"use strict";
// m41 - Aufmass und Kalkulation aus Stueckliste (UI, Reiter auf der Projektseite)
// Autor: T. Pfeiffer
const M41_EH = {m: "m", m2: "m²", m3: "m³", Stk: "Stk", kg: "kg", h: "Std"};
let m41Edit = null;   // Aufmass row being edited
let m41K = null;      // current calculation {pid, id, name, data, meta}

M4X.tab({key: "m41a", label: "Aufmaß", render: m41AufmassRender});
M4X.tab({key: "m41k", label: "Kalkulation", render: m41KalkRender});

// ---------------- Aufmass ----------------
function m41Masse(r){
  if (r.modus === "formel") return esc(r.formel || "");
  const v = ["l", "b", "h"].filter(k => r[k]).map(k => M4X.num(r[k], 3));
  if (r.anz != null && r.anz !== 1) v.push(M4X.num(r.anz, 3) + " Stk");
  return v.join(" × ");
}
async function m41AufmassRender(T, p){
  const d = await api("/api/m41/aufmass?project_id=" + p.id);
  const rows = d.rows || [];
  const e = m41Edit && m41Edit.project_id === p.id ? m41Edit : {modus: "lbh", einheit: "m2", anz: 1};
  const sum = rows.reduce((a, r) => a + (r.ergebnis || 0) * (r.preis || 0), 0);
  // input prefill: decimal comma, no thousands dots (server would read "1.250" as 1.25)
  const f = v => v == null || v === "" ? "" : String(Math.round(Number(v) * 1000) / 1000).replace(".", ",");
  T.innerHTML = `<div class="card" style="margin-bottom:14px"><div class="hd"><h3>${e.id ? "Aufmaß-Position bearbeiten" : "Aufmaß erfassen"}</h3>
      <div class="act"><div class="seg" id="m41mod"><button data-m="lbh" class="${e.modus !== "formel" ? "on" : ""}">L × B × H × Anzahl</button><button data-m="formel" class="${e.modus === "formel" ? "on" : ""}">Formel</button></div></div></div><div class="bd">
    <div class="row" style="flex-wrap:wrap;align-items:flex-end">
      <label class="f" style="flex:.35">Pos.<input class="in" id="m41pos" value="${esc(e.pos || String(rows.length + 1))}"></label>
      <label class="f" style="flex:1.2">Baustein (optional)<select class="in" id="m41art"><option value="">– frei –</option>${S.articles.map(a => `<option value="${a.id}" ${a.id == e.article_id ? "selected" : ""}>${esc((a.nr ? a.nr + " " : "") + a.name)} (${eur(a.price)})</option>`).join("")}</select></label>
      <label class="f" style="flex:1.6">Beschreibung<input class="in" id="m41bes" value="${esc(e.beschreibung || "")}" placeholder="z. B. Geländerfüllung Lochblech, Kabelkanal 60x110"></label>
    </div>
    <div class="row" style="flex-wrap:wrap;align-items:flex-end;margin-top:8px">
      <span id="m41lbh" style="display:${e.modus === "formel" ? "none" : "contents"}">
        <label class="f" style="flex:.5">Länge<input class="in num m41v" id="m41l" value="${f(e.l)}"></label>
        <label class="f" style="flex:.5">Breite<input class="in num m41v" id="m41b" value="${f(e.b)}"></label>
        <label class="f" style="flex:.5">Höhe<input class="in num m41v" id="m41h" value="${f(e.h)}"></label>
        <label class="f" style="flex:.45">Anzahl<input class="in num m41v" id="m41n" value="${f(e.anz ?? 1)}"></label></span>
      <label class="f" id="m41fw" style="flex:2;display:${e.modus === "formel" ? "" : "none"}">Formel (+ − × / ( ), Komma erlaubt, z. B. 2*3,5+1,2)<input class="in m41v" id="m41f" value="${esc(e.formel || "")}" style="font-family:Consolas,monospace"></label>
      <label class="f" style="flex:.45">Einheit<select class="in" id="m41eh">${Object.entries(M41_EH).map(([k, l]) => `<option value="${k}" ${e.einheit === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="f" style="flex:.6">Einzelpreis €<input class="in num" id="m41pr" value="${e.preis != null ? nde(e.preis) : ""}"></label>
      <div class="f" style="flex:.8"><span class="small muted">Ergebnis</span><div id="m41erg" class="num" style="font:600 18px/34px var(--disp)">–</div></div>
      ${e.id ? `<button class="btn" style="flex:none" id="m41can">Abbrechen</button>` : ""}
      <button class="btn pri" style="flex:none" id="m41save">${ic(e.id ? "save" : "plus")} ${e.id ? "Speichern" : "Hinzufügen"}</button>
    </div></div></div>
    <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th style="width:28px"><input type="checkbox" id="m41all" checked style="accent-color:var(--acc)"></th><th>Pos.</th><th>Beschreibung</th><th>Maße / Formel</th><th class="r">Ergebnis</th><th class="r">EP</th><th class="r">Gesamt</th><th></th><th></th></tr></thead>
      <tbody>${rows.map(r => `<tr><td><input type="checkbox" class="m41sel" value="${r.id}" checked style="accent-color:var(--acc)"></td><td class="num">${esc(r.pos || "")}</td><td><b>${esc(r.beschreibung || "")}</b></td>
        <td class="small" style="font-family:Consolas,monospace">${m41Masse(r)}</td><td class="r num"><b>${M4X.num(r.ergebnis, 3)}</b> ${M41_EH[r.einheit] || esc(r.einheit)}</td>
        <td class="r num">${eur(r.preis)}</td><td class="r num">${eur((r.ergebnis || 0) * (r.preis || 0))}</td>
        <td>${r.invoice_id ? `<span class="badge ok click" data-inv="${r.invoice_id}">in Rechnung</span>` : ""}</td>
        <td class="r" style="white-space:nowrap"><button class="btn sm ghost" data-m41ed="${r.id}" title="Bearbeiten">✎</button><button class="btn sm ghost danger" data-m41del="${r.id}" title="Löschen">${ic("trash")}</button></td></tr>`).join("") || `<tr><td colspan="9" class="empty">Noch kein Aufmaß. Maße oben eintragen – das Ergebnis wird sofort berechnet.</td></tr>`}</tbody>
      <tfoot><tr><td colspan="6">Summe</td><td class="r num">${eur(sum)}</td><td colspan="2"></td></tr></tfoot></table></div>
    <div class="row" style="margin-top:12px;justify-content:flex-end">${expButtons("m41_aufmass", {id: p.id})}<span class="sp"></span>
      <button class="btn" style="flex:none" id="m41toA">${ic("inv")} In Angebot übernehmen</button><button class="btn pri" style="flex:none" id="m41toR">${ic("inv")} In Rechnung übernehmen</button></div>`;
  bindCommon(T);
  let mode = e.modus === "formel" ? "formel" : "lbh", tmr = 0;
  const show = (txt, bad) => { const el = $("#m41erg", T); el.textContent = txt; el.style.color = bad ? "var(--bad)" : ""; el.style.fontSize = bad ? "12px" : ""; };
  const upd = () => {
    const eh = M41_EH[$("#m41eh", T).value] || "";
    if (mode === "lbh") {
      const v = ["#m41l", "#m41b", "#m41h"].map(s => $(s, T).value.trim()).filter(Boolean).map(pnum).filter(x => x !== 0);
      const n = $("#m41n", T).value.trim() ? pnum($("#m41n", T).value) : 1;
      const r = (v.length ? v.reduce((a, b) => a * b, 1) : 1) * n;
      show(M4X.num(r, 3) + " " + eh);
    } else {
      clearTimeout(tmr);
      const fx = $("#m41f", T).value;
      if (!fx.trim()) { show("–"); return; }
      tmr = setTimeout(async () => { const r = await api("/api/m41/formel", {formel: fx}, {quiet: true}); if (r.ok) show(M4X.num(r.wert, 3) + " " + eh); else show(r.error || "Fehler", true); }, 250);
    }
  };
  $$("#m41mod button", T).forEach(b => b.onclick = () => { mode = b.dataset.m; $$("#m41mod button", T).forEach(x => x.classList.toggle("on", x === b));
    $("#m41lbh", T).style.display = mode === "formel" ? "none" : "contents"; $("#m41fw", T).style.display = mode === "formel" ? "" : "none"; upd(); });
  $$(".m41v", T).forEach(i => i.oninput = upd);
  $("#m41eh", T).onchange = upd;
  $("#m41art", T).onchange = ev => { const a = S.articles.find(a => a.id == ev.target.value); if (!a) return;
    if (!$("#m41bes", T).value.trim()) $("#m41bes", T).value = a.name; $("#m41pr", T).value = nde(a.price);
    const u = (a.unit || "").toLowerCase().replace("²", "2").replace("³", "3"); const map = {m: "m", m2: "m2", qm: "m2", m3: "m3", stk: "Stk", "stück": "Stk", kg: "kg", std: "h", h: "h"};
    if (map[u]) { $("#m41eh", T).value = map[u]; upd(); } };
  $("#m41save", T).onclick = async () => {
    const body = {id: e.id || null, project_id: p.id, pos: $("#m41pos", T).value, beschreibung: $("#m41bes", T).value, modus: mode, einheit: $("#m41eh", T).value,
      article_id: +$("#m41art", T).value || null, preis: $("#m41pr", T).value.trim() ? pnum($("#m41pr", T).value) : "", preis_manuell: $("#m41pr", T).value.trim() !== ""};
    const nv = s => { const t = $(s, T).value.trim(); return t ? pnum(t) : ""; };   // same parsing as the live preview
    if (mode === "lbh") Object.assign(body, {l: nv("#m41l"), b: nv("#m41b"), h: nv("#m41h"), anz: nv("#m41n")});
    else body.formel = $("#m41f", T).value;
    const r = await api("/api/m41/aufmass/save", body);
    if (r && r.ok) { m41Edit = null; toast("Aufmaß gespeichert"); m41AufmassRender(T, p); }
  };
  if ($("#m41can", T)) $("#m41can", T).onclick = () => { m41Edit = null; m41AufmassRender(T, p); };
  $$("[data-m41ed]", T).forEach(b => b.onclick = () => { m41Edit = rows.find(r => r.id == b.dataset.m41ed); m41AufmassRender(T, p); });
  $$("[data-m41del]", T).forEach(b => b.onclick = async () => { if (!await confirmBox("Aufmaß-Position löschen?")) return; await api("/api/m41/aufmass/delete", {id: +b.dataset.m41del}); m41AufmassRender(T, p); });
  $("#m41all", T).onchange = ev => $$(".m41sel", T).forEach(c => c.checked = ev.target.checked);
  const toDoc = async typ => {
    const ids = $$(".m41sel", T).filter(c => c.checked).map(c => +c.value);
    if (!ids.length) { toast("Keine Position ausgewählt", true); return; }
    const r = await api("/api/m41/aufmass/to_doc", {project_id: p.id, ids, typ});
    if (r && r.ok) { toast(`${r.n} Position(en) in ${typ === "angebot" ? "Angebot" : "Rechnung"} (Entwurf) übernommen`); M4X.openDoc(r.id); }
  };
  $("#m41toA", T).onclick = () => toDoc("angebot");
  $("#m41toR", T).onclick = () => toDoc("rechnung");
  upd();
}

// ---------------- Kalkulation ----------------
function m41Calc(data, meta){
  // mirror of m41_kalk_calc (Python) for live display; the server recalculates on save
  const n = v => v === "" || v == null ? null : pnum(v);
  const satz = n(data.stundensatz) ?? (meta.stundensatz || 0), mz = n(data.mat_zuschlag) ?? (meta.aufschlag || 0);
  const gk = n(data.gk) || 0, gw = n(data.gewinn) || 0, fremd = n(data.fremd) || 0;
  let material = 0, kg = 0, miss = 0;
  const rows = (data.rows || []).map(r => {
    if (r.use === false) return Object.assign({}, r, {summe: 0, ek_calc: 0, skip: true});
    const qty = pnum(r.qty), masse = pnum(r.masse_kg), pk0 = n(r.preis_kg) ?? (meta.preise[r.material || ""] ?? null), ek = n(r.ek_stk);
    let e = 0, src = "fehlt";
    if (ek && ek > 0) { e = ek; src = "EK"; } else if (pk0 != null && masse) { e = masse * pk0; src = "kg"; } else miss++;
    const s = Math.round(e * qty * 100) / 100; material += s; kg += masse * qty;
    return Object.assign({}, r, {ek_calc: e, summe: s, quelle: src, pk_used: pk0});
  });
  const std = (data.arbeit || []).reduce((a, x) => a + pnum(x.std), 0), lohn = std * satz, mzu = material * mz / 100;
  const herst = material + mzu + lohn + fremd, gke = herst * gk / 100, selbst = herst + gke, gew = selbst * gw / 100;
  const r2 = v => Math.round((v + 1e-9) * 100) / 100;
  return {rows, material: r2(material), kg, mz, mat_zuschlag: r2(mzu), stunden: std, satz, lohn: r2(lohn), fremd: r2(fremd), herstell: r2(herst), gk, gk_eur: r2(gke),
    selbst: r2(selbst), gw, gewinn: r2(gew), preis: r2(selbst + gew), miss};
}
async function m41KalkRender(T, p){
  const meta = await api("/api/m41/kalk?project_id=" + p.id);
  if (!m41K || m41K.pid !== p.id) {
    m41K = {pid: p.id, id: null, name: "", data: JSON.parse(JSON.stringify(meta.default)), dirty: false};
    if (meta.list.length) { const k = await api("/api/m41/kalk?id=" + meta.list[0].id); m41K = {pid: p.id, id: k.id, name: k.name, data: k.data, angebot_id: k.angebot_id, dirty: false}; }
  }
  const K = m41K, D = K.data;
  D.rows = D.rows || []; D.arbeit = D.arbeit || [];
  const ph = (v, d) => v == null || v === "" ? "" : nde(v, d);
  const mats = Object.keys(meta.preise || {});
  T.innerHTML = `<style>#m41kr .in{padding:5px 6px;font-size:12.5px}#m41kr td{padding-left:4px;padding-right:4px}</style><div class="row" style="margin-bottom:12px;align-items:flex-end;flex-wrap:wrap">
      <label class="f" style="flex:1">Kalkulation<select class="in" id="m41ks"><option value="">+ neue Kalkulation</option>${meta.list.map(k => `<option value="${k.id}" ${k.id == K.id ? "selected" : ""}>${esc(k.name)} · ${eur(k.angebotspreis)}</option>`).join("")}</select></label>
      <label class="f" style="flex:1.4">Name<input class="in" id="m41kn" value="${esc(K.name)}" placeholder="z. B. Treppengeländer EG–2.OG"></label>
      <label class="f" style="flex:1.4">Positionstext im Angebot (pauschal)<input class="in" id="m41kt" value="${esc(D.titel || "")}" placeholder="leer = Name"></label>
      <button class="btn pri" style="flex:none" id="m41ksave">${ic("save")} Speichern</button>
      ${K.id ? `<button class="btn ghost danger" style="flex:none" id="m41kdel" title="Kalkulation löschen">${ic("trash")}</button>` : ""}</div>
    <div class="grid" style="grid-template-columns:minmax(0,1.8fr) minmax(270px,1fr);align-items:start">
    <div>
      <div class="card" style="margin-bottom:14px"><div class="hd"><h3>Material (Stückliste)</h3><div class="act">
        <button class="btn sm" id="m41kup">${ic("up")} Stückliste importieren</button>
        ${meta.boms.length ? `<select class="in" id="m41kpf" style="width:auto;padding:3px 8px;font-size:12px"><option value="">aus Projektordner …</option>${meta.boms.map(b => `<option value="${b.id}">${esc(b.name)}</option>`).join("")}</select>` : ""}
        <button class="btn sm" id="m41kadd">${ic("plus")} Zeile</button></div></div>
        <div class="scroll" style="max-height:420px;overflow:auto"><table class="t"><thead><tr><th></th><th>Nr.</th><th>Benennung</th><th class="r">Menge</th><th>Material</th><th class="r">kg/Stk</th><th class="r">€/kg</th><th class="r">EK/Stk €</th><th class="r">Summe</th><th></th></tr></thead>
        <tbody id="m41kr">${D.rows.map((r, i) => `<tr data-i="${i}"><td><input type="checkbox" data-f="use" ${r.use === false ? "" : "checked"} style="accent-color:var(--acc)"></td>
          <td><input class="in" data-f="nr" value="${esc(r.nr || "")}" style="width:72px"></td><td><input class="in" data-f="name" value="${esc(r.name || "")}" style="min-width:96px"></td>
          <td><input class="in num" data-f="qty" value="${ph(r.qty, 2)}" style="width:52px;text-align:right"></td>
          <td><input class="in" data-f="material" list="m41mats" value="${esc(r.material || "")}" style="width:92px"></td>
          <td><input class="in num" data-f="masse_kg" value="${ph(r.masse_kg, 3)}" style="width:60px;text-align:right"></td>
          <td><input class="in num" data-f="preis_kg" value="${ph(r.preis_kg, 2)}" style="width:50px;text-align:right" data-ph="1"></td>
          <td><input class="in num" data-f="ek_stk" value="${ph(r.ek_stk, 2)}" style="width:58px;text-align:right" placeholder="auto"></td>
          <td class="r num m41ks" style="white-space:nowrap"></td><td><button class="btn sm ghost danger" data-m41kx="${i}">×</button></td></tr>`).join("") || `<tr><td colspan="10" class="empty">Stückliste importieren (Inventor CSV/XLSX) oder Zeilen von Hand anlegen.</td></tr>`}</tbody></table></div>
        <datalist id="m41mats">${mats.map(m => `<option value="${esc(m)}">`).join("")}</datalist>
        <div class="bd small muted" style="padding-top:6px">EK/Stk leer = Masse × €/kg (€/kg leer = Materialpreis aus den Einstellungen). EK/Stk eingetragen = gilt vorrangig (z. B. Normteile, Zukaufteile).</div></div>
      <div class="card"><div class="hd"><h3>Arbeitszeit</h3><div class="act"><button class="btn sm" id="m41aadd">${ic("plus")} Arbeitsgang</button></div></div><div class="bd">
        <table class="t"><tbody id="m41ar">${D.arbeit.map((a, i) => `<tr data-i="${i}"><td><input class="in" data-a="bez" value="${esc(a.bez || "")}"></td><td style="width:110px"><input class="in num" data-a="std" value="${ph(a.std, 2)}" style="text-align:right"></td><td style="width:40px" class="small muted">Std</td><td style="width:36px"><button class="btn sm ghost danger" data-m41ax="${i}">×</button></td></tr>`).join("")}</tbody></table>
        <div class="row" style="margin-top:10px;flex-wrap:wrap">
          <label class="f">Stundensatz €<input class="in num" id="m41z_stundensatz" value="${ph(D.stundensatz, 2)}" placeholder="${nde(meta.stundensatz)}"></label>
          <label class="f">Material-Zuschlag %<input class="in num" id="m41z_mat_zuschlag" value="${ph(D.mat_zuschlag, 1)}" placeholder="${nde(meta.aufschlag, 1)}"></label>
          <label class="f">Gemeinkosten %<input class="in num" id="m41z_gk" value="${ph(D.gk, 1)}"></label>
          <label class="f">Gewinn / Marge %<input class="in num" id="m41z_gewinn" value="${ph(D.gewinn, 1)}"></label></div>
        <div class="row" style="margin-top:8px"><label class="f" style="flex:.5">Fremdleistung €<input class="in num" id="m41z_fremd" value="${ph(D.fremd, 2)}"></label>
          <label class="f">Bezeichnung Fremdleistung<input class="in" id="m41z_fremd_text" value="${esc(D.fremd_text || "")}" placeholder="z. B. Feuerverzinkung, Pulverbeschichtung, Laserzuschnitt"></label></div>
      </div></div>
    </div>
    <div class="card" style="position:sticky;top:10px"><div class="hd"><h3>Ergebnis</h3></div><div class="bd" id="m41res"></div>
      <div class="bd" style="border-top:1px solid var(--line);display:flex;flex-direction:column;gap:8px">
        <button class="btn pri" id="m41kap" style="justify-content:center">${ic("inv")} Als Angebot – Pauschalposition</button>
        <button class="btn" id="m41kad" style="justify-content:center">${ic("inv")} Als Angebot – detailliert</button>
        <button class="btn" id="m41kpdf" style="justify-content:center">${ic("pdf")} Kalkulation als PDF</button>
        ${K.angebot_id ? `<div class="small muted">Zuletzt übernommen: <a href="#" data-inv="${K.angebot_id}">Angebot öffnen</a></div>` : ""}
      </div></div></div>`;
  bindCommon(T);
  const fnum = ["qty", "masse_kg", "preis_kg", "ek_stk"];
  const readAll = () => {
    $$("#m41kr tr[data-i]", T).forEach(tr => { const r = D.rows[+tr.dataset.i]; $$("[data-f]", tr).forEach(el => { const k = el.dataset.f;
      r[k] = k === "use" ? el.checked : fnum.includes(k) ? (el.value.trim() === "" ? (k === "qty" || k === "masse_kg" ? 0 : null) : pnum(el.value)) : el.value; }); });
    $$("#m41ar tr[data-i]", T).forEach(tr => { const a = D.arbeit[+tr.dataset.i]; a.bez = $("[data-a=bez]", tr).value; a.std = pnum($("[data-a=std]", tr).value); });
    ["stundensatz", "mat_zuschlag", "gk", "gewinn", "fremd"].forEach(k => { const v = $("#m41z_" + k, T).value.trim(); D[k] = v === "" ? null : pnum(v); });
    D.fremd_text = $("#m41z_fremd_text", T).value; D.titel = $("#m41kt", T).value; K.name = $("#m41kn", T).value;
  };
  const show = () => {
    readAll();
    const c = m41Calc(D, meta);
    $$("#m41kr tr[data-i]", T).forEach(tr => { const r = c.rows[+tr.dataset.i]; const el = $(".m41ks", tr);
      el.innerHTML = r.skip ? `<span class="muted">–</span>` : eur(r.summe) + (r.quelle === "fehlt" ? ` <span title="kein Preis" style="color:var(--bad)">!</span>` : "");
      const pk = $("[data-f=preis_kg]", tr); pk.placeholder = r.pk_used != null && (r.preis_kg == null) ? nde(r.pk_used) : ""; });
    const L = (l, b, v, strong, col) => `<div class="kv" style="grid-template-columns:1fr auto;${strong ? "font-weight:600;border-top:1px solid var(--line);padding-top:4px;margin-top:2px" : ""}"><span class="sub">${l}${b ? `<span class="small muted"> · ${b}</span>` : ""}</span><span class="r num" ${col ? `style="color:${col}"` : ""}>${eur(v)}</span></div>`;
    $("#m41res", T).innerHTML = L("Material", nde(c.kg, 1) + " kg", c.material) + L("Material-Zuschlag", nde(c.mz, 1) + " %", c.mat_zuschlag) +
      L("Lohn", nde(c.stunden, 1) + " Std × " + eur(c.satz), c.lohn) + (c.fremd ? L(esc(D.fremd_text || "Fremdleistung"), "", c.fremd) : "") +
      L("Herstellkosten", "", c.herstell, true) + L("Gemeinkosten", nde(c.gk, 1) + " %", c.gk_eur) + L("Selbstkosten", "", c.selbst, true) +
      L("Gewinn / Marge", nde(c.gw, 1) + " %", c.gewinn) +
      `<div style="margin-top:10px;padding:10px 12px;border-radius:10px;background:var(--accsoft)"><div class="small muted">Angebotspreis (netto, ohne USt)</div><div class="num" style="font:600 24px/1.2 var(--disp);color:var(--acc2)">${eur(c.preis)}</div>
       ${c.stunden ? `<div class="small muted">entspricht ${eur((c.preis - c.material - c.mat_zuschlag - c.fremd) / c.stunden)} je Std (inkl. Zuschläge)</div>` : ""}</div>` +
      (c.miss ? `<div class="small" style="color:var(--bad);margin-top:6px">${c.miss} Material-Position(en) ohne Preis – mit 0 € gerechnet.</div>` : "");
  };
  const save = async () => {
    readAll();
    if (!K.name.trim()) K.name = "Kalkulation " + dde(todayIso());
    const r = await api("/api/m41/kalk/save", {id: K.id, project_id: p.id, name: K.name, data: D});
    if (r && r.ok) { K.id = r.id; toast("Kalkulation gespeichert"); return true; }
    return false;
  };
  const addBom = rows => { readAll(); rows.forEach(x => D.rows.push({nr: x.nr || "", name: x.name || "", qty: x.qty || 1, unit: x.unit || "Stk", material: x.material || "", masse_kg: x.masse_kg || 0, preis_kg: null, ek_stk: null, use: true}));
    toast(rows.length + " Stücklisten-Position(en) übernommen – Speichern nicht vergessen"); m41KalkRender(T, p); };
  $$("#m41kr input, #m41ar input, [id^=m41z_]", T).forEach(el => { el.oninput = show; el.onchange = show; });
  $("#m41ks", T).onchange = async ev => { const v = ev.target.value;
    if (!v) m41K = {pid: p.id, id: null, name: "", data: JSON.parse(JSON.stringify(meta.default))};
    else { const k = await api("/api/m41/kalk?id=" + v); m41K = {pid: p.id, id: k.id, name: k.name, data: k.data, angebot_id: k.angebot_id}; }
    m41KalkRender(T, p); };
  $("#m41ksave", T).onclick = async () => { if (await save()) m41KalkRender(T, p); };
  if ($("#m41kdel", T)) $("#m41kdel", T).onclick = async () => { if (!await confirmBox(`Kalkulation „${K.name}“ löschen?`)) return; await api("/api/m41/kalk/delete", {id: K.id}); m41K = null; m41KalkRender(T, p); };
  $("#m41kadd", T).onclick = () => { readAll(); D.rows.push({nr: "", name: "", qty: 1, unit: "Stk", material: "", masse_kg: 0, use: true}); m41KalkRender(T, p); };
  $("#m41aadd", T).onclick = () => { readAll(); D.arbeit.push({bez: "", std: 0}); m41KalkRender(T, p); };
  $$("[data-m41kx]", T).forEach(b => b.onclick = () => { readAll(); D.rows.splice(+b.dataset.m41kx, 1); m41KalkRender(T, p); });
  $$("[data-m41ax]", T).forEach(b => b.onclick = () => { readAll(); D.arbeit.splice(+b.dataset.m41ax, 1); m41KalkRender(T, p); });
  $("#m41kup", T).onclick = () => pickFiles(".csv,.xlsx,.xlsm,.txt", async fs => { const r = await upload("/api/upload/bom", fs[0]); if (!r.ok) { toast(r.error, true); return; } addBom(r.rows); });
  if ($("#m41kpf", T)) $("#m41kpf", T).onchange = async ev => { if (!ev.target.value) return; const r = await api("/api/m41/bom_file", {file_id: +ev.target.value}); if (r && r.ok) addBom(r.rows); };
  const toAng = async mode => { if (!await save()) return; const r = await api("/api/m41/kalk/angebot", {id: K.id, mode});
    if (r && r.ok) { toast(`Angebot (Entwurf) über ${eur(r.summe)} angelegt`); m41K = null; M4X.openDoc(r.id); } };
  $("#m41kap", T).onclick = () => toAng("pauschal");
  $("#m41kad", T).onclick = () => toAng("detail");
  $("#m41kpdf", T).onclick = async () => { if (!await save()) return; const r = await api("/api/m41/kalk/pdf", {id: K.id}); if (r && r.ok) toast("PDF gespeichert: " + r.path.split(/[\\/]/).pop() + " (Projektordner)"); };
  show();
}
