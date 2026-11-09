// =============================================================
//  PA Rechnung - Modul m30 E-Mails (Import, Erkennung, IMAP, Handy)  v1.1.0
//  v1.1.0 (Programm v3.6.0): Mails lesen - ganze Mail (HTML), An/Kopie, gelesen/ungelesen,
//          Suche, Vor/Zurueck blaettern, Antworten im Mailprogramm, externe Bilder auf Wunsch.
//  Autor: T. Pfeiffer
// =============================================================
Object.assign(IC, {
  phone:'<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  inbox:'<path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1 2h6l1-2h5"/>',
});
if (!IC.mail) IC.mail = '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>';

const MAILF = {f:"alle", sort:"datum", hide:false, q:""};
const MAILSEL = new Set();
let MAILD = null;
const MAIL_BADGE = {rechnung_anhang:"ok", rechnung_text:"ok", erechnung:"ok", rechnung_link:"warn", gutschrift:"acc", mahnung:"bad", auftrag:"", keine:"", zahlung:"warn"};
const MAIL_STATUS = {neu:["", "offen"], uebernommen:["ok", "übernommen"], keine:["", "keine Rechnung"]};

EXT.nav.push({key:"mails", label:"E-Mails", icon:"mail", section:"Finanzen", cnt:() => (S && S.mailimp && S.mailimp.offen) || ""});

function mailPct(v){ return Math.round((Number(v)||0)*100); }
function mailPctBadge(v){ const p = mailPct(v); return `<span class="small" style="font-weight:600;color:${p>=85?"var(--ok)":p>=65?"var(--warn)":"var(--bad)"}">${p} %</span>`; }
function mailWhen(iso){ return iso ? dde(iso.slice(0,10)) + " " + iso.slice(11,16) : ""; }
function mailKb(n){ n = Number(n)||0; return n > 1048576 ? nde(n/1048576,1) + " MB" : Math.max(1, Math.round(n/1024)) + " KB"; }

function mailFiltered(){
  const u = MAILD.unsicher || 0.65;
  let l = MAILD.items.filter(r => {
    if (MAILF.hide && r.status !== "neu") return false;
    if (MAILF.q) { const t = (r.absender + " " + r.absender_addr + " " + r.betreff).toLowerCase(); if (!MAILF.q.toLowerCase().split(/\s+/).every(w => t.includes(w))) return false; }
    if (MAILF.f === "ungelesen") return !r.gelesen;
    if (MAILF.f === "rechnungen") return r.rechnung;
    if (MAILF.f === "keine") return !r.rechnung;
    if (MAILF.f === "zahlungen") return r.urteil === "zahlung";
    if (MAILF.f === "unsicher") return r.sicherheit < u && r.status === "neu";
    return true;
  });
  const by = {datum:(a,b)=>(b.datum||"").localeCompare(a.datum||""), sicherheit:(a,b)=>a.sicherheit-b.sicherheit,
    absender:(a,b)=>(a.absender||"").localeCompare(b.absender||"", "de"), urteil:(a,b)=>(a.urteil_text||"").localeCompare(b.urteil_text||"", "de")};
  return l.sort(by[MAILF.sort] || by.datum);
}

async function mailUpload(files){
  // v2.4.4: Outlook-Datendatei (.pst/.ost) -> Hintergrund-Import (m99c)
  const pst = [...files].filter(f => /\.(pst|ost)$/i.test(f.name));
  for (const f of pst) if (window.moPstImport) await window.moPstImport(f, "geschaeft");
  files = [...files].filter(f => /\.(eml|msg|mbox|mbx)$/i.test(f.name) || !/\.\w{2,5}$/.test(f.name));
  if (!files.length) { if (!pst.length) toast("Bitte E-Mail-Dateien wählen (.eml, .msg, .mbox oder Outlook-Datei .pst/.ost)", true); return; }
  let neu = 0, dop = 0, err = 0;
  for (const [i, f] of files.entries()) {
    const st = $("#mstat"); if (st) st.textContent = `Lese ${i+1}/${files.length}: ${f.name} …`;
    try { const r = await upload("/api/upload/mail", f);
      if (r.ok === false) { toast(r.error || "Fehler", true); err++; continue; }
      neu += r.neu||0; dop += r.doppelt||0; err += r.fehler||0;
    } catch (e) { err++; toast(f.name + ": Fehler beim Einlesen", true); }
  }
  toast(`${neu} E-Mail(s) neu eingelesen` + (dop ? `, ${dop} schon vorhanden` : "") + (err ? `, ${err} Fehler` : ""), !!err && !neu);
  await reload(); vMails();
}

async function mailAction(kind, ids){
  ids = [...ids]; if (!ids.length) return false;
  if (kind === "loeschen" && !await confirmBox(`${ids.length} E-Mail(s) löschen? Die Dateien wandern in den Ordner „_Papierkorb“ im Datenordner.`, "Löschen")) return false;
  let extra = {};
  if (kind === "ist_rechnung") {
    // v2.4.5: declare as invoice; optionally the sender goes onto the list of invoice senders
    const rows = ids.map(i => (MAILD && MAILD.items || []).find(x => x.id === i)).filter(Boolean);
    const doms = [...new Set(rows.map(x => String(x.absender_addr || "").split("@")[1]).filter(Boolean))];
    const v = await modal("Als Rechnung markieren", `<div class="fr"><div class="small">${ids.length} Mail(s) werden als <b>Rechnung</b> markiert und erscheinen unter „Rechnungen“. Eine Neubewertung ändert das nicht mehr. Mit ✓ legst du sie danach in die Beleg-Prüfliste.</div>
      ${doms.length ? `<label class="chk"><input type="checkbox" id="mrlist"> Rechnungen von <b>${esc(doms.slice(0,4).join(", "))}</b>${doms.length > 4 ? " …" : ""} künftig automatisch erkennen (Rechnungs-Absenderliste)</label>` : ""}</div>`,
      [{label:"Abbrechen", value:null}, {label:"Als Rechnung markieren", cls:"pri", value:"ok", onClick: async mb => { const c = $("#mrlist", mb); extra.liste = !!(c && c.checked); }}]);
    if (!v) return false;
  }
  const r = await api("/api/mail/" + kind, Object.assign({ids}, extra));
  if (!r || r.ok === false) return false;
  if (kind === "uebernehmen") toast(`${r.belege} Beleg(e) aus ${r.mails} E-Mail(s) in die Prüfliste unter „Belege & Import“ gelegt`);
  if (kind === "keine") toast(`${r.n} E-Mail(s) als „keine Rechnung“ markiert – Absender gemerkt`);
  if (kind === "ist_rechnung") toast(`${r.n} E-Mail(s) als Rechnung markiert` + ((r.liste||[]).length ? ` – auf die Absenderliste: ${r.liste.join(", ")}` : "") + ((r.hinweise||[]).length ? ` (nicht auf die Liste: ${r.hinweise.join("; ")})` : ""));
  if (kind === "loeschen") toast(`${r.n} E-Mail(s) gelöscht`);
  if (kind === "neu_bewerten") toast(`${r.n} E-Mail(s) neu bewertet`);
  ids.forEach(i => MAILSEL.delete(i));
  await reload(); if (view === "mails") vMails();
  return true;
}

async function mailImapNow(btn){
  if (btn) { btn.disabled = true; btn.textContent = "Rufe ab …"; }
  const r = await api("/api/mail/imap/abrufen", {});
  if (btn) btn.disabled = false;
  if (r && r.ok) toast("Postfach abgerufen: " + r.text);
  await reload(); if (view === "mails") vMails(); else if (btn) btn.innerHTML = `${ic("sync")} Jetzt abrufen`;
}

EXT.views.mails = async function(){
  $("#main").innerHTML = `<div class="page">${pageHead("E-Mails", "lädt …")}</div>`;
  MAILD = await api("/api/mail/list");
  if (!MAILD || !MAILD.items) { MAILD = {items:[], urteile:{}, imap:{}, handy:{}}; }
  const im = MAILD.imap || {}, last = im.letzter || {};
  const list = mailFiltered();
  const ids = new Set(MAILD.items.map(r => r.id)); [...MAILSEL].forEach(i => { if (!ids.has(i)) MAILSEL.delete(i); });
  const cnt = k => ({alle:MAILD.items.length, rechnungen:MAILD.items.filter(r=>r.rechnung).length, keine:MAILD.items.filter(r=>!r.rechnung).length,
    unsicher:MAILD.items.filter(r=>r.sicherheit<(MAILD.unsicher||0.65)&&r.status==="neu").length,
    zahlungen:MAILD.items.filter(r=>r.urteil==="zahlung").length, ungelesen:MAILD.items.filter(r=>!r.gelesen).length})[k];
  const offen = MAILD.items.filter(r => r.status === "neu" && r.rechnung).length;
  const act = `${im.eingerichtet?`<button class="btn" id="mimap">${ic("sync")} Jetzt abrufen</button>`:`<button class="btn ghost" id="mimapset">${ic("set")} Postfach einrichten</button>`}
    <button class="btn" id="mhandy">${ic("phone")} Beleg per Handy</button><button class="btn pri" id="mpick">${ic("plus")} E-Mails hinzufügen</button>`;
  $("#main").innerHTML = `<div class="page">
    ${pageHead("E-Mails", "Mails hineinziehen oder vom Postfach abrufen – das Programm erkennt, ob eine Rechnung drin ist, und legt sie in die Beleg-Prüfliste", act)}
    <div class="dz" id="mdz" style="margin-bottom:14px;padding:26px"><b>E-Mails hier ablegen</b><span class="muted">.eml (Thunderbird, Outlook „Speichern unter“), .msg (Outlook), .mbox (ganze Postfächer, z. B. Google-Takeout/Thunderbird-Export) und Outlook-Datendateien .pst/.ost (werden gemerkt und bei jedem Start aktualisiert) · doppelte Mails werden erkannt</span></div>
    <div class="row small muted" style="margin-bottom:10px;align-items:center;flex-wrap:wrap"><span id="mstat" style="flex:none">${im.eingerichtet?`Postfach: ${im.intervall?`Abruf alle ${im.intervall} Min.`:"automatischer Abruf aus"}${last.zeit?` · letzter Abruf ${mailWhen(last.zeit)} – <span style="color:${last.ok?"var(--ok)":"var(--bad)"}">${esc(last.text||"")}</span>`:""}`:"Kein Postfach eingerichtet – E-Mails per Drag&Drop einlesen oder unter Einstellungen → E-Mail-Abruf ein IMAP-Postfach eintragen."}</span>
      ${offen?`<span class="sp"></span><span class="badge warn" style="flex:none"><span class="dot"></span>${offen} Rechnung(en) noch nicht übernommen</span>`:""}</div>
    <div class="row" style="margin:4px 0 10px;align-items:center;flex-wrap:wrap">
      <div class="chips" style="flex:none">${[["alle","Alle"],["ungelesen","Ungelesen"],["rechnungen","Rechnungen"],["zahlungen","Mit Betrag"],["keine","Keine"],["unsicher","Unsicher"]].map(([k,l])=>`<span class="chip ${MAILF.f===k?"on":""}" data-mf="${k}">${l} (${cnt(k)})</span>`).join("")}</div>
      <input class="in" id="mq" placeholder="Suchen (Absender, Betreff)" value="${esc(MAILF.q)}" style="width:220px;flex:none;margin-left:10px">
      <label class="chk" style="flex:none;margin-left:10px"><input type="checkbox" id="mhide" ${MAILF.hide?"checked":""}> Erledigte ausblenden</label>
      <span class="sp"></span>
      <label class="small muted" style="flex:none">Sortierung <select class="in" id="msort" style="width:auto;display:inline-block">${[["datum","Datum (neueste zuerst)"],["sicherheit","Sicherheit (unsicherste zuerst)"],["absender","Absender"],["urteil","Urteil"]].map(([k,l])=>`<option value="${k}" ${MAILF.sort===k?"selected":""}>${l}</option>`).join("")}</select></label></div>
    <div id="mbar"></div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th style="width:28px"><input type="checkbox" id="mall"></th><th>Datum</th><th>Absender</th><th>Betreff</th><th>Urteil</th><th class="r">Sicherheit</th><th class="r">Betrag</th><th>Status</th><th></th></tr></thead>
    <tbody>${list.map(r => { const st = MAIL_STATUS[r.status] || ["", r.status];
      return `<tr class="click" data-mid="${r.id}"><td onclick="event.stopPropagation()"><input type="checkbox" data-msel="${r.id}" ${MAILSEL.has(r.id)?"checked":""}></td>
      <td class="num small">${r.gelesen?"":`<span title="ungelesen" style="display:inline-block;width:8px;height:8px;border-radius:4px;background:var(--acc,#0A84FF);margin-right:5px"></span>`}${mailWhen(r.datum)}</td><td><b>${esc(r.absender||r.absender_addr)}</b><div class="small muted">${esc(r.absender_addr||"")}</div></td>
      <td style="${r.gelesen?"":"font-weight:700"}">${esc(r.betreff||"(ohne Betreff)")}${r.anhaenge?` <span class="small muted" title="Anhänge">${ic("clip")}${r.anhaenge}</span>`:""}</td>
      <td><span class="badge ${MAIL_BADGE[r.urteil]||""}">${esc(r.urteil_text)}</span></td><td class="r">${mailPctBadge(r.sicherheit)}</td>
      <td class="r num">${r.betrag?eur(r.betrag):""}</td><td><span class="badge ${st[0]}">${esc(st[1])}${r.status==="uebernommen"&&r.belege?" ("+r.belege+")":""}</span></td>
      <td class="r" onclick="event.stopPropagation()" style="white-space:nowrap">${r.status!=="uebernommen"?`<button class="btn sm" data-mtake="${r.id}" title="Als Beleg übernehmen">${ic("check")}</button>`:""}${!r.rechnung&&r.status!=="uebernommen"?`<button class="btn sm ghost" data-mrech="${r.id}" title="Ist eine Rechnung">€</button>`:""}${r.status==="neu"?`<button class="btn sm ghost" data-mnone="${r.id}" title="Keine Rechnung">✕</button>`:""}<button class="btn sm ghost" data-mdel="${r.id}" title="Löschen">${ic("trash")}</button></td></tr>`; }).join("")
      || `<tr><td colspan="9" class="empty">${MAILD.items.length?"Keine E-Mails in dieser Ansicht.":"Noch keine E-Mails eingelesen."}</td></tr>`}</tbody></table></div></div>`;
  const dz = $("#mdz");
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); mailUpload([...e.dataTransfer.files]); };
  $("#mpick").onclick = () => pickFiles(".eml,.msg,.mbox,.mbx,.pst,.ost", mailUpload);
  $("#mhandy").onclick = () => handyDialog();
  if ($("#mimap")) $("#mimap").onclick = e => mailImapNow(e.currentTarget);
  if ($("#mimapset")) $("#mimapset").onclick = () => { setTab = "mailabruf"; go("set"); };
  $$("[data-mf]").forEach(c => c.onclick = () => { MAILF.f = c.dataset.mf; vMails(); });
  $("#mhide").onchange = e => { MAILF.hide = e.target.checked; vMails(); };
  let mqT = null;
  $("#mq").oninput = e => { clearTimeout(mqT); mqT = setTimeout(async () => { MAILF.q = e.target.value.trim(); await vMails(); const i = $("#mq"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }, 250); };
  $("#msort").onchange = e => { MAILF.sort = e.target.value; vMails(); };
  $$("[data-mid]").forEach(tr => tr.onclick = () => mailDetail(+tr.dataset.mid));
  $$("[data-mtake]").forEach(b => b.onclick = () => mailAction("uebernehmen", [+b.dataset.mtake]));
  $$("[data-mnone]").forEach(b => b.onclick = () => mailAction("keine", [+b.dataset.mnone]));
  $$("[data-mrech]").forEach(b => b.onclick = () => mailAction("ist_rechnung", [+b.dataset.mrech]));
  $$("[data-mdel]").forEach(b => b.onclick = () => mailAction("loeschen", [+b.dataset.mdel]));
  $$("[data-msel]").forEach(cb => cb.onchange = () => { cb.checked ? MAILSEL.add(+cb.dataset.msel) : MAILSEL.delete(+cb.dataset.msel); mailBar(); });
  $("#mall").onchange = e => { list.forEach(r => e.target.checked ? MAILSEL.add(r.id) : MAILSEL.delete(r.id)); $$("[data-msel]").forEach(cb => cb.checked = e.target.checked); mailBar(); };
  mailBar();
};
function vMails(){ return EXT.views.mails(); }

function mailBar(){
  const el = $("#mbar"); if (!el) return;
  if (!MAILSEL.size) { el.innerHTML = ""; return; }
  el.innerHTML = `<div class="hl row" style="align-items:center;margin-bottom:10px;flex-wrap:wrap"><b style="flex:none">${MAILSEL.size} markiert</b><span class="sp"></span>
    <button class="btn sm pri" data-mb="uebernehmen">${ic("check")} Als Beleg übernehmen</button><button class="btn sm" data-mb="ist_rechnung">€ Ist eine Rechnung</button><button class="btn sm" data-mb="keine">Keine Rechnung</button>
    <button class="btn sm" data-mb="gelesen">Als gelesen</button><button class="btn sm" data-mb="ungelesen">Als ungelesen</button>
    <button class="btn sm" data-mb="neu_bewerten">Neu bewerten</button><button class="btn sm danger" data-mb="loeschen">${ic("trash")} Löschen</button>
    <button class="btn sm ghost" data-mb="clear">Auswahl aufheben</button></div>`;
  $$("[data-mb]", el).forEach(b => b.onclick = async () => { const k = b.dataset.mb;
    if (k === "clear") { MAILSEL.clear(); vMails(); return; }
    if (k === "gelesen" || k === "ungelesen") { await api("/api/mail/gelesen", {ids:[...MAILSEL], gelesen: k === "gelesen"}); MAILSEL.clear(); await reload(); if (view === "mails") vMails(); return; }
    mailAction(k, MAILSEL); });
}

// v1.1.0: reading view. Same viewer as "Privat-Mails": HTML in a sandboxed frame, scripts/forms off,
// external images blocked until "Bilder laden" (otherwise the sender sees that the mail was opened).
const MAIL_CSP = img => `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:${img ? " https: http:" : ""}; style-src 'unsafe-inline'${img ? " https:" : ""}; font-src data:">`;
function mailFrame(fr, r, img){
  fr.srcdoc = MAIL_CSP(img) + `<base target="_blank"><style>body{font:14px system-ui,sans-serif;margin:12px;color:#222;background:#fff}img{max-width:100%;height:auto}</style>` + r.html;
}
function mailAddr(s){ const m = String(s||"").match(/[\w.+-]+@[\w-]+(\.[\w-]+)+/); return m ? m[0] : ""; }

async function mailDetail(id){
  const r = await api("/api/mail/get?id=" + id);
  if (!r || r.ok === false) return;
  const it = MAILD && (MAILD.items||[]).find(x => x.id === id);
  if (it && !it.gelesen) { it.gelesen = 1; if (S.mailimp && S.mailimp.ungelesen) { S.mailimp.ungelesen--; } }
  const ai = r.absender_info || {};
  const atts = (r.anhaenge||[]);
  const artL = {erechnung:["ok","E-Rechnung"], rechnung:["ok","Rechnung"], gutschrift:["acc","Gutschrift"], mahnung:["bad","Mahnung"], auftrag:["","Angebot/Auftrag"],
    dokument:["","Dokument"], bild:["","Foto/Scan"], logo:["","Logo – verworfen"], sonstig:["","sonstiges"], leer:["","leer"]};
  const list = MAILD ? mailFiltered() : [];
  const pos = list.findIndex(x => x.id === id);
  const prev = pos > 0 ? list[pos-1].id : null, next = pos >= 0 && pos < list.length-1 ? list[pos+1].id : null;
  const hasExt = r.html && /<img[^>]+src\s*=\s*["']?https?:/i.test(r.html);
  const body = r.html
    ? `<iframe id="mrfr" sandbox="allow-popups allow-popups-to-escape-sandbox" style="width:100%;height:52vh;border:1px solid var(--line);border-radius:8px;background:#fff"></iframe>`
    : `<pre class="small" style="white-space:pre-wrap;max-height:52vh;overflow:auto;background:var(--bg2,#f7f6fb);padding:12px;border-radius:8px;margin:0;font-family:inherit;font-size:13.5px;line-height:1.5">${esc((r.text||"").trim()||"(kein Text)")}</pre>`;
  const pct = mailPct(r.sicherheit);
  const html = `<div class="fr">
    <div class="grid g2" style="gap:6px 18px"><div class="small"><span class="muted">Von</span><br><b>${esc(r.absender||"")}</b> ${esc(r.absender_addr?"<"+r.absender_addr+">":"")}</div>
      <div class="small"><span class="muted">Datum</span><br>${mailWhen(r.datum)} <span class="muted">· ${esc(r.quelle||"")}</span>${pos>=0?` <span class="muted">· ${pos+1} von ${list.length}</span>`:""}</div>
      ${r.an||r.empfaenger?`<div class="small" style="grid-column:1/-1"><span class="muted">An</span> ${esc(r.an||r.empfaenger)}</div>`:""}
      ${r.cc?`<div class="small" style="grid-column:1/-1"><span class="muted">Kopie</span> ${esc(r.cc)}</div>`:""}
      ${r.antwort_an?`<div class="small" style="grid-column:1/-1"><span class="muted">Antwort an</span> ${esc(r.antwort_an)}</div>`:""}</div>
    <div class="small muted">${r.ordner?`<a href="#" id="mfold">Ordner öffnen</a> · `:""}<a href="#" id="mreply">Antworten</a> (öffnet dein Mailprogramm)${r.ordner?` · <a href="#" id="morig">Original öffnen</a>`:""} · <a href="#" id="munread">Als ungelesen markieren</a></div>
    <div class="row small" style="align-items:center;gap:8px;flex-wrap:wrap"><span class="badge ${MAIL_BADGE[r.urteil]||""}" style="flex:none">${esc(r.urteil_text)}</span>
      <span style="flex:none;color:${pct>=85?"var(--ok)":pct>=65?"var(--warn)":"var(--bad)"}"><b>${pct} %</b></span>${r.betrag?`<span style="flex:none">· ${eur(r.betrag)}</span>`:""}
      <span class="sp"></span>${hasExt?`<span class="muted" id="mrimgw" style="flex:none" title="Externe Bilder sind blockiert – sonst sieht der Absender, dass du die Mail geöffnet hast">Bilder blockiert · <a href="#" id="mrimg">Bilder laden</a></span>`:""}
      <a href="#" id="mrerk" style="flex:none">Warum? (Erkennung)</a></div>
    <div id="mrerkbox" class="hl small" hidden style="border-left:3px solid ${pct>=85?"var(--ok)":pct>=65?"var(--warn)":"var(--bad)"}">
      <ul style="margin:0 0 0 18px;padding:0">${(r.begruendung||[]).map(b=>`<li>${esc(b)}</li>`).join("")}</ul>
      ${r.urteil==="rechnung_link"?`<div style="margin-top:6px"><b>Hinweis:</b> Die Rechnung hängt nicht an der Mail. Bitte im Kundenportal herunterladen und unter „Belege & Import“ nachreichen – oder die Mail selbst als Beleg übernehmen (wird als PDF abgelegt).</div>`:""}
      ${(r.links||[]).length?`<div style="margin-top:6px"><b>Rechnungs-Links</b>${r.links.map((l,i)=>`<div style="margin-top:3px"><a href="#" data-mlink="${i}">${esc(l.text||l.url).slice(0,90)}</a> <span class="muted">${esc(l.url.replace(/^https?:\/\//,"").slice(0,60))}</span></div>`).join("")}</div>`:""}
      <div class="muted" style="margin-top:6px">Absender-Gedächtnis: ${ai.rechnung||0}× als Rechnung übernommen, ${ai.keine||0}× „keine Rechnung“${(ai.rechnung||ai.keine)?` · <a href="#" id="mforget">vergessen</a>`:""}</div></div>
    ${atts.length?`<div><div class="small muted" style="margin-bottom:4px"><b>Anhänge</b> (${atts.length})</div>${atts.map((a,i)=>{ const al = artL[a.art]||["",a.art];
      return `<div class="row small" style="align-items:center;padding:4px 0;border-bottom:1px solid var(--line)">${ic("clip")}<b style="flex:1;overflow:hidden;text-overflow:ellipsis">${esc(a.name)}</b>
        <span class="badge ${al[0]}" style="flex:none">${esc(al[1])}</span><span class="muted" style="flex:none">${esc(a.hinweis||"")} · ${mailKb(a.size)}</span>
        ${a.file?`<button class="btn sm ghost" style="flex:none" data-mopen="${i}">${ic("open")} Öffnen</button>`:""}</div>`; }).join("")}</div>`:""}
    ${body}
</div>`;
  let goTo = null;
  const btns = [];
  if (prev) btns.push({label:"‹ Vorherige", onClick: async () => { goTo = prev; }});
  btns.push({label:"Löschen", cls:"danger", onClick: async () => mailAction("loeschen", [id])});
  if (r.status === "neu") btns.push({label:"Keine Rechnung", onClick: async () => { await mailAction("keine", [id]); }});
  if (r.status !== "uebernommen" && !["rechnung_anhang","rechnung_text","erechnung","rechnung_link"].includes(r.urteil)) btns.push({label:"€ Ist eine Rechnung", onClick: async () => { await mailAction("ist_rechnung", [id]); }});
  if (r.status !== "uebernommen") btns.push({label:"Als Beleg übernehmen", onClick: async () => { await mailAction("uebernehmen", [id]); }});
  btns.push({label:"Schließen", cls:"pri"});
  if (next) btns.push({label:"Nächste ›", onClick: async () => { goTo = next; }});
  await modal(r.betreff || "(ohne Betreff)", html, btns, true, mb => {
    const fr = $("#mrfr", mb); if (fr) mailFrame(fr, r, false);
    const im = $("#mrimg", mb); if (im) im.onclick = e => { e.preventDefault(); mailFrame(fr, r, true); $("#mrimgw", mb).remove(); };
    const ek = $("#mrerk", mb); ek.onclick = e => { e.preventDefault(); const b = $("#mrerkbox", mb); b.hidden = !b.hidden; };
    $$("[data-mopen]", mb).forEach(b => b.onclick = () => api("/api/open", {path:atts[+b.dataset.mopen].file}));
    $$("[data-mlink]", mb).forEach(a => a.onclick = e => { e.preventDefault(); api("/api/mail/link", {id, url:r.links[+a.dataset.mlink].url}); });
    const f = $("#mfold", mb); if (f) f.onclick = e => { e.preventDefault(); api("/api/open", {path:r.ordner, folder:true}); };
    const o = $("#morig", mb); if (o) o.onclick = e => { e.preventDefault(); api("/api/mail/original", {id}); };
    $("#mreply", mb).onclick = e => { e.preventDefault();
      const to = mailAddr(r.antwort_an) || r.absender_addr || "";
      const sub = /^(re|aw):/i.test(r.betreff||"") ? r.betreff : "AW: " + (r.betreff||"");
      api("/api/mail/antworten", {id, to, betreff: sub}); };
    $("#munread", mb).onclick = async e => { e.preventDefault(); await api("/api/mail/gelesen", {ids:[id], gelesen:false}); if (it) it.gelesen = 0; toast("Als ungelesen markiert"); };
    const fg = $("#mforget", mb); if (fg) fg.onclick = async e => { e.preventDefault(); await api("/api/mail/absender_vergessen", {addr:r.absender_addr}); toast("Absender vergessen"); fg.remove(); };
  });
  if (goTo) return mailDetail(goTo);
  if (view === "mails") vMails();
}

// ---------- Beleg per Handy ----------
async function handyDialog(ip){
  const r = await api("/api/handy/start", ip ? {ip} : {});
  if (!r || !r.ok) return;
  let timer = null;
  const html = `<div class="row" style="align-items:flex-start;gap:20px;flex-wrap:wrap">
    <div style="flex:none;background:#fff;padding:10px;border-radius:12px;border:1px solid var(--line);width:280px;height:280px">${r.svg}</div>
    <div style="flex:1;min-width:240px" class="fr">
      <div><b>So geht's:</b><ol class="small" style="margin:6px 0 0 18px;padding:0"><li>Handy-Kamera auf den QR-Code richten und den Link öffnen.</li>
        <li>„Foto aufnehmen“ tippen, Beleg fotografieren – oder ein PDF wählen.</li><li>Die Fotos erscheinen hier und unter „Belege & Import“ in der Prüfliste.</li></ol></div>
      <div class="small muted">Adresse: <span style="font-family:Consolas,monospace">${esc(r.url)}</span></div>
      ${(r.ips||[]).length>1?`<label class="f small">Netzwerk-Adresse des PCs<select class="in" id="hip">${r.ips.map(i=>`<option ${i===r.ip?"selected":""}>${esc(i)}</option>`).join("")}</select></label>`:""}
      <div class="alert warn small" style="margin:0">Das Handy muss im <b>selben WLAN</b> sein wie dieser PC. Beim ersten Mal fragt die Windows-Firewall – bitte „Zugriff zulassen“ (privates Netzwerk) wählen.</div>
      <div class="small">Code gültig noch <b id="hrest">30:00</b> Min. · max. ${r.max_mb} MB pro Datei</div>
      <div id="hlist" class="small"></div></div></div>`;
  const poll = async () => { const s = await api("/api/handy/status", undefined, {quiet:true}); const el = document.getElementById("hlist"); if (!el || !s) return;
    const m = Math.floor(s.rest_s/60), sec = s.rest_s%60; const rs = document.getElementById("hrest"); if (rs) rs.textContent = s.aktiv ? `${m}:${String(sec).padStart(2,"0")}` : "abgelaufen";
    el.innerHTML = (s.files||[]).length ? `<b>Empfangen (${s.n})</b>` + s.files.slice().reverse().map(f=>`<div>${ic("check")} ${esc(f.zeit)} ${esc(f.name)} <span class="muted">${mailKb(f.groesse)} · ${esc(f.status)}</span></div>`).join("") : `<span class="muted">Noch nichts empfangen.</span>`; };
  const v = await modal("Beleg per Handy", html, [{label:"Beenden", value:"stop"}, {label:"Neuer Code", value:"neu"}, {label:"Zur Prüfliste", cls:"pri", value:"beleg"}], true, mb => {
    timer = setInterval(poll, 3000); poll();
    const s = $("#hip", mb); if (s) s.onchange = () => { handyDialog._ip = s.value; const b = [...$$(".mf .btn", mb)].find(x => x.textContent === "Neuer Code"); if (b) b.click(); };
  });
  clearInterval(timer);
  if (v === "stop") { await api("/api/handy/stop", {}); toast("Handy-Upload beendet"); }
  if (v === "neu") { const ip2 = handyDialog._ip || ip; handyDialog._ip = ""; return handyDialog(ip2); }
  await reload();
  if (v === "beleg") go("beleg");
  else if (view === "beleg") vBelege();
}

EXT.after.push(name => {
  if (name !== "vBelege") return;
  const a = $("#main .ph .act"); if (!a || $("#bhandy", a)) return;
  const b = document.createElement("button"); b.className = "btn"; b.id = "bhandy"; b.innerHTML = `${ic("phone")} Beleg per Handy`;
  b.onclick = () => handyDialog(); a.prepend(b);
  const m = document.createElement("button"); m.className = "btn ghost"; m.id = "bmails"; m.innerHTML = `${ic("mail")} E-Mails`;
  m.title = "E-Mails einlesen und Rechnungen erkennen"; m.onclick = () => go("mails"); a.prepend(m);
});

// ---------- Einstellungen: E-Mail-Abruf ----------
EXT.settings.push({key:"mailabruf", label:"E-Mail-Abruf", render(el){
  const s = S.settings;
  const f = (k,l,ph="",type="text",def="") => `<label class="f">${l}<input class="in" data-s="${k}" type="${type}" value="${esc(s[k]??def)}" placeholder="${esc(ph)}"></label>`;
  const after = s.mi_after || "nichts";
  el.innerHTML = `<div class="grid g2" style="align-items:start">
    <div class="card"><div class="hd"><h3>IMAP-Postfach</h3><div class="act">${s.mi_pass_set?`<span class="badge ok"><span class="dot"></span>Passwort gespeichert</span>`:`<span class="badge warn">nicht eingerichtet</span>`}</div></div><div class="bd fr">
      <div class="small">Das Programm holt Mails aus deinem Postfach und prüft sie wie Mails, die du auf der Seite <b>E-Mails</b> hineinziehst. Rechnungen landen dort zur Übernahme.</div>
      <div class="row">${f("mi_host","IMAP-Server","imap.gmail.com")}<div style="flex:.4">${f("mi_port","Port","993","number")}</div></div>
      <label class="chk"><input type="checkbox" data-s="mi_ssl" ${s.mi_ssl!==false?"checked":""}> SSL/TLS verwenden (Port 993; aus = 143 mit STARTTLS)</label>
      ${f("mi_user","Benutzer / E-Mail-Adresse")}
      <label class="f">Passwort / App-Passwort<input class="in" type="password" id="mipw" autocomplete="new-password" placeholder="${s.mi_pass_set?"•••••••• (gespeichert – nur zum Ändern eintragen)":"Passwort eintragen"}"></label>
      <div class="row">${f("mi_folder","Ordner","INBOX","text","INBOX")}<div style="flex:.6">${f("mi_interval","Abruf alle X Minuten (0 = aus)","0","number","0")}</div></div>
      <label class="chk"><input type="checkbox" data-s="mi_unseen" ${s.mi_unseen!==false?"checked":""}> Nur ungelesene Mails abrufen</label>
      <label class="f">Nach dem Abruf<select class="in" data-s="mi_after" id="miafter">
        <option value="nichts" ${after==="nichts"?"selected":""}>nichts ändern (Mails bleiben ungelesen)</option>
        <option value="gelesen" ${after==="gelesen"?"selected":""}>als gelesen markieren</option>
        <option value="verschieben" ${after==="verschieben"?"selected":""}>in Ordner verschieben</option></select></label>
      <div id="mimove" style="${after==="verschieben"?"":"display:none"}">${f("mi_move_folder","Zielordner","z. B. Rechnungen oder INBOX/Erledigt")}</div>
      <div class="small muted">Gmail/Outlook/GMX: meist ein <b>App-Passwort</b> nötig. Das Passwort wird verschlüsselt gespeichert (Windows-DPAPI) und nie angezeigt. Beim ersten Abruf werden nur Mails der letzten 60 Tage geholt; danach nur neue.</div>
      <div class="row" style="align-items:center;flex-wrap:wrap"><button class="btn" style="flex:none" id="mitest">Verbindung testen</button><button class="btn" style="flex:none" id="minow">${ic("sync")} Jetzt abrufen</button>
        ${s.mi_pass_set?`<button class="btn ghost sm" style="flex:none" id="mipwdel">Passwort löschen</button>`:""}</div>
      <div class="small" id="mires"></div></div></div>
    <div class="card"><div class="hd"><h3>Beleg per Handy</h3></div><div class="bd fr">
      <div class="small">Mit dem Knopf <b>„Beleg per Handy“</b> (Seiten E-Mails und Belege & Import) erscheint ein QR-Code. Das Handy öffnet damit eine einfache Upload-Seite auf diesem PC und schickt Fotos oder PDFs direkt in die Beleg-Prüfliste.</div>
      <div class="row">${f("handy_port","Port für das Handy","8765","number","8765")}${f("handy_max_mb","Max. Dateigröße (MB)","25","number","25")}</div>
      <div class="small muted">Nur im selben WLAN erreichbar. Jeder Code ist zufällig und gilt 30 Minuten, danach wird der Handy-Zugang automatisch geschlossen. Beim ersten Mal fragt die Windows-Firewall – „Private Netzwerke“ zulassen.</div></div></div></div>`;
  const vals = () => ({host:$("[data-s=mi_host]",el).value.trim(), port:pnum($("[data-s=mi_port]",el).value), ssl:$("[data-s=mi_ssl]",el).checked,
    user:$("[data-s=mi_user]",el).value.trim(), pass:$("#mipw",el).value, folder:$("[data-s=mi_folder]",el).value.trim()||"INBOX",
    interval:pnum($("[data-s=mi_interval]",el).value), unseen:$("[data-s=mi_unseen]",el).checked, after:$("#miafter",el).value,
    move_folder:$("[data-s=mi_move_folder]",el).value.trim(), auth:($("[data-s=mi_auth]",el)||{}).value||"pass"});
  const res = (ok, t) => { $("#mires",el).innerHTML = `<span style="color:${ok?"var(--ok)":"var(--bad)"}">${ok?"✓ ":""}${esc(t)}</span>`; };
  $("#miafter",el).onchange = e => { $("#mimove",el).style.display = e.target.value === "verschieben" ? "" : "none"; };
  const sv = $("#ssave"); if (sv) sv.addEventListener("click", () => { const pw = $("#mipw",el) && $("#mipw",el).value; if (pw) api("/api/mail/imap/speichern", {pass:pw}); });
  $("#mitest",el).onclick = async () => { $("#mires",el).textContent = "teste …"; const r = await api("/api/mail/imap/test", vals(), {quiet:true}); res(r.ok, r.ok ? r.info : (r.error || "Fehler")); };
  $("#minow",el).onclick = async () => { $("#mires",el).textContent = "speichere und rufe ab …"; await api("/api/mail/imap/speichern", vals());
    const r = await api("/api/mail/imap/abrufen", {}, {quiet:true}); res(r.ok, r.ok ? "Abgerufen: " + r.text : (r.error || "Fehler")); await reload(); };
  const pd = $("#mipwdel",el); if (pd) pd.onclick = async () => { if (!await confirmBox("Gespeichertes IMAP-Passwort löschen? Der automatische Abruf stoppt dann.", "Löschen")) return;
    await api("/api/mail/imap/speichern", {pass_loeschen:true}); await reload(); vSettings(); toast("Passwort gelöscht"); };
}});
