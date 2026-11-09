// Pfeiffer-Audio Rechnung v2.0.0 - UI-Modul m53_liquiditaet: Liquiditaetsvorschau (Finanzen)
// Kontostand + erwartete Zahlungen fuer ca. 3 Monate, SVG-Kurve, Ereignistabelle, Mindestreserve.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  if (!document.getElementById("m5xcss")) { const st = document.createElement("style"); st.id = "m5xcss";
    st.textContent = ".alert > svg + span{flex:1;min-width:0}"; document.head.appendChild(st); }
  IC.m53 = IC.m53 || '<path d="M3 17l5-5 4 3 8-9"/><path d="M15 6h5v5"/><path d="M3 21h18"/>';
  const ST = {sicher:false, ruecklage:null, start:"", tab:"ev"};

  EXT.nav.push({key:"liq", label:"Liquidität", icon:"m53", section:"Finanzen"});

  function kfmt(v){ const a = Math.abs(v); return (v < 0 ? "−" : "") + (a >= 1000 ? (Math.round(a / 100) / 10).toLocaleString("de-DE") + "k" : Math.round(a)); }

  function liqChart(d, h=220){
    const W = 760, pad = 46, ser = d.series; if (!ser.length) return "";
    const vals = ser.map(p => p.saldo).concat([d.min_reserve || 0, 0]);
    let mx = Math.max(...vals), mn = Math.min(...vals);
    if (mx === mn) mx = mn + 1;
    const lowest = mn, span = mx - mn; mx += span * .06; mn = lowest >= 0 ? 0 : mn - span * .06;
    const X = i => pad + (W - pad - 6) * i / Math.max(1, ser.length - 1);
    const Y = v => 4 + h - (v - mn) / (mx - mn) * h;
    let s = `<svg class="chart" viewBox="0 0 ${W} ${h + 26}" width="100%" style="display:block;max-height:${h + 60}px">`;
    for (let k = 0; k <= 4; k++) { const v = mn + (mx - mn) * k / 4, y = Y(v);
      s += `<line x1="${pad}" x2="${W}" y1="${y}" y2="${y}" stroke="#eeebf4"/><text x="${pad - 6}" y="${y + 4}" text-anchor="end">${kfmt(v)}</text>`; }
    if (mn < 0 && mx > 0) s += `<line x1="${pad}" x2="${W}" y1="${Y(0)}" y2="${Y(0)}" stroke="#bdb6cc"/>`;
    if (d.min_reserve) s += `<line x1="${pad}" x2="${W}" y1="${Y(d.min_reserve)}" y2="${Y(d.min_reserve)}" stroke="var(--bad)" stroke-dasharray="5 4" stroke-width="1.2"><title>Mindestreserve ${eur(d.min_reserve)}</title></line>`;
    // month labels
    ser.forEach((p, i) => { if (p.d.slice(8) === "01" || i === 0) s += `<line x1="${X(i)}" x2="${X(i)}" y1="4" y2="${h + 4}" stroke="#f3f1f8"/><text x="${X(i) + 3}" y="${h + 20}">${MON[+p.d.slice(5, 7) - 1]}${i === 0 ? " " + p.d.slice(8) + "." : ""}</text>`; });
    const pts = ser.map((p, i) => `${X(i).toFixed(1)},${Y(p.saldo).toFixed(1)}`);
    s += `<path d="M${X(0)},${Y(Math.max(mn, Math.min(0, mx)))} L${pts.join(" L")} L${X(ser.length - 1)},${Y(Math.max(mn, Math.min(0, mx)))} Z" fill="var(--acc)" opacity=".08"/>`;
    s += `<polyline points="${pts.join(" ")}" fill="none" stroke="var(--acc)" stroke-width="2.2" stroke-linejoin="round"/>`;
    const byDay = {}; d.events.forEach(e => { (byDay[e.datum] = byDay[e.datum] || []).push(e); });
    ser.forEach((p, i) => { const ev = byDay[p.d]; if (!ev) return;
      const sum = ev.reduce((a, e) => a + e.betrag, 0);
      s += `<circle cx="${X(i)}" cy="${Y(p.saldo)}" r="3.6" fill="${sum >= 0 ? "var(--ok)" : "var(--bad)"}" stroke="#fff" stroke-width="1.2"><title>${dde(p.d)}: ${eur(p.saldo)}\n${ev.map(e => (e.betrag >= 0 ? "+" : "") + eur(e.betrag) + "  " + esc(e.text)).join("\n")}</title></circle>`; });
    const mi = ser.findIndex(p => p.d === d.min.datum);
    if (mi >= 0) s += `<circle cx="${X(mi)}" cy="${Y(d.min.saldo)}" r="5.5" fill="none" stroke="var(--bad)" stroke-width="1.6"><title>Tiefster Stand ${eur(d.min.saldo)} am ${dde(d.min.datum)}</title></circle>`;
    return s + `</svg>`;
  }

  async function settings(d){
    const c = d.cfg || {};
    await modal("Liquidität – Einstellungen", `<div class="fr">
      <div class="row"><label class="f">Mindestreserve €<input class="in num" id="m53r" value="${nde(c.min_reserve || 0)}"></label>
        <label class="f">Zeitraum (Tage)<input class="in num" id="m53t" value="${c.tage || 92}"></label></div>
      <div class="row"><label class="f">Gehalt netto / Monat € (0 = aus Abrechnungen)<input class="in num" id="m53g" value="${nde(c.gehalt_netto || 0)}"></label>
        <label class="f" style="flex:.6">Zahltag (0 = automatisch)<input class="in num" id="m53gt" value="${c.gehalt_tag || 0}"></label></div>
      <div class="row"><label class="f">Private Ausgaben / Monat € (Miete, Leben)<input class="in num" id="m53p" value="${nde(c.privat_monat || 0)}"></label>
        <label class="f" style="flex:.6">am Tag<input class="in num" id="m53pt" value="${c.privat_tag || 1}"></label></div>
      <label class="small" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="m53rl" ${c.ruecklage ? "checked" : ""}> Steuer-Rücklage monatlich abziehen (Standard)</label>
      <div class="small muted" style="margin-top:8px">Erkannt: Gehalt ${eur(d.gehalt.netto)} am ${d.gehalt.tag || "–"}. (${esc(d.gehalt.quelle)}) · Fixkosten: ${esc(d.fixkosten_quelle)} ·
        Zahlungsverhalten: Kunden zahlen im Schnitt ${d.zahlverhalten.durchschnitt_tage} Tage nach Fälligkeit (${d.zahlverhalten.rechnungen} Rechnungen).</div></div>`,
      [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
        const r = await api("/api/m53/cfg", {min_reserve: pnum($("#m53r", mb).value), tage: parseInt($("#m53t", mb).value) || 92,
          gehalt_netto: pnum($("#m53g", mb).value), gehalt_tag: parseInt($("#m53gt", mb).value) || 0, privat_monat: pnum($("#m53p", mb).value),
          privat_tag: parseInt($("#m53pt", mb).value) || 1, ruecklage: $("#m53rl", mb).checked});
        if (!r || !r.ok) return false;
        ST.ruecklage = null; EXT.views.liq();
      }}]);
  }

  EXT.views.liq = async function(){
    const qs = new URLSearchParams({sicher: ST.sicher ? "1" : "0"});
    if (ST.ruecklage !== null) qs.set("ruecklage", ST.ruecklage ? "1" : "0");
    if (ST.start !== "") qs.set("start", ST.start);
    $("#main").innerHTML = `<div class="page">${pageHead("Liquidität", "Vorschau wird berechnet …", "")}</div>`;
    const d = await api("/api/m53/liquiditaet?" + qs.toString());
    if (!d || !d.series) return;
    if (view !== "liq") return;
    const days = d.series.length - 1;
    const rl = ST.ruecklage === null ? d.ruecklage : ST.ruecklage;
    let run = d.start;
    const evRows = d.events.filter(e => e.datum >= d.stichtag && e.datum <= d.series[d.series.length - 1].d).map(e => { run += e.betrag;
      return `<tr ${e.link && e.link.inv ? `class="click" data-inv="${e.link.inv}"` : ""}><td class="num">${dde(e.datum)}</td><td>${esc(e.art)}</td><td>${esc(e.text)}</td>
        <td>${e.sicher ? `<span class="badge ok">sicher</span>` : `<span class="badge warn">erwartet</span>`}</td>
        <td class="r num" style="color:${e.betrag < 0 ? "var(--bad)" : "var(--ok)"}">${e.betrag > 0 ? "+" : ""}${eur(e.betrag)}</td><td class="r num">${eur(run)}</td></tr>`; }).join("");
    const wkRows = d.weeks.map(w => `<tr><td class="num">${dde(w.von)} – ${dde(w.bis)}</td><td class="r num" style="color:var(--ok)">${w.ein ? "+" + eur(w.ein) : ""}</td>
      <td class="r num" style="color:var(--bad)">${w.aus ? eur(w.aus) : ""}</td><td class="r num" style="${w.saldo < d.min_reserve ? "color:var(--bad);font-weight:600" : ""}">${eur(w.saldo)}</td></tr>`).join("");
    $("#main").innerHTML = `<div class="page">
      ${pageHead("Liquidität", `Vorschau ${days} Tage ab ${dde(d.stichtag)} · Start: ${esc(d.start_info)}`,
        `<div class="seg nokeep" id="m53seg"><button class="${ST.sicher ? "" : "on"}" data-s="0">Alle Posten</button><button class="${ST.sicher ? "on" : ""}" data-s="1" title="Kundenzahlungen werden ignoriert – nur Gehalt und alle Ausgaben">Nur sichere Posten</button></div>
         <label class="small nokeep" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="m53rlc" ${rl ? "checked" : ""}> Rücklage abziehen</label>
         <button class="btn" id="m53st" type="button" title="Startwert für diese Vorschau überschreiben">Startwert</button>
         <button class="btn" id="m53set" type="button">${ic("set")} Einstellungen</button>`)}
      ${(d.warnungen || []).map(w => `<div class="alert bad" style="cursor:default;margin-bottom:10px">${ic("alert")}<span>${esc(w)}</span></div>`).join("")}
      <div class="grid g4" style="margin-bottom:16px">
        <div class="card kpi"><div class="l">Startwert</div><div class="v">${eur(d.start)}</div><div class="s">${esc(d.start_info)}</div></div>
        <div class="card kpi"><div class="l">Tiefster Stand</div><div class="v" style="color:${d.min.saldo < d.min_reserve ? "var(--bad)" : "inherit"}">${eur(d.min.saldo)}</div><div class="s">am ${dde(d.min.datum)} · Reserve ${eur0(d.min_reserve)}</div></div>
        <div class="card kpi"><div class="l">Ein / Aus</div><div class="v" style="font-size:18px"><span style="color:var(--ok)">+${eur0(d.summe_ein)}</span> / <span style="color:var(--bad)">${eur0(d.summe_aus)}</span></div><div class="s">${ST.sicher ? "nur sichere Posten" : "alle erwarteten Posten"}</div></div>
        <div class="card kpi acc"><div class="l">Stand in ${days} Tagen</div><div class="v">${eur(d.ende)}</div><div class="s">${rl ? `inkl. Rücklage ${eur0(d.ruecklage_monat)}/Monat` : "ohne Rücklage"}</div></div>
      </div>
      <div class="card" style="margin-bottom:16px"><div class="hd"><h3>Kontostand-Verlauf</h3><div class="act legend"><span><i style="background:var(--acc)"></i>Kontostand</span>
        <span><i style="background:var(--ok)"></i>Eingang</span><span><i style="background:var(--bad)"></i>Ausgang / Mindestreserve</span></div></div>
        <div class="bd">${liqChart(d)}</div></div>
      <div class="tabs nokeep"><div class="tab ${ST.tab === "ev" ? "on" : ""}" data-t="ev">Ereignisse<span class="cnt">${d.events.length}</span></div><div class="tab ${ST.tab === "wk" ? "on" : ""}" data-t="wk">Wochen<span class="cnt">${d.weeks.length}</span></div></div>
      <div class="card" style="overflow:hidden">${ST.tab === "ev"
        ? `<table class="t"><thead><tr><th>Datum</th><th>Art</th><th>Beschreibung</th><th></th><th class="r">Betrag</th><th class="r">Kontostand</th></tr></thead><tbody>${evRows || `<tr><td colspan="6" class="empty">Keine erwarteten Zahlungen im Zeitraum.</td></tr>`}</tbody></table>`
        : `<table class="t"><thead><tr><th>Woche</th><th class="r">Eingänge</th><th class="r">Ausgänge</th><th class="r">Kontostand Wochenende</th></tr></thead><tbody>${wkRows}</tbody></table>`}</div>
      <div class="small muted" style="margin-top:10px">Annahmen: offene Rechnungen am Fälligkeitstag, verschoben um das bisherige Zahlungsverhalten des Kunden (überfällige in 7 Tagen);
        Abo-, Wartungs- und Unterrichtsrechnungen nach Plan bzw. Durchschnitt; Gehalt aus den Abrechnungen; Fixkosten (${esc(d.fixkosten_quelle)}); ESt-Vorauszahlungen am 10.03./06./09./12.;
        Rücklage am Monatsersten. „Nur sichere Posten“ ignoriert alle Kundenzahlungen. Schätzung – keine Garantie.</div>
    </div>`;
    bindCommon();
    $$("#m53seg [data-s]").forEach(b => b.onclick = () => { ST.sicher = b.dataset.s === "1"; EXT.views.liq(); });
    $("#m53rlc").onchange = e => { ST.ruecklage = e.target.checked; EXT.views.liq(); };
    $$(".tabs [data-t]").forEach(t => t.onclick = () => { ST.tab = t.dataset.t; EXT.views.liq(); });
    $("#m53set").onclick = () => settings(d);
    $("#m53st").onclick = async () => {
      const v = await modal("Startwert", `<div class="fr nokeep"><label class="f">Kontostand für diese Vorschau €<input class="in num" id="m53sv" value="${ST.start !== "" ? esc(ST.start) : nde(d.start)}"></label>
        <div class="small muted">Leer lassen = erfasster Kontostand. Dauerhaft wird der Kontostand im Dashboard oder über den Bank-Abgleich gepflegt.</div></div>`,
        [{label:"Zurücksetzen", value:"__reset"}, {label:"Übernehmen", cls:"pri", onClick: mb => { ST.start = String(pnum($("#m53sv", mb).value)); }, value:"ok"}]);
      if (v === "__reset") ST.start = "";
      if (v) EXT.views.liq();
    };
  };
})();
