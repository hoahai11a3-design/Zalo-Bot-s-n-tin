"""Xử lý tin nhắn: lệnh /..., và trò chuyện khi được tag."""
import logging
import re
from datetime import datetime

from . import hunter, llm, tools
from .config import cfg
from .store import Store, strip_accents
from .zalo import ZaloBot

log = logging.getLogger(__name__)

HELP = """🤖 Tui là {name} – bot hóng biến & săn sale!

📰 Tin tức
/tin – hóng biến nóng ngay bây giờ
/sale – săn deal, mã giảm giá
/dangky – bật tự động gửi tin cho nhóm này
/huy – tắt tự động gửi
/tansuat 15 – đổi tần suất gửi (phút)
/chude hot,sale – chọn chủ đề (hot / sale)
/giongvan hong|nghiem|hai – đổi giọng văn

🧰 Tiện ích
/thoitiet Hà Nội – dự báo thời tiết
/tygia – tỷ giá ngoại tệ
/coin btc eth – giá tiền ảo
/vang – tin giá vàng
/homnay – ngày này năm xưa
/boi – xem bói vui đầu ngày
/quen – xoá trí nhớ cuộc trò chuyện
/id – xem ID nhóm/chat

💬 Muốn tám thì tag @{name} + câu hỏi (vd: "@{name} kể kỹ tin số 2 đi")."""


def _norm(s: str) -> str:
    return strip_accents(s).lower()


def extract_mention(text: str) -> str | None:
    """Trả về phần nội dung sau khi bỏ phần tag bot; None nếu tin không gọi bot."""
    t = _norm(text)
    for name in cfg.bot_names:
        n = _norm(name)
        m = re.search(rf"@{re.escape(n)}\b", t)
        if m:
            return (text[:m.start()] + text[m.end():]).strip(" ,:")
    return None


class Handler:
    def __init__(self, bot: ZaloBot, store: Store):
        self.bot = bot
        self.store = store
        self.name = cfg.bot_names[0] if cfg.bot_names else "bot"

    async def handle_update(self, update: dict) -> None:
        msg = update.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        if not text or not chat_id or (msg.get("from") or {}).get("is_bot"):
            return
        is_private = str(chat.get("chat_type", "")).upper() == "PRIVATE"
        user = msg.get("from") or {}

        if text.startswith(("/", "!")):
            await self.command(chat_id, user, text[1:])
            return
        content = extract_mention(text)
        if content is None and not is_private:
            return  # trong nhóm: chỉ trả lời khi được tag
        await self.converse(chat_id, user, content if content is not None else text)

    async def command(self, chat_id: str, user: dict, raw: str) -> None:
        cmd, _, arg = raw.partition(" ")
        cmd, arg = _norm(cmd.split("@")[0]), arg.strip()
        chat = self.store.get_chat(chat_id)
        reply = None
        try:
            if cmd in ("help", "start", "menu", "huongdan"):
                reply = HELP.format(name=self.name)
            elif cmd in ("tin", "hot", "bien"):
                await self.bot.typing(chat_id)
                reply = await hunter.build_digest(self.store, chat, manual=True, topics={"hot"}) \
                    or "Tạm thời chưa có biến gì mới, cả nhà nghỉ ngơi xíu nha 😴"
            elif cmd in ("sale", "deal", "giamgia"):
                await self.bot.typing(chat_id)
                reply = await hunter.build_digest(self.store, chat, manual=True, topics={"sale"}) \
                    or "Chưa săn được deal nào mới, lát tui quay lại nha 🛒"
            elif cmd in ("dangky", "batdau", "on"):
                if self._allowed(user):
                    self.store.set_chat(chat_id, subscribed=1, last_sent=0)
                    reply = f"✅ Đã bật! Cứ {chat['interval']} phút tui sẽ báo biến 1 lần (trừ giờ ngủ {cfg.quiet_hours}h)."
            elif cmd in ("huy", "tat", "off"):
                if self._allowed(user):
                    self.store.set_chat(chat_id, subscribed=0)
                    reply = "🔕 Đã tắt tự động gửi. Gõ /dangky để bật lại."
            elif cmd in ("tansuat", "interval"):
                if self._allowed(user):
                    if arg.isdigit() and 5 <= int(arg) <= 1440:
                        self.store.set_chat(chat_id, interval=int(arg))
                        reply = f"⏱ Ok, từ giờ {arg} phút gửi 1 lần."
                    else:
                        reply = "Gõ kiểu: /tansuat 15 (từ 5 đến 1440 phút)"
            elif cmd in ("giongvan", "persona"):
                if arg in llm.PERSONAS:
                    self.store.set_chat(chat_id, persona=arg)
                    reply = {"hong": "Okiii, tui quay lại làm bà tám Gen Z nha 💅",
                             "nghiem": "Đã chuyển sang giọng nghiêm túc.",
                             "hai": "Chế độ tấu hài đã bật 🤡🎤"}[arg]
                else:
                    reply = "Chọn 1 trong: /giongvan hong | nghiem | hai"
            elif cmd in ("chude", "topic"):
                topics = {t.strip() for t in _norm(arg).split(",")} & {"hot", "sale"}
                if topics:
                    self.store.set_chat(chat_id, topics=",".join(sorted(topics)))
                    reply = f"📌 Chủ đề: {', '.join(sorted(topics))}"
                else:
                    reply = "Gõ kiểu: /chude hot,sale (hoặc chỉ hot / chỉ sale)"
            elif cmd in ("thoitiet", "weather"):
                reply = await tools.weather(arg)
            elif cmd in ("tygia", "fx"):
                reply = await tools.exchange_rates()
            elif cmd in ("coin", "crypto"):
                reply = await tools.crypto(arg.split())
            elif cmd in ("vang", "gold"):
                reply = await tools.gold_news()
            elif cmd in ("homnay", "today"):
                reply = await self.today(chat)
            elif cmd in ("boi", "tarot"):
                reply = await self.fortune(chat, user)
            elif cmd in ("quen", "reset"):
                self.store.clear_history(chat_id)
                reply = "🧹 Tui quên sạch rồi, mình làm lại từ đầu nha!"
            elif cmd == "id":
                reply = f"🆔 Chat ID: {chat_id}\n👤 User ID: {user.get('id')}"
            else:
                reply = f"Lệnh lạ quá 🤔 Gõ /help để xem tui làm được gì."
        except Exception as e:  # lỗi API bên ngoài không được làm sập bot
            log.exception("Lệnh %s lỗi", cmd)
            reply = f"Ối, tui bị lỗi rồi 😵 ({type(e).__name__}). Thử lại sau nha."
        if reply is None:
            reply = "⛔ Chỉ admin mới dùng được lệnh này."
        await self.bot.send_text(chat_id, reply)

    def _allowed(self, user: dict) -> bool:
        return not cfg.admin_ids or str(user.get("id")) in cfg.admin_ids

    async def converse(self, chat_id: str, user: dict, text: str) -> None:
        if not llm.available():
            await self.bot.send_text(chat_id, "Chưa cấu hình model AI nên tui chưa tám được 🥲 (xem README).")
            return
        await self.bot.typing(chat_id)
        chat = self.store.get_chat(chat_id)
        now = datetime.now(cfg.tz)
        system = (
            f"{llm.persona_prompt(chat['persona'])}\n"
            f"Bây giờ là {now:%H:%M ngày %d/%m/%Y}. Trả lời ngắn gọn (≤ 150 chữ trừ khi được yêu cầu), "
            "không dùng markdown phức tạp vì Zalo hiển thị chữ thường.\n"
        )
        digest = self.store.last_digest(chat_id)
        if digest:
            system += f"\nBản tin gần nhất bạn đã gửi vào nhóm (dùng khi được hỏi về 'tin số X'):\n{digest}\n"
        speaker = user.get("display_name") or "ai đó"
        messages = [{"role": "system", "content": system}, *self.store.get_history(chat_id)]
        messages.append({"role": "user", "content": f"{speaker}: {text}"})
        reply = await llm.chat(messages) or "Não tui đang lag xíu, hỏi lại sau nha 😵‍💫"
        self.store.add_history(chat_id, "user", f"{speaker}: {text}")
        self.store.add_history(chat_id, "assistant", reply)
        await self.bot.send_text(chat_id, reply)

    async def today(self, chat: dict) -> str:
        now = datetime.now(cfg.tz)
        events = await tools.on_this_day(now)
        if not events:
            return f"📅 Hôm nay {now:%d/%m/%Y}. Tui chưa lấy được 'ngày này năm xưa', thử lại sau nha."
        if not llm.available():
            return f"📅 Ngày này năm xưa ({now:%d/%m}):\n" + "\n".join(f"• {e}" for e in events)
        reply = await llm.chat([
            {"role": "system", "content": llm.persona_prompt(chat["persona"])},
            {"role": "user", "content": f"Hôm nay {now:%d/%m/%Y}. Kể lại ngắn gọn bằng tiếng Việt 3-4 sự kiện "
                                        f"thú vị nhất 'ngày này năm xưa' dưới đây, mỗi ý 1 dòng bắt đầu bằng năm, "
                                        f"mở đầu bằng '📅 Ngày này năm xưa':\n" + "\n".join(events)},
        ])
        return reply or "\n".join(events)

    async def fortune(self, chat: dict, user: dict) -> str:
        if not llm.available():
            return "🔮 Quẻ hôm nay: Đại cát! (bật AI để xem bói xịn hơn nha)"
        now = datetime.now(cfg.tz)
        reply = await llm.chat([
            {"role": "system", "content": llm.persona_prompt(chat["persona"])},
            {"role": "user", "content": f"Xem bói vui (chỉ để giải trí) cho '{user.get('display_name', 'bạn')}' "
                                        f"ngày {now:%d/%m/%Y}: công việc, tình duyên, tài lộc, con số may mắn, "
                                        "màu may mắn. Ngắn gọn, hài hước, mở đầu bằng 🔮."},
        ], temperature=1.0)
        return reply or "🔮 Quẻ bị nhiễu sóng, thử lại sau nha!"
