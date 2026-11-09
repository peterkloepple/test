// Pfeiffer-Audio Rechnung v3.3.0 - UI-Modul m71b_abgleich v1.0.0: Seite "Abgleich" (Finanzen)
// Offene Bankumsaetze mit Vorschlaegen (Rechnung, Beleg, Ausgabe anlegen ...), sichere mit einem Klick,
// zweiter Reiter: Ausgabe-Belege ohne Bankbewegung.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m71b = '<path d="M4 7h11l-3-3M20 17H9l3 3"/><circle cx="18" cy="7" r="2"/><circle cx="6" cy="17" r="2"/>';
  EXT.nav.push({key: "m71b", label: "Abgleich", icon: "m71b", section: "Finanzen", cnt: () => (S.abgleich_offen || "")});
  EXT.views.m71b = vAbg;
  const F = {tab: "bank", year: thisYear, filter: "alle"};
  const SL = {3: ["sicher", "var(--green,#2e9e5b)"], 2: ["wahrscheinlich", "#d98a00"], 1: ["möglich", "var(--muted,#6b7280)"], 0: ["kein Treffer", "var(--muted,#6b7280)"]};
  const EXTRA = [["ausgabe", "Als Ausgabe anlegen"], ["einnahme", "Als Einnahme anlegen"], ["privat", "Privat (keine Buchung)"], ["erledigt", "Erledigt (ausblenden)"]];
  let D = null, B = null;

  async function vAbg(){
    const m = $("#main");
    m.innerHTML = `<div class="page">${pageHead("Abgleich", "Bankumsätze mit Rechnungen und Belegen verbinden – sichere Treffer mit einem Klick", "")}
      <div class="seg" id="abgtab" style="margin-bottom:12px"><button data-t="bank" class="${F.tab === "bank" ? "on" : ""}">Bankumsätze</button><button data-t="belege" class="${F.tab === "belege" ? "on" : ""}">Belege ohne Bankbewegung</button></div>
      <div id="abgbody"><div class="muted">Lade …</div></div></div>`;
    $$("#abgtab button").forEach(b => b.onclick = () => { F.tab = b.dataset.t; vAbg(); });
    if (F.tab === "bank") await bank(); else await belege();
  }

  function optsFor(r){
    const c = r.kandidaten || [];
    const have = new Set(c.map(k => k.aktion));
    const o = c.map((k, i) => `<option value="k${i}">${esc((k.sicher ? "● " : "") + k.text)}</option>`);
    EXTRA.forEach(([a, l]) => {
      if (have.has(a)) return;
      if (a === "ausgabe" && r.betrag > 0) return;
      if (a === "einnahme" && r.betrag < 0) return;
      o.push(`<option value="${a}">${esc(l)}</option>`);
    });
    return o.join("");
  }

  function itemOf(r, v){
    if (v && v[0] === "k") { const k = r.kandidaten[+v.slice(1)]; return {tx_id: r.id, aktion: k.aktion, ziel: k.ziel, kategorie: k.kategorie}; }
    return {tx_id: r.id, aktion: v};
  }

  async function bank(){
    D = await api("/api/abgleich/liste");
    const el = $("#abgbody");
    if (!D || !D.ok) { el.innerHTML = `<div class="alert warn">Liste konnte nicht geladen werden.</div>`; return; }
    S.abgleich_offen = D.anzahl;
    if (!D.bank) { el.innerHTML = `<div class="card" style="padding:18px"><b>Noch keine Bankumsätze im Programm.</b><div class="muted small" style="margin-top:6px">Kontoauszug unter <b>Bank-Abgleich</b> einlesen – danach erscheinen hier alle Umsätze, die noch keiner Rechnung oder keinem Beleg zugeordnet sind.</div></div>`; return; }
    if (!D.anzahl) { el.innerHTML = `<div class="card" style="padding:18px"><b style="color:var(--green,#2e9e5b)">✓ Alles abgeglichen.</b><div class="muted small" style="margin-top:6px">Jeder Bankumsatz ist einer Rechnung, einem Beleg oder „privat/erledigt“ zugeordnet.</div></div>`; return; }
    const rows = D.umsaetze.filter(r => F.filter === "alle" || (F.filter === "sicher" ? r.sicher === 3 : F.filter === "ein" ? r.betrag > 0 : r.betrag < 0));
    el.innerHTML = `<div class="card" style="padding:12px 14px;margin-bottom:12px"><div class="row" style="gap:10px;flex-wrap:wrap;align-items:center">
        <button class="btn pri" id="abgsafe" ${D.sicher ? "" : "disabled"}>✓ Alle sicheren übernehmen (${D.sicher})</button>
        <button class="btn" id="abgsel">Ausgewählte übernehmen</button>
        <select class="in" id="abgf" style="width:180px;flex:none"><option value="alle">Alle (${D.anzahl})</option><option value="sicher">Nur sichere</option><option value="ein">Nur Eingänge</option><option value="aus">Nur Ausgänge</option></select>
        <button class="btn ghost" id="abghid">Ausgeblendete anzeigen</button>
        <span class="small muted">● = Vorschlag des Programms. Sicher = Betrag und Rechnungsnummer/Name passen eindeutig.</span></div><div id="abghl"></div></div>
      <div class="card"><table class="tbl"><thead><tr><th style="width:28px"><input type="checkbox" id="abgall"></th><th style="width:90px">Datum</th><th style="width:110px" class="r" style="text-align:right">Betrag</th><th>Auftraggeber / Verwendungszweck</th><th style="width:44%">Zuordnung</th><th style="width:110px">Treffer</th><th style="width:90px"></th></tr></thead><tbody>
      ${rows.map(r => `<tr data-r="${r.id}"><td><input type="checkbox" data-c="${r.id}" ${r.sicher === 3 ? "checked" : ""}></td><td>${esc(dde(r.datum))}</td>
        <td class="r" style="text-align:right;color:${r.betrag < 0 ? "var(--red,#c0392b)" : "var(--green,#2e9e5b)"}"><b>${eur(r.betrag)}</b></td>
        <td><div><b>${esc(r.name || "")}</b></div><div class="small muted" style="word-break:break-word">${esc((r.zweck || "").slice(0, 160))}</div></td>
        <td><select class="in" data-s="${r.id}">${optsFor(r)}</select></td>
        <td><span class="small" style="color:${SL[r.sicher][1]}"><b>${SL[r.sicher][0]}</b></span></td>
        <td><button class="btn sm" data-ok="${r.id}">Übernehmen</button></td></tr>`).join("")}
      </tbody></table></div>`;
    $("#abgf").value = F.filter;
    $("#abghid").onclick = hidden;
    $("#abgf").onchange = e => { F.filter = e.target.value; bank(); };
    $("#abgall").onchange = e => $$("[data-c]").forEach(c => c.checked = e.target.checked);
    const byId = id => D.umsaetze.find(r => r.id === id);
    const run = async (items, label) => {
      if (!items.length) { toast("Nichts ausgewählt."); return; }
      const r = await api("/api/abgleich/anwenden", {items});
      if (!r || !r.ok) return;
      toast(`${r.erledigt} ${label}` + (r.fehler.length ? ` · ${r.fehler.length} nicht möglich: ${r.fehler[0]}` : ""), !!r.fehler.length);
      await reload(); await bank();
    };
    $$("[data-ok]").forEach(b => b.onclick = () => { const r = byId(+b.dataset.ok); run([itemOf(r, $(`[data-s="${r.id}"]`).value)], "übernommen"); });
    $("#abgsel").onclick = () => run($$("[data-c]").filter(c => c.checked).map(c => { const r = byId(+c.dataset.c); return itemOf(r, $(`[data-s="${r.id}"]`).value); }), "übernommen");
    $("#abgsafe").onclick = async () => {
      if (!await confirmBox(`${D.sicher} sichere Zuordnung(en) übernehmen?\nZahlungen werden auf die Rechnungen gebucht, Belege verknüpft.`)) return;
      const r = await api("/api/abgleich/anwenden", {alle_sicheren: true});
      if (r && r.ok) { toast(`${r.erledigt} übernommen` + (r.fehler.length ? ` · ${r.fehler.length} nicht möglich` : ""), !!r.fehler.length); await reload(); await bank(); }
    };
  }

  // rows marked "privat" / "erledigt" - can be brought back into the list
  async function hidden(){
    const r = await api("/api/abgleich/ausgeblendet");
    const el = $("#abghl");
    if (!r || !r.ok || !el) return;
    el.innerHTML = r.umsaetze.length ? `<table class="tbl" style="margin-top:10px"><tbody>${r.umsaetze.map(u => `<tr><td style="width:90px">${esc(dde(u.datum))}</td>
      <td style="width:110px;text-align:right">${eur(u.betrag)}</td><td>${esc(u.name || "")} <span class="small muted">${esc((u.zweck || "").slice(0, 80))}</span></td>
      <td style="width:80px" class="small">${esc(u.abg)}</td><td style="width:110px"><button class="btn sm" data-back="${u.id}">Zurückholen</button></td></tr>`).join("")}</tbody></table>`
      : `<div class="small muted" style="margin-top:8px">Keine ausgeblendeten Umsätze.</div>`;
    $$("[data-back]").forEach(b => b.onclick = async () => { await api("/api/abgleich/zuruecksetzen", {tx_id: +b.dataset.back}); await reload(); await bank(); });
  }

  async function belege(){
    B = await api("/api/abgleich/belege_ohne_bank?year=" + F.year);
    const el = $("#abgbody");
    if (!B || !B.ok) return;
    const ys = []; for (let y = thisYear; y >= thisYear - 5; y--) ys.push(y);
    el.innerHTML = `<div class="card" style="padding:12px 14px;margin-bottom:12px"><div class="row" style="gap:10px;align-items:center;flex-wrap:wrap">
        <select class="in" id="abgy" style="width:110px;flex:none">${ys.map(y => `<option ${y === F.year ? "selected" : ""}>${y}</option>`).join("")}</select>
        <span><b>${B.belege.length}</b> Ausgabe-Belege ohne Bankbewegung · zusammen <b>${eur(B.summe)}</b></span>
        <span class="small muted">Bar bezahlt (dann ins Kassenbuch), per Karte/PayPal oder fehlt ein Kontoauszug? Belege aus dem Kassenbuch sind schon herausgerechnet.</span></div></div>
      ${B.belege.length ? `<div class="card"><table class="tbl"><thead><tr><th style="width:90px">Datum</th><th>Partner</th><th>Kategorie</th><th class="r" style="text-align:right;width:110px">Betrag</th><th style="width:90px">Quelle</th></tr></thead><tbody>
        ${B.belege.map(b => `<tr><td>${esc(dde(b.datum))}</td><td>${esc(b.partner || "–")}</td><td class="small">${esc(b.kategorie || "")}</td><td class="r" style="text-align:right">${eur(b.betrag)}</td><td class="small muted">${esc(b.quelle || "")}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="card" style="padding:18px"><b style="color:var(--green,#2e9e5b)">✓ Für ${F.year} hat jeder Ausgabe-Beleg eine Bankbewegung (oder steht im Kassenbuch).</b></div>`}`;
    $("#abgy").onchange = e => { F.year = +e.target.value; belege(); };
  }

  console.log("INIT UI m71b_abgleich v1.0.0");
})();
