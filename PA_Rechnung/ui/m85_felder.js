// PA Rechnung v2.0.19 - UI-Modul m85_felder: eigene Felder
// Einstellungs-Reiter "Eigene Felder", Eingabe in den Bearbeiten-Dialogen (Kunde, Projekt, Beleg, Lagerartikel),
// Knopf "Felder" bei Bausteinen und im Rechnungs-Editor, Spalten + Filter in den Listen.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m85 = '<path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="16" r="3"/>';
  const OBJ_ROUTES = {kunde:["/api/customer/save"], projekt:["/api/project/save"], beleg:["/api/beleg/update"], lager:["/api/m42/save"], rechnung:[], baustein:[]};
  const VIEW_OBJ = {inv:"rechnung", users:"kunde", proj:"projekt", beleg:"beleg", blocks:"baustein", m42lager:"lager"};
  window.m85Flt = window.m85Flt || {};          // view -> {fid, val} (also stored by saved views m87)
  let PEND = null;

  const M = () => S.m85 || {felder:[], werte:{}, objekte:{}, typen:{}};
  const felder = (obj, all) => M().felder.filter(f => f.objekt === obj && (all || f.aktiv));
  const wert = (obj, id, fid) => (((M().werte[obj] || {})[String(id)] || {})[String(fid)]) ?? "";
  const disp = (f, v) => { if (v === "" || v == null) return ""; if (f.typ === "janein") return String(v) === "1" ? "ja" : "nein";
    if (f.typ === "datum") return dde(v); if (f.typ === "zahl") return nde(+v, Math.abs(+v - Math.round(+v)) > 1e-9 ? 2 : 0); return String(v); };
  window.m85Disp = disp; window.m85Felder = felder; window.m85Wert = wert;

  // ---------------------------------------------------------------- input block
  function inputHtml(f, v){
    const id = "m85f" + f.id, req = f.pflicht ? " *" : "";
    const lab = `${esc(f.name)}${req}${f.hinweis ? ` <span class="muted small">${esc(f.hinweis)}</span>` : ""}`;
    if (f.typ === "janein") return `<label class="chk" style="margin:6px 0"><input type="checkbox" data-m85="${f.id}" ${String(v) === "1" ? "checked" : ""}> ${lab}</label>`;
    if (f.typ === "auswahl") return `<label class="f">${lab}<select class="in" data-m85="${f.id}"><option value=""></option>${(f.auswahl || []).map(a => `<option ${a === v ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></label>`;
    if (f.typ === "datum") return `<label class="f">${lab}<input type="date" class="in" data-m85="${f.id}" value="${esc(v)}"></label>`;
    if (f.typ === "zahl") return `<label class="f">${lab}<input class="in num" data-m85="${f.id}" value="${v === "" ? "" : esc(nde(+v, Math.abs(+v - Math.round(+v)) > 1e-9 ? 2 : 0))}"></label>`;
    if (f.typ === "link") return `<label class="f">${lab}<div class="row" style="gap:6px"><input class="in" id="${id}" data-m85="${f.id}" value="${esc(v)}" placeholder="https://… oder C:\\Pfad\\Datei">${v ? `<button class="btn sm ghost" type="button" data-m85open="${f.id}" style="flex:none">${ic("open")}</button>` : ""}</div></label>`;
    return `<label class="f">${lab}<input class="in" data-m85="${f.id}" value="${esc(v)}"></label>`;
  }
  function blockHtml(obj, id){
    const fs = felder(obj); if (!fs.length) return "";
    return `<div class="m85box" data-m85obj="${obj}" style="border-top:1px dashed var(--line);margin-top:10px;padding-top:8px">
      <div class="small muted" style="margin-bottom:4px">${ic("m85")} Eigene Felder</div><div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:4px 12px">${fs.map(f => inputHtml(f, id ? wert(obj, id, f.id) : "")).join("")}</div></div>`;
  }
  function readBlock(root){
    const out = {};
    $$("[data-m85]", root).forEach(e => { out[e.dataset.m85] = e.type === "checkbox" ? (e.checked ? "1" : "0") : e.value.trim(); });
    return out;
  }
  function checkReq(obj, vals){
    const miss = felder(obj).filter(f => f.pflicht && f.typ !== "janein" && !String(vals[f.id] ?? "").trim()).map(f => f.name);
    return miss.length ? "Pflichtfeld leer: " + miss.join(", ") : "";
  }
  function bindOpen(root){ $$("[data-m85open]", root).forEach(b => b.onclick = () => { const v = $(`[data-m85="${b.dataset.m85open}"]`, root).value.trim();
    if (/^https?:/i.test(v)) window.open(v, "_blank"); else api("/api/open", {path:v}); }); }
  async function saveVals(obj, id, vals){
    const r = await api("/api/m85/werte_save", {obj, id, werte: vals});
    if (r && r.ok) { const W = M().werte; W[obj] = W[obj] || {}; W[obj][String(id)] = {}; Object.entries(r.werte || {}).forEach(([k, v]) => W[obj][String(id)][String(k)] = v); }
    return r;
  }

  // a dialog of its own (articles, invoices, anything with an id)
  window.m85Edit = async function(obj, id, title){
    if (!felder(obj).length) { toast("Für " + (M().objekte[obj] || obj) + " sind noch keine eigenen Felder angelegt (Einstellungen › Eigene Felder)."); return false; }
    let ok = false;
    await modal(title || "Eigene Felder", `<div class="fr">${blockHtml(obj, id)}</div>`, [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
      const v = readBlock(mb), e = checkReq(obj, v); if (e) { toast(e, true); return false; }
      const r = await saveVals(obj, id, v); if (!r || !r.ok) return false; ok = true; }}], false, mb => bindOpen(mb));
    return ok;
  };

  // ---------------------------------------------------------------- inject into the existing dialogs
  const obs = new MutationObserver(ms => {
    if (!PEND) return;
    for (const m of ms) for (const n of m.addedNodes) {
      if (!(n instanceof HTMLElement) || !n.classList.contains("mb") || n._m85) continue;
      const p = PEND; PEND = null; n._m85 = p;
      const html = blockHtml(p.obj, p.id); if (!html) return;
      const host = $(".mc .fr", n) || $(".mc", n); if (!host) return;
      const d = document.createElement("div"); d.innerHTML = html; host.appendChild(d.firstElementChild); bindOpen(n);
      return;
    }
  });
  obs.observe(document.body, {childList:true});
  const wrapFn = (name, obj, idOf) => { const f = window[name]; if (typeof f !== "function" || f._m85) return;
    const w = function(...a){ PEND = {obj, id: idOf(a)}; setTimeout(() => { PEND = null; }, 1500); return f.apply(this, a); };
    w._m85 = true; window[name] = w; };
  wrapFn("editCustomer", "kunde", a => (a[0] && a[0].id) || null);
  wrapFn("editProject", "projekt", a => (a[0] && a[0].id) || null);
  wrapFn("newProject", "projekt", () => null);
  wrapFn("editBeleg", "beleg", a => (a[0] && a[0].id) || null);
  wrapFn("m42Edit", "lager", a => (a[0] && a[0].id) || null);

  // save the values together with the dialog's own save call
  const origApi = window.api;
  window.api = async function(path, body, opts){
    const obj = body !== undefined ? Object.keys(OBJ_ROUTES).find(o => OBJ_ROUTES[o].includes(path)) : null;
    const mb = obj ? [...document.querySelectorAll(".mb")].reverse().find(m => m._m85 && m._m85.obj === obj && $(".m85box", m)) : null;
    let vals = null;
    if (mb) { vals = readBlock(mb); const e = checkReq(obj, vals); if (e) { toast(e, true); return {ok:false, error:e}; } }
    const r = await origApi.call(this, path, body, opts);
    if (mb && r && r.ok !== false) { const id = r.id || (body && body.id) || (mb._m85 && mb._m85.id); if (id) await saveVals(obj, id, vals); }
    return r;
  };

  // ---------------------------------------------------------------- list columns + filter
  function fltBar(vkey, obj, rerender){
    const fs = felder(obj); if (!fs.length) return null;
    const st = window.m85Flt[vkey] || {};
    const d = document.createElement("div"); d.className = "m85fb row"; d.style.cssText = "margin:0 0 10px;align-items:center;gap:6px;flex-wrap:wrap";
    const f = fs.find(f => String(f.id) === String(st.fid));
    d.innerHTML = `<span class="small muted" style="flex:none">${ic("m85")} Feld-Filter</span><select class="in" data-m85ff style="width:auto;flex:none"><option value="">– kein –</option>${fs.map(x_ => `<option value="${x_.id}" ${String(x_.id) === String(st.fid) ? "selected" : ""}>${esc(x_.name)}</option>`).join("")}</select>
      ${f ? (f.typ === "auswahl" || f.typ === "janein" ? `<select class="in" data-m85fv style="width:auto;flex:none"><option value="">(alle)</option><option value="__leer" ${st.val === "__leer" ? "selected" : ""}>(leer)</option>${(f.typ === "janein" ? [["1", "ja"], ["0", "nein"]] : f.auswahl.map(a => [a, a])).map(([k, l]) => `<option value="${esc(k)}" ${st.val === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`
        : `<input class="in" data-m85fv style="max-width:200px;flex:none" placeholder="enthält … / >100 / <100" value="${esc(st.val || "")}">`) : ""}`;
    $("[data-m85ff]", d).onchange = e => { window.m85Flt[vkey] = {fid: e.target.value, val: ""}; rerender(); };
    const fv = $("[data-m85fv]", d);
    if (fv) { const h = () => { window.m85Flt[vkey] = {fid: st.fid, val: fv.value}; applyFlt(vkey, obj); };
      if (fv.tagName === "SELECT") fv.onchange = h; else fv.oninput = () => { clearTimeout(fv._t); fv._t = setTimeout(h, 200); }; }
    return d;
  }
  function match(f, v, want){
    if (want === "" || want == null) return true;
    if (want === "__leer") return v === "" || v == null;
    if (f.typ === "auswahl" || f.typ === "janein") return String(v) === want;
    const w = String(want).trim(), m = w.match(/^([<>]=?)\s*(.+)$/);
    if (m && (f.typ === "zahl" || f.typ === "datum")) { const a = f.typ === "zahl" ? +v : String(v), b = f.typ === "zahl" ? pnum(m[2]) : m[2];
      if (v === "") return false; return m[1] === ">" ? a > b : m[1] === ">=" ? a >= b : m[1] === "<" ? a < b : a <= b; }
    return String(disp(f, v)).toLowerCase().includes(w.toLowerCase());
  }
  const ROWSEL = {rechnung:["tr[data-open]", "open"], beleg:["tr[data-b]", "b"], baustein:["tr[data-a]", "a"], lager:["tr[data-m42id]", "m42id"], kunde:[".list .it[data-c]", "c"], projekt:[".pcard[data-proj]", "proj"]};
  function applyFlt(vkey, obj){
    const st = window.m85Flt[vkey] || {}, f = felder(obj).find(x_ => String(x_.id) === String(st.fid));
    const [sel, attr] = ROWSEL[obj];
    $$("#main " + sel).forEach(r => { const id = r.dataset[attr]; r.style.display = !f || match(f, wert(obj, id, f.id), st.val) ? "" : "none"; });
  }
  window.m85Apply = (vkey) => { const obj = VIEW_OBJ[vkey]; if (obj) applyFlt(vkey, obj); };
  // used by the saved views (m87): does object id pass the field filter st = {fid, val}?
  window.m85Pass = (obj, id, st) => { if (!st || !st.fid) return true; const f = felder(obj).find(x_ => String(x_.id) === String(st.fid)); return !f || match(f, wert(obj, id, f.id), st.val); };

  function addColumns(obj){
    const fs = felder(obj).filter(f => f.spalte); if (!fs.length) return;
    const [sel, attr] = ROWSEL[obj];
    const rows = $$("#main " + sel); if (!rows.length) return;
    if (rows[0].tagName === "TR") {
      const tbl = rows[0].closest("table"); if (!tbl || tbl._m85) return; tbl._m85 = true;
      const hr = tbl.tHead && tbl.tHead.rows[0]; if (!hr) return;
      const lastIsAct = !hr.cells[hr.cells.length - 1].textContent.trim();
      const at = lastIsAct ? hr.cells.length - 1 : hr.cells.length;
      fs.forEach((f, k) => { const th = document.createElement("th"); th.textContent = f.name; th.className = "m85c"; hr.insertBefore(th, hr.cells[at + k] || null); });
      $$("tr", tbl.tBodies[0]).forEach(r => { const id = r.dataset[attr];
        if (!id) { const c = r.cells[0]; if (c && c.colSpan > 1) c.colSpan += fs.length; return; }
        fs.forEach((f, k) => { const td = document.createElement("td"); td.className = "small m85c"; td.textContent = disp(f, wert(obj, id, f.id)); r.insertBefore(td, r.cells[at + k] || null); }); });
      const ft = tbl.tFoot && tbl.tFoot.rows[0]; if (ft && ft.cells[0]) ft.cells[0].colSpan += fs.length;
    } else {
      rows.forEach(r => { if ($(".m85v", r)) return; const id = r.dataset[attr];
        const t = fs.map(f => { const v = disp(f, wert(obj, id, f.id)); return v ? `<span class="badge" style="margin:2px 3px 0 0">${esc(f.name)}: ${esc(v)}</span>` : ""; }).join("");
        if (!t) return; const d = document.createElement("div"); d.className = "m85v small"; d.innerHTML = t;
        const host = r.querySelector("div[style*='min-width:0']") || r; host.appendChild(d); });
    }
  }
  function decorate(vkey, rerender){
    const obj = VIEW_OBJ[vkey]; if (!obj || view !== vkey) return;
    const page = $("#main .page"); if (!page || $(".m85fb", page)) { addColumns(obj); applyFlt(vkey, obj); return; }
    addColumns(obj);
    const bar = fltBar(vkey, obj, rerender);
    if (bar) { const anchor = obj === "kunde" ? $(".split", page) : (page.querySelector(".card table.t") || page.querySelector(".pgrid") || page.querySelector(".card.empty"));
      const holder = anchor ? (anchor.closest(".card") && obj !== "projekt" ? anchor.closest(".card") : anchor) : null;
      if (holder && holder.parentNode) holder.parentNode.insertBefore(bar, holder); else page.appendChild(bar); }
    applyFlt(vkey, obj);
  }
  window.m85Decorate = decorate;

  EXT.after.push((n, ...a) => {
    const map = {vInvoices:["inv", () => vInvoices()], vBelege:["beleg", () => vBelege()], vBlocks:["blocks", () => vBlocks()], vCustomers:["users", () => vCustomers()], vProjects:["proj", () => vProjects()]};
    if (map[n]) setTimeout(() => decorate(map[n][0], map[n][1]), 0);
    if (n === "vBlocks") setTimeout(() => {
      if (!felder("baustein").length) return;
      $$("#main tr[data-a]").forEach(r => { const c = r.cells[r.cells.length - 1]; if (!c || $("[data-m85a]", c)) return;
        const b = document.createElement("button"); b.className = "btn sm ghost"; b.title = "Eigene Felder"; b.dataset.m85a = r.dataset.a; b.innerHTML = ic("m85");
        b.onclick = async e => { e.stopPropagation(); if (await m85Edit("baustein", +r.dataset.a, "Eigene Felder – Baustein")) vBlocks(); };
        c.insertBefore(b, c.firstChild); }); }, 0);
    if (n === "vEditor" && typeof cur !== "undefined" && cur && cur.id && felder("rechnung").length) setTimeout(() => {
      const act = $("#main .ph .act"); if (!act || $("#m85ed", act)) return;
      const fs = felder("rechnung"), filled = fs.filter(f => wert("rechnung", cur.id, f.id) !== "").length;
      const b = document.createElement("button"); b.className = "btn ghost"; b.id = "m85ed"; b.type = "button";
      b.innerHTML = `${ic("m85")} Felder${filled ? ` <span class="badge">${filled}/${fs.length}</span>` : ""}`;
      b.onclick = async () => { if (await m85Edit("rechnung", cur.id, "Eigene Felder – " + (cur.nr || "Dokument"))) vEditor(); };
      act.insertBefore(b, act.firstChild); }, 0);
    if (n === "vCustomers") setTimeout(() => {
      const fs = felder("kunde"); if (!fs.length || typeof custSel === "undefined" || !custSel) return;
      const grid = $("#main .card .bd.grid.g3"); if (!grid || $(".m85cd", grid)) return;
      const d = document.createElement("div"); d.className = "m85cd"; d.style.gridColumn = "1 / -1";
      d.innerHTML = `<div class="small muted">Eigene Felder <a href="#" data-m85ce class="small">bearbeiten</a></div><div>${fs.map(f => { const v = disp(f, wert("kunde", custSel, f.id));
        return `<span class="badge" style="margin:3px 4px 0 0">${esc(f.name)}: <b>${v ? esc(v) : "–"}</b></span>`; }).join("")}</div>`;
      grid.appendChild(d);
      $("[data-m85ce]", d).onclick = async e => { e.preventDefault(); if (await m85Edit("kunde", custSel, "Eigene Felder – Kunde")) vCustomers(); }; }, 0);
    if (n === "vProject") setTimeout(() => {
      const id = a[0], fs = felder("projekt"); if (!fs.length || !id) return;
      const ph = $("#main .ph"); if (!ph || $(".m85pd", ph.parentNode)) return;
      const d = document.createElement("div"); d.className = "m85pd small"; d.style.margin = "-6px 0 12px";
      d.innerHTML = fs.map(f => { const v = disp(f, wert("projekt", id, f.id)); return `<span class="badge" style="margin:2px 4px 0 0">${esc(f.name)}: <b>${v ? esc(v) : "–"}</b></span>`; }).join("") + ` <a href="#" data-m85pe class="small">Felder bearbeiten</a>`;
      ph.parentNode.insertBefore(d, ph.nextSibling);
      $("[data-m85pe]", d).onclick = async e => { e.preventDefault(); if (await m85Edit("projekt", id, "Eigene Felder – Projekt")) vProject(id); }; }, 0);
  });
  // Lager page (an EXT view, not covered by EXT.after)
  if (EXT.views.m42lager && !EXT.views.m42lager._m85) {
    const o = EXT.views.m42lager;
    EXT.views.m42lager = async function(...a){ const r = await o.apply(this, a); setTimeout(() => decorate("m42lager", () => EXT.views.m42lager()), 0); return r; };
    EXT.views.m42lager._m85 = true;
  }

  // ---------------------------------------------------------------- settings tab
  async function renderSettings(el){
    const d = await api("/api/m85/felder");
    const fs = d.felder || [], objs = d.objekte || {}, typen = d.typen || {};
    el.innerHTML = `<div class="card" style="margin-top:14px"><div class="hd"><h3>Eigene Felder</h3><div class="act"><button class="btn pri" id="m85new">${ic("plus")} Neues Feld</button></div></div>
      <div class="bd"><div class="small muted" style="margin-bottom:10px">Zusätzliche Angaben, die das Programm nicht kennt – z. B. „Raum-Nr.“ beim Kunden, „EXC-Klasse“ beim Projekt, „Garantie bis“ beim Lagerartikel.
        Eingabe in den Bearbeiten-Dialogen, Spalte und Filter in den Listen, Platzhalter <code>{{Feld:Name}}</code> in Rechnungs-, Mail- und Brieftexten, Spalten in den Excel-/PDF-Exporten.</div>
      ${Object.entries(objs).map(([k, l]) => { const ff = fs.filter(f => f.objekt === k); return `<div style="margin:12px 0 4px"><b>${esc(l)}</b> <span class="muted small">${ff.length || "keine"} Feld(er)</span></div>
        ${ff.length ? `<table class="t"><thead><tr><th style="width:60px"></th><th>Name</th><th>Typ</th><th>Pflicht</th><th>Spalte in Liste</th><th>Aktiv</th><th>Platzhalter</th><th style="width:90px"></th></tr></thead><tbody>${ff.map((f, i) => `<tr data-m85id="${f.id}" class="click">
          <td onclick="event.stopPropagation()"><button class="btn sm ghost" data-m85up="${f.id}" ${i ? "" : "disabled"}>▲</button><button class="btn sm ghost" data-m85dn="${f.id}" ${i < ff.length - 1 ? "" : "disabled"}>▼</button></td>
          <td><b>${esc(f.name)}</b>${f.typ === "auswahl" ? `<div class="small muted">${esc((f.auswahl || []).join(" · "))}</div>` : ""}</td><td>${esc(typen[f.typ] || f.typ)}</td>
          <td>${f.pflicht ? "ja" : ""}</td><td>${f.spalte ? "ja" : ""}</td><td>${f.aktiv ? "ja" : "nein"}</td><td class="small"><code>{{Feld:${esc(f.name)}}}</code></td>
          <td class="r" onclick="event.stopPropagation()"><button class="btn sm ghost danger" data-m85del="${f.id}" title="Feld und alle Werte löschen">${ic("trash")}</button></td></tr>`).join("")}</tbody></table>` : ""}`; }).join("")}</div></div>`;
    const re = async () => { await reload(); renderSettings(el); };
    $("#m85new", el).onclick = () => editFeld({objekt: "kunde", typ: "text", aktiv: 1}, objs, typen, re);
    $$("[data-m85id]", el).forEach(r => r.onclick = () => editFeld(fs.find(f => f.id == r.dataset.m85id), objs, typen, re));
    $$("[data-m85del]", el).forEach(b => b.onclick = async () => { await api("/api/m85/feld_delete", {id: +b.dataset.m85del}); toast("Feld gelöscht"); re(); });
    const move = async (id, dir) => { const f = fs.find(x_ => x_.id == id), ff = fs.filter(x_ => x_.objekt === f.objekt), i = ff.indexOf(f), j = i + dir;
      if (j < 0 || j >= ff.length) return; [ff[i], ff[j]] = [ff[j], ff[i]]; await api("/api/m85/sort", {ids: ff.map(x_ => x_.id)}); re(); };
    $$("[data-m85up]", el).forEach(b => b.onclick = () => move(+b.dataset.m85up, -1));
    $$("[data-m85dn]", el).forEach(b => b.onclick = () => move(+b.dataset.m85dn, 1));
  }
  async function editFeld(f, objs, typen, after){
    const html = `<div class="fr"><div class="row"><label class="f">Bereich<select class="in" id="m85o">${Object.entries(objs).map(([k, l]) => `<option value="${k}" ${f.objekt === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      <label class="f">Name<input class="in" id="m85n" value="${esc(f.name || "")}" placeholder="z. B. Raum-Nr., EXC-Klasse, Garantie bis"></label></div>
      <div class="row"><label class="f">Typ<select class="in" id="m85t">${Object.entries(typen).map(([k, l]) => `<option value="${k}" ${f.typ === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label class="f">Hinweis (optional)<input class="in" id="m85h" value="${esc(f.hinweis || "")}" placeholder="kleiner Text neben dem Feld"></label></div>
      <label class="f" id="m85al">Auswahlwerte (einer je Zeile)<textarea class="in" id="m85a" rows="4">${esc((f.auswahl || []).join("\n"))}</textarea></label>
      <div class="row"><label class="chk"><input type="checkbox" id="m85p" ${f.pflicht ? "checked" : ""}> Pflichtfeld</label><label class="chk"><input type="checkbox" id="m85s" ${f.spalte ? "checked" : ""}> als Spalte in der Liste zeigen</label>
        <label class="chk"><input type="checkbox" id="m85k" ${f.aktiv !== 0 ? "checked" : ""}> aktiv</label></div></div>`;
    await modal(f.id ? "Feld bearbeiten" : "Neues eigenes Feld", html, [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
      const r = await api("/api/m85/feld_save", {id: f.id || null, objekt: $("#m85o", mb).value, name: $("#m85n", mb).value, typ: $("#m85t", mb).value, hinweis: $("#m85h", mb).value,
        auswahl: $("#m85a", mb).value, pflicht: $("#m85p", mb).checked, spalte: $("#m85s", mb).checked, aktiv: $("#m85k", mb).checked ? 1 : 0});
      if (!r || !r.ok) return false; }}], false, mb => { const t = $("#m85t", mb), al = $("#m85al", mb); const h = () => al.style.display = t.value === "auswahl" ? "" : "none"; t.onchange = h; h(); });
    after();
  }
  EXT.settings.push({key: "m85", label: "Eigene Felder", render: renderSettings});
})();
