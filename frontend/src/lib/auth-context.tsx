"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { apiFetch } from "@/lib/api";

export interface UserInfo {
  id: number;
  email: string;
  username: string;
  role: string;
  points: number;
  free_points_today: number;
  membership_type: string;
  checkin_streak: number;
  email_verified: boolean;
  invite_code: string | null;
  disabled: boolean;
  email_verified: boolean;
  guide_step: number;
  created_at: string | null;
  last_login_at: string | null;
}

interface AuthContextType {
  user: UserInfo | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  register: (
    email: string,
    username: string,
    password: string,
    confirmPassword: string,
    inviteCode?: string,
  ) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

function setStoredToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem("auth_token", token);
  } else {
    localStorage.removeItem("auth_token");
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 页面加载时从 localStorage 恢复 token 并获取用户信息
  useEffect(() => {
    const savedToken = getStoredToken();
    if (savedToken) {
      setToken(savedToken);
      fetchUser(savedToken).then((u) => {
        if (u) setUser(u);
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, []);

  const fetchUser = async (t: string): Promise<UserInfo | null> => {
    const res = await apiFetch<UserInfo>("/api/auth/me", {
      headers: { Authorization: `Bearer ${t}` },
    });
    if (res.ok && res.data) {
      return res.data;
    }
    return null;
  };

  const refreshUser = useCallback(async () => {
    const t = token || getStoredToken();
    if (!t) return;
    const u = await fetchUser(t);
    if (u) {
      setUser(u);
    }
  }, [token]);

  const login = useCallback(
    async (email: string, password: string): Promise<{ ok: boolean; error?: string }> => {
      const res = await apiFetch<{ token: string; user: UserInfo; free_points_granted?: number }>(
        "/api/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ credential: email, password }),
        },
      );
      if (res.ok && res.data) {
        setStoredToken(res.data.token);
        setToken(res.data.token);
        setUser(res.data.user);
        return { ok: true };
      }
      return { ok: false, error: res.error?.message || "登录失败" };
    },
    [],
  );

  const register = useCallback(
    async (
      email: string,
      username: string,
      password: string,
      confirmPassword: string,
      inviteCode?: string,
    ): Promise<{ ok: boolean; error?: string }> => {
      const body: Record<string, unknown> = {
        email,
        username,
        password,
        confirm_password: confirmPassword,
      };
      if (inviteCode) body.invite_code = inviteCode;

      const res = await apiFetch<{ token: string; user: UserInfo }>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (res.ok && res.data) {
        setStoredToken(res.data.token);
        setToken(res.data.token);
        setUser(res.data.user);
        return { ok: true };
      }
      return { ok: false, error: res.error?.message || "注册失败" };
    },
    [],
  );

  const logout = useCallback(() => {
    setStoredToken(null);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, token, loading, login, register, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
