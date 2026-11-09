// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m75_pruefungen: Pruefprotokolle mit Fristen
// Seite "Prüfungen" (Projekte): Prueflinge mit Faelligkeit, Pruefungen erfassen (Messwerte, automatische
// Bewertung), PDF-Protokoll, Sammelprotokoll je Kunde, Abrechnen, Pruefarten, Pruefgeraete (Kalibrierung).
// Karte auf der Kundenseite, Hinweis im Dashboard.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m75 = '<path d="M9 3h6v3H9z"/><path d="M7 5H5v16h14V5h-2"/><path d="M9 13l2 2 4-4"/>';
  const ST = (() => { try { return Object.assign({tab:"prueflinge", cid:"", q:"", filter:""}, JSON.parse(localStorage.getItem("pa_m75") || "{}")); } catch (e) { return {tab:"prueflinge", cid:"", q:"", filter:""}; } })();
  const save = () => { try { localStorage.setItem("pa_m75", JSON.stringify({tab:ST.tab, cid:ST.cid, filter:ST.filter})); } catch (e) {} };
  const STL = {nie:["nie geprüft","warn"], ueberfaellig:["überfällig","bad"], faellig:["fällig","warn"], gesperrt:["gesperrt","bad"], ok:["ok","ok"]};
  const ERC = {bestanden:"ok", maengel:"warn", nicht_bestanden:"bad"};
  let D = null;

  EXT.nav.push({key:"m75", label:"Prüfungen", icon:"m75", section:"Projekte", cnt: () => (S.m75 && (S.m75.faellig || (S.m75.kalib || []).length)) ? "⚠ " + (S.m75.faellig + (S.m75.kalib || []).length) : ""});
  EXT.views.m75 = m75View;

  EXT.dash.push(el => {
    const m = S.m75; if (!m || !(m.faellig || (m.kalib || []).length)) return;
    const d = document.createElement("div"); d.className = "alert warn"; d.style.marginBottom = "10px";
    const txt = m.liste.slice(0, 3).map(r => esc((r.inventar_nr || r.bezeichnung) + " (" + r.kunde + ")")).join(" · ") + ((m.kalib || []).length ? " · " + m.kalib.map(k => esc(k.name + ": " + k.text)).join(" · ") : "");
    d.innerHTML = `${ic("m75")}<b>${m.faellig} Prüfung(en) fällig${m.ueberfaellig ? `, ${m.ueberfaellig} überfällig/gesperrt` : ""}</b><span class="small">${txt}</span><span class="sp" style="flex:1"></span><span class="small"><u>Ansehen →</u></span>`;
    d.onclick = () => { ST.filter = "faellig"; ST.tab = "prueflinge"; go("m75"); };
    el.appendChild(d);
  });

  const cOpts = (sel, eigen = true) => (eigen ? `<option value="0" ${!sel || sel == "0" ? "selected" : ""}>Eigenes Inventar</option>` : "") +
    S.customers.map(c => `<option value="${c.id}" ${c.id == sel ? "selected" : ""}>${esc(cname(c))} (${esc(c.kdnr)})</option>`).join("");
  const aOpts = (sel, list) => `<option value="">– Prüfart wählen –</option>` + (list || D.arten).filter(a => a.aktiv || a.id == sel).map(a => `<option value="${a.id}" ${a.id == sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
  const gOpts = sel => `<option value="">– kein Prüfgerät –</option>` + D.geraete.filter(g => g.aktiv || g.id == sel).map(g => `<option value="${g.id}" ${g.id == sel ? "selected" : ""}>${esc(g.name)}${g.kalibriert_am ? " (kal. " + dde(g.kalibriert_am) + ")" : ""}</option>`).join("");
  const stB = s => { const x_ = STL[s] || ["", ""]; return `<span class="badge ${x_[1]}"><span class="dot"></span>${x_[0]}</span>`; };
  const erB = e => e ? `<span class="badge ${ERC[e] || ""}"><span class="dot"></span>${esc(D.ergebnis[e] || e)}</span>` : `<span class="muted">–</span>`;

  async function load(){ D = await api("/api/m75/data" + (ST.cid !== "" ? "?customer_id=" + ST.cid : "")); return D && D.ok; }

  // ------------------------------------------------------------------ main page
  async function m75View(arg){
    if (arg && arg.customer_id !== undefined) ST.cid = String(arg.customer_id);
    if (arg && arg.tab) ST.tab = arg.tab;
    if (!(await load())) return;
    const pls = D.prueflinge, pr = D.pruefungen;
    const fae = pls.filter(p => p.aktiv && ["nie", "ueberfaellig", "faellig", "gesperrt"].includes(p.status));
    const offenAbr = pr.filter(p => !p.invoice_id && p.customer_id).length;
    const tabs = [["prueflinge", `Prüflinge (${pls.filter(p => p.aktiv).length})`], ["pruefungen", `Prüfungen (${pr.length})`], ["arten", "Prüfarten"], ["geraete", `Prüfgeräte${D.kalib.length ? " ⚠" : ""}`]];
    $("#main").innerHTML = `<div class="page">${pageHead("Prüfungen", "DGUV V3, DGUV V17/Rigging, Leitern und eigene Prüfarten – mit Messwerten, Plakette, Protokoll und Fristen",
        expButtons("m75_pruefungen", {customer_id: ST.cid === "" ? undefined : ST.cid}) + `<button class="btn" id="m75cfg">${ic("set")} Einstellungen</button><button class="btn" id="m75pl">${ic("plus")} Prüfling</button><button class="btn pri" id="m75new">${ic("plus")} Prüfung erfassen</button>`)}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Prüflinge</div><div class="v">${pls.filter(p => p.aktiv).length}</div><div class="s">${new Set(pls.map(p => p.customer_id || 0)).size} Kunde(n) / Inventar</div></div>
        <div class="card kpi click" id="m75kf"><div class="l">Fällig</div><div class="v" style="color:${fae.length ? "var(--warn)" : "inherit"}">${fae.length}</div><div class="s">${fae.filter(p => p.status === "ueberfaellig").length} überfällig · ${fae.filter(p => p.status === "nie").length} nie geprüft</div></div>
        <div class="card kpi"><div class="l">Prüfungen ${thisYear}</div><div class="v">${pr.filter(p => (p.datum || "").startsWith(String(thisYear))).length}</div><div class="s">${pr.filter(p => p.ergebnis === "nicht_bestanden" && (p.datum || "").startsWith(String(thisYear))).length} nicht bestanden</div></div>
        <div class="card kpi"><div class="l">Nicht abgerechnet</div><div class="v">${offenAbr}</div><div class="s">Prüfungen bei Kunden</div></div></div>
      ${D.kalib.map(k => `<div class="alert warn" style="margin-bottom:8px;cursor:default">${ic("alert")}<span><b>Prüfgerät ${esc(k.name)}:</b> ${esc(k.text)}</span></div>`).join("")}
      <div class="row" style="margin-bottom:14px;align-items:center;flex-wrap:wrap">
        <div class="seg" style="flex:none">${tabs.map(([k, l]) => `<button class="${ST.tab === k ? "on" : ""}" data-m75t="${k}">${l}</button>`).join("")}</div>
        <select class="in" id="m75cid" style="width:auto;max-width:280px"><option value="" ${ST.cid === "" ? "selected" : ""}>Alle Kunden + Inventar</option>${cOpts(ST.cid === "" ? "x" : ST.cid)}</select>
        <div class="search" style="max-width:280px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="m75q" placeholder="Inv.-Nr., Bezeichnung, Seriennr. …" value="${esc(ST.q)}"></div>
        <span style="flex:1"></span>
        ${ST.cid !== "" && ST.cid !== "0" ? `<button class="btn" id="m75sam">${ic("pdf")} Sammelprotokoll</button>` : ""}</div>
      <div id="m75body"></div></div>`;
    bindCommon();
    $$("[data-m75t]").forEach(b => b.onclick = () => { ST.tab = b.dataset.m75t; save(); m75View(); });
    $("#m75cid").onchange = e => { ST.cid = e.target.value; save(); m75View(); };
    $("#m75q").oninput = e => { ST.q = e.target.value; clearTimeout(window._m75T); window._m75T = setTimeout(body, 180); };
    $("#m75kf").onclick = () => { ST.tab = "prueflinge"; ST.filter = ST.filter === "faellig" ? "" : "faellig"; save(); m75View(); };
    $("#m75cfg").onclick = settings;
    $("#m75pl").onclick = () => editPl(null);
    $("#m75new").onclick = () => editPr({});
    if ($("#m75sam")) $("#m75sam").onclick = () => sammel(+ST.cid);
    body();
  }

  const qm = (...a) => { const q_ = ST.q.trim().toLowerCase(); return !q_ || a.join(" ").toLowerCase().includes(q_); };

  function body(){
    const el = $("#m75body"); if (!el || !D) return;
    if (ST.tab === "prueflinge") return bodyPl(el);
    if (ST.tab === "pruefungen") return bodyPr(el);
    if (ST.tab === "arten") return bodyArten(el);
    return bodyGeraete(el);
  }

  function bodyPl(el){
    const list = D.prueflinge.filter(p => (ST.filter === "faellig" ? p.aktiv && ["nie", "ueberfaellig", "faellig", "gesperrt"].includes(p.status) : ST.filter === "inaktiv" ? !p.aktiv : p.aktiv) &&
      qm(p.inventar_nr, p.bezeichnung, p.hersteller, p.typ, p.seriennr, p.standort, p.kunde, p.art_name));
    el.innerHTML = `<div class="row" style="margin-bottom:10px;align-items:center"><div class="seg" style="flex:none">${[["", "Aktiv"], ["faellig", "Fällig"], ["inaktiv", "Ausgemustert"]].map(([k, l]) => `<button class="${ST.filter === k ? "on" : ""}" data-m75f="${k}">${l}</button>`).join("")}</div>
        <span style="flex:1"></span>${D.assets.length ? `<button class="btn sm" id="m75inv">${ic("box")} Aus Anlagen & Inventar übernehmen</button>` : ""}</div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Inv.-Nr.</th><th>Bezeichnung</th><th>Kunde / Standort</th><th>Prüfart</th><th>Letzte</th><th>Ergebnis</th><th>Plakette</th><th>Nächste</th><th>Status</th><th style="width:150px"></th></tr></thead>
      <tbody>${list.map(p => `<tr class="click" data-m75pl="${p.id}"><td><b>${esc(p.inventar_nr || "")}</b></td><td>${esc(p.bezeichnung || "")}<div class="small muted">${esc([p.hersteller, p.typ, p.seriennr ? "SN " + p.seriennr : ""].filter(Boolean).join(" · "))}</div></td>
        <td class="small">${esc(p.kunde)}${p.standort ? `<div class="muted">${esc(p.standort)}</div>` : ""}</td><td class="small">${esc(p.art_name || "–")}</td><td class="num">${dde(p.letzte) || "–"}</td><td>${erB(p.ergebnis)}</td>
        <td class="small">${esc(p.plakette || "")}</td><td class="num">${dde(p.naechste) || "–"}</td><td>${stB(p.status)}</td>
        <td class="r" style="white-space:nowrap" onclick="event.stopPropagation()"><button class="btn sm pri" data-m75p="${p.id}" title="Prüfung erfassen">Prüfen</button><button class="btn sm ghost" data-m75h="${p.id}" title="Prüfungen dieses Prüflings">${ic("clock")}</button></td></tr>`).join("")
      || `<tr><td colspan="10" class="empty">${D.prueflinge.length ? "Keine Prüflinge für diesen Filter." : "Noch keine Prüflinge. Mit „Prüfling“ anlegen oder aus Anlagen & Inventar übernehmen."}</td></tr>`}</tbody></table></div>`;
    $$("[data-m75f]", el).forEach(b => b.onclick = () => { ST.filter = b.dataset.m75f; save(); body(); });
    $$("[data-m75pl]", el).forEach(r => r.onclick = () => editPl(D.prueflinge.find(p => p.id == r.dataset.m75pl)));
    $$("[data-m75p]", el).forEach(b => b.onclick = () => { const p = D.prueflinge.find(x_ => x_.id == b.dataset.m75p); editPr({pruefling_id:p.id, art_id:p.art_id}); });
    $$("[data-m75h]", el).forEach(b => b.onclick = () => { const p = D.prueflinge.find(x_ => x_.id == b.dataset.m75h); ST.tab = "pruefungen"; ST.q = p.inventar_nr || p.bezeichnung || ""; save(); m75View(); });
    if ($("#m75inv", el)) $("#m75inv", el).onclick = fromInventory;
    selectify({kind:"m75pl", rows:"tr[data-m75pl]", id:"data-m75pl", rerender: m75View, actions:[
      {label:"Excel", run: async ids => { await doExport("m75_pruefungen", "xlsx", {ids, teil:"prueflinge"}); return false; }},
      {label:"Ausmustern", run: async ids => { for (const id of ids) { const p = D.prueflinge.find(x_ => x_.id == id); if (p) await api("/api/m75/pruefling/save", Object.assign({}, p, {aktiv:0})); } toast(ids.length + " ausgemustert"); }},
      {label:"Löschen", cls:"danger", run: async ids => { await api("/api/m75/delete", {kind:"pruefling", ids}); toast(ids.length + " Prüfling(e) gelöscht"); await reload(); }}]});
  }

  function bodyPr(el){
    const list = D.pruefungen.filter(p => qm(p.inventar_nr, p.bezeichnung, p.seriennr, p.kunde, p.art_name, p.plakette, p.pruefer, p.inv_nr));
    el.innerHTML = `<div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Datum</th><th>Prüfling</th><th>Kunde</th><th>Prüfart</th><th>Ergebnis</th><th>Plakette</th><th>Nächste</th><th>Prüfer</th><th>Rechnung</th><th style="width:90px"></th></tr></thead>
      <tbody>${list.map(p => `<tr class="click" data-m75pr="${p.id}"><td class="num">${dde(p.datum)}</td><td><b>${esc(p.inventar_nr || "")}</b> ${esc(p.bezeichnung || "")}${p.maengel ? `<div class="small" style="color:var(--warn)">${esc(p.maengel)}</div>` : ""}</td>
        <td class="small">${esc(p.kunde)}</td><td class="small">${esc(p.art_name || "")}</td><td>${erB(p.ergebnis)}</td><td class="small">${esc(p.plakette || "")}</td><td class="num">${dde(p.naechste) || "–"}</td><td class="small">${esc(p.pruefer || "")}</td>
        <td class="small">${p.inv_nr ? `<a href="#" data-m75inv="${p.invoice_id}">${esc(p.inv_nr)}</a>` : (p.customer_id ? `<span class="muted">offen</span>` : `<span class="muted">–</span>`)}</td>
        <td class="r" onclick="event.stopPropagation()"><button class="btn sm" data-m75pdf="${p.id}" title="PDF-Prüfprotokoll">${ic("pdf")} PDF</button></td></tr>`).join("")
      || `<tr><td colspan="10" class="empty">Noch keine Prüfungen.</td></tr>`}</tbody></table></div>
      <div class="small muted" style="margin-top:10px">Mehrere Prüfungen eines Kunden markieren → „Abrechnen“ erzeugt einen Rechnungsentwurf (Preis je Prüfart in den Einstellungen).</div>`;
    $$("[data-m75pr]", el).forEach(r => r.onclick = () => editPr(D.pruefungen.find(p => p.id == r.dataset.m75pr)));
    $$("[data-m75pdf]", el).forEach(b => b.onclick = () => pdf([+b.dataset.m75pdf]));
    $$("[data-m75inv]", el).forEach(a => a.onclick = e => { e.preventDefault(); e.stopPropagation(); openInvoice(+a.dataset.m75inv); });
    selectify({kind:"m75pr", rows:"tr[data-m75pr]", id:"data-m75pr", rerender: m75View, actions:[
      {label:"PDF-Protokolle", run: async ids => { await pdf(ids); return false; }},
      {label:"Abrechnen", cls:"pri", run: async ids => { const r = await api("/api/m75/abrechnen", {ids}); if (r && r.ok) { toast(`Rechnungsentwurf ${r.nr} mit ${r.n} Prüfung(en)`); await reload(); openInvoice(r.id); } return false; }},
      {label:"Excel", run: async ids => { await doExport("m75_pruefungen", "xlsx", {ids, teil:"pruefungen"}); return false; }},
      {label:"Löschen", cls:"danger", run: async ids => { await api("/api/m75/delete", {kind:"pruefung", ids}); toast(ids.length + " Prüfung(en) gelöscht"); await reload(); }}]});
  }

  function bodyArten(el){
    el.innerHTML = `<div class="row" style="margin-bottom:10px"><span style="flex:1"></span><button class="btn pri" id="m75an">${ic("plus")} Eigene Prüfart</button></div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Prüfart</th><th>Norm / Grundlage</th><th class="r">Intervall</th><th class="r">Prüffelder</th><th class="r">Preis je Prüfling</th><th>Status</th></tr></thead>
      <tbody>${D.arten.map(a => `<tr class="click" data-m75a="${a.id}"><td><b>${esc(a.name)}</b>${a.eigen ? ` <span class="badge">eigene</span>` : ""}</td><td class="small">${esc(a.norm || "")}</td>
        <td class="r num">${a.intervall} Mon.</td><td class="r num">${a.felder.length}</td><td class="r num">${(D.cfg.preis_art || {})[a.id] || a.preis ? eur((D.cfg.preis_art || {})[a.id] || a.preis) : "–"}</td>
        <td>${a.aktiv ? `<span class="badge ok"><span class="dot"></span>aktiv</span>` : `<span class="badge">aus</span>`}</td></tr>`).join("")}</tbody></table></div>`;
    $("#m75an", el).onclick = () => editArt(null);
    $$("[data-m75a]", el).forEach(r => r.onclick = () => editArt(D.arten.find(a => a.id == r.dataset.m75a)));
  }

  function bodyGeraete(el){
    el.innerHTML = `<div class="row" style="margin-bottom:10px"><span style="flex:1"></span><button class="btn pri" id="m75gn">${ic("plus")} Prüfgerät</button></div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Prüfgerät</th><th>Hersteller / Typ</th><th>Seriennr.</th><th>Kalibriert am</th><th class="r">Intervall</th><th>Status</th></tr></thead>
      <tbody>${D.geraete.map(g => { const k = D.kalib.find(x_ => x_.id === g.id);
        return `<tr class="click" data-m75g="${g.id}"><td><b>${esc(g.name)}</b></td><td class="small">${esc([g.hersteller, g.typ].filter(Boolean).join(" "))}</td><td class="small">${esc(g.seriennr || "")}</td>
        <td class="num">${dde(g.kalibriert_am) || "–"}</td><td class="r num">${g.kalibrier_monate} Mon.</td><td>${!g.aktiv ? `<span class="badge">aus</span>` : k ? `<span class="badge warn"><span class="dot"></span>${esc(k.text)}</span>` : `<span class="badge ok"><span class="dot"></span>kalibriert</span>`}</td></tr>`; }).join("")
      || `<tr><td colspan="6" class="empty">Noch kein Prüfgerät. Das Messgerät (z. B. Gerätetester) mit Kalibrierdatum anlegen – es erscheint im Protokoll.</td></tr>`}</tbody></table></div>`;
    $("#m75gn", el).onclick = () => editGeraet(null);
    $$("[data-m75g]", el).forEach(r => r.onclick = () => editGeraet(D.geraete.find(g => g.id == r.dataset.m75g)));
  }

  // ------------------------------------------------------------------ dialogs
  async function editPl(p){
    if (!D) await load();
    const n = !p; p = p || {customer_id: ST.cid && ST.cid !== "0" ? +ST.cid : 0, aktiv:1};
    const html = `<div class="fr"><div class="row"><label class="f" style="flex:.6">Inventar-Nr.<input class="in" id="m75i1" value="${esc(p.inventar_nr || "")}" placeholder="z. B. K-0012"></label><label class="f">Bezeichnung<input class="in" id="m75i2" value="${esc(p.bezeichnung || "")}" placeholder="z. B. Endstufe, Kabeltrommel 25 m, Traverse 2 m"></label></div>
      <div class="row"><label class="f">Hersteller<input class="in" id="m75i3" value="${esc(p.hersteller || "")}"></label><label class="f">Typ<input class="in" id="m75i4" value="${esc(p.typ || "")}"></label><label class="f">Seriennr.<input class="in" id="m75i5" value="${esc(p.seriennr || "")}"></label></div>
      <div class="row"><label class="f">Kunde<select class="in" id="m75i6">${cOpts(p.customer_id || 0)}</select></label><label class="f">Standort<input class="in" id="m75i7" value="${esc(p.standort || "")}" placeholder="z. B. Saal 1, Lager"></label></div>
      <div class="row"><label class="f">Prüfart<select class="in" id="m75i8">${aOpts(p.art_id)}</select></label><label class="f" style="flex:.5">Eigenes Intervall (Monate, 0 = wie Prüfart)<input class="in num" id="m75i9" value="${p.intervall || 0}"></label></div>
      <label class="f">Notiz<input class="in" id="m75i10" value="${esc(p.notiz || "")}"></label>
      ${n ? "" : `<label class="chk"><input type="checkbox" id="m75i11" ${p.aktiv ? "checked" : ""}> aktiv (aus = ausgemustert)</label>`}</div>`;
    const btns = [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      const r = await api("/api/m75/pruefling/save", {id:p.id || null, inventar_nr:$("#m75i1", mb).value, bezeichnung:$("#m75i2", mb).value, hersteller:$("#m75i3", mb).value, typ:$("#m75i4", mb).value,
        seriennr:$("#m75i5", mb).value, customer_id:$("#m75i6", mb).value, standort:$("#m75i7", mb).value, art_id:$("#m75i8", mb).value, intervall:$("#m75i9", mb).value,
        notiz:$("#m75i10", mb).value, asset_id:p.asset_id || null, aktiv: n ? 1 : ($("#m75i11", mb).checked ? 1 : 0)});
      if (!r || !r.ok) return false; p.id = r.id; p.art_id = +$("#m75i8", mb).value || p.art_id; }}];
    if (!n) btns.unshift({label:"Löschen", cls:"danger", value:"del"}, {label:"Prüfen", value:"pruef"});
    const v = await modal(n ? "Neuer Prüfling" : "Prüfling " + (p.inventar_nr || p.bezeichnung), html, btns, true);
    if (v === "del") { await api("/api/m75/delete", {kind:"pruefling", ids:[p.id]}); toast("Prüfling gelöscht"); }
    if (v === "pruef") { editPr({pruefling_id:p.id, art_id:p.art_id}); return; }
    if (v) { await reload(); if (view === "m75") m75View(); }
    if (v === "ok" && n) editPr({pruefling_id:p.id, art_id:p.art_id});
  }

  function feldHtml(f, v){
    const lim = [f.min != null ? "≥ " + nde(f.min, 2) : "", f.max != null ? "≤ " + nde(f.max, 2) : ""].filter(Boolean).join(" ");
    if (f.typ === "check") {
      const s = v === 1 || v === "1" ? "1" : v === 0 || v === "0" ? "0" : "";
      return `<div class="row" style="align-items:center;margin-bottom:4px"><div style="flex:1">${esc(f.label)}${f.hinweis ? `<div class="small muted">${esc(f.hinweis)}</div>` : ""}</div>
        <div class="seg" style="flex:none" data-m75chk="${f.key}">${[["1", "i. O."], ["0", "n. i. O."], ["", "–"]].map(([k, l]) => `<button type="button" class="${s === k ? "on" : ""}" data-v="${k}">${l}</button>`).join("")}</div></div>`;
    }
    if (f.typ === "num") return `<div class="row" style="align-items:center;margin-bottom:4px"><div style="flex:1">${esc(f.label)}<div class="small muted">${esc(f.hinweis || lim)}</div></div>
      <input class="in num" style="width:110px;flex:none" data-m75num="${f.key}" value="${v === "" || v == null ? "" : nde(v, 2)}"><span class="small" style="width:34px;flex:none">${esc(f.einheit || "")}</span></div>`;
    return `<label class="f">${esc(f.label)}<input class="in" data-m75txt="${f.key}" value="${esc(v ?? "")}"></label>`;
  }

  function readWerte(mb){
    const w = {};
    $$("[data-m75chk]", mb).forEach(s => { const b = $("button.on", s); w[s.dataset.m75chk] = b ? b.dataset.v : ""; });
    $$("[data-m75num]", mb).forEach(i => { w[i.dataset.m75num] = i.value.trim() === "" ? "" : pnum(i.value); });
    $$("[data-m75txt]", mb).forEach(i => { w[i.dataset.m75txt] = i.value; });
    return w;
  }

  async function editPr(p){
    if (!D) await load();
    const n = !p.id;
    const plist = D.prueflinge.filter(x_ => x_.aktiv || x_.id == p.pruefling_id);
    if (!plist.length) { toast("Zuerst einen Prüfling anlegen.", true); return editPl(null); }
    const w0 = p.werte || {};
    const html = `<div class="fr"><div class="row"><label class="f">Prüfling<select class="in" id="m75e1">${plist.map(x_ => `<option value="${x_.id}" ${x_.id == p.pruefling_id ? "selected" : ""}>${esc((x_.inventar_nr ? x_.inventar_nr + " · " : "") + (x_.bezeichnung || "") + " (" + x_.kunde + ")")}</option>`).join("")}</select></label>
        <label class="f">Prüfart<select class="in" id="m75e2">${aOpts(p.art_id)}</select></label></div>
      <div class="row"><label class="f" style="flex:.6">Datum<input type="date" class="in" id="m75e3" value="${p.datum || todayIso()}"></label><label class="f">Prüfer<input class="in" id="m75e4" value="${esc(p.pruefer || D.cfg.pruefer || "")}"></label>
        <label class="f">Prüfgerät<select class="in" id="m75e5">${gOpts(p.geraet_id || (D.geraete.find(g => g.aktiv) || {}).id)}</select></label></div>
      <div class="card" style="padding:10px 12px;margin:6px 0 10px"><div class="small muted" style="margin-bottom:6px">Messwerte und Prüfpunkte</div><div id="m75fe"></div></div>
      <div class="row" style="align-items:center"><div class="f" style="flex:1">Automatische Bewertung<div id="m75auto" class="small" style="margin-top:4px">–</div></div>
        <label class="f">Ergebnis<select class="in" id="m75e6"><option value="">automatisch</option>${Object.entries(D.ergebnis).map(([k, l]) => `<option value="${k}" ${p.ergebnis === k && p.ergebnis !== p.auto ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label></div>
      <label class="f">Mängel / Bemerkung<textarea class="in" id="m75e7" rows="2">${esc(p.maengel || "")}</textarea></label>
      <div class="row"><label class="f">Plakette-Nr. (leer = nächste: ${esc(D.cfg.plakette_next)})<input class="in" id="m75e8" value="${esc(p.plakette || "")}"></label><label class="f">Nächste Prüfung (leer = nach Intervall)<input type="date" class="in" id="m75e9" value="${p.naechste || ""}"></label></div></div>`;
    let evalT = null;
    const drawFelder = mb => {
      const a = D.arten.find(a_ => a_.id == $("#m75e2", mb).value);
      $("#m75fe", mb).innerHTML = a ? a.felder.map(f => feldHtml(f, w0[f.key])).join("") + (a.norm ? `<div class="small muted" style="margin-top:6px">${esc(a.norm)}</div>` : "") : `<div class="small muted">Bitte Prüfart wählen.</div>`;
      $$("[data-m75chk] button", mb).forEach(b => b.onclick = () => { $$("button", b.parentElement).forEach(x_ => x_.classList.toggle("on", x_ === b)); doEval(mb); });
      $$("[data-m75num]", mb).forEach(i => i.oninput = () => doEval(mb));
      doEval(mb);
    };
    const doEval = mb => { clearTimeout(evalT); evalT = setTimeout(async () => {
      const aid = $("#m75e2", mb).value; if (!aid) return;
      const r = await api("/api/m75/eval", {art_id:aid, werte:readWerte(mb)}, {quiet:true}); const o = $("#m75auto", mb); if (!r || !r.ok || !o) return;
      o.innerHTML = (r.fehlt.length && r.ergebnis === "bestanden" ? `<span class="badge"><span class="dot"></span>unvollständig</span>` : erB(r.ergebnis)) + (r.fehler.length ? `<div style="color:var(--bad);margin-top:3px">${r.fehler.map(esc).join("<br>")}</div>` : "") + (r.fehlt.length ? `<div class="muted" style="margin-top:3px">Noch offen: ${r.fehlt.map(esc).join(", ")}</div>` : "");
    }, 200); };
    const btns = [{label:"Abbrechen"}, {label:"Speichern", value:"ok", onClick: m => doSave(m)}, {label:"Speichern & PDF", cls:"pri", value:"pdf", onClick: m => doSave(m)}];
    if (!n) btns.unshift({label:"Löschen", cls:"danger", value:"del"});
    let savedId = p.id || null;
    async function doSave(mb){
      const r = await api("/api/m75/pruefung/save", {id:p.id || null, pruefling_id:$("#m75e1", mb).value, art_id:$("#m75e2", mb).value, datum:$("#m75e3", mb).value, pruefer:$("#m75e4", mb).value,
        geraet_id:$("#m75e5", mb).value, werte:readWerte(mb), ergebnis:$("#m75e6", mb).value, maengel:$("#m75e7", mb).value, plakette:$("#m75e8", mb).value, naechste:$("#m75e9", mb).value});
      if (!r || !r.ok) return false;
      savedId = r.id;
      toast(`Prüfung gespeichert: ${D.ergebnis[r.ergebnis] || r.ergebnis}${r.plakette ? " · Plakette " + r.plakette : ""}${r.naechste ? " · nächste " + dde(r.naechste) : ""}`);
    }
    const v = await modal(n ? "Prüfung erfassen" : "Prüfung vom " + dde(p.datum), html, btns, true, mb => {
      $("#m75e1", mb).onchange = () => { const pl = D.prueflinge.find(x_ => x_.id == $("#m75e1", mb).value); if (pl && pl.art_id) { $("#m75e2", mb).value = pl.art_id; drawFelder(mb); } };
      $("#m75e2", mb).onchange = () => drawFelder(mb);
      if (!$("#m75e2", mb).value) { const pl = D.prueflinge.find(x_ => x_.id == $("#m75e1", mb).value); if (pl && pl.art_id) $("#m75e2", mb).value = pl.art_id; }
      drawFelder(mb);
    });
    if (v === "del") { await api("/api/m75/delete", {kind:"pruefung", ids:[p.id]}); toast("Prüfung gelöscht"); }
    if (v === "pdf" && savedId) await pdf([savedId]);
    if (v) { await reload(); if (view === "m75") m75View(); }
  }

  async function editArt(a){
    const n = !a; a = a || {name:"", norm:"", intervall:12, felder:[{label:"Sichtprüfung in Ordnung", typ:"check"}], aktiv:1, preis:0};
    let F = JSON.parse(JSON.stringify(a.felder || []));
    const row = (f, i) => `<tr><td><input class="in" data-k="label" data-i="${i}" value="${esc(f.label || "")}"></td>
      <td><select class="in" data-k="typ" data-i="${i}">${[["check", "i. O. / n. i. O."], ["num", "Messwert"], ["text", "Text"]].map(([k, l]) => `<option value="${k}" ${f.typ === k ? "selected" : ""}>${l}</option>`).join("")}</select></td>
      <td><input class="in" data-k="einheit" data-i="${i}" value="${esc(f.einheit || "")}" style="width:60px"></td><td><input class="in num" data-k="min" data-i="${i}" value="${f.min == null ? "" : nde(f.min, 2)}" style="width:70px"></td>
      <td><input class="in num" data-k="max" data-i="${i}" value="${f.max == null ? "" : nde(f.max, 2)}" style="width:70px"></td><td><input class="in" data-k="hinweis" data-i="${i}" value="${esc(f.hinweis || "")}"></td>
      <td><button type="button" class="btn sm ghost" data-del="${i}" title="Feld entfernen">✕</button></td></tr>`;
    const html = `<div class="fr"><div class="row"><label class="f">Name<input class="in" id="m75a1" value="${esc(a.name)}" placeholder="z. B. Bühnenpodest, Feuerlöscher"></label><label class="f">Norm / Grundlage<input class="in" id="m75a2" value="${esc(a.norm || "")}"></label></div>
      <div class="row"><label class="f" style="flex:.4">Intervall (Monate)<input class="in num" id="m75a3" value="${a.intervall}"></label><label class="f" style="flex:.4">Preis je Prüfling €<input class="in num" id="m75a4" value="${nde((D.cfg.preis_art || {})[a.id] || a.preis || 0)}"></label>
        ${n ? "" : `<label class="chk" style="flex:none;align-self:flex-end;margin-bottom:8px"><input type="checkbox" id="m75a5" ${a.aktiv ? "checked" : ""}> aktiv</label>`}</div>
      <div class="small muted" style="margin:6px 0 4px">Prüffelder (Messwert: Grenze min/max → automatische Bewertung)</div>
      <table class="t"><thead><tr><th>Feld</th><th>Typ</th><th>Einheit</th><th>min</th><th>max</th><th>Hinweis / Grenzwert-Text</th><th></th></tr></thead><tbody id="m75ft"></tbody></table>
      <button type="button" class="btn sm" id="m75fadd" style="margin-top:6px">${ic("plus")} Feld</button></div>`;
    const sync = mb => { $$("[data-k]", mb).forEach(i => { const f = F[+i.dataset.i]; if (!f) return; const k = i.dataset.k; f[k] = (k === "min" || k === "max") ? (i.value.trim() === "" ? null : pnum(i.value)) : i.value; }); };
    const draw = mb => { $("#m75ft", mb).innerHTML = F.map(row).join("");
      $$("[data-del]", mb).forEach(b => b.onclick = () => { sync(mb); F.splice(+b.dataset.del, 1); draw(mb); }); };
    const btns = [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      sync(mb);
      const r = await api("/api/m75/art/save", {id:a.id || null, name:$("#m75a1", mb).value, norm:$("#m75a2", mb).value, intervall:$("#m75a3", mb).value, felder:F, preis:pnum($("#m75a4", mb).value),
        aktiv: n ? 1 : ($("#m75a5", mb).checked ? 1 : 0)});
      if (!r || !r.ok) return false;
      const pa = Object.assign({}, D.cfg.preis_art || {}); pa[r.id] = pnum($("#m75a4", mb).value);
      await api("/api/m75/cfg", {preis_art: pa}, {quiet:true}); }}];
    if (!n) btns.unshift({label: a.eigen ? "Löschen" : "Ausblenden", cls:"danger", value:"del"});
    const v = await modal(n ? "Eigene Prüfart" : "Prüfart " + a.name, html, btns, true, mb => { draw(mb); $("#m75fadd", mb).onclick = () => { sync(mb); F.push({label:"", typ:"check"}); draw(mb); }; });
    if (v === "del") { const r = await api("/api/m75/delete", {kind:"art", ids:[a.id]}); toast((r && r.hinweis) || "Prüfart gelöscht"); }
    if (v) m75View();
  }

  async function editGeraet(g){
    const n = !g; g = g || {kalibrier_monate: D.cfg.kalib_monate || 12, aktiv:1};
    const html = `<div class="fr"><label class="f">Name<input class="in" id="m75g1" value="${esc(g.name || "")}" placeholder="z. B. Gerätetester"></label>
      <div class="row"><label class="f">Hersteller<input class="in" id="m75g2" value="${esc(g.hersteller || "")}"></label><label class="f">Typ<input class="in" id="m75g3" value="${esc(g.typ || "")}"></label><label class="f">Seriennr.<input class="in" id="m75g4" value="${esc(g.seriennr || "")}"></label></div>
      <div class="row"><label class="f">Kalibriert am<input type="date" class="in" id="m75g5" value="${g.kalibriert_am || ""}"></label><label class="f">Kalibrier-Intervall (Monate)<input class="in num" id="m75g6" value="${g.kalibrier_monate || 12}"></label>
        ${n ? "" : `<label class="chk" style="flex:none;align-self:flex-end;margin-bottom:8px"><input type="checkbox" id="m75g8" ${g.aktiv ? "checked" : ""}> aktiv</label>`}</div>
      <label class="f">Notiz<input class="in" id="m75g7" value="${esc(g.notiz || "")}"></label></div>`;
    const btns = [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      const r = await api("/api/m75/geraet/save", {id:g.id || null, name:$("#m75g1", mb).value, hersteller:$("#m75g2", mb).value, typ:$("#m75g3", mb).value, seriennr:$("#m75g4", mb).value,
        kalibriert_am:$("#m75g5", mb).value, kalibrier_monate:$("#m75g6", mb).value, notiz:$("#m75g7", mb).value, aktiv: n ? 1 : ($("#m75g8", mb).checked ? 1 : 0)});
      return !!(r && r.ok); }}];
    if (!n) btns.unshift({label:"Löschen", cls:"danger", value:"del"});
    const v = await modal(n ? "Neues Prüfgerät" : "Prüfgerät " + g.name, html, btns);
    if (v === "del") { await api("/api/m75/delete", {kind:"geraet", ids:[g.id]}); toast("Prüfgerät gelöscht"); }
    if (v) { await reload(); m75View(); }
  }

  async function fromInventory(){
    const html = `<div class="fr"><div class="small muted" style="margin-bottom:6px">Geräte aus „Anlagen & Inventar“ als Prüflinge (eigenes Inventar) übernehmen. Bereits übernommene werden übersprungen.</div>
      <label class="f">Prüfart für alle<select class="in" id="m75ia">${aOpts("")}</select></label>
      <div style="max-height:320px;overflow:auto">${D.assets.map(a => `<label class="chk" style="display:flex;margin:3px 0"><input type="checkbox" value="${a.id}" checked> ${esc(a.bezeichnung)} <span class="small muted">${esc([a.kategorie, a.seriennr, a.standort].filter(Boolean).join(" · "))}</span></label>`).join("")}</div></div>`;
    await modal("Aus Anlagen & Inventar übernehmen", html, [{label:"Abbrechen"}, {label:"Übernehmen", cls:"pri", onClick: async mb => {
      const ids = $$("input[type=checkbox]:checked", mb).map(i => +i.value);
      const r = await api("/api/m75/inventar", {ids, art_id:$("#m75ia", mb).value || null}); if (!r || !r.ok) return false; toast(r.n + " Prüfling(e) übernommen"); }}]);
    await reload(); m75View();
  }

  async function settings(){
    const c = D.cfg;
    await modal("Prüfungen – Einstellungen", `<div class="fr">
      <div class="row"><label class="f">Prüfer (Name im Protokoll)<input class="in" id="m75c1" value="${esc(c.pruefer || "")}"></label><label class="f">Nächste Plakette-Nr.<input class="in" id="m75c2" value="${esc(c.plakette_next || "")}"></label></div>
      <div class="row"><label class="f">Vorwarnzeit (Tage)<input class="in num" id="m75c3" value="${c.warn_tage}"></label><label class="f">Kalibrier-Intervall Standard (Monate)<input class="in num" id="m75c4" value="${c.kalib_monate}"></label></div>
      <div class="row"><label class="f">Baustein für die Abrechnung<select class="in" id="m75c5"><option value="">– Preis aus Prüfart / unten –</option>${S.articles.map(a => `<option value="${a.id}" ${a.id == c.artikel_id ? "selected" : ""}>${esc((a.nr ? a.nr + " " : "") + a.name)} (${eur(a.price)})</option>`).join("")}</select></label>
        <label class="f" style="flex:.5">Standardpreis je Prüfling €<input class="in num" id="m75c6" value="${nde(c.preis_je || 0)}"></label></div>
      <div class="small muted">Preis-Reihenfolge beim Abrechnen: Preis der Prüfart → Baustein → Standardpreis.</div></div>`,
      [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
        const r = await api("/api/m75/cfg", {pruefer:$("#m75c1", mb).value, plakette_next:$("#m75c2", mb).value, warn_tage:$("#m75c3", mb).value, kalib_monate:$("#m75c4", mb).value,
          artikel_id:$("#m75c5", mb).value, preis_je:pnum($("#m75c6", mb).value)});
        if (!r || !r.ok) return false; toast("Gespeichert"); }}]);
    await reload(); m75View();
  }

  async function pdf(ids){ const r = await api("/api/m75/pdf", {ids}); if (r && r.ok) toast("Protokoll erstellt: " + String(r.path || "").split(/[\\/]/).pop()); }

  async function sammel(cid){
    await modal("Sammelprotokoll", `<div class="fr"><div class="row"><label class="f">von<input type="date" class="in" id="m75s1" value="${thisYear}-01-01"></label><label class="f">bis<input type="date" class="in" id="m75s2" value="${todayIso()}"></label></div>
      <label class="chk"><input type="checkbox" id="m75s3" checked> Einzelprotokolle anhängen</label></div>`,
      [{label:"Abbrechen"}, {label:"PDF erstellen", cls:"pri", onClick: async mb => {
        const r = await api("/api/m75/sammel", {customer_id:cid, von:$("#m75s1", mb).value, bis:$("#m75s2", mb).value, einzel:$("#m75s3", mb).checked});
        if (!r || !r.ok) return false; toast("Sammelprotokoll erstellt"); }}]);
  }

  // ------------------------------------------------------------------ customer page card
  EXT.after.push(async n => {
    if (n !== "vCustomers") return;
    let cid = null; try { cid = custSel; } catch (e) {}
    if (!cid) return;
    const col = $("#main .split > div:last-child"); if (!col || $("#m75card", col)) return;
    const r = await api("/api/m75/faellig?customer_id=" + cid, undefined, {quiet:true});
    let cur_ = null; try { cur_ = custSel; } catch (e) {}
    if (!r || !r.ok || cur_ != cid || $("#m75card", col)) return;
    const card = document.createElement("div"); card.className = "card"; card.style.marginTop = "16px"; card.id = "m75card";
    card.innerHTML = `<div class="hd"><h3>Prüfungen${r.faellig.length ? ` <span class="badge warn">${r.faellig.length} fällig</span>` : ""}</h3><div class="act"><button class="btn sm" data-m75go="1">Alle Prüflinge</button><button class="btn sm" data-m75sam="1">${ic("pdf")} Sammelprotokoll</button></div></div>
      ${r.faellig.length ? `<table class="t"><tbody>${r.faellig.slice(0, 8).map(p => `<tr><td><b>${esc(p.inventar_nr || "")}</b> ${esc(p.bezeichnung || "")}</td><td class="num">${dde(p.naechste) || "–"}</td><td>${stB(p.status)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="bd small muted">Keine fälligen Prüfungen.</div>`}`;
    $("[data-m75go]", card).onclick = () => { ST.cid = String(cid); ST.tab = "prueflinge"; save(); go("m75"); };
    $("[data-m75sam]", card).onclick = async () => { if (!D) await load(); sammel(cid); };
    col.appendChild(card);
  });
})();
