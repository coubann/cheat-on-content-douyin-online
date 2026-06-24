"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface Trend {
  platform: string;
  topic: string;
  heat_level: string;
  description: string;
  related_keywords: string[];
  content_angle: string;
  competition_level: string;
}

interface Candidate {
  topic: string;
  source: string;
  priority: string;
  reasoning: string;
  suggested_angle: string;
}

const heatBadge: Record<string, string> = {
  super_hot: "badge-red",
  hot: "badge-yellow",
  warm: "badge-blue",
};

const heatLabels: Record<string, string> = {
  super_hot: "爆",
  hot: "热",
  warm: "温",
};

const heatColors: Record<string, string> = {
  super_hot: "#ef4444",
  hot: "#eab308",
  warm: "#3b82f6",
};

const platformLabels: Record<string, string> = {
  douyin: "抖音",
  xiaohongshu: "小红书",
  weibo: "微博",
  wechat: "微信",
};

const competitionLabels: Record<string, { label: string; color: string }> = {
  high: { label: "竞争激烈", color: "#ef4444" },
  medium: { label: "竞争适中", color: "#eab308" },
  low: { label: "蓝海机会", color: "#22c55e" },
};

export default function TrendsPage() {
  const [trends, setTrends] = useState<Trend[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [niche, setNiche] = useState("泛知识/观点输出");
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"trends" | "candidates">("trends");
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const fetchTrendsData = async () => {
    setLoading(true);
    setExpandedIndex(null);
    const res = await apiFetch<{ trends: Trend[] }>("/api/comments/trends?niche=" + encodeURIComponent(niche));
    if (res.ok && res.data) setTrends(res.data.trends);
    setLoading(false);
  };

  const fetchCandidates = async () => {
    setLoading(true);
    setExpandedIndex(null);
    const res = await apiFetch<{ candidates: Candidate[] }>("/api/comments/candidates/recommend?limit=5");
    if (res.ok && res.data) setCandidates(res.data.candidates);
    setLoading(false);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-glow">热点 & 选题</h1>
      <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
        多平台热点抓取 + 智能选题推荐
      </p>

      {/* Tab 切换 */}
      <div className="mt-6 flex gap-2">
        <button
          className={activeTab === "trends" ? "btn-primary" : "btn-ghost"}
          onClick={() => setActiveTab("trends")}
        >
          热点抓取
        </button>
        <button
          className={activeTab === "candidates" ? "btn-primary" : "btn-ghost"}
          onClick={() => setActiveTab("candidates")}
        >
          选题推荐
        </button>
      </div>

      {activeTab === "trends" && (
        <div className="mt-6">
          <div className="flex gap-3">
            <input
              className="input flex-1"
              placeholder="你的领域（如：泛知识/观点输出）"
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
            />
            <button
              className="btn-primary"
              onClick={fetchTrendsData}
              disabled={loading}
            >
              {loading ? "抓取中..." : "抓取热点"}
            </button>
          </div>

          <div className="mt-4 space-y-3">
            {trends.map((t, i) => {
              const isExpanded = expandedIndex === i;
              const comp = competitionLabels[t.competition_level] || { label: t.competition_level, color: "#888" };
              return (
                <div
                  key={i}
                  className="card cursor-pointer group transition-all"
                  style={{ borderColor: isExpanded ? "rgba(34,197,94,0.3)" : undefined }}
                  onClick={() => setExpandedIndex(isExpanded ? null : i)}
                >
                  {/* 标题行 */}
                  <div className="flex items-center gap-2">
                    <span className={`badge ${heatBadge[t.heat_level] || "badge-blue"}`}>
                      {heatLabels[t.heat_level] || t.heat_level}
                    </span>
                    <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e" }}>
                      {platformLabels[t.platform] || t.platform}
                    </span>
                    <span className="font-medium flex-1">{t.topic}</span>
                    <span className="text-xs" style={{ color: isExpanded ? "#22c55e" : "var(--text-muted)" }}>
                      {isExpanded ? "收起" : "展开详情"}
                    </span>
                  </div>

                  {/* 简短描述（始终可见） */}
                  <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>{t.description}</p>

                  {/* 展开详情 */}
                  {isExpanded && (
                    <div className="mt-4 space-y-4 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
                      {/* 切入角度 */}
                      <div className="rounded-lg p-3" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
                        <div className="text-xs font-semibold mb-1" style={{ color: "#22c55e" }}>建议切入角度</div>
                        <p className="text-sm" style={{ color: "var(--text-primary)" }}>{t.content_angle}</p>
                      </div>

                      {/* 竞争程度 */}
                      <div className="flex items-center gap-2">
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>竞争程度:</span>
                        <span className="text-xs font-medium" style={{ color: comp.color }}>{comp.label}</span>
                      </div>

                      {/* 相关关键词 */}
                      <div>
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>相关关键词</span>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {t.related_keywords.map((kw) => (
                            <span key={kw} className="px-2 py-0.5 rounded text-xs" style={{ background: "var(--bg-input)", color: "var(--text-secondary)" }}>
                              {kw}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {activeTab === "candidates" && (
        <div className="mt-6">
          <button
            className="btn-primary"
            onClick={fetchCandidates}
            disabled={loading}
          >
            {loading ? "推荐中..." : "获取推荐"}
          </button>

          <div className="mt-4 space-y-3">
            {candidates.map((c, i) => {
              const isExpanded = expandedIndex === i;
              const priorityColor = c.priority === "high" ? "#ef4444" : c.priority === "medium" ? "#eab308" : "#3b82f6";
              const priorityLabel = c.priority === "high" ? "高优先" : c.priority === "medium" ? "中优先" : "低优先";
              return (
                <div
                  key={i}
                  className="card cursor-pointer group transition-all"
                  style={{ borderColor: isExpanded ? "rgba(34,197,94,0.3)" : undefined }}
                  onClick={() => setExpandedIndex(isExpanded ? null : i)}
                >
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-xs font-bold" style={{ background: priorityColor, color: "#fff" }}>
                      {priorityLabel}
                    </span>
                    <span className="font-medium flex-1">{c.topic}</span>
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>来源: {c.source}</span>
                    <span className="text-xs" style={{ color: isExpanded ? "#22c55e" : "var(--text-muted)" }}>
                      {isExpanded ? "收起" : "展开"}
                    </span>
                  </div>

                  {isExpanded ? (
                    <div className="mt-4 space-y-3 pt-4" style={{ borderTop: "1px solid var(--border)" }}>
                      {/* 推荐理由 */}
                      <div className="rounded-lg p-3" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
                        <div className="text-xs font-semibold mb-1" style={{ color: "#22c55e" }}>推荐理由</div>
                        <p className="text-sm" style={{ color: "var(--text-primary)" }}>{c.reasoning}</p>
                      </div>

                      {/* 建议角度 */}
                      <div className="rounded-lg p-3" style={{ background: "rgba(59,130,246,0.06)", borderLeft: "3px solid #3b82f6" }}>
                        <div className="text-xs font-semibold mb-1" style={{ color: "#3b82f6" }}>建议切入角度</div>
                        <p className="text-sm" style={{ color: "var(--text-primary)" }}>{c.suggested_angle}</p>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-1 text-sm truncate" style={{ color: "var(--text-muted)" }}>{c.reasoning}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
