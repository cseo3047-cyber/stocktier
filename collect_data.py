#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 전 종목 데이터 수집 v3.1 (네이버 증권 모바일 API)
# 종목 + 지수(KOSPI/KOSDAQ/KPI200, 3개월 추이) + 업종 + 테마 + 외인·기관 순매수
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


def idx_hist(symbol, count=70):
    """지수 일별 시세 (fchart): [고가, 저가, 종가] 리스트"""
    try:
        r = S.get(f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count={count}&requestType=0",
                  timeout=15)
        rows = re.findall(r'data="([^"]+)"', r.text)
        out = []
        for row in rows:
            p = row.split("|")
            if len(p) >= 5 and num(p[4]):
                out.append([round(float(num(p[2]) or 0), 2),
                            round(float(num(p[3]) or 0), 2),
                            round(float(p[4]), 2)])
        return out
    except Exception:
        return []


def market_extra():
    """지수(+3개월 추이) + 업종 + 테마"""
    mk = {}
    for sym, key in (("KOSPI", "kospi"), ("KOSDAQ", "kosdaq"), ("KPI200", "kpi200")):
        j = get_json(f"https://m.stock.naver.com/api/index/{sym}/basic")
        h = idx_hist(sym)
        o = {}
        if j:
            o = {"price": num(j.get("closePrice")),
                 "chg": num(j.get("compareToPreviousClosePrice")),
                 "ratio": num(j.get("fluctuationsRatio"))}
        elif len(h) >= 2:
            prev, cur = h[-2][2], h[-1][2]
            o = {"price": cur, "chg": round(cur - prev, 2),
                 "ratio": round((cur - prev) / prev * 100, 2) if prev else 0.0}
        if o:
            if h:
                o["high"], o["low"] = h[-1][0], h[-1][1]
                o["hist"] = [x[2] for x in h]
            mk[key] = o

    def groups(kind, keep):
        j = get_json(f"https://m.stock.naver.com/api/stocks/{kind}?page=1&pageSize=100")
        out = []
        for g in (j or {}).get("groups", []):
            out.append([str(g.get("name") or ""), num(g.get("changeRate")) or 0.0,
                        int(g.get("riseCount") or 0), int(g.get("fallCount") or 0),
                        int(g.get("totalCount") or 0)])
        return out[:keep]

    mk["upjong"] = groups("upjong", 100)
    mk["theme"] = groups("theme", 30)
    print("지수:", [k for k in mk if k not in ("upjong", "theme")],
          "/ 업종", len(mk.get("upjong", [])), "/ 테마", len(mk.get("theme", [])), flush=True)
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
            r1w, r1m, r3m, fbuy, obuy,
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
        fp.write("window.STOCK_MARKET=" + json.dumps(market, ensure_ascii=False,
                                                     separators=(",", ":")) + ";\n")
        fp.write("window.STOCK_DB=" + json.dumps(out, ensure_ascii=False,
                                                 separators=(",", ":")) + ";\n")
    print("완료:", len(out), "종목 → data.js (fchart 성공:", fchart_ok, ")")


if __name__ == "__main__":
    main()
