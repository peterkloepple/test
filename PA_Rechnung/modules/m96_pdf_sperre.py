# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m96_pdf_sperre (v2.4.1)
# Absturz behoben: Die PDF-Bibliothek pypdfium2 (PDFium) ist NICHT threadsicher. Der
# Programm-Server bedient jede Anfrage in einem eigenen Thread - zeigt eine Seite mehrere
# PDF-Vorschaubilder gleichzeitig (z. B. Projekt-Dateien), rendern mehrere Threads parallel
# und PDFium stuerzt mit "Segmentation fault" ab -> das ganze Programm schliesst sich.
# Abhilfe: alle Funktionen, die PDFium benutzen, laufen nacheinander (eine gemeinsame
# Sperre). Vorschau, Druck, Beleg-Texterkennung und Briefvorschau sind betroffen.
# Autor: T. Pfeiffer

M96_VERSION = "1.0.0"
M96_LOCK = threading.RLock()
M96_FUNCS = ("pdf_to_pngs", "file_thumb", "ocr_file", "print_pdf_bytes")


def _m96_wrap(name):
    f = globals().get(name)
    if f is None or getattr(f, "_m96", False):
        return

    def locked(*a, **k):
        with M96_LOCK:
            return f(*a, **k)
    locked._m96 = True
    locked.__name__ = getattr(f, "__name__", name)
    globals()[name] = locked


for _m96_n in M96_FUNCS:
    _m96_wrap(_m96_n)


def _m96_selftest():
    err = []
    for n in M96_FUNCS:
        f = globals().get(n)
        if f is not None and not getattr(f, "_m96", False):
            err.append(f"m96: {n} ohne PDF-Sperre")
    return err


HOOK_SELFTEST.append(_m96_selftest)
