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


# ---------------------------------------------------------------- REAL (vnstock 5)
# Bảng ratio() dựng sẵn của vnstock cần gói trả phí, nên hệ thống TỰ TÍNH
# chỉ số từ báo cáo tài chính gốc (gói miễn phí) + giá thị trường.
INDEX_NAMES = {"VNINDEX", "VN30", "HNXINDEX", "HNX30", "UPCOMINDEX"}


def _market():
    from vnstock import Market  # noqa: import trễ để MOCK không cần cài
    return Market()


def get_history(ticker: str, days: int = 420) -> pd.DataFrame:
    """Giá ngày (OHLCV), cổ phiếu tính bằng đồng, chỉ số tính bằng điểm; cũ → mới."""
    if MOCK:
        return _mock_history(ticker, days)
    m = _market()
    obj = m.index(ticker) if ticker in INDEX_NAMES else m.equity(ticker)
    start = (date.today() - timedelta(days=int(days * 1.5))).isoformat()
    df = obj.ohlcv(start=start, interval="1D")
    df = df.rename(columns=str.lower)[PRICE_COLS].copy()
    t = pd.to_datetime(df["time"])
    df["time"] = t.dt.tz_localize(None) if t.dt.tz is not None else t
    if ticker not in INDEX_NAMES and df["close"].median() < 1000:
        df[["open", "high", "low", "close"]] *= 1000  # nghìn đồng -> đồng
    return df.sort_values("time").tail(days).reset_index(drop=True)


def _wide(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Bảng dạng dài (period, id, name, value) -> bảng rộng theo quý."""
    df = df[df["period"].astype(str).str.contains("Q")]
    w = df.pivot_table(index="period", columns="id", values="value", aggfunc="first").sort_index()
    names = {i: str(n).strip().lower() for i, n in zip(df["id"], df["name"])}
    return w, names


def _pick(w: pd.DataFrame, names: dict, ids=(), keys=()):
    """Tìm 1 dòng BCTC: theo mã id trước, rồi theo tên (khớp đúng > bắt đầu bằng > chứa)."""
    for i in ids:
        if i in w:
            return w[i]
    for mode in ("eq", "start", "in"):
        for col in w.columns:
            n = names.get(col, "")
            for k in keys:
                if (mode == "eq" and n == k) or (mode == "start" and n.startswith(k)) or (mode == "in" and k in n):
                    return w[col]
    return None


def _div(a, b):
    if a is None or b is None:
        return None
    return a / b.replace(0, np.nan)


def get_ratios(ticker: str, bank: bool = False) -> pd.DataFrame:
    """Chỉ số tài chính theo quý, TỰ TÍNH từ BCTC (miễn phí). Thiếu dòng nào thì chỉ số đó để trống."""
    if MOCK:
        return _mock_ratios(ticker, bank)
    from vnstock import Fundamental

    f = Fundamental().equity(ticker)
    inc, n_inc = _wide(f.income_statement(period="quarter"))
    bal, n_bal = _wide(f.balance_sheet(period="quarter"))
    idx = inc.index.union(bal.index)
    inc, bal = inc.reindex(idx), bal.reindex(idx)
    if os.getenv("DUMP_IDS") == "1":  # in danh sách dòng BCTC để dò khi cần
        print(ticker, "IS:", {k: n_inc[k] for k in list(inc.columns)[:60]})
        print(ticker, "BS:", {k: n_bal[k] for k in list(bal.columns)[:60]})

    rev = _pick(inc, n_inc, ("IS_NET_REVENUE",), ("doanh thu thuần", "thu nhập lãi thuần", "tổng thu nhập hoạt động"))
    gross = _pick(inc, n_inc, ("IS_GROSS_PROFIT",), ("lợi nhuận gộp",))
    np_ = _pick(inc, n_inc, ("IS_NET_PROFIT_PARENT", "IS_NET_PROFIT_AFTER_TAX"),
                ("lợi nhuận sau thuế của cổ đông công ty mẹ", "lợi nhuận sau thuế thu nhập doanh nghiệp", "lợi nhuận sau thuế"))
    assets = _pick(bal, n_bal, ("BS_TOTAL_ASSETS",), ("tổng cộng tài sản", "tổng tài sản"))
    equity = _pick(bal, n_bal, ("BS_OWNERS_EQUITY", "BS_EQUITY"), ("vốn chủ sở hữu", "tổng vốn chủ sở hữu"))
    liab = _pick(bal, n_bal, ("BS_TOTAL_LIABILITIES", "BS_LIABILITIES"), ("nợ phải trả", "tổng nợ phải trả"))
    cur_a = _pick(bal, n_bal, ("BS_CURRENT_ASSETS",), ("tài sản ngắn hạn",))
    cur_l = _pick(bal, n_bal, ("BS_CURRENT_LIABILITIES",), ("nợ ngắn hạn",))
    inv = _pick(bal, n_bal, ("BS_INVENTORIES",), ("hàng tồn kho",))
    cash = _pick(bal, n_bal, ("BS_CASH",), ("tiền và các khoản tương đương tiền", "tiền mặt"))
    capital = _pick(bal, n_bal, ("BS_CHARTER_CAPITAL",), ("vốn góp của chủ sở hữu", "vốn điều lệ", "cổ phiếu phổ thông"))

    out = pd.DataFrame(index=idx)
    out["quarter"] = ["Q" + p.split("Q")[-1].strip("-") + "/" + p[2:4] for p in idx.astype(str)]
    if rev is not None:
        out["revenue"] = rev
    if np_ is not None:
        out["profit"] = np_
    shares = None
    if capital is not None:
        scale = 1e9 if capital.dropna().median() < 1e7 else 1  # BCTC tính bằng tỷ đồng
        shares = capital * scale / 10000  # mệnh giá 10.000đ
        out["shares"] = shares
        unit = scale
    else:
        unit = 1
    ttm = np_.rolling(4, min_periods=1).mean() * 4 if np_ is not None else None  # lợi nhuận năm hoá
    if ttm is not None and shares is not None:
        out["eps"] = ttm * unit / shares
    if equity is not None and shares is not None:
        out["bvps"] = equity * unit / shares
    out["roe"] = _div(ttm, equity) * 100 if ttm is not None and equity is not None else None
    out["roa"] = _div(ttm, assets) * 100 if ttm is not None and assets is not None else None
    if rev is not None:
        if gross is not None:
            out["blng"] = _div(gross, rev) * 100
        if np_ is not None:
            out["blnr"] = _div(np_, rev) * 100
    if cur_a is not None and cur_l is not None:
        out["tthh"] = _div(cur_a, cur_l)
        if inv is not None:
            out["ttn"] = _div(cur_a - inv, cur_l)
        if cash is not None:
            out["ttm"] = _div(cash, cur_l)
    if liab is not None and equity is not None:
        out["debt"] = _div(liab, equity)
    if rev is not None and assets is not None:
        out["vqtts"] = _div(rev.rolling(4, min_periods=1).mean() * 4, assets)
    out = out.dropna(axis=1, how="all")
    return out.tail(12).reset_index(drop=True)
