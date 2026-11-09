// Pfeiffer-Audio Rechnung v3.2.0 - Oberflaeche Kern: Statistik, Jahresabrechnung & Steuer
// v3.6.1: Statistik aufraeumen - Knopf "Aufraeumen" (Doppelte, 0-Euro-Eintraege) und Eintraege markieren + loeschen.
// (bis v3.1 Teil des Skripts in ui.html; Reihenfolge kern_01..kern_13 = bisherige Reihenfolge)
// Autor: T. Pfeiffer
// ---------- stats ----------
let stYear = thisYear;
let stTab = "ueb";
// v1.6.2: Unterrubriken Rechnungen / Einnahmen / Ausgaben
const stF = {year:String(thisYear), group:{re:"jahr", ein:"monat", aus:"kategorie", geh:"monat"}, status:"", ckey:"", kat:"", art:"", q:""};
const stOpen = {};
let stData = null, stDataYear = null;
const ST_GROUPS = {
  re:[["jahr","Jahr"],["quartal","Quartal"],["monat","Monat"],["kunde","Kunde"],["projekt","Projekt"],["status","Status"]],
  ein:[["jahr","Jahr"],["quartal","Quartal"],["monat","Monat"],["kunde","Kunde / Partner"],["art","Art"]],
  aus:[["kategorie","Kategorie"],["lieferant","Lieferant"],["jahr","Jahr"],["quartal","Quartal"],["monat","Monat"],["projekt","Projekt"]],
  geh:[["monat","Monat"],["quartal","Quartal"],["jahr","Jahr"],["arbeitgeber","Arbeitgeber"],["art","Art"]]};
const ST_STATUS_TXT = {offen:"offen", bezahlt:"bezahlt", storniert:"storniert"};

async function vStats(){
  const tabs = [["ueb","Übersicht"],["re","Rechnungen"],["ein","Einnahmen"],["aus","Ausgaben"],["geh","Gehalt (Job)"]];
  if (stTab === "ueb") return vStatsOverview(tabs);
  return vStatsDetail(tabs);
}
function stTabsHtml(tabs, cnt){
  return `<div class="tabs">${tabs.map(([k,l])=>`<div class="tab ${stTab===k?"on":""}" data-stt="${k}">${l}${cnt&&cnt[k]!=null?`<span class="cnt">${cnt[k]}</span>`:""}</div>`).join("")}</div>`;
}
function bindStTabs(){
  $$("[data-stt]").forEach(t => t.onclick = () => {
    if (stTab === "ueb" && t.dataset.stt !== "ueb") stF.year = String(stYear);
    if (stTab !== "ueb" && t.dataset.stt === "ueb" && stF.year) stYear = +stF.year;
    stTab = t.dataset.stt; stF.status = ""; stF.ckey = ""; stF.kat = ""; stF.art = ""; stF.q = ""; vStats(); });
}

async function vStatsOverview(tabs){
  const st = await api("/api/stats?year="+stYear);
  const maxM = Math.max(1, ...st.months.map(m=>Math.max(m.umsatz,m.ausgaben)));
  const maxK = Math.max(1, ...st.kunden.map(k=>k.summe)), maxL = Math.max(1, ...st.leistungen.map(l=>l.summe));
  const maxY = Math.max(1, ...st.jahre.map(j=>Math.max(j.umsatz, j.ausgaben)));
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Statistik", `${st.anzahl} Rechnungen · ${eur(st.total)} Umsatz in ${stYear}`, yearSel("sty", stYear) + expButtons("stats", () => ({year:stYear})) + `<button class="btn" id="stclean">🧹 Aufräumen</button><button class="btn pri" id="jber">${ic("pdf")} Jahresbericht PDF</button>`)}
    ${stTabsHtml(tabs)}
    <div class="card" style="margin-bottom:16px"><div class="hd"><h3>Monate ${stYear}</h3><div class="act legend"><span><i style="background:var(--acc)"></i>Umsatz</span><span><i style="background:#e6a1a0"></i>Ausgaben</span></div></div><div class="bd">${monthChart(st.months, maxM, 230)}</div></div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><div class="hd"><h3>Kunden</h3><div class="act small muted">${st.kunden.length} Kunden</div></div><div class="bd">${st.kunden.map(k=>`<div class="hbar"><span class="lb" title="${esc(k.name)}">${esc(k.name)}</span><div class="tr"><div class="fl" style="width:${100*k.summe/maxK}%"></div></div><span class="r num"><b>${eur(k.summe)}</b> <span class="muted small">${nde(k.anteil,0)}%</span></span></div>`).join("")||`<div class="muted">–</div>`}</div></div>
      <div class="card"><div class="hd"><h3>Leistungen / Bausteine</h3></div><div class="bd">${st.leistungen.map(l=>`<div class="hbar"><span class="lb" title="${esc(l.name)}">${esc(l.name)} <span class="muted small">${nde(l.menge, Number.isInteger(l.menge)?0:2)}×</span></span><div class="tr"><div class="fl" style="width:${100*l.summe/maxL}%;background:var(--gold)"></div></div><span class="r num"><b>${eur(l.summe)}</b> <span class="muted small">${nde(l.anteil,0)}%</span></span></div>`).join("")||`<div class="muted">–</div>`}</div></div>
    </div>
    <div class="grid g2">
      <div class="card"><div class="hd"><h3>Jahresvergleich</h3><div class="act small muted">Jahr anklicken = alle Rechnungen</div></div><div class="bd"><table class="t"><thead><tr><th>Jahr</th><th class="r">Umsatz</th><th class="r">Einnahmen</th><th class="r">Ausgaben</th><th class="r">Gewinn</th><th style="width:30%"></th></tr></thead><tbody>${st.jahre.slice().reverse().map(j=>`<tr class="click" data-sty2="${j.year}"><td><b>${j.year}</b></td><td class="r num">${eur(j.umsatz)}</td><td class="r num">${eur(j.einnahmen)}</td><td class="r num">${eur(j.ausgaben)}</td><td class="r num"><b>${eur(j.gewinn)}</b></td><td><div class="prog"><div style="width:${100*j.umsatz/maxY}%;background:var(--acc)"></div></div></td></tr>`).join("")}</tbody></table></div></div>
      <div class="card"><div class="hd"><h3>Projekte & Bereiche</h3></div><div class="bd">${Object.keys(st.bereiche).length?Object.entries(st.bereiche).map(([b,v])=>`<div class="hbar"><span class="lb"><span class="dot" style="color:${BEREICH_COL[b]||"#888"}"></span> ${esc(b)}</span><div class="tr"><div class="fl" style="width:${100*v/Math.max(...Object.values(st.bereiche))}%;background:${BEREICH_COL[b]||"#888"}"></div></div><span class="r num">${eur(v)}</span></div>`).join("")+`<hr class="s">`+st.projekte.map(p=>`<div class="list"><div class="it" data-proj="${p.id}" style="padding:6px 0"><b style="flex:1">${esc(p.name)}</b><span class="muted small">${p.anzahl} Re.</span><span class="num"><b>${eur(p.summe)}</b></span></div></div>`).join(""):`<div class="muted">Noch keine Projektrechnungen in ${stYear}.</div>`}</div></div>
    </div></div>`;
  bindCommon(); bindStTabs();
  $$("#stclean,#sdclean2").forEach(b => b.onclick = () => stClean());
  $$("[data-sty2]").forEach(r => r.onclick = () => { stTab = "re"; stF.year = r.dataset.sty2; stF.group.re = "monat"; stF.status = ""; stF.ckey = ""; stF.q = ""; vStats(); });
  $("#sty").onchange = e => { stYear = +e.target.value; vStats(); };
  $("#jber").onclick = () => jahresbericht(stYear);
}

function stYearSel(){
  const ys = new Set([thisYear]);
  (stData && stData.years || []).forEach(y => ys.add(+y));
  S.invoices.forEach(i => i.datum && ys.add(+i.datum.slice(0,4)));
  return `<select class="in" id="sdy" style="width:auto"><option value="" ${!stF.year?"selected":""}>Alle Jahre</option>${[...ys].sort((a,b)=>b-a).map(v=>`<option value="${v}" ${String(v)===stF.year?"selected":""}>${v}</option>`).join("")}</select>`;
}
function stGroupKey(r, g, kind){
  if (g === "monat") return [`${r.jahr}-${String(r.monat).padStart(2,"0")}`, `${MONL[r.monat-1]} ${r.jahr}`];
  if (g === "quartal") { const q_ = Math.floor((r.monat-1)/3)+1; return [`${r.jahr}-Q${q_}`, `Q${q_} ${r.jahr}`]; }
  if (g === "kunde") { const n = kind==="re" ? r.kunde : r.partner; return [(n||"").toLowerCase(), n || "(ohne Name)"]; }
  if (g === "lieferant") return [(r.partner||"").toLowerCase(), r.partner || "(ohne Lieferant)"];
  if (g === "arbeitgeber") return [(r.partner||"").toLowerCase(), r.partner || "(ohne Arbeitgeber)"];
  if (g === "kategorie") return [r.kategorie, r.kategorie];
  if (g === "projekt") return [r.projekt || "~", r.projekt || "(ohne Projekt)"];
  if (g === "status") return [r.status, ST_STATUS_TXT[r.status] || r.status];
  if (g === "art") return kind==="geh" ? [r.art, r.art==="jahr" ? "Lohnsteuerbescheinigungen" : "Monatsabrechnungen"] : [r.art, r.art==="rechnung" ? "Rechnungen" : "Sonstige Einnahmen"];
  return [String(r.jahr), String(r.jahr)];
}
function stFilter(rows, kind){
  const qq = stF.q.toLowerCase().trim();
  return rows.filter(r => {
    if (kind === "re") {
      if (stF.status === "ueberfaellig" ? !r.ueberfaellig : (stF.status && r.status !== stF.status)) return false;
      if (stF.ckey && r.ckey !== stF.ckey) return false;
      return !qq || `${r.nr} ${r.kunde} ${r.titel} ${r.projekt}`.toLowerCase().includes(qq);
    }
    if (kind === "ein") {
      if (stF.art && r.art !== stF.art) return false;
      if (stF.ckey && r.ckey !== stF.ckey) return false;
      return !qq || `${r.nr} ${r.partner} ${r.titel} ${r.kategorie}`.toLowerCase().includes(qq);
    }
    if (kind === "geh") {
      if (stF.art && r.art !== stF.art) return false;
      if (stF.ckey && r.partner.trim().toLowerCase() !== stF.ckey) return false;
      return !qq || `${r.partner} ${r.zeitraum} ${r.notiz}`.toLowerCase().includes(qq);
    }
    if (stF.kat && r.kategorie !== stF.kat) return false;
    if (stF.ckey && r.partner.trim().toLowerCase() !== stF.ckey) return false;
    return !qq || `${r.nr} ${r.partner} ${r.notiz} ${r.kategorie} ${r.projekt}`.toLowerCase().includes(qq);
  });
}

async function vStatsDetail(tabs){
  if (!stData || stDataYear !== stF.year) { stData = await api("/api/stats/detail?year="+stF.year); stDataYear = stF.year; }
  const kind = stTab, d = stData;
  const all = kind==="re" ? d.rechnungen : kind==="ein" ? d.einnahmen : kind==="geh" ? (d.gehalt||[]) : d.ausgaben;
  const rows = stFilter(all, kind);
  const g = stF.group[kind];
  const val = r => kind==="re" ? (r.zaehlt ? r.summe : 0) : kind==="ein" ? r.summe : kind==="geh" ? (r.zaehlt ? r.brutto : 0) : r.abzug;
  const yl = stF.year || "alle Jahre";
  // KPIs
  let kpi = "";
  if (kind === "re") {
    const cnt = rows.filter(r=>r.zaehlt && r.typ==="rechnung");
    const sum = rows.reduce((a,r)=>a+val(r),0);
    const paid = rows.filter(r=>r.status==="bezahlt"), open = rows.filter(r=>r.status==="offen"), over = rows.filter(r=>r.ueberfaellig);
    const td = paid.filter(r=>r.tage!=null);
    kpi = `<div class="card kpi"><div class="l">Rechnungen</div><div class="v">${cnt.length}</div><div class="s">${rows.filter(r=>r.status==="storniert").length} storniert · ${rows.filter(r=>r.typ==="storno").length} Storno-Belege</div></div>
      <div class="card kpi acc"><div class="l">Rechnungssumme</div><div class="v">${eur(sum)}</div><div class="s">Ø ${eur(cnt.length?sum/cnt.length:0)} je Rechnung</div></div>
      <div class="card kpi"><div class="l">Bezahlt</div><div class="v">${eur(paid.reduce((a,r)=>a+r.summe,0))}</div><div class="s">${paid.length} Rechnung(en) · Ø ${td.length?nde(td.reduce((a,r)=>a+r.tage,0)/td.length,0):"–"} Tage bis Zahlung</div></div>
      <div class="card kpi"><div class="l">Offen</div><div class="v" style="color:${over.length?"var(--bad)":"inherit"}">${eur(open.reduce((a,r)=>a+r.summe,0))}</div><div class="s">${open.length} offen${over.length?` · <b style="color:var(--bad)">${over.length} überfällig (${eur(over.reduce((a,r)=>a+r.summe,0))})</b>`:""}</div></div>`;
  } else if (kind === "ein") {
    const re_ = rows.filter(r=>r.art==="rechnung"), so = rows.filter(r=>r.art==="sonstige");
    const sum = rows.reduce((a,r)=>a+r.summe,0);
    const ms = new Set(rows.map(r=>r.jahr+"-"+r.monat)).size;
    kpi = `<div class="card kpi acc"><div class="l">Einnahmen gesamt</div><div class="v">${eur(sum)}</div><div class="s">Zufluss ${esc(yl)} (EÜR)</div></div>
      <div class="card kpi"><div class="l">aus Rechnungen</div><div class="v">${eur(re_.reduce((a,r)=>a+r.summe,0))}</div><div class="s">${re_.length} Zahlungseingänge${re_.some(r=>r.zehn_tage)?` · ${re_.filter(r=>r.zehn_tage).length}× 10-Tage-Regel`:""}</div></div>
      <div class="card kpi"><div class="l">Sonstige Einnahmen</div><div class="v">${eur(so.reduce((a,r)=>a+r.summe,0))}</div><div class="s">${so.length} Beleg(e)</div></div>
      <div class="card kpi"><div class="l">Ø pro Monat</div><div class="v">${eur(ms?sum/(stF.year?12:ms):0)}</div><div class="s">${stF.year?"über 12 Monate":`über ${ms} Monate mit Eingang`}</div></div>`;
  } else if (kind === "geh") {
    const z = rows.filter(r=>r.zaehlt), S_ = k => z.reduce((a,r)=>a+(r[k]||0),0);
    const br = S_("brutto"), nt = S_("netto"), stx = S_("steuer"), soz = S_("sozial");
    const ms = new Set(z.filter(r=>r.art==="monat").map(r=>r.jahr+"-"+r.monat)).size;
    kpi = `<div class="card kpi acc"><div class="l">Brutto</div><div class="v">${eur(br)}</div><div class="s">${esc(yl)} · ${new Set(rows.map(r=>r.partner.trim().toLowerCase())).size} Arbeitgeber</div></div>
      <div class="card kpi"><div class="l">Netto</div><div class="v">${eur(nt)}</div><div class="s">${ms?`Ø ${eur(nt/ms)} pro Monat`:"aus Jahreswerten"}</div></div>
      <div class="card kpi"><div class="l">Steuern</div><div class="v">${eur(stx)}</div><div class="s">LSt ${eur(S_("lst"))} · Soli ${eur(S_("soli"))} · KiSt ${eur(S_("kist"))}</div></div>
      <div class="card kpi"><div class="l">Sozialversicherung</div><div class="v">${eur(soz)}</div><div class="s">RV ${eur(S_("rv"))} · KV/PV ${eur(S_("kv")+S_("pv"))} · AV ${eur(S_("av"))}</div></div>`;
  } else {
    const sumB = rows.reduce((a,r)=>a+r.betrag,0), sumA = rows.reduce((a,r)=>a+r.abzug,0);
    const kats = {}; rows.forEach(r => kats[r.kategorie] = (kats[r.kategorie]||0) + r.abzug);
    const top = Object.entries(kats).sort((a,b)=>b[1]-a[1])[0];
    kpi = `<div class="card kpi acc"><div class="l">Ausgaben (abzugsfähig)</div><div class="v">${eur(sumA)}</div><div class="s">Belegsumme ${eur(sumB)}</div></div>
      <div class="card kpi"><div class="l">Belege</div><div class="v">${rows.length}</div><div class="s">${rows.filter(r=>r.anlage).length} davon Anlagen (über AfA)</div></div>
      <div class="card kpi"><div class="l">Lieferanten</div><div class="v">${new Set(rows.map(r=>r.partner.trim().toLowerCase())).size}</div><div class="s">${Object.keys(kats).length} Kategorien</div></div>
      <div class="card kpi"><div class="l">Größte Kategorie</div><div class="v" style="font-size:17px">${top?esc(top[0]):"–"}</div><div class="s">${top?eur(top[1]):""}</div></div>`;
  }
  // groups
  const grp = new Map();
  rows.forEach(r => { const [k, lb] = stGroupKey(r, g, kind); if (!grp.has(k)) grp.set(k, {k, lb, rows:[], sum:0}); const e = grp.get(k); e.rows.push(r); e.sum += val(r); });
  let groups = [...grp.values()];
  if (["jahr","monat","quartal"].includes(g)) groups.sort((a,b)=>a.k<b.k?1:-1); else groups.sort((a,b)=>b.sum-a.sum);
  const tot = groups.reduce((a,x)=>a+x.sum,0), maxG = Math.max(1, ...groups.map(x=>Math.abs(x.sum)));
  const okey = kind+"|"+g+"|"+stF.year;
  if (!stOpen[okey]) stOpen[okey] = new Set(groups.length <= 3 ? groups.map(x=>x.k) : groups.slice(0,1).map(x=>x.k));
  const opened = stOpen[okey];
  // filter controls
  const custOpts = () => { const m = new Map(); all.forEach(r => { const k = (kind==="aus"||kind==="geh") ? r.partner.trim().toLowerCase() : r.ckey; const n = kind==="re" ? r.kunde : r.partner; if (k && !m.has(k)) m.set(k, n || "(ohne Name)"); });
    return [...m.entries()].sort((a,b)=>a[1].localeCompare(b[1],"de")).map(([k,n])=>`<option value="${esc(k)}" ${stF.ckey===k?"selected":""}>${esc(n)}</option>`).join(""); };
  let filt = `<div class="seg" style="flex:none">${ST_GROUPS[kind].map(([k,l])=>`<button class="${g===k?"on":""}" data-sdg="${k}">${l}</button>`).join("")}</div>`;
  if (kind === "re") filt += `<div class="seg" style="flex:none">${[["","Alle"],["offen","Offen"],["ueberfaellig","Überfällig"],["bezahlt","Bezahlt"],["storniert","Storniert"]].map(([k,l])=>`<button class="${stF.status===k?"on":""}" data-sds="${k}">${l}</button>`).join("")}</div>`;
  if (kind === "geh") filt += `<div class="seg" style="flex:none">${[["","Alle"],["monat","Monatsabrechnungen"],["jahr","Lohnsteuerbescheinigung"]].map(([k,l])=>`<button class="${stF.art===k?"on":""}" data-sda="${k}">${l}</button>`).join("")}</div>`;
  if (kind === "ein") filt += `<div class="seg" style="flex:none">${[["","Alle"],["rechnung","Rechnungen"],["sonstige","Sonstige"]].map(([k,l])=>`<button class="${stF.art===k?"on":""}" data-sda="${k}">${l}</button>`).join("")}</div>`;
  if (kind === "aus") filt += `<select class="in" id="sdkat" style="width:auto;max-width:240px"><option value="">Alle Kategorien</option>${[...new Set(all.map(r=>r.kategorie))].sort((a,b)=>a.localeCompare(b,"de")).map(k=>`<option ${stF.kat===k?"selected":""}>${esc(k)}</option>`).join("")}</select>`;
  filt += `<select class="in" id="sdc" style="width:auto;max-width:240px"><option value="">${kind==="aus"?"Alle Lieferanten":kind==="geh"?"Alle Arbeitgeber":"Alle Kunden"}</option>${custOpts()}</select>`;
  filt += `<input class="in" id="sdq" placeholder="Suchen …" style="flex:1;min-width:160px" value="${esc(stF.q)}">`;
  // table columns
  const head = kind==="re" ? `<th>Nr.</th><th>Datum</th><th>Kunde</th><th>Titel</th><th>Status</th><th class="r">Zahltage</th><th class="r">Betrag</th>`
    : kind==="ein" ? `<th>Zufluss</th><th>Art</th><th>Nr.</th><th>Kunde / Partner</th><th>Titel / Notiz</th><th class="r">Betrag</th>`
    : kind==="geh" ? `<th>Datum</th><th>Arbeitgeber</th><th>Zeitraum</th><th class="r">Lohnsteuer</th><th class="r">Soli + KiSt</th><th class="r">Sozialvers.</th><th class="r">Netto</th><th class="r">Brutto</th>`
    : `<th>Datum</th><th>Lieferant</th><th>Beleg-Nr.</th><th>Kategorie</th><th>Notiz</th><th class="r">Betrag</th><th class="r">abzugsf.</th>`;
  const ncol = kind==="re" ? 7 : kind==="ein" ? 6 : kind==="geh" ? 8 : 7;
  const line = r => kind==="re"
    ? `<tr class="click" data-sdinv="${r.id}" style="${r.zaehlt?"":"opacity:.55"}"><td><b>${esc(r.nr)}</b>${r.typ==="storno"?` <span class="badge">Storno</span>`:""}</td><td class="num">${dde(r.datum)}</td><td>${esc(r.kunde)}</td><td class="muted">${esc(r.titel)}${r.projekt?`<div class="small">${esc(r.projekt)}</div>`:""}</td>
       <td>${r.ueberfaellig?`<span class="badge bad"><span class="dot"></span>überfällig</span>`:r.status==="bezahlt"?`<span class="badge ok"><span class="dot"></span>bezahlt ${dde(r.bezahlt_am)}</span>`:r.status==="storniert"?`<span class="badge">storniert</span>`:`<span class="badge warn"><span class="dot"></span>offen bis ${dde(r.faellig)}</span>`}</td>
       <td class="r num muted">${r.tage!=null?r.tage:""}</td><td class="r num"><b>${eur(r.summe)}</b></td></tr>`
    : kind==="geh"
    ? `<tr class="click" data-sdbel="${r.id}" style="${r.zaehlt?"":"opacity:.55"}" title="${r.zaehlt?"":"nicht gezählt – Lohnsteuerbescheinigung für dieses Jahr vorhanden"}"><td class="num">${dde(r.datum)}</td><td><b>${esc(r.partner)}</b></td><td>${r.art==="jahr"?`<span class="badge ok">${esc(r.zeitraum)}</span>`:esc(r.zeitraum)}</td>
       <td class="r num">${eur(r.lst)}</td><td class="r num">${eur(r.soli+r.kist)}</td><td class="r num">${eur(r.sozial)}</td><td class="r num">${eur(r.netto)}</td><td class="r num"><b>${eur(r.brutto)}</b></td></tr>`
    : kind==="ein"
    ? `<tr class="click" ${r.art==="rechnung"?`data-sdinv="${r.id}"`:`data-sdbel="${r.id}"`}><td class="num">${dde(r.zufluss)}${r.zehn_tage?` <span class="badge" title="10-Tage-Regel: zählt zum Vorjahr">10T</span>`:""}</td><td>${esc(r.kategorie)}</td><td><b>${esc(r.nr)}</b>${r.art==="rechnung"?`<div class="small muted">vom ${dde(r.datum)}</div>`:""}</td><td>${esc(r.partner)}</td><td class="muted">${esc(r.titel)}</td><td class="r num"><b>${eur(r.summe)}</b></td></tr>`
    : `<tr class="click" data-sdbel="${r.id}"><td class="num">${dde(r.datum)}</td><td>${esc(r.partner)}</td><td>${esc(r.nr)}</td><td>${esc(r.kategorie)}</td><td class="muted">${esc(r.notiz)}${r.projekt?`<div class="small">${esc(r.projekt)}</div>`:""}</td><td class="r num">${eur(r.betrag)}</td><td class="r num"><b>${r.anlage?`<span class="muted small" title="läuft über Abschreibung">AfA</span>`:eur(r.abzug)}</b></td></tr>`;
  const sortRows = rs => rs.slice().sort((a,b) => { const da = kind==="ein" ? a.zufluss : a.datum, db = kind==="ein" ? b.zufluss : b.datum; return da < db ? 1 : da > db ? -1 : 0; });
  const body = groups.map(x => {
    const on = opened.has(x.k);
    const extra = kind==="re" ? (() => { const o = x.rows.filter(r=>r.status==="offen").reduce((a,r)=>a+r.summe,0); return `${x.rows.filter(r=>r.zaehlt&&r.typ==="rechnung").length} Re.${o?` · <span style="color:var(--warn)">${eur(o)} offen</span>`:""}`; })() : `${x.rows.length} ${kind==="ein"?"Eingänge":kind==="geh"?"Abrechnung(en) · netto "+eur(x.rows.filter(r=>r.zaehlt).reduce((a,r)=>a+r.netto,0)):"Belege"}`;
    return `<tr class="click sdgrp" data-sdk="${esc(x.k)}" style="background:var(--panel2)"><td colspan="${ncol-2}"><b>${on?"▾":"▸"} ${esc(x.lb)}</b> <span class="muted small" style="margin-left:8px">${extra}</span></td>
      <td><div class="prog" style="min-width:90px"><div style="width:${100*Math.abs(x.sum)/maxG}%;background:${kind==="aus"?"#e6a1a0":"var(--acc)"}"></div></div></td><td class="r num"><b>${eur(x.sum)}</b> <span class="muted small">${tot?nde(100*x.sum/tot,0):0}%</span></td></tr>`
      + (on ? sortRows(x.rows).map(line).join("") : "");
  }).join("");
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Statistik", `${kind==="re"?"Alle geschriebenen Rechnungen":kind==="ein"?"Einnahmen nach Zahlungseingang (Zuflussprinzip)":kind==="geh"?"Gehaltsabrechnungen aus deinem Job (Brutto-Summen)":"Ausgaben nach Belegen"} · ${esc(yl)}`,
      stYearSel() + expButtons(kind==="re"?"stat_re":kind==="ein"?"stat_ein":kind==="geh"?"stat_geh":"stat_aus", () => ({year:stF.year, group:stF.group[kind], status:stF.status, ckey:stF.ckey, kat:stF.kat, art:stF.art, q:stF.q})))}
    ${stTabsHtml(tabs)}
    <div class="grid g4" style="margin-bottom:16px">${kpi}</div>
    <div class="row" style="margin-bottom:12px;align-items:center;flex-wrap:wrap;gap:8px"><span class="small muted" style="flex:none">Gruppieren:</span>${filt}</div>
    ${kind==="geh"&&rows.some(r=>!r.zaehlt)?`<div class="hl small" style="margin-bottom:12px">Für Jahre mit <b>Lohnsteuerbescheinigung</b> zählen deren Jahreswerte – die Monatsabrechnungen werden dann blass angezeigt und nicht doppelt summiert (wie in der Jahresabrechnung).</div>`:""}
    ${kind==="geh"&&!all.length?`<div class="hl small" style="margin-bottom:12px">Noch keine Gehaltsabrechnungen für ${esc(yl)}. Zieh Monatsabrechnungen oder die Lohnsteuerbescheinigung unter <b>Belege &amp; Import</b> hinein.</div>`:""}
    <div class="card" style="overflow:hidden"><div class="hd"><h3>${groups.length} Gruppe(n) · ${rows.length} Einträge · ${eur(tot)}</h3><div class="act"><button class="btn sm" id="sdclean2">🧹 Aufräumen</button><button class="btn sm ghost" id="sdall">Alle aufklappen</button><button class="btn sm ghost" id="sdnone">Alle zuklappen</button></div></div>
      ${rows.length?`<table class="t"><thead><tr>${head}</tr></thead><tbody>${body}</tbody>
      <tfoot><tr><td colspan="${ncol-1}" style="padding:10px"><b>Summe ${esc(yl)}</b></td><td class="r num" style="padding:10px"><b>${eur(tot)}</b></td></tr></tfoot></table>`:`<div class="empty">Keine Einträge für diese Auswahl.</div>`}</div>
  </div>`;
  bindCommon(); bindStTabs();
  $$("#stclean,#sdclean2").forEach(b => b.onclick = () => stClean());
  $("#sdy").onchange = e => { stF.year = e.target.value; stF.ckey = ""; vStats(); };
  $$("[data-sdg]").forEach(b => b.onclick = () => { stF.group[kind] = b.dataset.sdg; vStats(); });
  $$("[data-sds]").forEach(b => b.onclick = () => { stF.status = b.dataset.sds; vStats(); });
  $$("[data-sda]").forEach(b => b.onclick = () => { stF.art = b.dataset.sda; vStats(); });
  const sk = $("#sdkat"); if (sk) sk.onchange = e => { stF.kat = e.target.value; vStats(); };
  $("#sdc").onchange = e => { stF.ckey = e.target.value; vStats(); };
  let qt; $("#sdq").oninput = e => { clearTimeout(qt); qt = setTimeout(() => { stF.q = e.target.value; vStats().then(() => { const i = $("#sdq"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }); }, 250); };
  $$("[data-sdk]").forEach(r => r.onclick = () => { const k = r.dataset.sdk; opened.has(k) ? opened.delete(k) : opened.add(k); vStats(); });
  const sa = $("#sdall"); if (sa) sa.onclick = () => { groups.forEach(x => opened.add(x.k)); vStats(); };
  const sn = $("#sdnone"); if (sn) sn.onclick = () => { opened.clear(); vStats(); };
  $$("[data-sdinv]").forEach(r => r.onclick = () => { stData = null; openInvoice(+r.dataset.sdinv); });
  $$("[data-sdbel]").forEach(r => r.onclick = () => { const b = S.belege.find(x=>x.id==r.dataset.sdbel); if (b) { stData = null; editBeleg(b, vStats); } });
  // v3.6.1: mark entries and delete them right here. On "Einnahmen" only the receipts (sonstige) - a paid invoice is not
  // deleted from the income list by accident. Locked invoices (GoBD) are refused by the server.
  const selRows = $$(kind === "ein" ? "tr[data-sdbel]" : "tr[data-sdinv],tr[data-sdbel]");
  if (selRows.length) selectify({kind:"stat", rows: selRows, id: el => el.dataset.sdinv ? "i" + el.dataset.sdinv : "b" + el.dataset.sdbel, rerender: vStats, actions:[
    {label:`${ic("trash")} Löschen`, cls:"danger", run: async ids => stDelete(ids)}]});
}

// ---------- v3.6.1: Statistik aufraeumen ----------
async function stDelete(ids){
  const inv = ids.filter(x => x[0] === "i").map(x => +x.slice(1)), bel = ids.filter(x => x[0] === "b").map(x => +x.slice(1));
  const txt = [inv.length ? `${inv.length} Rechnung(en)` : "", bel.length ? `${bel.length} Beleg(e)` : ""].filter(Boolean).join(" und ");
  if (!txt) return false;
  if (!await confirmBox(`${txt} löschen?\n\nBeleg-Dateien wandern in den Ordner „_Papierkorb“. Festgeschriebene Rechnungen werden nicht gelöscht (GoBD – dafür stornieren). Rückgängig: Verlauf.`, "Löschen")) return false;
  if (inv.length) await bulk("invoice", "delete", inv);
  if (bel.length) await bulk("beleg", "delete", bel);
  stData = null; await reload(); vStats();
  return true;
}

async function stClean(){
  const year = stTab === "ueb" ? String(stYear) : (stF.year || "");
  const d = await api("/api/stats/detail?year=" + year);
  if (!d) return;
  const yl = year || "alle Jahre";
  // 0-Euro entries of this year: invoices with sum 0, receipts with amount 0 (expenses, other income, salary)
  const Z = [];
  (d.rechnungen || []).filter(r => Math.abs(r.summe || 0) < 0.005).forEach(r => Z.push({k:"i"+r.id, art:"Rechnung", datum:r.datum, nr:r.nr, name:r.kunde, txt:r.titel || r.status, locked:!!r.locked}));
  (d.ausgaben || []).filter(r => Math.abs(r.betrag || 0) < 0.005).forEach(r => Z.push({k:"b"+r.id, art:"Ausgabe", datum:r.datum, nr:r.nr, name:r.partner, txt:r.kategorie}));
  (d.einnahmen || []).filter(r => r.art === "sonstige" && Math.abs(r.summe || 0) < 0.005).forEach(r => Z.push({k:"b"+r.id, art:"Einnahme", datum:r.datum, nr:r.nr, name:r.partner, txt:r.kategorie}));
  (d.gehalt || []).filter(r => Math.abs(r.brutto || 0) < 0.005 && Math.abs(r.netto || 0) < 0.005).forEach(r => Z.push({k:"b"+r.id, art:"Gehalt", datum:r.datum, nr:"", name:r.partner, txt:r.art === "jahr" ? "Lohnsteuerbescheinigung" : "Monatsabrechnung"}));
  const seen = new Set(), zero = Z.filter(z => !seen.has(z.k) && seen.add(z.k));
  const html = `<div class="fr nokeep">
    <div class="card" style="margin:0"><div class="hd"><h3>Doppelte Einträge</h3><div class="act"><button class="btn sm pri" id="stcdup">Doppelte suchen …</button></div></div>
      <div class="bd small muted">Der Assistent sucht Belege und Rechnungen mit gleichem Betrag, Datum und Partner bzw. gleicher Datei (alle Jahre) und schlägt vor, welcher bleibt.</div></div>
    <div class="card" style="margin:0"><div class="hd"><h3>0-€-Einträge ${esc(yl)} <span class="muted small" style="font-weight:400">(${zero.length})</span></h3>
      <div class="act">${zero.length ? `<button class="btn sm danger" id="stczero">${ic("trash")} Markierte löschen</button>` : ""}</div></div>
      ${zero.length ? `<div style="max-height:46vh;overflow:auto"><table class="t nosort"><thead><tr><th style="width:30px"><input type="checkbox" id="stcall" checked></th><th>Art</th><th>Datum</th><th>Nr.</th><th>Kunde / Partner</th><th>Info</th></tr></thead><tbody>
        ${zero.map(z => `<tr><td><input type="checkbox" data-stz="${z.k}" ${z.locked ? "disabled title='festgeschrieben – nur stornieren'" : "checked"}></td><td>${esc(z.art)}${z.locked ? " 🔒" : ""}</td><td class="num">${dde(z.datum)}</td><td>${esc(z.nr || "")}</td><td>${esc(z.name || "")}</td><td class="small muted">${esc(z.txt || "")}</td></tr>`).join("")}</tbody></table></div>
        <div class="small muted" style="padding:8px 12px">Oft Fehlimporte (Werbung, Versandbestätigungen) oder Belege ohne erkannten Betrag. Vor dem Löschen kurz prüfen – ein Klick in der Statistik öffnet den Eintrag.</div>`
      : `<div class="bd small muted">✓ Keine Einträge mit 0,00 € in ${esc(yl)}.</div>`}</div>
    <div class="small muted">Einzelne Einträge löschen: in der Statistik (Reiter Rechnungen, Einnahmen, Ausgaben, Gehalt) links ankreuzen → <b>Löschen</b>. Alles lässt sich im <b>Verlauf</b> rückgängig machen.</div></div>`;
  let changed = false;
  await modal("Statistik aufräumen – " + yl, html, [{label:"Schließen", cls:"pri"}], true, mb => {
    const all = $("#stcall", mb); if (all) all.onchange = () => $$("[data-stz]", mb).forEach(c => { if (!c.disabled) c.checked = all.checked; });
    $("#stcdup", mb).onclick = () => { $$(".mf .btn", mb).pop().click(); setTimeout(() => dupCheck(() => { stData = null; vStats(); }), 50); };
    const zb = $("#stczero", mb); if (zb) zb.onclick = async () => {
      const ids = $$("[data-stz]", mb).filter(c => c.checked && !c.disabled).map(c => c.dataset.stz);
      if (!ids.length) { toast("Nichts markiert", true); return; }
      const inv = ids.filter(x => x[0] === "i").map(x => +x.slice(1)), bel = ids.filter(x => x[0] === "b").map(x => +x.slice(1));
      if (!await confirmBox(`${ids.length} Eintrag/Einträge mit 0,00 € löschen?`, "Löschen")) return;
      if (inv.length) await bulk("invoice", "delete", inv);
      if (bel.length) await bulk("beleg", "delete", bel);
      changed = true;
      $$("[data-stz]", mb).filter(c => c.checked && !c.disabled).forEach(c => c.closest("tr").remove());
    };
  });
  if (changed) { stData = null; await reload(); vStats(); }
}

// ---------- tax ----------
let txYear = thisYear;
async function vTax(){
  const t = await api("/api/tax?year="+txYear);
  const e = t.euer, c = t.calc, g = t.gehalt, i = t.inputs;
  const kat = Object.entries(e.kategorien).sort((a,b)=>b[1]-a[1]);
  $("#main").innerHTML = `<div class="page">
    ${pageHead("Jahresabrechnung & Steuer", "Einnahmen-Überschuss-Rechnung, Gehalt und Einkommensteuer-Schätzung", yearSel("txy", txYear) + expButtons("euer", () => ({year:txYear})) + `<button class="btn" id="csv">CSV für Steuerberater</button><button class="btn" id="jber2">${ic("pdf")} Jahresbericht</button><button class="btn pri" id="rep">${ic("pdf")} Jahresabrechnung PDF</button>`)}
    ${t.tarif_hinweis?`<div class="hl small" style="margin-bottom:14px">${esc(t.tarif_hinweis)}</div>`:""}
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card kpi"><div class="l">Einnahmen gesamt</div><div class="v">${eur(e.einnahmen + Number((t.gehalt||{}).brutto||0))}</div><div class="s">${Number((t.gehalt||{}).brutto||0) ? `Gewerbe ${eur(e.einnahmen)} + Gehalt ${eur(t.gehalt.brutto)} (brutto)` : `Gewerbe ${eur(e.einnahmen)} · <span style="color:var(--warn)">kein Gehalt ${txYear} erfasst</span>`}</div></div>
      <div class="card kpi"><div class="l">Betriebsausgaben</div><div class="v">${eur(e.ausgaben)}</div><div class="s">${kat.length} Kategorien</div></div>
      <div class="card kpi"><div class="l">Gewinn (EÜR)</div><div class="v">${eur(e.gewinn)}</div><div class="s">${e.offen_anzahl?`+ ${eur(e.offen)} offen (nicht enthalten)`:"keine offenen Posten"}</div></div>
      <div class="card kpi acc"><div class="l">${t.differenz>=0?"Voraussichtliche Nachzahlung":"Voraussichtliche Erstattung"}</div><div class="v">${eur(Math.abs(t.differenz))}</div><div class="s">ESt gesamt ${eur(c.gesamt)} · gezahlt ${eur(t.bereits_gezahlt)}</div></div>
    </div>
    <div class="grid" style="grid-template-columns:1fr 1fr 1fr;align-items:start">
      <div class="card"><div class="hd"><h3>1 · EÜR</h3></div><div class="bd"><div class="kv">
        <span>Einnahmen aus Rechnungen</span><span class="r">${eur(e.einnahmen_rechnungen)}</span>
        <span>Sonstige Einnahmen</span><span class="r">${eur(e.einnahmen_sonstige)}</span>
        <span class="tot">Betriebseinnahmen</span><span class="r tot">${eur(e.einnahmen)}</span>
        ${kat.map(([k,v])=>`<span class="sub">${esc(k)}</span><span class="r sub">− ${eur(v)}</span>`).join("")||`<span class="sub">Keine Ausgaben erfasst</span><span></span>`}
        <span class="tot">Betriebsausgaben</span><span class="r tot">− ${eur(e.ausgaben)}</span>
        <span class="tot">Gewinn</span><span class="r tot" style="color:var(--acc2)">${eur(e.gewinn)}</span></div>
        <hr class="s"><div class="small muted">Umsatz ${txYear}: ${eur(t.umsatz)} · Vorjahr: ${eur(t.umsatz_vj)}</div>
        <span class="badge ${t.ku_ok?"ok":"bad"}" style="margin-top:6px"><span class="dot"></span>${t.ku_ok?"Kleinunternehmer (§19) passt":"Kleinunternehmergrenze überschritten"}</span></div></div>
      <div class="card"><div class="hd"><h3>2 · Gehalt</h3><div class="act"><button class="btn sm" data-go="beleg">${ic("up")} Abrechnung einfügen</button></div></div><div class="bd">
        ${t.arbeitgeber.length?t.arbeitgeber.map(a=>`<div style="margin-bottom:10px"><b>${esc(a.name)}</b> <span class="small muted">· ${esc(a.quelle)}</span></div>`).join(""):`<div class="muted small" style="margin-bottom:10px">Noch keine Gehaltsabrechnungen für ${txYear}. Zieh Monatsabrechnungen oder die Lohnsteuerbescheinigung unter „Belege & Import“ hinein.</div>`}
        <div class="kv"><span>Bruttoarbeitslohn</span><span class="r">${eur(g.brutto)}</span><span class="sub">Lohnsteuer</span><span class="r sub">${eur(g.lst)}</span><span class="sub">Solidaritätszuschlag</span><span class="r sub">${eur(g.soli)}</span><span class="sub">Kirchensteuer</span><span class="r sub">${eur(g.kist)}</span>
        <span class="sub">Rentenversicherung (AN)</span><span class="r sub">${eur(g.rv)}</span><span class="sub">Kranken-/Pflegevers. (AN)</span><span class="r sub">${eur(g.kv+g.pv)}</span><span class="sub">Arbeitslosenvers. (AN)</span><span class="r sub">${eur(g.av)}</span>
        <span class="tot">Werbungskosten</span><span class="r tot">${eur(Math.max(t.wk_pauschale, t.wk_real||0))}</span></div>
        <div class="small muted" style="margin-top:6px">${(t.wk_real||0)>t.wk_pauschale?"tatsächliche Werbungskosten (inkl. Fahrten/Homeoffice)":"Arbeitnehmer-Pauschbetrag "+eur(t.wk_pauschale)}</div></div></div>
      <div class="card"><div class="hd"><h3>3 · Einkommensteuer ${txYear}</h3></div><div class="bd"><div class="kv">
        <span>Einkünfte Gehalt</span><span class="r">${eur(c.nsa)}</span><span>Einkünfte selbstständig</span><span class="r">${eur(e.gewinn)}</span>${i.sonstige?`<span>Sonstige Einkünfte</span><span class="r">${eur(i.sonstige)}</span>`:""}
        <span class="sub">− Vorsorgeaufwendungen</span><span class="r sub">${eur(c.vorsorge)}</span><span class="sub">− Sonderausgaben</span><span class="r sub">${eur(c.sonder)}</span>
        <span class="tot">zu versteuerndes Einkommen</span><span class="r tot">${eur(c.zve)}</span>
        <span>Einkommensteuer</span><span class="r">${eur(c.est)}</span><span>Solidaritätszuschlag</span><span class="r">${eur(c.soli)}</span><span>Kirchensteuer</span><span class="r">${eur(c.kist)}</span>
        ${c.gew.gewst?`<span>Gewerbesteuer (Gemeinde)</span><span class="r">${eur(c.gew.gewst)}</span>`:""}
        <span class="tot">Steuer gesamt</span><span class="r tot">${eur(c.gesamt)}</span><span class="sub">− bereits gezahlt</span><span class="r sub">${eur(t.bereits_gezahlt)}</span>
        <span class="tot">${t.differenz>=0?"Nachzahlung":"Erstattung"}</span><span class="r tot" style="color:${t.differenz>=0?"var(--bad)":"var(--ok)"}">${eur(Math.abs(t.differenz))}</span></div>
        <div class="hl small" style="margin-top:12px">Auf die Selbstständigkeit entfallen ca. <b>${eur(t.anteil_selbst)}</b> Steuer – leg das als Rücklage zur Seite. Grenzsteuersatz ca. <b>${nde(t.grenzsteuersatz,1)} %</b>.</div></div></div>
    </div>
    <div id="akte" style="margin-top:16px"></div>
    <div class="card" style="margin-top:16px"><div class="hd"><h3>Angaben für die Berechnung ${txYear}</h3><div class="act"><button class="btn sm pri" id="txsave">${ic("save")} Übernehmen & neu berechnen</button></div></div><div class="bd">
      <div class="row" style="flex-wrap:wrap">
        <label class="f">Werbungskosten tatsächlich €<input class="in num" data-i="wk" value="${nde(i.wk||0)}"></label>
        <label class="f">weitere Vorsorge (KV/PV privat, Rürup …) €<input class="in num" data-i="vorsorge_extra" value="${nde(i.vorsorge_extra||0)}"></label>
        <label class="f">Sonderausgaben (Spenden …) €<input class="in num" data-i="sonder" value="${nde(i.sonder||0)}"></label>
        <label class="f">ESt-Vorauszahlungen €<input class="in num" data-i="vorauszahlung" value="${nde(i.vorauszahlung||0)}"></label>
        <label class="f">Sonstige Einkünfte €<input class="in num" data-i="sonstige" value="${nde(i.sonstige||0)}"></label>
        <label class="f">Homeoffice-Tage (max. 210 × 6 €)<input class="in num" data-i="ho_tage" value="${i.ho_tage||0}"></label>
        <label class="f">Homeoffice zählt für<select class="in" data-i="ho_zuordnung" data-txt="1"><option value="selbst" ${i.ho_zuordnung!=="gehalt"?"selected":""}>Selbstständigkeit (EÜR)</option><option value="gehalt" ${i.ho_zuordnung==="gehalt"?"selected":""}>Angestellt (Werbungskosten)</option></select></label></div>
      <div class="row" style="margin-top:12px;align-items:center;flex-wrap:wrap">
        <label class="chk" style="flex:none"><input type="checkbox" data-i="kist" ${i.kist?"checked":""}> Kirchensteuerpflichtig</label>
        <label class="f" style="flex:none;width:110px">KiSt-Satz %<input class="in num" data-i="kist_satz" value="${nde(i.kist_satz||9,1)}"></label>
        <label class="chk" style="flex:none"><input type="checkbox" data-i="gewerblich" ${i.gewerblich?"checked":""}> gewerblich (Gewerbesteuer)</label>
        <label class="f" style="flex:none;width:120px">Hebesatz %<input class="in num" data-i="hebesatz" value="${nde(i.hebesatz||475,0)}"></label>
        <label class="chk" style="flex:none"><input type="checkbox" data-i="splitting" ${i.splitting?"checked":""}> Zusammenveranlagung</label>
        <label class="f" style="flex:none;width:200px">zvE Partner/in €<input class="in num" data-i="partner_zve" value="${nde(i.partner_zve||0)}"></label></div>
      <div class="small muted" style="margin-top:10px">Schätzung nach §32a EStG (Grundtarif ${txYear}), Vorsorge vereinfacht. Werbungskosten tatsächlich ${eur(t.wk_real)} inkl. Entfernungspauschale ${eur(t.pendel_eur)} (Fahrten). Ersetzt keine Steuerberatung und keinen Steuerbescheid.</div></div></div>
    <div class="card" style="margin-top:16px;overflow:hidden"><div class="hd"><h3>Übertrag in die Anlage EÜR</h3><div class="act small muted">Zeilen/Kennzahlen gemäß Formular 2025 – beim Übertrag die Kennzahl (Kz) verwenden</div></div>
      <table class="t"><thead><tr><th style="width:70px">Zeile</th><th style="width:70px">Kz</th><th>Bezeichnung</th><th class="r">Betrag</th></tr></thead><tbody>${(t.euer_form||[]).map(([z,k,l,v])=>`<tr><td class="num">${z}</td><td class="num"><b>${k}</b></td><td>${esc(l)}</td><td class="r num"><b>${eur(v)}</b></td></tr>`).join("")}</tbody></table></div>
  </div>`;
  bindCommon();
  $("#txy").onchange = e => { pageLeave(); txYear = +e.target.value; Promise.resolve(vTax()).then(() => setTimeout(pageRestore, 0)); };
  $("#txsave").onclick = async () => { const inp = {}; $$("[data-i]").forEach(el => inp[el.dataset.i] = el.type==="checkbox" ? el.checked : (el.dataset.txt ? el.value : pnum(el.value)));
    await api("/api/tax/save", {year:txYear, inputs:inp}); toast("Neu berechnet"); vTax(); };
  $("#jber2").onclick = () => jahresbericht(txYear);
  $("#rep").onclick = async () => { toast("Jahresabrechnung wird erstellt …"); const r = await api("/api/report/year", {year:txYear}); if (r.ok) toast("Gespeichert: " + r.path.split(/[\\/]/).pop()); };
  $("#csv").onclick = async () => { const r = await api("/api/export/csv?year="+txYear); if (r.ok) toast("CSV gespeichert: " + r.path.split(/[\\/]/).pop()); };
  loadAkte();
}
async function loadAkte(){
  const a = await api("/api/steuerakte?year="+txYear), el = $("#akte"); if (!el) return;
  const ab = a.abschluss || {}, pr = a.programm || {};
  const num = k => ab[k]==null || ab[k]==="" ? "" : nde(ab[k]);
  const diff = (p, k) => ab[k]==null || ab[k]==="" ? "" : `<span class="${Math.abs(p-ab[k])<0.01?"muted":""}" style="color:${Math.abs(p-ab[k])<0.01?"var(--ok)":"var(--warn)"}">${Math.abs(p-ab[k])<0.01?"✓ gleich":eur(p-ab[k])}</span>`;
  const vg = a.vergleich || {};
  const kbtn = (feld, p, k) => ab[k]==null || ab[k]==="" || Math.abs(p-ab[k])<0.01 ? "" : `<button class="btn sm" data-korr="${feld}|${k}">Korrigieren</button>`;
  const KF = {einnahmen:"Betriebseinnahmen", ausgaben:"Betriebsausgaben", gewinn:"Gewinn", bruttolohn:"Bruttoarbeitslohn", lst_abzug:"Lohnsteuer (Abzug vom Lohn)", wk:"Werbungskosten"};
  const bes = [["bruttolohn","bruttolohn","Bruttoarbeitslohn",true],["lst_abzug","lst_abzug","Lohnsteuer (Abzug vom Lohn)",true],["wk","wk","Werbungskosten",true],
    ["zve","zve","zu versteuerndes Einkommen",false],["est_festgesetzt","est_festgesetzt","Einkommensteuer",false],["soli_festgesetzt","soli_festgesetzt","Solidaritätszuschlag",false]];
  const groups = {}; a.docs.forEach(d => (groups[d.art] = groups[d.art] || []).push(d));
  el.innerHTML = `<div class="card"><div class="hd"><h3>Steuerakte & Jahresabschluss ${txYear}</h3>
    <div class="act">${ab.abgeschlossen?`<span class="badge ok"><span class="dot"></span>abgeschlossen${ab.bescheid_datum?" · Bescheid "+dde(ab.bescheid_datum):""}</span>`:`<span class="badge">offen</span>`}
    ${expButtons("steuerakte", {year:txYear}, true)}<button class="btn sm" id="akup">${ic("up")} Unterlage hinzufügen</button><button class="btn sm pri" id="aksave">${ic("save")} Speichern</button></div></div>
    <div class="bd"><div class="grid g2" style="align-items:start">
      <div><table class="t nosort"><thead><tr><th></th><th class="r">Programm</th><th class="r">lt. Erklärung</th><th class="r">Abweichung</th><th></th></tr></thead><tbody>
        <tr><td>Betriebseinnahmen</td><td class="r num">${eur(pr.einnahmen||0)}</td><td class="r"><input class="in num" data-ab="eur_einnahmen" value="${num("eur_einnahmen")}" style="width:110px"></td><td class="r small">${diff(pr.einnahmen||0,"eur_einnahmen")}</td><td class="r">${kbtn("einnahmen", pr.einnahmen||0, "eur_einnahmen")}</td></tr>
        <tr><td>Betriebsausgaben</td><td class="r num">${eur(pr.ausgaben||0)}</td><td class="r"><input class="in num" data-ab="eur_ausgaben" value="${num("eur_ausgaben")}" style="width:110px"></td><td class="r small">${diff(pr.ausgaben||0,"eur_ausgaben")}</td><td class="r">${kbtn("ausgaben", pr.ausgaben||0, "eur_ausgaben")}</td></tr>
        <tr><td><b>Gewinn / Verlust</b></td><td class="r num"><b>${eur(pr.gewinn||0)}</b></td><td class="r"><input class="in num" data-ab="eur_gewinn" value="${num("eur_gewinn")}" style="width:110px"></td><td class="r small">${diff(pr.gewinn||0,"eur_gewinn")}</td><td class="r">${kbtn("gewinn", pr.gewinn||0, "eur_gewinn")}</td></tr>
      </tbody></table>
      <div class="small muted" style="margin:6px 0 0">Abweichung = Programm − Erklärung. Erst <b>Speichern</b>, dann <b>Korrigieren</b> bucht die Differenz in deine Buchhaltung.</div>
      <div class="small muted" style="margin:10px 0 4px"><b>Bescheid</b></div>
      <div class="row" style="flex-wrap:wrap">${a.felder.slice(3).map(([k,l])=>`<label class="f" style="flex:1 1 46%">${esc(l)}<input class="in num" data-ab="${k}" value="${num(k)}"></label>`).join("")}</div>
      <div class="row" style="align-items:flex-end"><label class="f">Bescheid vom<input type="date" class="in" data-abt="bescheid_datum" value="${esc(ab.bescheid_datum||"")}"></label>
        <label class="chk" style="flex:none;margin-bottom:9px"><input type="checkbox" data-abc="abgeschlossen" ${ab.abgeschlossen?"checked":""}> Jahr abgeschlossen</label></div>
      ${bes.some(([k,,,])=>ab[k]!=null&&ab[k]!=="")?`<div class="small muted" style="margin:10px 0 4px"><b>Abgleich Bescheid</b></div>
      <table class="t nosort"><thead><tr><th></th><th class="r">Programm</th><th class="r">lt. Bescheid</th><th class="r">Abweichung</th><th></th></tr></thead><tbody>
      ${bes.filter(([k])=>ab[k]!=null&&ab[k]!=="").map(([k,vk,l,c])=>`<tr><td>${esc(l)}</td><td class="r num">${eur(vg[vk]||0)}</td><td class="r num">${eur(ab[k])}</td><td class="r small">${diff(vg[vk]||0,k)}</td><td class="r">${c?kbtn(k, vg[vk]||0, k):`<span class="small muted" title="Ergebnis der Berechnung – passt sich nach den Korrekturen oben an">folgt</span>`}</td></tr>`).join("")}</tbody></table>`:""}
      ${(a.korrekturen||[]).length?`<div class="small muted" style="margin:10px 0 4px"><b>Korrekturbuchungen ${txYear}</b></div>
      <table class="t nosort"><thead><tr><th>Datum</th><th>Bereich</th><th>Info</th><th class="r">Differenz</th><th></th></tr></thead><tbody>
      ${a.korrekturen.map(k=>`<tr><td class="num">${dde(k.datum)}</td><td>${esc(KF[k.feld]||k.feld)}</td><td class="small muted">${esc(k.art==="eingabe"?`${k.kategorie}: ${eur(k.alt)} → ${eur(k.neu)}`:(k.kategorie||""))}${k.notiz?` · ${esc(k.notiz)}`:""}</td><td class="r num"><b>${eur(k.betrag)}</b></td>
        <td class="r"><button class="btn sm ghost" data-kundo="${k.art}|${k.id}" title="Korrektur zurücknehmen">Zurücknehmen</button></td></tr>`).join("")}</tbody></table>`:""}
      <label class="f">Anmerkungen (eine pro Zeile – erscheinen in der Jahresabrechnung)<textarea class="in" id="aknot" rows="5">${esc((ab.notizen||[]).join("\n"))}</textarea></label></div>
      <div>${a.docs.length?Object.entries(groups).map(([art,ds])=>`<div class="small muted" style="margin:6px 0 2px"><b>${esc(art)}</b></div>${ds.map(d=>`<div class="row" style="align-items:center;padding:3px 0;border-bottom:1px solid var(--line)"><span style="flex:1">${esc(d.titel)}${d.datum?` <span class="muted small">· ${dde(d.datum)}</span>`:""}</span><button class="btn sm ghost" style="flex:none" data-akopen="${esc(d.file)}">${ic("open")}</button><button class="btn sm ghost" style="flex:none" data-akdel="${d.id}">✕</button></div>`).join("")}`).join(""):`<div class="muted small">Noch keine Unterlagen. Steuerbescheid, Erklärung, Lohnsteuerbescheinigung usw. hier ablegen – sie werden im Datenordner unter Belege\\Steuer\\${txYear} gespeichert.</div>`}</div>
    </div></div></div>`;
  $("#aksave").onclick = async () => { const d = {}; $$("[data-ab]").forEach(e => d[e.dataset.ab] = e.value.trim()==="" ? null : pnum(e.value));
    $$("[data-abt]").forEach(e => d[e.dataset.abt] = e.value); $$("[data-abc]").forEach(e => d[e.dataset.abc] = e.checked);
    if (d.abgeschlossen && !ab.abgeschlossen) d.abgeschlossen_am = todayIso();
    d.notizen = $("#aknot").value.split("\n").map(x=>x.trim()).filter(Boolean);
    await api("/api/steuerakte/save", {year:txYear, abschluss:d}); toast("Jahresabschluss gespeichert"); loadAkte(); };
  $("#akup").onclick = () => pickFiles("", async fs => {
    const r = await modal("Unterlage zur Steuerakte " + txYear, `<label class="f">Art<select class="in" id="akart">${a.arten.map(x=>`<option>${esc(x)}</option>`).join("")}</select></label><div class="small muted">${fs.length} Datei(en)</div>`,
      [{label:"Abbrechen"},{label:"Ablegen", cls:"pri", value:1, onClick: async mb => { const art = $("#akart",mb).value; for (const f of fs) await upload("/api/upload/steuer", f, {"X-Year":String(txYear), "X-Art":encodeURIComponent(art)}); }}]);
    if (r) { toast("Abgelegt"); loadAkte(); } });
  $$("[data-akopen]").forEach(b => b.onclick = () => api("/api/open", {path:b.dataset.akopen}));
  $$("[data-korr]").forEach(b => b.onclick = () => { const [feld, k] = b.dataset.korr.split("|");
    const prog = feld==="einnahmen" ? pr.einnahmen : feld==="ausgaben" ? pr.ausgaben : feld==="gewinn" ? pr.gewinn : vg[feld];
    korrDialog(feld, KF[feld]||feld, prog||0, +ab[k], a.kategorien||[]); });
  $$("[data-kundo]").forEach(b => b.onclick = async () => { const [art, id] = b.dataset.kundo.split("|");
    if (!await confirmBox("Diese Korrektur zurücknehmen?", "Zurücknehmen")) return;
    const r = await api("/api/abschluss/korrektur_undo", {year:txYear, art, id:+id}); if (r.ok) { await reload(); toast("Korrektur zurückgenommen"); vTax(); } });
  selectify({kind:"steuerakte", rows:[...$$("#akte [data-akdel]")].map(b => b.closest(".row")), id: el => el.querySelector("[data-akdel]").dataset.akdel, rerender:loadAkte, actions:[
    {label:"Entfernen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Unterlage(n) aus der Steuerakte entfernen? Die Dateien wandern in den Ordner „_Papierkorb“.", "Entfernen")) return false; await bulk("steuerakte", "delete", ids); loadAkte(); }}]});
  $$("[data-akdel]").forEach(b => b.onclick = async () => { if (!await confirmBox("Eintrag aus der Steuerakte entfernen? (Die Datei bleibt im Datenordner.)", "Entfernen")) return; await api("/api/steuerakte/delete", {id:+b.dataset.akdel}); loadAkte(); });
}

// v1.6.6: Abweichung Jahresabschluss in die Buchhaltung uebernehmen
async function korrDialog(feld, label, prog, soll, kats){
  const d0 = Math.round((soll - prog) * 100) / 100;
  const txt = {einnahmen:`Es wird eine <b>Korrekturbuchung „Sonstige Einnahme“</b> über die Differenz angelegt (negativ = Einnahmen werden verringert).`,
    ausgaben:`Es wird ein <b>Korrekturbeleg „Ausgabe“</b> in der gewählten EÜR-Kategorie angelegt (negativ = Ausgaben werden verringert).`,
    gewinn:`Der Gewinn ergibt sich aus Einnahmen − Ausgaben. Wähle, wo die Differenz gebucht wird.`,
    bruttolohn:`Es wird ein <b>Korrektureintrag Gehalt</b> (Jahreswert) über die Differenz beim Bruttolohn angelegt.`,
    lst_abzug:`Es wird ein <b>Korrektureintrag Gehalt</b> (Jahreswert) über die Differenz bei der einbehaltenen Lohnsteuer angelegt.`,
    wk:`Die Angabe <b>Werbungskosten tatsächlich</b> für ${txYear} wird um die Differenz angepasst.`}[feld] || "";
  const r = await modal(`Korrektur ${label} ${txYear}`, `<div class="fr">
    <div class="kv"><span>Programm</span><span class="r">${eur(prog)}</span><span>lt. Erklärung / Bescheid</span><span class="r">${eur(soll)}</span>
      <span class="tot">Korrektur (Differenz)</span><span class="r tot" style="color:${d0>=0?"var(--ok)":"var(--bad)"}">${d0>=0?"+":""}${eur(d0)}</span></div>
    <div class="small">${txt}</div>
    ${feld==="gewinn"?`<div class="seg" id="kvia"><button class="on" data-v="einnahmen">als Einnahme buchen</button><button data-v="ausgaben">als Ausgabe buchen</button></div>`:""}
    <div class="row">${feld!=="wk"?`<label class="f">Buchungsdatum<input type="date" class="in" id="kdat" value="${txYear}-12-31" min="${txYear}-01-01" max="${txYear}-12-31"></label>`:""}
      <label class="f">Betrag (änderbar)<input class="in num" id="kbet" value="${nde(d0)}"></label></div>
    <label class="f" id="kkatw" style="${feld==="ausgaben"?"":"display:none"}">EÜR-Kategorie<select class="in" id="kkat">${kats.map(k=>`<option ${k==="Sonstige Betriebsausgaben"?"selected":""}>${esc(k)}</option>`).join("")}</select></label>
    <label class="f">Notiz (z. B. Grund der Abweichung)<input class="in" id="knot" placeholder="z. B. Bankgebühren Dezember fehlten"></label>
    <div class="small muted">Die Buchung erscheint unter „Korrekturbuchungen“ und kann jederzeit zurückgenommen werden. Danach stimmen EÜR, Statistik und Jahresbericht mit deiner Erklärung überein.</div></div>`,
    [{label:"Abbrechen"}, {label:"Korrektur buchen", cls:"pri", value:true, onClick: async mb => {
      const via = $("#kvia button.on", mb) ? $("#kvia button.on", mb).dataset.v : "";
      const x_ = await api("/api/abschluss/korrektur", {year:txYear, feld, betrag:pnum($("#kbet", mb).value), datum:$("#kdat", mb) ? $("#kdat", mb).value : "",
        kategorie:$("#kkat", mb).value, notiz:$("#knot", mb).value, via});
      if (!x_.ok) return false; toast(x_.info || "Korrektur gebucht"); }}], false,
    mb => { $$("#kvia button", mb).forEach(b => b.onclick = () => { $$("#kvia button", mb).forEach(x_ => x_.classList.toggle("on", x_ === b)); $("#kkatw", mb).style.display = b.dataset.v === "ausgaben" ? "" : "none"; }); });
  if (r) { await reload(); vTax(); }
}

