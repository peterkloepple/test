// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Projekte
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- projects ----------
let projF = {status:"aktiv", bereich:"", q:""};
function vProjects(){
  const bereiche = [...new Set([...Object.keys(BEREICH_COL), ...S.projects.map(p=>p.bereich)])];
  const list = S.projects.filter(p => (!projF.status || p.status===projF.status) && (!projF.bereich || p.bereich===projF.bereich) &&
    (!projF.q || (p.nr+" "+p.name+" "+p.descr).toLowerCase().includes(projF.q.toLowerCase())));
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Projekte", "Zeichnungen, Blockschaltbilder, Programme und Schweißdokumentation – strukturiert je Projekt", expButtons("projects") + `<button class="btn pri" id="pnew">${ic("plus")} Neues Projekt</button>`)}
    <div class="row" style="margin-bottom:14px;align-items:center">
      <div class="search" style="max-width:300px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="pq" placeholder="Projekt suchen …" value="${esc(projF.q)}"></div>
      <div class="seg" style="flex:none">${[["aktiv","Aktiv"],["angebot","Angebot"],["abgeschlossen","Abgeschlossen"],["","Alle"]].map(([k,l])=>`<button class="${projF.status===k?"on":""}" data-st="${k}">${l}</button>`).join("")}</div>
      <div class="chips" style="flex:none"><span class="chip ${!projF.bereich?"on":""}" data-b="">Alle Bereiche</span>${bereiche.map(b=>`<span class="chip ${projF.bereich===b?"on":""}" data-b="${esc(b)}">${esc(b)}</span>`).join("")}</div>
    </div>
    ${list.length ? `<div class="pgrid">${list.map(p=>{ const c = S.customers.find(c=>c.id==p.customer_id); const col = BEREICH_COL[p.bereich]||"#888";
      return `<div class="card pcard" data-proj="${p.id}"><div class="stripe" style="background:${col}"></div>
        <div class="row" style="align-items:center"><span class="nr">${esc(p.nr)}</span><span class="sp"></span><span class="badge" style="background:${col}1c;color:${col}">${esc(p.bereich)}</span>${p.status!=="aktiv"?`<span class="badge">${esc(p.status)}</span>`:""}</div>
        <h3>${esc(p.name)}</h3><div class="small muted">${c?esc(cname(c)):"ohne Kunde"}${p.start?" · seit "+dde(p.start):""}</div>
        <div class="meta"><span><b>${p.nfiles}</b> Dateien</span><span><b>${eur0(p.umsatz)}</b> abgerechnet</span>${p.offen_pos?`<span style="color:var(--warn)"><b style="color:inherit">${p.offen_pos}</b> offen</span>`:""}</div></div>`; }).join("")}</div>`
      : `<div class="card empty">Keine Projekte in dieser Ansicht.<br><br><button class="btn pri" id="pnew2">${ic("plus")} Erstes Projekt anlegen</button></div>`}
  </div>`;
  bindCommon();
  $("#pq").oninput = e => { projF.q = e.target.value; debRender("pq", vProjects); };
  $$("[data-st]").forEach(b => b.onclick = () => { projF.status = b.dataset.st; vProjects(); });
  $$("[data-b]").forEach(b => b.onclick = () => { projF.bereich = b.dataset.b; vProjects(); });
  $("#pnew").onclick = newProject; if ($("#pnew2")) $("#pnew2").onclick = newProject;
}
async function newProject(){
  const tpls = S.templates;
  const html = `<div class="fr">
    <div class="row"><label class="f">Projektname<input class="in" id="pn" placeholder="z. B. Konferenzraum 3.OG – Q-SYS Umbau"></label><label class="f" style="flex:.45">Projekt-Nr.<input class="in" id="pnr" placeholder="${esc(S.settings.next_projnr)}"></label></div>
    <div class="row"><label class="f">Kunde<select class="in" id="pc"><option value="">– ohne –</option>${S.customers.map(c=>`<option value="${c.id}">${esc(cname(c))} (${esc(c.kdnr)})</option>`).join("")}</select></label>
      <label class="f" style="flex:.6">Bereich<select class="in" id="pb">${Object.keys(BEREICH_COL).map(b=>`<option>${b}</option>`).join("")}</select></label></div>
    <label class="f">Strukturvorlage<select class="in" id="pt">${tpls.map(t=>`<option value="${t.id}" data-b="${esc(t.bereich)}">${esc(t.name)}</option>`).join("")}</select></label>
    <div class="small muted">Ordnerstruktur (eine Zeile pro Ordner, Unterordner mit /) – frei anpassbar:</div>
    <textarea class="in" id="pf" rows="8" style="font-family:Consolas,monospace;font-size:12.5px"></textarea>
    <div class="row"><label class="f">Start<input type="date" class="in" id="ps" value="${todayIso()}"></label><label class="f">Budget / Angebotssumme (€)<input class="in num" id="pbu" placeholder="optional"></label>
      <label class="f">Status<select class="in" id="pst"><option value="aktiv">aktiv</option><option value="angebot">angebot</option></select></label></div>
    <label class="f">Beschreibung<textarea class="in" id="pd" rows="2"></textarea></label></div>`;
  let id = null;
  const p = modal("Neues Projekt", html, [{label:"Abbrechen"},{label:"Projekt anlegen", cls:"pri", onClick: async mb => {
    const d = {name:$("#pn",mb).value.trim(), nr:$("#pnr",mb).value.trim(), customer_id:+$("#pc",mb).value||null, bereich:$("#pb",mb).value,
      folders:$("#pf",mb).value.split("\n").map(s=>s.trim().replace(/\\/g,"/")).filter(Boolean), start:$("#ps",mb).value, budget:pnum($("#pbu",mb).value), status:$("#pst",mb).value, descr:$("#pd",mb).value};
    if (!d.name) { toast("Bitte Projektnamen angeben", true); return false; }
    const r = await api("/api/project/save", d); id = r.id; }}], true);
  const mb = $$(".mb").pop();
  const fill = () => { const t = tpls.find(t=>t.id==$("#pt",mb).value); $("#pf",mb).value = JSON.parse(t.folders).join("\n"); if (t.bereich && BEREICH_COL[t.bereich]) $("#pb",mb).value = t.bereich; };
  $("#pt",mb).onchange = fill; fill();
  $("#pb",mb).onchange = () => { const t = tpls.find(t=>t.bereich===$("#pb",mb).value); if (t) { $("#pt",mb).value = t.id; fill(); } };
  await p;
  if (id) { await reload(); go("project", id); toast("Projekt angelegt – Ordner erstellt"); }
}
let pTab = "files", pFolder = "*", pKind = "";
async function vProject(id){
  const p = await api("/api/project?id="+id);
  if (!p) { go("proj"); return; }
  const col = BEREICH_COL[p.bereich]||"#888";
  const unbilled = p.entries.filter(e=>!e.invoice_id);
  const billedSum = p.invoices.filter(i=>["rechnung","storno"].includes(i.typ) && !["entwurf","storniert"].includes(i.status)).reduce((a,i)=>a+i.summe,0);
  const openSum = unbilled.reduce((a,e)=>a+e.qty*e.price,0);
  $("#main").innerHTML = `<div class="page">
    <div class="small" style="margin-bottom:6px"><a href="#" id="back" style="color:var(--acc2);text-decoration:none">← Projekte</a></div>
    <div class="ph"><div><div style="display:flex;align-items:center;gap:8px"><span class="badge" style="background:${col}1c;color:${col}">${esc(p.bereich)}</span><span class="muted small">${esc(p.nr)}</span>
      <select class="in" id="pstat" style="width:auto;padding:2px 8px;font-size:12px">${["angebot","aktiv","abgeschlossen","archiv"].map(s=>`<option ${p.status===s?"selected":""}>${s}</option>`).join("")}</select></div>
      <h1 style="margin-top:6px">${esc(p.name)}</h1><div class="sub">${p.customer?esc(cname(p.customer)):"ohne Kunde"} · Start ${dde(p.start)}${p.budget?" · Budget "+eur(p.budget):""}</div></div>
      <div class="act">${expButtons("project", {id:p.id})}${S.settings.timer&&S.settings.timer.project_id==p.id?`<button class="btn" id="ptstop">${ic("clock")} Timer stoppen</button>`:`<button class="btn" id="ptstart">${ic("clock")} Timer</button>`}<button class="btn" id="phand">${ic("pdf")} Übergabe-Doku</button><button class="btn" id="pedit">Bearbeiten</button><button class="btn" id="popen">${ic("folder")} Ordner</button><button class="btn" id="psync" title="Dateien, die direkt im Explorer in den Projektordner gelegt wurden, übernehmen">${ic("sync")} Abgleichen</button>
      <button class="btn pri" id="pinv" ${unbilled.length?"":"disabled"}>${ic("inv")} Rechnung aus Projekt${unbilled.length?` (${unbilled.length})`:""}</button></div></div>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card kpi"><div class="l">Dateien</div><div class="v">${p.files.length}</div><div class="s">${p.folders.length} Ordner</div></div>
      <div class="card kpi"><div class="l">Abgerechnet</div><div class="v">${eur(billedSum)}</div><div class="s">${p.invoices.length} Rechnung(en)</div></div>
      <div class="card kpi"><div class="l">Noch nicht abgerechnet</div><div class="v" style="color:${openSum?"var(--warn)":"inherit"}">${eur(openSum)}</div><div class="s">${unbilled.length} Position(en)</div></div>
      <div class="card kpi"><div class="l">Budget</div><div class="v">${p.budget?Math.round(100*(billedSum+openSum)/p.budget)+" %":"–"}</div><div class="prog ${p.budget&&billedSum+openSum>p.budget?"b":""}" style="margin-top:8px"><div style="width:${p.budget?Math.min(100,100*(billedSum+openSum)/p.budget):0}%"></div></div></div>
    </div>
    <div class="tabs">${[["files","Dateien",p.files.length],["entries","Leistungen & Material",p.entries.length],["invoices","Rechnungen",p.invoices.length],["struct","Struktur",p.folders.length],["info","Info",""]].map(([k,l,n])=>`<div class="tab ${pTab===k?"on":""}" data-tab="${k}">${l}${n!==""?`<span class="cnt">${n}</span>`:""}</div>`).join("")}</div>
    <div id="ptab"></div></div>`;
  $("#back").onclick = e => { e.preventDefault(); go("proj"); };
  $$("[data-tab]").forEach(t => t.onclick = () => { pTab = t.dataset.tab; vProject(id); });
  $("#pstat").onchange = async e => { await api("/api/project/save", Object.assign({}, p, {status:e.target.value, folders:p.folders})); await reload(); toast("Status geändert"); };
  $("#popen").onclick = () => api("/api/open", {path:p.abs_dir, folder:true});
  $("#psync").onclick = async () => { const r = await api("/api/project/sync", {id}); toast(r.added ? r.added + " neue Datei(en) übernommen" : "Alles aktuell"); vProject(id); };
  $("#pinv").onclick = () => projectToInvoice(p, unbilled.map(e=>e.id));
  if ($("#ptstart")) $("#ptstart").onclick = () => startTimer(p.id);
  if ($("#ptstop")) $("#ptstop").onclick = stopTimer;
  $("#phand").onclick = () => handoverDialog(p);
  $("#pedit").onclick = () => editProject(p);
  const T = $("#ptab");
  if (pTab === "files") projFiles(T, p);
  if (pTab === "entries") projEntries(T, p);
  if (pTab === "invoices") { T.innerHTML = `<div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Nr.</th><th>Datum</th><th>Status</th><th class="r">Betrag</th></tr></thead><tbody>${p.invoices.map(i=>`<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b></td><td>${dde(i.datum)}</td><td>${statusBadge(i)}</td><td class="r num">${eur(i.summe)}</td></tr>`).join("")||`<tr><td colspan="4" class="empty">Noch keine Rechnungen zu diesem Projekt.</td></tr>`}</tbody><tfoot><tr><td colspan="3">Summe</td><td class="r num">${eur(billedSum)}</td></tr></tfoot></table></div>`; bindCommon(T); }
  if (pTab === "struct") projStruct(T, p);
  if (pTab === "info") { T.innerHTML = `<div class="card"><div class="bd"><div class="kv"><span class="sub">Projektordner</span><span>${esc(p.abs_dir)}</span><span class="sub">Kunde</span><span>${p.customer?esc(cname(p.customer)):"–"}</span><span class="sub">Zeitraum</span><span>${dde(p.start)} – ${dde(p.ende)||"offen"}</span></div><hr class="s"><div style="white-space:pre-line">${esc(p.descr||"Keine Beschreibung.")}</div></div></div>`; }
}
function folderTree(folders){
  const nodes = []; const seen = new Set();
  folders.forEach(f => { const parts = f.split("/"); parts.forEach((_,i) => { const path = parts.slice(0,i+1).join("/"); if (!seen.has(path)) { seen.add(path); nodes.push({path, name:parts[i], depth:i}); } }); });
  return nodes;
}
function projFiles(T, p){
  const nodes = folderTree(p.folders);
  const cnt = path => p.files.filter(f => f.folder===path || (f.folder||"").startsWith(path+"/")).length;
  const kinds = [...new Set(p.files.map(f=>f.kind))];
  const files = p.files.filter(f => (pFolder==="*" || f.folder===pFolder || (f.folder||"").startsWith(pFolder+"/")) && (!pKind || f.kind===pKind));
  const ext = n => (n.split(".").pop()||"").toUpperCase().slice(0,5);
  T.innerHTML = `<div class="grid" style="grid-template-columns:270px 1fr;align-items:start">
    <div class="card"><div class="bd ftree" style="padding:8px">
      <div class="fn ${pFolder==="*"?"on":""}" data-fo="*">${ic("folder")}<b>Alle Dateien</b><span class="c">${p.files.length}</span></div>
      ${nodes.map(n=>`<div class="fn ${pFolder===n.path?"on":""}" data-fo="${esc(n.path)}" style="padding-left:${10+n.depth*16}px">${ic("folder")}<span>${esc(n.name)}</span><span class="c">${cnt(n.path)||""}</span></div>`).join("")}
    </div></div>
    <div>
      <div class="dz" id="pdz" style="margin-bottom:14px"><b>Dateien hier ablegen</b>
        <span class="muted">Zeichnungen (DWG, DXF, Inventor IPT/IAM/IDW, STEP), Blockschaltbilder, Q-SYS/Crestron-Dateien, WPS/WPQR, Fotos, PDFs …</span>
        <div class="row" style="justify-content:center;margin-top:10px;align-items:center;gap:14px"><label class="chk" style="flex:none"><input type="checkbox" id="autosort" ${pFolder==="*"?"checked":""}> automatisch erkennen & einsortieren</label><button class="btn sm" id="fpick">${ic("up")} Dateien auswählen</button></div>
        <div class="small muted" style="margin-top:6px">${pFolder==="*"?"":"Ziel ohne Automatik: <b>"+esc(pFolder)+"</b>"}</div></div>
      ${kinds.length>1?`<div class="chips" style="margin-bottom:12px"><span class="chip ${!pKind?"on":""}" data-k="">Alle Arten</span>${kinds.map(k=>`<span class="chip ${pKind===k?"on":""}" data-k="${esc(k)}">${esc(k)}</span>`).join("")}</div>`:""}
      ${files.length?`<div class="fgrid">${files.map(f=>{ const c = KIND_COL[f.kind]||"#888"; const th = /\.(jpe?g|png|webp|gif|bmp|tiff?|pdf)$/i.test(f.name);
        return `<div class="fcard" data-f="${f.id}" draggable="true" title="${esc(f.name)}"><div class="th" style="${th?`background-image:url('/api/thumb?path=${encCss(f.path)}');background-position:${/\.pdf$/i.test(f.name)?"top":"center"}`:""}">${th?"":`<span class="ext" style="background:${c}">${esc(ext(f.name))}</span>`}</div>
        <div class="fb"><div class="nm">${esc(f.name)}</div><div class="kd"><span class="dot" style="color:${c}"></span>${esc(f.kind)}</div><div class="small muted" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(f.folder)}</div></div></div>`; }).join("")}</div>`
        : `<div class="card empty">Keine Dateien in diesem Ordner.</div>`}
    </div></div>`;
  $$("[data-fo]", T).forEach(n => {
    n.onclick = () => { pFolder = n.dataset.fo; projFiles(T, p); };
    if (n.dataset.fo !== "*") {
      n.ondragover = e => { e.preventDefault(); n.classList.add("dragover"); };
      n.ondragleave = () => n.classList.remove("dragover");
      n.ondrop = async e => { e.preventDefault(); n.classList.remove("dragover");
        const fid = e.dataTransfer.getData("text/file");
        if (fid) { await api("/api/project/file/update", {id:+fid, folder:n.dataset.fo}); toast("Verschoben nach " + n.dataset.fo); vProject(p.id); }
        else if (e.dataTransfer.files.length) uploadProjectFiles(p, [...e.dataTransfer.files], n.dataset.fo); };
    }
  });
  $$("[data-k]", T).forEach(c => c.onclick = () => { pKind = c.dataset.k; projFiles(T, p); });
  $$(".fcard", T).forEach(c => { c.ondragstart = e => e.dataTransfer.setData("text/file", c.dataset.f); c.onclick = () => fileDialog(p, p.files.find(f=>f.id==c.dataset.f)); });
  const dz = $("#pdz", T);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); uploadProjectFiles(p, [...e.dataTransfer.files], $("#autosort").checked ? null : pFolder); };
  $("#fpick", T).onclick = () => pickFiles("", fs => uploadProjectFiles(p, fs, $("#autosort").checked ? null : pFolder));
}
async function uploadProjectFiles(p, files, folder){
  if (!files.length) return;
  toast(files.length + " Datei(en) werden übernommen …");
  const res = [];
  for (const f of files) { const h = {"X-Project": String(p.id)}; if (folder && folder !== "*") h["X-Folder"] = encodeURIComponent(folder); res.push(await upload("/api/upload/project", f, h)); }
  await reload();
  const summary = {}; res.forEach(r => summary[r.kind] = (summary[r.kind]||0)+1);
  toast("Erkannt: " + Object.entries(summary).map(([k,v])=>v+"× "+k).join(", "));
  vProject(p.id);
}
async function fileDialog(p, f){
  const th = /\.(jpe?g|png|webp|gif|bmp|tiff?|pdf)$/i.test(f.name);
  await modal(f.name, `<div class="grid" style="grid-template-columns:${th?"260px ":""}1fr">
    ${th?`<img src="/api/thumb?path=${encodeURIComponent(f.path)}" style="width:100%;border:1px solid var(--line);border-radius:10px">`:""}
    <div class="fr"><label class="f">Art<select class="in" id="fk">${Object.keys(KIND_COL).map(k=>`<option ${f.kind===k?"selected":""}>${k}</option>`).join("")}</select></label>
    <label class="f">Ordner<select class="in" id="ff"><option value="" ${!f.folder?"selected":""}>(Hauptordner)</option>${p.folders.map(o=>`<option ${f.folder===o?"selected":""}>${esc(o)}</option>`).join("")}</select></label>
    <label class="f">Notiz<textarea class="in" id="fn">${esc(f.note||"")}</textarea></label>
    <div class="small muted">${(f.size/1024).toFixed(0)} KB · hinzugefügt ${esc(f.added)}</div></div></div>`,
    [{label:"Aus Projekt entfernen", cls:"danger", onClick: async () => { const r = await api("/api/project/file/delete", {id:f.id}); toast(r.info); vProject(p.id); }},
     {label:"Im Ordner zeigen", onClick: async () => { await api("/api/open", {path:f.path, folder:true}); return false; }},
     {label:"Öffnen", onClick: async () => { await api("/api/open", {path:f.path}); return false; }},
     {label:"Speichern", cls:"pri", onClick: async mb => { await api("/api/project/file/update", {id:f.id, kind:$("#fk",mb).value, folder:$("#ff",mb).value, note:$("#fn",mb).value}); vProject(p.id); }}], true);
}
function projEntries(T, p){
  const arts = S.articles;
  const sum = p.entries.reduce((a,e)=>a+e.qty*e.price,0);
  T.innerHTML = `<div class="card" style="margin-bottom:14px"><div class="hd"><h3>Leistung / Material erfassen</h3></div><div class="bd">
    <div class="row" style="flex-wrap:wrap">
      <label class="f" style="flex:.7">Datum<input type="date" class="in" id="ed" value="${todayIso()}"></label>
      <label class="f" style="flex:.8">Art<select class="in" id="ea"><option>Arbeitszeit</option><option>Material</option><option>Fahrt</option><option>Programmierung</option><option>Pauschale</option><option>Sonstiges</option></select></label>
      <label class="f" style="flex:1.3">Baustein<select class="in" id="eb"><option value="">– frei –</option>${arts.map(a=>`<option value="${a.id}">${esc(a.nr+" "+a.name)} (${eur(a.price)})</option>`).join("")}</select></label>
      <label class="f" style="flex:1.5">Bezeichnung<input class="in" id="en"></label>
      <label class="f" style="flex:.5">Menge<input class="in num" id="eq" value="1"></label>
      <label class="f" style="flex:.5">Einheit<input class="in" id="eu" value="Std"></label>
      <label class="f" style="flex:.7">Preis €<input class="in num" id="ep" value="0,00"></label>
    </div>
    <div class="row" style="margin-top:8px"><label class="f">Beschreibung (erscheint auf der Rechnung)<input class="in" id="ex" placeholder="z. B. Inbetriebnahme Q-SYS Core, Schweißarbeiten Geländer EG"></label><button class="btn pri" style="flex:none" id="eadd">${ic("plus")} Hinzufügen</button></div>
  </div></div>
  <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th style="width:30px"><input type="checkbox" id="eall" checked style="accent-color:var(--acc)"></th><th>Datum</th><th>Art</th><th>Bezeichnung</th><th class="r">Menge</th><th class="r">Preis</th><th class="r">Summe</th><th>Status</th><th></th></tr></thead>
  <tbody>${p.entries.map(e=>`<tr><td>${e.invoice_id?"":`<input type="checkbox" class="esel" value="${e.id}" checked style="accent-color:var(--acc)">`}</td><td class="num">${dde(e.datum)}</td><td><span class="badge">${esc(e.art)}</span></td><td><b>${esc(e.name)}</b><div class="small muted">${esc(e.descr)}</div></td>
    <td class="r num">${nde(e.qty,2)} ${esc(e.unit)}</td><td class="r num">${eur(e.price)}</td><td class="r num"><b>${eur(e.qty*e.price)}</b></td>
    <td>${e.invoice_id?`<span class="badge ok click" data-inv="${e.invoice_id}">abgerechnet</span>`:`<span class="badge warn">offen</span>`}</td><td>${e.invoice_id?"":`<button class="btn sm ghost danger" data-edel="${e.id}">${ic("trash")}</button>`}</td></tr>`).join("") || `<tr><td colspan="9" class="empty">Noch keine Einträge. Erfasse Arbeitszeit, Material oder Pauschalen – und rechne sie mit einem Klick ab.</td></tr>`}</tbody>
  <tfoot><tr><td colspan="6">Summe</td><td class="r num">${eur(sum)}</td><td colspan="2"></td></tr></tfoot></table></div>
  <div class="row" style="margin-top:12px;justify-content:flex-end"><button class="btn" style="flex:none" id="ebom">${ic("up")} Stückliste importieren (Inventor CSV/XLSX)</button><span class="sp"></span><button class="btn" style="flex:none" id="eang">${ic("inv")} Angebot aus Auswahl</button><button class="btn pri" style="flex:none" id="ebill">${ic("inv")} Ausgewählte abrechnen</button></div>`;
  bindCommon(T);
  $("#eb").onchange = e => { const a = arts.find(a=>a.id==e.target.value); if (a) { $("#en").value = a.name; $("#ep").value = nde(a.price); $("#ex").value = (a.descr||"").split("\n")[0]; $("#eu").value = a.unit||"Stk"; } };
  $("#eadd").onclick = async () => { const a = arts.find(a=>a.id==$("#eb").value);
    const d = {project_id:p.id, datum:$("#ed").value, art:$("#ea").value, nr:a?a.nr:"", name:$("#en").value||$("#ea").value, descr:$("#ex").value, qty:pnum($("#eq").value), unit:$("#eu").value, price:pnum($("#ep").value)};
    await api("/api/project/entry/save", d); await reload(); vProject(p.id); };
  $("#eall").onchange = e => $$(".esel").forEach(c => c.checked = e.target.checked);
  $("#ebom").onclick = () => bomImport(p);
  $("#eang").onclick = () => { const ids = $$(".esel").filter(c=>c.checked).map(c=>+c.value); if (!ids.length) { toast("Nichts ausgewählt", true); return; } projectToInvoice(p, ids, "angebot"); };
  $$("[data-edel]").forEach(b => b.onclick = async () => { await api("/api/project/entry/delete", {id:+b.dataset.edel}); vProject(p.id); });
  $("#ebill").onclick = () => { const ids = $$(".esel").filter(c=>c.checked).map(c=>+c.value); if (!ids.length) { toast("Nichts ausgewählt", true); return; } projectToInvoice(p, ids); };
}
async function projectToInvoice(p, ids, typ="rechnung"){
  const draft = await api("/api/project/to_invoice", {id:p.id, entry_ids:ids});
  draft.typ = typ;
  if (typ === "angebot") { const s = S.settings; const gb = new Date(); gb.setDate(gb.getDate()+(s.angebot_gueltig||30)); Object.assign(draft, {titel:"Angebot "+p.name, toptext:s.default_top_angebot, foottext:s.default_foot_angebot, gueltig_bis:isoLocal(gb), liefer:"", auftrag:""}); }
  newInvoice({typ, draft});
  toast(ids.length + " Position(en) aus Projekt übernommen");
}
function projStruct(T, p){
  T.innerHTML = `<div class="grid g2" style="align-items:start"><div class="card"><div class="hd"><h3>Ordnerstruktur</h3></div><div class="bd">
    <div class="small muted" style="margin-bottom:8px">Eine Zeile pro Ordner, Unterordner mit „/“ (z. B. <code>04 Programmierung/Q-SYS</code>). Neue Ordner werden sofort auf der Festplatte angelegt.</div>
    <textarea class="in" id="sf" rows="14" style="font-family:Consolas,monospace;font-size:12.5px">${esc(p.folders.join("\n"))}</textarea>
    <div class="row" style="margin-top:10px"><button class="btn pri" style="flex:none" id="ssave">${ic("save")} Struktur speichern</button><button class="btn" style="flex:none" id="stpl">Als Vorlage speichern</button></div></div></div>
    <div class="card"><div class="hd"><h3>Vorschau</h3></div><div class="bd ftree">${folderTree(p.folders).map(n=>`<div class="fn" style="padding-left:${10+n.depth*16}px">${ic("folder")}${esc(n.name)}</div>`).join("")}</div></div></div>`;
  $("#ssave").onclick = async () => { const f = $("#sf").value.split("\n").map(s=>s.trim().replace(/\\/g,"/")).filter(Boolean);
    await api("/api/project/save", Object.assign({}, p, {folders:f})); toast("Struktur gespeichert"); vProject(p.id); };
  $("#stpl").onclick = async () => { const n = await modal("Als Vorlage speichern", `<label class="f">Name der Vorlage<input class="in" id="tn" value="${esc(p.bereich)} – eigene Struktur"></label>`,
    [{label:"Abbrechen"},{label:"Speichern", cls:"pri", onClick: async mb => { await api("/api/template/save", {name:$("#tn",mb).value, bereich:p.bereich, folders:$("#sf").value.split("\n").map(s=>s.trim()).filter(Boolean)}); }, value:true}]);
    if (n) { await reload(); toast("Vorlage gespeichert"); } };
}
async function editProject(p){
  const html = `<div class="fr"><div class="row"><label class="f">Name<input class="in" id="pn" value="${esc(p.name)}"></label><label class="f" style="flex:.45">Nr.<input class="in" id="pnr" value="${esc(p.nr)}"></label></div>
    <div class="row"><label class="f">Kunde<select class="in" id="pc"><option value="">– ohne –</option>${S.customers.map(c=>`<option value="${c.id}" ${c.id==p.customer_id?"selected":""}>${esc(cname(c))}</option>`).join("")}</select></label>
    <label class="f" style="flex:.6">Bereich<select class="in" id="pb">${Object.keys(BEREICH_COL).map(b=>`<option ${b===p.bereich?"selected":""}>${b}</option>`).join("")}</select></label></div>
    <div class="row"><label class="f">Start<input type="date" class="in" id="ps" value="${p.start||""}"></label><label class="f">Ende<input type="date" class="in" id="pe" value="${p.ende||""}"></label><label class="f">Budget €<input class="in num" id="pbu" value="${p.budget?nde(p.budget):""}"></label></div>
    <label class="f">Beschreibung<textarea class="in" id="pd" rows="4">${esc(p.descr||"")}</textarea></label></div>`;
  const r = await modal("Projekt bearbeiten", html, [{label:"Projekt löschen", cls:"danger", value:"del"},{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
    await api("/api/project/save", Object.assign({}, p, {name:$("#pn",mb).value, nr:$("#pnr",mb).value, customer_id:+$("#pc",mb).value||null, bereich:$("#pb",mb).value, start:$("#ps",mb).value, ende:$("#pe",mb).value, budget:pnum($("#pbu",mb).value), descr:$("#pd",mb).value, folders:p.folders})); }}]);
  if (r === "del") { if (await confirmBox(`Projekt „${p.name}“ entfernen? Dateien bleiben auf der Festplatte.`)) { const x = await api("/api/project/delete", {id:p.id}); toast(x.info); await reload(); go("proj"); } return; }
  if (r === "ok") { await reload(); vProject(p.id); }
}

