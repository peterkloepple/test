// PA Rechnung v2.0.9 - Dauerfahrten (wiederkehrende Fahrten) in der Seite "Fahrten"
// Karte "Dauerfahrten" mit Vorlagen, Vorschlaege zum Bestaetigen, Dialog mit Vorschau,
// Knopf "als Dauerfahrt" an jeder Fahrt, Markierung erzeugter Fahrten.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const WD = ["Mo","Di","Mi","Do","Fr","Sa","So"];

  async function fsDialog(s){
    s = Object.assign({rhythmus:"woche", wochentage:"", alle_n:1, monatstag:"", nth:1, start:todayIso(), ende:"", modus:"auto", feiertage:1, aktiv:1, art:"dienst"}, s||{});
    const wds = new Set(String(s.wochentage||"").split(",").filter(Boolean).map(Number));
    const opt = (v, l, cur) => `<option value="${v}" ${String(v)===String(cur)?"selected":""}>${l}</option>`;
    const pr = modal(s.id ? "Dauerfahrt bearbeiten" : "Neue Dauerfahrt", `<div class="fr">
      <div class="row"><label class="f">Name<input class="in" id="fsn" value="${esc(s.name||"")}" placeholder="z. B. Wartung BPM City"></label>
        <label class="f" style="flex:.7">Art<select class="in" id="fsa">${opt("dienst","Dienstfahrt (gefahrene km gesamt)",s.art)}${opt("pendel","Fahrt zur Arbeit (einfache Entfernung)",s.art)}</select></label></div>
      <div class="row"><label class="f">Ziel<input class="in" id="fsz" value="${esc(s.ziel||"")}" placeholder="z. B. Kunde, Ort"></label><label class="f">Zweck<input class="in" id="fsw" value="${esc(s.zweck||"")}" placeholder="Unterricht, Wartung …"></label>
        <label class="f" style="flex:.35">km<input class="in num" id="fsk" value="${s.km?nde(s.km,1):""}"></label></div>
      <div class="row"><label class="f">Projekt<select class="in" id="fsp"><option value="">–</option>${S.projects.map(p=>opt(p.id, esc(p.nr+" "+p.name), s.project_id)).join("")}</select></label>
        <label class="f">Kunde<select class="in" id="fsc"><option value="">–</option>${S.customers.map(c=>opt(c.id, esc(cname(c)), s.customer_id)).join("")}</select></label></div>
      <div class="card" style="padding:12px;background:var(--panel2)"><div class="row" style="align-items:flex-end;flex-wrap:wrap">
        <label class="f" style="flex:1.1">Rhythmus<select class="in" id="fsr">${opt("woche","wöchentlich an bestimmten Tagen",s.rhythmus)}${opt("monat","monatlich an einem festen Tag",s.rhythmus)}${opt("monat_wt","monatlich am n-ten Wochentag",s.rhythmus)}</select></label>
        <label class="f" style="flex:.45"><span id="fsnl">alle … Wochen</span><input class="in num" id="fsall" value="${s.alle_n||1}"></label>
        <label class="f fsm" style="flex:.45">Tag im Monat<input class="in num" id="fsmt" value="${esc(s.monatstag||"")}" placeholder="1–31"></label>
        <label class="f fsx" style="flex:.55">Welcher<select class="in" id="fsnth">${[[1,"1."],[2,"2."],[3,"3."],[4,"4."],[-1,"letzter"]].map(([v,l])=>opt(v,l,s.nth)).join("")}</select></label></div>
        <div class="row fsw" style="gap:6px;margin-top:8px;flex-wrap:wrap">${WD.map((w,i)=>`<label class="chk fswd" style="flex:none;padding:4px 10px;border:1px solid var(--line);border-radius:8px"><input type="checkbox" value="${i+1}" ${wds.has(i+1)?"checked":""}> ${w}</label>`).join("")}</div>
        <div class="row" style="margin-top:8px"><label class="f">Ab<input type="date" class="in" id="fss" value="${esc(s.start||"")}"></label><label class="f">Bis (leer = unbegrenzt)<input type="date" class="in" id="fse" value="${esc(s.ende||"")}"></label></div>
        <label class="chk" style="margin-top:6px"><input type="checkbox" id="fsft" ${s.feiertage?"checked":""}> Feiertage auslassen (${esc((S.fs_land_name)||"Bundesland unten auf der Seite")})</label>
        <div class="small muted" id="fspv" style="margin-top:8px">…</div></div>
      <div class="row"><label class="f">Eintragen<select class="in" id="fsmo">${opt("auto","automatisch – Fahrten erscheinen am Tag selbst",s.modus)}${opt("vorschlag","als Vorschlag – ich bestätige jede Fahrt",s.modus)}</select></label>
        <label class="chk" style="flex:none;align-self:flex-end;padding-bottom:8px"><input type="checkbox" id="fsak" ${s.aktiv?"checked":""}> aktiv</label></div>
      <label class="f">Notiz<input class="in" id="fsno" value="${esc(s.notiz||"")}"></label>
      <div class="small muted">${s.id ? "Änderungen gelten ab heute – vergangene Termine werden beim Bearbeiten nicht nachgetragen." : "Vergangene Termine ab dem Startdatum werden beim ersten Speichern nachgetragen (höchstens gut ein Jahr zurück)."} Eine gelöschte Fahrt kommt nie wieder.</div></div>`,
      [...(s.id?[{label:"Löschen", cls:"danger", value:"del"}]:[]),{label:"Abbrechen"},{label:"Speichern", cls:"pri", value:"ok", onClick: async mb => {
        const r = await api("/api/fserie/save", Object.assign({id:s.id, quelle_fahrt_id:s.quelle_fahrt_id||null}, vals(mb)));
        if (!r || r.ok === false) return false;
        toast(r.angelegt ? `Gespeichert – ${r.angelegt} Fahrt(en) eingetragen` : "Dauerfahrt gespeichert"); }}], true);
    const mb = $$(".mb").pop();
    const vals = mb => ({name:$("#fsn",mb).value, art:$("#fsa",mb).value, ziel:$("#fsz",mb).value, zweck:$("#fsw",mb).value, km:pnum($("#fsk",mb).value),
      project_id:+$("#fsp",mb).value||null, customer_id:+$("#fsc",mb).value||null, rhythmus:$("#fsr",mb).value, alle_n:Math.max(1, Math.round(pnum($("#fsall",mb).value))||1),
      monatstag:Math.round(pnum($("#fsmt",mb).value))||null, nth:+$("#fsnth",mb).value, start:$("#fss",mb).value, ende:$("#fse",mb).value,
      wochentage:$$(".fswd input",mb).filter(e=>e.checked).map(e=>e.value).join(","), feiertage:$("#fsft",mb).checked?1:0, modus:$("#fsmo",mb).value,
      aktiv:$("#fsak",mb).checked?1:0, notiz:$("#fsno",mb).value});
    let pvT = null;
    const upd = () => {
      const r = $("#fsr",mb).value;
      $("#fsnl",mb).textContent = r === "woche" ? "alle … Wochen" : "alle … Monate";
      $(".fsm",mb).style.display = r === "monat" ? "" : "none";
      $(".fsx",mb).style.display = r === "monat_wt" ? "" : "none";
      $(".fsw",mb).style.display = r === "monat" ? "none" : "";
      if (r === "monat_wt") { // only one weekday makes sense
        const on = $$(".fswd input",mb).filter(e=>e.checked); on.slice(1).forEach(e=>e.checked=false); }
      clearTimeout(pvT); pvT = setTimeout(async () => {
        const p = await api("/api/fserie/preview", vals(mb), {quiet:true});
        const el = $("#fspv",mb); if (!el || !p) return;
        el.innerHTML = p.termine && p.termine.length ? `<b>${esc(p.text)}</b> · nächste Termine: ${p.termine.map(d=>WD[(new Date(d+"T12:00").getDay()+6)%7]+" "+dde(d)).join(", ")}` : `<b>${esc(p.text||"")}</b> · keine Termine im Zeitraum`;
      }, 200);
    };
    $$("input,select",mb).forEach(e => e.addEventListener("input", upd));
    $$(".fswd input",mb).forEach(e => e.addEventListener("change", () => { if ($("#fsr",mb).value === "monat_wt" && e.checked) $$(".fswd input",mb).forEach(o => { if (o !== e) o.checked = false; }); upd(); }));
    upd();
    const r = await pr;
    if (r === "del") {
      const anz = s.anzahl || 0;
      let mit = false;
      if (anz) { const a = await modal("Dauerfahrt löschen", `<div class="fr"><div>Aus dieser Vorlage wurden <b>${anz}</b> Fahrt(en) eingetragen.</div></div>`,
        [{label:"Abbrechen"},{label:"Vorlage löschen, Fahrten behalten", value:"keep"},{label:"Vorlage und alle Fahrten löschen", cls:"danger", value:"all"}]);
        if (!a) return; mit = a === "all"; }
      await api("/api/fserie/delete", {id:s.id, fahrten_mit:mit}); toast("Dauerfahrt gelöscht");
    }
    if (r) vTrips();
  }
  window.fsDialog = fsDialog;

  EXT.after.push(async n => {
    if (n !== "vTrips") return;
    const page = $("#main .page"); if (!page || $("#fscard")) return;
    const d = await api("/api/fserie/list", undefined, {quiet:true}); if (!d || !d.serien || view !== "trips") return;
    S.fs_land_name = (d.laender||{})[d.land] || d.land;
    const kpi = page.querySelector(".grid.g3");
    const card = document.createElement("div"); card.id = "fscard"; card.className = "card"; card.style.marginBottom = "14px";
    const vs = d.vorschlaege || [];
    card.innerHTML = `<div class="hd"><h3>${ic("sync")} Dauerfahrten</h3><div class="act">
        <label class="small muted" style="display:flex;gap:6px;align-items:center">Feiertage für <select class="in" id="fsland" style="width:auto;padding:3px 6px">${Object.entries(d.laender||{}).map(([k,l])=>`<option value="${k}" ${k===d.land?"selected":""}>${esc(l)}</option>`).join("")}</select></label>
        <button class="btn sm pri" id="fsnew">${ic("plus")} Dauerfahrt</button></div></div>
      ${vs.length?`<div class="bd" style="border-bottom:1px solid var(--line)"><div class="hl small" style="margin-bottom:8px"><b>${vs.length} Fahrt(en) warten auf Bestätigung</b> – Haken = eintragen, ohne Haken = Termin auslassen.</div>
        <div class="scroll" style="max-height:220px"><table class="t"><tbody>${vs.map((v,i)=>`<tr><td style="width:28px"><input type="checkbox" class="fsv" data-i="${i}" checked style="accent-color:var(--acc)"></td><td class="num">${WD[(new Date(v.datum+"T12:00").getDay()+6)%7]} ${dde(v.datum)}</td><td><b>${esc(v.name)}</b> <span class="small muted">${esc(v.ziel||"")}</span></td><td class="r num">${nde(v.km,1)} km</td></tr>`).join("")}</tbody></table></div>
        <div class="row" style="margin-top:8px;justify-content:flex-end;gap:8px"><button class="btn sm" id="fsvall">alle an/aus</button><button class="btn sm pri" id="fsvok">${ic("check")} Auswahl übernehmen</button></div></div>`:""}
      <table class="t"><tbody>${d.serien.map(s=>`<tr class="click" data-fs="${s.id}" style="${s.aktiv?"":"opacity:.5"}"><td><b>${esc(s.name)}</b><div class="small muted">${esc(s.ziel||"")}${s.zweck?" · "+esc(s.zweck):""}</div></td>
        <td class="small">${esc(s.rhythmus_text)}${s.feiertage?" · ohne Feiertage":""}<div class="muted">${dde(s.start)}${s.ende?" – "+dde(s.ende):" – offen"} · ${s.modus==="vorschlag"?"mit Bestätigung":"automatisch"}</div></td>
        <td class="small">${s.naechste?"nächste<br><b>"+dde(s.naechste)+"</b>":"–"}</td><td class="r num">${nde(s.km,1)} km<div class="small muted">${s.anzahl} eingetragen</div></td></tr>`).join("")
        || `<tr><td class="empty">Noch keine Dauerfahrten. Für Fahrten, die immer wiederkehren (z. B. jeden Dienstag zum Kunden), einmal eine Vorlage anlegen – oder in der Liste unten bei einer Fahrt auf ${ic("sync")} klicken.</td></tr>`}</tbody></table>`;
    if (kpi) kpi.after(card); else page.appendChild(card);
    $("#fsnew").onclick = () => fsDialog({});
    $("#fsland").onchange = async e => { await api("/api/fserie/land", {land:e.target.value}); toast("Bundesland gespeichert"); vTrips(); };
    $$("[data-fs]", card).forEach(r => r.onclick = () => fsDialog(d.serien.find(s => s.id == r.dataset.fs)));
    if (vs.length) {
      $("#fsvall").onclick = () => { const all = $$(".fsv", card); const on = all.some(e => !e.checked); all.forEach(e => e.checked = on); };
      $("#fsvok").onclick = async () => { const items = $$(".fsv", card).map(e => { const v = vs[+e.dataset.i]; return {serie_id:v.serie_id, datum:v.datum, use:e.checked}; });
        const r = await api("/api/fserie/apply", {items}); if (r && r.ok) { toast(`${r.angelegt} eingetragen, ${r.uebersprungen} ausgelassen`); await reload(); vTrips(); } };
    }
    // mark generated trips + "als Dauerfahrt" button per row
    let f = null; try { f = await api("/api/fahrten?year=" + trY, undefined, {quiet:true}); } catch (e) {}
    const byId = {}; ((f && f.rows) || []).forEach(r => byId[r.id] = r);
    $$("#main [data-fdel]").forEach(b => {
      const r = byId[b.dataset.fdel]; if (!r) return;
      const tr = b.closest("tr");
      if (r.serie_id) { const td = tr.children[1]; if (td && !td.querySelector(".fsmark")) td.insertAdjacentHTML("beforeend", ` <span class="fsmark small muted" title="aus Dauerfahrt">↻</span>`); return; }
      if (b.parentNode.querySelector("[data-fsmk]")) return;
      const x_ = document.createElement("button"); x_.className = "btn sm ghost"; x_.dataset.fsmk = r.id; x_.title = "Als Dauerfahrt anlegen (wiederkehrend)"; x_.innerHTML = ic("sync");
      x_.onclick = e => { e.stopPropagation(); const wd = ((new Date(r.datum + "T12:00").getDay() + 6) % 7) + 1;
        fsDialog({quelle_fahrt_id:r.id, name:r.ziel || r.zweck || "Dauerfahrt", ziel:r.ziel, zweck:r.zweck, km:r.km, art:r.art, project_id:r.project_id, customer_id:r.customer_id, wochentage:String(wd), start:r.datum, rhythmus:"woche"}); };
      b.before(x_);
    });
  });

  // sidebar counter on "Fahrten" when proposals wait
  EXT.after.push(() => {
    const n = S && S.fs_vorschlaege; const b = $('.lzone [data-go="trips"], .flwin [data-go="trips"], #side [data-go="trips"]'); if (!b) return;
    let c = b.querySelector(".cnt.fsc");
    if (n) { if (!c) { c = document.createElement("span"); c.className = "cnt fsc"; b.appendChild(c); } c.textContent = n; c.title = "Dauerfahrten warten auf Bestätigung"; }
    else if (c) c.remove();
  });
})();
