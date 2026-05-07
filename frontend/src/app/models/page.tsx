"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@tremor/react";
import { AuthExpiredError, fetchAPI, getAuthToken, setAuthToken } from "@/lib/api";

interface ProviderKeyRow {
  provider: string;
  enabled: boolean;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      title="Copy full model name"
      className={`text-xs px-2 py-0.5 rounded transition-colors ${copied ? "text-green-600 bg-green-50" : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"}`}
    >
      {copied ? "✓" : "Copy"}
    </button>
  );
}

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
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40">
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
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-lg text-gray-600 hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            type="button"
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

interface ModelItem {
  id: string;
  provider: string;
  model_id: string;
  display_name: string | null;
  owned_by: string | null;
  raw_created: number | null;
  enabled: boolean;
  synced_at: string;
}

interface TestModelResult {
  ok: boolean;
  latency_ms: number;
  message: string;
  response_preview: string | null;
}

export default function ModelsPage() {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeProvider, setActiveProvider] = useState<string>("all");
  const [enabledFilter, setEnabledFilter] = useState<"all" | "enabled" | "disabled">("all");

  const [addOpen, setAddOpen] = useState(false);
  const [providerOptions, setProviderOptions] = useState<string[]>([]);
  const [addProvider, setAddProvider] = useState("");
  const [addModelName, setAddModelName] = useState("");
  const [addSlug, setAddSlug] = useState("");
  const [addSaving, setAddSaving] = useState(false);
  const [addError, setAddError] = useState("");
  const [savingModelId, setSavingModelId] = useState<string | null>(null);
  const [testingModelId, setTestingModelId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestModelResult>>({});
  const [showReAuth, setShowReAuth] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);

  const requireAuth = useCallback((action: () => void) => {
    setPendingAction(() => action);
    setShowReAuth(true);
  }, []);

  const handleReAuthSuccess = () => {
    setShowReAuth(false);
    const action = pendingAction;
    setPendingAction(null);
    if (action) action();
  };

  const loadModels = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (enabledFilter === "enabled") params.set("enabled", "true");
      if (enabledFilter === "disabled") params.set("enabled", "false");
      const query = params.toString();
      const data = await fetchAPI<ModelItem[]>(`/models${query ? `?${query}` : ""}`);
      setModels(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [enabledFilter]);

  useEffect(() => { loadModels(); }, [loadModels]);
  useEffect(() => { setActiveProvider("all"); }, [enabledFilter]);

  const loadProviderOptions = useCallback(async () => {
    try {
      const keys = await fetchAPI<ProviderKeyRow[]>("/keys");
      const names = Array.from(
        new Set(keys.filter((k) => k.enabled).map((k) => k.provider)),
      ).sort();
      setProviderOptions(names);
      setAddProvider((prev) => (prev && names.includes(prev) ? prev : names[0] || ""));
    } catch (e: any) {
      if (e instanceof AuthExpiredError) {
        requireAuth(() => { void loadProviderOptions(); });
        return;
      }
      setProviderOptions([]);
    }
  }, [requireAuth]);

  useEffect(() => {
    if (addOpen) {
      setAddError("");
      loadProviderOptions();
    }
  }, [addOpen, loadProviderOptions]);

  const providers = useMemo(() => {
    const set = new Set(models.map((m) => m.provider));
    return ["all", ...Array.from(set).sort()];
  }, [models]);

  const filtered = useMemo(() => {
    return models.filter((m) => {
      const matchProvider = activeProvider === "all" || m.provider === activeProvider;
      const matchEnabled =
        enabledFilter === "all" ||
        (enabledFilter === "enabled" && m.enabled) ||
        (enabledFilter === "disabled" && !m.enabled);
      const q = search.toLowerCase();
      const fullName = `${m.provider}/${m.model_id}`;
      const matchSearch = !q || fullName.toLowerCase().includes(q);
      return matchProvider && matchEnabled && matchSearch;
    });
  }, [models, activeProvider, enabledFilter, search]);

  const handleAddModel = async () => {
    setAddError("");
    if (!addProvider.trim()) {
      setAddError("请选择 Provider");
      return;
    }
    if (!addSlug.trim()) {
      setAddError("请输入 Slug（上游 model id）");
      return;
    }
    setAddSaving(true);
    try {
      await fetchAPI("/models/manual", {
        method: "POST",
        body: JSON.stringify({
          provider: addProvider.trim(),
          model_name: addModelName.trim(),
          slug: addSlug.trim(),
        }),
      });
      setAddOpen(false);
      setAddModelName("");
      setAddSlug("");
      await loadModels();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) {
        requireAuth(() => { void handleAddModel(); });
      } else {
        setAddError(e.message || "添加失败");
      }
    } finally {
      setAddSaving(false);
    }
  };

  const handleAddClick = () => {
    if (!getAuthToken()) {
      requireAuth(() => setAddOpen(true));
      return;
    }
    setAddOpen(true);
  };

  const toggleModelEnabled = async (model: ModelItem) => {
    const nextEnabled = !model.enabled;
    setSavingModelId(model.id);
    setModels((prev) => prev.map((m) => (m.id === model.id ? { ...m, enabled: nextEnabled } : m)));
    try {
      const updated = await fetchAPI<ModelItem>(`/models/${model.id}`, {
        method: "PUT",
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      setModels((prev) => prev.map((m) => (m.id === model.id ? updated : m)));
    } catch (e: any) {
      setModels((prev) => prev.map((m) => (m.id === model.id ? model : m)));
      if (e instanceof AuthExpiredError) {
        requireAuth(() => {
          setModels((prev) => prev.map((m) => (m.id === model.id ? model : m)));
          void toggleModelEnabled(model);
        });
      } else {
        alert(e.message || "保存失败");
      }
    } finally {
      setSavingModelId(null);
    }
  };

  const testModel = async (model: ModelItem) => {
    setTestingModelId(model.id);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[model.id];
      return next;
    });
    try {
      const result = await fetchAPI<TestModelResult>(`/models/${model.id}/test`, {
        method: "POST",
      });
      setTestResults((prev) => ({ ...prev, [model.id]: result }));
    } catch (e: any) {
      if (e instanceof AuthExpiredError) {
        requireAuth(() => { void testModel(model); });
      } else {
        setTestResults((prev) => ({
          ...prev,
          [model.id]: {
            ok: false,
            latency_ms: 0,
            message: e.message || "测试失败",
            response_preview: null,
          },
        }));
      }
    } finally {
      setTestingModelId(null);
    }
  };

  const grouped = useMemo(() => {
    const map = new Map<string, ModelItem[]>();
    for (const m of filtered) {
      if (!map.has(m.provider)) map.set(m.provider, []);
      map.get(m.provider)!.push(m);
    }
    return map;
  }, [filtered]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Models</h1>
          <p className="text-sm text-gray-500 mt-1">
            {models.filter((m) => m.enabled).length} enabled / {models.length} models synced across {providers.length - 1} provider{providers.length - 1 !== 1 ? "s" : ""}.
            Use <span className="font-mono text-xs bg-gray-100 px-1 rounded">Get Models</span> on the{" "}
            <a href="/providers/" className="text-blue-600 hover:underline">Providers</a> page to sync.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleAddClick}
            className="px-3 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 font-medium"
          >
            Add model
          </button>
          <button
            type="button"
            onClick={loadModels}
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {addOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-model-title"
          onClick={() => !addSaving && setAddOpen(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl max-w-md w-full border border-gray-200 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="add-model-title" className="text-lg font-semibold text-gray-900">
              Add model
            </h2>
            <p className="text-xs text-gray-500 mt-1">
              Slug 为上游 API 使用的 model id（例如 <code className="bg-gray-100 px-1 rounded">BAAI/bge-large-en-v1.5</code>
              ）。列表中会显示为 <code className="bg-gray-100 px-1 rounded">provider/slug</code>。
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Provider</label>
                <select
                  value={addProvider}
                  onChange={(e) => setAddProvider(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {providerOptions.length === 0 ? (
                    <option value="">（暂无已启用的 Provider，请先在 Providers 添加密钥）</option>
                  ) : (
                    providerOptions.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))
                  )}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Model name（可选）</label>
                <input
                  type="text"
                  value={addModelName}
                  onChange={(e) => setAddModelName(e.target.value)}
                  placeholder="展示名称，不填则用 Slug"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Slug</label>
                <input
                  type="text"
                  value={addSlug}
                  onChange={(e) => setAddSlug(e.target.value)}
                  placeholder="e.g. BAAI/bge-large-en-v1.5"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              {addError && (
                <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{addError}</p>
              )}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={addSaving}
                onClick={() => setAddOpen(false)}
                className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={addSaving || !addProvider || providerOptions.length === 0}
                onClick={handleAddModel}
                className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {addSaving ? "Adding…" : "Add"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search models…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-56"
        />
        <div className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5">
          {[
            ["all", "All"],
            ["enabled", "Enabled"],
            ["disabled", "Disabled"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setEnabledFilter(value as "all" | "enabled" | "disabled")}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                enabledFilter === value
                  ? "bg-gray-900 text-white"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex gap-1 flex-wrap">
          {providers.map((p) => (
            <button
              key={p}
              onClick={() => setActiveProvider(p)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                activeProvider === p
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {p === "all" ? "All" : p}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="py-20 text-center text-gray-400 text-sm">Loading…</div>
      ) : models.length === 0 ? (
        <Card className="p-12 text-center">
          <p className="text-gray-500 text-sm">No models synced yet.</p>
          <p className="text-gray-400 text-xs mt-1">
            Go to{" "}
            <a href="/providers/" className="text-blue-600 hover:underline">Providers</a>
            {" "}and click <strong>Get Models</strong> on a configured provider.
          </p>
        </Card>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-gray-400 text-sm">No models match your filter.</div>
      ) : (
        <div className="space-y-4">
          {Array.from(grouped.entries()).map(([provider, items]) => (
            <Card key={provider} className="p-0 overflow-hidden">
              <div className="px-5 py-3 bg-gray-50 border-b flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-semibold bg-indigo-50 text-indigo-700">
                    {provider}
                  </span>
                  <span className="text-xs text-gray-400">
                    {items.filter((m) => m.enabled).length} enabled / {items.length} models
                  </span>
                </div>
                <span className="text-xs text-gray-400">
                  Synced {new Date(items[0].synced_at).toLocaleString()}
                </span>
              </div>
              <div className="divide-y divide-gray-50">
                {items.map((m) => {
                  const fullName = `${m.provider}/${m.model_id}`;
                  const testResult = testResults[m.id];
                  const testLabel = testResult
                    ? testResult.ok
                      ? `OK ${testResult.latency_ms}ms${testResult.response_preview ? ` · ${testResult.response_preview}` : ""}`
                      : `Failed ${testResult.latency_ms}ms · ${testResult.message}`
                    : "";
                  return (
                  <div
                    key={m.id}
                    className={`px-5 py-2.5 flex items-center justify-between hover:bg-gray-50 ${
                      m.enabled ? "" : "opacity-55"
                    }`}
                  >
                    <div className="min-w-0">
                      <span className="font-mono text-sm text-gray-800">{fullName}</span>
                      <span
                        className={`ml-2 inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          m.enabled ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {m.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
                      {testResult && (
                        <span
                          title={testLabel}
                          className={`max-w-[260px] truncate text-xs ${
                            testResult.ok ? "text-green-600" : "text-red-500"
                          }`}
                        >
                          {testLabel}
                        </span>
                      )}
                      <button
                        type="button"
                        disabled={testingModelId === m.id}
                        onClick={() => testModel(m)}
                        className="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors disabled:opacity-50"
                      >
                        {testingModelId === m.id ? "Testing…" : "Test"}
                      </button>
                      <button
                        type="button"
                        disabled={savingModelId === m.id}
                        onClick={() => toggleModelEnabled(m)}
                        className={`text-xs px-2 py-0.5 rounded transition-colors disabled:opacity-50 ${
                          m.enabled
                            ? "text-amber-700 bg-amber-50 hover:bg-amber-100"
                            : "text-green-700 bg-green-50 hover:bg-green-100"
                        }`}
                      >
                        {savingModelId === m.id ? "Saving…" : m.enabled ? "Disable" : "Enable"}
                      </button>
                      <CopyButton text={fullName} />
                    </div>
                  </div>
                  );
                })}
              </div>
            </Card>
          ))}
        </div>
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
