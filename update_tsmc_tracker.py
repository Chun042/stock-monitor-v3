#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TSMC Stock Monitor V2: daily data, technical transitions, LINE and iPhone Web Push."""
from __future__ import annotations

import os, json, logging, argparse
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.chart import LineChart, Reference
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
# Cloud mode writes the published files used by GitHub Pages.
# Local mode is isolated under local_test/ so it cannot overwrite cloud state.
DOCS = ROOT / "docs"
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
RUN_MODE = "local"

STOCK_ID = "2330"
TICKER = "2330.TW"
TZ = ZoneInfo("Asia/Taipei")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "").strip()
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_USER_ID = os.getenv("LINE_USER_ID", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_CLAIMS_SUB = os.getenv("VAPID_CLAIMS_SUB", "mailto:your-email@example.com").strip()
PUSH_API_BASE = os.getenv("PUSH_API_BASE", "").strip().rstrip("/")
PUSH_ADMIN_TOKEN = os.getenv("PUSH_ADMIN_TOKEN", "").strip()
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tsmc-monitor")


def finmind(dataset: str, start_date: str) -> pd.DataFrame:
    if not FINMIND_TOKEN:
        return pd.DataFrame()
    r = requests.get(
        "https://api.finmindtrade.com/api/v4/data",
        headers={"Authorization": f"Bearer {FINMIND_TOKEN}"},
        params={"dataset": dataset, "data_id": STOCK_ID, "start_date": start_date},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != 200:
        raise RuntimeError(f"FinMind {dataset}: {payload}")
    return pd.DataFrame(payload.get("data", []))


def get_prices() -> pd.DataFrame:
    df = yf.download(TICKER, period="2y", interval="1d", auto_adjust=True, progress=False, threads=False)
    if df.empty:
        raise RuntimeError("Yahoo Finance 未回傳行情；停止產生訊號，避免使用過期資料。")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "日期"
    df = df.rename(columns={"Open":"開盤", "High":"最高", "Low":"最低", "Close":"收盤", "Volume":"成交量"})
    return df[["開盤","最高","最低","收盤","成交量"]].dropna(subset=["收盤"])


def indicators(raw: pd.DataFrame) -> pd.DataFrame:
    x = raw.copy()
    c, h, l = x["收盤"], x["最高"], x["最低"]
    for n in (5, 20, 60, 120):
        x[f"MA{n}"] = c.rolling(n).mean()

    d = c.diff()
    up, down = d.clip(lower=0), -d.clip(upper=0)
    ag = up.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    al = down.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = ag / al.replace(0, np.nan)
    x["RSI14"] = 100 - 100/(1+rs)
    x.loc[(al == 0) & (ag > 0), "RSI14"] = 100

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    x["DIF"] = ema12 - ema26
    x["MACD訊號"] = x["DIF"].ewm(span=9, adjust=False).mean()
    x["MACD柱"] = x["DIF"] - x["MACD訊號"]

    lo9, hi9 = l.rolling(9).min(), h.rolling(9).max()
    rsv = (c-lo9)/(hi9-lo9).replace(0, np.nan)*100
    x["K"] = rsv.ewm(com=2, adjust=False).mean()
    x["D"] = x["K"].ewm(com=2, adjust=False).mean()

    pc = c.shift(1)
    tr = pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    x["ATR14"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x["MA20乖離率%"] = (c/x["MA20"]-1)*100
    x["20日均量"] = x["成交量"].rolling(20).mean()
    x["量比"] = x["成交量"]/x["20日均量"]
    x["前20日高點"] = x["最高"].shift(1).rolling(20).max()
    x["前20日低點"] = x["最低"].shift(1).rolling(20).min()
    x["帶量突破"] = (c > x["前20日高點"]) & (x["量比"] >= 1.5)
    return x


def safe_num(v):
    return None if pd.isna(v) else float(v)


def current_states(row: pd.Series) -> dict:
    def val(k):
        v = row.get(k)
        return None if pd.isna(v) else float(v)

    close, ma20, ma60, ma120 = val("收盤"), val("MA20"), val("MA60"), val("MA120")
    rsi, dif, sig, k, d, vr = val("RSI14"), val("DIF"), val("MACD訊號"), val("K"), val("D"), val("量比")
    rsi_zone = None
    if rsi is not None:
        rsi_zone = "超賣(<30)" if rsi < 30 else "偏弱(30-50)" if rsi < 50 else "偏強(50-70)" if rsi < 70 else "過熱(>=70)"
    return {
        "price_vs_ma20": None if close is None or ma20 is None else ("above" if close >= ma20 else "below"),
        "price_vs_ma60": None if close is None or ma60 is None else ("above" if close >= ma60 else "below"),
        "ma20_vs_ma60": None if ma20 is None or ma60 is None else ("bull" if ma20 >= ma60 else "bear"),
        "ma60_vs_ma120": None if ma60 is None or ma120 is None else ("bull" if ma60 >= ma120 else "bear"),
        "rsi_zone": rsi_zone,
        "macd": None if dif is None or sig is None else ("bull" if dif >= sig else "bear"),
        "kd": None if k is None or d is None else ("K>D" if k >= d else "K<D"),
        "volume": None if vr is None else ("surge" if vr >= 1.5 else "normal"),
        "breakout20": bool(row.get("帶量突破", False)) if not pd.isna(row.get("帶量突破", False)) else False,
    }


LABELS = {
    "price_vs_ma20": ("收盤價相對 MA20", {"above":"站上 MA20", "below":"跌破 MA20"}),
    "price_vs_ma60": ("收盤價相對 MA60", {"above":"站上 MA60", "below":"跌破 MA60"}),
    "ma20_vs_ma60": ("MA20 / MA60", {"bull":"MA20 上穿/位於 MA60 上方", "bear":"MA20 下穿/位於 MA60 下方"}),
    "ma60_vs_ma120": ("MA60 / MA120", {"bull":"MA60 位於 MA120 上方", "bear":"MA60 位於 MA120 下方"}),
    "rsi_zone": ("RSI14 區間", {}),
    "macd": ("MACD", {"bull":"DIF 位於訊號線上方", "bear":"DIF 位於訊號線下方"}),
    "kd": ("KD", {"K>D":"K 位於 D 上方", "K<D":"K 位於 D 下方"}),
    "volume": ("成交量", {"surge":"量比達 1.5 倍", "normal":"量比回到 1.5 倍以下"}),
    "breakout20": ("20 日突破", {True:"帶量突破前 20 日高點", False:"不再符合帶量突破"}),
}


def detect_events(old: dict, new: dict) -> list[str]:
    events = []
    if not old:
        return events  # first run establishes baseline; no false historical alerts
    for key, new_value in new.items():
        old_value = old.get(key)
        if new_value is None or old_value is None or new_value == old_value:
            continue
        label, mapping = LABELS[key]
        old_text = mapping.get(old_value, str(old_value))
        new_text = mapping.get(new_value, str(new_value))
        events.append(f"{label}：{old_text} → {new_text}")
    return events


def fetch_fundamentals():
    start = (datetime.now(TZ)-timedelta(days=900)).strftime("%Y-%m-%d")
    rev = finmind("TaiwanStockMonthRevenue", start)
    chips = finmind("TaiwanStockInstitutionalInvestorsBuySell", (datetime.now(TZ)-timedelta(days=90)).strftime("%Y-%m-%d"))
    fin = finmind("TaiwanStockFinancialStatements", (datetime.now(TZ)-timedelta(days=900)).strftime("%Y-%m-%d"))
    if not rev.empty:
        rev["date"] = pd.to_datetime(rev["date"])
        rev = rev.sort_values("date")
        rev["revenue"] = pd.to_numeric(rev["revenue"], errors="coerce")
        rev["MoM_pct"] = rev["revenue"].pct_change()*100
        rev["YoY_pct"] = rev["revenue"].pct_change(12)*100
    if not chips.empty:
        chips["date"] = pd.to_datetime(chips["date"])
        chips["buy"] = pd.to_numeric(chips["buy"], errors="coerce")
        chips["sell"] = pd.to_numeric(chips["sell"], errors="coerce")
        chips["net"] = chips["buy"] - chips["sell"]
    if not fin.empty:
        fin["date"] = pd.to_datetime(fin["date"])
    return rev, fin, chips


def line_push(text: str):
    if not LINE_TOKEN or not LINE_USER_ID:
        log.info("LINE credentials not set; skip LINE push.")
        return
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"},
        json={"to": LINE_USER_ID, "messages":[{"type":"text","text":text[:4900]}]},
        timeout=25,
    )
    r.raise_for_status()


def web_push(text: str, url: str, category: str = "daily"):
    """Fetch household device subscriptions from Cloudflare Worker and honor per-device preferences."""
    if not (PUSH_API_BASE and PUSH_ADMIN_TOKEN and VAPID_PRIVATE_KEY and VAPID_CLAIMS_SUB):
        log.info("Multi-user Web Push not configured; skip.")
        return
    try:
        from pywebpush import webpush, WebPushException
        r = requests.get(f"{PUSH_API_BASE}/admin/devices",
                         headers={"Authorization": f"Bearer {PUSH_ADMIN_TOKEN}"}, timeout=20)
        r.raise_for_status()
        devices = r.json().get("devices", [])
        sent = 0
        for device in devices:
            try:
                prefs = json.loads(device.get("preferences_json") or "{}")
                if not prefs.get(category, False):
                    continue
                sub = json.loads(device["subscription_json"])
                webpush(subscription_info=sub,
                        data=json.dumps({"title":"台積電 2330 追蹤提醒","body":text[:180],"url":url},ensure_ascii=False),
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub":VAPID_CLAIMS_SUB})
                sent += 1
            except WebPushException as e:
                log.warning("Web Push failed for device %s: %s",device.get("device_id","?")[:8],e)
            except Exception:
                log.exception("Failed to push to one device")
        log.info("Web Push category=%s sent=%s devices=%s",category,sent,len(devices))
    except Exception:
        log.exception("Multi-user Web Push processing failed")


def build_excel(prices, rev, fin, chips):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.chart import LineChart, Reference
    path = OUTPUT / "2330_TSMC_Tracker.xlsx"
    wb = Workbook()
    dash = wb.active
    dash.title = "Dashboard"
    dash.append(["台積電 2330｜雲端每日追蹤"])
    dash.append(["最新交易日", str(prices.index[-1].date())])
    row = prices.iloc[-1]
    for label, key in [("收盤價","收盤"),("MA20","MA20"),("MA60","MA60"),("MA120","MA120"),("RSI14","RSI14"),("DIF","DIF"),("MACD訊號","MACD訊號"),("MACD柱","MACD柱"),("K","K"),("D","D"),("ATR14","ATR14"),("量比","量比")]:
        dash.append([label, None if pd.isna(row[key]) else float(row[key])])
    chart = LineChart()
    chart.title = "收盤價與均線"
    chart.y_axis.title = "價格（元）"
    chart.x_axis.title = "日期"
    chart.height, chart.width = 8, 18
    ws = wb.create_sheet("技術指標")
    out = prices.reset_index()
    for r in [list(out.columns)] + out.replace({np.nan: None}).values.tolist():
        ws.append([v.to_pydatetime() if isinstance(v, pd.Timestamp) else (None if pd.isna(v) else (v.item() if isinstance(v, np.generic) else v)) for v in r])
    headers = list(out.columns)
    for col_name in ["收盤","MA20","MA60","MA120"]:
        col = headers.index(col_name)+1
        chart.add_data(Reference(ws, min_col=col, max_col=col, min_row=1, max_row=ws.max_row), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=ws.max_row))
    dash.add_chart(chart, "D2")
    for name, df in [("月營收", rev), ("季財報原始資料", fin), ("三大法人", chips)]:
        sh = wb.create_sheet(name)
        if df.empty:
            sh.append(["目前無資料／請確認 FinMind Token 與資料集"])
        else:
            df2 = df.copy()
            for c in df2.columns:
                if pd.api.types.is_datetime64_any_dtype(df2[c]):
                    df2[c] = df2[c].dt.strftime("%Y-%m-%d")
            sh.append(list(df2.columns))
            for vals in df2.replace({np.nan: None}).values.tolist():
                sh.append([v.item() if isinstance(v, np.generic) else v for v in vals])
    logws = wb.create_sheet("說明")
    logws.append(["資料來源","說明"])
    logws.append(["行情","Yahoo Finance yfinance；非即時資料，可能延遲或缺漏"])
    logws.append(["基本面/籌碼","FinMind API；請確認公告日期、欄位與單位"])
    logws.append(["技術訊號","只作研究提醒，不是自動下單指令"])
    for sh in wb.worksheets:
        sh.freeze_panes = "A2"
        sh.sheet_view.showGridLines = False
        for cell in sh[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17365D")
        for col in sh.columns:
            letter = get_column_letter(col[0].column)
            sh.column_dimensions[letter].width = min(max(14, max(len(str(c.value or "")) for c in col[:150])+2), 28)
    wb.save(path)
    return path


def main():
    global DOCS, DATA, OUTPUT, RUN_MODE
    parser = argparse.ArgumentParser(description="台積電 2330 每日追蹤")
    parser.add_argument("--mode", choices=["local", "cloud"], default="local",
                        help="local=本機測試且不推播；cloud=正式輸出並允許推播")
    parser.add_argument("--send-notifications", action="store_true",
                        help="本機測試時也發送通知（需明確指定）")
    args = parser.parse_args()
    RUN_MODE = args.mode
    if RUN_MODE == "local":
        local_root = ROOT / "local_test"
        DOCS, DATA, OUTPUT = local_root / "docs", local_root / "data", local_root / "output"
    else:
        DOCS, DATA, OUTPUT = ROOT / "docs", ROOT / "data", ROOT / "output"
    for folder in (DOCS, DATA, OUTPUT):
        folder.mkdir(parents=True, exist_ok=True)

    now = datetime.now(TZ)
    prices = indicators(get_prices())
    latest = prices.iloc[-1]
    trade_date = prices.index[-1].strftime("%Y-%m-%d")
    if (now.date() - prices.index[-1].date()).days > 5:
        raise RuntimeError(f"行情日期過舊：{trade_date}，停止通知。")

    rev, fin, chips = fetch_fundamentals()
    state_path = DATA / "indicator_state.json"
    old_state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}
    new_state = current_states(latest)
    events = detect_events(old_state.get("states", {}), new_state)

    def fmt(key, digits=2):
        v = latest.get(key)
        return "N/A" if pd.isna(v) else f"{float(v):,.{digits}f}"

    price = float(latest["收盤"])
    summary = (
        f"📊 台積電 2330｜{trade_date} 收盤分析\n"
        f"收盤：{price:,.2f}\n"
        f"MA5/20/60/120：{fmt('MA5')} / {fmt('MA20')} / {fmt('MA60')} / {fmt('MA120')}\n"
        f"RSI14：{fmt('RSI14')}｜DIF：{fmt('DIF')}｜MACD柱：{fmt('MACD柱')}\n"
        f"K/D：{fmt('K')} / {fmt('D')}｜ATR14：{fmt('ATR14')}｜量比：{fmt('量比')}\n"
        f"趨勢：{'多頭排列' if bool(latest.get('收盤',0) > latest.get('MA20',np.inf) > latest.get('MA60',np.inf) > latest.get('MA120',np.inf)) else '非完整多頭排列'}"
    )
    if events:
        summary += "\n\n🔔 今日技術指標狀態變化\n" + "\n".join(f"• {e}" for e in events)
    else:
        summary += "\n\n今日未偵測到指標狀態跨越／交叉事件。數值仍已更新至 Dashboard。"

    # Revenue alert only when latest published revenue changes and YoY falls sharply.
    revenue_alert = ""
    if not rev.empty:
        latest_rev = rev.iloc[-1]
        prev_rev_key = old_state.get("latest_revenue_date")
        rev_date = pd.Timestamp(latest_rev["date"]).strftime("%Y-%m-%d")
        yoy = latest_rev.get("YoY_pct")
        if rev_date != prev_rev_key and pd.notna(yoy):
            prev_yoy = old_state.get("latest_revenue_yoy")
            if yoy < 0 or (prev_yoy is not None and yoy <= prev_yoy - 10):
                revenue_alert = f"\n\n⚠️ 營收異常提醒：{rev_date} YoY {yoy:.2f}%"
            old_state["latest_revenue_date"] = rev_date
            old_state["latest_revenue_yoy"] = float(yoy)

    latest_json = {
        "symbol":"2330.TW", "name":"台積電", "trade_date":trade_date,
        "updated_at":now.isoformat(), "close":price,
        "change_pct":float((prices["收盤"].iloc[-1]/prices["收盤"].iloc[-2]-1)*100) if len(prices)>1 else None,
        "indicators":{k:safe_num(latest.get(k)) for k in ["MA5","MA20","MA60","MA120","RSI14","DIF","MACD訊號","MACD柱","K","D","ATR14","MA20乖離率%","量比"]},
        "states":new_state, "events":events, "revenue_alert":revenue_alert.strip(),
        "revenue_latest": None if rev.empty else {
            "date":pd.Timestamp(rev.iloc[-1]["date"]).strftime("%Y-%m-%d"),
            "revenue":safe_num(rev.iloc[-1].get("revenue")),
            "yoy_pct":safe_num(rev.iloc[-1].get("YoY_pct")),
            "mom_pct":safe_num(rev.iloc[-1].get("MoM_pct")),
        },
        "chips_latest": None if chips.empty else chips.tail(8).to_dict(orient="records"),
        "history":[{"date":idx.strftime("%Y-%m-%d"),"open":safe_num(r["開盤"]),"high":safe_num(r["最高"]),"low":safe_num(r["最低"]),"close":safe_num(r["收盤"]),"volume":safe_num(r["成交量"]),"ma5":safe_num(r["MA5"]),"ma20":safe_num(r["MA20"]),"ma60":safe_num(r["MA60"]),"ma120":safe_num(r["MA120"])} for idx,r in prices.tail(240).iterrows()],
        "data_status":{
            "finmind_token_configured":bool(FINMIND_TOKEN),
            "revenue_rows":len(rev), "financial_rows":len(fin), "chips_rows":len(chips),
            "note":"Yahoo Finance 行情非即時；FinMind 欄位以來源公告為準。"
        }
    }
    (DOCS/"latest.json").write_text(json.dumps(latest_json, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    prices.tail(500).to_csv(DATA/"price_history.csv", encoding="utf-8-sig")
    if not rev.empty: rev.to_csv(DATA/"revenue.csv", index=False, encoding="utf-8-sig")
    if not fin.empty: fin.to_csv(DATA/"financials_raw.csv", index=False, encoding="utf-8-sig")
    if not chips.empty: chips.to_csv(DATA/"chips.csv", index=False, encoding="utf-8-sig")
    build_excel(prices, rev, fin, chips)
    state_path.write_text(json.dumps({"trade_date":trade_date,"states":new_state,
        "latest_revenue_date":old_state.get("latest_revenue_date"),
        "latest_revenue_yoy":old_state.get("latest_revenue_yoy")}, ensure_ascii=False, indent=2), encoding="utf-8")

    full_message = summary + revenue_alert + "\\n\\n📱 手機 Dashboard：請使用你的 GitHub Pages 網址"
    # Local runs are safe by default: no LINE/Web Push and no cloud-state overwrite.
    if RUN_MODE == "cloud" or args.send_notifications:
        line_push(full_message)
        if events:
            web_push("；".join(events), "./", "technical")
        if revenue_alert:
            web_push(revenue_alert, "./", "revenue")
        web_push(f"台積電收盤 {price:,.2f}，每日分析已更新。", "./", "daily")
    else:
        log.info("Local test mode: notifications suppressed.")
    print(f"更新完成 [{RUN_MODE}]：{trade_date} close={price:.2f}; events={len(events)}; revenue={len(rev)}; chips={len(chips)}")


if __name__ == "__main__":
    main()
