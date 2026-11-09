// PA Rechnung v2.0.17 - Direkt drucken (auch Blanko-Vordrucke) (Editor, Liste, Briefe, Dokumente aus Vorlagen)
// Knopf "Drucken" + Strg+P im Editor, Druck-Dialog (Drucker, Kopien, Seiten, beidseitig, schwarzweiss),
// "kuenftig ohne Nachfrage", Sammeldruck in der Rechnungsliste, Karte "Drucken" in den Einstellungen.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  let busy = false;

  async function poll(job, titel){
    for (let i = 0; i < 400; i++) {
      await new Promise(r => setTimeout(r, 700));
      const st = await api("/api/print/status?job=" + job, undefined, {quiet:true});
      if (!st) continue;
      if (st.state === "fertig") { toast(`Gedruckt: ${titel} (${st.seiten} Seite${st.seiten === 1 ? "" : "n"}${st.drucker ? " · " + st.drucker : ""})`); return true; }
      if (st.state === "fehler") { toast(st.fehler || "Drucken fehlgeschlagen", true); return false; }
    }
    return false;
  }

  // ask for printer & options (or print directly) -> opt or null
  async function askOpts(titel, ev, withAtt){
    const info = await api("/api/print/info", undefined, {quiet:true}); if (!info) return null;
    if (!info.drucker.length && !info.windows) { toast("Kein Drucker gefunden", true); return null; }
    const base = {drucker:info.gewaehlt, kopien:1, seiten:"", duplex:info.duplex, sw:info.sw, anlagen:true};
    if (info.direkt && !(ev && ev.shiftKey)) return base;
    let opt = null;
    const r = await modal("Drucken – " + titel, `<div class="fr">
      <label class="f">Drucker<select class="in" id="pdr">${info.drucker.map(d => `<option ${d === info.gewaehlt ? "selected" : ""}>${esc(d)}</option>`).join("") || `<option value="">Windows-Standarddrucker</option>`}</select></label>
      <div class="row"><label class="f" style="flex:.4">Kopien<input class="in num" id="pkp" value="1"></label>
        <label class="f">Seiten (leer = alle, z. B. 1-2,4)<input class="in" id="psz" placeholder="alle"></label></div>
      <label class="chk"><input type="checkbox" id="pdx" ${info.duplex ? "checked" : ""}> beidseitig (wenn der Drucker es kann)</label>
      <label class="chk"><input type="checkbox" id="psw" ${info.sw ? "checked" : ""}> schwarzweiß</label>
      ${withAtt ? `<label class="chk"><input type="checkbox" id="pan" checked> Anlagen mitdrucken</label>` : ""}
      <label class="chk"><input type="checkbox" id="pdi"> künftig ohne diesen Dialog drucken (mit Umschalt+Klick erscheint er wieder)</label></div>`,
      [{label:"Abbrechen"}, {label:"Drucken", cls:"pri", value:1, onClick: async mb => {
        opt = {drucker:$("#pdr", mb).value, kopien:Math.max(1, Math.round(pnum($("#pkp", mb).value)) || 1), seiten:$("#psz", mb).value.trim(),
          duplex:$("#pdx", mb).checked, sw:$("#psw", mb).checked, anlagen:$("#pan", mb) ? $("#pan", mb).checked : true};
        if ($("#pdi", mb).checked) await api("/api/print/direkt", {an:true}, {quiet:true}); }}], false,
      mb => { const k = $("#pkp", mb); if (k) k.onkeydown = e => { if (e.key === "Enter") $(".mf .pri", mb).click(); }; });
    return r ? opt : null;
  }

  async function run(url, body, titel, ev, withAtt){
    if (busy) { toast("Es wird gerade gedruckt …"); return false; }
    const opt = await askOpts(titel, ev, withAtt); if (!opt) return false;
    busy = true;
    try {
      const r = await api(url, Object.assign({}, body, {opt})); if (!r || !r.ok) return false;
      toast("Wird gedruckt …");
      return await poll(r.job, titel);
    } finally { busy = false; }
  }

  // several documents from the list
  window.printDocs = async (ids, ev) => {
    const locked = ids.filter(id => { const i = S.invoices.find(x => x.id == id); return i && i.typ === "rechnung" && i.status !== "entwurf" && !i.locked; }).length;
    if (locked && !await ask(`${locked} Rechnung(en) werden beim Drucken festgeschrieben (wie beim PDF). Weiter?`)) return false;
    const ok = await run("/api/print/invoice", {ids:ids.map(Number)}, ids.length + " Dokument(e)", ev, true);
    if (ok) { await reload(); if (view === "inv") vInvoices(); }
    return ok;
  };

  // editor: invoice / offer / order confirmation / storno, letter, document from template
  async function printEditor(ev){
    if (!cur) return;
    if (cur.typ === "brief" || cur.typ === "vorlage") {
      if (cur.typ === "brief" && !+cur.vorlage_id) return run("/api/print/brief", {brief:window.briefPayload ? briefPayload() : cur}, "Brief", ev, false);
      // Word/LibreOffice template: create the file first, then print it
      if (!window.briefSave || !await briefSave(true, true)) return;
      if (!cur.datei) { toast("Dokument wurde nicht erstellt", true); return; }
      return run("/api/print/file", {path:cur.datei}, cur.datei.split(/[\\/]/).pop(), ev, false);
    }
    // v2.0.17: no positions yet -> blank form: printed as it is, without ENTWURF, number, saving or locking
    if (!(cur.items || []).length && (!cur.id || cur.status === "entwurf"))
      return run("/api/print/invoice", {inv:cur, blanko:true}, "Blanko-" + (DOCT[cur.typ] || "Dokument"), ev, false);
    const draft = cur.status === "entwurf";
    if (draft) return run("/api/print/invoice", {inv:cur}, "Entwurf", ev, true);
    if (!cur.locked) {
      if (!cur.id || curSnap() !== curBase) { if (!await saveInvoice(false, false, true)) return; }
      if (cur.typ === "rechnung" && !await ask("Die Rechnung wird beim Drucken festgeschrieben (wie beim PDF) – danach nur noch Storno möglich. Drucken?")) return;
    }
    const ok = await run("/api/print/invoice", {id:cur.id}, (DOCT[cur.typ] || "Dokument") + " " + (cur.nr || ""), ev, true);
    if (ok && !cur.locked && cur.id) { await reload(); cur = await api("/api/invoice?id=" + cur.id); curBase = curSnap(); vEditor(); }
  }
  window.printEditor = printEditor;

  EXT.after.push(n => {
    if (n !== "vEditor" || !cur || $("#bprint")) return;
    const act = $(".ed .mid .ph .act") || $("#main .ph .act"); if (!act) return;
    const b = document.createElement("button"); b.className = "btn"; b.id = "bprint";
    b.innerHTML = `${ic("inv")} Drucken`; b.title = !(cur.items || []).length && (!cur.id || cur.status === "entwurf") ? "Blanko-Vordruck drucken (ohne Positionen, ohne Nummer, wird nicht gespeichert) – Strg+P" : cur.status === "entwurf" ? "Entwurf drucken (mit Vermerk ENTWURF, wird nicht festgeschrieben) – Strg+P" : "Drucken – Strg+P · Umschalt+Klick: Druck-Dialog";
    b.onclick = ev => printEditor(ev);
    act.insertBefore(b, act.querySelector(".pri") || null);
  });
  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "p" && view === "editor" && cur && !$(".mb")) { e.preventDefault(); printEditor(e); }
  }, true);

  // settings › Dokumente: card "Drucken"
  async function card(host){
    const info = await api("/api/print/info", undefined, {quiet:true}); if (!info) return;
    const l = info.letzter || {};
    host.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>Drucken</h3></div><div class="bd fr">
      <div class="row" style="align-items:flex-end;flex-wrap:wrap"><label class="f">Drucker für Dokumente<select class="in" id="spdr">${info.drucker.map(d => `<option ${d === info.gewaehlt ? "selected" : ""}>${esc(d)}</option>`).join("") || `<option value="">(keine Drucker gefunden)</option>`}</select></label>
        <label class="chk" style="flex:none"><input type="checkbox" id="spdx" ${info.duplex ? "checked" : ""}> beidseitig</label>
        <label class="chk" style="flex:none"><input type="checkbox" id="spsw" ${info.sw ? "checked" : ""}> schwarzweiß</label>
        <label class="chk" style="flex:none"><input type="checkbox" id="spdi" ${info.direkt ? "checked" : ""}> ohne Druck-Dialog drucken</label></div>
      <div class="small muted">Knopf <b>Drucken</b> (oder Strg+P) im Editor von Rechnung, Angebot, Auftragsbestätigung, Storno, Brief und Dokument aus Vorlage; mehrere Dokumente über die Auswahl in der Liste. Windows-Standarddrucker: ${esc(info.standard || "–")}.${l.zeit ? ` Letzter Druck: ${dde(l.zeit.slice(0, 10))} ${l.zeit.slice(11, 16)} – ${l.ok ? esc(l.titel) + " (" + l.seiten + " S.)" : `<span style="color:var(--bad)">${esc(l.fehler || "")}</span>`}` : ""}</div></div></div>`;
    const sv = async () => { await api("/api/settings/save", {print_opts:{drucker:$("#spdr", host).value, duplex:$("#spdx", host).checked, sw:$("#spsw", host).checked}}, {quiet:true});
      await api("/api/print/direkt", {an:$("#spdi", host).checked}, {quiet:true}); toast("Druck-Einstellungen gespeichert"); };
    ["#spdr", "#spdx", "#spsw", "#spdi"].forEach(id => $(id, host).onchange = sv);
  }
  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "docs") return;
    const page = $("#main .page"); if (!page || $("#printhost")) return;
    const h = document.createElement("div"); h.id = "printhost";
    const fh = $("#uifonthost"); fh ? page.insertBefore(h, fh) : page.appendChild(h); card(h);
  });
})();
