"""LLM 调用统一封装 — 所有 LLM 调用必须走此模块"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

import httpx
import structlog

from backend.app.config import DATA_DIR
from backend.app.errors import LLM_CALL_FAILED, LLM_JSON_PARSE_FAILED

logger = structlog.get_logger()

# 用量日志路径
USAGE_LOG = DATA_DIR / ".cheat-cache" / "usage.jsonl"

# Provider 配置 — 从环境变量读取，支持运行时更新
_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_model": "deepseek-chat",
        "default_base_url": "https://api.deepseek.com/chat/completions",
    },
    "qwen": {
        "api_key_env": "DASHSCOPE_API_KEY",
        "model_env": "DASHSCOPE_MODEL",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "default_model": "qwen-plus",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    },
    "openrouter": {
        "api_key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "base_url_env": "OPENROUTER_BASE_URL",
        "default_model": "anthropic/claude-sonnet-4",
        "default_base_url": "https://openrouter.ai/api/v1/chat/completions",
    },
}


def _get_provider_config(provider: str) -> tuple[str, str, str]:
    """获取 provider 的 api_key / model / base_url — 优先 os.environ，其次 .env 文件"""
    cfg = _PROVIDER_DEFAULTS.get(provider, {})
    api_key = _read_env(cfg.get("api_key_env", ""))
    model = _read_env(cfg.get("model_env", "")) or cfg.get("default_model", "")
    base_url = _read_env(cfg.get("base_url_env", "")) or cfg.get("default_base_url", "")
    return api_key, model, base_url


def _find_env_path() -> Path:
    """查找 .env 文件绝对路径 — 与 config.py BASE_DIR 对齐"""
    # 1. ENV_FILE 环境变量
    env_file = os.environ.get("ENV_FILE", "")
    if env_file:
        p = Path(env_file)
        if p.is_absolute() and p.exists():
            return p
    # 2. 项目根目录（与 config.py BASE_DIR 一致）
    from backend.app.config import BASE_DIR
    root_env = BASE_DIR / ".env"
    if root_env.exists():
        return root_env
    # 3. 当前工作目录
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
    # 4. 兜底
    return root_env


def _read_env(key: str, default: str = "") -> str:
    """获取环境变量 — 优先 os.environ（排除占位符），其次 .env 文件"""
    val = os.environ.get(key, "")
    # 跳过占位符值，去 .env 文件读真实值
    if val and val != "sk-placeholder":
        return val
    # 从 .env 文件读取
    env_path = _find_env_path()
    if env_path.exists():
        prefix = f"{key}="
        for line in env_path.read_text(encoding="utf-8").strip().split("\n"):
            if line.startswith(prefix):
                file_val = line[len(prefix):].strip().strip("\"'")
                if file_val and file_val != "sk-placeholder":
                    return file_val
    return default


def _get_default_provider() -> str:
    """获取默认 Provider"""
    return _read_env("DEFAULT_LLM_PROVIDER", "deepseek")


async def call_llm(
    prompt: str,
    *,
    provider: Literal["deepseek", "qwen", "openrouter", "claude", "local"] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    tag: str = "default",
    system: str | None = None,
) -> str:
    """统一 LLM 调用入口

    Pre-conditions:
      - 至少一个 LLM provider API key 已配置
    Post-conditions:
      - 返回 LLM 响应文本
      - 用量记录写入 usage.jsonl
    Side effects:
      - 网络请求
      - 写 usage.jsonl
    Error codes:
      - LLM_CALL_FAILED: 调用失败
    """
    provider = provider or _get_default_provider()  # type: ignore[assignment]
    # "claude" 和 "local" 走 openrouter
    actual_provider = provider if provider in _PROVIDER_DEFAULTS else "openrouter"
    start = time.perf_counter()

    try:
        result = await _call_provider(actual_provider, prompt, temperature, max_tokens, system)
    except Exception as e:
        logger.error("llm_call_failed", provider=actual_provider, tag=tag, error=str(e))
        raise LLMCallError(LLM_CALL_FAILED, str(e)) from e

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    _log_usage(actual_provider, tag, elapsed_ms, max_tokens)
    return result


async def call_llm_json(
    prompt: str,
    *,
    provider: Literal["deepseek", "qwen", "openrouter", "claude", "local"] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    tag: str = "default",
    system: str | None = None,
) -> dict[str, Any]:
    """调用 LLM 并要求返回 JSON，Pydantic 校验

    Error codes:
      - LLM_JSON_PARSE_FAILED: 返回内容无法解析为 JSON
    """
    raw = await call_llm(
        prompt,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        tag=tag,
        system=system,
    )
    try:
        # 尝试提取 JSON 块（LLM 可能包裹在 ```json ... ``` 中）
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0]
        return json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("llm_json_parse_failed", raw=raw[:200], error=str(e))
        raise LLMCallError(LLM_JSON_PARSE_FAILED, f"无法解析 LLM 返回的 JSON: {e}") from e


def _log_usage(provider: str, tag: str, elapsed_ms: int, max_tokens: int) -> None:
    """记录用量到 usage.jsonl"""
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "provider": provider,
        "tag": tag,
        "elapsed_ms": elapsed_ms,
        "max_tokens": max_tokens,
    }
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def _call_provider(
    provider: str, prompt: str, temperature: float, max_tokens: int, system: str | None
) -> str:
    """通用 Provider 调用（所有 provider 都是 OpenAI-compatible API）"""
    api_key, model, base_url = _get_provider_config(provider)

    if not api_key:
        raise RuntimeError(f"未配置 {provider} 的 API Key")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class LLMCallError(Exception):
    """LLM 调用异常"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
