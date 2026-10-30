"""Lấy dữ liệu giá và báo cáo tài chính.

- Chạy thật: dùng thư viện vnstock (cài trên GitHub Actions).
- Chạy thử: đặt biến môi trường MOCK=1 để sinh dữ liệu giả lập (không cần mạng).

Mọi hàm trả về pandas.DataFrame đã chuẩn hoá tên cột, để phần còn lại
của hệ thống không phụ thuộc vào phiên bản vnstock.
"""
from __future__ import annotations

import os
import zlib
from datetime import date, timedelta

import numpy as np
import pandas as pd

MOCK = os.getenv("MOCK") == "1"
SOURCE = os.getenv("VNSTOCK_SOURCE", "VCI")

PRICE_COLS = ["time", "open", "high", "low", "close", "volume"]

# Tên chỉ số chuẩn của hệ thống -> các tên cột có thể gặp trong vnstock
# (vnstock đổi tên cột giữa các phiên bản, nên dò theo nhiều tên).
RATIO_ALIASES = {
    "eps": ["EPS (VND)", "eps", "EPS"],
    "bvps": ["BVPS (VND)", "bvps", "BVPS"],
    "pe": ["P/E", "pe", "price_to_earning"],
    "pb": ["P/B", "pb", "price_to_book"],
    "evebitda": ["EV/EBITDA", "ev_ebitda", "value_before_ebitda"],
    "roe": ["ROE (%)", "roe"],
    "roa": ["ROA (%)", "roa"],
    "blng": ["Gross Profit Margin (%)", "gross_profit_margin"],
    "blnr": ["Net Profit Margin (%)", "post_tax_margin", "net_profit_margin"],
    "ebitda": ["EBITDA Margin (%)", "ebitda_margin"],
    "tthh": ["Current Ratio", "current_payment", "current_ratio"],
    "ttn": ["Quick Ratio", "quick_payment", "quick_ratio"],
    "ttm": ["Cash Ratio", "cash_ratio"],
    "debt": ["Debt/Equity", "debt_on_equity", "de"],
    "icr": ["Interest Coverage", "ebit_on_interest", "interest_coverage"],
    "vqhtk": ["Inventory Turnover", "inventory_turnover"],
    "vqpt": ["Receivable Turnover", "receivable_turnover"],
    "vqtts": ["Asset Turnover", "asset_turnover"],
    "cap": ["Market Capital (Bn. VND)", "market_cap"],
    "revenue": ["Revenue (Bn. VND)", "revenue", "Doanh thu thuần"],
    "profit": ["Net Profit For the Year", "post_tax_profit", "Lợi nhuận sau thuế"],
    # Ngân hàng
    "nim": ["NIM (%)", "nim"],
    "npl": ["NPL (%)", "bad_debt_percentage", "npl"],
    "llr": ["LLR (%)", "provision_on_bad_debt", "llr"],
    "ldr": ["LDR (%)", "loan_on_deposit", "ldr"],
    "car": ["CAR (%)", "car"],
    "casa": ["CASA (%)", "casa"],
}


def _seed(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode())


# ---------------------------------------------------------------- MOCK
def _mock_history(ticker: str, days: int) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(ticker, "px"))
    n = days
    end = date.today()
    dates = pd.bdate_range(end=end, periods=n)
    price = 10 + rng.random() * 100
    rows = []
    for d in dates:
        o = price
        c = max(1.0, o * (1 + rng.normal(0.0004, 0.02)))
        h = max(o, c) * (1 + abs(rng.normal(0, 0.007)))
        l = min(o, c) * (1 - abs(rng.normal(0, 0.007)))
        v = int(rng.lognormal(13, 0.5))
        rows.append((d, o, h, l, c, v))
        price = c
    df = pd.DataFrame(rows, columns=PRICE_COLS)
    df[["open", "high", "low", "close"]] *= 1000  # đơn vị đồng
    return df


def _mock_ratios(ticker: str, bank: bool) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(ticker, "fin"))
    q = pd.period_range(end=pd.Timestamp.today(), periods=12, freq="Q")
    base = {
        "eps": 500 + rng.random() * 6000, "bvps": 8000 + rng.random() * 30000,
        "pe": 6 + rng.random() * 20, "pb": 0.7 + rng.random() * 3, "evebitda": 4 + rng.random() * 12,
        "roe": 6 + rng.random() * 20, "roa": 1 + rng.random() * 10, "blng": 8 + rng.random() * 40,
        "blnr": 2 + rng.random() * 20, "ebitda": 5 + rng.random() * 25, "tthh": 0.8 + rng.random() * 2.5,
        "ttn": 0.4 + rng.random() * 2, "ttm": 0.05 + rng.random() * 0.7, "debt": 0.1 + rng.random() * 1.8,
        "icr": 2 + rng.random() * 20, "vqhtk": 2 + rng.random() * 9, "vqpt": 3 + rng.random() * 10,
        "vqtts": 0.3 + rng.random() * 1.3, "cap": 3000 + rng.random() * 300000,
        "revenue": 500 + rng.random() * 30000, "profit": 50 + rng.random() * 4000,
    }
    if bank:
        base.update({"nim": 2.5 + rng.random() * 3, "npl": 0.6 + rng.random() * 2.2, "llr": 60 + rng.random() * 170,
                     "ldr": 70 + rng.random() * 20, "car": 9 + rng.random() * 5, "casa": 10 + rng.random() * 30})
    rows = []
    for i, p in enumerate(q):
        drift = 1 + (rng.random() - 0.5) * 0.15 * (i / 6)
        rows.append({"quarter": f"Q{p.quarter}/{str(p.year)[2:]}", **{k: v * drift for k, v in base.items()}})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- REAL
def _vn_stock(ticker: str):
    """Trả về đối tượng cổ phiếu của vnstock, chịu được cả API cũ lẫn mới."""
    import vnstock  # noqa: import trễ để MOCK không cần cài

    if hasattr(vnstock, "Vnstock"):
        return vnstock.Vnstock().stock(symbol=ticker, source=SOURCE)
    raise RuntimeError("Không tìm thấy lớp Vnstock — kiểm tra phiên bản vnstock (xem README).")


def get_history(ticker: str, days: int = 420) -> pd.DataFrame:
    """Giá ngày (OHLCV), đơn vị đồng, cũ → mới."""
    if MOCK:
        return _mock_history(ticker, days)
    st = _vn_stock(ticker)
    start = (date.today() - timedelta(days=int(days * 1.5))).isoformat()
    df = st.quote.history(start=start, end=date.today().isoformat(), interval="1D")
    df = df.rename(columns=str.lower)[PRICE_COLS].copy()
    df["time"] = pd.to_datetime(df["time"])
    # vnstock (nguồn VCI) trả giá theo đơn vị nghìn đồng
    if df["close"].median() < 1000:
        df[["open", "high", "low", "close"]] *= 1000
    return df.sort_values("time").tail(days).reset_index(drop=True)


def _flatten(cols) -> list[str]:
    out = []
    for c in cols:
        out.append(c[-1] if isinstance(c, tuple) else c)
    return [str(c) for c in out]


def get_ratios(ticker: str, bank: bool = False) -> pd.DataFrame:
    """Chỉ số tài chính theo quý (12 quý gần nhất), tên cột đã chuẩn hoá."""
    if MOCK:
        return _mock_ratios(ticker, bank)
    st = _vn_stock(ticker)
    raw = st.finance.ratio(period="quarter", lang="en", dropna=True)
    raw.columns = _flatten(raw.columns)
    out = pd.DataFrame()
    yr = next((c for c in raw.columns if c.lower() in ("yearreport", "year")), None)
    qr = next((c for c in raw.columns if c.lower() in ("lengthreport", "quarter")), None)
    if yr and qr:
        out["quarter"] = "Q" + raw[qr].astype(str) + "/" + raw[yr].astype(str).str[-2:]
    for key, names in RATIO_ALIASES.items():
        col = next((c for c in names if c in raw.columns), None)
        if col is not None:
            out[key] = pd.to_numeric(raw[col], errors="coerce")
    # % trong vnstock thường là số thập phân (0.21) — đổi về % cho dễ đọc
    for k in ("roe", "roa", "blng", "blnr", "ebitda", "nim", "npl", "llr", "ldr", "car", "casa"):
        if k in out and out[k].abs().median() < 1.5:
            out[k] *= 100
    if "quarter" in out:
        out = out.iloc[::-1] if out["quarter"].iloc[0] > out["quarter"].iloc[-1] else out
    return out.tail(12).reset_index(drop=True)
