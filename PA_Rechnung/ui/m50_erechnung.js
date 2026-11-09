// Pfeiffer-Audio Rechnung v2.0.0 - UI-Modul m50_erechnung: XRechnung (CII) und ZUGFeRD-PDF erzeugen
// Knoepfe im Rechnungseditor (nur gespeicherte, fertige Rechnungen) + Einstellungs-Reiter "E-Rechnung".
// Autor: T. Pfeiffer
(function(){
  "use strict";
  if (!document.getElementById("m5xcss")) { const st = document.createElement("style"); st.id = "m5xcss";
    st.textContent = ".alert > svg + span{flex:1;min-width:0}"; document.head.appendChild(st); }

  async function eDialog(fmt){
    if (!cur || !cur.id) return;
    const id = cur.id;
    const info = await api("/api/m50/info?id=" + id);
    if (!info || info.ok === false) return;
    const miss = info.seller_missing || [];
    const title = fmt === "zugferd" ? "ZUGFeRD-PDF erzeugen" : "XRechnung (XML) erzeugen";
    const r = await modal(title, `<div class="fr">
      ${miss.length ? `<div class="alert warn" style="cursor:default;margin-bottom:10px">${ic("alert")}<span>Verkäuferdaten unvollständig: <b>${esc(miss.join(", "))}</b> – bitte unter Einstellungen → E-Rechnung ergänzen.</span></div>` : ""}
      <label class="f">Käuferreferenz / Leitweg-ID (BT-10)<input class="in" id="m50ref" value="${esc(info.buyer_ref || "")}" placeholder="bei Behörden Leitweg-ID, sonst Bestellnummer oder leer (= n/a)"></label>
      <div class="row"><label class="f">E-Mail des Empfängers (BT-49)<input class="in" id="m50mail" value="${esc(info.buyer_mail || "")}" placeholder="rechnung@kunde.de"></label>
        <label class="f" style="flex:.7">Bestellnummer (optional)<input class="in" id="m50ord" value=""></label></div>
      ${info.kunde ? `<label class="small" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="m50save" checked> Leitweg-ID / E-Mail beim Kunden „${esc(info.kunde)}“ merken</label>` : ""}
      <div class="small muted" style="margin-top:10px">Kleinunternehmer: Steuerkategorie „E“, Befreiungsgrund „Kleinunternehmer gemäß § 19 UStG“, Steuerbetrag 0,00 €.
        ${fmt === "zugferd" ? "Das XML wird als <b>factur-x.xml</b> in das Rechnungs-PDF eingebettet (Profil EN 16931)." : "Profil XRechnung 3.0 (CII)."}
        Die Rechnung wird dabei festgeschrieben.</div></div>`,
      [{label:"Abbrechen"}, {label: fmt === "zugferd" ? "ZUGFeRD-PDF erzeugen" : "XML erzeugen", cls:"pri", value:true, onClick: async mb => {
        const body = {id, fmt, buyer_ref: $("#m50ref", mb).value, buyer_mail: $("#m50mail", mb).value, order_ref: $("#m50ord", mb).value,
          save_customer: !!($("#m50save", mb) && $("#m50save", mb).checked)};
        const res = await api("/api/m50/export", body);
        if (!res || !res.ok) return false;
        mb._res = res; eResult(res, fmt);
      }}]);
    if (r) { await reload(); if (view === "editor" && cur && cur.id === id) { cur = await api("/api/invoice?id=" + id); cur.attachments = cur.attachments || []; curBase = curSnap(); vEditor(); } }
  }

  function eResult(res, fmt){
    const ok = !(res.pruefung || []).length;
    modal(fmt === "zugferd" ? "ZUGFeRD-PDF erstellt" : "XRechnung erstellt", `<div class="fr">
      <div class="small" style="word-break:break-all"><b>Datei:</b> ${esc(res.path)}</div>
      <div class="kv" style="margin:10px 0"><span>Rechnungsbetrag</span><span class="r">${eur(res.summe)}</span><span>Käuferreferenz</span><span class="r">${esc(res.buyer_ref)}</span></div>
      <span class="badge ${ok ? "ok" : "bad"}"><span class="dot"></span>${ok ? "Rücklese-Prüfung bestanden (Summen stimmen)" : "Rücklese-Prüfung mit Abweichungen"}</span>
      ${(res.pruefung || []).map(t => `<div class="alert bad" style="cursor:default;margin-top:6px">${esc(t)}</div>`).join("")}
      ${(res.warn || []).map(t => `<div class="alert warn" style="cursor:default;margin-top:6px">${ic("alert")}<span>${esc(t)}</span></div>`).join("")}
      <div class="small muted" style="margin-top:10px">${esc(res.hinweis || "")} Zur offiziellen Prüfung kann die Datei z. B. im KoSIT-Validator oder bei einem Online-Prüfdienst getestet werden.</div></div>`,
      [{label:"Ordner öffnen", onClick: async () => { await api("/api/open", {path: res.path, folder: true}); return false; }}, {label:"Schließen", cls:"pri"}]);
  }

  EXT.after.push(n => {
    if (n !== "vEditor" || !cur || !cur.id) return;
    if (!["rechnung", "storno"].includes(cur.typ || "rechnung") || cur.status === "entwurf") return;
    const act = $("#main .ph .act"); if (!act || $("#m50x", act)) return;
    const span = document.createElement("span"); span.className = "expg"; span.id = "m50x";
    span.innerHTML = `<button class="btn" type="button" id="m50xml" title="E-Rechnung im Format XRechnung 3.0 (CII) erzeugen">${ic("inv")} XRechnung (XML)</button>` +
                     `<button class="btn" type="button" id="m50zf" title="PDF mit eingebetteter E-Rechnung (ZUGFeRD / Factur-X EN 16931)">${ic("pdf")} ZUGFeRD-PDF</button>`;
    act.insertBefore(span, act.lastElementChild);
    $("#m50xml", span).onclick = () => eDialog("xml");
    $("#m50zf", span).onclick = () => eDialog("zugferd");
  });

  EXT.settings.push({key:"m50", label:"E-Rechnung", async render(el){
    const d = await api("/api/m50/seller");
    const s = d.seller || {};
    const F = (k, l, ph="") => `<label class="f">${l}<input class="in" data-m50="${k}" value="${esc(s[k] || "")}" placeholder="${esc(ph)}"></label>`;
    el.innerHTML = `<div class="card" style="margin-top:16px"><div class="hd"><h3>E-Rechnung (Ausgang)</h3></div><div class="bd fr">
      <div class="small muted" style="margin-bottom:8px">Verkäuferdaten für XRechnung / ZUGFeRD. Vorbelegt aus Absenderzeile und Fußzeilen – hier korrigieren.
        Pflicht nach XRechnung: Name, Ansprechpartner, Straße, PLZ, Ort, Telefon, E-Mail und Steuernummer oder USt-IdNr.</div>
      ${(d.missing || []).length ? `<div class="alert warn" style="cursor:default;margin-bottom:10px">${ic("alert")}<span>Es fehlt: <b>${esc(d.missing.join(", "))}</b></span></div>` : ""}
      <div class="row">${F("name", "Firmenname")}${F("inhaber", "Ansprechpartner")}</div>
      <div class="row">${F("strasse", "Straße / Postfach")}${F("plz", "PLZ")}${F("ort", "Ort")}${F("land", "Land (ISO)", "DE")}</div>
      <div class="row">${F("tel", "Telefon")}${F("mail", "E-Mail")}</div>
      <div class="row">${F("steuernr", "Steuernummer")}${F("ustid", "USt-IdNr. (falls vorhanden)")}</div>
      <div class="small muted">IBAN/BIC und Kontoinhaber kommen aus „Firma &amp; Bank“.</div>
      <label class="small" style="display:flex;gap:6px;align-items:center;margin-top:12px"><input type="checkbox" id="m50def" ${d.zugferd_default ? "checked" : ""}>
        ZUGFeRD-PDF standardmäßig beim PDF-Export (jede fertige Rechnung bekommt die XML eingebettet)</label>
      <div class="small muted" style="margin-top:6px">Hinweis: Das PDF erhält Factur-X-Anhang, XMP-Metadaten und AF-Verknüpfung. Eine echte PDF/A-3-Konformität
        (eingebettete Schriften, Farbprofil) wird <b>nicht</b> hergestellt und nicht geprüft. Für Behörden die reine XRechnung (XML) senden.</div>
      <div class="row" style="margin-top:12px"><span class="sp"></span><button class="btn pri" id="m50sv" style="flex:none">${ic("save")} Speichern</button></div>
    </div></div>`;
    $("#m50sv", el).onclick = async () => {
      const seller = {}; $$("[data-m50]", el).forEach(i => seller[i.dataset.m50] = i.value.trim());
      const r = await api("/api/m50/settings", {seller, zugferd_default: $("#m50def", el).checked});
      if (r && r.ok) { toast((r.missing || []).length ? "Gespeichert – es fehlt noch: " + r.missing.join(", ") : "E-Rechnungs-Daten gespeichert", (r.missing || []).length > 0); S.settings.m50_zugferd_default = $("#m50def", el).checked; }
    };
  }});
})();
