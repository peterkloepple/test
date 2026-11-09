// PA Rechnung v2.0.16 (v3.6.1: Kontostand/Liquiditaet verdeckt bis Klick, kontoMask aus kern_02) - Uebersicht selbst gestalten (frei mit Rasterfang/Kantenfang oder im Raster): Kacheln aus allen Bereichen des Programms
// (Finanzen, Rechnungen, Kalender, Unterricht, Projekte, Steuer, Lager, Hinweise, Notizen ...),
// mehrere Seiten (Reiter), Groesse je Kachel, Reihenfolge per Ziehen, Einstellungen je Kachel.
// Gespeichert in den Einstellungen (dash_layout) - damit auch im Backup.
// Autor: T. Pfeiffer
(function(){
  const COLS = {3:"¼", 4:"⅓", 6:"½", 8:"⅔", 12:"ganz"};
  let edit = false, curTab = (() => { try { return localStorage.getItem("pa_dashtab") || ""; } catch (e) { return ""; } })();
  let saveT = null;
  const uid = () => "w" + Math.random().toString(36).slice(2, 9);

  // ---------------------------------------------------------------- data (fetched once per render)
  let DC = {};
  const D = {
    stats: y => DC["st" + y] = DC["st" + y] || api("/api/stats?year=" + y),
    tax: y => DC["tx" + y] = DC["tx" + y] || api("/api/tax?year=" + y),
    liq: () => DC.liq = DC.liq || api("/api/m53/liquiditaet?sicher=0", undefined, {quiet:true}),
    m54: () => DC.m54 = DC.m54 || api("/api/m54/ruecklage", undefined, {quiet:true}),
    kal: (von, bis) => DC["k" + von + bis] = DC["k" + von + bis] || api(`/api/kal/events?von=${von}&bis=${bis}`, undefined, {quiet:true}),
    unt: (y, m) => DC["u" + y + m] = DC["u" + y + m] || api(`/api/unterricht/month?year=${y}&month=${m}`, undefined, {quiet:true}),
    untRecent: n => DC["ur" + n] = DC["ur" + n] || api("/api/unt/recent?n=" + n, undefined, {quiet:true}),
  };
  const yr = o => o.jahr === "vorjahr" ? thisYear - 1 : thisYear;
  const addD = (d, n) => { const x_ = new Date(d); x_.setDate(x_.getDate() + n); return x_; };
  const card = (title, body, act = "") => `<div class="card dwc"><div class="hd"><h3>${title}</h3>${act ? `<div class="act">${act}</div>` : ""}</div>${body}</div>`;
  const list = (rows, empty) => rows.length ? `<table class="t"><tbody>${rows.join("")}</tbody></table>` : `<div class="empty">${empty}</div>`;

  // all pages of the program for "Schnellstart" / "Schnellzugriff"
  const PAGES = () => {
    const base = [["dash","Übersicht","dash"],["kalender","Kalender","cal"],["new","Neues Dokument","plus"],["inv","Rechnungen & Angebote","inv"],["users","Kunden","users"],["blocks","Bausteine","blocks"],
      ["school","Unterricht","school"],["proj","Projekte","proj"],["certs","Nachweise","award"],["abo","Wartung & Abos","wrench"],["beleg","Belege & Import","beleg"],["bank","Bank-Abgleich","bank"],
      ["assets","Anlagen & Inventar","box"],["trips","Fahrten","car"],["stat","Statistik","stat"],["tax","Jahresabrechnung & Steuer","tax"],["set","Einstellungen","set"]];
    const have = new Set(base.map(b => b[0]));
    EXT.nav.forEach(n => { if (!have.has(n.key)) base.push([n.key, n.label, n.icon || "dash"]); });
    return base;
  };
  const ACTIONS = {
    neu_rechnung: ["Neue Rechnung", "plus", () => go("new")],
    neu_angebot: ["Neues Angebot", "plus", () => newInvoice({typ:"angebot"})],
    beleg: ["Beleg einfügen", "up", () => go("beleg")],
    bank: ["Kontoauszug", "bank", () => go("bank")],
    kunde: ["Neuer Kunde", "users", () => { go("users"); setTimeout(() => { const b = [...document.querySelectorAll("#main button")].find(x_ => /Neuer Kunde|Kunde anlegen/.test(x_.textContent)); if (b) b.click(); }, 300); }],
    projekt: ["Neues Projekt", "proj", () => { go("proj"); setTimeout(() => { const b = [...document.querySelectorAll("#main button")].find(x_ => /Neues Projekt|Projekt anlegen/.test(x_.textContent)); if (b) b.click(); }, 300); }],
    kal_abrufen: ["Kalender abrufen", "sync", async () => { toast("TimeTree wird abgerufen …"); const r = await api("/api/kal/sync", {}); if (r && r.ok) toast(`${r.termine} Termine aktualisiert`); else if (r && r.error) toast(r.error, true); dashRender(); }],
    backup: ["Backup jetzt", "save", async () => { const r = await api("/api/backup/now", {}); if (r && r.ok) toast("Backup: " + r.datei); }],
    export: ["Gesamt-Export (Excel)", "xls", () => doExport("gesamt", "xlsx", {})],
    jey: ["Frag Dr. Jey", "m55", () => go("jey")],
    suche: ["Suchen (Strg+K)", "search", () => { const b = document.getElementById("gsearch"); if (b) b.click(); }],
  };

  // ---------------------------------------------------------------- widget catalogue
  const ALERT_KINDS = [["belege","Belege zu prüfen (Eingangsordner)"],["mails","E-Mails zu prüfen"],["entwuerfe","Entwürfe"],["ueberfaellig","Überfällige Rechnungen"],
    ["wartung","Wartung fällig"],["nachweise","Nachweise laufen ab"],["angebote","Offene Angebote"],["kalender","Termine heute"]];
  const KPI_KINDS = [["umsatz","Umsatz"],["eingang","Zahlungseingang"],["offen","Offene Rechnungen"],["ausgaben","Ausgaben"],["gewinn","Gewinn"],["ruecklage","Steuer-Rücklage"],
    ["konto","Kontostand"],["angebote","Offene Angebote"],["anzahl","Anzahl Rechnungen"],["ust_grenze","Rest bis KU-Grenze"]];
  const JAHR = {k:"jahr", label:"Jahr", type:"select", choices:[["aktuell","laufendes Jahr"],["vorjahr","Vorjahr"]], def:"aktuell"};
  const ANZ = (def = 8) => ({k:"n", label:"Anzahl Einträge", type:"select", choices:[[5,"5"],[8,"8"],[12,"12"],[20,"20"]], def});

  const W = {
    gruss: {cat:"Allgemein", title:"Begrüßung & Schnellzugriff", desc:"Name, Datum und frei wählbare Knöpfe (Neue Rechnung, Beleg, Kalender abrufen …).", w:12, plain:true,
      opts:[{k:"aktionen", label:"Knöpfe", type:"checks", choices:Object.entries(ACTIONS).map(([k, v]) => [k, v[0]]), def:["beleg","bank","neu_rechnung"]},
            {k:"export", label:"Export-Knöpfe (Excel/PDF gesamt)", type:"bool", def:true}],
      render: async (el, o) => {
        el.innerHTML = pageHead("Hallo " + esc((S.settings.inhaber || "").split(" ")[0]), new Date().toLocaleDateString("de-DE", {weekday:"long", day:"numeric", month:"long", year:"numeric"}),
          (o.export ? expButtons("gesamt", {}, false) : "") + (o.aktionen || []).filter(a => ACTIONS[a]).map((a, i, arr) => `<button class="btn ${i === arr.length - 1 ? "pri" : ""}" data-dact="${a}">${ic(ACTIONS[a][1])} ${esc(ACTIONS[a][0])}</button>`).join(""));
        $$("[data-dact]", el).forEach(b => b.onclick = () => ACTIONS[b.dataset.dact][2]());
      }},
    hinweise: {cat:"Allgemein", title:"Hinweise", desc:"Was zu tun ist: Belege, Mails, Entwürfe, Mahnungen, Wartung, Nachweise, Angebote, Termine.", w:12, plain:true,
      opts:[{k:"arten", label:"Anzeigen", type:"checks", choices:ALERT_KINDS, def:ALERT_KINDS.map(a => a[0]).filter(a => a !== "kalender")}],
      render: async (el, o) => {
        const on = new Set(o.arten || []), A = [];
        const drafts = S.invoices.filter(i => i.status === "entwurf"), offers = S.invoices.filter(i => i.typ === "angebot" && i.status === "offen");
        if (on.has("belege") && S.pending) A.push(`<div class="alert warn" data-go="beleg">${ic("alert")}<b>${S.pending} Beleg(e) aus dem Eingangsordner</b> warten auf deine Prüfung</div>`);
        if (on.has("mails") && S.mailimp && S.mailimp.offen) A.push(`<div class="alert warn" data-go="mails">${ic("mail")}<b>${S.mailimp.offen} E-Mail(s)</b> warten auf deine Prüfung</div>`);
        if (on.has("entwuerfe") && drafts.length) A.push(`<div class="alert acc" data-go-inv="draft">${ic("inv")}<b>${drafts.length} Entwurf/Entwürfe</b> warten aufs Fertigstellen</div>`);
        if (on.has("ueberfaellig") && S.overdue.length) A.push(`<div class="alert bad" data-go-inv="mahn">${ic("alert")}<b>${S.overdue.length} überfällige Rechnung(en)</b> · ${eur(S.overdue.reduce((a, i) => a + i.summe, 0))} – Mahnwesen öffnen</div>`);
        if (on.has("wartung")) S.vertraege_due.forEach(v => A.push(`<div class="alert warn" data-go="abo">${ic("wrench")}<b>Wartung fällig:</b> ${esc(v.name)} am ${dde(v.naechste)}</div>`));
        if (on.has("nachweise")) S.cert_warn.slice(0, 5).forEach(w => A.push(`<div class="alert ${w.tage < 0 ? "bad" : "warn"}" data-go="certs">${ic("award")}<b>${esc(w.art)}:</b> ${esc(w.bezeichnung)}${w.person ? " · " + esc(w.person) : ""} – ${dde(w.datum)}</div>`));
        if (on.has("angebote") && offers.length) A.push(`<div class="alert" data-go-inv="angebot">${ic("inv")}<b>${offers.length} offene(s) Angebot(e)</b> · ${eur(offers.reduce((a, i) => a + i.summe, 0))}</div>`);
        if (on.has("kalender") && S.kal && S.kal.heute) A.push(`<div class="alert acc" data-go="kalender">${ic("cal")}<b>${S.kal.heute} Termin(e) heute</b> – Kalender öffnen</div>`);
        el.innerHTML = A.length ? `<div class="alerts" style="margin:0">${A.join("")}</div>` : (edit ? `<div class="card"><div class="bd small muted">Hinweise: zurzeit nichts zu tun.</div></div>` : "");
      }},
    kpi: {cat:"Finanzen", title:"Kennzahlen", desc:"Umsatz, Zahlungseingang, Offen, Ausgaben, Gewinn, Rücklage, Kontostand … frei wählbar.", w:12, plain:true,
      opts:[JAHR, {k:"werte", label:"Kennzahlen", type:"checks", choices:KPI_KINDS, def:["umsatz","eingang","offen","ausgaben","gewinn","ruecklage"]}],
      render: async (el, o) => {
        const y = yr(o), [st, tx] = await Promise.all([D.stats(y), D.tax(y)]);
        const open = S.invoices.filter(i => i.typ === "rechnung" && i.status === "offen"), offers = S.invoices.filter(i => i.typ === "angebot" && i.status === "offen");
        const K = {umsatz:[`Umsatz ${y}`, eur(st.total), `${st.anzahl} Rechnungen`, "acc"], eingang:["Zahlungseingang", eur(tx.euer.einnahmen), "nach Zuflussprinzip"],
          offen:["Offen", eur(open.reduce((a, i) => a + i.summe, 0)), `${open.length} Rechnung(en)`, open.length ? "warnv" : ""], ausgaben:["Ausgaben", eur(tx.euer.ausgaben), "inkl. AfA & Fahrten"],
          gewinn:["Gewinn", eur(tx.euer.gewinn), "EÜR vorläufig"], ruecklage:["Steuer-Rücklage", eur(Math.max(0, tx.anteil_selbst)), "Anteil Selbstständigkeit"],
          konto:["Kontostand", S.konto ? kontoMask(eur(S.konto.saldo), true) : "–", S.konto ? "Stand " + dde(S.konto.datum) : "noch nicht erfasst"],
          angebote:["Offene Angebote", eur(offers.reduce((a, i) => a + i.summe, 0)), `${offers.length} Angebot(e)`], anzahl:["Rechnungen " + y, String(st.anzahl), "geschrieben"],
          ust_grenze:["Rest bis 100.000 €", eur(Math.max(0, 100000 - tx.umsatz)), "Kleinunternehmer " + y]};
        const ks = (o.werte || []).filter(k => K[k]);
        el.innerHTML = `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px">${ks.map(k => { const [l, v, s_, c] = K[k];
          return `<div class="card kpi ${c === "acc" ? "acc" : ""}"><div class="l">${esc(l)}</div><div class="v" ${c === "warnv" ? `style="color:var(--warn)"` : ""}>${v}</div><div class="s">${esc(s_)}</div></div>`; }).join("")}</div>`;
      }},
    verlauf: {cat:"Finanzen", title:"Monatsverlauf", desc:"Umsatz und Ausgaben je Monat als Balken.", w:8, opts:[JAHR],
      render: async (el, o) => { const y = yr(o), st = await D.stats(y); const maxM = Math.max(1, ...st.months.map(m => Math.max(m.umsatz, m.ausgaben)));
        el.innerHTML = card(`Monatsverlauf ${y}`, `<div class="bd">${monthChart(st.months, maxM)}</div>`, `<span class="legend"><span><i style="background:var(--acc)"></i>Umsatz</span><span><i style="background:#e6a1a0"></i>Ausgaben</span></span>`); }},
    konto: {cat:"Finanzen", title:"Kontostand", desc:"Letzter Kontostand mit Verlauf, eintragen per Klick.", w:4, plain:true,
      render: async el => { el.innerHTML = kontoCard(true); const k = $("#kset", el); if (k) { k.removeAttribute("id"); k.onclick = kontoDialog; } }},
    liq: {cat:"Finanzen", title:"Liquidität", desc:"Kontostand-Vorschau der nächsten Wochen mit tiefstem Stand.", w:4,
      render: async el => { const d = await D.liq(); if (!d || !d.series) { el.innerHTML = card("Liquidität", `<div class="bd small muted">Keine Vorschau möglich.</div>`); return; }
        const v = d.series.map(r => r.saldo), mn = Math.min(...v, 0), mx = Math.max(...v, 0), Wd = 300, H = 70, rg = (mx - mn) || 1;
        const pts = v.map((x_, i) => `${(i * (Wd / Math.max(1, v.length - 1))).toFixed(1)},${(H - 4 - (x_ - mn) / rg * (H - 8)).toFixed(1)}`).join(" ");
        el.innerHTML = card("Liquidität", `<div class="bd"><div class="kv"><span class="sub">heute</span><span class="r num">${kontoMask(eur(d.start))}</span><span class="sub">tiefster Stand ${d.min ? dde(d.min.datum) : ""}</span><span class="r num" style="color:${d.min && d.min.saldo < (d.min_reserve || 0) ? "var(--bad)" : "inherit"}">${d.min ? kontoMask(eur(d.min.saldo)) : "–"}</span><span class="sub">am Ende (${d.series.length - 1} Tage)</span><span class="r num">${kontoMask(eur(d.ende))}</span></div>
          ${kontoMask(`<svg viewBox="0 0 ${Wd} ${H}" preserveAspectRatio="none" style="width:100%;height:70px;margin-top:8px"><polyline points="${pts}" fill="none" stroke="var(--acc)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`)}
          ${(d.warnungen || []).slice(0, 2).map(w => `<div class="small" style="color:var(--warn)">${esc(w)}</div>`).join("")}</div>`, `<button class="btn sm ghost" data-go="liq">Öffnen</button>`); }},
    ku: {cat:"Steuer", title:"Kleinunternehmer-Grenzen", desc:"Umsatz gegen 25.000 € (Vorjahr) und 100.000 € (laufendes Jahr).", w:4,
      render: async el => { const y = thisYear, tx = await D.tax(y); const p1 = Math.min(100, tx.umsatz / 1000), p2 = Math.min(100, tx.umsatz_vj / 250);
        el.innerHTML = card("Kleinunternehmer-Grenzen", `<div class="bd"><div class="small muted">Umsatz ${y} · Grenze 100.000 €</div>
          <div class="row" style="align-items:center;margin:4px 0 14px"><div class="prog ${p1 > 80 ? "w" : ""}" style="flex:3"><div style="width:${p1}%"></div></div><b class="num" style="flex:none">${eur0(tx.umsatz)}</b></div>
          <div class="small muted">Umsatz ${y - 1} · Grenze 25.000 €</div>
          <div class="row" style="align-items:center;margin:4px 0 14px"><div class="prog ${p2 > 80 ? "w" : ""}" style="flex:3"><div style="width:${p2}%"></div></div><b class="num" style="flex:none">${eur0(tx.umsatz_vj)}</b></div>
          <span class="badge ${tx.ku_ok ? "ok" : "bad"}"><span class="dot"></span>${tx.ku_ok ? "§19 UStG weiterhin möglich" : "Grenze überschritten – prüfen!"}</span></div>`); }},
    steuer: {cat:"Steuer", title:"Steuer-Schätzung", desc:"Geschätzte Einkommensteuer und voraussichtliche Nachzahlung/Erstattung.", w:4, opts:[JAHR],
      render: async (el, o) => { const y = yr(o), tx = await D.tax(y);
        el.innerHTML = card(`Steuer ${y}`, `<div class="bd"><div class="kv"><span class="sub">Gewinn (EÜR)</span><span class="r num">${eur(tx.euer.gewinn)}</span><span class="sub">zu versteuerndes Einkommen</span><span class="r num">${eur(tx.calc.zve)}</span>
          <span class="sub">Einkommensteuer gesamt</span><span class="r num">${eur(tx.calc.gesamt)}</span><span class="sub">${tx.differenz >= 0 ? "Voraussichtl. Nachzahlung" : "Voraussichtl. Erstattung"}</span><span class="r num" style="color:${tx.differenz >= 0 ? "var(--bad)" : "var(--ok)"}">${eur(Math.abs(tx.differenz))}</span></div></div>`,
          `<button class="btn sm ghost" data-go="tax">Öffnen</button>`); }},
    ruecklage2: {cat:"Steuer", title:"Rücklage – Soll/Ist", desc:"Wie viel bis heute zurückgelegt sein sollte und was fehlt.", w:4,
      render: async el => { const r = await D.m54(); if (!r || r.soll_bis_heute === undefined) { el.innerHTML = card("Rücklage", `<div class="bd small muted">Keine Daten.</div>`); return; }
        el.innerHTML = card(`Rücklage ${r.year}`, `<div class="bd"><div class="kv"><span class="sub">Soll bis heute</span><span class="r num">${eur(r.soll_bis_heute)}</span><span class="sub">zurückgelegt</span><span class="r num">${eur((r.zurueckgelegt || {}).betrag || 0)}</span>
          <span class="sub">Lücke</span><span class="r num" style="color:${r.luecke > 0 ? "var(--bad)" : "var(--ok)"}">${eur(r.luecke)}</span><span class="sub">pro Monat</span><span class="r num">${eur(r.monat)}</span></div></div>`); }},
    offen: {cat:"Rechnungen", title:"Offene Rechnungen", desc:"Unbezahlte Rechnungen mit Status (überfällig, Mahnstufe).", w:4, opts:[ANZ(8)],
      render: async (el, o) => { const open = S.invoices.filter(i => i.typ === "rechnung" && i.status === "offen");
        el.innerHTML = card(`Offene Rechnungen <span class="cnt">${open.length}</span>`, list(open.slice(0, +o.n).map(i => `<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b><div class="small muted">${esc(invName(i))}</div></td><td>${statusBadge(i)}</td><td class="r num"><b>${eur(i.summe)}</b></td></tr>`), "Alles bezahlt."),
          `<button class="btn sm ghost" data-go-inv="rechnung">Alle</button>`); }},
    dokumente: {cat:"Rechnungen", title:"Letzte Dokumente", desc:"Zuletzt geschriebene Rechnungen, Angebote und Auftragsbestätigungen.", w:4,
      opts:[ANZ(8), {k:"typ", label:"Art", type:"select", choices:[["","alle"],["rechnung","Rechnungen"],["angebot","Angebote"],["auftrag","Auftragsbestätigungen"]], def:""}],
      render: async (el, o) => { const l = S.invoices.filter(i => !o.typ || i.typ === o.typ);
        el.innerHTML = card("Letzte Dokumente", list(l.slice(0, +o.n).map(i => `<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b><div class="small muted">${esc(DOCT[i.typ] || "")} · ${esc(invName(i))}</div></td><td>${statusBadge(i)}</td><td class="r num">${eur(i.summe)}</td></tr>`), "Noch keine Dokumente."),
          `<button class="btn sm ghost" data-go="inv">Alle</button>`); }},
    angebote: {cat:"Rechnungen", title:"Offene Angebote", desc:"Angebote, die noch nicht angenommen/abgelehnt sind (mit Gültigkeit).", w:4, opts:[ANZ(8)],
      render: async (el, o) => { const l = S.invoices.filter(i => i.typ === "angebot" && i.status === "offen");
        el.innerHTML = card(`Offene Angebote <span class="cnt">${l.length}</span>`, list(l.slice(0, +o.n).map(i => `<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b><div class="small muted">${esc(invName(i))}${i.gueltig_bis ? " · gültig bis " + dde(i.gueltig_bis) : ""}</div></td><td>${statusBadge(i)}</td><td class="r num">${eur(i.summe)}</td></tr>`), "Keine offenen Angebote."),
          `<button class="btn sm ghost" data-go-inv="angebot">Alle</button>`); }},
    mahn: {cat:"Rechnungen", title:"Überfällig / Mahnwesen", desc:"Überfällige Rechnungen nach Tagen, direkt ins Mahnwesen.", w:4, opts:[ANZ(8)],
      render: async (el, o) => { el.innerHTML = card(`Überfällig <span class="cnt">${S.overdue.length}</span>`, list(S.overdue.slice(0, +o.n).map(i => `<tr class="click" data-inv="${i.id}"><td><b>${esc(i.nr)}</b><div class="small muted">${esc(i.name || "")}</div></td><td class="small" style="color:var(--bad)">${i.tage} Tage</td><td class="r num">${eur(i.summe)}</td></tr>`), "Nichts überfällig."),
          `<button class="btn sm ghost" data-go-inv="mahn">Mahnwesen</button>`); }},
    topkunden: {cat:"Statistik", title:"Top-Kunden", desc:"Kunden mit dem meisten Umsatz im Jahr.", w:4, opts:[JAHR, ANZ(5)],
      render: async (el, o) => { const y = yr(o), st = await D.stats(y);
        el.innerHTML = card(`Top-Kunden ${y}`, list(st.kunden.slice(0, +o.n).map(k => `<tr><td><b>${esc(k.name || k.kdnr || "–")}</b><div class="small muted">${k.anzahl} Rechnung(en) · ${nde(k.anteil, 1)} %</div></td><td class="r num">${eur(k.summe)}</td></tr>`), "Noch kein Umsatz."),
          `<button class="btn sm ghost" data-go="stat">Statistik</button>`); }},
    topleistung: {cat:"Statistik", title:"Top-Leistungen", desc:"Bausteine/Leistungen mit dem meisten Umsatz.", w:4, opts:[JAHR, ANZ(5)],
      render: async (el, o) => { const y = yr(o), st = await D.stats(y);
        el.innerHTML = card(`Top-Leistungen ${y}`, list(st.leistungen.slice(0, +o.n).map(k => `<tr><td><b>${esc(k.name || k.nr || "–")}</b><div class="small muted">${nde(k.menge, 2)} × · ${nde(k.anteil, 1)} %</div></td><td class="r num">${eur(k.summe)}</td></tr>`), "Noch kein Umsatz."), ""); }},
    jahre: {cat:"Statistik", title:"Jahresvergleich", desc:"Umsatz, Einnahmen, Ausgaben und Gewinn je Jahr.", w:6,
      render: async el => { const st = await D.stats(thisYear);
        el.innerHTML = card("Jahresvergleich", `<table class="t"><thead><tr><th>Jahr</th><th class="r">Umsatz</th><th class="r">Einnahmen</th><th class="r">Ausgaben</th><th class="r">Gewinn</th></tr></thead><tbody>${st.jahre.slice().reverse().map(j => `<tr><td><b>${j.year}</b></td><td class="r num">${eur(j.umsatz)}</td><td class="r num">${eur(j.einnahmen)}</td><td class="r num">${eur(j.ausgaben)}</td><td class="r num">${eur(j.gewinn)}</td></tr>`).join("")}</tbody></table>`); }},
    kal_agenda: {cat:"Kalender", title:"Termine (Agenda)", desc:"Nächste Termine aus deinem Kalender (TimeTree / .ics).", w:4,
      opts:[{k:"tage", label:"Zeitraum", type:"select", choices:[[1,"heute"],[2,"heute + morgen"],[7,"7 Tage"],[14,"14 Tage"],[31,"31 Tage"]], def:7}, ANZ(12)],
      render: async (el, o) => { const a = new Date(), von = isoLocal(a), bis = isoLocal(addD(a, +o.tage)); const r = await D.kal(von, bis); const ev = ((r && r.events) || []).filter(e => !e.memo && e.end.slice(0, 16) >= isoLocal(a) + "T00:00");
        let last = "", rows = [];
        ev.slice(0, +o.n).forEach(e => { const d = e.start.slice(0, 10) < von ? von : e.start.slice(0, 10);
          if (d !== last) { rows.push(`<tr class="kdh"><td colspan="2"><b>${d === von ? "Heute" : d === isoLocal(addD(a, 1)) ? "Morgen" : ""}</b> ${new Date(d + "T12:00").toLocaleDateString("de-DE", {weekday:"short", day:"numeric", month:"short"})}</td></tr>`); last = d; }
          rows.push(`<tr class="click" data-kev='${esc(JSON.stringify(e))}'><td class="num small" style="width:62px">${e.all_day ? "ganzt." : e.start.slice(11, 16)}</td><td><span class="kdot" style="background:${esc(e.farbe)}"></span>${esc(e.title)}${e.ort ? `<div class="small muted">${esc(e.ort)}</div>` : ""}</td></tr>`); });
        el.innerHTML = card("Termine", rows.length ? `<table class="t"><tbody>${rows.join("")}</tbody></table>` : `<div class="empty">${r && r.ok ? "Keine Termine im Zeitraum." : "Kalender noch nicht eingerichtet."}</div>`, `<button class="btn sm ghost" data-go="kalender">Kalender</button>`);
        $$("[data-kev]", el).forEach(x_ => x_.onclick = () => window.kalEvDialog && kalEvDialog(JSON.parse(x_.dataset.kev))); }},
    kal_woche: {cat:"Kalender", title:"Kalender-Woche", desc:"Die aktuelle Woche, Tag für Tag mit allen Terminen.", w:12,
      render: async el => { const a = new Date(), mo = addD(a, -((a.getDay() + 6) % 7)); const r = await D.kal(isoLocal(mo), isoLocal(addD(mo, 7))); const m = window.kalByDay ? kalByDay((r && r.events) || []) : {};
        const t = todayIso();
        el.innerHTML = card("Diese Woche", `<div class="dwk">${Array.from({length:7}, (_, i) => { const d = addD(mo, i), k = isoLocal(d);
          return `<div class="dwkd ${k === t ? "today" : ""}" data-kday="${k}"><div class="small"><b>${["Mo","Di","Mi","Do","Fr","Sa","So"][i]}</b> ${d.getDate()}.${d.getMonth() + 1}.</div>${(m[k] || []).map(e => window.kalPill ? kalPill(e) : esc(e.title)).join("")}</div>`; }).join("")}</div>`,
          `<button class="btn sm ghost" data-go="kalender">Kalender</button>`);
        $$("[data-kev]", el).forEach(x_ => x_.onclick = ev => { ev.stopPropagation(); kalEvDialog(JSON.parse(x_.dataset.kev)); });
        $$("[data-kday]", el).forEach(x_ => x_.onclick = () => window.kalDayDialog && kalDayDialog(x_.dataset.kday)); }},
    kal_monat: {cat:"Kalender", title:"Kalender-Monat (klein)", desc:"Monatsübersicht mit Punkten für Tage mit Terminen.", w:4,
      render: async el => { const a = new Date(), f = new Date(a.getFullYear(), a.getMonth(), 1), s0 = addD(f, -((f.getDay() + 6) % 7));
        const r = await D.kal(isoLocal(s0), isoLocal(addD(s0, 42))); const m = window.kalByDay ? kalByDay((r && r.events) || []) : {}; const t = todayIso();
        el.innerHTML = card(`${MONL[a.getMonth()]} ${a.getFullYear()}`, `<div class="dmm">${["Mo","Di","Mi","Do","Fr","Sa","So"].map(w => `<b>${w}</b>`).join("")}${Array.from({length:42}, (_, i) => { const d = addD(s0, i), k = isoLocal(d), l = m[k] || [];
          return `<div class="dmd ${d.getMonth() !== a.getMonth() ? "other" : ""} ${k === t ? "today" : ""}" data-kday="${k}" title="${l.length} Termin(e)">${d.getDate()}<span>${l.slice(0, 3).map(e => `<i style="background:${esc(e.farbe)}"></i>`).join("")}</span></div>`; }).join("")}</div>`,
          `<button class="btn sm ghost" data-go="kalender">Kalender</button>`);
        $$("[data-kday]", el).forEach(x_ => x_.onclick = () => window.kalDayDialog && kalDayDialog(x_.dataset.kday)); }},
    unterricht: {cat:"Unterricht", title:"Unterricht diesen Monat", desc:"Erfasste Stunden je Rechnungsempfänger, Abrechnung mit einem Klick.", w:4,
      render: async el => { const a = new Date(), d = await D.unt(a.getFullYear(), a.getMonth() + 1); const p = (d && d.payers) || {};
        const n = (d && d.lessons || []).length;
        el.innerHTML = card(`Unterricht ${MONL[a.getMonth()]}`, `<div class="bd"><div class="kv"><span class="sub">Kurse aktiv</span><span class="r">${S.kurse.filter(k => k.aktiv).length}</span><span class="sub">Schüler/innen aktiv</span><span class="r">${S.students.filter(s => s.aktiv).length}</span><span class="sub">Stunden erfasst</span><span class="r">${n}</span></div>
          ${Object.keys(p).length ? `<div class="small" style="margin-top:8px"><b>Noch abzurechnen:</b><br>${Object.entries(p).map(([cid, k]) => `${esc(custName(+cid) || "?")} – ${k} Std.`).join("<br>")}</div>` : `<div class="small muted" style="margin-top:8px">Nichts offen zum Abrechnen.</div>`}</div>`,
          `<button class="btn sm ghost" data-go="school">Unterricht</button>`); }},
    unt_dateien: {cat:"Unterricht", title:"Unterricht – neue Dateien", desc:"Zuletzt abgelegte Noten, Aufnahmen und Dokumente.", w:4, opts:[ANZ(8)],
      render: async (el, o) => { const r = await D.untRecent(+o.n);
        el.innerHTML = card("Unterricht – Dateien", list(((r && r.dateien) || []).map(f => `<tr class="click" data-uof="${f.id}"><td><b>${esc(f.name)}</b><div class="small muted">${esc(f.ziel_name)} · ${esc(f.art)}${f.datum ? " · " + dde(f.datum) : ""}</div></td></tr>`), "Noch keine Dateien abgelegt."),
          `<button class="btn sm ghost" data-uall="1">Alle</button>`);
        $$("[data-uof]", el).forEach(x_ => x_.onclick = () => api("/api/unt/open", {id:+x_.dataset.uof}));
        const b = $("[data-uall]", el); if (b) b.onclick = () => { schTab = "dat"; go("school"); }; }},
    projekte: {cat:"Projekte", title:"Aktive Projekte", desc:"Laufende Projekte mit Dateien und offenen Positionen.", w:4, opts:[ANZ(8)],
      render: async (el, o) => { const l = S.projects.filter(p => p.status === "aktiv");
        el.innerHTML = card("Aktive Projekte", l.slice(0, +o.n).map(p => `<div class="list"><div class="it" data-proj="${p.id}"><div class="av" style="background:${BEREICH_COL[p.bereich] || "#888"}22;color:${BEREICH_COL[p.bereich] || "#888"}">${initials(p.bereich)}</div><div style="min-width:0"><b>${esc(p.name)}</b><div class="small muted">${esc(p.nr)} · ${p.nfiles} Dateien${p.offen_pos ? ` · ${p.offen_pos} offene Pos.` : ""}</div></div></div></div>`).join("") || `<div class="empty">Keine aktiven Projekte.</div>`,
          `<button class="btn sm ghost" data-go="proj">Alle</button>`); }},
    nachweise: {cat:"Projekte", title:"Nachweise & Zertifikate", desc:"Prüfungen, Zertifikate und Bestätigungen, die bald ablaufen.", w:4,
      render: async el => { el.innerHTML = card("Nachweise", list(S.cert_warn.map(w => `<tr class="click" data-go="certs"><td><b>${esc(w.art)}</b><div class="small muted">${esc(w.bezeichnung)}${w.person ? " · " + esc(w.person) : ""}</div></td><td class="r small" style="color:${w.tage < 0 ? "var(--bad)" : "var(--warn)"}">${dde(w.datum)}</td></tr>`), "Alles gültig."), `<button class="btn sm ghost" data-go="certs">Alle</button>`); }},
    wartung: {cat:"Projekte", title:"Wartung & Abos", desc:"Fällige Wartungsverträge und wiederkehrende Rechnungen.", w:4,
      render: async el => { const rec = (S.recurring || []).filter(r => r.aktiv).slice(0, 6);
        el.innerHTML = card("Wartung & Abos", list(S.vertraege_due.map(v => `<tr class="click" data-go="abo"><td><b>${esc(v.name)}</b><div class="small muted">Wartung</div></td><td class="r small">${dde(v.naechste)}</td></tr>`)
          .concat(rec.map(r => `<tr class="click" data-go="abo"><td><b>${esc(r.src_nr || "Abo")}</b><div class="small muted">Abo-Rechnung</div></td><td class="r small">${dde(r.naechstes)}</td></tr>`)), "Nichts fällig."), `<button class="btn sm ghost" data-go="abo">Öffnen</button>`); }},
    lager: {cat:"Projekte", title:"Lager – nachbestellen", desc:"Lagerartikel unter Mindestbestand.", w:4,
      render: async el => { const m = S.m42 || {}; el.innerHTML = card(`Lager <span class="cnt">${m.low || 0}</span>`, list((m.low_list || []).map(r => `<tr><td><b>${esc(r.name)}</b></td><td class="r num small">${nde(r.bestand, 0)} / ${nde(r.mindest, 0)} ${esc(r.einheit || "")}</td></tr>`), "Alles auf Lager."), `<button class="btn sm ghost" data-go="m42lager">Lager</button>`); }},
    belege: {cat:"Belege", title:"Letzte Belege", desc:"Zuletzt erfasste Ausgaben, Einnahmen und Gehaltsabrechnungen.", w:4, opts:[ANZ(8)],
      render: async (el, o) => { el.innerHTML = card("Letzte Belege", list(S.belege.slice(0, +o.n).map(b => `<tr class="click" data-go="beleg"><td><b>${esc(b.partner || "–")}</b><div class="small muted">${dde(b.datum)} · ${esc(b.kategorie || b.typ)}</div></td><td class="r num">${eur(b.betrag)}</td></tr>`), "Noch keine Belege."), `<button class="btn sm ghost" data-go="beleg">Alle</button>`); }},
    schnellstart: {cat:"Allgemein", title:"Schnellstart-Kacheln", desc:"Große Knöpfe zu beliebigen Seiten des Programms.", w:12,
      opts:[{k:"seiten", label:"Seiten", type:"checks", choices:() => PAGES().filter(p => p[0] !== "dash").map(p => [p[0], p[1]]), def:["kalender","inv","users","school","proj","beleg","stat"]}],
      render: async (el, o) => { const P_ = PAGES(); el.innerHTML = card("Schnellstart", `<div class="bd dqs">${(o.seiten || []).map(k => P_.find(p => p[0] === k)).filter(Boolean).map(p => `<button class="dq" data-go="${p[0]}">${ic(p[2])}<span>${esc(p[1])}</span></button>`).join("")}</div>`); }},
    notiz: {cat:"Allgemein", title:"Notiz / Pinnwand", desc:"Freier Text – direkt in der Kachel schreiben, wird automatisch gespeichert.", w:4, opts:[{k:"titel", label:"Überschrift", type:"text", def:"Notiz"}],
      render: async (el, o, w) => { el.innerHTML = card(esc(o.titel || "Notiz"), `<div class="bd"><textarea class="in dnote nokeep" rows="7" placeholder="Hier schreiben …">${esc(o.text || "")}</textarea></div>`);
        const ta = $("textarea", el); ta.oninput = () => { w.opts = Object.assign({}, w.opts, {text: ta.value}); saveLater(); }; }},
  };
  // modules that add dashboard cards themselves (EXT.dash) become widgets too
  const EXTW = [["jey", "m55dq", "Frag Dr. Jey", "Eingabezeile für Fragen an Dr. Jey.", "Allgemein", 12], ["ku_prognose", "m52card", "Kleinunternehmer-Prognose", "Hochrechnung des Jahresumsatzes gegen die Grenzen.", "Steuer", 6],
    ["ruecklage", "m54card", "Steuer-Rücklage live", "Rücklage für die Selbstständigkeit, mit Eintragen.", "Steuer", 6], ["fix_hinweis", "fixdash", "Fixkosten zu bestätigen", "Hinweis auf vorgemerkte Fixkosten.", "Finanzen", 12],
    ["lager_hinweis", "m42box", "Lager-Hinweis", "Hinweiszeile, wenn Artikel unter Mindestbestand sind.", "Projekte", 12]];
  function extWidgets(){
    const used = new Set();
    EXTW.forEach(([id, mark, title, desc, cat, w]) => { const fn = EXT.dash.find(f => String(f).includes(mark)); if (fn) { used.add(fn);
      W[id] = {cat, title, desc, w, plain:true, render: async el => { el.innerHTML = ""; fn(el); const r = el.querySelector("#m5xrow"); if (r) { r.style.marginBottom = "0"; r.style.gridTemplateColumns = "1fr"; }
        el.querySelectorAll(":scope > .card, :scope > .alerts, :scope > .alert").forEach(c => c.style.marginBottom = "0"); if (!el.innerHTML.trim() && edit) el.innerHTML = `<div class="card"><div class="bd small muted">${esc(title)}: zurzeit nichts anzuzeigen.</div></div>`; }}; } });
    EXT.dash.forEach((fn, i) => { if (used.has(fn)) return; W["ext" + i] = {cat:"Erweiterungen", title:"Erweiterung " + (i + 1), desc:"Kachel eines Zusatzmoduls.", w:12, plain:true, render: async el => { el.innerHTML = ""; fn(el); }}; });
  }
  const CATS = ["Allgemein", "Finanzen", "Rechnungen", "Kalender", "Unterricht", "Projekte", "Belege", "Statistik", "Steuer", "Erweiterungen"];

  // ---------------------------------------------------------------- layout
  function defLayout(){
    const it = (typ, w, opts) => ({id: uid(), typ, w: w || (W[typ] && W[typ].w) || 4, opts: opts || {}});
    const start = [it("gruss"), it("jey"), it("hinweise"), it("fix_hinweis"), it("lager_hinweis"), it("kpi"), it("ku_prognose"), it("ruecklage"),
      it("verlauf", 8), it("konto", 4), it("kal_agenda", 4), it("offen", 4), it("dokumente", 4), it("projekte", 4), it("unterricht", 4), it("kal_monat", 4)].filter(x_ => W[x_.typ]);
    return {v:1, tabs:[{id:"start", name:"Start", items:start}]};
  }
  // v2.1.0: a damaged saved layout (tab without items, null entries, bad ids/numbers, edited backup ...) no longer
  // breaks the whole overview - it is repaired once when read
  const WD = t => typeof t === "string" && Object.prototype.hasOwnProperty.call(W, t) ? W[t] : null;
  const NORMED = new WeakSet();
  function normLayout(L){
    const okId = v => typeof v === "string" && /^[\w-]{1,40}$/.test(v);
    const tids = new Set(), wids = new Set();
    L.tabs = L.tabs.filter(t => t && typeof t === "object" && !Array.isArray(t));
    L.tabs.forEach(t => {
      if (!okId(t.id) || tids.has(t.id)) t.id = uid();
      tids.add(t.id);
      t.name = typeof t.name === "string" && t.name.trim() ? t.name : "Seite";
      t.items = (Array.isArray(t.items) ? t.items : []).filter(w => w && typeof w === "object" && typeof w.typ === "string" && w.typ);
      t.items.forEach(w => {
        if (!okId(w.id) || wids.has(w.id)) w.id = uid();
        wids.add(w.id);
        if (!COLS[+w.w]) w.w = (WD(w.typ) && WD(w.typ).w) || 4;
        if (!w.opts || typeof w.opts !== "object" || Array.isArray(w.opts)) w.opts = {};
        ["x", "y", "fw", "fh", "z"].forEach(k => { if (w[k] == null) return; const v = Number(w[k]); w[k] = isFinite(v) ? Math.max(0, Math.min(20000, v)) : null; });
      });
    });
    if (!L.tabs.length) L.tabs = defLayout().tabs;
    if (L.fang != null && (typeof L.fang !== "object" || Array.isArray(L.fang))) L.fang = {};
    NORMED.add(L);
    return L;
  }
  function layout(){
    let L = S.settings.dash_layout;
    if (!L || typeof L !== "object" || !Array.isArray(L.tabs) || !L.tabs.length) { L = defLayout(); S.settings.dash_layout = L; }
    if (!NORMED.has(L)) normLayout(L);
    return L;
  }
  function saveLater(){ clearTimeout(saveT); saveT = setTimeout(() => api("/api/settings/save", {dash_layout: layout()}, {quiet:true}), 500); }
  function saveNow(){ clearTimeout(saveT); return api("/api/settings/save", {dash_layout: layout()}, {quiet:true}); }
  const tabOf = () => { const L = layout(); return L.tabs.find(t => t.id === curTab) || L.tabs[0]; };
  const optsOf = w => { const d = {}; ((WD(w.typ) || {}).opts || []).forEach(o => d[o.k] = o.def); return Object.assign(d, w.opts || {}); };

  // ---------------------------------------------------------------- render
  window.dashRender = async function(){
    extWidgets();
    DC = {};
    const L = layout(), T = tabOf(); curTab = T.id;
    const tabs = L.tabs.length > 1 || edit ? `<div class="tabs" style="margin-bottom:14px">${L.tabs.map(t => `<div class="tab ${t.id === T.id ? "on" : ""}" data-dtab="${t.id}">${esc(t.name)}<span class="cnt">${t.items.length}</span></div>`).join("")}${edit ? `<div class="tab" id="dtadd" title="Neue Seite">+ Seite</div>` : ""}</div>` : "";
    const fr = !!T.frei, FG = fangOf();
    const bar = edit ? `<div class="dbar"><b>Übersicht anpassen</b><span class="small muted">${fr ? "Kachel an der Leiste ziehen · Ecke unten rechts = Größe · Alt = ohne Fang" : "Kacheln ziehen zum Verschieben · Größe ¼ … ganz · ⚙ Einstellungen"}</span><span class="sp"></span>
        <div class="seg" style="flex:none"><button type="button" id="dmfree" class="${fr ? "on" : ""}" title="Kacheln frei platzieren – pixelgenau, ohne Raster">Frei</button><button type="button" id="dmgrid" class="${fr ? "" : "on"}" title="Kacheln im Raster anordnen">Raster</button></div>
        ${fr ? `<div class="dfang"><label class="chk" title="Kacheln rasten beim Verschieben und Größe-Ziehen am Raster ein (Alt gedrückt = ohne Fang)"><input type="checkbox" id="dfan" ${FG.an ? "checked" : ""}> Rasterfang</label>
          <select class="in" id="dfrw" title="Rasterweite">${FANG_RW.map(v => `<option value="${v}" ${v === FG.rw ? "selected" : ""}>${v} px</option>`).join("")}</select>
          <label class="chk" title="Kanten der anderen Kacheln fangen (bündig oder mit Abstand daneben)"><input type="checkbox" id="dfkt" ${FG.kanten ? "checked" : ""}> Kanten fangen</label>
          <button class="btn sm" id="dfalign" title="Alle Kacheln dieser Seite einmal aufs Raster setzen">Am Raster ausrichten</button></div>` : ""}
        <button class="btn sm" id="dadd">${ic("plus")} Kachel hinzufügen</button><button class="btn sm" id="dtren">Seite umbenennen</button>${L.tabs.length > 1 ? `<button class="btn sm" id="dtdel" style="color:var(--bad)">Seite löschen</button>` : ""}
        <button class="btn sm" id="dreset">Zurücksetzen</button><button class="btn sm pri" id="ddone">${ic("check")} Fertig</button></div>` : "";
    $("#main").innerHTML = `<div class="page dash ${edit ? "dedit" : ""}">${bar}<div class="row" style="align-items:flex-start">${tabs ? `<div style="flex:1">${tabs}</div>` : `<span class="sp"></span>`}
      ${edit ? "" : `<button class="btn sm ghost dcfg" id="dcfg" title="Übersicht anpassen">${ic("set")} Anpassen</button>`}</div>
      <div class="${fr ? "dfree" : "dgrid"}"${fr && edit && FG.an ? ` style="${gridBg(FG.rw)}"` : ""}>${T.items.map(w => `<div class="dw ${WD(w.typ) && WD(w.typ).plain ? "plain" : ""}" data-dw="${w.id}" style="${fr ? freeStyle(w) : "grid-column:span " + (w.w || 4)}" ${edit && !fr ? `draggable="true"` : ""}>
        ${edit ? `<div class="dwbar"><span class="dwh" title="Ziehen zum Verschieben">⠿</span><b>${esc(WD(w.typ) ? WD(w.typ).title : w.typ)}</b><span class="sp"></span>
          ${fr ? `<span class="dic" data-dauto title="Höhe automatisch (passt sich dem Inhalt an)">↕</span><span class="dic" data-dfront title="Nach vorne">⧉↑</span>` : Object.entries(COLS).map(([c, l]) => `<span class="dsz ${+c === +w.w ? "on" : ""}" data-sz="${c}" title="Breite ${l}">${l}</span>`).join("")}
          ${WD(w.typ) && WD(w.typ).opts ? `<span class="dic" data-dopt title="Einstellungen">⚙</span>` : ""}<span class="dic" data-ddup title="Duplizieren">⧉</span><span class="dic" data-ddel title="Entfernen" style="color:var(--bad)">✕</span></div>` : ""}
        <div class="dwb"></div>${fr && edit ? `<div class="dwr" title="Größe ziehen"></div>` : ""}</div>`).join("")}
        ${edit && !fr ? `<div class="dw dwadd" style="grid-column:span 4" id="dadd2">${ic("plus")}<span>Kachel hinzufügen</span></div>` : ""}</div>
      ${!T.items.length && !edit ? `<div class="card empty">Diese Seite ist leer. <button class="btn sm" id="dcfg2">Anpassen</button></div>` : ""}</div>`;
    // widgets render independently - one failing card never breaks the page
    await Promise.all(T.items.map(async w => {
      const box = $(`[data-dw="${w.id}"] .dwb`); if (!box) return;
      const def = WD(w.typ);
      if (!def || typeof def.render !== "function") { box.innerHTML = `<div class="card"><div class="bd small muted">Kachel „${esc(w.typ)}“ gibt es in dieser Version nicht.</div></div>`; return; }
      try { await def.render(box, optsOf(w), w); bindCommon(box);
        if (!edit && !box.innerHTML.trim()) box.parentNode.style.display = "none";   // nothing to show (e.g. no hints) -> no gap
        $$("[data-go-inv]", box).forEach(a => a.onclick = () => { invTab = a.dataset.goInv; go("inv"); }); }
      catch (e) { console.error(e); box.innerHTML = card(esc(def.title), `<div class="bd small muted">Konnte nicht geladen werden.</div>`); }
    }));
    bind(T);
    if (fr) fitCanvas(T);
  };

  // ---------------------------------------------------------------- free placement (v2.0.15)
  const ZF = () => parseFloat(document.body.style.zoom) || 1;
  function freeStyle(w){
    return `left:${Math.round(w.x || 0)}px;top:${Math.round(w.y || 0)}px;width:${Math.round(w.fw || 360)}px;${w.fh ? `height:${Math.round(w.fh)}px;` : ""}z-index:${w.z || 1}`;
  }
  function fitCanvas(T){
    const c = $(".dfree"); if (!c) return;
    let mb = 0, mr = 0;
    $$(".dfree > .dw").forEach(el => { if (el.style.display === "none") return; mb = Math.max(mb, el.offsetTop + el.offsetHeight); mr = Math.max(mr, el.offsetLeft + el.offsetWidth); });
    c.style.height = (mb + (edit ? 320 : 24)) + "px";
  }
  // switch a tab from grid to free: keep exactly the current look
  function toFree(T){
    const g = $(".dgrid"); if (!g) { T.frei = true; return; }
    const r0 = g.getBoundingClientRect(), z = ZF();
    let bottom = 0; const hidden = [];
    T.items.forEach(w => { const el = $(`[data-dw="${w.id}"]`, g); const r = el && el.getBoundingClientRect();
      if (!r || !r.width) { hidden.push(w); return; }       // empty tile (e.g. no hints right now)
      w.x = Math.round((r.left - r0.left) / z); w.y = Math.round((r.top - r0.top) / z); w.fw = Math.round(r.width / z); w.fh = null;
      bottom = Math.max(bottom, w.y + r.height / z); });
    hidden.forEach((w, i) => { w.x = 0; w.y = Math.round(bottom + 16 + i * 70); w.fw = Math.round(r0.width / z); w.fh = null; });
    T.frei = true;
  }
  // ---------------------------------------------------------------- snap to grid / edges (v2.0.16)
  const FANG_RW = [8, 12, 16, 24, 32, 48], GAP = 16, THR = 8;
  function fangOf(){ const f = layout().fang || {};
    return {an: f.an !== false, rw: FANG_RW.includes(+f.rw) ? +f.rw : 16, kanten: f.kanten !== false}; }
  function gridBg(rw){ const h = rw / 2;
    return `background-image:radial-gradient(circle,var(--accline) 1.2px,transparent 1.6px);background-size:${rw}px ${rw}px;background-position:-${h}px -${h}px`; }
  // edges of the other visible tiles (flush and with the normal gap next to them)
  function edgesOf(self){
    const xs = [0], ys = [0];
    $$(".dfree > .dw").forEach(o => { if (o === self || o.style.display === "none") return;
      const l = o.offsetLeft, t = o.offsetTop, r = l + o.offsetWidth, b = t + o.offsetHeight;
      xs.push(l, r, r + GAP, l - GAP); ys.push(t, b, b + GAP, t - GAP); });
    return {xs, ys};
  }
  // snap a moving span [pos, pos+size] (move) or only its end (resize) -> {v, g}
  function snapPos(pos, size, cands, F, off, endOnly){
    if (off || !F.an) return {v: pos, g: null, d: 0};
    let best = null;
    if (F.kanten) cands.forEach(c => (endOnly ? [size] : [0, size]).forEach(o => {
      const d = c - (pos + o); if (Math.abs(d) <= THR && (!best || Math.abs(d) < Math.abs(best.d))) best = {d, g: c}; }));
    if (best) return {v: pos + best.d, g: best.g, d: best.d};
    const e = endOnly ? pos + size : pos, r = Math.round(e / F.rw) * F.rw;
    return {v: pos + r - e, g: null, d: r - e};
  }
  function guides(c, gx, gy){
    let v = $(".dgv", c), h = $(".dgh", c);
    if (!v) { v = document.createElement("div"); v.className = "dgv"; c.appendChild(v); h = document.createElement("div"); h.className = "dgh"; c.appendChild(h); }
    v.style.display = gx == null ? "none" : ""; if (gx != null) v.style.left = gx + "px";
    h.style.display = gy == null ? "none" : ""; if (gy != null) h.style.top = gy + "px";
  }
  function noGuides(c){ $$(".dgv,.dgh", c).forEach(e => e.remove()); }
  function alignAll(T){
    const rw = fangOf().rw, R = v => Math.round((v || 0) / rw) * rw;
    T.items.forEach(w => { w.x = R(w.x); w.y = R(w.y); w.fw = Math.max(160, R(w.fw || 360)); if (w.fh) w.fh = Math.max(80, R(w.fh)); });
  }

  function bindFree(T){
    let zTop = Math.max(1, ...T.items.map(w => w.z || 1));
    $$(".dfree > .dw").forEach(el => {
      const w = T.items.find(x_ => x_.id === el.dataset.dw); if (!w) return;
      const front = () => { w.z = ++zTop; el.style.zIndex = w.z; };
      const bar = $(".dwbar", el);
      if (bar) bar.onpointerdown = ev => {
        if (ev.target.closest(".dic")) return;
        ev.preventDefault(); front();
        const z = ZF(), sx = ev.clientX, sy = ev.clientY, x0 = w.x || 0, y0 = w.y || 0, F = fangOf();
        el.classList.add("dmove");
        const c = el.parentNode, cw = c.clientWidth, E = edgesOf(el), ew = el.offsetWidth, eh = el.offsetHeight;
        const mv = e => {
          const rx = Math.round(x0 + (e.clientX - sx) / z), ry = Math.round(y0 + (e.clientY - sy) / z);
          const sx_ = snapPos(rx, ew, E.xs, F, e.altKey), sy_ = snapPos(ry, eh, E.ys, F, e.altKey);
          w.x = Math.min(Math.max(0, cw - 80), Math.max(0, sx_.v)); w.y = Math.max(0, sy_.v);
          el.style.left = w.x + "px"; el.style.top = w.y + "px"; guides(c, sx_.g, sy_.g); fitCanvas(T); };
        const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); el.classList.remove("dmove"); noGuides(c); saveLater(); };
        addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up);
      };
      const rz = $(".dwr", el);
      if (rz) rz.onpointerdown = ev => {
        ev.preventDefault(); ev.stopPropagation(); front();
        const z = ZF(), sx = ev.clientX, sy = ev.clientY, w0 = el.offsetWidth, h0 = el.offsetHeight, F = fangOf();
        const c = el.parentNode, cw = c.clientWidth, E = edgesOf(el), X = w.x || 0, Y = w.y || 0;
        const mv = e => {
          const rw_ = Math.round(w0 + (e.clientX - sx) / z), rh = Math.round(h0 + (e.clientY - sy) / z);
          const a_ = snapPos(X, rw_, E.xs, F, e.altKey, true), b_ = snapPos(Y, rh, E.ys, F, e.altKey, true);
          w.fw = Math.min(Math.max(160, cw - X), Math.max(160, rw_ + a_.d));
          w.fh = Math.max(80, rh + b_.d);
          el.style.width = w.fw + "px"; el.style.height = w.fh + "px"; guides(c, a_.g, b_.g); fitCanvas(T); };
        const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); noGuides(c); saveLater(); };
        addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up);
      };
      const a = $("[data-dauto]", el); if (a) a.onclick = () => { w.fh = null; el.style.height = ""; fitCanvas(T); saveLater(); };
      const f = $("[data-dfront]", el); if (f) f.onclick = () => { front(); saveLater(); };
    });
  }

  function bind(T){
    const L = layout();
    $$("[data-dtab]").forEach(t => t.onclick = () => { curTab = t.dataset.dtab; try { localStorage.setItem("pa_dashtab", curTab); } catch (e) {} dashRender(); });
    const on = (id, fn) => { const e = $("#" + id); if (e) e.onclick = fn; };
    const startEdit = () => { edit = true; if (!T.frei && !T.rasterGewollt) { toFree(T); saveLater(); } dashRender(); };
    on("dcfg", startEdit); on("dcfg2", startEdit);
    on("ddone", async () => { edit = false; await saveNow(); toast("Übersicht gespeichert"); dashRender(); });
    on("dadd", addDialog); on("dadd2", addDialog);
    on("dmfree", () => { if (!T.frei) { toFree(T); T.rasterGewollt = false; saveLater(); dashRender(); } });
    on("dmgrid", async () => { if (!T.frei) return; if (!await confirmBox("Zurück ins Raster? Die freien Positionen dieser Seite gehen verloren (Reihenfolge: von oben nach unten).", "Raster")) return;
      T.items.sort((a, b) => (a.y || 0) - (b.y || 0) || (a.x || 0) - (b.x || 0)); T.frei = false; T.rasterGewollt = true; saveLater(); dashRender(); });
    const setF = k => v => { const L_ = layout(); L_.fang = Object.assign(fangOf(), {[k]: v}); saveLater(); dashRender(); };
    const ch = (id, fn) => { const e = $("#" + id); if (e) e.onchange = () => fn(e.type === "checkbox" ? e.checked : +e.value); };
    ch("dfan", setF("an")); ch("dfrw", setF("rw")); ch("dfkt", setF("kanten"));
    on("dfalign", () => { alignAll(T); saveLater(); dashRender(); toast("Kacheln am Raster ausgerichtet"); });
    on("dtadd", async () => { const n = await askText("Neue Seite", "Name der Seite", "Seite " + (L.tabs.length + 1)); if (!n) return;
      const t = {id: uid(), name: n, items: [], frei: true}; L.tabs.push(t); curTab = t.id; saveLater(); dashRender(); });
    on("dtren", async () => { const n = await askText("Seite umbenennen", "Name der Seite", T.name); if (!n) return; T.name = n; saveLater(); dashRender(); });
    on("dtdel", async () => { if (!await confirmBox(`Seite „${T.name}“ mit ${T.items.length} Kachel(n) löschen?`, "Löschen")) return;
      L.tabs = L.tabs.filter(t => t !== T); curTab = L.tabs[0].id; saveLater(); dashRender(); });
    on("dreset", async () => { if (!await confirmBox("Übersicht auf die Standard-Anordnung zurücksetzen? Eigene Seiten und Notizen gehen verloren.", "Zurücksetzen")) return;
      S.settings.dash_layout = defLayout(); curTab = "start"; await saveNow(); dashRender(); });
    if (!edit) return;
    if (T.frei) {
      bindFree(T);
      $$("[data-dw]").forEach(el => { const w = T.items.find(x_ => x_.id === el.dataset.dw); if (!w) return;
        const o = $("[data-dopt]", el); if (o) o.onclick = () => optDialog(w);
        const d = $("[data-ddel]", el); if (d) d.onclick = () => { T.items = T.items.filter(x_ => x_ !== w); saveLater(); dashRender(); };
        const u = $("[data-ddup]", el); if (u) u.onclick = () => { T.items.push(Object.assign(JSON.parse(JSON.stringify(w)), {id: uid(), x:(w.x || 0) + 24, y:(w.y || 0) + 24})); saveLater(); dashRender(); }; });
      return;
    }
    $$("[data-dw]").forEach(el => {
      const w = T.items.find(x_ => x_.id === el.dataset.dw); if (!w) return;
      $$("[data-sz]", el).forEach(s_ => s_.onclick = () => { w.w = +s_.dataset.sz; saveLater(); dashRender(); });
      const o = $("[data-dopt]", el); if (o) o.onclick = () => optDialog(w);
      const d = $("[data-ddel]", el); if (d) d.onclick = () => { T.items = T.items.filter(x_ => x_ !== w); saveLater(); dashRender(); };
      const u = $("[data-ddup]", el); if (u) u.onclick = () => { T.items.splice(T.items.indexOf(w) + 1, 0, {id: uid(), typ: w.typ, w: w.w, opts: JSON.parse(JSON.stringify(w.opts || {}))}); saveLater(); dashRender(); };
      el.ondragstart = e => { e.dataTransfer.setData("text/dw", w.id); e.dataTransfer.effectAllowed = "move"; el.classList.add("drag"); };
      el.ondragend = () => el.classList.remove("drag");
      el.ondragover = e => { if (![...e.dataTransfer.types].includes("text/dw")) return; e.preventDefault(); const r = el.getBoundingClientRect();
        const after = (e.clientX - r.left) / r.width > .5; el.classList.toggle("dropl", !after); el.classList.toggle("dropr", after); };
      el.ondragleave = () => el.classList.remove("dropl", "dropr");
      el.ondrop = e => { e.preventDefault(); const after = el.classList.contains("dropr"); el.classList.remove("dropl", "dropr");
        const src = T.items.find(x_ => x_.id === e.dataTransfer.getData("text/dw")); if (!src || src === w) return;
        T.items.splice(T.items.indexOf(src), 1); T.items.splice(T.items.indexOf(w) + (after ? 1 : 0), 0, src); saveLater(); dashRender(); };
    });
    // drop a widget onto another tab = move it there
    $$("[data-dtab]").forEach(t => { t.ondragover = e => { if ([...e.dataTransfer.types].includes("text/dw")) { e.preventDefault(); t.classList.add("dragover"); } };
      t.ondragleave = () => t.classList.remove("dragover");
      t.ondrop = e => { e.preventDefault(); t.classList.remove("dragover"); const dst = L.tabs.find(x_ => x_.id === t.dataset.dtab); const src = T.items.find(x_ => x_.id === e.dataTransfer.getData("text/dw"));
        if (!dst || !src || dst === T) return; T.items = T.items.filter(x_ => x_ !== src); dst.items.push(src); saveLater(); toast(`„${(WD(src.typ) || {title: src.typ}).title}“ nach „${dst.name}“ verschoben`); dashRender(); }; });
  }

  async function askText(title, label, val){
    let out = null;
    await modal(title, `<div class="fr nokeep"><label class="f">${esc(label)}<input class="in" id="dtx" value="${esc(val || "")}"></label></div>`,
      [{label:"Abbrechen"}, {label:"OK", cls:"pri", onClick: mb => { out = $("#dtx", mb).value.trim(); if (!out) { toast("Bitte einen Namen eingeben", true); return false; } }}]);
    return out;
  }

  async function addDialog(){
    extWidgets();
    const T = tabOf();
    const used = new Set(T.items.map(w => w.typ));
    const byCat = CATS.map(c => [c, Object.entries(W).filter(([, d]) => d.cat === c)]).filter(([, l]) => l.length);
    const pr = modal("Kachel hinzufügen", `<div class="fr nokeep"><div class="small muted">Mehrere ankreuzen – sie kommen ans Ende der Seite „${esc(T.name)}“. Bereits vorhandene sind markiert (doppelt geht auch, z. B. zwei Notizen).</div>
      ${byCat.map(([c, l]) => `<div class="dcat"><div class="untgrp" style="padding:8px 0 4px">${esc(c)}</div>${l.map(([k, d]) => `<label class="chk dadd"><input type="checkbox" value="${k}"><span><b>${esc(d.title)}</b>${used.has(k) ? ` <span class="badge">schon da</span>` : ""}<br><span class="small muted">${esc(d.desc || "")}</span></span></label>`).join("")}</div>`).join("")}</div>`,
      [{label:"Abbrechen"}, {label:"Hinzufügen", cls:"pri", onClick: mb => { const ks = $$("input:checked", mb).map(c => c.value); if (!ks.length) { toast("Nichts ausgewählt", true); return false; }
        let y = 0; if (T.frei) $$(".dfree > .dw").forEach(el => { y = Math.max(y, el.offsetTop + el.offsetHeight); });
        ks.forEach((k, i) => T.items.push(Object.assign({id: uid(), typ: k, w: W[k].w, opts: {}},
          T.frei ? {x: fangOf().rw * Math.round(24 * i / fangOf().rw), y: fangOf().rw * Math.ceil((y + 16 + 24 * i) / fangOf().rw), fw: W[k].w >= 12 ? 900 : W[k].w >= 8 ? 640 : 360} : {}))); saveLater(); }}], true);
    await pr; dashRender();
  }

  async function optDialog(w){
    const def = WD(w.typ), o = optsOf(w);
    if (!def) return;
    const field = f => { const ch = typeof f.choices === "function" ? f.choices() : f.choices;
      if (f.type === "select") return `<label class="f">${esc(f.label)}<select class="in" data-ok="${f.k}">${ch.map(([v, l]) => `<option value="${esc(String(v))}" ${String(o[f.k]) === String(v) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
      if (f.type === "checks") return `<div class="f"><span>${esc(f.label)}</span><div class="dchk" data-ok="${f.k}">${ch.map(([v, l]) => `<label class="chk"><input type="checkbox" value="${esc(v)}" ${(o[f.k] || []).includes(v) ? "checked" : ""}> ${esc(l)}</label>`).join("")}</div></div>`;
      if (f.type === "bool") return `<label class="chk"><input type="checkbox" data-ok="${f.k}" ${o[f.k] ? "checked" : ""}> ${esc(f.label)}</label>`;
      return `<label class="f">${esc(f.label)}<input class="in" data-ok="${f.k}" value="${esc(o[f.k] || "")}"></label>`; };
    await modal(def.title + " – Einstellungen", `<div class="fr nokeep">${(def.opts || []).map(field).join("")}</div>`,
      [{label:"Abbrechen"}, {label:"Übernehmen", cls:"pri", onClick: mb => { const n = Object.assign({}, w.opts || {});
        (def.opts || []).forEach(f => { const el = $(`[data-ok="${f.k}"]`, mb); if (!el) return;
          n[f.k] = f.type === "checks" ? $$("input:checked", el).map(c => c.value) : f.type === "bool" ? el.checked : el.value; });
        w.opts = n; saveLater(); dashRender(); }}]);
  }

  const css = document.createElement("style");
  css.textContent = `.dgrid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:16px;align-items:start;grid-auto-flow:row dense}
    .dw{min-width:0;position:relative} .dw .dwb>.card,.dw .dwb>.ph{margin-bottom:0} .dw .dwb .ph{margin:0}
    .dw .dwb .card.dwc{height:100%} .dw .cnt{font-size:12px;color:var(--mute);font-weight:500;margin-left:4px}
    .dedit .dw{outline:2px dashed var(--accline);outline-offset:4px;border-radius:var(--r2);cursor:grab}
    .dedit .dw.drag{opacity:.4} .dw.dropl{box-shadow:-6px 0 0 -2px var(--acc)} .dw.dropr{box-shadow:6px 0 0 -2px var(--acc)}
    .dwbar{display:flex;align-items:center;gap:6px;background:var(--accsoft);border:1px solid var(--accline);border-radius:8px;padding:4px 8px;margin-bottom:6px;font-size:12.5px}
    .dwh{cursor:grab;font-size:16px;color:var(--acc)} .dsz{padding:1px 7px;border-radius:10px;cursor:pointer;color:var(--ink2)} .dsz.on{background:var(--acc);color:#fff}
    .dic{cursor:pointer;padding:0 5px;font-size:14px}
    .dwadd{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:120px;border:2px dashed var(--accline);border-radius:var(--r2);color:var(--acc);cursor:pointer;outline:none!important}
    .dwadd svg{width:26px;height:26px;stroke:currentColor;fill:none;stroke-width:2}
    .dbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--accline);border-radius:var(--r2);padding:10px 14px;margin-bottom:14px;position:sticky;top:0;z-index:5;box-shadow:var(--sh)}
    .dcfg{flex:none;margin-bottom:8px} .dash .tabs .tab.dragover{background:var(--accsoft)}
    .dqs{display:flex;flex-wrap:wrap;gap:10px} .dq{display:flex;flex-direction:column;align-items:center;gap:6px;width:118px;padding:14px 8px;border:1px solid var(--line);border-radius:12px;background:var(--panel2);cursor:pointer;font-size:12.5px;color:var(--ink)}
    .dq:hover{border-color:var(--acc);color:var(--acc)} .dq svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:1.8}
    .dwk{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border-top:1px solid var(--line)} .dwkd{min-height:90px;padding:6px;border-right:1px solid var(--line);cursor:pointer}
    .dwkd:last-child{border-right:0} .dwkd.today{background:var(--accsoft)} .dwkd .small{margin-bottom:4px}
    .dmm{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;padding:10px 12px;font-size:12px;text-align:center} .dmm b{color:var(--mute);font-weight:600;font-size:11px}
    .dmd{padding:4px 0 2px;border-radius:6px;cursor:pointer} .dmd:hover{background:var(--panel2)} .dmd.other{opacity:.4} .dmd.today{background:var(--acc);color:#fff}
    .dmd span{display:flex;justify-content:center;gap:2px;height:5px;margin-top:2px} .dmd i{width:5px;height:5px;border-radius:50%;display:block}
    tr.kdh td{background:var(--panel2);font-size:12px;padding-top:5px;padding-bottom:5px}
    .dnote{width:100%;resize:vertical;font:inherit;min-height:120px}
    .dadd{display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--line)} .dchk{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:4px 12px;margin-top:4px}
    .dfree{position:relative;min-height:200px;isolation:isolate}
    .dfree>.dw{position:absolute;display:flex;flex-direction:column}
    .dfree>.dw>.dwb{flex:1;min-height:0;overflow:auto}
    .dfree>.dw[style*="height"]>.dwb>.card{height:100%;overflow:auto}
    .dedit .dfree>.dw{cursor:default;background:var(--bg)}
    .dedit .dfree>.dw .dwbar{cursor:move;user-select:none}
    .dfree>.dw.dmove{opacity:.9;box-shadow:0 18px 40px rgba(20,15,40,.25)}
    .dwr{position:absolute;right:-6px;bottom:-6px;width:18px;height:18px;cursor:nwse-resize;border-right:3px solid var(--acc);border-bottom:3px solid var(--acc);border-radius:0 0 6px 0;z-index:3}
    .dedit .dfree{outline:1px dashed var(--accline);outline-offset:8px;border-radius:6px}
    .dgv,.dgh{position:absolute;pointer-events:none;z-index:99999;background:var(--acc)} .dgv{top:0;bottom:0;width:1px} .dgh{left:0;right:0;height:1px}
    .dfang{display:flex;align-items:center;gap:8px;flex:none;padding:0 6px;border-left:1px solid var(--line);border-right:1px solid var(--line)}
    .dfang .chk{flex:none;margin:0} .dfang select.in{width:auto;flex:none;padding:4px 8px;height:auto}
    @media (max-width:1250px){.dgrid>.dw{grid-column:span 6!important}.dgrid>.dw.plain,.dgrid>.dw[style*="span 12"],.dgrid>.dw[style*="span 8"]{grid-column:span 12!important}}
    .dfree>.dw{grid-column:auto!important}`;
  document.head.appendChild(css);
})();
