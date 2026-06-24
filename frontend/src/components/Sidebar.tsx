"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import MembershipBadge from "@/components/MembershipBadge";

const NAV_ITEMS = [
  { href: "/", label: "控制台", icon: "⌂" },
  { href: "/predict", label: "爆款预测", icon: "⚡" },
  { href: "/predictions", label: "已预测", icon: "📊" },
  { href: "/scripts", label: "脚本管理", icon: "📝" },
  { href: "/benchmark", label: "对标风格", icon: "🎯" },
  { href: "/seed", label: "热点选题", icon: "🔥" },
  { href: "/publish", label: "发布复盘", icon: "🚀" },
  { href: "/pipeline", label: "全链路", icon: "🔗" },
  { href: "/calendar", label: "内容日历", icon: "📅" },
  { href: "/experiments", label: "A/B 实验", icon: "🧪" },
  { href: "/monitors", label: "竞品监控", icon: "👁" },
  { href: "/status", label: "状态看板", icon: "📈" },
  { href: "/bump", label: "Rubric 升级", icon: "⬆" },
  { href: "/report", label: "复盘报告", icon: "📋" },
  { href: "/persona", label: "受众画像", icon: "👤" },
  { href: "/trends", label: "趋势分析", icon: "📡" },
];

const MEMBERSHIP_COLORS: Record<string, string> = {
  none: "#9CA3AF",
  basic: "#22C55E",
  standard: "#F59E0B",
  premium: "#A855F7",
};

const MEMBERSHIP_LABELS: Record<string, string> = {
  none: "",
  basic: "B",
  standard: "S",
  premium: "P",
};

export default function Sidebar() {
  const pathname = usePathname();
  const { user, token, loading } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [retroCount, setRetroCount] = useState(0);
  const [bumpCount, setBumpCount] = useState(0);
  const isAuthPage = pathname === "/login" || pathname === "/register";

  // 轮询通知（无条件调用 hooks，放在 early return 之前）
  useEffect(() => {
    if (isAuthPage) return; // 登录页不轮询
    const poll = async () => {
      // 只在标签页可见时轮询
      if (document.visibilityState !== "visible") return;
      try {
        const res = await apiFetch<{ retro_needed_count?: number; bump_suggestion_count?: number }>(
          "/api/notifications/summary",
        );
        if (res.ok && res.data) {
          setRetroCount(res.data.retro_needed_count ?? 0);
          setBumpCount(res.data.bump_suggestion_count ?? 0);
        }
      } catch {
        /* ignore */
      }
    };
    poll();
    // 只在标签可见时才启动定时器
    const onVisible = () => {
      poll();
      clearInterval(interval);
      interval = setInterval(poll, 60000);
    };
    let interval = setInterval(poll, 60000);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const handleNavClick = () => setMobileOpen(false);

  // 登录/注册页不渲染侧边栏（hooks 已无条件调用，放在这里不会导致 hooks 数量变化）
  if (isAuthPage) return null;

  return (
    <>
      {/* Mobile hamburger */}
      <button
        className="fixed left-4 top-4 z-50 rounded-lg p-2 md:hidden"
        onClick={() => setMobileOpen(!mobileOpen)}
        style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
      >
        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={mobileOpen ? "M6 18L18 6M6 6l12 12" : "M4 6h16M4 12h16M4 18h16"} />
        </svg>
      </button>

      {/* Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 z-40 flex h-full w-56 flex-col transition-transform md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ background: "var(--bg-card)", borderRight: "1px solid var(--border)" }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 py-4 border-b" style={{ borderColor: "var(--border)" }}>
          <span className="text-xl" style={{ color: "var(--accent)" }}>◇</span>
          <span className="text-sm font-bold tracking-tight">Content Studio</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));

            // 跳过系统设置
            if (item.href === "/settings") return null;

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={handleNavClick}
                className={`nav-item flex items-center gap-3 ${
                  isActive ? "nav-active" : ""
                }`}
              >
                <span className="w-5 text-center text-sm">{item.icon}</span>
                <span className="flex-1 text-sm">{item.label}</span>
                {/* 通知徽章 */}
                {item.href === "/publish" && retroCount > 0 && (
                  <span className="badge badge-red text-xs px-1.5">{retroCount}</span>
                )}
                {item.href === "/bump" && bumpCount > 0 && (
                  <span className="badge badge-yellow text-xs px-1.5">{bumpCount}</span>
                )}
              </Link>
            );
          })}

          {/* 管理员入口（仅 admin 可见） */}
          {user?.role === "admin" && (
            <Link
              href="/admin"
              onClick={handleNavClick}
              className={`nav-item flex items-center gap-3 ${
                pathname.startsWith("/admin") ? "nav-active" : ""
              }`}
            >
              <span className="w-5 text-center text-sm">⚙</span>
              <span className="flex-1 text-sm">管理后台</span>
            </Link>
          )}
        </nav>

        {/* User info at bottom */}
        <div
          className="px-4 py-3 border-t"
          style={{ borderColor: "var(--border)" }}
        >
          {!loading && user ? (
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold"
                  style={{ background: "rgba(34,197,94,0.15)", color: "var(--accent)" }}
                >
                  {user.username.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{user.username}</p>
                  <div className="flex items-center gap-1">
                    {user.role === "admin" && (
                      <span
                        className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                        style={{ background: "rgba(59,130,246,0.15)", color: "#3B82F6" }}
                      >
                        Admin
                      </span>
                    )}
                    {user.membership_type !== "none" && (
                      <MembershipBadge type={user.membership_type} />
                    )}
                  </div>
                </div>
                <Link
                  href="/profile"
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    color: "var(--text-muted)",
                    background: "var(--bg-primary)",
                  }}
                >
                  个人
                </Link>
              </div>
              <div className="flex gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
                <span>免费: <span style={{ color: "var(--accent)" }}>{user.free_points_today}</span></span>
                <span>点数: {user.points}</span>
              </div>
              <div className="flex gap-2 mt-1">
                <Link
                  href="/invite"
                  className="text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  邀请
                </Link>
                <Link
                  href="/profile"
                  className="text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  个人中心
                </Link>
              </div>
            </div>
          ) : !loading && !user ? (
            <Link
              href="/login"
              className="flex items-center justify-center gap-2 py-2 text-sm rounded-lg transition-colors font-medium"
              style={{
                color: "var(--accent)",
                border: "1px solid rgba(34,197,94,0.3)",
                background: "rgba(34,197,94,0.08)",
              }}
            >
              登录 / 注册
            </Link>
          ) : null}
          <p className="mt-1 text-xs text-center" style={{ color: "var(--text-muted)" }}>
            v0.2.0
          </p>
        </div>
      </aside>
    </>
  );
}
