"use client";

import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useEffect, useState } from "react";

const PUBLIC_PATHS = ["/login", "/register"];

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [showLoading, setShowLoading] = useState(true);

  const isPublicPath = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (loading) return;  // 等待 auth 初始化

    if (!user && !isPublicPath) {
      router.replace("/login");
    } else {
      setShowLoading(false);
    }
  }, [user, loading, isPublicPath, router]);

  // 加载中：显示空白 loading，避免闪烁
  if (loading || showLoading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: "var(--bg-primary)" }}
      >
        <div className="text-center space-y-3">
          <div
            className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-transparent"
            style={{
              borderTopColor: "var(--accent)",
              borderRightColor: "var(--accent)",
            }}
          />
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            加载中...
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
