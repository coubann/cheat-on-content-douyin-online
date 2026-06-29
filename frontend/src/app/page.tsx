"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import AnnouncementBanner from "@/components/AnnouncementBanner";
import GuideCard from "@/components/GuideCard";
import LlmStatusDot from "@/components/LlmStatusDot";
import CheckinButton from "@/components/CheckinButton";
import Link from "next/link";

interface StatusData {
  initialized: boolean;
  calibration_samples: number;
  rubric_version: string;
  buffer_color: string;
  confidence_level: string;
  pending_retros: number;
  bump_suggested: boolean;
  bump_trigger_type: string | null;
  bump_trigger_reason: string;
  shoots_in_buffer: number;
  in_progress_session: string | null;
  content_form: string;
  platforms: string[];
}

interface NotificationSummary {
  pending_retros: number;
  bump_suggestions: number;
  low_buffer_warnings: number;
  total_unread: number;
}

interface ProviderSettings {
  providers: { name: string; label: string; configured: boolean; model: string }[];
  default_provider: string;
  any_configured: boolean;
}

export default function HomePage() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [llmReady, setLlmReady] = useState<boolean | null>(null);
  const [configuredProviders, setConfiguredProviders] = useState<{ name: string; label: string; model: string }[]>([]);
  const [currentProvider, setCurrentProvider] = useState<string>("");
  const [switching, setSwitching] = useState(false);
  const [notifSummary, setNotifSummary] = useState<NotificationSummary | null>(null);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);
  const searchParams = useSearchParams();

  // 邮箱验证结果提示
  useEffect(() => {
    const v = searchParams.get("verify");
    if (v === "success") setVerifyMsg("✅ 邮箱验证成功！");
    else if (v === "already") setVerifyMsg("📧 该邮箱已验证过");
    else if (v === "fail") setVerifyMsg("❌ 验证链接无效或已过期");
    if (v) {
      // 3 秒后清除提示（并去掉 URL 参数）
      setTimeout(() => {
        setVerifyMsg(null);
        window.history.replaceState({}, "", "/");
      }, 5000);
    }
  }, [searchParams]);
    apiFetch<StatusData>("/api/status").then((res) => {
      if (res.ok && res.data) setStatus(res.data);
    });
    apiFetch<ProviderSettings>("/api/settings/providers").then((res) => {
      if (res.ok && res.data) {
        const d = res.data;
        setLlmReady(d.any_configured);
        setConfiguredProviders(d.providers.filter((p) => p.configured));
        setCurrentProvider(d.default_provider);
        const defaultP = d.providers.find((p) => p.name === d.default_provider);
        if (defaultP) {
          // default provider info is now in configuredProviders
        }
      }
    });
    apiFetch<NotificationSummary>("/api/notifications/summary").then((res) => {
      if (res.ok && res.data) setNotifSummary(res.data);
    });
  }, []);

  const handleSwitchProvider = async (providerName: string) => {
    setSwitching(true);
    const res = await apiFetch("/api/settings/default-provider", {
      method: "PUT",
      body: JSON.stringify({ provider: providerName }),
    });
    if (res.ok) {
      setCurrentProvider(providerName);
    }
    setSwitching(false);
  };

  const modules = [
    { href: "/predict", title: "爆款预测", desc: "盲打分 + 爆款指数 + 诊断建议", icon: "◈", color: "#22c55e" },
    { href: "/predictions", title: "已预测", desc: "查看所有预测结果和详情", icon: "◉", color: "#22c55e" },
    { href: "/scripts", title: "脚本管理", desc: "创建/编辑/管理口播文案", icon: "▤", color: "#3b82f6" },
    { href: "/benchmark", title: "对标风格", desc: "导入对标账号 → 模仿风格生成文案", icon: "◇", color: "#a855f7" },
    { href: "/trends", title: "热点选题", desc: "多平台热点 + 智能选题推荐", icon: "⟁", color: "#f59e0b" },
    { href: "/publish", title: "发布复盘", desc: "拍摄登记 → 发布 → T+N 复盘", icon: "↻", color: "#ec4899" },
    { href: "/status", title: "状态看板", desc: "Buffer / 置信度 / 今日待办", icon: "◫", color: "#06b6d4" },
    { href: "/bump", title: "Rubric 升级", desc: "校准池重打 → 排序一致性审计", icon: "⇡", color: "#22c55e" },
    { href: "/seed", title: "智能选题", desc: "多源信号融合 → 选题推荐", icon: "✦", color: "#f59e0b" },
    { href: "/persona", title: "受众画像", desc: "评论分析 → 受众特征画像", icon: "◎", color: "#a855f7" },
    { href: "/report", title: "复盘报告", desc: "自动化复盘 + 洞察分析", icon: "▤", color: "#3b82f6" },
  ];

  return (
    <div>
      <AnnouncementBanner />

      {user && !user.email_verified && (
        <div className="mb-4 rounded-lg px-5 py-4 text-sm" style={{ background: "rgba(239,68,68,0.12)", border: "2px solid rgba(239,68,68,0.4)", color: "#ef4444" }}>
          <div className="flex items-center gap-3">
            <span className="text-xl">⚠️</span>
            <div className="flex-1">
              <p className="font-semibold text-base">邮箱尚未验证</p>
              <p className="mt-1" style={{ color: "rgba(239,68,68,0.75)" }}>请查收注册邮箱中的验证邮件，点击链接完成验证后即可使用全部功能。</p>
            </div>
          </div>
        </div>
      )}

      {verifyMsg && (
        <div className="mb-4 rounded-lg px-4 py-3 text-sm font-medium text-center" style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.3)", color: "#22C55E" }}>
          {verifyMsg}
        </div>
      )}

      <GuideCard onClose={() => {}} />
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          <span className="text-glow">Content Studio</span>
        </h1>
        <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          基于 cheat-on-content 的爆款预测系统 — Score → Blind-predict → Publish → Retro → Evolve
        </p>
      </div>

      {/* Status bar with LLM dot & Checkin */}
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
          <LlmStatusDot />
          <span>AI 状态</span>
        </div>
        <CheckinButton />
      </div>

      {/* Status bar */}
      <div className="mb-8 flex flex-wrap gap-4">
        {/* LLM Provider 切换 */}
        {configuredProviders.length > 0 && (
          <div className="card flex items-center gap-3">
            <LlmStatusDot />
            <span className="text-sm font-medium" style={{ color: "var(--accent)" }}>LLM 已配置</span>
            <select
              className="select text-xs py-1 px-2"
              value={currentProvider}
              disabled={switching}
              onChange={(e) => handleSwitchProvider(e.target.value)}
            >
              {configuredProviders.map((p) => (
                <option key={p.name} value={p.name}>{p.label} · {p.model}</option>
              ))}
            </select>
          </div>
        )}
        {!llmReady && (
          <div className="card flex items-center gap-3" style={{ borderColor: "rgba(239,68,68,0.3)" }}>
            <LlmStatusDot />
            <span className="text-sm font-medium" style={{ color: "#ef4444" }}>LLM 未配置</span>
          </div>
        )}
        <div className="card flex items-center gap-3">
          <div className="h-2 w-2 rounded-full" style={{ background: status?.initialized ? "#22c55e" : "#ef4444" }} />
          <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {status?.initialized ? "已初始化" : "未初始化"}
          </span>
        </div>
        <div className="card flex items-center gap-3">
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>校准样本</span>
          <span className="text-sm font-medium text-glow">{status?.calibration_samples ?? 0}</span>
        </div>
        <div className="card flex items-center gap-3">
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>Rubric</span>
          <span className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>{status?.rubric_version ?? "—"}</span>
        </div>
        <div className="card flex items-center gap-3">
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>置信度</span>
          <span className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>{status?.confidence_level ?? "—"}</span>
        </div>
        {status?.pending_retros != null && status.pending_retros > 0 && (
          <div className="card flex items-center gap-3">
            <span className="badge badge-red">待复盘</span>
            <span className="text-sm font-medium" style={{ color: "#ef4444" }}>{status.pending_retros}</span>
          </div>
        )}
        {notifSummary && notifSummary.total_unread > 0 && (
          <div className="card flex items-center gap-3">
            <span className="badge badge-red">通知</span>
            <span className="text-sm font-medium" style={{ color: "#ef4444" }}>{notifSummary.total_unread} 未读</span>
          </div>
        )}
        {status?.bump_suggested && (
          <div className="card flex items-center gap-3">
            <span className="badge" style={{ background: "rgba(234,179,8,0.2)", color: "#eab308" }}>Rubric 升级</span>
            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {status.bump_trigger_type ? `${status.bump_trigger_type}: ` : ""}{status.bump_trigger_reason}
            </span>
          </div>
        )}
      </div>

      {/* Module grid */}
      <div className="grid grid-cols-3 gap-4">
        {modules.map((m) => (
          <a
            key={m.href}
            href={m.href}
            className="card group relative overflow-hidden"
          >
            {/* Glow effect on hover */}
            <div
              className="absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
              style={{ background: `radial-gradient(circle at 30% 30%, ${m.color}10, transparent 70%)` }}
            />
            <div className="relative z-10">
              <div className="flex items-center gap-3">
                <span className="text-2xl" style={{ color: m.color }}>{m.icon}</span>
                <h3 className="font-semibold" style={{ color: "var(--text-primary)" }}>{m.title}</h3>
              </div>
              <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>{m.desc}</p>
            </div>
          </a>
        ))}
      </div>

      {/* Methodology reminder */}
      <div className="mt-8 card" style={{ borderColor: "var(--border-accent)" }}>
        <h3 className="text-sm font-semibold text-glow">三条不可妥协原则</h3>
        <div className="mt-3 grid grid-cols-3 gap-4 text-sm" style={{ color: "var(--text-secondary)" }}>
          <div>
            <span className="font-medium" style={{ color: "#22c55e" }}>01</span> 盲预测 immutable — 预测段一旦写入不可修改
          </div>
          <div>
            <span className="font-medium" style={{ color: "#22c55e" }}>02</span> Bump = 全量重打 — 排序一致性 &lt; 0.8 则升级被拒
          </div>
          <div>
            <span className="font-medium" style={{ color: "#22c55e" }}>03</span> Rubric 是工作台 — 被推翻的观察要删除
          </div>
        </div>
      </div>
    </div>
  );
}
