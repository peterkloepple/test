// Pfeiffer-Audio Rechnung v2.0.0 - UI-Modul m34_fixkosten: wiederkehrende Ausgaben
// Seite "Fixkosten" (Finanzen), Dashboard-Hinweis, Vorschlaege aus Belegen.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const IVL = {monatlich:"monatlich", quartalsweise:"quartalsweise", halbjaehrlich:"halbjährlich", jaehrlich:"jährlich"};

  EXT.nav.push({key:"fixkosten", label:"Fixkosten", icon:"clock", section:"Finanzen", cnt:() => (S.fixkosten && S.fixkosten.offen) ? String(S.fixkosten.offen) : ""});

  EXT.dash.push(el => {
    const f = S.fixkosten; if (!f || !f.offen) return;
    const d = document.createElement("div"); d.className = "alerts";
    d.innerHTML = `<div class="alert warn" id="fixdash">${ic("clock")}<b>${f.offen} Fixkosten zu bestätigen</b> · ${eur(f.summe)} – vorgemerkt, noch nicht gebucht</div>`;
    el.appendChild(d);
    $("#fixdash", d).onclick = () => go("fixkosten");
  });

  async function editFix(f){
    f = f || {};
    const iv = f.intervall || "monatlich";
    const r = await modal(f.id ? "Fixkosten bearbeiten" : "Neue Fixkosten", `<div class="fr">
      <div class="row"><label class="f">Name<input class="in" id="fxn" value="${esc(f.name||"")}" placeholder="z. B. Adobe Creative Cloud"></label>
        <label class="f">Lieferant (wie auf dem Kontoauszug)<input class="in" id="fxp" value="${esc(f.partner||"")}" placeholder="z. B. Adobe"></label></div>
      <div class="row"><label class="f" style="flex:.6">Betrag €<input class="in num" id="fxb" value="${f.betrag!=null?nde(f.betrag):""}"></label>
        <label class="f" style="flex:.7">Intervall<select class="in" id="fxi">${Object.entries(IVL).map(([k,l])=>`<option value="${k}" ${k===iv?"selected":""}>${l}</option>`).join("")}</select></label>
        <label class="f">EÜR-Kategorie<select class="in" id="fxk">${S.kategorien.map(k=>`<option ${k===(f.kategorie||"Sonstige Betriebsausgaben")?"selected":""}>${esc(k)}</option>`).join("")}</select></label></div>
      <div class="row"><label class="f">Start<input type="date" class="in" id="fxs" value="${f.start||todayIso()}"></label>
        <label class="f">Nächste Fälligkeit<input type="date" class="in" id="fxx" value="${f.naechste||f.start||todayIso()}"></label>
        <label class="f">Ende (optional)<input type="date" class="in" id="fxe" value="${f.ende||""}"></label></div>
      <label class="f">Notiz<input class="in" id="fxo" value="${esc(f.notiz||"")}"></label>
      <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="fxa" ${f.aktiv===0?"":"checked"}> aktiv</label>
      <div class="small muted">Ist ein Posten fällig, wird er nur <b>vorgemerkt</b> (Dashboard-Hinweis). Erst mit „Bestätigen“ – oder automatisch, wenn die passende Bankbuchung kommt – entsteht ein Ausgabe-Beleg. Liegt die Fälligkeit in der Vergangenheit, werden höchstens die letzten 3 Monate nachgeholt.</div></div>`,
      [...(f.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
        const d = {id:f.id||null, name:$("#fxn",mb).value.trim(), partner:$("#fxp",mb).value.trim(), betrag:pnum($("#fxb",mb).value), intervall:$("#fxi",mb).value,
          kategorie:$("#fxk",mb).value, start:$("#fxs",mb).value, naechste:$("#fxx",mb).value, ende:$("#fxe",mb).value, notiz:$("#fxo",mb).value, aktiv:$("#fxa",mb).checked};
        const res = await api("/api/fixkosten/save", d); if (!res || !res.ok) return false; }}], true);
    if (r === "del") { if (!await confirmBox("Fixkosten-Posten löschen? Bereits gebuchte Belege bleiben erhalten, offene Vormerkungen werden entfernt.")) return; await api("/api/fixkosten/delete", {id:f.id}); }
    if (r) { await reload(); if (view === "fixkosten") vFix(); }
  }

  async function suggestDlg(){
    const sg = await api("/api/fixkosten/vorschlaege");
    if (!Array.isArray(sg) || !sg.length) { await modal("Vorschläge aus Belegen", `<div class="small muted">Keine regelmäßigen Ausgaben erkannt. Erkannt wird: gleicher Lieferant, ähnlicher Betrag (±5 %), mindestens 3× in regelmäßigem Abstand (monatlich, quartalsweise, halbjährlich, jährlich).</div>`); return; }
    let pick = null;
    await modal("Vorschläge aus Belegen", `<div class="small muted" style="margin-bottom:8px">Aus deinen Ausgabe-Belegen erkannt:</div>
      <table class="t"><tbody>${sg.map((s,i)=>`<tr><td><b>Erkannt: ${esc(s.partner)} ${eur(s.betrag)} ${esc(s.intervall_label)}</b><div class="small muted">${s.anzahl}× seit ${dde(s.start)} · zuletzt ${dde(s.letzte)} · ${esc(s.kategorie)}</div></td>
        <td class="r"><button class="btn sm pri" data-fxsg="${i}">Übernehmen?</button></td></tr>`).join("")}</tbody></table>`,
      [{label:"Schließen"}], true, mb => $$("[data-fxsg]", mb).forEach(b => b.onclick = () => { pick = sg[+b.dataset.fxsg]; $(".mf .btn", mb).click(); }));
    if (pick) editFix({name:pick.partner, partner:pick.partner, betrag:pick.betrag, intervall:pick.intervall, kategorie:pick.kategorie, start:pick.start, naechste:pick.naechste});
  }

  async function vFix(){
    const d = await api("/api/fixkosten");
    const L = d.liste || [], V = d.vormerk || [], E = d.erledigt || [];
    const akt = L.filter(f=>f.aktiv), mon = akt.reduce((a,f)=>a+f.monatlich,0);
    $("#main").innerHTML = `<div class="page">
      ${pageHead("Fixkosten", "Wiederkehrende Ausgaben – fällige Posten werden vorgemerkt und erst nach Bestätigung (oder passender Bankbuchung) als Beleg gebucht",
        expButtons("fixkosten") + `<button class="btn" id="fxsug">${ic("search")} Vorschläge aus Belegen</button><button class="btn pri" id="fxnew">${ic("plus")} Fixkosten</button>`)}
      <div class="grid g4" style="margin-bottom:16px">
        <div class="card kpi acc"><div class="l">Je Monat</div><div class="v">${eur(mon)}</div><div class="s">${akt.length} aktive Posten</div></div>
        <div class="card kpi"><div class="l">Im Jahr</div><div class="v">${eur(mon*12)}</div><div class="s">hochgerechnet</div></div>
        <div class="card kpi"><div class="l">Zu bestätigen</div><div class="v" style="color:${V.length?"var(--warn)":"inherit"}">${V.length}</div><div class="s">${eur(V.reduce((a,v)=>a+v.betrag,0))}</div></div>
        <div class="card kpi"><div class="l">Nächste Fälligkeit</div><div class="v" style="font-size:20px">${akt.length?dde(akt.map(f=>f.naechste).filter(Boolean).sort()[0]):"–"}</div><div class="s">&nbsp;</div></div></div>
      ${V.length?`<div class="card" style="overflow:hidden;margin-bottom:16px"><div class="hd"><h3>Vorgemerkt – bitte bestätigen</h3><div class="act small muted">noch nicht in der EÜR</div></div>
        <table class="t"><thead><tr><th>Fällig</th><th>Name / Lieferant</th><th>Kategorie</th><th style="width:130px">Buchungsdatum</th><th class="r" style="width:110px">Betrag €</th><th style="width:220px"></th></tr></thead><tbody>
        ${V.map(v=>`<tr data-vm="${v.id}"><td class="num">${dde(v.faellig)}</td><td><b>${esc(v.name)}</b><div class="small muted">${esc(v.partner||"")} · ${esc(IVL[v.intervall]||"")}</div></td><td class="small">${esc(v.kategorie||"")}</td>
          <td><input type="date" class="in" data-vd value="${v.faellig}"></td><td><input class="in num" data-vb value="${nde(v.betrag)}" style="text-align:right"></td>
          <td class="r"><button class="btn sm pri" data-vok="${v.id}">${ic("check")} Bestätigen</button> <button class="btn sm ghost" data-vskip="${v.id}">Überspringen</button></td></tr>`).join("")}
        </tbody></table></div>`:""}
      <div class="card" style="overflow:hidden"><table class="t"><thead><tr><th>Name / Lieferant</th><th>EÜR-Kategorie</th><th>Intervall</th><th class="r">Betrag</th><th class="r">je Monat</th><th>Nächste Fälligkeit</th><th>Laufzeit</th><th>Notiz</th></tr></thead><tbody>
        ${L.map(f=>`<tr class="click" data-fx="${f.id}" style="${f.aktiv?"":"opacity:.55"}"><td><b>${esc(f.name)}</b>${f.aktiv?"":` <span class="badge">inaktiv</span>`}${f.offen?` <span class="badge warn">${f.offen} offen</span>`:""}<div class="small muted">${esc(f.partner||"")}</div></td>
          <td class="small">${esc(f.kategorie||"")}</td><td>${esc(IVL[f.intervall]||f.intervall)}</td><td class="r num">${eur(f.betrag)}</td><td class="r num">${eur(f.monatlich)}</td>
          <td class="num">${f.aktiv?dde(f.naechste):"–"}</td><td class="small">${dde(f.start)}${f.ende?" – "+dde(f.ende):""}</td><td class="small muted">${esc(f.notiz||"")}</td></tr>`).join("")
          || `<tr><td colspan="8" class="empty">Noch keine Fixkosten. Lege Abos, Miete, Versicherungen usw. an – oder lass dir über „Vorschläge aus Belegen“ regelmäßige Ausgaben vorschlagen.</td></tr>`}
      </tbody></table></div>
      ${E.length?`<div class="card" style="overflow:hidden;margin-top:16px"><div class="hd"><h3>Zuletzt erledigt</h3></div><div class="scroll" style="max-height:260px"><table class="t"><tbody>
        ${E.map(v=>`<tr><td class="num">${dde(v.faellig)}</td><td>${esc(v.name)}</td><td><span class="badge ${v.status==="bestaetigt"?"ok":""}">${v.status==="bestaetigt"?(v.bank_tx_id?"gebucht · mit Bankbuchung verknüpft":"gebucht"):"übersprungen"}</span></td><td class="r num">${eur(v.betrag)}</td></tr>`).join("")}
      </tbody></table></div></div>`:""}
    </div>`;
    $("#fxnew").onclick = () => editFix(null);
    $("#fxsug").onclick = suggestDlg;
    $$("[data-fx]").forEach(r => r.onclick = () => editFix(L.find(f=>f.id==r.dataset.fx)));
    $$("[data-vok]").forEach(b => b.onclick = async () => { const tr = b.closest("tr");
      const r = await api("/api/fixkosten/confirm", {id:+b.dataset.vok, datum:$("[data-vd]",tr).value, betrag:pnum($("[data-vb]",tr).value)});
      if (r && r.ok) { toast("Als Ausgabe-Beleg gebucht"); await reload(); vFix(); } });
    $$("[data-vskip]").forEach(b => b.onclick = async () => { if (!await confirmBox("Diese Fälligkeit überspringen? Es wird kein Beleg angelegt.", "Überspringen")) return;
      await api("/api/fixkosten/skip", {id:+b.dataset.vskip}); await reload(); vFix(); });
    bindCommon();
  }
  EXT.views.fixkosten = vFix;
  window.vFix = vFix;
})();
