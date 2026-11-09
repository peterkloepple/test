// PA Rechnung v2.0.19 - UI-Modul m86_regeln: Regel-Automatik "Wenn - dann"
// Seite "Automatik" (Stammdaten): Regeln anlegen, Testlauf, an/aus, Protokoll; Hinweis-Kachel auf der Uebersicht.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m86 = '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>';
  let tab = "regeln";
  EXT.nav.push({key: "m86regeln", label: "Automatik", icon: "m86", section: "Stammdaten", cnt: () => S.m86_hinweise ? String(S.m86_hinweise) : ""});
  EXT.views.m86regeln = view86;

  const PRESETS = [
    {name: "Thomann-Belege → Kategorie", ausloeser: "beleg_neu", bedingungen: [{feld: "partner", op: "enthaelt", wert: "thomann"}], aktionen: [{typ: "kategorie", wert: ""}, {typ: "projekt", wert: "auto"}]},
    {name: "Zahlungserinnerung nach 14 Tagen", ausloeser: "rechnung_ueberfaellig", tage: 14, bedingungen: [{feld: "mahnstufe", op: "gleich", wert: "0"}],
      aktionen: [{typ: "mail", an: "kunde", betreff: "Erinnerung: Rechnung [Nummer]", anhang: true,
        text: "Guten Tag,\n\nsicher ist es Ihrer Aufmerksamkeit entgangen: Für die Rechnung [Nummer] über [Betrag] (fällig am [Faellig]) konnte ich noch keinen Zahlungseingang feststellen.\nIch bitte um Überweisung in den nächsten Tagen.\n\nMit freundlichen Grüßen\n" + ((S && S.settings && S.settings.inhaber) || "")},
        {typ: "hinweis", wert: "Erinnerung an [Kunde] zu Rechnung [Nummer] verschickt"}]},
    {name: "Angebot nach 10 Tagen nachfassen", ausloeser: "angebot_offen", tage: 10, bedingungen: [], aktionen: [{typ: "hinweis", wert: "Angebot [Nummer] an [Kunde] seit [Tage] Tagen offen – nachfassen"}]},
    {name: "Wartung fällig → Rechnungsentwurf", ausloeser: "wartung_faellig", bedingungen: [], aktionen: [{typ: "entwurf"}, {typ: "hinweis", wert: "Wartung [Vertrag] ([Kunde]) am [Termin] – Entwurf angelegt"}]},
    {name: "Große Ausgabe melden", ausloeser: "bank_neu", bedingungen: [{feld: "betrag", op: "kleiner", wert: "-500"}], aktionen: [{typ: "hinweis", wert: "Abbuchung [Betrag] an [Name]"}]},
  ];

  async function view86(){
    const d = await api("/api/m86/list");
    const M = d.meta, rs = d.regeln || [];
    window._m86meta = M;
    $("#main").innerHTML = `<div class="page">${pageHead("Automatik", "Regeln „Wenn – dann“: Belege einsortieren, Erinnerungen schicken, Entwürfe anlegen, Hinweise zeigen",
        expButtons("m86_log") + `<button class="btn" id="m86run">${ic("m86")} Jetzt prüfen</button><button class="btn pri" id="m86new">${ic("plus")} Neue Regel</button>`)}
      <div class="tabs"><div class="tab ${tab === "regeln" ? "on" : ""}" data-m86t="regeln">Regeln<span class="cnt">${rs.length}</span></div><div class="tab ${tab === "log" ? "on" : ""}" data-m86t="log">Protokoll<span class="cnt">${(d.log || []).length}</span></div></div>
      ${tab === "regeln" ? `<div class="card" style="overflow:hidden"><table class="t"><thead><tr><th style="width:60px">An</th><th>Name</th><th>Wenn</th><th>Bedingungen</th><th>Dann</th><th class="r">ausgeführt</th><th>zuletzt</th><th style="width:150px"></th></tr></thead>
        <tbody>${rs.map(r => `<tr class="click" data-m86id="${r.id}" style="${r.aktiv ? "" : "opacity:.55"}"><td onclick="event.stopPropagation()"><input type="checkbox" data-m86on="${r.id}" ${r.aktiv ? "checked" : ""} style="width:17px;height:17px;accent-color:var(--acc)"></td>
          <td><b>${esc(r.name)}</b>${r.wiederholen ? ` <span class="badge">wiederholt</span>` : ""}</td><td class="small">${esc((M.ausloeser[r.ausloeser] || {}).label || r.ausloeser)}${r.tage ? ` (${r.tage} T.)` : ""}</td>
          <td class="small muted">${r.bedingungen.length ? r.bedingungen.map(b => esc(fName(M, r.ausloeser, b.feld) + " " + (M.ops[b.op] || b.op) + (["leer", "nicht_leer"].includes(b.op) ? "" : " „" + (b.wert || "") + "“"))).join(r.modus === "eine" ? " <b>oder</b> " : " <b>und</b> ") : "immer"}</td>
          <td class="small">${r.aktionen.map(z => esc((M.aktionen[z.typ] || {}).label || z.typ)).join(", ")}</td><td class="r num">${r.n || 0}${r.fehler ? ` <span class="badge bad">${r.fehler} Fehler</span>` : ""}</td><td class="small num">${r.letzte ? dde(r.letzte.slice(0, 10)) + " " + r.letzte.slice(11, 16) : "–"}</td>
          <td class="r" onclick="event.stopPropagation()"><button class="btn sm ghost" data-m86test="${r.id}">Testlauf</button><button class="btn sm ghost" data-m86dup="${r.id}" title="Kopieren">${ic("copy")}</button><button class="btn sm ghost danger" data-m86del="${r.id}">${ic("trash")}</button></td></tr>`).join("")
          || `<tr><td colspan="8" class="empty">Noch keine Regeln. Mit „Neue Regel“ anlegen oder eine Vorlage nehmen:<div style="margin-top:10px">${PRESETS.map((p, i) => `<button class="btn sm" data-m86pre="${i}" style="margin:3px">${esc(p.name)}</button>`).join("")}</div></td></tr>`}</tbody></table></div>
        <div class="small muted" style="margin-top:10px">Jede Regel wirkt pro Beleg/Rechnung/Vertrag nur einmal – eine E-Mail geht nie zweimal an dasselbe Dokument. Fällige Regeln (überfällig, Angebot offen, Wartung, täglich) prüft das Programm alle 10 Minuten; „Jetzt prüfen“ startet sofort.</div>`
      : `<div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Zeit</th><th>Regel</th><th>Objekt</th><th>Aktion</th><th>Ergebnis</th></tr></thead><tbody>${(d.log || []).map(l => `<tr><td class="small num">${dde(l.zeit.slice(0, 10))} ${l.zeit.slice(11, 16)}</td><td>${esc(l.regel || "")}</td><td class="small">${esc(l.titel || "")}</td><td class="small">${esc(l.aktion || "")}</td>
        <td class="small">${l.ok ? esc(l.ergebnis || "") : `<span class="badge bad">Fehler</span> ${esc(l.ergebnis || "")}`}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">Noch nichts passiert.</td></tr>`}</tbody></table></div>`}</div>`;
    bindCommon();
    $$("[data-m86t]").forEach(t => t.onclick = () => { tab = t.dataset.m86t; view86(); });
    $("#m86new").onclick = () => edit86({ausloeser: "beleg_neu", aktiv: 1, modus: "alle", bedingungen: [{feld: "partner", op: "enthaelt", wert: ""}], aktionen: [{typ: "kategorie"}]});
    $("#m86run").onclick = async () => { const r = await api("/api/m86/run", {}); if (r && r.ok) { toast(r.n ? `${r.n} Regel-Ausführung(en)` : "Nichts fällig"); await reload(); view86(); } };
    $$("[data-m86pre]").forEach(b => b.onclick = () => edit86(JSON.parse(JSON.stringify(Object.assign({aktiv: 1, modus: "alle"}, PRESETS[+b.dataset.m86pre])))));
    $$("[data-m86id]").forEach(r => r.onclick = () => edit86(JSON.parse(JSON.stringify(rs.find(x_ => x_.id == r.dataset.m86id)))));
    $$("[data-m86dup]").forEach(b => b.onclick = () => { const r = JSON.parse(JSON.stringify(rs.find(x_ => x_.id == b.dataset.m86dup))); delete r.id; r.name += " (Kopie)"; r.aktiv = 0; edit86(r); });
    $$("[data-m86on]").forEach(c => c.onchange = async () => { await api("/api/m86/toggle", {id: +c.dataset.m86on, aktiv: c.checked}); view86(); });
    $$("[data-m86del]").forEach(b => b.onclick = async () => { await api("/api/m86/delete", {id: +b.dataset.m86del}); toast("Regel gelöscht"); view86(); });
    $$("[data-m86test]").forEach(b => b.onclick = () => testRun(rs.find(x_ => x_.id == b.dataset.m86test)));
  }

  const objOf = (M, a) => (M.ausloeser[a] || {}).obj;
  function fieldList(M, a){
    const obj = objOf(M, a), base = (M.felder[obj] || []).map(([k, l]) => [k, l]);
    const mo = {beleg: ["beleg", "projekt"], dok: ["rechnung", "kunde", "projekt"], wartung: ["kunde", "projekt"]}[obj] || [];
    const on = {kunde: "Kunde", projekt: "Projekt", beleg: "Beleg", rechnung: "Dokument"};
    (M.m85 || []).filter(f => mo.includes(f.objekt)).forEach(f => base.push(["feld:" + f.id, "Eigenes Feld (" + on[f.objekt] + "): " + f.name]));
    return base;
  }
  function fName(M, a, k){ const f = fieldList(M, a).find(([kk]) => kk === k); return f ? f[1] : k; }

  function condRow(M, a, b, i){
    return `<div class="row" data-m86c="${i}" style="gap:6px;margin-bottom:4px;align-items:center"><select class="in" data-k="feld" style="flex:1.2">${fieldList(M, a).map(([k, l]) => `<option value="${esc(k)}" ${b.feld === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <select class="in" data-k="op" style="flex:.9">${Object.entries(M.ops).map(([k, l]) => `<option value="${k}" ${b.op === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
      <input class="in" data-k="wert" style="flex:1.2" value="${esc(b.wert || "")}" placeholder="Wert (mehrere mit | = oder)"><button class="btn sm ghost danger" type="button" data-m86cdel="${i}" style="flex:none">${ic("trash")}</button></div>`;
  }
  function actParams(M, a, z){
    const t = z.typ, obj = objOf(M, a);
    if (t === "kategorie") return `<select class="in" data-k="wert"><option value="">– Kategorie wählen –</option>${(M.kategorien || []).map(k => `<option ${z.wert === k ? "selected" : ""}>${esc(k)}</option>`).join("")}</select>`;
    if (t === "projekt") return `<select class="in" data-k="wert"><option value="auto" ${!z.wert || z.wert === "auto" ? "selected" : ""}>automatisch: Projekt-Nr. im Text suchen</option>${(M.projekte || []).map(p => `<option value="${p.id}" ${String(z.wert) === String(p.id) ? "selected" : ""}>${esc(p.nr + " " + p.name)}</option>`).join("")}</select>`;
    if (t === "status") return `<select class="in" data-k="wert">${[["bezahlt", "bezahlt"], ["offen", "offen"], ["abgelehnt", "abgelehnt (Angebot)"], ["angenommen", "angenommen (Angebot)"], ["erledigt", "erledigt"]].map(([k, l]) => `<option value="${k}" ${z.wert === k ? "selected" : ""}>${l}</option>`).join("")}</select>`;
    if (t === "notiz" || t === "hinweis") return `<input class="in" data-k="wert" value="${esc(z.wert || "")}" placeholder="Text – Platzhalter [Nummer] [Kunde] [Betrag] [Tage] [Partner] …">`;
    if (t === "feld") { const mo = obj === "beleg" ? "beleg" : "rechnung"; const fs = (M.m85 || []).filter(f => f.objekt === mo);
      return fs.length ? `<div class="row" style="gap:6px"><select class="in" data-k="feld">${fs.map(f => `<option ${z.feld === f.name ? "selected" : ""}>${esc(f.name)}</option>`).join("")}</select><input class="in" data-k="wert" value="${esc(z.wert || "")}" placeholder="Wert"></div>`
        : `<span class="small muted">Keine eigenen Felder für ${obj === "beleg" ? "Belege" : "Rechnungen"} angelegt (Einstellungen › Eigene Felder).</span>`; }
    if (t === "entwurf") return `<span class="small muted">Legt einen Rechnungsentwurf mit Leistung und Preis des Vertrags an (Termin wird nicht weitergeschaltet).</span>`;
    if (t === "mail") return `<div class="fr" style="gap:4px"><div class="row" style="gap:6px"><label class="f" style="flex:.7">An<input class="in" data-k="an" value="${esc(z.an || "kunde")}" placeholder="kunde | ich | adresse@…"></label>
        <label class="f">Betreff<input class="in" data-k="betreff" value="${esc(z.betreff || "")}"></label></div><textarea class="in" data-k="text" rows="5" placeholder="Text – [Nummer] [Betrag] [Kunde] [Faellig] [Tage] {{Feld:Name}}">${esc(z.text || "")}</textarea>
        ${obj === "dok" ? `<label class="chk"><input type="checkbox" data-k="anhang" ${z.anhang ? "checked" : ""}> PDF des Dokuments anhängen</label>` : ""}</div>`;
    return "";
  }
  function actRow(M, a, z, i){
    const obj = objOf(M, a), opts = Object.entries(M.aktionen).filter(([, v]) => v.obj.includes(obj));
    return `<div class="card" data-m86a="${i}" style="padding:8px;margin-bottom:6px"><div class="row" style="gap:6px;align-items:flex-start"><select class="in" data-k="typ" style="flex:none;width:230px">${opts.map(([k, v]) => `<option value="${k}" ${z.typ === k ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select>
      <div style="flex:1;min-width:0" data-m86p>${actParams(M, a, z)}</div><button class="btn sm ghost danger" type="button" data-m86adel="${i}" style="flex:none">${ic("trash")}</button></div></div>`;
  }
  function read(mb, r){
    const o = {id: r.id || null, name: $("#m86n", mb).value, ausloeser: $("#m86au", mb).value, tage: +($("#m86tg", mb) || {value: 0}).value || 0, modus: $("#m86mo", mb).value,
      aktiv: $("#m86ak", mb).checked ? 1 : 0, wiederholen: $("#m86wh", mb).checked ? 1 : 0, bedingungen: [], aktionen: []};
    $$("[data-m86c]", mb).forEach(c => { const b = {}; $$("[data-k]", c).forEach(e => b[e.dataset.k] = e.value); o.bedingungen.push(b); });
    $$("[data-m86a]", mb).forEach(c => { const z = {}; $$("[data-k]", c).forEach(e => z[e.dataset.k] = e.type === "checkbox" ? e.checked : e.value); o.aktionen.push(z); });
    return o;
  }
  async function edit86(r){
    const M = window._m86meta;
    const html = () => { const A = M.ausloeser[r.ausloeser] || {};
      return `<div class="fr"><div class="row"><label class="f">Name<input class="in" id="m86n" value="${esc(r.name || "")}" placeholder="z. B. Thomann → Material"></label>
        <label class="chk" style="flex:none;align-self:flex-end;margin-bottom:8px"><input type="checkbox" id="m86ak" ${r.aktiv ? "checked" : ""}> aktiv</label></div>
      <div class="row"><label class="f"><b>Wenn</b><select class="in" id="m86au">${Object.entries(M.ausloeser).map(([k, v]) => `<option value="${k}" ${r.ausloeser === k ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></label>
        ${A.tage ? `<label class="f" style="flex:.4">Tage<input class="in num" id="m86tg" value="${r.tage || 0}"></label>` : ""}</div>
      <div class="row" style="align-items:center"><b style="flex:none">Bedingungen</b><select class="in" id="m86mo" style="width:auto;flex:none"><option value="alle" ${r.modus !== "eine" ? "selected" : ""}>alle müssen zutreffen</option><option value="eine" ${r.modus === "eine" ? "selected" : ""}>eine reicht</option></select><span class="sp"></span><button class="btn sm" type="button" id="m86cadd">${ic("plus")} Bedingung</button></div>
      <div>${(r.bedingungen || []).map((b, i) => condRow(M, r.ausloeser, b, i)).join("") || `<div class="small muted">keine – Regel gilt immer</div>`}</div>
      <div class="row" style="align-items:center;margin-top:6px"><b style="flex:none">Dann</b><span class="sp"></span><button class="btn sm" type="button" id="m86aadd">${ic("plus")} Aktion</button></div>
      <div>${(r.aktionen || []).map((z, i) => actRow(M, r.ausloeser, z, i)).join("")}</div>
      <label class="chk"><input type="checkbox" id="m86wh" ${r.wiederholen ? "checked" : ""}> bei jedem Auslösen erneut ausführen (sonst nur einmal pro Objekt; E-Mails gehen trotzdem nie doppelt)</label>
      <div id="m86res"></div></div>`; };
    const bind = mb => {
      const redraw = () => { const keep = read(mb, r); Object.assign(r, keep); $(".mc", mb).innerHTML = html(); bind(mb); };
      $("#m86au", mb).onchange = () => { const k = read(mb, r); k.bedingungen = []; const obj = objOf(M, k.ausloeser);
        k.aktionen = k.aktionen.filter(z => (M.aktionen[z.typ] || {obj: []}).obj.includes(obj)); if (!k.aktionen.length) k.aktionen = [{typ: Object.keys(M.aktionen).find(t => M.aktionen[t].obj.includes(obj))}];
        Object.assign(r, k); $(".mc", mb).innerHTML = html(); bind(mb); };
      $("#m86cadd", mb).onclick = () => { const k = read(mb, r); k.bedingungen.push({feld: (fieldList(M, k.ausloeser)[0] || [""])[0], op: "enthaelt", wert: ""}); Object.assign(r, k); $(".mc", mb).innerHTML = html(); bind(mb); };
      $("#m86aadd", mb).onclick = () => { const k = read(mb, r); k.aktionen.push({typ: "hinweis", wert: ""}); Object.assign(r, k); $(".mc", mb).innerHTML = html(); bind(mb); };
      $$("[data-m86cdel]", mb).forEach(b => b.onclick = () => { const k = read(mb, r); k.bedingungen.splice(+b.dataset.m86cdel, 1); Object.assign(r, k); $(".mc", mb).innerHTML = html(); bind(mb); });
      $$("[data-m86adel]", mb).forEach(b => b.onclick = () => { const k = read(mb, r); k.aktionen.splice(+b.dataset.m86adel, 1); Object.assign(r, k); $(".mc", mb).innerHTML = html(); bind(mb); });
      $$("[data-m86a] select[data-k=typ]", mb).forEach(s => s.onchange = redraw);
    };
    await modal(r.id ? "Regel bearbeiten" : "Neue Regel", html(), [{label: "Abbrechen"},
      {label: "Testlauf", onClick: async mb => { const o = read(mb, r); const t = await api("/api/m86/test", o); if (t && t.ok) $("#m86res", mb).innerHTML = testHtml(t); return false; }},
      {label: "Speichern", cls: "pri", onClick: async mb => { const res = await api("/api/m86/save", read(mb, r)); if (!res || !res.ok) return false; toast("Regel gespeichert"); }}], true, bind);
    if (view === "m86regeln") view86();
  }
  function testHtml(t){
    return `<div class="card" style="margin-top:10px;padding:10px"><b>Testlauf – nichts wurde geändert</b> <span class="small muted">${esc(t.hinweis)} · ${t.treffer.length} von ${t.gesamt} passen</span>
      ${t.treffer.length ? `<table class="t" style="margin-top:6px"><tbody>${t.treffer.slice(0, 40).map(r => `<tr><td>${esc(r.titel)}${r.erledigt ? ` <span class="badge">schon erledigt</span>` : ""}<div class="small muted">${r.gruende.map(esc).join(" · ")}</div></td>
        <td class="small">${r.aktionen.map(esc).join("<br>")}</td></tr>`).join("")}</tbody></table>` : `<div class="small muted" style="margin-top:6px">Kein Treffer.</div>`}</div>`;
  }
  async function testRun(r){
    const t = await api("/api/m86/test", r); if (!t || !t.ok) return;
    modal("Testlauf: " + r.name, testHtml(t), [{label: "Schließen"}], true);
  }

  // dashboard: notices of the rules
  EXT.dash.push(async el => {
    const d = await api("/api/m86/hinweise", undefined, {quiet: true}); const hs = (d && d.hinweise) || [];
    if (!hs.length) return;
    const c = document.createElement("div"); c.className = "card"; c.id = "m86hw"; c.style.marginBottom = "12px";
    c.innerHTML = `<div class="hd"><h3>${ic("m86")} Hinweise der Automatik</h3><div class="act"><button class="btn sm ghost" data-m86ok="alle">alle erledigt</button><button class="btn sm ghost" data-go="m86regeln">Regeln</button></div></div>
      <div class="bd" style="padding-top:0"><table class="t"><tbody>${hs.slice(0, 12).map(h => `<tr><td class="small num" style="width:90px">${dde(h.zeit.slice(0, 10))}</td><td>${esc(h.text)}</td>
        <td class="r" style="width:110px">${h.objekt === "dok" && h.objekt_id ? `<button class="btn sm ghost" data-m86open="${h.objekt_id}">öffnen</button>` : ""}<button class="btn sm ghost" data-m86ok="${h.id}" title="erledigt">${ic("check")}</button></td></tr>`).join("")}</tbody></table></div>`;
    el.appendChild(c); bindCommon(c);
    $$("[data-m86ok]", c).forEach(b => b.onclick = async () => { await api("/api/m86/hinweis_ok", b.dataset.m86ok === "alle" ? {alle: true} : {id: +b.dataset.m86ok}); const tr = b.closest("tr");
      if (tr && b.dataset.m86ok !== "alle") tr.remove(); else c.remove(); if (!$("tr", c)) c.remove(); S.m86_hinweise = Math.max(0, (S.m86_hinweise || 1) - 1); renderSide(); });
    $$("[data-m86open]", c).forEach(b => b.onclick = () => openInvoice(+b.dataset.m86open));
  });
})();
