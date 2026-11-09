// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m79_datev: DATEV-Export, Ausfuellhilfe Anlage EUER / Anlage N
// Karten in "Jahresabrechnung & Steuer" (vTax) + Einstellungs-Reiter "DATEV & Formulare".
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const LS = "pa_m79_zr";
  const lsGet = () => { try { return JSON.parse(localStorage.getItem(LS) || "{}"); } catch (e) { return {}; } };
  const lsSet = v => { try { localStorage.setItem(LS, JSON.stringify(v)); } catch (e) {} };

  // ------------------------------------------------------------------ Ausfuellhilfe (vTax)
  async function fillAusfuell(card, y){
    const a = await api("/api/m79/ausfuell?year=" + y, undefined, {quiet:true});
    if (!a || !a.euer) { card.remove(); return; }
    const n = a.anlage_n;
    const copyBtn = (t) => `<button class="btn sm ghost" type="button" data-m79cp="${esc(t)}" title="Betrag kopieren">${ic("copy")}</button>`;
    card.innerHTML = `<div class="hd"><h3>Ausfüllhilfe Steuererklärung ${y}</h3><div class="act">${expButtons("m79_ausfuell", {year:y}, true)}
        <button class="btn sm" type="button" id="m79zl">Zeilen anpassen</button></div></div>
      <div class="bd">
        <div class="alert" style="cursor:default;margin-bottom:10px;font-size:12.5px">${ic("alert")}<span>${esc(a.hinweis)} <b>Tabelle: ${esc(a.quelle)}</b></span></div>
        <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:16px">
          <div><h4 style="margin:0 0 6px">Anlage EÜR</h4>
            <table class="t"><thead><tr><th>Zeile</th><th>Kz</th><th>Bezeichnung</th><th class="r">Betrag</th><th></th></tr></thead>
            <tbody>${a.euer.map(r => `<tr><td><b>${r.zeile}</b></td><td class="muted">${r.kz}</td><td>${esc(r.label)}</td><td class="r num">${eur(r.betrag)}</td><td class="r">${copyBtn(nde(r.betrag))}</td></tr>`).join("")}</tbody></table></div>
          <div><h4 style="margin:0 0 6px">Anlage N (aus Gehaltsabrechnungen)</h4>
            <table class="t"><thead><tr><th>Nr. LStB</th><th>Bezeichnung</th><th class="r">Betrag</th><th></th></tr></thead>
            <tbody>${n.lstb.map(r => `<tr><td><b>${esc(r.nr)}</b></td><td>${esc(r.label)}</td><td class="r num">${eur(r.betrag)}</td><td class="r">${copyBtn(nde(r.betrag))}</td></tr>`).join("")}</tbody></table>
            <h4 style="margin:12px 0 6px">Werbungskosten</h4>
            <table class="t"><tbody>${n.werbungskosten.map(w => `<tr><td>${esc(w.label)}<div class="small muted">${esc(w.info || "")}</div></td><td class="r num">${eur(w.betrag)}</td></tr>`).join("")}
              <tr><td><b>Summe</b> <span class="small muted">(Pauschale ${eur(n.wk_pauschale)})</span></td><td class="r num"><b>${eur(n.wk_summe)}</b>
                <div class="small ${n.wk_wirkt ? "" : "muted"}">${n.wk_wirkt ? "liegt über der Pauschale – eintragen" : "unter der Pauschale"}</div></td></tr></tbody></table>
            <div class="small muted" style="margin-top:6px">${esc(n.hinweis)}</div></div>
        </div></div>`;
    $$("[data-m79cp]", card).forEach(b => b.onclick = () => { try { navigator.clipboard.writeText(b.dataset.m79cp); toast("Kopiert: " + b.dataset.m79cp); } catch (e) {} });
    $("#m79zl", card).onclick = () => zeilenDialog(y, () => fillAusfuell(card, y));
  }

  async function zeilenDialog(y, after){
    const z = await api("/api/m79/zeilen?year=" + y);
    if (!z || !z.rows) return;
    const html = `<div class="small muted" style="margin-bottom:8px">${esc(z.hinweis)}</div>
      <table class="t"><thead><tr><th>Bereich im Programm</th><th style="width:80px">Zeile</th><th style="width:80px">Kz</th><th>Bezeichnung im Vordruck</th></tr></thead>
      <tbody>${z.rows.map(r => `<tr data-k="${esc(r.key)}"><td>${esc(r.name)}${r.eigen ? ` <span class="badge acc">eigen</span>` : ""}</td>
        <td><input class="in num" data-f="zeile" value="${r.zeile}"></td><td><input class="in num" data-f="kz" value="${r.kz}"></td>
        <td><input class="in" data-f="label" value="${esc(r.label)}"></td></tr>`).join("")}</tbody></table>`;
    await modal(`Zeilen der Anlage EÜR ${y}`, html, [{label:"Abbrechen"},
      {label:"Auf Standard zurücksetzen", cls:"ghost", onClick: async () => { const r = await api("/api/m79/zeilen", {year:y, reset:true}); if (r && r.ok) { toast("Standard-Zeilen wiederhergestellt"); if (after) after(); } }},
      {label:"Speichern", cls:"pri", onClick: async mb => {
        const rows = $$("tr[data-k]", mb).map(tr => ({key: tr.dataset.k, zeile: $("[data-f=zeile]", tr).value, kz: $("[data-f=kz]", tr).value, label: $("[data-f=label]", tr).value}));
        const r = await api("/api/m79/zeilen", {year:y, rows});
        if (!r || !r.ok) return false;
        toast("Zeilen für " + y + " gespeichert"); if (after) after(); }}], true);
  }

  // ------------------------------------------------------------------ DATEV (vTax)
  function fillDatev(card, y){
    const zr = lsGet();
    const von = zr.y === y && zr.von ? zr.von : `${y}-01-01`, bis = zr.y === y && zr.bis ? zr.bis : `${y}-12-31`;
    card.innerHTML = `<div class="hd"><h3>DATEV-Export für den Steuerberater</h3><div class="act"><button class="btn sm ghost" type="button" data-go="set" id="m79set">Einstellungen</button></div></div>
      <div class="bd">
        <div class="small muted" style="margin-bottom:8px">Buchungsstapel im DATEV-Format (EXTF) mit allen bezahlten Rechnungen, Belegen, Kassenbuchungen und Fahrten im Zeitraum,
          dazu die Belegdateien als ZIP. Kontenrahmen und Konten unter Einstellungen → DATEV &amp; Formulare.</div>
        <div class="row" style="align-items:flex-end;flex-wrap:wrap">
          <label class="f" style="flex:none">Von<input type="date" class="in nokeep" id="m79von" value="${von}"></label>
          <label class="f" style="flex:none">Bis<input type="date" class="in nokeep" id="m79bis" value="${bis}"></label>
          <div class="seg" style="flex:none;margin-bottom:8px">${[["j","Jahr"],["q1","Q1"],["q2","Q2"],["q3","Q3"],["q4","Q4"]].map(([k,l]) => `<button type="button" data-m79q="${k}">${l}</button>`).join("")}</div>
          <label class="chk" style="flex:none;margin-bottom:8px"><input type="checkbox" class="nokeep" id="m79bel" checked> Belegdateien mitgeben</label>
          <span class="sp" style="flex:1"></span>
          <button class="btn" type="button" id="m79pv" style="flex:none;margin-bottom:8px">${ic("eye")} Vorschau</button>
          <button class="btn pri" type="button" id="m79ex" style="flex:none;margin-bottom:8px">${ic("up")} DATEV-Export erstellen</button></div>
        <div id="m79out"></div></div>`;
    const save = () => lsSet({y, von: $("#m79von", card).value, bis: $("#m79bis", card).value});
    $("#m79von", card).onchange = save; $("#m79bis", card).onchange = save;
    $$("[data-m79q]", card).forEach(b => b.onclick = () => {
      const k = b.dataset.m79q; let a = `${y}-01-01`, e = `${y}-12-31`;
      if (k !== "j") { const qn = +k.slice(1); a = `${y}-${String(qn * 3 - 2).padStart(2, "0")}-01`; e = new Date(y, qn * 3, 0); e = isoLocal(e); }
      $("#m79von", card).value = a; $("#m79bis", card).value = e; save(); });
    $("#m79pv", card).onclick = async () => {
      const v = $("#m79von", card).value, b = $("#m79bis", card).value;
      const r = await api(`/api/m79/preview?von=${v}&bis=${b}`);
      if (!r || !r.ok) return;
      $("#m79out", card).innerHTML = `<div class="small muted" style="margin:8px 0">${r.n} Buchungen · SKR${esc(r.skr)} · Soll ${eur(r.soll)} / Haben ${eur(r.haben)}
          ${r.n > r.rows.length ? ` · Vorschau zeigt die ersten ${r.rows.length}` : ""} <span style="margin-left:8px">${expButtons("m79_datev", {von:v, bis:b}, true)}</span></div>
        <div style="max-height:360px;overflow:auto"><table class="t"><thead><tr><th>Datum</th><th class="r">Umsatz</th><th>S/H</th><th>Konto</th><th>Gegenkonto</th><th>BU</th><th>Belegfeld 1</th><th>Buchungstext</th><th>Quelle</th></tr></thead>
        <tbody>${r.rows.map(x => `<tr><td>${dde(x.datum)}</td><td class="r num">${eur(x.betrag)}</td><td>${x.sh}</td><td>${x.konto}</td><td>${x.gegen}</td><td>${esc(x.bu)}</td><td>${esc(x.beleg)}</td><td>${esc(x.text)}</td><td class="small muted">${esc(x.quelle)}</td></tr>`).join("")
          || `<tr><td colspan="9" class="empty">Keine Buchungen im Zeitraum.</td></tr>`}</tbody></table></div>`;
    };
    $("#m79ex", card).onclick = async () => {
      toast("DATEV-Export wird erstellt …");
      const r = await api("/api/m79/export", {von: $("#m79von", card).value, bis: $("#m79bis", card).value, belege: $("#m79bel", card).checked});
      if (!r || !r.ok) return;
      toast(`DATEV-Export: ${r.buchungen} Buchungen, ${r.belege} Belege – ${r.path.split(/[\\/]/).pop()}`);
      (r.warn || []).forEach(w => toast(w, true));
    };
    bindCommon(card);
  }

  EXT.after.push(async n => {
    if (n !== "vTax") return;
    const page = $("#main .page"); if (!page || $("#m79aus", page)) return;
    const y = typeof txYear !== "undefined" ? txYear : new Date().getFullYear();
    const c1 = document.createElement("div"); c1.className = "card"; c1.id = "m79aus"; c1.style.marginTop = "16px";
    c1.innerHTML = `<div class="hd"><h3>Ausfüllhilfe Steuererklärung ${y}</h3></div><div class="bd small muted">Lädt …</div>`;
    const c2 = document.createElement("div"); c2.className = "card"; c2.id = "m79dv"; c2.style.marginTop = "16px";
    page.appendChild(c1); page.appendChild(c2);
    fillAusfuell(c1, y); fillDatev(c2, y);
  });

  // ------------------------------------------------------------------ Einstellungen
  EXT.settings.push({key:"m79", label:"DATEV & Formulare", async render(el){
    const d = await api("/api/m79/cfg");
    if (!d || !d.cfg) return;
    const c = d.cfg;
    el.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>DATEV-Export</h3></div><div class="bd fr">
      <div class="small muted" style="margin-bottom:8px">Die Angaben bekommst du vom Steuerberater. Die Kontenzuordnung ist ein Vorschlag nach SKR03 bzw. SKR04 – bitte einmal mit dem Steuerberater abstimmen.</div>
      <div class="row"><label class="f">Beraternummer<input class="in num" id="m79b" value="${c.berater || ""}" placeholder="z. B. 1234567"></label>
        <label class="f">Mandantennummer<input class="in num" id="m79m" value="${c.mandant || ""}" placeholder="z. B. 10001"></label>
        <label class="f">Kontenrahmen<select class="in" id="m79skr"><option value="03" ${c.skr === "03" ? "selected" : ""}>SKR03</option><option value="04" ${c.skr === "04" ? "selected" : ""}>SKR04</option></select></label></div>
      <div class="row"><label class="f">Wirtschaftsjahr-Beginn (MM-TT)<input class="in" id="m79wj" value="${esc(c.wj_beginn || "01-01")}"></label>
        <label class="f">Sachkontenlänge<select class="in" id="m79kl">${[4,5,6,7,8].map(v => `<option ${+c.kontenlaenge === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label class="f">Diktatkürzel (2 Buchstaben)<input class="in" id="m79kz" value="${esc(c.kuerzel || "")}" maxlength="2"></label></div>
      <div class="row" style="flex-wrap:wrap;gap:14px">
        <label class="chk" style="flex:none"><input type="checkbox" id="m79deb" ${c.debitoren ? "checked" : ""}> Debitoren (10000 + Kunden-ID)</label>
        <label class="chk" style="flex:none"><input type="checkbox" id="m79kre" ${c.kreditoren ? "checked" : ""}> Kreditoren (ab 70001 je Lieferant)</label>
        <label class="chk" style="flex:none"><input type="checkbox" id="m79km" ${c.km_buchen ? "checked" : ""}> Fahrten mit Privat-Pkw als Einlage buchen</label>
        <label class="chk" style="flex:none"><input type="checkbox" id="m79fs" ${c.festschreibung ? "checked" : ""}> Stapel beim Import festschreiben</label></div>
      <h4 style="margin:14px 0 6px">Konten</h4>
      <div style="max-height:420px;overflow:auto"><table class="t"><thead><tr><th>Kategorie / Zweck</th><th style="width:120px">Konto</th><th class="r">Standard</th></tr></thead>
        <tbody>${d.konten.map(k => `<tr><td>${esc(k.name)}</td><td><input class="in num" data-m79k="${esc(k.key)}" value="${k.konto}"></td>
          <td class="r small muted">${k.standard ?? "–"}${k.eigen ? ` <span class="badge acc">geändert</span>` : ""}</td></tr>`).join("")}</tbody></table></div>
      <div class="row" style="margin-top:12px"><span class="sp"></span><button class="btn pri" id="m79sv" style="flex:none">${ic("save")} Speichern</button></div>
    </div></div>
    <div class="card" style="margin-top:16px"><div class="hd"><h3>Anlage EÜR – Zeilennummern</h3></div><div class="bd">
      <div class="small muted" style="margin-bottom:8px">Die Zeilennummern im Vordruck können sich jedes Jahr ändern. Hier je Jahr anpassen, die Ausfüllhilfe übernimmt sie.</div>
      <div class="row" style="align-items:flex-end"><label class="f" style="flex:none">Jahr${yearSel("m79zy", thisYear)}</label>
        <button class="btn" type="button" id="m79zb" style="flex:none;margin-bottom:8px">Zeilen bearbeiten …</button></div></div></div>`;
    $("#m79zb", el).onclick = () => zeilenDialog(+$("#m79zy", el).value);
    $("#m79sv", el).onclick = async () => {
      const konten = {}; $$("[data-m79k]", el).forEach(i => konten[i.dataset.m79k] = i.value.trim());
      const skr = $("#m79skr", el).value;
      const r = await api("/api/m79/cfg", {berater: $("#m79b", el).value, mandant: $("#m79m", el).value, skr, wj_beginn: $("#m79wj", el).value,
        kontenlaenge: $("#m79kl", el).value, kuerzel: $("#m79kz", el).value, debitoren: $("#m79deb", el).checked, kreditoren: $("#m79kre", el).checked,
        km_buchen: $("#m79km", el).checked, festschreibung: $("#m79fs", el).checked, konten: skr === d.cfg.skr ? konten : {}});
      if (r && r.cfg) { toast("DATEV-Einstellungen gespeichert"); if (skr !== d.cfg.skr) this.render(el); }
    };
  }});
})();
