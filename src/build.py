"""Chạy toàn bộ quy trình và ghi docs/data.json cho dashboard + gửi bản tin Zalo.

Cách chạy:
    python src/build.py --mode daily       # sau 15h: giá, kỹ thuật, tin, nhận định mã nổi bật + ngành
    python src/build.py --mode weekly      # cuối tuần: nhận định cho TẤT CẢ mã
    python src/build.py --mode quarterly   # mùa BCTC: tải lại chỉ số tài chính
    python src/build.py --mode morning     # 8h sáng: chỉ gửi bản tin sáng từ dữ liệu sẵn có
Thêm --no-ai để bỏ qua AI, --no-send để không gửi Zalo. MOCK=1 để chạy thử không cần mạng.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adjust  # noqa: E402
import ai  # noqa: E402
import backtest  # noqa: E402
import data_source as ds  # noqa: E402
import indicators as ind  # noqa: E402
import news as newsmod  # noqa: E402
import zalo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data.json"
RATIO_CACHE = ROOT / "data" / "ratios"
VN_TZ = timezone(timedelta(hours=7))
TOP_N = 8
RATIO_KEYS = list(ds.RATIO_ALIASES)
INDICES = ["VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"]


def r2(x, nd=2):
    try:
        x = float(x)
        return None if np.isnan(x) or np.isinf(x) else round(x, nd)
    except (TypeError, ValueError):
        return None


def load_sectors() -> list[dict]:
    return json.loads((ROOT / "config" / "sectors.json").read_text())


def ratios_for(tk: str, bank: bool, refresh: bool) -> pd.DataFrame:
    RATIO_CACHE.mkdir(parents=True, exist_ok=True)
    f = RATIO_CACHE / f"{tk}.json"
    if f.exists() and not refresh:
        return pd.read_json(f)
    df = ds.get_ratios(tk, bank)
    df.to_json(f, orient="records", force_ascii=False)
    return df


def stock_block(tk: str, sec: dict, refresh_ratios: bool) -> dict | None:
    try:
        hist = ds.get_history(tk)
    except Exception as e:  # noqa: BLE001
        print(f"[giá] {tk} lỗi: {e}")
        return None
    gaps = adjust.suspicious_gaps(hist)
    x = ind.compute(hist)
    t, y = x.iloc[-1], x.iloc[-2]
    try:
        fin = ratios_for(tk, sec["id"] == "bank", refresh_ratios)
    except Exception as e:  # noqa: BLE001
        print(f"[BCTC] {tk} lỗi: {e}")
        fin = pd.DataFrame()
    last = fin.iloc[-1].to_dict() if len(fin) else {}
    lo_i = int(x["low"].tail(250).idxmin())
    after_lo = x.loc[lo_i:]
    peak = after_lo["high"].max()
    dd = (after_lo["close"] / after_lo["close"].cummax() - 1).min()
    b = {
        "tk": tk, "sec": sec["id"], "secName": sec["name"],
        "px": r2(t.close, 0), "chg": r2((t.close / y.close - 1) * 100),
        "vol": int(t.volume), "volx": r2(t.volx),
        "tech": ind.snapshot(x),
        "signals": backtest.run(x),
        "dayDinh": r2((peak / x.loc[lo_i, "low"] - 1) * 100, 0),
        "dieuChinh": r2(dd * 100, 0),
        "data_warnings": [f"Phiên {d:%d/%m/%Y} giá đổi {c:+.1%} vượt biên độ — có thể do sự kiện chưa điều chỉnh"
                          for d, c in zip(gaps["time"], gaps["change"])][-3:],
        "candles": [[d.strftime("%Y-%m-%d"), r2(o, 0), r2(h, 0), r2(l, 0), r2(c, 0), int(v)]
                    for d, o, h, l, c, v in x[["time", "open", "high", "low", "close", "volume"]].tail(180).itertuples(index=False)],
        "quarters": fin["quarter"].tolist() if "quarter" in fin else [],
        "hist": {k: [r2(v) for v in fin[k].tolist()] for k in RATIO_KEYS if k in fin},
    }
    for k in RATIO_KEYS:
        b[k] = r2(last.get(k))
    if b.get("cap"):
        b["cap"] = r2(b["cap"] / 1000, 0)  # tỷ -> nghìn tỷ
    # tăng trưởng lợi nhuận quý so cùng kỳ (quý hiện tại vs 4 quý trước)
    pr = b["hist"].get("profit", [])
    b["profit_yoy"] = r2((pr[-1] / pr[-5] - 1) * 100, 1) if len(pr) >= 5 and pr[-5] else None
    return b


def score(b: dict, sec_pe_median: float | None) -> tuple[int, list[str]]:
    s, why = 0.0, []
    if b["chg"] is not None and abs(b["chg"]) >= 3:
        s += min(30, abs(b["chg"]) * 5); why.append(f"Biến động mạnh {b['chg']:+.2f}%")
    if (b["volx"] or 0) >= 2:
        s += 25; why.append(f"Khối lượng gấp {b['volx']}× TB20")
    if b["tech"]["new_high52"]:
        s += 20; why.append("Lập đỉnh 52 tuần")
    if (b.get("profit_yoy") or 0) >= 30:
        s += 15; why.append(f"LN quý tăng {b['profit_yoy']:.0f}% cùng kỳ")
    if b.get("pe") and sec_pe_median and 0 < b["pe"] < sec_pe_median * 0.8:
        s += 10; why.append("P/E thấp hơn trung vị ngành")
    if any(v["active_today"] for v in b["signals"].values()):
        s += 10; why.append("Có tín hiệu kỹ thuật mới")
    return int(min(99, s)), why


def facts_for_ai(b: dict) -> dict:
    keep = ["px", "chg", "volx", "pe", "pb", "eps", "roe", "roa", "blnr", "debt", "profit_yoy", "dayDinh", "dieuChinh",
            "nim", "npl", "car", "pe_sector_median", "fair_pe"]
    f = {k: b.get(k) for k in keep if b.get(k) is not None}
    f["ky_thuat"] = b["tech"]
    f["tin_hieu_hom_nay"] = {v["label"]: backtest.describe(v, b["tk"]) for v in b["signals"].values() if v["active_today"]}
    f["xu_huong_chi_so_12_quy"] = {k: v for k, v in b["hist"].items() if k in ("eps", "roe", "blnr", "revenue", "profit")}
    return f


def zalo_text(data: dict, morning: bool) -> str:
    secs = sorted(data["sectors"], key=lambda s: s["chg"], reverse=True)
    idx = data["market"]["indices"]
    head = "☀️ Bản tin sáng" if morning else "📊 Bản tin cuối phiên"
    lines = [f"{head} {datetime.now(VN_TZ):%d/%m}"]
    for i in idx[:2]:
        v = f"{i['value']:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
        lines.append(f"{i['name']}: {v} ({i['chg']:+.2f}%)")
    lines.append("🟢 Mạnh: " + ", ".join(f"{s['name']} {s['chg']:+.1f}%" for s in secs[:3]))
    lines.append("🔴 Yếu: " + ", ".join(f"{s['name']} {s['chg']:+.1f}%" for s in secs[-3:]))
    lines.append("⭐ Nổi bật theo tiêu chí: " + " · ".join(data["top"][:5]))
    ok = [r["text"] for r in data["report"] if r["status"] == "ok"][:2]
    lines += [f"• {t}" for t in ok]
    url = os.getenv("DASHBOARD_URL", "")
    if url:
        lines.append(f"👉 Chi tiết: {url}")
    lines.append("Thông tin tham khảo, không phải khuyến nghị đầu tư.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="daily", choices=["daily", "weekly", "quarterly", "morning"])
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="chỉ chạy N mã/ngành (thử nghiệm)")
    a = ap.parse_args()
    if a.no_ai:
        os.environ.pop("ANTHROPIC_API_KEY", None)

    prev = json.loads(OUT.read_text()) if OUT.exists() else {}
    if a.mode == "morning":
        if prev and not a.no_send:
            zalo.register_new()
            zalo.send(zalo_text(prev, morning=True))
        return

    sectors = load_sectors()
    if a.limit:
        sectors = [dict(s, tickers=s["tickers"][:a.limit]) for s in sectors[:a.limit]]
    refresh = a.mode == "quarterly"

    stocks: dict[str, dict] = {}
    for sec in sectors:
        for tk in sec["tickers"]:
            b = stock_block(tk, sec, refresh)
            if b:
                stocks[tk] = b
            if not ds.MOCK:
                time.sleep(0.6)  # tránh bị nguồn dữ liệu chặn vì gọi quá nhanh
    # chỉ số thị trường
    indices = []
    for name in INDICES:
        try:
            h = ds.get_history(name, 30)
            indices.append({"name": name, "value": r2(h.close.iloc[-1] / (1000 if h.close.median() > 100000 else 1)),
                            "chg": r2((h.close.iloc[-1] / h.close.iloc[-2] - 1) * 100)})
        except Exception as e:  # noqa: BLE001
            print(f"[chỉ số] {name} lỗi: {e}")

    # tổng hợp ngành + định giá theo P/E trung vị ngành (code tính, không phải AI)
    sec_out = []
    for sec in sectors:
        arr = [stocks[t] for t in sec["tickers"] if t in stocks]
        if not arr:
            continue
        pes = [s["pe"] for s in arr if s.get("pe") and s["pe"] > 0]
        med = float(np.median(pes)) if pes else None
        for s in arr:
            s["pe_sector_median"] = r2(med, 1)
            s["fair_pe"] = r2(med, 1)
            s["fair_px"] = r2(s["eps"] * med, -2) if s.get("eps") and med else None
            s["upside"] = r2((s["fair_px"] / s["px"] - 1) * 100, 1) if s.get("fair_px") else None
            s["score"], s["reasons"] = score(s, med)
        sec_out.append({"id": sec["id"], "name": sec["name"], "tickers": [s["tk"] for s in arr],
                        "chg": r2(np.mean([s["chg"] for s in arr])), "pe": r2(med, 1)})

    top = [s["tk"] for s in sorted(stocks.values(), key=lambda s: s["score"], reverse=True)[:TOP_N]]

    # tin tức
    items = newsmod.fetch_all()
    by_tk, by_sec = newsmod.match(items, list(stocks), sec_out)
    for tk, lst in by_tk.items():
        stocks[tk]["news"] = lst[:6]
    for s in sec_out:
        s["news"] = by_sec.get(s["id"], [])[:6]

    # AI: hằng ngày chỉ mã nổi bật + ngành; hằng tuần mọi mã; còn lại giữ nhận định cũ
    prev_st = prev.get("stocks", {})
    targets = list(stocks) if a.mode == "weekly" else top
    for tk, s in stocks.items():
        if tk in targets:
            facts = facts_for_ai(s)
            view = ai.stock_view(tk, facts, s.get("news", []))
            checks = ai.verify([f"{k}: {v.get('text', '')}" for k, v in view.items()], facts)
            for (k, v), c in zip(view.items(), checks):
                v["status"], v["note"] = c["status"], c["note"]
            s["view"], s["view_date"] = view, datetime.now(VN_TZ).strftime("%d/%m/%Y")
        elif tk in prev_st and "view" in prev_st[tk]:
            s["view"], s["view_date"] = prev_st[tk]["view"], prev_st[tk].get("view_date")
    for s in sec_out:
        arr = [stocks[t] for t in s["tickers"]]
        facts = {"chg_tb": s["chg"], "pe_trung_vi": s["pe"],
                 "ma": {x["tk"]: {"chg": x["chg"], "pe": x.get("pe"), "roe": x.get("roe")} for x in arr}}
        v = ai.sector_view(s["name"], facts, s["news"])
        chk = ai.verify([v.get("now", ""), v.get("drivers", "")], facts)
        v["status"] = "ok" if all(c["status"] == "ok" for c in chk) else "warn"
        s["view"] = v

    market = {"indices": indices, "nganh": {s["name"]: s["chg"] for s in sec_out},
              "noi_bat": {t: stocks[t]["reasons"] for t in top}}
    report = ai.verify(ai.daily_report(market), market)

    data = {"updated": datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y"), "mock": ds.MOCK,
            "market": {"indices": indices}, "sectors": sec_out, "stocks": stocks, "top": top, "report": report}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cdir = OUT.parent / "c"
    cdir.mkdir(exist_ok=True)
    for tk, st in stocks.items():  # nến tách file riêng, dashboard chỉ tải khi mở mã
        (cdir / f"{tk}.json").write_text(json.dumps(st.pop("candles"), separators=(",", ":")))
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"Đã ghi {OUT} — {len(stocks)} mã, {len(sec_out)} ngành, {len(items)} tin")

    if a.mode == "daily" and not a.no_send:
        zalo.register_new()
        zalo.send(zalo_text(data, morning=False))


if __name__ == "__main__":
    main()
