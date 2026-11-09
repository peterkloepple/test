// PA Rechnung v2.0.7 - Unterricht: Dateiablage je Kurs, je Schueler/in und allgemeines Material
// Reiter "Dateien" im Unterricht, Knopf "Dateien" auf Kurskarten und in der Schuelerliste,
// Dateien hineinziehen / waehlen, Datum (Stunde) + Notiz, auf anderes Ziel ziehen = verschieben.
// Autor: T. Pfeiffer
(function(){
  let untSel = (() => { try { return JSON.parse(localStorage.getItem("pa_untsel") || "null") || {ziel:"allg", id:0}; } catch (e) { return {ziel:"allg", id:0}; } })();
  let untQ = "", untArt = "";
  const saveSel = () => { try { localStorage.setItem("pa_untsel", JSON.stringify(untSel)); } catch (e) {} };
  const fsz = b => b >= 1048576 ? nde(b / 1048576, 1) + " MB" : nde(Math.max(1, Math.round((b || 0) / 1024)), 0) + " KB";
  const ART_IC = {"Noten & Arbeitsblätter":"📄", "Aufnahme (Audio)":"🎵", "Video":"🎬", "Foto":"🖼", "Dokument":"📝", "Projekt-/Session-Datei":"🎛", "Sonstiges":"📎"};

  // jump from course card / student list
  window.untOpenFiles = (ziel, id) => { untSel = {ziel, id:+id || 0}; saveSel(); schTab = "dat"; if (view === "school") vSchool(); else go("school"); };

  window.untFilesRender = async function(host){
    const ov = await api("/api/unt/overview");
    const cnt = (z, i) => (ov.counts || {})[z + ":" + i] || 0;
    if (untSel.ziel === "kurs" && !S.kurse.some(k => k.id === untSel.id) && !(ov.orphans||[]).some(o => o.ziel === "kurs" && o.ziel_id === untSel.id)) untSel = {ziel:"allg", id:0};
    if (untSel.ziel === "schueler" && !S.students.some(s => s.id === untSel.id) && !(ov.orphans||[]).some(o => o.ziel === "schueler" && o.ziel_id === untSel.id)) untSel = {ziel:"allg", id:0};
    const d = await api(`/api/unt/files?ziel=${untSel.ziel}&id=${untSel.id}`);
    const node = (z, i, label, sub) => `<div class="untn ${untSel.ziel===z && untSel.id===i ? "on" : ""}" data-uz="${z}" data-ui="${i}"><span class="untl">${label}</span>${sub?`<span class="small muted untsub">${sub}</span>`:""}<span class="cnt">${cnt(z, i)}</span></div>`;
    const kurse = S.kurse.slice().sort((a,b) => (b.aktiv - a.aktiv) || a.name.localeCompare(b.name));
    const studs = S.students.slice().sort((a,b) => (b.aktiv - a.aktiv) || a.name.localeCompare(b.name));
    const orph = ov.orphans || [];
    const ql = untQ.toLowerCase();
    const list = (d.dateien || []).filter(f => (!untArt || f.art === untArt) && (!ql || (f.name + " " + (f.notiz||"") + " " + f.art).toLowerCase().includes(ql)));
    host.innerHTML = `<div class="untwrap">
      <div class="card untside"><div class="untgrp">Material</div>${node("allg", 0, "Allgemeines Material", "für alle")}
        <div class="untgrp">Kurse</div>${kurse.map(k => node("kurs", k.id, esc(k.name), k.aktiv ? "" : "inaktiv")).join("") || `<div class="small muted" style="padding:4px 10px">noch keine Kurse</div>`}
        <div class="untgrp">Schüler/innen</div>${studs.map(s => node("schueler", s.id, esc(s.name), s.aktiv ? "" : "inaktiv")).join("") || `<div class="small muted" style="padding:4px 10px">noch keine Schüler</div>`}
        ${orph.length ? `<div class="untgrp">Ohne Zuordnung</div>${orph.map(o => node(o.ziel, o.ziel_id, (o.ziel==="kurs"?"Kurs ":"Schüler ") + o.ziel_id + " (gelöscht)", "")).join("")}` : ""}
        <div class="small muted" style="padding:10px">Datei auf einen Eintrag ziehen = dorthin verschieben</div></div>
      <div>
        <div class="card" style="margin-bottom:12px"><div class="hd"><h3>${esc(d.titel)}</h3><div class="act">
          <button class="btn sm" id="untdir" title="Ordner im Explorer öffnen">${ic("folder")} Ordner</button>
          <button class="btn sm" id="untsync" title="Dateien übernehmen, die im Explorer in den Ordner gelegt wurden">Ordner abgleichen</button>
          <button class="btn sm pri" id="untadd">${ic("plus")} Dateien</button></div></div>
          <div class="bd"><div class="dz" id="untdz" style="padding:16px">Dateien hierher ziehen – Noten, Aufnahmen, Arbeitsblätter, Fotos, Verträge …
            <div class="row" style="margin-top:10px;justify-content:center;gap:10px;align-items:center"><label class="small" style="flex:none">Datum / Stunde <input class="in" type="date" id="untdat" style="width:150px;display:inline-block;margin-left:6px" value=""></label>
            <label class="small" style="flex:1;max-width:360px">Notiz <input class="in" id="untnot" style="display:inline-block;width:250px;margin-left:6px" placeholder="optional, gilt für die nächsten Dateien"></label></div></div>
            ${d.ordner ? `<div class="small muted" style="margin-top:6px">Ablage: Datenordner › ${esc(d.ordner)}</div>` : ""}</div></div>
        <div class="row" style="margin-bottom:10px;align-items:center;flex-wrap:wrap;gap:6px">
          <div class="search" style="flex:1;min-width:200px"><svg viewBox="0 0 24 24">${IC.search}</svg><input class="in" id="untq" placeholder="Dateien suchen …" value="${esc(untQ)}"></div>
          <div class="chips" style="flex:none"><span class="chip ${untArt?"":"on"}" data-uart="">Alle <b>${(d.dateien||[]).length}</b></span>${(d.arten||[]).filter(a => (d.dateien||[]).some(f=>f.art===a)).map(a => `<span class="chip ${untArt===a?"on":""}" data-uart="${esc(a)}">${ART_IC[a]||""} ${esc(a)} <b>${(d.dateien||[]).filter(f=>f.art===a).length}</b></span>`).join("")}</div></div>
        <div class="card" style="overflow:hidden"><table class="t" id="untt"><thead><tr><th>Datei</th><th>Art</th><th>Datum</th><th class="r">Größe</th><th>Notiz</th><th></th></tr></thead><tbody>
          ${list.map(f => `<tr class="click" data-uf="${f.id}" draggable="true" style="${f.fehlt?"opacity:.55":""}"><td><b>${ART_IC[f.art]||"📎"} ${esc(f.name)}</b>${f.fehlt?` <span class="badge bad">fehlt im Ordner</span>`:""}</td>
            <td class="small">${esc(f.art)}</td><td class="num small">${f.datum?dde(f.datum):`<span class="muted">${dde((f.added||"").slice(0,10))}</span>`}</td><td class="r num small">${fsz(f.size)}</td>
            <td class="small muted">${esc(f.notiz||"")}</td>
            <td class="r" style="white-space:nowrap" onclick="event.stopPropagation()"><button class="btn sm" data-uo="${f.id}">Öffnen</button><button class="btn sm ghost" data-ud="${f.id}" title="Im Ordner zeigen">${ic("folder")}</button><button class="btn sm ghost" data-ux="${f.id}" title="Löschen (Datei kommt in den Papierkorb im Datenordner)" style="color:var(--bad)">✕</button></td></tr>`).join("")
          || `<tr><td colspan="6" class="empty">${(d.dateien||[]).length ? "Keine Dateien für diesen Filter." : "Noch keine Dateien – oben hineinziehen oder „+ Dateien“."}</td></tr>`}</tbody></table></div>
      </div></div>`;

    const up = async files => {
      if (!files.length) return;
      const dat = $("#untdat", host).value, nt = $("#untnot", host).value;
      toast(files.length + " Datei(en) werden abgelegt …");
      let n = 0;
      for (const f of files) { const r = await upload("/api/upload/unt", f, {"X-Ziel": untSel.ziel, "X-Id": String(untSel.id), "X-Datum": dat, "X-Notiz": encodeURIComponent(nt)}); if (r && r.ok) n++; }
      toast(n + " Datei(en) bei „" + d.titel + "“ abgelegt"); await reload(); untFilesRender(host);
    };
    $$("[data-uz]", host).forEach(n => {
      n.onclick = () => { untSel = {ziel:n.dataset.uz, id:+n.dataset.ui}; untArt = ""; saveSel(); untFilesRender(host); };
      n.ondragover = e => { e.preventDefault(); n.classList.add("dragover"); };
      n.ondragleave = () => n.classList.remove("dragover");
      n.ondrop = async e => { e.preventDefault(); n.classList.remove("dragover");
        const fid = e.dataTransfer.getData("text/untfile");
        if (fid) { const ids = (SEL.unt && SEL.unt.set.size && SEL.unt.set.has(fid)) ? [...SEL.unt.set] : [fid];
          for (const i of ids) await api("/api/unt/file/update", {id:+i, ziel:n.dataset.uz, ziel_id:+n.dataset.ui});
          toast(ids.length + " Datei(en) verschoben"); selClear(); await reload(); untFilesRender(host); }
        else if (e.dataTransfer.files.length) { untSel = {ziel:n.dataset.uz, id:+n.dataset.ui}; saveSel(); await up([...e.dataTransfer.files]); } };
    });
    const dz = $("#untdz", host);
    dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
    dz.ondragleave = () => dz.classList.remove("over");
    dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); up([...e.dataTransfer.files]); };
    $("#untadd", host).onclick = () => pickFiles("", fs => up(fs));
    $("#untdir", host).onclick = () => api("/api/unt/open", {ziel:untSel.ziel, ziel_id:untSel.id});
    $("#untsync", host).onclick = async () => { const r = await api("/api/unt/sync", {ziel:untSel.ziel, ziel_id:untSel.id});
      if (r.ok) { toast(`${r.neu} neue Datei(en) übernommen${r.fehlen?` · ${r.fehlen} fehlen im Ordner`:""}`); await reload(); untFilesRender(host); } };
    $("#untq", host).oninput = e => { untQ = e.target.value; clearTimeout(window._untT); window._untT = setTimeout(() => { if (!$("#untq")) return; const p = e.target.selectionStart; untFilesRender(host).then(() => { const n = $("#untq"); if (n) { n.focus(); try { n.setSelectionRange(p, p); } catch (e2) {} } }); }, 180); };
    $$("[data-uart]", host).forEach(c => c.onclick = () => { untArt = c.dataset.uart; untFilesRender(host); });
    $$("[data-uo]", host).forEach(b => b.onclick = () => api("/api/unt/open", {id:+b.dataset.uo}));
    $$("[data-ud]", host).forEach(b => b.onclick = () => api("/api/unt/open", {id:+b.dataset.ud, ordner:true}));
    $$("[data-ux]", host).forEach(b => b.onclick = async () => { if (!await ask("Datei löschen? Sie kommt in den Papierkorb im Datenordner.")) return;
      await api("/api/unt/file/delete", {ids:[+b.dataset.ux]}); toast("Gelöscht (Papierkorb im Datenordner)"); await reload(); untFilesRender(host); });
    $$("tr[data-uf]", host).forEach(r => { r.ondragstart = e => e.dataTransfer.setData("text/untfile", r.dataset.uf);
      r.onclick = () => untEdit((d.dateien||[]).find(f => f.id == r.dataset.uf), d, host); });
    selectify({kind:"unt", rows:"#untt tr[data-uf]", id:"data-uf", root:host, rerender:() => untFilesRender(host), actions:[
      {label:"Öffnen", run: async ids => { for (const i of ids.slice(0, 10)) await api("/api/unt/open", {id:+i}); return false; }},
      {label:"Löschen", cls:"danger", run: async ids => { if (!await ask(ids.length + " Datei(en) löschen? Sie kommen in den Papierkorb im Datenordner.")) return false;
        await api("/api/unt/file/delete", {ids:ids.map(Number)}); await reload(); untFilesRender(host); }}]});
  };

  async function untEdit(f, d, host){
    if (!f) return;
    const th = /\.(jpe?g|png|webp|gif|bmp|tiff?|pdf)$/i.test(f.name);
    const opts = [["allg", 0, "Allgemeines Material"], ...S.kurse.map(k => ["kurs", k.id, "Kurs: " + k.name]), ...S.students.map(s => ["schueler", s.id, "Schüler: " + s.name])];
    await modal(f.name, `<div class="grid" style="grid-template-columns:${th?"240px ":""}1fr">
      ${th?`<img src="/api/thumb?path=${encodeURIComponent(f.path)}" style="width:100%;border:1px solid var(--line);border-radius:10px">`:""}
      <div class="fr"><label class="f">Dateiname<input class="in" id="ufn" value="${esc(f.name)}"></label>
        <div class="row"><label class="f">Art<select class="in" id="ufa">${(d.arten||[]).map(a=>`<option ${f.art===a?"selected":""}>${esc(a)}</option>`).join("")}</select></label>
        <label class="f">Datum / Stunde<input class="in" type="date" id="ufd" value="${esc(f.datum||"")}"></label></div>
        <label class="f">Gehört zu<select class="in" id="ufz">${opts.map(([z,i,l])=>`<option value="${z}|${i}" ${f.ziel===z && f.ziel_id===i?"selected":""}>${esc(l)}</option>`).join("")}</select></label>
        <label class="f">Notiz<textarea class="in" id="ufno">${esc(f.notiz||"")}</textarea></label>
        <div class="small muted">${fsz(f.size)} · abgelegt ${dde((f.added||"").slice(0,10))} · Datenordner › ${esc(f.path)}</div></div></div>`,
      [{label:"Löschen", cls:"danger", onClick: async () => { const r = await api("/api/unt/file/delete", {ids:[f.id]}); if (!r || r.ok === false) return false; toast("Gelöscht (Papierkorb im Datenordner)"); await reload(); untFilesRender(host); }},
       {label:"Im Ordner zeigen", onClick: async () => { await api("/api/unt/open", {id:f.id, ordner:true}); return false; }},
       {label:"Öffnen", onClick: async () => { await api("/api/unt/open", {id:f.id}); return false; }},
       {label:"Speichern", cls:"pri", onClick: async mb => { const [z, i] = $("#ufz", mb).value.split("|");
         const r = await api("/api/unt/file/update", {id:f.id, name:$("#ufn",mb).value, art:$("#ufa",mb).value, datum:$("#ufd",mb).value, notiz:$("#ufno",mb).value, ziel:z, ziel_id:+i});
         if (r.ok === false) return false; await reload(); untFilesRender(host); }}], true);
  }

  // "Dateien" buttons on course cards and in the student list
  EXT.after.push(n => {
    if (n !== "vSchool") return;
    const c = S.unt_counts || {};
    $$("#main [data-addm]").forEach(b => { const kid = b.dataset.addm; if (b.parentNode.querySelector("[data-ukf]") || !b.closest(".pcard")) return;
      const x_ = document.createElement("button"); x_.className = "btn sm"; x_.dataset.ukf = kid;
      Object.assign(b.parentNode.style, {display:"flex", flexWrap:"wrap", gap:"6px"});
      x_.innerHTML = `${ic("folder")} Dateien${c["kurs:"+kid] ? " (" + c["kurs:"+kid] + ")" : ""}`; x_.onclick = () => untOpenFiles("kurs", kid); b.after(x_); });
    const tb = $("#main table.t"); if (tb && schTab === "st" && !tb.dataset.unt) { tb.dataset.unt = "1";
      const hr = tb.tHead && tb.tHead.rows[0]; if (hr) { const th = document.createElement("th"); th.textContent = "Dateien"; hr.appendChild(th); }
      $$("tr[data-es]", tb).forEach(r => { const td = document.createElement("td"); const sid = r.dataset.es, k = c["schueler:"+sid] || 0;
        td.innerHTML = `<button class="btn sm ghost">${ic("folder")} ${k || ""}</button>`; td.onclick = e => { e.stopPropagation(); untOpenFiles("schueler", sid); }; r.appendChild(td); }); }
  });

  const css = document.createElement("style");
  css.textContent = `.untwrap{display:grid;grid-template-columns:270px 1fr;gap:16px;align-items:start}
    .untside{padding:6px 0;max-height:calc(100vh - 230px);overflow:auto;position:sticky;top:0}
    .untgrp{font:600 11px var(--disp);text-transform:uppercase;letter-spacing:.06em;color:var(--mute);padding:10px 12px 4px}
    .untn{display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;border-left:3px solid transparent}
    .untn:hover{background:var(--panel2)} .untn.on{background:var(--accsoft);border-left-color:var(--acc)}
    .untn.dragover{outline:2px dashed var(--acc);outline-offset:-3px}
    .untl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap} .untsub{flex:none}
    .untn .cnt{flex:none;font-size:11px;color:var(--mute)}
    @media (max-width:1100px){.untwrap{grid-template-columns:1fr}.untside{position:static;max-height:260px}}`;
  document.head.appendChild(css);
})();
