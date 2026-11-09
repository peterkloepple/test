// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m78_inventor: Inventor-Stueckliste je Projekt
// Reiter "Stückliste" auf der Projektseite: Datei verknuepfen/ueberwachen, Aenderungen, Lagerabgleich,
// Reservieren/Entnehmen, Bestellliste nach Lieferant, Zuschnittliste mit Stabaufteilung. Hinweis auf der Uebersicht.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m78bom = '<path d="M4 4h16v16H4z"/><path d="M4 9h16M4 14h16M9 4v16"/>';
  const TABS = window.m76Tabs = window.m76Tabs || [];
  TABS.push({key: "m78", label: "Stückliste", render: (T, id) => m78Tab(T, id)});

  const STB = {ok: ["ok", "im Lager"], teilweise: ["warn", "teilweise"], fehlt: ["bad", "fehlt"], ohne: ["", "nicht zugeordnet"],
               entnommen: ["acc", "entnommen"], kein_lager: ["", "–"]};
  const badge = s => { const b = STB[s] || ["", s]; return `<span class="badge ${b[0]}"><span class="dot"></span>${b[1]}</span>`; };
  const n3 = v => { v = Number(v) || 0; return nde(v, Math.abs(v % 1) > 1e-9 ? (Math.abs((v * 100) % 1) > 1e-9 ? 3 : 2) : 0); };

  EXT.dash.push(el => {
    const m = S.m78; if (!m || !m.geaendert) return;
    const d = document.createElement("div"); d.className = "alert"; d.style.marginBottom = "10px";
    const f = m.liste[0] || {};
    d.innerHTML = `${ic("m78bom")}<b>${m.geaendert} Stückliste(n) aus Inventor geändert</b><span class="small">${m.liste.map(r => esc((r.nr || "") + " " + (r.name || ""))).join(" · ")}</span><span class="sp" style="flex:1"></span><span class="small"><u>Ansehen →</u></span>`;
    d.onclick = () => { pTab = "m78"; go("project", f.project_id); };
    el.appendChild(d);
  });

  // ---------------------------------------------------------------- link dialogs
  async function linkPath(pid, after){
    const r = await api("/api/pick", {accept: ".xlsx,.xlsm,.xls,.csv,.txt", multiple: false}, {quiet: true});
    if (r && r.native !== false) {
      if (!r.ok || !r.files || !r.files.length) return;
      const res = await api("/api/m78/link", {project_id: pid, path: r.files[0].path});
      if (res && res.ok) { toast(`Stückliste verknüpft – ${res.zeilen || 0} Positionen, wird überwacht`); after(); }
      return;
    }
    // browser without native dialog: upload into the project instead
    linkUpload(pid, after);
  }
  function linkUpload(pid, after){
    pickFiles(".xlsx,.xlsm,.xls,.csv,.txt", async files => {
      const res = await upload("/api/upload/m78", files[0], {"X-M78-Project": String(pid)});
      if (res && res.ok) { toast(`Stückliste übernommen – ${res.zeilen || 0} Positionen`); after(); } else toast((res && res.error) || "Fehler", true);
    }, false);
  }
  async function linkProjectFile(pid, files, after){
    if (!files.length) { toast("Im Projekt liegt keine Excel-/CSV-Datei.", true); return; }
    await modal("Stückliste aus Projektdateien", `<div class="fr"><label class="f">Datei<select class="in" id="m78pf">${files.map(f => `<option value="${f.id}">${esc(f.name)}</option>`).join("")}</select></label>
      <div class="small muted">Die Datei im Projektordner wird überwacht – wird sie dort ersetzt, liest das Programm sie neu ein.</div></div>`,
      [{label: "Abbrechen"}, {label: "Verknüpfen", cls: "pri", onClick: async mb => {
        const res = await api("/api/m78/link", {project_id: pid, file_id: +$("#m78pf", mb).value});
        if (!res || !res.ok) return false; toast(`Stückliste verknüpft – ${res.zeilen || 0} Positionen`); after(); }}]);
  }

  // ---------------------------------------------------------------- order mail / cut list
  async function mailDlg(b){
    const r = await api("/api/m78/mail", {bom_id: b.id}); if (!r || !r.ok) return;
    if (!r.mails.length) { toast("Es fehlt kein Material – keine Bestellung nötig."); return; }
    const html = r.mails.map((m, i) => `<div class="card" style="margin-bottom:10px"><div class="hd"><h3>${esc(m.lieferant)}</h3><div class="act">
        <button class="btn sm" data-m78cp="${i}">In Zwischenablage</button><a class="btn sm" href="mailto:?subject=${encodeURIComponent(m.betreff)}&body=${encodeURIComponent(m.text)}">Mail öffnen</a></div></div>
      <div class="bd"><textarea class="in" rows="9" data-m78tx="${i}" style="width:100%;font:12px/1.4 var(--mono,monospace)">${esc(m.text)}</textarea></div></div>`).join("");
    await modal("Bestellung per Mail", html, [{label: "Schließen"}], true, mb => {
      $$("[data-m78cp]", mb).forEach(bt => bt.onclick = async () => { const t = $(`[data-m78tx="${bt.dataset.m78cp}"]`, mb).value;
        try { await navigator.clipboard.writeText(t); toast("Text kopiert"); } catch (e) { const ta = $(`[data-m78tx="${bt.dataset.m78cp}"]`, mb); ta.select(); document.execCommand("copy"); toast("Text kopiert"); } });
    });
  }

  async function cutDlg(b, sets){
    let stab = sets.stablaenge, fuge = sets.schnittfuge;
    const body = d => d.profile.length ? d.profile.map(p => `<div class="card" style="margin-bottom:10px"><div class="hd"><h3>${esc(p.profil)}${p.material ? ` · <span class="muted">${esc(p.material)}</span>` : ""}</h3>
        <div class="act small">${p.stueck} Teile · ${nde(p.gesamt_m, 2)} m · <b>${p.staebe} Stäbe</b>${p.reststuecke ? ` + ${p.reststuecke} Reststück(e)` : ""} · Verschnitt ${nde(p.verschnitt_pct, 1)} % · Rest ${nde(p.rest_m, 2)} m</div></div>
      <div class="bd"><div class="small muted" style="margin-bottom:6px">Minimum rechnerisch ${p.min_staebe} Stab/Stäbe – ${p.optimal ? "<b>Aufteilung optimal</b>" : "beste gefundene Aufteilung (Rechenzeit begrenzt)"}</div>
        ${p.plan.map((s, i) => `<div style="display:flex;align-items:center;gap:8px;margin:3px 0"><span class="small ${s.reststueck ? "" : "muted"}" style="width:62px" title="${s.reststueck ? "Reststück aus dem Lager" : ""}">${s.reststueck ? "R " + nde(s.laenge, 0) : "Stab " + (i + 1 - (p.reststuecke || 0))}</span>
        <div style="flex:0 0 auto;width:calc((100% - 140px) * ${(s.laenge || d.stablaenge) / Math.max(d.stablaenge, ...p.plan.map(x => x.laenge || 0))});display:flex;height:20px;border:1px solid var(--line,#ccc);border-radius:4px;overflow:hidden;background:repeating-linear-gradient(45deg,transparent,transparent 4px,rgba(0,0,0,.06) 4px,rgba(0,0,0,.06) 8px)">
        ${s.teile.map(t => `<div title="${esc(t.pos)} ${nde(t.laenge, 0)} mm" style="width:${100 * t.laenge / (s.laenge || d.stablaenge)}%;background:var(--acc,#6a48e0);color:#fff;font-size:10px;line-height:20px;text-align:center;border-right:2px solid #fff;overflow:hidden;white-space:nowrap">${nde(t.laenge, 0)}</div>`).join("")}</div>
        <span class="small num" style="width:70px;text-align:right;margin-left:auto">Rest ${nde(s.rest, 0)}</span></div>`).join("")}
        <div class="row" style="align-items:flex-end;margin-top:8px"><label class="f small" style="flex:1;margin:0">Reststücke im Lager für dieses Profil (mm, mit ; oder Leerzeichen getrennt) – werden zuerst verplant
          <input class="in" data-m78rs="${esc(p.profil)}" value="${(p.reste_lager || []).map(v => nde(v, 0).replace(/\./g, "")).join("; ")}" placeholder="z. B. 1200; 850"></label>
          <button class="btn sm" type="button" data-m78rb="${esc(p.profil)}">Reststücke speichern</button></div>
        ${p.ueberlaenge.length ? `<div class="alert warn" style="cursor:default;margin-top:6px;font-size:12px">${ic("alert")}<span>Überlänge: ${p.ueberlaenge.map(u => nde(u.laenge, 0) + " mm").join(", ")} – länger als ein Stab</span></div>` : ""}</div></div>`).join("")
      : `<div class="empty">Die Stückliste enthält keine Längen-Spalte („Länge“). In Inventor die Spalte Länge (z. B. G_L) in den Stücklisten-Export aufnehmen.</div>`;
    const load = async () => api(`/api/m78/zuschnitt?bom_id=${b.id}&stab=${encodeURIComponent(stab)}&fuge=${encodeURIComponent(fuge)}`);
    let d = await load(); if (!d || !d.profile) return;
    const html = `<div class="row" style="align-items:flex-end;margin-bottom:10px"><label class="f" style="flex:0 0 150px">Stablänge mm<input class="in num" id="m78st" value="${nde(stab, 0)}"></label>
      <label class="f" style="flex:0 0 150px">Schnittfuge mm<input class="in num" id="m78sf" value="${nde(fuge, 1)}"></label><button class="btn sm" id="m78sr" type="button">Neu rechnen</button>
      <label class="chk small" style="flex:none"><input type="checkbox" id="m78sd"> als Standard speichern</label><span style="flex:1"></span>
      <button class="btn sm" id="m78sp" type="button">${ic("pdf")} PDF</button><button class="btn sm" id="m78sx" type="button">Excel</button></div><div id="m78sb">${body(d)}</div>`;
    await modal(`Zuschnittliste – ${b.name}`, html, [{label: "Schließen"}], true, mb => {
      $("#m78sr", mb).onclick = async () => { stab = pnum($("#m78st", mb).value); fuge = pnum($("#m78sf", mb).value);
        if ($("#m78sd", mb).checked) { const r = await api("/api/m78/settings", {stablaenge: stab, schnittfuge: fuge}); if (r && r.ok) { sets.stablaenge = stab; sets.schnittfuge = fuge; toast("Standard gespeichert"); } }
        d = await load(); if (d && d.profile) { $("#m78sb", mb).innerHTML = body(d); bindRest(); } };
      const bindRest = () => $$("[data-m78rb]", mb).forEach(bt => bt.onclick = async () => {
        const inp = $$("[data-m78rs]", mb).find(x => x.dataset.m78rs === bt.dataset.m78rb);
        const r = await api("/api/m78/reste", {profil: bt.dataset.m78rb, reste: inp ? inp.value : ""});
        if (r && r.ok) { toast(r.reste.length ? r.reste.length + " Reststück(e) gespeichert" : "Reststücke entfernt"); d = await load(); if (d && d.profile) { $("#m78sb", mb).innerHTML = body(d); bindRest(); } } });
      bindRest();
      $("#m78sp", mb).onclick = async () => { const r = await api("/api/m78/pdf", {bom_id: b.id, was: "zuschnitt"}); if (r && r.ok) toast(r.name + " im Projekt abgelegt"); };
      $("#m78sx", mb).onclick = () => doExport("m78_zuschnitt", "xlsx", {bom_id: b.id});
    });
  }

  async function mapDlg(b, row, arts, after){
    const html = `<div class="fr"><div class="small muted" style="margin-bottom:6px">Position <b>${esc(row.pos || "")} ${esc(row.nr || "")}</b> ${esc(row.name)} einem Lagerartikel zuordnen. Die Zuordnung wird gemerkt und gilt künftig für alle Stücklisten.</div>
      <label class="f">Lagerartikel<select class="in" id="m78ma"><option value="">– keine Zuordnung –</option>${arts.map(a => `<option value="${a.id}" ${row.artikel && row.artikel.id === a.id ? "selected" : ""}>${esc((a.nr ? a.nr + " · " : "") + a.name)} (${n3(a.bestand)} ${esc(a.einheit || "")})</option>`).join("")}</select></label></div>`;
    await modal("Lagerartikel zuordnen", html, [{label: "Abbrechen"}, {label: "Zuordnen", cls: "pri", onClick: async mb => {
      const r = await api("/api/m78/map", {key: row.key, artikel_id: $("#m78ma", mb).value || null}); if (!r || !r.ok) return false; toast("Zuordnung gespeichert"); after(); }}]);
  }

  // ---------------------------------------------------------------- project tab
  async function m78Tab(T, pid){
    const d = await api("/api/m78/project?project_id=" + pid);
    if (!d || !d.boms) { T.innerHTML = `<div class="card empty">Nicht verfügbar.</div>`; return; }
    const re = () => m78Tab(T, pid);
    const head = `<div class="row" style="margin-bottom:12px;flex-wrap:wrap;gap:6px"><span class="small muted" style="flex:1;min-width:240px">Stückliste aus Inventor als Excel/CSV exportieren und hier verknüpfen. Ändert sich die Datei, wird sie automatisch neu eingelesen.</span>
      <button class="btn pri" id="m78lp">${ic("m78bom")} Datei verknüpfen (überwachen)</button><button class="btn" id="m78lf">Aus Projektdateien</button><button class="btn ghost" id="m78lu">${ic("up")} Hochladen</button></div>`;
    T.innerHTML = head + (d.boms.map(b => {
      const s = b.summe, chg = b.changes.filter(c => !c.gesehen);
      return `<div class="card" style="margin-bottom:14px;overflow:hidden" data-m78b="${b.id}"><div class="hd"><h3>${ic("m78bom")} ${esc(b.name)}</h3><div class="act">
          <label class="chk small" style="flex:none" title="Datei alle 60 s auf Änderungen prüfen"><input type="checkbox" data-m78auto="${b.id}" ${b.auto ? "checked" : ""}> überwachen</label>
          <button class="btn sm" data-m78rl="${b.id}" title="Datei jetzt neu einlesen">${ic("sync")} Neu einlesen</button>
          <button class="btn sm ghost" data-m78of="${esc(b.path)}" title="Datei öffnen">Öffnen</button><button class="btn sm ghost" data-m78rm="${b.id}" title="Verknüpfung entfernen">✕</button></div></div>
        <div class="bd" style="padding-bottom:6px"><div class="small muted" style="word-break:break-all">${esc(b.path)} · gelesen ${esc((b.gelesen || "").slice(0, 16).replace("T", " "))}${b.extern ? " · Datei außerhalb des Projektordners" : ""}</div>
          ${!b.vorhanden ? `<div class="alert bad" style="cursor:default;margin-top:6px">${ic("alert")}<span>Datei nicht gefunden – verschoben oder umbenannt?</span></div>` : b.fehler ? `<div class="alert warn" style="cursor:default;margin-top:6px">${ic("alert")}<span>${esc(b.fehler)}</span></div>` : ""}
          ${chg.length ? `<div class="alert" style="cursor:default;margin-top:8px;display:block"><div style="display:flex;gap:8px;align-items:center">${ic("alert")}<b>Stückliste geändert</b><span class="small">${chg.map(c => `${esc(c.zeit.slice(0, 16).replace("T", " "))}: ${c.neu} neu, ${c.geaendert} geändert, ${c.entfernt} entfernt`).join(" · ")}</span><span style="flex:1"></span><button class="btn sm" data-m78seen="${b.id}">Gesehen</button></div>
            <div class="small" style="margin-top:6px">${chg.slice(0, 2).map(c => [...(c.details.neu || []).map(r => `<div><span class="badge ok">neu</span> ${esc(r.name)} (${n3(r.qty)})</div>`),
              ...(c.details.geaendert || []).map(r => `<div><span class="badge warn">geändert</span> ${esc(r.name)}: ${esc(r.was)}</div>`),
              ...(c.details.entfernt || []).map(r => `<div><span class="badge bad">entfernt</span> ${esc(r.name)}</div>`)].join("")).join("")}</div></div>` : ""}
          <div class="row" style="margin-top:10px;flex-wrap:wrap;gap:6px;align-items:flex-end">
            <label class="f" style="flex:0 0 260px">Kalkulation automatisch aktualisieren<select class="in" data-m78k="${b.id}"><option value="">– keine –</option>${d.kalks.map(k => `<option value="${k.id}" ${k.id === b.kalk_id ? "selected" : ""}>${esc(k.name)} (${eur(k.angebotspreis)})</option>`).join("")}<option value="neu">+ neue Kalkulation anlegen</option></select></label>
            <span style="flex:1"></span>
            ${b.lager ? `<span class="small">${s.ok} im Lager · ${s.teilweise} teilweise · ${s.fehlt} fehlen · ${s.ohne} ohne Zuordnung · ${s.entnommen} entnommen</span>` : `<span class="small muted">Lager nicht eingerichtet</span>`}</div>
          <div class="row" style="margin-top:8px;gap:6px;flex-wrap:wrap">${b.lager ? `<button class="btn sm" data-m78res="${b.id}" title="Verfügbaren Bestand für diese Stückliste vormerken">Alles reservieren</button><button class="btn sm" data-m78ent="${b.id}" title="Verfügbares Material buchen und als Projekt-Material eintragen">Verfügbares entnehmen</button>` : ""}
            <span style="flex:1"></span><button class="btn sm" data-m78bp="${b.id}">${ic("pdf")} Bestellliste</button><button class="btn sm" data-m78bx="${b.id}">Bestellliste Excel</button><button class="btn sm" data-m78bm="${b.id}">Bestell-Mail</button>
            <button class="btn sm ${b.hat_laenge ? "pri" : ""}" data-m78z="${b.id}">Zuschnittliste</button></div></div>
        <table class="t" data-m78t="${b.id}"><thead><tr><th>Pos.</th><th>Nr.</th><th>Benennung</th><th>Material</th><th class="r">Länge</th><th class="r">Menge</th><th>Lagerartikel</th><th class="r">Bedarf</th><th class="r">verfügbar</th><th class="r">reserv.</th><th>Status</th></tr></thead>
        <tbody>${b.rows.map(r => `<tr data-m78r="${esc(r.key)}" class="click"><td class="small">${esc(r.pos || "")}</td><td><b>${esc(r.nr || "")}</b></td><td>${esc(r.name)}${r.lieferant ? `<div class="small muted">${esc(r.lieferant)}</div>` : ""}</td><td class="small">${esc(r.material || "")}</td>
          <td class="r num">${r.laenge ? nde(r.laenge, 0) : ""}</td><td class="r num">${n3(r.qty)} ${esc(r.unit || "")}</td>
          <td class="small">${r.artikel ? `${esc((r.artikel.nr ? r.artikel.nr + " · " : "") + r.artikel.name)}${r.zuordnung ? ` <span class="muted">(${esc(r.zuordnung)})</span>` : ""}` : (b.lager ? `<span class="muted">zuordnen …</span>` : "")}</td>
          <td class="r num">${r.artikel ? n3(r.bedarf) + " " + esc(r.einheit || "") : ""}</td><td class="r num">${r.artikel ? n3(r.verfuegbar) : ""}</td><td class="r num">${r.reserviert ? n3(r.reserviert) : ""}</td>
          <td>${badge(r.status)}${r.fehlt > 0 && r.artikel ? `<div class="small muted">fehlt ${n3(r.fehlt)}</div>` : ""}</td></tr>`).join("") || `<tr><td colspan="11" class="empty">Keine Positionen gelesen.</td></tr>`}</tbody></table></div>`;
    }).join("") || `<div class="card empty">Noch keine Stückliste verknüpft.</div>`);
    bindCommon(T);
    $("#m78lp", T).onclick = () => linkPath(pid, re);
    $("#m78lf", T).onclick = () => linkProjectFile(pid, d.files, re);
    $("#m78lu", T).onclick = () => linkUpload(pid, re);
    const B = id => d.boms.find(b => b.id == id);
    $$("[data-m78auto]", T).forEach(c => c.onchange = async () => { await api("/api/m78/update", {id: +c.dataset.m78auto, auto: c.checked}); toast(c.checked ? "Überwachung an" : "Überwachung aus"); });
    $$("[data-m78rl]", T).forEach(bt => bt.onclick = async () => { const r = await api("/api/m78/reload", {id: +bt.dataset.m78rl}); if (r && r.ok) { toast(r.changed ? `Neu eingelesen: ${r.neu} neu, ${r.geaendert} geändert, ${r.entfernt} entfernt` : "Neu eingelesen – keine Änderungen"); re(); } });
    $$("[data-m78rm]", T).forEach(bt => bt.onclick = async () => { await api("/api/m78/unlink", {ids: [+bt.dataset.m78rm]}); toast("Verknüpfung entfernt (Datei bleibt erhalten)"); re(); });
    $$("[data-m78of]", T).forEach(bt => bt.onclick = () => api("/api/open", {path: bt.dataset.m78of}));
    $$("[data-m78seen]", T).forEach(bt => bt.onclick = async () => { await api("/api/m78/seen", {bom_id: +bt.dataset.m78seen}); await reload(); re(); });
    $$("[data-m78k]", T).forEach(sel => sel.onchange = async () => { const r = await api("/api/m78/update", {id: +sel.dataset.m78k, kalk_id: sel.value || null}); if (r && r.ok) { toast(sel.value ? "Kalkulation wird mit der Stückliste aktualisiert" : "Kalkulation entkoppelt"); re(); } });
    $$("[data-m78res]", T).forEach(bt => bt.onclick = async () => { const r = await api("/api/m78/reserve", {bom_id: +bt.dataset.m78res}); if (r && r.ok) { toast(`${r.n} Position(en) reserviert`); re(); } });
    $$("[data-m78ent]", T).forEach(bt => bt.onclick = async () => { const r = await api("/api/m78/entnahme", {bom_id: +bt.dataset.m78ent}); if (r && r.ok) { (r.warn || []).slice(0, 3).forEach(w => toast(w, true)); toast(`${r.n} Position(en) entnommen`); re(); } });
    $$("[data-m78bp]", T).forEach(bt => bt.onclick = async () => { const r = await api("/api/m78/pdf", {bom_id: +bt.dataset.m78bp, was: "bestell"}); if (r && r.ok) toast(r.name + " im Projekt abgelegt"); });
    $$("[data-m78bx]", T).forEach(bt => bt.onclick = () => doExport("m78_bestell", "xlsx", {bom_id: +bt.dataset.m78bx}));
    $$("[data-m78bm]", T).forEach(bt => bt.onclick = () => mailDlg(B(bt.dataset.m78bm)));
    $$("[data-m78z]", T).forEach(bt => bt.onclick = () => cutDlg(B(bt.dataset.m78z), d.settings));
    d.boms.forEach(b => {
      $$(`table[data-m78t="${b.id}"] tr[data-m78r]`, T).forEach(tr => tr.onclick = () => { if (!b.lager) return; mapDlg(b, b.rows.find(r => r.key === tr.dataset.m78r), d.artikel, re); });
      if (!b.lager) return;
      selectify({kind: "m78b" + b.id, rows: $$(`table[data-m78t="${b.id}"] tr[data-m78r]`, T), id: "data-m78r", rerender: re, actions: [
        {label: "Reservieren", run: async keys => { const r = await api("/api/m78/reserve", {bom_id: b.id, keys}); if (r && r.ok) toast(`${r.n} reserviert`); re(); }},
        {label: "Reservierung lösen", run: async keys => { await api("/api/m78/reserve", {bom_id: b.id, keys, weg: 1}); toast("Reservierung gelöst"); re(); }},
        {label: "Entnehmen", run: async keys => { const r = await api("/api/m78/entnahme", {bom_id: b.id, keys}); if (r && r.ok) { (r.warn || []).slice(0, 3).forEach(w => toast(w, true)); toast(`${r.n} entnommen`); } re(); }}]});
    });
  }
})();
