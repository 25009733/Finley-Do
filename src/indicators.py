"""Chỉ báo kỹ thuật — do CODE tính, không để AI tính (đảm bảo chính xác, lặp lại được)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI kiểu Wilder (giống TradingView)."""
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def support_resistance(df: pd.DataFrame, lookback: int = 60) -> tuple[float, float]:
    """Hỗ trợ = đáy gần nhất dưới giá, kháng cự = đỉnh gần nhất trên giá (theo đỉnh/đáy cục bộ)."""
    w = df.tail(lookback)
    px = w["close"].iloc[-1]
    lows = w["low"][(w["low"] == w["low"].rolling(5, center=True).min())]
    highs = w["high"][(w["high"] == w["high"].rolling(5, center=True).max())]
    sup = lows[lows < px].max() if (lows < px).any() else w["low"].min()
    res = highs[highs > px].min() if (highs > px).any() else w["high"].max()
    return float(sup), float(res)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["ma20"], out["ma50"], out["ma200"] = sma(c, 20), sma(c, 50), sma(c, 200)
    out["rsi"] = rsi(c)
    out["macd"], out["macd_sig"], out["macd_hist"] = macd(c)
    out["vol20"] = sma(out["volume"], 20)
    out["volx"] = out["volume"] / out["vol20"]
    out["hi52"] = out["high"].rolling(250, min_periods=120).max()
    out["lo52"] = out["low"].rolling(250, min_periods=120).min()
    return out


def snapshot(ind: pd.DataFrame) -> dict:
    """Trạng thái kỹ thuật hôm nay, dạng mô tả (không phải khuyến nghị)."""
    t, y = ind.iloc[-1], ind.iloc[-2]
    sup, res = support_resistance(ind)
    macd_state = "Cắt lên" if (y.macd_hist <= 0 < t.macd_hist) else "Cắt xuống" if (y.macd_hist >= 0 > t.macd_hist) \
        else ("Trên tín hiệu" if t.macd_hist > 0 else "Dưới tín hiệu")
    return {
        "rsi": round(float(t.rsi), 1),
        "rsi_state": "Quá mua" if t.rsi > 70 else "Quá bán" if t.rsi < 30 else "Trung tính",
        "macd": macd_state,
        "above_ma20": bool(t.close > t.ma20), "above_ma50": bool(t.close > t.ma50),
        "above_ma200": bool(t.close > t.ma200) if not np.isnan(t.ma200) else None,
        "volx": round(float(t.volx), 2),
        "support": round(sup, -1), "resistance": round(res, -1),
        "new_high52": bool(t.close >= t.hi52 * 0.999) if not np.isnan(t.hi52) else False,
        "new_low52": bool(t.close <= t.lo52 * 1.001) if not np.isnan(t.lo52) else False,
    }
