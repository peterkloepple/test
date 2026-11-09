// PA Rechnung v2.0.5 - Briefe: Reiter "Brief" beim neuen Dokument, Briefvorlage aus dem Vorlagen-Katalog,
// v2.0.5: Reiter "Aus Vorlage" - jede Vorlage des Katalogs als Baum (Kategorie > Ordner), ausfuellen oder Kopie,
// Liste "Briefe & Dokumente" unter Rechnungen & Angebote
// Autor: T. Pfeiffer
(function(){
  DOCT.brief = "Brief"; DOCT.vorlage = "Dokument aus Vorlage";
  const FILLDOC = /\.(docx|dotx|docm|dotm|odt|ott|ods|ots|xlsx|xltx|xlsm|xltm)$/i;
  const DTYP = [["rechnung","Rechnung"],["angebot","Angebot"],["auftrag","Auftragsbestätigung"],["brief","Brief"],["vorlage","Aus Vorlage"]];
  const keepOf = () => ({customer_id:cur.customer_id, kdnr:cur.kdnr, addr:cur.addr, project_id:cur.project_id});
  const switchTo = t => { const keep = keepOf();
    if (t === "brief") toBrief(keep); else if (t === "vorlage") cur = Object.assign(blankDok(), keep); else cur = Object.assign(blankInvoice(t), keep);
    vEditor(); };
  function blankDok(){
    return {id:null, bid:null, typ:"vorlage", customer_id:null, kdnr:"", addr:[], project_id:null, datum:todayIso(), betreff:"", anrede:"", text:"", gruss:"",
      vorlage_id:0, datei:"", items:[], attachments:[]};
  }
  const FILL = /\.(docx|dotx|docm|dotm|odt|ott)$/i;
  let VL = null, VLt = 0, BR = null;
  const loadVl = async (force) => { if (!VL || force || Date.now() - VLt > 30000) { const d = await api("/api/vorlagen", undefined, {quiet:true}); VL = (d && d.vorlagen) || []; VLt = Date.now(); } return VL; };
  const loadBr = async () => { const d = await api("/api/briefe", undefined, {quiet:true}); BR = (d && d.briefe) || []; return BR; };
  const FELD = {anschrift:"Anschrift", datum:"Datum", betreff:"Betreff", anrede:"Anrede", text:"Text", gruss:"Grußformel", inhaber:"Inhaber/Unterschrift",
    name:"Name", firma:"Firma", kunde:"Kunde", strasse:"Straße", plz:"PLZ", ort:"Ort", plz_ort:"PLZ Ort", kdnr:"Kunden-Nr.", absender:"Absender", projekt:"Projekt", meinefirma:"Meine Firma"};

  function autoAnrede(c){
    if (!c) return "Sehr geehrte Damen und Herren,";
    const an = (c.anrede||"").trim(), nm = (c.name||"").trim().split(/\s+/).pop() || "";
    if (/^herr/i.test(an) && nm) return `Sehr geehrter ${an} ${nm},`;
    if (/^frau/i.test(an) && nm) return `Sehr geehrte ${an} ${nm},`;
    return "Sehr geehrte Damen und Herren,";
  }
  function blankBrief(){
    const b = S.brief || {};
    return {id:null, bid:null, typ:"brief", customer_id:null, kdnr:"", addr:[], project_id:null, datum:todayIso(), betreff:"", anrede:"Sehr geehrte Damen und Herren,",
      anredeAuto:true, text:"", gruss:b.gruss || "Mit freundlichen Grüßen", vorlage_id:b.vorlage || 0, datei:"", items:[], attachments:[]};
  }
  window.blankBrief = blankBrief;
  const toBrief = keep => { cur = Object.assign(blankBrief(), keep); const c = S.customers.find(c=>c.id==cur.customer_id); if (c) cur.anrede = autoAnrede(c); };
  const payload = () => ({art:cur.typ === "vorlage" ? "vorlage" : "brief", bid:cur.bid, datum:cur.datum, customer_id:cur.customer_id, project_id:cur.project_id, kdnr:cur.kdnr, addr:cur.addr,
    betreff:cur.betreff, anrede:cur.anrede, text:cur.text, gruss:cur.gruss, vorlage_id:+cur.vorlage_id || 0, font:cur.font || null});

  // ---------- open / list ----------
  window.openBrief = async (id, dup) => {
    if (!id) return;
    pageLeave(); selClear();
    if (!dup && editorTake("b" + id)) { view = "editor"; viewArg = null; renderSide(); vEditor(); return; }
    const r = await api("/api/brief?id=" + id); if (!r || r.ok === false) return;
    cur = Object.assign(r.art === "vorlage" ? blankDok() : blankBrief(), {id:"b"+r.id, bid:r.id, customer_id:r.customer_id, project_id:r.project_id, kdnr:r.kdnr||"", addr:r.anschrift||[], datum:r.datum,
      betreff:r.betreff||"", anrede:r.anrede||"", anredeAuto:false, text:r.text||"", gruss:r.gruss||"", vorlage_id:r.vorlage_id||0, font:r.font||null, datei:r.datei_da?r.datei_abs:""});
    if (dup) Object.assign(cur, {id:null, bid:null, datum:todayIso(), datei:""});
    curBase = dup ? "" : curSnap();
    view = "editor"; viewArg = null; renderSide(); vEditor();
  };
  window.newBrief = (arg={}) => { newInvoice({typ:"brief", customer_id:arg.customer_id}); };
  window.newFromVorlage = (vid, arg={}) => { newInvoice({typ:"vorlage", customer_id:arg.customer_id, project_id:arg.project_id}); if (vid) { cur.vorlage_id = vid; curBase = curSnap(); vEditor(); } };

  // ---------- editor ----------
  const _vEditor = window.vEditor;
  window.vEditor = function(...a){
    if (cur && cur.typ === "brief") {
      if (cur.anredeAuto === undefined) { const clean = curBase === curSnap();
        toBrief({customer_id:cur.customer_id, kdnr:cur.kdnr, addr:cur.addr, project_id:cur.project_id}); if (clean) curBase = curSnap(); }
      return vBrief();
    }
    if (cur && cur.typ === "vorlage") {
      if (cur.betreff === undefined) { const clean = curBase === curSnap(); const pid = cur.project_id;
        cur = Object.assign(blankDok(), keepOf(), {project_id:pid}); if (clean) curBase = curSnap(); }
      return vDok();
    }
    return _vEditor.apply(this, a);
  };
  EXT.after.push(n => {
    if (n !== "vEditor" || !cur || ["brief","vorlage"].includes(cur.typ) || cur.id) return;
    const seg = $("#dtyp"); if (!seg || seg.querySelector("[data-t=brief]")) return;
    [["brief","Brief","Brief mit einer Vorlage aus dem Vorlagen-Katalog schreiben"],["vorlage","Aus Vorlage","Neues Dokument aus einer beliebigen Vorlage des Katalogs"]].forEach(([t,l,ti]) => {
      const b = document.createElement("button"); b.dataset.t = t; b.textContent = l; b.title = ti; b.onclick = () => switchTo(t); seg.appendChild(b); });
  });

  function vlOptions(list, sel){
    const ok = list.filter(v => v.status !== "fehlt" && !v.dublette_von);
    const briefe = ok.filter(v => v.kategorie === "brief" && FILL.test(v.name));
    const andere = ok.filter(v => v.kategorie !== "brief" && FILL.test(v.name));
    const nicht = ok.filter(v => v.kategorie === "brief" && !FILL.test(v.name));
    const o = v => `<option value="${v.id}" ${v.id==sel?"selected":""}>${esc(v.name)}${v.ordner?"  ·  "+esc(v.ordner):""}</option>`;
    return `<option value="0" ${!+sel?"selected":""}>Eigenes Briefpapier (PDF, wie Rechnungen)</option>`
      + (briefe.length ? `<optgroup label="Briefvorlagen">${briefe.map(o).join("")}</optgroup>` : "")
      + (andere.length ? `<optgroup label="Andere Word-/LibreOffice-Vorlagen">${andere.map(o).join("")}</optgroup>` : "")
      + (nicht.length ? `<optgroup label="Nicht ausfüllbar (bitte als .docx speichern)">${nicht.map(v=>`<option value="${v.id}" disabled>${esc(v.name)}</option>`).join("")}</optgroup>` : "");
  }

  let pvT = null;
  function briefPreview(ms=450){
    if (!showPv) return;
    clearTimeout(pvT);
    pvT = setTimeout(async () => {
      const bz = $("#busy"); if (bz) bz.classList.add("on");
      const r = await api("/api/brief/preview", payload(), {quiet:true});
      const box = $("#pvimgs"); if (!box) return;
      if (bz) bz.classList.remove("on");
      if (!r || r.ok === false) { box.innerHTML = `<div class="empty">${esc((r&&r.error)||"Vorschau nicht verfügbar")}</div>`; return; }
      if (!r.vorlage) {
        box.innerHTML = r.pages ? Array.from({length:r.pages}, (_,i)=>`<img src="/preview/${r.token}/${i}.png">`).join("") : `<div class="empty">Vorschau nicht verfügbar (pypdfium2 fehlt).</div>`;
        $("#pvinfo").textContent = `${r.pages||0} Seite(n) · eigenes Briefpapier`; return;
      }
      $("#pvinfo").textContent = "Word-/LibreOffice-Vorlage";
      if (r.fehler) { box.innerHTML = `<div class="card" style="margin:14px"><div class="bd small"><div class="alert bad" style="cursor:default"><span>${esc(r.fehler)}</span></div></div></div>`; return; }
      box.innerHTML = `<div class="card" style="margin:14px"><div class="bd">
        <div style="font:600 15px var(--disp);margin-bottom:4px">${esc(r.name)}</div>
        <div class="small muted" style="margin-bottom:10px">${esc(r.ordner||"(Hauptordner)")} · die Vorlage bleibt unverändert, es entsteht eine neue Datei</div>
        ${r.felder.length
          ? `<div class="hl small" style="margin-bottom:10px"><b>${r.felder.length} Platzhalter erkannt</b> – werden ausgefüllt:<br>${r.felder.map(f=>`<span class="badge ok" style="margin:3px 3px 0 0">${esc(FELD[f]||f)}</span>`).join("")}</div>`
          : `<div class="alert" style="cursor:default;margin-bottom:10px"><span><b>Keine Platzhalter in der Vorlage</b> – Anschrift, Datum, Betreff, Text und Gruß werden oben in die Vorlage eingefügt. Briefkopf und Fußzeile der Vorlage bleiben.</span></div>`}
        <details class="small"><summary style="cursor:pointer">Platzhalter für eigene Vorlagen</summary>
          <div class="muted" style="margin:6px 0">In Word an die gewünschte Stelle schreiben – Schreibweise egal: <code>{{Betreff}}</code>, <code>[Betreff]</code>, <code>«Betreff»</code> oder <code>&lt;&lt;Betreff&gt;&gt;</code>. Funktioniert auch in Kopf- und Fußzeile.</div>
          ${r.hilfe.map(h=>`<code style="display:inline-block;margin:2px 4px 2px 0">${esc(h)}</code>`).join("")}</details>
        <div class="small muted" style="margin-top:12px">Vorschau gibt es nur für das eigene Briefpapier. Mit <b>Brief erstellen</b> wird die ausgefüllte Datei gespeichert und in Word geöffnet.</div>
      </div></div>`;
    }, ms);
  }

  async function vBrief(){
    const c = S.customers.find(c=>c.id==cur.customer_id);
    const isNew = !cur.id;
    const btns = [`<button class="btn ghost" id="tgpv">${ic("eye")} Vorschau</button>`];
    if (cur.datei) btns.push(`<button class="btn" id="bropen" title="Erstellte Datei öffnen">${ic("open")} Öffnen</button><button class="btn ghost" id="brdir" title="Im Ordner zeigen">${ic("folder")}</button>`);
    if (cur.bid) btns.push(`<button class="btn" id="brdup">${ic("copy")} Duplizieren</button>`);
    btns.push(`<button class="btn" id="brsave">${ic("save")} Speichern</button><button class="btn pri" id="brmake">${ic("pdf")} Brief erstellen & öffnen</button>`);
    const tops = S.texts || [];
    $("#main").innerHTML = `<div class="page full"><div class="ed ${showPv?"":"nopv"}" style="grid-template-columns:minmax(0,1fr) ${showPv?"clamp(320px,30vw,560px)":"0"}">
      <div class="mid"><div class="inner">
        <div class="ph" style="margin-bottom:10px"><div><h1>${isNew?"Neuer Brief":"Brief"}</h1><div class="sub">${cur.datei?`Datei: <a href="#" id="brfile">${esc(cur.datei.split(/[\\/]/).pop())}</a>`:"Briefvorlage wählen, Text schreiben, erstellen"}</div></div>
          <div class="act">${btns.join("")}</div></div>
        ${isNew?`<div class="seg" id="dtyp" style="margin-bottom:14px">${DTYP.map(([k,l])=>`<button data-t="${k}" class="${k==="brief"?"on":""}">${l}</button>`).join("")}</div>`:""}
        <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-bottom:16px">
          <div class="card"><div class="bd">
            <label class="f">Empfänger</label>
            <div class="cpick" style="margin:4px 0 8px"><input class="in" id="cq" placeholder="Kunde suchen (Name, Firma, Kd-Nr.) …" value="${esc(c?cname(c)+"  ·  "+c.kdnr:"")}" autocomplete="off"><div class="dd" id="cdd" hidden></div></div>
            <label class="f">Anschrift<textarea class="in" id="addr" rows="5">${esc((cur.addr||[]).join("\n"))}</textarea></label>
            <div class="row" style="margin-top:8px"><button class="btn sm" id="newcust" type="button">${ic("plus")} Neuer Kunde</button><span class="sp"></span>
              <label class="f" style="flex:none;width:170px">Projekt<select class="in" id="proj"><option value="">– kein –</option>${S.projects.map(p=>`<option value="${p.id}" ${p.id==cur.project_id?"selected":""}>${esc(p.nr+" "+p.name)}</option>`).join("")}</select></label></div>
          </div></div>
          <div class="card"><div class="bd fr">
            <label class="f">Briefvorlage<select class="in" id="brvl"><option>wird geladen …</option></select></label>
            <div class="small muted" id="brvlh" style="margin:-4px 0 4px"></div>
            ${window.fontSelect ? `<label class="f brfont">Schrift (eigenes Briefpapier)${fontSelect("brfont", cur.font, cur.project_id)}</label>` : ""}
            <div class="row"><label class="f">Datum<input type="date" class="in" id="brdatum" value="${esc(cur.datum||"")}"></label>
              <label class="f">Kunden-Nr.<input class="in" id="brkdnr" value="${esc(cur.kdnr||"")}"></label></div>
            <div class="small muted">Gespeichert wird in ${cur.project_id?"den Projektordner <b>Briefe</b>":"<b>Datenordner › Briefe › Jahr</b>"}.</div>
          </div></div>
        </div>
        <div class="sec"><div class="h"><b>Betreff</b></div><input class="in" id="brbetreff" value="${esc(cur.betreff)}" placeholder="z. B. Ihre Anfrage vom …"></div>
        <div class="sec"><div class="h"><b>Anrede</b><span class="sp"></span><span class="small muted">${cur.anredeAuto?"automatisch aus dem Kunden":""}</span></div><input class="in" id="branrede" value="${esc(cur.anrede)}"></div>
        <div class="sec"><div class="h"><b>Text</b><span class="sp"></span><select class="in" id="brtb" style="width:auto;max-width:330px;padding:4px 8px;font-size:12.5px"><option value="">Textbaustein einsetzen …</option>${tops.map(t=>`<option value="${t.id}">${esc(t.text.slice(0,70))}</option>`).join("")}</select></div>
          <textarea class="in" id="brtext" rows="14" placeholder="Brieftext …">${esc(cur.text)}</textarea></div>
        <div class="sec"><div class="h"><b>Grußformel</b></div><input class="in" id="brgruss" value="${esc(cur.gruss)}"></div>
      </div></div>
      <div class="pv" ${showPv?"":"hidden"}><div class="bar"><b>Vorschau</b><span class="muted" id="pvinfo"></span><span class="sp"></span><span class="busy" id="busy"></span></div><div id="pvimgs"></div></div>
    </div></div>`;
    bindCommon($(".mid"));
    const set = (id, f, pv=true) => { const e = $("#"+id); e.oninput = () => { cur[f] = e.value; if (f==="anrede") cur.anredeAuto = false; if (pv) briefPreview(); }; };
    set("brbetreff","betreff"); set("branrede","anrede"); set("brtext","text"); set("brgruss","gruss"); set("brdatum","datum"); set("brkdnr","kdnr");
    $("#addr").oninput = e => { cur.addr = e.target.value.split("\n").filter(l=>l.trim()!==""); briefPreview(); };
    $("#proj").onchange = e => { cur.project_id = e.target.value ? +e.target.value : null; vBrief(); };
    $("#brtb").onchange = e => { const t = tops.find(t=>t.id==e.target.value); if (t) { const ta = $("#brtext"); const p = ta.selectionStart ?? ta.value.length;
      ta.value = ta.value.slice(0,p) + t.text + ta.value.slice(p); cur.text = ta.value; briefPreview(); } e.target.value = ""; };
    $$("#dtyp button").forEach(b => b.onclick = () => { if (b.dataset.t !== "brief") switchTo(b.dataset.t); });
    $("#tgpv").onclick = () => { showPv = !showPv; vBrief(); };
    $("#newcust").onclick = async () => { const id = await editCustomer({}); if (id) { setCustomer(id); if (cur.anredeAuto) cur.anrede = autoAnrede(S.customers.find(c=>c.id==id)); vBrief(); } };
    const on = (id, fn) => { const e = $("#"+id); if (e) e.onclick = fn; };
    on("brsave", () => saveBrief(false));
    on("brmake", () => saveBrief(true));
    on("brdup", () => openBrief(cur.bid, true));
    on("bropen", () => api("/api/brief/oeffnen", {id:cur.bid}));
    on("brfile", e => { e && e.preventDefault && e.preventDefault(); api("/api/brief/oeffnen", {id:cur.bid}); });
    on("brdir", () => api("/api/brief/oeffnen", {id:cur.bid, ordner:true}));
    // customer picker
    const cq = $("#cq"), dd = $("#cdd"); let sel = 0, res = [];
    const draw = () => { const ql = cq.value.toLowerCase().replace(/\s+·.*$/,"");
      res = S.customers.filter(c => !ql || (c.kdnr+" "+c.firma+" "+c.name+" "+c.ort).toLowerCase().includes(ql)).slice(0, 30);
      dd.innerHTML = res.map((c,i)=>`<div class="${i===sel?"on":""}" data-c="${c.id}"><b>${esc(cname(c))}</b>${c.firma&&c.name?`<span class="muted">${esc(c.name)}</span>`:""}<small>${esc(c.kdnr)} · ${esc(c.ort||"")}</small></div>`).join("") || `<div class="muted">Kein Treffer</div>`;
      dd.hidden = false; $$("[data-c]", dd).forEach(d => d.onmousedown = () => pick(+d.dataset.c)); };
    const pick = id => { setCustomer(id); if (cur.anredeAuto) cur.anrede = autoAnrede(S.customers.find(c=>c.id==id)); dd.hidden = true; vBrief(); };
    cq.onfocus = () => { cq.select(); draw(); }; cq.oninput = () => { sel = 0; draw(); }; cq.onblur = () => setTimeout(()=>dd.hidden=true, 150);
    cq.onkeydown = e => { if (e.key==="ArrowDown"){sel=Math.min(sel+1,res.length-1);draw();e.preventDefault();} if (e.key==="ArrowUp"){sel=Math.max(0,sel-1);draw();e.preventDefault();} if (e.key==="Enter"&&res[sel]) pick(res[sel].id); };
    document.onkeydown = e => { if (view==="editor" && cur && cur.typ==="brief" && (e.ctrlKey||e.metaKey) && e.key.toLowerCase()==="s") { e.preventDefault(); saveBrief(false); } };
    // templates
    const list = await loadVl();
    const vs = $("#brvl"); if (!vs) return;
    vs.innerHTML = vlOptions(list, cur.vorlage_id);
    if (+cur.vorlage_id && !vs.value) { cur.vorlage_id = 0; vs.value = "0"; }
    const nb = list.filter(v => v.kategorie === "brief" && v.status !== "fehlt" && !v.dublette_von && FILL.test(v.name)).length;
    $("#brvlh").innerHTML = !(S.vorlagen && S.vorlagen.ordner) ? `Noch kein Vorlagen-Ordner festgelegt – <a href="#" data-go="vorlagen">Vorlagen</a>`
      : nb ? `${nb} Briefvorlage(n) im Katalog` : `Keine Briefvorlage erkannt – in <a href="#" data-go="vorlagen">Vorlagen</a> die Kategorie auf „Briefe & Anschreiben" stellen`;
    bindCommon($("#brvlh"));
    const brf = $(".brfont"); const fv = () => { if (brf) brf.style.display = +cur.vorlage_id ? "none" : ""; };
    vs.onchange = () => { cur.vorlage_id = +vs.value || 0; fv(); briefPreview(0); };
    const fs_ = $("#brfont"); if (fs_) fs_.onchange = () => { cur.font = fs_.value || null; briefPreview(0); };
    fv(); briefPreview(0);
  }

  // ---------- v2.0.5: Dokument aus Vorlage ----------
  let dkQ = "";
  function custPick(after){
    const cq = $("#cq"), dd = $("#cdd"); let sel = 0, res = [];
    const draw = () => { const ql = cq.value.toLowerCase().replace(/\s+·.*$/,"");
      res = S.customers.filter(c => !ql || (c.kdnr+" "+c.firma+" "+c.name+" "+c.ort).toLowerCase().includes(ql)).slice(0, 30);
      dd.innerHTML = res.map((c,i)=>`<div class="${i===sel?"on":""}" data-c="${c.id}"><b>${esc(cname(c))}</b>${c.firma&&c.name?`<span class="muted">${esc(c.name)}</span>`:""}<small>${esc(c.kdnr)} · ${esc(c.ort||"")}</small></div>`).join("") || `<div class="muted">Kein Treffer</div>`;
      dd.hidden = false; $$("[data-c]", dd).forEach(d => d.onmousedown = () => pick(+d.dataset.c)); };
    const pick = id => { setCustomer(id); dd.hidden = true; after(); };
    cq.onfocus = () => { cq.select(); draw(); }; cq.oninput = () => { sel = 0; draw(); }; cq.onblur = () => setTimeout(()=>dd.hidden=true, 150);
    cq.onkeydown = e => { if (e.key==="ArrowDown"){sel=Math.min(sel+1,res.length-1);draw();e.preventDefault();} if (e.key==="ArrowUp"){sel=Math.max(0,sel-1);draw();e.preventDefault();} if (e.key==="Enter"&&res[sel]) pick(res[sel].id); };
  }
  let dkT = null;
  function dokPreview(ms=300){
    clearTimeout(dkT);
    dkT = setTimeout(async () => {
      const box = $("#pvimgs"); if (!box) return;
      if (!+cur.vorlage_id) { box.innerHTML = `<div class="empty">Links eine Vorlage auswählen.</div>`; $("#pvinfo").textContent = ""; return; }
      const r = await api("/api/brief/preview", payload(), {quiet:true}); if (!$("#pvimgs")) return;
      if (!r || r.fehler) { box.innerHTML = `<div class="card" style="margin:14px"><div class="bd small"><div class="alert bad" style="cursor:default"><span>${esc((r&&(r.fehler||r.error))||"Vorlage nicht verfügbar")}</span></div></div></div>`; return; }
      $("#pvinfo").textContent = r.kategorie || "";
      box.innerHTML = `<div class="card" style="margin:14px"><div class="bd">
        <div style="font:600 15px var(--disp);margin-bottom:4px">${esc(r.name)}</div>
        <div class="small muted" style="margin-bottom:10px">${esc(r.kategorie)} · ${esc(r.art)} · ${esc(r.ordner||"(Hauptordner)")}</div>
        ${r.hinweis ? `<div class="alert" style="cursor:default;margin-bottom:10px"><span>${esc(r.hinweis)}</span></div>`
          : !r.ausfuellbar ? `<div class="hl small" style="margin-bottom:10px"><b>Wird als Kopie angelegt</b> und im passenden Programm geöffnet – die Vorlage bleibt unverändert. Kunde und Text werden hier nicht eingesetzt.</div>`
          : r.felder.length ? `<div class="hl small" style="margin-bottom:10px"><b>${r.felder.length} Platzhalter erkannt</b> – werden ausgefüllt:<br>${r.felder.map(f=>`<span class="badge ok" style="margin:3px 3px 0 0">${esc(FELD[f]||f)}</span>`).join("")}</div>`
          : `<div class="alert" style="cursor:default;margin-bottom:10px"><span><b>Keine Platzhalter</b> – die Vorlage wird als Kopie mit Datum angelegt und geöffnet.</span></div>`}
        ${r.auszug ? `<div class="small muted" style="white-space:pre-wrap;max-height:180px;overflow:auto;border-top:1px solid var(--line);padding-top:8px">${esc(r.auszug)}</div>` : ""}
        ${r.ausfuellbar ? `<details class="small" style="margin-top:10px"><summary style="cursor:pointer">Platzhalter für eigene Vorlagen</summary>
          <div class="muted" style="margin:6px 0">In Word, Excel oder LibreOffice an die gewünschte Stelle schreiben: <code>{{Firma}}</code>, <code>[Datum]</code>, <code>«Betreff»</code> …</div>
          ${r.hilfe.map(h=>`<code style="display:inline-block;margin:2px 4px 2px 0">${esc(h)}</code>`).join("")}</details>` : ""}
      </div></div>`;
    }, ms);
  }
  function dokList(list){
    const ql = dkQ.toLowerCase();
    const rs = list.filter(v => !ql || (v.name+" "+(v.ordner||"")+" "+(v.schlagworte||"")+" "+(v.kategorie_label||"")).toLowerCase().includes(ql));
    const el = $("#dklist"); if (!el) return;
    vlTree(el, rs, {key:"dokument", selected:cur.vorlage_id, allOpen:!!ql,
      badges:v => FILLDOC.test(v.name) ? ` <span class="badge ok" title="Platzhalter werden ausgefüllt">ausfüllbar</span>` : "",
      meta:v => `<span>${esc(v.art||"")}</span>`,
      onPick:v => { cur.vorlage_id = v.id; dokPreview(0); }});
  }
  async function vDok(){
    const c = S.customers.find(c=>c.id==cur.customer_id);
    const isNew = !cur.id;
    const btns = [];
    if (cur.datei) btns.push(`<button class="btn" id="bropen" title="Erstellte Datei öffnen">${ic("open")} Öffnen</button><button class="btn ghost" id="brdir" title="Im Ordner zeigen">${ic("folder")}</button>`);
    if (cur.bid) btns.push(`<button class="btn" id="brdup">${ic("copy")} Duplizieren</button>`);
    btns.push(`<button class="btn" id="brsave">${ic("save")} Speichern</button><button class="btn pri" id="brmake">${ic("open")} Dokument erstellen & öffnen</button>`);
    $("#main").innerHTML = `<div class="page full"><div class="ed" style="grid-template-columns:minmax(0,1fr) clamp(320px,30vw,560px)">
      <div class="mid"><div class="inner">
        <div class="ph" style="margin-bottom:10px"><div><h1>${isNew?"Neues Dokument aus Vorlage":"Dokument aus Vorlage"}</h1><div class="sub">${cur.datei?`Datei: <a href="#" id="brfile">${esc(cur.datei.split(/[\\/]/).pop())}</a>`:"Vorlage aus dem Katalog wählen – Word, Excel und LibreOffice werden ausgefüllt, alles andere als Kopie angelegt"}</div></div>
          <div class="act">${btns.join("")}</div></div>
        ${isNew?`<div class="seg" id="dtyp" style="margin-bottom:14px">${DTYP.map(([k,l])=>`<button data-t="${k}" class="${k==="vorlage"?"on":""}">${l}</button>`).join("")}</div>`:""}
        <div class="card" style="margin-bottom:16px"><div class="bd">
          <div class="row" style="align-items:center;margin-bottom:8px"><b style="flex:none">Vorlage</b><span class="sp"></span>
            <div class="search" style="max-width:300px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="dkq" placeholder="Vorlage suchen …" value="${esc(dkQ)}"></div></div>
          <div id="dklist" style="max-height:380px;overflow:auto;border:1px solid var(--line);border-radius:10px"><div class="empty small">wird geladen …</div></div>
        </div></div>
        <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-bottom:16px">
          <div class="card"><div class="bd">
            <label class="f">Kunde (optional)</label>
            <div class="cpick" style="margin:4px 0 8px"><input class="in" id="cq" placeholder="Kunde suchen (Name, Firma, Kd-Nr.) …" value="${esc(c?cname(c)+"  ·  "+c.kdnr:"")}" autocomplete="off"><div class="dd" id="cdd" hidden></div></div>
            <label class="f">Anschrift<textarea class="in" id="addr" rows="4">${esc((cur.addr||[]).join("\n"))}</textarea></label>
          </div></div>
          <div class="card"><div class="bd fr">
            <div class="row"><label class="f">Datum<input type="date" class="in" id="brdatum" value="${esc(cur.datum||"")}"></label>
              <label class="f">Kunden-Nr.<input class="in" id="brkdnr" value="${esc(cur.kdnr||"")}"></label></div>
            <label class="f">Projekt<select class="in" id="proj"><option value="">– kein –</option>${S.projects.map(p=>`<option value="${p.id}" ${p.id==cur.project_id?"selected":""}>${esc(p.nr+" "+p.name)}</option>`).join("")}</select></label>
            <label class="f">Titel / Betreff (optional)<input class="in" id="brbetreff" value="${esc(cur.betreff)}" placeholder="kommt in den Dateinamen und in {{Betreff}}"></label>
            <div class="small muted">Gespeichert wird ${cur.project_id?"im <b>Projektordner</b> (Unterordner nach Dateiart)":"in <b>Datenordner › Dokumente › Jahr</b>"}.</div>
          </div></div>
        </div>
        <div class="sec"><div class="h"><b>Text</b><span class="sp"></span><span class="small muted">optional – für {{Text}} in der Vorlage</span></div>
          <textarea class="in" id="brtext" rows="4">${esc(cur.text)}</textarea></div>
      </div></div>
      <div class="pv"><div class="bar"><b>Vorlage</b><span class="muted" id="pvinfo"></span><span class="sp"></span><span class="busy" id="busy"></span></div><div id="pvimgs"></div></div>
    </div></div>`;
    bindCommon($(".mid"));
    const set = (id, f) => { const e = $("#"+id); e.oninput = () => { cur[f] = e.value; }; };
    set("brbetreff","betreff"); set("brtext","text"); set("brdatum","datum"); set("brkdnr","kdnr");
    $("#addr").oninput = e => { cur.addr = e.target.value.split("\n").filter(l=>l.trim()!==""); };
    $("#proj").onchange = e => { cur.project_id = e.target.value ? +e.target.value : null; vDok(); };
    $$("#dtyp button").forEach(b => b.onclick = () => { if (b.dataset.t !== "vorlage") switchTo(b.dataset.t); });
    const on = (id, fn) => { const e = $("#"+id); if (e) e.onclick = fn; };
    on("brsave", () => saveBrief(false));
    on("brmake", () => saveBrief(true));
    on("brdup", () => openBrief(cur.bid, true));
    on("bropen", () => api("/api/brief/oeffnen", {id:cur.bid}));
    on("brfile", e => { e && e.preventDefault && e.preventDefault(); api("/api/brief/oeffnen", {id:cur.bid}); });
    on("brdir", () => api("/api/brief/oeffnen", {id:cur.bid, ordner:true}));
    custPick(vDok);
    document.onkeydown = e => { if (view==="editor" && cur && cur.typ==="vorlage" && (e.ctrlKey||e.metaKey) && e.key.toLowerCase()==="s") { e.preventDefault(); saveBrief(false); } };
    const all = (await loadVl()).filter(v => v.status !== "fehlt" && !v.dublette_von);
    if (!$("#dklist")) return;
    if (!all.length) { $("#dklist").innerHTML = `<div class="empty small">${S.vorlagen && S.vorlagen.ordner ? "Im Vorlagen-Ordner wurden noch keine Vorlagen gefunden." : "Noch kein Vorlagen-Ordner festgelegt."} <a href="#" data-go="vorlagen">Zu den Vorlagen</a></div>`; bindCommon($("#dklist")); dokPreview(0); return; }
    dokList(all);
    $("#dkq").oninput = e => { dkQ = e.target.value; dokList(all); };
    dokPreview(0);
  }

  let saving = false;
  window.briefPayload = () => payload();
  window.briefSave = (make, noOpen) => saveBrief(make, noOpen);
  async function saveBrief(make, noOpen){
    if (saving) return false; saving = true;
    const k0 = cur.id || "new";
    try {
      const dok = cur.typ === "vorlage";
      if (make && dok && !+cur.vorlage_id) { toast("Bitte eine Vorlage auswählen", true); return false; }
      const r = await api(make ? "/api/brief/erstellen" : "/api/brief/save", Object.assign(payload(), {oeffnen:!!make && !noOpen}));
      if (!r || r.ok === false) return false;
      cur.bid = r.id; cur.id = "b" + r.id; if (r.datei) cur.datei = r.datei;
      if (!dok) S.brief = Object.assign(S.brief || {}, {vorlage:+cur.vorlage_id || 0, gruss:cur.gruss});
      curBase = curSnap(); if (KEEP.inv[k0]) { delete KEEP.inv[k0]; keepSave(); renderParkbar(); }
      if (make && dok) toast(r.hinweis ? `Dokument erstellt: ${r.name} – ${r.hinweis}` : r.modus === "platzhalter" ? `Dokument erstellt: ${r.name} – ${r.platzhalter} Platzhalter ausgefüllt` : `Dokument erstellt: ${r.name} (Kopie der Vorlage)`);
      else if (make) toast(r.modus === "eingefuegt" ? `Brief erstellt: ${r.name} – Vorlage ohne Platzhalter, Inhalt wurde oben eingefügt`
        : r.modus === "briefpapier" ? `Brief erstellt: ${r.name}` : `Brief erstellt: ${r.name} – ${r.platzhalter} Platzhalter ausgefüllt`);
      else toast(dok ? "Dokument gespeichert" : "Brief gespeichert");
      VL = null; vEditor();
      return true;
    } finally { saving = false; }
  }

  // ---------- list: tab "Briefe" under Rechnungen & Angebote ----------
  let brQ = "";
  EXT.after.push(async n => {
    if (n !== "vInvoices") return;
    const page = $("#main .page"), tabs = $("#main .tabs"); if (!page || !tabs || tabs.querySelector("[data-tab=brief]")) return;
    const act = $("#main .ph .act");
    if (act && !$("#newbrief")) { const b = document.createElement("button"); b.className = "btn"; b.id = "newbrief"; b.innerHTML = `${ic("plus")} Brief`; b.onclick = () => newBrief(); act.insertBefore(b, act.querySelector("[data-go=new]")); }
    const t = document.createElement("div"); t.className = "tab" + (invTab === "brief" ? " on" : ""); t.dataset.tab = "brief";
    t.innerHTML = `Briefe & Dokumente<span class="cnt">${(S.brief && S.brief.anzahl) || 0}</span>`;
    t.onclick = () => { invTab = "brief"; vInvoices(); };
    tabs.appendChild(t);
    if (invTab !== "brief") return;
    tabs.querySelectorAll(".tab").forEach(x_ => x_.classList.toggle("on", x_ === t));
    let el = tabs.nextElementSibling; while (el) { const nx = el.nextElementSibling; el.remove(); el = nx; }
    const box = document.createElement("div"); page.appendChild(box);
    const rows = await loadBr();
    S.brief = Object.assign(S.brief || {}, {anzahl:rows.length}); $(".cnt", t).textContent = rows.length;
    const draw = () => {
      const ql = brQ.toLowerCase();
      const rs = rows.filter(r => !ql || ((r.anschrift||[]).join(" ") + " " + r.betreff + " " + (r.vorlage_name||"")).toLowerCase().includes(ql));
      box.innerHTML = `<div class="row" style="margin-bottom:14px;align-items:center">
          <div class="search" style="max-width:320px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="brq" placeholder="Empfänger, Betreff, Vorlage …" value="${esc(brQ)}"></div>
          <span class="sp"></span><span class="muted small" style="flex:none">${rs.length} Eintrag/Einträge</span><button class="btn sm" id="dknew" style="flex:none">${ic("plus")} Aus Vorlage</button></div>
        <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Datum</th><th>Art</th><th>Empfänger</th><th>Betreff</th><th>Vorlage</th><th>Datei</th><th style="width:170px"></th></tr></thead>
        <tbody>${rs.map(r=>`<tr class="click" data-brief="${r.id}"><td class="num">${dde(r.datum)}</td><td class="muted">${r.art==="vorlage"?"Dokument":"Brief"}</td><td>${esc((r.anschrift||[])[0]||"–")}</td><td><b>${esc(r.betreff||(r.art==="vorlage"?(r.vorlage_name||""):"(ohne Betreff)"))}</b></td>
          <td class="muted">${esc(r.vorlage_name||"Eigenes Briefpapier")}</td><td class="muted small">${r.datei_da?esc(r.datei.split(/[\\/]/).pop()):"noch nicht erstellt"}</td>
          <td class="r" onclick="event.stopPropagation()">${r.datei_da?`<button class="btn sm ghost" title="Datei öffnen" data-bro="${r.id}">${ic("open")}</button><button class="btn sm ghost" title="Im Ordner zeigen" data-brd="${r.id}">${ic("folder")}</button>`:""}<button class="btn sm ghost" title="Duplizieren" data-brdup="${r.id}">${ic("copy")}</button><button class="btn sm ghost danger" title="Eintrag löschen (die Datei bleibt erhalten)" data-brdel="${r.id}">${ic("trash")}</button></td></tr>`).join("")
          || `<tr><td colspan="7" class="empty">Noch keine Briefe oder Dokumente. <button class="btn sm" id="brnew0" style="margin-left:8px">${ic("plus")} Brief schreiben</button></td></tr>`}</tbody></table></div>`;
      $("#brq").oninput = e => { brQ = e.target.value; const p = e.target.selectionStart; draw(); const nq = $("#brq"); nq.focus(); nq.setSelectionRange(p,p); };
      const nb0 = $("#brnew0"); if (nb0) nb0.onclick = () => newBrief();
      $("#dknew").onclick = () => newFromVorlage();
      $$("[data-brief]", box).forEach(r => r.onclick = () => openBrief(+r.dataset.brief));
      $$("[data-bro]", box).forEach(b => b.onclick = () => api("/api/brief/oeffnen", {id:+b.dataset.bro}));
      $$("[data-brd]", box).forEach(b => b.onclick = () => api("/api/brief/oeffnen", {id:+b.dataset.brd, ordner:true}));
      $$("[data-brdup]", box).forEach(b => b.onclick = () => openBrief(+b.dataset.brdup, true));
      $$("[data-brdel]", box).forEach(b => b.onclick = async () => { await api("/api/brief/delete", {id:+b.dataset.brdel});
        if (KEEP.inv["b"+b.dataset.brdel]) { delete KEEP.inv["b"+b.dataset.brdel]; keepSave(); renderParkbar(); }
        const i = rows.findIndex(r=>r.id==b.dataset.brdel); if (i >= 0) rows.splice(i, 1); S.brief.anzahl = rows.length; $(".cnt", t).textContent = rows.length; draw(); toast("Eintrag gelöscht – die Datei bleibt erhalten"); });
    };
    draw();
  });
})();
