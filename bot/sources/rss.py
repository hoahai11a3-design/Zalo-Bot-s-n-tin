"""Tin từ báo điện tử (RSS) và Google News (săn sale theo từ khoá)."""
import asyncio
import calendar
import html
import logging
import re
import time
from urllib.parse import quote_plus

import feedparser
import httpx

from .base import Item, is_sale

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (compatible; HongBot/1.0)"}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


async def _fetch_feed(http: httpx.AsyncClient, url: str, kind: str, max_age_h: float) -> list[Item]:
    try:
        r = await http.get(url, headers=UA, follow_redirects=True)
        feed = feedparser.parse(r.content)
    except httpx.HTTPError as e:
        log.warning("RSS %s lỗi: %s", url, e)
        return []
    name = _clean(feed.feed.get("title", "")) or url.split("/")[2]
    items = []
    for e in feed.entries[:30]:
        t = e.get("published_parsed") or e.get("updated_parsed")
        published = calendar.timegm(t) if t else time.time()
        if time.time() - published > max_age_h * 3600:
            continue
        title = _clean(e.get("title", ""))
        source = name
        # Google News thêm " - Tên báo" vào cuối tiêu đề
        if "news.google.com" in url and " - " in title:
            title, source = title.rsplit(" - ", 1)
        summary = _clean(e.get("summary", ""))
        if summary.startswith(title[:40]):  # Google News: phần mô tả chỉ lặp lại tiêu đề
            summary = ""
        if kind == "sale" and not is_sale(f"{title} {summary}"):
            continue  # kết quả tìm "sale" nhưng thực ra không phải tin khuyến mãi
        items.append(Item(title=title, url=e.get("link", ""), source=source,
                          text=summary[:500], kind=kind, published=published))
    return items


async def fetch_news(feeds: list[str], max_age_h: float = 6) -> list[Item]:
    async with httpx.AsyncClient(timeout=20) as http:
        results = await asyncio.gather(*(_fetch_feed(http, f, "hot", max_age_h) for f in feeds))
    return [i for r in results for i in r]


def google_news_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query + ' when:1d')}&hl=vi&gl=VN&ceid=VN:vi"


async def fetch_google_news(queries: list[str], kind: str = "sale", max_age_h: float = 24) -> list[Item]:
    async with httpx.AsyncClient(timeout=20) as http:
        results = await asyncio.gather(
            *(_fetch_feed(http, google_news_url(q), kind, max_age_h) for q in queries))
    return [i for r in results for i in r]
