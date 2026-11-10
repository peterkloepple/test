// PA Rechnung v2.0.12 - Oberflaeche frei gestalten (v3.6.4: Rubrik "Apps" fuer m57)
// - Menue-Rubriken (Stammdaten, Projekte, Finanzen ...) als Bloecke: links/rechts/oben/unten andocken
//   oder als freies Fenster irgendwo schweben lassen (mit Einrasten an Kanten, Fenstern und Raster)
// - Eintraege zwischen Rubriken ziehen, ausblenden, Rubriken anlegen/umbenennen/faerben/einklappen
// - Editor-Bereiche (Bausteine, Arbeitsbereich, Vorschau) andocken (links/rechts/oben/unten) oder schweben
// Gespeichert in den Einstellungen (ui_layout) - gilt fuer diesen Datenordner.
// v1.1.0 (Programm v3.8.0): der Menue-AUFBAU (Rubriken, Reihenfolge, Namen, Farben, eingeklappt, ausgeblendete Eintraege)
//   steht zusaetzlich in "ui_menu" und wird mit iPhone/iPad/zweitem PC abgeglichen (m58). Andock-Seite, Fenster-
//   Positionen und Breiten bleiben je Geraet (ui_layout). Neuere Fassung (Zeitstempel ts) gewinnt.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const GRID = 8, SNAP = 12, EDGE = 44;
  // v2.0.13: the program can be zoomed (body.style.zoom) - positions are kept in screen pixels and converted here
  const ZF = () => parseFloat(document.body.style.zoom) || 1;
  const P = v => (v / ZF()) + "px";
  const COLORS = ["", "#0A84FF", "#30D158", "#FF9F0A", "#FF453A", "#BF5AF2", "#64D2FF", "#FFD60A", "#8E8E93"];
  const CORE = [
    ["_brand", "Logo & Firma", "dash"], ["_search", "Suchen", "search"], ["dash", "Übersicht", "dash"], ["new", "Neues Dokument", "plus"],
    ["inv", "Rechnungen & Angebote", "inv"], ["users", "Kunden", "users"], ["blocks", "Bausteine", "blocks"], ["school", "Unterricht", "school"],
    ["proj", "Projekte", "proj"], ["certs", "Nachweise", "award"], ["abo", "Wartung & Abos", "wrench"], ["beleg", "Belege & Import", "beleg"],
    ["bank", "Bank-Abgleich", "bank"], ["assets", "Anlagen & Inventar", "box"], ["trips", "Fahrten", "car"], ["stat", "Statistik", "stat"],
    ["tax", "Jahresabrechnung & Steuer", "tax"], ["set", "Einstellungen", "set"], ["_timer", "Timer (wenn er läuft)", "clock"], ["_foot", "Hell/Dunkel & Version", "moon"]];
  const ED_NAMES = {pal:"Bausteine", mid:"Arbeitsbereich", pv:"Vorschau"};
  let L = null, edit = false, saveT = null;

  // ---------- model ----------
  const extSec = s => ({Top:"s_kopf", Stammdaten:"Stammdaten", Projekte:"Projekte", Finanzen:"Finanzen", Apps:"Apps"}[s] || "Finanzen");
  function allItems(){
    const m = {};
    CORE.forEach(([k, l, i]) => m[k] = {key:k, label:l, icon:i});
    EXT.nav.forEach(n => m[n.key] = {key:n.key, label:n.label, icon:n.icon || "dash", ext:n});
    return m;
  }
  function defLayout(){
    const ext = s => EXT.nav.filter(n => n.section === s).map(n => n.key);
    return {v:1, zones:{left:224, right:224},
      sections:[
        {id:"s_kopf", title:"", dock:"left", items:["_brand", "_search", "dash", ...ext("Top"), "new", "inv"]},
        {id:"Stammdaten", title:"Stammdaten", dock:"left", items:["users", "blocks", "school", ...ext("Stammdaten")]},
        {id:"Projekte", title:"Projekte", dock:"left", items:["proj", "certs", "abo", ...ext("Projekte")]},
        {id:"Finanzen", title:"Finanzen", dock:"left", items:["beleg", "bank", "assets", "trips", "stat", "tax", ...ext("Finanzen")]},
        {id:"s_sys", title:"", dock:"left", sep:true, items:["set", "_timer", "_foot"]}],
      hidden:[], editor:{pal:{dock:"left", size:250}, mid:{dock:"center"}, pv:{dock:"right", size:420}}};
  }
  const DOCKS = ["left", "right", "top", "bottom", "float"], EDOCKS = ["left", "right", "top", "bottom", "float", "center"];
  const num = (v, d, lo, hi) => { v = Number(v); return isFinite(v) ? Math.min(hi, Math.max(lo, v)) : d; };
  function load(){ try { return load2(); } catch (e) { console.error(e); return defLayout(); } }
  function load2(){
    let l = null;
    try { l = S.settings.ui_layout && typeof S.settings.ui_layout === "object" ? JSON.parse(JSON.stringify(S.settings.ui_layout)) : null; } catch (e) { l = null; }
    if (!l || !Array.isArray(l.sections)) l = defLayout();
    l = mergeMenu(l);
    const ids = new Set();
    l.sections = l.sections.filter(s => s && typeof s === "object" && typeof s.id === "string" && s.id && !ids.has(s.id) && ids.add(s.id));
    l.sections.forEach(s => { if (!Array.isArray(s.items)) s.items = []; s.items = s.items.filter(k => typeof k === "string");
      if (!DOCKS.includes(s.dock)) s.dock = "left"; s.title = typeof s.title === "string" ? s.title : "";
      if (s.color && !/^#[0-9a-fA-F]{3,8}$/.test(s.color)) s.color = "";
      ["x", "y", "w", "h"].forEach(k => { if (s[k] != null) s[k] = num(s[k], 0, 0, 20000); }); });
    if (!l.sections.length) l = defLayout();
    const z = l.zones && typeof l.zones === "object" ? l.zones : {};
    l.zones = {left:num(z.left, 224, 150, 460), right:num(z.right, 224, 150, 460)};
    l.hidden = Array.isArray(l.hidden) ? l.hidden.filter(k => typeof k === "string") : [];
    const de = defLayout().editor, ue = l.editor && typeof l.editor === "object" ? l.editor : {};
    l.editor = {};
    ["pal", "mid", "pv"].forEach(k => { const c = Object.assign({}, de[k], ue[k] && typeof ue[k] === "object" ? ue[k] : {});
      if (!EDOCKS.includes(c.dock) || (c.dock === "center" && k !== "mid")) c.dock = de[k].dock;
      ["size", "x", "y", "w", "h"].forEach(q => { if (c[q] != null) c[q] = num(c[q], undefined, 0, 20000); }); l.editor[k] = c; });
    // new items from modules (or removed ones)
    const items = allItems(), seen = new Set();
    l.sections.forEach(s => { s.items = (s.items || []).filter(k => items[k] && !seen.has(k) && seen.add(k)); });
    l.hidden = l.hidden.filter(k => items[k] && !seen.has(k) && k !== "set" && k !== "_foot");
    l.hidden.forEach(k => seen.add(k));
    Object.values(items).filter(it => !seen.has(it.key)).forEach(it => {
      const sid = it.ext ? extSec(it.ext.section) : "s_kopf";
      // v3.6.4: rubric "Apps" (m57) is created on first use, above the system block
      if (sid === "Apps" && !l.sections.some(x => x.id === "Apps")) {
        const si = l.sections.findIndex(x => x.id === "s_sys");
        l.sections.splice(si >= 0 ? si : l.sections.length, 0, {id:"Apps", title:"Apps", dock:"left", items:[]});
      }
      const s = l.sections.find(s => s.id === sid) || l.sections[l.sections.length - 1];
      if (s) s.items.push(it.key); else l.sections.push({id:"s_neu", title:"Weitere", dock:"left", items:[it.key]});
    });
    ["set", "_foot"].forEach(k => { if (!l.sections.some(s => s.items.includes(k))) (l.sections[0] || (l.sections[0] = {id:"s_kopf", title:"", dock:"left", items:[]})).items.push(k); });
    return l;
  }
  function save(){ clearTimeout(saveT); saveT = setTimeout(() => {
    const m = menuOf(L); L.menu_ts = m.ts; S.settings.ui_layout = L; S.settings.ui_menu = m;
    api("/api/settings/save", {ui_layout:L, ui_menu:m}, {quiet:true}); }, 300); }

  // ---------- v1.1.0: menu structure shared with the other devices ----------
  function menuOf(l){
    return {v:1, ts:Date.now(), hidden:(l.hidden || []).slice(),
      sections:(l.sections || []).map(s => ({id:s.id, title:s.title || "", color:s.color || "", sep:!!s.sep, collapsed:!!s.collapsed, items:(s.items || []).slice()}))};
  }
  function mergeMenu(l){
    const m = S.settings.ui_menu;
    if (!m || typeof m !== "object" || !Array.isArray(m.sections) || !m.sections.length || !(+m.ts > (+l.menu_ts || 0))) return l;
    const loc = {}; (l.sections || []).forEach(s => { if (s && s.id) loc[s.id] = s; });
    l.sections = m.sections.filter(ms => ms && typeof ms.id === "string").map(ms => {
      const b = loc[ms.id] || {dock:"left"};
      const o = {id:ms.id, title:typeof ms.title === "string" ? ms.title : "", dock:b.dock || "left", items:Array.isArray(ms.items) ? ms.items.slice() : []};
      ["x", "y", "w", "h"].forEach(k => { if (b[k] != null) o[k] = b[k]; });      // position stays on this device
      if (ms.color) o.color = ms.color; if (ms.sep) o.sep = true; if (ms.collapsed) o.collapsed = true;
      return o; });
    l.hidden = Array.isArray(m.hidden) ? m.hidden.slice() : [];
    l.menu_ts = +m.ts;
    return l;
  }
  // first start with v3.8.0: a menu arranged on the PC is offered to the devices once
  setTimeout(() => { try {
    if (!S.settings.ui_menu && S.settings.ui_layout && !(S.sync && S.sync.rolle === "mobil")) { L = L || load(); save(); }
  } catch (e) {} }, 4000);

  // ---------- counters (same as the classic sidebar) ----------
  function cnt(it){
    try {
      if (it.ext) return it.ext.cnt ? it.ext.cnt() : "";
      switch (it.key) {
        case "inv": { const o = S.invoices.filter(i => i.typ === "rechnung" && i.status === "offen").length, d = S.invoices.filter(i => i.status === "entwurf").length; return (o + d) || ""; }
        case "users": return S.customers.length;
        case "blocks": return S.articles.length;
        case "school": return S.students.filter(s => s.aktiv).length || "";
        case "proj": return S.projects.filter(p => p.status === "aktiv").length || "";
        case "certs": return S.cert_warn.length ? "⚠ " + S.cert_warn.length : "";
        case "abo": return S.vertraege_due.length || "";
      }
    } catch (e) {}
    return "";
  }
  const isOn = k => view === k || (k === "proj" && view === "project") || (k === "inv" && view === "editor");

  function itemHtml(k, horiz){
    const it = allItems()[k]; if (!it) return "";
    const dr = edit ? ` draggable="true" data-it="${k}"` : "";
    if (k === "_brand") return `<div class="brand${horiz ? " h" : ""}"${dr}><img src="/logo" alt=""><div><b>${esc(S.settings.firma)}</b><span>Rechnung & Verwaltung</span></div></div>`;
    if (k === "_search") return `<button class="nav srch" id="gsearch"${dr}>${ic("search")}<span>Suchen</span><span class="cnt">Strg+K</span></button>`;
    if (k === "_timer") {
      const t = S.settings.timer, tp = t ? S.projects.find(p => p.id == t.project_id) : null;
      if (!t) return edit ? `<div class="nav lghost"${dr}>${ic("clock")}<span>Timer (nur wenn er läuft)</span></div>` : "";
      return `<div class="timerbox"${dr}><div class="small">⏱ läuft · <b id="tmel">${timerElapsed(t)}</b></div><div class="small" style="opacity:.8">${esc(tp ? tp.name : "Projekt")}</div><button class="btn sm" id="tmstop" style="margin-top:6px;width:100%;justify-content:center">Stoppen & buchen</button></div>`;
    }
    if (k === "_foot") return `<div class="sidefoot"${dr}><button class="btn sm ghost" id="theme" style="color:var(--sideink)">${ic("moon")} ${document.documentElement.dataset.theme === "dark" ? "Hell" : "Dunkel"}</button>
      <button class="btn sm ghost" id="laybtn" style="color:var(--sideink)" title="Oberfläche anpassen: Rubriken und Bereiche verschieben">${ic("dash")} Oberfläche</button><span style="margin-left:auto">v${S.version}</span></div>`;
    const c = cnt(it);
    return `<button class="nav ${isOn(k) ? "on" : ""}" data-go="${k}"${dr} title="${esc(it.label)}">${ic(it.icon)}<span>${esc(it.label)}</span>${c ? `<span class="cnt">${c}</span>` : ""}</button>`;
  }
  function secHtml(s, horiz){
    const items = s.items.map(k => itemHtml(k, horiz)).join("");
    const head = (s.title || edit) ? `<div class="lsh" data-sh="${esc(s.id)}">${edit ? `<span class="lgrip" title="Ziehen: verschieben, andocken oder schweben lassen">⠿</span>` : ""}
      <span class="lst" ${edit ? `data-se="${esc(s.id)}" title="Klicken: umbenennen, Farbe"` : ""}>${esc(s.title || (edit ? "(ohne Titel)" : ""))}</span>
      ${s.title && !edit ? `<span class="lcol" data-col="${esc(s.id)}" title="Ein-/Ausklappen">${s.collapsed ? "▸" : "▾"}</span>` : ""}
      ${edit && s.dock !== "float" ? `<span class="lfl" data-fl="${esc(s.id)}" title="Als freies Fenster lösen">⇱</span>` : ""}</div>` : "";
    return `<div class="lsec${horiz ? " h" : ""}${s.sep ? " sep" : ""}${s.collapsed && !edit ? " col" : ""}" data-sec="${esc(s.id)}" style="${s.color ? "--sc:" + s.color : ""}">${head}<div class="lit" data-drop="${esc(s.id)}">${items}${edit && !s.items.length ? `<div class="lempty">Einträge hierher ziehen</div>` : ""}</div></div>`;
  }
  function floatHtml(s){
    const vw = innerWidth, vh = innerHeight;
    const w = Math.min(Math.max(170, s.w || 230), vw - 20), x = Math.min(Math.max(0, s.x || 300), vw - 60), y = Math.min(Math.max(0, s.y || 80), vh - 40);
    const h = s.h ? `height:${Math.min(s.h, vh - y - 4) / ZF()}px;` : "";
    return `<div class="flwin menu" data-fw="${esc(s.id)}" style="left:${x / ZF()}px;top:${y / ZF()}px;width:${w / ZF()}px;${h}${s.color ? "--sc:" + s.color : ""}">
      <div class="flt" data-ft="${esc(s.id)}"><span class="lgrip">⠿</span><b>${esc(s.title || "Menü")}</b><span class="sp"></span>
        <span class="lcol" data-col="${esc(s.id)}" title="Ein-/Ausklappen">${s.collapsed ? "▸" : "▾"}</span>${edit ? `<span data-se="${esc(s.id)}" title="Umbenennen, Farbe">✎</span>` : ""}
        <span data-dk="${esc(s.id)}" title="An die linke Seitenleiste andocken">◧</span></div>
      <div class="flb lit ${s.collapsed ? "col" : ""}" data-drop="${esc(s.id)}">${s.items.map(k => itemHtml(k, false)).join("")}${edit && !s.items.length ? `<div class="lempty">Einträge hierher ziehen</div>` : ""}</div>
      <div class="flr" data-fr="${esc(s.id)}"></div></div>`;
  }

  // ---------- render ----------
  function zoneEl(id, area){
    let z = document.getElementById(id);
    if (!z) { z = document.createElement(id === "side" ? "aside" : "div"); z.id = id; $("#app").appendChild(z); }
    z.style.gridArea = area; return z;
  }
  function flw(){ let f = $("#flw"); if (!f) { f = document.createElement("div"); f.id = "flw"; document.body.appendChild(f); } return f; }

  const _reload = window.reload;
  if (typeof _reload === "function") window.reload = async function(...a){ const r = await _reload.apply(this, a); const nl = load(); if (JSON.stringify(nl) !== JSON.stringify(L)) { L = nl; renderSide(); applyEditor(true); } return r; };
  window.renderSide = function(){
    if (!S) return;
    L = L || load();
    const by = d => L.sections.filter(s => s.dock === d);
    const zl = zoneEl("side", "left"), zr = zoneEl("sider", "right"), zt = zoneEl("sidet", "top"), zb = zoneEl("sideb", "bottom");
    zr.className = "lzone v"; zl.className = "lzone v"; zt.className = "lzone hz"; zb.className = "lzone hz";
    zl.innerHTML = `<div class="lspl" data-zs="left"></div>` + by("left").map(s => secHtml(s, false)).join("");
    zr.innerHTML = `<div class="lspl r" data-zs="right"></div>` + by("right").map(s => secHtml(s, false)).join("");
    zt.innerHTML = by("top").map(s => secHtml(s, true)).join("");
    zb.innerHTML = by("bottom").map(s => secHtml(s, true)).join("");
    const hasL = by("left").length || edit, hasR = by("right").length || edit, hasT = by("top").length || edit, hasB = by("bottom").length || edit;
    zl.style.display = hasL ? "" : "none"; zr.style.display = hasR ? "" : "none"; zt.style.display = hasT ? "" : "none"; zb.style.display = hasB ? "" : "none";
    const app = $("#app");
    app.style.gridTemplateAreas = `"top top top" "left main right" "bottom bottom bottom"`;
    app.style.gridTemplateColumns = `${hasL ? P(by("left").length ? L.zones.left : 120) : "0"} minmax(0,1fr) ${hasR ? P(by("right").length ? L.zones.right : 120) : "0"}`;
    app.style.gridTemplateRows = "auto minmax(0,1fr) auto";
    $("#main").style.gridArea = "main";
    if (edit) { if (!by("right").length) zr.innerHTML = `<div class="lzhint">rechts andocken</div>`; if (!by("top").length) zt.innerHTML = `<div class="lzhint">oben andocken</div>`;
      if (!by("bottom").length) zb.innerHTML = `<div class="lzhint">unten andocken</div>`; if (!by("left").length) zl.innerHTML = `<div class="lzhint">links andocken</div>`; }
    // floating menu windows
    const f = flw(); $$(".flwin.menu", f).forEach(e => e.remove());
    f.insertAdjacentHTML("beforeend", by("float").map(floatHtml).join(""));
    bind();
    document.body.classList.toggle("lay-edit", edit);
    toolbar();
  };

  function bind(){
    $$("[data-go]").forEach(b => { if (b.closest(".lzone, .flwin")) b.onclick = e => { if (edit) { e.preventDefault(); return; } go(b.dataset.go); }; });
    const gs = $("#gsearch"); if (gs) gs.onclick = () => { if (!edit) openSearch(); };
    const th = $("#theme"); if (th) th.onclick = toggleTheme;
    const tm = $("#tmstop"); if (tm) tm.onclick = stopTimer;
    const lb = $("#laybtn"); if (lb) lb.onclick = () => setEdit(!edit);
    $$("[data-col]").forEach(e => e.onclick = ev => { ev.stopPropagation(); const s = sec(e.dataset.col); s.collapsed = !s.collapsed; save(); renderSide(); });
    $$("[data-se]").forEach(e => e.onclick = ev => { ev.stopPropagation(); secDialog(sec(e.dataset.se)); });
    $$("[data-fl]").forEach(e => e.onclick = ev => { ev.stopPropagation(); const s = sec(e.dataset.fl); const r = e.closest(".lsec").getBoundingClientRect();
      Object.assign(s, {dock:"float", x:snapG(r.left + 30), y:snapG(r.top), w:Math.max(200, Math.round(r.width))}); save(); renderSide(); });
    $$("[data-dk]").forEach(e => e.onclick = ev => { ev.stopPropagation(); const s = sec(e.dataset.dk); moveSec(s, "left", 999); save(); renderSide(); });
    $$("[data-sh] .lgrip, .lsec.h [data-sh]").forEach(g => g.onpointerdown = ev => { if (edit) startSecDrag(ev, g.closest("[data-sec]").dataset.sec); });
    $$("[data-ft]").forEach(t => t.onpointerdown = ev => { if (ev.target.closest("[data-col],[data-se],[data-dk]")) return; startSecDrag(ev, t.dataset.ft); });
    $$("[data-fr]").forEach(r => r.onpointerdown = ev => startResize(ev, r.dataset.fr));
    $$("[data-zs]").forEach(z => z.onpointerdown = ev => startZoneResize(ev, z.dataset.zs));
    if (edit) bindItemDnd();
  }
  const sec = id => L.sections.find(s => s.id === id);
  const snapG = v => Math.round(v / GRID) * GRID;

  // ---------- item drag & drop (edit mode) ----------
  function bindItemDnd(){
    let drag = null;
    $$("[data-it]").forEach(el => {
      el.ondragstart = e => { drag = el.dataset.it; e.dataTransfer.setData("text/plain", drag); e.dataTransfer.effectAllowed = "move"; setTimeout(() => el.classList.add("ldrag"), 0); };
      el.ondragend = () => { el.classList.remove("ldrag"); $$(".ldropmark").forEach(m => m.remove()); };
    });
    const targets = [...$$("[data-drop]"), $("#laytray")].filter(Boolean);
    targets.forEach(t => {
      t.ondragover = e => { if (!drag) return; e.preventDefault(); $$(".ldropmark").forEach(m => m.remove());
        const before = itemAt(t, e); const mk = document.createElement("div"); mk.className = "ldropmark"; before ? t.insertBefore(mk, before) : t.appendChild(mk); };
      t.ondragleave = e => { if (!t.contains(e.relatedTarget)) $$(".ldropmark", t).forEach(m => m.remove()); };
      t.ondrop = e => { e.preventDefault(); if (!drag) return; const k = drag; drag = null;
        const before = itemAt(t, e); const bk = before && before.dataset ? before.dataset.it : null;
        L.sections.forEach(s => s.items = s.items.filter(x => x !== k)); L.hidden = L.hidden.filter(x => x !== k);
        if (t.id === "laytray") { if (k === "set" || k === "_foot") { toast("„Einstellungen“ und „Oberfläche“ müssen im Menü bleiben", true); L.sections[0].items.push(k); } else L.hidden.push(k); }
        else { const s = sec(t.dataset.drop); const i = bk ? s.items.indexOf(bk) : -1; i >= 0 ? s.items.splice(i, 0, k) : s.items.push(k); }
        save(); renderSide(); };
    });
  }
  function itemAt(t, e){
    const its = [...t.querySelectorAll(":scope > [data-it]")].filter(x => !x.classList.contains("ldrag"));
    const horiz = !!t.closest(".lsec.h");
    return its.find(x => { const r = x.getBoundingClientRect(); return horiz ? e.clientX < r.left + r.width / 2 : e.clientY < r.top + r.height / 2; }) || null;
  }

  // ---------- section drag (dock / float / snap) ----------
  function dockTarget(x, y){
    const vw = innerWidth, vh = innerHeight;
    const hit = id => { const z = document.getElementById(id); if (!z || z.style.display === "none") return false; const r = z.getBoundingClientRect(); return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom; };
    if (x < EDGE || hit("side")) return "left";
    if (x > vw - EDGE || hit("sider")) return "right";
    if (y < EDGE / 2 || hit("sidet")) return "top";
    if (y > vh - EDGE / 2 || hit("sideb")) return "bottom";
    return null;
  }
  function dockIndex(zone, x, y){
    const list = L.sections.filter(s => s.dock === zone);
    const id = {left:"side", right:"sider", top:"sidet", bottom:"sideb"}[zone];
    const els = $$(`#${id} > .lsec`);
    for (let i = 0; i < els.length; i++) { const r = els[i].getBoundingClientRect(); if (zone === "top" || zone === "bottom" ? x < r.left + r.width / 2 : y < r.top + r.height / 2) return i; }
    return list.length;
  }
  function moveSec(s, zone, idx){
    L.sections = L.sections.filter(x => x !== s); s.dock = zone;
    const same = L.sections.filter(x => x.dock === zone);
    const ref = same[idx];
    if (ref) L.sections.splice(L.sections.indexOf(ref), 0, s); else {
      const last = same[same.length - 1]; L.sections.splice(last ? L.sections.indexOf(last) + 1 : L.sections.length, 0, s); }
  }
  function snapFloat(id, x, y, w, h){
    const vw = innerWidth, vh = innerHeight;
    const xs = [0, vw], ys = [0, vh];
    $$(".flwin").forEach(f => { if (f.dataset.fw === id || f.dataset.fe === id) return; const r = f.getBoundingClientRect(); xs.push(r.left, r.right); ys.push(r.top, r.bottom); });
    ["side", "sider", "sidet", "sideb"].forEach(z => { const e = document.getElementById(z); if (e && e.style.display !== "none") { const r = e.getBoundingClientRect(); if (r.width && r.height) { xs.push(r.left, r.right); ys.push(r.top, r.bottom); } } });
    const best = (v, size, cands) => { let bv = snapG(v), bd = SNAP + 1;
      cands.forEach(c => { [[c, 0], [c - size, size]].forEach(([t]) => { const d = Math.abs(v - t); if (d < bd && d <= SNAP) { bd = d; bv = t; } }); }); return bv; };
    return {x:Math.min(Math.max(0, best(x, w, xs)), vw - 60), y:Math.min(Math.max(0, best(y, h, ys)), vh - 30)};
  }
  function ghost(x, y){ let g = $("#laydock"); if (!g) { g = document.createElement("div"); g.id = "laydock"; document.body.appendChild(g); } return g; }
  function showDock(zone){
    const g = ghost(); if (!zone) { g.style.display = "none"; return; }
    const vw = innerWidth, vh = innerHeight, t = 70;
    const r = {left:[0, 0, Math.max(t, L.zones.left), vh], right:[vw - Math.max(t, L.zones.right), 0, Math.max(t, L.zones.right), vh], top:[0, 0, vw, t], bottom:[0, vh - t, vw, t]}[zone];
    Object.assign(g.style, {display:"block", left:P(r[0]), top:P(r[1]), width:P(r[2]), height:P(r[3])});
  }
  function startSecDrag(ev, id){
    const s = sec(id); if (!s) return;
    ev.preventDefault();
    const sx = ev.clientX, sy = ev.clientY; let moved = false, win = null, offX = 0, offY = 0, zone = null;
    const src = document.querySelector(`[data-fw="${CSS.escape(id)}"]`) || document.querySelector(`[data-sec="${CSS.escape(id)}"]`);
    const r0 = src.getBoundingClientRect();
    const mv = e => {
      if (!moved && Math.hypot(e.clientX - sx, e.clientY - sy) < 6) return;
      if (!moved) { moved = true;
        if (s.dock !== "float") { Object.assign(s, {dock:"float", x:r0.left, y:r0.top, w:Math.max(200, Math.round(Math.min(r0.width, 320)))}); renderSide(); }
        win = document.querySelector(`[data-fw="${CSS.escape(id)}"]`); const r = win.getBoundingClientRect(); offX = sx - r.left; offY = sy - r.top; win.classList.add("moving"); }
      zone = dockTarget(e.clientX, e.clientY); showDock(zone);
      const r = win.getBoundingClientRect(); const p = snapFloat(id, e.clientX - offX, e.clientY - offY, r.width, r.height);
      win.style.left = P(p.x); win.style.top = P(p.y); s.x = p.x; s.y = p.y;
    };
    const up = e => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); showDock(null);
      if (!moved) return;
      if (zone) moveSec(s, zone, dockIndex(zone, e.clientX, e.clientY));
      save(); renderSide(); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up);
  }
  function startResize(ev, id){
    ev.preventDefault(); ev.stopPropagation();
    const s = sec(id), win = document.querySelector(`[data-fw="${CSS.escape(id)}"]`); const r = win.getBoundingClientRect();
    const sx = ev.clientX, sy = ev.clientY;
    const mv = e => { s.w = Math.max(170, snapG(r.width + e.clientX - sx)); s.h = Math.max(80, snapG(r.height + e.clientY - sy)); win.style.width = P(s.w); win.style.height = P(s.h); };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); save(); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up);
  }
  function startZoneResize(ev, z){
    ev.preventDefault();
    const sx = ev.clientX, w0 = L.zones[z];
    const mv = e => { L.zones[z] = Math.min(460, Math.max(150, Math.round(w0 + (z === "left" ? 1 : -1) * (e.clientX - sx)))); const app = $("#app"); const c = app.style.gridTemplateColumns.split(" ");
      if (z === "left") c[0] = P(L.zones.left); else c[c.length - 1] = P(L.zones.right); app.style.gridTemplateColumns = c.join(" "); };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); save(); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up);
  }

  // ---------- section dialog ----------
  async function secDialog(s){
    let col = s.color || "";
    const r = await modal("Rubrik bearbeiten", `<div class="fr"><label class="f">Titel (leer = ohne Überschrift)<input class="in" id="lst" value="${esc(s.title || "")}"></label>
      <div class="f">Farbe<div class="row" id="lcols" style="gap:6px;margin-top:4px">${COLORS.map(c => `<button type="button" class="lcb ${c === col ? "on" : ""}" data-c="${c}" style="background:${c || "transparent"}" title="${c || "keine"}">${c ? "" : "–"}</button>`).join("")}</div></div>
      <label class="chk"><input type="checkbox" id="lsep" ${s.sep ? "checked" : ""}> Trennlinie darüber</label>
      <div class="small muted">${s.items.length} Eintrag/Einträge · ${({left:"links angedockt", right:"rechts angedockt", top:"oben angedockt", bottom:"unten angedockt", float:"freies Fenster"})[s.dock]}</div></div>`,
      [...(L.sections.length > 1 ? [{label:"Rubrik auflösen", cls:"danger", value:"del"}] : []), {label:"Abbrechen"}, {label:"Übernehmen", cls:"pri", value:"ok", onClick: async mb => {
        s.title = $("#lst", mb).value.trim(); s.color = col; s.sep = $("#lsep", mb).checked; }}], false,
      mb => $$(".lcb", mb).forEach(b => b.onclick = () => { col = b.dataset.c; $$(".lcb", mb).forEach(x => x.classList.toggle("on", x === b)); }));
    if (r === "del") { const tgt = L.sections.find(x => x !== s); tgt.items.push(...s.items); L.sections = L.sections.filter(x => x !== s); }
    if (r) { save(); renderSide(); }
  }

  // ---------- edit mode toolbar ----------
  function toolbar(){
    let tb = $("#laybar");
    if (!edit) { if (tb) tb.remove(); return; }
    if (!tb) { tb = document.createElement("div"); tb.id = "laybar"; document.body.appendChild(tb); }
    const items = allItems();
    tb.innerHTML = `<b>Oberfläche anpassen</b><span class="small" style="opacity:.8">Rubrik am ⠿ ziehen: an eine Kante = andocken, sonst freies Fenster · Einträge per Ziehen verschieben</span>
      <button class="btn sm" id="laynew">${ic("plus")} Rubrik</button>
      <div id="laytray" class="lit" title="Hierher ziehen = ausblenden">${L.hidden.length ? L.hidden.map(k => `<span class="ltray" draggable="true" data-it="${k}">${esc(items[k].label)}</span>`).join("") : `<span class="small" style="opacity:.7">ausgeblendet: –</span>`}</div>
      <button class="btn sm" id="layfont" title="Schrift und Größe des Programms">Schrift …</button><button class="btn sm" id="layreset">Zurücksetzen</button><button class="btn sm pri" id="laydone">${ic("check")} Fertig</button>`;
    $("#laynew").onclick = () => { L.sections.push({id:"s_" + Date.now().toString(36), title:"Neue Rubrik", dock:"float", x:snapG(innerWidth / 2 - 110), y:120, w:220, items:[]}); save(); renderSide(); };
    $("#layreset").onclick = async () => { if (!await confirmBox("Menü und Editor-Bereiche auf die Standard-Anordnung zurücksetzen?", "Zurücksetzen")) return; L = defLayout(); save(); renderSide(); applyEditor(true); };
    $("#laydone").onclick = () => setEdit(false);
    $("#layfont").onclick = () => { setEdit(false); try { setTab = "docs"; } catch (e) {} go("set"); setTimeout(() => { const u = $("#uifonthost"); if (u) u.scrollIntoView({behavior:"smooth"}); }, 600); };
    bindItemDnd();
  }
  function setEdit(on){ edit = on; renderSide(); applyEditor(true); if (!on) toast("Oberfläche gespeichert"); }
  window.layoutEdit = setEdit;
  addEventListener("keydown", e => { if (edit && e.key === "Escape" && !$(".mb")) setEdit(false);
    if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "l") { e.preventDefault(); setEdit(!edit); } });
  let rsT = null;
  addEventListener("resize", () => { clearTimeout(rsT); rsT = setTimeout(() => { clampFloats(); clampDocked(); }, 80); });

  // ---------- editor areas ----------
  function applyEditor(force){
    const ed = $("#main .ed");
    const f = flw();
    if (!ed) { $$(".flwin.edp", f).forEach(e => e.remove()); return; }
    if (ed.dataset.lay && !force) return;
    L = L || load();
    const parts = {};
    if (!ed.dataset.edid) ed.dataset.edid = Math.random().toString(36).slice(2);
    const eid = ed.dataset.edid;
    // floating panels that belong to an older editor (e.g. invoice -> letter) are dropped
    $$(".flwin.edp", f).forEach(e => { if (e.dataset.edid !== eid) e.remove(); });
    ["pal", "mid", "pv"].forEach(k => { const el = ed.querySelector(`:scope .${k}`) || document.querySelector(`.flwin.edp[data-edid="${eid}"] .${k}`); if (el) parts[k] = el; });
    if (!parts.mid) return;
    const nopv = ed.classList.contains("nopv");
    const keep = {}; Object.entries(parts).forEach(([k, el]) => { keep[k] = el.scrollTop; });
    const act = document.activeElement, selS = act && act.selectionStart, selE = act && act.selectionEnd;
    ed.dataset.lay = "1"; ed.classList.add("lay");
    ed.style.gridTemplateColumns = "";
    let wrap = ed.querySelector(":scope > .edl");
    if (!wrap) { wrap = document.createElement("div"); wrap.className = "edl"; wrap.innerHTML = `<div class="edz t"></div><div class="edrow"><div class="edz l"></div><div class="edc"></div><div class="edz r"></div></div><div class="edz b"></div>`; ed.appendChild(wrap); }
    const Z = {top:$(".edz.t", wrap), left:$(".edz.l", wrap), right:$(".edz.r", wrap), bottom:$(".edz.b", wrap), center:$(".edc", wrap)};
    Object.values(Z).forEach(z => z.innerHTML = "");
    $$(".flwin.edp", f).forEach(e => e.remove());
    const order = ["pal", "pv", "mid"];
    order.forEach(k => {
      const p = parts[k]; if (!p) return;
      if (k === "pv" && nopv) { p.style.display = "none"; Z.right.appendChild(p); return; }
      p.style.display = "";
      const c = L.editor[k] || {dock:k === "mid" ? "center" : k === "pal" ? "left" : "right"};
      let dock = c.dock || "left";
      if (k === "mid" && dock === "center") { Z.center.appendChild(p); return; }
      if (dock === "float") {
        const vw = innerWidth, vh = innerHeight;
        const w = Math.min(Math.max(220, c.w || 360), vw - 20), h = Math.min(Math.max(160, c.h || 520), vh - 20);
        const x = Math.min(Math.max(0, c.x || 260), vw - 80), y = Math.min(Math.max(0, c.y || 70), vh - 40);
        const win = document.createElement("div"); win.className = "flwin edp"; win.dataset.fe = k; win.dataset.edid = eid;
        win.style.cssText = `left:${P(x)};top:${P(y)};width:${P(w)};height:${P(h)}`;
        win.innerHTML = `<div class="flt" data-et="${k}"><span class="lgrip">⠿</span><b>${ED_NAMES[k]}</b><span class="sp"></span>${dockBtns(k)}</div><div class="ed edfloat"></div><div class="flr" data-er="${k}"></div>`;
        $(".edfloat", win).appendChild(p); f.appendChild(win); return;
      }
      const box = document.createElement("div"); box.className = "edp-d " + dock; box.dataset.ep = k;
      const sz = c.size || (k === "pal" ? 250 : 420);
      if (dock === "left" || dock === "right") box.style.width = P(sz); else box.style.height = P(sz);
      if (edit) box.insertAdjacentHTML("beforeend", `<div class="edph" data-et="${k}"><span class="lgrip">⠿</span><b>${ED_NAMES[k]}</b><span class="sp"></span>${dockBtns(k)}</div>`);
      box.appendChild(p);
      box.insertAdjacentHTML("beforeend", `<div class="edspl ${dock}" data-es="${k}"></div>`);
      Z[dock].appendChild(box);
    });
    if (!Z.center.children.length) Z.center.innerHTML = `<div class="lzhint" style="margin:40px auto">Arbeitsbereich schwebt als Fenster</div>`;
    clampDocked();
    Object.entries(parts).forEach(([k, el]) => { if (keep[k]) el.scrollTop = keep[k]; });
    if (act && act !== document.body && act.isConnected && document.activeElement !== act) { try { act.focus({preventScroll:true}); if (selS != null) act.setSelectionRange(selS, selE); } catch (e) {} }
    if (edit && parts.mid && Z.center.contains(parts.mid)) Z.center.insertAdjacentHTML("afterbegin", `<div class="edph" data-et="mid"><span class="lgrip">⠿</span><b>Arbeitsbereich</b><span class="sp"></span>${dockBtns("mid")}</div>`);
    bindEditor();
  }
  // docked areas never take more room than there is (window got smaller, other monitor ...)
  function clampDocked(){
    const ed = $("#main .ed.lay"); if (!ed) return;
    const row = $(".edrow", ed), r = (row || ed).getBoundingClientRect(), MINC = 320, MINS = 140;
    const side = $$(".edz.l > .edp-d, .edz.r > .edp-d", ed), tb = $$(".edz.t > .edp-d, .edz.b > .edp-d", ed);
    const hasCenter = !!$(".edc .mid", ed);
    const availW = Math.max(MINS * side.length, r.width - (hasCenter ? MINC : 0)), availH = Math.max(MINS * tb.length, ed.getBoundingClientRect().height - 260);
    const fit = (els, avail, dim) => { const want = els.map(b => (L.editor[b.dataset.ep] || {}).size || 250); const sum = want.reduce((a, b) => a + b, 0);
      const k = sum > avail ? avail / sum : 1; els.forEach((b, i) => b.style[dim] = P(Math.max(MINS, Math.floor(want[i] * k)))); };
    fit(side, availW, "width"); fit(tb, availH, "height");
  }
  function clampFloats(){
    $$(".flwin").forEach(w => { const r = w.getBoundingClientRect(); const x = Math.min(Math.max(0, r.left), innerWidth - 60), y = Math.min(Math.max(0, r.top), innerHeight - 30);
      if (x !== r.left) w.style.left = P(x); if (y !== r.top) w.style.top = P(y);
      if (r.height > innerHeight - y) w.style.height = P(Math.max(120, innerHeight - y - 4)); if (r.width > innerWidth) w.style.width = P(innerWidth - 10); });
  }
  function dockBtns(k){
    const b = [["left", "◧", "links andocken"], ["right", "◨", "rechts andocken"], ["top", "⬒", "oben andocken"], ["bottom", "⬓", "unten andocken"], ["float", "⇱", "frei schweben"]];
    if (k === "mid") b.unshift(["center", "▣", "in die Mitte"]);
    return b.map(([d, s, t]) => `<span class="edb" data-ed="${k}:${d}" title="${t}">${s}</span>`).join("");
  }
  function bindEditor(){
    $$("[data-ed]").forEach(b => b.onclick = e => { e.stopPropagation(); const [k, d] = b.dataset.ed.split(":"); setEd(k, d); });
    $$("[data-et]").forEach(t => t.onpointerdown = ev => { if (ev.target.closest("[data-ed]")) return; startEdDrag(ev, t.dataset.et); });
    $$("[data-er]").forEach(r => r.onpointerdown = ev => { ev.preventDefault(); const k = r.dataset.er, win = r.closest(".flwin"), rr = win.getBoundingClientRect(), sx = ev.clientX, sy = ev.clientY, c = L.editor[k];
      const mv = e => { c.w = Math.max(220, snapG(rr.width + e.clientX - sx)); c.h = Math.max(160, snapG(rr.height + e.clientY - sy)); win.style.width = P(c.w); win.style.height = P(c.h); };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); save(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up); });
    $$("[data-es]").forEach(sp => sp.onpointerdown = ev => { ev.preventDefault(); const k = sp.dataset.es, box = sp.parentNode, c = L.editor[k], d = c.dock;
      const r0 = box.getBoundingClientRect(), sx = ev.clientX, sy = ev.clientY;
      const mv = e => { if (d === "left") c.size = r0.width + e.clientX - sx; else if (d === "right") c.size = r0.width - (e.clientX - sx);
        else if (d === "top") c.size = r0.height + e.clientY - sy; else c.size = r0.height - (e.clientY - sy);
        c.size = Math.max(140, Math.min(Math.round(c.size), (d === "left" || d === "right" ? innerWidth : innerHeight) - 200));
        if (d === "left" || d === "right") box.style.width = P(c.size); else box.style.height = P(c.size); };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); save(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up); });
  }
  function setEd(k, d){
    const c = L.editor[k] = Object.assign({}, L.editor[k] || {});
    if (d === "float") { const el = document.querySelector(`.ed .${k}, .flwin.edp .${k}`); const r = el ? el.getBoundingClientRect() : {left:300, top:80, width:380, height:520};
      Object.assign(c, {x:snapG(Math.max(10, r.left + 30)), y:snapG(Math.max(10, r.top + 30)), w:snapG(Math.min(Math.max(260, r.width), 640)), h:snapG(Math.min(Math.max(240, r.height), innerHeight - 120))}); }
    if (d === "center" && k !== "mid") d = "right";
    if (k === "mid" && d !== "center" && d !== "float" && !c.size) c.size = 520;
    c.dock = d; save(); applyEditor(true);
  }
  function edTarget(x, y){
    const ed = $("#main .ed"); if (!ed) return null;
    const r = ed.getBoundingClientRect();
    if (x < r.left || x > r.right || y < r.top || y > r.bottom) return null;
    if (x < r.left + EDGE * 1.5) return "left";
    if (x > r.right - EDGE * 1.5) return "right";
    if (y < r.top + EDGE) return "top";
    if (y > r.bottom - EDGE) return "bottom";
    return null;
  }
  function showEdDock(z){
    const g = ghost(); const ed = $("#main .ed");
    if (!z || !ed) { g.style.display = "none"; return; }
    const r = ed.getBoundingClientRect(), t = 90;
    const q = {left:[r.left, r.top, t, r.height], right:[r.right - t, r.top, t, r.height], top:[r.left, r.top, r.width, t], bottom:[r.left, r.bottom - t, r.width, t], center:[r.left + r.width / 4, r.top + r.height / 4, r.width / 2, r.height / 2]}[z];
    Object.assign(g.style, {display:"block", left:P(q[0]), top:P(q[1]), width:P(q[2]), height:P(q[3])});
  }
  function startEdDrag(ev, k){
    ev.preventDefault();
    const c = L.editor[k] = Object.assign({}, L.editor[k] || {});
    const sx = ev.clientX, sy = ev.clientY; let moved = false, win = null, offX = 0, offY = 0, zone = null;
    const mv = e => {
      if (!moved && Math.hypot(e.clientX - sx, e.clientY - sy) < 6) return;
      if (!moved) { moved = true;
        if (c.dock !== "float") { setEd(k, "float"); }
        win = document.querySelector(`.flwin.edp[data-fe="${k}"]`); if (!win) return; const r = win.getBoundingClientRect(); offX = Math.min(sx - r.left, r.width - 40); offY = 14; win.classList.add("moving"); }
      if (!win) return;
      zone = edTarget(e.clientX, e.clientY);
      if (k === "mid" && !zone) { const ed = $("#main .ed"); if (ed) { const r = ed.getBoundingClientRect(); if (e.clientX > r.left + r.width / 4 && e.clientX < r.right - r.width / 4 && e.clientY > r.top + r.height / 4 && e.clientY < r.bottom - r.height / 4) zone = "center"; } }
      showEdDock(zone);
      const r = win.getBoundingClientRect(); const p = snapFloat(k, e.clientX - offX, e.clientY - offY, r.width, r.height);
      win.style.left = P(p.x); win.style.top = P(p.y); c.x = p.x; c.y = p.y; L.editor[k] = c;
    };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); showEdDock(null); if (!moved) return;
      if (zone) setEd(k, zone); else save(); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up);
  }
  // click on a floating window brings it to the front
  let zTop = 1;
  document.addEventListener("pointerdown", e => { const w = e.target.closest && e.target.closest(".flwin"); if (w) w.style.zIndex = ++zTop; }, true);
  // apply after every render of the main area
  new MutationObserver(() => { const ed = $("#main .ed"); if (ed && !ed.dataset.lay) applyEditor(false); else if (!ed && $(".flwin.edp")) applyEditor(false); })
    .observe(document.getElementById("main"), {childList:true});

  // other modules look for counters in the sidebar - keep them working
  EXT.after.push(() => { if (edit) return; const tb = $("#laybar"); if (tb && !edit) tb.remove(); });

  const css = document.createElement("style");
  css.textContent = `
  #app>#sider,#app>#sidet,#app>#sideb{background:var(--side);color:var(--sideink)}
  .lzone.v{display:flex;flex-direction:column;padding:14px 12px;gap:2px;overflow:auto;position:relative}
  #side.lzone.v{overflow:auto}
  .lzone.hz{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;padding:6px 12px;position:relative}
  .lsec{display:flex;flex-direction:column;gap:2px}
  .lsec.sep{border-top:1px solid #2a2636;margin-top:8px;padding-top:8px}
  .lzone.v>.lsec:last-of-type{flex:1}.lzone.v>.lsec:last-of-type>.lit{flex:1}.lit>.sidefoot{margin-top:auto}
  .lsec .lsh{display:flex;align-items:center;gap:6px;font-size:10.5px;letter-spacing:.9px;text-transform:uppercase;color:var(--sc,var(--sidemute));padding:8px 10px 1px}
  .lsec .lsh .lst{flex:1}
  .lsec .lcol,.lsec .lfl{cursor:pointer;opacity:.7}.lsec .lcol:hover,.lsec .lfl:hover{opacity:1}
  .lsec.col .lit{display:none}
  .lsec .lit{display:flex;flex-direction:column;gap:2px}
  .lsec.h{flex-direction:row;align-items:center;gap:6px}
  .lsec.h .lsh{padding:0 4px 0 0}
  .lsec.h .lit{flex-direction:row;flex-wrap:wrap;gap:2px}
  .lsec.h .nav{width:auto;padding:5px 9px}
  .lsec.h .brand{padding:0 8px 0 0}.lsec.h .sidefoot{margin:0;padding:0 4px}
  .lsec[style*="--sc"] .nav.on{background:var(--sc)}
  .lsec[style*="--sc"] .nav:not(.on) svg{color:var(--sc)}
  .lzone .sidefoot{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
  .lspl{position:absolute;top:0;bottom:0;right:0;width:5px;cursor:col-resize;z-index:3}.lspl.r{left:0;right:auto}
  .lspl:hover{background:rgba(255,255,255,.14)}
  .lspl:hover{background:rgba(255,255,255,.12)}
  #flw{position:fixed;inset:0;pointer-events:none;z-index:55}
  .flwin{position:fixed;pointer-events:auto;display:flex;flex-direction:column;border-radius:12px;box-shadow:0 14px 40px rgba(15,10,35,.35);overflow:hidden;min-width:170px}
  .flwin.menu{background:var(--side);color:var(--sideink);max-height:calc(100vh - 8px)}
  .flwin.edp{background:var(--panel);border:1px solid var(--line2)}
  .flwin.moving{opacity:.88;box-shadow:0 20px 60px rgba(15,10,35,.45)}
  .flt{display:flex;align-items:center;gap:8px;padding:7px 10px;cursor:move;user-select:none;font-size:12.5px;background:rgba(255,255,255,.06);border-bottom:1px solid rgba(255,255,255,.08)}
  .flwin.menu .flt{border-top:3px solid var(--sc,transparent)}
  .flwin.edp .flt{background:var(--panel2);border-bottom:1px solid var(--line)}
  .flt .sp,.edph .sp{flex:1}
  .flt>span[data-col],.flt>span[data-se],.flt>span[data-dk],.edb{cursor:pointer;opacity:.75;padding:0 2px}.flt>span:hover,.edb:hover{opacity:1}
  .flb{flex:1;overflow:auto;padding:8px;display:flex;flex-direction:column;gap:2px}.flb.col{display:none}
  .flr{position:absolute;right:0;bottom:0;width:16px;height:16px;cursor:nwse-resize;background:linear-gradient(135deg,transparent 50%,rgba(128,128,128,.5) 50%)}
  .lgrip{cursor:grab;opacity:.75}
  #laydock{position:fixed;display:none;z-index:90;background:rgba(10,132,255,.18);border:2px dashed #0A84FF;border-radius:10px;pointer-events:none;transition:all .08s}
  body.lay-edit .lzone{outline:1px dashed rgba(10,132,255,.5);outline-offset:-3px}
  body.lay-edit [data-it]{cursor:grab}
  body.lay-edit .lsec .lsh{color:#fff}
  body.lay-edit .lsec{border-radius:8px;padding-bottom:6px}
  body.lay-edit .lsec:hover{background:rgba(255,255,255,.04)}
  .lzhint{color:var(--sidemute);font-size:11.5px;border:1px dashed rgba(255,255,255,.25);border-radius:8px;padding:8px 10px;text-align:center}
  .ed .lzhint{color:var(--mute);border-color:var(--line2)}
  .lempty{font-size:11px;opacity:.6;border:1px dashed rgba(255,255,255,.25);border-radius:7px;padding:8px;text-align:center}
  .ldropmark{height:3px;min-width:30px;background:#0A84FF;border-radius:2px;margin:1px 0}
  .ldrag{opacity:.35}
  .nav.lghost{opacity:.6;border:1px dashed rgba(255,255,255,.25)}
  #laybar{position:fixed;top:0;left:0;right:0;height:52px;z-index:95;display:flex;align-items:center;gap:10px;overflow:hidden;
    background:#1c1a26;color:#fff;padding:0 14px;box-shadow:0 4px 16px rgba(0,0,0,.3);font-size:13px}
  body.lay-edit #app{height:calc(100vh - 52px);margin-top:52px}
  #laybar>.small{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #laybar .btn{color:var(--ink)}#laybar .btn.pri{color:#fff}
  #laytray{display:flex;flex-direction:row;flex-wrap:wrap;gap:4px;min-width:150px;min-height:28px;align-items:center;border:1px dashed rgba(255,255,255,.35);border-radius:8px;padding:3px 6px}
  .ltray{background:rgba(255,255,255,.12);border-radius:6px;padding:2px 8px;font-size:12px;cursor:grab}
  .lcb{width:26px;height:26px;border-radius:50%;border:2px solid var(--line2);cursor:pointer;color:var(--mute)}.lcb.on{outline:3px solid var(--acc);outline-offset:2px}
  /* editor areas */
  .ed.lay{display:block!important;height:100%}
  .ed.lay>.edl{display:flex;flex-direction:column;height:100%;min-height:0}
  .edl>.edrow{flex:1;display:flex;min-height:0}
  .edl .edc{flex:1;min-width:0;min-height:0;display:flex;flex-direction:column}
  .edl .edc>.mid{flex:1;min-height:0}
  .edz.l,.edz.r{display:flex;min-height:0}
  .edz.t,.edz.b{display:flex;flex-direction:column}
  .edp-d{position:relative;display:flex;flex-direction:column;min-height:0;min-width:0;flex:none}
  .edp-d>.pal,.edp-d>.pv,.edp-d>.mid{flex:1;min-height:0;border:0}
  .edp-d.left{border-right:1px solid var(--line)}.edp-d.right{border-left:1px solid var(--line)}.edp-d.top{border-bottom:1px solid var(--line)}.edp-d.bottom{border-top:1px solid var(--line)}
  .edspl{position:absolute;z-index:5}.edspl.left{right:-3px;top:0;width:6px;height:100%;cursor:col-resize}.edspl.right{left:-3px;top:0;width:6px;height:100%;cursor:col-resize}
  .edspl.top{bottom:-3px;left:0;height:6px;width:100%;cursor:row-resize}.edspl.bottom{top:-3px;left:0;height:6px;width:100%;cursor:row-resize}
  .edspl:hover{background:rgba(10,132,255,.35)}
  .edph{display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--accsoft);border-bottom:1px solid var(--accline,#c9bff5);font-size:12.5px;cursor:move;user-select:none}
  .ed.edfloat{display:flex!important;flex-direction:column;height:auto;flex:1;min-height:0}
  .ed.edfloat>.pal,.ed.edfloat>.pv,.ed.edfloat>.mid{flex:1;min-height:0;border:0}
  `;
  document.head.appendChild(css);
})();
