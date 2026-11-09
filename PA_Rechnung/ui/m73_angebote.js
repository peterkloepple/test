// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m73_angebote: Angebote nachfassen
// Seite "Angebote" (oben im Menue): Status, Wiedervorlage, Nachfass-Mail, Ablehnungsgrund, Auswertung je Bereich/Kunde.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m73 = '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 14l2 2 4-4"/>';
  const F = {status: "offen", year: "", q: "", tab: "liste"};
  const STB = {offen: ["warn", "offen"], angenommen: ["ok", "angenommen"], abgelehnt: ["", "abgelehnt"], abgelaufen: ["bad", "abgelaufen"]};
  const badge = st => `<span class="badge ${STB[st][0]}"><span class="dot"></span>${STB[st][1]}</span>`;

  EXT.nav.push({key: "m73ang", label: "Angebote", icon: "m73", section: "Top", cnt: () => (S.m73 && S.m73.faellig) ? "⏰ " + S.m73.faellig : ""});
  EXT.views.m73ang = view;

  const _sb = statusBadge;
  statusBadge = function(i){
    try { if (i.typ === "angebot" && i.status === "offen" && S.m73 && (S.m73.abgelaufen_ids || []).includes(i.id)) return badge("abgelaufen"); } catch (e) {}
    return _sb(i);
  };

  EXT.dash.push(el => {
    const m = S.m73; if (!m || !m.faellig) return;
    const d = document.createElement("div"); d.className = "alert"; d.style.marginBottom = "10px"; d.style.cursor = "pointer";
    d.innerHTML = `${ic("m73")}<b>${m.faellig} Angebot(e) nachfassen</b><span class="small">${m.due.slice(0, 4).map(r => esc(r.nr) + " " + esc(r.name) + " (" + eur(r.summe) + ")").join(" · ")}${m.due.length > 4 ? " …" : ""}</span><span class="sp" style="flex:1"></span><span class="small"><u>Angebote →</u></span>`;
    d.onclick = () => { F.status = "faellig"; go("m73ang"); };
    el.appendChild(d);
  });

  async function statusDialog(r, gruende, st){
    if (st !== "abgelehnt") { const x_ = await api("/api/m73/status", {id: r.id, status: st}); if (x_ && x_.ok) { toast("Status: " + STB[st][1]); await reload(); view(); } return; }
    await modal(`Angebot ${r.nr} abgelehnt`, `<div class="fr"><label class="f">Grund<select class="in" id="m73g">${gruende.map(g => `<option ${g === r.grund ? "selected" : ""}>${esc(g)}</option>`).join("")}</select></label>
      <label class="f">Notiz<input class="in" id="m73n" value="${esc(r.notiz || "")}" placeholder="z. B. Mitbewerber 10 % günstiger"></label></div>`,
      [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
        const x_ = await api("/api/m73/status", {id: r.id, status: "abgelehnt", grund: $("#m73g", mb).value, notiz: $("#m73n", mb).value});
        if (!x_ || !x_.ok) return false; await reload(); view(); }}]);
  }

  async function wvDialog(r){
    await modal(`Wiedervorlage ${r.nr}`, `<div class="fr"><div class="row"><label class="f">Wiedervorlage am<input type="date" class="in" id="m73w" value="${r.wiedervorlage || todayIso()}"></label></div>
      <div class="chips" style="margin-bottom:8px">${[3, 7, 14, 30].map(n => `<span class="chip" data-m73p="${n}">+${n} Tage</span>`).join("")}</div>
      <label class="f">Notiz<input class="in" id="m73wn" value="${esc(r.notiz || "")}"></label></div>`,
      [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
        const x_ = await api("/api/m73/wv", {id: r.id, datum: $("#m73w", mb).value, notiz: $("#m73wn", mb).value}); if (!x_ || !x_.ok) return false; await reload(); view(); }}], false,
      mb => $$("[data-m73p]", mb).forEach(c => c.onclick = () => { const d = new Date(); d.setDate(d.getDate() + +c.dataset.m73p); $("#m73w", mb).value = isoLocal(d); }));
  }

  async function mailDlg(r){
    const p = await api("/api/m73/mail?id=" + r.id); if (!p || !p.ok) return;
    if (!p.configured) toast("E-Mail ist noch nicht eingerichtet (Einstellungen → E-Mail).", true);
    await modal(`Nachfassen: Angebot ${r.nr}`, `<div class="fr"><label class="f">An<input class="in" id="m73to" value="${esc(p.to)}"></label>
      <label class="f">Betreff<input class="in" id="m73su" value="${esc(p.subject)}"></label>
      <label class="f">Text<textarea class="in" id="m73bo" rows="9">${esc(p.body)}</textarea></label>
      <div class="small muted">Das Angebots-PDF wird angehängt. Danach rückt die Wiedervorlage automatisch weiter.</div></div>`,
      [{label: "Abbrechen"}, {label: "Senden", cls: "pri", onClick: async mb => {
        const x_ = await api("/api/m73/nachfass", {id: r.id, to: $("#m73to", mb).value, subject: $("#m73su", mb).value, body: $("#m73bo", mb).value});
        if (!x_ || !x_.ok) return false; toast("Nachfass-Mail gesendet"); await reload(); view(); }}], true);
  }

  async function settings(c){
    await modal("Angebote – Einstellungen", `<div class="fr"><div class="row">
      <label class="f">Erste Wiedervorlage nach Tagen (ab Versand)<input class="in num" id="m73t1" value="${c.m73_tage}"></label>
      <label class="f">Weitere Wiedervorlage nach Nachfassen (Tage)<input class="in num" id="m73t2" value="${c.m73_tage2}"></label></div>
      <label class="f">Betreff Nachfass-Mail<input class="in" id="m73mb" value="${esc(c.m73_mail_betreff)}"></label>
      <label class="f">Text Nachfass-Mail<textarea class="in" id="m73mt" rows="8">${esc(c.m73_mail_text)}</textarea></label>
      <div class="small muted">Platzhalter: [Nummer] [Titel] [Betrag] [Gueltig] [Datum] [Name] [Inhaber] [Firma]</div></div>`,
      [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
        const x_ = await api("/api/m73/cfg", {m73_tage: pnum($("#m73t1", mb).value), m73_tage2: pnum($("#m73t2", mb).value), m73_mail_betreff: $("#m73mb", mb).value, m73_mail_text: $("#m73mt", mb).value});
        if (!x_ || !x_.ok) return false; toast("Gespeichert"); view(); }}], true);
  }

  const quote = v => v === null || v === undefined ? "–" : nde(v, 0) + " %";
  const aggTable = (title, rows) => `<div class="card" style="overflow:hidden;margin-bottom:14px"><div class="hd"><h3>${title}</h3></div><table class="t"><thead><tr><th>Name</th><th class="r">Angebote</th><th class="r">Volumen</th>
    <th class="r">angenommen</th><th class="r">Vol. angenommen</th><th class="r">abgelehnt</th><th class="r">abgelaufen</th><th class="r">offen</th><th class="r">Quote</th></tr></thead>
    <tbody>${rows.map(a => `<tr><td><b>${esc(a.name)}</b></td><td class="r num">${a.anzahl}</td><td class="r num">${eur(a.volumen)}</td><td class="r num">${a.angenommen}</td><td class="r num">${eur(a.vol_angenommen)}</td>
      <td class="r num">${a.abgelehnt}</td><td class="r num">${a.abgelaufen}</td><td class="r num">${a.offen}</td>
      <td class="r"><div class="row" style="align-items:center;justify-content:flex-end;gap:6px"><div class="prog" style="width:70px"><div style="width:${a.quote || 0}%"></div></div><b class="num">${quote(a.quote)}</b></div></td></tr>`).join("") || `<tr><td colspan="9" class="empty">Keine Angebote.</td></tr>`}</tbody></table></div>`;

  async function view(){
    const d = await api("/api/m73/list" + (F.year ? "?year=" + F.year : ""));
    if (!d || !d.zeilen) return;
    const all = d.zeilen, a = d.auswertung;
    const years = [...new Set(S.invoices.filter(i => i.typ === "angebot" && i.datum).map(i => i.datum.slice(0, 4)))].sort().reverse();
    const list = all.filter(r => (F.status === "faellig" ? r.faellig : !F.status || r.status === F.status) &&
      (!F.q || [r.nr, r.name, r.titel, r.bereich].join(" ").toLowerCase().includes(F.q.toLowerCase())));
    const segs = [["faellig", "Nachfassen", all.filter(r => r.faellig).length], ["offen", "Offen", a.gesamt.offen], ["angenommen", "Angenommen", a.gesamt.angenommen],
      ["abgelehnt", "Abgelehnt", a.gesamt.abgelehnt], ["abgelaufen", "Abgelaufen", a.gesamt.abgelaufen], ["", "Alle", a.gesamt.anzahl]];
    const listHtml = `<div class="row" style="margin-bottom:12px;align-items:center;flex-wrap:wrap">
        <div class="search" style="max-width:280px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="m73q" placeholder="Nummer, Kunde, Titel …" value="${esc(F.q)}"></div>
        <div class="seg" style="flex:none">${segs.map(([k, l, n]) => `<button class="${F.status === k ? "on" : ""}" data-m73f="${k}">${l} (${n})</button>`).join("")}</div></div>
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Nr.</th><th>Datum</th><th>Kunde</th><th>Titel</th><th>Bereich</th><th>Status</th><th>Wiedervorlage</th><th class="r">Betrag</th><th style="width:330px"></th></tr></thead>
        <tbody>${list.map(r => `<tr class="click" data-m73id="${r.id}"><td><b>${esc(r.nr)}</b>${r.versendet_am ? ` <span class="muted" title="versendet ${dde(r.versendet_am)}">✉</span>` : ""}</td><td class="num">${dde(r.datum)}</td>
          <td>${esc(r.name)}</td><td class="muted">${esc(r.titel)}</td><td class="small">${esc(r.bereich)}</td>
          <td>${badge(r.status)}${r.grund ? `<div class="small muted">${esc(r.grund)}</div>` : ""}${r.folge.length ? `<div class="small muted">→ ${r.folge.map(f => esc(f.nr || "")).join(", ")}</div>` : ""}</td>
          <td class="num small">${r.wiedervorlage ? (r.faellig ? `<span class="badge warn"><span class="dot"></span>${dde(r.wiedervorlage)}</span>` : dde(r.wiedervorlage)) : ""}${r.nachfass ? `<div class="muted">${r.nachfass}× nachgefasst</div>` : ""}${r.gueltig_bis ? `<div class="muted">gültig bis ${dde(r.gueltig_bis)}</div>` : ""}</td>
          <td class="r num"><b>${eur(r.summe)}</b></td>
          <td class="r" style="white-space:nowrap" onclick="event.stopPropagation()">${r.status === "offen" ? `<button class="btn sm" data-m73m="${r.id}" title="Nachfass-Mail">${ic("mail")} Nachfassen</button><button class="btn sm ghost" data-m73w="${r.id}" title="Wiedervorlage">${ic("clock")}</button>` : ""}
            ${r.status !== "angenommen" ? `<button class="btn sm ghost" data-m73s="angenommen" data-i="${r.id}" title="angenommen">✓</button>` : ""}${r.status !== "abgelehnt" ? `<button class="btn sm ghost" data-m73s="abgelehnt" data-i="${r.id}" title="abgelehnt">✗</button>` : ""}
            ${r.status === "offen" ? `<button class="btn sm ghost" data-m73s="abgelaufen" data-i="${r.id}" title="als abgelaufen markieren">⌛</button>` : `<button class="btn sm ghost" data-m73s="offen" data-i="${r.id}" title="wieder offen">↺</button>`}</td></tr>`).join("")
          || `<tr><td colspan="9" class="empty">Keine Angebote für diesen Filter.</td></tr>`}</tbody>
        <tfoot><tr><td colspan="7">Summe</td><td class="r num">${eur(list.reduce((s_, r) => s_ + r.summe, 0))}</td><td></td></tr></tfoot></table></div>`;
    const ausHtml = `<div class="grid" style="grid-template-columns:2fr 1fr;gap:14px;align-items:start"><div>${aggTable("Je Bereich", a.bereich)}${aggTable("Je Kunde", a.kunde)}</div>
      <div class="card"><div class="hd"><h3>Ablehnungsgründe</h3></div><div class="bd">${a.gruende.length ? a.gruende.map(([g, n]) => `<div class="row" style="padding:3px 0"><span>${esc(g)}</span><span class="sp" style="flex:1"></span><b>${n}</b></div>`).join("") : `<div class="muted small">Noch keine abgelehnten Angebote mit Grund.</div>`}</div></div></div>`;
    $("#main").innerHTML = `<div class="page">${pageHead("Angebote", "Nachfassen, Status pflegen und sehen, was ankommt",
        expButtons("m73_angebote", () => ({year: F.year, status: F.status === "faellig" ? "offen" : F.status})) + `<button class="btn" id="m73set">${ic("set")} Einstellungen</button><button class="btn pri" id="m73new">${ic("plus")} Angebot</button>`)}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Offen</div><div class="v">${a.gesamt.offen}</div><div class="s">${eur(a.gesamt.vol_offen)}</div></div>
        <div class="card kpi"><div class="l">Angenommen</div><div class="v">${a.gesamt.angenommen}</div><div class="s">${eur(a.gesamt.vol_angenommen)}</div></div>
        <div class="card kpi"><div class="l">Annahmequote</div><div class="v">${quote(a.gesamt.quote)}</div><div class="s">von entschiedenen Angeboten</div></div>
        <div class="card kpi"><div class="l">Nachfassen fällig</div><div class="v" style="color:${all.some(r => r.faellig) ? "var(--warn)" : "inherit"}">${all.filter(r => r.faellig).length}</div><div class="s">Wiedervorlage erreicht</div></div></div>
      <div class="row" style="margin-bottom:12px;align-items:center"><div class="tabs" style="flex:1;margin:0">${[["liste", "Liste"], ["auswertung", "Auswertung"]].map(([k, l]) => `<div class="tab ${F.tab === k ? "on" : ""}" data-m73t="${k}">${l}</div>`).join("")}</div>
        <div class="chips" style="flex:none">${["", ...years].map(y => `<span class="chip ${F.year === y ? "on" : ""}" data-m73y="${y}">${y || "Alle Jahre"}</span>`).join("")}</div></div>
      ${F.tab === "liste" ? listHtml : ausHtml}</div>`;
    bindCommon();
    $("#m73set").onclick = () => settings(d.cfg);
    $("#m73new").onclick = () => newInvoice({typ: "angebot"});
    $$("[data-m73t]").forEach(b => b.onclick = () => { F.tab = b.dataset.m73t; view(); });
    $$("[data-m73y]").forEach(b => b.onclick = () => { F.year = b.dataset.m73y; view(); });
    $$("[data-m73f]").forEach(b => b.onclick = () => { F.status = b.dataset.m73f; view(); });
    if ($("#m73q")) $("#m73q").oninput = e => { F.q = e.target.value; debRender("m73q", view, 250); };
    $$("[data-m73id]").forEach(r => r.onclick = () => openInvoice(+r.dataset.m73id));
    $$("[data-m73m]").forEach(b => b.onclick = () => mailDlg(all.find(r => r.id == b.dataset.m73m)));
    $$("[data-m73w]").forEach(b => b.onclick = () => wvDialog(all.find(r => r.id == b.dataset.m73w)));
    $$("[data-m73s]").forEach(b => b.onclick = () => statusDialog(all.find(r => r.id == b.dataset.i), d.gruende, b.dataset.m73s));
    if (F.tab === "liste") selectify({kind: "m73", rows: "tr[data-m73id]", id: "data-m73id", rerender: view, actions: [
      {label: "Excel", run: async ids => { await doExport("m73_angebote", "xlsx", {ids, year: F.year}); return false; }},
      {label: "PDF", run: async ids => { await doExport("m73_angebote", "pdf", {ids, year: F.year}); return false; }},
      {label: "Abgelaufen", run: async ids => { for (const id of ids) await api("/api/m73/status", {id: +id, status: "abgelaufen"}); await reload(); view(); }}]});
  }
})();
