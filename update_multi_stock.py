#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a multi-market stock snapshot for Stock Monitor V3.0.

The existing update_tsmc_tracker.py remains the source of truth for TSMC's
original fundamentals/chip data and technical indicator calculations.
"""
from __future__ import annotations
import os, json, logging, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import update_tsmc_tracker as core

ROOT=Path(__file__).resolve().parent
DOCS=ROOT/"docs"
TZ=ZoneInfo("Asia/Taipei")
API_BASE=os.getenv("PUSH_API_BASE","").strip().rstrip("/")
ADMIN_TOKEN=os.getenv("PUSH_ADMIN_TOKEN","").strip()
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("multi-stock")

def get_watchlist():
    rows=[]
    if API_BASE and ADMIN_TOKEN:
        try:
            r=requests.get(f"{API_BASE}/admin/watchlists",headers={"Authorization":f"Bearer {ADMIN_TOKEN}"},timeout=20)
            r.raise_for_status()
            rows=r.json().get("items",[])
        except Exception as e:
            log.warning("Could not load remote watchlists (%s); using built-in TSMC fallback.",e)
    # TSMC remains pinned so the original V2.3 dashboard/data logic is retained.
    unique={("2330","TW"):{"symbol":"2330","market":"TW","display_name":"台積電"}}
    for x in rows:
        sym=str(x.get("symbol","")).strip().upper()
        market="US" if x.get("market")=="US" else "TW"
        if not re.fullmatch(r"[A-Z0-9.^_-]{1,15}",sym): continue
        unique[(sym,market)]={"symbol":sym,"market":market,"display_name":str(x.get("display_name") or sym)[:40]}
    return list(unique.values())

def ticker_for(item):
    sym=item["symbol"]
    if item["market"]=="US": return sym
    if sym.endswith(".TW") or sym.endswith(".TWO"): return sym
    # Optional explicit exchange suffix can be entered; otherwise listed Taiwan shares default to TWSE.
    return sym+".TW"

def load_one(item):
    ticker=ticker_for(item)
    raw=yf.download(ticker,period="2y",interval="1d",auto_adjust=True,progress=False,threads=False)
    if raw.empty: raise RuntimeError(f"{ticker}: Yahoo Finance returned no data")
    if isinstance(raw.columns,pd.MultiIndex): raw.columns=raw.columns.get_level_values(0)
    raw.index=pd.to_datetime(raw.index).tz_localize(None)
    raw.index.name="日期"
    raw=raw.rename(columns={"Open":"開盤","High":"最高","Low":"最低","Close":"收盤","Volume":"成交量"})
    raw=raw[["開盤","最高","最低","收盤","成交量"]].dropna(subset=["收盤"])
    calc=core.indicators(raw)
    last=calc.iloc[-1]
    if (datetime.now(TZ).date()-calc.index[-1].date()).days>7:
        raise RuntimeError(f"{ticker}: stale quote date {calc.index[-1].date()}")
    prev=calc["收盤"].iloc[-2] if len(calc)>1 else np.nan
    hist=[]
    for idx,row in calc.tail(240).iterrows():
        def n(v): return None if pd.isna(v) else float(v)
        hist.append({"date":idx.strftime("%Y-%m-%d"),"open":n(row["開盤"]),"high":n(row["最高"]),
          "low":n(row["最低"]),"close":n(row["收盤"]),"volume":n(row["成交量"]),
          "ma5":n(row["MA5"]),"ma20":n(row["MA20"]),"ma60":n(row["MA60"]),"ma120":n(row["MA120"])})
    indkeys=["MA5","MA20","MA60","MA120","RSI14","DIF","MACD訊號","MACD柱","K","D","ATR14","MA20乖離率%","量比"]
    inds={k:(None if pd.isna(last.get(k)) else float(last.get(k))) for k in indkeys}
    states=core.current_states(last)
    events=core.detect_events({},states)
    return {"symbol":item["symbol"],"ticker":ticker,"market":item["market"],"name":item["display_name"],
      "trade_date":calc.index[-1].strftime("%Y-%m-%d"),"updated_at":datetime.now(TZ).isoformat(),
      "close":float(last["收盤"]),"change_pct":None if pd.isna(prev) or prev==0 else float((last["收盤"]/prev-1)*100),
      "indicators":inds,"states":states,"events":events,"history":hist,
      "data_status":{"source":"Yahoo Finance via yfinance","note":"非即時行情；不同市場交易日與時區不同。"},
      "currency":"USD" if item["market"]=="US" else "TWD"}

def main():
    DOCS.mkdir(parents=True,exist_ok=True)
    watchlist=get_watchlist()
    results=[]
    failures=[]
    state_path=ROOT/"data"/"multi_stock_states.json"
    state_path.parent.mkdir(parents=True,exist_ok=True)
    old_states=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    new_states={}
    push_events=[]
    for item in watchlist:
        try:
            row=load_one(item)
            key=row["market"]+":"+row["symbol"]
            previous=old_states.get(key,{})
            row["events"]=core.detect_events(previous.get("states",{}),row["states"])
            new_states[key]={"trade_date":row["trade_date"],"states":row["states"]}
            if row["events"]:
                push_events.append(f'{row["name"]} {row["symbol"]}：'+"；".join(row["events"]))
            results.append(row)
            log.info("Updated %s %s",row["ticker"],row["trade_date"])
        except Exception as e:
            log.warning("Failed %s: %s",item,e)
            failures.append({"symbol":item["symbol"],"market":item["market"],"name":item["display_name"],"error":str(e)})
    if not any(x["symbol"]=="2330" and x["market"]=="TW" for x in results):
        raise RuntimeError("TSMC 2330 failed; refusing to publish incomplete multi-stock snapshot.")
    payload={"generated_at":datetime.now(TZ).isoformat(),"count":len(results),"stocks":results,"failures":failures,
      "note":"行情資料可能延遲或缺漏；個股技術指標只作研究參考。"}
    tmp=DOCS/"stocks.json.tmp"
    tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"),default=str),encoding="utf-8")
    tmp.replace(DOCS/"stocks.json")
    state_path.write_text(json.dumps(new_states,ensure_ascii=False,indent=2),encoding="utf-8")
    log.info("Published %d stocks; %d failures.",len(results),len(failures))

if __name__=="__main__":
    main()
