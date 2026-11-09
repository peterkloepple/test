# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m64_drucken (v2.0.18)
# Direkt drucken: Rechnungen, Angebote, Auftragsbestaetigungen, Storno,
# Mahnungen, Briefe und aus Vorlagen erstellte Dokumente.
# PDFs werden selbst gedruckt (pypdfium2 rendert die Seite, Windows-GDI schickt
# sie an den Drucker) - unabhaengig davon, welches PDF-Programm installiert ist.
# Druckerwahl, Kopien, Seiten, beidseitig, schwarzweiss. Word-/LibreOffice-
# Dateien gehen ueber das zugehoerige Programm ("print"-Befehl von Windows).
# Entwuerfe werden mit dem Vermerk ENTWURF gedruckt und nicht festgeschrieben;
# fertige Rechnungen werden - wie beim PDF - festgeschrieben.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M64_VERSION = "1.0.0"
PRINT_JOBS = {}
PRINT_LOCK = threading.Lock()
PRINT_DPI = 300
PRINT_FAKE = os.environ.get("PA_PRINT_FAKE")    # tests: folder for rendered pages instead of a printer


# ---------------- Windows printer API (ctypes, no extra library) ----------------

def _win():
    return sys.platform.startswith("win") and not PRINT_FAKE


def printers_list():
    if PRINT_FAKE:
        return ["Testdrucker A", "Testdrucker B"], "Testdrucker A"
    if not _win():
        names, dflt = [], ""
        try:
            out = subprocess.run(["lpstat", "-a"], capture_output=True, text=True, timeout=5).stdout
            names = [l.split()[0] for l in out.splitlines() if l.strip()]
            d = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, timeout=5).stdout
            dflt = d.split(":")[-1].strip() if ":" in d else ""
        except Exception:
            pass
        return names, dflt
    import ctypes
    from ctypes import wintypes
    ws = ctypes.windll.winspool.drv if hasattr(ctypes.windll, "winspool") else ctypes.WinDLL("winspool.drv")
    flags = 2 | 4      # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    need, cnt = wintypes.DWORD(0), wintypes.DWORD(0)
    ws.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(need), ctypes.byref(cnt))
    names = []
    if need.value:
        buf = ctypes.create_string_buffer(need.value)
        if ws.EnumPrintersW(flags, None, 4, buf, need, ctypes.byref(need), ctypes.byref(cnt)):
            class PI4(ctypes.Structure):
                _fields_ = [("pPrinterName", wintypes.LPWSTR), ("pServerName", wintypes.LPWSTR), ("Attributes", wintypes.DWORD)]
            arr = ctypes.cast(buf, ctypes.POINTER(PI4))
            names = [arr[i].pPrinterName for i in range(cnt.value) if arr[i].pPrinterName]
    n = wintypes.DWORD(0)
    ws.GetDefaultPrinterW(None, ctypes.byref(n))
    dflt = ""
    if n.value:
        b = ctypes.create_unicode_buffer(n.value)
        if ws.GetDefaultPrinterW(b, ctypes.byref(n)):
            dflt = b.value
    return sorted(set(names), key=str.lower), dflt


def _devmode(printer, duplex, gray):
    """DEVMODE with duplex / monochrome for CreateDC, or None"""
    import ctypes
    from ctypes import wintypes
    ws = _winspool()
    h = wintypes.HANDLE()
    if not ws.OpenPrinterW(printer, ctypes.byref(h), None):
        return None
    try:
        size = ws.DocumentPropertiesW(None, h, printer, None, None, 0)
        if size <= 0:
            return None
        buf = ctypes.create_string_buffer(size)
        if ws.DocumentPropertiesW(None, h, printer, buf, None, 2) < 0:   # DM_OUT_BUFFER
            return None
        fields = int.from_bytes(buf.raw[72:76], "little")
        if duplex:
            fields |= 0x1000                                              # DM_DUPLEX
            buf[94:96] = (2).to_bytes(2, "little")                        # DMDUP_VERTICAL (long edge)
        if gray:
            fields |= 0x0800                                              # DM_COLOR
            buf[92:94] = (1).to_bytes(2, "little")                        # DMCOLOR_MONOCHROME
        buf[72:76] = fields.to_bytes(4, "little")
        if ws.DocumentPropertiesW(None, h, printer, buf, buf, 2 | 8) < 0:   # DM_OUT_BUFFER | DM_IN_BUFFER
            return None
        return buf
    finally:
        ws.ClosePrinter(h)


_GDI = None


def _gdi32():
    """own gdi32 instance with full prototypes: on 64-bit Windows the HDC is a 64-bit handle and
    ctypes' default (int) gives 'argument 1: OverflowError: int too long to convert'"""
    global _GDI
    if _GDI is not None:
        return _GDI
    import ctypes
    from ctypes import wintypes
    g = ctypes.WinDLL("gdi32", use_last_error=True)
    H, I, VP = wintypes.HDC, ctypes.c_int, ctypes.c_void_p
    for name, res, args in (
            ("CreateDCW", H, [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, VP]),
            ("GetDeviceCaps", I, [H, I]),
            ("StartDocW", I, [H, VP]),
            ("SetStretchBltMode", I, [H, I]),
            ("SetBrushOrgEx", wintypes.BOOL, [H, I, I, VP]),
            ("StartPage", I, [H]), ("EndPage", I, [H]), ("EndDoc", I, [H]), ("AbortDoc", I, [H]),
            ("DeleteDC", wintypes.BOOL, [H]),
            ("StretchDIBits", I, [H, I, I, I, I, I, I, I, I, ctypes.c_char_p, VP, wintypes.UINT, wintypes.DWORD])):
        f = getattr(g, name)
        f.restype, f.argtypes = res, args
    _GDI = g
    return g


def _winspool():
    import ctypes
    from ctypes import wintypes
    w = ctypes.WinDLL("winspool.drv", use_last_error=True)
    w.OpenPrinterW.restype, w.OpenPrinterW.argtypes = wintypes.BOOL, [wintypes.LPCWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    w.ClosePrinter.restype, w.ClosePrinter.argtypes = wintypes.BOOL, [wintypes.HANDLE]
    w.DocumentPropertiesW.restype = ctypes.c_long
    w.DocumentPropertiesW.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
    return w


def _gdi_print(printer, title, images_fn, n_pages, page_sizes, copies, duplex, gray, job):
    import ctypes
    from ctypes import wintypes
    gdi = _gdi32()
    dm = None
    try:
        dm = _devmode(printer, duplex, gray)
    except Exception:
        dm = None
    hdc = gdi.CreateDCW("WINSPOOL", printer, None, dm)
    if not hdc:
        raise ValueError(f"Drucker „{printer}“ ist nicht erreichbar.")

    class DOCINFOW(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_int), ("lpszDocName", wintypes.LPCWSTR), ("lpszOutput", wintypes.LPCWSTR),
                    ("lpszDatatype", wintypes.LPCWSTR), ("fwType", wintypes.DWORD)]

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    try:
        dpx, dpy = gdi.GetDeviceCaps(hdc, 88), gdi.GetDeviceCaps(hdc, 90)          # LOGPIXELSX/Y
        offx, offy = gdi.GetDeviceCaps(hdc, 112), gdi.GetDeviceCaps(hdc, 113)      # PHYSICALOFFSETX/Y
        di = DOCINFOW(ctypes.sizeof(DOCINFOW), title[:120], None, None, 0)
        if gdi.StartDocW(hdc, ctypes.addressof(di)) <= 0:
            raise ValueError("Der Druckauftrag wurde vom Drucker abgelehnt.")
        gdi.SetStretchBltMode(hdc, 4)                                               # HALFTONE
        gdi.SetBrushOrgEx(hdc, 0, 0, None)
        done = 0
        for c in range(copies):
            if c and duplex and n_pages % 2:
                # v2.1.0: duplex + odd page count: an empty back side, otherwise the next copy starts on the
                # back of the last page (2 copies of a 1-page invoice ended up on one sheet)
                gdi.StartPage(hdc)
                gdi.EndPage(hdc)
            for i in range(n_pages):
                im = images_fn(i, min(dpx, PRINT_DPI))
                wpt, hpt = page_sizes[i]
                dw, dh = int(round(wpt / 72.0 * dpx)), int(round(hpt / 72.0 * dpy))
                gdi.StartPage(hdc)
                W, H = im.size
                band = 400
                for y0 in range(0, H, band):
                    part = im.crop((0, y0, W, min(H, y0 + band)))
                    pw, ph = part.size
                    stride = (pw * 3 + 3) & ~3
                    bits = part.tobytes("raw", "BGR", stride, -1)
                    bh = BMIH(40, pw, ph, 1, 24, 0, 0, 0, 0, 0, 0)
                    ty = int(round(y0 * dh / H)) - offy
                    th = int(round((y0 + ph) * dh / H)) - int(round(y0 * dh / H))
                    gdi.StretchDIBits(hdc, -offx, ty, dw, th, 0, 0, pw, ph, bits, ctypes.addressof(bh), 0, 0x00CC0020)
                gdi.EndPage(hdc)
                done += 1
                job["fortschritt"] = f"Seite {done} von {n_pages * copies}"
        gdi.EndDoc(hdc)
    except Exception:
        try:
            gdi.AbortDoc(hdc)
        except Exception:
            pass
        raise
    finally:
        gdi.DeleteDC(hdc)


def _page_set(spec, n):
    """'1-2,4' -> list of 0-based indexes"""
    spec = (spec or "").replace(" ", "")
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d*))?", part)
        if not m:
            raise ValueError(f"Seitenangabe „{spec}“ verstehe ich nicht (Beispiel: 1-2,4).")
        a = max(1, int(m.group(1)))
        b = int(m.group(2)) if m.group(2) else (n if part.endswith("-") else a)
        b = min(b, n)      # "1-99999999999" must not loop through billions of numbers
        out += [i - 1 for i in range(a, b + 1)]
    if not out:
        raise ValueError("Die gewählten Seiten gibt es im Dokument nicht.")
    return out


def print_pdf_bytes(data, opt, title, job, mark=""):
    with PDFIUM_LOCK:     # v3.6.1: pdfium is not thread safe - the whole print job keeps the document
        return _print_pdf_bytes(data, opt, title, job, mark)


def _print_pdf_bytes(data, opt, title, job, mark=""):
    doc = pdfium.PdfDocument(data)
    try:
        n = len(doc)
        pages = _page_set(opt.get("seiten"), n)
        sizes = [doc[i].get_size() for i in pages]
        gray = bool(opt.get("sw"))

        def img(k, dpi):
            from PIL import Image, ImageDraw, ImageFont
            im = doc[pages[k]].render(scale=dpi / 72.0).to_pil().convert("RGB")
            if gray:
                im = im.convert("L").convert("RGB")
            if mark:
                w, h = im.size
                ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                d = ImageDraw.Draw(ov)
                try:
                    f = ImageFont.truetype("arialbd.ttf" if _win() else "DejaVuSans-Bold.ttf", int(w / 7))
                except Exception:
                    f = ImageFont.load_default()
                tw = d.textlength(mark, font=f)
                d.text(((w - tw) / 2, h / 2 - w / 14), mark, font=f, fill=(200, 40, 40, 70))
                ov = ov.rotate(35, resample=Image.BICUBIC, center=(w / 2, h / 2))
                im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
            return im
        copies = max(1, min(99, int(opt.get("kopien") or 1)))
        if PRINT_FAKE:
            os.makedirs(PRINT_FAKE, exist_ok=True)
            for c in range(copies):
                for k in range(len(pages)):
                    img(k, 100).save(os.path.join(PRINT_FAKE, f"{_slugp(title)}_k{c + 1}_s{pages[k] + 1}.png"))
            job["fortschritt"] = f"{len(pages) * copies} Seite(n)"
            return len(pages) * copies
        printer = opt.get("drucker") or printers_list()[1]
        if not printer:
            raise ValueError("Kein Drucker gefunden – bitte in Windows einen Drucker einrichten.")
        if _win():
            _gdi_print(printer, title, img, len(pages), sizes, copies, bool(opt.get("duplex")), gray, job)
        else:
            tmp = os.path.join(DATA_DIR, "_tmp_print_" + uuid.uuid4().hex[:8] + ".pdf")
            with open(tmp, "wb") as f:
                f.write(data)
            try:
                args = ["lp", "-d", printer, "-n", str(copies)]
                if opt.get("seiten"):
                    args += ["-P", opt["seiten"]]
                if opt.get("duplex"):
                    args += ["-o", "sides=two-sided-long-edge"]
                r = subprocess.run(args + [tmp], capture_output=True, text=True, timeout=60)
                if r.returncode:
                    raise ValueError("Drucken fehlgeschlagen: " + (r.stderr or r.stdout)[:200])
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return len(pages) * copies
    finally:
        doc.close()


def _slugp(t):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", t)[:40] or "druck"


def print_other_file(path, opt):
    """Word, Excel, LibreOffice ...: print verb of the associated program (default printer)"""
    if PRINT_FAKE:
        os.makedirs(PRINT_FAKE, exist_ok=True)
        shutil.copy2(path, os.path.join(PRINT_FAKE, "datei_" + os.path.basename(path)))
        return 1
    if not _win():
        raise ValueError("Diese Dateiart kann hier nicht direkt gedruckt werden.")
    printer = opt.get("drucker")
    try:
        if printer:
            import ctypes
            sh = ctypes.WinDLL("shell32")
            sh.ShellExecuteW.restype = ctypes.c_void_p
            sh.ShellExecuteW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
            r = sh.ShellExecuteW(None, "printto", path, f'"{printer}"', None, 0)
            if (r or 0) > 32:
                return 1
        os.startfile(path, "print")
        return 1
    except OSError as e:
        raise ValueError(f"Für „{os.path.splitext(path)[1]}“-Dateien ist kein Programm zum Drucken eingerichtet ({e}). "
                         "Datei öffnen und dort drucken.")


# ---------------- jobs ----------------

def _job_run(job, fn):
    try:
        with PRINT_LOCK:
            job["state"] = "druckt"
            n = fn(job)
        job.update(state="fertig", seiten=n, ende=now_iso())
        set_setting("print_letzter", {"zeit": now_iso(), "ok": True, "titel": job["titel"], "seiten": n, "drucker": job["drucker"]})
    except Exception as e:
        if not isinstance(e, ValueError):
            traceback.print_exc()
        job.update(state="fehler", fehler=str(e) if isinstance(e, ValueError) else f"Drucken fehlgeschlagen: {e}")
        set_setting("print_letzter", {"zeit": now_iso(), "ok": False, "titel": job["titel"], "fehler": job["fehler"]})


def print_start(titel, opt, fn):
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "titel": titel, "state": "wartet", "drucker": opt.get("drucker") or "", "fortschritt": "", "start": now_iso()}
    PRINT_JOBS[jid] = job
    for k in [k for k, v in PRINT_JOBS.items() if v["state"] in ("fertig", "fehler") and k != jid][:-20]:
        PRINT_JOBS.pop(k, None)
    if opt.get("merken", True):
        keep = {k: opt.get(k) for k in ("drucker", "duplex", "sw") if k in opt}
        set_setting("print_opts", dict(get_settings().get("print_opts") or {}, **keep))
    threading.Thread(target=_job_run, args=(job, fn), daemon=True).start()
    return {"ok": True, "job": jid}


def print_invoice(d):
    opt = d.get("opt") or {}
    ids = [int(i) for i in (d.get("ids") or ([d["id"]] if d.get("id") else []))]
    inv_draft = d.get("inv")
    if not ids and not inv_draft:
        raise ValueError("Nichts zum Drucken ausgewählt.")
    s = get_settings()
    jobs = []
    if inv_draft:                      # unsaved state from the editor (draft / preview)
        inv = dict(inv_draft)
        if d.get("blanko"):            # v2.0.17: blank form - no watermark, no number, nothing saved or locked
            inv["nr"] = ""
            inv.pop("id", None)
            jobs.append((inv, ""))
        else:
            if not inv.get("nr"):
                inv["nr"] = "ENTWURF"
            jobs.append((inv, "ENTWURF"))
    for iid in ids:
        inv = get_invoice(iid)
        if not inv:
            continue
        if inv["status"] == "entwurf" or str(inv.get("nr") or "").startswith("E-"):
            jobs.append((inv, "ENTWURF"))
        else:
            jobs.append((inv, ""))
    if not jobs:
        raise ValueError("Dokument nicht gefunden.")
    titel = ", ".join(f"{DOC_TYPES.get(i.get('typ') or 'rechnung', DOC_TYPES['rechnung'])['title']} {i.get('nr') or ''}".strip() for i, _ in jobs[:4]) \
        + (f" + {len(jobs) - 4} weitere" if len(jobs) > 4 else "")

    def run(job):
        n = 0
        for inv, mark in jobs:
            if not mark and inv.get("id"):
                # printed = issued: lock like the PDF export and keep the PDF in the folder
                lock_invoice(inv["id"])
                inv = get_invoice(inv["id"])
                data = render_invoice_pdf(inv, s, attachments=bool(opt.get("anlagen", True)))
                try:
                    write_file(invoice_pdf_path(inv, s), render_invoice_pdf(inv, s))
                except Exception:
                    traceback.print_exc()
            else:
                data = render_invoice_pdf(inv, s, attachments=bool(opt.get("anlagen", True)))
            n += print_pdf_bytes(data, opt, f"{inv.get('nr') or 'Dokument'}", job, mark)
        return n
    return print_start(titel, opt, run)


def print_brief(d):
    opt = d.get("opt") or {}
    if d.get("bid") and not d.get("brief"):
        b = br_get(int(d["bid"]))
        if b.get("datei_da") and not b["datei_abs"].lower().endswith(".pdf"):
            return print_file({"path": b["datei_abs"], "opt": opt}, _intern=True)
    else:
        p = dict(d.get("brief") or {})
        b = dict(p, anschrift=p.get("addr") or p.get("anschrift") or [])
    data = brief_pdf(b, br_values(b))
    return print_start("Brief " + (b.get("betreff") or ""), opt, lambda job: print_pdf_bytes(data, opt, "Brief", job))


def _m64_path_ok(path):
    """v2.1.0: the HTTP route prints only files of the data folder / PDF folder (no arbitrary paths, no '..')"""
    roots = [DATA_DIR]
    pdir = (get_settings().get("pdf_dir") or "").strip()
    if pdir:
        roots.append(pdir)
    rp = os.path.normcase(os.path.realpath(path))
    for r in roots:
        rr = os.path.normcase(os.path.realpath(r))
        try:
            if os.path.commonpath([rr, rp]) == rr:
                return True
        except ValueError:      # other drive on Windows
            pass
    return False


def print_file(d, _intern=False):
    opt = d.get("opt") or {}
    path = str(d.get("path") or "")
    if path and not os.path.isabs(path):
        path = os.path.join(DATA_DIR, path)
    if not path or not os.path.isfile(path):
        raise ValueError("Datei nicht gefunden.")
    if not _intern and not _m64_path_ok(path):
        raise ValueError("Diese Datei liegt nicht im Datenordner und wird nicht gedruckt.")
    name = os.path.basename(path)
    if path.lower().endswith(".pdf"):
        data = open(path, "rb").read()
        return print_start(name, opt, lambda job: print_pdf_bytes(data, opt, name, job))
    return print_start(name, opt, lambda job: print_other_file(path, opt))


def print_mahnung(d):
    m = q("SELECT * FROM mahnungen WHERE id=?", (int(d["id"]),), one=True)
    if not m:
        raise ValueError("Mahnung nicht gefunden.")
    return print_file({"path": m["file"], "opt": d.get("opt") or {}}, _intern=True)


def print_info():
    names, dflt = printers_list()
    s = get_settings()
    o = s.get("print_opts") or {}
    return {"ok": True, "drucker": names, "standard": dflt, "gewaehlt": o.get("drucker") if o.get("drucker") in names else dflt,
            "duplex": bool(o.get("duplex")), "sw": bool(o.get("sw")), "direkt": bool(s.get("print_direkt")),
            "letzter": s.get("print_letzter") or {}, "windows": sys.platform.startswith("win")}


def _m64_selftest():
    err = []
    try:
        if _page_set("1-2,4", 5) != [0, 1, 3] or _page_set("", 3) != [0, 1, 2] or _page_set("2-", 4) != [1, 2, 3]:
            err.append("Drucken: Seitenangabe falsch ausgewertet")
    except Exception as e:
        err.append(f"Drucken: {e}")
    return err


HOOK_GET["/api/print/info"] = lambda h, qs: h._send(200, print_info())
HOOK_GET["/api/print/status"] = lambda h, qs: h._send(200, dict(PRINT_JOBS.get(qs.get("job") or "", {"state": "unbekannt"}), ok=True))
HOOK_POST["/api/print/invoice"] = lambda h, d: h._send(200, print_invoice(d))
HOOK_POST["/api/print/brief"] = lambda h, d: h._send(200, print_brief(d))
HOOK_POST["/api/print/file"] = lambda h, d: h._send(200, print_file(d))
HOOK_POST["/api/print/mahnung"] = lambda h, d: h._send(200, print_mahnung(d))
HOOK_POST["/api/print/direkt"] = lambda h, d: (set_setting("print_direkt", bool(d.get("an"))), h._send(200, {"ok": True}))[1]
HOOK_SELFTEST.append(_m64_selftest)
