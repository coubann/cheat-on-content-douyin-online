"""智能选题推荐 API 路由 — cheat-seed 的 Web 接口"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse
from backend.app.services.seed_service import recommend_topics

router = APIRouter()


@router.post("/recommend")
async def recommend_topics_endpoint(
    count: int = 5,
    strategy: str = "balanced",
) -> ApiResponse:
    """智能选题推荐 — 融合多源信号

    strategy: balanced(平衡) / safe(稳妥) / experimental(实验)
    """
    result = await recommend_topics(DATA_DIR, count=count, strategy=strategy)
    return ApiResponse(ok=True, data=result)
