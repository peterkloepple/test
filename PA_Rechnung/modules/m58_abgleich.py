# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m58_abgleich  v1.1.0 (ab Programm v3.7.1)
# v1.1.0: Programm-Update fuer die iPhone-App - der PC gibt seine Programmversion beim Abgleich weiter
#         (/sync/programm), die App legt sie in ihrem Programmordner ab und startet sie beim naechsten Oeffnen.
# Abgleich zwischen zwei Installationen (PC = Hauptgeraet, iPhone/iPad/zweiter PC = Mobilgeraet), beide arbeiten
# offline mit eigener Datenbank. Beim Abgleich werden nur Aenderungen ausgetauscht, in beide Richtungen.
#  - Jede Zeile jeder Datentabelle bekommt eine weltweit eindeutige ID (sync_row.uid) und eine Version
#    (Lamport-Uhr ver + Geraet dev). SQLite-Trigger erfassen JEDE Aenderung, egal welcher Programmteil sie macht.
#  - Geloeschte Zeilen werden als Grabstein (sync_tomb) weitergegeben.
#  - Verweise zwischen Tabellen (customer_id, invoice_id ...) werden beim Senden in IDs uebersetzt und beim
#    Empfangen in die lokalen Nummern zurueck (die Zeilennummern duerfen auf beiden Geraeten verschieden sein).
#  - Konflikt (beide Seiten haben dieselbe Zeile geaendert): die neuere Aenderung gewinnt, die andere Fassung
#    wird in sync_konflikt aufgehoben und angezeigt. Festgeschriebene Rechnungen werden nie ueberschrieben.
#  - Gleicher Datensatz auf beiden Seiten neu angelegt (z. B. Einstellung, eindeutige Nummer): wird zusammengefuehrt.
#  - Dateien (Belege, Rechnungs-PDFs, Projektdateien ...) werden nach Groesse/Zeit abgeglichen (nur neue/neuere).
#  - Nummernkreise: das Mobilgeraet bekommt eigene, lueckenlose Kreise (z. B. 2026-M001), damit offline nie
#    zwei Geraete dieselbe Rechnungsnummer vergeben (GoBD).
#  - Erstabgleich: das Mobilgeraet uebernimmt einmal den kompletten Stand des PCs (Daten + Dateien).
#  - Uebertragung ueber die Schnittstelle des PCs (m88, Abschnitt /sync/), eigener Zugang (Token-Art "sync"),
#    Adressen am Mobilgeraet einstellbar (WLAN, VPN, Internet) - sie werden der Reihe nach probiert.
#  - GoBD: das Aenderungsprotokoll (audit_log) bleibt je Geraet; uebernommene Aenderungen protokolliert jedes
#    Geraet selbst ("Abgleich von <Geraet>").
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import urllib.request
import urllib.error
import urllib.parse
import gzip as _gzip
import base64
import sqlite3
import secrets

M58_VERSION = "1.1.0"
M58_LOCK = threading.RLock()
M58_STATE = {"laeuft": False, "text": "", "letzter": None}
M58_BATCH = 1500

# tables that stay on each device (logs, caches, device access, mail fetched per device, folder scans)
M58_EXCLUDE = {
    "db_version", "db_migration_log", "audit_log", "m88_token", "m88_log", "m89_change", "m89_file", "m89_step",
    "m92_pin", "mail_inbox", "mail_privat", "mail_absender", "mail_log", "m99c_seen", "fints_pending", "eingang_log",
    "kal_cal", "kal_event", "kal_label", "unt_dirs", "unt_files", "vorlagen", "beleg_learn", "pending_belege",
}
# settings that belong to one device (numbers, access, folders, logins, layout, sync itself)
M58_SET_EXCL = re.compile(r"^(next_|sync_|m58|m88|m92|pin|ui_layout|fenster|win_|theme|zoom|tt_|mi_|mp_|mo_|gm_|smtp|imap|"
                          r"m94|fints|psd2|m93_|bk_last|backup|update|exe|pdf_dir|export_dir|eingang|ordner|pfad|path|kal_abos|"
                          r"kal_abo_seed|m84c_|m97_alt|gehalt_fix|m99b_bewertet|m72_heute|.*_dir$|.*_pass$|.*_pw$|.*_enc$)", re.I)   # *_enc: encrypted with the PIN of that device
# reference columns -> table (by column name, and per table where the name is ambiguous)
M58_FK = {
    "customer_id": "customers", "person_customer_id": "customers", "invoice_id": "invoices", "angebot_id": "invoices",
    "schluss_id": "invoices", "doc_id": "invoices", "project_id": "projects", "article_id": "articles",
    "entry_id": "project_entries", "beleg_id": "belege", "student_id": "students", "kurs_id": "kurse",
    "serie_id": "fahrt_serien", "fahrt_id": "fahrten", "fix_id": "fixkosten", "bank_tx_id": "bank_tx",
    "mahnung_id": "mahnungen", "raum_id": "m74_raum", "asset_id": "assets", "art_id": "m75_art",
    "pruefling_id": "m75_pruefling", "kalk_id": "m41_kalk", "bom_id": "m78_bom", "buchung_id": "m42_buchung",
    "kasse_id": "m81_kasse", "abschluss_id": "m81_abschluss", "feld_id": "m85_feld", "regel_id": "m86_regel",
    "artikel_id": "m42_artikel", "lager_id": "m42_artikel",
}
M58_FK_T = {("invoices", "ref_id"): "invoices", ("m74_service", "geraet_id"): "m74_geraet",
            ("m75_pruefung", "geraet_id"): "m75_geraet", ("briefe", "vorlage_id"): None}
# file folders inside the data folder that are NOT copied
M58_DIR_EXCL = {"backup", "export", "_papierkorb", "e-mails", "privat-mails", "versionen", "programm", "tmp", "_tmp",
                "logs", "__pycache__", "_m39_test", "_sync_tmp"}
M58_DIR_FILE_MAX = 200 * 1024 * 1024


# ---------------------------------------------------------------------------- schema / device
def m58_schema():
    x("CREATE TABLE IF NOT EXISTS sync_me (dev TEXT)")
    x("CREATE TABLE IF NOT EXISTS sync_clock (n INTEGER)")
    x("CREATE TABLE IF NOT EXISTS sync_flag (a INTEGER)")
    x("CREATE TABLE IF NOT EXISTS sync_row (tbl TEXT, rid INTEGER, uid TEXT, ver INTEGER, dev TEXT, lc INTEGER, PRIMARY KEY (tbl, rid))")
    x("CREATE INDEX IF NOT EXISTS ix_sync_row_uid ON sync_row(uid)")
    x("CREATE INDEX IF NOT EXISTS ix_sync_row_lc ON sync_row(lc)")
    x("CREATE TABLE IF NOT EXISTS sync_tomb (uid TEXT PRIMARY KEY, tbl TEXT, ver INTEGER, dev TEXT, lc INTEGER)")
    x("CREATE TABLE IF NOT EXISTS sync_peer (dev TEXT PRIMARY KEY, name TEXT, rolle TEXT, my_sent INTEGER DEFAULT 0, "
      "their_recv INTEGER DEFAULT 0, zuletzt TEXT, adresse TEXT, info TEXT)")
    x("CREATE TABLE IF NOT EXISTS sync_konflikt (id INTEGER PRIMARY KEY, zeit TEXT, tbl TEXT, uid TEXT, info TEXT, verlierer TEXT, "
      "erledigt INTEGER DEFAULT 0)")
    x("CREATE TABLE IF NOT EXISTS sync_log (id INTEGER PRIMARY KEY, zeit TEXT, peer TEXT, gesendet INTEGER, empfangen INTEGER, "
      "dateien_hin INTEGER, dateien_her INTEGER, konflikte INTEGER, ok INTEGER, text TEXT)")
    if not q("SELECT n FROM sync_clock", one=True):
        x("INSERT INTO sync_clock (n) VALUES (0)")
    if not q("SELECT a FROM sync_flag", one=True):
        x("INSERT INTO sync_flag (a) VALUES (0)")
    if not q("SELECT dev FROM sync_me", one=True):
        x("INSERT INTO sync_me (dev) VALUES (?)", (uuid.uuid4().hex[:16],))


HOOK_SCHEMA.append(m58_schema)
M58_EXCLUDE |= {"sync_me", "sync_clock", "sync_flag", "sync_row", "sync_tomb", "sync_peer", "sync_konflikt", "sync_log"}


def m58_me():
    return (q("SELECT dev FROM sync_me", one=True) or {}).get("dev") or ""


def m58_cfg():
    c = get_settings().get("sync_cfg") or {}
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except Exception:
            c = {}
    c.setdefault("aktiv", False)
    c.setdefault("rolle", "haupt")            # haupt = PC (server), mobil = this device syncs with a PC
    c.setdefault("adressen", [])
    c.setdefault("token", "")
    c.setdefault("auto_min", 15)
    c.setdefault("beim_start", True)
    c.setdefault("dateien", True)
    c.setdefault("programm", True)            # v1.1.0: mobile app takes newer program versions from the PC
    c.setdefault("name", "")
    return c


def m58_cfg_save(c):
    set_setting("sync_cfg", c)


def m58_tables():
    out = []
    for (t,) in CON.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        if t in M58_EXCLUDE or t.startswith(("sync_", "_")):
            continue
        out.append(t)
    return sorted(out)


def _m58_info(t):
    cols = [r[1] for r in CON.execute(f"PRAGMA table_info({t})").fetchall()]
    pk = [r[1] for r in sorted(CON.execute(f"PRAGMA table_info({t})").fetchall(), key=lambda r: r[5]) if r[5]]
    types = {r[1]: (r[2] or "").upper() for r in CON.execute(f"PRAGMA table_info({t})").fetchall()}
    intpk = len(pk) == 1 and types.get(pk[0]) == "INTEGER"
    return cols, pk, intpk


def _m58_fk(t, c):
    if (t, c) in M58_FK_T:
        return M58_FK_T[(t, c)]
    return M58_FK.get(c)


# ---------------------------------------------------------------------------- triggers
def m58_enable():
    """create change triggers for all data tables and give every existing row an id (version 0 = not changed)"""
    me = m58_me()
    with DB_LOCK:
        for t in m58_tables():
            _, pk, intpk = _m58_info(t)
            stale = "" if intpk else f"DELETE FROM sync_row WHERE tbl='{t}' AND rid NOT IN (SELECT rowid FROM \"{t}\");"
            CON.execute(f'''CREATE TRIGGER IF NOT EXISTS sync_i_{t} AFTER INSERT ON "{t}" WHEN (SELECT a FROM sync_flag)=0 BEGIN
                {stale}
                UPDATE sync_clock SET n=n+1;
                INSERT OR REPLACE INTO sync_row (tbl, rid, uid, ver, dev, lc) VALUES ('{t}', NEW.rowid,
                  COALESCE((SELECT uid FROM sync_row WHERE tbl='{t}' AND rid=NEW.rowid), lower(hex(randomblob(16)))),
                  (SELECT n FROM sync_clock), (SELECT dev FROM sync_me), (SELECT n FROM sync_clock)); END''')
            CON.execute(f'''CREATE TRIGGER IF NOT EXISTS sync_u_{t} AFTER UPDATE ON "{t}" WHEN (SELECT a FROM sync_flag)=0 BEGIN
                UPDATE sync_clock SET n=n+1;
                INSERT OR REPLACE INTO sync_row (tbl, rid, uid, ver, dev, lc) VALUES ('{t}', NEW.rowid,
                  COALESCE((SELECT uid FROM sync_row WHERE tbl='{t}' AND rid=OLD.rowid), lower(hex(randomblob(16)))),
                  (SELECT n FROM sync_clock), (SELECT dev FROM sync_me), (SELECT n FROM sync_clock));
                DELETE FROM sync_row WHERE tbl='{t}' AND rid=OLD.rowid AND OLD.rowid<>NEW.rowid; END''')
            CON.execute(f'''CREATE TRIGGER IF NOT EXISTS sync_d_{t} AFTER DELETE ON "{t}" WHEN (SELECT a FROM sync_flag)=0 BEGIN
                UPDATE sync_clock SET n=n+1;
                INSERT OR REPLACE INTO sync_tomb (uid, tbl, ver, dev, lc) SELECT uid, '{t}', (SELECT n FROM sync_clock),
                  (SELECT dev FROM sync_me), (SELECT n FROM sync_clock) FROM sync_row WHERE tbl='{t}' AND rid=OLD.rowid;
                DELETE FROM sync_row WHERE tbl='{t}' AND rid=OLD.rowid; END''')
            CON.execute(f"INSERT INTO sync_row (tbl, rid, uid, ver, dev, lc) SELECT '{t}', rowid, lower(hex(randomblob(16))), 0, ?, 0 "
                        f"FROM \"{t}\" WHERE rowid NOT IN (SELECT rid FROM sync_row WHERE tbl='{t}')", (me,))
        CON.commit()


def m58_disable_triggers():
    with DB_LOCK:
        for (n,) in CON.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'sync\\_%' ESCAPE '\\'").fetchall():
            CON.execute(f"DROP TRIGGER IF EXISTS {n}")
        CON.commit()


# ---------------------------------------------------------------------------- export of changes
def _m58_uid_of(t, rid):
    r = CON.execute("SELECT uid FROM sync_row WHERE tbl=? AND rid=?", (t, rid)).fetchone()
    return r[0] if r else None


def _m58_rid_of(uid):
    r = CON.execute("SELECT tbl, rid FROM sync_row WHERE uid=?", (uid,)).fetchone()
    return (r[0], r[1]) if r else (None, None)


def _m58_pack_row(t, rid, info, keep_rid=False):
    cols, pk, intpk = info
    row = CON.execute(f'SELECT * FROM "{t}" WHERE rowid=?', (rid,)).fetchone()
    if row is None:
        return None
    d = {}
    for c, v in zip(cols, row):
        if intpk and c == pk[0] and not keep_rid:
            continue
        tgt = _m58_fk(t, c)
        if tgt and isinstance(v, int) and v:
            u = _m58_uid_of(tgt, v)
            d[c] = {"$u": u} if u else v
        elif isinstance(v, bytes):
            d[c] = {"$b": base64.b64encode(v).decode()}
        else:
            d[c] = v
    if t == "settings" and M58_SET_EXCL.match(str(d.get("k") or "")):
        return None
    return d


def m58_changes_since(lc_from, limit=M58_BATCH, peer=None, keep_rid=False):
    """-> (rows, upto). rows sorted by local change counter; rows last changed by the receiving peer are left out"""
    out, upto = [], lc_from
    infos = {}
    tabs = set(m58_tables())
    with DB_LOCK:
        live = CON.execute("SELECT tbl, rid, uid, ver, dev, lc FROM sync_row WHERE lc>? ORDER BY lc LIMIT ?", (lc_from, limit)).fetchall()
        dead = CON.execute("SELECT uid, tbl, ver, dev, lc FROM sync_tomb WHERE lc>? ORDER BY lc LIMIT ?", (lc_from, limit)).fetchall()
        ev = sorted([("r",) + tuple(r) for r in live] + [("d",) + tuple(r) for r in dead], key=lambda e: e[-1])[:limit]
        for e in ev:
            upto = max(upto, e[-1])
            if e[0] == "r":
                _, t, rid, uid, ver, dev, lc = e
                if t not in tabs or (peer and dev == peer):
                    continue
                info = infos.get(t) or infos.setdefault(t, _m58_info(t))
                d = _m58_pack_row(t, rid, info, keep_rid)
                if d is None:
                    continue
                r_ = {"t": t, "u": uid, "v": ver, "d": dev, "r": d}
                if keep_rid:
                    r_["rid"] = rid
                out.append(r_)
            else:
                _, uid, t, ver, dev, lc = e
                if t not in tabs or (peer and dev == peer):
                    continue
                out.append({"t": t, "u": uid, "v": ver, "d": dev, "x": 1})
    return out, upto


def m58_full_export(after_rowid=0, limit=4000):
    """initial copy for a new mobile device: every live row with its id (in sync_row order)"""
    out = []
    infos = {}
    tabs = set(m58_tables())
    with DB_LOCK:
        rows = CON.execute("SELECT rowid, tbl, rid, uid, ver, dev FROM sync_row WHERE rowid>? ORDER BY rowid LIMIT ?", (after_rowid, limit)).fetchall()
        last = after_rowid
        for srid, t, rid, uid, ver, dev in rows:
            last = srid
            if t not in tabs:
                continue
            info = infos.get(t) or infos.setdefault(t, _m58_info(t))
            d = _m58_pack_row(t, rid, info, keep_rid=True)
            if d is not None:
                out.append({"t": t, "u": uid, "v": ver, "d": dev, "r": d, "rid": rid})
        clock = CON.execute("SELECT n FROM sync_clock").fetchone()[0]
    return {"rows": out, "next": last if len(rows) == limit else None, "clock": clock}


# ---------------------------------------------------------------------------- import of changes
def _m58_locked(t, rid):
    try:
        if t == "invoices":
            r = CON.execute("SELECT locked FROM invoices WHERE rowid=?", (rid,)).fetchone()
            return bool(r and r[0])
        if t == "items":
            r = CON.execute("SELECT i.locked FROM items it JOIN invoices i ON i.id=it.invoice_id WHERE it.rowid=?", (rid,)).fetchone()
            return bool(r and r[0])
    except sqlite3.Error:
        pass
    return False


def _m58_unique_match(t, err, vals):
    """UNIQUE/PK conflict -> rowid of the existing local row with the same key (same record created on both sides)"""
    m = re.search(r"(?:UNIQUE|PRIMARY KEY) constraint failed: (.+)$", str(err))
    if not m:
        return None
    cols = [p.split(".", 1)[1].strip() for p in m.group(1).split(",") if "." in p]
    if not cols or any(c not in vals for c in cols):
        return None
    r = CON.execute(f'SELECT rowid FROM "{t}" WHERE ' + " AND ".join(f'"{c}" IS ?' for c in cols), [vals[c] for c in cols]).fetchone()
    return r[0] if r else None


def m58_apply(rows, src_name="", initial=False, conflict_since=None):
    """apply received rows. -> dict(neu, geaendert, geloescht, konflikte, uebersprungen)
    conflict_since: local change counter up to which the other side already knows our rows (only the PC passes it -
    conflicts are detected and kept there, where both versions are known)"""
    st = {"neu": 0, "geaendert": 0, "geloescht": 0, "konflikte": 0, "uebersprungen": 0}
    if not rows:
        return st
    tabs = set(m58_tables())
    infos = {}
    pend = []      # (table, rowid, column, uid) - reference to a row that arrives later in this batch
    audit = []
    with DB_LOCK:
        CON.execute("UPDATE sync_flag SET a=1")
        try:
            clock = CON.execute("SELECT n FROM sync_clock").fetchone()[0]
            for r in rows:
                t, uid, ver, dev = r.get("t"), r.get("u"), int(r.get("v") or 0), r.get("d") or ""
                if t not in tabs or not uid:
                    st["uebersprungen"] += 1
                    continue
                clock = max(clock, ver)
                loc = CON.execute("SELECT rid, ver, dev, lc FROM sync_row WHERE uid=?", (uid,)).fetchone()
                if r.get("x"):
                    if not loc:
                        CON.execute("INSERT OR REPLACE INTO sync_tomb (uid, tbl, ver, dev, lc) VALUES (?,?,?,?,?)", (uid, t, ver, dev, clock + 1))
                        clock += 1
                        continue
                    if (loc[1], loc[2]) > (ver, dev):
                        _m58_conflict(t, uid, "Gelöscht auf " + src_name + ", hier später geändert – bleibt erhalten", None)
                        st["konflikte"] += 1
                        continue
                    if _m58_locked(t, loc[0]):
                        _m58_conflict(t, uid, "Festgeschriebene Rechnung – Löschen vom anderen Gerät abgelehnt", None)
                        st["konflikte"] += 1
                        continue
                    CON.execute(f'DELETE FROM "{t}" WHERE rowid=?', (loc[0],))
                    CON.execute("DELETE FROM sync_row WHERE uid=?", (uid,))
                    clock += 1
                    CON.execute("INSERT OR REPLACE INTO sync_tomb (uid, tbl, ver, dev, lc) VALUES (?,?,?,?,?)", (uid, t, ver, dev, clock))
                    st["geloescht"] += 1
                    audit.append((t, loc[0], "gelöscht"))
                    continue
                tomb = CON.execute("SELECT ver, dev FROM sync_tomb WHERE uid=?", (uid,)).fetchone()
                if tomb and (tomb[0], tomb[1]) >= (ver, dev):
                    st["uebersprungen"] += 1
                    continue
                if loc and (loc[1], loc[2]) >= (ver, dev):
                    if conflict_since is not None and loc[3] > conflict_since and loc[2] != dev and (loc[1], loc[2]) != (ver, dev):
                        _m58_conflict(t, uid, f"Auf beiden Geräten geändert – Fassung hier ist neuer und gilt, Fassung von {src_name} verworfen",
                                      r.get("r"))
                        st["konflikte"] += 1
                    st["uebersprungen"] += 1          # we have this or a newer state
                    continue
                info = infos.get(t) or infos.setdefault(t, _m58_info(t))
                cols, pk, intpk = info
                vals = {}
                for c, v in (r.get("r") or {}).items():
                    if c not in cols:
                        continue
                    if isinstance(v, dict) and "$u" in v:
                        tt, rr = _m58_rid_of(v["$u"])
                        if rr is None:
                            pend.append([t, None, c, v["$u"], uid])
                            v = None
                        else:
                            v = rr
                    elif isinstance(v, dict) and "$b" in v:
                        v = base64.b64decode(v["$b"])
                    vals[c] = v
                if initial and intpk and r.get("rid"):
                    vals[pk[0]] = int(r["rid"])
                if loc:
                    rid = loc[0]
                    if _m58_locked(t, rid):
                        cur = _m58_pack_row(t, rid, info)
                        _m58_conflict(t, uid, f"Festgeschriebene Rechnung – Änderung von {src_name} abgelehnt", r.get("r"), cur)
                        st["konflikte"] += 1
                        continue
                    if conflict_since is not None and loc[3] > conflict_since and loc[2] != dev:
                        # changed here as well since then -> remote is newer and wins; keep our version for review
                        _m58_conflict(t, uid, f"Auf beiden Geräten geändert – Fassung von {src_name} ist neuer und gilt",
                                      _m58_pack_row(t, rid, info))
                        st["konflikte"] += 1
                    sets = [c for c in vals if not (intpk and c == pk[0])]
                    if sets:
                        CON.execute(f'UPDATE "{t}" SET ' + ", ".join(f'"{c}"=?' for c in sets) + " WHERE rowid=?", [vals[c] for c in sets] + [rid])
                    st["geaendert"] += 1
                    audit.append((t, rid, "geändert"))
                else:
                    ks = list(vals)
                    try:
                        cur_ = CON.execute(f'INSERT INTO "{t}" (' + ", ".join(f'"{c}"' for c in ks) + ") VALUES (" + ",".join("?" * len(ks)) + ")",
                                           [vals[c] for c in ks])
                        rid = cur_.lastrowid
                        st["neu"] += 1
                        audit.append((t, rid, "neu"))
                    except sqlite3.IntegrityError as e:
                        rid = _m58_unique_match(t, e, vals)
                        if rid is None:
                            _m58_conflict(t, uid, f"Konnte nicht übernommen werden: {e}", r.get("r"))
                            st["konflikte"] += 1
                            continue
                        if _m58_locked(t, rid):
                            st["uebersprungen"] += 1
                        else:
                            sets = [c for c in ks if not (intpk and c == pk[0])]
                            if sets:
                                CON.execute(f'UPDATE "{t}" SET ' + ", ".join(f'"{c}"=?' for c in sets) + " WHERE rowid=?",
                                            [vals[c] for c in sets] + [rid])
                            st["geaendert"] += 1
                    CON.execute("DELETE FROM sync_row WHERE tbl=? AND rid=?", (t, rid))
                clock += 1
                CON.execute("INSERT OR REPLACE INTO sync_row (tbl, rid, uid, ver, dev, lc) VALUES (?,?,?,?,?,?)",
                            (t, rid, uid, ver, dev, 0 if initial else clock))
                for p_ in pend:
                    if p_[4] == uid and p_[1] is None:
                        p_[1] = rid
            # references to rows that came later in the batch
            for t, rid, c, ref_uid, _u in pend:
                _tt, rr = _m58_rid_of(ref_uid)
                if rid is not None and rr is not None:
                    CON.execute(f'UPDATE "{t}" SET "{c}"=? WHERE rowid=?', (rr, rid))
            CON.execute("UPDATE sync_clock SET n=?", (clock,))
            CON.execute("UPDATE sync_flag SET a=0")
            CON.commit()
        except Exception:
            CON.rollback()
            CON.execute("UPDATE sync_flag SET a=0")
            CON.commit()
            raise
    try:
        DB_GEN[0] += 1
    except NameError:
        pass
    # GoBD: every device logs what it took over (own hash chain)
    fn = globals().get("m51_log")
    if callable(fn) and audit and not initial:
        ber = {"invoices": "Dokument", "belege": "Beleg", "customers": "Kunde", "items": "Position"}
        for t, rid, art in audit[:500]:
            if t in ber:
                try:
                    fn(ber[t], rid, f"Abgleich ({art})", "", "", "", f"von {src_name}")
                except Exception:
                    pass
    return st


def _m58_conflict(t, uid, info, verlierer, aktuell=None):
    try:
        CON.execute("INSERT INTO sync_konflikt (zeit, tbl, uid, info, verlierer) VALUES (?,?,?,?,?)",
                    (now_iso(), t, uid, info, json.dumps({"verworfen": verlierer, "aktuell": aktuell}, ensure_ascii=False, default=str)[:200000]))
    except sqlite3.Error:
        pass


# ---------------------------------------------------------------------------- numbers of the mobile device
def m58_mobile_numbers():
    """own gap-free number ranges on the mobile device: 2026-012 -> 2026-M001, KD-1003 -> KD-M001, A2026-002 -> A2026-M001"""
    s = get_settings()
    done = []
    for k, v in list(s.items()):
        if not k.startswith("next_") or not isinstance(v, str):
            continue
        m = re.fullmatch(r"(.*?)(\d+)", v)
        if not m or "M" in m.group(1)[-1:]:
            continue
        nv = m.group(1) + "M" + "1".zfill(max(3, len(m.group(2)) - 1))
        set_setting(k, nv)
        done.append(f"{k}: {v} → {nv}")
    return done


# ---------------------------------------------------------------------------- files
def m58_file_dirs():
    out = []
    try:
        for n in sorted(os.listdir(DATA_DIR)):
            p = os.path.join(DATA_DIR, n)
            if os.path.isdir(p) and n.lower() not in M58_DIR_EXCL and not n.startswith("."):
                out.append(n)
    except Exception:
        pass
    return out


def m58_manifest():
    files = {}
    for d in m58_file_dirs():
        root = os.path.join(DATA_DIR, d)
        for dp, dn, fn in os.walk(root):
            dn[:] = [x_ for x_ in dn if not x_.startswith(".") and x_.lower() not in M58_DIR_EXCL]
            for f in fn:
                if f.startswith((".", "~$")) or f.endswith((".tmp", ".part")):
                    continue
                p = os.path.join(dp, f)
                try:
                    stt = os.stat(p)
                except OSError:
                    continue
                if stt.st_size > M58_DIR_FILE_MAX:
                    continue
                rel = os.path.relpath(p, DATA_DIR).replace("\\", "/")
                files[rel] = [stt.st_size, int(stt.st_mtime)]
    return files


def _m58_safe_rel(rel):
    rel = (rel or "").replace("\\", "/").lstrip("/")
    root = os.path.abspath(DATA_DIR)
    p = os.path.abspath(os.path.join(root, rel))
    if os.path.commonpath([p, root]) != root or rel.split("/", 1)[0].lower() in M58_DIR_EXCL or ".." in rel.split("/"):
        raise ValueError("Pfad nicht erlaubt.")
    return p


def m58_manifest_compare(theirs):
    """server side: which files does the PC need from the device (need), which does the device get (give) - newer wins"""
    mine = m58_manifest()
    need = [rel for rel, (sz, mt) in theirs.items() if rel not in mine or mt > mine[rel][1] + 2]
    give = [[rel, sz, mt] for rel, (sz, mt) in mine.items() if rel not in theirs or mt > theirs[rel][1] + 2]
    return {"need": need, "give": give}


def m58_file_write(rel, data, mtime=None):
    p = _m58_safe_rel(rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, p)
    if mtime:
        try:
            os.utime(p, (int(mtime), int(mtime)))
        except OSError:
            pass


# ---------------------------------------------------------------------------- server side (PC) - called from m88
def m58_server_route(h, method, p, qs, tok):
    """/sync/... on the interface server. tok = token row (typ 'sync') or None (only /sync/pair, /sync/ping)"""
    if p == "/sync/ping":
        return h._out(200, {"ok": True, "app": "PA Rechnung", "version": APP_VERSION, "dev": m58_me(), "name": m58_cfg().get("name") or ""})
    if p == "/sync/pair" and method == "POST":
        d = h._json()
        code = re.sub(r"[^A-Z0-9]", "", (d.get("code") or "").upper())
        pr = M88.get("pair")
        if not (pr and time.time() < pr["ablauf"] and len(code) == 8 and secrets.compare_digest(code, pr["code"])):
            h._fail()
            return h._out(403, {"ok": False, "error": "Kopplungscode falsch oder abgelaufen – am PC neu erzeugen."})
        M88["pair"] = None
        nm = (d.get("name") or "Mobilgerät").strip()[:60]
        tid, token = m88_token_new(nm + " (Abgleich)", "schreiben", "sync", 3650)
        c = m58_cfg()
        if not c.get("aktiv"):
            c.update(aktiv=True, rolle="haupt")
            m58_cfg_save(c)
        m58_enable()
        x("INSERT OR REPLACE INTO sync_peer (dev, name, rolle, zuletzt, info) VALUES (?,?,?,?,?)",
          (str(d.get("dev") or "")[:40], nm, "mobil", now_iso(), "gekoppelt"))
        return h._out(200, {"ok": True, "token": token, "dev": m58_me(), "name": m58_cfg().get("name") or "PC", "version": APP_VERSION})
    if not tok or tok.get("typ") != "sync":
        h._fail()
        return h._out(401, {"ok": False, "error": "Abgleich-Zugang fehlt oder ungültig – Gerät neu koppeln."})
    if p == "/sync/full" and method == "POST":
        d = h._json()
        m58_enable()
        return h._out(200, dict(m58_full_export(int(d.get("after") or 0)), ok=True))
    if p == "/sync/changes" and method == "POST":
        d = h._json(limit=200 << 20)
        peer = str(d.get("dev") or "")[:40]
        m58_enable()
        st = m58_apply(d.get("changes") or [], d.get("name") or peer, conflict_since=int(d.get("ack") or 0))
        rows, upto = m58_changes_since(int(d.get("ack") or 0), peer=peer)
        x("INSERT OR REPLACE INTO sync_peer (dev, name, rolle, my_sent, their_recv, zuletzt, adresse, info) VALUES (?,?,?,?,?,?,?,?)",
          (peer, (d.get("name") or "")[:60], "mobil", upto, int(d.get("upto") or 0), now_iso(), h._ip(), json.dumps(st)))
        return h._out(200, {"ok": True, "changes": rows, "upto": upto, "applied": st, "dev": m58_me()})
    if p == "/sync/manifest" and method == "POST":
        d = h._json(limit=100 << 20)
        return h._out(200, dict(m58_manifest_compare(d.get("files") or {}), ok=True))
    if p == "/sync/file" and method == "GET":
        fp = _m58_safe_rel(qs.get("rel"))
        if not os.path.isfile(fp):
            return h._out(404, {"ok": False, "error": "Datei fehlt"})
        return h._out(200, open(fp, "rb").read(), "application/octet-stream", {"X-Mtime": str(int(os.path.getmtime(fp)))})
    if p == "/sync/file" and method == "POST":
        n = int(h.headers.get("Content-Length") or 0)
        if n > M58_DIR_FILE_MAX:
            return h._out(413, {"ok": False, "error": "Datei zu groß"})
        data = h.rfile.read(n) if n > 0 else b""
        m58_file_write(qs.get("rel"), data, qs.get("mtime"))
        return h._out(200, {"ok": True})
    if p == "/sync/programm" and method == "GET":
        pk = m58_prog_paket()
        return h._out(200, {"ok": True, "version": pk["ver"], "sha256": pk["sha"], "groesse": len(pk["zip"])})
    if p == "/sync/programm/paket" and method == "GET":
        return h._out(200, m58_prog_paket()["zip"], "application/zip")
    return h._out(404, {"ok": False, "error": "Unbekannter Abgleich-Befehl"})


# ---------------------------------------------------------------------------- program update for the mobile app (v1.1.0)
# The PC hands its own program files (core, modules, ui, assets) to a paired mobile device. The iPhone app keeps
# them in its own program folder (PA_RECHNUNG_PROG_DIR, set by the app) and starts the newer version at the next
# app start. Without that folder (PC, second PC) nothing is fetched - a PC is updated with the .paupdate file.
M58_PROG = {"ver": None, "zip": b"", "sha": ""}


def _m58_vt(v):
    return tuple(int(n) for n in re.findall(r"\d+", str(v or ""))[:4])


def m58_prog_paket():
    """ZIP of the running program version (built once, then cached)"""
    if M58_PROG["ver"] == APP_VERSION and M58_PROG["zip"]:
        return M58_PROG
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.abspath(__file__), f"PA_Rechnung_v{APP_VERSION}.py")
        z.write(res_path("ui.html"), "ui.html")
        for sub, src in (("modules", modules_dir() if os.path.isdir(modules_dir()) else res_path("modules")),
                         ("ui", ui_dir()), ("assets", res_path("assets"))):
            for root, dirs, files in os.walk(src):
                dirs[:] = sorted(d_ for d_ in dirs if d_ != "__pycache__")
                for fn in sorted(files):
                    if not fn.endswith((".pyc", ".pyo")):
                        fp = os.path.join(root, fn)
                        z.write(fp, sub + "/" + os.path.relpath(fp, src).replace(os.sep, "/"))
    data = buf.getvalue()
    M58_PROG.update(ver=APP_VERSION, zip=data, sha=hashlib.sha256(data).hexdigest())
    return M58_PROG


def m58_prog_dir():
    return os.environ.get("PA_RECHNUNG_PROG_DIR") or ""


def _m58_prog_json(name, default):
    try:
        with open(os.path.join(m58_prog_dir(), name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def m58_prog_state():
    st = {"version": APP_VERSION, "selbst": bool(m58_prog_dir()), "neu": None, "defekt": []}
    if st["selbst"]:
        a = _m58_prog_json("aktiv.json", {}) or {}
        bad = [e for e in (_m58_prog_json("defekt.json", []) or []) if isinstance(e, dict)]
        if _m58_vt(a.get("version")) > _m58_vt(APP_VERSION) and not any(e.get("sha") == a.get("sha") for e in bad):
            st["neu"] = a.get("version")
        st["defekt"] = [e.get("version") for e in bad]
    return st


def m58_prog_update(base, token):
    """mobile app only: fetch a newer program version from the PC. Returns the new version (waits for the next
    app start) or None."""
    d = m58_prog_dir()
    if not d:
        return None
    try:
        info = _m58_json(base, "/sync/programm", token=token, timeout=30)
    except ValueError:
        return None                                 # PC older than v3.7.1 - cannot hand out its program
    ver, sha = str(info.get("version") or ""), str(info.get("sha256") or "")
    if not info.get("ok") or not re.fullmatch(r"\d+(\.\d+){1,3}", ver) or _m58_vt(ver) <= _m58_vt(APP_VERSION):
        return None
    if any(isinstance(e, dict) and e.get("sha") == sha for e in (_m58_prog_json("defekt.json", []) or [])):
        return None                                 # this very package did not start on this device - not again
    if (_m58_prog_json("aktiv.json", {}) or {}).get("sha") == sha and os.path.isdir(os.path.join(d, ver)):
        return ver                                  # already here, waits for the app restart
    M58_STATE["text"] = f"Programm v{ver} wird geladen …"
    _s, data, _h = _m58_http(base, "/sync/programm/paket", token=token, timeout=600)
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("Programm-Update unvollständig übertragen.")
    z = zipfile.ZipFile(io.BytesIO(data))
    names = [n for n in z.namelist() if not n.endswith("/")]
    if f"PA_Rechnung_v{ver}.py" not in names or "ui.html" not in names or not any(n.startswith("modules/m01") for n in names):
        raise ValueError("Programm-Update unvollständig.")
    tmp, dst = os.path.join(d, "_neu"), os.path.join(d, ver)
    shutil.rmtree(tmp, ignore_errors=True)
    for n in names:
        if n.startswith(("/", "\\")) or ":" in n or ".." in n.replace("\\", "/").split("/"):
            raise ValueError("Programm-Update enthält unzulässige Pfade.")
        fp = os.path.join(tmp, *n.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as f:
            f.write(z.read(n))
    shutil.rmtree(dst, ignore_errors=True)
    os.replace(tmp, dst)
    with open(os.path.join(d, "aktiv.json"), "w", encoding="utf-8") as f:
        json.dump({"version": ver, "sha": sha, "zeit": now_iso(), "von": base}, f)
    return ver


def m58_app_quit(d):
    """iPhone app: close the app so that the next start runs the new program version"""
    if not m58_prog_dir():
        raise ValueError("Nur in der iPhone-App.")
    threading.Timer(0.7, lambda: os._exit(0)).start()
    return {"ok": True}


# ---------------------------------------------------------------------------- client side (mobile device)
def _m58_http(base, path, body=None, raw=None, token="", timeout=60, method=None, ctype="application/json"):
    data = None
    hd = {"User-Agent": "PA-Rechnung-Abgleich", "Accept-Encoding": "gzip"}
    if token:
        hd["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        hd["Content-Type"] = ctype
    elif raw is not None:
        data = raw
        hd["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=hd, method=method or ("POST" if data is not None else "GET"))
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=timeout) as r:
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                b = _gzip.decompress(b)
            return r.status, b, r.headers
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            msg = json.loads(b).get("error")
        except Exception:
            msg = ""
        raise ValueError(msg or f"PC meldet Fehler {e.code}.")


def _m58_json(base, path, body=None, token="", timeout=120):
    st_, b, _h = _m58_http(base, path, body=body, token=token, timeout=timeout)
    return json.loads(b or b"{}")


def m58_find_server(c=None):
    c = c or m58_cfg()
    errs = []
    for a in c.get("adressen") or []:
        a = (a or "").strip().rstrip("/")
        if not a:
            continue
        if not re.match(r"^https?://", a, re.I):
            a = "http://" + a
        try:
            j = _m58_json(a, "/sync/ping", timeout=4)
            if j.get("ok"):
                return a, j
        except Exception as e:
            errs.append(f"{a}: {str(e)[:80]}")
    raise ValueError("PC nicht erreichbar" + (" (" + "; ".join(errs) + ")" if errs else " – keine Adresse eingetragen."))


def m58_pair(d):
    """mobile device: couple with the PC (code from the PC) and take over its complete state"""
    c = m58_cfg()
    adr = [a.strip() for a in (d.get("adressen") or c.get("adressen") or []) if a and a.strip()]
    if not adr:
        raise ValueError("Bitte mindestens eine Adresse des PCs eintragen (z. B. http://192.168.1.20:8780).")
    c["adressen"] = adr
    base, info = m58_find_server(c)
    j = _m58_json(base, "/sync/pair", {"code": d.get("code"), "name": d.get("name") or c.get("name") or "Mobilgerät", "dev": m58_me()})
    if not j.get("ok"):
        raise ValueError(j.get("error") or "Kopplung fehlgeschlagen.")
    c.update(aktiv=True, rolle="mobil", token=j["token"], pc_dev=j.get("dev"), pc_name=j.get("name"), name=d.get("name") or c.get("name") or "")
    m58_cfg_save(c)
    r = m58_initial_copy(base, j["token"], j.get("dev"))
    return dict(r, ok=True, pc=j.get("name"))


def m58_initial_copy(base, token, pc_dev):
    """replace all data of this device by the PC's state (keeps device settings), then own number ranges"""
    M58_STATE.update(laeuft=True, text="Erstabgleich: Daten werden geholt …")
    try:
        rows, after, clock = [], 0, 0
        while True:
            j = _m58_json(base, "/sync/full", {"after": after}, token=token, timeout=300)
            rows += j.get("rows") or []
            clock = max(clock, int(j.get("clock") or 0))
            M58_STATE["text"] = f"Erstabgleich: {len(rows)} Datensätze geholt …"
            if not j.get("next"):
                break
            after = j["next"]
        m58_enable()
        keep = {k: v for k, v in get_settings().items() if M58_SET_EXCL.match(k)}
        with DB_LOCK:
            CON.execute("UPDATE sync_flag SET a=1")
            for t in m58_tables():
                CON.execute(f'DELETE FROM "{t}"')
            CON.execute("DELETE FROM sync_row")
            CON.execute("DELETE FROM sync_tomb")
            CON.execute("UPDATE sync_flag SET a=0")
            CON.commit()
        st = m58_apply(rows, "PC", initial=True)
        for k, v in keep.items():
            set_setting(k, v)
        with DB_LOCK:
            CON.execute("UPDATE sync_clock SET n=MAX(n, ?)", (clock,))
            # what the PC has is "already received"; nothing of the copy goes back
            CON.execute("UPDATE sync_row SET lc=0")
            CON.execute("INSERT OR REPLACE INTO sync_peer (dev, name, rolle, my_sent, their_recv, zuletzt, adresse, info) VALUES (?,?,?,?,?,?,?,?)",
                        (pc_dev or "", m58_cfg().get("pc_name") or "PC", "haupt", 0, clock, now_iso(), base, "Erstabgleich"))
            CON.commit()
        nums = m58_mobile_numbers()
        files = m58_sync_files(base, token) if m58_cfg().get("dateien", True) else {"hin": 0, "her": 0}
        txt = f"Erstabgleich fertig: {len(rows)} Datensätze, {files['her']} Dateien vom PC."
        x("INSERT INTO sync_log (zeit, peer, gesendet, empfangen, dateien_hin, dateien_her, konflikte, ok, text) VALUES (?,?,?,?,?,?,?,?,?)",
          (now_iso(), "PC", 0, len(rows), files["hin"], files["her"], st["konflikte"], 1, txt))
        M58_STATE.update(letzter={"zeit": now_iso(), "ok": True, "text": txt})
        return {"datensaetze": len(rows), "nummern": nums, "dateien": files, "text": txt}
    finally:
        M58_STATE.update(laeuft=False, text="")


def m58_sync_files(base, token):
    mine = m58_manifest()
    j = _m58_json(base, "/sync/manifest", {"files": mine}, token=token, timeout=300)
    hin = her = 0
    for rel in j.get("need") or []:
        try:
            fp = _m58_safe_rel(rel)
            _m58_http(base, "/sync/file?rel=" + urllib.parse.quote(rel) + "&mtime=" + str(int(os.path.getmtime(fp))),
                      raw=open(fp, "rb").read(), token=token, timeout=300)
            hin += 1
        except Exception:
            traceback.print_exc()
    for rel, sz, mt in j.get("give") or []:
        try:
            _s, b, hd = _m58_http(base, "/sync/file?rel=" + urllib.parse.quote(rel), token=token, timeout=300)
            m58_file_write(rel, b, hd.get("X-Mtime") or mt)
            her += 1
        except Exception:
            traceback.print_exc()
    return {"hin": hin, "her": her}


def m58_sync_now(grund="Knopf"):
    c = m58_cfg()
    if c.get("rolle") != "mobil" or not c.get("token"):
        raise ValueError("Dieses Gerät ist nicht mit einem PC gekoppelt.")
    with M58_LOCK:
        if M58_STATE["laeuft"]:
            return {"ok": True, "laeuft": True}
        M58_STATE.update(laeuft=True, text="Verbinde mit dem PC …")
    res = {"zeit": now_iso(), "ok": False, "text": "", "gesendet": 0, "empfangen": 0, "konflikte": 0, "dateien": {"hin": 0, "her": 0}}
    try:
        base, info = m58_find_server(c)
        pc = q("SELECT * FROM sync_peer WHERE rolle='haupt' ORDER BY zuletzt DESC LIMIT 1", one=True) or {}
        my_sent, their_recv = int(pc.get("my_sent") or 0), int(pc.get("their_recv") or 0)
        rounds = 0
        while True:
            rounds += 1
            prev = (my_sent, their_recv)
            M58_STATE["text"] = f"Abgleich läuft … (Runde {rounds})"
            mine, upto_mine = m58_changes_since(my_sent, peer=c.get("pc_dev"))
            j = _m58_json(base, "/sync/changes", {"dev": m58_me(), "name": c.get("name") or "Mobilgerät", "changes": mine,
                                                    "ack": their_recv, "upto": upto_mine}, token=c["token"], timeout=600)
            if not j.get("ok"):
                raise ValueError(j.get("error") or "Abgleich abgelehnt.")
            res["gesendet"] += len(mine)
            res["konflikte"] += int((j.get("applied") or {}).get("konflikte") or 0)
            st = m58_apply(j.get("changes") or [], c.get("pc_name") or "PC")
            res["empfangen"] += len(j.get("changes") or [])
            res["konflikte"] += st["konflikte"]
            my_sent = max(my_sent, upto_mine)
            their_recv = max(their_recv, int(j.get("upto") or 0))
            x("INSERT OR REPLACE INTO sync_peer (dev, name, rolle, my_sent, their_recv, zuletzt, adresse, info) VALUES (?,?,?,?,?,?,?,?)",
              (j.get("dev") or c.get("pc_dev") or "", c.get("pc_name") or "PC", "haupt", my_sent, their_recv, now_iso(), base, grund))
            if (my_sent, their_recv) == prev or rounds > 500:
                break
        if c.get("dateien", True):
            M58_STATE["text"] = "Dateien werden abgeglichen …"
            res["dateien"] = m58_sync_files(base, c["token"])
        neu = None
        if c.get("programm", True):
            try:
                neu = m58_prog_update(base, c["token"])
            except Exception as e:
                res["programm_fehler"] = str(e)[:200]
        res["ok"] = True
        res["text"] = (f"{res['gesendet']} Änderungen gesendet, {res['empfangen']} empfangen, Dateien {res['dateien']['hin']} hin / "
                       f"{res['dateien']['her']} her" + (f", {res['konflikte']} Konflikt(e)" if res["konflikte"] else "")
                       + (f" – Programm v{neu} geladen: App schließen und neu öffnen" if neu else "")
                       + (f" – Programm-Update: {res['programm_fehler']}" if res.get("programm_fehler") else ""))
    except Exception as e:
        if not isinstance(e, ValueError):
            traceback.print_exc()
        res["text"] = str(e)[:300]
    finally:
        try:
            x("INSERT INTO sync_log (zeit, peer, gesendet, empfangen, dateien_hin, dateien_her, konflikte, ok, text) VALUES (?,?,?,?,?,?,?,?,?)",
              (res["zeit"], c.get("pc_name") or "PC", res["gesendet"], res["empfangen"], res["dateien"]["hin"], res["dateien"]["her"],
               res["konflikte"], 1 if res["ok"] else 0, res["text"]))
        except Exception:
            pass
        M58_STATE.update(laeuft=False, text="", letzter=res)
    return dict(res, ok=res["ok"], error=None if res["ok"] else res["text"])


def _m58_loop():
    time.sleep(20)
    first = True
    while True:
        try:
            c = m58_cfg()
            if c.get("aktiv") and first:
                m58_enable()
            if c.get("aktiv") and c.get("rolle") == "mobil" and c.get("token"):
                last = (M58_STATE.get("letzter") or {}).get("zeit") or ""
                due = first and c.get("beim_start", True)
                if not due and int(c.get("auto_min") or 0) > 0:
                    try:
                        due = not last or (datetime.datetime.now() - datetime.datetime.fromisoformat(last.replace(" ", "T")[:19])).total_seconds() >= int(c["auto_min"]) * 60
                    except Exception:
                        due = True
                if due and not M58_STATE["laeuft"]:
                    try:
                        m58_sync_now("automatisch")
                    except Exception:
                        pass
            first = False
        except Exception:
            traceback.print_exc()
        time.sleep(60)


HOOK_START.append(_m58_loop)


# ---------------------------------------------------------------------------- program API (UI)
def _m58_state():
    st = {k: M58_STATE[k] for k in ("laeuft", "text", "letzter")}
    if not st.get("letzter"):                       # after a program start: last result from the protocol
        r = q("SELECT zeit, ok, text FROM sync_log ORDER BY id DESC LIMIT 1", one=True)
        if r:
            st["letzter"] = {"zeit": r["zeit"], "ok": bool(r["ok"]), "text": r["text"]}
    return st


def m58_view():
    c = m58_cfg()
    peers = q("SELECT dev, name, rolle, zuletzt, adresse, info FROM sync_peer ORDER BY zuletzt DESC")
    toks = []
    try:
        toks = q("SELECT id, name, erstellt, zuletzt, zuletzt_ip FROM m88_token WHERE typ='sync' AND aktiv=1 ORDER BY id DESC")
    except Exception:
        pass
    pend = 0
    try:
        p_ = q("SELECT my_sent FROM sync_peer WHERE rolle='haupt' ORDER BY zuletzt DESC LIMIT 1", one=True) or {}
        # only changes made on THIS device (rows received from the PC also get a new local clock value)
        ms, me = int(p_.get("my_sent") or 0), m58_me()
        # device-specific settings (PIN, logins, number ranges ...) are recorded but never sent - not counted
        rows = q("SELECT r.tbl, s.k FROM sync_row r LEFT JOIN settings s ON r.tbl='settings' AND s.rowid=r.rid WHERE r.lc>? AND r.dev=?", (ms, me))
        pend = sum(1 for r in rows if not (r["tbl"] == "settings" and M58_SET_EXCL.match(str(r.get("k") or "")))) + \
               (q("SELECT COUNT(*) n FROM sync_tomb WHERE lc>? AND dev=? AND tbl<>'settings'", (ms, me), one=True) or {}).get("n", 0)
    except Exception:
        pass
    m88c = {}
    try:
        m88c = m88_cfg()
    except Exception:
        pass
    return {"ok": True, "cfg": {k: v for k, v in c.items() if k != "token"}, "gekoppelt": bool(c.get("token")),
            "me": m58_me(), "peers": peers, "zugaenge": toks, "offen": pend, "state": _m58_state(),
            "log": q("SELECT * FROM sync_log ORDER BY id DESC LIMIT 20"),
            "konflikte": q("SELECT id, zeit, tbl, uid, info FROM sync_konflikt WHERE erledigt=0 ORDER BY id DESC LIMIT 100"),
            "server": {"aktiv": bool(m88c.get("aktiv")), "port": m88c.get("port"), "modus": m88c.get("modus")},
            "plattform": sys.platform, "programm": m58_prog_state()}


def m58_save(d):
    c = m58_cfg()
    if "adressen" in d:
        c["adressen"] = [a.strip() for a in (d.get("adressen") or []) if a and a.strip()][:8]
    for k in ("auto_min", "beim_start", "dateien", "name", "programm"):
        if k in d:
            c[k] = d[k]
    m58_cfg_save(c)
    return m58_view()


def m58_unpair(d):
    c = m58_cfg()
    c.update(token="", aktiv=c.get("rolle") == "haupt")
    m58_cfg_save(c)
    return m58_view()


def m58_conflict_get(cid):
    r = q("SELECT * FROM sync_konflikt WHERE id=?", (int(cid),), one=True)
    if not r:
        raise ValueError("Konflikt nicht gefunden.")
    r["verlierer"] = json.loads(r["verlierer"] or "{}")
    return r


HOOK_GET["/api/sync"] = lambda h, qs: h._send(200, m58_view())
HOOK_GET["/api/sync/konflikt"] = lambda h, qs: h._send(200, m58_conflict_get(qs.get("id")))
HOOK_POST["/api/sync/speichern"] = lambda h, d: h._send(200, m58_save(d))
HOOK_POST["/api/sync/koppeln"] = lambda h, d: h._send(200, m58_pair(d))
HOOK_POST["/api/sync/jetzt"] = lambda h, d: h._send(200, m58_sync_now("Knopf"))
HOOK_POST["/api/sync/entkoppeln"] = lambda h, d: h._send(200, m58_unpair(d))
HOOK_POST["/api/sync/konflikt_erledigt"] = lambda h, d: h._send(200, (x("UPDATE sync_konflikt SET erledigt=1 WHERE id=? OR ?", (int(d.get("id") or 0), 1 if d.get("alle") else 0)), m58_view())[1])
HOOK_POST["/api/sync/beenden"] = lambda h, d: h._send(200, m58_app_quit(d))
HOOK_BOOT.append(lambda d: d.update(sync={"rolle": m58_cfg().get("rolle"), "gekoppelt": bool(m58_cfg().get("token")), "laeuft": M58_STATE["laeuft"]}))


def m58_selftest():
    err = []
    try:
        if m58_mobile_numbers.__doc__ is None:
            err.append("m58: Doku fehlt")
        m = re.fullmatch(r"(.*?)(\d+)", "2026-012")
        if (m.group(1) + "M" + "1".zfill(max(3, len(m.group(2)) - 1))) != "2026-M001":
            err.append("m58: Mobil-Nummernkreis falsch")
        for bad in ("../daten.sqlite", "Backup/x.sqlite", "Belege/../../x"):
            try:
                _m58_safe_rel(bad)
                err.append(f"m58: unsicherer Pfad angenommen ({bad})")
            except ValueError:
                pass
        if "invoices" not in m58_tables() or "audit_log" in m58_tables():
            err.append("m58: Tabellenauswahl falsch")
        if not (_m58_vt("3.10.0") > _m58_vt("3.9.9") > _m58_vt("3.9")):
            err.append("m58: Versionsvergleich falsch")
        nm = zipfile.ZipFile(io.BytesIO(m58_prog_paket()["zip"])).namelist()
        if f"PA_Rechnung_v{APP_VERSION}.py" not in nm or "modules/m58_abgleich.py" not in nm or "ui.html" not in nm:
            err.append("m58: Programm-Paket unvollstaendig")
    except Exception as e:
        err.append(f"m58 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m58_selftest)
print(f"INIT m58_abgleich v{M58_VERSION}")
