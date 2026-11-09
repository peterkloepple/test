# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m30_mail_eingang  v3.2.0
# v3.2.0 (Programm v3.6.0): Mails lesen - ganze Mail mit HTML-Ansicht, An/Kopie, gelesen/ungelesen
#         (Spalte mail_inbox.gelesen, Migration 3), Route /api/mail/gelesen.
# Mail-Eingang - ab v3.1.0 in EINER Datei zusammengefasst aus:
#   m30_mail_import  E-Mails einlesen (.eml/.msg/.mbox) und beurteilen
#   m31_imap         IMAP-Postfach abrufen
# Reihenfolge der Teile = bisherige Lade-Reihenfolge (Verhalten unveraendert).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer


# ============================================================================
# Teil aus m30_mail_import.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m30_mail_import  v1.0.0
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer
#
# E-Mails einlesen (.eml, .msg, .mbox) und beurteilen: Rechnung ja/nein.
# - Anhaenge werden einzeln geprueft (E-Rechnung XML / ZUGFeRD, PDF-Text, Office)
# - Mailtext/Betreff: gewichtete Schluesselwoerter + Gegenindikatoren
# - Absender-Lernen (Tabelle mail_absender)
# - optional lokale KI (Ollama, Settings ki_*) nur wenn unsicher
# - Uebernahme in die vorhandene Beleg-Pruefliste (pending_belege)
# Ablage: <Datenordner>/E-Mails/<JJJJ-MM>/<zeit>_<betreff>_<hash>/

import mailbox
import email.utils
import email.header

MAIL_DIRNAME = "E-Mails"
MAIL_LOCK = threading.RLock()

MAIL_URTEILE = {
    "rechnung_anhang": "Rechnung (Anhang)",
    "rechnung_text": "Rechnung im Mailtext",
    "erechnung": "E-Rechnung (XML)",
    "rechnung_link": "Rechnung nur per Link/Kundenportal",
    "gutschrift": "Gutschrift/Erstattung",
    "mahnung": "Zahlungserinnerung/Mahnung",
    "auftrag": "Auftragsbestätigung/Angebot (keine Rechnung)",
    "keine": "Keine Rechnung",
}
MAIL_BELEG_URTEILE = ("rechnung_anhang", "rechnung_text", "erechnung", "rechnung_link", "gutschrift", "mahnung")
MAIL_UNSICHER = 0.65
MAIL_FREEMAIL = {"gmail.com", "googlemail.com", "gmx.de", "gmx.net", "web.de", "t-online.de", "outlook.com", "outlook.de",
                 "hotmail.com", "hotmail.de", "live.de", "live.com", "yahoo.com", "yahoo.de", "icloud.com", "me.com",
                 "freenet.de", "posteo.de", "mailbox.org", "aol.com", "arcor.de", "1und1.de", "online.de"}

# ---------------- keyword tables (pattern, weight, reason) ----------------
_U = r"(?:ä|ae|a)"      # umlaut tolerant
_UE = r"(?:ü|ue|u)"
_OE = r"(?:ö|oe|o)"

MAIL_POS = [
    (r"\brechnung(en)?\b", 1.5, "Wort „Rechnung“"),
    (r"rechnungs-?\s?(nr|nummer)|rechnung\s*(nr|nummer)\b|invoice\s*(no|number|#|nr)", 2.5, "Rechnungsnummer"),
    (r"rechnungsbetrag|gesamtbetrag|endbetrag|zahlbetrag|zu zahlen(der betrag)?|amount due|total due|gesamtsumme", 2.0, "Rechnungs-/Gesamtbetrag"),
    (r"rechnungsdatum|invoice date|leistungsdatum|leistungszeitraum", 1.5, "Rechnungs-/Leistungsdatum"),
    (r"f" + _U + r"llig|zahlbar (bis|innerhalb|sofort)|zahlungsziel|due date|payable|bitte " + _UE + r"berweisen", 1.5, "Fälligkeit / Zahlungsziel"),
    (r"\biban\b|\bbic\b|verwendungszweck|bankverbindung", 1.2, "Bankverbindung / IBAN"),
    (r"kundennummer|kunden-?nr|customer (no|number|id)|vertragsnummer|vertragskonto", 0.8, "Kunden-/Vertragsnummer"),
    (r"\binvoice\b|\bfactura\b|\bfacture\b|\bbill\b", 2.0, "„Invoice“"),
    (r"ust\.?-?id|umsatzsteuer|\bmwst\b|mehrwertsteuer|\bvat\b|\bnetto\b|\bbrutto\b", 0.8, "Steuer-/Netto-/Bruttoangaben"),
    (r"lastschrift|abgebucht|wird .{0,40}eingezogen|sepa", 0.8, "Abbuchung / Lastschrift"),
    (r"\bquittung\b|\bkassenbon\b|zahlungsbest" + _U + r"tigung|\breceipt\b|payment confirmation", 1.5, "Quittung / Zahlungsbestätigung"),
]
MAIL_SUBJ_POS = [
    (r"\brechnung|\binvoice\b|\bfactura\b|\bfacture\b|\bbeleg\b|\bquittung\b|\breceipt\b", 2.5, "Betreff nennt Rechnung/Beleg"),
]
MAIL_MAHN = r"zahlungserinnerung|\bmahnung\b|\bgemahnt|" + _UE + r"berf" + _U + r"llig|noch (nicht|kein[e]?) (bezahlt|beglichen|zahlungseingang)|offene[rn]? (betrag|posten|rechnung|forderung)|payment reminder|past due|overdue|zahlungsverzug"
MAIL_GUT = r"\bgutschrift\b|r" + _UE + r"ckerstattung|\berstattung\b|\berstattet\b|\brefund\b|credit note|stornorechnung|\bstorniert\b"
MAIL_AUFTRAG = (r"auftragsbest" + _U + r"tigung|bestellbest" + _U + r"tigung|order confirmation|ihre bestellung|bestellung (ist )?(eingegangen|erhalten|aufgenommen)|"
                r"\bangebot\b|\bangebots-?nr|kostenvoranschlag|\bquotation\b|\bquote\b|versandbest" + _U + r"tigung|wurde versandt|has shipped|lieferschein")
MAIL_NEWS = [
    (r"newsletter|\babmelden\b|abbestellen|unsubscribe|nicht mehr erhalten|im browser (an)?sehen|view (this email )?in (your )?browser|webversion|online-version", 3.0, "Newsletter-Merkmale (Abmelden-Link)"),
    (r"\brabatt|gutschein|\bsale\b|%\s?off\b|angebote? der woche|nur heute|jetzt (kaufen|shoppen|sichern|entdecken)|gewinnspiel|black friday|sonderaktion", 1.5, "Werbung (Rabatt/Aktion)"),
    (r"webinar|einladung zu|save the date|veranstaltung", 0.8, "Einladung / Veranstaltung"),
]
MAIL_PRIVATE = r"liebe gr" + _UE + r"(ß|ss)e|viele gr" + _UE + r"(ß|ss)e|\bhallo \w+[,!]|\bhi \w+[,!]|\bbussi\b|\bknutsch|hab dich lieb"
MAIL_LINK = (r"(rechnung|invoice|beleg)[^\n]{0,90}(herunterladen|download|abrufen|abholen|einsehen|ansehen|online|kundenportal|kundenkonto|kundencenter|"
             r"mein(em)? konto|portal|bereit|verf" + _UE + r"gbar|available|view|postfach|servicewelt)|"
             r"(herunterladen|download|abrufen|einsehen|ansehen|kundenportal|kundenkonto|kundencenter|mein(em)? konto|servicewelt)[^\n]{0,90}(rechnung|invoice)")
MAIL_AMT = re.compile(r"(?:(?:€|eur)\s?-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d{1,3}(?:\.\d{3})*,\d{2}\s?(?:€|eur\b)|(?:€|eur)\s?\d+[.,]\d{2}|\d+[.,]\d{2}\s?(?:€|eur\b))", re.I)

ATT_INV = [
    (r"\brechnung\b|\binvoice\b|\bfactura\b|\bfacture\b", 2.0),
    (r"rechnungs-?\s?(nr|nummer)|rechnung\s*nr|invoice\s*(no|number|#)", 2.0),
    (r"rechnungsbetrag|gesamtbetrag|endbetrag|zu zahlen|amount due|gesamtsumme|\bsumme\b|\btotal\b", 1.5),
    (r"rechnungsdatum|invoice date|leistungsdatum", 1.0),
    (r"ust\.?-?id|umsatzsteuer|\bmwst\b|\bvat\b|steuernummer", 1.0),
    (r"\biban\b|bankverbindung|f" + _U + r"llig|zahlbar", 0.8),
    (r"\bquittung\b|kassenbon|\breceipt\b|\bbeleg\b", 1.5),
]
ATT_NAME_INV = re.compile(r"rechnung|invoice|\brg[-_ ]?\d|\bre[-_]\d|faktura|factur|beleg|quittung|receipt|gutschrift|credit", re.I)
ATT_DOC_EXT = (".pdf", ".xml", ".docx", ".doc", ".xlsx", ".xls", ".odt", ".ods", ".rtf", ".txt", ".csv", ".htm", ".html", ".zip")
ATT_IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic")


def mail_schema():
    x("""CREATE TABLE IF NOT EXISTS mail_inbox (id INTEGER PRIMARY KEY, msgid TEXT, hash TEXT, quelle TEXT, datei TEXT,
         absender TEXT, absender_addr TEXT, empfaenger TEXT, betreff TEXT, datum TEXT, text TEXT, anhaenge TEXT, meta TEXT,
         urteil TEXT, sicherheit REAL, begruendung TEXT, betrag REAL, status TEXT, ordner TEXT, belege INTEGER DEFAULT 0,
         created TEXT, updated TEXT)""")
    try:
        x("ALTER TABLE mail_inbox ADD COLUMN gelesen INTEGER DEFAULT 0")   # v3.2.0
    except Exception:
        pass
    x("CREATE INDEX IF NOT EXISTS ix_mail_inbox_msgid ON mail_inbox (msgid)")
    x("CREATE INDEX IF NOT EXISTS ix_mail_inbox_hash ON mail_inbox (hash)")
    x("""CREATE TABLE IF NOT EXISTS mail_absender (addr TEXT PRIMARY KEY, domain TEXT, rechnung INTEGER DEFAULT 0,
         keine INTEGER DEFAULT 0, updated TEXT)""")


HOOK_SCHEMA.append(mail_schema)


def mail_dir():
    d = os.path.join(DATA_DIR, MAIL_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


# ---------------- parsing ----------------
def _hdr(v):
    try:
        return re.sub(r"\s+", " ", str(email.header.make_header(email.header.decode_header(str(v or ""))))).strip()
    except Exception:
        return re.sub(r"\s+", " ", str(v or "")).strip()


def _links_from_html(html):
    out = []
    for m in re.finditer(r"<a\b[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html or "", re.I | re.S):
        url = m.group(1).strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        txt = re.sub(r"\s+", " ", html_text(m.group(2))).strip()
        out.append({"text": txt[:120], "url": url[:500]})
    return out


def _links_from_text(text):
    return [{"text": "", "url": u[:500]} for u in re.findall(r"https?://[^\s<>\"')\]]+", text or "")]


def _mail_fix_headers(raw):
    """v2.1.0: unencoded 8-bit headers of old mailers are mostly cp1252 ("Fuer" with a raw 0xFC byte became "F?r") -> recode to UTF-8"""
    ends = [i for i in (raw.find(b"\r\n\r\n"), raw.find(b"\n\n")) if i >= 0]
    end = min(ends) if ends else len(raw)
    head = raw[:end]
    try:
        head.decode("utf-8")
        return raw
    except UnicodeDecodeError:
        return head.decode("cp1252", "replace").encode("utf-8") + raw[end:]


def mail_parse_eml(raw):
    """raw bytes of an RFC822 mail -> dict with header fields, text, links, attachments"""
    m = email.message_from_bytes(_mail_fix_headers(raw), policy=email.policy.default)

    def h(k):
        try:
            return _hdr(m.get(k, ""))
        except Exception:
            return ""
    name, addr = email.utils.parseaddr(h("from"))
    datum = ""
    try:
        dt = email.utils.parsedate_to_datetime(h("date"))
        if dt.tzinfo:
            dt = dt.astimezone().replace(tzinfo=None)
        datum = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    plain, html = "", ""
    def _body_txt(part):
        # v2.0.6: unknown charsets (unknown-8bit, x-unknown ...) no longer lose the text
        try:
            return part.get_content()
        except Exception:
            try:
                return _decode(part.get_payload(decode=True) or b"")
            except Exception:
                return ""
    try:
        b = m.get_body(preferencelist=("plain",))
        if b is not None:
            plain = _body_txt(b)
    except Exception:
        pass
    try:
        b = m.get_body(preferencelist=("html",))
        if b is not None:
            html = _body_txt(b)
    except Exception:
        pass
    text = plain if plain.strip() else html_text(html)
    links = _links_from_html(html) + _links_from_text(plain)
    atts = []
    for part in m.walk():
        if part.is_multipart():
            continue
        fn = part.get_filename()
        disp = (part.get_content_disposition() or "")
        ctype = part.get_content_type()
        if not fn and disp != "attachment":
            continue
        if not fn:
            fn = "anhang" + (mimetypes.guess_extension(ctype) or ".bin")
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:
            continue
        inline = bool(part.get("Content-ID")) or disp == "inline"
        atts.append({"name": _hdr(fn), "data": data, "ctype": ctype, "inline": inline})
    return {"absender": name or addr, "absender_addr": (addr or "").lower(), "empfaenger": h("to")[:300],
            "betreff": h("subject"), "datum": datum, "msgid": h("message-id").strip("<> ").lower()[:300],
            "text": text or "", "links": links[:200], "atts": atts,
            "list_unsub": bool(h("list-unsubscribe")), "precedence": h("precedence").lower(),
            "auto": h("auto-submitted").lower()}


def _msg_props(path):
    """read Message-ID and sent date from an Outlook .msg (best effort)"""
    out = {"msgid": "", "datum": ""}
    try:
        import olefile
        ole = olefile.OleFileIO(path)
        try:
            for suf, enc in (("001F", "utf-16le"), ("001E", "cp1252")):
                n = "__substg1.0_1035" + suf
                if ole.exists(n):
                    out["msgid"] = ole.openstream(n).read().decode(enc, "replace").rstrip("\x00").strip("<> ").lower()
                    break
            if ole.exists("__properties_version1.0"):
                data = ole.openstream("__properties_version1.0").read()
                for off in range(32, len(data) - 15, 16):
                    tag = struct.unpack("<I", data[off:off + 4])[0]
                    if tag in (0x00390040, 0x0E060040):     # PR_CLIENT_SUBMIT_TIME, PR_MESSAGE_DELIVERY_TIME
                        ft = struct.unpack("<Q", data[off + 8:off + 16])[0]
                        if ft:
                            dt = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ft // 10)
                            dt = dt.replace(tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
                            out["datum"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                            if tag == 0x00390040:
                                break
        finally:
            ole.close()
    except Exception:
        pass
    return out


def mail_parse_msg(path):
    """Outlook .msg via the existing unpack_container (m13)"""
    atts, text, _u = unpack_container(path, "mail.msg")
    body, head = text, ""
    k = text.rfind("\n\nVon: ")
    if k >= 0:
        body, head = text[:k], text[k + 2:]
    hd = {}
    for ln in head.split("\n"):
        if ": " in ln:
            a, b = ln.split(": ", 1)
            hd[a.strip()] = b.strip()
    name, addr = email.utils.parseaddr(hd.get("Von", ""))
    if not addr and "@" in hd.get("Von", ""):
        addr = re.findall(r"[\w.+-]+@[\w.-]+", hd["Von"])[0]
    pr = _msg_props(path)
    return {"absender": name or addr, "absender_addr": (addr or "").lower(), "empfaenger": "",
            "betreff": hd.get("Betreff", ""), "datum": pr["datum"], "msgid": pr["msgid"], "text": body,
            "links": _links_from_text(body), "atts": [{"name": n, "data": b, "ctype": mimetypes.guess_type(n)[0] or "",
                                                         "inline": False} for n, b in atts],
            "list_unsub": False, "precedence": "", "auto": ""}


# ---------------- attachment check ----------------
def _kw_score(text, table):
    sc, hits = 0.0, []
    for pat, w, *why in table:
        if re.search(pat, text, re.I):
            sc += w
            if why:
                hits.append(why[0])
    return sc, hits


def mail_att_info(name, data, inline=False, other_docs=False):
    """classify one attachment -> dict(art, score, hinweis, ...)"""
    ext = os.path.splitext((name or "").lower())[1]
    info = {"name": name, "size": len(data or b""), "ext": ext, "art": "sonstig", "score": 0.0, "hinweis": ""}
    if not data:
        info.update(art="leer", hinweis="leer")
        return info
    if ext in ATT_IMG_EXT:
        if inline or len(data) < 30000 or other_docs:
            info.update(art="logo", hinweis="Bild/Logo – verworfen")
        else:
            info.update(art="bild", hinweis="Foto/Scan")
            if ATT_NAME_INV.search(name or ""):
                info["score"] = 2.0
        return info
    if ext not in ATT_DOC_EXT:
        info["hinweis"] = "kein Beleg-Format"
        return info
    info["art"] = "dokument"
    text = ""
    if ext == ".xml":
        try:
            ei = parse_einvoice_xml(data)
        except Exception:
            ei = None
        if ei:
            info.update(art="gutschrift" if ei.get("gutschrift") else "erechnung", score=10.0, betrag=ei.get("betrag") or 0,
                        hinweis=f"E-Rechnung: {ei.get('format', '')} {ei.get('nr', '')}".strip(), partner=ei.get("partner", ""))
            if ei.get("gutschrift"):
                info["erechnung"] = True
            return info
        text = re.sub(r"<[^>]+>", " ", _decode(data[:400000]))
    else:
        tp = _tmp_for(name)
        try:
            write_file(tp, data)
            if ext == ".pdf":
                emb = pdf_embedded_xml(tp)
                if emb:
                    ei = emb[0]
                    info.update(art="gutschrift" if ei.get("gutschrift") else "erechnung", score=10.0, betrag=ei.get("betrag") or 0,
                                hinweis="ZUGFeRD/Factur-X (PDF mit E-Rechnung)", partner=ei.get("partner", ""), erechnung=True)
                    return info
            if ext != ".zip":
                try:
                    text, _used, _fmt = extract_text_any(tp, name)
                except PasswordNeeded:
                    info["hinweis"] = "passwortgeschützt"
                    info["geschuetzt"] = True
                except Exception:
                    text = ""
        finally:
            try:
                os.remove(tp)
            except Exception:
                pass
    low = (text or "")[:20000].lower()
    sc = sum(w for p, w in ATT_INV if re.search(p, low))
    if MAIL_AMT.search(low) or re.search(AMT, low):
        sc += 1.0
    if ATT_NAME_INV.search(name or ""):
        sc += 2.0
    head = low[:1500]
    info["score"] = round(sc, 1)
    info["textlen"] = len(low.strip())
    if re.search(r"auftragsbest" + _U + r"tigung|\bangebot\b|kostenvoranschlag|lieferschein|order confirmation|quotation", head) \
            and not re.search(r"\brechnung\b|\binvoice\b", head):
        info.update(art="auftrag", hinweis="Angebot/Auftragsbestätigung")
    elif re.search(MAIL_MAHN, head):
        info.update(art="mahnung", hinweis="Mahnung/Zahlungserinnerung")
    elif re.search(r"\bgutschrift\b|credit note|stornorechnung|erstattung", head) and not re.search(r"rechnungsbetrag|zu zahlen", low):
        info.update(art="gutschrift", hinweis="Gutschrift")
    elif sc >= 3.5:
        info.update(art="rechnung", hinweis="sieht nach Rechnung aus")
        try:
            info["betrag"] = first_amount_after(text, [r"rechnungsbetrag", r"gesamtbetrag", r"zu zahlen(?:der betrag)?", r"endbetrag",
                                                       r"gesamtsumme", r"brutto(?:betrag)?", r"amount due|total due|grand total",
                                                       TOTAL_LABEL], "last", avoid=NET_LINE)
        except Exception:
            pass
    elif not low.strip() and ext == ".pdf":
        info["hinweis"] = "PDF ohne Text (Scan?)"
        if ATT_NAME_INV.search(name or ""):
            info["art"] = "rechnung"
    elif ext == ".zip":
        info["hinweis"] = "ZIP-Archiv"
    else:
        info["hinweis"] = "Dokument (keine Rechnungsmerkmale)"
    return info


# ---------------- classification ----------------
def _sig(v):
    return 1.0 / (1.0 + math.exp(-v))


def mail_sender_memory(addr):
    addr = (addr or "").lower()
    dom = addr.split("@")[-1] if "@" in addr else ""
    r = {"rechnung": 0, "keine": 0, "dom_rechnung": 0, "dom_keine": 0}
    try:
        a = q("SELECT rechnung, keine FROM mail_absender WHERE addr=?", (addr,), one=True) if addr else None
        if a:
            r["rechnung"], r["keine"] = a["rechnung"] or 0, a["keine"] or 0
        if dom and dom not in MAIL_FREEMAIL:
            d = q("SELECT COALESCE(SUM(rechnung),0) r, COALESCE(SUM(keine),0) k FROM mail_absender WHERE domain=? AND addr!=?", (dom, addr), one=True)
            if d:
                r["dom_rechnung"], r["dom_keine"] = d["r"] or 0, d["k"] or 0
    except Exception:
        pass
    return r


def mail_learn_sender(addr, rechnung):
    addr = (addr or "").lower().strip()
    if not addr:
        return
    dom = addr.split("@")[-1] if "@" in addr else ""
    col = "rechnung" if rechnung else "keine"
    if q("SELECT addr FROM mail_absender WHERE addr=?", (addr,), one=True):
        x(f"UPDATE mail_absender SET {col}={col}+1, updated=? WHERE addr=?", (now_iso(), addr))
    else:
        x(f"INSERT INTO mail_absender (addr, domain, {col}, updated) VALUES (?,?,1,?)", (addr, dom, now_iso()))


def mail_classify(p, atts_info, use_memory=True):
    """p: parsed mail (betreff, text, links, list_unsub, absender_addr ...), atts_info: list of mail_att_info dicts
    -> dict(urteil, sicherheit, begruendung[list], betrag)"""
    subj = (p.get("betreff") or "")
    body = (p.get("text") or "")[:30000]
    low = (subj + "\n" + body).lower()
    sl = subj.lower()
    why = []
    pos, hits = _kw_score(low, MAIL_POS)
    sp, sh = _kw_score(sl, MAIL_SUBJ_POS)
    pos += sp
    hits += sh
    amts = MAIL_AMT.findall(low)
    if amts:
        pos += 1.5
        hits.append("Betrag in EUR")
    neg, nh = _kw_score(low, MAIL_NEWS)
    if p.get("list_unsub"):
        neg += 2.5
        nh.append("Kopfzeile List-Unsubscribe (Verteiler)")
    if p.get("precedence") in ("bulk", "list"):
        neg += 1.0
        nh.append("Massenversand (Precedence)")
    if re.search(MAIL_PRIVATE, low[:3000]) and pos < 3:
        neg += 1.0
        nh.append("klingt nach privater Mail")
    mahn = re.search(MAIL_MAHN, low)
    gut = re.search(MAIL_GUT, low)
    auftrag = re.search(MAIL_AUFTRAG, low)
    link_m = re.search(MAIL_LINK, low)
    if not link_m:
        for l_ in p.get("links") or []:
            t_ = (l_.get("text") or "").lower() + " " + (l_.get("url") or "").lower()
            if re.search(r"rechnung|invoice|beleg|kundenportal|kundenkonto", t_) and re.search(r"rechnung|invoice|download|pdf|portal|konto|ansehen|abrufen", t_):
                link_m = True
                break
    has_url = bool(p.get("links")) or bool(re.search(r"https?://", body))
    # sender memory
    mem = mail_sender_memory(p.get("absender_addr")) if use_memory else {"rechnung": 0, "keine": 0, "dom_rechnung": 0, "dom_keine": 0}
    if mem["rechnung"]:
        pos += min(4.0, 2.0 + mem["rechnung"])
        why.append(f"Absender bekannt: schon {mem['rechnung']}× als Rechnung übernommen")
    elif mem["dom_rechnung"]:
        pos += 1.5
        why.append(f"Absender-Domain schickte schon {mem['dom_rechnung']}× Rechnungen")
    if mem["keine"]:
        neg += min(4.0, 2.0 + mem["keine"])
        why.append(f"Absender als „keine Rechnung“ gemerkt ({mem['keine']}×)")
    elif mem["dom_keine"] and not mem["rechnung"]:
        neg += 1.0
        why.append("Absender-Domain bisher keine Rechnungen")
    docs = [a for a in atts_info if a.get("art") not in ("logo", "leer", "sonstig")]
    einv = [a for a in docs if a.get("erechnung") or a.get("art") == "erechnung"]
    inv_atts = [a for a in docs if a.get("art") in ("rechnung", "erechnung", "gutschrift", "mahnung")]
    betrag = 0.0
    for a in einv + inv_atts:
        betrag = betrag or float(a.get("betrag") or 0)
    if not betrag and amts:
        betrag = _mail_text_betrag(body, amts)
    logos = [a for a in atts_info if a.get("art") == "logo"]
    if logos:
        why.append(f"{len(logos)} Bild(er)/Logo(s) ignoriert")
    urteil, conf = "keine", 0.5
    if einv:
        a = einv[0]
        urteil = "gutschrift" if a.get("art") == "gutschrift" else "erechnung"
        conf = 0.97
        why.insert(0, f"Anhang „{a['name']}“: {a.get('hinweis') or 'E-Rechnung'}")
    elif inv_atts:
        best = max(inv_atts, key=lambda a: a.get("score") or 0)
        arts = {a["art"] for a in inv_atts}
        if "mahnung" in arts or (mahn and re.search(MAIL_MAHN, sl)):
            urteil = "mahnung"
        elif "gutschrift" in arts and "rechnung" not in arts:
            urteil = "gutschrift"
        else:
            urteil = "rechnung_anhang"
        why.insert(0, f"Anhang „{best['name']}“: {best.get('hinweis') or 'Rechnung'} (Merkmale {nde_py(best.get('score') or 0, 1)})")
        conf = _sig((best.get("score") or 0) * 0.55 + pos * 0.25 - neg * 0.35 - 0.6)
        conf = max(0.55, min(0.96, conf))
    else:
        doc_hint = [a for a in docs if a.get("art") in ("dokument", "bild") and (ATT_NAME_INV.search(a["name"] or "") or a.get("geschuetzt"))]
        auftrag_doc = [a for a in docs if a.get("art") == "auftrag"]
        if mahn and pos >= 2:
            urteil = "mahnung"
            conf = _sig(pos * 0.35 - neg * 0.4 + 0.5)
            why.insert(0, "Text: Zahlungserinnerung / Mahnung")
        elif gut and (pos >= 2 or amts) and not re.search(r"\bgutschein", low):
            urteil = "gutschrift"
            conf = _sig(pos * 0.3 - neg * 0.4 + 0.3)
            why.insert(0, "Text: Gutschrift / Erstattung")
        elif (auftrag or auftrag_doc) and not re.search(r"\brechnung\b|\binvoice\b", sl) and not re.search(r"rechnungs-?\s?(nr|nummer)|rechnungsbetrag", low):
            urteil = "auftrag"
            conf = _sig(1.2 + (0.8 if auftrag_doc else 0) - pos * 0.15)
            why.insert(0, "Angebot / Bestell- oder Auftragsbestätigung – noch keine Rechnung"
                       + (f" (Anhang „{auftrag_doc[0]['name']}“)" if auftrag_doc else ""))
        elif doc_hint and (pos >= 2 or ATT_NAME_INV.search(doc_hint[0]["name"] or "")):
            urteil = "rechnung_anhang"
            conf = _sig(pos * 0.3 - neg * 0.4 - 0.2)
            why.insert(0, f"Anhang „{doc_hint[0]['name']}“ heißt wie eine Rechnung, Inhalt nicht lesbar ({doc_hint[0].get('hinweis') or 'Scan/Foto'})")
        elif link_m and has_url and pos >= 1.5:
            urteil = "rechnung_link"
            conf = _sig(pos * 0.3 - neg * 0.5 + 0.3)
            why.insert(0, "Rechnung liegt nur online (Link / Kundenportal) – bitte herunterladen und nachreichen")
        elif pos >= 5 and amts and re.search(r"rechnungs-?\s?(nr|nummer)|rechnung\s*nr|invoice|f" + _U + r"llig|zahlbar|\biban\b|rechnungsbetrag|gesamtbetrag|quittung|receipt", low):
            urteil = "rechnung_text"
            conf = _sig((pos - 5) * 0.35 - neg * 0.5 + 1.0)
            why.insert(0, "Rechnungsdaten stehen direkt im Mailtext")
        elif mem["rechnung"] and (amts or docs) and neg < 3:
            # known invoice sender, weak text: probably an invoice, but let the user decide
            urteil = "rechnung_anhang" if docs else "rechnung_text"
            conf = _sig(pos * 0.25 - neg * 0.4 - 0.9)
            why.insert(0, "Bekannter Rechnungs-Absender, " + ("Anhang ohne klare Rechnungsmerkmale" if docs else "Betrag im Text") + " – bitte prüfen")
        else:
            urteil = "keine"
            conf = _sig(neg * 0.6 - pos * 0.45 + 1.0)
            if not nh and pos < 2:
                why.insert(0, "Anhänge ohne Rechnungsmerkmale" if docs else "Keine Rechnungsmerkmale gefunden")
        conf = max(0.3, min(0.95, conf))
    if urteil != "keine" and urteil != "auftrag" and hits:
        why.append("Merkmale: " + ", ".join(dict.fromkeys(hits)))
    if nh:
        why.append(("Gegenindikatoren: " if urteil != "keine" else "") + ", ".join(dict.fromkeys(nh)))
    if urteil == "keine" and hits and pos >= 2:
        why.append("schwache Rechnungsmerkmale: " + ", ".join(dict.fromkeys(hits)))
    own = (get_settings().get("smtp_user") or "").lower().strip()
    if own and own == (p.get("absender_addr") or ""):
        why.append("Von dir selbst gesendet – evtl. eigene Ausgangsrechnung")
    return {"urteil": urteil, "sicherheit": round(conf, 2), "begruendung": why, "betrag": round(betrag or 0, 2)}


def _mail_text_betrag(body, amts):
    """v2.1.0: invoice amount from the mail text. Was the LAST Euro amount of the mail - e.g. the VAT line
    ("darin MwSt. 38,00 EUR"), a saving ("10,00 EUR gespart") or a fee. Now: labelled total first, else the largest amount."""
    v = 0.0
    try:
        v = first_amount_after(body, [r"rechnungsbetrag", r"gesamtbetrag", r"zu zahlen(?:der betrag)?", r"zahlbetrag", r"endbetrag",
                                      r"amount due|total due|grand total|amount paid|amount charged", r"gesamtsumme",
                                      SUM_LABEL, TOTAL_LABEL, r"brutto(?:betrag)?"], "first", avoid=NET_LINE)
    except Exception:
        traceback.print_exc()
    if not v:
        vals = []
        for a in amts:
            try:
                vals.append(abs(parse_amount(re.sub(r"[^\d,.\-]", "", a))))
            except Exception:
                continue
        v = max(vals) if vals else 0.0
    return v


# nde_py(): definiert in m71_zahlungen (v2.1.0: alte, nie benutzte Fassung entfernt)


def mail_llm(p, s):
    """ask the local LLM (Ollama) for a verdict; same server/model settings as llm_classify"""
    url = (s.get("ki_url") or "http://127.0.0.1:11434").rstrip("/")
    model = s.get("ki_model") or ""
    if not model:
        tags = json.loads(urllib.request.urlopen(url + "/api/tags", timeout=4).read().decode())
        names = [t["name"] for t in tags.get("models", [])]
        pref = [n for n in names if re.match(r"(qwen|llama|mistral|gemma|phi)", n)]
        model = (pref or names or [""])[0]
        if not model:
            raise RuntimeError("Kein Modell in Ollama installiert.")
    keys = ", ".join(MAIL_URTEILE)
    prompt = ("Du prüfst E-Mails für die Buchhaltung eines Kleinunternehmers. Ist diese E-Mail eine Rechnung? "
              "Antworte NUR mit JSON: {\"urteil\":..., \"sicherheit\":0-1, \"begruendung\":\"kurz, deutsch\"}. "
              "urteil ist genau einer von: " + keys + ".\n\n"
              f"VON: {p.get('absender')} <{p.get('absender_addr')}>\nBETREFF: {p.get('betreff')}\n"
              f"ANHAENGE: {', '.join(a['name'] for a in p.get('atts') or [])}\n\nTEXT:\n" + (p.get("text") or "")[:3000])
    body = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(url + "/api/generate", body, {"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=int(s.get("ki_timeout") or 45)).read().decode())
    r = json.loads(out.get("response") or "{}")
    r["_model"] = model
    return r


def mail_classify_full(p, atts_info, llm_budget=None):
    r = mail_classify(p, atts_info)
    s = get_settings()
    if s.get("ki_enabled") and r["sicherheit"] < MAIL_UNSICHER and (llm_budget is None or llm_budget[0] > 0):
        if llm_budget is not None:
            llm_budget[0] -= 1
        try:
            l = mail_llm(p, s)
            u = l.get("urteil")
            try:
                c = max(0.0, min(1.0, float(str(l.get("sicherheit") or 0.6).replace(",", "."))))
            except Exception:
                c = 0.6
            if u in MAIL_URTEILE:
                r["begruendung"].append(f"Dr. Jey ({l['_model']}): {MAIL_URTEILE[u]} {int(c * 100)} %" + (f" – {l.get('begruendung')}" if l.get("begruendung") else ""))
                if u == r["urteil"]:
                    r["sicherheit"] = round(min(0.95, r["sicherheit"] + 0.25 * c), 2)
                elif c >= 0.6:
                    r["urteil"] = u
                    r["sicherheit"] = round(min(0.85, 0.5 + 0.3 * c), 2)
        except Exception as e:
            r["begruendung"].append(f"Dr. Jey nicht erreichbar ({str(e)[:60]})")
    return r


# ---------------- import / storage ----------------
def _mail_folder(p, h):
    ym = (p.get("datum") or now_iso())[:7]
    stamp = re.sub(r"[^0-9]", "", (p.get("datum") or now_iso()))[:14]
    sub = re.sub(r"[^\w\-]+", "_", (p.get("betreff") or "ohne_Betreff"))[:40].strip("_") or "Mail"
    d = os.path.join(mail_dir(), ym, f"{stamp[:8]}_{stamp[8:14]}_{sub}_{h[:6]}")
    os.makedirs(d, exist_ok=True)
    return d


def mail_find_dup(msgid, h):
    if msgid:
        r = q("SELECT id, status FROM mail_inbox WHERE msgid=? LIMIT 1", (msgid,), one=True)
        if r:
            return r
    return q("SELECT id, status FROM mail_inbox WHERE hash=? LIMIT 1", (h,), one=True)


def mail_import_raw(raw, ext=".eml", quelle="Datei", datei="", llm_budget=None):
    """import one mail (raw bytes). ext .eml or .msg. -> dict(status neu/doppelt/fehler, id, urteil)"""
    h = hashlib.sha1(raw).hexdigest()
    tmp = None
    try:
        if ext == ".msg":
            tmp = _tmp_for("mail.msg")
            write_file(tmp, raw)
            p = mail_parse_msg(tmp)
        else:
            p = mail_parse_eml(raw)
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except Exception:
                pass
    with MAIL_LOCK:
        dup = mail_find_dup(p.get("msgid"), h)
        if dup:
            return {"status": "doppelt", "id": dup["id"], "betreff": p.get("betreff")}
        other_docs = any(os.path.splitext(a["name"].lower())[1] in ATT_DOC_EXT for a in p["atts"])
        infos, seen = [], set()
        for a in p["atts"][:40]:
            hh = hashlib.sha1(a["data"]).hexdigest()
            if hh in seen:
                continue
            seen.add(hh)
            i = mail_att_info(a["name"], a["data"], a.get("inline"), other_docs)
            i["_data"] = a["data"]
            infos.append(i)
        r = mail_classify_full(p, infos, llm_budget)
        folder = _mail_folder(p, h)
        write_file(os.path.join(folder, "mail" + (".msg" if ext == ".msg" else ".eml")), raw)
        used = {"mail.eml", "mail.msg", "mail.pdf"}
        for i in infos:
            data = i.pop("_data")
            if i["art"] in ("logo", "leer"):
                i["file"] = ""
                continue
            nm = safe_name(i["name"])
            base, e_ = os.path.splitext(nm)
            k = 2
            while nm.lower() in used:
                nm = f"{base}_{k}{e_}"
                k += 1
            used.add(nm.lower())
            write_file(os.path.join(folder, nm), data)
            i["file"] = os.path.relpath(os.path.join(folder, nm), DATA_DIR)
        meta = {"links": p.get("links", [])[:60], "list_unsub": p.get("list_unsub"), "precedence": p.get("precedence"),
                "auto": p.get("auto")}
        mid = x("INSERT INTO mail_inbox (msgid, hash, quelle, datei, absender, absender_addr, empfaenger, betreff, datum, text, anhaenge, meta, "
                "urteil, sicherheit, begruendung, betrag, status, ordner, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.get("msgid") or "", h, quelle, datei[:200], p.get("absender", "")[:200], p.get("absender_addr", "")[:200],
                 p.get("empfaenger", ""), p.get("betreff", "")[:500], p.get("datum") or now_iso(), (p.get("text") or "")[:30000],
                 json.dumps(infos, ensure_ascii=False, default=str), json.dumps(meta, ensure_ascii=False), r["urteil"], r["sicherheit"],
                 json.dumps(r["begruendung"], ensure_ascii=False), r["betrag"], "neu", os.path.relpath(folder, DATA_DIR), now_iso(), now_iso()))
    return {"status": "neu", "id": mid, "betreff": p.get("betreff"), "urteil": r["urteil"], "sicherheit": r["sicherheit"]}


def mail_import_file(path, filename, quelle="Datei"):
    """.eml / .msg / .mbox file -> summary"""
    ext = os.path.splitext(filename.lower())[1]
    out = {"ok": True, "neu": 0, "doppelt": 0, "fehler": 0, "items": [], "datei": filename}
    budget = [10]
    if ext in (".mbox", ".mbx") or (ext not in (".eml", ".msg") and open(path, "rb").read(5) == b"From "):
        mb = mailbox.mbox(path, create=False)
        try:
            for k, msg in enumerate(mb):
                if k >= 3000:
                    break
                try:
                    r = mail_import_raw(msg.as_bytes(), ".eml", quelle + " (mbox)", filename, budget)
                except Exception as e:
                    traceback.print_exc()
                    r = {"status": "fehler", "error": str(e)[:120]}
                out[r["status"]] = out.get(r["status"], 0) + 1
                out["items"].append(r)
        finally:
            mb.close()
    elif ext in (".eml", ".msg"):
        try:
            r = mail_import_raw(open(path, "rb").read(), ext, quelle, filename, budget)
        except Exception as e:
            traceback.print_exc()
            r = {"status": "fehler", "error": str(e)[:160]}
        out[r["status"]] = out.get(r["status"], 0) + 1
        out["items"].append(r)
    else:
        raise ValueError(f"„{filename}“ ist keine E-Mail-Datei (.eml, .msg oder .mbox).")
    return out


# ---------------- list / detail ----------------
MAIL_LIST_COLS = "id, quelle, absender, absender_addr, betreff, datum, urteil, sicherheit, betrag, status, belege, anhaenge, created, gelesen"


def mail_row_short(r):
    atts = json.loads(r.get("anhaenge") or "[]")
    r = dict(r)
    r["anhaenge"] = len([a for a in atts if a.get("art") not in ("logo", "leer")])
    r["urteil_text"] = MAIL_URTEILE.get(r["urteil"], r["urteil"])
    r["rechnung"] = r["urteil"] in MAIL_BELEG_URTEILE
    return r


def mail_list():
    rows = [mail_row_short(r) for r in q(f"SELECT {MAIL_LIST_COLS} FROM mail_inbox WHERE status!='geloescht' ORDER BY datum DESC, id DESC LIMIT 3000")]
    return {"items": rows, "urteile": MAIL_URTEILE, "unsicher": MAIL_UNSICHER, "imap": mail_imap_brief(), "handy": handy_brief()}


def mail_imap_brief():
    try:
        return imap_status()
    except Exception:
        return {}


def handy_brief():
    try:
        return handy_status()
    except Exception:
        return {}


def mail_get(mid):
    if not str(mid or "").isdigit():
        raise ValueError("E-Mail nicht gefunden.")
    r = q("SELECT * FROM mail_inbox WHERE id=?", (int(mid),), one=True)
    if not r:
        raise ValueError("E-Mail nicht gefunden.")
    r["anhaenge"] = json.loads(r["anhaenge"] or "[]")
    r["begruendung"] = json.loads(r["begruendung"] or "[]")
    r["meta"] = json.loads(r["meta"] or "{}")
    r["urteil_text"] = MAIL_URTEILE.get(r["urteil"], r["urteil"])
    r["text"] = (r["text"] or "")[:60000]     # v3.2.0: whole mail for reading (was 6000)
    r.update(mail_read_view(r.get("ordner")))
    if not r.get("gelesen"):
        x("UPDATE mail_inbox SET gelesen=1 WHERE id=?", (r["id"],))
    mem = mail_sender_memory(r["absender_addr"])
    r["absender_info"] = mem
    r["links"] = [l_ for l_ in r["meta"].get("links", []) if re.search(r"rechnung|invoice|beleg|download|portal|konto|pdf", (l_.get("text", "") + " " + l_.get("url", "")).lower())][:8]
    return r


def mail_read_view(ordner):
    """v3.2.0: reading view of the stored original - HTML part (cid images inline, no forms/frames/refresh),
    plus To/Cc/Reply-To from the header. .msg: HTML body and To/Cc straight from the Outlook file (olefile)."""
    out = {"html": "", "an": "", "cc": "", "antwort_an": ""}
    if not ordner:
        return out
    folder = os.path.join(DATA_DIR, ordner)
    eml, msg = os.path.join(folder, "mail.eml"), os.path.join(folder, "mail.msg")
    try:
        if os.path.isfile(eml):
            fn = globals().get("_mp_html")            # m98_mail: same viewer as "Privat-Mails"
            out["html"] = fn(eml) if fn else ""
            raw = open(eml, "rb").read(200000)
            m = email.message_from_bytes(_mail_fix_headers(raw), policy=email.policy.default)
            out["an"] = _hdr(m.get("To", ""))[:1000]
            out["cc"] = _hdr(m.get("Cc", ""))[:1000]
            rt = _hdr(m.get("Reply-To", ""))
            out["antwort_an"] = rt[:300] if rt and rt != _hdr(m.get("From", "")) else ""
        elif os.path.isfile(msg):
            out.update(_mail_msg_view(msg))
    except Exception:
        traceback.print_exc()
    if out["html"]:
        # form fields are useless in the viewer (sandbox without forms) - remove them instead of showing empty boxes
        out["html"] = re.sub(r"<(input|button|select|textarea)\b[^>]*>", "", out["html"], flags=re.I)
    return out


def _mail_msg_view(path):
    """Outlook .msg (OLE): PR_HTML (0x1013), PR_DISPLAY_TO (0x0E04), PR_DISPLAY_CC (0x0E03); no extra package needed"""
    out = {}
    import olefile
    ole = olefile.OleFileIO(path)
    try:
        def rd(name):
            return ole.openstream(name).read() if ole.exists(name) else None
        for k, sid in (("an", "0E04"), ("cc", "0E03")):
            b = rd(f"__substg1.0_{sid}001F")
            if b:
                out[k] = b.decode("utf-16-le", "replace").rstrip("\x00")[:1000]
            else:
                b = rd(f"__substg1.0_{sid}001E")
                if b:
                    out[k] = b.decode("cp1252", "replace").rstrip("\x00")[:1000]
        hb = rd("__substg1.0_10130102") or rd("__substg1.0_1013001E")
        if hb:
            m = re.search(rb"charset\s*=\s*[\"']?([\w-]+)", hb[:3000], re.I)
            enc = m.group(1).decode() if m else "utf-8"
            try:
                html = hb.decode(enc)
            except Exception:
                html = hb.decode("cp1252", "replace")
            html = html.split("\x00", 1)[0]      # stream is padded with NUL bytes
            html = re.sub(r"<meta[^>]+http-equiv\s*=\s*[\"']?refresh[^>]*>", "", html, flags=re.I)
            out["html"] = re.sub(r"<(base|link|iframe|frame|object|embed|form)\b[^>]*>", "", html, flags=re.I)[:3000000]
    finally:
        ole.close()
    return out


def mail_mark_read(d):
    ids = _mail_ids(d)
    if ids:
        x(f"UPDATE mail_inbox SET gelesen=? WHERE id IN ({','.join('?' * len(ids))})", (1 if d.get("gelesen", True) else 0, *ids))
    return {"ok": True, "n": len(ids)}


def mail_reclassify(ids=None):
    rows = q("SELECT * FROM mail_inbox WHERE status='neu'" + (f" AND id IN ({','.join('?' * len(ids))})" if ids else ""), tuple(ids or ()))
    n = 0
    budget = [5]
    for r in rows:
        meta = json.loads(r["meta"] or "{}")
        p = {"betreff": r["betreff"], "text": r["text"], "links": meta.get("links", []), "list_unsub": meta.get("list_unsub"),
             "precedence": meta.get("precedence") or "", "absender": r["absender"], "absender_addr": r["absender_addr"], "atts": []}
        infos = json.loads(r["anhaenge"] or "[]")
        p["atts"] = [{"name": a["name"]} for a in infos]
        res = mail_classify_full(p, infos, budget)
        x("UPDATE mail_inbox SET urteil=?, sicherheit=?, begruendung=?, betrag=?, updated=? WHERE id=?",
          (res["urteil"], res["sicherheit"], json.dumps(res["begruendung"], ensure_ascii=False), res["betrag"], now_iso(), r["id"]))
        n += 1
    return n


# ---------------- actions ----------------
def mail_text_pdf(r, path):
    """render the mail (header + text) as a simple PDF so it can be filed as a Beleg"""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor
    from xml.sax.saxutils import escape as xesc
    st = font_stylesheet()
    hs = ParagraphStyle("h", parent=st["Normal"], fontName=FONT_B(), fontSize=13, textColor=HexColor("#5b3fd6"), spaceAfter=6)
    ns = ParagraphStyle("n", parent=st["Normal"], fontName=FONT_R(), fontSize=9.5, leading=12.5)
    ms = ParagraphStyle("m", parent=ns, textColor=HexColor("#555555"))
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50,
                            title=r.get("betreff") or "E-Mail", author="T. Pfeiffer")
    el = [Paragraph(xesc(r.get("betreff") or "(ohne Betreff)"), hs)]
    for lbl, v in (("Von", f"{r.get('absender') or ''} <{r.get('absender_addr') or ''}>"), ("An", r.get("empfaenger") or ""),
                   ("Datum", de_date((r.get("datum") or "")[:10]) + " " + (r.get("datum") or "")[11:16])):
        if v.strip(" <>"):
            el.append(Paragraph(f"<b>{lbl}:</b> {xesc(v)}", ms))
    el.append(Spacer(1, 10))
    for para in re.split(r"\n\s*\n", (r.get("text") or "")[:30000]):
        t = xesc(para.strip()).replace("\n", "<br/>")
        if t:
            el.append(Paragraph(t, ns))
            el.append(Spacer(1, 5))
    doc.build(el)


def _pending_add(src, name, hint, mail_row):
    """copy a file into a temp file and put the analysis into pending_belege (like eingang_scan)"""
    tmp = _tmp_for(name)
    shutil.copy(src, tmp)
    n = 0
    for res in prepare_results(analyze_any(tmp, name), tmp, name):
        TMP.pop(res.get("token"), None)
        res.pop("token", None)
        res["hint"] = (hint + " " + (res.get("hint") or "")).strip()
        res["mail_id"] = mail_row["id"]
        nm = res.get("filename") or name
        x("INSERT INTO pending_belege (file, name, result, created) VALUES (?,?,?,?)",
          (res["tmp"], nm, json.dumps(res, ensure_ascii=False, default=str), now_iso()))
        try:
            x("INSERT INTO eingang_log (datum, file, typ, betrag, partner, status, info) VALUES (?,?,?,?,?,?,?)",
              (now_iso(), f"E-Mail » {nm}", res.get("typ"), res.get("betrag") or 0, res.get("partner", ""), "prüfen",
               f"aus E-Mail von {mail_row.get('absender') or mail_row.get('absender_addr')}"))
        except Exception:
            traceback.print_exc()
        n += 1
    return n


def _pending_add_text(r, folder):
    """mail without usable attachment -> PDF of the mail text, analysed with the mail text"""
    pdf = os.path.join(folder, "mail.pdf")
    if not os.path.exists(pdf):
        mail_text_pdf(r, pdf)
    nm = safe_name(f"E-Mail {(r.get('absender') or '')[:30]} {(r.get('betreff') or '')[:50]}".strip()) + ".pdf"
    tmp = _tmp_for(nm)
    shutil.copy(pdf, tmp)
    text = f"Betreff: {r.get('betreff')}\n\n{r.get('text') or ''}\n\nVon: {r.get('absender')} <{r.get('absender_addr')}>\nDatum: {de_date((r.get('datum') or '')[:10])}\n"
    res = analyze_text(tmp, nm, text, "E-Mail")
    if not res.get("datum") and r.get("datum"):
        res["datum"] = r["datum"][:10]
    if r.get("absender") or r.get("absender_addr"):
        # the sender is the most reliable partner for a mail without a document
        res["partner"] = (r.get("absender") or r.get("absender_addr") or "")[:80]
    if r.get("betrag"):
        # mail classifier only takes amounts with EUR/currency sign -> more reliable than the generic rule
        res["betrag"] = r["betrag"]
    items = prepare_results([res], tmp, nm)
    n = 0
    for res in items:
        TMP.pop(res.get("token"), None)
        res.pop("token", None)
        res["hint"] = ("Rechnung aus dem Mailtext. " if r["urteil"] != "rechnung_link" else
                       "Achtung: Rechnung liegt nur online – Original herunterladen und nachreichen. ") + (res.get("hint") or "")
        res["mail_id"] = r["id"]
        x("INSERT INTO pending_belege (file, name, result, created) VALUES (?,?,?,?)",
          (res["tmp"], nm, json.dumps(res, ensure_ascii=False, default=str), now_iso()))
        x("INSERT INTO eingang_log (datum, file, typ, betrag, partner, status, info) VALUES (?,?,?,?,?,?,?)",
          (now_iso(), f"E-Mail » {nm}", res.get("typ"), res.get("betrag") or 0, res.get("partner", ""), "prüfen", "Mailtext"))
        n += 1
    return n


def mail_take(ids):
    # v2.6.3: serialized - two parallel requests (double click) put the same mail twice into the review list
    with MAIL_LOCK:
        return _mail_take(ids)


def _mail_take(ids):
    total, done = 0, 0
    for mid in ids:
        r = q("SELECT * FROM mail_inbox WHERE id=?", (int(mid),), one=True)
        if not r or r["status"] in ("geloescht", "uebernommen"):   # v2.0.6: no duplicates in the review list
            continue
        folder = os.path.join(DATA_DIR, r["ordner"])
        atts = json.loads(r["anhaenge"] or "[]")
        avail = [a for a in atts if a.get("file") and os.path.exists(os.path.join(DATA_DIR, a["file"]))]
        chosen = [a for a in avail if a.get("erechnung") or a.get("art") == "erechnung"]
        if not chosen:
            chosen = [a for a in avail if a.get("art") in ("rechnung", "gutschrift", "mahnung")]
        if not chosen and r["urteil"] not in ("rechnung_text", "rechnung_link"):
            chosen = [a for a in avail if a.get("art") in ("dokument", "bild")]
        n = 0
        hint = f"Aus E-Mail „{(r['betreff'] or '')[:60]}“ von {r['absender'] or r['absender_addr']}."
        for a in chosen:
            n += _pending_add(os.path.join(DATA_DIR, a["file"]), a["name"], hint, r)
        if not chosen:
            n += _pending_add_text(r, folder)
        x("UPDATE mail_inbox SET status='uebernommen', belege=belege+?, updated=? WHERE id=?", (n, now_iso(), r["id"]))
        if r["status"] != "uebernommen":
            mail_learn_sender(r["absender_addr"], True)
        total += n
        done += 1
    return {"ok": True, "mails": done, "belege": total}


def mail_mark_none(ids):
    n = 0
    for mid in ids:
        r = q("SELECT id, absender_addr, status FROM mail_inbox WHERE id=?", (int(mid),), one=True)
        if not r or r["status"] == "geloescht":
            continue
        x("UPDATE mail_inbox SET status='keine', urteil='keine', updated=? WHERE id=?", (now_iso(), r["id"]))
        if r["status"] != "keine":
            mail_learn_sender(r["absender_addr"], False)
        n += 1
    return {"ok": True, "n": n}


def mail_delete(ids):
    n = 0
    trash = os.path.join(DATA_DIR, "_Papierkorb", MAIL_DIRNAME)
    for mid in ids:
        r = q("SELECT id, ordner FROM mail_inbox WHERE id=?", (int(mid),), one=True)
        if not r:
            continue
        src = os.path.join(DATA_DIR, r["ordner"] or "")
        if r["ordner"] and os.path.isdir(src):
            try:
                os.makedirs(trash, exist_ok=True)
                dst = os.path.join(trash, os.path.basename(src))
                if os.path.exists(dst):
                    dst += "_" + uuid.uuid4().hex[:4]
                shutil.move(src, dst)
            except Exception:
                traceback.print_exc()
        # tombstone: keeps msgid/hash so the mail is not imported again
        x("UPDATE mail_inbox SET status='geloescht', text='', anhaenge='[]', meta='{}', ordner='', updated=? WHERE id=?", (now_iso(), r["id"]))
        n += 1
    return {"ok": True, "n": n}


def mail_reset_sender(addr):
    x("DELETE FROM mail_absender WHERE addr=?", ((addr or "").lower(),))
    return {"ok": True}


# ---------------- HTTP ----------------
def _mail_ids(d):
    ids = d.get("ids") or ([d["id"]] if d.get("id") else [])
    return [int(i) for i in ids]


def _up_mail(h, tmp, name):
    try:
        r = mail_import_file(tmp, name)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    return h._send(200, r)


HOOK_UPLOAD["/api/upload/mail"] = _up_mail
HOOK_GET["/api/mail/list"] = lambda h, qs: h._send(200, mail_list())
HOOK_GET["/api/mail/get"] = lambda h, qs: h._send(200, mail_get(qs.get("id")))
HOOK_POST["/api/mail/uebernehmen"] = lambda h, d: h._send(200, mail_take(_mail_ids(d)))
HOOK_POST["/api/mail/keine"] = lambda h, d: h._send(200, mail_mark_none(_mail_ids(d)))
HOOK_POST["/api/mail/loeschen"] = lambda h, d: h._send(200, mail_delete(_mail_ids(d)))
HOOK_POST["/api/mail/neu_bewerten"] = lambda h, d: h._send(200, {"ok": True, "n": mail_reclassify(_mail_ids(d) or None)})
HOOK_POST["/api/mail/absender_vergessen"] = lambda h, d: h._send(200, mail_reset_sender(d.get("addr")))
HOOK_POST["/api/mail/gelesen"] = lambda h, d: h._send(200, mail_mark_read(d))


def mail_open_original(d):
    """v3.2.0: open the stored .eml/.msg in the default mail program (Outlook, Thunderbird, Windows Mail)"""
    r = q("SELECT ordner FROM mail_inbox WHERE id=?", (int(d.get("id") or 0),), one=True)
    if not r or not r["ordner"]:
        raise ValueError("Original nicht vorhanden.")
    for fn in ("mail.eml", "mail.msg"):
        f_ = os.path.join(DATA_DIR, r["ordner"], fn)
        if os.path.isfile(f_):
            return {"ok": open_path(f_)}
    raise ValueError("Original nicht vorhanden.")


def mail_reply(d):
    """v3.2.0: answer in the default mail program (mailto:) - recipient, AW: subject, quoted beginning of the text"""
    import urllib.parse
    r = q("SELECT absender, absender_addr, datum, text FROM mail_inbox WHERE id=?", (int(d.get("id") or 0),), one=True)
    if not r:
        raise ValueError("E-Mail nicht gefunden.")
    to = str(d.get("to") or r["absender_addr"] or "").strip()
    if not re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", to):
        raise ValueError("Keine gültige Absender-Adresse.")
    txt = (r["text"] or "").strip()[:1200]
    head = f"Am {(r['datum'] or '')[:10]} schrieb {r['absender'] or to}:"
    body = "\r\n\r\n\r\n" + head + "\r\n" + "\r\n".join("> " + l_ for l_ in txt.splitlines())
    url = "mailto:" + to + "?subject=" + urllib.parse.quote(str(d.get("betreff") or "")[:250]) + "&body=" + urllib.parse.quote(body)
    if sys.platform.startswith("win"):
        os.startfile(url)  # noqa
    else:
        webbrowser.open(url)
    return {"ok": True}


HOOK_POST["/api/mail/original"] = lambda h, d: h._send(200, mail_open_original(d))
HOOK_POST["/api/mail/antworten"] = lambda h, d: h._send(200, mail_reply(d))


def mail_open_link(d):
    """open a link of a stored mail in the default browser (only links that belong to that mail)"""
    r = q("SELECT meta FROM mail_inbox WHERE id=?", (int(d.get("id") or 0),), one=True)
    url = d.get("url") or ""
    links = [l_.get("url") for l_ in json.loads((r or {}).get("meta") or "{}").get("links", [])]
    if not r or url not in links or not url.lower().startswith(("http://", "https://")):
        raise ValueError("Link nicht gefunden.")
    webbrowser.open(url)
    return {"ok": True}


HOOK_POST["/api/mail/link"] = lambda h, d: h._send(200, mail_open_link(d))


def _mail_boot(d):
    # mi_pass is removed from the settings by _imap_boot (m31)
    try:
        n = q("SELECT COUNT(*) n FROM mail_inbox WHERE status='neu' AND urteil IN (%s)" % ",".join("?" * len(MAIL_BELEG_URTEILE)),
              MAIL_BELEG_URTEILE, one=True)["n"]
    except Exception:
        n = 0
    try:
        u = q("SELECT COUNT(*) n FROM mail_inbox WHERE status!='geloescht' AND COALESCE(gelesen,0)=0", one=True)["n"]
    except Exception:
        u = 0
    d["mailimp"] = {"offen": n, "ungelesen": u}


HOOK_BOOT.append(_mail_boot)


# ---------------- self test ----------------
def _mail_selftest():
    err = []
    samples = [
        ({"betreff": "Ihre Rechnung 2026-1043", "absender_addr": "buchhaltung@beispiel-lieferant.de",
          "text": "Sehr geehrte Damen und Herren,\nanbei die Daten Ihrer Rechnung.\nRechnungsnummer: 2026-1043\nRechnungsdatum: 12.10.2026\n"
                  "Rechnungsbetrag: 238,00 EUR (inkl. 19 % MwSt.)\nZahlbar bis 26.10.2026 auf IBAN DE12 3456 7890 1234 5678 90.\nMit freundlichen Grüßen",
          "links": []}, "rechnung_text"),
        ({"betreff": "Unsere Herbst-Angebote: 20 % Rabatt", "absender_addr": "news@shop-beispiel.de", "list_unsub": True,
          "text": "Jetzt shoppen und sparen! Nur heute 20 % Rabatt auf alles.\nSie erhalten diesen Newsletter, weil ... Hier abmelden: https://shop.example/unsub",
          "links": [{"text": "abmelden", "url": "https://shop.example/unsub"}]}, "keine"),
        ({"betreff": "Ihre Rechnung für Oktober ist da", "absender_addr": "service@telefon-beispiel.de",
          "text": "Hallo,\nIhre neue Rechnung steht ab sofort im Kundenportal zum Download bereit.\nRechnungsbetrag: 39,99 €\n"
                  "Jetzt ansehen: https://kundenportal.example/rechnung",
          "links": [{"text": "Rechnung ansehen", "url": "https://kundenportal.example/rechnung"}]}, "rechnung_link"),
    ]
    for p, want in samples:
        try:
            r = mail_classify(p, [], use_memory=False)
            if r["urteil"] != want:
                err.append(f"Mail-Erkennung: „{p['betreff']}“ ergab {r['urteil']} statt {want}")
        except Exception as e:
            err.append(f"Mail-Erkennung Fehler: {e}")
    return err


HOOK_SELFTEST.append(_mail_selftest)


# v3.2.0: mails that were already in the program before reading existed count as read
@db_migration(3, "E-Mails: vorhandene als gelesen markieren")
def _m30_mig3():
    CON.execute("UPDATE mail_inbox SET gelesen=1 WHERE gelesen IS NULL OR gelesen=0")


def _mail_read_selftest():
    err = []
    try:
        tmp = os.path.join(DATA_DIR, MAIL_DIRNAME, "_selftest_lesen")
        os.makedirs(tmp, exist_ok=True)
        open(os.path.join(tmp, "mail.eml"), "wb").write(
            b"From: A <a@x.de>\r\nTo: B <b@y.de>\r\nCc: C <c@z.de>\r\nSubject: Test\r\nMIME-Version: 1.0\r\n"
            b"Content-Type: multipart/alternative; boundary=XX\r\n\r\n--XX\r\nContent-Type: text/plain\r\n\r\nHallo\r\n"
            b"--XX\r\nContent-Type: text/html\r\n\r\n<p>Hallo <b>Welt</b></p><form action=x></form>\r\n--XX--\r\n")
        v = mail_read_view(os.path.relpath(tmp, DATA_DIR))
        shutil.rmtree(tmp, ignore_errors=True)
        if globals().get("_mp_html") and "<b>Welt</b>" not in v["html"]:
            err.append("m30 Lesen: HTML-Teil fehlt")
        if "<form" in v["html"]:
            err.append("m30 Lesen: Formular nicht entfernt")
        if "b@y.de" not in v["an"] or "c@z.de" not in v["cc"]:
            err.append("m30 Lesen: An/Kopie fehlt")
    except Exception as e:
        err.append(f"m30 Lesen Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_mail_read_selftest)


# ============================================================================
# Teil aus m31_imap.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m31_imap  v1.0.0
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer
#
# IMAP-Postfach abrufen. Abgerufene Mails laufen durch dieselbe Analyse wie
# der Datei-Import (mail_import_raw aus m30). Passwort mit protect_secret.
# Settings: mi_host, mi_port, mi_ssl, mi_user, mi_pass (geschuetzt), mi_folder,
#           mi_interval (Minuten, 0 = aus), mi_unseen, mi_after (nichts/gelesen/verschieben),
#           mi_move_folder, mi_state (letzte UID je Ordner), mi_status (letzter Abruf)

import imaplib

IMAP_LOCK = threading.Lock()
IMAP_MAX_PER_RUN = 200
IMAP_FIRST_DAYS = 60


def imap_cfg(over=None):
    s = get_settings()
    c = {"host": (s.get("mi_host") or "").strip(), "port": int(s.get("mi_port") or 0),
         "ssl": s.get("mi_ssl", True) not in (False, 0, "0", "false"), "user": (s.get("mi_user") or "").strip(),
         "pass": "", "folder": (s.get("mi_folder") or "INBOX").strip() or "INBOX",
         "interval": int(float(s.get("mi_interval") or 0)), "unseen": bool(s.get("mi_unseen", True)),
         "after": s.get("mi_after") or "nichts", "move_folder": (s.get("mi_move_folder") or "").strip()}
    try:
        c["pass"] = unprotect_secret(s.get("mi_pass") or "")
    except Exception:
        c["pass"] = ""
    for k, v in (over or {}).items():
        if k == "pass" and not v:
            continue
        if k in c and v is not None:
            c[k] = v
    if over:
        c["port"] = int(float(c.get("port") or 0))
        c["ssl"] = c["ssl"] not in (False, 0, "0", "false")
    if not c["port"]:
        c["port"] = 993 if c["ssl"] else 143
    return c


def imap_connect(c, timeout=20):
    if not c["host"] or not c["user"]:
        raise ValueError("Bitte IMAP-Server und Benutzer eintragen.")
    if not c["pass"]:
        raise ValueError("Bitte das Passwort eintragen.")
    try:
        if c["ssl"]:
            M = imaplib.IMAP4_SSL(c["host"], c["port"], timeout=timeout)
        else:
            M = imaplib.IMAP4(c["host"], c["port"], timeout=timeout)
            if "STARTTLS" in M.capabilities:
                try:
                    M.starttls()
                except Exception as e:
                    # v2.0.6: never send the password unencrypted after a failed STARTTLS
                    try:
                        M.shutdown()
                    except Exception:
                        pass
                    raise ValueError(f"Verschlüsselung (STARTTLS) mit {c['host']} fehlgeschlagen: {e}")
    except socket.gaierror:
        raise ValueError(f"Server „{c['host']}“ nicht gefunden – Adresse oder Internetverbindung prüfen.")
    except (socket.timeout, TimeoutError):
        raise ValueError(f"Keine Antwort von {c['host']}:{c['port']} (Zeitüberschreitung) – Port/SSL prüfen.")
    except ConnectionRefusedError:
        raise ValueError(f"{c['host']}:{c['port']} lehnt die Verbindung ab – Port/SSL prüfen.")
    except OSError as e:
        raise ValueError(f"Verbindung zu {c['host']}:{c['port']} fehlgeschlagen: {e}")
    try:
        M.login(c["user"], c["pass"])
    except imaplib.IMAP4.error as e:
        try:
            M.logout()
        except Exception:
            pass
        raise ValueError("Anmeldung abgelehnt – Benutzer/Passwort prüfen (bei Gmail/Outlook ein App-Passwort verwenden). "
                         f"Server sagt: {_imap_txt(e)}")
    return M


def _imap_txt(e):
    t = str(e)
    m = re.search(r"b'(.*)'", t)
    return (m.group(1) if m else t)[:160]


def imap_utf7_enc(name):
    """folder name -> IMAP modified UTF-7 (RFC 3501 5.1.3). v2.1.0: folders with umlauts ("Eingaenge" with a-umlaut) failed with
    an 'ascii' codec error. Names that are already encoded (old settings, chosen from the server list) stay as they are."""
    name = name or ""
    if all(ord(ch) < 128 for ch in name):
        if "&" not in name or re.search(r"&[A-Za-z0-9+,]*-", name):
            return name
    out, buf = [], []

    def flush():
        if buf:
            b = base64.b64encode("".join(buf).encode("utf-16-be")).decode("ascii").rstrip("=").replace("/", ",")
            out.append("&" + b + "-")
            buf.clear()
    for ch in name:
        if 0x20 <= ord(ch) <= 0x7e:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


def imap_utf7_dec(name):
    """IMAP modified UTF-7 -> readable folder name ("Eing&AOQ-nge" -> "Eingaenge" with a-umlaut)"""
    def dec(m):
        b = m.group(1)
        if not b:
            return "&"
        b = b.replace(",", "/")
        try:
            return base64.b64decode(b + "=" * (-len(b) % 4)).decode("utf-16-be")
        except Exception:
            return m.group(0)
    return re.sub(r"&([A-Za-z0-9+,]*)-", dec, name or "")


def _imap_quote(name):
    name = imap_utf7_enc(name)
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _imap_select(M, folder, readonly=False):
    typ, data = M.select(_imap_quote(folder), readonly=readonly)
    if typ != "OK":
        raise ValueError(f"Ordner „{folder}“ nicht gefunden.")
    return int((data or [b"0"])[0] or 0)


def imap_test(over=None):
    c = imap_cfg(over)
    M = imap_connect(c)
    try:
        n = _imap_select(M, c["folder"], readonly=True)
        typ, data = M.search(None, "UNSEEN")
        unseen = len((data or [b""])[0].split()) if typ == "OK" else 0
        folders = []
        try:
            typ, lst = M.list()
            for ln in lst or []:
                s_ = ln.decode("utf-8", "replace") if isinstance(ln, bytes) else str(ln)
                m = re.search(r'"((?:[^"\\]|\\.)*)"\s*$', s_) or re.search(r'\s(\S+)\s*$', s_)
                if m:
                    folders.append(imap_utf7_dec(m.group(1).replace('\\"', '"')))
        except Exception:
            pass
        if c["after"] == "verschieben" and c["move_folder"] and folders and imap_utf7_dec(imap_utf7_enc(c["move_folder"])) not in folders:
            return {"ok": True, "info": f"Verbunden. {n} Mail(s) im Ordner „{c['folder']}“, davon {unseen} ungelesen. "
                    f"Achtung: Zielordner „{c['move_folder']}“ gibt es nicht.", "ordner": folders[:80]}
        return {"ok": True, "info": f"Verbunden. {n} Mail(s) im Ordner „{c['folder']}“, davon {unseen} ungelesen.", "ordner": folders[:80]}
    finally:
        try:
            M.logout()
        except Exception:
            pass


def imap_fetch(over=None):
    """fetch new mails -> summary; called from button and background loop"""
    if not IMAP_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Abruf läuft bereits."}
    st = {"zeit": now_iso(), "ok": False, "neu": 0, "doppelt": 0, "fehler": 0, "text": ""}
    try:
        c = imap_cfg(over)
        M = imap_connect(c)
        try:
            _imap_select(M, c["folder"])
            typ, data = M.response("UIDVALIDITY")
            uidv = (data[0].decode() if data and data[0] else "") if isinstance(data, list) else ""
            state = get_settings().get("mi_state") or {}
            key = f"{c['user']}@{c['host']}/{c['folder']}"
            prev = state.get(key) or {}
            last = int(prev.get("uid") or 0) if prev.get("uidvalidity") == uidv else 0
            crit = []
            if last:
                crit += ["UID", f"{last + 1}:*"]
            else:
                # month names must be English for IMAP (no locale dependent strftime)
                mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                d_ = datetime.date.today() - datetime.timedelta(days=IMAP_FIRST_DAYS)
                since = f"{d_.day:02d}-{mon[d_.month - 1]}-{d_.year}"
                crit += ["SINCE", since]
            if c["unseen"]:
                crit.append("UNSEEN")
            typ, data = M.uid("SEARCH", None, *crit)
            if typ != "OK":
                raise ValueError("Suche im Postfach fehlgeschlagen.")
            uids = sorted({int(u) for u in (data[0] or b"").split() if u.isdigit() and int(u) > last})
            more = len(uids) > IMAP_MAX_PER_RUN
            uids = uids[:IMAP_MAX_PER_RUN]
            # v2.0.6: failed mails are retried (max. 3 times) without blocking newer mails
            retry = {int(k): int(v) for k, v in ((prev.get("retry") or {}) if prev.get("uidvalidity") == uidv else {}).items()}
            uids = sorted(set(uids) | {u_ for u_, n_ in retry.items() if n_ < 3 and u_ <= last})
            budget = [10]
            max_uid = last
            done = []
            for u in uids:
                typ, msg = M.uid("FETCH", str(u), "(BODY.PEEK[])")
                raw = None
                for part in msg or []:
                    if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
                        raw = bytes(part[1])
                        break
                if raw is None:
                    st["fehler"] += 1
                    if u > last:
                        max_uid = max(max_uid, u)
                    retry[u] = retry.get(u, 0) + 1
                    continue
                try:
                    r = mail_import_raw(raw, ".eml", "IMAP", c["user"], budget)
                except Exception:
                    traceback.print_exc()
                    r = {"status": "fehler"}
                st[r["status"]] = st.get(r["status"], 0) + 1
                if u > last:
                    max_uid = max(max_uid, u)
                if r["status"] != "fehler":
                    done.append(u)
                    retry.pop(u, None)
                else:
                    retry[u] = retry.get(u, 0) + 1
            if done and c["after"] == "gelesen":
                M.uid("STORE", ",".join(map(str, done)), "+FLAGS", "(\\Seen)")
            elif done and c["after"] == "verschieben" and c["move_folder"]:
                uidset = ",".join(map(str, done))
                try:
                    _t, _cd = M.capability()     # v2.0.6: capabilities after login (MOVE often only listed then)
                    caps = tuple(str(b"".join(_cd) if _cd and isinstance(_cd[0], bytes) else _cd, "ascii", "ignore").upper().split()) if _cd else ()
                except Exception:
                    caps = getattr(M, "capabilities", ()) or ()
                if "MOVE" in caps:
                    typ, _d = M.uid("MOVE", uidset, _imap_quote(c["move_folder"]))
                else:
                    typ, _d = M.uid("COPY", uidset, _imap_quote(c["move_folder"]))
                    if typ == "OK":
                        M.uid("STORE", uidset, "+FLAGS", "(\\Deleted)")
                        if "UIDPLUS" in caps:
                            M.uid("EXPUNGE", uidset)   # only our mails, not others marked as deleted
                        else:
                            M.expunge()
                if typ != "OK":
                    st["text"] = f"Verschieben nach „{c['move_folder']}“ fehlgeschlagen. "
            state[key] = {"uidvalidity": uidv, "uid": max_uid, "retry": {str(k): v for k, v in retry.items() if v < 3}}
            set_setting("mi_state", state)
            st["ok"] = True
            st["text"] += f"{st['neu']} neu, {st['doppelt']} schon vorhanden" + (f", {st['fehler']} Fehler" if st["fehler"] else "") + \
                (" – weitere Mails beim nächsten Abruf" if more else "")
        finally:
            try:
                M.logout()
            except Exception:
                pass
    except ValueError as e:
        st["text"] = str(e)
    except Exception as e:
        traceback.print_exc()
        st["text"] = f"Fehler beim Abruf: {e}"
    finally:
        set_setting("mi_status", st)
        IMAP_LOCK.release()
    return dict(st, error=None if st["ok"] else st["text"])


def imap_status():
    s = get_settings()
    return {"eingerichtet": bool((s.get("mi_host") or "").strip() and (s.get("mi_user") or "").strip() and s.get("mi_pass")),
            "intervall": int(float(s.get("mi_interval") or 0)), "letzter": s.get("mi_status") or {},
            "laeuft": IMAP_LOCK.locked(), "passwort": bool(s.get("mi_pass"))}


def imap_save(d):
    keys = {"host": "mi_host", "port": "mi_port", "ssl": "mi_ssl", "user": "mi_user", "folder": "mi_folder", "interval": "mi_interval",
            "unseen": "mi_unseen", "after": "mi_after", "move_folder": "mi_move_folder"}
    for k, sk in keys.items():
        if k in d:
            set_setting(sk, d[k])
    if d.get("pass"):
        set_setting("mi_pass", protect_secret(d["pass"]))
    if d.get("pass_loeschen"):
        set_setting("mi_pass", "")
    return {"ok": True, "status": imap_status()}


def imap_loop():
    time.sleep(15)
    while True:
        try:
            c = imap_cfg()
            if c["interval"] > 0 and c["host"] and c["user"] and c["pass"]:
                last = (get_settings().get("mi_status") or {}).get("zeit") or ""
                due = True
                if last:
                    try:
                        dt = datetime.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                        due = (datetime.datetime.now() - dt).total_seconds() >= c["interval"] * 60
                    except Exception:
                        due = True
                if due:
                    imap_fetch()
        except Exception:
            traceback.print_exc()
        time.sleep(30)


HOOK_START.append(imap_loop)


def _imap_over(d):
    o = {k: d.get(k) for k in ("host", "port", "ssl", "user", "pass", "folder", "unseen", "after", "move_folder") if k in d}
    return o or None


def _imap_test_route(h, d):
    return h._send(200, imap_test(_imap_over(d)))


def _imap_fetch_route(h, d):
    r = imap_fetch()
    if not r.get("ok"):
        raise ValueError(r.get("error") or "Abruf fehlgeschlagen.")
    return h._send(200, r)


HOOK_POST["/api/mail/imap/test"] = _imap_test_route
HOOK_POST["/api/mail/imap/abrufen"] = _imap_fetch_route
HOOK_POST["/api/mail/imap/speichern"] = lambda h, d: h._send(200, imap_save(d))
HOOK_GET["/api/mail/imap/status"] = lambda h, qs: h._send(200, imap_status())


def _imap_boot(d):
    st = d.get("settings") or {}
    st.pop("mi_pass", None)
    st.pop("mi_state", None)
    st["mi_pass_set"] = bool(get_settings().get("mi_pass"))


HOOK_BOOT.append(_imap_boot)
