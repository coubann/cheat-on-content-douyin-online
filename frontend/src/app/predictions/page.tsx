"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

interface PredictionItem {
  prediction_id: string;
  script_id: string;
  pred_time: string;
  has_retro: boolean;
  virality_score: number | null;
  bucket: string;
  file_mtime: number;
}

interface PredictionDetail {
  prediction_id: string;
  content: string;
  prediction_hash: string;
  has_retro: boolean;
}

// 维度中文映射
const DIM_LABELS: Record<string, string> = {
  ER: "情感共鸣", HP: "钩子强度", QL: "金句密度", NA: "叙事性",
  AB: "受众广度", SR: "社会共振", SAT: "讽刺深度", TS: "分享冲动",
  MS: "模因传播", CC: "内容紧凑",
};

// 维度图标
const DIM_ICONS: Record<string, string> = {
  ER: "heart", HP: "hook", QL: "quote", NA: "story",
  AB: "users", SR: "wave", SAT: "irony", TS: "share",
  MS: "meme", CC: "compact",
};

// 解析预测 markdown 为结构化数据
function parsePrediction(content: string) {
  const lines = content.split("\n");

  // 基础信息
  let scriptId = "";
  let predTime = "";
  let viralityScore = 0;
  let compositeScore = 0;
  let bucket = "";
  let contentForm = "";
  let platforms = "";

  // 维度得分
  const dimensions: { key: string; label: string; score: number; confidence: number; reason: string }[] = [];

  // 子分
  const subScores: { key: string; value: number; contribution: number }[] = [];

  // 改稿建议
  const suggestions: { priority: string; dimension: string; action: string; impact: string }[] = [];

  // 风险/亮点
  const risks: string[] = [];
  const highlights: string[] = [];

  // 反事实
  const counterfactuals: string[] = [];

  // 复盘内容
  let retroContent = "";
  let inRetro = false;

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("## 复盘")) {
      inRetro = true;
      i++;
      continue;
    }
    if (inRetro) {
      retroContent += line + "\n";
      i++;
      continue;
    }

    // 脚本 ID
    if (line.startsWith("- 脚本 ID:")) {
      scriptId = line.split(":", 2)[1]?.trim() || "";
    }
    // 预测时间
    if (line.startsWith("- 预测时间:")) {
      predTime = line.split(":", 2)[1]?.trim() || "";
    }
    // 爆款分
    if (line.includes("爆款分")) {
      const m = line.match(/(\d+\.?\d*)\s*\/\s*100/);
      if (m) viralityScore = parseFloat(m[1]);
    }
    // 综合分
    if (line.includes("综合分")) {
      const m = line.match(/(\d+\.?\d*)\s*\/\s*10/);
      if (m) compositeScore = parseFloat(m[1]);
    }
    // Bucket
    if (line.includes("Bucket:")) {
      bucket = line.replace(/^.*Bucket:/, "").trim();
    }
    // 内容形态
    if (line.includes("内容形态:")) {
      contentForm = line.split(":", 2)[1]?.trim() || "";
    }
    // 目标平台
    if (line.includes("目标平台:")) {
      platforms = line.split(":", 2)[1]?.trim() || "";
    }

    // 维度表格解析
    if (line.startsWith("|") && line.includes("维度") && line.includes("分数")) {
      i++; // skip header
      i++; // skip separator
      while (i < lines.length && lines[i].startsWith("|") && !lines[i].includes("---")) {
        const cells = lines[i].split("|").map(c => c.trim()).filter(Boolean);
        if (cells.length >= 4) {
          const key = cells[0];
          const score = parseFloat(cells[1]) || 0;
          const conf = parseInt(cells[2]) || 0;
          const reason = cells[3] || "";
          if (DIM_LABELS[key]) {
            dimensions.push({ key, label: DIM_LABELS[key], score, confidence: conf, reason });
          }
        }
        i++;
      }
      continue;
    }

    // 子分表格解析
    if (line.startsWith("|") && line.includes("子分") && line.includes("值")) {
      i++; // skip header
      i++; // skip separator
      while (i < lines.length && lines[i].startsWith("|") && !lines[i].includes("---")) {
        const cells = lines[i].split("|").map(c => c.trim()).filter(Boolean);
        if (cells.length >= 3) {
          subScores.push({ key: cells[0], value: parseFloat(cells[1]) || 0, contribution: parseFloat(cells[2]) || 0 });
        }
        i++;
      }
      continue;
    }

    // 改稿建议
    if (line.startsWith("- [")) {
      const priorityMatch = line.match(/\[(HIGH|MEDIUM|LOW)\]/);
      const priority = priorityMatch ? priorityMatch[1] : "MEDIUM";
      // 提取维度: 格式 "DIM: xxx"
      const dimMatch = line.match(/\]\s*(\w+):/);
      const dimension = dimMatch ? dimMatch[1] : "";
      // 提取建议内容和预期影响
      const afterBracket = line.replace(/^.*\]\s*/, "");
      const impactMatch = afterBracket.match(/\(预期影响:\s*(.+?)\)/);
      const impact = impactMatch ? impactMatch[1] : "";
      // 提取建议正文（去掉预期影响部分）
      let action = afterBracket.replace(/\s*\(预期影响:.+?\)\s*$/, "").trim();
      // 去掉维度前缀
      if (action.startsWith(dimension + ":")) {
        action = action.slice(dimension.length + 1).trim();
      }
      suggestions.push({ priority, dimension, action, impact });
    }

    // 风险信号
    if (line.startsWith("**风险信号:**")) {
      i++;
      while (i < lines.length && lines[i].startsWith("- ")) {
        risks.push(lines[i].slice(2).trim());
        i++;
      }
      continue;
    }

    // 亮点
    if (line.startsWith("**亮点:**")) {
      i++;
      while (i < lines.length && lines[i].startsWith("- ")) {
        highlights.push(lines[i].slice(2).trim());
        i++;
      }
      continue;
    }

    // 反事实
    if (line.startsWith("- 如果最弱维度") || line.startsWith("- 如果钩子")) {
      counterfactuals.push(line.slice(2).trim());
    }

    i++;
  }

  return { scriptId, predTime, viralityScore, compositeScore, bucket, contentForm, platforms, dimensions, subScores, suggestions, risks, highlights, counterfactuals, retroContent };
}

// 环形进度条
function ScoreRing({ score, max, label, size = 120 }: { score: number; max: number; label: string; size?: number }) {
  const pct = Math.round((score / max) * 100);
  const r = (size - 12) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  const color = pct >= 70 ? "#22c55e" : pct >= 40 ? "#eab308" : "#ef4444";
  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1a1a2e" strokeWidth="6" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: "stroke-dashoffset 1s ease" }} />
        <text x={size / 2} y={size / 2 - 8} textAnchor="middle" fill={color} fontSize="28" fontWeight="bold">{score}</text>
        <text x={size / 2} y={size / 2 + 14} textAnchor="middle" fill="#888" fontSize="12">/{max}</text>
      </svg>
      <span className="text-sm font-medium mt-1" style={{ color }}>{label}</span>
    </div>
  );
}

// 维度进度条（带关联建议）
function DimBar({ label, score, confidence, reason, dimKey, suggestions, expandedDim, setExpandedDim }: {
  label: string; score: number; confidence: number; reason: string;
  dimKey: string; suggestions: { priority: string; dimension: string; action: string; impact: string }[];
  expandedDim: string | null; setExpandedDim: (d: string | null) => void;
}) {
  const pct = (score / 5) * 100;
  const color = score >= 4 ? "#22c55e" : score >= 2 ? "#eab308" : "#ef4444";
  const relatedSuggestions = suggestions.filter(s => s.dimension === dimKey);
  const isExpanded = expandedDim === dimKey;

  return (
    <div>
      <div
        className="flex items-center justify-between mb-1 cursor-pointer"
        onClick={() => setExpandedDim(isExpanded ? null : dimKey)}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{label}</span>
          {relatedSuggestions.length > 0 && (
            <span className="px-1.5 py-0.5 rounded text-xs" style={{
              background: score < 3 ? "rgba(239,68,68,0.15)" : "rgba(234,179,8,0.15)",
              color: score < 3 ? "#ef4444" : "#eab308",
              fontSize: "10px",
            }}>
              {relatedSuggestions.length}条建议
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>置信度 {confidence}%</span>
          <span className="text-sm font-bold" style={{ color }}>{score}/5</span>
        </div>
      </div>
      <div className="w-full h-2.5 rounded-full" style={{ background: "var(--bg-input)" }}>
        <div className="h-2.5 rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
      <p className="text-xs mt-1 leading-relaxed" style={{ color: "var(--text-muted)" }}>
        {reason}
      </p>
      {isExpanded && relatedSuggestions.length > 0 && (
        <div className="mt-2 space-y-2 pl-3 border-l-2" style={{ borderColor: color }}>
          {relatedSuggestions.map((s, i) => (
            <SuggestionCard key={i} priority={s.priority} dimension={s.dimension} action={s.action} impact={s.impact} compact />
          ))}
        </div>
      )}
    </div>
  );
}

// 改稿建议卡片
function SuggestionCard({ priority, dimension, action, impact, compact }: { priority: string; dimension: string; action: string; impact: string; compact?: boolean }) {
  const dimLabel = DIM_LABELS[dimension] || dimension;
  const priorityColor = priority === "HIGH" ? "#ef4444" : priority === "MEDIUM" ? "#eab308" : "#3b82f6";
  const priorityLabel = priority === "HIGH" ? "必须改" : priority === "MEDIUM" ? "建议改" : "可优化";

  if (compact) {
    return (
      <div className="rounded-lg p-3" style={{ background: "rgba(34,197,94,0.06)" }}>
        <div className="flex items-center gap-2 mb-1">
          <span className="px-1.5 py-0.5 rounded text-xs font-bold" style={{ background: priorityColor, color: "#fff", fontSize: "10px" }}>
            {priorityLabel}
          </span>
          <span className="text-xs" style={{ color: "#22c55e" }}>{dimLabel}</span>
        </div>
        <p className="text-xs leading-relaxed" style={{ color: "var(--text-primary)" }}>{action}</p>
        {impact && <p className="text-xs mt-1" style={{ color: "#22c55e" }}>&#x2191; {impact}</p>}
      </div>
    );
  }

  return (
    <div className="rounded-xl p-4 border-l-4" style={{
      background: "rgba(34, 197, 94, 0.06)",
      borderColor: priorityColor,
    }}>
      <div className="flex items-center gap-2 mb-2">
        <span className="px-2 py-0.5 rounded text-xs font-bold" style={{ background: priorityColor, color: "#fff" }}>
          {priorityLabel}
        </span>
        <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e" }}>
          {dimLabel}
        </span>
      </div>
      <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>{action}</p>
      {impact && (
        <div className="mt-2 flex items-center gap-1">
          <span className="text-xs" style={{ color: "#22c55e" }}>&#x2191;</span>
          <span className="text-xs" style={{ color: "#22c55e" }}>{impact}</span>
        </div>
      )}
    </div>
  );
}

export default function PredictionsPage() {
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<PredictionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [viewMode, setViewMode] = useState<"simple" | "detail">("simple");

  // 最优文案
  const [optimizedScript, setOptimizedScript] = useState<string>("");
  const [optimizeLoading, setOptimizeLoading] = useState(false);
  const [optimizeImprovements, setOptimizeImprovements] = useState<string[]>([]);
  const [optimizeBoost, setOptimizeBoost] = useState("");
  const [copied, setCopied] = useState(false);

  // 当前展开的维度
  const [expandedDim, setExpandedDim] = useState<string | null>(null);

  const loadPredictions = async () => {
    setLoading(true);
    const res = await apiFetch<{ predictions: PredictionItem[] }>("/api/predict/list");
    if (res.ok && res.data) {
      setPredictions(res.data.predictions);
    }
    setLoading(false);
  };

  const loadDetail = async (predictionId: string) => {
    setDetailLoading(true);
    setViewMode("simple");
    setOptimizedScript("");
    setOptimizeImprovements([]);
    setOptimizeBoost("");
    const res = await apiFetch<PredictionDetail>(`/api/predict/${predictionId}`);
    if (res.ok && res.data) {
      setDetail(res.data);
    }
    setDetailLoading(false);
  };

  const handleOptimize = async () => {
    if (!detail) return;
    setOptimizeLoading(true);
    setOptimizedScript("");
    const res = await apiFetch<{ optimized_script: string; improvements: string[]; estimated_score_boost: string }>(
      `/api/predict/${detail.prediction_id}/optimize`,
      { method: "POST" }
    );
    if (res.ok && res.data) {
      setOptimizedScript(res.data.optimized_script);
      setOptimizeImprovements(res.data.improvements || []);
      setOptimizeBoost(res.data.estimated_score_boost || "");
    }
    setOptimizeLoading(false);
  };

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  useEffect(() => {
    loadPredictions();
  }, []);

  // 详情视图
  if (detail) {
    const parsed = parsePrediction(detail.content);
    const title = parsed.scriptId.replace(/^\d{4}-\d{2}-\d{2}_[a-f0-9]+_/, "");

    return (
      <div>
        {/* 顶部导航 */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <button onClick={() => setDetail(null)} className="btn-ghost text-sm px-3 py-1">
              &larr; 返回列表
            </button>
            <h1 className="text-2xl font-bold text-glow">{title || "预测详情"}</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setViewMode("simple")}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${viewMode === "simple" ? "bg-green-500/20 text-green-400" : ""}`}
              style={viewMode !== "simple" ? { color: "var(--text-muted)" } : {}}
            >
              简明视图
            </button>
            <button
              onClick={() => setViewMode("detail")}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${viewMode === "detail" ? "bg-green-500/20 text-green-400" : ""}`}
              style={viewMode !== "detail" ? { color: "var(--text-muted)" } : {}}
            >
              专业视图
            </button>
          </div>
        </div>

        {viewMode === "simple" ? (
          /* ========== 简明视图 ========== */
          <div className="space-y-6">
            {/* 核心评分区 */}
            <div className="card" style={{ borderColor: "rgba(34,197,94,0.2)" }}>
              <div className="flex items-center justify-center gap-12 py-4">
                <ScoreRing score={parsed.viralityScore} max={100} label="爆款指数" size={140} />
                <ScoreRing score={parsed.compositeScore} max={10} label="综合评分" size={100} />
              </div>
              {/* 一句话结论 */}
              <div className="text-center mt-2">
                <span className="text-lg font-semibold" style={{
                  color: parsed.viralityScore >= 70 ? "#22c55e" : parsed.viralityScore >= 40 ? "#eab308" : "#ef4444"
                }}>
                  {parsed.viralityScore >= 70 ? "爆款潜力强" : parsed.viralityScore >= 40 ? "有潜力，需优化" : "爆款潜力弱，建议大改"}
                </span>
                <span className="ml-3 text-sm" style={{ color: "var(--text-muted)" }}>
                  预计播放量 {parsed.bucket || "—"}
                </span>
              </div>
            </div>

            {/* 维度速览 - 横向条形图（点击展开关联建议） */}
            <div className="card">
              <h2 className="text-lg font-semibold mb-4">各维度评分 <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>点击维度查看改稿建议</span></h2>
              <div className="grid grid-cols-2 gap-x-8 gap-y-4">
                {parsed.dimensions.map((d) => (
                  <DimBar key={d.key} label={d.label} score={d.score} confidence={d.confidence} reason={d.reason}
                    dimKey={d.key} suggestions={parsed.suggestions} expandedDim={expandedDim} setExpandedDim={setExpandedDim} />
                ))}
              </div>
            </div>

            {/* 改稿建议 - 绿色高亮卡片 */}
            <div>
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <span style={{ color: "#22c55e" }}>&#x270D;</span> 改稿建议
                <span className="text-xs font-normal" style={{ color: "var(--text-muted)" }}>
                  按优先级排列，改了就能提分
                </span>
              </h2>
              <div className="space-y-3">
                {parsed.suggestions.map((s, i) => (
                  <SuggestionCard key={i} priority={s.priority} dimension={s.dimension} action={s.action} impact={s.impact} />
                ))}
              </div>
              {parsed.suggestions.length === 0 && (
                <div className="card text-center py-8">
                  <p style={{ color: "var(--text-muted)" }}>暂无改稿建议</p>
                </div>
              )}
            </div>

            {/* 风险/亮点 */}
            {(parsed.risks.length > 0 || parsed.highlights.length > 0) && (
              <div className="grid grid-cols-2 gap-4">
                {parsed.risks.length > 0 && (
                  <div className="card" style={{ borderColor: "rgba(239,68,68,0.3)" }}>
                    <h3 className="text-sm font-semibold mb-3" style={{ color: "#ef4444" }}>&#x26A0; 风险信号</h3>
                    <ul className="space-y-2">
                      {parsed.risks.map((r, i) => (
                        <li key={i} className="text-sm" style={{ color: "var(--text-secondary)" }}>- {r}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {parsed.highlights.length > 0 && (
                  <div className="card" style={{ borderColor: "rgba(34,197,94,0.3)" }}>
                    <h3 className="text-sm font-semibold mb-3" style={{ color: "#22c55e" }}>&#x2713; 亮点</h3>
                    <ul className="space-y-2">
                      {parsed.highlights.map((h, i) => (
                        <li key={i} className="text-sm" style={{ color: "var(--text-secondary)" }}>+ {h}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* 提分潜力 */}
            {parsed.counterfactuals.length > 0 && (
              <div className="card" style={{ borderColor: "rgba(59,130,246,0.3)" }}>
                <h3 className="text-sm font-semibold mb-3" style={{ color: "#3b82f6" }}>&#x1F4C8; 提分潜力</h3>
                <div className="space-y-2">
                  {parsed.counterfactuals.map((c, i) => (
                    <p key={i} className="text-sm" style={{ color: "var(--text-secondary)" }}>{c}</p>
                  ))}
                </div>
              </div>
            )}

            {/* 最优文案 */}
            <div className="card" style={{ borderColor: "rgba(34,197,94,0.3)" }}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold" style={{ color: "#22c55e" }}>&#x2705; 最优文案</h2>
                {optimizedScript && (
                  <button
                    className="px-3 py-1 rounded text-xs font-medium"
                    style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e" }}
                    onClick={() => handleCopy(optimizedScript)}
                  >
                    {copied ? "已复制" : "复制文案"}
                  </button>
                )}
              </div>

              {!optimizedScript ? (
                <div className="text-center py-6">
                  <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
                    基于维度评分和改稿建议，AI 为你重写一份最优版本的文案
                  </p>
                  <button
                    className="btn-primary"
                    onClick={handleOptimize}
                    disabled={optimizeLoading}
                  >
                    {optimizeLoading ? "生成中..." : "生成最优文案"}
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {optimizeBoost && (
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-semibold" style={{ color: "#22c55e" }}>预计提分: {optimizeBoost}</span>
                    </div>
                  )}
                  <div className="rounded-xl p-5" style={{ background: "rgba(34,197,94,0.04)", border: "1px solid rgba(34,197,94,0.15)" }}>
                    <pre className="whitespace-pre-wrap text-sm leading-relaxed font-sans" style={{ color: "var(--text-primary)" }}>
                      {optimizedScript}
                    </pre>
                  </div>
                  {optimizeImprovements.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>改进要点</h3>
                      <div className="space-y-1">
                        {optimizeImprovements.map((imp, i) => (
                          <div key={i} className="flex items-start gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                            <span style={{ color: "#22c55e" }}>&#x2713;</span>
                            <span>{imp}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* ========== 专业视图 ========== */
          <div className="space-y-6">
            {/* 核心评分区（同简明） */}
            <div className="card" style={{ borderColor: "rgba(34,197,94,0.2)" }}>
              <div className="flex items-center justify-center gap-12 py-4">
                <ScoreRing score={parsed.viralityScore} max={100} label="爆款指数" size={140} />
                <ScoreRing score={parsed.compositeScore} max={10} label="综合评分" size={100} />
              </div>
              <div className="text-center mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
                预计播放量 {parsed.bucket || "—"} | 内容形态: {parsed.contentForm || "—"} | 平台: {parsed.platforms || "—"}
              </div>
            </div>

            {/* 维度得分详情表格 */}
            <div className="card">
              <h2 className="text-lg font-semibold mb-4">维度得分详情</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th className="text-left py-2 px-3" style={{ color: "var(--text-muted)" }}>维度</th>
                      <th className="text-center py-2 px-3" style={{ color: "var(--text-muted)" }}>分数</th>
                      <th className="text-center py-2 px-3" style={{ color: "var(--text-muted)" }}>置信度</th>
                      <th className="text-left py-2 px-3" style={{ color: "var(--text-muted)" }}>分析</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsed.dimensions.map((d) => (
                      <tr key={d.key} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td className="py-2 px-3">
                          <span className="font-medium">{d.label}</span>
                          <span className="ml-2 text-xs" style={{ color: "var(--text-muted)" }}>{d.key}</span>
                        </td>
                        <td className="text-center py-2 px-3">
                          <span className="font-bold" style={{ color: d.score >= 4 ? "#22c55e" : d.score >= 2 ? "#eab308" : "#ef4444" }}>
                            {d.score}
                          </span>/5
                        </td>
                        <td className="text-center py-2 px-3" style={{ color: "var(--text-secondary)" }}>{d.confidence}%</td>
                        <td className="py-2 px-3 text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>{d.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 爆款子分 */}
            {parsed.subScores.length > 0 && (
              <div className="card">
                <h2 className="text-lg font-semibold mb-4">爆款子分</h2>
                <div className="grid grid-cols-4 gap-4">
                  {parsed.subScores.map((s) => (
                    <div key={s.key} className="text-center p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                      <div className="text-2xl font-bold" style={{ color: "#22c55e" }}>
                        {(s.value * 100).toFixed(0)}%
                      </div>
                      <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{s.key}</div>
                      <div className="text-xs" style={{ color: "var(--text-muted)" }}>贡献 {s.contribution}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 改稿建议 */}
            <div>
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <span style={{ color: "#22c55e" }}>&#x270D;</span> 改稿建议
              </h2>
              <div className="space-y-3">
                {parsed.suggestions.map((s, i) => (
                  <SuggestionCard key={i} priority={s.priority} dimension={s.dimension} action={s.action} impact={s.impact} />
                ))}
              </div>
            </div>

            {/* 风险/亮点 */}
            {(parsed.risks.length > 0 || parsed.highlights.length > 0) && (
              <div className="grid grid-cols-2 gap-4">
                {parsed.risks.length > 0 && (
                  <div className="card" style={{ borderColor: "rgba(239,68,68,0.3)" }}>
                    <h3 className="text-sm font-semibold mb-3" style={{ color: "#ef4444" }}>风险信号</h3>
                    <ul className="space-y-2">
                      {parsed.risks.map((r, i) => <li key={i} className="text-sm" style={{ color: "var(--text-secondary)" }}>- {r}</li>)}
                    </ul>
                  </div>
                )}
                {parsed.highlights.length > 0 && (
                  <div className="card" style={{ borderColor: "rgba(34,197,94,0.3)" }}>
                    <h3 className="text-sm font-semibold mb-3" style={{ color: "#22c55e" }}>亮点</h3>
                    <ul className="space-y-2">
                      {parsed.highlights.map((h, i) => <li key={i} className="text-sm" style={{ color: "var(--text-secondary)" }}>+ {h}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* 反事实 + 校准假设 */}
            {parsed.counterfactuals.length > 0 && (
              <div className="card" style={{ borderColor: "rgba(59,130,246,0.3)" }}>
                <h3 className="text-sm font-semibold mb-3" style={{ color: "#3b82f6" }}>提分潜力（反事实推演）</h3>
                <div className="space-y-2">
                  {parsed.counterfactuals.map((c, i) => (
                    <p key={i} className="text-sm" style={{ color: "var(--text-secondary)" }}>{c}</p>
                  ))}
                </div>
              </div>
            )}

            {/* 复盘 */}
            {parsed.retroContent.trim() && (
              <div className="card" style={{ borderColor: "rgba(96,165,250,0.3)" }}>
                <h2 className="text-lg font-semibold mb-3" style={{ color: "#60a5fa" }}>&#x1F504; 复盘</h2>
                <div className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                  {parsed.retroContent.trim().split("\n").map((line, i) => {
                    if (line.startsWith("> ")) return <p key={i} className="text-xs italic" style={{ color: "var(--text-muted)" }}>{line.slice(2)}</p>;
                    if (line.startsWith("- ")) return <p key={i}>&#x2022; {line.slice(2)}</p>;
                    if (line.trim()) return <p key={i}>{line}</p>;
                    return null;
                  })}
                </div>
              </div>
            )}

            {/* 最优文案（专业视图也有） */}
            <div className="card" style={{ borderColor: "rgba(34,197,94,0.3)" }}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold" style={{ color: "#22c55e" }}>&#x2705; 最优文案</h2>
                {optimizedScript && (
                  <button
                    className="px-3 py-1 rounded text-xs font-medium"
                    style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e" }}
                    onClick={() => handleCopy(optimizedScript)}
                  >
                    {copied ? "已复制" : "复制文案"}
                  </button>
                )}
              </div>
              {!optimizedScript ? (
                <div className="text-center py-6">
                  <button className="btn-primary" onClick={handleOptimize} disabled={optimizeLoading}>
                    {optimizeLoading ? "生成中..." : "生成最优文案"}
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {optimizeBoost && (
                    <span className="text-sm font-semibold" style={{ color: "#22c55e" }}>预计提分: {optimizeBoost}</span>
                  )}
                  <div className="rounded-xl p-5" style={{ background: "rgba(34,197,94,0.04)", border: "1px solid rgba(34,197,94,0.15)" }}>
                    <pre className="whitespace-pre-wrap text-sm leading-relaxed font-sans" style={{ color: "var(--text-primary)" }}>
                      {optimizedScript}
                    </pre>
                  </div>
                  {optimizeImprovements.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>改进要点</h3>
                      <div className="space-y-1">
                        {optimizeImprovements.map((imp, i) => (
                          <div key={i} className="flex items-start gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                            <span style={{ color: "#22c55e" }}>&#x2713;</span>
                            <span>{imp}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  // 列表视图
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-glow">已预测</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            查看所有已完成的爆款预测结果
          </p>
        </div>
        <button
          onClick={loadPredictions}
          disabled={loading}
          className="btn-ghost text-sm px-3 py-1"
        >
          {loading ? "加载中..." : "刷新"}
        </button>
      </div>

      {loading ? (
        <div className="card text-center py-12">
          <p style={{ color: "var(--text-muted)" }}>加载中...</p>
        </div>
      ) : predictions.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-lg mb-2" style={{ color: "var(--text-muted)" }}>暂无预测记录</p>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            前往 <a href="/predict" className="underline" style={{ color: "#22c55e" }}>爆款预测</a> 对脚本进行预测
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {predictions.map((p) => {
            const title = p.script_id.replace(/^\d{4}-\d{2}-\d{2}_[a-f0-9]+_/, "");
            return (
              <div
                key={p.prediction_id}
                className="card group cursor-pointer transition-all hover:border-green-500/30"
                onClick={() => loadDetail(p.prediction_id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-5">
                    {/* 爆款分环形 */}
                    {p.virality_score !== null ? (
                      <div className="flex-shrink-0">
                        <svg width="56" height="56">
                          <circle cx="28" cy="28" r="22" fill="none" stroke="#1a1a2e" strokeWidth="4" />
                          <circle cx="28" cy="28" r="22" fill="none"
                            stroke={p.virality_score >= 70 ? "#22c55e" : p.virality_score >= 40 ? "#eab308" : "#ef4444"}
                            strokeWidth="4" strokeDasharray={2 * Math.PI * 22}
                            strokeDashoffset={2 * Math.PI * 22 * (1 - p.virality_score / 100)}
                            strokeLinecap="round" transform="rotate(-90 28 28)" />
                          <text x="28" y="33" textAnchor="middle" fill={p.virality_score >= 70 ? "#22c55e" : p.virality_score >= 40 ? "#eab308" : "#ef4444"} fontSize="14" fontWeight="bold">
                            {p.virality_score}
                          </text>
                        </svg>
                      </div>
                    ) : (
                      <div className="flex-shrink-0 w-14 h-14 flex items-center justify-center">
                        <span className="text-xl" style={{ color: "var(--text-muted)" }}>—</span>
                      </div>
                    )}

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-base">{title || p.script_id}</span>
                        {p.has_retro ? (
                          <span className="badge badge-green text-xs">已复盘</span>
                        ) : (
                          <span className="badge badge-yellow text-xs">待复盘</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                          {p.pred_time ? new Date(p.pred_time).toLocaleString("zh-CN") : new Date(p.file_mtime * 1000).toLocaleString("zh-CN")}
                        </span>
                        <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: "var(--bg-input)", color: "var(--text-muted)", fontSize: "10px" }}>
                          ID: {p.prediction_id.length > 25 ? p.prediction_id.slice(0, 25) + "..." : p.prediction_id}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {!p.has_retro && (
                      <a
                        href={`/publish?retro=${encodeURIComponent(p.prediction_id)}`}
                        className="px-3 py-1 rounded text-xs font-medium"
                        style={{ background: "rgba(234,179,8,0.15)", color: "#eab308" }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        去复盘
                      </a>
                    )}
                    <span className="text-sm opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: "#22c55e" }}>
                      查看详情 &rarr;
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
