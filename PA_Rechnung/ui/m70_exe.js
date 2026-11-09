// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m70_exe: EXE nach Update automatisch neu bauen und tauschen
// Einstellungs-Reiter "EXE", Kurzinfo unter Programm-Update, Hinweis nach dem Tausch.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m70exe = '<rect x="3" y="4" width="18" height="14" rx="2"/><path d="M3 8h18M8 21h8M12 18v3"/><path d="M9 13l2 2 4-4"/>';
  const ART = {onefile: "Einzeldatei (.exe)", onedir: "Ordner-Variante (Schnellstart)", kein: "keine EXE (direkt aus Python gestartet)"};
  let pollT = null;

  const statusHtml = d => {
    const r = d.run, b = d.bereit;
    if (r.state === "laeuft") return `<div class="small"><b>Neue EXE v${esc(r.ver)} wird gebaut</b> (${esc(ART[r.art] || r.art)}) – läuft unsichtbar im Hintergrund, du kannst normal weiterarbeiten.</div>
      <div class="row" style="align-items:center;margin:6px 0"><div class="prog" style="flex:3"><div style="width:${r.pct}%"></div></div><b class="num" style="flex:none">${r.pct} %</b></div>
      <div class="small muted" style="word-break:break-all">${esc(r.msg)}</div>`;
    if (b) return `<div class="alert" style="cursor:default">${ic("m70exe")}<span><b>Neue EXE v${esc(b.ver)} ist fertig gebaut</b> (${esc(ART[b.art] || b.art)}, ${nde((b.groesse || 0) / 1048576, 0)} MB, ${esc(dde((b.fertig || "").slice(0, 10)))}).
      ${!d.info.frozen ? `Das Programm läuft ohne EXE – die neue EXE liegt unter <span style="word-break:break-all">${esc(b.exe || "")}</span>.`
        : d.settings.auto_tausch ? "Sie ersetzt die alte EXE automatisch, sobald du das Programm schließt." : "Zum Einsetzen „Jetzt tauschen und neu starten“ klicken."}</span></div>`;
    if (r.state === "fehler") return `<div class="alert warn" style="cursor:default">${ic("alert")}<span>${esc(r.msg)}</span></div>`;
    if (r.state === "abgebrochen") return `<div class="small muted">Bau abgebrochen.</div>`;
    if (r.state === "laeuft_extern") return `<div class="small muted">${esc(r.msg)}</div>`;
    if (d.info.veraltet) return `<div class="small">Die EXE enthält noch v${esc(d.info.builtin)}, das Programm läuft als v${esc(d.info.version)} aus einem Update. Eine neue EXE kann gebaut werden.</div>`;
    return `<div class="small muted">${d.info.frozen ? "Die EXE ist auf dem Stand des Programms." : "Das Programm läuft direkt aus Python – es gibt keine EXE zu tauschen."}</div>`;
  };

  async function render(el){
    clearTimeout(pollT);
    const d = await api("/api/m70/info", undefined, {quiet: true});
    if (!d || !d.ok) { el.innerHTML = `<div class="empty">EXE-Daten nicht verfügbar.</div>`; return; }
    const s = d.settings, i = d.info, r = d.run, b = d.bereit;
    const py = d.py;
    el.innerHTML = `<div class="grid g2" style="align-items:start;margin-top:4px">
      <div class="card"><div class="hd"><h3>Aktuelle EXE</h3></div><div class="bd">
        <div class="kv small">
          <span class="sub">EXE-Datei</span><span class="r" style="word-break:break-all">${i.exe ? esc(i.exe) : "–"}</span>
          <span class="sub">Art</span><span class="r">${esc(ART[i.art] || i.art)}</span>
          <span class="sub">In der EXE eingebaut</span><span class="r">${i.builtin ? "v" + esc(i.builtin) : "–"}</span>
          <span class="sub">Laufende Programmversion</span><span class="r">v${esc(i.version)} ${i.source === "update" ? "(aus Update)" : ""}</span>
          <span class="sub">Status</span><span class="r">${i.veraltet ? `<span class="badge warn"><span class="dot"></span>EXE älter als Programm</span>` : i.frozen ? `<span class="badge ok">aktuell</span>` : `<span class="badge">ohne EXE</span>`}</span></div>
      </div></div>
      <div class="card"><div class="hd"><h3>Neue EXE bauen</h3></div><div class="bd fr" id="m70st">${statusHtml(d)}
        <div class="row" style="flex-wrap:wrap;margin-top:8px">
          ${r.state === "laeuft" ? `<button class="btn" style="flex:none" id="m70ab">Bau abbrechen</button>` : `<button class="btn ${b ? "" : "pri"}" style="flex:none" id="m70bau" ${d.is_win ? "" : "disabled title='nur unter Windows'"}>${ic("m70exe")} Neue EXE jetzt bauen</button>`}
          ${b && i.frozen ? `<button class="btn pri" style="flex:none" id="m70tau">Jetzt tauschen und neu starten</button><button class="btn ghost" style="flex:none" id="m70ver">Verwerfen</button>` : ""}
          <button class="btn ghost" style="flex:none" id="m70log">Log ansehen</button></div>
        <div class="small muted">Gebaut wird mit Python + PyInstaller auf diesem PC (wie build_exe.bat), unsichtbar und mit niedriger Priorität. Dauer meist 3–10 Minuten, beim ersten Mal länger (Pakete werden geladen).</div></div></div>
      <div class="card"><div class="hd"><h3>Einstellungen</h3></div><div class="bd fr">
        <label class="chk"><input type="checkbox" id="m70ab1" ${s.auto_bau ? "checked" : ""}> Nach jedem Update automatisch die neue EXE bauen</label>
        <label class="chk"><input type="checkbox" id="m70at1" ${s.auto_tausch ? "checked" : ""}> Neue EXE beim Beenden automatisch einsetzen (alte EXE wird ersetzt, Verknüpfungen umgebogen)</label>
        <label class="chk"><input type="checkbox" id="m70oc1" ${s.ocr ? "checked" : ""}> Texterkennung (Windows-OCR) mit einbauen</label>
        <label class="f">Bau-Variante<select class="in" id="m70va">
          <option value="auto" ${s.variante === "auto" ? "selected" : ""}>wie bisher (${esc(ART[d.variante] || d.variante)})</option>
          <option value="onefile" ${s.variante === "onefile" ? "selected" : ""}>Einzeldatei (.exe)</option>
          <option value="onedir" ${s.variante === "onedir" ? "selected" : ""}>Ordner-Variante (startet schneller)</option></select></label>
        <label class="f">Python (leer = automatisch suchen)<input class="in" id="m70py" value="${esc(s.python || "")}" placeholder="z. B. C:\\Users\\…\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"></label>
        <div class="row" style="flex-wrap:wrap;align-items:center"><button class="btn sm" style="flex:none" id="m70pyb" type="button">Durchsuchen …</button>
          <button class="btn sm" style="flex:none" id="m70pyt" type="button">Python suchen / testen</button>
          <span class="small" id="m70pyr">${py && py.ok ? `<span style="color:var(--ok)">✓ Python ${esc(py.version)} (${esc(py.bits)} Bit): ${esc(py.cmd.join(" "))}</span>` : ""}</span></div>
        <div class="row"><button class="btn pri" style="flex:none" id="m70sv">${ic("save")} Speichern</button></div></div></div>
      <div class="card"><div class="hd"><h3>Letzte Bauten</h3></div><div class="bd" style="padding:0">
        <table class="t"><thead><tr><th>Datum</th><th>Version</th><th>Art</th><th class="r">Dauer</th><th>Ergebnis</th><th></th></tr></thead><tbody>
        ${(d.bauten || []).map(x => `<tr><td class="small">${esc(dde((x.datum || "").slice(0, 10)))} ${esc((x.datum || "").slice(11, 16))}</td><td>v${esc(x.ver)}</td><td class="small">${esc(x.art === "onedir" ? "Ordner" : x.art === "onefile" ? "Einzeldatei" : "")}</td>
          <td class="r num small">${x.dauer_s ? Math.round(x.dauer_s / 60) + " min" : ""}</td><td class="small">${x.ok ? `<span class="badge ok">fertig</span>` : `<span class="badge bad">${esc((x.msg || "Fehler").slice(0, 90))}</span>`}<div class="muted">${esc(x.grund || "")}</div></td>
          <td class="r">${x.log ? `<button class="btn sm ghost" data-m70log="${esc(x.log)}">Log</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Noch keine EXE gebaut.</td></tr>`}</tbody></table>
        <div class="small muted" style="padding:8px 12px"><button class="btn sm ghost" id="m70tlog" type="button">Tausch-Protokoll ansehen</button> Alte EXE liegt nach dem Tausch unter <b>${esc(d.app_dir)}\\exe_alt</b> (nur die letzte).</div></div></div></div>`;
    const on = (id, fn) => { const e = $("#" + id, el); if (e) e.onclick = fn; };
    on("m70bau", async () => { const x = await api("/api/m70/bauen", {}); if (x && x.ok) toast("EXE-Bau gestartet"); render(el); });
    on("m70ab", async () => { await api("/api/m70/abbrechen", {}); toast("Bau abgebrochen"); setTimeout(() => render(el), 800); });
    on("m70ver", async () => { await api("/api/m70/verwerfen", {}); toast("Gebaute EXE verworfen"); render(el); });
    on("m70tau", async () => { const x = await api("/api/m70/tauschen", {}); if (x && x.ok) restartScreen("Neue EXE wird eingesetzt …"); });
    on("m70log", () => showLog(""));
    on("m70tlog", () => showLog("", true));
    $$("[data-m70log]", el).forEach(bn => bn.onclick = () => showLog(bn.dataset.m70log));
    on("m70pyb", async () => { const x = await api("/api/pick", {accept: ".exe", multiple: false}, {quiet: true});
      if (x && x.ok && x.paths && x.paths[0]) $("#m70py", el).value = x.paths[0]; });
    on("m70pyt", async () => { const o = $("#m70pyr", el); o.textContent = "suche …";
      const x = await api("/api/m70/python", {python: $("#m70py", el).value}, {quiet: true});
      o.innerHTML = x && x.ok ? `<span style="color:var(--ok)">✓ Python ${esc(x.version)} (${esc(x.bits)} Bit): ${esc(x.cmd.join(" "))}</span>`
        : `<span style="color:var(--bad)">${esc((x && x.error) || "nicht gefunden")}</span>${x && x.tried && x.tried.length ? `<div class="muted">Versucht: ${x.tried.map(t => esc(t.cmd + " → " + t.info)).join(" · ")}</div>` : ""}`; });
    on("m70sv", async () => { const x = await api("/api/m70/settings", {auto_bau: $("#m70ab1", el).checked, auto_tausch: $("#m70at1", el).checked,
      ocr: $("#m70oc1", el).checked, variante: $("#m70va", el).value, python: $("#m70py", el).value});
      if (x && x.ok) toast("EXE-Einstellungen gespeichert"); render(el); });
    if (r.state === "laeuft") pollT = setTimeout(() => { if (el.isConnected) render(el); }, 2500);
  }

  async function showLog(path, tausch){
    const x = await api("/api/m70/log?" + (tausch ? "tausch=1" : "log=" + encodeURIComponent(path || "")), undefined, {quiet: true});
    const lines = (x && x.lines) || [];
    await modal(tausch ? "Tausch-Protokoll" : "EXE-Bau – Log", `<div class="small muted" style="margin-bottom:6px;word-break:break-all">${esc((x && x.path) || "")}</div>
      <pre style="max-height:60vh;overflow:auto;font:11.5px/1.45 Consolas,monospace;white-space:pre-wrap;margin:0">${esc(lines.join("\n")) || "(leer)"}</pre>`, [{label: "Schließen"}], true);
  }

  EXT.settings.push({key: "m70exe", label: "EXE", render});

  // short info below "Programm-Update" in the tab "Daten, Backup & Update"
  EXT.after.push(async n => {
    if (n !== "vSettings" || typeof setTab === "undefined" || setTab !== "daten") return;
    const ub = $("#updbox"); if (!ub || $("#m70mini")) return;
    const card = document.createElement("div"); card.className = "card"; card.id = "m70mini";
    card.innerHTML = `<div class="hd"><h3>EXE</h3><div class="act"><button class="btn sm" type="button" id="m70go">EXE-Einstellungen</button></div></div><div class="bd small muted">lädt …</div>`;
    ub.closest(".card").after(card);
    $("#m70go", card).onclick = () => { setTab = "m70exe"; vSettings(); };
    const d = await api("/api/m70/info", undefined, {quiet: true});
    if (d && d.ok) $(".bd", card).innerHTML = statusHtml(d);
  });

  // after start: report the result of an EXE swap once, mention a finished build
  let tries = 0;
  const once = () => {
    if (typeof S === "undefined" || !S || !S.m70) { if (++tries < 60) setTimeout(once, 1000); return; }
    const m = S.m70, e = m.ergebnis;
    if (e) {
      api("/api/m70/gesehen", {}, {quiet: true});
      if (e.ok) toast(`Neue EXE eingesetzt${e.verknuepfungen ? ` – ${e.verknuepfungen} Verknüpfung(en) umgebogen` : ""}.`);
      else modal("EXE nicht getauscht", `<div style="white-space:pre-line">${esc(e.text || "")}</div><div class="small muted" style="margin-top:8px">Einstellungen → EXE → „Tausch-Protokoll ansehen“.</div>`);
    } else if (m.bereit) toast(`Neue EXE v${m.bereit} ist fertig – ${m.auto_tausch ? "wird beim Schließen eingesetzt" : "einsetzen unter Einstellungen → EXE"}.`);
  };
  setTimeout(once, 1500);
})();
