"""多平台热点抓取服务 — 真实 API + LLM 兜底

支持平台：微博热搜 / 抖音热榜 / 小红书探索 / 百度热搜 / 知乎热榜
优先使用真实 API，失败时回退到 LLM 模拟。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from backend.app.config import TREND_API_TIMEOUT, TREND_USE_REAL_API
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()

# 支持的热点源
SUPPORTED_SOURCES = [
    "weibo-hot",
    "douyin-hot",
    "xhs-explore",
    "baidu-hot",
    "zhihu-hot",
    "wechat-trending",
]

# 源 → 平台显示名映射
_SOURCE_PLATFORM_MAP: dict[str, str] = {
    "weibo-hot": "weibo",
    "douyin-hot": "douyin",
    "xhs-explore": "xiaohongshu",
    "baidu-hot": "baidu",
    "zhihu-hot": "zhihu",
    "wechat-trending": "wechat",
}


# ---------------------------------------------------------------------------
# Real API fetchers — each returns list[dict] or empty list on failure
# ---------------------------------------------------------------------------


async def _fetch_weibo_hot() -> list[dict[str, Any]]:
    """抓取微博热搜

    Pre-conditions:
      - 网络可达 weibo.com
    Post-conditions:
      - 返回微博热搜列表（最多 10 条）
    Side effects:
      - HTTP 请求
    """
    try:
        async with httpx.AsyncClient(timeout=TREND_API_TIMEOUT) as client:
            resp = await client.get(
                "https://weibo.com/ajax/side/hotSearch",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        items = data.get("data", {}).get("realword", [])
        trends = []
        for item in items[:10]:
            trends.append({
                "platform": "weibo",
                "topic": item.get("note", ""),
                "heat_level": _heat_to_level(item.get("raw_hot", 0)),
                "description": item.get("note", ""),
                "related_keywords": [],
                "content_angle": "",
                "competition_level": "high" if item.get("raw_hot", 0) > 1000000 else "medium",
            })
        logger.info("trends_weibo_ok", count=len(trends))
        return trends
    except Exception as e:
        logger.warning("trends_weibo_fail", error=str(e))
        return []


async def _fetch_douyin_hot() -> list[dict[str, Any]]:
    """抓取抖音热榜

    Pre-conditions:
      - 网络可达第三方 API
    Post-conditions:
      - 返回抖音热榜列表（最多 10 条）
    Side effects:
      - HTTP 请求
    """
    try:
        async with httpx.AsyncClient(timeout=TREND_API_TIMEOUT) as client:
            resp = await client.get(
                "https://api.vvhan.com/api/hotlist/douyinHot",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            body = resp.json()

        items = body.get("data", [])
        trends = []
        for item in items[:10]:
            trends.append({
                "platform": "douyin",
                "topic": item.get("title", ""),
                "heat_level": _heat_to_level(item.get("hot", 0)),
                "description": item.get("title", ""),
                "related_keywords": [],
                "content_angle": "",
                "competition_level": "high" if item.get("hot", 0) > 500000 else "medium",
            })
        logger.info("trends_douyin_ok", count=len(trends))
        return trends
    except Exception as e:
        logger.warning("trends_douyin_fail", error=str(e))
        return []


async def _fetch_xhs_hot() -> list[dict[str, Any]]:
    """抓取小红书探索

    Pre-conditions:
      - 网络可达第三方 API
    Post-conditions:
      - 返回小红书热搜列表（最多 10 条）
    Side effects:
      - HTTP 请求
    """
    try:
        async with httpx.AsyncClient(timeout=TREND_API_TIMEOUT) as client:
            resp = await client.get(
                "https://api.vvhan.com/api/hotlist/xiaohongshu",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            body = resp.json()

        items = body.get("data", [])
        trends = []
        for item in items[:10]:
            trends.append({
                "platform": "xiaohongshu",
                "topic": item.get("title", ""),
                "heat_level": _heat_to_level(item.get("hot", 0)),
                "description": item.get("title", ""),
                "related_keywords": [],
                "content_angle": "",
                "competition_level": "medium",
            })
        logger.info("trends_xhs_ok", count=len(trends))
        return trends
    except Exception as e:
        logger.warning("trends_xhs_fail", error=str(e))
        return []


async def _fetch_baidu_hot() -> list[dict[str, Any]]:
    """抓取百度热搜

    Pre-conditions:
      - 网络可达 top.baidu.com
    Post-conditions:
      - 返回百度热搜列表（最多 10 条）
    Side effects:
      - HTTP 请求
    """
    try:
        async with httpx.AsyncClient(timeout=TREND_API_TIMEOUT) as client:
            resp = await client.get(
                "https://top.baidu.com/api/board?platform=wise&tab=realtime",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            body = resp.json()

        cards = body.get("data", {}).get("cards", [])
        trends = []
        for card in cards:
            for item in card.get("content", [])[:5]:
                trends.append({
                    "platform": "baidu",
                    "topic": item.get("word", ""),
                    "heat_level": _heat_to_level(item.get("hotScore", 0)),
                    "description": item.get("desc", item.get("word", "")),
                    "related_keywords": [],
                    "content_angle": "",
                    "competition_level": "high" if item.get("hotScore", 0) > 1000000 else "medium",
                })
            if len(trends) >= 10:
                break
        logger.info("trends_baidu_ok", count=len(trends))
        return trends
    except Exception as e:
        logger.warning("trends_baidu_fail", error=str(e))
        return []


async def _fetch_zhihu_hot() -> list[dict[str, Any]]:
    """抓取知乎热榜

    Pre-conditions:
      - 网络可达第三方 API
    Post-conditions:
      - 返回知乎热榜列表（最多 10 条）
    Side effects:
      - HTTP 请求
    """
    try:
        async with httpx.AsyncClient(timeout=TREND_API_TIMEOUT) as client:
            resp = await client.get(
                "https://api.vvhan.com/api/hotlist/zhihuHot",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            body = resp.json()

        items = body.get("data", [])
        trends = []
        for item in items[:10]:
            trends.append({
                "platform": "zhihu",
                "topic": item.get("title", ""),
                "heat_level": _heat_to_level(item.get("hot", 0)),
                "description": item.get("title", ""),
                "related_keywords": [],
                "content_angle": "",
                "competition_level": "medium",
            })
        logger.info("trends_zhihu_ok", count=len(trends))
        return trends
    except Exception as e:
        logger.warning("trends_zhihu_fail", error=str(e))
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FETCH_MAP: dict[str, Any] = {
    "weibo-hot": _fetch_weibo_hot,
    "douyin-hot": _fetch_douyin_hot,
    "xhs-explore": _fetch_xhs_hot,
    "baidu-hot": _fetch_baidu_hot,
    "zhihu-hot": _fetch_zhihu_hot,
}


def _heat_to_level(heat: int | float) -> str:
    """将热度数值转换为 heat_level 字符串"""
    if heat >= 1000000:
        return "super_hot"
    if heat >= 100000:
        return "hot"
    return "warm"


async def _fetch_with_fallback(source: str, niche: str) -> list[dict[str, Any]]:
    """尝试真实 API，失败则回退到 LLM 模拟

    Pre-conditions:
      - source 在 SUPPORTED_SOURCES 中
    Post-conditions:
      - 返回该平台的热点列表（非空）
    Side effects:
      - HTTP 请求（真实 API）
      - LLM 调用（兜底时, tag="trends_fetch_fallback"）
    """
    fetcher = _FETCH_MAP.get(source)
    if fetcher:
        try:
            trends = await fetcher()
            if trends:
                return trends
        except Exception as e:
            logger.warning("trends_real_api_error", source=source, error=str(e))

    # Fallback: LLM 模拟
    logger.info("trends_fallback_to_llm", source=source)
    return await _llm_simulate_source(source, niche)


async def _llm_simulate_source(source: str, niche: str) -> list[dict[str, Any]]:
    """用 LLM 模拟单个平台热点

    Pre-conditions:
      - 至少一个 LLM provider 已配置
    Post-conditions:
      - 返回模拟热点列表
    Side effects:
      - LLM 调用 (tag="trends_fetch_fallback")
    """
    platform = _SOURCE_PLATFORM_MAP.get(source, source)
    prompt = f"""模拟 {platform} 平台当前的热点话题列表。基于你对该平台内容生态的了解，生成真实感强的热点。

目标领域: {niche}
平台: {platform}

返回 JSON：
```json
{{
  "trends": [
    {{
      "platform": "{platform}",
      "topic": "热点话题",
      "heat_level": "super_hot/hot/warm",
      "description": "简短描述",
      "related_keywords": ["关键词1", "关键词2"],
      "content_angle": "建议切入角度",
      "competition_level": "high/medium/low"
    }}
  ]
}}
```

生成 3-5 个热点。"""

    result = await call_llm_json(prompt, tag="trends_fetch_fallback", temperature=0.5)
    return result.get("trends", [])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_trends_real(
    sources: list[str] | None = None,
    niche: str | None = None,
) -> dict[str, Any]:
    """仅使用真实 API 抓取热点（不回退到 LLM）

    Pre-conditions:
      - sources 中的源在 SUPPORTED_SOURCES 中
    Post-conditions:
      - 返回各平台热点列表（可能部分为空）
    Side effects:
      - HTTP 请求
    """
    sources = sources or ["douyin-hot", "xhs-explore"]
    niche = niche or "泛知识/观点输出"

    logger.info("trends_fetch_real_start", sources=sources)

    all_trends: list[dict[str, Any]] = []
    failed_sources: list[str] = []

    for source in sources:
        fetcher = _FETCH_MAP.get(source)
        if fetcher:
            try:
                trends = await fetcher()
                if trends:
                    all_trends.extend(trends)
                else:
                    failed_sources.append(source)
            except Exception as e:
                logger.warning("trends_real_api_error", source=source, error=str(e))
                failed_sources.append(source)
        else:
            failed_sources.append(source)

    return {
        "trends": all_trends,
        "sources": sources,
        "niche": niche,
        "fetched_at": datetime.now().isoformat(),
        "failed_sources": failed_sources,
        "mode": "real_api",
    }


async def fetch_trends(
    data_dir: Path,
    sources: list[str] | None = None,
    niche: str | None = None,
) -> dict[str, Any]:
    """抓取多平台热点 — 优先真实 API，失败回退 LLM

    Pre-conditions:
      - sources 中的源在 SUPPORTED_SOURCES 中
    Post-conditions:
      - 返回各平台热点列表
    Side effects:
      - HTTP 请求（真实 API）
      - LLM 调用（兜底时, tag="trends_fetch" 或 "trends_fetch_fallback"）
    """
    sources = sources or ["douyin-hot", "xhs-explore"]
    niche = niche or "泛知识/观点输出"

    logger.info("trends_fetch_start", sources=sources, niche=niche, use_real_api=TREND_USE_REAL_API)

    if not TREND_USE_REAL_API:
        # 直接走 LLM 模拟
        return await _fetch_trends_llm_only(sources, niche)

    # 尝试真实 API + LLM 兜底
    all_trends: list[dict[str, Any]] = []
    fallback_sources: list[str] = []

    for source in sources:
        trends = await _fetch_with_fallback(source, niche)
        if trends:
            all_trends.extend(trends)
        else:
            fallback_sources.append(source)

    # 判断是否有任何真实 API 数据
    has_real_data = any(
        _FETCH_MAP.get(s) and len([t for t in all_trends if t.get("platform") == _SOURCE_PLATFORM_MAP.get(s)]) > 0
        for s in sources
        if s in _FETCH_MAP
    )

    note = "真实 API 数据" if has_real_data else "LLM 模拟数据（API 均不可用）"
    if fallback_sources:
        note += f" | 回退源: {', '.join(fallback_sources)}"

    logger.info("trends_fetch_complete", count=len(all_trends), note=note)
    return {
        "trends": all_trends,
        "sources": sources,
        "niche": niche,
        "fetched_at": datetime.now().isoformat(),
        "note": note,
    }


async def _fetch_trends_llm_only(
    sources: list[str],
    niche: str,
) -> dict[str, Any]:
    """纯 LLM 模拟热点（原有 Phase 1 逻辑）

    Pre-conditions:
      - 至少一个 LLM provider 已配置
    Post-conditions:
      - 返回模拟热点列表
    Side effects:
      - LLM 调用 (tag="trends_fetch")
    """
    prompt = f"""模拟以下平台当前的热点话题列表。基于你对这些平台内容生态的了解，生成真实感强的热点。

目标领域: {niche}
平台: {', '.join(sources)}

返回 JSON：
```json
{{
  "trends": [
    {{
      "platform": "douyin",
      "topic": "热点话题",
      "heat_level": "super_hot/hot/warm",
      "description": "简短描述",
      "related_keywords": ["关键词1", "关键词2"],
      "content_angle": "建议切入角度",
      "competition_level": "high/medium/low"
    }}
  ],
  "fetched_at": "{datetime.now().isoformat()}"
}}
```

每个平台生成 3-5 个热点。"""

    result = await call_llm_json(prompt, tag="trends_fetch", temperature=0.5)

    trends = result.get("trends", [])
    logger.info("trends_fetch_llm_complete", count=len(trends))
    return {
        "trends": trends,
        "sources": sources,
        "niche": niche,
        "fetched_at": datetime.now().isoformat(),
        "note": "LLM 模拟数据（TREND_USE_REAL_API=false）",
    }


async def match_trends_to_niche(
    data_dir: Path,
    trends: list[dict[str, Any]],
    niche: str,
    content_form: str = "opinion-video",
) -> list[dict[str, Any]]:
    """将热点与细分领域匹配，筛选适合的选题

    Pre-conditions:
      - trends 非空
    Post-conditions:
      - 返回匹配后的热点列表（带适配度评分）
    Side effects:
      - LLM 调用 (tag="trends_match")
    """
    if not trends:
        return []

    trends_text = "\n".join(
        f"- [{t.get('platform', '')}] {t.get('topic', '')}: {t.get('description', '')}"
        for t in trends
    )

    prompt = f"""评估以下热点与我的内容领域的匹配度。

我的领域: {niche}
内容形态: {content_form}

热点列表:
{trends_text}

返回 JSON：
```json
{{
  "matched": [
    {{
      "topic": "热点话题",
      "platform": "平台",
      "niche_fit_score": 0.8,
      "content_angle": "具体切入角度",
      "why_fit": "为什么适合我的领域",
      "risk": "潜在风险（如蹭热点翻车）"
    }}
  ]
}}
```

niche_fit_score 范围 0-1，只返回 >= 0.5 的。"""

    result = await call_llm_json(prompt, tag="trends_match", temperature=0.2)
    return result.get("matched", [])
