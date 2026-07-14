// Stocktier 차트 데이터피드 — TradingView 고급차트(Charting Library)의 공개 Datafeed API에
// 우리 사이트 데이터(data.js + ohlc/*.json)를 연결하는 어댑터. (자체 작성 코드)
// 사용: new TradingView.widget({ datafeed: window.makeStocktierDatafeed(), ... })
window.makeStocktierDatafeed = function () {
  var KR = (window.ST && ST.KR) || {};
  var byCode = {};                 // 6자리 코드 → { name, e }
  for (var nm in KR) if (KR[nm] && KR[nm][0]) byCode[KR[nm][0]] = { name: nm, e: KR[nm] };

  var CHARTABLE = null;            // OHLC 파일이 있는 종목 코드 집합
  var idxReady = fetch("ohlc/index.json")
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (a) { CHARTABLE = new Set(a); })
    .catch(function () { CHARTABLE = new Set(); });

  var barCache = {};
  var CFG = { supported_resolutions: ["1D", "1W", "1M"], supports_time: true,
              exchanges: [{ value: "", name: "전체", desc: "전체" }],
              symbols_types: [{ name: "주식", value: "stock" }] };

  function symInfo(code) {
    var o = byCode[code]; if (!o) return null;
    return {
      name: o.name, ticker: code, description: o.name, type: "stock",
      session: "0900-1530", timezone: "Asia/Seoul",
      exchange: o.e[1] || "KRX", listed_exchange: o.e[1] || "KRX",
      format: "price", minmov: 1, pricescale: 1, has_intraday: false,
      supported_resolutions: CFG.supported_resolutions,
      volume_precision: 0, data_status: "endofday", currency_code: "KRW"
    };
  }

  // 주봉/월봉 집계 (일봉 → 주/월)
  function aggregate(bars, res) {
    if (res === "1D" || !bars.length) return bars;
    var out = [], cur = null, ck = null;
    for (var i = 0; i < bars.length; i++) {
      var b = bars[i], d = new Date(b.time), k;
      if (res === "1W") { var x = new Date(b.time); var day = (x.getUTCDay() + 6) % 7; x.setUTCDate(x.getUTCDate() - day); k = x.getUTCFullYear() + "-" + x.getUTCMonth() + "-" + x.getUTCDate(); }
      else { k = d.getUTCFullYear() + "-" + d.getUTCMonth(); }
      if (k !== ck) { if (cur) out.push(cur); cur = { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume }; ck = k; }
      else { cur.high = Math.max(cur.high, b.high); cur.low = Math.min(cur.low, b.low); cur.close = b.close; cur.volume += b.volume; }
    }
    if (cur) out.push(cur);
    return out;
  }

  function loadBars(code) {
    if (barCache[code]) return Promise.resolve(barCache[code]);
    return fetch("ohlc/" + code + ".json")
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (rows) {
        var bars = rows.map(function (a) {
          var s = String(a[0]);
          return { time: Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)),
                   open: +a[1], high: +a[2], low: +a[3], close: +a[4], volume: +a[5] };
        }).filter(function (b) { return b.close > 0; }).sort(function (x, y) { return x.time - y.time; });
        barCache[code] = bars; return bars;
      });
  }

  return {
    onReady: function (cb) { setTimeout(function () { cb(CFG); }, 0); },

    searchSymbols: function (input, exchange, symbolType, onResult) {
      idxReady.then(function () {
        var q = (input || "").toLowerCase(), res = [];
        for (var nm in KR) {
          var code = KR[nm][0];
          if (CHARTABLE && CHARTABLE.size && !CHARTABLE.has(code)) continue;
          if (nm.toLowerCase().indexOf(q) >= 0 || String(code).indexOf(q) >= 0) {
            res.push({ symbol: nm, full_name: nm, ticker: code, description: nm,
                       exchange: KR[nm][1] || "KRX", type: "stock" });
          }
          if (res.length >= 40) break;
        }
        onResult(res);
      });
    },

    resolveSymbol: function (symbolName, onResolve, onError) {
      idxReady.then(function () {
        var code = symbolName;
        if (!byCode[code] && KR[symbolName]) code = KR[symbolName][0];   // 종목명으로 들어온 경우
        var info = symInfo(code);
        if (info && (!CHARTABLE || !CHARTABLE.size || CHARTABLE.has(code))) onResolve(info);
        else onError("종목을 찾을 수 없어요 (차트 지원: 국내 시총 상위 종목)");
      });
    },

    getBars: function (symbolInfo, resolution, periodParams, onResult, onError) {
      loadBars(symbolInfo.ticker).then(function (bars) {
        var bb = aggregate(bars, resolution);
        var from = periodParams.from, to = periodParams.to;
        var sel = bb.filter(function (b) { return b.time / 1000 >= from && b.time / 1000 < to; });
        if (!sel.length && periodParams.firstDataRequest) sel = bb.slice(-Math.min(bb.length, periodParams.countBack || 300));
        onResult(sel, { noData: sel.length === 0 });
      }).catch(function () { onResult([], { noData: true }); });
    },

    subscribeBars: function () {},      // 일봉 EOD — 실시간 갱신 없음
    unsubscribeBars: function () {}
  };
};
