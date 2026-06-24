"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

interface StatusData {
  initialized: boolean;
  rubric_version: string;
  content_form: string;
  platforms: string[];
  calibration_samples: number;
  confidence_level: string;
  buffer_color: string;
  pending_retros: number;
  shoots_in_buffer: number;
  bump_suggested: boolean;
  bump_trigger_type: string | null;
  bump_trigger_reason: string;
  rubric_weights: Record<string, number>;
}

interface TodayData {
  todos: Array<{
    priority: number;
    action: string;
    endpoint: string;
  }>;
}

function BufferIndicator({ color }: { color: string }) {
  const colors: Record<string, string> = {
    red: "#ef4444",
    orange: "#f97316",
    green: "#22c55e",
    blue: "#3b82f6",
  };
  const labels: Record<string, string> = {
    red: "不足 (<1天)",
    orange: "紧张 (1-2天)",
    green: "充足 (3-5天)",
    blue: "充裕 (>5天)",
  };

  return (
    <div className="flex items-center gap-3">
      <div className="h-4 w-4 rounded-full" style={{ background: colors[color] || "#555" }} />
      <span className="text-sm">{labels[color] || color}</span>
    </div>
  );
}

function ConfidenceIndicator({ level }: { level: string }) {
  const labels: Record<string, string> = {
    none: "无数据",
    low: "低 (1-2样本)",
    medium: "中 (3-4样本)",
    high: "高 (5+样本)",
  };
  const colors: Record<string, string> = {
    none: "var(--text-muted)",
    low: "#ef4444",
    medium: "#eab308",
    high: "#22c55e",
  };

  return (
    <span className="font-medium" style={{ color: colors[level] || "var(--text-muted)" }}>
      {labels[level] || level}
    </span>
  );
}

export default function StatusPage() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [today, setToday] = useState<TodayData | null>(null);
  const [loading, setLoading] = useState(false);

  const loadStatus = async () => {
    setLoading(true);
    const [statusRes, todayRes] = await Promise.all([
      apiFetch<StatusData>("/api/status"),
      apiFetch<TodayData>("/api/status/today"),
    ]);
    if (statusRes.ok && statusRes.data) setStatus(statusRes.data);
    if (todayRes.ok && todayRes.data) setToday(todayRes.data);
    setLoading(false);
  };

  useEffect(() => {
    loadStatus();
  }, []);

  if (loading && !status) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8">
        <p style={{ color: "var(--text-muted)" }}>加载中...</p>
      </main>
    );
  }

  if (!status || !status.initialized) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8">
        <h1 className="text-2xl font-bold text-glow">状态看板</h1>
        <p className="mt-4" style={{ color: "var(--text-muted)" }}>
          项目未初始化，请先{" "}
          <a href="/api/init" style={{ color: "#22c55e", textDecoration: "underline" }}>
            初始化项目
          </a>
        </p>
        <button
          className="btn-primary mt-4"
          onClick={async () => {
            await apiFetch("/api/init", {
              method: "POST",
              body: JSON.stringify({ platforms: ["douyin"] }),
            });
            loadStatus();
          }}
        >
          一键初始化
        </button>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-bold text-glow">状态看板</h1>

      <div className="mt-6 grid gap-6 md:grid-cols-3">
        {/* Buffer */}
        <div className="card">
          <h2 className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>Buffer</h2>
          <div className="mt-2">
            <BufferIndicator color={status.buffer_color} />
          </div>
          <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            {status.shoots_in_buffer} 篇待发
          </p>
        </div>

        {/* Confidence */}
        <div className="card">
          <h2 className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>Confidence</h2>
          <div className="mt-2">
            <ConfidenceIndicator level={status.confidence_level} />
          </div>
          <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            {status.calibration_samples} 校准样本
          </p>
        </div>

        {/* Rubric */}
        <div className="card">
          <h2 className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>Rubric</h2>
          <div className="mt-2 text-lg font-bold">{status.rubric_version}</div>
          <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            {status.content_form} | {status.platforms.join(", ")}
          </p>
          {status.bump_suggested && (
            <div className="mt-2 rounded px-2 py-1 text-xs" style={{ background: "rgba(234,179,8,0.2)", color: "#eab308" }}>
              建议升级 rubric — {status.bump_trigger_type ? `${status.bump_trigger_type}: ` : ""}{status.bump_trigger_reason}
            </div>
          )}
        </div>
      </div>

      {/* Rubric 权重 */}
      <div className="card mt-6">
        <h2 className="mb-4 text-lg font-semibold">Rubric 权重</h2>
        <div className="grid grid-cols-5 gap-4">
          {Object.entries(status.rubric_weights).map(([dim, weight]) => (
            <div key={dim} className="text-center">
              <div className="text-lg font-bold">{dim}</div>
              <div className="text-sm" style={{ color: "var(--text-muted)" }}>{weight}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 今日 todo */}
      {today && today.todos.length > 0 && (
        <div className="card mt-6">
          <h2 className="mb-4 text-lg font-semibold">今日待办</h2>
          <div className="space-y-2">
            {today.todos.map((todo, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-lg p-3"
                style={{ background: "var(--bg-input)" }}
              >
                <span className="badge-blue badge flex h-6 w-6 items-center justify-center text-xs font-medium">
                  {todo.priority}
                </span>
                <span className="text-sm">{todo.action}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pending retros */}
      {status.pending_retros > 0 && (
        <div className="mt-4 rounded-lg p-4" style={{ background: "rgba(249, 115, 22, 0.1)", border: "1px solid rgba(249, 115, 22, 0.3)" }}>
          <p className="text-sm" style={{ color: "#f97316" }}>
            有 {status.pending_retros} 篇待复盘内容
          </p>
        </div>
      )}

      <button
        className="btn-ghost mt-6 text-sm"
        onClick={loadStatus}
      >
        刷新
      </button>
    </main>
  );
}
