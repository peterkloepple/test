# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m76_en1090 (v2.0.19)
# EN-1090-/Schweiss-Dokumentation je Projekt (Metallbau / Schweissen):
#  - Ausfuehrungsklasse EXC1-4, Bauprodukt, Verwendungszweck, DoP-Nummer, erklaerte Leistungen
#  - Bauteile/Positionen mit WPS, Schweissern, Naht und Pruefumfang
#  - WPS/WPQR-Bibliothek (projektuebergreifend) mit Verfahren, Werkstoffgruppe, Dicke, Position, Gueltigkeit
#  - Schweisser = Nachweise (zertifikate) - Warnung bei abgelaufener Pruefung / faelliger Bestaetigung
#  - Werkstoffzeugnisse 3.1 nach EN 10204 je Charge, Zusatzwerkstoffe, Pruefungen (VT/MT/PT/UT/RT)
#  - Leistungserklaerung (DoP) und CE-Kennzeichnung als PDF (Angaben nach EN 1090-1 Anhang ZA)
#  - Uebergabepaket als ZIP und als ein zusammengefuehrtes PDF mit Deckblatt und Inhaltsverzeichnis
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M76_VERSION = "1.0.0"
M76_EXC = ["EXC1", "EXC2", "EXC3", "EXC4"]
M76_VERFAHREN = {"111": "Lichtbogenhandschweissen (E)", "114": "Fuelldrahtschweissen ohne Schutzgas", "121": "UP-Schweissen",
                 "131": "MIG-Schweissen", "135": "MAG-Schweissen (Massivdraht)", "136": "MAG-Schweissen (Fuelldraht)",
                 "138": "MAG-Schweissen (Metallpulver-Fuelldraht)", "141": "WIG-Schweissen", "15": "Plasmaschweissen",
                 "311": "Gasschweissen", "783": "Bolzenschweissen mit Hubzuendung"}
M76_ARTEN = ("pos", "zeugnis", "zusatz", "pruefung")
M76_ART_DE = {"pos": "Bauteil / Position", "zeugnis": "Werkstoffzeugnis", "zusatz": "Zusatzwerkstoff", "pruefung": "Prüfung"}
M76_DIR = "EN 1090"
M76_MERKMALE = [
    ("toleranz", "Maßtoleranzen", "EN 1090-2"),
    ("schweisseignung", "Schweißeignung", "S235JR / S355J2 nach EN 10025-2"),
    ("bruchzaehigkeit", "Bruchzähigkeit", "27 J bei 0 °C bzw. -20 °C (je nach Werkstoff)"),
    ("tragfaehigkeit", "Tragfähigkeit", "siehe Bauteilspezifikation / Statik"),
    ("ermuedung", "Ermüdungsfestigkeit", "NPD"),
    ("feuerwiderstand", "Feuerwiderstand", "NPD"),
    ("brandverhalten", "Brandverhalten", "Klasse A1"),
    ("cadmium", "Freisetzung von Cadmium", "NPD"),
    ("radioaktiv", "Freisetzung von Radioaktivität", "NPD"),
    ("dauerhaftigkeit", "Dauerhaftigkeit", "siehe Korrosionsschutz nach EN ISO 12944"),
    ("herstellung", "Herstellung", "nach Bauteilspezifikation, EN 1090-2, Ausführungsklasse [EXC]"),
]
M76_DEF_SET = {"hersteller": "", "anschrift": "", "wpk_nr": "", "stelle_name": "", "stelle_nr": "", "aufsicht": "",
               "ort": "", "avcp": "2+", "norm": "EN 1090-1:2009+A1:2011", "ausf_norm": "EN 1090-2"}


def _m76_schema():
    x("CREATE TABLE IF NOT EXISTS m76_proj (project_id INTEGER PRIMARY KEY, aktiv INTEGER DEFAULT 1, exc TEXT, produkt TEXT, "
      "verwendung TEXT, dop_nr TEXT, ce_jahr TEXT, merkmale TEXT, notiz TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m76_wps (id INTEGER PRIMARY KEY, art TEXT, nr TEXT, verfahren TEXT, werkstoff TEXT, dicke TEXT, "
      "position TEXT, zusatz TEXT, norm TEXT, gueltig_bis TEXT, file TEXT, notiz TEXT, aktiv INTEGER DEFAULT 1, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS m76_eintrag (id INTEGER PRIMARY KEY, project_id INTEGER, art TEXT, data TEXT, file TEXT, "
      "sort INTEGER DEFAULT 0, created TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m76_link (project_id INTEGER, art TEXT, ref_id INTEGER, PRIMARY KEY (project_id, art, ref_id))")
    try:
        x("CREATE INDEX IF NOT EXISTS m76_e_p ON m76_eintrag(project_id)")
    except Exception:
        pass


HOOK_SCHEMA.append(_m76_schema)


def _m76_e(t):
    return (str(t if t is not None else "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def m76_settings():
    s = get_settings()
    m = dict(M76_DEF_SET, **(s.get("m76") or {}))
    if not m["hersteller"]:
        m["hersteller"] = s.get("firma") or ""
    if not m["anschrift"]:
        m["anschrift"] = (s.get("absender") or "").split(",", 1)[-1].strip() if s.get("absender") else ""
    if not m["aufsicht"]:
        m["aufsicht"] = s.get("inhaber") or ""
    return m


def _m76_zert_state(z, t=None):
    """status of a welder certificate: ok / bald / abgelaufen (+ text)"""
    t = t or datetime.date.today()
    gb = d_iso(z.get("gueltig_bis"))
    st, txt = "ok", ""
    if gb:
        if gb < t:
            st, txt = "abgelaufen", f"abgelaufen am {de_date(gb.isoformat())}"
        elif gb <= t + datetime.timedelta(days=60):
            st, txt = "bald", f"läuft ab am {de_date(gb.isoformat())}"
    if z.get("bestaetigung_monate"):
        base = d_iso(z.get("bestaetigt_am")) or d_iso(z.get("ausgestellt"))
        if base:
            nb = add_months(base, int(z["bestaetigung_monate"]))
            if nb < t and st != "abgelaufen":
                st, txt = "abgelaufen", f"Bestätigung (alle {z['bestaetigung_monate']} Monate) fehlt seit {de_date(nb.isoformat())}"
            elif nb <= t + datetime.timedelta(days=30) and st == "ok":
                st, txt = "bald", f"Bestätigung fällig am {de_date(nb.isoformat())}"
    return st, txt


def _m76_wps_state(w, t=None):
    t = t or datetime.date.today()
    gb = d_iso(w.get("gueltig_bis"))
    if gb and gb < t:
        return "abgelaufen"
    if gb and gb <= t + datetime.timedelta(days=60):
        return "bald"
    return "ok"


def _m76_proj_row(pid):
    p = q("SELECT * FROM m76_proj WHERE project_id=?", (pid,), one=True)
    if not p:
        return {"project_id": pid, "aktiv": 0, "exc": "EXC2", "produkt": "", "verwendung": "", "dop_nr": "", "ce_jahr": "",
                "merkmale": {}, "notiz": "", "neu": True}
    p["merkmale"] = json.loads(p["merkmale"] or "{}")
    return p


def m76_get(pid):
    pid = int(pid)
    pr = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not pr:
        raise ValueError("Projekt nicht gefunden.")
    d = _m76_proj_row(pid)
    if not d.get("dop_nr"):
        d["dop_vorschlag"] = f"DoP-{pr['nr']}"
    ent = q("SELECT * FROM m76_eintrag WHERE project_id=? ORDER BY art, sort, id", (pid,))
    for e in ent:
        e["data"] = json.loads(e["data"] or "{}")
    t = datetime.date.today()
    wps_ids = {r["ref_id"] for r in q("SELECT ref_id FROM m76_link WHERE project_id=? AND art='wps'", (pid,))}
    sw_ids = {r["ref_id"] for r in q("SELECT ref_id FROM m76_link WHERE project_id=? AND art='schweisser'", (pid,))}
    for e in ent:
        if e["art"] == "pos":
            if e["data"].get("wps_id"):
                wps_ids.add(int(e["data"]["wps_id"]))
            for s_ in e["data"].get("schweisser") or []:
                if str(s_).isdigit():
                    sw_ids.add(int(s_))
    wps = [w for w in q("SELECT * FROM m76_wps ORDER BY art DESC, nr") if w["id"] in wps_ids]
    for w in wps:
        w["state"] = _m76_wps_state(w, t)
    sw = q(f"SELECT * FROM zertifikate WHERE id IN ({','.join(str(i) for i in sw_ids) or '0'}) ORDER BY person, gueltig_bis")
    for z in sw:
        z["state"], z["state_txt"] = _m76_zert_state(z, t)
    grouped = {a: [e for e in ent if e["art"] == a] for a in M76_ARTEN}
    d["eintraege"] = grouped
    d["wps"] = wps
    d["schweisser"] = sw
    d["warnungen"] = m76_warnungen(d, pr)
    d["projekt"] = {"id": pr["id"], "nr": pr["nr"], "name": pr["name"], "bereich": pr["bereich"]}
    d["dateien"] = q("SELECT id, name, path FROM project_files WHERE project_id=? AND folder LIKE ? ORDER BY name", (pid, M76_DIR + "%"))
    return d


def m76_warnungen(d, pr=None):
    w = []
    st = m76_settings()
    exc = d.get("exc") or "EXC2"
    for z in d.get("schweisser") or []:
        if z["state"] == "abgelaufen":
            w.append({"stufe": "fehler", "text": f"Schweißer {z['person'] or z['bezeichnung']}: {z['state_txt']}"})
        elif z["state"] == "bald":
            w.append({"stufe": "warnung", "text": f"Schweißer {z['person'] or z['bezeichnung']}: {z['state_txt']}"})
    for x_ in d.get("wps") or []:
        if x_["state"] == "abgelaufen":
            w.append({"stufe": "fehler", "text": f"{x_['art']} {x_['nr']} ist nicht mehr gültig."})
    e = d.get("eintraege") or {}
    if not e.get("pos"):
        w.append({"stufe": "hinweis", "text": "Noch keine Bauteile/Positionen erfasst."})
    if exc != "EXC1" and not d.get("wps"):
        w.append({"stufe": "warnung", "text": f"{exc}: Schweißarbeiten brauchen eine WPS - noch keine zugeordnet."})
    if not d.get("schweisser"):
        w.append({"stufe": "warnung", "text": "Noch kein Schweißer (Prüfungsbescheinigung ISO 9606-1) zugeordnet."})
    if exc in ("EXC2", "EXC3", "EXC4") and not e.get("zeugnis"):
        w.append({"stufe": "warnung", "text": f"{exc}: Werkstoffzeugnisse 3.1 nach EN 10204 fehlen."})
    if not any((p_.get("data") or {}).get("art") == "VT" for p_ in e.get("pruefung") or []):
        w.append({"stufe": "hinweis", "text": "Sichtprüfung (VT, 100 %) ist noch nicht dokumentiert."})
    if any((p_.get("data") or {}).get("ergebnis") == "n.i.O." for p_ in e.get("pruefung") or []):
        w.append({"stufe": "fehler", "text": "Es gibt Prüfungen mit Ergebnis n.i.O. - Nacharbeit dokumentieren."})
    if not st.get("wpk_nr") or not st.get("stelle_nr"):
        w.append({"stufe": "hinweis", "text": "Für DoP/CE fehlen WPK-Zertifikatsnummer bzw. Nr. der notifizierten Stelle (Einstellungen > EN 1090 & Abnahme)."})
    sw_ids = {z["id"] for z in d.get("schweisser") or []}
    for p_ in e.get("pos") or []:
        for s_ in p_["data"].get("schweisser") or []:
            if str(s_).isdigit() and int(s_) not in sw_ids:
                w.append({"stufe": "warnung", "text": f"Position {p_['data'].get('pos', '')}: Schweißer-Nachweis nicht gefunden."})
    return w


def m76_overview():
    rows = q("SELECT p.id, p.nr, p.name, p.bereich, p.status, m.aktiv, m.exc, m.dop_nr FROM projects p "
             "LEFT JOIN m76_proj m ON m.project_id=p.id "
             "WHERE m.aktiv=1 OR (m.project_id IS NULL AND (p.bereich LIKE 'Metall%' OR p.bereich LIKE 'Schwei%')) "
             "ORDER BY p.status, p.start DESC")
    out = []
    for r in rows:
        try:
            d = m76_get(r["id"])
        except Exception:
            continue
        n = {a: len(d["eintraege"][a]) for a in M76_ARTEN}
        out.append({"id": r["id"], "nr": r["nr"], "name": r["name"], "bereich": r["bereich"], "status": r["status"],
                    "aktiv": bool(r["aktiv"]), "exc": r["exc"] or "", "dop_nr": r["dop_nr"] or "", "anzahl": n,
                    "schweisser": len(d["schweisser"]), "wps": len(d["wps"]),
                    "fehler": sum(1 for w in d["warnungen"] if w["stufe"] == "fehler"),
                    "warnungen": sum(1 for w in d["warnungen"] if w["stufe"] == "warnung"), "hinweise": d["warnungen"][:6]})
    return {"projekte": out, "wps": m76_wps_list(), "settings": m76_settings(), "verfahren": M76_VERFAHREN,
            "schweisser_alle": m76_welders()}


def m76_welders():
    rows = q("SELECT * FROM zertifikate WHERE aktiv=1 ORDER BY person, gueltig_bis")
    out = []
    for z in rows:
        txt = f"{z['typ'] or ''} {z['bezeichnung'] or ''} {z['norm'] or ''}".lower()
        if re.search(r"9606|schwei|welder|287", txt):
            z["state"], z["state_txt"] = _m76_zert_state(z)
            out.append(z)
    return out


def m76_wps_list():
    rows = q("SELECT * FROM m76_wps ORDER BY aktiv DESC, art DESC, nr")
    for r in rows:
        r["state"] = _m76_wps_state(r)
        r["n_proj"] = q("SELECT COUNT(*) n FROM m76_link WHERE art='wps' AND ref_id=?", (r["id"],), one=True)["n"]
    return rows


def m76_save_proj(d):
    pid = int(d["project_id"])
    mk = d.get("merkmale") or {}
    vals = (1 if d.get("aktiv", 1) not in (0, False, "0") else 0, (d.get("exc") or "EXC2") if (d.get("exc") or "EXC2") in M76_EXC else "EXC2",
            (d.get("produkt") or "").strip()[:300], (d.get("verwendung") or "").strip()[:500], (d.get("dop_nr") or "").strip()[:80],
            (d.get("ce_jahr") or "").strip()[:4], json.dumps({k: str(v)[:300] for k, v in mk.items()}, ensure_ascii=False),
            (d.get("notiz") or "")[:2000], now_iso())
    if q("SELECT project_id FROM m76_proj WHERE project_id=?", (pid,), one=True):
        x("UPDATE m76_proj SET aktiv=?, exc=?, produkt=?, verwendung=?, dop_nr=?, ce_jahr=?, merkmale=?, notiz=?, updated=? WHERE project_id=?",
          vals + (pid,))
    else:
        x("INSERT INTO m76_proj (aktiv, exc, produkt, verwendung, dop_nr, ce_jahr, merkmale, notiz, updated, project_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
          vals + (pid,))
    return {"ok": True}


def _m76_ensure(pid):
    if not q("SELECT project_id FROM m76_proj WHERE project_id=?", (pid,), one=True):
        x("INSERT INTO m76_proj (project_id, aktiv, exc, merkmale, updated) VALUES (?,1,'EXC2','{}',?)", (pid, now_iso()))


def m76_save_entry(d):
    art = d.get("art")
    if art not in M76_ARTEN:
        raise ValueError("Unbekannte Art.")
    pid = int(d["project_id"])
    _m76_ensure(pid)
    data = {k: (v if isinstance(v, (list, int, float)) else str(v or "")[:500]) for k, v in (d.get("data") or {}).items()}
    if art == "pos" and not (data.get("bezeichnung") or data.get("pos")):
        raise ValueError("Bitte Position oder Bezeichnung eintragen.")
    if art == "zeugnis" and not (data.get("werkstoff") or data.get("charge")):
        raise ValueError("Bitte Werkstoff oder Charge eintragen.")
    if d.get("id"):
        x("UPDATE m76_eintrag SET data=?, updated=? WHERE id=? AND project_id=?", (json.dumps(data, ensure_ascii=False), now_iso(), int(d["id"]), pid))
        return {"ok": True, "id": int(d["id"])}
    n = q("SELECT COALESCE(MAX(sort),0)+1 n FROM m76_eintrag WHERE project_id=? AND art=?", (pid, art), one=True)["n"]
    eid = x("INSERT INTO m76_eintrag (project_id, art, data, file, sort, created, updated) VALUES (?,?,?,?,?,?,?)",
            (pid, art, json.dumps(data, ensure_ascii=False), "", n, now_iso(), now_iso()))
    return {"ok": True, "id": eid}


def _m76_drop_file(rel):
    """remove an attachment (file + project file entry) if nothing else in m76 points to it"""
    if not rel:
        return
    if q("SELECT id FROM m76_eintrag WHERE file=? LIMIT 1", (rel,), one=True) or q("SELECT id FROM m76_wps WHERE file=? LIMIT 1", (rel,), one=True):
        return
    x("DELETE FROM project_files WHERE path=?", (rel,))
    try:
        fp = rel if os.path.isabs(rel) else os.path.join(DATA_DIR, rel)
        if os.path.isfile(fp):
            os.remove(fp)
    except OSError:
        pass


def m76_delete_entry(ids):
    n = 0
    for i in ids or []:
        e = q("SELECT file FROM m76_eintrag WHERE id=?", (int(i),), one=True)
        x("DELETE FROM m76_eintrag WHERE id=?", (int(i),))
        if e:
            _m76_drop_file(e["file"])
        n += 1
    return {"ok": True, "n": n}


def m76_link(d):
    pid, art, rid = int(d["project_id"]), d.get("art"), int(d["ref_id"])
    if art not in ("wps", "schweisser"):
        raise ValueError("Unbekannte Verknüpfung.")
    _m76_ensure(pid)
    if d.get("weg"):
        x("DELETE FROM m76_link WHERE project_id=? AND art=? AND ref_id=?", (pid, art, rid))
    else:
        x("INSERT OR IGNORE INTO m76_link (project_id, art, ref_id) VALUES (?,?,?)", (pid, art, rid))
    return {"ok": True}


def m76_save_wps(d):
    nr = (d.get("nr") or "").strip()
    if not nr:
        raise ValueError("Bitte die WPS-/WPQR-Nummer eintragen.")
    art = "WPQR" if (d.get("art") or "").upper() == "WPQR" else "WPS"
    vals = (art, nr, (d.get("verfahren") or "").strip(), (d.get("werkstoff") or "").strip(), (d.get("dicke") or "").strip(),
            (d.get("position") or "").strip(), (d.get("zusatz") or "").strip(), (d.get("norm") or "").strip(),
            (d.get("gueltig_bis") or "")[:10], d.get("notiz") or "", 0 if d.get("aktiv") in (0, False, "0") else 1)
    if d.get("id"):
        x("UPDATE m76_wps SET art=?, nr=?, verfahren=?, werkstoff=?, dicke=?, position=?, zusatz=?, norm=?, gueltig_bis=?, notiz=?, aktiv=? WHERE id=?",
          vals + (int(d["id"]),))
        wid = int(d["id"])
    else:
        wid = x("INSERT INTO m76_wps (art, nr, verfahren, werkstoff, dicke, position, zusatz, norm, gueltig_bis, notiz, aktiv, file, created) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,'',?)", vals + (now_iso(),))
    if d.get("project_id"):
        m76_link({"project_id": d["project_id"], "art": "wps", "ref_id": wid})
    return {"ok": True, "id": wid}


def m76_delete_wps(ids):
    for i in ids or []:
        w = q("SELECT file FROM m76_wps WHERE id=?", (int(i),), one=True)
        x("DELETE FROM m76_wps WHERE id=?", (int(i),))
        x("DELETE FROM m76_link WHERE art='wps' AND ref_id=?", (int(i),))
        if w:
            _m76_drop_file(w["file"])
    return {"ok": True}


def _m76_store_project_file(pid, tmp, name, note):
    r = add_project_file(pid, tmp, name, M76_DIR)
    x("UPDATE project_files SET note=? WHERE id=?", (note[:200], r["id"]))
    f = q("SELECT * FROM project_files WHERE id=?", (r["id"],), one=True)
    return f["path"]


def _m76_upload(h, tmp, name):
    try:
        art = h.headers.get("X-M76-Art") or ""
        rid = int(h.headers.get("X-M76-Id") or 0)
        if art == "wps":
            d = os.path.join(DATA_DIR, M76_DIR, "WPS")
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, safe_name(name))
            root, ext = os.path.splitext(dst)
            k = 2
            while os.path.exists(dst):
                dst = f"{root} ({k}){ext}"
                k += 1
            old = q("SELECT file FROM m76_wps WHERE id=?", (rid,), one=True)
            if not old:
                raise ValueError("WPS nicht gefunden.")
            shutil.move(tmp, dst)
            x("UPDATE m76_wps SET file=? WHERE id=?", (os.path.relpath(dst, DATA_DIR), rid))
            _m76_drop_file(old["file"])     # replaced file
            return h._send(200, {"ok": True})
        e = q("SELECT * FROM m76_eintrag WHERE id=?", (rid,), one=True)
        if not e:
            raise ValueError("Eintrag nicht gefunden.")
        rel = _m76_store_project_file(e["project_id"], tmp, name, M76_ART_DE.get(e["art"], "EN 1090"))
        x("UPDATE m76_eintrag SET file=?, updated=? WHERE id=?", (rel, now_iso(), rid))
        _m76_drop_file(e["file"])       # replaced file
        return h._send(200, {"ok": True, "file": rel})
    except ValueError as ex:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return h._send(200, {"ok": False, "error": str(ex)})


HOOK_UPLOAD["/api/upload/m76"] = _m76_upload


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _m76_styles():
    from reportlab.lib.styles import ParagraphStyle
    ink, gray, acc = colors.HexColor("#1e1a2b"), colors.HexColor("#6c6880"), colors.HexColor("#3d6f8f")
    return {"N": ParagraphStyle("n", fontName=FONT_R(), fontSize=9, leading=12, textColor=ink),
            "NS": ParagraphStyle("ns", fontName=FONT_R(), fontSize=7.5, leading=9.5, textColor=gray),
            "K": ParagraphStyle("k", fontName=FONT_B(), fontSize=7.5, leading=9, textColor=acc),
            "H1": ParagraphStyle("h1", fontName=FONT_B(), fontSize=18, leading=22, textColor=ink, spaceAfter=2),
            "H2": ParagraphStyle("h2", fontName=FONT_B(), fontSize=11.5, leading=15, textColor=ink, spaceBefore=10, spaceAfter=5),
            "C": ParagraphStyle("c", fontName=FONT_R(), fontSize=8, leading=10, textColor=ink),
            "ink": ink, "gray": gray, "acc": acc, "soft": colors.HexColor("#eef3f6"), "line": colors.HexColor("#d9e2e8")}


def _m76_table(rows, widths, st):
    from reportlab.platypus import Table, TableStyle
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), FONT_B(), 7.5), ("TEXTCOLOR", (0, 0), (-1, 0), st["gray"]),
                           ("FONT", (0, 1), (-1, -1), FONT_R(), 8), ("LINEBELOW", (0, 0), (-1, 0), 0.6, st["ink"]),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, st["soft"]]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    return t


def _m76_doc(buf, title):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.units import mm
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=16 * mm,
                             title=title, author="T. Pfeiffer", creator=f"{APP_NAME} v{APP_VERSION}")


def _m76_onpage(label):
    from reportlab.lib.units import mm

    def f(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(colors.HexColor("#6c6880"))
        cv.drawString(18 * mm, 9 * mm, label)
        cv.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Seite {dc.page}")
    return f


def _m76_ctx(pid):
    d = m76_get(pid)
    p = get_project(pid)
    st = m76_settings()
    if not d.get("dop_nr"):
        d["dop_nr"] = d.get("dop_vorschlag") or f"DoP-{p['nr']}"
    if not d.get("ce_jahr"):
        d["ce_jahr"] = today()[:4]
    if not d.get("produkt"):
        d["produkt"] = f"Tragendes Stahlbauteil - {p['name']}"
    if not d.get("verwendung"):
        d["verwendung"] = "Tragendes Bauteil für Stahl- und Metallbaukonstruktionen in Gebäuden und Ingenieurbauwerken"
    return d, p, st


def _m76_merkmale(d):
    mk = d.get("merkmale") or {}
    out = []
    for k, lbl, dv in M76_MERKMALE:
        v = (mk.get(k) or dv).replace("[EXC]", d.get("exc") or "EXC2")
        out.append((lbl, v))
    return out


def m76_dop_bytes(pid):
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import mm
    d, p, s = _m76_ctx(pid)
    S_ = _m76_styles()
    e = _m76_e
    buf = io.BytesIO()
    doc = _m76_doc(buf, f"Leistungserklärung {d['dop_nr']}")
    el = [Paragraph("LEISTUNGSERKLÄRUNG", S_["K"]), Paragraph(f"Nr. {e(d['dop_nr'])}", S_["H1"]),
          Paragraph("nach Anhang III der Verordnung (EU) Nr. 305/2011 (Bauproduktenverordnung)", S_["NS"]), Spacer(1, 8)]
    rows = [["Nr.", "Angabe", ""],
            ["1", "Eindeutiger Kenncode des Produkttyps", Paragraph(e(f"{d['produkt']} ({p['nr']})"), S_["C"])],
            ["2", "Verwendungszweck", Paragraph(e(d["verwendung"]), S_["C"])],
            ["3", "Hersteller", Paragraph(e(s["hersteller"]) + "<br/>" + e(s["anschrift"]), S_["C"])],
            ["4", "Bevollmächtigter", "entfällt"],
            ["5", "System zur Bewertung und Überprüfung der Leistungsbeständigkeit", f"System {e(s['avcp'])}"],
            ["6", "Harmonisierte Norm", e(s["norm"])],
            ["", "Notifizierte Stelle", Paragraph(e(f"{s['stelle_name']} (Kenn-Nr. {s['stelle_nr'] or '-'})") + "<br/>" +
                                                  e(f"Zertifikat der werkseigenen Produktionskontrolle: {s['wpk_nr'] or '-'}"), S_["C"])],
            ["", "Ausführungsklasse", f"{e(d['exc'])} nach {e(s['ausf_norm'])}"]]
    el.append(_m76_table(rows, [10 * mm, 62 * mm, 102 * mm], S_))
    el += [Paragraph("7  Erklärte Leistung", S_["H2"])]
    mr = [["Wesentliches Merkmal", "Leistung", "Harmonisierte technische Spezifikation"]]
    for lbl, v in _m76_merkmale(d):
        mr.append([lbl, Paragraph(e(v), S_["C"]), "EN 1090-1"])
    el.append(_m76_table(mr, [52 * mm, 88 * mm, 34 * mm], S_))
    el += [Spacer(1, 10), Paragraph("Die Leistung des vorstehenden Produkts entspricht der erklärten Leistung. Für die Erstellung der "
                                    "Leistungserklärung ist allein der obengenannte Hersteller verantwortlich.", S_["N"]),
           Spacer(1, 22),
           Paragraph(f"Unterzeichnet für den Hersteller und im Namen des Herstellers von: {e(s['aufsicht'])}", S_["N"]),
           Spacer(1, 26),
           Paragraph(f"{e(s['ort'] or '')}{', ' if s['ort'] else ''}{de_date(today())} &nbsp; &nbsp; ______________________________", S_["N"]),
           Paragraph("Ort, Datum &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; Unterschrift / Schweißaufsicht", S_["NS"])]
    doc.build(el, onFirstPage=_m76_onpage(f"Leistungserklärung {d['dop_nr']} · {p['nr']} · T. Pfeiffer"),
              onLaterPages=_m76_onpage(f"Leistungserklärung {d['dop_nr']} · {p['nr']} · T. Pfeiffer"))
    return buf.getvalue()


def _m76_draw_ce(cv, x0, y0, h):
    """CE mark drawn from circle arcs (proportions after Annex II 765/2008, simplified)"""
    r = h / 2.0
    lw = h * 0.16
    cv.saveState()
    cv.setLineWidth(lw)
    cv.setLineCap(0)
    cv.setStrokeColor(colors.black)
    cx = x0 + r
    cy = y0 + r
    rr = r - lw / 2
    p = cv.beginPath()
    p.arc(cx - rr, cy - rr, cx + rr, cy + rr, startAng=55, extent=250)
    cv.drawPath(p, stroke=1, fill=0)
    cx2 = cx + h * 1.05
    p = cv.beginPath()
    p.arc(cx2 - rr, cy - rr, cx2 + rr, cy + rr, startAng=55, extent=250)
    cv.drawPath(p, stroke=1, fill=0)
    cv.setLineWidth(lw * 0.85)
    cv.line(cx2 - rr * 0.95, cy, cx2 + rr * 0.55, cy)
    cv.restoreState()


def m76_ce_bytes(pid):
    from reportlab.lib.units import mm
    d, p, s = _m76_ctx(pid)
    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=A4)
    cv.setTitle(f"CE-Kennzeichnung {p['nr']}")
    cv.setAuthor("T. Pfeiffer")
    W, H = A4
    left, top = 30 * mm, H - 30 * mm
    cv.setFont(FONT_B(), 8)
    cv.setFillColor(colors.HexColor("#3d6f8f"))
    cv.drawString(left, top + 6 * mm, "CE-KENNZEICHNUNG NACH EN 1090-1 ANHANG ZA.3")
    bw, bh = W - 2 * left, 150 * mm
    cv.setStrokeColor(colors.HexColor("#222222"))
    cv.setLineWidth(0.8)
    cv.rect(left, top - bh, bw, bh, stroke=1, fill=0)
    _m76_draw_ce(cv, left + bw / 2 - 22 * mm, top - 36 * mm, 26 * mm)
    lines = [(FONT_B(), 13, s["stelle_nr"] or "____"),
             (FONT_B(), 11, s["hersteller"]),
             (FONT_R(), 9.5, s["anschrift"]),
             (FONT_B(), 11, d["ce_jahr"][-2:]),
             (FONT_R(), 9.5, f"WPK-Zertifikat: {s['wpk_nr'] or '-'}"),
             (FONT_R(), 9.5, f"Leistungserklärung: {d['dop_nr']}"),
             (FONT_B(), 10.5, s["norm"]),
             (FONT_R(), 9.5, d["produkt"]),
             (FONT_R(), 9.5, f"Ausführungsklasse {d['exc']} nach {s['ausf_norm']}")]
    y = top - 46 * mm
    cv.setFillColor(colors.black)
    for fnt, sz, t in lines:
        for ln in simpleSplit(t or "", fnt, sz, bw - 20 * mm)[:2]:
            cv.setFont(fnt, sz)
            cv.drawCentredString(left + bw / 2, y, ln)
            y -= sz * 1.45
        y -= 1.5
    mk = _m76_merkmale(d)
    cv.setFont(FONT_R(), 7.5)
    for lbl, v in mk:
        if y < top - bh + 8 * mm:
            break
        cv.drawCentredString(left + bw / 2, y, f"{lbl}: {v}"[:110])
        y -= 10
    cv.setFont(FONT_R(), 7)
    cv.setFillColor(colors.HexColor("#6c6880"))
    cv.drawString(left, top - bh - 6 * mm, f"Projekt {p['nr']} {p['name']} · erstellt {de_date(today())} · T. Pfeiffer")
    cv.showPage()
    cv.save()
    return buf.getvalue()


def m76_doku_bytes(pid):
    """overview: positions, welders, WPS, certificates 3.1, consumables, inspections"""
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import mm
    d, p, s = _m76_ctx(pid)
    S_ = _m76_styles()
    e = _m76_e
    P = lambda t: Paragraph(e(t), S_["C"])
    buf = io.BytesIO()
    doc = _m76_doc(buf, f"Schweißdokumentation {p['nr']}")
    cust = (p.get("customer") or {})
    el = [Paragraph("SCHWEISS- UND HERSTELLUNGSDOKUMENTATION", S_["K"]), Paragraph(e(p["name"]), S_["H1"]),
          Paragraph(f"Projekt {e(p['nr'])} · Kunde: {e(cust.get('firma') or cust.get('name') or '-')} · {e(d['exc'])} nach {e(s['ausf_norm'])} · "
                    f"Stand {de_date(today())}", S_["NS"]), Spacer(1, 6)]
    E = d["eintraege"]
    wmap = {w["id"]: w for w in d["wps"]}
    zmap = {z["id"]: z for z in d["schweisser"]}
    if E["pos"]:
        rows = [["Pos.", "Bezeichnung", "Zeichnung", "Werkstoff", "WPS", "Schweißer", "Naht", "Prüfung"]]
        for r in E["pos"]:
            a = r["data"]
            w = wmap.get(int(a["wps_id"])) if str(a.get("wps_id") or "").isdigit() else None
            sw = ", ".join((zmap[int(i)]["person"] or zmap[int(i)]["nummer"] or "") for i in a.get("schweisser") or [] if str(i).isdigit() and int(i) in zmap)
            rows.append([P(a.get("pos")), P(a.get("bezeichnung")), P(a.get("zeichnung")), P(a.get("werkstoff")), P(w["nr"] if w else ""),
                         P(sw), P(a.get("naht")), P(a.get("pruefung"))])
        el += [Paragraph("Bauteile / Positionen", S_["H2"]), _m76_table(rows, [12 * mm, 38 * mm, 22 * mm, 20 * mm, 18 * mm, 26 * mm, 18 * mm, 20 * mm], S_)]
    if d["schweisser"]:
        rows = [["Schweißer", "Prüfungsbescheinigung", "Norm", "Nr.", "gültig bis", "Status"]]
        for z in d["schweisser"]:
            rows.append([P(z["person"]), P(z["bezeichnung"]), P(z["norm"]), P(z["nummer"]), de_date(z["gueltig_bis"] or ""),
                         P("gültig" if z["state"] == "ok" else z["state_txt"])])
        el += [Paragraph("Schweißer", S_["H2"]), _m76_table(rows, [30 * mm, 46 * mm, 26 * mm, 24 * mm, 18 * mm, 30 * mm], S_)]
    if d["wps"]:
        rows = [["Art", "Nr.", "Verfahren", "Werkstoff", "Dicke", "Position", "Zusatz", "gültig bis"]]
        for w in d["wps"]:
            rows.append([w["art"], P(w["nr"]), P(w["verfahren"]), P(w["werkstoff"]), P(w["dicke"]), P(w["position"]), P(w["zusatz"]),
                         de_date(w["gueltig_bis"] or "")])
        el += [Paragraph("Schweißanweisungen (WPS) / Verfahrensprüfungen (WPQR)", S_["H2"]),
               _m76_table(rows, [12 * mm, 24 * mm, 22 * mm, 26 * mm, 18 * mm, 22 * mm, 30 * mm, 20 * mm], S_)]
    if E["zeugnis"]:
        rows = [["Werkstoff", "Abmessung", "Charge / Schmelze", "Lieferant", "Lieferschein", "Zeugnis", "Datum"]]
        for r in E["zeugnis"]:
            a = r["data"]
            rows.append([P(a.get("werkstoff")), P(a.get("abmessung")), P(" / ".join(v for v in (a.get("charge"), a.get("schmelze")) if v)),
                         P(a.get("lieferant")), P(a.get("lieferschein")), P(a.get("typ") or "3.1"), de_date(a.get("datum") or "")])
        el += [Paragraph("Werkstoffzeugnisse nach EN 10204", S_["H2"]), _m76_table(rows, [24 * mm, 26 * mm, 32 * mm, 30 * mm, 24 * mm, 16 * mm, 22 * mm], S_)]
    if E["zusatz"]:
        rows = [["Zusatzwerkstoff", "Normbezeichnung", "Hersteller", "Charge", "Durchmesser"]]
        for r in E["zusatz"]:
            a = r["data"]
            rows.append([P(a.get("bezeichnung")), P(a.get("norm")), P(a.get("hersteller")), P(a.get("charge")), P(a.get("durchmesser"))])
        el += [Paragraph("Zusatzwerkstoffe", S_["H2"]), _m76_table(rows, [36 * mm, 56 * mm, 30 * mm, 30 * mm, 22 * mm], S_)]
    if E["pruefung"]:
        rows = [["Datum", "Art", "Umfang", "Position", "Ergebnis", "Prüfer", "Bericht"]]
        for r in E["pruefung"]:
            a = r["data"]
            rows.append([de_date(a.get("datum") or ""), P(a.get("art")), P(a.get("umfang")), P(a.get("pos")), P(a.get("ergebnis")),
                         P(a.get("pruefer")), P(a.get("bericht"))])
        el += [Paragraph("Prüfungen", S_["H2"]), _m76_table(rows, [20 * mm, 12 * mm, 22 * mm, 30 * mm, 18 * mm, 34 * mm, 38 * mm], S_)]
    if d.get("notiz"):
        el += [Paragraph("Bemerkungen", S_["H2"]), Paragraph(e(d["notiz"]).replace("\n", "<br/>"), S_["N"])]
    el += [Spacer(1, 14), Paragraph(f"Schweißaufsicht: {e(s['aufsicht'])} &nbsp; &nbsp; Datum: {de_date(today())} &nbsp; &nbsp; Unterschrift: ______________________", S_["N"])]
    doc.build(el, onFirstPage=_m76_onpage(f"Schweißdokumentation {p['nr']} · T. Pfeiffer"), onLaterPages=_m76_onpage(f"Schweißdokumentation {p['nr']} · T. Pfeiffer"))
    return buf.getvalue()


def _m76_pdf_pages(b):
    import pypdf
    return len(pypdf.PdfReader(io.BytesIO(b)).pages)


def _m76_file_pdf(path):
    """attached file -> pdf bytes (pdf as is, images on an A4 page), else None"""
    low = path.lower()
    try:
        if low.endswith(".pdf"):
            b = pdf_plain_bytes(path) if "pdf_plain_bytes" in globals() else None
            b = b or open(path, "rb").read()
            _m76_pdf_pages(b)
            return b
        if low.endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp")):
            from PIL import Image
            im = Image.open(path)
            im = im.convert("RGB")
            buf = io.BytesIO()
            cv = rl_canvas.Canvas(buf, pagesize=A4)
            W, H = A4
            iw, ih = im.size
            sc = min((W - 60) / iw, (H - 80) / ih)
            ib = io.BytesIO()
            im.save(ib, "JPEG", quality=85)
            cv.drawImage(ImageReader(io.BytesIO(ib.getvalue())), (W - iw * sc) / 2, (H - ih * sc) / 2, iw * sc, ih * sc)
            cv.setFont(FONT_R(), 7)
            cv.drawString(30, 20, os.path.basename(path))
            cv.showPage()
            cv.save()
            return buf.getvalue()
    except Exception:
        traceback.print_exc()
    return None


def _m76_parts(pid):
    d, p, s = _m76_ctx(pid)
    parts = [("Schweiß- und Herstellungsdokumentation", m76_doku_bytes(pid), None),
             ("Leistungserklärung " + d["dop_nr"], m76_dop_bytes(pid), None),
             ("CE-Kennzeichnung", m76_ce_bytes(pid), None)]
    files = []
    for w in d["wps"]:
        if w.get("file"):
            files.append((f"{w['art']} {w['nr']}", w["file"]))
    for z in d["schweisser"]:
        if z.get("file"):
            files.append((f"Schweißerprüfung {z['person'] or ''} {z['nummer'] or ''}".strip(), z["file"]))
    for art in ("zeugnis", "zusatz", "pruefung", "pos"):
        for r in d["eintraege"][art]:
            if r.get("file"):
                a = r["data"]
                lbl = {"zeugnis": f"Werkstoffzeugnis {a.get('werkstoff', '')} {a.get('charge', '')}",
                       "zusatz": f"Zusatzwerkstoff {a.get('bezeichnung', '')}",
                       "pruefung": f"Prüfbericht {a.get('art', '')} {a.get('bericht', '')}",
                       "pos": f"Zeichnung {a.get('pos', '')} {a.get('bezeichnung', '')}"}[art]
                files.append((lbl.strip(), r["file"]))
    for lbl, rel in files:
        fp = rel if os.path.isabs(rel) else os.path.join(DATA_DIR, rel)
        if os.path.isfile(fp):
            parts.append((lbl, None, fp))
    return d, p, s, parts


def _m76_cover(d, p, s, toc, total):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    S_ = _m76_styles()
    e = _m76_e
    buf = io.BytesIO()
    doc = _m76_doc(buf, f"Übergabepaket {p['nr']}")
    cust = p.get("customer") or {}
    el = [Spacer(1, 30 * mm), Paragraph("ÜBERGABEPAKET · EN 1090", S_["K"]), Paragraph(e(p["name"]), S_["H1"]),
          Paragraph(f"Projekt {e(p['nr'])} · Kunde: {e(cust.get('firma') or cust.get('name') or '-')}", S_["N"]),
          Paragraph(f"Ausführungsklasse {e(d['exc'])} · Leistungserklärung {e(d['dop_nr'])} · Hersteller {e(s['hersteller'])}", S_["N"]),
          Paragraph(f"Stand {de_date(today())} · {total} Seiten", S_["NS"]), Spacer(1, 14), Paragraph("Inhalt", S_["H2"])]
    rows = [[f"{i + 1}.", Paragraph(e(t), S_["C"]), str(pg)] for i, (t, pg) in enumerate(toc)]
    t = Table(rows or [["", "", ""]], colWidths=[10 * mm, 140 * mm, 20 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), FONT_R(), 9), ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, S_["line"]), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(t)
    doc.build(el, onFirstPage=_m76_onpage(f"Übergabepaket {p['nr']} · T. Pfeiffer"), onLaterPages=_m76_onpage(f"Übergabepaket {p['nr']} · T. Pfeiffer"))
    return buf.getvalue()


def m76_merged_bytes(pid):
    import pypdf
    d, p, s, parts = _m76_parts(pid)
    blobs = []
    for lbl, b, fp in parts:
        if b is None:
            b = _m76_file_pdf(fp)
            if b is None:
                continue
        blobs.append((lbl, b, _m76_pdf_pages(b)))
    cover_pages = 1
    for _ in range(3):
        toc, pg = [], cover_pages + 1
        for lbl, b, n in blobs:
            toc.append((lbl, pg))
            pg += n
        cover = _m76_cover(d, p, s, toc, pg - 1)
        n_c = _m76_pdf_pages(cover)
        if n_c == cover_pages:
            break
        cover_pages = n_c
    w = pypdf.PdfWriter()
    for b in [cover] + [b for _, b, _ in blobs]:
        for pg_ in pypdf.PdfReader(io.BytesIO(b)).pages:
            w.add_page(pg_)
    try:
        for lbl, pg_ in toc:
            w.add_outline_item(lbl, pg_ - 1)
    except Exception:
        pass
    w.add_metadata({"/Title": f"Übergabepaket {p['nr']} {p['name']}", "/Author": "T. Pfeiffer"})
    out = io.BytesIO()
    w.write(out)
    return out.getvalue(), [p_[0] for p_ in blobs]


def _m76_save_to_project(pid, name, data, note):
    p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    base = ensure_project_folders(p)
    dd = os.path.join(base, M76_DIR)
    os.makedirs(dd, exist_ok=True)
    fp = os.path.join(dd, safe_name(name))
    write_file(fp, data)
    rel = os.path.relpath(fp, DATA_DIR)
    if q("SELECT id FROM project_files WHERE path=?", (rel,), one=True):
        x("UPDATE project_files SET size=?, added=? WHERE path=?", (len(data), now_iso(), rel))
    else:
        x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
          (pid, M76_DIR, "Schweißdokument", os.path.basename(fp), rel, len(data), note, now_iso()))
    return fp, rel


def m76_make(pid, was):
    pid = int(pid)
    p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("Projekt nicht gefunden.")
    _m76_ensure(pid)
    tag = today()
    if was == "dop":
        d = _m76_ctx(pid)[0]
        fp, rel = _m76_save_to_project(pid, f"Leistungserklaerung_{d['dop_nr']}_{tag}.pdf", m76_dop_bytes(pid), "Leistungserklärung (DoP)")
    elif was == "ce":
        fp, rel = _m76_save_to_project(pid, f"CE-Kennzeichnung_{p['nr']}_{tag}.pdf", m76_ce_bytes(pid), "CE-Kennzeichnung")
    elif was == "doku":
        fp, rel = _m76_save_to_project(pid, f"Schweissdokumentation_{p['nr']}_{tag}.pdf", m76_doku_bytes(pid), "Schweißdokumentation")
    elif was == "pdf":
        b, inh = m76_merged_bytes(pid)
        fp, rel = _m76_save_to_project(pid, f"Uebergabepaket_{p['nr']}_{tag}.pdf", b, "Übergabepaket (ein PDF)")
    elif was == "zip":
        d, p2, s, parts = _m76_parts(pid)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            b, inh = m76_merged_bytes(pid)
            z.writestr(f"00_Uebergabepaket_{p['nr']}.pdf", b)
            for i, (lbl, bb, fp_) in enumerate(parts, 1):
                if bb is not None:
                    z.writestr(f"{i:02d}_{safe_name(lbl)}.pdf", bb)
                else:
                    z.write(fp_, f"{i:02d}_{safe_name(lbl)}{os.path.splitext(fp_)[1].lower()}")
        fp, rel = _m76_save_to_project(pid, f"Uebergabepaket_{p['nr']}_{tag}.zip", buf.getvalue(), "Übergabepaket (ZIP)")
    else:
        raise ValueError("Unbekanntes Dokument.")
    if not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return {"ok": True, "path": fp, "rel": rel, "name": os.path.basename(fp)}


# ---------------------------------------------------------------------------
# Routes, export, boot, selftest
# ---------------------------------------------------------------------------
def _m76_ok(h, r):
    return h._send(200, r)


HOOK_GET["/api/m76/project"] = lambda h, qs: _m76_ok(h, m76_get(int(qs["project_id"])))
HOOK_GET["/api/m76/overview"] = lambda h, qs: _m76_ok(h, m76_overview())
HOOK_POST["/api/m76/save"] = lambda h, d: _m76_ok(h, m76_save_proj(d))
HOOK_POST["/api/m76/entry/save"] = lambda h, d: _m76_ok(h, m76_save_entry(d))
HOOK_POST["/api/m76/entry/delete"] = lambda h, d: _m76_ok(h, m76_delete_entry(d.get("ids") or [d.get("id")]))
HOOK_POST["/api/m76/link"] = lambda h, d: _m76_ok(h, m76_link(d))
HOOK_POST["/api/m76/wps/save"] = lambda h, d: _m76_ok(h, m76_save_wps(d))
HOOK_POST["/api/m76/wps/delete"] = lambda h, d: _m76_ok(h, m76_delete_wps(d.get("ids") or [d.get("id")]))
HOOK_POST["/api/m76/make"] = lambda h, d: _m76_ok(h, m76_make(d["project_id"], d.get("was") or "pdf"))


def _m76_settings_save(h, d):
    cur_ = m76_settings()
    for k in M76_DEF_SET:
        if k in d:
            cur_[k] = str(d[k] or "")[:300]
    set_setting("m76", cur_)
    return h._send(200, {"ok": True, "settings": cur_})


HOOK_POST["/api/m76/settings"] = _m76_settings_save


def _m76_boot(b):
    try:
        warn = 0
        ids = []
        for r in q("SELECT project_id FROM m76_proj WHERE aktiv=1"):
            ids.append(r["project_id"])
            pr = q("SELECT status FROM projects WHERE id=?", (r["project_id"],), one=True)
            if not pr or pr["status"] != "aktiv":
                continue
            d = m76_get(r["project_id"])
            warn += sum(1 for w in d["warnungen"] if w["stufe"] == "fehler")
        b["m76"] = {"fehler": warn, "ids": ids}
    except Exception:
        b["m76"] = {"fehler": 0, "ids": []}


HOOK_BOOT.append(_m76_boot)


def _m76_ex(p):
    pid = int(p.get("project_id") or 0)
    if pid:
        d = m76_get(pid)
        E = d["eintraege"]
        out = [_sh("Positionen", [("Pos.", "t", 8), ("Bezeichnung", "t", 30), ("Zeichnung", "t", 16), ("Werkstoff", "t", 14),
                                  ("Naht", "t", 14), ("Prüfung", "t", 14)],
                   [[r["data"].get("pos", ""), r["data"].get("bezeichnung", ""), r["data"].get("zeichnung", ""), r["data"].get("werkstoff", ""),
                     r["data"].get("naht", ""), r["data"].get("pruefung", "")] for r in E["pos"]], f"{d['projekt']['nr']} {d['projekt']['name']} · {d['exc']}"),
               _sh("Werkstoffzeugnisse", [("Werkstoff", "t", 16), ("Abmessung", "t", 18), ("Charge", "t", 14), ("Schmelze", "t", 14),
                                          ("Lieferant", "t", 20), ("Lieferschein", "t", 14), ("Zeugnis", "t", 8), ("Datum", "d", 11)],
                   [[r["data"].get(k, "") for k in ("werkstoff", "abmessung", "charge", "schmelze", "lieferant", "lieferschein", "typ", "datum")] for r in E["zeugnis"]]),
               _sh("Prüfungen", [("Datum", "d", 11), ("Art", "t", 8), ("Umfang", "t", 12), ("Position", "t", 16), ("Ergebnis", "t", 10),
                                 ("Prüfer", "t", 18), ("Bericht", "t", 16)],
                   [[r["data"].get(k, "") for k in ("datum", "art", "umfang", "pos", "ergebnis", "pruefer", "bericht")] for r in E["pruefung"]]),
               _sh("Schweißer", [("Person", "t", 22), ("Nachweis", "t", 30), ("Nr.", "t", 16), ("gültig bis", "d", 11), ("Status", "t", 30)],
                   [[z["person"] or "", z["bezeichnung"] or "", z["nummer"] or "", z["gueltig_bis"] or "", z["state_txt"] or "gültig"] for z in d["schweisser"]])]
        return out
    ov = m76_overview()
    return [_sh("EN 1090 Projekte", [("Nr.", "t", 12), ("Projekt", "t", 30), ("EXC", "t", 7), ("DoP", "t", 16), ("Positionen", "n", 9),
                                     ("Zeugnisse", "n", 9), ("Prüfungen", "n", 9), ("Fehler", "n", 7), ("Warnungen", "n", 9)],
                [[r["nr"], r["name"], r["exc"], r["dop_nr"], r["anzahl"]["pos"], r["anzahl"]["zeugnis"], r["anzahl"]["pruefung"], r["fehler"], r["warnungen"]]
                 for r in ov["projekte"]], f"Stand {de_date(today())}", total=False),
            _sh("WPS / WPQR", [("Art", "t", 7), ("Nr.", "t", 16), ("Verfahren", "t", 12), ("Werkstoff", "t", 16), ("Dicke", "t", 10),
                               ("Position", "t", 12), ("Zusatz", "t", 18), ("gültig bis", "d", 11)],
                [[w["art"], w["nr"], w["verfahren"], w["werkstoff"], w["dicke"], w["position"], w["zusatz"], w["gueltig_bis"] or ""] for w in ov["wps"]], "", total=False)]


EXPORTS["m76_en1090"] = ("EN1090", _m76_ex)


def _m76_selftest():
    err = []
    pid = None
    try:
        pid = x("INSERT INTO projects (nr, name, bereich, status, start, folders, created, updated) VALUES (?,?,?,?,?,?,?,?)",
                ("_ST76", "Selbsttest Geländer", "Metallbau", "aktiv", today(), "[]", now_iso(), now_iso()))
        m76_save_proj({"project_id": pid, "exc": "EXC2", "produkt": "Treppengeländer", "dop_nr": "DoP-ST76"})
        m76_save_entry({"project_id": pid, "art": "pos", "data": {"pos": "1", "bezeichnung": "Pfosten", "werkstoff": "S235JR"}})
        m76_save_entry({"project_id": pid, "art": "pruefung", "data": {"art": "VT", "umfang": "100 %", "ergebnis": "i.O."}})
        w = m76_save_wps({"art": "WPS", "nr": "_ST-WPS-135", "verfahren": "135", "gueltig_bis": "2000-01-01", "project_id": pid})
        d = m76_get(pid)
        if len(d["eintraege"]["pos"]) != 1 or not d["wps"]:
            err.append("m76: Einträge/WPS fehlen")
        if not any("nicht mehr gültig" in w_["text"] for w_ in d["warnungen"]):
            err.append("m76: abgelaufene WPS nicht gewarnt")
        b = m76_dop_bytes(pid)
        if not b.startswith(b"%PDF"):
            err.append("m76: DoP kein PDF")
        mb, inh = m76_merged_bytes(pid)
        if _m76_pdf_pages(mb) < 4:
            err.append("m76: Übergabe-PDF zu kurz")
        m76_delete_wps([w["id"]])
    except Exception as e:
        err.append(f"m76 Ausnahme: {e}")
    finally:
        if pid:
            x("DELETE FROM m76_eintrag WHERE project_id=?", (pid,))
            x("DELETE FROM m76_link WHERE project_id=?", (pid,))
            x("DELETE FROM m76_proj WHERE project_id=?", (pid,))
            x("DELETE FROM project_files WHERE project_id=?", (pid,))
            x("DELETE FROM projects WHERE id=?", (pid,))
    return err


HOOK_SELFTEST.append(_m76_selftest)
