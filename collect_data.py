#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# STOCK.GG 전 종목 데이터 수집 스크립트 (GitHub Actions에서 실행됨)
# 결과물: data.js (사이트가 읽는 데이터 파일)
import json
import sys
import time
import datetime

import pandas as pd
from pykrx import stock

try:
    import FinanceDataReader as fdr
except ImportError:
    fdr = None

TODAY = datetime.date.today()
NEED_DAYS = 64  # 약 3개월치 거래일


def fetch_ohlcv(ds):
    """해당 날짜의 전 종목 시세. 휴장일이면 None."""
    try:
        df = stock.get_market_ohlcv(ds, market="ALL")
        if df is not None and len(df) > 500 and df["거래량"].sum() > 0:
            return df
    except Exception as e:
        print("skip", ds, str(e)[:60])
    return None


def main():
    # 1) 최근 거래일부터 거꾸로 3개월치 일별 시세 수집
    dates = []
    snaps = {}
    d = TODAY
    while len(dates) < NEED_DAYS and (TODAY - d).days < 130:
        ds = d.strftime("%Y%m%d")
        df = fetch_ohlcv(ds)
        if df is not None:
            dates.append(ds)
            snaps[ds] = df
            print("ok", ds, len(df), flush=True)
        d -= datetime.timedelta(days=1)
        time.sleep(0.3)

    if len(dates) < 10:
        sys.exit("시세 수집 실패: 거래일 데이터를 충분히 받지 못함")

    dates_sorted = sorted(dates)
    base = dates_sorted[-1]  # 기준일 = 가장 최근 거래일
    print("기준일:", base)

    # 2) 종가/거래량 시계열 구성
    closes, vols = {}, {}
    for ds in dates_sorted:
        df = snaps[ds]
        cs = df["종가"]
        vs = df["거래량"]
        for t in df.index:
            closes.setdefault(t, []).append(int(cs[t]))
            vols.setdefault(t, []).append(int(vs[t]))

    # 3) 기준일 재무지표 (PER/PBR/EPS/BPS/배당)
    fund = stock.get_market_fundamental(base, market="ALL")

    # 4) 외국인 지분율 (실패해도 계속 진행)
    forn = None
    try:
        forn = stock.get_exhaustion_rates_of_foreign_investment(base, market="ALL")["지분율"]
    except Exception as e:
        print("외국인 지분율 생략:", str(e)[:60])

    # 5) 종목명/시장/시가총액
    listing = None
    if fdr is not None:
        try:
            listing = fdr.StockListing("KRX")
            listing = listing[listing["Market"].isin(["KOSPI", "KOSDAQ"])]
        except Exception as e:
            print("FDR 실패, pykrx로 대체:", str(e)[:60])
            listing = None

    if listing is not None:
        rows = [(str(r["Code"]).zfill(6), str(r["Name"]).strip(), str(r["Market"]),
                 int(r["Marcap"]) if pd.notna(r["Marcap"]) else 0)
                for _, r in listing.iterrows()]
    else:
        cap_df = stock.get_market_cap(base, market="ALL")["시가총액"]
        rows = []
        for mkt in ("KOSPI", "KOSDAQ"):
            for t in stock.get_market_ticker_list(base, market=mkt):
                rows.append((t, stock.get_market_ticker_name(t), mkt,
                             int(cap_df.get(t, 0))))

    # 6) 종목별 데이터 조립
    def fval(t, col):
        try:
            v = float(fund.at[t, col])
            return v if pd.notna(v) else 0.0
        except Exception:
            return 0.0

    out = {}
    for code, name, mkt, marcap in rows:
        c = closes.get(code)
        v = vols.get(code)
        if not c or len(c) < 6 or c[-1] <= 0:
            continue

        days = []  # [오늘, 1일전, ..., 4일전] 등락률
        for i in range(1, 6):
            prev, cur = c[-i - 1], c[-i]
            days.append(round((cur - prev) / prev * 100, 2) if prev else 0.0)

        per = round(fval(code, "PER"), 1)
        pbr = round(fval(code, "PBR"), 2)
        div = round(fval(code, "DIV"), 1)
        eps, bps = fval(code, "EPS"), fval(code, "BPS")
        roe = round(eps / bps * 100, 1) if bps > 0 else 0.0

        f = None
        if forn is not None:
            try:
                fv = float(forn.get(code))
                f = round(fv, 1) if pd.notna(fv) else None
            except Exception:
                f = None

        def ret(n):
            if len(c) >= n and c[-n] > 0:
                return round((c[-1] - c[-n]) / c[-n] * 100, 1)
            return None

        out[name] = [
            code, mkt, c[-1], days[0], per, pbr, div, roe,
            int(marcap / 1e8),                     # 시가총액(억원)
            int(sum(v) / len(v)),                  # 3개월 평균 거래량
            v[-2], v[-1],                          # 전일/당일 거래량
            days, f,
            ret(6), ret(21), ret(len(c)),          # 1주/1개월/3개월 수익률
        ]

    meta = {"date": base, "count": len(out),
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open("data.js", "w", encoding="utf-8") as fp:
        fp.write("window.STOCK_META=" + json.dumps(meta, ensure_ascii=False) + ";\n")
        fp.write("window.STOCK_DB=" + json.dumps(out, ensure_ascii=False,
                                                 separators=(",", ":")) + ";\n")
    print("완료:", len(out), "종목 → data.js")


if __name__ == "__main__":
    main()
