// PA Rechnung v2.3.0 - Bankabruf ueber PSD2 (Enable Banking) fuer Banken ohne FinTS, z. B. C24 Bank
// v2.3.0: Bank als Auswahlliste (wird automatisch von Enable Banking geladen, sobald App-ID + Schluessel da sind)
// Karte im Einstellungs-Reiter "Bankabruf", Knopf im Bank-Abgleich.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const ebSum = e => {
    if (!e || !e.zeit) return `<div class="small muted">Noch kein Abruf.</div>`;
    if (e.ok === false) return `<div class="small"><span class="badge bad">Fehler</span> ${dde(e.zeit.slice(0,10))} ${e.zeit.slice(11,16)}</div><div class="small" style="color:var(--bad);margin-top:4px">${esc(e.fehler||"")}</div>`;
    return `<div class="small"><span class="badge ok">OK</span> ${dde(e.zeit.slice(0,10))} ${e.zeit.slice(11,16)} · ${dde(e.von)} – ${dde(e.bis)}${e.konto?" · "+esc(e.konto):""}</div>
      <div class="small" style="margin-top:4px">${e.abgerufen} Umsätze · <b>${e.neu}</b> neu · ${e.doppelt} schon bekannt · ${(e.bezahlt||[]).length} Rechnung(en) automatisch bezahlt · <b>${e.offen}</b> zur Prüfung${e.saldo?` · Kontostand ${eur(e.saldo.saldo)}`:""}</div>
      ${(e.log||[]).length?`<details style="margin-top:6px"><summary class="small muted" style="cursor:pointer">Protokoll</summary><pre class="small" style="white-space:pre-wrap">${esc(e.log.join("\n"))}</pre></details>`:""}`;
  };

  async function ebAbruf(tage){
    toast("Umsätze werden über PSD2 abgerufen …");
    const r = await api("/api/eb/abruf", tage ? {tage} : {});
    if (!r || r.ok === false) { if (view === "bank") vBank(); return; }
    await reload();
    await modal("Bankabruf abgeschlossen", `<div class="fr">${ebSum(r)}${r.offen?`<div class="hl small" style="margin-top:8px">${r.offen} Buchung(en) stehen jetzt im Bank-Abgleich zur Bestätigung bereit.</div>`:""}</div>`);
    if (view === "bank") vBank(); else go("bank");
  }
  window.ebAbruf = ebAbruf;

  async function card(host){
    const c = await api("/api/eb/config", undefined, {quiet:true}); if (!c) return;
    const bank = c.bank || "C24 Bank";
    host.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>${esc(bank)} & andere Banken ohne FinTS – Abruf über PSD2</h3><div class="act">${c.verbunden?`<span class="badge ok"><span class="dot"></span>verbunden bis ${dde(c.gueltig_bis)||"?"}</span>`:c.eingerichtet?`<span class="badge warn">nicht verbunden</span>`:`<span class="badge">nicht eingerichtet</span>`}</div></div>
      <div class="bd"><div class="grid g2" style="align-items:start">
      <div class="fr">
        <div class="hl small">Die <b>C24 Bank bietet kein FinTS/HBCI</b> an – der FinTS-Zugang links/oben funktioniert dort nicht. Der Abruf läuft stattdessen über die gesetzliche PSD2-Schnittstelle der Bank. Vermittler ist der Kontoinformationsdienst <b>Enable Banking</b> (eigene, kostenlose App-Registrierung für die eigenen Konten – Bedingungen beim Anbieter prüfen). Anleitung: Handbuch Kapitel 13.</div>
        <div class="small"><b>1.</b> Bei Enable Banking ein Konto anlegen, eine Anwendung erstellen und als Weiterleitungs-Adresse (Redirect URL) eintragen:
          <div style="font:600 12.5px Consolas,monospace;user-select:all;margin:4px 0;padding:6px 8px;background:var(--panel2);border-radius:6px">${esc(c.redirect||c.default_redirect)}</div>
          <button class="btn sm" id="ebcp" type="button">Enable Banking öffnen</button></div>
        <label class="f"><span><b>2.</b> Application-ID</span><input class="in" id="ebapp" value="${esc(c.app_id)}" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" autocomplete="off"></label>
        <div class="row" style="align-items:center"><button class="btn sm" style="flex:none" id="ebkey" type="button">${ic("clip")} Privaten Schlüssel (.pem) laden</button>
          <span class="small">${c.key_gesetzt?(c.key_ok?`<span style="color:var(--ok)">✓ Schlüssel gespeichert (verschlüsselt)</span>`:`<span style="color:var(--bad)">Schlüssel nicht lesbar – neu laden</span>`):`<span class="muted">noch kein Schlüssel</span>`}</span></div>
        <details class="small"><summary style="cursor:pointer" class="muted">Weiterleitungs-Adresse ändern</summary><input class="in" id="ebred" value="${esc(c.redirect)}" style="margin-top:6px"><div class="muted" style="margin-top:4px">Muss genau so bei Enable Banking eingetragen sein. Bei http://localhost:${esc(String((c.default_redirect.match(/:(\d+)/)||[])[1]||""))} übernimmt das Programm die Freigabe automatisch, sonst die Adresse aus dem Browser einfügen.</div></details>
      </div>
      <div class="fr">
        <div class="row" style="align-items:flex-end"><label class="f"><span><b>3.</b> Bank</span><select class="in" id="ebbank"><option value="${esc(bank)}" selected>${esc(bank)}</option></select></label>
          <button class="btn sm" style="flex:none" id="ebbls" type="button" title="Bankliste von Enable Banking neu laden">Liste aktualisieren</button></div>
        <div class="small muted" id="ebblh" style="margin-top:-6px">${c.app_id && c.key_ok ? "Bankliste wird geladen …" : "Die Bankliste erscheint, sobald Application-ID und Schlüssel (Schritt 2) gespeichert sind."}</div>
        <div class="row" style="align-items:center"><button class="btn pri" style="flex:none" id="ebcon" type="button">${ic("sync")} <b>4.</b> Mit ${esc(bank)} verbinden</button><span class="small muted" id="ebcst"></span></div>
        <div id="ebpaste" style="display:none" class="fr"><label class="f">Adresse aus der Browser-Adresszeile nach der Freigabe einfügen<input class="in" id="ebcode" placeholder="https://…?code=…&state=…"></label><div><button class="btn sm pri" id="ebcodeok" type="button">Übernehmen</button></div></div>
        ${(c.konten||[]).length?`<label class="f">Konto<select class="in" id="ebkto">${c.konten.map(k=>`<option value="${esc(k.uid)}" ${k.uid===c.konto?"selected":""}>${esc(k.iban||k.uid)}${k.name?" · "+esc(k.name):""}</option>`).join("")}</select></label>`:""}
        <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ebauto" ${c.auto?"checked":""}> Sichere Zuordnungen automatisch buchen (wie beim FinTS-Abruf)</label>
        <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ebaa" ${c.auto_abruf?"checked":""}> Einmal täglich automatisch abrufen (solange die Freigabe gilt)</label>
        <div class="row"><button class="btn" style="flex:none" id="ebsave" type="button">${ic("save")} Speichern</button>${c.verbunden?`<button class="btn pri" style="flex:none" id="ebnow" type="button">${ic("sync")} Jetzt abrufen</button><button class="btn ghost danger sm" style="flex:none" id="ebdis" type="button">Verbindung trennen</button>`:""}</div>
        <div class="small muted">Die Freigabe der Bank gilt höchstens 180 Tage (je nach Bank auch 90) – danach einmal neu verbinden. Ohne Abruf geht weiterhin der CSV-/PDF-Import im Bank-Abgleich.</div>
        <div class="card" style="padding:10px"><div class="small" style="font-weight:600;margin-bottom:4px">Letzter Abruf</div>${ebSum(c.log)}</div>
      </div></div></div></div>`;
    const v = () => ({app_id:$("#ebapp",host).value.trim(), bank:$("#ebbank",host).value.trim(), redirect:($("#ebred",host).value||"").trim() || c.default_redirect,
      konto:($("#ebkto",host)||{}).value, auto:$("#ebauto",host).checked, auto_abruf:$("#ebaa",host).checked});
    const save = async quiet => { const r = await api("/api/eb/config/save", v(), {quiet:!!quiet}); if (r && r.ok && !quiet) toast("Gespeichert"); return r; };
    $("#ebcp",host).onclick = () => api("/api/eb/openurl", {});
    $("#ebsave",host).onclick = async () => { await save(); await reload(); card(host); };
    const ss = $("#ssave"); if (ss) ss.addEventListener("click", () => save(true));
    $("#ebkey",host).onclick = () => pickFiles(".pem,.key,.txt", async fs => { await save(true); const r = await upload("/api/upload/ebkey", fs[0]); if (r && r.ok) { toast("Schlüssel gespeichert"); card(host); } else toast((r&&r.error)||"Schlüssel nicht lesbar", true); });
    const loadBanks = async quiet => {
      if (!quiet) await save(true);
      const r = await api("/api/eb/banks", undefined, {quiet:!!quiet}); const h = $("#ebblh",host);
      if (!r || !r.banken || !r.banken.length) { if (h) h.textContent = "Bankliste konnte nicht geladen werden – App-ID und Schlüssel prüfen, dann „Liste aktualisieren“."; return; }
      const sel = $("#ebbank",host); if (!sel) return;
      const cur = sel.value, names = [...new Set(r.banken.map(b => b.name).filter(Boolean))].sort((a, b) => a.localeCompare(b, "de"));
      if (cur && !names.includes(cur)) names.unshift(cur);
      sel.innerHTML = names.map(n => { const b = r.banken.find(x => x.name === n); const t = b && b.max_tage ? " (Freigabe bis " + Math.round(b.max_tage / 86400) + " Tage)" : "";
        return `<option value="${esc(n)}" ${n===cur?"selected":""}>${esc(n + t)}</option>`; }).join("");
      if (h) h.textContent = `${names.length} Banken von Enable Banking geladen.`;
      if (!quiet) toast(`${names.length} Banken geladen`);
    };
    $("#ebbls",host).onclick = () => loadBanks(false);
    if (c.app_id && c.key_ok) loadBanks(true);
    $("#ebcon",host).onclick = async () => {
      const r0 = await save(true); if (!r0 || r0.ok === false) return;
      const r = await api("/api/eb/connect", v()); if (!r || r.ok === false) return;
      $("#ebcst",host).textContent = "Bitte im Browser bei der Bank anmelden und freigeben …";
      $("#ebpaste",host).style.display = r.lauscht ? "none" : "";
      if (!r.lauscht) { $("#ebcst",host).textContent = "Nach der Freigabe die Adresse aus der Browserzeile unten einfügen."; return; }
      for (let i = 0; i < 300; i++) {
        await new Promise(res => setTimeout(res, 2000));
        if (!host.isConnected) return;
        const st = await api("/api/eb/config", undefined, {quiet:true}); if (!st) continue;
        if (st.callback && st.callback.fehler) { $("#ebcst",host).innerHTML = `<span style="color:var(--bad)">${esc(st.callback.fehler)}</span>`; $("#ebpaste",host).style.display = ""; return; }
        if (st.verbunden && st.session !== c.session) { toast(`Mit ${bank} verbunden – ${(st.konten||[]).length} Konto/Konten`); await reload(); card(host); return; }
        if (!st.callback.wartet && i > 3 && !st.verbunden) { $("#ebpaste",host).style.display = ""; }
      }
    };
    $("#ebcodeok",host).onclick = async () => { const r = await api("/api/eb/code", {url:$("#ebcode",host).value}); if (r && r.ok) { toast(`Verbunden – ${r.konten.length} Konto/Konten`); await reload(); card(host); } };
    const nw = $("#ebnow",host); if (nw) nw.onclick = async () => { await save(true); ebAbruf(); };
    const ds = $("#ebdis",host); if (ds) ds.onclick = async () => { await api("/api/eb/trennen", {}); await reload(); card(host); toast("Verbindung getrennt"); };
  }

  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "fints") return;
    const page = $("#main .page"); if (!page || $("#ebhost")) return;
    const h = document.createElement("div"); h.id = "ebhost"; page.appendChild(h); card(h);
  });

  EXT.after.push(n => {
    if (n !== "vBank") return;
    const act = $("#main .ph .act"); const p = S.psd2 || {};
    if (!act || $("#ebbtn") || !p.eingerichtet) return;
    const b = document.createElement("button"); b.className = "btn" + ((S.fints||{}).eingerichtet ? "" : " pri"); b.id = "ebbtn";
    b.innerHTML = `${ic("sync")} ${esc(p.bank || "PSD2")} abrufen`;
    b.title = p.verbunden ? `Umsätze von ${p.bank} über PSD2 holen (Freigabe bis ${dde(p.gueltig_bis)})` : "Noch nicht mit der Bank verbunden";
    b.onclick = async () => { if (!p.verbunden) { if (await confirmBox(`Die Freigabe von ${p.bank} fehlt oder ist abgelaufen. Jetzt in den Einstellungen verbinden?`, "Verbinden")) { try { setTab = "fints"; } catch (e) {} go("set"); } return; } ebAbruf(); };
    const f = $("#ftsbtn"); if (f && !(S.fints||{}).eingerichtet) f.remove();
    act.prepend(b);
  });
})();
