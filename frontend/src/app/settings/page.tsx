"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function SettingsRedirect() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    // 管理员去管理后台，普通用户去首页
    if (user?.role === "admin") {
      router.replace("/admin");
    } else {
      router.replace("/");
    }
  }, [user, loading, router]);

  return (
    <div
      className="flex min-h-[60vh] items-center justify-center"
      style={{ color: "var(--text-muted)" }}
    >
      <p className="text-sm">跳转中...</p>
    </div>
  );
}
