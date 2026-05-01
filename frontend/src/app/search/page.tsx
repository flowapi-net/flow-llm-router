"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@tremor/react";
import { AuthExpiredError, fetchAPI, getAuthToken } from "@/lib/api";

interface SearchProviderInfo {
  id: string;
  provider: string;
  key_name: string;
  key_masked: string;
  base_url: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

interface SearchTestResult {
  ok: boolean;
  latency_ms: number;
  result_count: number;
  sample_title: string | null;
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

function AddSearchKeyDialog({
  onSuccess,
  onCancel,
  onAuthExpired,
}: {
  onSuccess: () => void;
  onCancel: () => void;
  onAuthExpired: () => void;
}) {
  const [keyName, setKeyName] = useState("Tavily");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setError("");
    if (!keyName.trim()) { setError("Name is required"); return; }
    if (!apiKey.trim()) { setError("API key is required"); return; }
    setLoading(true);
    try {
      await fetchAPI("/search/providers", {
        method: "POST",
        body: JSON.stringify({
          provider: "tavily",
          key_name: keyName.trim(),
          api_key: apiKey.trim(),
          base_url: baseUrl.trim() || null,
        }),
      });
      onSuccess();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) onAuthExpired();
      else setError(e.message || "Failed to add search key");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-md space-y-4">
        <h3 className="text-lg font-semibold">Add Search Key</h3>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-gray-700">Provider</label>
            <input
              type="text"
              value="tavily"
              readOnly
              className="w-full mt-1 border rounded-lg px-3 py-2 text-sm bg-gray-50 text-gray-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Name</label>
            <input
              type="text"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              className="w-full mt-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">Base URL</label>
            <input
              type="text"
              placeholder="https://api.tavily.com/search"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full mt-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700">API Key</label>
            <input
              type="password"
              placeholder="tvly-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              className="w-full mt-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
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
            {loading ? "Saving..." : "Add Key"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SearchPage() {
  const [providers, setProviders] = useState<SearchProviderInfo[]>([]);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showReAuth, setShowReAuth] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const [authed, setAuthed] = useState(false);
  const [testQuery, setTestQuery] = useState("Flow LLM Router");
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testMsg, setTestMsg] = useState<{ id: string; text: string; ok: boolean } | null>(null);

  const loadProviders = useCallback(async () => {
    try {
      const data = await fetchAPI<SearchProviderInfo[]>("/search/providers");
      setProviders(data);
    } catch (e: any) {
      if (e instanceof AuthExpiredError) setShowReAuth(true);
    }
  }, []);

  useEffect(() => {
    const check = async () => {
      if (!getAuthToken()) {
        setShowReAuth(true);
        return;
      }
      try {
        await loadProviders();
        setAuthed(true);
      } catch {
        setShowReAuth(true);
      }
    };
    check();
  }, [loadProviders]);

  const requireAuth = (action: () => void) => {
    setPendingAction(() => action);
    setShowReAuth(true);
  };

  const handleReAuthSuccess = () => {
    setShowReAuth(false);
    setAuthed(true);
    loadProviders();
    if (pendingAction) {
      pendingAction();
      setPendingAction(null);
    }
  };

  const handleAddClick = () => {
    if (!authed) { requireAuth(() => setShowAddDialog(true)); return; }
    setShowAddDialog(true);
  };

  const handleToggle = async (provider: SearchProviderInfo) => {
    try {
      await fetchAPI(`/search/providers/${provider.id}`, {
        method: "PUT",
        body: JSON.stringify({ enabled: !provider.enabled }),
      });
      loadProviders();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) requireAuth(() => handleToggle(provider));
      else alert(e.message);
    }
  };

  const handleDelete = async (provider: SearchProviderInfo) => {
    if (!confirm(`Delete "${provider.key_name}"?`)) return;
    try {
      await fetchAPI(`/search/providers/${provider.id}`, { method: "DELETE" });
      loadProviders();
    } catch (e: any) {
      if (e instanceof AuthExpiredError) requireAuth(() => handleDelete(provider));
      else alert(e.message);
    }
  };

  const handleTest = async (provider: SearchProviderInfo) => {
    setTestingId(provider.id);
    setTestMsg(null);
    try {
      const result = await fetchAPI<SearchTestResult>(`/search/providers/${provider.id}/test`, {
        method: "POST",
        body: JSON.stringify({ query: testQuery.trim() || "Flow LLM Router", max_results: 3 }),
      });
      const title = result.sample_title ? `: ${result.sample_title}` : "";
      setTestMsg({
        id: provider.id,
        ok: true,
        text: `${result.result_count} results in ${result.latency_ms} ms${title}`,
      });
    } catch (e: any) {
      if (e instanceof AuthExpiredError) requireAuth(() => handleTest(provider));
      else setTestMsg({ id: provider.id, ok: false, text: e.message || "Test failed" });
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Search</h1>
        <button
          onClick={handleAddClick}
          className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700"
        >
          + Add Search Key
        </button>
      </div>

      <div className="flex items-center gap-3">
        <input
          type="text"
          value={testQuery}
          onChange={(e) => setTestQuery(e.target.value)}
          className="w-full max-w-md border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <Card className="p-0 overflow-hidden">
        {providers.length === 0 ? (
          <div className="py-16 text-center text-gray-400 text-sm">
            No search keys configured yet.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr className="text-left text-gray-500 text-xs uppercase tracking-wide">
                <th className="px-5 py-3 font-medium">Provider</th>
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Base URL</th>
                <th className="px-5 py-3 font-medium">Key</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {providers.map((p) => {
                const msg = testMsg?.id === p.id ? testMsg : null;
                return (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-indigo-50 text-indigo-700">
                        {p.provider}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-gray-800">{p.key_name}</td>
                    <td className="px-5 py-4 text-gray-500 text-xs font-mono">
                      {p.base_url ? (
                        <span title={p.base_url} className="truncate max-w-[260px] block">{p.base_url}</span>
                      ) : (
                        <span className="text-gray-300">default</span>
                      )}
                    </td>
                    <td className="px-5 py-4 font-mono text-gray-400 text-xs">{p.key_masked}</td>
                    <td className="px-5 py-4">
                      <button
                        onClick={() => handleToggle(p)}
                        className={`text-xs font-medium ${p.enabled ? "text-green-600 hover:text-green-800" : "text-gray-400 hover:text-gray-600"}`}
                      >
                        {p.enabled ? "Enabled" : "Disabled"}
                      </button>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center justify-end gap-3">
                        {msg && (
                          <span className={`text-xs max-w-[340px] truncate ${msg.ok ? "text-green-600" : "text-red-500"}`} title={msg.text}>
                            {msg.text}
                          </span>
                        )}
                        <button
                          onClick={() => handleTest(p)}
                          disabled={testingId === p.id}
                          className="text-xs px-2.5 py-1 rounded border border-blue-300 text-blue-600 hover:bg-blue-50 disabled:opacity-40"
                        >
                          {testingId === p.id ? "Testing..." : "Test"}
                        </button>
                        <button
                          onClick={() => handleDelete(p)}
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
        <AddSearchKeyDialog
          onSuccess={() => { setShowAddDialog(false); loadProviders(); }}
          onCancel={() => setShowAddDialog(false)}
          onAuthExpired={() => {
            setShowAddDialog(false);
            requireAuth(() => setShowAddDialog(true));
          }}
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
