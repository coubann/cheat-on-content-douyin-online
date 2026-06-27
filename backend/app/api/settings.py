"""Settings API 路由 — LLM Provider 配置"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.app.models.response import ApiResponse, ErrorDetail
from backend.app.services.settings_service import (
    get_provider_settings,
    save_default_provider,
    save_provider_settings,
    test_provider_connection,
)

router = APIRouter()


@router.get("/providers")
async def get_providers() -> ApiResponse:
    """获取所有 Provider 的完整配置状态"""
    result = get_provider_settings()
    return ApiResponse(ok=True, data=result)


@router.put("/providers/{provider_name}")
async def save_provider(provider_name: str, body: dict[str, Any]) -> ApiResponse:
    """保存单个 Provider 的配置（api_key / model / base_url）"""
    result = save_provider_settings(
        provider_name=provider_name,
        api_key=body.get("api_key"),
        model=body.get("model"),
        base_url=body.get("base_url"),
    )
    if result.get("status") == "error":
        return ApiResponse(ok=False, error=ErrorDetail(code="INVALID_REQUEST", message=result["message"]))
    return ApiResponse(ok=True, data=result)


@router.put("/default-provider")
async def set_default_provider(body: dict[str, Any]) -> ApiResponse:
    """设置默认 Provider"""
    provider = body.get("provider", "")
    result = save_default_provider(provider)
    if result.get("status") == "error":
        return ApiResponse(ok=False, error=ErrorDetail(code="INVALID_REQUEST", message=result["message"]))
    return ApiResponse(ok=True, data=result)


@router.post("/providers/{provider_name}/test")
async def test_connection(provider_name: str) -> ApiResponse:
    """测试 Provider 连接是否可用"""
    result = await test_provider_connection(provider_name)
    if result.get("ok"):
        return ApiResponse(ok=True, data=result)
    return ApiResponse(ok=False, error=ErrorDetail(code="LLM_CALL_FAILED", message=result.get("message", "连接失败")))


@router.get("/llm-status")
async def llm_status() -> ApiResponse:
    """获取 LLM 连接状态（绿点/红点）- 公共接口，无需登录

    绿点 = 至少有一个 Provider 配置正确且连接成功
    红点 = 所有 Provider 均未配置或连接失败
    """
    result = get_provider_settings()
    any_configured = result.get("any_configured", False)
    return ApiResponse(ok=True, data={
        "connected": any_configured,
        "status": "connected" if any_configured else "disconnected",
    })
