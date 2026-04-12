"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, Text } from "@tremor/react";
import { fetchAPI, getAuthToken, setAuthToken } from "@/lib/api";

/* ── Types ── */

interface VaultStatus {
  vault_initialized: boolean;
  vault_unlocked: boolean;
}

/* ── Password Dialog ── */

function PasswordDialog({
  mode,
  onSuccess,
  onCancel,
}: {
  mode: "setup" | "verify";
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setError("");
    if (mode === "setup" && password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 4) {
      setError("Password must be at least 4 characters");
      return;
    }
    setLoading(true);
    try {
      if (mode === "setup") {
        await fetchAPI("/auth/setup", {
          method: "POST",
          body: JSON.stringify({ password }),
        });
      }
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
        <h3 className="text-lg font-semibold">
          {mode === "setup" ? "Set Master Password" : "Enter Master Password"}
        </h3>
        <input
          type="password"
          placeholder="Master password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          autoFocus
          onKeyDown={(e) => e.key === "Enter" && (mode === "verify" || confirm) && handleSubmit()}
        />
        {mode === "setup" && (
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          />
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-lg text-gray-600 hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "..." : mode === "setup" ? "Set Password" : "Unlock"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Main Settings Page ── */

export default function SettingsPage() {
  const [vaultStatus, setVaultStatus] = useState<VaultStatus | null>(null);
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [passwordMode, setPasswordMode] = useState<"setup" | "verify">("verify");
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);

  const isAuthed = !!getAuthToken();

  const loadVaultStatus = useCallback(async () => {
    try {
      const status = await fetchAPI<VaultStatus>("/auth/status");
      setVaultStatus(status);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadVaultStatus();
  }, [loadVaultStatus]);

  const requireAuth = (action: () => void) => {
    setPendingAction(() => action);
    setPasswordMode("verify");
    setShowPasswordDialog(true);
  };

  const handleUnlockClick = () => {
    if (!vaultStatus) return;
    setPasswordMode(vaultStatus.vault_initialized ? "verify" : "setup");
    setPendingAction(null);
    setShowPasswordDialog(true);
  };

  const handlePasswordSuccess = () => {
    setShowPasswordDialog(false);
    loadVaultStatus();
    if (pendingAction) {
      pendingAction();
      setPendingAction(null);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

      {/* Vault */}
      <Card className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <Text className="font-semibold text-base">密钥保险箱（Vault）</Text>
            <p className="mt-1 text-sm text-gray-500 leading-relaxed">
              FlowGate 将所有 Provider API Key 加密存储在本地 SQLite 中。
              Vault 由一个<strong className="text-gray-700">主密码</strong>保护——只有输入正确主密码后，
              FlowGate 才会在调用 LLM 时临时解密所需的 Key，调用完毕立即销毁明文，
              不会将 Key 长期留在内存或环境变量中。
            </p>
            <p className="mt-1.5 text-xs text-gray-400">
              服务重启后 Vault 自动锁定，需重新解锁才能继续代理请求。
              如需管理 Provider API Key，请前往{" "}
              <a href="/providers" className="text-blue-500 hover:underline">Providers</a> 页面。
            </p>
            <div className="mt-3 flex items-center gap-3">
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                  vaultStatus?.vault_unlocked
                    ? "bg-green-100 text-green-700"
                    : vaultStatus?.vault_initialized
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-gray-100 text-gray-600"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    vaultStatus?.vault_unlocked
                      ? "bg-green-500"
                      : vaultStatus?.vault_initialized
                      ? "bg-yellow-500"
                      : "bg-gray-400"
                  }`}
                />
                {vaultStatus?.vault_unlocked
                  ? "已解锁 · 可正常代理请求"
                  : vaultStatus?.vault_initialized
                  ? "已锁定 · 代理请求将失败"
                  : "未初始化 · 请先设置主密码"}
              </span>
              {isAuthed && (
                <span className="text-xs text-green-600 font-medium">✓ 已认证</span>
              )}
            </div>
          </div>
          {(!vaultStatus?.vault_unlocked || !isAuthed) && (
            <button
              onClick={handleUnlockClick}
              className="shrink-0 px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700"
            >
              {!vaultStatus?.vault_initialized ? "初始化" : "解锁"}
            </button>
          )}
        </div>
      </Card>

      {/* Dialogs */}
      {showPasswordDialog && (
        <PasswordDialog
          mode={passwordMode}
          onSuccess={handlePasswordSuccess}
          onCancel={() => setShowPasswordDialog(false)}
        />
      )}
    </div>
  );
}
