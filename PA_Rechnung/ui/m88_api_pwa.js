// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m88_api_pwa: Schnittstelle & Handy (REST-API, Handy-App, Tokens, Protokoll)
// Einstellungs-Reiter "Schnittstelle & Handy" + Dashboard-Karte "Notizen vom Handy".
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m88api = '<path d="M8 4H5v16h3M16 4h3v16h-3"/><path d="M10 9l-2 3 2 3M14 9l2 3-2 3"/>';
  const dt = v => v ? dde(String(v).slice(0, 10)) + " " + String(v).slice(11, 16) : "–";
  // local time "YYYY-MM-DDTHH:MM:SS" (token expiry is stored in local time, toISOString() would be UTC)
  const nowLocal = () => { const d = new Date(), p = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
  let logShow = false;

  function copyBox(id, val){
    return `<div class="row" style="align-items:center;gap:6px"><input class="in" id="${id}" value="${esc(val)}" readonly style="font-family:ui-monospace,Consolas,monospace;font-size:12.5px">
      <button class="btn sm" type="button" data-m88copy="${id}" style="flex:none">Kopieren</button></div>`;
  }
  function bindCopy(root){
    $$("[data-m88copy]", root).forEach(b => b.onclick = async () => { const i = $("#" + b.dataset.m88copy, root.ownerDocument ? root : document) || $("#" + b.dataset.m88copy);
      i.select(); let ok = false; try { await navigator.clipboard.writeText(i.value); ok = true; } catch (e) { try { ok = document.execCommand("copy"); } catch (e2) {} }
      toast(ok ? "Kopiert" : "Markiert – mit Strg+C kopieren"); });
  }

  function exampleBlock(base){
    const b = base || "http://127.0.0.1:8780";
    const pre = t => `<pre style="white-space:pre-wrap;word-break:break-all;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px;font:12px/1.45 ui-monospace,Consolas,monospace;margin:4px 0 12px">${esc(t)}</pre>`;
    const ep = [["GET", "/v1/status", "Programm, Version, laufende Stoppuhr"], ["GET", "/v1/kunden?q=…", "Kunden (Suche optional)"],
      ["GET", "/v1/rechnungen?status=offen&typ=rechnung&jahr=2026&limit=200", "Rechnungen filtern (typ: rechnung, angebot, auftrag, storno, alle)"],
      ["GET", "/v1/rechnungen/<id>", "eine Rechnung mit Positionen"], ["GET", "/v1/rechnungen/<id>/pdf", "Rechnung als PDF"],
      ["GET", "/v1/offene-posten", "offene Rechnungen mit Fälligkeit und Überfällig-Tagen"], ["GET", "/v1/projekte?status=aktiv", "Projekte mit gebuchten Stunden"],
      ["GET", "/v1/kennzahlen?jahr=2026", "Umsatz, Gewinn, Offen, Kontostand, Monate"], ["GET", "/v1/lager?filter=nachbestellen", "Lagerartikel"],
      ["GET", "/v1/bausteine", "aktive Bausteine (für Zeitbuchung)"], ["GET", "/v1/notizen", "offene Notizen"],
      ["GET", "/v1/kalender?von=2026-11-08&bis=2026-11-22&q=", "Termine aller Kalender (TimeTree, .ics, Kalender-Abos, Programm)"], ["GET", "/v1/kalender/abos", "Kalender-Abos mit Status"],
      ["POST", "/v1/kalender/abrufen", "alle Kalender-Abos jetzt abrufen (Schreib-Recht)"],
      ["POST", "/v1/zeit", '{"project_id":12, "stunden":1.5, "text":"…", "datum":"2026-10-27", "article_id":null}'],
      ["POST", "/v1/fahrt", '{"datum":"2026-10-27", "km":84, "art":"dienst", "ziel":"Köln", "zweck":"…", "project_id":12}'],
      ["POST", "/v1/beleg", "Datei als Rohdaten, Header X-Filename: rechnung.pdf"], ["POST", "/v1/notiz", '{"text":"…"}'],
      ["POST", "/v1/timer/start | stop | cancel", '{"project_id":12} bzw. {"descr":"…"}']];
    return `<table class="t" style="margin-bottom:12px"><thead><tr><th style="width:60px">Art</th><th>Endpunkt</th><th>Inhalt</th></tr></thead><tbody>
      ${ep.map(e => `<tr><td><span class="badge ${e[0] === "POST" ? "acc" : ""}">${e[0]}</span></td><td class="small" style="font-family:ui-monospace,Consolas,monospace">${esc(e[1])}</td><td class="small">${esc(e[2])}</td></tr>`).join("")}</tbody></table>
      <div class="small muted" style="margin-bottom:8px">Jede Anfrage braucht den Kopf <b>Authorization: Bearer &lt;token&gt;</b>. Lese-Zugänge dürfen nur GET, Schreib-Zugänge auch POST. Antworten sind JSON (UTF-8), Fehler kommen als {"ok":false,"error":"…"} mit HTTP 400/401/403/404/429.</div>
      <b class="small">curl</b>${pre(`curl -H "Authorization: Bearer TOKEN" ${b}/v1/offene-posten\ncurl -X POST -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" -d "{\\"project_id\\":12,\\"stunden\\":1.5,\\"text\\":\\"Inbetriebnahme\\"}" ${b}/v1/zeit`)}
      <b class="small">PowerShell</b>${pre(`$h = @{ Authorization = "Bearer TOKEN" }\nInvoke-RestMethod -Uri "${b}/v1/kennzahlen" -Headers $h\nInvoke-RestMethod -Method Post -Uri "${b}/v1/notiz" -Headers $h -ContentType "application/json" -Body '{"text":"Kunde zurueckrufen"}'`)}
      <b class="small">Q-SYS (Lua, Control Script)</b>${pre(`-- PA Rechnung API abfragen (Q-SYS Lua)  v1.0.0\n-- Autor: T. Pfeiffer\nlocal json = require("rapidjson")\nlocal URL, TOKEN = "${b}", "TOKEN"\nprint("INIT PA-API Abfrage v1.0.0")\nHttpClient.Download{\n  Url = URL .. "/v1/offene-posten",\n  Headers = { ["Authorization"] = "Bearer " .. TOKEN },\n  Timeout = 10,\n  EventHandler = function(tbl, code, data, err, headers)\n    if code == 200 then\n      local d = json.decode(data)\n      print("Offen: " .. d.summe .. " EUR in " .. d.anzahl .. " Rechnungen")\n    else\n      print("Fehler " .. tostring(code) .. " " .. tostring(err))\n    end\n  end\n}\n-- Schreiben: HttpClient.Upload{ Url = URL .. "/v1/notiz", Method = "POST",\n--   Headers = { ["Authorization"] = "Bearer " .. TOKEN, ["Content-Type"] = "application/json" },\n--   Data = json.encode({ text = "Raum 1 Mikro defekt" }), EventHandler = function(t, c, d) print(c) end }`)}
      <b class="small">Crestron (SIMPL+ / SIMPL#)</b>
      <div class="small muted" style="margin:4px 0 6px">SIMPL+: TCP/IP-Client-Symbol auf die PC-Adresse und den Port, beim Verbinden diese Anfrage als String senden (Zeilenende CR LF, am Ende eine Leerzeile). Die Antwort enthält nach der Leerzeile den JSON-Text. Bequemer ist ein SIMPL#-Modul mit Crestron.SimplSharp.Net.Http.HttpClient und demselben Header.</div>
      ${pre(`GET /v1/offene-posten HTTP/1.1\\r\\nHost: ${b.replace(/^https?:\/\//, "")}\\r\\nAuthorization: Bearer TOKEN\\r\\nConnection: close\\r\\n\\r\\n`)}`;
  }

  async function newToken(after){
    await modal("Neuer API-Zugang", `<div class="fr">
      <label class="f">Name (wofür?)<input class="in" id="m88tn" placeholder="z. B. Dr. Jey, Q-SYS Werkstatt, Skript"></label>
      <div class="row"><label class="f">Recht<select class="in" id="m88tr"><option value="lesen">nur lesen</option><option value="schreiben">lesen + schreiben (Zeit, Fahrt, Beleg, Notiz)</option></select></label>
        <label class="f" style="flex:.6">Gültig (Tage, leer = unbegrenzt)<input class="in num" id="m88tt" placeholder="unbegrenzt"></label></div>
      <div class="small muted">Der Zugang (Token) wird nur <b>einmal</b> angezeigt und danach nur noch verschlüsselt gespeichert.</div></div>`,
      [{label:"Abbrechen"}, {label:"Erzeugen", cls:"pri", onClick: async mb => {
        const r = await api("/api/m88/token/new", {name: $("#m88tn", mb).value, recht: $("#m88tr", mb).value, tage: String(Math.round(pnum($("#m88tt", mb).value)) || "")});
        if (!r || !r.ok) return false;
        setTimeout(() => showToken(r.token, after), 50);
      }}]);
  }

  function showToken(tok, after, extra){
    modal("Zugang erzeugt – jetzt kopieren", `<div class="fr"><div class="alert warn" style="cursor:default">${ic("alert")}<span>Diesen Token jetzt kopieren und sicher aufbewahren – er wird nicht noch einmal angezeigt.</span></div>
      ${copyBox("m88tokv", tok)}${extra || ""}</div>`, [{label:"Fertig", cls:"pri"}], false, mb => bindCopy(mb)).then(() => { if (after) after(); });
  }

  async function pairDlg(after){
    const r = await api("/api/m88/pair", {});
    if (!r || !r.ok) return;
    let timer = null;
    await modal("Handy koppeln", `<div class="fr" style="align-items:center;text-align:center">
      <div style="width:240px;height:240px;background:#fff;padding:8px;border-radius:10px;margin:0 auto">${r.svg}</div>
      <div class="small muted">Mit der Handy-Kamera scannen. Oder auf dem Handy <b>${esc(r.base)}</b> öffnen und diesen Code eintippen:</div>
      <div style="font:700 30px/1.2 ui-monospace,Consolas,monospace;letter-spacing:3px">${esc(r.code)}</div>
      <div class="small muted" id="m88pt">gültig ${r.gueltig_min} Minuten, nur einmal verwendbar</div>
      ${(r.ips || []).length > 1 ? `<div class="small">Anderes Netz? ${r.ips.map(ip => `<button class="btn sm ghost" type="button" data-m88ip="${esc(ip)}">${esc(ip)}</button>`).join("")}</div>` : ""}
      <div class="small muted" style="text-align:left">Danach auf dem Handy „Zum Home-Bildschirm“ wählen – dann gibt es ein App-Symbol. Wird die App vom Startbildschirm geöffnet (iPhone), einmal neu koppeln und den Code eintippen.</div></div>`,
      [{label:"Fertig", cls:"pri"}], false, mb => {
        $$("[data-m88ip]", mb).forEach(b => b.onclick = async () => { const n = await api("/api/m88/pair", {ip: b.dataset.m88ip}); if (n && n.ok) { mb.querySelector("svg").outerHTML = n.svg; toast("QR-Code für " + n.ip); } });
        const t0 = Date.now(); timer = setInterval(() => { const e = $("#m88pt", mb); if (!e) return clearInterval(timer);
          const s = Math.max(0, r.gueltig_min * 60 - Math.floor((Date.now() - t0) / 1000)); e.textContent = s ? `noch ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} min gültig, nur einmal verwendbar` : "abgelaufen – neu erzeugen"; }, 1000);
      });
    clearInterval(timer);
    if (after) after();
  }

  async function render(el){
    el.innerHTML = `<div class="small muted" style="margin-top:16px">lädt …</div>`;
    const c = await api("/api/m88/config");
    if (!c || !c.cfg) { el.innerHTML = `<div class="alert bad" style="margin-top:16px">${ic("alert")}Schnittstelle nicht verfügbar.</div>`; return; }
    const cf = c.cfg, toks = c.tokens || [];
    const api_t = toks.filter(t => t.typ !== "geraet"), dev = toks.filter(t => t.typ === "geraet");
    const base = (c.urls || []).slice(-1)[0] || `http://127.0.0.1:${cf.port}`;
    const nz = await api("/api/m88/notizen", undefined, {quiet:true});
    const notes = (nz && nz.notizen) || [];
    const lg = logShow ? ((await api("/api/m88/log?n=300", undefined, {quiet:true})) || {}).log || [] : [];
    const tokRow = t => `<tr data-m88t="${t.id}"><td><b>${esc(t.name)}</b><div class="small muted" style="font-family:ui-monospace,Consolas,monospace">${esc(t.prefix || "")}</div></td>
      <td>${t.recht === "schreiben" ? `<span class="badge acc">lesen + schreiben</span>` : `<span class="badge">nur lesen</span>`}</td>
      <td class="small">${dt(t.erstellt)}${t.ablauf ? `<div class="muted">bis ${dde(t.ablauf.slice(0, 10))}</div>` : ""}</td><td class="small">${dt(t.zuletzt)}<div class="muted">${esc(t.zuletzt_ip || "")}</div></td>
      <td>${t.aktiv ? (t.ablauf && t.ablauf < nowLocal() ? `<span class="badge warn">abgelaufen</span>` : `<span class="badge ok">aktiv</span>`) : `<span class="badge bad">widerrufen</span>`}</td>
      <td class="r" style="white-space:nowrap">${t.aktiv ? `<button class="btn sm" type="button" data-m88rv="${t.id}">Widerrufen</button>` : ""}<button class="btn sm ghost danger" type="button" data-m88del="${t.id}" title="Entfernen">${ic("trash")}</button></td></tr>`;
    el.innerHTML = `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(min(520px,100%),1fr));align-items:start;margin-top:16px">
      <div class="fr" style="gap:16px;min-width:0">
      <div class="card"><div class="hd"><h3>Schnittstelle (REST-API & Handy-App)</h3><div class="act">${c.laeuft ? `<span class="badge ok"><span class="dot"></span>läuft</span>` : `<span class="badge">aus</span>`}</div></div><div class="bd fr">
        <label class="chk"><input type="checkbox" id="m88on" ${cf.aktiv ? "checked" : ""}> Schnittstelle einschalten (startet mit dem Programm)</label>
        <div class="row"><label class="f">Erreichbar<select class="in" id="m88mo"><option value="lokal" ${cf.modus === "lokal" ? "selected" : ""}>nur dieser PC (127.0.0.1)</option><option value="lan" ${cf.modus === "lan" ? "selected" : ""}>im Heimnetz (WLAN/LAN, für Handy)</option></select></label>
          <label class="f" style="flex:.45">Port<input class="in num" id="m88po" value="${esc(cf.port)}"></label></div>
        <div class="row"><label class="f">Max. Anfragen pro Minute und Gerät<input class="in num" id="m88ra" value="${esc(cf.rate)}"></label>
          <label class="f">Handy-Kopplung gültig (Tage)<input class="in num" id="m88gt" value="${esc(cf.geraet_tage)}"></label></div>
        ${c.fehler ? `<div class="alert bad" style="cursor:default">${ic("alert")}<span>${esc(c.fehler)}</span></div>` : ""}
        ${c.laeuft ? `<div class="small">Adresse${(c.urls || []).length > 1 ? "n" : ""}: ${(c.urls || []).map(u => `<b style="font-family:ui-monospace,Consolas,monospace">${esc(u)}</b>`).join(" · ")}</div>` : ""}
        <div class="alert warn" style="cursor:default;font-size:12.5px">${ic("alert")}<span>Nur im eigenen Netz oder über VPN benutzen – <b>nie</b> im Router ins Internet freigeben (keine Portweiterleitung). Die Verbindung ist unverschlüsselt (http); Schutz bieten Token, Rate-Limit und Sperre nach 10 Fehlversuchen.</span></div>
        <div><button class="btn pri" type="button" id="m88sv">${ic("save")} Speichern & (neu) starten</button></div></div></div>
      <div class="card" style="overflow:auto"><div class="hd"><h3>Handy-App</h3><div class="act"><button class="btn sm pri" type="button" id="m88pair" ${c.laeuft && cf.modus === "lan" ? "" : "disabled"}>Handy koppeln</button></div></div><div class="bd fr">
        <div class="small muted">Offene Posten, Kunden (Anrufen/Mail), Projekte mit Stoppuhr und Zeitbuchung, Fahrt erfassen, Beleg fotografieren, Notiz senden und Kennzahlen – direkt am Handy. ${c.laeuft && cf.modus === "lan" ? "" : "<b>Dafür oben „im Heimnetz“ wählen und speichern.</b>"}</div>
        <table class="t"><thead><tr><th>Gerät</th><th>Recht</th><th>Gekoppelt</th><th>Zuletzt</th><th>Status</th><th></th></tr></thead><tbody>${dev.map(tokRow).join("") || `<tr><td colspan="6" class="empty">Noch kein Handy gekoppelt.</td></tr>`}</tbody></table></div></div>
      <div class="card"><div class="hd"><h3>Notizen vom Handy / aus der API</h3></div><div class="bd">
        ${notes.length ? `<table class="t"><tbody>${notes.map(n => `<tr><td class="small muted" style="width:110px">${dt(n.zeit)}<div>${esc(n.quelle || "")}</div></td><td>${esc(n.text)}</td>
          <td class="r" style="white-space:nowrap"><button class="btn sm" type="button" data-m88nd="${n.id}">Erledigt</button><button class="btn sm ghost danger" type="button" data-m88nx="${n.id}">${ic("trash")}</button></td></tr>`).join("")}</tbody></table>` : `<div class="small muted">Keine offenen Notizen.</div>`}</div></div>
      </div>
      <div class="fr" style="gap:16px;min-width:0">
      <div class="card" style="overflow:auto"><div class="hd"><h3>API-Zugänge (Tokens)</h3><div class="act"><button class="btn sm pri" type="button" id="m88nt">${ic("plus")} Neuer Zugang</button></div></div><div class="bd fr">
        <table class="t"><thead><tr><th>Name</th><th>Recht</th><th>Erstellt</th><th>Zuletzt</th><th>Status</th><th></th></tr></thead><tbody>${api_t.map(tokRow).join("") || `<tr><td colspan="6" class="empty">Noch kein Zugang angelegt.</td></tr>`}</tbody></table>
        <div class="row" style="flex-wrap:wrap;gap:8px"><button class="btn sm" type="button" id="m88jey">Beispiel-Datei für Dr. Jey (Downloads)</button>
          ${c.ics ? `<button class="btn sm" type="button" id="m88ics">Kalender-Abo-Link erzeugen</button>` : ""}${expButtons("m88_api", {}, true)}</div></div></div>
      <div class="card"><div class="hd"><h3>Zugriffsprotokoll</h3><div class="act"><button class="btn sm" type="button" id="m88lg">${logShow ? "Ausblenden" : "Anzeigen"}</button>${logShow ? `<button class="btn sm ghost danger" type="button" id="m88lc">Leeren</button>` : ""}</div></div>
        ${logShow ? `<div class="bd" style="max-height:340px;overflow:auto"><table class="t"><thead><tr><th>Zeit</th><th>IP</th><th>Anfrage</th><th class="r">Status</th><th>Zugang</th></tr></thead><tbody>
          ${lg.map(r => `<tr><td class="small num">${dt(r.zeit)}</td><td class="small">${esc(r.ip)}</td><td class="small"><b>${esc(r.methode)}</b> ${esc(r.pfad)}</td>
            <td class="r"><span class="badge ${r.status >= 400 ? "bad" : "ok"}">${r.status}</span></td><td class="small">${esc(r.token || "")}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">Noch keine Zugriffe.</td></tr>`}</tbody></table></div>` : `<div class="bd small muted">Jeder Zugriff wird mit Zeit, IP, Anfrage und Ergebnis protokolliert (letzte 3000).</div>`}</div>
      <div class="card"><div class="hd"><h3>Dokumentation & Beispiele</h3></div><div class="bd">${exampleBlock(base)}</div></div>
      </div></div>`;
    bindCommon(el);
    const again = () => render(el);
    $("#m88sv", el).onclick = async () => {
      const r = await api("/api/m88/save", {aktiv: $("#m88on", el).checked, modus: $("#m88mo", el).value, port: Math.round(pnum($("#m88po", el).value)) || 8780,
        rate: Math.round(pnum($("#m88ra", el).value)) || 120, geraet_tage: Math.round(pnum($("#m88gt", el).value)) || 365});
      if (r && r.ok) toast(r.laeuft ? "Schnittstelle läuft" : "Schnittstelle aus");
      again();
    };
    $("#m88nt", el).onclick = () => newToken(again);
    const pb = $("#m88pair", el); if (pb) pb.onclick = () => pairDlg(again);
    $("#m88jey", el).onclick = async () => { const r = await api("/api/m88/jey", {}); if (r && r.ok) toast("Gespeichert: " + r.path); };
    const ib = $("#m88ics", el); if (ib) ib.onclick = async () => {
      const r = await api("/api/m88/token/new", {name: "Kalender-Abo", recht: "lesen", typ: "ics"});
      if (!r || !r.ok) return;
      const u = base + "/ics/" + r.token + ".ics";
      showToken(r.token, again, `<div class="small muted" style="margin-top:6px">Kalender-Abo-Adresse (im Handy-Kalender als „Abonnierter Kalender“ eintragen):</div>${copyBox("m88icsu", u)}`);
    };
    $("#m88lg", el).onclick = () => { logShow = !logShow; again(); };
    const lc = $("#m88lc", el); if (lc) lc.onclick = async () => { await api("/api/m88/log/clear", {}); toast("Protokoll geleert"); again(); };
    $$("[data-m88rv]", el).forEach(b => b.onclick = async () => { await api("/api/m88/token/revoke", {id: +b.dataset.m88rv}); toast("Zugang widerrufen"); again(); });
    $$("[data-m88del]", el).forEach(b => b.onclick = async () => { await api("/api/m88/token/delete", {id: +b.dataset.m88del}); toast("Zugang entfernt"); again(); });
    $$("[data-m88nd]", el).forEach(b => b.onclick = async () => { await api("/api/m88/notiz/set", {id: +b.dataset.m88nd, erledigt: true}); again(); });
    $$("[data-m88nx]", el).forEach(b => b.onclick = async () => { await api("/api/m88/notiz/set", {id: +b.dataset.m88nx, loeschen: true}); again(); });
    selectify({kind: "m88tok", rows: "tr[data-m88t]", root: el, id: "data-m88t", rerender: again, actions: [
      {label: "Widerrufen", run: async ids => { for (const i of ids) await api("/api/m88/token/revoke", {id: +i}); toast(ids.length + " widerrufen"); }},
      {label: "Entfernen", cls: "danger", run: async ids => { await api("/api/m88/token/delete", {ids: ids.map(Number)}); toast(ids.length + " entfernt"); }}]});
  }

  EXT.settings.push({key: "m88", label: "Schnittstelle & Handy", render});

  // dashboard: notes sent from the phone
  EXT.dash.push(el => {
    const m = S.m88; if (!m || !(m.notizen || []).length) return;
    const card = document.createElement("div"); card.className = "card"; card.id = "m88card"; card.style.marginBottom = "16px";
    const draw = list => {
      if (!list.length) { card.remove(); return; }
      card.innerHTML = `<div class="hd"><h3>Notizen vom Handy</h3><div class="act"><button class="btn sm ghost" type="button" id="m88go">Alle</button></div></div>
        <div class="bd"><table class="t"><tbody>${list.slice(0, 6).map(n => `<tr><td class="small muted" style="width:96px">${dt(n.zeit)}</td><td>${esc(n.text)}</td>
          <td class="r"><button class="btn sm" type="button" data-m88dn="${n.id}">Erledigt</button></td></tr>`).join("")}</tbody></table></div>`;
      $("#m88go", card).onclick = () => { try { setTab = "m88"; } catch (e) {} go("set"); };
      $$("[data-m88dn]", card).forEach(b => b.onclick = async () => { const r = await api("/api/m88/notiz/set", {id: +b.dataset.m88dn, erledigt: true}); if (!r || r.ok === false) return;
        m.notizen = m.notizen.filter(n => n.id != b.dataset.m88dn); draw(m.notizen); });
    };
    el.appendChild(card); draw(m.notizen);
  });
})();
