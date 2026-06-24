"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

interface StyleRef {
  id: string;
  account: string;
  updated_at: string;
}

interface TranscriptResult {
  video_url: string;
  platform: string;
  transcript: string;
  metadata: { title?: string; duration?: number; uploader?: string };
  method: string;
  error?: string;
  suggestion?: string;
}

interface StyleExtractionResult {
  label: string;
  platform: string;
  video_url: string;
  fingerprint: {
    fingerprint_text: string;
    traits: Record<string, string>;
    patterns: string[];
  };
  transcript_length: number;
}

interface MimicResult {
  style_label: string;
  title: string;
  script: string;
  title_suggestion: string;
  style_notes: string;
  confidence: number;
}

interface BenchmarkDetail {
  id: string;
  account: string;
  platform: string;
  imported_at: string;
  fingerprint_text: string;
  traits: Record<string, string>;
  patterns: string[];
  samples: string[];
}

const PLATFORM_OPTIONS = [
  { value: "douyin", label: "抖音" },
  { value: "bilibili", label: "B站" },
  { value: "xiaohongshu", label: "小红书" },
  { value: "wechat", label: "视频号" },
];

const TRAIT_LABELS: Record<string, string> = {
  tone: "语气特征",
  opening_style: "开头方式",
  transition_style: "转折方式",
  ending_style: "结尾方式",
  rhythm: "节奏特征",
  vocabulary_level: "用词水平",
  humor_type: "幽默类型",
};

export default function BenchmarkPage() {
  // Step 1: 提取文案
  const [videoUrl, setVideoUrl] = useState("");
  const [platform, setPlatform] = useState("douyin");
  const [transcriptResult, setTranscriptResult] = useState<TranscriptResult | null>(null);
  const [manualTranscript, setManualTranscript] = useState("");
  const [extractingTranscript, setExtractingTranscript] = useState(false);

  // Step 2: 分析风格
  const [styleLabel, setStyleLabel] = useState("");
  const [styleResult, setStyleResult] = useState<StyleExtractionResult | null>(null);
  const [extractingStyle, setExtractingStyle] = useState(false);

  // Step 3: 模仿生成
  const [mimicTitle, setMimicTitle] = useState("");
  const [mimicBrief, setMimicBrief] = useState("");
  const [mimicResult, setMimicResult] = useState<MimicResult | null>(null);
  const [mimicking, setMimicking] = useState(false);
  const [savingScript, setSavingScript] = useState(false);

  // 已保存的风格参考列表
  const [styleRefs, setStyleRefs] = useState<StyleRef[]>([]);
  const [selectedStyle, setSelectedStyle] = useState("");

  // 详情弹窗
  const [detailData, setDetailData] = useState<BenchmarkDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 消息
  const [message, setMessage] = useState<{ type: "ok" | "error" | "warn"; text: string } | null>(null);

  // 当前步骤 (1, 2, 3)
  const [currentStep, setCurrentStep] = useState(1);

  const loadStyleRefs = async () => {
    const res = await apiFetch<{ benchmarks: StyleRef[] }>("/api/benchmark");
    if (res.ok && res.data) setStyleRefs(res.data.benchmarks);
  };

  useEffect(() => { loadStyleRefs(); }, []);

  // Step 1: 提取文案
  const handleExtractTranscript = async () => {
    if (!videoUrl) return;
    setExtractingTranscript(true);
    setTranscriptResult(null);
    setMessage(null);

    const res = await apiFetch<TranscriptResult>("/api/benchmark/extract-transcript", {
      method: "POST",
      body: JSON.stringify({ video_url: videoUrl, platform }),
    });

    if (res.ok && res.data) {
      setTranscriptResult(res.data);
      if (res.data.transcript) {
        setManualTranscript(res.data.transcript);
        setCurrentStep(2);
      } else if (res.data.error) {
        setMessage({ type: "warn", text: res.data.error + (res.data.suggestion ? " " + res.data.suggestion : "") });
      }
    } else {
      setMessage({ type: "error", text: res.error?.message || "提取失败" });
    }
    setExtractingTranscript(false);
  };

  // Step 2: 分析风格
  const handleExtractStyle = async () => {
    const transcript = manualTranscript.trim();
    if (!transcript) return;
    setExtractingStyle(true);
    setStyleResult(null);
    setMessage(null);

    const res = await apiFetch<StyleExtractionResult>("/api/benchmark/extract-style", {
      method: "POST",
      body: JSON.stringify({
        video_url: videoUrl,
        transcript,
        platform,
        label: styleLabel || undefined,
      }),
    });

    if (res.ok && res.data) {
      setStyleResult(res.data);
      setSelectedStyle(res.data.label);
      setCurrentStep(3);
      loadStyleRefs();
      setMessage({ type: "ok", text: `风格「${res.data.label}」提取成功` });
    } else {
      setMessage({ type: "error", text: res.error?.message || "风格提取失败" });
    }
    setExtractingStyle(false);
  };

  // Step 3: 模仿生成
  const handleMimic = async () => {
    const label = selectedStyle;
    if (!label || !mimicTitle) return;
    setMimicking(true);
    setMimicResult(null);

    const res = await apiFetch<MimicResult>("/api/benchmark/mimic", {
      method: "POST",
      body: JSON.stringify({
        style_label: label,
        title: mimicTitle,
        brief: mimicBrief,
      }),
    });

    if (res.ok && res.data) {
      setMimicResult(res.data);
    } else {
      setMessage({ type: "error", text: res.error?.message || "生成失败" });
    }
    setMimicking(false);
  };

  const handleViewDetail = async (benchId: string) => {
    setDetailLoading(true);
    setDetailData(null);
    const res = await apiFetch<BenchmarkDetail>(`/api/benchmark/${benchId}`);
    if (res.ok && res.data) {
      setDetailData(res.data);
    }
    setDetailLoading(false);
  };

  const handleDelete = async (benchId: string) => {
    const res = await apiFetch(`/api/benchmark/${benchId}`, { method: "DELETE" });
    if (res.ok) {
      setMessage({ type: "ok", text: "已删除" });
      loadStyleRefs();
    }
  };

  return (
    <main>
      <h1 className="text-2xl font-bold text-glow">对标风格</h1>
      <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
        从视频提取口播文案 → 分析风格 → 模仿生成新文案
      </p>

      {message && (
        <div className="mt-4 rounded-lg p-3 text-sm" style={{
          border: `1px solid ${message.type === "ok" ? "rgba(34,197,94,0.3)" : message.type === "warn" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.3)"}`,
          background: message.type === "ok" ? "rgba(34,197,94,0.1)" : message.type === "warn" ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)",
          color: message.type === "ok" ? "#22c55e" : message.type === "warn" ? "#f59e0b" : "#ef4444",
        }}>
          {message.text}
        </div>
      )}

      {/* 流程步骤指示器 */}
      <div className="mt-6 flex items-center gap-2">
        {[1, 2, 3].map((step) => (
          <button
            key={step}
            className="flex items-center gap-2"
            onClick={() => setCurrentStep(step)}
          >
            <div
              className={`h-8 w-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${
                currentStep === step ? "text-black" : currentStep > step ? "text-black" : ""
              }`}
              style={{
                background: currentStep > step ? "#22c55e" : currentStep === step ? "#22c55e" : "var(--bg-input)",
                color: currentStep >= step ? "black" : "var(--text-muted)",
              }}
            >
              {currentStep > step ? "✓" : step}
            </div>
            <span className="text-sm hidden sm:inline" style={{ color: currentStep >= step ? "var(--text-primary)" : "var(--text-muted)" }}>
              {step === 1 ? "提取文案" : step === 2 ? "分析风格" : "模仿生成"}
            </span>
            {step < 3 && <div className="w-8 h-px" style={{ background: currentStep > step ? "#22c55e" : "var(--border)" }} />}
          </button>
        ))}
      </div>

      {/* Step 1: 提取文案 */}
      {currentStep === 1 && (
        <div className="card mt-6">
          <h2 className="mb-4 text-lg font-semibold">Step 1: 提取视频口播文案</h2>
          <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
            粘贴一个视频链接，系统自动提取音频并转录为口播文案。如果自动提取失败，可以手动粘贴文案。
          </p>

          <div className="grid gap-3 sm:grid-cols-4 mb-3">
            <select className="select" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              {PLATFORM_OPTIONS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <input
              className="input sm:col-span-3"
              placeholder="粘贴视频链接，如：https://www.douyin.com/video/..."
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
            />
          </div>

          <button className="btn-primary w-full" onClick={handleExtractTranscript} disabled={extractingTranscript || !videoUrl}>
            {extractingTranscript ? "提取中（下载音频 → 语音转录）..." : "提取文案"}
          </button>

          {transcriptResult?.error && (
            <div className="mt-3 rounded-lg p-3 text-sm" style={{ background: "rgba(245,158,11,0.1)", borderLeft: "3px solid #f59e0b" }}>
              <p style={{ color: "#f59e0b" }}>{transcriptResult.error}</p>
              {transcriptResult.suggestion && <p className="mt-1" style={{ color: "var(--text-secondary)" }}>{transcriptResult.suggestion}</p>}
            </div>
          )}

          <div className="mt-4">
            <label className="text-sm font-medium mb-2 block" style={{ color: "var(--text-secondary)" }}>
              口播文案（可手动编辑或直接粘贴）
            </label>
            <textarea
              className="input w-full"
              rows={8}
              placeholder={"自动提取的文案会出现在这里。如果自动提取失败，请手动粘贴视频的口播文案内容。\n\n提示：你可以边看视频边打字，或者用手机语音转文字功能记录口播内容。"}
              value={manualTranscript}
              onChange={(e) => setManualTranscript(e.target.value)}
            />
            {manualTranscript && (
              <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                {manualTranscript.length} 字
              </p>
            )}
          </div>

          {manualTranscript && (
            <button className="btn-primary w-full mt-3" onClick={() => setCurrentStep(2)}>
              下一步：分析风格 →
            </button>
          )}
        </div>
      )}

      {/* Step 2: 分析风格 */}
      {currentStep === 2 && (
        <div className="card mt-6">
          <h2 className="mb-4 text-lg font-semibold">Step 2: 分析文案风格</h2>
          <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
            给这个风格起个名字，系统会分析口播文案的语气、句式、节奏等特征。
          </p>

          <input
            className="input mb-3 w-full"
            placeholder="给风格起个名字（如：老罗式、半佛式、老师好我叫何同学式）"
            value={styleLabel}
            onChange={(e) => setStyleLabel(e.target.value)}
          />

          <div className="rounded-lg p-3 mb-3" style={{ background: "var(--bg-input)" }}>
            <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>待分析的文案预览</div>
            <p className="text-sm line-clamp-4" style={{ color: "var(--text-secondary)" }}>
              {manualTranscript.slice(0, 200)}...
            </p>
          </div>

          <div className="flex gap-3">
            <button className="btn-ghost flex-1" onClick={() => setCurrentStep(1)}>
              ← 上一步
            </button>
            <button className="btn-primary flex-1" onClick={handleExtractStyle} disabled={extractingStyle || !manualTranscript}>
              {extractingStyle ? "分析风格中..." : "分析风格"}
            </button>
          </div>

          {styleResult && (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg p-4" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
                <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>风格指纹</h3>
                <p className="text-sm" style={{ color: "var(--text-primary)" }}>{styleResult.fingerprint.fingerprint_text}</p>
              </div>

              {Object.keys(styleResult.fingerprint.traits).length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>关键特征</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(styleResult.fingerprint.traits).map(([key, value]) => (
                      <div key={key} className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                        <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>{TRAIT_LABELS[key] || key}</div>
                        <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {styleResult.fingerprint.patterns.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>常用句式</h3>
                  <div className="space-y-1">
                    {styleResult.fingerprint.patterns.map((p, i) => (
                      <div key={i} className="rounded-lg px-3 py-2 text-sm" style={{ background: "var(--bg-input)", color: "var(--text-primary)" }}>
                        {p}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <button className="btn-primary w-full" onClick={() => setCurrentStep(3)}>
                下一步：模仿生成 →
              </button>
            </div>
          )}
        </div>
      )}

      {/* Step 3: 模仿生成 */}
      {currentStep === 3 && (
        <div className="card mt-6">
          <h2 className="mb-4 text-lg font-semibold">Step 3: 模仿风格生成文案</h2>
          <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
            给一个标题和大意，系统按照提取的风格生成口播文案。
          </p>

          <div className="mb-3">
            <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>选择风格参考</label>
            <select className="select w-full" value={selectedStyle} onChange={(e) => setSelectedStyle(e.target.value)}>
              <option value="">选择风格...</option>
              {styleRefs.map((ref) => (
                <option key={ref.id} value={ref.account}>{ref.account}</option>
              ))}
            </select>
          </div>

          <input
            className="input mb-3 w-full"
            placeholder="视频标题（如：为什么打工人越来越焦虑）"
            value={mimicTitle}
            onChange={(e) => setMimicTitle(e.target.value)}
          />

          <textarea
            className="input mb-3 w-full"
            rows={3}
            placeholder="大概意思/方向（可选）：比如想聊职场内卷但给出解法，或者想吐槽996但带点幽默"
            value={mimicBrief}
            onChange={(e) => setMimicBrief(e.target.value)}
          />

          <div className="flex gap-3">
            <button className="btn-ghost flex-1" onClick={() => setCurrentStep(2)}>
              ← 上一步
            </button>
            <button className="btn-primary flex-1" onClick={handleMimic} disabled={mimicking || !selectedStyle || !mimicTitle}>
              {mimicking ? "生成中..." : "模仿生成"}
            </button>
          </div>

          {mimicResult && (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg p-4" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold" style={{ color: "#22c55e" }}>生成的口播文案</span>
                  <button
                    className="text-xs px-2 py-1 rounded"
                    style={{ background: "var(--bg-input)", color: "var(--text-muted)" }}
                    onClick={() => navigator.clipboard.writeText(mimicResult.script)}
                  >
                    复制
                  </button>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                  {mimicResult.script}
                </p>
              </div>

              {mimicResult.title_suggestion && (
                <div className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                  <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>建议标题</div>
                  <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{mimicResult.title_suggestion}</p>
                </div>
              )}

              {mimicResult.style_notes && (
                <div className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                  <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>模仿了哪些风格特征</div>
                  <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{mimicResult.style_notes}</p>
                </div>
              )}

              <button
                className="btn-ghost w-full"
                disabled={savingScript}
                onClick={async () => {
                  setSavingScript(true);
                  try {
                    const res = await apiFetch("/api/scripts", {
                      method: "POST",
                      body: JSON.stringify({
                        title: mimicResult.title_suggestion || mimicTitle,
                        content: mimicResult.script,
                      }),
                    });
                    if (res.ok) {
                      setMessage({ type: "ok", text: "已保存为脚本" });
                    } else {
                      setMessage({ type: "error", text: res.error?.message || "保存失败" });
                    }
                  } catch (e) {
                    setMessage({ type: "error", text: "保存失败: " + String(e) });
                  }
                  setSavingScript(false);
                }}
              >
                {savingScript ? "保存中..." : "保存为脚本"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* 已保存的风格参考列表 */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold">已保存的风格参考</h2>
        {styleRefs.length === 0 ? (
          <div className="card text-center py-8">
            <p style={{ color: "var(--text-muted)" }}>暂无风格参考，请在上方从视频提取</p>
          </div>
        ) : (
          <div className="space-y-2">
            {styleRefs.map((ref) => (
              <div key={ref.id} className="card flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full flex items-center justify-center text-sm font-bold" style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e" }}>
                    {ref.account.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <span className="font-medium">{ref.account}</span>
                    <span className="ml-2 text-xs" style={{ color: "var(--text-muted)" }}>
                      {new Date(ref.updated_at).toLocaleDateString("zh-CN")}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button className="btn-ghost text-xs px-3 py-1" onClick={() => handleViewDetail(ref.id)}>
                    查看
                  </button>
                  <button
                    className="px-3 py-1 rounded text-xs font-medium"
                    style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e" }}
                    onClick={() => { setSelectedStyle(ref.account); setMimicTitle(""); setMimicBrief(""); setMimicResult(null); setCurrentStep(3); }}
                  >
                    模仿
                  </button>
                  <button className="btn-ghost text-xs px-2 py-1" style={{ color: "#ef4444" }} onClick={() => handleDelete(ref.id)}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 风格详情弹窗 */}
      {detailData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }}>
          <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl p-6" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-glow">{detailData.account}</h2>
              <button onClick={() => setDetailData(null)} className="btn-ghost text-sm px-3 py-1">关闭</button>
            </div>
            {detailLoading ? (
              <p style={{ color: "var(--text-muted)" }}>加载中...</p>
            ) : (
              <div className="space-y-6">
                {detailData.fingerprint_text && (
                  <div>
                    <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>风格指纹</h3>
                    <div className="rounded-lg p-4" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
                      <p className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>{detailData.fingerprint_text}</p>
                    </div>
                  </div>
                )}
                {Object.keys(detailData.traits).length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>关键特征</h3>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(detailData.traits).map(([key, value]) => (
                        <div key={key} className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                          <div className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>{TRAIT_LABELS[key] || key}</div>
                          <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {detailData.patterns.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>常用句式</h3>
                    <div className="space-y-1">
                      {detailData.patterns.map((p, i) => (
                        <div key={i} className="rounded-lg px-3 py-2 text-sm" style={{ background: "var(--bg-input)", color: "var(--text-primary)" }}>{p}</div>
                      ))}
                    </div>
                  </div>
                )}
                {detailData.samples.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>原始文案 ({detailData.samples.length} 条)</h3>
                    <div className="space-y-2">
                      {detailData.samples.map((s, i) => (
                        <div key={i} className="rounded-lg p-3" style={{ background: "var(--bg-input)" }}>
                          <p className="text-sm whitespace-pre-wrap" style={{ color: "var(--text-secondary)" }}>{s}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
