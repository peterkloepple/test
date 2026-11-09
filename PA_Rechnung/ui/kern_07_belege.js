// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Belege & Import, doppelte Belege
// v3.6.1: Pruefliste - Klick aufs Vorschaubild / "Groß ansehen" oeffnet die Datei gross (m39_ansicht), dort Uebernehmen und Blaettern.
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- belege ----------
let queue = [], belF = {year:String(thisYear), typ:""};
function vBelege(){
  syncQueue();
  const list = S.belege.filter(b => (!belF.year || b.datum.startsWith(belF.year)) && (!belF.typ || b.typ===belF.typ));
  const sums = {}; list.forEach(b => sums[b.typ] = (sums[b.typ]||0) + b.betrag);
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Belege & Import", "PDF einfach hineinziehen – das Programm erkennt, was es ist: Eingangsrechnung, Gehaltsabrechnung, Lohnsteuerbescheinigung, eigene Rechnung oder Anlage", expButtons("belege", () => ({year:belF.year, typ:belF.typ})))}
    <div class="dz" id="bdz" style="margin-bottom:16px;padding:34px"><b>Belege hier ablegen – jedes Format</b><span class="muted">PDF, Excel, Word, OpenOffice, E-Rechnung (XML/ZUGFeRD), E-Mails (.eml/.msg mit Anhängen), ZIP-Archive, Fotos & Scans${S.ocr?" (Texterkennung aktiv)":""}, Text, RTF, HTML … · passwortgeschützte Dateien werden erkannt</span>
      <div style="margin-top:12px"><button class="btn pri" id="bpick">${ic("up")} Dateien auswählen</button></div></div>
    <div id="assist"></div>
    <div id="queue"></div>
    <div class="row" style="margin:6px 0 12px;align-items:center"><h2 style="margin:0;font:600 17px var(--disp);flex:none">Erfasste Belege</h2><span class="sp"></span>
      <div class="chips" style="flex:none">${["", ...new Set([String(thisYear), ...S.belege.map(b=>b.datum.slice(0,4))])].sort().reverse().map(y=>`<span class="chip ${belF.year===y?"on":""}" data-y="${y}">${y||"Alle"}</span>`).join("")}</div>
      <select class="in" id="btyp" style="width:auto;flex:none"><option value="">Alle Arten</option>${Object.entries(TYPES).filter(([k])=>k!=="eigene_rechnung").map(([k,v])=>`<option value="${k}" ${belF.typ===k?"selected":""}>${v}</option>`).join("")}</select></div>
    <div class="grid g4" style="margin-bottom:14px">${["ausgabe","gehalt","einnahme","anlage"].map(k=>`<div class="card kpi"><div class="l">${TYPES[k]}</div><div class="v">${k==="anlage"?list.filter(b=>b.typ===k).length:eur(sums[k]||0)}</div><div class="s">${list.filter(b=>b.typ===k).length} Beleg(e)</div></div>`).join("")}</div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Datum</th><th>Art</th><th>Partner</th><th>Nr.</th><th>Kategorie / Info</th><th class="r">Betrag</th><th></th></tr></thead>
    <tbody>${list.map(b=>{ const d = JSON.parse(b.details||"{}"); return `<tr class="click" data-b="${b.id}"><td class="num">${dde(b.datum)}</td><td><span class="badge ${TYPE_BADGE[b.typ]}">${esc(TYPES[b.typ]||b.typ)}</span></td><td><b>${esc(b.partner)}</b></td><td class="small">${esc(b.nr)}</td>
      <td class="small muted">${b.typ==="gehalt"?`${d.zeitraum==="jahr"?"Jahreswerte":esc(d.periode||"Monat")} · LSt ${eur(d.lst)}`:b.typ==="anlage"?(b.invoice_id?"an Rechnung "+esc((S.invoices.find(i=>i.id==b.invoice_id)||{}).nr||""):"nicht zugeordnet"):esc(b.kategorie)}</td>
      <td class="r num"><b>${b.typ==="anlage"?"":eur(b.betrag)}</b></td><td class="r" onclick="event.stopPropagation()">${b.file?`<button class="btn sm ghost" data-of="${esc(b.file)}">${ic("open")}</button>`:""}</td></tr>`; }).join("") || `<tr><td colspan="7" class="empty">Keine Belege in dieser Ansicht.</td></tr>`}</tbody></table></div></div>`;
  const dz = $("#bdz");
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); analyzeFiles([...e.dataTransfer.files]); };
  $("#bpick").onclick = () => pickFiles("", analyzeFiles);
  $$("[data-y]").forEach(c => c.onclick = () => { belF.year = c.dataset.y; vBelege(); });
  $("#btyp").onchange = e => { belF.typ = e.target.value; vBelege(); };
  $$("[data-b]").forEach(r => r.onclick = () => editBeleg(S.belege.find(b=>b.id==r.dataset.b)));
  const belDone = async () => { await reload(); vBelege(); };
  selectify({kind:"beleg", rows:"tr[data-b]", id:"data-b", rerender:vBelege, actions:[
    {label:"Kategorie …", run: async ids => { const v = await askValue("Kategorie für " + ids.length + " Beleg(e)", `<label class="f">Kategorie (EÜR)<select class="in" id="bk">${S.kategorien.map(k=>`<option>${esc(k)}</option>`).join("")}</select></label>`, mb => $("#bk", mb).value);
      if (v === null) return false; await bulk("beleg", "kategorie", ids, v); await belDone(); }},
    {label:"Art …", run: async ids => { const v = await askValue("Art für " + ids.length + " Beleg(e)", `<label class="f">Art<select class="in" id="bt">${Object.entries(TYPES).filter(([k])=>k!=="eigene_rechnung").map(([k,l])=>`<option value="${k}">${esc(l)}</option>`).join("")}</select></label>`, mb => $("#bt", mb).value);
      if (v === null) return false; await bulk("beleg", "typ", ids, v); await belDone(); }},
    {label:"Projekt …", run: async ids => { const v = await askValue("Projekt zuordnen", `<label class="f">Projekt<select class="in" id="bp"><option value="">– kein Projekt –</option>${S.projects.map(p=>`<option value="${p.id}">${esc(p.nr+" "+p.name)}</option>`).join("")}</select></label>`, mb => $("#bp", mb).value);
      if (v === null) return false; await bulk("beleg", "projekt", ids, v); await belDone(); }},
    {label:"Datum …", run: async ids => { const v = await askValue("Datum für " + ids.length + " Beleg(e)", `<label class="f">Datum<input type="date" class="in" id="bd" value="${todayIso()}"></label>`, mb => $("#bd", mb).value);
      if (!v) return false; await bulk("beleg", "datum", ids, v); await belDone(); }},
    {label:"Dateien exportieren", run: async ids => { const v = await askValue("Belegdateien exportieren", `<div class="small">Die Originaldateien der ${ids.length} Beleg(e) werden in einen neuen Ordner unter <b>Export</b> kopiert.</div><label class="chk" style="margin-top:10px"><input type="checkbox" id="bx"> Passwortgeschützte PDFs entschlüsselt exportieren</label>`, mb => $("#bx", mb).checked);
      if (v === null) return false; const r = await bulk("beleg", "export", ids, null, {entschluesseln:v}); if (r.folder) toast("Exportiert nach " + r.folder); }},
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Beleg(e) löschen? Die Dateien wandern in den Ordner „_Papierkorb“ im Datenordner.")) return false;
      await bulk("beleg", "delete", ids); await belDone(); }}]});
  $$("[data-of]").forEach(b => b.onclick = () => api("/api/open", {path:b.dataset.of}));
  renderQueue();
  loadAssist();
}
// ---------- v1.6.4: Assistent - doppelte Belege / Rechnungen nachtraeglich finden ----------
async function dupCheck(after){
  toast("Assistent sucht doppelte Einträge …");
  let d = await api("/api/dups");
  let changed = false, opened = false;
  const render = mb => {
    const box = $("#dupbox", mb);
    if (!d.gruppen.length) { box.innerHTML = `<div class="empty">✓ Keine doppelten Belege oder Rechnungen gefunden.</div>`; return; }
    box.innerHTML = `<div class="small muted" style="margin-bottom:10px">${d.gruppen.length} Gruppe(n) mit möglichen Dubletten · ${d.anzahl} Eintrag/Einträge zu viel. Der Assistent hat je Gruppe einen Eintrag zum <b>Behalten</b> vorgeschlagen (der mit Verknüpfungen zu Bank, Anlage, Rechnung bzw. der festgeschriebene/bezahlte). Die übrigen sind zum Entfernen markiert.</div>`
      + d.gruppen.map((g, gi) => `<div class="card" style="margin-bottom:12px;overflow:hidden" data-dg="${gi}"><div class="hd"><h3 style="font-size:14px">${g.kind==="invoice"?"Rechnungen / Dokumente":"Belege"} <span class="muted small" style="font-weight:400">· ${esc(g.grund)}</span></h3>
        <div class="act"><button class="btn sm ghost" data-dgi="${gi}">Kein Duplikat</button><button class="btn sm danger" data-dgr="${gi}">${ic("trash")} Markierte entfernen</button></div></div>
        <table class="t nosort"><thead><tr><th style="width:70px">Behalten</th><th style="width:70px">Entfernen</th><th>Datum</th><th>Art</th><th>Nr.</th><th>${g.kind==="invoice"?"Kunde":"Partner"}</th><th>${g.kind==="invoice"?"Status":"Datei"}</th><th class="r">Betrag</th><th></th></tr></thead><tbody>
        ${g.items.map(it => `<tr><td><input type="radio" name="dk${gi}" value="${it.id}" ${it.id===g.keep?"checked":""}></td><td><input type="checkbox" data-del="${it.id}" ${it.id!==g.keep?"checked":""} ${it.locked?"disabled title='festgeschrieben – nur Storno möglich'":""}></td>
          <td class="num">${dde(it.datum)}</td><td class="small">${esc(it.typ)}</td><td><b>${esc(it.nr)}</b></td><td>${esc(it.partner)}${it.titel?`<div class="small muted">${esc(it.titel)}</div>`:""}</td>
          <td class="small">${g.kind==="invoice"?`${esc(it.status)}${it.locked?" 🔒":""}`:esc(it.file)}${it.verknuepft?` <span class="badge ok">verknüpft</span>`:""}</td><td class="r num"><b>${eur(it.betrag)}</b></td>
          <td class="r"><button class="btn sm ghost" data-dopen="${g.kind}|${it.id}">Öffnen</button></td></tr>`).join("")}</tbody></table>
        ${g.items.some(it=>it.locked && it.id!==g.keep)?`<div class="small muted" style="padding:6px 12px 10px">🔒 Festgeschriebene Rechnungen dürfen nicht gelöscht werden (GoBD) – zum Entfernen öffnen und <b>Stornieren</b>.</div>`:""}</div>`).join("");
    $$("[data-dg]", box).forEach(card => {
      const gi = +card.dataset.dg;
      $$(`input[name=dk${gi}]`, card).forEach(rb => rb.onchange = () => $$("[data-del]", card).forEach(cb => { if (!cb.disabled) cb.checked = cb.dataset.del !== rb.value; else cb.checked = false; }));
    });
    $$("[data-dgi]", box).forEach(b => b.onclick = async () => { const g = d.gruppen[+b.dataset.dgi]; await api("/api/dups/ignore", {sig:g.sig}); d.gruppen.splice(+b.dataset.dgi, 1); toast("Gemerkt – wird nicht mehr als Duplikat gemeldet"); render(mb); });
    $$("[data-dgr]", box).forEach(b => b.onclick = async () => {
      const gi = +b.dataset.dgr, g = d.gruppen[gi], card = $(`[data-dg="${gi}"]`, box);
      const ids = $$("[data-del]", card).filter(cb => cb.checked && !cb.disabled).map(cb => +cb.dataset.del);
      if (!ids.length) { toast("Nichts zum Entfernen markiert", true); return; }
      if (ids.length >= g.items.length) { toast("Mindestens einen Eintrag behalten", true); return; }
      if (!await confirmBox(`${ids.length} doppelte(n) ${g.kind==="invoice"?"Rechnung(en)/Dokument(e)":"Beleg(e)"} entfernen?${g.kind==="beleg"?" Dateien wandern in den Ordner „_Papierkorb“.":""}`, "Entfernen")) return;
      const r = await bulk(g.kind, "delete", ids);
      if (r && r.ok) { changed = true; d = await api("/api/dups"); render(mb); }
    });
    $$("[data-dopen]", box).forEach(b => b.onclick = async () => { const [k, id] = b.dataset.dopen.split("|");
      opened = true; if (changed) await reload();
      if (k === "invoice") { close_(); openInvoice(+id); } else { const be = S.belege.find(x=>x.id==id); if (be) { close_(); go("beleg"); editBeleg(be); } } });
  };
  let close_ = () => {};
  await modal("Assistent: doppelte Einträge", `<div id="dupbox" class="nokeep" style="max-height:68vh;overflow:auto"></div>`,
    [{label:"Alle Vorschläge übernehmen", cls:"pri", onClick: async mb => {
      const all = [];
      d.gruppen.forEach((g, gi) => { const card = $(`[data-dg="${gi}"]`, mb); if (!card) return; const ids = $$("[data-del]", card).filter(cb => cb.checked && !cb.disabled).map(cb => +cb.dataset.del); if (ids.length && ids.length < g.items.length) all.push([g.kind, ids]); });
      const n = all.reduce((a, x) => a + x[1].length, 0);
      if (!n) { toast("Nichts zum Entfernen markiert", true); return false; }
      if (!await confirmBox(`${n} doppelte Einträge entfernen?`, "Entfernen")) return false;
      for (const kind of ["beleg","invoice"]) { const ids = all.filter(x=>x[0]===kind).flatMap(x=>x[1]); if (ids.length) await bulk(kind, "delete", ids); }
      changed = true; }},
     {label:"Schließen"}], true, mb => { close_ = () => { const b = [...$$(".mf .btn", mb)].pop(); if (b) b.click(); }; render(mb); });
  if (changed && !opened) { await reload(); (after || (() => go(view, viewArg)))(); }
}
let assistOpen = false;
async function loadAssist(){
  const [st, pend] = await Promise.all([api("/api/assist/status"), api("/api/pending/list")]);
  let added = 0;
  pend.forEach(p => { if (!savedPending.has(p.pending_id) && !queue.some(q => q.pending_id === p.pending_id)) { queue.push(p); added++; } });
  if (added) renderQueue();
  const el = $("#assist"); if (!el) return;
  const pt = st.pro_typ || {};
  el.innerHTML = `<div class="card" style="margin-bottom:16px"><div class="hd"><h3>Beleg-Assistent</h3>
    <div class="act"><span class="small muted">${st.gelernt} Belege gelernt · ${st.partner} Partner bekannt${st.ki_enabled?" · Dr. Jey (lokale KI) aktiv":""}</span><span id="dupcnt"></span><button class="btn sm" id="adup">Doppelte suchen</button><button class="btn sm ghost" id="astog">${assistOpen?"Weniger":"Details"}</button></div></div>
    <div class="bd"><div class="small" style="margin-bottom:8px">Der Assistent prüft jeden Beleg: <b>Eingangsrechnung, Ausgangsrechnung, Gehalt</b> oder Gutschrift? Er lernt aus jeder Übernahme und jeder Korrektur, kennt deine Lieferanten und warnt vor Dubletten, falschen Daten und unplausiblen Werten.</div>
    <div class="row" style="flex-wrap:wrap;align-items:center">${["ausgabe","eigene_rechnung","gehalt","einnahme","anlage"].map(k=>`<span class="badge ${TYPE_BADGE[k]}" style="flex:none">${esc(TYPES[k])}: ${pt[k]||0}</span>`).join("")}<span class="sp"></span>
      ${st.auto_eingang?`<span class="small muted" style="flex:none" title="${esc(st.eingang_dir)}">Eingangsordner wird überwacht</span>`:`<span class="small muted" style="flex:none">Eingangsordner aus</span>`}
      <button class="btn sm" style="flex:none" id="aeopen">${ic("folder")} Eingangsordner</button><button class="btn sm" style="flex:none" id="aescan">Jetzt prüfen</button></div>
    ${assistOpen?`<hr class="s"><div class="grid g2" style="align-items:start"><div><div class="small muted" style="margin-bottom:4px"><b>Bekannte Partner</b></div>${(st.top_partner||[]).map(p=>`<div class="small">${esc(p.partner)} → <b>${esc(TYPES[p.typ]||p.typ)}</b>${p.kategorie?" · "+esc(p.kategorie):""} <span class="muted">(${p.n}×)</span></div>`).join("")||`<div class="small muted">Noch nichts gelernt.</div>`}
      <div style="margin-top:10px"><button class="btn sm" id="artrain">Neu trainieren</button> <button class="btn sm" id="aset">Einstellungen</button></div></div>
      <div><div class="small muted" style="margin-bottom:4px"><b>Eingangsordner – Protokoll</b> <span class="muted">${esc(st.eingang_dir)}</span></div>${(st.log||[]).map(l=>`<div class="small"><span class="badge ${l.status==="gebucht"?"ok":"warn"}" style="padding:1px 6px">${esc(l.status)}</span> ${dde(l.datum.slice(0,10))} ${esc(l.file)} · ${esc(TYPES[l.typ]||l.typ)} · ${eur(l.betrag)} <span class="muted">${esc(l.info||"")}</span></div>`).join("")||`<div class="small muted">Noch keine Dateien verarbeitet. PDFs, die du in den Eingangsordner legst, werden automatisch eingeordnet.</div>`}</div></div>`:""}
    </div></div>`;
  $("#astog").onclick = () => { assistOpen = !assistOpen; loadAssist(); };
  $("#adup").onclick = () => dupCheck(() => vBelege());
  api("/api/dups", undefined, {quiet:true}).then(r => { const c = $("#dupcnt"); if (c && r && r.gruppen && r.gruppen.length) { c.innerHTML = `<span class="badge warn" style="cursor:pointer"><span class="dot"></span>${r.anzahl} mögliche Dublette(n)</span>`; c.onclick = () => dupCheck(() => vBelege()); } }).catch(() => {});
  $("#aeopen").onclick = () => api("/api/eingang/open", {});
  $("#aescan").onclick = async () => { const r = await api("/api/eingang/scan", {}); toast(r.n ? r.n + " Datei(en) verarbeitet" : "Keine neuen Dateien im Eingangsordner"); await reload(); vBelege(); };
  const t = $("#artrain"); if (t) t.onclick = async () => { const r = await api("/api/assist/retrain", {}); toast(`Trainiert: ${r.status.gelernt} Belege im Gedächtnis`); loadAssist(); };
  const a = $("#aset"); if (a) a.onclick = () => { setTab = "assist"; go("set"); };
}
function assistBlock(r){
  const a = r.assistent; const w = r.warnungen || [];
  let h = "";
  if (a) { const pc = Math.round((a.sicherheit||0)*100);
    h += `<div class="hl small" style="margin-bottom:8px;border-left:3px solid ${pc>=85?"var(--ok)":pc>=60?"var(--warn)":"var(--bad)"}"><b>Assistent:</b> ${esc(TYPES[a.typ]||a.typ)}${a.kategorie?" · "+esc(a.kategorie):""} – <b>${pc} % sicher</b>
      <div class="muted" style="margin-top:3px">${(a.quellen||[]).map(q=>q.fehler?`${esc(q.name)}: ${esc(q.fehler)}`:`${esc(q.name)}: ${esc(TYPES[q.typ]||q.typ||"–")}${q.kategorie&&q.typ==="ausgabe"?" ("+esc(q.kategorie)+")":""} ${Math.round((q.conf||0)*100)} %${q.begruendung?" – „"+esc(q.begruendung)+"“":""}`).join(" · ")}</div></div>`; }
  if (w.length) h += `<div class="small" style="margin-bottom:8px;padding:8px 10px;border-radius:8px;background:color-mix(in srgb, var(--warn) 14%, transparent);color:var(--ink)">${w.map(x=>`⚠ ${esc(x)}`).join("<br>")}</div>`;
  if (r.pending_id) h += `<div class="small muted" style="margin-bottom:6px">Aus dem Eingangsordner (${dde((r.eingang||"").slice(0,10))})</div>`;
  return h;
}
async function analyzeFiles(files){
  for (const f of files) {
    let r;
    try { r = await upload("/api/upload/beleg", f); } catch (e) { toast(f.name + ": konnte nicht gelesen werden", true); continue; }
    if (r.error) { toast(f.name + ": " + r.error, true); continue; }
    const items = r.items || [r];
    if (items.length > 1) toast(`${f.name}: ${items.length} Belege gefunden`);
    if (!items.length) toast(f.name + ": keine Belege darin gefunden", true);
    queue.push(...items); renderQueue();
  }
}
function lockCard(r, i){
  return `<div class="review" data-q="${i}" data-tok="${esc(r.token)}"><div><div class="thumb" style="background-image:url('/api/thumb?path=${encCss(r.tmp)}&t=${encCss(r.token)}')"></div><div class="small muted" style="margin-top:4px;word-break:break-all">${esc(r.filename)}${r.aus?`<br>aus ${esc(r.aus)}`:""}</div></div>
    <div><div class="row" style="align-items:center;margin-bottom:8px"><span class="badge warn" style="flex:none">🔒 Passwort nötig</span><span class="small" style="flex:3">${esc(r.format?r.format+": ":"")}${esc(r.hint)}</span></div>
    <div class="hl small" style="margin-bottom:10px;${r.wrong?"border-left:3px solid var(--bad)":""}">${r.wrong?"<b>Das Passwort war falsch.</b> Bitte nochmal eingeben.":`<b>${esc(r.filename)}</b> ist verschlüsselt. Gib das Passwort ein, dann liest der Assistent die Datei aus${r.container?" und holt alle Belege aus dem Archiv":""}.`}</div>
    <div class="row" style="align-items:flex-end"><label class="f">Passwort<input class="in" type="password" data-pw="${i}" autocomplete="off" placeholder="Passwort der Datei"></label>
      <label class="chk" style="flex:none;margin-bottom:9px"><input type="checkbox" data-pwm="${i}"> merken (auch für weitere Dateien)</label></div>
    <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn sm" style="flex:none" data-qx="${i}">Verwerfen</button>${r.container?"":`<button class="btn sm" style="flex:none" data-qn="${i}">Ohne Passwort ablegen</button>`}<button class="btn sm pri" style="flex:none" data-qu="${i}">🔓 Entsperren</button></div></div></div>`;
}
let unlocking = false;
async function unlockItem(tok){
  if (taking || unlocking) return;
  const i0 = qIdx(tok); if (i0 < 0) return;
  const r = queue[i0], inp = $(`[data-pw="${i0}"]`), pw = inp ? inp.value : "";
  if (!pw) { toast("Bitte Passwort eingeben", true); if (inp) inp.focus(); return; }
  unlocking = true; if (inp) inp.disabled = true;
  let res;
  try { res = await api("/api/beleg/unlock", {token:r.token, password:pw, merken:!!($(`[data-pwm="${i0}"]`)||{}).checked, pending_id:r.pending_id||null}); }
  finally { unlocking = false; if (inp) inp.disabled = false; }
  if (!res.ok) { toast(res.error, true); return; }
  syncQueue();
  const i = qIdx(tok); if (i < 0) return;
  const it = res.items || [];
  if (it.length === 1 && it[0].needs_password) { toast("Passwort falsch", true); queue[i] = it[0]; renderQueue(); const n = $(`[data-pw="${qIdx(it[0].token)}"]`); if (n) n.focus(); return; }
  if (r.pending_id) savedPending.add(r.pending_id);
  queue.splice(i, 1, ...it); toast(it.length > 1 ? `Entsperrt – ${it.length} Belege gefunden` : it.length ? "Entsperrt und ausgelesen" : "Entsperrt – keine Belege darin", !it.length); renderQueue();
}
function belegFields(r, prefix=""){
  const d = r.details || {};
  const sal = (k,l) => `<label class="f">${l}<input class="in num" data-d="${k}" value="${nde(d[k]||0)}"></label>`;
  let h = `<div class="row"><label class="f">Art<select class="in" data-k="typ">${Object.entries(TYPES).map(([k,v])=>`<option value="${k}" ${r.typ===k?"selected":""}>${v}</option>`).join("")}</select></label>
    <label class="f" style="flex:.6">Datum<input type="date" class="in" data-k="datum" value="${r.datum||todayIso()}"></label></div>`;
  if (r.typ === "eigene_rechnung") {
    const p = r.parsed;
    h += p ? `<div class="hl small"><b>Rechnung ${esc(p.nr)}</b> vom ${dde(p.datum)} · Kd-Nr. ${esc(p.kdnr)} · ${p.items.length} Position(en) · <b>${eur(p.summe)}</b><br>${p.items.map(i=>esc(i.qty+"× "+i.name)).join(", ")}</div>
      <div class="row" style="margin-top:8px"><label class="f">Status<select class="in" data-k="status"><option value="bezahlt">bezahlt</option><option value="offen">offen</option></select></label><label class="f">Bezahlt am<input type="date" class="in" data-k="bezahlt_am" value="${p.datum||""}"></label></div>` : `<div class="muted">Layout nicht lesbar.</div>`;
    return h;
  }
  h += `<div class="row"><label class="f">${r.typ==="gehalt"?"Arbeitgeber":"Partner / Lieferant"}<input class="in" data-k="partner" value="${esc(r.partner)}"></label><label class="f" style="flex:.6">Beleg-Nr.<input class="in" data-k="nr" value="${esc(r.nr)}"></label></div>`;
  if (r.typ === "gehalt") {
    h += `<div class="row"><label class="f">Zeitraum<select class="in" data-d="zeitraum"><option value="monat" ${d.zeitraum!=="jahr"?"selected":""}>Monatsabrechnung</option><option value="jahr" ${d.zeitraum==="jahr"?"selected":""}>Jahreswerte (Lohnsteuerbescheinigung)</option></select></label><label class="f">Periode<input class="in" data-dt="periode" value="${esc(d.periode||"")}"></label></div>
      <div class="row">${sal("brutto","Brutto")}${sal("lst","Lohnsteuer")}${sal("soli","Soli")}${sal("kist","Kirchensteuer")}</div>
      <div class="row">${sal("rv","RV (AN)")}${sal("kv","KV (AN)")}${sal("pv","PV (AN)")}${sal("av","AV (AN)")}${sal("netto","Netto")}</div>`;
  } else if (r.typ === "anlage") {
    h += `<label class="f">An Rechnung anhängen<select class="in" data-k="invoice_id"><option value="">– später zuordnen –</option>${(r.invoice_id && !S.invoices.slice(0,200).some(i=>i.id==r.invoice_id) ? [S.invoices.find(i=>i.id==r.invoice_id), ...S.invoices.slice(0,200)] : S.invoices.slice(0,200)).filter(Boolean).map(i=>`<option value="${i.id}" ${r.invoice_id==i.id?"selected":""}>${esc(i.nr)} · ${esc(invName(i))} · ${eur(i.summe)}</option>`).join("")}</select></label>`;
  } else {
    h += `<div class="row"><label class="f" style="flex:.6">Betrag (brutto) €<input class="in num" data-k="betrag" value="${nde(r.betrag||0)}"></label>${r.typ==="ausgabe"?`<label class="f">Kategorie (EÜR)<select class="in" data-k="kategorie">${S.kategorien.map(k=>`<option ${r.kategorie===k?"selected":""}>${k}</option>`).join("")}</select></label>`:""}</div>`;
    if (d.einvoice && d.einvoice.items && d.einvoice.items.length) h += `<div class="hl small"><b>E-Rechnung:</b> ${d.einvoice.items.slice(0,6).map(i=>esc(nde(i.qty, Number.isInteger(i.qty)?0:2)+"× "+i.name)).join(", ")}${d.einvoice.items.length>6?" …":""}</div>`;
    if (r.typ === "ausgabe" && r.token) h += `<div class="row" style="align-items:center;flex-wrap:wrap"><label class="chk" style="flex:none"><input type="checkbox" data-k="als_anlage" ${r.anlage_vorschlag||r.als_anlage?"checked":""}> als Anlagegut erfassen (AfA / Inventar)</label>
      <label class="f">Bezeichnung<input class="in" data-k="anlage_name" value="${esc(r.anlage_name||"")}" placeholder="z. B. Mischpult SQ-5"></label>
      <label class="f" style="flex:.5">Nutzungsdauer J.<input class="in num" data-k="anlage_nd" value="${r.anlage_nd||7}"></label><label class="f" style="flex:.7">Seriennr.<input class="in" data-k="anlage_sn" value="${esc(r.anlage_sn||"")}"></label></div>`;
  }
  h += `<div class="row"><label class="f">Projekt<select class="in" data-k="project_id"><option value="">–</option>${S.projects.map(p=>`<option value="${p.id}" ${r.project_id==p.id?"selected":""}>${esc(p.nr+" "+p.name)}</option>`).join("")}</select></label><label class="f">Notiz<input class="in" data-k="notiz" value="${esc(r.notiz||"")}"></label></div>`;
  return h;
}
function readBeleg(el, r){
  const d = Object.assign({}, r); d.details = Object.assign({}, r.details||{});
  $$("[data-k]", el).forEach(e => d[e.dataset.k] = e.type==="checkbox" ? e.checked : (["betrag","anlage_nd"].includes(e.dataset.k) ? pnum(e.value) : e.value));
  $$("[data-d]", el).forEach(e => d.details[e.dataset.d] = e.dataset.d==="zeitraum" ? e.value : pnum(e.value));
  $$("[data-dt]", el).forEach(e => d.details[e.dataset.dt] = e.value);
  if (d.typ === "gehalt") d.betrag = d.details.brutto || 0;
  d.invoice_id = d.invoice_id ? +d.invoice_id : null; d.project_id = d.project_id ? +d.project_id : null;
  return d;
}
function syncQueue(){
  $$("#queue [data-tok]").forEach(el => { const k = queue.findIndex(x => x.token === el.dataset.tok);
    if (k >= 0 && !queue[k].needs_password && $("[data-k=typ]", el)) queue[k] = readBeleg(el, queue[k]); });
}
function typSwitch(d, typ, old){
  d.details = Object.assign({}, d.details || {});
  if (typ === "gehalt" && old.typ !== "gehalt" && !d.details.brutto && old.betrag) { d.details.brutto = old.betrag; d.betrag = old.betrag; }
  if (old.typ === "gehalt" && typ !== "gehalt") d.betrag = d.details.brutto || old.betrag || 0;
  d.typ = typ; return d;
}
const qIdx = tok => queue.findIndex(x => x.token === tok);
function renderQueue(){
  const q = $("#queue"); if (!q) return;
  syncQueue();
  if (!queue.length) { q.innerHTML = ""; return; }
  q.innerHTML = `<div class="card" style="margin-bottom:18px"><div class="hd"><h3>Erkannt – bitte prüfen (${queue.length})</h3><div class="act"><button class="btn sm pri" id="qall">${ic("check")} Alle übernehmen</button></div></div>
    ${queue.map((r,i)=>r.needs_password ? lockCard(r,i) : `<div class="review" data-q="${i}" data-tok="${esc(r.token)}"><div><div class="thumb" data-qview="${i}" title="Klicken zum Vergrößern" style="cursor:zoom-in;background-image:url('/api/thumb?path=${encCss(r.tmp)}&t=${encCss(r.token)}')"></div><button class="btn sm ghost" data-qview="${i}" style="margin-top:6px;width:100%">🔍 Groß ansehen</button><div class="small muted" style="margin-top:4px;word-break:break-all">${esc(r.filename)}${r.aus?`<br>aus ${esc(r.aus)}`:""}${r.format&&r.format!=="PDF"?`<br>${esc(r.format)}`:""}${(r.details||{}).passwortgeschuetzt||r.ohne_pw?" · 🔒":""}</div></div>
      <div><div class="row" style="align-items:center;margin-bottom:8px"><span class="badge ${TYPE_BADGE[r.typ]}" style="flex:none">${esc(TYPES[r.typ])}</span><span class="small muted" style="flex:none">Sicherheit ${Math.round(r.confidence*100)} %</span><span class="small" style="flex:3">${esc(r.hint)}</span></div>
      ${assistBlock(r)}
      <div class="fr" data-fields>${belegFields(r)}</div>
      <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn sm" style="flex:none" data-qx="${i}">Verwerfen</button><button class="btn sm pri" style="flex:none" data-qok="${i}">${ic("check")} Übernehmen</button></div></div></div>`).join("")}</div>`;
  $$("[data-qu]").forEach(b => b.onclick = () => unlockItem(b.closest("[data-tok]").dataset.tok));
  $$("[data-pw]").forEach(inp => inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); unlockItem(inp.closest("[data-tok]").dataset.tok); } });
  $$("[data-qn]").forEach(b => b.onclick = () => { if (taking) return; const r = queue[qIdx(b.closest("[data-tok]").dataset.tok)]; if (!r) return; Object.assign(r, {needs_password:false, ohne_pw:true, hint:"Verschlüsselt abgelegt – Inhalt nicht ausgelesen, bitte Werte selbst eintragen."}); renderQueue(); });
  const fpw = $("[data-pw]"); if (fpw && !document.activeElement.matches("input,select,textarea")) fpw.focus();
  $$("[data-q]").forEach(el => { const tok = el.dataset.tok; if (!$("[data-k=typ]", el)) return;
    $("[data-k=typ]", el).onchange = e => { const k = qIdx(tok); if (k < 0) return; queue[k] = typSwitch(readBeleg(el, queue[k]), e.target.value, queue[k]); renderQueue(); }; });
  $$("[data-qx]").forEach(b => b.onclick = async () => { if (taking) return; syncQueue(); const r = queue[qIdx(b.closest("[data-tok]").dataset.tok)]; if (!r) return;
    if (r.pending_id) { if (!await confirmBox("Datei aus dem Eingang endgültig verwerfen?", "Verwerfen")) return; await api("/api/pending/discard", {id:r.pending_id}); }
    else await api("/api/beleg/discard", {token:r.token});
    syncQueue(); const k = qIdx(r.token); if (k >= 0) queue.splice(k,1); renderQueue(); });
  $$("[data-qok]").forEach(b => b.onclick = () => takeBeleg(b.closest("[data-tok]").dataset.tok));
  $$("[data-qview]").forEach(b => b.onclick = () => queueAnsicht(b.closest("[data-tok]").dataset.tok));
  $("#qall").onclick = async () => { if (taking) return; const nw = queue.filter(r => (r.warnungen||[]).length).length;
    if (nw && !await confirmBox(`${nw} Beleg(e) haben Warnungen des Assistenten (z. B. mögliche Dublette). Trotzdem alle übernehmen?`, "Alle übernehmen")) return;
    syncQueue(); taking = true; $("#qall").disabled = true; let okN = 0; const done = new Set();
    try { const items = queue.filter(r => !r.needs_password).map(r => Object.assign({}, r));
      for (const d of items) { let r; try { r = await api("/api/beleg/save", d); } catch (e) { r = {ok:false}; }
        if (r && r.ok) { okN++; done.add(d.token); if (r.info) toast(r.info); } }
      queue = queue.filter(r => !done.has(r.token));
      toast(okN + " Beleg(e) übernommen" + (okN < items.length ? ` – ${items.length-okN} fehlgeschlagen, bitte prüfen` : "") + (queue.some(r=>r.needs_password) ? " – passwortgeschützte warten noch" : ""), okN < items.length);
    } finally { taking = false; } await reload(); vBelege(); };
  selectify({kind:"queue", rows:"#queue [data-tok]", id:"data-tok", place: el => el.children[1] && el.children[1].querySelector(".row"), allBox: $("#queue .hd h3"), rerender:renderQueue, actions:[
    {label:"✓ Übernehmen", cls:"pri", run: async toks => { if (taking) return false; syncQueue(); taking = true; let okN = 0;
      try { for (const t of toks) { const k = qIdx(t); if (k < 0 || queue[k].needs_password) continue; const d = Object.assign({}, queue[k]); let r;
          try { r = await api("/api/beleg/save", d); } catch (e) { r = {ok:false}; }
          if (r && r.ok) { okN++; const j = qIdx(t); if (j >= 0) queue.splice(j, 1); savedPending.add(d.pending_id); } } }
      finally { taking = false; } toast(okN + " Beleg(e) übernommen" + (okN < toks.length ? ` – ${toks.length-okN} nicht (gesperrt oder Fehler)` : ""), okN < toks.length); await reload(); vBelege(); }},
    {label:"Art …", run: async toks => { const v = await askValue("Art für " + toks.length + " Beleg(e)", `<label class="f">Art<select class="in" id="qt">${Object.entries(TYPES).map(([k,l])=>`<option value="${k}">${esc(l)}</option>`).join("")}</select></label>`, mb => $("#qt", mb).value);
      if (v === null) return false; syncQueue(); toks.forEach(t => { const k = qIdx(t); if (k >= 0 && !queue[k].needs_password) queue[k] = typSwitch(Object.assign({}, queue[k]), v, queue[k]); }); renderQueue(); }},
    {label:"Verwerfen", cls:"danger", run: async toks => { if (taking) return false; if (!await ask(toks.length + " erkannte Datei(en) verwerfen? Dateien aus dem Eingangsordner werden dabei gelöscht.", "Verwerfen")) return false;
      syncQueue(); const items = toks.map(t => queue[qIdx(t)]).filter(Boolean);
      const pend = items.filter(r => r.pending_id).map(r => r.pending_id), tmp = items.filter(r => !r.pending_id).map(r => r.token);
      if (pend.length) await api("/api/bulk", {kind:"pending", action:"discard", ids:pend}); if (tmp.length) await api("/api/bulk", {kind:"tmp", action:"discard", ids:tmp});
      queue = queue.filter(r => !toks.includes(r.token)); toast(items.length + " verworfen"); renderQueue(); }}]});
}
let taking = false;
async function takeBeleg(tok, silent){
  if (taking) return;
  syncQueue();
  const i = qIdx(tok); if (i < 0) return;
  const w = (queue[i] && queue[i].warnungen) || [];
  if (w.length && !silent && !await confirmBox("Der Assistent hat Bedenken:\n\n" + w.map(x=>"⚠ "+x).join("\n") + "\n\nTrotzdem übernehmen?", "Übernehmen")) return;
  taking = true;
  try { await takeBelegInner(tok, silent); } finally { taking = false; }
}
async function takeBelegInner(tok, silent){
  syncQueue();
  const i = qIdx(tok); if (i < 0) return;
  const d = Object.assign({}, queue[i]);
  const r = await api("/api/beleg/save", d);
  if (r.ok) { toast(r.info || "Übernommen: " + (TYPES[d.typ]||d.typ)); syncQueue(); const k = qIdx(tok); if (k >= 0) queue.splice(k,1); savedPending.add(d.pending_id); }
  else if (r.error) toast(r.error, true);
  if (!silent) { await reload(); vBelege(); }
}
const savedPending = new Set();
// v3.6.1: big view of a queue file - compare with the recognised values, take it over from there, then on to the next one
function queueAnsicht(tok){
  if (!window.dateiAnsicht) return;
  syncQueue();
  const list = queue.filter(x => !x.needs_password), i = list.findIndex(x => x.token === tok);
  if (i < 0) return;
  const r = list[i], prev = list[i-1], next = list[i+1];
  const d = r.details || {};
  const info = `<span class="badge ${TYPE_BADGE[r.typ]||""}">${esc(TYPES[r.typ]||r.typ)}</span> `
    + [r.partner ? `<b>${esc(r.partner)}</b>` : "", r.betrag != null && r.betrag !== "" ? `<b>${eur(r.betrag)}</b>` : "", r.datum ? dde(r.datum) : "", r.nr ? "Nr. " + esc(r.nr) : "", r.kategorie ? esc(r.kategorie) : ""]
      .filter(Boolean).join(" · ") + `<span class="muted"> · ${i+1} von ${list.length}${d.passwortgeschuetzt ? " · 🔒" : ""}</span>`;
  window.dateiAnsicht(r.tmp, {titel: r.filename, info,
    zurueck: prev ? () => queueAnsicht(prev.token) : null,
    vor: next ? () => queueAnsicht(next.token) : null,
    aktionen: [{label: "Werte ändern", run: async () => { const c = $(`#queue [data-tok="${CSS.escape(tok)}"]`); if (c) { c.scrollIntoView({block:"center"}); const f = $("input,select", c.children[1]); if (f) setTimeout(() => f.focus(), 50); } }},
      {label: "✓ Übernehmen", cls: "pri", offen: true, run: async () => {
        await takeBeleg(tok);
        if (qIdx(tok) >= 0) return false;                 // not taken (warning cancelled or error) - stay on this file
        const nx = queue.find(x => !x.needs_password && list.slice(i+1).some(y => y.token === x.token)) || queue.find(x => !x.needs_password);
        if (nx) queueAnsicht(nx.token); else window.dateiAnsichtSchliessen();
      }}]});
}
async function editBeleg(b, after){
  let r = Object.assign({}, b, {details:JSON.parse(b.details||"{}")});
  const bindTyp = mb => { const sel = $("[data-k=typ]", mb); if (!sel) return;
    sel.onchange = e => { r = typSwitch(readBeleg(mb, r), e.target.value, r); $(".fr", mb).innerHTML = belegFields(r); bindTyp(mb); }; };
  await modal("Beleg bearbeiten", `<div class="fr">${belegFields(r)}</div>`, [
    {label:"Löschen", cls:"danger", onClick: async () => { if (!await confirmBox("Beleg löschen?")) return false; await api("/api/beleg/delete", {id:b.id}); }},
    ...(b.file?[{label:"PDF öffnen", onClick: async () => { await api("/api/open", {path:b.file}); return false; }}]:[]),
    {label:"Abbrechen"},
    {label:"Speichern", cls:"pri", onClick: async mb => { await api("/api/beleg/update", readBeleg(mb, r)); }}], true, bindTyp);
  await reload(); (after || vBelege)();
}

