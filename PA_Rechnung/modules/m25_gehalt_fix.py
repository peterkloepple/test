# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m25_gehalt_fix (v2.0.0)
# Korrektur Gehaltsabrechnungen / Vorsorgeaufwendungen:
#  1) DEUEV-Meldebescheinigungen (Paragraph 25 DEUEV) werden erkannt und NICHT
#     als Monatsabrechnung gezaehlt (sie enthalten Entgelt, keine Beitraege).
#  2) Sozialversicherungs-Zeilen: statt "erster Betrag hinter dem Stichwort"
#     (= oft Bemessungsgrundlage/SV-Brutto oder Spalte "kumuliert") wird der
#     Betrag gewaehlt, der zum ueblichen AN-Beitragssatz passt.
#  3) Plausibilitaetspruefung: AN-Beitraege > 25 % vom Brutto oder ein Beitrag
#     >= Brutto -> Werte dieser Abrechnung zaehlen nicht, Warnung in der Steuer.
#  4) Bereits eingelesene Abrechnungen werden einmalig neu eingelesen
#     (alte Werte bleiben in details["alt_werte"]), Knopf zum erneuten Einlesen.
# Autor: T. Pfeiffer

SV_RATE = {"rv": 0.093, "kv": 0.0875, "pv": 0.018, "av": 0.013}   # typical employee shares
SV_MAX = {"rv": 0.12, "kv": 0.11, "pv": 0.03, "av": 0.02}          # upper plausible share of gross
MELDE_RE = re.compile(r"meldebescheinigung|de[uü]e?v|meldung zur sozialversicherung|meldegrund|"
                      r"beitragspflichtiges (?:brutto)?arbeitsentgelt|personengruppe.{0,40}beitragsgruppe", re.I)
SV_KEYS = {"rv": [r"rentenvers", r"\brv[- ]?beitrag", r"\brv\b"], "kv": [r"krankenvers", r"\bkv[- ]?beitrag", r"\bkv\b"],
           "pv": [r"pflegevers", r"\bpv[- ]?beitrag", r"\bpv\b"], "av": [r"arbeitslosenvers", r"\bav[- ]?beitrag", r"\bav\b"]}


def is_meldebescheinigung(text):
    low = (text or "").lower()
    hits = len(set(m.group(0).lower()[:12] for m in MELDE_RE.finditer(low)))
    payslip = re.search(r"auszahlungsbetrag|überweisungsbetrag|nettoverdienst|netto[- ]?bezug", low)
    return ("meldebescheinigung" in low or hits >= 2) and not payslip


def _line_amounts(line):
    out = []
    for m in re.finditer(AMT, line):
        after = line[m.end():m.end() + 3]
        if "%" in after:
            continue                      # contribution rate, not an amount
        try:
            out.append(abs(parse_amount(m.group(0))))
        except Exception:
            pass
    return out


def sv_amount(text, key, brutto):
    """pick the employee contribution for rv/kv/pv/av from the payslip lines"""
    cands = []
    lines = text.split("\n")
    for pat in SV_KEYS[key]:
        for i, line in enumerate(lines):
            if re.search(pat, line, re.I) and not re.search(r"arbeitgeber|ag[- ]?anteil", line, re.I):
                tail = re.split(pat, line, maxsplit=1, flags=re.I)[-1]
                am = _line_amounts(tail)
                if not am and i + 1 < len(lines):
                    am = _line_amounts(lines[i + 1])
                cands += am
        if cands:
            break
    if not cands:
        return 0.0
    if brutto > 0:
        ok = [c for c in cands if 0 < c <= brutto * SV_MAX[key]]
        if not ok:
            return 0.0
        target = brutto * SV_RATE[key]
        return round(min(ok, key=lambda c: abs(c - target)), 2)
    return round(min(c for c in cands if c > 0), 2) if any(c > 0 for c in cands) else 0.0


@chain_step("salary_fields", "m25_gehalt_fix")
def _m25_step_salary_fields(_next, text, year_doc):
    d = _next(text, year_doc)
    if not year_doc:
        b = float(d.get("brutto") or 0)
        for k in ("rv", "kv", "pv", "av"):
            d[k] = sv_amount(text, k, b)
    d["plausibel"] = salary_plausible(d)[0]
    return d


def salary_plausible(d):
    b = float(d.get("brutto") or 0)
    sv = {k: float(d.get(k) or 0) for k in ("rv", "kv", "pv", "av")}
    s = sum(sv.values())
    if b <= 0:
        return (s == 0), ("kein Brutto erkannt" if s else "")
    if any(v >= b for v in sv.values()):
        return False, "ein Sozialversicherungsbeitrag ist größer als das Brutto"
    if s > 0.25 * b:
        return False, f"AN-Beiträge {s:,.2f} € sind mehr als 25 % vom Brutto {b:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    for k, v in sv.items():
        if v > b * SV_MAX[k] * 1.2:
            return False, f"{k.upper()}-Beitrag unplausibel hoch"
    # v2.1.0: wage tax can never be close to the gross (top rate 45 % + Soli/KiSt; 50 % leaves room for one-off payments)
    lst = sum(float(d.get(k) or 0) for k in ("lst", "soli", "kist"))
    if lst > 0.5 * b:
        return False, f"Lohnsteuer/Soli/KiSt {lst:,.2f} € sind mehr als die Hälfte vom Brutto {b:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    if s + lst >= b:
        return False, "Abzüge sind größer als das Brutto"
    return True, ""


@chain_step("analyze_pdf", "m25_gehalt_fix")
def _m25_step_analyze_pdf(_next, path, filename, pw=None, pre_text=None, pre_fmt=None):
    res = _next(path, filename, pw, pre_text, pre_fmt)
    try:
        txt = pre_text if pre_text is not None else (res.get("text") or "")
        if res.get("typ") in ("gehalt", "ausgabe", "anlage") and is_meldebescheinigung(txt):
            res["typ"] = "gehalt"
            sv_b = first_amount_after(txt, [r"beitragspflichtiges.{0,20}entgelt", r"bruttoarbeitsentgelt", r"entgelt"])
            res["details"] = {"zeitraum": "meldung", "meldebescheinigung": True, "sv_brutto": sv_b}
            res["betrag"] = 0.0
            res["confidence"] = 0.9
            res["hint"] = ("DEÜV-Meldebescheinigung erkannt – enthält das Entgelt für die Rentenversicherung, keine Beiträge. "
                           "Wird abgelegt, fließt aber NICHT in Gehalt und Steuer ein (gehört in die Steuerakte).")
        elif res.get("typ") == "gehalt":
            ok, why = salary_plausible(res.get("details") or {})
            if not ok:
                res.setdefault("warnungen", []).append("Gehaltswerte unplausibel: " + why + " – bitte Werte prüfen.")
                res["hint"] = (res.get("hint") or "") + " Achtung: " + why + "."
    except Exception:
        traceback.print_exc()
    return res


def _doc_counts(d):
    """(counts_at_all, sv_counts, reason)"""
    if d.get("meldebescheinigung") or d.get("zeitraum") == "meldung":
        return False, False, "DEÜV-Meldebescheinigung"
    ok, why = salary_plausible(d)
    return True, ok, why


def salary_sum(year):
    """v2.0.0: like before, but skips DEUEV notices and SV values of implausible payslips"""
    rows = q("SELECT * FROM belege WHERE typ='gehalt' AND substr(datum,1,4)=?", (str(year),))
    by, warn = {}, []
    for r in rows:
        try:
            d = json.loads(r["details"] or "{}")
        except Exception:
            d = {}
        cnt, sv_ok, why = _doc_counts(d)
        if not cnt:
            continue
        if not sv_ok:
            d = dict(d)
            # implausible payslip: neither contributions nor wage tax count (warning stays)
            for k in ("rv", "kv", "pv", "av", "lst", "soli", "kist"):
                d[k] = 0.0
            warn.append({"id": r["id"], "datum": r["datum"], "partner": r["partner"] or "", "grund": why})
        key = (r["partner"] or "Arbeitgeber").strip().lower()
        by.setdefault(key, {"jahr": [], "monat": [], "name": r["partner"] or "Arbeitgeber"})
        by[key]["jahr" if d.get("zeitraum") == "jahr" else "monat"].append(d)
    tot = {k: 0.0 for k in ("brutto", "lst", "soli", "kist", "rv", "kv", "pv", "av", "netto")}
    emp = []
    for key, v in by.items():
        src = v["jahr"] if v["jahr"] else v["monat"]
        e = {k: round(sum(float(d.get(k) or 0) for d in src), 2) for k in tot}
        e["name"] = v["name"]
        e["quelle"] = "Lohnsteuerbescheinigung" if v["jahr"] else f"{len(v['monat'])} Monatsabrechnung(en)"
        emp.append(e)
        for k in tot:
            tot[k] += e[k]
    SALARY_WARN[int(year)] = warn
    return {k: round(v, 2) for k, v in tot.items()}, emp


SALARY_WARN = {}
@chain_step("tax_calc", "m25_gehalt_fix")
def _m25_step_tax_calc(_next, year):
    r = _next(year)
    w = SALARY_WARN.get(int(year)) or []
    melde = q("SELECT COUNT(*) n FROM belege WHERE typ='gehalt' AND substr(datum,1,4)=? AND details LIKE '%meldebescheinigung%'", (str(year),), one=True)["n"]
    r["gehalt_warnungen"] = w
    r["gehalt_meldebescheinigungen"] = melde
    g = r.get("gehalt") or {}
    b = float(g.get("brutto") or 0)
    sv = sum(float(g.get(k) or 0) for k in ("rv", "kv", "pv", "av"))
    r["gehalt_sv_quote"] = round(100 * sv / b, 1) if b else 0.0
    return r


@chain_step("stats_detail", "m25_gehalt_fix")
def _m25_step_stats_detail(_next, year=None):
    d = _next(year)
    rows_ = d.get("gehalt") or []
    # v2.0.6: one query for all payslips instead of one per row
    ids_ = [int(r_["id"]) for r_ in rows_ if r_.get("id")]
    dets_ = {}
    for i0 in range(0, len(ids_), 500):
        part = ids_[i0:i0 + 500]
        for b_ in q(f"SELECT id, details FROM belege WHERE id IN ({','.join('?' * len(part))})", part):
            dets_[b_["id"]] = b_["details"]
    for row in rows_:
        b = {"details": dets_[row["id"]]} if row.get("id") in dets_ else None
        try:
            det = json.loads(b["details"] or "{}") if b else {}
        except Exception:
            det = {}
        cnt, sv_ok, why = _doc_counts(det)
        if not cnt:
            row["zaehlt"] = False
            row["zeitraum"] = "DEÜV-Meldebescheinigung (nicht gezählt)"
            row["brutto"] = row["netto"] = 0.0
        elif not sv_ok:
            for k in ("rv", "kv", "pv", "av", "lst", "soli", "kist"):
                row[k] = 0.0
            row["sozial"] = 0.0
            row["steuer"] = 0.0
            row["zeitraum"] = (row.get("zeitraum") or "") + " · SV-Werte unplausibel"
    return d


def gehalt_reparse(only_bad=True):
    """re-read stored payslips with the corrected parser; old values are kept in details['alt_werte']"""
    n, changed, melde, errs = 0, 0, 0, []
    for b in q("SELECT * FROM belege WHERE typ='gehalt' AND file<>'' ORDER BY datum"):
        try:
            det = json.loads(b["details"] or "{}")
        except Exception:
            det = {}
        if det.get("korrektur"):
            continue                          # correction entries from the year-end check stay untouched
        if only_bad and _doc_counts(det)[1]:
            continue
        fp = b["file"] if os.path.isabs(b["file"]) else os.path.join(DATA_DIR, b["file"])
        if not os.path.isfile(fp):
            continue
        n += 1
        try:
            text, _, _ = extract_text_any(fp, os.path.basename(fp), None)
        except Exception as e:
            errs.append(f"{os.path.basename(fp)}: {e}")
            continue
        if not text.strip():
            continue
        if is_meldebescheinigung(text):
            new = {"zeitraum": "meldung", "meldebescheinigung": True,
                   "sv_brutto": first_amount_after(text, [r"beitragspflichtiges.{0,20}entgelt", r"bruttoarbeitsentgelt", r"entgelt"])}
            melde += 1
        else:
            year_doc = "lohnsteuerbescheinigung" in text.lower()
            new = salary_fields(text, year_doc)
            if det.get("periode") and not new.get("periode"):
                new["periode"] = det["periode"]
        keys = ("zeitraum", "brutto", "lst", "soli", "kist", "rv", "kv", "pv", "av", "netto", "meldebescheinigung")
        if any((det.get(k) or 0) != (new.get(k) or 0) for k in keys):
            new["alt_werte"] = {k: det.get(k) for k in keys if k in det}
            new["neu_eingelesen"] = now_iso()
            x("UPDATE belege SET details=?, betrag=? WHERE id=?",
              (json.dumps(new, ensure_ascii=False), float(new.get("brutto") or 0) if not new.get("meldebescheinigung") else 0.0, b["id"]))
            changed += 1
    return {"ok": True, "geprueft": n, "geaendert": changed, "meldebescheinigungen": melde, "fehler": errs[:5]}


def _gehalt_migrate():
    if get_settings().get("gehalt_fix_v200"):
        return
    try:
        r = gehalt_reparse(only_bad=True)   # only implausible ones - manual corrections stay untouched
        set_setting("gehalt_fix_v200", {"zeit": now_iso(), **{k: r[k] for k in ("geprueft", "geaendert", "meldebescheinigungen")}})
    except Exception:
        traceback.print_exc()


def _gehalt_selftest():
    errs = []
    slip = ("Entgeltabrechnung Oktober 2026\nGesamt-Brutto 3.000,00 30.000,00\nLohnsteuer 300,00\n"
            "Rentenversicherung 9,30 % 3.000,00 279,00 2.790,00\nKrankenversicherung 8,75 % 3.000,00 262,50 2.625,00\n"
            "Pflegeversicherung 1,80 % 3.000,00 54,00\nArbeitslosenversicherung 1,30 % 3.000,00 39,00\nAuszahlungsbetrag 2.065,50\n")
    d = salary_fields(slip, False)
    for k, v in (("rv", 279.0), ("kv", 262.5), ("pv", 54.0), ("av", 39.0)):
        if abs((d.get(k) or 0) - v) > 0.01:
            errs.append(f"{k} gelesen {d.get(k)} statt {v}")
    if not salary_plausible(d)[0]:
        errs.append("plausible Abrechnung als unplausibel markiert")
    if salary_plausible({"brutto": 3000, "rv": 3000, "kv": 19000})[0]:
        errs.append("unplausible Werte nicht erkannt")
    if not is_meldebescheinigung("Meldebescheinigung zur Sozialversicherung nach § 25 DEÜV\nBeitragspflichtiges Bruttoarbeitsentgelt 34.577"):
        errs.append("DEÜV-Meldebescheinigung nicht erkannt")
    if is_meldebescheinigung(slip):
        errs.append("Abrechnung faelschlich als Meldebescheinigung erkannt")
    return errs


HOOK_START.append(_gehalt_migrate)
HOOK_POST["/api/gehalt/neu_einlesen"] = lambda h, d: h._send(200, gehalt_reparse(only_bad=not d.get("alle")))
HOOK_SELFTEST.append(_gehalt_selftest)
