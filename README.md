# 🔥 Hóng Bot – bot Zalo săn tin hot & deal giảm giá

Bot cho **Zalo** (dùng Zalo Bot API chính thức) cứ 15 phút lại đi hóng tin trên **Threads**, báo điện tử và Google News,
nhờ **AI miễn phí** chọn những tin đáng hóng nhất, tóm tắt bằng giọng Gen Z rồi gửi vào nhóm, để cả nhóm không bị "tối cổ".

```
⚠️ HÓNG BIẾN TRONG 15' QUA ⚠️
Ủa alo cả nhà, có biến nè 👀

1. 📢 QUÁN TRÀ SỮA X BỊ TỐ ...
• Tóm tắt 1–2 câu bằng giọng của bot
• Nguồn: Threads @hongbien
• Link: https://www.threads.com/@hongbien/post/...

2. 🛒 FLASH SALE 11.11 GIẢM ĐẾN 50%
• Giảm bao nhiêu, ở đâu, hạn đến khi nào
...
👉 Tag @Hóng + câu hỏi để tám tiếp nha! [2026-10-30 06:40]
```

## Tính năng

| Yêu cầu | Cách làm |
|---|---|
| Tần suất gửi | Mặc định 15 phút, đổi bằng `/tansuat 30`. Không gửi trong giờ ngủ (`QUIET_HOURS=0-6`). Không có tin mới thì **im lặng**, không spam |
| Giọng văn | 3 giọng: `hong` (Gen Z hóng biến), `nghiem` (biên tập viên), `hai` (tấu hài) – đổi bằng `/giongvan` |
| Không trùng lặp | Lưu tin đã gửi trong SQLite: trùng link **hoặc** tiêu đề na ná (so khớp từ khoá, bỏ dấu) trong 3 ngày → bỏ qua. Nhiều báo cùng đưa 1 sự việc → gộp còn 1 |
| Gọi bằng tag | Trong nhóm, bot chỉ trả lời khi bị tag `@Hóng ...` hoặc gõ lệnh `/...`. Chat riêng thì nói gì cũng trả lời |
| Trò chuyện | Nhớ 12 câu gần nhất của mỗi nhóm, biết bản tin vừa gửi → hỏi được "kể kỹ tin số 2 đi" |
| Model miễn phí | Groq / Gemini / OpenRouter (`:free`) / Ollama chạy trên máy – điền key nào dùng key đó, lỗi hoặc hết quota tự nhảy sang cái kế |
| API vui khác | Thời tiết (Open-Meteo), tỷ giá, giá coin (CoinGecko), tin giá vàng, ngày này năm xưa (Wikipedia), xem bói vui |

### Lệnh

```
/tin              hóng biến ngay           /thoitiet Hà Nội   thời tiết 3 ngày
/sale             săn deal ngay            /tygia             tỷ giá ngoại tệ
/dangky  /huy     bật/tắt tự gửi           /coin btc eth      giá tiền ảo
/tansuat 15       đổi tần suất (phút)      /vang              tin giá vàng
/chude hot,sale   chọn chủ đề              /homnay            ngày này năm xưa
/giongvan hai     đổi giọng văn            /boi               xem bói vui
/quen             xoá trí nhớ trò chuyện   /id                xem ID chat
```

## Cài đặt

Cần Python 3.11 trở lên.

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Mở `.env` và điền:

1. **`ZALO_BOT_TOKEN`**: tạo bot theo hướng dẫn tại https://bot.zaloplatforms.com/docs.
2. **Ít nhất 1 key AI miễn phí**, ví dụ `GEMINI_API_KEY` (https://aistudio.google.com/apikey) hoặc `GROQ_API_KEY` (https://console.groq.com/keys).
   Không có key thì bot vẫn chạy, chỉ gửi tiêu đề thô và không tám được.

Chạy bot:

```bash
python -m bot.main
```

Thêm bot vào nhóm rồi gõ `/dangky`. Từ đó cứ 15 phút bot sẽ gửi bản tin một lần.

## Lấy tin từ Threads

Threads muốn xem kết quả tìm kiếm thì phải đăng nhập. Có 2 cách:

**Cách A: đăng nhập bằng tài khoản của bạn (dễ nhất).** **Đừng** gửi mật khẩu cho ai, kể cả ghi vào `.env`.
Chạy script dưới đây trên máy có màn hình, cửa sổ trình duyệt mở ra thì bạn tự đăng nhập (kể cả mã 2FA):

```bash
pip install playwright
```

```bash
playwright install chromium
```

```bash
python -m scripts.threads_login
```

Script chỉ lưu cookie phiên vào `data/threads_state.json`. Nếu bot chạy trên server thì copy file đó lên server.
File này quan trọng như mật khẩu, đừng chia sẻ. Nên dùng một **tài khoản phụ** cho bot.

Tuỳ chỉnh nội dung cần hóng trong `.env`:
- `THREADS_KEYWORDS=drama,biến căng,sale,giảm giá`: tìm theo từ khoá.
- `THREADS_ACCOUNTS=theanh28,...`: theo dõi các trang chuyên đăng biến/deal.

**Cách B: API chính thức của Meta.** Điền `THREADS_ACCESS_TOKEN` (app phải được duyệt quyền `threads_keyword_search`).
Cách này ổn định hơn nhưng thủ tục duyệt app khá lâu.

> ⚠️ Cách A là đọc giao diện web. Threads mà đổi giao diện thì có thể phải sửa lại `bot/sources/threads.py`.
> Nên để tần suất ≥ 15 phút để tài khoản không bị nghi là bot.
> Threads lỗi thì bot vẫn chạy bình thường với các nguồn báo và Google News.

## Chạy 24/7

Chạy trên VPS, Raspberry Pi hoặc máy luôn bật, ví dụ bằng `tmux`/`screen` hoặc systemd:

```ini
# /etc/systemd/system/hongbot.service
[Unit]
Description=Hong Zalo Bot
After=network-online.target

[Service]
WorkingDirectory=/opt/hongbot
ExecStart=/usr/bin/python3 -m bot.main
Restart=always

[Install]
WantedBy=multi-user.target
```

Có domain HTTPS thì có thể chuyển sang webhook (`ZALO_MODE=webhook`, `WEBHOOK_URL=https://...`). Nếu không, cứ dùng polling.

## Cấu trúc

```
bot/
  main.py        vòng lặp nhận tin + bộ hẹn giờ gửi bản tin
  commands.py    xử lý lệnh /..., tag @bot, trò chuyện
  hunter.py      gom tin → lọc trùng → AI chọn & tóm tắt → soạn tin
  llm.py         gọi model miễn phí (Groq/Gemini/OpenRouter/Ollama) + 3 giọng văn
  store.py       SQLite: cài đặt nhóm, tin đã gửi, lịch sử chat
  tools.py       thời tiết, tỷ giá, coin, giá vàng, ngày này năm xưa
  zalo.py        client Zalo Bot API
  sources/       threads.py, rss.py (báo + Google News săn sale)
scripts/threads_login.py   đăng nhập Threads 1 lần, lưu cookie
```

Thêm nguồn mới: viết một hàm `async def fetch_xxx() -> list[Item]` trong `bot/sources/`, rồi thêm nó vào `collect()` trong `hunter.py`.
