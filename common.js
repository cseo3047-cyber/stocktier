// Stocktier 공용 로직 (data.js, data_us.js 이후에 로드할 것)
// 필드: 0코드 1시장 2주가 3등락 4PER 5PBR 6배당 7ROE 8시총 9평균거래량 10전일 11당일 12최근5일 13외인 14주간 15월간 16분기 [17] [18]
window.ST = (function () {
  const SAMPLE_KR = {
    "삼성전자": ["005930","KOSPI",278000,0.18,22.5,3.87,0.6,17.2,16252654,32000000,33525758,28796159,[0.18,-6.25,-6.92,2.75,8.22],46.6,2.1,5.4,12.7],
    "SK하이닉스": ["000660","KOSPI",2186000,5.3,9.8,2.4,0.8,24.5,15579674,4200000,3900000,5615826,[5.3,1.1,-0.9,4.2,0.3],55.1,4.1,11.2,28.4],
    "카카오": ["035720","KOSPI",41850,-2.1,38.5,0.9,0.2,2.4,190000,2900000,2400000,2100000,[-2.1,-0.8,-1.5,0.4,-0.9],27.9,-3.1,-5.2,-8.8]
  };
  const SAMPLE_US = {
    "AAPL": ["AAPL","NASDAQ",254.3,0.8,32.5,48.2,0.4,120.3,38200,52000000,48000000,61000000,[0.8,1.2,-0.5,0.3,1.9],null,2.2,4.8,11.3,"Apple Inc."]
  };
  const KR = (window.STOCK_DB && Object.keys(window.STOCK_DB).length) ? window.STOCK_DB : SAMPLE_KR;
  const US = (window.STOCK_DB_US && Object.keys(window.STOCK_DB_US).length) ? window.STOCK_DB_US : SAMPLE_US;
  const ALIAS = window.KO_ALIAS || { "애플": "AAPL" };
  const isReal = { kr: !!window.STOCK_DB, us: !!window.STOCK_DB_US };

  const GRADES = [
    { g:"S", min:80, label:"챌린저급 대장주" },
    { g:"A", min:65, label:"다이아급 우량주" },
    { g:"B", min:50, label:"플래티넘급 중견주" },
    { g:"C", min:35, label:"골드급 존버주" },
    { g:"D", min:0,  label:"브론즈급 기도주" }
  ];

  function score(s, us) {
    const per=s[4], div=s[6], roe=s[7], cap=s[8], vol3m=s[9], volToday=s[11], days=s[12], forn=s[13];
    const perGood=us?15:10, perMid=us?28:20, perBad=us?80:60;
    const divGood=us?2:3, divMid=us?0.5:1;
    const capBig=us?5000:100000, capSmall=us?20:1000;
    let sc = 50;
    if (per>0 && per<perGood) sc+=15; else if (per>0 && per<perMid) sc+=8; else if (per<=0 || per>perBad) sc-=10;
    if (roe>=15) sc+=15; else if (roe>=8) sc+=8; else if (roe<0) sc-=12;
    if (div>=divGood) sc+=8; else if (div>=divMid) sc+=4;
    if (!us && forn!=null) { if (forn>=30) sc+=8; else if (forn<5) sc-=5; }
    if (vol3m>0 && volToday/vol3m>=1.5) sc+=6;
    const wins = days.filter(d=>d>0).length;
    sc += (wins-2.5)*3;
    if (cap>=capBig) sc+=5; else if (cap<capSmall) sc-=5;
    return Math.max(0, Math.min(100, Math.round(sc)));
  }
  function risk(s) {
    const days=s[12], vol3m=s[9], volToday=s[11], r1w=s[14];
    const avgAbs = days.reduce((a,b)=>a+Math.abs(b),0)/days.length;
    const surge = vol3m>0 ? volToday/vol3m : 0;
    let r = Math.min(60, avgAbs*9);
    if (surge>=3) r+=25; else if (surge>=2) r+=18; else if (surge>=1.5) r+=10;
    const downs = days.filter(d=>d<0).length;
    r += downs*3;
    if (r1w!=null && r1w<=-10) r+=12; else if (r1w!=null && r1w<=-5) r+=6;
    return Math.max(0, Math.min(100, Math.round(r)));
  }
  const gradeOf = sc => GRADES.find(x => sc >= x.min);

  const pct = n => n==null ? "-" : (n>0?"+":"") + Number(n).toFixed(1) + "%";
  const pct2 = n => n==null ? "-" : (n>0?"+":"") + Number(n).toFixed(2) + "%";
  const num = n => Number(n).toLocaleString("ko-KR");
  const cls = n => n>0?"up":(n<0?"down":"flat");
  const capStr = (c,us) => us ? (c>=10000?(c/10000).toFixed(2)+"조 달러":num(c)+"억 달러")
                              : (c>=10000?(c/10000).toFixed(1).replace(/\.0$/,"")+"조원":num(c)+"억원");
  const priceStr = (p,us) => us ? "$"+Number(p).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}) : num(p)+"원";

  // 티커 → 한글명 역방향 맵 (1회 생성 — 매번 전체 탐색하면 검색이 멈춤)
  const ALIAS_REV = {};
  for (const a of Object.keys(ALIAS)) ALIAS_REV[ALIAS[a]] = a;
  function displayName(src, key) {
    if (src==="kr") return key;
    return ALIAS_REV[key] || (US[key] && US[key][17]) || key;
  }
  function get(src, key) { return src==="us" ? US[key] : KR[key]; }
  function all() {
    const out = [];
    for (const k of Object.keys(KR)) out.push({ src:"kr", key:k, e:KR[k] });
    for (const k of Object.keys(US)) out.push({ src:"us", key:k, e:US[k] });
    return out;
  }
  function stockUrl(src, key) { return "stock.html?src="+src+"&k="+encodeURIComponent(key); }

  function findStock(q) {
    const qU = q.toUpperCase();
    if (KR[q]) return ["kr", q];
    if (ALIAS[q] && US[ALIAS[q]]) return ["us", ALIAS[q]];
    if (US[qU]) return ["us", qU];
    const krKeys = Object.keys(KR);
    let k = krKeys.find(x => KR[x][0]===q);
    if (k) return ["kr", k];
    k = krKeys.find(x => x.startsWith(q)) || krKeys.find(x => x.includes(q));
    if (k) return ["kr", k];
    const alias = Object.keys(ALIAS).find(x => x.startsWith(q));
    if (alias && US[ALIAS[alias]]) return ["us", ALIAS[alias]];
    const usKeys = Object.keys(US);
    k = usKeys.find(x => x.startsWith(qU)) || usKeys.find(x => (US[x][17]||"").toUpperCase().includes(qU));
    if (k) return ["us", k];
    return null;
  }
  function suggestions(q, limit) {
    limit = limit || 8;
    const qU = q.toUpperCase(), hits = [];
    for (const k of Object.keys(KR)) {
      if (hits.length>=limit) break;
      if (k.startsWith(q) || KR[k][0].startsWith(q)) hits.push(["kr",k]);
    }
    for (const a of Object.keys(ALIAS)) {
      if (hits.length>=limit) break;
      if (a.startsWith(q) && US[ALIAS[a]] && !hits.some(h=>h[0]==="us"&&h[1]===ALIAS[a])) hits.push(["us",ALIAS[a]]);
    }
    for (const k of Object.keys(US)) {
      if (hits.length>=limit) break;
      if ((k.startsWith(qU) || (US[k][17]||"").toUpperCase().startsWith(qU)) && !hits.some(h=>h[0]==="us"&&h[1]===k)) hits.push(["us",k]);
    }
    if (hits.length<limit) for (const k of Object.keys(KR)) {
      if (hits.length>=limit) break;
      if (!k.startsWith(q) && k.includes(q)) hits.push(["kr",k]);
    }
    return hits;
  }

  // 관심종목 (localStorage)
  function watchGet() { try { return JSON.parse(localStorage.getItem("st_watch")||"[]"); } catch(e){ return []; } }
  function watchSet(list) { localStorage.setItem("st_watch", JSON.stringify(list)); }
  function watchHas(src,key) { return watchGet().some(w=>w[0]===src&&w[1]===key); }
  function watchToggle(src,key) {
    let l = watchGet();
    if (watchHas(src,key)) l = l.filter(w=>!(w[0]===src&&w[1]===key));
    else l.push([src,key]);
    watchSet(l);
    return watchHas(src,key);
  }

  // 상단 네비게이션 렌더 + 검색
  function nav(active) {
    const items = [["tier.html","티어 랭킹"],["watchlist.html","관심종목"],["risk.html","리스크 워치"],["calendar.html","실적 캘린더"],["news.html","뉴스"],["disclosure.html","공시 충격도"],["compare.html","종목 비교"],["portfolio.html","포트폴리오 진단"],["simulator.html","시뮬레이터"]];
    const mktOn = (active==="market.html" || active==="market_us.html") ? "on" : "";
    const mktDrop = `<span class="navdrop">
      <a href="market.html" class="${mktOn}">오늘의 시장 ▾</a>
      <span class="dmenu">
        <a href="market.html" class="${active==="market.html"?"cur":""}">🇰🇷 국내 시장</a>
        <a href="market_us.html" class="${active==="market_us.html"?"cur":""}">🇺🇸 미국 시장</a>
      </span></span>`;
    const menu = mktDrop + items.map(([h,t]) => `<a href="${h}" class="${active===h?"on":""}">${t}</a>`).join("");
    document.getElementById("nav").innerHTML = `
      <a class="brand" href="index.html"><span class="mark"><i></i><i></i><i></i></span>Stocktier</a>
      <div class="menu">${menu}</div>
      <div class="spacer"></div>
      <div class="nsearch"><input id="navq" type="text" placeholder="종목명 또는 코드 검색" autocomplete="off"><span class="sicon">⌕</span><div class="suggest" id="navsug"></div></div>
      <span class="bell" title="알림 (준비 중)" onclick="alert('알림 기능은 준비 중입니다.')">🔔</span>
      <button class="loginbtn" onclick="alert('로그인 기능은 준비 중입니다.')">로그인</button>`;
    const input = document.getElementById("navq"), sug = document.getElementById("navsug");
    input.addEventListener("input", () => {
      const q = input.value.trim();
      if (!q) { sug.style.display="none"; return; }
      const hits = suggestions(q);
      if (!hits.length) { sug.style.display="none"; return; }
      sug.innerHTML = hits.map(([src,k]) => {
        const e = get(src,k);
        return `<div onclick="location.href='${stockUrl(src,k)}'">${displayName(src,k)}<span class="code">${e[0]} · ${e[1]}</span></div>`;
      }).join("");
      sug.style.display="block";
    });
    input.addEventListener("keydown", e => {
      if (e.key==="Enter") {
        const hit = findStock(input.value.trim());
        if (hit) location.href = stockUrl(hit[0], hit[1]);
      }
    });
    document.addEventListener("click", e => { if (!e.target.closest(".nsearch")) sug.style.display="none"; });
    // 모든 페이지 공통 하단 고지 바 (footer가 없으면 자동 생성)
    const notice = "ⓘ 본 서비스는 재미용 지표를 제공하며, 등급·점수는 오락 목적의 가공 수치로 투자 판단의 근거가 될 수 없습니다.";
    let ft = document.querySelector(".footer");
    if (!ft) {
      ft = document.createElement("div");
      ft.className = "footer";
      (document.querySelector(".wrap") || document.body).appendChild(ft);
    }
    ft.textContent = notice;
  }

  function asofText() {
    const p = [];
    if (isReal.kr && window.STOCK_META) { const d=window.STOCK_META.date; p.push(`국내 ${num(window.STOCK_META.count)}종목 ${d.slice(4,6)}/${d.slice(6,8)}`); }
    if (isReal.us && window.STOCK_META_US) { const d=window.STOCK_META_US.date; p.push(`미국 ${num(window.STOCK_META_US.count)}종목 ${d.slice(4,6)}/${d.slice(6,8)}`); }
    return p.length ? p.join(" · ") + " 종가 기준" : "샘플 데이터로 동작 중";
  }
  function sampleNotice(elId) {
    const missing = [];
    if (!isReal.kr) missing.push("국내(data.js)");
    if (!isReal.us) missing.push("미국(data_us.js)");
    if (missing.length && document.getElementById(elId)) {
      const n = document.getElementById(elId);
      n.textContent = missing.join(", ") + " 데이터가 아직 없어 일부는 샘플로 표시됩니다. GitHub Actions 실행 후 실제 데이터로 바뀝니다.";
      n.classList.remove("hidden");
    }
  }

  // 5일 등락 스파크라인 (days는 [오늘,...,4일전] 또는 임의 길이)
  function spark(days, w, h) {
    w = w||70; h = h||24;
    const seq = days.slice().reverse();
    let v = 100; const pts = [v];
    for (const d of seq) { v = v*(1+d/100); pts.push(v); }
    const mn = Math.min(...pts), mx = Math.max(...pts), rg = (mx-mn)||1;
    const xy = pts.map((p,i) => `${(i/(pts.length-1)*w).toFixed(1)},${(h-3-(p-mn)/rg*(h-6)).toFixed(1)}`).join(" ");
    const up = pts[pts.length-1] >= pts[0];
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="flex-shrink:0;"><polyline points="${xy}" fill="none" stroke="${up?"#4cd7a5":"#f0645a"}" stroke-width="1.6"/></svg>`;
  }

  const qp = k => new URLSearchParams(location.search).get(k);

  // 2026년 주요 일정 (확정 일정만, 연 1회 갱신)
  // [날짜, 지역, 구분, 제목]
  const EVENTS = [
    ["2026-07-14","🇺🇸","경제","미국 6월 CPI 발표"],
    ["2026-07-16","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-07-29","🇺🇸","금리","FOMC 결과 발표 (한국시간 30일 새벽)"],
    ["2026-08-27","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-09-10","🇰🇷","만기","선물·옵션 동시만기일"],
    ["2026-09-16","🇺🇸","금리","FOMC 결과 발표 · 점도표 (한국시간 17일 새벽)"],
    ["2026-10-22","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-10-28","🇺🇸","금리","FOMC 결과 발표 (한국시간 29일 새벽)"],
    ["2026-11-26","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-12-09","🇺🇸","금리","FOMC 결과 발표 · 점도표 (한국시간 10일 새벽)"],
    ["2026-12-10","🇰🇷","만기","선물·옵션 동시만기일"],
  ];

  return { KR, US, ALIAS, isReal, GRADES, EVENTS, score, risk, gradeOf, pct, pct2, num, cls, capStr, priceStr,
           displayName, get, all, stockUrl, findStock, suggestions,
           watchGet, watchSet, watchHas, watchToggle, nav, asofText, sampleNotice, spark, qp };
})();
