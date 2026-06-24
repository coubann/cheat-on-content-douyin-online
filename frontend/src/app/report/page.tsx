"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import type { RetroReportSummary } from "@/lib/api-types";
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";

interface RetroReport {
  status: string;
  generated_at: string;
  summary: {
    total_retros: number;
    calibration_samples: number;
    rubric_version: string;
    last_bump_at: string | null;
  };
  accuracy: {
    total: number;
    accuracy_rate: number;
    accuracy_distribution: {
      overestimated: number;
      underestimated: number;
      accurate: number;
      unknown: number;
    };
    plays: { avg: number; max: number; min: number };
    composite: { avg: number };
    top3: Array<{ script_id: string; actual_plays: number; composite: number }>;
    bottom3: Array<{ script_id: string; actual_plays: number; composite: number }>;
  };
  dimension_analysis: {
    dimensions: Record<
      string,
      { avg_score: number; correlation_with_plays: number; sample_count: number }
    >;
    most_predictive: string | null;
    least_predictive: string | null;
  };
  rubric_history: Array<{
    date: string;
    consistency: number;
    pool_size: number;
  }>;
  llm_insights: {
    overall_assessment: string;
    key_findings: string[];
    rubric_recommendation: string;
    content_strategy: string;
    next_bump_trigger: string;
    risk_warnings: string[];
  };
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

const CHART_COLORS = {
  green: "#22c55e",
  blue: "#3b82f6",
  yellow: "#f59e0b",
  red: "#ef4444",
  text: "#999",
  grid: "#333",
};

// Shared tooltip style for dark theme
const tooltipStyle: React.CSSProperties = {
  backgroundColor: "#1a1a2e",
  border: "1px solid #333",
  borderRadius: "8px",
  color: "#e0e0e0",
  fontSize: "12px",
};

export default function ReportPage() {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<RetroReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [historyReports, setHistoryReports] = useState<RetroReportSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  // 加载历史报告列表
  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setHistoryLoading(true);
    const res = await apiFetch<{ reports: RetroReportSummary[] }>("/api/publish/retro-reports");
    if (res.ok && res.data) {
      setHistoryReports(res.data.reports);
    }
    setHistoryLoading(false);
  };

  const generateReport = async () => {
    setLoading(true);
    setError(null);
    setReport(null);
    setSelectedReportId(null);

    const res = await apiFetch<RetroReport>("/api/publish/retro-report");

    if (res.ok && res.data) {
      setReport(res.data);
      // 刷新历史列表
      await loadHistory();
    } else {
      setError(res.error?.message || "生成报告失败");
    }
    setLoading(false);
  };

  const viewHistoryReport = async (reportId: string) => {
    setLoading(true);
    setError(null);
    setSelectedReportId(reportId);

    const res = await apiFetch<RetroReport>(`/api/publish/retro-reports/${reportId}`);

    if (res.ok && res.data) {
      setReport(res.data);
    } else {
      setError(res.error?.message || "加载报告失败");
    }
    setLoading(false);
  };

  // Prepare dimension radar chart data
  const getRadarData = () => {
    if (!report) return [];
    return Object.entries(report.dimension_analysis.dimensions || {}).map(
      ([dim, info]) => ({
        dimension: DIM_LABELS[dim] || dim,
        avg_score: info.avg_score,
        correlation: Math.abs(info.correlation_with_plays),
      })
    );
  };

  // Prepare dimension correlation bar chart data
  const getCorrelationData = () => {
    if (!report) return [];
    return Object.entries(report.dimension_analysis.dimensions || {})
      .sort(
        ([, a], [, b]) =>
          Math.abs(b.correlation_with_plays) -
          Math.abs(a.correlation_with_plays)
      )
      .map(([dim, info]) => ({
        dimension: `${dim} (${DIM_LABELS[dim] || dim})`,
        correlation: Number(info.correlation_with_plays.toFixed(3)),
        avg_score: Number(info.avg_score.toFixed(1)),
      }));
  };

  // Prepare rubric history line chart data
  const getHistoryData = () => {
    if (!report) return [];
    return report.rubric_history.map((h) => ({
      date: h.date,
      consistency: Number(h.consistency.toFixed(2)),
      pool_size: h.pool_size,
    }));
  };

  // Prepare accuracy distribution pie chart data
  const getPieData = () => {
    if (!report) return [];
    const d = report.accuracy.accuracy_distribution;
    return [
      { name: "高估", value: d.overestimated, color: CHART_COLORS.red },
      { name: "准确", value: d.accurate, color: CHART_COLORS.green },
      { name: "低估", value: d.underestimated, color: CHART_COLORS.blue },
    ].filter((item) => item.value > 0);
  };

  // 格式化时间
  const formatTime = (isoStr: string) => {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoStr;
    }
  };

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-3xl font-bold text-glow">自动化复盘报告</h1>
      <p className="mt-2" style={{ color: "var(--text-secondary)" }}>
        从已复盘数据中提取洞察，生成综合报告
      </p>

      <div className="mt-6 flex items-center gap-4">
        <button
          onClick={generateReport}
          disabled={loading}
          className="btn-primary"
        >
          {loading ? "生成中..." : "生成新报告"}
        </button>
        {selectedReportId && (
          <button
            onClick={() => {
              setSelectedReportId(null);
              setReport(null);
            }}
            className="btn-secondary"
          >
            返回当前
          </button>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-lg p-4" style={{ border: "1px solid rgba(239, 68, 68, 0.3)", background: "rgba(239, 68, 68, 0.1)", color: "#ef4444" }}>
          {error}
        </div>
      )}

      {/* 历史报告列表 */}
      <div className="mt-8">
        <h2 className="text-xl font-bold">历史报告</h2>
        {historyLoading ? (
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>加载中...</p>
        ) : historyReports.length === 0 ? (
          <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>暂无历史报告，点击上方按钮生成第一份</p>
        ) : (
          <div className="mt-3 space-y-2">
            {historyReports.map((r) => (
              <button
                key={r.report_id}
                onClick={() => viewHistoryReport(r.report_id)}
                className="card w-full text-left transition-colors hover:border-[var(--accent)]"
                style={{
                  borderColor: selectedReportId === r.report_id
                    ? "var(--accent)"
                    : undefined,
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-mono" style={{ color: "var(--text-muted)" }}>
                      {r.rubric_version}
                    </span>
                    <span className="font-medium">
                      {formatTime(r.generated_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span>
                      <span className="font-mono font-bold">{r.total_retros}</span>
                      <span style={{ color: "var(--text-muted)" }}> 篇复盘</span>
                    </span>
                    <span>
                      <span className="font-mono font-bold">{(r.accuracy_rate * 100).toFixed(0)}%</span>
                      <span style={{ color: "var(--text-muted)" }}> 准确率</span>
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 报告详情 */}
      {report && (
        <div className="mt-6 space-y-6">
          {selectedReportId && (
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>
              查看历史报告: {formatTime(report.generated_at)}
            </div>
          )}

          {/* 概览 */}
          <div className="card">
            <h2 className="text-xl font-bold">概览</h2>
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <div className="text-2xl font-bold">
                  {report.summary.total_retros}
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>复盘总数</div>
              </div>
              <div>
                <div className="text-2xl font-bold">
                  {report.summary.calibration_samples}
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>校准样本</div>
              </div>
              <div>
                <div className="text-2xl font-bold">
                  {report.summary.rubric_version}
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>Rubric 版本</div>
              </div>
              <div>
                <div className="text-2xl font-bold">
                  {(report.accuracy.accuracy_rate * 100).toFixed(0)}%
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>预测准确率</div>
              </div>
            </div>
          </div>

          {/* 准确性分布 - PieChart */}
          <div className="card">
            <h3 className="font-semibold">预测准确性分布</h3>
            <div className="mt-3" style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={getPieData()}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={3}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {getPieData().map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend
                    wrapperStyle={{ color: CHART_COLORS.text }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* 维度相关性 - BarChart */}
          <div className="card">
            <h3 className="font-semibold">维度与播放量相关性</h3>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
              最预测性: {report.dimension_analysis.most_predictive || "N/A"} |
              最不预测性: {report.dimension_analysis.least_predictive || "N/A"}
            </p>
            <div className="mt-3" style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={getCorrelationData()}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                  <XAxis
                    type="number"
                    tick={{ fill: CHART_COLORS.text, fontSize: 12 }}
                    axisLine={{ stroke: CHART_COLORS.grid }}
                  />
                  <YAxis
                    type="category"
                    dataKey="dimension"
                    tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                    axisLine={{ stroke: CHART_COLORS.grid }}
                    width={95}
                  />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ color: CHART_COLORS.text }} />
                  <Bar
                    dataKey="correlation"
                    name="相关性"
                    radius={[0, 4, 4, 0]}
                    fill={CHART_COLORS.green}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* 维度雷达图 - RadarChart */}
          <div className="card">
            <h3 className="font-semibold">维度平均分雷达图</h3>
            <div className="mt-3" style={{ height: 350 }}>
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={getRadarData()}>
                  <PolarGrid stroke={CHART_COLORS.grid} />
                  <PolarAngleAxis
                    dataKey="dimension"
                    tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                  />
                  <PolarRadiusAxis
                    angle={90}
                    domain={[0, 5]}
                    tick={{ fill: CHART_COLORS.text, fontSize: 10 }}
                  />
                  <Radar
                    name="平均分"
                    dataKey="avg_score"
                    stroke={CHART_COLORS.green}
                    fill={CHART_COLORS.green}
                    fillOpacity={0.2}
                  />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ color: CHART_COLORS.text }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Rubric 演进 - LineChart */}
          {report.rubric_history?.length > 0 && (
            <div className="card">
              <h3 className="font-semibold">Rubric 演进历史</h3>
              <div className="mt-3" style={{ height: 280 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={getHistoryData()}>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                      axisLine={{ stroke: CHART_COLORS.grid }}
                    />
                    <YAxis
                      yAxisId="left"
                      domain={[0, 1]}
                      tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                      axisLine={{ stroke: CHART_COLORS.grid }}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                      axisLine={{ stroke: CHART_COLORS.grid }}
                    />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Legend wrapperStyle={{ color: CHART_COLORS.text }} />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="consistency"
                      name="一致性"
                      stroke={CHART_COLORS.green}
                      strokeWidth={2}
                      dot={{ fill: CHART_COLORS.green }}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="pool_size"
                      name="校准池"
                      stroke={CHART_COLORS.blue}
                      strokeWidth={2}
                      dot={{ fill: CHART_COLORS.blue }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Top/Bottom */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="card" style={{ borderColor: "rgba(34, 197, 94, 0.3)" }}>
              <h3 className="font-semibold" style={{ color: "#22c55e" }}>最佳表现 Top 3</h3>
              <ul className="mt-2 space-y-1 text-sm">
                {report.accuracy.top3.map((item) => (
                  <li key={item.script_id} className="flex justify-between">
                    <span>{item.script_id}</span>
                    <span className="font-mono">
                      {item.actual_plays} 播放
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card" style={{ borderColor: "rgba(239, 68, 68, 0.3)" }}>
              <h3 className="font-semibold" style={{ color: "#ef4444" }}>最差表现 Bottom 3</h3>
              <ul className="mt-2 space-y-1 text-sm">
                {report.accuracy.bottom3.map((item) => (
                  <li key={item.script_id} className="flex justify-between">
                    <span>{item.script_id}</span>
                    <span className="font-mono">
                      {item.actual_plays} 播放
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* LLM 洞察 */}
          {report.llm_insights && (
            <div className="card">
              <h3 className="font-semibold">AI 洞察</h3>
              <div className="mt-3 space-y-3">
                <div>
                  <span className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                    整体评估
                  </span>
                  <p className="mt-1">
                    {report.llm_insights.overall_assessment}
                  </p>
                </div>
                {report.llm_insights.key_findings?.length > 0 && (
                  <div>
                    <span className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                      关键发现
                    </span>
                    <ul className="mt-1 list-inside list-disc text-sm">
                      {report.llm_insights.key_findings.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div>
                  <span className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                    Rubric 建议
                  </span>
                  <p className="mt-1">{report.llm_insights.rubric_recommendation}</p>
                </div>
                <div>
                  <span className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>
                    内容策略
                  </span>
                  <p className="mt-1">{report.llm_insights.content_strategy}</p>
                </div>
                {report.llm_insights.risk_warnings?.length > 0 && (
                  <div>
                    <span className="text-sm font-medium" style={{ color: "#ef4444" }}>
                      风险提示
                    </span>
                    <ul className="mt-1 list-inside list-disc text-sm" style={{ color: "#ef4444" }}>
                      {report.llm_insights.risk_warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
