// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Nachweise, Wartung & Abos, Bank-Abgleich, Anlagen, Fahrten, Stueckliste/Uebergabe
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---- Nachweise ----
function certState(z){ const t = todayIso(); if (!z.gueltig_bis) return ["", "unbefristet"]; if (z.gueltig_bis < t) return ["bad","abgelaufen"];
  const d = (new Date(z.gueltig_bis) - new Date())/86400000; return d < 60 ? ["warn", "läuft ab"] : ["ok","gültig"]; }
function vCerts(){
  const list = S.zertifikate;
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Nachweise & Zertifikate", "Schweißen, Elektro, Q-SYS, Crestron, Extron, Dante, AVIXA und mehr – Zertifikat-PDF wird gelesen, mit Ablaufwarnung", expButtons("zert") + `<button class="btn" id="ztypes" title="Eigene Nachweis-Arten anlegen">Arten …</button><button class="btn pri" id="znew">${ic("plus")} Nachweis</button>`)}
    ${S.cert_warn.length?`<div class="alerts">${S.cert_warn.map(w=>`<div class="alert ${w.tage<0?"bad":"warn"}">${ic("award")}<b>${esc(w.art)}:</b> ${esc(w.bezeichnung)}${w.person?" · "+esc(w.person):""} – ${dde(w.datum)} (${w.tage<0?"seit "+(-w.tage):"in "+w.tage} Tagen)</div>`).join("")}</div>`:""}
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Art</th><th>Bezeichnung</th><th>Person</th><th>Nr. / Norm</th><th>Gültig bis</th><th>Bestätigung</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map(z=>{ const [c,l] = certState(z); const nb = z.bestaetigung_monate ? addMonthsIso(z.bestaetigt_am||z.ausgestellt||todayIso(), +z.bestaetigung_monate) : "";
      return `<tr class="click" data-z="${z.id}" style="${z.aktiv?"":"opacity:.5"}"><td class="small">${esc(z.typ)}</td><td><b>${esc(z.bezeichnung)}</b></td><td>${esc(z.person||"")}</td><td class="small">${esc([z.nummer,z.norm].filter(Boolean).join(" · "))}</td>
      <td class="num">${dde(z.gueltig_bis)||"–"}</td><td class="small">${nb?`nächste ${dde(nb)}`:"–"}</td><td><span class="badge ${c}"><span class="dot"></span>${l}</span></td>
      <td class="r" onclick="event.stopPropagation()">${z.bestaetigung_monate?`<button class="btn sm" data-zc="${z.id}" title="Bestätigung heute eintragen">${ic("check")} bestätigt</button>`:""}${z.file?`<button class="btn sm ghost" data-of="${esc(z.file)}">${ic("open")}</button>`:""}</td></tr>`; }).join("") || `<tr><td colspan="8" class="empty">Noch keine Nachweise erfasst.</td></tr>`}
    </tbody></table></div></div>`;
  $("#znew").onclick = () => editCert({typ:"", aktiv:1});
  $("#ztypes").onclick = async () => { const r = await modal("Eigene Nachweis-Arten", `<div class="fr"><div class="small muted">Eine Art pro Zeile. Sie erscheinen in der Auswahl ganz oben – zusätzlich zu den ${S.cert_types.length - (S.cert_types_eigene||[]).length} eingebauten (Schweißen, Elektro, Q-SYS, Crestron, Extron, Dante, AVIXA, Biamp, Shure …).</div>
      <textarea class="in" id="zte" rows="10">${esc((S.cert_types_eigene||[]).join("\n"))}</textarea></div>`, [{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:1, onClick: async mb => {
      await api("/api/zert/types", {eigene:$("#zte",mb).value.split("\n").map(t=>t.trim()).filter(Boolean)}); }}]);
    if (r) { await reload(); vCerts(); } };
  $$("[data-z]").forEach(r => r.onclick = () => editCert(list.find(z=>z.id==r.dataset.z)));
  selectify({kind:"zert", rows:"tr[data-z]", id:"data-z", rerender:vCerts, actions:[
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Nachweis(e) löschen? Die Dateien wandern in den Ordner „_Papierkorb“.")) return false; await bulk("zert", "delete", ids); await reload(); vCerts(); }}]});
  $$("[data-zc]").forEach(b => b.onclick = async () => { const z = list.find(z=>z.id==b.dataset.zc); await api("/api/zert/save", Object.assign({}, z, {bestaetigt_am:todayIso()})); await reload(); vCerts(); toast("Bestätigung eingetragen"); });
  $$("[data-of]").forEach(b => b.onclick = () => api("/api/open", {path:b.dataset.of}));
}
async function editCert(z){
  let file = z.file || "";
  const pr = modal(z.id?"Nachweis bearbeiten":"Neuer Nachweis", `<div class="fr">
    <div class="row"><label class="f">Art <span class="small muted">(Liste oder frei eintippen)</span><input class="in" id="zt" list="ztl" value="${esc(z.typ||"")}" placeholder="z. B. Q-SYS, Dante, Extron …"><datalist id="ztl">${S.cert_types.map(t=>`<option value="${esc(t)}">${esc((S.cert_groups||{})[t]||"eigene Art")}</option>`).join("")}</datalist></label><label class="f">Person / Gerät<input class="in" id="zp" value="${esc(z.person||"")}" placeholder="z. B. T. Pfeiffer"></label></div>
    <label class="f">Bezeichnung<input class="in" id="zb" value="${esc(z.bezeichnung||"")}" placeholder="z. B. ISO 9606-1 135 P BW FM1 S t10 PA ss nb"></label>
    <div class="row"><label class="f">Zertifikats-Nr.<input class="in" id="zn" value="${esc(z.nummer||"")}"></label><label class="f">Norm / Prüfstelle<input class="in" id="zno" value="${esc(z.norm||"")}"></label></div>
    <div class="row"><label class="f">Ausgestellt<input type="date" class="in" id="za" value="${z.ausgestellt||""}"></label><label class="f">Gültig bis<input type="date" class="in" id="zg" value="${z.gueltig_bis||""}"></label></div>
    <div class="row"><label class="f">Bestätigung alle … Monate (ISO 9606: 6)<input class="in num" id="zm" value="${z.bestaetigung_monate||""}" placeholder="leer = keine"></label><label class="f">Zuletzt bestätigt<input type="date" class="in" id="zba" value="${z.bestaetigt_am||""}"></label></div>
    <div class="row" style="align-items:center"><button class="btn sm" style="flex:none" id="zf" type="button">${ic("clip")} Zertifikat-PDF/Scan</button><span class="small muted" id="zfn">${esc(file.split(/[\\/]/).pop()||"keine Datei")}</span><span class="sp"></span><label class="chk" style="flex:none"><input type="checkbox" id="zak" ${z.aktiv?"checked":""}> aktiv</label></div>
    <label class="f">Notiz<input class="in" id="znt" value="${esc(z.notiz||"")}"></label></div>`,
    [...(z.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      const d = {id:z.id, typ:$("#zt",mb).value, person:$("#zp",mb).value, bezeichnung:$("#zb",mb).value, nummer:$("#zn",mb).value, norm:$("#zno",mb).value, ausgestellt:$("#za",mb).value, gueltig_bis:$("#zg",mb).value,
        bestaetigung_monate:parseInt($("#zm",mb).value)||null, bestaetigt_am:$("#zba",mb).value, file, aktiv:$("#zak",mb).checked?1:0, notiz:$("#znt",mb).value};
      if (!d.bezeichnung) { toast("Bezeichnung fehlt", true); return false; } if (!d.typ) d.typ = "Sonstiges";
      if (!S.cert_types.includes(d.typ)) await api("/api/zert/types", {eigene:[...(S.cert_types_eigene||[]), d.typ]}, {quiet:true});
      await api("/api/zert/save", d); }}], true);
  const mb = $$(".mb").pop();
  $("#zf", mb).onclick = () => pickFiles(".pdf,.jpg,.jpeg,.png", async fs => { $("#zfn", mb).textContent = "lädt und liest das Zertifikat …"; const r = await upload("/api/upload/zert", fs[0]); if (!r.ok) { $("#zfn", mb).textContent = r.error || "Fehler"; return; }
    file = r.file; $("#zfn", mb).textContent = fs[0].name;
    // v2.0.9: fill empty fields from the recognised certificate
    const e = r.erkannt || {}, set = (id, v) => { const el = $("#"+id, mb); if (el && v && !el.value) { el.value = v; el.classList.add("zauto"); } };
    if (e.typ && (!$("#zt", mb).value || !z.id)) { $("#zt", mb).value = e.typ; $("#zt", mb).classList.add("zauto"); }
    set("zb", e.bezeichnung); set("zn", e.nummer); set("zno", e.norm); set("za", e.ausgestellt); set("zg", e.gueltig_bis); set("zp", e.person); set("zm", e.bestaetigung_monate);
    const n = Object.keys(e).filter(k => k !== "gueltig_geschaetzt").length;
    $("#zfn", mb).innerHTML = esc(fs[0].name) + (n ? ` · <span style="color:var(--ok)">${n} Angabe(n) erkannt – bitte prüfen</span>${e.gueltig_geschaetzt?" (Ablauf aus üblicher Laufzeit geschätzt)":""}` : (r.text_gefunden ? " · nichts erkannt" : " · kein Text im Dokument")); });
  $("#zt", mb).addEventListener("change", () => { const m = (S.cert_meta||{})[$("#zt", mb).value]; if (m && m.bestaetigung && !$("#zm", mb).value) $("#zm", mb).value = m.bestaetigung;
    if (m && m.gueltig && !$("#zg", mb).value && $("#za", mb).value) $("#zg", mb).value = addMonthsIso($("#za", mb).value, m.gueltig); });
  const r = await pr;
  if (r === "del" && await confirmBox("Nachweis löschen?")) await api("/api/zert/delete", {id:z.id});
  if (r) { await reload(); vCerts(); }
}
// ---- Wartung & Abos ----
async function vAbo(){
  const rec = S.recurring, vt = S.vertraege;
  const nm = id => { const c = S.customers.find(c=>c.id==id); return c ? cname(c) : "–"; };
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Wartung & Abos", "Wiederkehrende Rechnungen werden automatisch als Entwurf angelegt · Wartungsverträge erinnern und rechnen ab", expButtons("abos") + `<button class="btn" id="runab">${ic("sync")} Jetzt prüfen</button><button class="btn" id="anew">${ic("plus")} Abo</button><button class="btn pri" id="vnew">${ic("plus")} Wartungsvertrag</button>`)}
    <div class="grid g2" style="align-items:start">
      <div class="card" style="overflow:hidden"><div class="hd"><h3>Wiederkehrende Rechnungen</h3></div><table class="t"><tbody>
      ${rec.map(r=>`<tr class="click" data-r="${r.id}" style="${r.aktiv?"":"opacity:.5"}"><td><b>${esc(r.name)}</b><div class="small muted">Vorlage ${esc(r.src_nr||"?")} · alle ${r.intervall} Monat(e)</div></td><td class="small">nächste<br><b>${dde(r.naechstes)}</b></td><td class="r num">${eur(r.src_summe||0)}</td></tr>`).join("") || `<tr><td class="empty">Noch keine Abos. In einer Rechnung auf „Abo“ klicken oder hier anlegen.</td></tr>`}
      </tbody></table></div>
      <div class="card" style="overflow:hidden"><div class="hd"><h3>Wartungsverträge</h3></div><table class="t"><tbody>
      ${vt.map(v=>{ const due = S.vertraege_due.find(d=>d.id===v.id); return `<tr class="click" data-v="${v.id}" style="${v.aktiv?"":"opacity:.5"}"><td><b>${esc(v.name)}</b><div class="small muted">${esc(nm(v.customer_id))} · alle ${v.intervall} Monate · ${eur(v.preis)}</div></td>
        <td class="small">fällig<br><b style="color:${due?"var(--warn)":"inherit"}">${dde(v.naechste)}</b></td><td class="r" onclick="event.stopPropagation()">${due?`<button class="btn sm pri" data-vd="${v.id}">${ic("check")} Erledigt${v.auto_rechnung?" & abrechnen":""}</button>`:""}</td></tr>`; }).join("") || `<tr><td class="empty">Noch keine Wartungsverträge.</td></tr>`}
      </tbody></table></div>
    </div></div>`;
  $("#runab").onclick = async () => { const r = await api("/api/recurring/run", {}); toast(r.erzeugt ? r.erzeugt + " Entwurf/Entwürfe erzeugt" : "Nichts fällig"); await reload(); vAbo(); };
  $("#anew").onclick = () => aboDialog({intervall:1, aktiv:1});
  $("#vnew").onclick = () => vertragDialog({intervall:12, vorlauf:14, auto_rechnung:1, aktiv:1, naechste:todayIso()});
  $$("[data-r]").forEach(r => r.onclick = () => aboDialog(rec.find(x_=>x_.id==r.dataset.r)));
  $$("[data-v]").forEach(r => r.onclick = () => vertragDialog(vt.find(x_=>x_.id==r.dataset.v)));
  $$("[data-vd]").forEach(b => b.onclick = async () => { const r = await api("/api/vertrag/done", {id:+b.dataset.vd}); await reload(); if (r.invoice_id) { toast("Erledigt – Rechnungsentwurf erstellt"); openInvoice(r.invoice_id); } else { toast("Erledigt – nächster Termin gesetzt"); vAbo(); } });
}
async function aboDialog(a){
  const srcs = S.invoices.filter(i=>i.typ==="rechnung"&&i.status!=="entwurf").slice(0,300);
  const nx = a.naechstes || (()=>{ const d = new Date(); d.setMonth(d.getMonth()+1, 1); return isoLocal(d); })();
  const r = await modal(a.id?"Abo bearbeiten":"Wiederkehrende Rechnung", `<div class="fr">
    <label class="f">Name<input class="in" id="an" value="${esc(a.name||"")}" placeholder="z. B. BPM City Monatsrechnung"></label>
    <label class="f">Vorlage (wird kopiert, Monatsname im Titel wird angepasst)<select class="in" id="ai">${srcs.map(i=>`<option value="${i.id}" ${i.id==a.invoice_id?"selected":""}>${esc(i.nr)} · ${esc(invName(i))} · ${esc(i.titel)} · ${eur(i.summe)}</option>`).join("")}</select></label>
    <div class="row"><label class="f">Intervall<select class="in" id="aiv">${[[1,"monatlich"],[3,"vierteljährlich"],[6,"halbjährlich"],[12,"jährlich"]].map(([k,l])=>`<option value="${k}" ${k==a.intervall?"selected":""}>${l}</option>`).join("")}</select></label>
      <label class="f">Nächste Rechnung am<input type="date" class="in" id="anx" value="${nx}"></label><label class="chk" style="flex:none"><input type="checkbox" id="aak" ${a.aktiv!==0?"checked":""}> aktiv</label></div>
    <div class="small muted">Am Stichtag (bzw. beim nächsten Programmstart) wird automatisch ein Entwurf erzeugt. Du prüfst ihn und klickst „Fertigstellen“.</div></div>`,
    [...(a.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      const x_ = await api("/api/recurring/save", {id:a.id, name:$("#an",mb).value||"Abo", invoice_id:+$("#ai",mb).value, intervall:+$("#aiv",mb).value, naechstes:$("#anx",mb).value, aktiv:$("#aak",mb).checked?1:0});
      if (x_.erzeugt) toast(x_.erzeugt + " Entwurf/Entwürfe erzeugt"); }}]);
  if (r === "del") await api("/api/recurring/delete", {id:a.id});
  if (r) { await reload(); if (view==="abo") vAbo(); else toast("Abo gespeichert"); }
}
async function vertragDialog(v){
  const r = await modal(v.id?"Wartungsvertrag":"Neuer Wartungsvertrag", `<div class="fr">
    <label class="f">Bezeichnung<input class="in" id="vn" value="${esc(v.name||"")}" placeholder="z. B. Jahreswartung Medientechnik Saal 1"></label>
    <div class="row"><label class="f">Kunde<select class="in" id="vc"><option value="">–</option>${S.customers.map(c=>`<option value="${c.id}" ${c.id==v.customer_id?"selected":""}>${esc(cname(c))}</option>`).join("")}</select></label>
      <label class="f">Projekt<select class="in" id="vp"><option value="">–</option>${S.projects.map(p=>`<option value="${p.id}" ${p.id==v.project_id?"selected":""}>${esc(p.nr+" "+p.name)}</option>`).join("")}</select></label></div>
    <div class="row"><label class="f">Intervall (Monate)<input class="in num" id="vi" value="${v.intervall||12}"></label><label class="f">Nächster Termin<input type="date" class="in" id="vx" value="${v.naechste||""}"></label><label class="f">Erinnern … Tage vorher<input class="in num" id="vv" value="${v.vorlauf??14}"></label></div>
    <div class="row"><label class="f">Baustein<select class="in" id="va"><option value="">– frei –</option>${S.articles.map(a=>`<option value="${a.id}" ${a.id==v.article_id?"selected":""}>${esc(a.nr+" "+a.name)}</option>`).join("")}</select></label><label class="f" style="flex:.5">Preis €<input class="in num" id="vpr" value="${nde(v.preis||0)}"></label></div>
    <label class="f">Leistungsbeschreibung (auf der Rechnung)<textarea class="in" id="vb" rows="2">${esc(v.beschreibung||"")}</textarea></label>
    <div class="row"><label class="chk" style="flex:none"><input type="checkbox" id="var" ${v.auto_rechnung?"checked":""}> bei „Erledigt“ Rechnungsentwurf erzeugen</label><label class="chk" style="flex:none"><input type="checkbox" id="vak" ${v.aktiv?"checked":""}> aktiv</label></div>
    <label class="f">Notiz<input class="in" id="vno" value="${esc(v.notiz||"")}"></label></div>`,
    [...(v.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      const d = {id:v.id, name:$("#vn",mb).value||"Wartung", customer_id:+$("#vc",mb).value||null, project_id:+$("#vp",mb).value||null, intervall:+$("#vi",mb).value||12, naechste:$("#vx",mb).value,
        vorlauf:+$("#vv",mb).value||0, article_id:+$("#va",mb).value||null, preis:pnum($("#vpr",mb).value), beschreibung:$("#vb",mb).value, auto_rechnung:$("#var",mb).checked?1:0, aktiv:$("#vak",mb).checked?1:0, notiz:$("#vno",mb).value};
      await api("/api/vertrag/save", d); }}], true);
  if (r === "del" && await confirmBox("Wartungsvertrag löschen?")) await api("/api/vertrag/delete", {id:v.id});
  if (r) { await reload(); vAbo(); }
}
// ---- Bank-Abgleich ----
let bankTx = [];
async function pwPrompt(name, wrong){
  let pw = null;
  const r = await modal(wrong ? "Passwort falsch" : "Passwort nötig", `<div class="fr"><div class="small">${wrong?"<b>Das Passwort war falsch.</b> ":""}„${esc(name)}“ ist passwortgeschützt.</div>
    <label class="f">Passwort<input class="in" type="password" id="ppw" autocomplete="off"></label></div>`,
    [{label:"Abbrechen"},{label:"Öffnen", cls:"pri", value:1, onClick: async mb => { pw = $("#ppw", mb).value; if (!pw) return false; }}], false,
    mb => { const i = $("#ppw", mb); setTimeout(()=>i.focus(), 50); i.onkeydown = e => { if (e.key === "Enter") $(".md .mf .btn.pri", mb).click(); }; });
  return r ? pw : null;
}
async function vBank(){
  const hist = await api("/api/bank/history");
  const openInv = S.invoices.filter(i=>["rechnung","storno"].includes(i.typ)&&i.status==="offen");
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Bank-Abgleich", "Kontoauszug als PDF, CSV oder Excel einlesen – Zahlungseingänge werden den offenen Rechnungen zugeordnet, Ausgaben übernommen", expButtons("bank"))}
    <div id="kontobox" style="margin-bottom:16px">${kontoCard()}</div>
    <div class="dz" id="bkdz" style="margin-bottom:16px"><b>Kontoauszug (PDF, CSV oder Excel) hier ablegen</b><span class="muted">PDF-Kontoauszug aus dem Online-Banking oder Postfach – oder CSV-/Excel-Export (C24: Konto → Umsätze → Export). Der Kontostand wird automatisch übernommen. Gescannte Auszüge werden per Texterkennung gelesen${S.ocr?"":" (Texterkennung nicht installiert)"}.</span><div style="margin-top:10px"><button class="btn pri" id="bkpick">${ic("up")} Kontoauszug auswählen</button></div></div>
    <div id="bktx"></div>
    <div class="card" style="overflow:hidden;margin-top:16px"><div class="hd"><h3>Bereits übernommen</h3><div class="act small muted">${hist.length}</div></div><div class="scroll" style="max-height:340px"><table class="t"><tbody>
    ${hist.map(t=>`<tr data-bt="${t.id}"><td class="num">${dde(t.datum)}</td><td><b>${esc(t.name)}</b><div class="small muted">${esc(t.zweck).slice(0,90)}</div></td><td><span class="badge ${t.status==="paid"?"ok":t.status==="ausgabe"?"bad":""}">${{paid:"Rechnung bezahlt",ausgabe:"Ausgabe",einnahme:"Einnahme",ignore:"ignoriert"}[t.status]||t.status}</span></td><td class="r num">${eur(t.betrag)}</td></tr>`).join("") || `<tr><td class="empty">Noch nichts importiert.</td></tr>`}
    </tbody></table></div></div></div>`;
  selectify({kind:"bank", rows:"tr[data-bt]", id:"data-bt", rerender:vBank, actions:[
    {label:"Ignorieren", run: async ids => { await bulk("bank", "ignore", ids); vBank(); }},
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Bankbuchung(en) aus der Liste löschen? Bereits übernommene Belege und bezahlte Rechnungen bleiben erhalten. Beim nächsten Import desselben Auszugs werden die Buchungen wieder angeboten.")) return false;
      await bulk("bank", "delete", ids); vBank(); }}]});
  const dz = $("#bkdz");
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); }; dz.ondragleave = () => dz.classList.remove("over");
  const load = async (f, pw) => { if (/\.pdf$/i.test(f.name)) toast("Kontoauszug wird gelesen …");
    let r;
    try { r = await upload("/api/upload/bank", f, pw ? {"X-Password": encodeURIComponent(pw)} : {}); } catch (e) { toast(f.name + ": konnte nicht gelesen werden", true); return; }
    if (r.needs_password) { const p2 = await pwPrompt(f.name, r.wrong); if (p2) load(f, p2); return; }
    if (!r.ok) { toast(r.error, true); return; } bankTx = r.tx; renderBankTx(openInv);
    toast(r.tx.length + " Buchungen erkannt" + (r.saldo ? ` · Kontostand ${eur(r.saldo.saldo)}` : "") + (/\.pdf$/i.test(f.name) ? " – bitte kurz gegenprüfen" : ""));
    if (r.saldo) { await reload(); const kc = $("#kontobox"); if (kc) kc.innerHTML = kontoCard(); const k2 = $("#kset"); if (k2) k2.onclick = kontoDialog; } };
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0]); };
  $("#bkpick").onclick = () => pickFiles(".pdf,.csv,.txt,.xlsx,.xls", fs => load(fs[0]));
  const ks = $("#kset"); if (ks) ks.onclick = kontoDialog;
  if (bankTx.length) renderBankTx(openInv);
}
function renderBankTx(openInv){
  const neu = bankTx.filter(t=>t.neu);
  if (!$("#bktx")) return;
  $("#bktx").innerHTML = `<div class="card" style="overflow:hidden"><div class="hd"><h3>${neu.length} neue Buchungen</h3><div class="act small muted">${bankTx.length-neu.length} schon bekannt (ausgeblendet)</div><div class="act"><button class="btn sm pri" id="bkok">${ic("check")} Übernehmen</button></div></div>
    <table class="t"><thead><tr><th>Datum</th><th>Name / Verwendungszweck</th><th class="r">Betrag</th><th style="width:380px">Aktion</th></tr></thead><tbody>
    ${neu.map((t,i)=>`<tr data-bi="${bankTx.indexOf(t)}"><td class="num">${dde(t.datum)}</td><td><b>${esc(t.name)}</b><div class="small muted">${esc(t.zweck).slice(0,120)}</div></td><td class="r num"><b style="color:${t.betrag>0?"var(--ok)":"var(--bad)"}">${eur(t.betrag)}</b></td>
      <td><div class="row" style="gap:6px"><select class="in" data-k="aktion" style="flex:.8">${(t.betrag>0?[["paid","Rechnung bezahlt"],["einnahme","Sonstige Einnahme"],["ignore","Ignorieren (privat)"]]:[...(t.vorschlag?[["paid","Erstattung zu Storno"]]:[]),["ausgabe","Betriebsausgabe"],["ignore","Ignorieren (privat)"]]).map(([k,l])=>`<option value="${k}" ${t.aktion===k?"selected":""}>${l}</option>`).join("")}</select>
      ${t.betrag>0||t.vorschlag?`<select class="in" data-k="invoice_id">${`<option value="">– Rechnung –</option>`+openInv.filter(o=>t.betrag>0?o.typ==="rechnung":o.typ==="storno").map(o=>`<option value="${o.id}" ${t.vorschlag&&t.vorschlag.id==o.id?"selected":""}>${esc(o.nr)} · ${esc(invName(o))} · ${eur(o.summe)}</option>`).join("")}</select>`:`<select class="in" data-k="kategorie">${S.kategorien.map(k=>`<option ${t.kategorie===k?"selected":""}>${k}</option>`).join("")}</select>`}</div>
      ${t.hinweis?`<div class="small" style="margin-top:3px;color:var(--warn)">${esc(t.hinweis)}</div>`:""}${t.vorschlag?`<div class="small" style="margin-top:3px;color:${t.sicher>=3?"var(--ok)":"var(--warn)"}">${t.sicher>=3?"✓ Rechnungsnummer im Verwendungszweck":t.sicher>=2?"Betrag + Name passen":"nur Betrag passt – bitte prüfen"}</div>`:""}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">Keine neuen Buchungen.</td></tr>`}
    </tbody></table></div>`;
  $("#bkok").onclick = async () => {
    const items = $$("[data-bi]").map(tr => { const t = Object.assign({}, bankTx[+tr.dataset.bi]); $$("[data-k]", tr).forEach(e => t[e.dataset.k] = e.value); return t; });
    if (items.some(t=>t.aktion==="paid"&&!t.invoice_id)) { toast("Bitte bei „Rechnung bezahlt“ eine Rechnung wählen", true); return; }
    const r = await api("/api/bank/apply", {items}); if (!r.ok) return;
    toast(`${r.bezahlt} Rechnung(en) bezahlt · ${r.ausgaben} Ausgabe(n) · ${r.einnahmen} Einnahme(n)`); bankTx = []; await reload(); vBank();
  };
}
// ---- Anlagen & Inventar ----
let asYear = thisYear;
async function vAssets(){
  const rows = await api("/api/afa?year="+asYear);
  const tot = rows.reduce((a,r)=>a+r.afa,0), rest = rows.filter(r=>!r.abgang).reduce((a,r)=>a+r.restwert,0);
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Anlagen & Inventar", (S.gwg_brutto !== false ? "Equipment über 800 € (brutto, Kleinunternehmer) wird abgeschrieben (AfA) · GWG bis 800 € sofort" : "Equipment über 800 € netto wird abgeschrieben (AfA) · GWG bis 800 € netto sofort") + " · Inventar mit Seriennummern", yearSel("asy", asYear) + expButtons("assets", () => ({year:asYear})) + `<button class="btn pri" id="asnew">${ic("plus")} Anlagegut</button>`)}
    <div class="grid g3" style="margin-bottom:16px"><div class="card kpi"><div class="l">AfA ${asYear}</div><div class="v">${eur(tot)}</div><div class="s">fließt in die EÜR</div></div>
      <div class="card kpi"><div class="l">Restbuchwert Ende ${asYear}</div><div class="v">${eur(rest)}</div><div class="s">${rows.filter(r=>!r.abgang).length} Gegenstände</div></div>
      <div class="card kpi"><div class="l">Inventar gesamt</div><div class="v">${eur(rows.reduce((a,r)=>a+r.betrag,0))}</div><div class="s">Anschaffungskosten</div></div></div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Bezeichnung</th><th>Kategorie</th><th>Seriennr. / Standort</th><th>Kauf</th><th class="r">AK (brutto)</th><th>Methode</th><th class="r">AfA ${asYear}</th><th class="r">Restwert</th></tr></thead><tbody>
    ${rows.map(a=>`<tr class="click" data-a="${a.id}" style="${a.abgang?"opacity:.55":""}"><td><b>${esc(a.bezeichnung)}</b>${a.abgang?` <span class="badge">Abgang ${dde(a.abgang)}</span>`:""}</td><td class="small">${esc(a.kategorie||"")}</td><td class="small">${esc([a.seriennr,a.standort].filter(Boolean).join(" · "))}</td><td class="num">${dde(a.kaufdatum)}</td>
      <td class="r num">${eur(a.betrag)}</td><td class="small">${a.methode==="gwg"?"GWG sofort":"linear "+nde(a.nd_jahre,0)+" J."}</td><td class="r num"><b>${eur(a.afa)}</b></td><td class="r num">${eur(a.restwert)}</td></tr>`).join("") || `<tr><td colspan="8" class="empty">Noch keine Anlagegüter. Beim Beleg-Import kannst du Equipment direkt als Anlagegut übernehmen.</td></tr>`}
    </tbody><tfoot><tr><td colspan="6">Summe</td><td class="r num">${eur(tot)}</td><td class="r num">${eur(rest)}</td></tr></tfoot></table></div>
    <div class="small muted" style="margin-top:8px">Nutzungsdauer laut amtlicher AfA-Tabelle prüfen. Computer-Hardware und Software: 1 Jahr (voller Abzug im Kaufjahr). Als Kleinunternehmer ist der Bruttobetrag die Anschaffungskosten; die 800-€-Grenze gilt netto.</div></div>`;
  $("#asy").onchange = e => { asYear = +e.target.value; vAssets(); };
  $("#asnew").onclick = () => editAsset({kaufdatum:todayIso(), nd_jahre:7, methode:"linear", kategorie:S.afa_presets[1][0]});
  $$("[data-a]").forEach(r => r.onclick = () => editAsset(rows.find(a=>a.id==r.dataset.a)));
  selectify({kind:"asset", rows:"tr[data-a]", id:"data-a", rerender:vAssets, actions:[
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Anlagegut/Anlagegüter löschen?")) return false; await bulk("asset", "delete", ids); await reload(); vAssets(); }}]});
}
async function editAsset(a){
  const pr = modal(a.id?"Anlagegut bearbeiten":"Neues Anlagegut", `<div class="fr">
    <div class="row"><label class="f">Bezeichnung<input class="in" id="ab" value="${esc(a.bezeichnung||"")}" placeholder="z. B. Allen & Heath SQ-5"></label><label class="f" style="flex:.8">Kategorie<select class="in" id="ak">${S.afa_presets.map(([k,n])=>`<option data-nd="${n}" ${k===a.kategorie?"selected":""}>${esc(k)}</option>`).join("")}</select></label></div>
    <div class="row"><label class="f">Kaufdatum<input type="date" class="in" id="ad" value="${a.kaufdatum||""}"></label><label class="f">Betrag brutto €<input class="in num" id="abt" value="${nde(a.betrag||0)}"></label><label class="f" style="flex:.6">Nutzungsdauer (J.)<input class="in num" id="an" value="${nde(a.nd_jahre||5,0)}"></label>
      <label class="f">Methode<select class="in" id="am"><option value="linear" ${a.methode!=="gwg"?"selected":""}>linear (AfA)</option><option value="gwg" ${a.methode==="gwg"?"selected":""}>GWG sofort (bis 800 € netto)</option></select></label></div>
    <div class="small" id="agwg"></div>
    <div class="row"><label class="f">Seriennummer<input class="in" id="as" value="${esc(a.seriennr||"")}"></label><label class="f">Standort<input class="in" id="ast" value="${esc(a.standort||"")}"></label><label class="f">Abgang / verkauft am<input type="date" class="in" id="aab" value="${a.abgang||""}"></label></div>
    <label class="f">Notiz<input class="in" id="ano" value="${esc(a.notiz||"")}"></label></div>`,
    [...(a.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
      const d = {id:a.id, bezeichnung:$("#ab",mb).value||"Anlagegut", kategorie:$("#ak",mb).value, kaufdatum:$("#ad",mb).value, betrag:pnum($("#abt",mb).value), nd_jahre:pnum($("#an",mb).value)||1,
        methode:$("#am",mb).value, beleg_id:a.beleg_id||null, seriennr:$("#as",mb).value, standort:$("#ast",mb).value, notiz:$("#ano",mb).value, abgang:$("#aab",mb).value, project_id:a.project_id||null};
      await api("/api/asset/save", d); }}], true);
  const mb = $$(".mb").pop();
  // v2.1.0: GWG basis like the server - Kleinunternehmer gross (no input tax), Regelbesteuerung net
  const hint = () => { const v = pnum($("#abt",mb).value); const br = S.gwg_brutto !== false; const ak = br ? v : v/1.19; const gwg = ak <= 800;
    const lbl = br ? `${eur(ak)} (brutto = Anschaffungskosten)` : `${eur(ak)} netto`;
    $("#agwg",mb).innerHTML = v ? (gwg ? `<span style="color:var(--ok)">✓ ${lbl} – geringwertig, Sofortabzug möglich</span>` : `<span class="muted">${lbl} – über 800 €, wird über die Nutzungsdauer abgeschrieben</span>`) : ""; return gwg; };
  $("#abt",mb).onchange = () => { $("#am",mb).value = hint() ? "gwg" : "linear"; };
  $("#ak",mb).onchange = e => { $("#an",mb).value = e.target.selectedOptions[0].dataset.nd; };
  hint();
  const r = await pr;
  if (r === "del" && await confirmBox("Anlagegut löschen?")) await api("/api/asset/delete", {id:a.id});
  if (r) { await reload(); vAssets(); }
}
// ---- Fahrten ----
let trY = thisYear;
async function vTrips(){
  const f = await api("/api/fahrten?year="+trY);
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Fahrten", "Dienstfahrten mit dem Privat-Pkw (km-Pauschale → EÜR) und Fahrten zur Arbeit (Entfernungspauschale → Werbungskosten)", yearSel("try", trY) + expButtons("fahrten", () => ({year:trY})))}
    <div class="grid g3" style="margin-bottom:16px"><div class="card kpi"><div class="l">Dienstfahrten</div><div class="v">${nde(f.dienst_km,1)} km</div><div class="s">${eur(f.dienst_eur)} Betriebsausgabe</div></div>
      <div class="card kpi"><div class="l">Fahrten zur Arbeit</div><div class="v">${f.pendel_tage} Tage</div><div class="s">${eur(f.pendel_eur)} Werbungskosten</div></div>
      <div class="card kpi"><div class="l">km-Satz Dienstfahrt</div><div class="v">${nde(S.settings.km_dienst||0.3,2)} €</div><div class="s">änderbar in Einstellungen</div></div></div>
    <div class="card" style="margin-bottom:14px"><div class="bd"><div class="row" style="flex-wrap:wrap">
      <label class="f" style="flex:.6">Datum<input type="date" class="in" id="fd" value="${todayIso()}"></label>
      <label class="f" style="flex:.7">Art<select class="in" id="fa"><option value="dienst">Dienstfahrt (gefahrene km gesamt)</option><option value="pendel">Fahrt zur Arbeit (einfache Entfernung)</option></select></label>
      <label class="f">Ziel<input class="in" id="fz" placeholder="z. B. IHK Mönchengladbach"></label><label class="f">Zweck<input class="in" id="fw" placeholder="Inbetriebnahme, Aufmaß …"></label>
      <label class="f" style="flex:.4">km<input class="in num" id="fk"></label>
      <label class="f" style="flex:.8">Projekt<select class="in" id="fp"><option value="">–</option>${S.projects.map(p=>`<option value="${p.id}">${esc(p.nr+" "+p.name)}</option>`).join("")}</select></label>
      <button class="btn pri" style="flex:none" id="fadd">${ic("plus")} Eintragen</button></div></div></div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Datum</th><th>Art</th><th>Ziel</th><th>Zweck</th><th>Projekt</th><th class="r">km</th><th class="r">€</th><th></th></tr></thead><tbody>
    ${f.rows.map(r=>{ const p = S.projects.find(p=>p.id==r.project_id); return `<tr><td class="num">${dde(r.datum)}</td><td><span class="badge ${r.art==="pendel"?"":"acc"}">${r.art==="pendel"?"zur Arbeit":"Dienstfahrt"}</span></td><td>${esc(r.ziel)}</td><td class="small muted">${esc(r.zweck)}</td><td class="small">${p?esc(p.nr):""}</td><td class="r num">${nde(r.km,1)}</td>
      <td class="r num">${r.art==="pendel"?"":eur(r.km*(S.settings.km_dienst||0.3))}</td><td class="r"><button class="btn sm ghost danger" data-fdel="${r.id}">${ic("trash")}</button></td></tr>`; }).join("") || `<tr><td colspan="8" class="empty">Noch keine Fahrten in ${trY}.</td></tr>`}
    </tbody></table></div></div>`;
  $("#try").onchange = e => { trY = +e.target.value; vTrips(); };
  $("#fadd").onclick = async () => { const d = {datum:$("#fd").value, art:$("#fa").value, ziel:$("#fz").value, zweck:$("#fw").value, km:pnum($("#fk").value), project_id:+$("#fp").value||null};
    if (!d.km) { toast("km fehlen", true); return; } await api("/api/fahrt/save", d); vTrips(); };
  $$("[data-fdel]").forEach(b => b.onclick = async () => { await api("/api/fahrt/delete", {id:+b.dataset.fdel}); vTrips(); });
  selectify({kind:"fahrt", rows:[...$$("[data-fdel]")].map(b => b.closest("tr")), id: el => el.querySelector("[data-fdel]").dataset.fdel, rerender:vTrips, actions:[
    {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Fahrt(en) löschen?")) return false; await bulk("fahrt", "delete", ids); vTrips(); }}]});
}
// ---- project: BOM + handover ----
async function bomImport(p){
  pickFiles(".csv,.xlsx,.xlsm,.txt", async fs => {
    const r = await upload("/api/upload/bom", fs[0]);
    if (!r.ok) { toast(r.error, true); return; }
    const preise = r.preise || {};
    const mats = [...new Set(r.rows.map(x_=>x_.material).filter(Boolean))];
    const pr = modal("Stückliste übernehmen – " + fs[0].name, `<div class="row" style="margin-bottom:10px;align-items:flex-end;flex-wrap:wrap"><label class="f" style="flex:none;width:120px">Aufschlag %<input class="in num" id="bauf" value="${nde(S.settings.aufschlag ?? 20,0)}"></label>
      ${mats.map(m=>`<label class="f" style="flex:none;width:140px">${esc(m)} €/kg<input class="in num bmp" data-m="${esc(m)}" value="${preise[m]!=null?nde(preise[m]):""}"></label>`).join("")}</div>
      <div class="scroll" style="max-height:52vh"><table class="t"><thead><tr><th></th><th>Nr.</th><th>Benennung</th><th class="r">Menge</th><th>Material</th><th class="r">Masse</th><th>EK je Stk €</th><th class="r">VK gesamt</th></tr></thead><tbody id="bomb">
      ${r.rows.map((x_,i)=>`<tr data-ri="${i}"><td><input type="checkbox" class="bu" checked style="accent-color:var(--acc)"></td><td class="small">${esc(x_.nr)}</td><td><b>${esc(x_.name)}</b></td><td class="r num">${nde(x_.qty, Number.isInteger(x_.qty)?0:2)} ${esc(x_.unit)}</td><td class="small">${esc(x_.material)}</td><td class="r num small">${x_.masse_kg?nde(x_.masse_kg,3)+" kg":""}</td>
        <td><input class="in num bek" value="0,00" style="width:90px;text-align:right"></td><td class="r num bvk"></td></tr>`).join("")}</tbody></table></div>
      <div class="small muted" style="margin-top:6px">EK = Masse × €/kg (sobald ein Materialpreis eingetragen ist), sonst von Hand eintragen. VK = EK × Menge × (1 + Aufschlag). Die Positionen landen als „Material“ unter Leistungen & Material.</div>`,
      [{label:"Abbrechen"},{label:"Übernehmen", cls:"pri", value:"ok", onClick: async mb => {
        const a = pnum($("#bauf",mb).value);
        const rows = $$("#bomb tr", mb).map(tr => { const x_ = r.rows[+tr.dataset.ri]; const ek = pnum($(".bek",tr).value); return Object.assign({}, x_, {use:$(".bu",tr).checked, vk:+(ek*(1+a/100)).toFixed(2)}); });
        const pp = Object.assign({}, preise); $$(".bmp", mb).forEach(e => { if (e.value.trim()) pp[e.dataset.m] = pnum(e.value); });
        await api("/api/settings/save", {aufschlag:a}, {quiet:true});
        const x_ = await api("/api/project/bom_apply", {project_id:p.id, rows, preise:pp}); toast(x_.n + " Materialposition(en) übernommen"); }}], true);
    const mb = $$(".mb").pop();
    const priceOf = m => { const e = $$(".bmp", mb).find(e=>e.dataset.m===m); return e && e.value.trim() ? pnum(e.value) : null; };
    const fillEk = () => $$("#bomb tr", mb).forEach(tr => { const x_ = r.rows[+tr.dataset.ri]; const pk = priceOf(x_.material); const e = $(".bek",tr);
      if (e.dataset.manual !== "1" && pk != null && x_.masse_kg) e.value = nde(pk * x_.masse_kg); });
    const calc = () => { const a = pnum($("#bauf",mb).value); $$("#bomb tr", mb).forEach(tr => { const x_ = r.rows[+tr.dataset.ri]; $(".bvk",tr).textContent = eur(pnum($(".bek",tr).value) * x_.qty * (1+a/100)); }); };
    $$(".bek", mb).forEach(e => e.oninput = () => { e.dataset.manual = "1"; calc(); });
    $$(".bmp", mb).forEach(e => e.oninput = () => { fillEk(); calc(); });
    $("#bauf", mb).oninput = calc;
    fillEk(); calc();
    if (await pr) { await reload(); vProject(p.id); }
  });
}
async function handoverDialog(p){
  const emb = f => /\.(pdf|jpe?g|png|webp|bmp|tiff?|gif)$/i.test(f.name);
  const def = f => emb(f) && ["Blockschaltbild","Zeichnung","CAD-Zeichnung","Foto","Schweißdokument","Dokument","Stückliste"].includes(f.kind) && !/^Uebergabe_/.test(f.name);
  const r = await modal("Übergabe-Dokumentation erstellen", `<div class="fr"><div class="small muted">Deckblatt, Inhaltsverzeichnis und alle gewählten PDFs/Bilder in einem PDF. Andere Dateien (DWG, Q-SYS …) werden aufgelistet.</div>
    <div class="scroll card" style="max-height:44vh;padding:6px 10px">${p.files.map(f=>`<label class="chk" style="padding:4px 0"><input type="checkbox" class="hf" value="${f.id}" ${def(f)?"checked":""}> <span class="badge" style="background:${KIND_COL[f.kind]||"#888"}1c;color:${KIND_COL[f.kind]||"#888"}">${esc(f.kind)}</span> ${esc(f.name)} <span class="small muted">${esc(f.folder)}</span>${emb(f)?"":` <span class="small muted">(nur gelistet)</span>`}</label>`).join("") || `<div class="muted">Keine Dateien im Projekt.</div>`}</div>
    <label class="f">Hinweise zur Übergabe (optional)<textarea class="in" id="hn" rows="3" placeholder="z. B. Zugangsdaten übergeben, Einweisung am …, Wartungsintervall"></textarea></label></div>`,
    [{label:"Abbrechen"},{label:"PDF erstellen", cls:"pri", value:"ok", onClick: async mb => {
      const ids = $$(".hf", mb).filter(c=>c.checked).map(c=>+c.value);
      if (!ids.length) { toast("Bitte mindestens eine Datei auswählen", true); return false; }
      const x_ = await api("/api/project/handover", {id:p.id, file_ids:ids, notes:$("#hn",mb).value}); if (x_.ok) toast("Übergabe-Doku erstellt"); }}], true);
  if (r) vProject(p.id);
}

// prevent the window from navigating when files are dropped outside a drop zone
window.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("drop", e => e.preventDefault());
