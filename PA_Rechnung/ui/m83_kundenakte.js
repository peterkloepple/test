// PA Rechnung v2.0.19 - UI-Modul m83_kundenakte: Kunden-Zeitstrahl
// Seite "Kundenakte" (Stammdaten, arg = Kunden-ID), Karte im Kunden-Detail, Notizen/Telefonnotizen/Wiedervorlagen,
// Hinweis auf faellige Wiedervorlagen in der Uebersicht, Export PDF/Excel.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m83 = '<path d="M12 3v18"/><circle cx="12" cy="6" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="18" r="2"/><path d="M14 6h6M4 12h6M14 18h6"/>';
  const COL = {angebot:"#8e6be0", auftrag:"#6a48e0", rechnung:"#0a84ff", storno:"#ff453a", zahlung:"#30d158", mahnung:"#ff9f0a", mail_aus:"#5ac8fa",
    mail_ein:"#64d2ff", brief:"#8a8599", projekt:"#3d6f8f", termin:"#ff9f0a", fahrt:"#a2845e", unterricht:"#1f9d6b", datei:"#6b6478",
    notiz:"#bf5af2", telefon:"#bf5af2", gespraech:"#bf5af2", wiedervorlage:"#ff375f", sonstiges:"#8e8e93"};
  const GRP = [["", "Alle"], ["angebot,auftrag,rechnung,storno,zahlung,mahnung", "Belege & Geld"], ["mail_aus,mail_ein,brief", "Post & Mail"],
    ["projekt,datei,fahrt,termin,unterricht", "Projekte & Termine"], ["notiz,telefon,gespraech,wiedervorlage", "Notizen"]];
  const NOTIZ = {notiz:"Notiz", telefon:"Telefonnotiz", gespraech:"Gespräch", wiedervorlage:"Wiedervorlage"};
  const F = {art:"", q:"", cid:null};

  EXT.nav.push({key:"m83akte", label:"Kundenakte", icon:"m83", section:"Stammdaten", cnt:() => (S.m83 && S.m83.wv_faellig) ? "⏰ " + S.m83.wv_faellig : ""});
  EXT.views.m83akte = view83;

  function openRef(e){
    const r = e.ref || {};
    if (r.kind === "invoice") openInvoice(r.id);
    else if (r.kind === "project") go("project", r.id);
    else if (r.kind === "trip") go("trips");
    else if (r.kind === "school") go("school");
    else if (r.kind === "kal") go("kalender");
    else if (r.kind === "mail") go("mails");
    else if (r.kind === "brief") go("inv");
    else if (r.kind === "notiz") editNote({id:r.id});
  }

  function evRow(e, compact){
    const c = COL[e.art] || "#8e8e93";
    return `<tr class="click" data-m83e='${esc(JSON.stringify({ref:e.ref, art:e.art}))}'>
      <td class="num" style="white-space:nowrap">${dde(e.datum)}${e.zeit ? `<div class="small muted">${esc(e.zeit)}</div>` : ""}</td>
      <td style="white-space:nowrap"><span class="badge" style="background:${c}22;color:${c}"><span class="dot" style="background:${c}"></span>${esc(e.art_de)}</span></td>
      <td><b>${esc(e.titel)}</b>${e.text && !compact ? `<div class="small muted" style="white-space:pre-line">${esc(e.text.slice(0, 220))}</div>` : (e.text && compact ? `<div class="small muted">${esc(e.text.slice(0, 90))}</div>` : "")}</td>
      <td class="r num">${e.betrag !== null && e.betrag !== undefined && e.betrag !== "" ? eur(e.betrag) : ""}</td>
      <td class="small muted">${esc(e.status || "")}</td></tr>`;
  }
  function bindRows(root, events){
    $$("[data-m83e]", root).forEach(tr => tr.onclick = () => { try { openRef(JSON.parse(tr.dataset.m83e)); } catch (e) { console.error(e); } });
  }

  async function editNote(n, cid, after){
    if (n && n.id && !n.customer_id) { const r = await api("/api/m83/notiz?id=" + n.id); n = r.notiz || n; }
    n = n || {}; const neu = !n.id;
    const cust = n.customer_id || cid;
    const projs = S.projects.filter(p => p.customer_id == cust);
    const html = `<div class="fr"><div class="row"><label class="f" style="flex:.8">Art<select class="in" id="m83a">${Object.entries(NOTIZ).map(([k, l]) => `<option value="${k}" ${(n.art || "telefon") === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="f" style="flex:.7">Datum<input type="date" class="in" id="m83d" value="${esc(n.datum || todayIso())}"></label>
        <label class="f" style="flex:.45">Uhrzeit<input type="time" class="in" id="m83z" value="${esc(n.zeit || (neu ? new Date().toTimeString().slice(0, 5) : ""))}"></label></div>
      <label class="f">Betreff<input class="in" id="m83t" value="${esc(n.titel || "")}" placeholder="z. B. Rückruf wegen Angebot Saalumbau"></label>
      <label class="f">Text<textarea class="in" id="m83x" rows="6">${esc(n.text || "")}</textarea></label>
      <div class="row"><label class="f">Wiedervorlage am (optional)<input type="date" class="in" id="m83w" value="${esc(n.wv_datum || "")}"></label>
        <label class="f">Projekt (optional)<select class="in" id="m83p"><option value="">–</option>${projs.map(p => `<option value="${p.id}" ${p.id == n.project_id ? "selected" : ""}>${esc((p.nr ? p.nr + " " : "") + p.name)}</option>`).join("")}</select></label>
        ${neu ? "" : `<label class="chk" style="flex:none;align-self:flex-end;margin-bottom:8px"><input type="checkbox" id="m83e" ${n.erledigt ? "checked" : ""}> erledigt</label>`}</div></div>`;
    const btns = [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
      const r = await api("/api/m83/notiz", {id:n.id || null, customer_id:cust, art:$("#m83a", mb).value, datum:$("#m83d", mb).value, zeit:$("#m83z", mb).value,
        titel:$("#m83t", mb).value, text:$("#m83x", mb).value, wv_datum:$("#m83w", mb).value, project_id:+$("#m83p", mb).value || null,
        erledigt:neu ? 0 : ($("#m83e", mb).checked ? 1 : 0)});
      if (!r || !r.ok) return false; toast("Gespeichert"); }}];
    if (!neu) btns.unshift({label:"Löschen", cls:"danger", value:"del"});
    const v = await modal(neu ? "Neue Notiz" : "Notiz bearbeiten", html, btns);
    if (v === "del") { await api("/api/m83/notiz_delete", {id:n.id}); toast("Notiz gelöscht"); }
    if (v !== null || neu) { await reloadQuiet(); if (after) after(); else if (view === "m83akte") view83(F.cid); else if (view === "users") vCustomers(); }
  }
  async function reloadQuiet(){ try { const b = await api("/api/bootstrap", undefined, {quiet:true}); if (b && b.m83) { S.m83 = b.m83; renderSide(); } } catch (e) {} }

  async function view83(arg){
    if (arg) F.cid = +arg;
    if (!F.cid && S.customers.length) F.cid = S.customers[0].id;
    const custs = [...S.customers].sort((a, b) => cname(a).localeCompare(cname(b), "de"));
    if (!F.cid) { $("#main").innerHTML = `<div class="page">${pageHead("Kundenakte", "")}<div class="card empty">Noch keine Kunden.</div></div>`; return; }
    const d = await api(`/api/m83/akte?id=${F.cid}&art=${encodeURIComponent(F.art)}&q=${encodeURIComponent(F.q)}`);
    if (!d || !d.ok) return;
    const c = d.kunde, k = d.kpi;
    const yrs = Object.entries(k.umsatz_jahr || {}).sort().reverse();
    const maxY = Math.max(1, ...yrs.map(y => y[1]));
    $("#main").innerHTML = `<div class="page">${pageHead("Kundenakte", "Alles zu einem Kunden auf einer Zeitleiste",
        `<select class="in" id="m83c" style="width:260px">${custs.map(x_ => `<option value="${x_.id}" ${x_.id == F.cid ? "selected" : ""}>${esc(cname(x_))} (${esc(x_.kdnr || "")})</option>`).join("")}</select>`
        + expButtons("m83_kundenakte", {id:F.cid, art:F.art, q:F.q}) + `<button class="btn" id="m83k">${ic("users")} Kunde</button><button class="btn pri" id="m83n">${ic("plus")} Notiz</button>`)}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Umsatz gesamt</div><div class="v">${eur(k.umsatz_gesamt)}</div><div class="s">${thisYear}: ${eur(k.umsatz_akt)}</div></div>
        <div class="card kpi"><div class="l">Offene Posten</div><div class="v" style="color:${k.offen_n ? "var(--warn)" : "inherit"}">${eur(k.offen_summe)}</div><div class="s">${k.offen_n} Rechnung(en)</div></div>
        <div class="card kpi"><div class="l">Ø Zahlungsdauer</div><div class="v">${k.zahlungsdauer !== null ? nde(k.zahlungsdauer, 1) + " Tage" : "–"}</div><div class="s">aus ${k.zahlungen_n} bezahlten Rechnungen</div></div>
        <div class="card kpi"><div class="l">Letzte Aktivität</div><div class="v" style="font-size:18px">${dde(k.letzte) || "–"}</div><div class="s">Kunde seit ${dde(k.erste) || "–"} · Angebote ${k.angebote_ok}/${k.angebote_n}</div></div></div>
      ${(d.wiedervorlagen || []).length ? `<div class="card" style="margin-bottom:14px"><div class="hd"><h3>${ic("clock")} Offene Wiedervorlagen</h3></div><table class="t"><tbody>
        ${d.wiedervorlagen.map(w => `<tr class="click" data-m83wv="${w.id}"><td class="num" style="width:110px">${w.wv_datum <= todayIso() ? `<span class="badge warn"><span class="dot"></span>${dde(w.wv_datum)}</span>` : dde(w.wv_datum)}</td>
          <td><b>${esc(w.titel || NOTIZ[w.art] || "Notiz")}</b><div class="small muted">${esc((w.text || "").slice(0, 140))}</div></td>
          <td class="r" style="width:120px" onclick="event.stopPropagation()"><button class="btn sm" data-m83ok="${w.id}">✓ Erledigt</button></td></tr>`).join("")}</tbody></table></div>` : ""}
      <div class="grid" style="grid-template-columns:minmax(0,3fr) minmax(240px,1fr);align-items:start">
        <div class="card" style="overflow:hidden"><div class="hd" style="flex-wrap:wrap;gap:8px"><h3>Zeitstrahl</h3>
          <div class="chips" style="flex:none">${GRP.map(([a, l]) => `<span class="chip ${F.art === a ? "on" : ""}" data-m83g="${a}">${l}</span>`).join("")}</div>
          <div class="search" style="flex:none;width:220px;margin-left:auto"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="m83q" placeholder="Im Zeitstrahl suchen …" value="${esc(F.q)}"></div></div>
          <table class="t"><thead><tr><th style="width:96px">Datum</th><th style="width:150px">Art</th><th>Eintrag</th><th class="r" style="width:110px">Betrag</th><th style="width:100px">Status</th></tr></thead>
          <tbody>${d.events.map(e => evRow(e)).join("") || `<tr><td colspan="5" class="empty">Keine Einträge${F.q || F.art ? " für diesen Filter" : ""}.</td></tr>`}</tbody></table></div>
        <div>
          <div class="card" style="margin-bottom:14px"><div class="hd"><div class="av" style="width:38px;height:38px">${initials(cname(c))}</div><div><h3>${esc(cname(c))}</h3><div class="small muted">Kd-Nr. ${esc(c.kdnr || "")}</div></div></div>
            <div class="bd small"><div style="white-space:pre-line;margin-bottom:6px">${esc(addrLines(c).join("\n"))}</div>
              ${c.tel ? `<div>☎ ${esc(c.tel)}</div>` : ""}${c.mobil ? `<div>📱 ${esc(c.mobil)}</div>` : ""}${c.mail ? `<div>✉ ${esc(c.mail)}</div>` : ""}
              ${c.notiz ? `<hr class="s"><div class="muted" style="white-space:pre-line">${esc(c.notiz)}</div>` : ""}</div></div>
          <div class="card" style="margin-bottom:14px"><div class="hd"><h3>Umsatz pro Jahr</h3></div><div class="bd">${yrs.map(([y, v]) => `<div class="hbar"><span class="lb">${y}</span><div class="tr"><div class="fl" style="width:${100 * v / maxY}%"></div></div><span class="r num">${eur0(v)}</span></div>`).join("") || `<div class="muted small">–</div>`}</div></div>
          <div class="card"><div class="hd"><h3>Einträge je Art</h3></div><div class="bd small">${Object.entries(d.counts || {}).sort((a, b) => b[1] - a[1]).map(([a, n]) => `<div class="row" style="justify-content:space-between;margin:2px 0"><span><span class="dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${COL[a] || "#888"};margin-right:6px"></span>${esc(d.arten[a] || a)}</span><b>${n}</b></div>`).join("") || "–"}</div></div>
        </div></div></div>`;
    bindCommon();
    bindRows($("#main"), d.events);
    $("#m83c").onchange = e => { F.cid = +e.target.value; view83(); };
    $("#m83k").onclick = () => go("users", F.cid);
    $("#m83n").onclick = () => editNote(null, F.cid);
    $$("[data-m83g]").forEach(b => b.onclick = () => { F.art = b.dataset.m83g; view83(); });
    $$("[data-m83wv]").forEach(r => r.onclick = () => editNote({id:+r.dataset.m83wv}, F.cid));
    $$("[data-m83ok]").forEach(b => b.onclick = async () => { await api("/api/m83/notiz_done", {id:+b.dataset.m83ok}); toast("Wiedervorlage erledigt"); await reloadQuiet(); view83(); });
    $("#m83q").oninput = e => { F.q = e.target.value; clearTimeout(window._m83T);
      window._m83T = setTimeout(() => { if (!$("#m83q")) return; const p = e.target.selectionStart;
        view83().then(() => { const n = $("#m83q"); if (n) { n.focus(); try { n.setSelectionRange(p, p); } catch (e2) {} } }); }, 250); };
  }

  // ---------- customer detail: compact timeline card ----------
  EXT.after.push(async n => {
    if (n !== "vCustomers" || typeof custSel === "undefined" || !custSel) return;
    const ed = $("#cedit"); if (!ed || $("#m83card")) return;
    const head = ed.closest(".card"); const col = head && head.parentElement; if (!col) return;
    const act = ed.parentElement;
    if (act && !$("#m83ak", act)) { const b = document.createElement("button"); b.className = "btn"; b.id = "m83ak"; b.type = "button"; b.innerHTML = ic("m83") + " Kundenakte";
      b.onclick = () => go("m83akte", custSel); act.insertBefore(b, ed); }
    const cid = custSel;
    const card = document.createElement("div"); card.className = "card"; card.id = "m83card"; card.style.cssText = "margin-top:16px;overflow:hidden";
    card.innerHTML = `<div class="hd"><h3>${ic("m83")} Zeitstrahl</h3></div><div class="bd small muted">Lädt …</div>`;
    col.appendChild(card);
    const d = await api(`/api/m83/akte?id=${cid}`, undefined, {quiet:true});
    if (!d || !d.ok || custSel !== cid || !card.isConnected) return;
    const k = d.kpi;
    card.innerHTML = `<div class="hd"><h3>${ic("m83")} Zeitstrahl</h3><div class="act"><span class="small muted" style="margin-right:8px">Ø Zahlungsdauer ${k.zahlungsdauer !== null ? nde(k.zahlungsdauer, 1) + " Tage" : "–"} · letzte Aktivität ${dde(k.letzte) || "–"}${k.wv_offen ? ` · <b style="color:var(--warn)">${k.wv_offen} Wiedervorlage(n)</b>` : ""}</span>
        <button class="btn sm" id="m83cn" type="button">${ic("plus")} Notiz</button><button class="btn sm ghost" id="m83ca" type="button">Alle ${d.events.length} Einträge</button></div></div>
      <table class="t"><tbody>${d.events.slice(0, 10).map(e => evRow(e, true)).join("") || `<tr><td class="empty">Noch keine Einträge.</td></tr>`}</tbody></table>`;
    bindRows(card, d.events);
    $("#m83cn", card).onclick = () => editNote(null, cid, () => vCustomers());
    $("#m83ca", card).onclick = () => go("m83akte", cid);
  });

  // ---------- dashboard: due follow-ups ----------
  EXT.dash.push(el => {
    const m = S.m83; if (!m || !m.wv_faellig) return;
    const d = document.createElement("div"); d.className = "alert warn"; d.style.marginBottom = "10px"; d.id = "m83dash";
    d.innerHTML = `${ic("clock")}<b>${m.wv_faellig} Wiedervorlage${m.wv_faellig > 1 ? "n" : ""} fällig</b><span class="small" id="m83dl">Kundenakte</span><span class="sp" style="flex:1"></span><span class="small"><u>Ansehen →</u></span>`;
    el.appendChild(d);
    api("/api/m83/wv", undefined, {quiet:true}).then(r => { const l = $("#m83dl", d); if (l && r && r.rows) l.textContent = r.rows.slice(0, 3).map(w => (w.kunde || "") + ": " + (w.titel || "Notiz")).join(" · ") + (r.rows.length > 3 ? " …" : "");
      d.onclick = () => go("m83akte", r && r.rows && r.rows[0] ? r.rows[0].customer_id : undefined); });
  });

  window.m83EditNote = editNote;
})();
