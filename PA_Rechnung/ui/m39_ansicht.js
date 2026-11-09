// Pfeiffer-Audio Rechnung v3.6.1 - UI-Modul m39_ansicht v1.0.0: grosse Ansicht einer Datei (Vorschau vor dem Uebernehmen)
// window.dateiAnsicht(path, opt) - opt: {titel, info (HTML-Zeile), aktionen:[{label, cls, run}], vor(), zurueck(), oeffnen}
// Alle Seiten untereinander, Zoom (Knoepfe, Strg+Mausrad, +/-), "Breite" / "Ganze Seite", Drehen, Blaettern mit Pfeiltasten.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const ST = {zoom: "breite", z: 1, rot: 0};
  let OPEN = null;

  function css(){
    if ($("#m39css")) return;
    const s = document.createElement("style"); s.id = "m39css";
    s.textContent = `.m39{position:fixed;inset:0;z-index:90;background:#2b2937;display:flex;flex-direction:column}
.m39 .m39h{display:flex;align-items:center;gap:10px;padding:10px 16px;background:var(--card,#fff);color:var(--ink);border-bottom:1px solid var(--line);flex-wrap:wrap}
.m39 .m39h .t{font-weight:700;flex:1;min-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.m39 .m39h .z{min-width:52px;text-align:center;font-variant-numeric:tabular-nums}
.m39 .m39b{flex:1;overflow:auto;padding:18px;display:flex;flex-direction:column;align-items:center;gap:14px}
.m39 .m39b img{background:#fff;box-shadow:0 4px 24px rgba(0,0,0,.45);border-radius:3px;max-width:none;flex:none;height:auto;min-height:200px}
.m39 .m39b pre{background:var(--card,#fff);color:var(--ink);padding:16px;border-radius:8px;white-space:pre-wrap;max-width:1000px;width:100%;font-size:13px;line-height:1.45}
.m39 .m39f{display:flex;align-items:center;gap:10px;padding:10px 16px;background:var(--card,#fff);border-top:1px solid var(--line);flex-wrap:wrap}
.m39 .m39f .i{flex:1;min-width:200px;color:var(--ink)}`;
    document.head.appendChild(s);
  }

  function pageW(box){
    const avail = Math.max(300, box.clientWidth - 40);
    if (ST.zoom === "breite") return Math.min(avail, 1400);
    if (ST.zoom === "seite") return Math.min(avail, Math.round((box.clientHeight - 40) / 1.414));
    return Math.round(Math.min(avail, 1400) * ST.z);
  }

  function layout(o){
    const box = $(".m39b", o.el); if (!box || !o.info || o.info.typ === "text") return;
    const w = pageW(box);
    const want = Math.min(2800, Math.max(400, Math.ceil(w * (window.devicePixelRatio || 1) / 400) * 400));
    $$("img[data-s]", box).forEach(im => {
      const src = `/api/ansicht/seite?path=${encodeURIComponent(o.path)}&s=${im.dataset.s}&b=${want}&r=${ST.rot}`;
      if (im.dataset.src !== src) { im.dataset.src = src; im.src = src; }
      im.style.width = w + "px";
    });
    const zl = $(".z", o.el); if (zl) zl.textContent = Math.round(w / Math.min(Math.max(300, box.clientWidth - 40), 1400) * 100) + " %";
  }

  function close(){
    if (!OPEN) return;
    document.removeEventListener("keydown", OPEN.key, true);
    window.removeEventListener("resize", OPEN.rs);
    OPEN.el.remove(); OPEN = null;
  }

  async function dateiAnsicht(path, opt){
    opt = opt || {};
    css(); close();
    const el = document.createElement("div"); el.className = "m39";
    const acts = opt.aktionen || [];
    el.innerHTML = `<div class="m39h"><span class="t" title="${esc(opt.titel || path)}">${esc(opt.titel || String(path).split(/[\\/]/).pop())}</span>
        <button class="btn sm ghost" data-z="-" title="Verkleinern (−)">−</button><span class="z small">100 %</span><button class="btn sm ghost" data-z="+" title="Vergrößern (+)">+</button>
        <button class="btn sm ghost" data-z="breite" title="An Fensterbreite anpassen">Breite</button><button class="btn sm ghost" data-z="seite" title="Ganze Seite sichtbar">Ganze Seite</button>
        <button class="btn sm ghost" data-rot title="Ansicht um 90° drehen (nur Anzeige, die Datei bleibt unverändert)">↻ Drehen</button>
        <button class="btn sm ghost" data-ext title="Mit dem passenden Programm öffnen">${ic("open")} Programm</button>
        <button class="btn sm" data-x title="Schließen (Esc)">✕</button></div>
      <div class="m39b"><div class="small" style="color:#ddd">lädt …</div></div>
      <div class="m39f"><div class="i small">${opt.info || ""}</div>
        ${opt.zurueck ? `<button class="btn" data-prev title="Vorheriger (←)">‹ Vorheriger</button>` : ""}
        ${acts.map((a, i) => `<button class="btn ${a.cls || ""}" data-act="${i}">${esc(a.label)}</button>`).join("")}
        ${opt.vor ? `<button class="btn" data-next title="Nächster (→)">Nächster ›</button>` : ""}</div>`;
    document.body.appendChild(el);
    const o = {el, path, info: null};
    OPEN = o;
    o.key = e => {
      if (OPEN !== o || e.target.matches && e.target.matches("input,textarea,select")) return;
      if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); close(); }
      else if (e.key === "+" || e.key === "=") { zoom("+"); e.preventDefault(); }
      else if (e.key === "-") { zoom("-"); e.preventDefault(); }
      else if (e.key === "ArrowRight" && opt.vor) { e.preventDefault(); opt.vor(); }
      else if (e.key === "ArrowLeft" && opt.zurueck) { e.preventDefault(); opt.zurueck(); }
    };
    o.rs = () => layout(o);
    document.addEventListener("keydown", o.key, true);
    window.addEventListener("resize", o.rs);
    const zoom = k => {
      const box = $(".m39b", el);
      if (k === "breite" || k === "seite") { ST.zoom = k; ST.z = 1; }
      else {
        if (ST.zoom !== "frei") { ST.z = pageW(box) / Math.min(Math.max(300, box.clientWidth - 40), 1400); ST.zoom = "frei"; }
        ST.z = Math.min(4, Math.max(0.25, ST.z * (k === "+" ? 1.25 : 0.8)));
      }
      layout(o);
    };
    $$("[data-z]", el).forEach(b => b.onclick = () => zoom(b.dataset.z));
    $("[data-rot]", el).onclick = () => { ST.rot = (ST.rot + 90) % 360; layout(o); };
    $("[data-x]", el).onclick = close;
    $("[data-ext]", el).onclick = () => api("/api/open", {path});
    const pv = $("[data-prev]", el); if (pv) pv.onclick = () => opt.zurueck();
    const nx = $("[data-next]", el); if (nx) nx.onclick = () => opt.vor();
    $$("[data-act]", el).forEach(b => b.onclick = async () => { const a = acts[+b.dataset.act]; b.disabled = true;
      try { const r = await a.run(); if (r !== false && OPEN === o && !a.offen) close(); } finally { b.disabled = false; } });
    $(".m39b", el).addEventListener("wheel", e => { if (!e.ctrlKey) return; e.preventDefault(); zoom(e.deltaY < 0 ? "+" : "-"); }, {passive: false});
    const info = await api("/api/ansicht/info?path=" + encodeURIComponent(path), undefined, {quiet: true});
    if (OPEN !== o) return;
    const box = $(".m39b", el);
    if (!info || info.ok === false) { box.innerHTML = `<div class="alert warn">Datei kann nicht angezeigt werden${info && info.error ? ": " + esc(info.error) : ""}.</div>`; return; }
    o.info = info;
    if (info.typ === "text") {
      box.innerHTML = `<div class="small" style="color:#ddd">${esc(info.format || "Datei")} – Inhalt als Text${info.fehler ? " · " + esc(info.fehler) : ""}. Mit „Programm“ im Original öffnen.</div><pre>${esc(info.text || "(kein lesbarer Inhalt)")}</pre>`;
      $$("[data-z],[data-rot]", el).forEach(b => b.disabled = true);
      return;
    }
    box.innerHTML = Array.from({length: Math.max(1, info.seiten)}, (_, i) => `<img data-s="${i}" alt="Seite ${i + 1}" loading="lazy">`).join("")
      + (info.seiten > 1 ? `<div class="small" style="color:#ddd">${info.seiten} Seiten</div>` : "");
    layout(o);
  }

  window.dateiAnsicht = dateiAnsicht;
  window.dateiAnsichtSchliessen = close;
  console.log("INIT UI m39_ansicht v1.0.0");
})();
