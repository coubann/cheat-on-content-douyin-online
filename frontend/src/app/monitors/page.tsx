"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import type { CompetitorMonitor, MonitorUpdate } from "@/lib/api-types";

export default function MonitorsPage() {
  const [monitors, setMonitors] = useState<CompetitorMonitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    account_name: "",
    platform: "douyin",
    check_interval_hours: "6",
  });
  const [submitting, setSubmitting] = useState(false);
  const [checking, setChecking] = useState<string | null>(null);
  const [checkingAll, setCheckingAll] = useState(false);
  const [history, setHistory] = useState<MonitorUpdate[]>([]);
  const [showHistory, setShowHistory] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError("");
    const res = await apiFetch<{ monitors: CompetitorMonitor[] }>("/api/monitors");
    if (res.ok && res.data) {
      setMonitors(res.data.monitors);
    } else {
      setError(res.error?.message || "加载失败");
    }
    setLoading(false);
  };

  const handleCreate = async () => {
    if (!createForm.account_name) return;
    setSubmitting(true);
    const res = await apiFetch<CompetitorMonitor>("/api/monitors", {
      method: "POST",
      body: JSON.stringify({
        account_name: createForm.account_name,
        platform: createForm.platform,
        check_interval_hours: Number(createForm.check_interval_hours),
      }),
    });
    if (res.ok) {
      setShowCreate(false);
      setCreateForm({ account_name: "", platform: "douyin", check_interval_hours: "6" });
      loadData();
    } else {
      setError(res.error?.message || "创建失败");
    }
    setSubmitting(false);
  };

  const handleCheck = async (id: string) => {
    setChecking(id);
    const res = await apiFetch<{ updates: MonitorUpdate[] }>(`/api/monitors/${id}/check`, {
      method: "POST",
    });
    if (res.ok) {
      loadData();
    } else {
      setError(res.error?.message || "检查失败");
    }
    setChecking(null);
  };

  const handleCheckAll = async () => {
    setCheckingAll(true);
    const res = await apiFetch<{ results: Array<{ monitor_id: string; updates: MonitorUpdate[] }> }>("/api/monitors/check-all", {
      method: "POST",
    });
    if (res.ok) {
      loadData();
    } else {
      setError(res.error?.message || "检查失败");
    }
    setCheckingAll(false);
  };

  const loadHistory = async (id: string) => {
    setShowHistory(id);
    setHistoryLoading(true);
    const res = await apiFetch<{ updates: MonitorUpdate[] }>(`/api/monitors/${id}/history`);
    if (res.ok && res.data) {
      setHistory(res.data.updates);
    } else {
      setHistory([]);
    }
    setHistoryLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  const newContentCount = monitors.filter((m) => m.new_content_detected).length;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-glow">竞品监控</h1>
          <p className="mt-1" style={{ color: "var(--text-secondary)" }}>
            监控竞品账号动态，发现新内容自动提醒
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "取消" : "添加监控"}
          </button>
          <button
            className="btn-ghost text-sm"
            onClick={handleCheckAll}
            disabled={checkingAll || monitors.length === 0}
          >
            {checkingAll ? "检查中..." : "全部检查"}
          </button>
          <button className="btn-ghost text-sm" onClick={loadData}>
            刷新
          </button>
        </div>
      </div>

      {/* 新内容提醒 */}
      {newContentCount > 0 && (
        <div className="mt-4 rounded-lg px-4 py-3" style={{ background: "rgba(234,179,8,0.1)", borderLeft: "3px solid #eab308" }}>
          <span style={{ color: "#eab308" }}>
            ⚠ {newContentCount} 个监控账号检测到新内容
          </span>
        </div>
      )}

      {/* 新建监控表单 */}
      {showCreate && (
        <div className="card mt-6">
          <h3 className="text-lg font-semibold mb-4">添加竞品监控</h3>
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>账号名称</label>
              <input
                className="input w-full"
                placeholder="竞品账号名"
                value={createForm.account_name}
                onChange={(e) => setCreateForm({ ...createForm, account_name: e.target.value })}
              />
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>平台</label>
              <select
                className="select w-full"
                value={createForm.platform}
                onChange={(e) => setCreateForm({ ...createForm, platform: e.target.value })}
              >
                <option value="douyin">抖音</option>
                <option value="xiaohongshu">小红书</option>
                <option value="bilibili">B站</option>
              </select>
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>检查间隔(小时)</label>
              <input
                type="number"
                className="input w-full"
                value={createForm.check_interval_hours}
                onChange={(e) => setCreateForm({ ...createForm, check_interval_hours: e.target.value })}
              />
            </div>
          </div>
          <button
            className="btn-primary mt-4"
            onClick={handleCreate}
            disabled={submitting || !createForm.account_name}
          >
            {submitting ? "创建中..." : "添加监控"}
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

      {/* 监控列表 */}
      <div className="mt-6 space-y-3">
        {monitors.length === 0 && !loading && (
          <p style={{ color: "var(--text-muted)" }}>暂无监控，点击"添加监控"开始</p>
        )}
        {monitors.map((m) => (
          <div key={m.id} className="card flex items-center justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{m.account_name}</span>
                <span className="badge badge-blue">{m.platform}</span>
                {m.new_content_detected && (
                  <span className="badge badge-yellow">新内容</span>
                )}
              </div>
              <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                每 {m.check_interval_hours}h 检查
                {m.last_check && ` · 上次: ${new Date(m.last_check).toLocaleString("zh-CN")}`}
                {` · 内容数: ${m.last_content_count}`}
              </div>
            </div>
            <div className="flex items-center gap-2 ml-4">
              <button
                className="btn-ghost text-sm"
                onClick={() => handleCheck(m.id)}
                disabled={checking === m.id}
              >
                {checking === m.id ? "检查中..." : "检查"}
              </button>
              <button
                className="btn-ghost text-sm"
                onClick={() => loadHistory(m.id)}
              >
                历史
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* 历史弹窗 */}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div className="card w-full max-w-lg mx-4 max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">更新历史</h2>
              <button
                onClick={() => { setShowHistory(null); setHistory([]); }}
                className="text-sm"
                style={{ color: "var(--text-muted)" }}
              >
                关闭
              </button>
            </div>
            {historyLoading ? (
              <p style={{ color: "var(--text-muted)" }}>加载中...</p>
            ) : history.length === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>暂无历史记录</p>
            ) : (
              <div className="space-y-3">
                {history.map((u, i) => (
                  <div key={i} className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium">
                        {new Date(u.detected_at).toLocaleString("zh-CN")}
                      </span>
                      <span className="badge badge-green">{u.action_taken}</span>
                    </div>
                    {u.new_samples.length > 0 && (
                      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                        新内容: {u.new_samples.join(", ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
