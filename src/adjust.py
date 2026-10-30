"""Điều chỉnh giá khi có sự kiện doanh nghiệp (cổ tức, phát hành thêm, thưởng cổ phiếu).

Tại sao cần: ngày giao dịch không hưởng quyền (GDKHQ), giá tham chiếu bị
hạ xuống. Nếu không điều chỉnh lịch sử, biểu đồ có một "vực" giả và các
chỉ báo (MA, RSI, MACD, đỉnh 52 tuần) đều sai.

Công thức giá tham chiếu sau sự kiện (theo cách Sở GDCK áp dụng):
    P_ref = (P_truoc - Co_tuc_tien + Gia_PH * R_mua) / (1 + R_mua + R_thuong)
    - R_mua   : tỷ lệ quyền mua phát hành thêm (vd 10:3 -> 0.3)
    - Gia_PH  : giá phát hành cho cổ đông hiện hữu
    - R_thuong: tỷ lệ thưởng / cổ tức bằng cổ phiếu (vd 100:20 -> 0.2)
Hệ số điều chỉnh k = P_ref / P_truoc. Mọi giá TRƯỚC ngày GDKHQ nhân k,
khối lượng TRƯỚC ngày đó chia k.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Biên độ dao động: vượt mức này mà không có sự kiện = dữ liệu đáng ngờ
BAND = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}


@dataclass
class CorporateAction:
    ex_date: str            # ngày GDKHQ, "YYYY-MM-DD"
    cash_dividend: float = 0.0   # đồng / CP
    rights_ratio: float = 0.0    # R_mua
    rights_price: float = 0.0    # Gia_PH
    bonus_ratio: float = 0.0     # R_thuong


def adjustment_factor(prev_close: float, a: CorporateAction) -> float:
    p_ref = (prev_close - a.cash_dividend + a.rights_price * a.rights_ratio) / (1 + a.rights_ratio + a.bonus_ratio)
    return p_ref / prev_close


def adjust_prices(df: pd.DataFrame, actions: list[CorporateAction]) -> pd.DataFrame:
    """Trả về bản sao df đã điều chỉnh giá/khối lượng cho các sự kiện."""
    out = df.copy()
    out[["open", "high", "low", "close", "volume"]] = out[["open", "high", "low", "close", "volume"]].astype(float)
    for a in sorted(actions, key=lambda x: x.ex_date, reverse=True):
        ex = pd.Timestamp(a.ex_date)
        before = out["time"] < ex
        if not before.any():
            continue
        prev_close = out.loc[before, "close"].iloc[-1]
        k = adjustment_factor(prev_close, a)
        out.loc[before, ["open", "high", "low", "close"]] *= k
        out.loc[before, "volume"] = (out.loc[before, "volume"] / k).round()
    return out


def suspicious_gaps(df: pd.DataFrame, exchange: str = "HOSE") -> pd.DataFrame:
    """Các phiên giá đổi vượt biên độ sàn -> gần như chắc chắn là sự kiện chưa điều chỉnh."""
    band = BAND.get(exchange, 0.07) + 0.005
    chg = df["close"] / df["close"].shift(1) - 1
    return df.loc[chg.abs() > band, ["time", "close"]].assign(change=chg[chg.abs() > band])
