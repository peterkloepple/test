# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m41_aufmass_kalk
# Aufmass-Liste je Projekt (mit sicherer Formelauswertung, KEIN eval) und
# Kalkulation aus Inventor-Stueckliste (Material, Lohn, Zuschlaege, Marge) -> Angebot / PDF.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M41_EINHEITEN = ["m", "m2", "m3", "Stk", "kg", "h"]
M41_EINHEIT_DE = {"m": "m", "m2": "m²", "m3": "m³", "Stk": "Stk", "kg": "kg", "h": "Std"}


def _m41_schema():
    x("CREATE TABLE IF NOT EXISTS m41_aufmass (id INTEGER PRIMARY KEY, project_id INTEGER, pos TEXT, beschreibung TEXT, "
      "modus TEXT, l REAL, b REAL, h REAL, anz REAL, formel TEXT, einheit TEXT, ergebnis REAL, preis REAL, "
      "article_id INTEGER, sort INTEGER DEFAULT 0, invoice_id INTEGER, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS m41_kalk (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, data TEXT, result TEXT, "
      "angebot_id INTEGER, created TEXT, updated TEXT)")


HOOK_SCHEMA.append(_m41_schema)


# ---------------------------------------------------------------------------
# Safe formula evaluation (tokenizer + recursive descent parser, no eval)
# Grammar: expr := term (('+'|'-') term)* ; term := unary (('*'|'/') unary)*
#          unary := ('-'|'+') unary | power ; power := atom ('^' unary)? ; atom := number | '(' expr ')'
# German decimal comma accepted; 'x', 'X', and the multiplication sign act as '*'; ':' acts as '/'.
# ---------------------------------------------------------------------------
class M41FormelFehler(ValueError):
    pass


def _m41_tokens(s):
    s = (s or "").strip()
    if not s:
        raise M41FormelFehler("Formel ist leer.")
    if len(s) > 300:
        raise M41FormelFehler("Formel ist zu lang (max. 300 Zeichen).")
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch in " \t":
            i += 1
            continue
        if ch.isdigit() or ch in ".,":
            j = i
            while j < len(s) and (s[j].isdigit() or s[j] in ".,"):
                j += 1
            raw = s[i:j]
            # "1.234,5" -> thousands dot + decimal comma; "3,5" -> 3.5; "3.5" -> 3.5
            if "," in raw:
                raw = raw.replace(".", "").replace(",", ".")
            if raw.count(".") > 1 or raw == ".":
                raise M41FormelFehler(f"Ungültige Zahl „{s[i:j]}“.")
            out.append(("n", float(raw)))
            i = j
            continue
        if ch in "xX×⋅*":
            out.append(("o", "*"))
        elif ch in ":/÷":
            out.append(("o", "/"))
        elif ch in "+-^()":
            out.append(("o", ch))
        elif ch in "−":
            out.append(("o", "-"))
        else:
            raise M41FormelFehler(f"Unerlaubtes Zeichen „{ch}“ in der Formel.")
        i += 1
    return out


def m41_formel(s):
    """evaluate an arithmetic formula like '2*3,5+1,2' safely; returns float"""
    toks = _m41_tokens(s)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else (None, None)

    def take():
        t = peek()
        pos[0] += 1
        return t

    def expr(depth):
        if depth > 50:
            raise M41FormelFehler("Formel zu tief verschachtelt.")
        v = term(depth)
        while peek() in (("o", "+"), ("o", "-")):
            op = take()[1]
            r = term(depth)
            v = v + r if op == "+" else v - r
        return v

    def term(depth):
        v = unary(depth)
        while peek() in (("o", "*"), ("o", "/")):
            op = take()[1]
            r = unary(depth)
            if op == "*":
                v *= r
            else:
                if r == 0:
                    raise M41FormelFehler("Division durch 0.")
                v /= r
        return v

    def unary(depth):
        if peek() == ("o", "-"):
            take()
            return -unary(depth + 1)
        if peek() == ("o", "+"):
            take()
            return unary(depth + 1)
        return power(depth)

    def power(depth):
        v = atom(depth)
        if peek() == ("o", "^"):
            take()
            e = unary(depth + 1)
            if abs(e) > 6:
                raise M41FormelFehler("Exponent zu groß (max. 6).")
            v = v ** e
        return v

    def atom(depth):
        k, v = take()
        if k == "n":
            return v
        if (k, v) == ("o", "("):
            r = expr(depth + 1)
            if take() != ("o", ")"):
                raise M41FormelFehler("Schließende Klammer fehlt.")
            return r
        raise M41FormelFehler("Formel unvollständig." if k is None else f"Unerwartetes Zeichen „{v}“.")

    try:
        res = expr(0)
    except (OverflowError, ZeroDivisionError, TypeError):
        raise M41FormelFehler("Ergebnis ungültig (zu groß oder nicht berechenbar).")
    if pos[0] != len(toks):
        raise M41FormelFehler(f"Unerwartetes Zeichen „{toks[pos[0]][1]}“.")
    if isinstance(res, complex) or res != res or abs(res) > 1e12:
        raise M41FormelFehler("Ergebnis ungültig.")
    return round(float(res), 6)


def m41_ergebnis(r):
    """result of one Aufmass row: formula or product of L x B x H x Anzahl (empty fields ignored)"""
    if (r.get("modus") or "lbh") == "formel":
        return round(m41_formel(r.get("formel") or ""), 4)
    vals = [r.get(k) for k in ("l", "b", "h")]
    vals = [float(v) for v in vals if v not in (None, "") and float(v) != 0]
    anz = float(r.get("anz")) if r.get("anz") not in (None, "") else 1.0   # v2.0.6: 0 stays 0
    if not vals:
        return round(anz, 4)
    p = 1.0
    for v in vals:
        p *= v
    return round(p * anz, 4)


def _m41_fnum(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"„{v}“ ist keine Zahl.")


def _m41_link_ok(iid, pid, src):
    """v2.6.3: a stored invoice link is only valid if that invoice still belongs to the project and was created here.
    SQLite reuses the id of a deleted invoice (no AUTOINCREMENT) - a deleted draft must not point to a new, unrelated document."""
    if not iid:
        return False
    r = q("SELECT project_id, COALESCE(source, '') source FROM invoices WHERE id=?", (iid,), one=True)
    return bool(r) and r["project_id"] == pid and r["source"] == src


def m41_aufmass_list(pid):
    rows = q("SELECT * FROM m41_aufmass WHERE project_id=? ORDER BY sort, id", (pid,))
    for r in rows:
        if r.get("invoice_id") and not _m41_link_ok(r["invoice_id"], pid, "m41_aufmass"):
            r["invoice_id"] = None     # invoice deleted (id may be reused) -> position is free again
    return rows


def m41_aufmass_save(d):
    r = {"modus": "formel" if d.get("modus") == "formel" else "lbh", "formel": (d.get("formel") or "").strip()}
    for k in ("l", "b", "h", "anz"):
        r[k] = _m41_fnum(d.get(k))
    try:
        erg = m41_ergebnis(r)
    except M41FormelFehler as e:
        raise ValueError(f"Formel: {e}")
    einheit = d.get("einheit") if d.get("einheit") in M41_EINHEITEN else "Stk"
    preis = _m41_fnum(d.get("preis")) or 0.0
    aid = int(d["article_id"]) if d.get("article_id") else None
    if aid and not d.get("preis_manuell") and not preis:
        a = q("SELECT price FROM articles WHERE id=?", (aid,), one=True)
        preis = float(a["price"] or 0) if a else 0.0
    vals = (int(d["project_id"]), (d.get("pos") or "").strip(), (d.get("beschreibung") or "").strip(), r["modus"],
            r["l"], r["b"], r["h"], r["anz"], r["formel"], einheit, erg, preis, aid)
    if d.get("id"):
        x("UPDATE m41_aufmass SET project_id=?, pos=?, beschreibung=?, modus=?, l=?, b=?, h=?, anz=?, formel=?, einheit=?, "
          "ergebnis=?, preis=?, article_id=? WHERE id=?", vals + (int(d["id"]),))
        return int(d["id"])
    n = q("SELECT COALESCE(MAX(sort),0)+1 n FROM m41_aufmass WHERE project_id=?", (vals[0],), one=True)["n"]
    return x("INSERT INTO m41_aufmass (project_id, pos, beschreibung, modus, l, b, h, anz, formel, einheit, ergebnis, preis, "
             "article_id, sort, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (n, now_iso()))


def _m41_fmt_formel(r):
    if r["modus"] == "formel":
        return r["formel"] or ""
    parts = [num_de(float(r[k]), 3).rstrip("0").rstrip(",") for k in ("l", "b", "h") if r[k] not in (None, 0)]
    a = r["anz"]
    if a not in (None, 1, 1.0):
        parts.append(num_de(float(a), 3).rstrip("0").rstrip(",") + " Stk")
    return " × ".join(parts)


def m41_aufmass_to_doc(pid, ids, typ):
    # v2.6.3: serialized - a double click billed the same positions twice
    with DOC_LOCK:
        return _m41_aufmass_to_doc(pid, ids, typ)


def _m41_aufmass_to_doc(pid, ids, typ):
    if typ not in ("angebot", "rechnung"):
        raise ValueError("Bitte Angebot oder Rechnung wählen.")
    rows = [r for r in m41_aufmass_list(pid) if not ids or r["id"] in set(int(i) for i in ids)]
    if not rows:
        raise ValueError("Keine Aufmaß-Positionen ausgewählt.")
    if typ == "rechnung":
        # v2.0.6: positions already billed (invoice not cancelled) are not billed a second time
        # v2.1.0: a cancelled PAID invoice keeps status 'bezahlt' (storno_von set) - it is cancelled too
        done = [r for r in rows if r.get("invoice_id") and q("SELECT id FROM invoices WHERE id=? AND status NOT IN ('storniert') "
                                                            "AND storno_von IS NULL", (r["invoice_id"],), one=True)]
        if done and len(done) == len(rows):
            raise ValueError(f"Die {len(done)} gewählten Aufmaß-Position(en) sind bereits abgerechnet.")
        rows = [r for r in rows if r not in done]
    p, s, d = _m40_head(pid)
    items = []
    for r in rows:
        a = q("SELECT nr, name, descr FROM articles WHERE id=?", (r["article_id"],), one=True) if r["article_id"] else None
        name = r["beschreibung"] or (a["name"] if a else "Aufmaß-Position")
        dsc = f"Aufmaß{(' Pos. ' + r['pos']) if r['pos'] else ''}: {_m41_fmt_formel(r)} = {num_de(r['ergebnis'], 3).rstrip('0').rstrip(',')} {M41_EINHEIT_DE.get(r['einheit'], r['einheit'])}"
        if a and a["descr"] and not r["beschreibung"]:
            dsc = a["descr"].split("\n")[0] + "\n" + dsc
        items.append({"qty": round(float(r["ergebnis"] or 0), 3), "nr": a["nr"] if a else (r["pos"] or ""), "name": name,
                      "descr": dsc, "price": float(r["preis"] or 0), "rabatt": 0, "article_id": r["article_id"]})
    if typ == "angebot":
        gb = (datetime.date.today() + datetime.timedelta(days=int(s.get("angebot_gueltig") or 30))).isoformat()
        d.update(typ="angebot", titel=f"Angebot {p['name']}", toptext=s.get("default_top_angebot", ""),
                 foottext=s.get("default_foot_angebot", ""), gueltig_bis=gb, liefer="", auftrag="")
    else:
        d.update(typ="rechnung", titel=f"Rechnung {p['name']} nach Aufmaß", toptext=s.get("default_top", ""))
    d.update(items=items, source="m41_aufmass")
    iid, nr = save_invoice(d)
    if typ == "rechnung":
        x(f"UPDATE m41_aufmass SET invoice_id=? WHERE id IN ({','.join('?' * len(rows))})", [iid] + [r["id"] for r in rows])
    return {"ok": True, "id": iid, "nr": nr, "n": len(items)}


# ---------------------------------------------------------------------------
# Kalkulation
# ---------------------------------------------------------------------------
M41_KALK_DEFAULT = {"rows": [], "arbeit": [{"bez": "Fertigung / Schweißen", "std": 0}, {"bez": "Montage", "std": 0}],
                    "stundensatz": None, "mat_zuschlag": None, "gk": 15.0, "gewinn": 10.0, "fremd": 0.0,
                    "fremd_text": "", "titel": ""}


def m41_kalk_calc(data, preise=None):
    """pure calculation. data: rows [{qty, masse_kg, material, ek_stk}], arbeit [{std}], stundensatz,
    mat_zuschlag %, gk %, gewinn %, fremd EUR. returns dict with all values (rounded 2)"""
    s = None
    if preise is None or data.get("stundensatz") in (None, "") or data.get("mat_zuschlag") in (None, ""):
        s = get_settings()
    preise = preise if preise is not None else (s.get("materialpreise") or {})
    satz = float(data["stundensatz"]) if data.get("stundensatz") not in (None, "") else float(s.get("stundensatz") or 0)
    mz = float(data["mat_zuschlag"]) if data.get("mat_zuschlag") not in (None, "") else float(s.get("aufschlag") or 0)
    gk = float(data.get("gk") or 0)
    gw = float(data.get("gewinn") or 0)
    fremd = float(data.get("fremd") or 0)
    rows = []
    material = 0.0
    kg = 0.0
    for r in data.get("rows") or []:
        if r.get("use") is False:
            continue
        qty = float(r.get("qty") or 0)
        masse = float(r.get("masse_kg") or 0)
        ek = r.get("ek_stk")
        pk = r.get("preis_kg")
        if pk in (None, ""):
            pk = preise.get(r.get("material") or "")
        pk = float(pk) if pk not in (None, "") else None
        if ek not in (None, "") and float(ek) > 0:
            ek_stk, quelle = float(ek), "EK"
        elif pk is not None and masse:
            ek_stk, quelle = masse * pk, "kg"
        else:
            ek_stk, quelle = 0.0, "fehlt"
        sum_ = round(ek_stk * qty, 2)
        material += sum_
        kg += masse * qty
        rows.append(dict(r, ek_calc=round(ek_stk, 4), preis_kg_used=pk, summe=sum_, quelle=quelle))
    std = sum(float(a.get("std") or 0) for a in data.get("arbeit") or [])
    lohn = std * satz
    mat_zu = material * mz / 100.0
    herstell = material + mat_zu + lohn + fremd
    gk_eur = herstell * gk / 100.0
    selbst = herstell + gk_eur
    gewinn = selbst * gw / 100.0
    preis = selbst + gewinn
    r2 = lambda v: round(v + 1e-9, 2)
    return {"rows": rows, "material": r2(material), "kg": round(kg, 3), "mat_zuschlag_pct": mz, "mat_zuschlag": r2(mat_zu),
            "stunden": round(std, 2), "stundensatz": satz, "lohn": r2(lohn), "fremd": r2(fremd), "herstell": r2(herstell),
            "gk_pct": gk, "gk": r2(gk_eur), "selbstkosten": r2(selbst), "gewinn_pct": gw, "gewinn": r2(gewinn),
            "angebotspreis": r2(preis), "fehlende_preise": sum(1 for r in rows if r["quelle"] == "fehlt"),
            # factor from cost to sales price - used for detailed offer lines
            "faktor_material": (1 + mz / 100.0) * (1 + gk / 100.0) * (1 + gw / 100.0),
            "faktor_lohn": (1 + gk / 100.0) * (1 + gw / 100.0)}


def _m41_kalk_load(kid):
    k = q("SELECT * FROM m41_kalk WHERE id=?", (kid,), one=True)
    if not k:
        raise ValueError("Kalkulation nicht gefunden.")
    k["data"] = dict(M41_KALK_DEFAULT, **json.loads(k["data"] or "{}"))
    k["result"] = json.loads(k["result"] or "{}")
    if k.get("angebot_id") and not _m41_link_ok(k["angebot_id"], k["project_id"], "m41_kalk"):
        k["angebot_id"] = None
    return k


def m41_kalk_list(pid):
    out = []
    for k in q("SELECT id, project_id, name, result, angebot_id, updated FROM m41_kalk WHERE project_id=? ORDER BY id DESC", (pid,)):
        r = json.loads(k["result"] or "{}")
        out.append({"id": k["id"], "name": k["name"], "updated": k["updated"],
                    "angebot_id": k["angebot_id"] if _m41_link_ok(k["angebot_id"], pid, "m41_kalk") else None,
                    "angebotspreis": r.get("angebotspreis", 0), "stunden": r.get("stunden", 0), "material": r.get("material", 0)})
    return out


def m41_kalk_save(d):
    pid = int(d["project_id"])
    data = dict(M41_KALK_DEFAULT, **(d.get("data") or {}))
    clean_rows = []
    for r in data.get("rows") or []:
        clean_rows.append({"nr": str(r.get("nr") or "")[:60], "name": str(r.get("name") or "")[:160],
                           "qty": _m41_fnum(r.get("qty")) or 0.0, "unit": str(r.get("unit") or "Stk")[:10],
                           "material": str(r.get("material") or "")[:60], "masse_kg": _m41_fnum(r.get("masse_kg")) or 0.0,
                           "ek_stk": _m41_fnum(r.get("ek_stk")), "preis_kg": _m41_fnum(r.get("preis_kg")),
                           "use": r.get("use") is not False})
    data["rows"] = clean_rows
    data["arbeit"] = [{"bez": str(a.get("bez") or "")[:80], "std": _m41_fnum(a.get("std")) or 0.0} for a in data.get("arbeit") or []]
    for k in ("stundensatz", "mat_zuschlag", "gk", "gewinn", "fremd"):
        data[k] = _m41_fnum(data.get(k))
    res = m41_kalk_calc(data)
    name = (d.get("name") or "").strip() or f"Kalkulation {today()}"
    if d.get("id"):
        x("UPDATE m41_kalk SET name=?, data=?, result=?, updated=? WHERE id=?",
          (name, json.dumps(data, ensure_ascii=False), json.dumps(res, ensure_ascii=False), now_iso(), int(d["id"])))
        kid = int(d["id"])
    else:
        kid = x("INSERT INTO m41_kalk (project_id, name, data, result, created, updated) VALUES (?,?,?,?,?,?)",
                (pid, name, json.dumps(data, ensure_ascii=False), json.dumps(res, ensure_ascii=False), now_iso(), now_iso()))
    return kid, res


def m41_kalk_to_angebot(kid, mode):
    k = _m41_kalk_load(kid)
    res = m41_kalk_calc(k["data"])
    pid = k["project_id"]
    p, s, d = _m40_head(pid)
    titel = k["data"].get("titel") or k["name"]
    items = []
    if mode == "pauschal":
        npos = len(res["rows"])
        dsc = [f"Material lt. Stückliste ({npos} Positionen{', ' + num_de(res['kg'], 1) + ' kg' if res['kg'] else ''})"] if npos else []
        if res["stunden"]:
            dsc.append(f"Fertigung und Montage ca. {num_de(res['stunden'], 1)} Std")
        if res["fremd"]:
            dsc.append(k["data"].get("fremd_text") or "Fremdleistungen")
        items.append({"qty": 1, "nr": "", "name": titel, "descr": "\n".join(dsc), "price": res["angebotspreis"], "rabatt": 0})
    else:
        fm, fl = res["faktor_material"], res["faktor_lohn"]
        for r in res["rows"]:
            if not r["qty"]:
                continue
            dsc = " · ".join(v for v in (r.get("material") or "", (num_de(r["masse_kg"], 2) + " kg/Stk") if r.get("masse_kg") else "") if v)
            items.append({"qty": r["qty"], "nr": r.get("nr") or "", "name": r.get("name") or "Material", "descr": dsc,
                          "price": round(r["ek_calc"] * fm + 1e-9, 2), "rabatt": 0})
        for a in k["data"].get("arbeit") or []:
            if float(a.get("std") or 0):
                items.append({"qty": float(a["std"]), "nr": "", "name": a.get("bez") or "Arbeitszeit", "descr": "Stunden",
                              "price": round(res["stundensatz"] * fl + 1e-9, 2), "rabatt": 0})
        if res["fremd"]:
            items.append({"qty": 1, "nr": "", "name": k["data"].get("fremd_text") or "Fremdleistungen", "descr": "",
                          "price": round(res["fremd"] * fl + 1e-9, 2), "rabatt": 0})
        if not items:
            raise ValueError("Die Kalkulation enthält keine Positionen.")
        diff = round(res["angebotspreis"] - sum(line_total(i) for i in items), 2)
        if abs(diff) >= 0.01:
            items.append({"qty": 1, "nr": "", "name": "Rundungsausgleich Kalkulation", "descr": "", "price": diff, "rabatt": 0})
    gb = (datetime.date.today() + datetime.timedelta(days=int(s.get("angebot_gueltig") or 30))).isoformat()
    d.update(typ="angebot", titel=f"Angebot {titel}", toptext=s.get("default_top_angebot", ""),
             foottext=s.get("default_foot_angebot", ""), gueltig_bis=gb, liefer="", auftrag="", items=items, source="m41_kalk")
    iid, nr = save_invoice(d)
    x("UPDATE m41_kalk SET angebot_id=? WHERE id=?", (iid, kid))
    return {"ok": True, "id": iid, "nr": nr, "summe": round(sum(line_total(i) for i in items), 2)}


def m41_kalk_pdf(kid):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    k = _m41_kalk_load(kid)
    res = m41_kalk_calc(k["data"])
    p = get_project(k["project_id"])
    acc, ink, gray, line, soft = (colors.HexColor("#5b3fd6"), colors.HexColor("#1e1a2b"), colors.HexColor("#6c6880"),
                                  colors.HexColor("#e4e1ee"), colors.HexColor("#f3f1fb"))
    N = ParagraphStyle("n", fontName=FONT_R(), fontSize=9, leading=12, textColor=ink)
    NS = ParagraphStyle("ns", parent=N, fontSize=7.5, leading=9.5, textColor=gray)
    KIC = ParagraphStyle("k", fontName=FONT_B(), fontSize=7.5, leading=9, textColor=acc)
    H1 = ParagraphStyle("h1", fontName=FONT_B(), fontSize=19, leading=23, textColor=ink, spaceAfter=2)
    H2 = ParagraphStyle("h2", fontName=FONT_B(), fontSize=11.5, leading=15, textColor=ink, spaceBefore=10, spaceAfter=5)
    m = lambda v: money(v).replace(" EUR", " €")
    e = esc_xml
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=16 * mm,
                            title=f"Kalkulation {p['nr']} {k['name']}", author="T. Pfeiffer", creator=f"{APP_NAME} v{APP_VERSION}")
    el = [Paragraph("KALKULATION", KIC), Paragraph(e(k["name"]), H1),
          Paragraph(f"{e(p['nr'])} · {e(p['name'])} · Kunde: {e(((p['customer'] or {}).get('firma') or (p['customer'] or {}).get('name') or '-'))}"
                    f" · Stand {de_date(today())}", NS), Spacer(1, 8)]
    ts_base = [("FONT", (0, 0), (-1, 0), FONT_B(), 7.5), ("TEXTCOLOR", (0, 0), (-1, 0), gray),
               ("FONT", (0, 1), (-1, -1), FONT_R(), 8), ("LINEBELOW", (0, 0), (-1, 0), 0.6, ink),
               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
               ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    # summary block
    summ = [["Position", "Basis", "Betrag"],
            ["Materialkosten (Stückliste)", f"{num_de(res['kg'], 2)} kg", m(res["material"])],
            ["Material-Zuschlag", f"{num_de(res['mat_zuschlag_pct'], 1)} %", m(res["mat_zuschlag"])],
            ["Lohnkosten", f"{num_de(res['stunden'], 2)} Std × {m(res['stundensatz'])}", m(res["lohn"])]]
    if res["fremd"]:
        summ.append([k["data"].get("fremd_text") or "Fremdleistungen", "", m(res["fremd"])])
    summ += [["Herstellkosten", "", m(res["herstell"])],
             ["Gemeinkosten", f"{num_de(res['gk_pct'], 1)} % auf Herstellkosten", m(res["gk"])],
             ["Selbstkosten", "", m(res["selbstkosten"])],
             ["Gewinn / Marge", f"{num_de(res['gewinn_pct'], 1)} % auf Selbstkosten", m(res["gewinn"])],
             ["Angebotspreis", "netto, zzgl. USt" if _m40_regel(today()) else "Kleinunternehmer, ohne USt-Ausweis",
              m(res["angebotspreis"])]]
    t = Table(summ, colWidths=[62 * mm, 70 * mm, 42 * mm])
    bold_rows = [i for i, r in enumerate(summ) if r[0] in ("Herstellkosten", "Selbstkosten", "Angebotspreis")]
    st = list(ts_base) + [("ALIGN", (2, 0), (2, -1), "RIGHT")]
    for i in bold_rows:
        st.append(("FONT", (0, i), (-1, i), FONT_B(), 8.5))
        st.append(("LINEABOVE", (0, i), (-1, i), 0.4, line))
    st.append(("BACKGROUND", (0, len(summ) - 1), (-1, len(summ) - 1), colors.HexColor("#e9e4fb")))
    st.append(("TEXTCOLOR", (2, len(summ) - 1), (2, len(summ) - 1), acc))
    t.setStyle(TableStyle(st))
    el += [Paragraph("Zusammenfassung", H2), t]
    if res["rows"]:
        rows = [["Nr.", "Benennung", "Menge", "Material", "kg/Stk", "€/kg", "EK/Stk", "Summe"]]
        for r in res["rows"]:
            rows.append([Paragraph(e(r.get("nr") or ""), NS), Paragraph(e(r.get("name") or ""), ParagraphStyle("c", parent=N, fontSize=8, leading=10)),
                         num_de(r["qty"], 2).rstrip("0").rstrip(",") + " " + (r.get("unit") or ""), e(r.get("material") or ""),
                         num_de(r["masse_kg"], 3) if r.get("masse_kg") else "",
                         num_de(r["preis_kg_used"], 2) if r.get("preis_kg_used") is not None else "",
                         m(r["ek_calc"]) + ("" if r["quelle"] != "fehlt" else " !"), m(r["summe"])])
        rows.append(["", "Summe Material", "", "", num_de(res["kg"], 2) + " kg", "", "", m(res["material"])])
        t2 = Table(rows, colWidths=[22 * mm, 50 * mm, 16 * mm, 24 * mm, 14 * mm, 12 * mm, 18 * mm, 18 * mm], repeatRows=1)
        t2.setStyle(TableStyle(list(ts_base) + [("ALIGN", (2, 0), (2, -1), "RIGHT"), ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
                                                ("FONT", (0, -1), (-1, -1), FONT_B(), 8), ("LINEABOVE", (0, -1), (-1, -1), 0.6, ink)]))
        el += [Paragraph("Material aus Stückliste", H2), t2]
        if res["fehlende_preise"]:
            el.append(Paragraph(f"! {res['fehlende_preise']} Position(en) ohne Preis (weder EK noch Materialpreis je kg) - mit 0 € gerechnet.", NS))
    arb = [a for a in k["data"].get("arbeit") or [] if float(a.get("std") or 0)]
    if arb:
        rows = [["Arbeitsgang", "Stunden", "Satz", "Summe"]] + \
               [[e(a.get("bez") or ""), num_de(float(a["std"]), 2), m(res["stundensatz"]), m(float(a["std"]) * res["stundensatz"])] for a in arb]
        t3 = Table(rows, colWidths=[90 * mm, 25 * mm, 30 * mm, 29 * mm])
        t3.setStyle(TableStyle(list(ts_base) + [("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
        el += [Paragraph("Arbeitszeit", H2), t3]
    el += [Spacer(1, 10), Paragraph("Interne Kalkulation - nicht zur Weitergabe an den Kunden bestimmt. Erstellt von T. Pfeiffer.", NS)]

    def onpage(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(gray)
        cv.drawString(18 * mm, 9 * mm, f"Kalkulation {p['nr']} · {k['name']} · T. Pfeiffer")
        cv.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Seite {dc.page}")
        cv.setStrokeColor(acc)
        cv.setLineWidth(2)
        cv.line(18 * mm, A4[1] - 10 * mm, 40 * mm, A4[1] - 10 * mm)
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    data = buf.getvalue()
    base = ensure_project_folders(q("SELECT * FROM projects WHERE id=?", (k["project_id"],), one=True))
    fp = os.path.join(base, safe_name(f"Kalkulation_{p['nr']}_{k['name']}_{today()}.pdf"))
    write_file(fp, data)
    rel = os.path.relpath(fp, DATA_DIR)
    if not q("SELECT id FROM project_files WHERE path=?", (rel,), one=True):
        x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
          (k["project_id"], "", "Dokument", os.path.basename(fp), rel, len(data), "Kalkulation", now_iso()))
    else:
        x("UPDATE project_files SET size=? WHERE path=?", (len(data), rel))
    if not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return fp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _m41_g_aufmass(h, qs):
    return h._send(200, {"rows": m41_aufmass_list(int(qs["project_id"])), "einheiten": M41_EINHEITEN})


def _m41_p_aufmass_save(h, d):
    return h._send(200, {"ok": True, "id": m41_aufmass_save(d)})


def _m41_p_aufmass_del(h, d):
    x("DELETE FROM m41_aufmass WHERE id=?", (int(d["id"]),))
    return h._send(200, {"ok": True})


def _m41_p_formel(h, d):
    try:
        return h._send(200, {"ok": True, "wert": m41_formel(d.get("formel") or "")})
    except M41FormelFehler as e:
        return h._send(200, {"ok": False, "error": str(e), "quiet": True})


def _m41_p_aufmass_doc(h, d):
    return h._send(200, m41_aufmass_to_doc(int(d["project_id"]), d.get("ids") or [], d.get("typ") or "angebot"))


def _m41_g_kalk(h, qs):
    if qs.get("id"):
        k = _m41_kalk_load(int(qs["id"]))
        k["result"] = m41_kalk_calc(k["data"])
        return h._send(200, k)
    s = get_settings()
    return h._send(200, {"list": m41_kalk_list(int(qs["project_id"])), "default": M41_KALK_DEFAULT,
                         "preise": s.get("materialpreise") or {}, "stundensatz": s.get("stundensatz") or 0,
                         "aufschlag": s.get("aufschlag") or 0,
                         "boms": q("SELECT id, name, path, folder FROM project_files WHERE project_id=? AND (kind='Stückliste' OR "
                                   "lower(name) LIKE '%.csv' OR lower(name) LIKE '%.xlsx') ORDER BY added DESC", (int(qs["project_id"]),))})


def _m41_p_kalk_save(h, d):
    kid, res = m41_kalk_save(d)
    return h._send(200, {"ok": True, "id": kid, "result": res})


def _m41_p_kalk_calc(h, d):
    data = dict(M41_KALK_DEFAULT, **(d.get("data") or {}))
    for k in ("stundensatz", "mat_zuschlag", "gk", "gewinn", "fremd"):
        data[k] = _m41_fnum(data.get(k))
    return h._send(200, {"ok": True, "result": m41_kalk_calc(data)})


def _m41_p_kalk_del(h, d):
    x("DELETE FROM m41_kalk WHERE id=?", (int(d["id"]),))
    return h._send(200, {"ok": True})


def _m41_p_kalk_angebot(h, d):
    return h._send(200, m41_kalk_to_angebot(int(d["id"]), d.get("mode") or "pauschal"))


def _m41_p_kalk_pdf(h, d):
    return h._send(200, {"ok": True, "path": m41_kalk_pdf(int(d["id"]))})


def _m41_p_bom_file(h, d):
    f = q("SELECT * FROM project_files WHERE id=?", (int(d["file_id"]),), one=True)
    if not f:
        raise ValueError("Datei nicht gefunden.")
    fp = os.path.join(DATA_DIR, f["path"])
    if not os.path.isfile(fp):
        raise ValueError("Datei fehlt im Projektordner.")
    return h._send(200, {"ok": True, "rows": parse_bom(fp), "preise": get_settings().get("materialpreise") or {}})


HOOK_GET["/api/m41/aufmass"] = _m41_g_aufmass
HOOK_POST["/api/m41/aufmass/save"] = _m41_p_aufmass_save
HOOK_POST["/api/m41/aufmass/delete"] = _m41_p_aufmass_del
HOOK_POST["/api/m41/formel"] = _m41_p_formel
HOOK_POST["/api/m41/aufmass/to_doc"] = _m41_p_aufmass_doc
HOOK_GET["/api/m41/kalk"] = _m41_g_kalk
HOOK_POST["/api/m41/kalk/save"] = _m41_p_kalk_save
HOOK_POST["/api/m41/kalk/calc"] = _m41_p_kalk_calc
HOOK_POST["/api/m41/kalk/delete"] = _m41_p_kalk_del
HOOK_POST["/api/m41/kalk/angebot"] = _m41_p_kalk_angebot
HOOK_POST["/api/m41/kalk/pdf"] = _m41_p_kalk_pdf
HOOK_POST["/api/m41/bom_file"] = _m41_p_bom_file


def _m41_ex_aufmass(p):
    if not str(p.get("id") or "").isdigit():
        raise ValueError("Bitte zuerst ein Projekt öffnen.")
    pid = int(p["id"])
    pr = q("SELECT nr, name FROM projects WHERE id=?", (pid,), one=True) or {"nr": "", "name": ""}
    rows = m41_aufmass_list(pid)
    return [_sh(f"Aufmaß {pr['nr']}", [("Pos.", "t", 8), ("Beschreibung", "t", 34), ("Formel / Maße", "t", 30), ("Ergebnis", "n", 10),
                                       ("Einheit", "t", 7), ("Einzelpreis", "m", 12), ("Gesamt", "m", 13)],
                [[r["pos"] or "", r["beschreibung"] or "", _m41_fmt_formel(r), r["ergebnis"] or 0, M41_EINHEIT_DE.get(r["einheit"], r["einheit"]),
                  r["preis"] or 0, round((r["ergebnis"] or 0) * (r["preis"] or 0), 2)] for r in rows], f"{pr['nr']} {pr['name']}")]


EXPORTS["m41_aufmass"] = ("Aufmass", _m41_ex_aufmass)


def _m41_selftest():
    err = []
    tests = [("2*3,5+1,2", 8.2), ("(2+3) x 4", 20.0), ("-1,5*2", -3.0), ("1.234,5+0,5", 1235.0), ("2^3", 8.0), ("10:4", 2.5)]
    for f, exp in tests:
        try:
            v = m41_formel(f)
            if abs(v - exp) > 1e-9:
                err.append(f"m41: Formel {f} = {v}, erwartet {exp}")
        except Exception as e:
            err.append(f"m41: Formel {f} Fehler {e}")
    for bad in ("__import__('os')", "2**", "1/0", "(1+2", "abc", ""):
        try:
            m41_formel(bad)
            err.append(f"m41: unsichere/falsche Formel {bad!r} wurde akzeptiert")
        except M41FormelFehler:
            pass
    if m41_ergebnis({"modus": "lbh", "l": 2.5, "b": 1.2, "h": None, "anz": 3}) != 9.0:
        err.append("m41: L x B x Anzahl falsch")
    data = {"rows": [{"qty": 10, "masse_kg": 50, "material": "S235"}, {"qty": 4, "ek_stk": 25}],
            "arbeit": [{"std": 10}], "stundensatz": 60, "mat_zuschlag": 10, "gk": 15, "gewinn": 10, "fremd": 0}
    r = m41_kalk_calc(data, preise={"S235": 1.8})
    # material = 10*50*1.8 + 4*25 = 900 + 100 = 1000; +10% = 100; lohn 600 -> herstell 1700; gk 255 -> 1955; gewinn 195,5 -> 2150,5
    if (r["material"], r["herstell"], r["selbstkosten"], r["angebotspreis"]) != (1000.0, 1700.0, 1955.0, 2150.5):
        err.append(f"m41: Kalkulation falsch: {r['material']}, {r['herstell']}, {r['selbstkosten']}, {r['angebotspreis']}")
    return err


HOOK_SELFTEST.append(_m41_selftest)
