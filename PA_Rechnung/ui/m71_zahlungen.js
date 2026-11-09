// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m71_zahlungen: Zahlungseingaenge, Teilzahlungen, Skonto
// Seite "Zahlungseingaenge" (Finanzen), Skonto-Felder + Zahlungsbox im Rechnungs-Editor, Rest-Badge in Listen.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m71 = '<path d="M3 7h18v10H3z"/><circle cx="12" cy="12" r="2.5"/><path d="M7 4l-3 3 3 3M17 20l3-3-3-3"/>';
  const F = {tab: "pruefen"};

  EXT.nav.push({key: "m71zahl", label: "Zahlungseingänge", icon: "m71", section: "Finanzen",
    cnt: () => (S.m71 && S.m71.pending) ? String(S.m71.pending) : ""});
  EXT.views.m71zahl = view;

  // ---- rest badge in all invoice lists
  const _sb = statusBadge;
  statusBadge = function(i){
    let h = _sb(i);
    try {
      const r = S.m71 && S.m71.rest && S.m71.rest[i.id];
      if (r !== undefined && i.status === "offen") h += ` <span class="badge warn" title="Teilzahlung erhalten: ${esc(eur(S.m71.gezahlt[i.id] || 0))}">Rest ${eur(r)}</span>`;
    } catch (e) {}
    return h;
  };

  async function bookDialog(inv, after){
    const st = (await api("/api/m71/state?id=" + inv.id, undefined, {quiet: true})) || {};
    const rest = st && st.rest !== undefined ? st.rest : inv.summe;
    const sk = st && st.skonto_regel && st.skonto_regel.bis >= todayIso() && !st.gezahlt ? st.skonto_regel : null;
    await modal(`Zahlung erfassen – ${inv.nr}`, `<div class="fr">
      <div class="small muted" style="margin-bottom:8px">Rechnungsbetrag ${eur(st.summe || inv.summe)} · bisher gezahlt ${eur(st.gezahlt || 0)} · <b>offen ${eur(rest)}</b>
        ${sk ? `<br>Skonto möglich: ${nde(sk.pct)} % bis ${dde(sk.bis)} → Zahlbetrag ${eur(sk.betrag)}` : ""}</div>
      <div class="row"><label class="f">Datum<input type="date" class="in" id="m71d" value="${todayIso()}"></label>
        <label class="f">Betrag €<input class="in num" id="m71b" value="${nde(sk ? sk.betrag : rest)}"></label></div>
      <label class="f">Notiz<input class="in" id="m71n" placeholder="z. B. Barzahlung, PayPal, Überweisung"></label>
      <div class="small muted" style="margin-top:6px">Weniger als offen = Teilzahlung (Rechnung bleibt offen). Innerhalb der Skontofrist mit Skontobetrag = bezahlt, der Abzug wird als Skonto gebucht.</div></div>`,
      [{label: "Abbrechen"},
       {label: "Rest ausbuchen", cls: "ghost", onClick: async mb => {
         const r = await api("/api/m71/book", {invoice_id: inv.id, datum: $("#m71d", mb).value, betrag: rest, art: "ausbuchung", notiz: $("#m71n", mb).value || "Rest ausgebucht"});
         if (!r || !r.ok) return false; toast("Rest ausgebucht – Rechnung erledigt"); if (after) after(); }},
       {label: "Zahlung buchen", cls: "pri", onClick: async mb => {
         const r = await api("/api/m71/book", {invoice_id: inv.id, datum: $("#m71d", mb).value, betrag: pnum($("#m71b", mb).value), notiz: $("#m71n", mb).value});
         if (!r || !r.ok) return false;
         toast(r.status === "bezahlt" ? (r.art === "skonto" ? `Bezahlt mit Skonto (${eur(r.skonto)})` : "Rechnung bezahlt") : `Teilzahlung gebucht – offen ${eur(r.rest)}`);
         if (after) after(); }}]);
  }
  window.m71Book = bookDialog;

  async function view(){
    const d = await api("/api/m71/overview");
    if (!d || !d.offen) return;
    const openSel = (sel) => `<option value="">– Rechnung wählen –</option>` + d.offen.map(o => `<option value="${o.id}" ${o.id == sel ? "selected" : ""}>${esc(o.nr)} · ${esc(o.name)} · offen ${eur(o.rest)}</option>`).join("");
    const tabs = [["pruefen", "Zu prüfen", d.pending.length], ["offen", "Offene Posten", d.offen.length], ["zahlungen", "Gebuchte Zahlungen", d.zahlungen.length], ["einst", "Einstellungen", ""]];
    let body = "";
    if (F.tab === "pruefen") {
      body = `<div class="card" style="overflow:hidden"><div class="hd"><h3>Eingegangene Zahlungen aus dem Bankabruf</h3><div class="act">
          <button class="btn sm" id="m71auto">${ic("check")} Sichere Zuordnungen buchen</button></div></div>
        <table class="t"><thead><tr><th>Datum</th><th>Auftraggeber</th><th>Verwendungszweck</th><th class="r">Betrag</th><th style="min-width:300px">Rechnung</th><th style="width:210px"></th></tr></thead>
        <tbody>${d.pending.map(t => `<tr data-m71h="${esc(t.hash)}"><td class="num">${dde(t.datum)}</td><td>${esc(t.name)}</td><td class="small">${esc(t.zweck)}${t.hinweis ? `<div class="small muted">${esc(t.hinweis)}</div>` : ""}</td>
            <td class="r num"><b>${eur(t.betrag)}</b></td>
            <td><select class="in" data-m71s="${esc(t.hash)}">${openSel(t.vorschlag ? t.vorschlag.id : "")}</select>${t.vorschlag ? `<div class="small muted">${t.sicher >= 3 ? "sicher" : "Vorschlag"}${t.m71 ? " · " + ({voll: "voll", skonto: "mit Skonto", teil: "Teilzahlung"}[t.m71.art] || "") : ""}</div>` : ""}</td>
            <td class="r" style="white-space:nowrap"><button class="btn sm pri" data-m71a="${esc(t.hash)}">${ic("check")} Übernehmen</button><button class="btn sm ghost" data-m71e="${esc(t.hash)}" title="als sonstige Einnahme buchen">Einnahme</button><button class="btn sm ghost" data-m71i="${esc(t.hash)}" title="ignorieren (z. B. Privat)">Ignorieren</button></td></tr>`).join("")
          || `<tr><td colspan="6" class="empty">Keine offenen Zahlungseingänge. Neue Buchungen kommen über den Bankabruf (FinTS/PSD2) oder den Kontoauszug-Import im Bank-Abgleich.</td></tr>`}</tbody></table></div>`;
    } else if (F.tab === "offen") {
      body = `<div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Nr.</th><th>Kunde</th><th>Datum</th><th>Fällig</th><th class="r">Betrag</th><th class="r">Gezahlt</th><th class="r">Offen</th><th>Skonto</th><th style="width:150px"></th></tr></thead>
        <tbody>${d.offen.map(o => `<tr class="click" data-m71o="${o.id}"><td><b>${esc(o.nr)}</b></td><td>${esc(o.name)}</td><td class="num">${dde(o.datum)}</td>
          <td class="num">${o.tage > 0 ? `<span class="badge bad"><span class="dot"></span>${dde(o.faellig)} · ${o.tage} T.</span>` : dde(o.faellig)}</td>
          <td class="r num">${eur(o.summe)}</td><td class="r num">${o.gezahlt ? eur(o.gezahlt) : "–"}</td><td class="r num"><b>${eur(o.rest)}</b></td>
          <td class="small">${o.skonto ? `${nde(o.skonto.pct)} % bis ${dde(o.skonto.bis)}` : ""}</td>
          <td class="r" onclick="event.stopPropagation()"><button class="btn sm" data-m71p="${o.id}">${ic("plus")} Zahlung</button></td></tr>`).join("")
          || `<tr><td colspan="9" class="empty">Keine offenen Rechnungen.</td></tr>`}</tbody>
        <tfoot><tr><td colspan="6">Summe offen</td><td class="r num">${eur(d.summe_offen)}</td><td colspan="2"></td></tr></tfoot></table></div>`;
    } else if (F.tab === "zahlungen") {
      body = `<div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Datum</th><th>Rechnung</th><th>Kunde</th><th>Art</th><th>Quelle</th><th class="r">Betrag</th><th>Notiz</th><th></th></tr></thead>
        <tbody>${d.zahlungen.map(z => `<tr data-m71z="${z.id}"><td class="num">${dde(z.datum)}</td><td>${z.nr ? `<a href="#" data-inv="${z.invoice_id}"><b>${esc(z.nr)}</b></a>` : "<i>gelöscht</i>"}</td><td>${esc(z.name)}</td>
          <td><span class="badge ${z.art === "teil" ? "warn" : z.art === "skonto" || z.art === "ausbuchung" ? "" : "ok"}">${esc(z.art_de)}</span></td>
          <td class="small muted">${esc({bank: "Bank", manuell: "manuell", status: "als bezahlt markiert", auto: "automatisch"}[z.quelle] || z.quelle || "")}</td>
          <td class="r num">${eur(z.betrag)}</td><td class="small">${esc(z.notiz || "")}</td>
          <td class="r"><button class="btn sm ghost danger" data-m71x="${z.id}" title="Zahlung löschen">${ic("trash")}</button></td></tr>`).join("")
          || `<tr><td colspan="8" class="empty">Noch keine Zahlungen gebucht.</td></tr>`}</tbody></table></div>`;
    } else {
      const c = d.cfg;
      body = `<div class="card"><div class="hd"><h3>Skonto & automatische Zuordnung</h3></div><div class="bd fr">
        <div class="row"><label class="f">Standard-Skonto %<input class="in num" id="m71cp" value="${nde(c.skonto_pct)}"></label>
          <label class="f">binnen Tagen<input class="in num" id="m71ct" value="${c.skonto_tage}"></label>
          <label class="f">Toleranz € (Kleindifferenz ausbuchen)<input class="in num" id="m71ctol" value="${nde(c.toleranz)}"></label></div>
        <div class="small muted" style="margin-bottom:8px">0 % = kein Skonto. In jeder Rechnung lässt sich Skonto im Editor abweichend einstellen. Platzhalter für Kopf-/Fußtext: <b>[Skonto]</b> (ganzer Satz), [Skontobetrag], [Skontodatum], [Skontosatz].</div>
        <label class="chk"><input type="checkbox" id="m71ca" ${c.auto ? "checked" : ""}> Sicher erkannte Zahlungen aus dem Bankabruf automatisch buchen (Rechnungsnummer im Verwendungszweck, oder eindeutiger Betrag + Name)</label>
        <label class="chk"><input type="checkbox" id="m71cat" ${c.auto_teil ? "checked" : ""}> Auch Teilzahlungen automatisch buchen, wenn die Rechnungsnummer im Verwendungszweck steht</label>
        <div style="margin-top:10px"><button class="btn pri" id="m71cs">${ic("save")} Speichern</button></div></div></div>`;
    }
    $("#main").innerHTML = `<div class="page">${pageHead("Zahlungseingänge", "Bankbuchungen den Rechnungen zuordnen – mit Teilzahlungen und Skonto",
        expButtons("m71_zahlungen", {}) + `<button class="btn" data-go="bank">${ic("sync")} Bank-Abgleich</button>`)}
      <div class="grid g4" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Zu prüfen</div><div class="v" style="color:${d.pending.length ? "var(--warn)" : "inherit"}">${d.pending.length}</div><div class="s">Zahlungseingänge</div></div>
        <div class="card kpi"><div class="l">Offene Posten</div><div class="v">${eur(d.summe_offen)}</div><div class="s">${d.offen.length} Rechnungen</div></div>
        <div class="card kpi"><div class="l">Teilzahlungen</div><div class="v">${d.teil_anzahl}</div><div class="s">Rechnungen mit Restbetrag</div></div>
        <div class="card kpi"><div class="l">Skonto Standard</div><div class="v" style="font-size:20px">${d.cfg.skonto_pct ? nde(d.cfg.skonto_pct) + " % / " + d.cfg.skonto_tage + " T." : "aus"}</div><div class="s">${d.cfg.auto ? "automatisch buchen an" : "nur Vorschläge"}</div></div></div>
      <div class="tabs" style="margin-bottom:12px">${tabs.map(([k, l, n]) => `<div class="tab ${F.tab === k ? "on" : ""}" data-m71t="${k}">${l}${n !== "" ? `<span class="cnt">${n}</span>` : ""}</div>`).join("")}</div>
      ${body}</div>`;
    bindCommon();
    $$("[data-m71t]").forEach(b => b.onclick = () => { F.tab = b.dataset.m71t; view(); });
    const refresh = async () => { await reload(); view(); };
    $$("[data-m71a]").forEach(b => b.onclick = async () => {
      const sel = $(`[data-m71s="${CSS.escape(b.dataset.m71a)}"]`); const iid = sel ? +sel.value : 0;
      if (!iid) { toast("Bitte eine Rechnung wählen", true); return; }
      const r = await api("/api/m71/apply", {hash: b.dataset.m71a, invoice_id: iid});
      if (r && r.ok) { toast(r.teilzahlungen ? "Teilzahlung gebucht" : "Zahlung gebucht"); refresh(); } });
    $$("[data-m71i]").forEach(b => b.onclick = async () => { await api("/api/m71/ignore", {hash: b.dataset.m71i}); refresh(); });
    $$("[data-m71e]").forEach(b => b.onclick = async () => { await api("/api/m71/ignore", {hash: b.dataset.m71e, aktion: "einnahme"}); toast("Als sonstige Einnahme gebucht"); refresh(); });
    if ($("#m71auto")) $("#m71auto").onclick = async () => { const r = await api("/api/m71/auto", {}); if (r && r.ok) { toast(r.gebucht.length ? `${r.gebucht.length} Zahlung(en) gebucht` : "Keine eindeutigen Zuordnungen gefunden"); refresh(); } };
    $$("[data-m71p]").forEach(b => b.onclick = () => bookDialog(d.offen.find(o => o.id == b.dataset.m71p), refresh));
    $$("[data-m71o]").forEach(r => r.onclick = () => openInvoice(+r.dataset.m71o));
    $$("[data-m71x]").forEach(b => b.onclick = async () => { const r = await api("/api/m71/delete", {id: +b.dataset.m71x}); if (r && r.ok) { toast("Zahlung gelöscht"); refresh(); } });
    if ($("#m71cs")) $("#m71cs").onclick = async () => {
      const r = await api("/api/m71/cfg", {m71_skonto_pct: pnum($("#m71cp").value), m71_skonto_tage: pnum($("#m71ct").value), m71_toleranz: pnum($("#m71ctol").value),
        m71_auto: $("#m71ca").checked, m71_auto_teil: $("#m71cat").checked});
      if (r && r.ok) { toast("Gespeichert"); refresh(); } };
    if (F.tab === "zahlungen") selectify({kind: "m71z", rows: "tr[data-m71z]", id: "data-m71z", rerender: view, actions: [
      {label: "Löschen", cls: "danger", run: async ids => { for (const id of ids) await api("/api/m71/delete", {id: +id}); await reload(); view(); }}]});
    if (F.tab === "pruefen") selectify({kind: "m71p", rows: "tr[data-m71h]", id: "data-m71h", rerender: view, actions: [
      {label: "Ignorieren", run: async ids => { await api("/api/m71/ignore", {hashes: ids}); await reload(); view(); }}]});
  }

  // ---- editor: skonto fields + payment box
  EXT.after.push(async n => {
    if (n !== "vEditor" || typeof cur === "undefined" || !cur || cur.typ !== "rechnung") return;
    const fr = $("#frist");
    if (fr && !$("#m71sk")) {
      const row = fr.closest(".row");
      const el = document.createElement("div"); el.className = "row"; el.id = "m71sk";
      const def = (S.m71 && S.m71.cfg) || {};
      el.innerHTML = `<label class="f">Skonto %<input class="in num" id="m71skp" value="${cur.skonto_pct === null || cur.skonto_pct === undefined || cur.skonto_pct === "" ? "" : nde(cur.skonto_pct)}" placeholder="${def.skonto_pct ? nde(def.skonto_pct) + " (Standard)" : "kein Skonto"}" ${cur.locked ? "disabled" : ""}></label>
        <label class="f">Skonto binnen Tagen<input class="in num" id="m71skt" value="${cur.skonto_tage === null || cur.skonto_tage === undefined ? "" : cur.skonto_tage}" placeholder="${def.skonto_tage ? def.skonto_tage + " (Standard)" : ""}" ${cur.locked ? "disabled" : ""}></label>`;
      if (row) row.insertAdjacentElement("afterend", el);
      const up = () => { const p = $("#m71skp").value.trim(), t = $("#m71skt").value.trim();
        cur.skonto_pct = p === "" ? null : pnum(p); cur.skonto_tage = t === "" ? null : Math.round(pnum(t)); if (typeof schedulePreview === "function") schedulePreview(); };
      $("#m71skp").oninput = up; $("#m71skt").oninput = up;
    }
    if (!cur.id || !["offen", "bezahlt"].includes(cur.status) || $("#m71box")) return;
    const st = await api("/api/m71/state?id=" + cur.id, undefined, {quiet: true});
    if (!st || !st.ok || (!st.zahlungen.length && cur.status === "bezahlt")) return;
    const top = $("#toptext"); const sec = top ? top.closest(".sec") : null; if (!sec || $("#m71box")) return;
    const box = document.createElement("div"); box.className = "sec"; box.id = "m71box";
    box.innerHTML = `<div class="h"><b>Zahlungen</b><span class="sp"></span>${cur.status === "offen" ? `<button class="btn sm" type="button" id="m71eb">${ic("plus")} Zahlung erfassen</button>` : ""}</div>
      <div class="card"><div class="bd small">${st.zahlungen.map(z => `<div class="row" style="align-items:center;padding:2px 0"><span style="flex:none;width:80px">${dde(z.datum)}</span><span>${esc(z.art_de)}${z.notiz ? ` · <span class="muted">${esc(z.notiz)}</span>` : ""}</span><span class="sp" style="flex:1"></span><b class="num">${eur(z.betrag)}</b></div>`).join("") || `<div class="muted">Noch keine Zahlung eingegangen.</div>`}
        <div class="row" style="border-top:1px solid var(--line);margin-top:4px;padding-top:4px"><span>Offen</span><span class="sp" style="flex:1"></span><b class="num">${eur(st.rest)}</b></div>
        ${st.skonto_regel ? `<div class="muted">Skonto: ${nde(st.skonto_regel.pct)} % bis ${dde(st.skonto_regel.bis)} (Zahlbetrag ${eur(st.skonto_regel.betrag)})</div>` : ""}</div></div>`;
    sec.parentNode.insertBefore(box, sec);
    if ($("#m71eb")) $("#m71eb").onclick = () => bookDialog({id: cur.id, nr: cur.nr, summe: cur.summe}, async () => { await reload(); openInvoice(cur.id, true); });
  });
})();
