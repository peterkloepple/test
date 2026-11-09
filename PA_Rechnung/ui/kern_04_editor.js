// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Editor fuer Rechnungen, Angebote, Gutschriften
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- editor ----------
function blankInvoice(typ="rechnung"){
  const s = S.settings;
  const gb = new Date(); gb.setDate(gb.getDate() + (s.angebot_gueltig||30));
  const top = typ==="rechnung" ? s.default_top : (s["default_top_"+typ]||""), foot = typ==="rechnung" ? s.default_foot : (s["default_foot_"+typ]||s.default_foot);
  return {id:null, typ, nr:"", customer_id:null, kdnr:"", addr:[], datum:todayIso(), liefer:typ==="angebot"?"":todayIso(), auftrag:typ==="angebot"?"":todayIso(), titel:DOCT[typ]||"Rechnung",
    toptext:top, foottext:foot, zahlart:s.zahlart||"Ueberweisung", frist:fristOf(s.frist), status:"offen", bezahlt_am:"", items:[], attachments:[], project_id:null,
    gueltig_bis: typ==="angebot" ? isoLocal(gb) : ""};
}
function newInvoice(arg){
  if (view === "editor" && cur && !cur.id && !arg && curBase !== null && curSnap() !== curBase) {
    modal("Neues Dokument", `<p style="margin:0">Das aktuelle neue Dokument ist noch nicht gespeichert.</p>`,
      [{label:"Weiter bearbeiten", value:false}, {label:"Verwerfen & neu beginnen", cls:"danger", value:true}]).then(ok => { if (ok) { curBase = null; newInvoice(); } });
    return;
  }
  pageLeave(); selClear();
  if (!arg && editorTake("new")) { view = "editor"; viewArg = null; renderSide(); vEditor(); return; }
  cur = blankInvoice((arg && arg.typ) || "rechnung"); curPk = null;
  if (arg && arg.customer_id) setCustomer(arg.customer_id);
  if (arg && arg.draft) Object.assign(cur, arg.draft);
  cur.attachments = cur.attachments || [];
  curBase = (arg && (arg.draft || arg.customer_id)) ? "" : curSnap();
  view = "editor"; viewArg = null; renderSide(); vEditor();
}
async function openInvoice(id, fresh){
  // v2.0.6: fresh = after a status change/convert on the server - never restore the stale parked copy
  if (fresh) { curBase = null; const k_ = String(id); if (KEEP.inv && KEEP.inv[k_]) { delete KEEP.inv[k_]; keepSave(); renderParkbar(); } }
  pageLeave(); selClear();
  // v2.1.0: parked changes of a document that was locked meanwhile (PDF/mail/paid from the list) cannot be saved any more
  const si_ = S.invoices.find(i => i.id == id), pk_ = KEEP.inv && KEEP.inv[String(id)];
  if (!fresh && pk_ && si_ && si_.locked && !(pk_.cur || {}).locked) { delete KEEP.inv[String(id)]; keepSave(); renderParkbar();
    toast("Das Dokument wurde inzwischen festgeschrieben – die nicht gespeicherten Änderungen wurden verworfen.", true); }
  else if (!fresh && editorTake(id)) { view = "editor"; viewArg = null; renderSide(); vEditor(); return; }
  cur = await api("/api/invoice?id="+id); curPk = null;
  cur.attachments = cur.attachments || [];
  curBase = curSnap();
  view = "editor"; viewArg = null; renderSide(); vEditor();
}
async function duplicateInvoice(id){
  pageLeave(); selClear();
  const src = await api("/api/invoice?id="+id);
  const typ = src.typ === "storno" ? "rechnung" : src.typ;
  curPk = null;
  cur = Object.assign(blankInvoice(typ), {customer_id:src.customer_id, project_id:src.project_id, kdnr:src.kdnr, addr:src.addr, titel:src.titel, toptext:src.toptext, foottext:src.foottext, zahlart:src.zahlart, frist:src.frist, font:src.font||null});
  const m = /(^|\s)(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Jan|Feb|Mär|Apr|Jun|Jul|Aug|Sept?|Okt|Nov|Dez)\.?(?=\s|$)/i;
  if (m.test(cur.titel)) cur.titel = cur.titel.replace(m, (all, pre) => pre + MONL[new Date().getMonth()]);
  cur.items = src.items.map(it => ({qty:Math.abs(it.qty), nr:it.nr, name:it.name, descr:it.descr, price:it.price, rabatt:it.rabatt, article_id:it.article_id}));
  curBase = "";
  view = "editor"; viewArg = null; renderSide(); vEditor(); toast("Kopie erstellt – neue Nummer wird beim Speichern vergeben");
}
function addrLines(c){
  if (!c) return [];
  const o = [], an = (c.anrede||"").trim();
  if (c.firma) { o.push(c.firma); if (c.name) o.push((an+" "+c.name).trim()); }
  else { if (an) o.push(an); if (c.name) o.push(c.name); }
  if (c.strasse) o.push(c.strasse);
  const po = [c.plz, c.ort].filter(Boolean).join(" "); if (po) o.push(po);
  if (c.land && !["DE","Deutschland",""].includes(c.land)) o.push(c.land);
  return o;
}
function setCustomer(id){
  const c = S.customers.find(c => c.id == id);
  cur.customer_id = c ? c.id : null; cur.kdnr = c ? c.kdnr : ""; cur.addr = addrLines(c);
}
let showPv = true;
function vEditor(){
  const s = S.settings;
  const tops = S.texts.filter(t=>t.kind==="top"), foots = S.texts.filter(t=>t.kind==="foot");
  const c = S.customers.find(c=>c.id==cur.customer_id);
  const typ = cur.typ || "rechnung";
  const ro = !!cur.locked;
  const draft = cur.status === "entwurf";
  const over = cur.id && typ==="rechnung" && cur.status==="offen" && isOverdue(cur);
  const title = cur.id ? `${DOCT[typ]} ${draft?"(Entwurf)":esc(cur.nr)}` : `Neue${typ==="rechnung"?" Rechnung":typ==="angebot"?"s Angebot":" Auftragsbestätigung"}`;
  const nrPh = {rechnung:s.next_nr, storno:s.next_nr, angebot:s.next_angnr, auftrag:s.next_abnr}[typ];
  const btns = [];
  btns.push(`<button class="btn ghost" id="tgpv">${ic("eye")} Vorschau</button>`);
  if (cur.id) btns.push(expButtons("invoice", {id:cur.id}, false, ["xlsx"]));
  if (cur.id && !draft) btns.push(`<button class="btn" id="bmail">${ic("mail")} E-Mail</button>`);
  if (cur.id) btns.push(`<button class="btn" id="bdup">${ic("copy")} Duplizieren</button>`);
  if (cur.id && ["rechnung","storno"].includes(typ) && cur.status==="offen") btns.push(`<button class="btn" id="bpaid">${ic("check")} ${typ==="storno"?"Erstattet":"Bezahlt"}</button>`);
  if (cur.id && typ==="angebot" && cur.status==="offen") btns.push(`<button class="btn ghost" id="bdecl">Abgelehnt</button>`);
  if (cur.id && typ==="angebot" && cur.status==="abgelehnt") btns.push(`<button class="btn ghost" id="breopen">Wieder offen</button>`);
  if (over) btns.push(`<button class="btn" id="bmahn">${ic("alert")} ${["Zahlungserinnerung","1. Mahnung","2. Mahnung","Letzte Mahnung"][Math.min(cur.mahnstufe||0,3)]}</button>`);
  if (cur.id && typ==="rechnung" && !draft && !cur.storno_von) btns.push(`<button class="btn danger" id="bstorno">Stornieren</button>`);
  if (cur.id && typ==="angebot") btns.push(`<button class="btn" id="b2ab">→ Auftragsbestätigung</button><button class="btn" id="b2re">→ Rechnung</button>`);
  if (cur.id && typ==="auftrag") btns.push(`<button class="btn" id="b2re">→ Rechnung</button>`);
  if (cur.id && typ==="rechnung" && !draft) btns.push(`<button class="btn ghost" id="babo" title="Als wiederkehrende Rechnung einrichten">${ic("sync")} Abo</button>`);
  if (!ro) btns.push(draft ? `<button class="btn" id="bsave">${ic("save")} Entwurf speichern</button><button class="btn pri" id="bfinal">${ic("check")} Fertigstellen</button>`
                        : `<button class="btn" id="bsave">${ic("save")} Speichern</button><button class="btn pri" id="bpdf">${ic("pdf")} Speichern & PDF</button>`);
  else btns.push(`<button class="btn pri" id="bpdfro">${ic("pdf")} PDF</button>`);
  const links = [];
  if (cur.ref) links.push(`aus <a href="#" data-inv="${cur.ref.id}">${esc(DOCT[cur.ref.typ])} ${esc(cur.ref.nr)}</a>`);
  (cur.children||[]).forEach(ch => links.push(`→ <a href="#" data-inv="${ch.id}">${esc(DOCT[ch.typ])} ${esc(ch.nr)}</a>`));
  if (cur.storno_von) links.push(`storniert durch <a href="#" data-inv="${cur.storno_von}">Storno</a>`);
  $("#main").innerHTML = `<div class="page full"><div class="ed ${showPv?"":"nopv"}">
    <div class="pal" ${ro?'style="opacity:.45;pointer-events:none"':""}>
      <div class="top"><div style="font:600 15px var(--disp)">Bausteine</div>
        <div class="search"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="palq" placeholder="Suchen …" value="${esc(palQ)}"></div>
        <div class="chips" id="palcats"></div></div>
      <div class="lst" id="pallist"></div>
    </div>
    <div class="mid"><div class="inner">
      <div class="ph" style="margin-bottom:10px"><div><h1>${title}</h1><div class="sub">${cur.id?statusBadge(cur)+" ":""}${links.join(" · ")||"Bausteine links anklicken oder in die Positionen ziehen"}</div></div>
        <div class="act">${btns.join("")}</div></div>
      ${!cur.id?`<div class="seg" id="dtyp" style="margin-bottom:14px">${[["rechnung","Rechnung"],["angebot","Angebot"],["auftrag","Auftragsbestätigung"]].map(([k,l])=>`<button data-t="${k}" class="${typ===k?"on":""}">${l}</button>`).join("")}</div>`:""}
      ${ro?`<div class="alert" style="margin-bottom:14px;cursor:default"><span>🔒 <b>Festgeschrieben</b> – ${cur.status==="bezahlt"?"bezahlt":cur.versendet_am?"versendet am "+dde(cur.versendet_am):"als PDF ausgegeben"}. Rechnungen dürfen danach nicht mehr geändert werden (GoBD). Korrektur: <b>Stornieren</b> und neu erstellen.</span></div>`:""}
      ${draft?`<div class="alert acc" style="margin-bottom:14px;cursor:default"><span>Entwurf – bekommt erst beim <b>Fertigstellen</b> eine Rechnungsnummer.</span></div>`:""}
      <fieldset id="edf" ${ro?"disabled":""} style="border:0;padding:0;margin:0;min-width:0">
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-bottom:16px">
        <div class="card"><div class="bd">
          <label class="f">Kunde</label>
          <div class="cpick" style="margin:4px 0 8px"><input class="in" id="cq" placeholder="Kunde suchen (Name, Firma, Kd-Nr.) …" value="${esc(c?cname(c)+"  ·  "+c.kdnr:"")}" autocomplete="off"><div class="dd" id="cdd" hidden></div></div>
          <label class="f">Anschrift<textarea class="in" id="addr" rows="5">${esc((cur.addr||[]).join("\n"))}</textarea></label>
          <div class="row" style="margin-top:8px"><button class="btn sm" id="newcust" type="button">${ic("plus")} Neuer Kunde</button><span class="sp"></span>
          <label class="f" style="flex:none;width:150px">Projekt<select class="in" id="proj"><option value="">– kein –</option>${S.projects.map(p=>`<option value="${p.id}" ${p.id==cur.project_id?"selected":""}>${esc(p.nr+" "+p.name)}</option>`).join("")}</select></label></div>
        </div></div>
        <div class="card"><div class="bd fr">
          <div class="row"><label class="f">${typ==="angebot"?"Angebot":typ==="auftrag"?"Auftrag":"Rechnung"} Nr.<input class="in" id="nr" value="${esc(draft?"":cur.nr)}" placeholder="${esc(nrPh||"")} (automatisch)" ${draft?"disabled":""}></label>
            <label class="f">Kunden-Nr.<input class="in" id="kdnr" value="${esc(cur.kdnr)}"></label></div>
          <div class="row"><label class="f">Datum<input type="date" class="in" id="datum" value="${cur.datum||""}"></label>
            ${typ==="angebot"?`<label class="f">Gültig bis<input type="date" class="in" id="gueltig_bis" value="${cur.gueltig_bis||""}"></label>`:`<label class="f">Lieferdatum<input type="date" class="in" id="liefer" value="${cur.liefer||""}"></label>
            <label class="f">Auftragsdatum<input type="date" class="in" id="auftrag" value="${cur.auftrag||""}"></label>`}</div>
          <div class="row"><label class="f">Titel<input class="in" id="titel" value="${esc(cur.titel)}" list="titlist"></label>
            <datalist id="titlist">${[DOCT[typ],...MONL.map(m=>DOCT[typ]+" "+m)].map(t=>`<option>${t}</option>`).join("")}</datalist>
            ${typ==="rechnung"?`<label class="f" style="flex:.45">Frist (Tage)<input class="in num" id="frist" value="${cur.frist}"></label>`:""}</div>
          ${typ==="rechnung"?`<div><div class="f" style="margin-bottom:4px;font-size:12px;color:var(--ink2);font-weight:500">Zahlart</div>
            <div class="seg" id="zahlart">${[["Ueberweisung","Überweisung + QR"],["PayPal","PayPal"],["Bar","Bar"]].map(([k,l])=>`<button type="button" data-z="${k}" class="${cur.zahlart===k?"on":""}">${l}</button>`).join("")}</div></div>`:""}
        </div></div>
      </div>
      <div class="sec"><div class="h"><b>Kopftext</b><span class="sp"></span><select class="in" id="topsel" style="width:auto;max-width:330px;padding:4px 8px;font-size:12.5px"><option value="">Textbaustein einsetzen …</option>${tops.map(t=>`<option value="${t.id}">${esc(t.text.slice(0,70))}</option>`).join("")}</select></div>
        <textarea class="in" id="toptext" rows="2">${esc(cur.toptext)}</textarea><div class="small muted" style="margin-top:3px">Platzhalter: [Frist] [Zahlungsfrist] [Rechnungsnummer] [Betrag] [Gültig]</div></div>
      <div class="sec"><div class="h"><b>Positionen</b><span class="sp"></span><button class="btn sm" id="addfree" type="button">${ic("plus")} Freie Position</button></div>
        <div class="pos" id="pos"></div></div>
      <div class="sec"><div class="h"><b>Fußtext</b><span class="sp"></span><select class="in" id="footsel" style="width:auto;max-width:330px;padding:4px 8px;font-size:12.5px"><option value="">Textbaustein einsetzen …</option>${foots.map(t=>`<option value="${t.id}">${esc(t.text.slice(0,70))}</option>`).join("")}</select></div>
        <textarea class="in" id="foottext" rows="2">${esc(cur.foottext)}</textarea></div>
      <div class="sec"><div class="h"><b>Anlagen</b><span class="small muted">PDFs werden hinten angehängt (z. B. Dozentenabrechnung, Stundennachweis)</span></div>
        <div id="atts"></div>
        <div class="dz" id="attdz" style="padding:14px"><b style="font-size:13.5px;display:inline">PDF hier ablegen</b> <span class="muted">oder</span> <button class="btn sm" id="attpick" type="button">${ic("clip")} auswählen</button></div></div>
      </fieldset>
      ${(cur.mahnungen||[]).length||(cur.mails||[]).length?`<div class="sec"><div class="h"><b>Verlauf</b></div><div class="card"><div class="bd small">
        ${(cur.mahnungen||[]).map(m=>`<div class="row" style="align-items:center;padding:3px 0">${ic("alert")}<span>${["Zahlungserinnerung","1. Mahnung","2. Mahnung","Letzte Mahnung"][Math.min(m.stufe,3)]} vom ${dde(m.datum)} · Frist ${dde(m.frist_bis)}${m.gebuehr?" · Gebühr "+eur(m.gebuehr):""}</span><span class="sp"></span><button class="btn sm ghost" data-of="${esc(m.file)}">${ic("open")}</button><button class="btn sm ghost" data-mm="${m.id}">${ic("mail")}</button></div>`).join("")}
        ${(cur.mails||[]).map(m=>`<div class="row" style="align-items:center;padding:3px 0">${ic("mail")}<span>${m.ok?"gesendet":"<b style='color:var(--bad)'>Fehler</b>"} an ${esc(m.an)} · ${esc(m.datum)}${m.fehler?" · "+esc(m.fehler):""}</span></div>`).join("")}
      </div></div></div>`:""}
    </div></div>
    <div class="pv" ${showPv?"":"hidden"}><div class="bar"><b>Live-Vorschau</b><span class="muted" id="pvinfo"></span><span class="sp"></span><span class="busy" id="busy"></span></div><div id="pvimgs"></div></div>
  </div></div>`;
  renderPalette(); renderPositions(); renderAtts(); bindEditor(); schedulePreview(0);
}
function renderPalette(){
  const cats = ["Alle", ...new Set(S.articles.filter(a=>a.active).map(a=>a.cat||"Sonstiges"))];
  $("#palcats").innerHTML = cats.map(c=>`<span class="chip ${palCat===c?"on":""}" data-c="${esc(c)}">${esc(c)}</span>`).join("");
  $$("#palcats .chip").forEach(ch => ch.onclick = () => { palCat = ch.dataset.c; renderPalette(); });
  const ql = palQ.toLowerCase();
  const arts = S.articles.filter(a => a.active && (palCat==="Alle" || (a.cat||"Sonstiges")===palCat) && (!ql || (a.nr+" "+a.name+" "+a.descr).toLowerCase().includes(ql)));
  const groups = {};
  arts.forEach(a => (groups[a.cat||"Sonstiges"] = groups[a.cat||"Sonstiges"] || []).push(a));
  $("#pallist").innerHTML = Object.entries(groups).map(([g, list]) => `<h4>${esc(g)}</h4>` + list.map(a => `
    <div class="blk" draggable="true" data-a="${a.id}" title="${esc(a.descr)}"><div style="min-width:0"><div class="n">${esc(a.name)}</div><div class="d">${esc((a.descr||"").split("\n")[0])}</div><span class="nr">${esc(a.nr)}</span></div><div class="p">${eur(a.price)}</div></div>`).join("")).join("")
    || `<div class="empty small">Keine Bausteine.<br><button class="btn sm" style="margin-top:8px" data-go="blocks">Bausteine anlegen</button></div>`;
  $$("#pallist .blk").forEach(b => {
    b.onclick = () => addArticle(+b.dataset.a);
    b.ondragstart = e => { e.dataTransfer.setData("text/article", b.dataset.a); e.dataTransfer.effectAllowed = "copy"; };
  });
  bindCommon($("#pallist"));
}
function addArticle(aid, at){
  const a = S.articles.find(a=>a.id==aid); if (!a) return;
  const it = {qty:1, nr:a.nr, name:a.name, descr:a.descr||"", price:a.price, rabatt:0, article_id:a.id};
  if (at == null) cur.items.push(it); else cur.items.splice(at, 0, it);
  renderPositions(); schedulePreview();
  const rows = $$("#pos .posrow:not(.head)"); const r = rows[at ?? rows.length-1]; if (r) { r.style.background = "var(--accsoft)"; setTimeout(()=>r.style.background="", 600); }
}
function renderPositions(){
  const el = $("#pos");
  el.innerHTML = `<div class="posrow head"><span></span><span>Anzahl</span><span>Art.-Nr.</span><span>Bezeichnung</span><span style="text-align:right">Preis</span><span style="text-align:right">Rabatt %</span><span style="text-align:right">Gesamt</span><span></span></div>` +
    cur.items.map((it,i)=>`<div class="posrow" data-i="${i}">
      <span class="hdl" draggable="true" title="Ziehen zum Sortieren">⋮⋮</span>
      <input class="in num" data-f="qty" value="${nde(it.qty, Number.isInteger(+it.qty)?0:Math.abs(+it.qty*100-Math.round(+it.qty*100))>1e-6?3:2)}">
      <input class="in" data-f="nr" value="${esc(it.nr)}">
      <input class="in" data-f="name" value="${esc(it.name)}" style="font-weight:600" placeholder="Bezeichnung">
      <input class="in num" data-f="price" value="${nde(it.price, Math.abs(+it.price*100-Math.round(+it.price*100))>1e-6?4:2)}" style="text-align:right">
      <input class="in num" data-f="rabatt" value="${it.rabatt?nde(it.rabatt):""}" style="text-align:right" placeholder="–">
      <div class="tot" data-tot="${i}">${eur(lineTotal(it))}</div>
      <button class="btn sm ghost danger" data-rm="${i}" title="Entfernen" style="padding:4px">${ic("trash")}</button>
      <div class="dsc"><textarea class="in" data-f="descr" rows="${Math.max(1,(it.descr||"").split("\n").length)}" placeholder="Beschreibung (mehrzeilig, z. B. Teilnehmer, Datum …)">${esc(it.descr)}</textarea></div></div>`).join("") +
    `<div class="posdrop" id="posdrop">${cur.items.length?"Baustein hierher ziehen zum Anhängen":"Noch keine Positionen – Baustein links anklicken oder hierher ziehen"}</div>
     <div class="sumbar"><span class="muted">${cur.items.length} Position(en)</span><span>Gesamtbetrag</span><span class="v" id="sumv">${eur(cur.items.reduce((a,it)=>a+lineTotal(it),0))}</span></div>`;
  $$("#pos .posrow:not(.head)").forEach(row => {
    const i = +row.dataset.i;
    $$("[data-f]", row).forEach(inp => {
      inp.oninput = () => {
        const f = inp.dataset.f;
        cur.items[i][f] = ["qty","price","rabatt"].includes(f) ? pnum(inp.value) : inp.value;
        if (f === "descr") inp.rows = Math.max(1, inp.value.split("\n").length);
        $(`[data-tot="${i}"]`).textContent = eur(lineTotal(cur.items[i]));
        $("#sumv").textContent = eur(cur.items.reduce((a,it)=>a+lineTotal(it),0));
        schedulePreview();
      };
    });
    const h = $(".hdl", row);
    h.ondragstart = e => { e.dataTransfer.setData("text/row", String(i)); row.classList.add("drag"); };
    h.ondragend = () => row.classList.remove("drag");
    row.ondragover = e => { e.preventDefault(); row.classList.add("over"); };
    row.ondragleave = () => row.classList.remove("over");
    row.ondrop = e => { e.preventDefault(); row.classList.remove("over");
      const a = e.dataTransfer.getData("text/article"), r = e.dataTransfer.getData("text/row");
      if (a) addArticle(+a, i);
      // dropping on a row takes that row's place (down: behind it, up: before it) - was: one row down was a no-op
      else if (r !== "") { const from = +r; if (from === i) return; const [m] = cur.items.splice(from, 1); cur.items.splice(i, 0, m); renderPositions(); schedulePreview(); } };
  });
  $$("[data-rm]").forEach(b => b.onclick = () => { cur.items.splice(+b.dataset.rm, 1); renderPositions(); schedulePreview(); });
  const pd = $("#posdrop");
  pd.ondragover = e => { e.preventDefault(); pd.classList.add("over"); };
  pd.ondragleave = () => pd.classList.remove("over");
  pd.ondrop = e => { e.preventDefault(); pd.classList.remove("over"); const a = e.dataTransfer.getData("text/article"), r = e.dataTransfer.getData("text/row");
    if (a) addArticle(+a); else if (r !== "") { const [m] = cur.items.splice(+r,1); cur.items.push(m); renderPositions(); schedulePreview(); } };
}
function renderAtts(){
  $("#atts").innerHTML = (cur.attachments||[]).map(a=>`<div class="row" style="align-items:center;padding:7px 10px;background:#fff;border:1px solid var(--line);border-radius:9px;margin-bottom:6px">
    ${ic("clip")}<span style="flex:1">${esc(a.partner||String(a.file||"").split(/[\\/]/).pop())}</span><button class="btn sm ghost" data-oa="${esc(a.file)}">${ic("open")}</button><button class="btn sm ghost danger" data-ra="${a.id}">${ic("trash")}</button></div>`).join("");
  $$("[data-oa]").forEach(b => b.onclick = () => api("/api/open", {path:b.dataset.oa}));
  $$("[data-ra]").forEach(b => b.onclick = async () => { await api("/api/anlage/remove", {id:+b.dataset.ra}); cur.attachments = cur.attachments.filter(a=>a.id!=b.dataset.ra); renderAtts(); schedulePreview(); });
}
function bindEditor(){
  const bind = (id, f, num) => { const e = $("#"+id); if (!e) return; e.oninput = () => { cur[f] = num ? pnum(e.value) : e.value; schedulePreview(); }; };
  ["nr","kdnr","datum","liefer","auftrag","titel","toptext","foottext","gueltig_bis"].forEach(k => bind(k, k));
  bind("frist","frist",true);
  bindCommon($(".mid"));
  $("#addr").oninput = e => { cur.addr = e.target.value.split("\n").filter(l=>l.trim()!==""); schedulePreview(); };
  $("#proj").onchange = e => cur.project_id = e.target.value ? +e.target.value : null;
  $$("#zahlart button").forEach(b => b.onclick = () => { cur.zahlart = b.dataset.z; $$("#zahlart button").forEach(x=>x.classList.toggle("on", x===b)); schedulePreview(); });
  $$("#dtyp button").forEach(b => b.onclick = () => { const keep = {customer_id:cur.customer_id, kdnr:cur.kdnr, addr:cur.addr, items:cur.items, project_id:cur.project_id, attachments:cur.attachments};
    cur = Object.assign(blankInvoice(b.dataset.t), keep); vEditor(); });
  $("#topsel").onchange = e => { const t = S.texts.find(t=>t.id==e.target.value); if (t) { cur.toptext = t.text; $("#toptext").value = t.text; schedulePreview(); } e.target.value=""; };
  $("#footsel").onchange = e => { const t = S.texts.find(t=>t.id==e.target.value); if (t) { cur.foottext = t.text; $("#foottext").value = t.text; schedulePreview(); } e.target.value=""; };
  $("#palq").oninput = e => { palQ = e.target.value; renderPalette(); };
  $("#addfree").onclick = () => { cur.items.push({qty:1, nr:"", name:"", descr:"", price:0, rabatt:0}); renderPositions(); $$("#pos [data-f=name]").pop().focus(); };
  $("#tgpv").onclick = () => { showPv = !showPv; vEditor(); };
  const on = (id, fn) => { const e = $("#"+id); if (e) e.onclick = fn; };
  on("bsave", () => saveInvoice(false));
  on("bpdf", () => saveInvoice(true));
  on("bfinal", () => saveInvoice(false, true));
  on("bpdfro", async () => { const r = await api("/api/invoice/export", {id:cur.id}); if (r.ok) toast("PDF: " + r.path.split(/[\\/]/).pop()); });
  on("bdup", () => duplicateInvoice(cur.id));
  on("bmail", async () => { if (!cur.locked && !(await saveInvoice(false, false, true))) return; mailDialog({doc_id:cur.id}); });
  on("bpaid", async () => { if (!cur.locked) { const r = await api("/api/invoice/save", cur); if (!r.ok) return; } await markPaid(cur.id); openInvoice(cur.id, true); });
  // save pending edits first - afterwards the editor reloads fresh (with the new reminder), not the stale parked copy
  on("bmahn", async () => { if (!cur.locked && curBase !== null && curSnap() !== curBase && !(await saveInvoice(false, false, true))) return; makeMahnung(cur.id); });
  on("bdecl", async () => { if (!cur.locked) { const r0 = await api("/api/invoice/save", cur); if (!r0.ok) return; } await api("/api/invoice/offer_status", {id:cur.id, status:"abgelehnt"}); await reload(); openInvoice(cur.id, true); });
  on("breopen", async () => { if (!cur.locked) { const r0 = await api("/api/invoice/save", cur); if (!r0.ok) return; } await api("/api/invoice/offer_status", {id:cur.id, status:"offen"}); await reload(); openInvoice(cur.id, true); });
  on("bstorno", async () => { if (!await confirmBox(`Rechnung ${cur.nr} stornieren? Es wird eine Storno-Rechnung mit eigener Nummer erzeugt.`, "Stornieren")) return;
    const r = await api("/api/invoice/storno", {id:cur.id}); if (r.ok) { toast("Storno-Rechnung " + r.nr + " erstellt"); await reload(); openInvoice(r.id); } });
  on("b2ab", () => convertDoc("auftrag"));
  on("b2re", () => convertDoc("rechnung"));
  on("babo", () => aboDialog({invoice_id:cur.id, name:invName(cur)+" – "+(cur.titel||""), intervall:1}));
  on("newcust", async () => { const id = await editCustomer({}); if (id) { setCustomer(id); vEditor(); } });
  $$("[data-of]").forEach(b => b.onclick = () => api("/api/open", {path:b.dataset.of}));
  $$("[data-mm]").forEach(b => b.onclick = () => mailDialog({mahnung_id:+b.dataset.mm}));
  const cq = $("#cq"), dd = $("#cdd"); let sel = 0, res = [];
  const draw = () => { const ql = cq.value.toLowerCase().replace(/\s+·.*$/,"");
    res = S.customers.filter(c => !ql || (c.kdnr+" "+c.firma+" "+c.name+" "+c.ort).toLowerCase().includes(ql)).slice(0, 30);
    dd.innerHTML = res.map((c,i)=>`<div class="${i===sel?"on":""}" data-c="${c.id}"><b>${esc(cname(c))}</b>${c.firma&&c.name?`<span class="muted">${esc(c.name)}</span>`:""}<small>${esc(c.kdnr)} · ${esc(c.ort||"")}</small></div>`).join("") || `<div class="muted">Kein Treffer</div>`;
    dd.hidden = false; $$("[data-c]", dd).forEach(d => d.onmousedown = () => pick(+d.dataset.c)); };
  const pick = id => { setCustomer(id); dd.hidden = true; vEditor(); };
  cq.onfocus = () => { cq.select(); draw(); }; cq.oninput = () => { sel = 0; draw(); }; cq.onblur = () => setTimeout(()=>dd.hidden=true, 150);
  cq.onkeydown = e => { if (e.key==="ArrowDown"){sel=Math.min(sel+1,res.length-1);draw();e.preventDefault();} if (e.key==="ArrowUp"){sel=Math.max(0,sel-1);draw();e.preventDefault();} if (e.key==="Enter"&&res[sel]) pick(res[sel].id); };
  const dz = $("#attdz");
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); if (!cur.locked) addAttachments([...e.dataTransfer.files]); };
  $("#attpick").onclick = () => pickFiles(".pdf", addAttachments);
  document.onkeydown = e => { if (view==="editor" && !cur.locked && (e.ctrlKey||e.metaKey) && e.key.toLowerCase()==="s") { e.preventDefault(); saveInvoice(false); } };
}
async function addAttachments(files){
  for (const f of files) {
    if (!/\.pdf$/i.test(f.name)) { toast(f.name + ": nur PDF möglich", true); continue; }
    let r;
    try { r = await upload("/api/upload/anlage", f, {"X-Invoice": String(cur.id||0)}); } catch (e) { r = {ok:false}; }
    if (!r || !r.ok || !r.id) { toast(f.name + ": " + ((r && r.error) || "Anlage konnte nicht hochgeladen werden"), true); continue; }
    cur.attachments.push({id:r.id, file:r.file, partner:r.partner, pending:!cur.id});
  }
  renderAtts(); schedulePreview();
}
// v1.6.4: native Windows-Dialog, startet immer im Ordner "Downloads"
let picking = false;
function pickFilesHtml(accept, cb){
  const fp = $("#filepick"); fp.accept = accept || ""; fp.value = "";
  fp.onchange = () => cb([...fp.files]); fp.click();
}
async function pickFiles(accept, cb, multiple=true){
  if (picking) return; picking = true;
  let r;
  try { r = await api("/api/pick", {accept:accept||"", multiple}, {quiet:true}); } finally { picking = false; }
  if (!r || r.native === false) return pickFilesHtml(accept, cb);
  if (!r.ok || !r.files || !r.files.length) return;
  const files = [];
  for (const f of r.files) {
    const res = await fetch("/api/pickfile?path=" + encodeURIComponent(f.path));
    if (!res.ok) { toast(f.name + ": konnte nicht gelesen werden", true); continue; }
    const b = await res.blob();
    files.push(new File([b], f.name, {type:b.type||""}));
  }
  if (files.length) cb(files);
}
async function pickFolder(){
  const r = await api("/api/pick", {folder:true, multiple:false}, {quiet:true});
  return r && r.ok && r.paths && r.paths[0] ? r.paths[0] : "";
}
// folder fields: add a "..." button that opens the folder dialog (starts in Downloads)
function bindFolderFields(root=document){
  ["pdf_dir","eingang_dir","backup_target"].forEach(k => {
    const el = root.querySelector(`[data-s="${k}"]`); if (!el || el.dataset.fb) return; el.dataset.fb = "1";
    const b = document.createElement("button"); b.type = "button"; b.className = "btn sm"; b.textContent = "Durchsuchen …"; b.style.marginTop = "4px";
    b.onclick = async () => { const p = await pickFolder(); if (p) { el.value = p; TOUCHED.add(el); el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); } };
    el.insertAdjacentElement("afterend", b);
  });
}
function schedulePreview(ms=450){
  if (!showPv) return;
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    const b = $("#busy"); if (b) b.classList.add("on");
    const seq = ++pvSeq;
    const r = await api("/api/invoice/preview", cur, {quiet:true});
    if (!$("#pvimgs") || seq !== pvSeq) return;   // v2.1.0: an older, slower answer must not replace the newer preview
    if (b) b.classList.remove("on");
    if (r.pages) { $("#pvimgs").innerHTML = Array.from({length:r.pages}, (_,i)=>`<img src="/preview/${r.token}/${i}.png">`).join("");
      $("#pvinfo").textContent = `${r.pages} Seite(n) · ${eur(r.summe)}`; }
    else $("#pvimgs").innerHTML = `<div class="empty">Vorschau nicht verfügbar (pypdfium2 fehlt).</div>`;
  }, ms);
}
let saving = false;
async function saveInvoice(pdf, finalize=false, silent=false){
  if (saving) return false;
  saving = true;
  // only the parked copy of THIS document (was: fallback "new" deleted another parked new document)
  const k0 = cur && (cur.id || curPk);
  try { const ok = await saveInvoiceInner(pdf, finalize, silent);
    if (ok) { curBase = curSnap(); curPk = null; if (k0 && KEEP.inv[k0]) { delete KEEP.inv[k0]; keepSave(); renderParkbar(); } }
    return ok; } finally { saving = false; }
}
async function saveInvoiceInner(pdf, finalize=false, silent=false){
  // v2.0.17: empty documents (blank forms) may be saved and printed
  const body = Object.assign({}, cur, {finalize});
  const r = await api("/api/invoice/save", body);
  if (!r.ok) return false;
  for (const a of (cur.attachments||[]).filter(a=>a.pending)) await api("/api/beleg/update", Object.assign({}, S.belege.find(b=>b.id==a.id)||{typ:"anlage",datum:todayIso(),partner:a.partner,details:{}}, {id:a.id, typ:"anlage", invoice_id:r.id}));
  // v2.0.6: one reload + one fetch (was 2x each with PDF)
  let e_ = null;
  if (pdf) e_ = await api("/api/invoice/export", {id:r.id});
  await reload();
  cur = await api("/api/invoice?id="+r.id);
  if (pdf) { if (e_ && e_.ok) toast("Gespeichert & PDF erstellt: " + e_.path.split(/[\\/]/).pop()); }
  else if (!silent) toast((finalize?"Fertiggestellt: ":"Gespeichert: ") + (cur.status==="entwurf"?"Entwurf":r.nr));
  vEditor();
  return true;
}
