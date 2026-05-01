"use client";

import { useEffect, useMemo, useState } from "react";

export interface CatalogModelRow {
  id: string;
  provider: string;
  model_id: string;
  display_name?: string | null;
}

/**
 * Canonical id stored in router config and sent to the proxy: `{vault_provider}/{upstream_model_id}`.
 * Matches backend `_infer_provider()` (first path segment = vault key) and `_upstream_model_for_openai_compatible()`.
 */
export function catalogModelToRoutingId(m: CatalogModelRow): string {
  const p = (m.provider || "").trim();
  const id = (m.model_id || "").trim();
  if (!id) return p;
  if (!p) return id;
  const pl = p.toLowerCase();
  const il = id.toLowerCase();
  if (il === pl || il.startsWith(`${pl}/`)) {
    return id;
  }
  return `${p}/${id}`;
}

export function catalogContainsRoutingValue(models: CatalogModelRow[], value: string): boolean {
  const v = value.trim();
  if (!v) return false;
  return models.some((m) => catalogModelToRoutingId(m) === v || m.model_id === v);
}

type Props = {
  open: boolean;
  title: string;
  models: CatalogModelRow[];
  /** Current value not present in catalog (still selectable as legacy) */
  legacyValue?: string;
  allowEmpty?: boolean;
  emptyLabel?: string;
  onClose: () => void;
  /** Full routing id, e.g. `siliconflow/BAAI/bge-large-en-v1.5` */
  onSelect: (routingModelId: string) => void;
};

export default function ModelPickerModal({
  open,
  title,
  models,
  legacyValue,
  allowEmpty = false,
  emptyLabel = "— Clear —",
  onClose,
  onSelect,
}: Props) {
  const [provider, setProvider] = useState<string>("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    if (open) {
      setProvider("all");
      setQ("");
    }
  }, [open]);

  const providers = useMemo(() => {
    const s = new Set(models.map((m) => m.provider));
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [models]);

  const filtered = useMemo(() => {
    let rows = models;
    if (provider !== "all") {
      rows = rows.filter((m) => m.provider === provider);
    }
    const qq = q.trim().toLowerCase();
    if (qq) {
      rows = rows.filter((m) => {
        const name = (m.display_name || "").toLowerCase();
        const routing = catalogModelToRoutingId(m).toLowerCase();
        return (
          routing.includes(qq) ||
          m.model_id.toLowerCase().includes(qq) ||
          name.includes(qq) ||
          m.provider.toLowerCase().includes(qq)
        );
      });
    }
    return rows;
  }, [models, provider, q]);

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);

  if (!open) return null;

  const showLegacy =
    legacyValue &&
    !catalogContainsRoutingValue(models, legacyValue) &&
    (!q.trim() || legacyValue.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="model-picker-title"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[85vh] flex flex-col border border-gray-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 pt-4 pb-3 border-b border-gray-100">
          <h2 id="model-picker-title" className="text-lg font-semibold text-gray-900">
            {title}
          </h2>
          <div className="mt-3 flex flex-col sm:flex-row gap-2">
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All providers</option>
              {providers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search provider/model, id, or name…"
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoFocus
            />
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2">
          {allowEmpty && (
            <button
              type="button"
              onClick={() => {
                onSelect("");
                onClose();
              }}
              className="w-full text-left px-3 py-2.5 rounded-lg text-sm text-gray-600 hover:bg-gray-50 border border-dashed border-gray-200 mb-1"
            >
              {emptyLabel}
            </button>
          )}
          {showLegacy && (
            <button
              type="button"
              onClick={() => {
                onSelect(legacyValue);
                onClose();
              }}
              className="w-full text-left px-3 py-2.5 rounded-lg text-sm border border-amber-200 bg-amber-50 text-amber-900 mb-2"
            >
              <span className="font-mono font-medium">{legacyValue}</span>
              <span className="ml-2 text-xs text-amber-700">(not in catalog — re-pick to use provider/model)</span>
            </button>
          )}
          {filtered.length === 0 && !showLegacy && !allowEmpty ? (
            <p className="text-sm text-gray-500 px-3 py-8 text-center">
              No models match. Try another provider or search term.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {filtered.map((m) => {
                const routing = catalogModelToRoutingId(m);
                return (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(routing);
                        onClose();
                      }}
                      className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset"
                    >
                      <div className="font-mono text-gray-900 truncate">{routing}</div>
                      {m.display_name && (
                        <div className="text-xs text-gray-500 truncate mt-0.5">{m.display_name}</div>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="px-4 py-3 border-t border-gray-100 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
