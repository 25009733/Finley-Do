"""Thu thập tin tức qua RSS miễn phí (không tốn phí search của AI).

Kiểm tra lại các đường dẫn RSS khi chạy lần đầu (xem README) —
báo có thể đổi đường dẫn. Feed nào lỗi sẽ được bỏ qua, không làm hỏng cả lượt chạy.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

FEEDS = [
    ("CafeF", "https://cafef.vn/thi-truong-chung-khoan.rss"),
    ("CafeF DN", "https://cafef.vn/doanh-nghiep.rss"),
    ("VnExpress", "https://vnexpress.net/rss/kinh-doanh.rss"),
    ("Vietstock", "https://vietstock.vn/830/chung-khoan/co-phieu.rss"),
    ("Tuổi Trẻ", "https://tuoitre.vn/rss/kinh-doanh.rss"),
]

# Từ khoá nhận diện tin theo ngành
SECTOR_KEYWORDS = {
    "bank": ["ngân hàng", "tín dụng", "lãi suất", "nợ xấu"],
    "bds": ["bất động sản", "nhà ở", "khu công nghiệp", "dự án"],
    "chung-khoan": ["công ty chứng khoán", "margin", "thanh khoản thị trường"],
    "thep": ["thép", "quặng sắt", "tôn"],
    "cong-nghe": ["công nghệ", "phần mềm", "viễn thông", "chuyển đổi số"],
    "ban-le": ["bán lẻ", "tiêu dùng", "sức mua"],
    "fnb": ["thực phẩm", "đồ uống", "bia", "sữa", "đường"],
    "dau-khi": ["dầu", "khí", "xăng", "giá dầu"],
    "dien": ["điện", "năng lượng", "EVN", "quy hoạch điện"],
    "hoa-chat": ["hóa chất", "phân bón", "ure"],
    "vlxd": ["xi măng", "vật liệu xây dựng", "nhựa", "đá"],
    "xay-dung": ["xây dựng", "đầu tư công", "cao tốc", "hạ tầng"],
    "duoc": ["dược", "thuốc", "y tế"],
    "hang-khong": ["hàng không", "sân bay", "chuyến bay"],
    "thuy-san": ["thủy sản", "cá tra", "tôm"],
    "logistic": ["cảng", "logistics", "vận tải", "container"],
    "cao-su": ["cao su"],
    "det-may": ["dệt may", "may mặc", "sợi"],
    "khoang-san": ["khoáng sản", "than", "đất hiếm"],
}


def _mock_items() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {"source": "Mẫu", "title": "[Tin mẫu] Ngân hàng đẩy mạnh tín dụng cuối năm, VCB và BID được chú ý", "summary": "Tin giả lập để kiểm thử.", "link": "#", "published": now},
        {"source": "Mẫu", "title": "[Tin mẫu] Giá thép xây dựng điều chỉnh, HPG công bố sản lượng tháng", "summary": "Tin giả lập để kiểm thử.", "link": "#", "published": now},
        {"source": "Mẫu", "title": "[Tin mẫu] FPT ký hợp đồng công nghệ mới tại thị trường nước ngoài", "summary": "Tin giả lập để kiểm thử.", "link": "#", "published": now},
    ]


def fetch_all(limit_per_feed: int = 40) -> list[dict]:
    if os.getenv("MOCK") == "1":
        return _mock_items()
    import feedparser

    items, seen = [], set()
    for name, url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            print(f"[news] bỏ qua {name}: {e}")
            continue
        for e in feed.entries[:limit_per_feed]:
            title = e.get("title", "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            summary = re.sub("<[^>]+>", " ", e.get("summary", "")).strip()
            items.append({"source": name, "title": title, "summary": summary[:400],
                          "link": e.get("link", ""), "published": e.get("published", "")})
    return items


def match(items: list[dict], tickers: list[str], sectors: list[dict]) -> tuple[dict, dict]:
    """Gắn tin vào mã (theo mã CK viết hoa) và vào ngành (theo từ khoá)."""
    by_tk = {t: [] for t in tickers}
    by_sec = {s["id"]: [] for s in sectors}
    pats = {t: re.compile(rf"(?<![A-Z0-9]){t}(?![A-Z0-9])") for t in tickers}
    for it in items:
        text = it["title"] + " " + it["summary"]
        for t, p in pats.items():
            if p.search(text):
                by_tk[t].append(it)
        low = text.lower()
        for sid, kws in SECTOR_KEYWORDS.items():
            if sid in by_sec and any(k.lower() in low for k in kws):
                by_sec[sid].append(it)
    return by_tk, by_sec
