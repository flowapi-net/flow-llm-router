"use client";

import { AreaChart, BarChart, Card, DonutChart, Metric, Text } from "@tremor/react";
import useSWR from "swr";
import { apiURL } from "@/lib/api";
import { formatCost, formatTokens, formatLatency } from "@/lib/utils";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function KPICard({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <Text>{title}</Text>
      <Metric className="mt-1">{value}</Metric>
      {sub && <Text className="mt-1 text-xs text-gray-500">{sub}</Text>}
    </Card>
  );
}

export default function DashboardPage() {
  const { data: overview } = useSWR(apiURL("/stats/overview?period=today"), fetcher, {
    refreshInterval: 5000,
  });
  const { data: timeline } = useSWR(apiURL("/stats/timeline?granularity=hour&days=1"), fetcher, {
    refreshInterval: 10000,
  });
  const { data: providers } = useSWR(apiURL("/stats/providers?days=30"), fetcher, {
    refreshInterval: 30000,
  });
  const { data: models } = useSWR(apiURL("/stats/models?days=30&limit=8"), fetcher, {
    refreshInterval: 30000,
  });

  const stats = overview?.data;
  const timelineData = timeline?.data || [];
  const providerData = providers?.data || [];
  const modelData = models?.data || [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Today Requests"
          value={stats ? String(stats.total_requests) : "—"}
        />
        <KPICard
          title="Today Tokens"
          value={stats ? formatTokens(stats.total_tokens) : "—"}
          sub={stats ? `${formatTokens(stats.total_prompt_tokens)} in / ${formatTokens(stats.total_completion_tokens)} out` : undefined}
        />
        <KPICard
          title="Today Cost"
          value={stats ? formatCost(stats.total_cost_usd) : "—"}
        />
        <KPICard
          title="Avg Latency"
          value={stats ? formatLatency(stats.avg_latency_ms) : "—"}
          sub={stats ? `${stats.success_rate}% success` : undefined}
        />
      </div>

      {/* Timeline Chart */}
      <Card>
        <Text className="font-semibold">Token Usage (24h)</Text>
        <AreaChart
          className="mt-4 h-64"
          data={timelineData}
          index="time"
          categories={["tokens"]}
          colors={["blue"]}
          valueFormatter={(v: number) => formatTokens(v)}
          showLegend={false}
          showAnimation
        />
      </Card>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Provider Pie */}
        <Card>
          <Text className="font-semibold">Cost by Provider (30d)</Text>
          {providerData.length > 0 ? (
            <DonutChart
              className="mt-4 h-52"
              data={providerData}
              category="cost"
              index="provider"
              colors={["blue", "cyan", "indigo", "violet", "fuchsia"]}
              valueFormatter={(v: number) => formatCost(v)}
              showAnimation
            />
          ) : (
            <div className="mt-4 h-52 flex items-center justify-center text-gray-400 text-sm">
              No data yet
            </div>
          )}
        </Card>

        {/* Model Bar Chart */}
        <Card>
          <Text className="font-semibold">Top Models (30d)</Text>
          {modelData.length > 0 ? (
            <BarChart
              className="mt-4 h-52"
              data={modelData}
              index="model"
              categories={["requests"]}
              colors={["blue"]}
              showLegend={false}
              showAnimation
            />
          ) : (
            <div className="mt-4 h-52 flex items-center justify-center text-gray-400 text-sm">
              No data yet
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
