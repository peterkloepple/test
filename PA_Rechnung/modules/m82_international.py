# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m82_international (v2.0.19)
# Englische Dokumente und Fremdwaehrung je Kunde / je Dokument.
#  - Kunde: Sprache (de / en) und Waehrung (EUR, USD, GBP, CHF ...) als Vorgabe fuer neue Dokumente
#  - Dokument (Rechnung, Angebot, AB, Storno, Mahnung): Sprache, Waehrung, Kurs (EZB-Tageskurs oder manuell)
#  - PDF: alle festen Beschriftungen, Datums- und Zahlenformat, Kleinunternehmer-Hinweis, Standardtexte,
#    Mahnungstexte und Bausteine (englischer Name/Text je Baustein) in der Dokumentsprache.
#    Technik: der Quelltext von render_invoice_pdf (m02) wird beim Laden gelesen, feste deutsche
#    Beschriftungen werden durch L("...") ersetzt und als eigene Variante kompiliert. Diese Variante
#    wird NUR fuer Dokumente benutzt, die nicht Deutsch/EUR sind - deutsche Dokumente laufen
#    unveraendert ueber die bisherige Kette (m50 ZUGFeRD, m62 Schriften, evtl. m80).
#  - Fremdwaehrung: im Programm (Positionen, Summe, Statistik, EUER) bleibt alles in EUR. Das PDF
#    rechnet jede Position mit dem Kurs des Dokuments um und nennt den EUR-Gegenwert.
#    Fremdwaehrungsbetrag und Kurs liegen in der Tabelle m82_doc.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import contextlib
import urllib.request

M82_VERSION = "1.0.0"
M82_LANGS = {"de": "Deutsch", "en": "English"}
M82_CURS = ["EUR", "USD", "GBP", "CHF", "DKK", "SEK", "NOK", "PLN", "CZK", "HUF", "RON", "JPY", "CNY", "AUD", "CAD", "NZD",
            "SGD", "HKD", "TRY", "ZAR", "INR", "BRL", "MXN", "ILS", "KRW", "ISK"]
M82_ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
M82_MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# fixed PDF labels German -> English
M82_LBL_EN = {
    "Pos.": "Item", "Anzahl": "Qty", "Artikel": "Article", "Beschreibung": "Description", "Preis": "Unit price",
    "Rabatt": "Discount", "Gesamtpreis": "Amount", "Datum": "Date", "Gültig bis": "Valid until", "Seite": "Page",
    "Kunden-Nr.": "Customer no.", "Lieferdatum": "Delivery date", "Auftragsdatum": "Order date",
    "Übertrag:": "Carried forward:", "Übertrag": "Brought forward", "Gesamtbetrag:": "Total amount:",
    "Zahlbetrag": "Amount due", "Unsere Bankverbindung (IBAN)": "Our bank account (IBAN)",
    "Mit einem Klick per PayPal bezahlen": "Pay with one click via PayPal", "Zahlbetrag:": "Amount due:",
    "Empfänger:": "Recipient:", "Rechnungsdatum": "Invoice date", "Rechnung": "Invoice",
    "Rechnung Nr.": "Invoice no.", "Angebot Nr.": "Quotation no.", "Auftrag Nr.": "Order no.",
    "Storno-Rechnung": "Cancellation invoice", "Angebot": "Quotation", "Auftragsbestätigung": "Order confirmation",
    "Zahlungserinnerung": "Payment reminder", "1. Mahnung": "First reminder", "2. Mahnung": "Second reminder",
    "Letzte Mahnung": "Final reminder", "Mahngebühr": "Reminder fee", "Gegenwert": "Equivalent",
    "Nettobetrag:": "Net amount:", "zzgl. USt ": "plus VAT ", "USt 0 %:": "VAT 0 %:",
}
M82_KU_DE = "Kein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG"
M82_KU_EN = "VAT exempt under section 19 German VAT Act (UStG) - small business"

M82_TEXTE_EN = {
    "top_rechnung": "Thank you for your order! Please pay the amount within [Frist] days of the invoice date.",
    "foot_rechnung": M82_KU_EN,
    "top_angebot": "Thank you for your enquiry. We are pleased to offer you the following services:",
    "foot_angebot": "This quotation is valid until [Gueltig]. " + M82_KU_EN,
    "top_auftrag": "Thank you for your order. We hereby confirm the following services:",
    "foot_auftrag": M82_KU_EN,
    "top_storno": "We hereby cancel the following invoice.",
    "foot_storno": M82_KU_EN,
    "mahn_anrede": "Dear Sir or Madam,",
    "mahn_text": [
        "this may have escaped your attention: we have not yet received payment for the following invoice. Please transfer the outstanding amount by [Mahnfrist].",
        "unfortunately, despite our payment reminder, we have not yet received your payment. Please transfer the outstanding amount plus the reminder fee by [Mahnfrist].",
        "despite our reminder and first dunning letter, the following invoice is still unpaid. Please settle the total amount immediately, by [Mahnfrist] at the latest.",
        "this is our final reminder. If the total amount is not received by [Mahnfrist], we will take legal action without further notice."],
    "mahn_foot": "If you have already made the payment, please disregard this letter.",
    "mail_subject": "[Dokument] [Nummer] - [Firma]",
    "mail_body": "Dear Sir or Madam,\n\nplease find attached [Dokument] [Nummer] for [Betrag].\n\nKind regards\n[Inhaber]\n[Firma]",
}
# German sentences that are swapped for English ones in non-German documents (substring replace)
M82_SENT = [
    ("Dieses Angebot ist gültig bis [Gueltig].", "This quotation is valid until [Gueltig]."),
    ("Dieses Angebot ist gültig bis [Gültig].", "This quotation is valid until [Gueltig]."),
    (M82_KU_DE, M82_KU_EN),
    ("Kein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach § 19 UStG", M82_KU_EN),
    ("Kleinunternehmer nach § 19 UStG – kein Ausweis von Umsatzsteuer", M82_KU_EN),
    ("Betrag dankend erhalten.", "Amount received with thanks."),
    ("Bitte überweisen Sie den Betrag bis zum [Zahlungsfrist] auf unser Konto.", "Please transfer the amount to our account by [Zahlungsfrist]."),
    ("Sollten Sie die Zahlung bereits veranlasst haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.",
     "If you have already made the payment, please disregard this letter."),
]

_M82_TL = threading.local()
_M82_INTL = [None, ""]      # intl renderer (base renderer with English / currency formatter), error text


def _m82_schema():
    x("CREATE TABLE IF NOT EXISTS m82_kunde (customer_id INTEGER PRIMARY KEY, sprache TEXT DEFAULT 'de', waehrung TEXT DEFAULT 'EUR', "
      "updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m82_artikel (article_id INTEGER PRIMARY KEY, name_en TEXT, descr_en TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m82_doc (invoice_id INTEGER PRIMARY KEY, sprache TEXT DEFAULT 'de', waehrung TEXT DEFAULT 'EUR', "
      "kurs REAL DEFAULT 1, kurs_datum TEXT, kurs_quelle TEXT, betrag_fw REAL, betrag_eur REAL, updated TEXT)")


HOOK_SCHEMA.append(_m82_schema)


# ---------------------------------------------------------------------------
# context + formatting
# ---------------------------------------------------------------------------
def _m82_ctx():
    return getattr(_M82_TL, "ctx", None) or {"lang": "de", "cur": "EUR", "kurs": 1.0}


def _m82_lang():
    return _m82_ctx().get("lang") or "de"


def _m82_cur():
    return _m82_ctx().get("cur") or "EUR"


def m82_texte(lang="en"):
    t = dict(M82_TEXTE_EN)
    own = ((get_settings().get("m82_texte") or {}).get(lang) or {})
    for k, v in own.items():
        if k in t and v not in (None, "", []):
            t[k] = v
    return t


def L(s):
    if _m82_lang() == "en":
        own = (get_settings().get("m82_labels_en") or {})
        return own.get(s) or M82_LBL_EN.get(s, s)
    return s


def _m82_numfmt(v, dec=2, lang=None):
    lang = lang or _m82_lang()
    s = f"{v:,.{dec}f}"
    if lang == "de":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _m82_num(v, dec=2):
    return _m82_numfmt(v, dec)


def _m82_money(v, cur=None):
    v = float(v or 0)
    dec = 0 if (cur or _m82_cur()) in ("JPY", "KRW", "HUF", "ISK") and abs(v - round(v)) < 1e-9 else 2
    return ("-" if v < 0 else "") + _m82_numfmt(abs(v), dec) + " " + (cur or _m82_cur())


def _m82_date(iso, lang=None):
    lang = lang or _m82_lang()
    if not iso:
        return ""
    if lang != "en":
        return de_date(iso)
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
        return f"{d.day} {M82_MON_EN[d.month - 1]} {d.year}"
    except Exception:
        return str(iso)


def _m82_fill(text, inv, summe):
    frist = int(inv.get("frist")) if str(inv.get("frist", "")).strip() not in ("", "None") else 7
    try:
        dd = datetime.date.fromisoformat(inv.get("datum") or today())
    except Exception:
        dd = datetime.date.today()
    fdate = _m82_date((dd + datetime.timedelta(days=frist)).isoformat())
    gb = inv.get("gueltig_bis") or ""
    t = (text or "").replace("[Frist]", str(frist)).replace("[Zahlungsfrist]", fdate) \
        .replace("[Rechnungsnummer]", inv.get("nr", "")).replace("[Nummer]", inv.get("nr", "")) \
        .replace("[Betrag]", _m82_money(summe)).replace("[Gueltig]", _m82_date(gb)).replace("[Gültig]", _m82_date(gb)) \
        .replace("[Mahnfrist]", _m82_date(inv.get("_mahnfrist") or ""))
    if "[Skonto" in t:
        # m71 Skonto in document language and currency (summe is already in the document currency here)
        sk = None
        try:
            if "m71_skonto" in globals() and not inv.get("_mahnfrist"):
                sk = m71_skonto(dict(inv, summe=summe, typ=inv.get("typ") or "rechnung"))
        except Exception:
            sk = None
        if sk:
            pct = _m82_numfmt(sk["pct"], 2).rstrip("0").rstrip(".,")
            if _m82_lang() == "en":
                txt = (f"If paid by {_m82_date(sk['bis'])}, we grant a {pct} % early payment discount "
                       f"(amount payable {_m82_money(sk['betrag'])}).")
            else:
                txt = f"Bei Zahlung bis zum {_m82_date(sk['bis'])} gewähren wir {pct} % Skonto (Zahlbetrag {_m82_money(sk['betrag'])})."
            t = t.replace("[Skonto]", txt).replace("[Skontobetrag]", _m82_money(sk["betrag"])) \
                .replace("[Skontodatum]", _m82_date(sk["bis"])).replace("[Skontosatz]", pct + " %")
        else:
            t = re.sub(r"\[Skonto(betrag|datum|satz)?\]", "", t)
    if "[" in t:
        # remaining placeholders of other modules (e.g. m85 custom fields) - the normal chain leaves replaced text untouched
        try:
            t = fill_placeholders(t, inv, summe)
        except Exception:
            traceback.print_exc()
    return t


# ---------------------------------------------------------------------------
# build the international variant of render_invoice_pdf from the m02 source
# ---------------------------------------------------------------------------
M82_LITS = ["Pos.", "Anzahl", "Artikel", "Beschreibung", "Preis", "Rabatt", "Gesamtpreis", "Datum", "Gültig bis", "Seite",
            "Kunden-Nr.", "Lieferdatum", "Auftragsdatum", "Übertrag:", "Übertrag", "Gesamtbetrag:", "Zahlbetrag",
            "Unsere Bankverbindung (IBAN)", "Mit einem Klick per PayPal bezahlen", "Zahlbetrag:", "Empfänger:",
            "Nettobetrag:", "zzgl. USt ", "USt 0 %:"]
# v3.0.0: the base renderer of m02 has the hooks for language / currency natively (RENDER_TL.fmt);
# before, this module rebuilt render_invoice_pdf from the m02 source text (broke silently when m02 changed).
M82_FMT = {"L": lambda s_: L(s_), "money": lambda *a, **k: _m82_money(*a, **k), "num": lambda *a, **k: _m82_num(*a, **k),
           "date": lambda *a, **k: _m82_date(*a, **k), "fill": lambda t, inv, summe: _m82_fill(t, inv, summe), "cur": lambda: _m82_cur()}


def _m82_render_intl(inv, s=None, attachments=True):
    old = getattr(RENDER_TL, "fmt", None)
    RENDER_TL.fmt = M82_FMT
    try:
        return render_invoice_pdf_base(inv, s, attachments)
    finally:
        RENDER_TL.fmt = old


if "render_invoice_pdf_base" in globals():
    _M82_INTL[0] = _m82_render_intl
else:
    _M82_INTL[1] = "Basis-Renderer (m02) ohne Sprach-Schnittstelle"


# ---------------------------------------------------------------------------
# data access
# ---------------------------------------------------------------------------
def _m82_norm(d):
    d = d or {}
    lang = (d.get("sprache") or d.get("lang") or "de").lower()
    if lang not in M82_LANGS:
        lang = "de"
    cur = (d.get("waehrung") or d.get("cur") or "EUR").upper()
    if not re.fullmatch(r"[A-Z]{3}", cur):
        cur = "EUR"
    try:
        kurs = float(str(d.get("kurs") or 1).replace(",", "."))
    except Exception:
        kurs = 1.0
    if cur == "EUR" or kurs <= 0:
        kurs = 1.0
    return {"sprache": lang, "waehrung": cur, "kurs": kurs, "kurs_datum": d.get("kurs_datum") or "",
            "kurs_quelle": d.get("kurs_quelle") or ("" if cur == "EUR" else "manuell")}


def m82_kunde_get(cid):
    if not cid:
        return None
    try:
        return q("SELECT * FROM m82_kunde WHERE customer_id=?", (cid,), one=True)
    except sqlite3.OperationalError:     # table not yet created (seed runs before HOOK_SCHEMA)
        return None


def m82_doc_get(iid):
    if not iid:
        return None
    try:
        return q("SELECT * FROM m82_doc WHERE invoice_id=?", (iid,), one=True)
    except sqlite3.OperationalError:
        return None


def m82_doc_set(iid, d):
    n = _m82_norm(d)
    inv = q("SELECT locked FROM invoices WHERE id=?", (iid,), one=True)
    if not inv:
        return None
    old = m82_doc_get(iid)
    if inv["locked"]:
        return old          # issued documents keep language, currency and rate (GoBD: identical reprint) - also German/EUR ones
    if n["sprache"] == "de" and n["waehrung"] == "EUR":
        if old:
            x("DELETE FROM m82_doc WHERE invoice_id=?", (iid,))
        return None
    eur_, fw = _m82_amounts(iid, n["kurs"])
    x("INSERT OR REPLACE INTO m82_doc (invoice_id, sprache, waehrung, kurs, kurs_datum, kurs_quelle, betrag_fw, betrag_eur, updated) "
      "VALUES (?,?,?,?,?,?,?,?,?)", (iid, n["sprache"], n["waehrung"], n["kurs"], n["kurs_datum"], n["kurs_quelle"], fw, eur_, now_iso()))
    return m82_doc_get(iid)


def _m82_amounts(iid, kurs):
    its = q("SELECT * FROM items WHERE invoice_id=?", (iid,))
    eur_ = round(sum(float(i["total"] or 0) for i in its), 2)
    fw = 0.0
    by = {}
    for i in its:
        t_ = line_total({"qty": i["qty"], "price": round(float(i["price"] or 0) * kurs, 2), "rabatt": i["rabatt"]})
        fw += t_
        sz = i.get("ust_satz")
        by[sz] = by.get(sz, 0.0) + t_
    # m80 Regelbesteuerung: invoice total is gross -> foreign amount gross as well
    try:
        row = q("SELECT summe, ust_modus FROM invoices WHERE id=?", (iid,), one=True)
        if row and row.get("ust_modus") == "regel":
            fw = sum(round(n_, 2) + round(round(n_, 2) * float(s_ or 0) / 100.0, 2) for s_, n_ in by.items())
            eur_ = round(float(row["summe"] or 0), 2)
    except Exception:
        pass
    return eur_, round(fw, 2)


def m82_ctx_for(inv):
    """None = German / EUR (normal path)."""
    if not inv:
        return None
    m = inv.get("m82")
    if not isinstance(m, dict):
        m = m82_doc_get(inv.get("id")) if inv.get("id") and not inv.get("_m82_skip") else None
    if not m:
        return None
    n = _m82_norm(m)
    if n["sprache"] == "de" and n["waehrung"] == "EUR":
        return None
    return {"lang": n["sprache"], "cur": n["waehrung"], "kurs": n["kurs"], "kurs_datum": n["kurs_datum"], "kurs_quelle": n["kurs_quelle"]}


# ---------------------------------------------------------------------------
# ECB rates
# ---------------------------------------------------------------------------
def m82_ecb_rates(force=False):
    cache = get_settings().get("m82_kurse") or {}
    if not force and cache.get("geholt", "")[:10] == today() and cache.get("rates"):
        return cache
    try:
        req = urllib.request.Request(M82_ECB_URL, headers={"User-Agent": f"PA-Rechnung/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = r.read()
        root = ET.fromstring(data)
        rates, datum = {}, ""
        for el in root.iter():
            if el.tag.endswith("Cube"):
                if el.get("time"):
                    datum = el.get("time")
                if el.get("currency") and el.get("rate"):
                    rates[el.get("currency")] = float(el.get("rate"))
        if not rates:
            raise ValueError("keine Kurse in der Antwort")
        cache = {"datum": datum, "rates": rates, "geholt": now_iso()}
        set_setting("m82_kurse", cache)
        return cache
    except Exception as e:
        if cache.get("rates"):
            return dict(cache, warnung=f"EZB nicht erreichbar ({e}) - letzter Stand {de_date(cache.get('datum'))}")
        raise ValueError(f"EZB-Kurse nicht abrufbar ({e}). Kurs bitte von Hand eintragen.")


def m82_kurs(cur, force=False):
    cur = (cur or "EUR").upper()
    if cur == "EUR":
        return {"ok": True, "kurs": 1.0, "datum": today(), "quelle": ""}
    r = m82_ecb_rates(force)
    if cur not in r["rates"]:
        raise ValueError(f"Für {cur} veröffentlicht die EZB keinen Referenzkurs - bitte Kurs von Hand eintragen.")
    return {"ok": True, "kurs": r["rates"][cur], "datum": r.get("datum") or today(), "quelle": "EZB", "warnung": r.get("warnung", "")}


# ---------------------------------------------------------------------------
# prepare a document copy for the intl renderer
# ---------------------------------------------------------------------------
def _m82_swap_text(text, typ_key, lang):
    if lang != "en" or not text:
        return text
    s = get_settings()
    t = m82_texte("en")
    norm = lambda v: re.sub(r"\s+", " ", (v or "").strip())
    de_tops = {norm(s.get(k)) for k in ("default_top", "default_top_angebot", "default_top_auftrag")} | \
              {norm(r["text"]) for r in q("SELECT text FROM texts WHERE kind='top'")}
    de_foots = {norm(s.get(k)) for k in ("default_foot", "default_foot_angebot", "default_foot_auftrag")}
    n = norm(text)
    if typ_key.startswith("top") and n in de_tops:
        return t.get(typ_key) or text
    if typ_key.startswith("foot") and n in de_foots:
        return t.get(typ_key) or text
    for a, b in M82_SENT:
        text = text.replace(a, b)
    return text


def m82_prepare(inv, ctx):
    inv2 = dict(inv)
    lang, kurs = ctx["lang"], float(ctx.get("kurs") or 1)
    typ = inv.get("typ") or "rechnung"
    t = m82_texte("en")
    items = [dict(it) for it in (inv.get("items") or [])]
    eur_sum = round(sum(item_total(inv, it) for it in items), 2)
    if inv.get("_m82_regel"):
        try:
            eur_sum = m80_ust_block(inv)["brutto"]
        except Exception:
            pass
    # English article texts
    if lang == "en":
        aids = [it.get("article_id") for it in items if it.get("article_id")]
        if aids:
            arts = {r["id"]: r for r in q(f"SELECT id, name, descr FROM articles WHERE id IN ({','.join('?' * len(aids))})", aids)}
            ens = {r["article_id"]: r for r in q(f"SELECT * FROM m82_artikel WHERE article_id IN ({','.join('?' * len(aids))})", aids)}
            for it in items:
                a, e = arts.get(it.get("article_id")), ens.get(it.get("article_id"))
                if a and e:
                    if e.get("name_en") and (it.get("name") or "").strip() == (a["name"] or "").strip():
                        it["name"] = e["name_en"]
                    if e.get("descr_en") and (it.get("descr") or "").strip() == (a["descr"] or "").strip():
                        it["descr"] = e["descr_en"]
    # reminder (pseudo document from create_mahnung)
    if inv.get("_mahnfrist") and lang == "en":
        try:
            stufe = MAHN_TITLES.index(inv.get("titel"))
        except Exception:
            stufe = None
        if inv.get("_meta"):
            def _dd(v):
                mm_ = re.fullmatch(r"(\d\d)\.(\d\d)\.(\d{4})", str(v or ""))
                return _m82_date(f"{mm_.group(3)}-{mm_.group(2)}-{mm_.group(1)}", "en") if mm_ else v
            inv2["_meta"] = [(a_, _dd(b_)) for a_, b_ in inv["_meta"]]
        if stufe is not None:
            inv2["titel"] = L_lang(MAHN_TITLES[stufe], lang)
            inv2["_doctitle"] = inv2["titel"]
            inv2["toptext"] = t["mahn_anrede"] + "\n\n" + t["mahn_text"][min(stufe, len(t["mahn_text"]) - 1)]
            regel = False
            try:
                regel = "m80_inv_regel" in globals() and m80_inv_regel(inv)
            except Exception:
                regel = False
            inv2["foottext"] = t["mahn_foot"] + ("" if regel else "\n" + M82_KU_EN)   # no par. 19 note for VAT invoices
            for it in items:
                mm = re.match(r"^Rechnung (.+) vom (\d\d)\.(\d\d)\.(\d{4})$", it.get("name") or "")
                if mm:
                    if inv.get("m82") and inv["m82"].get("betrag_fw") and ctx["cur"] != "EUR":
                        it["_fw_price"] = float(inv["m82"]["betrag_fw"])     # same amount as on the invoice PDF
                    it["name"] = f"Invoice {mm.group(1)} dated {_m82_date(f'{mm.group(4)}-{mm.group(3)}-{mm.group(2)}', 'en')}"
                md = re.match(r"^fällig seit (\d\d)\.(\d\d)\.(\d{4})$", it.get("descr") or "")
                if md:
                    it["descr"] = "due since " + _m82_date(f"{md.group(3)}-{md.group(2)}-{md.group(1)}", "en")
                if it.get("name") == "Mahngebühr":
                    it["name"] = "Reminder fee"
                # lines added by m72 (payments received, default interest, 40 EUR flat rate)
                kind = it.get("_m72kind")
                en_amt = lambda v: _m82_numfmt(float(v or 0), 2, "en") + " EUR"
                if kind == "zahlungen":
                    it["name"] = "less payments already received"
                    it["descr"] = ", ".join(f"{_m82_date(d_, 'en')}: {en_amt(b_)}" for d_, b_ in (it.get("_m72data") or []))
                elif kind == "zinsen":
                    zd = it.get("_m72data") or {}
                    seg = zd.get("seg") or []
                    it["name"] = "Default interest (sec. 288 German Civil Code)"
                    if len(seg) > 1:
                        it["descr"] = (f"Base rate + {zd.get('pp')} percentage points on {en_amt(zd.get('rest'))}: " +
                                       "; ".join(f"{_m82_date(s_[0], 'en')} - {_m82_date(s_[1], 'en')}: {s_[2]} days at "
                                                 f"{_m82_numfmt(s_[3], 2, 'en')} %" for s_ in seg))
                    else:
                        it["descr"] = (f"{_m82_numfmt(float(zd.get('satz') or 0), 2, 'en')} % p.a. (base rate + {zd.get('pp')} percentage points) "
                                       f"for {zd.get('tage')} days on {en_amt(zd.get('rest'))}")
                elif kind == "pauschale":
                    it["name"] = "Flat-rate default charge (sec. 288 (5) German Civil Code)"
    elif lang == "en":
        if inv.get("titel") in (v["title"] for v in DOC_TYPES.values()) or inv.get("titel") in ("Rechnung", "Storno-Rechnung", "Angebot", "Auftragsbestätigung"):
            inv2["titel"] = L_lang(inv["titel"], lang)
        inv2["toptext"] = _m82_swap_text(inv.get("toptext"), "top_" + typ, lang)
        inv2["foottext"] = _m82_swap_text(inv.get("foottext"), "foot_" + typ, lang)
        if inv.get("_m82_regel"):
            inv2["foottext"] = (inv2["foottext"] or "").replace(M82_KU_EN, "").strip()
    # currency
    if ctx["cur"] != "EUR":
        for it in items:
            p = float(it.get("price") or 0)
            it["price"] = round(float(it.pop("_fw_price")), 2) if it.get("_fw_price") is not None else round(p * kurs, 2)
            if inv.get("locked") and it.get("total") not in (None, ""):
                # same formula as m82_doc.betrag_fw (price converted, then qty / discount) - the issued PDF (rendered
                # after locking) must show the same total as the preview, the mail text and the reminder
                it["total"] = line_total({"qty": it.get("qty"), "price": it["price"], "rabatt": it.get("rabatt")})
        kd = _m82_date(ctx.get("kurs_datum") or inv.get("datum") or today(), lang)
        src = ctx.get("kurs_quelle") or ""
        eur_txt = _m82_numfmt(eur_sum, 2, lang) + " EUR"
        if lang == "en":
            note = (f"Equivalent: {eur_txt} (exchange rate 1 EUR = {_m82_numfmt(kurs, 4, 'en')} {ctx['cur']}"
                    f"{', ECB ' if src == 'EZB' else ', '}{kd}). Payment in {ctx['cur']}.")
        else:
            note = (f"Gegenwert: {eur_txt} (Kurs 1 EUR = {_m82_numfmt(kurs, 4, 'de')} {ctx['cur']}"
                    f"{', EZB ' if src == 'EZB' else ', '}{kd}). Zahlung in {ctx['cur']}.")
        inv2["foottext"] = (inv2.get("foottext") or "").rstrip() + ("\n" if inv2.get("foottext") else "") + note
    for it in items:
        it.pop("_fw_price", None)
    if inv.get("_nrlabel"):
        inv2["_nrlabel"] = L_lang(inv["_nrlabel"], lang)
    inv2["items"] = items
    inv2["_m82_eur_sum"] = eur_sum
    return inv2


def L_lang(s, lang):
    if lang == "en":
        own = (get_settings().get("m82_labels_en") or {})
        return own.get(s) or M82_LBL_EN.get(s, s)
    return s


# ---------------------------------------------------------------------------
# wrappers
# ---------------------------------------------------------------------------
def _m82_m80_prep(inv):
    """same preparation as the m80 wrapper (VAT block, rate marks, no par. 19 note) - only when m80 is active"""
    try:
        if "m80_inv_regel" not in globals() or not m80_inv_regel(inv):
            return inv
        if inv.get("_mahnfrist"):
            # reminder: invoice line already gross, fees / interest not taxable -> no VAT block (same as m80)
            inv2 = dict(inv)
            inv2["foottext"] = m80_strip_ku(inv.get("foottext") or "").replace(M82_KU_EN, "").strip()
            return inv2
        inv2 = dict(inv)
        items = [dict(it) for it in (inv.get("items") or [])]
        std = float(m80_cfg().get("satz") or 19)
        rates = {m80_item_satz(it) for it in items}
        if len(rates) > 1 or (rates and rates != {std}):
            for it in items:
                it["descr"] = ((it.get("descr") or "").rstrip() + "\n" + f"VAT {_m80_pct(m80_item_satz(it))}").strip()
        inv2["items"] = items
        if not inv.get("locked"):
            ft = m80_strip_ku(inv.get("foottext") or "")
            inv2["foottext"] = ft.replace(M82_KU_EN, "").strip()
        inv2["_m80"] = True
        inv2["_m82_regel"] = True
        return inv2
    except Exception:
        traceback.print_exc()
        return inv


@chain_step("render_invoice_pdf", "m82_international")
def _m82_step_render_invoice_pdf(_next, inv, s=None, attachments=True):
    ctx = m82_ctx_for(inv)
    if not ctx or not _M82_INTL[0]:
        return _next(inv, s, attachments)
    s2 = s or get_settings()
    inv = _m82_m80_prep(inv)
    inv2 = m82_prepare(inv, ctx)
    old = getattr(_M82_TL, "ctx", None)
    _M82_TL.ctx = ctx
    try:
        fam = None
        try:
            fam = inv_font(inv) if "inv_font" in globals() else None
        except Exception:
            fam = None
        cm = doc_font(fam) if (fam and "doc_font" in globals()) else contextlib.nullcontext()
        with cm:
            data = _M82_INTL[0](inv2, s2, attachments)
    finally:
        _M82_TL.ctx = old
    # ZUGFeRD automatically (setting of m50) - only possible in EUR
    try:
        if (ctx["cur"] == "EUR" and s2.get("m50_zugferd_default") and inv.get("id") and (inv.get("typ") or "rechnung") in ("rechnung", "storno")
                and inv.get("status") != "entwurf" and not str(inv.get("nr") or "").startswith("E-") and inv.get("items")
                and "m50_zugferd_pdf" in globals()):
            data, _, _ = m50_zugferd_pdf(inv, None, s2, base_pdf=data)
    except Exception:
        traceback.print_exc()
    return data


@chain_step("get_invoice", "m82_international")
def _m82_step_get_invoice(_next, iid):
    inv = _next(iid)
    if inv:
        try:
            d = m82_doc_get(inv["id"])
            inv["m82"] = {k: d[k] for k in ("sprache", "waehrung", "kurs", "kurs_datum", "kurs_quelle", "betrag_fw")} if d else None
        except Exception:
            inv["m82"] = None
    return inv


@chain_step("save_invoice", "m82_international")
def _m82_step_save_invoice(_next, d, bump=True):
    res = _next(d, bump)
    try:
        iid = res[0]
        m = d.get("m82")
        if m is None and not d.get("id") and d.get("customer_id") and (d.get("typ") or "rechnung") != "storno":
            k = m82_kunde_get(d["customer_id"])
            if k and (k["sprache"] != "de" or k["waehrung"] != "EUR"):
                m = {"sprache": k["sprache"], "waehrung": k["waehrung"]}
                if k["waehrung"] != "EUR":
                    try:
                        kr = m82_kurs(k["waehrung"])
                        m.update(kurs=kr["kurs"], kurs_datum=kr["datum"], kurs_quelle=kr["quelle"])
                    except Exception:
                        m.update(kurs=1.0)
        if isinstance(m, dict):
            m82_doc_set(iid, m)
        elif m is None and d.get("id"):
            pass        # client did not send m82 -> keep what is stored
        else:
            m82_doc_set(iid, {})
    except Exception:
        traceback.print_exc()
    return res


@chain_step("storno_invoice", "m82_international")
def _m82_step_storno_invoice(_next, iid):
    r = _next(iid)
    try:
        o = m82_doc_get(iid)
        row = q("SELECT storno_von FROM invoices WHERE id=?", (iid,), one=True)
        sid = row and row["storno_von"]
        if o and sid and not m82_doc_get(sid):
            eur_, fw = _m82_amounts(sid, float(o["kurs"] or 1))
            x("INSERT OR REPLACE INTO m82_doc (invoice_id, sprache, waehrung, kurs, kurs_datum, kurs_quelle, betrag_fw, betrag_eur, updated) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (sid, o["sprache"], o["waehrung"], o["kurs"], o["kurs_datum"], o["kurs_quelle"], fw, eur_, now_iso()))
    except Exception:
        traceback.print_exc()
    return r


@chain_step("mail_prepare", "m82_international")
def _m82_step_mail_prepare(_next, doc_id=None, mahnung_id=None):
    r = _next(doc_id, mahnung_id)
    try:
        if mahnung_id:
            m = q("SELECT * FROM mahnungen WHERE id=?", (mahnung_id,), one=True)
            inv = get_invoice(m["invoice_id"]) if m else None
        else:
            inv = get_invoice(doc_id) if doc_id else None
        ctx = m82_ctx_for(inv)
        if not ctx or ctx["lang"] != "en":
            return r
        t = m82_texte("en")
        if mahnung_id and m:
            title = L_lang(MAHN_TITLES[min(m["stufe"], 3)], "en") + " for invoice"
        else:
            title = L_lang(DOC_TYPES.get(inv["typ"], DOC_TYPES["rechnung"])["title"], "en")
        c = q("SELECT * FROM customers WHERE id=?", (inv.get("customer_id"),), one=True) if inv.get("customer_id") else None
        amount = (inv.get("summe") or 0) * (float(ctx["kurs"]) if ctx["cur"] != "EUR" else 1.0)
        if ctx["cur"] != "EUR" and inv.get("m82") and inv["m82"].get("betrag_fw") and not mahnung_id:
            amount = float(inv["m82"]["betrag_fw"])
        old = getattr(_M82_TL, "ctx", None)
        _M82_TL.ctx = ctx
        try:
            amt = _m82_money(amount)
        finally:
            _M82_TL.ctx = old

        def fill(text):
            return (text or "").replace("[Dokument]", title).replace("[Nummer]", inv.get("nr", "")) \
                .replace("[Betrag]", amt).replace("[Name]", (c["name"] or c["firma"]) if c else "") \
                .replace("[Inhaber]", get_settings().get("inhaber") or "").replace("[Firma]", get_settings().get("firma") or "").replace("\\n", "\n")
        r["subject"], r["body"] = fill(t["mail_subject"]), fill(t["mail_body"])
    except Exception:
        traceback.print_exc()
    return r


if "build_xrechnung" in globals():
    _m82_prev_xr = build_xrechnung

    def build_xrechnung(inv, *a, **k):
        ctx = m82_ctx_for(inv)
        if ctx and ctx["cur"] != "EUR":
            raise ValueError(f"Dieses Dokument ist in {ctx['cur']} ausgestellt. E-Rechnung (XRechnung/ZUGFeRD) erzeugt das Programm nur in EUR - "
                             "für Kunden im Ausland ist eine E-Rechnung in der Regel nicht vorgeschrieben; das normale PDF genügt.")
        return _m82_prev_xr(inv, *a, **k)


# ---------------------------------------------------------------------------
# bootstrap + routes
# ---------------------------------------------------------------------------
def _m82_boot(d):
    try:
        d["m82"] = {"kunden": {str(r["customer_id"]): {"sprache": r["sprache"], "waehrung": r["waehrung"]}
                               for r in q("SELECT * FROM m82_kunde") if r["sprache"] != "de" or r["waehrung"] != "EUR"},
                    "artikel": {str(r["article_id"]): {"name_en": r["name_en"] or "", "descr_en": r["descr_en"] or ""} for r in q("SELECT * FROM m82_artikel")},
                    "langs": M82_LANGS, "curs": M82_CURS, "texte_en": m82_texte("en"), "intl_ok": bool(_M82_INTL[0]), "intl_info": _M82_INTL[1]}
    except Exception:
        traceback.print_exc()


HOOK_BOOT.append(_m82_boot)


def _m82_r_kunde(h, d):
    cid = int(d["customer_id"])
    n = _m82_norm(d)
    if n["sprache"] == "de" and n["waehrung"] == "EUR":
        x("DELETE FROM m82_kunde WHERE customer_id=?", (cid,))
    else:
        x("INSERT OR REPLACE INTO m82_kunde (customer_id, sprache, waehrung, updated) VALUES (?,?,?,?)", (cid, n["sprache"], n["waehrung"], now_iso()))
    return h._send(200, {"ok": True, "kunde": m82_kunde_get(cid)})


def _m82_r_artikel(h, d):
    rows = d.get("rows") if isinstance(d.get("rows"), list) else [d]
    n = 0
    for r in rows:
        try:
            aid = int(r.get("article_id"))
        except Exception:
            continue
        ne, de_ = (r.get("name_en") or "").strip(), (r.get("descr_en") or "").strip()
        if not ne and not de_:
            x("DELETE FROM m82_artikel WHERE article_id=?", (aid,))
        else:
            x("INSERT OR REPLACE INTO m82_artikel (article_id, name_en, descr_en, updated) VALUES (?,?,?,?)", (aid, ne, de_, now_iso()))
        n += 1
    return h._send(200, {"ok": True, "n": n})


def _m82_r_kurs(h, qs):
    try:
        return h._send(200, m82_kurs(qs.get("w") or "USD", bool(qs.get("force"))))
    except ValueError as e:
        return h._send(200, {"ok": False, "error": str(e)})


def _m82_r_texte_get(h, qs):
    return h._send(200, {"ok": True, "texte": m82_texte("en"), "standard": M82_TEXTE_EN,
                         "labels": dict(M82_LBL_EN, **(get_settings().get("m82_labels_en") or {}))})


def _m82_r_texte(h, d):
    own = get_settings().get("m82_texte") or {}
    en = {}
    for k, v in (d.get("texte") or {}).items():
        if k in M82_TEXTE_EN:
            if k == "mahn_text":
                v = [str(t_ or "") for t_ in (v or [])][:4]
                if v != M82_TEXTE_EN[k] and any(v):
                    en[k] = v
            elif (v or "").strip() and v != M82_TEXTE_EN[k]:
                en[k] = v
    own["en"] = en
    set_setting("m82_texte", own)
    if isinstance(d.get("labels"), dict):
        set_setting("m82_labels_en", {k: v for k, v in d["labels"].items() if k in M82_LBL_EN and v and v != M82_LBL_EN[k]})
    return h._send(200, {"ok": True, "texte": m82_texte("en")})


def _m82_r_doc(h, d):
    iid = int(d["id"])
    r = m82_doc_set(iid, d)
    return h._send(200, {"ok": True, "doc": r})


def _m82_r_list(h, qs):
    rows = q("SELECT d.*, i.nr, i.datum, i.typ, i.status, i.summe FROM m82_doc d JOIN invoices i ON i.id=d.invoice_id ORDER BY i.datum DESC")
    return h._send(200, {"ok": True, "rows": rows})


HOOK_POST["/api/m82/kunde"] = _m82_r_kunde
HOOK_POST["/api/m82/artikel"] = _m82_r_artikel
HOOK_GET["/api/m82/kurs"] = _m82_r_kurs
HOOK_GET["/api/m82/texte"] = _m82_r_texte_get
HOOK_POST["/api/m82/texte"] = _m82_r_texte
HOOK_POST["/api/m82/doc"] = _m82_r_doc
HOOK_GET["/api/m82/list"] = _m82_r_list


def _m82_ex(p):
    rows = q("SELECT d.*, i.nr, i.datum, i.typ, i.status, i.summe, i.customer_id, i.addr, i.kdnr FROM m82_doc d JOIN invoices i ON i.id=d.invoice_id "
             "ORDER BY i.datum DESC")
    ids = _ids(p)
    if ids:
        rows = [r for r in rows if r["invoice_id"] in ids]
    return [_sh("Fremdsprache und Fremdwährung", [("Nr.", "t", 14), ("Datum", "d", 11), ("Art", "t", 14), ("Kunde", "t", 28), ("Sprache", "t", 9),
                                                  ("Währung", "t", 9), ("Kurs", "n", 10), ("Betrag Fremdw.", "n", 14), ("Betrag EUR", "m", 13), ("Status", "t", 10)],
                [[r["nr"], r["datum"], TYP_DE.get(r["typ"], r["typ"]), inv_name(r), M82_LANGS.get(r["sprache"], r["sprache"]), r["waehrung"],
                  r["kurs"] or 1, r["betrag_fw"] or 0, r["summe"] or 0, r["status"]] for r in rows], f"Stand {de_date(today())}")]


EXPORTS["m82_international"] = ("Fremdsprache_Waehrung", _m82_ex)


def _m82_selftest():
    err = []
    try:
        if not _M82_INTL[0]:
            err.append("m82: englische PDF-Variante fehlt (" + _M82_INTL[1] + ")")
        elif _M82_INTL[1]:
            err.append("m82: PDF-Variante unvollständig (" + _M82_INTL[1] + ")")
        _M82_TL.ctx = {"lang": "en", "cur": "USD", "kurs": 1.1}
        try:
            if _m82_money(1234.5) != "1,234.50 USD":
                err.append(f"m82: Betragsformat EN falsch ({_m82_money(1234.5)})")
            if _m82_date("2026-10-27") != "27 Oct 2026":
                err.append("m82: Datumsformat EN falsch")
            if L("Gesamtbetrag:") != "Total amount:":
                err.append("m82: Übersetzung fehlt")
        finally:
            _M82_TL.ctx = None
        if _m82_money(5) != "5,00 EUR":
            err.append("m82: Betragsformat DE falsch")
        cid = x("INSERT INTO customers (kdnr, firma, name, created) VALUES (?,?,?,?)", ("_ST_M82", "Selftest Ltd", "", now_iso()))
        x("INSERT INTO m82_kunde (customer_id, sprache, waehrung) VALUES (?,?,?)", (cid, "en", "USD"))
        iid, nr = save_invoice({"customer_id": cid, "kdnr": "_ST_M82", "addr": ["Selftest Ltd"], "status": "entwurf", "typ": "rechnung",
                                "foottext": M82_KU_DE, "m82": {"sprache": "en", "waehrung": "USD", "kurs": 1.25},
                                "items": [{"qty": 2, "name": "Test", "price": 100.0, "rabatt": 0}]}, bump=False)
        doc = m82_doc_get(iid)
        if not doc or abs((doc["betrag_fw"] or 0) - 250.0) > 0.001 or abs((doc["betrag_eur"] or 0) - 200.0) > 0.001:
            err.append(f"m82: Fremdwährungsbetrag falsch ({doc})")
        inv = get_invoice(iid)
        if abs(inv["summe"] - 200.0) > 0.001:
            err.append("m82: Rechnungssumme nicht in EUR")
        if pypdf:
            pdf = render_invoice_pdf(inv)
            txt = " ".join((pg.extract_text() or "") for pg in pypdf.PdfReader(io.BytesIO(pdf)).pages)
            if "250.00 USD" not in txt or "Total amount" not in txt or "Equivalent" not in txt:
                err.append("m82: englisches PDF ohne erwartete Texte")
            if "section 19" not in txt:
                err.append("m82: Kleinunternehmer-Hinweis nicht übersetzt")
        x("DELETE FROM items WHERE invoice_id=?", (iid,))
        x("DELETE FROM invoices WHERE id=?", (iid,))
        x("DELETE FROM m82_doc WHERE invoice_id=?", (iid,))
        # with m80 (Regelbesteuerung): English VAT block and gross foreign amount
        if "m80_ust_block" in globals() and pypdf:
            old_cfg = get_settings().get("m80")
            try:
                set_setting("m80", dict(old_cfg or {}, ab="2000-01-01"))
                iid2, _ = save_invoice({"customer_id": cid, "kdnr": "_ST_M82", "addr": ["Selftest Ltd"], "status": "entwurf", "typ": "rechnung",
                                        "datum": today(), "m82": {"sprache": "en", "waehrung": "USD", "kurs": 1.25},
                                        "items": [{"qty": 1, "name": "Test", "price": 100.0, "rabatt": 0, "ust_satz": 19}]}, bump=False)
                d2 = m82_doc_get(iid2)
                if not d2 or abs((d2["betrag_fw"] or 0) - 148.75) > 0.011:
                    err.append(f"m82+m80: Fremdwährungsbetrag brutto falsch ({d2 and d2['betrag_fw']})")
                t2 = " ".join((pg.extract_text() or "") for pg in pypdf.PdfReader(io.BytesIO(render_invoice_pdf(get_invoice(iid2)))).pages)
                if "Net amount" not in t2 or "148.75 USD" not in t2:
                    err.append("m82+m80: englischer USt-Block fehlt")
                x("DELETE FROM items WHERE invoice_id=?", (iid2,))
                x("DELETE FROM invoices WHERE id=?", (iid2,))
                x("DELETE FROM m82_doc WHERE invoice_id=?", (iid2,))
            finally:
                if old_cfg is None:
                    x("DELETE FROM settings WHERE k='m80'")
                else:
                    set_setting("m80", old_cfg)
        x("DELETE FROM m82_kunde WHERE customer_id=?", (cid,))
        x("DELETE FROM customers WHERE id=?", (cid,))
    except Exception as e:
        traceback.print_exc()
        err.append(f"m82 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m82_selftest)
