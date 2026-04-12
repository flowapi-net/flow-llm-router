# FlowGate (flow-llm-router)

> 零配置、本地优先的大模型网关与成本审计中枢

FlowGate 为 AI 开发者提供一个开箱即用的本地 LLM 网关，彻底解决 Agent 开发中的 **"Token 焦虑"** 和 **"调试黑盒"** 问题。

## 核心特性

- **无侵入代理** — 完全兼容 OpenAI `/v1/chat/completions` 接口，只需修改 `BASE_URL`
- **多模型翻译** — 通过 LiteLLM 自动对接 100+ 模型（OpenAI / Anthropic / Google / Azure / 本地模型）
- **智能路由** — 基于 Prompt 复杂度自动分发请求到合适的模型，实现无感降本
- **动态技能编排** — 语义匹配最相关的 Top-3 技能注入上下文，解决 "Token 税" 问题
- **本地日志** — 所有请求日志结构化存入本地 SQLite，数据绝对私密
- **可视化面板** — 实时 Token 消耗、成本趋势、日志回放、成本诊断

## 快速开始

```bash
pip install flow-llm-router
flow-router start
```

启动后访问（默认端口 `7798`，可在 `flowgate.yaml` 中修改）：
- **Dashboard**: http://127.0.0.1:7798
- **API Proxy**: http://127.0.0.1:7798/v1/chat/completions

## 接入方式

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:7798/v1",
    api_key="your-api-key",  # 直接传入你的 Provider API Key
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + LiteLLM + SQLModel + ChromaDB |
| 前端 | Next.js + Tremor + shadcn/ui + Tailwind CSS |
| 存储 | SQLite (日志) + ChromaDB (技能向量) |
| 分发 | PyPI (`pip install`) |

## 配置

创建 `flowgate.yaml`：

```yaml
smart_router:
  enabled: true
  tiers:
    SIMPLE: gpt-4o-mini
    MEDIUM: gpt-4o
    COMPLEX: claude-sonnet
    REASONING: o1-preview
```

或通过环境变量：

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

## 文档

详细技术设计文档请参阅 [DESIGN.md](DESIGN.md)。

## License

MIT
