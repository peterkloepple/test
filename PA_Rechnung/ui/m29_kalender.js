// PA Rechnung v2.0.7 - Kalender: kompletter TimeTree-Kalender (heruntergeladen) als eigener Reiter unter "Uebersicht"
// Ansichten Monat / Woche / Liste, Kalender ein-/ausblenden, Suche, Termin-Details, Abruf per Knopf oder automatisch,
// .ics-Import (z. B. bei Google/Apple-Anmeldung) und Export als .ics. Nur lesend - Aenderungen bitte in TimeTree.
// Autor: T. Pfeiffer
(function(){
  IC.cal = '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/><path d="M7 13h3M7 17h3M14 13h3"/>';
  EXT.nav.push({key:"kalender", label:"Kalender", icon:"cal", section:"Top", cnt:() => (S.kal && S.kal.heute) ? "heute " + S.kal.heute : ""});
  const LS = "pa_kal";
  const st = (() => { try { return Object.assign({ansicht:"monat", datum:todayIso(), q:""}, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) { return {ansicht:"monat", datum:todayIso(), q:""}; } })();
  const save = () => { try { localStorage.setItem(LS, JSON.stringify({ansicht:st.ansicht, datum:st.datum})); } catch (e) {} };
  const WD = ["Mo","Di","Mi","Do","Fr","Sa","So"];
  const pd = s => { const [y,m,d] = s.slice(0,10).split("-").map(Number); return new Date(y, m-1, d); };
  const addD = (d, n) => { const x_ = new Date(d); x_.setDate(x_.getDate() + n); return x_; };
  const monday = d => addD(d, -((d.getDay() + 6) % 7));
  const hm = s => s.slice(11, 16);
  const fmtD = s => { const d = pd(s); return `${WD[(d.getDay()+6)%7]}, ${d.getDate()}. ${MONL[d.getMonth()]} ${d.getFullYear()}`; };
  let pollT = null;

  function range(){
    const d = pd(st.datum);
    if (st.ansicht === "woche") { const a = monday(d); return [a, addD(a, 7)]; }
    if (st.ansicht === "liste") { const a = new Date(d.getFullYear(), d.getMonth(), 1); return [a, new Date(d.getFullYear(), d.getMonth() + 2, 1)]; }
    const a = monday(new Date(d.getFullYear(), d.getMonth(), 1)); return [a, addD(a, 42)];
  }
  function title(){
    const d = pd(st.datum);
    if (st.ansicht === "woche") { const a = monday(d), b = addD(a, 6); const kw = isoWeek(a);
      return `KW ${kw} · ${a.getDate()}.${a.getMonth()+1}. – ${b.getDate()}.${b.getMonth()+1}.${b.getFullYear()}`; }
    if (st.ansicht === "liste") { const b = new Date(d.getFullYear(), d.getMonth() + 1, 1); return `${MONL[d.getMonth()]} – ${MONL[b.getMonth()]} ${b.getFullYear()}`; }
    return `${MONL[d.getMonth()]} ${d.getFullYear()}`;
  }
  function isoWeek(d){ const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); const dn = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - dn);
    const y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1)); return Math.ceil(((t - y0) / 86400000 + 1) / 7); }
  // occurrences per day (multi-day events appear on every day)
  function byDay(evs){
    const m = {};
    evs.forEach(e => { let d = pd(e.start); const last = pd(e.end);
      for (let i = 0; i < 62 && d <= last; i++) { const k = isoLocal(d); (m[k] = m[k] || []).push(e);
        if (!e.all_day && i === 0 && e.end.slice(0,10) !== e.start.slice(0,10) && hm(e.end) === "00:00" && isoLocal(addD(d,1)) === e.end.slice(0,10)) break;
        d = addD(d, 1); } });
    return m;
  }
  const pill = e => `<div class="kev ${e.all_day?"ad":""}" data-kev='${esc(JSON.stringify(e))}' style="--c:${esc(e.farbe)}" title="${esc(e.title)}${e.ort?" · "+esc(e.ort):""}">${e.all_day?"":`<b>${hm(e.start)}</b> `}${esc(e.title)}</div>`;

  EXT.views.kalender = async function(){
    const info = await api("/api/kal/info");
    const [a, b] = range();
    const r = (info.kalender || []).length ? await api(`/api/kal/events?von=${isoLocal(a)}&bis=${isoLocal(b)}&q=${encodeURIComponent(st.q)}`) : {events: []};
    const evs = r.events || [];
    const last = info.last || {};
    const sub = info.laeuft ? `Wird abgerufen … ${esc(info.status||"")}` :
      (last.zeit ? `TimeTree zuletzt abgerufen ${dde(last.zeit.slice(0,10))} ${last.zeit.slice(11,16)} · ${last.kalender||0} Kalender, ${nde(last.termine||0,0)} Termine` : "TimeTree-Kalender im Programm")
      + (last.fehler ? ` · <span style="color:var(--bad)">${esc(last.fehler)}</span>` : "");
    const head = pageHead("Kalender", sub,
      `<button class="btn" id="kics">${ic("up")} .ics importieren</button><button class="btn" id="kexp">${ic("save")} Als .ics speichern</button>
       <button class="btn" id="kset">${ic("set")} TimeTree</button><button class="btn pri" id="ksync" ${info.laeuft?"disabled":""}>${ic("sync")} Jetzt abrufen</button>`);
    let body = "";
    if (!(info.kalender || []).length) {
      body = setupCard(info);
    } else {
      const chips = info.kalender.map(c => `<span class="chip kchip ${c.aktiv?"on":""}" data-kc="${esc(c.id)}" style="--c:${esc(c.farbe||"#0a84ff")}"><i></i>${esc(c.name)} <b>${nde(c.anzahl||0,0)}</b></span>`).join("");
      const tb = `<div class="row" style="align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
          <button class="btn" style="flex:none" id="kprev">‹</button><button class="btn" style="flex:none" id="khome">Heute</button><button class="btn" style="flex:none" id="knext">›</button>
          <b style="flex:none;min-width:200px;font:600 17px var(--disp);margin:0 6px">${title()}</b>
          <div class="chips" style="flex:none">${[["monat","Monat"],["woche","Woche"],["liste","Liste"]].map(([k,l])=>`<span class="chip ${st.ansicht===k?"on":""}" data-ka="${k}">${l}</span>`).join("")}</div>
          <span class="sp"></span>
          <div class="search" style="flex:none;width:240px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="kq" placeholder="Termine suchen …" value="${esc(st.q)}"></div></div>
        <div class="chips" style="margin-bottom:12px">${chips}</div>`;
      body = tb + (st.ansicht === "monat" ? monthView(evs, a) : st.ansicht === "woche" ? weekView(evs, a) : listView(evs));
    }
    $("#main").innerHTML = `<div class="page kal">${head}${body}</div>`;
    bind(info);
    clearTimeout(pollT);
    if (info.laeuft) pollT = setTimeout(() => { if (view === "kalender") EXT.views.kalender(); }, 1500);
  };

  function setupCard(info){
    return `<div class="grid g2" style="align-items:start"><div class="card"><div class="hd"><h3>${ic("cal")} TimeTree verbinden</h3></div><div class="bd fr">
      <div class="small muted">Der komplette TimeTree-Kalender (alle Kalender, Labels, Termine mit Wiederholungen, Notizen und Orten) wird heruntergeladen und im Programm gespeichert. In TimeTree wird nichts verändert.</div>
      ${tTForm(info)}
      <button class="btn pri" id="kconnect">${ic("sync")} Verbinden &amp; abrufen</button></div></div>
      <div class="card"><div class="hd"><h3>${ic("up")} Oder: Kalenderdatei (.ics) einlesen</h3></div><div class="bd fr">
      <div class="small muted">Für Konten, die sich in TimeTree nur über Google, Apple oder LINE anmelden (ohne TimeTree-Passwort): Kalender als .ics-Datei exportieren und hier hineinziehen. Auch jede andere .ics-Datei (Outlook, Google, iCloud) geht.</div>
      <div class="dz" id="kdz">.ics-Datei hierher ziehen<br><button class="btn" id="kics2" style="margin-top:10px">Datei wählen …</button></div></div></div></div>`;
  }
  function tTForm(info){
    return `<label class="f">E-Mail (TimeTree-Konto)<input class="in" id="kmail" value="${esc(info.email||"")}" autocomplete="off"></label>
      <label class="f">Passwort ${info.has_pw?`<span class="badge ok">gespeichert</span>`:""}<input class="in" type="password" id="kpw" placeholder="${info.has_pw?"leer lassen = unverändert":"TimeTree-Passwort"}" autocomplete="new-password"></label>
      <label class="f">Automatisch abrufen<select class="in" id="kauto">${[[0,"aus (nur per Knopf)"],[15,"alle 15 Minuten"],[30,"alle 30 Minuten"],[60,"jede Stunde"],[240,"alle 4 Stunden"],[1440,"einmal täglich"]].map(([v,l])=>`<option value="${v}" ${+info.auto===v?"selected":""}>${l}</option>`).join("")}</select></label>
      <div class="small muted">Das Passwort wird verschlüsselt (Windows-Benutzerkonto) im Datenordner gespeichert. Der Abruf nutzt die Web-Schnittstelle von TimeTree (wie timetreeapp.com) – sie ist nicht offiziell dokumentiert und kann sich ändern.</div>`;
  }

  function monthView(evs, a){
    const m = byDay(evs), cur = pd(st.datum).getMonth(), t = todayIso();
    let h = `<div class="card kmon"><div class="kgrid khead">${WD.map(w=>`<div>${w}</div>`).join("")}</div><div class="kgrid">`;
    for (let i = 0; i < 42; i++) { const d = addD(a, i), k = isoLocal(d), list = (m[k] || []);
      const show = list.slice(0, 4);
      h += `<div class="kday ${d.getMonth()!==cur?"other":""} ${k===t?"today":""} ${[5,6].includes(i%7)?"we":""}" data-kd="${k}"><div class="kdn">${d.getDate()}</div>${show.map(pill).join("")}${list.length>4?`<div class="kmore" data-kday="${k}">+ ${list.length-4} weitere</div>`:""}</div>`; }
    return h + `</div></div><div class="small muted" style="margin-top:8px">Tag anklicken = alle Termine des Tages · Termin anklicken = Details</div>`;
  }
  function weekView(evs, a){
    const m = byDay(evs), t = todayIso(), H0 = 0, H1 = 24, PX = 42;
    const days = Array.from({length:7}, (_, i) => addD(a, i));
    const allday = days.map(d => (m[isoLocal(d)] || []).filter(e => e.all_day));
    const timed = days.map(d => (m[isoLocal(d)] || []).filter(e => !e.all_day));
    let h = `<div class="card kweek"><div class="kwh"><div></div>${days.map(d=>`<div class="${isoLocal(d)===t?"today":""}" data-kday="${isoLocal(d)}"><b>${WD[(d.getDay()+6)%7]}</b> ${d.getDate()}.${d.getMonth()+1}.</div>`).join("")}</div>
      <div class="kwh kwad"><div class="small muted">ganztägig</div>${allday.map(l=>`<div>${l.map(pill).join("")}</div>`).join("")}</div>
      <div class="kwbody" id="kwbody"><div class="kwtimes">${Array.from({length:H1-H0},(_,i)=>`<div style="height:${PX}px">${String(H0+i).padStart(2,"0")}:00</div>`).join("")}</div>`;
    days.forEach((d, di) => { const k = isoLocal(d);
      const list = timed[di].map(e => { const s = e.start.slice(0,10) < k ? 0 : (+e.start.slice(11,13)) * 60 + (+e.start.slice(14,16));
        const en = e.end.slice(0,10) > k ? 1440 : Math.max(s + 20, (+e.end.slice(11,13)) * 60 + (+e.end.slice(14,16))); return {e, s, en}; }).sort((x_, y_) => x_.s - y_.s || y_.en - x_.en);
      const lanes = []; list.forEach(o => { let l = lanes.findIndex(end => end <= o.s); if (l < 0) { l = lanes.length; lanes.push(0); } lanes[l] = o.en; o.l = l; });
      const nl = Math.max(1, lanes.length);
      h += `<div class="kwcol ${k===t?"today":""}" style="height:${(H1-H0)*PX}px">${Array.from({length:H1-H0},(_,i)=>`<div class="kwline" style="top:${i*PX}px"></div>`).join("")}
        ${list.map(o => `<div class="kev kwev" data-kev='${esc(JSON.stringify(o.e))}' style="--c:${esc(o.e.farbe)};top:${(o.s/60-H0)*PX}px;height:${Math.max(18,(o.en-o.s)/60*PX-2)}px;left:${o.l/nl*100}%;width:${100/nl}%"><b>${hm(o.e.start)}</b> ${esc(o.e.title)}${o.e.ort?`<div class="small">${esc(o.e.ort)}</div>`:""}</div>`).join("")}</div>`; });
    return h + `</div></div>`;
  }
  function listView(evs){
    const m = {}; evs.forEach(e => { const k = e.start.slice(0,10) < isoLocal(range()[0]) ? isoLocal(range()[0]) : e.start.slice(0,10); (m[k] = m[k] || []).push(e); });
    const keys = Object.keys(m).sort(); const t = todayIso();
    return `<div class="card" style="overflow:hidden"><table class="t"><thead><tr><th style="width:190px">Tag</th><th style="width:110px">Zeit</th><th>Termin</th><th>Ort</th><th>Kalender / Label</th></tr></thead><tbody>
      ${keys.map(k => m[k].map((e, i) => `<tr class="click ${k===t?"ktoday":""}" data-kev='${esc(JSON.stringify(e))}'><td>${i===0?`<b>${fmtD(k)}</b>`:""}</td>
        <td class="num small">${e.all_day?"ganztägig":hm(e.start)+"–"+(e.end.slice(0,10)!==e.start.slice(0,10)?dde(e.end.slice(0,10))+" ":"")+hm(e.end)}</td>
        <td><span class="kdot" style="background:${esc(e.farbe)}"></span><b>${esc(e.title)}</b>${e.wdh?` <span class="small muted" title="wiederkehrend">↻</span>`:""}${e.notiz?`<div class="small muted">${esc(e.notiz.slice(0,120))}</div>`:""}</td>
        <td class="small">${esc(e.ort)}</td><td class="small muted">${esc(e.kal)}${e.label?" · "+esc(e.label):""}</td></tr>`).join("")).join("")
      || `<tr><td colspan="5" class="empty">Keine Termine in diesem Zeitraum${st.q?" für diese Suche":""}.</td></tr>`}</tbody></table></div>`;
  }

  function evDialog(e){
    const same = e.start.slice(0,10) === e.end.slice(0,10);
    const when = e.all_day ? (same ? fmtD(e.start) + " · ganztägig" : fmtD(e.start) + " – " + fmtD(e.end) + " · ganztägig")
      : (same ? `${fmtD(e.start)} · ${hm(e.start)} – ${hm(e.end)} Uhr` : `${fmtD(e.start)} ${hm(e.start)} – ${fmtD(e.end)} ${hm(e.end)} Uhr`);
    const link = s => esc(s).replace(/(https?:\/\/[^\s<]+)/g, '<a href="#" data-kurl="$1">$1</a>');
    modal(e.title, `<div class="fr"><div style="display:flex;gap:10px;align-items:center"><span class="kdot" style="width:12px;height:12px;background:${esc(e.farbe)}"></span><b>${when}</b>${e.wdh?` <span class="badge">↻ wiederkehrend</span>`:""}</div>
      <div class="small muted">${esc(e.kal)}${e.label?" · Label: "+esc(e.label):""}</div>
      ${e.ort?`<div><b>Ort:</b> ${esc(e.ort)} <a href="#" data-kmap="${esc(e.ort)}">Karte</a></div>`:""}
      ${e.url?`<div><b>Link:</b> <a href="#" data-kurl="${esc(e.url)}">${esc(e.url)}</a></div>`:""}
      ${e.notiz?`<div class="hl" style="white-space:pre-wrap">${link(e.notiz)}</div>`:""}
      <div class="small muted">Termine bitte in TimeTree ändern – beim nächsten Abruf ist die Änderung hier.</div></div>`, [{label:"Schließen"}]);
    const mb = $$(".mb").pop();
    $$("[data-kurl]", mb).forEach(a_ => a_.onclick = ev => { ev.preventDefault(); api("/api/kal/url", {url:a_.dataset.kurl}); });
    $$("[data-kmap]", mb).forEach(a_ => a_.onclick = ev => { ev.preventDefault(); api("/api/kal/url", {url:"https://www.google.com/maps/search/" + encodeURIComponent(a_.dataset.kmap)}); });
  }
  async function dayDialog(k){
    const r = await api(`/api/kal/events?von=${k}&bis=${isoLocal(addD(pd(k),1))}&q=${encodeURIComponent(st.q)}`);
    modal(fmtD(k), `<div class="fr">${(r.events||[]).map(e => `<div class="kev big" data-kev='${esc(JSON.stringify(e))}' style="--c:${esc(e.farbe)}">${e.all_day?"ganztägig":hm(e.start)+"–"+hm(e.end)} · <b>${esc(e.title)}</b>${e.ort?` <span class="small">· ${esc(e.ort)}</span>`:""}</div>`).join("") || `<div class="muted">Keine Termine.</div>`}</div>`, [{label:"Schließen"}]);
    const mb = $$(".mb").pop(); $$("[data-kev]", mb).forEach(x_ => x_.onclick = () => evDialog(JSON.parse(x_.dataset.kev)));
  }
  async function setDialog(info){
    await modal("TimeTree", `<div class="fr">${tTForm(info)}
      <div class="small"><b>Kalender im Programm:</b><br>${(info.kalender||[]).map(c => `<div class="row" style="align-items:center;gap:8px;margin-top:6px"><input type="color" value="${esc(c.farbe||"#0a84ff")}" data-kcol="${esc(c.id)}" style="width:34px;height:26px;border:0;background:none;flex:none">
        <span style="flex:1">${esc(c.name)} <span class="muted">(${c.quelle==="ics"?".ics":c.quelle==="abo"?"Abo (Link)":"TimeTree"}, ${nde(c.anzahl||0,0)} Termine)</span></span>${c.quelle==="ics"?`<button class="btn sm ghost" data-kdel="${esc(c.id)}" style="color:var(--bad)">Entfernen</button>`:""}</div>`).join("") || "noch keine"}</div></div>`,
      [{label:"Abmelden", cls:"danger", onClick: async () => { await api("/api/kal/settings", {abmelden:true}); toast("TimeTree-Passwort gelöscht – die heruntergeladenen Termine bleiben"); EXT.views.kalender(); }},
       {label:"Abbrechen"},
       {label:"Speichern", cls:"pri", onClick: async mb => { await saveForm(mb); EXT.views.kalender(); }}]);
  }
  async function saveForm(root){
    const d = {email:$("#kmail", root).value.trim(), auto:+$("#kauto", root).value}; const pw = $("#kpw", root).value; if (pw) d.password = pw;
    await api("/api/kal/settings", d); $("#kpw", root).value = "";
  }
  async function doSync(){
    toast("TimeTree wird abgerufen …");
    const p_ = api("/api/kal/sync", {});
    setTimeout(() => { if (view === "kalender") EXT.views.kalender(); }, 400);
    const r = await p_;
    if (r && r.ok) toast(`TimeTree: ${r.kalender} Kalender, ${nde(r.termine,0)} Termine heruntergeladen`);
    else if (r && r.error) toast(r.error, true);
    await reload(); if (view === "kalender") EXT.views.kalender();
  }
  async function importIcs(files){
    for (const f of files) { const r = await upload("/api/upload/ics", f); if (r && r.ok) toast(`„${r.kalender}“: ${nde(r.termine,0)} Termine eingelesen`); else if (r && r.error) toast(r.error, true); }
    await reload(); EXT.views.kalender();
  }

  function bind(info){
    const on = (id, fn) => { const e = $("#" + id); if (e) e.onclick = fn; };
    on("ksync", doSync);
    on("kset", () => setDialog(info));
    on("kics", () => pickFiles(".ics", importIcs));
    on("kics2", () => pickFiles(".ics", importIcs));
    on("kexp", async () => { const r = await api("/api/kal/export", {}); if (r.ok) toast("Gespeichert: " + r.path.split(/[\\/]/).pop()); });
    on("kconnect", async () => { const root = $("#main"); if (!$("#kmail", root).value.trim()) { toast("Bitte die E-Mail eintragen", true); return; }
      if (!$("#kpw", root).value && !info.has_pw) { toast("Bitte das Passwort eintragen", true); return; }
      await saveForm(root); doSync(); });
    const dz = $("#kdz"); if (dz) { dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); }; dz.ondragleave = () => dz.classList.remove("over");
      dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); importIcs([...e.dataTransfer.files].filter(f => /\.ics$/i.test(f.name))); }; }
    const step = n => { const d = pd(st.datum);
      if (st.ansicht === "woche") st.datum = isoLocal(addD(d, 7 * n)); else st.datum = isoLocal(new Date(d.getFullYear(), d.getMonth() + n, 1)); save(); EXT.views.kalender(); };
    on("kprev", () => step(-1)); on("knext", () => step(1));
    on("khome", () => { st.datum = todayIso(); save(); EXT.views.kalender(); });
    $$("[data-ka]").forEach(c => c.onclick = () => { st.ansicht = c.dataset.ka; save(); EXT.views.kalender(); });
    $$("[data-kc]").forEach(c => c.onclick = async () => { await api("/api/kal/cal", {id:c.dataset.kc, aktiv:!c.classList.contains("on")}); EXT.views.kalender(); });
    const q_ = $("#kq"); if (q_) q_.oninput = e => { st.q = e.target.value; clearTimeout(window._kalT); window._kalT = setTimeout(() => { if (!$("#kq")) return;
      const p = e.target.selectionStart; Promise.resolve(EXT.views.kalender()).then(() => { const n = $("#kq"); if (n) { n.focus(); try { n.setSelectionRange(p, p); } catch (e2) {} } }); }, 250); };
    $$("[data-kev]").forEach(x_ => x_.onclick = ev => { ev.stopPropagation(); evDialog(JSON.parse(x_.dataset.kev)); });
    $$("[data-kday]").forEach(x_ => x_.onclick = ev => { ev.stopPropagation(); dayDialog(x_.dataset.kday); });
    $$(".kday[data-kd]").forEach(x_ => x_.onclick = () => dayDialog(x_.dataset.kd));
    const wb = $("#kwbody"); if (wb && !wb.dataset.sc) { wb.dataset.sc = 1; wb.scrollTop = 7 * 42; }
  }
  // colour / remove inside the TimeTree dialog
  document.addEventListener("change", async e => { const t = e.target; if (t && t.dataset && t.dataset.kcol) { await api("/api/kal/cal", {id:t.dataset.kcol, farbe:t.value}); if (view === "kalender") EXT.views.kalender(); } });
  document.addEventListener("click", async e => { const t = e.target.closest && e.target.closest("[data-kdel]"); if (!t) return; e.preventDefault();
    await api("/api/kal/cal", {id:t.dataset.kdel, loeschen:true}); t.closest(".row").remove(); toast("Kalender entfernt"); if (view === "kalender") EXT.views.kalender(); });

  // v2.0.8: shared with the configurable dashboard (m61)
  window.kalEvDialog = evDialog; window.kalDayDialog = dayDialog; window.kalPill = pill; window.kalByDay = byDay;

  const css = document.createElement("style");
  css.textContent = `.kgrid{display:grid;grid-template-columns:repeat(7,1fr)}
    .khead>div{padding:8px 10px;font:600 12px var(--disp);color:var(--mute);text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--line)}
    .kday{min-height:112px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);padding:4px 5px;cursor:pointer;overflow:hidden}
    .kday:nth-child(7n){border-right:0} .kday.we{background:var(--panel2)} .kday.other{opacity:.45}
    .kday.today .kdn{background:var(--acc);color:#fff;border-radius:10px;padding:0 7px;display:inline-block}
    .kdn{font:600 12.5px var(--disp);margin:2px 2px 4px}
    .kev{font-size:12px;line-height:1.35;padding:2px 6px;margin-bottom:2px;border-radius:5px;border-left:3px solid var(--c);background:color-mix(in srgb, var(--c) 13%, transparent);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
    .kev.ad{background:var(--c);color:#fff;border-left-color:transparent} .kev b{font-weight:600}
    .kev.big{white-space:normal;font-size:13.5px;padding:7px 10px}
    .kmore{font-size:11.5px;color:var(--acc);padding:0 6px;cursor:pointer}
    .kdot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:0}
    .kchip i{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--c);margin-right:6px}
    .kchip:not(.on){opacity:.5;text-decoration:line-through} .kchip.on{background:var(--panel);color:var(--ink);border-color:var(--c)}
    .kweek .kwh{display:grid;grid-template-columns:56px repeat(7,1fr);border-bottom:1px solid var(--line)}
    .kweek .kwh>div{padding:6px 8px;font-size:12.5px} .kweek .kwh>div.today{color:var(--acc)}
    .kweek .kwad>div{min-height:28px;border-left:1px solid var(--line)}
    .kwbody{display:grid;grid-template-columns:56px repeat(7,1fr);max-height:calc(100vh - 330px);overflow:auto;position:relative}
    .kwtimes>div{font-size:11px;color:var(--mute);padding:0 6px;text-align:right;box-sizing:border-box}
    .kwcol{position:relative;border-left:1px solid var(--line)} .kwcol.today{background:var(--accsoft)}
    .kwline{position:absolute;left:0;right:0;border-top:1px solid var(--line);opacity:.6}
    .kwev{position:absolute;white-space:normal;box-sizing:border-box;margin:0;z-index:1;font-size:11.5px}
    tr.ktoday td{background:var(--accsoft)}`;
  document.head.appendChild(css);
})();
