"""账号内容抓取服务

所有平台统一使用 Playwright + 系统 Chrome 浏览器自动化抓取。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

logger = structlog.get_logger()

# 公共浏览器配置
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1280, "height": 800}
PAGE_TIMEOUT = 30000


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def _is_noise_line(line: str) -> bool:
    """判断是否为噪声行（播放量、时长、导航等）"""
    stripped = line.replace(".", "").replace("万", "").replace(" ", "").replace(",", "")
    if stripped.isdigit():
        return True
    if re.match(r"^\d+[小时天分钟周月年前]+$", line):
        return True
    if line in ("昨天", "今天", "前天", "最新", "合作", "广告"):
        return True
    return bool(":" in line and len(line) < 10 and not _has_chinese(line))


# ─── B站 ────────────────────────────────────────────────────


async def fetch_bilibili_samples(uid: str, count: int = 5) -> list[str]:
    """通过 Playwright 抓取 B站用户空间视频标题"""
    logger.info("bilibili_fetch_start", uid=uid)

    def _scrape() -> list[str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(user_agent=UA, viewport=VIEWPORT)
            page = context.new_page()
            samples = []

            try:
                page.goto(f"https://space.bilibili.com/{uid}/video", timeout=PAGE_TIMEOUT, wait_until="networkidle")
                page.evaluate("window.scrollTo(0, 800)")
                page.wait_for_timeout(3000)

                # 获取用户名
                username_el = page.query_selector("#h-name") or page.query_selector('[class*="nickname"]')
                username = username_el.inner_text().strip() if username_el else uid

                # B站空间页的视频链接成对出现：
                # 奇数索引（0,2,4...）= 缩略图链接（含播放量/弹幕/时长）
                # 偶数索引（1,3,5...）= 标题链接（含视频标题文本）
                video_links = page.query_selector_all('a[href*="/video/BV"]')
                seen_bvids: set[str] = set()
                for i, link_el in enumerate(video_links):
                    # 只取标题链接（奇数索引，即第2、4、6...个链接）
                    if i % 2 == 0:
                        continue
                    try:
                        href = link_el.get_attribute("href") or ""
                        import re
                        bvid_match = re.search(r"BV\w+", href)
                        bvid = bvid_match.group(0) if bvid_match else ""
                        if not bvid or bvid in seen_bvids:
                            continue
                        seen_bvids.add(bvid)

                        title = link_el.inner_text().strip()
                        if title and len(title) > 2:
                            samples.append(f"【{title}】")
                        if len(samples) >= count:
                            break
                    except Exception:
                        continue

                if not samples:
                    samples = [f"[B站用户 {username} 暂无公开投稿]"]

            except Exception as e:
                logger.warning("bilibili_scrape_failed", uid=uid, error=str(e))
                samples = [f"[B站用户 {uid} 抓取失败: {str(e)[:100]}]"]
            finally:
                browser.close()
            return samples[:count]

    loop = asyncio.get_event_loop()
    samples = await loop.run_in_executor(None, _scrape)
    logger.info("bilibili_fetch_complete", uid=uid, count=len(samples))
    return samples


# ─── 抖音 ────────────────────────────────────────────────────


async def fetch_douyin_samples(account_id: str, count: int = 5) -> list[str]:
    """通过 Playwright 抓取抖音用户主页内容"""
    logger.info("douyin_fetch_start", account=account_id)

    def _scrape() -> list[str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(user_agent=UA, viewport=VIEWPORT)
            page = context.new_page()
            samples = []

            try:
                # 抖音用户主页 URL 格式：https://www.douyin.com/user/抖音号
                page.goto(f"https://www.douyin.com/user/{account_id}", timeout=PAGE_TIMEOUT, wait_until="networkidle")
                # 滚动触发懒加载
                for scroll_y in [400, 800, 1200]:
                    page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    page.wait_for_timeout(2000)

                # 获取用户昵称
                nickname_el = (
                    page.query_selector('[class*="nickname"]')
                    or page.query_selector('[class*="user-name"]')
                    or page.query_selector("h1")
                )
                nickname = nickname_el.inner_text().strip() if nickname_el else account_id

                # 获取简介
                bio_el = (
                    page.query_selector('[class*="bio"]')
                    or page.query_selector('[class*="desc"]')
                    or page.query_selector('[class*="signature"]')
                )
                bio = bio_el.inner_text().strip() if bio_el else ""

                # 从页面文本提取视频描述
                text = page.inner_text("body")
                skip_keywords = [
                    "登录", "注册", "首页", "推荐", "关注", "热点",
                    "搜索", "消息", "我", "发布", "喜欢", "收藏",
                    "粉丝", "关注", "获赞", "抖音", "直播",
                ]
                seen = set()
                for line in text.split("\n"):
                    line = line.strip()
                    if len(line) < 6 or _is_noise_line(line):
                        continue
                    if any(kw in line for kw in skip_keywords):
                        continue
                    if line == nickname or line in seen:
                        continue
                    if _has_chinese(line) or len(line) > 15:
                        seen.add(line)
                        samples.append(f"【{line}】")
                        if len(samples) >= count:
                            break

                # 如果没提取到视频描述，至少返回昵称+简介
                if not samples and bio:
                    samples = [f"[{nickname}]\n{bio}"]

                if not samples:
                    samples = [f"[抖音用户 {nickname} 暂无公开内容]"]

            except Exception as e:
                logger.warning("douyin_scrape_failed", account=account_id, error=str(e))
                samples = [f"[抖音账号 {account_id} 抓取失败: {str(e)[:100]}]"]
            finally:
                browser.close()
            return samples[:count]

    loop = asyncio.get_event_loop()
    samples = await loop.run_in_executor(None, _scrape)
    logger.info("douyin_fetch_complete", account=account_id, count=len(samples))
    return samples


# ─── 小红书 ──────────────────────────────────────────────────


async def fetch_xiaohongshu_samples(account_id: str, count: int = 5) -> list[str]:
    """通过 Playwright 抓取小红书用户笔记内容"""
    logger.info("xiaohongshu_fetch_start", account=account_id)

    def _scrape() -> list[str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(user_agent=UA, viewport=VIEWPORT)
            page = context.new_page()
            samples = []

            try:
                # 先搜索用户
                page.goto(
                    f"https://www.xiaohongshu.com/search_result?keyword={account_id}&source=web_user_page",
                    timeout=PAGE_TIMEOUT,
                    wait_until="networkidle",
                )
                page.wait_for_timeout(3000)

                # 尝试点击用户搜索结果进入主页
                user_tab = page.query_selector('[class*="user"]') or page.query_selector('a[href*="/user/profile/"]')
                if user_tab:
                    try:
                        user_tab.click()
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass

                # 滚动触发懒加载
                for scroll_y in [400, 800, 1200]:
                    page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    page.wait_for_timeout(1500)

                # 从页面文本提取笔记标题/描述
                text = page.inner_text("body")
                skip_keywords = [
                    "登录", "注册", "首页", "搜索", "发布", "消息",
                    "小红书", "关注", "粉丝", "获赞", "收藏",
                ]
                seen = set()
                for line in text.split("\n"):
                    line = line.strip()
                    if len(line) < 6 or _is_noise_line(line):
                        continue
                    if any(kw in line for kw in skip_keywords):
                        continue
                    if line in seen:
                        continue
                    if _has_chinese(line) or len(line) > 15:
                        seen.add(line)
                        samples.append(f"【{line}】")
                        if len(samples) >= count:
                            break

                if not samples:
                    samples = [f"[小红书账号 {account_id} 暂无公开笔记或页面加载失败]"]

            except Exception as e:
                logger.warning("xiaohongshu_scrape_failed", account=account_id, error=str(e))
                samples = [f"[小红书账号 {account_id} 抓取失败: {str(e)[:100]}]"]
            finally:
                browser.close()
            return samples[:count]

    loop = asyncio.get_event_loop()
    samples = await loop.run_in_executor(None, _scrape)
    logger.info("xiaohongshu_fetch_complete", account=account_id, count=len(samples))
    return samples


# ─── 微信公众号 ──────────────────────────────────────────────


async def fetch_wechat_samples(account_name: str, count: int = 5) -> list[str]:
    """通过 Playwright 抓取微信公众号文章"""
    logger.info("wechat_fetch_start", account=account_name)

    def _scrape() -> list[str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(user_agent=UA, viewport=VIEWPORT)
            page = context.new_page()
            samples = []

            try:
                # 通过搜狗微信搜索公众号
                page.goto(
                    f"https://weixin.sogou.com/weixin?type=1&query={account_name}",
                    timeout=PAGE_TIMEOUT,
                    wait_until="networkidle",
                )
                page.wait_for_timeout(3000)

                # 获取公众号主页链接
                account_link = page.query_selector('a[href*="mp.weixin.qq.com"]')
                profile_url = account_link.get_attribute("href") if account_link else ""

                if profile_url:
                    # 进入公众号主页
                    page.goto(profile_url, timeout=PAGE_TIMEOUT, wait_until="networkidle")
                    page.wait_for_timeout(3000)

                    # 滚动加载更多文章
                    for scroll_y in [400, 800, 1200]:
                        page.evaluate(f"window.scrollTo(0, {scroll_y})")
                        page.wait_for_timeout(1500)

                    # 从页面文本提取文章标题
                    text = page.inner_text("body")
                    skip_keywords = [
                        "登录", "注册", "搜索", "关注", "粉丝",
                        "阅读", "点赞", "在看", "分享", "收藏",
                    ]
                    seen = set()
                    for line in text.split("\n"):
                        line = line.strip()
                        if len(line) < 6 or _is_noise_line(line):
                            continue
                        if any(kw in line for kw in skip_keywords):
                            continue
                        if line in seen:
                            continue
                        if _has_chinese(line) or len(line) > 15:
                            seen.add(line)
                            samples.append(f"【{line}】")
                            if len(samples) >= count:
                                break

                if not samples:
                    # 搜狗搜索结果页也可能有文章标题
                    text = page.inner_text("body")
                    for line in text.split("\n"):
                        line = line.strip()
                        if len(line) < 6 or _is_noise_line(line):
                            continue
                        if line in seen:
                            continue
                        if _has_chinese(line) and len(line) > 6:
                            seen.add(line)
                            samples.append(f"【{line}】")
                            if len(samples) >= count:
                                break

                if not samples:
                    samples = [f"[微信公众号 {account_name} 暂无公开文章或搜索无结果]"]

            except Exception as e:
                logger.warning("wechat_scrape_failed", account=account_name, error=str(e))
                samples = [f"[微信公众号 {account_name} 抓取失败: {str(e)[:100]}]"]
            finally:
                browser.close()
            return samples[:count]

    loop = asyncio.get_event_loop()
    samples = await loop.run_in_executor(None, _scrape)
    logger.info("wechat_fetch_complete", account=account_name, count=len(samples))
    return samples


# ─── 评论抓取 ────────────────────────────────────────────────


async def fetch_douyin_comments(video_url: str, count: int = 20) -> list[dict[str, Any]]:
    """通过 Playwright 抓取抖音视频评论

    Pre-conditions:
      - video_url 为有效的抖音视频链接
      - count >= 1
    Post-conditions:
      - 返回评论列表 [{"text": "...", "likes": 0, "replies": 0}]
    Side effects:
      - 启动浏览器
    """
    logger.info("douyin_comments_fetch_start", url=video_url)

    def _scrape() -> list[dict[str, Any]]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(user_agent=UA, viewport=VIEWPORT)
            page = context.new_page()
            comments: list[dict[str, Any]] = []

            try:
                page.goto(video_url, timeout=PAGE_TIMEOUT, wait_until="networkidle")
                page.wait_for_timeout(3000)

                # 滚动加载评论
                for scroll_y in [600, 1200, 1800]:
                    page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    page.wait_for_timeout(2000)

                # 尝试点击评论区域展开
                comment_tab = page.query_selector('[class*="comment"]') or page.query_selector('[class*="Comment"]')
                if comment_tab:
                    try:
                        comment_tab.click()
                        page.wait_for_timeout(2000)
                    except Exception:
                        pass

                # 提取评论
                comment_els = page.query_selector_all(
                    '[class*="comment-item"], '
                    '[class*="CommentItem"], '
                    '[class*="commentContent"]'
                )
                for el in comment_els:
                    try:
                        text = el.inner_text().strip()
                        if not text or len(text) < 2:
                            continue

                        # 尝试提取点赞数
                        likes = 0
                        like_el = el.query_selector(
                            '[class*="like"] [class*="count"], '
                            '[class*="digg"] [class*="count"]'
                        )
                        if like_el:
                            like_text = like_el.inner_text().strip()
                            likes = int(re.sub(r"[^\d]", "", like_text) or "0")

                        # 尝试提取回复数
                        replies = 0
                        reply_el = el.query_selector(
                            '[class*="reply"] [class*="count"], '
                            '[class*="sub-comment"] [class*="count"]'
                        )
                        if reply_el:
                            reply_text = reply_el.inner_text().strip()
                            replies = int(re.sub(r"[^\d]", "", reply_text) or "0")

                        comments.append({"text": text, "likes": likes, "replies": replies})
                        if len(comments) >= count:
                            break
                    except Exception:
                        continue

                # 备选方案：从页面文本提取
                if not comments:
                    text = page.inner_text("body")
                    skip_keywords = ["登录", "注册", "推荐", "关注", "分享", "收藏", "点赞"]
                    for line in text.split("\n"):
                        line = line.strip()
                        if len(line) < 4 or _is_noise_line(line):
                            continue
                        if any(kw in line for kw in skip_keywords):
                            continue
                        if _has_chinese(line) or len(line) > 10:
                            comments.append({"text": line, "likes": 0, "replies": 0})
                            if len(comments) >= count:
                                break

            except Exception as e:
                logger.warning("douyin_comments_scrape_failed", url=video_url, error=str(e))
            finally:
                browser.close()
            return comments[:count]

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _scrape)
    logger.info("douyin_comments_fetch_complete", url=video_url, count=len(result))
    return result


async def fetch_bilibili_comments(bvid: str, count: int = 20) -> list[dict[str, Any]]:
    """通过 Playwright 抓取 B站视频评论

    Pre-conditions:
      - bvid 为有效的 BV 号
      - count >= 1
    Post-conditions:
      - 返回评论列表 [{"text": "...", "likes": 0, "replies": 0}]
    Side effects:
      - 启动浏览器
    """
    logger.info("bilibili_comments_fetch_start", bvid=bvid)

    def _scrape() -> list[dict[str, Any]]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(user_agent=UA, viewport=VIEWPORT)
            page = context.new_page()
            comments: list[dict[str, Any]] = []

            try:
                page.goto(f"https://www.bilibili.com/video/{bvid}", timeout=PAGE_TIMEOUT, wait_until="networkidle")
                page.wait_for_timeout(3000)

                # 滚动到评论区
                for scroll_y in [800, 1600, 2400]:
                    page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    page.wait_for_timeout(2000)

                # B站评论选择器
                comment_els = page.query_selector_all('.reply-item, [class*="reply-item"], [class*="ReplyItem"]')
                for el in comment_els:
                    try:
                        # 评论文本
                        text_el = el.query_selector('.reply-content, [class*="reply-content"], [class*="text-con"]')
                        text = text_el.inner_text().strip() if text_el else ""
                        if not text or len(text) < 2:
                            continue

                        # 点赞数
                        likes = 0
                        like_el = el.query_selector('.reply-like [class*="count"], [class*="like"] [class*="count"]')
                        if like_el:
                            like_text = like_el.inner_text().strip()
                            likes = int(re.sub(r"[^\d]", "", like_text) or "0")

                        # 回复数
                        replies = 0
                        reply_el = el.query_selector(
                            '.reply-btn [class*="count"], '
                            '[class*="sub-reply"] [class*="count"]'
                        )
                        if reply_el:
                            reply_text = reply_el.inner_text().strip()
                            replies = int(re.sub(r"[^\d]", "", reply_text) or "0")

                        comments.append({"text": text, "likes": likes, "replies": replies})
                        if len(comments) >= count:
                            break
                    except Exception:
                        continue

            except Exception as e:
                logger.warning("bilibili_comments_scrape_failed", bvid=bvid, error=str(e))
            finally:
                browser.close()
            return comments[:count]

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _scrape)
    logger.info("bilibili_comments_fetch_complete", bvid=bvid, count=len(result))
    return result


async def fetch_xiaohongshu_comments(note_url: str, count: int = 20) -> list[dict[str, Any]]:
    """通过 Playwright 抓取小红书笔记评论

    Pre-conditions:
      - note_url 为有效的小红书笔记链接
      - count >= 1
    Post-conditions:
      - 返回评论列表 [{"text": "...", "likes": 0, "replies": 0}]
    Side effects:
      - 启动浏览器
    """
    logger.info("xiaohongshu_comments_fetch_start", url=note_url)

    def _scrape() -> list[dict[str, Any]]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(user_agent=UA, viewport=VIEWPORT)
            page = context.new_page()
            comments: list[dict[str, Any]] = []

            try:
                page.goto(note_url, timeout=PAGE_TIMEOUT, wait_until="networkidle")
                page.wait_for_timeout(3000)

                # 滚动到评论区
                for scroll_y in [600, 1200, 1800]:
                    page.evaluate(f"window.scrollTo(0, {scroll_y})")
                    page.wait_for_timeout(2000)

                # 小红书评论选择器
                comment_els = page.query_selector_all(
                    '[class*="comment-item"], '
                    '[class*="CommentItem"], '
                    '[class*="commentInner"]'
                )
                for el in comment_els:
                    try:
                        # 评论文本
                        text_el = el.query_selector('[class*="content"], [class*="note-text"], [class*="comment-text"]')
                        text = text_el.inner_text().strip() if text_el else el.inner_text().strip()
                        if not text or len(text) < 2:
                            continue

                        # 点赞数
                        likes = 0
                        like_el = el.query_selector('[class*="like"] [class*="count"], [class*="like-wrapper"]')
                        if like_el:
                            like_text = like_el.inner_text().strip()
                            likes = int(re.sub(r"[^\d]", "", like_text) or "0")

                        # 回复数
                        replies = 0
                        reply_el = el.query_selector('[class*="reply"] [class*="count"], [class*="sub-comment"]')
                        if reply_el:
                            reply_text = reply_el.inner_text().strip()
                            replies = int(re.sub(r"[^\d]", "", reply_text) or "0")

                        comments.append({"text": text, "likes": likes, "replies": replies})
                        if len(comments) >= count:
                            break
                    except Exception:
                        continue

                # 备选方案：从页面文本提取
                if not comments:
                    text = page.inner_text("body")
                    skip_keywords = ["登录", "注册", "搜索", "关注", "收藏", "点赞", "小红书"]
                    for line in text.split("\n"):
                        line = line.strip()
                        if len(line) < 4 or _is_noise_line(line):
                            continue
                        if any(kw in line for kw in skip_keywords):
                            continue
                        if _has_chinese(line) or len(line) > 10:
                            comments.append({"text": line, "likes": 0, "replies": 0})
                            if len(comments) >= count:
                                break

            except Exception as e:
                logger.warning("xiaohongshu_comments_scrape_failed", url=note_url, error=str(e))
            finally:
                browser.close()
            return comments[:count]

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _scrape)
    logger.info("xiaohongshu_comments_fetch_complete", url=note_url, count=len(result))
    return result


async def fetch_comments(
    url_or_id: str,
    platform: str,
    count: int = 20,
) -> list[dict[str, Any]]:
    """统一评论抓取入口

    Pre-conditions:
      - url_or_id 非空
      - platform 为 douyin/bilibili/xiaohongshu 之一
      - count >= 1
    Post-conditions:
      - 返回评论列表 [{"text": "...", "likes": 0, "replies": 0}]
    Side effects:
      - 启动浏览器
    """
    fetchers = {
        "douyin": fetch_douyin_comments,
        "bilibili": fetch_bilibili_comments,
        "xiaohongshu": fetch_xiaohongshu_comments,
    }

    fetcher = fetchers.get(platform)
    if not fetcher:
        logger.warning("comments_fetch_unsupported_platform", platform=platform)
        return []

    try:
        return await fetcher(url_or_id, count)
    except Exception as e:
        logger.error("comments_fetch_failed", url_or_id=url_or_id, platform=platform, error=str(e))
        return []


# ─── 统一入口 ────────────────────────────────────────────────


async def fetch_account_samples(
    account_name: str,
    platform: str,
    count: int = 5,
) -> list[str]:
    """统一账号内容抓取入口

    Pre-conditions:
      - account_name 非空
      - platform 为 bilibili/douyin/xiaohongshu/wechat 之一
    Post-conditions:
      - 返回内容样本列表
    Side effects:
      - 启动浏览器
    """
    fetchers = {
        "bilibili": fetch_bilibili_samples,
        "douyin": fetch_douyin_samples,
        "xiaohongshu": fetch_xiaohongshu_samples,
        "wechat": fetch_wechat_samples,
    }

    fetcher = fetchers.get(platform)
    if not fetcher:
        return [f"[不支持的平台: {platform}]"]

    try:
        samples = await fetcher(account_name, count)
        return samples
    except Exception as e:
        logger.error("fetch_account_failed", account=account_name, platform=platform, error=str(e))
        return [f"[{platform} 账号 {account_name} 抓取失败: {str(e)[:100]}]"]
