"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface PersonaData {
  status: string;
  persona?: {
    name: string;
    demographics: {
      age_range: string;
      occupation: string;
      region: string;
    };
    interests: string[];
    engagement_patterns: {
      why_like: string;
      why_share: string;
      why_comment: string;
    };
    content_preferences: string[];
  };
  raw?: string;
}

export default function PersonaPage() {
  const [loading, setLoading] = useState(false);
  const [persona, setPersona] = useState<PersonaData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const buildPersona = async () => {
    setLoading(true);
    setError(null);
    const res = await apiFetch<PersonaData>("/api/persona/build", { method: "POST" });
    if (res.ok && res.data) {
      setPersona(res.data);
    } else {
      setError(res.error?.message || "构建画像失败");
    }
    setLoading(false);
  };

  const loadPersona = async () => {
    setLoading(true);
    setError(null);
    const res = await apiFetch<PersonaData>("/api/persona");
    if (res.ok && res.data) {
      setPersona(res.data);
    } else {
      setError(res.error?.message || "画像不存在");
    }
    setLoading(false);
  };

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-3xl font-bold text-glow">受众画像</h1>
      <p className="mt-2" style={{ color: "var(--text-secondary)" }}>
        从评论数据中分析受众特征 — blind scorer 硬禁读此数据
      </p>

      <div className="mt-6 flex gap-4">
        <button
          onClick={buildPersona}
          disabled={loading}
          className="btn-primary"
        >
          {loading ? "构建中..." : "构建画像"}
        </button>
        <button
          onClick={loadPersona}
          disabled={loading}
          className="btn-ghost"
        >
          查看画像
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-lg p-4" style={{ border: "1px solid rgba(239, 68, 68, 0.3)", background: "rgba(239, 68, 68, 0.1)", color: "#ef4444" }}>
          {error}
        </div>
      )}

      {persona?.persona && (
        <div className="mt-6 space-y-6">
          <div className="card">
            <h2 className="text-xl font-bold">{persona.persona.name}</h2>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>年龄段</div>
                <div className="font-medium">{persona.persona.demographics.age_range}</div>
              </div>
              <div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>职业</div>
                <div className="font-medium">{persona.persona.demographics.occupation}</div>
              </div>
              <div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>地域</div>
                <div className="font-medium">{persona.persona.demographics.region}</div>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold">兴趣标签</h3>
            <div className="mt-2 flex flex-wrap gap-2">
              {persona.persona.interests.map((i, idx) => (
                <span key={idx} className="badge-blue badge">
                  {i}
                </span>
              ))}
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold">互动模式</h3>
            <div className="mt-2 space-y-2 text-sm">
              <div><span className="font-medium" style={{ color: "#ef4444" }}>点赞:</span> {persona.persona.engagement_patterns.why_like}</div>
              <div><span className="font-medium" style={{ color: "#22c55e" }}>转发:</span> {persona.persona.engagement_patterns.why_share}</div>
              <div><span className="font-medium" style={{ color: "#3b82f6" }}>评论:</span> {persona.persona.engagement_patterns.why_comment}</div>
            </div>
          </div>

          <div className="card">
            <h3 className="font-semibold">内容偏好</h3>
            <ul className="mt-2 list-inside list-disc text-sm">
              {persona.persona.content_preferences.map((p, idx) => (
                <li key={idx}>{p}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </main>
  );
}
