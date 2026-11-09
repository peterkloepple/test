# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m84_kalender  v3.1.0
# Kalender (ergaenzt m29 TimeTree-Lesen) - ab v3.1.0 in EINER Datei zusammengefasst aus:
#   m84_kalender_plus      Programm-Termine, eigene Termine, ICS-Abo, Aktionen aus Terminen
#   m84b_timetree_schreiben Termine nach TimeTree schreiben, Pruefung, Wiederholung, Diagnose
#   m84c_kurstermine       Kurstermine ohne Teilnehmer, Nachtragen beim Hinzufuegen
# Reihenfolge der Teile = bisherige Lade-Reihenfolge (Verhalten unveraendert).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer


# ============================================================================
# Teil aus m84_kalender_plus.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m84_kalender_plus (v2.0.19)
# Kalender in beide Richtungen (ergaenzt m29 TimeTree, das nur lesend ist):
#  (a) Programm-Termine: Faelligkeiten offener Rechnungen, ablaufende Angebote, Mahnfristen, Wartung,
#      Projektstart/-ende, ablaufende Nachweise, Wiedervorlagen (m83) und Termine anderer Module
#      (Registrierung ueber M84_QUELLEN). Erscheinen als Kalender "Programm-Termine" im Reiter Kalender,
#      als .ics-Datei speicherbar und als ICS-Abo: m84_ics(scope) liefert den Text, die Auslieferung
#      ans Handy uebernimmt der API-Server (m88, Route /ics/<token>.ics).
#  (b) Aus jedem Termin: "Als Fahrt erfassen", "Zeit buchen" (Projekt), "Rechnung" und "Unterrichtsstunde".
#      Kunde / Projekt / Schueler werden aus Titel und Ort erraten.
#  (c) Eigene Termine im Programm (Tabelle m84_termin) - Kalender "Eigene Termine" neben TimeTree.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M84_VERSION = "1.0.0"
M84_CAL_EIGEN = "m84_eigen"
M84_CAL_PROG = "m84_prog"
M84_ARTEN = {"rechnung": "Fällige Rechnungen", "angebot": "Angebote laufen ab", "mahnung": "Mahnfristen", "wartung": "Wartung & Abos",
             "projekt": "Projektstart / -ende", "nachweis": "Nachweise laufen ab", "wiedervorlage": "Wiedervorlagen (Kundenakte)"}
M84_DEFAULT = {"arten": list(M84_ARTEN), "eigen": True, "timetree": False, "tage_zurueck": 60, "tage_voraus": 400}
# other modules: M84_QUELLEN["key"] = ("Label", fn(von_iso, bis_iso) -> [{"datum", "titel", "notiz", "ort", "ref"}])
M84_QUELLEN = {}


def _m84_schema():
    x("CREATE TABLE IF NOT EXISTS m84_termin (id INTEGER PRIMARY KEY, datum TEXT, bis_datum TEXT, von TEXT, bis TEXT, ganztags INTEGER DEFAULT 0, "
      "titel TEXT, ort TEXT, notiz TEXT, customer_id INTEGER, project_id INTEGER, uid TEXT, created TEXT, updated TEXT)")
    x("CREATE INDEX IF NOT EXISTS ix_m84_termin_d ON m84_termin(datum)")
    x("INSERT OR IGNORE INTO kal_cal (id, quelle, name, farbe, aktiv, anzahl, abgerufen, raw) VALUES (?,?,?,?,?,?,?,?)",
      (M84_CAL_EIGEN, "programm", "Eigene Termine", "#ff9f0a", 1, 0, "", ""))
    x("INSERT OR IGNORE INTO kal_cal (id, quelle, name, farbe, aktiv, anzahl, abgerufen, raw) VALUES (?,?,?,?,?,?,?,?)",
      (M84_CAL_PROG, "programm", "Programm-Termine", "#8e8e93", 1, 0, "", ""))


HOOK_SCHEMA.append(_m84_schema)


# v2.0.19 (R4): appointments keep their date, but lose the link to a deleted customer / project
# (otherwise a new customer with the re-used id would show them in his Kundenakte)
def _m84_clean_cust():
    x("UPDATE m84_termin SET customer_id=NULL WHERE customer_id IS NOT NULL AND customer_id NOT IN (SELECT id FROM customers)")


def _m84_clean_proj():
    x("UPDATE m84_termin SET project_id=NULL WHERE project_id IS NOT NULL AND project_id NOT IN (SELECT id FROM projects)")


if "M83_NACH_LOESCHEN" in globals():
    M83_NACH_LOESCHEN.setdefault("customers", []).append(_m84_clean_cust)
    M83_NACH_LOESCHEN.setdefault("projects", []).append(_m84_clean_proj)


def _m84_num(v, name):
    """German number input ("1.234,5", "12,5", 12.5) -> float, clear message on garbage"""
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(parse_amount(str(v)))
    except Exception:
        raise ValueError(f"{name}: „{v}“ ist keine Zahl.")


def _m84_hm(v, name):
    """'9:00' / '09:00' / '09:00:00' -> '09:00', '' stays ''; anything else -> clear message"""
    t = str(v or "").strip()
    if not t:
        return ""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", t)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError(f"{name}: „{t}“ ist keine Uhrzeit (bitte HH:MM).")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def m84_cfg():
    c = dict(M84_DEFAULT)
    c.update({k: v for k, v in (get_settings().get("m84_ics") or {}).items() if k in M84_DEFAULT})
    return c


def _m84_in(d, von, bis):
    return bool(d) and von <= d[:10] <= bis


# ---------------------------------------------------------------------------
# program dates
# ---------------------------------------------------------------------------
def m84_prog_events(von, bis, arten=None):
    arten = set(arten if arten is not None else m84_cfg()["arten"])
    out = []

    def add(art, datum, titel, notiz="", ort="", ref=None):
        if _m84_in(datum, von, bis):
            out.append({"uid": f"m84-{art}-{(ref or {}).get('kind', '')}-{(ref or {}).get('id', '')}-{datum[:10]}", "art": art,
                        "datum": datum[:10], "titel": titel, "notiz": notiz or "", "ort": ort or "", "ref": ref or {}})

    if "rechnung" in arten:
        invs = q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen'")
        # v2.1.0: open amount after partial payments (m71) - before, the full invoice sum was shown as "offen"
        sts = {}
        try:
            sts = m71_states(invs) if "m71_states" in globals() else {}
        except Exception:
            traceback.print_exc()
        for r in invs:
            try:
                due = (datetime.date.fromisoformat(r["datum"][:10]) + datetime.timedelta(days=_frist(r["frist"]))).isoformat()
            except Exception:
                continue
            offen = (sts.get(r["id"]) or {}).get("rest", r["summe"] or 0)
            add("rechnung", due, f"Fällig: Rechnung {r['nr']} – {inv_name(r)}", f"{money(offen)} offen", "", {"kind": "invoice", "id": r["id"]})
    if "angebot" in arten:
        for r in q("SELECT * FROM invoices WHERE typ='angebot' AND status='offen' AND COALESCE(gueltig_bis,'')!=''"):
            add("angebot", r["gueltig_bis"], f"Angebot {r['nr']} läuft ab – {inv_name(r)}", money(r["summe"] or 0), "", {"kind": "invoice", "id": r["id"]})
    if "mahnung" in arten:
        for m in q("SELECT m.*, i.nr, i.customer_id, i.addr, i.kdnr FROM mahnungen m JOIN invoices i ON i.id=m.invoice_id WHERE i.status='offen'"):
            add("mahnung", m["frist_bis"] or "", f"Mahnfrist: {MAHN_TITLES[min(int(m['stufe'] or 0), 3)]} {m['nr']} – {inv_name(m)}", money(m["betrag"] or 0), "",
                {"kind": "invoice", "id": m["invoice_id"]})
    if "wartung" in arten:
        for v in q("SELECT v.*, COALESCE(NULLIF(c.firma,''), c.name) kunde FROM vertraege v LEFT JOIN customers c ON c.id=v.customer_id WHERE v.aktiv=1"):
            add("wartung", v["naechste"] or "", f"Wartung: {v['name']}" + (f" – {v['kunde']}" if v["kunde"] else ""), v["beschreibung"] or "", "",
                {"kind": "abo", "id": v["id"]})
    if "projekt" in arten:
        for p in q("SELECT p.*, COALESCE(NULLIF(c.firma,''), c.name) kunde FROM projects p LEFT JOIN customers c ON c.id=p.customer_id "
                   "WHERE COALESCE(p.status,'') NOT IN ('abgeschlossen','archiviert','storniert')"):
            nm = f"{p['nr'] or ''} {p['name'] or ''}".strip()
            add("projekt", p["start"] or "", f"Projektstart: {nm}", p["kunde"] or "", "", {"kind": "project", "id": p["id"]})
            if p["ende"] and p["ende"] != p["start"]:
                add("projekt", p["ende"], f"Projektende: {nm}", p["kunde"] or "", "", {"kind": "project", "id": p["id"]})
    if "nachweis" in arten:
        for z in q("SELECT * FROM zertifikate WHERE aktiv=1 AND COALESCE(gueltig_bis,'')!=''"):
            add("nachweis", z["gueltig_bis"], f"Nachweis läuft ab: {z['bezeichnung']}" + (f" ({z['person']})" if z["person"] else ""), z["nummer"] or "", "",
                {"kind": "cert", "id": z["id"]})
    if "wiedervorlage" in arten and _m83_tab("m83_notiz"):
        for n in q("SELECT n.*, COALESCE(NULLIF(c.firma,''), c.name) kunde FROM m83_notiz n LEFT JOIN customers c ON c.id=n.customer_id "
                   "WHERE COALESCE(n.wv_datum,'')!='' AND COALESCE(n.erledigt,0)=0"):
            add("wiedervorlage", n["wv_datum"], f"Wiedervorlage: {n['titel'] or 'Notiz'}" + (f" – {n['kunde']}" if n["kunde"] else ""), n["text"] or "", "",
                {"kind": "customer", "id": n["customer_id"]})
    for key, (label, fn) in list(M84_QUELLEN.items()):
        if key not in arten and arten != set(M84_ARTEN) | set(M84_QUELLEN):
            if key not in (m84_cfg().get("arten") or []):
                continue
        try:
            for e in fn(von, bis) or []:
                add(key, e.get("datum") or "", e.get("titel") or label, e.get("notiz") or "", e.get("ort") or "", e.get("ref"))
        except Exception:
            traceback.print_exc()
    out.sort(key=lambda e: (e["datum"], e["titel"]))
    return out


def m84_termine(von, bis):
    return q("SELECT t.*, COALESCE(NULLIF(c.firma,''), c.name) kunde, p.nr pnr, p.name pname FROM m84_termin t "
             "LEFT JOIN customers c ON c.id=t.customer_id LEFT JOIN projects p ON p.id=t.project_id "
             "WHERE t.datum<=? AND COALESCE(NULLIF(t.bis_datum,''), t.datum)>=? ORDER BY t.datum, t.von", (bis[:10], von[:10]))


# ---------------------------------------------------------------------------
# calendar integration (m29)
# ---------------------------------------------------------------------------
_m84_prev_kal_events = chain_inner("kal_events", "m84_kalender")   # v3.0.0: the level below this module (was: the function before the wrapper)
@chain_step("kal_events", "m84_kalender")
def _m84_step_kal_events(_next, von, bis, qtext="", alle=False):
    out = _next(von, bis, qtext, alle)
    try:
        cals = {r["id"]: r for r in q("SELECT id, name, farbe, aktiv FROM kal_cal WHERE id IN (?,?)", (M84_CAL_EIGEN, M84_CAL_PROG))}
        ql = (qtext or "").lower().strip()
        ce, cp = cals.get(M84_CAL_EIGEN), cals.get(M84_CAL_PROG)
        if ce and (ce["aktiv"] or alle):
            for t in m84_termine(von, bis):
                if ql and ql not in f"{t['titel']} {t['notiz']} {t['ort']} {t['kunde'] or ''}".lower():
                    continue
                ad = bool(t["ganztags"]) or not t["von"]
                end_d = t["bis_datum"] or t["datum"]
                out.append({"uuid": f"m84t-{t['id']}", "cal_id": M84_CAL_EIGEN, "kal": ce["name"], "title": t["titel"] or "(ohne Titel)",
                            "start": f"{t['datum']}T{'00:00' if ad else t['von']}", "end": f"{end_d}T{'00:00' if ad else (t['bis'] or t['von'])}",
                            "all_day": ad, "farbe": ce["farbe"] or "#ff9f0a", "label": t["kunde"] or "", "ort": t["ort"] or "", "notiz": t["notiz"] or "",
                            "url": "", "wdh": False, "memo": False,
                            "m84": {"kind": "termin", "id": t["id"], "customer_id": t["customer_id"], "project_id": t["project_id"]}})
        if cp and (cp["aktiv"] or alle):
            for e in m84_prog_events(von, bis):
                if ql and ql not in f"{e['titel']} {e['notiz']}".lower():
                    continue
                out.append({"uuid": e["uid"], "cal_id": M84_CAL_PROG, "kal": cp["name"], "title": e["titel"], "start": e["datum"] + "T00:00",
                            "end": e["datum"] + "T00:00", "all_day": True, "farbe": cp["farbe"] or "#8e8e93",
                            "label": M84_ARTEN.get(e["art"]) or (M84_QUELLEN.get(e["art"]) or ("",))[0], "ort": e["ort"], "notiz": e["notiz"],
                            "url": "", "wdh": False, "memo": False, "m84": {"kind": "prog", "art": e["art"], "ref": e["ref"]}})
        out.sort(key=lambda r: (r["start"][:10], not r["all_day"], r["start"], r["title"]))
    except Exception:
        traceback.print_exc()
    return out


@chain_step("kal_info", "m84_kalender")
def _m84_step_kal_info(_next, ):
    r = _next()
    try:
        t0 = datetime.date.today()
        n_e = q("SELECT COUNT(*) n FROM m84_termin", one=True)["n"]
        n_p = len(m84_prog_events((t0 - datetime.timedelta(days=60)).isoformat(), (t0 + datetime.timedelta(days=400)).isoformat()))
        for c in r.get("kalender") or []:
            if c["id"] == M84_CAL_EIGEN:
                c["anzahl"] = n_e
            elif c["id"] == M84_CAL_PROG:
                c["anzahl"] = n_p
        r["m84"] = {"cfg": m84_cfg(), "arten": dict(M84_ARTEN, **{k: v[0] for k, v in M84_QUELLEN.items()}), "abo": m84_abo_info()}
    except Exception:
        traceback.print_exc()
    return r


@chain_step("kal_cal_update", "m84_kalender")
def _m84_step_kal_cal_update(_next, d):
    if d.get("loeschen") and d.get("id") in (M84_CAL_EIGEN, M84_CAL_PROG):
        raise ValueError("Die Programm-Kalender lassen sich nicht entfernen - zum Ausblenden auf den Kalender-Chip klicken.")
    return _next(d)


HOOK_POST["/api/kal/cal"] = lambda h, d: h._send(200, kal_cal_update(d))
HOOK_GET["/api/kal/info"] = lambda h, qs: h._send(200, kal_info())


# ---------------------------------------------------------------------------
# ICS (file + subscription)
# ---------------------------------------------------------------------------
def _m84_ics_dt(d, hm=None):
    if hm:
        return d.replace("-", "") + "T" + hm.replace(":", "") + "00"
    return d.replace("-", "")


def m84_ics(token_scope=None):
    """ICS text for subscription / file. token_scope: None = settings, list of kinds, or dict like M84_DEFAULT."""
    cfg = m84_cfg()
    if isinstance(token_scope, (list, tuple, set)):
        cfg["arten"] = [a for a in token_scope if a not in ("eigen", "timetree")]
        cfg["eigen"] = "eigen" in token_scope or cfg["eigen"]
        cfg["timetree"] = "timetree" in token_scope
    elif isinstance(token_scope, dict):
        cfg.update({k: v for k, v in token_scope.items() if k in M84_DEFAULT})
    t0 = datetime.date.today()
    von = (t0 - datetime.timedelta(days=int(cfg["tage_zurueck"] or 60))).isoformat()
    bis = (t0 + datetime.timedelta(days=int(cfg["tage_voraus"] or 400))).isoformat()
    stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    L_ = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//T. Pfeiffer//PA Rechnung {APP_VERSION}//DE", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
          "X-WR-CALNAME:" + _ics_esc(get_settings().get("firma") or "PA Rechnung"), "X-PUBLISHED-TTL:PT1H", "REFRESH-INTERVAL;VALUE=DURATION:PT1H"]
    if cfg.get("eigen"):
        for t in m84_termine(von, bis):
            ad = bool(t["ganztags"]) or not t["von"]
            try:
                # one broken stored appointment (old data) must not break the whole subscription
                end_d = t["bis_datum"] or t["datum"]
                datetime.date.fromisoformat(t["datum"])
                datetime.date.fromisoformat(end_d)
                hv, hb = ("", "") if ad else (_m84_hm(t["von"], "Beginn"), _m84_hm(t["bis"], "Ende"))
            except Exception:
                continue
            L_ += ["BEGIN:VEVENT", "UID:" + _ics_esc(t["uid"] or f"m84t-{t['id']}@pa-rechnung"), "DTSTAMP:" + stamp, "SUMMARY:" + _ics_esc(t["titel"])]
            if ad:
                e_ = (datetime.date.fromisoformat(end_d) + datetime.timedelta(days=1)).isoformat()
                L_ += ["DTSTART;VALUE=DATE:" + _m84_ics_dt(t["datum"]), "DTEND;VALUE=DATE:" + _m84_ics_dt(e_)]
            else:
                L_ += ["DTSTART:" + _m84_ics_dt(t["datum"], hv), "DTEND:" + _m84_ics_dt(end_d, hb or hv)]
            desc = "\n".join(v for v in (t["notiz"], ("Kunde: " + t["kunde"]) if t["kunde"] else "", ("Projekt: " + (t["pnr"] or "")) if t["pnr"] else "") if v)
            if desc:
                L_.append("DESCRIPTION:" + _ics_esc(desc))
            if t["ort"]:
                L_.append("LOCATION:" + _ics_esc(t["ort"]))
            L_ += ["CATEGORIES:Eigene Termine", "END:VEVENT"]
    for e in m84_prog_events(von, bis, cfg.get("arten") or []):
        try:
            nd = (datetime.date.fromisoformat(e["datum"]) + datetime.timedelta(days=1)).isoformat()
        except ValueError:
            continue        # date field of another module with a broken value
        L_ += ["BEGIN:VEVENT", "UID:" + _ics_esc(e["uid"] + "@pa-rechnung"), "DTSTAMP:" + stamp, "SUMMARY:" + _ics_esc(e["titel"]),
               "DTSTART;VALUE=DATE:" + _m84_ics_dt(e["datum"]), "DTEND;VALUE=DATE:" + _m84_ics_dt(nd), "TRANSP:TRANSPARENT"]
        if e["notiz"]:
            L_.append("DESCRIPTION:" + _ics_esc(e["notiz"]))
        L_ += ["CATEGORIES:" + _ics_esc(M84_ARTEN.get(e["art"]) or e["art"]), "END:VEVENT"]
    if cfg.get("timetree"):
        try:
            for e in _m84_prev_kal_events(von, bis):
                L_ += ["BEGIN:VEVENT", "UID:" + _ics_esc(f"{e['uuid']}-{e['start']}@timetree"), "DTSTAMP:" + stamp, "SUMMARY:" + _ics_esc(e["title"])]
                if e["all_day"]:
                    nd = (datetime.date.fromisoformat(e["end"][:10]) + datetime.timedelta(days=1)).isoformat()
                    L_ += ["DTSTART;VALUE=DATE:" + _m84_ics_dt(e["start"][:10]), "DTEND;VALUE=DATE:" + _m84_ics_dt(nd)]
                else:
                    L_ += ["DTSTART:" + _m84_ics_dt(e["start"][:10], e["start"][11:16]), "DTEND:" + _m84_ics_dt(e["end"][:10], e["end"][11:16])]
                if e["ort"]:
                    L_.append("LOCATION:" + _ics_esc(e["ort"]))
                if e["notiz"]:
                    L_.append("DESCRIPTION:" + _ics_esc(e["notiz"]))
                L_ += ["CATEGORIES:" + _ics_esc(e["kal"]), "END:VEVENT"]
        except Exception:
            traceback.print_exc()
    L_.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l_) for l_ in L_) + "\r\n"


def m84_abo_info():
    """v2.1.0: subscription via the m88 server - tokens are stored hashed, so a link is created on demand
    (button in the dialog); before, m84 asked for a function m88 never had and the link never showed"""
    have = callable(globals().get("m88_running"))
    run = bool(have and m88_running())
    base = ""
    if run:
        try:
            base = (m88_urls() or [""])[-1]
        except Exception:
            base = ""
    return {"url": "", "verfuegbar": have, "aktiv": run, "base": base}


# ---------------------------------------------------------------------------
# guessing customer / project / student from an appointment
# ---------------------------------------------------------------------------
def m84_raten(title="", ort="", datum=""):
    blob = f"{title} {ort}".lower()
    cust = None
    best = 0
    for c in q("SELECT id, firma, name, ort, kdnr FROM customers"):
        for n in ((c["firma"] or "").strip(), (c["name"] or "").strip()):
            if len(n) >= 3 and n.lower() in blob and len(n) > best:
                cust, best = c, len(n)
        if not cust and c["kdnr"] and len(c["kdnr"]) >= 3 and re.search(r"\b" + re.escape(c["kdnr"].lower()) + r"\b", blob):
            cust, best = c, 1
    if not cust and ort:
        o = ort.lower()
        cands = [c for c in q("SELECT id, firma, name, ort FROM customers WHERE COALESCE(ort,'')!=''") if (c["ort"] or "").lower() in o]
        if len(cands) == 1:
            cust = cands[0]
    proj = None
    for p in q("SELECT id, nr, name, customer_id, status FROM projects ORDER BY CASE WHEN status='aktiv' THEN 0 ELSE 1 END, start DESC"):
        if (p["nr"] and p["nr"].lower() in blob) or (p["name"] and len(p["name"]) >= 4 and p["name"].lower() in blob):
            proj = p
            break
    if not proj and cust:
        act = q("SELECT id, nr, name, customer_id, status FROM projects WHERE customer_id=? AND status='aktiv' ORDER BY start DESC", (cust["id"],))
        if len(act) >= 1:
            proj = act[0]
    if proj and not cust and proj["customer_id"]:
        cust = q("SELECT id, firma, name, ort FROM customers WHERE id=?", (proj["customer_id"],), one=True)
    stud = None
    for s_ in q("SELECT id, name, customer_id FROM students WHERE aktiv=1"):
        nm = (s_["name"] or "").strip()
        if len(nm) >= 3 and nm.lower() in blob:
            stud = s_
            break
    km = None
    zl = (ort or title or "").strip()
    if zl:
        r = q("SELECT km FROM fahrten WHERE lower(ziel)=? AND art='dienst' ORDER BY datum DESC LIMIT 1", (zl.lower(),), one=True)
        km = r["km"] if r else None
    s = get_settings()
    return {"ok": True, "customer_id": cust["id"] if cust else None, "kunde": (cust["firma"] or cust["name"]) if cust else "",
            "project_id": proj["id"] if proj else None, "projekt": f"{proj['nr'] or ''} {proj['name'] or ''}".strip() if proj else "",
            "student_id": stud["id"] if stud else None, "schueler": stud["name"] if stud else "", "km_letzte": km,
            "stundensatz": float(s.get("stundensatz") or 0)}


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
def _m84_r_termin(h, d):
    if d.get("delete"):
        for i in d.get("ids") or [d.get("id")]:
            if i:
                x("DELETE FROM m84_termin WHERE id=?", (int(i),))
        return h._send(200, {"ok": True})
    datum = (d.get("datum") or today())[:10]
    try:
        datetime.date.fromisoformat(datum)
    except Exception:
        raise ValueError("Datum fehlt oder ist ungültig.")
    bisd = (d.get("bis_datum") or "")[:10]
    if bisd:
        try:
            datetime.date.fromisoformat(bisd)
        except Exception:
            raise ValueError("Bis-Datum ist ungültig.")
    if bisd and bisd < datum:
        bisd = datum
    von, bis = _m84_hm(d.get("von"), "Beginn"), _m84_hm(d.get("bis"), "Ende")
    gt = 1 if d.get("ganztags") or not von else 0
    if not gt and bis and (bisd or datum) == datum and bis < von:
        bis = von
    if not (d.get("titel") or "").strip():
        raise ValueError("Bitte einen Titel eintragen.")
    vals = (datum, bisd, "" if gt else von, "" if gt else bis, gt, d.get("titel").strip()[:200], (d.get("ort") or "")[:200], (d.get("notiz") or "")[:4000],
            d.get("customer_id") or None, d.get("project_id") or None)
    if d.get("id"):
        x("UPDATE m84_termin SET datum=?, bis_datum=?, von=?, bis=?, ganztags=?, titel=?, ort=?, notiz=?, customer_id=?, project_id=?, updated=? WHERE id=?",
          vals + (now_iso(), int(d["id"])))
        tid = int(d["id"])
    else:
        tid = x("INSERT INTO m84_termin (datum, bis_datum, von, bis, ganztags, titel, ort, notiz, customer_id, project_id, uid, created, updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (uuid.uuid4().hex + "@pa-rechnung", now_iso(), now_iso()))
    return h._send(200, {"ok": True, "id": tid})


def _m84_r_termin_get(h, qs):
    return h._send(200, {"ok": True, "termin": q("SELECT * FROM m84_termin WHERE id=?", (int(qs["id"]),), one=True)})


def _m84_r_raten(h, qs):
    return h._send(200, m84_raten(qs.get("title") or "", qs.get("ort") or "", qs.get("datum") or ""))


def _m84_r_fahrt(h, d):
    km = _m84_num(d.get("km"), "km")
    if km <= 0:
        raise ValueError("Bitte die km eintragen.")
    fid = x("INSERT INTO fahrten (datum, ziel, zweck, km, art, project_id, customer_id, notiz) VALUES (?,?,?,?,?,?,?,?)",
            ((d.get("datum") or today())[:10], (d.get("ziel") or "")[:200], (d.get("zweck") or "")[:200], km,
             d.get("art") if d.get("art") in ("dienst", "pendel") else "dienst", d.get("project_id") or None, d.get("customer_id") or None,
             (d.get("notiz") or "")[:300]))
    return h._send(200, {"ok": True, "id": fid})


def _m84_r_zeit(h, d):
    pid = d.get("project_id")
    if not pid:
        raise ValueError("Bitte ein Projekt wählen.")
    std = _m84_num(d.get("stunden"), "Stunden")
    if std <= 0:
        raise ValueError("Dauer fehlt.")
    a = q("SELECT * FROM articles WHERE id=?", (d.get("article_id"),), one=True) if d.get("article_id") else None
    price = _m84_num(d.get("price"), "Preis") if d.get("price") not in (None, "") else (float(a["price"]) if a else float(get_settings().get("stundensatz") or 0))
    eid = x("INSERT INTO project_entries (project_id, datum, art, nr, name, descr, qty, unit, price, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (int(pid), (d.get("datum") or today())[:10], "Arbeitszeit", a["nr"] if a else "", (a["name"] if a else "Arbeitszeit"),
             (d.get("descr") or "")[:500], round(std, 2), "Std", price, now_iso()))
    return h._send(200, {"ok": True, "id": eid})


def _m84_r_stunde(h, d):
    sid = d.get("student_id")
    if not sid:
        raise ValueError("Bitte Schüler/in wählen.")
    datum = (d.get("datum") or today())[:10]
    kid = d.get("kurs_id") or None
    if q("SELECT id FROM lessons WHERE student_id=? AND datum=? AND COALESCE(kurs_id,0)=?", (int(sid), datum, kid or 0), one=True):
        raise ValueError("Für diesen Tag ist die Stunde schon eingetragen.")
    lid = x("INSERT INTO lessons (student_id, datum, dauer, status, notiz, kurs_id) VALUES (?,?,?,?,?,?)",
            (int(sid), datum, _m84_num(d["dauer"], "Dauer") if d.get("dauer") else None, "stattgefunden", (d.get("notiz") or "")[:300], kid))
    return h._send(200, {"ok": True, "id": lid})


def _m84_r_cfg(h, d):
    c = m84_cfg()
    if isinstance(d.get("arten"), list):
        c["arten"] = [a for a in d["arten"] if a in M84_ARTEN or a in M84_QUELLEN]
    for k in ("eigen", "timetree"):
        if k in d:
            c[k] = bool(d[k])
    for k in ("tage_zurueck", "tage_voraus"):
        if k in d:
            c[k] = max(0, min(3650, int(d[k] or 0)))
    set_setting("m84_ics", c)
    return h._send(200, {"ok": True, "cfg": c})


def _m84_r_export(h, d):
    data = m84_ics(d.get("scope") or None)
    out = os.path.join(DATA_DIR, "Export", "Programm-Termine_" + time.strftime("%Y-%m-%d") + ".ics")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_file(out, data, text=True)
    if d.get("open", True) and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(os.path.dirname(out))
    return h._send(200, {"ok": True, "path": out, "n": data.count("BEGIN:VEVENT")})


def _m84_r_ics(h, qs):
    return h._send(200, m84_ics(), "text/calendar; charset=utf-8")


HOOK_POST["/api/m84/termin"] = _m84_r_termin
HOOK_GET["/api/m84/termin"] = _m84_r_termin_get
HOOK_GET["/api/m84/raten"] = _m84_r_raten
HOOK_POST["/api/m84/fahrt"] = _m84_r_fahrt
HOOK_POST["/api/m84/zeit"] = _m84_r_zeit
HOOK_POST["/api/m84/stunde"] = _m84_r_stunde
HOOK_POST["/api/m84/cfg"] = _m84_r_cfg
HOOK_POST["/api/m84/export"] = _m84_r_export
HOOK_GET["/api/m84/ics"] = _m84_r_ics


def _m84_selftest():
    err = []
    try:
        if not q("SELECT id FROM kal_cal WHERE id=?", (M84_CAL_EIGEN,), one=True):
            err.append("m84: Kalender 'Eigene Termine' fehlt")
        d0 = datetime.date.today().isoformat()
        tid = x("INSERT INTO m84_termin (datum, von, bis, ganztags, titel, ort, uid) VALUES (?,?,?,?,?,?,?)", (d0, "09:00", "10:30", 0, "_ST_M84 Termin", "Köln", "st@m84"))
        cid = x("INSERT INTO customers (kdnr, firma, name, created) VALUES (?,?,?,?)", ("_ST_M84", "Kalenderprobe GmbH", "", now_iso()))
        iid, nr = save_invoice({"customer_id": cid, "kdnr": "_ST_M84", "addr": ["Kalenderprobe GmbH"], "datum": d0, "frist": 3, "typ": "rechnung",
                                "status": "offen", "items": [{"qty": 1, "name": "Test", "price": 10.0}]}, bump=False)
        bis = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
        evs = kal_events(d0, bis)
        if not any(e.get("uuid") == f"m84t-{tid}" for e in evs):
            err.append("m84: eigener Termin fehlt im Kalender")
        due = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        if not any(e.get("m84", {}).get("ref", {}).get("id") == iid and e["start"][:10] == due for e in evs):
            err.append("m84: Fälligkeit fehlt im Kalender")
        ics = m84_ics()
        if "BEGIN:VCALENDAR" not in ics or "_ST_M84 Termin" not in ics or f"Rechnung {nr}" not in ics:
            err.append("m84: ICS unvollständig")
        r = m84_raten("Inbetriebnahme Kalenderprobe GmbH", "Köln")
        if r["customer_id"] != cid:
            err.append("m84: Kunde nicht erraten")
        x("DELETE FROM items WHERE invoice_id=?", (iid,))
        x("DELETE FROM invoices WHERE id=?", (iid,))
        x("DELETE FROM customers WHERE id=?", (cid,))
        x("DELETE FROM m84_termin WHERE id=?", (tid,))
    except Exception as e:
        traceback.print_exc()
        err.append(f"m84 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m84_selftest)


# ============================================================================
# Teil aus m84b_timetree_schreiben.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m84b_timetree_schreiben  v1.0.0 (ab Programm v2.6.5; laedt nach m84)
# Termine aus dem Programm in TimeTree schreiben (anlegen, aendern, loeschen) - Gegenrichtung zu m29 (nur lesend).
# - Eigene Termine (m84_termin) bekommen ein Ziel: "nur im Programm" oder ein TimeTree-Kalender (+ Label).
# - Uebertragung ueber die TimeTree-Web-Schnittstelle (inoffiziell, gleiche Anmeldung wie m29). Es gibt keine
#   oeffentliche Beschreibung der Schreib-Aufrufe: das Modul probiert die bekannten Formen nacheinander, merkt sich
#   die funktionierende und PRUEFT jede Uebertragung, indem es TimeTree danach neu laedt. Erst wenn der Termin dort
#   gefunden wird, gilt er als "uebertragen". Sonst bleibt er im Programm (Status + Diagnose), nichts geht verloren.
# - Bestehende TimeTree-Termine (nicht wiederkehrend) koennen im Programm bearbeitet/geloescht werden.
# - Anmeldung: Rueckfall mit CSRF-Token (TimeTree verlangt das inzwischen teils), falls die alte Anmeldung scheitert.
# - Hintergrund: nicht uebertragene Termine werden alle 5 Minuten erneut versucht (max. 6 Versuche).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M48_VERSION = "1.0.0"
M48_WEB = "https://timetreeapp.com"
M48_LOCK = threading.RLock()
if os.environ.get("PA_TT_TEST_BASE"):          # test server only (never set in normal use)
    TT_API = os.environ["PA_TT_TEST_BASE"].rstrip("/") + "/api/v1"
    M48_WEB = os.environ["PA_TT_TEST_BASE"].rstrip("/")
M48_MAX_TRIES = 6
M48_STATUS = {"": "nur im Programm", "wartet": "wartet auf Übertragung", "gesendet": "übertragen - wird geprüft",
              "ok": "in TimeTree", "fehler": "nicht übertragen", "pruefen": "unklar - bitte in TimeTree prüfen",
              "loeschen": "wird in TimeTree gelöscht"}


def _m48_schema():
    for col, typ in (("tt_cal", "TEXT"), ("tt_uuid", "TEXT"), ("tt_label", "INTEGER"), ("tt_status", "TEXT"),
                     ("tt_fehler", "TEXT"), ("tt_tries", "INTEGER DEFAULT 0"), ("tt_sync", "TEXT")):
        try:
            x(f"ALTER TABLE m84_termin ADD COLUMN {col} {typ}")
        except Exception:
            pass


HOOK_SCHEMA.append(_m48_schema)


# ---------------------------------------------------------------------------
# HTTP with cookies + CSRF (m29's _tt_req only sends the session cookie)
# ---------------------------------------------------------------------------
M48_SESS = {"csrf": "", "cookies": {}, "zeit": 0}


def _m48_cookies_from(hd, jar):
    for hv in (hd.get_all("Set-Cookie") or []) if hd else []:
        c = http.cookies.SimpleCookie()
        try:
            c.load(hv)
        except Exception:
            continue
        for k, m in c.items():
            jar[k] = m.value
    return jar


def _m48_http(method, url, body=None, cookies=None, csrf="", timeout=25, accept="application/json"):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hd = {"Accept": accept, "Accept-Language": "de-DE,de;q=0.9",
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    if data is not None:
        hd["Content-Type"] = "application/json"
    if url.startswith(TT_API):
        hd["X-Timetreea"] = TT_UA
    if csrf:
        hd["X-CSRF-Token"] = csrf
    if cookies:
        hd["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req = urllib.request.Request(url, data=data, method=method, headers=hd)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, r.headers, raw
    except urllib.error.HTTPError as e:
        return e.code, e.headers, (e.read() or b"")
    except urllib.error.URLError as e:
        raise ValueError(f"TimeTree nicht erreichbar ({getattr(e, 'reason', e)}) - Internetverbindung prüfen.")
    except (socket.timeout, TimeoutError):
        raise ValueError("TimeTree antwortet nicht (Zeitüberschreitung).")


def _m48_js(raw):
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        return {"text": (raw or b"")[:300].decode("utf-8", "replace")}


def _m48_csrf_page(cookies):
    """GET a TimeTree web page and read <meta name="csrf-token">"""
    for path in ("/signin", "/"):
        try:
            st_, hd, raw = _m48_http("GET", M48_WEB + path, cookies=cookies, accept="text/html,application/xhtml+xml")
        except ValueError:
            continue
        _m48_cookies_from(hd, cookies)
        m = re.search(rb'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)', raw or b"", re.I) or \
            re.search(rb'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token', raw or b"", re.I)
        if m:
            return m.group(1).decode("utf-8", "replace")
    return ""


@chain_step("tt_login", "m84_kalender")
def _m84b_step_tt_login(_next, email, pw):
    """old login first (keeps working accounts unchanged); on failure the CSRF flow of the current TimeTree web page"""
    try:
        sid = _next(email, pw)
        M48_SESS.update(cookies={"_session_id": sid}, csrf="", zeit=time.time())
        return sid
    except ValueError as e0:
        if "zu viele" in str(e0):
            raise
        jar = {}
        csrf = _m48_csrf_page(jar)
        if not csrf:
            raise e0
        st_, hd, raw = _m48_http("PUT", TT_API + "/auth/email/signin", {"uid": email, "password": pw, "uuid": uuid.uuid4().hex},
                                 cookies=jar, csrf=csrf)
        _m48_cookies_from(hd, jar)
        if st_ != 200 or "_session_id" not in jar:
            raise e0
        M48_SESS.update(cookies=jar, csrf=csrf, zeit=time.time())
        return jar["_session_id"]


def _m48_session():
    email, pw, sess = _tt_creds()
    if not (email and pw):
        raise ValueError("Bitte zuerst E-Mail und Passwort deines TimeTree-Kontos eintragen (Kalender → Einstellungen).")
    if not sess:
        sess = tt_login(email, pw)
        set_setting("tt_session", protect_secret(sess))
    jar = dict(M48_SESS.get("cookies") or {})
    jar["_session_id"] = sess
    return email, pw, jar


def _m48_csrf(jar, force=False):
    if M48_SESS.get("csrf") and not force and time.time() - (M48_SESS.get("zeit") or 0) < 1800:
        return M48_SESS["csrf"]
    tok = _m48_csrf_page(jar)
    M48_SESS.update(csrf=tok, zeit=time.time(), cookies=dict(jar))
    return tok


def _m48_diag(entry):
    """last requests for the diagnosis view - never contains password or session"""
    d = list(get_settings().get("m48_diag") or [])
    d.append(dict(entry, zeit=now_iso()))
    set_setting("m48_diag", d[-12:])


def _m48_call(method, path, body):
    """write request with session renewal on 401/403 and CSRF (first without, then with fresh token on 422/419/403)"""
    email, pw, jar = _m48_session()
    csrf = M48_SESS.get("csrf") or ""
    tries = 0
    while True:
        tries += 1
        st_, hd, raw = _m48_http(method, TT_API + path, body, cookies=jar, csrf=csrf)
        _m48_cookies_from(hd, jar)
        js = _m48_js(raw)
        _m48_diag({"aufruf": f"{method} {path.split('?')[0]}", "http": st_, "antwort": json.dumps(js, ensure_ascii=False)[:500],
                   "csrf": bool(csrf)})
        if st_ == 401 and tries <= 2:
            sid = tt_login(email, pw)
            set_setting("tt_session", protect_secret(sid))
            jar = dict(M48_SESS.get("cookies") or {}, _session_id=sid)
            continue
        if st_ in (403, 419, 422) and tries <= 2:
            csrf = _m48_csrf(jar, force=True)
            if csrf:
                continue
        M48_SESS["cookies"] = jar
        return st_, js


# ---------------------------------------------------------------------------
# building the TimeTree event from an own appointment
# ---------------------------------------------------------------------------
def _m48_learn(cid):
    """defaults learned from existing events of this calendar (format of uuid, timezone, category, attendees, all-day style)"""
    rows = q("SELECT uuid, raw, all_day, start_ms, end_ms, start_tz FROM kal_event WHERE cal_id=? ORDER BY updated_ms DESC LIMIT 300", (cid,))
    out = {"dash": False, "tz": "Europe/Berlin", "category": 1, "type": 0, "attendees": [], "ad_tz": "UTC", "ad_incl": True,
           "label": None, "n": len(rows)}
    if not rows:
        return out
    out["dash"] = sum(1 for r in rows if "-" in (r["uuid"] or "")) > len(rows) / 2
    tzs = [r["start_tz"] for r in rows if r["start_tz"] and not r["all_day"]]
    if tzs:
        out["tz"] = max(set(tzs), key=tzs.count)
    cats, typs, labs = [], [], []
    for r in rows:
        try:
            e = json.loads(r["raw"] or "{}")
        except Exception:
            e = {}
        if not isinstance(e, dict) or e.get("recurrences"):
            continue
        if e.get("category") is not None:
            cats.append(e.get("category"))
        if e.get("type") is not None:
            typs.append(e.get("type"))
        lid = _ev_label(e)
        if lid is not None:
            labs.append(lid)
        if not out["attendees"] and isinstance(e.get("attendees"), list) and e["attendees"]:
            out["attendees"] = e["attendees"]
    if cats:
        out["category"] = max(set(cats), key=cats.count)
    if typs:
        out["type"] = max(set(typs), key=typs.count)
    if labs:
        out["label"] = max(set(labs), key=labs.count)
    ad = [r for r in rows if r["all_day"]]
    if ad:
        tz_ad = [r["start_tz"] for r in ad if r["start_tz"]]
        if tz_ad:
            out["ad_tz"] = max(set(tz_ad), key=tz_ad.count)
        # single-day all-day events: end == start -> inclusive end day, end == start + 1 day -> exclusive
        incl = sum(1 for r in ad if (r["end_ms"] or 0) == (r["start_ms"] or 0))
        excl = sum(1 for r in ad if (r["end_ms"] or 0) - (r["start_ms"] or 0) == 86400000)
        out["ad_incl"] = incl >= excl
    return out


def _m48_utc_midnight_ms(d):
    return int((datetime.datetime(d.year, d.month, d.day) - datetime.datetime(1970, 1, 1)).total_seconds() * 1000)


def m48_build(t, cid, uuid_=None, base=None):
    L = _m48_learn(cid)
    d0 = datetime.date.fromisoformat(t["datum"][:10])
    d1 = datetime.date.fromisoformat((t["bis_datum"] or t["datum"])[:10])
    ad = bool(t["ganztags"]) or not t["von"]
    if ad:
        tz = L["ad_tz"] or "UTC"
        if tz == "UTC":
            s_ms = _m48_utc_midnight_ms(d0)
            e_ms = _m48_utc_midnight_ms(d1 if L["ad_incl"] else d1 + datetime.timedelta(days=1))
        else:
            s_ms = local_to_ms(datetime.datetime(d0.year, d0.month, d0.day))
            e_ms = local_to_ms(datetime.datetime(d1.year, d1.month, d1.day) + (datetime.timedelta(days=0 if L["ad_incl"] else 1)))
    else:
        tz = L["tz"] or "Europe/Berlin"
        h0, m0 = [int(v) for v in t["von"].split(":")]
        bis = t["bis"] or t["von"]
        h1, m1 = [int(v) for v in bis.split(":")]
        s_dt = datetime.datetime(d0.year, d0.month, d0.day, h0, m0)
        e_dt = datetime.datetime(d1.year, d1.month, d1.day, h1, m1)
        if e_dt <= s_dt:
            e_dt = s_dt + datetime.timedelta(hours=1)
        s_ms, e_ms = local_to_ms(s_dt), local_to_ms(e_dt)
    ev = dict(base or {})
    for k in ("deactivated_at", "deleted_at", "updated_at", "created_at", "relationships"):
        ev.pop(k, None)
    if not uuid_:
        uuid_ = str(uuid.uuid4()) if L["dash"] else uuid.uuid4().hex
    lid = t.get("tt_label")
    if lid in (None, ""):
        lid = ev.get("label_id") if ev.get("label_id") is not None else L["label"]
        if lid is None:
            r = q("SELECT label_id FROM kal_label WHERE cal_id=? ORDER BY label_id LIMIT 1", (cid,), one=True)
            lid = r["label_id"] if r else 1
    ev.update({"uuid": uuid_, "title": (t["titel"] or "")[:200], "all_day": ad, "start_at": s_ms, "start_timezone": tz,
               "end_at": e_ms, "end_timezone": tz, "label_id": int(lid), "note": t["notiz"] or "", "location": t["ort"] or ""})
    ev.setdefault("category", L["category"])
    ev.setdefault("type", L["type"])
    ev.setdefault("url", "")
    ev.setdefault("recurrences", [])
    ev.setdefault("alerts", [])
    ev.setdefault("attendees", L["attendees"])
    ev.setdefault("file_uuids", [])
    ev.setdefault("parent_id", None)
    return ev


def _m48_tt_id(cid):
    return str(cid).split(":", 1)[1] if str(cid).startswith("tt:") else str(cid)


# variants of the (undocumented) write calls; the working one is remembered in settings "m48_var"
def _m48_variants(kind, tid, uid=None):
    c = f"/calendar/{tid}"
    if kind == "create":
        return [("POST", c + "/event", "plain"), ("POST", c + "/event", "wrap"), ("POST", c + "/events", "plain")]
    if kind == "update":
        return [("PUT", c + f"/event/{uid}", "plain"), ("PUT", c + f"/event/{uid}", "wrap"), ("PATCH", c + f"/event/{uid}", "plain")]
    return [("DELETE", c + f"/event/{uid}", "none")]


def _m48_send(kind, cid, ev=None, uid=None):
    """-> (ok, response_json, message)"""
    tid = _m48_tt_id(cid)
    vs = _m48_variants(kind, tid, uid)
    known = (get_settings().get("m48_var") or {}).get(kind)
    if known is not None and 0 <= int(known) < len(vs):
        vs = [vs[int(known)]] + [v for i, v in enumerate(vs) if i != int(known)]
    last = ""
    for method, path, form in vs:
        body = None if form == "none" else ({"event": ev} if form == "wrap" else ev)
        st_, js = _m48_call(method, path, body)
        if 200 <= st_ < 300 or (kind == "delete" and st_ == 404):
            allv = dict(get_settings().get("m48_var") or {})
            allv[kind] = _m48_variants(kind, tid, uid).index((method, path, form))
            set_setting("m48_var", allv)
            return True, js, ""
        err = js.get("error") if isinstance(js, dict) else None
        msg = (err.get("message") if isinstance(err, dict) else err) or (js.get("text") if isinstance(js, dict) else "") or ""
        last = f"HTTP {st_}" + (f": {str(msg)[:160]}" if msg else "")
        if st_ in (401,):
            break
        if st_ in (400, 422) and kind != "create":
            continue
    return False, {}, last or "keine Antwort"


def _m48_resp_uuid(js, fallback):
    if isinstance(js, dict):
        for k in ("event", "data"):
            v = js.get(k)
            if isinstance(v, dict) and (v.get("uuid") or v.get("id")):
                return str(v.get("uuid") or v.get("id"))
        if js.get("uuid"):
            return str(js["uuid"])
    return fallback


# ---------------------------------------------------------------------------
# push / verify
# ---------------------------------------------------------------------------
def _m48_set(tid, **kw):
    cols = ", ".join(f"{k}=?" for k in kw)
    x(f"UPDATE m84_termin SET {cols} WHERE id=?", tuple(kw.values()) + (int(tid),))


def _m48_found(cid, uid, t=None):
    if uid and q("SELECT 1 FROM kal_event WHERE cal_id=? AND uuid=?", (cid, uid), one=True):
        return uid
    if t:
        # server may assign its own id: same title and same start
        ev = m48_build(t, cid, uid or "x")
        r = q("SELECT uuid FROM kal_event WHERE cal_id=? AND title=? AND start_ms=?", (cid, ev["title"], ev["start_at"]), one=True)
        if r:
            return r["uuid"]
    return None


def m48_push(tid, verify=True):
    """send one own appointment to TimeTree (create/update/delete) and verify it by reloading TimeTree"""
    with M48_LOCK:
        t = q("SELECT * FROM m84_termin WHERE id=?", (int(tid),), one=True)
        if not t or not t.get("tt_cal"):
            return {"ok": True, "status": ""}
        cid = t["tt_cal"]
        if not q("SELECT 1 FROM kal_cal WHERE id=? AND quelle='timetree'", (cid,), one=True):
            _m48_set(tid, tt_status="fehler", tt_fehler="TimeTree-Kalender nicht (mehr) vorhanden - bitte Kalender abrufen.")
            return {"ok": False, "status": "fehler", "fehler": "TimeTree-Kalender nicht vorhanden."}
        tries = int(t.get("tt_tries") or 0) + 1
        try:
            if t.get("tt_status") == "loeschen":
                ok, js, msg = _m48_send("delete", cid, uid=t["tt_uuid"]) if t.get("tt_uuid") else (True, {}, "")
                if not ok:
                    _m48_set(tid, tt_fehler=f"Löschen in TimeTree fehlgeschlagen ({msg})", tt_tries=tries)
                    return {"ok": False, "status": "loeschen", "fehler": msg}
                x("DELETE FROM m84_termin WHERE id=?", (int(tid),))
                if t.get("tt_uuid"):
                    x("DELETE FROM kal_event WHERE cal_id=? AND uuid=?", (cid, t["tt_uuid"]))
                _m48_bg_sync()
                return {"ok": True, "status": "geloescht"}
            base = None
            if t.get("tt_uuid"):
                r = q("SELECT raw FROM kal_event WHERE cal_id=? AND uuid=?", (cid, t["tt_uuid"]), one=True)
                try:
                    base = json.loads(r["raw"]) if r and r["raw"] else None
                except Exception:
                    base = None
                if base and base.get("recurrences"):
                    _m48_set(tid, tt_status="fehler", tt_fehler="Wiederkehrender TimeTree-Termin - bitte direkt in TimeTree ändern.")
                    return {"ok": False, "status": "fehler", "fehler": "Wiederkehrende Termine bitte in TimeTree ändern."}
            # update when TimeTree already has it (by uuid, or same title+start after a sent-but-unconfirmed create), else create
            kind = "create"
            if t.get("tt_uuid"):
                if base:
                    kind = "update"
                else:
                    found = _m48_found(cid, t["tt_uuid"], t)
                    if found:
                        t = dict(t, tt_uuid=found)
                        _m48_set(tid, tt_uuid=found)
                        kind = "update"
            ev = m48_build(t, cid, t.get("tt_uuid") if kind == "update" else None, base if kind == "update" else None)
            ok, js, msg = _m48_send(kind, cid, ev, uid=t.get("tt_uuid"))
            if not ok:
                _m48_set(tid, tt_status="fehler", tt_fehler=f"TimeTree hat abgelehnt ({msg})", tt_tries=tries)
                return {"ok": False, "status": "fehler", "fehler": msg}
            uid = _m48_resp_uuid(js, ev["uuid"])
            _m48_set(tid, tt_uuid=uid, tt_status="gesendet", tt_fehler="", tt_tries=tries, tt_sync=now_iso())
        except ValueError as e:
            _m48_set(tid, tt_status="fehler", tt_fehler=str(e)[:300], tt_tries=tries)
            return {"ok": False, "status": "fehler", "fehler": str(e)}
    if verify:
        return m48_verify([int(tid)])
    return {"ok": True, "status": "gesendet"}


def m48_verify(ids=None):
    """reload TimeTree, then check every sent appointment"""
    try:
        tt_sync()
    except ValueError as e:
        if "gerade abgerufen" in str(e):
            time.sleep(3)
            try:
                tt_sync()
            except ValueError:
                pass
    res = {"ok": True, "status": "ok", "geprueft": 0}
    rows = q("SELECT * FROM m84_termin WHERE tt_status='gesendet'" + (f" AND id IN ({','.join('?' * len(ids))})" if ids else ""),
             tuple(ids or ()))
    for t in rows:
        uid = _m48_found(t["tt_cal"], t["tt_uuid"], t)
        res["geprueft"] += 1
        if uid:
            _m48_set(t["id"], tt_uuid=uid, tt_status="ok", tt_fehler="")
        else:
            _m48_set(t["id"], tt_status="pruefen", tt_fehler="TimeTree hat den Auftrag angenommen, der Termin ist beim Neuladen aber nicht zu finden.")
            res.update(ok=False, status="pruefen", fehler="Termin nach dem Übertragen in TimeTree nicht gefunden.")
    return res


_M48_BG = {"t": None}


def _m48_bg_sync():
    def run():
        try:
            tt_sync()
        except Exception:
            pass
    if not KAL_STATE.get("laeuft"):
        threading.Thread(target=run, daemon=True).start()


def _m48_loop():
    time.sleep(90)
    while True:
        try:
            ids = [r["id"] for r in q("SELECT id FROM m84_termin WHERE tt_cal IS NOT NULL AND tt_cal<>'' AND tt_status IN ('wartet','fehler','loeschen') "
                                      "AND COALESCE(tt_tries,0)<?", (M48_MAX_TRIES,))]
            email, pw, _ = _tt_creds()
            if ids and email and pw:
                for i in ids:
                    m48_push(i, verify=False)
                if q("SELECT 1 FROM m84_termin WHERE tt_status='gesendet' LIMIT 1", one=True):
                    m48_verify()
        except Exception:
            traceback.print_exc()
        time.sleep(300)


HOOK_START.append(_m48_loop)


# ---------------------------------------------------------------------------
# display: synced appointments come from TimeTree itself - hide the program copy, show status of the others
# ---------------------------------------------------------------------------
@chain_step("m84_termine", "m84_kalender")
def _m84b_step_m84_termine(_next, von, bis):
    out = []
    for t in _next(von, bis):
        if t.get("tt_cal") and t.get("tt_status") in ("ok", "gesendet", "pruefen", "loeschen") and t.get("tt_uuid") and \
                q("SELECT 1 FROM kal_event WHERE cal_id=? AND uuid=?", (t["tt_cal"], t["tt_uuid"]), one=True):
            continue
        if t.get("tt_status") == "loeschen":
            continue
        out.append(t)
    return out


@chain_step("kal_events", "m84_kalender")
def _m84b_step_kal_events(_next, von, bis, qtext="", alle=False):
    out = _next(von, bis, qtext, alle)
    try:
        links = {(r["tt_cal"], r["tt_uuid"]): r for r in q("SELECT id, tt_cal, tt_uuid, tt_status FROM m84_termin WHERE tt_uuid IS NOT NULL AND tt_uuid<>''")}
        stat = {r["id"]: r for r in q("SELECT id, tt_cal, tt_status, tt_fehler FROM m84_termin WHERE tt_cal IS NOT NULL AND tt_cal<>''")}
        cals = {r["id"]: r["name"] for r in q("SELECT id, name FROM kal_cal WHERE quelle='timetree'")}
        for e in out:
            cid = e.get("cal_id") or ""
            if str(cid).startswith("tt:"):
                ln = links.get((cid, e.get("uuid")))
                e["m48"] = {"tt": True, "cal": cid, "uuid": e.get("uuid"), "edit": not e.get("wdh"), "termin_id": ln["id"] if ln else None}
            elif (e.get("m84") or {}).get("kind") == "termin":
                s_ = stat.get((e["m84"] or {}).get("id"))
                if s_:
                    e["m48"] = {"status": s_["tt_status"] or "wartet", "text": M48_STATUS.get(s_["tt_status"] or "wartet", ""),
                                "fehler": s_["tt_fehler"] or "", "ziel": cals.get(s_["tt_cal"], "TimeTree")}
                    if s_["tt_status"] in ("fehler", "pruefen", "wartet"):
                        e["title"] = ("⚠ " if s_["tt_status"] != "wartet" else "⏳ ") + e["title"]
    except Exception:
        traceback.print_exc()
    return out


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
def m48_ziele():
    cals = q("SELECT id, name, farbe FROM kal_cal WHERE quelle='timetree' ORDER BY name")
    labs = {}
    for r in q("SELECT cal_id, label_id, name, farbe FROM kal_label ORDER BY cal_id, label_id"):
        labs.setdefault(r["cal_id"], []).append({"id": r["label_id"], "name": r["name"] or f"Label {r['label_id']}", "farbe": r["farbe"]})
    email, pw, _ = _tt_creds()
    return {"ok": True, "kalender": [dict(c, labels=labs.get(c["id"], [])) for c in cals], "zugang": bool(email and pw),
            "standard": get_settings().get("m48_ziel") or "", "diag": (get_settings().get("m48_diag") or [])[-12:],
            "status_texte": M48_STATUS}


def _m48_r_termin(h, d):
    """wraps /api/m84/termin: target calendar + push; delete of linked appointments goes through TimeTree"""
    if d.get("delete"):
        ids = [int(i) for i in (d.get("ids") or [d.get("id")]) if i]
        res = {"ok": True, "fehler": []}
        for i in ids:
            t = q("SELECT * FROM m84_termin WHERE id=?", (i,), one=True)
            if t and t.get("tt_cal") and t.get("tt_uuid") and t.get("tt_status") in ("ok", "gesendet", "pruefen", "fehler", "loeschen"):
                _m48_set(i, tt_status="loeschen", tt_tries=0)
                r = m48_push(i, verify=False)
                if not r.get("ok"):
                    res["fehler"].append(r.get("fehler") or "")
            else:
                x("DELETE FROM m84_termin WHERE id=?", (i,))
        if res["fehler"]:
            res.update(ok=True, warnung="In TimeTree noch nicht gelöscht - wird automatisch erneut versucht: " + res["fehler"][0])
        return h._send(200, res)
    ziel = d.get("tt_cal")
    if ziel is not None:
        set_setting("m48_ziel", ziel or "")
    # original save (validation, insert/update) - capture its answer
    cap = {}

    class _H:
        def _send(self, code, obj, *a, **k):
            cap["code"], cap["obj"] = code, obj
    _m48_orig_route(_H(), d)
    r = cap.get("obj") or {}
    if not r.get("ok"):
        return h._send(cap.get("code") or 200, r)
    tid = r["id"]
    old = q("SELECT tt_cal, tt_uuid, tt_status FROM m84_termin WHERE id=?", (tid,), one=True) or {}
    if ziel is not None:
        if ziel and not str(ziel).startswith("tt:"):
            raise ValueError("Unbekannter Kalender.")
        if old.get("tt_cal") and old.get("tt_uuid") and (ziel or "") != old["tt_cal"]:
            # moved to another calendar / back to program only: delete the TimeTree copy first
            st_ = old.get("tt_status")
            _m48_set(tid, tt_status="loeschen", tt_tries=0)
            rr = m48_push_delete_only(tid, old["tt_cal"], old["tt_uuid"])
            if not rr.get("ok"):
                _m48_set(tid, tt_status=st_)
                raise ValueError("Der Termin konnte in TimeTree nicht entfernt werden: " + (rr.get("fehler") or ""))
            _m48_set(tid, tt_uuid=None)
        lab = d.get("tt_label")
        keep = bool(ziel) and old.get("tt_cal") == ziel and old.get("tt_uuid")
        _m48_set(tid, tt_cal=ziel or None, tt_label=int(lab) if str(lab or "").strip().lstrip("-").isdigit() else None,
                 tt_status=((old.get("tt_status") if old.get("tt_status") not in ("fehler", "loeschen", None, "") else "ok") if keep
                            else ("wartet" if ziel else "")), tt_fehler="", tt_tries=0)
    elif old.get("tt_cal"):
        _m48_set(tid, tt_status="wartet" if not old.get("tt_uuid") else (old.get("tt_status") if old.get("tt_status") != "fehler" else "ok"),
                 tt_tries=0)
    t = q("SELECT tt_cal FROM m84_termin WHERE id=?", (tid,), one=True)
    out = {"ok": True, "id": tid}
    if t and t["tt_cal"]:
        p = m48_push(tid)
        st_ = q("SELECT tt_status, tt_fehler FROM m84_termin WHERE id=?", (tid,), one=True) or {}
        out.update(tt_status=st_.get("tt_status"), tt_text=M48_STATUS.get(st_.get("tt_status") or "", ""), tt_fehler=st_.get("tt_fehler") or "")
    return h._send(200, out)


def m48_push_delete_only(tid, cid, uid):
    try:
        ok, js, msg = _m48_send("delete", cid, uid=uid)
    except ValueError as e:
        return {"ok": False, "fehler": str(e)}
    if ok:
        x("DELETE FROM kal_event WHERE cal_id=? AND uuid=?", (cid, uid))
    return {"ok": ok, "fehler": msg}


def m48_uebernehmen(d):
    """edit an existing TimeTree event in the program: create/return the linked own appointment"""
    cid, uid = d.get("cal_id"), d.get("uuid")
    ln = q("SELECT id FROM m84_termin WHERE tt_cal=? AND tt_uuid=?", (cid, uid), one=True)
    if ln:
        return {"ok": True, "id": ln["id"]}
    e = q("SELECT * FROM kal_event WHERE cal_id=? AND uuid=?", (cid, uid), one=True)
    if not e:
        raise ValueError("Termin nicht gefunden - bitte Kalender neu abrufen.")
    try:
        raw = json.loads(e["raw"] or "{}")
    except Exception:
        raw = {}
    if raw.get("recurrences") or (e["rec"] or "[]") not in ("[]", "", "null"):
        raise ValueError("Wiederkehrende Termine bitte direkt in TimeTree ändern.")
    s_ = ms_to_local(e["start_ms"], e["start_tz"], bool(e["all_day"]))
    en = ms_to_local(e["end_ms"], e["end_tz"], bool(e["all_day"]))
    if e["all_day"]:
        bisd = en.date()
        if bisd > s_.date() and not _m48_learn(cid)["ad_incl"]:
            bisd = bisd - datetime.timedelta(days=1)
        vals = (s_.date().isoformat(), bisd.isoformat() if bisd > s_.date() else "", "", "", 1)
    else:
        vals = (s_.date().isoformat(), en.date().isoformat() if en.date() > s_.date() else "", s_.strftime("%H:%M"), en.strftime("%H:%M"), 0)
    tid = x("INSERT INTO m84_termin (datum, bis_datum, von, bis, ganztags, titel, ort, notiz, uid, created, updated, tt_cal, tt_uuid, tt_label, tt_status, tt_tries) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
            vals + ((e["title"] or "")[:200], (e["location"] or "")[:200], (e["note"] or "")[:4000], uuid.uuid4().hex + "@pa-rechnung",
                    now_iso(), now_iso(), cid, uid, e["label_id"], "ok"))
    return {"ok": True, "id": tid}


def m48_retry(d):
    ids = [int(i) for i in (d.get("ids") or [d.get("id")]) if i]
    out = []
    for i in ids:
        _m48_set(i, tt_tries=0)
        t = q("SELECT tt_status FROM m84_termin WHERE id=?", (i,), one=True) or {}
        if t.get("tt_status") == "pruefen":
            _m48_set(i, tt_status="gesendet")
            out.append(m48_verify([i]))
        else:
            out.append(m48_push(i))
    st_ = [q("SELECT id, tt_status, tt_fehler FROM m84_termin WHERE id=?", (i,), one=True) for i in ids]
    return {"ok": True, "termine": [s for s in st_ if s]}


_m48_orig_route = HOOK_POST["/api/m84/termin"]
HOOK_POST["/api/m84/termin"] = _m48_r_termin
HOOK_GET["/api/m48/ziele"] = lambda h, qs: h._send(200, m48_ziele())
HOOK_POST["/api/m48/uebernehmen"] = lambda h, d: h._send(200, m48_uebernehmen(d))
HOOK_POST["/api/m48/retry"] = lambda h, d: h._send(200, m48_retry(d))
HOOK_POST["/api/m48/diag_clear"] = lambda h, d: (set_setting("m48_diag", []), h._send(200, {"ok": True}))[1]


def _m48_boot(d):
    try:
        n = q("SELECT COUNT(*) n FROM m84_termin WHERE tt_status IN ('fehler','pruefen')", one=True)["n"]
        d["m48"] = {"probleme": n}
    except Exception:
        pass


HOOK_BOOT.append(_m48_boot)


def m48_selftest():
    err = []
    try:
        # build: timed event in Europe/Berlin, all-day inclusive end
        t = {"datum": "2026-03-10", "bis_datum": "", "von": "09:30", "bis": "11:00", "ganztags": 0, "titel": "Test", "ort": "Köln", "notiz": "",
             "tt_label": 3}
        ev = m48_build(t, "tt:selftest-none")
        if ev["end_at"] - ev["start_at"] != 90 * 60000 or ev["all_day"] or ev["label_id"] != 3 or not ev["uuid"]:
            err.append(f"m48: Termin falsch gebaut ({ev['start_at']} {ev['end_at']})")
        t2 = dict(t, ganztags=1, von="", bis="", bis_datum="2026-03-12")
        ev2 = m48_build(t2, "tt:selftest-none")
        if not ev2["all_day"] or ev2["end_at"] - ev2["start_at"] != 2 * 86400000 or ev2["start_timezone"] != "UTC":
            err.append("m48: Ganztags-Termin falsch gebaut")
        if _m48_variants("create", "1")[0] != ("POST", "/calendar/1/event", "plain"):
            err.append("m48: Varianten falsch")
        if _m48_resp_uuid({"event": {"uuid": "abc"}}, "x") != "abc" or _m48_resp_uuid({}, "x") != "x":
            err.append("m48: Antwort-UUID falsch gelesen")
        m = re.search(rb'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)', b'<meta name="csrf-token" content="T0K3N==">', re.I)
        if not m or m.group(1) != b"T0K3N==":
            err.append("m48: CSRF-Token wird nicht gelesen")
    except Exception as e:
        err.append(f"m48 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m48_selftest)
print(f"INIT m84b_timetree_schreiben v{M48_VERSION}")


# ============================================================================
# Teil aus m84c_kurstermine.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m84c_kurstermine  v1.0.0 (ab Programm v2.6.5; laedt nach m08, m18 und m84)
# Kurstermine: ein Kurs kann Termine haben, auch wenn noch kein Teilnehmer eingetragen ist.
# - Tabelle kurs_termine (Kurs, Datum, von/bis, Notiz). Klick auf die Kurszeile im Unterricht legt ohne Teilnehmer
#   einen Kurstermin an (vorher: Fehlermeldung "Der Kurs hat noch keine Teilnehmer"); mit Teilnehmern wie bisher
#   (Stunde je Teilnehmer) und zusaetzlich der Kurstermin.
# - Teilnehmer spaeter hinzufuegen: bisherige Kurstermine werden auf Wunsch nachgetragen (alle / ab heute / keine);
#   abgerechnete Stunden bleiben unberuehrt, nichts wird doppelt angelegt.
# - Kalender: Kurstermine erscheinen unter "Programm-Termine" (Art "Kurstermine"); aus einem Kalendertermin
#   "Unterrichtsstunde" geht jetzt auch nur mit Kurs (ohne Schueler) -> Kurstermin.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M84C_VERSION = "1.0.0"


def _m84c_schema():
    x("CREATE TABLE IF NOT EXISTS kurs_termine (id INTEGER PRIMARY KEY, kurs_id INTEGER, datum TEXT, von TEXT, bis TEXT, notiz TEXT, "
      "created TEXT, UNIQUE(kurs_id, datum))")
    x("CREATE INDEX IF NOT EXISTS ix_kurs_termine_d ON kurs_termine(datum)")
    # existing course days (lessons of all members) become course dates once
    if not get_settings().get("m84c_migriert"):
        try:
            for r in q("SELECT DISTINCT kurs_id, datum FROM lessons WHERE kurs_id IS NOT NULL AND COALESCE(datum,'')<>''"):
                x("INSERT OR IGNORE INTO kurs_termine (kurs_id, datum, von, bis, notiz, created) VALUES (?,?,?,?,?,?)",
                  (r["kurs_id"], r["datum"][:10], "", "", "", now_iso()))
        except Exception:
            traceback.print_exc()
        set_setting("m84c_migriert", now_iso())
    # course dates appear in the calendar ("Programm-Termine") - switch the new kind on once for existing settings
    try:
        cfg = get_settings().get("m84_ics")
        if isinstance(cfg, dict) and isinstance(cfg.get("arten"), list) and "kurs" not in cfg["arten"] and not get_settings().get("m84c_kal"):
            cfg = dict(cfg, arten=cfg["arten"] + ["kurs"])
            set_setting("m84_ics", cfg)
        set_setting("m84c_kal", 1)
    except Exception:
        traceback.print_exc()


HOOK_SCHEMA.append(_m84c_schema)

M84_ARTEN["kurs"] = "Kurstermine (Unterricht)"
if "kurs" not in M84_DEFAULT["arten"]:
    M84_DEFAULT["arten"] = list(M84_DEFAULT["arten"]) + ["kurs"]


def _m84c_date(v):
    v = (v or "")[:10]
    try:
        datetime.date.fromisoformat(v)
    except Exception:
        raise ValueError("Datum fehlt oder ist ungültig.")
    return v


def _m84c_members(kid):
    return [m["student_id"] for m in q("SELECT student_id FROM kurs_members WHERE kurs_id=?", (int(kid),))]


def _m84c_lessons_for(kid, datum, sids, dauer=None):
    n = 0
    for sid in sids:
        if not q("SELECT id FROM lessons WHERE student_id=? AND datum=? AND COALESCE(kurs_id,0)=?", (sid, datum, int(kid)), one=True):
            x("INSERT INTO lessons (student_id, datum, dauer, status, notiz, kurs_id) VALUES (?,?,?,?,?,?)",
              (sid, datum, dauer, "stattgefunden", "", int(kid)))
            n += 1
    return n


def m84c_termin_set(d):
    """create/update a course date (+ lessons for current members) or delete it (+ not invoiced lessons of that day)"""
    kid = int(d["kurs_id"])
    if not q("SELECT id FROM kurse WHERE id=?", (kid,), one=True):
        raise ValueError("Kurs nicht gefunden.")
    datum = _m84c_date(d.get("datum"))
    if d.get("delete"):
        x("DELETE FROM kurs_termine WHERE kurs_id=? AND datum=?", (kid, datum))
        n = 0
        for l in q("SELECT id, invoice_id FROM lessons WHERE kurs_id=? AND datum=?", (kid, datum)):
            if not l["invoice_id"]:
                x("DELETE FROM lessons WHERE id=?", (l["id"],))
                n += 1
        return {"ok": True, "state": None, "n": n}
    von = _m84_hm(d.get("von"), "Beginn") if d.get("von") else ""
    bis = _m84_hm(d.get("bis"), "Ende") if d.get("bis") else ""
    notiz = (d.get("notiz") or "")[:300]
    if q("SELECT id FROM kurs_termine WHERE kurs_id=? AND datum=?", (kid, datum), one=True):
        x("UPDATE kurs_termine SET von=?, bis=?, notiz=? WHERE kurs_id=? AND datum=?", (von, bis, notiz, kid, datum))
    else:
        x("INSERT INTO kurs_termine (kurs_id, datum, von, bis, notiz, created) VALUES (?,?,?,?,?,?)", (kid, datum, von, bis, notiz, now_iso()))
    dauer = None
    if von and bis and bis > von:
        h0, m0 = [int(v) for v in von.split(":")]
        h1, m1 = [int(v) for v in bis.split(":")]
        dauer = round(((h1 * 60 + m1) - (h0 * 60 + m0)) / 60, 2)
    if d.get("dauer"):
        try:
            dauer = float(str(d["dauer"]).replace(",", "."))
        except ValueError:
            pass
    n = _m84c_lessons_for(kid, datum, _m84c_members(kid), dauer)
    return {"ok": True, "state": "termin", "n": n}


@chain_step("kurs_toggle_day", "m84_kalender")
def _m84c_step_kurs_toggle_day(_next, kid, datum):
    """course row click: without members -> course date only; with members -> as before plus the course date"""
    datum = _m84c_date(datum)
    if not _m84c_members(kid):
        if q("SELECT id FROM kurs_termine WHERE kurs_id=? AND datum=?", (int(kid), datum), one=True):
            x("DELETE FROM kurs_termine WHERE kurs_id=? AND datum=?", (int(kid), datum))
            return {"state": None, "n": 0, "termin": False}
        x("INSERT INTO kurs_termine (kurs_id, datum, von, bis, notiz, created) VALUES (?,?,?,?,?,?)", (int(kid), datum, "", "", "", now_iso()))
        return {"state": "termin", "n": 0, "termin": True}
    r = _next(kid, datum)
    if r.get("state"):
        x("INSERT OR IGNORE INTO kurs_termine (kurs_id, datum, von, bis, notiz, created) VALUES (?,?,?,?,?,?)", (int(kid), datum, "", "", "", now_iso()))
    else:
        x("DELETE FROM kurs_termine WHERE kurs_id=? AND datum=?", (int(kid), datum))
    return r


@chain_step("lesson_month", "m84_kalender")
def _m84c_step_lesson_month(_next, year, month, customer_id=None):
    r = _next(year, month, customer_id)
    ym = f"{int(year):04d}-{int(month):02d}"
    r["kurs_termine"] = q("SELECT * FROM kurs_termine WHERE substr(datum,1,7)=? ORDER BY datum", (ym,))
    return r


def m84c_add_members(d):
    """/api/kurs/add (same as before) + fill in the existing course dates for the new members"""
    kid = int(d["kurs_id"])
    k = q("SELECT * FROM kurse WHERE id=?", (kid,), one=True)
    if not k:
        raise ValueError("Kurs nicht gefunden.")
    sids = [int(v) for v in d.get("student_ids") or []]
    for cid in d.get("customer_ids") or []:
        sids.append(student_for_customer(int(cid), None, None if k["customer_id"] else int(cid)))
    neu = []
    for sid in sids:
        if not q("SELECT id FROM kurs_members WHERE kurs_id=? AND student_id=?", (kid, sid), one=True):
            neu.append(sid)
        x("INSERT OR IGNORE INTO kurs_members (kurs_id, student_id, seit) VALUES (?,?,?)", (kid, sid, today()))
    mode = d.get("nachtragen") or "keine"
    n_nach = 0
    if neu and mode in ("alle", "ab_heute"):
        sql = "SELECT * FROM kurs_termine WHERE kurs_id=?" + (" AND datum>=?" if mode == "ab_heute" else "")
        for t in q(sql, (kid, today()) if mode == "ab_heute" else (kid,)):
            dauer = None
            if t["von"] and t["bis"] and t["bis"] > t["von"]:
                h0, m0 = [int(v) for v in t["von"].split(":")]
                h1, m1 = [int(v) for v in t["bis"].split(":")]
                dauer = round(((h1 * 60 + m1) - (h0 * 60 + m0)) / 60, 2)
            n_nach += _m84c_lessons_for(kid, t["datum"], neu, dauer)
    return {"ok": True, "n": len(sids), "nachgetragen": n_nach}


def m84c_info(kid):
    kid = int(kid)
    ts = q("SELECT datum FROM kurs_termine WHERE kurs_id=? ORDER BY datum", (kid,))
    return {"ok": True, "termine": len(ts), "ab_heute": sum(1 for t in ts if t["datum"] >= today()),
            "erster": ts[0]["datum"] if ts else "", "letzter": ts[-1]["datum"] if ts else ""}


def _m84c_kal(von, bis):
    out = []
    for t in q("SELECT t.*, k.name FROM kurs_termine t JOIN kurse k ON k.id=t.kurs_id WHERE t.datum BETWEEN ? AND ? ORDER BY t.datum", (von, bis)):
        n = len(_m84c_members(t["kurs_id"]))
        zeit = f"{t['von']}–{t['bis']} " if t["von"] else ""
        out.append({"datum": t["datum"], "titel": f"Kurs: {t['name']}", "notiz": f"{zeit}{n} Teilnehmer" + (f" · {t['notiz']}" if t["notiz"] else ""),
                    "ort": "", "ref": {"kind": "school", "id": t["kurs_id"]}})
    return out


M84_QUELLEN["kurs"] = ("Kurstermine (Unterricht)", _m84c_kal)

_m84c_orig_stunde = HOOK_POST.get("/api/m84/stunde")


def _m84c_r_stunde(h, d):
    """calendar -> 'Unterrichtsstunde': without pupil but with a course -> course date (+ lessons for its members)"""
    if not d.get("student_id") and d.get("kurs_id"):
        r = m84c_termin_set({"kurs_id": d["kurs_id"], "datum": d.get("datum"), "von": d.get("von"), "bis": d.get("bis"),
                             "dauer": d.get("dauer"), "notiz": d.get("notiz")})
        return h._send(200, dict(r, kurstermin=True))
    return _m84c_orig_stunde(h, d)


HOOK_POST["/api/m84/stunde"] = _m84c_r_stunde
HOOK_POST["/api/kurs/add"] = lambda h, d: h._send(200, m84c_add_members(d))
HOOK_POST["/api/kurs/termin"] = lambda h, d: h._send(200, m84c_termin_set(d))
HOOK_GET["/api/kurs/termine_info"] = lambda h, qs: h._send(200, m84c_info(qs.get("kurs_id") or 0))


def _m84c_cleanup_delete(h, d):
    """deleting a course also removes its course dates (the m18 route keeps doing the rest)"""
    try:
        x("DELETE FROM kurs_termine WHERE kurs_id=?", (int(d.get("id") or 0),))
    except Exception:
        traceback.print_exc()
    return None


@chain_step("ext_post", "m84_kalender")
def _m84c_step_ext_post(_next, h, p, d):
    if p == "/api/kurs/delete":
        _m84c_cleanup_delete(h, d)
    return _next(h, p, d)


def m84c_selftest():
    err = []
    try:
        kid = x("INSERT INTO kurse (name, modus, dauer, aktiv) VALUES (?,?,?,?)", ("_m84c_test", "stunde", 1, 1))
        try:
            r = kurs_toggle_day(kid, "2026-03-03")
            if r.get("state") != "termin" or not q("SELECT 1 FROM kurs_termine WHERE kurs_id=? AND datum=?", (kid, "2026-03-03"), one=True):
                err.append("m84c: Kurstermin ohne Teilnehmer nicht angelegt")
            m84c_termin_set({"kurs_id": kid, "datum": "2026-03-10", "von": "17:00", "bis": "18:30"})
            sid = x("INSERT INTO students (name, aktiv) VALUES (?,?)", ("_m84c_schueler", 1))
            a = m84c_add_members({"kurs_id": kid, "student_ids": [sid], "nachtragen": "alle"})
            les = q("SELECT datum, dauer FROM lessons WHERE kurs_id=? AND student_id=? ORDER BY datum", (kid, sid))
            if a.get("nachgetragen") != 2 or [l["datum"] for l in les] != ["2026-03-03", "2026-03-10"] or abs((les[1]["dauer"] or 0) - 1.5) > 0.01:
                err.append(f"m84c: Nachtragen falsch ({a}, {les})")
            a2 = m84c_add_members({"kurs_id": kid, "student_ids": [sid], "nachtragen": "alle"})
            if a2.get("nachgetragen") != 0:
                err.append("m84c: Nachtragen doppelt")
            r2 = kurs_toggle_day(kid, "2026-03-03")
            if r2.get("state") is not None or q("SELECT 1 FROM kurs_termine WHERE kurs_id=? AND datum=?", (kid, "2026-03-03"), one=True):
                err.append("m84c: Kurstermin mit Teilnehmern nicht entfernt")
            if not any(e["ref"].get("id") == kid for e in _m84c_kal("2026-03-01", "2026-03-31")):
                err.append("m84c: Kurstermin fehlt im Kalender")
            x("DELETE FROM lessons WHERE kurs_id=?", (kid,))
            x("DELETE FROM kurs_members WHERE kurs_id=?", (kid,))
            x("DELETE FROM students WHERE id=?", (sid,))
        finally:
            x("DELETE FROM kurs_termine WHERE kurs_id=?", (kid,))
            x("DELETE FROM kurse WHERE id=?", (kid,))
    except Exception as e:
        err.append(f"m84c Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m84c_selftest)
print(f"INIT m84c_kurstermine v{M84C_VERSION}")
