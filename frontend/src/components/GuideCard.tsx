"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import Link from "next/link";

const GUIDE_STEPS = [
  { step: 0, label: "管理员已配置 AI 模型", done: true, href: null },
  { step: 1, label: "分析你的第一条脚本", href: "/predict", cost: "10点" },
  { step: 2, label: "生成你的第一条文案", href: "/predictions", cost: "20点" },
  { step: 3, label: "查看爆款预测", href: "/predict", cost: "" },
];

const GUIDE_TITLE: Record<number, string> = {
  0: "🎉 欢迎使用 Content Studio！",
  1: "👏 继续下一步！",
  2: "📈 快完成了！",
  3: "🚀 已经是老用户了！",
};

interface GuideCardProps {
  onClose: (permanent: boolean) => void;
}

export default function GuideCard({ onClose }: GuideCardProps) {
  const { user, token, refreshUser } = useAuth();
  const [guideStep, setGuideStep] = useState(0);
  const [showCloseOptions, setShowCloseOptions] = useState(false);
  const [sessionDismissed, setSessionDismissed] = useState(false);

  useEffect(() => {
    if (user) {
      setGuideStep(user.guide_step || 0);
    }
  }, [user]);

  // 检查 localStorage 中是否有本次关闭标记
  useEffect(() => {
    const sd = localStorage.getItem("guide_session_dismissed");
    if (sd === "true") setSessionDismissed(true);
  }, []);

  // 老用户或永久关闭或本次关闭 → 不显示
  if (guideStep >= 3 || user?.guide_step === undefined) return null;
  if (sessionDismissed) return null;

  const handleDismiss = async (permanent: boolean) => {
    if (permanent) {
      // 调用 API 永久关闭
      await apiFetch("/api/auth/guide-status", {
        method: "PUT",
        body: JSON.stringify({ dismissed: true }),
        headers: { Authorization: `Bearer ${token}` },
      });
      await refreshUser();
    } else {
      // 本次关闭 → localStorage 标记
      localStorage.setItem("guide_session_dismissed", "true");
    }
    setSessionDismissed(true);
    onClose(permanent);
  };

  return (
    <div
      className="card mb-6 relative overflow-hidden"
      style={{
        borderColor: "rgba(34, 197, 94, 0.3)",
        background: "linear-gradient(135deg, rgba(34,197,94,0.05) 0%, transparent 100%)",
      }}
    >
      {/* 关闭按钮 */}
      <button
        onClick={() => setShowCloseOptions(!showCloseOptions)}
        className="absolute right-3 top-3 text-xs px-2 py-1 rounded"
        style={{ color: "var(--text-muted)", background: "rgba(0,0,0,0.2)" }}
      >
        关闭
      </button>

      {showCloseOptions ? (
        <div className="space-y-3 py-4">
          <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            是否关闭操作指引？
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => handleDismiss(false)}
              className="btn-ghost text-xs px-4 py-2"
            >
              本次关闭
            </button>
            <button
              onClick={() => handleDismiss(true)}
              className="btn-ghost text-xs px-4 py-2"
              style={{ color: "#ef4444" }}
            >
              永久关闭
            </button>
            <button
              onClick={() => setShowCloseOptions(false)}
              className="btn-ghost text-xs px-4 py-2"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <div>
          <h3 className="text-sm font-semibold mb-3">
            {GUIDE_TITLE[guideStep] || "操作指引"}
          </h3>
          <div className="space-y-2">
            {GUIDE_STEPS.map((s) => {
              const isPast = s.step <= guideStep;
              return (
                <div key={s.step} className="flex items-center gap-3 text-sm">
                  <span
                    className="flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold"
                    style={{
                      background: isPast ? "rgba(34,197,94,0.2)" : "rgba(255,255,255,0.1)",
                      color: isPast ? "var(--accent)" : "var(--text-muted)",
                    }}
                  >
                    {isPast ? "✓" : s.step + 1}
                  </span>
                  <span
                    className="flex-1"
                    style={{
                      color: isPast ? "var(--text-primary)" : "var(--text-secondary)",
                    }}
                  >
                    {s.label}
                  </span>
                  {s.cost && !isPast && (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      ({s.cost})
                    </span>
                  )}
                  {!isPast && s.href && (
                    <Link
                      href={s.href}
                      className="text-xs font-medium underline"
                      style={{ color: "var(--accent)" }}
                    >
                      去使用
                    </Link>
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
