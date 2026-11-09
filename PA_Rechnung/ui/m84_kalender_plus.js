// PA Rechnung v2.6.5 - UI-Modul m84_kalender_plus: Kalender in beide Richtungen
// v2.6.5: Ziel-Kalender TimeTree (m84b) mit Status/Diagnose, TimeTree-Termine bearbeiten/loeschen, Kurstermine (m84c)
// Eigene Termine anlegen/bearbeiten, Programm-Termine (Faelligkeiten, Wartung, Projekte ...) im Kalender,
// aus jedem Termin: Fahrt erfassen, Zeit buchen, Rechnung, Unterrichtsstunde; ICS-Datei und ICS-Abo.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const durH = e => { if (e.all_day) return 0; const a = new Date(e.start), b = new Date(e.end); const h = (b - a) / 3600000; return h > 0 && h < 24 ? Math.round(h * 4) / 4 : 0; };
  const projOpts = (sel, cid) => { const ps = S.projects.filter(p => p.status !== "archiviert"); const a = cid ? ps.filter(p => p.customer_id == cid) : [];
    const rest = ps.filter(p => !a.includes(p));
    return `<option value="">–</option>${a.length ? `<optgroup label="Projekte des Kunden">${a.map(p => `<option value="${p.id}" ${p.id == sel ? "selected" : ""}>${esc((p.nr ? p.nr + " " : "") + p.name)}</option>`).join("")}</optgroup>` : ""}
      <optgroup label="Alle Projekte">${rest.map(p => `<option value="${p.id}" ${p.id == sel ? "selected" : ""}>${esc((p.nr ? p.nr + " " : "") + p.name)}</option>`).join("")}</optgroup>`; };
  const custOpts = sel => `<option value="">–</option>` + [...S.customers].sort((a, b) => cname(a).localeCompare(cname(b), "de")).map(c => `<option value="${c.id}" ${c.id == sel ? "selected" : ""}>${esc(cname(c))}</option>`).join("");
  async function guess(e){ return api(`/api/m84/raten?title=${encodeURIComponent(e.title || "")}&ort=${encodeURIComponent(e.ort || "")}&datum=${(e.start || "").slice(0, 10)}`, undefined, {quiet:true}); }
  const refresh = () => { if (view === "kalender" && EXT.views.kalender) EXT.views.kalender(); };

  // ---------- own appointments ----------
  async function editTermin(t, preset){
    if (t && t.id && !t.titel) { const r = await api("/api/m84/termin?id=" + t.id); t = r.termin || t; }
    t = t || Object.assign({datum: todayIso(), von: "09:00", bis: "10:00", ganztags: 0}, preset || {});
    const neu = !t.id;
    const Z = await api("/api/m48/ziele", undefined, {quiet:true}) || {kalender:[]};
    const zcal = t.id ? (t.tt_cal || "") : (preset && preset.tt_cal !== undefined ? preset.tt_cal : (Z.standard || ""));
    const zOpts = `<option value="">Nur im Programm (Eigene Termine)</option>` + (Z.kalender || []).map(c => `<option value="${esc(c.id)}" ${c.id === zcal ? "selected" : ""}>TimeTree: ${esc(c.name)}</option>`).join("");
    const lOpts = cid => { const c = (Z.kalender || []).find(c_ => c_.id === cid); const ls = (c && c.labels) || [];
      return `<option value="">Standard</option>` + ls.map(l => `<option value="${l.id}" ${l.id == t.tt_label ? "selected" : ""}>${esc(l.name)}</option>`).join(""); };
    const stTxt = (Z.status_texte || {})[t.tt_status || ""] || "";
    const stBox = t.tt_cal ? `<div class="${["fehler", "pruefen"].includes(t.tt_status) ? "alert warn" : "hl"} small" style="cursor:default;margin-bottom:8px"><span>TimeTree: <b>${esc(stTxt)}</b>${t.tt_fehler ? " – " + esc(t.tt_fehler) : ""}</span></div>` : "";
    const html = `<div class="fr">${stBox}<div class="row"><label class="f">Kalender<select class="in" id="m84z">${zOpts}</select></label>
        <label class="f" style="flex:.7" id="m84lw">TimeTree-Label<select class="in" id="m84l">${lOpts(zcal)}</select></label></div>
      ${!(Z.kalender || []).length ? `<div class="small muted" style="margin:-4px 0 6px">${Z.zugang ? "Noch keine TimeTree-Kalender geladen – unter Kalender erst „Abrufen“." : "Für TimeTree: unter Kalender → Einstellungen E-Mail und Passwort eintragen und abrufen."}</div>` : ""}
      <label class="f">Titel<input class="in" id="m84t" value="${esc(t.titel || "")}" placeholder="z. B. Inbetriebnahme Saal 2, Kunde XY"></label>
      <div class="row"><label class="f" style="flex:.8">Datum<input type="date" class="in" id="m84d" value="${esc(t.datum || todayIso())}"></label>
        <label class="f" style="flex:.55">von<input type="time" class="in" id="m84v" value="${esc(t.von || "")}"></label><label class="f" style="flex:.55">bis<input type="time" class="in" id="m84b" value="${esc(t.bis || "")}"></label>
        <label class="f" style="flex:.8">bis Datum (mehrtägig)<input type="date" class="in" id="m84bd" value="${esc(t.bis_datum || "")}"></label>
        <label class="chk" style="flex:none;align-self:flex-end;margin-bottom:8px"><input type="checkbox" id="m84g" ${t.ganztags ? "checked" : ""}> ganztägig</label></div>
      <label class="f">Ort<input class="in" id="m84o" value="${esc(t.ort || "")}" placeholder="Adresse oder Ort"></label>
      <div class="row"><label class="f">Kunde<select class="in" id="m84c">${custOpts(t.customer_id)}</select></label>
        <label class="f">Projekt<select class="in" id="m84p">${projOpts(t.project_id, t.customer_id)}</select></label></div>
      <label class="f">Notiz<textarea class="in" id="m84n" rows="3">${esc(t.notiz || "")}</textarea></label>
      <div class="small muted" id="m84zh"></div></div>`;
    const btns = [{label:"Abbrechen"}, {label:"Speichern", cls:"pri", onClick: async mb => {
      const gt = $("#m84g", mb).checked;
      const r = await api("/api/m84/termin", {id:t.id || null, titel:$("#m84t", mb).value, datum:$("#m84d", mb).value, bis_datum:$("#m84bd", mb).value,
        von:gt ? "" : $("#m84v", mb).value, bis:gt ? "" : $("#m84b", mb).value, ganztags:gt, ort:$("#m84o", mb).value,
        customer_id:+$("#m84c", mb).value || null, project_id:+$("#m84p", mb).value || null, notiz:$("#m84n", mb).value,
        tt_cal:$("#m84z", mb).value, tt_label:$("#m84l", mb).value});
      if (!r || !r.ok) return false;
      if (r.tt_status === "ok") toast((neu ? "Termin angelegt" : "Termin gespeichert") + " – in TimeTree übertragen ✓");
      else if (r.tt_status) toast(`Im Programm gespeichert. TimeTree: ${r.tt_text}${r.tt_fehler ? " – " + r.tt_fehler : ""}`, ["fehler", "pruefen"].includes(r.tt_status));
      else toast(neu ? "Termin angelegt" : "Termin gespeichert"); }}];
    if (!neu) btns.unshift({label:"Löschen", cls:"danger", value:"del"});
    if (t.tt_cal && ["fehler", "pruefen", "wartet"].includes(t.tt_status)) btns.unshift({label:"Erneut übertragen", value:"retry"});
    const v = await modal(neu ? "Neuer Termin" : "Termin bearbeiten", html, btns, false, mb => {
      const g = $("#m84g", mb), sync = () => { $("#m84v", mb).disabled = $("#m84b", mb).disabled = g.checked; }; g.onchange = sync; sync();
      const z = $("#m84z", mb), zs = () => { $("#m84lw", mb).style.display = z.value ? "" : "none";
        $("#m84zh", mb).textContent = z.value ? "Wird beim Speichern in TimeTree eingetragen; danach lädt das Programm TimeTree neu und prüft, ob der Termin angekommen ist."
          : "Eigene Termine stehen im Kalender „Eigene Termine“ und – wenn eingeschaltet – im ICS-Abo fürs Handy."; };
      z.onchange = () => { $("#m84l", mb).innerHTML = lOpts(z.value); zs(); }; zs();
      $("#m84c", mb).onchange = () => { $("#m84p", mb).innerHTML = projOpts(+$("#m84p", mb).value, +$("#m84c", mb).value); };
      if (neu) setTimeout(() => { const i = $("#m84t", mb); if (i) i.focus(); }, 50); });
    if (v === "del") { const r = await api("/api/m84/termin", {delete:true, id:t.id}); if (r && r.ok) toast(r.warnung || (t.tt_cal ? "Termin gelöscht (auch in TimeTree)" : "Termin gelöscht"), !!r.warnung); }
    if (v === "retry") { toast("Übertrage nach TimeTree …"); const r = await api("/api/m48/retry", {id:t.id}); const s_ = ((r && r.termine) || [])[0] || {};
      toast(s_.tt_status === "ok" ? "In TimeTree übertragen ✓" : `TimeTree: ${(Z.status_texte || {})[s_.tt_status] || s_.tt_status || "?"}${s_.tt_fehler ? " – " + s_.tt_fehler : ""}`, s_.tt_status !== "ok"); }
    if (v !== null) refresh();
  }

  // ---------- actions from an appointment ----------
  async function asTrip(e){
    const g = await guess(e) || {};
    const v = await modal("Als Fahrt erfassen", `<div class="fr"><div class="row"><label class="f" style="flex:.7">Datum<input type="date" class="in" id="m84fd" value="${(e.start || "").slice(0, 10)}"></label>
        <label class="f">Ziel<input class="in" id="m84fz" value="${esc(e.ort || e.title || "")}"></label><label class="f" style="flex:.5">km (einfach + zurück)<input class="in num" id="m84fk" value="${g.km_letzte ? nde(g.km_letzte, 1) : ""}" placeholder="z. B. 84"></label></div>
      <label class="f">Zweck<input class="in" id="m84fw" value="${esc(e.title || "")}"></label>
      <div class="row"><label class="f">Kunde<select class="in" id="m84fc">${custOpts(g.customer_id)}</select></label><label class="f">Projekt<select class="in" id="m84fp">${projOpts(g.project_id, g.customer_id)}</select></label>
        <label class="f" style="flex:.6">Art<select class="in" id="m84fa"><option value="dienst">Dienstfahrt</option><option value="pendel">Pendelfahrt (Gehalt)</option></select></label></div>
      ${g.km_letzte ? `<div class="small muted">km von der letzten Fahrt zum selben Ziel übernommen.</div>` : `<div class="small muted">Kunde/Projekt aus Titel und Ort erraten – bitte prüfen.</div>`}</div>`,
      [{label:"Abbrechen"}, {label:"Fahrt speichern", cls:"pri", onClick: async mb => {
        const r = await api("/api/m84/fahrt", {datum:$("#m84fd", mb).value, ziel:$("#m84fz", mb).value, zweck:$("#m84fw", mb).value, km:pnum($("#m84fk", mb).value),
          art:$("#m84fa", mb).value, customer_id:+$("#m84fc", mb).value || null, project_id:+$("#m84fp", mb).value || null, notiz:"aus Kalender"});
        return !!(r && r.ok); }}]);
    if (v !== null) toast("Fahrt erfasst");
  }
  async function asTime(e){
    const g = await guess(e) || {};
    const std = (S.articles || []).filter(a => a.active !== 0 && /std|stunde/i.test((a.unit || "") + " " + a.name));
    const h = durH(e);
    const v = await modal("Zeit buchen", `<div class="fr"><div class="row"><label class="f">Projekt<select class="in" id="m84zp">${projOpts(g.project_id, g.customer_id)}</select></label>
        <label class="f" style="flex:.6">Datum<input type="date" class="in" id="m84zd" value="${(e.start || "").slice(0, 10)}"></label><label class="f" style="flex:.45">Stunden<input class="in num" id="m84zh" value="${h ? nde(h, 2) : ""}"></label></div>
      <div class="row"><label class="f">Baustein (Stundensatz)<select class="in" id="m84za"><option value="">– Stundensatz aus Einstellungen (${eur(g.stundensatz || 0)}) –</option>${std.map(a => `<option value="${a.id}" data-p="${a.price}">${esc((a.nr ? a.nr + " " : "") + a.name)} (${eur(a.price)})</option>`).join("")}</select></label>
        <label class="f" style="flex:.45">Preis/Std €<input class="in num" id="m84zr" value="${nde(g.stundensatz || 0)}"></label></div>
      <label class="f">Tätigkeit<input class="in" id="m84zt" value="${esc(e.title || "")}"></label>
      <div class="small muted">Wird im Projekt unter „Leistungen &amp; Material“ als Arbeitszeit eingetragen und kann von dort abgerechnet werden.</div></div>`,
      [{label:"Abbrechen"}, {label:"Zeit buchen", cls:"pri", onClick: async mb => {
        const r = await api("/api/m84/zeit", {project_id:+$("#m84zp", mb).value || null, datum:$("#m84zd", mb).value, stunden:pnum($("#m84zh", mb).value),
          article_id:+$("#m84za", mb).value || null, price:pnum($("#m84zr", mb).value), descr:$("#m84zt", mb).value});
        return !!(r && r.ok); }}], false,
      mb => { $("#m84za", mb).onchange = ev => { const o = ev.target.selectedOptions[0]; if (o && o.dataset.p) $("#m84zr", mb).value = nde(+o.dataset.p); }; });
    if (v !== null) { toast("Zeit gebucht"); try { await reload(); } catch (e2) {} }
  }
  async function asInvoice(e){
    const g = await guess(e) || {};
    const h = durH(e) || 1;
    const draft = {titel: e.title || "", items: [{qty:h, nr:"", name:e.title || "Leistung", descr:`${dde((e.start || "").slice(0, 10))}${e.ort ? " · " + e.ort : ""}`, price:g.stundensatz || 0, rabatt:0}]};
    if (g.project_id) draft.project_id = g.project_id;
    newInvoice({customer_id:g.customer_id || undefined, draft});
    toast(g.customer_id ? "Rechnungsentwurf mit Kunde " + (g.kunde || "") : "Rechnungsentwurf – bitte Kunde wählen");
  }
  async function asLesson(e){
    const g = await guess(e) || {};
    const st = (S.students || []).filter(s => s.aktiv);
    if (!st.length && !(S.kurse || []).some(k => k.aktiv)) { toast("Keine aktiven Kurse oder Schüler/innen angelegt", true); return; }
    const v = await modal("Unterrichtsstunde eintragen", `<div class="fr"><div class="row"><label class="f">Schüler/in<select class="in" id="m84us"><option value="">– nur Kurstermin (ohne Schüler) –</option>${st.map(s => `<option value="${s.id}" ${s.id == g.student_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></label>
        <label class="f" style="flex:.6">Datum<input type="date" class="in" id="m84ud" value="${(e.start || "").slice(0, 10)}"></label><label class="f" style="flex:.45">Dauer (Std)<input class="in num" id="m84uh" value="${durH(e) ? nde(durH(e), 2) : ""}"></label></div>
      <label class="f">Kurs (optional – ohne Schüler wird ein Kurstermin angelegt, Teilnehmer kannst du später nachtragen)<select class="in" id="m84uk"><option value="">–</option>${(S.kurse || []).filter(k => k.aktiv).map(k => `<option value="${k.id}" ${g.kurs_id == k.id ? "selected" : ""}>${esc(k.name)}</option>`).join("")}</select></label>
      <label class="f">Notiz<input class="in" id="m84un" value="${esc(e.title || "")}"></label></div>`,
      [{label:"Abbrechen"}, {label:"Eintragen", cls:"pri", onClick: async mb => {
        if (!+$("#m84us", mb).value && !+$("#m84uk", mb).value) { toast("Bitte Schüler/in oder Kurs wählen", true); return false; }
        const ev = e.all_day ? {} : {von:(e.start || "").slice(11, 16), bis:(e.end || "").slice(11, 16)};
        const r = await api("/api/m84/stunde", Object.assign({student_id:+$("#m84us", mb).value || null, datum:$("#m84ud", mb).value, dauer:pnum($("#m84uh", mb).value) || null,
          kurs_id:+$("#m84uk", mb).value || null, notiz:$("#m84un", mb).value}, ev));
        if (r && r.kurstermin) toast(`Kurstermin eingetragen${r.n ? " (" + r.n + " Teilnehmer)" : " – Teilnehmer kannst du im Kurs nachtragen"}`);
        return !!(r && r.ok); }}]);
    if (v !== null && !$(".tst")) toast("Unterrichtsstunde eingetragen");
  }
  function openProg(ref){
    if (!ref) return;
    if (ref.kind === "invoice") openInvoice(ref.id);
    else if (ref.kind === "project") go("project", ref.id);
    else if (ref.kind === "abo") go("abo");
    else if (ref.kind === "cert") go("certs");
    else if (ref.kind === "customer") go(EXT.views.m83akte ? "m83akte" : "users", ref.id);
    else if (ref.kind === "school") go("school");
    else if (ref.kind && EXT.views[ref.kind]) go(ref.kind, ref.id);
  }

  // inject action buttons into the appointment dialog of m29
  // v2.0.19 (R4): the dialogs of m29 open after a server request (day dialog) - wait for the new,
  // visible dialog instead of taking the last ".mb" (could be a parked, hidden dialog)
  const topMb = () => [...document.querySelectorAll(".mb")].filter(m => !m.hidden).pop();
  function whenNewMb(before, fn){
    let n = 0;
    const t = () => { const mb = topMb(); if (mb && mb !== before) return fn(mb); if (++n < 40) setTimeout(t, 50); };
    setTimeout(t, 0);
  }
  function inject(e){
    const before = topMb();
    whenNewMb(before && $(".m84act", before) ? before : null, mb => {
      if (!mb || $(".m84act", mb)) return;
      const mc = $(".mc", mb); if (!mc) return;
      const m = e.m84 || {};
      const box = document.createElement("div"); box.className = "m84act"; box.style.cssText = "margin-top:12px;padding-top:10px;border-top:1px solid var(--line)";
      let h = "";
      if (m.kind === "termin") h += `<button class="btn sm pri" data-m84x="edit">${ic("set")} Bearbeiten</button><button class="btn sm ghost danger" data-m84x="del">${ic("trash")} Löschen</button>`;
      if (m.kind === "prog") h += `<button class="btn sm pri" data-m84x="open">Öffnen</button>`;
      const t48 = e.m48 || {};
      if (t48.tt && t48.edit) h += `<button class="btn sm pri" data-m84x="ttedit">${ic("set")} Bearbeiten</button><button class="btn sm ghost danger" data-m84x="ttdel">${ic("trash")} Löschen</button>`;
      if (t48.status && t48.status !== "ok") h += `<div class="${["fehler", "pruefen"].includes(t48.status) ? "alert warn" : "hl"} small" style="cursor:default;width:100%;margin-bottom:6px"><span>TimeTree (${esc(t48.ziel || "")}): <b>${esc(t48.text || "")}</b>${t48.fehler ? " – " + esc(t48.fehler) : ""}</span></div>
        <button class="btn sm" data-m84x="ttretry">Erneut übertragen</button><button class="btn sm ghost" data-m84x="ttdiag">Diagnose</button>`;
      if (m.kind !== "prog") h += `<button class="btn sm" data-m84x="trip">${ic("car")} Als Fahrt erfassen</button><button class="btn sm" data-m84x="time">${ic("clock")} Zeit buchen</button>
        <button class="btn sm" data-m84x="inv">${ic("plus")} Rechnung daraus</button>${((S.students || []).some(s => s.aktiv) || (S.kurse || []).some(k => k.aktiv)) ? `<button class="btn sm" data-m84x="lesson">${ic("school")} Unterrichtsstunde</button>` : ""}`;
      box.innerHTML = `<div class="row" style="flex-wrap:wrap;gap:6px">${h}</div>`;
      mc.appendChild(box);
      const close = () => { const b = [...$$(".mf .btn", mb)].pop(); if (b) b.click(); else mb.remove(); };
      $$("[data-m84x]", box).forEach(b => b.onclick = async () => {
        const a = b.dataset.m84x; close();
        if (a === "edit") editTermin({id:m.id});
        else if (a === "del") { await api("/api/m84/termin", {delete:true, id:m.id}); toast("Termin gelöscht"); refresh(); }
        else if (a === "open") openProg(m.ref);
        else if (a === "ttedit" || a === "ttdel") {
          const r = await api("/api/m48/uebernehmen", {cal_id:e.m48.cal, uuid:e.m48.uuid}); if (!r || !r.ok) return;
          if (a === "ttedit") editTermin({id:r.id});
          else if (await confirmBox(`„${e.title}“ in TimeTree löschen?`, "Löschen")) { const d_ = await api("/api/m84/termin", {delete:true, id:r.id});
            if (d_ && d_.ok) { toast(d_.warnung || "In TimeTree gelöscht", !!d_.warnung); refresh(); } } }
        else if (a === "ttretry") { toast("Übertrage nach TimeTree …"); const r = await api("/api/m48/retry", {id:m.id}); const s_ = ((r && r.termine) || [])[0] || {};
          toast(s_.tt_status === "ok" ? "In TimeTree übertragen ✓" : `TimeTree: ${s_.tt_fehler || s_.tt_status || "?"}`, s_.tt_status !== "ok"); refresh(); }
        else if (a === "ttdiag") ttDiag();
        else if (a === "trip") asTrip(e);
        else if (a === "time") asTime(e);
        else if (a === "inv") asInvoice(e);
        else if (a === "lesson") asLesson(e);
      });
      if (m.kind === "termin" || (e.m48 && e.m48.edit)) { const hint = [...$$(".small.muted", mc)].find(x_ => /TimeTree ändern/.test(x_.textContent)); if (hint) hint.remove(); }
    });
  }
  function injectDay(k){
    whenNewMb(topMb(), mb => { if (!mb || $(".m84day", mb)) return; const mc = $(".mc", mb); if (!mc) return;
      const b = document.createElement("button"); b.className = "btn sm m84day"; b.style.marginTop = "10px"; b.innerHTML = ic("plus") + " Neuer Termin an diesem Tag";
      b.onclick = () => { const c = [...$$(".mf .btn", mb)].pop(); if (c) c.click(); editTermin(null, {datum:k}); };
      mc.appendChild(b);
      // appointments inside the day dialog open via m29 evDialog -> add actions there too
      $$("[data-kev]", mb).forEach(x_ => x_.addEventListener("click", () => { try { inject(JSON.parse(x_.dataset.kev)); } catch (er) {} }));
    });
  }
  document.addEventListener("click", ev => {
    if (view !== "kalender" && !$(".dwc")) return;
    const k = ev.target.closest && ev.target.closest("[data-kev]");
    if (k && !k.closest(".mb")) { try { inject(JSON.parse(k.dataset.kev)); } catch (er) {} return; }
    const d = ev.target.closest && (ev.target.closest("[data-kday]") || ev.target.closest(".kday[data-kd]"));
    if (d && !d.closest(".mb")) injectDay(d.dataset.kday || d.dataset.kd);
  }, true);
  if (typeof window.kalEvDialog === "function") {
    const orig = window.kalEvDialog;
    window.kalEvDialog = function(e){ const r = orig.apply(this, arguments); inject(e); return r; };
  }

  // ---------- ICS export / subscription ----------
  async function icsOpen(){
    const info = await api("/api/kal/info"); const m = info.m84 || {}; const cfg = m.cfg || {}; const arten = m.arten || {}; const abo = m.abo || {};
    let vals = null;
    const read = mb => ({arten:$$("[data-m84art]", mb).filter(c => c.checked).map(c => c.dataset.m84art), eigen:$("#m84ie", mb).checked, timetree:$("#m84it", mb).checked,
      tage_zurueck:Math.round(pnum($("#m84iz", mb).value)), tage_voraus:Math.round(pnum($("#m84iv", mb).value))});
    const v = await modal("Programm-Termine & ICS-Abo", `<div class="fr">
      <div class="small muted">Diese Termine erscheinen im Kalender „Programm-Termine“ und lassen sich als .ics-Datei speichern oder als Abo im Handy-Kalender (iPhone, Android, Outlook) einbinden.</div>
      <div><b class="small">Welche Termine?</b><div class="grid" style="grid-template-columns:1fr 1fr;gap:4px;margin-top:6px">
        ${Object.entries(arten).map(([k, l]) => `<label class="chk"><input type="checkbox" data-m84art="${k}" ${(cfg.arten || []).includes(k) ? "checked" : ""}> ${esc(l)}</label>`).join("")}
        <label class="chk"><input type="checkbox" id="m84ie" ${cfg.eigen ? "checked" : ""}> Eigene Termine</label>
        <label class="chk"><input type="checkbox" id="m84it" ${cfg.timetree ? "checked" : ""}> TimeTree-Termine (nur Datei/Abo)</label></div></div>
      <div class="row"><label class="f">Tage zurück<input class="in num" id="m84iz" value="${cfg.tage_zurueck ?? 60}"></label><label class="f">Tage voraus<input class="in num" id="m84iv" value="${cfg.tage_voraus ?? 400}"></label></div>
      <div class="hl small" id="m84abo">${abo.aktiv ? `<b>Abo fürs Handy:</b> <button class="btn sm" type="button" id="m84abl">Abo-Adresse erzeugen</button><br><span class="muted">Erzeugt einen eigenen Lese-Zugang „Kalender-Abo“ (widerrufbar unter Einstellungen → „Schnittstelle &amp; Handy“). Im Handy: Kalender → Kalender hinzufügen → Abonnement → Adresse einfügen. Nur im eigenen Netz/VPN erreichbar.</span>`
        : abo.verfuegbar ? `Das ICS-Abo ist verfügbar, sobald unter Einstellungen → „Schnittstelle &amp; Handy“ der Server eingeschaltet ist.` : `Für das Abo am Handy wird die Schnittstelle (Einstellungen → „Schnittstelle &amp; Handy“) gebraucht. Ohne sie: .ics-Datei speichern und im Kalender importieren.`}</div></div>`,
      [{label:"Abbrechen"}, {label:"Als .ics speichern", onClick: async mb => { vals = read(mb); return true; }, value:"exp"},
       {label:"Speichern", cls:"pri", onClick: async mb => { vals = read(mb); return true; }, value:"ok"}], false, mb => {
        const b = $("#m84abl", mb); if (!b) return;
        b.onclick = async () => {
          const r = await api("/api/m88/token/new", {name: "Kalender-Abo", recht: "lesen", typ: "ics"}); if (!r || !r.ok) return;
          const u = (abo.base || "") + "/ics/" + r.token + ".ics";
          $("#m84abo", mb).innerHTML = `<b>Abo-Adresse fürs Handy</b> (nur jetzt sichtbar – kopieren):<br><code style="word-break:break-all;user-select:all">${esc(u)}</code>
            <br><button class="btn sm" type="button" id="m84abc" style="margin-top:6px">Kopieren</button>`;
          $("#m84abc", mb).onclick = () => { try { navigator.clipboard.writeText(u); toast("Adresse kopiert"); } catch (e) {} };
        };
      });
    if (v === null || !vals) return;
    const r = await api("/api/m84/cfg", vals); if (!r || !r.ok) return;
    if (v === "exp") { const e = await api("/api/m84/export", {}); if (e && e.ok) toast(`${e.n} Termine gespeichert: ${e.path.split(/[\\/]/).pop()}`); }
    else toast("Einstellungen gespeichert");
    refresh();
  }

  // ---------- calendar page: extra buttons ----------
  const origView = EXT.views.kalender;
  if (typeof origView === "function") {
    EXT.views.kalender = async function(){
      const r = await origView.apply(this, arguments);
      try {
        const act = $("#main .ph .act");
        if (act && !$("#m84new", act)) {
          const b1 = document.createElement("button"); b1.className = "btn"; b1.id = "m84ics"; b1.type = "button"; b1.innerHTML = ic("cal") + " Programm-Termine / Abo"; b1.onclick = icsOpen;
          const b2 = document.createElement("button"); b2.className = "btn pri"; b2.id = "m84new"; b2.type = "button"; b2.innerHTML = ic("plus") + " Neuer Termin"; b2.onclick = () => editTermin(null);
          act.prepend(b1); act.prepend(b2);
          const sync = $("#ksync", act); if (sync) sync.classList.remove("pri");
        }
      } catch (e) { console.error(e); }
      return r;
    };
  }
  // v2.6.5: last TimeTree calls (for troubleshooting the unofficial write access)
  async function ttDiag(){
    const z = await api("/api/m48/ziele") || {};
    const d = (z.diag || []).slice().reverse();
    const rows = d.length ? d.map(x => `<tr><td class="small">${esc(x.zeit || "")}</td><td class="small"><b>${esc(x.aufruf || "")}</b></td><td class="small">${esc(String(x.http || ""))}</td><td class="small" style="word-break:break-all">${esc(String(x.antwort || x.fehler || "")).slice(0, 300)}</td></tr>`).join("")
      : `<tr><td colspan="4" class="muted small">Noch keine Aufrufe gespeichert.</td></tr>`;
    const v = await modal("TimeTree – Diagnose", `<div class="small muted" style="margin-bottom:8px">Die letzten Aufrufe an TimeTree (ohne Passwort). Bei Problemen diese Liste abfotografieren oder kopieren.</div>
      <div class="scroll" style="max-height:55vh"><table class="tbl"><thead><tr><th>Zeit</th><th>Aufruf</th><th>HTTP</th><th>Antwort</th></tr></thead><tbody>${rows}</tbody></table></div>`,
      [{label:"Liste leeren", value:"clear"}, {label:"Schließen", cls:"pri"}], true);
    if (v === "clear") { await api("/api/m48/diag_clear", {}); toast("Diagnose geleert"); }
  }
  window.m84TtDiag = ttDiag;
  window.m84EditTermin = editTermin;
  window.m84IcsDialog = icsOpen;
})();
