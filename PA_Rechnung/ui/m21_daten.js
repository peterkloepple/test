// PA Rechnung v2.0.0 - Datenordner aendern, Backup mit Versionen, Selbsttest
// Autor: T. Pfeiffer
(function(){
  IC.disk = IC.disk || '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v5h10V4M8 15h8"/>';
  IC.shield = IC.shield || '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>';

  async function datenCard(host){
    const i = await api("/api/datadir");
    const card = document.createElement("div"); card.className = "card"; card.style.marginBottom = "16px";
    card.innerHTML = `<div class="hd"><h3>${ic("disk")} Datenordner</h3><div class="act"><button class="btn sm" id="ddopen">${ic("folder")} Öffnen</button><button class="btn sm pri" id="ddchg">Ändern …</button></div></div>
      <div class="bd fr">
        <div style="font:600 15px/1.4 Consolas,monospace;word-break:break-all;padding:8px 10px;background:var(--panel2);border-radius:8px">${esc(i.path)}</div>
        <div class="small muted">${i.files} Dateien · ${nde(i.size_mb,1)} MB · ${i.is_default?"Standardort (Dokumente)":"eigener Ort"}${i.env?" · fest vorgegeben über PA_RECHNUNG_DATA":""}</div>
        <div class="small muted">Hier liegen Datenbank, Belege, Projekte, Exporte und Backups. Installierte Programm-Updates bleiben immer unter <b>${esc(i.programm_dir)}</b>.</div>
      </div>`;
    host.prepend(card);
    $("#ddopen", card).onclick = () => api("/api/open", {path:i.path, folder:true});
    $("#ddchg", card).onclick = () => changeDialog(i);
    if (i.env) $("#ddchg", card).disabled = true;
  }

  async function changeDialog(i){
    let chk = null;
    await modal("Datenordner ändern", `<div class="fr nokeep">
      <div class="small muted">Aktuell: <b>${esc(i.path)}</b></div>
      <label class="f">Neuer Ordner<div class="row" style="gap:6px"><input class="in" id="ddp" placeholder="z. B. D:\\Buchhaltung\\Pfeiffer-Audio Rechnung" style="flex:1"><button class="btn" type="button" id="ddpick" style="flex:none">Durchsuchen …</button></div></label>
      <div class="seg" id="ddmode" style="display:flex">
        <button class="on" data-m="move" style="flex:1">Umziehen</button><button data-m="copy" style="flex:1">Kopieren</button><button data-m="use" style="flex:1">Vorhandene Daten verwenden</button></div>
      <div class="small" id="ddhelp"></div>
      <div id="ddres" class="small"></div>
      ${!i.is_default?`<div class="small muted">Zurück zum Standardort: <a href="#" id="dddef">Standard (Dokumente) wieder verwenden</a></div>`:""}
    </div>`, [{label:"Abbrechen"}, {label:"Prüfen & ausführen", cls:"pri", value:true, onClick: async mb => {
        const path = $("#ddp", mb).value.trim(), mode = $("#ddmode button.on", mb).dataset.m;
        chk = await api("/api/datadir/check", {path}); if (!chk || chk.ok === false) return false;
        if (chk.fehler) { $("#ddres", mb).innerHTML = `<span style="color:var(--bad)">${esc(chk.fehler)}</span>`; return false; }
        const w = (chk.warnungen||[]).map(x=>"⚠ "+x).join("\n");
        const txt = mode==="use" ? `Ab jetzt die Daten aus\n${chk.path}\nverwenden?\n\nDas Programm startet danach neu.`
          : `${chk.need_mb} MB nach\n${chk.path}\n${mode==="move"?"umziehen":"kopieren"}?\n\nDas Programm startet danach neu und arbeitet im neuen Ordner.${mode==="move"?"\nDie alten Daten werden NICHT gelöscht, sondern im alten Ordner unter „_alter_Datenordner_<Datum>“ abgelegt.":"\nDer alte Ordner bleibt unverändert."}`;
        if (!await confirmBox((w?w+"\n\n":"") + txt, mode==="use"?"Verwenden":"Ausführen")) return false;
        toast("Daten werden kopiert und geprüft …");
        const x_ = await api("/api/datadir/change", {path:chk.path, mode});
        if (!x_ || !x_.ok) return false;
        toast(`Fertig – ${x_.dateien||""} Dateien. Programm startet neu …`);
      }}], true, mb => {
        const help = {move:"Kopiert alle Daten in den neuen Ordner, prüft jede Datei und schaltet um. Der alte Ordner wird danach archiviert (nichts wird gelöscht).",
          copy:"Wie Umziehen, aber der alte Ordner bleibt komplett unverändert stehen.", use:"Für einen Ordner, in dem schon Programmdaten liegen (z. B. nach Neuinstallation oder von einer Sicherung)."};
        const setH = () => $("#ddhelp", mb).textContent = help[$("#ddmode button.on", mb).dataset.m];
        $$("#ddmode button", mb).forEach(b => b.onclick = () => { $$("#ddmode button", mb).forEach(x_ => x_.classList.toggle("on", x_ === b)); setH(); });
        setH();
        $("#ddpick", mb).onclick = async () => { const p = await pickFolder(); if (p) $("#ddp", mb).value = p; };
        const df = $("#dddef", mb); if (df) df.onclick = async ev => { ev.preventDefault(); if (!await confirmBox(`Wieder den Standardordner verwenden?\n${i.default}`, "Umschalten")) return;
          const x_ = await api("/api/datadir/change", {mode:"default"}); if (x_ && x_.ok) toast("Programm startet neu …"); };
      });
  }

  async function backupCard(host){
    const b = await api("/api/backup/list"), s = b.einstellungen;
    const card = document.createElement("div"); card.className = "card"; card.style.marginBottom = "16px";
    card.innerHTML = `<div class="hd"><h3>${ic("shield")} Backup mit Versionen</h3><div class="act"><button class="btn sm" id="bknow">${ic("save")} Komplett-Backup jetzt</button><button class="btn sm pri" id="bksave">Übernehmen</button></div></div>
      <div class="bd fr nokeep">
        <div class="small muted">Täglich wird die Datenbank gesichert, sonntags komplett mit allen Dateien (Belege, Projekte, Rechnungen, Briefe …). Aufbewahrt werden die letzten Tage, Wochen und Monate – ältere Versionen werden automatisch aufgeräumt.${b.letztes?` Letztes Auto-Backup: <b>${dde((b.letztes.zeit||"").slice(0,10))}</b>${b.letztes.fehler?` <span style="color:var(--bad)">· ${esc(b.letztes.fehler)}</span>`:""}`:""}</div>
        <div class="row"><label class="f">täglich behalten<input class="in num" id="bkd" value="${s.bk_keep_daily}"></label><label class="f">wöchentlich<input class="in num" id="bkw" value="${s.bk_keep_weekly}"></label><label class="f">monatlich<input class="in num" id="bkm" value="${s.bk_keep_monthly}"></label></div>
        <label class="chk"><input type="checkbox" id="bkfull" ${s.bk_full_weekly?"checked":""}> sonntags Komplett-Backup inkl. aller Dateien</label>
        <div><div class="small" style="margin-bottom:4px"><b>Backup-Ziele</b> (NAS, OneDrive, USB …) – zusätzlich zum Datenordner</div><div id="bktg"></div>
          <button class="btn sm" type="button" id="bkadd">+ Ziel hinzufügen</button></div>
        <label class="chk"><input type="checkbox" id="bkenc" ${s.bk_encrypt?"checked":""}> Kopien in den Zielen verschlüsseln (AES-256-ZIP, mit 7-Zip/WinZip und Passwort lesbar)</label>
        <label class="f">Backup-Passwort ${s.bk_has_pw?`<span class="badge ok">gesetzt</span>`:`<span class="badge">nicht gesetzt</span>`}<input class="in" type="password" id="bkpw" placeholder="${s.bk_has_pw?"leer lassen = unverändert":"mind. 8 Zeichen"}" autocomplete="new-password"></label>
        <div class="small muted">Passwort gut aufbewahren – ohne Passwort lassen sich verschlüsselte Backups nicht öffnen.</div>
        <details><summary class="small"><b>${b.liste.length} Backup-Versionen</b> anzeigen / wiederherstellen</summary>
          <div class="scroll" style="max-height:300px;margin-top:8px"><table class="t"><thead><tr><th>Datum</th><th>Art</th><th>Ort</th><th class="r">MB</th><th></th></tr></thead><tbody>
          ${b.liste.map((r,ix)=>`<tr><td class="num">${dde(r.datum)}${r.zeit?" "+r.zeit.slice(0,2)+":"+r.zeit.slice(2):""}</td><td>${r.vor_wiederherstellung?"Sicherung vor Wiederherstellung":(r.voll?"komplett":"Datenbank")}${r.verschluesselt?" 🔒":""}</td><td class="small muted">${esc(r.ort)}</td><td class="r num">${nde(r.mb,2)}</td>
            <td class="r"><button class="btn sm ghost" data-bkr="${ix}">Wiederherstellen</button></td></tr>`).join("") || `<tr><td colspan="5" class="empty">Noch keine Backups.</td></tr>`}</tbody></table></div></details>
      </div>`;
    host.prepend(card);
    let targets = s.bk_targets.slice();
    const rT = () => { $("#bktg", card).innerHTML = targets.map((t,ix)=>`<div class="row" style="align-items:center;gap:6px;margin-bottom:4px"><span class="small" style="flex:1;font-family:Consolas,monospace;word-break:break-all">${esc(t)}</span><button class="btn sm ghost" style="flex:none" data-bkx="${ix}">✕</button></div>`).join("") || `<div class="small muted">keins</div>`;
      $$("[data-bkx]", card).forEach(x_ => x_.onclick = () => { targets.splice(+x_.dataset.bkx, 1); rT(); }); };
    rT();
    $("#bkadd", card).onclick = async () => { const p = await pickFolder(); if (p && !targets.includes(p)) { targets.push(p); rT(); } };
    $("#bksave", card).onclick = async () => {
      const d = {bk_keep_daily:pnum($("#bkd",card).value), bk_keep_weekly:pnum($("#bkw",card).value), bk_keep_monthly:pnum($("#bkm",card).value),
        bk_full_weekly:$("#bkfull",card).checked, bk_encrypt:$("#bkenc",card).checked, bk_targets:targets};
      const pw = $("#bkpw",card).value; if (pw) d.bk_pw = pw;
      if (d.bk_encrypt && !s.bk_has_pw && !pw) { toast("Für die Verschlüsselung bitte ein Passwort eingeben", true); return; }
      const r = await api("/api/backup/settings", d); if (r.ok) { await reload(); toast("Backup-Einstellungen gespeichert"); vSettings(); } };
    $("#bknow", card).onclick = async () => { toast("Komplett-Backup läuft …"); const r = await api("/api/backup/now", {}); if (r.ok) { toast(r.warn ? r.warn : "Backup erstellt: " + r.datei, !!r.warn); vSettings(); } };
    $$("[data-bkr]", card).forEach(x_ => x_.onclick = async () => {
      const it = b.liste[+x_.dataset.bkr];
      await modal("Backup wiederherstellen", `<div class="fr nokeep"><div>Stand vom <b>${dde(it.datum)}</b> (${it.voll?"komplett":"nur Datenbank"}) aus <b>${esc(it.ort)}</b> zurückholen?</div>
        <div class="hl small">Deine aktuellen Daten werden vorher automatisch gesichert („…_vor_wiederherstellung“). Danach startet das Programm neu.</div>
        ${it.verschluesselt?`<label class="f">Passwort (leer = gespeichertes verwenden)<input class="in" type="password" id="bkrpw"></label>`:""}
        ${it.voll?`<label class="chk"><input type="checkbox" id="bkrf" checked> fehlende Dateien aus dem Backup ergänzen (Belege, Projekte, Rechnungen, Briefe …)</label>`:""}</div>`,
        [{label:"Abbrechen"}, {label:"Wiederherstellen", cls:"danger", value:true, onClick: async mb => {
          const r = await api("/api/backup/restore", {pfad:it.pfad, pw:$("#bkrpw",mb)?$("#bkrpw",mb).value:"", dateien:$("#bkrf",mb)?$("#bkrf",mb).checked:false});
          if (!r || !r.ok) return false; toast(`Wiederhergestellt (${r.rechnungen} Rechnungen) – Programm startet neu …`); }}]);
    });
  }

  async function selftestCard(host){
    const card = document.createElement("div"); card.className = "card"; card.style.marginBottom = "16px";
    card.innerHTML = `<div class="hd"><h3>${ic("check")} Selbsttest</h3><div class="act"><button class="btn sm" id="sttest">Jetzt prüfen</button></div></div>
      <div class="bd"><div class="small muted" id="stres">Rechnet Statistik, EÜR, Steuer, PDF- und Excel-Erzeugung sowie alle Module mit Beispieldaten in einer Testdatenbank durch – deine Daten werden dabei nicht berührt. Jedes eingespielte Update wird automatisch so geprüft und nur aktiviert, wenn alles stimmt.</div></div>`;
    host.appendChild(card);
    $("#sttest", card).onclick = async () => { $("#stres", card).textContent = "läuft …"; const r = (await api("/api/selbsttest", {})) || {};
      $("#stres", card).innerHTML = r.ok ? `<span style="color:var(--ok)">✓ Alles in Ordnung</span> – ${r.tests} Testgruppen, ${(r.module || []).length} Module, ${nde(r.dauer_s,1)} s`
        : (f_ => `<span style="color:var(--bad)">✗ ${f_.length} Problem(e):</span><ul>${f_.map(e=>`<li>${esc(e)}</li>`).join("")}</ul>`)(r.fehler || [r.error || "Selbsttest fehlgeschlagen"]); };
  }

  EXT.after.push(async (n) => {
    if (n !== "vSettings" || setTab !== "daten") return;
    const grid = $("#main .page .grid"); if (!grid || grid.dataset.v2) return; grid.dataset.v2 = "1";
    // the old one-line hint and backup target field are replaced by the cards
    const oldHint = [...grid.querySelectorAll(".small.muted")].find(e => e.textContent.startsWith("Datenordner:")); if (oldHint) oldHint.remove();
    const bt = grid.querySelector('[data-s="backup_target"]'); if (bt) { const l = bt.closest("label"); if (l) l.remove(); }
    const wrap = document.createElement("div"); wrap.style.gridColumn = "1 / -1";
    grid.prepend(wrap);
    const two = document.createElement("div"); two.className = "grid g2"; two.style.alignItems = "start"; wrap.appendChild(two);
    const left = document.createElement("div"), right = document.createElement("div"); two.append(left, right);
    await datenCard(left); await selftestCard(left); await backupCard(right);
  });

  // data folder always visible: tooltip on the version in the sidebar footer
  EXT.after.push(() => { const f = $(".sidefoot > span"); if (f && S.data_dir) f.title = "Datenordner: " + S.data_dir; });
})();
