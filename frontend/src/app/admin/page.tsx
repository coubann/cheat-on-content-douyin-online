"use client";

import React from "react";
import { useAuth } from "@/lib/auth-context";
import { useState, useEffect, useCallback, Fragment } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

// ---- Error Boundary ----
class AdminErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("=== AdminPage Error ===");
    console.error("Message:", error.message);
    console.error("Stack:", error.stack);
    console.error("Component Stack:", info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-6 max-w-2xl mx-auto">
          <h2 className="text-lg font-bold text-red-500 mb-3">页面出错</h2>
          <pre className="text-sm p-4 rounded overflow-auto max-h-60" style={{ background: "var(--bg-secondary)", color: "var(--text-secondary)" }}>
            {this.state.error.message}
            {"\n\n"}
            {this.state.error.stack}
          </pre>
          <button onClick={() => this.setState({ error: null })} className="btn-primary mt-4">
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const MEMBERSHIP_OPTIONS = [
  { value: "none", label: "无会员" },
  { value: "basic", label: "Basic" },
  { value: "standard", label: "Standard" },
  { value: "premium", label: "Premium" },
];

const STATUS_OPTIONS = [
  { value: "", label: "全部" },
  { value: "paid", label: "已支付" },
  { value: "pending", label: "待支付" },
];

type TabKey = "users" | "llm" | "config" | "announcements" | "orders";

interface PaginatedData<T> {
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  data: T[];
}

interface OrderUser {
  id: number;
  username: string;
  email: string;
}

interface OrderItem {
  id: number;
  user_id: number;
  out_trade_no: string;
  ifdian_order_id: string | null;
  tier: string;
  amount: number;
  amount_yuan: number;
  points_granted: number;
  status: string;
  created_at: string | null;
  paid_at: string | null;
  user: OrderUser;
}

interface UserItem {
  id: number;
  username: string;
  email: string;
  role: string;
  points: number;
  free_points_today: number;
  membership_type: string;
  checkin_streak: number;
  invite_code: string | null;
  disabled: boolean;
  created_at: string | null;
  last_login_at: string | null;
  order_count: number;
  paid_order_count: number;
  total_spent: number;
}

function Pagination({
  page,
  totalPages,
  onPrev,
  onNext,
  onGo,
}: {
  page: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
  onGo: (p: number) => void;
}) {
  if (totalPages <= 1) return null;

  const pages: (number | "...")[] = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  if (start > 1) {
    pages.push(1);
    if (start > 2) pages.push("...");
  }
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < totalPages) {
    if (end < totalPages - 1) pages.push("...");
    pages.push(totalPages);
  }

  return (
    <div className="flex items-center justify-center gap-1 pt-3">
      <button
        onClick={onPrev}
        disabled={page <= 1}
        className="px-3 py-1 text-xs rounded transition-all disabled:opacity-30"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
      >
        ‹ 上一页
      </button>
      {pages.map((p, i) =>
        p === "..." ? (
          <span key={`ellipsis-${i}`} className="px-2 text-xs" style={{ color: "var(--text-muted)" }}>...</span>
        ) : (
          <button
            key={p}
            onClick={() => onGo(p)}
            className="px-3 py-1 text-xs rounded transition-all"
            style={{
              border: "1px solid var(--border)",
              background: page === p ? "var(--accent)" : "transparent",
              color: page === p ? "#fff" : "var(--text-secondary)",
            }}
          >
            {p}
          </button>
        )
      )}
      <button
        onClick={onNext}
        disabled={page >= totalPages}
        className="px-3 py-1 text-xs rounded transition-all disabled:opacity-30"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
      >
        下一页 ›
      </button>
    </div>
  );
}

export default function AdminPageWrapper() {
  return (
    <AdminErrorBoundary>
      <AdminPage />
    </AdminErrorBoundary>
  );
}

function AdminPage() {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<TabKey>("users");
  const [users, setUsers] = useState<UserItem[]>([]);
  const [announcements, setAnnouncements] = useState<Array<Record<string, unknown>>>([]);
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [editingUser, setEditingUser] = useState<Record<string, unknown> | null>(null);
  const [editForm, setEditForm] = useState<Record<string, unknown>>({});
  const [message, setMessage] = useState<{ type: "ok" | "error"; text: string } | null>(null);
  const [annForm, setAnnForm] = useState({ title: "", content: "", type: "info" });

  // ---- Pagination & filters: orders ----
  const [ordersPage, setOrdersPage] = useState(1);
  const [ordersTotal, setOrdersTotal] = useState(0);
  const [ordersTotalPages, setOrdersTotalPages] = useState(0);
  const [ordersSearch, setOrdersSearch] = useState("");
  const [ordersStatus, setOrdersStatus] = useState("");
  const [ordersLoading, setOrdersLoading] = useState(false);

  // ---- Pagination & filters: users ----
  const [usersPage, setUsersPage] = useState(1);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersTotalPages, setUsersTotalPages] = useState(0);
  const [usersSearch, setUsersSearch] = useState("");
  const [usersLoading, setUsersLoading] = useState(false);

  // ---- Expanded user row ----
  const [expandedUserId, setExpandedUserId] = useState<number | null>(null);
  const [userOrders, setUserOrders] = useState<Record<number, OrderItem[]>>({});
  const [userOrdersLoading, setUserOrdersLoading] = useState(false);

  useEffect(() => {
    if (!loading) {
      if (!user) {
        router.replace("/login");
        return;
      }
      if (user.role !== "admin") {
        router.replace("/");
      }
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (!token) return;
    loadAnnouncements();
    loadConfig();
    loadLlmProviders();
  }, [token]);

  // Load orders when page / filter / search changes
  useEffect(() => {
    if (!token) return;
    loadOrders();
  }, [token, ordersPage, ordersStatus, ordersSearch]);

  // Load users when page / search changes
  useEffect(() => {
    if (!token) return;
    loadUsers();
  }, [token, usersPage, usersSearch]);

  const authHeaders = () => ({ Authorization: `Bearer ${token}` });

  const loadOrders = useCallback(async () => {
    setOrdersLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(ordersPage));
      params.set("per_page", "20");
      if (ordersStatus) params.set("status", ordersStatus);
      if (ordersSearch.trim()) params.set("search", ordersSearch.trim());

      const res = await apiFetch<PaginatedData<OrderItem>>(`/api/admin/orders?${params.toString()}`, {
        headers: authHeaders(),
      });
      if (res.ok && res.data) {
        setOrders(res.data.data);
        setOrdersTotal(res.data.total);
        setOrdersTotalPages(res.data.total_pages);
      }
    } finally {
      setOrdersLoading(false);
    }
  }, [ordersPage, ordersStatus, ordersSearch, token]);

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(usersPage));
      params.set("per_page", "20");
      if (usersSearch.trim()) params.set("search", usersSearch.trim());

      const res = await apiFetch<PaginatedData<UserItem>>(`/api/admin/users?${params.toString()}`, {
        headers: authHeaders(),
      });
      if (res.ok && res.data) {
        setUsers(res.data.data);
        setUsersTotal(res.data.total);
        setUsersTotalPages(res.data.total_pages);
      }
    } finally {
      setUsersLoading(false);
    }
  }, [usersPage, usersSearch, token]);

  const loadAnnouncements = async () => {
    const res = await apiFetch<Array<Record<string, unknown>>>("/api/admin/announcements", {
      headers: authHeaders(),
    });
    if (res.ok && res.data) setAnnouncements(res.data);
  };

  const loadConfig = async () => {
    const res = await apiFetch<Record<string, string>>("/api/admin/config", {
      headers: authHeaders(),
    });
    if (res.ok && res.data) setConfigs(res.data);
  };

  const toggleUserOrders = async (userId: number) => {
    if (expandedUserId === userId) {
      setExpandedUserId(null);
      return;
    }
    setExpandedUserId(userId);
    if (userOrders[userId]) return; // already loaded

    setUserOrdersLoading(true);
    try {
      const res = await apiFetch<OrderItem[]>(`/api/admin/users/${userId}/orders`, {
        headers: authHeaders(),
      });
      if (res.ok && res.data) {
        setUserOrders((prev) => ({ ...prev, [userId]: res.data as OrderItem[] }));
      }
    } finally {
      setUserOrdersLoading(false);
    }
  };

  const handleEditUser = (u: Record<string, unknown>) => {
    setEditingUser(u);
    setEditForm({
      points: u.points as number,
      membership_type: u.membership_type as string,
      disabled: u.disabled as boolean,
      email_verified: u.email_verified as boolean,
      new_password: "",
    });
    setMessage(null);
  };

  const handleSaveUser = async () => {
    if (!editingUser) return;
    const body: Record<string, unknown> = {};
    if (editForm.points !== undefined) body.points = editForm.points;
    if (editForm.membership_type !== undefined) body.membership_type = editForm.membership_type;
    if (editForm.disabled !== undefined) body.disabled = editForm.disabled;
    if (editForm.email_verified !== undefined) body.email_verified = editForm.email_verified;
    if ((editForm.new_password as string)?.trim()) body.new_password = editForm.new_password;

    const res = await apiFetch(`/api/admin/users/${editingUser.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
      headers: authHeaders(),
    });
    if (res.ok) {
      setMessage({ type: "ok", text: "更新成功" });
      setEditingUser(null);
      loadUsers();
    } else {
      setMessage({ type: "error", text: res.error?.message || "更新失败" });
    }
  };

  const handleCreateAnnouncement = async () => {
    if (!annForm.title.trim() || !annForm.content.trim()) return;
    const res = await apiFetch("/api/admin/announcements", {
      method: "POST",
      body: JSON.stringify(annForm),
      headers: authHeaders(),
    });
    if (res.ok) {
      setAnnForm({ title: "", content: "", type: "info" });
      loadAnnouncements();
    }
  };

  const handleDeleteAnnouncement = async (id: number) => {
    const res = await apiFetch(`/api/admin/announcements/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (res.ok) loadAnnouncements();
  };

  // ---- LLM 配置 ----
  const [llmProviders, setLlmProviders] = useState<Array<Record<string, unknown>>>([]);
  const [llmDefaultProvider, setLlmDefaultProvider] = useState("");
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmTesting, setLlmTesting] = useState<string | null>(null);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmMessage, setLlmMessage] = useState<{ type: "ok" | "error"; text: string } | null>(null);

  const loadLlmProviders = async () => {
    const res = await apiFetch<{ providers: Array<Record<string, unknown>>; default_provider: string }>(
      "/api/admin/llm-providers", { headers: authHeaders() }
    );
    if (res.ok && res.data) {
      setLlmProviders(res.data.providers);
      setLlmDefaultProvider(res.data.default_provider);
    }
  };

  const handleEditProvider = (name: string) => {
    const p = llmProviders.find((x) => x.name === name);
    setEditingProvider(name);
    setLlmApiKey("");
    setLlmModel((p?.model as string) || "");
    setLlmBaseUrl((p?.base_url as string) || "");
    setLlmMessage(null);
  };

  const handleSaveProvider = async () => {
    if (!editingProvider) return;
    setLlmSaving(true);
    setLlmMessage(null);
    const body: Record<string, string> = {};
    if (llmApiKey.trim()) body.api_key = llmApiKey.trim();
    if (llmModel.trim()) body.model = llmModel.trim();
    if (llmBaseUrl.trim()) body.base_url = llmBaseUrl.trim();

    const res = await apiFetch(`/api/admin/llm-providers/${editingProvider}`, {
      method: "PUT", body: JSON.stringify(body), headers: authHeaders(),
    });
    if (res.ok) {
      setLlmMessage({ type: "ok", text: "保存成功" });
      setLlmApiKey("");
      await loadLlmProviders();
    } else {
      setLlmMessage({ type: "error", text: res.error?.message || "保存失败" });
    }
    setLlmSaving(false);
  };

  const handleTestProvider = async (name: string) => {
    setLlmTesting(name);
    const res = await apiFetch(`/api/admin/llm-providers/${name}/test`, {
      method: "POST", body: "{}", headers: authHeaders(),
    });
    if (res.ok) {
      setLlmMessage({ type: "ok", text: `${name}: 连接成功 ✅` });
    } else {
      setLlmMessage({ type: "error", text: `${name}: 连接失败 ❌` });
    }
    setLlmTesting(null);
  };

  if (loading || !user) {
    return <div className="py-20 text-center" style={{ color: "var(--text-secondary)" }}>加载中...</div>;
  }

  const statusBadge = (status: string) => {
    if (status === "paid") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
          style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e" }}>
          ✅ 已支付
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
        style={{ background: "rgba(245,158,11,0.15)", color: "#f59e0b" }}>
        ⏳ 待支付
      </span>
    );
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">
        <span className="text-glow">管理员后台</span>
      </h1>

      {/* Tabs */}
      <div className="flex gap-1 border-b" style={{ borderColor: "var(--border)" }}>
        {[
          { key: "users", label: "用户管理" },
          { key: "llm", label: "LLM 配置" },
          { key: "config", label: "系统配置" },
          { key: "announcements", label: "公告管理" },
          { key: "orders", label: "订单管理" },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key as TabKey)}
            className={`px-5 py-3 text-sm font-medium transition-all ${
              tab === t.key ? "tab-active" : "tab-inactive"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: Users */}
      {tab === "users" && (
        <div className="space-y-3">
          {/* Toolbar */}
          <div className="flex items-center gap-3 flex-wrap">
            <input
              type="text"
              className="input flex-1 min-w-[200px]"
              placeholder="搜索用户名或邮箱..."
              value={usersSearch}
              onChange={(e) => {
                setUsersSearch(e.target.value);
                setUsersPage(1);
              }}
            />
            <button onClick={() => loadUsers()} className="btn-ghost text-xs px-3 py-2">
              刷新
            </button>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              共 {usersTotal} 个用户
            </span>
          </div>

          {/* Users table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>ID</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>用户名</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>邮箱</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>角色</th>
                  <th className="text-right px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>点数</th>
                  <th className="text-right px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>免费</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>会员</th>
                  <th className="text-right px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>订单数</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>注册时间</th>
                  <th className="text-center px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {usersLoading ? (
                  <tr>
                    <td colSpan={10} className="text-center py-8 text-xs" style={{ color: "var(--text-muted)" }}>
                      加载中...
                    </td>
                  </tr>
                ) : (users || []).length === 0 ? (
                  <tr>
                    <td colSpan={10} className="text-center py-8 text-xs" style={{ color: "var(--text-muted)" }}>
                      暂无用户
                    </td>
                  </tr>
                ) : (
                  (users || []).map((u) => (
                    <Fragment key={u.id}>
                      <tr
                        onClick={() => toggleUserOrders(u.id)}
                        className="cursor-pointer transition-all hover:opacity-80"
                        style={{ borderBottom: "1px solid var(--border)" }}
                      >
                        <td className="px-3 py-3 text-xs" style={{ color: "var(--text-secondary)" }}>{u.id}</td>
                        <td className="px-3 py-3 font-medium">{u.username}</td>
                        <td className="px-3 py-3 text-xs" style={{ color: "var(--text-secondary)" }}>{u.email}</td>
                        <td className="px-3 py-3">
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            u.role === "admin"
                              ? "bg-purple-500/15 text-purple-400"
                              : "bg-blue-500/10 text-blue-400"
                          }`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-right">{u.points}</td>
                        <td className="px-3 py-3 text-right" style={{ color: "var(--accent)" }}>{u.free_points_today}</td>
                        <td className="px-3 py-3 text-xs">{u.membership_type === "none" ? "—" : u.membership_type}</td>
                        <td className="px-3 py-3 text-right">{u.order_count}</td>
                        <td className="px-3 py-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                          {u.created_at ? new Date(u.created_at).toLocaleDateString("zh-CN") : "—"}
                        </td>
                        <td className="px-3 py-3 text-center">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleEditUser(u as unknown as Record<string, unknown>); }}
                            className="btn-ghost text-xs px-2 py-1"
                          >
                            编辑
                          </button>
                        </td>
                      </tr>
                      {/* Expanded user orders */}
                      {expandedUserId === u.id && (
                        <tr style={{ borderBottom: "1px solid var(--border)" }}>
                          <td colSpan={10} className="px-6 py-3">
                            <div className="text-xs space-y-2">
                              <p className="font-medium" style={{ color: "var(--text-secondary)" }}>
                                该用户的订单 {userOrdersLoading ? "加载中..." : `(${(userOrders[u.id] || []).length} 条)`}
                              </p>
                              {userOrders[u.id] && userOrders[u.id].length > 0 && (
                                <div className="overflow-x-auto">
                                  <table className="w-full text-xs" style={{ borderCollapse: "collapse" }}>
                                    <thead>
                                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                                        <th className="text-left px-2 py-1" style={{ color: "var(--text-muted)" }}>订单号</th>
                                        <th className="text-left px-2 py-1" style={{ color: "var(--text-muted)" }}>档位</th>
                                        <th className="text-right px-2 py-1" style={{ color: "var(--text-muted)" }}>金额</th>
                                        <th className="text-right px-2 py-1" style={{ color: "var(--text-muted)" }}>点数</th>
                                        <th className="text-left px-2 py-1" style={{ color: "var(--text-muted)" }}>状态</th>
                                        <th className="text-left px-2 py-1" style={{ color: "var(--text-muted)" }}>时间</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {userOrders[u.id].map((order) => (
                                        <tr key={order.id} style={{ borderBottom: "1px solid var(--border)" }}>
                                          <td className="px-2 py-1.5 font-mono">{order.out_trade_no}</td>
                                          <td className="px-2 py-1.5">{order.tier}</td>
                                          <td className="px-2 py-1.5 text-right">¥{order.amount_yuan.toFixed(2)}</td>
                                          <td className="px-2 py-1.5 text-right">+{order.points_granted}</td>
                                          <td className="px-2 py-1.5">{statusBadge(order.status)}</td>
                                          <td className="px-2 py-1.5" style={{ color: "var(--text-muted)" }}>
                                            {order.created_at ? new Date(order.created_at).toLocaleString("zh-CN") : "—"}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <Pagination
            page={usersPage}
            totalPages={usersTotalPages}
            onPrev={() => setUsersPage((p) => Math.max(1, p - 1))}
            onNext={() => setUsersPage((p) => Math.min(usersTotalPages, p + 1))}
            onGo={(p) => setUsersPage(p)}
          />

          {/* Edit user modal */}
          {editingUser && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="rounded-xl p-6 w-full max-w-sm space-y-4" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
                <h3 className="font-semibold">编辑用户: {editingUser.username as string}</h3>

                <div>
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>点数</label>
                  <input type="number" className="input w-full" value={editForm.points as number}
                    onChange={(e) => setEditForm({ ...editForm, points: parseInt(e.target.value) || 0 })} />
                </div>
                <div>
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>会员类型</label>
                  <select className="select w-full" value={editForm.membership_type as string}
                    onChange={(e) => setEditForm({ ...editForm, membership_type: e.target.value })}>
                    {MEMBERSHIP_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={editForm.disabled as boolean}
                    onChange={(e) => setEditForm({ ...editForm, disabled: e.target.checked })} />
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>禁用此用户</label>
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={editForm.email_verified as boolean}
                    onChange={(e) => setEditForm({ ...editForm, email_verified: e.target.checked })} />
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>已验证邮箱</label>
                </div>
                <div>
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>重置密码（留空不修改）</label>
                  <input type="password" className="input w-full" placeholder="输入新密码"
                    value={editForm.new_password as string}
                    onChange={(e) => setEditForm({ ...editForm, new_password: e.target.value })} />
                </div>

                {message && (
                  <p className="text-sm" style={{ color: message.type === "ok" ? "var(--accent)" : "#ef4444" }}>
                    {message.text}
                  </p>
                )}

                <div className="flex gap-2">
                  <button onClick={handleSaveUser} className="btn-primary flex-1">保存</button>
                  <button onClick={() => setEditingUser(null)} className="btn-ghost">取消</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab: LLM 配置 */}
      {tab === "llm" && (
        <div className="space-y-4">
          <div className="flex gap-1 border-b flex-wrap" style={{ borderColor: "var(--border)" }}>
            {llmProviders.map((p) => (
              <button
                key={p.name as string}
                onClick={() => handleEditProvider(p.name as string)}
                className={`px-4 py-2 text-sm font-medium transition-all ${
                  editingProvider === p.name ? "tab-active" : "tab-inactive"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="inline-block h-2 w-2 rounded-full" style={{
                    background: p.configured ? "#22c55e" : "#ef4444",
                  }} />
                  {p.label as string}
                </span>
              </button>
            ))}
            <button onClick={loadLlmProviders} className="btn-ghost text-xs px-3 py-2 ml-auto">
              刷新
            </button>
          </div>

          {editingProvider && (() => {
            const p = llmProviders.find((x) => x.name === editingProvider);
            if (!p) return null;
            return (
              <div className="card space-y-4">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-sm font-medium">{p.label as string}</span>
                  <span className={`badge ${p.configured ? "badge-green" : "badge-red"}`}>
                    {p.configured ? "已配置" : "未配置"}
                  </span>
                  <code className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {p.masked_key as string}
                  </code>
                </div>

                <div>
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>API Key</label>
                  <input type="password" className="input w-full" placeholder="留空保持不变" value={llmApiKey}
                    onChange={(e) => setLlmApiKey(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>Model</label>
                  <div className="flex gap-2">
                    <select className="select flex-1" value={llmModel}
                      onChange={(e) => setLlmModel(e.target.value)}>
                      {(p.available_models as string[] || []).map((m: string) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    <input type="text" className="input flex-1" placeholder="或自定义" value={llmModel}
                      onChange={(e) => setLlmModel(e.target.value)} />
                  </div>
                </div>
                <div>
                  <label className="text-xs" style={{ color: "var(--text-muted)" }}>Base URL</label>
                  <input type="text" className="input w-full" value={llmBaseUrl}
                    onChange={(e) => setLlmBaseUrl(e.target.value)} />
                  <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                    默认: {p.default_base_url as string}
                  </p>
                </div>

                <div className="flex gap-3 items-center">
                  <button onClick={handleSaveProvider} disabled={llmSaving} className="btn-primary">
                    {llmSaving ? "保存中..." : "保存配置"}
                  </button>
                  <button onClick={() => handleTestProvider(editingProvider)} disabled={llmTesting === editingProvider}
                    className="btn-ghost text-xs px-4 py-2">
                    {llmTesting === editingProvider ? "测试中..." : "测试连接"}
                  </button>
                </div>
              </div>
            );
          })()}

          {llmMessage && (
            <p className="text-sm" style={{
              color: llmMessage.type === "ok" ? "var(--accent)" : "#ef4444",
            }}>{llmMessage.text}</p>
          )}
        </div>
      )}

      {/* Tab: Config */}
      {tab === "config" && (
        <div className="card space-y-4">
          <h2 className="text-lg font-semibold">系统配置</h2>
          <div className="space-y-3">
            {Object.entries(configs).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between py-2 border-b" style={{ borderColor: "var(--border)" }}>
                <code className="text-xs">{key}</code>
                <code className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  {value.length > 50 ? value.slice(0, 50) + "..." : value}
                </code>
              </div>
            ))}
          </div>
          {Object.keys(configs).length === 0 && (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>暂无配置</p>
          )}
        </div>
      )}

      {/* Tab: Announcements */}
      {tab === "announcements" && (
        <div className="space-y-4">
          <div className="card space-y-3">
            <h2 className="text-lg font-semibold">发布新公告</h2>
            <input className="input w-full" placeholder="公告标题" value={annForm.title}
              onChange={(e) => setAnnForm({ ...annForm, title: e.target.value })} />
            <textarea className="input w-full min-h-[80px]" placeholder="公告内容" value={annForm.content}
              onChange={(e) => setAnnForm({ ...annForm, content: e.target.value })} />
            <div className="flex gap-2">
              <select className="select" value={annForm.type}
                onChange={(e) => setAnnForm({ ...annForm, type: e.target.value })}>
                <option value="info">信息</option>
                <option value="warning">警告</option>
                <option value="success">成功</option>
              </select>
              <button onClick={handleCreateAnnouncement} className="btn-primary">发布</button>
            </div>
          </div>

          <div className="space-y-2">
            {(announcements || []).length === 0 ? (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>暂无公告</p>
            ) : (
              (announcements || []).map((a) => (
                <div key={a.id as number} className="card flex items-center justify-between">
                  <div className="text-sm space-y-1">
                    <p className="font-medium">{a.title as string}</p>
                    <p style={{ color: "var(--text-secondary)" }}>{a.content as string}</p>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                      类型: {a.type as string} | {a.active ? "启用" : "停用"}
                    </p>
                  </div>
                  <button onClick={() => handleDeleteAnnouncement(a.id as number)}
                    className="btn-ghost text-xs" style={{ color: "#ef4444" }}>
                    删除
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Tab: Orders */}
      {tab === "orders" && (
        <div className="space-y-3">
          {/* Toolbar */}
          <div className="flex items-center gap-3 flex-wrap">
            <input
              type="text"
              className="input flex-1 min-w-[200px]"
              placeholder="搜索订单号、用户名或邮箱..."
              value={ordersSearch}
              onChange={(e) => {
                setOrdersSearch(e.target.value);
                setOrdersPage(1);
              }}
            />
            <select
              className="select"
              value={ordersStatus}
              onChange={(e) => {
                setOrdersStatus(e.target.value);
                setOrdersPage(1);
              }}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <button onClick={() => loadOrders()} className="btn-ghost text-xs px-3 py-2">
              刷新
            </button>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              共 {ordersTotal} 条订单
            </span>
          </div>

          {/* Orders table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>ID</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>订单号</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>用户</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>档位</th>
                  <th className="text-right px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>金额</th>
                  <th className="text-right px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>点数</th>
                  <th className="text-center px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>状态</th>
                  <th className="text-left px-3 py-2 font-medium text-xs" style={{ color: "var(--text-muted)" }}>支付时间</th>
                </tr>
              </thead>
              <tbody>
                {ordersLoading ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-xs" style={{ color: "var(--text-muted)" }}>
                      加载中...
                    </td>
                  </tr>
                ) : (orders || []).length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-xs" style={{ color: "var(--text-muted)" }}>
                      暂无订单
                    </td>
                  </tr>
                ) : (
                  (orders || []).map((o) => (
                    <tr key={o.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td className="px-3 py-3 text-xs" style={{ color: "var(--text-secondary)" }}>{o.id}</td>
                      <td className="px-3 py-3 font-mono text-xs">{o.out_trade_no}</td>
                      <td className="px-3 py-3">
                        <div className="text-xs">
                          <span>{o.user.username}</span>
                          <span className="ml-1" style={{ color: "var(--text-muted)" }}>({o.user.email})</span>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-xs">{o.tier}</td>
                      <td className="px-3 py-3 text-right">¥{o.amount_yuan.toFixed(2)}</td>
                      <td className="px-3 py-3 text-right">+{o.points_granted}</td>
                      <td className="px-3 py-3 text-center">{statusBadge(o.status)}</td>
                      <td className="px-3 py-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                        {o.paid_at ? new Date(o.paid_at).toLocaleString("zh-CN") : "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <Pagination
            page={ordersPage}
            totalPages={ordersTotalPages}
            onPrev={() => setOrdersPage((p) => Math.max(1, p - 1))}
            onNext={() => setOrdersPage((p) => Math.min(ordersTotalPages, p + 1))}
            onGo={(p) => setOrdersPage(p)}
          />
        </div>
      )}
    </div>
  );
}
