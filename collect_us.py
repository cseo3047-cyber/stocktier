#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 미국 전 종목 데이터 수집 (네이버 증권 해외 API — 한글 종목명 포함)
# 결과물: data_us.js
import json
import re
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
START = (TODAY - datetime.timedelta(days=1850)).strftime("%Y%m%d") + "000000"   # 5년치
IDX_START = START
END = TODAY.strftime("%Y%m%d") + "235959"


def idx_us(code):
    """미국 지수: basic + 5년 일별 차트"""
    o = {}
    j = get_json(f"https://api.stock.naver.com/index/{code}/basic")
    if j:
        o = {"price": num(j.get("closePrice")),
             "chg": num(j.get("compareToPreviousClosePrice")),
             "ratio": num(j.get("fluctuationsRatio"))}
    chart = get_json(f"https://api.stock.naver.com/chart/foreign/index/{code}/day?startDateTime={IDX_START}&endDateTime={END}")
    if chart and isinstance(chart, list) and len(chart) >= 2:
        closes, dates, vols = [], [], []
        for r in chart:
            c = r.get("closePrice")
            if not c:
                continue
            closes.append(round(float(c), 2))
            dates.append(str(r.get("localDate") or "")[4:])
            vols.append(int(r.get("accumulatedTradingVolume") or 0))
        if closes:
            if not o and len(closes) > 1:
                prev, cur = closes[-2], closes[-1]
                o = {"price": cur, "chg": round(cur - prev, 2),
                     "ratio": round((cur - prev) / prev * 100, 2) if prev else 0.0}
            o["hist"], o["hdates"], o["vhist"] = closes, dates, vols
            o["high"] = round(float(chart[-1].get("highPrice") or 0), 2)
            o["low"] = round(float(chart[-1].get("lowPrice") or 0), 2)
    return o


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
    rc = closes[-65:]          # 최근 3개월 (지표 계산용)
    rv = vols[-65:]

    days = []
    for i in range(1, 6):
        prev, cur = closes[-i - 1], closes[-i]
        days.append(round((cur - prev) / prev * 100, 2) if prev else 0.0)

    # 장기 차트: 5년치를 100개 점으로 압축 (현재가=1000 기준 상대값)
    spk = None
    if len(closes) >= 10:
        step = max(1, len(closes) // 100)
        pts = closes[::step][-100:]
        last = pts[-1] or 1
        spk = [int(round(p / last * 1000)) for p in pts]

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
        if len(rc) >= n and rc[-n] > 0:
            return round((rc[-1] - rc[-n]) / rc[-n] * 100, 1)
        return None

    last_date = str(chart[-1].get("localDate") or "")
    entry = [
        st["sym"], st["ex"], round(closes[-1], 2), days[0], per, pbr,
        round(div, 1), roe, st["cap"],
        int(sum(rv) / len(rv)), vols[-2], vols[-1],
        days, None, ret(6), ret(21), ret(len(rc)),
        st["en"], spk,
    ]
    return st, entry, last_date


def earn_us():
    """실적 발표 예정일 (나스닥 공식 캘린더 API, 향후 40일)"""
    hd = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
          "Accept": "application/json, text/plain, */*",
          "Origin": "https://www.nasdaq.com",
          "Referer": "https://www.nasdaq.com/"}
    out = {}
    ok = 0
    for i in range(40):
        d = TODAY + datetime.timedelta(days=i)
        if d.weekday() >= 5:          # 주말 제외
            continue
        ds = d.strftime("%Y-%m-%d")
        try:
            r = requests.get("https://api.nasdaq.com/api/calendar/earnings?date=" + ds,
                             headers=hd, timeout=15)
            if r.status_code != 200:
                if ok == 0 and i < 3:
                    print("[진단] 나스닥 캘린더 status=", r.status_code, flush=True)
                continue
            rows = ((r.json().get("data") or {}).get("rows")) or []
            for row in rows:
                sym = str(row.get("symbol") or "").strip().upper()
                if sym:
                    out.setdefault(sym, d.strftime("%Y%m%d"))
            ok += 1
        except Exception as e:
            if ok == 0 and i < 3:
                print("[진단] 나스닥 캘린더 실패:", str(e)[:100], flush=True)
        time.sleep(0.4)
    print("실적 일정(미국):", len(out), "종목 /", ok, "일 성공", flush=True)
    return out


def sec_filings(symbols):
    """SEC EDGAR 일별 공시 (무료 공개, 키 불필요) — 커버 종목만, 30일 누적 → dart_us.js"""
    hd = {"User-Agent": "Stocktier data collector (contact: cseo3047@gmail.com)"}
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=hd, timeout=20)
        tk = {str(v["cik_str"]): str(v["ticker"]).upper() for v in r.json().values()}
    except Exception as e:
        print("[진단] SEC 티커맵 실패:", str(e)[:100], flush=True)
        return
    FORMS = {
        "10-K": ("실적 보고", 3, 0), "10-Q": ("실적 보고", 3, 0),
        "8-K": ("주요 사건", 3, 0), "6-K": ("주요 사건", 2, 0),
        "S-1": ("증권 발행", 4, -1), "S-3": ("증권 발행", 4, -1), "424B5": ("증권 발행", 3, -1),
        "SC 13D": ("지분 공시", 3, 1), "SC 13G": ("지분 공시", 2, 0),
    }

    def fetch_day(d):
        ds = d.strftime("%Y%m%d")
        q = (d.month - 1) // 3 + 1
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{q}/form.{ds}.idx"
        try:
            r2 = requests.get(url, headers=hd, timeout=20)
            if r2.status_code != 200:
                return []
            items = []
            for line in r2.text.splitlines():
                parts = re.split(r"\s{2,}", line.strip())
                if len(parts) < 5:
                    continue
                form, comp, cik, _fd, fname = parts[0].strip().upper(), parts[1].strip(), parts[2].strip(), parts[3], parts[4].strip()
                key = None
                for fk in FORMS:
                    if form == fk or form == fk + "/A":
                        key = fk
                        break
                if not key:
                    continue
                sym = tk.get(cik)
                if not sym or sym not in symbols:
                    continue
                ty, imp, tone = FORMS[key]
                acc = fname.split("/")[-1].replace(".txt", "")
                link = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-','')}/{acc}-index.htm"
                items.append([comp[:40], sym, ty, form + " — " + comp[:60], imp, tone, link, "US"])
            return items[:400]
        except Exception as e:
            print("[진단] SEC idx 실패:", ds, str(e)[:80], flush=True)
            return []

    store = {}
    try:
        with open("dart_us.js", encoding="utf-8") as f2:
            m = re.search(r"window\.STOCK_DART_US=(\{.*\});", f2.read(), re.S)
            if m:
                store = json.loads(m.group(1))
    except Exception:
        store = {}
    d0 = datetime.date.today()
    fetched = 0
    for back in range(30):
        d = d0 - datetime.timedelta(days=back)
        if d.weekday() >= 5:
            continue
        ds = d.strftime("%Y%m%d")
        if ds in store and back >= 2:
            continue
        store[ds] = fetch_day(d)
        fetched += 1
        time.sleep(0.4)
    cutoff = (d0 - datetime.timedelta(days=30)).strftime("%Y%m%d")
    store = {k: v for k, v in store.items() if k >= cutoff}
    with open("dart_us.js", "w", encoding="utf-8") as f2:
        f2.write("window.STOCK_DART_US=" + json.dumps(store, ensure_ascii=False,
                                                      separators=(",", ":")) + ";\n")
    print("SEC 공시 누적:", sum(len(v) for v in store.values()), "건 /", len(store),
          "일 (신규", fetched, "일) → dart_us.js", flush=True)


def main():
    stocks = listing()
    if len(stocks) < 500:
        sys.exit("미국 종목 목록 수집 실패: " + str(len(stocks)))
    print("전체 대상:", len(stocks), flush=True)

    # 미국 지수 (다우/S&P500/나스닥)
    market = {}
    for code, key in ((".DJI", "dji"), (".INX", "inx"), (".IXIC", "ixic")):
        d = idx_us(code)
        if d:
            market[key] = d
    print("미국 지수:", list(market.keys()), flush=True)

    # 미국 뉴스 (네이버 API 시도 → 실패 시 언론사 공식 RSS 폴백)
    def rss_news(feeds, n=8):
        import html as _h
        mon = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
               "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
        hd = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        for url, office in feeds:
            try:
                r = requests.get(url, headers=hd, timeout=15)
                if r.status_code != 200:
                    print("[진단] RSS status=", r.status_code, url[:60], flush=True)
                    continue
                out = []
                for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
                    tmt = re.search(r"<title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>", it, re.S)
                    lmt = re.search(r"<link>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</link>", it, re.S)
                    dmt = re.search(r"(\d{1,2}) ([A-Za-z]{3}) \d{4} (\d{2}):(\d{2})", it)
                    if not tmt or not lmt:
                        continue
                    t = _h.unescape(re.sub(r"<[^>]+>", "", tmt.group(1))).strip()
                    u = lmt.group(1).strip()
                    tm2 = f"{mon.get(dmt.group(2), '01')}/{int(dmt.group(1)):02d} {dmt.group(3)}:{dmt.group(4)}" if dmt else ""
                    if t and u.startswith("http"):
                        out.append([t, office, tm2, u, "해외"])
                    if len(out) >= n:
                        break
                if out:
                    print("RSS 뉴스:", len(out), "건 ←", office, flush=True)
                    return out
            except Exception as e:
                print("[진단] RSS 실패:", str(e)[:100], url[:60], flush=True)
        return []

    def news_us():
        import html as _h
        for url in ("https://api.stock.naver.com/news/worldStock/mainnews?page=1&pageSize=12",
                    "https://m.stock.naver.com/api/news/worldMainnews?page=1&pageSize=12"):
            j = get_json(url)
            if not j:
                continue
            groups = j if isinstance(j, list) else ([j] if isinstance(j, dict) else [])
            out = []
            try:
                for grp in groups:
                    for it in (grp.get("items", []) if isinstance(grp, dict) else []):
                        t = _h.unescape(str(it.get("titleFull") or it.get("title") or "")).strip()
                        u = str(it.get("mobileNewsUrl") or it.get("linkUrl") or "")
                        dt = str(it.get("datetime") or "")
                        tm = f"{dt[4:6]}/{dt[6:8]} {dt[8:10]}:{dt[10:12]}" if len(dt) >= 12 else ""
                        if t and u:
                            out.append([t, str(it.get("officeName") or ""), tm, u])
                        if len(out) >= 8:
                            break
                    if len(out) >= 8:
                        break
            except Exception as e:
                print("[진단] 미국 뉴스 파싱 실패:", str(e)[:120], flush=True)
            if out:
                print("미국 뉴스:", len(out), "건", flush=True)
                return out
        out = rss_news([
            ("https://www.hankyung.com/feed/international", "한국경제"),
            ("https://www.mk.co.kr/rss/30300018/", "매일경제"),
            ("https://www.yna.co.kr/rss/international.xml", "연합뉴스"),
        ])
        if not out:
            print("[진단] 미국 뉴스 수집 실패 (API·RSS 모두)", flush=True)
        return out

    market["news"] = news_us()
    market["earn"] = earn_us()

    out, alias, ind = {}, {}, {}
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
            if st.get("industry"):
                ind.setdefault(st["industry"], []).append(entry[3])
            if last_date > base_date:
                base_date = last_date

    # 업종별 등락 집계 (종목 3개 이상인 업종만)
    upjong = sorted(
        [[k, round(sum(v) / len(v), 2),
          sum(1 for c in v if c > 0), sum(1 for c in v if c < 0), len(v)]
         for k, v in ind.items() if k and len(v) >= 3],
        key=lambda x: -x[1])
    market["upjong"] = upjong
    print("미국 업종:", len(upjong), "개", flush=True)

    if len(out) < 500:
        sys.exit("상세 수집 실패: " + str(len(out)))

    meta = {"date": base_date or TODAY.strftime("%Y%m%d"),
            "count": len(out),
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open("data_us.js", "w", encoding="utf-8") as fp:
        fp.write("window.STOCK_META_US=" + json.dumps(meta, ensure_ascii=False) + ";\n")
        fp.write("window.STOCK_MARKET_US=" + json.dumps(market, ensure_ascii=False,
                                                        separators=(",", ":")) + ";\n")
        fp.write("window.STOCK_DB_US=" + json.dumps(out, ensure_ascii=False,
                                                    separators=(",", ":")) + ";\n")
        fp.write("window.KO_ALIAS=" + json.dumps(alias, ensure_ascii=False,
                                                 separators=(",", ":")) + ";\n")
    print("완료:", len(out), "종목 / 한글명", len(alias), "개 → data_us.js")

    # SEC 공시 (커버 종목만, 30일 누적)
    sec_filings(set(out.keys()))


if __name__ == "__main__":
    main()
