"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@tremor/react";
import { fetchAPI } from "@/lib/api";

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
        <button
          onClick={loadModels}
          className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
        >
          ↻ Refresh
        </button>
      </div>

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
