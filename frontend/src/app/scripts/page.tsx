"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

interface Script {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  size_bytes: number;
}

export default function ScriptsPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/login");
    }
  }, [user, authLoading, router]);

  const loadScripts = async () => {
    // 强制不缓存，避免新建后重新拉取列表时命中旧缓存而看不到新脚本
    const res = await apiFetch<{ scripts: Script[] }>("/api/scripts", {
      cache: "no-store",
    });
    if (res.ok && res.data) setScripts(res.data.scripts);
  };

  const handleCreate = async () => {
    if (!title || !content) return;
    setSaving(true);
    setCreateError(null);
    const res = await apiFetch<{ id: string; title: string }>("/api/scripts", {
      method: "POST",
      body: JSON.stringify({ title, content }),
    });
    if (res.ok && res.data) {
      // 将新建返回的脚本直接追加到本地 state，保证立即可见，
      // 不依赖（可能命中缓存的）重新拉取结果。
      const newScript: Script = {
        id: res.data.id,
        title: res.data.title,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        size_bytes: 0,
      };
      setScripts((prev) => [newScript, ...prev]);
      setTitle("");
      setContent("");
      setShowCreate(false);
      loadScripts();
    } else {
      // 创建失败：给出可见提示，避免静默失败（用户体感"创建了但不显示"）。
      const msg = res.error?.message || "创建失败，请重试";
      setCreateError(msg);
      window.alert(msg);
    }
    setSaving(false);
  };

  const handleEdit = async (id: string) => {
    const res = await apiFetch<{ id: string; content: string }>(`/api/scripts/${encodeURIComponent(id)}`);
    if (res.ok && res.data) {
      setEditingId(id);
      setEditContent(res.data.content);
    }
  };

  const handleSaveEdit = async () => {
    if (!editingId || !editContent) return;
    setEditLoading(true);
    const res = await apiFetch(`/api/scripts/${encodeURIComponent(editingId)}`, {
      method: "PUT",
      body: JSON.stringify({ content: editContent }),
    });
    if (res.ok) {
      setEditingId(null);
      setEditContent("");
      loadScripts();
    }
    setEditLoading(false);
  };

  const handleDelete = async (id: string) => {
    const res = await apiFetch(`/api/scripts/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    if (res.ok) {
      setDeleteConfirm(null);
      loadScripts();
    }
  };

  useEffect(() => {
    loadScripts();
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-glow">草稿管理</h1>
          <p className="mt-1" style={{ color: "var(--text-secondary)" }}>
            新建 / 编辑 / 删除草稿
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "取消" : "新建草稿"}
        </button>
      </div>

      {/* 新建表单 */}
      {showCreate && (
        <div className="card mt-6">
          <input
            className="input mb-3 w-full"
            placeholder="标题"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            className="input mb-3 w-full"
            rows={8}
            placeholder="脚本内容..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <button
            className="btn-primary"
            onClick={handleCreate}
            disabled={saving || !title || !content}
          >
            {saving ? "创建中..." : "创建"}
          </button>
          {createError && (
            <p className="text-sm mt-2" style={{ color: "#ef4444" }}>
              {createError}
            </p>
          )}
        </div>
      )}

      {/* 编辑弹窗 */}
      {editingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div className="card w-full max-w-2xl mx-4 max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">编辑草稿</h2>
              <button onClick={() => { setEditingId(null); setEditContent(""); }} className="text-sm" style={{ color: "var(--text-muted)" }}>关闭</button>
            </div>
            <textarea
              className="input w-full mb-4"
              rows={15}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
            />
            <div className="flex gap-3">
              <button className="btn-primary" onClick={handleSaveEdit} disabled={editLoading}>
                {editLoading ? "保存中..." : "保存"}
              </button>
              <button className="btn-ghost" onClick={() => { setEditingId(null); setEditContent(""); }}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认 */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div className="card w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold mb-3" style={{ color: "#ef4444" }}>确认删除</h2>
            <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
              确定要删除这个草稿吗？此操作不可撤销。
            </p>
            <div className="flex gap-3">
              <button
                className="px-4 py-2 rounded-lg text-sm font-medium"
                style={{ background: "#ef4444", color: "white" }}
                onClick={() => handleDelete(deleteConfirm)}
              >
                确认删除
              </button>
              <button className="btn-ghost" onClick={() => setDeleteConfirm(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 脚本列表 */}
      <div className="mt-6 space-y-3">
        {scripts.length === 0 ? (
          <p style={{ color: "var(--text-muted)" }}>暂无草稿，点击"新建草稿"开始</p>
        ) : (
          scripts
            .slice()
            .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
            .map((s) => (
            <div key={s.id} className="card flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{s.title || s.id}</div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                  创建于 {new Date(s.created_at).toLocaleString("zh-CN")}
                  {s.size_bytes > 0 && ` · ${s.size_bytes}B`}
                </div>
              </div>
              <div className="flex items-center gap-2 ml-4">
                <a href={`/predict?script=${s.id}`} className="badge badge-blue">预测</a>
                <button
                  onClick={() => handleEdit(s.id)}
                  className="badge badge-green cursor-pointer"
                >
                  编辑
                </button>
                <button
                  onClick={() => setDeleteConfirm(s.id)}
                  className="badge badge-red cursor-pointer"
                >
                  删除
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <button className="btn-ghost mt-4 text-sm" onClick={loadScripts}>
        刷新列表
      </button>
    </main>
  );
}
