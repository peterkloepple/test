# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m24_scanner  v1.1.0 (ab Programm v2.6.6)
# Scannen direkt in Rechnungen und Angebote (Anlage) und in Belege & Import (v1.1.0):
# - Windows-Scanschnittstelle WIA ueber PowerShell (kein Zusatzprogramm): das normale Windows-Scanfenster
#   oeffnet sich (Scanner, Einzug/Glas, Farbe, Aufloesung waehlbar), jede Seite landet als Bild in einer Scan-Sitzung.
# - Mehrere Seiten nacheinander, Seiten entfernen, dann alle Seiten als EINE PDF an das Dokument haengen
#   (gleicher Weg wie "Anlage hinzufuegen": Belege\Anlagen\<Jahr>, festgeschriebene Dokumente bleiben gesperrt).
# - Belege: Scan geht wie eine hineingezogene Datei durch die Belegerkennung (Texterkennung, Assistent, Pruefliste);
#   wahlweise alle Seiten = ein Beleg oder jede Seite = ein eigener Beleg (Stapel Kassenzettel).
# - Scan-Sitzungen liegen im Datenordner unter _scan und werden nach 2 Tagen automatisch entfernt.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M24_VERSION = "1.1.0"
M24_DIR = os.path.join(DATA_DIR, "_scan")
M24_LOCK = threading.Lock()
M24_TIMEOUT = 900          # the Windows scan dialog may stay open while the user prepares the page
M24_FORMAT_JPEG = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
M24_INTENT = {"farbe": 1, "grau": 2, "sw": 4}

M24_PS = r"""
$ErrorActionPreference = 'Stop'
try {
  $dlg = New-Object -ComObject WIA.CommonDialog
  # DeviceType 1 = scanner, Intent (1 colour / 2 grey / 4 text), Bias 0, JPEG, AlwaysSelectDevice, UseCommonUI, CancelError
  $img = $dlg.ShowAcquireImage(1, __INTENT__, 0, '__FMT__', $false, $true, $true)
  if ($img -eq $null) { Write-Output 'ABBRUCH'; exit 0 }
  if ($img.FormatID -ne '__FMT__') {
    $ip = New-Object -ComObject WIA.ImageProcess
    $ip.Filters.Add($ip.FilterInfos.Item('Convert').FilterID)
    $ip.Filters.Item(1).Properties.Item('FormatID').Value = '__FMT__'
    $ip.Filters.Item(1).Properties.Item('Quality').Value = 90
    $img = $ip.Apply($img)
  }
  if (Test-Path -LiteralPath '__OUT__') { Remove-Item -LiteralPath '__OUT__' -Force }
  $img.SaveFile('__OUT__')
  Write-Output ('OK ' + $img.HorizontalResolution)
} catch {
  $m = $_.Exception.Message
  if ($m -match '0x80210064' -or $m -match 'cancel' -or $m -match 'abgebrochen') { Write-Output 'ABBRUCH'; exit 0 }
  if ($m -match '0x80210015' -or $m -match 'no device' -or $m -match 'kein Ger') { Write-Output 'KEINSCANNER'; exit 0 }
  if ($m -match '80040154') { Write-Output 'KEINWIA'; exit 0 }
  Write-Output ('FEHLER ' + $m)
}
"""


def _m24_sid(sid):
    sid = str(sid or "")
    if not re.fullmatch(r"[0-9a-f]{16}", sid):
        raise ValueError("Ungültige Scan-Sitzung.")
    return sid


def _m24_dir(sid):
    return os.path.join(M24_DIR, _m24_sid(sid))


def _m24_pages(sid):
    d = _m24_dir(sid)
    if not os.path.isdir(d):
        return []
    return sorted(fn for fn in os.listdir(d) if re.fullmatch(r"p\d{3}\.(jpg|png)", fn))


def m24_scan_page(d):
    """one page from the scanner (Windows WIA dialog) -> jpg in the scan session"""
    sid = d.get("session") or uuid.uuid4().hex[:16]
    sd = _m24_dir(sid)
    os.makedirs(sd, exist_ok=True)
    pages = _m24_pages(sid)
    if len(pages) >= 200:
        raise ValueError("Höchstens 200 Seiten je Scan.")
    nr = (int(pages[-1][1:4]) + 1) if pages else 1
    out = os.path.join(sd, f"p{nr:03d}.jpg")
    test_img = os.environ.get("PA_SCAN_TEST_IMAGE")        # tests only
    if test_img:
        shutil.copy(test_img, out)
        return {"ok": True, "session": sid, "seiten": _m24_pages(sid), "neu": os.path.basename(out)}
    if not sys.platform.startswith("win"):
        raise ValueError("Scannen geht nur unter Windows (Windows-Scanschnittstelle WIA).")
    if not M24_LOCK.acquire(blocking=False):
        raise ValueError("Das Scanfenster ist schon offen.")
    try:
        script = M24_PS.replace("__INTENT__", str(M24_INTENT.get(d.get("modus") or "farbe", 1))).replace("__FMT__", M24_FORMAT_JPEG) \
            .replace("__OUT__", out.replace("'", "''"))
        ps1 = os.path.join(sd, "_scan.ps1")
        with open(ps1, "w", encoding="utf-8-sig") as f:
            f.write(script)
        flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            r = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", ps1],
                               capture_output=True, text=True, timeout=M24_TIMEOUT, creationflags=flags)
        except subprocess.TimeoutExpired:
            raise ValueError("Der Scanner hat nicht rechtzeitig geantwortet.")
        except FileNotFoundError:
            raise ValueError("PowerShell wurde nicht gefunden - Scannen nicht möglich.")
        finally:
            try:
                os.remove(ps1)
            except OSError:
                pass
        txt = (r.stdout or "").strip().splitlines()
        last = txt[-1] if txt else (r.stderr or "").strip()[:200]
        if last.startswith("ABBRUCH"):
            return {"ok": True, "session": sid, "seiten": _m24_pages(sid), "abbruch": True}
        if last.startswith("KEINSCANNER"):
            raise ValueError("Kein Scanner gefunden. Ist er eingeschaltet und in Windows (Geräte und Drucker) eingerichtet?")
        if last.startswith("KEINWIA"):
            raise ValueError("Die Windows-Scanschnittstelle (WIA) ist auf diesem PC nicht verfügbar.")
        if not last.startswith("OK") or not os.path.isfile(out):
            raise ValueError("Scannen fehlgeschlagen: " + (last[7:] if last.startswith("FEHLER") else last or "keine Antwort")[:200])
    finally:
        M24_LOCK.release()
    return {"ok": True, "session": sid, "seiten": _m24_pages(sid), "neu": os.path.basename(out)}


def m24_remove(d):
    sid = _m24_sid(d.get("session"))
    fn = str(d.get("seite") or "")
    if not re.fullmatch(r"p\d{3}\.(jpg|png)", fn):
        raise ValueError("Ungültige Seite.")
    fp = os.path.join(_m24_dir(sid), fn)
    if os.path.isfile(fp):
        os.remove(fp)
    return {"ok": True, "session": sid, "seiten": _m24_pages(sid)}


def m24_discard(d):
    try:
        shutil.rmtree(_m24_dir(d.get("session")), ignore_errors=True)
    except ValueError:
        pass
    return {"ok": True}


def m24_pdf(sid, only=None):
    """all pages of the session (or only the given page) -> one PDF (bytes); pages keep their size (A4 scan stays A4)"""
    from PIL import Image
    pages = _m24_pages(sid)
    if only:
        pages = [p_ for p_ in pages if p_ == only]
    if not pages:
        raise ValueError("Noch keine Seite gescannt.")
    ims = []
    dpi = 200
    for fn in pages:
        im = Image.open(os.path.join(_m24_dir(sid), fn))
        try:
            dpi = int(round((im.info.get("dpi") or (dpi, dpi))[0])) or dpi
        except Exception:
            pass
        im = im.convert("L") if im.mode in ("1", "L", "LA") else im.convert("RGB")
        # very large scans (e.g. 600 dpi colour) are reduced to 300 dpi to keep the PDF small
        if dpi > 300:
            f_ = 300 / dpi
            im = im.resize((max(1, int(im.width * f_)), max(1, int(im.height * f_))))
            dpi = 300
        ims.append(im)
    b = io.BytesIO()
    ims[0].save(b, "PDF", save_all=True, append_images=ims[1:], resolution=float(dpi or 200))
    return b.getvalue(), len(ims)


def m24_attach(d):
    """scan session -> PDF -> attachment of the document (same rules as /api/upload/anlage)"""
    sid = _m24_sid(d.get("session"))
    iid = int(d.get("invoice_id") or 0)
    if iid:
        li_ = q("SELECT locked FROM invoices WHERE id=?", (iid,), one=True)
        if not li_:
            raise ValueError("Dokument nicht gefunden.")
        if li_["locked"]:
            raise ValueError("Das Dokument ist festgeschrieben - Anlagen können nicht mehr geändert werden.")
    data, n = m24_pdf(sid)
    name = (d.get("name") or "").strip() or ("Scan_" + datetime.datetime.now().strftime("%Y-%m-%d_%H%M"))
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)[:120]
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    tmp = os.path.join(_m24_dir(sid), "_out.pdf")
    with open(tmp, "wb") as f:
        f.write(data)
    rel = store_upload(tmp, name, "Anlagen")
    bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("anlage", today(), name, "", 0, "", f"Scan ({n} Seite{'n' if n != 1 else ''})", rel, json.dumps({"scan": True, "seiten": n}), iid or None, now_iso()))
    shutil.rmtree(_m24_dir(sid), ignore_errors=True)
    return {"ok": True, "id": bid, "file": rel, "partner": name, "seiten": n}


def _m24_name(d, prefix="Scan"):
    name = (d.get("name") or "").strip() or (prefix + "_" + datetime.datetime.now().strftime("%Y-%m-%d_%H%M"))
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)[:120]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return name


def m24_beleg(d):
    """scan session -> PDF(s) -> same recognition as a dropped file in Belege & Import (review queue)"""
    sid = _m24_sid(d.get("session"))
    pages = _m24_pages(sid)
    if not pages:
        raise ValueError("Noch keine Seite gescannt.")
    base = _m24_name(d, "Beleg_Scan")
    groups = [[p_] for p_ in pages] if d.get("einzeln") and len(pages) > 1 else [None]
    items = []
    for i, g in enumerate(groups, 1):
        data, n = m24_pdf(sid, g[0] if g else None)
        name = base + (f"_{i:02d}" if len(groups) > 1 else "") + ".pdf"
        tmp = os.path.join(DATA_DIR, "_tmp_" + uuid.uuid4().hex + ".pdf")
        with open(tmp, "wb") as f:
            f.write(data)
        try:
            items += prepare_results(analyze_any(tmp, name), tmp, name)
        except Exception as e:
            traceback.print_exc()
            items.append({"error": f"{name}: {e}"})
    shutil.rmtree(_m24_dir(sid), ignore_errors=True)
    return {"ok": True, "items": items, "belege": len(groups)}


def _m24_thumb(h, qs):
    from PIL import Image
    sid = _m24_sid(qs.get("session"))
    fn = str(qs.get("seite") or "")
    if not re.fullmatch(r"p\d{3}\.(jpg|png)", fn):
        return h._send(404, b"", "text/plain")
    fp = os.path.join(_m24_dir(sid), fn)
    if not os.path.isfile(fp):
        return h._send(404, b"", "text/plain")
    im = Image.open(fp)
    im.thumbnail((320, 440))
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=80)
    return h._send(200, b.getvalue(), "image/jpeg")


def _m24_cleanup():
    try:
        if os.path.isdir(M24_DIR):
            for fn in os.listdir(M24_DIR):
                p = os.path.join(M24_DIR, fn)
                if os.path.isdir(p) and time.time() - os.path.getmtime(p) > 2 * 86400:
                    shutil.rmtree(p, ignore_errors=True)
    except Exception:
        traceback.print_exc()


HOOK_POST["/api/scan/page"] = lambda h, d: h._send(200, m24_scan_page(d))
HOOK_POST["/api/scan/remove"] = lambda h, d: h._send(200, m24_remove(d))
HOOK_POST["/api/scan/discard"] = lambda h, d: h._send(200, m24_discard(d))
HOOK_POST["/api/scan/attach"] = lambda h, d: h._send(200, m24_attach(d))
HOOK_POST["/api/scan/beleg"] = lambda h, d: h._send(200, m24_beleg(d))
HOOK_GET["/api/scan/thumb"] = _m24_thumb
HOOK_START.append(_m24_cleanup)
HOOK_BOOT.append(lambda d: d.update(scanner=sys.platform.startswith("win") or bool(os.environ.get("PA_SCAN_TEST_IMAGE"))))


def m24_selftest():
    err = []
    try:
        from PIL import Image
        sid = uuid.uuid4().hex[:16]
        sd = _m24_dir(sid)
        os.makedirs(sd, exist_ok=True)
        Image.new("RGB", (1654, 2339), "white").save(os.path.join(sd, "p001.jpg"), dpi=(200, 200))
        Image.new("L", (1654, 2339), 200).save(os.path.join(sd, "p002.jpg"), dpi=(200, 200))
        data, n = m24_pdf(sid)
        if n != 2 or not data.startswith(b"%PDF"):
            err.append("m24: PDF aus Scan-Seiten falsch")
        r = m24_attach({"session": sid, "invoice_id": 0, "name": "Test"})
        b = q("SELECT * FROM belege WHERE id=?", (r["id"],), one=True)
        if not b or b["typ"] != "anlage" or not os.path.isfile(os.path.join(DATA_DIR, b["file"])) or os.path.isdir(sd):
            err.append("m24: Scan nicht als Anlage gespeichert")
        sid2 = uuid.uuid4().hex[:16]
        os.makedirs(_m24_dir(sid2), exist_ok=True)
        for i in (1, 2):
            Image.new("L", (800, 1100), 255).save(os.path.join(_m24_dir(sid2), f"p{i:03d}.jpg"), dpi=(150, 150))
        rb = m24_beleg({"session": sid2, "name": "Test", "einzeln": True})
        if rb.get("belege") != 2 or not isinstance(rb.get("items"), list) or os.path.isdir(_m24_dir(sid2)):
            err.append(f"m24: Beleg-Scan falsch ({rb.get('belege')})")
        for it in rb.get("items") or []:
            tp = it.get("tmp") if isinstance(it, dict) else None
            if tp and os.path.isfile(tp):
                try:
                    os.remove(tp)
                except OSError:
                    pass
        try:
            _m24_sid("../x")
            err.append("m24: ungültige Sitzung akzeptiert")
        except ValueError:
            pass
    except Exception as e:
        err.append(f"m24 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m24_selftest)
print(f"INIT m24_scanner v{M24_VERSION}")
