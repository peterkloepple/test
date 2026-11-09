// Pfeiffer-Audio Rechnung v3.1.0 - UI-Modul m44_steuerjahr: Steuerbescheid, Jahr bearbeiten, Angleichen (zusammengefasst)
// Autor: T. Pfeiffer


// ============================================================================
// Teil aus m44_bescheid.js
// ============================================================================
// Pfeiffer-Audio Rechnung v2.6.1 - UI-Modul m44_bescheid: Steuerbescheid einfuegen + Werte auslesen
// Knopf "Steuerbescheid einfuegen" in der Steuerakte (Jahresabrechnung & Steuer und Seite "Jahr bearbeiten"),
// "Werte auslesen" an vorhandenen Bescheiden, Vorschau mit Vergleich bisher / Programm, Uebernahme in den Jahresabschluss.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const val = v => v == null || v === "" ? "" : nde(v);

  async function preview(r, after){
    if (!r || r.ok === false) return;
    const keys = r.keys || [], L = r.labels || {}, w = r.werte || {}, b = r.bisher || {}, p = r.programm || {};
    const PK = {est_festgesetzt:"est_festgesetzt", soli_festgesetzt:"soli_festgesetzt", zve:"zve", bruttolohn:"bruttolohn", lst_abzug:"lst_abzug", wk:"wk"};
    const rows = keys.map(k => {
      const has = w[k] != null, old = b[k];
      const diffOld = has && old != null && old !== "" && Math.abs(old - w[k]) >= 0.01;
      return `<tr><td><label class="chk" style="margin:0"><input type="checkbox" data-m44c="${k}" ${has ? "checked" : ""}> ${esc(L[k] || k)}</label></td>
        <td class="r"><input class="in num" data-m44v="${k}" value="${has ? nde(w[k]) : ""}" style="width:120px;${has ? "" : "opacity:.7"}" placeholder="nicht erkannt"></td>
        <td class="r num small ${diffOld ? "" : "muted"}" ${diffOld ? 'style="color:var(--warn)"' : ""}>${val(old) || "–"}</td>
        <td class="r num small muted">${PK[k] && p[PK[k]] != null ? nde(p[PK[k]]) : "–"}</td></tr>`;
    }).join("");
    const vz = r.vz_folge;
    const html = `<div class="fr">
      ${r.year !== r.year_hint ? `<div class="hl small" style="margin-bottom:8px">Der Bescheid gehört zum Jahr <b>${r.year}</b> und wurde dort in der Steuerakte abgelegt.</div>` : ""}
      ${r.aenderung ? `<div class="hl small" style="margin-bottom:8px">Das ist ein <b>Änderungsbescheid</b> – die neuen Werte ersetzen die bisherigen, der alte Stand bleibt im Verlauf.</div>` : ""}
      ${(r.hinweise || []).map(h => `<div class="alert warn" style="cursor:default;margin-bottom:6px;font-size:12.5px">${ic("alert")}<span>${esc(h)}</span></div>`).join("")}
      <div class="small muted" style="margin-bottom:6px">${(r.gefunden || []).length} von ${keys.length} Werten erkannt${r.ocr ? " (per Texterkennung aus dem Scan – bitte besonders genau prüfen)" : ""}. Werte kannst du vor dem Übernehmen ändern; nur angehakte Zeilen werden übernommen.</div>
      <table class="t nosort"><thead><tr><th>Wert</th><th class="r">lt. Bescheid</th><th class="r">bisher gespeichert</th><th class="r">Programm</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="small muted" style="margin:4px 0 10px">Erstattung positiv, Nachzahlung negativ eingeben.</div>
      <div class="row" style="align-items:flex-end;flex-wrap:wrap">
        <label class="f" style="flex:none">Bescheid vom<input type="date" class="in" id="m44d" value="${esc(r.datum || r.bisher_datum || "")}"></label>
        <label class="chk" style="flex:none;margin-bottom:9px"><input type="checkbox" id="m44a" ${r.abgeschlossen ? "checked" : ""}> Jahr ${r.year} abgeschlossen</label></div>
      ${vz ? `<label class="chk" style="margin-top:8px"><input type="checkbox" id="m44vz" checked> ESt-Vorauszahlungen <b>${vz.year}</b> auf <input class="in num" id="m44vzb" value="${nde(vz.betrag)}" style="width:110px;display:inline-block"> € im Jahr setzen
        <span class="small muted">(bisher ${eur(r.vz_aktuell || 0)})</span></label>` : ""}
      </div>`;
    const ok = await modal(`Steuerbescheid ${r.year} – erkannte Werte`, html, [
      {label:"Nur ablegen"},
      {label:"In den Jahresabschluss übernehmen", cls:"pri", value:1, onClick: async mb => {
        const werte = {};
        $$("[data-m44c]", mb).forEach(c => { if (c.checked) { const v = $(`[data-m44v="${c.dataset.m44c}"]`, mb).value.trim(); werte[c.dataset.m44c] = v === "" ? null : pnum(v); } });
        const body = {year:r.year, id:r.id, werte, bescheid_datum:$("#m44d", mb).value, abgeschlossen:$("#m44a", mb).checked, aenderung:!!r.aenderung};
        if ($("#m44vz", mb) && $("#m44vz", mb).checked) body.vz_folge = {year:vz.year, betrag:pnum($("#m44vzb", mb).value)};
        const x_ = await api("/api/m44/apply", body);
        if (!x_ || !x_.ok) return false;
        toast(x_.info || "Übernommen");
      }}], true);
    // v2.6.1: after taking over the values, go straight to the reconciliation when anything differs (m46)
    if (ok && window.m46Open) { await m46Open(r.year, after ? () => after(r.year, true) : null, true); return; }
    if (after) after(r.year, !!ok);
  }

  // public: pick a file, upload, preview
  window.m44Insert = function(year, after){
    pickFiles(".pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt,.xml,.html,.htm", async fs => {
      if (!fs.length) return;
      toast("Steuerbescheid wird gelesen …");
      for (const f of fs) {
        const r = await upload("/api/upload/m44bescheid", f, {"X-Year": String(year)});
        if (!r || r.error) { toast((r && r.error) || "Fehler beim Lesen", true); continue; }
        await preview(r, after);
      }
    }, false);
  };
  window.m44Reparse = async function(id, after){
    const r = await api("/api/m44/reparse", {id:+id});
    await preview(r, after);
  };

  // hook into the tax file (Steuerakte) - used on "Jahresabrechnung & Steuer" and "Jahr bearbeiten"
  if (typeof loadAkte === "function" && !window.m44Wrapped) {
    window.m44Wrapped = true;
    const orig = loadAkte;
    window.loadAkte = async function(...a){
      const res = await orig.apply(this, a);
      try {
        const el = $("#akte"); if (!el) return res;
        const act = $(".hd .act", el);
        if (act && !$("#m44btn", act)) {
          const b = document.createElement("button"); b.className = "btn sm pri"; b.id = "m44btn"; b.type = "button";
          b.innerHTML = `${ic("up")} Steuerbescheid einfügen`; b.title = "Bescheid (PDF/Scan) ablegen und Werte automatisch auslesen";
          act.insertBefore(b, act.firstChild);
          b.onclick = () => m44Insert(txYear, () => loadAkte());
          const sv = $("#aksave", act); if (sv) sv.classList.remove("pri");
        }
        // "Werte auslesen" next to every notice already in the file
        $$("[data-akopen]", el).forEach(o => {
          const row = o.closest(".row"); if (!row || $("[data-m44r]", row)) return;
          const grp = row.previousElementSibling;
          let g = row; while (g && !(g.classList.contains("small") && g.classList.contains("muted"))) g = g.previousElementSibling;
          const art = g ? g.textContent.trim() : "";
          if (!/bescheid/i.test(art)) return;
          const del = $("[data-akdel]", row); if (!del) return;
          const rb = document.createElement("button"); rb.className = "btn sm ghost"; rb.style.flex = "none"; rb.type = "button";
          rb.dataset.m44r = del.dataset.akdel; rb.textContent = "Werte auslesen"; rb.title = "Werte aus diesem Bescheid erkennen und übernehmen";
          row.insertBefore(rb, o);
          rb.onclick = () => m44Reparse(del.dataset.akdel, () => loadAkte());
        });
        // history of applied notices
        const ab = (await api("/api/steuerakte?year=" + txYear, undefined, {quiet:true}) || {}).abschluss || {};
        const h = ab.bescheide || [];
        if (h.length > 1 && !$("#m44hist", el)) {
          const d = document.createElement("div"); d.id = "m44hist"; d.className = "small muted"; d.style.cssText = "margin:10px 16px 14px";
          d.innerHTML = `<b>Bescheid-Verlauf ${txYear}</b><br>` + h.slice().reverse().map(x => `${x.datum ? dde(x.datum) : "ohne Datum"}${x.aenderung ? " (Änderung)" : ""}: ` +
            `ESt ${eur(x.werte.est_festgesetzt || 0)}${x.werte.erstattung != null ? ` · ${x.werte.erstattung >= 0 ? "Erstattung" : "Nachzahlung"} ${eur(Math.abs(x.werte.erstattung))}` : ""}`).join("<br>");
          const card = $(".card", el); if (card) card.appendChild(d);
        }
      } catch (e) { console.error(e); }
      return res;
    };
  }
})();


// ============================================================================
// Teil aus m45_jahr.js
// ============================================================================
// Pfeiffer-Audio Rechnung v2.6.0 - UI-Modul m45_jahr: Seite "Jahr bearbeiten" (Finanzen)
// Alles eines Jahres an einer Stelle: Ueberblick + Pruefung, Rechnungen (Zahlstatus/Zahldatum), Ausgaben,
// sonstige Einnahmen, Gehalt (direkt in der Tabelle bearbeiten, neu, loeschen), Steuer-Angaben,
// Steuerbescheid & Jahresabschluss (Steuerakte inkl. "Steuerbescheid einfuegen").
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m45 = '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/><path d="M8 14l2.5 2.5L16 12"/>';
  const LS = "pa_m45";
  const F = {year: thisYear - 1, tab: "ueb", q: ""};
  try { Object.assign(F, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) {}
  const keep = () => { try { localStorage.setItem(LS, JSON.stringify({year: F.year, tab: F.tab})); } catch (e) {} };
  let D = null;
  const DB = {}, DR = {};          // dirty belege / rechnungen: id -> changed fields
  const nDirty = () => Object.keys(DB).length + Object.keys(DR).length;
  const TABS = [["ueb", "Überblick"], ["re", "Rechnungen"], ["aus", "Ausgaben"], ["ein", "Sonstige Einnahmen"], ["geh", "Gehalt"], ["st", "Steuer-Angaben"], ["abs", "Bescheid & Abschluss"]];
  const TYP_OF = {aus: "ausgabe", ein: "einnahme", geh: "gehalt"};
  const TYPL = {ausgabe: "Ausgabe", einnahme: "Sonst. Einnahme", gehalt: "Gehalt", anlage: "Anlage zu Rechnung"};

  EXT.nav.push({key: "m45jahr", label: "Jahr bearbeiten", icon: "m45", section: "Finanzen"});
  EXT.views.m45jahr = vJahr;

  // corrections from the tax file call vTax() afterwards - on this page re-render here instead
  if (typeof vTax === "function" && !window.m45Wrapped) {
    window.m45Wrapped = true;
    const ov = vTax;
    window.vTax = function(...a){ if (view === "m45jahr") return reloadData(); return ov.apply(this, a); };
  }

  async function vJahr(){
    D = await api("/api/m45/jahr?year=" + F.year);
    if (!D || !D.euer) return;
    render();
  }
  async function reloadData(){ D = await api("/api/m45/jahr?year=" + F.year); if (D && D.euer) render(); }

  function cnt(k){
    if (!D) return "";
    if (k === "re") return D.rechnungen.length;
    if (TYP_OF[k]) return D.belege.filter(b => b.typ === TYP_OF[k]).length;
    if (k === "ueb") return D.pruefung.filter(p => p.stufe === "warnung").length || "";
    return "";
  }

  function render(){
    const e = D.euer, ab = D.abschluss || {}, c = D.calc || {};
    const hasB = ab.est_festgesetzt != null && ab.est_festgesetzt !== "";
    const er = hasB && ab.erstattung != null && ab.erstattung !== "" ? +ab.erstattung : -(D.differenz || 0);
    const acts = yearSel("m45y", F.year) +
      `<button class="btn" id="m45jb" type="button">${ic("pdf")} Jahresbericht</button>` +
      `<button class="btn pri" id="m45sb" type="button">${ic("up")} Steuerbescheid einfügen</button>`;
    $("#main").innerHTML = `<div class="page">${pageHead("Jahr bearbeiten " + F.year, "Alle Zahlen des Jahres an einer Stelle prüfen und ändern", acts)}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Betriebseinnahmen</div><div class="v">${eur(e.einnahmen)}</div><div class="s">Rechnungen ${eur0(e.einnahmen_rechnungen)} · sonstige ${eur0(e.einnahmen_sonstige)}</div></div>
        <div class="card kpi"><div class="l">Betriebsausgaben</div><div class="v">${eur(e.ausgaben)}</div><div class="s">${Object.keys(e.kategorien || {}).length} Kategorien</div></div>
        <div class="card kpi"><div class="l">Gewinn (EÜR)</div><div class="v">${eur(e.gewinn)}</div><div class="s">${e.offen_anzahl ? `+ ${eur0(e.offen)} offen` : "keine offenen Posten"}</div></div>
        <div class="card kpi acc"><div class="l">${er >= 0 ? "Erstattung" : "Nachzahlung"} ${hasB ? "lt. Bescheid" : "(Schätzung)"}</div><div class="v">${eur(Math.abs(er))}</div>
          <div class="s">${hasB ? `ESt festgesetzt ${eur0(ab.est_festgesetzt)}${ab.bescheid_datum ? " · Bescheid " + dde(ab.bescheid_datum) : ""}` : `ESt geschätzt ${eur0(c.gesamt || 0)}`}${ab.abgeschlossen ? " · abgeschlossen" : ""}</div></div></div>
      <div style="display:flex;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
        <div class="seg" id="m45tabs" style="flex-wrap:wrap;max-width:100%">${TABS.map(([k, l]) => { const n = cnt(k); return `<button type="button" data-m45t="${k}" class="${F.tab === k ? "on" : ""}">${l}${n !== "" ? ` <span class="small" style="opacity:.75">${n}</span>` : ""}</button>`; }).join("")}</div>
        <span style="flex:1"></span>
        <span id="m45dirty" style="display:none;align-items:center;gap:8px"><span class="small" id="m45dn" style="color:var(--warn)"></span>
          <button class="btn sm" id="m45disc" type="button">Verwerfen</button><button class="btn sm pri" id="m45save" type="button">${ic("save")} Änderungen speichern</button></span></div>
      <div id="m45body"></div></div>`;
    bindCommon();
    $("#m45y").onchange = async ev => {
      if (nDirty() && !await confirmBox(`${nDirty()} ungespeicherte Änderung(en) verwerfen?`, "Verwerfen")) { ev.target.value = F.year; return; }
      clearDirty(); F.year = +ev.target.value; keep(); vJahr(); };
    $("#m45jb").onclick = () => jahresbericht(F.year);
    $("#m45sb").onclick = () => m44Insert(F.year, () => { F.tab = "abs"; keep(); reloadData(); });
    $$("[data-m45t]").forEach(b => b.onclick = () => { F.tab = b.dataset.m45t; keep(); selClear(); render(); });
    drawDirty();
    const B = $("#m45body");
    ({ueb: tabUeb, re: tabRe, aus: tabBel, ein: tabBel, geh: tabBel, st: tabSt, abs: tabAbs}[F.tab] || tabUeb)(B);
  }

  function clearDirty(){ Object.keys(DB).forEach(k => delete DB[k]); Object.keys(DR).forEach(k => delete DR[k]); }
  function drawDirty(){
    // structure stays in place - only text/visibility change (a click on "speichern" right after editing a field
    // fires the field's change event first; re-creating the button there would swallow the click)
    const el = $("#m45dirty"); if (!el) return;
    const n = nDirty();
    el.style.display = n ? "inline-flex" : "none";
    $("#m45dn").textContent = n ? `${n} Änderung(en) nicht gespeichert` : "";
    $("#m45disc").onclick = () => { clearDirty(); render(); };
    $("#m45save").onclick = saveAll;
  }
  async function saveAll(){
    if ((D.abschluss || {}).abgeschlossen && !await confirmBox(`Das Jahr ${F.year} ist als abgeschlossen markiert. Trotzdem ändern?`, "Speichern")) return;
    const errs = []; let done = 0;
    const br = Object.entries(DB).map(([id, f]) => Object.assign({id: +id}, f));
    if (br.length) { const r = await api("/api/m45/belege_save", {rows: br}); if (r && r.ok) { done += r.done; errs.push(...r.errors); } }
    const rr = Object.entries(DR).map(([id, f]) => Object.assign({id: +id}, f));
    if (rr.length) { const r = await api("/api/m45/rechnungen_save", {rows: rr}); if (r && r.ok) { done += r.done; errs.push(...r.errors); } }
    clearDirty();
    toast(`${done} gespeichert` + (errs.length ? " – " + errs.join(" · ") : ""), !!errs.length);
    await reload(); await reloadData();
  }

  // ---------------- Ueberblick ----------------
  function tabUeb(B){
    const ys = String(F.year);
    const M = Array.from({length: 12}, () => ({ein: 0, aus: 0, geh: 0, n: 0}));
    D.rechnungen.forEach(i => { if (i.status === "bezahlt" && i.zufluss === F.year) { const m = i.zehn_tage ? 11 : +((i.bezahlt_am || i.datum).slice(5, 7)) - 1; M[m].ein += +i.summe || 0; M[m].n++; } });
    D.belege.forEach(b => { const m = +b.datum.slice(5, 7) - 1; if (m < 0 || m > 11) return;
      if (b.typ === "einnahme") M[m].ein += +b.betrag || 0; else if (b.typ === "ausgabe") M[m].aus += +b.betrag || 0; else if (b.typ === "gehalt") M[m].geh += +b.betrag || 0; });
    const tot = M.reduce((a, m) => ({ein: a.ein + m.ein, aus: a.aus + m.aus, geh: a.geh + m.geh}), {ein: 0, aus: 0, geh: 0});
    const ST = {warnung: "warn", hinweis: "", info: ""};
    B.innerHTML = `<div class="grid" style="grid-template-columns:minmax(320px,1fr) minmax(320px,1.3fr);align-items:start">
      <div class="card"><div class="hd"><h3>Prüfung ${ys}</h3></div><div class="bd">
        ${D.pruefung.length ? D.pruefung.map(p => `<div class="alert ${ST[p.stufe] || ""}" data-m45go="${p.tab}" style="margin-bottom:6px;font-size:12.5px">${ic(p.stufe === "info" ? "check" : "alert")}<span>${esc(p.text)}</span></div>`).join("")
          : `<div class="muted small">Alles vollständig – keine Auffälligkeiten gefunden.</div>`}
        <div class="small muted" style="margin-top:10px">Klick auf einen Hinweis öffnet den passenden Reiter. Steuerakte: ${D.akte} Unterlage(n).</div></div></div>
      <div class="card"><div class="hd"><h3>Monate ${ys}</h3></div>
        <table class="t nosort"><thead><tr><th>Monat</th><th class="r">Einnahmen (Zufluss)</th><th class="r">Ausgaben</th><th class="r">Ergebnis</th><th class="r">Gehalt (netto)</th></tr></thead><tbody>
        ${M.map((m, k) => `<tr><td>${MONL[k]}</td><td class="r num">${m.ein ? eur(m.ein) : "–"}</td><td class="r num">${m.aus ? eur(m.aus) : "–"}</td><td class="r num" style="color:${m.ein - m.aus < 0 ? "var(--bad)" : "inherit"}">${m.ein || m.aus ? eur(m.ein - m.aus) : "–"}</td><td class="r num muted">${m.geh ? eur(m.geh) : "–"}</td></tr>`).join("")}
        </tbody><tfoot><tr><td><b>Summe</b></td><td class="r num"><b>${eur(tot.ein)}</b></td><td class="r num"><b>${eur(tot.aus)}</b></td><td class="r num"><b>${eur(tot.ein - tot.aus)}</b></td><td class="r num">${eur(tot.geh)}</td></tr></tfoot></table>
        <div class="small muted" style="padding:8px 14px 12px">Ausgaben ohne AfA, Fahrten und Homeoffice-Pauschale – die stehen in der EÜR (Kachel oben). Zahlungen nach der 10-Tage-Regel (Anfang Januar) stehen im Dezember.</div></div></div>`;
    $$("[data-m45go]", B).forEach(a => a.onclick = () => { F.tab = a.dataset.m45go; keep(); render(); });
  }

  // ---------------- Rechnungen ----------------
  function tabRe(B){
    const ys = String(F.year);
    const ql = (F.q || "").toLowerCase();
    const rows = D.rechnungen.filter(i => !ql || [i.nr, i.kunde, i.titel, i.kdnr].join(" ").toLowerCase().includes(ql));
    const STL = {offen: "offen", bezahlt: "bezahlt", entwurf: "Entwurf", storniert: "storniert"};
    B.innerHTML = `<div class="card"><div class="hd"><h3>Rechnungen ${ys}</h3><div class="act"><input class="in" id="m45q" placeholder="Suchen …" value="${esc(F.q || "")}" style="width:200px"></div></div>
      <div style="overflow-x:auto"><table class="t" id="m45tre"><thead><tr><th>Nr.</th><th>Datum</th><th>Kunde</th><th class="r">Betrag</th><th>Status</th><th>bezahlt am</th><th>zählt für</th><th></th></tr></thead><tbody>
      ${rows.map(i => { const d = DR[i.id] || {}; const st = d.status || i.status, bz = d.bezahlt_am !== undefined ? d.bezahlt_am : (i.bezahlt_am || "");
        const ed = i.status === "offen" || i.status === "bezahlt";
        const zj = st === "bezahlt" ? (d.bezahlt_am !== undefined ? (bz ? +bz.slice(0, 4) : null) : i.zufluss) : null;
        return `<tr data-m45r="${i.id}" class="${DR[i.id] ? "m45dirty" : ""}"><td class="num"><b>${esc(i.nr || "–")}</b>${i.typ === "storno" ? ' <span class="badge bad">Storno</span>' : ""}</td>
          <td class="num">${dde(i.datum)}${i.datum.slice(0, 4) !== ys ? ` <span class="badge" title="Rechnung aus ${i.datum.slice(0, 4)}, Zahlung ${ys}">${i.datum.slice(0, 4)}</span>` : ""}</td>
          <td>${esc(i.kunde || i.kdnr || "")}<div class="small muted">${esc(i.titel || "")}</div></td><td class="r num">${eur(i.summe)}</td>
          <td>${ed ? `<select class="in" data-rf="status" style="width:auto">${["offen", "bezahlt"].map(s => `<option ${s === st ? "selected" : ""}>${s}</option>`).join("")}</select>` : `<span class="badge">${STL[i.status] || esc(i.status)}</span>`}</td>
          <td>${ed ? `<input type="date" class="in" data-rf="bezahlt_am" value="${esc(bz)}" ${st === "bezahlt" ? "" : "disabled"} style="width:150px">` : (bz ? dde(bz) : "")}</td>
          <td data-m45z>${zj ? `<span class="badge ${zj === F.year ? "ok" : ""}">${zj}${i.zehn_tage && d.bezahlt_am === undefined ? " (10-Tage)" : ""}</span>` : `<span class="small muted">–</span>`}</td>
          <td class="r"><button class="btn sm ghost" data-m45open="${i.id}" type="button">${ic("open")}</button></td></tr>`; }).join("") || `<tr><td colspan="8" class="muted">Keine Rechnungen ${ys}.</td></tr>`}
      </tbody></table></div>
      <div class="small muted" style="padding:8px 14px 12px">Status und Zahldatum hier ändern bestimmt, in welchem Jahr die Einnahme zählt (Zuflussprinzip). Inhalte festgeschriebener Rechnungen änderst du nur per Storno – über ${ic("open")} öffnen.</div></div>`;
    $("#m45q").oninput = ev => { F.q = ev.target.value; const p = ev.target.selectionStart; tabRe(B); const n = $("#m45q"); n.focus(); n.setSelectionRange(p, p); };
    $$("[data-m45r]", B).forEach(tr => {
      const id = tr.dataset.m45r, i = D.rechnungen.find(x => String(x.id) === id);
      $$("[data-rf]", tr).forEach(inp => inp.onchange = () => {
        const d = DR[id] || (DR[id] = {});
        d[inp.dataset.rf] = inp.value;
        const bzI = $("[data-rf=bezahlt_am]", tr);
        if (inp.dataset.rf === "status") { bzI.disabled = inp.value !== "bezahlt";
          // no automatic "today": the payment date decides the tax year - it has to be entered
          if (inp.value === "bezahlt" && !bzI.value) { d.bezahlt_am = ""; bzI.focus(); toast("Bitte das Zahldatum eintragen – es bestimmt, in welchem Jahr die Einnahme zählt."); }
          if (inp.value !== "bezahlt") { bzI.value = ""; d.bezahlt_am = ""; } }
        if ((d.status || i.status) === i.status && (d.bezahlt_am === undefined || d.bezahlt_am === (i.bezahlt_am || ""))) delete DR[id];
        const st = (DR[id] || {}).status || i.status, bz = bzI.value;
        const zj = st === "bezahlt" ? (DR[id] ? (bz ? +bz.slice(0, 4) : null) : i.zufluss) : null;
        $("[data-m45z]", tr).innerHTML = zj ? `<span class="badge ${zj === F.year ? "ok" : ""}">${zj}</span>` : st === "bezahlt" ? `<span class="small" style="color:var(--warn)">Datum fehlt</span>` : `<span class="small muted">–</span>`;
        tr.classList.toggle("m45dirty", !!DR[id]); drawDirty(); });
    });
    $$("[data-m45open]", B).forEach(b => b.onclick = () => openInvoice(+b.dataset.m45open));
  }

  // ---------------- Belege (Ausgaben / Einnahmen / Gehalt) ----------------
  function tabBel(B){
    const typ = TYP_OF[F.tab], ys = String(F.year);
    const ql = (F.q || "").toLowerCase();
    const all = D.belege.filter(b => b.typ === typ);
    const rows = all.filter(b => !ql || [b.partner, b.nr, b.notiz, b.kategorie].join(" ").toLowerCase().includes(ql));
    const kats = D.kategorien || [];
    const cur = (b, k) => DB[b.id] && DB[b.id][k] !== undefined ? DB[b.id][k] : b[k];
    const sum = rows.reduce((a, b) => a + pnum(cur(b, "betrag")), 0);
    const title = {ausgabe: "Ausgaben", einnahme: "Sonstige Einnahmen", gehalt: "Gehalt / Lohn"}[typ];
    const katCell = b => typ === "ausgabe"
      ? `<select class="in" data-bf="kategorie" style="width:170px"><option value="" ${!cur(b, "kategorie") ? "selected" : ""}>– ohne –</option>${kats.map(k => `<option ${k === cur(b, "kategorie") ? "selected" : ""}>${esc(k)}</option>`).join("")}${cur(b, "kategorie") && !kats.includes(cur(b, "kategorie")) ? `<option selected>${esc(cur(b, "kategorie"))}</option>` : ""}</select>`
      : `<input class="in" data-bf="kategorie" value="${esc(cur(b, "kategorie") || "")}" style="width:150px">`;
    B.innerHTML = `<div class="card"><div class="hd"><h3>${title} ${ys}</h3><div class="act">
        <input class="in" id="m45q" placeholder="Suchen …" value="${esc(F.q || "")}" style="width:200px">
        <button class="btn sm" id="m45imp" type="button" data-go="beleg">${ic("up")} Belege importieren</button>
        <button class="btn sm pri" id="m45neu" type="button">${ic("plus")} Neuer Eintrag</button></div></div>
      <div style="overflow-x:auto"><table class="t" id="m45tb"><thead><tr><th>Datum</th><th>${typ === "gehalt" ? "Arbeitgeber" : "Partner"}</th><th>Nr.</th><th class="r">${typ === "gehalt" ? "Netto" : "Betrag"}</th><th>${typ === "ausgabe" ? "EÜR-Kategorie" : "Kategorie"}</th><th>Notiz</th><th>Art</th><th></th></tr></thead><tbody>
      ${rows.map(b => `<tr data-m45b="${b.id}" class="${DB[b.id] ? "m45dirty" : ""}">
          <td><input type="date" class="in" data-bf="datum" value="${esc(cur(b, "datum"))}" style="width:135px"></td>
          <td><input class="in" data-bf="partner" value="${esc(cur(b, "partner") || "")}" style="min-width:120px">${b.korrektur ? '<div class="small muted">Korrekturbuchung</div>' : ""}${typ === "gehalt" && b.brutto ? `<div class="small muted">Brutto ${eur(b.brutto)}${b.lst ? " · LSt " + eur(b.lst) : ""}</div>` : ""}</td>
          <td><input class="in" data-bf="nr" value="${esc(cur(b, "nr") || "")}" style="width:90px"></td>
          <td class="r"><input class="in num" data-bf="betrag" value="${nde(pnum(cur(b, "betrag")))}" style="width:105px"></td>
          <td>${katCell(b)}</td>
          <td><input class="in" data-bf="notiz" value="${esc(cur(b, "notiz") || "")}" style="min-width:110px"></td>
          <td><select class="in" data-bf="typ" style="width:auto">${Object.entries(TYPL).map(([k, l]) => `<option value="${k}" ${k === cur(b, "typ") ? "selected" : ""}>${l}</option>`).join("")}</select></td>
          <td class="r" style="white-space:nowrap">${b.file ? `<button class="btn sm ghost" type="button" data-m45f="${esc(b.file)}" title="Belegdatei öffnen">${ic("open")}</button>` : ""}<button class="btn sm ghost" type="button" data-m45e="${b.id}" title="Alle Details bearbeiten">…</button></td></tr>`).join("")
        || `<tr><td colspan="8" class="muted">Keine Einträge ${ys}.</td></tr>`}
      </tbody><tfoot><tr><td colspan="3"><b>${rows.length} Einträge</b>${rows.length !== all.length ? ` <span class="small muted">(von ${all.length})</span>` : ""}</td><td class="r num"><b>${eur(sum)}</b></td><td colspan="4"></td></tr></tfoot></table></div>
      <div class="small muted" style="padding:8px 14px 12px">Felder direkt ändern, dann oben <b>Änderungen speichern</b>. „Art“ verschiebt einen Eintrag z. B. von Ausgabe zu sonstiger Einnahme. Mehrere markieren → Kategorie setzen oder löschen.</div></div>`;
    $("#m45q").oninput = ev => { F.q = ev.target.value; const p = ev.target.selectionStart; tabBel(B); const n = $("#m45q"); n.focus(); n.setSelectionRange(p, p); };
    $("#m45neu").onclick = () => neu(typ);
    bindCommon(B);
    $$("[data-m45b]", B).forEach(tr => {
      const id = tr.dataset.m45b, b = D.belege.find(x => String(x.id) === id);
      $$("[data-bf]", tr).forEach(inp => inp.oninput = inp.onchange = ev => {
        const k = inp.dataset.bf, d = DB[id] || (DB[id] = {});
        let v = inp.value; if (k === "betrag") { v = pnum(v); if (ev.type === "change") inp.value = nde(v); }
        const orig = k === "betrag" ? +b[k] || 0 : (b[k] || "");
        if (k === "betrag" ? Math.abs(v - orig) < 0.005 : v === orig) delete d[k]; else d[k] = v;
        if (!Object.keys(d).length) delete DB[id];
        tr.classList.toggle("m45dirty", !!DB[id]); drawDirty();
        if (k === "betrag") { const s = $$("[data-m45b]", B).reduce((a, r) => a + pnum($("[data-bf=betrag]", r).value), 0); const f = $("tfoot td.r b", B); if (f) f.textContent = eur(s); }
      });
    });
    $$("[data-m45f]", B).forEach(x => x.onclick = () => api("/api/open", {path: x.dataset.m45f}));
    $$("[data-m45e]", B).forEach(x => x.onclick = async () => {
      if (DB[x.dataset.m45e] && !await confirmBox("Ungespeicherte Änderungen in dieser Zeile verwerfen und den Beleg-Dialog öffnen?", "Öffnen")) return;
      delete DB[x.dataset.m45e];
      const b = D.belege.find(y => String(y.id) === x.dataset.m45e); if (b) editBeleg(b, () => go("m45jahr")); });
    selectify({kind: "m45beleg", rows: $$("[data-m45b]", B), id: "data-m45b", rerender: () => tabBel(B), actions: [
      ...(typ === "ausgabe" ? [{label: "Kategorie setzen", run: async ids => {
        const v = await askValue("Kategorie setzen", `<label class="f">EÜR-Kategorie<select class="in" id="m45k">${kats.map(k => `<option>${esc(k)}</option>`).join("")}</select></label>`, mb => $("#m45k", mb).value);
        if (v == null) return false; await bulk("beleg", "kategorie", ids.map(Number), v); ids.forEach(i => delete DB[i]); await reloadData(); }}] : []),
      {label: "Löschen", cls: "danger", run: async ids => { if (!await ask(ids.length + " Eintrag/Einträge löschen? Belegdateien wandern in den Papierkorb.", "Löschen")) return false;
        await bulk("beleg", "delete", ids.map(Number)); ids.forEach(i => delete DB[i]); await reload(); await reloadData(); }}]});
  }

  async function neu(typ){
    const ys = String(F.year);
    const def = ys === String(thisYear) ? todayIso() : ys + "-12-31";
    const kats = D.kategorien || [];
    const ok = await modal(`Neuer Eintrag ${ys} – ${TYPL[typ]}`, `<div class="fr">
      <div class="row"><label class="f">Datum<input type="date" class="in" id="m45nd" value="${def}" min="${ys}-01-01" max="${ys}-12-31"></label>
        <label class="f">${typ === "gehalt" ? "Netto" : "Betrag"} €<input class="in num" id="m45nb"></label>
        ${typ === "gehalt" ? `<label class="f">Brutto €<input class="in num" id="m45nbr"></label>` : ""}</div>
      <label class="f">${typ === "gehalt" ? "Arbeitgeber" : "Partner / Lieferant"}<input class="in" id="m45np"></label>
      <div class="row"><label class="f">Beleg-Nr.<input class="in" id="m45nn"></label>
        ${typ === "ausgabe" ? `<label class="f">EÜR-Kategorie<select class="in" id="m45nk">${kats.map(k => `<option>${esc(k)}</option>`).join("")}</select></label>` : `<label class="f">Kategorie<input class="in" id="m45nk"></label>`}</div>
      <label class="f">Notiz<input class="in" id="m45no"></label>
      <div class="small muted">Ohne Belegdatei – die Datei kannst du später über „…“ bzw. unter „Belege &amp; Import“ zuordnen.</div></div>`,
      [{label: "Abbrechen"}, {label: "Anlegen", cls: "pri", value: 1, onClick: async mb => {
        const r = await api("/api/m45/beleg_neu", {typ, datum: $("#m45nd", mb).value, betrag: pnum($("#m45nb", mb).value), brutto: $("#m45nbr", mb) ? pnum($("#m45nbr", mb).value) : 0,
          partner: $("#m45np", mb).value, nr: $("#m45nn", mb).value, kategorie: $("#m45nk", mb).value, notiz: $("#m45no", mb).value});
        if (!r || !r.ok) return false; }}]);
    if (ok) { toast("Angelegt"); await reload(); await reloadData(); }
  }

  // ---------------- Steuer-Angaben ----------------
  function tabSt(B){
    const i = D.inputs || {};
    const nf = (k, l, d = 2) => `<label class="f">${l}<input class="in num" data-si="${k}" value="${nde(i[k] || 0, d)}"></label>`;
    B.innerHTML = `<div class="card"><div class="hd"><h3>Angaben für die Steuerberechnung ${F.year}</h3><div class="act"><button class="btn sm pri" id="m45sts" type="button">${ic("save")} Speichern &amp; neu berechnen</button></div></div><div class="bd">
      <div class="row" style="flex-wrap:wrap">${nf("wk", "Werbungskosten tatsächlich €")}${nf("vorsorge_extra", "weitere Vorsorge (KV/PV privat, Rürup …) €")}${nf("sonder", "Sonderausgaben (Spenden …) €")}
        ${nf("vorauszahlung", "ESt-Vorauszahlungen €")}${nf("sonstige", "Sonstige Einkünfte €")}${nf("ho_tage", "Homeoffice-Tage (max. 210)", 0)}
        <label class="f">Homeoffice zählt für<select class="in" data-si="ho_zuordnung" data-txt="1"><option value="selbst" ${i.ho_zuordnung !== "gehalt" ? "selected" : ""}>Selbstständigkeit (EÜR)</option><option value="gehalt" ${i.ho_zuordnung === "gehalt" ? "selected" : ""}>Angestellt (Werbungskosten)</option></select></label></div>
      <div class="row" style="margin-top:12px;align-items:center;flex-wrap:wrap">
        <label class="chk" style="flex:none"><input type="checkbox" data-si="kist" ${i.kist ? "checked" : ""}> Kirchensteuerpflichtig</label>
        <label class="f" style="flex:none;width:110px">KiSt-Satz %<input class="in num" data-si="kist_satz" value="${nde(i.kist_satz || 9, 1)}"></label>
        <label class="chk" style="flex:none"><input type="checkbox" data-si="gewerblich" ${i.gewerblich ? "checked" : ""}> gewerblich (Gewerbesteuer)</label>
        <label class="f" style="flex:none;width:120px">Hebesatz %<input class="in num" data-si="hebesatz" value="${nde(i.hebesatz || 475, 0)}"></label>
        <label class="chk" style="flex:none"><input type="checkbox" data-si="splitting" ${i.splitting ? "checked" : ""}> Zusammenveranlagung</label>
        <label class="f" style="flex:none;width:200px">zvE Partner/in €<input class="in num" data-si="partner_zve" value="${nde(i.partner_zve || 0)}"></label></div>
      <div class="small muted" style="margin-top:10px">Gleiche Angaben wie unter „Jahresabrechnung &amp; Steuer“ – Änderungen gelten dort sofort mit.</div></div></div>`;
    $("#m45sts").onclick = async () => {
      const inp = {}; $$("[data-si]", B).forEach(el => inp[el.dataset.si] = el.type === "checkbox" ? el.checked : (el.dataset.txt ? el.value : pnum(el.value)));
      const r = await api("/api/tax/save", {year: F.year, inputs: inp}); if (r) { toast("Gespeichert und neu berechnet"); reloadData(); } };
  }

  // ---------------- Bescheid & Abschluss ----------------
  function tabAbs(B){
    txYear = F.year;
    const h = D.bescheide || [];
    B.innerHTML = `<div id="akte"></div>
      ${h.length ? `<div class="card" style="margin-top:14px"><div class="hd"><h3>Übernommene Bescheide ${F.year}</h3></div>
        <table class="t nosort"><thead><tr><th>Bescheid vom</th><th></th><th class="r">ESt</th><th class="r">Soli</th><th class="r">zvE</th><th class="r">Erstattung / Nachzahlung</th><th>übernommen</th></tr></thead><tbody>
        ${h.slice().reverse().map(x => `<tr><td class="num">${x.datum ? dde(x.datum) : "–"}</td><td>${x.aenderung ? '<span class="badge">Änderung</span>' : ""}</td>
          <td class="r num">${x.werte.est_festgesetzt != null ? eur(x.werte.est_festgesetzt) : "–"}</td><td class="r num">${x.werte.soli_festgesetzt != null ? eur(x.werte.soli_festgesetzt) : "–"}</td>
          <td class="r num">${x.werte.zve != null ? eur(x.werte.zve) : "–"}</td>
          <td class="r num">${x.werte.erstattung != null ? `<span style="color:${x.werte.erstattung >= 0 ? "var(--ok)" : "var(--bad)"}">${x.werte.erstattung >= 0 ? "+" : "−"} ${eur(Math.abs(x.werte.erstattung))}</span>` : "–"}</td>
          <td class="small muted">${dde((x.uebernommen || "").slice(0, 10))}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
    loadAkte();
  }

  if (!document.getElementById("m45css")) { const st = document.createElement("style"); st.id = "m45css";
    st.textContent = "#m45tb td,#m45tre td{vertical-align:top} #m45tb .in,#m45tre .in{padding:4px 7px;font-size:12.5px} #m45tabs button{white-space:nowrap} tr.m45dirty td{background:rgba(255,170,0,.08)} tr.m45dirty td:first-child{box-shadow:inset 3px 0 0 var(--warn)}";
    document.head.appendChild(st); }
})();


// ============================================================================
// Teil aus m46_angleich.js
// ============================================================================
// Pfeiffer-Audio Rechnung v2.6.1 - UI-Modul m46_angleich: Jahr an den Steuerbescheid angleichen
// Dialog mit allen Abweichungen Programm <-> Bescheid, ein Klick bucht alles; Knopf + Hinweis in der Steuerakte;
// startet automatisch nach "In den Jahresabschluss uebernehmen" (m44), wenn es Abweichungen gibt.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const ART = {buchung: "Buchung", angabe: "Angabe", abgleich: "Abgleich", steuer: "lt. Bescheid"};

  function table(p, withCb){
    return `<table class="t nosort"><thead><tr>${withCb ? "<th></th>" : ""}<th>Bereich</th><th class="r">Programm</th><th class="r">Bescheid</th><th class="r">Differenz</th><th>Was passiert</th></tr></thead><tbody>
      ${p.rows.map(r => `<tr>${withCb ? `<td>${r.aktiv ? `<input type="checkbox" data-m46k="${r.key}" checked>` : ""}</td>` : ""}
        <td>${esc(r.label)}</td><td class="r num">${eur(r.programm)}</td><td class="r num">${r.bescheid == null ? "–" : eur(r.bescheid)}</td>
        <td class="r num">${r.ok ? `<span style="color:var(--ok)">✓ ${r.fix ? "lt. Bescheid" : "gleich"}</span>` : `<b style="color:var(--warn)">${r.diff >= 0 ? "+" : ""}${eur(r.diff)}</b>`}</td>
        <td class="small ${r.ok ? "muted" : ""}">${r.ok ? (r.fix ? "Bescheidwert wird verwendet" : "–") : `<span class="badge">${ART[r.art] || ""}</span> ${esc(r.aktion)}${r.hinweis ? `<div class="muted">${esc(r.hinweis)}</div>` : ""}`}
          ${r.key === "gewinn" && !r.ok && withCb ? `<div class="row" style="margin-top:4px;gap:6px"><select class="in" id="m46via" style="width:auto"><option value="einnahmen">als Einnahme buchen</option><option value="ausgaben">als Ausgabe buchen</option></select></div>` : ""}</td></tr>`).join("")}
      </tbody></table>`;
  }

  window.m46Open = async function(year, after, auto){
    const p = await api("/api/m46/plan?year=" + year, undefined, {quiet: true});
    if (!p || !p.rows) { if (after) after(); return; }
    if (auto && !p.offen) { if (after) after(); return; }
    if (!p.rows.length) { await modal(`An Bescheid angleichen ${year}`, `<div class="muted">${esc(p.hinweis)}</div>`); if (after) after(); return; }
    const needKat = p.rows.some(r => r.aktiv && (r.key === "ausgaben" || r.key === "gewinn"));
    const aktiv = p.offen > 0;
    const html = `<div class="fr">
      <div class="small" style="margin-bottom:8px">${aktiv ? `<b>${p.offen} Abweichung(en)</b> zwischen deinen Programmwerten und dem Bescheid${p.bescheid_datum ? " vom " + dde(p.bescheid_datum) : ""}. Angehakte Punkte werden so angepasst, dass ${year} mit dem Bescheid übereinstimmt.` : `${year} stimmt mit dem Bescheid überein.`}</div>
      ${table(p, aktiv)}
      ${aktiv ? `<div class="row" style="margin-top:10px;flex-wrap:wrap">
        <label class="f" style="flex:none">Buchungsdatum<input type="date" class="in" id="m46d" value="${year}-12-31" min="${year}-01-01" max="${year}-12-31"></label>
        ${needKat ? `<label class="f" style="flex:none;min-width:240px">EÜR-Kategorie (bei Ausgabe)<select class="in" id="m46kat">${(p.kategorien || []).map(k => `<option ${k === "Sonstige Betriebsausgaben" ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>` : ""}
        <label class="f">Notiz<input class="in" id="m46n" placeholder="Angleichung an Steuerbescheid ${year}"></label></div>
      <div class="small muted" style="margin-top:6px">Buchungen erscheinen unter „Korrekturbuchungen“ und lassen sich einzeln zurücknehmen. Der zvE-Abgleich gleicht Vorsorge- und Sonderausgaben so aus, wie das Finanzamt sie angesetzt hat. „lt. Bescheid“: Steuer, Soli, Kirchensteuer und Erstattung/Nachzahlung zeigt das Programm dann genau wie im Bescheid.</div>` : ""}
      ${p.steuer_fix || p.zve_abgleich ? `<div class="small muted" style="margin-top:8px">Aktiv: ${[p.zve_abgleich ? "zvE-Abgleich " + eur(p.zve_abgleich) : "", p.steuer_fix ? "Steuerwerte lt. Bescheid" : ""].filter(Boolean).join(" · ")}</div>` : ""}
      </div>`;
    let res = null;
    const btns = [{label: aktiv ? "Abbrechen" : "Schließen"}];
    if (p.steuer_fix || p.zve_abgleich) btns.push({label: "Angleichung zurücknehmen", onClick: async () => {
      if (!await confirmBox("zvE-Abgleich entfernen und Steuer wieder nach Programmberechnung anzeigen? (Korrekturbuchungen bleiben – die nimmst du in der Liste einzeln zurück.)", "Zurücknehmen")) return false;
      const r = await api("/api/m46/reset", {year}); if (r && r.ok) toast(r.info); }});
    if (aktiv) btns.push({label: "Angleichen", cls: "pri", value: 1, onClick: async mb => {
      const keys = $$("[data-m46k]", mb).filter(c => c.checked).map(c => c.dataset.m46k);
      if (!keys.length) { toast("Nichts angehakt", true); return false; }
      res = await api("/api/m46/apply", {year, keys, datum: $("#m46d", mb).value, notiz: $("#m46n", mb).value,
        kategorie: $("#m46kat", mb) ? $("#m46kat", mb).value : "", gewinn_via: $("#m46via", mb) ? $("#m46via", mb).value : "einnahmen"});
      if (!res || !res.ok) return false; }});
    await modal(`An Bescheid angleichen ${year}`, html, btns, true);
    if (res && res.ok) {
      await reload();
      await modal(`Angleichung ${year} erledigt`, `<div class="fr">
        ${res.info.map(t => `<div class="small">✓ ${esc(t)}</div>`).join("")}
        ${(res.errors || []).map(t => `<div class="alert warn" style="cursor:default;margin-top:6px;font-size:12.5px">${ic("alert")}<span>${esc(t)}</span></div>`).join("")}
        <div style="margin-top:10px">${table(res.plan, false)}</div>
        ${res.plan.offen ? `<div class="small" style="margin-top:6px;color:var(--warn)">${res.plan.offen} Punkt(e) weichen noch ab – nicht angehakt oder nicht buchbar.</div>` : `<div class="small" style="margin-top:6px;color:var(--ok)"><b>${year} stimmt jetzt mit dem Bescheid überein.</b></div>`}</div>`, [{label: "OK", cls: "pri"}], true);
    }
    if (after) after();
  };

  // tax page: year with tax values lt. Bescheid -> label the tile, hide the (estimated) tax reserve of that year
  EXT.after.push(async n => {
    if (n !== "vTax") return;
    const y = typeof txYear !== "undefined" ? txYear : thisYear;
    const t = await api("/api/tax?year=" + y, undefined, {quiet: true});
    if (!t || !t.lt_bescheid || y !== txYear) return;
    const l = $("#main .card.kpi.acc .l");
    if (l) l.textContent = (t.differenz >= 0 ? "Nachzahlung" : "Erstattung") + " lt. Bescheid";
    const s = $("#main .card.kpi.acc .s");
    if (s) s.textContent = `ESt festgesetzt ${eur(t.calc.gesamt)} · angerechnet ${eur(t.bereits_gezahlt)}`;
    const r = $("#m54tax"); if (r) r.remove();
  });

  // tax file: button + notice
  if (typeof loadAkte === "function" && !window.m46Wrapped) {
    window.m46Wrapped = true;
    const orig = loadAkte;
    window.loadAkte = async function(...a){
      const res = await orig.apply(this, a);
      try {
        const el = $("#akte"); if (!el) return res;
        const y = txYear;
        const act = $(".hd .act", el);
        if (act && !$("#m46btn", act)) {
          const b = document.createElement("button"); b.className = "btn sm"; b.id = "m46btn"; b.type = "button";
          b.innerHTML = `${ic("check")} An Bescheid angleichen`; b.title = "Alle Abweichungen zum Bescheid in einem Schritt angleichen";
          const ref = $("#m44btn", act); act.insertBefore(b, ref ? ref.nextSibling : act.firstChild);
          b.onclick = () => m46Open(y, () => { if (typeof view !== "undefined" && view === "m45jahr") go("m45jahr"); else loadAkte(); });
        }
        const p = await api("/api/m46/plan?year=" + y, undefined, {quiet: true});
        if (p && p.offen && !$("#m46note", el)) {
          const n = document.createElement("div"); n.id = "m46note"; n.className = "alert warn"; n.style.cssText = "margin:12px 16px 0;font-size:12.5px";
          n.innerHTML = `${ic("alert")}<span><b>${p.offen} Abweichung(en) zum Bescheid ${y}</b> – Klick: alles in einem Schritt angleichen.</span>`;
          n.onclick = () => $("#m46btn", el).click();
          const card = $(".card", el), hd = card && $(".hd", card); if (hd) hd.after(n);
        } else if (p && p.rows && p.rows.length && !p.offen && !$("#m46note", el)) {
          const bd = $(".hd .act", el); const s = document.createElement("span"); s.id = "m46note"; s.className = "badge ok"; s.innerHTML = '<span class="dot"></span>stimmt mit Bescheid';
          if (bd) bd.insertBefore(s, bd.firstChild);
        }
      } catch (e) { console.error(e); }
      return res;
    };
  }
})();
