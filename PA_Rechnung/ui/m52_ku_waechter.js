// Pfeiffer-Audio Rechnung v2.0.0 - UI-Modul m52_ku_waechter: Kleinunternehmer-Prognose
// Dashboard-Karte mit Hochrechnung + Hinweis beim Speichern/Fertigstellen einer Rechnung (blockiert nicht).
// Autor: T. Pfeiffer
(function(){
  "use strict";
  if (!document.getElementById("m5xcss")) { const st = document.createElement("style"); st.id = "m5xcss";
    st.textContent = ".alert > svg + span{flex:1;min-width:0}"; document.head.appendChild(st); }
  const LS = "pa_m52_angebote";
  const lsGet = () => { try { return localStorage.getItem(LS) === "1"; } catch (e) { return false; } };
  const lsSet = v => { try { localStorage.setItem(LS, v ? "1" : "0"); } catch (e) {} };
  const STC = {ok:"ok", hinweis:"warn", warnung:"warn", kritisch:"bad"};
  const STL = {ok:"im grünen Bereich", hinweis:"im Blick behalten", warnung:"Grenze rückt näher", kritisch:"Grenze überschritten"};

  // shared two-column row for the m52/m54 dashboard cards
  window.m5xRow = window.m5xRow || function(el){
    let r = el.querySelector("#m5xrow");
    if (!r) { r = document.createElement("div"); r.id = "m5xrow"; r.className = "grid";
      r.style.cssText = "grid-template-columns:repeat(auto-fit,minmax(340px,1fr));margin-bottom:16px"; el.appendChild(r); }
    return r;
  };

  async function fill(card){
    const ang = lsGet();
    const p = await api("/api/m52/prognose?angebote=" + (ang ? "1" : "0"), undefined, {quiet:true});
    if (!p || p.prognose === undefined) { card.remove(); return; }
    const pctB = Math.min(100, p.pct_bisher), pctP = Math.min(100, p.pct_prognose);
    const bar = (pct, st) => `<div class="prog ${st === "kritisch" ? "b" : st !== "ok" ? "w" : ""}" style="flex:3"><div style="width:${pct}%"></div></div>`;
    card.innerHTML = `<div class="hd"><h3>Kleinunternehmer-Prognose ${p.year}</h3><div class="act"><span class="badge ${STC[p.stufe]}"><span class="dot"></span>${STL[p.stufe]}</span></div></div>
      <div class="bd">
        <div class="small muted">Umsatz bisher · ${nde(p.pct_bisher, 1)} % von 100.000 €</div>
        <div class="row" style="align-items:center;margin:4px 0 10px">${bar(pctB, p.stufe_bisher)}<b class="num" style="flex:none">${eur0(p.bisher)}</b></div>
        <div class="small muted">Hochrechnung Jahresende · ${nde(p.pct_prognose, 1)} % von 100.000 € · ${nde(p.pct_prognose_vj, 0)} % von 25.000 €</div>
        <div class="row" style="align-items:center;margin:4px 0 10px">${bar(pctP, p.stufe_prognose)}<b class="num" style="flex:none">${eur0(p.prognose)}</b></div>
        <div class="kv small"><span class="sub">linear nach Tagen</span><span class="r">${eur0(p.linear_tage)}</span>
          <span class="sub">linear nach Monaten</span><span class="r">${eur0(p.linear_monate)}</span>
          <span class="sub">nach Vorjahresverlauf</span><span class="r">${p.saison_vj === null ? "–" : eur0(p.saison_vj)}</span>
          <span class="sub">offene Angebote/Aufträge</span><span class="r">${eur0(p.pipeline)}</span></div>
        <label class="small" style="display:flex;gap:6px;align-items:center;margin-top:8px"><input type="checkbox" class="nokeep" id="m52ang" ${ang ? "checked" : ""}> offene Angebote/Aufträge einrechnen</label>
        ${(p.warnungen || []).map(w => `<div class="alert ${STC[w.stufe]}" style="cursor:default;margin-top:8px;font-size:12.5px">${ic("alert")}<span>${esc(w.text)}</span></div>`).join("")}
        <div class="small muted" style="margin-top:8px">${esc(p.hinweis)}</div>
      </div>`;
    $("#m52ang", card).onchange = e => { lsSet(e.target.checked); fill(card); };
  }

  EXT.dash.push(el => {
    const card = document.createElement("div"); card.className = "card"; card.id = "m52card";
    card.innerHTML = `<div class="hd"><h3>Kleinunternehmer-Prognose</h3></div><div class="bd small muted">Lädt …</div>`;
    window.m5xRow(el).appendChild(card);
    fill(card);
  });

  // hint before saving / finishing an invoice that would cross a limit (never blocks: "Trotzdem speichern")
  let okKey = null;
  const orig = window.saveInvoice;
  if (typeof orig === "function") {
    window.saveInvoice = async function(pdf, finalize=false, silent=false){
      try {
        const typ = (cur && cur.typ) || "rechnung";
        if (!silent && cur && typ === "rechnung" && (finalize || cur.status !== "entwurf") && (cur.items || []).length) {
          const summe = Math.round((cur.items || []).reduce((a, i) => a + lineTotal(i), 0) * 100) / 100;
          const key = (cur.id || "neu") + "|" + summe + "|" + (cur.datum || "");
          if (okKey !== key) {
            const r = await api("/api/m52/check", {id: cur.id, summe, datum: cur.datum, typ}, {quiet:true});
            if (r && (r.warnungen || []).length) {
              const go_ = await modal("Hinweis Kleinunternehmergrenze", `<div class="fr">${r.warnungen.map((w, i) =>
                `<div class="alert ${i === r.warnungen.length - 1 ? "" : "warn"}" style="cursor:default;margin-bottom:8px">${i === r.warnungen.length - 1 ? "" : ic("alert")}<span>${esc(w)}</span></div>`).join("")}</div>`,
                [{label:"Zurück zur Rechnung", value:false}, {label:"Trotzdem speichern", cls:"pri", value:true}]);
              if (!go_) return false;
              okKey = key;
            }
          }
        }
      } catch (e) { console.error(e); }
      return orig.apply(this, arguments);
    };
  }
})();
