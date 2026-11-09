// PA Rechnung v2.0.14 - Rechnungen frei korrigieren und loeschen (auch festgeschriebene)
// Editor: "Bearbeiten" hebt die Festschreibung auf, "Loeschen" loescht das Dokument.
// Einstellungen > Dokumente: Schalter "Rechnungen frei korrigieren und loeschen".
// Autor: T. Pfeiffer
(function(){
  "use strict";
  EXT.after.push(n => {
    if (n !== "vEditor" || !cur || !cur.id || ["brief", "vorlage"].includes(cur.typ) || $("#bfrei") || !S.inv_frei) return;
    const act = $(".ed .mid .ph .act") || $("#main .ph .act"); if (!act) return;
    if (cur.locked) {
      const b = document.createElement("button"); b.className = "btn"; b.id = "bfrei";
      b.innerHTML = `${ic("save")} Bearbeiten`; b.title = "Festschreibung aufheben und die Rechnung korrigieren";
      b.onclick = async () => { if (!await ask(`${DOCT[cur.typ] || "Dokument"} ${cur.nr} wieder bearbeitbar machen? Die Aufhebung wird im GoBD-Protokoll vermerkt. Beim nächsten PDF, Druck oder Mailversand wird sie wieder festgeschrieben.`)) return;
        const r = await api("/api/invoice/unlock", {id:cur.id}); if (r && r.ok) { await reload(); openInvoice(cur.id, true); toast("Rechnung ist wieder bearbeitbar"); } };
      act.prepend(b);
    }
    const d = document.createElement("button"); d.className = "btn ghost danger"; d.id = "bfdel"; d.innerHTML = `${ic("trash")} Löschen`;
    d.onclick = async () => { const sv = cur.storno_von ? " Die zugehörige Storno-Rechnung wird mitgelöscht." : cur.typ === "storno" ? " Die ursprüngliche Rechnung wird wieder „offen“." : "";
      if (!await ask(`${DOCT[cur.typ] || "Dokument"} ${cur.status === "entwurf" ? "(Entwurf)" : cur.nr} löschen?${sv}${cur.locked ? " Die PDF-Datei wandert in den Papierkorb im Datenordner." : ""}`)) return;
      const id = cur.id; const r = await api("/api/invoice/delete", {id}); if (!r || !r.ok) return;
      if (KEEP.inv[id]) { delete KEEP.inv[id]; keepSave(); renderParkbar(); }
      curBase = null; await reload(); go("inv"); toast(r.geloescht > 1 ? `${r.geloescht} Dokumente gelöscht` : "Gelöscht"); };
    act.appendChild(d);
  });

  async function card(host){
    host.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>Rechnungen korrigieren</h3></div><div class="bd fr">
      <label class="chk"><input type="checkbox" id="ifrei" ${S.inv_frei ? "checked" : ""}> Rechnungen frei korrigieren und löschen – auch festgeschriebene (statt stornieren)</label>
      <div class="small muted">An: Im Editor gibt es <b>Bearbeiten</b> (hebt die Festschreibung auf) und <b>Löschen</b>; in der Liste lässt sich jede Rechnung löschen. Wird die zuletzt vergebene Nummer gelöscht, wird sie wieder frei. Jede Aufhebung und Löschung steht im GoBD-Protokoll. Hinweis: Für das Finanzamt sollen ausgestellte Rechnungen unverändert bleiben – verschickte Rechnungen im Zweifel besser stornieren.</div></div></div>`;
    $("#ifrei", host).onchange = async e => { await api("/api/settings/save", {inv_frei:e.target.checked}, {quiet:true}); S.inv_frei = e.target.checked; toast(e.target.checked ? "Rechnungen frei korrigierbar" : "Festgeschriebene Rechnungen geschützt"); };
  }
  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "docs") return;
    const page = $("#main .page"); if (!page || $("#freihost")) return;
    const h = document.createElement("div"); h.id = "freihost";
    const ph = $("#printhost"); ph ? page.insertBefore(h, ph) : page.appendChild(h); card(h);
  });
})();
