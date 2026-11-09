// PA Rechnung v2.4.9 - UI-Modul m99d_stimme: Stimme als zweiter Schluessel nach der PIN
// Karte "Stimme" im Einstellungs-Reiter "PIN & Sperre": 10x einsprechen (einzeln oder "alle nacheinander" mit
// Ansage und Signaltoenen), testen, einschalten (mit PIN), Notfall-Code, Strenge, Ansage/Toene, ausschalten.
// Der Satz ist geheim: verdeckt angezeigt, beim Entsperren wird er nicht gezeigt.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  IC.m99d = '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>';
  const when = t => t ? dde(String(t).slice(0,10)) + " " + String(t).slice(11,16) : "";
  const STR = {locker: "locker (erkennt dich leichter, z. B. bei Erkältung)", normal: "normal", streng: "streng (lässt weniger durch)"};
  let AC = null, ST = {ansage: true, toene: true}, guided = false;

  // ---------- acoustic guidance (same tones as on the lock page)
  function tone(seq){
    if (!ST.toene) return Promise.resolve();
    try {
      AC = AC || new (window.AudioContext || window.webkitAudioContext)();
      let t = AC.currentTime + 0.02, end = t;
      for (const [f, d] of seq) {
        const o = AC.createOscillator(), g = AC.createGain();
        o.type = "sine"; o.frequency.value = f; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.015);
        g.gain.exponentialRampToValueAtTime(0.0001, t + d); o.connect(g); g.connect(AC.destination); o.start(t); o.stop(t + d + 0.02); t += d + 0.04; end = t;
      }
      return new Promise(res => setTimeout(res, (end - AC.currentTime) * 1000 + 60));
    } catch (e) { return Promise.resolve(); }
  }
  function say(text){
    if (!ST.ansage || !window.speechSynthesis) return Promise.resolve();
    return new Promise(res => {
      try {
        const u = new SpeechSynthesisUtterance(text); u.lang = "de-DE"; u.rate = 1.05;
        const de = speechSynthesis.getVoices().find(v => /^de/i.test(v.lang)); if (de) u.voice = de;
        u.onend = () => setTimeout(res, 150); u.onerror = () => res(); speechSynthesis.cancel(); speechSynthesis.speak(u);
        setTimeout(res, 5000);
      } catch (e) { res(); }
    });
  }
  const T_START = [[880, 0.12]], T_OK = [[660, 0.1], [990, 0.16]], T_NO = [[300, 0.18], [220, 0.28]];

  // one recording: tone -> server records -> result tone
  async function rec(btn, url, body, sek){
    const lbl = btn ? btn.innerHTML : ""; if (btn) { btn.disabled = true; btn.classList.add("pri"); btn.textContent = "Achtung …"; }
    await tone(T_START);
    let left = Math.ceil(sek || 4); if (btn) btn.textContent = `Sprich jetzt … ${left}`;
    const t = setInterval(() => { left--; if (btn) btn.textContent = left > 0 ? `Sprich jetzt … ${left}` : "werte aus …"; }, 1000);
    const r = await api(url, body, {quiet: true}) || {ok: false, error: "keine Antwort"};
    clearInterval(t); if (btn) { btn.disabled = false; btn.classList.remove("pri"); btn.innerHTML = lbl; }
    await tone(r.ok && r.erkannt !== false ? T_OK : T_NO);
    return r;
  }

  function codeBox(code){
    return modal("Dein Notfall-Code", `<div class="fr"><div class="small">Mit diesem Code kommst du ins Programm, wenn deine Stimme einmal nicht erkannt wird (Erkältung, Mikrofon kaputt, Lärm). Er wird <b>nur jetzt</b> angezeigt – bitte aufschreiben und gut aufheben (nicht am PC).</div>
      <div style="font:700 28px/1.2 Consolas,monospace;letter-spacing:3px;text-align:center;padding:14px;border:2px dashed var(--acc);border-radius:12px;user-select:all">${esc(code)}</div>
      <div class="small muted">Nach der PIN auf „Stimme klappt nicht? Notfall-Code eingeben“ klicken.</div></div>`, [{label: "Ich habe ihn aufgeschrieben", cls: "pri"}]);
  }

  async function card(host){
    const s = await api("/api/m99d/status", undefined, {quiet: true}); if (!s || !host.isConnected) return;
    ST = {ansage: s.ansage, toene: s.toene};
    const N = s.n || 10, have = s.aufnahmen || [], done = have.length >= N;
    const lz = s.letzte || {};
    const recBtns = Array.from({length: N}, (_, i) => i + 1).map(n => `<button class="btn sm ${have.includes(n) ? "" : "ghost"}" type="button" data-vrec="${n}" style="flex:none;min-width:46px" title="Aufnahme ${n}">${have.includes(n) ? ic("check") : ""}${n}</button>`).join("");
    host.innerHTML = `<div class="card" style="margin-top:12px"><div class="hd"><h3>${ic("m99d")} Stimme (zusätzlich zur PIN)</h3>
        <div class="act">${s.aktiv ? `<span class="badge ok"><span class="dot"></span>eingeschaltet</span>` : `<span class="badge">aus</span>`}</div></div>
      <div class="bd fr">
        <div class="small">Nach der richtigen PIN sprichst du deinen geheimen Satz ins Mikrofon – er wird dabei <b>nicht</b> angezeigt. Das Programm prüft Wortlaut und Sprechweise <b>und</b> den Klang deiner Stimme; das Raumgeräusch wird herausgerechnet. Gespeichert werden keine Tonaufnahmen, nur Merkmale – verschlüsselt mit deiner PIN.</div>
        ${s.alt ? `<div class="alert warn small" style="margin:0">Dein Stimmprofil stammt noch aus der alten Version (3 Aufnahmen). Bitte <b>10 neue Aufnahmen</b> machen und mit PIN „Neu einlernen“ – dann greift die bessere Erkennung.</div>` : ""}
        ${!s.windows ? `<div class="alert warn small" style="margin:0">Die Sprachprüfung gibt es nur unter Windows.</div>` : ""}
        <label class="f">Dein geheimer Satz (2–4 Sekunden, immer gleich sprechen)
          <div class="row" style="gap:6px"><input class="in" id="vsatz" type="password" value="${esc(s.satz)}" maxlength="80" autocomplete="off"><button class="btn sm ghost" type="button" id="vshow" style="flex:none">zeigen</button></div></label>
        <div class="small muted">Wähle etwas, das nicht jeder sagt. Er steht nur hier (verschlüsselt) und wird beim Entsperren nie angezeigt.</div>
        <div class="small"><b>${N} Aufnahmen</b> – ruhiger Raum, normaler Abstand zum Mikrofon, so sprechen wie später auch. Nach dem hohen Ton sprechen.</div>
        <div class="row" style="gap:6px;flex-wrap:wrap;align-items:center">${recBtns}
          <span class="small muted" style="flex:none;margin-left:4px">${have.length}/${N}</span></div>
        <div class="row" style="gap:8px;flex-wrap:wrap">
          <button class="btn ${done ? "" : "pri"}" type="button" id="vall" style="flex:none">${ic("m99d")} ${have.length ? "Fehlende nacheinander aufnehmen" : `Alle ${N} nacheinander aufnehmen`}</button>
          ${have.length ? `<button class="btn ghost sm" type="button" id="vclear" style="flex:none">Aufnahmen verwerfen</button>` : ""}</div>
        <div class="row" style="gap:10px;flex-wrap:wrap;align-items:flex-end">
          <label class="f" style="flex:1 1 220px">Strenge<select class="in" id="vstr">${Object.entries(STR).map(([k,l]) => `<option value="${k}" ${s.strenge===k?"selected":""}>${l}</option>`).join("")}</select></label>
          <button class="btn" type="button" id="vtest" style="flex:none" ${(s.aktiv || done) ? "" : "disabled"}>${ic("m99d")} Testen</button></div>
        <div class="row" style="gap:14px;flex-wrap:wrap">
          <label class="chk"><input type="checkbox" id="vans" ${s.ansage ? "checked" : ""}> Sprachansage</label>
          <label class="chk"><input type="checkbox" id="vton" ${s.toene ? "checked" : ""}> Signaltöne (Start, erkannt, nicht erkannt)</label></div>
        <div class="small" id="vres">${lz.zeit ? `Letzte Prüfung beim Entsperren: ${esc(when(lz.zeit))} – ${lz.notfall ? "mit Notfall-Code" : (lz.ok ? `<span style="color:var(--ok)">erkannt</span>` : `<span style="color:var(--bad)">nicht erkannt</span>`) + (lz.score != null ? ` (Wert ${lz.score}; bis 1,0 = erkannt)` : "")}` : ""}</div>
        <div class="row" style="gap:10px;flex-wrap:wrap;align-items:flex-end;border-top:1px solid var(--line);padding-top:10px">
          <label class="f" style="flex:none">PIN zur Bestätigung<input class="in num" id="vpin" type="password" inputmode="numeric" maxlength="6" autocomplete="off" style="width:130px"></label>
          ${s.aktiv
            ? `<button class="btn ${done ? "pri" : ""}" type="button" id="vneu" style="flex:none" ${done ? "" : "disabled"} title="Erst ${N} neue Aufnahmen machen">Neu einlernen</button>
               <button class="btn" type="button" id="vcode" style="flex:none">Neuen Notfall-Code</button>
               <button class="btn danger" type="button" id="vaus" style="flex:none">Stimme ausschalten</button>`
            : `<button class="btn pri" type="button" id="van" style="flex:none" ${done ? "" : "disabled"}>${ic("m99d")} Stimme einschalten</button>`}</div>
        <div class="small muted">Ehrlich gesagt: Eine Stimme ist ein zusätzliches Hindernis, aber kein Tresor – eine gute Aufnahme deiner Stimme kann die Prüfung täuschen. Die PIN bleibt der eigentliche Schutz. Wird deine Stimme nicht erkannt, hilft der Notfall-Code.</div>
      </div></div>`;
    const pin = () => $("#vpin", host).value.replace(/\D/g, "");
    $("#vpin", host).oninput = e => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6); };
    $("#vshow", host).onclick = e => { const i = $("#vsatz", host); i.type = i.type === "password" ? "text" : "password"; e.target.textContent = i.type === "password" ? "zeigen" : "verbergen"; };
    const one = async (n, b) => {
      const r = await rec(b, "/api/m99d/aufnahme", {nr: n}, s.sek);
      if (!r.ok) toast(`Aufnahme ${n}: ${r.error || "fehlgeschlagen"}`, true);
      return r.ok;
    };
    $$("[data-vrec]", host).forEach(b => b.onclick = async () => { if (guided) return; await one(+b.dataset.vrec, b); card(host); });
    $("#vall", host).onclick = async e => {
      if (guided) return; guided = true; e.currentTarget.disabled = true;
      try {
        const miss = Array.from({length: N}, (_, i) => i + 1).filter(n => !have.includes(n));
        await say(`Ich nehme jetzt ${miss.length} mal deinen Satz auf. Sprich jeweils nach dem hohen Ton.`);
        for (const n of miss) {
          if (!host.isConnected) break;
          const b = $(`[data-vrec="${n}"]`, host);
          let ok = await one(n, b);
          if (!ok) { await say("Nochmal bitte."); ok = await one(n, b); }
          if (ok && b) { b.classList.remove("ghost"); b.innerHTML = ic("check") + n; }
          await new Promise(r => setTimeout(r, 600));
        }
        await say("Fertig.");
      } finally { guided = false; card(host); }
    };
    const vc_ = $("#vclear", host); if (vc_) vc_.onclick = async () => { await api("/api/m99d/verwerfen", {}); card(host); };
    $("#vstr", host).onchange = async e => { await api("/api/m99d/einstellen", {strenge: e.target.value}); toast("Strenge gespeichert"); };
    $("#vans", host).onchange = async e => { await api("/api/m99d/einstellen", {ansage: e.target.checked}); ST.ansage = e.target.checked; };
    $("#vton", host).onchange = async e => { await api("/api/m99d/einstellen", {toene: e.target.checked}); ST.toene = e.target.checked; };
    const sz = $("#vsatz", host); if (sz && !s.aktiv) sz.onchange = () => api("/api/m99d/einstellen", {satz: sz.value}, {quiet: true});
    $("#vtest", host).onclick = async e => {
      const r = await rec(e.currentTarget, "/api/m99d/test", {strenge: $("#vstr", host).value}, s.sek);
      $("#vres", host).innerHTML = r.ok ? (r.erkannt ? `<span style="color:var(--ok)"><b>Erkannt</b></span>` : `<span style="color:var(--bad)"><b>Nicht erkannt</b></span>`) + ` – Wert ${String(r.score).replace(".", ",")} (bis 1,0 = erkannt; kleiner = ähnlicher)`
        : `<span style="color:var(--bad)">${esc(r.error || "Fehler")}</span>`;
    };
    const an = $("#van", host); if (an) an.onclick = async () => {
      const r = await api("/api/m99d/aktivieren", {pin: pin(), satz: $("#vsatz", host).value, strenge: $("#vstr", host).value});
      if (r && r.ok) { toast("Stimme eingeschaltet – ab dem nächsten Entsperren wird sie abgefragt"); if (r.notfall_code) await codeBox(r.notfall_code); card(host); }
    };
    const neu = $("#vneu", host); if (neu) neu.onclick = async () => {
      const r = await api("/api/m99d/aktivieren", {pin: pin(), satz: $("#vsatz", host).value, strenge: $("#vstr", host).value});
      if (r && r.ok) { toast("Stimme neu eingelernt"); card(host); }
    };
    const vc = $("#vcode", host); if (vc) vc.onclick = async () => {
      const r = await api("/api/m99d/notfall", {pin: pin()}); if (r && r.ok && r.notfall_code) { await codeBox(r.notfall_code); card(host); }
    };
    const au = $("#vaus", host); if (au) au.onclick = async () => {
      if (!await confirmBox("Stimmprüfung ausschalten? Danach reicht wieder die PIN.", "Ausschalten")) return;
      const r = await api("/api/m99d/aus", {pin: pin()}); if (r && r.ok) { toast("Stimmprüfung aus"); card(host); }
    };
  }

  const ent = (EXT.settings || []).find(e => e.key === "m92pin");
  if (ent) {
    const orig = ent.render;
    ent.render = function(el, ...a){
      const r = orig.call(this, el, ...a);
      const h = document.createElement("div"); h.id = "m99dhost"; el.appendChild(h); card(h);
      return r;
    };
  }
})();
