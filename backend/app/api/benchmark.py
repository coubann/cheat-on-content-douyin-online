"""对标风格路由"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR
from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.style_mimic import (
    delete_benchmark,
    extract_style_from_transcript,
    get_benchmark_detail,
    import_benchmark,
    list_benchmarks,
    mimic_style,
)
from backend.app.services.video_transcript import extract_transcript

router = APIRouter()


class ImportBenchmarkRequest(BaseModel):
    account_name: str
    platform: str = "douyin"
    sample_contents: list[str] = Field(min_length=1)


class ExtractTranscriptRequest(BaseModel):
    video_url: str
    platform: str = "auto"


class ExtractStyleRequest(BaseModel):
    video_url: str = ""
    transcript: str
    platform: str = "douyin"
    label: str = ""


class MimicRequest(BaseModel):
    style_label: str = ""
    account_name: str = ""  # backward compat
    title: str
    brief: str = ""
    topic: str = ""  # backward compat
    content_form: str = "opinion-video"


@router.post("/import")
async def import_benchmark_endpoint(req: ImportBenchmarkRequest) -> ApiResponse:
    """导入对标账号"""
    result = await import_benchmark(DATA_DIR, req.account_name, req.platform, req.sample_contents)
    return ApiResponse(ok=True, data=result)


@router.post("/extract-transcript")
async def extract_transcript_endpoint(req: ExtractTranscriptRequest) -> ApiResponse:
    """从视频链接提取口播文案

    即使自动提取失败，也返回 ok=True，包含 error/suggestion 字段，
    让前端展示手动粘贴的 fallback UI。
    """
    result = await extract_transcript(req.video_url, req.platform)
    return ApiResponse(ok=True, data=result)


@router.post("/extract-style")
async def extract_style_endpoint(req: ExtractStyleRequest) -> ApiResponse:
    """从视频文案提取风格指纹"""
    result = await extract_style_from_transcript(
        DATA_DIR, req.video_url, req.transcript, req.platform, req.label
    )
    return ApiResponse(ok=True, data=result)


@router.get("")
async def list_benchmarks_endpoint() -> ApiResponse:
    """列出所有对标账号"""
    result = await list_benchmarks(DATA_DIR)
    return ApiResponse(ok=True, data={"benchmarks": result})


@router.get("/{bench_id}")
async def get_benchmark_detail_endpoint(bench_id: str) -> ApiResponse:
    """获取对标账号详情"""
    result = await get_benchmark_detail(DATA_DIR, bench_id)
    if not result:
        return ApiResponse(ok=False, error=ErrorDetail(code="BENCHMARK_NOT_FOUND", message="对标账号不存在"))
    return ApiResponse(ok=True, data=result)


@router.delete("/{bench_id}")
async def delete_benchmark_endpoint(bench_id: str) -> ApiResponse:
    """删除对标账号"""
    try:
        result = await delete_benchmark(DATA_DIR, bench_id)
        return ApiResponse(ok=True, data=result)
    except FileNotFoundError as e:
        return ApiResponse(ok=False, error=ErrorDetail(code="BENCHMARK_NOT_FOUND", message=str(e)))


@router.post("/mimic")
async def mimic_endpoint(req: MimicRequest) -> ApiResponse:
    """模仿对标账号风格生成脚本"""
    result = await mimic_style(
        DATA_DIR,
        style_label=req.style_label,
        account_name=req.account_name,
        title=req.title,
        brief=req.brief,
        topic=req.topic,
        content_form=req.content_form,
    )
    if "error" in result:
        return ApiResponse(
            ok=False,
            error=ErrorDetail(
                code="BENCHMARK_NOT_FOUND",
                message=result["error"],
                suggested_action=result.get("suggested_action", ""),
            ),
        )
    return ApiResponse(ok=True, data=result)
