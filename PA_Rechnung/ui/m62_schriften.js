// PA Rechnung v2.0.13 - Schriftarten: Ordner "Schriften", Standard-Schrift, Wahl je Dokument und je Projekt, Schrift des Programms
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const BUILTIN = {Helvetica:"Helvetica, Arial, sans-serif", Times:"'Times New Roman', Times, serif", Courier:"'Courier New', Courier, monospace"};
  const LOADED = {};
  const ST_DE = {r:"Normal", b:"Fett", i:"Kursiv", bi:"Fett kursiv"};

  // load a font family from the fonts folder into the browser (for previews)
  window.fontCss = name => BUILTIN[name] || `'PAF-${name}', ${BUILTIN.Helvetica}`;
  window.fontLoad = async name => {
    if (!name || BUILTIN[name] || LOADED[name]) return;
    LOADED[name] = true;
    const u = st => `/api/fonts/file?fam=${encodeURIComponent(name)}&st=${st}`;
    for (const [st, d] of [["r", {}], ["b", {weight:"700"}], ["i", {style:"italic"}], ["bi", {weight:"700", style:"italic"}]]) {
      try { const ff = new FontFace("PAF-" + name, `url(${u(st)})`, d); await ff.load(); document.fonts.add(ff); } catch (e) {}
    }
  };
  const fonts = () => (S.fonts && S.fonts.liste) || ["Helvetica", "Times", "Courier"];
  const projFont = pid => { const p = pid && S.projects.find(p => p.id == pid); return p && p.font && fonts().includes(p.font) ? p.font : ""; };

  // <select> with "Standard (...)" + all families; value "" = inherit
  window.fontSelect = (id, val, pid, opts) => {
    const pf = projFont(pid), std = pf || (S.fonts && S.fonts.standard) || "Helvetica";
    const lbl = (opts && opts.noInherit) ? "" : `<option value="">${pf ? "wie Projekt" : "Standard"} (${esc(std)})</option>`;
    const v = val && fonts().includes(val) ? val : "";
    return `<select class="in fontsel" id="${id}" ${(opts && opts.disabled) ? "disabled" : ""}>${lbl}${fonts().map(f => `<option value="${esc(f)}" ${f === v ? "selected" : ""} style="font-family:${esc(fontCss(f))}">${esc(f)}</option>`).join("")}</select>`;
  };
  const styleSel = el => { if (!el) return; const f = el.value || (el.options[el.selectedIndex] || {}).text.replace(/^.*\((.*)\)$/, "$1"); fontLoad(f); el.style.fontFamily = fontCss(f); };

  // ---------- invoice editor ----------
  EXT.after.push(n => {
    if (n !== "vEditor" || !cur || ["brief", "vorlage"].includes(cur.typ) || $("#ifont")) return;
    const t = $("#titel"); if (!t) return;
    const row = t.closest(".row"); if (!row) return;
    const l = document.createElement("div"); l.className = "row";
    l.innerHTML = `<label class="f">Schrift${fontSelect("ifont", cur.font, cur.project_id, {disabled: !!cur.locked})}</label>`;
    row.after(l);
    const s = $("#ifont"); styleSel(s);
    if (cur.locked) s.title = "Festgeschrieben – die Schrift bleibt wie beim Ausstellen.";
    s.onchange = () => { cur.font = s.value || null; styleSel(s); schedulePreview(0); };
  });

  // ---------- project page ----------
  EXT.after.push(n => {
    if (n !== "vProject" || $("#pfont")) return;
    const ps = $("#pstat"); if (!ps) return;
    const pid = viewArg; const p = S.projects.find(p => p.id == pid);
    const w = document.createElement("span"); w.style.cssText = "display:inline-flex;align-items:center;gap:6px;margin-left:6px";
    w.innerHTML = `<span class="small muted">Schrift</span>` + fontSelect("pfont", p && p.font, null).replace('class="in fontsel"', 'class="in fontsel" style="width:auto;padding:2px 8px;font-size:12px"');
    ps.after(w);
    const s = $("#pfont"); styleSel(s); s.title = "Schrift für alle Dokumente dieses Projekts (Rechnungen, Angebote, Briefe, Kalkulation, Übergabe-Doku) – einzelne Dokumente können abweichen";
    s.onchange = async () => { await api("/api/fonts/project", {project_id:+pid, font:s.value || null}); if (p) p.font = s.value || null; styleSel(s); toast("Projekt-Schrift: " + (s.value || "Standard")); };
  });

  // ---------- settings › Dokumente: card "Schriftarten" ----------
  async function card(host){
    const v = await api("/api/fonts", undefined, {quiet:true}); if (!v) return;
    v.familien.forEach(f => fontLoad(f.name));
    const badges = f => ["r","b","i","bi"].map(k => `<span class="badge ${f.stile[k]?"ok":""}" style="${f.stile[k]?"":"opacity:.45"}" title="${f.stile[k]?"vorhanden":"fehlt – wird durch "+(k==="r"?"einen anderen Schnitt":"Normal/Fett")+" ersetzt"}">${ST_DE[k]}</span>`).join(" ");
    host.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>Schriftarten für Dokumente</h3><div class="act">
        <button class="btn sm" id="fopen">${ic("folder")} Ordner „Schriften“</button><button class="btn sm" id="fsys">Aus Windows übernehmen …</button>
        <button class="btn sm" id="fscan">Neu einlesen</button><button class="btn sm pri" id="fadd">${ic("plus")} Schriften hinzufügen</button></div></div>
      <div class="bd fr">
        <div class="row" style="align-items:flex-end"><label class="f" style="max-width:340px">Standard-Schrift für alle Dokumente${fontSelect("fstd", v.gewaehlt, null, {noInherit:true})}</label>
          <div class="small muted" style="flex:1;align-self:center">Gilt für Rechnungen, Angebote, Mahnungen, Briefe, Kalkulation, Übergabe-Doku und Berichte. Abweichend wählbar je <b>Projekt</b> (Projektseite oben) und je <b>Dokument</b> (Editor, Feld „Schrift“). Festgeschriebene Rechnungen behalten ihre Schrift.</div></div>
        <div class="dz small" id="fdz" style="padding:12px">.ttf-, .otf-, .ttc-Dateien oder ein ZIP hierher ziehen – sie landen im Ordner <b>${esc(v.ordner)}</b></div>
        <div class="scroll" style="max-height:52vh"><table class="t"><tbody>${v.familien.map(f => `<tr data-fam="${esc(f.name)}">
          <td style="width:30%"><b>${esc(f.name)}</b>${f.builtin?` <span class="small muted">eingebaut</span>`:""}<div class="small muted">${f.builtin?"immer verfügbar":f.dateien.map(d=>esc(d.datei)).join(", ")}${f.dateien.some(d=>d.variabel)?" · variable Schrift (nur Grundschnitt)":""}</div></td>
          <td><div class="fprev" style="font-family:${esc(fontCss(f.name))};font-size:17px;line-height:1.35">Rechnung 2026-042 · 1.234,56 € · <b>Gesamtbetrag</b> <i>kursiv</i> ÄÖÜß</div><div style="margin-top:3px">${badges(f)}</div></td>
          <td class="r" style="white-space:nowrap">${f.benutzt?`<span class="small muted">${f.benutzt} Dok.</span> `:""}${f.name===v.standard?`<span class="badge acc">Standard</span> `:""}<button class="btn sm ghost" data-fp="${esc(f.name)}" title="Probe-Seite als PDF-Vorschau">Probe</button>${f.builtin?"":`<button class="btn sm ghost danger" data-fd="${esc(f.name)}" title="Dateien in den Papierkorb im Datenordner">${ic("trash")}</button>`}</td></tr>`).join("")}</tbody></table></div>
        ${v.probleme.length?`<div class="alert warn" style="display:block"><b>Nicht nutzbar (${v.probleme.length}):</b><br>${v.probleme.slice(0,20).map(p=>`${esc(p.datei)} – ${esc(p.grund)}`).join("<br>")}</div>`:""}
      </div></div>`;
    const std = $("#fstd", host); styleSel(std);
    std.onchange = async () => { const r = await api("/api/fonts/default", {font:std.value}); if (r && r.ok) { S.fonts.standard = std.value; toast("Standard-Schrift: " + std.value); card(host); } };
    $("#fopen", host).onclick = () => api("/api/fonts/open", {});
    $("#fscan", host).onclick = async () => { await api("/api/fonts/rescan", {}); await reload(); card(host); toast("Schriften neu eingelesen"); };
    const up = async fs => { let n = 0, d = 0; for (const f of fs) { const r = await upload("/api/upload/font", f); if (r && r.ok) { n += r.neu.length; d += r.schon_da.length; } else toast((r && r.error) || "Fehler", true); }
      await reload(); card(host); toast(`${n} Schrift-Datei(en) hinzugefügt` + (d ? `, ${d} schon vorhanden` : "")); };
    $("#fadd", host).onclick = () => pickFiles(".ttf,.otf,.ttc,.otc,.zip", up, true);
    const dz = $("#fdz", host);
    dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); }; dz.ondragleave = () => dz.classList.remove("over");
    dz.ondrop = e => { e.preventDefault(); e.stopPropagation(); dz.classList.remove("over"); up([...e.dataTransfer.files]); };
    $$("[data-fp]", host).forEach(b => b.onclick = async () => { const r = await api("/api/fonts/probe", {font:b.dataset.fp}); if (!r || !r.token) return;
      modal("Probe – " + b.dataset.fp, `<div style="text-align:center">${Array.from({length:r.pages}, (_, i) => `<img src="/preview/${r.token}/${i}.png" style="max-width:100%;border:1px solid var(--line);border-radius:6px">`).join("")}</div>`, [{label:"Schließen"}], true); });
    $$("[data-fd]", host).forEach(b => b.onclick = async () => { const f = v.familien.find(x => x.name === b.dataset.fd) || {};
      const txt = `Schrift „${f.name}“ entfernen? Die Dateien wandern in den Papierkorb im Datenordner.` + (f.benutzt ? `\n${f.benutzt} Dokument(e) nutzen sie – offene fallen auf Projekt-/Standard-Schrift zurück, festgeschriebene Rechnungen verhindern das Entfernen.` : "");
      if (typeof ask === "function" ? !await ask(txt) : !await confirmBox(txt, "Entfernen")) return;
      const r = await api("/api/fonts/delete", {name:b.dataset.fd}); if (r && r.ok) { await reload(); card(host); toast("Schrift entfernt (Papierkorb im Datenordner)"); } });
    $("#fsys", host).onclick = () => sysDialog(host);
  }

  async function sysDialog(host){
    let q_ = "", picked = new Set();
    const pr = modal("Schriften aus Windows übernehmen", `<div class="fr"><input class="in" id="fsq" placeholder="Suchen, z. B. Segoe, Calibri, Arial …">
      <div class="small muted">Kopiert die gewählten Familien (alle Schnitte) in den Ordner „Schriften“ – so sind sie auch im Backup und auf anderen PCs mit diesem Datenordner da. Bitte die Lizenz der Schrift beachten.</div>
      <div class="scroll card" style="max-height:52vh;padding:4px 10px" id="fsl"><div class="small muted">lädt …</div></div><div class="small muted" id="fsn"></div></div>`,
      [{label:"Abbrechen"},{label:"Übernehmen", cls:"pri", value:1, onClick: async () => { if (!picked.size) { toast("Bitte mindestens eine Schrift ankreuzen", true); return false; }
        const r = await api("/api/fonts/system/add", {namen:[...picked]}); if (!r || r.ok === false) return false; toast(`${r.kopiert} Datei(en) übernommen`); }}], true);
    const draw = async () => {
      const r = await api("/api/fonts/system?q=" + encodeURIComponent(q_), undefined, {quiet:true}); const el = $("#fsl"); if (!el || !r) return;
      el.innerHTML = r.schriften.map(f => `<label class="chk" style="padding:4px 0;display:flex;gap:8px;align-items:center"><input type="checkbox" value="${esc(f.name)}" ${picked.has(f.name)?"checked":""} ${f.da?"disabled":""}>
        <span style="flex:1"><b>${esc(f.name)}</b> ${f.da?`<span class="badge ok">schon da</span>`:""}</span><span class="small muted">${["r","b","i","bi"].filter(k=>f.stile[k]).map(k=>ST_DE[k]).join(" · ")}</span></label>`).join("") || `<div class="small muted">Keine Schriften gefunden.</div>`;
      $("#fsn").textContent = r.anzahl > r.schriften.length ? `${r.schriften.length} von ${r.anzahl} angezeigt – Suche eingrenzen` : `${r.anzahl} Familien`;
      $$("input[type=checkbox]", el).forEach(c => c.onchange = () => { c.checked ? picked.add(c.value) : picked.delete(c.value); });
    };
    let t = null; $("#fsq").oninput = e => { q_ = e.target.value; clearTimeout(t); t = setTimeout(draw, 250); };
    draw();
    if (await pr) { await reload(); card(host); }
  }

  // ---------- font of the program itself (v2.0.13) ----------
  const UI_STD = {font:`"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif`, disp:`"Segoe UI Variable Display","Segoe UI",system-ui,sans-serif`};
  let SYSF = null;
  const cssName = n => `"${String(n).replace(/["\\]/g, "")}"`;
  function uiCss(name, which){
    if (!name) return UI_STD[which];
    if (BUILTIN[name]) return BUILTIN[name];
    const inFolder = (S.fonts && S.fonts.liste || []).includes(name);
    if (inFolder) { fontLoad(name); return `${cssName("PAF-" + name)}, ${cssName(name)}, ${UI_STD.font}`; }
    return `${cssName(name)}, ${UI_STD.font}`;          // installed in Windows
  }
  window.uiFontApply = (o) => {
    const st = Object.assign({}, (S && S.settings) || {}, o || {});
    const r = document.documentElement.style;
    r.setProperty("--font", uiCss(st.ui_font || "", "font"));
    r.setProperty("--disp", st.ui_font_disp === "=" ? uiCss(st.ui_font || "", "font") : uiCss(st.ui_font_disp || "", "disp"));
    const z = Math.min(150, Math.max(80, +st.ui_zoom || 100));
    document.body.style.zoom = z === 100 ? "" : String(z / 100);
    r.setProperty("--zf", String(z / 100));
  };
  // with zoom, "100vh" would be taller than the window - divide by the zoom factor
  const zcss = document.createElement("style");
  zcss.textContent = `#app{height:calc(100vh / var(--zf,1))}body.lay-edit #app{height:calc(100vh / var(--zf,1) - 52px)}
    .ed{height:calc(100vh / var(--zf,1))}.md{max-height:calc(90vh / var(--zf,1));width:min(640px,calc(94vw / var(--zf,1)))}.md.wide{width:min(980px,calc(96vw / var(--zf,1)))}
    .flwin.menu{max-height:calc(100vh / var(--zf,1) - 8px)}`;
  document.head.appendChild(zcss);
  const _boot = window.boot, _rel = window.reload;
  if (typeof _boot === "function") window.boot = async function(...a){ const r = await _boot.apply(this, a); uiFontApply(); return r; };
  if (typeof _rel === "function") window.reload = async function(...a){ const r = await _rel.apply(this, a); uiFontApply(); return r; };

  async function uiCard(host){
    if (!SYSF) { const r = await api("/api/fonts/system", undefined, {quiet:true}); SYSF = (r && r.schriften || []).map(f => f.name); }
    const st = S.settings, folder = (S.fonts && S.fonts.liste || []).filter(f => !BUILTIN[f]);
    const opts = (cur, first) => `${first}<optgroup label="Schriften-Ordner">${folder.map(f => `<option value="${esc(f)}" ${f===cur?"selected":""} style="font-family:${esc(fontCss(f))}">${esc(f)}</option>`).join("")}</optgroup>
      <optgroup label="In Windows installiert">${SYSF.filter(f => !folder.includes(f)).map(f => `<option value="${esc(f)}" ${f===cur?"selected":""} style="font-family:${esc(cssName(f))}">${esc(f)}</option>`).join("")}</optgroup>`;
    host.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>Schrift des Programms</h3><div class="act"><button class="btn sm" id="uifr">Standard</button></div></div>
      <div class="bd fr"><div class="row" style="flex-wrap:wrap;align-items:flex-end">
        <label class="f">Text, Menüs, Tabellen<select class="in" id="uif">${opts(st.ui_font || "", `<option value="">Standard (Segoe UI)</option>`)}</select></label>
        <label class="f">Überschriften & Zahlen-Kacheln<select class="in" id="uifd">${opts(st.ui_font_disp || "", `<option value="">Standard (Segoe UI Display)</option><option value="=" ${st.ui_font_disp==="="?"selected":""}>wie Text</option>`)}</select></label>
        <label class="f" style="flex:.45">Größe<select class="in" id="uiz">${[80,90,100,110,120,130,140,150].map(z => `<option value="${z}" ${(+st.ui_zoom||100)===z?"selected":""}>${z} %</option>`).join("")}</select></label></div>
        <div class="card" style="padding:12px 14px;background:var(--panel2)"><div style="font:600 20px var(--disp)">Rechnung 2026-042 · 1.234,56 €</div><div style="margin-top:4px">Kunden, Projekte, Belege & Bank – so sieht der Programmtext aus. ÄÖÜ äöü ß 0123456789</div></div>
        <div class="small muted">Wirkt sofort und gilt für die ganze Oberfläche (nicht für die PDFs – deren Schrift stellst du unten ein). Schriften aus dem Schriften-Ordner und alle in Windows installierten Schriften stehen zur Wahl.</div></div></div>`;
    const sv = () => { const o = {ui_font:$("#uif", host).value, ui_font_disp:$("#uifd", host).value, ui_zoom:+$("#uiz", host).value};
      Object.assign(S.settings, o); uiFontApply(o); api("/api/settings/save", o, {quiet:true}); };
    ["#uif", "#uifd", "#uiz"].forEach(id => $(id, host).onchange = sv);
    $("#uifr", host).onclick = () => { $("#uif", host).value = ""; $("#uifd", host).value = ""; $("#uiz", host).value = "100"; sv(); };
  }

  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "docs") return;
    const page = $("#main .page"); if (!page || $("#fonthost")) return;
    const u = document.createElement("div"); u.id = "uifonthost"; page.appendChild(u); uiCard(u);
    const h = document.createElement("div"); h.id = "fonthost"; page.appendChild(h); card(h);
  });
})();
