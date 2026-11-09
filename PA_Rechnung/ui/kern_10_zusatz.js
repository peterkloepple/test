// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Mahnwesen, E-Mail, Suche, Hell/Dunkel, Zeiterfassung
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ============ v1.1.0 additions ============
Object.assign(IC, {
  school:'<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5"/><path d="M22 9v6"/>',
  award:'<circle cx="12" cy="9" r="6"/><path d="M8.5 14L7 22l5-3 5 3-1.5-8"/>',
  wrench:'<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  bank:'<path d="M3 10h18L12 4z"/><path d="M5 10v8M9 10v8M15 10v8M19 10v8M3 21h18"/>',
  box:'<path d="M21 8l-9-5-9 5 9 5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
  car:'<path d="M5 16h14l-1.5-6.5A2 2 0 0 0 15.6 8H8.4a2 2 0 0 0-1.9 1.5z"/><circle cx="7.5" cy="17.5" r="1.5"/><circle cx="16.5" cy="17.5" r="1.5"/><path d="M3 16h18"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  moon:'<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  alert:'<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
});
const DOCT = {rechnung:"Rechnung", storno:"Storno-Rechnung", angebot:"Angebot", auftrag:"Auftragsbestätigung"};
let invTab = "rechnung";
function bindInvHead(){
  bindCommon();
  $$(".tab[data-tab]").forEach(t => t.onclick = () => { invTab = t.dataset.tab; invF.status = ""; vInvoices(); });
  $("#newang").onclick = () => newInvoice({typ:"angebot"});
  if ($("#invdup")) $("#invdup").onclick = () => dupCheck(() => vInvoices());
}
let converting = false;   // v2.1.0: double click created two invoices from one offer
async function convertDoc(to){
  if (converting) return; converting = true;
  try { await convertDocInner(to); } finally { converting = false; }
}
async function convertDocInner(to){
  if (!cur.locked && cur.typ!=="rechnung") { const r = await api("/api/invoice/save", cur); if (!r.ok) return; }
  const r = await api("/api/invoice/convert", {id:cur.id, to});
  if (r.ok) { const src_ = cur.id; curBase = null; if (KEEP.inv && KEEP.inv[String(src_)]) { delete KEEP.inv[String(src_)]; keepSave(); renderParkbar(); }
    toast(DOCT[to] + " " + r.nr + " erstellt"); await reload(); openInvoice(r.id, true); }
}
// ---- Mahnwesen ----
function renderMahn(){
  const o = S.overdue;
  $("#mahn").innerHTML = `<div class="card" style="overflow:hidden;margin-bottom:16px"><div class="hd"><h3>Überfällige Rechnungen</h3><div class="act small muted">${o.length} · ${eur(o.reduce((a,i)=>a+i.summe,0))}</div></div>
    <table class="t"><thead><tr><th>Nr.</th><th>Kunde</th><th>Fällig seit</th><th>Tage</th><th>Stufe</th><th class="r">Betrag</th><th style="width:260px"></th></tr></thead><tbody>
    ${o.map(i=>`<tr><td><a href="#" data-inv="${i.id}"><b>${esc(i.nr)}</b></a></td><td>${esc(i.name)}</td><td>${dde(i.faellig)}</td><td class="num"><b style="color:${i.tage>30?"var(--bad)":"var(--warn)"}">${i.tage}</b></td>
      <td>${i.mahnstufe?`<span class="badge bad">${i.mahnstufe}. Stufe</span>`:`<span class="badge">–</span>`}</td><td class="r num"><b>${eur(i.summe)}</b></td>
      <td class="r"><button class="btn sm" data-mk="${i.id}">${ic("alert")} ${["Erinnerung","1. Mahnung","2. Mahnung","Letzte Mahnung"][Math.min(i.mahnstufe||0,3)]}</button> <button class="btn sm ghost" data-paid="${i.id}" title="Bezahlt">${ic("check")}</button></td></tr>`).join("") || `<tr><td colspan="7" class="empty">Keine überfälligen Rechnungen 🎉</td></tr>`}
    </tbody></table></div>
    <div class="card" style="overflow:hidden"><div class="hd"><h3>Erstellte Mahnungen</h3></div><table class="t"><tbody>
    ${S.mahnungen.map(m=>`<tr><td>${dde(m.datum)}</td><td><b>${["Zahlungserinnerung","1. Mahnung","2. Mahnung","Letzte Mahnung"][Math.min(m.stufe,3)]}</b> zu <a href="#" data-inv="${m.invoice_id}">${esc(m.nr||"")}</a></td><td>Frist ${dde(m.frist_bis)}</td><td class="r num">${eur(m.betrag)}</td>
      <td class="r"><button class="btn sm ghost" data-of="${esc(m.file)}">${ic("open")}</button><button class="btn sm ghost" data-mm="${m.id}">${ic("mail")}</button></td></tr>`).join("") || `<tr><td class="empty">Noch keine Mahnungen.</td></tr>`}
    </tbody></table></div>`;
  bindCommon($("#mahn"));
  $$("[data-mk]").forEach(b => b.onclick = () => makeMahnung(+b.dataset.mk));
  $$("#mahn [data-paid]").forEach(b => b.onclick = () => markPaid(+b.dataset.paid));
  $$("#mahn [data-of]").forEach(b => b.onclick = () => api("/api/open", {path:b.dataset.of}));
  $$("#mahn [data-mm]").forEach(b => b.onclick = () => mailDialog({mahnung_id:+b.dataset.mm}));
}
async function makeMahnung(id){
  const r = await api("/api/mahnung/create", {id});
  if (!r.ok) return;
  await reload();
  const act = await modal(r.titel + " erstellt", `<p style="margin:0">Das PDF wurde gespeichert:<br><span class="small muted">${esc(r.path)}</span></p>`,
    [{label:"Schließen", value:"x"},{label:"PDF öffnen", value:"open"},{label:"Per E-Mail senden", cls:"pri", value:"mail"}]);
  if (act === "open") api("/api/open", {path:r.path});
  if (act === "mail") { mailDialog({mahnung_id:r.id}); return; }
  if (view === "editor" && cur && cur.id) openInvoice(cur.id, cur.id == id); else go(view, viewArg);
}
// ---- E-Mail ----
async function mailDialog(ref){
  const p = await api("/api/mail/prepare?" + (ref.mahnung_id ? "mahnung_id="+ref.mahnung_id : "doc_id="+ref.doc_id));
  if (!p.configured) { const go_ = await modal("E-Mail einrichten", `<p style="margin:0">Der E-Mail-Versand ist noch nicht eingerichtet. Unter <b>Einstellungen → E-Mail</b> Server, Benutzer und App-Passwort eintragen (bei Gmail: Google-Konto → Sicherheit → App-Passwörter).</p>`, [{label:"Später"},{label:"Zu den Einstellungen", cls:"pri", value:true}]); if (go_) { setTab = "mail"; go("set"); } return; }
  await modal("Per E-Mail senden", `<div class="fr">
    <div class="row"><label class="f">An<input class="in nokeep" id="mto" value="${esc(p.to)}"></label><label class="f" style="flex:.7">Cc<input class="in nokeep" id="mcc"></label></div>
    <label class="f">Betreff<input class="in" id="msub" value="${esc(p.subject)}"></label>
    <label class="f">Nachricht<textarea class="in" id="mbody" rows="9">${esc(p.body)}</textarea></label>
    <div class="small muted">${ic("clip")} Anhang: ${esc(p.attachment)}</div></div>`,
    [{label:"Abbrechen"},{label:"Senden", cls:"pri", onClick: async mb => {
      const b = $$(".md .btn.pri", mb)[0]; b.disabled = true; b.textContent = "Sende …";
      const r = await api("/api/mail/send", Object.assign({}, ref, {to:$("#mto",mb).value, cc:$("#mcc",mb).value, subject:$("#msub",mb).value, body:$("#mbody",mb).value}));
      if (!r.ok) { b.disabled = false; b.textContent = "Senden"; return false; }
      toast("E-Mail gesendet"); }}], true);
  await reload();
  if (view === "editor" && cur && cur.id) openInvoice(cur.id); else go(view, viewArg);
}
// ---- Search (Ctrl+K) ----
function openSearch(){
  const mb = document.createElement("div"); mb.className = "mb"; mb.style.alignItems = "flex-start"; mb.style.paddingTop = "10vh";
  mb.innerHTML = `<div class="md" style="width:min(720px,94vw)"><div class="mc" style="padding:14px"><div class="search"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="gq" placeholder="Kunden, Rechnungen, Projekte, Dateien, Belege, Bausteine, Schüler, Nachweise …" style="font-size:16px;padding:11px 12px 11px 34px"></div>
    <div id="gres" style="max-height:60vh;overflow:auto;margin-top:10px"><div class="muted small" style="padding:10px">Mindestens 2 Zeichen eingeben · Esc schließt</div></div></div></div>`;
  document.body.appendChild(mb);
  const close = () => mb.remove();
  mb.addEventListener("mousedown", e => { if (e.target === mb) close(); });
  const inp = $("#gq", mb); inp.focus();
  let tm = null, items = [], sel = 0;
  const run = async () => {
    const r = await api("/api/search?q=" + encodeURIComponent(inp.value), undefined, {quiet:true});
    items = []; let h = "";
    for (const [grp, rows] of Object.entries(r||{})) { if (!rows || !rows.length) continue;
      h += `<div class="sidelbl" style="color:var(--mute);padding:10px 8px 4px">${esc(grp)}</div>`;
      rows.forEach(x_ => { const i = items.length; items.push([grp, x_]);
        const sub = grp==="Rechnungen & Angebote" ? `${DOCT[x_.typ]||""} · ${dde(x_.datum)} · ${eur(x_.summe)}` : grp==="Belege" ? `${dde(x_.datum)} · ${eur(x_.betrag)}` : grp==="Bausteine" ? eur(x_.price) : grp==="Nachweise" ? (x_.sub||"")+" · gültig bis "+dde(x_.gueltig_bis) : (x_.sub||x_.kdnr||x_.nr||"");
        h += `<div class="gr ${i===sel?"on":""}" data-i="${i}"><b>${esc(x_.title||"")}</b><span class="muted small">${esc(sub||"")}</span></div>`; }); }
    $("#gres", mb).innerHTML = h || `<div class="muted small" style="padding:10px">Nichts gefunden.</div>`;
    $$(".gr", mb).forEach(e => e.onclick = () => openHit(+e.dataset.i));
  };
  const openHit = i => { const [g, x_] = items[i] || []; if (!g) return; close();
    if (g==="Kunden") { custSel = x_.id; go("users"); }
    else if (g==="Rechnungen & Angebote") openInvoice(x_.id);
    else if (g==="Projekte") go("project", x_.id);
    else if (g==="Projektdateien") { pTab = "files"; pFolder = x_.sub || "*"; go("project", x_.project_id); }
    else if (g==="Belege") { go("beleg"); setTimeout(()=>editBeleg(S.belege.find(b=>b.id==x_.id)), 200); }
    else if (g==="Bausteine") go("blocks");
    else if (g==="Schüler") { schTab = "st"; go("school"); setTimeout(()=>editStudent(S.students.find(s=>s.id==x_.id)), 300); }
    else if (g==="Kurse") { schTab = "kurse"; go("school"); }
    else if (g==="Nachweise") go("certs");
    else if (g==="Vorlagen") { go("vorlagen"); setTimeout(() => window.vlDetailById && window.vlDetailById(x_.id), 400); } };
  inp.oninput = () => { sel = 0; clearTimeout(tm); tm = setTimeout(run, 160); };
  inp.onkeydown = e => { if (e.key==="Escape") close(); if (e.key==="ArrowDown"){ sel=Math.min(sel+1, items.length-1); run(); e.preventDefault(); } if (e.key==="ArrowUp"){ sel=Math.max(0, sel-1); run(); e.preventDefault(); } if (e.key==="Enter") openHit(sel); };
}
document.addEventListener("keydown", e => { if ((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==="k") { e.preventDefault(); if (!$("#gq")) openSearch(); } });
// ---- theme ----
function applyTheme(t){ document.documentElement.dataset.theme = t; try { localStorage.setItem("pa_theme", t); } catch(e) {} }
function toggleTheme(){ const t = document.documentElement.dataset.theme==="dark" ? "light" : "dark"; applyTheme(t); api("/api/settings/save", {theme:t}, {quiet:true}); S.settings.theme = t; renderSide(); }
// ---- timer ----
function timerElapsed(t){ const ms = Date.now() - new Date(t.start).getTime(); const m = Math.max(0, Math.floor(ms/60000)); return Math.floor(m/60)+":"+String(m%60).padStart(2,"0")+" h"; }
setInterval(() => { const e = $("#tmel"); if (e && S && S.settings.timer) e.textContent = timerElapsed(S.settings.timer); }, 30000);
async function startTimer(pid){
  if (S.settings.timer && !(await confirmBox("Es läuft bereits ein Timer. Den alten verwerfen und neu starten?", "Neu starten"))) return;
  await api("/api/timer/start", {project_id:pid}); await reload(); toast("Timer gestartet"); go(view, viewArg);
}
async function stopTimer(){
  const t = S.settings.timer; if (!t) return;
  const r = await modal("Zeit buchen", `<div class="fr"><div class="hl small">Laufzeit: <b>${timerElapsed(t)}</b> – wird auf volle Viertelstunden aufgerundet.</div>
    <label class="f">Was wurde gemacht?<input class="in" id="tmd" placeholder="z. B. Programmierung Q-SYS, Schweißarbeiten Treppengeländer"></label>
    <label class="f">Baustein / Stundensatz<select class="in" id="tma"><option value="">Stundensatz aus Einstellungen (${eur(S.settings.stundensatz)})</option>${S.articles.filter(a=>a.active).map(a=>`<option value="${a.id}">${esc(a.nr+" "+a.name)} (${eur(a.price)})</option>`).join("")}</select></label></div>`,
    [{label:"Verwerfen", cls:"danger", value:"cancel"},{label:"Abbrechen"},{label:"Buchen", cls:"pri", value:"ok", onClick: async mb => {
      const x_ = await api("/api/timer/stop", {descr:$("#tmd",mb).value, article_id:+$("#tma",mb).value||null}); if (x_.ok) toast(nde(x_.stunden,2)+" Std gebucht"); }}]);
  if (r === "cancel" && await confirmBox("Timer verwerfen, ohne zu buchen?", "Verwerfen")) await api("/api/timer/cancel", {});
  await reload(); go(view, viewArg);
}
