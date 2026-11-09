// Pfeiffer-Audio Rechnung v2.0.0 - UI-Modul m51_gobd: Aenderungsprotokoll (GoBD) + Verfahrensdokumentation
// Einstellungs-Reiter "Protokoll (GoBD)" mit Filter, Suche, Pruefung der Hash-Kette und Export.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  if (!document.getElementById("m5xcss")) { const st = document.createElement("style"); st.id = "m5xcss";
    st.textContent = ".alert > svg + span{flex:1;min-width:0}"; document.head.appendChild(st); }
  const F = {bereich:"", aktion:"", von:"", bis:"", q:""};
  let rows = [], total = 0, bereiche = [];
  const AKT = ["angelegt", "geändert", "gelöscht"];

  async function load(el, more){
    const p = new URLSearchParams(Object.assign({}, F, {limit: 300, offset: more ? rows.length : 0}));
    const r = await api("/api/m51/log?" + p.toString());
    rows = more ? rows.concat(r.rows || []) : (r.rows || []);
    total = r.total || 0; bereiche = r.bereiche || bereiche;
    draw(el);
  }

  function short(v){ v = String(v ?? ""); return v.length > 120 ? v.slice(0, 120) + " …" : v; }

  function draw(el){
    const tb = $("#m51tb", el); if (!tb) return;
    tb.innerHTML = rows.map(r => `<tr><td class="num" style="white-space:nowrap">${esc(dde(r.zeit))} ${esc((r.zeit || "").slice(11, 16))}</td>
      <td>${esc(r.bereich)}${r.datensatz_id != null ? ` <span class="muted small">#${r.datensatz_id}</span>` : ""}</td>
      <td><span class="badge ${r.aktion === "gelöscht" ? "bad" : r.aktion === "angelegt" ? "ok" : "warn"}">${esc(r.aktion)}</span></td>
      <td>${esc(r.feld || "")}</td><td class="small" title="${esc(r.alt || "")}">${esc(short(r.alt))}</td><td class="small" title="${esc(r.neu || "")}">${esc(short(r.neu))}</td>
      <td class="small muted">${esc(r.info || "")}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">Keine Einträge.</td></tr>`;
    $("#m51cnt", el).textContent = `${rows.length} von ${total} Einträgen`;
    $("#m51more", el).style.display = rows.length >= total ? "none" : "";
    const bs = $("#m51b", el);
    if (bs && bs.options.length <= 1) bs.innerHTML = `<option value="">Alle Bereiche</option>` + bereiche.map(b => `<option ${b === F.bereich ? "selected" : ""}>${esc(b)}</option>`).join("");
  }

  async function doku(){
    await modal("Verfahrensdokumentation erzeugen", `<div class="fr nokeep">
      <div class="small muted" style="margin-bottom:8px">Erzeugt eine Vorlage der Verfahrensdokumentation nach GoBD als PDF (Ordner Export): Unternehmen, Belegfluss,
        Nummernkreise, Festschreibung, Datensicherung, Aufbewahrung, Zugriffsschutz, Änderungsprotokoll und internes Kontrollsystem.
        <b>Die Vorlage ist von dir zu prüfen, anzupassen und zu unterschreiben.</b></div>
      <label class="f">Eigene Ergänzungen (optional, erscheinen als eigener Abschnitt)<textarea class="in" id="m51not" rows="5" placeholder="z. B. Papierbelege werden nach dem Scannen im Ordner 2026 aufbewahrt."></textarea></label></div>`,
      [{label:"Abbrechen"}, {label:"PDF erzeugen", cls:"pri", onClick: async mb => {
        const r = await api("/api/m51/verfahrensdoku", {notiz: $("#m51not", mb).value});
        if (!r || !r.ok) return false;
        toast("Verfahrensdokumentation gespeichert: " + r.path.split(/[\\/]/).pop());
      }}]);
  }

  EXT.settings.push({key:"m51", label:"Protokoll (GoBD)", async render(el){
    el.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>Änderungsprotokoll (GoBD)</h3>
        <div class="act">${expButtons("gobd_log", () => Object.assign({}, F), true)}<button class="btn sm" id="m51ver" type="button">Integrität prüfen</button>
        <button class="btn sm pri" id="m51doc" type="button">${ic("pdf")} Verfahrensdokumentation</button></div></div>
      <div class="bd">
        <div class="small muted" style="margin-bottom:10px">Alle Änderungen an Rechnungen, Positionen, Belegen, Kunden und Bank-Zuordnungen werden automatisch protokolliert.
          Das Protokoll ist nur anfügbar (Löschen/Ändern technisch gesperrt) und über eine Hash-Kette gegen Manipulation gesichert.</div>
        <div class="row nokeep" style="align-items:flex-end;margin-bottom:10px">
          <label class="f" style="flex:.8">Bereich<select class="in" id="m51b"><option value="">Alle Bereiche</option></select></label>
          <label class="f" style="flex:.7">Aktion<select class="in" id="m51a"><option value="">Alle</option>${AKT.map(a => `<option>${a}</option>`).join("")}</select></label>
          <label class="f" style="flex:.7">Von<input type="date" class="in" id="m51v"></label>
          <label class="f" style="flex:.7">Bis<input type="date" class="in" id="m51e"></label>
          <label class="f">Suche<input class="in" id="m51q" placeholder="Rechnungsnummer, Kunde, Wert …"></label>
        </div>
        <div id="m51res"></div>
        <div style="overflow:auto;max-height:560px"><table class="t"><thead><tr><th>Zeit</th><th>Bereich</th><th>Aktion</th><th>Feld</th><th>Alt</th><th>Neu</th><th>Kurzinfo</th></tr></thead>
          <tbody id="m51tb"><tr><td colspan="7" class="empty">Lädt …</td></tr></tbody></table></div>
        <div class="row" style="margin-top:8px;align-items:center"><span class="small muted" id="m51cnt"></span><span class="sp"></span>
          <button class="btn sm" id="m51more" type="button" style="display:none">Weitere laden</button></div>
      </div></div>`;
    let tmr = null;
    const upd = () => { F.bereich = $("#m51b", el).value; F.aktion = $("#m51a", el).value; F.von = $("#m51v", el).value; F.bis = $("#m51e", el).value; F.q = $("#m51q", el).value.trim();
      clearTimeout(tmr); tmr = setTimeout(() => load(el, false), 250); };
    ["#m51b", "#m51a", "#m51v", "#m51e"].forEach(s => $(s, el).onchange = upd);
    $("#m51q", el).oninput = upd;
    $("#m51more", el).onclick = () => load(el, true);
    $("#m51doc", el).onclick = doku;
    $("#m51ver", el).onclick = async () => { const r = await api("/api/m51/verify");
      $("#m51res", el).innerHTML = `<div class="alert ${r.ok ? "" : "bad"}" style="cursor:default;margin-bottom:10px">${ic(r.ok ? "check" : "alert")}<span>${esc(r.text || "")}</span></div>`; };
    await load(el, false);
  }});
})();
