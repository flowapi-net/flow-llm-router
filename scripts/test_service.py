#!/usr/bin/env python3
"""
FlowGate 服务集成测试脚本

用法:
  python scripts/test_service.py                         # 全部测试（需要已配置 Provider）
  python scripts/test_service.py --base http://127.0.0.1:7798
  python scripts/test_service.py --token fgt_xxxx        # 指定 Access Token
  python scripts/test_service.py --model gpt-4o-mini     # 指定模型
  python scripts/test_service.py --suite health          # 只跑 health 测试组
  python scripts/test_service.py --suite proxy           # 只跑代理测试组
"""

import argparse
import json
import sys
import time
from typing import Any

try:
    import httpx
except ImportError:
    print("❌ 依赖缺失，请先安装：pip install httpx")
    sys.exit(1)

# ─── ANSI 颜色 ───────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg: str) -> None: print(f"  {RED}✗{RESET} {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg: str) -> None: print(f"  {GRAY}→{RESET} {msg}")
def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}▸ {title}{RESET}")

# ─── Result tracker ──────────────────────────────────────────────────────────
passed = failed = skipped = 0

def check(name: str, cond: bool, detail: str = "") -> bool:
    global passed, failed
    if cond:
        passed += 1
        ok(f"{name}" + (f"  {GRAY}({detail}){RESET}" if detail else ""))
    else:
        failed += 1
        fail(f"{name}" + (f"  {GRAY}→ {detail}{RESET}" if detail else ""))
    return cond

def skip(name: str, reason: str = "") -> None:
    global skipped
    skipped += 1
    warn(f"{name}" + (f"  {GRAY}({reason}){RESET}" if reason else ""))

# ─── Tests ───────────────────────────────────────────────────────────────────

def test_health(client: httpx.Client, base: str) -> None:
    section("Health & 基础连通性")

    # 1. dashboard
    try:
        r = client.get(f"{base}/")
        check("Dashboard 页面可访问", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        fail(f"Dashboard 页面可访问  ({e})")

    # 2. vault status
    try:
        r = client.get(f"{base}/api/auth/status")
        check("Vault 状态接口 /api/auth/status", r.status_code == 200, f"HTTP {r.status_code}")
        data = r.json()
        info(f"vault_initialized={data.get('vault_initialized')}, vault_unlocked={data.get('vault_unlocked')}")
        if not data.get("vault_initialized"):
            warn("Vault 尚未初始化，代理相关测试可能失败")
        elif not data.get("vault_unlocked"):
            warn("Vault 已初始化但未解锁，代理相关测试可能失败")
    except Exception as e:
        fail(f"Vault 状态接口  ({e})")

    # 3. models list
    try:
        r = client.get(f"{base}/v1/models")
        check("/v1/models 接口", r.status_code == 200, f"HTTP {r.status_code}")
        models = r.json().get("data", [])
        info(f"返回 {len(models)} 个模型" + (f"，第一个: {models[0]['id']}" if models else "（空列表）"))
    except Exception as e:
        fail(f"/v1/models 接口  ({e})")

    # 4. server config
    try:
        r = client.get(f"{base}/api/server-config")
        check("服务器配置接口 /api/server-config", r.status_code == 200, f"HTTP {r.status_code}")
        cfg = r.json()
        info(f"host={cfg.get('host')}, port={cfg.get('port')}, ip_mode={cfg.get('ip_mode')}")
    except Exception as e:
        fail(f"服务器配置接口  ({e})")


def test_proxy_chat(client: httpx.Client, base: str, token: str, model: str) -> None:
    section("Chat Completions 代理（非流式）")

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "用一句话介绍你自己。"}],
        "max_tokens": 64,
    }

    try:
        t0 = time.monotonic()
        r = client.post(f"{base}/v1/chat/completions", json=payload, headers=headers, timeout=30)
        latency = (time.monotonic() - t0) * 1000

        check("HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code != 200:
            info(f"错误详情: {r.text[:200]}")
            return

        data = r.json()
        check("响应包含 choices", bool(data.get("choices")), str(data.get("choices")))
        content = data["choices"][0]["message"]["content"] if data.get("choices") else ""
        check("content 非空", bool(content), content[:60] if content else "空")
        usage = data.get("usage", {})
        check("包含 usage 统计", bool(usage), f"prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}")
        info(f"延迟 {latency:.0f}ms，模型: {data.get('model', model)}")
    except Exception as e:
        fail(f"Chat Completions 请求失败  ({e})")


def test_proxy_stream(client: httpx.Client, base: str, token: str, model: str) -> None:
    section("Chat Completions 代理（流式 SSE）")

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "数一二三四五，每个数字单独一行。"}],
        "max_tokens": 64,
        "stream": True,
    }

    try:
        t0 = time.monotonic()
        chunks: list[str] = []
        ttft_ms: float | None = None

        with client.stream("POST", f"{base}/v1/chat/completions", json=payload, headers=headers, timeout=30) as r:
            check("HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
            if r.status_code != 200:
                info(f"错误详情: {r.read()[:200]}")
                return

            for raw_line in r.iter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    c = delta.get("content", "")
                    if c:
                        if ttft_ms is None:
                            ttft_ms = (time.monotonic() - t0) * 1000
                        chunks.append(c)
                except Exception:
                    pass

        total_latency = (time.monotonic() - t0) * 1000
        full = "".join(chunks)
        check("收到流式 chunks", len(chunks) > 0, f"{len(chunks)} 个 chunk")
        check("合并内容非空", bool(full), full[:60] if full else "空")
        if ttft_ms:
            info(f"TTFT {ttft_ms:.0f}ms，总耗时 {total_latency:.0f}ms")
    except Exception as e:
        fail(f"流式请求失败  ({e})")


def test_proxy_params(client: httpx.Client, base: str, token: str, model: str) -> None:
    section("参数透传测试")

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # temperature=0（deterministic）
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "输出数字 42，仅此而已。"}],
        "max_tokens": 16,
        "temperature": 0,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }
    try:
        r = client.post(f"{base}/v1/chat/completions", json=payload, headers=headers, timeout=30)
        check("temperature/presence_penalty/frequency_penalty 参数透传", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        fail(f"参数透传测试  ({e})")

    # stop sequences
    payload2 = {
        "model": model,
        "messages": [{"role": "user", "content": "输出 A B C D"}],
        "max_tokens": 32,
        "stop": ["C"],
    }
    try:
        r = client.post(f"{base}/v1/chat/completions", json=payload2, headers=headers, timeout=30)
        check("stop 参数透传", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            check("stop 序列有效（不含 C 及之后内容）", "C" not in content, f"content='{content}'")
    except Exception as e:
        fail(f"stop 参数测试  ({e})")


def test_embeddings(client: httpx.Client, base: str, token: str, embed_model: str) -> None:
    section("Embeddings 接口")

    if not embed_model:
        skip("Embeddings 测试", "未指定 --embed-model，跳过")
        return

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {"model": embed_model, "input": ["Hello, FlowGate!", "测试向量化"]}

    try:
        r = client.post(f"{base}/v1/embeddings", json=payload, headers=headers, timeout=30)
        check("HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            check("返回 embedding 数据", len(data.get("data", [])) == 2, f"{len(data.get('data', []))} 条")
            dim = len(data["data"][0].get("embedding", [])) if data.get("data") else 0
            check("向量维度非零", dim > 0, f"维度={dim}")
    except Exception as e:
        fail(f"Embeddings 请求失败  ({e})")


def test_auth(client: httpx.Client, base: str, token: str) -> None:
    section("鉴权机制")

    # 检查没有 token 时的行为
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 8,
    }
    try:
        r = client.post(f"{base}/v1/chat/completions", json=payload, headers={}, timeout=10)
        if token:
            # 如果创建了 token，无 token 请求应该 401
            check("无 Token 时返回 401", r.status_code == 401, f"实际 HTTP {r.status_code}")
        else:
            # 没有创建 token，代理开放，实际调用结果取决于 vault
            info(f"未配置 Access Token，代理开放模式，HTTP {r.status_code}")
    except Exception as e:
        fail(f"鉴权测试  ({e})")

    # 错误 token
    r2 = client.post(f"{base}/v1/chat/completions", json=payload,
                     headers={"Authorization": "Bearer fgt_invalid_token_xyz"}, timeout=10)
    check("无效 Token 返回 401", r2.status_code == 401, f"实际 HTTP {r2.status_code}")


def test_logs(client: httpx.Client, base: str) -> None:
    section("日志记录验证")
    try:
        r = client.get(f"{base}/api/logs?limit=5")
        check("/api/logs 接口可访问", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            logs = r.json()
            count = len(logs) if isinstance(logs, list) else logs.get("total", 0)
            info(f"数据库中共 {count} 条日志")
    except Exception as e:
        fail(f"日志接口测试  ({e})")

    try:
        r = client.get(f"{base}/api/stats/overview")
        check("/api/stats/overview 接口可访问", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            stats = r.json()
            info(f"今日请求数: {stats.get('today_requests', 'N/A')}, 今日 tokens: {stats.get('today_tokens', 'N/A')}")
    except Exception as e:
        fail(f"统计接口测试  ({e})")


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FlowGate 服务集成测试")
    parser.add_argument("--base",        default="http://127.0.0.1:7798", help="FlowGate 服务地址")
    parser.add_argument("--token",       default="",                       help="FlowGate Access Token（可选）")
    parser.add_argument("--model",       default="gpt-4o-mini",            help="用于 chat 测试的模型 ID")
    parser.add_argument("--embed-model", default="",                       help="用于 embedding 测试的模型 ID")
    parser.add_argument("--suite",       default="all",
                        choices=["all", "health", "proxy", "stream", "params", "embed", "auth", "logs"],
                        help="只运行指定测试组")
    args = parser.parse_args()

    print(f"\n{BOLD}FlowGate 集成测试{RESET}")
    print(f"  服务地址: {CYAN}{args.base}{RESET}")
    print(f"  模型:     {CYAN}{args.model}{RESET}")
    print(f"  Token:    {CYAN}{args.token[:12] + '…' if args.token else '（未指定，开放模式）'}{RESET}")
    print(f"  测试组:   {CYAN}{args.suite}{RESET}")

    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        run = args.suite

        if run in ("all", "health"):
            test_health(client, args.base)
        if run in ("all", "auth"):
            test_auth(client, args.base, args.token)
        if run in ("all", "proxy"):
            test_proxy_chat(client, args.base, args.token, args.model)
        if run in ("all", "stream"):
            test_proxy_stream(client, args.base, args.token, args.model)
        if run in ("all", "params"):
            test_proxy_params(client, args.base, args.token, args.model)
        if run in ("all", "embed"):
            test_embeddings(client, args.base, args.token, args.embed_model)
        if run in ("all", "logs"):
            test_logs(client, args.base)

    # ── Summary ──
    total = passed + failed + skipped
    print(f"\n{'─'*50}")
    print(f"{BOLD}测试结果{RESET}  通过 {GREEN}{passed}{RESET}  失败 {RED}{failed}{RESET}  跳过 {YELLOW}{skipped}{RESET}  共 {total} 项")
    if failed == 0:
        print(f"{GREEN}{BOLD}✓ 全部通过{RESET}")
    else:
        print(f"{RED}{BOLD}✗ 有 {failed} 项失败{RESET}")
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
