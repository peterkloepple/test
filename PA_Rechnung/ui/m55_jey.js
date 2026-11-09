// Pfeiffer-Audio Rechnung v2.0.0 - UI-Modul m55_jey: "Frag Dr. Jey"
// Fragen in Alltagssprache (Strg+J, Seitenleiste, Dashboard). Zahlen kommen nur aus dem Programm.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m55 = IC.m55 || '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M9.5 9.5a2.5 2.5 0 0 1 4.9.7c0 1.7-2.4 2-2.4 3.3M12 16.5v.01"/>';
  const HIST = [];

  EXT.nav.push({key:"jey", label:"Frag Dr. Jey", icon:"m55", section:"Finanzen", cnt:() => "Strg+J"});

  function closeModal(node){ const mb = node && node.closest(".mb"); if (mb) { const b = mb.querySelector(".mf .btn"); if (b) b.click(); } }

  function follow(l, node){
    closeModal(node);
    if (l.view === "stat" && l.year) { try { stYear = l.year; stTab = "ueb"; } catch (e) {} }
    if (l.view === "tax" && l.year) { try { txYear = l.year; } catch (e) {} }
    go(l.view, l.arg);
  }

  function answerHtml(r){
    if (!r) return "";
    const z = r.zahlen || [], li = r.liste || [], ln = r.links || [];
    return `<div class="m55a" style="margin-top:12px">
      ${r.frage ? `<div class="small muted" style="margin-bottom:4px">„${esc(r.frage)}“</div>` : ""}
      <div style="font-size:14.5px;line-height:1.45;margin-bottom:8px">${esc(r.antwort || "")}</div>
      ${z.length ? `<div class="kv" style="margin-bottom:8px">${z.map(x => `<span class="sub">${esc(x.label)}</span><span class="r"><b>${esc(x.wert)}</b></span>`).join("")}</div>` : ""}
      ${li.length ? `<div class="list" style="margin-bottom:8px">${li.map((x, i) => `<div class="row small" style="padding:4px 0;border-top:1px solid var(--line);align-items:center;${x.inv || x.kunde ? "cursor:pointer" : ""}" data-m55li="${i}">
          <span style="flex:1">${esc(x.label)}</span>${x.wert ? `<b class="num" style="flex:none">${esc(x.wert)}</b>` : ""}</div>`).join("")}</div>` : ""}
      ${(r.beispiele || []).length ? `<div class="chips" style="margin:6px 0">${r.beispiele.map(b => `<span class="chip" data-m55ex="${esc(b)}">${esc(b)}</span>`).join("")}</div>` : ""}
      ${ln.length ? `<div class="row" style="gap:6px;flex-wrap:wrap;margin-top:6px">${ln.map((l, i) => `<button class="btn sm" type="button" data-m55ln="${i}" style="flex:none">${ic("open")} ${esc(l.label)}</button>`).join("")}</div>` : ""}
      <div class="small muted" style="margin-top:8px">Quelle: ${esc(r.quelle || "Regeln")}${r.model ? " · Modell " + esc(r.model) : ""}${r.hinweis ? " · " + esc(r.hinweis) : ""}</div>
    </div>`;
  }

  function bindAnswer(box, r, ask){
    $$("[data-m55ln]", box).forEach(b => b.onclick = () => follow(r.links[+b.dataset.m55ln], b));
    $$("[data-m55li]", box).forEach(b => b.onclick = () => { const x = r.liste[+b.dataset.m55li];
      if (x.inv) { closeModal(b); openInvoice(x.inv); } else if (x.kunde) follow({view:"users", arg:x.kunde}, b); });
    $$("[data-m55ex]", box).forEach(c => c.onclick = () => ask(c.dataset.m55ex));
  }

  async function askApi(q){
    const r = await api("/api/m55/frage", {frage:q});
    if (r && r.ok !== false) { HIST.unshift(r); HIST.splice(12); }
    return r;
  }

  function openJey(pre){
    if ($("#m55q")) { $("#m55q").focus(); return; }
    modal("Frag Dr. Jey", `<div class="nokeep">
      <div class="row" style="gap:8px"><input class="in" id="m55q" placeholder="z. B. Wie viel Umsatz hatte ich letztes Jahr mit Kunde X?" autocomplete="off">
        <button class="btn pri" id="m55go" type="button" style="flex:none">Fragen</button></div>
      <div id="m55out"><div class="small muted" style="margin-top:10px">Ich rechne nur mit deinen echten Daten. Beispiele:</div>
        <div class="chips" style="margin-top:6px">${["Wie viel Umsatz hatte ich dieses Jahr?", "Welche Rechnungen sind noch offen?", "Wer sind meine größten Kunden?",
          "Wie hoch sind meine Fixkosten?", "Muss ich Steuern nachzahlen?", "Reicht das Geld die nächsten Monate?"].map(b => `<span class="chip" data-m55ex="${esc(b)}">${esc(b)}</span>`).join("")}</div></div></div>`,
      [{label:"Schließen"}], true, mb => {
        const inp = $("#m55q", mb), out = $("#m55out", mb);
        const ask = async q => { q = (q || "").trim(); if (!q) return; inp.value = q; out.innerHTML = `<div class="small muted" style="margin-top:10px">Dr. Jey rechnet …</div>`;
          const r = await askApi(q); out.innerHTML = answerHtml(r); bindAnswer(out, r, ask); inp.select(); };
        $("#m55go", mb).onclick = () => ask(inp.value);
        inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); ask(inp.value); } };
        $$("[data-m55ex]", out).forEach(c => c.onclick = () => ask(c.dataset.m55ex));
        setTimeout(() => inp.focus(), 50);
        if (pre) ask(pre);
      });
  }
  window.openJey = openJey;

  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "j") { e.preventDefault(); openJey(); }
  }, true);

  EXT.dash.push(el => {
    const d = document.createElement("div"); d.className = "card nokeep"; d.style.marginBottom = "16px";
    d.innerHTML = `<div class="bd" style="display:flex;gap:10px;align-items:center;padding:10px 14px">
      <span style="flex:none;display:flex;color:var(--acc)">${ic("m55")}</span><b style="flex:none">Frag Dr. Jey</b>
      <input class="in" id="m55dq" placeholder="z. B. Was habe ich 2025 für Software ausgegeben?  (Strg+J)" autocomplete="off">
      <button class="btn pri" id="m55dg" type="button" style="flex:none">Fragen</button></div>`;
    el.insertBefore(d, el.firstChild);
    const run = () => { const v = $("#m55dq", d).value.trim(); $("#m55dq", d).value = ""; openJey(v || undefined); };
    $("#m55dg", d).onclick = run;
    $("#m55dq", d).onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); run(); } };
  });

  EXT.views.jey = async function(){
    const info = await api("/api/m55/info", undefined, {quiet:true}) || {};
    $("#main").innerHTML = `<div class="page">${pageHead("Frag Dr. Jey", "Fragen zu Umsatz, Kunden, Ausgaben, Steuer und Kontostand – beantwortet mit deinen echten Zahlen")}
      <div class="card nokeep" style="margin-bottom:16px"><div class="bd">
        <div class="row" style="gap:8px"><input class="in" id="m55pq" placeholder="Frage eingeben …" autocomplete="off"><button class="btn pri" id="m55pg" type="button" style="flex:none">Fragen</button></div>
        <div class="chips" style="margin-top:10px">${(info.beispiele || []).map(b => `<span class="chip" data-m55ex="${esc(b)}">${esc(b)}</span>`).join("")}</div>
        <div class="small muted" style="margin-top:10px">${info.ki ? "Lokale KI ist aktiv: sie hilft beim Verstehen der Frage und beim Formulieren – die Zahlen rechnet immer das Programm, KI-Sätze mit fremden Zahlen werden verworfen."
          : "Regelbasiert (lokale KI aus). Mit aktivierter lokaler KI (Einstellungen → Assistent / KI) versteht Dr. Jey auch freier formulierte Fragen."}</div>
      </div></div>
      <div id="m55hist">${HIST.map(r => `<div class="card" style="margin-bottom:12px"><div class="bd">${answerHtml(r)}</div></div>`).join("")}</div></div>`;
    const ask = async q => { q = (q || "").trim(); if (!q) return; $("#m55pq").value = ""; await askApi(q); EXT.views.jey(); };
    $("#m55pg").onclick = () => ask($("#m55pq").value);
    $("#m55pq").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); ask($("#m55pq").value); } };
    $$("#main .card.nokeep [data-m55ex]").forEach(c => c.onclick = () => ask(c.dataset.m55ex));
    $$("#m55hist .card").forEach((c, i) => bindAnswer(c, HIST[i], ask));
    bindCommon();
    setTimeout(() => { const i = $("#m55pq"); if (i) i.focus(); }, 30);
  };
})();
