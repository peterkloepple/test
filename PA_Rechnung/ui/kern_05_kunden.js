// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Kunden und Bausteine
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- customers ----------
let custSel = null, custQ = "";
let custSort = (() => { try { return JSON.parse(localStorage.getItem("pa_custsort") || "null") || {k:"", d:1}; } catch (e) { return {k:"", d:1}; } })();
async function vCustomers(arg){
  if (arg) custSel = arg;
  const ql = custQ.toLowerCase();
  const list = S.customers.filter(c => !ql || (c.kdnr+" "+c.firma+" "+c.name+" "+c.ort+" "+c.mail).toLowerCase().includes(ql));
  const umsOf = id => S.invoices.filter(i=>i.customer_id==id && ["rechnung","storno"].includes(i.typ) && !["entwurf","storniert"].includes(i.status)).reduce((a,i)=>a+i.summe,0);
  const coll = new Intl.Collator("de", {numeric:true, sensitivity:"base"});
  const cs = custSort.k, cd = custSort.d;
  if (cs === "nr") list.sort((a,b)=>cd*coll.compare(a.kdnr||"", b.kdnr||""));
  else if (cs === "ort") list.sort((a,b)=>cd*coll.compare(a.ort||"~", b.ort||"~") || coll.compare(cname(a), cname(b)));
  else if (cs === "ums") { const u = new Map(list.map(c=>[c.id, umsOf(c.id)])); list.sort((a,b)=>cd*(u.get(b.id)-u.get(a.id))); }
  else if (cs === "name") list.sort((a,b)=>cd*coll.compare(cname(a), cname(b)));
  if (!custSel && list.length) custSel = list[0].id;
  const c = S.customers.find(c=>c.id==custSel);
  const invs = c ? S.invoices.filter(i=>i.customer_id==c.id && ["rechnung","storno"].includes(i.typ) && !["entwurf","storniert"].includes(i.status) && !i.storno_von) : [];
  const byYear = {}; invs.forEach(i => byYear[i.datum.slice(0,4)] = (byYear[i.datum.slice(0,4)]||0) + i.summe);
  const maxY = Math.max(1, ...Object.values(byYear));
  const projs = c ? S.projects.filter(p=>p.customer_id==c.id) : [];
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Kunden", `${S.customers.length} Kunden in der Datenbank`, expButtons("customers") + `<button class="btn pri" id="cnew">${ic("plus")} Neuer Kunde</button>`)}
    <div class="split">
      <div class="card" style="overflow:hidden"><div class="bd" style="padding:10px"><div class="search"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="custq" placeholder="Suchen …" value="${esc(custQ)}"></div>
          <div class="seg" style="margin-top:8px;display:flex">${[["name","Name"],["nr","Kd-Nr."],["ort","Ort"],["ums","Umsatz"]].map(([k,l])=>`<button style="flex:1" class="${custSort.k===k?"on":""}" data-csort="${k}">${l}${custSort.k===k?(custSort.d>0?" ▲":" ▼"):""}</button>`).join("")}</div></div>
        <div class="list scroll" style="max-height:calc(100vh - 210px)">${list.map(k=>`<div class="it ${k.id==custSel?"on":""}" data-c="${k.id}"><div class="av">${esc(initials(cname(k)))}</div><div style="min-width:0;flex:1"><b>${esc(cname(k))}</b><div class="small muted">${esc(k.kdnr)}${k.ort?" · "+esc(k.ort):""}</div></div></div>`).join("")}</div></div>
      <div>${c ? `
        <div class="card" style="margin-bottom:16px"><div class="hd"><div class="av" style="width:44px;height:44px;font-size:16px">${esc(initials(cname(c)))}</div><div><h3 style="font-size:18px">${esc(cname(c))}</h3><div class="small muted">Kd-Nr. ${esc(c.kdnr)}${c.gruppe?" · "+esc(c.gruppe):""}</div></div>
          <div class="act">${expButtons("customer", {id:c.id}, true)}<button class="btn" id="cedit">Bearbeiten</button><button class="btn pri" id="cinv">${ic("plus")} Rechnung</button><button class="btn ghost danger" id="cdel">${ic("trash")}</button></div></div>
          <div class="bd grid g3">
            <div><div class="small muted">Anschrift</div><div style="white-space:pre-line">${esc(addrLines(c).join("\n"))}</div></div>
            <div><div class="small muted">Kontakt</div>${c.tel?`<div>☎ ${esc(c.tel)}</div>`:""}${c.mobil?`<div>📱 ${esc(c.mobil)}</div>`:""}${c.mail?`<div>✉ ${esc(c.mail)}</div>`:""}${c.web?`<div>🌐 ${esc(c.web)}</div>`:""}</div>
            <div><div class="small muted">Notiz</div><div style="white-space:pre-line">${esc(c.notiz||"–")}</div></div>
          </div></div>
        <div class="grid g3" style="margin-bottom:16px">
          <div class="card kpi"><div class="l">Umsatz gesamt</div><div class="v">${eur(invs.reduce((a,i)=>a+i.summe,0))}</div><div class="s">${invs.length} Rechnungen</div></div>
          <div class="card kpi"><div class="l">Umsatz ${thisYear}</div><div class="v">${eur(byYear[thisYear]||0)}</div><div class="s">${invs.filter(i=>i.datum.startsWith(thisYear)).length} Rechnungen</div></div>
          <div class="card kpi"><div class="l">Offen</div><div class="v">${eur(invs.filter(i=>i.status==="offen").reduce((a,i)=>a+i.summe,0))}</div><div class="s">${invs.filter(i=>i.status==="offen").length} Rechnung(en)</div></div>
        </div>
        <div class="grid" style="grid-template-columns:1.4fr 1fr">
          <div class="card" style="overflow:hidden"><div class="hd"><h3>Rechnungen</h3></div><div class="scroll" style="max-height:380px"><table class="t"><tbody>${invs.map(i=>`<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b></td><td class="num">${dde(i.datum)}</td><td class="muted">${esc(i.titel)}</td><td>${statusBadge(i)}</td><td class="r num">${eur(i.summe)}</td></tr>`).join("") || `<tr><td class="empty">Noch keine Rechnungen</td></tr>`}</tbody></table></div></div>
          <div class="card"><div class="hd"><h3>Umsatz pro Jahr</h3></div><div class="bd">${Object.entries(byYear).sort().reverse().map(([y,v])=>`<div class="hbar"><span class="lb">${y}</span><div class="tr"><div class="fl" style="width:${100*v/maxY}%"></div></div><span class="r num">${eur(v)}</span></div>`).join("") || `<div class="muted">–</div>`}
            ${projs.length?`<hr class="s"><div class="small muted" style="margin-bottom:6px">Projekte</div>${projs.map(p=>`<div class="list"><div class="it" data-proj="${p.id}" style="padding:6px 0"><span class="badge" style="background:${BEREICH_COL[p.bereich]}22;color:${BEREICH_COL[p.bereich]}">${esc(p.bereich)}</span><b>${esc(p.name)}</b></div></div>`).join("")}`:""}</div></div>
        </div>` : `<div class="card empty">Noch keine Kunden.</div>`}</div>
    </div></div>`;
  bindCommon();
  $("#custq").oninput = e => { custQ = e.target.value; debRender("custq", vCustomers); };
  $$("[data-csort]").forEach(b => b.onclick = () => { const k = b.dataset.csort; custSort = custSort.k !== k ? {k, d:1} : custSort.d > 0 ? {k, d:-1} : {k:"", d:1};
    try { localStorage.setItem("pa_custsort", JSON.stringify(custSort)); } catch (e) {} vCustomers(); });
  $$("[data-c]").forEach(r => r.onclick = () => { custSel = +r.dataset.c; vCustomers(); });
  selectify({kind:"customer", rows:".list .it[data-c]", id:"data-c", rerender:() => vCustomers(), actions:[
    {label:"Gruppe …", run: async ids => { const v = await askValue("Gruppe für " + ids.length + " Kunde(n)", `<label class="f">Gruppe<input class="in" id="cg" list="cgl"><datalist id="cgl">${[...new Set(S.customers.map(c=>c.gruppe).filter(Boolean))].map(g=>`<option>${esc(g)}</option>`).join("")}</datalist></label>`, mb => $("#cg", mb).value);
      if (v === null) return false; await bulk("customer", "gruppe", ids, v); await reload(); vCustomers(); }},
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Kunde(n) löschen? Kunden mit Rechnungen bleiben erhalten.")) return false;
      await bulk("customer", "delete", ids); if (ids.includes(String(custSel))) custSel = null; await reload(); vCustomers(); }}]});
  $("#cnew").onclick = async () => { const id = await editCustomer({}); if (id) { custSel = id; vCustomers(); } };
  if (c) {
    $("#cedit").onclick = async () => { if (await editCustomer(c)) vCustomers(); };
    $("#cinv").onclick = () => newInvoice({customer_id:c.id});
    $("#cdel").onclick = async () => { if (await confirmBox(`Kunde ${cname(c)} löschen?`)) { const r = await api("/api/customer/delete", {id:c.id}); if (r.ok) { custSel = null; await reload(); vCustomers(); } } };
  }
}
async function editCustomer(c){
  const f = (k,l,ph="") => `<label class="f">${l}<input class="in" data-k="${k}" value="${esc(c[k]||"")}" placeholder="${ph}"></label>`;
  let saved = null;
  await modal(c.id ? "Kunde bearbeiten" : "Neuer Kunde", `<div class="fr">
    <div class="row">${f("kdnr","Kunden-Nr.", S.settings.next_kdnr+" (automatisch)")}${f("gruppe","Gruppe","Kunden")}</div>
    <div class="row"><label class="f" style="flex:.5">Anrede<select class="in" data-k="anrede">${["","Herrn","Frau","Familie","Firma"].map(a=>`<option ${c.anrede===a?"selected":""}>${a}</option>`).join("")}</select></label>${f("firma","Firma")}</div>
    ${f("name","Name / Ansprechpartner")}${f("strasse","Straße")}
    <div class="row"><div style="flex:.4">${f("plz","PLZ")}</div>${f("ort","Ort")}<div style="flex:.4">${f("land","Land","DE")}</div></div>
    <div class="row">${f("tel","Telefon")}${f("mobil","Mobil")}</div><div class="row">${f("mail","E-Mail")}${f("web","Web")}</div>
    <label class="f">Notiz<textarea class="in" data-k="notiz">${esc(c.notiz||"")}</textarea></label></div>`,
    [{label:"Abbrechen"},{label:"Speichern", cls:"pri", onClick: async mb => {
      const d = Object.assign({}, c); $$("[data-k]", mb).forEach(e => d[e.dataset.k] = e.value.trim());
      if (!d.name && !d.firma) { toast("Name oder Firma angeben", true); return false; }
      const r = await api("/api/customer/save", d); if (!r.ok) return false; saved = r.id; }}]);
  if (saved) await reload();
  return saved;
}

// ---------- bausteine ----------
let blkTab = "art", blkCat = "Alle";
function vBlocks(){
  const cats = ["Alle", ...new Set(S.articles.map(a=>a.cat||"Sonstiges"))];
  const arts = S.articles.filter(a => blkCat==="Alle" || (a.cat||"Sonstiges")===blkCat);
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Bausteine", "Produkte, Dienstleistungen und Textbausteine für deine Rechnungen", expButtons("articles") + (blkTab==="art"?`<button class="btn pri" id="anew">${ic("plus")} Neuer Baustein</button>`:`<button class="btn pri" id="tnew">${ic("plus")} Neuer Textbaustein</button>`))}
    <div class="tabs"><div class="tab ${blkTab==="art"?"on":""}" data-t="art">Leistungen & Produkte<span class="cnt">${S.articles.length}</span></div><div class="tab ${blkTab==="txt"?"on":""}" data-t="txt">Textbausteine<span class="cnt">${S.texts.length}</span></div></div>
    ${blkTab==="art" ? `<div class="chips" style="margin-bottom:12px">${cats.map(c=>`<span class="chip ${blkCat===c?"on":""}" data-c="${esc(c)}">${esc(c)}</span>`).join("")}</div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th style="width:80px">Art.-Nr.</th><th>Bezeichnung</th><th>Beschreibung</th><th style="width:130px">Kategorie</th><th style="width:80px">Einheit</th><th class="r" style="width:110px">Preis</th><th style="width:60px">Aktiv</th><th style="width:44px"></th></tr></thead>
    <tbody>${arts.map(a=>`<tr data-a="${a.id}"><td><input class="in" data-k="nr" value="${esc(a.nr)}"></td><td><input class="in" data-k="name" value="${esc(a.name)}" style="font-weight:600"></td>
      <td><textarea class="in" data-k="descr" rows="1" style="min-height:34px">${esc(a.descr)}</textarea></td><td><input class="in" data-k="cat" value="${esc(a.cat)}" list="catlist"></td><td><input class="in" data-k="unit" value="${esc(a.unit)}"></td>
      <td><input class="in num" data-k="price" value="${nde(a.price)}" style="text-align:right"></td><td><input type="checkbox" class="chk" data-k="active" ${a.active?"checked":""} style="width:17px;height:17px;accent-color:var(--acc)"></td>
      <td><button class="btn sm ghost danger" data-del="${a.id}">${ic("trash")}</button></td></tr>`).join("")}</tbody></table>
      <datalist id="catlist">${[...new Set(S.articles.map(a=>a.cat))].map(c=>`<option>${esc(c)}</option>`).join("")}</datalist></div>
    <div class="small muted" style="margin-top:8px">Änderungen werden beim Verlassen eines Feldes automatisch gespeichert.</div>`
    : `<div class="grid g2">${["top","foot"].map(k=>`<div class="card"><div class="hd"><h3>${k==="top"?"Kopftexte":"Fußtexte"}</h3></div><div class="bd fr">${S.texts.filter(t=>t.kind===k).map(t=>`<div class="row" style="align-items:flex-start"><textarea class="in" data-t="${t.id}" data-kind="${k}" rows="2">${esc(t.text)}</textarea><button class="btn sm ghost danger" style="flex:none" data-tdel="${t.id}">${ic("trash")}</button></div>`).join("")}</div></div>`).join("")}</div>
      <div class="small muted" style="margin-top:8px">Platzhalter: [Frist] [Zahlungsfrist] [Rechnungsnummer] [Betrag]</div>`}</div>`;
  $$("[data-t]").forEach(t => { if (t.classList.contains("tab")) t.onclick = () => { blkTab = t.dataset.t; vBlocks(); }; });
  $$(".chip[data-c]").forEach(c => c.onclick = () => { blkCat = c.dataset.c; vBlocks(); });
  if (blkTab === "art") selectify({kind:"article", rows:"tr[data-a]", id:"data-a", rerender:vBlocks, actions:[
    {label:"Aktivieren", run: async ids => { await bulk("article", "aktiv", ids); await reload(); vBlocks(); }},
    {label:"Deaktivieren", run: async ids => { await bulk("article", "inaktiv", ids); await reload(); vBlocks(); }},
    {label:"Kategorie …", run: async ids => { const v = await askValue("Kategorie für " + ids.length + " Baustein(e)", `<label class="f">Kategorie<input class="in" id="ac" list="catlist2"><datalist id="catlist2">${[...new Set(S.articles.map(a=>a.cat))].map(c=>`<option>${esc(c)}</option>`).join("")}</datalist></label>`, mb => $("#ac", mb).value);
      if (v === null) return false; await bulk("article", "kategorie", ids, v); await reload(); vBlocks(); }},
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Baustein(e) löschen?")) return false; await bulk("article", "delete", ids); await reload(); vBlocks(); }}]});
  $$("tr[data-a]").forEach(tr => {
    $$("[data-k]", tr).forEach(inp => inp.onchange = async () => {
      const a = S.articles.find(a=>a.id==tr.dataset.a);
      $$("[data-k]", tr).forEach(e => a[e.dataset.k] = e.type==="checkbox" ? (e.checked?1:0) : (e.dataset.k==="price" ? pnum(e.value) : e.value));
      await api("/api/article/save", a); toast("Gespeichert");
    });
  });
  $$("[data-del]").forEach(b => b.onclick = async () => { if (await confirmBox("Baustein löschen?")) { await api("/api/article/delete", {id:+b.dataset.del}); await reload(); vBlocks(); } });
  if ($("#anew")) $("#anew").onclick = async () => { await api("/api/article/save", {nr:"", name:"Neuer Baustein", descr:"", price:0, unit:"Stk", cat: blkCat==="Alle"?"Sonstiges":blkCat, active:1, sort:999}); await reload(); vBlocks(); const ins = $$("tr[data-a] [data-k=name]"); const last = ins[ins.length-1]; if (last) { last.focus(); last.select(); } };
  if ($("#tnew")) $("#tnew").onclick = async () => { const k = await modal("Neuer Textbaustein", `<div class="fr"><select class="in" id="tk"><option value="top">Kopftext</option><option value="foot">Fußtext</option></select><textarea class="in" id="tt" rows="3"></textarea></div>`,
    [{label:"Abbrechen"},{label:"Anlegen", cls:"pri", onClick: async mb => { await api("/api/text/save", {kind:$("#tk",mb).value, text:$("#tt",mb).value}); }, value:true}]); if (k) { await reload(); vBlocks(); } };
  $$("textarea[data-t]").forEach(t => t.onchange = async () => { await api("/api/text/save", {id:+t.dataset.t, kind:t.dataset.kind, text:t.value}); await reload(); toast("Gespeichert"); });
  $$("[data-tdel]").forEach(b => b.onclick = async () => { await api("/api/text/delete", {id:+b.dataset.tdel}); await reload(); vBlocks(); });
}

