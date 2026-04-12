"use client";

import { useEffect, useState } from "react";
import { fetchAPI, setAuthToken } from "@/lib/api";

type GateState = "checking" | "setup" | "unlock" | "open";

interface VaultStatus {
  vault_initialized: boolean;
  vault_unlocked: boolean;
}

/* ── Fullscreen Gate Wrapper ── */

export default function VaultGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const checkStatus = async () => {
    try {
      const status = await fetchAPI<VaultStatus>("/auth/status");
      if (!status.vault_initialized) {
        setState("setup");
      } else if (!status.vault_unlocked) {
        setState("unlock");
      } else {
        setState("open");
      }
    } catch {
      // If API not reachable yet, retry
      setState("open");
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  const handleSetup = async () => {
    setError("");
    if (password.length < 4) {
      setError("密码至少 4 位");
      return;
    }
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      await fetchAPI("/auth/setup", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      const res = await fetchAPI<{ token: string }>("/auth/verify", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setAuthToken(res.token);
      setState("open");
    } catch (e: any) {
      setError(e.message || "设置失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  const handleUnlock = async () => {
    setError("");
    if (!password) {
      setError("请输入 Master Password");
      return;
    }
    setLoading(true);
    try {
      const res = await fetchAPI<{ token: string }>("/auth/verify", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setAuthToken(res.token);
      setState("open");
    } catch (e: any) {
      setError(e.message || "密码错误");
    } finally {
      setLoading(false);
    }
  };

  if (state === "checking") {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-gray-950">
        <div className="text-gray-500 text-sm animate-pulse">正在连接 FlowGate…</div>
      </div>
    );
  }

  if (state === "setup") {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-gray-950">
        <div className="w-full max-w-sm px-4">
          <div className="text-center mb-8">
            <div className="text-4xl mb-3">⚡</div>
            <h1 className="text-2xl font-bold text-white">欢迎使用 FlowGate</h1>
            <p className="text-gray-400 text-sm mt-2">
              首次使用需要设置一个 Master Password。<br />
              所有 Provider API Key 将使用此密码加密存储。
            </p>
          </div>
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Master Password
              </label>
              <input
                type="password"
                placeholder="设置一个强密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && confirm && handleSetup()}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                确认密码
              </label>
              <input
                type="password"
                placeholder="再次输入密码"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                onKeyDown={(e) => e.key === "Enter" && handleSetup()}
              />
            </div>
            {error && (
              <p className="text-red-400 text-xs bg-red-950/50 border border-red-900 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            <button
              onClick={handleSetup}
              disabled={loading || !password || !confirm}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {loading ? "初始化中…" : "设置 Master Password"}
            </button>
            <p className="text-xs text-gray-600 text-center">
              密码不会被明文存储，丢失后需重新添加所有 API Key
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (state === "unlock") {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-gray-950">
        <div className="w-full max-w-sm px-4">
          <div className="text-center mb-8">
            <div className="text-4xl mb-3">🔒</div>
            <h1 className="text-2xl font-bold text-white">FlowGate 已锁定</h1>
            <p className="text-gray-400 text-sm mt-2">
              输入 Master Password 解锁 Vault，<br />
              API Key 才能在代理请求中自动注入。
            </p>
          </div>
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Master Password
              </label>
              <input
                type="password"
                placeholder="输入 Master Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && handleUnlock()}
              />
            </div>
            {error && (
              <p className="text-red-400 text-xs bg-red-950/50 border border-red-900 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            <button
              onClick={handleUnlock}
              disabled={loading || !password}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {loading ? "验证中…" : "解锁 Vault"}
            </button>
            <p className="text-xs text-gray-600 text-center">
              认证 token 仅保存在当前浏览器 session，关闭标签页后需重新验证
            </p>
          </div>
        </div>
      </div>
    );
  }

  // state === "open"
  return <>{children}</>;
}
