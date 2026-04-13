"use client";

import { Card, Text, Badge } from "@tremor/react";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { apiURL } from "@/lib/api";
import { formatTokens, formatLatency, timeAgo } from "@/lib/utils";

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
  latency_ms: number;
  ttft_ms: number | null;
  session_id: string | null;
  complexity_tier: string | null;
}

interface LogDetail {
  id: string;
  created_at?: string;
  model_requested: string;
  model_used: string;
  provider: string;
  messages: string;
  response_content: string | null;
  error_message: string | null;
  temperature: number | null;
  max_tokens: number | null;
  stream?: boolean;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  ttft_ms: number | null;
  session_id?: string | null;
  user_tag?: string | null;
  complexity_score?: number | null;
  complexity_tier?: string | null;
  skills_injected?: string | null;
  [key: string]: unknown;
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge color={status === "success" ? "green" : "red"} size="xs">
      {status}
    </Badge>
  );
}

const TIER_STYLES: Record<string, string> = {
  SIMPLE: "bg-green-100 text-green-700",
  MEDIUM: "bg-blue-100 text-blue-700",
  COMPLEX: "bg-orange-100 text-orange-700",
  REASONING: "bg-purple-100 text-purple-700",
  STRONG: "bg-purple-100 text-purple-700",
  WEAK: "bg-green-100 text-green-700",
};

function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return <span className="text-gray-400">—</span>;
  const cls = TIER_STYLES[tier] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold ${cls}`}>
      {tier}
    </span>
  );
}

/** Structured record for the “raw JSON” tab (mirrors API fields + parsed messages). */
function buildRawLogRecord(detail: LogDetail, parsedMessages: unknown): Record<string, unknown> {
  const req: Record<string, unknown> = {
    model_requested: detail.model_requested,
    model_used: detail.model_used,
    provider: detail.provider,
    stream: detail.stream ?? false,
    temperature: detail.temperature,
    max_tokens: detail.max_tokens,
  };
  if (Array.isArray(parsedMessages)) {
    req.messages = parsedMessages;
  } else if (typeof detail.messages === "string" && detail.messages) {
    req.messages_raw = detail.messages;
  }

  return {
    id: detail.id,
    created_at: detail.created_at ?? null,
    request: req,
    response: {
      status: detail.status,
      content: detail.response_content,
      error: detail.error_message,
    },
    usage: {
      prompt_tokens: detail.prompt_tokens,
      completion_tokens: detail.completion_tokens,
      total_tokens: detail.total_tokens,
    },
    performance: {
      latency_ms: detail.latency_ms,
      ttft_ms: detail.ttft_ms,
    },
    session_id: detail.session_id ?? null,
    user_tag: detail.user_tag ?? null,
    routing: {
      complexity_score: detail.complexity_score ?? null,
      complexity_tier: detail.complexity_tier ?? null,
      skills_injected: detail.skills_injected ?? null,
    },
  };
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
  const [viewMode, setViewMode] = useState<"readable" | "raw">("readable");
  const [copied, setCopied] = useState(false);

  let messages: any[] = [];
  let messagesParseError = false;
  try {
    if (detail?.messages) messages = JSON.parse(detail.messages);
  } catch {
    messagesParseError = !!detail?.messages;
  }

  const rawJsonString = useMemo(() => {
    if (!detail) return "";
    const record = buildRawLogRecord(detail, messagesParseError ? null : messages);
    return JSON.stringify(record, null, 2);
  }, [detail, messages, messagesParseError]);

  const copyRaw = async () => {
    if (!rawJsonString) return;
    try {
      await navigator.clipboard.writeText(rawJsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-2xl bg-white shadow-xl overflow-y-auto flex flex-col">
        <div className="sticky top-0 z-10 bg-white border-b px-6 py-4 flex flex-wrap items-center gap-3 justify-between">
          <h2 className="font-semibold text-lg">Request Detail</h2>
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5 text-xs font-medium">
              <button
                type="button"
                onClick={() => setViewMode("readable")}
                className={`rounded-md px-3 py-1.5 transition-colors ${
                  viewMode === "readable"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                可读视图
              </button>
              <button
                type="button"
                onClick={() => setViewMode("raw")}
                className={`rounded-md px-3 py-1.5 transition-colors ${
                  viewMode === "raw"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                原始 JSON
              </button>
            </div>
            {viewMode === "raw" && (
              <button
                type="button"
                onClick={copyRaw}
                className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                {copied ? "已复制" : "复制 JSON"}
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none px-1">
              &times;
            </button>
          </div>
        </div>

        {detail ? (
          <div className="px-6 py-4 space-y-6 flex-1">
            {viewMode === "raw" ? (
              <div className="space-y-2">
                <p className="text-xs text-gray-500">
                  以下为该条日志的完整结构化数据（含请求 messages、响应与用量），便于调试与对接。
                </p>
                <div className="rounded-xl border border-slate-800 overflow-hidden shadow-inner">
                  <SyntaxHighlighter
                    language="json"
                    style={vscDarkPlus}
                    customStyle={{
                      margin: 0,
                      padding: "1rem 1.125rem",
                      fontSize: "12.5px",
                      lineHeight: 1.55,
                      maxHeight: "min(70vh, 640px)",
                      overflow: "auto",
                      borderRadius: 0,
                    }}
                    showLineNumbers
                    lineNumberStyle={{ minWidth: "2.5rem", opacity: 0.45 }}
                    wrapLongLines
                  >
                    {rawJsonString}
                  </SyntaxHighlighter>
                </div>
              </div>
            ) : (
              <>
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
                <span className="text-gray-500">Latency</span>
                <p>{formatLatency(detail.latency_ms)}</p>
              </div>
              <div>
                <span className="text-gray-500">TTFT</span>
                <p>{detail.ttft_ms != null ? formatLatency(detail.ttft_ms) : "—"}</p>
              </div>
              <div>
                <span className="text-gray-500">Routing</span>
                <div className="mt-0.5 flex items-center gap-2">
                  <TierBadge tier={detail.complexity_tier ?? null} />
                  {detail.complexity_score != null && (
                    <span className="text-gray-400 text-xs font-mono">score: {detail.complexity_score}</span>
                  )}
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Messages</h3>
              <div className="bg-gray-50 rounded-lg p-4 max-h-80 overflow-y-auto">
                {messagesParseError && detail.messages ? (
                  <pre className="text-sm whitespace-pre-wrap break-words text-amber-800 font-mono">
                    {detail.messages}
                  </pre>
                ) : (
                  messages.map((msg: any, i: number) => (
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
                  ))
                )}
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
              </>
            )}
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
                <th className="px-4 py-3">Tier</th>
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
                  <td className="px-4 py-3">
                    <TierBadge tier={log.complexity_tier} />
                  </td>
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
