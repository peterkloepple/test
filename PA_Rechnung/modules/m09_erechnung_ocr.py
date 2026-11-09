# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m09_erechnung_ocr
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ---------------- E-Rechnung (XRechnung / ZUGFeRD) ----------------


def _ln(tag):
    return tag.split("}")[-1]


def _child(el, name):
    if el is None:
        return None
    for c in el:
        if _ln(c.tag) == name:
            return c
    return None


def _path(el, path):
    for p in path.split("/"):
        el = _child(el, p)
        if el is None:
            return None
    return el


def _txt(el, path=None):
    e = _path(el, path) if path else el
    return (e.text or "").strip() if e is not None and e.text else ""


def _num(v):
    try:
        return float((v or "0").replace(",", "."))
    except Exception:
        return 0.0


def parse_einvoice_xml(data):
    root = ET.fromstring(data)
    kind = _ln(root.tag)
    info = {"format": "", "nr": "", "datum": "", "partner": "", "betrag": 0.0, "waehrung": "EUR", "items": [], "kaeufer": ""}
    if kind in ("CrossIndustryInvoice", "CrossIndustryDocument"):
        # v2.1.0: also ZUGFeRD 1.0 (CrossIndustryDocument, used until 2019) - same data, older element names
        v1 = kind == "CrossIndustryDocument"
        info["format"] = "ZUGFeRD 1.0 (CII)" if v1 else "ZUGFeRD / Factur-X / XRechnung (CII)"
        hd = "HeaderExchangedDocument" if v1 else "ExchangedDocument"
        info["nr"] = _txt(root, hd + "/ID")
        dt = _txt(root, hd + "/IssueDateTime/DateTimeString")
        if re.match(r"^\d{8}$", dt):
            d_ = d_iso(f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}")     # v2.6.3: only a real calendar date
            info["datum"] = d_.isoformat() if d_ else ""
        tr = _child(root, "SpecifiedSupplyChainTradeTransaction" if v1 else "SupplyChainTradeTransaction")
        ag = _child(tr, "ApplicableSupplyChainTradeAgreement" if v1 else "ApplicableHeaderTradeAgreement")
        info["partner"] = _txt(ag, "SellerTradeParty/Name")
        info["kaeufer"] = _txt(ag, "BuyerTradeParty/Name")
        se = _child(tr, "ApplicableSupplyChainTradeSettlement" if v1 else "ApplicableHeaderTradeSettlement")
        st = _child(se, "SpecifiedTradeSettlementMonetarySummation" if v1 else "SpecifiedTradeSettlementHeaderMonetarySummation")
        info["betrag"] = _num(_txt(st, "GrandTotalAmount")) or _num(_txt(st, "DuePayableAmount"))
        info["gutschrift"] = _txt(root, hd + "/TypeCode") in ("381", "261")
        info["waehrung"] = _txt(se, "InvoiceCurrencyCode") or "EUR"
        ln_ = ("SpecifiedSupplyChainTrade" if v1 else "SpecifiedLineTrade")
        for li in (list(tr) if tr is not None else []):
            if _ln(li.tag) != "IncludedSupplyChainTradeLineItem":
                continue
            info["items"].append({"name": _txt(li, "SpecifiedTradeProduct/Name"),
                                  "qty": _num(_txt(li, ln_ + "Delivery/BilledQuantity")),
                                  "price": _num(_txt(li, ln_ + "Agreement/NetPriceProductTradePrice/ChargeAmount")),
                                  "total": _num(_txt(li, ln_ + "Settlement/" + ("SpecifiedTradeSettlementMonetarySummation" if v1 else
                                                                               "SpecifiedTradeSettlementLineMonetarySummation") + "/LineTotalAmount"))})
    elif kind in ("Invoice", "CreditNote"):
        info["format"] = "XRechnung (UBL)" + (" Gutschrift" if kind == "CreditNote" else "")
        info["nr"] = _txt(root, "ID")
        d_ = d_iso(_txt(root, "IssueDate"))     # v2.6.3: only a real calendar date
        info["datum"] = d_.isoformat() if d_ else ""
        sp = _path(root, "AccountingSupplierParty/Party")
        info["partner"] = _txt(sp, "PartyName/Name") or _txt(sp, "PartyLegalEntity/RegistrationName")
        bp = _path(root, "AccountingCustomerParty/Party")
        info["kaeufer"] = _txt(bp, "PartyName/Name") or _txt(bp, "PartyLegalEntity/RegistrationName")
        info["betrag"] = _num(_txt(root, "LegalMonetaryTotal/TaxInclusiveAmount")) or _num(_txt(root, "LegalMonetaryTotal/PayableAmount"))
        info["gutschrift"] = kind == "CreditNote"
        info["waehrung"] = _txt(root, "DocumentCurrencyCode") or "EUR"
        for li in root:
            if _ln(li.tag) not in ("InvoiceLine", "CreditNoteLine"):
                continue
            info["items"].append({"name": _txt(li, "Item/Name"),
                                  "qty": _num(_txt(li, "InvoicedQuantity") or _txt(li, "CreditedQuantity")),
                                  "price": _num(_txt(li, "Price/PriceAmount")), "total": _num(_txt(li, "LineExtensionAmount"))})
    else:
        return None
    return info


def pdf_embedded_xml(path, pw=None):
    """-> (info, xml_bytes, used_password) or None. v2.1.0: opens password protected PDFs with the entered,
    the standard or a saved password (before, a protected ZUGFeRD PDF was only read as text)"""
    if not pypdf:
        return None
    try:
        try:
            r, used = pdf_open(path, pw)
        except PasswordNeeded:
            return None
        for name, blobs in (r.attachments or {}).items():
            if name.lower().endswith(".xml"):
                for b in blobs:
                    try:
                        info = parse_einvoice_xml(b)
                        if info:
                            return info, b, used
                    except Exception:
                        continue
    except Exception:
        pass
    return None


def einvoice_view_pdf(info):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"E-Rechnung {info['nr']}")
    ss = font_stylesheet()
    el = [Paragraph(f"<b>E-Rechnung {esc_xml(info['nr'])}</b>", ss["Title"]),
          Paragraph(f"Format: {esc_xml(info['format'])}<br/>Rechnungssteller: {esc_xml(info['partner'])}<br/>"
                    f"Empfänger: {esc_xml(info['kaeufer'])}<br/>Datum: {de_date(info['datum'])}", ss["Normal"]), Spacer(1, 8)]
    rows = [["Position", "Menge", "Preis", "Summe"]] + [[(i["name"] or "")[:60], num_de(i["qty"], 2), num_de(i["price"], 2), num_de(i["total"], 2)] for i in info["items"]]
    rows.append(["Zahlbetrag", "", "", f"{num_de(info['betrag'], 2)} {info['waehrung']}"])
    t = Table(rows, colWidths=[95 * mm, 22 * mm, 25 * mm, 30 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), FONT_B(), 9), ("FONT", (0, 1), (-1, -1), FONT_R(), 9),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black), ("FONT", (0, -1), (-1, -1), FONT_B(), 9),
                           ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    el.append(t)
    el.append(Spacer(1, 10))
    el.append(Paragraph("Sichtansicht automatisch aus den XML-Daten erzeugt. Maßgeblich ist die XML-Datei.", ss["Italic"]))
    doc.build(el)
    return buf.getvalue()


def esc_xml(v):
    return (str(v or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def einvoice_result(info, s):
    own = (s.get("firma") or "").lower()
    res = {"typ": "ausgabe", "confidence": 1.0, "datum": info["datum"], "partner": info["partner"], "nr": info["nr"],
           "betrag": abs(info["betrag"]), "kategorie": guess_category(info["partner"] + " " + " ".join(i["name"] for i in info["items"])),
           "details": {"einvoice": info}, "hint": f"E-Rechnung erkannt ({info['format']}) - Werte exakt aus den XML-Daten."}
    if info.get("gutschrift"):
        res["typ"] = "einnahme"
        res["hint"] += " Gutschrift eines Lieferanten - als Einnahme (Erstattung) vorgeschlagen."
    cur = (info.get("waehrung") or "EUR").upper()
    if cur != "EUR":
        # v2.1.0: a foreign currency amount was booked 1:1 as Euro (and even automatically from the inbox)
        res["confidence"] = 0.6
        res.setdefault("warnungen", []).append(f"E-Rechnung in {cur} ({num_de(abs(info['betrag']), 2)} {cur}) – das Programm rechnet in Euro: "
                                               "bitte den Euro-Betrag (Kontoauszug) eintragen.")
    if own and own in (info["partner"] or "").lower():
        res["typ"] = "einnahme"
        # v2.0.6: own invoice re-imported -> never auto-book (would count the revenue twice)
        # v2.1.0: the reasons are warnings now - assist() kept the 0.97 of an e-invoice and the inbox booked it automatically
        ex = q("SELECT id FROM invoices WHERE nr=?", (info.get("nr") or "",), one=True) if info.get("nr") else None
        if ex:
            res["confidence"] = 0.3
            res.setdefault("warnungen", []).append(f"Eigene Rechnung {info['nr']} ist schon im Programm - nicht als Einnahme buchen (sonst doppelt).")
            res["hint"] += f" Das ist deine eigene Rechnung {info['nr']}, sie ist schon im Programm erfasst - bitte verwerfen."
        else:
            res["confidence"] = 0.6
            res.setdefault("warnungen", []).append("Rechnungssteller ist deine eigene Firma – bitte prüfen, ob das eine eigene Ausgangsrechnung ist.")
            res["hint"] += " Rechnungssteller ist {0} - als Einnahme vorgeschlagen (bitte pruefen, ob es eine eigene Rechnung ist).".format(s.get("firma"))
    return res

# ---------------- OCR (Windows) ----------------
# v2.6.7: two ways to the Windows text recognition (Windows.Media.Ocr):
#  1. Python package winrt (requirements_ocr.txt) - runs in its own thread with MTA apartment
#     (the HTTP worker threads / the STA window thread made calls fail before)
#  2. fallback without any package: PowerShell 5.1 loads the same WinRT classes (works on every Windows 10/11)
# The last error is kept (OCR_LAST) and shown in the hint, the settings test shows which way works.
# Phone photos are turned upright (EXIF), small images are enlarged, HEIC goes directly to the Windows decoder.

import tempfile
OCR_LAST = {"weg": "", "fehler": ""}
_OCR_STATE = {"winrt": None, "ps": None}
OCR_MAX_PAGES = 3

OCR_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
  $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
  $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
  $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
  $m = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
  function Await($op, $t) { $task = $m.MakeGenericMethod($t).Invoke($null, @($op)); $null = $task.Wait(-1); $task.Result }
  $eng = $null
  try { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('de-DE')) } catch {}
  if ($eng -eq $null) { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
  if ($eng -eq $null) { Write-Output '##KEINESPRACHE'; exit 0 }
  $max = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
  foreach ($p in (Get-Content -LiteralPath '__LIST__' -Encoding UTF8)) {
    if (-not $p) { continue }
    $f = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
    $st = Await ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
      $dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($st)) ([Windows.Graphics.Imaging.BitmapDecoder])
      if ($dec.PixelWidth -gt $max -or $dec.PixelHeight -gt $max) {
        $sc = [Math]::Min($max / $dec.PixelWidth, $max / $dec.PixelHeight)
        $tr = [Windows.Graphics.Imaging.BitmapTransform]::new()
        $tr.ScaledWidth = [uint32]([Math]::Floor($dec.PixelWidth * $sc)); $tr.ScaledHeight = [uint32]([Math]::Floor($dec.PixelHeight * $sc))
        $bmp = Await ($dec.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied, $tr, [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation, [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
      } else {
        $bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
      }
      $res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
      foreach ($l in $res.Lines) { Write-Output $l.Text }
    } finally { $st.Dispose() }
    Write-Output '##SEITE'
  }
} catch {
  Write-Output ('##FEHLER ' + $_.Exception.Message)
}
"""


def _ocr_winrt_ok():
    if _OCR_STATE["winrt"] is None:
        try:
            import winrt.windows.media.ocr  # noqa
            _OCR_STATE["winrt"] = True
        except Exception as e:
            _OCR_STATE["winrt"] = False
            OCR_LAST["winrt_import"] = str(e)[:200]
    return _OCR_STATE["winrt"]


def ocr_available():
    if os.environ.get("PA_OCR_TEST"):          # tests only
        return True
    if not sys.platform.startswith("win"):
        return False
    if _ocr_winrt_ok():
        return True
    if _OCR_STATE["ps"] is None:
        _OCR_STATE["ps"] = bool(shutil.which("powershell.exe") or shutil.which("powershell"))
    return _OCR_STATE["ps"]


def _ocr_winrt(png):
    """Python winrt way - executed in a fresh thread (own MTA apartment, no running event loop)"""
    import asyncio
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

    async def run():
        stream = InMemoryRandomAccessStream()
        w = DataWriter(stream)
        try:
            w.write_bytes(png)
        except TypeError:
            w.write_bytes(list(png))
        await w.store_async()
        await w.flush_async()
        w.detach_stream()
        stream.seek(0)
        dec = await BitmapDecoder.create_async(stream)
        bmp = await dec.get_software_bitmap_async()
        eng = None
        try:
            eng = OcrEngine.try_create_from_language(Language("de-DE"))
        except Exception:
            eng = None
        eng = eng or OcrEngine.try_create_from_user_profile_languages()
        if eng is None:
            raise RuntimeError("KEINESPRACHE")
        res = await eng.recognize_async(bmp)
        return "\n".join(l.text for l in res.lines)

    out = {}

    def worker():
        try:
            try:
                import winrt
                if hasattr(winrt, "init_apartment"):
                    winrt.init_apartment(getattr(winrt, "MTA", 0))
            except Exception:
                pass
            out["t"] = asyncio.run(run())
        except Exception as e:
            out["e"] = e

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(120)
    if th.is_alive():
        raise RuntimeError("Texterkennung antwortet nicht (Zeitüberschreitung).")
    if "e" in out:
        raise out["e"]
    return out.get("t", "")


def _ocr_ps(files):
    """PowerShell way: list of image files (png/jpg/heic/tif) -> list of page texts"""
    d = tempfile.mkdtemp(prefix="pa_ocr_")
    try:
        lst = os.path.join(d, "liste.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(os.path.abspath(p_) for p_ in files))
        ps1 = os.path.join(d, "ocr.ps1")
        with open(ps1, "w", encoding="utf-8-sig") as f:
            f.write(OCR_PS.replace("__LIST__", lst.replace("'", "''")))
        flags = 0x08000000 if sys.platform.startswith("win") else 0
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
                           capture_output=True, timeout=180, creationflags=flags)
        out = (r.stdout or b"").decode("utf-8", "replace").replace("\ufeff", "")
        if "##KEINESPRACHE" in out:
            raise RuntimeError("KEINESPRACHE")
        m = re.search(r"##FEHLER (.*)", out)
        if m:
            raise RuntimeError(m.group(1).strip()[:300])
        if "##SEITE" not in out:
            err = (r.stderr or b"").decode("utf-8", "replace").strip()
            raise RuntimeError(("PowerShell: " + err[:300]) if err else "PowerShell lieferte kein Ergebnis.")
        return [t.strip() for t in out.split("##SEITE")[:-1]]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _ocr_reason(e):
    t = str(e)
    if "KEINESPRACHE" in t:
        return "Keine Texterkennungs-Sprache installiert (Windows-Einstellungen → Zeit und Sprache → Sprache → Deutsch → Optionen → Texterkennung/OCR hinzufügen)."
    return t[:300]


def _ocr_images(path, pw=None, max_pages=None):
    """file -> list of PNG bytes (PDF: first pages, image: upright + suitable size)"""
    from PIL import Image, ImageOps
    pngs = []
    low = path.lower()
    if low.endswith(".pdf"):
        if not pdfium:
            raise RuntimeError("PDF-Bibliothek (pypdfium2) fehlt.")
        with PDFIUM_LOCK:     # v3.6.1: pdfium is not thread safe
            doc = pdfium.PdfDocument(path, password=pw) if pw else pdfium.PdfDocument(path)
            try:
                for i in range(min(len(doc), max_pages or OCR_MAX_PAGES)):
                    pg = doc[i]
                    w_pt = max(1.0, pg.get_width())
                    # about 300 dpi for A4, small receipts get more (max 4000 px wide)
                    sc = min(max(2480.0 / w_pt, 2.6), 4000.0 / w_pt, 8.0)
                    im = pg.render(scale=sc).to_pil()
                    b = io.BytesIO()
                    im.convert("RGB").save(b, "PNG")
                    pngs.append(b.getvalue())
            finally:
                doc.close()
    else:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)          # phone photos: turn upright
        if max(im.size) < 1600:                  # small images: enlarge, OCR needs about 20 px per letter
            f_ = 1600 / max(im.size)
            im = im.resize((int(im.width * f_), int(im.height * f_)), Image.LANCZOS)
        im.thumbnail((4000, 4000))
        b = io.BytesIO()
        im.convert("RGB").save(b, "PNG")
        pngs.append(b.getvalue())
    return pngs


def ocr_png(png):
    """one PNG -> text (winrt, else PowerShell)"""
    return ocr_pngs([png])


def ocr_pngs(pngs):
    errs = []
    if os.environ.get("PA_OCR_TEST"):          # tests only: fixed text
        OCR_LAST.update(weg="Test", fehler="")
        return os.environ.get("PA_OCR_TEST")
    if _ocr_winrt_ok():
        try:
            t = "\n".join(_ocr_winrt(p_) for p_ in pngs)
            OCR_LAST.update(weg="Python (winrt)", fehler="")
            return t
        except Exception as e:
            errs.append(e)
    d = tempfile.mkdtemp(prefix="pa_ocrp_")
    try:
        files = []
        for i, p_ in enumerate(pngs):
            fp = os.path.join(d, f"s{i:02d}.png")
            with open(fp, "wb") as f:
                f.write(p_)
            files.append(fp)
        try:
            t = "\n".join(_ocr_ps(files))
            OCR_LAST.update(weg="PowerShell", fehler="")
            return t
        except Exception as e:
            errs.append(e)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    OCR_LAST.update(weg="", fehler=" / ".join(_ocr_reason(e) for e in errs))
    traceback.print_exc()
    raise RuntimeError(OCR_LAST["fehler"])


def ocr_file(path, pw=None, max_pages=None):
    OCR_LAST.update(weg="", fehler="")
    low = path.lower()
    try:
        pngs = _ocr_images(path, pw, max_pages)
    except Exception as e:
        # e.g. HEIC (Pillow cannot read it): the Windows decoder can, give it the file directly
        if low.endswith((".heic", ".heif")) and sys.platform.startswith("win"):
            try:
                t = "\n".join(_ocr_ps([path]))
                OCR_LAST.update(weg="PowerShell", fehler="")
                return t
            except Exception as e2:
                OCR_LAST["fehler"] = _ocr_reason(e2)
                raise
        OCR_LAST["fehler"] = "Datei konnte nicht gelesen werden: " + str(e)[:200]
        raise
    return ocr_pngs(pngs)


def ocr_need(text):
    """v2.6.7: scanner PDFs often hold a few stray characters (page number, scanner name) - then OCR anyway"""
    return len(re.sub(r"[\W_]+", "", text or "")) < 25


def ocr_test():
    """settings: test image with known text -> which way works, what was read"""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1600, 500), "white")
    dr = ImageDraw.Draw(im)
    font = None
    for fn in ("arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(fn, 64)
            break
        except Exception:
            continue
    dr.text((60, 80), "Rechnung Nr. 4711", fill="black", font=font)
    dr.text((60, 240), "Gesamtbetrag 123,45 EUR", fill="black", font=font)
    b = io.BytesIO()
    im.save(b, "PNG")
    info = {"windows": sys.platform.startswith("win"), "winrt": bool(sys.platform.startswith("win") and _ocr_winrt_ok()),
            "winrt_fehler": OCR_LAST.get("winrt_import", ""), "verfuegbar": ocr_available()}
    if not info["verfuegbar"]:
        return dict(info, ok=False, fehler="Texterkennung gibt es nur unter Windows 10/11.")
    try:
        t = ocr_png(b.getvalue())
    except Exception as e:
        return dict(info, ok=False, fehler=_ocr_reason(e), weg="")
    ok = "4711" in t and "123" in t
    return dict(info, ok=ok, text=t[:300], weg=OCR_LAST.get("weg"),
                fehler="" if ok else "Text wurde nicht richtig erkannt.")


HOOK_POST["/api/ocr/test"] = lambda h, d: h._send(200, ocr_test())


def m09_ocr_selftest():
    err = []
    try:
        from PIL import Image
        if not ocr_need("  \x0c 1 ") or ocr_need("Rechnung Nr 4711 Gesamtbetrag 123,45 EUR Datum 01.02.2026"):
            err.append("m09: ocr_need falsch")
        d = tempfile.mkdtemp(prefix="pa_ocrst_")
        try:
            small = os.path.join(d, "k.jpg")
            Image.new("RGB", (400, 900), "white").save(small)
            pngs = _ocr_images(small)
            im = Image.open(io.BytesIO(pngs[0]))
            if max(im.size) < 1600:
                err.append("m09: kleines Bild nicht vergroessert")
            pdf = os.path.join(d, "s.pdf")
            Image.new("RGB", (800, 1100), "white").save(pdf, "PDF", save_all=True,
                                                         append_images=[Image.new("RGB", (800, 1100), "white") for _ in range(5)], resolution=100.0)
            if pdfium and len(_ocr_images(pdf, None, 12)) != 6:
                err.append("m09: OCR liest nicht alle Seiten")
        finally:
            shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        err.append(f"m09 OCR Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m09_ocr_selftest)
