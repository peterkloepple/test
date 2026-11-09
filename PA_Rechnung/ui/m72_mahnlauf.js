// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m72_mahnlauf: Mahnlauf auf Knopfdruck
// Seite "Mahnlauf" (Finanzen): ueberfaellige Rechnungen, vorgeschlagene Stufe, Zinsen/Pauschale, Versand per Mail oder Sammel-PDF.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m72 = '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/><path d="M17 3h4v4"/>';
  const SEL = {}; let showAll = false, lastRun = null;

  EXT.nav.push({key: "m72mahn", label: "Mahnlauf", icon: "m72", section: "Finanzen",
    cnt: () => (S.m72 && S.m72.heute && S.m72.heute.n) ? String(S.m72.heute.n) : (S.overdue && S.overdue.length ? String(S.overdue.length) : "")});
  EXT.views.m72mahn = view;

  EXT.dash.push(el => {
    const h = S.m72 && S.m72.heute; if (!h || !h.n) return;
    const d = document.createElement("div"); d.className = "alert warn"; d.style.marginBottom = "10px"; d.style.cursor = "pointer";
    d.innerHTML = `${ic("m72")}<b>Mahnlauf: ${h.n} Rechnung(en) zur nächsten Mahnstufe</b><span class="small">offen zusammen ${eur(h.summe || 0)}${h.gesendet ? ` · heute automatisch versendet: ${h.gesendet}` : ""}</span><span class="sp" style="flex:1"></span><span class="small"><u>Mahnlauf öffnen →</u></span>`;
    d.onclick = () => go("m72mahn");
    el.appendChild(d);
  });

  async function settings(d){
    const c = d.cfg;
    await modal("Mahnlauf – Einstellungen", `<div class="fr">
      <div class="row"><label class="f">Basiszinssatz %<input class="in num" id="m72b" value="${nde(c.m72_basis)}"></label>
        <label class="f">gültig ab<input type="date" class="in" id="m72bd" value="${esc(c.m72_basis_datum)}"></label></div>
      <div class="small muted" style="margin:-4px 0 8px">Wird von der Deutschen Bundesbank zum 1.1. und 1.7. bekannt gegeben – bitte halbjährlich prüfen (bundesbank.de → Basiszinssatz).
        Verzugszinsen: Unternehmen 9, Verbraucher 5 Prozentpunkte über Basiszinssatz (§ 288 BGB). Pauschale 40 € nur gegenüber Unternehmen.</div>
      <div class="row"><label class="f">Verzugszinsen ab Stufe<select class="in" id="m72z">${[[-1, "nie"], ...d.stufen.map((s, i) => [i, s])].map(([v, l]) => `<option value="${v}" ${c.m72_zinsen_ab == v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="f">40-€-Pauschale ab Stufe<select class="in" id="m72p">${[[-1, "nie"], ...d.stufen.map((s, i) => [i, s])].map(([v, l]) => `<option value="${v}" ${c.m72_pauschale_ab == v ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
      <div class="row"><label class="f">Erste Erinnerung ab Tagen überfällig<input class="in num" id="m72e" value="${c.m72_erste}"></label>
        <label class="f">Tage nach Ablauf der Mahnfrist bis zur nächsten Stufe<input class="in num" id="m72a" value="${c.m72_abstand}"></label></div>
      <label class="chk"><input type="checkbox" id="m72av" ${c.m72_auto_vorschlag ? "checked" : ""}> Täglich prüfen und auf der Übersicht melden</label>
      <label class="chk"><input type="checkbox" id="m72as" ${c.m72_auto_senden ? "checked" : ""}> Fällige Mahnungen täglich automatisch per E-Mail senden (nur Kunden mit E-Mail-Adresse)</label>
      <label class="f" style="margin-top:8px">E-Mail-Betreff<input class="in" id="m72mb" value="${esc(c.m72_mail_betreff)}"></label>
      <label class="f">E-Mail-Text<textarea class="in" id="m72mt" rows="7">${esc(c.m72_mail_text)}</textarea></label>
      <div class="small muted">Platzhalter: [Dokument] [Nummer] [Offen] [Betrag] [Mahnfrist] [Name] [Inhaber] [Firma]. Mahngebühren je Stufe und Mahntexte: Einstellungen → Mahnwesen.</div></div>`,
      [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
        const r = await api("/api/m72/cfg", {m72_basis: pnum($("#m72b", mb).value), m72_basis_datum: $("#m72bd", mb).value, m72_zinsen_ab: +$("#m72z", mb).value,
          m72_pauschale_ab: +$("#m72p", mb).value, m72_erste: pnum($("#m72e", mb).value), m72_abstand: pnum($("#m72a", mb).value),
          m72_auto_vorschlag: $("#m72av", mb).checked, m72_auto_senden: $("#m72as", mb).checked, m72_mail_betreff: $("#m72mb", mb).value, m72_mail_text: $("#m72mt", mb).value});
        if (!r || !r.ok) return false; toast("Gespeichert"); view(); }}], true);
  }

  async function showLauf(id){
    const r = await api("/api/m72/lauf?id=" + id); if (!r || !r.ok) return;
    const z = (r.lauf.details && r.lauf.details.zeilen) || [];
    await modal(`Mahnlauf vom ${dde(r.lauf.zeit.slice(0, 10))} ${r.lauf.zeit.slice(11, 16)}`, `<table class="t"><thead><tr><th>Rechnung</th><th>Mahnung</th><th class="r">Betrag</th><th>Ergebnis</th></tr></thead><tbody>
      ${z.map(x_ => `<tr><td>${esc(x_.nr || "")}</td><td>${esc(x_.titel || "")}</td><td class="r num">${x_.betrag ? eur(x_.betrag) : ""}</td><td class="small">${x_.gesendet ? "✉ an " + esc(x_.gesendet) : x_.fehler ? `<span style="color:var(--bad)">${esc(x_.fehler)}</span>` : "PDF / Druck" + (x_.hinweis ? " – " + esc(x_.hinweis) : "")}</td></tr>`).join("")}</tbody></table>
      ${r.lauf.details && r.lauf.details.sammel ? `<div style="margin-top:10px"><button class="btn" id="m72os">${ic("pdf")} Sammel-PDF öffnen</button></div>` : ""}`, [{label: "Schließen"}], true,
      mb => { const b = $("#m72os", mb); if (b) b.onclick = () => api("/api/m72/open", {path: r.lauf.details.sammel}); });
  }

  async function view(){
    const d = await api("/api/m72/list");
    if (!d || !d.zeilen) return;
    d.zeilen.forEach(r => { if (SEL[r.id] === undefined) SEL[r.id] = {on: r.vorgeschlagen, stufe: r.stufe, senden: !!r.mail}; });
    const rows = showAll ? d.zeilen : d.zeilen.filter(r => r.vorgeschlagen || SEL[r.id].on);
    const chosen = d.zeilen.filter(r => SEL[r.id] && SEL[r.id].on);
    const sum = chosen.reduce((a, r) => a + r.gesamt, 0);
    $("#main").innerHTML = `<div class="page">${pageHead("Mahnlauf", "Alle überfälligen Rechnungen auf einen Blick – markieren, Stufe prüfen, mit einem Klick mahnen",
        expButtons("m72_mahnlauf", {}) + `<button class="btn" id="m72set">${ic("set")} Einstellungen</button>`)}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Überfällig</div><div class="v">${d.zeilen.length}</div><div class="s">${eur(d.zeilen.reduce((a, r) => a + r.rest, 0))} offen</div></div>
        <div class="card kpi"><div class="l">Zur Mahnung fällig</div><div class="v" style="color:${d.zeilen.some(r => r.vorgeschlagen) ? "var(--warn)" : "inherit"}">${d.zeilen.filter(r => r.vorgeschlagen).length}</div><div class="s">nach Fristen</div></div>
        <div class="card kpi"><div class="l">Ausgewählt</div><div class="v">${chosen.length}</div><div class="s">${eur(sum)} inkl. Gebühren/Zinsen</div></div>
        <div class="card kpi"><div class="l">Basiszinssatz</div><div class="v" style="font-size:20px">${nde(d.cfg.m72_basis)} %</div><div class="s">seit ${dde(d.cfg.m72_basis_datum)}</div></div></div>
      <div class="row" style="margin-bottom:12px;align-items:center">
        <label class="chk" style="flex:none"><input type="checkbox" id="m72all" ${showAll ? "checked" : ""}> auch noch nicht fällige anzeigen</label>
        <span class="sp" style="flex:1"></span>
        <label class="chk" style="flex:none"><input type="checkbox" id="m72sam" checked> Ausdrucke als ein Sammel-PDF</label>
        <button class="btn pri" id="m72go" ${chosen.length ? "" : "disabled"}>${ic("m72")} ${chosen.length} Mahnung(en) erstellen & senden</button></div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th style="width:28px"></th><th>Rechnung</th><th>Kunde</th><th>Fällig</th><th class="r">Tage</th><th>Stufe</th>
        <th class="r">Offen</th><th class="r">Gebühr</th><th class="r">Zinsen</th><th class="r">Pauschale</th><th class="r">Gesamt</th><th>Versand</th></tr></thead>
        <tbody>${rows.map(r => { const s = SEL[r.id]; return `<tr data-m72r="${r.id}" style="${r.vorgeschlagen ? "" : "opacity:.75"}">
          <td><input type="checkbox" data-m72c="${r.id}" ${s.on ? "checked" : ""}></td>
          <td><a href="#" data-inv="${r.id}"><b>${esc(r.nr)}</b></a><div class="small muted">${r.mahnungen ? `${r.mahnungen} Mahnung(en), zuletzt ${dde(r.letzte)}` : "noch nicht gemahnt"}</div></td>
          <td>${esc(r.name)}<div class="small"><span class="chip ${r.b2b ? "on" : ""}" data-m72b="${r.customer_id || ""}" data-v="${r.b2b ? 0 : 1}" title="${r.customer_id ? "Klick: zwischen Unternehmen und Verbraucher umschalten" : "ohne Kundenstamm"}">${r.b2b ? "Unternehmen" : "Verbraucher"}${r.b2b_manuell ? " ✎" : ""}</span></div></td>
          <td class="num">${dde(r.faellig)}</td><td class="r num">${r.tage}</td>
          <td><select class="in" data-m72s="${r.id}" style="width:auto;padding:3px 6px">${d.stufen.map((l, i) => `<option value="${i}" ${s.stufe == i ? "selected" : ""}>${l}</option>`).join("")}</select>${r.hinweis ? `<div class="small muted">${esc(r.hinweis)}</div>` : ""}</td>
          <td class="r num">${eur(r.rest)}${r.gezahlt ? `<div class="small muted">gezahlt ${eur(r.gezahlt)}</div>` : ""}</td><td class="r num">${r.gebuehr ? eur(r.gebuehr) : "–"}</td>
          <td class="r num">${r.zinsen ? `${eur(r.zinsen)}<div class="small muted">${nde(r.zins_satz)} % · ${r.zins_tage} T.</div>` : "–"}</td><td class="r num">${r.pauschale ? eur(r.pauschale) : "–"}</td>
          <td class="r num"><b>${eur(r.gesamt)}</b></td>
          <td class="small">${r.mail ? `<label class="chk"><input type="checkbox" data-m72m="${r.id}" ${s.senden ? "checked" : ""}> ✉ ${esc(r.mail)}</label>` : `<span class="muted">${ic("pdf").replace("<svg ", '<svg style="width:14px;height:14px;vertical-align:-2px;stroke:currentColor;fill:none;stroke-width:2" ')} Druck (keine E-Mail)</span>`}</td></tr>`; }).join("")
        || `<tr><td colspan="12" class="empty">${d.zeilen.length ? "Zurzeit ist keine Mahnung fällig. Mit „auch noch nicht fällige anzeigen“ siehst du alle überfälligen Rechnungen." : "Keine überfälligen Rechnungen – alles im grünen Bereich."}</td></tr>`}</tbody></table></div>
      <div class="small muted" style="margin-top:8px">Hinweis: Zinsen und Pauschale werden bis heute berechnet und als eigene Positionen auf die Mahnung gesetzt; der GiroCode enthält den Gesamtbetrag. Verzug bei Verbrauchern setzt voraus, dass auf der Rechnung auf die Folgen hingewiesen wurde (§ 286 Abs. 3 BGB) – im Zweifel erst ab der 1. Mahnung berechnen.</div>
      ${lastRun ? `<div class="card" style="margin-top:14px"><div class="hd"><h3>Ergebnis</h3></div><div class="bd small">${lastRun.erstellt} Mahnung(en) erstellt · ${lastRun.gesendet} per E-Mail · ${lastRun.drucken.length} zum Drucken${lastRun.fehler ? ` · <b style="color:var(--bad)">${lastRun.fehler} Fehler</b>` : ""}
        ${lastRun.zeilen.filter(z => z.fehler).map(z => `<div style="color:var(--bad)">${esc(z.nr || "")}: ${esc(z.fehler)}</div>`).join("")}
        <div style="margin-top:8px">${lastRun.sammel_pdf ? `<button class="btn sm" id="m72op">${ic("pdf")} Sammel-PDF öffnen</button>` : ""}${lastRun.drucken.length && window.printDocs ? ` <button class="btn sm" id="m72pr">Direkt drucken</button>` : ""}</div></div></div>` : ""}
      <div class="card" style="margin-top:14px;overflow:hidden"><div class="hd"><h3>Protokoll der Mahnläufe</h3></div><table class="t"><thead><tr><th>Zeit</th><th>Art</th><th class="r">Mahnungen</th><th class="r">E-Mail</th><th class="r">Druck</th><th class="r">Fehler</th></tr></thead>
        <tbody>${d.laeufe.map(l => `<tr class="click" data-m72l="${l.id}"><td>${dde(l.zeit.slice(0, 10))} ${esc(l.zeit.slice(11, 16))}</td><td>${esc(l.art)}</td><td class="r num">${l.anzahl}</td><td class="r num">${l.gesendet}</td><td class="r num">${l.gedruckt}</td><td class="r num">${l.fehler || ""}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Noch kein Mahnlauf.</td></tr>`}</tbody></table></div></div>`;
    bindCommon();
    $("#m72set").onclick = () => settings(d);
    $("#m72all").onchange = e => { showAll = e.target.checked; view(); };
    $$("[data-m72c]").forEach(c => c.onchange = () => { SEL[c.dataset.m72c].on = c.checked; view(); });
    $$("[data-m72s]").forEach(c => c.onchange = () => { SEL[c.dataset.m72s].stufe = +c.value; });
    $$("[data-m72m]").forEach(c => c.onchange = () => { SEL[c.dataset.m72m].senden = c.checked; });
    $$("[data-m72b]").forEach(c => c.onclick = async () => { if (!c.dataset.m72b) return;
      await api("/api/m72/b2b", {customer_id: +c.dataset.m72b, b2b: c.dataset.v === "1"}); view(); });
    $$("[data-m72l]").forEach(r => r.onclick = () => showLauf(+r.dataset.m72l));
    if ($("#m72op")) $("#m72op").onclick = () => api("/api/m72/open", {path: lastRun.sammel_pdf});
    if ($("#m72pr")) $("#m72pr").onclick = async () => { for (const id of lastRun.drucken) await api("/api/print/mahnung", {id}); toast("An den Drucker geschickt"); };
    $("#m72go").onclick = async () => {
      const items = chosen.map(r => ({id: r.id, stufe: SEL[r.id].stufe, senden: SEL[r.id].senden}));
      $("#m72go").disabled = true; toast(`${items.length} Mahnung(en) werden erstellt …`);
      const r = await api("/api/m72/run", {items, sammel: $("#m72sam").checked});
      if (r && r.ok) { lastRun = r; chosen.forEach(c => delete SEL[c.id]);
        toast(`${r.erstellt} Mahnung(en) erstellt, ${r.gesendet} per E-Mail`); await reload(); }
      view();
    };
  }
})();
