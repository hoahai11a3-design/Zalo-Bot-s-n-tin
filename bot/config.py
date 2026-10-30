"""Đọc cấu hình từ biến môi trường / file .env."""
import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


DEFAULT_RSS = ",".join([
    "https://vnexpress.net/rss/tin-xem-nhieu.rss",
    "https://kenh14.vn/rss/home.rss",
    "https://genk.vn/rss/home.rss",
    "https://thanhnien.vn/rss/home.rss",
    "https://dantri.com.vn/rss/home.rss",
])

# Google News RSS theo từ khoá: săn sale / khuyến mãi
DEFAULT_SALE_QUERIES = "flash sale,mã giảm giá,khuyến mãi khủng,sale 11.11,giảm giá sốc"


@dataclass
class Config:
    zalo_token: str = os.getenv("ZALO_BOT_TOKEN", "")
    mode: str = os.getenv("ZALO_MODE", "polling")  # polling | webhook
    webhook_url: str = os.getenv("WEBHOOK_URL", "")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
    port: int = _int("PORT", 8080)

    # Tên dùng để gọi bot khi tag trong nhóm, ví dụ "@Hóng"
    bot_names: list[str] = field(default_factory=lambda: _list("BOT_NAMES", "Hóng,Hong,bot"))
    admin_ids: list[str] = field(default_factory=lambda: _list("ADMIN_IDS"))
    broadcast_chat_ids: list[str] = field(default_factory=lambda: _list("BROADCAST_CHAT_IDS"))

    interval_minutes: int = _int("POST_INTERVAL_MINUTES", 15)
    max_items: int = _int("MAX_ITEMS_PER_POST", 5)
    quiet_hours: str = os.getenv("QUIET_HOURS", "0-6")  # không gửi tự động trong khung giờ này
    tz: ZoneInfo = ZoneInfo(os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh"))
    default_persona: str = os.getenv("PERSONA", "hong")
    dedup_days: int = _int("DEDUP_DAYS", 3)
    db_path: str = os.getenv("DB_PATH", "data/bot.db")

    # Nguồn tin
    rss_feeds: list[str] = field(default_factory=lambda: _list("RSS_FEEDS", DEFAULT_RSS))
    sale_queries: list[str] = field(default_factory=lambda: _list("SALE_QUERIES", DEFAULT_SALE_QUERIES))
    threads_keywords: list[str] = field(default_factory=lambda: _list("THREADS_KEYWORDS", "drama,biến căng,sale,giảm giá"))
    threads_accounts: list[str] = field(default_factory=lambda: _list("THREADS_ACCOUNTS"))
    threads_access_token: str = os.getenv("THREADS_ACCESS_TOKEN", "")
    threads_state_file: str = os.getenv("THREADS_STATE_FILE", "data/threads_state.json")
    source_cache_minutes: int = _int("SOURCE_CACHE_MINUTES", 10)

    # LLM miễn phí (API tương thích OpenAI) – thử lần lượt, cái nào lỗi thì nhảy sang cái sau
    groq_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    gemini_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    openrouter_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    ollama_url: str = os.getenv("OLLAMA_URL", "")  # ví dụ http://localhost:11434/v1
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


cfg = Config()
