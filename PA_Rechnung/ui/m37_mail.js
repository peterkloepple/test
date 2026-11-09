// PA Rechnung v2.0.17 - E-Mail: Anbieter-Vorlagen, Test mit Schritt-Protokoll, Microsoft-Anmeldung (OAuth2)
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const g = k => $(`[data-s="${k}"]`);
  const provFor = (user, host) => {
    const L = S.mail_providers || [], dom = (user||"").includes("@") ? user.split("@").pop().toLowerCase() : "", h = (host||"").trim().toLowerCase();
    return L.find(p => dom && p.domains.includes(dom)) || L.find(p => h && p.smtp[0] && (p.smtp[0] === h || p.imap[0] === h)) || null;
  };
  const resHtml = r => `<div class="card" style="padding:10px;margin-top:4px;border-color:${r.ok?"var(--ok)":"var(--bad)"}">
    ${r.ok?`<div style="color:var(--ok);font-weight:600">✓ Test-Mail an ${esc(r.an)} gesendet – bitte Posteingang (und Spam-Ordner) prüfen.</div>`:`<div style="color:var(--bad);font-weight:600">Versand fehlgeschlagen</div><div class="small" style="margin-top:4px">${esc(r.error||"")}</div>`}
    ${(r.schritte||[]).length?`<div class="small muted" style="margin-top:6px;white-space:pre-line">${esc((r.schritte||[]).join("\n"))}</div>`:""}</div>`;

  window.mailTest = async function(){
    const box = $("#mres"); if (box) box.innerHTML = `<div class="small muted">teste … (bis zu 30 Sekunden)</div>`;
    const d = {host:g("smtp_host").value, port:pnum(g("smtp_port").value), sec:g("smtp_sec").value, user:g("smtp_user").value, pass:g("smtp_pass_new").value,
      from_name:g("smtp_from").value, from_addr:g("smtp_from_addr").value, auth:g("smtp_auth").value, verify:!g("smtp_noverify").checked};
    const r = await api("/api/mail/test", d, {quiet:true});
    if (box) box.innerHTML = resHtml(r || {ok:false, error:"Keine Antwort vom Programm."});
    const st = $("#mstat"); if (st && r) { const z = new Date(); st.innerHTML = `Letzter Test: ${z.toLocaleDateString("de-DE")} ${z.toTimeString().slice(0, 5)} – ${r.ok ? "OK" : `<span style="color:var(--bad)">fehlgeschlagen (siehe oben)</span>`}`; }
    if (r && r.ok) { toast("Test-Mail gesendet – Posteingang prüfen" + (r.gespeichert ? " · Passwort gespeichert" : ""));
      if (r.gespeichert) { const pw = g("smtp_pass_new"); if (pw) { pw.value = ""; pw.placeholder = "•••••••• (gespeichert – nur zum Ändern eintragen)"; } S.smtp_set = true; S.smtp_fremd = false; const f = $("#mfremd"); if (f) f.remove(); } }
  };

  async function msLogin(){
    const cid = g("ms_client_id").value.trim(), ten = g("ms_tenant").value.trim() || "common";
    if (!/^[0-9a-fA-F-]{36}$/.test(cid)) { toast("Bitte zuerst die Anwendungs-ID (Client-ID) eintragen – Anleitung im Handbuch, Kapitel 13", true); return; }
    await api("/api/settings/save", {ms_client_id:cid, ms_tenant:ten, smtp_auth:"ms"}, {quiet:true});
    const r = await api("/api/mail/ms/start", {client_id:cid, tenant:ten});
    if (!r || r.ok === false) return;
    let stop = false, mref = null;
    const pr = modal("Bei Microsoft anmelden", `<div class="fr"><div>1. Im Browser öffnet sich <b>${esc(r.url)}</b> (sonst den Link von Hand öffnen).</div>
      <div>2. Diesen Code eingeben:</div><div style="font:700 28px Consolas,monospace;letter-spacing:4px;text-align:center;user-select:all;padding:10px;background:var(--panel2);border-radius:10px">${esc(r.code)}</div>
      <div>3. Mit dem Microsoft-Konto anmelden, das die Mails verschickt, und den Zugriff erlauben.</div>
      <div class="small muted" id="msw">warte auf die Anmeldung …</div></div>`, [{label:"Abbrechen", value:0}], false, m => { mref = m; });
    pr.then(() => { stop = true; });
    for (let i = 0; i < 200 && !stop; i++) {
      await new Promise(res => setTimeout(res, 3000));
      const st = await api("/api/mail/ms/status", undefined, {quiet:true});
      const f = st && st.flow;
      if (f && f.state === "fertig") { stop = true; if (mref && mref.isConnected) $(".mf .btn", mref).click();
        toast("Mit Microsoft verbunden" + (st.konto ? " als " + st.konto : "")); await reload(); vSettings(); return; }
      if (f && f.state === "fehler") { const w = $("#msw"); if (w) w.innerHTML = `<span style="color:var(--bad)">${esc(f.msg)}</span>`; return; }
    }
  }

  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "mail" || !g("smtp_host")) return;
    const auth = $("#mauth"), mpw = $(".mpw"), mms = $(".mms"), sel = $("#mprov"), hint = $("#mhint");
    const vis = () => { const ms = auth.value === "ms"; mpw.style.display = ms ? "none" : ""; mms.style.display = ms ? "" : "none"; };
    const showHint = () => { const p = provFor(g("smtp_user").value, g("smtp_host").value);
      if (p && sel.value === "") sel.value = p.id;
      const ps = (S.mail_providers||[]).find(x => x.id === sel.value) || p;
      if (ps && ps.hint) { hint.style.display = ""; hint.textContent = ps.hint; } else hint.style.display = "none"; };
    auth.onchange = vis; vis();
    sel.onchange = () => { const p = (S.mail_providers||[]).find(x => x.id === sel.value); if (!p) return;
      if (p.smtp[0]) g("smtp_host").value = p.smtp[0]; g("smtp_port").value = p.smtp[1]; g("smtp_sec").value = p.smtp[2] || "auto";
      if (p.auth === "ms") { auth.value = "ms"; vis(); } else if (auth.value === "ms") { auth.value = "pass"; vis(); }
      const ih = g("mi_host"), ip = g("mi_port"); if (ih && !ih.value && p.imap[0]) { ih.value = p.imap[0]; if (ip) ip.value = p.imap[1]; }
      showHint(); };
    g("smtp_user").addEventListener("change", () => { sel.value = ""; showHint(); });
    showHint();
    // v2.0.17: password stored on another PC / Windows user -> say so right at the field
    if (S.smtp_fremd && mpw && !$("#mfremd")) { const n = document.createElement("div"); n.id = "mfremd"; n.className = "small"; n.style.cssText = "color:var(--bad);margin-top:4px";
      n.textContent = "Das gespeicherte Passwort stammt von einem anderen PC oder Windows-Benutzer und ist hier nicht lesbar. Bitte hier eintragen und speichern (oder Test-Mail senden – bei Erfolg wird es gespeichert). Die anderen PCs behalten ihr Passwort.";
      mpw.appendChild(n); }
    const go_ = $("#msgo"); if (go_) go_.onclick = msLogin;
    const out = $("#msout"); if (out) out.onclick = async e => { e.preventDefault(); await api("/api/mail/ms/logout", {}); await reload(); vSettings(); toast("Microsoft-Anmeldung entfernt"); };
  });

  // E-Mail-Abruf (IMAP): same login method as for sending
  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "mailabruf") return;
    const mih = g("mi_user");
    if (!mih || g("mi_auth")) return;
    const l = document.createElement("label"); l.className = "f";
    l.innerHTML = `Anmeldung am Postfach<select class="in" data-s="mi_auth"><option value="pass">Passwort / App-Passwort (leer = Passwort vom Versand, wenn gleicher Benutzer)</option><option value="ms">Microsoft-Konto (OAuth2, wie beim Versand)</option></select>`;
    mih.closest("label").after(l);
    const se = $("select", l); se.value = S.settings.mi_auth === "ms" ? "ms" : "pass";
    const pw = $("#mipw"); const vis = () => { if (pw) pw.closest("label").style.display = se.value === "ms" ? "none" : ""; };
    se.onchange = () => { vis(); api("/api/settings/save", {mi_auth:se.value}, {quiet:true}); };
    vis();
    if (se.value === "ms" && !S.ms_verbunden) l.insertAdjacentHTML("beforeend", `<div class="small" style="color:var(--warn)">Noch nicht bei Microsoft angemeldet – Reiter „E-Mail“ › Bei Microsoft anmelden.</div>`);
    const ih = g("mi_host"), ip = g("mi_port");
    if (ih && !ih.value && S.settings.smtp_user) { const p = provFor(S.settings.smtp_user, S.settings.smtp_host); if (p && p.imap[0]) { ih.value = p.imap[0]; if (ip) ip.value = p.imap[1]; } }
  });
})();
