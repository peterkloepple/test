// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Liste Rechnungen & Angebote
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- invoices list ----------
let invF = {year:String(thisYear), status:"", q:""};
function vInvoices(){
  const tabs = [["rechnung","Rechnungen"],["draft","Entwürfe"],["angebot","Angebote"],["auftrag","Auftragsbestätigungen"],["mahn","Mahnwesen"]];
  const cnt = {rechnung:S.invoices.filter(i=>["rechnung","storno"].includes(i.typ)&&i.status!=="entwurf").length, draft:S.invoices.filter(i=>i.status==="entwurf").length,
    angebot:S.invoices.filter(i=>i.typ==="angebot").length, auftrag:S.invoices.filter(i=>i.typ==="auftrag").length, mahn:S.overdue.length};
  const head = pageHead("Rechnungen & Angebote", "", expButtons(invTab === "mahn" ? "mahn" : "invoices", () => ({tab:invTab, year:invF.year, status:invF.status, q:invF.q})) + `<button class="btn" id="invdup" title="Assistent sucht doppelte Rechnungen und Belege">Doppelte suchen</button><button class="btn" id="newang">${ic("plus")} Angebot</button><button class="btn pri" data-go="new">${ic("plus")} Neue Rechnung</button>`)
    + `<div class="tabs">${tabs.map(([k,l])=>`<div class="tab ${invTab===k?"on":""}" data-tab="${k}">${l}<span class="cnt">${cnt[k]}</span></div>`).join("")}</div>`;
  if (invTab === "mahn") { $("#main").innerHTML = `<div class="page">${head}<div id="mahn"></div></div>`; bindInvHead(); renderMahn(); return; }
  const base = S.invoices.filter(i => invTab==="draft" ? i.status==="entwurf" : invTab==="rechnung" ? (["rechnung","storno"].includes(i.typ) && i.status!=="entwurf") : i.typ===invTab);
  const years = [...new Set(base.map(i=>i.datum.slice(0,4)))].sort().reverse();
  const rows = base.filter(i => (!invF.year || i.datum.startsWith(invF.year) || invTab==="draft") && (!invF.status || i.status===invF.status) &&
     (!invF.q || (i.nr + " " + (i.addr||"") + " " + (i.titel||"")).toLowerCase().includes(invF.q.toLowerCase())));
  const sum = rows.reduce((a,i)=>a+i.summe,0), sumOpen = rows.filter(i=>i.status==="offen").reduce((a,i)=>a+i.summe,0);
  const stOpts = invTab==="angebot"?[["","Alle"],["offen","Offen"],["angenommen","Angenommen"],["abgelehnt","Abgelehnt"]]:invTab==="rechnung"?[["","Alle"],["offen","Offen"],["bezahlt","Bezahlt"],["storniert","Storniert"]]:[["","Alle"]];
  $("#main").innerHTML = `<div class="page">${head}
    <div class="row" style="margin-bottom:14px;align-items:center">
      <div class="search" style="max-width:320px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="iq" placeholder="Nummer, Kunde, Titel …" value="${esc(invF.q)}"></div>
      ${invTab!=="draft"?`<div class="chips" style="flex:none">${["",...years].map(y=>`<span class="chip ${invF.year===y?"on":""}" data-y="${y}">${y||"Alle Jahre"}</span>`).join("")}</div>`:""}
      <div class="seg" style="flex:none">${stOpts.map(([k,l])=>`<button class="${invF.status===k?"on":""}" data-st="${k}">${l}</button>`).join("")}</div>
      <span class="sp"></span><span class="muted small" style="flex:none">${rows.length} · ${eur(sum)}${sumOpen?` · offen ${eur(sumOpen)}`:""}</span>
    </div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Nr.</th><th>Datum</th><th>Kunde</th><th>Titel</th><th>Status</th><th class="r">Betrag</th><th style="width:200px"></th></tr></thead>
    <tbody>${rows.map(i=>`<tr class="click" data-open="${i.id}"><td><b>${esc(i.status==="entwurf"?"Entwurf":i.nr)}</b>${i.locked?` <span title="festgeschrieben" class="muted">🔒</span>`:""}${i.versendet_am?` <span title="versendet ${dde(i.versendet_am)}" class="muted">✉</span>`:""}</td><td class="num">${dde(i.datum)}</td><td>${esc(invName(i))}</td><td class="muted">${esc(i.titel)}</td>
      <td>${statusBadge(i)}</td><td class="r num"><b>${eur(i.summe)}</b></td>
      <td class="r" onclick="event.stopPropagation()">${i.status!=="entwurf"?`<button class="btn sm ghost" title="PDF speichern & öffnen" data-pdf="${i.id}">${ic("pdf")}</button><button class="btn sm ghost" title="Per E-Mail senden" data-mail="${i.id}">${ic("mail")}</button>`:""}<button class="btn sm ghost" title="Duplizieren" data-dup="${i.id}">${ic("copy")}</button>
      ${["rechnung","storno"].includes(i.typ)&&i.status==="offen"?`<button class="btn sm ghost" title="${i.typ==="storno"?"Erstattung erledigt":"Als bezahlt markieren"}" data-paid="${i.id}">${ic("check")}</button>`:""}
      ${!i.locked||S.inv_frei?`<button class="btn sm ghost danger" title="Löschen" data-del="${i.id}">${ic("trash")}</button>`:""}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">Keine Einträge.</td></tr>`}</tbody>
    <tfoot><tr><td colspan="5">Summe</td><td class="r num">${eur(sum)}</td><td></td></tr></tfoot></table></div></div>`;
  bindInvHead();
  selectify({kind:"invoice", rows:"tr[data-open]", id:"data-open", rerender:vInvoices, actions:[
    ...(invTab==="rechnung" ? [{label:"✓ Als bezahlt", run: async ids => { const d = await askValue("Zahlungseingang für " + ids.length + " Rechnung(en)", `<label class="f">Bezahlt am<input type="date" class="in" id="bpd" value="${todayIso()}"></label>`, mb => $("#bpd", mb).value);
        if (!d) return false; await bulk("invoice", "bezahlt", ids, d); await reload(); vInvoices(); }},
      {label:"Als offen", run: async ids => { await bulk("invoice", "offen", ids); await reload(); vInvoices(); }}] : []),
    ...(window.printDocs ? [{label:"Drucken", run: async ids => { await printDocs(ids); return false; }}] : []),
    ...(invTab!=="draft" ? [{label:"PDFs speichern", run: async ids => { toast("PDFs werden erstellt …"); await bulk("invoice", "pdf", ids); await reload(); vInvoices(); }}] : []),
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Dokument(e) löschen?" + (S.inv_frei ? " Auch festgeschriebene Rechnungen werden gelöscht (PDF in den Papierkorb, Eintrag im GoBD-Protokoll)." : " Festgeschriebene Rechnungen bleiben erhalten (nur stornieren möglich)."))) return false;
      await bulk("invoice", "delete", ids); await reload(); vInvoices(); }}]});
  $("#iq").oninput = e => { invF.q = e.target.value; debRender("iq", vInvoices); };
  $$("[data-y]").forEach(c => c.onclick = () => { invF.year = c.dataset.y; vInvoices(); });
  $$("[data-st]").forEach(c => c.onclick = () => { invF.status = c.dataset.st; vInvoices(); });
  $$("[data-open]").forEach(r => r.onclick = () => openInvoice(+r.dataset.open));
  $$("[data-pdf]").forEach(b => b.onclick = async () => { const r = await api("/api/invoice/export", {id:+b.dataset.pdf}); if (r.ok) { toast("PDF gespeichert: " + r.path.split(/[\\/]/).pop()); await reload(); vInvoices(); } });
  $$("[data-mail]").forEach(b => b.onclick = () => mailDialog({doc_id:+b.dataset.mail}));
  $$("[data-dup]").forEach(b => b.onclick = () => duplicateInvoice(+b.dataset.dup));
  $$("[data-paid]").forEach(b => b.onclick = () => markPaid(+b.dataset.paid));
  $$("[data-del]").forEach(b => b.onclick = async () => { const i = S.invoices.find(x=>x.id==b.dataset.del);
    if (await confirmBox(`${DOCT[i.typ]||"Dokument"} ${i.status==="entwurf"?"(Entwurf)":i.nr} wirklich löschen?`)) { const r = await api("/api/invoice/delete", {id:i.id}); if (r.ok) { if (KEEP.inv[i.id]) { delete KEEP.inv[i.id]; keepSave(); renderParkbar(); } await reload(); vInvoices(); toast("Gelöscht"); } } });
}
async function markPaid(id){
  const r = await modal("Zahlungseingang", `<label class="f">Bezahlt am<input type="date" class="in" id="pdate" value="${todayIso()}"></label>`,
    [{label:"Abbrechen"},{label:"Als bezahlt markieren", cls:"pri", onClick: async mb => { await api("/api/invoice/status", {id, status:"bezahlt", bezahlt_am: $("#pdate", mb).value}); }, value:true}]);
  if (r) { await reload(); go(view, viewArg); toast("Als bezahlt markiert"); }
}

