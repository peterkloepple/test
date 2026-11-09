"use strict";
// m43 - Soll/Ist je Projekt (Karte auf der Projektseite) und Auswertung nach Bereich (eigene Seite)
// Autor: T. Pfeiffer
IC.m43 = '<path d="M3 3v18h18"/><path d="M7 14h3v4H7zM12 9h3v9h-3zM17 5h3v13h-3z"/>';
const M43_COL = {gruen: "var(--ok)", gelb: "var(--warn)", rot: "var(--bad)", grau: "var(--mute)"};
const M43_TXT = {gruen: "im Plan", gelb: "Achtung", rot: "überschritten", grau: "kein Soll"};
let m43F = {year: "", status: ""};
let m43Open = true;
try { m43Open = localStorage.getItem("m43_open") !== "0"; } catch (e) {}

function m43Dot(a, big){ const s = big ? 14 : 10; return `<span title="${M43_TXT[a] || ""}" style="display:inline-block;width:${s}px;height:${s}px;border-radius:50%;background:${M43_COL[a] || M43_COL.grau};vertical-align:middle"></span>`; }
function m43Val(v, unit){ return v == null ? "–" : unit === "Std" ? nde(v, 1) + " Std" : eur(v); }

M4X.card(async (p, tabs) => {
  const d = await api("/api/m43/project?project_id=" + p.id, undefined, {quiet: true});
  if (!d || !d.project || !tabs.isConnected || $("#m43card")) return;
  const c = document.createElement("div");
  c.className = "card"; c.id = "m43card"; c.style.marginBottom = "16px";
  const z = d.zeilen || [];
  c.innerHTML = `<div class="hd" style="cursor:pointer" id="m43tg"><h3>${m43Dot(d.ampel, true)} Soll/Ist</h3><div class="act small muted">${d.soll ? "Soll: " + esc(d.soll.quelle) : "Noch kein Soll – Kalkulation oder Angebot anlegen"} · ${m43Open ? "▾" : "▸"}</div></div>
    <div class="bd" style="${m43Open ? "" : "display:none"};padding-top:4px">
      ${z.length ? `<table class="t"><thead><tr><th></th><th>Kennzahl</th><th class="r">Soll</th><th class="r">Ist</th><th class="r">Abweichung</th><th class="r">%</th></tr></thead><tbody>
        ${z.map(r => `<tr><td style="width:20px">${m43Dot(r.ampel)}</td><td>${esc(r.label)}</td><td class="r num">${m43Val(r.soll, r.unit)}</td><td class="r num"><b>${m43Val(r.ist, r.unit)}</b></td>
          <td class="r num" style="color:${r.key === "stunden" || r.key === "material" ? (r.diff > 0 ? "var(--bad)" : "var(--ok)") : "inherit"}">${r.diff > 0 ? "+" : ""}${r.unit === "Std" ? nde(r.diff, 1) + " Std" : eur(r.diff)}</td>
          <td class="r num">${r.pct == null ? "–" : (r.pct > 0 ? "+" : "") + nde(r.pct, 1) + " %"}</td></tr>`).join("")}</tbody></table>` : ""}
      <div class="row small" style="margin-top:10px;gap:22px;flex-wrap:wrap">
        <span><span class="muted">Ist-Stunden</span> <b>${nde(d.ist.stunden, 1)}</b></span>
        <span><span class="muted">Material Ist (Belege ${eur(d.ist.material_belege)} + Lager ${eur(d.ist.material_lager)})</span> <b>${eur(d.ist.material_kosten)}</b></span>
        <span><span class="muted">abgerechnet</span> <b>${eur(d.ist.abgerechnet)}</b> <span class="muted">· bezahlt</span> <b>${eur(d.ist.bezahlt)}</b></span>
        <span><span class="muted">Deckungsbeitrag</span> <b>${eur(d.db)}</b></span>
        <span><span class="muted">Stundenlohn effektiv</span> <b>${d.stundenlohn == null ? "–" : eur(d.stundenlohn)}</b></span></div></div>`;
  tabs.parentNode.insertBefore(c, tabs);
  $("#m43tg", c).onclick = () => { m43Open = !m43Open; try { localStorage.setItem("m43_open", m43Open ? "1" : "0"); } catch (e) {} const b = $(".bd", c); b.style.display = m43Open ? "" : "none"; $("#m43tg .act", c).innerHTML = $("#m43tg .act", c).innerHTML.replace(/[▾▸]$/, m43Open ? "▾" : "▸"); };
});

EXT.nav.push({key: "m43sollist", label: "Soll/Ist", icon: "m43", section: "Projekte"});
EXT.views.m43sollist = m43View;

async function m43View(){
  const d = await api(`/api/m43/auswertung?year=${encodeURIComponent(m43F.year)}&status=${encodeURIComponent(m43F.status)}`);
  const years = [...new Set(S.projects.map(p => (p.start || "").slice(0, 4)).filter(Boolean))].sort().reverse();
  const g = d.gesamt, mx = Math.max(1, ...d.bereiche.map(b => Math.abs(b.db)));
  $("#main").innerHTML = `<div class="page">${pageHead("Soll/Ist & Deckungsbeitrag", "Deckungsbeitrag = abgerechneter Erlös − Materialkosten (Belege mit Projekt + Lager-Entnahmen zum EK). Stundenlohn effektiv = Deckungsbeitrag ÷ erfasste Stunden.",
      expButtons("m43_sollist", () => ({year: m43F.year, status: m43F.status})))}
    <div class="row" style="margin-bottom:14px;align-items:center;flex-wrap:wrap">
      <div class="chips" style="flex:none"><span class="chip ${!m43F.year ? "on" : ""}" data-m43y="">Alle Jahre</span>${years.map(y => `<span class="chip ${m43F.year === y ? "on" : ""}" data-m43y="${y}">${y}</span>`).join("")}</div>
      <div class="seg" style="flex:none">${[["", "Alle"], ["aktiv", "Aktiv"], ["abgeschlossen", "Abgeschlossen"]].map(([k, l]) => `<button class="${m43F.status === k ? "on" : ""}" data-m43s="${k}">${l}</button>`).join("")}</div></div>
    <div class="grid g4" style="margin-bottom:14px">
      <div class="card kpi"><div class="l">Erlös (abgerechnet)</div><div class="v">${eur(g.erloes)}</div><div class="s">noch offen ${eur(g.offen)}</div></div>
      <div class="card kpi"><div class="l">Materialkosten</div><div class="v">${eur(g.material)}</div><div class="s">Belege + Lager</div></div>
      <div class="card kpi acc"><div class="l">Deckungsbeitrag</div><div class="v">${eur(g.db)}</div><div class="s">${g.erloes ? nde(100 * g.db / g.erloes, 1) + " % vom Erlös" : "&nbsp;"}</div></div>
      <div class="card kpi"><div class="l">Stundenlohn effektiv</div><div class="v">${g.stundenlohn == null ? "–" : eur(g.stundenlohn)}</div><div class="s">${nde(g.stunden, 1)} Std erfasst</div></div></div>
    <div class="card" style="margin-bottom:14px;overflow:hidden"><div class="hd"><h3>Nach Bereich</h3></div><table class="t"><thead><tr><th>Bereich</th><th class="r">Projekte</th><th class="r">Erlös</th><th class="r">Material</th><th class="r">Deckungsbeitrag</th><th style="width:22%"></th><th class="r">DB-Quote</th><th class="r">Stunden</th><th class="r">Std-Lohn eff.</th></tr></thead>
      <tbody>${d.bereiche.map(b => { const col = BEREICH_COL[b.bereich] || "#888"; return `<tr><td><span class="badge" style="background:${col}1c;color:${col}">${esc(b.bereich)}</span></td><td class="r num">${b.projekte}</td><td class="r num">${eur(b.erloes)}</td><td class="r num">${eur(b.material)}</td><td class="r num"><b>${eur(b.db)}</b></td>
        <td><div class="prog"><div style="width:${Math.max(0, 100 * b.db / mx)}%;background:${col}"></div></div></td><td class="r num">${b.db_quote == null ? "–" : nde(b.db_quote, 1) + " %"}</td><td class="r num">${nde(b.stunden, 1)}</td><td class="r num">${b.stundenlohn == null ? "–" : eur(b.stundenlohn)}</td></tr>`; }).join("") || `<tr><td colspan="9" class="empty">Keine Projekte.</td></tr>`}</tbody></table></div>
    <div class="card" style="overflow:hidden"><div class="hd"><h3>Projekte</h3></div><table class="t"><thead><tr><th></th><th>Nr.</th><th>Projekt</th><th>Bereich</th><th class="r">Soll</th><th class="r">Erlös</th><th class="r">offen</th><th class="r">Material</th><th class="r">DB</th><th class="r">Std</th><th class="r">Std-Lohn eff.</th></tr></thead>
      <tbody>${d.rows.map(r => `<tr class="click" data-proj="${r.id}"><td style="width:20px">${m43Dot(r.ampel)}</td><td class="small">${esc(r.nr || "")}</td><td><b>${esc(r.name || "")}</b>${r.status !== "aktiv" ? ` <span class="badge">${esc(r.status || "")}</span>` : ""}</td><td class="small">${esc(r.bereich)}</td>
        <td class="r num">${r.soll ? eur(r.soll) : "–"}</td><td class="r num">${eur(r.erloes)}</td><td class="r num muted">${eur(r.offen)}</td><td class="r num">${eur(r.material)}</td><td class="r num"><b>${eur(r.db)}</b></td><td class="r num">${nde(r.stunden, 1)}</td><td class="r num">${r.stundenlohn == null ? "–" : eur(r.stundenlohn)}</td></tr>`).join("") || `<tr><td colspan="11" class="empty">Keine Projekte.</td></tr>`}</tbody></table></div></div>`;
  bindCommon();
  $$("[data-m43y]").forEach(c => c.onclick = () => { m43F.year = c.dataset.m43y; m43View(); });
  $$("[data-m43s]").forEach(c => c.onclick = () => { m43F.status = c.dataset.m43s; m43View(); });
}
