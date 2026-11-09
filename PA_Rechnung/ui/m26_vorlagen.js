// PA Rechnung v2.6.3 - Vorlagen-Katalog (Ordner wird gescannt, kategorisiert, Dubletten aussortiert; nichts wird kopiert)
// v2.6.3: Aufraeumen (m47) - Unsichere bestaetigen, Doppelte loeschen, Mehrfachauswahl, leere Dateien/Ordner, aehnliche Namen
// v2.0.5: Baumansicht Kategorie > Ordner > Unterordner > Vorlage (vlTree, auch fuer "Aus Vorlage" und Projekt)
// Autor: T. Pfeiffer
(function(){
  IC.tpl = IC.tpl || '<path d="M4 4h10l6 6v10H4z"/><path d="M14 4v6h6"/><path d="M8 14h8M8 17h5"/>';
  const vlF = {kat:"", status:"", q:"", ansicht:(() => { try { return localStorage.getItem("pa_vl_ansicht") || "baum"; } catch (e) { return "baum"; } })()};

  // ---------- v2.0.5: tree Kategorie > Ordner > Unterordner > Vorlage ----------
  if (!document.getElementById("vtree-css")) { const st = document.createElement("style"); st.id = "vtree-css"; st.textContent = `
    .vtree{font-size:13.5px}
    .vtree .vt-n{display:flex;align-items:center;gap:7px;padding:6px 10px;border-bottom:1px solid var(--line);cursor:pointer;min-height:34px}
    .vtree .vt-n:hover{background:var(--panel2)}
    .vtree .vt-n.on{background:var(--accsoft)}
    .vtree .vt-car{display:inline-block;width:12px;color:var(--ink2);transition:transform .12s;flex:none;text-align:center}
    .vtree .vt-n.open>.vt-car{transform:rotate(90deg)}
    .vtree .vt-k{font-weight:600;background:var(--panel2)}
    .vtree .vt-d{color:var(--ink2);font-weight:500}
    .vtree .vt-ic{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.7;color:var(--ink2)}
    .vtree .vt-k .vt-ic{color:var(--acc)}
    .vtree .vt-cnt{font-size:11.5px;color:var(--ink2);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:0 7px}
    .vtree .vt-meta{margin-left:auto;display:flex;align-items:center;gap:8px;flex:none;color:var(--ink2);font-size:12px}
    .vtree .vt-name{min-width:0;overflow:hidden;text-overflow:ellipsis}
    .vtree .vt-hd{display:flex;gap:6px;padding:6px 8px;border-bottom:1px solid var(--line);background:var(--panel)}`;
    document.head.appendChild(st); }
  const VT_OPEN = {};
  const vtLoad = k => { if (!VT_OPEN[k]) { let a = []; try { a = JSON.parse(localStorage.getItem("pa_vt_" + k) || "[]"); } catch (e) {} VT_OPEN[k] = new Set(a); } return VT_OPEN[k]; };
  const vtSave = k => { try { localStorage.setItem("pa_vt_" + k, JSON.stringify([...VT_OPEN[k]])); } catch (e) {} };
  // el: container, list: templates, o: {key, selected, onPick(v), meta(v)->html, actions(v)->html, bind(el, v, row), allOpen}
  window.vlTree = function(el, list, o={}){
    const key = o.key || "std", open = vtLoad(key);
    const kats = ((S.vorlagen && S.vorlagen.kategorien) || []).map(k => k.key);
    const lbl = k => (((S.vorlagen && S.vorlagen.kategorien) || []).find(x_ => x_.key === k) || {}).label || k || "Sonstiges";
    const root = {};
    list.forEach(v => { const k = v.kategorie || "sonstiges";
      const n0 = root[k] = root[k] || {dirs:{}, files:[], n:0}; n0.n++;
      let n = n0; (v.ordner || "").split(/[\\/]/).filter(Boolean).forEach(seg => { n = n.dirs[seg] = n.dirs[seg] || {dirs:{}, files:[], n:0}; n.n++; });
      n.files.push(v); });
    const sel = list.find(v => v.id == o.selected);
    if (sel) { const k = sel.kategorie || "sonstiges"; open.add(k); let pth = k; (sel.ordner||"").split(/[\\/]/).filter(Boolean).forEach(seg => { pth += "/" + seg; open.add(pth); }); }
    const isOpen = pth => o.allOpen || open.has(pth);
    const IF = '<svg class="vt-ic" viewBox="0 0 24 24"><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/></svg>';
    const IT = `<svg class="vt-ic" viewBox="0 0 24 24">${IC.tpl}</svg>`;
    const files = [];
    const pad = d => `padding-left:${10 + d * 20}px`;
    const node = (n, pth, d) => {
      let h = "";
      Object.keys(n.dirs).sort((a, b) => a.localeCompare(b, "de")).forEach(nm => { const c = n.dirs[nm], pp = pth + "/" + nm, op = isOpen(pp);
        h += `<div class="vt-n vt-d ${op?"open":""}" data-vtp="${esc(pp)}" style="${pad(d)}"><span class="vt-car">▸</span>${IF}<span class="vt-name">${esc(nm)}</span><span class="vt-cnt">${c.n}</span></div>`;
        if (op) h += node(c, pp, d + 1); });
      n.files.slice().sort((a, b) => a.name.localeCompare(b.name, "de")).forEach(v => { const i = files.push(v) - 1;
        h += `<div class="vt-n vt-f ${v.id==o.selected?"on":""}" data-vtf="${i}" style="${pad(d)}${v.status==="fehlt"?";opacity:.5":""}"><span class="vt-car"></span>${IT}<span class="vt-name"><b>${esc(v.name)}</b>${o.badges?o.badges(v):""}</span>
          <span class="vt-meta">${o.meta?o.meta(v):esc(v.art||"")}${o.actions?`<span onclick="event.stopPropagation()" style="white-space:nowrap">${o.actions(v, i)}</span>`:""}</span></div>`; });
      return h;
    };
    const ks = Object.keys(root).sort((a, b) => (kats.indexOf(a) < 0 ? 99 : kats.indexOf(a)) - (kats.indexOf(b) < 0 ? 99 : kats.indexOf(b)));
    let h = o.noTools ? "" : `<div class="vt-hd"><button class="btn sm ghost" data-vtall="1" type="button">Alle aufklappen</button><button class="btn sm ghost" data-vtall="0" type="button">Alle zuklappen</button></div>`;
    ks.forEach(k => { const op = isOpen(k);
      h += `<div class="vt-n vt-k ${op?"open":""}" data-vtp="${esc(k)}"><span class="vt-car">▸</span>${IF}<span class="vt-name">${esc(lbl(k))}</span><span class="vt-cnt">${root[k].n}</span></div>`;
      if (op) h += node(root[k], k, 1); });
    el.innerHTML = `<div class="vtree">${h || `<div class="empty small">Keine Vorlage gefunden.</div>`}</div>`;
    const redraw = () => window.vlTree(el, list, o);
    $$("[data-vtp]", el).forEach(r => r.onclick = () => { if (o.allOpen) return; const pp = r.dataset.vtp; open.has(pp) ? open.delete(pp) : open.add(pp); vtSave(key); redraw(); });
    $$("[data-vtall]", el).forEach(b => b.onclick = () => { if (b.dataset.vtall === "1") { const walk = (n, pp) => { open.add(pp); Object.keys(n.dirs).forEach(nm => walk(n.dirs[nm], pp + "/" + nm)); };
      ks.forEach(k => walk(root[k], k)); } else open.clear(); vtSave(key); redraw(); });
    $$("[data-vtf]", el).forEach(r => { const v = files[+r.dataset.vtf];
      r.onclick = () => { if (o.onPick) { o.selected = v.id; o.onPick(v); if (o.keepSel !== false) { $$(".vt-f", el).forEach(x_ => x_.classList.toggle("on", x_ === r)); } } };
      if (o.bind) o.bind(r, v); });
  };
  let VL = null, pollT = null;
  const sizeTxt = b => b >= 1048576 ? nde(b/1048576,1) + " MB" : b >= 1024 ? nde(b/1024,0) + " KB" : (b||0) + " B";
  const katOpts = (cur, auto) => `<option value="_auto">automatisch${auto?" ("+esc(((S.vorlagen&&S.vorlagen.kategorien)||[]).find(k=>k.key===auto)?.label||auto)+")":""}</option>` +
    ((S.vorlagen && S.vorlagen.kategorien) || []).map(k => `<option value="${k.key}" ${k.key===cur?"selected":""}>${esc(k.label)}</option>`).join("");

  async function chooseFolder(){
    const p = await pickFolder(); if (!p) return;
    const r = await api("/api/vorlagen/ordner", {ordner:p});
    if (r && r.ok) { await reload(); toast("Vorlagen-Ordner gesetzt – wird gescannt …"); watchScan(); if (view === "vorlagen") vVorlagen(); }
  }
  async function startScan(komplett){
    const r = await api("/api/vorlagen/scan", {komplett:!!komplett});
    if (r && r.ok) { if (!r.gestartet) toast("Scan läuft bereits"); watchScan(); if (view === "vorlagen") vVorlagen(); }
  }
  function watchScan(){
    clearInterval(pollT);
    pollT = setInterval(async () => {
      const s = await api("/api/vorlagen/scan_status", undefined, {quiet:true});
      const bar = $("#vlbar");
      if (s && s.laeuft) { if (bar) bar.innerHTML = scanBar(s); return; }
      clearInterval(pollT); pollT = null;
      if (s && s.ergebnis) {
        const e = s.ergebnis;
        if (e.ok === false) toast(e.fehler || "Scan fehlgeschlagen", true);
        else toast(`Scan fertig: ${e.eindeutig} Vorlagen · ${e.neu} neu · ${e.geaendert} geändert · ${e.entfernt} entfernt · ${e.doppelt} doppelt aussortiert`);
      }
      await reload(); if (view === "vorlagen") vVorlagen();
    }, 1000);
  }
  const scanBar = s => `<div class="hl small" style="margin-bottom:12px">Ordner wird gescannt … ${s.fortschritt} / ${s.gesamt || "?"}${s.datei?` · <span class="muted">${esc(s.datei)}</span>`:""}
    <div class="prog" style="margin-top:6px"><div style="width:${s.gesamt?Math.round(100*s.fortschritt/s.gesamt):5}%"></div></div></div>`;

  async function detail(v){
    const r = await modal(v.name, `<div class="fr nokeep">
      <div class="small muted">${esc(v.ordner || "(Hauptordner)")} · ${esc(v.art)} · ${sizeTxt(v.groesse)} · geändert ${dde((v.geaendert_datei||"").slice(0,10))}</div>
      ${v.dublette_von?`<div class="alert warn" style="cursor:default"><span><b>Doppelt</b> – gleicher Inhalt wie <b>${esc(v.original_rel)}</b>. Wird im Katalog nicht geführt; „Doppelte löschen“ legt die Kopie in den Papierkorb.</span></div>`:""}
      ${v.kopien?`<div class="hl small">${v.kopien} doppelte Kopie(n) dieser Vorlage wurden aussortiert.</div>`:""}
      ${v.status==="fehlt"?`<div class="alert bad" style="cursor:default"><span>Die Datei liegt nicht mehr im Vorlagen-Ordner.</span></div>`:""}
      <label class="f">Kategorie <span class="small muted">· automatisch erkannt: ${esc((S.vorlagen.kategorien.find(k=>k.key===v.kategorie_auto)||{}).label||"–")} (${Math.round((v.sicherheit||0)*100)} %)${v.manuell?" · von dir festgelegt":""}</span>
        <select class="in" id="vlk">${katOpts(v.manuell?v.kategorie:"_auto", v.kategorie_auto)}</select></label>
      <div class="small"><b>Begründung:</b> ${esc(v.begruendung || "–")}</div>
      ${v.schlagworte?`<div class="small"><b>Schlagworte:</b> ${esc(v.schlagworte)}</div>`:""}
      <label class="f">Notiz<input class="in" id="vln" value="${esc(v.notiz||"")}" placeholder="z. B. nur für Behörden-Aufträge"></label>
      <div class="small muted">${v.benutzt?`${v.benutzt}× verwendet, zuletzt ${dde((v.zuletzt||"").slice(0,10))}`:"noch nicht verwendet"}</div></div>`,
      [...(v.dublette_von?[{label:"Als Original festlegen", value:"orig"}, {label:"Doppelte löschen", cls:"danger", value:"deldup"}]:[]),
       ...(isUns(v)?[{label:"✓ Bestätigen", value:"ok"}]:[]),
       ...(!v.dublette_von&&v.status!=="fehlt"?[{label:"Datei löschen", value:"del"}]:[]),
       {label:"Im Ordner zeigen", value:"dir"}, {label:"Schließen"},
       {label:"Übernehmen", cls:"pri", value:"save", onClick: async mb => {
         await api("/api/vorlagen/update", {id:v.id, kategorie:$("#vlk",mb).value, notiz:$("#vln",mb).value, gesehen:true}); }}]);
    if (r === "orig") { await api("/api/vorlagen/update", {id:v.id, original:true}); toast("Als Original festgelegt"); }
    if (r === "dir") api("/api/vorlagen/oeffnen", {id:v.id, ordner:true});
    if (r === "ok") return confirmIds([v.id]);
    if (r === "deldup") return delDups([v.id]);
    if (r === "del") return delFiles([v.id], [v.rel]);
    if (r === "save" || r === "orig") { await reload(); if (view === "vorlagen") vVorlagen(); }
  }

  async function toProject(v, pid){
    const projs = S.projects.slice().sort((a,b) => (a.status==="aktiv"?0:1) - (b.status==="aktiv"?0:1) || (b.nr||"").localeCompare(a.nr||""));
    if (!projs.length) { toast("Noch keine Projekte vorhanden", true); return false; }
    const r = await modal("Vorlage in Projekt kopieren", `<div class="fr nokeep">
      <div class="small muted">Vorlage: <b>${esc(v.rel)}</b> – das Original im Vorlagen-Ordner bleibt unverändert.</div>
      <label class="f">Projekt<select class="in" id="vlp">${projs.map(p=>`<option value="${p.id}" ${p.id==pid?"selected":""}>${esc(p.nr+" "+p.name)}${p.status!=="aktiv"?" ("+esc(p.status)+")":""}</option>`).join("")}</select></label>
      <label class="f">Unterordner im Projekt<select class="in" id="vlf"><option value="">automatisch nach Dateiart</option></select></label>
      <label class="f">Dateiname<input class="in" id="vlnm" value="${esc(v.name)}"></label></div>`,
      [{label:"Abbrechen"}, {label:"In Projekt kopieren", cls:"pri", value:true, onClick: async mb => {
        const x_ = await api("/api/vorlagen/kopie", {id:v.id, project_id:+$("#vlp",mb).value, folder:$("#vlf",mb).value, name:$("#vlnm",mb).value});
        if (!x_ || !x_.ok) return false; toast("In Projekt kopiert"); }}], false,
      mb => { const load = async () => { const p = await api("/api/project?id=" + $("#vlp",mb).value);
          $("#vlf",mb).innerHTML = `<option value="">automatisch nach Dateiart</option>` + (p.folders||[]).map(o=>`<option>${esc(o)}</option>`).join(""); };
        $("#vlp",mb).onchange = load; load(); });
    if (r) await reload();
    return !!r;
  }

  function filtered(list){
    const qq = vlF.q.toLowerCase();
    return list.filter(v => {
      if (vlF.status === "doppelt") { if (!v.dublette_von || v.status === "fehlt") return false; }
      else if (vlF.status === "fehlt") { if (v.status !== "fehlt") return false; }
      else { if (v.dublette_von || v.status === "fehlt") return false;
        if (vlF.status === "neu" && !["neu","geaendert"].includes(v.status)) return false;
        if (vlF.status === "unsicher" && (v.manuell || (v.sicherheit||0) >= 0.5)) return false; }
      if (vlF.kat && v.kategorie !== vlF.kat) return false;
      return !qq || `${v.name} ${v.ordner} ${v.schlagworte||""} ${v.notiz||""} ${v.kategorie_label}`.toLowerCase().includes(qq);
    });
  }

  // ---------- v2.6.3: Aufraeumen ----------
  const isUns = v => !v.manuell && (v.sicherheit||0) < 0.5 && !v.dublette_von && v.status !== "fehlt";
  const freed = b => sizeTxt(b || 0);
  function cleanMsg(r){
    const wo = [r.papierkorb ? `${r.papierkorb} im Windows-Papierkorb` : "", r.ordner ? `${r.ordner} im Ordner „_Papierkorb_Vorlagen“` : ""].filter(Boolean).join(", ");
    toast(`${r.geloescht} gelöscht${r.bytes ? " · " + freed(r.bytes) + " frei" : ""}${wo ? " (" + wo + ")" : ""}` + (r.fehler && r.fehler.length ? ` · ${r.uebersprungen} übersprungen: ` + r.fehler.slice(0,3).join(" · ") : ""), !!(r.fehler && r.fehler.length));
  }
  async function confirmIds(ids){ const r = await api("/api/vorlagen/bestaetigen", ids === "alle" ? {alle:true} : {ids}); if (r && r.ok) toast(`${r.bestaetigt} Kategorie(n) bestätigt`); await reload(); vVorlagen(); }
  async function delDups(ids){
    const n = ids === "alle" ? (VL && VL.doppelt) : ids.length;
    if (!await confirmBox(`${n} doppelte Datei(en) löschen? Vorher wird der Inhalt noch einmal mit dem Original verglichen – das Original bleibt. Die Dateien landen im Papierkorb.`, "Löschen")) return;
    const r = await api("/api/vorlagen/doppelte_loeschen", ids === "alle" ? {alle:true} : {ids}); if (r && r.ok) cleanMsg(r); await reload(); vVorlagen();
  }
  async function delFiles(ids, names){
    if (!await confirmBox(`${ids.length} Vorlage(n) löschen?${names ? "\n\n" + names.slice(0,5).join("\n") + (names.length > 5 ? "\n…" : "") : ""}\n\nDie Dateien landen im Papierkorb.`, "Löschen")) return;
    const r = await api("/api/vorlagen/dateien_loeschen", {ids}); if (r && r.ok) cleanMsg(r); await reload(); vVorlagen();
  }
  async function cleanup(){
    const i = await api("/api/vorlagen/aufraeumen");
    if (!i || !i.ok) return;
    if (!i.erreichbar) { toast("Der Vorlagen-Ordner ist nicht erreichbar.", true); return; }
    const row = (k, n, txt, on, hint) => `<label class="chk" style="display:flex;align-items:flex-start;gap:8px;padding:7px 0;border-bottom:1px solid var(--line);${n ? "" : "opacity:.5"}">
      <input type="checkbox" data-vcl="${k}" ${n && on ? "checked" : ""} ${n ? "" : "disabled"}><span style="flex:1"><b>${n}</b> ${txt}${hint ? `<div class="small muted">${hint}</div>` : ""}</span></label>`;
    const ae = i.aehnlich || [];
    const html = `<div class="fr nokeep">
      ${i.scan_laeuft ? `<div class="alert warn" style="cursor:default"><span>Der Ordner wird gerade gescannt – bitte nach dem Scan aufräumen.</span></div>` : ""}
      ${row("unsicher", i.unsicher, "unsichere Kategorie(n) <b>bestätigen</b> – so wie erkannt", true, "Danach gelten sie als von dir festgelegt und bleiben bei jedem Scan so.")}
      ${row("doppelt", i.doppelt, `doppelte Datei(en) <b>löschen</b>${i.doppelt_bytes ? " – " + freed(i.doppelt_bytes) : ""}`, true, "Inhalt wird vorher neu mit dem Original verglichen; das Original bleibt. Briefe mit der Kopie zeigen danach aufs Original.")}
      ${row("fehlt", i.fehlt, "fehlende Vorlage(n) aus dem Katalog entfernen", true, "Dateien, die nicht mehr im Ordner liegen.")}
      ${row("neu", i.neu, "neue/geänderte als gesehen markieren", true, "")}
      ${row("leer_dateien", i.leer_dateien, "leere Datei(en) (0 Byte) löschen", false, "")}
      ${row("leer_ordner", (i.leer_ordner||[]).length, "leere(n) Ordner löschen", false, (i.leer_ordner||[]).slice(0,4).map(esc).join(" · ") + ((i.leer_ordner||[]).length > 4 ? " …" : ""))}
      <div class="small muted" style="margin-top:8px">Gelöscht wird in den Windows-Papierkorb. Liegt der Vorlagen-Ordner auf einem Netzlaufwerk/NAS, landen die Dateien im Unterordner „${esc(i.papierkorb)}“ – den kannst du später selbst leeren.</div>
      ${ae.length ? `<div style="margin-top:12px"><b>Ähnliche Namen, aber anderer Inhalt (${ae.length})</b> <span class="small muted">– z. B. „… - Kopie“, „(1)“. Nicht automatisch, bitte selbst entscheiden:</span>
        <div class="scroll" style="max-height:34vh;margin-top:6px">${ae.map(g => `<div style="border:1px solid var(--line);border-radius:8px;padding:6px 8px;margin-bottom:6px">
          ${g.dateien.map((f, k) => `<div class="row" style="align-items:center;gap:6px;padding:2px 0"><span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis" title="${esc(f.rel)}">${k === 0 ? '<span class="badge ok">neueste</span> ' : ""}${esc(f.rel)}</span>
            <span class="small muted" style="flex:none">${sizeTxt(f.groesse)} · ${f.mtime ? new Date(f.mtime*1000).toLocaleDateString("de-DE") : ""}${f.benutzt ? " · " + f.benutzt + "× benutzt" : ""}</span>
            <button class="btn sm ghost" style="flex:none" type="button" data-vae="${f.id}" title="Öffnen">${ic("open")}</button>
            <button class="btn sm ghost" style="flex:none" type="button" data-vad="${f.id}" title="Diese Datei löschen (Papierkorb)">✕</button></div>`).join("")}</div>`).join("")}</div></div>` : ""}
      </div>`;
    let res = null;
    await modal("Vorlagen aufräumen", html, [{label:"Schließen"}, {label:"Aufräumen", cls:"pri", onClick: async mb => {
      const d = {}; $$("[data-vcl]", mb).forEach(c => d[c.dataset.vcl] = c.checked);
      if (!Object.values(d).some(Boolean)) { toast("Nichts ausgewählt", true); return false; }
      if ((d.doppelt || d.leer_dateien || d.leer_ordner) && !await confirmBox("Ausgewählte Dateien/Ordner jetzt löschen (Papierkorb)?", "Aufräumen")) return false;
      res = await api("/api/vorlagen/aufraeumen", d); if (!res || !res.ok) return false; }}], true,
      mb => {
        $$("[data-vae]", mb).forEach(b => b.onclick = () => api("/api/vorlagen/oeffnen", {id:+b.dataset.vae}));
        $$("[data-vad]", mb).forEach(b => b.onclick = async () => {
          if (!await confirmBox("Diese Datei löschen (Papierkorb)?", "Löschen")) return;
          const r = await api("/api/vorlagen/dateien_loeschen", {ids:[+b.dataset.vad]}); if (r && r.ok) { cleanMsg(r); const line = b.closest(".row"); if (line) line.remove(); } });
      });
    if (res) {
      await modal("Aufgeräumt", `<div class="fr">${res.schritte.map(t => `<div class="small">✓ ${esc(t)}</div>`).join("")}
        ${(res.fehler||[]).length ? `<div class="alert warn" style="cursor:default;margin-top:8px;font-size:12.5px"><span><b>Nicht gelöscht:</b><br>${res.fehler.slice(0,10).map(esc).join("<br>")}</span></div>` : ""}</div>`, [{label:"OK", cls:"pri"}]);
    }
    await reload(); if (view === "vorlagen") vVorlagen();
  }
  window.vlCleanup = cleanup;

  async function vVorlagen(){
    VL = await api("/api/vorlagen");
    const d = VL, all = d.vorlagen || [];
    const act = all.filter(v => !v.dublette_von && v.status !== "fehlt");
    const nNeu = act.filter(v => ["neu","geaendert"].includes(v.status)).length, nUns = act.filter(v => !v.manuell && (v.sicherheit||0) < 0.5).length;
    const nFehlt = all.filter(v => v.status === "fehlt").length;
    const rows = filtered(all);
    const ls = d.letzter_scan;
    const head = pageHead("Vorlagen", d.ordner ? `${act.length} Vorlage(n) aus <b>${esc(d.ordner)}</b>${ls?` · gescannt ${dde((ls.zeit||"").slice(0,10))} ${(ls.zeit||"").slice(11,16)}`:""}${d.doppelt?` · ${d.doppelt} doppelt aussortiert`:""}`
        : "Eigene Vorlagen aus einem Ordner – wird gescannt und kategorisiert, nichts wird kopiert",
      (d.ordner ? `<button class="btn" id="vlclean" title="Unsichere bestätigen, Doppelte löschen, leere Dateien/Ordner …">${ic("check")} Aufräumen</button><button class="btn" id="vlopen">${ic("folder")} Ordner öffnen</button><button class="btn" id="vlscan" title="Neue und geänderte Dateien einlesen (Umschalt+Klick: alles komplett neu bewerten)">${ic("sync")} Ordner scannen</button>` : "") +
      `<button class="btn pri" id="vlset">${ic("folder")} ${d.ordner ? "Ordner ändern …" : "Ordner wählen …"}</button>`);
    let body = d.scan && d.scan.laeuft ? `<div id="vlbar">${scanBar(d.scan)}</div>` : `<div id="vlbar"></div>`;
    if (!d.ordner) body += `<div class="card empty">Gib den Ordner an, in dem deine Vorlagen liegen – Word, Excel, PDF, Zeichnungen, Q-SYS-/Crestron-Programme.<br>
        Das Programm scannt ihn, ordnet jede Vorlage einer Kategorie zu und sortiert doppelte aus. <b>Es wird nichts kopiert</b> – der Ordner bleibt, wie er ist.<br><br>
        <button class="btn pri" id="vlset2">${ic("folder")} Vorlagen-Ordner wählen</button></div>`;
    else if (!d.erreichbar) body += `<div class="alert bad" style="cursor:default"><span>Der Vorlagen-Ordner ist nicht erreichbar (Laufwerk/NAS getrennt oder verschoben).<br><span class="small">${esc(d.ordner)}</span></span></div>`;
    if (d.ordner && (all.length || !(d.scan && d.scan.laeuft))) body += `
      <div class="chips" style="margin-bottom:8px">${[{key:"",label:"Alle",anzahl:act.length}, ...d.kategorien.filter(k=>k.anzahl)].map(k=>`<span class="chip ${vlF.kat===k.key?"on":""}" data-vk="${k.key}">${esc(k.label)} <span class="muted">${k.anzahl}</span></span>`).join("")}</div>
      <div class="row" style="margin-bottom:12px;align-items:center;flex-wrap:wrap;gap:8px">
        <div class="seg" style="flex:none">${[["","Katalog"],["neu",`Neu/geändert (${nNeu})`],["unsicher",`Unsicher (${nUns})`],["doppelt",`Doppelte (${d.doppelt||0})`],...(nFehlt?[["fehlt",`Fehlt (${nFehlt})`]]:[])].map(([k,l])=>`<button class="${vlF.status===k?"on":""}" data-vs="${k}">${l}</button>`).join("")}</div>
        <input class="in" id="vlq" placeholder="Vorlage suchen (Name, Ordner, Schlagworte, Inhalt) …" style="flex:1;min-width:200px" value="${esc(vlF.q)}">
        <div class="seg" style="flex:none">${[["baum","Baum"],["liste","Liste"]].map(([k,l])=>`<button class="${vlF.ansicht===k?"on":""}" data-van="${k}" title="${k==="baum"?"Nach Kategorie › Ordner › Unterordner":"Tabelle mit Kategorie-Auswahl, sortierbar"}">${l}</button>`).join("")}</div>
        ${vlF.status==="neu"&&nNeu?`<button class="btn sm" id="vlseen">Alle als gesehen markieren</button>`:""}
        ${vlF.status==="unsicher"&&nUns?`<button class="btn sm pri" id="vlokall" title="Kategorie so übernehmen, wie sie erkannt wurde">${ic("check")} Alle ${nUns} bestätigen</button>`:""}
        ${vlF.status==="doppelt"&&d.doppelt?`<button class="btn sm danger" id="vldupall">Alle ${d.doppelt} Doppelten löschen</button>`:""}
        ${vlF.status==="fehlt"&&nFehlt?`<button class="btn sm danger" id="vlgone">Fehlende aus dem Katalog entfernen</button>`:""}</div>
      ${vlF.status==="doppelt"?`<div class="hl small" style="margin-bottom:10px">Gleicher Inhalt wie eine andere Vorlage – im Katalog wird nur das Original geführt. Mit „Löschen“ kommen die Kopien in den Papierkorb (Inhalt wird vorher noch einmal verglichen, das Original bleibt).</div>`:""}
      <div class="card" style="overflow:hidden" id="vlbody">${vlF.ansicht==="baum"&&rows.length?"":rows.length?`<table class="t"><thead><tr><th>Vorlage</th><th>Kategorie</th><th>Ordner</th><th>Art</th><th>Geändert</th><th class="r">Größe</th><th style="width:380px"></th></tr></thead><tbody>
        ${rows.map((v,i)=>`<tr class="click" data-vd="${i}" style="${v.status==="fehlt"?"opacity:.5":""}">
          <td><b>${esc(v.name)}</b>${v.status==="neu"?` <span class="badge ok">neu</span>`:v.status==="geaendert"?` <span class="badge warn">geändert</span>`:""}${v.kopien?` <span class="badge" title="doppelte Kopien aussortiert">+${v.kopien} doppelt</span>`:""}${v.notiz?`<div class="small muted">${esc(v.notiz)}</div>`:""}${v.dublette_von?`<div class="small muted">doppelt von ${esc(v.original_rel)}</div>`:""}</td>
          <td onclick="event.stopPropagation()"><select class="in" data-vkat="${i}" style="width:auto;max-width:240px;padding:3px 6px;font-size:12px" title="${esc(v.begruendung||"")}">${katOpts(v.manuell?v.kategorie:"_auto", v.kategorie_auto)}</select>
            <div class="small muted">${v.manuell?"von dir festgelegt":`${Math.round((v.sicherheit||0)*100)} % sicher`}${isUns(v)?` <button class="btn sm ghost" style="padding:1px 6px" data-vok="${i}" title="Kategorie so bestätigen">✓ bestätigen</button>`:""}</div></td>
          <td class="small muted">${esc(v.ordner||"–")}</td><td class="small">${esc(v.art)}</td>
          <td class="num small">${dde((v.geaendert_datei||"").slice(0,10))}</td><td class="r num small">${sizeTxt(v.groesse)}</td>
          <td class="r" style="white-space:nowrap" onclick="event.stopPropagation()">${v.status==="fehlt"?"":`<button class="btn sm ghost" data-vo="${i}" title="Vorlage im passenden Programm öffnen">${ic("open")} Öffnen</button><button class="btn sm" data-vc="${i}" title="Kopie mit Datum im Datenordner unter „Vorlagen-Kopien“ anlegen und öffnen – das Original bleibt unverändert">${ic("copy")} Kopie bearbeiten</button><button class="btn sm ghost" data-vp="${i}" title="In einen Projektordner kopieren">${ic("proj")} In Projekt</button>${v.dublette_von?`<button class="btn sm danger" data-vdd="${i}" title="Doppelte Datei löschen (Papierkorb)">Löschen</button>`:""}`}</td></tr>`).join("")}
      </tbody></table>`:`<div class="empty">${act.length||all.length?"Keine Vorlage passt zur Auswahl.":"Noch nichts gescannt."}</div>`}</div>
      <div class="small muted" style="margin-top:8px">${vlF.ansicht==="liste"?"Mehrere markieren (Kästchen links, Umschalt = Bereich) → unten bestätigen, Kategorie setzen, löschen. ":"Mehrfachauswahl: Ansicht „Liste“. "}Klick auf eine Zeile zeigt Begründung, Schlagworte und Notiz. Kategorie umstellen = deine Festlegung bleibt bei jedem Scan erhalten, ähnliche Dateien im selben Ordner werden künftig genauso eingeordnet.</div>`;
    $("#main").innerHTML = `<div class="page">${head}${body}</div>`;
    bindCommon();
    ["vlset","vlset2"].forEach(id => { const b = $("#"+id); if (b) b.onclick = chooseFolder; });
    if ($("#vlopen")) $("#vlopen").onclick = () => api("/api/open", {path:d.ordner, folder:true});
    if ($("#vlscan")) $("#vlscan").onclick = e => startScan(e.shiftKey);
    $$("[data-vk]").forEach(c => c.onclick = () => { vlF.kat = c.dataset.vk; vVorlagen(); });
    $$("[data-vs]").forEach(c => c.onclick = () => { vlF.status = c.dataset.vs; vVorlagen(); });
    $$("[data-van]").forEach(c => c.onclick = () => { vlF.ansicht = c.dataset.van; try { localStorage.setItem("pa_vl_ansicht", vlF.ansicht); } catch (e) {} vVorlagen(); });
    if (vlF.ansicht === "baum" && rows.length && $("#vlbody")) vlTree($("#vlbody"), rows, {key:"seite", allOpen:!!vlF.q || vlF.status==="doppelt" || vlF.status==="fehlt", onPick:v => detail(v), keepSel:false,
      badges:v => `${v.status==="neu"?` <span class="badge ok">neu</span>`:v.status==="geaendert"?` <span class="badge warn">geändert</span>`:""}${v.kopien?` <span class="badge">+${v.kopien} doppelt</span>`:""}${v.dublette_von?` <span class="small muted">doppelt von ${esc(v.original_rel)}</span>`:""}${v.notiz?` <span class="small muted">· ${esc(v.notiz)}</span>`:""}`,
      meta:v => `<span title="${esc(v.begruendung||"")}">${v.manuell?"von dir festgelegt":Math.round((v.sicherheit||0)*100)+" % sicher"}</span><span>${esc(v.art)}</span><span class="num">${sizeTxt(v.groesse)}</span>`,
      actions:(v) => v.status==="fehlt" ? "" : `${isUns(v)?`<button class="btn sm ghost" data-tok="${v.id}" title="Kategorie so bestätigen">✓</button>`:""}${v.dublette_von?`<button class="btn sm danger" data-tdd="${v.id}" title="Doppelte Datei löschen (Papierkorb)">Löschen</button>`:""}<button class="btn sm ghost" data-to="${v.id}" title="Vorlage im passenden Programm öffnen">${ic("open")}</button><button class="btn sm ghost" data-tc="${v.id}" title="Kopie bearbeiten (Original bleibt unverändert)">${ic("copy")}</button><button class="btn sm ghost" data-tp="${v.id}" title="In Projekt">${ic("proj")}</button>${window.newFromVorlage?`<button class="btn sm ghost" data-tn="${v.id}" title="Neues Dokument aus dieser Vorlage">${ic("plus")}</button>`:""}`,
      bind:(r, v) => { const b = (a, fn) => { const e = r.querySelector(`[${a}]`); if (e) e.onclick = fn; };
        b("data-to", () => api("/api/vorlagen/oeffnen", {id:v.id}));
        b("data-tc", async () => { const x_ = await api("/api/vorlagen/kopie", {id:v.id}); if (x_.ok) toast("Kopie angelegt: " + x_.pfad.split(/[\\/]/).pop()); });
        b("data-tp", () => toProject(v));
        b("data-tn", () => newFromVorlage(v.id));
        b("data-tok", () => confirmIds([v.id]));
        b("data-tdd", () => delDups([v.id])); }});
    let qt; if ($("#vlq")) $("#vlq").oninput = e => { clearTimeout(qt); qt = setTimeout(() => { vlF.q = e.target.value; vVorlagen().then(() => { const i = $("#vlq"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }); }, 250); };
    if ($("#vlseen")) $("#vlseen").onclick = async () => { await api("/api/vorlagen/update", {ids:act.filter(v=>["neu","geaendert"].includes(v.status)).map(v=>v.id), gesehen:true}); await reload(); vVorlagen(); };
    if ($("#vlclean")) $("#vlclean").onclick = cleanup;
    if ($("#vlokall")) $("#vlokall").onclick = () => confirmIds("alle");
    if ($("#vldupall")) $("#vldupall").onclick = () => delDups("alle");
    $$("[data-vok]").forEach(el => el.onclick = () => confirmIds([rows[+el.dataset.vok].id]));
    $$("[data-vdd]").forEach(el => el.onclick = () => delDups([rows[+el.dataset.vdd].id]));
    if (vlF.ansicht !== "baum" && rows.length) selectify({kind:"vorlage", rows:$$("#vlbody tr[data-vd]"), id: el => String(rows[+el.dataset.vd].id), rerender: vVorlagen, actions:[
      {label:"Bestätigen", run: async ids => { await confirmIds(ids.map(Number)); }},
      {label:"Kategorie setzen", run: async ids => {
        const k = await askValue("Kategorie setzen", `<label class="f">Kategorie<select class="in" id="vlbk">${((S.vorlagen&&S.vorlagen.kategorien)||[]).map(k=>`<option value="${k.key}">${esc(k.label)}</option>`).join("")}</select></label>`, mb => $("#vlbk", mb).value);
        if (k == null) return false; await api("/api/vorlagen/update", {ids:ids.map(Number), kategorie:k}); toast(ids.length + " Kategorie(n) gesetzt"); await reload(); vVorlagen(); }},
      {label:"Als gesehen", run: async ids => { await api("/api/vorlagen/update", {ids:ids.map(Number), gesehen:true}); await reload(); vVorlagen(); }},
      ...(vlF.status === "doppelt" ? [{label:"Doppelte löschen", cls:"danger", run: async ids => { await delDups(ids.map(Number)); }}]
        : [{label:"Löschen", cls:"danger", run: async ids => { const nm = rows.filter(v => ids.includes(String(v.id))).map(v => v.rel); await delFiles(ids.map(Number), nm); }}])]});
    if ($("#vlgone")) $("#vlgone").onclick = async () => { if (!await confirmBox(`${nFehlt} fehlende Vorlage(n) aus dem Katalog entfernen?`, "Entfernen")) return; await api("/api/vorlagen/fehlende_entfernen", {}); await reload(); vVorlagen(); };
    $$("[data-vd]").forEach(el => el.onclick = () => detail(rows[+el.dataset.vd]));
    $$("[data-vkat]").forEach(el => el.onchange = async () => { const v = rows[+el.dataset.vkat]; await api("/api/vorlagen/update", {id:v.id, kategorie:el.value}); toast("Kategorie gespeichert"); await reload(); vVorlagen(); });
    $$("[data-vo]").forEach(el => el.onclick = () => api("/api/vorlagen/oeffnen", {id:rows[+el.dataset.vo].id}));
    $$("[data-vc]").forEach(el => el.onclick = async () => { const r = await api("/api/vorlagen/kopie", {id:rows[+el.dataset.vc].id}); if (r.ok) toast("Kopie angelegt: " + r.pfad.split(/[\\/]/).pop()); });
    $$("[data-vp]").forEach(el => el.onclick = () => toProject(rows[+el.dataset.vp]));
    if (d.scan && d.scan.laeuft && !pollT) watchScan();
  }
  window.vlDetailById = async id => { const d = await api("/api/vorlagen"); const v = (d.vorlagen||[]).find(x_=>x_.id==id); if (v) detail(v); };

  EXT.nav.push({key:"vorlagen", label:"Vorlagen", icon:"tpl", section:"Stammdaten", cnt:() => (S.vorlagen && S.vorlagen.neu) ? "neu " + S.vorlagen.neu : ""});
  EXT.views.vorlagen = vVorlagen;

  // project page: "Aus Vorlage ..." picks a template from the catalog and copies it into the project
  EXT.after.push((n, pid) => {
    if (n !== "vProject" || !S.vorlagen || !S.vorlagen.ordner) return;
    const act = $("#main .ph .act"); if (!act || $("#vlfromp")) return;
    const b = document.createElement("button"); b.className = "btn"; b.id = "vlfromp"; b.innerHTML = `${ic("tpl")} Aus Vorlage …`;
    act.prepend(b);
    b.onclick = async () => {
      const d = await api("/api/vorlagen"); const list = (d.vorlagen||[]).filter(v => !v.dublette_von && v.status !== "fehlt");
      const projId = typeof viewArg === "number" ? viewArg : pid;
      let qq = "";
      await modal("Vorlage ins Projekt holen", `<div class="nokeep"><div class="chips" id="vpk" style="margin-bottom:8px"></div><input class="in" id="vpq" placeholder="Suchen …" style="margin-bottom:8px"><div id="vpl" class="scroll" style="max-height:52vh"></div></div>`,
        [{label:"Schließen"}], true, mb => {
          $("#vpk",mb).remove();
          const render = () => {
            const r = list.filter(v => !qq || `${v.name} ${v.ordner} ${v.schlagworte||""} ${v.kategorie_label}`.toLowerCase().includes(qq));
            vlTree($("#vpl",mb), r, {key:"projekt", allOpen:!!qq, keepSel:false,
              actions:() => `<button class="btn sm pri" data-pi="1">Ins Projekt</button>`,
              bind:(row, v) => { row.querySelector("[data-pi]").onclick = async () => { if (await toProject(v, projId)) { $(".mf .btn", mb).click(); go("project", projId); } }; }});
          };
          $("#vpq",mb).oninput = e => { qq = e.target.value.toLowerCase(); render(); };
          render();
        });
    };
  });

  // Einstellungen > Projekte & Kalkulation: card next to the project structure templates
  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "proj") return;
    const h = [...$$("#main .card .hd h3")].find(e => e.textContent.trim() === "Projekt-Strukturvorlagen"); if (!h) return;
    const card0 = h.closest(".card"); if (!card0 || $("#vlcfg")) return;
    const o = (S.vorlagen && S.vorlagen.ordner) || "";
    const c = document.createElement("div"); c.className = "card"; c.id = "vlcfg"; c.style.marginTop = "16px";
    c.innerHTML = `<div class="hd"><h3>Vorlagen-Ordner</h3><div class="act"><button class="btn sm pri" id="vlcset">${o?"Ändern …":"Ordner wählen …"}</button>${o?`<button class="btn sm" id="vlcgo">Vorlagen anzeigen</button>`:""}</div></div>
      <div class="bd fr"><div style="font:600 13px/1.4 Consolas,monospace;word-break:break-all">${o?esc(o):`<span class="muted">nicht festgelegt</span>`}</div>
      <div class="small muted">${o?`${S.vorlagen.anzahl} Vorlage(n) im Katalog. `:""}Der Ordner wird gescannt und kategorisiert, doppelte werden aussortiert – kopiert wird nichts. Zu finden unter <b>Stammdaten › Vorlagen</b>.</div></div>`;
    card0.insertAdjacentElement("afterend", c);
    $("#vlcset", c).onclick = async () => { await chooseFolder(); vSettings(); };
    const g = $("#vlcgo", c); if (g) g.onclick = () => go("vorlagen");
  });
})();
