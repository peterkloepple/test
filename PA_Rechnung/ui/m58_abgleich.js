// Pfeiffer-Audio Rechnung v3.7.0 - UI-Modul m58_abgleich v1.0.0: Seite "Abgleich" (System)
// PC (Hauptgeraet): gekoppelte Geraete, "Geraet koppeln" (Code), Konflikte, Protokoll.
// Mobilgeraet (iPhone/iPad/zweiter PC): mit PC koppeln (Adressen + Code), Jetzt abgleichen, Adressen/Intervall, Konflikte.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m58 = '<path d="M4 12a8 8 0 0 1 13.7-5.6L20 9"/><path d="M20 4v5h-5"/><path d="M20 12a8 8 0 0 1-13.7 5.6L4 15"/><path d="M4 20v-5h5"/>';
  EXT.nav.push({key: "m58", label: "Abgleich", icon: "m58", section: "System", cnt: () => (S.sync && S.sync.laeuft ? "…" : "")});
  EXT.views.m58 = vSync;
  let T = null;
  const when = z => z ? `${dde(z.slice(0, 10))} ${z.slice(11, 16)}` : "–";
  const INT = [[0, "nur per Knopf"], [5, "alle 5 Minuten"], [15, "alle 15 Minuten"], [60, "jede Stunde"], [240, "alle 4 Stunden"]];

  async function vSync(){
    clearTimeout(T);
    const d = await api("/api/sync"); if (!d) return;
    const c = d.cfg || {}, mob = c.rolle === "mobil" && d.gekoppelt, st = d.state || {}, last = st.letzter || {};
    const konf = d.konflikte || [];
    let body = "";
    if (mob) {
      body = `<div class="grid g2" style="align-items:start">
        <div class="card"><div class="hd"><h3>${ic("m58")} Abgleich mit ${esc(c.pc_name || "PC")}</h3></div><div class="bd fr">
          <div class="row" style="align-items:center;gap:12px"><button class="btn pri" id="sjetzt" ${st.laeuft ? "disabled" : ""}>${ic("sync")} Jetzt abgleichen</button>
            <span class="small">${st.laeuft ? `<b>${esc(st.text || "läuft …")}</b>` : last.zeit ? `<span style="color:${last.ok ? "var(--ok)" : "var(--bad)"}">${last.ok ? "✓" : "✗"}</span> ${esc(when(last.zeit))} · ${esc(last.text || "")}` : "noch nicht abgeglichen"}</span></div>
          <div class="small muted">${d.offen ? `<b>${d.offen}</b> Änderung(en) auf diesem Gerät warten auf den Abgleich.` : "Alle Änderungen dieses Geräts sind beim PC."}</div>
          <label class="f">Adressen des PCs (der Reihe nach probiert – z. B. WLAN, dann VPN)<textarea class="in" id="sadr" rows="3" placeholder="http://192.168.1.20:8780&#10;http://pc.mein-vpn:8780">${esc((c.adressen || []).join("\n"))}</textarea></label>
          <div class="row"><label class="f">Automatisch abgleichen<select class="in" id="sauto">${INT.map(([v, l]) => `<option value="${v}" ${+c.auto_min === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
            <label class="f">Name dieses Geräts<input class="in" id="sname" value="${esc(c.name || "")}" placeholder="z. B. iPhone"></label></div>
          <label class="chk"><input type="checkbox" id="sstart" ${c.beim_start !== false ? "checked" : ""}> beim Programmstart abgleichen</label>
          <label class="chk"><input type="checkbox" id="sdat" ${c.dateien !== false ? "checked" : ""}> Dateien mit abgleichen (Belege, Rechnungs-PDFs, Projektdateien)</label>
          <div class="row" style="gap:8px"><button class="btn" id="ssave">Speichern</button><span class="sp"></span><button class="btn ghost" id="sunp" style="color:var(--bad)">Entkoppeln</button></div>
          <div class="small muted">Eigene Nummernkreise auf diesem Gerät (z. B. 2026-M001) – so vergeben PC und Gerät offline nie dieselbe Rechnungsnummer.</div></div></div>
        ${logCard(d)}</div>`;
    } else {
      const srv = d.server || {};
      body = `<div class="grid g2" style="align-items:start">
        <div class="card"><div class="hd"><h3>${ic("m58")} Dieser PC ist das Hauptgerät</h3></div><div class="bd fr">
          <div class="small">iPhone, iPad oder ein zweiter PC arbeiten offline mit einer eigenen Kopie und gleichen sich mit diesem PC ab.</div>
          <div class="small ${srv.aktiv && srv.modus === "lan" ? "muted" : ""}" style="${srv.aktiv && srv.modus === "lan" ? "" : "color:var(--warn)"}">Schnittstelle: ${srv.aktiv ? `an, Port ${esc(String(srv.port))}, ${srv.modus === "lan" ? "im Heimnetz erreichbar" : "nur dieser PC – zum Koppeln „im Heimnetz erreichbar“ einstellen"}` : "aus – unter Einstellungen → Schnittstelle &amp; Handy einschalten (im Heimnetz erreichbar)"}</div>
          <button class="btn pri" id="spaircode" ${srv.aktiv && srv.modus === "lan" ? "" : "disabled"}>${ic("plus")} Gerät koppeln (Code anzeigen)</button>
          <div id="spc"></div>
          <div><b class="small">Gekoppelte Geräte</b>${(d.zugaenge || []).length ? (d.zugaenge || []).map(z => `<div class="row small" style="align-items:center;border-bottom:1px solid var(--line);padding:5px 0"><span style="flex:1">${esc(z.name)}</span><span class="muted" style="flex:none">zuletzt ${esc(when(z.zuletzt))}${z.zuletzt_ip ? " · " + esc(z.zuletzt_ip) : ""}</span><button class="btn sm ghost" style="flex:none;color:var(--bad)" data-srev="${z.id}">Sperren</button></div>`).join("") : `<div class="small muted">noch keine</div>`}</div></div></div>
        <div class="card"><div class="hd"><h3>Oder: dieses Gerät mit einem PC koppeln</h3></div><div class="bd fr">
          <div class="small">Für iPhone/iPad (oder einen zweiten PC): Auf dem PC unter <b>Abgleich → Gerät koppeln</b> den Code anzeigen lassen und hier eintragen.</div>
          <label class="f">Adressen des PCs (eine je Zeile)<textarea class="in" id="sadr" rows="3" placeholder="http://192.168.1.20:8780">${esc((c.adressen || []).join("\n"))}</textarea></label>
          <div class="row"><label class="f">Kopplungscode<input class="in" id="scode" placeholder="ABCD-EFGH" autocomplete="off"></label><label class="f">Name dieses Geräts<input class="in" id="sname" value="${esc(c.name || "")}" placeholder="z. B. iPhone"></label></div>
          <div class="alert warn" style="cursor:default">Beim Koppeln übernimmt dieses Gerät <b>alle Daten des PCs</b> – was hier bisher gespeichert war, wird ersetzt.</div>
          <button class="btn" id="spair">Koppeln &amp; Daten holen</button></div></div></div>
        ${logCard(d)}`;
    }
    $("#main").innerHTML = `<div class="page">${pageHead("Abgleich", mob ? "Offline arbeiten – Änderungen werden mit dem PC ausgetauscht, in beide Richtungen" : "PC und Mobilgeräte arbeiten offline und gleichen sich ab", "")}
      ${konf.length ? `<div class="alert warn" style="margin-bottom:14px;cursor:default">${konf.length} Konflikt(e): Ein Datensatz wurde auf beiden Geräten geändert – die neuere Fassung gilt, die andere ist unten aufgehoben.</div>` : ""}
      ${body}</div>`;
    bind(d);
    if ((d.state || {}).laeuft) T = setTimeout(() => { if (view === "m58") vSync(); }, 1500);
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
    on("sjetzt", async () => { toast("Abgleich läuft …"); const p_ = api("/api/sync/jetzt", {}); setTimeout(vSync, 300); const r = await p_;
      if (r && r.ok) toast(r.text || "Abgeglichen"); else if (r && r.error) toast(r.error, true); await reload(); if (view === "m58") vSync(); });
    on("ssave", async () => { await api("/api/sync/speichern", {adressen: adr(), auto_min: +$("#sauto").value, name: $("#sname").value.trim(), beim_start: $("#sstart").checked, dateien: $("#sdat").checked}); toast("Gespeichert"); vSync(); });
    on("sunp", async () => { if (!await confirmBox("Dieses Gerät vom PC entkoppeln? Die Daten bleiben hier, es wird aber nicht mehr abgeglichen.", "Entkoppeln")) return; await api("/api/sync/entkoppeln", {}); vSync(); });
    on("spair", async () => {
      const code = $("#scode").value.trim(); if (!adr().length || !code) { toast("Adresse und Code eintragen", true); return; }
      if (!await confirmBox("Alle Daten dieses Geräts werden durch den Stand des PCs ersetzt. Weiter?", "Koppeln")) return;
      toast("Kopple und hole die Daten vom PC …");
      const r = await api("/api/sync/koppeln", {adressen: adr(), code, name: $("#sname").value.trim()});
      if (r && r.ok) { toast(r.text || "Gekoppelt"); await reload(); vSync(); } });
    on("spaircode", async () => {
      const r = await api("/api/m88/pair", {}); if (!r || r.ok === false) return;
      $("#spc").innerHTML = `<div class="hl"><div class="small">Auf dem Gerät unter <b>Abgleich</b> eintragen (gültig ${r.gueltig_min} Minuten):</div>
        <div style="font:700 28px var(--disp);letter-spacing:2px;margin:6px 0">${esc(r.code)}</div>
        <div class="small">Adresse im Heimnetz: <b>${esc((r.base || "").replace(/\/$/, ""))}</b>${(r.ips || []).length > 1 ? ` <span class="muted">(weitere: ${(r.ips || []).filter(i => i !== r.ip).map(i => esc(i)).join(", ")})</span>` : ""}</div>
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
  console.log("INIT UI m58_abgleich v1.0.0");
})();
