// Pfeiffer-Audio Rechnung v3.8.1 - UI-Modul m58_abgleich v1.2.0: Seite "Abgleich" (System)
// PC (Hauptgeraet): gekoppelte Geraete (live/zuletzt), "Geraet koppeln" (Code), Konflikte, Protokoll.
// Mobilgeraet (iPhone/iPad/zweiter PC): "PC suchen" + Code, Live-Abgleich, Status laufend, Adressen nur fuer VPN.
// v1.1.0: PC suchen, Live-Schalter, Intervall "jede Minute", Status aktualisiert sich alle 3 s ohne die Eingaben zu stoeren.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m58 = '<path d="M4 12a8 8 0 0 1 13.7-5.6L20 9"/><path d="M20 4v5h-5"/><path d="M20 12a8 8 0 0 1-13.7 5.6L4 15"/><path d="M4 20v-5h5"/>';
  EXT.nav.push({key: "m58", label: "Abgleich", icon: "m58", section: "System", cnt: () => (S.sync && S.sync.laeuft ? "…" : "")});
  EXT.views.m58 = vSync;
  let T = null, PCS = null, SEL = "";
  const when = z => z ? `${dde(z.slice(0, 10))} ${z.slice(11, 16)}` : "–";
  const INT = [[0, "nur per Knopf / live"], [1, "jede Minute"], [5, "alle 5 Minuten"], [15, "alle 15 Minuten"], [60, "jede Stunde"], [240, "alle 4 Stunden"]];
  const dot = (col, t) => `<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${col};margin-right:6px;vertical-align:middle"></span>${t}`;

  function statusHtml(d){
    const st = d.state || {}, last = st.letzter || {}, rt = d.rt || {};
    let verb;
    if (st.laeuft) verb = dot("var(--acc)", `<b>${esc(st.text || "Abgleich läuft …")}</b>`);
    else if (rt.live) verb = dot("var(--ok)", "Live verbunden – Änderungen werden sofort ausgetauscht");
    else if (rt.erreichbar === false) verb = dot("var(--bad)", `PC nicht erreichbar${rt.naechster_s ? ` – nächster Versuch in ${rt.naechster_s} s` : ""} (wird automatisch gesucht)`);
    else if (rt.erreichbar) verb = dot("var(--warn)", "Verbunden");
    else verb = dot("var(--line)", "Noch nicht verbunden");
    const l = last.zeit ? `<span style="color:${last.ok ? "var(--ok)" : "var(--bad)"}">${last.ok ? "✓" : "✗"}</span> ${esc(when(last.zeit))} · ${esc(last.text || "")}` : "noch nicht abgeglichen";
    return `<div class="small">${verb}</div><div class="small muted" style="margin-top:4px">Zuletzt: ${l}</div>
      <div class="small muted" style="margin-top:2px">${d.offen ? `<b>${d.offen}</b> Änderung(en) auf diesem Gerät gehen gleich zum PC.` : "Alle Änderungen dieses Geräts sind beim PC."}</div>`;
  }

  function pcList(){
    if (PCS === null) return "";
    if (!PCS.length) return `<div class="small" style="color:var(--warn)">Kein PC gefunden. Ist das Gerät im selben WLAN und am PC die Schnittstelle „im Heimnetz erreichbar“ an? Sonst die Adresse unten von Hand eintragen.</div>`;
    return PCS.map(p => `<label class="row small" style="align-items:center;gap:8px;border:1px solid ${SEL === p.base ? "var(--acc)" : "var(--line)"};border-radius:8px;padding:8px;cursor:pointer;margin-bottom:6px">
      <input type="radio" name="spcsel" value="${esc(p.base)}" ${SEL === p.base ? "checked" : ""} style="flex:none">
      <span style="flex:1"><b>${esc(p.name || "PC")}</b> <span class="muted">${esc(p.base)} · v${esc(p.version || "?")}</span></span>
      ${p.pairing ? `<span style="flex:none;color:var(--ok)">bereit zum Koppeln</span>` : `<span class="muted" style="flex:none">am PC „Gerät koppeln“ drücken</span>`}</label>`).join("");
  }

  async function vSync(){
    clearTimeout(T);
    const d = await api("/api/sync"); if (!d) return;
    const c = d.cfg || {}, mob = c.rolle === "mobil" && d.gekoppelt;
    const konf = d.konflikte || [], pg = d.programm || {};
    let body = "";
    if (mob) {
      body = `<div class="grid g2" style="align-items:start">
        <div class="card"><div class="hd"><h3>${ic("m58")} Abgleich mit ${esc(c.pc_name || "PC")}</h3></div><div class="bd fr">
          <div class="row" style="align-items:center;gap:12px"><button class="btn pri" id="sjetzt">${ic("sync")} Jetzt abgleichen</button><span class="sp"></span></div>
          <div id="sstat">${statusHtml(d)}</div>
          <label class="chk"><input type="checkbox" id="slive" ${c.live !== false ? "checked" : ""}> <b>Live</b>: Änderungen sofort austauschen (PC → Gerät in 2–3 s, Gerät → PC ca. 8 s nach der letzten Eingabe)</label>
          <div class="row"><label class="f">Zusätzlich regelmäßig<select class="in" id="sauto">${INT.map(([v, l]) => `<option value="${v}" ${+c.auto_min === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
            <label class="f">Name dieses Geräts<input class="in" id="sname" value="${esc(c.name || "")}" placeholder="z. B. iPhone"></label></div>
          <label class="chk"><input type="checkbox" id="sstart" ${c.beim_start !== false ? "checked" : ""}> beim Programmstart abgleichen</label>
          <label class="chk"><input type="checkbox" id="sdat" ${c.dateien !== false ? "checked" : ""}> Dateien mit abgleichen (Belege, Rechnungs-PDFs, Projektdateien)</label>
          ${pg.selbst ? `<label class="chk"><input type="checkbox" id="sprog" ${c.programm !== false ? "checked" : ""}> Programm-Updates vom PC übernehmen</label>` : ""}
          <div class="small muted">Programm v${esc(pg.version || "")}${pg.selbst ? " – neue Versionen kommen beim Abgleich vom PC, ohne neue Installation" : ""}${(pg.defekt || []).length ? ` · auf diesem Gerät nicht startfähig: v${esc([...new Set(pg.defekt)].join(", v"))}` : ""}</div>
          <details><summary class="small" style="cursor:pointer">Adressen des PCs (werden automatisch gefunden)</summary><div class="fr" style="margin-top:8px">
            <div class="small muted">Gefunden: ${(c.auto_adr || []).length ? (c.auto_adr || []).map(esc).join(", ") : "–"}${c.last_base ? ` · zuletzt erreicht: <b>${esc(c.last_base)}</b>` : ""}</div>
            <label class="f">Zusätzliche Adressen von Hand (nur für VPN / unterwegs, eine je Zeile)<textarea class="in" id="sadr" rows="2" placeholder="http://pc.mein-vpn:8780">${esc((c.adressen || []).join("\n"))}</textarea></label>
            <button class="btn sm" id="ssuch">PC im Netz suchen</button></div></details>
          <div class="row" style="gap:8px"><button class="btn" id="ssave">Speichern</button><span class="sp"></span><button class="btn ghost" id="sunp" style="color:var(--bad)">Entkoppeln</button></div>
          <div class="small muted">Eigene Nummernkreise auf diesem Gerät (z. B. 2026-M001) – so vergeben PC und Gerät offline nie dieselbe Rechnungsnummer.</div></div></div>
        ${logCard(d)}</div>`;
    } else {
      const srv = d.server || {}, lanOk = srv.aktiv && srv.modus === "lan";
      const live = (d.peers || []).filter(p => p.live && p.rolle === "mobil");
      body = `<div class="grid g2" style="align-items:start">
        <div class="card"><div class="hd"><h3>${ic("m58")} Dieser PC ist das Hauptgerät</h3></div><div class="bd fr">
          <div class="small">iPhone, iPad oder ein zweiter PC arbeiten offline mit einer eigenen Kopie und gleichen sich mit diesem PC ab – live, sobald sie im Netz sind.</div>
          <div class="small ${lanOk ? "muted" : ""}" style="${lanOk ? "" : "color:var(--warn)"}">Schnittstelle: ${srv.aktiv ? `an, Port ${esc(String(srv.port))}, ${srv.modus === "lan" ? "im Heimnetz erreichbar" : "nur dieser PC – zum Koppeln „im Heimnetz erreichbar“ einstellen"}` : "aus – unter Einstellungen → Schnittstelle &amp; Handy einschalten (im Heimnetz erreichbar)"}</div>
          ${lanOk ? `<div class="small muted">Geräte-Suche: ${srv.suche ? "an (UDP-Port 8781)" : `aus${srv.suche_fehler ? " – " + esc(srv.suche_fehler) : ""} – Geräte finden den PC dann über die Netz-Suche (dauert etwas länger)`}</div>` : ""}
          <button class="btn pri" id="spaircode" ${lanOk ? "" : "disabled"}>${ic("plus")} Gerät koppeln (Code anzeigen)</button>
          <div id="spc"></div>
          <div id="slivepc" class="small">${live.length ? dot("var(--ok)", "Live verbunden: " + live.map(p => esc(p.name || p.dev)).join(", ")) : ""}</div>
          <div><b class="small">Gekoppelte Geräte</b>${(d.zugaenge || []).length ? (d.zugaenge || []).map(z => `<div class="row small" style="align-items:center;border-bottom:1px solid var(--line);padding:5px 0"><span style="flex:1">${esc(z.name)}</span><span class="muted" style="flex:none">zuletzt ${esc(when(z.zuletzt))}${z.zuletzt_ip ? " · " + esc(z.zuletzt_ip) : ""}</span><button class="btn sm ghost" style="flex:none;color:var(--bad)" data-srev="${z.id}">Sperren</button></div>`).join("") : `<div class="small muted">noch keine</div>`}</div></div></div>
        <div class="card"><div class="hd"><h3>Oder: dieses Gerät mit einem PC koppeln</h3></div><div class="bd fr">
          <div class="small"><b>1.</b> Am PC unter <b>Abgleich → Gerät koppeln</b> drücken. <b>2.</b> Hier <b>PC suchen</b>. <b>3.</b> Code eintippen – fertig.</div>
          <button class="btn" id="ssuch">${ic("search")} PC suchen</button>
          <div id="spcs">${pcList()}</div>
          <div class="row"><label class="f">Kopplungscode<input class="in" id="scode" placeholder="ABCD-EFGH" autocomplete="off" autocapitalize="characters"></label><label class="f">Name dieses Geräts<input class="in" id="sname" value="${esc(c.name || "")}" placeholder="z. B. iPhone"></label></div>
          <details><summary class="small" style="cursor:pointer">PC wird nicht gefunden? Adresse von Hand</summary>
            <label class="f" style="margin-top:8px">Adressen des PCs (eine je Zeile)<textarea class="in" id="sadr" rows="2" placeholder="http://192.168.1.20:8780">${esc((c.adressen || []).join("\n"))}</textarea></label></details>
          <div class="alert warn" style="cursor:default">Beim Koppeln übernimmt dieses Gerät <b>alle Daten des PCs</b> – was hier bisher gespeichert war, wird ersetzt.</div>
          <button class="btn pri" id="spair">Koppeln &amp; Daten holen</button></div></div></div>
        ${logCard(d)}`;
    }
    $("#main").innerHTML = `<div class="page">${pageHead("Abgleich", mob ? "Offline arbeiten – Änderungen werden mit dem PC ausgetauscht, in beide Richtungen" : "PC und Mobilgeräte arbeiten offline und gleichen sich ab", "")}
      ${pg.neu ? `<div class="alert warn" style="margin-bottom:14px;cursor:default"><b>Programm v${esc(pg.neu)} ist geladen.</b> Es wird beim nächsten Öffnen der App verwendet. <button class="btn sm pri" id="squit" style="margin-left:8px">App jetzt schließen</button></div>` : ""}
      ${konf.length ? `<div class="alert warn" style="margin-bottom:14px;cursor:default">${konf.length} Konflikt(e): Ein Datensatz wurde auf beiden Geräten geändert – die neuere Fassung gilt, die andere ist unten aufgehoben.</div>` : ""}
      ${body}</div>`;
    bind(d);
    tick();
  }

  // only the status area is refreshed - inputs stay untouched
  function tick(){
    clearTimeout(T);
    T = setTimeout(async () => {
      if (view !== "m58") return;
      const s = await api("/api/sync/status");
      if (s && view === "m58") {
        const e = $("#sstat"); if (e) e.innerHTML = statusHtml(s);
        const b = $("#sjetzt"); if (b) b.disabled = !!(s.state || {}).laeuft;
        const l = $("#slivepc"); if (l) l.innerHTML = (s.live_geraete || []).length ? dot("var(--ok)", "Live verbunden: " + s.live_geraete.map(esc).join(", ")) : "";
      }
      tick();
    }, 3000);
  }

  function logCard(d){
    const konf = d.konflikte || [];
    return `<div class="card" style="margin-top:14px"><div class="hd"><h3>Konflikte</h3><div class="act">${konf.length ? `<button class="btn sm ghost" id="skall">Alle als erledigt</button>` : ""}</div></div>
      ${konf.length ? `<table class="t nosort"><thead><tr><th>Zeit</th><th>Tabelle</th><th>Was passiert ist</th><th></th></tr></thead><tbody>${konf.map(k => `<tr><td class="num small">${esc(when(k.zeit))}</td><td class="small">${esc(k.tbl)}</td><td class="small">${esc(k.info)}</td>
        <td class="r" style="white-space:nowrap"><button class="btn sm ghost" data-ksee="${k.id}">Ansehen</button><button class="btn sm ghost" data-kok="${k.id}">Erledigt</button></td></tr>`).join("")}</tbody></table>` : `<div class="bd small muted">Keine offenen Konflikte.</div>`}</div>
      <div class="card" style="margin-top:14px"><div class="hd"><h3>Protokoll</h3></div>
      ${(d.log || []).length ? `<table class="t nosort"><thead><tr><th>Zeit</th><th>Gerät</th><th class="r">gesendet</th><th class="r">empfangen</th><th class="r">Dateien</th><th>Ergebnis</th></tr></thead><tbody>${d.log.map(l => `<tr><td class="num small">${esc(when(l.zeit))}</td><td class="small">${esc(l.peer || "")}</td><td class="r num">${l.gesendet}</td><td class="r num">${l.empfangen}</td><td class="r num small">${l.dateien_hin} / ${l.dateien_her}</td><td class="small" style="color:${l.ok ? "inherit" : "var(--bad)"}">${esc(l.text || "")}</td></tr>`).join("")}</tbody></table>`
        : `<div class="bd small muted">${(d.peers || []).length ? (d.peers || []).map(p => `${esc(p.name || p.dev)} · zuletzt ${esc(when(p.zuletzt))}`).join("<br>") : "Noch kein Abgleich."}</div>`}</div>`;
  }

  function bind(d){
    const on = (id, fn) => { const e = $("#" + id); if (e) e.onclick = fn; };
    const adr = () => ($("#sadr") ? $("#sadr").value.split(/\s*\n\s*/).map(s => s.trim()).filter(Boolean) : []);
    const bindSel = () => $$("[name=spcsel]").forEach(r => r.onchange = () => { SEL = r.value; $("#spcs").innerHTML = pcList(); bindSel(); });
    bindSel();
    on("sjetzt", async () => { toast("Abgleich läuft …"); const p_ = api("/api/sync/jetzt", {}); setTimeout(tick, 300); const r = await p_;
      if (r && r.ok) toast(r.text || "Abgeglichen"); else if (r && r.error) toast(r.error, true); await reload(); if (view === "m58") vSync(); });
    on("ssave", async () => { await api("/api/sync/speichern", {adressen: adr(), auto_min: +$("#sauto").value, name: $("#sname").value.trim(), beim_start: $("#sstart").checked, dateien: $("#sdat").checked, live: $("#slive").checked, programm: $("#sprog") ? $("#sprog").checked : true}); toast("Gespeichert"); vSync(); });
    on("squit", async () => { toast("App wird geschlossen – bitte neu öffnen"); await api("/api/sync/beenden", {}); });
    on("sunp", async () => { if (!await confirmBox("Dieses Gerät vom PC entkoppeln? Die Daten bleiben hier, es wird aber nicht mehr abgeglichen.", "Entkoppeln")) return; await api("/api/sync/entkoppeln", {}); vSync(); });
    on("ssuch", async () => {
      const b = $("#ssuch"); b.disabled = true; const t0 = b.innerHTML; b.textContent = "Suche läuft …";
      const r = await api("/api/sync/suchen", {}); b.disabled = false; b.innerHTML = t0;
      if (!r) return;
      PCS = r.pcs || [];
      if (!SEL || !PCS.some(p => p.base === SEL)) { const ready = PCS.filter(p => p.pairing); SEL = (ready[0] || PCS[0] || {}).base || ""; }
      const e = $("#spcs"); if (e) { e.innerHTML = pcList(); bindSel(); }
      else toast(PCS.length ? `Gefunden: ${PCS.map(p => p.name).join(", ")}` : "Kein PC gefunden", !PCS.length);
      if (PCS.length && $("#scode")) $("#scode").focus();
    });
    on("spair", async () => {
      const code = $("#scode").value.trim(); if (!code) { toast("Kopplungscode vom PC eintragen", true); return; }
      if (!SEL && !adr().length) { toast("Erst „PC suchen“ drücken (oder Adresse eintragen)", true); return; }
      if (!await confirmBox("Alle Daten dieses Geräts werden durch den Stand des PCs ersetzt. Weiter?", "Koppeln")) return;
      toast("Kopple und hole die Daten vom PC …");
      const r = await api("/api/sync/koppeln", {base: SEL, adressen: adr(), code, name: $("#sname").value.trim()});
      if (r && r.ok) { toast(r.text || "Gekoppelt"); PCS = null; SEL = ""; await reload(); vSync(); } });
    on("spaircode", async () => {
      const r = await api("/api/m88/pair", {}); if (!r || r.ok === false) return;
      $("#spc").innerHTML = `<div class="hl"><div class="small">Auf dem Gerät unter <b>Abgleich → PC suchen</b>, dann diesen Code eintippen (gültig ${r.gueltig_min} Minuten):</div>
        <div style="font:700 28px var(--disp);letter-spacing:2px;margin:6px 0">${esc(r.code)}</div>
        <div class="small muted">Falls das Gerät den PC nicht findet – Adresse von Hand: <b>${esc((r.base || "").replace(/\/$/, ""))}</b>${(r.ips || []).length > 1 ? ` (weitere: ${(r.ips || []).filter(i => i !== r.ip).map(i => esc(i)).join(", ")})` : ""}</div>
        <div class="small muted" style="margin-top:4px">Für unterwegs zusätzlich die VPN-Adresse des PCs eintragen (z. B. http://pc-name:${esc(String((d.server || {}).port || 8780))}).</div></div>`; });
    $$("[data-srev]").forEach(b => b.onclick = async () => { if (!await confirmBox("Diesem Gerät den Abgleich sperren?", "Sperren")) return; await api("/api/m88/token/revoke", {id: +b.dataset.srev}); vSync(); });
    $$("[data-kok]").forEach(b => b.onclick = async () => { await api("/api/sync/konflikt_erledigt", {id: +b.dataset.kok}); vSync(); });
    on("skall", async () => { await api("/api/sync/konflikt_erledigt", {alle: true}); vSync(); });
    $$("[data-ksee]").forEach(b => b.onclick = async () => {
      const k = await api("/api/sync/konflikt?id=" + b.dataset.ksee); if (!k) return;
      const v = (k.verlierer || {}).verworfen || {}, a = (k.verlierer || {}).aktuell || {};
      const keys = [...new Set([...Object.keys(v), ...Object.keys(a)])].filter(x => typeof v[x] !== "object" || v[x] === null);
      modal("Konflikt – " + k.tbl, `<div class="fr"><div class="small">${esc(k.info)}</div>
        <table class="t nosort"><thead><tr><th>Feld</th><th>verworfene Fassung</th>${Object.keys(a).length ? "<th>gültige Fassung</th>" : ""}</tr></thead><tbody>
        ${keys.map(x => `<tr${Object.keys(a).length && String(v[x]) !== String(a[x]) ? ' style="background:var(--accsoft)"' : ""}><td class="small">${esc(x)}</td><td class="small">${esc(v[x] == null ? "" : String(v[x]).slice(0, 300))}</td>${Object.keys(a).length ? `<td class="small">${esc(a[x] == null ? "" : String(a[x]).slice(0, 300))}</td>` : ""}</tr>`).join("")}</tbody></table>
        <div class="small muted">Wenn die verworfene Fassung richtig war: Datensatz öffnen und die Werte von Hand übernehmen.</div></div>`, [{label: "Schließen", cls: "pri"}], true);
    });
  }
  // v1.1.0: data (or the menu) arrived from the other device -> reload the open page by itself,
  // but never while something is being typed, a dialog is open or a document is being edited
  let G = null;
  const busy = () => { const a = document.activeElement;
    return !!$(".mb") || view === "editor" || (a && (/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) || a.isContentEditable)); };
  async function genTick(){
    try {
      if (!document.hidden) {
        const r = await fetch("/api/sync/gen", {cache:"no-store"}).then(x => x.ok ? x.json() : null).catch(() => null);
        if (r && G === null) G = r.g;
        else if (r && r.g !== G && !r.laeuft && !busy()) {
          G = r.g;
          const m = $("#main"), sc = m ? m.scrollTop : 0;
          await reload();
          if (view !== "m58" && typeof go === "function") { go(view, viewArg); setTimeout(() => { const mm = $("#main"); if (mm) mm.scrollTop = sc; }, 60); }
        }
      }
    } catch (e) {}
    setTimeout(genTick, 4000);
  }
  setTimeout(genTick, 6000);
  console.log("INIT UI m58_abgleich v1.2.0");
})();
