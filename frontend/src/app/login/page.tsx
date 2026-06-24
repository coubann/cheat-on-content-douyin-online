"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { login, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user) {
      router.replace("/");
    }
  }, [user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!email.trim() || !password.trim()) {
      setError("请填写邮箱/用户名和密码");
      return;
    }

    setSubmitting(true);
    const result = await login(email.trim(), password);
    setSubmitting(false);

    if (result.ok) {
      router.replace("/");
    } else {
      setError(result.error || "登录失败");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
      <div className="w-full max-w-sm rounded-xl p-8" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold" style={{ color: "var(--accent)" }}>Content Studio</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>登录你的账号</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>邮箱 / 用户名</label>
            <input type="text" className="input w-full" placeholder="输入邮箱或用户名" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>密码</label>
            <input type="password" className="input w-full" placeholder="请输入密码" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <p className="text-sm" style={{ color: "#ef4444" }}>{error}</p>}
          <button type="submit" disabled={submitting} className="btn-primary w-full">{submitting ? "登录中..." : "登录"}</button>
        </form>

        <div className="mt-6 text-center text-sm" style={{ color: "var(--text-secondary)" }}>
          <span>还没有账号？</span>
          <Link href="/register" className="ml-1 underline" style={{ color: "var(--accent)" }}>立即注册</Link>
        </div>
        <div className="mt-4 text-center">
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>忘记密码？请联系管理员重置</p>
        </div>
      </div>
    </div>
  );
}
