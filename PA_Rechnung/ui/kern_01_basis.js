// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Grundlagen: Hilfsfunktionen, Start, Mehrfachauswahl, Export, Programm-Update
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
"use strict";
// =============================================================
//  Pfeiffer-Audio Rechnung - UI v1.5.0
// =============================================================
const UI_VERSION = "3.8.1";
// v2.0.0: Andockpunkte fuer UI-Module (/ui/_all.js)
const EXT = {nav:[], views:{}, dash:[], settings:[], editor:[], project:[], beleg:[], tax:[], after:[]};
function extNav(section){ return EXT.nav.filter(n => n.section === section).map(n => { const c = n.cnt ? n.cnt() : ""; return `<button class="nav ${view===n.key?"on":""}" data-go="${n.key}">${ic(n.icon||"dash")}<span>${n.label}</span>${c?`<span class="cnt">${c}</span>`:""}</button>`; }).join(""); }
function extRun(list, ...a){ list.forEach(f => { try { f(...a); } catch (e) { console.error(e); } }); }
let S = null;          // bootstrap data
let view = "dash";
let viewArg = null;
let cur = null;        // invoice in editor
let pvTimer = null, pvSeq = 0;
let palCat = "Alle", palQ = "";
const MON = ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
const MONL = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"];
const BEREICH_COL = {"AV":"#6a48e0","Metallbau":"#3d6f8f","Schweißen":"#d06a2c","Audio":"#b9a33a","Unterricht":"#1f9d6b","Sonstiges":"#8a8599"};
const KIND_COL = {"CAD-Zeichnung":"#3d6f8f","Blockschaltbild":"#6a48e0","Schweißdokument":"#d06a2c","Q-SYS / AV-Programm":"#2b7bd6","Foto":"#1f9d6b","Stückliste":"#8a6d1f","Zeichnung":"#4f6b8a","Dokument":"#6b6478","Audio":"#b9a33a","Sonstiges":"#8a8599"};
const TYPES = {ausgabe:"Eingangsrechnung / Ausgabe", gehalt:"Gehalt / Lohn", eigene_rechnung:"Ausgangsrechnung (eigene)", anlage:"Anlage zu Rechnung", einnahme:"Sonstige Einnahme / Gutschrift"};
const TYPE_BADGE = {ausgabe:"bad", gehalt:"acc", eigene_rechnung:"ok", anlage:"", einnahme:"ok"};

// ---------- utils ----------
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const eur = v => (Number(v)||0).toLocaleString("de-DE",{minimumFractionDigits:2,maximumFractionDigits:2}) + " €";
const eur0 = v => (Number(v)||0).toLocaleString("de-DE",{maximumFractionDigits:0}) + " €";
const nde = (v,d=2) => (Number(v)||0).toLocaleString("de-DE",{minimumFractionDigits:d,maximumFractionDigits:d});
// unicode minus / en dash -> "-"; dots are thousands separators only if the first group is 1-999 without leading 0 ("1.500" = 1500, "0.500" = 0.5)
const pnum = s => { if (typeof s === "number") return s; s = String(s||"").trim().replace(/\s|€/g,"").replace(/^[−–]/,"-"); if (/,/.test(s) || /^[-+]?[1-9]\d{0,2}(\.\d{3})+$/.test(s)) s = s.replace(/\./g,"").replace(",","."); const v = parseFloat(s); return isNaN(v) ? 0 : v; };
// payment term like the server (_frist): 0 stays 0, default 7 only when empty/None
const fristOf = v => { const t = String(v ?? "").trim(); if (t === "" || t === "None" || t === "null") return 7; const n = parseInt(t, 10); return isNaN(n) ? 7 : n; };
const addDaysIso = (iso, n) => { const [y, m, d] = String(iso).slice(0,10).split("-").map(Number); return isoLocal(new Date(y, m - 1, d + n)); };
// overdue like the server: due date (datum + frist) < today, pure ISO string comparison
const isOverdue = i => !!(i && i.datum) && addDaysIso(i.datum, fristOf(i.frist)) < todayIso();
// URL part for CSS url('...') inside a style attribute: also encode ' ( ) (encodeURIComponent leaves them)
const encCss = v => encodeURIComponent(String(v ?? "")).replace(/['()]/g, c => "%" + c.charCodeAt(0).toString(16).toUpperCase());
const dde = iso => iso ? iso.slice(8,10)+"."+iso.slice(5,7)+"."+iso.slice(0,4) : "";
const todayIso = () => { const d = new Date(); return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0"); };
// v2.0.6: local date helpers (toISOString() is UTC -> one day off between 0 and 2 o'clock)
const isoLocal = d => d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
const addMonthsIso = (iso, n) => { const [y, m, dd] = String(iso).slice(0,10).split("-").map(Number); const t = (m - 1) + n, yy = y + Math.floor(t / 12), mm = ((t % 12) + 12) % 12;
  const last = new Date(yy, mm + 1, 0).getDate(); return yy + "-" + String(mm + 1).padStart(2,"0") + "-" + String(Math.min(dd || 1, last)).padStart(2,"0"); };
const thisYear = new Date().getFullYear();
const lineTotal = it => { const v = pnum(it.qty)*pnum(it.price)*(1-pnum(it.rabatt)/100); return v ? Math.sign(v)*Math.round((Math.abs(v)+1e-9)*100)/100 : 0; };   // v2.0.6: same rounding as the server
const cname = c => c ? (c.firma || c.name || c.kdnr) : "";
function invName(i){ const c = S.customers.find(c=>c.id==i.customer_id); if (c) return cname(c);
  const a = (Array.isArray(i.addr) ? i.addr : JSON.parse(i.addr||"[]")).filter(l=>!/^(herrn?|frau|familie|firma)$/i.test(l.trim())); return a[0] || i.kdnr || ""; }
function initials(s){ return (s||"?").split(/\s+/).filter(Boolean).slice(0,2).map(w=>w[0]).join("").toUpperCase(); }

async function api(path, body, opts={}){
  const o = body !== undefined ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {};
  const r = await fetch(path, o);
  const j = await r.json().catch(()=>({}));
  if (j && j.ok === false && j.error && !opts.quiet) toast(j.error, true);
  if (!r.ok && !opts.quiet) toast(j.error || ("Fehler " + r.status), true);
  return j;
}
async function upload(url, file, headers={}){
  const h = {"X-Filename": encodeURIComponent(file.name)};
  Object.assign(h, headers);
  const r = await fetch(url, {method:"POST", headers:h, body:file});
  return r.json();
}
function toast(msg, bad){
  const t = document.createElement("div"); t.className = "tst" + (bad ? " bad" : ""); t.textContent = msg;
  // v2.4.5: long messages stay longer (approx. reading time), click closes
  t.title = "Klicken zum Schließen"; t.onclick = () => t.remove();
  $("#toast").appendChild(t); setTimeout(()=>t.remove(), Math.min(15000, Math.max(bad ? 5200 : 3200, String(msg||"").length * 60)));
}
// ---------- v1.6.2: Eingaben behalten (Dialoge, Editor, Seiten) ----------
const KEEP_LS = "pa_keep_v1";
const KEEP = (() => { try { const j = JSON.parse(localStorage.getItem(KEEP_LS) || "{}"); return {modal:j.modal||{}, page:j.page||{}, inv:j.inv||{}}; } catch (e) { return {modal:{}, page:{}, inv:{}}; } })();
// old modal keys "m|<title>" (without record hash) could restore input into another record - drop them
Object.keys(KEEP.modal).forEach(k => { if (k.split("|").length < 3) delete KEEP.modal[k]; });
const PARKED = [];   // geparkte Dialoge (nur im laufenden Programm)
const TOUCHED = new WeakSet();
function keepSave(){ try { localStorage.setItem(KEEP_LS, JSON.stringify(KEEP)); } catch (e) {} }
document.addEventListener("input", e => { if (e.target && e.target.matches && e.target.matches("input,textarea,select")) TOUCHED.add(e.target); }, true);
document.addEventListener("change", e => { if (e.target && e.target.matches && e.target.matches("input,textarea,select")) TOUCHED.add(e.target); }, true);
const KF_SKIP = ["file","hidden","button","submit","reset","password","image"];
// never keep one-time codes, TANs, PINs or passwords (a stale TAN would cost a bank login attempt)
const KF_SECRET = /(^|[_-])(tan|pin|pw|pwd|pass|passwort|password|secret|token|otp)([_-]|\d|$)|(tan|pin)$/i;
function kFields(root){ return [...root.querySelectorAll("input,textarea,select")].filter(el => !KF_SKIP.includes((el.type||"").toLowerCase()) && !el.closest(".nokeep")
  && el.autocomplete !== "one-time-code" && !KF_SECRET.test(el.id || "") && !KF_SECRET.test(el.name || "") && !KF_SECRET.test(el.dataset.s || "")); }
function kDefault(el){
  if (el.type === "checkbox" || el.type === "radio") return el.defaultChecked ? "1" : "0";
  if (el.tagName === "SELECT") { const o = [...el.options]; const d = o.filter(x=>x.defaultSelected); return el.multiple ? d.map(x=>x.value).join("\u0001") : (d.length ? d[d.length-1].value : (o[0] ? o[0].value : "")); }
  return el.defaultValue;
}
function kVal(el){
  if (el.type === "checkbox" || el.type === "radio") return el.checked ? "1" : "0";
  if (el.tagName === "SELECT" && el.multiple) return [...el.options].filter(x=>x.selected).map(x=>x.value).join("\u0001");
  return el.value;
}
function kSet(el, v){
  if (el.type === "checkbox" || el.type === "radio") el.checked = v === "1";
  else if (el.tagName === "SELECT" && el.multiple) { const s = new Set(v.split("\u0001")); [...el.options].forEach(o => o.selected = s.has(o.value)); }
  else el.value = v;
  TOUCHED.add(el);
}
function kKey(el, i){ return (el.id ? "#" + el.id : el.dataset.i ? "i:" + el.dataset.i : el.dataset.k ? "k:" + el.dataset.k : el.dataset.s ? "s:" + el.dataset.s : el.name ? "n:" + el.name + (el.type==="radio" ? "=" + el.value : "") : "@" + i) + "|" + el.tagName + (el.type ? ":" + el.type : ""); }
// snapshot only fields the user changed; orig = rendered default (so it is only restored into the same record)
function kSnap(root, onlyPlain){
  const out = {};
  kFields(root).forEach((el, i) => {
    if (!TOUCHED.has(el)) return;
    if ((el.type === "checkbox" || el.type === "radio") && kKey(el, i).startsWith("@")) return;
    if (onlyPlain && (el.oninput || el.onchange || el.onkeyup)) return;
    const v = kVal(el), d = kDefault(el);
    if (v !== d) out[kKey(el, i)] = {o:d, v};
  });
  return Object.keys(out).length ? out : null;
}
function kApply(root, snap){
  let n = 0; const fl = kFields(root);
  fl.forEach((el, i) => { const s = snap[kKey(el, i)]; if (s && kDefault(el) === s.o && kVal(el) !== s.v) { kSet(el, s.v); n++; } });
  return n;
}
// page drafts (plain inputs that are read on save, e.g. settings, tax inputs, customer forms)
// settings tab and tax year are part of the key (else a draft of one tab/year is dropped or lands in another)
const pageKey = () => view + "|" + JSON.stringify(viewArg ?? null) + (view === "set" ? "|" + setTab : view === "tax" ? "|" + txYear : "");
function pageLeave(){
  if (view === "editor") { editorLeave(); return; }
  if (view === "stat") stData = null;   // Statistik detail tabs: reload after visiting other views (data may have changed)
  const m = $("#main"); if (!m) return;
  const s = kSnap(m, true), k = pageKey();
  if (s) KEEP.page[k] = s; else delete KEEP.page[k];
  keepSave();
}
function pageRestore(){
  const k = pageKey(), s = KEEP.page[k]; if (!s) return;
  const n = kApply($("#main"), s);
  if (n) toast(`${n} nicht gespeicherte Eingabe(n) wiederhergestellt`);
}
// invoice editor: keep unsaved document when leaving
let curBase = null;
let curPk = null;      // key of a parked NEW document (new, new~<time>) while it is open in the editor
// v2.0.6: search fields re-render after a short pause (was: whole table on every key, 4000 rows = ~3 s per key)
const _DEB = {};
function debRender(id, fn, ms = 180){
  clearTimeout(_DEB[id]);
  _DEB[id] = setTimeout(() => {
    const o = document.getElementById(id); if (!o) return;   // view changed meanwhile (e.g. editor opened)
    const p = o.selectionStart;
    fn();
    const n = document.getElementById(id); if (n) { n.focus(); if (p !== null) { try { n.setSelectionRange(p, p); } catch (e) {} } }
  }, ms);
}
const curSnap = () => { try { return JSON.stringify(cur); } catch (e) { return ""; } };
function editorLeave(){
  if (!cur || cur.locked || curBase === null) return;
  const s = curSnap();
  if (s && s !== curBase) {
    // v2.1.0: a second new document (or a new letter) no longer overwrites an already parked new one
    let k = cur.id || curPk;
    if (!k) { k = "new"; if (KEEP.inv[k]) k = "new~" + Date.now(); }
    curPk = null;      // parked now - the key comes back only with editorTake()
    KEEP.inv[k] = {cur:JSON.parse(s), base:curBase, t:Date.now()}; keepSave(); renderParkbar(); }
}
function editorTake(key){
  const p = KEEP.inv[key]; if (!p) return false;
  cur = p.cur; curBase = p.base; curPk = String(key).startsWith("new") ? key : null; delete KEEP.inv[key]; keepSave(); renderParkbar();
  cur.attachments = cur.attachments || [];
  toast("Nicht gespeicherte Eingaben wiederhergestellt");
  return true;
}
window.addEventListener("beforeunload", () => {
  PARKED.forEach(p => { const sn = kSnap(p.mb); if (sn) KEEP.modal[p.dk] = sn; });
  try { if (view === "editor") editorLeave(); else pageLeave(); } catch (e) {}
  keepSave();
});
const isNewK = k => k === "new" || String(k).startsWith("new~");
function renderParkbar(){
  let pb = $("#parkbar");
  if (!pb) { pb = document.createElement("div"); pb.id = "parkbar"; document.body.appendChild(pb); }
  const inv = Object.entries(KEEP.inv).map(([k, p]) => { const c = p.cur || {}; const t = DOCT[c.typ||"rechnung"] || "Dokument";
    return `<div class="pk"><button class="btn sm pri" data-pkinv="${esc(k)}" title="Weiter bearbeiten">↩ ${c.typ==="vorlage"?(isNewK(k)?"Neues Dokument aus Vorlage":esc("Dokument "+(c.betreff||""))):c.typ==="brief"?(isNewK(k)?"Neuer Brief":esc("Brief "+(c.betreff||""))):isNewK(k)?"Neue"+(c.typ==="angebot"?"s ":" ")+t:esc(t+" "+(c.nr||"Entwurf"))}${c.addr&&c.addr[0]?" · "+esc(c.addr[0]):""}</button><button class="btn sm ghost" data-pkx="${esc(k)}" title="Verwerfen">×</button></div>`; });
  const md = PARKED.map((p, i) => `<div class="pk"><button class="btn sm pri" data-pkm="${i}" title="Dialog wieder öffnen">↩ ${esc(p.title)}</button></div>`);
  pb.innerHTML = (inv.length || md.length) ? `<div class="pkh">Nicht abgeschlossen</div>${md.join("")}${inv.join("")}` : "";
  $$("[data-pkm]", pb).forEach(b => b.onclick = () => { const p = PARKED[+b.dataset.pkm]; if (p) p.show(); });
  $$("[data-pkinv]", pb).forEach(b => b.onclick = () => { if (view === "editor" && cur && (cur.id ? String(cur.id) : curPk) === b.dataset.pkinv) return; pageLeave(); selClear(); editorTake(b.dataset.pkinv); view = "editor"; viewArg = null; renderSide(); vEditor(); });
  $$("[data-pkx]", pb).forEach(b => b.onclick = async () => { if (await confirmBox("Nicht gespeicherte Eingaben verwerfen?", "Verwerfen")) { delete KEEP.inv[b.dataset.pkx]; keepSave(); renderParkbar(); } });
}
function hashStr(s){ let h = 5381; s = String(s || ""); for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36); }
function modal(title, html, buttons=[{label:"Schließen"}], wide=false, onOpen=null){
  return new Promise(res => {
    const mb = document.createElement("div"); mb.className = "mb";
    mb.innerHTML = `<div class="md ${wide?"wide":""}"><div class="mh"><h3>${esc(title)}</h3></div><div class="mc">${html}</div><div class="mf"></div></div>`;
    const mf = $(".mf", mb);
    const origin = {view, arg:viewArg};
    // keep key per record: same title but different content (other customer, other mail) -> different key
    const dk = "m|" + title + "|" + hashStr(html);
    let parkEntry = null, keepIt = true, busy = false;
    const unpark = () => { if (parkEntry) { const i = PARKED.indexOf(parkEntry); if (i >= 0) PARKED.splice(i, 1); parkEntry = null; renderParkbar(); } };
    buttons.forEach(b => { const e = document.createElement("button"); e.className = "btn " + (b.cls||""); e.textContent = b.label;
      e.onclick = async () => { if (busy) return;
        if (b.onClick) {
          // busy lock: no second click while the request runs (was: double click = two customers/projects/bookings)
          busy = true; const bs = [...mf.querySelectorAll("button")], was = bs.map(x => x.disabled); bs.forEach(x => x.disabled = true);
          let ok;
          try { ok = await b.onClick(mb); } catch (err) { console.error(err); ok = false; }
          finally { busy = false; bs.forEach((x, k) => x.disabled = was[k]); }
          if (ok === false) return; }
        if (/\b(pri|danger)\b/.test(b.cls||"")) keepIt = false;
        close(b.value ?? null); }; mf.appendChild(e); });
    const top = () => [...document.querySelectorAll(".mb")].filter(m => !m.hidden).pop();
    const onKey = e => { if (e.key === "Escape" && !busy && !mb.hidden && top() === mb) { e.stopImmediatePropagation(); close(null); } };
    const close = v => {
      if (keepIt) { const s = kSnap(mb); if (s) KEEP.modal[dk] = s; } else delete KEEP.modal[dk];
      keepSave(); unpark();
      document.removeEventListener("keydown", onKey, true); mb.remove(); res(v); };
    document.addEventListener("keydown", onKey, true);
    mb.addEventListener("mousedown", e => { if (e.target === mb && !busy) close(null); });
    document.body.appendChild(mb);
    if (onOpen) onOpen(mb);
    if (kFields(mb).length) {
      const pk = document.createElement("button"); pk.className = "btn sm ghost"; pk.type = "button"; pk.style.marginLeft = "auto";
      pk.title = "Dialog kurz wegklicken, um woanders nachzusehen – Eingaben bleiben stehen. Unten links wieder öffnen.";
      pk.textContent = "Kurz wegklicken ↘"; $(".mh", mb).style.display = "flex"; $(".mh", mb).style.alignItems = "center"; $(".mh", mb).appendChild(pk);
      pk.onclick = () => { mb.hidden = true;
        parkEntry = {title, mb, dk, show: () => { if (origin.view !== view || JSON.stringify(origin.arg ?? null) !== JSON.stringify(viewArg ?? null)) go(origin.view, origin.arg);
          mb.hidden = false; unpark(); }};
        PARKED.push(parkEntry); renderParkbar(); };
      const sv = KEEP.modal[dk];
      if (sv && kApply(mb, sv)) {
        const h = document.createElement("div"); h.className = "hl small"; h.style.marginBottom = "10px";
        h.innerHTML = `Deine letzten Eingaben wurden wiederhergestellt. <a href="#" style="margin-left:6px">Verwerfen</a>`;
        $(".mc", mb).prepend(h);
        $("a", h).onclick = ev => { ev.preventDefault(); kFields(mb).forEach(el => kSet(el, kDefault(el))); delete KEEP.modal[dk]; keepSave(); h.remove(); };
      }
    }
    const f = $("input,textarea,select", mb); if (f) setTimeout(()=>f.focus(), 30);
  });
}
async function confirmBox(text, ok="Löschen"){
  return modal("Bitte bestätigen", `<p style="margin:0;white-space:pre-line">${esc(text)}</p>`, [{label:"Abbrechen", value:false},{label:ok, cls:"pri", value:true}]);
}
const IC = {
  dash:'<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  xls:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>',
  inv:'<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6M9 13h7M9 17h7"/>',
  users:'<circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-6 7-6s7 2 7 6"/><path d="M17 11a3 3 0 1 0 0-6M22 21c0-3-2-5-4-5.5"/>',
  blocks:'<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><path d="M17 13v8M13 17h8"/>',
  proj:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  beleg:'<path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  tax:'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M8 11h2M12 11h2M16 11v6M8 15h2M12 15h2M8 19h6"/>',
  stat:'<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 6-7"/>',
  set:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  search:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  pdf:'<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/><path d="M9 15h6M12 12v6"/>',
  copy:'<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  trash:'<path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15"/>',
  check:'<path d="M20 6L9 17l-5-5"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  open:'<path d="M14 3h7v7M21 3l-9 9M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
  up:'<path d="M12 19V5M5 12l7-7 7 7"/>',
  eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  save:'<path d="M5 3h11l5 5v13H5z"/><path d="M8 3v5h8M8 21v-7h8v7"/>',
  sync:'<path d="M21 12a9 9 0 0 1-15.5 6.3L3 16M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>',
  clip:'<path d="M21 11l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8"/>',
};
const ic = (k) => `<svg viewBox="0 0 24 24">${IC[k]||""}</svg>`;

// ---------- boot ----------
async function boot(){
  S = await api("/api/bootstrap");
  applyTheme(S.settings.theme === "dark" ? "dark" : "light");
  renderSide();
  go(view, viewArg);
  renderParkbar();
  const h = S.upd && S.upd.hinweis;
  if (h && h.text) { await modal("Programm-Update", `<div>${esc(h.text)}</div>${h.fehler?`<details style="margin-top:10px"><summary class="small muted">Technische Details</summary><pre class="small" style="white-space:pre-wrap;max-height:240px;overflow:auto">${esc(h.fehler)}</pre></details>`:""}`);
    api("/api/update/hinweis_ok", {}); }
  // v2.4.7: modules switched off because a library is missing in this EXE
  const mf = S.modul_fehler || [];
  if (mf.length) await modal("Einige Funktionen sind abgeschaltet", `<div class="fr"><div>In diesem Programm fehlt ein Baustein – diese Teile wurden deshalb nicht geladen, der Rest läuft normal:</div>
    <ul style="margin:0 0 0 18px">${mf.map(m => `<li><b>${esc(m.modul)}</b> – Grund: <code>${esc(m.fehlt)}</code></li>`).join("")}</ul>
    <div class="small muted">Abhilfe: Einstellungen → EXE → „EXE neu bauen“ (oder build_exe.bat ausführen). Dann ist der Baustein dabei.</div></div>`);
}
async function reload(){ S = await api("/api/bootstrap"); renderSide(); }
function renderSide(){
  const open = S.invoices.filter(i=>i.typ==="rechnung"&&i.status==="offen").length;
  const drafts = S.invoices.filter(i=>i.status==="entwurf").length;
  const act = S.projects.filter(p=>p.status==="aktiv").length;
  const warn = S.cert_warn.length;
  const isOn = k => view===k || (k==="proj"&&view==="project") || (k==="inv"&&view==="editor");
  const n = (k,lbl,cnt,icon) => `<button class="nav ${isOn(k)?"on":""}" data-go="${k}">${ic(icon||(k==="new"?"plus":k))}<span>${lbl}</span>${cnt?`<span class="cnt">${cnt}</span>`:""}</button>`;
  const t = S.settings.timer;
  const tp = t ? S.projects.find(p=>p.id==t.project_id) : null;
  $("#side").innerHTML = `
    <div class="brand"><img src="/logo" alt=""><div><b>${esc(S.settings.firma)}</b><span>Rechnung & Verwaltung</span></div></div>
    <button class="nav srch" id="gsearch">${ic("search")}<span>Suchen</span><span class="cnt">Strg+K</span></button>
    ${n("dash","Übersicht")}
    ${extNav("Top")}
    ${n("new","Neues Dokument")}
    ${n("inv","Rechnungen & Angebote", (open+drafts)||"")}
    <div class="sidelbl">Stammdaten</div>
    ${n("users","Kunden", S.customers.length)}
    ${n("blocks","Bausteine", S.articles.length)}
    ${n("school","Unterricht", S.students.filter(s=>s.aktiv).length||"", "school")}
    ${extNav("Stammdaten")}
    <div class="sidelbl">Projekte</div>
    ${n("proj","Projekte", act||"")}
    ${n("certs","Nachweise", warn?"⚠ "+warn:"", "award")}
    ${n("abo","Wartung & Abos", S.vertraege_due.length||"", "wrench")}
    ${extNav("Projekte")}
    <div class="sidelbl">Finanzen</div>
    ${n("beleg","Belege & Import")}
    ${n("bank","Bank-Abgleich","","bank")}
    ${n("assets","Anlagen & Inventar","","box")}
    ${n("trips","Fahrten","","car")}
    ${n("stat","Statistik")}
    ${n("tax","Jahresabrechnung & Steuer")}
    ${extNav("Finanzen")}
    <div class="sidesep"></div>
    ${n("set","Einstellungen")}
    ${extNav("System")}
    ${t?`<div class="timerbox"><div class="small">⏱ läuft · <b id="tmel">${timerElapsed(t)}</b></div><div class="small" style="opacity:.8">${esc(tp?tp.name:"Projekt")}</div><button class="btn sm" id="tmstop" style="margin-top:6px;width:100%;justify-content:center">Stoppen & buchen</button></div>`:""}
    <div class="sidefoot"><button class="btn sm ghost" id="theme" style="color:var(--sideink)">${ic("moon")} ${document.documentElement.dataset.theme==="dark"?"Hell":"Dunkel"}</button><span style="margin-left:auto">v${S.version}</span></div>`;
  $$("#side [data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
  $("#gsearch").onclick = openSearch;
  $("#theme").onclick = toggleTheme;
  if ($("#tmstop")) $("#tmstop").onclick = stopTimer;
}
function go(v, arg){
  if (v === "new") { newInvoice(arg); return; }
  if (!(v === "editor" && view === "editor")) pageLeave();
  if (v !== view) selClear();
  if (v !== view && typeof KONTO_SHOW !== "undefined") { KONTO_SHOW = false; KMASK.length = 0; }   // v3.6.1: balance covered again
  view = v; viewArg = arg ?? null;
  renderSide();
  const m = $("#main"); m.scrollTop = 0;
  const VIEWS = {dash:vDash, inv:vInvoices, users:vCustomers, blocks:vBlocks, proj:vProjects, project:vProject, beleg:vBelege, stat:vStats, tax:vTax, set:vSettings, editor:vEditor,
    school:vSchool, certs:vCerts, abo:vAbo, bank:vBank, assets:vAssets, trips:vTrips};
  const ret = (VIEWS[v] || EXT.views[v] || vDash)(arg);
  Promise.resolve(ret).then(() => setTimeout(pageRestore, 0)).catch(() => {});
}
function pageHead(title, sub, actions=""){
  return `<div class="ph"><div><h1>${title}</h1>${sub?`<div class="sub">${sub}</div>`:""}</div><div class="act">${actions}</div></div>`;
}
function yearSel(id, y){
  const ys = new Set([thisYear, thisYear-1]);
  S.invoices.forEach(i => i.datum && ys.add(+i.datum.slice(0,4)));
  S.belege.forEach(b => b.datum && ys.add(+b.datum.slice(0,4)));
  return `<select class="in" id="${id}" style="width:auto">${[...ys].sort((a,b)=>b-a).map(v=>`<option ${v==y?"selected":""}>${v}</option>`).join("")}</select>`;
}

// ---------- multi select (v1.6.0) ----------
const SEL = {};
let selCur = null;
function selClear(kind){ if (kind) { if (SEL[kind]) SEL[kind].set.clear(); } else Object.values(SEL).forEach(o => o.set.clear()); selBar(); }
function selectify(o){
  // o: {kind, rows (selector or elements), id (attr name or fn), actions:[{label, cls, run(ids)}], place(el) -> container, root}
  const prev = SEL[o.kind];
  const set = prev ? prev.set : new Set();
  if (EXP_KIND[o.kind] && !o.actions.some(a => a.exp)) {
    const ek = EXP_KIND[o.kind], extra = o.kind === "asset" ? () => ({year: asYear}) : () => ({});
    o.actions = [{label:"Excel", exp:1, run: async ids => { await doExport(ek, "xlsx", Object.assign(extra(), {ids})); return false; }},
                 {label:"PDF", exp:1, run: async ids => { await doExport(ek, "pdf", Object.assign(extra(), {ids})); return false; }}, ...o.actions];
  }
  const els = typeof o.rows === "string" ? $$(o.rows, o.root || document) : o.rows;
  SEL[o.kind] = Object.assign({}, o, {set, els});
  const idOf = el => String(typeof o.id === "function" ? o.id(el) : el.getAttribute(o.id));
  const vis = els.map(idOf);
  const visS = new Set(vis);   // v2.0.6: O(n) instead of O(n*m)
  [...set].forEach(v => { if (!visS.has(v)) set.delete(v); });
  SEL[o.kind].visible = vis;
  let last = null;
  const mark = () => { els.forEach(el => { const on = set.has(idOf(el)); el.classList.toggle("sel", on); const c = el.querySelector(":scope .selc[data-sk]"); if (c) c.checked = on; });
    if (hb) { hb.checked = vis.length && vis.every(v => set.has(v)); hb.indeterminate = !hb.checked && vis.some(v => set.has(v)); } selCur = o.kind; selBar(); };
  els.forEach((el, idx) => {
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.className = "selc"; cb.dataset.sk = o.kind; cb.title = "Markieren (Umschalt = Bereich)";
    cb.onclick = e => { e.stopPropagation(); const v = idOf(el);
      if (e.shiftKey && last !== null) { const [a, b] = [Math.min(last, idx), Math.max(last, idx)]; for (let k = a; k <= b; k++) cb.checked ? set.add(vis[k]) : set.delete(vis[k]); }
      else cb.checked ? set.add(v) : set.delete(v);
      last = idx; mark(); };
    if (el.tagName === "TR") { const td = document.createElement("td"); td.className = "selcell"; td.onclick = e => e.stopPropagation(); td.appendChild(cb); el.prepend(td); }
    else { const c = o.place ? o.place(el) : el; (c || el).prepend(cb); cb.addEventListener("mousedown", e => e.stopPropagation()); }
  });
  let hb = null;
  const tbl = els[0] && els[0].tagName === "TR" ? els[0].closest("table") : null;
  if (tbl) {
    $$("thead tr", tbl).forEach(tr => { const th = document.createElement("th"); th.className = "selcell";
      hb = document.createElement("input"); hb.type = "checkbox"; hb.className = "selc"; hb.title = "Alle markieren";
      hb.onclick = () => { hb.checked ? vis.forEach(v => set.add(v)) : vis.forEach(v => set.delete(v)); mark(); };
      th.appendChild(hb); tr.prepend(th); });
    $$("tfoot tr", tbl).forEach(tr => tr.prepend(document.createElement("td")));
    $$("tbody tr", tbl).forEach(tr => { if (!els.includes(tr)) { const c = tr.querySelector("td[colspan]"); if (c) c.colSpan = (+c.colSpan || 1) + 1; else tr.prepend(document.createElement("td")); } });
  } else if (o.allBox) {
    hb = document.createElement("input"); hb.type = "checkbox"; hb.className = "selc"; hb.title = "Alle markieren";
    hb.onclick = () => { hb.checked ? vis.forEach(v => set.add(v)) : vis.forEach(v => set.delete(v)); mark(); };
    o.allBox.prepend(hb);
  }
  mark();
}
function selBar(){
  // forget selections whose list is no longer on screen (other tab / view)
  Object.values(SEL).forEach(x => { if (x.set.size && !(x.els || []).some(e => e.isConnected)) x.set.clear(); });
  let bar = $("#selbar");
  if (!bar) { bar = document.createElement("div"); bar.id = "selbar"; document.body.appendChild(bar); }
  let o = selCur && SEL[selCur];
  if (!o || !o.set.size) o = Object.values(SEL).find(x => x.set.size);
  if (!o || !o.set.size) { bar.classList.remove("on"); return; }
  selCur = o.kind;
  const ids = [...o.set];
  bar.innerHTML = `<span class="n">${ids.length} markiert</span>${o.visible && ids.length < o.visible.length ? `<button class="btn sm" data-sa="all">Alle ${o.visible.length}</button>` : ""}` +
    o.actions.map((a, k) => `<button class="btn sm ${a.cls||""}" data-sa="${k}">${a.label}</button>`).join("") + `<button class="x" title="Auswahl aufheben (Esc)" data-sa="x">✕</button>`;
  bar.classList.add("on");
  $$("[data-sa]", bar).forEach(b => b.onclick = async () => {
    const k = b.dataset.sa;
    if (k === "x") { o.set.clear(); return o.rerender ? o.rerender() : selectRefresh(); }
    if (k === "all") { o.visible.forEach(v => o.set.add(v)); return o.rerender ? o.rerender() : selectRefresh(); }
    const a = o.actions[+k]; const r = await a.run([...o.set]);
    if (r !== false) { o.set.clear(); selBar(); }
  });
}
function selectRefresh(){ go(view, viewArg); }
let selObsT = 0;
new MutationObserver(muts => { if (muts.every(m => m.target.closest && m.target.closest("#selbar, .toast, #toast"))) return; clearTimeout(selObsT); selObsT = setTimeout(() => { if (Object.values(SEL).some(x => x.set.size)) selBar(); }, 30); })
  .observe(document.documentElement, {childList: true, subtree: true});
document.addEventListener("keydown", e => { if (e.key === "Escape" && Object.values(SEL).some(o => o.set.size) && !$(".mb:not([hidden])")) { const o = SEL[selCur]; selClear(); if (o && o.rerender) o.rerender(); else go(view, viewArg); } });
async function bulk(kind, action, ids, value, extra){
  const r = await api("/api/bulk", Object.assign({kind, action, ids, value}, extra||{}));
  if (r && r.ok) { const msg = `${r.done} erledigt` + (r.skipped ? ` · ${r.skipped} übersprungen` : ""); toast(r.errors && r.errors.length ? msg + " – " + r.errors.join(" ") : msg, !!r.skipped); }
  return r;
}
async function askValue(title, html, getter){
  let v = null;
  const ok = await modal(title, html, [{label:"Abbrechen"},{label:"Übernehmen", cls:"pri", value:1, onClick: mb => { v = getter(mb); }}]);
  return ok ? v : null;
}
const ask = (t, n) => confirmBox(t, n);

// ---------- export Excel / PDF (v1.6.1) ----------
const EXPR = {}; let expN = 0;
function expButtons(kind, params = {}, small = false, fmts = ["xlsx", "pdf"]){
  const k = "e" + (++expN); EXPR[k] = {kind, params};
  const c = small ? "btn sm" : "btn";
  const lbl = {xlsx:`${ic("xls")} Excel`, pdf:`${ic("pdf")} PDF`};
  return `<span class="expg">${fmts.map(f => `<button class="${c}" type="button" data-expk="${k}" data-fmt="${f}" title="${f==="pdf"?"Als PDF exportieren":"Als Excel-Datei exportieren"}">${lbl[f]}</button>`).join("")}</span>`;
}
async function doExport(kind, fmt, params){
  toast((fmt === "pdf" ? "PDF" : "Excel-Datei") + " wird erstellt …");
  const r = await api("/api/export", {kind, fmt, params: params || {}});
  if (r && r.ok) toast("Exportiert: " + r.path.split(/[\\/]/).pop() + " (Ordner Export)");
  return r;
}
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-expk]"); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const x = EXPR[b.dataset.expk]; if (!x) return;
  doExport(x.kind, b.dataset.fmt, typeof x.params === "function" ? x.params() : x.params);
}, true);
const EXP_KIND = {invoice:"invoices", beleg:"belege", customer:"customers", article:"articles", bank:"bank", asset:"assets", fahrt:"fahrten", zert:"zert", steuerakte:"steuerakte"};

// ---------- Jahresbericht (v1.6.1) ----------
async function jahresbericht(y){
  toast(`Jahresbericht ${y} wird erstellt …`);
  const r = await api("/api/report/jahresbericht", {year:y});
  if (r.ok) toast("Gespeichert: " + r.path.split(/[\\/]/).pop());
}

// ---------- program update (v1.6.0) ----------
function restartScreen(txt){
  document.body.innerHTML = `<div class="empty" style="padding-top:30vh;font-size:16px">${txt}<div class="small muted" style="margin-top:10px">Das Fenster schließt sich und öffnet sich gleich neu.</div></div>`;
}
async function installUpdateFile(f){
  const isExe = /\.exe$/i.test(f.name);
  if (!isExe && !/\.(paupdate|zip)$/i.test(f.name)) return toast("Bitte eine Update-Datei (.paupdate) auswählen.", true);
  if (!await confirmBox(`Update „${f.name}“ einspielen? Das Programm startet danach neu. Deine Daten bleiben unberührt.`, "Einspielen")) return;
  toast("Update wird eingespielt …");
  let r = await upload("/api/upload/update", f);
  if (r.ok === false && /nicht neuer als die laufende Version/.test(r.error || "") && new RegExp("^v" + S.version.replace(/\./g, "\\.") + " ").test(r.error)
      && await confirmBox(`Version v${S.version} läuft bereits. Dieselbe Version trotzdem neu einspielen (z. B. korrigierte Update-Datei)?`, "Neu einspielen"))
    r = await upload("/api/upload/update", f, {"X-Force": "1"});
  if (r.ok === false) { await modal("Update nicht eingespielt", `<div style="white-space:pre-line">${esc(r.error)}</div>`); return; }
  if (r.restart === false) { await modal("Update eingespielt", `Version <b>v${esc(r.version||"")}</b> ist installiert. Bitte das Programm jetzt schließen und neu starten.`); return; }
  restartScreen(isExe ? "Neue EXE wird installiert …" : `Update auf <b>v${esc(r.version)}</b> eingespielt – Neustart …`);
}
async function renderUpdBox(){
  const el = $("#updbox"); if (!el) return;
  const u = await api("/api/update/info");
  const src = {update:"aus Update-Datei", builtin:"in der EXE eingebaut", direkt:"direkt gestartet (ohne Starter)"}[u.source] || u.source;
  el.innerHTML = `<div class="small">Laufende Version: <b>v${esc(u.version)}</b> · ${esc(src)}${u.launcher?` · Starter v${esc(u.launcher)}`:""}${u.builtin&&u.source==="update"?`<br><span class="muted">In der EXE eingebaut: v${esc(u.builtin)}</span>`:""}</div>
    ${u.launcher?`<div class="small muted">Updates kommen als <b>.paupdate</b>-Datei: auswählen oder einfach ins Programmfenster ziehen. Keine neue EXE nötig – außer das Update meldet, dass eine neue Bibliothek fehlt.</div>`
      :`<div class="alert warn small">Diese Version läuft noch ohne Starter. Einmalig mit <b>build_exe.bat</b> (ab v1.6.0) die neue EXE bauen – danach gehen alle Updates per Datei.</div>`}
    <div class="row" style="flex-wrap:wrap"><button class="btn pri" style="flex:none" id="updf">${ic("up")} Update einspielen (.paupdate)</button>${S.frozen?`<button class="btn" style="flex:none" id="upde">Neue EXE installieren …</button>`:""}</div>
    ${u.installed.length?`<div class="small muted" style="margin-top:6px"><b>Installierte Versionen</b></div><div class="updlist">${u.installed.map(v=>`<div class="it2"><b style="flex:none">v${esc(v.version)}</b><span class="small muted" style="flex:1">${esc(v.datum||"")}${u.defekt.includes(v.version)?" · <span style='color:var(--bad)'>ließ sich nicht starten</span>":""}${v.changelog?"<br>"+esc(v.changelog).slice(0,160):""}</span>
      ${u.active===v.version?`<span class="badge ok" style="flex:none">aktiv</span>`:`<button class="btn sm" style="flex:none" data-act="${esc(v.version)}">Aktivieren</button>`}</div>`).join("")}
      <div class="it2"><b style="flex:none">EXE</b><span class="small muted" style="flex:1">eingebaute Version${u.builtin?" v"+esc(u.builtin):""}</span>${u.active==="builtin"?`<span class="badge ok" style="flex:none">aktiv</span>`:`<button class="btn sm" style="flex:none" data-act="builtin">Aktivieren</button>`}</div></div>`:""}`;
  $("#updf").onclick = () => pickFiles(".paupdate,.zip", fs => installUpdateFile(fs[0]));
  if ($("#upde")) $("#upde").onclick = () => pickFiles(".exe", fs => installUpdateFile(fs[0]));
  $$("[data-act]", el).forEach(b => b.onclick = async () => { const v = b.dataset.act;
    if (!await confirmBox(`${v==="builtin"?"Die in der EXE eingebaute Version":"Version v"+v} aktivieren? Das Programm startet neu.`, "Aktivieren")) return;
    const r = await api("/api/update/activate", {version:v}); if (r.ok) restartScreen("Version wird gewechselt …"); });
}
window.addEventListener("drop", e => {
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (f && /\.paupdate$/i.test(f.name)) { e.preventDefault(); e.stopPropagation(); installUpdateFile(f); }
}, true);

