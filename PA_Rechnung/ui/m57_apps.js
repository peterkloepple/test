// Pfeiffer-Audio Rechnung v3.6.4 - UI-Modul m57_apps v1.0.0: andere Web-Apps per Link erfassen und oeffnen
// Seite "Apps" (System): Kacheln, hinzufuegen/bearbeiten/entfernen, Reihenfolge, oeffnen im Programmfenster oder Browser.
// Seitenleiste: Bereich "Apps" mit allen Apps, die "in der Seitenleiste" haben - ein Klick oeffnet die App.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.apps = '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17.5 14v7M14 17.5h7"/>';
  EXT.nav.push({key: "apps", label: "Apps", icon: "apps", section: "System"});
  EXT.views.apps = vApps;
  let L = [];
  const host = u => { try { return new URL(u).host; } catch (e) { return u; } };
  const badge = (a, s) => `<span style="flex:none;display:inline-flex;align-items:center;justify-content:center;width:${s}px;height:${s}px;border-radius:${Math.round(s * .26)}px;background:${esc(a.farbe || "#6a48e0")};color:#fff;font:700 ${Math.round(s * .46)}px var(--disp,system-ui)">${esc(a.symbol || (a.name || "?")[0])}</span>`;

  async function openApp(id, wie){
    const r = await api("/api/apps/oeffnen", {id, wie});
    if (r && r.ok) toast(`${r.name} geöffnet` + (r.wo === "browser" ? " (im Browser)" : ""));
  }
  window.appOeffnen = openApp;

  // ---- sidebar: every app with "seitenleiste" becomes a normal menu entry (key app_<id>, rubric "Apps") - so the
  // layout editor (m63) can move or hide it like any other entry. Synced whenever the start data arrive.
  const svgEsc = t => String(t).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  function syncNav(apps){
    for (let i = EXT.nav.length - 1; i >= 0; i--) if (String(EXT.nav[i].key).startsWith("app_")) EXT.nav.splice(i, 1);
    (apps || []).filter(x => x.seitenleiste).forEach(x => {
      const k = "app_" + x.id;
      IC[k] = `<rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="${svgEsc(x.farbe || "#6a48e0")}" stroke="none"/>`
        + `<text x="12" y="16.3" text-anchor="middle" font-size="11.5" font-weight="700" font-family="system-ui,sans-serif" fill="#fff" stroke="none">${svgEsc(x.symbol || (x.name || "?")[0])}</text>`;
      EXT.nav.push({key: k, label: x.name, icon: k, section: "Apps"});
    });
  }
  const origApi = window.api;
  window.api = async function(p, ...r){
    const res = await origApi.call(this, p, ...r);
    if (p === "/api/bootstrap" && res && Array.isArray(res.apps)) { try { syncNav(res.apps); } catch (e) { console.error(e); } }
    return res;
  };
  const origGo = window.go;
  window.go = function(v, ...r){
    if (typeof v === "string" && v.startsWith("app_")) { openApp(v.slice(4)); return; }   // open the app, stay on the page
    return origGo.call(this, v, ...r);
  };

  async function vApps(){
    const d = await api("/api/apps"); L = (d && d.apps) || [];
    const kats = [...new Set(L.map(a => a.kategorie || ""))].sort((a, b) => a.localeCompare(b, "de"));
    $("#main").innerHTML = `<div class="page">${pageHead("Apps", "Andere Web-Apps per Link erfassen und mit einem Klick öffnen – im eigenen Programmfenster oder im Browser",
        `<button class="btn pri" id="appadd">${ic("plus")} App hinzufügen</button>`)}
      ${L.length ? kats.map(k => `${k ? `<div class="small muted" style="margin:14px 2px 8px;font-weight:600">${esc(k)}</div>` : ""}
        <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px">${L.filter(a => (a.kategorie || "") === k).map(tile).join("")}</div>`).join("")
      : `<div class="card"><div class="bd"><div class="empty" style="padding:30px">Noch keine Apps.<br><span class="small muted">„App hinzufügen“ – Name und Weblink eintragen, z. B. MediaFlow, TimeTree, Online-Banking, ein Lieferanten-Portal oder die Weboberfläche eines Geräts im Netz.</span></div></div></div>`}
      <div class="small muted" style="margin-top:14px">Das Programm ruft die Links nicht selbst ab (kein Vorschaubild, kein Symbol aus dem Internet) – eine App wird erst beim Öffnen geladen und bekommt keine Daten aus dem Programm.</div></div>`;
    $("#appadd").onclick = () => edit(null);
    $$("[data-aopen]").forEach(b => b.onclick = () => openApp(b.dataset.aopen));
    $$("[data-abr]").forEach(b => b.onclick = e => { e.stopPropagation(); openApp(b.dataset.abr, "browser"); });
    $$("[data-aed]").forEach(b => b.onclick = e => { e.stopPropagation(); edit(L.find(a => a.id === b.dataset.aed)); });
    $$("[data-amv]").forEach(b => b.onclick = async e => { e.stopPropagation(); const [id, dir] = b.dataset.amv.split("|"); const ids = L.map(a => a.id), i = ids.indexOf(id), j = i + (+dir);
      if (j < 0 || j >= ids.length) return; [ids[i], ids[j]] = [ids[j], ids[i]]; await api("/api/apps/sortieren", {ids}); await reload(); vApps(); });
  }

  function tile(a){
    return `<div class="card" style="cursor:pointer" data-aopen="${esc(a.id)}" title="Öffnen">
      <div class="bd"><div class="row" style="align-items:center;gap:12px">${badge(a, 44)}
        <div style="flex:1;min-width:0"><b style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.name)}</b>
          <div class="small muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(host(a.url))}</div></div></div>
        ${a.notiz ? `<div class="small" style="margin-top:8px">${esc(a.notiz)}</div>` : ""}
        <div class="small muted" style="margin-top:8px">${a.oeffnen === "browser" ? "öffnet im Browser" : "öffnet im Programmfenster"}${a.seitenleiste ? " · in der Seitenleiste" : ""}</div>
        <div class="row" style="margin-top:8px;gap:6px;align-items:center;justify-content:flex-end">
          <button class="btn sm ghost" style="flex:none" data-amv="${esc(a.id)}|-1" title="nach vorne">‹</button><button class="btn sm ghost" style="flex:none" data-amv="${esc(a.id)}|1" title="nach hinten">›</button>
          <button class="btn sm ghost" style="flex:none" data-abr="${esc(a.id)}" title="Im Browser öffnen">${ic("open")}</button><button class="btn sm" style="flex:none" data-aed="${esc(a.id)}">Bearbeiten</button></div></div></div>`;
  }

  async function edit(a){
    const x = a || {farbe: "#6a48e0", oeffnen: "fenster", seitenleiste: true};
    const btns = [];
    if (a) btns.push({label: "Entfernen", cls: "danger", onClick: async () => { await api("/api/apps/loeschen", {id: a.id}); }});
    btns.push({label: "Abbrechen"}, {label: a ? "Speichern" : "Hinzufügen", cls: "pri", value: 1, onClick: async mb => {
      const d = {id: a ? a.id : "", name: $("#apn", mb).value.trim(), url: $("#apu", mb).value.trim(), symbol: $("#aps", mb).value.trim(), farbe: $("#apf", mb).value,
        oeffnen: $("#apo", mb).value, seitenleiste: $("#apl", mb).checked, kategorie: $("#apk", mb).value.trim(), notiz: $("#apx", mb).value.trim()};
      if (!d.name || !d.url) { toast("Name und Weblink eintragen", true); return false; }
      const r = await api("/api/apps/speichern", d); if (!r || r.ok === false) return false; }});
    const kats = [...new Set(L.map(v => v.kategorie).filter(Boolean))];
    await modal(a ? "App bearbeiten" : "App hinzufügen", `<div class="fr">
      <label class="f">Weblink<input class="in" id="apu" value="${esc(x.url || "")}" placeholder="https://app.beispiel.de" autocomplete="off"></label>
      <div class="row"><label class="f" style="flex:2">Name<input class="in" id="apn" value="${esc(x.name || "")}" placeholder="z. B. MediaFlow"></label>
        <label class="f" style="flex:none;width:90px">Symbol<input class="in" id="aps" value="${esc(x.symbol || "")}" maxlength="2" placeholder="M" title="1–2 Zeichen, auch Emoji"></label>
        <label class="f" style="flex:none">Farbe<input type="color" class="in" id="apf" value="${esc(x.farbe || "#6a48e0")}" style="width:60px;padding:2px"></label></div>
      <div class="row"><label class="f">Öffnen<select class="in" id="apo"><option value="fenster" ${x.oeffnen !== "browser" ? "selected" : ""}>im eigenen Programmfenster</option><option value="browser" ${x.oeffnen === "browser" ? "selected" : ""}>im Standard-Browser</option></select></label>
        <label class="f">Gruppe (optional)<input class="in" id="apk" value="${esc(x.kategorie || "")}" list="apkl" placeholder="z. B. Arbeit, Bank, Geräte"><datalist id="apkl">${kats.map(k => `<option value="${esc(k)}">`).join("")}</datalist></label></div>
      <label class="f">Notiz (optional)<input class="in" id="apx" value="${esc(x.notiz || "")}" placeholder="z. B. Login mit Firmen-Konto"></label>
      <label class="chk"><input type="checkbox" id="apl" ${x.seitenleiste !== false ? "checked" : ""}> in der Seitenleiste anzeigen (Bereich „Apps“)</label>
      <div class="small muted">Programmfenster: eigenes Fenster wie ein kleiner Browser nur für diese App – Anmeldungen bleiben gespeichert. Wenn eine Seite darin nicht richtig läuft (z. B. Anmeldung über Microsoft/Google), „im Standard-Browser“ wählen.</div></div>`,
      btns, false);
    await reload(); if (view === "apps") vApps();
  }
  console.log("INIT UI m57_apps v1.0.0");
})();
