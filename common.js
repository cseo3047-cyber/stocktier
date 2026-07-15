// Stocktier 공용 로직 (data.js, data_us.js 이후에 로드할 것)

// ===================== Firebase 로그인 설정 =====================
// Firebase 콘솔(console.firebase.google.com) → 프로젝트 설정 ⚙ → 일반 → 내 앱(웹)에서
// 아래 3개 값을 복사해 붙여넣으면 로그인 기능이 자동으로 켜집니다. (비워두면 로그인 버튼은 '준비 중')
window.FIREBASE_CONFIG = {
  apiKey: "AIzaSyAWwuhXh_maZB5mmsmuKU82XgCMAxEUzVE",
  authDomain: "stocktier-10c96.firebaseapp.com",
  projectId: "stocktier-10c96",
};
// App Check(reCAPTCHA v3): 아래에 reCAPTCHA v3 "사이트 키"를 붙여넣으면 App Check가 켜집니다.
// (비워두면 App Check는 적용되지 않고 기존 동작 그대로입니다.)
window.APP_CHECK_SITE_KEY = "";  // App Check 미사용(끔). 나중에 쓰려면 여기에 reCAPTCHA v3 사이트 키를 붙여넣으세요.
// 종목 로고: true = 실제 로고(토스/네이버) 대신 자체 제작 아바타(색깔 원+이니셜) 사용 → 저작권 안전.
//            false = 실제 로고를 쓰고, 못 불러올 때만 아바타로 대체.
window.ST_AVATAR_ONLY = true;
// (선택) 실제 로고를 합법적으로: logo.dev 무료 publishable key를 아래에 넣으면
// 티커/코드로 실제 로고를 불러오고, 없는 종목은 위 아바타로 자동 대체합니다. (미국 커버리지 우수)
window.LOGO_DEV_KEY = "pk_AkrpMP7RS46Y4pA6gzbjdg";
// ================================================================
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

  // 채권 신용등급 방식 티어 (AAA~BBB 투자적격 · BB~D 투기등급)
  const GRADES = [
    { g:"AAA", min:85, label:"안정성 최고 수준의 대장주" },
    { g:"AA",  min:75, label:"매우 우수한 우량주" },
    { g:"A",   min:65, label:"양호한 우량주" },
    { g:"BBB", min:55, label:"보통 · 최저 투자적격급" },
    { g:"BB",  min:45, label:"변동성 큰 투기등급 시작" },
    { g:"B",   min:35, label:"체력 취약 · 요주의" },
    { g:"CCC", min:25, label:"불확실성 상존 · 고위험" },
    { g:"C",   min:10, label:"신용위험 매우 높음" },
    { g:"D",   min:0,  label:"지표 최하위 · 부도급" }
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

  // 관심종목 (localStorage + 로그인 시 Firebase 클라우드 저장)
  function watchGet() { try { return JSON.parse(localStorage.getItem("st_watch")||"[]"); } catch(e){ return []; } }
  function watchSet(list) { localStorage.setItem("st_watch", JSON.stringify(list)); cloudPush(list); }
  function watchHas(src,key) { return watchGet().some(w=>w[0]===src&&w[1]===key); }
  function watchToggle(src,key) {
    let l = watchGet();
    if (watchHas(src,key)) l = l.filter(w=>!(w[0]===src&&w[1]===key));
    else l.push([src,key]);
    watchSet(l);
    return watchHas(src,key);
  }
  // ── 포트폴리오(내 투자) — 관심종목과 별개 저장소 ──
  function pfGet() { try { return JSON.parse(localStorage.getItem("st_pf")||"[]"); } catch(e){ return []; } }
  function pfSet(list) { localStorage.setItem("st_pf", JSON.stringify(list)); }
  function pfHas(src,key) { return pfGet().some(w=>w[0]===src&&w[1]===key); }
  function pfToggle(src,key) {
    let l = pfGet();
    if (pfHas(src,key)) l = l.filter(w=>!(w[0]===src&&w[1]===key));
    else l.push([src,key]);
    pfSet(l);
    return pfHas(src,key);
  }

  // ── Firebase 로그인 + 관심종목 클라우드 동기화 ──
  let fbUser = null;
  const fbOn = () => !!(window.FIREBASE_CONFIG && window.FIREBASE_CONFIG.apiKey);
  function loadScript(src) {
    return new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  async function initFirebase() {
    if (!fbOn() || window.firebase) return;
    try {
      await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
      await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js");
      await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore-compat.js");
      if (window.APP_CHECK_SITE_KEY) await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-check-compat.js");
      firebase.initializeApp(window.FIREBASE_CONFIG);
      // App Check (reCAPTCHA v3) — 사이트 키가 있을 때만 활성화
      if (window.APP_CHECK_SITE_KEY) {
        try { firebase.appCheck().activate(window.APP_CHECK_SITE_KEY, true); }
        catch (e) { console.warn("App Check 활성화 실패:", e); }
      }
      firebase.auth().onAuthStateChanged(async u => {
        fbUser = u;
        updateLoginBtn();
        if (u) { await cloudSync(); await judgePreds(u); }
        else window.ST_PROFILE = null;
        updateLoginBtn();
        document.dispatchEvent(new CustomEvent("st-auth", { detail: u }));
      });
    } catch (e) { console.warn("Firebase 초기화 실패", e); }
  }
  async function cloudSync() {
    try {
      const ref = firebase.firestore().collection("watchlists").doc(fbUser.uid);
      const snap = await ref.get();
      const d = snap.exists ? snap.data() : {};
      window.ST_PROFILE = { nick: d.nick || "", avatar: d.avatar || "", photo: d.photo || "" };
      const local = watchGet();
      // Firestore는 중첩 배열을 지원하지 않으므로 "src|key" 문자열 배열로 저장/복원
      const cloud = (d.items || []).map(w => Array.isArray(w) ? w : String(w).split("|"));
      const seen = new Set(local.map(w => w[0] + "|" + w[1]));
      const merged = local.concat(cloud.filter(w => !seen.has(w[0] + "|" + w[1])));
      localStorage.setItem("st_watch", JSON.stringify(merged));
      await ref.set({ items: merged.map(w => w[0] + "|" + w[1]), updated: Date.now() }, { merge: true });
      if (merged.length !== local.length && !sessionStorage.getItem("st_synced")) {
        sessionStorage.setItem("st_synced", "1");
        location.reload();   // 클라우드 목록을 화면에 반영
      }
    } catch (e) { console.warn("관심종목 동기화 실패", e); }
  }
  function cloudPush(list) {
    if (fbUser && window.firebase) {
      firebase.firestore().collection("watchlists").doc(fbUser.uid)
        .set({ items: (list || []).map(w => w[0] + "|" + w[1]), updated: Date.now() }, { merge: true }).catch(() => {});
    }
  }
  // ── 예측 게임 채점: 로그인 시 어느 페이지에서든 자동 채점 + 결과 팝업 ──
  async function judgePreds(u) {
    try {
      const DD = (window.STOCK_META && window.STOCK_META.date) || "";
      if (!DD || !window.firebase) return;
      const ref = firebase.firestore().collection("games").doc(u.uid);
      const snap = await ref.get();
      if (!snap.exists) return;
      const G = snap.data();
      if (!G.preds) return;
      const judged = [];
      let hit = G.hit || 0, total = G.total || 0;
      let pstreak = G.pstreak || 0, pbest = G.pbest || 0;
      for (const dk of Object.keys(G.preds).sort()) {
        const pd = G.preds[dk];
        if (pd.done || dk >= DD) continue;
        for (const code of Object.keys(pd.picks || {})) {
          const key2 = Object.keys(KR).find(k => KR[k][0] === code);
          if (!key2) continue;
          const cur = KR[key2][2];
          const ok = (cur > pd.price0[code]) === (pd.picks[code] === "up");
          hit += ok ? 1 : 0; total += 1;
          pstreak = ok ? pstreak + 1 : 0;           // 연속 적중
          pbest = Math.max(pbest, pstreak);
          judged.push({ name: key2, pick: pd.picks[code], ok, p0: pd.price0[code], p1: cur, d: dk });
        }
        pd.done = true;
      }
      if (!judged.length) return;
      G.hit = hit; G.total = total; G.lastJudged = judged;
      G.pstreak = pstreak; G.pbest = pbest;
      G.res = judged.slice().reverse().concat(G.res || []).slice(0, 40);   // 채점 이력 (최신순)
      await ref.set(G, { merge: true });
      const okN = judged.filter(j => j.ok).length;
      const pm = document.createElement("div");
      pm.style.cssText = "position:fixed;inset:0;background:#000000aa;display:flex;align-items:center;justify-content:center;z-index:320;";
      pm.innerHTML = `<div style="background:var(--panel);border:1px solid var(--gold-dim);border-radius:16px;width:min(360px,92vw);padding:24px;">
        <div style="font-size:17px;font-weight:800;margin-bottom:4px;">🎯 예측 결과 도착!</div>
        <div style="font-size:12px;color:var(--muted);margin-bottom:14px;">지난 예측 ${judged.length}개 중 <b style="color:${okN>judged.length/2?"var(--up)":"var(--down)"};">${okN}개 적중</b> · 누적 적중률 ${Math.round(hit/total*100)}%</div>
        ${judged.map(j => `<div style="display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid #ffffff0d;font-size:13px;">
          <span style="font-size:16px;">${j.ok ? "⭕" : "❌"}</span>
          <b style="flex:1;">${j.name}</b>
          <span style="color:var(--muted);font-size:12px;">${j.pick === "up" ? "📈 오른다" : "📉 내린다"} 예측</span>
          <span class="num" style="color:var(--dim);font-size:11px;">${num(j.p0)}→${num(j.p1)}</span></div>`).join("")}
        <div style="display:flex;gap:10px;margin-top:16px;">
          <button onclick="location.href='predict.html'" style="flex:1;padding:11px;border-radius:10px;border:none;background:#1d9e75;color:#fff;font-weight:800;font-size:13px;cursor:pointer;">오늘의 예측하러 가기</button>
          <button onclick="this.closest('div[style*=fixed]').remove()" style="padding:11px 18px;border-radius:10px;border:1px solid var(--border);background:transparent;color:var(--muted);font-weight:800;font-size:13px;cursor:pointer;">닫기</button>
        </div></div>`;
      pm.addEventListener("click", e => { if (e.target === pm) pm.remove(); });
      document.body.appendChild(pm);
    } catch (e) { console.warn("예측 채점 실패", e); }
  }

  function updateLoginBtn() {
    const b = document.getElementById("loginbtn");
    if (!b) return;
    if (fbUser) {
      const p = window.ST_PROFILE || {};
      const nm = p.nick || fbUser.displayName || fbUser.email.split("@")[0];
      if (p.photo) {
        b.innerHTML = `<img src="${p.photo}" style="width:19px;height:19px;border-radius:50%;object-fit:cover;vertical-align:-4px;margin-right:6px;">${nm} ▾`;
      } else {
        b.textContent = (p.avatar ? p.avatar + " " : "") + nm + " ▾";
      }
      b.style.borderColor = "var(--gold-dim)"; b.style.color = "var(--gold)";
    } else {
      b.textContent = "로그인";
      b.style.borderColor = ""; b.style.color = "";
    }
  }
  const AUTH_ERR = {
    "auth/invalid-credential": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "auth/invalid-email": "이메일 형식이 올바르지 않습니다.",
    "auth/user-not-found": "등록되지 않은 계정입니다.",
    "auth/wrong-password": "비밀번호가 올바르지 않습니다.",
    "auth/too-many-requests": "시도가 너무 많습니다. 잠시 후 다시 해주세요.",
    "auth/popup-closed-by-user": "로그인 창이 닫혔습니다.",
  };
  function setupLoginUI() {
    const lm = document.createElement("div");
    lm.id = "loginmodal";
    lm.style.cssText = "position:fixed;inset:0;background:#000000aa;display:none;align-items:center;justify-content:center;z-index:300;";
    lm.innerHTML = `<div style="background:var(--panel);border:1px solid var(--border);border-radius:16px;width:min(340px,92vw);padding:24px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <b style="font-size:16px;">로그인</b><span id="lmclose" style="cursor:pointer;color:var(--muted);padding:2px 6px;">✕</span></div>
      <button id="googlelogin" style="width:100%;padding:11px;border-radius:10px;border:1px solid var(--border);background:#fff;color:#1a1a1a;font-weight:800;font-size:13px;cursor:pointer;">Google 계정으로 로그인</button>
      <div style="display:flex;align-items:center;gap:10px;margin:14px 0;color:var(--dim);font-size:11px;"><span style="flex:1;height:1px;background:var(--border);"></span>또는<span style="flex:1;height:1px;background:var(--border);"></span></div>
      <input id="lmemail" type="email" placeholder="이메일" autocomplete="username" style="width:100%;box-sizing:border-box;padding:10px 12px;margin-bottom:8px;border-radius:9px;border:1px solid var(--border);background:var(--panel2);color:var(--text);outline:none;font-size:13px;">
      <input id="lmpw" type="password" placeholder="비밀번호" autocomplete="current-password" style="width:100%;box-sizing:border-box;padding:10px 12px;border-radius:9px;border:1px solid var(--border);background:var(--panel2);color:var(--text);outline:none;font-size:13px;">
      <button id="emaillogin" style="width:100%;padding:11px;border-radius:10px;border:none;background:#1d9e75;color:#fff;font-weight:800;font-size:13px;cursor:pointer;margin-top:10px;">이메일로 로그인</button>
      <div id="lmerr" style="color:#f0708a;font-size:11.5px;margin-top:8px;min-height:15px;"></div>
      <div style="color:var(--dim);font-size:10.5px;line-height:1.7;">이메일 계정은 운영자가 발급합니다.<br>로그인하면 관심종목이 계정에 저장되어 어느 기기에서든 이어집니다.</div>
    </div>`;
    document.body.appendChild(lm);
    const err = m => document.getElementById("lmerr").textContent = m || "";
    lm.addEventListener("click", e => { if (e.target === lm) lm.style.display = "none"; });
    document.getElementById("lmclose").addEventListener("click", () => lm.style.display = "none");
    document.getElementById("googlelogin").addEventListener("click", () => {
      err("");
      firebase.auth().signInWithPopup(new firebase.auth.GoogleAuthProvider())
        .then(() => lm.style.display = "none")
        .catch(e => err(AUTH_ERR[e.code] || "로그인에 실패했습니다."));
    });
    const doEmail = () => {
      err("");
      firebase.auth().signInWithEmailAndPassword(
        document.getElementById("lmemail").value.trim(),
        document.getElementById("lmpw").value)
        .then(() => lm.style.display = "none")
        .catch(e => err(AUTH_ERR[e.code] || "로그인에 실패했습니다."));
    };
    document.getElementById("emaillogin").addEventListener("click", doEmail);
    document.getElementById("lmpw").addEventListener("keydown", e => { if (e.key === "Enter") doEmail(); });
    // 로그인 상태 드롭다운 메뉴 (마이페이지 / 관심종목 / 로그아웃)
    const ud = document.createElement("div");
    ud.id = "userdrop";
    ud.style.cssText = "position:fixed;display:none;background:var(--panel);border:1px solid var(--border);border-radius:11px;min-width:158px;padding:6px;z-index:310;box-shadow:0 10px 26px rgba(0,0,0,.45);";
    const udIc = ic => `<span style="display:inline-block;width:21px;text-align:center;margin-right:4px;">${ic}</span>`;
    ud.innerHTML = `
      <div class="udit" data-act="my" style="padding:9px 13px;border-radius:8px;font-size:13px;color:var(--text);font-weight:600;cursor:pointer;">${udIc("👤")}마이페이지</div>
      <div class="udit" data-act="watch" style="padding:9px 13px;border-radius:8px;font-size:13px;color:var(--text);font-weight:600;cursor:pointer;">${udIc("★")}관심종목</div>
      <div style="height:1px;background:var(--border);margin:5px 8px;"></div>
      <div class="udit" data-act="out" style="padding:9px 13px;border-radius:8px;font-size:13px;color:#f0708a;font-weight:600;cursor:pointer;">${udIc("🚪")}로그아웃</div>`;
    document.body.appendChild(ud);
    const uds = document.createElement("style");
    uds.textContent = "#userdrop .udit:hover{background:var(--panel2);}";
    document.head.appendChild(uds);
    ud.addEventListener("click", e => {
      const it = e.target.closest(".udit");
      const act = it && it.dataset.act;
      ud.style.display = "none";
      if (act === "my") location.href = "mypage.html";
      else if (act === "watch") location.href = "watchlist.html";
      else if (act === "out") { sessionStorage.removeItem("st_synced"); firebase.auth().signOut(); }
    });
    document.addEventListener("click", e => {
      if (!e.target.closest("#userdrop") && !e.target.closest("#loginbtn")) ud.style.display = "none";
    });
    document.getElementById("loginbtn").addEventListener("click", () => {
      if (!fbOn()) { alert("로그인 기능은 준비 중입니다."); return; }
      if (!window.firebase) { alert("로그인 모듈을 불러오는 중입니다. 잠시 후 다시 눌러주세요."); return; }
      if (fbUser) {
        if (ud.style.display === "block") { ud.style.display = "none"; return; }
        const r = document.getElementById("loginbtn").getBoundingClientRect();
        ud.style.top = (r.bottom + 6) + "px";
        ud.style.right = Math.max(8, window.innerWidth - r.right) + "px";
        ud.style.display = "block";
      } else {
        err(""); lm.style.display = "flex";
      }
    });
  }

  // 상단 네비게이션 렌더 + 검색
  function nav(active) {
    const flag = c => `<img src="https://flagcdn.com/w20/${c}.png" alt="" style="width:18px;height:auto;border-radius:2px;vertical-align:-2px;margin-right:7px;">`;
    const drop = (label, list) => {
      const on = list.some(([h]) => h === active) ? "on" : "";
      return `<span class="navdrop">
        <a href="${list[0][0]}" class="${on}">${label} ▾</a>
        <span class="dmenu">${list.map(([h,t]) => `<a href="${h}" class="${active===h?"cur":""}">${t}</a>`).join("")}</span></span>`;
    };
    const link = (h, t) => `<span class="navdrop"><a href="${h}" class="${active===h?"on":""}">${t}</a></span>`;
    const menu =
      drop("오늘의 시장", [["market.html", flag("kr")+"국내 시장"], ["market_us.html", flag("us")+"미국 시장"]]) +
      drop("종목 분석", [["tier.html","📊 티어 랭킹"], ["risk.html","⚠️ 리스크 워치"], ["compare.html","⚔️ 종목 비교"]]) +
      drop("시장 정보", [["calendar.html","📅 실적 캘린더"], ["news.html","📰 뉴스"], ["disclosure.html","📄 공시 충격도"]]) +
      drop("내 투자", [["watchlist.html","⭐ 관심종목"], ["portfolio.html","💼 포트폴리오 진단"], ["simulator.html","🧮 시뮬레이터"]]) +
      drop("게임", [["predict.html","🎯 예측 게임"], ["attend.html","🔥 출석 체크"], ["league.html","🏆 모의투자 리그"]]) +
      link("chart.html", "차트");
    document.getElementById("nav").innerHTML = `
      <a class="brand" href="index.html"><span class="mark"><i></i><i></i><i></i></span>Stocktier</a>
      <div class="menu">${menu}</div>
      <div class="spacer"></div>
      <div class="nsearch"><input id="navq" type="text" placeholder="종목명 또는 코드 검색" autocomplete="off"><span class="sicon">⌕</span><div class="suggest" id="navsug"></div></div>
      <span class="bell" title="알림 (준비 중)" onclick="alert('알림 기능은 준비 중입니다.')">🔔</span>
      <button class="loginbtn" id="loginbtn">로그인</button>`;
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
    ft.innerHTML = notice
      + ` &nbsp;·&nbsp; <a href="privacy.html" style="color:var(--muted);text-decoration:underline;">개인정보 처리방침</a>`
      + ` &nbsp;·&nbsp; <a href="terms.html" style="color:var(--muted);text-decoration:underline;">이용약관</a>`
      + (window.LOGO_DEV_KEY ? ` &nbsp;·&nbsp; <a href="https://logo.dev" target="_blank" rel="noopener" style="color:var(--muted);text-decoration:underline;">Logos by Logo.dev</a>` : "")
      + `<div style="margin-top:7px;font-size:11px;color:var(--dim);">© 2026 Stocktier. All rights reserved. · 콘텐츠·디자인·코드의 무단 복제·배포·도용을 금합니다.</div>`;
    // 주요 목록·표 hover 시 녹색 테두리 (전 페이지 공통 — 페이지별 스타일보다 나중에 주입되어 우선 적용)
    const hoverCss = document.createElement("style");
    hoverCss.textContent = `
      table.stbl tbody tr:hover td, table.ptbl tbody tr:hover td, table.rtbl tbody tr:hover td,
      table.rt tbody tr:hover td, table.ntbl tbody tr:hover td {
        background:#4cd7a50d !important;
        box-shadow: inset 0 1px 0 #4cd7a5, inset 0 -1px 0 #4cd7a5; }
      table.stbl tbody tr:hover td:first-child, table.ptbl tbody tr:hover td:first-child,
      table.rtbl tbody tr:hover td:first-child, table.rt tbody tr:hover td:first-child,
      table.ntbl tbody tr:hover td:first-child {
        box-shadow: inset 1px 1px 0 #4cd7a5, inset 0 -1px 0 #4cd7a5; border-radius:8px 0 0 8px; }
      table.stbl tbody tr:hover td:last-child, table.ptbl tbody tr:hover td:last-child,
      table.rtbl tbody tr:hover td:last-child, table.rt tbody tr:hover td:last-child,
      table.ntbl tbody tr:hover td:last-child {
        box-shadow: inset -1px 1px 0 #4cd7a5, inset 0 -1px 0 #4cd7a5; border-radius:0 8px 8px 0; }
      .nrow2:hover, .evrow:hover, .dmrow:hover, .alrow:hover, .smrow:hover, .flashrow:hover,
      .rowlist .row:hover, .gaugerow:hover, .issrow:hover, .temprow:hover,
      .crow:hover, .nrow:hover, .histrow:hover {
        outline:1px solid #4cd7a5; outline-offset:2px; border-radius:8px; background:#4cd7a50d; box-shadow:none; }
      /* ── 모바일 대응 (전 페이지 공통) ── */
      @media (max-width: 760px) {
        .wrap { padding-left: 10px !important; padding-right: 10px !important; max-width: 100% !important; }
        .nav { flex-wrap: wrap; gap: 8px; padding: 10px 12px; }
        .nav .brand { font-size: 17px; }
        .nav .spacer { display: none; }
        .nav .nsearch { flex: 1; min-width: 0; order: 2; }
        .nav .nsearch input { width: 100% !important; min-width: 0; box-sizing: border-box; }
        .nav .bell { order: 3; }
        .nav .loginbtn { order: 4; }
        .nav .menu { order: 5; width: 100%; flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
        .nav .menu::-webkit-scrollbar { display: none; }
        .nav .menu a { white-space: nowrap; padding: 7px 10px; font-size: 13px; }
        .nav .navdrop .dmenu { position: fixed !important; left: 10px !important; right: 10px !important; }
        .page-title { font-size: 22px !important; }
        .page-sub { font-size: 12px !important; }
        h3 input { width: 110px !important; min-width: 0 !important; }
        table.stbl, table.ptbl, table.rtbl, table.rt, table.ntbl { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }
        .cards4, .cards5, .statgrid, .sumrow { grid-template-columns: repeat(2, minmax(0,1fr)) !important; }
        .seasonrow { gap: 8px; }
        .footer { font-size: 10.5px; }
      }
      @media (max-width: 480px) {
        .cards4, .cards5, .statgrid, .sumrow { grid-template-columns: 1fr !important; }
        .nav .menu a { padding: 7px 8px; font-size: 12.5px; }
      }
      .navdrop.open .dmenu { display: block !important; }`;
    document.head.appendChild(hoverCss);
    // 터치 기기: 드롭다운은 hover가 없으므로 첫 탭 = 메뉴 열기, 두 번째 탭 = 이동
    if (window.matchMedia && window.matchMedia("(hover: none)").matches) {
      document.querySelectorAll(".navdrop > a").forEach(a => {
        const nd = a.parentElement;
        if (!nd.querySelector(".dmenu")) return;
        a.addEventListener("click", e => {
          if (!nd.classList.contains("open")) {
            e.preventDefault();
            document.querySelectorAll(".navdrop.open").forEach(o => o.classList.remove("open"));
            nd.classList.add("open");
          }
        });
      });
      document.addEventListener("click", e => {
        if (!e.target.closest(".navdrop")) document.querySelectorAll(".navdrop.open").forEach(o => o.classList.remove("open"));
      });
    }
    // 로그인 UI + Firebase 초기화
    setupLoginUI();
    initFirebase();
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
    ["2026-07-15","🇺🇸","경제","미국 6월 PPI 발표 (한국시간 당일 밤)"],
    ["2026-07-16","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-07-29","🇺🇸","금리","FOMC 결과 발표 (한국시간 30일 새벽)"],
    ["2026-08-12","🇺🇸","경제","미국 7월 CPI 발표"],
    ["2026-08-13","🇺🇸","경제","미국 7월 PPI 발표"],
    ["2026-08-27","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-09-10","🇰🇷","만기","선물·옵션 동시만기일"],
    ["2026-09-10","🇺🇸","경제","미국 8월 PPI 발표"],
    ["2026-09-11","🇺🇸","경제","미국 8월 CPI 발표"],
    ["2026-09-16","🇺🇸","금리","FOMC 결과 발표 · 점도표 (한국시간 17일 새벽)"],
    ["2026-10-14","🇺🇸","경제","미국 9월 CPI 발표"],
    ["2026-10-15","🇺🇸","경제","미국 9월 PPI 발표"],
    ["2026-10-22","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-10-28","🇺🇸","금리","FOMC 결과 발표 (한국시간 29일 새벽)"],
    ["2026-11-10","🇺🇸","경제","미국 10월 CPI 발표"],
    ["2026-11-13","🇺🇸","경제","미국 10월 PPI 발표"],
    ["2026-11-26","🇰🇷","금리","한국은행 금통위 기준금리 결정"],
    ["2026-12-09","🇺🇸","금리","FOMC 결과 발표 · 점도표 (한국시간 10일 새벽)"],
    ["2026-12-10","🇰🇷","만기","선물·옵션 동시만기일"],
    ["2026-12-10","🇺🇸","경제","미국 11월 CPI 발표"],
    ["2026-12-15","🇺🇸","경제","미국 11월 PPI 발표"],
  ];

  return { KR, US, ALIAS, isReal, GRADES, EVENTS, score, risk, gradeOf, pct, pct2, num, cls, capStr, priceStr,
           displayName, get, all, stockUrl, findStock, suggestions,
           watchGet, watchSet, watchHas, watchToggle, pfGet, pfSet, pfHas, pfToggle, nav, asofText, sampleNotice, spark, qp };
})();

// ── 콘텐츠 무단 복제 억제 (참고: 완전 차단은 불가능한 "억지력" 수준) ──
(function () {
  var inField = function (el) { return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable); };
  // 우클릭(컨텍스트 메뉴) 차단 — 입력창에서는 허용(검색·댓글 붙여넣기 편의)
  document.addEventListener("contextmenu", function (e) { if (!inField(e.target)) e.preventDefault(); });
  // 소스보기(Ctrl+U)·저장(Ctrl+S)·개발자도구(F12, Ctrl+Shift+I/J/C) 단축키 억제
  document.addEventListener("keydown", function (e) {
    var k = (e.key || "").toLowerCase();
    if (e.key === "F12") { e.preventDefault(); return; }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (k === "i" || k === "j" || k === "c")) { e.preventDefault(); return; }
    if ((e.ctrlKey || e.metaKey) && !inField(e.target) && (k === "u" || k === "s")) { e.preventDefault(); }
  });
  // 이미지·로고 드래그 저장 억제
  document.addEventListener("dragstart", function (e) { if (e.target && e.target.tagName === "IMG") e.preventDefault(); });
})();

// ── 종목 로고 아바타 (실제 로고 대신/실패 시 색깔 원 + 이니셜) ──
(function () {
  function avGrad(s) { var h = 0; s = String(s || "?"); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; var u = h % 360; return "linear-gradient(140deg,hsl(" + u + ",62%,57%),hsl(" + ((u + 42) % 360) + ",58%,40%))"; }
  function isLogo(img) { var s = img.getAttribute("src") || img.src || ""; return /tossinvest|pstatic\.net|imgstock/.test(s); }
  function labelOf(img) {
    var l = img.getAttribute("data-nm") || (img.parentElement && (img.parentElement.textContent || "").trim()) || "";
    if (!l) { var m = (img.getAttribute("src") || img.src || "").match(/Stock([A-Za-z]{1,6})(?:\.[ONA])?\.svg/); if (m) l = m[1]; }
    return l;
  }
  function toAvatar(img) {
    if (!img || img.dataset.avdone) return;
    img.dataset.avdone = "1";
    var label = labelOf(img), ch = ((label || "?").trim().charAt(0) || "?").toUpperCase();
    var cs; try { cs = getComputedStyle(img); } catch (_) { cs = {}; }
    var w = parseFloat(cs.width) || img.width || 20, h = parseFloat(cs.height) || img.height || w;
    var span = document.createElement("span");
    span.textContent = ch;
    span.style.cssText = "display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;box-sizing:border-box;overflow:hidden;"
      + "width:" + w + "px;height:" + h + "px;border-radius:50%;background:" + avGrad(label || ch) + ";color:#fff;font-weight:800;"
      + "box-shadow:inset 0 1px 1px rgba(255,255,255,.30),inset 0 0 0 1px rgba(255,255,255,.14),0 1px 3px rgba(0,0,0,.28);"
      + "text-shadow:0 1px 2px rgba(0,0,0,.30);letter-spacing:-.02em;"
      + "font-size:" + Math.max(9, Math.round(w * 0.46)) + "px;line-height:1;"
      + "vertical-align:" + (cs.verticalAlign || "-4px") + ";margin-right:" + (cs.marginRight || "6px") + ";";
    try { img.replaceWith(span); } catch (_) { img.style.visibility = "hidden"; }
  }
  // 1) 로고 로드 실패 시 아바타로 대체 (네이버 폴백까지 실패한 뒤)
  document.addEventListener("error", function (e) {
    var img = e.target;
    if (img && img.tagName === "IMG" && img.dataset.f && isLogo(img)) toAvatar(img);
  }, true);
  // 2) logo.dev 실제 로고 (키 있을 때) → 없는 종목은 아바타로 대체
  var LDV = window.LOGO_DEV_KEY;
  function ldvSrc(img) {
    var src = img.getAttribute("src") || img.src || "", t = null;
    var m = src.match(/Stock([A-Za-z0-9]{1,7})(?:\.[ONA])?\.svg/); if (m) t = m[1];
    if (!t) { var mm = src.match(/icn-sec-fill-(\w+)/); if (mm) t = mm[1]; }
    if (!t) t = img.getAttribute("data-ticker");
    // 미국 티커(알파벳)만 logo.dev 사용, 국내 6자리 코드(숫자)는 아바타로 대체
    return (t && /^[A-Za-z.]+$/.test(t)) ? "https://img.logo.dev/ticker/" + encodeURIComponent(t) + "?token=" + encodeURIComponent(LDV) + "&size=96&format=png" : null;
  }
  function useLdv(img) {
    if (img.dataset.ldv) return; img.dataset.ldv = "1";
    var u = ldvSrc(img); if (!u) { toAvatar(img); return; }
    img.onerror = function () { toAvatar(img); };
    img.src = u;
  }
  function handle(img) { if (LDV) useLdv(img); else if (window.ST_AVATAR_ONLY) toAvatar(img); }
  // 3) 아바타 전용 / logo.dev 모드: 로고 이미지를 감지해 처리
  if (LDV || window.ST_AVATAR_ONLY) {
    var scan = function (root) { if (root && root.querySelectorAll) root.querySelectorAll("img").forEach(function (im) { if (isLogo(im)) handle(im); }); };
    new MutationObserver(function (muts) {
      muts.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) { if (n.tagName === "IMG" && isLogo(n)) handle(n); else scan(n); } }); });
    }).observe(document.documentElement, { childList: true, subtree: true });
    document.addEventListener("DOMContentLoaded", function () { scan(document); });
  }
})();
