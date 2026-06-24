"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface TopicRecommendation {
  title: string;
  core_angle: string;
  estimated_dimensions: Record<string, number>;
  estimated_composite: number;
  tier: number;
  reason: string;
  hook_suggestion: string;
  risk: string;
}

interface SeedResult {
  status: string;
  recommendations: {
    topics: TopicRecommendation[];
    strategy_used: string;
    cold_start_tips: string[];
  };
  signals_used: string[];
}

const DIM_LABELS: Record<string, string> = {
  ER: "情感共鸣", HP: "钩子强度", QL: "金句密度", NA: "叙事性",
  AB: "受众广度", SR: "社会共振", SAT: "讽刺深度", TS: "分享冲动",
  MS: "模因传播", CC: "内容紧凑",
};

export default function SeedPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SeedResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [strategy, setStrategy] = useState("balanced");
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const handleRecommend = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setExpandedIndex(null);

    const res = await apiFetch<SeedResult>(
      `/api/seed/recommend?count=5&strategy=${strategy}`,
      { method: "POST" },
    );

    if (res.ok && res.data) {
      setResult(res.data);
    } else {
      setError(res.error?.message || "推荐失败");
    }
    setLoading(false);
  };

  const tierBadge = (tier: number) => {
    if (tier === 1) return { cls: "badge-green", label: "Tier 1 强烈推荐", color: "#22c55e" };
    if (tier === 2) return { cls: "badge-yellow", label: "Tier 2 值得尝试", color: "#eab308" };
    return { cls: "badge-blue", label: "Tier 3 可探索", color: "#3b82f6" };
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-glow">智能选题推荐</h1>
      <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
        融合热点 + 评论 + 对标 + 受众画像的多源信号推荐
      </p>

      <div className="mt-6 flex items-center gap-4">
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          className="select"
        >
          <option value="balanced">平衡策略</option>
          <option value="safe">稳妥策略</option>
          <option value="experimental">实验策略</option>
        </select>
        <button
          onClick={handleRecommend}
          disabled={loading}
          className="btn-primary"
        >
          {loading ? "推荐中..." : "获取推荐"}
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-lg p-4" style={{ border: "1px solid rgba(239, 68, 68, 0.3)", background: "rgba(239, 68, 68, 0.1)", color: "#ef4444" }}>
          {error}
        </div>
      )}

      {result && (
        <div className="mt-6 space-y-6">
          <div className="flex gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
            <span>策略: {result.recommendations.strategy_used}</span>
            <span>|</span>
            <span>信号源: {result.signals_used.join(", ")}</span>
          </div>

          <div className="space-y-3">
            {result.recommendations.topics.map((topic, idx) => {
              const isExpanded = expandedIndex === idx;
              const tier = tierBadge(topic.tier);
              const dims = topic.estimated_dimensions || {};
              return (
                <div
                  key={idx}
                  className="card cursor-pointer transition-all"
                  style={{ borderColor: isExpanded ? "rgba(34,197,94,0.3)" : undefined }}
                  onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                >
                  {/* 标题行 */}
                  <div className="flex items-center gap-3">
                    <span className={`badge ${tier.cls}`}>Tier {topic.tier}</span>
                    <h3 className="font-semibold flex-1">{topic.title}</h3>
                    <span className="text-sm" style={{ color: tier.color }}>
                      预估 {topic.estimated_composite}/10
                    </span>
                    <span className="text-xs" style={{ color: isExpanded ? "#22c55e" : "var(--text-muted)" }}>
                      {isExpanded ? "收起" : "展开详情"}
                    </span>
                  </div>

                  {/* 简要（始终可见） */}
                  <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>{topic.core_angle}</p>

                  {/* 展开详情 */}
                  {isExpanded && (
                    <div className="mt-4 space-y-4 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
                      {/* 推荐理由 */}
                      <div className="rounded-lg p-3" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
                        <div className="text-xs font-semibold mb-1" style={{ color: "#22c55e" }}>推荐理由</div>
                        <p className="text-sm" style={{ color: "var(--text-primary)" }}>{topic.reason}</p>
                      </div>

                      {/* 钩子建议 */}
                      <div className="rounded-lg p-3" style={{ background: "rgba(59,130,246,0.06)", borderLeft: "3px solid #3b82f6" }}>
                        <div className="text-xs font-semibold mb-1" style={{ color: "#3b82f6" }}>开头钩子建议</div>
                        <p className="text-sm" style={{ color: "var(--text-primary)" }}>{topic.hook_suggestion}</p>
                      </div>

                      {/* 风险 */}
                      {topic.risk && (
                        <div className="rounded-lg p-3" style={{ background: "rgba(239,68,68,0.06)", borderLeft: "3px solid #ef4444" }}>
                          <div className="text-xs font-semibold mb-1" style={{ color: "#ef4444" }}>潜在风险</div>
                          <p className="text-sm" style={{ color: "var(--text-primary)" }}>{topic.risk}</p>
                        </div>
                      )}

                      {/* 预估维度分 */}
                      {Object.keys(dims).length > 0 && (
                        <div>
                          <div className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>预估维度分</div>
                          <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                            {Object.entries(dims).map(([key, val]) => (
                              <div key={key} className="flex items-center gap-2">
                                <span className="text-xs w-16" style={{ color: "var(--text-muted)" }}>{DIM_LABELS[key] || key}</span>
                                <div className="flex-1 h-1.5 rounded-full" style={{ background: "var(--bg-input)" }}>
                                  <div className="h-1.5 rounded-full" style={{
                                    width: `${(val / 5) * 100}%`,
                                    background: val >= 4 ? "#22c55e" : val >= 2 ? "#eab308" : "#ef4444",
                                  }} />
                                </div>
                                <span className="text-xs font-medium" style={{
                                  color: val >= 4 ? "#22c55e" : val >= 2 ? "#eab308" : "#ef4444"
                                }}>{val}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {result.recommendations.cold_start_tips.length > 0 && (
            <div className="card" style={{ borderColor: "rgba(234, 179, 8, 0.3)", background: "rgba(234, 179, 8, 0.08)" }}>
              <h3 className="font-semibold" style={{ color: "#eab308" }}>冷启动建议</h3>
              <ul className="mt-2 list-inside list-disc text-sm" style={{ color: "#eab308" }}>
                {result.recommendations.cold_start_tips.map((tip, idx) => (
                  <li key={idx}>{tip}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
