"""Lấy bài hot trên Threads.

Hai cách (dùng được cách nào thì dùng cách đó):
1. API chính thức của Meta (THREADS_ACCESS_TOKEN, cần quyền threads_keyword_search) – ổn định nhất.
2. Trình duyệt Playwright dùng phiên đăng nhập đã lưu (THREADS_STATE_FILE, tạo bằng
   `python -m scripts.threads_login`). Bot KHÔNG lưu mật khẩu, chỉ lưu cookie phiên.
"""
import json
import logging
import os
import time
from datetime import datetime
from urllib.parse import quote

import httpx

from ..config import cfg
from .base import Item

log = logging.getLogger(__name__)
THREADS_WEB = "https://www.threads.com"


# ---------- Cách 1: API chính thức ----------
async def _official_search(keywords: list[str]) -> list[Item]:
    items = []
    async with httpx.AsyncClient(timeout=20) as http:
        for kw in keywords:
            try:
                r = await http.get("https://graph.threads.net/v1.0/keyword_search", params={
                    "q": kw, "search_type": "TOP",
                    "fields": "id,text,permalink,timestamp,username",
                    "access_token": cfg.threads_access_token,
                })
                data = r.json().get("data", [])
            except (httpx.HTTPError, ValueError) as e:
                log.warning("Threads API '%s' lỗi: %s", kw, e)
                continue
            for p in data:
                text = p.get("text") or ""
                if not text:
                    continue
                try:
                    published = datetime.strptime(p["timestamp"], "%Y-%m-%dT%H:%M:%S%z").timestamp()
                except (KeyError, ValueError):
                    published = time.time()
                items.append(Item(title=text[:120], text=text[:800], url=p.get("permalink", ""),
                                  source=f"Threads @{p.get('username', '?')}", published=published))
    return items


# ---------- Cách 2: Playwright + phiên đăng nhập ----------
def _walk_posts(node, out: dict):
    """Duyệt đệ quy JSON của Threads, nhặt mọi object trông giống một bài đăng."""
    if isinstance(node, dict):
        if "code" in node and "taken_at" in node and isinstance(node.get("user"), dict):
            out[node["code"]] = node
        for v in node.values():
            _walk_posts(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_posts(v, out)


def _post_to_item(p: dict) -> Item | None:
    text = ((p.get("caption") or {}).get("text") or "").strip()
    if not text:
        return None
    user = p["user"].get("username", "?")
    info = p.get("text_post_app_info") or {}
    engagement = (p.get("like_count") or 0) + 3 * (info.get("direct_reply_count") or 0) \
        + 5 * (info.get("repost_count") or 0)
    return Item(title=text[:120], text=text[:800], url=f"{THREADS_WEB}/@{user}/post/{p['code']}",
                source=f"Threads @{user}", published=float(p.get("taken_at") or time.time()),
                engagement=int(engagement))


async def _browser_scrape(keywords: list[str], accounts: list[str]) -> list[Item]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("Chưa cài playwright – bỏ qua Threads (pip install playwright && playwright install chromium)")
        return []

    urls = [f"{THREADS_WEB}/search?q={quote(k)}&serp_type=default" for k in keywords]
    urls += [f"{THREADS_WEB}/@{a.lstrip('@')}" for a in accounts]
    posts: dict = {}

    async def on_response(resp):
        if "graphql" in resp.url or "/api/" in resp.url:
            try:
                _walk_posts(await resp.json(), posts)
            except Exception:
                pass

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            storage_state=cfg.threads_state_file if os.path.exists(cfg.threads_state_file) else None,
            locale="vi-VN",
        )
        page = await ctx.new_page()
        page.on("response", on_response)
        for url in urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                await page.mouse.wheel(0, 4000)  # cuộn để tải thêm bài
                await page.wait_for_timeout(2500)
                # Dữ liệu trang đầu nằm sẵn trong các thẻ <script type="application/json">
                for raw in await page.locator('script[type="application/json"]').all_text_contents():
                    if '"taken_at"' in raw:
                        try:
                            _walk_posts(json.loads(raw), posts)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                log.warning("Threads %s lỗi: %s", url, e)
        # Lưu lại cookie mới (giữ phiên đăng nhập sống lâu hơn)
        if os.path.exists(cfg.threads_state_file):
            await ctx.storage_state(path=cfg.threads_state_file)
        await browser.close()

    items = [i for i in (_post_to_item(p) for p in posts.values()) if i]
    log.info("Threads: lấy được %d bài", len(items))
    return items


async def fetch_threads(max_age_h: float = 12) -> list[Item]:
    keywords, accounts = cfg.threads_keywords, cfg.threads_accounts
    if cfg.threads_access_token:
        items = await _official_search(keywords)
        if accounts:
            items += await _browser_scrape([], accounts)
    elif os.path.exists(cfg.threads_state_file) or accounts:
        items = await _browser_scrape(keywords if os.path.exists(cfg.threads_state_file) else [], accounts)
    else:
        return []
    cutoff = time.time() - max_age_h * 3600
    return [i for i in items if i.published >= cutoff]
