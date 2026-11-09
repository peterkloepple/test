// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m81_kassenbuch: Seite "Kassenbuch" (Finanzen)
// Kassen, Bar-Einnahmen/-Ausgaben, Einlage/Entnahme/Geldtransit, laufender Bestand, Zaehlprotokoll + Abschluss,
// Vorschlaege aus Rechnungen mit Zahlart Bar, Storno nach Abschluss, Excel/PDF.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m81 = '<rect x="2" y="6" width="20" height="13" rx="2"/><path d="M2 10h20"/><circle cx="12" cy="14.5" r="2"/>';
  const F = {kasse: 0, monat: ""};
  const LS = "pa_m81";
  try { Object.assign(F, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) {}
  const keep = () => { try { localStorage.setItem(LS, JSON.stringify(F)); } catch (e) {} };
  const curMonth = () => todayIso().slice(0, 7);

  EXT.nav.push({key: "m81kasse", label: "Kassenbuch", icon: "m81", section: "Finanzen",
    cnt: () => (S.m81 && S.m81.vorschlaege) ? String(S.m81.vorschlaege) : ""});
  EXT.views.m81kasse = view;

  function range(){
    const m = F.monat || curMonth();
    if (m === "alle") return {von: "", bis: ""};
    if (/^\d{4}$/.test(m)) return {von: m + "-01-01", bis: m + "-12-31"};
    const [y, mo] = m.split("-").map(Number);
    return {von: `${m}-01`, bis: isoLocal(new Date(y, mo, 0))};
  }
  function monthOpts(){
    const out = [], t = new Date();
    for (let i = 0; i < 24; i++) { const d = new Date(t.getFullYear(), t.getMonth() - i, 1); const k = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
      out.push([k, MONL[d.getMonth()] + " " + d.getFullYear()]); }
    [thisYear, thisYear - 1].forEach(y => out.push([String(y), "Jahr " + y]));
    out.push(["alle", "alle Buchungen"]);
    return out;
  }

  async function view(){
    const r = range();
    const d = await api(`/api/m81/data?kasse=${F.kasse || ""}&von=${r.von}&bis=${r.bis}`);
    if (!d) return;
    F.kasse = d.kasse_id || 0; keep();
    const L = d.liste, k = L.kasse;
    const acts = k ? expButtons("m81_kasse", {kasse: F.kasse, von: r.von, bis: r.bis}) +
      `<button class="btn" id="m81z" type="button">${ic("check")} Zählen &amp; Abschluss</button>
       <button class="btn" id="m81t" type="button">Einlage / Entnahme / Transit</button>
       <button class="btn" id="m81a" type="button">− Ausgabe</button>
       <button class="btn pri" id="m81e" type="button">${ic("plus")} Einnahme</button>` : "";
    $("#main").innerHTML = `<div class="page">${pageHead("Kassenbuch", "Bargeld: Einnahmen, Ausgaben, Bestand und Kassenabschluss", acts)}
      ${!d.kassen.length ? `<div class="card"><div class="bd"><div class="empty" style="padding:30px">Noch keine Kasse angelegt.<br><br>
          <button class="btn pri" id="m81nk" type="button">${ic("plus")} Kasse anlegen</button></div>
          <div class="small muted" style="max-width:640px;margin:0 auto 14px">Das Kassenbuch zeigt dein Bargeld. Einnahmen aus Rechnungen werden nur verknüpft, Barausgaben legen einen Beleg an –
          die Gewinnermittlung zählt jeden Betrag genau einmal.</div></div></div></div>` : `
      <div class="row" style="margin-bottom:12px;align-items:center;flex-wrap:wrap">
        <div class="chips" style="flex:none">${d.kassen.map(x => `<span class="chip ${x.id === F.kasse ? "on" : ""}" data-m81k="${x.id}">${esc(x.name)}${x.aktiv ? "" : " (inaktiv)"}</span>`).join("")}
          <span class="chip" id="m81nk" title="Weitere Kasse anlegen">+ Kasse</span><span class="chip" id="m81ek" title="Name, Anfangsbestand, DATEV-Konto">Kasse bearbeiten</span></div>
        <span class="sp" style="flex:1"></span>
        <select class="in" id="m81m" style="width:auto">${monthOpts().map(([v, l]) => `<option value="${v}" ${v === (F.monat || curMonth()) ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Bestand heute</div><div class="v" style="color:${d.bestand_heute < 0 ? "var(--bad,#c0392b)" : "inherit"}">${eur(d.bestand_heute)}</div><div class="s">${esc(k.name)}</div></div>
        <div class="card kpi"><div class="l">Zugänge</div><div class="v">${eur(L.ein)}</div><div class="s">Einnahmen, Einlagen, Transit</div></div>
        <div class="card kpi"><div class="l">Abgänge</div><div class="v">${eur(L.aus)}</div><div class="s">Anfang ${eur(L.anfang)} → Ende ${eur(L.ende)}</div></div>
        <div class="card kpi"><div class="l">Abgeschlossen bis</div><div class="v" style="font-size:18px">${d.abgeschlossen_bis ? dde(d.abgeschlossen_bis) : "–"}</div><div class="s">danach nur Storno</div></div></div>
      ${d.vorschlaege.length ? `<div class="card" style="margin-bottom:14px"><div class="hd"><h3>Barzahlungen aus Rechnungen übernehmen (${d.vorschlaege.length})</h3>
          <div class="act"><button class="btn sm pri" type="button" id="m81va">Alle übernehmen</button></div></div>
        <table class="t"><thead><tr><th>Datum</th><th>Rechnung</th><th>Kunde</th><th>Status</th><th class="r">Betrag</th><th></th></tr></thead><tbody>
        ${d.vorschlaege.map(v => `<tr><td>${dde(v.datum)}</td><td><b>${esc(v.nr)}</b></td><td>${esc(v.name)}</td><td><span class="badge ${v.status === "bezahlt" ? "ok" : "warn"}">${v.status === "bezahlt" ? "bezahlt" : "offen → wird bezahlt"}</span></td>
          <td class="r num">${eur(v.betrag)}</td><td class="r"><button class="btn sm" type="button" data-m81v="${v.invoice_id}">Übernehmen</button></td></tr>`).join("")}</tbody></table></div>` : ""}
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Nr.</th><th>Datum</th><th>Art</th><th>Text</th><th>Kategorie</th><th class="r">Einnahme</th><th class="r">Ausgabe</th><th class="r">Bestand</th><th style="width:150px"></th></tr></thead>
        <tbody>${L.anfang !== undefined ? `<tr class="muted"><td></td><td></td><td colspan="5"><i>Anfangsbestand${L.von && L.von > "0001" ? " zum " + dde(L.von) : ""}</i></td><td class="r num">${eur(L.anfang)}</td><td></td></tr>` : ""}
        ${L.rows.map(b => `<tr data-m81id="${b.id}" class="${b.storniert ? "muted" : ""}"><td><b>${b.nr}</b></td><td>${dde(b.datum)}</td>
          <td><span class="badge ${b.wert >= 0 ? "ok" : "bad"}">${esc(b.art_label)}</span>${b.storno_von ? ` <span class="badge">Storno</span>` : ""}${b.storniert ? ` <span class="badge">storniert</span>` : ""}</td>
          <td>${esc(b.text || "")}${b.inv_nr ? `<div class="small muted">Rechnung ${esc(b.inv_nr)}</div>` : b.beleg_id ? `<div class="small muted">Beleg${b.beleg_partner ? ": " + esc(b.beleg_partner) : ""}</div>` : ""}</td>
          <td class="small">${esc(b.kategorie || "")}</td>
          <td class="r num">${b.wert > 0 ? eur(b.wert) : ""}</td><td class="r num">${b.wert < 0 ? eur(-b.wert) : ""}</td>
          <td class="r num" style="${b.negativ ? "color:var(--bad,#c0392b);font-weight:700" : ""}">${eur(b.bestand)}</td>
          <td class="r" style="white-space:nowrap">${b.gesperrt ? `<span class="small muted" title="abgeschlossen">🔒</span>` : ""}
            ${!b.storno_von && !b.storniert ? `<button class="btn sm ghost" type="button" data-m81s="${b.id}" title="Gegenbuchung erzeugen">Storno</button>` : ""}
            ${!b.gesperrt ? `<button class="btn sm ghost danger" type="button" data-m81d="${b.id}" title="Löschen">${ic("trash")}</button>` : ""}</td></tr>`).join("")
          || `<tr><td colspan="9" class="empty">Keine Buchungen im Zeitraum.</td></tr>`}</tbody></table></div>
      ${d.abschluesse.length ? `<div class="card" style="margin-top:14px"><div class="hd"><h3>Abschlüsse &amp; Zählprotokolle</h3></div>
        <table class="t"><thead><tr><th>Bis</th><th>Art</th><th class="r">Soll</th><th class="r">Gezählt</th><th class="r">Differenz</th><th>Notiz</th></tr></thead><tbody>
        ${d.abschluesse.map(a => `<tr><td>${dde(a.bis)}</td><td>${a.art === "monat" ? "Monat" : "Tag"}</td><td class="r num">${eur(a.soll)}</td><td class="r num">${a.ist === null ? "–" : eur(a.ist)}</td>
          <td class="r num" style="${Math.abs(a.differenz) > 0.004 ? "color:var(--warn)" : ""}">${eur(a.differenz)}</td><td class="small">${esc(a.notiz || "")}</td></tr>`).join("")}</tbody></table></div>` : ""}
      <div class="small muted" style="margin-top:10px">Einnahmen aus Rechnungen werden nur verknüpft (die Rechnung zählt in der EÜR), Barausgaben und sonstige Bareinnahmen legen einen Beleg an.
        Einlage, Entnahme und Geldtransit wirken nicht auf den Gewinn.</div>`}</div>`;
    bindCommon();
    const nk = $("#m81nk"); if (nk) nk.onclick = () => kasseDlg(null);
    if (!k) return;
    $("#m81ek").onclick = () => kasseDlg(k);
    $$("[data-m81k]").forEach(c => c.onclick = () => { F.kasse = +c.dataset.m81k; keep(); view(); });
    $("#m81m").onchange = e => { F.monat = e.target.value; keep(); view(); };
    $("#m81e").onclick = () => buchDlg("einnahme", d);
    $("#m81a").onclick = () => buchDlg("ausgabe", d);
    $("#m81t").onclick = () => buchDlg("einlage", d);
    $("#m81z").onclick = () => zaehlDlg(d);
    const va = $("#m81va"); if (va) va.onclick = () => uebernehmen(d.vorschlaege.map(v => v.invoice_id));
    $$("[data-m81v]").forEach(b => b.onclick = () => uebernehmen([+b.dataset.m81v]));
    $$("[data-m81d]").forEach(b => b.onclick = async () => { const r = await api("/api/m81/del", {id: +b.dataset.m81d}); if (r && r.ok) { toast("Buchung gelöscht"); await reload(); view(); } });
    $$("[data-m81s]").forEach(b => b.onclick = async () => { const r = await api("/api/m81/storno", {id: +b.dataset.m81s}); if (r && r.ok) { toast(`Storno als Nr. ${r.nr} gebucht`); await reload(); view(); } });
    selectify({kind: "m81", rows: "tr[data-m81id]", id: "data-m81id", rerender: view, actions: [
      {label: "Excel", run: async ids => { await doExport("m81_kasse", "xlsx", {kasse: F.kasse, ids}); return false; }},
      {label: "PDF", run: async ids => { await doExport("m81_kasse", "pdf", {kasse: F.kasse, ids}); return false; }}]});
  }

  async function uebernehmen(ids){
    const r = await api("/api/m81/uebernehmen", {kasse_id: F.kasse, ids});
    if (r && r.ok) { toast(`${r.n} Barzahlung(en) übernommen`); if (r.warn) toast(r.warn, true); await reload(); view(); }
  }

  async function kasseDlg(k){
    const n = !k; k = k || {name: "Hauptkasse", anfang: 0, anfang_datum: todayIso(), aktiv: 1};
    await modal(n ? "Kasse anlegen" : "Kasse bearbeiten", `<div class="fr">
      <label class="f">Name<input class="in" id="m81kn" value="${esc(k.name)}"></label>
      <div class="row"><label class="f">Anfangsbestand €<input class="in num" id="m81ka" value="${nde(k.anfang || 0)}"></label>
        <label class="f">am<input type="date" class="in" id="m81kd" value="${esc(k.anfang_datum || todayIso())}"></label></div>
      <div class="row"><label class="f">DATEV-Kassenkonto (leer = Standard)<input class="in num" id="m81kk" value="${k.konto || ""}" placeholder="1000 / 1600"></label>
        ${n ? "" : `<label class="chk" style="flex:none;align-self:flex-end;margin-bottom:8px"><input type="checkbox" id="m81kak" ${k.aktiv ? "checked" : ""}> aktiv</label>`}</div>
      <label class="f">Notiz<input class="in" id="m81kno" value="${esc(k.notiz || "")}"></label>
      <div class="small muted">Anfangsbestand = gezähltes Bargeld am Starttag. Nach dem ersten Abschluss nicht mehr änderbar.</div></div>`,
      [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
        const r = await api("/api/m81/kasse", {id: k.id || null, name: $("#m81kn", mb).value, anfang: pnum($("#m81ka", mb).value), anfang_datum: $("#m81kd", mb).value,
          konto: $("#m81kk", mb).value, aktiv: n ? 1 : ($("#m81kak", mb).checked ? 1 : 0), notiz: $("#m81kno", mb).value});
        if (!r || !r.ok) return false;
        F.kasse = r.id; keep(); await reload(); view(); }}]);
  }

  async function buchDlg(art, d){
    const transit = !["einnahme", "ausgabe"].includes(art);
    const bel = art === "ausgabe" || art === "einnahme" ? await api("/api/m81/belege", undefined, {quiet:true}) : {rows: []};
    const belege = (bel && bel.rows || []).filter(b => b.typ === art);
    const arten = transit ? [["einlage", "Privateinlage (Geld in die Kasse)"], ["entnahme", "Privatentnahme (Geld aus der Kasse)"],
      ["bank_kasse", "Geldtransit Bank → Kasse (abgehoben)"], ["kasse_bank", "Geldtransit Kasse → Bank (eingezahlt)"]] : [];
    const kats = art === "ausgabe" ? d.kategorien : [];
    const html = `<div class="fr">
      ${transit ? `<label class="f">Art<select class="in" id="m81art">${arten.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></label>` : ""}
      <div class="row"><label class="f">Datum<input type="date" class="in" id="m81d" value="${todayIso()}"></label>
        <label class="f">Betrag €<input class="in num" id="m81b" placeholder="0,00"></label></div>
      ${belege.length ? `<label class="f">Vorhandenen Beleg verknüpfen (optional)<select class="in" id="m81bel"><option value="">– neuer Eintrag –</option>
        ${belege.map(b => `<option value="${b.id}" data-b="${b.betrag}" data-dt="${b.datum}">${dde(b.datum)} · ${esc(b.partner || "")} ${esc(b.nr || "")} · ${eur(b.betrag)}</option>`).join("")}</select></label>` : ""}
      <label class="f">Text<input class="in" id="m81tx" placeholder="${art === "ausgabe" ? "z. B. Briefmarken Post" : art === "einnahme" ? "z. B. Barverkauf Kabel" : "z. B. Wechselgeld"}"></label>
      ${art === "ausgabe" ? `<div class="row"><label class="f">Kategorie (EÜR)<select class="in" id="m81kat">${kats.map(c => `<option ${c === "Bürobedarf / Porto" ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
        <label class="f" style="flex:.6">Beleg-Nr.<input class="in" id="m81bn"></label></div>` : ""}
      ${art === "einnahme" ? `<div class="small muted">Für Barzahlungen von Rechnungen die Vorschläge auf der Seite nutzen – dann zählt die Rechnung.</div>` : ""}
      ${art === "ausgabe" ? `<div class="small muted">Ohne verknüpften Beleg legt das Programm einen Beleg in „Belege“ an (Kategorie für die EÜR). Beleg-PDF dort nachträglich anhängen.</div>` : ""}</div>`;
    await modal(transit ? "Einlage / Entnahme / Geldtransit" : art === "einnahme" ? "Bareinnahme" : "Barausgabe", html,
      [{label: "Abbrechen"}, {label: "Buchen", cls: "pri", onClick: async mb => {
        const bsel = $("#m81bel", mb);
        const r = await api("/api/m81/buchen", {kasse_id: F.kasse, art: transit ? $("#m81art", mb).value : art, datum: $("#m81d", mb).value,
          betrag: pnum($("#m81b", mb).value), text: $("#m81tx", mb).value, kategorie: $("#m81kat", mb) ? $("#m81kat", mb).value : "",
          belegnr: $("#m81bn", mb) ? $("#m81bn", mb).value : "", beleg_id: bsel && bsel.value ? +bsel.value : null});
        if (!r || !r.ok) return false;
        toast(`Gebucht als Nr. ${r.nr} · Bestand ${eur(r.bestand)}`); if (r.warn) toast(r.warn, true);
        await reload(); view(); }}],
      false, mb => { const bsel = $("#m81bel", mb); if (bsel) bsel.onchange = () => { const o = bsel.selectedOptions[0];
        if (o && o.dataset.b) { $("#m81b", mb).value = nde(+o.dataset.b); $("#m81d", mb).value = o.dataset.dt; } }; });
  }

  async function zaehlDlg(d){
    const st = d.stuecke;
    const html = `<div class="fr"><div class="row"><label class="f">Abschluss bis einschließlich<input type="date" class="in" id="m81zb" value="${todayIso()}"></label>
        <label class="f">Art<select class="in" id="m81za"><option value="tag">Tagesabschluss</option><option value="monat">Monatsabschluss</option></select></label></div>
      <div class="small muted" style="margin-bottom:6px">Zählprotokoll: Anzahl je Schein / Münze eintragen (leer lassen = nicht gezählt).</div>
      <div class="grid" style="grid-template-columns:repeat(5,1fr);gap:6px">${st.map(v => `<label class="f" style="margin:0">${v >= 5 ? v + " €" : v >= 1 ? v + " €" : Math.round(v * 100) + " ct"}
        <input class="in num" data-m81st="${v}" placeholder="0"></label>`).join("")}</div>
      <div class="kv small" style="margin-top:10px"><span class="sub">Gezählt</span><span class="r"><b id="m81zs">–</b></span>
        <span class="sub">Soll laut Kassenbuch (heute)</span><span class="r">${eur(d.bestand_heute)}</span>
        <span class="sub">Differenz</span><span class="r" id="m81zd">–</span></div>
      <label class="chk"><input type="checkbox" id="m81zdb" checked> Differenz als „Kassendifferenz“ buchen</label>
      <label class="f">Notiz<input class="in" id="m81zn" placeholder="z. B. gezählt von T. Pfeiffer"></label>
      <div class="alert warn" style="cursor:default;font-size:12.5px">${ic("alert")}<span>Nach dem Abschluss sind alle Buchungen bis zu diesem Tag festgeschrieben – Korrekturen nur noch als Storno.</span></div></div>`;
    await modal("Kasse zählen & abschließen", html, [{label: "Abbrechen"}, {label: "Abschließen", cls: "pri", onClick: async mb => {
      const zaehl = {}; let any = false;
      $$("[data-m81st]", mb).forEach(i => { if (i.value.trim() !== "") { zaehl[i.dataset.m81st] = Math.round(pnum(i.value)); any = true; } });
      const r = await api("/api/m81/abschluss", {kasse_id: F.kasse, bis: $("#m81zb", mb).value, art: $("#m81za", mb).value, zaehl: any ? zaehl : null,
        differenz_buchen: $("#m81zdb", mb).checked, notiz: $("#m81zn", mb).value});
      if (!r || !r.ok) return false;
      toast(`Abgeschlossen: ${r.buchungen} Buchungen · Soll ${eur(r.soll)}${r.ist !== null ? " · gezählt " + eur(r.ist) : ""}`); if (r.warn) toast(r.warn, true);
      await reload(); view(); }}], false, mb => {
      const upd = () => { let s = 0, any = false; $$("[data-m81st]", mb).forEach(i => { if (i.value.trim() !== "") { any = true; s += pnum(i.dataset.m81st) * Math.round(pnum(i.value)); } });
        $("#m81zs", mb).textContent = any ? eur(s) : "–"; $("#m81zd", mb).textContent = any ? eur(Math.round((s - d.bestand_heute) * 100) / 100) : "–"; };
      $$("[data-m81st]", mb).forEach(i => i.oninput = upd); });
  }
})();
