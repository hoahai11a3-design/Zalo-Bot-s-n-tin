"""Client tối giản cho Zalo Bot API chính thức (https://bot.zaloplatforms.com)."""
import logging

import httpx

log = logging.getLogger(__name__)

MAX_TEXT = 2000  # giới hạn của sendMessage


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Cắt tin dài thành nhiều tin, ưu tiên cắt ở chỗ xuống dòng."""
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts


class ZaloBot:
    def __init__(self, token: str):
        if not token:
            raise SystemExit("Thiếu ZALO_BOT_TOKEN trong .env")
        self.base = f"https://bot-api.zaloplatforms.com/bot{token}"
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(45.0))

    async def call(self, method: str, **params) -> dict:
        r = await self.http.post(f"{self.base}/{method}", json=params)
        data = r.json()
        if not data.get("ok"):
            log.warning("Zalo %s lỗi: %s", method, data)
        return data

    async def get_me(self) -> dict:
        return await self.call("getMe")

    async def get_updates(self, timeout: int = 30) -> list[dict]:
        try:
            data = await self.call("getUpdates", timeout=str(timeout))
        except (httpx.TimeoutException, ValueError):
            return []
        result = data.get("result")
        if not result:
            return []
        return result if isinstance(result, list) else [result]

    async def send_text(self, chat_id: str, text: str) -> None:
        for part in split_text(text):
            await self.call("sendMessage", chat_id=chat_id, text=part)

    async def send_photo(self, chat_id: str, photo_url: str, caption: str = "") -> None:
        params = {"chat_id": chat_id, "photo": photo_url}
        if caption:
            params["caption"] = caption[:MAX_TEXT]
        await self.call("sendPhoto", **params)

    async def typing(self, chat_id: str) -> None:
        try:
            await self.call("sendChatAction", chat_id=chat_id, action="typing")
        except httpx.HTTPError:
            pass

    async def set_webhook(self, url: str, secret: str) -> dict:
        return await self.call("setWebhook", url=url, secret_token=secret)

    async def delete_webhook(self) -> dict:
        return await self.call("deleteWebhook")
