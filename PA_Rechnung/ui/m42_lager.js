"use strict";
// m42 - Lager: Seite "Lager" (Stammdaten), Hinweis im Dashboard, Entnahme im Projekt
// Autor: T. Pfeiffer
IC.m42box = '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>';
const M42_ARTEN = {zugang: "Zugang", abgang: "Abgang", inventur: "Inventur", entnahme: "Projekt-Entnahme", storno: "Rückbuchung"};
let m42F = {q: "", kat: "", filter: ""};

EXT.nav.push({key: "m42lager", label: "Lager", icon: "m42box", section: "Stammdaten", cnt: () => (S.m42 && S.m42.low) ? String(S.m42.low) : ""});
EXT.views.m42lager = m42View;

EXT.dash.push(el => {
  const m = S.m42; if (!m || !m.low) return;
  const d = document.createElement("div");
  d.className = "alert warn"; d.style.marginBottom = "10px";
  d.innerHTML = `${ic("m42box")}<b>${m.low} Lagerartikel unter Mindestbestand</b><span class="small">${m.low_list.slice(0, 4).map(r => esc(r.name) + " (" + nde(r.bestand, 0) + "/" + nde(r.mindest, 0) + " " + esc(r.einheit || "") + ")").join(" · ")}${m.low > 4 ? " …" : ""}</span><span class="sp" style="flex:1"></span><span class="small"><u>Nachbestellen →</u></span>`;
  d.onclick = () => { m42F.filter = "nachbestellen"; go("m42lager"); };
  el.appendChild(d);
});

async function m42View(arg){
  if (arg === "nachbestellen") m42F.filter = "nachbestellen";
  const d = await api("/api/m42/list");
  const all = d.artikel || [];
  const list = all.filter(a => (m42F.filter === "nachbestellen" ? a.nachbestellen : m42F.filter === "inaktiv" ? !a.aktiv : a.aktiv) &&
    (!m42F.kat || a.kategorie === m42F.kat) && (!m42F.q || [a.nr, a.name, a.lagerort, a.kategorie].join(" ").toLowerCase().includes(m42F.q.toLowerCase())));
  const kats = [...new Set([...d.kategorien, ...all.map(a => a.kategorie).filter(Boolean)])];
  const act = all.filter(a => a.aktiv), wert = act.reduce((s, a) => s + a.wert, 0), low = act.filter(a => a.nachbestellen).length;
  $("#main").innerHTML = `<div class="page">${pageHead("Lager", "Kabel, Stecker, Profile, Bleche … mit Bestand, Mindestbestand und Buchungshistorie",
      expButtons("m42_lager", () => ({filter: m42F.filter === "nachbestellen" ? "nachbestellen" : ""})) + `<button class="btn pri" id="m42new">${ic("plus")} Neuer Artikel</button>`)}
    <div class="grid g4" style="margin-bottom:14px">
      <div class="card kpi"><div class="l">Artikel</div><div class="v">${act.length}</div><div class="s">${kats.filter(k => act.some(a => a.kategorie === k)).length} Kategorien</div></div>
      <div class="card kpi"><div class="l">Lagerwert (EK)</div><div class="v">${eur(wert)}</div><div class="s">Bestand × EK</div></div>
      <div class="card kpi"><div class="l">Nachbestellen</div><div class="v" style="color:${low ? "var(--warn)" : "inherit"}">${low}</div><div class="s">unter Mindestbestand</div></div>
      <div class="card kpi"><div class="l">Letzte Buchung</div><div class="v" style="font-size:18px">${dde(all.map(a => a.letzte || "").sort().pop() || "") || "–"}</div><div class="s">&nbsp;</div></div></div>
    <div class="row" style="margin-bottom:14px;align-items:center;flex-wrap:wrap">
      <div class="search" style="max-width:300px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="m42q" placeholder="Nr., Bezeichnung, Lagerort …" value="${esc(m42F.q)}"></div>
      <div class="seg" style="flex:none">${[["", "Aktiv"], ["nachbestellen", "Nachbestellen" + (low ? ` (${low})` : "")], ["inaktiv", "Inaktiv"]].map(([k, l]) => `<button class="${m42F.filter === k ? "on" : ""}" data-m42f="${k}">${l}</button>`).join("")}</div>
      <div class="chips" style="flex:none"><span class="chip ${!m42F.kat ? "on" : ""}" data-m42k="">Alle</span>${kats.map(k => `<span class="chip ${m42F.kat === k ? "on" : ""}" data-m42k="${esc(k)}">${esc(k)}</span>`).join("")}</div></div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Nr.</th><th>Bezeichnung</th><th>Kategorie</th><th>Lagerort</th><th class="r">Bestand</th><th class="r">Mindest</th><th class="r">EK</th><th class="r">Wert</th><th style="width:250px"></th></tr></thead>
      <tbody>${list.map(a => `<tr class="click" data-m42id="${a.id}"><td><b>${esc(a.nr || "")}</b></td><td>${esc(a.name)}${a.baustein ? `<div class="small muted">Baustein: ${esc(a.baustein)}</div>` : ""}</td><td><span class="badge">${esc(a.kategorie || "")}</span></td><td class="small">${esc(a.lagerort || "")}</td>
        <td class="r num">${a.nachbestellen ? `<span class="badge warn"><span class="dot"></span>${nde(a.bestand, a.bestand % 1 ? 2 : 0)}</span>` : `<b>${nde(a.bestand, a.bestand % 1 ? 2 : 0)}</b>`} ${esc(a.einheit || "")}</td>
        <td class="r num muted">${a.mindest ? nde(a.mindest, a.mindest % 1 ? 2 : 0) : "–"}</td><td class="r num">${eur(a.ek)}</td><td class="r num">${eur(a.wert)}</td>
        <td class="r" style="white-space:nowrap" onclick="event.stopPropagation()"><button class="btn sm" data-m42b="zugang" data-a="${a.id}" title="Zugang buchen">+ Zugang</button><button class="btn sm" data-m42b="abgang" data-a="${a.id}" title="Abgang buchen">− Abgang</button><button class="btn sm ghost" data-m42b="inventur" data-a="${a.id}" title="Inventur: gezählten Bestand eintragen">Inventur</button><button class="btn sm ghost" data-m42h="${a.id}" title="Historie">${ic("clock")}</button></td></tr>`).join("")
        || `<tr><td colspan="9" class="empty">${all.length ? "Keine Artikel für diesen Filter." : "Noch keine Lagerartikel. Mit „Neuer Artikel“ anlegen."}</td></tr>`}</tbody></table></div>
    <div class="small muted" style="margin-top:10px">Tipp: Wird im Projekt unter „Leistungen & Material“ ein Eintrag der Art <b>Material</b> mit der Lager-Artikelnummer als Nr. erfasst, bucht das Lager den Abgang automatisch. Oder im Projekt „Material aus Lager entnehmen“ verwenden.</div></div>`;
  bindCommon();
  $("#m42new").onclick = () => m42Edit(null, d);
  // v2.0.6: debounced + stale answers ignored (fast typing scrambled letters: "kabel" -> "kelab")
  $("#m42q").oninput = e => { m42F.q = e.target.value; clearTimeout(window._m42T);
    window._m42T = setTimeout(() => { const o = $("#m42q"); if (!o) return; const p = o.selectionStart, q0 = m42F.q;
      m42View().then(() => { const n = $("#m42q"); if (!n) return; if (n.value !== m42F.q) n.value = m42F.q; n.focus();
        const pp = q0 === m42F.q ? p : m42F.q.length; try { n.setSelectionRange(pp, pp); } catch (e2) {} }); }, 220); };
  $$("[data-m42f]").forEach(b => b.onclick = () => { m42F.filter = b.dataset.m42f; m42View(); });
  $$("[data-m42k]").forEach(b => b.onclick = () => { m42F.kat = b.dataset.m42k; m42View(); });
  $$("[data-m42id]").forEach(r => r.onclick = () => m42Edit(all.find(a => a.id == r.dataset.m42id), d));
  $$("[data-m42b]").forEach(b => b.onclick = () => m42Book(all.find(a => a.id == b.dataset.a), b.dataset.m42b));
  $$("[data-m42h]").forEach(b => b.onclick = () => m42Hist(all.find(a => a.id == b.dataset.m42h)));
  selectify({kind: "m42", rows: "tr[data-m42id]", id: "data-m42id", rerender: m42View, actions: [
    {label: "Excel", run: async ids => { await doExport("m42_lager", "xlsx", {ids}); return false; }},
    {label: "PDF", run: async ids => { await doExport("m42_lager", "pdf", {ids, filter: "auswahl"}); return false; }}]});
}

async function m42Edit(a, d){
  const n = !a; a = a || {einheit: "Stk", kategorie: m42F.kat || "Sonstiges", aktiv: 1};
  const kats = [...new Set([...(d.kategorien || []), a.kategorie].filter(Boolean))];
  const html = `<div class="fr"><div class="row"><label class="f" style="flex:.6">Artikel-Nr.<input class="in" id="m42nr" value="${esc(a.nr || "")}" placeholder="z. B. K-CAT7, FL-40-5"></label><label class="f">Bezeichnung<input class="in" id="m42na" value="${esc(a.name || "")}"></label></div>
    <div class="row"><label class="f">Kategorie<input class="in" id="m42ka" list="m42kl" value="${esc(a.kategorie || "")}"><datalist id="m42kl">${kats.map(k => `<option value="${esc(k)}">`).join("")}</datalist></label>
      <label class="f" style="flex:.5">Einheit<input class="in" id="m42eh" list="m42el" value="${esc(a.einheit || "Stk")}"><datalist id="m42el">${["Stk", "m", "m²", "kg", "Rolle", "Pkg", "l", "Fl."].map(k => `<option value="${k}">`).join("")}</datalist></label>
      <label class="f">Lagerort<input class="in" id="m42lo" value="${esc(a.lagerort || "")}" placeholder="z. B. Regal A2, Kragarm 1"></label></div>
    <div class="row">${n ? `<label class="f">Anfangsbestand<input class="in num" id="m42bs" value="0"></label>` : `<label class="f">Bestand<input class="in num" value="${nde(a.bestand, 2)}" disabled title="Bestand nur über Buchungen ändern"></label>`}
      <label class="f">Mindestbestand<input class="in num" id="m42mi" value="${nde(a.mindest || 0, 2)}"></label><label class="f">EK je Einheit €<input class="in num" id="m42ek" value="${nde(a.ek || 0)}"></label></div>
    <div class="row"><label class="f">Verknüpfter Baustein (optional, für VK bei Entnahme)<select class="in" id="m42ar"><option value="">– keiner –</option>${S.articles.map(x => `<option value="${x.id}" ${x.id == a.article_id ? "selected" : ""}>${esc((x.nr ? x.nr + " " : "") + x.name)} (${eur(x.price)})</option>`).join("")}</select></label>
      ${n ? "" : `<label class="chk" style="flex:none;align-self:flex-end;margin-bottom:8px"><input type="checkbox" id="m42ak" ${a.aktiv ? "checked" : ""}> aktiv</label>`}</div>
    <label class="f">Notiz<input class="in" id="m42no" value="${esc(a.notiz || "")}"></label></div>`;
  const btns = [{label: "Abbrechen"}, {label: "Speichern", cls: "pri", value: "ok", onClick: async mb => {
    const r = await api("/api/m42/save", {id: a.id || null, nr: $("#m42nr", mb).value, name: $("#m42na", mb).value, kategorie: $("#m42ka", mb).value, einheit: $("#m42eh", mb).value,
      lagerort: $("#m42lo", mb).value, mindest: $("#m42mi", mb).value, ek: $("#m42ek", mb).value, article_id: +$("#m42ar", mb).value || null, notiz: $("#m42no", mb).value,
      bestand: n ? $("#m42bs", mb).value : undefined, aktiv: n ? 1 : ($("#m42ak", mb).checked ? 1 : 0)});
    return !!(r && r.ok); }}];
  if (!n) btns.unshift({label: "Löschen", cls: "danger", value: "del"});
  const r = await modal(n ? "Neuer Lagerartikel" : "Lagerartikel " + (a.nr || a.name), html, btns, true);
  if (r === "del") { if (await confirmBox(`„${a.name}“ löschen? Artikel mit Buchungen werden nur deaktiviert.`)) { const x_ = await api("/api/m42/delete", {id: a.id}); if (x_.ok) toast(x_.info); } }
  if (r) { await reload(); m42View(); }
}

async function m42Book(a, art){
  const inv = art === "inventur";
  const html = `<div class="fr"><div class="small muted" style="margin-bottom:6px"><b>${esc(a.nr || "")} ${esc(a.name)}</b> · aktueller Bestand ${nde(a.bestand, 2)} ${esc(a.einheit || "")}</div>
    <div class="row"><label class="f">${inv ? "Gezählter Bestand" : "Menge"} (${esc(a.einheit || "")})<input class="in num" id="m42m" value="${inv ? nde(a.bestand, 2) : ""}"></label><label class="f">Datum<input type="date" class="in" id="m42d" value="${todayIso()}"></label></div>
    ${art === "abgang" ? `<label class="f">Projekt (optional – zählt als Materialverbrauch im Soll/Ist)<select class="in" id="m42p"><option value="">– kein Projekt –</option>${S.projects.filter(p => p.status !== "archiv").map(p => `<option value="${p.id}">${esc(p.nr + " " + p.name)}</option>`).join("")}</select></label>` : ""}
    <label class="f">Notiz<input class="in" id="m42n" placeholder="${art === "zugang" ? "z. B. Lieferant, Lieferschein-Nr." : inv ? "z. B. Jahresinventur" : "z. B. Ausschuss, Eigenbedarf"}"></label></div>`;
  const ok = await modal(M42_ARTEN[art] + " buchen", html, [{label: "Abbrechen"}, {label: "Buchen", cls: "pri", value: true, onClick: async mb => {
    const pid = $("#m42p", mb) ? +$("#m42p", mb).value || null : null;
    const r = await api("/api/m42/book", {artikel_id: a.id, art: pid && art === "abgang" ? "entnahme" : art, menge: $("#m42m", mb).value, datum: $("#m42d", mb).value, notiz: $("#m42n", mb).value, project_id: pid});
    if (r && r.ok) toast(`Gebucht – neuer Bestand ${nde(r.bestand, 2)} ${a.einheit || ""}`);
    return !!(r && r.ok); }}]);
  if (ok) { await reload(); if (view === "m42lager") m42View(); }
}

async function m42Hist(a){
  const h = await api("/api/m42/history?id=" + a.id);
  await modal("Historie – " + (a.nr ? a.nr + " " : "") + a.name, `<div class="scroll" style="max-height:60vh"><table class="t"><thead><tr><th>Datum</th><th>Art</th><th class="r">Menge</th><th class="r">Bestand danach</th><th>Projekt</th><th>Notiz</th></tr></thead>
    <tbody>${h.map(b => `<tr style="${b.storniert ? "opacity:.5;text-decoration:line-through" : ""}"><td class="num">${dde(b.datum)}</td><td><span class="badge ${b.menge > 0 ? "ok" : b.menge < 0 ? "warn" : ""}">${M42_ARTEN[b.art] || esc(b.art)}</span></td>
      <td class="r num">${b.menge > 0 ? "+" : ""}${nde(b.menge, 2)}</td><td class="r num">${nde(b.bestand_nach, 2)}</td><td class="small">${b.pnr ? `<a href="#" data-m42p="${b.project_id}">${esc(b.pnr)}</a>` : ""}</td><td class="small">${esc(b.notiz || "")}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Keine Buchungen.</td></tr>`}</tbody></table></div>`,
    [{label: "Schließen"}], true, mb => $$("[data-m42p]", mb).forEach(x => x.onclick = e => { e.preventDefault(); $(".mf .btn", mb).click(); go("project", +x.dataset.m42p); }));
}

// ---------------- project: take material from stock ----------------
async function m42Entnahme(p){
  const arts = (S.m42 && S.m42.artikel) || [];
  if (!arts.length) { toast("Noch keine Lagerartikel angelegt (Stammdaten → Lager)", true); return; }
  const bsPrice = a => { const b = a.article_id ? S.articles.find(x => x.id == a.article_id) : null; return b ? b.price : Math.round(a.ek * (1 + (S.settings.aufschlag ?? 20) / 100) * 100) / 100; };
  const html = `<div class="fr"><label class="f">Lagerartikel<select class="in" id="m42ea">${arts.map(a => `<option value="${a.id}">${esc((a.nr ? a.nr + " · " : "") + a.name)} – Bestand ${nde(a.bestand, 2)} ${esc(a.einheit || "")}</option>`).join("")}</select></label>
    <div class="row"><label class="f">Menge<input class="in num" id="m42em" value="1"></label><label class="f">Datum<input type="date" class="in" id="m42ed" value="${todayIso()}"></label><label class="f">VK je Einheit € (für Abrechnung)<input class="in num" id="m42ev"></label></div>
    <label class="chk"><input type="checkbox" id="m42ee" checked> als Material-Position unter „Leistungen & Material“ eintragen (abrechenbar)</label>
    <label class="f">Notiz / Beschreibung<input class="in" id="m42en" placeholder="z. B. Verkabelung Besprechungsraum 2"></label>
    <div class="small muted" id="m42ei"></div></div>`;
  const ok = await modal("Material aus Lager entnehmen", html, [{label: "Abbrechen"}, {label: "Entnehmen", cls: "pri", value: true, onClick: async mb => {
    const r = await api("/api/m42/entnahme", {project_id: p.id, artikel_id: +$("#m42ea", mb).value, menge: $("#m42em", mb).value, datum: $("#m42ed", mb).value,
      vk: $("#m42ev", mb).value.trim() === "" ? null : pnum($("#m42ev", mb).value), als_eintrag: $("#m42ee", mb).checked, notiz: $("#m42en", mb).value});
    if (r && r.ok) { if (r.warn) toast(r.warn, true); toast("Entnahme gebucht"); }
    return !!(r && r.ok); }}], false, mb => {
      const upd = () => { const a = arts.find(x => x.id == $("#m42ea", mb).value); if (!a) return; $("#m42ev", mb).value = nde(bsPrice(a));
        $("#m42ei", mb).textContent = `EK ${eur(a.ek)} je ${a.einheit || "Einheit"} · Bestand ${nde(a.bestand, 2)}`; };
      $("#m42ea", mb).onchange = upd; upd(); });
  if (ok) { await reload(); vProject(p.id); }
}
EXT.after.push((vn, id) => {
  if (vn !== "vProject" || pTab !== "entries") return;
  const b0 = $("#ebom"); if (!b0 || $("#m42ent")) return;
  const b = document.createElement("button"); b.className = "btn"; b.style.flex = "none"; b.id = "m42ent"; b.innerHTML = `${ic("m42box")} Material aus Lager entnehmen`;
  b.onclick = async () => { const p = await api("/api/project?id=" + id); m42Entnahme(p); };
  b0.after(b);
});
