// PA Rechnung v2.0.0 - Loeschen ohne Rueckfrage (Einstellung, Standard: keine Rueckfrage)
// Gilt fuer alle Bestaetigungen mit Knopf "Loeschen", "Entfernen" oder "Verwerfen" -
// auch fuer Sammelaktionen. Andere Rueckfragen (Wiederherstellen, Datenordner,
// Grenzwarnungen ...) bleiben unveraendert.
// Autor: T. Pfeiffer
(function(){
  const DEL_LABELS = ["Löschen", "Entfernen", "Verwerfen"];
  const orig = window.confirmBox;
  window.confirmBox = function(text, ok = "Löschen"){
    const ask_ = !!(S && S.settings && S.settings.loeschen_bestaetigen);
    if (!ask_ && DEL_LABELS.includes(ok)) return Promise.resolve(true);
    return orig(text, ok);
  };

  EXT.after.push(n => {
    if (n !== "vSettings" || setTab !== "daten") return;
    const page = $("#main .page"); if (!page || $("#delcfg", page)) return;
    const card = document.createElement("div"); card.className = "card"; card.id = "delcfg"; card.style.marginTop = "16px";
    card.innerHTML = `<div class="hd"><h3>Bedienung</h3></div><div class="bd fr">
      <label class="chk"><input type="checkbox" data-s="loeschen_bestaetigen" ${S.settings.loeschen_bestaetigen?"checked":""}> Vor dem Löschen nachfragen</label>
      <div class="small muted">Aus (Standard): Löschen, Entfernen und Verwerfen passieren sofort ohne Rückfrage – auch bei mehreren markierten Einträgen. Gelöschte Beleg-Dateien landen weiterhin im Ordner „_Papierkorb“ im Datenordner, und jede Löschung steht im GoBD-Protokoll. Festgeschriebene Rechnungen lassen sich weiterhin nicht löschen (nur stornieren). Mit „Speichern“ oben übernehmen.</div></div>`;
    page.appendChild(card);
  });
})();
