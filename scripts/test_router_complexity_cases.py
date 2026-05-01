#!/usr/bin/env python3
"""Router complexity smoke test with expected tier assertions.

What it does:
1) Reads current router config from API.
2) Temporarily switches router to deterministic complexity mode.
3) Runs representative prompts for SIMPLE/MEDIUM/COMPLEX/REASONING.
4) Verifies tier (and rough score range) for each case.
5) Restores original router config.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Case:
    name: str
    prompt: str
    expected_tier: str
    min_score: float
    max_score: float


CASES: list[Case] = [
    Case(
        name="simple_greeting",
        prompt="Hello!",
        expected_tier="SIMPLE",
        min_score=0.0,
        max_score=0.02,
    ),
    Case(
        name="medium_distributed_request",
        prompt=(
            "Implement a distributed database sharding service with API endpoints, "
            "async workers, and query optimization."
        ),
        expected_tier="MEDIUM",
        min_score=0.24,
        max_score=0.30,
    ),
    Case(
        name="complex_long_system_design",
        prompt=(
            "I need a production-grade design for a distributed system. "
            "Implement API gateway middleware, database schema, query optimization, async workers, "
            "docker deployment, kubernetes autoscaling, recursive retry algorithm, and interface contracts. "
            "Include microservice boundaries, sharding, replication, consensus, throughput tuning, latency budgets, "
            "race condition handling, deadlock avoidance, mutex strategy, oauth and jwt authentication, tls cipher selection, "
            "and vector database embedding pipeline. Provide endpoint naming, SQL migration strategy, rollback plan, "
            "benchmarking plan, observability, and incident playbooks. Also cover failure modes for network partitions, "
            "stale cache, duplicate events, and idempotency keys. What architecture should we use? Which algorithm is best? "
            "How should we optimize performance? "
            + " ".join(["Add detailed API/database interface examples and deployment checks."] * 25)
        ),
        expected_tier="COMPLEX",
        min_score=0.50,
        max_score=0.62,
    ),
    Case(
        name="reasoning_step_by_step",
        prompt=(
            "Step by step, analyze the trade-offs between Raft and Paxos "
            "for a multi-region distributed system."
        ),
        expected_tier="REASONING",
        min_score=0.99,
        max_score=1.0,
    ),
]


def http_json(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    payload = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw}
        return e.code, data


def make_complexity_config(current_data: dict) -> dict:
    """Build deterministic complexity config for repeatable test results."""
    complexity = current_data.get("complexity", {})
    tiers = complexity.get("tiers", {})
    if not tiers:
        tiers = {
            "SIMPLE": "gpt-4o-mini",
            "MEDIUM": "gpt-4o",
            "COMPLEX": "claude-sonnet",
            "REASONING": "o1-preview",
        }
    return {
        "enabled": True,
        "strategy": "complexity",
        "complexity": {
            "tiers": tiers,
            "tier_boundaries": {
                "simple_medium": 0.25,
                "medium_complex": 0.50,
                "complex_reasoning": 0.75,
            },
            "dimension_weights": {
                "tokenCount": 0.15,
                "codePresence": 0.20,
                "reasoningMarkers": 0.25,
                "technicalTerms": 0.15,
                "simpleIndicators": 0.15,
                "multiStepPatterns": 0.05,
                "questionComplexity": 0.05,
            },
        },
        "classifier": {
            "type": "mf",
            "tier_boundaries": {
                "simple_medium": 0.28,
                "medium_complex": 0.40,
                "complex_reasoning": 0.50,
            },
            "mf_embedding_model": current_data.get("classifier", {}).get(
                "mf_embedding_model", "text-embedding-3-small"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run router complexity expectation cases")
    parser.add_argument("--base-url", default="http://127.0.0.1:7789", help="API base URL")
    parser.add_argument(
        "--keep-config",
        action="store_true",
        help="Do not restore original router config after test",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    health_status, health_data = http_json(f"{base}/api/health")
    print(f"[health] status={health_status} body={health_data}")
    if health_status != 200:
        print("FAIL: health check failed")
        return 1

    get_status, get_data = http_json(f"{base}/api/router/config")
    if get_status != 200 or not get_data.get("success"):
        print(f"FAIL: cannot fetch router config. status={get_status} body={get_data}")
        return 1
    original_config = get_data["data"]

    test_config = make_complexity_config(original_config)
    set_status, set_data = http_json(f"{base}/api/router/config", method="PUT", body=test_config)
    if set_status != 200 or not set_data.get("success"):
        print(f"FAIL: cannot set complexity test config. status={set_status} body={set_data}")
        return 1
    print("[setup] switched router to deterministic complexity mode")

    failures = 0
    for case in CASES:
        status, data = http_json(
            f"{base}/api/router/test",
            method="POST",
            body={"messages": [{"role": "user", "content": case.prompt}], "model": "gpt-4o"},
        )
        if status != 200 or not data.get("success"):
            failures += 1
            print(f"[{case.name}] FAIL: request error status={status} body={data}")
            continue

        result = data["data"]
        tier = result.get("tier")
        score = float(result.get("score", -1))
        ok_tier = tier == case.expected_tier
        ok_score = case.min_score <= score <= case.max_score
        ok = ok_tier and ok_score
        if not ok:
            failures += 1

        print(
            f"[{case.name}] {'PASS' if ok else 'FAIL'} "
            f"tier={tier} expected={case.expected_tier} "
            f"score={score:.4f} expected_range=[{case.min_score:.2f},{case.max_score:.2f}] "
            f"routed_model={result.get('routed_model')}"
        )

    if not args.keep_config:
        restore_status, restore_data = http_json(
            f"{base}/api/router/config",
            method="PUT",
            body=original_config,
        )
        if restore_status == 200 and restore_data.get("success"):
            print("[teardown] restored original router config")
        else:
            print(
                f"[teardown] WARN: failed to restore config. "
                f"status={restore_status} body={restore_data}"
            )
            failures += 1

    if failures:
        print(f"FAIL: {failures} case(s) failed")
        return 1

    print("PASS: all complexity router cases matched expected output")
    return 0


if __name__ == "__main__":
    sys.exit(main())
