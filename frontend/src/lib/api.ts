/** 统一 API fetch 封装 — 带 retry + error 包装 */

// SSR 时需要完整 URL（Node.js fetch 不支持相对路径）
// 客户端时用相对路径，走 Next.js rewrites 代理，避免 CORS
const API_BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : "";

// 预测等长时间操作直连后端，绕过 Next.js 代理超时
// 生产环境走域名，开发环境走 localhost
const BACKEND_DIRECT = typeof window === "undefined"
  ? "http://localhost:8000"
  : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
const LONG_RUNNING_PATHS = ["/api/predict/full", "/api/publish/retro", "/api/bump", "/api/benchmark/extract-transcript", "/api/persona/build"];
const LONG_RUNNING_SUFFIXES = ["/optimize"];  // 路径后缀匹配

/** 从 localStorage 获取 JWT token */
function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;  // SSR 跳过
  return localStorage.getItem("auth_token");
}

export interface ApiError {
  code: string;
  message: string;
  suggested_action: string | null;
}

export interface ApiResponse<T> {
  ok: boolean;
  data: T | null;
  error: ApiError | null;
  meta: {
    response_time_ms: number;
    schema_version: string;
  } | null;
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<ApiResponse<T>> {
  // 长时间请求直连后端，避免 Next.js rewrites 代理超时
  const isLongRunning = LONG_RUNNING_PATHS.some((p) => path.startsWith(p))
    || LONG_RUNNING_SUFFIXES.some((s) => path.endsWith(s));
  const base = (typeof window !== "undefined" && isLongRunning) ? BACKEND_DIRECT : API_BASE;
  const url = `${base}${path}`;

  // 自动注入 auth token
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

    const data: ApiResponse<T> = await res.json();

    if (!data.ok) {
      console.error(`API Error [${data.error?.code}]: ${data.error?.message}`);
    }

    return data;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "网络请求失败";
    console.error(`API Error: ${message}`);
    return {
      ok: false,
      data: null,
      error: { code: "NETWORK_ERROR", message, suggested_action: "请检查网络连接或稍后重试" },
      meta: null,
    };
  }
}

/** SSE 流式请求 — 用于长时间操作的进度反馈 */
export async function sseFetch<T>(
  path: string,
  body: Record<string, unknown>,
  onProgress: (event: { phase: string; progress: number; current?: number; total?: number }) => void,
): Promise<T> {
  const SSE_BASE = typeof window === "undefined"
    ? "http://localhost:8000"
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
  const url = `${SSE_BASE}${path}`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`SSE request failed: ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: T | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          if (data.phase === "complete") {
            finalResult = data.result as T;
          } else if (data.phase === "error") {
            throw new Error(data.message || "操作失败");
          } else {
            onProgress(data);
          }
        } catch (e) {
          if (e instanceof Error && e.message !== "操作失败") {
            // Skip malformed JSON
          } else {
            throw e;
          }
        }
      }
    }
  }

  if (!finalResult) {
    throw new Error("SSE stream ended without result");
  }
  return finalResult;
}
