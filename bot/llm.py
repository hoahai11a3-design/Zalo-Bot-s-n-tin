"""Gọi các model miễn phí qua API tương thích OpenAI, tự chuyển nhà cung cấp khi lỗi / hết quota."""
import json
import logging
import re

import httpx

from .config import cfg

log = logging.getLogger(__name__)

PERSONAS = {
    "hong": (
        "Bạn là 'Hóng' – con bot chuyên hóng biến, săn sale trong nhóm Zalo. "
        "Giọng Gen Z, lầy lội, thân thiện, xưng 'tui' gọi mọi người là 'mấy bà/mấy ông' hoặc 'cả nhà', "
        "dùng emoji vừa phải, câu ngắn gọn dễ đọc trên điện thoại. "
        "Không bịa thông tin; chuyện chưa kiểm chứng thì nói rõ là 'nghe đồn'/'chưa xác thực'."
    ),
    "nghiem": (
        "Bạn là trợ lý tin tức trong nhóm Zalo. Giọng lịch sự, trung lập, súc tích như biên tập viên báo, "
        "xưng 'mình', ít emoji. Không bịa thông tin, nêu rõ khi tin chưa được xác thực."
    ),
    "hai": (
        "Bạn là bot hài hước trong nhóm Zalo, kể tin như MC tấu hài: chơi chữ, so sánh vui, "
        "nhưng vẫn giữ đúng sự thật, không xúc phạm ai. Xưng 'tui', dùng emoji thoải mái."
    ),
}


def persona_prompt(name: str) -> str:
    return PERSONAS.get(name, PERSONAS["hong"])


def _providers() -> list[tuple[str, str, str, str]]:
    """(tên, base_url, api_key, model) theo thứ tự ưu tiên."""
    out = []
    if cfg.groq_key:
        out.append(("groq", "https://api.groq.com/openai/v1", cfg.groq_key, cfg.groq_model))
    if cfg.gemini_key:
        out.append(("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                    cfg.gemini_key, cfg.gemini_model))
    if cfg.openrouter_key:
        out.append(("openrouter", "https://openrouter.ai/api/v1", cfg.openrouter_key, cfg.openrouter_model))
    if cfg.ollama_url:
        out.append(("ollama", cfg.ollama_url.rstrip("/"), "ollama", cfg.ollama_model))
    return out


def available() -> bool:
    return bool(_providers())


async def chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 1200) -> str | None:
    async with httpx.AsyncClient(timeout=60) as http:
        for name, base, key, model in _providers():
            try:
                r = await http.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "messages": messages,
                          "temperature": temperature, "max_tokens": max_tokens},
                )
                if r.status_code != 200:
                    log.warning("LLM %s trả %s: %s", name, r.status_code, r.text[:300])
                    continue
                return r.json()["choices"][0]["message"]["content"].strip()
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                log.warning("LLM %s lỗi: %s", name, e)
    return None


def parse_json(text: str | None):
    """Lấy JSON từ câu trả lời của model (kể cả khi bị bọc trong ```json ...```)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if start == -1:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        end = max(text.rfind("}"), text.rfind("]"))
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
