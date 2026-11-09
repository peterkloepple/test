# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m39_ansicht  v1.0.0 (ab Programm v3.6.1)
# Grosse Ansicht einer Datei vor dem Uebernehmen (Belege & Import, Pruefliste):
# - GET /api/ansicht/info?path=...           -> Art (pdf/bild/text), Seitenzahl, bei sonstigen Formaten der Text
# - GET /api/ansicht/seite?path=...&s=0&b=1600&r=0 -> Seite s als JPEG, b = gewuenschte Breite in Pixeln (400..2800),
#   r = Drehung 0/90/180/270 (nur Anzeige, Datei bleibt unveraendert)
# PDF ueber pdfium (auch mit gemerktem Passwort), Bilder inkl. Drehung aus der Kamera (EXIF) und mehrseitige TIFF.
# Nur Dateien im Datenordner. Kleiner Zwischenspeicher fuer zuletzt gezeigte Seiten.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M39_VERSION = "1.0.0"
import collections
M39_CACHE = collections.OrderedDict()
M39_LOCK = threading.Lock()
M39_IMG = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def _m39_path(rel):
    root_ = os.path.abspath(DATA_DIR)
    fp = os.path.abspath(os.path.join(root_, rel or ""))
    if os.path.normcase(os.path.commonpath([fp, root_])) != os.path.normcase(root_):
        raise ValueError("Datei liegt nicht im Datenordner.")
    if not os.path.isfile(fp):
        raise ValueError("Datei nicht gefunden.")
    return fp


def _m39_pw(fp):
    return (globals().get("FILE_PW") or {}).get(os.path.abspath(fp))


def m39_info(rel):
    fp = _m39_path(rel)
    ext = os.path.splitext(fp)[1].lower()
    out = {"ok": True, "name": os.path.basename(fp), "groesse": os.path.getsize(fp), "typ": "text", "seiten": 0, "text": ""}
    try:
        if ext == ".pdf" and globals().get("pdfium"):
            with PDFIUM_LOCK:     # pdfium is not thread safe
                doc = pdfium.PdfDocument(fp, password=_m39_pw(fp))
                try:
                    out.update(typ="pdf", seiten=len(doc))
                finally:
                    doc.close()
            return out
        if ext in M39_IMG:
            from PIL import Image
            with Image.open(fp) as im:
                out.update(typ="bild", seiten=max(1, int(getattr(im, "n_frames", 1) or 1)))
            return out
    except Exception as e:
        out["fehler"] = str(e)[:200]
    # other formats (XML e-invoice, Word, Excel, mail ...): show the text the program reads from them
    try:
        t_, _used, fmt = extract_text_any(fp, fp, _m39_pw(fp))
        out.update(typ="text", text=(t_ or "")[:200000], format=fmt)
    except Exception as e:
        out.update(typ="text", text="", fehler=f"Inhalt nicht lesbar: {str(e)[:200]}")
    return out


def m39_seite(rel, s=0, b=1600, r=0):
    fp = _m39_path(rel)
    s = max(0, int(s or 0))
    b = min(2800, max(400, int(b or 1600)))
    r = (int(r or 0) // 90 * 90) % 360
    key = (fp, os.path.getmtime(fp), s, b, r)
    with M39_LOCK:
        if key in M39_CACHE:
            M39_CACHE.move_to_end(key)
            return M39_CACHE[key]
    from PIL import Image, ImageOps
    ext = os.path.splitext(fp)[1].lower()
    if ext == ".pdf":
        with PDFIUM_LOCK:     # pdfium is not thread safe - pages are requested in parallel
            doc = pdfium.PdfDocument(fp, password=_m39_pw(fp))
            try:
                if s >= len(doc):
                    raise ValueError("Seite nicht vorhanden.")
                pg = doc[s]
                w_pt = (pg.get_height() if r in (90, 270) else pg.get_width()) or 595
                im = pg.render(scale=min(6.0, max(0.5, b / w_pt))).to_pil()
            finally:
                doc.close()
    elif ext in M39_IMG:
        im = Image.open(fp)
        if s:
            im.seek(s)
        im = ImageOps.exif_transpose(im)
        if r:
            im = im.rotate(-r, expand=True)
        if im.width > b:
            im = im.resize((b, max(1, round(im.height * b / im.width))), Image.LANCZOS)
    else:
        raise ValueError("Keine Bildansicht für dieses Format.")
    if r and ext == ".pdf":
        im = im.rotate(-r, expand=True)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=88)
    data = buf.getvalue()
    with M39_LOCK:
        M39_CACHE[key] = data
        while len(M39_CACHE) > 40:
            M39_CACHE.popitem(last=False)
    return data


def _m39_seite_route(h, qs):
    try:
        data = m39_seite(qs.get("path"), qs.get("s") or 0, qs.get("b") or 1600, qs.get("r") or 0)
    except ValueError as e:
        return h._send(404, str(e).encode("utf-8"), "text/plain; charset=utf-8")
    return h._send(200, data, "image/jpeg", {"Cache-Control": "max-age=600"})


HOOK_GET["/api/ansicht/info"] = lambda h, qs: h._send(200, m39_info(qs.get("path")))
HOOK_GET["/api/ansicht/seite"] = _m39_seite_route


def m39_selftest():
    err = []
    tmp = os.path.join(DATA_DIR, "_m39_test")
    try:
        os.makedirs(tmp, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (900, 1200), "white").save(os.path.join(tmp, "a.png"))
        rel = os.path.relpath(os.path.join(tmp, "a.png"), DATA_DIR)
        i = m39_info(rel)
        if i["typ"] != "bild" or i["seiten"] != 1:
            err.append(f"m39: Bild-Info falsch ({i})")
        d = m39_seite(rel, 0, 600)
        if Image.open(io.BytesIO(d)).width != 600:
            err.append("m39: Bild nicht auf Breite gebracht")
        dr = Image.open(io.BytesIO(m39_seite(rel, 0, 600, 90)))
        if dr.width != 600 or dr.height != 450:
            err.append(f"m39: gedrehtes Bild falsch ({dr.size})")
        if globals().get("pdfium"):
            from reportlab.pdfgen import canvas as _cv
            pp = os.path.join(tmp, "b.pdf")
            c_ = _cv.Canvas(pp)
            c_.drawString(72, 760, "Seite 1"); c_.showPage(); c_.drawString(72, 760, "Seite 2"); c_.save()
            relp = os.path.relpath(pp, DATA_DIR)
            ip = m39_info(relp)
            if ip["typ"] != "pdf" or ip["seiten"] != 2:
                err.append(f"m39: PDF-Info falsch ({ip})")
            if abs(Image.open(io.BytesIO(m39_seite(relp, 1, 1000))).width - 1000) > 3:
                err.append("m39: PDF-Seite nicht in gewuenschter Breite")
        try:
            m39_info("../../etc/passwd")
            err.append("m39: Pfad ausserhalb des Datenordners nicht abgewiesen")
        except ValueError:
            pass
    except Exception as e:
        err.append(f"m39 Ausnahme: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return err


HOOK_SELFTEST.append(m39_selftest)
print(f"INIT m39_ansicht v{M39_VERSION}")
