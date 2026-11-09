// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Unterricht
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---- Unterricht v1.2.0 ----
let schY = new Date().getFullYear(), schM = new Date().getMonth()+1, schTab = "cal", schPayer = "";
const custName = id => { const c = S.customers.find(c=>c.id==id); return c ? cname(c) : ""; };
const artName = id => { const a = S.articles.find(a=>a.id==id); return a ? a.name+" · "+eur(a.price) : "–"; };
async function vSchool(){
  const data = await api(`/api/unterricht/month?year=${schY}&month=${schM}`);
  const payers = data.payers || {};
  const openN = Object.values(payers).reduce((a,b)=>a+b,0);
  const tabs = [["cal","Kalender"],["kurse","Kurse"],["st","Schüler"],["dat","Dateien"]];   // v2.0.7: Dateien
  const head = pageHead("Unterricht", "Kurse und Schüler aus deinen Kunden – Stunden abhaken, am Monatsende automatisch abrechnen",
    expButtons("unterricht", () => ({year:schY})) + `<button class="btn" id="knew">${ic("plus")} Kurs</button><button class="btn" id="snew">${ic("plus")} Schüler</button>`)
    + `<div class="tabs">${tabs.map(([k,l])=>`<div class="tab ${schTab===k?"on":""}" data-stab="${k}">${l}<span class="cnt">${k==="kurse"?S.kurse.filter(k=>k.aktiv).length:k==="st"?S.students.filter(s=>s.aktiv).length:k==="dat"?Object.values(S.unt_counts||{}).reduce((a,b)=>a+b,0):openN}</span></div>`).join("")}</div>`;
  let body = "";
  if (schTab === "cal") body = schoolCal(data, payers);
  if (schTab === "kurse") body = schoolKurse();
  if (schTab === "st") body = schoolStudents();
  if (schTab === "dat") body = `<div id="untfiles"></div>`;
  $("#main").innerHTML = `<div class="page">${head}${body}</div>`;
  if (schTab === "dat" && window.untFilesRender) await untFilesRender($("#untfiles"));
  $$("[data-stab]").forEach(t => t.onclick = () => { schTab = t.dataset.stab; vSchool(); });
  $("#knew").onclick = () => editKurs({modus:"monat", dauer:1, aktiv:1});
  $("#snew").onclick = () => editStudent({modus:"monat", dauer:1, aktiv:1});
  bindSchool(data, payers);
}
function schoolCal(data, payers){
  const days = new Date(schY, schM, 0).getDate();
  const iso = d => `${schY}-${String(schM).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
  const wd = d => new Date(schY, schM-1, d).getDay();
  const L = {}; data.lessons.forEach(l => L[(l.kurs_id||0)+"|"+l.student_id+"|"+l.datum] = l);
  const KT = {}; (data.kurs_termine||[]).forEach(t => KT[t.kurs_id+"|"+t.datum] = t);   // v2.6.5: course dates (also without members)
  const stById = {}; data.students.forEach(s => stById[s.id] = s);
  const kurse = data.kurse.filter(k => k.aktiv || data.lessons.some(l=>l.kurs_id===k.id));
  const memOf = kid => data.members.filter(m=>m.kurs_id===kid).map(m=>stById[m.student_id]).filter(Boolean).sort((a,b)=>a.name.localeCompare(b.name));
  const inCourse = new Set(data.members.map(m=>m.student_id));
  const singles = data.students.filter(s => (s.aktiv && !inCourse.has(s.id)) || data.lessons.some(l=>!l.kurs_id && l.student_id===s.id));
  const th = Array.from({length:days},(_,i)=>`<th class="d ${[0,6].includes(wd(i+1))?"we":""}">${i+1}<br><span>${["So","Mo","Di","Mi","Do","Fr","Sa"][wd(i+1)]}</span></th>`).join("");
  const cell = (kid, s, d) => { const l = L[kid+"|"+s.id+"|"+iso(d)];
    return `<td class="d ${[0,6].includes(wd(d))?"we":""} ${l?(l.invoice_id?"billed":"on"):""}" data-k="${kid}" data-s="${s.id}" data-d="${iso(d)}">${l?(l.invoice_id?"✓":"●"):""}</td>`; };
  const hours = (kid, s) => data.lessons.filter(l=>(l.kurs_id||0)===kid && l.student_id===s.id).reduce((a,l)=>a+(l.dauer_eff||1),0);
  let rows = "";
  kurse.forEach(k => { const mem = memOf(k.id);
    rows += `<tr class="grp kurs"><td><a href="#" data-ek="${k.id}"><b>${esc(k.name)}</b></a><div class="small muted">${esc(artName(k.article_id))}${k.modus==="stunde"?" je Std.":" je Monat"} · ${k.customer_id?"zahlt: "+esc(custName(k.customer_id)):"jeder selbst"}</div></td>
      ${Array.from({length:days},(_,i)=>{ const d=i+1; const n = mem.filter(s=>L[k.id+"|"+s.id+"|"+iso(d)]).length; const kt = KT[k.id+"|"+iso(d)];
        const full = (n && n===mem.length) || (!mem.length && kt);
        return `<td class="d kd ${[0,6].includes(wd(d))?"we":""} ${full?"on":n?"part":""}" data-kd="${k.id}" data-d="${iso(d)}" title="${mem.length?"ganzer Kurs":"Kurstermin (noch ohne Teilnehmer)"}${kt&&kt.von?" "+kt.von+(kt.bis?"–"+kt.bis:""):""}">${full?"●":n?"◐":""}</td>`; }).join("")}<td class="r small muted">${mem.length} TN${!mem.length&&Object.keys(KT).some(x_=>x_.startsWith(k.id+"|"))?" · Termine":""}</td></tr>`;
    rows += mem.map(s => `<tr><td style="padding-left:22px"><a href="#" data-es="${s.id}">${esc(s.name)}</a></td>${Array.from({length:days},(_,i)=>cell(k.id, s, i+1)).join("")}<td class="r num">${nde(hours(k.id,s),1)}</td></tr>`).join("")
      || `<tr><td colspan="${days+2}" class="small muted" style="padding-left:22px">Noch keine Teilnehmer – <a href="#" data-addm="${k.id}">Teilnehmer hinzufügen</a></td></tr>`;
  });
  if (singles.length) {
    rows += `<tr class="grp"><td colspan="${days+2}">Einzelunterricht</td></tr>`;
    rows += singles.map(s => `<tr><td><a href="#" data-es="${s.id}"><b>${esc(s.name)}</b></a><div class="small muted">${esc(artName(s.article_id))} · zahlt: ${esc(custName(s.customer_id)||"–")}</div></td>${Array.from({length:days},(_,i)=>cell(0, s, i+1)).join("")}<td class="r num">${nde(hours(0,s),1)}</td></tr>`).join("");
  }
  const payerOpts = Object.entries(payers).map(([cid,n])=>`<option value="${cid}" ${cid==schPayer?"selected":""}>${esc(custName(+cid)||"?")} – ${n} Std.</option>`).join("");
  return `<div class="row" style="align-items:center;margin-bottom:14px;flex-wrap:wrap">
      <button class="btn" style="flex:none" id="mprev">‹</button><b style="flex:none;min-width:150px;text-align:center;font:600 17px var(--disp)">${MONL[schM-1]} ${schY}</b><button class="btn" style="flex:none" id="mnext">›</button>
      <span class="sp"></span>
      ${Object.keys(payers).length?`<select class="in" id="spay" style="flex:none;width:250px"><option value="">Rechnungsempfänger wählen …</option>${payerOpts}</select>
      <button class="btn" style="flex:none" id="sbill">${ic("inv")} Rechnung erstellen</button>
      <button class="btn pri" style="flex:none" id="sball">${ic("inv")} Alle ${Object.keys(payers).length} als Entwurf</button>`:`<span class="small muted" style="flex:none">Keine offenen Stunden in diesem Monat</span>`}</div>
    ${(kurse.length||singles.length)?`<div class="card" style="overflow:auto"><table class="t cal"><thead><tr><th style="min-width:200px">Kurs / Schüler</th>${th}<th class="r">Std.</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="small muted" style="margin-top:8px">Kurszeile anklicken = Kurstermin (auch ohne Teilnehmer – später nachtragbar) bzw. Stunde für alle Teilnehmer · Schülerzeile = einzeln · ● erfasst · ◐ teilweise · ✓ abgerechnet</div>`
    : `<div class="card empty">Noch keine Kurse oder Schüler.<br><br><button class="btn pri" id="knew2">${ic("plus")} Ersten Kurs anlegen</button></div>`}`;
}
function schoolKurse(){
  const ks = S.kurse;
  const mem = kid => S.kurs_members.filter(m=>m.kurs_id===kid).map(m=>S.students.find(s=>s.id===m.student_id)).filter(Boolean);
  return ks.length ? `<div class="pgrid">${ks.map(k=>`<div class="card pcard" style="cursor:default;${k.aktiv?"":"opacity:.55"}"><div class="stripe" style="background:${k.farbe||"var(--acc)"}"></div>
      <div class="row" style="align-items:center"><span class="nr">${esc(k.rhythmus||"")}</span><span class="sp"></span><button class="btn sm ghost" data-ek="${k.id}">Bearbeiten</button></div>
      <h3>${esc(k.name)}</h3><div class="small muted">${esc(artName(k.article_id))}${k.modus==="stunde"?" je Std.":" je Monat"} · ${k.customer_id?"Rechnung an "+esc(custName(k.customer_id)):"jeder Teilnehmer zahlt selbst"}</div>
      <div class="chips" style="margin-top:10px">${mem(k.id).map(s=>`<span class="chip" style="cursor:default">${esc(s.name)} <a href="#" data-rm="${k.id}|${s.id}" title="aus Kurs entfernen" style="color:var(--bad);text-decoration:none;margin-left:4px">×</a></span>`).join("") || `<span class="small muted">noch keine Teilnehmer</span>`}</div>
      <div style="margin-top:10px"><button class="btn sm" data-addm="${k.id}">${ic("plus")} Teilnehmer (Schüler oder Kunden)</button></div></div>`).join("")}</div>`
    : `<div class="card empty">Noch keine Kurse.<br><br><button class="btn pri" id="knew2">${ic("plus")} Kurs anlegen</button></div>`;
}
function schoolStudents(){
  const kOf = sid => S.kurs_members.filter(m=>m.student_id===sid).map(m=>S.kurse.find(k=>k.id===m.kurs_id)).filter(Boolean);
  return `<div class="row" style="margin-bottom:12px"><button class="btn" style="flex:none" id="sfromc">${ic("users")} Schüler aus Kunden übernehmen</button><span class="sp"></span></div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Schüler/in</th><th>Kunde</th><th>Rechnung an</th><th>Kurse</th><th>Einzel-Baustein</th><th>Rhythmus</th></tr></thead><tbody>
    ${S.students.map(s=>`<tr class="click" data-es="${s.id}" style="${s.aktiv?"":"opacity:.5"}"><td><b>${esc(s.name)}</b></td><td class="small">${s.person_customer_id?esc(custName(s.person_customer_id)):`<span class="muted">–</span>`}</td>
      <td class="small">${esc(custName(s.customer_id)||"–")}</td><td>${kOf(s.id).map(k=>`<span class="badge acc">${esc(k.name)}</span>`).join(" ")||`<span class="muted small">–</span>`}</td>
      <td class="small">${s.article_id?esc(artName(s.article_id)):"–"}</td><td class="small muted">${esc(s.rhythmus||"")}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Noch keine Schüler.</td></tr>`}</tbody></table></div>`;
}
function bindSchool(data, payers){
  const on = (sel, fn) => $$(sel).forEach(e => e.onclick = ev => { ev.preventDefault(); fn(e, ev); });
  if ($("#mprev")) $("#mprev").onclick = () => { schM--; if (schM<1) { schM=12; schY--; } vSchool(); };
  if ($("#mnext")) $("#mnext").onclick = () => { schM++; if (schM>12) { schM=1; schY++; } vSchool(); };
  if ($("#knew2")) $("#knew2").onclick = () => editKurs({modus:"monat", dauer:1, aktiv:1});
  if ($("#spay")) $("#spay").onchange = e => schPayer = e.target.value;
  on("[data-es]", e => editStudent(S.students.find(s=>s.id==e.dataset.es)));
  on("[data-ek]", e => editKurs(S.kurse.find(k=>k.id==e.dataset.ek)));
  on("[data-addm]", e => addMembers(S.kurse.find(k=>k.id==e.dataset.addm)));
  on("[data-rm]", async e => { const [kid, sid] = e.dataset.rm.split("|"); await api("/api/kurs/remove", {kurs_id:+kid, student_id:+sid}); await reload(); vSchool(); });
  $$("td[data-s]").forEach(td => td.onclick = async () => { const r = await api("/api/lesson/toggle", {student_id:+td.dataset.s, datum:td.dataset.d, kurs_id:+td.dataset.k||null}); if (r.ok) vSchool(); });
  $$("td[data-kd]").forEach(td => td.onclick = async () => { const r = await api("/api/kurs/toggle_day", {kurs_id:+td.dataset.kd, datum:td.dataset.d}); if (r.ok) vSchool(); });
  if ($("#sfromc")) $("#sfromc").onclick = () => pickCustomers("Schüler aus Kunden übernehmen", S.customers.filter(c=>!S.students.some(s=>s.person_customer_id===c.id)), async ids => {
    await api("/api/student/from_customers", {customer_ids:ids}); await reload(); toast(ids.length + " Schüler angelegt"); vSchool(); });
  if ($("#sbill")) $("#sbill").onclick = async () => {
    const cid = $("#spay").value; if (!cid) { toast("Bitte Rechnungsempfänger wählen", true); return; }
    const draft = await api("/api/unterricht/to_invoice", {customer_id:+cid, year:schY, month:schM, attach:true});
    if (draft.ok === false) return;
    await reload(); newInvoice({draft}); toast("Rechnung aus " + draft.lesson_ids.length + " Stunden – Stundennachweis ist angehängt"); };
  if ($("#sball")) $("#sball").onclick = async () => {
    if (!await confirmBox(`Für alle ${Object.keys(payers).length} Rechnungsempfänger je einen Rechnungsentwurf (${MONL[schM-1]}) mit Stundennachweis anlegen?`, "Entwürfe anlegen")) return;
    const r = await api("/api/unterricht/bill_all", {year:schY, month:schM});
    if (r.ok) { await reload(); toast(r.ids.length + " Entwürfe angelegt – unter Rechnungen › Entwürfe prüfen und fertigstellen"); invTab = "draft"; go("inv"); } };
}
function pickCustomers(title, list, cb, extraHtml=""){
  const pr = modal(title, `<div class="fr">${extraHtml}<div class="search"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="pcq" placeholder="Kunden suchen …"></div>
    <div class="scroll card" style="max-height:46vh;padding:4px 10px" id="pcl">${list.map(c=>`<label class="chk pcrow" style="padding:6px 0" data-t="${esc((cname(c)+" "+c.name+" "+c.kdnr+" "+c.ort).toLowerCase())}"><input type="checkbox" value="${c.id}"> <b>${esc(cname(c))}</b>${c.firma&&c.name?` <span class="muted">${esc(c.name)}</span>`:""} <span class="small muted">${esc(c.kdnr)}${c.ort?" · "+esc(c.ort):""}</span></label>`).join("") || `<div class="muted small" style="padding:10px">Alle Kunden sind bereits übernommen.</div>`}</div></div>`,
    [{label:"Abbrechen"},{label:"Übernehmen", cls:"pri", value:"ok", onClick: async mb => { const ids = $$("#pcl input", mb).filter(c=>c.checked).map(c=>+c.value);
      if (!ids.length) { toast("Niemand ausgewählt", true); return false; } await cb(ids, mb); }}], true);
  const mb = $$(".mb").pop();
  $("#pcq", mb).oninput = e => { const v = e.target.value.toLowerCase(); $$(".pcrow", mb).forEach(r => r.style.display = r.dataset.t.includes(v) ? "" : "none"); };
  return pr;
}
async function addMembers(k){
  const inK = new Set(S.kurs_members.filter(m=>m.kurs_id===k.id).map(m=>m.student_id));
  const ti = await api("/api/kurs/termine_info?kurs_id=" + k.id, undefined, {quiet:true}) || {};   // v2.6.5: fill in existing course dates
  const nachHtml = ti.termine ? `<label class="f" style="margin-top:10px">Bisherige Kurstermine für die neuen Teilnehmer<select class="in" id="amnach">
      <option value="alle" ${!inK.size?"selected":""}>Alle ${ti.termine} Kurstermine nachtragen (${dde(ti.erster)} – ${dde(ti.letzter)})</option>
      <option value="ab_heute" ${inK.size?"selected":""}>Nur Termine ab heute (${ti.ab_heute})</option><option value="keine">Nicht nachtragen</option></select></label>` : "";
  const studs = S.students.filter(s=>s.aktiv && !inK.has(s.id));
  const custs = S.customers.filter(c=>!S.students.some(s=>s.person_customer_id===c.id && inK.has(s.id)));
  const pr = modal(`Teilnehmer für „${k.name}“`, `<div class="tabs" style="margin-bottom:10px"><div class="tab on" data-mt="s">Schüler<span class="cnt">${studs.length}</span></div><div class="tab" data-mt="c">Kunden<span class="cnt">${custs.length}</span></div></div>
    <div class="search"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="amq" placeholder="Suchen …"></div>
    <div class="scroll card" style="max-height:44vh;padding:4px 10px;margin-top:8px">
      <div id="ams">${studs.map(s=>`<label class="chk amrow" style="padding:6px 0" data-t="${esc(s.name.toLowerCase())}"><input type="checkbox" value="${s.id}"> <b>${esc(s.name)}</b> <span class="small muted">${esc(custName(s.customer_id))}</span></label>`).join("") || `<div class="muted small" style="padding:10px">Keine weiteren Schüler – über „Kunden“ direkt hinzufügen.</div>`}</div>
      <div id="amc" hidden>${custs.map(c=>`<label class="chk amrow" style="padding:6px 0" data-t="${esc((cname(c)+" "+c.name+" "+c.kdnr).toLowerCase())}"><input type="checkbox" value="${c.id}"> <b>${esc(cname(c))}</b>${c.firma&&c.name?` <span class="muted">${esc(c.name)}</span>`:""} <span class="small muted">${esc(c.kdnr)}</span></label>`).join("")}</div></div>
    <div class="small muted" style="margin-top:8px">Kunden werden automatisch als Schüler angelegt (Name und Adresse kommen aus der Kundendatenbank). ${k.customer_id?`Abgerechnet wird über den Kurs an <b>${esc(custName(k.customer_id))}</b>.`:"Jeder Teilnehmer bekommt seine eigene Rechnung."}</div>${nachHtml}`,
    [{label:"Abbrechen"},{label:"Hinzufügen", cls:"pri", value:"ok", onClick: async mb => {
      const sids = $$("#ams input", mb).filter(c=>c.checked).map(c=>+c.value), cids = $$("#amc input", mb).filter(c=>c.checked).map(c=>+c.value);
      if (!sids.length && !cids.length) { toast("Niemand ausgewählt", true); return false; }
      const r = await api("/api/kurs/add", {kurs_id:k.id, student_ids:sids, customer_ids:cids, nachtragen:$("#amnach",mb)?$("#amnach",mb).value:"keine"});
      if (r.ok) toast(r.n + " Teilnehmer hinzugefügt" + (r.nachgetragen ? ` · ${r.nachgetragen} Stunden nachgetragen` : "")); }}], true);
  const mb = $$(".mb").pop();
  $$("[data-mt]", mb).forEach(t => t.onclick = () => { $$("[data-mt]", mb).forEach(x_=>x_.classList.toggle("on", x_===t)); $("#ams",mb).hidden = t.dataset.mt!=="s"; $("#amc",mb).hidden = t.dataset.mt!=="c"; });
  $("#amq", mb).oninput = e => { const v = e.target.value.toLowerCase(); $$(".amrow", mb).forEach(r => r.style.display = r.dataset.t.includes(v) ? "" : "none"); };
  if (await pr) { await reload(); vSchool(); }
}
async function editKurs(k){
  const arts = S.articles.filter(a=>a.active);
  const r = await modal(k.id?"Kurs bearbeiten":"Neuer Kurs", `<div class="fr">
    <div class="row"><label class="f">Kursname<input class="in" id="kn" value="${esc(k.name||"")}" placeholder="z. B. DJ Team Samstag 17 Uhr"></label><label class="f" style="flex:.7">Rhythmus / Termin<input class="in" id="kr" value="${esc(k.rhythmus||"")}" placeholder="14-tägig Sa 17:00"></label></div>
    <div class="row"><label class="f">Baustein (Preis)<select class="in" id="ka"><option value="">–</option>${arts.map(a=>`<option value="${a.id}" ${a.id==k.article_id?"selected":""}>${esc(a.nr+" "+a.name)} · ${eur(a.price)}</option>`).join("")}</select></label>
      <label class="f">Rechnung an<select class="in" id="kc"><option value="">– jeder Teilnehmer selbst –</option>${S.customers.map(c=>`<option value="${c.id}" ${c.id==k.customer_id?"selected":""}>${esc(cname(c))}</option>`).join("")}</select></label></div>
    <div class="row"><label class="f">Abrechnung<select class="in" id="km"><option value="monat" ${k.modus!=="stunde"?"selected":""}>pro Teilnehmer und Monat (Pauschale)</option><option value="stunde" ${k.modus==="stunde"?"selected":""}>pro Stunde (Termine × Dauer)</option></select></label>
      <label class="f" style="flex:.4">Dauer (Std)<input class="in num" id="kd" value="${nde(k.dauer||1,2)}"></label><label class="f" style="flex:.35">Farbe<input type="color" class="in" id="kf" value="${k.farbe||"#6a48e0"}" style="height:38px;padding:3px"></label>
      <label class="chk" style="flex:none"><input type="checkbox" id="kak" ${k.aktiv?"checked":""}> aktiv</label></div>
    <div class="row"><label class="f">Start<input type="date" class="in" id="ks" value="${k.start||""}"></label><label class="f">Ende<input type="date" class="in" id="ke" value="${k.ende||""}"></label></div>
    <label class="f">Notiz<input class="in" id="kno" value="${esc(k.notiz||"")}"></label></div>`,
    [...(k.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:k.id?"Speichern":"Anlegen & Teilnehmer wählen", cls:"pri", value:"ok", onClick: async mb => {
      const d = {id:k.id, name:$("#kn",mb).value.trim(), rhythmus:$("#kr",mb).value, article_id:+$("#ka",mb).value||null, customer_id:+$("#kc",mb).value||null, modus:$("#km",mb).value,
        dauer:pnum($("#kd",mb).value)||1, farbe:$("#kf",mb).value, aktiv:$("#kak",mb).checked?1:0, start:$("#ks",mb).value, ende:$("#ke",mb).value, notiz:$("#kno",mb).value, sort:k.sort||0};
      if (!d.name) { toast("Kursname fehlt", true); return false; }
      const x_ = await api("/api/kurs/save", d); k._newId = x_.id; }}], true);
  if (r === "del" && await confirmBox(`Kurs „${k.name}“ löschen? Nicht abgerechnete Termine werden entfernt.`)) { const x_ = await api("/api/kurs/delete", {id:k.id}); if (x_.info) toast(x_.info); }
  if (r) { await reload(); if (r === "ok" && !k.id && k._newId) { await addMembers(S.kurse.find(x_=>x_.id===k._newId)); return; } vSchool(); }
}
async function editStudent(s){
  const arts = S.articles.filter(a=>a.active);
  const myK = new Set(S.kurs_members.filter(m=>m.student_id===s.id).map(m=>m.kurs_id));
  const taken = new Set(S.students.filter(x_=>x_.id!==s.id && x_.person_customer_id).map(x_=>x_.person_customer_id));
  const pr = modal(s.id?"Schüler bearbeiten":"Neuer Schüler", `<div class="fr">
    <label class="f">Aus Kunden übernehmen<select class="in" id="spc"><option value="">– kein Kunde / frei eingeben –</option>${S.customers.filter(c=>!taken.has(c.id)).map(c=>`<option value="${c.id}" ${c.id==s.person_customer_id?"selected":""}>${esc(cname(c))}${c.firma&&c.name?" – "+esc(c.name):""} (${esc(c.kdnr)})</option>`).join("")}</select></label>
    <div class="row"><label class="f">Name<input class="in" id="sn" value="${esc(s.name||"")}"></label><label class="f" style="flex:.8">Rhythmus / Termin<input class="in" id="sr" value="${esc(s.rhythmus||"")}" placeholder="z. B. 14-tägig Sa 14:30"></label></div>
    <label class="f">Rechnung an (wenn nicht über einen Kurs abgerechnet)<select class="in" id="sc"><option value="">–</option>${S.customers.map(c=>`<option value="${c.id}" ${c.id==s.customer_id?"selected":""}>${esc(cname(c))}</option>`).join("")}</select></label>
    <div><div class="small" style="color:var(--ink2);font-weight:500;margin-bottom:4px">Kurse</div><div class="chips">${S.kurse.filter(k=>k.aktiv||myK.has(k.id)).map(k=>`<label class="chip" style="display:inline-flex;gap:6px;align-items:center"><input type="checkbox" class="skk" value="${k.id}" ${myK.has(k.id)?"checked":""} style="accent-color:var(--acc)">${esc(k.name)}</label>`).join("") || `<span class="small muted">noch keine Kurse angelegt</span>`}</div></div>
    <div class="small muted" style="margin-top:-2px">Einzelunterricht (ohne Kurs):</div>
    <div class="row"><label class="f">Baustein<select class="in" id="sa"><option value="">–</option>${arts.map(a=>`<option value="${a.id}" ${a.id==s.article_id?"selected":""}>${esc(a.nr+" "+a.name)} · ${eur(a.price)}</option>`).join("")}</select></label>
      <label class="f">Abrechnung<select class="in" id="sm"><option value="monat" ${s.modus!=="stunde"?"selected":""}>pro Monat (Pauschale)</option><option value="stunde" ${s.modus==="stunde"?"selected":""}>pro Stunde</option></select></label>
      <label class="f" style="flex:.4">Dauer (Std)<input class="in num" id="sd" value="${nde(s.dauer||1,2)}"></label>
      <label class="chk" style="flex:none"><input type="checkbox" id="sak" ${s.aktiv?"checked":""}> aktiv</label></div>
    <label class="f">Notiz<input class="in" id="sno" value="${esc(s.notiz||"")}"></label></div>`,
    [...(s.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      const d = {id:s.id, person_customer_id:+$("#spc",mb).value||null, name:$("#sn",mb).value.trim(), rhythmus:$("#sr",mb).value, customer_id:+$("#sc",mb).value||null, article_id:+$("#sa",mb).value||null,
        modus:$("#sm",mb).value, dauer:pnum($("#sd",mb).value), aktiv:$("#sak",mb).checked?1:0, notiz:$("#sno",mb).value, sort:s.sort||0, kurs_ids:$$(".skk",mb).filter(c=>c.checked).map(c=>+c.value)};
      if (!d.name) { toast("Name fehlt – Kunden wählen oder Namen eingeben", true); return false; }
      const x_ = await api("/api/student/save", d); if (!x_.ok) return false; }}], true);
  const mb = $$(".mb").pop();
  $("#spc", mb).onchange = e => { const c = S.customers.find(c=>c.id==e.target.value); if (!c) return;
    $("#sn", mb).value = c.name || c.firma || ""; if (!$("#sc", mb).value) $("#sc", mb).value = c.id; };
  const r = await pr;
  if (r === "del" && await confirmBox(`${s.name} löschen?`)) { const x_ = await api("/api/student/delete", {id:s.id}); if (x_.info) toast(x_.info); }
  if (r) { await reload(); vSchool(); }
}
