"use client";

import { AreaChart, BarList, Card, DonutChart, Metric, Text } from "@tremor/react";
import useSWR from "swr";
import { apiURL } from "@/lib/api";
import { formatTokens } from "@/lib/utils";

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

  const modelBarData = modelData.map((m: { model: string; tokens: number }) => ({
    name: m.model,
    value: m.tokens,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
      <p className="text-sm text-gray-500 -mt-4">
        This page now focuses on usage volume only: requests, tokens, models, and providers.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4">
          <Text>7-Day Requests</Text>
          <Metric className="mt-1">
            {weekStats ? String(weekStats.total_requests) : "—"}
          </Metric>
          <Text className="text-xs text-gray-500 mt-1">
            {weekStats ? `${formatTokens(weekStats.total_tokens)} tokens` : ""}
          </Text>
        </Card>
        <Card className="p-4">
          <Text>30-Day Requests</Text>
          <Metric className="mt-1">
            {monthStats ? String(monthStats.total_requests) : "—"}
          </Metric>
          <Text className="text-xs text-gray-500 mt-1">
            {monthStats ? `${formatTokens(monthStats.total_tokens)} tokens` : ""}
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

      <Card>
        <Text className="font-semibold">Daily Token Trend (30d)</Text>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <Text className="font-semibold">Tokens by Model (30d)</Text>
          {modelBarData.length > 0 ? (
            <BarList
              data={modelBarData}
              className="mt-4"
              valueFormatter={(v: number) => formatTokens(v)}
            />
          ) : (
            <div className="mt-4 h-40 flex items-center justify-center text-gray-400 text-sm">
              No data yet
            </div>
          )}
        </Card>

        <Card>
          <Text className="font-semibold">Requests by Provider (30d)</Text>
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
