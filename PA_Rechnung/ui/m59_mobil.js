// Pfeiffer-Audio Rechnung v3.7.0 - UI-Modul m59_mobil v1.0.0: Bedienung auf iPhone / schmalen Bildschirmen
// Unter 820 px Breite (iPhone, kleines Fenster) oder in der iPhone-App: Menue als Schublade (Knopf oben links),
// Inhalte einspaltig, breite Tabellen seitlich wischbar, Editor untereinander, Dialoge bildschirmfuellend,
// Eingabefelder 16 px (iOS zoomt sonst beim Antippen). Auf dem PC-Bildschirm aendert sich nichts.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const MQ = matchMedia("(max-width: 820px)");
  const IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || /PARechnung-iOS/.test(navigator.userAgent);
  const css = `
  body.mob{--mtop:calc(50px + env(safe-area-inset-top,0px))}
  body.mob #app{display:block!important;height:100vh;height:100dvh;overflow:hidden}
  body.mob #main{height:100%;padding-top:var(--mtop);overflow:auto;-webkit-overflow-scrolling:touch}
  body.mob #side{position:fixed!important;top:0;left:0;bottom:0;width:min(86vw,310px)!important;z-index:150;transform:translateX(-105%);transition:transform .2s ease;
    padding-top:calc(14px + env(safe-area-inset-top,0px));box-shadow:0 0 40px rgba(0,0,0,.35);display:flex!important}
  body.mob.mnav #side{transform:none}
  body.mob #sider,body.mob #sidet,body.mob #sideb{display:none!important}
  body.mob .lspl{display:none}
  #mtop{display:none}
  body.mob #mtop{display:flex;position:fixed;top:0;left:0;right:0;z-index:140;height:var(--mtop);padding:env(safe-area-inset-top,0px) 10px 0;align-items:center;gap:8px;
    background:var(--side);color:#fff;box-shadow:0 2px 10px rgba(0,0,0,.18)}
  #mtop button{border:0;background:none;color:#fff;width:42px;height:42px;display:flex;align-items:center;justify-content:center;border-radius:10px}
  #mtop button:active{background:rgba(255,255,255,.12)}
  #mtop svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round}
  #mtop b{flex:1;font:600 16px var(--disp);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #mshade{display:none}
  body.mob.mnav #mshade{display:block;position:fixed;inset:0;background:rgba(10,8,20,.45);z-index:145}
  body.mob .page{padding:14px 12px calc(70px + env(safe-area-inset-bottom,0px))}
  body.mob .ph h1{font-size:20px}
  body.mob .ph .act{margin-left:0;width:100%}
  body.mob .g2,body.mob .g3,body.mob .split,body.mob .review{grid-template-columns:minmax(0,1fr)!important}
  body.mob .g4,body.mob .g6{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  body.mob .row{flex-wrap:wrap}
  body.mob .row>*{min-width:min(100%,150px)}
  body.mob table.t{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;white-space:nowrap}
  body.mob .card{max-width:100%}
  body.mob .in,body.mob select.in,body.mob textarea.in,body.mob input{font-size:16px}
  body.mob .btn{padding:9px 14px}
  body.mob .btn.sm{padding:6px 10px}
  body.mob .nav{padding:11px 10px}
  body.mob .md,body.mob .md.wide{width:100vw;max-height:100dvh;height:100dvh;border-radius:0;padding-top:env(safe-area-inset-top,0px)}
  body.mob .md .mf{padding-bottom:calc(12px + env(safe-area-inset-bottom,0px));flex-wrap:wrap}
  body.mob .ed,body.mob .ed.nopv,body.mob .ed.lay{display:block!important;height:auto!important;min-height:100%}
  body.mob .ed .pal{max-height:45vh;border-right:0;border-bottom:1px solid var(--line)}
  body.mob .ed .edrow,body.mob .ed .edz{display:block!important;width:auto!important;height:auto!important}
  body.mob .ed .edp-d{width:auto!important;height:auto!important;max-height:none}
  body.mob .ed .edspl,body.mob .ed .edph{display:none!important}
  body.mob .posrow{min-width:560px}
  body.mob .ed .mid{overflow-x:auto}
  body.mob .flwin{max-width:96vw}
  body.mob #selbar{bottom:calc(10px + env(safe-area-inset-bottom,0px));max-width:96vw}
  body.mob #toast{bottom:calc(16px + env(safe-area-inset-bottom,0px));width:94vw}
  body.mob #laybtn{display:none}
  `;
  const st = document.createElement("style"); st.id = "m59css"; st.textContent = css; document.head.appendChild(st);
  const bar = document.createElement("div"); bar.id = "mtop";
  bar.innerHTML = `<button id="mburg" aria-label="Menü"><svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button><b id="mtitle">PA Rechnung</b>
    <button id="msync" aria-label="Abgleichen" title="Jetzt abgleichen" hidden><svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 13.7-5.6L20 9"/><path d="M20 4v5h-5"/><path d="M20 12a8 8 0 0 1-13.7 5.6L4 15"/><path d="M4 20v-5h5"/></svg></button>
    <button id="msrch" aria-label="Suchen"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg></button>`;
  const shade = document.createElement("div"); shade.id = "mshade";
  document.body.appendChild(bar); document.body.appendChild(shade);
  const close = () => document.body.classList.remove("mnav");
  $("#mburg").onclick = () => document.body.classList.toggle("mnav");
  shade.onclick = close;
  $("#msrch").onclick = () => { close(); if (typeof openSearch === "function") openSearch(); else { const g = $("#gsearch"); if (g) g.click(); } };
  $("#msync").onclick = async () => { toast("Abgleich läuft …"); const r = await api("/api/sync/jetzt", {}); if (r && r.ok) toast(r.text || "Abgeglichen"); await reload(); if (typeof view !== "undefined" && EXT.views[view]) go(view); };
  // swipe from the left edge opens the menu, swipe left closes it
  let sx = null, sy = 0;
  addEventListener("touchstart", e => { const t = e.touches[0]; sx = (t.clientX < 22 || document.body.classList.contains("mnav")) ? t.clientX : null; sy = t.clientY; }, {passive: true});
  addEventListener("touchend", e => { if (sx == null) return; const t = e.changedTouches[0], dx = t.clientX - sx;
    if (Math.abs(t.clientY - sy) < 60) { if (dx > 60) document.body.classList.add("mnav"); else if (dx < -60) close(); } sx = null; }, {passive: true});

  function apply(){
    const on = MQ.matches || IOS && innerWidth < 1000;
    document.body.classList.toggle("mob", on);
    if (!on) close();
  }
  (MQ.addEventListener ? MQ.addEventListener("change", apply) : MQ.addListener(apply)); addEventListener("resize", apply); apply();
  if (IOS) document.body.classList.add("ios");

  const origGo = window.go;
  window.go = function(v, ...r){
    close();
    const res = origGo.call(this, v, ...r);
    try { const it = (EXT.nav || []).find(n => n.key === v); const el = document.querySelector(`[data-go="${v}"]`);
      $("#mtitle").textContent = (it && it.label) || (el && [...el.childNodes].filter(n => !(n.classList && n.classList.contains("cnt"))).map(n => n.textContent).join("").trim()) || "PA Rechnung"; } catch (e) {}
    try { $("#main").scrollTop = 0; } catch (e) {}
    return res;
  };
  // the sync button in the top bar only on a paired mobile device
  const origApi = window.api;
  window.api = async function(p, ...r){
    const res = await origApi.call(this, p, ...r);
    if (p === "/api/bootstrap" && res && res.sync) { const b = $("#msync"); if (b) b.hidden = !(res.sync.rolle === "mobil" && res.sync.gekoppelt); }
    return res;
  };
  console.log("INIT UI m59_mobil v1.0.0");
})();
