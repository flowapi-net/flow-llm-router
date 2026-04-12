"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthExpiredError, fetchAPI, getAuthToken } from "@/lib/api";

/* ── Types ── */
interface CallerToken {
  id: string; name: string; token_prefix: string;
  enabled: boolean; created_at: string; last_used_at: string | null;
}
interface ServerConfig { host: string; port: number; ip_mode: string; allowed_ips: string[]; }

/* ── Hooks ── */
function useProxyBase() {
  const [base, setBase] = useState("http://127.0.0.1:7798");
  useEffect(() => { if (typeof window !== "undefined") setBase(window.location.origin); }, []);
  return base;
}

/* ── Sub-components ── */
function CopyButton({ text, className = "" }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className={`text-xs px-2 py-1 rounded transition-colors ${copied ? "bg-green-600 text-white" : "bg-gray-700 text-gray-300 hover:bg-gray-600"} ${className}`}
    >
      {copied ? "✓ Copied" : "Copy"}
    </button>
  );
}

function CodeBlock({ code, lang = "" }: { code: string; lang?: string }) {
  return (
    <div className="relative group">
      <pre className="bg-gray-950 text-gray-100 text-xs rounded-lg p-4 overflow-x-auto leading-relaxed font-mono">{code}</pre>
      <div className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

function InlineCode({ children }: { children: React.ReactNode }) {
  return <code className="bg-gray-100 text-indigo-700 px-1.5 py-0.5 rounded text-xs font-mono">{children}</code>;
}

function StepBadge({ n }: { n: number }) {
  return (
    <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold shrink-0">{n}</span>
  );
}

/* ── ReAuth Dialog ── */
function ReAuthDialog({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const [pw, setPw] = useState(""); const [err, setErr] = useState(""); const [loading, setLoading] = useState(false);
  const submit = async () => {
    setLoading(true); setErr("");
    try {
      const { setAuthToken } = await import("@/lib/api");
      const r = await fetchAPI<{ token: string }>("/auth/verify", { method: "POST", body: JSON.stringify({ password: pw }) });
      setAuthToken(r.token); onSuccess();
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-sm space-y-4">
        <h3 className="text-lg font-semibold">Enter Master Password</h3>
        <input type="password" autoFocus placeholder="Master password" value={pw}
          onChange={e => setPw(e.target.value)} onKeyDown={e => e.key === "Enter" && submit()}
          className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        {err && <p className="text-sm text-red-600">{err}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="px-4 py-2 text-sm rounded-lg text-gray-600 hover:bg-gray-100">Cancel</button>
          <button onClick={submit} disabled={loading} className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50">
            {loading ? "..." : "Unlock"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Language tabs ── */
const MODES = ["普通", "流式 (Stream)"] as const;
type Mode = typeof MODES[number];
const LANGS = ["Python", "Node.js", "cURL"] as const;
type Lang = typeof LANGS[number];

function makeSnippets(base: string, token: string): Record<Mode, Record<Lang, string>> {
  const tok = token || "fgt_xxxxxxxxxxxxxxxx";
  return {
    "普通": {
      Python:
`from openai import OpenAI

client = OpenAI(
    base_url="${base}/v1",  # 👈 只改这一行
    api_key="${tok}",
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)`,

      "Node.js":
`import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${base}/v1",  // 👈 只改这一行
  apiKey: "${tok}",
});

const response = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);`,

      cURL:
`curl ${base}/v1/chat/completions \\
  -H "Authorization: Bearer ${tok}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
    },

    "流式 (Stream)": {
      Python:
`from openai import OpenAI

client = OpenAI(
    base_url="${base}/v1",
    api_key="${tok}",
)

# stream=True 即可开启流式输出，FlowGate 直接透传 SSE
with client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
) as stream:
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        print(delta, end="", flush=True)
print()  # 换行`,

      "Node.js":
`import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${base}/v1",
  apiKey: "${tok}",
});

const stream = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Hello!" }],
  stream: true,  // 开启流式
});

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}`,

      cURL:
`# -N 禁用缓冲，实时看到 SSE 输出
curl -N ${base}/v1/chat/completions \\
  -H "Authorization: Bearer ${tok}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'

# 每行格式: data: {"choices":[{"delta":{"content":"..."}}]}
# 结束标记: data: [DONE]`,
    },
  };
}

/* ── Main ── */
export default function IntegratePage() {
  const base = useProxyBase();
  const [lang, setLang] = useState<Lang>("Python");
  const [mode, setMode] = useState<Mode>("普通");
  const [tokens, setTokens] = useState<CallerToken[]>([]);
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [newTokenName, setNewTokenName] = useState("");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [showReAuth, setShowReAuth] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const [creating, setCreating] = useState(false);
  const [tokenErr, setTokenErr] = useState("");
  const [authed, setAuthed] = useState(false);

  const exampleToken = tokens.find(t => t.enabled)?.token_prefix
    ? tokens.find(t => t.enabled)!.token_prefix + "…"
    : "fgt_xxxxxxxxxxxxxxxx";
  const allSnippets = makeSnippets(base, exampleToken);

  const loadTokens = useCallback(async () => {
    try { setTokens(await fetchAPI<CallerToken[]>("/caller-tokens")); } catch { }
  }, []);
  const loadConfig = useCallback(async () => {
    try { setConfig(await fetchAPI<ServerConfig>("/server-config")); } catch { }
  }, []);

  useEffect(() => {
    loadConfig();
    const check = async () => {
      const token = getAuthToken();
      if (!token) { setShowReAuth(true); return; }
      try { await fetchAPI("/caller-tokens"); setAuthed(true); loadTokens(); }
      catch (e: any) { if (e instanceof AuthExpiredError) setShowReAuth(true); else { setAuthed(true); loadTokens(); } }
    };
    check();
  }, [loadTokens, loadConfig]);

  const requireAuth = (action: () => void) => { setPendingAction(() => action); setShowReAuth(true); };
  const handleReAuthSuccess = () => {
    setShowReAuth(false); setAuthed(true); loadTokens();
    if (pendingAction) { pendingAction(); setPendingAction(null); }
  };

  const handleCreate = async () => {
    if (!newTokenName.trim()) { setTokenErr("请输入 Token 名称"); return; }
    if (!authed) { requireAuth(handleCreate); return; }
    setTokenErr(""); setCreating(true);
    try {
      const r = await fetchAPI<{ token: string; id: string; name: string }>("/caller-tokens", {
        method: "POST", body: JSON.stringify({ name: newTokenName.trim() }),
      });
      setNewToken(r.token); setNewTokenName(""); loadTokens();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) requireAuth(handleCreate);
      else setTokenErr(e.message);
    } finally { setCreating(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("删除后使用该 Token 的服务将立即失去访问权限，确认删除？")) return;
    try { await fetchAPI(`/caller-tokens/${id}`, { method: "DELETE" }); loadTokens(); }
    catch (e: any) { if (e instanceof AuthExpiredError) requireAuth(() => handleDelete(id)); else alert(e.message); }
  };

  const handleToggle = async (t: CallerToken) => {
    try { await fetchAPI(`/caller-tokens/${t.id}`, { method: "PUT", body: JSON.stringify({ enabled: !t.enabled }) }); loadTokens(); }
    catch (e: any) { if (e instanceof AuthExpiredError) requireAuth(() => handleToggle(t)); else alert(e.message); }
  };

  return (
    <div className="max-w-3xl space-y-10 pb-16">

      {/* ── Hero ── */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">接入指南</h1>
        <p className="mt-2 text-sm text-gray-500 leading-relaxed">
          FlowGate 完全兼容 OpenAI 接口协议。你的代码<strong className="text-gray-700">只需修改 base_url</strong>，
          无需改动任何业务逻辑——FlowGate 在后端用 LiteLLM 自动路由到对应 Provider。
        </p>
      </div>

      {/* ── How it works ── */}
      <section className="bg-indigo-50 border border-indigo-100 rounded-xl p-5 space-y-3">
        <h2 className="text-sm font-semibold text-indigo-900">工作原理</h2>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 text-xs text-indigo-800">
          <div className="flex items-center gap-2 bg-white border border-indigo-200 rounded-lg px-3 py-2">
            <span className="text-base">🤖</span>
            <div>
              <p className="font-semibold">你的代码</p>
              <p className="text-indigo-500">OpenAI SDK / 任意 HTTP 客户端</p>
            </div>
          </div>
          <span className="text-indigo-400 font-mono text-lg sm:mx-1">→</span>
          <div className="flex items-center gap-2 bg-indigo-600 rounded-lg px-3 py-2 text-white">
            <span className="text-base">⚡</span>
            <div>
              <p className="font-semibold">FlowGate</p>
              <p className="text-indigo-200">鉴权 · 日志 · 路由</p>
            </div>
          </div>
          <span className="text-indigo-400 font-mono text-lg sm:mx-1">→</span>
          <div className="flex items-center gap-2 bg-white border border-indigo-200 rounded-lg px-3 py-2">
            <span className="text-base">🌐</span>
            <div>
              <p className="font-semibold">LiteLLM</p>
              <p className="text-indigo-500">OpenAI / Claude / Gemini / 本地模型…</p>
            </div>
          </div>
        </div>
        <p className="text-xs text-indigo-700">
          你传入的 <InlineCode>api_key</InlineCode> 是 <strong>FlowGate Access Token</strong>（下面创建），
          真实的 Provider API Key 保存在 Vault 里，你的代码永远不会接触到它。
        </p>
      </section>

      {/* ── Quick Start ── */}
      <section className="space-y-5">
        <h2 className="text-base font-semibold text-gray-900 border-b pb-2">快速开始</h2>

        {/* Step 1 */}
        <div className="space-y-2">
          <div className="flex items-center gap-2.5">
            <StepBadge n={1} />
            <h3 className="text-sm font-semibold text-gray-800">在 Providers 页添加你的 Provider API Key</h3>
          </div>
          <p className="ml-8.5 text-xs text-gray-500">
            前往 <a href="/providers" className="text-indigo-600 hover:underline">Providers</a> 页面，
            填写 Provider 名称（如 <InlineCode>openai</InlineCode>、<InlineCode>siliconflow</InlineCode>）、
            Base URL（可选）和 API Key。FlowGate 会加密保存，代理时自动取用。
          </p>
        </div>

        {/* Step 2 */}
        <div className="space-y-2">
          <div className="flex items-center gap-2.5">
            <StepBadge n={2} />
            <h3 className="text-sm font-semibold text-gray-800">生成一个 Access Token（下方操作）</h3>
          </div>
          <p className="ml-8.5 text-xs text-gray-500">
            Access Token 用于对外鉴权。未创建任何 Token 时代理完全开放；
            一旦创建，所有请求必须携带有效 Token，建议生产环境务必创建。
          </p>
        </div>

        {/* Step 3 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2.5">
            <StepBadge n={3} />
            <h3 className="text-sm font-semibold text-gray-800">把 base_url 改成 FlowGate 地址，其他代码不动</h3>
          </div>
          <div className="ml-8.5 space-y-3">
            {/* Base URL pill */}
            <div className="inline-flex items-center gap-3 bg-gray-950 rounded-lg px-4 py-2.5">
              <span className="text-xs text-gray-400 font-medium uppercase tracking-wide">Base URL</span>
              <code className="font-mono text-sm text-indigo-300">{base}/v1</code>
              <CopyButton text={`${base}/v1`} className="shrink-0" />
            </div>
            {/* Mode + Lang tabs */}
            <div className="space-y-2">
              {/* Mode selector */}
              <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
                {MODES.map(m => (
                  <button key={m} onClick={() => setMode(m)}
                    className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${mode === m ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
                    {m}
                  </button>
                ))}
              </div>
              {/* Lang selector */}
              <div className="flex gap-1.5">
                {LANGS.map(l => (
                  <button key={l} onClick={() => setLang(l)}
                    className={`px-3 py-1.5 text-xs rounded-md font-medium transition-colors ${lang === l ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>
            {mode === "流式 (Stream)" && (
              <div className="flex items-start gap-2 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2 text-xs text-blue-700">
                <span className="shrink-0 mt-0.5">ℹ️</span>
                <span>FlowGate 直接透传 Server-Sent Events（SSE），流式输出与直连 Provider 行为完全一致，无额外延迟。</span>
              </div>
            )}
            <CodeBlock code={allSnippets[mode][lang]} />
          </div>
        </div>
      </section>

      {/* ── Endpoints ── */}
      <section className="space-y-3">
        <h2 className="text-base font-semibold text-gray-900 border-b pb-2">支持的接口</h2>
        <div className="rounded-xl border overflow-hidden text-xs">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr className="text-left text-gray-500 uppercase text-xs tracking-wide">
                <th className="px-4 py-2.5 font-medium">Method</th>
                <th className="px-4 py-2.5 font-medium">Endpoint</th>
                <th className="px-4 py-2.5 font-medium">说明</th>
              </tr>
            </thead>
            <tbody className="divide-y bg-white">
              {([
                ["POST", "/v1/chat/completions", "Chat 对话，支持 streaming / tools / vision / o1 系列参数"],
                ["POST", "/v1/embeddings",        "文本向量化（传 base_url 给 LiteLLM 自动路由）"],
                ["GET",  "/v1/models",            "列出已同步的模型（先在 Providers 页 Get Models）"],
              ] as [string, string, string][]).map(([m, p, d]) => (
                <tr key={p} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span className={`font-mono font-bold ${m === "POST" ? "text-green-700" : "text-blue-700"}`}>{m}</span>
                  </td>
                  <td className="px-4 py-3 font-mono text-gray-800">{p}</td>
                  <td className="px-4 py-3 text-gray-500">{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-400">
          所有请求参数与 OpenAI 官方 API 完全兼容，由 LiteLLM 负责翻译并转发至对应 Provider。
        </p>
      </section>

      {/* ── Access Tokens ── */}
      <section className="space-y-4">
        <div className="border-b pb-2 flex items-end justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Access Tokens</h2>
            <p className="text-xs text-gray-500 mt-0.5">为每个服务 / Agent 生成独立 Token，可单独撤销。</p>
          </div>
          {tokens.length > 0 && (
            <span className="text-xs text-gray-400">{tokens.filter(t => t.enabled).length} / {tokens.length} 启用</span>
          )}
        </div>

        {/* Newly created — show once */}
        {newToken && (
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-2.5">
            <div className="flex items-center gap-2">
              <span className="text-green-700 font-semibold text-sm">✓ Token 已创建</span>
              <span className="text-xs text-green-600 bg-green-100 px-2 py-0.5 rounded-full">仅显示一次，请立即复制</span>
            </div>
            <div className="flex items-center gap-2">
              <code className="font-mono text-sm text-green-900 bg-white border border-green-200 px-3 py-2 rounded-lg flex-1 break-all select-all">{newToken}</code>
              <CopyButton text={newToken} className="bg-green-600 text-white hover:bg-green-700 shrink-0 !text-sm !px-3 !py-2" />
            </div>
            <button onClick={() => setNewToken(null)} className="text-xs text-green-600 hover:underline">关闭</button>
          </div>
        )}

        {/* Create */}
        <div className="flex gap-2 items-start">
          <div className="flex-1">
            <input type="text" placeholder="Token 名称，e.g.  my-agent  /  jupyter-nb  /  prod-server"
              value={newTokenName} onChange={e => { setNewTokenName(e.target.value); setTokenErr(""); }}
              onKeyDown={e => e.key === "Enter" && handleCreate()}
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            {tokenErr && <p className="text-xs text-red-500 mt-1">{tokenErr}</p>}
          </div>
          <button onClick={handleCreate} disabled={creating}
            className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 shrink-0 font-medium">
            {creating ? "生成中…" : "+ 生成 Token"}
          </button>
        </div>

        {/* Token list */}
        {tokens.length > 0 ? (
          <div className="rounded-xl border overflow-hidden text-xs">
            <table className="w-full">
              <thead className="bg-gray-50 border-b">
                <tr className="text-left text-gray-500 uppercase tracking-wide">
                  <th className="px-4 py-2.5 font-medium">名称</th>
                  <th className="px-4 py-2.5 font-medium">Token 前缀</th>
                  <th className="px-4 py-2.5 font-medium">最后使用</th>
                  <th className="px-4 py-2.5 font-medium">状态</th>
                  <th className="px-4 py-2.5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y bg-white">
                {tokens.map(t => (
                  <tr key={t.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-800 font-medium">{t.name}</td>
                    <td className="px-4 py-3 font-mono text-gray-500">{t.token_prefix}…</td>
                    <td className="px-4 py-3 text-gray-400">
                      {t.last_used_at ? new Date(t.last_used_at).toLocaleString("zh-CN") : "从未使用"}
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => handleToggle(t)}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium transition-colors
                          ${t.enabled
                            ? "bg-green-100 text-green-700 hover:bg-green-200"
                            : "bg-gray-100 text-gray-500 hover:bg-gray-200"}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${t.enabled ? "bg-green-500" : "bg-gray-400"}`} />
                        {t.enabled ? "启用" : "禁用"}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => handleDelete(t.id)} className="text-red-400 hover:text-red-600 font-medium">删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !newToken && (
            <div className="rounded-xl border border-dashed border-gray-200 py-8 text-center">
              <p className="text-sm text-gray-400">暂无 Access Token</p>
              <p className="text-xs text-gray-400 mt-1">当前代理处于<strong>开放模式</strong>，任何请求均可通过。建议生产环境创建 Token。</p>
            </div>
          )
        )}
      </section>

      {/* ── IP Control ── */}
      <section className="space-y-3">
        <h2 className="text-base font-semibold text-gray-900 border-b pb-2">IP 访问控制</h2>
        {config ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
                ${config.ip_mode === "local_only" ? "bg-blue-100 text-blue-700" :
                  config.ip_mode === "whitelist"  ? "bg-yellow-100 text-yellow-700"
                                                  : "bg-gray-100 text-gray-500"}`}>
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                {config.ip_mode === "local_only" ? "仅本机 (127.0.0.1)" :
                 config.ip_mode === "whitelist"  ? "IP 白名单" : "完全开放"}
              </span>
              <span className="text-xs text-gray-400 font-mono">{config.host}:{config.port}</span>
            </div>
            {config.ip_mode === "whitelist" && config.allowed_ips.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {config.allowed_ips.map(ip => (
                  <span key={ip} className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">{ip}</span>
                ))}
              </div>
            )}
            <details className="text-xs">
              <summary className="cursor-pointer text-gray-500 hover:text-gray-700 select-none">
                如何修改 IP 白名单？
              </summary>
              <div className="mt-2 space-y-1.5">
                <p className="text-gray-500">编辑 <InlineCode>flowgate.yaml</InlineCode> 后重启服务：</p>
                <CodeBlock code={`security:
  ip_whitelist:
    enabled: true
    mode: whitelist       # local_only | whitelist | open
    allowed_ips:
      - "127.0.0.1"
      - "192.168.1.0/24"  # 支持 CIDR
      - "10.0.0.5"`} />
              </div>
            </details>
          </div>
        ) : (
          <p className="text-xs text-gray-400">加载中…</p>
        )}
      </section>

      {showReAuth && (
        <ReAuthDialog
          onSuccess={handleReAuthSuccess}
          onCancel={() => { setShowReAuth(false); setPendingAction(null); }}
        />
      )}
    </div>
  );
}
