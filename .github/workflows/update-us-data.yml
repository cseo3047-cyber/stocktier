#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 미국 전 종목 데이터 수집 (네이버 증권 해외 API — 한글 종목명 포함)
# 결과물: data_us.js
import json
import sys
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept": "application/json",
}
S = requests.Session()
S.headers.update(HEADERS)

EXCHANGES = ["NASDAQ", "NYSE", "AMEX"]
TODAY = datetime.date.today()
START = (TODAY - datetime.timedelta(days=130)).strftime("%Y%m%d") + "000000"
END = TODAY.strftime("%Y%m%d") + "235959"


def get_json(url, tries=3):
    for i in range(tries):
        try:
            r = S.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(0.8 + i)
    return None


def num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("배", "").replace("%", "").strip()
    if s in ("", "N/A", "-", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def listing():
    out, seen = [], set()
    for ex in EXCHANGES:
        got = 0
        page = 1
        while page <= 80:
            j = get_json(f"https://api.stock.naver.com/stock/exchange/{ex}/marketValue?page={page}&pageSize=100")
            if not j or not j.get("stocks"):
                break
            for s in j["stocks"]:
                if s.get("stockEndType") != "stock":
                    continue
                rc, sym = s.get("reutersCode"), s.get("symbolCode")
                if not rc or not sym or sym in seen:
                    continue
                seen.add(sym)
                ind = s.get("industryCodeType") or {}
                out.append({
                    "reuters": rc, "sym": sym, "ex": ex,
                    "ko": str(s.get("stockName") or "").strip(),
                    "en": str(s.get("stockNameEng") or sym).strip(),
                    "cap": int((num(s.get("marketValueRaw")) or 0) / 1e8),   # 억 달러
                    "div": num(s.get("dividendYield")) or 0.0,
                    "industry": str(ind.get("industryGroupKor") or ""),
                })
                got += 1
            total = j.get("totalCount", 0)
            if page * 100 >= total:
                break
            page += 1
            time.sleep(0.05)
        print(ex, "목록:", got, flush=True)
    return out


def fetch_one(st):
    """차트(주가·거래량 이력) + basic(재무지표)"""
    rc = st["reuters"]
    chart = get_json(f"https://api.stock.naver.com/chart/foreign/item/{rc}/day?startDateTime={START}&endDateTime={END}")
    if not chart or not isinstance(chart, list) or len(chart) < 6:
        return None
    closes = [float(r["closePrice"]) for r in chart if r.get("closePrice")]
    vols = [int(r.get("accumulatedTradingVolume") or 0) for r in chart if r.get("closePrice")]
    if len(closes) < 6 or closes[-1] <= 0:
        return None

    days = []
    for i in range(1, 6):
        prev, cur = closes[-i - 1], closes[-i]
        days.append(round((cur - prev) / prev * 100, 2) if prev else 0.0)

    per = pbr = 0.0
    roe = 0.0
    div = st["div"]
    basic = get_json(f"https://api.stock.naver.com/stock/{rc}/basic")
    if basic:
        info = {i.get("code"): i.get("value") for i in (basic.get("stockItemTotalInfos") or [])}
        per = round(num(info.get("per")) or 0.0, 1)
        pbr = round(num(info.get("pbr")) or 0.0, 2)
        d2 = num(info.get("dividendYieldRatio"))
        if d2 is not None:
            div = d2
        eps, bps = num(info.get("eps")), num(info.get("bps"))
        if eps is not None and bps and bps > 0:
            roe = round(eps / bps * 100, 1)

    def ret(n):
        if len(closes) >= n and closes[-n] > 0:
            return round((closes[-1] - closes[-n]) / closes[-n] * 100, 1)
        return None

    last_date = str(chart[-1].get("localDate") or "")
    entry = [
        st["sym"], st["ex"], round(closes[-1], 2), days[0], per, pbr,
        round(div, 1), roe, st["cap"],
        int(sum(vols) / len(vols)), vols[-2], vols[-1],
        days, None, ret(6), ret(21), ret(len(closes)),
        st["en"],
    ]
    return st, entry, last_date


def main():
    stocks = listing()
    if len(stocks) < 500:
        sys.exit("미국 종목 목록 수집 실패: " + str(len(stocks)))
    print("전체 대상:", len(stocks), flush=True)

    out, alias = {}, {}
    base_date = ""
    done = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_one, st) for st in stocks]
        for f in as_completed(futures):
            try:
                r = f.result()
            except Exception:
                r = None
            done += 1
            if done % 500 == 0:
                print(f"{done}/{len(stocks)} 처리, 수집 성공 {len(out)}", flush=True)
            if not r:
                continue
            st, entry, last_date = r
            out[st["sym"]] = entry
            if st["ko"]:
                alias[st["ko"]] = st["sym"]
            if last_date > base_date:
                base_date = last_date

    if len(out) < 500:
        sys.exit("상세 수집 실패: " + str(len(out)))

    meta = {"date": base_date or TODAY.strftime("%Y%m%d"),
            "count": len(out),
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open("data_us.js", "w", encoding="utf-8") as fp:
        fp.write("window.STOCK_META_US=" + json.dumps(meta, ensure_ascii=False) + ";\n")
        fp.write("window.STOCK_DB_US=" + json.dumps(out, ensure_ascii=False,
                                                    separators=(",", ":")) + ";\n")
        fp.write("window.KO_ALIAS=" + json.dumps(alias, ensure_ascii=False,
                                                 separators=(",", ":")) + ";\n")
    print("완료:", len(out), "종목 / 한글명", len(alias), "개 → data_us.js")


if __name__ == "__main__":
    main()
