"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

const TYPE_STYLES: Record<string, { bg: string; color: string; border: string }> = {
  info: { bg: "rgba(59,130,246,0.1)", color: "#3B82F6", border: "rgba(59,130,246,0.3)" },
  warning: { bg: "rgba(245,158,11,0.1)", color: "#F59E0B", border: "rgba(245,158,11,0.3)" },
  success: { bg: "rgba(34,197,94,0.1)", color: "#22C55E", border: "rgba(34,197,94,0.3)" },
};

interface Announcement {
  id: number;
  title: string;
  content: string;
  type: string;
}

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

export default function AnnouncementBanner() {
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    (async () => {
      const token = getAuthToken();
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await apiFetch<Announcement>("/api/announcements/active", { headers });
      if (res.ok && res.data) {
        setAnnouncement(res.data);
      }
    })();
  }, []);

  const handleDismiss = async () => {
    if (!announcement) return;
    setDismissed(true);
    // 持久化关闭记录
    const token = getAuthToken();
    if (token) {
      await apiFetch(`/api/announcements/${announcement.id}/dismiss`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  };

  if (!announcement || dismissed) return null;

  const style = TYPE_STYLES[announcement.type] || TYPE_STYLES.info;

  return (
    <div
      className="mb-4 flex items-start gap-3 rounded-lg px-4 py-3 text-sm"
      style={{ background: style.bg, border: `1px solid ${style.border}` }}
    >
      <div className="flex-1">
        <p className="font-medium" style={{ color: style.color }}>{announcement.title}</p>
        <p style={{ color: "var(--text-secondary)" }}>{announcement.content}</p>
      </div>
      <button
        onClick={handleDismiss}
        className="text-xs px-2 py-1 rounded hover:opacity-70"
        style={{ color: "var(--text-muted)", background: "rgba(0,0,0,0.2)" }}
      >
        关闭
      </button>
    </div>
  );
}
