"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

export default function InvitePage() {
  const router = useRouter();
  const { user, token } = useAuth();
  const [inviteCode, setInviteCode] = useState("");
  const [records, setRecords] = useState<Array<Record<string, unknown>>>([]);
  const [stats, setStats] = useState({ total_invited: 0, total_reward_points: 0 });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!token) {
      router.replace("/login");
      return;
    }
    loadData();
  }, [token]);

  const loadData = async () => {
    // 邀请码
    const codeRes = await apiFetch<{ invite_code: string }>("/api/invite/my-code", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (codeRes.ok && codeRes.data) {
      setInviteCode(codeRes.data.invite_code || "");
    }

    // 邀请记录
    const recordsRes = await apiFetch<{
      total_invited: number;
      total_reward_points: number;
      records: Array<Record<string, unknown>>;
    }>("/api/invite/records", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (recordsRes.ok && recordsRes.data) {
      setRecords(recordsRes.data.records);
      setStats({
        total_invited: recordsRes.data.total_invited,
        total_reward_points: recordsRes.data.total_reward_points,
      });
    }
  };

  const handleCopy = () => {
    if (inviteCode) {
      navigator.clipboard.writeText(inviteCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!user) {
    return <div className="py-20 text-center" style={{ color: "var(--text-secondary)" }}>加载中...</div>;
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold">
        <span className="text-glow">邀请好友</span>
      </h1>

      {/* 邀请码卡片 */}
      <div className="card text-center py-8">
        <p className="text-sm mb-2" style={{ color: "var(--text-secondary)" }}>
          你的专属邀请码
        </p>
        <div className="flex items-center justify-center gap-3 mb-4">
          <code
            className="text-3xl font-bold tracking-widest"
            style={{ color: "var(--accent)", fontFamily: "monospace" }}
          >
            {inviteCode || "—"}
          </code>
          {inviteCode && (
            <button
              onClick={handleCopy}
              className="text-xs px-3 py-1.5 rounded"
              style={{
                color: copied ? "var(--accent)" : "var(--text-muted)",
                background: "var(--bg-primary)",
              }}
            >
              {copied ? "已复制 ✓" : "复制"}
            </button>
          )}
        </div>
        <div className="flex items-center justify-center gap-6 text-sm">
          <div>
            <p className="text-lg font-semibold" style={{ color: "var(--accent)" }}>
              {stats.total_invited}
            </p>
            <p style={{ color: "var(--text-muted)" }}>已邀请</p>
          </div>
          <div className="w-px h-10" style={{ background: "var(--border)" }} />
          <div>
            <p className="text-lg font-semibold">{stats.total_reward_points}</p>
            <p style={{ color: "var(--text-muted)" }}>获得奖励</p>
          </div>
        </div>
      </div>

      {/* 奖励说明 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-3">奖励规则</h2>
        <div className="space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          <div className="flex items-center gap-2">
            <span className="text-lg">🎁</span>
            <span>邀请好友注册，你和好友各得 <strong style={{ color: "var(--accent)" }}>100 点</strong></span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-lg">📋</span>
            <span>每人最多邀请 <strong>10 人</strong></span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-lg">💡</span>
            <span>注册时填入邀请码即可绑定邀请关系</span>
          </div>
        </div>
      </div>

      {/* 邀请记录 */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-3">邀请记录</h2>
        {records.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            暂无邀请记录
          </p>
        ) : (
          <div className="space-y-2">
            {records.map((r) => (
              <div
                key={r.id as number}
                className="flex items-center justify-between py-2 text-sm"
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {r.invitee_email as string}
                  </span>
                </div>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {r.created_at ? new Date(String(r.created_at)).toLocaleDateString() : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
