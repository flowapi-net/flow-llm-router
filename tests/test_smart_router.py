"""Unit tests for SmartRouter complexity scoring, service layer, and routing."""

from __future__ import annotations

import pytest

from flowgate.config import SmartRouterConfig
from flowgate.smart_router.complexity import ComplexityScorer, RoutingResult
from flowgate.smart_router.service import SmartRouterService


def _service(enabled: bool = True, strategy: str = "complexity", **kwargs) -> SmartRouterService:
    cfg = SmartRouterConfig(
        enabled=enabled,
        strategy=strategy,
        tiers={
            "SIMPLE": "gpt-4o-mini",
            "MEDIUM": "gpt-4o",
            "COMPLEX": "claude-sonnet",
            "REASONING": "o1-preview",
        },
        tier_boundaries={
            "simple_medium": 0.15,
            "medium_complex": 0.35,
            "complex_reasoning": 0.60,
        },
    )
    return SmartRouterService(cfg)


def _msg(content: str, role: str = "user") -> dict:
    return {"role": role, "content": content}


# ─── Disabled / off mode ─────────────────────────────────────────────────────


class TestDisabledRouter:
    def test_returns_direct_tier(self):
        svc = _service(enabled=False)
        result = svc.route([_msg("Hello")], "gpt-4o")
        assert result.tier == "DIRECT"

    def test_off_strategy(self):
        svc = _service(enabled=True, strategy="off")
        result = svc.route([_msg("Hello")], "gpt-4o")
        assert result.tier == "DIRECT"

    def test_preserves_original_model(self):
        svc = _service(enabled=False)
        result = svc.route([_msg("Implement a Raft consensus algorithm")], "claude-sonnet")
        assert result.model == "claude-sonnet"
        assert result.original_model == "claude-sonnet"

    def test_score_is_zero(self):
        svc = _service(enabled=False)
        result = svc.route([_msg("Write me a full OS kernel")], "gpt-4o")
        assert result.score == 0.0


# ─── SIMPLE tier ──────────────────────────────────────────────────────────────


class TestSimpleTier:
    def test_greeting(self):
        svc = _service()
        result = svc.route([_msg("Hello!")], "gpt-4o")
        assert result.tier == "SIMPLE"
        assert result.model == "gpt-4o-mini"

    def test_basic_definition(self):
        svc = _service()
        result = svc.route([_msg("What is Python?")], "gpt-4o")
        assert result.tier == "SIMPLE"

    def test_empty_messages(self):
        svc = _service()
        result = svc.route([], "gpt-4o")
        assert result.tier == "SIMPLE"

    def test_no_user_messages(self):
        svc = _service()
        result = svc.route([{"role": "system", "content": "You are helpful."}], "gpt-4o")
        assert result.tier == "SIMPLE"

    def test_short_question(self):
        svc = _service()
        result = svc.route([_msg("Define recursion")], "gpt-4o")
        assert result.tier == "SIMPLE"


# ─── MEDIUM tier ─────────────────────────────────────────────────────────────


class TestMediumTier:
    def test_moderate_technical_request(self):
        svc = _service()
        result = svc.route(
            [_msg("Write a Python function to implement database query with error handling and unit tests")],
            "gpt-4o",
        )
        assert result.tier in ("MEDIUM", "COMPLEX")

    def test_score_in_medium_range(self):
        svc = _service()
        result = svc.route(
            [_msg("Implement a Python function with database query and proper error handling")],
            "gpt-4o",
        )
        assert result.score >= 0.15


# ─── COMPLEX tier ────────────────────────────────────────────────────────────


class TestComplexTier:
    def test_code_heavy_request(self):
        svc = _service()
        message = (
            "Implement a distributed database sharding system with API interface, "
            "concurrent async code, and query optimization using microservice architecture."
        )
        result = svc.route([_msg(message)], "gpt-4o")
        assert result.tier in ("MEDIUM", "COMPLEX", "REASONING")

    def test_model_is_routed(self):
        svc = _service()
        message = (
            "Implement a distributed consensus algorithm with concurrent database sharding, "
            "API interface, microservice architecture, and async code optimization."
        )
        result = svc.route([_msg(message)], "gpt-4o")
        assert result.tier in ("COMPLEX", "REASONING")
        assert result.model in ("claude-sonnet", "o1-preview")

    def test_multiple_technical_terms(self):
        svc = _service()
        message = (
            "Explain the trade-offs between different consensus algorithms "
            "like Raft and Paxos for distributed systems, including CAP theorem implications."
        )
        result = svc.route([_msg(message)], "gpt-4o")
        assert result.tier in ("COMPLEX", "REASONING")


# ─── REASONING tier ──────────────────────────────────────────────────────────


class TestReasoningTier:
    def test_step_by_step_with_analyze(self):
        svc = _service()
        message = (
            "Please think through this problem step by step and analyze "
            "the root cause of the memory leak in this service."
        )
        result = svc.route([_msg(message)], "gpt-4o")
        assert result.tier == "REASONING"
        assert result.model == "o1-preview"

    def test_two_reasoning_markers_shortcut(self):
        svc = _service()
        message = "Step by step, analyze the pros and cons of this architecture."
        result = svc.route([_msg(message)], "gpt-4o")
        assert result.tier == "REASONING"
        assert result.score == 1.0

    def test_reasoning_tier_uses_configured_model(self):
        cfg = SmartRouterConfig(
            enabled=True,
            tiers={"REASONING": "o3-mini", "SIMPLE": "gpt-4o-mini", "MEDIUM": "gpt-4o", "COMPLEX": "claude"},
            tier_boundaries={"simple_medium": 0.15, "medium_complex": 0.35, "complex_reasoning": 0.60},
        )
        svc = SmartRouterService(cfg)
        message = "Analyze this step by step and think through every trade-off."
        result = svc.route([_msg(message)], "gpt-4o")
        assert result.tier == "REASONING"
        assert result.model == "o3-mini"


# ─── SmartRouterService features ─────────────────────────────────────────────


class TestSmartRouterService:
    def test_get_config_dict(self):
        svc = _service()
        d = svc.get_config_dict()
        assert d["enabled"] is True
        assert d["strategy"] == "complexity"
        assert "SIMPLE" in d["complexity"]["tiers"]
        assert "type" in d["classifier"]

    def test_reload(self):
        svc = _service(enabled=False)
        result = svc.route([_msg("Hello")], "gpt-4o")
        assert result.tier == "DIRECT"

        new_cfg = SmartRouterConfig(
            enabled=True,
            tiers={"SIMPLE": "test-model", "MEDIUM": "gpt-4o", "COMPLEX": "claude", "REASONING": "o1"},
            tier_boundaries={"simple_medium": 0.15, "medium_complex": 0.35, "complex_reasoning": 0.60},
        )
        svc.reload(new_cfg)
        result = svc.route([_msg("Hello")], "gpt-4o")
        assert result.tier == "SIMPLE"
        assert result.model == "test-model"

    def test_test_route(self):
        svc = _service()
        result = svc.test_route([_msg("Hello")], "gpt-4o")
        assert "strategy" in result
        assert "tier" in result
        assert "routed_model" in result
        assert "latency_us" in result

    def test_config_from_dict(self):
        data = {
            "enabled": True,
            "strategy": "complexity",
            "complexity": {
                "tiers": {"SIMPLE": "a", "MEDIUM": "b", "COMPLEX": "c", "REASONING": "d"},
                "tier_boundaries": {"simple_medium": 0.1, "medium_complex": 0.3, "complex_reasoning": 0.5},
            },
            "classifier": {
                "type": "bert",
                "tier_boundaries": {
                    "simple_medium": 0.2,
                    "medium_complex": 0.4,
                    "complex_reasoning": 0.55,
                },
            },
        }
        cfg = SmartRouterService.config_from_dict(data)
        assert cfg.enabled is True
        assert cfg.tiers["SIMPLE"] == "a"
        assert cfg.classifier_type == "bert"
        assert cfg.classifier_tier_boundaries["simple_medium"] == 0.2

    def test_config_from_dict_ignores_embedding_secrets_from_client(self):
        data = {
            "enabled": True,
            "strategy": "classifier",
            "complexity": {
                "tiers": {"SIMPLE": "a", "MEDIUM": "b", "COMPLEX": "c", "REASONING": "d"},
                "tier_boundaries": {"simple_medium": 0.1, "medium_complex": 0.3, "complex_reasoning": 0.5},
            },
            "classifier": {
                "type": "mf",
                "tier_boundaries": {
                    "simple_medium": 0.2,
                    "medium_complex": 0.4,
                    "complex_reasoning": 0.55,
                },
                "mf_embedding_api_key": "should-not-be-used",
                "mf_embedding_base_url": "https://evil.example/v1",
                "mf_embedding_model": "text-embedding-3-small",
            },
        }
        cfg = SmartRouterService.config_from_dict(data)
        assert cfg.mf_embedding_api_key == ""
        assert cfg.mf_embedding_base_url == ""
        assert cfg.mf_embedding_model == "text-embedding-3-small"

    def test_classifier_fallback_without_routellm(self, monkeypatch):
        monkeypatch.setattr("flowgate.smart_router.service._check_routellm", lambda: False)
        cfg = SmartRouterConfig(enabled=True, strategy="classifier")
        svc = SmartRouterService(cfg)
        result = svc.route([_msg("Hello")], "gpt-4o")
        assert result.tier in ("SIMPLE", "DIRECT")


# ─── ComplexityScorer direct tests ───────────────────────────────────────────


class TestComplexityScorer:
    def test_custom_weights(self):
        scorer = ComplexityScorer(
            weights={"codePresence": 0.50, "tokenCount": 0.50},
            boundaries={"simple_medium": 0.25, "medium_complex": 0.50, "complex_reasoning": 0.75},
        )
        score = scorer.score([_msg("function class api database algorithm")])
        assert score > 0.4

    def test_score_ordering(self):
        scorer = ComplexityScorer()
        simple = scorer.score([_msg("Hi!")])
        medium = scorer.score([_msg("Write a function to parse JSON in Python")])
        complex_ = scorer.score(
            [_msg("Implement a distributed consensus algorithm with database and api layers")]
        )
        assert simple < medium
        assert medium < complex_


# ─── Routing result fields ────────────────────────────────────────────────────


class TestRoutingResultFields:
    def test_original_model_preserved(self):
        svc = _service()
        result = svc.route([_msg("What is the meaning of life?")], "my-custom-model")
        assert result.original_model == "my-custom-model"

    def test_score_between_0_and_1(self):
        svc = _service()
        for content in [
            "Hi",
            "Write a complex distributed system with consensus algorithm step by step",
            "Implement a class with database and api code and analyze trade-offs",
        ]:
            result = svc.route([_msg(content)], "gpt-4o")
            assert 0.0 <= result.score <= 1.0, f"Score {result.score} out of range for: {content}"

    def test_multipart_user_content(self):
        svc = _service()
        messages = [{"role": "user", "content": [{"type": "text", "text": "What is Python?"}]}]
        result = svc.route(messages, "gpt-4o")
        assert result.tier == "SIMPLE"

    def test_only_user_messages_scored(self):
        svc = _service()
        messages = [
            {"role": "system", "content": "Implement a complex distributed consensus algorithm step by step."},
            {"role": "user", "content": "Hello"},
        ]
        result = svc.route(messages, "gpt-4o")
        assert result.tier == "SIMPLE"
