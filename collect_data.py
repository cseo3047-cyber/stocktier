#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 전 종목 데이터 수집 v3 (네이버 증권 모바일 API)
# 종목 + 지수(KOSPI/KOSDAQ) + 업종별 등락 + 테마 + 외인·기관 순매수
# 결과물: data.js
import json
import re
import sys
import time
import datetime

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept": "application/json",
}
S = requests.Session()
S.headers.update(HEADERS)


def get_json(url, tries=3):
    for i in range(tries):
        try:
            r = S.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1.0 + i)
    return None


def num(s):
    """'22.47배' '46.55%' '12,372원' '-18,500' '+971,031' 'N/A' → float 또는 None"""
    if s is None:
        return None
    s = str(s).replace(",", "").replace("배", "").replace("%", "").replace("원", "").replace("+", "").strip()
    if s in ("", "N/A", "-", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def listing(market):
    out = []
    page = 1
    while page <= 40:
        j = get_json(f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100")
        if not j or not j.get("stocks"):
            break
        for s in j["stocks"]:
            if s.get("stockEndType") != "stock":
                continue
            out.append({
                "code": s["itemCode"],
                "name": str(s["stockName"]).strip(),
                "mkt": market,
                "price": int(num(s.get("closePriceRaw") or s.get("closePrice")) or 0),
                "chg": num(s.get("fluctuationsRatio")) or 0.0,
                "volToday": int(num(s.get("accumulatedTradingVolumeRaw") or s.get("accumulatedTradingVolume")) or 0),
                "cap": int((num(s.get("marketValueRaw")) or 0) / 1e8),
            })
        total = j.get("totalCount", 0)
        if page * 100 >= total:
            break
        page += 1
        time.sleep(0.1)
    print(market, "목록:", len(out), flush=True)
    return out


def detail(code):
    """PER/PBR/배당/외인지분 + 직전 4일 등락 + 전일 거래량 + 외인·기관 순매수"""
    j = get_json(f"https://m.stock.naver.com/api/stock/{code}/integration")
    if not j:
        return None
    info = {i.get("code"): i.get("value") for i in (j.get("totalInfos") or [])}
    per = num(info.get("per")) or 0.0
    pbr = num(info.get("pbr")) or 0.0
    div = num(info.get("dividendYieldRatio")) or 0.0
    eps, bps = num(info.get("eps")), num(info.get("bps"))
    roe = round(eps / bps * 100, 1) if (eps is not None and bps and bps > 0) else 0.0
    forn = num(info.get("foreignRate"))
    trends = j.get("dealTrendInfos") or []
    prevs, vol_prev = [], None
    for d in trends[:4]:
        close, cmpv = num(d.get("closePrice")), num(d.get("compareToPreviousClosePrice"))
        if close is not None and cmpv is not None and (close - cmpv) != 0:
            prevs.append(round(cmpv / (close - cmpv) * 100, 2))
        else:
            prevs.append(0.0)
        if vol_prev is None:
            vol_prev = int(num(d.get("accumulatedTradingVolume")) or 0)
    fbuy = obuy = None
    if trends:
        f0 = num(trends[0].get("foreignerPureBuyQuant"))
        o0 = num(trends[0].get("organPureBuyQuant"))
        fbuy = int(f0) if f0 is not None else None
        obuy = int(o0) if o0 is not None else None
    return per, pbr, div, roe, forn, prevs, vol_prev, fbuy, obuy


def history(code, count=70):
    try:
        r = S.get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0",
                  timeout=15)
        rows = re.findall(r'data="([^"]+)"', r.text)
        closes, vols = [], []
        for row in rows:
            p = row.split("|")
            if len(p) >= 6 and num(p[4]) and num(p[4]) > 0:
                closes.append(float(p[4]))
                vols.append(float(p[5]) if num(p[5]) is not None else 0.0)
        return closes, vols
    except Exception:
        return [], []


def market_extra():
    """지수 + 업종 + 테마"""
    mk = {}
    for idx in ("KOSPI", "KOSDAQ"):
        j = get_json(f"https://m.stock.naver.com/api/index/{idx}/basic")
        if j:
            mk[idx.lower()] = {
                "price": num(j.get("closePrice")),
                "chg": num(j.get("compareToPreviousClosePrice")),
                "ratio": num(j.get("fluctuationsRatio")),
            }

    def groups(kind, keep):
        j = get_json(f"https://m.stock.naver.com/api/stocks/{kind}?page=1&pageSize=100")
        out = []
        for g in (j or {}).get("groups", []):
            out.append([str(g.get("name") or ""), num(g.get("changeRate")) or 0.0,
                        int(g.get("riseCount") or 0), int(g.get("fallCount") or 0),
                        int(g.get("totalCount") or 0)])
        return out[:keep]

    mk["upjong"] = groups("upjong", 100)   # 등락률 내림차순 전체(79개)
    mk["theme"] = groups("theme", 30)      # 상위 30개 테마
    print("지수:", list(mk.keys()), "/ 업종", len(mk.get("upjong", [])), "/ 테마", len(mk.get("theme", [])), flush=True)
    return mk


def main():
    stocks = listing("KOSPI") + listing("KOSDAQ")
    if len(stocks) < 100:
        sys.exit("종목 목록 수집 실패: " + str(len(stocks)))

    market = market_extra()

    out = {}
    fchart_ok = 0
    for i, st in enumerate(stocks):
        d = detail(st["code"])
        if d is None:
            continue
        per, pbr, div, roe, forn, prevs, vol_prev, fbuy, obuy = d

        closes, vols = history(st["code"])
        if closes:
            fchart_ok += 1
            vol3m = int(sum(vols) / len(vols))

            def ret(n):
                if len(closes) >= n and closes[-n] > 0:
                    return 
