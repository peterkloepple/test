// Pfeiffer-Audio Rechnung v2.6.7 - UI-Modul m24_scanner v1.1.1 (Knopf Texterkennung testen): Scannen in Rechnungen/Angebote und in Belege
// Editor: Knopf "Scannen" bei den Anlagen - alle Seiten als eine PDF an das Dokument haengen.
// Belege & Import (v1.1.0): Knopf "Scannen" - Scan geht durch die Belegerkennung wie eine hineingezogene Datei,
// wahlweise alle Seiten = ein Beleg oder jede Seite = ein eigener Beleg.
// Windows-Scanfenster, mehrere Seiten, Seiten entfernen.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  let busy = false;
  const MODI = `<option value="farbe">Farbe</option><option value="grau">Graustufen</option><option value="sw">Schwarz-Weiß (Text)</option>`;

  // mode "anlage" (editor) or "beleg" (Belege & Import)
  function openScan(mode){
    mode = mode === "beleg" ? "beleg" : "anlage";
    if (mode === "anlage" && (!cur || cur.locked)) { toast("Das Dokument ist festgeschrieben.", true); return; }
    if ($("#m24dlg")) return;
    let sid = "", pages = [], scanning = false;
    const mb = document.createElement("div"); mb.className = "mb"; mb.id = "m24dlg";
    let title, defName, hint, okLabel;
    if (mode === "anlage") {
      const typ = cur.typ === "angebot" ? "Angebot" : (cur.typ === "rechnung" ? "Rechnung" : "Dokument");
      title = `Scannen – Anlage zu ${typ}${cur.nr ? " " + cur.nr : ""}`;
      defName = "Scan_" + (cur.nr ? String(cur.nr).replace(/[\\/:*?"<>|]+/g, "_") + "_" : "") + todayIso();
      hint = "Alle Seiten werden zusammen als eine PDF angehängt.";
      okLabel = "Als PDF anhängen";
    } else {
      title = "Beleg scannen";
      defName = "Beleg_Scan_" + todayIso();
      hint = "Danach liest das Programm den Scan aus (Texterkennung) und zeigt ihn zur Prüfung an – wie eine hineingezogene Datei.";
      okLabel = "Auslesen & prüfen";
    }
    mb.innerHTML = `<div class="md wide"><div class="mh"><h3>${esc(title)}</h3></div>
      <div class="mc">
        <div class="row" style="gap:10px;align-items:end;flex-wrap:wrap">
          <label style="flex:1;min-width:220px"><span class="small muted">Name der PDF</span><input class="in" id="m24name" value="${esc(defName)}"></label>
          <label><span class="small muted">Art</span><select class="in" id="m24modus">${MODI}</select></label>
          <button class="btn pri" id="m24scan" type="button">Seite scannen</button>
        </div>
        ${mode === "beleg" ? `<div class="row" style="gap:14px;margin-top:10px;flex-wrap:wrap" id="m24grp">
          <label class="chk" style="flex:none"><input type="radio" name="m24g" value="ein" checked> <span>Alle Seiten = <b>ein</b> Beleg (mehrseitige Rechnung)</span></label>
          <label class="chk" style="flex:none"><input type="radio" name="m24g" value="einzeln"> <span>Jede Seite = <b>eigener</b> Beleg (Stapel Kassenzettel)</span></label></div>` : ""}
        <div class="small muted" style="margin:8px 0">Es öffnet sich das Windows-Scanfenster. Dort Scanner, Einzug oder Glas und Auflösung wählen und „Scannen“ klicken. Danach kannst du weitere Seiten scannen. ${esc(hint)}</div>
        <div id="m24st" class="small" style="min-height:18px"></div>
        <div id="m24pages" style="display:flex;flex-wrap:wrap;gap:10px;margin-top:8px"></div>
      </div>
      <div class="mf"><button class="btn" id="m24cancel" type="button">Abbrechen</button><button class="btn pri" id="m24ok" type="button" disabled>${esc(okLabel)}</button></div></div>`;
    document.body.appendChild(mb);
    const st = (t, err) => { const e = $("#m24st", mb); e.textContent = t || ""; e.style.color = err ? "var(--red,#c0392b)" : ""; };
    const draw = () => {
      $("#m24pages", mb).innerHTML = pages.length ? pages.map((p, i) => `<div style="position:relative;border:1px solid var(--line);border-radius:8px;padding:4px;background:#fff">
          <img src="/api/scan/thumb?session=${sid}&seite=${p}&t=${Date.now()}" style="display:block;width:150px;height:200px;object-fit:contain">
          <div class="row" style="justify-content:space-between;align-items:center;margin-top:4px"><span class="small">Seite ${i + 1}</span>
          <button class="btn sm ghost danger" data-m24rm="${p}" type="button" title="Seite entfernen">${ic("trash")}</button></div></div>`).join("")
        : `<div class="muted small">Noch keine Seite gescannt.</div>`;
      $("#m24ok", mb).disabled = !pages.length || scanning;
      $("#m24scan", mb).disabled = scanning;
      $("#m24scan", mb).textContent = pages.length ? "Weitere Seite scannen" : "Seite scannen";
      $$("[data-m24rm]", mb).forEach(b => b.onclick = async () => {
        const r = await api("/api/scan/remove", {session: sid, seite: b.dataset.m24rm});
        if (r && r.ok) { pages = r.seiten || []; draw(); }
      });
    };
    const close = async (discard) => {
      if (discard && sid) { try { await api("/api/scan/discard", {session: sid}); } catch (e) {} }
      mb.remove();
    };
    $("#m24scan", mb).onclick = async () => {
      if (scanning) return;
      scanning = true; draw(); st("Scanfenster ist offen … (es kann hinter diesem Fenster liegen)");
      let r;
      try { r = await api("/api/scan/page", {session: sid, modus: $("#m24modus", mb).value}); } catch (e) { r = {ok: false, error: String(e)}; }
      scanning = false;
      if (r && r.ok) {
        sid = r.session || sid; pages = r.seiten || [];
        st(r.abbruch ? "Scannen abgebrochen." : `Seite ${pages.length} gescannt.`);
      } else st((r && r.error) || "Scannen fehlgeschlagen.", true);
      draw();
    };
    $("#m24cancel", mb).onclick = async () => {
      if (pages.length && !await confirmBox(`${pages.length} gescannte Seite(n) verwerfen?`)) return;
      close(true);
    };
    $("#m24ok", mb).onclick = async () => {
      if (busy || !pages.length) return;
      busy = true; $("#m24ok", mb).disabled = true;
      let r;
      if (mode === "anlage") {
        st("PDF wird erstellt …");
        try { r = await api("/api/scan/attach", {session: sid, invoice_id: cur.id || 0, name: $("#m24name", mb).value}); } catch (e) { r = {ok: false, error: String(e)}; }
        busy = false;
        if (!r || !r.ok) { st((r && r.error) || "Anhängen fehlgeschlagen.", true); draw(); return; }
        cur.attachments = cur.attachments || [];
        cur.attachments.push({id: r.id, file: r.file, partner: r.partner, pending: !cur.id});
        close(false);
        renderAtts(); schedulePreview();
        toast(`Scan angehängt (${r.seiten} Seite${r.seiten === 1 ? "" : "n"}).`);
        return;
      }
      st("Beleg wird ausgelesen (Texterkennung) …");
      const g = $("input[name=m24g]:checked", mb);
      try { r = await api("/api/scan/beleg", {session: sid, name: $("#m24name", mb).value, einzeln: !!(g && g.value === "einzeln")}); } catch (e) { r = {ok: false, error: String(e)}; }
      busy = false;
      if (!r || !r.ok) { st((r && r.error) || "Auslesen fehlgeschlagen.", true); draw(); return; }
      close(false);
      const items = (r.items || []).filter(it => { if (it && it.error) { toast(it.error, true); return false; } return !!it; });
      if (!items.length) { toast("Im Scan wurde kein Beleg erkannt.", true); return; }
      queue.push(...items); renderQueue();
      toast(items.length === 1 ? "Scan ausgelesen – bitte unten prüfen und übernehmen." : `${items.length} Belege aus dem Scan – bitte unten prüfen und übernehmen.`);
      const qd = $("#queue"); if (qd) qd.scrollIntoView({behavior: "smooth", block: "start"});
    };
    draw();
  }

  function injectEditor(){
    const pick = $("#attpick");
    if (!pick || $("#m24btn")) return;
    const b = document.createElement("button");
    b.className = "btn sm"; b.id = "m24btn"; b.type = "button";
    b.innerHTML = `${ic("pdf")} Scannen`;
    b.title = S && S.scanner === false ? "Scannen geht nur unter Windows" : "Direkt vom Scanner als PDF anhängen";
    b.onclick = () => openScan("anlage");
    if (cur && cur.locked) b.disabled = true;
    pick.insertAdjacentElement("afterend", b);
    pick.insertAdjacentText("afterend", " ");
  }

  function injectBelege(){
    const pick = $("#bpick");
    if (!pick || $("#m24bbtn")) return;
    const b = document.createElement("button");
    b.className = "btn"; b.id = "m24bbtn"; b.type = "button";
    b.innerHTML = `${ic("pdf")} Scannen`;
    b.title = S && S.scanner === false ? "Scannen geht nur unter Windows" : "Beleg direkt vom Scanner einlesen";
    b.onclick = e => { e.stopPropagation(); openScan("beleg"); };
    pick.insertAdjacentElement("afterend", b);
    pick.insertAdjacentText("afterend", " ");
    const t = document.createElement("button");
    t.className = "btn ghost"; t.id = "m24ocrt"; t.type = "button";
    t.textContent = "Texterkennung testen";
    t.onclick = e => { e.stopPropagation(); ocrTest(); };
    b.insertAdjacentElement("afterend", t);
    b.insertAdjacentText("afterend", " ");
  }

  // v2.6.7: shows whether the Windows text recognition works and which way (Python winrt / PowerShell)
  async function ocrTest(){
    toast("Texterkennung wird getestet …");
    let r;
    try { r = await api("/api/ocr/test", {}); } catch (e) { r = {ok: false, fehler: String(e)}; }
    r = r || {};
    const row = (k, v) => `<tr><td class="muted small" style="width:170px">${esc(k)}</td><td class="small">${v}</td></tr>`;
    const html = `<div style="font-size:15px;margin-bottom:10px"><b style="color:${r.ok ? "var(--green,#2e9e5b)" : "var(--red,#c0392b)"}">${r.ok ? "✓ Texterkennung funktioniert" : "✗ Texterkennung funktioniert nicht"}</b></div>
      <table class="tbl">${row("Weg", esc(r.weg || "–"))}${row("Python-Paket winrt", r.winrt ? "vorhanden" : "nicht vorhanden" + (r.winrt_fehler ? " (" + esc(r.winrt_fehler) + ")" : "") + " – es wird PowerShell benutzt")}
      ${r.text ? row("Gelesen", "<pre style='white-space:pre-wrap;margin:0'>" + esc(r.text) + "</pre>") : ""}${r.fehler ? row("Grund", esc(r.fehler)) : ""}</table>
      ${r.ok ? "" : `<div class="small muted" style="margin-top:10px">Häufigste Ursache: In Windows fehlt das Texterkennungs-Paket für Deutsch. <b>Einstellungen → Zeit und Sprache → Sprache und Region → Deutsch → … → Sprachoptionen → Optische Zeichenerkennung (OCR) / „Grundlegende Eingabe“ hinzufügen</b>, danach das Programm neu starten.</div>`}`;
    await modal("Texterkennung testen", html, [{label: "Schließen", cls: "pri"}], true);
  }

  window.m24Scan = openScan;
  window.m24OcrTest = ocrTest;
  EXT.after.push(n => { if (n === "vEditor") injectEditor(); if (n === "vBelege") injectBelege(); });
  console.log("INIT UI m24_scanner v1.1.1");
})();
