// Pfeiffer-Audio Rechnung v2.0.0 - UI-Modul m54_ruecklage: Steuer-Ruecklage live
// Dashboard-Karte + Abschnitt in "Jahresabrechnung & Steuer" (vTax).
// Autor: T. Pfeiffer
(function(){
  "use strict";
  if (!document.getElementById("m5xcss")) { const st = document.createElement("style"); st.id = "m5xcss";
    st.textContent = ".alert > svg + span{flex:1;min-width:0}"; document.head.appendChild(st); }
  const STC = {hinweis:"", warnung:"warn"};


  async function enter(r, after){
    const z = r.zurueckgelegt || {};
    await modal(`Steuer-Rücklage ${r.year}`, `<div class="fr">
      <div class="small muted" style="margin-bottom:8px">Trage ein, wie viel du für die Steuer ${r.year} bereits beiseitegelegt hast (z. B. Stand des Tagesgeld- oder Unterkontos).</div>
      <div class="row"><label class="f">Bereits zurückgelegt €<input class="in num" id="m54b" value="${z.betrag ? nde(z.betrag) : ""}"></label>
        <label class="f">Stand vom<input type="date" class="in" id="m54d" value="${z.datum || todayIso()}"></label></div>
      <label class="f">Notiz (Konto)<input class="in" id="m54n" value="${esc(z.notiz || "")}" placeholder="z. B. Tagesgeld C24"></label></div>`,
      [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
        const res = await api("/api/m54/save", {year: r.year, betrag: pnum($("#m54b", mb).value), datum: $("#m54d", mb).value, notiz: $("#m54n", mb).value});
        if (!res || !res.ok) return false;
        toast("Rücklage gespeichert"); if (after) after();
      }}]);
  }

  function body(r, compact){
    const pct = r.soll_netto > 0 ? Math.min(100, 100 * (r.zurueckgelegt.betrag || 0) / r.soll_netto) : 100;
    return `<div class="grid" style="grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
        <div><div class="small muted">pro Monat zurücklegen</div><div style="font:600 22px var(--disp)">${eur(r.monat)}</div>
          <div class="small muted">${r.vorauszahlung_jahr ? `davon über Vorauszahlungen hinaus: ${eur(r.monat_netto)}` : "keine Vorauszahlungen eingetragen"}</div></div>
        <div><div class="small muted">Steuer auf Selbstständigkeit ${r.year}</div><div style="font:600 22px var(--disp)">${eur(r.anteil_jahr)}</div>
          <div class="small muted">Gewinn ${eur0(r.gewinn_bisher)} → hochgerechnet ${eur0(r.gewinn_hoch)}</div></div></div>
      <div class="small muted">Soll bis heute (nach Vorauszahlungen ${eur0(r.vorauszahlung_bisher)}) · zurückgelegt</div>
      <div class="row" style="align-items:center;margin:4px 0 10px"><div class="prog ${pct < 60 ? "b" : pct < 100 ? "w" : ""}" style="flex:3"><div style="width:${pct}%"></div></div>
        <b class="num" style="flex:none">${eur0(r.zurueckgelegt.betrag || 0)} / ${eur0(r.soll_netto)}</b></div>
      ${compact ? "" : `<div class="kv small" style="margin-bottom:8px">
        <span class="sub">Einkommensteuer gesamt (hochgerechnet)</span><span class="r">${eur(r.steuer_gesamt_jahr)}</span>
        <span class="sub">− Lohnsteuer/Soli/KiSt aus Gehalt${r.gehalt_faktor > 1 ? ` (×${nde(r.gehalt_faktor, 2)} aufs Jahr)` : ""}</span><span class="r">− ${eur(r.lohnsteuer_jahr)}</span>
        <span class="sub">− Vorauszahlungen ${r.year}</span><span class="r">− ${eur(r.vorauszahlung_jahr)}</span>
        <span class="tot">${r.nachzahlung_erwartet >= 0 ? "Erwartete Nachzahlung" : "Erwartete Erstattung"}</span><span class="r tot">${eur(Math.abs(r.nachzahlung_erwartet))}</span>
        <span class="sub">Grenzsteuersatz ca.</span><span class="r">${nde(r.grenzsteuersatz, 1)} %</span>
        <span class="sub">Basis</span><span class="r">${esc(r.basis)} (${nde(r.anteil_vergangen, 0)} % des Jahres)</span></div>`}
      ${(r.hinweise || []).map(h => `<div class="alert ${STC[h.stufe] || ""}" style="cursor:default;margin-top:6px;font-size:12.5px">${ic("alert")}<span>${esc(h.text)}</span></div>`).join("")}
      <div class="small muted" style="margin-top:8px">${esc(r.hinweis)}</div>`;
  }

  async function fillDash(card){
    const r = await api("/api/m54/ruecklage", undefined, {quiet:true});
    if (!r || r.monat === undefined) { card.remove(); return; }
    card.innerHTML = `<div class="hd"><h3>Steuer-Rücklage live</h3><div class="act"><button class="btn sm" id="m54e" type="button">Zurückgelegt eintragen</button>
      <button class="btn sm ghost" type="button" data-go="tax">Details</button></div></div><div class="bd">${body(r, true)}</div>`;
    $("#m54e", card).onclick = () => enter(r, () => fillDash(card));
    bindCommon(card);
  }

  EXT.dash.push(el => {
    const card = document.createElement("div"); card.className = "card"; card.id = "m54card";
    card.innerHTML = `<div class="hd"><h3>Steuer-Rücklage live</h3></div><div class="bd small muted">Lädt …</div>`;
    (window.m5xRow ? window.m5xRow(el) : el).appendChild(card);   // shared row helper from m52
    fillDash(card);
  });

  EXT.after.push(async n => {
    if (n !== "vTax") return;
    const page = $("#main .page"); if (!page || $("#m54tax", page)) return;
    const y = typeof txYear !== "undefined" ? txYear : new Date().getFullYear();
    const card = document.createElement("div"); card.className = "card"; card.id = "m54tax"; card.style.marginBottom = "16px";
    card.innerHTML = `<div class="hd"><h3>Steuer-Rücklage ${y} (live)</h3></div><div class="bd small muted">Lädt …</div>`;
    const kpis = page.querySelector(".grid.g4");
    if (kpis && kpis.nextSibling) page.insertBefore(card, kpis.nextSibling); else page.appendChild(card);
    const draw = async () => {
      const r = await api("/api/m54/ruecklage?year=" + y, undefined, {quiet:true});
      if (!r || r.monat === undefined) { card.remove(); return; }
      card.innerHTML = `<div class="hd"><h3>Steuer-Rücklage ${y} (live)</h3><div class="act"><button class="btn sm" id="m54e2" type="button">Zurückgelegt eintragen</button></div></div>
        <div class="bd">${body(r, false)}</div>`;
      card.style.marginBottom = "16px";
      $("#m54e2", card).onclick = () => enter(r, draw);
    };
    draw();
  });
})();
