"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import Link from "next/link";

const MEMBERSHIP_LABELS: Record<string, string> = {
  none: "未开通",
  basic: "Basic",
  standard: "Standard",
  premium: "Premium",
};

const MEMBERSHIP_COLORS: Record<string, string> = {
  none: "#9CA3AF",
  basic: "#22C55E",
  standard: "#F59E0B",
  premium: "#A855F7",
};

export default function ProfilePage() {
  const router = useRouter();
  const { user, token, refreshUser, logout } = useAuth();
  const [username, setUsername] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [message, setMessage] = useState<{ type: "ok" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [pointsLog, setPointsLog] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    if (user) {
      setUsername(user.username);
    }
    loadPointsLog();
  }, [token, user]);

  const loadPointsLog = async () => {
    const res = await apiFetch<Array<Record<string, unknown>>>("/api/points/log", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok && res.data) {
      setPointsLog(res.data);
    }
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setSaving(true);

    const body: Record<string, unknown> = {};

    if (username.trim() !== user?.username) {
      body.username = username.trim();
    }

    if (newPassword) {
      body.current_password = currentPassword;
      body.new_password = newPassword;
      body.confirm_new_password = confirmNewPassword;
    }

    if (Object.keys(body).length === 0) {
      setMessage({ type: "error", text: "没有需要保存的更改" });
      setSaving(false);
      return;
    }

    const res = await apiFetch("/api/auth/profile", {
      method: "PUT",
      body: JSON.stringify(body),
      headers: { Authorization: `Bearer ${token}` },
    });

    if (res.ok) {
      setMessage({ type: "ok", text: "保存成功" });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      await refreshUser();
    } else {
      setMessage({ type: "error", text: res.error?.message || "保存失败" });
    }
    setSaving(false);
  };

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  const getMemberBadge = () => {
    if (!user || user.membership_type === "none") return null;
    const color = MEMBERSHIP_COLORS[user.membership_type] || "#9CA3AF";
    const label = MEMBERSHIP_LABELS[user.membership_type] || user.membership_type;
    return { color, label };
  };

  const memberBadge = getMemberBadge();

  if (!user) {
    return (
      <div className="flex items-center justify-center py-20">
        <p style={{ color: "var(--text-secondary)" }}>加载中...</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold tracking-tight">
        <span className="text-glow">个人中心</span>
      </h1>

      {/* 用户信息卡片 */}
      <div className="card">
        <div className="flex items-center gap-4 mb-6">
          <div
            className="flex h-16 w-16 items-center justify-center rounded-full text-xl font-bold"
            style={{ background: "rgba(34,197,94,0.15)", color: "var(--accent)" }}
          >
            {user.username.charAt(0).toUpperCase()}
          </div>
          <div>
            <h2 className="text-lg font-semibold">{user.username}</h2>
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {user.email}
            </p>
            {memberBadge && (
              <span
                className="inline-flex items-center gap-1 mt-1 text-xs font-medium px-2 py-0.5 rounded"
                style={{
                  background: `${memberBadge.color}20`,
                  color: memberBadge.color,
                  border: `1px solid ${memberBadge.color}40`,
                }}
              >
                {memberBadge.label}
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span style={{ color: "var(--text-muted)" }}>免费点数</span>
            <p className="text-lg font-semibold" style={{ color: "var(--accent)" }}>
              {user.free_points_today}
            </p>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>充值点数</span>
            <p className="text-lg font-semibold">{user.points}</p>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>签到连续</span>
            <p className="text-lg font-semibold">{user.checkin_streak} 天</p>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>邀请码</span>
            <div className="flex items-center gap-2">
              <p className="text-lg font-semibold font-mono">{user.invite_code || "-"}</p>
              {user.invite_code && (
                <button
                  onClick={() => navigator.clipboard.writeText(user.invite_code!)}
                  className="text-xs px-2 py-0.5 rounded"
                  style={{ color: "var(--text-muted)", background: "var(--bg-primary)" }}
                >
                  复制
                </button>
              )}
            </div>
          </div>
        </div>

        <Link
          href="/invite"
          className="inline-flex items-center gap-1 text-xs mt-3"
          style={{ color: "var(--accent)" }}
        >
          查看邀请记录 →
        </Link>
      </div>

      {/* 编辑资料 */}
      <form onSubmit={handleSaveProfile} className="card space-y-4">
        <h2 className="text-lg font-semibold">编辑资料</h2>

        <div>
          <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            昵称
          </label>
          <input
            type="text"
            className="input w-full"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>

        <hr style={{ borderColor: "var(--border)" }} />

        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          修改密码请填写以下字段，不修改则留空
        </p>

        <div>
          <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            当前密码
          </label>
          <input
            type="password"
            className="input w-full"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="输入当前密码"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            新密码
          </label>
          <input
            type="password"
            className="input w-full"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="至少 8 位"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            确认新密码
          </label>
          <input
            type="password"
            className="input w-full"
            value={confirmNewPassword}
            onChange={(e) => setConfirmNewPassword(e.target.value)}
            placeholder="再次输入新密码"
          />
        </div>

        {message && (
          <p
            className="text-sm"
            style={{ color: message.type === "ok" ? "var(--accent)" : "#ef4444" }}
          >
            {message.text}
          </p>
        )}

        <div className="flex gap-3">
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "保存中..." : "保存修改"}
          </button>
          <button type="button" onClick={handleLogout} className="btn-ghost" style={{ color: "#ef4444" }}>
            退出登录
          </button>
        </div>
      </form>

      {/* 点数记录 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">点数记录</h2>
        {pointsLog.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            暂无点数记录
          </p>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {pointsLog.map((log, i) => (
              <div
                key={i}
                className="flex items-center justify-between text-sm py-2"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <div>
                  <span>{String(log.reason || "")}</span>
                  {Boolean(log.detail) && (
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      {String(log.detail)}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className="font-mono"
                    style={{
                      color: Number(log.change) > 0 ? "var(--accent)" : "#ef4444",
                    }}
                  >
                    {Number(log.change) > 0 ? "+" : ""}
                    {String(log.change)}
                  </span>
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {log.created_at
                      ? new Date(String(log.created_at)).toLocaleString()
                      : ""}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 充值入口 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-3">充值点数</h2>
        <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
          充值点数永久有效，用完为止
        </p>
        <div className="grid grid-cols-3 gap-3">
          {[
            { tier: "basic", label: "Basic ¥10", points: "1800 点", color: "#22C55E" },
            { tier: "standard", label: "Standard ¥18", points: "5000 点", color: "#F59E0B" },
            { tier: "premium", label: "Premium ¥50", points: "30000 点", color: "#A855F7" },
          ].map((tier) => (
            <button
              key={tier.tier}
              onClick={async () => {
                const res = await apiFetch<{ pay_url: string; out_trade_no: string }>(
                  "/api/membership/create-order",
                  {
                    method: "POST",
                    body: JSON.stringify({ tier: tier.tier }),
                    headers: { Authorization: `Bearer ${token}` },
                  }
                );
                if (res.ok && res.data) {
                  window.open(res.data.pay_url, "_blank");
                }
              }}
              className="rounded-lg p-4 text-center transition-all hover:scale-105"
              style={{
                background: `${tier.color}15`,
                border: `1px solid ${tier.color}30`,
                cursor: "pointer",
              }}
            >
              <p className="text-sm font-semibold" style={{ color: tier.color }}>
                {tier.label}
              </p>
              <p className="text-lg font-bold mt-1">{tier.points}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
