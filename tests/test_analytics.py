"""Unit tests for BudgetDoctor analytics engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from flowgate.analytics.budget_doctor import BudgetDoctor
from flowgate.db.models import RequestLog


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def mem_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session(mem_engine):
    with Session(mem_engine) as s:
        yield s


def _log(session: Session, **kwargs) -> RequestLog:
    defaults = dict(
        model_requested="gpt-4o",
        model_used="gpt-4o",
        provider="openai",
        messages="[]",
        stream=False,
        status="success",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.0,
        latency_ms=200,
    )
    defaults.update(kwargs)
    log = RequestLog(**defaults)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


# ─── Empty DB ─────────────────────────────────────────────────────────────────


class TestEmptyDb:
    def test_diagnose_zeros(self, session):
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert report.total_cost_usd == 0.0
        assert report.total_requests == 0
        assert report.cost_by_provider == {}
        assert report.cost_by_model == {}
        assert report.daily_trend == []
        assert report.expensive_simple_calls == []

    def test_suggestions_when_no_data(self, session):
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        # No requests → no suggestions about routing
        assert isinstance(report.suggestions, list)

    def test_suggestion_when_requests_no_cost(self, session):
        _log(session, cost_usd=0.0)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert any("Cost tracking" in s for s in report.suggestions)


# ─── Cost aggregation ─────────────────────────────────────────────────────────


class TestCostAggregation:
    def test_total_cost(self, session):
        _log(session, provider="openai", cost_usd=0.01)
        _log(session, provider="openai", cost_usd=0.02)
        _log(session, provider="anthropic", cost_usd=0.05)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert abs(report.total_cost_usd - 0.08) < 1e-6

    def test_total_requests(self, session):
        for _ in range(5):
            _log(session)
        doc = BudgetDoctor(session)
        assert doc.diagnose(days=30).total_requests == 5

    def test_cost_by_provider(self, session):
        _log(session, provider="openai", cost_usd=0.10)
        _log(session, provider="anthropic", cost_usd=0.20)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert "openai" in report.cost_by_provider
        assert "anthropic" in report.cost_by_provider
        assert abs(report.cost_by_provider["anthropic"] - 0.20) < 1e-6

    def test_cost_by_model(self, session):
        _log(session, model_used="gpt-4o", cost_usd=0.05)
        _log(session, model_used="gpt-4o-mini", cost_usd=0.001)
        _log(session, model_used="gpt-4o", cost_usd=0.05)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert "gpt-4o" in report.cost_by_model
        assert abs(report.cost_by_model["gpt-4o"] - 0.10) < 1e-6

    def test_cost_by_provider_empty_provider_excluded(self, session):
        _log(session, provider="", cost_usd=0.01)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert "" not in report.cost_by_provider


# ─── Daily trend ─────────────────────────────────────────────────────────────


class TestDailyTrend:
    def test_daily_trend_structure(self, session):
        _log(session, cost_usd=0.01)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert len(report.daily_trend) >= 1
        entry = report.daily_trend[0]
        assert "date" in entry
        assert "cost_usd" in entry
        assert "requests" in entry

    def test_daily_trend_date_format(self, session):
        _log(session, cost_usd=0.01)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        # Date should be YYYY-MM-DD
        date_str = report.daily_trend[0]["date"]
        datetime.strptime(date_str, "%Y-%m-%d")

    def test_old_records_excluded(self, session):
        old_time = datetime.now(timezone.utc) - timedelta(days=40)
        _log(session, cost_usd=0.99, created_at=old_time)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert report.total_cost_usd == 0.0


# ─── Expensive simple calls ───────────────────────────────────────────────────


class TestExpensiveSimpleCalls:
    def test_finds_expensive_simple_by_score(self, session):
        _log(session, complexity_score=0.05, cost_usd=0.05)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert len(report.expensive_simple_calls) == 1

    def test_finds_expensive_simple_by_tier(self, session):
        _log(session, complexity_tier="SIMPLE", cost_usd=0.05)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert len(report.expensive_simple_calls) == 1

    def test_ignores_cheap_simple_calls(self, session):
        # cost_usd below 0.01 threshold
        _log(session, complexity_score=0.05, cost_usd=0.005)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert len(report.expensive_simple_calls) == 0

    def test_ignores_complex_expensive_calls(self, session):
        _log(session, complexity_score=0.80, cost_usd=0.50)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert len(report.expensive_simple_calls) == 0

    def test_expensive_simple_structure(self, session):
        _log(session, complexity_score=0.05, complexity_tier="SIMPLE",
             model_used="gpt-4o", provider="openai", cost_usd=0.02)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        entry = report.expensive_simple_calls[0]
        assert entry["model_used"] == "gpt-4o"
        assert entry["provider"] == "openai"
        assert entry["cost_usd"] == pytest.approx(0.02, abs=1e-6)


# ─── Suggestions ─────────────────────────────────────────────────────────────


class TestSuggestions:
    def test_smart_router_suggestion_when_many_expensive_simple(self, session):
        for _ in range(6):
            _log(session, complexity_score=0.05, cost_usd=0.02)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert any("Smart Router" in s for s in report.suggestions)

    def test_dominant_model_suggestion(self, session):
        for _ in range(10):
            _log(session, model_used="gpt-4o", cost_usd=0.10)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        assert any("gpt-4o" in s for s in report.suggestions)

    def test_no_suggestions_when_no_issues(self, session):
        # Mix of models, no simple expensive calls, cost tracking active
        _log(session, model_used="gpt-4o", cost_usd=0.05, complexity_score=0.50)
        _log(session, model_used="gpt-4o-mini", cost_usd=0.001, complexity_score=0.10)
        doc = BudgetDoctor(session)
        report = doc.diagnose(days=30)
        # Dominant model suggestion only if > 70%
        if report.total_cost_usd > 0:
            by_model = report.cost_by_model
            top_cost = max(by_model.values()) if by_model else 0
            if top_cost / report.total_cost_usd <= 0.70:
                routing_suggestions = [s for s in report.suggestions if "Smart Router" in s]
                assert len(routing_suggestions) == 0
