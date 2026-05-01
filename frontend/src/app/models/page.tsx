"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@tremor/react";
import { fetchAPI } from "@/lib/api";

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

interface ModelItem {
  id: string;
  provider: string;
  model_id: string;
  display_name: string | null;
  owned_by: string | null;
  raw_created: number | null;
  synced_at: string;
}

export default function ModelsPage() {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeProvider, setActiveProvider] = useState<string>("all");

  const [addOpen, setAddOpen] = useState(false);
  const [providerOptions, setProviderOptions] = useState<string[]>([]);
  const [addProvider, setAddProvider] = useState("");
  const [addModelName, setAddModelName] = useState("");
  const [addSlug, setAddSlug] = useState("");
  const [addSaving, setAddSaving] = useState(false);
  const [addError, setAddError] = useState("");

  const loadModels = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchAPI<ModelItem[]>("/models");
      setModels(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadModels(); }, [loadModels]);

  const loadProviderOptions = useCallback(async () => {
    try {
      const keys = await fetchAPI<ProviderKeyRow[]>("/keys");
      const names = Array.from(
        new Set(keys.filter((k) => k.enabled).map((k) => k.provider)),
      ).sort();
      setProviderOptions(names);
      setAddProvider((prev) => (prev && names.includes(prev) ? prev : names[0] || ""));
    } catch {
      setProviderOptions([]);
    }
  }, []);

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
      const q = search.toLowerCase();
      const fullName = `${m.provider}/${m.model_id}`;
      const matchSearch = !q || fullName.toLowerCase().includes(q);
      return matchProvider && matchSearch;
    });
  }, [models, activeProvider, search]);

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
      setAddError(e.message || "添加失败");
    } finally {
      setAddSaving(false);
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
            {models.length} models synced across {providers.length - 1} provider{providers.length - 1 !== 1 ? "s" : ""}.
            Use <span className="font-mono text-xs bg-gray-100 px-1 rounded">Get Models</span> on the{" "}
            <a href="/providers/" className="text-blue-600 hover:underline">Providers</a> page to sync.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setAddOpen(true)}
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
                  <span className="text-xs text-gray-400">{items.length} models</span>
                </div>
                <span className="text-xs text-gray-400">
                  Synced {new Date(items[0].synced_at).toLocaleString()}
                </span>
              </div>
              <div className="divide-y divide-gray-50">
                {items.map((m) => {
                  const fullName = `${m.provider}/${m.model_id}`;
                  return (
                  <div
                    key={m.id}
                    className="px-5 py-2.5 flex items-center justify-between hover:bg-gray-50"
                  >
                    <span className="font-mono text-sm text-gray-800">{fullName}</span>
                    <CopyButton text={fullName} />
                  </div>
                  );
                })}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
