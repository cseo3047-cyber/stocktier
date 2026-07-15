#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 전 종목 데이터 수집 v3.1 (네이버 증권 모바일 API)
# 종목 + 지수(KOSPI/KOSDAQ/KPI200, 3개월 추이) + 업종 + 테마 + 외인·기관 순매수
# 결과물: data.js
import json
import os
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

PC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://finance.naver.com/",
}


def build_group_maps():
    """네이버 PC 업종/테마 상세 페이지에서 종목코드 → 업종명/테마명 매핑"""
    ind_map, thm_map = {}, {}

    def list_pairs(gtype, pages):
        pairs = []
        for pg in range(1, pages + 1):
            try:
                url = f"https://finance.naver.com/sise/sise_group.naver?type={gtype}&page={pg}"
                r = requests.get(url, headers=PC_HEADERS, timeout=15)
                r.encoding = "euc-kr"
                found = re.findall(r'type=' + gtype + r'&(?:amp;)?no=(\d+)"[^>]*>([^<]+)</a>', r.text)
                if not found:
                    break
                pairs += found
            except Exception:
                break
            time.sleep(0.1)
        # 중복 제거
        seen, out = set(), []
        for no, nm in pairs:
            if no not in seen:
                seen.add(no)
                out.append((no, nm.strip()))
        return out

    def detail_codes(gtype, no):
        try:
            url = f"https://finance.naver.com/sise/sise_group_detail.naver?type={gtype}&no={no}"
            r = requests.get(url, headers=PC_HEADERS, timeout=15)
            r.encoding = "euc-kr"
            return re.findall(r'/item/main\.naver\?code=(\d{6})', r.text)
        except Exception:
            return []

    for no, nm in list_pairs("upjong", 2):
        for c in detail_codes("upjong", no):
            ind_map.setdefault(c, nm)
        time.sleep(0.05)
    for no, nm in list_pairs("theme", 8):
        for c in detail_codes("theme", no):
            thm_map.setdefault(c, nm)
        time.sleep(0.05)
    print("업종 매핑:", len(ind_map), "종목 / 테마 매핑:", len(thm_map), "종목", flush=True)
    return ind_map, thm_map


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
    flows = []
    if trends:
        f0 = num(trends[0].get("foreignerPureBuyQuant"))
        o0 = num(trends[0].get("organPureBuyQuant"))
        fbuy = int(f0) if f0 is not None else None
        obuy = int(o0) if o0 is not None else None
        # 최근 5거래일 수급 이력: [YYMMDD, 외인 순매수(억), 기관 순매수(억)]
        for t in trends[:5]:
            fq, oq = num(t.get("foreignerPureBuyQuant")), num(t.get("organPureBuyQuant"))
            cp = num(t.get("closePrice"))
            bd = str(t.get("bizdate") or "")
            if fq is None or oq is None or not cp or len(bd) < 8:
                continue
            flows.append([bd[2:], int(round(fq * cp / 1e8)), int(round(oq * cp / 1e8))])
        flows.reverse()   # 과거 → 최신 순
    return per, pbr, div, roe, forn, prevs, vol_prev, fbuy, obuy, flows


def scrape_frgn(code, pages=6):
    """PC 매매동향 페이지에서 과거 수급 소급 (약 20거래일/페이지 × 6 ≈ 6개월) → [[YYMMDD, 외인억, 기관억] 과거→최신]"""
    rows = {}
    for page in range(1, pages + 1):
        try:
            r = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}",
                             headers=PC_HEADERS, timeout=15)
            r.encoding = "euc-kr"
            for tr in r.text.split("<tr")[1:]:
                dm = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", tr)
                if not dm:
                    continue
                vals = re.findall(r'<span class="tah[^"]*">\s*([+\-]?[\d,.%]+)\s*</span>', tr)
                if len(vals) < 6:
                    continue
                close = num(vals[0])
                organ = num(vals[4])
                forgn = num(vals[5])
                if close is None or organ is None or forgn is None:
                    continue
                ymd = dm.group(1)[2:] + dm.group(2) + dm.group(3)
                rows[ymd] = [ymd, int(round(forgn * close / 1e8)), int(round(organ * close / 1e8))]
            time.sleep(0.05)
        except Exception:
            break
    return [rows[k] for k in sorted(rows.keys())]


def history(code, count=1250):
    """일별 시세 약 5년치. 반환: (종가리스트, 거래량리스트, OHLC리스트)
       OHLC = [[YYYYMMDD, 시가, 고가, 저가, 종가, 거래량], ...] (과거→최신, 차트용)"""
    try:
        r = S.get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0",
                  timeout=15)
        rows = re.findall(r'data="([^"]+)"', r.text)
        closes, vols, ohlc = [], [], []
        for row in rows:
            p = row.split("|")
            # fchart 포맷: p[0]=날짜(YYYYMMDD) p[1]=시가 p[2]=고가 p[3]=저가 p[4]=종가 p[5]=거래량
            if len(p) >= 6 and num(p[4]) and num(p[4]) > 0:
                c = float(p[4])
                v = float(p[5]) if num(p[5]) is not None else 0.0
                closes.append(c)
                vols.append(v)
                o = num(p[1]); h = num(p[2]); l = num(p[3]); d = str(p[0]).strip()
                if len(d) == 8:
                    ohlc.append([d, round(o if o else c, 2), round(h if h else c, 2),
                                 round(l if l else c, 2), round(c, 2), int(v)])
        return closes, vols, ohlc
    except Exception:
        return [], [], []


def idx_hist(symbol, count=1250):
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
                            round(float(p[4]), 2),
                            str(p[0])[4:],           # MMDD
                            int(num(p[5]) or 0) if len(p) >= 6 else 0])   # 거래량
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
                o["hdates"] = [x[3] for x in h]
                o["vhist"] = [x[4] for x in h]
            mk[key] = o

    def groups(kind, keep):
        def fetch(base):
            out = []
            page = 1
            while page <= 10 and len(out) < keep:
                url = f"{base}/{kind}?page={page}&pageSize=20"
                j = None
                try:
                    r = S.get(url, timeout=15)
                    if r.status_code == 200:
                        j = r.json()
                    if not j or not j.get("groups"):
                        print(f"[진단] {kind} p{page} {base.split('//')[1].split('/')[0]} status={r.status_code}", flush=True)
                        break
                except Exception as e:
                    print(f"[진단] {kind} p{page} 요청 실패: {str(e)[:120]}", flush=True)
                    break
                for g in j["groups"]:
                    out.append([str(g.get("name") or ""), num(g.get("changeRate")) or 0.0,
                                int(g.get("riseCount") or 0), int(g.get("fallCount") or 0),
                                int(g.get("totalCount") or 0)])
                total = j.get("totalCount", 0)
                if page * 20 >= total:
                    break
                page += 1
                time.sleep(0.2)
            return out
        out = fetch("https://m.stock.naver.com/api/stocks")
        if not out:
            out = fetch("https://api.stock.naver.com/stocks")
        return out[:keep]

    def upjong_scrape():
        """PC 네이버 증권 업종 페이지에서 직접 추출 (최후의 수단) — 데스크톱 UA 사용"""
        pc_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://finance.naver.com/",
        }
        for url in ("https://finance.naver.com/sise/sise_group.naver?type=upjong",
                    "https://finance.naver.com/sise/sise_group.nhn?type=upjong"):
            try:
                r = requests.get(url, headers=pc_headers, timeout=15)
                r.encoding = "euc-kr"
                rows = re.findall(r'type=upjong&(?:amp;)?no=\d+">([^<]+)</a>(.*?)</tr>', r.text, re.S)
                out = []
                for nm, block in rows:
                    m = re.search(r'([+\-]?\d+(?:\.\d+)?)%', block)
                    nums = re.findall(r'>\s*([\d,]+)\s*</td>', block)
                    if not m or len(nums) < 4:
                        continue
                    total, up = int(nums[0].replace(",", "")), int(nums[1].replace(",", ""))
                    down = int(nums[3].replace(",", ""))
                    out.append([nm.strip(), float(m.group(1)), up, down, total])
                if out:
                    out.sort(key=lambda x: -x[1])
                    print("[진단] upjong PC 스크래핑 성공:", len(out), "개", flush=True)
                    return out
                print(f"[진단] upjong 스크래핑 0개 status={r.status_code} url={r.url} body={r.text[:250]!r}", flush=True)
            except Exception as e:
                print("[진단] upjong 스크래핑 실패:", str(e)[:150], flush=True)
        return []

    def rss_feed(url, office, cat, n=5):
        """RSS 1개에서 제목+링크 수집 → [제목, 출처, 시각, 링크, 분야]"""
        import html as _h
        mon = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
               "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}
        try:
            r = requests.get(url, headers=PC_HEADERS, timeout=15)
            if r.status_code != 200:
                print("[진단] RSS status=", r.status_code, cat, url[:60], flush=True)
                return []
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
                    out.append([t, office, tm2, u, cat])
                if len(out) >= n:
                    break
            return out
        except Exception as e:
            print("[진단] RSS 실패:", str(e)[:100], url[:60], flush=True)
            return []

    def rss_news(_unused=None, n=8):
        """분야별 여러 언론사 RSS를 합쳐 다양하게 수집 (후보 주소는 실패해도 무시)"""
        FEEDS = [
            # (주소, 출처, 분야) — 분야: 시장/기업/정책/산업/해외
            ("https://www.mk.co.kr/rss/50200011/", "매일경제", "시장"),
            ("https://www.hankyung.com/feed/finance", "한국경제", "시장"),
            ("https://www.mk.co.kr/rss/30100041/", "매일경제", "기업"),
            ("https://www.hankyung.com/feed/economy", "한국경제", "기업"),
            ("https://www.yna.co.kr/rss/economy.xml", "연합뉴스", "정책"),
            ("https://www.yna.co.kr/rss/industry.xml", "연합뉴스", "산업"),
            ("https://www.hankyung.com/feed/industry", "한국경제", "산업"),
            ("https://www.mk.co.kr/rss/30300018/", "매일경제", "해외"),
            ("https://www.yna.co.kr/rss/international.xml", "연합뉴스", "해외"),
        ]
        out, seenT, catN = [], set(), {}
        for url, office, cat in FEEDS:
            if catN.get(cat, 0) >= 5:
                continue
            for it in rss_feed(url, office, cat, 5):
                if it[0] in seenT:
                    continue
                seenT.add(it[0])
                out.append(it)
                catN[cat] = catN.get(cat, 0) + 1
            time.sleep(0.2)
        out.sort(key=lambda x: x[2] or "00/00 00:00", reverse=True)
        print("RSS 뉴스 통합:", len(out), "건 / 분야:", dict(catN), flush=True)
        return out[:22]

    def news_kr():
        import html as _h
        j = get_json("https://m.stock.naver.com/api/news/mainnews?page=1&pageSize=12")
        out = []
        try:
            for grp in (j or []):
                for it in grp.get("items", []):
                    t = _h.unescape(str(it.get("titleFull") or it.get("title") or "")).strip()
                    u = str(it.get("mobileNewsUrl") or "")
                    dt = str(it.get("datetime") or "")
                    tm = f"{dt[4:6]}/{dt[6:8]} {dt[8:10]}:{dt[10:12]}" if len(dt) >= 12 else ""
                    if t and u:
                        out.append([t, str(it.get("officeName") or ""), tm, u])
                    if len(out) >= 8:
                        break
                if len(out) >= 8:
                    break
        except Exception as e:
            print("[진단] 뉴스 파싱 실패:", str(e)[:120], flush=True)
        if not out:
            out = rss_news([
                ("https://www.hankyung.com/feed/finance", "한국경제"),
                ("https://www.mk.co.kr/rss/50200011/", "매일경제"),
                ("https://www.yna.co.kr/rss/economy.xml", "연합뉴스"),
            ])
        print("뉴스:", len(out), "건", flush=True)
        return out

    def reports_scrape():
        """네이버 증권 리서치 → [[증권사, 제목, MM/DD, 링크], ...] 최대 8건
           1) 모바일 API 후보 → 2) PC 페이지(.naver/.nhn) 순서로 시도. 제목·출처·날짜만 수집."""
        import html as _h
        out, seen = [], set()

        def add(firm, title, md, url):
            firm, title = str(firm).strip(), str(title).strip()
            if firm and title and title not in seen and len(out) < 8:
                seen.add(title)
                out.append([firm, title, md, url])

        # ── 1) 모바일 리서치 API 후보 (JSON) ──
        def from_json(j):
            def find_list(o, depth=0):
                if depth > 3:
                    return None
                if isinstance(o, list) and o and isinstance(o[0], dict):
                    return o
                if isinstance(o, dict):
                    for v in o.values():
                        r2 = find_list(v, depth + 1)
                        if r2:
                            return r2
                return None
            lst = find_list(j) or []
            n0 = len(out)
            for it in lst[:12]:
                title = it.get("title") or it.get("titleName") or it.get("reportTitle") or ""
                firm = it.get("brokerName") or it.get("officeName") or it.get("stockFirmName") or it.get("securitiesFirm") or ""
                dt = str(it.get("writeDate") or it.get("date") or it.get("registerDate") or it.get("createdAt") or "")
                nid = str(it.get("researchId") or it.get("nid") or it.get("id") or it.get("seq") or "")
                m2 = re.search(r"\d{4}[.\-/]?(\d{2})[.\-/]?(\d{2})", dt)
                md = f"{m2.group(1)}/{m2.group(2)}" if m2 else ""
                url = f"https://m.stock.naver.com/investment/research/{nid}" if nid else "https://finance.naver.com/research/"
                add(firm, title, md, url)
            if lst and len(out) == n0:
                print("[진단] 리서치 JSON 항목 키:", list(lst[0].keys())[:12], flush=True)
        for api in ("https://m.stock.naver.com/front-api/research/list?category=industry&page=1&pageSize=10",
                    "https://m.stock.naver.com/api/research/industry?page=1&pageSize=10"):
            if len(out) >= 8:
                break
            j = get_json(api)
            if j:
                from_json(j)
                if out:
                    print("[진단] 리서치 모바일 API 성공:", api.split("?")[0].split("/")[-1], flush=True)

        # ── 2) PC 페이지 스크래핑 (.naver / .nhn 모두 시도) ──
        if len(out) < 8:
            for path in ("industry_list.naver", "invest_list.naver", "industry_list.nhn", "invest_list.nhn"):
                if len(out) >= 8:
                    break
                try:
                    r = requests.get(f"https://finance.naver.com/research/{path}",
                                     headers=PC_HEADERS, timeout=15)
                    r.encoding = "euc-kr"
                    if r.status_code != 200:
                        print(f"[진단] 리서치 {path} status={r.status_code}", flush=True)
                        continue
                    n0 = len(out)
                    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
                        a = re.search(r'href="(/research/\w+_read\.(?:naver|nhn)\?[^"]+)"[^>]*>(.*?)</a>', tr, re.S)
                        d = re.search(r"(\d{2})\.(\d{2})\.(\d{2})", tr)
                        if not a or not d:
                            continue
                        title = _h.unescape(re.sub(r"<[^>]+>", "", a.group(2))).strip()
                        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                        firm = ""
                        for i2, td in enumerate(tds):
                            if "_read." in td and i2 + 1 < len(tds):
                                firm = re.sub(r"<[^>]+>", "", tds[i2 + 1]).strip()
                                break
                        add(firm, title, f"{d.group(2)}/{d.group(3)}",
                            "https://finance.naver.com" + _h.unescape(a.group(1)))
                    if len(out) == n0:   # 이 페이지에서 0건이면 원인 진단 출력
                        body = re.sub(r"\s+", " ", r.text[:200])
                        print(f"[진단] 리서치 {path} 파싱 0건 · len={len(r.text)} · _read.링크 {r.text.count('_read.')}개 · 앞부분: {body!r}", flush=True)
                    time.sleep(0.2)
                except Exception as e:
                    print("[진단] 리서치 수집 실패:", str(e)[:120], flush=True)
        print("리서치 리포트:", len(out), "건", flush=True)
        return out

    def dart_disclosures():
        """오픈DART 공시 수집 (GitHub Secret: DART_API_KEY) — 유형 분류 + 충격도/호악재 판정"""
        key = os.environ.get("DART_API_KEY", "").strip()
        if not key:
            print("[진단] DART_API_KEY 없음 — 공시 수집 건너뜀 (GitHub Secrets 설정 필요)", flush=True)
            return {"date": "", "items": []}
        RULES = [
            ("상장폐지", "거래정지", 5, -2), ("거래정지", "거래정지", 5, -2),
            ("투자위험", "투자주의·경고", 5, -2), ("투자경고", "투자주의·경고", 4, -1),
            ("투자주의", "투자주의·경고", 3, -1), ("불성실공시", "투자주의·경고", 4, -1),
            ("횡령", "소송", 5, -2), ("배임", "소송", 5, -2), ("소송", "소송", 4, -1),
            ("유상증자", "유상증자", 4, -1), ("무상증자", "증자·배당", 3, 1),
            ("전환사채", "전환사채", 4, -1), ("신주인수권", "전환사채", 4, -1), ("교환사채", "전환사채", 3, -1),
            ("공급계약", "공급계약", 4, 1), ("수주", "공급계약", 4, 1),
            ("자기주식취득", "자사주", 3, 1), ("자기주식 취득", "자사주", 3, 1),
            ("자기주식처분", "자사주", 3, -1), ("자기주식 처분", "자사주", 3, -1),
            ("최대주주변경", "최대주주 변경", 3, 0), ("최대주주 변경", "최대주주 변경", 3, 0),
            ("감사의견", "감사의견", 3, 0), ("감사보고서", "감사의견", 2, 0),
            ("영업정지", "실적·영업", 4, -1), ("잠정실적", "실적·영업", 3, 0),
            ("영업(잠정)", "실적·영업", 3, 0), ("실적", "실적·영업", 3, 0),
            ("배당", "증자·배당", 3, 1),
            ("합병", "지배구조", 3, 0), ("분할", "지배구조", 3, 0),
            ("정정", "정정", 2, 0),
        ]

        def classify(nm):
            for kw, ty, imp, tone in RULES:
                if kw in nm:
                    return ty, imp, tone
            return "기타", 2, 0

        def fetch_day(ds):
            rows = []
            for page in range(1, 11):
                j = get_json(f"https://opendart.fss.or.kr/api/list.json?crtfc_key={key}"
                             f"&bgn_de={ds}&end_de={ds}&page_no={page}&page_count=100")
                if not j or j.get("status") != "000":
                    if page == 1 and j and j.get("status") != "013":   # 013 = 조회 데이터 없음(휴일)
                        print("[진단] DART 응답:", j.get("status"), str(j.get("message"))[:80], flush=True)
                    break
                rows += j.get("list", [])
                if page >= int(j.get("total_page", 1) or 1):
                    break
                time.sleep(0.2)
            items = []
            for r in rows:
                if r.get("corp_cls") not in ("Y", "K") or not (r.get("stock_code") or "").strip():
                    continue
                nm = str(r.get("report_nm") or "").strip()
                ty, imp, tone = classify(nm)
                items.append([str(r.get("corp_name") or ""), str(r.get("stock_code") or "").strip(),
                              ty, nm, imp, tone, str(r.get("rcept_no") or ""),
                              "Y" if r.get("corp_cls") == "Y" else "K"])
            items.sort(key=lambda x: x[6], reverse=True)   # 접수번호 = 최신순
            return items[:400]

        # 기존 누적분(dart.js) 로드 → 최근 30일 중 빠진 날짜만 새로 조회 (오늘·어제는 항상 갱신)
        store = {}
        try:
            with open("dart.js", encoding="utf-8") as f:
                m = re.search(r"window\.STOCK_DART=(\{.*\});", f.read(), re.S)
                if m:
                    store = json.loads(m.group(1))
        except Exception:
            store = {}
        d0 = datetime.date.today()
        fetched = 0
        for back in range(30):
            ds = (d0 - datetime.timedelta(days=back)).strftime("%Y%m%d")
            if ds in store and back >= 2:
                continue
            store[ds] = fetch_day(ds)
            fetched += 1
            time.sleep(0.3)
        cutoff = (d0 - datetime.timedelta(days=30)).strftime("%Y%m%d")
        store = {k: v for k, v in store.items() if k >= cutoff}
        with open("dart.js", "w", encoding="utf-8") as f:
            f.write("window.STOCK_DART=" + json.dumps(store, ensure_ascii=False,
                                                      separators=(",", ":")) + ";\n")
        total = sum(len(v) for v in store.values())
        print("공시 누적:", total, "건 /", len(store), "일 (신규 조회", fetched, "일) → dart.js", flush=True)
        for ds in sorted(store.keys(), reverse=True):
            if store[ds]:
                return {"date": ds, "items": store[ds]}
        print("[진단] 공시 0건 (최근 30일)", flush=True)
        return {"date": "", "items": []}

    def fx_usdkrw():
        """원/달러 환율 (ECB 기반 무료 API, 실패 시 후보 재시도)"""
        for url in ("https://api.frankfurter.app/latest?from=USD&to=KRW",
                    "https://open.er-api.com/v6/latest/USD"):
            j = get_json(url)
            try:
                if j and "rates" in j and "KRW" in j["rates"]:
                    return round(float(j["rates"]["KRW"]), 2)
            except Exception:
                pass
        print("[진단] 환율 수집 실패 — 기본값 사용", flush=True)
        return None

    mk["fx"] = fx_usdkrw() or 0
    print("환율(USD/KRW):", mk["fx"] or "실패", flush=True)

    def fx_hist(days=90):
        """원/달러 최근 90일 이력 (그래프용)"""
        try:
            end = datetime.date.today()
            start = end - datetime.timedelta(days=days)
            j = get_json(f"https://api.frankfurter.app/{start}..{end}?from=USD&to=KRW")
            rates = (j or {}).get("rates", {})
            return [round(float(rates[d]["KRW"]), 2) for d in sorted(rates)]
        except Exception as e:
            print("[진단] 환율 이력 실패:", str(e)[:100], flush=True)
            return []

    mk["fxHist"] = fx_hist()
    print("환율 이력:", len(mk["fxHist"]), "일", flush=True)
    mk["upjong"] = groups("upjong", 100) or upjong_scrape()
    mk["theme"] = groups("theme", 30)
    mk["news"] = news_kr()
    mk["reports"] = reports_scrape()
    mk["earn"] = {}   # 국내 실적 발표 예정일: 무료 공개 소스 없음(브라우저 확인 완료) — 미국은 collect_us에서 수집
    mk["dart"] = dart_disclosures()
    print("지수:", [k for k in mk if k not in ("upjong", "theme")],
          "/ 업종", len(mk.get("upjong", [])), "/ 테마", len(mk.get("theme", [])), flush=True)
    return mk


def main():
    stocks = listing("KOSPI") + listing("KOSDAQ")
    if len(stocks) < 100:
        sys.exit("종목 목록 수집 실패: " + str(len(stocks)))

    market = market_extra()
    ind_map, thm_map = build_group_maps()

    # 이전 수급 이력(flows.js) 로드 — 최근 120거래일(약 6개월) 누적 유지
    prev_flows = {}
    try:
        with open("flows.js", encoding="utf-8") as f:
            m = re.search(r"window\.STOCK_FLOWS=(\{.*\});", f.read(), re.S)
            if m:
                prev_flows = json.loads(m.group(1))
    except Exception:
        prev_flows = {}
    new_flows = {}
    # 첫 실행(누적 데이터가 거의 없을 때)에만 과거 3개월 소급 스크래핑
    BACKFILL = len(prev_flows) < 100
    if BACKFILL:
        print("수급 소급 스크래핑 시작 (첫 실행 · 종목당 약 120거래일)", flush=True)

    # 차트용 OHLC 대상: 시총 상위 종목만 (레포 크기 관리). 필요 시 숫자만 올리면 됨.
    OHLC_TOP = 900
    ohlc_codes = set(s["code"] for s in sorted(stocks, key=lambda s: -(s.get("cap") or 0))[:OHLC_TOP])
    os.makedirs("ohlc", exist_ok=True)
    ohlc_written = []

    out = {}
    fchart_ok = 0
    for i, st in enumerate(stocks):
        d = detail(st["code"])
        if d is None:
            continue
        per, pbr, div, roe, forn, prevs, vol_prev, fbuy, obuy, flows = d

        # 수급 이력 병합 (날짜 기준 중복 제거, 최근 120거래일 유지)
        byd = {r[0]: r for r in prev_flows.get(st["code"], [])}
        if BACKFILL:
            for r in scrape_frgn(st["code"]):
                byd[r[0]] = r
        for r in flows:
            byd[r[0]] = r
        if byd:
            new_flows[st["code"]] = [byd[k] for k in sorted(byd.keys())][-120:]

        closes, vols, ohlc = history(st["code"])
        # 차트용 OHLC 저장 (상위 종목만, 최근 500거래일 ≈ 2년)
        if ohlc and st["code"] in ohlc_codes:
            try:
                with open(f"ohlc/{st['code']}.json", "w", encoding="utf-8") as of:
                    json.dump(ohlc[-500:], of, ensure_ascii=False, separators=(",", ":"))
                ohlc_written.append(st["code"])
            except Exception:
                pass
        spk = None
        if closes:
            fchart_ok += 1
            rc = closes[-65:]           # 최근 3개월 (지표 계산용)
            rv = vols[-65:]
            vol3m = int(sum(rv) / len(rv))

            def ret(n):
                if len(rc) >= n and rc[-n] > 0:
                    return round((rc[-1] - rc[-n]) / rc[-n] * 100, 1)
                return None
            r1w, r1m, r3m = ret(6), ret(21), ret(len(rc))
            # 장기 차트: 5년치를 100개 점으로 압축 (현재가=1000 기준 상대값)
            if len(closes) >= 10:
                step = max(1, len(closes) // 100)
                pts = closes[::step][-100:]
                last = pts[-1] or 1
                spk = [int(round(p / last * 1000)) for p in pts]
        else:
            vol3m = int((st["volToday"] + (vol_prev or st["volToday"])) / 2)
            r1w = r1m = r3m = None

        days = ([round(st["chg"], 2)] + prevs + [0.0] * 4)[:5]
        if vol_prev is None:
            vol_prev = vol3m

        def vavg(n):
            if not vols:
                return vol3m
            w = vols[-n:] if len(vols) > n else vols
            return int(sum(w) / len(w)) if w else vol3m

        out[st["name"]] = [
            st["code"], st["mkt"], st["price"], days[0], per, pbr, div, roe,
            st["cap"], vol3m, vol_prev, st["volToday"], days, forn,
            r1w, r1m, r3m, fbuy, obuy, spk,
            ind_map.get(st["code"], ""), thm_map.get(st["code"], ""),
            vavg(126), vavg(252), vavg(756), vavg(9999),   # [22~25] 6개월/1년/3년/5년 평균 거래량
        ]
        if (i + 1) % 200 == 0:
            print(f"{i+1}/{len(stocks)} 처리, fchart 성공 {fchart_ok}", flush=True)
        time.sleep(0.05)

    if len(out) < 100:
        sys.exit("상세 수집 실패: " + str(len(out)))

    # ── 지수(코스피/코스닥) 수급 = 전 종목 외인·기관 순매수 합산 (날짜별, 억원)
    #    새 네트워크 호출 없이 flows에서 파생. 종목별로 보이는 값의 합이라 일관·투명.
    mkt_of = {st["code"]: st["mkt"] for st in stocks}
    idx_agg = {"KOSPI": {}, "KOSDAQ": {}}
    for code, rows in new_flows.items():
        mk_ = mkt_of.get(code)
        if mk_ not in idx_agg:
            continue
        for r in rows:
            if len(r) < 3:
                continue
            ymd, fq, oq = r[0], r[1], r[2]
            acc = idx_agg[mk_].setdefault(ymd, [0, 0])
            acc[0] += fq
            acc[1] += oq
    market["flowIdx"] = {
        mk_: [[ymd, agg[ymd][0], agg[ymd][1]] for ymd in sorted(agg)][-120:]
        for mk_, agg in idx_agg.items()
    }
    print("지수 수급 합산:",
          {mk_: len(v) for mk_, v in market["flowIdx"].items()}, "일 → data.js (STOCK_MARKET.flowIdx)", flush=True)

    meta = {"date": datetime.date.today().strftime("%Y%m%d"),
            "count": len(out),
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open("data.js", "w", encoding="utf-8") as fp:
        fp.write("window.STOCK_META=" + json.dumps(meta, ensure_ascii=False) + ";\n")
        fp.write("window.STOCK_MARKET=" + json.dumps(market, ensure_ascii=False,
                                                     separators=(",", ":")) + ";\n")
        fp.write("window.STOCK_DB=" + json.dumps(out, ensure_ascii=False,
                                                 separators=(",", ":")) + ";\n")
    with open("flows.js", "w", encoding="utf-8") as fp:
        fp.write("window.STOCK_FLOWS=" + json.dumps(new_flows, ensure_ascii=False,
                                                    separators=(",", ":")) + ";\n")
    avg_days = round(sum(len(v) for v in new_flows.values()) / max(1, len(new_flows)), 1)
    print("수급 이력:", len(new_flows), "종목 (평균", avg_days, "일) → flows.js", flush=True)
    # 차트용 OHLC 인덱스 (차트 페이지 datafeed가 참조: 차트 가능한 종목 코드 목록)
    try:
        with open("ohlc/index.json", "w", encoding="utf-8") as fp:
            json.dump(sorted(set(ohlc_written)), fp, ensure_ascii=False, separators=(",", ":"))
        print("차트 OHLC:", len(set(ohlc_written)), "종목 → ohlc/*.json", flush=True)
    except Exception as e:
        print("[진단] OHLC 인덱스 쓰기 실패:", str(e)[:120], flush=True)
    print("완료:", len(out), "종목 → data.js (fchart 성공:", fchart_ok, ")")


if __name__ == "__main__":
    main()
