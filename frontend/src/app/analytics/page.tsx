"use client";

import { AreaChart, BarList, Card, DonutChart, Metric, Text } from "@tremor/react";
import useSWR from "swr";
import { apiURL } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/utils";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function AnalyticsPage() {
  const { data: overviewWeek } = useSWR(
    apiURL("/stats/overview?period=week"),
    fetcher,
    { refreshInterval: 30000 }
  );
  const { data: overviewMonth } = useSWR(
    apiURL("/stats/overview?period=month"),
    fetcher,
    { refreshInterval: 30000 }
  );
  const { data: timeline } = useSWR(
    apiURL("/stats/timeline?granularity=day&days=30"),
    fetcher,
    { refreshInterval: 60000 }
  );
  const { data: models } = useSWR(
    apiURL("/stats/models?days=30&limit=10"),
    fetcher,
    { refreshInterval: 60000 }
  );
  const { data: providers } = useSWR(
    apiURL("/stats/providers?days=30"),
    fetcher,
    { refreshInterval: 60000 }
  );

  const weekStats = overviewWeek?.data;
  const monthStats = overviewMonth?.data;
  const timelineData = timeline?.data || [];
  const modelData = models?.data || [];
  const providerData = providers?.data || [];

  const modelBarData = modelData.map((m: any) => ({
    name: m.model,
    value: m.cost,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Cost Analytics</h1>

      {/* Period Comparison */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <Text>7-Day Cost</Text>
          <Metric className="mt-1">
            {weekStats ? formatCost(weekStats.total_cost_usd) : "—"}
          </Metric>
          <Text className="text-xs text-gray-500 mt-1">
            {weekStats ? `${weekStats.total_requests} requests` : ""}
          </Text>
        </Card>
        <Card className="p-4">
          <Text>30-Day Cost</Text>
          <Metric className="mt-1">
            {monthStats ? formatCost(monthStats.total_cost_usd) : "—"}
          </Metric>
          <Text className="text-xs text-gray-500 mt-1">
            {monthStats ? `${monthStats.total_requests} requests` : ""}
          </Text>
        </Card>
        <Card className="p-4">
          <Text>7-Day Tokens</Text>
          <Metric className="mt-1">
            {weekStats ? formatTokens(weekStats.total_tokens) : "—"}
          </Metric>
        </Card>
        <Card className="p-4">
          <Text>30-Day Tokens</Text>
          <Metric className="mt-1">
            {monthStats ? formatTokens(monthStats.total_tokens) : "—"}
          </Metric>
        </Card>
      </div>

      {/* Daily Cost Trend */}
      <Card>
        <Text className="font-semibold">Daily Cost Trend (30d)</Text>
        <AreaChart
          className="mt-4 h-64"
          data={timelineData}
          index="time"
          categories={["cost"]}
          colors={["emerald"]}
          valueFormatter={(v: number) => formatCost(v)}
          showLegend={false}
          showAnimation
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Cost by Model */}
        <Card>
          <Text className="font-semibold">Cost by Model (30d)</Text>
          {modelBarData.length > 0 ? (
            <BarList
              data={modelBarData}
              className="mt-4"
              valueFormatter={(v: number) => formatCost(v)}
            />
          ) : (
            <div className="mt-4 h-40 flex items-center justify-center text-gray-400 text-sm">
              No data yet
            </div>
          )}
        </Card>

        {/* Provider Distribution */}
        <Card>
          <Text className="font-semibold">Provider Distribution (30d)</Text>
          {providerData.length > 0 ? (
            <DonutChart
              className="mt-4 h-52"
              data={providerData}
              category="requests"
              index="provider"
              colors={["blue", "cyan", "indigo", "violet", "fuchsia"]}
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
