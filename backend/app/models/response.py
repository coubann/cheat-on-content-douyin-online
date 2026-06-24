"""统一 API 响应模型"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    suggested_action: str | None = None


class ResponseMeta(BaseModel):
    response_time_ms: int
    schema_version: str = "1.4-ext"


class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: ErrorDetail | None = None
    meta: ResponseMeta | None = None
