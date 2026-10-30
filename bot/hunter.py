"""Gom tin từ mọi nguồn → lọc trùng → nhờ AI chọn & tóm tắt → soạn tin nhắn."""
import asyncio
import logging
import time
from datetime import datetime

from . import llm
from .config import cfg
from .sources.base import Item
from .sources.rss import fetch_google_news, fetch_news
from .sources.threads import fetch_threads
from .store import Store, jaccard, normalize_title

log = logging.getLogger(__name__)

_cache: dict = {"ts": 0.0, "items": []}
_lock = asyncio.Lock()


async def collect(force: bool = False) -> list[Item]:
    """Lấy tin từ tất cả nguồn, có cache để nhiều nhóm dùng chung, không spam nguồn."""
    async with _lock:
        if not force and time.time() - _cache["ts"] < cfg.source_cache_minutes * 60:
            return _cache["items"]
        results = await asyncio.gather(
            fetch_threads(), fetch_news(cfg.rss_feeds), fetch_google_news(cfg.sale_queries),
            return_exceptions=True,
        )
        items: list[Item] = []
        for name, r in zip(["threads", "news", "sale"], results):
            if isinstance(r, Exception):
                log.warning("Nguồn %s lỗi: %s", name, r)
            else:
                log.info("Nguồn %s: %d tin", name, len(r))
                items += r
        _cache.update(ts=time.time(), items=_dedupe_batch(items))
        return _cache["items"]


def _dedupe_batch(items: list[Item]) -> list[Item]:
    """Gộp các tin cùng một sự việc trong cùng một lượt lấy (ví dụ 3 báo cùng đưa 1 tin)."""
    kept: list[tuple[str, Item]] = []
    for it in sorted(items, key=lambda i: -i.score()):
        norm = normalize_title(it.title)
        if any(jaccard(norm, n) >= 0.5 for n, _ in kept):
            continue
        kept.append((norm, it))
    return [it for _, it in kept]


def _pick_candidates(store: Store, chat_id: str, items: list[Item], topics: set[str], n: int) -> list[Item]:
    fresh = [i for i in items if i.kind in topics and not store.is_duplicate(chat_id, i.url, i.title)]
    fresh.sort(key=lambda i: -i.score())
    # Cân bằng: không để toàn tin sale hoặc toàn tin hot
    hot = [i for i in fresh if i.kind == "hot"]
    sale = [i for i in fresh if i.kind == "sale"]
    picked = hot[: n * 2] + sale[: n]
    return picked[: n * 3]


SUMMARY_TASK = """Dưới đây là danh sách tin vừa săn được (đánh số). Nhiệm vụ:
1. Chọn tối đa {n} tin ĐÁNG HÓNG nhất (drama, sự kiện nóng, tin nhiều người quan tâm, deal/sale thật sự hời).
   Bỏ tin nhạt, quảng cáo lộ liễu, tin trùng ý nhau.
2. Với mỗi tin: viết tiêu đề ngắn (≤ 12 chữ) và tóm tắt sự việc 1–2 câu, đúng giọng của bạn.
   Với tin sale: nêu rõ giảm bao nhiêu, ở đâu, hạn đến khi nào (nếu có).
3. Trả về DUY NHẤT JSON dạng:
{{"items": [{{"id": <số>, "type": "hot" hoặc "sale", "title": "...", "summary": "..."}}], "intro": "<1 câu mở đầu vui>"}}

Danh sách:
{listing}"""


async def build_digest(store: Store, chat: dict, manual: bool = False, topics: set[str] | None = None) -> str | None:
    """Trả về nội dung tin nhắn, hoặc None nếu không có gì mới."""
    chat_id = chat["chat_id"]
    topics = topics or set(chat["topics"].split(","))
    items = await collect(force=manual)
    candidates = _pick_candidates(store, chat_id, items, topics, cfg.max_items)
    if not candidates:
        return None

    chosen: list[tuple[Item, str, str]] = []  # (item, title, summary)
    intro = ""
    if llm.available():
        listing = "\n".join(
            f"[{i}] ({it.kind}) {it.source}: {it.title}\n    {it.text[:300]}" for i, it in enumerate(candidates)
        )
        reply = await llm.chat([
            {"role": "system", "content": llm.persona_prompt(chat["persona"])},
            {"role": "user", "content": SUMMARY_TASK.format(n=cfg.max_items, listing=listing)},
        ], temperature=0.6)
        data = llm.parse_json(reply)
        if isinstance(data, dict):
            intro = data.get("intro", "")
            for x in data.get("items", []):
                try:
                    it = candidates[int(x["id"])]
                except (KeyError, ValueError, IndexError, TypeError):
                    continue
                chosen.append((it, x.get("title") or it.title, x.get("summary", "")))
    if not chosen:  # không có AI hoặc AI lỗi → gửi bản thô
        chosen = [(it, it.title, it.text[:200]) for it in candidates[: cfg.max_items]]

    for it, _, _ in chosen:
        store.mark_sent(chat_id, it.url, it.title)

    text = format_digest(chosen, intro, chat["interval"], manual)
    store.save_digest(chat_id, text)
    return text


def format_digest(chosen: list[tuple[Item, str, str]], intro: str, interval: int, manual: bool) -> str:
    now = datetime.now(cfg.tz)
    header = "🔥 HÓNG BIẾN NÓNG HỔI 🔥" if manual else f"⚠️ HÓNG BIẾN TRONG {interval}' QUA ⚠️"
    lines = [header]
    if intro:
        lines.append(intro)
    for n, (it, title, summary) in enumerate(chosen, 1):
        icon = "🛒" if it.kind == "sale" else "📢"
        lines += ["", f"{n}. {icon} {title.upper()}"]
        if summary:
            lines.append(f"• {summary}")
        lines.append(f"• Nguồn: {it.source}")
        if it.url:
            lines.append(f"• Link: {it.url}")
    names = cfg.bot_names[0] if cfg.bot_names else "bot"
    lines += ["", f"👉 Tag @{names} + câu hỏi để tám tiếp nha! [{now:%Y-%m-%d %H:%M}]"]
    return "\n".join(lines)
