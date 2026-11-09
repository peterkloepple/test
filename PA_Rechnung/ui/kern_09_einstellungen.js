// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Einstellungen
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- settings ----------
let setTab = "firma";
function vSettings(){
  const s = S.settings;
  const f = (k,l,ph="",type="text") => `<label class="f">${l}<input class="in" data-s="${k}" type="${type}" value="${esc(s[k]??"")}" placeholder="${esc(ph)}"></label>`;
  const ta = (k,l,r=3) => `<label class="f">${l}<textarea class="in" data-s="${k}" rows="${r}">${esc(s[k]??"")}</textarea></label>`;
  const tabs = [["firma","Firma & Bank"],["docs","Dokumente & Nummern"],["mail","E-Mail"],["mahn","Mahnwesen"],["proj","Projekte & Kalkulation"],["assist","Assistent / KI"],["daten","Daten, Backup & Update"], ...EXT.settings.map(t=>[t.key,t.label])];
  let body = "";
  if (setTab === "firma") body = `<div class="grid g2" style="align-items:start">
      <div class="card"><div class="hd"><h3>Firma & Absender</h3></div><div class="bd fr">
        <div class="row"><div style="flex:none;text-align:center"><img src="/logo?${Date.now()}" style="width:64px;height:96px;object-fit:contain;border:1px solid var(--line);border-radius:10px;background:#fff;padding:4px"><br><button class="btn sm" id="logo" style="margin-top:6px">Logo ändern</button></div>
          <div class="fr" style="flex:1">${f("firma","Firmenname (oben rechts)")}${f("inhaber","Inhaber / Name")}</div></div>
        ${f("absender","Absenderzeile über der Anschrift")}
        <label class="f">Farbe Markierung „Rechnung Nr.“<input class="in" type="color" data-s="highlight" value="${esc(s.highlight)}" style="height:38px;padding:3px"></label></div></div>
      <div class="card"><div class="hd"><h3>Bank & Zahlung</h3></div><div class="bd fr">
        <div class="row">${f("bank","Bank")}${f("bic","BIC")}</div>${f("iban","IBAN")}${f("kontoinhaber","Kontoinhaber (für QR-Code)")}
        <div class="row">${f("paypal_mail","PayPal-E-Mail")}${f("paypal_me","PayPal.me-Name (optional)","z. B. ThomasPfeiffer")}</div>
        <div class="row"><label class="f">Standard-Zahlart<select class="in" data-s="zahlart">${[["Ueberweisung","Überweisung"],["PayPal","PayPal"],["Bar","Bar"]].map(([k,l])=>`<option value="${k}" ${s.zahlart===k?"selected":""}>${l}</option>`).join("")}</select></label>${f("frist","Zahlungsfrist (Tage)","","number")}</div></div></div>
      <div class="card" style="grid-column:1/-1"><div class="hd"><h3>Fußzeile (4 Spalten)</h3></div><div class="bd grid g4">${ta("fuss1","Spalte 1")}${ta("fuss2","Spalte 2")}${ta("fuss3","Spalte 3")}${ta("fuss4","Spalte 4 (rechtsbündig)")}</div></div></div>`;
  if (setTab === "docs") body = `<div class="grid g2" style="align-items:start">
      <div class="card"><div class="hd"><h3>Nummernkreise</h3></div><div class="bd fr">
        <div class="row">${f("next_nr","Nächste Rechnungsnummer")}${f("next_kdnr","Nächste Kundennummer")}</div>
        <div class="row">${f("next_angnr","Nächste Angebotsnummer")}${f("next_abnr","Nächste Auftragsnummer")}${f("next_projnr","Nächste Projektnummer")}</div>
        ${f("pdf_dir","Ordner für PDFs (Unterordner pro Jahr)")}${f("pdf_pattern","Dateiname Rechnungen","rechnung_{nr}.pdf")}</div></div>
      <div class="card"><div class="hd"><h3>Standardtexte</h3></div><div class="bd fr">
        ${ta("default_top","Rechnung – Kopftext",2)}${ta("default_foot","Rechnung – Fußtext",2)}
        ${ta("default_top_angebot","Angebot – Kopftext",2)}${ta("default_foot_angebot","Angebot – Fußtext ([Gültig] = Gültigkeitsdatum)",2)}
        <div class="row">${f("angebot_gueltig","Angebote gültig (Tage)","","number")}</div>
        ${ta("default_top_auftrag","Auftragsbestätigung – Kopftext",2)}${ta("default_foot_auftrag","Auftragsbestätigung – Fußtext",2)}</div></div></div>`;
  if (setTab === "mail") body = `<div class="grid g2" style="align-items:start">
      <div class="card"><div class="hd"><h3>Mailserver (Versand)</h3><div class="act">${(s.smtp_auth==="ms"?S.ms_verbunden:S.smtp_set)?`<span class="badge ok"><span class="dot"></span>${s.smtp_auth==="ms"?"Microsoft verbunden":"Passwort gespeichert"}</span>`:`<span class="badge warn">nicht eingerichtet</span>`}</div></div><div class="bd fr">
        <label class="f">Anbieter (füllt Server und Port aus)<select class="in" id="mprov"><option value="">– wählen –</option>${(S.mail_providers||[]).map(p=>`<option value="${p.id}">${esc(p.label)}</option>`).join("")}</select></label>
        <div class="row">${f("smtp_host","SMTP-Server","smtp.gmail.com")}<div style="flex:.35">${f("smtp_port","Port","587","number")}</div>
          <label class="f" style="flex:.6">Verschlüsselung<select class="in" data-s="smtp_sec">${[["auto","automatisch"],["starttls","STARTTLS (587)"],["ssl","SSL/TLS (465)"],["none","keine"]].map(([k,l])=>`<option value="${k}" ${(s.smtp_sec||"auto")===k?"selected":""}>${l}</option>`).join("")}</select></label></div>
        ${f("smtp_user","Benutzer / Login (meist die E-Mail-Adresse)")}
        <label class="f">Anmeldung<select class="in" data-s="smtp_auth" id="mauth"><option value="pass" ${s.smtp_auth!=="ms"?"selected":""}>Passwort / App-Passwort</option><option value="ms" ${s.smtp_auth==="ms"?"selected":""}>Microsoft-Konto (OAuth2) – Outlook.com, Hotmail, Microsoft 365</option></select></label>
        <label class="f mpw">Passwort / App-Passwort<input class="in" type="password" data-s="smtp_pass_new" autocomplete="new-password" placeholder="${S.smtp_set?"•••••••• (gespeichert – nur zum Ändern eintragen)":"App-Passwort eintragen"}"></label>
        <div class="mms card" style="padding:10px;background:var(--panel2)"><div class="row">${f("ms_client_id","Anwendungs-ID (Client-ID) deiner App-Registrierung","xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")}<div style="flex:.45">${f("ms_tenant","Verzeichnis","common")}</div></div>
          <div class="row" style="align-items:center"><button class="btn sm pri" style="flex:none" id="msgo" type="button">Bei Microsoft anmelden</button><span class="small" id="msst">${S.ms_verbunden?`<span style="color:var(--ok)">✓ verbunden${s.ms_konto?" als "+esc(s.ms_konto):""}</span> <a href="#" id="msout">abmelden</a>`:`<span class="muted">nicht angemeldet</span>`}</span></div>
          <div class="small muted">Microsoft lässt Mailprogramme nur noch mit dieser Anmeldung zu. Einmalig im Azure-Portal eine kostenlose App-Registrierung anlegen und die ID hier eintragen – Schritt für Schritt im Handbuch, Kapitel 13.</div></div>
        <div class="row">${f("smtp_from","Absendername")}${f("smtp_from_addr","Absender-Adresse (leer = wie Login)")}</div>
        <label class="chk"><input type="checkbox" data-s="mail_bcc_self" ${s.mail_bcc_self?"checked":""}> Kopie (BCC) an mich selbst</label>
        <label class="chk"><input type="checkbox" data-s="smtp_noverify" ${s.smtp_noverify?"checked":""}> Zertifikat des Servers nicht prüfen (nur für eigenen Server mit selbst ausgestelltem Zertifikat)</label>
        <div class="hl small" id="mhint" style="display:none"></div>
        <div class="small muted">Das Passwort wird mit Windows-Verschlüsselung (DPAPI) gespeichert.</div>
        <div class="row" style="align-items:center"><button class="btn" style="flex:none" id="mtest">${ic("mail")} Test-Mail an mich</button><span class="small muted">testet die Werte im Formular – auch ohne Speichern</span></div>
        <div id="mres"></div>
        ${s.mail_status&&s.mail_status.zeit?`<div class="small muted" id="mstat">Letzter Versand: ${dde(s.mail_status.zeit.slice(0,10))} ${s.mail_status.zeit.slice(11,16)} – ${s.mail_status.ok?"OK":`<span style="color:var(--bad)">${esc(s.mail_status.fehler||"Fehler")}</span>`}</div>`:""}</div></div>
      <div class="card"><div class="hd"><h3>Vorlage</h3></div><div class="bd fr">${f("mail_subject","Betreff")}${ta("mail_body","Text",8)}
        <div class="small muted">Platzhalter: [Dokument] [Nummer] [Betrag] [Name]</div></div></div></div>`;
  if (setTab === "mahn") body = `<div class="card"><div class="hd"><h3>Mahnstufen</h3></div><div class="bd fr">
      <div class="row">${f("mahn_frist","Neue Frist (Tage)","","number")}</div>
      ${["Zahlungserinnerung","1. Mahnung","2. Mahnung","Letzte Mahnung"].map((l,k)=>`<div class="row" style="align-items:flex-start"><label class="f" style="flex:none;width:150px">${l} – Gebühr €<input class="in num" data-mg="${k}" value="${nde((s.mahn_gebuehr||[])[k]||0)}"></label><label class="f">Text<textarea class="in" data-mt="${k}" rows="2">${esc((s.mahn_text||[])[k]||"")}</textarea></label></div>`).join("")}
      <div class="small muted">Platzhalter: [Mahnfrist]. Mahngebühren sind nur bei Verzug zulässig (Erinnerung ohne Gebühr).</div></div></div>`;
  if (setTab === "proj") body = `<div class="grid g2" style="align-items:start">
      <div class="card"><div class="hd"><h3>Kalkulation</h3></div><div class="bd fr">
        <div class="row">${f("stundensatz","Stundensatz für Timer (€)","","number")}${f("aufschlag","Material-Aufschlag (%)","","number")}${f("km_dienst","km-Satz Dienstfahrt (€)","","number")}</div>
        <label class="f">Materialpreise €/kg (eine Zeile: Material = Preis)<textarea class="in" id="matp" rows="6" style="font-family:Consolas,monospace">${esc(Object.entries(s.materialpreise||{}).map(([k,v])=>k+" = "+nde(v)).join("\n"))}</textarea></label></div></div>
      <div class="card"><div class="hd"><h3>Projekt-Strukturvorlagen</h3><div class="act"><button class="btn sm" id="tplnew">${ic("plus")} Neue Vorlage</button></div></div><div class="bd">
        ${S.templates.map(t=>`<div class="row" style="align-items:center;padding:7px 0;border-bottom:1px solid var(--line)"><span class="badge" style="flex:none;background:${BEREICH_COL[t.bereich]||"#888"}1c;color:${BEREICH_COL[t.bereich]||"#888"}">${esc(t.bereich)}</span><b>${esc(t.name)}</b><span class="small muted" style="flex:none">${JSON.parse(t.folders).length} Ordner</span><button class="btn sm ghost" style="flex:none" data-tpl="${t.id}">Bearbeiten</button></div>`).join("")}</div></div></div>`;
  if (setTab === "assist") body = `<div class="grid g2" style="align-items:start">
      <div class="card"><div class="hd"><h3>Beleg-Assistent</h3></div><div class="bd fr">
        <div class="small">Der Assistent ordnet jeden Beleg ein (Eingangsrechnung, Ausgangsrechnung, Gehalt, Gutschrift, Anlage) und schlägt die EÜR-Kategorie vor. Er kombiniert feste Regeln, sein Gedächtnis (jede Übernahme und Korrektur wird gelernt) und optional eine lokale KI.</div>
        <label class="chk"><input type="checkbox" data-s="auto_eingang" ${s.auto_eingang?"checked":""}> Eingangsordner überwachen (alle 20 Sekunden)</label>
        ${f("eingang_dir","Eingangsordner", S.data_dir + "\\Eingang")}
        <label class="f">Automatisch buchen ab Sicherheit (%)<input class="in num" type="number" min="50" max="100" data-s="auto_schwelle_pct" value="${Math.round((s.auto_schwelle||0.9)*100)}"></label>
        <div class="small muted">Belege über dieser Schwelle <b>und ohne Warnung</b> bucht der Assistent selbst (Protokoll auf der Belege-Seite). Alles andere – auch jede eigene Ausgangsrechnung – landet unter „Erkannt – bitte prüfen“. Tipp: Scanner oder Mail-Anhänge direkt in den Eingangsordner speichern lassen.</div>
        <div class="row"><button class="btn" style="flex:none" id="artrain2">Aus vorhandenen Belegen neu trainieren</button><button class="btn danger" style="flex:none" id="areset">Gedächtnis löschen</button></div>
        <hr class="s"><div class="small"><b>Gespeicherte Datei-Passwörter:</b> ${S.pw_count||0} – werden bei verschlüsselten Belegen automatisch ausprobiert (verschlüsselt gespeichert mit Windows-DPAPI).</div>
        <div><button class="btn sm" id="pwclr" ${S.pw_count?"":"disabled"}>Gespeicherte Passwörter löschen</button></div>
        <label class="f">Standard-Passwort – wird bei jeder verschlüsselten Datei (PDF, Excel, Word, ZIP) automatisch zuerst probiert<input class="in" data-s="std_pw" value="${esc(s.std_pw||"")}" autocomplete="off" style="font-family:Consolas,monospace"></label>
        <div class="small muted">Passt es, fragt das Programm nicht nach. Beim Öffnen und in der Vorschau werden solche PDFs automatisch entsperrt angezeigt – das Original im Datenordner bleibt verschlüsselt.</div></div></div>
      <div class="card"><div class="hd"><h3>Dr. Jey – lokale KI (optional)</h3></div><div class="bd fr">
        <div class="small">Für schwierige Belege kann der Assistent eine KI auf deinem Rechner fragen (<b>Ollama</b>, kostenlos, offline – deine Belege verlassen den PC nicht). Ollama installieren, z. B. <span style="font-family:Consolas,monospace">ollama pull qwen2.5:7b</span>, dann hier einschalten.</div>
        <label class="chk"><input type="checkbox" data-s="ki_enabled" ${s.ki_enabled?"checked":""}> Lokale KI verwenden</label>
        <label class="chk"><input type="checkbox" data-s="ki_immer" ${s.ki_immer?"checked":""}> Bei jedem Beleg fragen (sonst nur, wenn Regeln und Gedächtnis unsicher sind)</label>
        <div class="row">${f("ki_url","Adresse","http://127.0.0.1:11434")}${f("ki_model","Modell (leer = automatisch)","qwen2.5:7b")}</div>
        ${f("ki_timeout","Zeitlimit (Sekunden)","45","number")}
        <div class="row" style="align-items:center"><button class="btn" style="flex:none" id="kitest">Verbindung testen</button><span class="small muted" id="kires"></span></div></div></div></div>`;
  if (setTab === "daten") body = `<div class="grid g2" style="align-items:start">
      <div class="card"><div class="hd"><h3>Daten & Sicherung</h3></div><div class="bd fr">
        <div class="small muted">Datenordner: <b>${esc(S.data_dir)}</b></div>
        ${f("backup_target","Zusätzliches Backup-Ziel (NAS / OneDrive-Ordner)","z. B. \\\\NAS\\Backup\\Rechnung oder C:\\Users\\…\\OneDrive\\Backup")}
        <div class="row" style="flex-wrap:wrap"><button class="btn" style="flex:none" id="dopen">${ic("folder")} Datenordner öffnen</button><button class="btn" style="flex:none" id="dbak">${ic("save")} Komplett-Backup jetzt</button><button class="btn" style="flex:none" id="dvdt">Import aus „Rechnung 10“</button></div>
        <div class="small muted">Täglich automatische Sicherung der Datenbank (30 Stück), zusätzlich ins Backup-Ziel, wenn eingetragen.</div></div></div>
      <div class="card"><div class="hd"><h3>Daten-Paket</h3></div><div class="bd fr">
        <div class="small">Alle Daten mit Belegen als <b>eine ZIP-Datei</b> – zum Umziehen auf einen anderen PC, als Archiv oder zum Einspielen vorbereiteter Daten (z. B. ganze Jahre). Beim Einspielen wird <b>nichts überschrieben</b>: vorhandene Rechnungen, Belege und Buchungen werden erkannt und übersprungen.</div>
        <div class="row" style="flex-wrap:wrap"><button class="btn" style="flex:none" id="pexp">${ic("save")} Daten-Paket exportieren</button><button class="btn pri" style="flex:none" id="pimp">${ic("up")} Daten-Paket einspielen</button></div>
        <div class="small muted" id="pres"></div></div></div>
      <div class="card"><div class="hd"><h3>Export</h3></div><div class="bd fr">
        <div class="small">Alles auf einmal: Rechnungen, Positionen, Kunden, Bausteine, Projekte, Belege, Bank und Kontostände, Fahrten, Nachweise, Steuerakte, Abos, EÜR je Jahr und Anlagen – als <b>eine Excel-Datei</b> (ein Blatt je Bereich) oder als <b>ein PDF</b>.</div>
        <div class="row" style="flex-wrap:wrap">${expButtons("gesamt")}</div>
        <div class="small muted">Jede Liste im Programm hat außerdem oben eigene Excel/PDF-Knöpfe, und markierte Einträge lassen sich über die Aktionsleiste exportieren. Dateien landen im Datenordner unter <b>Export</b>.</div></div></div>
      <div class="card"><div class="hd"><h3>Programm-Update</h3></div><div class="bd fr" id="updbox"><div class="small muted">lädt …</div></div></div></div>`;
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Einstellungen", "", `<button class="btn pri" id="ssave">${ic("save")} Speichern</button>`)}
    <div class="tabs">${tabs.map(([k,l])=>`<div class="tab ${setTab===k?"on":""}" data-tab="${k}">${l}</div>`).join("")}</div>${body}</div>`;
  $$(".tab[data-tab]").forEach(t => t.onclick = () => { if (t.dataset.tab === setTab) return; pageLeave(); setTab = t.dataset.tab; vSettings(); setTimeout(pageRestore, 0); });
  $("#ssave").onclick = async () => { const d = {};
    $$("[data-s]").forEach(e => d[e.dataset.s] = e.type==="checkbox" ? e.checked : e.type==="number" ? pnum(e.value) : e.value);
    if ("auto_schwelle_pct" in d) { d.auto_schwelle = Math.min(1, Math.max(0.5, (d.auto_schwelle_pct||90)/100)); delete d.auto_schwelle_pct; }
    if ($("[data-mg]")) { d.mahn_gebuehr = $$("[data-mg]").map(e=>pnum(e.value)); d.mahn_text = $$("[data-mt]").map(e=>e.value); }
    if ($("#matp")) { const mp = {}; $("#matp").value.split("\n").forEach(l => { const m = l.split("="); if (m.length===2 && m[0].trim()) mp[m[0].trim()] = pnum(m[1]); }); d.materialpreise = mp; }
    await api("/api/settings/save", d); await reload(); toast("Einstellungen gespeichert"); vSettings(); };
  const on = (id, fn) => { const e = $("#"+id); if (e) e.onclick = fn; };
  on("logo", () => pickFiles("image/*", async fs => { await upload("/api/upload/logo", fs[0]); await reload(); vSettings(); toast("Logo aktualisiert"); }));
  on("dopen", () => api("/api/open", {path:S.data_dir, folder:true}));
  on("pwclr", async () => { if (!await confirmBox("Alle gespeicherten Datei-Passwörter löschen?", "Löschen")) return; await api("/api/beleg/pwclear", {}); await reload(); vSettings(); toast("Passwörter gelöscht"); });
  on("artrain2", async () => { const r = await api("/api/assist/retrain", {}); toast(`Trainiert: ${r.status.gelernt} Belege im Gedächtnis`); });
  on("areset", async () => { if (!await confirmBox("Alles Gelernte löschen und nur aus den vorhandenen Belegen neu lernen?", "Löschen")) return; const r = await api("/api/assist/retrain", {reset:true}); toast(`Neu aufgebaut: ${r.status.gelernt} Belege`); });
  on("kitest", async () => { const d = {}; $$("[data-s^=ki_]").forEach(e => d[e.dataset.s] = e.type==="checkbox" ? e.checked : e.value); $("#kires").textContent = "teste …";
    const r = await api("/api/assist/kitest", d); $("#kires").innerHTML = r.ok ? `<span style="color:var(--ok)">✓ ${esc(r.model)} antwortet: ${esc(TYPES[r.antwort.typ]||r.antwort.typ||"?")}</span>` : `<span style="color:var(--bad)">${esc(r.error)}</span>`; });
  on("dbak", async () => { const r = await api("/api/backup", {}); if (r.ok) toast(r.warn ? r.warn : "Backup erstellt" + (S.settings.backup_target ? " (auch im Backup-Ziel)" : ""), !!r.warn); });
  on("dvdt", () => pickFiles(".vdt", async fs => { const r = await upload("/api/upload/vdt", fs[0]); await reload(); toast(`Importiert: ${r.articles} Bausteine, ${r.customers} Kunden`); }));
  on("mtest", () => window.mailTest && mailTest());
  on("pexp", async () => { toast("Daten-Paket wird erstellt …"); const r = await api("/api/paket/export", {}); if (r.ok) { $("#pres").textContent = "Gespeichert: " + r.path + " (" + nde(r.size/1048576,1) + " MB)"; toast("Daten-Paket gespeichert"); } });
  on("pimp", () => pickFiles(".zip", async fs => { if (!await confirmBox(`„${fs[0].name}“ einspielen? Vorhandene Daten bleiben erhalten, doppelte Einträge werden übersprungen.`, "Einspielen")) return;
    $("#pres").textContent = "Wird eingespielt … (große Pakete brauchen etwas)"; const r = await upload("/api/upload/paket", fs[0]);
    if (r.ok === false) { toast(r.error, true); $("#pres").textContent = r.error; return; }
    const x = r.result; $("#pres").innerHTML = `Eingespielt: <b>${x.rechnungen}</b> Rechnungen (${x.rechnungen_aktualisiert} aktualisiert), <b>${x.belege}</b> Belege, <b>${x.bank}</b> Bankbuchungen, <b>${x.kontostand}</b> Kontostände, <b>${x.steuerakte}</b> Steuerunterlagen, ${x.kunden} Kunden, ${x.projekte} Projekte (${x.projektdateien} Dateien) · ${x.uebersprungen} schon vorhanden`;
    if (x.konflikte && x.konflikte.length) $("#pres").innerHTML += `<div class="warn" style="margin-top:6px"><b>Nicht übernommen / umbenannt (${x.konflikte.length}):</b><br>${x.konflikte.slice(0, 30).map(esc).join("<br>")}</div>`;
    await reload(); toast("Daten-Paket eingespielt"); }));
  if (setTab === "daten") renderUpdBox();
  { const t = EXT.settings.find(t=>t.key===setTab); if (t) { const el = document.createElement("div"); $("#main .page").appendChild(el); try { t.render(el); } catch (e) { console.error(e); } } }
  const editTpl = async t => {
    const r = await modal(t.id?"Vorlage bearbeiten":"Neue Vorlage", `<div class="fr"><div class="row"><label class="f">Name<input class="in" id="tn" value="${esc(t.name||"")}"></label><label class="f" style="flex:.6">Bereich<select class="in" id="tb">${Object.keys(BEREICH_COL).map(b=>`<option ${b===t.bereich?"selected":""}>${b}</option>`).join("")}</select></label></div>
      <label class="f">Ordner (eine Zeile pro Ordner, Unterordner mit /)<textarea class="in" id="tf" rows="12" style="font-family:Consolas,monospace;font-size:12.5px">${esc(JSON.parse(t.folders||"[]").join("\n"))}</textarea></label></div>`,
      [...(t.id?[{label:"Löschen", cls:"danger", onClick: async () => { await api("/api/template/delete", {id:t.id}); }, value:1}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:1, onClick: async mb => {
        await api("/api/template/save", {id:t.id, name:$("#tn",mb).value, bereich:$("#tb",mb).value, folders:$("#tf",mb).value.split("\n").map(s=>s.trim()).filter(Boolean)}); }}]);
    if (r) { await reload(); vSettings(); }
  };
  $$("[data-tpl]").forEach(b => b.onclick = () => editTpl(S.templates.find(t=>t.id==b.dataset.tpl)));
  on("tplnew", () => editTpl({name:"", bereich:"AV", folders:"[]"}));
}

