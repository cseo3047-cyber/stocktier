#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 미국 주식 데이터 수집 스크립트 (GitHub Actions에서 실행됨)
# 결과물: data_us.js
import json
import sys
import time
import datetime

import pandas as pd
import yfinance as yf

try:
    import FinanceDataReader as fdr
except ImportError:
    fdr = None

# 한글 이름 → 티커 매핑 (검색용)
KO_ALIAS = {
    "애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "아마존": "AMZN",
    "구글": "GOOGL", "알파벳": "GOOGL", "메타": "META", "페이스북": "META",
    "테슬라": "TSLA", "넷플릭스": "NFLX", "브로드컴": "AVGO", "인텔": "INTC",
    "퀄컴": "QCOM", "마이크론": "MU", "티에스엠씨": "TSM", "팔란티어": "PLTR",
    "코인베이스": "COIN", "일라이릴리": "LLY", "화이자": "PFE", "존슨앤존슨": "JNJ",
    "버크셔": "BRK-B", "버크셔해서웨이": "BRK-B", "제이피모건": "JPM", "JP모건": "JPM",
    "뱅크오브아메리카": "BAC", "골드만삭스": "GS", "비자": "V", "마스터카드": "MA",
    "페이팔": "PYPL", "월마트": "WMT", "코스트코": "COST", "맥도날드": "MCD",
    "스타벅스": "SBUX", "나이키": "NKE", "코카콜라": "KO", "펩시": "PEP",
    "디즈니": "DIS", "보잉": "BA", "캐터필러": "CAT", "엑슨모빌": "XOM",
    "셰브론": "CVX", "오라클": "ORCL", "세일즈포스": "CRM", "어도비": "ADBE",
    "시스코": "CSCO", "우버": "UBER", "에어비앤비": "ABNB", "도어대시": "DASH",
    "리비안": "RIVN", "루시드": "LCID", "니오": "NIO", "알리바바": "BABA",
    "쇼피파이": "SHOP", "슈퍼마이크로": "SMCI", "에이엠디": "AMD", "암홀딩스": "ARM",
    "존디어": "DE", "홈디포": "HD", "버라이즌": "VZ", "에이티앤티": "T",
    "유나이티드헬스": "UNH", "애브비": "ABBV", "머크": "MRK", "암젠": "AMGN",
}

# S&P500 외 추가 인기 종목
EXTRA = ["PLTR", "COIN", "RBLX", "HOOD", "SOFI", "IONQ", "RIVN", "LCID",
         "SMCI", "ARM", "TSM", "BABA", "NIO", "XPEV", "LI", "SE", "SHOP",
         "SNAP", "U", "DKNG", "ASML", "MSTR"]

# fdr 실패 시 대체용 핵심 종목
FALLBACK = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
            "BRK-B", "LLY", "JPM", "V", "MA", "UNH", "XOM", "WMT", "COST",
            "HD", "PG", "JNJ", "ABBV", "MRK", "NFLX", "AMD", "INTC", "QCOM",
            "MU", "ORCL", "CRM", "ADBE", "CSCO", "IBM", "TXN", "AMAT", "KO",
            "PEP", "MCD", "SBUX", "NKE", "DIS", "BA", "CAT", "GS", "BAC",
            "PYPL", "UBER", "ABNB", "GE", "T", "VZ", "PFE", "AMGN", "DE"]


def get_universe():
    tickers = []
    if fdr is not None:
        try:
            sp = fdr.StockListing("S&P500")
            tickers = [str(s).replace(".", "-") for s in sp["Symbol"]]
            print("S&P500 목록:", len(tickers))
        except Exception as e:
            print("S&P500 목록 실패:", str(e)[:60])
    if not tickers:
        tickers = list(FALLBACK)
    for t in EXTRA:
        if t not in tickers:
            tickers.append(t)
    return tickers


def main():
    tickers = get_universe()
    print("대상 종목:", len(tickers))

    # 1) 3개월+ 일별 시세 일괄 다운로드
    hist = yf.download(tickers, period="4mo", interval="1d",
                       group_by="ticker", threads=True, progress=False,
                       auto_adjust=False)
    if hist is None or len(hist) == 0:
        sys.exit("시세 다운로드 실패")

    # 2) 종목별 재무지표
    out = {}
    base_date = None
    for i, t in enumerate(tickers):
        try:
            df = hist[t].dropna(subset=["Close"])
        except Exception:
            continue
        if len(df) < 6:
            continue
        c = [float(x) for x in df["Close"]]
        v = [int(x) for x in df["Volume"].fillna(0)]
        if c[-1] <= 0:
            continue
        if base_date is None:
            base_date = df.index[-1].strftime("%Y%m%d")

        days = []
        for k in range(1, 6):
            prev, cur = c[-k - 1], c[-k]
            days.append(round((cur - prev) / prev * 100, 2) if prev else 0.0)

        per = pbr = div = roe = 0.0
        cap = 0
        name = t
        exch = "US"
        try:
            info = yf.Ticker(t).info or {}
            per = round(float(info.get("trailingPE") or 0), 1)
            pbr = round(float(info.get("priceToBook") or 0), 2)
            dv = info.get("dividendYield") or 0
            div = round(float(dv) * 100, 1) if dv < 1 else round(float(dv), 1)
            re_ = info.get("returnOnEquity")
            roe = round(float(re_) * 100, 1) if re_ is not None else 0.0
            cap = int(info.get("marketCap") or 0)
            name = str(info.get("shortName") or t).strip()
            ex = str(info.get("fullExchangeName") or "")
            exch = "NASDAQ" if "Nasdaq" in ex else ("NYSE" if "NYSE" in ex else "US")
        except Exception as e:
            print("info 생략", t, str(e)[:40])
        time.sleep(0.1)

        def ret(n):
            if len(c) >= n and c[-n] > 0:
                return round((c[-1] - c[-n]) / c[-n] * 100, 1)
            return None

        out[t] = [
            t, exch, round(c[-1], 2), days[0], per, pbr, div, roe,
            int(cap / 1e8),                      # 시가총액(억 달러)
            int(sum(v) / len(v)), v[-2], v[-1],
            days, None,
            ret(6), ret(21), ret(len(c)),
            name,                                 # [17] 영문명
        ]
        if (i + 1) % 50 == 0:
            print(f"{i+1}/{len(tickers)} 완료", flush=True)

    if len(out) < 20:
        sys.exit("수집된 종목이 너무 적음: " + str(len(out)))

    # 한글 별칭 역방향 부여
    alias = {k: v for k, v in KO_ALIAS.items() if v in out}

    meta = {"date": base_date or datetime.date.today().strftime("%Y%m%d"),
            "count": len(out),
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open("data_us.js", "w", encoding="utf-8") as fp:
        fp.write("window.STOCK_META_US=" + json.dumps(meta, ensure_ascii=False) + ";\n")
        fp.write("window.STOCK_DB_US=" + json.dumps(out, ensure_ascii=False,
                                                    separators=(",", ":")) + ";\n")
        fp.write("window.KO_ALIAS=" + json.dumps(alias, ensure_ascii=False,
                                                 separators=(",", ":")) + ";\n")
    print("완료:", len(out), "종목 → data_us.js")


if __name__ == "__main__":
    main()
