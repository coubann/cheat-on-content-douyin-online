"""项目初始化路由"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.models.response import ApiResponse
from backend.app.services.cheat_wrapper import CheatWrapper

router = APIRouter()


class InitRequest(BaseModel):
    """初始化请求 — 对应 cheat-init 的 6 个问题"""

    content_form: str = Field(default="opinion-video", description="内容形态")
    platforms: list[str] = Field(default=["douyin"], description="目标平台")
    has_published: bool = Field(default=False, description="是否发过内容")
    data_collection_method: str = Field(default="manual", description="数据回收方式")
    topic_pool_status: str = Field(default="empty", description="选题池状态")
    install_hooks: bool = Field(default=False, description="是否安装 hook")
    benchmark_accounts: list[str] = Field(default_factory=list, description="对标账号")
    target_publish_cadence_days: int = Field(default=2, description="发布节奏（天）")
    typical_duration_seconds: int = Field(default=240, description="典型时长（秒）")


@router.post("")
async def init_project(req: InitRequest) -> ApiResponse:
    """初始化项目 — cheat-init"""
    wrapper = CheatWrapper()
    answers = req.model_dump()
    result = await wrapper.init(answers)
    return ApiResponse(ok=True, data=result)
