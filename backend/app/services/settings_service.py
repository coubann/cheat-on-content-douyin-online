"""LLM Provider 配置服务 — 管理 API Key / Model / Base URL"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write

logger = structlog.get_logger()

# 每个 Provider 的完整配置定义
PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_model": "deepseek-chat",
        "default_base_url": "https://api.deepseek.com/chat/completions",
        "available_models": [
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ],
        "docs_url": "https://api-docs.deepseek.com/zh-cn/",
    },
    "qwen": {
        "label": "通义千问 (DashScope)",
        "api_key_env": "DASHSCOPE_API_KEY",
        "model_env": "DASHSCOPE_MODEL",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "default_model": "qwen-plus",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "available_models": [
            "qwen-turbo",
            "qwen-plus",
            "qwen-max",
            "qwen3-max",
            "qwen3.5-plus",
            "qwen3.5-flash",
            "qwen3.6-plus",
            "qwen3.6-flash",
            "qwen3.7-max",
            "qwen-long",
            "qwen3-coder-plus",
            "qwq-plus",
        ],
        "docs_url": "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
    },
    "openrouter": {
        "label": "OpenRouter",
        "api_key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "base_url_env": "OPENROUTER_BASE_URL",
        "default_model": "anthropic/claude-sonnet-4",
        "default_base_url": "https://openrouter.ai/api/v1/chat/completions",
        "available_models": [
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-haiku",
            "google/gemini-2.5-flash-preview",
            "meta-llama/llama-4-maverick",
            "deepseek/deepseek-chat-v3-0324",
            "qwen/qwen3-235b-a22b",
        ],
        "docs_url": "https://openrouter.ai/keys",
    },
}


def _read_env_var_from_file(key: str) -> str | None:
    """直接从 .env 文件读取变量值（绕过 os.environ 缓存问题）"""
    env_path = _find_env_path()
    if not env_path.exists():
        return None
    prefix = f"{key}="
    for line in read_file(env_path).strip().split("\n"):
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip("\"'")
    return None


def _get_env_var(key: str, default: str = "") -> str:
    """获取环境变量 — 优先 os.environ（排除占位符），其次 .env 文件"""
    val = os.environ.get(key, "")
    # 跳过占位符值，去 .env 文件读真实值
    if val and val != "sk-placeholder":
        return val
    file_val = _read_env_var_from_file(key)
    # 如果 .env 文件中也是占位符，返回空
    if file_val and file_val != "sk-placeholder":
        return file_val
    return default


def get_provider_settings() -> dict[str, Any]:
    """获取所有 Provider 的完整配置状态

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回各 provider 的配置状态（key 脱敏）
    Side effects:
      - 无
    """
    providers = []
    for name, cfg in PROVIDER_CONFIG.items():
        api_key = _get_env_var(cfg["api_key_env"])
        configured = bool(api_key) and api_key != "sk-placeholder"
        masked_key = ""
        if api_key and len(api_key) > 8:
            masked_key = api_key[:4] + "****" + api_key[-4:]
        elif api_key:
            masked_key = "****"

        model = _get_env_var(cfg["model_env"]) or cfg["default_model"]
        base_url = _get_env_var(cfg["base_url_env"]) or cfg["default_base_url"]

        providers.append({
            "name": name,
            "label": cfg["label"],
            "configured": configured,
            "masked_key": masked_key,
            "model": model,
            "base_url": base_url,
            "default_model": cfg["default_model"],
            "default_base_url": cfg["default_base_url"],
            "available_models": cfg["available_models"],
            "api_key_env": cfg["api_key_env"],
            "docs_url": cfg["docs_url"],
        })

    # 优先从 .env 文件读取（避免 os.environ 缓存问题）
    current = _read_env_var_from_file("DEFAULT_LLM_PROVIDER") or os.environ.get("DEFAULT_LLM_PROVIDER", "deepseek")
    return {
        "providers": providers,
        "default_provider": current,
        "any_configured": any(p["configured"] for p in providers),
    }


def save_provider_settings(
    provider_name: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """保存单个 Provider 的配置

    Pre-conditions:
      - provider_name 有效
      - .env 文件可写
    Post-conditions:
      - .env 被更新
      - 当前进程环境变量被更新
    Side effects:
      - 写文件系统
      - 更新 os.environ
    """
    if provider_name not in PROVIDER_CONFIG:
        return {"status": "error", "message": f"未知 provider: {provider_name}"}

    cfg = PROVIDER_CONFIG[provider_name]
    env_path = _find_env_path()

    existing_lines = _read_env(env_path)
    updated: list[str] = []

    # API Key
    if api_key is not None and api_key.strip():
        _update_env_var(existing_lines, cfg["api_key_env"], api_key.strip())
        os.environ[cfg["api_key_env"]] = api_key.strip()
        updated.append("api_key")

    # Model
    if model is not None and model.strip():
        _update_env_var(existing_lines, cfg["model_env"], model.strip())
        os.environ[cfg["model_env"]] = model.strip()
        updated.append("model")

    # Base URL
    if base_url is not None and base_url.strip():
        _update_env_var(existing_lines, cfg["base_url_env"], base_url.strip())
        os.environ[cfg["base_url_env"]] = base_url.strip()
        updated.append("base_url")

    safe_write(env_path, "\n".join(existing_lines) + "\n")
    logger.info("provider_settings_saved", provider=provider_name, updated=updated)
    return {"status": "ok", "provider": provider_name, "updated": updated}


def save_default_provider(provider: str) -> dict[str, Any]:
    """保存默认 Provider"""
    if provider not in PROVIDER_CONFIG:
        return {"status": "error", "message": f"未知 provider: {provider}"}

    env_path = _find_env_path()
    existing_lines = _read_env(env_path)
    _update_env_var(existing_lines, "DEFAULT_LLM_PROVIDER", provider)
    os.environ["DEFAULT_LLM_PROVIDER"] = provider
    safe_write(env_path, "\n".join(existing_lines) + "\n")
    return {"status": "ok", "default_provider": provider}


async def test_provider_connection(provider_name: str) -> dict[str, Any]:
    """测试 Provider 连接是否可用 — 发送一个最小请求验证 API Key

    Pre-conditions:
      - provider_name 有效
      - API Key 已配置
    Post-conditions:
      - 返回连接测试结果
    Side effects:
      - 网络请求（1 次 LLM 调用）
    """
    if provider_name not in PROVIDER_CONFIG:
        return {"ok": False, "message": f"未知 provider: {provider_name}"}

    cfg = PROVIDER_CONFIG[provider_name]
    api_key = _get_env_var(cfg["api_key_env"])
    model = _get_env_var(cfg["model_env"]) or cfg["default_model"]
    base_url = _get_env_var(cfg["base_url_env"]) or cfg["default_base_url"]

    if not api_key or api_key == "sk-placeholder":
        return {"ok": False, "message": "API Key 未配置"}

    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                base_url,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5,
                },
            )
            if resp.status_code == 200:
                return {"ok": True, "provider": provider_name, "model": model}
            else:
                try:
                    body = resp.json()
                    err_msg = body.get("error", {}).get("message", resp.text[:200])
                except Exception:
                    err_msg = resp.text[:200]
                return {"ok": False, "message": f"HTTP {resp.status_code}: {err_msg}"}
    except httpx.ConnectError as e:
        return {"ok": False, "message": f"连接失败: {e}"}
    except httpx.TimeoutException:
        return {"ok": False, "message": "连接超时（15秒）"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


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


def _read_env(env_path: Path) -> list[str]:
    """读取 .env 文件行"""
    if env_path.exists():
        return read_file(env_path).strip().split("\n")
    return []


def _update_env_var(lines: list[str], key: str, value: str) -> None:
    """更新 .env 文件中的某个变量（原地修改 lines）"""
    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}={value}"
            return
    lines.append(f"{key}={value}")
