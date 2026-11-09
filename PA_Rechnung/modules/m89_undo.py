# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m89_undo (v2.1.0)
# Rueckgaengig (Strg+Z / Knopf im Hinweis nach Speichern oder Loeschen), Wiederherstellen
# (Strg+Y / Strg+Umschalt+Z, v2.1.0) und Seite "Verlauf".
#  - Jede Benutzer-Aktion (= eine POST-Anfrage der Oberflaeche) ist ein Schritt.
#  - x() wird ummantelt: vor UPDATE/DELETE/INSERT OR REPLACE werden die betroffenen Zeilen
#    gesichert (Vorher-Bild), bei INSERT die neue rowid gemerkt. Zuruecknehmen spielt das
#    Vorher-Bild in umgekehrter Reihenfolge zurueck (ueber x(), damit das GoBD-Protokoll m51
#    die Ruecknahme selbst als Aenderung protokolliert).
#  - Dateien, die waehrend der Aktion in den Papierkorb verschoben wurden, kommen zurueck.
#  - Hintergrund-Ablaeufe (Eingangsordner, Bankabruf, Automatik) werden NICHT aufgezeichnet.
#  - Festgeschriebene Rechnungen nur, wenn "Rechnungen frei korrigieren" (m65 inv_frei) an ist.
#  - Stapel der letzten 50 Schritte (m89_step / m89_change / m89_file).
#  - v2.1.0: vor dem Zuruecknehmen wird der aktuelle Stand aller betroffenen Zeilen (und der
#    zurueckgeholten Dateien) gesichert (m89_step.redo_data) - Wiederherstellen spielt ihn exakt
#    zurueck. Jede neue Aenderung verwirft den Wiederherstellen-Stapel.
#  - v2.1.0: mehrere Schritte ("bis hierhin") laufen als EIN Vorgang unter DB_LOCK + M89_LOCK:
#    andere Threads (zweites Fenster, Schnittstelle m88, Hintergrund) warten; scheitert ein
#    Schritt, werden die schon zurueckgenommenen Schritte wiederhergestellt (alles oder nichts).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M89_VERSION = "1.1.1"
M89_LOCK = threading.RLock()
M89_KEEP = 50
M89_MAXROWS = 2000
_m89_tl = threading.local()
# never recorded: protocol/log/cache tables, own tables, settings (except number ranges, see below)
# v2.1.0: fints_pending ("Zu pruefen" of the bank list) IS recorded - assigning / ignoring a bank booking removes it
# from there; after "Rueckgaengig" the booking was neither in the list nor in bank_tx and could never be assigned again
M89_SKIP = {"settings", "audit_log", "m89_step", "m89_change", "m89_file", "m86_log", "m86_done", "m86_hinweis", "pending_belege",
            "eingang_log", "beleg_learn", "mail_inbox", "mail_absender", "kal_cal", "kal_label", "kal_event",
            "sqlite_sequence", "fixkosten_vormerk",
            # v2.0.19 (R4): protocols - a sent mail stays sent; undo must not remove the proof of sending
            "mail_log", "m88_log", "m72_lauf",
            # security data: an undo must never bring back a revoked/deleted access, an old PIN or voice data
            "m88_token", "m92_pin",
            # v3.7.0: sync bookkeeping (m58) - never part of an undo step
            "sync_me", "sync_clock", "sync_flag", "sync_row", "sync_tomb", "sync_peer", "sync_konflikt", "sync_log"}
M89_SETTING_KEYS = re.compile(r"^next_")
M89_SKIP_PATHS = ("/api/m89/", "/api/preview", "/api/export", "/api/print", "/api/m64/", "/api/search", "/api/selftest",
                  "/api/m88/", "/api/m92/", "/api/m99d/", "/api/sync/")
M89_TBL = {"customers": "Kunde", "invoices": "Dokument", "belege": "Beleg", "projects": "Projekt", "project_entries": "Projekt-Eintrag",
           "project_files": "Projektdatei", "fahrten": "Fahrt", "articles": "Baustein", "texts": "Textbaustein", "vertraege": "Wartungsvertrag",
           "recurring": "Abo-Rechnung", "students": "Schüler/in", "kurse": "Kurs", "kurs_members": "Kurs-Teilnahme", "lessons": "Unterrichtsstunde",
           "assets": "Anlage", "zertifikate": "Nachweis", "mahnungen": "Mahnung", "bank_tx": "Bankbuchung", "kontostand": "Kontostand",
           "steuerakte": "Steuerakte-Dokument", "briefe": "Brief", "m42_artikel": "Lagerartikel", "m42_buchung": "Lagerbuchung",
           "m85_feld": "Eigenes Feld", "m85_wert": "Feldwert", "m86_regel": "Regel", "fixkosten": "Fixkosten", "fahrt_serien": "Dauerfahrt",
           "items": "Position", "settings": "Nummernkreis",
           "m71_zahlung": "Zahlung", "m72_extra": "Mahnbetrag", "m72_kunde": "B2B-Kennzeichen", "m73_angebot": "Angebotsdaten",
           "m74_raum": "Raum", "m74_geraet": "Gerät", "m74_service": "Serviceeintrag", "m74_datei": "Anlagen-Datei", "m75_pruefling": "Prüfling",
           "m75_pruefung": "Prüfung", "m75_art": "Prüfart", "m75_geraet": "Messgerät", "m76_proj": "EN-1090-Projekt", "m76_eintrag": "EN-1090-Eintrag",
           "m76_wps": "WPS", "m76_link": "EN-1090-Verknüpfung", "m77_prot": "Abnahmeprotokoll", "m78_bom": "Stückliste", "m78_map": "Stücklisten-Zuordnung",
           "m78_res": "Stücklisten-Ergebnis", "m78_change": "Stücklisten-Änderung", "m81_kasse": "Kasse", "m81_buchung": "Kassenbuchung",
           "m81_abschluss": "Kassenabschluss", "m82_kunde": "Auslandsdaten Kunde", "m82_artikel": "Auslandsdaten Artikel", "m82_doc": "Auslandsdaten Dokument",
           "m83_notiz": "Kundennotiz", "fints_pending": "Bankbuchung (zu prüfen)", "m84_termin": "Termin", "m88_notiz": "Handy-Notiz", "m40_plan": "Abschlagsplan", "m41_aufmass": "Aufmaß",
           "m41_kalk": "Kalkulation", "m86_hinweis": "Automatik-Hinweis"}
# preferred title of a step (a cash booking creates a Beleg first - the title should say "Kassenbuchung")
M89_PRIO = ("m81_abschluss", "m81_buchung")
# rows that follow another object (removed together with it) - not used as title when the object is in the step
M89_DEP = {"m71_zahlung", "m83_notiz", "m84_termin", "m72_extra", "m82_doc", "m82_kunde", "m82_artikel"}
# v2.0.19 (R4): actions sent by the UI right after another one belong to it (custom fields after "Kunde speichern")
M89_MERGE = {"/api/m85/werte_save": ("/api/customer/save", "/api/project/save", "/api/beleg/update", "/api/m42/save")}
M89_MERGE_SEK = 5
M89_AUX = {"items", "m85_wert", "kurs_members", "settings", "m42_buchung", "project_files", "fints_pending"}   # secondary tables, not used as title
M89_ART = {"insert": "angelegt", "update": "geändert", "delete": "gelöscht", "upsert": "gesetzt"}
_M89_RX = re.compile(r"^\s*(INSERT(?:\s+OR\s+(\w+))?\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+([A-Za-z_]\w*)\s*(\(([^)]*)\))?", re.I)
_M89_WHERE = re.compile(r"\bWHERE\b", re.I)


def _m89_schema():
    _m89_orig_x("CREATE TABLE IF NOT EXISTS m89_step (id INTEGER PRIMARY KEY, zeit TEXT, titel TEXT, pfad TEXT, n INTEGER DEFAULT 0, "
                "voll INTEGER DEFAULT 1, zurueck INTEGER DEFAULT 0, zurueck_zeit TEXT, fehler TEXT)")
    _m89_orig_x("CREATE TABLE IF NOT EXISTS m89_change (id INTEGER PRIMARY KEY, step_id INTEGER, seq INTEGER, tbl TEXT, rid INTEGER, "
                "art TEXT, alt TEXT, schluessel TEXT, info TEXT)")
    _m89_orig_x("CREATE TABLE IF NOT EXISTS m89_file (id INTEGER PRIMARY KEY, step_id INTEGER, quelle TEXT, ziel TEXT)")
    try:
        _m89_orig_x("CREATE INDEX IF NOT EXISTS m89_c_step ON m89_change(step_id)")
    except Exception:
        pass
    # v2.1.0: redo
    have = {r["name"] for r in q("PRAGMA table_info(m89_step)")}
    for col, decl in (("redo", "INTEGER DEFAULT 0"), ("redo_data", "TEXT"), ("redo_zeit", "TEXT")):
        if col not in have:
            _m89_orig_x(f"ALTER TABLE m89_step ADD COLUMN {col} {decl}")
    # security tables recorded by older versions (e.g. a revoked API token) must not come back by undo/redo
    _m89_orig_x("DELETE FROM m89_change WHERE tbl IN ('m88_token', 'm92_pin')")
    _m89_orig_x("UPDATE m89_step SET redo=0, redo_data=NULL WHERE redo_data LIKE '%\"m88_token\"%' OR redo_data LIKE '%\"m92_pin\"%'")


def _m89_skipped(tbl):
    """change rows of tables that must never be undone (also rows recorded before the table was skipped)"""
    return tbl in M89_SKIP and tbl != "settings"


HOOK_SCHEMA.append(_m89_schema)


# v2.0.19 (R4): payments (m71) of a deleted invoice were removed later by m71_sync (statistics,
# EUER - outside the user action) and were missing after "Rueckgaengig". They go now in the same
# step as the invoice and come back with it.
def _m89_clean_payments():
    if _m89_active():
        x("DELETE FROM m71_zahlung WHERE invoice_id NOT IN (SELECT id FROM invoices)")


if "M83_NACH_LOESCHEN" in globals():
    M83_NACH_LOESCHEN.setdefault("invoices", []).append(_m89_clean_payments)

# ---------------------------------------------------------------------------
# request context (one POST = one step)
# ---------------------------------------------------------------------------


def m89_begin(path):
    _m89_tl.ctx = {"path": path or "", "step": None, "seq": 0, "voll": True}


def m89_end():
    ctx = getattr(_m89_tl, "ctx", None)
    _m89_tl.ctx = None
    if ctx and ctx.get("step"):
        try:
            _m89_finish(ctx)
        except Exception:
            traceback.print_exc()
    return ctx


def _m89_active():
    ctx = getattr(_m89_tl, "ctx", None)
    if not ctx or getattr(_m89_tl, "undoing", False):
        return None
    return ctx


def _m89_step(ctx):
    if not ctx["step"]:
        ctx["step"] = _m89_orig_x("INSERT INTO m89_step (zeit, titel, pfad, n) VALUES (?,?,?,0)", (now_iso(), "Änderung", ctx["path"][:120]))
    return ctx["step"]


def _m89_cols(tbl):
    return [r["name"] for r in q(f"PRAGMA table_info({tbl})")]


def _m89_pk(tbl):
    return [r["name"] for r in sorted(q(f"PRAGMA table_info({tbl})"), key=lambda r: r["pk"]) if r["pk"]]


def _m89_keysets(tbl):
    """primary key + all unique indexes as lists of lower case column names"""
    out = []
    pk = [p.lower() for p in _m89_pk(tbl)]
    if pk:
        out.append(pk)
    try:
        for ix in q(f"PRAGMA index_list({tbl})"):
            if ix.get("unique"):
                cols = [r["name"].lower() for r in q(f"PRAGMA index_info({ix['name']})") if r.get("name")]
                if cols and cols not in out:
                    out.append(cols)
    except Exception:
        pass
    return out


def _m89_info(tbl, r):
    if not r:
        return ""
    try:
        if "_m51_info" in globals() and tbl in ("invoices", "items", "belege", "customers", "bank_tx"):
            s_ = _m51_info(tbl, r)
            if s_:
                return s_
        if tbl == "settings":
            return f"{r.get('k')}"
        if tbl == "m81_buchung":
            return f"Nr. {r.get('nr') or ''} {de_date(r.get('datum'))} {money(float(r.get('vz') or 1) * float(r.get('betrag') or 0))} {r.get('text') or ''}".strip()[:80]
        for k in ("nr", "name", "bezeichnung", "titel", "ziel", "partner", "kdnr"):
            if r.get(k):
                extra = r.get("name") if k == "nr" and r.get("name") else ""
                return f"{r[k]} {extra}".strip()[:80]
    except Exception:
        pass
    return ""


def _m89_add(ctx, tbl, rid, art, alt=None, key=None, info=""):
    sid = _m89_step(ctx)
    ctx["seq"] += 1
    _m89_orig_x("INSERT INTO m89_change (step_id, seq, tbl, rid, art, alt, schluessel, info) VALUES (?,?,?,?,?,?,?,?)",
                (sid, ctx["seq"], tbl, rid, art, json.dumps(alt, ensure_ascii=False, default=str) if alt is not None else None,
                 json.dumps(key, ensure_ascii=False, default=str) if key is not None else None, (info or "")[:200]))


def _m89_watch(tbl, sql, args):
    if tbl in M89_SKIP and tbl != "settings":
        return False
    if tbl == "settings":
        try:
            return bool(args) and bool(M89_SETTING_KEYS.match(str(list(args)[0])))
        except Exception:
            return False
    return True


# ---------------------------------------------------------------------------
# wrapper around x()
# ---------------------------------------------------------------------------
_m89_orig_x = chain_inner("x", "m89_undo")   # v3.1.0: the level below this module
@chain_step("x", "m89_undo")
def _m89_step_x(_next, sql, args=()):
    ctx = _m89_active() if isinstance(sql, str) else None
    if not ctx or isinstance(args, dict):
        return _next(sql, args)
    m = _M89_RX.match(sql)
    if not m:
        return _next(sql, args)
    tbl = m.group(3).lower()
    if not _m89_watch(tbl, sql, args):
        return _next(sql, args)
    verb = m.group(1)[:6].upper()
    mode = (m.group(2) or "").upper()
    a = list(args or ())
    with DB_LOCK:
        before, key = None, None
        try:
            if verb in ("UPDATE", "DELETE"):
                wm = _M89_WHERE.search(sql)
                if wm:
                    nset = sql[:wm.start()].count("?")
                    before = q(f"SELECT rowid AS _rid, * FROM {tbl} WHERE {sql[wm.end():]} LIMIT {M89_MAXROWS + 1}", a[nset:])
                else:
                    before = q(f"SELECT rowid AS _rid, * FROM {tbl} LIMIT {M89_MAXROWS + 1}")
            elif verb == "INSERT" and mode in ("REPLACE", "IGNORE"):
                if not m.group(5):
                    ctx["voll"] = mode != "REPLACE" and ctx["voll"]
                else:
                    cols = [c.strip().strip('"[]`').lower() for c in m.group(5).split(",")]
                    if len(a) >= len(cols):
                        for ks in _m89_keysets(tbl):
                            if all(k_ in cols for k_ in ks):
                                key = {k_: a[cols.index(k_)] for k_ in ks}
                                before = q(f"SELECT rowid AS _rid, * FROM {tbl} WHERE " + " AND ".join(f"{k_}=?" for k_ in ks), tuple(key.values()))
                                break
                    if key is None and mode == "REPLACE":
                        ctx["voll"] = False          # replaced row cannot be found again
        except Exception:
            before = None
            ctx["voll"] = False
        if before is not None and len(before) > M89_MAXROWS:
            ctx["voll"] = False
            before = before[:M89_MAXROWS]
        rid = _next(sql, args)
        try:
            if verb == "INSERT" and key is not None:
                if mode == "IGNORE" and before:
                    pass                      # nothing changed
                else:
                    _m89_add(ctx, tbl, None, "upsert", before or [], key, _m89_info(tbl, (before or [{}])[0]) or _m89_info(tbl, key))
            elif verb == "INSERT":
                if rid:
                    new = q(f"SELECT * FROM {tbl} WHERE rowid=?", (rid,), one=True)
                    ok_new = bool(new)
                    if ok_new and mode == "IGNORE" and m.group(5):
                        # lastrowid is not reliable for an ignored insert -> row must carry the inserted values
                        cols = [c.strip().strip('"[]`').lower() for c in m.group(5).split(",")]
                        low = {k.lower(): v for k, v in new.items()}
                        ok_new = all(str(low.get(c)) == str(a[i]) for i, c in enumerate(cols) if i < len(a))
                    if ok_new:
                        _m89_add(ctx, tbl, rid, "insert", None, None, _m89_info(tbl, new))
                    elif mode != "IGNORE":
                        ctx["voll"] = False
            elif before:
                art = "update" if verb == "UPDATE" else "delete"
                for r in before:
                    _m89_add(ctx, tbl, r["_rid"], art, {k: v for k, v in r.items() if k != "_rid"}, None, _m89_info(tbl, r))
        except Exception:
            traceback.print_exc()
            ctx["voll"] = False
    return rid


# files moved into the trash during an action come back on undo
_m89_orig_move = shutil.move


def _m89_move(src, dst, *a, **kw):
    r = _m89_orig_move(src, dst, *a, **kw)
    try:
        ctx = _m89_active()
        if ctx:
            d = os.path.abspath(str(r or dst))
            rel = os.path.relpath(d, DATA_DIR) if d.lower().startswith(os.path.abspath(DATA_DIR).lower()) else ""
            if rel and rel.replace("\\", "/").split("/")[0] in ("_Papierkorb", "Papierkorb"):
                sid = _m89_step(ctx)
                _m89_orig_x("INSERT INTO m89_file (step_id, quelle, ziel) VALUES (?,?,?)", (sid, os.path.abspath(str(src)), d))
    except Exception:
        traceback.print_exc()
    return r


shutil.move = _m89_move

# ---------------------------------------------------------------------------
# finishing a step: title, prune
# ---------------------------------------------------------------------------


def m89_title(sid):
    ch = q("SELECT tbl, art, info, rid, alt FROM m89_change WHERE step_id=? ORDER BY seq", (sid,))
    nf = q("SELECT COUNT(*) n FROM m89_file WHERE step_id=?", (sid,), one=True)["n"]
    if not ch:
        return f"{nf} Datei(en) in den Papierkorb" if nf else "Änderung"
    main = [c for c in ch if c["tbl"] not in M89_AUX] or ch
    main = [c for c in main if c["tbl"] not in M89_DEP] or main
    pr = [c for c in main if c["tbl"] in M89_PRIO]
    if pr:
        best = M89_PRIO[min(M89_PRIO.index(c["tbl"]) for c in pr)]
        main = [c for c in main if c["tbl"] == best] + [c for c in main if c["tbl"] != best]
    t0 = main[0]["tbl"]
    objs = {}
    for c in main:
        if c["tbl"] == t0:
            objs.setdefault((c["rid"], c["art"]), c)
    arts = [k[1] for k in objs]
    art = "delete" if "delete" in arts else "insert" if "insert" in arts else arts[0] if arts else "update"
    name = M89_TBL.get(t0, t0)
    n = len({k[0] for k in objs})
    if t0 == "invoices" and main[0].get("rid"):
        r = q("SELECT typ FROM invoices WHERE id=?", (main[0]["rid"],), one=True)
        if not r:
            try:
                r = json.loads(main[0].get("alt") or "null")
            except Exception:
                r = None
        if isinstance(r, dict) and r.get("typ"):
            name = DOC_TYPES.get(r["typ"], {}).get("title", name)
    info = next((c["info"] for c in main if c["tbl"] == t0 and c["info"]), "")
    if t0 == "invoices" and n > 1:
        # v2.1.1: a cancellation inserts the storno document and updates the original - one readable title
        for (rid_, art_) in objs:
            if art_ == "insert":
                r_ = q("SELECT typ, nr FROM invoices WHERE id=?", (rid_,), one=True)
                if r_ and r_["typ"] == "storno":
                    return f"Storno erstellt: {r_['nr'] or ''}".strip(": ")[:160]
    head = f"{name} {M89_ART.get(art, 'geändert')}" if n <= 1 else f"{n}× {name} {M89_ART.get(art, 'geändert')}"
    return (head + (f": {info}" if info and n <= 1 else "")).strip()[:160]


def _m89_finish(ctx):
    sid = ctx["step"]
    n = q("SELECT COUNT(*) n FROM m89_change WHERE step_id=?", (sid,), one=True)["n"]
    nf = q("SELECT COUNT(*) n FROM m89_file WHERE step_id=?", (sid,), one=True)["n"]
    if not n and not nf:
        _m89_orig_x("DELETE FROM m89_step WHERE id=?", (sid,))
        ctx["step"] = None
        return None
    if ctx.get("path") in M89_MERGE and not ctx.get("merged"):
        prev = q("SELECT * FROM m89_step WHERE id<? ORDER BY id DESC LIMIT 1", (sid,), one=True)
        try:
            age = (datetime.datetime.now() - datetime.datetime.fromisoformat(prev["zeit"][:19])).total_seconds() if prev else 999
        except Exception:
            age = 999
        if prev and not prev["zurueck"] and 0 <= age <= M89_MERGE_SEK and (prev["pfad"] or "") in M89_MERGE[ctx["path"]]:
            off = (q("SELECT MAX(seq) m FROM m89_change WHERE step_id=?", (prev["id"],), one=True) or {}).get("m") or 0
            _m89_orig_x("UPDATE m89_change SET step_id=?, seq=seq+? WHERE step_id=?", (prev["id"], off, sid))
            _m89_orig_x("UPDATE m89_file SET step_id=? WHERE step_id=?", (prev["id"], sid))
            _m89_orig_x("DELETE FROM m89_step WHERE id=?", (sid,))
            ctx["step"] = sid = prev["id"]
            ctx["merged"] = True
            ctx["voll"] = bool(ctx.get("voll", True)) and bool(prev["voll"])
            n = q("SELECT COUNT(*) n FROM m89_change WHERE step_id=?", (sid,), one=True)["n"]
            nf = q("SELECT COUNT(*) n FROM m89_file WHERE step_id=?", (sid,), one=True)["n"]
    t = m89_title(sid)
    _m89_orig_x("UPDATE m89_step SET titel=?, n=?, voll=? WHERE id=?", (t, n + nf, 1 if ctx.get("voll", True) else 0, sid))
    # v2.1.0: a new change after undo discards the redo stack (as in every editor)
    _m89_orig_x("UPDATE m89_step SET redo=0, redo_data=NULL WHERE redo=1 AND id<>?", (sid,))
    old = q(f"SELECT id FROM m89_step ORDER BY id DESC LIMIT -1 OFFSET {M89_KEEP}")
    if old:
        ids = [r["id"] for r in old]
        mx = max(ids)
        _m89_orig_x("DELETE FROM m89_change WHERE step_id<=?", (mx,))
        _m89_orig_x("DELETE FROM m89_file WHERE step_id<=?", (mx,))
        _m89_orig_x("DELETE FROM m89_step WHERE id<=?", (mx,))
    return {"id": sid, "titel": t}


# hook into the HTTP handler: begin / end of each POST, step info in the JSON answer
_m89_orig_post = Handler.do_POST
_m89_orig_send = Handler._send


def _m89_do_post(self):
    p = urlparse(self.path).path
    if p.startswith(M89_SKIP_PATHS) or not p.startswith("/api/"):
        return _m89_orig_post(self)
    m89_begin(p)
    try:
        return _m89_orig_post(self)
    finally:
        m89_end()


def _m89_send(self, code, body, *a, **kw):
    try:
        ctx = getattr(_m89_tl, "ctx", None)
        if ctx and ctx.get("step") and isinstance(body, dict) and code == 200 and body.get("ok", True) is not False:
            info = _m89_finish(ctx)
            if info:
                body = dict(body, _m89=info)
                ctx["sent"] = True
    except Exception:
        traceback.print_exc()
    return _m89_orig_send(self, code, body, *a, **kw)


Handler.do_POST = _m89_do_post
Handler._send = _m89_send

# ---------------------------------------------------------------------------
# undo
# ---------------------------------------------------------------------------


def _m89_locked_check(steps):
    try:
        frei = inv_frei() if "inv_frei" in globals() else False
    except Exception:
        frei = False
    for s_ in steps:
        # v2.0.19 (R4): a closed cash book (Kassenabschluss) is final - GoBD, also with "frei korrigieren"
        for c in q("SELECT tbl, rid, alt FROM m89_change WHERE step_id=? AND tbl IN ('m81_abschluss','m81_buchung')", (s_["id"],)):
            alt = json.loads(c["alt"] or "null")
            now_ = q("SELECT abschluss_id FROM m81_buchung WHERE rowid=?", (c["rid"],), one=True) if c["tbl"] == "m81_buchung" and c["rid"] else None
            if c["tbl"] == "m81_abschluss" or (isinstance(alt, dict) and alt.get("abschluss_id")) or (now_ and now_.get("abschluss_id")):
                raise ValueError(f"„{s_['titel']}“ betrifft einen Kassenabschluss – abgeschlossene Kassenbuchungen lassen sich nicht zurücknehmen "
                                 "(GoBD). Bitte im Kassenbuch eine Stornobuchung erfassen.")
    if frei:
        return
    for s_ in steps:
        for c in q("SELECT tbl, rid, alt FROM m89_change WHERE step_id=? AND tbl IN ('invoices','items')", (s_["id"],)):
            alt = json.loads(c["alt"] or "null") or {}
            iid = c["rid"] if c["tbl"] == "invoices" else (alt.get("invoice_id") if isinstance(alt, dict) else None)
            if isinstance(alt, dict) and c["tbl"] == "invoices" and alt.get("locked"):
                raise ValueError(f"„{s_['titel']}“ betrifft eine festgeschriebene Rechnung – Zurücknehmen nur mit "
                                 "Einstellung „Rechnungen frei korrigieren“.")
            if iid:
                r = q("SELECT locked FROM invoices WHERE id=?", (iid,), one=True)
                if r and r["locked"]:
                    raise ValueError(f"„{s_['titel']}“ betrifft eine festgeschriebene Rechnung – Zurücknehmen nur mit "
                                     "Einstellung „Rechnungen frei korrigieren“.")


def _m89_restore_rows(tbl, rows):
    cols_now = set(_m89_cols(tbl))
    for r in rows:
        rid = r.get("_rid")
        d = {k: v for k, v in r.items() if k in cols_now and k != "_rid"}
        if not d:
            continue
        names = list(d)
        if rid is not None:
            x(f"INSERT OR REPLACE INTO {tbl} (rowid, {', '.join(names)}) VALUES ({','.join('?' * (len(names) + 1))})", (rid,) + tuple(d.values()))
        else:
            x(f"INSERT OR REPLACE INTO {tbl} ({', '.join(names)}) VALUES ({','.join('?' * len(names))})", tuple(d.values()))


def _m89_undo_step(s_):
    ch = q("SELECT * FROM m89_change WHERE step_id=? ORDER BY seq DESC", (s_["id"],))
    for c in ch:
        tbl, art = c["tbl"], c["art"]
        if _m89_skipped(tbl):
            continue
        alt = json.loads(c["alt"]) if c["alt"] else None
        if art == "insert":
            x(f"DELETE FROM {tbl} WHERE rowid=?", (c["rid"],))
        elif art == "update":
            cols_now = set(_m89_cols(tbl))
            d = {k: v for k, v in (alt or {}).items() if k in cols_now}
            if d:
                x(f"UPDATE {tbl} SET {', '.join(k + '=?' for k in d)} WHERE rowid=?", tuple(d.values()) + (c["rid"],))
        elif art == "delete":
            if not q(f"SELECT 1 FROM {tbl} WHERE rowid=?", (c["rid"],), one=True):
                _m89_restore_rows(tbl, [dict(alt or {}, _rid=c["rid"])])
        elif art == "upsert":
            key = json.loads(c["schluessel"] or "{}")
            if key:
                x(f"DELETE FROM {tbl} WHERE " + " AND ".join(f"{k}=?" for k in key), tuple(key.values()))
            if alt:
                _m89_restore_rows(tbl, alt)
    moved = []
    for f in q("SELECT * FROM m89_file WHERE step_id=? ORDER BY id DESC", (s_["id"],)):
        try:
            if os.path.isfile(f["ziel"]) and not os.path.exists(f["quelle"]):
                os.makedirs(os.path.dirname(f["quelle"]), exist_ok=True)
                _m89_orig_move(f["ziel"], f["quelle"])
                moved.append(f["id"])
        except Exception:
            traceback.print_exc()
    return moved


# ---------------------------------------------------------------------------
# v2.1.0: state snapshots (redo + all-or-nothing)
# ---------------------------------------------------------------------------


def _m89_targets(sid):
    """rows a step touches: (tbl, rowid) or (tbl, unique key) - deduplicated, in order"""
    out, seen = [], set()
    for c in q("SELECT tbl, rid, art, schluessel FROM m89_change WHERE step_id=? ORDER BY seq", (sid,)):
        if _m89_skipped(c["tbl"]):
            continue
        if c["art"] == "upsert":
            key = json.loads(c["schluessel"] or "{}")
            if not key:
                continue
            k_ = (c["tbl"], "k", json.dumps(key, sort_keys=True, default=str))
            if k_ not in seen:
                seen.add(k_)
                out.append({"t": c["tbl"], "key": key})
        elif c["rid"] is not None:
            k_ = (c["tbl"], "r", c["rid"])
            if k_ not in seen:
                seen.add(k_)
                out.append({"t": c["tbl"], "rid": c["rid"]})
    return out


def _m89_snapshot(sid):
    """current state of every row the step touches (taken right before undo / redo)"""
    rows = []
    for tg in _m89_targets(sid):
        tbl = tg["t"]
        try:
            if "key" in tg:
                cur = q(f"SELECT rowid AS _rid, * FROM {tbl} WHERE " + " AND ".join(f"{k}=?" for k in tg["key"]), tuple(tg["key"].values()))
                rows.append({"t": tbl, "key": tg["key"], "rows": cur})
            else:
                cur = q(f"SELECT rowid AS _rid, * FROM {tbl} WHERE rowid=?", (tg["rid"],), one=True)
                rows.append({"t": tbl, "rid": tg["rid"], "row": cur})
        except Exception:
            traceback.print_exc()          # table dropped meanwhile - nothing to keep
    return {"rows": rows, "files": []}


def _m89_apply(snap, files_forward=True):
    """put every row back to the state in the snapshot; files moved back by the undo go to the trash again"""
    rows = [e for e in (snap.get("rows") or []) if not _m89_skipped(e.get("t"))]
    for e in rows:                         # 1) remove what must not exist / what is replaced by key
        tbl = e["t"]
        if "key" in e:
            x(f"DELETE FROM {tbl} WHERE " + " AND ".join(f"{k}=?" for k in e["key"]), tuple(e["key"].values()))
        elif not e.get("row"):
            x(f"DELETE FROM {tbl} WHERE rowid=?", (e["rid"],))
    for e in rows:                         # 2) write the rows of the snapshot (same rowid)
        tbl = e["t"]
        if "key" in e:
            if e.get("rows"):
                _m89_restore_rows(tbl, e["rows"])
        elif e.get("row"):
            _m89_restore_rows(tbl, [e["row"]])
    n = 0
    if files_forward:
        for fid in snap.get("files") or []:
            f = q("SELECT * FROM m89_file WHERE id=?", (fid,), one=True)
            try:
                if f and os.path.isfile(f["quelle"]) and not os.path.exists(f["ziel"]):
                    os.makedirs(os.path.dirname(f["ziel"]), exist_ok=True)
                    _m89_orig_move(f["quelle"], f["ziel"])
                    n += 1
            except Exception:
                traceback.print_exc()
    return n


def _m89_files_back(snap):
    """undo the file part of a redo (used when a redo range is rolled back)"""
    for fid in snap.get("files") or []:
        f = q("SELECT * FROM m89_file WHERE id=?", (fid,), one=True)
        try:
            if f and os.path.isfile(f["ziel"]) and not os.path.exists(f["quelle"]):
                os.makedirs(os.path.dirname(f["quelle"]), exist_ok=True)
                _m89_orig_move(f["ziel"], f["quelle"])
        except Exception:
            traceback.print_exc()


class _M89Quiet:
    """no recording, no automation rules, DB exclusive for this thread while undo/redo runs"""

    def __enter__(self):
        M89_LOCK.acquire()
        DB_LOCK.acquire()
        self.prev = getattr(_m89_tl, "undoing", False)
        _m89_tl.undoing = True
        self.m86 = "_m86_tl" in globals()
        if self.m86:
            self.m86_prev = getattr(_m86_tl, "busy", False)
            _m86_tl.busy = True
        return self

    def __exit__(self, *a):
        _m89_tl.undoing = self.prev
        if self.m86:
            _m86_tl.busy = self.m86_prev
        DB_LOCK.release()
        M89_LOCK.release()
        return False


def _m89_gobd(aktion, titel):
    try:
        if "m51_log" in globals():
            m51_log("System", None, aktion, "", "", "", titel)
    except Exception:
        pass


def _m89_redo_check(steps):
    """same rules as undo: closed cash book never, locked invoices only with 'frei korrigieren'"""
    try:
        frei = inv_frei() if "inv_frei" in globals() else False
    except Exception:
        frei = False
    for s_ in steps:
        if q("SELECT 1 FROM m89_change WHERE step_id=? AND tbl='m81_abschluss' LIMIT 1", (s_["id"],), one=True):
            raise ValueError(f"„{s_['titel']}“ betrifft einen Kassenabschluss und kann nicht wiederhergestellt werden.")
        snap = json.loads(s_["redo_data"] or "{}")
        for e in snap.get("rows") or []:
            if e["t"] == "m81_buchung" and e.get("row") and e["row"].get("abschluss_id"):
                raise ValueError(f"„{s_['titel']}“ betrifft einen Kassenabschluss und kann nicht wiederhergestellt werden.")
            if frei:
                continue
            if e["t"] == "invoices":
                if (e.get("row") or {}).get("locked"):
                    raise ValueError(f"„{s_['titel']}“ betrifft eine festgeschriebene Rechnung – Wiederherstellen nur mit "
                                     "Einstellung „Rechnungen frei korrigieren“.")
                r = q("SELECT locked FROM invoices WHERE rowid=?", (e.get("rid"),), one=True) if e.get("rid") else None
                if r and r["locked"]:
                    raise ValueError(f"„{s_['titel']}“ betrifft eine festgeschriebene Rechnung – Wiederherstellen nur mit "
                                     "Einstellung „Rechnungen frei korrigieren“.")


def m89_undo(step_id=None):
    """undo the newest open step, or all open steps from step_id up to the newest ('bis hierhin') -
    v2.1.0: one locked operation, all or nothing, each step keeps a redo snapshot"""
    with M89_LOCK:
        open_ = q("SELECT * FROM m89_step WHERE zurueck=0 ORDER BY id DESC")
        if not open_:
            raise ValueError("Es gibt nichts mehr zurückzunehmen.")
        steps = [open_[0]] if not step_id else [s_ for s_ in open_ if s_["id"] >= int(step_id)]
        if not steps:
            raise ValueError("Dieser Schritt ist schon zurückgenommen.")
        bad = [s_ for s_ in steps if not s_["voll"]]
        if bad:
            raise ValueError(f"„{bad[0]['titel']}“ wurde nicht vollständig aufgezeichnet (sehr viele Zeilen) und kann nicht zurückgenommen werden.")
        _m89_locked_check(steps)
        done, files = [], 0
        with _M89Quiet():
            for s_ in steps:
                snap = _m89_snapshot(s_["id"])
                try:
                    snap["files"] = _m89_undo_step(s_)      # ids of the files brought back from the trash
                except Exception as e:
                    traceback.print_exc()
                    # all or nothing: this step back to its state, then the steps before it (newest last)
                    try:
                        _m89_apply(dict(snap, files=[f["id"] for f in q("SELECT id FROM m89_file WHERE step_id=?", (s_["id"],))]))
                    except Exception:
                        traceback.print_exc()
                    for d_ in reversed(done):
                        try:
                            _m89_apply(d_["snap"])
                            _m89_orig_x("UPDATE m89_step SET zurueck=0, zurueck_zeit=NULL, redo=0, redo_data=NULL WHERE id=?", (d_["id"],))
                        except Exception:
                            traceback.print_exc()
                    msg = (f"„{s_['titel']}“ ließ sich nicht zurücknehmen ({e}). "
                           + ("Die davor zurückgenommenen Schritte wurden wiederhergestellt – es hat sich nichts geändert."
                              if done else "Es hat sich nichts geändert."))
                    raise ValueError(msg)
                done.append({"id": s_["id"], "titel": s_["titel"], "snap": snap})
            for d_ in done:
                files += len(d_["snap"]["files"])
                _m89_orig_x("UPDATE m89_step SET zurueck=1, zurueck_zeit=?, redo=1, redo_data=? WHERE id=?",
                            (now_iso(), json.dumps(d_["snap"], ensure_ascii=False, default=str), d_["id"]))
                _m89_gobd("Rückgängig", d_["titel"])
    return {"ok": True, "n": len(done), "titel": [d_["titel"] for d_ in done], "ids": [d_["id"] for d_ in done], "dateien": files}


def m89_redo(step_id=None):
    """redo the oldest undone step (reverse order of undo), or all redoable steps up to step_id -
    one locked operation, all or nothing"""
    with M89_LOCK:
        cand = q("SELECT * FROM m89_step WHERE zurueck=1 AND redo=1 ORDER BY id ASC")
        if not cand:
            raise ValueError("Es gibt nichts wiederherzustellen.")
        steps = [cand[0]] if not step_id else [s_ for s_ in cand if s_["id"] <= int(step_id)]
        if not steps:
            raise ValueError("Dieser Schritt kann nicht wiederhergestellt werden.")
        _m89_redo_check(steps)
        done, files = [], 0
        with _M89Quiet():
            for s_ in steps:
                snap = json.loads(s_["redo_data"] or "{}")
                pre = _m89_snapshot(s_["id"])
                try:
                    files += _m89_apply(snap)
                except Exception as e:
                    traceback.print_exc()
                    try:
                        _m89_apply(pre, files_forward=False)
                        _m89_files_back(snap)
                    except Exception:
                        traceback.print_exc()
                    for d_ in reversed(done):
                        try:
                            _m89_apply(d_["pre"], files_forward=False)
                            _m89_files_back(d_["snap"])
                            _m89_orig_x("UPDATE m89_step SET zurueck=1, redo=1, redo_data=?, redo_zeit=NULL WHERE id=?",
                                        (json.dumps(d_["snap"], ensure_ascii=False, default=str), d_["id"]))
                        except Exception:
                            traceback.print_exc()
                    raise ValueError(f"„{s_['titel']}“ ließ sich nicht wiederherstellen ({e}). "
                                     + ("Die davor wiederhergestellten Schritte wurden wieder zurückgenommen – es hat sich nichts geändert."
                                        if done else "Es hat sich nichts geändert."))
                _m89_orig_x("UPDATE m89_step SET zurueck=0, zurueck_zeit=NULL, redo=0, redo_data=NULL, redo_zeit=? WHERE id=?", (now_iso(), s_["id"]))
                done.append({"id": s_["id"], "titel": s_["titel"], "snap": snap, "pre": pre})
            for d_ in done:
                _m89_gobd("Wiederhergestellt", d_["titel"])
    return {"ok": True, "n": len(done), "titel": [d_["titel"] for d_ in done], "ids": [d_["id"] for d_ in done], "dateien": files}


def m89_list(n=M89_KEEP):
    rows = q("SELECT * FROM m89_step ORDER BY id DESC LIMIT ?", (int(n),))
    return rows


def m89_detail(sid):
    return {"step": q("SELECT * FROM m89_step WHERE id=?", (int(sid),), one=True),
            "changes": [{"tbl": c["tbl"], "bereich": M89_TBL.get(c["tbl"], c["tbl"]), "art": M89_ART.get(c["art"], c["art"]), "info": c["info"] or ""}
                        for c in q("SELECT tbl, art, info FROM m89_change WHERE step_id=? ORDER BY seq", (int(sid),))],
            "files": [{"quelle": f["quelle"], "ziel": f["ziel"]} for f in q("SELECT * FROM m89_file WHERE step_id=?", (int(sid),))]}


def _m89_r_list(h, qs):
    return h._send(200, {"steps": m89_list()})


def _m89_r_detail(h, qs):
    return h._send(200, m89_detail(qs.get("id") or 0))


def _m89_r_undo(h, d):
    return h._send(200, m89_undo(d.get("id")))


def _m89_r_redo(h, d):
    return h._send(200, m89_redo(d.get("id")))


def _m89_r_clear(h, d):
    with M89_LOCK:
        return _m89_clear(h)


def _m89_clear(h):
    _m89_orig_x("DELETE FROM m89_change")
    _m89_orig_x("DELETE FROM m89_file")
    _m89_orig_x("DELETE FROM m89_step")
    return h._send(200, {"ok": True})


def _m89_boot(d):
    try:
        r = q("SELECT id, titel FROM m89_step WHERE zurueck=0 ORDER BY id DESC LIMIT 1", one=True)
        d["m89_last"] = r
        d["m89_redo"] = q("SELECT id, titel FROM m89_step WHERE zurueck=1 AND redo=1 ORDER BY id ASC LIMIT 1", one=True)
    except Exception:
        d["m89_last"] = None
        d["m89_redo"] = None


HOOK_GET["/api/m89/list"] = _m89_r_list
HOOK_GET["/api/m89/detail"] = _m89_r_detail
HOOK_POST["/api/m89/undo"] = _m89_r_undo
HOOK_POST["/api/m89/redo"] = _m89_r_redo
HOOK_POST["/api/m89/clear"] = _m89_r_clear
HOOK_BOOT.append(_m89_boot)


def _m89_ex(p):
    rows = []
    for s_ in m89_list():
        rows.append([s_["zeit"][:16].replace("T", " "), s_["titel"] or "", s_["n"] or 0,
                     ("zurückgenommen (wiederherstellbar)" if s_.get("redo") else "zurückgenommen") if s_["zurueck"]
                     else ("nicht möglich" if not s_["voll"] else "offen")])
    return [_sh("Verlauf (Rückgängig)", [("Zeit", "t", 16), ("Aktion", "t", 50), ("Änderungen", "n", 11), ("Status", "t", 24)], rows,
                f"Stand {de_date(today())}", False)]


EXPORTS["m89_verlauf"] = ("Verlauf", _m89_ex)


def _m89_selftest():
    err = []
    try:
        m89_begin("/api/_st")
        cid = x("INSERT INTO customers (kdnr, firma, name, ort, created) VALUES (?,?,?,?,?)", ("_ST89", "_ST Firma", "Muster", "Köln", now_iso()))
        st1 = m89_end()
        m89_begin("/api/_st")
        x("UPDATE customers SET ort=? WHERE id=?", ("Bonn", cid))
        st2 = m89_end()
        m89_begin("/api/_st")
        x("DELETE FROM customers WHERE id=?", (cid,))
        st3 = m89_end()
        if not (st1["step"] and st2["step"] and st3["step"]):
            err.append("m89: Schritte nicht aufgezeichnet")
        else:
            m89_undo()                                  # undo delete
            r = q("SELECT ort FROM customers WHERE id=?", (cid,), one=True)
            if not r or r["ort"] != "Bonn":
                err.append(f"m89: Löschen nicht zurückgenommen ({r})")
            m89_undo(st2["step"])                       # undo update
            r = q("SELECT ort FROM customers WHERE id=?", (cid,), one=True)
            if not r or r["ort"] != "Köln":
                err.append(f"m89: Änderung nicht zurückgenommen ({r})")
            m89_undo(st1["step"])                       # undo insert
            if q("SELECT 1 FROM customers WHERE id=?", (cid,), one=True):
                err.append("m89: Anlegen nicht zurückgenommen")
            if "Kunde" not in (q("SELECT titel FROM m89_step WHERE id=?", (st1["step"],), one=True) or {}).get("titel", ""):
                err.append("m89: Titel ohne Bereich")
        # number range (settings next_*) is restored
        nr0 = get_settings().get("next_nr")
        m89_begin("/api/_st")
        set_setting("next_nr", "_ST-999")
        st4 = m89_end()
        if st4 and st4["step"]:
            m89_undo(st4["step"])
            if get_settings().get("next_nr") != nr0:
                err.append("m89: Nummernkreis nicht zurückgenommen")
        else:
            err.append("m89: Nummernkreis nicht aufgezeichnet")
        err += _m89_selftest_redo()
        for s_ in (st1, st2, st3, st4):
            if s_ and s_.get("step"):
                _m89_orig_x("DELETE FROM m89_change WHERE step_id=?", (s_["step"],))
                _m89_orig_x("DELETE FROM m89_step WHERE id=?", (s_["step"],))
        _m89_orig_x("DELETE FROM customers WHERE kdnr='_ST89'")
    except Exception as e:
        err.append(f"m89 Ausnahme: {e}")
        _m89_tl.ctx = None
    return err


def _m89_selftest_redo():
    """v2.1.0: undo -> redo -> undo gives identical data; new change drops redo; failing range rolls back"""
    err, made = [], []
    g = globals()

    def step(sql, args):
        m89_begin("/api/_st")
        r_ = x(sql, args)
        st = m89_end()
        made.append(st["step"])
        return r_, st["step"]

    def row(cid):
        return q("SELECT * FROM customers WHERE id=?", (cid,), one=True)
    try:
        cid, sa = step("INSERT INTO customers (kdnr, firma, name, ort, created) VALUES (?,?,?,?,?)", ("_ST89R", "_ST Redo", "Muster", "Köln", now_iso()))
        _, sb = step("UPDATE customers SET ort=? WHERE id=?", ("Bonn", cid))
        r_b = row(cid)
        _, sc = step("DELETE FROM customers WHERE id=?", (cid,))
        # single undo / redo / undo
        m89_undo()
        if row(cid) != r_b:
            err.append("m89 redo: Zurücknehmen stellt Zeile nicht her")
        m89_redo()
        if row(cid) is not None:
            err.append("m89 redo: Wiederherstellen (Löschen) wirkt nicht")
        m89_undo()
        if row(cid) != r_b:
            err.append("m89 redo: Undo-Redo-Undo nicht identisch")
        # range undo back to A, then redo step by step and as range
        m89_undo(sa)
        if row(cid) is not None:
            err.append("m89 redo: Bereich zurücknehmen unvollständig")
        if [r_["id"] for r_ in q("SELECT id FROM m89_step WHERE zurueck=1 AND redo=1 AND id IN (?,?,?) ORDER BY id", (sa, sb, sc))] != [sa, sb, sc]:
            err.append("m89 redo: Wiederherstellen-Stapel fehlt")
        m89_redo()                                    # A again
        r_ = row(cid)
        if not r_ or r_["ort"] != "Köln":
            err.append(f"m89 redo: Anlegen nicht wiederhergestellt ({r_})")
        m89_redo(sb)                                  # B (range up to B)
        if row(cid) != r_b:
            err.append("m89 redo: Bereich wiederherstellen ungleich")
        # a new change drops the redo stack (C is still undone)
        _, sd = step("UPDATE customers SET name=? WHERE id=?", ("Neu", cid))
        try:
            m89_redo()
            err.append("m89 redo: neue Änderung hat den Wiederherstellen-Stapel nicht verworfen")
        except ValueError:
            pass
        # all or nothing: range undo where the older step fails -> newer step must come back
        _, se = step("UPDATE customers SET ort=? WHERE id=?", ("Aachen", cid))
        r_e = row(cid)
        orig_us = g["_m89_undo_step"]

        def boom(s_):
            if s_["id"] == sd:
                raise RuntimeError("Testfehler")
            return orig_us(s_)
        g["_m89_undo_step"] = boom
        try:
            m89_undo(sd)
            err.append("m89 redo: Fehler im Bereich wurde nicht gemeldet")
        except ValueError:
            pass
        finally:
            g["_m89_undo_step"] = orig_us
        if row(cid) != r_e:
            err.append(f"m89 redo: Bereich nicht alles-oder-nichts ({row(cid)})")
        if q("SELECT COUNT(*) n FROM m89_step WHERE id IN (?,?) AND zurueck=1", (sd, se), one=True)["n"]:
            err.append("m89 redo: Schritte nach Rückabwicklung als zurückgenommen markiert")
    except Exception as e:
        err.append(f"m89 redo Ausnahme: {e}")
        _m89_tl.ctx = None
    finally:
        for sid in made:
            _m89_orig_x("DELETE FROM m89_change WHERE step_id=?", (sid,))
            _m89_orig_x("DELETE FROM m89_file WHERE step_id=?", (sid,))
            _m89_orig_x("DELETE FROM m89_step WHERE id=?", (sid,))
        _m89_orig_x("DELETE FROM customers WHERE kdnr='_ST89R'")
    return err


HOOK_SELFTEST.append(_m89_selftest)
