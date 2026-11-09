// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m74_anlagenakte: AV-Anlagenakte je Kunde
// Seite "Anlagenakte" (Projekte): Raeume, Geraete, Dateien, Service-Einsaetze, Erinnerungen, Suche,
// Import/Export, PDF-Anlagenbericht. Karte auf der Kunden- und der Projektseite, Hinweis im Dashboard.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m74 = '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><circle cx="7.5" cy="10" r="1.2"/><path d="M11 9h6M11 12h4"/>';
  const ST = (() => { try { return Object.assign({raum:null, tab:"geraete", q:"", rq:""}, JSON.parse(localStorage.getItem("pa_m74") || "{}")); } catch (e) { return {raum:null, tab:"geraete", q:"", rq:""}; } })();
  const save = () => { try { localStorage.setItem("pa_m74", JSON.stringify({raum:ST.raum, tab:ST.tab})); } catch (e) {} };
  const HCOL = {garantie:"warn", wartung:"warn", firmware:""};
  const HLBL = {garantie:"Garantie", wartung:"Wartung", firmware:"Firmware"};
  let L = null;   // list data

  EXT.nav.push({key:"m74", label:"Anlagenakte", icon:"m74", section:"Projekte", cnt: () => (S.m74 && S.m74.hinweise) ? "⚠ " + S.m74.hinweise : ""});
  EXT.views.m74 = m74View;

  EXT.dash.push(el => {
    const m = S.m74; if (!m || !m.hinweise) return;
    const d = document.createElement("div"); d.className = "alert warn"; d.style.marginBottom = "10px";
    d.innerHTML = `${ic("m74")}<b>${m.hinweise} Hinweis(e) in der Anlagenakte</b><span class="small">${m.liste.slice(0, 3).map(h => esc(h.kunde + " · " + h.geraet + ": " + h.text)).join(" · ")}${m.hinweise > 3 ? " …" : ""}</span><span class="sp" style="flex:1"></span><span class="small"><u>Ansehen →</u></span>`;
    d.onclick = () => go("m74", {hinweise:1});
    el.appendChild(d);
  });

  const gName = g => [g.hersteller, g.modell].filter(Boolean).join(" ") || g.kategorie || "Gerät";
  const cOpts = sel => `<option value="">– ohne Kunde –</option>` + S.customers.map(c => `<option value="${c.id}" ${c.id == sel ? "selected" : ""}>${esc(cname(c))} (${esc(c.kdnr)})</option>`).join("");
  const pOpts = sel => `<option value="">– kein Projekt –</option>` + S.projects.map(p => `<option value="${p.id}" ${p.id == sel ? "selected" : ""}>${esc(p.nr + " " + p.name)}</option>`).join("");
  const rOpts = (sel, list) => (list || (L && L.raeume) || []).map(r => `<option value="${r.id}" ${r.id == sel ? "selected" : ""}>${esc((r.kunde ? r.kunde + " · " : "") + r.titel)}</option>`).join("");
  const hBadges = hs => (hs || []).map(h => `<span class="badge ${HCOL[h.art] || ""}" title="${esc(h.text)}"><span class="dot"></span>${HLBL[h.art]}</span>`).join(" ");

  // ------------------------------------------------------------------ main page
  async function m74View(arg){
    if (arg && arg.raum) { ST.raum = +arg.raum; ST.q = ""; }
    if (arg && arg.tab) ST.tab = arg.tab;
    L = await api("/api/m74/list");
    if (!L || !L.raeume) return;
    if (arg && arg.neu) { setTimeout(() => editRaum(Object.assign({}, arg.neu)), 50); }
    if (ST.raum && !L.raeume.some(r => r.id == ST.raum)) ST.raum = null;
    if (!ST.raum && L.raeume.length) ST.raum = L.raeume[0].id;
    const rq = ST.rq.toLowerCase();
    const rl = L.raeume.filter(r => !rq || (r.kunde + " " + r.titel + " " + (r.projekt || "") + " " + (r.adresse || "")).toLowerCase().includes(rq));
    const nG = L.raeume.reduce((a, r) => a + r.n_geraete, 0), nS = L.raeume.reduce((a, r) => a + r.n_service_offen, 0);
    const showH = arg && arg.hinweise;
    let lastK = null;
    $("#main").innerHTML = `<div class="page">${pageHead("Anlagenakte", "Räume, Geräte, Programme und Service je Kunde – mit Erinnerungen für Garantie, Wartung und Firmware",
        expButtons("m74_anlagen", {}) + `<button class="btn" id="m74cfg">${ic("set")} Einstellungen</button><button class="btn pri" id="m74new">${ic("plus")} Neuer Raum</button>`)}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Räume</div><div class="v">${L.raeume.length}</div><div class="s">${new Set(L.raeume.map(r => r.customer_id)).size} Kunde(n)</div></div>
        <div class="card kpi"><div class="l">Geräte</div><div class="v">${nG}</div><div class="s">aktiv</div></div>
        <div class="card kpi click" id="m74kh"><div class="l">Hinweise</div><div class="v" style="color:${L.hinweise.length ? "var(--warn)" : "inherit"}">${L.hinweise.length}</div><div class="s">Garantie · Wartung · Firmware</div></div>
        <div class="card kpi"><div class="l">Service offen</div><div class="v">${nS}</div><div class="s">noch nicht abgerechnet</div></div></div>
      <div class="row" style="margin-bottom:14px;align-items:center">
        <div class="search" style="max-width:460px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="m74q" placeholder="Alle Geräte durchsuchen: IP, Seriennr., MAC, Modell, Firmware …" value="${esc(ST.q)}"></div></div>
      <div id="m74hin"></div><div id="m74res"></div>
      <div class="split" id="m74split">
        <div class="card" style="overflow:hidden"><div class="bd" style="padding:10px"><div class="search"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="m74rq" placeholder="Räume filtern …" value="${esc(ST.rq)}"></div></div>
          <div class="list scroll" style="max-height:calc(100vh - 330px)">${rl.map(r => { const k = r.kunde || "ohne Kunde"; const head = k !== lastK ? `<div class="small muted" style="padding:8px 12px 2px;font-weight:600">${esc(k)}</div>` : ""; lastK = k;
            return head + `<div class="it ${r.id == ST.raum ? "on" : ""}" data-m74r="${r.id}"><div style="min-width:0;flex:1"><b>${esc(r.titel)}</b><div class="small muted">${r.n_geraete} Geräte · ${r.n_dateien} Dateien${r.n_service ? " · " + r.n_service + " Einsätze" : ""}</div></div>${r.n_hinweise ? `<span class="badge warn">⚠ ${r.n_hinweise}</span>` : ""}</div>`; }).join("")
            || `<div class="empty">${L.raeume.length ? "Kein Raum passt zum Filter." : "Noch keine Räume. Mit „Neuer Raum“ anlegen."}</div>`}</div></div>
        <div id="m74det"></div></div></div>`;
    bindCommon();
    $("#m74new").onclick = () => editRaum({});
    $("#m74cfg").onclick = settings;
    $("#m74kh").onclick = () => drawHinweise(true);
    $$("[data-m74r]").forEach(e => e.onclick = () => { ST.raum = +e.dataset.m74r; save(); m74View(); });
    let t1 = null, t2 = null;
    $("#m74rq").oninput = e => { ST.rq = e.target.value; clearTimeout(t1); t1 = setTimeout(() => m74View().then(() => { const n = $("#m74rq"); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }), 220); };
    $("#m74q").oninput = e => { ST.q = e.target.value; clearTimeout(t2); t2 = setTimeout(search, 220); };
    selectify({kind:"m74raum", rows:"[data-m74r]", id:"data-m74r", rerender:() => m74View(), actions:[
      {label:"Anlagenbericht PDF", run: async ids => { await bericht(ids); return false; }},
      {label:"Löschen", cls:"danger", run: async ids => { await api("/api/m74/raum/delete", {ids}); toast(ids.length + " Raum/Räume gelöscht (Dateien im Papierkorb)"); await reload(); m74View(); }}]});
    if (showH) drawHinweise(true); else drawHinweise(false);
    if (ST.q) search();
    if (ST.raum) detail(ST.raum); else $("#m74det").innerHTML = `<div class="card empty">Raum links wählen oder neu anlegen.</div>`;
  }

  function drawHinweise(open){
    const el = $("#m74hin"); if (!el || !L) return;
    const hs = L.hinweise;
    if (!hs.length) { el.innerHTML = ""; return; }
    el.innerHTML = `<div class="card" style="margin-bottom:14px;overflow:hidden"><div class="hd"><h3>Hinweise (${hs.length})</h3><div class="act"><button class="btn sm ghost" id="m74ht">${open ? "Einklappen" : "Alle zeigen"}</button></div></div>
      ${open ? `<table class="t"><thead><tr><th>Fällig</th><th>Art</th><th>Kunde</th><th>Raum</th><th>Gerät</th><th>Hinweis</th><th></th></tr></thead><tbody>${hs.map(h => `<tr data-m74hg="${h.geraet_id}" data-m74hr="${h.raum_id}">
        <td class="num">${dde(h.faellig)}</td><td><span class="badge ${HCOL[h.art] || ""}">${HLBL[h.art]}</span></td><td>${esc(h.kunde)}</td><td>${esc(h.raum)}</td><td>${esc(h.geraet)}${h.seriennr ? `<div class="small muted">SN ${esc(h.seriennr)}</div>` : ""}</td><td class="small">${esc(h.text)}</td>
        <td class="r" style="white-space:nowrap"><button class="btn sm" data-m74hok="${h.art}" data-g="${h.geraet_id}">${h.art === "firmware" ? "Geprüft" : h.art === "wartung" ? "Erledigt" : "Öffnen"}</button></td></tr>`).join("")}</tbody></table>`
      : `<div class="bd small">${hs.slice(0, 4).map(h => `<span class="badge ${HCOL[h.art] || ""}" style="margin:2px">${HLBL[h.art]}: ${esc(h.kunde ? h.kunde + " · " : "")}${esc(h.geraet)} – ${esc(h.text)}</span>`).join("")}${hs.length > 4 ? " …" : ""}</div>`}</div>`;
    $("#m74ht").onclick = () => drawHinweise(!open);
    $$("[data-m74hg]", el).forEach(r => r.onclick = () => { ST.raum = +r.dataset.m74hr; ST.tab = "geraete"; save(); m74View(); });
    $$("[data-m74hok]", el).forEach(b => b.onclick = async e => { e.stopPropagation(); const a = b.dataset.m74hok, g = +b.dataset.g;
      if (a === "garantie") { const h = hs.find(x_ => x_.geraet_id == g); ST.raum = h.raum_id; save(); return m74View(); }
      await api("/api/m74/geraet/bulk", {ids:[g], action: a === "firmware" ? "fw_ok" : "wartung_ok"}); toast(a === "firmware" ? "Firmware als geprüft vermerkt" : "Wartung als erledigt vermerkt");
      await reload(); m74View({hinweise:1}); });
  }

  async function search(){
    const el = $("#m74res"); if (!el) return;
    const qv = ST.q.trim();
    if (qv.length < 2) { el.innerHTML = ""; $("#m74split").style.display = ""; return; }
    const r = await api("/api/m74/suche?q=" + encodeURIComponent(qv), undefined, {quiet:true});
    if (!r || !r.treffer || $("#m74q").value.trim() !== qv) return;
    $("#m74split").style.display = "none";
    el.innerHTML = `<div class="card" style="overflow:hidden;margin-bottom:14px"><div class="hd"><h3>${r.treffer.length} Treffer für „${esc(qv)}“</h3><div class="act"><button class="btn sm ghost" id="m74qx">Suche leeren</button></div></div>
      <table class="t"><thead><tr><th>Kunde</th><th>Raum</th><th>Kategorie</th><th>Gerät</th><th>Seriennr.</th><th>Firmware</th><th>IP</th><th>MAC</th><th>Standort</th></tr></thead><tbody>${r.treffer.map(g => `<tr class="click" data-m74sg="${g.id}" data-r="${g.raum_id}">
        <td>${esc(g.kunde)}</td><td>${esc(g.raum_titel)}</td><td class="small">${esc(g.kategorie || "")}</td><td><b>${esc(gName(g))}</b></td><td class="small">${esc(g.seriennr || "")}</td><td class="small">${esc(g.firmware || "")}</td>
        <td class="num">${esc(g.ip || "")}</td><td class="num small">${esc(g.mac || "")}</td><td class="small">${esc(g.standort || "")}</td></tr>`).join("") || `<tr><td colspan="9" class="empty">Nichts gefunden.</td></tr>`}</tbody></table></div>`;
    $("#m74qx").onclick = () => { ST.q = ""; $("#m74q").value = ""; search(); };
    $$("[data-m74sg]", el).forEach(t => t.onclick = () => { ST.raum = +t.dataset.r; ST.q = ""; ST.tab = "geraete"; save(); m74View().then(() => editGeraetById(+t.dataset.m74sg)); });
  }

  // ------------------------------------------------------------------ room detail
  async function detail(rid){
    const host = $("#m74det"); if (!host) return;
    const D = await api("/api/m74/raum?id=" + rid, undefined, {quiet:true});
    if (!D || !D.raum) { host.innerHTML = `<div class="card empty">Raum nicht gefunden.</div>`; return; }
    const r = D.raum;
    const openS = D.service.filter(s => !s.inv_nr);
    host.innerHTML = `<div class="card" style="margin-bottom:14px"><div class="hd"><div><h3 style="font-size:18px">${esc(r.titel)}</h3><div class="small muted">${esc(r.kunde || "ohne Kunde")}${r.projekt ? " · Projekt " + esc(r.projekt) : ""}${r.adresse ? " · " + esc(r.adresse) : ""}</div></div>
        <div class="act"><button class="btn sm" id="m74rb">${ic("pdf")} Anlagenbericht</button><button class="btn sm" id="m74re">Bearbeiten</button><button class="btn sm ghost danger" id="m74rd" title="Raum löschen (Dateien in den Papierkorb)">${ic("trash")}</button></div></div>
        ${r.notiz ? `<div class="bd small" style="white-space:pre-line">${esc(r.notiz)}</div>` : ""}</div>
      <div class="tabs">${[["geraete", "Geräte", D.geraete.filter(g => g.aktiv).length], ["dateien", "Dateien", D.dateien.length], ["service", "Service", D.service.length]].map(([k, l, n]) => `<div class="tab ${ST.tab === k ? "on" : ""}" data-m74t="${k}">${l}<span class="cnt">${n}</span></div>`).join("")}</div>
      <div id="m74tab"></div>`;
    $$("[data-m74t]", host).forEach(t => t.onclick = () => { ST.tab = t.dataset.m74t; save(); detail(rid); });
    $("#m74re").onclick = () => editRaum(r);
    $("#m74rb").onclick = () => bericht([r.id]);
    $("#m74rd").onclick = async () => { await api("/api/m74/raum/delete", {id:r.id}); toast("Raum gelöscht (Dateien im Papierkorb)"); ST.raum = null; await reload(); m74View(); };
    const T = $("#m74tab");
    if (ST.tab === "dateien") tabDateien(T, D); else if (ST.tab === "service") tabService(T, D, openS); else tabGeraete(T, D);
  }

  function tabGeraete(T, D){
    const r = D.raum;
    T.innerHTML = `<div class="row" style="margin:10px 0;flex-wrap:wrap;gap:6px"><button class="btn pri sm" id="m74gn">${ic("plus")} Gerät</button><button class="btn sm" id="m74gi">${ic("up")} Import Excel/CSV</button>
        <button class="btn sm ghost" id="m74gv">CSV-Vorlage</button>${expButtons("m74_anlagen", {raum_id:r.id}, true)}</div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Kategorie</th><th>Gerät</th><th>Seriennr.</th><th>Firmware</th><th>IP / VLAN</th><th>MAC</th><th>Standort</th><th>Garantie</th><th>Hinweise</th></tr></thead>
      <tbody>${D.geraete.map(g => `<tr class="click" data-m74g="${g.id}" style="${g.aktiv ? "" : "opacity:.55"}"><td class="small">${esc(g.kategorie || "")}</td><td><b>${esc(gName(g))}</b>${g.notiz ? `<div class="small muted">${esc(g.notiz.slice(0, 80))}</div>` : ""}${g.aktiv ? "" : ` <span class="badge">ausgebaut</span>`}</td>
        <td class="small">${esc(g.seriennr || "")}</td><td class="small">${esc(g.firmware || "")}${g.fw_geprueft ? `<div class="muted">geprüft ${dde(g.fw_geprueft)}</div>` : ""}</td><td class="num">${esc(g.ip || "")}${g.vlan ? `<span class="muted"> / ${esc(g.vlan)}</span>` : ""}</td>
        <td class="num small">${esc(g.mac || "")}</td><td class="small">${esc(g.standort || "")}</td><td class="num small">${g.garantie_bis ? dde(g.garantie_bis) : "–"}</td><td>${hBadges(g.hinweise)}</td></tr>`).join("")
        || `<tr><td colspan="9" class="empty">Noch keine Geräte. „Gerät“ oder „Import Excel/CSV“.</td></tr>`}</tbody></table></div>`;
    $("#m74gn").onclick = () => editGeraet({raum_id:r.id, kategorie:"DSP / Core", aktiv:1}, D);
    $("#m74gv").onclick = () => api("/api/m74/vorlage", {});
    $("#m74gi").onclick = () => pickFiles(".xlsx,.xlsm,.csv,.txt", async files => {
      for (const f of files) { const res = await upload("/api/upload/m74import", f, {"X-Raum": String(r.id)});
        if (res && res.ok) toast(`${res.n} Gerät(e) aus ${f.name} übernommen`); else toast((res && res.error) || "Import fehlgeschlagen", true); }
      await reload(); detail(r.id); }, false);
    $$("[data-m74g]", T).forEach(t => t.onclick = () => editGeraet(D.geraete.find(g => g.id == t.dataset.m74g), D));
    selectify({kind:"m74g", rows:"tr[data-m74g]", id:"data-m74g", root:T, rerender:() => detail(r.id), actions:[
      {label:"Excel", run: async ids => { await doExport("m74_anlagen", "xlsx", {ids}); return false; }},
      {label:"PDF", run: async ids => { await doExport("m74_anlagen", "pdf", {ids}); return false; }},
      {label:"Firmware geprüft", run: async ids => { await api("/api/m74/geraet/bulk", {ids, action:"fw_ok"}); toast("Firmware als geprüft vermerkt"); await reload(); detail(r.id); }},
      {label:"Wartung erledigt", run: async ids => { await api("/api/m74/geraet/bulk", {ids, action:"wartung_ok"}); toast("Wartung vermerkt"); await reload(); detail(r.id); }},
      {label:"Verschieben …", run: async ids => { const v = await askRaum("Geräte verschieben in", r.id); if (!v) return false; await api("/api/m74/geraet/bulk", {ids, action:"move", value:v}); toast("Verschoben"); await reload(); m74View(); }},
      {label:"Kopieren …", run: async ids => { const v = await askRaum("Geräte kopieren nach (ohne Seriennr./IP/MAC)", r.id); if (!v) return false; await api("/api/m74/geraet/bulk", {ids, action:"copy", value:v}); toast("Kopiert"); await reload(); m74View(); }},
      {label:"Löschen", cls:"danger", run: async ids => { await api("/api/m74/geraet/bulk", {ids, action:"delete"}); toast(ids.length + " Gerät(e) gelöscht"); await reload(); detail(r.id); }}]});
  }

  function tabDateien(T, D){
    const r = D.raum;
    const byArt = {}; D.dateien.forEach(f => (byArt[f.art] = byArt[f.art] || []).push(f));
    T.innerHTML = `<div class="row" style="margin:10px 0;flex-wrap:wrap;gap:6px"><button class="btn pri sm" id="m74fa">${ic("up")} Dateien hinzufügen</button><button class="btn sm" id="m74fo">${ic("folder")} Ordner öffnen</button>
        <button class="btn sm ghost" id="m74fs">${ic("sync")} Mit Ordner abgleichen</button></div>
      <div class="drop" id="m74fd" style="border:2px dashed var(--line);border-radius:10px;padding:14px;text-align:center;margin-bottom:10px" class="small muted">Dateien hierher ziehen: Q-SYS-Design, SIMPL-Programm, Pläne, Fotos, Handbücher …</div>
      <div class="alert" style="cursor:default;margin-bottom:10px;font-size:12.5px">${ic("alert")}<span>Passwortlisten nicht im Klartext ablegen – besser im Passwort-Manager oder als verschlüsseltes 7z/ZIP.</span></div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Art</th><th>Datei</th><th>Notiz</th><th class="r">Größe</th><th>Hinzugefügt</th></tr></thead><tbody>${D.dateien.map(f => `<tr class="click" data-m74f="${f.id}">
        <td><span class="badge">${esc(f.art)}</span></td><td><b>${esc(f.name)}</b>${f.fehlt ? ` <span class="badge bad">fehlt</span>` : ""}</td><td class="small">${esc(f.notiz || "")}</td><td class="r num small">${nde((f.size || 0) / 1024, 0)} KB</td><td class="num small">${dde((f.added || "").slice(0, 10))}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">Noch keine Dateien.</td></tr>`}</tbody></table></div>`;
    const add = async files => { let n = 0; for (const f of files) { const res = await upload("/api/upload/m74datei", f, {"X-Raum": String(r.id)});
      if (res && res.ok) { n++; if (res.warn) toast(res.warn, true); } else toast((res && res.error) || (f.name + ": Fehler"), true); }
      toast(n + " Datei(en) abgelegt"); detail(r.id); };
    $("#m74fa").onclick = () => pickFiles("", add);
    $("#m74fo").onclick = () => api("/api/m74/ordner", {raum_id:r.id});
    $("#m74fs").onclick = async () => { const res = await api("/api/m74/datei/sync", {raum_id:r.id}); if (res && res.ok) toast(`${res.neu} neu, ${res.entfernt} entfernt`); detail(r.id); };
    const dz = $("#m74fd");
    dz.ondragover = e => { e.preventDefault(); dz.style.borderColor = "var(--acc)"; };
    dz.ondragleave = () => dz.style.borderColor = "";
    dz.ondrop = e => { e.preventDefault(); dz.style.borderColor = ""; const fs = [...(e.dataTransfer.files || [])]; if (fs.length) add(fs); };
    $$("[data-m74f]", T).forEach(t => t.onclick = () => { const f = D.dateien.find(x_ => x_.id == t.dataset.m74f); if (f) api("/api/open", {path:f.path}); });
    selectify({kind:"m74f", rows:"tr[data-m74f]", id:"data-m74f", root:T, rerender:() => detail(r.id), actions:[
      {label:"Löschen", cls:"danger", run: async ids => { await api("/api/m74/datei/delete", {ids}); toast(ids.length + " Datei(en) in den Papierkorb"); detail(r.id); }}]});
  }

  function tabService(T, D, openS){
    const r = D.raum;
    T.innerHTML = `<div class="row" style="margin:10px 0;flex-wrap:wrap;gap:6px"><button class="btn pri sm" id="m74sn">${ic("plus")} Service-Einsatz</button>
        <button class="btn sm" id="m74sr" ${openS.length ? "" : "disabled"}>${ic("inv")} Servicerechnung (${openS.length} offen)</button></div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Datum</th><th>Gerät</th><th>Tätigkeit</th><th class="r">Std.</th><th class="r">Material</th><th>Rechnung</th></tr></thead><tbody>${D.service.map(s => `<tr class="click" data-m74s="${s.id}">
        <td class="num">${dde(s.datum)}</td><td class="small">${esc(s.geraet || "–")}</td><td style="white-space:pre-line">${esc(s.beschreibung || "")}</td><td class="r num">${nde(s.stunden || 0)}</td>
        <td class="r num small">${s.material.length ? eur(s.material.reduce((a, m) => a + pnum(m.qty) * pnum(m.price), 0)) : "–"}</td>
        <td>${s.inv_nr ? `<span class="badge ${s.inv_status === "entwurf" ? "" : "ok"}" data-m74inv="${s.invoice_id}">${esc(s.inv_nr)}</span>` : `<span class="badge warn">offen</span>`}</td></tr>`).join("")
        || `<tr><td colspan="6" class="empty">Noch keine Service-Einsätze.</td></tr>`}</tbody></table></div>`;
    $("#m74sn").onclick = () => editService({raum_id:r.id, datum:todayIso(), stunden:1, material:[]}, D);
    $("#m74sr").onclick = () => rechnung(openS.map(s => s.id), r.id);
    $$("[data-m74s]", T).forEach(t => t.onclick = () => editService(D.service.find(s => s.id == t.dataset.m74s), D));
    $$("[data-m74inv]", T).forEach(b => b.onclick = e => { e.stopPropagation(); openInvoice(+b.dataset.m74inv); });
    selectify({kind:"m74s", rows:"tr[data-m74s]", id:"data-m74s", root:T, rerender:() => detail(r.id), actions:[
      {label:"Servicerechnung", run: async ids => { await rechnung(ids, r.id); return false; }},
      {label:"Löschen", cls:"danger", run: async ids => { await api("/api/m74/service/delete", {ids}); toast(ids.length + " Einsatz/Einsätze gelöscht"); await reload(); detail(r.id); }}]});
  }

  async function rechnung(ids, rid){
    const res = await api("/api/m74/service/rechnung", {ids});
    if (!res || !res.ok) return;
    toast(`Rechnungsentwurf ${res.nr} aus ${res.n} Einsatz/Einsätzen erstellt`);
    await reload(); openInvoice(res.id);
  }

  async function bericht(ids){
    toast("Anlagenbericht wird erstellt …");
    const res = await api("/api/m74/bericht", {raum_ids:ids.map(Number)});
    if (res && res.ok) toast("Gespeichert: " + res.path.split(/[\\/]/).pop());
  }

  // ------------------------------------------------------------------ dialogs
  async function askRaum(title, notId){
    const list = (L ? L.raeume : []).filter(r => r.id != notId);
    if (!list.length) { toast("Kein anderer Raum vorhanden", true); return null; }
    return askValue(title, `<label class="f">Raum<select class="in" id="m74ar">${rOpts(null, list)}</select></label>`, mb => +$("#m74ar", mb).value || null);
  }

  async function editRaum(r){
    const n = !r.id;
    let id = null;
    await modal(n ? "Neuer Raum / Standort" : "Raum bearbeiten", `<div class="fr">
      <div class="row"><label class="f">Kunde<select class="in" id="m74c">${cOpts(r.customer_id)}</select></label><label class="f">Projekt (optional)<select class="in" id="m74p">${pOpts(r.project_id)}</select></label></div>
      <div class="row"><label class="f">Gebäude / Standort<input class="in" id="m74b" value="${esc(r.gebaeude || "")}" placeholder="z. B. Hauptgebäude, 2. OG"></label><label class="f">Raum<input class="in" id="m74ra" value="${esc(r.raum || "")}" placeholder="z. B. Großer Saal, Konferenz 2.14"></label></div>
      <label class="f">Adresse<input class="in" id="m74ad" value="${esc(r.adresse || "")}" placeholder="falls abweichend von der Kundenadresse"></label>
      <label class="f">Notiz (Zugang, Ansprechpartner, Besonderheiten – keine Passwörter)<textarea class="in" id="m74no" rows="4">${esc(r.notiz || "")}</textarea></label></div>`,
      [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
        const res = await api("/api/m74/raum/save", {id:r.id || null, customer_id:$("#m74c", mb).value, project_id:$("#m74p", mb).value, gebaeude:$("#m74b", mb).value,
          raum:$("#m74ra", mb).value, adresse:$("#m74ad", mb).value, notiz:$("#m74no", mb).value});
        if (!res || !res.ok) return false; id = res.id; }}]);
    if (id) { ST.raum = id; save(); await reload(); if (view === "m74") m74View(); else go("m74", {raum:id}); }
    return id;
  }

  async function editGeraetById(gid){
    if (!ST.raum) return;
    const D = await api("/api/m74/raum?id=" + ST.raum, undefined, {quiet:true});
    const g = D && D.geraete.find(x_ => x_.id == gid); if (g) editGeraet(g, D);
  }

  async function editGeraet(g, D){
    const n = !g.id;
    const lag = (L && L.lager) || [];
    const f = (k, l, ph = "", t = "text") => `<label class="f">${l}<input class="in" type="${t}" id="m74_${k}" value="${esc(g[k] ?? "")}" placeholder="${ph}"></label>`;
    const btns = [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
      const d = {id:g.id || null, raum_id:g.raum_id};
      ["kategorie","hersteller","modell","seriennr","firmware","fw_geprueft","ip","mac","vlan","standort","einbau","garantie_bis","wartung_monate","wartung_letzte","lager_id","notiz"].forEach(k => { const e = $("#m74_" + k, mb); if (e) d[k] = e.value; });
      d.aktiv = $("#m74_aktiv", mb).checked ? 1 : 0;
      const res = await api("/api/m74/geraet/save", d); if (!res || !res.ok) return false; }}];
    if (!n) btns.unshift({label:"Löschen", cls:"danger", value:"del"});
    const v = await modal(n ? "Neues Gerät" : gName(g), `<div class="fr">
      <div class="row"><label class="f">Kategorie<select class="in" id="m74_kategorie">${(L ? L.kategorien : []).map(k => `<option ${k === g.kategorie ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>${f("hersteller", "Hersteller", "z. B. QSC, Crestron, Extron")}${f("modell", "Modell", "z. B. Core 8 Flex")}</div>
      <div class="row">${f("seriennr", "Seriennummer")}${f("firmware", "Firmware", "z. B. 9.13.0")}${f("fw_geprueft", "Firmware geprüft am", "", "date")}</div>
      <div class="row">${f("ip", "IP-Adresse", "192.168.1.10")}${f("mac", "MAC-Adresse", "00:60:74:..")}<div style="flex:.5">${f("vlan", "VLAN")}</div></div>
      <div class="row">${f("standort", "Standort im Raum", "z. B. Technikschrank HE 12, Decke vorne")}${f("einbau", "Einbaudatum", "", "date")}${f("garantie_bis", "Garantie bis", "", "date")}</div>
      <div class="row"><div style="flex:.6">${f("wartung_monate", "Wartung alle … Monate", "0 = keine")}</div>${f("wartung_letzte", "Letzte Wartung", "", "date")}
        <label class="f">Lager-Artikel (optional)<select class="in" id="m74_lager_id"><option value="">– keiner –</option>${lag.map(a => `<option value="${a.id}" ${a.id == g.lager_id ? "selected" : ""}>${esc((a.nr ? a.nr + " " : "") + a.name)}</option>`).join("")}</select></label></div>
      <label class="f">Notiz<textarea class="in" id="m74_notiz" rows="3">${esc(g.notiz || "")}</textarea></label>
      <label class="chk"><input type="checkbox" id="m74_aktiv" ${g.aktiv === 0 ? "" : "checked"}> eingebaut / aktiv (aus = ausgebaut, bleibt in der Historie)</label>
      ${(g.hinweise || []).length ? `<div style="margin-top:8px">${g.hinweise.map(h => `<div class="alert ${HCOL[h.art] || ""}" style="cursor:default;margin-top:4px;font-size:12.5px">${ic("alert")}<span>${esc(h.text)}</span></div>`).join("")}</div>` : ""}</div>`, btns, true);
    if (v === "del") { await api("/api/m74/geraet/bulk", {ids:[g.id], action:"delete"}); toast("Gerät gelöscht"); }
    await reload(); if ($("#m74det")) detail(g.raum_id);
  }

  async function editService(s, D){
    const n = !s.id;
    const mats = (s.material || []).map(m => Object.assign({}, m));
    const lag = (L && L.lager) || [];
    const matRows = () => mats.map((m, i) => `<div class="row" data-mi="${i}" style="align-items:flex-end"><label class="f" style="flex:.6">Menge<input class="in num" data-mk="qty" value="${nde(pnum(m.qty) || 1, 2)}"></label>
      <label class="f" style="flex:2">Material<input class="in" data-mk="name" list="m74ml" value="${esc(m.name || "")}"></label><label class="f" style="flex:.8">Preis €<input class="in num" data-mk="price" value="${nde(pnum(m.price), 2)}"></label>
      <button class="btn sm ghost danger" data-mdel="${i}" type="button" style="margin-bottom:8px">✕</button></div>`).join("");
    const btns = [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
      sync(mb);
      const res = await api("/api/m74/service/save", {id:s.id || null, raum_id:s.raum_id, geraet_id:$("#m74sg", mb).value, datum:$("#m74sd", mb).value,
        beschreibung:$("#m74sb", mb).value, stunden:pnum($("#m74ss", mb).value), material:mats.map(m => ({name:m.name, qty:pnum(m.qty), price:pnum(m.price), nr:m.nr || ""})),
        wartung_erledigt:$("#m74sw", mb).checked});
      if (!res || !res.ok) return false; }}];
    if (!n) btns.unshift({label:"Löschen", cls:"danger", value:"del"});
    const sync = mb => $$("[data-mi]", mb).forEach(rw => { const m = mats[+rw.dataset.mi]; $$("[data-mk]", rw).forEach(e => m[e.dataset.mk] = e.value);
      const a = lag.find(a_ => ((a_.nr ? a_.nr + " " : "") + a_.name) === m.name); if (a) { m.nr = a.nr; if (!pnum(m.price)) m.price = a.ek; } });
    const bindMat = mb => { $$("[data-mdel]", mb).forEach(b => b.onclick = () => { sync(mb); mats.splice(+b.dataset.mdel, 1); $("#m74mr", mb).innerHTML = matRows(); bindMat(mb); }); };
    const v = await modal(n ? "Neuer Service-Einsatz" : "Service-Einsatz " + dde(s.datum), `<div class="fr">
      <div class="row"><label class="f" style="flex:.7">Datum<input type="date" class="in" id="m74sd" value="${esc(s.datum || todayIso())}"></label>
        <label class="f">Gerät (optional)<select class="in" id="m74sg"><option value="">– ganzer Raum –</option>${D.geraete.map(g => `<option value="${g.id}" ${g.id == s.geraet_id ? "selected" : ""}>${esc(gName(g) + (g.seriennr ? " · " + g.seriennr : ""))}</option>`).join("")}</select></label>
        <label class="f" style="flex:.5">Stunden<input class="in num" id="m74ss" value="${nde(s.stunden || 0, 2)}"></label></div>
      <label class="f">Tätigkeit / Beschreibung<textarea class="in" id="m74sb" rows="4" placeholder="z. B. Firmware-Update Core auf 9.13, Mikrofon-Pegel neu eingestellt">${esc(s.beschreibung || "")}</textarea></label>
      <div class="small muted" style="margin:6px 0 2px">Material</div><div id="m74mr">${matRows()}</div><datalist id="m74ml">${lag.map(a => `<option value="${esc((a.nr ? a.nr + " " : "") + a.name)}">`).join("")}</datalist>
      <button class="btn sm" id="m74ma" type="button">${ic("plus")} Material</button>
      <label class="chk" style="margin-top:10px"><input type="checkbox" id="m74sw"> Wartung des Geräts damit erledigt (setzt „Letzte Wartung“)</label>
      ${s.inv_nr ? `<div class="small muted" style="margin-top:6px">Abgerechnet mit ${esc(s.inv_nr)}</div>` : ""}</div>`, btns, true, mb => {
        $("#m74ma", mb).onclick = () => { sync(mb); mats.push({qty:1, name:"", price:0}); $("#m74mr", mb).innerHTML = matRows(); bindMat(mb); };
        bindMat(mb); });
    if (v === "del") { await api("/api/m74/service/delete", {ids:[s.id]}); toast("Einsatz gelöscht"); }
    await reload(); if ($("#m74det")) detail(s.raum_id);
  }

  async function settings(){
    const c = (L && L.cfg) || {};
    await modal("Anlagenakte – Einstellungen", `<div class="fr">
      <div class="row"><label class="f">Firmware-Prüfung erinnern nach … Monaten<input class="in num" id="m74c1" value="${c.fw_monate ?? 12}"></label><label class="f">Vorwarnzeit Garantie/Wartung (Tage)<input class="in num" id="m74c2" value="${c.warn_tage ?? 30}"></label></div>
      <div class="row"><label class="f">Baustein für Service-Stunden<select class="in" id="m74c5"><option value="">– Stundensatz unten verwenden –</option>${S.articles.map(a => `<option value="${a.id}" ${a.id == c.service_artikel ? "selected" : ""}>${esc((a.nr ? a.nr + " " : "") + a.name)} (${eur(a.price)})</option>`).join("")}</select></label>
        <label class="f" style="flex:.6">Stundensatz €<input class="in num" id="m74c3" value="${nde(c.stundensatz || 0)}"></label><label class="f" style="flex:.6">Anfahrtspauschale € (0 = keine)<input class="in num" id="m74c4" value="${nde(c.anfahrt || 0)}"></label></div></div>`,
      [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
        const res = await api("/api/m74/cfg", {fw_monate:$("#m74c1", mb).value, warn_tage:$("#m74c2", mb).value, stundensatz:pnum($("#m74c3", mb).value), anfahrt:pnum($("#m74c4", mb).value), service_artikel:$("#m74c5", mb).value});
        if (!res || !res.ok) return false; toast("Gespeichert"); }}]);
    await reload(); m74View();
  }

  // ------------------------------------------------------------------ customer + project page cards
  function roomCard(list, title, neu, extraBtn){
    const card = document.createElement("div"); card.className = "card"; card.style.marginTop = "16px"; card.id = "m74card";
    card.innerHTML = `<div class="hd"><h3>${title} (${list.length})</h3><div class="act">${extraBtn || ""}<button class="btn sm" data-m74cn="1">${ic("plus")} Raum</button></div></div>
      ${list.length ? `<table class="t"><tbody>${list.map(r => `<tr class="click" data-m74cr="${r.id}"><td><b>${esc(r.titel)}</b>${r.projekt && !neu.project_id ? `<div class="small muted">${esc(r.projekt)}</div>` : ""}</td>
        <td class="small muted">${r.n_geraete} Geräte · ${r.n_dateien} Dateien</td><td class="r">${r.n_hinweise ? `<span class="badge warn">⚠ ${r.n_hinweise}</span>` : ""}${r.n_service_offen ? ` <span class="badge">${r.n_service_offen} Service offen</span>` : ""}</td></tr>`).join("")}</tbody></table>`
        : `<div class="bd small muted">Noch keine Anlagen dokumentiert. Räume mit Geräten, IPs, Seriennummern und Programmen anlegen.</div>`}`;
    $$("[data-m74cr]", card).forEach(t => t.onclick = () => { ST.raum = +t.dataset.m74cr; ST.q = ""; save(); go("m74", {raum:+t.dataset.m74cr}); });
    $("[data-m74cn]", card).onclick = () => go("m74", {neu});
    const b = $("[data-m74rep]", card); if (b) b.onclick = () => bericht(list.map(r => r.id));
    return card;
  }

  EXT.after.push(async (n, arg) => {
    if (n === "vCustomers") {
      let cid = null; try { cid = custSel; } catch (e) {}
      if (!cid) return;
      const col = $("#main .split > div:last-child"); if (!col || $("#m74card", col)) return;
      const r = await api("/api/m74/list?customer_id=" + cid, undefined, {quiet:true});
      if (!r || !r.raeume) return;
      let cur_ = null; try { cur_ = custSel; } catch (e) {}
      if (cur_ != cid || $("#m74card", col)) return;
      col.appendChild(roomCard(r.raeume, "Anlagenakte", {customer_id:cid}, r.raeume.length ? `<button class="btn sm" data-m74rep="1">${ic("pdf")} Bericht</button>` : ""));
    }
    if (n === "vProject") {
      const pid = arg; const page = $("#main .page"); if (!page || !pid || $("#m74card", page)) return;
      const r = await api("/api/m74/list?project_id=" + pid, undefined, {quiet:true});
      if (!r || !r.raeume || $("#m74card", page)) return;
      const p = S.projects.find(p_ => p_.id == pid);
      if (!r.raeume.length && p && !/av|audio/i.test(p.bereich || "")) return;   // only AV projects show an empty card
      page.appendChild(roomCard(r.raeume, "Anlagenakte (Räume dieses Projekts)", {project_id:pid, customer_id:p ? p.customer_id : null},
        r.raeume.length ? `<button class="btn sm" data-m74rep="1">${ic("pdf")} Bericht</button>` : ""));
    }
  });
})();
