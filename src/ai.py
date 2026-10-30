"""Phần AI: Claude Haiku viết nhận định, Claude Sonnet kiểm chứng.

Nguyên tắc:
- AI KHÔNG tính số. Mọi con số đưa vào prompt đều do code tính sẵn.
- AI chỉ mô tả, KHÔNG khuyến nghị mua/bán/nắm giữ (quy định UBCKNN).
- Mỗi nhận định được Sonnet đối chiếu lại với chính số liệu đầu vào:
  khớp -> "ok", không đối chiếu được / sai -> "warn".
Không có ANTHROPIC_API_KEY -> trả văn bản giữ chỗ, hệ thống vẫn chạy.
"""
from __future__ import annotations

import json
import os
import re

WRITER = os.getenv("WRITER_MODEL", "claude-haiku-5-5")
CHECKER = os.getenv("CHECKER_MODEL", "claude-sonnet-5-5")

RULES = (
    "Bạn là biên tập viên dữ liệu chứng khoán Việt Nam. Viết tiếng Việt, ngắn gọn, dễ hiểu cho nhà đầu tư mới.\n"
    "QUY TẮC BẮT BUỘC:\n"
    "1. Chỉ dùng số liệu và tin được cung cấp. Không tự thêm con số, không bịa sự kiện.\n"
    "2. Không khuyến nghị mua, bán, nắm giữ; không dùng các từ 'nên mua', 'nên bán', 'điểm mua', 'mục tiêu giá'.\n"
    "3. Chỉ mô tả trạng thái và xu hướng; nói rõ khi dữ liệu chưa đủ.\n"
    "4. Mỗi ý trích nguồn trong ngoặc vuông nếu dựa trên tin, ví dụ [CafeF]."
)

_client = None


def enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _ask(model: str, prompt: str, max_tokens: int = 700) -> str:
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    msg = _client.messages.create(model=model, max_tokens=max_tokens, system=RULES,
                                  messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def _json(text: str):
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    return json.loads(m.group(0)) if m else None


def _news_block(items: list[dict], n: int = 6) -> str:
    return "\n".join(f"- [{i['source']}] {i['title']}: {i['summary'][:200]}" for i in items[:n]) or "(không có tin)"


def stock_view(tk: str, facts: dict, news: list[dict]) -> dict:
    """Nhận định 4 khung thời gian cho 1 mã. Trả dict các đoạn văn + xu hướng."""
    if not enabled():
        return {k: {"trend": "Trung tính", "text": "[Chưa bật AI] Thêm ANTHROPIC_API_KEY để có nhận định."}
                for k in ("today", "short", "mid", "long")}
    prompt = (f"Mã {tk}. Số liệu (do hệ thống tính, đã chính xác):\n{json.dumps(facts, ensure_ascii=False)}\n\n"
              f"Tin liên quan:\n{_news_block(news)}\n\n"
              "Trả về JSON đúng dạng: {\"today\":{\"trend\":\"Tích cực|Trung tính|Tiêu cực\",\"text\":\"2 câu\"},"
              "\"short\":{...1-4 tuần, dựa trên kỹ thuật},\"mid\":{...1-6 tháng, dựa trên KQKD và định giá so ngành},"
              "\"long\":{...trên 1 năm, dựa trên ngành và hiệu quả sinh lời}}. Chỉ trả JSON.")
    return _json(_ask(WRITER, prompt)) or {}


def sector_view(name: str, facts: dict, news: list[dict]) -> dict:
    if not enabled():
        return {"trend": "Trung tính", "now": "[Chưa bật AI]", "drivers": "[Chưa bật AI]"}
    prompt = (f"Ngành {name}. Số liệu:\n{json.dumps(facts, ensure_ascii=False)}\n\nTin:\n{_news_block(news, 8)}\n\n"
              "Trả về JSON: {\"trend\":\"Tích cực|Trung tính|Tiêu cực\",\"now\":\"3 câu về giai đoạn hiện tại\","
              "\"drivers\":\"động lực và rủi ro chính, mỗi ý 1 câu\"}. Chỉ trả JSON.")
    return _json(_ask(WRITER, prompt)) or {}


def news_summary(item: dict) -> str:
    if not enabled():
        return item["summary"][:180]
    return _ask(WRITER, f"Tóm tắt tin sau trong 1-2 câu, nói vì sao quan trọng với cổ phiếu liên quan:\n"
                        f"{item['title']}\n{item['summary']}", 200)


def daily_report(market: dict) -> list[str]:
    """Bản tin Adviser: 3-5 dòng."""
    if not enabled():
        return ["[Chưa bật AI] Bản tin sẽ do Claude viết khi có API key."]
    out = _ask(WRITER, f"Dữ liệu phiên hôm nay:\n{json.dumps(market, ensure_ascii=False)}\n\n"
                       "Viết bản tin 3-5 dòng, mỗi dòng 1 ý (diễn biến chỉ số, dòng tiền theo ngành, mã nổi bật theo tiêu chí). "
                       "Trả về JSON là mảng chuỗi.", 600)
    return _json(out) or [out]


def verify(claims: list[str], facts: dict) -> list[dict]:
    """Sonnet đối chiếu từng câu với số liệu. Trả [{text, status: ok|warn, note}]."""
    if not enabled() or not claims:
        return [{"text": c, "status": "warn", "note": "Chưa kiểm chứng (AI tắt)"} for c in claims]
    prompt = ("Kiểm tra từng nhận định dưới đây CHỈ dựa trên bộ số liệu. Nhận định đúng với số liệu -> \"ok\". "
              "Sai, phóng đại, không có trong số liệu, hoặc mang tính khuyến nghị mua/bán -> \"warn\" kèm lý do ngắn.\n\n"
              f"SỐ LIỆU:\n{json.dumps(facts, ensure_ascii=False)}\n\nNHẬN ĐỊNH:\n"
              + "\n".join(f"{i}. {c}" for i, c in enumerate(claims))
              + "\n\nTrả JSON: [{\"i\":0,\"status\":\"ok|warn\",\"note\":\"...\"}]")
    res = _json(_ask(CHECKER, prompt, 800)) or []
    by_i = {r.get("i"): r for r in res if isinstance(r, dict)}
    return [{"text": c, "status": by_i.get(i, {}).get("status", "warn"),
             "note": by_i.get(i, {}).get("note", "Không kiểm được")} for i, c in enumerate(claims)]
