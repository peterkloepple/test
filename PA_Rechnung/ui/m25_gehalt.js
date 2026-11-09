// PA Rechnung v2.0.0 - Gehalt: Plausibilitaet, DEUEV-Meldebescheinigung, neu einlesen
// Autor: T. Pfeiffer
(function(){
  EXT.after.push(async n => {
    if (n !== "vTax") return;
    const h = [...$$("#main .card .hd h3")].find(e => e.textContent.trim() === "2 · Gehalt"); if (!h) return;
    const card = h.closest(".card"); if (!card || card.dataset.gfix) return; card.dataset.gfix = "1";
    const t = await api("/api/tax?year=" + txYear);
    const w = t.gehalt_warnungen || [], md = t.gehalt_meldebescheinigungen || 0;
    const box = document.createElement("div"); box.style.marginTop = "10px";
    let html = "";
    if (w.length) html += `<div class="alert bad" style="cursor:default;margin-bottom:8px"><span><b>${w.length} Abrechnung(en) mit unplausiblen Sozialversicherungswerten</b> – deren Beiträge zählen nicht in die Vorsorgeaufwendungen:<br>${w.map(x=>`${dde(x.datum)} ${esc(x.partner)}: ${esc(x.grund)}`).join("<br>")}</span></div>`;
    if (md) html += `<div class="hl small" style="margin-bottom:8px">${md} DEÜV-Meldebescheinigung(en) erkannt – enthalten nur das Entgelt für die Rentenversicherung und fließen nicht in Gehalt und Steuer ein.</div>`;
    html += `<div class="small muted">Sozialversicherung (AN) = <b>${nde(t.gehalt_sv_quote,1)} %</b> vom Brutto${t.gehalt_sv_quote > 25 ? ` <span style="color:var(--bad)">– zu hoch, üblich ca. 20–21 %</span>` : t.gehalt.brutto ? " (üblich ca. 20–21 %)" : ""}</div>
      <button class="btn sm" id="gfixre" style="margin-top:8px" title="Liest unplausible Abrechnungen und Meldebescheinigungen mit dem korrigierten Leser neu ein – plausible bzw. von Hand korrigierte Werte bleiben unverändert">Unplausible Abrechnungen neu einlesen</button>`;
    box.innerHTML = html;
    $(".bd", card).appendChild(box);
    $("#gfixre", card).onclick = async () => { toast("Abrechnungen werden neu eingelesen …"); const r = await api("/api/gehalt/neu_einlesen", {alle:false});
      if (r.ok) { toast(`${r.geprueft} geprüft · ${r.geaendert} korrigiert${r.meldebescheinigungen?` · ${r.meldebescheinigungen} Meldebescheinigung(en)`:""}`); await reload(); vTax(); } };
  });
})();
