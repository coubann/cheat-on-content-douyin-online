"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import type { ABExperiment } from "@/lib/api-types";

const STATUS_LABELS: Record<string, string> = {
  created: "已创建",
  predicted: "已预测",
  completed: "已完成",
};
const STATUS_COLORS: Record<string, string> = {
  created: "#888888",
  predicted: "#3b82f6",
  completed: "#22c55e",
};

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<ABExperiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [scripts, setScripts] = useState<Array<{ id: string; title: string }>>([]);
  const [createForm, setCreateForm] = useState({
    topic: "",
    script_a_id: "",
    script_b_id: "",
    hypothesis: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [predicting, setPredicting] = useState<string | null>(null);
  const [selectedExp, setSelectedExp] = useState<ABExperiment | null>(null);
  const [completeForm, setCompleteForm] = useState({ actual_plays_a: "", actual_plays_b: "" });
  const [completing, setCompleting] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError("");
    const res = await apiFetch<{ experiments: ABExperiment[] }>("/api/experiments");
    if (res.ok && res.data) {
      setExperiments(res.data.experiments);
    } else {
      setError(res.error?.message || "加载失败");
    }
    setLoading(false);
  };

  const loadScripts = async () => {
    const res = await apiFetch<{ scripts: Array<{ id: string; title: string }> }>("/api/scripts");
    if (res.ok && res.data) setScripts(res.data.scripts);
  };

  const handleCreate = async () => {
    if (!createForm.topic || !createForm.script_a_id || !createForm.script_b_id) return;
    setSubmitting(true);
    const res = await apiFetch<ABExperiment>("/api/experiments", {
      method: "POST",
      body: JSON.stringify(createForm),
    });
    if (res.ok) {
      setShowCreate(false);
      setCreateForm({ topic: "", script_a_id: "", script_b_id: "", hypothesis: "" });
      loadData();
    } else {
      setError(res.error?.message || "创建失败");
    }
    setSubmitting(false);
  };

  const handlePredict = async (id: string) => {
    setPredicting(id);
    const res = await apiFetch<ABExperiment>(`/api/experiments/${id}/predict`, {
      method: "POST",
    });
    if (res.ok) {
      loadData();
    } else {
      setError(res.error?.message || "预测失败");
    }
    setPredicting(null);
  };

  const handleComplete = async (id: string) => {
    if (!completeForm.actual_plays_a || !completeForm.actual_plays_b) return;
    setCompleting(id);
    const res = await apiFetch<ABExperiment>(`/api/experiments/${id}/complete`, {
      method: "POST",
      body: JSON.stringify({
        actual_plays_a: Number(completeForm.actual_plays_a),
        actual_plays_b: Number(completeForm.actual_plays_b),
      }),
    });
    if (res.ok) {
      setSelectedExp(null);
      setCompleteForm({ actual_plays_a: "", actual_plays_b: "" });
      loadData();
    } else {
      setError(res.error?.message || "完成实验失败");
    }
    setCompleting(null);
  };

  useEffect(() => {
    loadData();
    loadScripts();
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-glow">A/B 实验</h1>
          <p className="mt-1" style={{ color: "var(--text-secondary)" }}>
            对比两个脚本版本的预测效果与实际表现
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "取消" : "新建实验"}
          </button>
          <button className="btn-ghost text-sm" onClick={loadData}>
            刷新
          </button>
        </div>
      </div>

      {/* 新建实验表单 */}
      {showCreate && (
        <div className="card mt-6">
          <h3 className="text-lg font-semibold mb-4">新建 A/B 实验</h3>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>实验主题</label>
              <input
                className="input w-full"
                placeholder="例: 开头钩子对比"
                value={createForm.topic}
                onChange={(e) => setCreateForm({ ...createForm, topic: e.target.value })}
              />
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>假设</label>
              <input
                className="input w-full"
                placeholder="例: 直接提问式钩子更吸引人"
                value={createForm.hypothesis}
                onChange={(e) => setCreateForm({ ...createForm, hypothesis: e.target.value })}
              />
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>脚本 A</label>
              <select
                className="select w-full"
                value={createForm.script_a_id}
                onChange={(e) => setCreateForm({ ...createForm, script_a_id: e.target.value })}
              >
                <option value="">选择脚本 A...</option>
                {scripts.map((s) => (
                  <option key={s.id} value={s.id}>{s.title || s.id}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>脚本 B</label>
              <select
                className="select w-full"
                value={createForm.script_b_id}
                onChange={(e) => setCreateForm({ ...createForm, script_b_id: e.target.value })}
              >
                <option value="">选择脚本 B...</option>
                {scripts.map((s) => (
                  <option key={s.id} value={s.id}>{s.title || s.id}</option>
                ))}
              </select>
            </div>
          </div>
          <button
            className="btn-primary mt-4"
            onClick={handleCreate}
            disabled={submitting || !createForm.topic || !createForm.script_a_id || !createForm.script_b_id}
          >
            {submitting ? "创建中..." : "创建实验"}
          </button>
        </div>
      )}

      {/* 加载状态 */}
      {loading && (
        <div className="mt-8 text-center" style={{ color: "var(--text-muted)" }}>加载中...</div>
      )}

      {/* 错误提示 */}
      {error && !loading && (
        <div className="mt-6 rounded-lg p-4" style={{ border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.1)" }}>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* 实验列表 */}
      <div className="mt-6 space-y-4">
        {experiments.length === 0 && !loading && (
          <p style={{ color: "var(--text-muted)" }}>暂无实验，点击"新建实验"开始</p>
        )}
        {experiments.map((exp) => (
          <div key={exp.id} className="card">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-semibold">{exp.topic}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className="badge"
                    style={{
                      background: `${STATUS_COLORS[exp.status]}20`,
                      color: STATUS_COLORS[exp.status],
                    }}
                  >
                    {STATUS_LABELS[exp.status]}
                  </span>
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    创建于 {new Date(exp.created_at).toLocaleString("zh-CN")}
                  </span>
                </div>
                {exp.hypothesis && (
                  <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                    假设: {exp.hypothesis}
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                {exp.status === "created" && (
                  <button
                    className="btn-primary text-sm"
                    onClick={() => handlePredict(exp.id)}
                    disabled={predicting === exp.id}
                  >
                    {predicting === exp.id ? "预测中..." : "运行预测"}
                  </button>
                )}
                {exp.status === "predicted" && (
                  <button
                    className="btn-ghost text-sm"
                    onClick={() => {
                      setSelectedExp(exp);
                      setCompleteForm({ actual_plays_a: "", actual_plays_b: "" });
                    }}
                  >
                    填入实际结果
                  </button>
                )}
              </div>
            </div>

            {/* 预测对比 */}
            {exp.prediction_a && exp.prediction_b && (
              <div className="grid gap-4 md:grid-cols-2 mt-4">
                <div className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                  <div className="text-sm font-medium mb-2" style={{ color: "#3b82f6" }}>脚本 A</div>
                  {exp.prediction_a.virality_score !== undefined && (
                    <div className="text-2xl font-bold" style={{ color: "#3b82f6" }}>
                      {typeof exp.prediction_a.virality_score === "number"
                        ? exp.prediction_a.virality_score
                        : "—"}
                    </div>
                  )}
                  {exp.actual_plays_a !== null && (
                    <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                      实际播放: {exp.actual_plays_a}
                    </div>
                  )}
                </div>
                <div className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                  <div className="text-sm font-medium mb-2" style={{ color: "#eab308" }}>脚本 B</div>
                  {exp.prediction_b.virality_score !== undefined && (
                    <div className="text-2xl font-bold" style={{ color: "#eab308" }}>
                      {typeof exp.prediction_b.virality_score === "number"
                        ? exp.prediction_b.virality_score
                        : "—"}
                    </div>
                  )}
                  {exp.actual_plays_b !== null && (
                    <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                      实际播放: {exp.actual_plays_b}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 完成结果 */}
            {exp.result && (
              <div className="mt-4 rounded-lg p-3" style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)" }}>
                <div className="text-sm font-medium" style={{ color: "#22c55e" }}>实验结论</div>
                <p className="text-sm mt-1">
                  {exp.result.winner != null && `胜出: ${String(exp.result.winner) === "a" ? "脚本 A" : "脚本 B"}`}
                  {exp.result.summary != null && ` · ${String(exp.result.summary)}`}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 完成实验弹窗 */}
      {selectedExp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div className="card w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold mb-4">填入实际播放量</h2>
            <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
              实验: {selectedExp.topic}
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>脚本 A 实际播放</label>
                <input
                  type="number"
                  className="input w-full"
                  placeholder="播放量"
                  value={completeForm.actual_plays_a}
                  onChange={(e) => setCompleteForm({ ...completeForm, actual_plays_a: e.target.value })}
                />
              </div>
              <div>
                <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>脚本 B 实际播放</label>
                <input
                  type="number"
                  className="input w-full"
                  placeholder="播放量"
                  value={completeForm.actual_plays_b}
                  onChange={(e) => setCompleteForm({ ...completeForm, actual_plays_b: e.target.value })}
                />
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button
                className="btn-primary"
                onClick={() => handleComplete(selectedExp.id)}
                disabled={completing === selectedExp.id || !completeForm.actual_plays_a || !completeForm.actual_plays_b}
              >
                {completing === selectedExp.id ? "提交中..." : "完成实验"}
              </button>
              <button className="btn-ghost" onClick={() => setSelectedExp(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
