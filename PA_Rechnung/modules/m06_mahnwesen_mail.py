# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m06_mahnwesen_mail
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# v1.1.0 extensions
# ----------------------------------------------------------------------------
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
             "November", "Dezember"]
MAHN_TITLES = ["Zahlungserinnerung", "1. Mahnung", "2. Mahnung", "Letzte Mahnung"]


def d_iso(v):
    try:
        return datetime.date.fromisoformat((v or "")[:10])
    except Exception:
        return None


def add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return datetime.date(y, m, min(d.day, last))


def month_title(title, d):
    pat = r"(?i)(^|\s)(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Jan|Feb|Mär|Apr|Jun|Jul|Aug|Sept?|Okt|Nov|Dez)\.?(?=\s|$)"
    if re.search(pat, title or ""):
        return re.sub(pat, lambda m: m.group(1) + MONTHS_DE[d.month - 1], title, count=1)
    return title

# ---------------- Mahnwesen ----------------


def overdue_list():
    out = []
    t = datetime.date.today()
    for r in q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen'"):
        d0 = d_iso(r["datum"])
        if not d0:
            continue
        due = d0 + datetime.timedelta(days=_frist(r["frist"]))
        if due < t:
            r["faellig"] = due.isoformat()
            r["tage"] = (t - due).days
            r["name"] = inv_name(r)
            out.append(r)
    return sorted(out, key=lambda r: -r["tage"])


# create_mahnung(): definiert in m72_mahnlauf (v2.1.0: alte, nie benutzte Fassung entfernt)

# ---------------- E-Mail ----------------


def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    bin_ = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    bout = BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if protect:
        ok = fn(ctypes.byref(bin_), "PA_Rechnung", None, None, None, 0, ctypes.byref(bout))
    else:
        ok = fn(ctypes.byref(bin_), None, None, None, None, 0, ctypes.byref(bout))
    if not ok:
        raise OSError("DPAPI failed")
    res = ctypes.string_at(bout.pbData, bout.cbData)
    ctypes.windll.kernel32.LocalFree(bout.pbData)
    return res


# protect_secret(): definiert in m66_geheimnisse (v2.1.0: alte, nie benutzte Fassung entfernt)


# unprotect_secret(): definiert in m66_geheimnisse (v2.1.0: alte, nie benutzte Fassung entfernt)


def mail_fill(text, inv, title):
    c = q("SELECT * FROM customers WHERE id=?", (inv.get("customer_id"),), one=True) if inv.get("customer_id") else None
    return (text or "").replace("[Dokument]", title).replace("[Nummer]", inv.get("nr", "")) \
        .replace("[Betrag]", money(inv.get("summe") or 0)).replace("[Name]", (c["name"] or c["firma"]) if c else "") \
        .replace("[Inhaber]", get_settings().get("inhaber") or "").replace("[Firma]", get_settings().get("firma") or "") \
        .replace("\\n", "\n")


def mail_prepare(doc_id=None, mahnung_id=None):
    s = get_settings()
    if mahnung_id:
        m = q("SELECT * FROM mahnungen WHERE id=?", (mahnung_id,), one=True)
        inv = get_invoice(m["invoice_id"])
        title = MAHN_TITLES[min(m["stufe"], 3)] + " zu Rechnung"
        fname = os.path.basename(m["file"])
    else:
        inv = get_invoice(doc_id)
        title = DOC_TYPES.get(inv["typ"], DOC_TYPES["rechnung"])["title"]
        fname = os.path.basename(invoice_pdf_path(inv, s))
    c = q("SELECT * FROM customers WHERE id=?", (inv.get("customer_id"),), one=True) if inv.get("customer_id") else None
    return {"to": (c["mail"] if c else "") or "", "cc": "", "subject": mail_fill(s["mail_subject"], inv, title),
            "body": mail_fill(s["mail_body"], inv, title), "attachment": fname,
            "configured": bool(s.get("smtp_host") and s.get("smtp_user") and s.get("smtp_pass"))}


# send_mail(): definiert in m37_mail_plus (v2.1.0: alte, nie benutzte Fassung entfernt)


# mail_send(): definiert in m37_mail_plus (v2.1.0: alte, nie benutzte Fassung entfernt)
