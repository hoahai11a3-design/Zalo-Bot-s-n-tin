"""Đăng nhập Threads MỘT LẦN trên máy có màn hình, lưu cookie phiên để bot dùng.

    pip install playwright && playwright install chromium
    python -m scripts.threads_login

Cửa sổ trình duyệt sẽ mở ra → bạn tự đăng nhập (kể cả mã 2FA) → quay lại terminal bấm Enter.
Mật khẩu KHÔNG được lưu ở đâu cả; chỉ file cookie (data/threads_state.json) được lưu.
Nếu bot chạy trên server, copy file này lên server cùng đường dẫn THREADS_STATE_FILE.
Giữ file này bí mật như mật khẩu (ai có nó là vào được tài khoản).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import cfg  # noqa: E402


async def main() -> None:
    from playwright.async_api import async_playwright

    os.makedirs(os.path.dirname(cfg.threads_state_file) or ".", exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="vi-VN")
        page = await ctx.new_page()
        await page.goto("https://www.threads.com/login")
        await asyncio.to_thread(input, "Đăng nhập xong trong trình duyệt thì bấm Enter ở đây... ")
        await ctx.storage_state(path=cfg.threads_state_file)
        await browser.close()
    print(f"✅ Đã lưu phiên đăng nhập vào {cfg.threads_state_file}")


if __name__ == "__main__":
    asyncio.run(main())
