"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

export default function CheckinButton() {
  const { user, token, refreshUser } = useAuth();
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const handleCheckin = async () => {
    if (checking) return;
    setChecking(true);
    setMessage(null);

    const res = await apiFetch<{
      earned: number;
      bonus: number;
      streak: number;
      free_points_today: number;
    }>("/api/points/checkin", {
      method: "POST",
      body: "{}",
      headers: { Authorization: `Bearer ${token}` },
    });

    setChecking(false);

    if (res.ok && res.data) {
      setMessage({
        ok: true,
        text: `签到成功！+${res.data.earned}点（连续${res.data.streak}天）`,
      });
      await refreshUser();
    } else if (res.error?.code === "ALREADY_CHECKED_IN") {
      setMessage({ ok: false, text: "今日已签到" });
    } else {
      setMessage({ ok: false, text: res.error?.message || "签到失败" });
    }
  };

  if (!user) return null;

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleCheckin}
        disabled={checking}
        className="btn-ghost text-xs px-3 py-1.5"
        style={{
          color: "var(--accent)",
          border: "1px solid rgba(34,197,94,0.3)",
        }}
      >
        {checking ? "签到中..." : "🔥 签到"}
      </button>
      {user.checkin_streak > 0 && (
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          连续 {user.checkin_streak} 天
        </span>
      )}
      {message && (
        <span
          className="text-xs"
          style={{
            color: message.ok ? "var(--accent)" : "#f59e0b",
          }}
        >
          {message.text}
        </span>
      )}
    </div>
  );
}
