"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, DonutChart, AreaChart, Text, Metric, Badge } from "@tremor/react";
import { fetchAPI, apiURL } from "@/lib/api";
import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

/* ─── Types ─── */

interface RouterConfigData {
  enabled: boolean;
  strategy: string;
  complexity: {
    tiers: Record<string, string>;
    tier_boundaries: Record<string, number>;
    dimension_weights: Record<string, number>;
  };
  classifier: {
    type: string;
    tier_boundaries: {
      simple_medium: number;
      medium_complex: number;
      complex_reasoning: number;
    };
    available: boolean;
    mf_embedding_model: string;
  };
}

interface TestResult {
  strategy: string;
  score: number;
  tier: string;
  routed_model: string;
  original_model: string;
  latency_us: number;
}

interface ModelItem {
  id: string;
  model_id?: string;
}

/* ─── Tier badge colors ─── */

const TIER_COLORS: Record<string, string> = {
  SIMPLE: "bg-green-100 text-green-700",
  MEDIUM: "bg-blue-100 text-blue-700",
  COMPLEX: "bg-orange-100 text-orange-700",
  REASONING: "bg-purple-100 text-purple-700",
  STRONG: "bg-purple-100 text-purple-700",
  WEAK: "bg-green-100 text-green-700",
  DIRECT: "bg-gray-100 text-gray-600",
};

function TierBadge({ tier }: { tier: string }) {
  const cls = TIER_COLORS[tier] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-semibold ${cls}`}>
      {tier}
    </span>
  );
}

/* ─── Slider component ─── */

function LabeledSlider({
  label,
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.01,
  suffix = "",
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-600 w-44 shrink-0">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="flex-1 h-2 rounded-lg appearance-none cursor-pointer accent-blue-600 bg-gray-200"
      />
      <span className="text-sm font-mono text-gray-700 w-14 text-right">
        {value.toFixed(2)}{suffix}
      </span>
    </div>
  );
}

/* ─── Model selector ─── */

const DEFAULT_SELECT_CLASS =
  "flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

function ModelSelect({
  label,
  value,
  onChange,
  models,
  allowEmpty = false,
  emptyLabel = "— Select —",
  labelClassName = "text-sm text-gray-600 w-28 shrink-0 font-medium",
  selectClassName = DEFAULT_SELECT_CLASS,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  models: string[];
  allowEmpty?: boolean;
  emptyLabel?: string;
  labelClassName?: string;
  selectClassName?: string;
}) {
  const withLegacy =
    value !== "" && !models.includes(value) ? [value, ...models] : models;
  return (
    <div className="flex items-center gap-3">
      <span className={labelClassName}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={selectClassName}
      >
        {allowEmpty && <option value="">{emptyLabel}</option>}
        {withLegacy.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>
  );
}

/* ─── Main Page ─── */

export default function RouterPage() {
  const [config, setConfig] = useState<RouterConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [showWeights, setShowWeights] = useState(false);

  // Test area
  const [testPrompt, setTestPrompt] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);

  // Models list for dropdowns
  const [modelList, setModelList] = useState<string[]>([]);

  // Stats
  const { data: statsData } = useSWR(apiURL("/router/stats?days=7"), fetcher, {
    refreshInterval: 30000,
  });
  const stats = statsData?.data;

  // Load config
  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiURL("/router/config"));
      const json = await res.json();
      if (json.success) setConfig(json.data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  // Load models
  const loadModels = useCallback(async () => {
    try {
      const data = await fetchAPI<ModelItem[]>("/models");
      setModelList(data.map((m) => m.model_id || m.id));
    } catch {
      setModelList(["gpt-4o-mini", "gpt-4o", "claude-sonnet", "o1-preview"]);
    }
  }, []);

  useEffect(() => {
    loadConfig();
    loadModels();
  }, [loadConfig, loadModels]);

  // Derive strategy from config
  const strategy = config
    ? config.enabled
      ? config.strategy
      : "off"
    : "off";

  const setStrategy = (s: string) => {
    if (!config) return;
    setConfig({
      ...config,
      enabled: s !== "off",
      strategy: s === "off" ? "complexity" : s,
    });
  };

  // Save
  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setSaveMsg("");
    try {
      await fetchAPI("/router/config", {
        method: "PUT",
        body: JSON.stringify(config),
      });
      setSaveMsg("saved");
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e: any) {
      setSaveMsg(e.message || "save failed");
    } finally {
      setSaving(false);
    }
  };

  // Test
  const handleTest = async () => {
    if (!testPrompt.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(apiURL("/router/test"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{ role: "user", content: testPrompt }],
          model: "gpt-4o",
        }),
      });
      const json = await res.json();
      if (json.success) setTestResult(json.data);
    } catch {
      /* ignore */
    } finally {
      setTesting(false);
    }
  };

  // Helpers for updating nested config
  const updateTier = (tier: string, model: string) => {
    if (!config) return;
    setConfig({
      ...config,
      complexity: {
        ...config.complexity,
        tiers: { ...config.complexity.tiers, [tier]: model },
      },
    });
  };

  const updateBoundary = (key: string, val: number) => {
    if (!config) return;
    setConfig({
      ...config,
      complexity: {
        ...config.complexity,
        tier_boundaries: { ...config.complexity.tier_boundaries, [key]: val },
      },
    });
  };

  const updateWeight = (key: string, val: number) => {
    if (!config) return;
    setConfig({
      ...config,
      complexity: {
        ...config.complexity,
        dimension_weights: { ...config.complexity.dimension_weights, [key]: val },
      },
    });
  };

  const updateClassifier = (patch: Partial<RouterConfigData["classifier"]>) => {
    if (!config) return;
    setConfig({
      ...config,
      classifier: { ...config.classifier, ...patch },
    });
  };

  // Stats charts
  const tierChartData = useMemo(() => {
    if (!stats?.tier_distribution) return [];
    return stats.tier_distribution.map((t: any) => ({
      name: t.tier,
      value: t.count,
    }));
  }, [stats]);

  const trendChartData = useMemo(() => {
    if (!stats?.daily_trend) return [];
    return stats.daily_trend;
  }, [stats]);

  const trendCategories = useMemo(() => {
    if (!trendChartData.length) return [];
    const keys = new Set<string>();
    for (const row of trendChartData) {
      for (const k of Object.keys(row)) {
        if (k !== "date") keys.add(k);
      }
    }
    return Array.from(keys);
  }, [trendChartData]);

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-gray-900">Smart Router</h1>
        <Card className="p-8 text-center text-gray-400">Loading configuration...</Card>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-gray-900">Smart Router</h1>
        <Card className="p-8 text-center text-red-500">Failed to load router configuration.</Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Smart Router</h1>
          <p className="text-sm text-gray-500 mt-1">
            Configure how requests are automatically routed to different models based on complexity.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saveMsg === "saved" && (
            <span className="text-sm text-green-600 font-medium">Saved!</span>
          )}
          {saveMsg && saveMsg !== "saved" && (
            <span className="text-sm text-red-600">{saveMsg}</span>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving..." : "Save Configuration"}
          </button>
        </div>
      </div>

      {/* ─── Strategy Selection ─── */}
      <Card className="p-5">
        <Text className="font-semibold text-base mb-4">Routing Strategy</Text>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            {
              id: "off",
              title: "Off",
              desc: "All requests forwarded directly to the client-specified model.",
            },
            {
              id: "complexity",
              title: "Rule-based Scoring",
              desc: "LiteLLM Complexity Router — 7-dimension scoring, < 1ms, no API calls.",
            },
            {
              id: "classifier",
              title: "Trained Classifier",
              desc: "RouteLLM — BERT/MF classifier, higher accuracy, 10-50ms.",
            },
          ].map((opt) => (
            <button
              key={opt.id}
              onClick={() => setStrategy(opt.id)}
              className={`text-left rounded-xl border-2 p-4 transition-all ${
                strategy === opt.id
                  ? "border-blue-600 bg-blue-50 ring-1 ring-blue-200"
                  : "border-gray-200 hover:border-gray-300 bg-white"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <div
                  className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                    strategy === opt.id ? "border-blue-600" : "border-gray-300"
                  }`}
                >
                  {strategy === opt.id && (
                    <div className="w-2 h-2 rounded-full bg-blue-600" />
                  )}
                </div>
                <span className="font-medium text-sm text-gray-900">{opt.title}</span>
              </div>
              <p className="text-xs text-gray-500 ml-6">{opt.desc}</p>
            </button>
          ))}
        </div>
      </Card>

      {/* ─── Complexity Config ─── */}
      {strategy === "complexity" && (
        <Card className="p-5 space-y-6">
          <Text className="font-semibold text-base">Rule-based Scoring Configuration</Text>

          {/* Model Mapping */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-gray-700">Model Mapping</h3>
            <p className="text-xs text-gray-500">
              Each complexity tier routes to a different model. Select from your synced models.
            </p>
            <div className="space-y-2">
              {(["SIMPLE", "MEDIUM", "COMPLEX", "REASONING"] as const).map((tier) => (
                <ModelSelect
                  key={tier}
                  label={tier}
                  value={config.complexity.tiers[tier] || ""}
                  onChange={(v) => updateTier(tier, v)}
                  models={modelList}
                />
              ))}
            </div>
          </div>

          {/* Tier Boundaries */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-gray-700">Tier Boundaries</h3>
            <p className="text-xs text-gray-500">
              Adjust where each tier begins. Lower values mean more requests go to stronger models.
            </p>
            <div className="space-y-2">
              <LabeledSlider
                label="SIMPLE / MEDIUM"
                value={config.complexity.tier_boundaries.simple_medium}
                onChange={(v) => updateBoundary("simple_medium", v)}
              />
              <LabeledSlider
                label="MEDIUM / COMPLEX"
                value={config.complexity.tier_boundaries.medium_complex}
                onChange={(v) => updateBoundary("medium_complex", v)}
              />
              <LabeledSlider
                label="COMPLEX / REASONING"
                value={config.complexity.tier_boundaries.complex_reasoning}
                onChange={(v) => updateBoundary("complex_reasoning", v)}
              />
            </div>
          </div>

          {/* Dimension Weights (collapsible) */}
          <div>
            <button
              onClick={() => setShowWeights(!showWeights)}
              className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900"
            >
              <span className={`transition-transform ${showWeights ? "rotate-90" : ""}`}>
                ▶
              </span>
              Dimension Weights (Advanced)
            </button>
            {showWeights && (
              <div className="mt-3 space-y-2 pl-5">
                <p className="text-xs text-gray-500 mb-2">
                  How much each signal contributes to the complexity score.
                </p>
                {Object.entries(config.complexity.dimension_weights).map(([key, val]) => (
                  <LabeledSlider
                    key={key}
                    label={key}
                    value={val}
                    onChange={(v) => updateWeight(key, v)}
                    max={0.5}
                  />
                ))}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* ─── Classifier Config ─── */}
      {strategy === "classifier" && (
        <Card className="p-5 space-y-6">
          <Text className="font-semibold text-base">Trained Classifier Configuration</Text>

          {!config.classifier.available && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
              <strong>RouteLLM not installed.</strong> Install with:{" "}
              <code className="bg-amber-100 px-1.5 py-0.5 rounded text-xs">
                pip install &apos;flow-llm-router[classifier]&apos;
              </code>
              <br />
              The system will fall back to rule-based scoring until RouteLLM is available.
            </div>
          )}

          {/* Classifier Type */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-gray-700">Classifier Type</h3>
            <div className="flex flex-wrap gap-2">
              {[
                { id: "bert", label: "BERT", desc: "Recommended — fully local, no API needed" },
                { id: "mf", label: "MF (Matrix Factorization)", desc: "Requires OpenAI API key for embeddings" },
                { id: "sw_ranking", label: "SW Ranking", desc: "Semantic weighted (needs OpenAI)" },
                { id: "causal_llm", label: "Causal LLM", desc: "LLM-based" },
              ].map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => updateClassifier({ type: opt.id })}
                  className={`rounded-lg border px-4 py-2 text-sm transition-all ${
                    config.classifier.type === opt.id
                      ? "border-blue-600 bg-blue-50 text-blue-700 font-medium"
                      : "border-gray-200 text-gray-600 hover:border-gray-300"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Tier Boundaries */}
          <div className="space-y-3">
            <div>
              <h3 className="text-sm font-medium text-gray-700">Tier Boundaries</h3>
              <p className="text-xs text-gray-400 mt-0.5">
                The classifier outputs a 0–1 score (likelihood the strong model is preferred).
                BERT scores typically range 0.18–0.57. Adjust to split into 4 tiers.
                Model mapping is shared with Rule-based Scoring.
              </p>
            </div>
            {(
              [
                { key: "simple_medium", label: "SIMPLE / MEDIUM" },
                { key: "medium_complex", label: "MEDIUM / COMPLEX" },
                { key: "complex_reasoning", label: "COMPLEX / REASONING" },
              ] as { key: keyof RouterConfigData["classifier"]["tier_boundaries"]; label: string }[]
            ).map(({ key, label }) => (
              <LabeledSlider
                key={key}
                label={label}
                value={config.classifier.tier_boundaries[key]}
                onChange={(v) =>
                  updateClassifier({
                    tier_boundaries: { ...config.classifier.tier_boundaries, [key]: v },
                  })
                }
              />
            ))}
          </div>

          {/* MF Embedding Settings — only shown when MF is selected */}
          {config.classifier.type === "mf" && (
            <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
              <div>
                <h3 className="text-sm font-medium text-amber-900">MF Router — Embedding Settings</h3>
                <p className="text-xs text-amber-700 mt-0.5">
                  MF needs embeddings from the same provider that listed this model. FlowGate uses the
                  provider key and base URL you already configured on the Providers page (vault). Pick a
                  model from the catalog after syncing. If the model is not found or the vault is locked,
                  the server falls back to <code className="bg-amber-100 px-1 rounded">OPENAI_API_KEY</code> /{" "}
                  <code className="bg-amber-100 px-1 rounded">OPENAI_BASE_URL</code>; if the embedding model
                  id is empty, it uses <code className="bg-amber-100 px-1 rounded">text-embedding-3-small</code>.
                </p>
              </div>

              <div className="space-y-2">
                <ModelSelect
                  label="Embedding model"
                  value={config.classifier.mf_embedding_model}
                  onChange={(v) => updateClassifier({ mf_embedding_model: v })}
                  models={modelList}
                  allowEmpty
                  emptyLabel="— Choose from synced models —"
                  labelClassName="text-sm text-amber-800 w-36 shrink-0"
                  selectClassName="flex-1 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>
            </div>
          )}
        </Card>
      )}

      {/* ─── Live Test ─── */}
      <Card className="p-5 space-y-4">
        <Text className="font-semibold text-base">Live Routing Test</Text>
        <p className="text-xs text-gray-500">
          Enter a prompt to see how it would be routed. No actual LLM call is made.
        </p>
        <div className="flex gap-3">
          <textarea
            value={testPrompt}
            onChange={(e) => setTestPrompt(e.target.value)}
            placeholder="Type a prompt to test routing... e.g. 'Design a distributed microservice with Kubernetes'"
            rows={3}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
          <button
            onClick={handleTest}
            disabled={testing || !testPrompt.trim()}
            className="self-end px-5 py-2 text-sm font-medium rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-40 transition-colors"
          >
            {testing ? "Testing..." : "Test Route"}
          </button>
        </div>

        {testResult && (
          <div className="rounded-lg bg-gray-50 border border-gray-200 p-4 grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Strategy</span>
              <p className="font-medium">{testResult.strategy}</p>
            </div>
            <div>
              <span className="text-gray-500">Score</span>
              <p className="font-mono font-medium">{testResult.score.toFixed(4)}</p>
            </div>
            <div>
              <span className="text-gray-500">Tier</span>
              <p><TierBadge tier={testResult.tier} /></p>
            </div>
            <div>
              <span className="text-gray-500">Routed To</span>
              <p className="font-mono text-blue-600 font-medium">{testResult.routed_model}</p>
            </div>
            <div>
              <span className="text-gray-500">Original Model</span>
              <p className="font-mono text-gray-500">{testResult.original_model}</p>
            </div>
            <div>
              <span className="text-gray-500">Latency</span>
              <p className="font-mono">{testResult.latency_us < 1000 ? `${testResult.latency_us}µs` : `${(testResult.latency_us / 1000).toFixed(1)}ms`}</p>
            </div>
          </div>
        )}
      </Card>

      {/* ─── Routing Stats ─── */}
      {stats && stats.total_routed > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="p-5">
            <Text className="font-semibold">Tier Distribution (7 days)</Text>
            <Metric className="mt-1 text-lg">{stats.total_routed} routed requests</Metric>
            {tierChartData.length > 0 ? (
              <DonutChart
                className="mt-4 h-52"
                data={tierChartData}
                category="value"
                index="name"
                colors={["green", "blue", "orange", "purple"]}
                showAnimation
              />
            ) : (
              <div className="mt-4 h-52 flex items-center justify-center text-gray-400 text-sm">
                No routing data yet
              </div>
            )}
          </Card>

          <Card className="p-5">
            <Text className="font-semibold">Daily Routing Trend (7 days)</Text>
            {trendChartData.length > 0 ? (
              <AreaChart
                className="mt-4 h-56"
                data={trendChartData}
                index="date"
                categories={trendCategories}
                colors={["green", "blue", "orange", "purple"]}
                showAnimation
                showLegend
              />
            ) : (
              <div className="mt-4 h-56 flex items-center justify-center text-gray-400 text-sm">
                No routing data yet
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
