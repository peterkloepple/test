// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m76_en1090: EN-1090-/Schweissdokumentation je Projekt
// Reiter "EN 1090" auf der Projektseite (Metallbau/Schweissen oder aktiviert), Seite "EN 1090" (Projekte),
// Einstellungs-Reiter "EN 1090 & Abnahme". Stellt window.m76Tabs bereit (eigene Projekt-Reiter, genutzt von m77/m78).
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m76weld = '<path d="M4 20l6-6M14 4l6 6-8 8-6-6z"/><path d="M15 15l3 3M3 21h6"/>';

  // ---------------------------------------------------------------- project tabs helper (m76/m77/m78)
  const TABS = window.m76Tabs = window.m76Tabs || [];
  EXT.after.push((n, id) => {
    if (n !== "vProject") return;
    const tabs = $("#main .tabs"); if (!tabs || tabs.dataset.m7x) return;
    tabs.dataset.m7x = "1";
    const p = (S.projects || []).find(x => x.id == id) || {id};
    // tab of a module that is hidden for this project -> back to the standard tab
    if (/^m7\d$/.test(pTab) && !TABS.some(t => t.key === pTab && (!t.show || t.show(p)))) { pTab = "files"; vProject(id); return; }
    TABS.forEach(t => {
      if (t.show && !t.show(p)) return;
      const d = document.createElement("div");
      d.className = "tab" + (pTab === t.key ? " on" : "");
      d.innerHTML = esc(t.label) + (t.cnt ? (c => c ? `<span class="cnt">${c}</span>` : "")(t.cnt(p)) : "");
      d.onclick = () => { pTab = t.key; vProject(id); };
      tabs.appendChild(d);
    });
    const t = TABS.find(t => t.key === pTab), T = $("#ptab");
    if (t && T) Promise.resolve().then(() => t.render(T, id, p)).catch(e => { console.error(e); T.innerHTML = `<div class="card empty">Fehler: ${esc(e.message || e)}</div>`; });
  });

  const ST = {ok: ["ok", "gültig"], bald: ["warn", "läuft bald ab"], abgelaufen: ["bad", "abgelaufen"]};
  const stB = (s, txt) => { const b = ST[s] || ["", s]; return `<span class="badge ${b[0]}" title="${esc(txt || "")}"><span class="dot"></span>${esc(txt || b[1])}</span>`; };
  const WST = {fehler: "bad", warnung: "warn", hinweis: ""};
  const isMetal = p => /metall|schwei/i.test(p.bereich || "") || ((S.m76 && S.m76.ids) || []).includes(p.id);

  TABS.push({key: "m76", label: "EN 1090", show: isMetal, render: (T, id) => m76Tab(T, id)});

  EXT.nav.push({key: "m76", label: "EN 1090", icon: "m76weld", section: "Projekte", cnt: () => (S.m76 && S.m76.fehler) ? "⚠ " + S.m76.fehler : ""});
  EXT.views.m76 = m76View;

  // ---------------------------------------------------------------- field definitions
  const F = {
    pos: [["pos", "Pos.", .4], ["bezeichnung", "Bezeichnung"], ["zeichnung", "Zeichnungs-Nr."], ["werkstoff", "Werkstoff", .7, "S235JR,S275JR,S355J2,S355J2H,1.4301,1.4571,EN AW-6060"],
          ["naht", "Naht (z. B. Kehlnaht a4)"], ["pruefung", "Prüfumfang (z. B. VT 100 %)"], ["notiz", "Notiz"]],
    zeugnis: [["werkstoff", "Werkstoff", .7, "S235JR,S275JR,S355J2,S355J2H,1.4301,1.4571"], ["abmessung", "Abmessung (z. B. HEA 200, Fl 40x5)"], ["charge", "Charge"],
              ["schmelze", "Schmelze"], ["lieferant", "Lieferant"], ["lieferschein", "Lieferschein-Nr."], ["typ", "Zeugnis", .4, "3.1,3.2,2.2,2.1"], ["datum", "Datum", .6, "", "date"], ["menge", "Menge"]],
    zusatz: [["bezeichnung", "Zusatzwerkstoff (Handelsname)"], ["norm", "Normbezeichnung (z. B. ISO 14341-A G 42 4 M21 3Si1)"], ["hersteller", "Hersteller"], ["charge", "Charge"], ["durchmesser", "Ø", .4]],
    pruefung: [["datum", "Datum", .6, "", "date"], ["art", "Art", .4, "VT,MT,PT,UT,RT"], ["umfang", "Umfang (z. B. 100 %)"], ["pos", "Position(en)"],
               ["ergebnis", "Ergebnis", .5, "i.O.,n.i.O."], ["pruefer", "Prüfer"], ["bericht", "Bericht-Nr."], ["notiz", "Notiz"]],
  };
  const TITLE = {pos: "Bauteile / Positionen", zeugnis: "Werkstoffzeugnisse (EN 10204)", zusatz: "Zusatzwerkstoffe", pruefung: "Prüfungen"};
  const COLS = {pos: ["pos", "bezeichnung", "zeichnung", "werkstoff", "naht", "pruefung"], zeugnis: ["werkstoff", "abmessung", "charge", "schmelze", "lieferant", "typ", "datum"],
                zusatz: ["bezeichnung", "norm", "hersteller", "charge"], pruefung: ["datum", "art", "umfang", "pos", "ergebnis", "pruefer", "bericht"]};
  const lbl = (art, k) => ((F[art].find(f => f[0] === k) || [k, k])[1]).replace(/ \(.*\)$/, "");

  function fieldHtml(art, a, prefix){
    return `<div class="row" style="flex-wrap:wrap">${F[art].map(([k, l, w, opts, type]) => {
      const v = a[k] || (k === "typ" && art === "zeugnis" ? "3.1" : k === "datum" ? todayIso() : "");
      const dl = opts ? `list="${prefix}${k}l"` : "";
      return `<label class="f" style="flex:${w || 1} 1 ${w ? 120 * w : 180}px">${esc(l)}<input class="in" id="${prefix}${k}" ${type ? `type="${type}"` : ""} ${dl} value="${esc(v)}">${opts ? `<datalist id="${prefix}${k}l">${opts.split(",").map(o => `<option value="${esc(o)}">`).join("")}</datalist>` : ""}</label>`;
    }).join("")}</div>`;
  }

  async function editEntry(pid, art, e, d, after){
    const a = (e && e.data) || {};
    let extra = "";
    if (art === "pos") {
      extra = `<div class="row"><label class="f">WPS<select class="in" id="m76ewps"><option value="">– keine –</option>${(d.wps_alle || []).map(w => `<option value="${w.id}" ${w.id == a.wps_id ? "selected" : ""}>${esc(w.art + " " + w.nr + " · " + (w.verfahren || ""))}</option>`).join("")}</select></label></div>
        <div class="small muted" style="margin:4px 0">Schweißer</div><div class="chips">${(d.sw_alle || []).map(z => `<label class="chip ${(a.schweisser || []).map(String).includes(String(z.id)) ? "on" : ""}"><input type="checkbox" data-m76sw="${z.id}" ${(a.schweisser || []).map(String).includes(String(z.id)) ? "checked" : ""} style="display:none">${esc(z.person || z.nummer || z.bezeichnung)}</label>`).join("") || `<span class="small muted">Keine Schweißer-Nachweise (ISO 9606) unter „Nachweise“ erfasst.</span>`}</div>`;
    }
    const html = `<div class="fr">${fieldHtml(art, a, "m76e")}${extra}</div>`;
    const btns = [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
      const data = {};
      F[art].forEach(([k]) => data[k] = $("#m76e" + k, mb).value.trim());
      if (art === "pos") { data.wps_id = $("#m76ewps", mb).value; data.schweisser = $$("[data-m76sw]", mb).filter(c => c.checked).map(c => +c.dataset.m76sw); }
      const r = await api("/api/m76/entry/save", {project_id: pid, art, id: e ? e.id : null, data});
      if (!r || !r.ok) return false;
      toast("Gespeichert"); after();
    }}];
    if (e) btns.unshift({label: "Löschen", cls: "danger", onClick: async () => { const r = await api("/api/m76/entry/delete", {ids: [e.id]}); if (!r || r.ok === false) return false; toast("Gelöscht"); after(); }});
    await modal((e ? "" : "Neu: ") + TITLE[art].replace(/ \(.*\)$/, ""), html, btns, true, mb => {
      $$("[data-m76sw]", mb).forEach(c => c.closest("label").onclick = ev => { ev.preventDefault(); c.checked = !c.checked; c.closest("label").classList.toggle("on", c.checked); });
    });
  }

  function upFile(art, id, after){
    pickFiles(".pdf,image/*", async files => {
      for (const f of files) { const r = await upload("/api/upload/m76", f, {"X-M76-Art": art, "X-M76-Id": String(id)}); if (!r || !r.ok) toast((r && r.error) || "Upload fehlgeschlagen", true); }
      toast("Datei abgelegt"); after();
    }, false);
  }

  async function editWps(w, pid, after){
    w = w || {art: "WPS", aktiv: 1};
    const vf = (window.M76VF || {});
    const html = `<div class="fr"><div class="row"><label class="f" style="flex:.4">Art<select class="in" id="m76wa"><option ${w.art === "WPS" ? "selected" : ""}>WPS</option><option ${w.art === "WPQR" ? "selected" : ""}>WPQR</option></select></label>
      <label class="f">Nummer<input class="in" id="m76wn" value="${esc(w.nr || "")}"></label>
      <label class="f">Verfahren (ISO 4063)<input class="in" id="m76wv" list="m76wvl" value="${esc(w.verfahren || "")}"><datalist id="m76wvl">${Object.entries(vf).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</datalist></label></div>
      <div class="row"><label class="f">Werkstoffgruppe (ISO/TR 15608)<input class="in" id="m76ww" value="${esc(w.werkstoff || "")}" placeholder="z. B. 1.1 / 1.2"></label>
      <label class="f">Dickenbereich<input class="in" id="m76wd" value="${esc(w.dicke || "")}" placeholder="z. B. 3–30 mm"></label>
      <label class="f">Position<input class="in" id="m76wp" value="${esc(w.position || "")}" placeholder="z. B. PA, PB, PF"></label></div>
      <div class="row"><label class="f">Zusatzwerkstoff<input class="in" id="m76wz" value="${esc(w.zusatz || "")}"></label>
      <label class="f">Norm<input class="in" id="m76wno" value="${esc(w.norm || "")}" placeholder="z. B. ISO 15614-1"></label>
      <label class="f" style="flex:.6">gültig bis<input type="date" class="in" id="m76wg" value="${esc(w.gueltig_bis || "")}"></label></div>
      <label class="f">Notiz<input class="in" id="m76wno2" value="${esc(w.notiz || "")}"></label>
      ${w.id ? `<label class="chk"><input type="checkbox" id="m76wak" ${w.aktiv ? "checked" : ""}> aktiv</label>` : ""}</div>`;
    const btns = [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
      const r = await api("/api/m76/wps/save", {id: w.id || null, project_id: pid || null, art: $("#m76wa", mb).value, nr: $("#m76wn", mb).value, verfahren: $("#m76wv", mb).value,
        werkstoff: $("#m76ww", mb).value, dicke: $("#m76wd", mb).value, position: $("#m76wp", mb).value, zusatz: $("#m76wz", mb).value, norm: $("#m76wno", mb).value,
        gueltig_bis: $("#m76wg", mb).value, notiz: $("#m76wno2", mb).value, aktiv: w.id ? ($("#m76wak", mb).checked ? 1 : 0) : 1});
      if (!r || !r.ok) return false;
      toast("WPS gespeichert"); after();
    }}];
    if (w.id) btns.unshift({label: "Löschen", cls: "danger", onClick: async () => { const r = await api("/api/m76/wps/delete", {ids: [w.id]}); if (!r || r.ok === false) return false; toast("Gelöscht"); after(); }});
    await modal(w.id ? `${w.art} ${w.nr}` : "Neue WPS / WPQR", html, btns, true);
  }

  // ---------------------------------------------------------------- project tab
  async function m76Tab(T, pid){
    const [d, ov] = await Promise.all([api("/api/m76/project?project_id=" + pid), api("/api/m76/overview", undefined, {quiet: true})]);
    if (!d || !d.projekt) { T.innerHTML = `<div class="card empty">EN-1090-Daten nicht verfügbar.</div>`; return; }
    window.M76VF = ov.verfahren || {};
    d.wps_alle = (ov.wps || []).filter(w => w.aktiv);
    d.sw_alle = ov.schweisser_alle || [];
    const re = () => m76Tab(T, pid);
    const mk = d.merkmale || {};
    const E = d.eintraege;
    const sect = art => `<div class="card" style="margin-bottom:14px;overflow:hidden"><div class="hd"><h3>${TITLE[art]}</h3><div class="act"><button class="btn sm" data-m76new="${art}">${ic("plus")} Neu</button></div></div>
      <table class="t" data-m76tab="${art}"><thead><tr>${COLS[art].map(k => `<th>${esc(lbl(art, k))}</th>`).join("")}${art === "pos" ? "<th>WPS</th><th>Schweißer</th>" : ""}<th>Datei</th><th style="width:90px"></th></tr></thead>
      <tbody>${E[art].map(e => `<tr class="click" data-m76e="${e.id}" data-art="${art}">${COLS[art].map(k => `<td>${k === "datum" ? dde(e.data[k] || "") : k === "ergebnis" ? (e.data[k] === "n.i.O." ? `<span class="badge bad">n.i.O.</span>` : e.data[k] ? `<span class="badge ok">${esc(e.data[k])}</span>` : "") : esc(e.data[k] || "")}</td>`).join("")}
        ${art === "pos" ? `<td class="small">${esc(((d.wps || []).find(w => w.id == e.data.wps_id) || {}).nr || "")}</td><td class="small">${(e.data.schweisser || []).map(i => esc(((d.schweisser || []).find(z => z.id == i) || {}).person || "")).join(", ")}</td>` : ""}
        <td class="small">${e.file ? `<a href="#" data-m76of="${esc(e.file)}">${ic("pdf")} öffnen</a>` : ""}</td>
        <td class="r" onclick="event.stopPropagation()"><button class="btn sm ghost" data-m76up="${e.id}" title="Datei (PDF/Foto) anhängen">${ic("up")}</button><button class="btn sm ghost" data-m76del="${e.id}" title="Löschen">✕</button></td></tr>`).join("")
        || `<tr><td colspan="${COLS[art].length + (art === "pos" ? 4 : 2)}" class="empty">Noch nichts erfasst.</td></tr>`}</tbody></table></div>`;
    T.innerHTML = `
      ${d.warnungen.length ? `<div style="margin-bottom:12px">${d.warnungen.map(w => `<div class="alert ${WST[w.stufe] || ""}" style="cursor:default;margin-bottom:6px;font-size:12.5px">${ic("alert")}<span>${esc(w.text)}</span></div>`).join("")}</div>` : `<div class="alert ok" style="cursor:default;margin-bottom:12px">${ic("check")}<span>Dokumentation vollständig – keine offenen Punkte.</span></div>`}
      <div class="card" style="margin-bottom:14px"><div class="hd"><h3>Bauprodukt & Leistungserklärung</h3><div class="act">
        <button class="btn sm" data-m76mk="doku">${ic("pdf")} Schweißdoku</button><button class="btn sm" data-m76mk="dop">${ic("pdf")} Leistungserklärung</button>
        <button class="btn sm" data-m76mk="ce">${ic("pdf")} CE-Kennzeichnung</button><button class="btn sm pri" data-m76mk="pdf">${ic("pdf")} Übergabepaket PDF</button>
        <button class="btn sm" data-m76mk="zip">ZIP</button>${expButtons("m76_en1090", {project_id: pid}, true)}</div></div>
        <div class="bd"><div class="row" style="flex-wrap:wrap">
          <label class="f" style="flex:0 0 120px">Ausführungsklasse<select class="in" id="m76exc">${["EXC1", "EXC2", "EXC3", "EXC4"].map(k => `<option ${d.exc === k ? "selected" : ""}>${k}</option>`).join("")}</select></label>
          <label class="f" style="flex:2 1 260px">Bauprodukt / Kenncode<input class="in" id="m76prod" value="${esc(d.produkt || "")}" placeholder="z. B. Treppengeländer Stahl verzinkt"></label>
          <label class="f" style="flex:1 1 160px">Nr. Leistungserklärung<input class="in" id="m76dop" value="${esc(d.dop_nr || "")}" placeholder="${esc(d.dop_vorschlag || "")}"></label>
          <label class="f" style="flex:0 0 110px">CE-Jahr<input class="in" id="m76cej" value="${esc(d.ce_jahr || "")}" placeholder="${new Date().getFullYear()}"></label></div>
          <label class="f">Verwendungszweck<input class="in" id="m76verw" value="${esc(d.verwendung || "")}" placeholder="Tragendes Bauteil für Stahl- und Metallbaukonstruktionen …"></label>
          <details style="margin-top:6px"><summary class="small" style="cursor:pointer">Erklärte Leistungen (Merkmale) anpassen</summary>
            <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px;margin-top:8px">${(window.M76MK || [
              ["toleranz","Maßtoleranzen"],["schweisseignung","Schweißeignung"],["bruchzaehigkeit","Bruchzähigkeit"],["tragfaehigkeit","Tragfähigkeit"],["ermuedung","Ermüdungsfestigkeit"],
              ["feuerwiderstand","Feuerwiderstand"],["brandverhalten","Brandverhalten"],["cadmium","Freisetzung von Cadmium"],["radioaktiv","Freisetzung von Radioaktivität"],
              ["dauerhaftigkeit","Dauerhaftigkeit"],["herstellung","Herstellung"]]).map(([k, l]) => `<label class="f">${l}<input class="in" data-m76mkf="${k}" value="${esc(mk[k] || "")}" placeholder="Standard"></label>`).join("")}</div></details>
          <label class="f" style="margin-top:6px">Bemerkungen<textarea class="in" id="m76not" rows="2">${esc(d.notiz || "")}</textarea></label>
          <div class="row" style="margin-top:8px;align-items:center"><label class="chk" style="flex:none"><input type="checkbox" id="m76akt" ${d.aktiv || d.neu ? "checked" : ""}> EN-1090-Dokumentation für dieses Projekt führen</label><span style="flex:1"></span><button class="btn pri sm" id="m76save">Speichern</button></div></div></div>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px;margin-bottom:14px">
        <div class="card" style="overflow:hidden"><div class="hd"><h3>Schweißer (ISO 9606-1)</h3><div class="act"><select class="in" id="m76swsel" style="width:auto;height:30px"><option value="">+ zuordnen …</option>${d.sw_alle.filter(z => !d.schweisser.some(s => s.id === z.id)).map(z => `<option value="${z.id}">${esc((z.person || "") + " · " + (z.bezeichnung || z.nummer || ""))}</option>`).join("")}</select><button class="btn sm ghost" data-go="certs" title="Nachweise verwalten">Nachweise</button></div></div>
          <table class="t"><thead><tr><th>Person</th><th>Nachweis</th><th>gültig bis</th><th>Status</th><th></th></tr></thead><tbody>${d.schweisser.map(z => `<tr><td><b>${esc(z.person || "")}</b></td><td class="small">${esc(z.bezeichnung || "")} ${esc(z.nummer || "")}</td><td>${dde(z.gueltig_bis || "")}</td><td>${stB(z.state, z.state_txt)}</td><td class="r"><button class="btn sm ghost" data-m76unsw="${z.id}" title="Zuordnung entfernen">✕</button></td></tr>`).join("") || `<tr><td colspan="5" class="empty">Kein Schweißer zugeordnet.</td></tr>`}</tbody></table></div>
        <div class="card" style="overflow:hidden"><div class="hd"><h3>WPS / WPQR</h3><div class="act"><select class="in" id="m76wsel" style="width:auto;height:30px"><option value="">+ zuordnen …</option>${d.wps_alle.filter(w => !d.wps.some(x => x.id === w.id)).map(w => `<option value="${w.id}">${esc(w.art + " " + w.nr)}</option>`).join("")}</select><button class="btn sm" id="m76wnew">${ic("plus")} Neue WPS</button></div></div>
          <table class="t"><thead><tr><th>Art</th><th>Nr.</th><th>Verfahren</th><th>Werkstoff</th><th>gültig bis</th><th></th></tr></thead><tbody>${d.wps.map(w => `<tr class="click" data-m76w="${w.id}"><td>${esc(w.art)}</td><td><b>${esc(w.nr)}</b></td><td>${esc(w.verfahren || "")}</td><td class="small">${esc(w.werkstoff || "")} ${esc(w.dicke || "")}</td><td>${w.gueltig_bis ? stB(w.state, dde(w.gueltig_bis)) : "–"}</td><td class="r" onclick="event.stopPropagation()">${w.file ? `<button class="btn sm ghost" data-m76of="${esc(w.file)}" title="Datei öffnen">${ic("pdf")}</button>` : ""}<button class="btn sm ghost" data-m76wup="${w.id}" title="WPS-Datei anhängen">${ic("up")}</button><button class="btn sm ghost" data-m76unw="${w.id}" title="Zuordnung entfernen">✕</button></td></tr>`).join("") || `<tr><td colspan="6" class="empty">Keine WPS zugeordnet.</td></tr>`}</tbody></table></div></div>
      ${["pos", "zeugnis", "zusatz", "pruefung"].map(sect).join("")}
      ${d.dateien.length ? `<div class="card"><div class="hd"><h3>Erzeugte Dokumente (Ordner „EN 1090“)</h3></div><div class="bd">${d.dateien.map(f => `<a href="#" class="chip" data-m76of="${esc(f.path)}">${ic("pdf")} ${esc(f.name)}</a>`).join(" ")}</div></div>` : ""}`;
    bindCommon(T);
    const saveHead = async (quiet) => {
      const merk = {}; $$("[data-m76mkf]", T).forEach(i => { if (i.value.trim()) merk[i.dataset.m76mkf] = i.value.trim(); });
      const r = await api("/api/m76/save", {project_id: pid, aktiv: $("#m76akt", T).checked ? 1 : 0, exc: $("#m76exc", T).value, produkt: $("#m76prod", T).value,
        dop_nr: $("#m76dop", T).value, ce_jahr: $("#m76cej", T).value, verwendung: $("#m76verw", T).value, notiz: $("#m76not", T).value, merkmale: merk});
      if (r && r.ok && !quiet) { toast("Gespeichert"); S.m76 = S.m76 || {}; S.m76.ids = S.m76.ids || []; if (!S.m76.ids.includes(pid)) S.m76.ids.push(pid); }
      return r && r.ok;
    };
    $("#m76save", T).onclick = async () => { if (await saveHead()) re(); };
    $$("[data-m76mk]", T).forEach(b => b.onclick = async () => {
      await saveHead(true);
      toast("Dokument wird erstellt …");
      const r = await api("/api/m76/make", {project_id: pid, was: b.dataset.m76mk});
      if (r && r.ok) { toast(r.name + " im Projektordner abgelegt"); re(); }
    });
    $$("[data-m76new]", T).forEach(b => b.onclick = () => editEntry(pid, b.dataset.m76new, null, d, re));
    $$("[data-m76e]", T).forEach(r => r.onclick = () => editEntry(pid, r.dataset.art, E[r.dataset.art].find(e => e.id == r.dataset.m76e), d, re));
    $$("[data-m76del]", T).forEach(b => b.onclick = async () => { await api("/api/m76/entry/delete", {ids: [+b.dataset.m76del]}); toast("Gelöscht"); re(); });
    $$("[data-m76up]", T).forEach(b => b.onclick = () => upFile("entry", +b.dataset.m76up, re));
    $$("[data-m76wup]", T).forEach(b => b.onclick = () => upFile("wps", +b.dataset.m76wup, re));
    $$("[data-m76of]", T).forEach(a => a.onclick = ev => { ev.preventDefault(); ev.stopPropagation(); api("/api/open", {path: a.dataset.m76of}); });
    $$("[data-m76w]", T).forEach(r => r.onclick = () => editWps(d.wps.find(w => w.id == r.dataset.m76w), pid, re));
    $("#m76wnew", T).onclick = () => editWps(null, pid, re);
    $("#m76wsel", T).onchange = async e => { if (!e.target.value) return; await api("/api/m76/link", {project_id: pid, art: "wps", ref_id: +e.target.value}); re(); };
    $("#m76swsel", T).onchange = async e => { if (!e.target.value) return; await api("/api/m76/link", {project_id: pid, art: "schweisser", ref_id: +e.target.value}); re(); };
    $$("[data-m76unw]", T).forEach(b => b.onclick = async () => { await api("/api/m76/link", {project_id: pid, art: "wps", ref_id: +b.dataset.m76unw, weg: 1}); re(); });
    $$("[data-m76unsw]", T).forEach(b => b.onclick = async () => { await api("/api/m76/link", {project_id: pid, art: "schweisser", ref_id: +b.dataset.m76unsw, weg: 1}); re(); });
    ["pos", "zeugnis", "zusatz", "pruefung"].forEach(art => selectify({kind: "m76" + art, rows: $$(`table[data-m76tab="${art}"] tr[data-m76e]`, T), id: "data-m76e", rerender: re,
      actions: [{label: "Löschen", cls: "danger", run: async ids => { await api("/api/m76/entry/delete", {ids: ids.map(Number)}); toast(ids.length + " gelöscht"); re(); }}]}));
  }

  // ---------------------------------------------------------------- overview page
  async function m76View(){
    const d = await api("/api/m76/overview");
    window.M76VF = d.verfahren || {};
    $("#main").innerHTML = `<div class="page">${pageHead("EN 1090", "Schweiß- und Herstellungsdokumentation, WPS-Bibliothek, Schweißer-Nachweise", expButtons("m76_en1090", {}))}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Projekte</div><div class="v">${d.projekte.length}</div><div class="s">Metallbau / Schweißen</div></div>
        <div class="card kpi"><div class="l">Mit Fehlern</div><div class="v" style="color:${d.projekte.some(p => p.fehler) ? "var(--bad)" : "inherit"}">${d.projekte.filter(p => p.fehler).length}</div><div class="s">abgelaufen / n.i.O.</div></div>
        <div class="card kpi"><div class="l">WPS / WPQR</div><div class="v">${d.wps.filter(w => w.aktiv).length}</div><div class="s">${d.wps.filter(w => w.state === "abgelaufen").length} abgelaufen</div></div>
        <div class="card kpi"><div class="l">Schweißer</div><div class="v">${d.schweisser_alle.length}</div><div class="s">${d.schweisser_alle.filter(z => z.state !== "ok").length} mit Handlungsbedarf</div></div></div>
      <div class="card" style="margin-bottom:14px;overflow:hidden"><div class="hd"><h3>Projekte</h3></div><table class="t"><thead><tr><th>Nr.</th><th>Projekt</th><th>EXC</th><th>DoP</th><th class="r">Pos.</th><th class="r">Zeugn.</th><th class="r">Prüf.</th><th>Status</th></tr></thead>
        <tbody>${d.projekte.map(p => `<tr class="click" data-m76p="${p.id}"><td><b>${esc(p.nr)}</b></td><td>${esc(p.name)}${p.aktiv ? "" : ` <span class="badge">nicht aktiviert</span>`}</td><td>${esc(p.exc)}</td><td class="small">${esc(p.dop_nr)}</td>
          <td class="r num">${p.anzahl.pos}</td><td class="r num">${p.anzahl.zeugnis}</td><td class="r num">${p.anzahl.pruefung}</td>
          <td>${p.fehler ? `<span class="badge bad"><span class="dot"></span>${p.fehler} Fehler</span>` : p.warnungen ? `<span class="badge warn"><span class="dot"></span>${p.warnungen} offen</span>` : `<span class="badge ok"><span class="dot"></span>vollständig</span>`}</td></tr>`).join("")
          || `<tr><td colspan="8" class="empty">Keine Projekte im Bereich Metallbau/Schweißen.</td></tr>`}</tbody></table></div>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px">
      <div class="card" style="overflow:hidden"><div class="hd"><h3>WPS-Bibliothek</h3><div class="act"><button class="btn sm pri" id="m76wn2">${ic("plus")} Neue WPS / WPQR</button></div></div>
        <table class="t" id="m76wt"><thead><tr><th>Art</th><th>Nr.</th><th>Verfahren</th><th>Werkstoff</th><th>Dicke</th><th>Position</th><th>gültig bis</th><th class="r">Proj.</th></tr></thead>
        <tbody>${d.wps.map(w => `<tr class="click" data-m76w="${w.id}" style="${w.aktiv ? "" : "opacity:.55"}"><td>${esc(w.art)}</td><td><b>${esc(w.nr)}</b></td><td>${esc(w.verfahren || "")}</td><td>${esc(w.werkstoff || "")}</td><td>${esc(w.dicke || "")}</td><td>${esc(w.position || "")}</td>
          <td>${w.gueltig_bis ? stB(w.state, dde(w.gueltig_bis)) : "–"}</td><td class="r num">${w.n_proj}</td></tr>`).join("") || `<tr><td colspan="8" class="empty">Noch keine WPS erfasst.</td></tr>`}</tbody></table></div>
      <div class="card" style="overflow:hidden"><div class="hd"><h3>Schweißer-Nachweise</h3><div class="act"><button class="btn sm" data-go="certs">Nachweise verwalten</button></div></div>
        <table class="t"><thead><tr><th>Person</th><th>Nachweis</th><th>Nr.</th><th>gültig bis</th><th>Status</th></tr></thead>
        <tbody>${d.schweisser_alle.map(z => `<tr><td><b>${esc(z.person || "")}</b></td><td class="small">${esc(z.bezeichnung || "")}</td><td class="small">${esc(z.nummer || "")}</td><td>${dde(z.gueltig_bis || "")}</td><td>${stB(z.state, z.state_txt)}</td></tr>`).join("")
          || `<tr><td colspan="5" class="empty">Keine Schweißerprüfungen unter „Nachweise“ (Art „Schweißerprüfung (ISO 9606)“).</td></tr>`}</tbody></table></div></div></div>`;
    bindCommon();
    $$("[data-m76p]").forEach(r => r.onclick = () => { pTab = "m76"; go("project", +r.dataset.m76p); });
    $$("[data-m76w]").forEach(r => r.onclick = () => editWps(d.wps.find(w => w.id == r.dataset.m76w), null, m76View));
    $("#m76wn2").onclick = () => editWps(null, null, m76View);
    selectify({kind: "m76wps", rows: "#m76wt tr[data-m76w]", id: "data-m76w", rerender: m76View,
      actions: [{label: "Löschen", cls: "danger", run: async ids => { await api("/api/m76/wps/delete", {ids: ids.map(Number)}); toast(ids.length + " gelöscht"); m76View(); }}]});
  }

  // ---------------------------------------------------------------- settings tab (shared with m77)
  EXT.settings.push({key: "m76set", label: "EN 1090 & Abnahme", render: async el => {
    const d = await api("/api/m76/overview");
    const s = d.settings || {};
    const f = (k, l, ph) => `<label class="f">${l}<input class="in" data-m76s="${k}" value="${esc(s[k] || "")}" placeholder="${esc(ph || "")}"></label>`;
    el.innerHTML = `<div class="card" style="margin-bottom:14px"><div class="hd"><h3>EN 1090 – Angaben für Leistungserklärung und CE-Kennzeichnung</h3></div><div class="bd fr">
      <div class="row">${f("hersteller", "Hersteller (Name)")}${f("anschrift", "Anschrift Hersteller")}</div>
      <div class="row">${f("wpk_nr", "Zertifikat WPK (Nr.)", "z. B. 1234-CPR-1090-…")}${f("stelle_name", "Notifizierte Stelle (Name)")}${f("stelle_nr", "Kenn-Nr. notifizierte Stelle", "z. B. 1234")}</div>
      <div class="row">${f("aufsicht", "Schweißaufsicht / Unterzeichner")}${f("ort", "Ort (für Unterschrift)")}${f("avcp", "System (AVCP)", "2+")}</div>
      <div class="row">${f("norm", "Harmonisierte Norm", "EN 1090-1:2009+A1:2011")}${f("ausf_norm", "Ausführungsnorm", "EN 1090-2")}</div>
      <div class="row"><span style="flex:1"></span><button class="btn pri" id="m76ss">Speichern</button></div></div></div><div id="m77setbox"></div>`;
    $("#m76ss", el).onclick = async () => { const b = {}; $$("[data-m76s]", el).forEach(i => b[i.dataset.m76s] = i.value); const r = await api("/api/m76/settings", b); if (r && r.ok) toast("Gespeichert"); };
    if (window.m77SettingsRender) window.m77SettingsRender($("#m77setbox", el));
  }});
})();
