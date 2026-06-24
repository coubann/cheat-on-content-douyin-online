"use client";

import { useAuth } from "@/lib/auth-context";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

const MEMBERSHIP_OPTIONS = [
  { value: "none", label: "无会员" },
  { value: "basic", label: "Basic" },
  { value: "standard", label: "Standard" },
  { value: "premium", label: "Premium" },
];

export default function AdminPage() {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<"users" | "config" | "announcements" | "orders">("users");
  const [users, setUsers] = useState<Array<Record<string, unknown>>>([]);
  const [announcements, setAnnouncements] = useState<Array<Record<string, unknown>>>([]);
  const [orders, setOrders] = useState<Array<Record<string, unknown>>>([]);
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [editingUser, setEditingUser] = useState<Record<string, unknown> | null>(null);
  const [editForm, setEditForm] = useState<Record<string, unknown>>({});
  const [message, setMessage] = useState<{ type: "ok" | "error"; text: string } | null>(null);
  const [annForm, setAnnForm] = useState({ title: "", content: "", type: "info" });

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
    loadUsers();
    loadAnnouncements();
    loadOrders();
    loadConfig();
    loadLlmProviders();
  }, [token]);

  const authHeaders = () => ({ Authorization: `Bearer ${token}` });

  const loadUsers = async () => {
    const res = await apiFetch<Array<Record<string, unknown>>>("/api/admin/users", {
      headers: authHeaders(),
    });
    if (res.ok && res.data) setUsers(res.data);
  };

  const loadAnnouncements = async () => {
    const res = await apiFetch<Array<Record<string, unknown>>>("/api/admin/announcements", {
      headers: authHeaders(),
    });
    if (res.ok && res.data) setAnnouncements(res.data);
  };

  const loadOrders = async () => {
    const res = await apiFetch<Array<Record<string, unknown>>>("/api/admin/orders", {
      headers: authHeaders(),
    });
    if (res.ok && res.data) setOrders(res.data);
  };

  const loadConfig = async () => {
    const res = await apiFetch<Record<string, string>>("/api/admin/config", {
      headers: authHeaders(),
    });
    if (res.ok && res.data) setConfigs(res.data);
  };

  const handleEditUser = (u: Record<string, unknown>) => {
    setEditingUser(u);
    setEditForm({
      points: u.points as number,
      membership_type: u.membership_type as string,
      disabled: u.disabled as boolean,
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
    if (res.ok && res.data?.ok) {
      setLlmMessage({ type: "ok", text: `${name}: 连接成功 ✅` });
    } else {
      setLlmMessage({ type: "error", text: `${name}: 连接失败 ❌` });
    }
    setLlmTesting(null);
  };

  if (loading || !user) {
    return <div className="py-20 text-center" style={{ color: "var(--text-secondary)" }}>加载中...</div>;
  }

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
            onClick={() => setTab(t.key as typeof tab)}
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
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            共 {users.length} 个用户
          </p>
          {users.map((u) => (
            <div key={u.id as number} className="card flex items-center justify-between">
              <div className="text-sm space-y-1">
                <p className="font-medium">{u.username as string}</p>
                <p style={{ color: "var(--text-muted)" }}>{u.email as string}</p>
                <div className="flex gap-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                  <span>角色: {u.role as string}</span>
                  <span>点数: {u.points as number}</span>
                  <span>免费: {u.free_points_today as number}</span>
                  <span>会员: {u.membership_type as string}</span>
                  {u.disabled && <span style={{ color: "#ef4444" }}>已禁用</span>}
                </div>
              </div>
              <button onClick={() => handleEditUser(u)} className="btn-ghost text-xs px-3 py-1">
                编辑
              </button>
            </div>
          ))}

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
            {announcements.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>暂无公告</p>
            ) : (
              announcements.map((a) => (
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
        <div className="space-y-2">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            共 {orders.length} 个订单
          </p>
          {orders.length === 0 ? (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>暂无订单</p>
          ) : (
            orders.map((o) => (
              <div key={o.id as number} className="card flex items-center justify-between text-sm">
                <div className="space-y-1">
                  <p><span className="text-xs" style={{ color: "var(--text-muted)" }}>用户ID:</span> {o.user_id}</p>
                  <p><span className="text-xs" style={{ color: "var(--text-muted)" }}>档位:</span> {o.tier}</p>
                  <p><span className="text-xs" style={{ color: "var(--text-muted)" }}>点数:</span> {o.points_granted}</p>
                  <p><span className="text-xs" style={{ color: "var(--text-muted)" }}>金额:</span> ¥{(o.amount as number / 100).toFixed(2)}</p>
                </div>
                <div className="text-right space-y-1">
                  <span className="badge" style={{
                    background: o.status === "paid" ? "rgba(34,197,94,0.15)" : "rgba(245,158,11,0.15)",
                    color: o.status === "paid" ? "#22c55e" : "#f59e0b",
                  }}>
                    {o.status === "paid" ? "已支付" : "待支付"}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
