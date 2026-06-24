"""视频文案提取服务

从视频链接提取音频 → 转录为文字 → 返回口播文案。
支持抖音、B站、小红书等平台。

转录优先级：
1. faster-whisper 本地转录（无需 API Key，速度快）
2. OpenAI Whisper API（需要 OPENAI_API_KEY）
3. LLM fallback（提示用户手动粘贴）
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from typing import Any

import structlog

from backend.app.services.llm import call_llm_json

logger = structlog.get_logger()

# 匹配常见视频平台 URL 的正则
_VIDEO_URL_PATTERN = re.compile(
    r'(https?://[^\s<>"{}|\\^`\[\]]+(?:douyin|tiktok|bilibili|b23\.tv|xiaohongshu|xhslink|v\.douyin|www\.douyin|space\.bilibili)[^\s<>"{}|\\^`\[\]]*)',
    re.IGNORECASE,
)


def _extract_video_url(raw_input: str) -> str:
    """从用户输入中提取视频链接

    用户可能粘贴抖音分享的完整文本，如：
    '4.87 03/16 F@h.oQ pDh:/ ... https://v.douyin.com/xxx/ 复制此链接...'
    需要从中提取出真正的 URL。
    """
    raw_input = raw_input.strip()

    # 如果本身就是有效 URL，直接返回
    if raw_input.startswith("http://") or raw_input.startswith("https://"):
        return raw_input

    # 从文本中提取视频链接
    match = _VIDEO_URL_PATTERN.search(raw_input)
    if match:
        url = match.group(1)
        # 去掉末尾的中文标点
        url = re.sub(r'[，。！？、；：\u201c\u201d\u2018\u2019\u300a\u300b\u3010\u3011\uff08\uff09\s]+$', '', url)
        logger.info("extracted_url_from_text", original_len=len(raw_input), url=url)
        return url

    # 没找到视频链接，返回原始输入（后续会报错）
    return raw_input


async def extract_transcript(
    video_url: str,
    platform: str = "auto",
) -> dict[str, Any]:
    """从视频链接提取口播文案

    Pre-conditions:
      - video_url 是有效的视频链接
    Post-conditions:
      - 返回转录文本 + 元数据
    Side effects:
      - 下载临时文件（用后即删）
      - 可能调用 faster-whisper / Whisper API
      - LLM 调用 (tag="transcript_cleanup")
    """
    logger.info("transcript_extract_start", url=video_url, platform=platform)

    # 0. 从用户输入中提取真正的视频链接
    video_url = _extract_video_url(video_url)

    # 1. 下载视频/音频
    media_path = None
    metadata = {}

    try:
        media_path, metadata = await _download_media(video_url)
    except Exception as e:
        logger.warning("media_download_failed", url=video_url, error=str(e))
        return await _llm_fallback_transcript(video_url, platform, str(e))

    # 2. 提取音频（如果下载的是视频文件）
    audio_path = media_path
    is_video = media_path and media_path.endswith(".mp4")
    if is_video:
        try:
            audio_path = await _extract_audio_from_video(media_path)
        except Exception as e:
            logger.warning("audio_extract_failed", error=str(e))
            # 直接用视频文件转录（faster-whisper 支持视频格式）
            audio_path = media_path

    # 3. 转录音频
    transcript = ""
    try:
        if audio_path and os.path.exists(audio_path):
            transcript = await _transcribe_audio(audio_path)
    except Exception as e:
        logger.warning("transcription_failed", error=str(e))

    # 4. 清理临时文件
    for path in [media_path, audio_path]:
        if path and path != media_path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    if media_path and os.path.exists(media_path):
        try:
            os.remove(media_path)
        except OSError:
            pass

    # 5. 如果拿到了转录文本，用 LLM 清理格式
    if transcript:
        cleaned = await _cleanup_transcript(transcript, platform)
        transcript = cleaned

    # 6. 如果还是空，用 LLM fallback
    if not transcript:
        return await _llm_fallback_transcript(video_url, platform, "转录为空")

    logger.info("transcript_extract_complete", length=len(transcript))
    return {
        "video_url": video_url,
        "platform": platform,
        "transcript": transcript,
        "metadata": metadata,
        "method": "whisper",
    }


async def _download_media(video_url: str) -> tuple[str | None, dict[str, Any]]:
    """用 yt-dlp 下载视频或音频

    抖音等平台没有纯音频格式，所以先下载视频再提取音频。

    Returns:
      (media_file_path, metadata_dict)
    """
    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, "media.%(ext)s")

    # 先尝试只提取音频（对支持的平台更快）
    cmd = [
        "yt-dlp",
        "-x",  # extract audio
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", output_template,
        "--no-playlist",
        "--max-filesize", "100M",
        "--print-json",
        video_url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    # 如果音频提取失败（如抖音无纯音频格式），下载视频
    if proc.returncode != 0:
        error_msg = stderr.decode()[:500]
        logger.info("audio_extract_not_available, downloading video", error=error_msg)

        cmd_video = [
            "yt-dlp",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "-o", output_template,
            "--no-playlist",
            "--max-filesize", "100M",
            "--print-json",
            video_url,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd_video,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode()[:500]
            logger.error("yt_dlp_download_failed", error=error_msg)
            raise RuntimeError(f"yt-dlp 下载失败: {error_msg}")

    # 找到下载的文件
    media_path = None
    for ext in ["mp3", "m4a", "webm", "opus", "wav", "mp4", "mkv"]:
        candidate = os.path.join(tmp_dir, f"media.{ext}")
        if os.path.exists(candidate):
            media_path = candidate
            break

    # 如果没找到固定扩展名，扫描目录
    if not media_path:
        for f in os.listdir(tmp_dir):
            fp = os.path.join(tmp_dir, f)
            if os.path.isfile(fp):
                media_path = fp
                break

    # 解析元数据
    metadata = {}
    try:
        info = json.loads(stdout.decode())
        metadata = {
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
            "description": info.get("description", "")[:500],
        }
    except Exception:
        pass

    return media_path, metadata


async def _extract_audio_from_video(video_path: str) -> str:
    """用 ffmpeg 从视频中提取音频

    Returns:
      音频文件路径
    """
    audio_path = video_path.rsplit(".", 1)[0] + "_audio.mp4"

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # no video
        "-acodec", "copy",
        "-f", "mp4",
        audio_path,
        "-y",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if proc.returncode != 0 or not os.path.exists(audio_path):
        # 如果 copy 模式失败，尝试重编码
        audio_path_wav = video_path.rsplit(".", 1)[0] + "_audio.wav"
        cmd_wav = [
            "ffmpeg",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            audio_path_wav,
            "-y",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd_wav,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        if os.path.exists(audio_path_wav):
            return audio_path_wav

        raise RuntimeError("ffmpeg 音频提取失败")

    return audio_path


async def _transcribe_audio(audio_path: str) -> str:
    """转录音频

    优先级：
    1. faster-whisper 本地转录
    2. OpenAI Whisper API
    """
    # 1. faster-whisper 本地转录（优先，无需 API Key）
    result = await _faster_whisper_transcribe(audio_path)
    if result:
        return result

    # 2. OpenAI Whisper API
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        result = await _openai_whisper_transcribe(audio_path, openai_key)
        if result:
            return result

    return ""


async def _faster_whisper_transcribe(audio_path: str) -> str:
    """使用 faster-whisper 本地转录

    faster-whisper 基于 CTranslate2，比 openai-whisper 快 4 倍且内存占用更少。
    首次使用会自动下载模型（base 模型约 150MB）。
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.info("faster_whisper_not_installed")
        return ""

    try:
        # 在线程池中运行（faster-whisper 是同步的）
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _run_faster_whisper,
            audio_path,
        )
        return result
    except Exception as e:
        logger.warning("faster_whisper_failed", error=str(e))
        return ""


def _run_faster_whisper(audio_path: str) -> str:
    """同步执行 faster-whisper 转录（在线程池中调用）"""
    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, language="zh", vad_filter=True)

    logger.info("faster_whisper_info",
                language=info.language,
                probability=info.language_probability,
                duration=info.duration)

    full_text = ""
    for segment in segments:
        text = segment.text.strip()
        if text:
            full_text += text + "\n"

    return full_text.strip()


async def _openai_whisper_transcribe(audio_path: str, api_key: str) -> str:
    """使用 OpenAI Whisper API 转录"""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            with open(audio_path, "rb") as f:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data={"model": "whisper-1", "language": "zh"},
                    files={"file": ("audio.mp3", f, "audio/mpeg")},
                )
            if resp.status_code == 200:
                return resp.json().get("text", "")
            logger.warning("openai_whisper_failed", status=resp.status_code)
    except Exception as e:
        logger.warning("openai_whisper_error", error=str(e))
    return ""


async def _cleanup_transcript(raw: str, platform: str = "") -> str:
    """用 LLM 清理转录文本，提取口播文案

    处理：语气词去除、口误修正、繁简转换、语音识别纠错
    """
    if len(raw) < 20:
        return raw

    prompt = f"""以下是一段从{platform or '在线'}视频提取的语音转录文本，可能存在以下问题：
1. 繁体中文需要转为简体中文
2. 语音识别错误（同音字、近音字）
3. 语气词、重复、口误

请清理为流畅的简体中文口播文案，保留原始表达风格和语气，但：
- 去除明显的口误和重复
- 修正语音识别错误（根据上下文推断正确内容）
- 繁体转简体
- 保留专业术语和英文（如 Excel、AI、HTML 等）

原始转录：
{raw[:4000]}

返回 JSON：
```json
{{
  "cleaned": "清理后的口播文案",
  "word_count": 123,
  "style_summary": "一句话风格总结"
}}
```"""

    try:
        result = await call_llm_json(prompt, tag="transcript_cleanup", temperature=0.2)
        return result.get("cleaned", raw)
    except Exception as e:
        logger.warning("transcript_cleanup_failed", error=str(e))
        return raw


async def _llm_fallback_transcript(
    video_url: str,
    platform: str,
    error: str,
) -> dict[str, Any]:
    """LLM 降级方案：无法下载/转录时，用 LLM 模拟"""
    logger.warning("transcript_llm_fallback", url=video_url, error=error)

    prompt = f"""用户想从以下视频链接提取口播文案，但系统无法自动下载/转录（原因：{error}）。

视频链接: {video_url}
平台: {platform}

请告知用户无法自动提取，建议他们手动粘贴文案内容。
返回 JSON：
```json
{{
  "transcript": "",
  "error": "无法自动提取视频文案，请手动粘贴视频的口播文案内容",
  "suggestion": "你可以：1. 打开视频，边听边打字记录口播内容 "
    "2. 使用手机语音转文字功能 3. 如果视频有字幕，可以复制字幕文本"
}}
```"""

    result = await call_llm_json(prompt, tag="transcript_fallback", temperature=0.2)
    return {
        "video_url": video_url,
        "platform": platform,
        "transcript": result.get("transcript", ""),
        "error": result.get("error", "无法自动提取视频文案"),
        "suggestion": result.get("suggestion", "请手动粘贴视频的口播文案"),
        "method": "fallback",
    }
