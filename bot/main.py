"""Điểm khởi chạy: python -m bot.main"""
import asyncio
import logging
import time
from datetime import datetime

from . import hunter
from .commands import Handler
from .config import cfg
from .store import Store
from .zalo import ZaloBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


def in_quiet_hours(now: datetime) -> bool:
    try:
        start, end = (int(x) for x in cfg.quiet_hours.split("-"))
    except ValueError:
        return False
    h = now.hour
    return start <= h < end if start <= end else (h >= start or h < end)


async def scheduler(bot: ZaloBot, store: Store) -> None:
    """Mỗi 30 giây kiểm tra nhóm nào đến giờ nhận bản tin."""
    while True:
        try:
            now = datetime.now(cfg.tz)
            if not in_quiet_hours(now):
                for chat in store.subscribed_chats():
                    if time.time() - chat["last_sent"] < chat["interval"] * 60:
                        continue
                    store.set_chat(chat["chat_id"], last_sent=time.time())
                    text = await hunter.build_digest(store, chat)
                    if text:  # không có gì mới thì im lặng, không spam
                        await bot.send_text(chat["chat_id"], text)
                        log.info("Đã gửi bản tin cho %s", chat["chat_id"])
            if now.minute == 0 and now.hour == 3:
                store.cleanup()
        except Exception:
            log.exception("Lỗi scheduler")
        await asyncio.sleep(30)


async def polling(bot: ZaloBot, handler: Handler) -> None:
    await bot.delete_webhook()
    log.info("Đang chạy chế độ polling...")
    while True:
        try:
            for update in await bot.get_updates(timeout=30):
                asyncio.create_task(_safe(handler.handle_update(update)))
        except Exception:
            log.exception("Lỗi polling")
            await asyncio.sleep(5)


async def _safe(coro) -> None:
    try:
        await coro
    except Exception:
        log.exception("Lỗi xử lý tin nhắn")


async def webhook(bot: ZaloBot, handler: Handler) -> None:
    from aiohttp import web

    async def receive(request: web.Request):
        if request.headers.get("X-Bot-Api-Secret-Token") != cfg.webhook_secret:
            return web.Response(status=403)
        body = await request.json()
        update = body.get("result", body)
        asyncio.create_task(_safe(handler.handle_update(update)))
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_post("/webhook", receive)
    app.router.add_get("/", lambda _: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", cfg.port).start()
    log.info("Webhook lắng nghe cổng %s; đăng ký: %s", cfg.port,
             await bot.set_webhook(f"{cfg.webhook_url.rstrip('/')}/webhook", cfg.webhook_secret))
    await asyncio.Event().wait()


async def main() -> None:
    bot = ZaloBot(cfg.zalo_token)
    me = await bot.get_me()
    log.info("Bot: %s", me.get("result"))
    store = Store()
    handler = Handler(bot, store)
    receiver = webhook if cfg.mode == "webhook" else polling
    await asyncio.gather(scheduler(bot, store), receiver(bot, handler))


if __name__ == "__main__":
    asyncio.run(main())
