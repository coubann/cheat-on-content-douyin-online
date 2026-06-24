"use client";

import { useState } from "react";
import { apiFetch, sseFetch } from "@/lib/api";

interface BumpResult {
  status: "accepted" | "rejected";
  reason?: string;
  consistency: number;
  old_version: string;
  new_version?: string;
  old_weights: Record<string, number>;
  new_weights?: Record<string, number>;
  rubric_diff?: string;
  pool_size?: number;
  rescored?: Array<{
    script_id: string;
    old_composite: number;
    new_composite: number;
    actual_plays: number;
  }>;
}

const DIM_LABELS: Record<string, string> = {
  ER: "情感共鸣",
  HP: "钩子强度",
  QL: "金句密度",
  NA: "叙事性",
  AB: "受众广度",
  SR: "社会共振",
  SAT: "讽刺深度",
  TS: "分享冲动",
  MS: "模因可传播",
  CC: "内容紧凑度",
};

export default function BumpPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BumpResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [currentPhase, setCurrentPhase] = useState("");

  const handleBump = async (force = false) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setProgress(0);
    setCurrentPhase("");

    try {
      const result = await sseFetch("/api/sse/bump", { force }, (event) => {
        setProgress(event.progress);
        setCurrentPhase(event.phase);
      });
      setResult(result as BumpResult);
    } catch (err) {
      // Fallback to regular endpoint
      try {
        const res = await apiFetch<BumpResult>(
          `/api/bump${force ? "?force=true" : ""}`,
          { method: "POST" },
        );
        if (res.ok && res.data) {
          setResult(res.data);
        }
      } catch (fallbackErr) {
        setError("升级失败: " + String(fallbackErr));
      }
    }
    setLoading(false);
  };

  const dims = Object.keys(DIM_LABELS);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-3xl font-bold text-glow">Rubric 升级 (Bump)</h1>
      <p className="mt-2" style={{ color: "var(--text-secondary)" }}>
        基于校准池数据，LLM 提议新权重 → blind 全量重打 → 排序一致性审计 → 写入
      </p>

      <div className="mt-6 flex gap-4">
        <button
          onClick={() => handleBump(false)}
          disabled={loading}
          className="btn-primary"
        >
          {loading ? "执行中..." : "执行 Bump"}
        </button>
        <button
          onClick={() => handleBump(true)}
          disabled={loading}
          className="btn-ghost"
          style={{ borderColor: "#f97316", color: "#f97316" }}
        >
          强制 Bump
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-lg p-4" style={{ border: "1px solid rgba(239, 68, 68, 0.3)", background: "rgba(239, 68, 68, 0.1)", color: "#ef4444" }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="mt-4 rounded-lg p-4" style={{ background: "rgba(34,197,94,0.06)" }}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm" style={{ color: "#22c55e" }}>
              {currentPhase === "collecting_pool" ? "收集校准池..." :
               currentPhase === "proposing_weights" ? "生成新权重..." :
               currentPhase === "rescoring_pool" ? "重打分校准池..." :
               currentPhase === "consistency_audit" ? "一致性审计..." :
               "处理中..."}
            </span>
            <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>{progress}%</span>
          </div>
          <div className="w-full h-2 rounded-full" style={{ background: "var(--bg-input)" }}>
            <div
              className="h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%`, background: "#22c55e" }}
            />
          </div>
        </div>
      )}

      {result && (
        <div className="mt-6 space-y-6">
          {/* 状态 */}
          <div
            className="card"
            style={{
              borderColor: result.status === "accepted" ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)",
              background: result.status === "accepted" ? "rgba(34, 197, 94, 0.08)" : "rgba(239, 68, 68, 0.08)",
            }}
          >
            <h2 className="text-xl font-bold">
              {result.status === "accepted" ? "升级通过" : "升级被拒"}
            </h2>
            {result.status === "rejected" && (
              <p className="mt-1" style={{ color: "#ef4444" }}>{result.reason}</p>
            )}
            {result.status === "accepted" && (
              <p className="mt-1" style={{ color: "#22c55e" }}>
                {result.old_version} → {result.new_version}
              </p>
            )}
          </div>

          {/* 一致性 */}
          <div className="card">
            <h3 className="font-semibold">排序一致性</h3>
            <div className="mt-2 flex items-center gap-4">
              <div className="text-4xl font-bold">
                {result.consistency.toFixed(2)}
              </div>
              <div className="flex-1">
                <div className="h-4 rounded-full" style={{ background: "var(--bg-input)" }}>
                  <div
                    className="h-4 rounded-full"
                    style={{
                      width: `${Math.min(100, result.consistency * 100)}%`,
                      background: result.consistency >= 0.8
                        ? "#22c55e"
                        : result.consistency >= 0.6
                          ? "#eab308"
                          : "#ef4444",
                    }}
                  />
                </div>
                <div className="mt-1 flex justify-between text-xs" style={{ color: "var(--text-muted)" }}>
                  <span>0</span>
                  <span className="font-medium" style={{ color: "#22c55e" }}>
                    阈值 0.80
                  </span>
                  <span>1.0</span>
                </div>
              </div>
            </div>
          </div>

          {/* 权重对比 */}
          <div className="card">
            <h3 className="font-semibold">权重对比</h3>
            <div className="mt-3 space-y-2">
              {dims.map((dim) => {
                const oldW = result.old_weights[dim] || 1;
                const newW = result.new_weights?.[dim] || oldW;
                const diff = newW - oldW;
                return (
                  <div key={dim} className="flex items-center gap-3">
                    <span className="w-24 text-sm font-medium">
                      {dim} ({DIM_LABELS[dim]})
                    </span>
                    <span className="w-12 text-right text-sm" style={{ color: "var(--text-muted)" }}>
                      {oldW}
                    </span>
                    <span style={{ color: "var(--text-muted)" }}>→</span>
                    <span className="w-12 text-sm font-semibold">{newW}</span>
                    <span
                      className="text-sm"
                      style={{
                        color: diff > 0 ? "#22c55e" : diff < 0 ? "#ef4444" : "var(--text-muted)",
                      }}
                    >
                      {diff > 0 ? `+${diff}` : diff < 0 ? `${diff}` : "="}
                    </span>
                    <div className="flex-1">
                      <div className="h-2 rounded-full" style={{ background: "var(--bg-input)" }}>
                        <div
                          className="h-2 rounded-full"
                          style={{ width: `${(newW / 3) * 100}%`, background: "#22c55e" }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 重打分结果 */}
          {result.rescored && result.rescored.length > 0 && (
            <div className="card">
              <h3 className="font-semibold">
                校准池重打分 ({result.rescored.length} 篇)
              </h3>
              <table className="mt-3 w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                    <th className="pb-2 text-left">Script ID</th>
                    <th className="pb-2 text-left">旧综合分</th>
                    <th className="pb-2 text-left">新综合分</th>
                    <th className="pb-2 text-left">实际播放</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rescored.map((r) => (
                    <tr key={r.script_id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td className="py-2">{r.script_id}</td>
                      <td className="py-2">{r.old_composite}</td>
                      <td className="py-2 font-semibold">{r.new_composite}</td>
                      <td className="py-2">{r.actual_plays}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Rubric 修订 */}
          {result.rubric_diff && (
            <div className="card">
              <h3 className="font-semibold">Rubric 修订内容</h3>
              <pre className="mt-2 whitespace-pre-wrap text-sm" style={{ color: "var(--text-secondary)" }}>
                {result.rubric_diff}
              </pre>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
