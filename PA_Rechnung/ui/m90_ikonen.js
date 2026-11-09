// Pfeiffer-Audio Rechnung v2.0.19 - UI-Modul m90_ikonen: Standardgroesse fuer Symbole
// Symbole (ic(...)) ausserhalb von Knoepfen, Karten-Titeln oder Hinweisen hatten keine Groesse
// und wurden als grosses schwarzes Quadrat gezeichnet. :where() hat Spezifitaet 0 - alle
// vorhandenen Regeln (.btn svg, .nav svg, .alert svg ...) behalten Vorrang.
// Autor: T. Pfeiffer
(function(){
  "use strict";
  if (document.getElementById("m90css")) return;
  const st = document.createElement("style"); st.id = "m90css";
  st.textContent = ":where(#main, .mb, #side, #toast) svg[viewBox='0 0 24 24']:not([width]){width:1.15em;height:1.15em;" +
    "stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;vertical-align:-0.2em;flex:none}" +
    // v2.0.19: many settings tabs - wrap whole tabs into a second row instead of breaking labels
    ".tabs{flex-wrap:wrap}.tab{white-space:nowrap}";
  document.head.appendChild(st);
})();
