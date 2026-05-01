"""Budget Doctor — SQL-driven cost diagnostics engine.

Analyses the RequestLog table and produces actionable optimisation suggestions.
Described in DESIGN.md §5.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, text


@dataclass
class DiagnosisReport:
    total_cost_usd: float
    total_requests: int
    cost_by_provider: dict[str, float]
    cost_by_model: dict[str, float]
    daily_trend: list[dict]                   # [{date, cost_usd, requests}]
    expensive_simple_calls: list[dict]        # requests using expensive models for trivial tasks
    suggestions: list[str]


class BudgetDoctor:
    """Diagnose cost patterns and generate optimisation suggestions.

    Parameters
    ----------
    session:
        An open SQLModel / SQLAlchemy Session bound to the application DB.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # ── Public API ────────────────────────────────────────────────────────────

    def diagnose(self, days: int = 30) -> DiagnosisReport:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return DiagnosisReport(
            total_cost_usd=self._total_cost(since),
            total_requests=self._total_requests(since),
            cost_by_provider=self._cost_by_provider(since),
            cost_by_model=self._cost_by_model(since),
            daily_trend=self._daily_trend(since),
            expensive_simple_calls=self._expensive_simple_calls(since),
            suggestions=self._generate_suggestions(since),
        )

    # ── Private query methods ─────────────────────────────────────────────────

    def _total_cost(self, since: str) -> float:
        row = self.session.exec(
            text(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM request_logs "
                "WHERE created_at >= :since"
            ),
            params={"since": since},
        ).first()
        return round(float(row[0]), 6) if row else 0.0

    def _total_requests(self, since: str) -> int:
        row = self.session.exec(
            text(
                "SELECT COUNT(*) FROM request_logs WHERE created_at >= :since"
            ),
            params={"since": since},
        ).first()
        return int(row[0]) if row else 0

    def _cost_by_provider(self, since: str) -> dict[str, float]:
        rows = self.session.exec(
            text(
                """
                SELECT provider, COALESCE(SUM(cost_usd), 0.0) as total
                FROM request_logs
                WHERE created_at >= :since AND provider != ''
                GROUP BY provider
                ORDER BY total DESC
                """
            ),
            params={"since": since},
        ).all()
        return {r[0]: round(float(r[1]), 6) for r in rows}

    def _cost_by_model(self, since: str) -> dict[str, float]:
        rows = self.session.exec(
            text(
                """
                SELECT model_used, COALESCE(SUM(cost_usd), 0.0) as total
                FROM request_logs
                WHERE created_at >= :since
                GROUP BY model_used
                ORDER BY total DESC
                LIMIT 20
                """
            ),
            params={"since": since},
        ).all()
        return {r[0]: round(float(r[1]), 6) for r in rows}

    def _daily_trend(self, since: str) -> list[dict]:
        rows = self.session.exec(
            text(
                """
                SELECT strftime('%Y-%m-%d', created_at) as day,
                       COALESCE(SUM(cost_usd), 0.0) as cost_usd,
                       COUNT(*) as requests
                FROM request_logs
                WHERE created_at >= :since
                GROUP BY day
                ORDER BY day
                """
            ),
            params={"since": since},
        ).all()
        return [{"date": r[0], "cost_usd": round(float(r[1]), 6), "requests": r[2]} for r in rows]

    def _expensive_simple_calls(self, since: str, cost_threshold: float = 0.01) -> list[dict]:
        """Find requests with low complexity but unexpectedly high cost.

        Targets requests where:
        - complexity_score < 0.15 (simple prompt), OR complexity_tier = 'SIMPLE'
        - cost_usd > cost_threshold
        """
        rows = self.session.exec(
            text(
                """
                SELECT id, created_at, model_used, provider,
                       complexity_score, complexity_tier,
                       cost_usd, total_tokens
                FROM request_logs
                WHERE created_at >= :since
                  AND cost_usd > :threshold
                  AND (
                      (complexity_score IS NOT NULL AND complexity_score < 0.15)
                      OR complexity_tier = 'SIMPLE'
                  )
                ORDER BY cost_usd DESC
                LIMIT 50
                """
            ),
            params={"since": since, "threshold": cost_threshold},
        ).all()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "model_used": r[2],
                "provider": r[3],
                "complexity_score": r[4],
                "complexity_tier": r[5],
                "cost_usd": round(float(r[6]), 6),
                "total_tokens": r[7],
            }
            for r in rows
        ]

    def _generate_suggestions(self, since: str) -> list[str]:
        suggestions: list[str] = []

        expensive_simple = self._expensive_simple_calls(since)
        if len(expensive_simple) > 5:
            wasted = sum(r["cost_usd"] for r in expensive_simple)
            suggestions.append(
                f"Found {len(expensive_simple)} simple requests using expensive models. "
                f"Enable Smart Router to auto-downgrade — estimated saving: ${wasted:.4f}"
            )

        total = self._total_cost(since)
        by_model = self._cost_by_model(since)
        if by_model and total > 0:
            top_model, top_cost = next(iter(by_model.items()))
            pct = top_cost / total * 100
            if pct > 70:
                suggestions.append(
                    f"Model '{top_model}' accounts for {pct:.0f}% of total cost. "
                    "Consider distributing load across cheaper models for simpler tasks."
                )

        if total == 0 and self._total_requests(since) > 0:
            suggestions.append(
                "Cost tracking is not yet active. Enable Smart Router to start "
                "capturing per-request USD costs via LiteLLM."
            )

        return suggestions
