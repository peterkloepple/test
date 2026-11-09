// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Seite Uebersicht (Dashboard)
// v3.6.1: Kontostand auf der Uebersicht verdeckt - erst ein Klick zeigt ihn (bis die Seite verlassen wird).
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- dashboard ----------
// v3.6.1: hide the bank balance on the overview until it is clicked (nobody reads it over your shoulder).
// kontoMask(html) -> covered placeholder; the real html stays in KMASK (not in the page) until revealed.
// One click reveals all covered amounts of the page; a click on a shown amount covers them again.
// Leaving the overview covers them again (go() resets KONTO_SHOW).
let KONTO_SHOW = false;
const KMASK = [];
function kontoMask(html, big){
  if (KONTO_SHOW) return `<span class="kmask on" data-kmask="${KMASK.push(html) - 1}" title="Klicken zum Verbergen" style="cursor:pointer">${html}</span>`;
  return `<span class="kmask" data-kmask="${KMASK.push(html) - 1}" title="Klicken zum Anzeigen" style="cursor:pointer;display:inline-flex;align-items:center;gap:6px;color:var(--mut,#8a8799)">`
    + `<span style="letter-spacing:${big ? "3px" : "2px"}">••••••</span><svg viewBox="0 0 24 24" width="${big ? 18 : 14}" height="${big ? 18 : 14}" fill="none" stroke="currentColor" stroke-width="2">${IC.eye}</svg></span>`;
}
function kontoMaskToggle(){
  KONTO_SHOW = !KONTO_SHOW;
  $$("[data-kmask]").forEach(e => {
    const h = KMASK[+e.dataset.kmask];
    if (KONTO_SHOW) { e.className = "kmask on"; e.title = "Klicken zum Verbergen"; e.removeAttribute("style"); e.style.cursor = "pointer"; e.innerHTML = h; }
    else { const t = document.createElement("span"); t.innerHTML = kontoMask(h, e.closest(".kmaskbig") !== null); e.replaceWith(t.firstChild); }
  });
}
document.addEventListener("click", ev => {
  const m = ev.target && ev.target.closest && ev.target.closest("[data-kmask]");
  if (!m) return;
  ev.preventDefault(); ev.stopPropagation(); kontoMaskToggle();
}, true);
function kontoSpark(v){
  if (!v || v.length < 2) return "";
  const vals = v.map(r=>r.saldo), mn = Math.min(...vals, 0), mx = Math.max(...vals, 0), W = 300, H = 46, rg = (mx-mn)||1;
  const pts = vals.map((x,i)=>`${(i*(W/(vals.length-1))).toFixed(1)},${(H-4-(x-mn)/rg*(H-8)).toFixed(1)}`).join(" ");
  const y0 = (H-4-(0-mn)/rg*(H-8)).toFixed(1);
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:46px;margin-top:8px"><line x1="0" x2="${W}" y1="${y0}" y2="${y0}" stroke="var(--line2)" stroke-dasharray="3 3"/><polyline points="${pts}" fill="none" stroke="var(--acc)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}
function kontoCard(hide){
  const k = S.konto;
  const M = (h, big) => hide ? kontoMask(h, big) : h;
  if (!k) return `<div class="card"><div class="hd"><h3>Kontostand</h3><div class="act"><button class="btn sm" id="kset">Eintragen</button></div></div>
    <div class="bd small muted">Noch kein Kontostand bekannt. Er wird beim Einlesen eines Kontoauszugs (PDF, CSV oder Excel) automatisch übernommen – oder trag ihn von Hand ein.</div></div>`;
  const alt = Math.round((new Date() - new Date(k.datum)) / 864e5);
  return `<div class="card"><div class="hd"><h3>Kontostand</h3><div class="act"><button class="btn sm ghost" id="kset">Eintragen</button><button class="btn sm ghost" data-go="bank">Kontoauszug</button></div></div>
    <div class="bd"><div style="font:700 28px var(--disp);color:var(--ink)" class="num kmaskbig">${M(`<span style="color:${k.saldo<0?"var(--bad)":"var(--ink)"}">${eur(k.saldo)}</span>`, true)}</div>
    <div class="small muted">Stand ${dde(k.datum)} · ${esc(k.quelle||"")}${alt>14?` · <span style="color:var(--warn)">${alt} Tage alt – neuen Auszug einlesen</span>`:""}</div>
    ${k.nachher_n?`<div class="small" style="margin-top:4px">Seitdem ${k.nachher_n} Buchung(en) eingelesen: ${M(eur(k.nachher))} → ca. <b>${M(eur(k.geschaetzt))}</b></div>`:""}
    ${hide ? M(kontoSpark(k.verlauf)) : kontoSpark(k.verlauf)}</div></div>`;
}
async function kontoDialog(){
  const k = S.konto || {};
  await modal("Kontostand eintragen", `<div class="fr"><div class="row"><label class="f">Kontostand €<input class="in num" id="ksal" value="${k.saldo!=null?nde(k.saldo):""}" placeholder="z. B. 2.345,67"></label>
    <label class="f">Stand am<input type="date" class="in" id="kdat" value="${todayIso()}"></label></div>
    <div class="small muted">Wird automatisch aktualisiert, sobald du einen Kontoauszug im Bank-Abgleich einliest.</div>
    ${(k.verlauf||[]).length?`<div class="small" style="margin-top:6px"><b>Verlauf</b>${k.verlauf.slice().reverse().map(v=>`<div class="row" style="align-items:center"><span style="flex:1">${dde(v.datum)} · ${esc(v.quelle||"")}</span><b class="num" style="flex:none">${eur(v.saldo)}</b><button class="btn sm ghost" style="flex:none" data-kdel="${v.id}">✕</button></div>`).join("")}</div>`:""}</div>`,
    [{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:1, onClick: async mb => { const v = $("#ksal",mb).value.trim(); if (!v) { toast("Betrag eintragen", true); return false; }
      await api("/api/kontostand/save", {saldo:pnum(v), datum:$("#kdat",mb).value}); }}],
    false, mb => $$("[data-kdel]", mb).forEach(b => b.onclick = async () => { await api("/api/kontostand/delete", {id:+b.dataset.kdel}); b.closest(".row").remove(); }));
  await reload(); if (view === "dash") vDash(); else if (view === "bank") vBank();
}
async function vDash(){
  if (window.dashRender && !window.DASH_CLASSIC) return dashRender();   // v2.0.8: configurable dashboard (ui/m61_dashboard.js)
  const y = thisYear;
  const [st, tx] = await Promise.all([api("/api/stats?year="+y), api("/api/tax?year="+y)]);
  const open = S.invoices.filter(i=>i.typ==="rechnung"&&i.status==="offen");
  const drafts = S.invoices.filter(i=>i.status==="entwurf");
  const offers = S.invoices.filter(i=>i.typ==="angebot"&&i.status==="offen");
  const maxM = Math.max(1, ...st.months.map(m=>Math.max(m.umsatz,m.ausgaben)));
  const kuPct = Math.min(100, tx.umsatz/1000), vjPct = Math.min(100, tx.umsatz_vj/250);
  const alerts = [];
  if (S.pending) alerts.push(`<div class="alert warn" data-go="beleg">${ic("alert")}<b>${S.pending} Beleg(e) aus dem Eingangsordner</b> warten auf deine Prüfung – der Assistent war sich nicht sicher</div>`);
  if (drafts.length) alerts.push(`<div class="alert acc" data-go-inv="draft">${ic("inv")}<b>${drafts.length} Entwurf/Entwürfe</b> aus Abos, Wartung oder Unterricht warten aufs Fertigstellen</div>`);
  if (S.overdue.length) alerts.push(`<div class="alert bad" data-go-inv="mahn">${ic("alert")}<b>${S.overdue.length} überfällige Rechnung(en)</b> · ${eur(S.overdue.reduce((a,i)=>a+i.summe,0))} – Mahnwesen öffnen</div>`);
  S.vertraege_due.forEach(v => alerts.push(`<div class="alert warn" data-go="abo">${ic("wrench")}<b>Wartung fällig:</b> ${esc(v.name)} am ${dde(v.naechste)} (${v.tage>=0?"in "+v.tage+" Tagen":"seit "+(-v.tage)+" Tagen"})</div>`));
  S.cert_warn.slice(0,5).forEach(w => alerts.push(`<div class="alert ${w.tage<0?"bad":"warn"}" data-go="certs">${ic("award")}<b>${esc(w.art)}:</b> ${esc(w.bezeichnung)}${w.person?" · "+esc(w.person):""} – ${dde(w.datum)}</div>`));
  if (offers.length) alerts.push(`<div class="alert" data-go-inv="angebot">${ic("inv")}<b>${offers.length} offene(s) Angebot(e)</b> · ${eur(offers.reduce((a,i)=>a+i.summe,0))}</div>`);
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Hallo " + esc((S.settings.inhaber||"").split(" ")[0]), new Date().toLocaleDateString("de-DE",{weekday:"long",day:"numeric",month:"long",year:"numeric"}),
      expButtons("gesamt", {}, false) + `<button class="btn" data-go="bank">${ic("bank")} Kontoauszug</button><button class="btn" data-go="beleg">${ic("up")} Beleg einfügen</button><button class="btn pri" data-go="new">${ic("plus")} Neue Rechnung</button>`)}
    ${alerts.length?`<div class="alerts">${alerts.join("")}</div>`:""}
    <div id="dashext"></div>
    <div class="grid g6" style="margin-bottom:16px">
      <div class="card kpi acc"><div class="l">Umsatz ${y}</div><div class="v">${eur(st.total)}</div><div class="s">${st.anzahl} Rechnungen</div></div>
      <div class="card kpi"><div class="l">Zahlungseingang</div><div class="v">${eur(tx.euer.einnahmen)}</div><div class="s">nach Zuflussprinzip</div></div>
      <div class="card kpi"><div class="l">Offen</div><div class="v" style="color:${open.length?"var(--warn)":"inherit"}">${eur(open.reduce((a,i)=>a+i.summe,0))}</div><div class="s">${open.length} Rechnung(en)</div></div>
      <div class="card kpi"><div class="l">Ausgaben</div><div class="v">${eur(tx.euer.ausgaben)}</div><div class="s">inkl. AfA & Fahrten</div></div>
      <div class="card kpi"><div class="l">Gewinn</div><div class="v">${eur(tx.euer.gewinn)}</div><div class="s">EÜR vorläufig</div></div>
      <div class="card kpi"><div class="l">Steuer-Rücklage</div><div class="v">${eur(Math.max(0,tx.anteil_selbst))}</div><div class="s">Anteil Selbstständigkeit</div></div>
    </div>
    <div class="grid" style="grid-template-columns:1.6fr 1fr;margin-bottom:16px">
      <div class="card"><div class="hd"><h3>Monatsverlauf ${y}</h3><div class="act legend"><span><i style="background:var(--acc)"></i>Umsatz</span><span><i style="background:#e6a1a0"></i>Ausgaben</span></div></div>
        <div class="bd">${monthChart(st.months, maxM)}</div></div>
      <div style="display:flex;flex-direction:column;gap:16px">${kontoCard(true)}
      <div class="card"><div class="hd"><h3>Kleinunternehmer-Grenzen</h3></div><div class="bd">
        <div class="small muted">Umsatz ${y} · Grenze 100.000 €</div>
        <div class="row" style="align-items:center;margin:4px 0 14px"><div class="prog ${kuPct>80?"w":""}" style="flex:3"><div style="width:${kuPct}%"></div></div><b class="num" style="flex:none">${eur0(tx.umsatz)}</b></div>
        <div class="small muted">Umsatz ${y-1} · Grenze 25.000 €</div>
        <div class="row" style="align-items:center;margin:4px 0 14px"><div class="prog ${vjPct>80?"w":""}" style="flex:3"><div style="width:${vjPct}%"></div></div><b class="num" style="flex:none">${eur0(tx.umsatz_vj)}</b></div>
        <span class="badge ${tx.ku_ok?"ok":"bad"}"><span class="dot"></span>${tx.ku_ok?"§19 UStG weiterhin möglich":"Grenze überschritten – prüfen!"}</span>
        <hr class="s"><div class="kv"><span class="sub">Geschätzte ESt gesamt ${y}</span><span class="r">${eur(tx.calc.gesamt)}</span>
        <span class="sub">${tx.differenz>=0?"Voraussichtl. Nachzahlung":"Voraussichtl. Erstattung"}</span><span class="r" style="color:${tx.differenz>=0?"var(--bad)":"var(--ok)"}">${eur(Math.abs(tx.differenz))}</span></div>
      </div></div></div>
    </div>
    <div class="grid g3">
      <div class="card"><div class="hd"><h3>Offene Rechnungen</h3></div>${open.length?`<table class="t"><tbody>${open.slice(0,8).map(i=>`<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b><div class="small muted">${esc(invName(i))}</div></td><td>${statusBadge(i)}</td><td class="r num"><b>${eur(i.summe)}</b></td></tr>`).join("")}</tbody></table>`:`<div class="empty">Alles bezahlt.</div>`}</div>
      <div class="card"><div class="hd"><h3>Letzte Dokumente</h3><div class="act"><button class="btn sm ghost" data-go="inv">Alle</button></div></div><table class="t"><tbody>${S.invoices.slice(0,8).map(i=>`<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b><div class="small muted">${esc(DOCT[i.typ]||"")} · ${esc(invName(i))}</div></td><td>${statusBadge(i)}</td><td class="r num">${eur(i.summe)}</td></tr>`).join("")}</tbody></table></div>
      <div class="card"><div class="hd"><h3>Aktive Projekte</h3><div class="act"><button class="btn sm ghost" data-go="proj">Alle</button></div></div>${S.projects.filter(p=>p.status==="aktiv").slice(0,8).map(p=>`<div class="list"><div class="it" data-proj="${p.id}"><div class="av" style="background:${BEREICH_COL[p.bereich]||"#888"}22;color:${BEREICH_COL[p.bereich]||"#888"}">${esc(initials(p.bereich))}</div><div style="min-width:0"><b>${esc(p.name)}</b><div class="small muted">${esc(p.nr)} · ${p.nfiles} Dateien${p.offen_pos?` · ${p.offen_pos} offene Pos.`:""}</div></div></div></div>`).join("") || `<div class="empty">Noch keine Projekte.<br><button class="btn sm" style="margin-top:8px" data-go="proj">Projekt anlegen</button></div>`}</div>
    </div></div>`;
  extRun(EXT.dash, $("#dashext"));
  bindCommon();
  const ks_ = $("#kset"); if (ks_) ks_.onclick = kontoDialog;
  $$("[data-go-inv]").forEach(a => a.onclick = () => { invTab = a.dataset.goInv; go("inv"); });
}
function monthChart(months, max, h=200){
  const W = 760, pad = 34, bw = (W-pad)/12;
  const ticks = [0, .25, .5, .75, 1].map(t => t*max);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${h+24}" width="100%" style="display:block;max-height:${h+60}px">`;
  ticks.forEach(t => { const y = h - (t/max)*h + 4; s += `<line x1="${pad}" x2="${W}" y1="${y}" y2="${y}" stroke="#eeebf4"/><text x="${pad-6}" y="${y+4}" text-anchor="end">${t>=1000?Math.round(t/100)/10+"k":Math.round(t)}</text>`; });
  months.forEach((m,i) => {
    const x = pad + i*bw + bw*.18, w = bw*.3;
    const h1 = (m.umsatz/max)*h, h2 = (m.ausgaben/max)*h;
    s += `<rect x="${x}" y="${h-h1+4}" width="${w}" height="${Math.max(0,h1)}" rx="3" fill="var(--acc)"><title>${MONL[i]}: Umsatz ${eur(m.umsatz)}</title></rect>`;
    s += `<rect x="${x+w+3}" y="${h-h2+4}" width="${w}" height="${Math.max(0,h2)}" rx="3" fill="#e6a1a0"><title>${MONL[i]}: Ausgaben ${eur(m.ausgaben)}</title></rect>`;
    s += `<text x="${pad+i*bw+bw/2}" y="${h+20}" text-anchor="middle">${MON[i]}</text>`;
  });
  return s + `</svg>`;
}
function statusBadge(i){
  const b = (cls, t) => `<span class="badge ${cls}"><span class="dot"></span>${t}</span>`;
  if (i.status === "entwurf") return b("acc", "Entwurf");
  if (i.typ === "angebot") return i.status==="angenommen"?b("ok","angenommen"):i.status==="abgelehnt"?b("","abgelehnt"):(i.gueltig_bis&&i.gueltig_bis<todayIso()?b("bad","abgelaufen"):b("warn","offen"));
  if (i.typ === "auftrag") return i.status==="erledigt"?b("ok","abgerechnet"):b("warn","in Arbeit");
  if (i.typ === "storno") return i.status==="offen"?b("warn","Erstattung offen"):b("", "Storno");
  if (i.storno_von) return b("", "storniert");
  if (i.status === "bezahlt") return b("ok","bezahlt");
  if (i.status === "storniert") return b("","storniert");
  const over = isOverdue(i);
  return b(over?"bad":"warn", over?(i.mahnstufe?`${i.mahnstufe}. Mahnstufe`:"überfällig"):"offen");
}
function bindCommon(root=document){
  $$("[data-go]", root).forEach(b => { if (!b.closest("#side, .lzone, .flwin.menu, #laybar")) b.onclick = () => go(b.dataset.go); });
  $$("[data-inv]", root).forEach(r => r.onclick = () => openInvoice(+r.dataset.inv));
  $$("[data-proj]", root).forEach(r => r.onclick = () => go("project", +r.dataset.proj));
}

