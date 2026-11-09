// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Sortieren per Spaltenkopf, Andockpunkte fuer UI-Module
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- v1.6.4: alle Tabellen per Klick auf die Spaltenkoepfe sortieren ----------
const TSORT = (() => { try { return JSON.parse(localStorage.getItem("pa_tsort_v1") || "{}"); } catch (e) { return {}; } })();
function tsSave(){ try { localStorage.setItem("pa_tsort_v1", JSON.stringify(TSORT)); } catch (e) {} }
function thLabel(th){ if (th.dataset.lbl == null) th.dataset.lbl = (th.textContent || "").trim(); return th.dataset.lbl; }
function tsKey(table){ const ths = [...table.tHead.rows[0].cells]; return view + "|" + ths.map(thLabel).join("¦"); }
function tsSortable(table){ return table.classList.contains("t") && !table.classList.contains("cal") && !table.classList.contains("nosort") && table.tHead && table.tHead.rows.length && table.tBodies.length; }
function tsCellVal(cell){
  if (!cell) return null;
  const f = cell.querySelector("input:not([type=checkbox]):not([type=radio]),select,textarea");
  let t = f ? (f.tagName === "SELECT" ? (f.options[f.selectedIndex] || {}).text || "" : f.value) : (cell.dataset.sort != null ? cell.dataset.sort : cell.innerText || cell.textContent || "");
  t = String(t).replace(/\s+/g, " ").trim();
  if (!t || t === "–" || t === "-") return null;
  let m = t.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})/);
  if (m) return {n: +(m[3] + m[2].padStart(2, "0") + m[1].padStart(2, "0"))};
  m = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return {n: +(m[1] + m[2] + m[3])};
  const nm = t.replace(/[€%×\s]/g, "").replace(/^−/, "-").replace(/^[-+]?$/, "");
  if (/^[-+]?\d{1,3}(\.\d{3})*(,\d+)?$/.test(nm) || /^[-+]?\d+(,\d+)?$/.test(nm)) return {n: parseFloat(nm.replace(/\./g, "").replace(",", ".")), s: t.toLowerCase()};
  return {s: t.toLowerCase()};
}
const tsColl = new Intl.Collator("de", {numeric:true, sensitivity:"base"});
function tsCmp(a, b){
  if (a == null && b == null) return 0; if (a == null) return 1; if (b == null) return -1;
  if (a.n != null && b.n != null) return a.n - b.n;
  return tsColl.compare(a.s != null ? a.s : String(a.n), b.s != null ? b.s : String(b.n));
}
function tsIsSep(tr){ return tr.classList.contains("sdgrp") || tr.classList.contains("grp") || [...tr.cells].some(c => c.colSpan > 1) || !!tr.querySelector(".empty"); }
function tsApply(table){
  if (!tsSortable(table)) return;
  const ths = [...table.tHead.rows[0].cells];
  const st = TSORT[tsKey(table)];
  ths.forEach((th, i) => {
    thLabel(th);
    const ok = th.textContent.trim() !== "" && !th.querySelector("input,select,button");
    th.classList.toggle("srt", ok);
    let ar = th.querySelector(".sarr");
    const want = st && st.c === i ? (st.d > 0 ? "▲" : "▼") : "";
    if (ok && !ar) { ar = document.createElement("span"); ar.className = "sarr"; th.appendChild(ar); }
    if (ar && ar.textContent !== want) ar.textContent = want;
  });
  const tb = table.tBodies[0];
  const rows = [...tb.rows];
  if (!tb._origIdx || rows.length !== tb._origIdx.size || rows.some(r => !tb._origIdx.has(r))) tb._origIdx = new Map(rows.map((r, i) => [r, i]));   // v2.0.6: Map instead of O(n^2)
  // segments between separator rows (group headers) are sorted on their own
  const segs = []; let cur_ = [];
  rows.forEach(r => { if (tsIsSep(r)) { segs.push(cur_); segs.push(r); cur_ = []; } else cur_.push(r); });
  segs.push(cur_);
  const order = [];
  segs.forEach(sg => {
    if (!Array.isArray(sg)) { order.push(sg); return; }
    let arr = sg.slice();
    if (st && st.c < ths.length) { const v = new Map(arr.map(r => [r, tsCellVal(r.cells[st.c])]));
      arr.sort((a, b) => { const x = v.get(a), y = v.get(b); if (x == null || y == null) return tsCmp(x, y); return st.d * tsCmp(x, y); }); }
    else arr.sort((a, b) => tb._origIdx.get(a) - tb._origIdx.get(b));
    order.push(...arr);
  });
  if (order.some((r, i) => rows[i] !== r)) order.forEach(r => tb.appendChild(r));
}
document.addEventListener("click", e => {
  const th = e.target.closest && e.target.closest("table.t > thead > tr > th.srt");
  if (!th || e.target.closest("input,select,button,a")) return;
  const table = th.closest("table"); if (!tsSortable(table)) return;
  const i = [...th.parentNode.cells].indexOf(th), k = tsKey(table), st = TSORT[k];
  if (!st || st.c !== i) TSORT[k] = {c:i, d:1};
  else if (st.d > 0) TSORT[k] = {c:i, d:-1};
  else delete TSORT[k];
  tsSave();
  document.querySelectorAll("table.t").forEach(t => { if (tsSortable(t) && tsKey(t) === k) tsApply(t); });
});
let tsQueued = false;
const TSQ = new Set();
// v2.0.6: only tables that were really changed (before: every table on every toast / timer tick)
const tsObs = new MutationObserver(muts => {
  let any = false;
  for (const m of muts) {
    const t = m.target; if (!t || !t.closest) continue;
    if (t.closest("#toast, .toast, #selbar, #parkbar")) continue;
    any = true;
    const tab = t.closest("table.t");
    if (tab) TSQ.add(tab); else if (t.querySelectorAll) t.querySelectorAll("table.t").forEach(x => TSQ.add(x));
  }
  if (!any || tsQueued) return; tsQueued = true;
  requestAnimationFrame(() => { tsQueued = false; const ts = [...TSQ]; TSQ.clear(); ts.forEach(t => { if (t.isConnected) tsApply(t); }); try { bindFolderFields(); } catch (e) {} });
});
tsObs.observe(document.body, {childList:true, subtree:true});
console.log("INIT UI v" + UI_VERSION);
// v2.0.0: after every (re-)render of these views EXT.after hooks run: fn(viewName, ...args)
["vDash","vInvoices","vCustomers","vBlocks","vProjects","vProject","vBelege","vStats","vTax","vSettings","vEditor","vSchool","vCerts","vAbo","vBank","vAssets","vTrips"].forEach(n => {
  const f = window[n]; if (typeof f !== "function") return;
  window[n] = function(...a){ const r = f.apply(this, a); Promise.resolve(r).then(() => extRun(EXT.after, n, ...a)).catch(() => {}); return r; };
});
