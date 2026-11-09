# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m50_erechnung_out
# E-Rechnung AUSGANG: XRechnung (CII, EN16931 / XRechnung 3.0) und ZUGFeRD/Factur-X-PDF.
# Kleinunternehmer nach par. 19 UStG: Steuerkategorie E, Steuerbetrag 0.
# Empfang (parse_einvoice_xml, pdf_embedded_xml) liegt in m09 und wird hier nur zum Zuruecklesen benutzt.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M50_VERSION = "1.0.0"
M50_KU_REASON = "Kleinunternehmer gemäß § 19 UStG"
M50_GUIDELINE = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
M50_PROCESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
M50_FX_GUIDELINE = "urn:cen.eu:en16931:2017"
M50_COUNTRY = {"deutschland": "DE", "germany": "DE", "österreich": "AT", "oesterreich": "AT", "austria": "AT",
               "schweiz": "CH", "switzerland": "CH", "niederlande": "NL", "belgien": "BE", "frankreich": "FR",
               "luxemburg": "LU", "dänemark": "DK", "polen": "PL", "italien": "IT", "spanien": "ES"}


def m50_schema():
    try:
        x("ALTER TABLE customers ADD COLUMN leitweg_id TEXT")
    except Exception:
        pass


HOOK_SCHEMA.append(m50_schema)

# ---------------------------------------------------------------------------
# Seller data (own settings with defaults parsed from existing settings)
# ---------------------------------------------------------------------------


def m50_seller(s=None):
    s = s or get_settings()
    snd = [p.strip() for p in (s.get("absender") or "").split(",") if p.strip()]
    strasse, plz, ort = "", "", ""
    for p in snd[1:]:
        m = re.match(r"^(?:D-|DE-)?(\d{5})\s+(.+)$", p)
        if m:
            plz, ort = m.group(1), m.group(2)
        elif not strasse:
            strasse = p
    f3 = s.get("fuss3") or ""
    f4 = s.get("fuss4") or ""
    ust_m = re.search(r"\bDE\s?\d{9}\b", f3)
    ustid = ust_m.group(0) if ust_m else ""
    stnr_m = re.search(r"\b\d{2,3}/\d{3,4}/\d{4,5}\b", f3)
    tel_m = re.search(r"\+?\d[\d \-/]{6,}\d", f4)
    mail_m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", f4) or re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", s.get("smtp_user") or "")
    d = {"name": s.get("firma") or s.get("inhaber") or "", "inhaber": s.get("inhaber") or "",
         "strasse": strasse, "plz": plz, "ort": ort, "land": "DE",
         "tel": tel_m.group(0).strip() if tel_m else "", "mail": mail_m.group(0) if mail_m else "",
         "steuernr": stnr_m.group(0) if stnr_m else "", "ustid": (ustid or "").replace(" ", ""),
         "iban": re.sub(r"\s", "", s.get("iban") or ""), "bic": s.get("bic") or "",
         "kontoinhaber": s.get("kontoinhaber") or s.get("inhaber") or ""}
    own = s.get("m50_seller") or {}
    for k, v in own.items():
        if k in d and str(v or "").strip():
            d[k] = str(v).strip()
    return d


def m50_seller_check(sd):
    miss = []
    for k, lbl in (("name", "Firmenname"), ("inhaber", "Ansprechpartner"), ("strasse", "Straße"), ("plz", "PLZ"),
                   ("ort", "Ort"), ("tel", "Telefon"), ("mail", "E-Mail"), ("steuernr", "Steuernummer")):
        if not sd.get(k):
            miss.append(lbl)
    return miss

# ---------------------------------------------------------------------------
# XML builder
# ---------------------------------------------------------------------------


_M50_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def _m50_e(t):
    # v2.0.6: XML-invalid control characters (Word Shift+Enter = \x0b ...) -> space
    return _M50_BAD.sub(" ", str(t if t is not None else "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _m50_amt(v, dec=2):
    return f"{round(float(v or 0) + 0.0, dec):.{dec}f}"


def _m50_qty(v):
    s_ = f"{float(v or 0):.4f}".rstrip("0").rstrip(".")
    return s_ or "0"


def _m50_date(iso):
    d = d_iso(iso)
    return d.strftime("%Y%m%d") if d else datetime.date.today().strftime("%Y%m%d")


def _m50_country(v):
    v = (v or "").strip()
    if not v:
        return "DE"
    if re.fullmatch(r"[A-Za-z]{2}", v):
        return v.upper()
    return M50_COUNTRY.get(v.lower(), "DE")


def _m50_unit(it):
    u = ""
    if it.get("article_id"):
        a = q("SELECT unit FROM articles WHERE id=?", (it["article_id"],), one=True)
        u = (a or {}).get("unit") or ""
    t = (u + " " + (it.get("name") or "")).lower()
    if re.search(r"\b(std|stunde|stunden|h)\b", t):
        return "HUR"
    if re.search(r"\bkm\b", t):
        return "KMT"
    if re.search(r"\b(tag|tage|tagessatz)\b", t):
        return "DAY"
    if re.search(r"\bpausch", t):
        return "LS"
    return "C62"


def _m50_buyer(inv, c):
    addr = [l for l in (inv.get("addr") or []) if l.strip()]
    b = {"name": "", "strasse": "", "plz": "", "ort": "", "land": "DE", "mail": "", "kontakt": ""}
    if c:
        b.update(name=c.get("firma") or c.get("name") or "", strasse=c.get("strasse") or "", plz=c.get("plz") or "",
                 ort=c.get("ort") or "", land=_m50_country(c.get("land")), mail=c.get("mail") or "",
                 kontakt=(c.get("name") or "") if c.get("firma") else "")
    if not b["name"]:
        names = [l for l in addr if not re.match(r"^(herrn?|frau|familie|firma)$", l.strip(), re.I)]
        b["name"] = names[0] if names else (inv.get("kdnr") or "Kunde")
    if not b["plz"]:
        for l in reversed(addr):
            m = re.match(r"^(?:[A-Z]{1,2}-)?(\d{4,5})\s+(.+)$", l.strip())
            if m:
                b["plz"], b["ort"] = m.group(1), m.group(2)
                i = addr.index(l)
                if i > 0 and not b["strasse"]:
                    b["strasse"] = addr[i - 1]
                break
    return b


def build_xrechnung(inv, opts=None, s=None):
    """inv = get_invoice() dict. opts: buyer_ref, buyer_mail, order_ref. Returns (xml_bytes, info)."""
    opts = opts or {}
    s = s or get_settings()
    if not inv:
        raise ValueError("Rechnung nicht gefunden.")
    typ = inv.get("typ") or "rechnung"
    if typ not in ("rechnung", "storno"):
        raise ValueError("E-Rechnungen gibt es nur für Rechnungen und Storno-Rechnungen (nicht für Angebote/Aufträge).")
    if inv.get("status") == "entwurf" or str(inv.get("nr") or "").startswith("E-"):
        raise ValueError("Bitte den Entwurf erst fertigstellen (Rechnungsnummer nötig).")
    sd = m50_seller(s)
    c = q("SELECT * FROM customers WHERE id=?", (inv["customer_id"],), one=True) if inv.get("customer_id") else None
    b = _m50_buyer(inv, c)
    if opts.get("buyer_mail"):
        b["mail"] = opts["buyer_mail"].strip()
    buyer_ref = (opts.get("buyer_ref") or (c or {}).get("leitweg_id") or opts.get("order_ref") or "n/a").strip() or "n/a"
    items = inv.get("items") or []
    if not items:
        # BR-16: at least one invoice line - the validator rejects an empty document
        raise ValueError("Die Rechnung hat keine Positionen - eine E-Rechnung braucht mindestens eine Position.")
    total = round(sum(item_total(inv, it) for it in items), 2)
    credit = typ == "storno" or total < 0
    sign = -1.0 if credit else 1.0
    tcode = "381" if credit else "380"
    warn = []
    miss = m50_seller_check(sd)
    if miss:
        warn.append("Verkäuferdaten unvollständig: " + ", ".join(miss) + " (Einstellungen → E-Rechnung).")
    if not b["mail"]:
        warn.append("Keine E-Mail-Adresse des Käufers (BT-49) - in XRechnung 3.0 Pflicht.")
    if not b["plz"] or not b["ort"]:
        warn.append("Anschrift des Käufers ohne PLZ/Ort erkannt.")
    if not sd["iban"] and (inv.get("zahlart") or "Ueberweisung") == "Ueberweisung":
        warn.append("Keine IBAN in den Einstellungen.")
    frist = int(inv.get("frist") or 0)
    dd = d_iso(inv.get("datum")) or datetime.date.today()
    due = dd + datetime.timedelta(days=frist)
    L = []
    a = L.append
    a('<?xml version="1.0" encoding="UTF-8"?>')
    a('<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" '
      'xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" '
      'xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100" '
      'xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">')
    a(' <rsm:ExchangedDocumentContext>')
    a(f'  <ram:BusinessProcessSpecifiedDocumentContextParameter><ram:ID>{M50_PROCESS}</ram:ID></ram:BusinessProcessSpecifiedDocumentContextParameter>')
    a(f'  <ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>{_m50_e(opts.get("guideline") or M50_GUIDELINE)}</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter>')
    a(' </rsm:ExchangedDocumentContext>')
    a(' <rsm:ExchangedDocument>')
    a(f'  <ram:ID>{_m50_e(inv["nr"])}</ram:ID>')
    a(f'  <ram:TypeCode>{tcode}</ram:TypeCode>')
    a(f'  <ram:IssueDateTime><udt:DateTimeString format="102">{_m50_date(inv.get("datum"))}</udt:DateTimeString></ram:IssueDateTime>')
    if inv.get("titel"):
        a(f'  <ram:IncludedNote><ram:Content>{_m50_e(inv["titel"])}</ram:Content></ram:IncludedNote>')
    a(f'  <ram:IncludedNote><ram:Content>{_m50_e(M50_KU_REASON)} - es wird keine Umsatzsteuer berechnet.</ram:Content><ram:SubjectCode>REG</ram:SubjectCode></ram:IncludedNote>')
    a(' </rsm:ExchangedDocument>')
    a(' <rsm:SupplyChainTradeTransaction>')
    for i, it in enumerate(items):
        qty = float(it.get("qty") or 0) * sign
        price = float(it.get("price") or 0)
        rab = float(it.get("rabatt") or 0)
        lt = round(item_total(inv, it) * sign, 2)
        net = round(price * (1 - rab / 100.0), 4)
        if price < 0:
            # negative unit price is not allowed (BR-27): move the sign into the quantity
            qty, price, net = -qty, -price, -net
        a('  <ram:IncludedSupplyChainTradeLineItem>')
        a(f'   <ram:AssociatedDocumentLineDocument><ram:LineID>{i + 1}</ram:LineID></ram:AssociatedDocumentLineDocument>')
        a('   <ram:SpecifiedTradeProduct>')
        if it.get("nr"):
            a(f'    <ram:SellerAssignedID>{_m50_e(it["nr"])}</ram:SellerAssignedID>')
        a(f'    <ram:Name>{_m50_e((it.get("name") or "").strip() or ("Position " + str(i + 1)))}</ram:Name>')
        if (it.get("descr") or "").strip():
            a(f'    <ram:Description>{_m50_e(it["descr"].strip())}</ram:Description>')
        a('   </ram:SpecifiedTradeProduct>')
        a('   <ram:SpecifiedLineTradeAgreement>')
        if rab:
            a(f'    <ram:GrossPriceProductTradePrice><ram:ChargeAmount>{_m50_amt(price, 4)}</ram:ChargeAmount>'
              f'<ram:AppliedTradeAllowanceCharge><ram:ChargeIndicator><udt:Indicator>false</udt:Indicator></ram:ChargeIndicator>'
              f'<ram:ActualAmount>{_m50_amt(price - net, 4)}</ram:ActualAmount></ram:AppliedTradeAllowanceCharge></ram:GrossPriceProductTradePrice>')
        a(f'    <ram:NetPriceProductTradePrice><ram:ChargeAmount>{_m50_amt(net, 4)}</ram:ChargeAmount></ram:NetPriceProductTradePrice>')
        a('   </ram:SpecifiedLineTradeAgreement>')
        a(f'   <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="{_m50_unit(it)}">{_m50_qty(qty)}</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>')
        a('   <ram:SpecifiedLineTradeSettlement>')
        a('    <ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>E</ram:CategoryCode>'
          '<ram:RateApplicablePercent>0</ram:RateApplicablePercent></ram:ApplicableTradeTax>')
        a(f'    <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>{_m50_amt(lt)}</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation>')
        a('   </ram:SpecifiedLineTradeSettlement>')
        a('  </ram:IncludedSupplyChainTradeLineItem>')
    # agreement
    a('  <ram:ApplicableHeaderTradeAgreement>')
    a(f'   <ram:BuyerReference>{_m50_e(buyer_ref)}</ram:BuyerReference>')
    a('   <ram:SellerTradeParty>')
    a(f'    <ram:Name>{_m50_e(sd["name"])}</ram:Name>')
    a('    <ram:DefinedTradeContact>')
    a(f'     <ram:PersonName>{_m50_e(sd["inhaber"] or sd["name"])}</ram:PersonName>')
    if sd["tel"]:
        a(f'     <ram:TelephoneUniversalCommunication><ram:CompleteNumber>{_m50_e(sd["tel"])}</ram:CompleteNumber></ram:TelephoneUniversalCommunication>')
    if sd["mail"]:
        a(f'     <ram:EmailURIUniversalCommunication><ram:URIID>{_m50_e(sd["mail"])}</ram:URIID></ram:EmailURIUniversalCommunication>')
    a('    </ram:DefinedTradeContact>')
    a(f'    <ram:PostalTradeAddress><ram:PostcodeCode>{_m50_e(sd["plz"])}</ram:PostcodeCode><ram:LineOne>{_m50_e(sd["strasse"])}</ram:LineOne>'
      f'<ram:CityName>{_m50_e(sd["ort"])}</ram:CityName><ram:CountryID>{_m50_country(sd["land"])}</ram:CountryID></ram:PostalTradeAddress>')
    if sd["mail"]:
        a(f'    <ram:URIUniversalCommunication><ram:URIID schemeID="EM">{_m50_e(sd["mail"])}</ram:URIID></ram:URIUniversalCommunication>')
    if sd["steuernr"]:
        a(f'    <ram:SpecifiedTaxRegistration><ram:ID schemeID="FC">{_m50_e(sd["steuernr"])}</ram:ID></ram:SpecifiedTaxRegistration>')
    if sd["ustid"]:
        a(f'    <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">{_m50_e(sd["ustid"])}</ram:ID></ram:SpecifiedTaxRegistration>')
    a('   </ram:SellerTradeParty>')
    a('   <ram:BuyerTradeParty>')
    a(f'    <ram:Name>{_m50_e(b["name"])}</ram:Name>')
    if b["kontakt"]:
        a(f'    <ram:DefinedTradeContact><ram:PersonName>{_m50_e(b["kontakt"])}</ram:PersonName></ram:DefinedTradeContact>')
    a('    <ram:PostalTradeAddress>' + (f'<ram:PostcodeCode>{_m50_e(b["plz"])}</ram:PostcodeCode>' if b["plz"] else "") +
      (f'<ram:LineOne>{_m50_e(b["strasse"])}</ram:LineOne>' if b["strasse"] else "") +
      (f'<ram:CityName>{_m50_e(b["ort"])}</ram:CityName>' if b["ort"] else "") +
      f'<ram:CountryID>{_m50_country(b["land"])}</ram:CountryID></ram:PostalTradeAddress>')
    if b["mail"]:
        a(f'    <ram:URIUniversalCommunication><ram:URIID schemeID="EM">{_m50_e(b["mail"])}</ram:URIID></ram:URIUniversalCommunication>')
    a('   </ram:BuyerTradeParty>')
    if (opts.get("order_ref") or "").strip():
        a(f'   <ram:BuyerOrderReferencedDocument><ram:IssuerAssignedID>{_m50_e(opts["order_ref"].strip())}</ram:IssuerAssignedID></ram:BuyerOrderReferencedDocument>')
    a('  </ram:ApplicableHeaderTradeAgreement>')
    # delivery
    a('  <ram:ApplicableHeaderTradeDelivery>')
    if inv.get("liefer"):
        a(f'   <ram:ActualDeliverySupplyChainEvent><ram:OccurrenceDateTime><udt:DateTimeString format="102">{_m50_date(inv["liefer"])}</udt:DateTimeString></ram:OccurrenceDateTime></ram:ActualDeliverySupplyChainEvent>')
    a('  </ram:ApplicableHeaderTradeDelivery>')
    # settlement
    za = inv.get("zahlart") or "Ueberweisung"
    a('  <ram:ApplicableHeaderTradeSettlement>')
    a(f'   <ram:PaymentReference>{_m50_e(inv["nr"])}</ram:PaymentReference>')
    a('   <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>')
    if za == "Ueberweisung" or (credit and sd["iban"]):
        a('   <ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>58</ram:TypeCode><ram:Information>SEPA-Überweisung</ram:Information>')
        if sd["iban"]:
            a(f'    <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>{_m50_e(sd["iban"])}</ram:IBANID>'
              f'<ram:AccountName>{_m50_e(sd["kontoinhaber"])}</ram:AccountName></ram:PayeePartyCreditorFinancialAccount>')
            if sd["bic"]:
                a(f'    <ram:PayeeSpecifiedCreditorFinancialInstitution><ram:BICID>{_m50_e(sd["bic"])}</ram:BICID></ram:PayeeSpecifiedCreditorFinancialInstitution>')
        a('   </ram:SpecifiedTradeSettlementPaymentMeans>')
    elif za == "PayPal":
        a(f'   <ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>68</ram:TypeCode><ram:Information>PayPal {_m50_e(s.get("paypal_mail") or "")}</ram:Information></ram:SpecifiedTradeSettlementPaymentMeans>')
    else:
        a('   <ram:SpecifiedTradeSettlementPaymentMeans><ram:TypeCode>10</ram:TypeCode><ram:Information>Barzahlung</ram:Information></ram:SpecifiedTradeSettlementPaymentMeans>')
    basis = round(total * sign, 2)
    a(f'   <ram:ApplicableTradeTax><ram:CalculatedAmount>0.00</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode>'
      f'<ram:ExemptionReason>{_m50_e(M50_KU_REASON)}</ram:ExemptionReason><ram:BasisAmount>{_m50_amt(basis)}</ram:BasisAmount>'
      f'<ram:CategoryCode>E</ram:CategoryCode><ram:RateApplicablePercent>0</ram:RateApplicablePercent></ram:ApplicableTradeTax>')
    terms = f"Zahlbar bis {de_date(due.isoformat())} ohne Abzug." if frist and not credit else ("Gutschrift / Erstattung." if credit else "Zahlbar sofort ohne Abzug.")
    a(f'   <ram:SpecifiedTradePaymentTerms><ram:Description>{_m50_e(terms)}</ram:Description>' +
      (f'<ram:DueDateDateTime><udt:DateTimeString format="102">{due.strftime("%Y%m%d")}</udt:DateTimeString></ram:DueDateDateTime>' if not credit else "") +
      '</ram:SpecifiedTradePaymentTerms>')
    a('   <ram:SpecifiedTradeSettlementHeaderMonetarySummation>')
    a(f'    <ram:LineTotalAmount>{_m50_amt(basis)}</ram:LineTotalAmount>')
    a(f'    <ram:TaxBasisTotalAmount>{_m50_amt(basis)}</ram:TaxBasisTotalAmount>')
    a('    <ram:TaxTotalAmount currencyID="EUR">0.00</ram:TaxTotalAmount>')
    a(f'    <ram:GrandTotalAmount>{_m50_amt(basis)}</ram:GrandTotalAmount>')
    a(f'    <ram:DuePayableAmount>{_m50_amt(basis)}</ram:DuePayableAmount>')
    a('   </ram:SpecifiedTradeSettlementHeaderMonetarySummation>')
    if inv.get("ref_id"):
        ref = q("SELECT nr, datum, typ FROM invoices WHERE id=?", (inv["ref_id"],), one=True)
        if ref and ref["typ"] in ("rechnung", "storno"):   # v2.0.6: an offer is no "preceding invoice" (BT-25)
            a(f'   <ram:InvoiceReferencedDocument><ram:IssuerAssignedID>{_m50_e(ref["nr"])}</ram:IssuerAssignedID>'
              f'<ram:FormattedIssueDateTime><qdt:DateTimeString format="102">{_m50_date(ref["datum"])}</qdt:DateTimeString></ram:FormattedIssueDateTime></ram:InvoiceReferencedDocument>')
    a('  </ram:ApplicableHeaderTradeSettlement>')
    a(' </rsm:SupplyChainTradeTransaction>')
    a('</rsm:CrossIndustryInvoice>')
    xml = "\n".join(L).encode("utf-8")
    return xml, {"summe": basis, "typecode": tcode, "buyer_ref": buyer_ref, "buyer": b, "seller": sd, "warn": warn}


def m50_check_roundtrip(xml, expect_total, expect_items):
    """parse with the existing receive parser (m09) and compare sums -> list of errors"""
    err = []
    info = parse_einvoice_xml(xml)
    if not info:
        return ["XML wird vom Empfangs-Parser nicht erkannt."]
    if abs(abs(info["betrag"]) - abs(expect_total)) > 0.005:
        err.append(f"Gesamtbetrag weicht ab: XML {info['betrag']} / Rechnung {expect_total}")
    if len(info["items"]) != expect_items:
        err.append(f"Positionsanzahl weicht ab: XML {len(info['items'])} / Rechnung {expect_items}")
    s_lines = round(sum(i["total"] for i in info["items"]), 2)
    if abs(abs(s_lines) - abs(expect_total)) > 0.005:
        err.append(f"Summe der Positionen {s_lines} passt nicht zum Gesamtbetrag {expect_total}")
    return err

# ---------------------------------------------------------------------------
# ZUGFeRD / Factur-X: embed XML into the PDF
# ---------------------------------------------------------------------------


def _m50_xmp(title, author, nr):
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    return f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>3</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{_m50_e(title)}</rdf:li></rdf:Alt></dc:title>
   <dc:creator><rdf:Seq><rdf:li>{_m50_e(author)}</rdf:li></rdf:Seq></dc:creator>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">E-Rechnung {_m50_e(nr)} (Factur-X / ZUGFeRD EN 16931)</rdf:li></rdf:Alt></dc:description>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
   <pdf:Producer>{_m50_e(APP_NAME)} v{APP_VERSION}</pdf:Producer>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   <xmp:CreatorTool>{_m50_e(APP_NAME)} v{APP_VERSION}</xmp:CreatorTool>
   <xmp:CreateDate>{now}</xmp:CreateDate>
   <xmp:ModifyDate>{now}</xmp:ModifyDate>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/" xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#" xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
   <pdfaExtension:schemas><rdf:Bag><rdf:li rdf:parseType="Resource">
    <pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
    <pdfaSchema:namespaceURI>urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#</pdfaSchema:namespaceURI>
    <pdfaSchema:prefix>fx</pdfaSchema:prefix>
    <pdfaSchema:property><rdf:Seq>
     <rdf:li rdf:parseType="Resource"><pdfaProperty:name>DocumentFileName</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>name of the embedded XML invoice file</pdfaProperty:description></rdf:li>
     <rdf:li rdf:parseType="Resource"><pdfaProperty:name>DocumentType</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>INVOICE</pdfaProperty:description></rdf:li>
     <rdf:li rdf:parseType="Resource"><pdfaProperty:name>Version</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The actual version of the Factur-X XML schema</pdfaProperty:description></rdf:li>
     <rdf:li rdf:parseType="Resource"><pdfaProperty:name>ConformanceLevel</pdfaProperty:name><pdfaProperty:valueType>Text</pdfaProperty:valueType><pdfaProperty:category>external</pdfaProperty:category><pdfaProperty:description>The conformance level of the embedded Factur-X data</pdfaProperty:description></rdf:li>
    </rdf:Seq></pdfaSchema:property>
   </rdf:li></rdf:Bag></pdfaExtension:schemas>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:fx="urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#">
   <fx:DocumentType>INVOICE</fx:DocumentType>
   <fx:DocumentFileName>factur-x.xml</fx:DocumentFileName>
   <fx:Version>1.0</fx:Version>
   <fx:ConformanceLevel>EN 16931</fx:ConformanceLevel>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>""".encode("utf-8")


def embed_facturx(pdf_bytes, xml_bytes, title="", author="", nr=""):
    if not pypdf:
        raise ValueError("pypdf ist nicht installiert - ZUGFeRD-PDF nicht möglich.")
    from pypdf.generic import (NameObject, DictionaryObject, ArrayObject, TextStringObject, DecodedStreamObject,
                               IndirectObject, NumberObject, create_string_object)
    r = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    w = pypdf.PdfWriter()
    for pg in r.pages:
        w.add_page(pg)
    try:
        if r.metadata:
            w.add_metadata({k: v for k, v in r.metadata.items() if isinstance(v, str)})
    except Exception:
        pass
    w.add_attachment("factur-x.xml", xml_bytes)
    root = w._root_object
    names = root["/Names"]["/EmbeddedFiles"]["/Names"]
    spec_ref = None
    for i in range(0, len(names), 2):
        if str(names[i]) == "factur-x.xml":
            obj = names[i + 1]
            if isinstance(obj, IndirectObject):
                spec_ref = obj
            else:
                spec_ref = w._add_object(obj)
                names[i + 1] = spec_ref
    if spec_ref is None:
        raise ValueError("Anhang konnte nicht eingebettet werden.")
    spec = spec_ref.get_object()
    spec[NameObject("/AFRelationship")] = NameObject("/Alternative")
    spec[NameObject("/Desc")] = TextStringObject("Factur-X / ZUGFeRD Rechnungsdaten (EN 16931)")
    spec[NameObject("/UF")] = TextStringObject("factur-x.xml")
    try:
        ef = spec["/EF"]["/F"].get_object()
        ef[NameObject("/Subtype")] = NameObject("/text/xml")
        mdate = "D:" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S") + "+00'00'"
        params = ef.get("/Params") or DictionaryObject()
        params = params.get_object() if hasattr(params, "get_object") else params
        params[NameObject("/ModDate")] = create_string_object(mdate)
        params[NameObject("/Size")] = NumberObject(len(xml_bytes))
        ef[NameObject("/Params")] = params
    except Exception:
        traceback.print_exc()
    root[NameObject("/AF")] = ArrayObject([spec_ref])
    meta = DecodedStreamObject()
    meta.set_data(_m50_xmp(title, author, nr))
    meta[NameObject("/Type")] = NameObject("/Metadata")
    meta[NameObject("/Subtype")] = NameObject("/XML")
    root[NameObject("/Metadata")] = w._add_object(meta)
    root[NameObject("/PageMode")] = NameObject("/UseAttachments")
    o = io.BytesIO()
    w.write(o)
    return o.getvalue()


_M50_TL = threading.local()


def m50_zugferd_pdf(inv, opts=None, s=None, base_pdf=None):
    s = s or get_settings()
    if base_pdf is not None and getattr(_M50_TL, "plain", False):
        # visible part of an explicit ZUGFeRD export is being rendered: no automatic embedding (m50 / m82 setting)
        return base_pdf, None, None
    # Factur-X / ZUGFeRD profile EN 16931 (matches the XMP ConformanceLevel); the XRechnung-only XML uses M50_GUIDELINE
    xml, info = build_xrechnung(inv, dict(opts or {}, guideline=(opts or {}).get("guideline") or M50_FX_GUIDELINE), s)
    if base_pdf is not None:
        pdf = base_pdf
    else:
        # v2.1.0: render with the COMPLETE renderer chain (Regelbesteuerung m80, fonts m62, international m82 ...).
        # Before, the renderer from before m50 was used: with Regelbesteuerung the visible PDF showed the net sum
        # without VAT block and the par. 19 note, while the embedded XML carried VAT.
        prev = getattr(_M50_TL, "plain", False)
        _M50_TL.plain = True
        try:
            pdf = render_invoice_pdf(inv, s)
        finally:
            _M50_TL.plain = prev
    out = embed_facturx(pdf, xml, f"{DOC_TYPES.get(inv.get('typ') or 'rechnung', DOC_TYPES['rechnung'])['title']} {inv['nr']}",
                        s.get("inhaber") or "", inv["nr"])
    return out, xml, info

# ---------------------------------------------------------------------------
# Optional: ZUGFeRD automatically on every invoice PDF (setting, default OFF)
# ---------------------------------------------------------------------------
@chain_step("render_invoice_pdf", "m50_erechnung_out")
def _m50_step_render_invoice_pdf(_next, inv, s=None, attachments=True):
    data = _next(inv, s, attachments)
    try:
        s2 = s or get_settings()
        if (s2.get("m50_zugferd_default") and inv and inv.get("id") and (inv.get("typ") or "rechnung") in ("rechnung", "storno")
                and inv.get("status") != "entwurf" and not str(inv.get("nr") or "").startswith("E-") and inv.get("items")):
            data, _, _ = m50_zugferd_pdf(inv, None, s2, base_pdf=data)
    except Exception:
        traceback.print_exc()
    return data

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _m50_outdir(inv, s):
    y = (inv.get("datum") or today())[:4]
    d = os.path.join(s.get("pdf_dir") or os.path.join(DATA_DIR, "Rechnungen"), y, "E-Rechnung")
    os.makedirs(d, exist_ok=True)
    return d


def _m50_opts(d, inv):
    o = {"buyer_ref": (d.get("buyer_ref") or "").strip(), "buyer_mail": (d.get("buyer_mail") or "").strip(),
         "order_ref": (d.get("order_ref") or "").strip()}
    if d.get("save_customer") and inv.get("customer_id") and o["buyer_ref"]:
        x("UPDATE customers SET leitweg_id=? WHERE id=?", (o["buyer_ref"], inv["customer_id"]))
    if d.get("save_customer") and inv.get("customer_id") and o["buyer_mail"]:
        c = q("SELECT mail FROM customers WHERE id=?", (inv["customer_id"],), one=True)
        if c and not (c["mail"] or "").strip():
            x("UPDATE customers SET mail=? WHERE id=?", (o["buyer_mail"], inv["customer_id"]))
    return o


def m50_route_info(h, qs):
    inv = get_invoice(int(qs["id"]))
    if not inv:
        raise ValueError("Rechnung nicht gefunden.")
    c = q("SELECT * FROM customers WHERE id=?", (inv["customer_id"],), one=True) if inv.get("customer_id") else None
    sd = m50_seller()
    return h._send(200, {"ok": True, "buyer_ref": (c or {}).get("leitweg_id") or "", "buyer_mail": (c or {}).get("mail") or "",
                         "kunde": (c or {}).get("firma") or (c or {}).get("name") or "", "seller": sd, "seller_missing": m50_seller_check(sd),
                         "typ": inv.get("typ"), "status": inv.get("status")})


def _m50_parse_ok(xml):
    """v2.0.6: check the XML BEFORE the invoice is locked and the file is written"""
    try:
        ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError as e:
        raise ValueError(f"Die E-Rechnung konnte nicht fehlerfrei erzeugt werden ({e}). Die Rechnung bleibt unverändert.")


def m50_route_export(h, d):
    inv = get_invoice(int(d["id"]))
    if not inv:
        raise ValueError("Rechnung nicht gefunden.")
    s = get_settings()
    opts = _m50_opts(d, inv)
    fmt = d.get("fmt") or "xml"
    safe = re.sub(r"[^0-9A-Za-z_-]", "", inv["nr"])
    if fmt == "zugferd":
        pdf, xml, info = m50_zugferd_pdf(inv, opts, s)
        _m50_parse_ok(xml)
        lock_invoice(inv["id"])
        path = os.path.join(_m50_outdir(inv, s), safe_name(f"rechnung_{safe}_zugferd.pdf"))
        write_file(path, pdf)
        back = pdf_embedded_xml(io.BytesIO(pdf))
        err = [] if back else ["Eingebettete XML wurde beim Zuruecklesen nicht gefunden."]
    else:
        xml, info = build_xrechnung(inv, opts, s)
        _m50_parse_ok(xml)
        lock_invoice(inv["id"])
        path = os.path.join(_m50_outdir(inv, s), safe_name(f"xrechnung_{safe}.xml"))
        write_file(path, xml)
        err = []
    err += m50_check_roundtrip(xml, info["summe"], len(inv["items"]))
    if d.get("open", True) and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(os.path.dirname(path) if fmt == "xml" else path)
    return h._send(200, {"ok": True, "path": path, "summe": info["summe"], "buyer_ref": info["buyer_ref"],
                         "warn": info["warn"], "pruefung": err,
                         "hinweis": "Technische Prüfung: Rücklesen mit dem eigenen Empfangs-Parser und Summenvergleich. "
                                    "Keine Validierung gegen den offiziellen KoSIT-Validator; PDF/A-3-Konformität wird nicht geprüft."})


def m50_route_settings(h, d):
    cur_ = get_settings().get("m50_seller") or {}
    for k in ("name", "inhaber", "strasse", "plz", "ort", "land", "tel", "mail", "steuernr", "ustid"):
        if k in (d.get("seller") or {}):
            cur_[k] = (d["seller"][k] or "").strip()
    set_setting("m50_seller", cur_)
    if "zugferd_default" in d:
        set_setting("m50_zugferd_default", bool(d["zugferd_default"]))
    return h._send(200, {"ok": True, "seller": m50_seller(), "missing": m50_seller_check(m50_seller())})


def m50_route_seller(h, qs):
    sd = m50_seller()
    return h._send(200, {"seller": sd, "missing": m50_seller_check(sd), "zugferd_default": bool(get_settings().get("m50_zugferd_default"))})


HOOK_GET["/api/m50/info"] = m50_route_info
HOOK_GET["/api/m50/seller"] = m50_route_seller
HOOK_POST["/api/m50/export"] = m50_route_export
HOOK_POST["/api/m50/settings"] = m50_route_settings

# ---------------------------------------------------------------------------
# Selftest: XRechnung round trip
# ---------------------------------------------------------------------------


def m50_selftest():
    err = []
    try:
        rows = q("SELECT id FROM invoices WHERE typ='rechnung' AND status!='entwurf' ORDER BY id LIMIT 3")
        if not rows:
            return ["m50: keine Rechnung in der Testdatenbank für den XRechnung-Rundlauf."]
        for r in rows:
            inv = get_invoice(r["id"])
            xml, info = build_xrechnung(inv, {"buyer_ref": "04011000-12345-67", "buyer_mail": "test@example.org"})
            ET.fromstring(xml)
            for e in m50_check_roundtrip(xml, inv["summe"], len(inv["items"])):
                err.append(f"m50 XRechnung {inv['nr']}: {e}")
            if b"<ram:CategoryCode>E</ram:CategoryCode>" not in xml or b"<ram:TaxTotalAmount currencyID=\"EUR\">0.00" not in xml:
                err.append(f"m50 XRechnung {inv['nr']}: Steuerkategorie E / Steuerbetrag 0 fehlt")
        inv = get_invoice(rows[0]["id"])
        pdf, xml, info = m50_zugferd_pdf(inv, {"buyer_ref": "n/a", "buyer_mail": "test@example.org"})
        back = pdf_embedded_xml(io.BytesIO(pdf))
        if not back:
            err.append("m50 ZUGFeRD: eingebettete XML nicht gefunden")
        elif abs(back[0]["betrag"] - inv["summe"]) > 0.005:
            err.append("m50 ZUGFeRD: Betrag der eingebetteten XML weicht ab")
    except Exception as e:
        err.append(f"m50 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m50_selftest)
