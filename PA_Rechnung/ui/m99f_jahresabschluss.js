// Pfeiffer-Audio Rechnung v3.4.0 - UI-Modul m99f_jahresabschluss v1.0.0: Seite "Jahresabschluss" (Finanzen)
// Schritt-fuer-Schritt-Pruefliste eines Steuerjahres, ELSTER-Werte zum Abtippen, Ausgabe (Jahresbericht, DATEV, Datenpaket).
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m99f = '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>';
  EXT.nav.push({key: "m99f", label: "Jahresabschluss", icon: "m99f", section: "Finanzen"});
  EXT.views.m99f = vJa;
  const F = {year: thisYear - 1};
  const STEPS = {1: "Rechnungen", 2: "Belege", 3: "Bank", 4: "Kasse", 5: "Anlagen & AfA", 6: "Fahrten & Gehalt", 7: "Umsatzsteuer", 8: "Ergebnis & Steuer"};
  const COL = {ok: "var(--green,#2e9e5b)", warn: "#d98a00", fehler: "var(--red,#c0392b)", info: "var(--muted,#6b7280)"};
  const SYM = {ok: "✓", warn: "!", fehler: "✗", info: "i"};

  async function vJa(){
    const m = $("#main");
    m.innerHTML = `<div class="page">${pageHead("Jahresabschluss " + F.year, "Schritt für Schritt durch das Steuerjahr – bis zu den Werten für ELSTER und dem Paket für den Steuerberater",
      `<select class="in" id="jay" style="width:110px">${[0, 1, 2, 3, 4].map(i => thisYear - i).map(y => `<option ${y === F.year ? "selected" : ""}>${y}</option>`).join("")}</select>`)}
      <div id="jabody"><div class="muted">Prüfe …</div></div></div>`;
    $("#jay").onchange = e => { F.year = +e.target.value; vJa(); };
    const r = await api("/api/jahresabschluss?year=" + F.year);
    if (!r || !r.ok) return;
    const done = new Set(r.erledigt || []);
    const groups = {};
    r.punkte.forEach(p => (groups[p.schritt] = groups[p.schritt] || []).push(p));
    const stepState = ps => ps.some(p => p.status === "fehler") ? "fehler" : ps.some(p => p.status === "warn") ? "warn" : "ok";
    const nSteps = Object.keys(groups).length;
    const nDone = Object.keys(groups).filter(s => done.has(+s) || stepState(groups[s]) === "ok").length;
    const pct = Math.round(100 * nDone / Math.max(1, nSteps));
    $("#jabody").innerHTML = `<div class="card" style="padding:14px 16px;margin-bottom:12px">
        <div class="row" style="gap:14px;align-items:center;flex-wrap:wrap"><b style="font-size:15px">${nDone} von ${nSteps} Schritten erledigt</b>
        <div style="flex:1;min-width:200px;height:10px;background:var(--line,#e5e7eb);border-radius:6px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${pct === 100 ? "var(--green,#2e9e5b)" : "var(--accent,#0A84FF)"}"></div></div>
        <span class="small">${r.fehler ? `<b style="color:${COL.fehler}">${r.fehler} Fehler</b> · ` : ""}${r.hinweise} Hinweise</span></div>
        <div class="small muted" style="margin-top:6px">Grüne Schritte sind automatisch erledigt. Bei Hinweisen: prüfen, beheben – oder bewusst abhaken („erledigt“), z. B. wenn ein Monat wirklich ohne Ausgaben war.</div></div>
      ${Object.keys(groups).sort((a, b) => a - b).map(s => {
        const ps = groups[s], st = stepState(ps), dn = done.has(+s);
        return `<div class="card" style="margin-bottom:10px"><div class="hd"><h3><span style="display:inline-block;width:22px;height:22px;border-radius:11px;text-align:center;line-height:22px;color:#fff;background:${dn && st !== "ok" ? COL.ok : COL[st]};font-size:12px;margin-right:8px">${dn && st !== "ok" ? "✓" : SYM[st]}</span>${s}. ${esc(STEPS[s] || "")}</h3>
          <div class="act">${st !== "ok" ? `<label class="chk" style="flex:none"><input type="checkbox" data-done="${s}" ${dn ? "checked" : ""}> erledigt</label>` : `<span class="small" style="color:${COL.ok}">erledigt</span>`}</div></div>
          <div class="bd"><table class="tbl"><tbody>${ps.map(p => `<tr><td style="width:26px"><b style="color:${COL[p.status]}">${SYM[p.status]}</b></td><td style="width:210px"><b>${esc(p.titel)}</b></td><td>${esc(p.text)}</td>
            <td style="width:110px">${p.seite && p.status !== "ok" ? `<button class="btn sm" data-go2="${esc(p.seite)}">Öffnen →</button>` : ""}</td></tr>`).join("")}</tbody></table></div></div>`;
      }).join("")}
      ${elsterCard(r.elster)}
      <div class="card" style="margin-bottom:10px"><div class="hd"><h3>10. Ausgabe</h3></div><div class="bd"><div class="row" style="gap:10px;flex-wrap:wrap">
        <button class="btn pri" id="jajb">${ic("pdf")} Jahresbericht ${F.year} (PDF)</button>
        <button class="btn" id="jadatev">DATEV-Export (Jahresabrechnung & Steuer)</button>
        <button class="btn" id="japaket">Datenpaket ${F.year} (ZIP)</button></div>
        <div class="small muted" style="margin-top:8px">Jahresbericht = alle Zahlen und die Ausfüllhilfe als PDF. DATEV-Export = Buchungsstapel für den Steuerberater. Datenpaket = Belege, Rechnungen und Daten des Jahres in einer ZIP-Datei.</div></div></div>`;
    $$("[data-go2]").forEach(b => b.onclick = () => go(b.dataset.go2));
    $$("[data-done]").forEach(c => c.onchange = async () => { await api("/api/jahresabschluss/erledigt", {year: F.year, schritt: +c.dataset.done, an: c.checked}); vJa(); });
    $("#jajb").onclick = async () => { const x = await api("/api/report/jahresbericht", {year: F.year}); if (x && x.ok !== false) toast("Jahresbericht erstellt" + (x.path ? ": " + x.path : "")); };
    $("#jadatev").onclick = () => go("tax");
    $("#japaket").onclick = async () => { const x = await api("/api/paket/export", {years: [F.year]}); if (x && x.ok !== false) toast("Datenpaket gespeichert: " + (x.path || "")); };
  }

  function elsterCard(e){
    if (!e || !e.euer) return "";
    const n = e.anlage_n || {};
    const nl = [...(n.lstb || []), ...(n.vorsorge || []), ...(n.werbungskosten || [])].filter(z => z && z.betrag);
    return `<div class="card" style="margin-bottom:10px"><div class="hd"><h3>9. Werte für ELSTER (zum Abtippen)</h3><div class="act"><button class="btn sm" id="jacopy">Als Text kopieren</button></div></div>
      <div class="bd"><div class="small muted" style="margin-bottom:8px">Anlage EÜR – ${esc(e.quelle || "")}. Direkt an ELSTER senden geht nur mit einer Zulassung als Software-Hersteller; deshalb hier Zeile, Kennzahl und Betrag zum Eintragen in „Mein ELSTER“.</div>
      <table class="tbl"><thead><tr><th style="width:70px">Zeile</th><th style="width:70px">Kz</th><th>Bezeichnung</th><th class="r" style="text-align:right;width:140px">Betrag</th></tr></thead><tbody>
      ${e.euer.map(z => `<tr><td>${esc(String(z.zeile))}</td><td><b>${esc(String(z.kz))}</b></td><td>${esc(z.label)}</td><td class="r" style="text-align:right"><b>${eur(z.betrag)}</b></td></tr>`).join("")}</tbody></table>
      ${nl.length ? `<div style="margin-top:10px"><b>Anlage N / Vorsorge / Werbungskosten</b> (aus den Gehaltsabrechnungen und Fahrten)</div><table class="tbl"><tbody>${nl.map(z => `<tr><td style="width:140px">${esc(z.nr ? "Nr. " + z.nr : "")}</td><td>${esc(z.label || "")}</td><td class="r" style="text-align:right;width:140px"><b>${eur(z.betrag)}</b></td></tr>`).join("")}</tbody></table>` : ""}
      ${e.hinweis ? `<div class="small muted" style="margin-top:8px">${esc(e.hinweis)}</div>` : ""}</div></div>`;
  }

  document.addEventListener("click", ev => {
    if (ev.target && ev.target.id === "jacopy") {
      const rows = [...document.querySelectorAll("#jabody .card:nth-last-child(2) tbody tr")].map(tr => [...tr.children].map(td => td.innerText.trim()).join("\t"));
      try { navigator.clipboard.writeText(rows.join("\n")); toast("Werte kopiert"); } catch (e) { toast("Kopieren nicht möglich", true); }
    }
  });
  console.log("INIT UI m99f_jahresabschluss v1.0.0");
})();
