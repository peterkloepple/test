# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m42_lager
# Lagerverwaltung: Artikel mit Bestand / Mindestbestand, Zugang / Abgang / Inventur mit Historie,
# Entnahme fuer Projekte (Bestand sinkt, optional als Material-Eintrag im Projekt).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer
#
# Kopplung an project_entries: ein Projekt-Eintrag mit art 'Material' und nr = Lager-Artikelnummer,
# der NACH dem Anlegen des Lagerartikels erfasst wurde, wird beim naechsten Abgleich automatisch als
# Abgang gebucht (m42_sync). Wird der Eintrag geloescht, bucht der Abgleich die Menge zurueck.

M42_KATEGORIEN = ["Kabel", "Stecker / Verbinder", "AV-Komponenten", "Befestigung", "Profile", "Bleche", "Rohre",
                  "Schweißzusatz", "Gase", "Verbrauchsmaterial", "Sonstiges"]
M42_ARTEN = {"zugang": "Zugang", "abgang": "Abgang", "inventur": "Inventur", "entnahme": "Projekt-Entnahme",
             "storno": "Rückbuchung"}


def _m42_schema():
    x("CREATE TABLE IF NOT EXISTS m42_artikel (id INTEGER PRIMARY KEY, nr TEXT, name TEXT, kategorie TEXT, einheit TEXT, "
      "bestand REAL DEFAULT 0, mindest REAL DEFAULT 0, lagerort TEXT, ek REAL DEFAULT 0, article_id INTEGER, notiz TEXT, "
      "aktiv INTEGER DEFAULT 1, created TEXT, updated TEXT)")
    x("CREATE TABLE IF NOT EXISTS m42_buchung (id INTEGER PRIMARY KEY, artikel_id INTEGER, datum TEXT, art TEXT, menge REAL, "
      "bestand_nach REAL, ek REAL, project_id INTEGER, entry_id INTEGER, notiz TEXT, storniert INTEGER DEFAULT 0, created TEXT)")
    try:
        x("CREATE INDEX IF NOT EXISTS m42_b_art ON m42_buchung(artikel_id)")
        x("CREATE INDEX IF NOT EXISTS m42_b_entry ON m42_buchung(entry_id)")
    except Exception:
        pass


HOOK_SCHEMA.append(_m42_schema)


def _m42_f(v, name="Wert"):
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"{name}: „{v}“ ist keine Zahl.")


def m42_book(aid, art, menge, notiz="", datum=None, project_id=None, entry_id=None):
    """art: zugang (+), abgang/entnahme (-), inventur (menge = gezaehlter Bestand), storno (+/- as given).
    returns booking id"""
    with DB_LOCK:
        a = q("SELECT * FROM m42_artikel WHERE id=?", (aid,), one=True)
        if not a:
            raise ValueError("Lagerartikel nicht gefunden.")
        alt = float(a["bestand"] or 0)
        menge = float(menge)
        if art == "inventur":
            if menge < 0:
                raise ValueError("Der gezählte Bestand darf nicht negativ sein.")
            delta = menge - alt
        elif art == "zugang":
            if menge <= 0:
                raise ValueError("Die Menge muss größer als 0 sein.")
            delta = menge
        elif art in ("abgang", "entnahme"):
            if menge <= 0:
                raise ValueError("Die Menge muss größer als 0 sein.")
            delta = -menge
        elif art == "storno":
            delta = menge
        else:
            raise ValueError("Unbekannte Buchungsart.")
        neu = round(alt + delta, 4)
        x("UPDATE m42_artikel SET bestand=?, updated=? WHERE id=?", (neu, now_iso(), aid))
        return x("INSERT INTO m42_buchung (artikel_id, datum, art, menge, bestand_nach, ek, project_id, entry_id, notiz, created) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)", (aid, datum or today(), art, round(delta, 4), neu, float(a["ek"] or 0),
                                                  project_id, entry_id, notiz or "", now_iso()))


def m42_sync():
    # v2.0.6: atomic (parallel calls booked the same withdrawal twice) + quantity edits are re-booked
    with DB_LOCK:
        return _m42_sync()


def _m42_ts(v):
    return str(v or "").replace("T", " ")[:19]


def _m42_sync():
    """book project material entries that reference a stock article number; reverse deleted ones.
    v2.6.3: project_entries has no AUTOINCREMENT - SQLite reuses the id of a deleted entry. A booking only stays
    linked if its entry still exists, is a 'Material' entry with the article number of the booked article and was
    created before the first booking; otherwise the entry is treated as deleted (stock booked back)."""
    n = 0
    try:
        arts_all = {a["id"]: a for a in q("SELECT id, nr FROM m42_artikel")}
        for g in q("SELECT entry_id, MIN(artikel_id) artikel_id, MIN(created) first, SUM(-menge) booked FROM m42_buchung "
                   "WHERE entry_id IS NOT NULL AND storniert=0 AND art IN ('entnahme','storno') GROUP BY entry_id"):
            e = q("SELECT id, art, nr, qty, project_id, created FROM project_entries WHERE id=?", (g["entry_id"],), one=True)
            a = arts_all.get(g["artikel_id"])
            ok = bool(e) and bool(a) and e["art"] == "Material" and (e["nr"] or "").strip().lower() == (a["nr"] or "").strip().lower() \
                and (not e["created"] or not g["first"] or _m42_ts(e["created"]) <= _m42_ts(g["first"]))
            if not ok:
                # entry deleted, id reused by another entry or changed to another article/type -> give stock back
                for b in q("SELECT * FROM m42_buchung WHERE entry_id=? AND storniert=0 AND art IN ('entnahme','storno')", (g["entry_id"],)):
                    x("UPDATE m42_buchung SET storniert=1 WHERE id=?", (b["id"],))
                    m42_book(b["artikel_id"], "storno", -float(b["menge"]), "Projekt-Eintrag gelöscht/geändert - Rückbuchung", today(),
                             b["project_id"], None)
                    n += 1
                continue
            diff = float(e["qty"] or 0) - float(g["booked"] or 0)
            if abs(diff) > 1e-6:
                m42_book(g["artikel_id"], "storno", -diff, "Menge im Projekt geändert - Korrektur", today(), e["project_id"], e["id"])
                n += 1
    except Exception:
        traceback.print_exc()
    arts = q("SELECT id, nr, created FROM m42_artikel WHERE aktiv=1 AND nr IS NOT NULL AND nr!=''")
    if arts:
        by_nr = {}
        for a in arts:
            by_nr.setdefault(a["nr"].strip().lower(), a)
        ents = q("SELECT e.* FROM project_entries e WHERE e.art='Material' AND e.nr IS NOT NULL AND e.nr!='' "
                 "AND NOT EXISTS (SELECT 1 FROM m42_buchung b WHERE b.entry_id=e.id AND b.storniert=0)")
        for e in ents:
            a = by_nr.get((e["nr"] or "").strip().lower())
            if not a or (e["created"] or "") < (a["created"] or ""):
                continue
            if float(e["qty"] or 0) <= 0:
                continue
            m42_book(a["id"], "entnahme", float(e["qty"]), f"Projekt-Material: {e['name'] or ''}", e["datum"] or today(),
                     e["project_id"], e["id"])
            n += 1
    return n


def m42_list(filt=""):
    m42_sync()
    rows = q("SELECT a.*, (SELECT name FROM articles WHERE id=a.article_id) baustein, "
             "(SELECT MAX(datum) FROM m42_buchung b WHERE b.artikel_id=a.id) letzte FROM m42_artikel a "
             "ORDER BY a.aktiv DESC, a.kategorie, a.nr, a.name")
    for r in rows:
        r["nachbestellen"] = bool(r["aktiv"]) and float(r["mindest"] or 0) > 0 and float(r["bestand"] or 0) < float(r["mindest"] or 0)
        r["wert"] = round(float(r["bestand"] or 0) * float(r["ek"] or 0), 2)
    if filt == "nachbestellen":
        rows = [r for r in rows if r["nachbestellen"]]
    return rows


def m42_low():
    return q("SELECT id, nr, name, bestand, mindest, einheit FROM m42_artikel WHERE aktiv=1 AND mindest>0 AND bestand<mindest "
             "ORDER BY (bestand*1.0/mindest), name")


def m42_save(d):
    name = (d.get("name") or "").strip()
    if not name:
        raise ValueError("Bitte eine Bezeichnung eintragen.")
    nr = (d.get("nr") or "").strip()
    if nr:
        dup = q("SELECT id FROM m42_artikel WHERE lower(nr)=lower(?) AND id!=?", (nr, int(d.get("id") or 0)), one=True)
        if dup:
            raise ValueError(f"Artikelnummer {nr} ist schon vergeben.")
    vals = (nr, name, (d.get("kategorie") or "Sonstiges").strip(), (d.get("einheit") or "Stk").strip(),
            _m42_f(d.get("mindest"), "Mindestbestand"), (d.get("lagerort") or "").strip(), _m42_f(d.get("ek"), "EK"),
            int(d["article_id"]) if d.get("article_id") else None, d.get("notiz") or "", 0 if d.get("aktiv") in (0, False, "0") else 1)
    if d.get("id"):
        aid = int(d["id"])
        x("UPDATE m42_artikel SET nr=?, name=?, kategorie=?, einheit=?, mindest=?, lagerort=?, ek=?, article_id=?, notiz=?, aktiv=?, "
          "updated=? WHERE id=?", vals + (now_iso(), aid))
    else:
        aid = x("INSERT INTO m42_artikel (nr, name, kategorie, einheit, mindest, lagerort, ek, article_id, notiz, aktiv, bestand, created, updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)", vals + (now_iso(), now_iso()))
        start = _m42_f(d.get("bestand"), "Anfangsbestand")
        if start:
            m42_book(aid, "inventur", start, "Anfangsbestand")
    return aid


def m42_delete(aid):
    n = q("SELECT COUNT(*) n FROM m42_buchung WHERE artikel_id=? AND art!='inventur'", (aid,), one=True)["n"]
    if n:
        x("UPDATE m42_artikel SET aktiv=0, updated=? WHERE id=?", (now_iso(), aid))
        return {"ok": True, "info": "Artikel hat Buchungen und wurde deaktiviert (Historie bleibt erhalten)."}
    x("DELETE FROM m42_buchung WHERE artikel_id=?", (aid,))
    x("DELETE FROM m42_artikel WHERE id=?", (aid,))
    return {"ok": True, "info": "Artikel gelöscht."}


def m42_entnahme(d):
    """take material from stock for a project; optional project entry (Material) with sales price"""
    pid = int(d["project_id"])
    aid = int(d["artikel_id"])
    menge = _m42_f(d.get("menge"), "Menge")
    if menge <= 0:
        raise ValueError("Die Menge muss größer als 0 sein.")
    a = q("SELECT * FROM m42_artikel WHERE id=?", (aid,), one=True)
    if not a:
        raise ValueError("Lagerartikel nicht gefunden.")
    warn = ""
    if float(a["bestand"] or 0) < menge:
        warn = f"Achtung: Bestand ({num_de(float(a['bestand'] or 0), 2)} {a['einheit']}) reicht nicht - Bestand wird negativ."
    eid = None
    vk = None
    if d.get("als_eintrag", True):
        vk = d.get("vk")
        if vk in (None, ""):
            bs = q("SELECT price FROM articles WHERE id=?", (a["article_id"],), one=True) if a["article_id"] else None
            if bs:
                vk = float(bs["price"] or 0)
            else:
                vk = round(float(a["ek"] or 0) * (1 + float(get_settings().get("aufschlag") or 0) / 100.0), 2)
        vk = _m42_f(vk, "VK")
    # v2.1.0: entry + booking under the DB lock - a parallel m42_sync (list, boot, Soll/Ist) saw the new entry
    # without booking and booked it a second time (healed later by a correction, but doubled in the history)
    with DB_LOCK:
        if d.get("als_eintrag", True):
            eid = x("INSERT INTO project_entries (project_id, datum, art, nr, name, descr, qty, unit, price, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (pid, d.get("datum") or today(), "Material", a["nr"] or "", a["name"], d.get("notiz") or "Material aus Lager",
                     menge, a["einheit"] or "Stk", vk, now_iso()))
        bid = m42_book(aid, "entnahme", menge, d.get("notiz") or "Entnahme für Projekt", d.get("datum") or today(), pid, eid)
    return {"ok": True, "buchung_id": bid, "entry_id": eid, "warn": warn}


def m42_project_material(pid):
    """net stock withdrawals of a project at purchase price (EK at booking time)"""
    rows = q("SELECT b.*, a.nr, a.name, a.einheit FROM m42_buchung b LEFT JOIN m42_artikel a ON a.id=b.artikel_id "
             "WHERE b.project_id=? AND b.art IN ('entnahme','storno') ORDER BY b.datum, b.id", (pid,))
    ek = round(sum(-float(r["menge"] or 0) * float(r["ek"] or 0) for r in rows), 2)
    return {"rows": rows, "ek_summe": ek}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _m42_g_list(h, qs):
    return h._send(200, {"artikel": m42_list(qs.get("filter") or ""), "kategorien": M42_KATEGORIEN, "arten": M42_ARTEN})


def _m42_g_hist(h, qs):
    m42_sync()
    if qs.get("project_id"):
        return h._send(200, m42_project_material(int(qs["project_id"])))
    return h._send(200, q("SELECT b.*, p.nr pnr, p.name pname FROM m42_buchung b LEFT JOIN projects p ON p.id=b.project_id "
                          "WHERE b.artikel_id=? ORDER BY b.id DESC LIMIT 500", (int(qs["id"]),)))


def _m42_p_save(h, d):
    return h._send(200, {"ok": True, "id": m42_save(d)})


def _m42_p_delete(h, d):
    return h._send(200, m42_delete(int(d["id"])))


def _m42_p_book(h, d):
    bid = m42_book(int(d["artikel_id"]), d.get("art") or "zugang", _m42_f(d.get("menge"), "Menge"), d.get("notiz") or "",
                   d.get("datum") or today(), int(d["project_id"]) if d.get("project_id") else None)
    a = q("SELECT bestand FROM m42_artikel WHERE id=?", (int(d["artikel_id"]),), one=True)
    return h._send(200, {"ok": True, "id": bid, "bestand": a["bestand"]})


def _m42_p_entnahme(h, d):
    return h._send(200, m42_entnahme(d))


HOOK_GET["/api/m42/list"] = _m42_g_list
HOOK_GET["/api/m42/history"] = _m42_g_hist
HOOK_POST["/api/m42/save"] = _m42_p_save
HOOK_POST["/api/m42/delete"] = _m42_p_delete
HOOK_POST["/api/m42/book"] = _m42_p_book
HOOK_POST["/api/m42/entnahme"] = _m42_p_entnahme


def _m42_boot(d):
    try:
        m42_sync()
    except Exception:
        traceback.print_exc()
    low = m42_low()
    d["m42"] = {"low": len(low), "low_list": [dict(r) for r in low[:6]],
                "artikel": q("SELECT id, nr, name, einheit, bestand, ek, article_id FROM m42_artikel WHERE aktiv=1 ORDER BY nr, name")}


HOOK_BOOT.append(_m42_boot)


def _m42_ex(p):
    rows = m42_list(p.get("filter") or "")
    ids = {int(i) for i in (p.get("ids") or []) if str(i).isdigit()}
    if ids:
        rows = [r for r in rows if r["id"] in ids]
    out = [_sh("Lagerbestand" + (" - nachbestellen" if p.get("filter") == "nachbestellen" else ""),
               [("Nr.", "t", 12), ("Bezeichnung", "t", 32), ("Kategorie", "t", 16), ("Lagerort", "t", 14), ("Bestand", "n", 10),
                ("Mindest", "n", 10), ("Einheit", "t", 7), ("EK", "m", 11), ("Wert", "m", 12), ("Nachbestellen", "t", 12)],
               [[r["nr"] or "", r["name"] or "", r["kategorie"] or "", r["lagerort"] or "", r["bestand"] or 0, r["mindest"] or 0,
                 r["einheit"] or "", r["ek"] or 0, r["wert"], "ja" if r["nachbestellen"] else ""] for r in rows],
               f"Stand {de_date(today())}")]
    if not p.get("filter"):
        bu = q("SELECT b.*, a.nr, a.name, a.einheit, p.nr pnr FROM m42_buchung b LEFT JOIN m42_artikel a ON a.id=b.artikel_id "
               "LEFT JOIN projects p ON p.id=b.project_id ORDER BY b.datum DESC, b.id DESC LIMIT 2000")
        out.append(_sh("Buchungen", [("Datum", "d", 11), ("Art", "t", 16), ("Nr.", "t", 12), ("Artikel", "t", 30), ("Menge", "n", 10),
                                     ("Bestand danach", "n", 12), ("Einheit", "t", 7), ("Projekt", "t", 12), ("Notiz", "t", 30)],
                       [[b["datum"], M42_ARTEN.get(b["art"], b["art"]), b["nr"] or "", b["name"] or "", b["menge"] or 0,
                         b["bestand_nach"] or 0, b["einheit"] or "", b["pnr"] or "", b["notiz"] or ""] for b in bu], "", total=False))
    return out


EXPORTS["m42_lager"] = ("Lager", _m42_ex)


def _m42_selftest():
    err = []
    try:
        aid = m42_save({"nr": "_ST_M42", "name": "Selbsttest Kabel", "kategorie": "Kabel", "einheit": "m", "mindest": 50,
                        "ek": 0.5, "bestand": 100})
        m42_book(aid, "abgang", 30)
        m42_book(aid, "zugang", 5)
        b = q("SELECT bestand FROM m42_artikel WHERE id=?", (aid,), one=True)["bestand"]
        if abs(b - 75) > 1e-9:
            err.append(f"m42: Bestand nach Buchungen {b}, erwartet 75")
        m42_book(aid, "inventur", 40)
        if not any(r["id"] == aid for r in m42_low()):
            err.append("m42: Mindestbestand-Warnung fehlt")
        x("DELETE FROM m42_buchung WHERE artikel_id=?", (aid,))
        x("DELETE FROM m42_artikel WHERE id=?", (aid,))
    except Exception as e:
        err.append(f"m42: Lagerbuchung Fehler {e}")
    return err


HOOK_SELFTEST.append(_m42_selftest)
