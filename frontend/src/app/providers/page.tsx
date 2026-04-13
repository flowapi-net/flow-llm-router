"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text } from "@tremor/react";
import { AuthExpiredError, fetchAPI, getAuthToken } from "@/lib/api";

interface ProviderKeyInfo {
  id: string;
  provider: string;
  key_name: string;
  key_masked: string;
  extra_config: string | null;
  enabled: boolean;
  created_at: string;
}

/* ── Password re-auth dialog ── */
function ReAuthDialog({
  onSuccess,
  onCancel,
}: {
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setError("");
    if (!password) return;
    setLoading(true);
    try {
      const { setAuthToken } = await import("@/lib/api");
      const res = await fetchAPI<{ token: string }>("/auth/verify", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setAuthToken(res.token);
      onSuccess();
    } catch (e: any) {
      setError(e.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-sm space-y-4">
        <h3 className="text-lg font-semibold">Enter Master Password</h3>
        <input
          type="password"
          placeholder="Master password"
          value={password}
          autoFocus
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="px-4 py-2 text-sm rounded-lg text-gray-600 hover:bg-gray-100">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "..." : "Unlock"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Add Key Dialog ── */
function AddKeyDialog({
  onSuccess,
  onCancel,
  onAuthExpired,
  existingProviders = [],
}: {
  onSuccess: () => void;
  onCancel: () => void;
  onAuthExpired?: () => void;
  existingProviders?: string[];
}) {
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const providerNorm = provider.trim().toLowerCase().replace(/\s+/g, "-");

  const handleSubmit = async () => {
    setError("");
    if (!providerNorm) { setError("Provider name is required"); return; }
    if (existingProviders.includes(providerNorm)) {
      setError(`Provider "${providerNorm}" already exists. Please use a different name.`);
      return;
    }
    if (!apiKey.trim()) { setError("API Key is required"); return; }
    setLoading(true);
    try {
      await fetchAPI("/keys", {
        method: "POST",
        body: JSON.stringify({
          provider: providerNorm,
          key_name: `${providerNorm}-default`,
          api_key: apiKey.trim(),
          extra_config: baseUrl.trim() ? JSON.stringify({ base_url: baseUrl.trim() }) : null,
        }),
      });
      onSuccess();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) onAuthExpired?.();
      else setError(e.message || "Failed to add key");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-md space-y-4">
        <h3 className="text-lg font-semibold">Add Provider</h3>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-gray-700">Provider Name <span className="text-red-500">*</span></label>
            <input
              type="text"
              placeholder="e.g. openai / siliconflow / deepseek"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              autoFocus
              className="w-full mt-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">
              Base URL <span className="text-gray-400 font-normal text-xs">（可选，自定义 API 地址）</span>
            </label>
            <input
              type="text"
              placeholder="https://api.example.com/v1"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full mt-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">API Key <span className="text-red-500">*</span></label>
            <input
              type="password"
              placeholder="sk-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              className="w-full mt-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="px-4 py-2 text-sm rounded-lg text-gray-600 hover:bg-gray-100">Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Saving..." : "Add Provider"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Integration Guide ── */

function useProxyBase() {
  const [base, setBase] = useState("http://127.0.0.1:7789");
  useEffect(() => {
    if (typeof window !== "undefined") setBase(window.location.origin);
  }, []);
  return base;
}

function buildSnippets(base: string) {
  const b = `${base}/v1`;
  return {
    curl: `curl ${b}/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
    python: `from openai import OpenAI

client = OpenAI(
    base_url="${b}",
    api_key="any",          # FlowGate 管密钥，这里随便填
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(resp.choices[0].message.content)`,
    js: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${b}",
  apiKey: "any",            // FlowGate 管密钥，这里随便填
  dangerouslyAllowBrowser: true,
});

const resp = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(resp.choices[0].message.content);`,
    langchain: `from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o-mini",
    openai_api_base="${b}",
    openai_api_key="any",
)
print(llm.invoke("Hello!").content)`,
  };
}

type SnippetKey = keyof ReturnType<typeof buildSnippets>;

function IntegrationGuide() {
  const base = useProxyBase();
  const snippets = useMemo(() => buildSnippets(base), [base]);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<SnippetKey>("python");
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(snippets[tab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-xl border border-blue-100 bg-blue-50/60">
      {/* Header row */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left"
      >
        <div className="flex items-center gap-2.5">
          <span className="text-blue-600 text-base">⚡</span>
          <span className="text-sm font-semibold text-blue-800">如何接入 FlowGate 代理</span>
          <span className="font-mono text-xs bg-white border border-blue-200 text-blue-700 px-2 py-0.5 rounded">
            POST {base}/v1/chat/completions
          </span>
        </div>
        <span className="text-blue-400 text-sm">{open ? "▲ 收起" : "▼ 展开"}</span>
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-3">
          <p className="text-xs text-blue-700">
            将你代码中的 <code className="bg-white px-1 py-0.5 rounded border border-blue-200">base_url</code> 改成
            {" "}<code className="bg-white px-1 py-0.5 rounded border border-blue-200">{base}/v1</code>，
            <code className="bg-white px-1 py-0.5 rounded border border-blue-200">api_key</code> 随便填（FlowGate 统一管理密钥）。
            所有请求会自动路由到下方配置的 Provider。
          </p>

          {/* Tab bar */}
          <div className="flex gap-1">
            {(Object.keys(snippets) as SnippetKey[]).map((k) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                  tab === k
                    ? "bg-blue-600 text-white"
                    : "bg-white border border-blue-200 text-blue-700 hover:bg-blue-100"
                }`}
              >
                {k === "js" ? "Node.js" : k === "langchain" ? "LangChain" : k.charAt(0).toUpperCase() + k.slice(1)}
              </button>
            ))}
          </div>

          {/* Code block */}
          <div className="relative">
            <pre className="bg-gray-900 text-gray-100 text-xs rounded-lg p-4 overflow-x-auto leading-relaxed">
              {snippets[tab]}
            </pre>
            <button
              onClick={copy}
              className="absolute top-2.5 right-2.5 text-xs px-2 py-1 rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
            >
              {copied ? "✓ Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main Page ── */

export default function ProvidersPage() {
  const [keys, setKeys] = useState<ProviderKeyInfo[]>([]);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showReAuth, setShowReAuth] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const [syncingProvider, setSyncingProvider] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState<{ provider: string; text: string; ok: boolean } | null>(null);
  const [authed, setAuthed] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      const data = await fetchAPI<ProviderKeyInfo[]>("/keys");
      setKeys(data);
    } catch { /* ignore */ }
  }, []);

  // On mount: verify token is valid; if not, show unlock immediately
  useEffect(() => {
    const check = async () => {
      const token = getAuthToken();
      if (!token) {
        setShowReAuth(true);
        return;
      }
      // Probe a protected endpoint to confirm token is still valid
      try {
        await fetchAPI<ProviderKeyInfo[]>("/keys");
        setAuthed(true);
        loadKeys();
      } catch (e: any) {
        if (e instanceof AuthExpiredError) {
          setShowReAuth(true);
        } else {
          // Non-auth error, still let them in
          setAuthed(true);
          loadKeys();
        }
      }
    };
    check();
  }, [loadKeys]);

  const requireAuth = (action: () => void) => {
    setPendingAction(() => action);
    setShowReAuth(true);
  };

  const handleReAuthSuccess = () => {
    setShowReAuth(false);
    setAuthed(true);
    loadKeys();
    if (pendingAction) { pendingAction(); setPendingAction(null); }
  };

  const handleAddClick = () => {
    if (!authed) { requireAuth(() => setShowAddDialog(true)); return; }
    setShowAddDialog(true);
  };

  const handleDelete = async (id: string, provider: string) => {
    if (!confirm(`Delete the key for "${provider}"?`)) return;
    try {
      await fetchAPI(`/keys/${id}`, { method: "DELETE" });
      loadKeys();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) requireAuth(() => handleDelete(id, provider));
      else alert(e.message);
    }
  };

  const handleToggle = async (key: ProviderKeyInfo) => {
    try {
      await fetchAPI(`/keys/${key.id}`, {
        method: "PUT",
        body: JSON.stringify({ enabled: !key.enabled }),
      });
      loadKeys();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) requireAuth(() => handleToggle(key));
      else alert(e.message);
    }
  };

  const handleSyncModels = async (provider: string) => {
    setSyncingProvider(provider);
    setSyncMsg(null);
    try {
      const res = await fetchAPI<{ synced: number; models: string[] }>(
        `/models/sync/${provider}`,
        { method: "POST" },
      );
      setSyncMsg({ provider, text: `✓ Synced ${res.synced} models`, ok: true });
    } catch (e: any) {
      if (e instanceof AuthExpiredError) {
        requireAuth(() => handleSyncModels(provider));
      } else {
        setSyncMsg({ provider, text: e.message || "Sync failed", ok: false });
      }
    } finally {
      setSyncingProvider(null);
    }
  };

  const getBaseUrl = (key: ProviderKeyInfo) => {
    if (!key.extra_config) return null;
    try { return JSON.parse(key.extra_config).base_url || null; } catch { return null; }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Providers</h1>
        <button
          onClick={handleAddClick}
          className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700"
        >
          + Add Provider
        </button>
      </div>

      <IntegrationGuide />

      <Card className="p-0 overflow-hidden">
        {keys.length === 0 ? (
          <div className="py-16 text-center text-gray-400 text-sm">
            No providers configured yet. Click &quot;+ Add Provider&quot; to get started.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr className="text-left text-gray-500 text-xs uppercase tracking-wide">
                <th className="px-5 py-3 font-medium">Provider</th>
                <th className="px-5 py-3 font-medium">Base URL</th>
                <th className="px-5 py-3 font-medium">Key</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {keys.map((k) => {
                const baseUrl = getBaseUrl(k);
                const isSyncing = syncingProvider === k.provider;
                const msg = syncMsg?.provider === k.provider ? syncMsg : null;
                return (
                  <tr key={k.id} className="hover:bg-gray-50">
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-indigo-50 text-indigo-700">
                        {k.provider}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-gray-500 text-xs font-mono">
                      {baseUrl ? (
                        <span title={baseUrl} className="truncate max-w-[200px] block">
                          {baseUrl}
                        </span>
                      ) : (
                        <span className="text-gray-300">default</span>
                      )}
                    </td>
                    <td className="px-5 py-4 font-mono text-gray-400 text-xs">{k.key_masked}</td>
                    <td className="px-5 py-4">
                      <button
                        onClick={() => handleToggle(k)}
                        className={`text-xs font-medium ${k.enabled ? "text-green-600 hover:text-green-800" : "text-gray-400 hover:text-gray-600"}`}
                      >
                        {k.enabled ? "● Enabled" : "○ Disabled"}
                      </button>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center justify-end gap-3">
                        {msg && (
                          <span className={`text-xs ${msg.ok ? "text-green-600" : "text-red-500"}`}>
                            {msg.text}
                          </span>
                        )}
                        <button
                          onClick={() => handleSyncModels(k.provider)}
                          disabled={isSyncing}
                          className="text-xs px-2.5 py-1 rounded border border-blue-300 text-blue-600 hover:bg-blue-50 disabled:opacity-40"
                        >
                          {isSyncing ? "Syncing…" : "Get Models"}
                        </button>
                        <button
                          onClick={() => handleDelete(k.id, k.provider)}
                          className="text-xs text-red-400 hover:text-red-600"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      {showAddDialog && (
        <AddKeyDialog
          onSuccess={() => { setShowAddDialog(false); loadKeys(); }}
          onCancel={() => setShowAddDialog(false)}
          onAuthExpired={() => {
            setShowAddDialog(false);
            requireAuth(() => setShowAddDialog(true));
          }}
          existingProviders={keys.map((k) => k.provider)}
        />
      )}
      {showReAuth && (
        <ReAuthDialog
          onSuccess={handleReAuthSuccess}
          onCancel={() => { setShowReAuth(false); setPendingAction(null); }}
        />
      )}
    </div>
  );
}
