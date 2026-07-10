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
    if trends:
        f0 = num(trends[0].get("foreignerPureBuyQuant"))
        o0 = num(trends[0].get("organPureBuyQuant"))
        fbuy = int(f0) if f0 is not None else None
        obuy = int(o0) if o0 is not None else None
    return per, pbr, div, roe, forn, prevs, vol_prev, fbuy, obuy


def history(code, count=1250):
    """일별 시세 약 5년치 (최근 65개는 지표 계산용, 전체는 장기 차트용)"""
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

    mk["upjong"] = groups("upjong", 100) or upjong_scrape()
    mk["theme"] = groups("theme", 30)
    mk["news"] = news_kr()
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

    out = {}
    fchart_ok = 0
    for i, st in enumerate(stocks):
        d = detail(st["code"])
        if d is None:
            continue
        per, pbr, div, roe, forn, prevs, vol_prev, fbuy, obuy = d

        closes, vols = history(st["code"])
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

        out[st["name"]] = [
            st["code"], st["mkt"], st["price"], days[0], per, pbr, div, roe,
            st["cap"], vol3m, vol_prev, st["volToday"], days, forn,
            r1w, r1m, r3m, fbuy, obuy, spk,
            ind_map.get(st["code"], ""), thm_map.get(st["code"], ""),
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
