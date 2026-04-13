"""SmartRouterService — unified routing layer integrating multiple strategies.

Strategies:
  - complexity: Rule-based 7-dimension scoring (mirrors LiteLLM Complexity Router)
  - classifier: RouteLLM trained classifier (MF / BERT / SW Ranking)
  - off: Passthrough, no routing
"""

from __future__ import annotations

import logging
import time
from typing import Any

from flowgate.config import SmartRouterConfig
from flowgate.smart_router.complexity import ComplexityScorer, RoutingResult

logger = logging.getLogger("flowgate.smart_router")

_routellm_available: bool | None = None


def _check_routellm() -> bool:
    """Check if routellm is installed without importing it (avoids OpenAI client init at load time)."""
    global _routellm_available
    if _routellm_available is None:
        import importlib.util
        _routellm_available = importlib.util.find_spec("routellm") is not None
    return _routellm_available


class SmartRouterService:
    """Unified routing: delegates to complexity scorer or RouteLLM based on config."""

    def __init__(self, config: SmartRouterConfig) -> None:
        self._config = config
        self._scorer: ComplexityScorer | None = None
        self._routellm_controller: Any = None
        self._build()

    @property
    def config(self) -> SmartRouterConfig:
        return self._config

    def reload(self, config: SmartRouterConfig) -> None:
        self._config = config
        self._scorer = None
        self._routellm_controller = None
        self._build()

    def _build(self) -> None:
        cfg = self._config
        if not cfg.enabled or cfg.strategy == "off":
            return

        if cfg.strategy == "complexity":
            self._scorer = ComplexityScorer(
                weights=cfg.dimension_weights,
                boundaries=cfg.tier_boundaries,
            )

        elif cfg.strategy == "classifier":
            if not _check_routellm():
                logger.warning(
                    "RouteLLM not installed — falling back to complexity strategy. "
                    "Install with: pip install 'flow-llm-router[classifier]'"
                )
                self._config.strategy = "complexity"
                self._scorer = ComplexityScorer(
                    weights=cfg.dimension_weights,
                    boundaries=cfg.tier_boundaries,
                )
                return

            try:
                import os
                from openai import OpenAI

                # routellm's SW router instantiates a global OpenAI() client at import time.
                # We monkey-patch it BEFORE importing Controller so it uses our configured
                # credentials. This avoids touching any RouteLLM source code.
                openai_kwargs: dict[str, str] = {}
                if cfg.mf_embedding_api_key:
                    openai_kwargs["api_key"] = cfg.mf_embedding_api_key
                elif not os.environ.get("OPENAI_API_KEY"):
                    # Supply a dummy key so the OpenAI() constructor doesn't raise.
                    # It only matters for actual MF embedding calls, not BERT.
                    os.environ["OPENAI_API_KEY"] = "dummy-key-for-routellm-init"
                if cfg.mf_embedding_base_url:
                    openai_kwargs["base_url"] = cfg.mf_embedding_base_url

                import routellm.routers.similarity_weighted.utils as _sw_utils  # noqa: PLC0415
                _sw_utils.OPENAI_CLIENT = OpenAI(**openai_kwargs)

                from routellm.controller import Controller  # noqa: PLC0415
                # strong_model/weak_model on Controller only affect ctrl.completion() calls;
                # we use the router's calculate_strong_win_rate() directly, so these are stubs.
                self._routellm_controller = Controller(
                    routers=[cfg.classifier_type],
                    strong_model="gpt-4o",
                    weak_model="gpt-4o-mini",
                )

                # Apply user-configured embedding model name to the MF router (catalog id; empty → OpenAI default name).
                if cfg.classifier_type == "mf":
                    mf_router = self._routellm_controller.routers.get("mf")
                    emb = (cfg.mf_embedding_model or "").strip() or "text-embedding-3-small"
                    if mf_router and hasattr(mf_router, "model") and hasattr(mf_router.model, "embedding_model"):
                        mf_router.model.embedding_model = emb
                        logger.info("MF router embedding model set to: %s", emb)

                logger.info("RouteLLM initialized: router=%s", cfg.classifier_type)
            except Exception as e:
                logger.error("Failed to initialize RouteLLM: %s — falling back to complexity", e)
                self._config.strategy = "complexity"
                self._scorer = ComplexityScorer(
                    weights=cfg.dimension_weights,
                    boundaries=cfg.tier_boundaries,
                )

    def route(self, messages: list[dict], requested_model: str) -> RoutingResult:
        cfg = self._config
        if not cfg.enabled or cfg.strategy == "off":
            return RoutingResult(
                model=requested_model, tier="DIRECT", score=0.0,
                original_model=requested_model,
            )

        if cfg.strategy == "classifier" and self._routellm_controller is not None:
            return self._route_classifier(messages, requested_model)

        return self._route_complexity(messages, requested_model)

    def _route_complexity(self, messages: list[dict], requested_model: str) -> RoutingResult:
        if self._scorer is None:
            self._scorer = ComplexityScorer(
                weights=self._config.dimension_weights,
                boundaries=self._config.tier_boundaries,
            )
        score = self._scorer.score(messages)
        tier = self._scorer.score_to_tier(score)
        model = self._config.tiers.get(tier, requested_model)
        return RoutingResult(
            model=model, tier=tier, score=round(score, 4),
            original_model=requested_model,
        )

    def _route_classifier(self, messages: list[dict], requested_model: str) -> RoutingResult:
        """Score using the underlying RouteLLM router directly (no LLM API call needed).

        Maps the continuous win-rate score [0, 1] to the same 4-tier system used by
        the complexity scorer (SIMPLE → MEDIUM → COMPLEX → REASONING), then looks up
        the target model from cfg.tiers — so both strategies share one model mapping.
        """
        cfg = self._config
        ctrl = self._routellm_controller
        try:
            router = ctrl.routers[cfg.classifier_type]

            # Concatenate non-system turns into a single scoring string
            prompt = "\n".join(
                m.get("content", "") for m in messages
                if isinstance(m.get("content"), str) and m.get("role") != "system"
            ).strip() or (messages[-1].get("content", "") if messages else "")

            score = float(router.calculate_strong_win_rate(prompt))
            tier = self._classifier_score_to_tier(score, cfg.classifier_tier_boundaries)
            model = cfg.tiers.get(tier, requested_model)

            return RoutingResult(
                model=model, tier=tier, score=round(score, 4),
                original_model=requested_model,
            )
        except Exception as e:
            # MF router requires OpenAI embeddings API; BERT is fully local.
            logger.warning(
                "RouteLLM routing failed (%s: %s) — falling back to complexity scoring. "
                "For MF, ensure the embedding model is synced from Providers and the vault is unlocked, "
                "or set OPENAI_API_KEY / OPENAI_BASE_URL.",
                type(e).__name__, e,
            )
            return self._route_complexity(messages, requested_model)

    @staticmethod
    def _classifier_score_to_tier(score: float, boundaries: dict[str, float]) -> str:
        """Map a [0, 1] classifier win-rate score to SIMPLE/MEDIUM/COMPLEX/REASONING."""
        if score < boundaries.get("simple_medium", 0.30):
            return "SIMPLE"
        if score < boundaries.get("medium_complex", 0.50):
            return "MEDIUM"
        if score < boundaries.get("complex_reasoning", 0.70):
            return "COMPLEX"
        return "REASONING"

    def test_route(self, messages: list[dict], model: str = "gpt-4o") -> dict:
        """Test routing without making LLM calls. Returns detailed result for the UI."""
        start = time.perf_counter_ns()
        result = self.route(messages, model)
        elapsed_us = (time.perf_counter_ns() - start) // 1000
        return {
            "strategy": self._config.strategy if self._config.enabled else "off",
            "score": result.score,
            "tier": result.tier,
            "routed_model": result.model,
            "original_model": result.original_model,
            "latency_us": elapsed_us,
        }

    def get_config_dict(self) -> dict:
        """Serialize current config for the API."""
        cfg = self._config
        return {
            "enabled": cfg.enabled,
            "strategy": cfg.strategy if cfg.enabled else "off",
            "complexity": {
                "tiers": cfg.tiers,
                "tier_boundaries": cfg.tier_boundaries,
                "dimension_weights": cfg.dimension_weights,
            },
            "classifier": {
                "type": cfg.classifier_type,
                "tier_boundaries": cfg.classifier_tier_boundaries,
                "available": _check_routellm(),
                "mf_embedding_model": cfg.mf_embedding_model,
            },
        }

    @staticmethod
    def config_from_dict(data: dict) -> SmartRouterConfig:
        """Deserialize API payload into SmartRouterConfig."""
        defaults = SmartRouterConfig()
        strategy = data.get("strategy", "off")
        enabled = strategy != "off" and data.get("enabled", True)
        cx = data.get("complexity", {})
        cl = data.get("classifier", {})
        return SmartRouterConfig(
            enabled=enabled,
            strategy=strategy if enabled else "off",
            tiers=cx.get("tiers", defaults.tiers),
            tier_boundaries=cx.get("tier_boundaries", defaults.tier_boundaries),
            dimension_weights=cx.get("dimension_weights", defaults.dimension_weights),
            classifier_type=cl.get("type", defaults.classifier_type),
            classifier_tier_boundaries=cl.get("tier_boundaries", defaults.classifier_tier_boundaries),
            # UI/API must not supply embedding URLs or keys; YAML can still set via load_settings.
            mf_embedding_base_url="",
            mf_embedding_api_key="",
            mf_embedding_model=cl.get("mf_embedding_model", defaults.mf_embedding_model),
        )
