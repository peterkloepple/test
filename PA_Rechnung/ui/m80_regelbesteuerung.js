// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m80_regelbesteuerung: Umschaltung auf Regelbesteuerung
// Einstellungs-Reiter "Umsatzsteuer" (Stichtag, Was-waere-wenn), UStVA + Vorsteuer in "Jahresabrechnung & Steuer",
// USt-Satz je Position im Editor (nur ab Stichtag), Hinweise auf der Uebersicht.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  if (!document.getElementById("m80css")) { const st = document.createElement("style"); st.id = "m80css";
    st.textContent = `.m80ust{display:flex;gap:6px;align-items:center;margin-bottom:4px;font-size:12px;color:var(--mut,#6b6478)}
      .m80ust select{width:auto;padding:0 6px;height:26px;font-size:12px;line-height:24px}
      .m80sum{display:grid;grid-template-columns:1fr auto;gap:2px 16px;padding:6px 10px 10px;font-size:12.5px;justify-items:end}
      .m80sum span:nth-child(odd){justify-self:end;color:var(--mut,#6b6478)}`;
    document.head.appendChild(st); }
  const pct = v => (Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)) : nde(v, 1)) + " %";
  const m80 = () => (S && S.m80) || {ab: "", satz: 19};

  function curRegel(){
    if (!cur) return false;
    const typ = cur.typ || "rechnung";
    if (!["rechnung", "storno", "angebot", "auftrag"].includes(typ)) return false;
    if (cur.ust_modus === "regel") return true;
    if (cur.ust_modus === "ku") return false;
    if (cur.locked) return false;
    const ab = m80().ab; if (!ab) return false;
    return String(cur.datum || todayIso()).slice(0, 10) >= ab;
  }
  const itemSatz = it => (it.ust_satz === undefined || it.ust_satz === null || it.ust_satz === "") ? +m80().satz : +it.ust_satz;

  function block(){
    const by = {};
    (cur.items || []).forEach(it => { const s = itemSatz(it); by[s] = Math.round(((by[s] || 0) + lineTotal(it)) * 100) / 100; });
    const saetze = Object.keys(by).map(Number).sort((a, b) => b - a).map(s => ({satz: s, netto: by[s], ust: Math.round(by[s] * s) / 100}));
    const netto = saetze.reduce((a, r) => a + r.netto, 0), ust = saetze.reduce((a, r) => a + r.ust, 0);
    return {saetze, netto: Math.round(netto * 100) / 100, ust: Math.round(ust * 100) / 100, brutto: Math.round((netto + ust) * 100) / 100};
  }

  function drawSum(){
    const pos = $("#pos"); if (!pos) return;
    let el = $("#m80sum", pos);
    if (!curRegel()) { if (el) el.remove(); return; }
    const b = block();
    if (!el) { el = document.createElement("div"); el.id = "m80sum"; el.className = "m80sum"; pos.appendChild(el); }
    el.innerHTML = `<span>Nettobetrag</span><b class="num">${eur(b.netto)}</b>` +
      b.saetze.map(r => `<span>${r.satz ? "zzgl. USt " + pct(r.satz) : "USt 0 %"}</span><span class="num">${eur(r.ust)}</span>`).join("") +
      `<span><b>Gesamtbetrag (brutto)</b></span><b class="num">${eur(b.brutto)}</b>`;
    const sv = $("#sumv"); if (sv) sv.textContent = eur(b.netto) + " netto";
  }

  // ------------------------------------------------------------------ editor: USt rate per position
  const origRP = window.renderPositions;
  if (typeof origRP === "function") {
    window.renderPositions = function(...a){
      const r = origRP.apply(this, a);
      try {
        if (curRegel()) {
          const ro = !!cur.locked;
          $$("#pos .posrow:not(.head)").forEach(row => {
            const i = +row.dataset.i, it = cur.items[i]; if (!it) return;
            const dsc = $(".dsc", row); if (!dsc || $(".m80ust", dsc)) return;
            const s = itemSatz(it);
            const opts = [19, 7, 0]; if (!opts.includes(s)) opts.push(s);
            const w = document.createElement("div"); w.className = "m80ust";
            w.innerHTML = `USt <select class="in nokeep" ${ro ? "disabled" : ""}>${opts.map(v => `<option value="${v}" ${v === s ? "selected" : ""}>${pct(v)}</option>`).join("")}</select>`;
            $("select", w).onchange = e => { it.ust_satz = +e.target.value; drawSum(); if (typeof schedulePreview === "function") schedulePreview(); };
            dsc.insertBefore(w, dsc.firstChild);
          });
          $$("#pos [data-f]").forEach(inp => inp.addEventListener("input", () => setTimeout(drawSum, 0)));
        }
        drawSum();
      } catch (e) { console.error(e); }
      return r;
    };
  }
  // datum change in the editor may cross the Stichtag
  document.addEventListener("change", e => { if (e.target && e.target.id === "datum" && m80().ab && $("#pos")) { try { window.renderPositions(); } catch (e2) {} } });

  // ------------------------------------------------------------------ Vorsteuer dialog
  async function vstDialog(after){
    const d = await api("/api/m80/vst");
    if (!d) return;
    if (!d.ab) { toast("Erst in den Einstellungen → Umsatzsteuer einen Stichtag eintragen.", true); return; }
    const html = `<div class="small muted" style="margin-bottom:8px">Ausgaben ab ${dde(d.ab)}. Vorsteuer = die in der Eingangsrechnung ausgewiesene USt. „Erkennen“ liest sie aus dem PDF-Text.</div>
      <div style="max-height:460px;overflow:auto"><table class="t"><thead><tr><th>Datum</th><th>Partner</th><th>Kategorie</th><th class="r">Brutto</th><th style="width:120px">Vorsteuer €</th><th>Quelle</th></tr></thead>
      <tbody>${d.rows.map(r => `<tr data-id="${r.id}"><td>${dde(r.datum)}</td><td>${esc(r.partner || "")}<div class="small muted">${esc(r.nr || "")}</div></td><td class="small">${esc(r.kategorie || "")}</td>
        <td class="r num">${eur(r.betrag)}</td><td><input class="in num" data-vst value="${r.vorsteuer === null || r.vorsteuer === undefined || r.vorsteuer === "" ? "" : nde(r.vorsteuer)}" placeholder="–"></td>
        <td class="small muted">${esc(r.vst_quelle || "")}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Keine Ausgaben ab dem Stichtag.</td></tr>`}</tbody></table></div>`;
    await modal("Vorsteuer aus Eingangsrechnungen", html, [{label:"Schließen"},
      {label:"Vorsteuer erkennen (leere Felder)", cls:"ghost", onClick: async mb => {
        const r = await api("/api/m80/vst_detect", {});
        if (r && r.ok) { toast(`${r.erkannt} von ${r.geprueft} Belegen erkannt`); (r.rows || []).forEach(x => { const i = $(`tr[data-id="${x.id}"] [data-vst]`, mb); if (i) i.value = nde(x.vorsteuer); }); }
        return false; }},
      {label:"Speichern", cls:"pri", onClick: async mb => {
        let n = 0;
        for (const tr of $$("tr[data-id]", mb)) {
          const v = $("[data-vst]", tr).value.trim(), old = d.rows.find(r => r.id == tr.dataset.id);
          const ov = old && old.vorsteuer !== null && old.vorsteuer !== undefined && old.vorsteuer !== "" ? nde(old.vorsteuer) : "";
          if (v === ov) continue;
          const r = await api("/api/m80/vst", {id: +tr.dataset.id, vorsteuer: v === "" ? null : pnum(v)});
          if (!r || !r.ok) return false; n++;
        }
        toast(n ? `${n} Beleg(e) gespeichert` : "Keine Änderungen"); if (after) after(); }}], true);
  }

  // ------------------------------------------------------------------ UStVA card (vTax)
  async function fillUstva(card, y){
    const u = await api("/api/m80/ustva?year=" + y, undefined, {quiet:true});
    if (!u || !u.perioden) { card.remove(); return; }
    const act = u.perioden.filter(p => p.aktiv);
    card.innerHTML = `<div class="hd"><h3>Umsatzsteuer-Voranmeldung ${y}</h3><div class="act">${expButtons("m80_ustva", {year:y}, true)}
        <button class="btn sm" type="button" id="m80vst">Vorsteuer erfassen</button></div></div>
      <div class="bd">
        <div class="small muted" style="margin-bottom:8px">Regelbesteuerung ab ${dde(u.ab)} · ${u.ist ? "Ist" : "Soll"}-Versteuerung · ${{monat:"monatlich", quartal:"vierteljährlich", jahr:"jährlich"}[u.zeitraum]}${u.dfv ? " · Dauerfristverlängerung" : ""}</div>
        <table class="t"><thead><tr><th>Zeitraum</th><th class="r">Kz 81 (19 %)</th><th class="r">USt 19 %</th><th class="r">Kz 86 (7 %)</th><th class="r">USt 7 %</th><th class="r">Kz 66 Vorsteuer</th><th class="r">Kz 83 Zahllast</th><th>Fällig</th></tr></thead>
        <tbody>${u.perioden.map(p => `<tr class="${p.aktiv ? "" : "muted"}"><td><b>${esc(p.periode)}</b><div class="small muted">${p.rechnungen} Rechn. · ${p.belege_vst} Belege</div></td>
          <td class="r num">${p.aktiv ? eur0(p.kz81) : "–"}</td><td class="r num">${p.aktiv ? eur(p.ust81) : "–"}</td><td class="r num">${p.aktiv ? eur0(p.kz86) : "–"}</td><td class="r num">${p.aktiv ? eur(p.ust86) : "–"}</td>
          <td class="r num">${p.aktiv ? eur(p.kz66) : "–"}</td><td class="r num"><b>${p.aktiv ? eur(p.kz83) : "–"}</b></td>
          <td>${p.aktiv ? (p.ueberfaellig ? `<span class="badge bad" title="Frist abgelaufen - abgegeben?"><span class="dot"></span>${dde(p.faellig)}</span>` : p.bald ? `<span class="badge warn" title="bald fällig"><span class="dot"></span>${dde(p.faellig)}</span>` : dde(p.faellig)) : ""}</td></tr>`).join("")}
          ${act.length > 1 ? `<tr><td><b>Summe</b></td><td class="r num">${eur0(u.summe.kz81)}</td><td class="r num">${eur(u.summe.ust81)}</td><td class="r num">${eur0(u.summe.kz86)}</td><td class="r num">${eur(u.summe.ust86)}</td><td class="r num">${eur(u.summe.kz66)}</td><td class="r num"><b>${eur(u.summe.kz83)}</b></td><td></td></tr>` : ""}</tbody></table>
        <div class="small muted" style="margin-top:8px">${esc(u.hinweis)}</div></div>`;
    $("#m80vst", card).onclick = () => vstDialog(() => fillUstva(card, y));
  }

  EXT.after.push(async n => {
    if (n !== "vTax" || !m80().ab) return;
    const page = $("#main .page"); if (!page || $("#m80uv", page)) return;
    const y = typeof txYear !== "undefined" ? txYear : new Date().getFullYear();
    if (String(y) < m80().ab.slice(0, 4)) return;
    const c = document.createElement("div"); c.className = "card"; c.id = "m80uv"; c.style.marginTop = "16px";
    c.innerHTML = `<div class="hd"><h3>Umsatzsteuer-Voranmeldung ${y}</h3></div><div class="bd small muted">Lädt …</div>`;
    page.appendChild(c); fillUstva(c, y);
  });

  EXT.after.push(n => {
    if (n !== "vBelege" || !m80().ab) return;
    const act = $("#main .page .ph .act"); if (!act || $("#m80bv", act)) return;
    const b = document.createElement("button"); b.className = "btn"; b.id = "m80bv"; b.type = "button"; b.textContent = "Vorsteuer";
    b.title = "Vorsteuer der Eingangsrechnungen ab dem Stichtag erfassen"; b.onclick = () => vstDialog();
    act.insertBefore(b, act.firstChild);
  });

  // ------------------------------------------------------------------ dashboard hints
  EXT.dash.push(async el => {
    const box = document.createElement("div"); box.id = "m80dash"; el.appendChild(box);
    const goSet = () => { try { setTab = "m80"; } catch (e) {} go("set"); };
    if (m80().ab) {
      const st = await api("/api/m80/status", undefined, {quiet:true});
      if (!st) return;
      const n = st.naechste;
      if (st.geplant) box.innerHTML = `<div class="alert" style="margin-bottom:10px">${ic("alert")}<b>Regelbesteuerung ab ${dde(st.ab)}</b><span class="small">Ab diesem Tag Rechnungen mit Umsatzsteuer.${st.warnungen.length ? " " + esc(st.warnungen[0]) : ""}</span></div>`;
      else if (n) box.innerHTML = `<div class="alert ${n.ueberfaellig ? "bad" : "warn"}" style="margin-bottom:10px">${ic("alert")}<b>UStVA ${esc(n.periode)} ${n.year}: ${n.ueberfaellig ? "überfällig" : "fällig"} am ${dde(n.faellig)}</b><span class="small">Zahllast ${eur(n.kz83)} · Kz 81 ${eur0(n.kz81)} · Kz 66 ${eur(n.kz66)}</span></div>`;
      else if (st.warnungen.length) box.innerHTML = `<div class="alert warn" style="margin-bottom:10px">${ic("alert")}<b>Umsatzsteuer</b><span class="small">${esc(st.warnungen[0])}</span></div>`;
      const a = $(".alert", box); if (a) a.onclick = () => { if (n) go("tax"); else goSet(); };
      return;
    }
    const p = await api("/api/m52/prognose", undefined, {quiet:true});
    if (!p || !(p.warnungen || []).some(w => w.stufe === "kritisch" || w.stufe === "warnung")) return;
    box.innerHTML = `<div class="alert warn" style="margin-bottom:10px">${ic("alert")}<b>Kleinunternehmergrenze in Sicht</b><span class="small">Umstellung auf Regelbesteuerung vorbereiten: Stichtag, Simulation und Checkliste</span><span class="sp" style="flex:1"></span><span class="small"><u>Umsatzsteuer →</u></span></div>`;
    $(".alert", box).onclick = goSet;
  });

  // ------------------------------------------------------------------ settings tab
  function simHtml(s){
    const sc = o => `<div class="card" style="padding:10px 12px"><div class="small muted">${esc(o.titel)}</div>
      <div style="font:600 20px var(--disp);color:${o.ergebnis >= 0 ? "var(--ok,#1f9d6b)" : "var(--bad,#c0392b)"}">${o.ergebnis >= 0 ? "+" : "−"} ${eur(Math.abs(o.ergebnis))}</div>
      <div class="small">${esc(o.text)}</div></div>`;
    return `<div class="kv small" style="margin-bottom:10px"><span class="sub">Umsatz ${s.year}</span><span class="r">${eur(s.umsatz)}</span>
        <span class="sub">Anteil Privatkunden (B2C)</span><span class="r">${nde(s.b2c_anteil, 1)} %</span>
        <span class="sub">USt bei Netto-Preisen + ${nde(s.satz, 0)} %</span><span class="r">${eur(s.ust_auf_netto)}</span>
        <span class="sub">USt aus gleichen Endpreisen</span><span class="r">${eur(s.ust_aus_brutto)}</span>
        <span class="sub">Vorsteuer (Schätzung aus Ausgaben)</span><span class="r">${eur(s.vorsteuer_schaetzung)}</span>
        <span class="sub">Voranmeldung voraussichtlich</span><span class="r">${esc(s.zeitraum_vorschlag)}</span></div>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:10px">${sc(s.szenario_a)}${sc(s.szenario_b)}${sc(s.szenario_mix)}</div>
      <div class="small muted">Ergebnis = Wirkung auf deinen Gewinn im Jahr gegenüber heute.</div>
      <h4 style="margin:12px 0 6px">Checkliste für die Umstellung</h4>
      <ol class="small" style="margin:0;padding-left:18px">${s.checkliste.map(c => `<li>${esc(c)}</li>`).join("")}</ol>
      <div class="small muted" style="margin-top:8px">${esc(s.hinweis)}</div>`;
  }

  EXT.settings.push({key:"m80", label:"Umsatzsteuer", async render(el){
    const st = await api("/api/m80/status");
    if (!st || !st.cfg) return;
    const c = st.cfg;
    el.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>Kleinunternehmer / Regelbesteuerung</h3>
        <div class="act"><span class="badge ${st.aktiv ? "acc" : st.geplant ? "warn" : "ok"}"><span class="dot"></span>${st.aktiv ? "Regelbesteuerung aktiv" : st.geplant ? "Umstellung geplant" : "Kleinunternehmer (§ 19)"}</span></div></div>
      <div class="bd fr">
        <div class="small muted" style="margin-bottom:8px">Solange kein Stichtag eingetragen ist, arbeitet das Programm genau wie bisher als Kleinunternehmer.
          Ab dem Stichtag: Preise netto, USt-Satz je Position, PDF mit Netto/USt/Brutto, kein § 19-Hinweis, E-Rechnung mit Steuerkategorie S.
          Schon ausgestellte Rechnungen bleiben unverändert.</div>
        ${(st.warnungen || []).map(w => `<div class="alert warn" style="cursor:default;margin-bottom:8px;font-size:12.5px">${ic("alert")}<span>${esc(w)}</span></div>`).join("")}
        <div class="row"><label class="f">Regelbesteuerung ab (leer = Kleinunternehmer)<input type="date" class="in" id="m80ab" value="${esc(c.ab || "")}"></label>
          <label class="f">Standard-Steuersatz<select class="in" id="m80sz">${[19, 7, 0].map(v => `<option value="${v}" ${+c.satz === v ? "selected" : ""}>${v} %</option>`).join("")}</select></label></div>
        <div class="row"><label class="f">Versteuerung<select class="in" id="m80vs"><option value="ist" ${c.versteuerung === "ist" ? "selected" : ""}>Ist (nach Zahlungseingang)</option>
            <option value="soll" ${c.versteuerung === "soll" ? "selected" : ""}>Soll (nach Rechnungsdatum)</option></select></label>
          <label class="f">Voranmeldungszeitraum<select class="in" id="m80zr">${[["monat","monatlich"],["quartal","vierteljährlich"],["jahr","jährlich (keine Voranmeldung)"]].map(([k, l]) => `<option value="${k}" ${c.zeitraum === k ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
        <label class="chk"><input type="checkbox" id="m80dfv" ${c.dfv ? "checked" : ""}> Dauerfristverlängerung (Fälligkeit einen Monat später)</label>
        <div class="kv small" style="margin-top:8px"><span class="sub">Rechnungen mit USt bisher</span><span class="r">${st.rechnungen_regel}</span>
          <span class="sub">PDF-Summenblock</span><span class="r">${st.patch.ok ? "bereit" : "nicht verfügbar – " + esc(st.patch.msg)}</span></div>
        <div class="row" style="margin-top:12px">${c.ab ? `<button class="btn ghost danger" id="m80off" type="button" style="flex:none">Stichtag entfernen</button>` : ""}<span class="sp"></span>
          <button class="btn pri" id="m80sv" type="button" style="flex:none">${ic("save")} Speichern</button></div>
      </div></div>
      <div class="card" style="margin-top:16px"><div class="hd"><h3>Was wäre wenn …</h3></div><div class="bd">
        <div class="row" style="align-items:flex-end;flex-wrap:wrap"><label class="f" style="flex:none">Jahr${yearSel("m80sy", thisYear)}</label>
          <label class="f" style="flex:none;width:160px">Privatkunden-Anteil %<input class="in num nokeep" id="m80b2c" placeholder="automatisch"></label>
          <label class="f" style="flex:none">Steuersatz<select class="in nokeep" id="m80ss"><option>19</option><option>7</option></select></label>
          <button class="btn" type="button" id="m80sim" style="flex:none;margin-bottom:8px">Berechnen</button></div>
        <div id="m80simout" class="small muted" style="margin-top:12px">„Berechnen“ zeigt, wie sich die Regelbesteuerung auf das gewählte Jahr ausgewirkt hätte.</div></div></div>`;
    const save = async ab => {
      const r = await api("/api/m80/cfg", {ab, satz: $("#m80sz", el).value, versteuerung: $("#m80vs", el).value, zeitraum: $("#m80zr", el).value, dfv: $("#m80dfv", el).checked});
      if (r && r.ok) { toast(ab ? `Regelbesteuerung ab ${dde(ab)} gespeichert` : "Kleinunternehmer – Stichtag entfernt"); await reload(); this.render(el); }
    };
    $("#m80sv", el).onclick = () => save($("#m80ab", el).value);
    if ($("#m80off", el)) $("#m80off", el).onclick = () => save("");
    $("#m80sim", el).onclick = async () => {
      const b2c = $("#m80b2c", el).value.trim();
      const s = await api(`/api/m80/sim?year=${$("#m80sy", el).value}&satz=${$("#m80ss", el).value}${b2c ? "&b2c=" + pnum(b2c) : ""}`);
      if (s && s.szenario_a) { $("#m80simout", el).className = ""; $("#m80simout", el).style.marginTop = "12px"; $("#m80simout", el).innerHTML = simHtml(s); }
    };
  }});
})();
