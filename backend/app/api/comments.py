"""评论选题路由"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse
from backend.app.services.comment_miner import analyze_comments, recommend_candidates
from backend.app.services.trends_service import fetch_trends

router = APIRouter()


class AnalyzeCommentsRequest(BaseModel):
    video_id: str
    comments: list[str] = Field(min_length=3)
    platform: str = "douyin"


class TrendsRequest(BaseModel):
    sources: list[str] | None = None
    niche: str | None = None


@router.post("/analyze")
async def analyze_comments_endpoint(req: AnalyzeCommentsRequest) -> ApiResponse:
    """分析评论 → 挖掘选题"""
    result = await analyze_comments(DATA_DIR, req.video_id, req.comments, req.platform)
    return ApiResponse(ok=True, data=result)


@router.get("/trends")
async def get_trends(sources: str | None = None, niche: str | None = None) -> ApiResponse:
    """获取多平台热点"""
    source_list = sources.split(",") if sources else None
    result = await fetch_trends(DATA_DIR, source_list, niche)
    return ApiResponse(ok=True, data=result)


@router.get("/candidates/recommend")
async def recommend_candidates_endpoint(limit: int = 5) -> ApiResponse:
    """选题推荐"""
    result = await recommend_candidates(DATA_DIR, limit)
    return ApiResponse(ok=True, data=result)
