// PA Rechnung v2.4.2 - UI-Modul m92_pin: PIN-Sperre
// Knopf "Sperren" in der Seitenleiste, Strg+L, automatische Sperre nach Leerlauf,
// Einstellungen -> PIN & Sperre (PIN aendern, Leerlauf-Zeit).
// Jede Antwort "gesperrt" (401 + X-PA-Locked) laedt die Sperrseite.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m92 = '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>';

  // ---------------------------------------------------------------- server says "locked" -> lock page
  const _fetch = window.fetch.bind(window);
  let reloading = false;
  window.fetch = async function(...a){
    const r = await _fetch(...a);
    if (r.status === 401 && r.headers.get("X-PA-Locked") && !reloading) { reloading = true; location.replace("/"); }
    return r;
  };

  async function lockNow(){
    try { await _fetch("/api/m92/lock", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}); } catch (e) {}
    reloading = true; location.replace("/");
  }
  window.m92Lock = lockNow;

  // ---------------------------------------------------------------- Strg+L
  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.key === "l" || e.key === "L")) { e.preventDefault(); lockNow(); }
  }, true);

  // ---------------------------------------------------------------- lock button in the top right corner of the sidebar
  if (!document.getElementById("m92css")) { const st = document.createElement("style"); st.id = "m92css";
    st.textContent = "#side{position:relative}#m92lockbtn{position:absolute;top:12px;right:10px;z-index:2;border:0;background:var(--side2);color:var(--sideink);width:26px;height:26px;border-radius:7px;cursor:pointer;display:flex;align-items:center;justify-content:center}" +
      "#m92lockbtn:hover{background:var(--acc);color:#fff}#m92lockbtn svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}";
    document.head.appendChild(st); }
  function addBtn(){
    const f = document.getElementById("side");
    if (!f || f.querySelector("#m92lockbtn")) return;
    const b = document.createElement("button");
    b.id = "m92lockbtn"; b.type = "button"; b.title = "Programm sperren (Strg+L)";
    b.innerHTML = ic("m92");
    b.onclick = e => { e.stopPropagation(); lockNow(); };
    f.appendChild(b);
  }
  const side = document.getElementById("side");
  if (side) new MutationObserver(addBtn).observe(side, {childList: true, subtree: true});
  setTimeout(addBtn, 300);

  // ---------------------------------------------------------------- idle auto-lock
  let last = Date.now();
  ["mousemove", "mousedown", "keydown", "wheel", "touchstart"].forEach(ev => document.addEventListener(ev, () => { last = Date.now(); }, {passive: true, capture: true}));
  setInterval(() => {
    const m = Number((S && S.m92 && S.m92.autolock) || 0);
    if (m > 0 && Date.now() - last > m * 60000) lockNow();
  }, 15000);

  // ---------------------------------------------------------------- settings tab
  function render(el){
    const d = (S && S.m92) || {};
    el.innerHTML = `<div class="card"><div class="hd"><h3>${ic("m92")} PIN &amp; Sperre</h3></div><div class="bd fr">
      <div class="small muted">Das Programm lässt sich nur mit deiner 6-stelligen PIN öffnen. Es gibt keinen anderen Zugang und kein „PIN vergessen“.
        ${d.gesetzt ? `PIN festgelegt am ${esc(dde(String(d.gesetzt).slice(0,10)))}${d.geaendert && d.geaendert !== d.gesetzt ? `, zuletzt geändert am ${esc(dde(String(d.geaendert).slice(0,10)))}` : ""}.` : ""}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
        <label class="f">Automatisch sperren nach
          <select class="in" id="m92al" style="width:auto">${[0,5,10,15,30,60,120].map(v => `<option value="${v}" ${Number(d.autolock||0)===v?"selected":""}>${v ? v + " min ohne Bedienung" : "nie"}</option>`).join("")}</select></label>
        <button class="btn" type="button" id="m92sv">Speichern</button>
        <button class="btn" type="button" id="m92now">${ic("m92")} Jetzt sperren (Strg+L)</button>
      </div>
      <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="m92lan" ${d.lan_offen ? "checked" : ""}> Handy-Upload, Abnahme-Link und Handy-App auch bei gesperrtem Programm erlauben (z. B. damit die Stoppuhr am Handy weiterläuft)</label>
      <div class="small muted">Aus (Standard): Ist das Programm gesperrt, antworten Handy und Schnittstelle „gesperrt“, bis die PIN wieder eingegeben ist.</div></div></div>
      <div class="card" style="margin-top:12px"><div class="hd"><h3>PIN ändern</h3></div><div class="bd fr">
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <label class="f">Bisherige PIN<input class="in num" id="m92a" type="password" inputmode="numeric" maxlength="6" autocomplete="off" style="width:130px"></label>
          <label class="f">Neue PIN<input class="in num" id="m92n" type="password" inputmode="numeric" maxlength="6" autocomplete="off" style="width:130px"></label>
          <label class="f">Neue PIN wiederholen<input class="in num" id="m92n2" type="password" inputmode="numeric" maxlength="6" autocomplete="off" style="width:130px"></label>
        </div>
        <div><button class="btn pri" type="button" id="m92ch">PIN ändern</button></div>
        <div class="small muted">Genau 6 Ziffern; nicht erlaubt: lauter gleiche Ziffern oder fortlaufende Folgen (123456, 654321 …).</div>
      </div></div>`;
    $$("#m92a,#m92n,#m92n2", el).forEach(i => i.addEventListener("input", () => { i.value = i.value.replace(/\D/g, "").slice(0, 6); }));
    $("#m92sv", el).onclick = async () => {
      const r = await api("/api/m92/settings", {autolock: Number($("#m92al", el).value), lan_offen: $("#m92lan", el).checked});
      if (r && r.ok) { S.m92 = Object.assign(S.m92 || {}, {autolock: r.autolock, lan_offen: r.lan_offen}); toast(r.autolock ? `Sperre nach ${r.autolock} min Leerlauf` : "Automatische Sperre aus"); }
    };
    $("#m92now", el).onclick = lockNow;
    $("#m92ch", el).onclick = async () => {
      const r = await api("/api/m92/change", {alt: $("#m92a", el).value, neu: $("#m92n", el).value, neu2: $("#m92n2", el).value});
      if (r && r.ok) { toast("PIN geändert"); S.m92 = Object.assign(S.m92 || {}, {geaendert: todayIso()}); render(el); }
    };
  }
  EXT.settings.push({key: "m92pin", label: "PIN & Sperre", render});
})();
