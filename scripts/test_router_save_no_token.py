#!/usr/bin/env python3
"""Smoke test: save router config without auth token."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def http_json(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    payload = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        data = {}
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"raw": raw}
        return e.code, data


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify /api/router/config save works without token")
    parser.add_argument("--base-url", default="http://127.0.0.1:7789", help="Server base URL")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    health_status, health_data = http_json(f"{base}/api/health")
    print(f"[health] status={health_status} body={health_data}")
    if health_status != 200:
        print("FAIL: health check failed")
        return 1

    payload = {
        "enabled": True,
        "strategy": "classifier",
        "complexity": {
            "tiers": {
                "SIMPLE": "siliconflow/Pro/zai-org/GLM-4.7",
                "MEDIUM": "siliconflow/Pro/zai-org/GLM-5",
                "COMPLEX": "siliconflow/Pro/zai-org/GLM-5.1",
                "REASONING": "siliconflow/Pro/moonshotai/Kimi-K2.5",
            },
            "tier_boundaries": {
                "simple_medium": 0.25,
                "medium_complex": 0.5,
                "complex_reasoning": 0.75,
            },
            "dimension_weights": {
                "tokenCount": 0.15,
                "codePresence": 0.2,
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
                "medium_complex": 0.4,
                "complex_reasoning": 0.5,
            },
            "mf_embedding_model": "siliconflow/Qwen/Qwen3-Embedding-4B",
        },
    }

    save_status, save_data = http_json(f"{base}/api/router/config", method="PUT", body=payload)
    print(f"[save] status={save_status} body={save_data}")
    if save_status != 200:
        print("FAIL: save request did not return 200")
        return 1
    if not save_data.get("success"):
        print("FAIL: save response success=false")
        return 1

    # Note: service may fallback strategy at runtime when MF assets are unavailable.
    saved_strategy = save_data.get("data", {}).get("strategy")
    print(f"[save] returned strategy={saved_strategy}")

    get_status, get_data = http_json(f"{base}/api/router/config")
    print(f"[get] status={get_status} body={get_data}")
    if get_status != 200 or not get_data.get("success"):
        print("FAIL: get config failed after save")
        return 1

    print("PASS: router config save endpoint works without token.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
