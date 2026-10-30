"""Gửi bản tin qua bot Zalo (Zalo Bot Platform — bot.zaloplatforms.com).

API của Zalo Bot Platform có dạng giống Telegram:
    https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>
KIỂM TRA LẠI tên method và tham số theo tài liệu chính thức khi tạo bot
(xem README, mục "Test bot Zalo"). Nếu khác, chỉ cần sửa 2 hàm dưới đây.

Danh sách người nhận lưu ở config/subscribers.json (chat_id).
Người dùng mới nhắn "/start" cho bot -> lượt chạy kế tiếp tự thêm vào danh sách.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

TOKEN = os.getenv("ZALO_BOT_TOKEN", "")
BASE = os.getenv("ZALO_API_BASE", "https://bot-api.zaloplatforms.com")
SUBS = Path(__file__).resolve().parent.parent / "config" / "subscribers.json"


def _url(method: str) -> str:
    return f"{BASE}/bot{TOKEN}/{method}"


def load_subscribers() -> list[str]:
    return json.loads(SUBS.read_text()) if SUBS.exists() else []


def register_new() -> list[str]:
    """Lấy tin nhắn mới, ai gửi /start thì thêm vào danh sách nhận."""
    subs = load_subscribers()
    if not TOKEN:
        return subs
    try:
        r = requests.post(_url("getUpdates"), json={"timeout": 0}, timeout=20).json()
    except Exception as e:  # noqa: BLE001
        print(f"[zalo] getUpdates lỗi: {e}")
        return subs
    for u in r.get("result", []) if isinstance(r.get("result"), list) else [r.get("result") or {}]:
        msg = u.get("message", {})
        chat = str(msg.get("chat", {}).get("id", ""))
        if chat and msg.get("text", "").strip().lower() in ("/start", "start", "đăng ký") and chat not in subs:
            subs.append(chat)
    SUBS.write_text(json.dumps(subs, indent=1))
    return subs


def send(text: str, chat_ids: list[str] | None = None) -> int:
    """Gửi text tới danh sách người nhận. Trả về số tin gửi thành công."""
    chat_ids = chat_ids if chat_ids is not None else load_subscribers()
    if not TOKEN:
        print("[zalo] Chưa có ZALO_BOT_TOKEN — in bản tin ra màn hình:\n" + text)
        return 0
    ok = 0
    for cid in chat_ids:
        try:
            r = requests.post(_url("sendMessage"), json={"chat_id": cid, "text": text[:2000]}, timeout=20)
            ok += r.ok
        except Exception as e:  # noqa: BLE001
            print(f"[zalo] gửi {cid} lỗi: {e}")
    return ok
