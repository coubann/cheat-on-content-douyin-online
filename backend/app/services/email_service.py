"""邮件发送服务 — SMTP + 验证邮件"""
from __future__ import annotations

import asyncio
import smtplib
import structlog
from email.mime.text import MIMEText

logger = structlog.get_logger()


async def send_verification_email(to_email: str, verify_url: str) -> bool:
    """发送邮箱验证邮件"""
    subject = "验证您的邮箱 — Content Studio"
    body = f"感谢您的注册！\n\n请点击下方链接验证您的邮箱：\n\n{verify_url}\n\n该链接 24 小时内有效。\n如果这不是您本人的操作，请忽略此邮件。"
    return await _send_email(to_email, subject, body)


async def _send_email(to: str, subject: str, body: str) -> bool:
    """底层邮件发送（异步封装 SMTP）"""
    from backend.app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM

    if not SMTP_HOST or not SMTP_USER:
        logger.warning("smtp_not_configured", to=to, subject=subject)
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = to
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _smtp_send, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, to, msg
        )
        logger.info("email_sent", to=to, subject=subject)
        return True
    except Exception as e:
        logger.error("email_send_failed", to=to, error=str(e))
        return False


def _smtp_send(
    host: str, port: int, user: str, password: str, from_addr: str, to_addr: str, msg: MIMEText
) -> None:
    """SMTP 同步发送（在 executor 中执行）"""
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
