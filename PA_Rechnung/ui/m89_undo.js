// PA Rechnung v2.1.0 - UI-Modul m89_undo: Rueckgaengig (Strg+Z, Knopf im Hinweis), Wiederherstellen
// (Strg+Y / Strg+Umschalt+Z, Knopf im Hinweis nach dem Zuruecknehmen) und Seite "Verlauf"
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m89 = '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>';
  IC.m89r = '<path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>';
  EXT.nav.push({key: "m89verlauf", label: "Verlauf", icon: "m89", section: "Stammdaten"});
  EXT.views.m89verlauf = view89;
  let busy = false;

  // ---------------------------------------------------------------- toast with "Rueckgaengig"
  function undoToast(info, redo){
    const box = $("#toast"); if (!box) return;
    $$(".m89t", box).forEach(e => e.remove());
    const t = document.createElement("div"); t.className = "tst m89t";
    t.style.cssText = "display:flex;align-items:center;gap:10px;pointer-events:auto";
    t.innerHTML = `<span style="flex:1;min-width:0">${esc(info.titel)}</span><button class="btn sm" type="button" style="flex:none;color:#fff;background:#6b4cf0;border-color:#6b4cf0">${redo ? ic("m89r") + " Wiederherstellen" : ic("m89") + " Rückgängig"}</button>`;
    $("button", t).onclick = () => { t.remove(); redo ? doRedo() : doUndo(); };
    box.appendChild(t); setTimeout(() => t.remove(), 7000);
  }

  const origApi = window.api;
  window.api = async function(path, body, opts){
    const r = await origApi.call(this, path, body, opts);
    try { if (r && r._m89 && body !== undefined && !String(path).startsWith("/api/m89/")) { S.m89_last = r._m89; undoToast(r._m89); } } catch (e) {}
    return r;
  };

  async function after(){
    await reload();
    if (view === "editor") go("inv"); else go(view, viewArg);
  }
  async function doUndo(id){
    if (busy) return; busy = true;
    try {
      const r = await api("/api/m89/undo", id ? {id} : {});
      if (r && r.ok) {
        await after();
        undoToast({titel: r.n === 1 ? `Zurückgenommen: ${r.titel[0]}` : `${r.n} Schritte zurückgenommen`}, true);
      }
    } finally { busy = false; }
  }
  async function doRedo(id){
    if (busy) return; busy = true;
    try {
      const r = await api("/api/m89/redo", id ? {id} : {});
      if (r && r.ok) {
        await after();
        undoToast({titel: r.n === 1 ? `Wiederhergestellt: ${r.titel[0]}` : `${r.n} Schritte wiederhergestellt`}, false);
      }
    } finally { busy = false; }
  }
  window.m89Undo = doUndo;
  window.m89Redo = doRedo;

  // Strg+Z outside of input fields (there the normal text undo stays)
  // v2.0.19 (R4): parked dialogs (".mb[hidden]", "Kurz wegklicken") no longer block Strg+Z;
  // held key (auto repeat) does not undo several steps; never inside the document editor
  // (there Strg+Z means "undo my typing" - undoing the last saved step would delete the document)
  // v2.1.0: Strg+Y and Strg+Umschalt+Z = Wiederherstellen, same rules
  document.addEventListener("keydown", e => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const k = (e.key || "").toLowerCase();
    const isUndo = k === "z" && !e.shiftKey, isRedo = (k === "y" && !e.shiftKey) || (k === "z" && e.shiftKey);
    if (!isUndo && !isRedo) return;
    const a = document.activeElement;
    if (a && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))) return;
    if ($(".mb:not([hidden])")) return;   // a dialog is open
    if (e.repeat || view === "editor") return;
    e.preventDefault(); isUndo ? doUndo() : doRedo();
  });

  // ---------------------------------------------------------------- page "Verlauf"
  async function view89(){
    const d = await api("/api/m89/list");
    const st = d.steps || [];
    const firstOpen = st.find(s => !s.zurueck);
    const redoable = st.filter(s => s.zurueck && s.redo);
    const firstRedo = redoable.length ? redoable[redoable.length - 1] : null;   // list is newest first -> oldest undone step
    $("#main").innerHTML = `<div class="page">${pageHead("Verlauf", "Die letzten 50 Aktionen – zurücknehmen (Strg+Z) und wiederherstellen (Strg+Y), einzeln oder bis zu einem bestimmten Punkt",
        expButtons("m89_verlauf") + `<button class="btn" id="m89clr">Verlauf leeren</button><button class="btn" id="m89redo" ${firstRedo ? "" : "disabled"}>${ic("m89r")} Wiederherstellen</button><button class="btn pri" id="m89last" ${firstOpen ? "" : "disabled"}>${ic("m89")} Letzte zurücknehmen</button>`)}
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Zeit</th><th>Aktion</th><th class="r">Änderungen</th><th>Status</th><th style="width:250px"></th></tr></thead>
      <tbody>${st.map(s => `<tr class="click" data-m89id="${s.id}" style="${s.zurueck ? "opacity:.55" : ""}"><td class="small num">${dde(s.zeit.slice(0, 10))} ${s.zeit.slice(11, 16)}</td>
        <td>${s.zurueck ? `<s>${esc(s.titel)}</s>` : `<b>${esc(s.titel)}</b>`}</td><td class="r num">${s.n || 0}</td>
        <td>${s.zurueck ? `<span class="badge">zurückgenommen ${s.zurueck_zeit ? s.zurueck_zeit.slice(11, 16) : ""}</span>` : !s.voll ? `<span class="badge warn">nicht möglich</span>` : `<span class="badge ok">offen</span>`}</td>
        <td class="r" onclick="event.stopPropagation()">${!s.zurueck && s.voll ? (firstOpen && s.id === firstOpen.id ? `<button class="btn sm" data-m89u="${s.id}">Zurücknehmen</button>`
          : `<button class="btn sm ghost" data-m89u="${s.id}" title="nimmt diesen und alle späteren Schritte zurück">bis hierhin zurücknehmen</button>`)
          : s.zurueck && s.redo ? (firstRedo && s.id === firstRedo.id ? `<button class="btn sm" data-m89r="${s.id}">${ic("m89r")} Wiederherstellen</button>`
          : `<button class="btn sm ghost" data-m89r="${s.id}" title="stellt alle älteren zurückgenommenen Schritte und diesen wieder her">bis hierhin wiederherstellen</button>`) : ""}</td></tr>`).join("")
        || `<tr><td colspan="5" class="empty">Noch keine Aktionen aufgezeichnet. Jede Änderung über die Oberfläche (Speichern, Löschen, Buchen …) erscheint hier.</td></tr>`}</tbody></table></div>
      <div class="small muted" style="margin-top:10px">Aufgezeichnet wird, was du im Programm änderst. Hintergrund-Abläufe (Eingangsordner, Bankabruf, Automatik-Regeln, Kalenderabruf) und Einstellungen außer den Nummernkreisen werden nicht aufgezeichnet.
        Wiederherstellen geht, bis du etwas Neues änderst – dann verfällt der Wiederherstellen-Stapel. Mehrere Schritte werden immer ganz oder gar nicht zurückgenommen bzw. wiederhergestellt.
        Zurücknehmen und Wiederherstellen stehen selbst im Änderungsprotokoll (GoBD). Festgeschriebene Rechnungen lassen sich nur zurücknehmen, wenn „Rechnungen frei korrigieren“ eingeschaltet ist.</div></div>`;
    bindCommon();
    $("#m89last").onclick = () => doUndo();
    $("#m89redo").onclick = () => doRedo();
    $$("[data-m89r]").forEach(b => b.onclick = () => doRedo(+b.dataset.m89r));
    $("#m89clr").onclick = async () => { await api("/api/m89/clear", {}); toast("Verlauf geleert"); view89(); };
    $$("[data-m89u]").forEach(b => b.onclick = () => doUndo(+b.dataset.m89u));
    $$("[data-m89id]").forEach(r => r.onclick = () => detail(+r.dataset.m89id));
  }
  async function detail(id){
    const d = await api("/api/m89/detail?id=" + id); if (!d || !d.step) return;
    const s = d.step;
    const btns = [{label: "Schließen"}];
    if (!s.zurueck && s.voll) btns.push({label: "Bis hierhin zurücknehmen", cls: "pri", onClick: async () => { await doUndo(s.id); }});
    if (s.zurueck && s.redo) btns.push({label: "Bis hierhin wiederherstellen", cls: "pri", onClick: async () => { await doRedo(s.id); }});
    await modal(s.titel, `<div class="small muted" style="margin-bottom:8px">${dde(s.zeit.slice(0, 10))} ${s.zeit.slice(11, 16)} · ${esc(s.pfad || "")}</div>
      <table class="t"><thead><tr><th>Bereich</th><th>Art</th><th>Eintrag</th></tr></thead><tbody>${d.changes.map(c => `<tr><td>${esc(c.bereich)}</td><td>${esc(c.art)}</td><td class="small">${esc(c.info)}</td></tr>`).join("")
        || `<tr><td colspan="3" class="empty">keine Datenänderung</td></tr>`}</tbody></table>
      ${d.files.length ? `<div style="margin-top:10px"><b>Dateien im Papierkorb</b>${d.files.map(f => `<div class="small">${esc(f.quelle)}</div>`).join("")}</div>` : ""}`, btns, true);
    if (view === "m89verlauf") view89();
  }
})();
