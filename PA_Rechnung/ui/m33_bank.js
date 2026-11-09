// Pfeiffer-Audio Rechnung v2.4.0 - UI-Modul m33_bank: Bankabruf per FinTS (PIN/TAN)
// Einstellungen-Reiter "Bankabruf" (Bank aus der Bank-Bibliothek waehlen, Server/TAN/Konto per Auswahl), Knopf im Bank-Abgleich, TAN-Dialog, Protokoll.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  let ftsBusy = false;

  // ---------- small helpers ----------
  const fLogHtml = lg => (lg && lg.length) ? `<details style="margin-top:8px"><summary class="small muted" style="cursor:pointer">Protokoll anzeigen</summary><pre class="small" style="white-space:pre-wrap;margin:6px 0 0;max-height:220px;overflow:auto;background:var(--panel2,rgba(0,0,0,.03));padding:8px;border-radius:8px">${esc(lg.join("\n"))}</pre></details>` : "";

  function fSummary(e){
    if (!e) return `<div class="small muted">Noch kein Abruf.</div>`;
    if (e.ok === false) return `<div class="small"><span class="badge bad">Fehler</span> ${esc(dde((e.zeit||"").slice(0,10)))} ${esc((e.zeit||"").slice(11,16))}</div><div class="small" style="margin-top:4px;color:var(--bad)">${esc(e.fehler||"")}</div>${fLogHtml(e.log)}`;
    const paid = (e.bezahlt||[]).map(b=>`<div class="small">✓ ${esc(b.nr)} · ${esc(b.name)} · ${eur(b.betrag)}</div>`).join("");
    const fix = (e.fixkosten||[]).map(b=>`<div class="small">✓ Fixkosten ${esc(b.name)} · ${eur(b.betrag)}</div>`).join("");
    return `<div class="small"><span class="badge ok">OK</span> ${esc(dde((e.zeit||"").slice(0,10)))} ${esc((e.zeit||"").slice(11,16))} · Zeitraum ${dde(e.von)} – ${dde(e.bis)}${e.konto?" · "+esc(e.konto):""}</div>
      <div class="small" style="margin-top:4px">${e.abgerufen} Umsätze geholt · <b>${e.neu}</b> neu · ${e.doppelt} schon bekannt · ${(e.bezahlt||[]).length} Rechnung(en) automatisch bezahlt · ${(e.fixkosten||[]).length} Fixkosten verknüpft · <b>${e.offen}</b> zur Prüfung${e.saldo?` · Kontostand ${eur(e.saldo.saldo)}`:""}</div>
      ${paid||fix?`<div style="margin-top:4px">${paid}${fix}</div>`:""}${fLogHtml(e.log)}`;
  }

  // ---------- dialogs ----------
  async function askPin(cfg){
    let pin = "", merken = false;
    const r = await modal("PIN für den Bankabruf", `<div class="fr nokeep">
      <label class="f">Online-Banking-PIN<input class="in" type="password" id="ftpin" autocomplete="off"></label>
      ${cfg.pin_speichern?`<label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ftpm"> PIN geschützt speichern (Windows-Verschlüsselung)</label>`:`<div class="small muted">Die PIN wird nicht gespeichert (Einstellung „PIN bei jedem Abruf fragen“).</div>`}</div>`,
      [{label:"Abbrechen"},{label:"Weiter", cls:"pri", value:1, onClick: async mb => { pin = $("#ftpin",mb).value; merken = !!($("#ftpm",mb)||{}).checked; if (!pin) { toast("Bitte PIN eingeben", true); return false; } }}],
      false, mb => { const i = $("#ftpin",mb); if (i) i.onkeydown = e => { if (e.key === "Enter") $(".mf .pri", mb).click(); }; });
    return r ? {pin, merken} : null;
  }

  async function askFrage(f){
    if (f.art === "wahl") {
      let w = "";
      const r = await modal(f.titel || "Bitte wählen", `<div class="fr nokeep"><div class="small">${esc(f.text||"")}</div>
        <select class="in" id="ftw">${(f.optionen||[]).map(o=>`<option value="${esc(o.id)}">${esc(o.label)}</option>`).join("")}</select></div>`,
        [{label:"Abbrechen"},{label:"Weiter", cls:"pri", value:1, onClick: async mb => { w = $("#ftw",mb).value; }}]);
      return r ? {wahl:w} : {abbrechen:true};
    }
    if (f.art === "tan") {
      let tan = "";
      const txt = `<div class="small" style="white-space:pre-line;margin-bottom:8px">${esc(f.text||"")}</div>`;
      const img = f.bild ? `<div style="text-align:center;margin:8px 0"><img src="${f.bild}" alt="TAN-Grafik" style="max-width:260px;image-rendering:pixelated;background:#fff;padding:6px;border-radius:8px;border:1px solid var(--line)"></div>` : "";
      const hh = f.hhduc ? `<div class="small" style="margin:6px 0">chipTAN – Start-Code für die manuelle Eingabe am TAN-Generator:<div style="font:600 15px Consolas,monospace;margin-top:3px">${esc(f.hhduc)}</div><div class="muted">Die Flicker-Grafik wird hier nicht angezeigt – bequemer ist pushTAN oder photoTAN.</div></div>` : "";
      if (f.decoupled) {
        const r = await modal(f.titel || "Freigabe in der Banking-App", `<div class="fr nokeep">${txt}${img}
          <div class="hl small">Bitte den Auftrag in deiner Banking-/TAN-App freigeben und danach hier auf <b>In der App bestätigt</b> klicken.</div></div>`,
          [{label:"Abbrechen"},{label:"In der App bestätigt → Weiter", cls:"pri", value:1}]);
        return r ? {weiter:true} : {abbrechen:true};
      }
      const r = await modal(f.titel || "TAN eingeben", `<div class="fr nokeep">${txt}${img}${hh}
        <label class="f">TAN<input class="in num" id="fttan" autocomplete="one-time-code" inputmode="numeric" style="font-size:18px;letter-spacing:2px"></label></div>`,
        [{label:"Abbrechen"},{label:"TAN senden", cls:"pri", value:1, onClick: async mb => { tan = $("#fttan",mb).value.trim(); if (!tan) { toast("Bitte TAN eingeben", true); return false; } }}],
        false, mb => { const i = $("#fttan",mb); if (i) i.onkeydown = e => { if (e.key === "Enter") $(".mf .pri", mb).click(); }; });
      return r ? {tan} : {abbrechen:true};
    }
    return {abbrechen:true};
  }

  // runs a whole FinTS session (modus "abruf" | "konten"); returns final status or null
  async function ftsRun(modus, extra){
    if (ftsBusy) { toast("Bankabruf läuft bereits …"); return null; }
    ftsBusy = true;
    try {
      const cfg = await api("/api/fints/config");
      if (!cfg.lib_ok) { toast("Für den Bankabruf bitte einmal build_exe.bat ausführen (neue Bibliothek fints).", true); return null; }
      let body = Object.assign({modus}, extra||{});
      toast(modus === "konten" ? "Verbinde mit der Bank …" : "Umsätze werden von der Bank abgerufen …");
      let st = await api("/api/fints/start", body);
      if (st && st.state === "pin") {
        const p = await askPin(cfg); if (!p) return null;
        body = Object.assign(body, {pin:p.pin, pin_merken:p.merken});
        st = await api("/api/fints/start", body);
      }
      for (let i = 0; i < 400 && st && st.ok !== false; i++) {
        if (st.state === "running") { st = await api("/api/fints/status?wait=20&token=" + encodeURIComponent(st.token)); continue; }
        if (st.state === "frage") { const a = await askFrage(st.frage || {}); st = await api("/api/fints/answer", Object.assign({token:st.token}, a)); continue; }
        break;
      }
      if (!st || st.ok === false) return null;
      if (st.state === "fehler") { await modal("Bankabruf fehlgeschlagen", `<div class="fr"><div style="color:var(--bad)">${esc(st.error)}</div>${fLogHtml(st.log)}</div>`); return st; }
      if (st.state === "abgebrochen") { toast(st.error || "Bankabruf abgebrochen", true); return st; }
      return st;
    } finally { ftsBusy = false; }
  }

  async function ftsAbruf(tage){
    const st = await ftsRun("abruf", tage ? {tage} : {});
    if (!st || st.state !== "fertig") { if (view === "bank") vBank(); return; }
    const e = st.ergebnis || {};
    await reload();
    await modal("Bankabruf abgeschlossen", `<div class="fr">${fSummary(Object.assign({}, e, {log: st.log}))}
      ${e.offen?`<div class="hl small" style="margin-top:8px">${e.offen} Buchung(en) stehen jetzt im Bank-Abgleich zur Bestätigung bereit.</div>`:""}</div>`);
    if (view === "bank") vBank(); else go("bank");
  }
  window.ftsAbruf = ftsAbruf;

  // ---------- Bank-Abgleich: button, last log, pending ----------
  EXT.after.push(async (vn) => {
    if (vn !== "vBank") return;
    const act = $("#main .ph .act");
    if (act && !$("#ftsbtn")) {
      const b = document.createElement("button"); b.className = "btn pri"; b.id = "ftsbtn";
      b.innerHTML = `${ic("sync")} Umsätze von der Bank abrufen`;
      b.title = "Umsätze per FinTS/HBCI direkt von der Bank holen (seit letztem Abruf, sonst 90 Tage)";
      b.onclick = async () => {
        const f = S.fints || {};
        if (!f.eingerichtet) { if (await confirmBox("Der Bankabruf ist noch nicht eingerichtet. Jetzt in den Einstellungen einrichten?", "Einrichten")) { try { setTab = "fints"; } catch (e) {} go("set"); } return; }
        ftsAbruf();
      };
      act.prepend(b);
    }
    const page = $("#main .page"), kb = $("#kontobox");
    if (page && kb && !$("#ftsinfo") && S.fints && S.fints.eingerichtet) {
      const d = document.createElement("div"); d.id = "ftsinfo"; d.className = "card"; d.style.marginBottom = "16px";
      d.innerHTML = `<div class="hd"><h3>Letzter Bankabruf</h3><div class="act"><button class="btn sm ghost" id="ftsz">Zeitraum wählen …</button></div></div><div class="bd" id="ftsinfob"><div class="small muted">lädt …</div></div>`;
      kb.after(d);
      $("#ftsz").onclick = async () => {
        let t = 90;
        const r = await modal("Zeitraum für den Bankabruf", `<div class="fr"><label class="f">Umsätze der letzten … Tage<input class="in num" id="ftst" value="90"></label><div class="small muted">Viele Banken liefern nur 90 Tage ohne zusätzliche TAN, manche bis 365 Tage. Schon vorhandene Buchungen werden nicht doppelt übernommen.</div></div>`,
          [{label:"Abbrechen"},{label:"Abrufen", cls:"pri", value:1, onClick: async mb => { t = Math.max(1, Math.round(pnum($("#ftst",mb).value)) || 90); }}]);
        if (r) ftsAbruf(t);
      };
      api("/api/fints/log", undefined, {quiet:true}).then(lg => { const el = $("#ftsinfob"); if (el) el.innerHTML = fSummary(lg && lg.zeit ? lg : null); });
    }
    // fetched but unconfirmed transactions -> into the normal confirmation table
    try {
      const pend = await api("/api/fints/pending", undefined, {quiet:true});
      if (Array.isArray(pend) && pend.length && view === "bank") {
        const have = new Set(bankTx.map(t => t.hash));
        const add = pend.filter(t => !have.has(t.hash));
        if (add.length) {
          bankTx = bankTx.concat(add);
          renderBankTx(S.invoices.filter(i=>["rechnung","storno"].includes(i.typ)&&i.status==="offen"));
          const h = $("#bktx .hd h3"); if (h && !$("#ftspd")) h.insertAdjacentHTML("beforeend", ` <span class="badge acc" id="ftspd" title="Vom Bankabruf geholt, noch nicht bestätigt">${add.length} aus Bankabruf</span>`);
        }
      }
    } catch (e) { console.error(e); }
  });

  // ---------- v2.3.0: bank picker (bank library m93) ----------
  const fBadge = b => !b ? "" : b.url ? (b.url_quelle === "vermutet" ? `<span class="badge warn" title="Adresse abgeleitet (Genossenschaftsbank) – mit „Verbindung testen“ prüfen">FinTS vermutet</span>` : `<span class="badge ok">FinTS</span>`) : `<span class="badge" title="Keine FinTS-Adresse bekannt – ggf. PSD2 unten oder CSV-Import">kein FinTS bekannt</span>`;
  const fBankLine = b => b ? `<b>${esc(b.name)}</b>${b.ort ? " · " + esc(b.ort) : ""}<div class="small muted">BLZ ${esc(b.blz)}${b.bic ? " · BIC " + esc(b.bic) : ""}</div>` : `<span class="muted">Noch keine Bank gewählt</span>`;

  async function pickBank(cur){
    let chosen = null, list = [], sel = 0, seq = 0;
    const render = mb => {
      const box = $("#blres", mb);
      if (!list.length) { box.innerHTML = `<div class="small muted" style="padding:10px">${$("#blq", mb).value.trim() ? "Keine Bank gefunden." : "Name, Ort, BLZ, BIC oder deine IBAN eingeben."}</div>`; return; }
      box.innerHTML = list.map((b, i) => `<div class="it blit" data-i="${i}" style="display:flex;gap:10px;align-items:center;padding:8px 10px;border-radius:8px;cursor:pointer;${i===sel?"background:var(--accsoft)":""}">
        <div style="flex:1;min-width:0">${fBankLine(b)}</div><div style="flex:none">${fBadge(b)}</div></div>`).join("");
      $$(".blit", box).forEach(el => el.onclick = () => { chosen = list[+el.dataset.i]; $(".mf .pri", mb).click(); });
      const on = $(`.blit[data-i="${sel}"]`, box); if (on) on.scrollIntoView({block:"nearest"});
    };
    const search = async mb => {
      const q_ = $("#blq", mb).value.trim(), my = ++seq;
      const r = q_ ? await api("/api/bl/suche?n=60&q=" + encodeURIComponent(q_), undefined, {quiet:true}) : [];
      if (my !== seq) return;
      list = Array.isArray(r) ? r : []; sel = 0; render(mb);
    };
    const r = await modal("Bank wählen", `<div class="fr nokeep">
      <input class="in" id="blq" placeholder="z. B. Sparkasse Köln, Volksbank, DKB, 37050198 …" autocomplete="off" value="${esc(cur && cur.name ? cur.name : "")}">
      <div id="blres" style="max-height:380px;overflow:auto;border:1px solid var(--line);border-radius:10px;padding:4px"></div>
      <div class="small muted" id="blinfo"></div></div>`,
      [{label:"Abbrechen"},{label:"Übernehmen", cls:"pri", value:1, onClick: async () => { if (!chosen) chosen = list[sel]; if (!chosen) { toast("Bitte eine Bank wählen", true); return false; } }}],
      true, mb => {
        const i = $("#blq", mb); let t = null;
        i.oninput = () => { clearTimeout(t); t = setTimeout(() => search(mb), 140); };
        i.onkeydown = e => {
          if (e.key === "ArrowDown") { sel = Math.min(list.length - 1, sel + 1); render(mb); e.preventDefault(); }
          else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); render(mb); e.preventDefault(); }
          else if (e.key === "Enter") { e.preventDefault(); if (list[sel]) { chosen = list[sel]; $(".mf .pri", mb).click(); } }
        };
        setTimeout(() => { i.focus(); i.select(); }, 30);
        search(mb);
        api("/api/bl/info", undefined, {quiet:true}).then(x => { const el = $("#blinfo", mb); if (el && x && x.anzahl) el.textContent = `${x.anzahl} Bankleitzahlen, davon ${x.mit_fints} mit FinTS-Adresse · Liste zusammengestellt am ${dde(x.stand)} · ${x.quelle}`; });
      });
    return r ? chosen : null;
  }
  window.paPickBank = pickBank;

  // ---------- settings tab ----------
  const TAGE = [30, 60, 90, 180, 365, 730];
  let fBank = null;          // bank chosen in the open settings tab

  async function ftsSave(el, quiet, c){
    const g = id => $("#"+id, el);
    if (!g("fts_user")) return null;
    const urlSel = g("fts_urlsel").value;
    const d = {blz: fBank ? fBank.blz : "", user: g("fts_user").value,
      kunde: g("fts_kundesel").value === "eigen" ? g("fts_kunde").value : "",
      url: urlSel === "_eigen" ? g("fts_url").value : urlSel, produkt: g("fts_prod").value,
      pin_speichern: !g("fts_nopin").checked, auto: g("fts_auto").checked, tage: +g("fts_tage").value || 90};
    if (g("fts_konto")) d.konto = g("fts_konto").value;
    if (g("fts_tanm")) d.tan_mech = g("fts_tanm").value;
    if (g("fts_tanmed")) d.tan_medium = g("fts_tanmed").value;
    if (g("fts_pin").value) d.pin_neu = g("fts_pin").value;
    if (c && c.blz && d.blz && c.blz !== d.blz) d.reset_bank = true;   // other bank: forget TAN choice, accounts, bank state
    const r = await api("/api/fints/config/save", d);
    if (r && r.ok !== false) { g("fts_pin").value = ""; if (!quiet) toast("Bankabruf gespeichert"); await reload(); }
    return r;
  }

  function urlOptions(c, b){
    const o = [], seen = new Set();
    const add = (v, l) => { if (v && !seen.has(v)) { seen.add(v); o.push([v, l]); } };
    if (b && b.url) add(b.url, (b.url_quelle === "vermutet" ? "Vermutet für " : "Aus der Bankliste für ") + b.name);
    (c.server_hints || []).forEach(h => add(h.url, h.label));
    return o;
  }

  function renderUrl(el, c){
    const sel = $("#fts_urlsel", el), opts = urlOptions(c, fBank);
    let cur = $("#fts_url", el).value || c.url || "";
    if (!cur && fBank && fBank.url) cur = fBank.url;
    const known = opts.some(o => o[0] === cur);
    sel.innerHTML = opts.map(o => `<option value="${esc(o[0])}" ${o[0]===cur?"selected":""} title="${esc(o[0])}">${esc(o[1])}</option>`).join("") +
      `<option value="_eigen" ${(!known && cur) || !opts.length ? "selected" : ""}>Eigene Adresse eingeben …</option>`;
    if (fBank && fBank.url && $("#fts_banknew", el).value === "1") sel.value = fBank.url;
    if (sel.value === "_eigen" && !$("#fts_url", el).value) $("#fts_url", el).value = known ? "" : cur;
    updUrl(el);
  }

  function updUrl(el){
    const sel = $("#fts_urlsel", el), own = sel.value === "_eigen";
    $("#fts_urlbox", el).style.display = own ? "" : "none";
    const adr = own ? "" : `<div style="font:12px Consolas,monospace;user-select:all;margin-bottom:2px">${esc(sel.value)}</div>`;
    $("#fts_urlhint", el).innerHTML = own ? "Eigene Adresse der Bank (beginnt mit https://) – z. B. aus der Online-Banking-Hilfe, Stichwort „FinTS“." : adr + (fBank && !fBank.url ? `<span style="color:var(--warn)">Für ${esc(fBank.name)} ist keine FinTS-Adresse bekannt. Bitte bei der Bank nachsehen (Stichwort „FinTS“ / „HBCI PIN/TAN“) – oder unten den Abruf über PSD2 nutzen, sonst CSV-/PDF-Import.</span>`
      : fBank && fBank.url_quelle === "vermutet" ? "Adresse abgeleitet (Genossenschaftsbank, Rechenzentrum Atruvia) – mit „Verbindung testen“ prüfen."
      : "Adresse aus der Bankliste, ohne Gewähr – „Verbindung testen“ zeigt, ob sie stimmt.");
  }

  function renderBank(el, c){
    $("#fts_bankbox", el).innerHTML = `<div style="display:flex;gap:10px;align-items:center"><div style="flex:1;min-width:0">${fBankLine(fBank)}</div><div style="flex:none">${fBadge(fBank)}</div></div>`;
    $("#fts_loginhint", el).textContent = fBank ? fBank.login_hinweis : "";
    renderUrl(el, c);
  }

  EXT.settings.push({key:"fints", label:"Bankabruf", render: async el => {
    el.innerHTML = `<div class="small muted">lädt …</div>`;
    const c = await api("/api/fints/config");
    const own = await api("/api/bl/eigene", undefined, {quiet:true});
    fBank = c.bank || null;
    const opt = (v, l, sel) => `<option value="${esc(v)}" ${sel?"selected":""}>${esc(l)}</option>`;
    const tanO = c.tan_optionen || [], tanM = c.tan_medien || [];
    const tage = TAGE.includes(+c.tage) ? TAGE : TAGE.concat([+c.tage]).sort((a, b) => a - b);
    const eg = c.eigene || {}, egb = eg.bank, psd2Only = eg.weg === "psd2" && (!fBank || fBank.blz === egb.blz) && !c.user;
    const banner = !egb ? `<div class="hl small" style="margin-top:16px">Tipp: Trag unter <b>Einstellungen → Firma &amp; Bank</b> die IBAN deiner Rechnungen ein – dann füllt das Programm die Bank hier automatisch aus.</div>`
      : `<div class="card" style="margin-top:16px"><div class="bd" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
          <div style="flex:1;min-width:260px"><div class="small muted">Deine Bank laut Rechnung (Firma &amp; Bank)</div>
            <div style="font-size:15px;margin-top:2px"><b>${esc(egb.name)}</b>${egb.ort ? " · " + esc(egb.ort) : ""} ${fBadge(egb)}</div>
            <div class="small muted" style="font-family:Consolas,monospace">${esc(eg.iban_fmt)} · BLZ ${esc(egb.blz)} · BIC ${esc(egb.bic)}</div></div>
          <div style="flex:1.4;min-width:300px" class="small">${eg.weg === "fints"
            ? `Bank und FinTS-Server sind <b>schon eingetragen</b>${eg.auto ? " (automatisch aus der IBAN)" : ""}. Es fehlen nur deine <b>Benutzerkennung</b>, die <b>PIN</b> und einmalig die <b>Produkt-Registrierungsnummer</b> – dann „Verbindung testen“.`
            : `Die <b>${esc(egb.name)} bietet kein FinTS/HBCI</b>. Der Abruf läuft deshalb über den <b>Bank-Login im Browser</b>: Das Programm öffnet das Online-Banking, du meldest dich an (bei C24: QR-Code mit der App scannen) – Kontostand und Umsätze werden übernommen. Nichts einzurichten.
               <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn sm pri" type="button" id="fts_gowb">${ic("sync")} Jetzt Kontostand & Umsätze holen</button>
               <button class="btn sm ghost" type="button" id="fts_gopsd2">Alternative: PSD2</button>${psd2Only ? `<button class="btn sm ghost" type="button" id="fts_showfints">FinTS für eine andere Bank</button>` : ""}</div>`}</div></div></div>` + (eg.weg === "psd2" ? `<div id="wbslot"></div>` : "");
    el.innerHTML = banner + `<div class="grid g2" id="fts_grid" style="align-items:start;margin-top:16px;${psd2Only ? "display:none" : ""}">
      <div class="card"><div class="hd"><h3>Zugang zur Bank (FinTS / HBCI mit PIN/TAN)</h3></div><div class="bd fr">
        ${c.lib_ok?"":`<div class="alert bad">${ic("alert")}Für den Bankabruf bitte einmal build_exe.bat ausführen (neue Bibliothek fints).</div>`}
        <input type="hidden" id="fts_banknew" value="0">
        <div class="f"><span>Bank</span>
          <div style="border:1px solid var(--line2);border-radius:10px;padding:10px 12px" id="fts_bankbox"></div>
          <div class="row" style="margin-top:6px;gap:8px"><button class="btn sm pri" style="flex:none" type="button" id="fts_bankpick">${ic("search")} Bank wählen …</button>
            ${own && own.ok && (!fBank || own.bank.blz !== fBank.blz) ? `<button class="btn sm" style="flex:none" type="button" id="fts_bankown" title="IBAN aus Einstellungen → Firma & Bank">Meine Bank: ${esc(own.bank.name)}</button>` : ""}</div></div>
        <label class="f">FinTS-Server<select class="in" id="fts_urlsel"></select></label>
        <div id="fts_urlbox" style="display:none"><label class="f">Eigene Server-Adresse<input class="in" id="fts_url" placeholder="https://…" value=""></label></div>
        <div class="small muted" id="fts_urlhint"></div>
        <label class="f">Benutzerkennung / Login<input class="in" id="fts_user" value="${esc(c.user)}" autocomplete="off"></label>
        <div class="small muted" id="fts_loginhint" style="margin-top:-6px"></div>
        <div class="row"><label class="f" style="flex:.9">Kunden-ID<select class="in" id="fts_kundesel">${opt("wie", "wie Benutzerkennung (Standard)", !c.kunde)}${opt("eigen", "eigene Kunden-ID der Bank", !!c.kunde)}</select></label>
          <label class="f" id="fts_kundebox" style="${c.kunde?"":"display:none"}">Kunden-ID<input class="in" id="fts_kunde" value="${esc(c.kunde)}"></label></div>
        <label class="f">PIN ${c.pin_gespeichert?`<span class="badge ok">gespeichert</span>`:""}<input class="in" id="fts_pin" type="password" autocomplete="new-password" placeholder="${c.pin_gespeichert?"leer lassen = unverändert":"Online-Banking-PIN"}"></label>
        <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="fts_nopin" ${c.pin_speichern?"":"checked"}> PIN nicht speichern – bei jedem Abruf fragen</label>
        ${c.pin_gespeichert?`<div><button class="btn sm ghost danger" id="fts_pindel">Gespeicherte PIN löschen</button></div>`:""}
        <label class="f">Produkt-Registrierungsnummer<input class="in" id="fts_prod" value="${esc(c.produkt)}" placeholder="von der Deutschen Kreditwirtschaft"></label>
        <div class="small muted">Einmalig eintragen: die kostenlose Registrierung der Deutschen Kreditwirtschaft für dein Programm (<a href="#" id="fts_reg">www.hbci-zka.de/register/prod_register.htm</a>). Sie gilt für alle Banken.</div>
      </div></div>
      <div class="fr" style="gap:16px">
      <div class="card"><div class="hd"><h3>Konto & Abruf</h3></div><div class="bd fr">
        <div class="row" style="align-items:flex-end"><label class="f">Konto${(c.konten||[]).length?"":" (nach „Verbindung testen“ wählbar)"}<select class="in" id="fts_konto">${(c.konten||[]).length?(c.konten||[]).map(k=>opt(k.iban||k.nr, (k.iban||k.nr)+(k.unterkonto?" / "+k.unterkonto:""), (k.iban||k.nr)===c.konto)).join(""):opt("", "– noch keine Konten geladen –", true)}</select></label>
          <button class="btn" style="flex:none" id="fts_test">${ic("sync")} Verbindung testen & Konten laden</button></div>
        <label class="f">TAN-Verfahren${tanO.length?"":" (nach „Verbindung testen“ wählbar)"}<select class="in" id="fts_tanm">${tanO.length ? tanO.map(o=>opt(o.id, o.label, o.id===c.tan_mech)).join("") + (c.tan_mech && !tanO.some(o=>o.id===c.tan_mech) ? opt(c.tan_mech, c.tan_mech, true) : "") : opt(c.tan_mech||"", c.tan_mech ? c.tan_mech : "– wird beim ersten Verbinden von der Bank geholt –", true)}</select></label>
        ${tanM.length ? `<label class="f">TAN-Medium (Gerät / App)<select class="in" id="fts_tanmed">${tanM.map(o=>opt(o.id, o.label, o.id===c.tan_medium)).join("")}</select></label>`
          : c.tan_medium ? `<label class="f">TAN-Medium<select class="in" id="fts_tanmed">${opt(c.tan_medium, c.tan_medium, true)}</select></label>` : ""}
        <label class="f">Erster Abruf<select class="in" id="fts_tage">${tage.map(t=>opt(t, `Umsätze der letzten ${t} Tage`, +c.tage===t)).join("")}</select></label>
        <div class="small muted" style="margin-top:-6px">Danach wird automatisch ab dem letzten Abruf geholt (mit Überlappung, doppelte Buchungen werden erkannt). Viele Banken liefern ohne zusätzliche TAN nur 90 Tage.</div>
        <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="fts_auto" ${c.auto?"checked":""}> Sichere Zuordnungen automatisch buchen</label>
        <div class="small muted">Automatisch gebucht wird nur, wenn der Betrag exakt zu genau einer offenen Rechnung passt und Rechnungsnummer oder Kundenname im Verwendungszweck steht – sowie vorgemerkte Fixkosten. Alles andere wartet im Bank-Abgleich auf deine Bestätigung.</div>
        ${c.tan_mech||c.tan_medium||tanO.length?`<div class="small">TAN-Verfahren und Konten neu von der Bank holen: <button class="btn sm ghost" id="fts_reset">zurücksetzen</button></div>`:""}
        <div><button class="btn pri" id="fts_save">${ic("save")} Bankabruf speichern</button></div>
      </div></div>
      <div class="card"><div class="hd"><h3>Letzter Abruf</h3></div><div class="bd">${fSummary(c.log)}</div></div>
      </div></div>`;
    renderBank(el, c);
    const gw = $("#fts_gowb", el); if (gw) gw.onclick = () => { if (window.wbAbruf) window.wbAbruf(); };
    const gp = $("#fts_gopsd2", el); if (gp) gp.onclick = () => { const h = $("#ebhost"); if (h) h.scrollIntoView({behavior:"smooth", block:"start"}); const a = $("#ebapp"); if (a) setTimeout(() => a.focus(), 400); };
    const sf = $("#fts_showfints", el); if (sf) sf.onclick = () => { $("#fts_grid", el).style.display = ""; sf.remove(); };
    const setBank = b => { if (!b) return; fBank = b; $("#fts_banknew", el).value = "1"; $("#fts_url", el).value = ""; renderBank(el, c); };
    $("#fts_bankpick", el).onclick = async () => setBank(await pickBank(fBank));
    const bo = $("#fts_bankown", el); if (bo) bo.onclick = () => { setBank(own.bank); bo.remove(); };
    $("#fts_urlsel", el).onchange = () => { $("#fts_banknew", el).value = "0"; updUrl(el); if ($("#fts_urlsel", el).value === "_eigen") $("#fts_url", el).focus(); };
    $("#fts_kundesel", el).onchange = () => { const e_ = $("#fts_kundesel", el).value === "eigen"; $("#fts_kundebox", el).style.display = e_ ? "" : "none"; if (e_) $("#fts_kunde", el).focus(); };
    $("#fts_save", el).onclick = () => ftsSave(el, false, c);
    const ss = $("#ssave"); if (ss) ss.addEventListener("click", () => ftsSave(el, true, c));
    $("#fts_reg", el).onclick = ev => { ev.preventDefault(); api("/api/fints/openreg", {}); };
    const pd = $("#fts_pindel", el); if (pd) pd.onclick = async () => { await api("/api/fints/config/save", {pin_loeschen:true}); await reload(); toast("PIN gelöscht"); vSettings(); };
    const rs = $("#fts_reset", el); if (rs) rs.onclick = async () => { if (!await confirmBox("TAN-Verfahren, TAN-Medium, Kontoauswahl und gespeicherte Bankparameter zurücksetzen? Beim nächsten Verbinden holt das Programm sie neu von der Bank.", "Zurücksetzen")) return;
      await api("/api/fints/config/save", {reset_bank:true}); toast("Zurückgesetzt"); vSettings(); };
    $("#fts_test", el).onclick = async () => {
      if (!fBank) { toast("Bitte zuerst die Bank wählen", true); return; }
      const r = await ftsSave(el, true, c); if (!r || r.ok === false) return;
      const st = await ftsRun("konten");
      if (st && st.state === "fertig") { const n = ((st.ergebnis||{}).konten||[]).length; toast(`Verbindung OK – ${n} Konto/Konten gefunden`); vSettings(); }
    };
  }});
})();
