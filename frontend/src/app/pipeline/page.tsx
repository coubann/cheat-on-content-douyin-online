"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import type { PipelineItem, PipelineData } from "@/lib/api-types";

const STAGES = ["candidate", "script", "prediction", "publish", "retro"] as const;
const STAGE_LABELS: Record<string, string> = {
  candidate: "选题",
  script: "脚本",
  prediction: "预测",
  publish: "发布",
  retro: "复盘",
};
const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  predicted: "已预测",
  published: "已发布",
  completed: "已完成",
};
const STATUS_COLORS: Record<string, string> = {
  draft: "#888888",
  predicted: "#3b82f6",
  published: "#eab308",
  completed: "#22c55e",
};

function StageFlow({ item }: { item: PipelineItem }) {
  return (
    <div className="flex items-center gap-1">
      {STAGES.map((stage, i) => {
        const isDone = item.stages[stage] !== null;
        return (
          <div key={stage} className="flex items-center gap-1">
            <div className="flex flex-col items-center">
              <div
                className="flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold"
                style={{
                  background: isDone ? "#22c55e" : "var(--bg-input)",
                  color: isDone ? "#000" : "var(--text-muted)",
                }}
              >
                {isDone ? "✓" : i + 1}
              </div>
              <span className="mt-1 text-xs" style={{ color: isDone ? "#22c55e" : "var(--text-muted)" }}>
                {STAGE_LABELS[stage]}
              </span>
            </div>
            {i < STAGES.length - 1 && (
              <div
                className="h-0.5 w-4 mt-[-12px]"
                style={{ background: isDone ? "#22c55e" : "var(--border)" }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function PipelinePage() {
  const [data, setData] = useState<PipelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<string>("all");

  const loadData = async () => {
    setLoading(true);
    setError("");
    const res = await apiFetch<PipelineData>("/api/pipeline");
    if (res.ok && res.data) {
      setData(res.data);
    } else {
      setError(res.error?.message || "加载失败");
    }
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  const filtered = data?.pipelines.filter(
    (p) => filter === "all" || p.status === filter,
  ) || [];

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-glow">全链路追踪</h1>
          <p className="mt-1" style={{ color: "var(--text-secondary)" }}>
            从选题到复盘的完整内容生命周期
          </p>
        </div>
        <button className="btn-ghost text-sm" onClick={loadData}>
          刷新
        </button>
      </div>

      {/* 统计概览 */}
      {data && (
        <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          <div className="card text-center">
            <div className="text-2xl font-bold" style={{ color: "#22c55e" }}>{data.stats.total}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>总计</div>
          </div>
          {Object.entries(data.stats.by_status).map(([status, count]) => (
            <div key={status} className="card text-center">
              <div className="text-2xl font-bold" style={{ color: STATUS_COLORS[status] || "#888" }}>
                {count}
              </div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>{STATUS_LABELS[status] || status}</div>
            </div>
          ))}
        </div>
      )}

      {/* 状态筛选 */}
      <div className="mt-6 flex gap-2 flex-wrap">
        {["all", "draft", "predicted", "published", "completed"].map((s) => (
          <button
            key={s}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
              filter === s ? "text-black" : ""
            }`}
            style={{
              background: filter === s ? "#22c55e" : "var(--bg-input)",
              color: filter === s ? "#000" : "var(--text-secondary)",
              border: filter === s ? "none" : "1px solid var(--border)",
            }}
            onClick={() => setFilter(s)}
          >
            {s === "all" ? "全部" : STATUS_LABELS[s] || s}
          </button>
        ))}
      </div>

      {/* 加载状态 */}
      {loading && (
        <div className="mt-8 text-center" style={{ color: "var(--text-muted)" }}>
          加载中...
        </div>
      )}

      {/* 错误提示 */}
      {error && !loading && (
        <div className="mt-6 rounded-lg p-4" style={{ border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.1)" }}>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Pipeline 列表 */}
      <div className="mt-6 space-y-4">
        {filtered.length === 0 && !loading && (
          <p style={{ color: "var(--text-muted)" }}>暂无链路数据</p>
        )}
        {filtered.map((item) => (
          <div key={item.id} className="card">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-semibold">{item.title || item.id}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className="badge"
                    style={{
                      background: `${STATUS_COLORS[item.status]}20`,
                      color: STATUS_COLORS[item.status],
                    }}
                  >
                    {STATUS_LABELS[item.status]}
                  </span>
                  {item.experiment && (
                    <span className="badge badge-blue">
                      A/B: {item.experiment.topic}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* 阶段流程 */}
            <div className="overflow-x-auto py-2">
              <StageFlow item={item} />
            </div>

            {/* 时间线 */}
            {item.timeline.length > 0 && (
              <div className="mt-4 border-t pt-4" style={{ borderColor: "var(--border)" }}>
                <h4 className="text-sm font-medium mb-2" style={{ color: "var(--text-secondary)" }}>时间线</h4>
                <div className="space-y-2">
                  {item.timeline.map((evt, i) => (
                    <div key={i} className="flex items-center gap-3 text-sm">
                      <div
                        className="h-2 w-2 rounded-full flex-shrink-0"
                        style={{ background: "#22c55e" }}
                      />
                      <span style={{ color: "var(--text-muted)" }}>
                        {new Date(evt.time).toLocaleString("zh-CN")}
                      </span>
                      <span className="font-medium">{STAGE_LABELS[evt.stage] || evt.stage}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </main>
  );
}
