"use strict";
// m40 - Abschlagsrechnungen / Schlussrechnung (UI)
// Stellt ausserdem M4X bereit: eigene Reiter und Karten auf der Projektseite (genutzt von m41..m43).
// Autor: T. Pfeiffer
window.M4X = window.M4X || {tabs: [], cards: []};
M4X.tab = def => M4X.tabs.push(def);
M4X.card = fn => M4X.cards.push(fn);
M4X.openDoc = async id => { await reload(); openInvoice(id); };
M4X.num = (v, d = 2) => { let s = nde(v, d); if (s.includes(",")) s = s.replace(/0+$/, "").replace(/,$/, ""); return s; };
EXT.after.push(async (vn, id) => {
  if (vn !== "vProject") return;
  const tabs = $("#main .tabs");
  if (!tabs || tabs.dataset.m4x) return;
  tabs.dataset.m4x = "1";
  M4X.tabs.forEach(t => {
    const d = document.createElement("div");
    d.className = "tab" + (pTab === t.key ? " on" : "");
    d.dataset.m4xtab = t.key;
    d.textContent = t.label;
    d.onclick = () => { pTab = t.key; vProject(id); };
    tabs.appendChild(d);
  });
  const p = await api("/api/project?id=" + id, undefined, {quiet: true});
  if (!p || !p.id || !tabs.isConnected) return;
  M4X.cards.forEach(fn => { try { fn(p, tabs); } catch (e) { console.error(e); } });
  const t = M4X.tabs.find(t => t.key === pTab);
  const T = $("#ptab");
  if (t && T) { try { await t.render(T, p); } catch (e) { console.error(e); T.innerHTML = `<div class="card empty">Fehler: ${esc(e.message || e)}</div>`; } }
});

// ---------------- Abschlaege ----------------
const M40_ST = {frei: ["", "noch nicht gestellt"], entwurf: ["acc", "Entwurf"], offen: ["warn", "gestellt · offen"], bezahlt: ["ok", "bezahlt"], storniert: ["", "storniert"]};
function m40Badge(st){ const b = M40_ST[st] || ["", st || ""]; return `<span class="badge ${b[0]}"><span class="dot"></span>${b[1]}</span>`; }

M4X.tab({key: "m40", label: "Abschläge", render: m40Render});

async function m40Render(T, p){
  const d = await api("/api/m40/plan?project_id=" + p.id);
  const acc = d.angebote.find(a => ["angenommen", "erledigt"].includes(a.status)) || d.angebote[0];
  // v2.1.0: with Regelbesteuerung the order sum is NET (VAT is added on every installment / final invoice)
  const netOf = a => (a.netto ?? a.summe);
  const pl = d.plan || {auftragssumme: acc ? netOf(acc) : (p.budget || 0), angebot_id: acc ? acc.id : null, auftrag_text: "", quelle: "angebot",
    raten: d.vorlage.map((r, i) => Object.assign({}, r, {idx: null, state: "frei", inv: null}))};
  const k = d.kpi;
  T.innerHTML = `${k ? `<div class="grid g4" style="margin-bottom:14px">
      <div class="card kpi"><div class="l">Auftragssumme</div><div class="v">${eur(k.auftrag)}</div><div class="s">${pl.raten.length} Abschläge geplant</div></div>
      <div class="card kpi"><div class="l">Gestellt</div><div class="v">${eur(k.gestellt)}</div><div class="s">noch zu stellen ${eur(k.noch_zu_stellen)}</div></div>
      <div class="card kpi"><div class="l">Bezahlt</div><div class="v" style="color:var(--ok)">${eur(k.bezahlt)}</div><div class="s">${k.auftrag ? Math.round(100 * k.bezahlt / k.auftrag) + " % vom Auftrag" : ""}</div></div>
      <div class="card kpi"><div class="l">Offen (gestellt, unbezahlt)</div><div class="v" style="color:${k.offen ? "var(--warn)" : "inherit"}">${eur(k.offen)}</div><div class="s">&nbsp;</div></div></div>` : ""}
    <div class="card" style="margin-bottom:14px"><div class="hd"><h3>Zahlungsplan</h3><div class="act"><button class="btn sm" id="m40vor" title="Vorlage 30 / 40 / 30 % einsetzen (nur noch nicht gestellte Abschläge)">Vorlage 30/40/30</button></div></div><div class="bd">
      <div class="row" style="flex-wrap:wrap;align-items:flex-end">
        <label class="f" style="flex:.8">Auftragssumme €${d.regel ? " (netto)" : ""}<input class="in num" id="m40sum" value="${nde(pl.auftragssumme || 0)}"></label>
        <label class="f" style="flex:1.4">Grundlage (Angebot / Auftragsbestätigung)<select class="in" id="m40ang"><option value="">– manuell –</option>${d.angebote.map(a => `<option value="${a.id}" data-s="${netOf(a)}" ${a.id == pl.angebot_id ? "selected" : ""}>${esc(a.nr)} · ${dde(a.datum)} · ${eur(a.summe)}${a.status === "angenommen" ? " · angenommen" : ""}</option>`).join("")}</select></label>
        <button class="btn" style="flex:none" id="m40take">Summe übernehmen</button>
        <label class="f" style="flex:1.4">Bezeichnung des Auftrags (optional)<input class="in" id="m40txt" value="${esc(pl.auftrag_text || "")}" placeholder="z. B. Auftrag vom 01.10.2026 – Geländer Treppenhaus"></label>
      </div>
      <table class="t" style="margin-top:12px"><thead><tr><th style="width:28px">#</th><th>Bezeichnung</th><th style="width:90px">Art</th><th class="r" style="width:110px">Wert</th><th class="r" style="width:120px">Betrag</th><th>Rechnung</th><th style="width:220px"></th></tr></thead>
        <tbody id="m40rows">${pl.raten.map((r, i) => m40Row(r, i)).join("")}</tbody>
        <tfoot><tr><td></td><td colspan="3">Summe Zahlungsplan</td><td class="r num" id="m40psum"></td><td colspan="2" id="m40pdiff" class="small"></td></tr></tfoot></table>
      <div class="row" style="margin-top:10px;align-items:center">
        <button class="btn sm" style="flex:none" id="m40add">${ic("plus")} Abschlag</button>
        <label class="f" style="flex:none;width:300px;margin-left:auto">Schlussrechnung aus<select class="in" id="m40q">
          ${[["angebot", "Positionen des Angebots"], ["entries", "offenen Projektleistungen"], ["pauschal", "Auftragssumme (eine Position)"]].map(([v, l]) => `<option value="${v}" ${pl.quelle === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <button class="btn pri" style="flex:none" id="m40save">${ic("save")} Plan speichern</button>
      </div></div></div>
    <div class="card"><div class="hd"><h3>Schlussrechnung</h3></div><div class="bd">
      ${d.plan && d.plan.schluss && d.plan.schluss_state !== "storniert"
        ? `<div class="row" style="align-items:center"><span>${m40Badge(d.plan.schluss_state)}</span><b>${esc(d.plan.schluss_state === "entwurf" ? "Entwurf" : d.plan.schluss.nr)}</b><span class="muted">${dde(d.plan.schluss.datum)} · ${eur(d.plan.schluss.summe)}</span><span class="sp"></span><button class="btn" style="flex:none" data-m40open="${d.plan.schluss.id}">${ic("open")} Öffnen</button></div>`
        : `<div class="small muted" style="margin-bottom:10px">Enthält alle Leistungen (gewählte Quelle) und je gestellter Abschlagsrechnung eine Abzugsposition „abzgl. n. Abschlagsrechnung Nr. … vom …“ (negativer Betrag). Bezahlte und noch offene Abschläge werden im Text getrennt ausgewiesen. Abschläge im Entwurf werden nicht abgezogen.</div>
           <button class="btn pri" id="m40schluss" ${d.plan ? "" : "disabled"}>${ic("inv")} Schlussrechnung erstellen</button>${d.plan ? "" : `<span class="small muted" style="margin-left:10px">Zuerst den Plan speichern.</span>`}`}
    </div></div>`;
  const sumOf = () => pnum($("#m40sum", T).value);
  const calc = () => {
    let tot = 0;
    $$("#m40rows tr", T).forEach(tr => {
      const w = pnum($(".m40w", tr).value), b = $(".m40m", tr).value === "pct" ? Math.round(sumOf() * w) / 100 : w;
      $(".m40b", tr).textContent = eur(b); tot += b;
    });
    $("#m40psum", T).textContent = eur(tot);
    const diff = Math.round((tot - sumOf()) * 100) / 100;
    $("#m40pdiff", T).innerHTML = Math.abs(diff) >= 0.01 ? `<span style="color:var(--warn)">${diff > 0 ? "über" : "unter"} Auftragssumme: ${eur(Math.abs(diff))}</span>` : `<span style="color:var(--ok)">= Auftragssumme</span>`;
  };
  const collect = () => ({project_id: p.id, auftragssumme: sumOf(), angebot_id: +$("#m40ang", T).value || null, auftrag_text: $("#m40txt", T).value, quelle: $("#m40q", T).value,
    raten: $$("#m40rows tr", T).map(tr => ({idx: tr.dataset.idx === "" ? null : +tr.dataset.idx, invoice_id: +tr.dataset.inv || null, bez: $(".m40n", tr).value, modus: $(".m40m", tr).value, wert: pnum($(".m40w", tr).value)}))});
  const save = async quiet => { const r = await api("/api/m40/plan/save", collect()); if (r && r.ok && !quiet) toast("Zahlungsplan gespeichert"); return r && r.ok ? r : null; };
  const bindRows = () => {
    $$("#m40rows input, #m40rows select", T).forEach(e => e.oninput = calc);
    $$("[data-m40del]", T).forEach(b => b.onclick = () => { b.closest("tr").remove(); renumber(); calc(); });
    $$("[data-m40mk]", T).forEach(b => b.onclick = async () => {
      if (!sumOf()) { toast("Bitte zuerst eine Auftragssumme eintragen", true); return; }
      const tr = b.closest("tr"), pos = $$("#m40rows tr", T).indexOf(tr);
      const s = await save(true); if (!s) return;
      const r = await api("/api/m40/abschlag", {project_id: p.id, idx: pos});
      if (r && r.ok) { toast(`${pos + 1}. Abschlagsrechnung als Entwurf angelegt`); M4X.openDoc(r.id); }
    });
    $$("[data-m40open]", T).forEach(b => b.onclick = () => openInvoice(+b.dataset.m40open));
    $$("[data-m40un]", T).forEach(b => b.onclick = async () => { const r = await api("/api/m40/unlink", {project_id: p.id, idx: +b.dataset.m40un}); if (r && r.ok) { toast("Verknüpfung gelöst – Abschlag kann neu gestellt werden"); vProject(p.id); } });
  };
  const renumber = () => $$("#m40rows tr", T).forEach((tr, i) => { tr.firstElementChild.textContent = i + 1; });
  $("#m40add", T).onclick = () => { const n = $$("#m40rows tr", T).length; $("#m40rows", T).insertAdjacentHTML("beforeend", m40Row({bez: `${n + 1}. Abschlag`, modus: "pct", wert: 0, state: "frei", idx: null}, n)); bindRows(); calc(); };
  $("#m40vor", T).onclick = () => {
    const rows = $$("#m40rows tr", T);
    if (rows.some(tr => tr.dataset.lock === "1")) { toast("Es sind schon Abschläge gestellt – Vorlage nur für leere Pläne", true); return; }
    $("#m40rows", T).innerHTML = d.vorlage.map((r, i) => m40Row(Object.assign({}, r, {state: "frei", idx: null}), i)).join(""); bindRows(); calc();
  };
  $("#m40take", T).onclick = () => { const o = $("#m40ang", T).selectedOptions[0]; if (!o || !o.value) { toast("Bitte ein Angebot wählen", true); return; } $("#m40sum", T).value = nde(+o.dataset.s); calc(); };
  $("#m40sum", T).oninput = calc;
  $("#m40save", T).onclick = async () => { if (await save()) vProject(p.id); };
  const sb = $("#m40schluss", T);
  if (sb) sb.onclick = async () => {
    const s = await save(true); if (!s) return;
    const k2 = s.kpi || {};
    if (!await confirmBox(`Schlussrechnung als Entwurf erstellen?\n\nGestellte Abschläge (${eur(k2.gestellt || 0)}, davon bezahlt ${eur(k2.bezahlt || 0)}) werden als Abzugspositionen eingetragen.`, "Erstellen")) return;
    const r = await api("/api/m40/schluss", {project_id: p.id, quelle: $("#m40q", T).value});
    if (r && r.ok) { (r.warn || []).forEach(w => toast(w, true)); toast(`Schlussrechnung: Restbetrag ${eur(r.rest.rest)}`); M4X.openDoc(r.id); }
  };
  $$("[data-m40open]", T).forEach(b => b.onclick = () => openInvoice(+b.dataset.m40open));
  bindRows(); calc();
}

function m40Row(r, i){
  const inv = r.inv, lock = inv && ["offen", "bezahlt", "entwurf"].includes(r.state);
  let act = "";
  if (!inv || r.state === "storniert" || r.state === "frei") act = `<button class="btn sm pri" data-m40mk="1">${ic("inv")} Abschlagsrechnung erstellen</button>`;
  else act = `<button class="btn sm" data-m40open="${inv.id}">${ic("open")} ${r.state === "entwurf" ? "Entwurf öffnen" : "Öffnen"}</button>`;
  if (inv && r.state === "storniert") act += ` <button class="btn sm ghost" data-m40un="${r.idx}" title="Stornierte Rechnung vom Abschlag lösen">Lösen</button>`;
  return `<tr data-idx="${r.idx ?? ""}" data-inv="${inv ? inv.id : ""}" data-lock="${lock ? 1 : 0}"><td class="num">${i + 1}</td>
    <td><input class="in m40n" value="${esc(r.bez || "")}"></td>
    <td><select class="in m40m" ${lock ? "disabled" : ""}><option value="pct" ${r.modus !== "betrag" ? "selected" : ""}>%</option><option value="betrag" ${r.modus === "betrag" ? "selected" : ""}>€ fest</option></select></td>
    <td><input class="in num m40w" style="text-align:right" value="${nde(r.wert || 0)}" ${lock ? "disabled" : ""}></td>
    <td class="r num m40b"></td>
    <td>${inv ? `${m40Badge(r.state)} <span class="small">${esc(r.state === "entwurf" ? "" : inv.nr)} ${inv.datum ? dde(inv.datum) : ""}</span>` : m40Badge("frei")}</td>
    <td class="r" style="white-space:nowrap">${act}${!lock ? ` <button class="btn sm ghost danger" data-m40del="1" title="Zeile entfernen">${ic("trash")}</button>` : ""}</td></tr>`;
}
