#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 전 종목 데이터 수집 (네이버 증권 모바일 API — 해외 서버에서도 동작)
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
    """'22.47배' '46.55%' '12,372원' '-18,500' 'N/A' → float 또는 None"""
    if s is None:
        return None
    s = str(s).replace(",", "").replace("배", "").replace("%", "").replace("원", "").strip()
    if s in ("", "N/A", "-", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def listing(market):
    """시가총액 순 전 종목 목록 (KOSPI 또는 KOSDAQ)"""
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
    """PER/PBR/배당/외인 + 직전 4거래일 등락률/전일 거래량"""
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
    prevs, vol_prev = [], None
    for d in (j.get("dealTrendInfos") or [])[:4]:
        close, cmpv = num(d.get("closePrice")), num(d.get("compareToPreviousClosePrice"))
        if close is not None and cmpv is not None and (close - cmpv) != 0:
            prevs.append(round(cmpv / (close - cmpv) * 100, 2))
        else:
            prevs.append(0.0)
        if vol_prev is None:
            vol_prev = int(num(d.get("accumulatedTradingVolume")) or 0)
    return per, pbr, div, roe, forn, prevs, vol_prev


def history(code, count=70):
    """일별 종가/거래량 (3개월). 실패하면 빈 리스트."""
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


def main():
    stocks = listing("KOSPI") + listing("KOSDAQ")
    if len(stocks) < 100:
        sys.exit("종목 목록 수집 실패: " + str(len(stocks)))

    out = {}
    fchart_ok = 0
    for i, st in enumerate(stocks):
        d = detail(st["code"])
        if d is None:
            continue
        per, pbr, div, roe, forn, prevs, vol_prev = d

        closes, vols = history(st["code"])
        if closes:
            fchart_ok += 1
            vol3m = int(sum(vols) / len(vols))

            def ret(n):
                if len(closes) >= n and closes[-n] > 0:
                    return round((closes[-1] - closes[-n]) / closes[-n] * 100, 1)
                return None
            r1w, r1m, r3m = ret(6), ret(21), ret(len(closes))
        else:
            vol3m = int((st["volToday"] + (vol_prev or st["volToday"])) / 2)
            r1w = r1m = r3m = None

        days = ([round(st["chg"], 2)] + prevs + [0.0] * 4)[:5]
        if vol_prev is None:
            vol_prev = vol3m

        out[st["name"]] = [
            st["code"], st["mkt"], st["price"], days[0], per, pbr, div, roe,
            st["cap"], vol3m, vol_prev, st["volToday"], days, forn,
            r1w, r1m, r3m,
        ]
        if (i + 1) % 200 == 0:
            print(f"{i+1}/{len(stocks)} 처리, fchart 성공 {fchart_ok}", flush=True)
        time.sleep(0.05)

    if len(out) < 100:
        sys.exit("상세 수집 실패: " + str(len(out)))

    meta = {"date": datetime.date.today().strftime("%Y%m%d"),
            "count": len(out),
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open("data.js", "w", encoding="utf-8") as fp:
        fp.write("window.STOCK_META=" + json.dumps(meta, ensure_ascii=False) + ";\n")
        fp.write("window.STOCK_DB=" + json.dumps(out, ensure_ascii=False,
                                                 separators=(",", ":")) + ";\n")
    print("완료:", len(out), "종목 → data.js (fchart 성공:", fchart_ok, ")")


if __name__ == "__main__":
    main()
