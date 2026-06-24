"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch, sseFetch } from "@/lib/api";

interface DimensionScore {
  dimension: string;
  score: number;
  confidence: number;
  reason: string;
  self_check: string;
}

interface ScoreResult {
  dimensions: DimensionScore[];
  composite: number;
  rubric_version: string;
}

interface ViralityResult {
  virality_score: number;
  breakdown: Record<string, number>;
  sub_scores: Record<string, number>;
  diagnosis: {
    strongest_dimension: { dimension: string; score: number };
    weakest_dimension: { dimension: string; score: number };
    risks: string[];
    highlights: string[];
    composite: number;
  };
  suggestions: Array<{
    priority: string;
    target_dimension: string;
    action: string;
    expected_impact: string;
  }>;
  bucket: { scheme: string; prediction: string; samples: number };
  phase: string;
}

interface Script {
  id: string;
  title: string;
  created_at: string;
}

const DIMENSION_LABELS: Record<string, string> = {
  ER: "情感共鸣",
  HP: "钩子强度",
  QL: "金句密度",
  NA: "叙事性",
  AB: "受众广度",
  SR: "社会共振",
  SAT: "讽刺深度",
  TS: "分享冲动",
  MS: "模因传播",
  CC: "内容紧凑",
};

// 预测步骤定义
const PREDICT_STEPS = [
  { key: "read", label: "读取脚本" },
  { key: "score", label: "盲打分" },
  { key: "virality", label: "爆款预测" },
  { key: "write", label: "落盘写入" },
  { key: "complete", label: "完成" },
];

// SSE phase → step index mapping
const PHASE_TO_STEP: Record<string, number> = {
  reading_script: 0,
  blind_scoring: 1,
  virality_predict: 2,
  writing_prediction: 3,
  complete: 4,
};

function StepProgress({ currentStep, totalSteps }: { currentStep: number; totalSteps: number }) {
  const pct = Math.round(((currentStep + 1) / totalSteps) * 100);
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium" style={{ color: "#22c55e" }}>
          {PREDICT_STEPS[currentStep]?.label || "完成"}
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>{pct}%</span>
      </div>
      <div className="w-full h-2 rounded-full" style={{ background: "var(--bg-input)" }}>
        <div
          className="h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: "#22c55e" }}
        />
      </div>
      <div className="flex mt-2 gap-1">
        {PREDICT_STEPS.map((s, i) => (
          <div key={s.key} className="flex-1 text-center">
            <div
              className="h-1 rounded-full"
              style={{
                background: i <= currentStep ? "#22c55e" : "var(--bg-input)",
              }}
            />
            <span className="text-xs mt-1 block" style={{
              color: i <= currentStep ? "#22c55e" : "var(--text-muted)",
            }}>
              {s.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RadarChart({ dimensions }: { dimensions: DimensionScore[] }) {
  const size = 200;
  const center = size / 2;
  const radius = 80;
  const n = dimensions.length;
  if (n === 0) return null;
  const angleStep = (2 * Math.PI) / n;
  const points = dimensions.map((d, i) => {
    const angle = angleStep * i - Math.PI / 2;
    const r = (d.score / 5) * radius;
    return { x: center + r * Math.cos(angle), y: center + r * Math.sin(angle), label: DIMENSION_LABELS[d.dimension] || d.dimension, score: d.score };
  });
  const pathData = points.map((p) => `${p.x},${p.y}`).join(" ");
  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} className="mb-2">
        {[1, 2, 3, 4, 5].map((level) => (
          <polygon key={level} points={Array.from({ length: n }, (_, i) => { const angle = angleStep * i - Math.PI / 2; const r = (level / 5) * radius; return `${center + r * Math.cos(angle)},${center + r * Math.sin(angle)}`; }).join(" ")} fill="none" stroke="#333" strokeWidth="0.5" />
        ))}
        {points.map((p, i) => (<line key={i} x1={center} y1={center} x2={center + radius * Math.cos(angleStep * i - Math.PI / 2)} y2={center + radius * Math.sin(angleStep * i - Math.PI / 2)} stroke="#333" strokeWidth="0.5" />))}
        <polygon points={pathData} fill="rgba(34, 197, 94, 0.2)" stroke="#22c55e" strokeWidth="2" />
        {points.map((p, i) => (<circle key={i} cx={p.x} cy={p.y} r="3" fill="#22c55e" />))}
      </svg>
      <div className="grid grid-cols-5 gap-x-4 gap-y-1 text-xs" style={{ color: "var(--text-secondary)" }}>
        {points.map((p) => (<span key={p.label}>{p.label} <strong>{p.score}</strong></span>))}
      </div>
    </div>
  );
}

function ViralityGauge({ score }: { score: number }) {
  const color = score >= 70 ? "#22c55e" : score >= 40 ? "#eab308" : "#ef4444";
  return (
    <div className="flex flex-col items-center">
      <div className="text-5xl font-bold" style={{ color }}>{score}</div>
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>/ 100</div>
    </div>
  );
}

export default function PredictPage() {
  return (
    <Suspense>
      <PredictPageInner />
    </Suspense>
  );
}

function PredictPageInner() {
  const searchParams = useSearchParams();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [selectedScript, setSelectedScript] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(-1);
  const [scoreResult, setScoreResult] = useState<ScoreResult | null>(null);
  const [viralityResult, setViralityResult] = useState<ViralityResult | null>(null);
  const [error, setError] = useState("");
  const [existingPrediction, setExistingPrediction] = useState<string | null>(null);

  const loadScripts = async () => {
    const res = await apiFetch<{ scripts: Script[] }>("/api/scripts");
    if (res.ok && res.data) setScripts(res.data.scripts);
  };

  const handlePredict = async () => {
    if (!selectedScript) return;
    setLoading(true);
    setError("");
    setScoreResult(null);
    setViralityResult(null);
    setExistingPrediction(null);
    setCurrentStep(0);

    try {
      // Try SSE first for real-time progress
      const result = await sseFetch<{
        prediction_id: string;
        score: ScoreResult;
        virality: ViralityResult;
      }>(
        "/api/sse/predict",
        { script_id: selectedScript },
        (event) => {
          // Map SSE phase to step index
          const stepIndex = PHASE_TO_STEP[event.phase];
          if (stepIndex !== undefined) {
            setCurrentStep(stepIndex);
          }
        }
      );

      setCurrentStep(4);
      setScoreResult(result.score);
      setViralityResult(result.virality);
    } catch (sseError) {
      // SSE failed — fall back to regular POST /api/predict/full
      console.warn("SSE failed, falling back to regular endpoint:", sseError);

      // Simulate step progress for the fallback
      const stepTimers = [
        setTimeout(() => setCurrentStep(1), 500),
        setTimeout(() => setCurrentStep(2), 3000),
        setTimeout(() => setCurrentStep(3), 8000),
        setTimeout(() => setCurrentStep(4), 12000),
      ];

      try {
        const res = await apiFetch<{
          prediction_id: string;
          score: ScoreResult;
          virality: ViralityResult;
        }>("/api/predict/full", {
          method: "POST",
          body: JSON.stringify({ script_id: selectedScript }),
        });

        stepTimers.forEach(clearTimeout);

        if (res.ok && res.data) {
          setCurrentStep(4);
          setScoreResult(res.data.score);
          setViralityResult(res.data.virality);
        } else {
          if (res.error?.code === "PREDICTION_EXISTS") {
            const predictionId = res.error.message.match(/[\w_]+/)?.[0] || selectedScript;
            setExistingPrediction(predictionId);
            setError("该脚本已有预测结果，点击下方查看");
          } else {
            setError(res.error?.message || "预测失败");
          }
          setCurrentStep(-1);
        }
      } catch {
        stepTimers.forEach(clearTimeout);
        setError("网络错误，请检查后端服务是否运行");
        setCurrentStep(-1);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      const res = await apiFetch<{ scripts: Script[] }>("/api/scripts");
      if (res.ok && res.data) {
        setScripts(res.data.scripts);
        const preselectedScript = searchParams.get("script");
        if (preselectedScript && res.data.scripts.find(s => s.id === preselectedScript)) {
          setSelectedScript(preselectedScript);
        }
      }
    };
    init();
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-bold text-glow">爆款预测</h1>
      <p className="mt-2" style={{ color: "var(--text-secondary)" }}>
        选择脚本 → 盲打分 + 爆款预测 + 诊断建议
      </p>

      {/* 选择脚本 */}
      <div className="mt-6 flex gap-4">
        <select
          className="select flex-1"
          value={selectedScript}
          onChange={(e) => setSelectedScript(e.target.value)}
          onFocus={loadScripts}
        >
          <option value="">选择脚本...</option>
          {scripts.map((s) => (
            <option key={s.id} value={s.id}>{s.title || s.id}</option>
          ))}
        </select>
        <button
          className="btn-primary"
          onClick={handlePredict}
          disabled={!selectedScript || loading}
        >
          {loading ? "预测中..." : "预测"}
        </button>
      </div>

      {/* 进度条 */}
      {loading && <StepProgress currentStep={currentStep} totalSteps={PREDICT_STEPS.length} />}

      {/* 错误提示 */}
      {error && !loading && (
        <div className="mt-4 rounded-lg p-4" style={{ border: "1px solid rgba(239, 68, 68, 0.3)", background: "rgba(239, 68, 68, 0.1)" }}>
          <p className="text-sm">{error}</p>
          {existingPrediction && (
            <a href={`/predict?script=${existingPrediction}`} className="btn-ghost text-xs mt-2 inline-block">
              查看已有预测
            </a>
          )}
        </div>
      )}

      {/* 结果展示 */}
      {viralityResult && scoreResult && (
        <div className="mt-8 space-y-6">
          {/* 盲预测 immutable 提示 */}
          <div className="card flex items-center gap-2" style={{ borderColor: "rgba(234, 179, 8, 0.3)", background: "rgba(234, 179, 8, 0.08)" }}>
            <span className="text-lg" title="盲预测段不可修改">&#x1F512;</span>
            <span className="text-sm font-medium" style={{ color: "#eab308" }}>
              盲预测已锁定 — 预测段一旦写入不可修改，只能追加复盘段
            </span>
          </div>

          {/* 爆款分 + 雷达图 */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold">爆款分</h2>
              <ViralityGauge score={viralityResult.virality_score} />
              <div className="mt-4 text-sm" style={{ color: "var(--text-secondary)" }}>
                <p>Bucket: {viralityResult.bucket.scheme} → {viralityResult.bucket.prediction}</p>
                <p>综合分: {scoreResult.composite}/10 | Phase: {viralityResult.phase}</p>
              </div>
            </div>
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold">维度雷达图</h2>
              <RadarChart dimensions={scoreResult.dimensions} />
            </div>
          </div>

          {/* 子分 breakdown */}
          <div className="card">
            <h2 className="mb-4 text-lg font-semibold">爆款子分</h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {Object.entries(viralityResult.sub_scores).map(([key, val]) => (
                <div key={key} className="text-center">
                  <div className="text-2xl font-bold" style={{ color: "#22c55e" }}>
                    {((val as number) * 100).toFixed(0)}%
                  </div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>{key}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 诊断 */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="card" style={{ borderColor: "rgba(239, 68, 68, 0.3)" }}>
              <h2 className="mb-4 text-lg font-semibold" style={{ color: "#ef4444" }}>风险信号</h2>
              {viralityResult.diagnosis.risks.length > 0 ? (
                <ul className="space-y-2">{viralityResult.diagnosis.risks.map((r, i) => (<li key={i} className="text-sm">- {r}</li>))}</ul>
              ) : (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>无风险信号</p>
              )}
            </div>
            <div className="card" style={{ borderColor: "rgba(34, 197, 94, 0.3)" }}>
              <h2 className="mb-4 text-lg font-semibold" style={{ color: "#22c55e" }}>亮点</h2>
              {viralityResult.diagnosis.highlights.length > 0 ? (
                <ul className="space-y-2">{viralityResult.diagnosis.highlights.map((h, i) => (<li key={i} className="text-sm">+ {h}</li>))}</ul>
              ) : (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>无亮点</p>
              )}
            </div>
          </div>

          {/* 改稿建议 */}
          {viralityResult.suggestions.length > 0 && (
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold">改稿建议</h2>
              <div className="space-y-3">
                {viralityResult.suggestions.map((s, i) => (
                  <div key={i} className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                    <div className="flex items-center gap-2">
                      <span className={`badge ${s.priority === "high" ? "badge-red" : s.priority === "medium" ? "badge-yellow" : "badge-blue"}`}>
                        {s.priority.toUpperCase()}
                      </span>
                      <span className="font-medium">{s.target_dimension}</span>
                    </div>
                    <p className="mt-1 text-sm">{s.action}</p>
                    <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>预期影响: {s.expected_impact}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
