# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m80_regelbesteuerung (v2.0.19)
# Vorbereitung und Umschaltung von der Kleinunternehmerregelung (par. 19 UStG) auf die Regelbesteuerung.
#  - Einstellung "Regelbesteuerung ab" (Stichtag). Leer = Kleinunternehmer = Verhalten wie bisher, unveraendert.
#  - Ab Stichtag: USt-Satz je Position (19 / 7 / 0), Preise netto, Summe der Rechnung = Brutto,
#    PDF mit Nettobetrag, USt je Satz und Gesamtbetrag, par. 19-Hinweis entfaellt, XRechnung/ZUGFeRD Kategorie S.
#  - Jede Rechnung merkt sich ihren Modus (invoices.ust_modus 'ku' / 'regel'): festgeschriebene Rechnungen
#    werden immer so nachgedruckt, wie sie ausgestellt wurden; Storno uebernimmt Modus und Saetze des Originals.
#  - Belege: Vorsteuer (details.vorsteuer) - Erkennung aus dem PDF-Text oder Eingabe.
#  - UStVA-Werte je Monat / Quartal / Jahr (Kz 81, 86, 66, 83) mit Faelligkeit, Ist- oder Soll-Versteuerung.
#  - EUER-Aufteilung (Kz 112 / 140 / 185 / 186) fuer m79.
#  - "Was waere wenn": Auswirkungen der Regelbesteuerung auf ein Jahr.
# Rechnungs-PDF: der Basis-Renderer aus m02 wird zur Ladezeit per Quelltext-Umbau um einen Summenblock
# erweitert (nur aktiv, wenn inv["_m80"] gesetzt ist); alle Ummantelungen (m50, m62 ...) bleiben erhalten.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M80_VERSION = "1.0.0"
M80_DEFAULTS = {"ab": "", "versteuerung": "ist", "zeitraum": "quartal", "dfv": False, "satz": 19.0}
M80_SAETZE = (19.0, 7.0, 0.0)
M80_KAT_ZAHLUNG = "Umsatzsteuer-Zahlung (Finanzamt)"
M80_KAT_ERSTATTUNG = "Umsatzsteuer-Erstattung"
M80_KU_RX = re.compile(r"[^\n.]*(§\s*19|Kleinunternehmer)[^\n.]*\.?", re.I)
M80_PATCH = {"ok": False, "msg": ""}


def m80_cfg():
    c = dict(M80_DEFAULTS)
    c.update(get_settings().get("m80") or {})
    return c


def m80_ab():
    a = (m80_cfg().get("ab") or "").strip()
    return a if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a) else ""


def m80_regel_on(datum):
    a = m80_ab()
    return bool(a) and (str(datum or today())[:10] >= a)


def _m80_schema():
    for tbl, cols in (("items", [("ust_satz", "REAL")]),
                      ("invoices", [("ust_modus", "TEXT"), ("netto", "REAL"), ("ust", "REAL"), ("ust_detail", "TEXT")])):
        have = {r["name"] for r in q(f"PRAGMA table_info({tbl})")}
        for n, decl in cols:
            if n not in have:
                x(f"ALTER TABLE {tbl} ADD COLUMN {n} {decl}")
    _m80_kategorien()


HOOK_SCHEMA.append(_m80_schema)


def _m80_kategorien():
    """the USt payment category is offered only once a Stichtag is set (KU users see no change)"""
    if m80_ab():
        for k in (M80_KAT_ZAHLUNG,):
            if k not in EUER_KATEGORIEN:
                EUER_KATEGORIEN.append(k)

# ---------------------------------------------------------------------------
# Invoice mode and amounts
# ---------------------------------------------------------------------------


def m80_inv_regel(inv):
    if not inv:
        return False
    if (inv.get("typ") or "rechnung") not in ("rechnung", "storno", "angebot", "auftrag"):
        return False
    m = inv.get("ust_modus")
    if m == "regel":
        return True
    if m == "ku":
        return False
    if inv.get("locked"):
        return False        # issued before the Stichtag existed -> stays Kleinunternehmer
    return m80_regel_on(inv.get("datum"))


def m80_item_satz(it, default=None):
    d = m80_cfg().get("satz") if default is None else default
    for k in ("ust_satz", "ust"):
        v = it.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except Exception:
                pass
    try:
        return float(d)
    except Exception:
        return 19.0


def m80_ust_block(inv):
    """None for Kleinunternehmer documents, else {netto, saetze:[{satz, netto, ust}], ust, brutto}"""
    if not m80_inv_regel(inv):
        return None
    by = {}
    for it in inv.get("items") or []:
        t = item_total(inv, it)
        s_ = m80_item_satz(it)
        by[s_] = round(by.get(s_, 0.0) + t, 2)
    saetze = []
    for s_ in sorted(by, reverse=True):
        net = round(by[s_], 2)
        u = round(net * s_ / 100.0 + (1e-9 if net >= 0 else -1e-9), 2)
        saetze.append({"satz": s_, "netto": net, "ust": u})
    netto = round(sum(r["netto"] for r in saetze), 2)
    ust = round(sum(r["ust"] for r in saetze), 2)
    return {"netto": netto, "saetze": saetze, "ust": ust, "brutto": round(netto + ust, 2)}


def m80_strip_ku(text):
    if not text:
        return text
    t = M80_KU_RX.sub("", text)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _m80_pct(v):
    return (str(int(v)) if abs(v - round(v)) < 1e-9 else num_de(v, 1)) + " %"

# ---------------------------------------------------------------------------
# Rendering: the VAT block is native in the base renderer of m02 since v3.0.0 (inv["_m80"] switches it on);
# before, this module rebuilt the m02 renderer from its source text.
# ---------------------------------------------------------------------------
M80_PATCH.update(ok=True, msg="")

@chain_step("render_invoice_pdf", "m80_regelbesteuerung")
def _m80_step_render_invoice_pdf(_next, inv, s=None, attachments=True):
    if not inv or not m80_inv_regel(inv):
        return _next(inv, s, attachments)
    if inv.get("_mahnfrist"):
        # reminder (pseudo document of create_mahnung): the invoice line is already gross, fees / interest / 40 EUR
        # are not taxable -> no VAT block on top, only the par. 19 note goes
        inv2 = dict(inv)
        inv2["foottext"] = m80_strip_ku(inv.get("foottext") or "")
        return _next(inv2, s, attachments)
    inv2 = dict(inv)
    items = [dict(it) for it in (inv.get("items") or [])]
    std = float(m80_cfg().get("satz") or 19)
    rates = {m80_item_satz(it) for it in items}
    if len(rates) > 1 or (rates and rates != {std}):
        for it in items:
            mark = f"USt {_m80_pct(m80_item_satz(it))}"
            it["descr"] = ((it.get("descr") or "").rstrip() + "\n" + mark).strip()
    inv2["items"] = items
    if not inv.get("locked"):
        inv2["foottext"] = m80_strip_ku(inv.get("foottext") or "")
    inv2["_m80"] = True
    return _next(inv2, s, attachments)

# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------
def _m80_decide(d):
    """-> (regel: bool, ref_items: list | None)"""
    typ = d.get("typ") or "rechnung"
    if typ not in ("rechnung", "storno", "angebot", "auftrag"):
        return False, None
    ref = None
    if d.get("ref_id"):
        ref = q("SELECT * FROM invoices WHERE id=?", (d["ref_id"],), one=True)
    ref_items = q("SELECT pos, ust_satz FROM items WHERE invoice_id=? ORDER BY pos", (ref["id"],)) if ref else None
    if typ == "storno" and ref:
        return m80_inv_regel(ref), ref_items
    if d.get("id"):
        old = q("SELECT ust_modus, locked FROM invoices WHERE id=?", (d["id"],), one=True)
        if old and old["locked"] and old["ust_modus"] in ("ku", "regel"):
            return old["ust_modus"] == "regel", ref_items
    return m80_regel_on(d.get("datum") or today()), ref_items


@chain_step("save_invoice", "m80_regelbesteuerung")
def _m80_step_save_invoice(_next, d, bump=True):
    ab = m80_ab()
    if not ab:
        return _next(d, bump)
    regel, ref_items = _m80_decide(d)
    if regel:
        if ref_items:
            for i, it in enumerate(d.get("items") or []):
                if it.get("ust_satz") in (None, "") and it.get("ust") in (None, "") and i < len(ref_items) and ref_items[i]["ust_satz"] is not None:
                    it["ust_satz"] = ref_items[i]["ust_satz"]
        if d.get("foottext"):
            d["foottext"] = m80_strip_ku(d["foottext"])
    res = _next(d, bump)
    iid = res[0]
    try:
        if regel:
            _m80_make_regel(iid, d.get("items") or [])
        else:
            x("UPDATE invoices SET ust_modus='ku', netto=summe, ust=0, ust_detail=NULL WHERE id=? AND COALESCE(ust_modus,'')!='ku'", (iid,))
    except Exception:
        traceback.print_exc()
    return res


def _m80_make_regel(iid, src_items=None):
    """store an (unlocked) document as Regelbesteuerung: rate per item, summe = gross, VAT detail.
    src_items: items as sent by the client (their ust_satz wins), else the stored items / default rate"""
    inv = get_invoice(iid)
    if not inv:
        return None
    src_items = src_items or []
    inv["ust_modus"] = "regel"
    for i, it in enumerate(inv["items"]):
        src = src_items[i] if i < len(src_items) else {}
        sz = m80_item_satz(src) if src else m80_item_satz(it)
        it["ust_satz"] = sz
        x("UPDATE items SET ust_satz=? WHERE id=?", (sz, it["id"]))
    b = m80_ust_block(inv)
    if not b:
        return None
    det = {"saetze": {str(r["satz"]): [r["netto"], r["ust"]] for r in b["saetze"]}}
    x("UPDATE invoices SET summe=?, netto=?, ust=?, ust_modus='regel', ust_detail=? WHERE id=?",
      (b["brutto"], b["netto"], b["ust"], json.dumps(det), iid))
    return b


def _m80_make_ku(iid):
    """back to Kleinunternehmer for an unlocked document: summe = sum of the (net) line totals"""
    s_ = q("SELECT COALESCE(SUM(total),0) s FROM items WHERE invoice_id=?", (iid,), one=True)["s"] or 0
    x("UPDATE invoices SET summe=?, netto=?, ust=0, ust_modus='ku', ust_detail=NULL WHERE id=?", (round(float(s_), 2), round(float(s_), 2), iid))


def _m80_refresh_m82(iid):
    # foreign currency amount (m82) follows the new gross / net total
    try:
        if "m82_doc_get" in globals() and m82_doc_get(iid):
            o = m82_doc_get(iid)
            m82_doc_set(iid, {"sprache": o["sprache"], "waehrung": o["waehrung"], "kurs": o["kurs"],
                              "kurs_datum": o["kurs_datum"], "kurs_quelle": o["kurs_quelle"]})
    except Exception:
        traceback.print_exc()


def m80_convert_unlocked():
    """after a change of the Stichtag: every unlocked document gets the mode its date asks for (same result as
    saving it again, without the side effects of a save). Locked documents are never touched (GoBD).
    -> number of converted documents"""
    n = 0
    for r in q("SELECT id, datum, ust_modus, foottext FROM invoices WHERE COALESCE(locked,0)=0 AND "
               "typ IN ('rechnung','storno','angebot','auftrag')"):
        want = m80_regel_on(r["datum"] or today())
        if want and r["ust_modus"] != "regel":
            if _m80_make_regel(r["id"]):
                if r["foottext"]:
                    x("UPDATE invoices SET foottext=? WHERE id=?", (m80_strip_ku(r["foottext"]), r["id"]))
                _m80_refresh_m82(r["id"])
                n += 1
        elif not want and r["ust_modus"] == "regel":
            _m80_make_ku(r["id"])
            _m80_refresh_m82(r["id"])
            n += 1
    return n


# safety net: a document locked (sent / paid / printed) while it still has no mode gets it right now,
# so the stored total, the UStVA and every reprint match the PDF that was issued
@chain_step("lock_invoice", "m80_regelbesteuerung")
def _m80_step_lock_invoice(_next, iid):
    try:
        if m80_ab():
            r = q("SELECT datum, locked, ust_modus, typ, status FROM invoices WHERE id=?", (iid,), one=True)
            if (r and not r["locked"] and r["ust_modus"] is None and (r["typ"] or "rechnung") in ("rechnung", "storno")
                    and r["status"] != "entwurf" and m80_regel_on(r["datum"])):
                _m80_make_regel(iid)
                _m80_refresh_m82(iid)
    except Exception:
        traceback.print_exc()
    return _next(iid)

# ---------------------------------------------------------------------------
# E-Rechnung: category S instead of E for Regelbesteuerung
# ---------------------------------------------------------------------------
@chain_step("build_xrechnung", "m80_regelbesteuerung")
def _m80_step_build_xrechnung(_next, inv, opts=None, s=None):
    xml, info = _next(inv, opts, s)
    if not m80_inv_regel(inv):
        return xml, info
    b = m80_ust_block(inv)
    t = xml.decode("utf-8")
    sign = -1.0 if (inv.get("typ") == "storno" or b["netto"] < 0) else 1.0
    t = re.sub(r'\s*<ram:IncludedNote><ram:Content>[^<]*§ 19[^<]*</ram:Content><ram:SubjectCode>REG</ram:SubjectCode></ram:IncludedNote>', "", t)
    items = inv.get("items") or []
    idx = [0]
    line_e = ('<ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>E</ram:CategoryCode>'
              '<ram:RateApplicablePercent>0</ram:RateApplicablePercent></ram:ApplicableTradeTax>')

    def cat(sz):
        return "S" if sz > 0 else "Z"

    def rep_line(m):
        i = idx[0]
        idx[0] += 1
        sz = m80_item_satz(items[i]) if i < len(items) else float(m80_cfg().get("satz") or 19)
        return (f'<ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>{cat(sz)}</ram:CategoryCode>'
                f'<ram:RateApplicablePercent>{_m50_amt(sz)}</ram:RateApplicablePercent></ram:ApplicableTradeTax>')
    t = re.sub(re.escape(line_e), rep_line, t)
    hdr = re.search(r'<ram:ApplicableTradeTax><ram:CalculatedAmount>0\.00</ram:CalculatedAmount>.*?</ram:ApplicableTradeTax>', t, re.S)
    if hdr:
        blocks = "".join(f'<ram:ApplicableTradeTax><ram:CalculatedAmount>{_m50_amt(r["ust"] * sign)}</ram:CalculatedAmount>'
                         f'<ram:TypeCode>VAT</ram:TypeCode><ram:BasisAmount>{_m50_amt(r["netto"] * sign)}</ram:BasisAmount>'
                         f'<ram:CategoryCode>{cat(r["satz"])}</ram:CategoryCode><ram:RateApplicablePercent>{_m50_amt(r["satz"])}</ram:RateApplicablePercent>'
                         f'</ram:ApplicableTradeTax>' for r in b["saetze"])
        t = t[:hdr.start()] + blocks + t[hdr.end():]
    gross = round(b["brutto"] * sign, 2)
    t = t.replace('<ram:TaxTotalAmount currencyID="EUR">0.00</ram:TaxTotalAmount>',
                  f'<ram:TaxTotalAmount currencyID="EUR">{_m50_amt(b["ust"] * sign)}</ram:TaxTotalAmount>')
    t = re.sub(r'<ram:GrandTotalAmount>[^<]*</ram:GrandTotalAmount>', f'<ram:GrandTotalAmount>{_m50_amt(gross)}</ram:GrandTotalAmount>', t)
    t = re.sub(r'<ram:DuePayableAmount>[^<]*</ram:DuePayableAmount>', f'<ram:DuePayableAmount>{_m50_amt(gross)}</ram:DuePayableAmount>', t)
    info = dict(info, summe=gross, netto=round(b["netto"] * sign, 2), ust=round(b["ust"] * sign, 2))
    if not (info.get("seller") or {}).get("ustid") and not (info.get("seller") or {}).get("steuernr"):
        info["warn"] = list(info.get("warn") or []) + ["Regelbesteuerung: USt-IdNr. oder Steuernummer des Verkäufers fehlt (Pflichtangabe)."]
    return t.encode("utf-8"), info


@chain_step("m50_check_roundtrip", "m80_regelbesteuerung")
def _m80_step_m50_check_roundtrip(_next, xml, expect_total, expect_items):
    t = xml.decode("utf-8", "ignore") if isinstance(xml, (bytes, bytearray)) else str(xml)
    if "<ram:CategoryCode>S</ram:CategoryCode>" not in t:
        return _next(xml, expect_total, expect_items)
    err = []
    info = parse_einvoice_xml(xml)
    if not info:
        return ["XML wird vom Empfangs-Parser nicht erkannt."]
    if abs(abs(info["betrag"]) - abs(expect_total)) > 0.005:
        err.append(f"Gesamtbetrag weicht ab: XML {info['betrag']} / Rechnung {expect_total}")
    if len(info["items"]) != expect_items:
        err.append(f"Positionsanzahl weicht ab: XML {len(info['items'])} / Rechnung {expect_items}")
    mb = re.search(r"<ram:TaxBasisTotalAmount>([-\d.]+)</ram:TaxBasisTotalAmount>", t)
    mt = re.search(r'<ram:TaxTotalAmount currencyID="EUR">([-\d.]+)</ram:TaxTotalAmount>', t)
    if mb and mt and abs(abs(float(mb.group(1)) + float(mt.group(1))) - abs(expect_total)) > 0.005:
        err.append("Netto + USt ergibt nicht den Gesamtbetrag")
    s_lines = round(sum(i["total"] for i in info["items"]), 2)
    if mb and abs(abs(s_lines) - abs(float(mb.group(1)))) > 0.005:
        err.append(f"Summe der Positionen {s_lines} passt nicht zum Nettobetrag {mb.group(1)}")
    return err

# ---------------------------------------------------------------------------
# Belege: Vorsteuer
# ---------------------------------------------------------------------------
_M80_VST_RX = re.compile(r"(mwst|mw\.-?st|ust\b|ust\.|umsatzsteuer|mehrwertsteuer|vat|steuer)[^\n]{0,40}?(19|7)[,.]?0{0,2}\s*%[^\n]{0,30}?(" + AMT + r")", re.I)
_M80_VST_RX2 = re.compile(r"(19|7)[,.]?0{0,2}\s*%\s*(mwst|ust|umsatzsteuer|mehrwertsteuer|vat)[^\n]{0,30}?(" + AMT + r")", re.I)


def _m80_beleg_path(b):
    f = b.get("file") or ""
    if not f:
        return ""
    return f if os.path.isabs(f) else os.path.join(DATA_DIR, f)


def m80_detect_vst(b):
    """-> {vorsteuer, satz, quelle} or None. The Vorsteuer keeps the sign of the receipt: a credit note
    (negative amount) reduces the Vorsteuer (Kz 66)"""
    betrag = float(b.get("betrag") or 0)
    brutto = abs(betrag)
    sign = -1.0 if betrag < 0 else 1.0
    try:
        det = json.loads(b.get("details") or "{}") if isinstance(b.get("details"), str) else (b.get("details") or {})
    except Exception:
        det = {}
    if not isinstance(det, dict):
        det = {}
    for k in ("vorsteuer", "mwst", "ust", "steuer"):
        v = det.get(k)
        try:
            if v not in (None, "") and 0 < abs(float(v)) < brutto:
                return {"vorsteuer": round(sign * abs(float(v)), 2), "satz": None, "quelle": "Belegdaten"}
        except Exception:
            pass
    fp = _m80_beleg_path(b)
    text = ""
    if fp and os.path.isfile(fp) and fp.lower().endswith(".pdf"):
        try:
            text = pdf_text(fp)
        except Exception:
            text = ""
    cands = []
    for rx, gi_rate, gi_amt in ((_M80_VST_RX, 2, 3), (_M80_VST_RX2, 1, 3)):
        for m in rx.finditer(text or ""):
            try:
                v = abs(parse_amount(m.group(gi_amt)))
                sz = float(m.group(gi_rate))
            except Exception:
                continue
            if brutto and 0 < v < brutto * 0.2:
                exp = brutto * sz / (100 + sz)
                cands.append((abs(v - exp) / max(exp, 0.01), v, sz))
    if cands:
        cands.sort()
        dev, v, sz = cands[0]
        if dev < 0.03 or len(cands) == 1:
            return {"vorsteuer": round(sign * v, 2), "satz": sz, "quelle": "PDF-Text"}
    return None


def m80_vst_list(von=None, bis=None):
    ab = m80_ab()
    if not ab:
        return []
    von = max(von or ab, ab)
    bis = bis or "9999-12-31"
    out = []
    for b in q("SELECT id, datum, partner, nr, betrag, kategorie, details, file FROM belege WHERE typ='ausgabe' AND datum BETWEEN ? AND ? ORDER BY datum DESC, id DESC", (von, bis)):
        try:
            det = json.loads(b["details"] or "{}")
        except Exception:
            det = {}
        b["vorsteuer"] = det.get("vorsteuer")
        b["vst_quelle"] = det.get("vorsteuer_quelle") or ""
        b.pop("details", None)
        out.append(b)
    return out


def m80_vst_set(bid, value, quelle="manuell"):
    b = q("SELECT * FROM belege WHERE id=?", (int(bid),), one=True)
    if not b:
        raise ValueError("Beleg nicht gefunden.")
    try:
        det = json.loads(b["details"] or "{}")
    except Exception:
        det = {}
    if value in (None, ""):
        det.pop("vorsteuer", None)
        det.pop("vorsteuer_quelle", None)
    else:
        v = round(float(value), 2)
        bt = float(b["betrag"] or 0)
        if v and abs(v) >= abs(bt):
            raise ValueError("Vorsteuer muss kleiner als der Belegbetrag sein.")
        if (bt < 0 < v) or (v < 0 <= bt):
            # credit note / refund: negative Vorsteuer; normal receipt: positive
            raise ValueError("Vorsteuer muss dasselbe Vorzeichen haben wie der Belegbetrag (Gutschrift = negative Vorsteuer).")
        det["vorsteuer"] = v
        det["vorsteuer_quelle"] = quelle
    x("UPDATE belege SET details=? WHERE id=?", (json.dumps(det, ensure_ascii=False), b["id"]))
    return True

# ---------------------------------------------------------------------------
# EUER split (used by m79 euer_form)
# ---------------------------------------------------------------------------


def m80_scale_rates(rates, pay, full):
    """share of a payment in net / USt per rate: a partial payment or a payment less Skonto (m71) carries
    only its proportion of the invoice VAT; sum of net + USt is exactly the payment -> {satz: (net, ust)}"""
    try:
        full = float(full or 0)
        pay = float(pay or 0)
    except Exception:
        return rates
    if not rates or abs(full) < 0.005 or abs(pay - full) < 0.005:
        return rates
    f = pay / full
    out = {}
    for sz, (net, ust) in rates.items():
        out[sz] = [round(float(net) * f, 2), round(float(ust) * f, 2)]
    diff = round(pay - sum(n_ + u_ for n_, u_ in out.values()), 2)
    if diff:
        k = max(out, key=lambda k_: abs(out[k_][0]))
        out[k][0] = round(out[k][0] + diff, 2)
    return out


def m80_ist_rows(von, bis):
    """Ist-Versteuerung: regel invoices with their payments in [von, bis] -> [(invoice row, {satz: (net, ust)})].
    With payment rows (m71: partial payments, Skonto) each payment counts on its own date with its share."""
    ids = set()
    try:
        ids = m71_ids() if "m71_ids" in globals() else set()
    except Exception:
        ids = set()
    out = []

    def det_of(r):
        try:
            return json.loads(r["ust_detail"] or "{}").get("saetze") or {}
        except Exception:
            return {}
    for r in q("SELECT * FROM invoices WHERE ust_modus='regel' AND typ IN ('rechnung','storno') AND status='bezahlt' AND "
               "substr(COALESCE(NULLIF(bezahlt_am,''),datum),1,10) BETWEEN ? AND ?", (von, bis)):
        if r["id"] not in ids:
            out.append((r, det_of(r)))
    if ids:
        for z in q("SELECT z.betrag zbetrag, i.* FROM m71_zahlung z JOIN invoices i ON i.id=z.invoice_id WHERE i.ust_modus='regel' "
                   "AND z.art IN ('zahlung','teil') AND i.status IN ('offen','bezahlt','storniert') AND i.typ IN ('rechnung','storno') "
                   "AND substr(z.datum,1,10) BETWEEN ? AND ? ORDER BY z.datum, z.id", (von, bis)):
            out.append((z, m80_scale_rates(det_of(z), z["zbetrag"], z["summe"])))
    return out


def m80_ein_split(b):
    """income receipt (typ 'einnahme') -> (satz, netto, ust) from details.ust / details.ust_satz.
    satz 0 / ust 0 = no USt in the receipt. Used by the UStVA, the EUER split and DATEV (m79)"""
    v = float(b.get("betrag") or 0)
    try:
        det = json.loads(b.get("details") or "{}") if isinstance(b.get("details"), str) else (b.get("details") or {})
    except Exception:
        det = {}
    if not isinstance(det, dict):
        det = {}
    try:
        u = round(float(det.get("ust") or 0), 2)
    except Exception:
        u = 0.0
    if abs(u) < 0.005:
        return 0.0, round(v, 2), 0.0
    net = round(v - u, 2)
    try:
        sz = float(det.get("ust_satz"))
    except Exception:
        r_ = abs(u) / max(0.01, abs(net)) * 100
        sz = 19.0 if abs(r_ - 19) < 1.5 else 7.0 if abs(r_ - 7) < 1.0 else round(r_, 1)
    return sz, net, u


def m80_euer_split(year):
    ab = m80_ab()
    if not ab or ab[:4] > str(year):
        return None
    year = int(year)
    ys = str(year)
    r = {"ein_ku": 0.0, "ein_netto": 0.0, "ein_frei": 0.0, "ust": 0.0, "ust_erstattet": 0.0, "vorsteuer": 0.0, "kategorien_netto": {}}
    for inv in paid_invoices(year):
        rates = None
        if inv.get("ust_modus") == "regel":
            try:
                rates = (json.loads(inv.get("ust_detail") or "{}").get("saetze") or {})
            except Exception:
                rates = None
            # m71 delivers one row per payment (summe = payment) -> only its share, otherwise VAT counted per payment again
            if rates and inv.get("m71_rechnungsbetrag") is not None:
                rates = m80_scale_rates(rates, inv["summe"], inv["m71_rechnungsbetrag"])
        if rates:
            for sz, (net, ust) in rates.items():
                if float(sz) > 0:
                    r["ein_netto"] += float(net)
                    r["ust"] += float(ust)
                else:
                    r["ein_frei"] += float(net)
        else:
            r["ein_ku"] += float(inv["summe"] or 0)
    for b in q("SELECT * FROM belege WHERE typ='einnahme' AND substr(datum,1,4)=?", (ys,)):
        v = float(b["betrag"] or 0)
        if (b["kategorie"] or "") == M80_KAT_ERSTATTUNG:
            r["ust_erstattet"] += v
        elif b["datum"] >= ab:
            # same split as the UStVA (m80_ustva): receipts with USt -> net + USt, without USt -> tax free
            sz_, net_, u = m80_ein_split(b)
            if u:
                r["ein_netto"] += net_
                r["ust"] += u
            else:
                r["ein_frei"] += net_
        else:
            r["ein_ku"] += v
    e = euer(year)
    cats = dict(e["kategorien"])
    for b in e["ausgaben_list"]:
        if (b["datum"] or "") < ab:
            continue
        try:
            vst = float((json.loads(b["details"] or "{}")).get("vorsteuer") or 0)
        except Exception:
            vst = 0.0
        if not vst:
            continue
        k = b["kategorie"] or "Sonstige Betriebsausgaben"
        # the category holds the gross amount (Bewirtung: 70 % net + full VSt, see euer() below) -> net = minus VSt
        cats[k] = round(cats.get(k, 0) - vst, 2)
        r["vorsteuer"] += vst
    r["kategorien_netto"] = {k: round(v, 2) for k, v in cats.items()}
    for k in ("ein_ku", "ein_netto", "ein_frei", "ust", "ust_erstattet", "vorsteuer"):
        r[k] = round(r[k], 2)
    return r

# ---------------------------------------------------------------------------
# EUER: Bewirtung under Regelbesteuerung
# par. 4 (5) Nr. 2 EStG: 30 % of the NET Bewirtung are not deductible, the Vorsteuer is deductible in full
# (par. 15 (1a) UStG). The base euer() takes 70 % of the GROSS amount - with Vorsteuer that is 30 % of the
# VSt too little. From the Stichtag on the Bewirtung category becomes 70 % net + 100 % VSt (gross method like
# every other category); Kleinunternehmer (no VSt) stays exactly as before.
# ---------------------------------------------------------------------------
def _m80_bewirt_korr(ausgaben_list):
    """-> {kategorie: extra expense} for Bewirtung receipts with Vorsteuer from the Stichtag on"""
    ab = m80_ab()
    out = {}
    if not ab:
        return out
    for b in ausgaben_list or []:
        k = b.get("kategorie") or ""
        if not k.startswith("Bewirtung") or (b.get("datum") or "") < ab:
            continue
        try:
            vst = float((json.loads(b.get("details") or "{}") or {}).get("vorsteuer") or 0)
        except Exception:
            vst = 0.0
        if vst:
            out[k] = out.get(k, 0.0) + vst * 0.3
    return {k: round(v, 2) for k, v in out.items() if abs(v) >= 0.005}


_m80_orig_euer = chain_inner("euer", "m80_regelbesteuerung")   # v3.1.0: the level below this module
@chain_step("euer", "m80_regelbesteuerung")
def _m80_step_euer(_next, year):
    e = _next(year)
    try:
        ab = m80_ab()
        if ab and ab[:4] <= str(year):
            korr = _m80_bewirt_korr(e.get("ausgaben_list"))
            if korr:
                e = dict(e)
                cats = dict(e.get("kategorien") or {})
                for k, v in korr.items():
                    cats[k] = round(cats.get(k, 0) + v, 2)
                add = round(sum(korr.values()), 2)
                e["kategorien"] = cats
                e["ausgaben"] = round(e["ausgaben"] + add, 2)
                e["gewinn"] = round(e["gewinn"] - add, 2)
                e["m80_bewirt_korr"] = add
    except Exception:
        traceback.print_exc()
    return e


euer._m60_orig = getattr(CHAINS["euer"][-1].base, "_m60_orig", CHAINS["euer"][-1].base)   # uncached base euer (m04)

# euer_totals (m04, cached in m60) calls the base euer via euer._m60_orig and so passes this wrapper -
# in a Regelbesteuerung year the totals come from the corrected euer() (itself cached in m60)
@chain_step("euer_totals", "m80_regelbesteuerung")
def _m80_step_euer_totals(_next, year):
    ab = m80_ab()
    if ab and ab[:4] <= str(year):
        e = euer(year)
        return {"einnahmen": e["einnahmen"], "ausgaben": e["ausgaben"], "gewinn": e["gewinn"]}
    return _next(year)


# ---------------------------------------------------------------------------
# UStVA
# ---------------------------------------------------------------------------


def _m80_next_workday(d):
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


def m80_perioden(year, zeitraum):
    if zeitraum == "monat":
        ps = [(f"{MONTHS_DE[m - 1]}", datetime.date(year, m, 1), add_months(datetime.date(year, m, 1), 1) - datetime.timedelta(days=1)) for m in range(1, 13)]
    elif zeitraum == "jahr":
        ps = [(f"Jahr {year}", datetime.date(year, 1, 1), datetime.date(year, 12, 31))]
    else:
        ps = [(f"{i + 1}. Quartal", datetime.date(year, 3 * i + 1, 1), add_months(datetime.date(year, 3 * i + 1, 1), 3) - datetime.timedelta(days=1)) for i in range(4)]
    return ps


def m80_ustva(year=None):
    cfg = m80_cfg()
    ab = m80_ab()
    year = int(year or datetime.date.today().year)
    zr = cfg.get("zeitraum") or "quartal"
    ist = (cfg.get("versteuerung") or "ist") == "ist"
    out = []
    for lbl, a, b in m80_perioden(year, zr):
        va, vb = a.isoformat(), b.isoformat()
        if ab:
            va_eff = max(va, ab)
        else:
            va_eff = va
        n19 = u19 = n7 = u7 = n0 = 0.0
        cnt = 0
        if ab and va_eff <= vb:
            if ist:
                pairs = m80_ist_rows(va_eff, vb)
            else:
                pairs = []
                for r in q("SELECT * FROM invoices WHERE ust_modus='regel' AND typ IN ('rechnung','storno') AND status!='entwurf' AND "
                           "substr(datum,1,10) BETWEEN ? AND ?", (va_eff, vb)):
                    try:
                        pairs.append((r, json.loads(r["ust_detail"] or "{}").get("saetze") or {}))
                    except Exception:
                        pairs.append((r, {}))
                # v2.0.19: par. 17 UStG - Skonto and written-off rest reduce base and tax in the period they happen.
                # On a cancellation (m71) only the row 'storno_korr' counts (it gives back the Skonto / write-off of the
                # original); the 'ausbuchung' of the unpaid part of a partly paid invoice is no loss of receivables -
                # the cancellation already reverses the full amount (v2.1.0 fix: counted twice)
                try:
                    for z in q("SELECT z.betrag zbetrag, i.* FROM m71_zahlung z JOIN invoices i ON i.id=z.invoice_id WHERE i.ust_modus='regel' "
                               "AND (i.typ='rechnung' OR z.quelle='storno_korr') AND z.art IN ('skonto','ausbuchung') "
                               "AND substr(z.datum,1,10) BETWEEN ? AND ?", (va_eff, vb)):
                        br = float(z["summe"] or 0)
                        if abs(br) < 0.005:
                            continue
                        f_ = -float(z["zbetrag"] or 0) / br
                        det0 = json.loads(z["ust_detail"] or "{}").get("saetze") or {}
                        pairs.append((dict(z, _korrektur=True), {k_: (round(v_[0] * f_, 2), round(v_[1] * f_, 2)) for k_, v_ in det0.items()}))
                except Exception:
                    traceback.print_exc()
            # other income receipts (cash sales m81, manual income with USt) - same split as m80_euer_split;
            # the USt refund of the tax office is no turnover
            for bl in q("SELECT * FROM belege WHERE typ='einnahme' AND datum BETWEEN ? AND ? AND COALESCE(kategorie,'')!=?",
                        (va_eff, vb, M80_KAT_ERSTATTUNG)):
                sz_, net_, u_ = m80_ein_split(bl)
                pairs.append((dict(bl, _korrektur=True), {str(sz_ if u_ else 0.0): (net_, u_)}))
            for r, det in pairs:
                cnt += 0 if r.get("_korrektur") else 1
                for sz, (net, ust) in det.items():
                    sz = float(sz)
                    if abs(sz - 19) < 0.01:
                        n19 += net
                        u19 += ust
                    elif abs(sz - 7) < 0.01:
                        n7 += net
                        u7 += ust
                    else:
                        n0 += net
            vst = 0.0
            nb = 0
            for bl in q("SELECT details FROM belege WHERE typ='ausgabe' AND datum BETWEEN ? AND ?", (va_eff, vb)):
                try:
                    v = float(json.loads(bl["details"] or "{}").get("vorsteuer") or 0)
                except Exception:
                    v = 0.0
                if v:       # credit notes carry negative Vorsteuer and reduce Kz 66
                    vst += v
                    nb += 1
        else:
            vst, nb = 0.0, 0
        kz81, kz86 = math.floor(n19 + 1e-9) if n19 >= 0 else -math.floor(-n19 + 1e-9), math.floor(n7 + 1e-9) if n7 >= 0 else -math.floor(-n7 + 1e-9)
        ust_sum = round(u19 + u7, 2)
        kz83 = round(ust_sum - vst, 2)
        due = datetime.date(b.year + (1 if b.month == 12 else 0), 1 if b.month == 12 else b.month + 1, 10)
        if cfg.get("dfv"):
            due = add_months(due, 1)
        due = _m80_next_workday(due)
        out.append({"periode": lbl, "von": va, "bis": vb, "aktiv": bool(ab) and va_eff <= vb, "rechnungen": cnt, "belege_vst": nb,
                    "kz81": kz81, "ust81": round(u19, 2), "kz86": kz86, "ust86": round(u7, 2), "steuerfrei": round(n0, 2),
                    "kz66": round(vst, 2), "kz83": kz83, "faellig": due.isoformat(),
                    "ueberfaellig": bool(ab) and va_eff <= vb and b < datetime.date.today() and
                                    datetime.date.today() - datetime.timedelta(days=40) <= due < datetime.date.today(),
                    "bald": bool(ab) and va_eff <= vb and b < datetime.date.today() and
                            datetime.date.today() <= due <= datetime.date.today() + datetime.timedelta(days=14)})
    tot = {k: round(sum(p[k] for p in out), 2) for k in ("kz81", "ust81", "kz86", "ust86", "kz66", "kz83", "steuerfrei")}
    return {"year": year, "zeitraum": zr, "ist": ist, "dfv": bool(cfg.get("dfv")), "ab": ab, "perioden": out, "summe": tot,
            "hinweis": ("Ist-Versteuerung: Umsätze zählen im Monat/Quartal des Zahlungseingangs. " if ist else
                        "Soll-Versteuerung: Umsätze zählen im Monat/Quartal der Rechnung. ") +
                       "Kz 81/86 = Bemessungsgrundlage in vollen Euro, ELSTER rechnet die Steuer selbst. "
                       "Vorsteuer (Kz 66) aus den Belegen ab dem Stichtag. Ersetzt keine Steuerberatung."}


def m80_naechste():
    ab = m80_ab()
    if not ab:
        return None
    t = datetime.date.today()
    best = None
    for y in (t.year - 1, t.year):
        for p in m80_ustva(y)["perioden"]:
            if p["aktiv"] and p["bis"] < t.isoformat() and p["faellig"] >= (t - datetime.timedelta(days=40)).isoformat():
                if not best or p["faellig"] < best["faellig"]:
                    best = dict(p, year=y)
    return best

# ---------------------------------------------------------------------------
# What-if
# ---------------------------------------------------------------------------
M80_KEINE_VST = ("Versicherungen", "Bankgebühren", "Abschreibung", "Fahrten Privat", "Homeoffice", "Rechts- und Steuer")


def m80_simulation(year=None, satz=19.0, b2c_anteil=None):
    year = int(year or datetime.date.today().year)
    e = euer(year)
    inv = year_invoices(year)
    umsatz = round(sum(float(r["summe"] or 0) for r in inv), 2)
    # B2C share: customers without company name
    cm = {c["id"]: c for c in q("SELECT id, firma FROM customers")}
    b2c = sum(float(r["summe"] or 0) for r in inv if not ((cm.get(r["customer_id"]) or {}).get("firma") or "").strip())
    share = (b2c / umsatz) if umsatz else 0.0
    if b2c_anteil not in (None, ""):
        share = max(0.0, min(1.0, float(b2c_anteil) / 100.0))
    vst = 0.0
    for b in e["ausgaben_list"]:
        k = b["kategorie"] or ""
        if any(k.startswith(p) for p in M80_KEINE_VST):
            continue
        vst += float(b["betrag"] or 0) * satz / (100 + satz)
    vst = round(vst, 2)
    ust_netto_preise = round(umsatz * satz / 100, 2)                        # A: prices + USt on top
    ust_brutto_preise = round(umsatz * satz / (100 + satz), 2)             # B: prices unchanged incl. USt
    a_ergebnis = round(-0.0 + vst, 2)                                      # customers pay the USt -> only VSt advantage
    b_ergebnis = round(vst - ust_brutto_preise, 2)
    mix = round(vst - ust_brutto_preise * share, 2)                        # B2B on top, B2C prices unchanged
    zr = "Monat" if (ust_netto_preise - vst) > 9000 else "Quartal" if (ust_netto_preise - vst) > 2000 else "Jahr (evtl. Befreiung von Voranmeldungen)"
    return {"year": year, "satz": satz, "umsatz": umsatz, "b2c_anteil": round(share * 100, 1), "vorsteuer_schaetzung": vst,
            "ust_auf_netto": ust_netto_preise, "ust_aus_brutto": ust_brutto_preise,
            "szenario_a": {"titel": "Preise bleiben netto, USt kommt oben drauf", "ergebnis": a_ergebnis,
                           "text": f"Kunden zahlen {num_de(satz, 0)} % mehr. Dein Gewinn steigt um die Vorsteuer (ca. {money(vst)}). "
                                   "Für Privatkunden wird es teurer."},
            "szenario_b": {"titel": "Endpreise bleiben gleich (USt ist drin)", "ergebnis": b_ergebnis,
                           "text": f"Du führst ca. {money(ust_brutto_preise)} USt ab, bekommst ca. {money(vst)} Vorsteuer zurück."},
            "szenario_mix": {"titel": f"Firmenkunden + USt, Privatkunden ({round(share * 100)} %) gleicher Endpreis", "ergebnis": mix,
                             "text": "Firmenkunden ziehen die USt als Vorsteuer ab - für sie ändert sich nichts."},
            "zeitraum_vorschlag": zr,
            "checkliste": ["Stichtag mit dem Steuerberater klären (Grenze 25.000 € Vorjahr / 100.000 € laufendes Jahr).",
                           "Steuernummer oder USt-IdNr. auf jeder Rechnung (Fußzeile prüfen).",
                           "Preise der Bausteine auf netto prüfen; Angebote ab Stichtag mit USt.",
                           "Fußtexte ohne § 19-Hinweis (macht das Programm automatisch ab Stichtag).",
                           "Vorsteuer auf Eingangsrechnungen ab Stichtag erfassen.",
                           "Voranmeldungszeitraum festlegen (Monat/Quartal) und ELSTER-Zugang bereithalten.",
                           "Bei Monatszahlern mit Dauerfristverlängerung: Sondervorauszahlung (1/11 der Vorjahres-Zahllast)."],
            "hinweis": "Grobe Schätzung aus den Zahlen des Jahres. Vorsteuer nur aus Ausgaben, bei denen üblicherweise USt anfällt. "
                       "Ersetzt keine Steuerberatung."}

# ---------------------------------------------------------------------------
# Checks / status
# ---------------------------------------------------------------------------


def m80_check():
    s = get_settings()
    w = []
    txt = " ".join(str(s.get(k) or "") for k in ("fuss1", "fuss2", "fuss3", "fuss4"))
    sd = {}
    try:
        sd = m50_seller(s)
    except Exception:
        pass
    has_id = bool(re.search(r"\bDE\s?\d{9}\b", txt) or re.search(r"\d{2,3}/\d{3,4}/\d{4,5}", txt) or sd.get("ustid") or sd.get("steuernr"))
    if not has_id:
        w.append("Weder Steuernummer noch USt-IdNr. in der Fußzeile gefunden - Pflichtangabe auf Rechnungen.")
    for k in ("default_foot", "default_foot_angebot", "default_foot_auftrag"):
        if M80_KU_RX.search(s.get(k) or ""):
            w.append("Standard-Fußtexte enthalten den § 19-Hinweis - wird ab Stichtag automatisch entfernt; "
                     "die Texte können in den Einstellungen angepasst werden.")
            break
    if not M80_PATCH["ok"]:
        w.append("Rechnungs-PDF: Summenblock mit USt konnte nicht eingebaut werden (" + M80_PATCH["msg"] + ").")
    return w


def m80_status():
    cfg = m80_cfg()
    ab = m80_ab()
    n_regel = q("SELECT COUNT(*) n FROM invoices WHERE ust_modus='regel'", one=True)["n"]
    return {"cfg": cfg, "ab": ab, "aktiv": bool(ab) and today() >= ab, "geplant": bool(ab) and today() < ab,
            "rechnungen_regel": n_regel, "warnungen": m80_check() if ab else [], "patch": M80_PATCH,
            "naechste": m80_naechste(), "saetze": list(M80_SAETZE)}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def m80_route_status(h, qs):
    return h._send(200, m80_status())


def m80_route_cfg(h, d):
    cfg = m80_cfg()
    old_ab = m80_ab()
    if "ab" in d:
        a = (d.get("ab") or "").strip()
        if a and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a):
            raise ValueError("Stichtag bitte als Datum.")
        cfg["ab"] = a
    if d.get("versteuerung") in ("ist", "soll"):
        cfg["versteuerung"] = d["versteuerung"]
    if d.get("zeitraum") in ("monat", "quartal", "jahr"):
        cfg["zeitraum"] = d["zeitraum"]
    if "dfv" in d:
        cfg["dfv"] = bool(d["dfv"])
    if "satz" in d:
        try:
            cfg["satz"] = float(d["satz"])
        except Exception:
            pass
    set_setting("m80", cfg)
    if cfg["ab"] and cfg["ab"] != old_ab:
        # freeze: everything already issued stays as issued
        x("UPDATE invoices SET ust_modus='ku', netto=summe, ust=0 WHERE ust_modus IS NULL AND (COALESCE(locked,0)=1 OR datum<?)", (cfg["ab"],))
        try:
            m51_log("Einstellung", None, "Regelbesteuerung ab", "m80_ab", old_ab, cfg["ab"], "Umstellung Umsatzsteuer")
        except Exception:
            pass
    elif not cfg["ab"] and old_ab:
        try:
            m51_log("Einstellung", None, "Regelbesteuerung entfernt", "m80_ab", old_ab, "", "zurück zur Kleinunternehmerregelung")
        except Exception:
            pass
    n_conv = 0
    if (cfg["ab"] or "") != (old_ab or ""):
        # unlocked documents (drafts, not yet issued invoices) follow the new Stichtag right away - before, an
        # open unlocked invoice dated after the Stichtag kept its KU total but was printed with VAT
        try:
            n_conv = m80_convert_unlocked()
        except Exception:
            traceback.print_exc()
    _m80_kategorien()
    return h._send(200, dict(m80_status(), ok=True, umgestellt=n_conv))


def m80_route_ustva(h, qs):
    return h._send(200, m80_ustva(qs.get("year")))


def m80_route_sim(h, qs):
    return h._send(200, m80_simulation(qs.get("year"), float(qs.get("satz") or 19), qs.get("b2c")))


def m80_route_vst(h, qs):
    return h._send(200, {"ab": m80_ab(), "rows": m80_vst_list(qs.get("von"), qs.get("bis"))})


def m80_route_vst_set(h, d):
    m80_vst_set(d["id"], d.get("vorsteuer"), d.get("quelle") or "manuell")
    return h._send(200, {"ok": True})


def m80_route_vst_detect(h, d):
    ids = [int(i) for i in d.get("ids") or []]
    rows = [r for r in m80_vst_list() if (not ids or r["id"] in ids)]
    n = 0
    found = []
    for r in rows:
        if r.get("vorsteuer") not in (None, "") and not d.get("ueberschreiben"):
            continue
        b = q("SELECT * FROM belege WHERE id=?", (r["id"],), one=True)
        res = m80_detect_vst(b)
        if res:
            m80_vst_set(r["id"], res["vorsteuer"], "erkannt (" + res["quelle"] + ")")
            n += 1
            found.append({"id": r["id"], "vorsteuer": res["vorsteuer"]})
    return h._send(200, {"ok": True, "erkannt": n, "geprueft": len(rows), "rows": found})


def m80_route_block(h, d):
    inv = dict(d)
    b = m80_ust_block(inv)
    return h._send(200, {"regel": bool(b), "block": b})


HOOK_GET["/api/m80/status"] = m80_route_status
HOOK_POST["/api/m80/cfg"] = m80_route_cfg
HOOK_GET["/api/m80/ustva"] = m80_route_ustva
HOOK_GET["/api/m80/sim"] = m80_route_sim
HOOK_GET["/api/m80/vst"] = m80_route_vst
HOOK_POST["/api/m80/vst"] = m80_route_vst_set
HOOK_POST["/api/m80/vst_detect"] = m80_route_vst_detect
HOOK_POST["/api/m80/block"] = m80_route_block


def _m80_boot(d):
    d["m80"] = {"ab": m80_ab(), "satz": float(m80_cfg().get("satz") or 19)}


HOOK_BOOT.append(_m80_boot)


def _m80_ex_ustva(p):
    u = m80_ustva(p.get("year"))
    return [_sh(f"Umsatzsteuer-Voranmeldung {u['year']} ({'Ist' if u['ist'] else 'Soll'}-Versteuerung)",
                [("Zeitraum", "t", 14), ("Kz 81 (19 %)", "m", 13), ("USt 19 %", "m", 12), ("Kz 86 (7 %)", "m", 13), ("USt 7 %", "m", 12),
                 ("Kz 66 Vorsteuer", "m", 14), ("Kz 83 Zahllast", "m", 14), ("Fällig", "d", 11)],
                [[p_["periode"], p_["kz81"], p_["ust81"], p_["kz86"], p_["ust86"], p_["kz66"], p_["kz83"], p_["faellig"]] for p_ in u["perioden"]],
                u["hinweis"], True)]


EXPORTS["m80_ustva"] = ("UStVA", _m80_ex_ustva)

# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------


def m80_selftest():
    err = []
    s_old = get_settings()
    keep = {k: s_old.get(k) for k in ("m80", "next_nr")}
    iid = None
    try:
        if not M80_PATCH["ok"]:
            err.append("m80: Rechnungs-PDF-Erweiterung nicht aktiv - " + M80_PATCH["msg"])
        # 1) without Stichtag nothing changes
        r0 = q("SELECT id FROM invoices WHERE typ='rechnung' AND status!='entwurf' ORDER BY id LIMIT 1", one=True)
        if r0 and not m80_ab():
            inv = get_invoice(r0["id"])
            if m80_ust_block(inv) is not None:
                err.append("m80: Kleinunternehmer-Rechnung wird als Regelbesteuerung erkannt")
            pdf = render_invoice_pdf(inv)
            txt = pdf_text(pdf)
            if "Nettobetrag" in txt or "zzgl. USt" in txt:
                err.append("m80: Kleinunternehmer-PDF zeigt USt-Zeilen")
            summe0 = inv["summe"]
            d = dict(inv)
            d["items"] = [dict(it) for it in inv["items"]]
            if round(sum(line_total(it) for it in d["items"]), 2) != round(summe0, 2) and not inv.get("locked"):
                err.append("m80: Summe der KU-Rechnung weicht ab")
        # 2) with Stichtag: 19 % + 7 %
        set_setting("m80", dict(M80_DEFAULTS, ab="2000-01-01"))
        _m80_kategorien()
        iid, nr = save_invoice({"typ": "rechnung", "datum": today(), "addr": ["Selbsttest m80"], "status": "offen", "titel": "Test USt",
                                "foottext": "Danke.\nKein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
                                "items": [{"qty": 2, "name": "Technik", "price": 100.0, "ust_satz": 19},
                                          {"qty": 1, "name": "Buch", "price": 50.0, "ust_satz": 7}]})
        inv = get_invoice(iid)
        if inv.get("ust_modus") != "regel":
            err.append("m80: Modus regel nicht gespeichert")
        if abs(float(inv["summe"]) - (200 * 1.19 + 50 * 1.07)) > 0.005:
            err.append(f"m80: Bruttosumme falsch ({inv['summe']})")
        if "§19" in (inv.get("foottext") or "") or "Kleinunternehmer" in (inv.get("foottext") or ""):
            err.append("m80: § 19-Hinweis nicht entfernt")
        txt = pdf_text(render_invoice_pdf(inv))
        if "Nettobetrag" not in txt or "zzgl. USt 19" not in txt or "zzgl. USt 7" not in txt:
            err.append("m80: USt-Zeilen fehlen im PDF")
        xml, info = build_xrechnung(inv, {"buyer_ref": "n/a", "buyer_mail": "test@example.org"})
        if b"<ram:CategoryCode>S</ram:CategoryCode>" not in xml or b"<ram:CategoryCode>E</ram:CategoryCode>" in xml:
            err.append("m80: XRechnung ohne Kategorie S")
        for e_ in m50_check_roundtrip(xml, info["summe"], len(inv["items"])):
            err.append("m80 XRechnung: " + e_)
        sid, _ = storno_invoice(iid)
        st = get_invoice(sid)
        if st.get("ust_modus") != "regel" or abs(float(st["summe"]) + float(inv["summe"])) > 0.005:
            err.append(f"m80: Storno übernimmt USt nicht ({st.get('summe')})")
        u = m80_ustva(datetime.date.today().year)
        if not u["perioden"]:
            err.append("m80: UStVA ohne Zeiträume")
        x("DELETE FROM items WHERE invoice_id IN (?,?)", (iid, sid))
        x("DELETE FROM invoices WHERE id IN (?,?)", (iid, sid))
        iid = None
        if m80_strip_ku("Danke.\nKein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG") != "Danke.":
            err.append("m80: Fußtext-Bereinigung falsch")
    except Exception as e:
        traceback.print_exc()
        err.append(f"m80 Ausnahme: {e}")
    finally:
        try:
            if iid:
                x("DELETE FROM items WHERE invoice_id=?", (iid,))
                x("DELETE FROM invoices WHERE id=?", (iid,))
            for k, v in keep.items():
                if v is None:
                    x("DELETE FROM settings WHERE k=?", (k,))
                else:
                    set_setting(k, v)
            if M80_KAT_ZAHLUNG in EUER_KATEGORIEN and not m80_ab():
                EUER_KATEGORIEN.remove(M80_KAT_ZAHLUNG)
        except Exception:
            pass
    return err


HOOK_SELFTEST.append(m80_selftest)
