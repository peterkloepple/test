// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m77_abnahme: Abnahmeprotokoll mit Unterschrift (Handy/Tablet oder PC)
// Reiter "Abnahme" auf der Projektseite, Seite "Abnahmen & Mängel" (Projekte), Hinweis auf der Übersicht,
// Einstellungen im Reiter "EN 1090 & Abnahme".
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m77sig = '<path d="M3 17c3-4 5-9 7-9s-1 9 1 9 3-4 5-4 1 4 3 4h2"/><path d="M3 21h18"/>';
  const ERG = {"": "offen", erteilt: "Abnahme erteilt", vorbehalt: "unter Vorbehalt erteilt", verweigert: "Abnahme verweigert"};
  const STB = {entwurf: ["", "nicht unterschrieben"], teilweise: ["warn", "1 von 2 Unterschriften"], unterschrieben: ["ok", "unterschrieben"]};
  const badge = st => { const b = STB[st] || ["", st]; return `<span class="badge ${b[0]}"><span class="dot"></span>${b[1]}</span>`; };
  const TABS = window.m76Tabs = window.m76Tabs || [];
  TABS.push({key: "m77", label: "Abnahme", render: (T, id) => m77Tab(T, id)});

  EXT.nav.push({key: "m77", label: "Abnahmen & Mängel", icon: "m77sig", section: "Projekte", cnt: () => (S.m77 && S.m77.maengel_ueber) ? "⚠ " + S.m77.maengel_ueber : ""});
  EXT.views.m77 = m77View;
  EXT.dash.push(el => {
    const m = S.m77; if (!m || !m.maengel_ueber) return;
    const d = document.createElement("div"); d.className = "alert warn"; d.style.marginBottom = "10px";
    d.innerHTML = `${ic("m77sig")}<b>${m.maengel_ueber} Mangel/Mängel aus Abnahmen überfällig</b><span class="small">${m.maengel_offen} offen insgesamt</span><span class="sp" style="flex:1"></span><span class="small"><u>Mängel ansehen →</u></span>`;
    d.onclick = () => go("m77"); el.appendChild(d);
  });

  // ---------------------------------------------------------------- signature pad (PC)
  function padHtml(id){ return `<canvas id="${id}" style="width:100%;height:200px;border:2px dashed var(--line,#ccc);border-radius:10px;background:#fff;touch-action:none;display:block"></canvas>`; }
  function pad(cv){
    const ctx = cv.getContext("2d"); let down = false, last = null, drawn = false;
    const fit = () => { const r = cv.getBoundingClientRect(), d = window.devicePixelRatio || 1; cv.width = r.width * d; cv.height = r.height * d; ctx.setTransform(d, 0, 0, d, 0, 0);
      ctx.lineWidth = 2.4; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#111"; };
    setTimeout(fit, 30);
    const pos = e => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    cv.addEventListener("pointerdown", e => { down = true; last = pos(e); cv.setPointerCapture(e.pointerId); e.preventDefault(); });
    cv.addEventListener("pointermove", e => { if (!down) return; const p = pos(e); ctx.beginPath(); ctx.moveTo(last[0], last[1]); ctx.lineTo(p[0], p[1]); ctx.stroke(); last = p; drawn = true; });
    ["pointerup", "pointercancel"].forEach(t => cv.addEventListener(t, () => down = false));
    return {clear: () => { ctx.clearRect(0, 0, cv.width, cv.height); drawn = false; }, drawn: () => drawn,
      png: () => { const o = document.createElement("canvas"); o.width = cv.width; o.height = cv.height; const c = o.getContext("2d"); c.fillStyle = "#fff"; c.fillRect(0, 0, o.width, o.height); c.drawImage(cv, 0, 0); return o.toDataURL("image/png"); }};
  }

  async function signPc(r, rolle, defName, after){
    let P = null;
    const html = `<div class="fr"><label class="f">Name in Druckschrift<input class="in" id="m77sn" value="${esc(defName || "")}"></label>
      <div class="small muted" style="margin:6px 0">Mit Maus, Stift oder Finger (Touchscreen) im Feld unterschreiben.</div>${padHtml("m77pad")}</div>`;
    await modal(`Unterschrift ${rolle === "kunde" ? "Auftraggeber" : "Auftragnehmer"} – ${r.nr}`, html, [
      {label: "Feld leeren", onClick: () => { P.clear(); return false; }}, {label: "Abbrechen"},
      {label: "Unterschreiben", cls: "pri", onClick: async mb => {
        if (!P.drawn()) { toast("Bitte im Feld unterschreiben", true); return false; }
        const res = await api("/api/m77/sign", {id: r.id, rolle, name: $("#m77sn", mb).value, png: P.png()});
        if (!res || !res.ok) return false;
        toast(res.status === "unterschrieben" ? "Unterschrieben – PDF im Projekt abgelegt" : "Unterschrift gespeichert"); after();
      }}], true, mb => { P = pad($("#m77pad", mb)); });
  }

  async function signHandy(r, rolle, after){
    const res = await api("/api/m77/handy/start", {id: r.id, rolle});
    if (!res || !res.ok) return;
    let timer = null;
    const html = `<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap"><div style="width:240px;background:#fff;padding:8px;border-radius:10px">${res.svg}</div>
      <div style="flex:1;min-width:220px"><b>QR-Code mit dem Handy/Tablet scannen</b><div class="small muted" style="margin:6px 0">Gerät muss im selben WLAN sein. Dort werden Protokoll und Unterschriftsfeld angezeigt.</div>
      <div class="small"><code style="word-break:break-all">${esc(res.url)}</code></div>
      <div id="m77hs" class="small" style="margin-top:10px">Warte auf Unterschrift …</div></div></div>`;
    const poll = async () => {
      const s = await api("/api/m77/handy/status?token=" + encodeURIComponent(res.token), undefined, {quiet: true});
      const el = $("#m77hs"); if (!el) { clearInterval(timer); return; }
      if (s && s.fertig) { clearInterval(timer); el.innerHTML = `<span class="badge ok"><span class="dot"></span>Unterschrift empfangen</span>`; toast("Unterschrift vom Handy empfangen"); }
      else if (s && !s.aktiv) { clearInterval(timer); el.textContent = "Code abgelaufen – bitte neu erzeugen."; }
      else if (s) el.textContent = `Warte auf Unterschrift … (noch ${Math.ceil(s.rest_s / 60)} min)`;
    };
    timer = setInterval(poll, 2000);
    await modal(`Unterschrift per Handy – ${rolle === "kunde" ? "Auftraggeber" : "Auftragnehmer"}`, html, [{label: "Schließen"}], true);
    clearInterval(timer);
    after();
  }

  // ---------------------------------------------------------------- editor
  async function editProt(pid, r, vor, after){
    const n = !r;
    r = r || {datum: todayIso(), ort: vor.ort || "", teilnehmer: vor.teilnehmer || [], leistungen: vor.leistungen || [], maengel: [], vorbehalte: "", ergebnis: "erteilt"};
    const signed = r.signiert_kunde || r.signiert_an;
    const rowT = (a, i) => `<div class="row" data-m77tn style="margin-bottom:4px"><input class="in" data-k="name" value="${esc(a.name || "")}" placeholder="Name"><input class="in" data-k="rolle" value="${esc(a.rolle || "")}" placeholder="Funktion / Firma"><button class="btn sm ghost" type="button" data-m77x>✕</button></div>`;
    const rowL = a => `<div class="row" data-m77le style="margin-bottom:4px;align-items:center"><label class="chk" style="flex:none" title="abgenommen"><input type="checkbox" data-k="ok" ${a.ok !== false ? "checked" : ""}></label><input class="in" data-k="text" value="${esc(a.text || "")}" placeholder="Leistung"><button class="btn sm ghost" type="button" data-m77x>✕</button></div>`;
    const rowM = a => `<div class="row" data-m77ma style="margin-bottom:4px"><input class="in" data-k="text" value="${esc(a.text || "")}" placeholder="Mangel"><input type="date" class="in" data-k="frist" value="${esc(a.frist || "")}" style="flex:0 0 150px" title="Frist zur Beseitigung"><input type="hidden" data-k="erledigt_am" value="${esc(a.erledigt_am || "")}"><button class="btn sm ghost" type="button" data-m77x>✕</button></div>`;
    const html = `<div class="fr">${signed ? `<div class="alert warn" style="cursor:default;margin-bottom:8px">${ic("alert")}<span>Bereits unterschrieben – eine Änderung am Inhalt verwirft die Unterschriften.</span></div>` : ""}
      <div class="row"><label class="f" style="flex:0 0 160px">Datum<input type="date" class="in" id="m77d" value="${esc(r.datum || "")}"></label><label class="f">Ort<input class="in" id="m77o" value="${esc(r.ort || "")}"></label>
        <label class="f" style="flex:0 0 230px">Ergebnis<select class="in" id="m77e">${Object.entries(ERG).filter(([k]) => k).map(([k, l]) => `<option value="${k}" ${r.ergebnis === k ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
      <div class="small muted" style="margin:8px 0 4px">Teilnehmer</div><div id="m77tl">${(r.teilnehmer || []).map(rowT).join("")}</div><button class="btn sm" type="button" id="m77ta">${ic("plus")} Teilnehmer</button>
      <div class="small muted" style="margin:10px 0 4px">Abgenommene Leistungen (Haken = abgenommen)</div><div id="m77ll">${(r.leistungen || []).map(rowL).join("")}</div>
      <div class="row" style="gap:6px"><button class="btn sm" type="button" id="m77la">${ic("plus")} Leistung</button><button class="btn sm ghost" type="button" id="m77lv" title="aus angenommenem Angebot bzw. Projekt-Leistungen">Vorschlag übernehmen</button></div>
      <div class="small muted" style="margin:10px 0 4px">Mängel mit Frist</div><div id="m77ml">${(r.maengel || []).map(rowM).join("")}</div><button class="btn sm" type="button" id="m77ma">${ic("plus")} Mangel</button>
      <label class="f" style="margin-top:10px">Vorbehalte / Bemerkungen<textarea class="in" id="m77v" rows="3">${esc(r.vorbehalte || "")}</textarea></label></div>`;
    const collect = mb => {
      const grab = sel => $$(sel, mb).map(row => { const o = {}; $$("[data-k]", row).forEach(i => o[i.dataset.k] = i.type === "checkbox" ? i.checked : i.value.trim()); return o; });
      return {id: r.id || null, project_id: pid, datum: $("#m77d", mb).value, ort: $("#m77o", mb).value, ergebnis: $("#m77e", mb).value, vorbehalte: $("#m77v", mb).value,
        teilnehmer: grab("[data-m77tn]"), leistungen: grab("[data-m77le]"), maengel: grab("[data-m77ma]")};
    };
    const btns = [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", onClick: async mb => {
      const res = await api("/api/m77/save", collect(mb)); if (!res || !res.ok) return false;
      toast(res.info || "Protokoll gespeichert", !!res.info); after(res.id);
    }}];
    if (!n) btns.unshift({label: "Löschen", cls: "danger", onClick: async () => { const x_ = await api("/api/m77/delete", {ids: [r.id]}); if (!x_ || x_.ok === false) return false; toast("Protokoll gelöscht"); after(); }});
    await modal(n ? "Neues Abnahmeprotokoll" : `Abnahmeprotokoll ${r.nr}`, html, btns, true, mb => {
      const bindX = () => $$("[data-m77x]", mb).forEach(b => b.onclick = () => b.closest(".row").remove());
      const add = (id, h) => { $(id, mb).insertAdjacentHTML("beforeend", h); bindX(); };
      $("#m77ta", mb).onclick = () => add("#m77tl", rowT({}));
      $("#m77la", mb).onclick = () => add("#m77ll", rowL({}));
      $("#m77ma", mb).onclick = () => add("#m77ml", rowM({}));
      $("#m77lv", mb).onclick = () => { const have = new Set($$("[data-m77le] [data-k=text]", mb).map(i => i.value.trim().toLowerCase()));
        (vor.leistungen || []).filter(l => !have.has(l.text.toLowerCase())).forEach(l => add("#m77ll", rowL(l))); };
      bindX();
    });
  }

  // ---------------------------------------------------------------- project tab
  async function m77Tab(T, pid){
    const d = await api("/api/m77/project?project_id=" + pid);
    if (!d || !d.protokolle) { T.innerHTML = `<div class="card empty">Nicht verfügbar.</div>`; return; }
    const re = () => m77Tab(T, pid);
    const fg = d.freigabe;
    const custName = r => { const t = (r.teilnehmer || []).find(a => /auftraggeber|kunde|bauherr/i.test(a.rolle || "")); return t ? t.name : ""; };
    T.innerHTML = `<div class="alert ${fg.ok ? "ok" : "warn"}" style="cursor:default;margin-bottom:12px">${ic(fg.ok ? "check" : "alert")}<span><b>${fg.ok ? "Schlussrechnung freigegeben" : "Noch keine erteilte Abnahme"}</b> – ${esc(fg.text)}${fg.ok && fg.maengel_offen ? ` · ${fg.maengel_offen} Mangel/Mängel offen` : ""}</span></div>
      <div class="row" style="margin-bottom:12px"><span style="flex:1"></span>${expButtons("m77_abnahme", {project_id: pid}, true)}<button class="btn pri" id="m77new">${ic("plus")} Neues Abnahmeprotokoll</button></div>
      ${d.protokolle.map(r => `<div class="card" style="margin-bottom:14px" data-m77p="${r.id}"><div class="hd"><h3>${esc(r.nr)} · ${dde(r.datum)}</h3><div class="act">${badge(r.status)}
          <span class="badge ${r.ergebnis === "verweigert" ? "bad" : r.ergebnis ? "acc" : ""}">${esc(r.ergebnis_de)}</span>
          <button class="btn sm" data-m77ed="${r.id}">Bearbeiten</button><button class="btn sm" data-m77pdf="${r.id}">${ic("pdf")} PDF</button></div></div>
        <div class="bd"><div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px">
          <div><div class="small muted">Ort</div><div>${esc(r.ort || "–")}</div><div class="small muted" style="margin-top:6px">Leistungen</div><div class="small">${r.leistungen.length ? r.leistungen.map(l => (l.ok === false ? "✗ " : "✓ ") + esc(l.text)).join("<br>") : "gesamte Leistung"}</div></div>
          <div><div class="small muted">Mängel (${r.maengel_offen} offen${r.maengel_ueber ? `, <b style="color:var(--bad)">${r.maengel_ueber} überfällig</b>` : ""})</div>
            ${r.maengel.map((m, i) => `<label class="chk small" style="display:flex;gap:6px;margin:3px 0"><input type="checkbox" data-m77md="${r.id}|${i}" ${m.erledigt_am ? "checked" : ""}><span style="${m.erledigt_am ? "text-decoration:line-through;opacity:.6" : ""}">${esc(m.text)}${m.frist ? ` <span class="muted">– Frist ${dde(m.frist)}</span>` : ""}${m.erledigt_am ? ` <span class="muted">(erledigt ${dde(m.erledigt_am)})</span>` : ""}</span></label>`).join("") || `<div class="small">keine</div>`}</div>
          ${["kunde", "an"].map(ro => { const img = r["sig_" + ro + "_img"], nm = r["sig_" + ro + "_name"], z = r["sig_" + ro + "_zeit"];
            return `<div><div class="small muted">Unterschrift ${ro === "kunde" ? "Auftraggeber" : "Auftragnehmer"}</div>${img ? `<img src="${img}" style="max-width:100%;max-height:70px;background:#fff;border-radius:6px;display:block;margin:4px 0"><div class="small">${esc(nm || "")} · ${esc((z || "").slice(0, 16))}</div><button class="btn sm ghost" data-m77us="${r.id}|${ro}">Unterschrift entfernen</button>`
              : `<div class="row" style="gap:6px;margin-top:4px"><button class="btn sm pri" data-m77sh="${r.id}|${ro}" title="QR-Code für Handy/Tablet">${ic("m77sig")} Handy/Tablet</button><button class="btn sm" data-m77sp="${r.id}|${ro}" data-nm="${esc(ro === "an" ? d.settings.an_name : custName(r))}">Am PC</button></div>`}</div>`; }).join("")}
        </div>${r.pdf_file ? `<div class="small" style="margin-top:8px"><a href="#" data-m77of="${esc(r.pdf_file)}">${ic("pdf")} ${esc(r.pdf_file.split(/[\\/]/).pop())}</a> · Prüfsumme ${esc((r.hash || "").slice(0, 16))}…</div>` : ""}</div></div>`).join("")
        || `<div class="card empty">Noch kein Abnahmeprotokoll. Mit „Neues Abnahmeprotokoll“ anlegen – Leistungen werden aus dem angenommenen Angebot vorbelegt.</div>`}`;
    bindCommon(T);
    const find = id => d.protokolle.find(r => r.id == id);
    $("#m77new", T).onclick = () => editProt(pid, null, d.vorschlag, re);
    $$("[data-m77ed]", T).forEach(b => b.onclick = () => editProt(pid, find(b.dataset.m77ed), d.vorschlag, re));
    $$("[data-m77pdf]", T).forEach(b => b.onclick = async () => { const r = await api("/api/m77/pdf", {id: +b.dataset.m77pdf}); if (r && r.ok) { toast("PDF im Projekt abgelegt"); re(); } });
    $$("[data-m77sh]", T).forEach(b => b.onclick = () => { const [id, ro] = b.dataset.m77sh.split("|"); signHandy(find(id), ro, re); });
    $$("[data-m77sp]", T).forEach(b => b.onclick = () => { const [id, ro] = b.dataset.m77sp.split("|"); signPc(find(id), ro, b.dataset.nm, re); });
    $$("[data-m77us]", T).forEach(b => b.onclick = async () => { const [id, ro] = b.dataset.m77us.split("|"); await api("/api/m77/unsign", {id: +id, rolle: ro}); re(); });
    $$("[data-m77md]", T).forEach(c => c.onchange = async () => { const [id, i] = c.dataset.m77md.split("|"); await api("/api/m77/mangel", {id: +id, idx: +i, erledigt: c.checked}); await reload(); re(); });
    $$("[data-m77of]", T).forEach(a => a.onclick = ev => { ev.preventDefault(); api("/api/open", {path: a.dataset.m77of}); });
  }

  // ---------------------------------------------------------------- overview
  let m77F = "offen";
  async function m77View(){
    const d = await api("/api/m77/overview");
    const ml = d.maengel.filter(m => m77F === "alle" ? true : m77F === "ueber" ? m.ueber : !m.erledigt_am);
    $("#main").innerHTML = `<div class="page">${pageHead("Abnahmen & Mängel", "Abnahmeprotokolle aller Projekte und offene Mängel mit Fristen", expButtons("m77_abnahme", {}))}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Protokolle</div><div class="v">${d.protokolle.length}</div><div class="s">${d.protokolle.filter(r => r.status === "unterschrieben").length} unterschrieben</div></div>
        <div class="card kpi"><div class="l">Mängel offen</div><div class="v">${d.maengel.filter(m => !m.erledigt_am).length}</div><div class="s">von ${d.maengel.length}</div></div>
        <div class="card kpi"><div class="l">Überfällig</div><div class="v" style="color:${d.maengel.some(m => m.ueber) ? "var(--bad)" : "inherit"}">${d.maengel.filter(m => m.ueber).length}</div><div class="s">Frist überschritten</div></div>
        <div class="card kpi"><div class="l">Ohne Unterschrift</div><div class="v">${d.protokolle.filter(r => r.status !== "unterschrieben").length}</div><div class="s">Entwurf / teilweise</div></div></div>
      <div class="card" style="margin-bottom:14px;overflow:hidden"><div class="hd"><h3>Mängel</h3><div class="act"><div class="seg">${[["offen", "Offen"], ["ueber", "Überfällig"], ["alle", "Alle"]].map(([k, l]) => `<button class="${m77F === k ? "on" : ""}" data-m77f="${k}">${l}</button>`).join("")}</div></div></div>
        <table class="t"><thead><tr><th style="width:40px">erl.</th><th>Mangel</th><th>Projekt</th><th>Protokoll</th><th>Frist</th><th>erledigt am</th></tr></thead>
        <tbody>${ml.map(m => `<tr><td><input type="checkbox" data-m77md="${m.prot_id}|${m.idx}" ${m.erledigt_am ? "checked" : ""}></td><td>${esc(m.text)}</td><td class="click" data-m77pr="${m.project_id}"><b>${esc(m.pnr || "")}</b> ${esc(m.pname || "")}</td><td class="small">${esc(m.nr)}</td>
          <td>${m.frist ? (m.ueber ? `<span class="badge bad"><span class="dot"></span>${dde(m.frist)}</span>` : dde(m.frist)) : "–"}</td><td>${dde(m.erledigt_am || "")}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Keine Mängel für diesen Filter.</td></tr>`}</tbody></table></div>
      <div class="card" style="overflow:hidden"><div class="hd"><h3>Protokolle</h3></div><table class="t" id="m77pt"><thead><tr><th>Nr.</th><th>Datum</th><th>Projekt</th><th>Ergebnis</th><th>Status</th><th class="r">Mängel offen</th></tr></thead>
        <tbody>${d.protokolle.map(r => `<tr class="click" data-m77row="${r.id}" data-m77pr="${r.project_id}"><td><b>${esc(r.nr)}</b></td><td>${dde(r.datum)}</td><td>${esc(r.pnr || "")} ${esc(r.pname || "")}</td><td>${esc(r.ergebnis_de)}</td><td>${badge(r.status)}</td><td class="r num">${r.maengel_offen}</td></tr>`).join("")
          || `<tr><td colspan="6" class="empty">Noch keine Abnahmeprotokolle – im Projekt im Reiter „Abnahme“ anlegen.</td></tr>`}</tbody></table></div></div>`;
    bindCommon();
    $$("[data-m77f]").forEach(b => b.onclick = () => { m77F = b.dataset.m77f; m77View(); });
    $$("[data-m77pr]").forEach(r => r.onclick = () => { pTab = "m77"; go("project", +r.dataset.m77pr); });
    $$("[data-m77md]").forEach(c => c.onchange = async () => { const [id, i] = c.dataset.m77md.split("|"); await api("/api/m77/mangel", {id: +id, idx: +i, erledigt: c.checked}); await reload(); m77View(); });
    selectify({kind: "m77prot", rows: "#m77pt tr[data-m77row]", id: "data-m77row", rerender: m77View, actions: [
      {label: "Excel", run: async ids => { await doExport("m77_abnahme", "xlsx", {ids}); return false; }},
      {label: "PDF", run: async ids => { await doExport("m77_abnahme", "pdf", {ids}); return false; }},
      {label: "Löschen", cls: "danger", run: async ids => { await api("/api/m77/delete", {ids: ids.map(Number)}); toast(ids.length + " gelöscht"); await reload(); m77View(); }}]});
  }

  // ---------------------------------------------------------------- settings (rendered inside the m76 settings tab)
  window.m77SettingsRender = async el => {
    if (!el) return;
    const d = await api("/api/m77/settings", undefined, {quiet: true}).catch(() => null);
    const s = (d && d.settings) || (S.settings.m77 || {port: 8782, pruefen: true, sperren: false, an_name: S.settings.inhaber || ""});
    el.innerHTML = `<div class="card"><div class="hd"><h3>Abnahmeprotokoll</h3></div><div class="bd fr">
      <div class="row"><label class="f">Name Auftragnehmer (Unterzeichner)<input class="in" id="m77san" value="${esc(s.an_name || S.settings.inhaber || "")}"></label>
        <label class="f" style="flex:0 0 200px">Port für Handy-Unterschrift<input class="in num" id="m77spo" value="${esc(s.port || 8782)}"></label></div>
      <label class="chk"><input type="checkbox" id="m77spr" ${s.pruefen !== false ? "checked" : ""}> Beim Erstellen der Schlussrechnung prüfen, ob eine unterschriebene Abnahme vorliegt (Hinweis)</label>
      <label class="chk"><input type="checkbox" id="m77ssp" ${s.sperren ? "checked" : ""}> Schlussrechnung ohne Abnahme sperren (statt nur Hinweis)</label>
      <div class="row"><span style="flex:1"></span><button class="btn pri" id="m77ss">Speichern</button></div></div></div>`;
    $("#m77ss", el).onclick = async () => { const r = await api("/api/m77/settings", {an_name: $("#m77san", el).value, port: $("#m77spo", el).value, pruefen: $("#m77spr", el).checked, sperren: $("#m77ssp", el).checked});
      if (r && r.ok) toast("Gespeichert"); };
  };
})();
