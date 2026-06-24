"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

export default function LlmStatusDot() {
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      const res = await apiFetch<{ connected: boolean }>("/api/settings/llm-status");
      if (res.ok && res.data) {
        setConnected(res.data.connected);
      }
    })();
  }, []);

  if (connected === null) return null;

  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{
        background: connected ? "#22c55e" : "#ef4444",
        boxShadow: connected
          ? "0 0 6px rgba(34,197,94,0.5)"
          : "0 0 6px rgba(239,68,68,0.5)",
      }}
      title={connected ? "AI 已就绪" : "AI 连接异常"}
    />
  );
}
