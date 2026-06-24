"""风格模仿服务 — cheat-learn-from 的 Python 实现

对标账号导入 → 提取风格指纹 → 生成模仿脚本
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from backend.app.services.file_io import read_file, safe_write
from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()


async def import_benchmark(
    data_dir: Path,
    account_name: str,
    platform: str,
    sample_contents: list[str],
) -> dict[str, Any]:
    """导入对标账号

    Pre-conditions:
      - account_name 非空
      - sample_contents 至少 1 条（或包含 "__auto_fetch__" 标记）
    Post-conditions:
      - benchmarks/<hash>.md 被创建（含风格指纹）
      - 返回风格指纹
    Side effects:
      - LLM 调用 (tag="style_extract")
      - 写文件系统
    """
    logger.info("benchmark_import_start", account=account_name, platform=platform)

    # 自动模式：用 LLM 模拟该账号的内容样本
    if sample_contents == ["__auto_fetch__"]:
        sample_contents = await _auto_fetch_samples(account_name, platform)

    # 提取风格指纹
    fingerprint = await _extract_style_fingerprint(account_name, platform, sample_contents)

    # 存储
    bench_dir = data_dir / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)

    account_hash = hashlib.sha256(f"{platform}:{account_name}".encode()).hexdigest()[:8]
    bench_path = bench_dir / f"{account_hash}_{account_name}.md"

    content = f"""# 对标账号: {account_name}

> 平台: {platform}
> 导入时间: {datetime.now().isoformat()}

## 风格指纹

{fingerprint['fingerprint_text']}

## 关键特征

| 特征 | 描述 |
|---|---|
{chr(10).join(f'| {k} | {v} |' for k, v in fingerprint['traits'].items())}

## 常用句式

{chr(10).join(f'- {p}' for p in fingerprint['patterns'])}

## 原始样本

<details>
<summary>展开 {len(sample_contents)} 条样本</summary>

{chr(10).join(f'### 样本 {i+1}{chr(10)}{s}' for i, s in enumerate(sample_contents))}

</details>
"""
    safe_write(bench_path, content)

    logger.info("benchmark_import_complete", account=account_name, hash=account_hash)
    return {
        "account": account_name,
        "platform": platform,
        "hash": account_hash,
        "fingerprint": fingerprint,
        "path": str(bench_path),
    }


async def list_benchmarks(data_dir: Path) -> list[dict[str, Any]]:
    """列出所有对标账号

    Pre-conditions:
      - 无
    Post-conditions:
      - 返回对标账号列表
    Side effects:
      - 无
    """
    bench_dir = data_dir / "benchmarks"
    if not bench_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for f in sorted(bench_dir.glob("*.md")):
        stat = f.stat()
        # 从文件名解析 account_name
        parts = f.stem.split("_", 1)
        account_name = parts[1] if len(parts) > 1 else f.stem
        results.append({
            "id": f.stem,
            "account": account_name,
            "path": str(f),
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return results


async def extract_style_from_transcript(
    data_dir: Path,
    video_url: str,
    transcript: str,
    platform: str = "douyin",
    label: str = "",
) -> dict[str, Any]:
    """从视频文案提取风格指纹

    用户给一个视频链接，系统提取口播文案，分析风格特征。

    Pre-conditions:
      - transcript 非空（视频文案文本）
    Post-conditions:
      - benchmarks/<label>.md 被创建
      - 返回风格指纹
    Side effects:
      - LLM 调用 (tag="style_extract")
      - 写文件系统
    """
    if not label:
        label = f"video_{datetime.now().strftime('%m%d_%H%M')}"

    # 提取风格指纹
    fingerprint = await _extract_style_from_text(transcript, platform)

    # 存储
    bench_dir = data_dir / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)

    bench_path = bench_dir / f"{label}.md"

    content = f"""# 风格参考: {label}

> 来源: {video_url or '手动输入'}
> 平台: {platform}
> 导入时间: {datetime.now().isoformat()}

## 原始文案

{transcript}

## 风格指纹

{fingerprint['fingerprint_text']}

## 关键特征

| 特征 | 描述 |
|---|---|
{chr(10).join(f'| {k} | {v} |' for k, v in fingerprint['traits'].items())}

## 常用句式

{chr(10).join(f'- {p}' for p in fingerprint['patterns'])}
"""
    safe_write(bench_path, content)

    logger.info("style_extract_complete", label=label)
    return {
        "label": label,
        "platform": platform,
        "video_url": video_url,
        "fingerprint": fingerprint,
        "transcript_length": len(transcript),
        "path": str(bench_path),
    }


async def _extract_style_from_text(
    text: str,
    platform: str,
) -> dict[str, Any]:
    """从口播文案文本提取风格指纹"""
    prompt = f"""分析以下来自 {platform} 的口播文案，提取风格指纹。

这是视频的口播文案（说话内容），请分析说话风格、语气、句式、节奏等。

文案内容:
{text[:4000]}

返回 JSON：
```json
{{
  "fingerprint_text": "一句话风格总结",
  "traits": {{
    "tone": "语气特征（如：犀利/温和/幽默/严肃/唠嗑式/说教式）",
    "opening_style": "开头方式（如：提问式/场景式/反常识式/直接式）",
    "transition_style": "转折方式（如：但是/然而/关键是/你猜怎么着）",
    "ending_style": "结尾方式（如：金句收尾/互动提问/行动号召/留悬念）",
    "rhythm": "节奏特征（如：短句密集/长短交替/排比推进）",
    "vocabulary_level": "用词水平（如：口语化/书面化/专业术语多/接地气）"
  }},
  "patterns": ["常用句式1", "常用句式2", "常用句式3"]
}}
```"""

    result = await call_llm_json(prompt, tag="style_extract", temperature=0.2)
    return {
        "fingerprint_text": result.get("fingerprint_text", ""),
        "traits": result.get("traits", {}),
        "patterns": result.get("patterns", []),
    }


async def mimic_style(
    data_dir: Path,
    style_label: str = "",
    account_name: str = "",
    title: str = "",
    brief: str = "",
    topic: str = "",
    content_form: str = "opinion-video",
) -> dict[str, Any]:
    """模仿风格生成文案

    Pre-conditions:
      - style_label 对应的风格参考已存在
    Post-conditions:
      - 返回模仿生成的文案
    Side effects:
      - LLM 调用 (tag="style_mimic")
    """
    # 向后兼容：如果传了 account_name 但没传 style_label，用 account_name
    effective_label = style_label or account_name
    effective_title = title or topic

    logger.info("style_mimic_start", style=effective_label, title=effective_title)

    # 读取风格指纹
    bench_dir = data_dir / "benchmarks"
    bench_file = _find_benchmark_file(bench_dir, effective_label)
    if not bench_file:
        return {"error": f"风格参考 {effective_label} 未找到", "suggested_action": "请先提取视频文案风格"}

    bench_content = read_file(bench_file)

    # 提取原始文案和风格指纹
    original_transcript = ""

    m = re.search(r"## 原始文案\s*\n\n(.+?)(?=\n## |\Z)", bench_content, re.DOTALL)
    if m:
        original_transcript = m.group(1).strip()[:2000]

    prompt = f"""请模仿以下风格参考的口播风格，为指定标题和大意生成一段口播文案。

## 风格参考

{bench_content[:3000]}

{'## 参考原文案（重点模仿其说话方式）' if original_transcript else ''}
{original_transcript if original_transcript else ''}

## 生成要求

- 标题: {effective_title}
{f'- 大意/方向: {brief}' if brief else ''}
- 内容形态: {content_form}
- 严格模仿参考风格的：语气、句式、开头方式、转折方式、结尾方式、节奏
- 但内容必须是关于「{effective_title}」的原创内容
- 长度: 200-500 字
- 输出为口播文案格式，可以直接照着念

返回 JSON：
```json
{{
  "script": "生成的口播文案",
  "title_suggestion": "建议的视频标题",
  "style_notes": "模仿了哪些风格特征",
  "confidence": 0.8
}}
```"""

    result = await call_llm_json(prompt, tag="style_mimic", temperature=0.7)

    logger.info("style_mimic_complete", style=effective_label)
    return {
        "style_label": effective_label,
        "title": effective_title,
        "brief": brief,
        "script": result.get("script", ""),
        "title_suggestion": result.get("title_suggestion", ""),
        "style_notes": result.get("style_notes", ""),
        "confidence": result.get("confidence", 0.5),
    }


async def _extract_style_fingerprint(
    account_name: str,
    platform: str,
    samples: list[str],
) -> dict[str, Any]:
    """提取风格指纹

    Pre-conditions:
      - samples 至少 1 条
    Post-conditions:
      - 返回风格指纹 dict
    Side effects:
      - LLM 调用 (tag="style_extract")
    """
    samples_text = "\n---\n".join(samples[:5])  # 最多 5 条

    prompt = f"""分析以下来自 {platform} 账号 "{account_name}" 的内容样本，提取风格指纹。

样本内容:
{samples_text[:4000]}

返回 JSON：
```json
{{
  "fingerprint_text": "一句话风格总结",
  "traits": {{
    "tone": "语气特征",
    "opening_style": "开头方式",
    "transition_style": "转折方式",
    "ending_style": "结尾方式",
    "vocabulary_level": "用词水平",
    "humor_type": "幽默类型"
  }},
  "patterns": ["常用句式1", "常用句式2", "常用句式3"]
}}
```"""

    result = await call_llm_json(prompt, tag="style_extract", temperature=0.2)
    return {
        "fingerprint_text": result.get("fingerprint_text", ""),
        "traits": result.get("traits", {}),
        "patterns": result.get("patterns", []),
    }


def _find_benchmark_file(bench_dir: Path, name: str) -> Path | None:
    """查找对标账号文件 — 支持 account_name 和 label 两种查找方式"""
    if not bench_dir.exists():
        return None
    # 1. 精确匹配文件名 (label 方式)
    exact_match = bench_dir / f"{name}.md"
    if exact_match.exists():
        return exact_match
    # 2. 模糊匹配 stem (account_name 方式, 含 hash 前缀)
    for f in bench_dir.glob("*.md"):
        if name in f.stem:
            return f
    return None


async def get_benchmark_detail(data_dir: Path, bench_id: str) -> dict[str, Any] | None:
    """获取对标账号详情（结构化）

    Pre-conditions:
      - bench_id 非空
    Post-conditions:
      - 返回结构化的对标账号数据
    Side effects:
      - 无
    """
    bench_dir = data_dir / "benchmarks"
    bench_path = bench_dir / f"{bench_id}.md"
    if not bench_path.exists():
        return None

    content = read_file(bench_path)

    # 解析 markdown 提取结构化数据
    result: dict[str, Any] = {"id": bench_id, "raw": content}

    # 提取账号名/风格名（兼容两种格式）
    m = re.search(r"^# (?:对标账号|风格参考):\s*(.+)$", content, re.MULTILINE)
    result["account"] = m.group(1).strip() if m else bench_id

    # 提取平台
    m = re.search(r"^> 平台:\s*(.+)$", content, re.MULTILINE)
    result["platform"] = m.group(1).strip() if m else ""

    # 提取来源（视频链接）
    m = re.search(r"^> 来源:\s*(.+)$", content, re.MULTILINE)
    result["source_url"] = m.group(1).strip() if m else ""

    # 提取导入时间
    m = re.search(r"^> 导入时间:\s*(.+)$", content, re.MULTILINE)
    result["imported_at"] = m.group(1).strip() if m else ""

    # 提取风格指纹文本
    m = re.search(r"^## 风格指纹\s*\n\n(.+?)(?=\n## |\Z)", content, re.DOTALL | re.MULTILINE)
    result["fingerprint_text"] = m.group(1).strip() if m else ""

    # 提取关键特征表格
    traits: dict[str, str] = {}
    trait_section = re.search(r"^## 关键特征\s*\n\n(.+?)(?=\n## |\Z)", content, re.DOTALL | re.MULTILINE)
    if trait_section:
        for line in trait_section.group(1).strip().split("\n"):
            if line.startswith("|") and not line.startswith("|---") and not line.startswith("| 特征"):
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 2:
                    traits[cells[0]] = cells[1]
    result["traits"] = traits

    # 提取常用句式
    patterns: list[str] = []
    pattern_section = re.search(r"^## 常用句式\s*\n\n(.+?)(?=\n## |\Z)", content, re.DOTALL | re.MULTILINE)
    if pattern_section:
        for line in pattern_section.group(1).strip().split("\n"):
            if line.startswith("- "):
                patterns.append(line[2:].strip())
    result["patterns"] = patterns

    # 提取原始文案/原始样本
    samples: list[str] = []
    # 优先匹配 "## 原始文案"（extract_style_from_transcript 保存的格式）
    transcript_section = re.search(r"^## 原始文案\s*\n\n(.+?)(?=\n## |\Z)", content, re.DOTALL | re.MULTILINE)
    if transcript_section:
        text = transcript_section.group(1).strip()
        if text:
            samples.append(text)
    # 兼容 "## 原始样本"（import_benchmark 保存的格式）
    if not samples:
        sample_section = re.search(r"^## 原始样本\s*\n\n(.+?)(?=\n## |\Z)", content, re.DOTALL | re.MULTILINE)
        if sample_section:
            sample_text = sample_section.group(1)
            parts = re.split(r"### 样本 \d+\n", sample_text)
            for part in parts[1:]:
                text = part.strip()
                text = re.sub(r"</?details>", "", text).strip()
                text = re.sub(r"<summary>.*?</summary>", "", text).strip()
                if text:
                    samples.append(text)
    result["samples"] = samples

    return result


async def delete_benchmark(data_dir: Path, bench_id: str) -> dict[str, Any]:
    """删除对标账号

    Pre-conditions:
      - bench_id 非空
    Post-conditions:
      - 删除对标账号文件
    Side effects:
      - 删除文件
    """
    bench_dir = data_dir / "benchmarks"
    bench_path = bench_dir / f"{bench_id}.md"
    if not bench_path.exists():
        raise FileNotFoundError(f"对标账号 {bench_id} 不存在")
    bench_path.unlink()
    logger.info("benchmark_deleted", bench_id=bench_id)
    return {"id": bench_id, "deleted": True}


async def _auto_fetch_samples(account_name: str, platform: str) -> list[str]:
    """通过 Playwright 浏览器自动化抓取账号内容样本

    Pre-conditions:
      - account_name 非空
    Post-conditions:
      - 返回 3-5 条内容样本
    Side effects:
      - 启动浏览器
    """
    from backend.app.services.account_fetcher import fetch_account_samples
    samples = await fetch_account_samples(account_name, platform, count=5)
    logger.info("auto_fetch_complete", account=account_name, platform=platform, count=len(samples))
    return samples
