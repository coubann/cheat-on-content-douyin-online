"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

export default function RegisterPage() {
  const router = useRouter();
  const { register, user } = useAuth();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
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

    if (!email.trim()) { setError("请输入邮箱"); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError("邮箱格式不正确"); return; }
    if (!username.trim() || username.trim().length < 2 || username.trim().length > 20) { setError("用户名长度需在 2-20 字符之间"); return; }
    if (password.length < 8) { setError("密码至少 8 位"); return; }
    if (password !== confirmPassword) { setError("两次密码输入不一致"); return; }

    setSubmitting(true);
    const result = await register(email.trim(), username.trim(), password, confirmPassword, inviteCode.trim() || undefined);
    setSubmitting(false);

    if (!result.ok) {
      setError(result.error || "注册失败");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
      <div className="w-full max-w-sm rounded-xl p-8" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold" style={{ color: "var(--accent)" }}>Content Studio</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>创建你的账号</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>邮箱</label>
            <input type="email" className="input w-full" placeholder="请输入邮箱" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>用户名</label>
            <input type="text" className="input w-full" placeholder="2-20 个字符" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>密码</label>
            <input type="password" className="input w-full" placeholder="至少 8 位" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>确认密码</label>
            <input type="password" className="input w-full" placeholder="再次输入密码" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
              邀请码<span className="ml-1 text-xs" style={{ color: "var(--text-muted)" }}>（选填）</span>
            </label>
            <input type="text" className="input w-full" placeholder="输入邀请码（如有）" value={inviteCode} onChange={(e) => setInviteCode(e.target.value.toUpperCase())} />
          </div>
          {error && <p className="text-sm" style={{ color: "#ef4444" }}>{error}</p>}
          <button type="submit" disabled={submitting} className="btn-primary w-full">{submitting ? "注册中..." : "注册"}</button>
        </form>
        <div className="mt-6 text-center text-sm" style={{ color: "var(--text-secondary)" }}>
          <span>已有账号？</span>
          <Link href="/login" className="ml-1 underline" style={{ color: "var(--accent)" }}>立即登录</Link>
        </div>
      </div>
    </div>
  );
}
