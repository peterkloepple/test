# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m43_sollist
# Soll/Ist-Vergleich je Projekt (Kalkulation bzw. Angebot gegen erfasste Zeiten, Material, Rechnungen)
# und Auswertung ueber alle Projekte nach Bereich (Deckungsbeitrag, effektiver Stundenlohn).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M43_STD_UNITS = ("std", "h", "std.", "stunde", "stunden")
M43_STD_ART = ("Arbeitszeit", "Programmierung")


def _m43_r2(v):
    return round(float(v or 0) + 1e-9, 2)


def m43_ampel(ist, soll, gelb=10.0, rot=20.0):
    """cost-type traffic light: ist <= soll -> gruen; up to +gelb % -> gelb; above -> rot"""
    if not soll:
        return "grau"
    d = 100.0 * (ist - soll) / abs(soll)
    return "gruen" if d <= 0.0001 else ("gelb" if d <= gelb else "rot")


def _m43_dev(ist, soll):
    return {"soll": _m43_r2(soll), "ist": _m43_r2(ist), "diff": _m43_r2(ist - soll),
            "pct": round(100.0 * (ist - soll) / abs(soll), 1) if soll else None}


def _m43_is_hours(e):
    return (e.get("art") in M43_STD_ART) or ((e.get("unit") or "").strip().lower() in M43_STD_UNITS)


def m43_soll(pid):
    """target values: newest calculation, else accepted / newest offer, else project budget"""
    k = q("SELECT id, name, result, data, angebot_id FROM m41_kalk WHERE project_id=? ORDER BY updated DESC, id DESC LIMIT 1", (pid,), one=True)
    if k:
        r = m41_kalk_calc(json.loads(k["data"] or "{}"))
        return {"quelle": f"Kalkulation „{k['name']}“", "stunden": r["stunden"], "lohn": r["lohn"],
                "material": _m43_r2(r["material"] + r["fremd"]), "summe": r["angebotspreis"],
                "selbstkosten": r["selbstkosten"], "stundensatz": r["stundensatz"]}
    a = q("SELECT id, nr, COALESCE(netto, summe) summe FROM invoices WHERE project_id=? AND typ IN ('angebot','auftrag') AND status!='entwurf' "
          "ORDER BY CASE WHEN status IN ('angenommen','erledigt') OR typ='auftrag' THEN 0 ELSE 1 END, datum DESC, id DESC LIMIT 1",
          (pid,), one=True)
    if a:
        std = 0.0
        lohn = 0.0
        for it in q("SELECT i.qty, i.name, i.price, i.total, a.unit FROM items i LEFT JOIN articles a ON a.id=i.article_id "
                    "WHERE i.invoice_id=?", (a["id"],)):
            u = (it["unit"] or "").strip().lower()
            if u in M43_STD_UNITS or re.search(r"arbeitszeit|stunde|\bstd\b|montage|programmier", it["name"] or "", re.I):
                std += float(it["qty"] or 0)
                lohn += float(it["total"] or 0)
        s = float(a["summe"] or 0)
        return {"quelle": f"Angebot {a['nr']}", "stunden": round(std, 2), "lohn": _m43_r2(lohn),
                "material": None, "summe": _m43_r2(s), "selbstkosten": None, "stundensatz": None}
    p = q("SELECT budget FROM projects WHERE id=?", (pid,), one=True)
    if p and p["budget"]:
        return {"quelle": "Projekt-Budget", "stunden": None, "lohn": None, "material": None, "summe": _m43_r2(p["budget"]),
                "selbstkosten": None, "stundensatz": None}
    return None


def m43_ist(pid):
    ents = q("SELECT * FROM project_entries WHERE project_id=?", (pid,))
    std = sum(float(e["qty"] or 0) for e in ents if _m43_is_hours(e))
    std_wert = sum(float(e["qty"] or 0) * float(e["price"] or 0) for e in ents if _m43_is_hours(e))
    mat_vk = sum(float(e["qty"] or 0) * float(e["price"] or 0) for e in ents if e["art"] == "Material")
    leist = sum(float(e["qty"] or 0) * float(e["price"] or 0) for e in ents)
    offen = sum(float(e["qty"] or 0) * float(e["price"] or 0) for e in ents if not e["invoice_id"])
    # v2.1.0: net values - with Regelbesteuerung the VAT of the invoices is owed to the tax office and the input VAT
    # of the receipts comes back (m80: invoices.netto, belege.details.vorsteuer); for Kleinunternehmer netto = summe
    beleg = 0.0
    for b in q("SELECT betrag, details FROM belege WHERE project_id=? AND typ='ausgabe'", (pid,)):
        vst = 0.0
        try:
            vst = float((json.loads(b["details"] or "{}") or {}).get("vorsteuer") or 0)
        except Exception:
            vst = 0.0
        beleg += float(b["betrag"] or 0) - vst
    try:
        m42_sync()
        lager = m42_project_material(pid)["ek_summe"]
    except Exception:
        lager = 0.0
    inv = q(f"SELECT COALESCE(SUM(COALESCE(netto, summe)),0) s FROM invoices WHERE project_id=? AND {COUNT_SQL}", (pid,), one=True)["s"]
    paid = q(f"SELECT COALESCE(SUM(COALESCE(netto, summe)),0) s FROM invoices WHERE project_id=? AND {COUNT_SQL} AND status='bezahlt'",
             (pid,), one=True)["s"]
    fahrt_km = q("SELECT COALESCE(SUM(km),0) s FROM fahrten WHERE project_id=?", (pid,), one=True)["s"]
    return {"stunden": round(std, 2), "stunden_wert": _m43_r2(std_wert), "material_vk": _m43_r2(mat_vk),
            "material_kosten": _m43_r2(float(beleg or 0) + float(lager or 0)), "material_belege": _m43_r2(beleg),
            "material_lager": _m43_r2(lager), "leistungen": _m43_r2(leist), "offen": _m43_r2(offen),
            "abgerechnet": _m43_r2(inv), "bezahlt": _m43_r2(paid), "fahrt_km": round(float(fahrt_km or 0), 1)}


def m43_project(pid):
    p = q("SELECT id, nr, name, bereich, status, budget FROM projects WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("Projekt nicht gefunden.")
    soll = m43_soll(pid)
    ist = m43_ist(pid)
    erloes = ist["abgerechnet"]
    db = _m43_r2(erloes - ist["material_kosten"])
    out = {"project": p, "soll": soll, "ist": ist, "zeilen": [], "ampel": "grau",
           "db": db, "stundenlohn": _m43_r2(db / ist["stunden"]) if ist["stunden"] else None}
    if soll:
        z = []
        if soll.get("stunden"):
            z.append(dict(_m43_dev(ist["stunden"], soll["stunden"]), key="stunden", label="Stunden", unit="Std",
                          ampel=m43_ampel(ist["stunden"], soll["stunden"])))
        if soll.get("material"):
            z.append(dict(_m43_dev(ist["material_kosten"], soll["material"]), key="material", label="Material + Fremdleistung (EK)",
                          unit="EUR", ampel=m43_ampel(ist["material_kosten"], soll["material"])))
        if soll.get("summe"):
            gesamt = ist["abgerechnet"] + ist["offen"]
            # revenue line: more than planned is fine, less is a warning only once the project is done
            dv = _m43_dev(gesamt, soll["summe"])
            am = "gruen" if gesamt >= soll["summe"] - 0.005 else ("gelb" if p["status"] != "abgeschlossen" else "rot")
            z.append(dict(dv, key="summe", label="Leistung (abgerechnet + offen)", unit="EUR", ampel=am))
            z.append(dict(_m43_dev(ist["abgerechnet"], soll["summe"]), key="abgerechnet", label="davon abgerechnet", unit="EUR",
                          ampel="grau"))
        out["zeilen"] = z
        order = {"rot": 3, "gelb": 2, "gruen": 1, "grau": 0}
        out["ampel"] = max((r["ampel"] for r in z), key=lambda a: order[a], default="grau")
    return out


def m43_auswertung(year=None, status=""):
    sql = "SELECT id, nr, name, bereich, status, start FROM projects"
    args = []
    cond = []
    if year:
        cond.append("substr(COALESCE(start,''),1,4)=?")
        args.append(str(year))
    if status:
        cond.append("status=?")
        args.append(status)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    rows = []
    grp = {}
    for p in q(sql + " ORDER BY bereich, start DESC", tuple(args)):
        r = m43_project(p["id"])
        ist = r["ist"]
        row = {"id": p["id"], "nr": p["nr"], "name": p["name"], "bereich": p["bereich"] or "Sonstiges", "status": p["status"],
               "erloes": ist["abgerechnet"], "offen": ist["offen"], "material": ist["material_kosten"], "db": r["db"],
               "stunden": ist["stunden"], "stundenlohn": r["stundenlohn"], "ampel": r["ampel"],
               "soll": (r["soll"] or {}).get("summe")}
        rows.append(row)
        g = grp.setdefault(row["bereich"], {"bereich": row["bereich"], "projekte": 0, "erloes": 0.0, "material": 0.0, "db": 0.0,
                                            "stunden": 0.0, "offen": 0.0})
        g["projekte"] += 1
        for k in ("erloes", "material", "db", "stunden", "offen"):
            g[k] += row[k] or 0
    bereiche = []
    for g in sorted(grp.values(), key=lambda g: -g["db"]):
        g = {k: (_m43_r2(v) if isinstance(v, float) else v) for k, v in g.items()}
        g["stundenlohn"] = _m43_r2(g["db"] / g["stunden"]) if g["stunden"] else None
        g["db_quote"] = round(100.0 * g["db"] / g["erloes"], 1) if g["erloes"] else None
        bereiche.append(g)
    tot = {k: _m43_r2(sum(g[k] for g in bereiche)) for k in ("erloes", "material", "db", "stunden", "offen")}
    tot["stundenlohn"] = _m43_r2(tot["db"] / tot["stunden"]) if tot["stunden"] else None
    return {"rows": rows, "bereiche": bereiche, "gesamt": tot}


def _m43_g_project(h, qs):
    return h._send(200, m43_project(int(qs["project_id"])))


def _m43_g_all(h, qs):
    y = qs.get("year") or ""
    return h._send(200, m43_auswertung(int(y) if y.isdigit() else None, qs.get("status") or ""))


HOOK_GET["/api/m43/project"] = _m43_g_project
HOOK_GET["/api/m43/auswertung"] = _m43_g_all


def _m43_ex(p):
    y = str(p.get("year") or "")
    a = m43_auswertung(int(y) if y.isdigit() else None, p.get("status") or "")
    lab = f"Projekte {y}" if y else "alle Projekte"
    return [_sh("Auswertung nach Bereich", [("Bereich", "t", 18), ("Projekte", "n", 9), ("Erlös", "m", 13), ("Materialkosten", "m", 14),
                                            ("Deckungsbeitrag", "m", 15), ("DB-Quote %", "p", 10), ("Stunden", "n", 10),
                                            ("Std-Lohn eff.", "m", 13), ("noch offen", "m", 13)],
                [[g["bereich"], g["projekte"], g["erloes"], g["material"], g["db"], g["db_quote"] or 0, g["stunden"],
                  g["stundenlohn"] or 0, g["offen"]] for g in a["bereiche"]], f"Deckungsbeitrag = Erlös - Material (Belege + Lager-EK) · {lab}"),
            _sh("Projekte Soll/Ist", [("Nr.", "t", 11), ("Projekt", "t", 30), ("Bereich", "t", 13), ("Status", "t", 12), ("Soll", "m", 13),
                                      ("Erlös", "m", 13), ("offen", "m", 12), ("Material", "m", 12), ("DB", "m", 13), ("Stunden", "n", 9),
                                      ("Std-Lohn eff.", "m", 12), ("Ampel", "t", 8)],
                [[r["nr"] or "", r["name"] or "", r["bereich"], r["status"] or "", r["soll"] or 0, r["erloes"], r["offen"], r["material"],
                  r["db"], r["stunden"], r["stundenlohn"] or 0, {"gruen": "grün", "gelb": "gelb", "rot": "rot"}.get(r["ampel"], "-")]
                 for r in a["rows"]], lab)]


EXPORTS["m43_sollist"] = ("Soll_Ist", _m43_ex)


def _m43_selftest():
    err = []
    if m43_ampel(100, 100) != "gruen" or m43_ampel(105, 100) != "gelb" or m43_ampel(130, 100) != "rot" or m43_ampel(5, 0) != "grau":
        err.append("m43: Ampel-Logik falsch")
    d = _m43_dev(110, 100)
    if d["diff"] != 10.0 or d["pct"] != 10.0:
        err.append(f"m43: Abweichung falsch: {d}")
    try:
        m43_auswertung()
    except Exception as e:
        err.append(f"m43: Auswertung Fehler {e}")
    return err


HOOK_SELFTEST.append(_m43_selftest)
