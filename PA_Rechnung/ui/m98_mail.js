// Pfeiffer-Audio Rechnung v3.1.0 - UI-Modul m98_mail: Gmail-Login, privates Postfach, Outlook (zusammengefasst)
// v3.6.0: Privat-Mails - externe Bilder auf Wunsch laden ("Bilder laden"), wie bei E-Mails (m30).
// Autor: T. Pfeiffer


// ============================================================================
// Teil aus m98_gmail.js
// ============================================================================
// PA Rechnung v2.4.8 - UI-Modul m98_gmail: Gmail mit 2-Faktor - Login im Browser (wie Bank-Login)
// Knopf "Mit Google anmelden" auf der Seite E-Mails und in Einstellungen -> E-Mail-Abruf.
// Live-Dialog: Google-Fenster -> du meldest dich an (Passwort + 2. Faktor) -> App-Passwort wird
// erzeugt, gelesen, geprueft, gespeichert -> Mails werden abgerufen und gespeichert.
// Notweg: App-Passwort aus dem eigenen Browser einfuegen.
// v2.4.4: gmLogin(ziel) - "geschaeft" (Standard) oder "privat" (privates Postfach, m99).
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m98 = '<path d="M21 12.2c0-.7-.1-1.3-.2-1.9H12v3.6h5.1a4.4 4.4 0 0 1-1.9 2.9v2.4h3.1c1.8-1.7 2.7-4.1 2.7-7z"/><path d="M12 21c2.6 0 4.7-.9 6.3-2.3l-3.1-2.4c-.9.6-2 .9-3.2.9-2.5 0-4.6-1.7-5.3-3.9H3.5v2.5A9.5 9.5 0 0 0 12 21z"/><path d="M6.7 13.3a5.7 5.7 0 0 1 0-3.6V7.2H3.5a9.5 9.5 0 0 0 0 8.6z"/><path d="M12 6.8c1.4 0 2.6.5 3.6 1.4l2.7-2.7A9.5 9.5 0 0 0 3.5 7.2l3.2 2.5C7.4 8.5 9.5 6.8 12 6.8z"/>';
  let busy = false;

  const abrufHtml = a => !a ? "" : a.ok
    ? `<div class="small"><span class="badge ok">OK</span> E-Mails abgerufen und gespeichert: ${esc(a.text || "")}</div>`
    : `<div class="small" style="color:var(--warn)">Abruf: ${esc(a.error || a.text || "Fehler")}</div>`;

  function stHtml(st){
    if (st.state === "fehler") return `<div style="color:var(--bad)">${esc(st.error)}</div>`;
    if (st.state === "abgebrochen") return `<div class="small" style="color:var(--warn)">${esc(st.error || "Abgebrochen.")}</div>`;
    const ph = st.phase || "start", order = ["start", "login", "erzeugen", "pruefen", "abruf", "fertig"], at = order.indexOf(ph);
    const step = (i, t) => { const done = at > i || ph === "fertig", on = at === i && !done;
      return `<div style="display:flex;gap:10px;align-items:flex-start;margin:6px 0;${on||done?"":"opacity:.55"}">
        <span style="flex:none;width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;
          background:${done?"var(--ok)":on?"var(--acc)":"var(--line2)"};color:#fff">${done?"✓":on?"…":""}</span><div>${t}</div></div>`; };
    return step(0, "Google-Fenster geöffnet") +
      step(1, `<b>Jetzt im Google-Fenster anmelden</b><div class="small muted">${esc(st.hinweis || "")}</div>`) +
      step(2, `App-Passwort erzeugen<div class="small muted">Das Programm trägt „PA Rechnung“ ein und klickt „Erstellen“. Passiert nichts: selbst einen Namen eintippen und auf „Erstellen“ klicken – das Fenster dann einfach offen lassen.</div>`) +
      step(3, `App-Passwort lesen und am Postfach prüfen${st.adresse ? ` <span class="small muted">(${esc(st.adresse)})</span>` : ""}`) +
      step(4, `E-Mails abrufen und speichern`) +
      (st.hinweis2 ? `<div class="hl small" style="margin-top:8px">${esc(st.hinweis2)}</div>` : "") +
      (st.abruf ? `<div style="margin-top:8px">${abrufHtml(st.abruf)}</div>` : "") +
      `<details class="small" style="margin-top:8px"><summary class="muted">Protokoll</summary><pre style="white-space:pre-wrap;margin:6px 0 0;font-size:11px">${esc((st.log || []).join("\n"))}</pre></details>`;
  }

  async function gmLogin(ziel){
    if (typeof ziel !== "string") ziel = "geschaeft";
    const priv = ziel === "privat";
    if (busy) { toast("Google-Anmeldung läuft bereits …"); return; }
    // v2.4.8: private mailbox - ask for the address first (Google does not always show it on the page)
    if (priv) {
      const info = await api("/api/mp/info", undefined, {quiet: true}) || {};
      const cur = /@(gmail|googlemail)\.com$/i.test(info.user || "") ? info.user : "";
      // v2.5.0: address known -> no question, it is entered in the Google window automatically
      if (cur) gmLogin._adr = cur;
      const adr = cur ? "ok" : await modal("Privates Gmail verbinden", `<div class="fr"><div class="small">Gleiche Anmeldung wie beim Geschäftspostfach: Es öffnet sich ein Google-Fenster, du meldest dich dort mit deinem <b>privaten</b> Konto an (Passwort + Handy/Code), das Programm holt sich das App-Passwort selbst.</div>
        <label class="f">Deine private Gmail-Adresse<input class="in" id="gmpadr" value="${esc(cur)}" placeholder="name@gmail.com" autocomplete="off"></label></div>`,
        [{label: "Abbrechen", value: null}, {label: "Weiter zu Google", cls: "pri", value: "ok", onClick: async mb => { gmLogin._adr = $("#gmpadr", mb).value.trim(); }}]);
      if (!adr) return;
      let a = (gmLogin._adr || "").toLowerCase();
      if (a && !a.includes("@")) a += "@gmail.com";
      if (!/^[^@\s]+@(gmail|googlemail)\.com$/.test(a)) { toast("Bitte eine Gmail-Adresse eintragen (…@gmail.com).", true); return; }
      const sv = await api("/api/mp/speichern", {user: a, host: "imap.gmail.com", port: 993, ssl: true});
      if (!sv || sv.ok === false) return;
    }
    // v2.5.0: business mailbox - no Gmail address stored yet -> ask ONCE, remembered for every later login
    if (!priv) {
      const gi = await api("/api/gm/info", undefined, {quiet: true}) || {};
      if (!(gi.adressen || []).length) {
        gmLogin._gadr = "";
        const ok = await modal("Gmail verbinden", `<div class="fr"><div class="small">Einmalig: Mit welcher Gmail-Adresse meldest du dich beim <b>Geschäftspostfach</b> an? Sie wird gemerkt und steht ab jetzt jedes Mal schon in der Google-Anmeldung.</div>
          <label class="f">Deine Gmail-Adresse (Geschäft)<input class="in" id="gmgadr" placeholder="name@gmail.com" autocomplete="off"></label></div>`,
          [{label: "Abbrechen", value: null}, {label: "Weiter zu Google", cls: "pri", value: "ok", onClick: async mb => { gmLogin._gadr = $("#gmgadr", mb).value.trim(); }}]);
        if (!ok) return;
        const sv = await api("/api/gm/adresse", {adresse: gmLogin._gadr});
        if (!sv || sv.ok === false) return;
        if (S.gm) S.gm.adressen = sv.adressen;
      }
    }
    busy = true;
    try {
      const st0 = await api("/api/gm/start", {ziel});
      if (!st0 || st0.ok === false) return;
      let st = st0, done = null;
      const tok = st0.token;
      await modal(priv ? "Privates Gmail-Postfach verbinden" : "Gmail verbinden – Anmeldung bei Google", `<div class="fr nokeep">
          <div id="gmst">${stHtml(st)}</div>
          <div class="small muted">Das Programm sieht weder dein Google-Passwort noch den Bestätigungscode. Es liest nur das App-Passwort, das Google dir am Ende anzeigt, und speichert es verschlüsselt. Das Fenster nutzt ein frisches Profil – danach bleibt nichts davon zurück.</div>
          <details class="small"><summary>Google lässt die Anmeldung im Fenster nicht zu? App-Passwort selbst einfügen</summary>
            <div class="small muted" style="margin:6px 0">Im eigenen Browser <b>myaccount.google.com/apppasswords</b> öffnen, neues App-Passwort „PA Rechnung“ erstellen und die 16 Buchstaben hier einfügen.</div>
            <div class="row" style="gap:8px;flex-wrap:wrap;align-items:flex-end">
              <label class="f" style="flex:1 1 200px">Gmail-Adresse<input class="in" id="gmuser" value="${esc(priv ? ((S.mp || {}).adresse || "") : (((S.gm || {}).adressen || [])[0] || ""))}" placeholder="name@gmail.com"></label>
              <label class="f" style="flex:1 1 200px">App-Passwort<input class="in" id="gmpw" autocomplete="off" placeholder="abcd efgh ijkl mnop"></label>
              <button class="btn" type="button" id="gmpwgo" style="flex:none">Prüfen &amp; speichern</button></div>
            <div class="small" id="gmpwres"></div></details></div>`,
        [{label: "Abbrechen", onClick: async () => { if (!done) await api("/api/gm/abbrechen", {token: tok}, {quiet: true}); }},
         {label: "Schließen", cls: "pri", value: 1, onClick: async () => { if (!done && st.state === "browser") await api("/api/gm/abbrechen", {token: tok}, {quiet: true}); }}],
        false, async mb => {
          const go = $("#gmpwgo", mb);
          if (go) go.onclick = async () => {
            const res = $("#gmpwres", mb); res.textContent = "prüfe bei Gmail …"; go.disabled = true;
            const r = await api("/api/gm/passwort", {token: tok, ziel, pass: $("#gmpw", mb).value, user: $("#gmuser", mb).value}, {quiet: true});
            go.disabled = false;
            if (!r || r.ok === false) { res.innerHTML = `<span style="color:var(--bad)">${esc((r && r.error) || "Fehler")}</span>`; return; }
            res.innerHTML = `<span style="color:var(--ok)">Gespeichert.</span>`;
            if (r.state === "fertig" && r.phase === "fertig" && !r.token) { st = Object.assign({}, st, r); done = r; const b = $("#gmst", mb); if (b) b.innerHTML = stHtml(st); }
          };
          let errs = 0;
          while (mb.isConnected) {
            await new Promise(res => setTimeout(res, 1000));
            if (!mb.isConnected || (done && done.phase === "fertig")) break;
            const s2 = await api("/api/gm/status?token=" + encodeURIComponent(tok), undefined, {quiet: true});
            if (!s2 || s2.ok === false) { if (++errs > 5) break; continue; }
            st = s2; const b = $("#gmst", mb); if (b) b.innerHTML = stHtml(st);
            if (st.phase === "fertig" && st.state === "fertig") { done = st; break; }
            if (st.state === "fehler" || st.state === "abgebrochen") break;
          }
        });
      if (done) {
        await reload();
        toast(priv ? `Privates Postfach verbunden: ${done.adresse || ""}` : `Gmail verbunden: ${done.adresse || ""}${done.versand ? " – Abruf und Versand" : ""}`);
        if (priv && typeof window.mpRefresh === "function") window.mpRefresh();
        else if (view === "mails" && typeof vMails === "function") vMails();
        else if (view === "set" && typeof vSettings === "function") vSettings();
      }
    } finally { busy = false; }
  }
  window.gmLogin = gmLogin;

  const btn = (cls, txt) => { const b = document.createElement("button"); b.type = "button"; b.className = cls; b.innerHTML = `${ic("m98")} ${txt}`;
    b.title = "Gmail mit 2-Schritt-Bestätigung: im Google-Fenster anmelden – das Programm holt sich das App-Passwort selbst"; b.onclick = () => gmLogin("geschaeft"); return b; };

  // ---------- page E-Mails: button in the header
  if (EXT.views && typeof EXT.views.mails === "function") {
    const orig = EXT.views.mails;
    EXT.views.mails = async function(...a){
      const r = await orig.apply(this, a);
      try {
        const act = $("#main .ph .act"); const im = (typeof MAILD !== "undefined" && MAILD && MAILD.imap) || {}, last = im.letzter || {};
        if (act && !$("#gmbtn")) {
          const gm = S.gm || {};
          const need = !im.eingerichtet || last.ok === false || !gm.eingerichtet;
          const b = btn(need ? "btn pri" : "btn ghost", need ? "Mit Google anmelden" : "Google neu anmelden"); b.id = "gmbtn";
          if (need) $$(".btn.pri", act).forEach(x_ => x_.classList.remove("pri"));
          act.prepend(b);
        }
      } catch (e) {}
      return r;
    };
  }

  // ---------- settings: E-Mail-Abruf - box at the top of the IMAP card
  const ent = (EXT.settings || []).find(e => e.key === "mailabruf");
  if (ent) {
    const orig = ent.render;
    ent.render = function(el, ...a){
      const r = orig.call(this, el, ...a);
      try {
        const bd = $(".card .bd", el);
        if (bd && !$("#gmbox", el)) {
          const gm = S.gm || {};
          const d = document.createElement("div"); d.id = "gmbox"; d.className = "hl";
          d.style.cssText = "display:flex;gap:10px;align-items:center;flex-wrap:wrap";
          d.innerHTML = `<div class="small" style="flex:1 1 260px"><b>Gmail mit 2-Schritt-Bestätigung?</b> Einfach bei Google anmelden – wie beim Bank-Login. Das Programm erzeugt das App-Passwort selbst, prüft es, speichert es für Abruf und Versand und holt die Mails.${gm.eingerichtet ? `<br><span class="badge ok" style="margin-top:4px"><span class="dot"></span>verbunden: ${esc(gm.adresse)}</span>` : ""}</div>`;
          const b = btn(gm.eingerichtet ? "btn" : "btn pri", gm.eingerichtet ? "Neu anmelden" : "Mit Google anmelden"); b.style.flex = "none";
          d.appendChild(b); bd.prepend(d);
        }
      } catch (e) {}
      return r;
    };
  }
})();


// ============================================================================
// Teil aus m99_privat.js
// ============================================================================
// PA Rechnung v2.4.8 - UI-Modul m99_privat: privates Postfach (nur verwalten, nicht auswerten)
// + Karte "Rechnungs-Absender" (m99b) im Einstellungs-Reiter E-Mail-Abruf.
// Seite "Privat-Mails" (Seitenleiste oben), Einstellungs-Reiter "Privates Postfach".
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m99 = '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/><circle cx="18.5" cy="17.5" r="3.2" fill="var(--side,#fff)"/><path d="M18.5 16v1.6l1 .8"/>';
  const PF = {f: "alle", q: ""};
  let PD = null;
  const when = d => { if (!d) return ""; const t = String(d); const today = todayIso();
    return t.slice(0,10) === today ? t.slice(11,16) : dde(t.slice(0,10)) + (t.length > 11 ? " " + t.slice(11,16) : ""); };
  const kb = n => n > 1048576 ? (n/1048576).toFixed(1).replace(".", ",") + " MB" : Math.max(1, Math.round((n||0)/1024)) + " KB";

  EXT.nav.push({key: "privatmail", label: "Privat-Mails", icon: "m99", section: "Top", cnt: () => (S.mp && S.mp.ungelesen) ? String(S.mp.ungelesen) : ""});

  async function load(){
    PD = await api(`/api/mp/list?f=${encodeURIComponent(PF.f)}&q=${encodeURIComponent(PF.q)}`, undefined, {quiet: true});
    if (!PD || PD.ok === false) PD = {items: [], gesamt: 0, konto: {}};
    S.mp = Object.assign(S.mp || {}, {ungelesen: (PD.konto || {}).ungelesen || 0, eingerichtet: (PD.konto || {}).eingerichtet});
  }

  function rowsHtml(){
    if (!PD.items.length) return `<tr><td colspan="5" class="muted" style="text-align:center;padding:22px">${PF.q || PF.f !== "alle" ? "Nichts gefunden." : "Noch keine privaten Mails."}</td></tr>`;
    return PD.items.map(r => `<tr data-mp="${r.id}" style="cursor:pointer;${r.gelesen ? "" : "font-weight:600"}">
      <td style="width:28px" onclick="event.stopPropagation()"><input type="checkbox" data-mpsel="${r.id}"></td>
      <td style="white-space:nowrap;width:110px" class="small">${esc(when(r.datum))}</td>
      <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.markiert ? `<span style="color:var(--warn)">★</span> ` : ""}${esc(r.absender || r.absender_addr || "")}</td>
      <td><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:560px">${esc(r.betreff || "(ohne Betreff)")}${r.anh ? ` <span class="muted">${ic("clip")}${r.anh}</span>` : ""}${r.uebergeben ? ` <span class="badge acc">ans Geschäft übergeben</span>` : ""}</div>
        <div class="small muted" style="font-weight:400;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:560px">${esc(r.vorschau || "")}</div></td>
      <td class="r" onclick="event.stopPropagation()" style="white-space:nowrap"><button class="btn sm ghost" data-mpdel="${r.id}" title="Lokal löschen (im Postfach bleibt sie)">${ic("trash")}</button></td></tr>`).join("");
  }

  EXT.views.privatmail = async function(){
    $("#main").innerHTML = `<div class="page">${pageHead("Privat-Mails", "lädt …")}</div>`;
    await load();
    const k = PD.konto || {}, last = k.letzter || {};
    const act = k.eingerichtet
      ? `<button class="btn ${last.ok === false ? "pri" : "ghost"}" id="mpgm">${ic("m98")} ${last.ok === false ? "Mit Google neu anmelden" : "Google-Anmeldung"}</button><button class="btn" id="mpnow">${ic("sync")} Jetzt abrufen</button><button class="btn ghost" id="mpset">${ic("set")} Postfach</button><button class="btn ghost" id="mppst">${ic("m99c")} Outlook-Datei (.pst/.ost)</button>`
      : `<button class="btn pri" id="mpgm">${ic("m98")} Privates Gmail verbinden</button><button class="btn" id="mpset">${ic("set")} Anderes Postfach einrichten</button><button class="btn ghost" id="mppst">${ic("m99c")} Outlook-Datei (.pst/.ost)</button>`;
    $("#main").innerHTML = `<div class="page">
      ${pageHead("Privat-Mails", "Dein privates Postfach – getrennt vom Geschäft. Nur gespeichert und lesbar, keine Rechnungserkennung, nicht in Belegen, Steuer oder Protokoll.", act)}
      <div class="row small muted" style="margin-bottom:10px;align-items:center;flex-wrap:wrap">${k.eingerichtet
        ? `<span style="flex:none">${esc(k.user)} · ${k.interval ? `Abruf alle ${k.interval} Min.` : "automatischer Abruf aus"}${last.zeit ? ` · letzter Abruf ${when(last.zeit)} – <span style="color:${last.ok ? "var(--ok)" : "var(--bad)"}">${esc(last.text || "")}</span>` : ""} · ${k.anzahl} Mail(s) gespeichert</span>${last.ok === false && /anmeld|passwort|AUTHENTICATION|abgelehnt/i.test(last.text || "") ? `<div class="hl small" style="flex-basis:100%;margin-top:6px">Gmail nimmt das gespeicherte Passwort nicht (mehr) an – oben auf <b>„Mit Google neu anmelden“</b> klicken. Gleicher Ablauf wie beim Geschäftspostfach: im Google-Fenster mit dem <b>privaten</b> Konto anmelden, den Rest macht das Programm.</div>` : ""}`
        : `<span>Noch kein privates Postfach. Gmail: „Privates Gmail verbinden“ (Anmeldung im Google-Fenster wie beim Geschäftspostfach). Andere Anbieter: „Anderes Postfach einrichten“.</span>`}</div>
      <div class="dz" id="mpdz" style="margin-bottom:12px;padding:16px"><b>Private E-Mails hier ablegen</b><span class="muted">.eml, .msg, .mbox oder Outlook-Datendatei .pst/.ost – wird nur gespeichert, nicht ausgewertet</span></div>
      <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
        ${[["alle","Alle"],["ungelesen","Ungelesen"],["markiert","Markiert ★"],["anhang","Mit Anhang"]].map(([v,l]) => `<button class="chip ${PF.f===v?"on":""}" data-mpf="${v}" style="flex:none">${l}</button>`).join("")}
        <input class="in" id="mpq" placeholder="Suchen: Absender, Betreff, Text …" value="${esc(PF.q)}" style="flex:1 1 220px;max-width:360px">
        <span class="small muted" style="flex:none">${PD.gesamt} Treffer${PD.gesamt > PD.items.length ? ` (die neuesten ${PD.items.length})` : ""}</span>
        <span id="mpbulk" style="flex:none;display:none;gap:6px"><button class="btn sm" data-mpb="gelesen">Gelesen</button><button class="btn sm" data-mpb="markiert">★ Markieren</button><button class="btn sm danger" data-mpb="loeschen">${ic("trash")} Löschen</button></span></div>
      <div class="card"><table class="t"><thead><tr><th></th><th>Datum</th><th>Von</th><th>Betreff</th><th></th></tr></thead><tbody>${rowsHtml()}</tbody></table></div></div>`;
    const sel = () => $$("[data-mpsel]:checked").map(c => +c.dataset.mpsel);
    $$("[data-mpsel]").forEach(c => c.onchange = () => { $("#mpbulk").style.display = sel().length ? "inline-flex" : "none"; });
    $$("[data-mpb]").forEach(b => b.onclick = async () => {
      const ids = sel(); if (!ids.length) return;
      if (b.dataset.mpb === "loeschen") { if (!await confirmBox(`${ids.length} Mail(s) im Programm löschen?\n(Im Postfach selbst bleiben sie.)`)) return; await api("/api/mp/loeschen", {ids}); }
      else await api("/api/mp/markieren", {ids, [b.dataset.mpb]: true});
      EXT.views.privatmail();
    });
    $$("[data-mpf]").forEach(b => b.onclick = () => { PF.f = b.dataset.mpf; EXT.views.privatmail(); });
    let tq = null; $("#mpq").oninput = e => { clearTimeout(tq); tq = setTimeout(() => { PF.q = e.target.value; EXT.views.privatmail().then(() => { const i = $("#mpq"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }); }, 350); };
    $$("[data-mp]").forEach(tr => tr.onclick = () => openMail(+tr.dataset.mp));
    $$("[data-mpdel]").forEach(b => b.onclick = async () => { await api("/api/mp/loeschen", {ids: [+b.dataset.mpdel]}); EXT.views.privatmail(); });
    const n = $("#mpnow"); if (n) n.onclick = async () => { n.disabled = true; n.textContent = "Rufe ab …"; const r = await api("/api/mp/abrufen", {}); if (r && r.ok) toast("Privat: " + r.text); EXT.views.privatmail(); renderSide(); };
    const g = $("#mpgm"); if (g) g.onclick = () => window.gmLogin && window.gmLogin("privat");
    $("#mpset").onclick = () => { setTab = "mprivat"; go("set"); };
    $("#mppst").onclick = () => window.moPstPick && window.moPstPick("privat");
    const dz = $("#mpdz");
    dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
    dz.ondragleave = () => dz.classList.remove("over");
    dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); mpUpload(e.dataTransfer.files); };
    dz.onclick = () => pickFiles(".eml,.msg,.mbox,.mbx,.pst,.ost", mpUpload);
  };

  async function mpUpload(files){
    const pst = [...files].filter(f => /\.(pst|ost)$/i.test(f.name));
    for (const f of pst) if (window.moPstImport) await window.moPstImport(f, "privat");
    const rest = [...files].filter(f => !/\.(pst|ost)$/i.test(f.name));
    if (!rest.length) return;
    let neu = 0, dop = 0, err = 0;
    for (const f of rest) {
      try { const r = await upload("/api/upload/mp", f); if (!r || r.ok === false) { toast((r && r.error) || "Fehler", true); err++; continue; } neu += r.neu || 0; dop += r.doppelt || 0; err += r.fehler || 0; }
      catch (e) { err++; }
    }
    toast(`Privat: ${neu} Mail(s) eingelesen` + (dop ? `, ${dop} schon vorhanden` : "") + (err ? `, ${err} Fehler` : ""), !!err && !neu);
    await reload(); EXT.views.privatmail();
  }
  window.mpRefresh = async () => { await reload(); if (view === "privatmail") EXT.views.privatmail(); else if (view === "set") vSettings(); };

  async function openMail(id){
    const r = await api("/api/mp/get?id=" + id); if (!r || r.ok === false) return;
    const atts = r.anhaenge || [];
    const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:">`;
    const body = r.html
      ? `<iframe id="mpfr" sandbox="allow-popups allow-popups-to-escape-sandbox" style="width:100%;height:56vh;border:1px solid var(--line);border-radius:8px;background:#fff"></iframe>
         <div class="small muted">Externe Bilder sind blockiert (keine Lesebestätigung an den Absender). <a href="#" id="mpimg">Bilder laden</a></div>`
      : `<pre class="small" style="white-space:pre-wrap;max-height:56vh;overflow:auto;background:var(--bg2,#f7f6fb);padding:10px;border-radius:8px;margin:0;font-family:inherit">${esc((r.text || "").trim() || "(kein Text)")}</pre>`;
    const html = `<div class="fr">
      <div class="grid g2" style="gap:6px 18px"><div class="small"><span class="muted">Von</span><br><b>${esc(r.absender || "")}</b> ${esc(r.absender_addr ? "<" + r.absender_addr + ">" : "")}</div>
        <div class="small"><span class="muted">Datum</span><br>${esc(when(r.datum))}</div>
        <div class="small" style="grid-column:1/-1"><span class="muted">An</span> ${esc(r.empfaenger || "")}</div></div>
      ${body}
      ${atts.length ? `<div>${atts.map((a, i) => `<div class="row small" style="align-items:center;padding:4px 0;border-bottom:1px solid var(--line)">${ic("clip")}<b style="flex:1;overflow:hidden;text-overflow:ellipsis">${esc(a.name)}</b><span class="muted" style="flex:none">${kb(a.size)}</span><button class="btn sm ghost" style="flex:none" data-mpopen="${i}">${ic("open")} Öffnen</button></div>`).join("")}</div>` : ""}
      <div class="small muted">${r.ordner ? `<a href="#" id="mpfold">Ordner im Datenordner öffnen</a> · ` : ""}Private Mails werden nicht ausgewertet. Ist doch eine Geschäftsrechnung dabei: „Ans Geschäft übergeben“.</div></div>`;
    await modal(r.betreff || "(ohne Betreff)", html, [
      {label: "Löschen", cls: "danger", onClick: async () => { await api("/api/mp/loeschen", {ids: [id]}); }},
      {label: r.markiert ? "★ entfernen" : "★ Markieren", onClick: async () => { await api("/api/mp/markieren", {ids: [id], markiert: !r.markiert}); }},
      {label: r.uebergeben ? "Schon ans Geschäft übergeben" : "Ans Geschäft übergeben", onClick: async () => {
        if (r.uebergeben && !await confirmBox("Diese Mail wurde schon übergeben. Nochmal?", "Nochmal übergeben")) return false;
        const x_ = await api("/api/mp/uebergeben", {id}); if (x_ && x_.ok) toast(x_.status === "doppelt" ? "Liegt schon im Geschäftspostfach" : "An E-Mails (Geschäft) übergeben"); }},
      {label: "Schließen", cls: "pri"}], true, mb => {
        const fr = $("#mpfr", mb);
        const show = c => { if (fr) fr.srcdoc = c + `<base target="_blank"><style>body{font:14px system-ui,sans-serif;margin:12px;color:#222}img{max-width:100%;height:auto}</style>` + r.html; };
        show(csp);
        const im = $("#mpimg", mb); if (im) im.onclick = e => { e.preventDefault(); show(csp.replace("img-src data:", "img-src data: https: http:").replace("style-src 'unsafe-inline'", "style-src 'unsafe-inline' https:")); im.remove(); };
        $$("[data-mpopen]", mb).forEach(b => b.onclick = () => api("/api/open", {path: atts[+b.dataset.mpopen].file}));
        const f = $("#mpfold", mb); if (f) f.onclick = e => { e.preventDefault(); api("/api/open", {path: r.ordner, folder: true}); };
      });
    if (view === "privatmail") EXT.views.privatmail();
    try { const i = await api("/api/mp/info", undefined, {quiet: true}); if (i && S.mp) { S.mp.ungelesen = i.ungelesen; renderSide(); } } catch (e) {}
  }

  // ---------------------------------------------------------------- settings tab "Privates Postfach"
  EXT.settings.push({key: "mprivat", label: "Privates Postfach", async render(el){
    el.innerHTML = `<div class="small muted">lädt …</div>`;
    const c = await api("/api/mp/info", undefined, {quiet: true}) || {};
    const last = c.letzter || {};
    el.innerHTML = `<div class="grid g2" style="align-items:start">
      <div class="card"><div class="hd"><h3>${ic("m99")} Privates Postfach</h3><div class="act">${c.eingerichtet ? `<span class="badge ok"><span class="dot"></span>${esc(c.user)}</span>` : `<span class="badge warn">nicht eingerichtet</span>`}</div></div><div class="bd fr">
        <div class="hl" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><div class="small" style="flex:1 1 240px"><b>Privates Gmail?</b> Im Google-Fenster mit dem <b>privaten</b> Konto anmelden – Rest wie beim Geschäftspostfach.</div>
          <button class="btn ${c.eingerichtet ? "" : "pri"}" type="button" id="mpgm2" style="flex:none">${ic("m98")} ${c.eingerichtet && c.gmail ? "Neu anmelden" : "Mit Google anmelden"}</button></div>
        <div class="small">Andere Anbieter (GMX, web.de, T-Online, iCloud …): Felder ausfüllen. Server bleibt leer = wird aus der Adresse ergänzt.</div>
        <label class="f">E-Mail-Adresse / Benutzer<input class="in" id="mpu" value="${esc(c.user || "")}" placeholder="privat@…"></label>
        <div class="row"><label class="f">IMAP-Server<input class="in" id="mph" value="${esc(c.host || "")}" placeholder="automatisch"></label><label class="f" style="flex:.4">Port<input class="in" id="mpp" type="number" value="${esc(c.port || 993)}"></label></div>
        <label class="chk"><input type="checkbox" id="mps" ${c.ssl !== false ? "checked" : ""}> SSL/TLS (993)</label>
        <label class="f">Passwort / App-Passwort<input class="in" id="mppw" type="password" autocomplete="new-password" placeholder="${c.passwort ? "•••••••• (gespeichert – nur zum Ändern)" : "Passwort eintragen"}"></label>
        <div class="row"><label class="f">Ordner<input class="in" id="mpf" value="${esc(c.folder || "INBOX")}"></label><label class="f" style="flex:.6">Abruf alle X Min. (0 = aus)<input class="in" id="mpi" type="number" value="${esc(c.interval ?? 15)}"></label>
          <label class="f" style="flex:.6">Erster Abruf: letzte X Tage<input class="in" id="mpt" type="number" value="${esc(c.tage || 60)}"></label></div>
        <div class="small muted">Nur lesend – im Postfach wird nichts markiert, verschoben oder gelöscht. Passwort verschlüsselt gespeichert. Mails liegen im Datenordner unter „${esc(c.ordner_pfad || "E-Mails privat")}“.</div>
        <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn pri" style="flex:none" id="mpsv" type="button">${ic("save")} Speichern</button><button class="btn" style="flex:none" id="mptest" type="button">Verbindung testen</button>
          <button class="btn" style="flex:none" id="mpnow2" type="button">${ic("sync")} Jetzt abrufen</button>${c.eingerichtet ? `<button class="btn sm ghost danger" style="flex:none" id="mpdel" type="button">Postfach entfernen</button>` : ""}</div>
        <div class="small" id="mpres">${last.zeit ? `Letzter Abruf ${esc(when(last.zeit))}: <span style="color:${last.ok ? "var(--ok)" : "var(--bad)"}">${esc(last.text || "")}</span>` : ""}</div></div></div>
      <div class="card"><div class="hd"><h3>Was mit privaten Mails passiert</h3></div><div class="bd fr small">
        <div>✓ Abgerufen, gespeichert und auf der Seite <b>Privat-Mails</b> lesbar (Suche, Markieren, Anhänge öffnen).</div>
        <div>✗ Keine Rechnungserkennung, keine KI, keine Beleg-Prüfliste.</div>
        <div>✗ Nicht in Belegen, Buchhaltung, Steuer, DATEV, GoBD-Protokoll oder Statistik.</div>
        <div>→ Nur auf Knopfdruck: einzelne Mail „Ans Geschäft übergeben“ – dann wird sie dort wie jede Geschäftsmail geprüft.</div>
        <div>✓ Im Backup des Datenordners enthalten. Bei gesperrtem Programm (PIN) nicht zugänglich.</div></div></div></div>`;
    const vals = () => ({user: $("#mpu", el).value.trim(), host: $("#mph", el).value.trim(), port: pnum($("#mpp", el).value), ssl: $("#mps", el).checked,
      pass: $("#mppw", el).value, folder: $("#mpf", el).value.trim() || "INBOX", interval: pnum($("#mpi", el).value), tage: pnum($("#mpt", el).value) || 60});
    const res = (ok, t) => { $("#mpres", el).innerHTML = `<span style="color:${ok ? "var(--ok)" : "var(--bad)"}">${esc(t)}</span>`; };
    $("#mpgm2", el).onclick = () => window.gmLogin && window.gmLogin("privat");
    $("#mpsv", el).onclick = async () => { const r = await api("/api/mp/speichern", vals()); if (r && r.ok !== false) { toast("Privates Postfach gespeichert"); await reload(); } };
    $("#mptest", el).onclick = async () => { res(true, "teste …"); const r = await api("/api/mp/test", vals(), {quiet: true}); res(r && r.ok, r && r.ok ? r.info : ((r && r.error) || "Fehler")); };
    $("#mpnow2", el).onclick = async () => { res(true, "speichere und rufe ab …"); const s_ = await api("/api/mp/speichern", vals(), {quiet: true});
      if (!s_ || s_.ok === false) { res(false, (s_ && s_.error) || "Fehler"); return; }
      const r = await api("/api/mp/abrufen", {}, {quiet: true}); res(r && r.ok, r && r.ok ? "Abgerufen: " + r.text : ((r && r.error) || "Fehler")); await reload(); };
    const d = $("#mpdel", el); if (d) d.onclick = async () => {
      const v = await modal("Privates Postfach entfernen", `<p class="small">Zugangsdaten werden gelöscht. Was ist mit den schon gespeicherten privaten Mails?</p>`,
        [{label: "Abbrechen", value: null}, {label: "Mails behalten", value: "k"}, {label: "Mails auch löschen", cls: "danger", value: "d"}]);
      if (!v) return; await api("/api/mp/trennen", {mails_loeschen: v === "d"}); toast("Privates Postfach entfernt"); await reload(); vSettings();
    };
  }});

  // ---------------------------------------------------------------- settings E-Mail-Abruf: card "Rechnungs-Absender" (m99b)
  const ent = (EXT.settings || []).find(e => e.key === "mailabruf");
  if (ent) {
    const orig = ent.render;
    ent.render = function(el, ...a){
      const r = orig.call(this, el, ...a);
      (async () => {
        const c = await api("/api/m99b/liste", undefined, {quiet: true}); if (!c || c.ok === false || $("#m99bcard", el)) return;
        const d = document.createElement("div"); d.id = "m99bcard"; d.className = "card"; d.style.marginTop = "16px";
        d.innerHTML = `<div class="hd"><h3>Rechnungs-Absender</h3><div class="act">${c.eigene ? `<span class="badge acc">eigene Liste</span>` : `<span class="badge ok">Standard</span>`}</div></div><div class="bd grid g2" style="align-items:start">
          <div class="fr"><div class="small">Rechnungen aus E-Mails werden <b>nur</b> von diesen Absendern übernommen – und nur, wenn die Mail wirklich eine Rechnung enthält (Anhang, E-Rechnung, Rechnung im Text oder im Kundenportal). Alle anderen Mails werden gespeichert, aber nicht ausgewertet.</div>
            <div class="row" style="gap:6px;flex-wrap:wrap">${c.liste.map(x_ => `<span class="badge ${x_.sperre ? "bad" : "ok"}" style="flex:none">${x_.sperre ? "gesperrt: " : ""}${esc(x_.name)}</span>`).join("")}</div></div>
          <div class="fr"><label class="f">Liste (eine Zeile je Absender)<textarea class="in" id="m99bt" rows="6" style="font-family:Consolas,monospace;font-size:12px">${esc(c.text)}</textarea></label>
            <div class="small muted">Format <b>Name: muster, muster</b> – Muster = Teil der Absender-Domain: <code>apple</code> passt auf apple.com und email.apple.com, <code>*vodafone*</code> auf alles mit „vodafone“. <b>!Name:</b> = gesperrt (geht vor). Der Anzeigename zählt nicht – den kann jeder fälschen.</div>
            <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn" type="button" id="m99bsv" style="flex:none">${ic("save")} Liste speichern &amp; offene Mails neu bewerten</button>${c.eigene ? `<button class="btn ghost sm" type="button" id="m99bstd" style="flex:none">Standard wiederherstellen</button>` : ""}</div></div></div>`;
        el.appendChild(d);
        const save = async body => { const r2 = await api("/api/m99b/liste", body); if (r2 && r2.ok !== false) { toast(r2.hintergrund ? `Gespeichert – ${r2.hintergrund} offene Mails werden im Hintergrund neu bewertet` : `Gespeichert – ${r2.neu_bewertet || 0} offene Mail(s) neu bewertet`); vSettings(); } };
        $("#m99bsv", d).onclick = () => save({text: $("#m99bt", d).value});
        const st = $("#m99bstd", d); if (st) st.onclick = () => save({standard: true});
      })();
      return r;
    };
  }
})();


// ============================================================================
// Teil aus m99c_outlook.js
// ============================================================================
// PA Rechnung v2.4.5 - UI-Modul m99c_outlook: Schnittstelle zu Microsoft Outlook (Desktop)
// Einstellungs-Reiter "Outlook" (Versand ueber Outlook, Abruf aus Outlook), Knopf "Aus Outlook holen" auf der Seite E-Mails.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m99c = '<rect x="2" y="5" width="11" height="14" rx="2"/><circle cx="7.5" cy="12" r="2.6"/><path d="M13 8h8v10h-8M13 9l4 3 4-3"/>';
  const when = t => t ? dde(String(t).slice(0,10)) + " " + String(t).slice(11,16) : "";

  async function fetchNow(btn){
    if (btn) { btn.disabled = true; btn.textContent = "Hole aus Outlook …"; }
    const r = await api("/api/mo/abrufen", {});
    if (btn) btn.disabled = false;
    if (r && r.ok) toast("Outlook: " + r.text);
    await reload();
    if (view === "mails" && typeof vMails === "function") vMails();
    return r;
  }

  // ---------- Outlook data files (.pst/.ost): remembered + read; progress dialog (used by E-Mails and Privat-Mails)
  // file = File (drag & drop / browser picker: only the NAME is used - the program finds the file itself)
  //        or {path, name} (Windows file dialog)
  const jobBody = (s, priv) => {
    const pct = s.phase === "import" && s.gesamt ? Math.round(100 * s.fertig / s.gesamt) : 0;
    const t = s.sekunden || 0, mm = Math.floor(t / 60), ss = String(t % 60).padStart(2, "0");
    const multi = (s.quellen || 1) > 1 ? ` (Datei ${s.nr || 1} von ${s.quellen})` : "";
    return `<div class="fr"><div class="small"><b>${esc(s.aktuell || s.datei)}</b>${multi} → ${priv == null ? "" : priv ? "Privat-Mails (nur speichern)" : "E-Mails (Geschäft, wird auf Rechnungen geprüft)"}</div>
      ${s.state === "fehler" ? `<div style="color:var(--bad)">${esc(s.text)}</div>` :
        s.state === "fertig" ? `<div><span class="badge ok">fertig</span> ${esc(s.text)} · ${s.gesamt} Mail(s) in ${mm}:${ss} min</div>` :
        `<div class="small">${s.phase === "wartet" ? "Wartet, bis die laufende Outlook-Aktualisierung fertig ist …" : s.phase === "export" ? `1/2 Outlook liest die Datei: <b>${s.exportiert}</b> Mail(s) exportiert …` : `2/2 Einlesen: <b>${s.fertig}</b> von ${s.gesamt}`} · ${mm}:${ss} min</div>
         <div style="height:8px;border-radius:4px;background:var(--line2);overflow:hidden"><div style="height:100%;width:${s.phase === "import" ? 30 + pct * 0.7 : s.phase === "export" ? 30 : 4}%;background:var(--acc);transition:width .4s"></div></div>`}</div>`;
  };
  async function jobDialog(st, priv, extra){
    const tok = st.token;
    await modal("Outlook-Datei einlesen", `<div id="mopst">${jobBody(st, priv)}</div>${extra || ""}
      <div class="small muted" style="margin-top:8px">Läuft im Hintergrund weiter, auch wenn du dieses Fenster schließt. Ausgelassen werden „Gelöschte Elemente“, „Junk-E-Mail“, Postausgang und Entwürfe.${priv === false ? " Ausgewertet wird nur, was von deinen Rechnungs-Absendern kommt." : ""}</div>`,
      [{label: "Schließen", cls: "pri"}], false, async mb => {
        while (mb.isConnected) {
          await new Promise(r => setTimeout(r, 1500));
          const s = await api("/api/mo/pst/status?token=" + tok, undefined, {quiet: true});
          if (!s || s.ok === false) break;
          const b = $("#mopst", mb); if (b) b.innerHTML = jobBody(s, priv);
          if (s.state !== "laeuft") break;
        }
      });
    await reload();
    if (view === "mails" && typeof vMails === "function") vMails();
    if (view === "privatmail" && EXT.views.privatmail) EXT.views.privatmail();
    if (view === "set" && setTab === "outlook" && typeof vSettings === "function") vSettings();
  }
  window.moJobDialog = jobDialog;

  async function moPstImport(file, ziel){
    const priv = ziel === "privat";
    let st;
    if (file && file.path && !(file instanceof Blob)) {
      st = await api("/api/mo/datei", {pfad: file.path, ziel}, {quiet: true});
    } else {
      toast(`Suche „${file.name}“ …`);
      st = await api("/api/mo/datei", {name: file.name, groesse: file.size || 0, ziel}, {quiet: true});
      if (st && st.nicht_gefunden) {
        if (st.ost) { toast(st.error, true); return; }
        // .pst whose location is unknown: read the dropped copy once (cannot be remembered)
        toast(`Speicherort von „${file.name}“ unbekannt – wird einmalig eingelesen. Zum Merken über den Knopf „Outlook-Datei“ wählen.`);
        try { st = await upload("/api/upload/pst_" + (priv ? "privat" : "geschaeft"), file); } catch (e) { toast("Übertragung fehlgeschlagen", true); return; }
      }
    }
    if (!st || st.ok === false) { toast((st && st.error) || "Fehler", true); return; }
    await jobDialog(st, priv, st.quelle ? `<div class="small" style="margin-top:8px">${ic("check")} Gemerkt: <b>${esc(st.quelle)}</b> – wird bei jedem Programmstart aktualisiert (nur neue Mails).</div>` : "");
  }
  window.moPstImport = moPstImport;
  // button "Outlook-Datei": Windows file dialog -> path (nothing copied through the window); fallback browser picker
  async function moPstPick(ziel){
    const r = await api("/api/pick", {accept: ".pst,.ost", multiple: false}, {quiet: true});
    if (!r || r.native === false) return pickFilesHtml(".pst,.ost", fs => fs[0] && moPstImport(fs[0], ziel));
    if (!r.ok || !r.files || !r.files.length) return;
    return moPstImport({path: r.files[0].path, name: r.files[0].name}, ziel);
  }
  window.moPstPick = moPstPick;

  // ---------- E-Mails page: button
  if (EXT.views && typeof EXT.views.mails === "function") {
    const orig = EXT.views.mails;
    EXT.views.mails = async function(...a){
      const r = await orig.apply(this, a);
      try {
        const act = $("#main .ph .act");
        if (act && !$("#mopstbtn")) {
          const p = document.createElement("button"); p.type = "button"; p.className = "btn ghost"; p.id = "mopstbtn";
          p.innerHTML = `${ic("m99c")} Outlook-Datei (.pst/.ost)`; p.title = "Ganze Outlook-Datendatei einlesen – alle Ordner. Wird gemerkt und bei jedem Start aktualisiert.";
          p.onclick = () => moPstPick("geschaeft"); act.appendChild(p);
        }
        if (act && S.mo && S.mo.abruf && !$("#mobtn")) {
          const b = document.createElement("button"); b.type = "button"; b.className = "btn"; b.id = "mobtn";
          b.innerHTML = `${ic("m99c")} Aus Outlook holen`; b.title = "Neue Mails aus dem gewählten Outlook-Ordner holen und prüfen";
          b.onclick = () => fetchNow(b); act.prepend(b);
        }
      } catch (e) {}
      return r;
    };
  }

  // ---------- card "Gemerkte Outlook-Dateien" (in the settings tab Outlook)
  const zielL = z => z === "privat" ? "Privat-Mails" : "E-Mails (Geschäft)";
  async function quellenCard(host){
    if (!host) return;
    const q = await api("/api/mo/quellen", undefined, {quiet: true}); if (!q || !host.isConnected) return;
    const lz = q.letzter || {};
    host.innerHTML = `<div class="card"><div class="hd"><h3>${ic("m99c")} Gemerkte Outlook-Dateien</h3><div class="act">${q.laeuft ? `<span class="badge acc">aktualisiert gerade …</span>` : ""}</div></div><div class="bd fr">
      <div class="small">Jede eingefügte .pst/.ost wird hier gemerkt – mit ihrem Ordner. Beim Programmstart werden alle aktualisiert (nur neue Mails); neue .pst-Dateien in einem gemerkten Ordner kommen automatisch dazu.</div>
      <label class="chk"><input type="checkbox" id="moqstart" ${q.beim_start ? "checked" : ""}> Bei jedem Programmstart aktualisieren</label>
      ${q.quellen.length ? `<table class="t"><thead><tr><th>Datei</th><th>Ziel</th><th>Letzte Aktualisierung</th><th></th></tr></thead><tbody>${q.quellen.map(x => `<tr>
        <td><b>${esc(x.name)}</b><div class="small muted" style="word-break:break-all">${esc(x.pfad)}${x.da ? "" : ` <span style="color:var(--bad)">– nicht gefunden</span>`}</div></td>
        <td><select class="in" data-moqz="${x.id}" style="width:auto">${["geschaeft","privat"].map(z => `<option value="${z}" ${x.ziel===z?"selected":""}>${zielL(z)}</option>`).join("")}</select></td>
        <td class="small">${x.status && x.status.zeit ? `${esc(when(x.status.zeit))}<br><span style="color:${x.status.ok ? "var(--ok)" : "var(--bad)"}">${esc(x.status.text || "")}</span>` : (x.erstmal ? "noch nie – alles wird gelesen" : "")}</td>
        <td class="r" style="white-space:nowrap"><button class="btn sm" data-moqs="${x.id}" type="button">${ic("sync")}</button> <button class="btn sm ghost" data-moqd="${x.id}" type="button" title="Nicht mehr merken (eingelesene Mails bleiben)">${ic("trash")}</button></td></tr>`).join("")}</tbody></table>`
        : `<div class="small muted">Noch keine. Auf der Seite E-Mails oder Privat-Mails eine .pst/.ost hineinziehen oder „Outlook-Datei“ klicken.</div>`}
      ${(q.ordner || []).length ? `<div class="small"><b>Gemerkte Ordner:</b> ${q.ordner.map(o => `<span class="badge" style="margin:2px 4px 2px 0">${esc(o.ordner)} → ${zielL(o.ziel)} <a href="#" data-moqo="${esc(o.ordner)}" title="Ordner vergessen">✕</a></span>`).join("")}</div>` : ""}
      <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn" type="button" id="moqall" style="flex:none" ${q.quellen.length ? "" : "disabled"}>${ic("sync")} Jetzt alle aktualisieren</button>
        <button class="btn ghost" type="button" id="moqadd" style="flex:none">${ic("plus")} Datei hinzufügen …</button></div>
      ${lz.zeit ? `<div class="small muted">Letzter Lauf (${esc(lz.grund || "")}) ${esc(when(lz.zeit))}: ${esc(lz.text || "")}</div>` : ""}</div></div>`;
    const post = async body => { await api("/api/mo/quellen", body); quellenCard(host); };
    $("#moqstart", host).onchange = e => post({beim_start: e.target.checked});
    $$("[data-moqz]", host).forEach(sel => sel.onchange = async () => {
      if (!await confirmBox(`Ziel ändern auf „${zielL(sel.value)}“? Die Datei wird dann beim nächsten Lauf komplett neu gelesen.`, "Ändern")) { quellenCard(host); return; }
      post({ziel_id: sel.dataset.moqz, ziel: sel.value}); });
    $$("[data-moqd]", host).forEach(b => b.onclick = () => post({entfernen: b.dataset.moqd}));
    $$("[data-moqo]", host).forEach(a => a.onclick = e => { e.preventDefault(); post({ordner_entfernen: a.dataset.moqo}); });
    const run = async ids => { const r = await api("/api/mo/quellen/sync", ids ? {ids} : {}); if (r && r.ok !== false) jobDialog(r, null); };
    $$("[data-moqs]", host).forEach(b => b.onclick = () => run([b.dataset.moqs]));
    $("#moqall", host).onclick = () => run(null);
    $("#moqadd", host).onclick = async () => { const z = await modal("Outlook-Datei hinzufügen", `<div class="small">Wohin sollen die Mails?</div>`,
      [{label: "Abbrechen", value: null}, {label: "Privat-Mails", value: "privat"}, {label: "E-Mails (Geschäft)", cls: "pri", value: "geschaeft"}]); if (z) moPstPick(z); };
  }

  // ---------- settings tab "Outlook"
  EXT.settings.push({key: "outlook", label: "Outlook", async render(el){
    const c = await api("/api/mo/config", undefined, {quiet: true}) || {};
    let info = null;
    const opts = (sel, withDef) => (withDef ? `<option value="">Standardkonto von Outlook</option>` : "") +
      ((info && info.konten) || []).map(k => `<option value="${esc(k.smtp)}" ${k.smtp.toLowerCase() === String(sel || "").toLowerCase() ? "selected" : ""}>${esc(k.name)}${k.smtp && k.smtp !== k.name ? " – " + esc(k.smtp) : ""}</option>`).join("") +
      (sel && !((info && info.konten) || []).some(k => k.smtp.toLowerCase() === String(sel).toLowerCase()) ? `<option value="${esc(sel)}" selected>${esc(sel)}</option>` : "");
    const folders = () => { const k = ((info && info.konten) || []).find(k => k.smtp.toLowerCase() === String($("#mokab", el).value || "").toLowerCase()) || ((info && info.konten) || [])[0];
      const cur = $("#moord", el) ? $("#moord", el).value : c.ordner;
      return `<option value="">${esc((k && k.posteingang) || "Posteingang")}</option>` + ((k && k.ordner) || []).map(o => `<option value="${esc(o)}" ${o === cur ? "selected" : ""}>${esc((k && k.posteingang) || "Posteingang")} / ${esc(o)}</option>`).join("") +
        (cur && !((k && k.ordner) || []).includes(cur) ? `<option value="${esc(cur)}" selected>${esc(cur)}</option>` : ""); };
    const draw = () => {
      const st = c.status || {}, vs = c.versand_status || {};
      el.innerHTML = `${!c.windows ? `<div class="alert warn small">Die Outlook-Schnittstelle gibt es nur unter Windows.</div>` : ""}
      <div class="card"><div class="hd"><h3>${ic("m99c")} Microsoft Outlook</h3><div class="act">${info ? (info.ok === false ? `<span class="badge bad">nicht gefunden</span>` : `<span class="badge ok"><span class="dot"></span>Outlook ${esc(String(info.version || "").split(".")[0])} · ${(info.konten || []).length} Konto/Konten</span>`) : ""}
          <button class="btn sm" type="button" id="moscan">Outlook suchen</button></div></div>
        <div class="bd small">${info && info.ok === false ? `<div style="color:var(--bad)">${esc(info.error)}</div>` : `Das Programm arbeitet mit deinem installierten Outlook zusammen (das „klassische“ Outlook aus Microsoft 365/Office). Das <b>neue</b> Outlook hat keine Schnittstelle für Programme – dort ggf. oben rechts „Neues Outlook“ ausschalten.`}</div></div>
      <div class="grid g2" style="align-items:start;margin-top:16px">
        <div class="card"><div class="hd"><h3>Versand über Outlook</h3><div class="act">${c.versand ? `<span class="badge ok">an</span>` : `<span class="badge">aus – Versand per SMTP</span>`}</div></div><div class="bd fr">
          <label class="chk"><input type="checkbox" id="mov" ${c.versand ? "checked" : ""}> Rechnungen, Angebote, Mahnungen und automatische Mails über Outlook senden</label>
          <label class="f">Absender-Konto in Outlook<select class="in" id="mokv">${opts(c.konto, true)}</select></label>
          <label class="chk"><input type="checkbox" id="moa" ${c.anzeigen ? "checked" : ""}> Mail vorher im Outlook-Fenster anzeigen – ich klicke dort selbst auf Senden</label>
          <div class="small muted">Gesendete Mails liegen in Outlook unter „Gesendete Elemente“. Mit „vorher anzeigen“ gilt das Dokument im Programm als versendet, sobald das Outlook-Fenster aufgeht.</div>
          <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn" type="button" id="motest" style="flex:none">Test-Mail über Outlook</button></div>
          <div class="small" id="mores">${vs.zeit ? `Zuletzt: ${esc(when(vs.zeit))} an ${esc(vs.an || "")}${vs.angezeigt ? " (im Outlook-Fenster geöffnet)" : ""}` : ""}</div></div></div>
        <div class="card"><div class="hd"><h3>Mails aus Outlook holen</h3><div class="act">${c.abruf ? `<span class="badge ok">an</span>` : `<span class="badge">aus</span>`}</div></div><div class="bd fr">
          <label class="chk"><input type="checkbox" id="mob" ${c.abruf ? "checked" : ""}> Mails aus Outlook ins Programm holen und auf Rechnungen prüfen</label>
          <label class="f">Konto<select class="in" id="mokab">${opts(c.konto_abruf, true)}</select></label>
          <label class="f">Ordner<select class="in" id="moord">${folders()}</select></label>
          <div class="row"><label class="f">Abruf alle X Min. (0 = nur per Knopf)<input class="in" type="number" id="moi" value="${esc(c.interval ?? 0)}"></label><label class="f">Erster Abruf: letzte X Tage<input class="in" type="number" id="mot" value="${esc(c.tage || 60)}"></label></div>
          <div class="small muted">In Outlook ändert sich nichts. Es gilt die Liste der Rechnungs-Absender (Reiter E-Mail-Abruf) – alles andere wird nur gespeichert, nicht ausgewertet. Outlook muss dafür nicht offen sein.</div>
          <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn" type="button" id="monow" style="flex:none">${ic("sync")} Jetzt aus Outlook holen</button></div>
          <div class="small" id="mores2">${st.zeit ? `Letzter Abruf ${esc(when(st.zeit))}: <span style="color:${st.ok ? "var(--ok)" : "var(--bad)"}">${esc(st.text || "")}</span>` : ""}</div></div></div></div>
      <div class="row" style="margin-top:12px"><button class="btn pri" type="button" id="mosv" style="flex:none">${ic("save")} Outlook-Einstellungen speichern</button></div>
      <div id="moqhost" style="margin-top:16px"></div>`;
      quellenCard($("#moqhost", el));
      const vals = () => ({versand: $("#mov", el).checked, anzeigen: $("#moa", el).checked, konto: $("#mokv", el).value, abruf: $("#mob", el).checked,
        konto_abruf: $("#mokab", el).value, ordner: $("#moord", el).value, interval: pnum($("#moi", el).value), tage: pnum($("#mot", el).value) || 60});
      const save = async quiet => { const r = await api("/api/mo/speichern", vals()); if (r && r.ok !== false) { Object.assign(c, r); if (!quiet) toast("Outlook-Einstellungen gespeichert"); await reload(); } return r; };
      $("#mokab", el).onchange = () => { $("#moord", el).innerHTML = folders(); };
      $("#moscan", el).onclick = async e => { e.target.disabled = true; e.target.textContent = "suche …"; info = await api("/api/mo/info", undefined, {quiet: true}) || {ok: false, error: "keine Antwort"}; Object.assign(c, vals()); draw(); };
      $("#mosv", el).onclick = () => save();
      $("#motest", el).onclick = async () => { await save(true); $("#mores", el).textContent = "sende über Outlook …";
        const r = await api("/api/mo/test", {}, {quiet: true}); $("#mores", el).innerHTML = r && r.ok ? `<span style="color:var(--ok)">${esc((r.schritte || []).join(" "))}</span>` : `<span style="color:var(--bad)">${esc((r && r.error) || "Fehler")}</span>`; };
      $("#monow", el).onclick = async () => { await save(true); $("#mores2", el).textContent = "hole aus Outlook …";
        const r = await api("/api/mo/abrufen", {}, {quiet: true}); $("#mores2", el).innerHTML = r && r.ok ? `<span style="color:var(--ok)">${esc(r.text)}</span>` : `<span style="color:var(--bad)">${esc((r && r.error) || "Fehler")}</span>`; };
      const ss = $("#ssave"); if (ss) ss.addEventListener("click", () => save(true), {once: true});
    };
    draw();
    if (c.windows) { info = await api("/api/mo/info", undefined, {quiet: true}) || null; if (info && info.ok === false) info = {ok: false, error: info.error}; Object.assign(c, {}); if (el.isConnected) draw(); }
  }});
})();
