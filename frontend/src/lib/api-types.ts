/**
 * API 类型定义 — 与后端 Pydantic 模型保持同构
 *
 * 所有 API 响应使用同一套 TypeScript 接口，确保前后端类型一致。
 * 后端对应模型见 backend/app/models/
 */

// ---- 通用响应 ----

export interface ApiErrorResponse {
  code: string;
  message: string;
  suggested_action: string;
}

export interface ApiResponseMeta {
  response_time_ms?: number;
  schema_version?: string;
}

export interface ApiResponse<T> {
  ok: boolean;
  data?: T;
  error?: ApiErrorResponse;
  meta?: ApiResponseMeta;
}

// ---- 状态模型 ----

export interface RubricWeights {
  ER: number;
  HP: number;
  QL: number;
  NA: number;
  AB: number;
  SR: number;
  SAT: number;
  TS: number;
  MS: number;
  CC: number;
}

export interface CheatState {
  schema_version: string;
  your_project_version: string;
  rubric_version: string;
  content_form: string;
  platforms: string[];
  typical_duration_seconds: number;
  target_publish_cadence_days: number;
  baseline_plays: number | null;
  calibration_samples: number;
  last_bump_at: string | null;
  rubric_weights: RubricWeights;
  enabled_trend_sources: string[];
  pending_retros: string[];
  shoots: string[];
  in_progress_session: string | null;
  hooks_installed: boolean;
  initialized_at: string;
}

// ---- 评分模型 ----

export interface DimensionScore {
  dimension: string;
  score: number;
  confidence: number;
  reason: string;
  self_check: string;
}

export interface ScoreResult {
  dimensions: DimensionScore[];
  composite: number;
  rubric_version: string;
}

// ---- 爆款预测模型 ----

export interface ViralityDiagnosis {
  strongest_dimension: { dimension: string; score: number };
  weakest_dimension: { dimension: string; score: number };
  risks: string[];
  highlights: string[];
  composite: number;
}

export interface ViralitySuggestion {
  priority: string;
  target_dimension: string;
  action: string;
  expected_impact: string;
}

export interface ViralityBucket {
  scheme: string;
  prediction: string;
  samples: number;
}

export interface ViralityResult {
  virality_score: number;
  breakdown: Record<string, number>;
  sub_scores: Record<string, number>;
  diagnosis: ViralityDiagnosis;
  suggestions: ViralitySuggestion[];
  bucket: ViralityBucket;
  phase: string;
  phase1_baseline_score?: number;
  model_info?: {
    model_type: string;
    trained_samples?: number;
    retrained?: boolean;
  };
  feature_importance?: Record<string, number>;
  calibration_samples: number;
  timestamp: string;
}

// ---- 脚本模型 ----

export interface Script {
  id: string;
  title: string;
  content: string;
  created_at: string;
  updated_at: string;
}

// ---- 对标模型 ----

export interface Benchmark {
  name: string;
  fingerprint: string;
  traits: string[];
  patterns: string[];
  imported_at: string;
}

// ---- 热点模型 ----

export interface TrendItem {
  topic: string;
  platform: string;
  heat: number;
  tier: number;
  hook_suggestion: string;
}

// ---- Bump 模型 ----

export interface BumpResult {
  status: "accepted" | "rejected";
  reason?: string;
  consistency: number;
  old_version?: string;
  new_version?: string;
  old_weights: RubricWeights;
  new_weights?: RubricWeights;
  rubric_diff?: string;
  pool_size?: number;
  rescored?: Array<{
    script_id: string;
    old_composite: number;
    new_composite: number;
    actual_plays: number;
  }>;
}

// ---- 复盘报告模型 ----

export interface RetroReport {
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

// ---- 历史报告摘要 ----

export interface RetroReportSummary {
  report_id: string;
  generated_at: string;
  total_retros: number;
  accuracy_rate: number;
  rubric_version: string;
}

// ---- 受众画像模型 ----

export interface PersonaProfile {
  id: string;
  name: string;
  demographics: {
    age_range: string;
    occupation: string;
    region: string;
  };
  interests: string[];
  engagement_patterns: {
    why_like: string;
    why_share: string;
    why_comment: string;
  };
  content_preferences: string[];
  created_at: string;
  updated_at: string;
}

// ---- 维度标签 ----

export const DIMENSION_LABELS: Record<string, string> = {
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

// ---- 通知模型 ----
export interface Notification {
  id: string;
  type: "retro_reminder" | "bump_suggestion" | "buffer_warning" | "competitor_update";
  title: string;
  message: string;
  action_url: string;
  created_at: string;
  read: boolean;
}

export interface NotificationSummary {
  total: number;
  unread: number;
  by_type: Record<string, number>;
}

// ---- A/B 实验模型 ----
export interface ABExperiment {
  id: string;
  topic: string;
  script_a_id: string;
  script_b_id: string;
  hypothesis: string;
  status: "created" | "predicted" | "completed";
  prediction_a: Record<string, unknown> | null;
  prediction_b: Record<string, unknown> | null;
  actual_plays_a: number | null;
  actual_plays_b: number | null;
  result: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
}

// ---- 竞品监控模型 ----
export interface CompetitorMonitor {
  id: string;
  account_name: string;
  platform: string;
  check_interval_hours: number;
  last_check: string | null;
  last_content_count: number;
  new_content_detected: boolean;
  created_at: string;
}

export interface MonitorUpdate {
  monitor_id: string;
  detected_at: string;
  new_samples: string[];
  action_taken: string;
}

// ---- 内容日历模型 ----
export interface CalendarDay {
  date: string;
  weekday: string;
  is_today: boolean;
  is_weekend: boolean;
  scheduled: ScheduleItem[];
  scripts: Array<{ id: string; title: string; created_at: string }>;
  predictions: Array<{ id: string; pred_time: string; virality_score: number | null; has_retro: boolean }>;
}

export interface ScheduleItem {
  id: string;
  date: string;
  script_id: string;
  platform: string;
  notes: string;
  status: "planned" | "published" | "retro";
  created_at: string;
}

export interface CalendarData {
  days: CalendarDay[];
  suggestions: Array<{ type: string; message: string }>;
  buffer: number;
  cadence: number;
  total_scheduled: number;
}

// ---- 全链路追踪模型 ----
export interface PipelineItem {
  id: string;
  title: string;
  stages: {
    candidate: Record<string, unknown> | null;
    script: Record<string, unknown> | null;
    prediction: Record<string, unknown> | null;
    publish: Record<string, unknown> | null;
    retro: Record<string, unknown> | null;
  };
  experiment: { id: string; topic: string; role: string } | null;
  status: "draft" | "predicted" | "published" | "completed";
  timeline: Array<{ stage: string; time: string; data: Record<string, unknown> }>;
}

export interface PipelineData {
  pipelines: PipelineItem[];
  stats: { total: number; by_status: Record<string, number> };
}

// ---- 发布时间建议模型 ----
export interface PublishTimeRecommendation {
  platform: string;
  script_id: string | null;
  recommendation: {
    recommended_today: { time_slots: string[]; reason: string };
    recommended_this_week: { best_days: string[]; time_slots: string[]; reason: string };
    platform_tips: string[];
    avoid_times: string[];
    confidence: string;
  };
  historical_samples: number;
  generated_at: string;
}

// ---- 评论抓取模型 ----
export interface FetchedComment {
  text: string;
  likes: number;
  replies: number;
}

// ---- 任务队列模型 ----
export interface TaskInfo {
  task_id: string;
  task_type: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  current_phase: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

// ---- SSE 进度事件 ----
export interface SSEProgressEvent {
  phase: string;
  progress: number;
  current?: number;
  total?: number;
  result?: Record<string, unknown>;
  message?: string;
}
