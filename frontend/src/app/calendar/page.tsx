"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import type { CalendarData, CalendarDay, ScheduleItem } from "@/lib/api-types";

const WEEKDAY_HEADERS = ["一", "二", "三", "四", "五", "六", "日"];

const STATUS_COLORS: Record<string, string> = {
  planned: "#3b82f6",
  published: "#22c55e",
  retro: "#eab308",
};
const STATUS_LABELS: Record<string, string> = {
  planned: "计划",
  published: "已发",
  retro: "复盘",
};

export default function CalendarPage() {
  const [data, setData] = useState<CalendarData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showSchedule, setShowSchedule] = useState(false);
  const [scheduleForm, setScheduleForm] = useState({
    date: "",
    script_id: "",
    platform: "douyin",
    notes: "",
  });
  const [scripts, setScripts] = useState<Array<{ id: string; title: string }>>([]);
  const [submitting, setSubmitting] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError("");
    const res = await apiFetch<CalendarData>("/api/calendar?days=14");
    if (res.ok && res.data) {
      setData(res.data);
    } else {
      setError(res.error?.message || "加载失败");
    }
    setLoading(false);
  };

  const loadScripts = async () => {
    const res = await apiFetch<{ scripts: Array<{ id: string; title: string }> }>("/api/scripts");
    if (res.ok && res.data) setScripts(res.data.scripts);
  };

  const handleSchedule = async () => {
    if (!scheduleForm.date || !scheduleForm.script_id) return;
    setSubmitting(true);
    const res = await apiFetch<ScheduleItem>("/api/calendar/schedule", {
      method: "POST",
      body: JSON.stringify(scheduleForm),
    });
    if (res.ok) {
      setShowSchedule(false);
      setScheduleForm({ date: "", script_id: "", platform: "douyin", notes: "" });
      loadData();
    } else {
      setError(res.error?.message || "排期失败");
    }
    setSubmitting(false);
  };

  useEffect(() => {
    loadData();
    loadScripts();
  }, []);

  // 将天数按周排列
  const gridDays = data?.days || [];
  const firstDayOffset = gridDays.length > 0 ? new Date(gridDays[0].date).getDay() - 1 : 0;
  const adjustedOffset = firstDayOffset < 0 ? 6 : firstDayOffset;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-glow">内容日历</h1>
          <p className="mt-1" style={{ color: "var(--text-secondary)" }}>
            排期管理 · 发布节奏 · 缓冲天数
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => setShowSchedule(!showSchedule)}>
            {showSchedule ? "取消" : "新增排期"}
          </button>
          <button className="btn-ghost text-sm" onClick={loadData}>
            刷新
          </button>
        </div>
      </div>

      {/* 统计概览 */}
      {data && (
        <div className="mt-6 grid grid-cols-3 gap-3">
          <div className="card text-center">
            <div className="text-2xl font-bold" style={{ color: "#22c55e" }}>{data.total_scheduled}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>已排期</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold" style={{ color: "#3b82f6" }}>{data.buffer}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>缓冲天数</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold" style={{ color: "#eab308" }}>{data.cadence}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>发布节奏(天)</div>
          </div>
        </div>
      )}

      {/* 建议 */}
      {data && data.suggestions.length > 0 && (
        <div className="mt-4 space-y-2">
          {data.suggestions.map((s, i) => (
            <div
              key={i}
              className="rounded-lg px-4 py-2 text-sm"
              style={{
                background: s.type === "warning" ? "rgba(234,179,8,0.1)" : "rgba(34,197,94,0.1)",
                borderLeft: `3px solid ${s.type === "warning" ? "#eab308" : "#22c55e"}`,
                color: s.type === "warning" ? "#eab308" : "#22c55e",
              }}
            >
              {s.message}
            </div>
          ))}
        </div>
      )}

      {/* 新增排期表单 */}
      {showSchedule && (
        <div className="card mt-6">
          <h3 className="text-lg font-semibold mb-4">新增排期</h3>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>日期</label>
              <input
                type="date"
                className="input w-full"
                value={scheduleForm.date}
                onChange={(e) => setScheduleForm({ ...scheduleForm, date: e.target.value })}
              />
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>脚本</label>
              <select
                className="select w-full"
                value={scheduleForm.script_id}
                onChange={(e) => setScheduleForm({ ...scheduleForm, script_id: e.target.value })}
              >
                <option value="">选择脚本...</option>
                {scripts.map((s) => (
                  <option key={s.id} value={s.id}>{s.title || s.id}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>平台</label>
              <select
                className="select w-full"
                value={scheduleForm.platform}
                onChange={(e) => setScheduleForm({ ...scheduleForm, platform: e.target.value })}
              >
                <option value="douyin">抖音</option>
                <option value="xiaohongshu">小红书</option>
                <option value="bilibili">B站</option>
              </select>
            </div>
            <div>
              <label className="text-sm mb-1 block" style={{ color: "var(--text-secondary)" }}>备注</label>
              <input
                className="input w-full"
                placeholder="备注..."
                value={scheduleForm.notes}
                onChange={(e) => setScheduleForm({ ...scheduleForm, notes: e.target.value })}
              />
            </div>
          </div>
          <button
            className="btn-primary mt-4"
            onClick={handleSchedule}
            disabled={submitting || !scheduleForm.date || !scheduleForm.script_id}
          >
            {submitting ? "提交中..." : "确认排期"}
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

      {/* 日历网格 */}
      {!loading && gridDays.length > 0 && (
        <div className="mt-6">
          {/* 星期头 */}
          <div className="grid grid-cols-7 gap-1 mb-1">
            {WEEKDAY_HEADERS.map((d) => (
              <div key={d} className="text-center text-xs font-medium py-2" style={{ color: "var(--text-muted)" }}>
                {d}
              </div>
            ))}
          </div>

          {/* 日期格子 */}
          <div className="grid grid-cols-7 gap-1">
            {/* 前置空白 */}
            {Array.from({ length: adjustedOffset }, (_, i) => (
              <div key={`empty-${i}`} />
            ))}

            {gridDays.map((day) => (
              <div
                key={day.date}
                className="rounded-lg p-2 min-h-[100px] border transition-all"
                style={{
                  background: day.is_today
                    ? "rgba(34,197,94,0.08)"
                    : day.is_weekend
                    ? "rgba(255,255,255,0.02)"
                    : "var(--bg-card)",
                  borderColor: day.is_today ? "rgba(34,197,94,0.3)" : "var(--border)",
                  opacity: day.is_weekend ? 0.7 : 1,
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span
                    className="text-xs font-medium"
                    style={{
                      color: day.is_today ? "#22c55e" : "var(--text-secondary)",
                    }}
                  >
                    {day.date.slice(5)}
                  </span>
                  {day.is_today && (
                    <span className="text-xs" style={{ color: "#22c55e" }}>今</span>
                  )}
                </div>

                {/* 排期项 */}
                {day.scheduled.map((item) => (
                  <div
                    key={item.id}
                    className="mb-1 rounded px-1.5 py-0.5 text-xs truncate"
                    style={{
                      background: `${STATUS_COLORS[item.status]}20`,
                      color: STATUS_COLORS[item.status],
                    }}
                    title={`${STATUS_LABELS[item.status]} · ${item.platform}`}
                  >
                    {STATUS_LABELS[item.status]} · {item.platform}
                  </div>
                ))}

                {/* 脚本 */}
                {day.scripts.length > 0 && (
                  <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                    📝 {day.scripts.length} 脚本
                  </div>
                )}

                {/* 预测 */}
                {day.predictions.length > 0 && (
                  <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                    🔮 {day.predictions.length} 预测
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && gridDays.length === 0 && !error && (
        <p className="mt-8 text-center" style={{ color: "var(--text-muted)" }}>暂无日历数据</p>
      )}
    </main>
  );
}
