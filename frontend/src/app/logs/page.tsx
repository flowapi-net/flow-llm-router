"use client";

import { Card, Text, Badge } from "@tremor/react";
import { useCallback, useState } from "react";
import useSWR from "swr";
import { apiURL, fetchAPI } from "@/lib/api";
import { formatCost, formatTokens, formatLatency, timeAgo } from "@/lib/utils";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

interface LogEntry {
  id: string;
  created_at: string;
  model_requested: string;
  model_used: string;
  provider: string;
  stream: boolean;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  ttft_ms: number | null;
  session_id: string | null;
  complexity_tier: string | null;
}

interface LogDetail {
  id: string;
  messages: string;
  response_content: string | null;
  error_message: string | null;
  temperature: number | null;
  max_tokens: number | null;
  [key: string]: any;
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge color={status === "success" ? "green" : "red"} size="xs">
      {status}
    </Badge>
  );
}

function LogDetailPanel({
  logId,
  onClose,
}: {
  logId: string;
  onClose: () => void;
}) {
  const { data } = useSWR(apiURL(`/logs/${logId}`), fetcher);
  const detail: LogDetail | null = data?.data || null;

  let messages: any[] = [];
  try {
    if (detail?.messages) messages = JSON.parse(detail.messages);
  } catch {}

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-2xl bg-white shadow-xl overflow-y-auto">
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <h2 className="font-semibold text-lg">Request Detail</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">
            &times;
          </button>
        </div>

        {detail ? (
          <div className="px-6 py-4 space-y-6">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Model Requested</span>
                <p className="font-mono">{detail.model_requested}</p>
              </div>
              <div>
                <span className="text-gray-500">Model Used</span>
                <p className="font-mono">{detail.model_used}</p>
              </div>
              <div>
                <span className="text-gray-500">Provider</span>
                <p>{detail.provider || "—"}</p>
              </div>
              <div>
                <span className="text-gray-500">Status</span>
                <p><StatusBadge status={detail.status} /></p>
              </div>
              <div>
                <span className="text-gray-500">Tokens</span>
                <p>{detail.prompt_tokens} in / {detail.completion_tokens} out</p>
              </div>
              <div>
                <span className="text-gray-500">Cost</span>
                <p>{formatCost(detail.cost_usd)}</p>
              </div>
              <div>
                <span className="text-gray-500">Latency</span>
                <p>{formatLatency(detail.latency_ms)}</p>
              </div>
              <div>
                <span className="text-gray-500">TTFT</span>
                <p>{detail.ttft_ms != null ? formatLatency(detail.ttft_ms) : "—"}</p>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Messages</h3>
              <div className="bg-gray-50 rounded-lg p-4 max-h-80 overflow-y-auto">
                {messages.map((msg: any, i: number) => (
                  <div key={i} className="mb-3 last:mb-0">
                    <span className="text-xs font-semibold uppercase text-gray-500">
                      {msg.role}
                    </span>
                    <pre className="mt-1 text-sm whitespace-pre-wrap break-words text-gray-800 font-mono">
                      {typeof msg.content === "string"
                        ? msg.content
                        : JSON.stringify(msg.content, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Response</h3>
              <div className="bg-gray-50 rounded-lg p-4 max-h-80 overflow-y-auto">
                <pre className="text-sm whitespace-pre-wrap break-words text-gray-800 font-mono">
                  {detail.response_content || detail.error_message || "No content"}
                </pre>
              </div>
            </div>
          </div>
        ) : (
          <div className="px-6 py-12 text-center text-gray-400">Loading...</div>
        )}
      </div>
    </div>
  );
}

export default function LogsPage() {
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const pageSize = 30;

  const { data, isLoading } = useSWR(
    apiURL(`/logs?page=${page}&size=${pageSize}`),
    fetcher,
    { refreshInterval: 5000 }
  );

  const logs: LogEntry[] = data?.data || [];
  const total: number = data?.meta?.total || 0;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Request Logs</h1>
        <Text className="text-sm text-gray-500">{total} total requests</Text>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Tokens</th>
                <th className="px-4 py-3">Cost</th>
                <th className="px-4 py-3">Latency</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {isLoading && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                    Loading...
                  </td>
                </tr>
              )}
              {!isLoading && logs.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                    No logs yet. Send a request to /v1/chat/completions to get started.
                  </td>
                </tr>
              )}
              {logs.map((log) => (
                <tr
                  key={log.id}
                  className="hover:bg-blue-50 cursor-pointer transition-colors"
                  onClick={() => setSelectedId(log.id)}
                >
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                    {log.created_at ? timeAgo(log.created_at) : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {log.model_requested !== log.model_used ? (
                      <span>
                        <span className="text-gray-400">{log.model_requested}</span>
                        <span className="text-gray-300 mx-1">&rarr;</span>
                        <span className="text-blue-600">{log.model_used}</span>
                      </span>
                    ) : (
                      log.model_used
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{log.provider || "—"}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatTokens(log.total_tokens)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{formatCost(log.cost_usd)}</td>
                  <td className="px-4 py-3 tabular-nums">{formatLatency(log.latency_ms)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={log.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t px-4 py-3 text-sm">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-3 py-1 rounded border text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-gray-500">
              Page {page} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 rounded border text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        )}
      </Card>

      {selectedId && (
        <LogDetailPanel logId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}
