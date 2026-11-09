# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m00_schrift_basis (v2.0.11)
# Grundlage fuer waehlbare Schriftarten in allen PDFs: statt fest eingebauter
# Helvetica fragen alle PDF-Erzeuger FONT_R() / FONT_B() / FONT_I() / FONT_BI()
# nach dem aktuellen Schriftnamen. Welche Schrift gilt, legt m62_schriften fest:
#  - pro Vorgang (Thread) ueber "with doc_font(familie):"
#  - sonst die Standard-Schrift aus den Einstellungen.
# Wird als erstes Modul in den gemeinsamen Namensraum geladen.
# Autor: T. Pfeiffer

M00_VERSION = "1.0.0"

# family name -> {"r": reportlab font name, "b": ..., "i": ..., "bi": ...}
FONT_FAMILIES = {
    "Helvetica": {"r": "Helvetica", "b": "Helvetica-Bold", "i": "Helvetica-Oblique", "bi": "Helvetica-BoldOblique", "builtin": True},
    "Times": {"r": "Times-Roman", "b": "Times-Bold", "i": "Times-Italic", "bi": "Times-BoldItalic", "builtin": True},
    "Courier": {"r": "Courier", "b": "Courier-Bold", "i": "Courier-Oblique", "bi": "Courier-BoldOblique", "builtin": True},
}
FONT_DEFAULT = {"fam": "Helvetica"}          # set by m62 from the settings
_FONT_TL = threading.local()


def _font_map():
    fam = getattr(_FONT_TL, "fam", None) or FONT_DEFAULT.get("fam") or "Helvetica"
    return FONT_FAMILIES.get(fam) or FONT_FAMILIES["Helvetica"]


def FONT_R():
    return _font_map()["r"]


def FONT_B():
    return _font_map()["b"]


def FONT_I():
    return _font_map()["i"]


def FONT_BI():
    return _font_map()["bi"]


def font_stylesheet():
    """reportlab sample stylesheet with the current document font"""
    from reportlab.lib.styles import getSampleStyleSheet
    ss = getSampleStyleSheet()
    m = {"Helvetica": FONT_R(), "Helvetica-Bold": FONT_B(), "Helvetica-Oblique": FONT_I(), "Helvetica-BoldOblique": FONT_BI()}
    for st in ss.byName.values():
        fn = getattr(st, "fontName", None)
        if fn in m:
            st.fontName = m[fn]
    return ss


class doc_font(object):
    """with doc_font("Montserrat"): ... - font for everything rendered in this thread"""

    def __init__(self, fam):
        self.fam = fam if fam in FONT_FAMILIES else None

    def __enter__(self):
        self.prev = getattr(_FONT_TL, "fam", None)
        if self.fam:
            _FONT_TL.fam = self.fam
        return self

    def __exit__(self, *a):
        _FONT_TL.fam = self.prev
        return False
