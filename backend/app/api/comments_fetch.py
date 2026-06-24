"""评论抓取路由"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.account_fetcher import fetch_comments

router = APIRouter()


class FetchCommentsRequest(BaseModel):
    url_or_id: str
    platform: Literal["douyin", "bilibili", "xiaohongshu"]
    count: int = Field(default=20, ge=1, le=100)


@router.post("")
async def fetch_comments_endpoint(req: FetchCommentsRequest) -> ApiResponse:
    """抓取视频/笔记评论"""
    try:
        result = await fetch_comments(req.url_or_id, req.platform, req.count)
        return ApiResponse(ok=True, data={"comments": result, "count": len(result)})
    except Exception as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="COMMENTS_FETCH_FAILED", message=str(e)))
