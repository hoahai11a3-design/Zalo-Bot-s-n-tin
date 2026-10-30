"""Lưu trạng thái bằng SQLite: cài đặt từng nhóm, tin đã gửi (chống trùng), lịch sử trò chuyện."""
import hashlib
import os
import re
import sqlite3
import time
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from .config import cfg

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id TEXT PRIMARY KEY,
    subscribed INTEGER DEFAULT 0,
    interval INTEGER,
    persona TEXT,
    topics TEXT DEFAULT 'hot,sale',
    last_sent REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sent (
    chat_id TEXT, fp TEXT, title_norm TEXT, ts REAL,
    PRIMARY KEY (chat_id, fp)
);
CREATE TABLE IF NOT EXISTS history (
    chat_id TEXT, role TEXT, content TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS digests (
    chat_id TEXT PRIMARY KEY, content TEXT, ts REAL
);
"""

STOPWORDS = set("""
va la cua cho voi nhung cac mot nay do thi da dang se bi duoc khi tai trong tren ve ra vao
co khong nhu de tu den sau truoc hon rat lai con the nao gi ai
""".split())


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def normalize_title(title: str) -> str:
    s = strip_accents(title.lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(w for w in s.split() if w not in STOPWORDS and len(w) > 1)


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme, p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), "", ""))


def fingerprint(url: str, title: str) -> str:
    key = normalize_url(url) if url else normalize_title(title)
    return hashlib.sha1(key.encode()).hexdigest()


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class Store:
    def __init__(self, path: str = cfg.db_path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for chat_id in cfg.broadcast_chat_ids:
            self.ensure_chat(chat_id)
            self.set_chat(chat_id, subscribed=1)

    # ---- cài đặt từng chat ----
    def ensure_chat(self, chat_id: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (chat_id,))
        self.db.commit()

    def get_chat(self, chat_id: str) -> dict:
        self.ensure_chat(chat_id)
        row = dict(self.db.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,)).fetchone())
        row["interval"] = row["interval"] or cfg.interval_minutes
        row["persona"] = row["persona"] or cfg.default_persona
        return row

    def set_chat(self, chat_id: str, **fields) -> None:
        self.ensure_chat(chat_id)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE chats SET {cols} WHERE chat_id=?", (*fields.values(), chat_id))
        self.db.commit()

    def subscribed_chats(self) -> list[dict]:
        ids = [r["chat_id"] for r in self.db.execute("SELECT chat_id FROM chats WHERE subscribed=1")]
        return [self.get_chat(i) for i in ids]

    # ---- chống trùng lặp ----
    def is_duplicate(self, chat_id: str, url: str, title: str, threshold: float = 0.6) -> bool:
        """Trùng nếu cùng link, hoặc tiêu đề gần giống một tin đã gửi trong DEDUP_DAYS ngày."""
        since = time.time() - cfg.dedup_days * 86400
        fp = fingerprint(url, title)
        if self.db.execute("SELECT 1 FROM sent WHERE chat_id=? AND fp=?", (chat_id, fp)).fetchone():
            return True
        norm = normalize_title(title)
        for r in self.db.execute("SELECT title_norm FROM sent WHERE chat_id=? AND ts>?", (chat_id, since)):
            if jaccard(norm, r["title_norm"]) >= threshold:
                return True
        return False

    def mark_sent(self, chat_id: str, url: str, title: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO sent VALUES (?,?,?,?)",
            (chat_id, fingerprint(url, title), normalize_title(title), time.time()),
        )
        self.db.commit()

    def cleanup(self) -> None:
        cutoff = time.time() - max(cfg.dedup_days, 7) * 86400
        self.db.execute("DELETE FROM sent WHERE ts<?", (cutoff,))
        self.db.execute("DELETE FROM history WHERE ts<?", (cutoff,))
        self.db.commit()

    # ---- lịch sử trò chuyện ----
    def add_history(self, chat_id: str, role: str, content: str) -> None:
        self.db.execute("INSERT INTO history VALUES (?,?,?,?)", (chat_id, role, content, time.time()))
        self.db.commit()

    def get_history(self, chat_id: str, limit: int = 12) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM history WHERE chat_id=? ORDER BY ts DESC LIMIT ?", (chat_id, limit)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_history(self, chat_id: str) -> None:
        self.db.execute("DELETE FROM history WHERE chat_id=?", (chat_id,))
        self.db.commit()

    def save_digest(self, chat_id: str, content: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO digests VALUES (?,?,?)", (chat_id, content, time.time()))
        self.db.commit()

    def last_digest(self, chat_id: str) -> str:
        r = self.db.execute("SELECT content FROM digests WHERE chat_id=?", (chat_id,)).fetchone()
        return r["content"] if r else ""
