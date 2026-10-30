"""Backtest tín hiệu kỹ thuật trên lịch sử của CHÍNH mã đó.

Cho mỗi tín hiệu: đếm số lần xuất hiện, tỷ lệ giá cao hơn sau N phiên,
lợi nhuận trung bình. Mục đích: minh bạch tín hiệu đáng tin đến đâu —
mô tả thống kê quá khứ, không phải dự báo hay khuyến nghị.
"""
from __future__ import annotations

import pandas as pd

HORIZON = 20  # số phiên nhìn về phía trước

SIGNALS = {
    "rsi_up30": "RSI vượt lên khỏi vùng quá bán (30)",
    "ma50_up_vol": "Giá cắt lên MA50 kèm khối lượng ≥ 1,5× TB20",
    "macd_up": "MACD cắt lên đường tín hiệu",
    "high52": "Giá lập đỉnh 52 tuần",
    "rsi_down70": "RSI rời vùng quá mua (70)",
}


def _flags(ind: pd.DataFrame) -> pd.DataFrame:
    c, p = ind, ind.shift(1)
    return pd.DataFrame({
        "rsi_up30": (p.rsi < 30) & (c.rsi >= 30),
        "ma50_up_vol": (p.close <= p.ma50) & (c.close > c.ma50) & (c.volx >= 1.5),
        "macd_up": (p.macd_hist <= 0) & (c.macd_hist > 0),
        "high52": (c.close >= c.hi52 * 0.999) & (p.close < p.hi52 * 0.999),
        "rsi_down70": (p.rsi > 70) & (c.rsi <= 70),
    }).fillna(False)


def run(ind: pd.DataFrame, horizon: int = HORIZON) -> dict:
    """Trả về {tên_tín_hiệu: {...thống kê, active_today}}."""
    flags = _flags(ind)
    fwd = ind["close"].shift(-horizon) / ind["close"] - 1
    out = {}
    for key, label in SIGNALS.items():
        hits = flags[key] & fwd.notna()
        r = fwd[hits]
        out[key] = {
            "label": label,
            "active_today": bool(flags[key].iloc[-1]),
            "count": int(hits.sum()),
            "win_rate": round(float((r > 0).mean() * 100), 0) if len(r) else None,
            "avg_return": round(float(r.mean() * 100), 1) if len(r) else None,
            "horizon": horizon,
        }
    return out


def describe(stat: dict, ticker: str) -> str:
    if not stat["count"]:
        return f"Chưa đủ dữ liệu lịch sử để thống kê tín hiệu này ở {ticker}."
    return (f"Trong dữ liệu quá khứ, tín hiệu này xuất hiện {stat['count']} lần ở {ticker}: "
            f"{stat['win_rate']:.0f}% số lần giá cao hơn sau {stat['horizon']} phiên, "
            f"thay đổi trung bình {stat['avg_return']:+.1f}%. Quá khứ không đảm bảo tương lai.")
