// PA Rechnung v2.0.19 - UI-Modul m87_ansichten: gespeicherte Ansichten (Filter/Suche/Sortierung) in den Listen
// Knopf "Ansicht speichern" im Seitenkopf, Ansicht-Chips zum Wiederherstellen, Kachel "Gespeicherte Ansichten" auf der Uebersicht.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m87 = '<path d="M6 3h12v18l-6-4-6 4z"/>';
  // icons inside small labels (Ansichten:, Feld-Filter, Eigene Felder) were drawn at full size
  if (!document.getElementById("m87css")) { const st = document.createElement("style"); st.id = "m87css";
    st.textContent = ".small > svg{width:14px;height:14px;vertical-align:-2px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;flex:none}";
    document.head.appendChild(st); }
  const VIEWN = {vInvoices: "inv", vCustomers: "users", vProjects: "proj", vBelege: "beleg", vBlocks: "blocks"};
  const LABEL = {inv: "Rechnungen & Angebote", users: "Kunden", proj: "Projekte", beleg: "Belege", blocks: "Bausteine", m42lager: "Lager"};
  const OBJ = {inv: "rechnung", users: "kunde", proj: "projekt", beleg: "beleg", blocks: "baustein", m42lager: "lager"};
  const clone = o => JSON.parse(JSON.stringify(o));
  let active = {};          // view -> id of the view applied last (highlight)

  // ---------------------------------------------------------------- state of each list
  function tsortOf(v){ const o = {}; try { Object.entries(TSORT).forEach(([k, s]) => { if (k.startsWith(v + "|")) o[k] = s; }); } catch (e) {} return o; }
  function capture(v){
    const st = {tsort: tsortOf(v), m85: clone((window.m85Flt || {})[v] || {})};
    if (v === "inv") Object.assign(st, {invTab, invF: clone(invF)});
    else if (v === "users") Object.assign(st, {custQ, custSort: clone(custSort)});
    else if (v === "proj") st.projF = clone(projF);
    else if (v === "beleg") st.belF = clone(belF);
    else if (v === "blocks") Object.assign(st, {blkTab, blkCat});
    else if (v === "m42lager" && typeof m42F !== "undefined") st.m42F = clone(m42F);
    return st;
  }
  function restore(v, st){
    st = st || {};
    if (v === "inv") { if (st.invTab) invTab = st.invTab; if (st.invF) invF = Object.assign({year: "", status: "", q: ""}, st.invF); }
    else if (v === "users") { custQ = st.custQ || ""; if (st.custSort) custSort = st.custSort; }
    else if (v === "proj") { if (st.projF) projF = Object.assign({status: "", bereich: "", q: ""}, st.projF); }
    else if (v === "beleg") { if (st.belF) belF = Object.assign({year: "", typ: ""}, st.belF); }
    else if (v === "blocks") { if (st.blkTab) blkTab = st.blkTab; if (st.blkCat) blkCat = st.blkCat; }
    else if (v === "m42lager" && typeof m42F !== "undefined" && st.m42F) m42F = Object.assign({q: "", kat: "", filter: ""}, st.m42F);
    try { Object.keys(TSORT).forEach(k => { if (k.startsWith(v + "|")) delete TSORT[k]; }); Object.assign(TSORT, st.tsort || {}); localStorage.setItem("pa_tsort_v1", JSON.stringify(TSORT)); } catch (e) {}
    window.m85Flt = window.m85Flt || {}; window.m85Flt[v] = clone(st.m85 || {});
  }
  function applyView(a){ restore(a.view, a.state); active[a.view] = a.id; go(a.view); }
  window.m87Apply = id => { const a = (S.m87 || []).find(x_ => x_.id === id); if (a) applyView(a); };

  // ---------------------------------------------------------------- rows of a saved view (dashboard tile)
  async function rowsOf(a){
    const st = a.state || {}, pass = (id) => !window.m85Pass || window.m85Pass(OBJ[a.view], id, st.m85);
    if (a.view === "inv") { const t = st.invTab || "rechnung", f = Object.assign({year: "", status: "", q: ""}, st.invF || {});
      const base = S.invoices.filter(i => t === "draft" ? i.status === "entwurf" : t === "rechnung" ? (["rechnung", "storno"].includes(i.typ) && i.status !== "entwurf") : t === "mahn" ? false : i.typ === t);
      const rows = (t === "mahn" ? S.overdue : base.filter(i => (!f.year || i.datum.startsWith(f.year) || t === "draft") && (!f.status || i.status === f.status) &&
        (!f.q || (i.nr + " " + (i.addr || "") + " " + (i.titel || "")).toLowerCase().includes(f.q.toLowerCase())))).filter(i => pass(i.id));
      return {rows: rows.map(i => ({l: (i.status === "entwurf" ? "Entwurf" : i.nr) + " · " + invName(i), s: dde(i.datum) + (i.titel ? " · " + i.titel : ""), v: i.summe, go: () => openInvoice(i.id)})), sum: rows.reduce((s, i) => s + (i.summe || 0), 0)}; }
    if (a.view === "beleg") { const f = Object.assign({year: "", typ: ""}, st.belF || {});
      const rows = S.belege.filter(b => (!f.year || b.datum.startsWith(f.year)) && (!f.typ || b.typ === f.typ) && pass(b.id));
      return {rows: rows.map(b => ({l: b.partner || "–", s: dde(b.datum) + " · " + (b.kategorie || TYPES[b.typ] || b.typ), v: b.typ === "anlage" ? null : b.betrag})), sum: rows.filter(b => b.typ !== "anlage").reduce((s, b) => s + (b.betrag || 0), 0)}; }
    if (a.view === "users") { const ql = (st.custQ || "").toLowerCase();
      const rows = S.customers.filter(c => (!ql || (c.kdnr + " " + c.firma + " " + c.name + " " + c.ort + " " + c.mail).toLowerCase().includes(ql)) && pass(c.id));
      return {rows: rows.map(c => ({l: cname(c), s: (c.kdnr || "") + (c.ort ? " · " + c.ort : ""), go: () => go("users", c.id)})), sum: null}; }
    if (a.view === "proj") { const f = Object.assign({status: "", bereich: "", q: ""}, st.projF || {});
      const rows = S.projects.filter(p => (!f.status || p.status === f.status) && (!f.bereich || p.bereich === f.bereich) && (!f.q || (p.nr + " " + p.name + " " + p.descr).toLowerCase().includes(f.q.toLowerCase())) && pass(p.id));
      return {rows: rows.map(p => ({l: p.nr + " " + p.name, s: p.bereich + " · " + p.status, v: p.umsatz, go: () => go("project", p.id)})), sum: rows.reduce((s, p) => s + (p.umsatz || 0), 0)}; }
    if (a.view === "blocks") { const c = st.blkCat || "Alle";
      const rows = S.articles.filter(x_ => (c === "Alle" || (x_.cat || "Sonstiges") === c) && pass(x_.id));
      return {rows: rows.map(x_ => ({l: (x_.nr ? x_.nr + " " : "") + x_.name, s: x_.cat || "", v: x_.price})), sum: null}; }
    if (a.view === "m42lager") { const d = await api("/api/m42/list", undefined, {quiet: true}); const f = Object.assign({q: "", kat: "", filter: ""}, st.m42F || {});
      const rows = ((d && d.artikel) || []).filter(x_ => (f.filter === "nachbestellen" ? x_.nachbestellen : f.filter === "inaktiv" ? !x_.aktiv : x_.aktiv) && (!f.kat || x_.kategorie === f.kat) &&
        (!f.q || [x_.nr, x_.name, x_.lagerort, x_.kategorie].join(" ").toLowerCase().includes(f.q.toLowerCase())) && pass(x_.id));
      return {rows: rows.map(x_ => ({l: (x_.nr ? x_.nr + " " : "") + x_.name, s: nde(x_.bestand, 0) + " " + (x_.einheit || "") + (x_.lagerort ? " · " + x_.lagerort : ""), v: x_.wert})), sum: rows.reduce((s, x_) => s + (x_.wert || 0), 0)}; }
    return {rows: [], sum: null};
  }

  // ---------------------------------------------------------------- bar on the list pages
  async function saveDlg(v, a){
    const isNew = !a;
    const r = await modal(isNew ? "Ansicht speichern" : "Ansicht bearbeiten", `<div class="fr"><label class="f">Name<input class="in" id="m87n" value="${esc(a ? a.name : "")}" placeholder="z. B. Offene Rechnungen ${thisYear}"></label>
      <label class="chk"><input type="checkbox" id="m87d" ${a && a.dash ? "checked" : ""}> als Kachel auf der Übersicht zeigen</label>
      ${isNew ? `<div class="small muted">Gespeichert werden: Reiter, Suchtext, Filter (Jahr, Status, Bereich …), Spaltensortierung und der Feld-Filter.</div>`
        : `<label class="chk"><input type="checkbox" id="m87u"> mit den jetzigen Filtern überschreiben</label>`}</div>`,
      [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", value: "ok", onClick: async mb => {
        const body = {id: a ? a.id : null, view: v, name: $("#m87n", mb).value, dash: $("#m87d", mb).checked};
        if (isNew || ($("#m87u", mb) && $("#m87u", mb).checked)) body.state = capture(v);
        const res = await api("/api/m87/save", body); if (!res || !res.ok) return false; S.m87 = res.ansichten; active[v] = res.id; }}]);
    if (r === "ok") { toast("Ansicht gespeichert"); go(v); }
  }
  function bar(v){
    const page = $("#main .page"); if (!page || $(".m87bar", page)) return;
    const act = $(".ph .act", page);
    if (act && !$("#m87save", act)) { const b = document.createElement("button"); b.className = "btn"; b.id = "m87save"; b.type = "button"; b.title = "Filter, Suche und Sortierung dieser Liste als Ansicht speichern";
      b.innerHTML = `${ic("m87")} Ansicht speichern`; b.onclick = () => saveDlg(v, null); act.insertBefore(b, act.firstChild); }
    const mine = (S.m87 || []).filter(a => a.view === v); if (!mine.length) return;
    const d = document.createElement("div"); d.className = "m87bar chips"; d.style.cssText = "margin:-4px 0 12px;align-items:center";
    d.innerHTML = `<span class="small muted" style="margin-right:4px">${ic("m87")} Ansichten:</span>` + mine.map(a => `<span class="chip ${active[v] === a.id ? "on" : ""}" data-m87="${a.id}" title="Klick: anwenden · Doppelklick: bearbeiten">${a.dash ? "📌 " : ""}${esc(a.name)}
      <span data-m87x="${a.id}" title="Ansicht löschen" style="margin-left:6px;opacity:.6">×</span></span>`).join("");
    const ph = $(".ph", page); ph.parentNode.insertBefore(d, ph.nextSibling);
    $$("[data-m87]", d).forEach(c => { c.onclick = e => { if (e.target.dataset.m87x) return; const a = mine.find(x_ => x_.id === c.dataset.m87); applyView(a); };
      c.ondblclick = () => saveDlg(v, mine.find(x_ => x_.id === c.dataset.m87)); });
    $$("[data-m87x]", d).forEach(x_ => x_.onclick = async e => { e.stopPropagation(); const r = await api("/api/m87/delete", {id: x_.dataset.m87x}); if (r && r.ok) { S.m87 = r.ansichten; toast("Ansicht gelöscht"); go(v); } });
  }
  EXT.after.push(n => { const v = VIEWN[n]; if (v && view === v) setTimeout(() => bar(v), 0); });
  if (EXT.views.m42lager && !EXT.views.m42lager._m87) {
    const o = EXT.views.m42lager;
    EXT.views.m42lager = async function(...a){ const r = await o.apply(this, a); setTimeout(() => bar("m42lager"), 0); return r; };
    EXT.views.m42lager._m87 = true;
  }

  // ---------------------------------------------------------------- dashboard tile(s)
  EXT.dash.push(async el => {
    const list = (S.m87 || []).filter(a => a.dash); if (!list.length) return;
    const wrap = document.createElement("div"); wrap.className = "grid"; wrap.id = "m87dash";
    wrap.style.cssText = "grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-bottom:16px"; el.appendChild(wrap);
    for (const a of list) {
      const c = document.createElement("div"); c.className = "card"; wrap.appendChild(c);
      const r = await rowsOf(a);
      c.innerHTML = `<div class="hd"><h3>${ic("m87")} ${esc(a.name)}</h3><div class="act"><span class="badge">${r.rows.length}</span>${r.sum != null ? ` <b class="num" style="margin-left:6px">${eur(r.sum)}</b>` : ""}
        <button class="btn sm ghost" data-m87go type="button">öffnen</button></div></div><div class="small muted" style="padding:0 16px">${esc(LABEL[a.view] || a.view)}</div>
        <div class="bd" style="padding-top:6px">${r.rows.length ? `<table class="t"><tbody>${r.rows.slice(0, 6).map((x_, i) => `<tr class="${x_.go ? "click" : ""}" data-m87r="${i}"><td><b>${esc(x_.l)}</b><div class="small muted">${esc(x_.s || "")}</div></td><td class="r num">${x_.v != null ? eur(x_.v) : ""}</td></tr>`).join("")}</tbody></table>
          ${r.rows.length > 6 ? `<div class="small muted" style="margin-top:6px">… und ${r.rows.length - 6} weitere</div>` : ""}` : `<div class="empty small">Keine Einträge.</div>`}</div>`;
      $("[data-m87go]", c).onclick = () => applyView(a);
      $$("[data-m87r]", c).forEach(t => { const x_ = r.rows[+t.dataset.m87r]; if (x_.go) t.onclick = x_.go; });
    }
  });
})();
