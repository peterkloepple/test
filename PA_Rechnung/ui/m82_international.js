// PA Rechnung v2.0.19 - UI-Modul m82_international: englische Dokumente und Fremdwaehrung
// Editor: Sprache / Waehrung / Kurs je Dokument; Kunde: Vorgabe Sprache + Waehrung;
// Bausteine: englischer Name/Text; Einstellungen: englische Standardtexte, Beschriftungen, Liste.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m82 = '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.8 3.8 5.8 3.8 9s-1.3 6.2-3.8 9c-2.5-2.8-3.8-5.8-3.8-9S9.5 5.8 12 3z"/>';
  const M = () => S.m82 || {kunden:{}, artikel:{}, langs:{de:"Deutsch", en:"English"}, curs:["EUR"], texte_en:{}};
  const pv = () => { try { schedulePreview(0); } catch (e) {} };
  const kdef = cid => (M().kunden || {})[String(cid)] || {sprache:"de", waehrung:"EUR"};
  const norm = s => String(s || "").replace(/\s+/g, " ").trim();

  async function fetchKurs(cur, force){
    if (!cur || cur === "EUR") return {ok:true, kurs:1, datum:todayIso(), quelle:""};
    return api(`/api/m82/kurs?w=${encodeURIComponent(cur)}${force ? "&force=1" : ""}`, undefined, {quiet:true});
  }

  // German default texts -> English ones (only when untouched)
  function swapTexts(){
    if (!cur) return false;
    const t = M().texte_en || {}, s = S.settings || {}, typ = cur.typ || "rechnung";
    const deTop = [s.default_top, s.default_top_angebot, s.default_top_auftrag, ...(S.texts || []).filter(x_ => x_.kind === "top").map(x_ => x_.text)].map(norm);
    const deFoot = [s.default_foot, s.default_foot_angebot, s.default_foot_auftrag, ...(S.texts || []).filter(x_ => x_.kind === "foot").map(x_ => x_.text)].map(norm);
    let ch = false;
    if (t["top_" + typ] && (!cur.toptext || deTop.includes(norm(cur.toptext)))) { cur.toptext = t["top_" + typ]; ch = true; }
    if (t["foot_" + typ] && (!cur.foottext || deFoot.includes(norm(cur.foottext)))) { cur.foottext = t["foot_" + typ]; ch = true; }
    if (cur.titel && {"Rechnung":"Invoice", "Angebot":"Quotation", "Auftragsbestätigung":"Order confirmation", "Storno-Rechnung":"Cancellation invoice"}[cur.titel]) {
      cur.titel = {"Rechnung":"Invoice", "Angebot":"Quotation", "Auftragsbestätigung":"Order confirmation", "Storno-Rechnung":"Cancellation invoice"}[cur.titel]; ch = true; }
    return ch;
  }

  // new document: take language + currency from the customer
  const _setCustomer = window.setCustomer;
  if (typeof _setCustomer === "function") {
    window.setCustomer = function(id){
      const r = _setCustomer.apply(this, arguments);
      try {
        if (cur && !cur.id && !["brief", "vorlage"].includes(cur.typ)) {
          const k = kdef(id);
          if (k.sprache !== "de" || k.waehrung !== "EUR") {
            cur.m82 = {sprache:k.sprache, waehrung:k.waehrung, kurs:1, kurs_datum:"", kurs_quelle:""};
            if (k.sprache === "en") swapTexts();
            if (k.waehrung !== "EUR") fetchKurs(k.waehrung).then(kr => { if (kr && kr.ok && cur && cur.m82 && cur.m82.waehrung === k.waehrung) {
              Object.assign(cur.m82, {kurs:kr.kurs, kurs_datum:kr.datum, kurs_quelle:kr.quelle}); if (view === "editor") { const e = $("#m82k"); if (e) e.value = nde(kr.kurs, 4); pv(); } } });
          } else if (cur.m82 && !cur.id) cur.m82 = null;
        }
      } catch (e) { console.error(e); }
      return r;
    };
  }

  // ---------- editor ----------
  EXT.after.push(n => {
    if (n !== "vEditor" || !cur || ["brief", "vorlage"].includes(cur.typ) || $("#m82row")) return;
    const t = $("#titel"); if (!t) return;
    let anchor = t.closest(".row"); const fr = $("#ifont"); if (fr && fr.closest(".row")) anchor = fr.closest(".row");
    if (!anchor) return;
    const m = cur.m82 || {sprache:"de", waehrung:"EUR", kurs:1};
    const dis = cur.locked ? "disabled" : "";
    const curs = [...new Set([...(M().curs || ["EUR"]), m.waehrung || "EUR"])];
    const row = document.createElement("div"); row.className = "row"; row.id = "m82row"; row.style.alignItems = "flex-end";
    row.innerHTML = `<label class="f" style="flex:.6">Sprache<select class="in" id="m82l" ${dis}>${Object.entries(M().langs || {}).map(([k, l]) => `<option value="${k}" ${m.sprache === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      <label class="f" style="flex:.5">Währung<select class="in" id="m82w" ${dis}>${curs.map(c => `<option ${m.waehrung === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
      <label class="f" style="flex:.6" id="m82kl">Kurs (1 EUR =)<input class="in num" id="m82k" ${dis} value="${nde(m.kurs || 1, 4)}" title="${m.kurs_quelle === "EZB" ? "EZB-Referenzkurs vom " + dde(m.kurs_datum) : "von Hand eingetragen"}"></label>
      <button class="btn sm" type="button" id="m82e" style="flex:none;margin-bottom:6px" ${dis} title="EZB-Referenzkurs von heute holen">EZB-Kurs</button>
      <button class="btn sm ghost" type="button" id="m82t" style="flex:none;margin-bottom:6px" ${dis} title="Deutsche Standardtexte durch die englischen ersetzen">EN-Texte</button>`;
    anchor.after(row);
    const sync = () => { const fw = $("#m82w").value !== "EUR"; $("#m82kl").style.display = fw ? "" : "none"; $("#m82e").style.display = fw ? "" : "none";
      $("#m82t").style.display = $("#m82l").value === "en" ? "" : "none"; };
    sync();
    if (cur.locked) return;
    const put = () => { cur.m82 = Object.assign({}, cur.m82 || {}, {sprache:$("#m82l").value, waehrung:$("#m82w").value, kurs:pnum($("#m82k").value) || 1}); pv(); };
    $("#m82l").onchange = () => { put(); if ($("#m82l").value === "en" && swapTexts()) { toast("Englische Standardtexte übernommen"); vEditor(); return; } sync(); };
    $("#m82w").onchange = async () => { put(); sync(); if ($("#m82w").value !== "EUR") { const kr = await fetchKurs($("#m82w").value);
      if (kr && kr.ok) { $("#m82k").value = nde(kr.kurs, 4); Object.assign(cur.m82, {kurs:kr.kurs, kurs_datum:kr.datum, kurs_quelle:kr.quelle}); if (kr.warnung) toast(kr.warnung, true); pv(); }
      else toast((kr && kr.error) || "Kurs nicht abrufbar – bitte von Hand eintragen", true); } };
    $("#m82k").onchange = () => { put(); cur.m82.kurs_quelle = "manuell"; cur.m82.kurs_datum = cur.datum || todayIso(); };
    $("#m82e").onclick = async () => { const kr = await fetchKurs($("#m82w").value, true);
      if (kr && kr.ok) { $("#m82k").value = nde(kr.kurs, 4); put(); Object.assign(cur.m82, {kurs:kr.kurs, kurs_datum:kr.datum, kurs_quelle:kr.quelle}); toast(`EZB-Kurs ${dde(kr.datum)}: 1 EUR = ${nde(kr.kurs, 4)} ${$("#m82w").value}`); }
      else toast((kr && kr.error) || "EZB nicht erreichbar", true); };
    $("#m82t").onclick = () => { if (swapTexts()) { toast("Englische Standardtexte übernommen"); vEditor(); } else toast("Texte sind schon geändert – bitte von Hand anpassen"); };
  });

  // ---------- customer: default language + currency ----------
  EXT.after.push(n => {
    if (n !== "vCustomers" || $("#m82cust")) return;
    const ed = $("#cedit"); if (!ed || typeof custSel === "undefined" || !custSel) return;
    const card = ed.closest(".card"); if (!card) return;
    const k = kdef(custSel);
    const el = document.createElement("div"); el.className = "card"; el.id = "m82cust"; el.style.marginBottom = "16px";
    el.innerHTML = `<div class="bd row" style="align-items:center;flex-wrap:wrap;gap:10px">${ic("m82")}<b style="flex:none">Dokumente für diesen Kunden</b>
      <label class="f" style="flex:none;width:160px;margin:0">Sprache<select class="in" id="m82cl">${Object.entries(M().langs || {}).map(([a, l]) => `<option value="${a}" ${k.sprache === a ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      <label class="f" style="flex:none;width:120px;margin:0">Währung<select class="in" id="m82cw">${(M().curs || ["EUR"]).map(c => `<option ${k.waehrung === c ? "selected" : ""}>${c}</option>`).join("")}</select></label>
      <span class="small muted" style="flex:1;min-width:220px">Gilt für neue Rechnungen, Angebote und Auftragsbestätigungen. Statistik und Steuer bleiben in EUR.</span></div>`;
    card.after(el);
    const save = async () => { const r = await api("/api/m82/kunde", {customer_id:custSel, sprache:$("#m82cl").value, waehrung:$("#m82cw").value});
      if (r && r.ok) { S.m82 = S.m82 || {kunden:{}}; S.m82.kunden = S.m82.kunden || {};
        if ($("#m82cl").value === "de" && $("#m82cw").value === "EUR") delete S.m82.kunden[String(custSel)]; else S.m82.kunden[String(custSel)] = {sprache:$("#m82cl").value, waehrung:$("#m82cw").value};
        toast("Vorgabe gespeichert"); } };
    $("#m82cl").onchange = save; $("#m82cw").onchange = save;
  });

  // ---------- building blocks: English texts ----------
  async function artDialog(){
    const arts = (S.articles || []).filter(a => a.active !== 0);
    const A = M().artikel || {};
    await modal("Englische Texte für Bausteine", `<div class="small muted" style="margin-bottom:8px">Wird ein Baustein unverändert in ein englisches Dokument übernommen, erscheint im PDF dieser Name / Text. Leer = deutscher Text bleibt.</div>
      <div class="search" style="max-width:300px;margin-bottom:8px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="m82aq" placeholder="Baustein suchen …"></div>
      <div class="scroll" style="max-height:60vh"><table class="t"><thead><tr><th style="width:90px">Nr.</th><th>Deutsch</th><th>Name englisch</th><th>Beschreibung englisch</th></tr></thead><tbody>
      ${arts.map(a => { const e = A[String(a.id)] || {}; return `<tr data-m82a="${a.id}"><td class="small"><b>${esc(a.nr || "")}</b></td><td class="small">${esc(a.name)}${a.descr ? `<div class="muted">${esc(a.descr.slice(0, 90))}</div>` : ""}</td>
        <td><input class="in" data-m82n value="${esc(e.name_en || "")}"></td><td><textarea class="in" data-m82d rows="1">${esc(e.descr_en || "")}</textarea></td></tr>`; }).join("") || `<tr><td colspan="4" class="empty">Keine Bausteine.</td></tr>`}</tbody></table></div>`,
      [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
        const rows = $$("[data-m82a]", mb).map(tr => ({article_id:+tr.dataset.m82a, name_en:$("[data-m82n]", tr).value, descr_en:$("[data-m82d]", tr).value}));
        const r = await api("/api/m82/artikel", {rows}); if (!r || !r.ok) return false;
        await reload(); toast("Englische Bausteintexte gespeichert"); }}], true,
      mb => { const qi = $("#m82aq", mb); if (qi) qi.oninput = () => { const v = qi.value.toLowerCase(); $$("[data-m82a]", mb).forEach(tr => tr.style.display = tr.textContent.toLowerCase().includes(v) || $$("input,textarea", tr).some(i => i.value.toLowerCase().includes(v)) ? "" : "none"); }; });
  }
  EXT.after.push(n => {
    if (n !== "vBlocks" || $("#m82ab")) return;
    const act = $("#main .ph .act"); if (!act) return;
    const b = document.createElement("button"); b.className = "btn"; b.id = "m82ab"; b.type = "button"; b.innerHTML = ic("m82") + " Englische Texte";
    b.onclick = artDialog; act.prepend(b);
  });
  window.m82ArtDialog = artDialog;

  // ---------- settings tab ----------
  EXT.settings.push({key:"m82", label:"Englisch & Währung", render: async el => {
    const r = await api("/api/m82/texte"); const l = await api("/api/m82/list");
    const t = r.texte || {}, st = r.standard || {};
    const fld = (k, lbl, rows = 2) => `<label class="f">${lbl}<textarea class="in" rows="${rows}" data-m82t="${k}" placeholder="${esc(st[k] || "")}">${esc(t[k] !== st[k] ? t[k] : "")}</textarea></label>`;
    el.innerHTML = `<div class="card" style="margin-bottom:16px"><div class="hd"><h3>Englische Standardtexte</h3><div class="act"><button class="btn sm" id="m82art" type="button">Bausteine übersetzen</button></div></div><div class="bd fr">
      <div class="small muted">Leer = mitgelieferter Text (grau angezeigt). Platzhalter wie im Deutschen: [Frist], [Zahlungsfrist], [Gueltig], [Mahnfrist], [Betrag], [Nummer].
        Deutsche Standardtexte werden in englischen Dokumenten automatisch durch diese ersetzt, ebenso der Kleinunternehmer-Hinweis.</div>
      ${S.m82 && !S.m82.intl_ok ? `<div class="alert warn">${ic("alert")}<span>Englische PDF-Ausgabe nicht verfügbar: ${esc(S.m82.intl_info || "")}</span></div>` : (S.m82 && S.m82.intl_info ? `<div class="alert">${ic("alert")}<span>${esc(S.m82.intl_info)}</span></div>` : "")}
      <div class="grid" style="grid-template-columns:1fr 1fr;gap:10px">
        ${fld("top_rechnung", "Rechnung – Kopftext")}${fld("foot_rechnung", "Rechnung – Fußtext")}
        ${fld("top_angebot", "Angebot – Kopftext")}${fld("foot_angebot", "Angebot – Fußtext")}
        ${fld("top_auftrag", "Auftragsbestätigung – Kopftext")}${fld("foot_auftrag", "Auftragsbestätigung – Fußtext")}
        ${fld("mail_subject", "E-Mail – Betreff", 1)}${fld("mail_body", "E-Mail – Text", 4)}
        ${fld("mahn_anrede", "Mahnung – Anrede", 1)}${fld("mahn_foot", "Mahnung – Schlusssatz", 1)}</div>
      ${[0, 1, 2, 3].map(i => `<label class="f">${["Zahlungserinnerung", "1. Mahnung", "2. Mahnung", "Letzte Mahnung"][i]} – Text<textarea class="in" rows="2" data-m82m="${i}" placeholder="${esc((st.mahn_text || [])[i] || "")}">${esc((t.mahn_text || [])[i] !== (st.mahn_text || [])[i] ? (t.mahn_text || [])[i] || "" : "")}</textarea></label>`).join("")}
      <details><summary class="small" style="cursor:pointer">Feste Beschriftungen im PDF anpassen</summary><div class="grid" style="grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:8px">
        ${Object.entries(r.labels || {}).map(([de, en]) => `<label class="f small">${esc(de)}<input class="in" data-m82lb="${esc(de)}" value="${esc(en)}"></label>`).join("")}</div></details>
      <div><button class="btn pri" id="m82ts" type="button">Speichern</button></div></div></div>
      <div class="card" style="overflow:hidden"><div class="hd"><h3>Dokumente in Fremdsprache / Fremdwährung</h3><div class="act">${expButtons("m82_international", {}, true)}</div></div>
        <table class="t"><thead><tr><th>Nr.</th><th>Datum</th><th>Sprache</th><th>Währung</th><th class="r">Kurs</th><th class="r">Betrag Fremdw.</th><th class="r">EUR</th><th>Status</th></tr></thead><tbody>
        ${(l.rows || []).map(d => `<tr class="click" data-m82inv="${d.invoice_id}"><td><b>${esc(d.nr)}</b></td><td class="num">${dde(d.datum)}</td><td>${esc((M().langs || {})[d.sprache] || d.sprache)}</td><td>${esc(d.waehrung)}</td>
          <td class="r num">${d.waehrung === "EUR" ? "–" : nde(d.kurs || 1, 4)}</td><td class="r num">${d.waehrung === "EUR" ? "–" : nde(d.betrag_fw || 0) + " " + esc(d.waehrung)}</td><td class="r num">${eur(d.summe)}</td><td>${esc(d.status)}</td></tr>`).join("")
          || `<tr><td colspan="8" class="empty">Noch keine Dokumente in Englisch oder Fremdwährung.</td></tr>`}</tbody></table></div>`;
    bindCommon(el);
    $("#m82art", el).onclick = artDialog;
    $$("[data-m82inv]", el).forEach(tr => tr.onclick = () => openInvoice(+tr.dataset.m82inv));
    $("#m82ts", el).onclick = async () => {
      const texte = {}; $$("[data-m82t]", el).forEach(a => { texte[a.dataset.m82t] = a.value.trim() || st[a.dataset.m82t]; });
      texte.mahn_text = $$("[data-m82m]", el).map(a => a.value.trim() || (st.mahn_text || [])[+a.dataset.m82m]);
      const labels = {}; $$("[data-m82lb]", el).forEach(a => labels[a.dataset.m82lb] = a.value.trim());
      const res = await api("/api/m82/texte", {texte, labels}); if (res && res.ok) { await reload(); toast("Englische Texte gespeichert"); }
    };
  }});
})();
