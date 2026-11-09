// Pfeiffer-Audio Rechnung v3.6.2 - UI-Modul m29b_kalender_abo v1.0.0: Kalender-Abos per Link (ICS / webcal)
// Knopf "Kalender-Abos" auf der Seite Kalender: Links hinzufuegen, Name, Farbe, Abruf-Intervall, ein/aus,
// jetzt abrufen, entfernen. Die Termine erscheinen als eigener Kalender (Chip oben) wie TimeTree-Kalender.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  const INT = [[15, "alle 15 Minuten"], [30, "alle 30 Minuten"], [60, "jede Stunde"], [240, "alle 4 Stunden"], [720, "alle 12 Stunden"], [1440, "einmal täglich"]];
  const short = u => String(u || "").replace(/^https?:\/\//, "").replace(/^(.{34}).{6,}(.{22})$/, "$1…$2");
  const when = z => z ? `${dde(z.slice(0, 10))} ${z.slice(11, 16)}` : "noch nie";

  const orig = EXT.views.kalender;
  if (orig) EXT.views.kalender = async function(...a){
    const r = await orig.apply(this, a);
    try {
      const act = $("#main .ph .act");
      if (act && !$("#kabo", act)) {
        const v = await api("/api/kalabo/liste", undefined, {quiet: true});
        const n = (v && v.abos || []).length, bad = (v && v.abos || []).filter(x => x.letzter && x.letzter.ok === false).length;
        const b = document.createElement("button"); b.className = "btn"; b.id = "kabo";
        b.innerHTML = `${ic("cal")} Kalender-Abos${n ? ` <span class="badge ${bad ? "bad" : ""}" style="margin-left:4px">${n}</span>` : ""}`;
        b.title = "Internet-Kalender per Link abonnieren (ICS / webcal)";
        b.onclick = () => aboDialog();
        act.prepend(b);
      }
    } catch (e) { console.error(e); }
    return r;
  };

  function row(x){
    const l = x.letzter || {};
    const st = x.laeuft ? `<span class="muted">wird abgerufen …</span>`
      : l.zeit ? `<span style="color:${l.ok ? "var(--ok)" : "var(--bad)"}">${l.ok ? "✓" : "✗"}</span> ${esc(when(l.zeit))} · ${esc(l.text || "")}` : `<span class="muted">noch nicht abgerufen</span>`;
    return `<tr data-abo="${esc(x.id)}"><td style="width:34px"><input type="color" value="${esc(x.farbe)}" data-afarbe style="width:28px;height:24px;border:0;padding:0;background:none"></td>
      <td><b>${esc(x.name || "(ohne Name)")}</b><div class="small muted" title="${esc(x.url)}">${esc(short(x.url))}</div></td>
      <td class="small">${st}</td><td class="r num">${nde(x.termine || 0, 0)}</td>
      <td class="small">${x.aktiv ? esc((INT.find(i => i[0] === x.intervall) || [0, x.intervall + " Min."])[1]) : `<span class="badge">aus</span>`}</td>
      <td class="r" style="white-space:nowrap"><button class="btn sm" data-aget title="Jetzt abrufen">${ic("sync")}</button><button class="btn sm ghost" data-aedit>Bearbeiten</button><button class="btn sm ghost" data-adel style="color:var(--bad)">Entfernen</button></td></tr>`;
  }

  function form(x){
    x = x || {intervall: 60, aktiv: true, farbe: "#ff9f0a"};
    return `<div class="fr" id="aboform">
      <label class="f">Link zum Kalender (https://… oder webcal://…)<input class="in" id="aurl" value="${esc(x.url || "")}" placeholder="https://…/kalender.ics" autocomplete="off"></label>
      <div class="row"><label class="f" style="flex:2">Name (leer = Name aus dem Kalender)<input class="in" id="aname" value="${esc(x.name || "")}" placeholder="z. B. MediaFlow Laufzeiten"></label>
        <label class="f" style="flex:none">Farbe<input type="color" class="in" id="afarbe" value="${esc(x.farbe || "#ff9f0a")}" style="width:60px;padding:2px"></label></div>
      <div class="row" style="align-items:flex-end"><label class="f">Automatisch abrufen<select class="in" id="aint">${INT.map(([v, l]) => `<option value="${v}" ${+x.intervall === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="chk" style="flex:none;margin-bottom:9px"><input type="checkbox" id="aakt" ${x.aktiv !== false ? "checked" : ""}> aktiv</label></div>
      <div class="small muted">Der Link wird nur gelesen – im Ursprungskalender ändert sich nichts. Wer den Link kennt, sieht die Termine: wie ein Passwort behandeln.</div></div>`;
  }

  async function edit(x){
    let res = null;
    const ok = await modal(x ? "Kalender-Abo bearbeiten" : "Kalender-Abo hinzufügen", form(x), [{label: "Abbrechen"},
      {label: x ? "Speichern & abrufen" : "Hinzufügen & abrufen", cls: "pri", value: 1, onClick: async mb => {
        const d = {id: x ? x.id : "", url: $("#aurl", mb).value.trim(), name: $("#aname", mb).value.trim(), farbe: $("#afarbe", mb).value,
          intervall: +$("#aint", mb).value, aktiv: $("#aakt", mb).checked};
        if (!d.url) { toast("Bitte den Link eintragen", true); return false; }
        toast("Kalender wird abgerufen …");
        res = await api("/api/kalabo/speichern", d);
        if (!res || res.ok === false) return false;
      }}]);
    if (ok && res) {
      const a = res.abruf || {};
      if (a.ok) toast(`„${a.name || "Kalender"}“: ${nde(a.termine || 0, 0)} Termine abonniert`);
      else if (a.error) toast("Gespeichert, aber Abruf fehlgeschlagen: " + a.error, true);
    }
    return ok;
  }

  async function aboDialog(){
    let v = await api("/api/kalabo/liste");
    if (!v) return;
    let changed = false;
    const render = mb => {
      const box = $("#abobox", mb);
      box.innerHTML = (v.abos || []).length
        ? `<table class="t nosort"><thead><tr><th></th><th>Kalender</th><th>Letzter Abruf</th><th class="r">Termine</th><th>Abruf</th><th></th></tr></thead><tbody>${v.abos.map(row).join("")}</tbody></table>`
        : `<div class="empty">Noch keine Kalender-Abos. Mit „Kalender-Abo hinzufügen“ einen Link eintragen – z. B. einen Laufzeiten-, Dienstplan-, Google- oder Outlook-Kalender.</div>`;
      $$("[data-abo]", box).forEach(tr => {
        const x = v.abos.find(a => a.id === tr.dataset.abo);
        $("[data-aget]", tr).onclick = async e => { e.currentTarget.disabled = true; const r = await api("/api/kalabo/abrufen", {id: x.id});
          if (r && r.ok) toast(`„${r.name || x.name}“: ${nde(r.termine || 0, 0)} Termine`); else if (r && r.error) toast(r.error, true);
          changed = true; v = await api("/api/kalabo/liste"); render(mb); };
        $("[data-aedit]", tr).onclick = async () => { if (await edit(x)) { changed = true; v = await api("/api/kalabo/liste"); render(mb); } };
        $("[data-adel]", tr).onclick = async () => { if (!await confirmBox(`Abo „${x.name || x.url}“ entfernen? Seine Termine verschwinden aus dem Programm (im Ursprung bleibt alles).`, "Entfernen")) return;
          v = await api("/api/kalabo/loeschen", {id: x.id}); changed = true; render(mb); };
        $("[data-afarbe]", tr).onchange = async e => { await api("/api/kalabo/speichern", {id: x.id, url: x.url, name: x.name, intervall: x.intervall, aktiv: x.aktiv, farbe: e.target.value, abrufen: false}); changed = true; };
      });
    };
    await modal("Kalender-Abos (Internet-Kalender per Link)", `<div class="fr nokeep"><div class="small muted">Jeder Link wird als eigener Kalender gespeichert und automatisch aktualisiert. Die Termine erscheinen unter Kalender (oben als farbiger Chip ein-/ausblendbar), in der Übersicht und bei der Termin-Suche.</div>
      <div id="abobox"></div></div>`,
      [{label: "Alle jetzt abrufen", onClick: async mb => { toast("Kalender-Abos werden abgerufen …"); const r = await api("/api/kalabo/abrufen", {});
          if (r && r.ok) toast(`${r.abgerufen} Abo(s) abgerufen` + ((r.fehler || []).length ? ` – ${r.fehler.length} mit Fehler: ${r.fehler[0]}` : ""), !!(r.fehler || []).length);
          changed = true; v = await api("/api/kalabo/liste"); render(mb); return false; }},
       {label: "+ Kalender-Abo hinzufügen", onClick: async mb => { if (await edit(null)) { changed = true; v = await api("/api/kalabo/liste"); render(mb); } return false; }},
       {label: "Schließen", cls: "pri"}], true, mb => render(mb));
    if (changed && view === "kalender") { await reload(); EXT.views.kalender(); }
  }
  window.kalAboDialog = aboDialog;
  console.log("INIT UI m29b_kalender_abo v1.0.0");
})();
