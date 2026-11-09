// PA Rechnung v2.4.0 - UI-Modul m94_webbank: Bank-Login im Browser (z. B. C24 Bank, ohne FinTS)
// Knopf im Bank-Abgleich und an der Kontostand-Karte, Live-Dialog waehrend des Logins,
// Karte "Bank-Login im Browser" im Einstellungs-Reiter Bankabruf.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  let busy = false;
  const bankName = () => (S.wb && S.wb.bank) || "Bank";

  const sumHtml = e => {
    if (!e || !e.zeit) return `<div class="small muted">Noch kein Abruf.</div>`;
    const sal = e.saldo && typeof e.saldo === "object" ? e.saldo.saldo : null;
    return `<div class="small"><span class="badge ok">OK</span> ${dde(e.zeit.slice(0,10))} ${e.zeit.slice(11,16)}${e.von ? ` · ${dde(e.von)} – ${dde(e.bis)}` : ""}${e.konto ? " · " + esc(e.konto) : ""}</div>
      <div class="small" style="margin-top:4px">${e.abgerufen} Umsätze gelesen · <b>${e.neu}</b> neu · ${e.doppelt} schon bekannt · ${(e.bezahlt||[]).length} Rechnung(en) automatisch bezahlt · <b>${e.offen}</b> zur Prüfung${sal != null ? ` · Kontostand <b>${eur(sal)}</b>` : ""}</div>
      ${e.erkennung === "seitentext" ? `<div class="small" style="color:var(--warn);margin-top:4px">Aus dem sichtbaren Seitentext erkannt – bitte im Bank-Abgleich prüfen (nichts automatisch gebucht).</div>` : ""}`;
  };

  function stHtml(st){
    const e = st.erkannt || {}, ok = e.saldo || e.umsaetze;
    const step = (on, done, t) => `<div style="display:flex;gap:10px;align-items:flex-start;margin:6px 0;${on||done?"":"opacity:.55"}">
      <span style="flex:none;width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;
        background:${done?"var(--ok)":on?"var(--acc)":"var(--line2)"};color:#fff">${done?"✓":on?"…":""}</span><div>${t}</div></div>`;
    if (st.state === "fehler") return `<div style="color:var(--bad)">${esc(st.error)}</div>`;
    if (st.state === "abgebrochen") return `<div class="small" style="color:var(--warn)">${esc(st.error || "Abgebrochen.")}</div>`;
    return step(true, st.state !== "start", `Bank-Fenster geöffnet`) +
      step(st.state === "browser" && !st.pakete, st.pakete > 0, `<b>Jetzt im Bank-Fenster anmelden.</b><div class="small muted">${esc(st.hinweis || "")}</div>`) +
      step(st.pakete > 0 && !ok, !!ok, `Konto öffnen – Umsätze werden mitgelesen${st.pakete ? ` <span class="small muted">(${st.pakete} Datenpakete)</span>` : ""}<div class="small muted">Für ältere Umsätze im Bank-Fenster einfach weiter nach unten scrollen.</div>`) +
      (ok ? `<div class="card" style="padding:10px 12px;margin-top:10px"><div class="small muted">Erkannt</div>
        ${e.saldo ? `<div style="font:700 22px var(--disp)" class="num">${eur(e.saldo.saldo)}</div>` : ""}
        <div class="small">${e.umsaetze ? `<b>${e.umsaetze}</b> Umsätze · ${dde(e.von)} – ${dde(e.bis)}` : "noch keine Umsätze"}${e.konto ? " · " + esc(e.konto) : ""}</div></div>` : "");
  }

  async function wbAbruf(){
    if (busy) { toast("Bank-Login läuft bereits …"); return; }
    busy = true;
    try {
      const st0 = await api("/api/wb/start", {});
      if (!st0 || st0.ok === false) return;
      if (st0.state === "fehler") { await modal("Bank-Login", `<div style="color:var(--bad)">${esc(st0.error)}</div>`); return; }
      const tok = st0.token; let st = st0, result = null, stable = 0, lastP = -1, auto = true, taken = false;
      const take = async mb => {
        const r = await api("/api/wb/uebernehmen", {token: tok});
        if (!r || r.ok === false) { if (mb) { const b = $("#wbst", mb); if (b && r && r.error) b.insertAdjacentHTML("beforeend", `<div class="small" style="color:var(--warn);margin-top:8px">${esc(r.error)}</div>`); } return false; }
        result = r.ergebnis; return true;
      };
      const r = await modal(`Kontostand & Umsätze – ${st0.bank || bankName()}`, `<div class="fr nokeep">
          <div id="wbst">${stHtml(st)}</div>
          <label class="small" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="wbauto" checked> automatisch übernehmen, sobald Kontostand und Umsätze da sind</label>
          <div class="small muted">Das Programm sieht weder Passwort noch PIN – du meldest dich im Bank-Fenster selbst an. Gelesen wird nur, was die Bank-Seite dir anzeigt.</div></div>`,
        [{label: "Abbrechen", onClick: async () => { await api("/api/wb/abbrechen", {token: tok}, {quiet: true}); }},
         {label: "Übernehmen", cls: "pri", value: 1, onClick: async mb => taken || take(mb)}],
        false, async mb => {
          const cb = $("#wbauto", mb); if (cb) cb.onchange = () => { auto = cb.checked; };
          while (mb.isConnected) {
            await new Promise(res => setTimeout(res, 1000));
            if (!mb.isConnected) break;
            const s2 = await api("/api/wb/status?token=" + encodeURIComponent(tok), undefined, {quiet: true});
            if (!s2 || s2.ok === false) continue;
            st = s2; const b = $("#wbst", mb); if (b) b.innerHTML = stHtml(st);
            if (st.state === "fertig") { result = st.ergebnis; taken = true; const p = $(".mf .pri", mb); if (p) p.click(); break; }
            if (st.state !== "browser") continue;
            const e = st.erkannt || {};
            stable = st.pakete === lastP ? stable + 1 : 0; lastP = st.pakete;
            // close through the modal button (not mb.remove) so modal() resolves and busy resets
            if (auto && e.saldo && e.umsaetze && stable >= 4) { if (await take(mb)) { taken = true; const p = $(".mf .pri", mb); if (p) p.click(); break; } }
          }
        });
      if (!result) { if (r) toast("Nichts übernommen", true); return; }
      await reload();
      await modal(`${st0.bank || bankName()}: Abruf abgeschlossen`, `<div class="fr">${sumHtml(result)}
        ${result.offen ? `<div class="hl small" style="margin-top:8px">${result.offen} Buchung(en) stehen jetzt im Bank-Abgleich zur Bestätigung bereit.</div>` : ""}</div>`);
      if (view === "bank") vBank(); else if (view === "dash") vDash();
    } finally { busy = false; }
  }
  window.wbAbruf = wbAbruf;

  // ---------- Bank-Abgleich: main button
  EXT.after.push(n => {
    if (n !== "vBank" || !S.wb || !S.wb.eingerichtet) return;
    const act = $("#main .ph .act"); if (!act || $("#wbbtn")) return;
    const b = document.createElement("button"); b.className = "btn pri"; b.id = "wbbtn";
    b.innerHTML = `${ic("sync")} Kontostand & Umsätze holen (${esc(bankName())})`;
    b.title = "Bank-Fenster öffnen, anmelden (QR-Code / App-Freigabe) – das Programm liest Kontostand und Umsätze mit";
    b.onclick = wbAbruf;
    $$(".btn.pri", act).forEach(x_ => x_.classList.remove("pri"));
    const f = $("#ftsbtn"); if (f && !(S.fints || {}).eingerichtet) f.remove();
    act.prepend(b);
  });

  // ---------- dashboard: button on the balance card
  EXT.after.push(async n => {
    if (n !== "vDash" || !S.wb || !S.wb.eingerichtet) return;
    // dashboard tiles render asynchronously; the balance tile is found by its heading
    const find = () => $$("#main .card .hd h3").find(h => h.textContent.trim() === "Kontostand");
    for (let i = 0; i < 50 && !find(); i++) await new Promise(r => setTimeout(r, 100));
    const h3 = find(); if (!h3 || $("#wbdash")) return;
    const hd = h3.closest(".hd"); let act = $(".act", hd);
    if (!act) { act = document.createElement("div"); act.className = "act"; hd.appendChild(act); }
    const b = document.createElement("button"); b.className = "btn sm pri"; b.id = "wbdash"; b.type = "button";
    b.textContent = `Von ${bankName()} holen`; b.title = "Kontostand und Umsätze per Bank-Login abrufen";
    b.onclick = e => { e.stopPropagation(); wbAbruf(); };
    act.prepend(b);
  });

  // ---------- settings card (tab Bankabruf, top)
  async function card(host){
    const c = await api("/api/wb/config", undefined, {quiet: true}); if (!c) return;
    host.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>${esc(c.bank || "Bank")} – Bank-Login im Browser</h3>
        <div class="act">${c.eingerichtet ? `<span class="badge ok"><span class="dot"></span>bereit</span>` : `<span class="badge warn">Adresse fehlt</span>`}</div></div>
      <div class="bd"><div class="grid g2" style="align-items:start">
        <div class="fr">
          <div class="small">So läuft der Abruf: Das Programm öffnet das normale Online-Banking ${c.bank ? "der <b>" + esc(c.bank) + "</b>" : "deiner Bank"} in einem eigenen Fenster. Du meldest dich dort wie immer an${c.blz === "50024024" ? " – <b>QR-Code mit der C24-App scannen</b> bzw. in der App freigeben" : ""}. Das Programm liest Kontostand und Umsätze mit, übernimmt sie in den Bank-Abgleich und schließt das Fenster.</div>
          <label class="f">Online-Banking-Adresse<input class="in" id="wburl" value="${esc(c.url)}" placeholder="https://…"></label>
          <div class="small muted">Browser: ${c.browser ? `<b>${esc(c.browser_name)}</b>` : `<span style="color:var(--bad)">kein Edge/Chrome gefunden</span>`} · eigenes Profil im Datenordner (Bankzugang\\browser)</div>
          <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="wbprof" ${c.profil_behalten ? "checked" : ""}> Gerät merken (Login-Fenster behält Cookies – die Bank fragt seltener nach)</label>
          <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="wbauto2" ${c.auto ? "checked" : ""}> Sichere Zuordnungen automatisch buchen (wie beim FinTS-Abruf)</label>
          <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn pri" style="flex:none" id="wbgo" type="button" ${c.eingerichtet && c.browser ? "" : "disabled"}>${ic("sync")} Jetzt Kontostand & Umsätze holen</button>
            <button class="btn" style="flex:none" id="wbsave" type="button">${ic("save")} Speichern</button>
            ${c.profil_da ? `<button class="btn sm ghost danger" style="flex:none" id="wbdel" type="button">Gemerktes Gerät löschen</button>` : ""}</div>
        </div>
        <div class="card" style="padding:10px"><div class="small" style="font-weight:600;margin-bottom:4px">Letzter Abruf</div>${sumHtml(c.log)}
          <div class="small muted" style="margin-top:8px">Rohdaten der letzten 5 Abrufe: Datenordner\\Bankzugang\\rohdaten – nur für die Fehlersuche, falls die Bank ihre Seite umbaut.</div></div>
      </div></div></div>`;
    const save = async quiet => { const r = await api("/api/wb/config/save", {url: $("#wburl", host).value, profil_behalten: $("#wbprof", host).checked, auto: $("#wbauto2", host).checked});
      if (r && r.ok !== false) { if (!quiet) toast("Gespeichert"); await reload(); } return r; };
    $("#wbsave", host).onclick = async () => { await save(); card(host); };
    $("#wbgo", host).onclick = async () => { const r = await save(true); if (r && r.ok !== false) wbAbruf(); };
    const dl = $("#wbdel", host); if (dl) dl.onclick = async () => { const r = await api("/api/wb/profil_loeschen", {}); if (r && r.ok) { toast("Gemerktes Gerät gelöscht"); card(host); } };
    const ss = $("#ssave"); if (ss) ss.addEventListener("click", () => save(true));
  }
  EXT.after.push(async n => {
    if (n !== "vSettings" || setTab !== "fints") return;
    // the Bankabruf tab renders asynchronously: wait for its slot (only there for banks without FinTS)
    for (let i = 0; i < 40 && !$("#wbslot") && !$("#fts_grid"); i++) await new Promise(r => setTimeout(r, 75));
    const slot = $("#wbslot"); if (!slot || $("#wbhost")) return;
    const h = document.createElement("div"); h.id = "wbhost"; slot.appendChild(h);
    card(h);
  });
})();
