"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

interface ContentItem {
  id: string;
  title: string;
  predicted: boolean;
  published: boolean;
  has_retro: boolean;
  pred_time: string;
  virality_score: number | null;
  composite: number | null;
  rubric_version: string;
  actual_plays: number | null;
  accuracy: string;
  platform: string;
  publish_url: string;
  updated_at: string;
}

interface PredictionItem {
  prediction_id: string;
  virality_score: number;
  bucket: string;
  has_retro: boolean;
  updated_at: string;
}

function PublishPageContent() {
  const [contents, setContents] = useState<ContentItem[]>([]);
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [scriptId, setScriptId] = useState("");
  const [shootContent, setShootContent] = useState("");
  const [platform, setPlatform] = useState("douyin");
  const [publishUrl, setPublishUrl] = useState("");
  const [retroPredictionId, setRetroPredictionId] = useState("");
  const [actualPlays, setActualPlays] = useState<number>(0);
  const [actualLikes, setActualLikes] = useState<number | null>(null);
  const [actualComments, setActualComments] = useState<number | null>(null);
  const [actualShares, setActualShares] = useState<number | null>(null);
  const [daysSincePublish, setDaysSincePublish] = useState<number>(3);
  const [retroNotes, setRetroNotes] = useState("");
  const [retroResult, setRetroResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"retro" | "shoot" | "publish">("retro");

  const searchParams = useSearchParams();

  const loadContents = async () => {
    const res = await apiFetch<{ videos: ContentItem[] }>("/api/publish");
    if (res.ok && res.data) setContents(res.data.videos);
  };

  const loadPredictions = async () => {
    const res = await apiFetch<{ predictions: PredictionItem[] }>("/api/predict/list");
    if (res.ok && res.data) setPredictions(res.data.predictions);
  };

  const handleShoot = async () => {
    if (!scriptId || !shootContent) return;
    setLoading(true);
    await apiFetch("/api/publish/shoot", {
      method: "POST",
      body: JSON.stringify({ script_id: scriptId, shoot_content: shootContent }),
    });
    setScriptId("");
    setShootContent("");
    loadContents();
    setLoading(false);
  };

  const handlePublish = async () => {
    if (!scriptId) return;
    setLoading(true);
    await apiFetch("/api/publish", {
      method: "POST",
      body: JSON.stringify({ script_id: scriptId, platform, publish_url: publishUrl || undefined }),
    });
    setScriptId("");
    setPublishUrl("");
    loadContents();
    setLoading(false);
  };

  const handleRetro = async () => {
    if (!retroPredictionId || !actualPlays) return;
    setLoading(true);
    const res = await apiFetch("/api/publish/retro/" + retroPredictionId, {
      method: "POST",
      body: JSON.stringify({
        prediction_id: retroPredictionId,
        actual_plays: actualPlays,
        actual_likes: actualLikes || undefined,
        actual_comments: actualComments || undefined,
        actual_shares: actualShares || undefined,
        retro_notes: retroNotes || undefined,
        days_since_publish: daysSincePublish,
      }),
    });
    if (res.ok && res.data) setRetroResult(res.data as Record<string, unknown>);
    setLoading(false);
  };

  useEffect(() => {
    loadContents();
    loadPredictions();
    // 从 URL 参数自动填入预测 ID
    const retroId = searchParams.get("retro");
    if (retroId) {
      setRetroPredictionId(retroId);
      setActiveTab("retro");
    }
  }, [searchParams]);

  const pendingRetros = predictions.filter(p => !p.has_retro);

  return (
    <main>
      <h1 className="text-2xl font-bold text-glow">发布 & 复盘</h1>

      {/* 复盘流程说明 */}
      <div className="mt-4 rounded-xl p-5" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: "#22c55e" }}>复盘是什么？怎么操作？</h3>
        <div className="space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          <p><strong style={{ color: "var(--text-primary)" }}>复盘 = 发布后回看实际数据，对比预测是否准确</strong></p>
          <p>操作流程：</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
            <div className="rounded-lg p-3 text-center" style={{ background: "var(--bg-input)" }}>
              <div className="text-lg font-bold" style={{ color: "#22c55e" }}>1</div>
              <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>写脚本 → 预测爆款分</div>
            </div>
            <div className="rounded-lg p-3 text-center" style={{ background: "var(--bg-input)" }}>
              <div className="text-lg font-bold" style={{ color: "#22c55e" }}>2</div>
              <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>发布视频，等 3-7 天</div>
            </div>
            <div className="rounded-lg p-3 text-center" style={{ background: "var(--bg-input)" }}>
              <div className="text-lg font-bold" style={{ color: "#22c55e" }}>3</div>
              <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>回来填实际数据，提交复盘</div>
            </div>
          </div>
          <p className="mt-2">复盘后系统会：</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>对比预测分数和实际表现，告诉你预测准不准</li>
            <li>提取教训，帮你下次预测更准</li>
            <li>积累足够复盘后，自动校准评分标准（bump）</li>
          </ul>
        </div>
      </div>

      {/* Tab */}
      <div className="mt-6 flex gap-2">
        {(["retro", "shoot", "publish"] as const).map((tab) => (
          <button
            key={tab}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === tab ? "bg-green-500/20 text-green-400" : ""}`}
            style={activeTab !== tab ? { color: "var(--text-muted)" } : {}}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "retro" ? "复盘" : tab === "shoot" ? "登记拍摄" : "发布"}
            {tab === "retro" && pendingRetros.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 rounded text-xs" style={{ background: "rgba(239,68,68,0.2)", color: "#ef4444" }}>
                {pendingRetros.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 复盘 */}
      {activeTab === "retro" && (
        <div className="card mt-6">
          <h2 className="mb-4 text-lg font-semibold">提交复盘</h2>

          {/* 待复盘列表（快捷选择） */}
          {pendingRetros.length > 0 && (
            <div className="mb-4">
              <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--text-muted)" }}>待复盘的预测（点击选择）</h3>
              <div className="space-y-1">
                {pendingRetros.map((p) => (
                  <button
                    key={p.prediction_id}
                    className="w-full text-left rounded-lg px-3 py-2 text-sm transition-all"
                    style={{
                      background: retroPredictionId === p.prediction_id ? "rgba(34,197,94,0.1)" : "var(--bg-input)",
                      border: retroPredictionId === p.prediction_id ? "1px solid rgba(34,197,94,0.3)" : "1px solid transparent",
                      color: "var(--text-primary)",
                    }}
                    onClick={() => setRetroPredictionId(p.prediction_id)}
                  >
                    <span className="font-medium">{p.prediction_id.replace(/^\d{4}-\d{2}-\d{2}_/, "").replace(/_/g, " ").slice(0, 30)}</span>
                    <span className="ml-2 text-xs" style={{ color: "var(--text-muted)" }}>
                      爆款分 {p.virality_score} · {p.bucket}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 手动输入预测 ID */}
          <input
            className="input mb-3 w-full"
            placeholder="或手动输入预测 ID"
            value={retroPredictionId}
            onChange={(e) => setRetroPredictionId(e.target.value)}
          />

          {/* 实际数据 */}
          <div className="rounded-lg p-3 mb-3" style={{ background: "rgba(34,197,94,0.04)", border: "1px solid rgba(34,197,94,0.1)" }}>
            <h3 className="text-xs font-semibold mb-2" style={{ color: "#22c55e" }}>实际表现数据</h3>
            <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
              打开抖音/小红书等平台，找到你发布的视频，把实际数据填进来
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>播放量（必填）</label>
                <input
                  type="number"
                  className="input w-full"
                  placeholder="如：12500"
                  value={actualPlays || ""}
                  onChange={(e) => setActualPlays(Number(e.target.value))}
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>点赞数</label>
                <input
                  type="number"
                  className="input w-full"
                  placeholder="如：320"
                  value={actualLikes || ""}
                  onChange={(e) => setActualLikes(Number(e.target.value) || null)}
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>评论数</label>
                <input
                  type="number"
                  className="input w-full"
                  placeholder="如：45"
                  value={actualComments || ""}
                  onChange={(e) => setActualComments(Number(e.target.value) || null)}
                />
              </div>
              <div>
                <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>分享数</label>
                <input
                  type="number"
                  className="input w-full"
                  placeholder="如：18"
                  value={actualShares || ""}
                  onChange={(e) => setActualShares(Number(e.target.value) || null)}
                />
              </div>
            </div>
          </div>

          {/* 发布后天数 */}
          <div className="mb-3">
            <label className="text-xs mb-1 block" style={{ color: "var(--text-muted)" }}>发布后第几天</label>
            <select className="select w-full" value={daysSincePublish} onChange={(e) => setDaysSincePublish(Number(e.target.value))}>
              <option value={1}>T+1（第1天）</option>
              <option value={3}>T+3（第3天，推荐）</option>
              <option value={5}>T+5（第5天）</option>
              <option value={7}>T+7（第7天）</option>
              <option value={14}>T+14（第14天）</option>
              <option value={30}>T+30（第30天）</option>
            </select>
          </div>

          {/* 复盘备注 */}
          <textarea
            className="input mb-3 w-full"
            rows={3}
            placeholder="复盘备注（可选）：比如发布时有没有投流、有没有被限流、封面标题改了什么等"
            value={retroNotes}
            onChange={(e) => setRetroNotes(e.target.value)}
          />

          <button
            className="btn-primary w-full"
            onClick={handleRetro}
            disabled={loading || !retroPredictionId || !actualPlays}
          >
            {loading ? "分析中..." : "提交复盘"}
          </button>

          {/* 复盘结果 */}
          {retroResult && (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg p-4" style={{ background: "rgba(34,197,94,0.06)", borderLeft: "3px solid #22c55e" }}>
                <h3 className="text-sm font-semibold mb-2" style={{ color: "#22c55e" }}>复盘结果</h3>
                {(retroResult as Record<string, unknown>).deviation_analysis != null && (
                  <div className="space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                    {(() => {
                      const da = (retroResult as Record<string, unknown>).deviation_analysis as Record<string, unknown>;
                      const accuracyMap: Record<string, { label: string; color: string }> = {
                        overestimated: { label: "预测偏高", color: "#eab308" },
                        accurate: { label: "预测准确", color: "#22c55e" },
                        underestimated: { label: "预测偏低", color: "#3b82f6" },
                      };
                      const acc = accuracyMap[String(da.prediction_accuracy)] || { label: String(da.prediction_accuracy), color: "var(--text-muted)" };
                      return (
                        <>
                          <div className="flex items-center gap-2">
                            <span className="text-xs" style={{ color: "var(--text-muted)" }}>预测准确性：</span>
                            <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: `${acc.color}20`, color: acc.color }}>
                              {acc.label}
                            </span>
                          </div>
                          {da.key_deviation && <p>主要偏差：{String(da.key_deviation)}</p>}
                          {Array.isArray(da.lessons) && da.lessons.length > 0 && (
                            <div>
                              <span className="text-xs font-semibold" style={{ color: "#22c55e" }}>教训：</span>
                              <ul className="list-disc pl-5 mt-1 space-y-1">
                                {da.lessons.map((l: unknown, i: number) => <li key={i}>{String(l)}</li>)}
                              </ul>
                            </div>
                          )}
                          {da.rubric_observation && <p className="text-xs" style={{ color: "var(--text-muted)" }}>评分标准观察：{String(da.rubric_observation)}</p>}
                        </>
                      );
                    })()}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 登记拍摄 */}
      {activeTab === "shoot" && (
        <div className="card mt-6">
          <h2 className="mb-4 text-lg font-semibold">登记拍摄</h2>
          <input
            className="input mb-3 w-full"
            placeholder="脚本 ID"
            value={scriptId}
            onChange={(e) => setScriptId(e.target.value)}
          />
          <textarea
            className="input mb-3 w-full"
            rows={6}
            placeholder="拍摄稿内容（与脚本对比检测 diff）"
            value={shootContent}
            onChange={(e) => setShootContent(e.target.value)}
          />
          <button
            className="btn-primary"
            onClick={handleShoot}
            disabled={loading || !scriptId || !shootContent}
          >
            {loading ? "登记中..." : "登记"}
          </button>
        </div>
      )}

      {/* 发布 */}
      {activeTab === "publish" && (
        <div className="card mt-6">
          <h2 className="mb-4 text-lg font-semibold">发布登记</h2>
          <input
            className="input mb-3 w-full"
            placeholder="脚本 ID"
            value={scriptId}
            onChange={(e) => setScriptId(e.target.value)}
          />
          <select
            className="select mb-3 w-full"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="douyin">抖音</option>
            <option value="xiaohongshu">小红书</option>
            <option value="wechat">视频号</option>
            <option value="wechat_mp">公众号</option>
          </select>
          <input
            className="input mb-3 w-full"
            placeholder="发布链接（可选）"
            value={publishUrl}
            onChange={(e) => setPublishUrl(e.target.value)}
          />
          <button
            className="btn-primary"
            onClick={handlePublish}
            disabled={loading || !scriptId}
          >
            {loading ? "登记中..." : "登记发布"}
          </button>
        </div>
      )}

      {/* 内容列表 */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold">内容列表</h2>
        {contents.length === 0 ? (
          <p style={{ color: "var(--text-muted)" }}>暂无内容 — 先去写脚本、做预测吧</p>
        ) : (
          <div className="space-y-3">
            {contents.map((item) => {
              const statusLabel = item.has_retro
                ? "已复盘"
                : item.published
                  ? "已发布"
                  : item.predicted
                    ? "已预测"
                    : "草稿";
              const statusColor = item.has_retro
                ? "#22c55e"
                : item.published
                  ? "#3b82f6"
                  : item.predicted
                    ? "#f59e0b"
                    : "var(--text-muted)";

              const accuracyMap: Record<string, { label: string; color: string }> = {
                overestimated: { label: "预测偏高", color: "#eab308" },
                accurate: { label: "预测准确", color: "#22c55e" },
                underestimated: { label: "预测偏低", color: "#3b82f6" },
              };
              const accInfo = item.accuracy ? accuracyMap[item.accuracy] : null;

              return (
                <div key={item.id} className="card">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm truncate max-w-[280px]">{item.title || item.id}</span>
                        <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: `${statusColor}20`, color: statusColor }}>
                          {statusLabel}
                        </span>
                        {item.platform && (
                          <span className="text-xs" style={{ color: "var(--text-muted)" }}>{item.platform}</span>
                        )}
                      </div>

                      <div className="mt-2 flex items-center gap-4 flex-wrap text-xs" style={{ color: "var(--text-muted)" }}>
                        {item.virality_score != null && (
                          <span>爆款分 <strong style={{ color: item.virality_score >= 60 ? "#22c55e" : item.virality_score >= 40 ? "#f59e0b" : "#ef4444" }}>{item.virality_score}</strong>/100</span>
                        )}
                        {item.composite != null && (
                          <span>综合分 <strong style={{ color: "var(--text-primary)" }}>{item.composite}</strong>/10</span>
                        )}
                        {item.actual_plays != null && (
                          <span>实际播放 <strong style={{ color: "var(--text-primary)" }}>{item.actual_plays.toLocaleString()}</strong></span>
                        )}
                        {accInfo && (
                          <span className="px-1.5 py-0.5 rounded text-xs" style={{ background: `${accInfo.color}20`, color: accInfo.color }}>
                            {accInfo.label}
                          </span>
                        )}
                        {item.pred_time && (
                          <span>{new Date(item.pred_time).toLocaleDateString("zh-CN")}</span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {!item.has_retro && item.predicted && (
                        <button
                          className="btn-ghost text-xs px-3 py-1"
                          onClick={() => {
                            setRetroPredictionId(item.id);
                            setActiveTab("retro");
                          }}
                        >
                          复盘
                        </button>
                      )}
                      {item.publish_url && (
                        <a
                          href={item.publish_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn-ghost text-xs px-3 py-1"
                        >
                          查看
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}

export default function PublishPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center" style={{ color: "var(--text-muted)" }}>加载中...</div>}>
      <PublishPageContent />
    </Suspense>
  );
}
