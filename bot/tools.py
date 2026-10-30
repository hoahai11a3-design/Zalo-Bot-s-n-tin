"""Các API miễn phí, không cần key: thời tiết, tỷ giá, coin, ngày này năm xưa."""
import logging
from datetime import datetime

import httpx

from .sources.rss import fetch_google_news

log = logging.getLogger(__name__)

WMO = {
    0: "☀️ Trời quang", 1: "🌤 Ít mây", 2: "⛅ Có mây", 3: "☁️ Nhiều mây", 45: "🌫 Sương mù", 48: "🌫 Sương mù",
    51: "🌦 Mưa phùn nhẹ", 53: "🌦 Mưa phùn", 55: "🌧 Mưa phùn dày", 61: "🌧 Mưa nhẹ", 63: "🌧 Mưa vừa",
    65: "🌧 Mưa to", 80: "🌦 Mưa rào nhẹ", 81: "🌧 Mưa rào", 82: "⛈ Mưa rào rất to",
    95: "⛈ Dông", 96: "⛈ Dông kèm mưa đá", 99: "⛈ Dông kèm mưa đá lớn",
}

COIN_ALIASES = {"btc": "bitcoin", "eth": "ethereum", "bnb": "binancecoin", "sol": "solana",
                "xrp": "ripple", "doge": "dogecoin", "ton": "the-open-network", "ada": "cardano"}


async def weather(city: str) -> str:
    city = city.strip() or "Hà Nội"
    async with httpx.AsyncClient(timeout=15) as http:
        g = (await http.get("https://geocoding-api.open-meteo.com/v1/search",
                            params={"name": city, "count": 1, "language": "vi"})).json()
        if not g.get("results"):
            return f"Tui không tìm thấy địa điểm '{city}' 😅"
        loc = g["results"][0]
        f = (await http.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": loc["latitude"], "longitude": loc["longitude"], "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "forecast_days": 3,
        })).json()
    c, d = f["current"], f["daily"]
    lines = [
        f"🌏 Thời tiết {loc['name']}" + (f", {loc.get('admin1')}" if loc.get("admin1") else ""),
        f"Bây giờ: {WMO.get(c['weather_code'], '🌡')} {c['temperature_2m']}°C "
        f"(cảm giác {c['apparent_temperature']}°C), ẩm {c['relative_humidity_2m']}%, gió {c['wind_speed_10m']} km/h",
    ]
    for i, day in enumerate(d["time"]):
        label = ["Hôm nay", "Ngày mai", "Ngày kia"][i] if i < 3 else day
        lines.append(f"• {label}: {WMO.get(d['weather_code'][i], '')} {d['temperature_2m_min'][i]}–"
                     f"{d['temperature_2m_max'][i]}°C, khả năng mưa {d['precipitation_probability_max'][i]}%")
    return "\n".join(lines)


async def exchange_rates() -> str:
    async with httpx.AsyncClient(timeout=15) as http:
        data = (await http.get("https://open.er-api.com/v6/latest/USD")).json()
    rates = data["rates"]
    vnd = rates["VND"]
    lines = ["💱 Tỷ giá tham khảo (quy ra VND):"]
    for code, flag in [("USD", "🇺🇸"), ("EUR", "🇪🇺"), ("JPY", "🇯🇵"), ("KRW", "🇰🇷"),
                       ("CNY", "🇨🇳"), ("GBP", "🇬🇧"), ("SGD", "🇸🇬"), ("THB", "🇹🇭")]:
        lines.append(f"{flag} 1 {code} = {vnd / rates[code]:,.0f} ₫".replace(",", "."))
    lines.append(f"(Nguồn open.er-api.com, cập nhật {data.get('time_last_update_utc', '')[:16]})")
    return "\n".join(lines)


async def crypto(symbols: list[str]) -> str:
    ids = [COIN_ALIASES.get(s.lower(), s.lower()) for s in symbols] or ["bitcoin", "ethereum", "binancecoin", "solana"]
    async with httpx.AsyncClient(timeout=15) as http:
        data = (await http.get("https://api.coingecko.com/api/v3/simple/price", params={
            "ids": ",".join(ids), "vs_currencies": "usd,vnd", "include_24hr_change": "true"})).json()
    if not data:
        return "Không tìm thấy đồng nào 🤔 (thử btc, eth, sol...)"
    lines = ["🪙 Giá coin:"]
    for cid, v in data.items():
        ch = v.get("usd_24h_change") or 0
        lines.append(f"{'🟢' if ch >= 0 else '🔴'} {cid}: ${v['usd']:,} ({ch:+.2f}%/24h) ≈ "
                     f"{v['vnd']:,.0f} ₫".replace(",", "."))
    return "\n".join(lines)


async def gold_news() -> str:
    items = await fetch_google_news(["giá vàng hôm nay"], kind="hot", max_age_h=24)
    if not items:
        return "Chưa có tin giá vàng mới 🥲"
    lines = ["🥇 Tin giá vàng mới nhất:"]
    for it in sorted(items, key=lambda i: -i.published)[:5]:
        lines.append(f"• {it.title} ({it.source})")
    return "\n".join(lines)


async def on_this_day(now: datetime) -> list[str]:
    """Trả về vài sự kiện 'ngày này năm xưa' (tiếng Anh, để LLM dịch/kể lại)."""
    url = f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/{now.month:02d}/{now.day:02d}"
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "HongBot/1.0 (zalo bot)"}) as http:
            data = (await http.get(url)).json()
        return [f"{e['year']}: {e['text']}" for e in data.get("selected", [])[:6]]
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning("onthisday lỗi: %s", e)
        return []
