// Pfeiffer-Audio Rechnung v3.2.0 - UI-Modul m99e_systempruefung v1.1.0: Seite "Systempruefung" (Bereich System)
// Prueft am eigenen PC: Programm, Selbsttest, Datenbank, Rechnungs-Kette, Texterkennung, Scanner, TimeTree, Mail,
// Bank, Sicherung - plus Rundgang durch alle Seiten der Oberflaeche (JS-Fehler, Serverfehler). PDF-Bericht.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m99e = '<path d="M9 12l2 2 4-4"/><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>';
  EXT.nav.push({key: "m99e", label: "Systemprüfung", icon: "m99e", section: "System"});
  EXT.views.m99e = vSp;
  let R = null, RG = null, running = false;
  const TEILE = [["programm", "Programm & Module"], ["selbsttest", "Selbsttest"], ["datenbank", "Datenbank"], ["kette", "Rechnungs-Kette"],
                 ["ocr", "Texterkennung"], ["scanner", "Scanner"], ["timetree", "TimeTree"], ["mail", "Mail"], ["bank", "Bank"], ["sicherung", "Sicherung"], ["tempo", "Tempo"]];
  const COL = {ok: "var(--green,#2e9e5b)", warn: "#d98a00", fehler: "var(--red,#c0392b)", info: "var(--muted,#6b7280)"};
  const LBL = {ok: "OK", warn: "Hinweis", fehler: "Fehler", info: "Info"};

  function vSp(){
    const m = $("#main");
    const slow = RG ? RG.filter(x => x.ms).sort((a, b) => b.ms - a.ms).slice(0, 6) : [];
    const rows = (R ? R.punkte : []).concat(RG ? [{gruppe: "Rundgang", name: "Alle Seiten der Oberfläche", status: RG.some(x => x.fehler) ? "fehler" : "ok",
      text: `${RG.length} Seiten` + (RG.some(x => x.fehler) ? " · " + RG.filter(x => x.fehler).map(x => x.seite + ": " + x.fehler).join(" | ") : "")}] : [])
      .concat(slow.length ? [{gruppe: "Tempo", name: "Langsamste Seiten", status: slow[0].ms > 3000 ? "warn" : "ok", text: slow.map(x => `${x.seite} ${x.ms} ms`).join(" · ")}] : []);
    m.innerHTML = `<div class="page">${pageHead("Systemprüfung", "Prüft an diesem PC alles, was vorab nicht getestet werden kann – und schreibt einen PDF-Bericht", "")}
      <div class="card" style="padding:16px;margin-bottom:14px">
        <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center">
          <button class="btn pri" id="spall" ${running ? "disabled" : ""}>${ic("m99e")} Alles prüfen</button>
          <button class="btn" id="sprg" ${running ? "disabled" : ""}>Nur Rundgang</button>
          <button class="btn" id="sppdf" ${R ? "" : "disabled"}>${ic("pdf")} Bericht als PDF</button>
          <span class="small muted" id="spst">${running ? "läuft …" : (R ? `Zuletzt: ${esc(dde ? dde(R.zeit.slice(0, 10)) : R.zeit)} · ${R.fehler} Fehler · ${R.warn} Hinweise` : "Noch nicht geprüft.")}</span>
        </div>
        <div class="small muted" style="margin-top:8px">Der Selbsttest arbeitet auf einer Wegwerf-Kopie – deine Daten werden nicht verändert. Der Rundgang öffnet nacheinander jede Seite (dauert ca. 1 Minute) und ändert nichts.</div>
      </div>
      ${rows.length ? `<div class="card"><table class="tbl"><thead><tr><th style="width:140px">Bereich</th><th style="width:200px">Prüfung</th><th style="width:90px">Ergebnis</th><th>Details</th></tr></thead><tbody>
        ${rows.map(r => `<tr><td>${esc(r.gruppe)}</td><td>${esc(r.name)}</td><td><b style="color:${COL[r.status]}">${LBL[r.status]}</b></td><td class="small" style="word-break:break-word">${esc(r.text)}</td></tr>`).join("")}
      </tbody></table></div>` : ""}</div>`;
    $("#spall").onclick = () => runAll(true);
    $("#sprg").onclick = () => runAll(false);
    $("#sppdf").onclick = async () => { const r = await api("/api/sp/pdf", {ergebnis: R, rundgang: RG}); if (r && r.ok) toast("Bericht gespeichert: " + r.path); };
  }

  async function rundgang(st){
    const navs = [...new Set([...document.querySelectorAll("#side [data-go]")].map(b => b.dataset.go))].filter(v => v !== "m99e");
    const out = [];
    const errs = [];
    const onErr = e => errs.push(String((e && (e.message || e.reason)) || e).slice(0, 160));
    const oFetch = window.fetch;
    let busy = 0;
    window.fetch = async (...a) => { busy++; try { const r = await oFetch(...a); if (r.status >= 500) errs.push(`Server ${r.status} ${String(a[0]).split("?")[0]}`); return r; } finally { busy--; } };
    window.addEventListener("error", onErr);
    window.addEventListener("unhandledrejection", onErr);
    const oToast = window.toast;
    try {
      for (let i = 0; i < navs.length; i++) {
        errs.length = 0;
        st(`Rundgang ${i + 1}/${navs.length}: ${navs[i]}`);
        const t0 = performance.now();
        try { await go(navs[i]); } catch (e) { onErr(e); }
        // page time: until no request is running any more (max. 15 s)
        await new Promise(r => setTimeout(r, 60));
        while (busy > 0 && performance.now() - t0 < 15000) await new Promise(r => setTimeout(r, 40));
        const ms = Math.round(performance.now() - t0);
        await new Promise(r => setTimeout(r, 500));
        document.querySelectorAll(".mb").forEach(x => x.remove());
        out.push({seite: navs[i], fehler: [...new Set(errs)].join("; "), ms});
      }
    } finally {
      window.fetch = oFetch;
      window.removeEventListener("error", onErr);
      window.removeEventListener("unhandledrejection", onErr);
      window.toast = oToast;
    }
    return out;
  }

  async function runAll(full){
    if (running) return;
    running = true;
    vSp();
    const st = t => { const e = $("#spst"); if (e) e.textContent = t; };
    try {
      if (full) {
        st("Prüfe Programm, Datenbank, Texterkennung, Scanner … (bis zu 1 Minute)");
        R = await api("/api/sp/run", {teile: TEILE.map(t => t[0])});
      }
      RG = await rundgang(st);
    } finally {
      running = false;
      await go("m99e");
    }
    const nf = (R ? R.fehler : 0) + (RG && RG.some(x => x.fehler) ? 1 : 0);
    toast(nf ? `${nf} Fehler gefunden – Details in der Liste` : "Alles in Ordnung ✓", !!nf);
  }

  window.m99eRun = runAll;
  console.log("INIT UI m99e_systempruefung v1.1.0");
})();
