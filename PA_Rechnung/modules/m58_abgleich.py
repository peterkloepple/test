# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m58_abgleich  v1.2.0 (ab Programm v3.8.1, erstmals v3.7.0)
# v1.2.0: Programm-Update fuer die iPhone-App - der PC gibt seine Programmversion beim Abgleich weiter
#         (/sync/programm), die App legt sie in ihrem Programmordner ab und startet sie beim naechsten Oeffnen.
# v1.1.0: schneller, einfacher, automatisch
#  - PC suchen: das Mobilgeraet findet den PC selbst (UDP-Rundruf Port 8781, sonst Netz-Suche ueber /sync/ping);
#    beim Koppeln nur noch "PC suchen" + Code. Wechselt die IP des PCs, wird er automatisch wiedergefunden.
#  - Live: PC-Aenderungen kommen per Warte-Anfrage (/sync/wait, long poll) in 2-3 s aufs Geraet, Aenderungen
#    am Geraet gehen ca. 8 s nach der letzten Eingabe zum PC. Intervall zusaetzlich (auch jede Minute).
#  - Schneller: JSON gzip-komprimiert (beide Richtungen), groessere Pakete, alle PC-Adressen gleichzeitig pruefen,
#    Dateien gebuendelt (ZIP-Pakete bis 16 MB) und parallel (3 gleichzeitig), nur seit dem letzten Abgleich
#    geaenderte Dateien pruefen (einmal am Tag komplett). Abgleich-Zugang zaehlt nicht zum Anfragen-Limit (m88).
#  - Bei Fehlern automatisch neuer Versuch mit wachsendem Abstand (15 s ... 5 min).
#  - Neu empfangene Daten: offene Programmseiten laden sich selbst neu (/api/sync/gen) - nicht waehrend einer Eingabe.
#  - Menue-Aufbau links (ui_menu, aus m63) wird mit abgeglichen; Positionen/Breiten bleiben je Geraet (ui_layout).
#  - Alte Gegenstelle (v3.7.x) wird erkannt (Faehigkeiten im /sync/ping) und wie bisher bedient.
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
import socket as _m58_socket
import zipfile as _m58_zip
import io as _m58_io
import zlib as _m58_zlib
import concurrent.futures as _m58_cf

M58_VERSION = "1.2.0"
M58_LOCK = threading.RLock()
M58_STATE = {"laeuft": False, "text": "", "letzter": None}
M58_BATCH = 5000
M58_CAPS = ["gz", "zip", "wait", "fsince", "addrs"]
M58_DISC_PORT = 8781
M58_DISC_MSG = b"PA-SYNC-DISCOVER 1"
M58_CHUNK = 16 << 20            # bytes per file package
M58_CHUNK_N = 300               # files per file package
M58_WORKERS = 3                 # parallel file packages
M58_QUIET = 8                   # live: seconds without edits before the changes go to the PC
M58_FILE_EVERY = 600            # files at least every 10 minutes (and whenever data was exchanged)
M58_FULL_EVERY = 86400          # complete file comparison once a day
M58_WAIT = 25                   # long poll seconds
M58_STORED = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".pdf", ".zip", ".gz", ".7z", ".rar",
              ".mp4", ".mov", ".m4a", ".mp3", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".paupdate")
M58_WAKE = threading.Event()
M58_RT = {"live": False, "base": "", "caps": [], "fehler": 0, "naechster": 0.0, "grund": "", "erreichbar": None,
          "letzt_sync": 0.0, "f_last": 0.0, "push_ok": 0.0, "wake_t": 0.0, "gen": 0}
M58_LIVE = {}                   # PC side: device -> time of its last wait request

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
    c.setdefault("live", True)               # v1.1.0: changes are exchanged right away
    c.setdefault("auto_adr", [])             # v1.1.0: addresses reported by the PC itself (kept up to date)
    c.setdefault("last_base", "")
    c.setdefault("beim_start", True)
    c.setdefault("dateien", True)
    c.setdefault("programm", True)            # v1.2.0: mobile app takes newer program versions from the PC
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
    if st["neu"] or st["geaendert"] or st["geloescht"]:
        M58_RT["gen"] = int(M58_RT.get("gen") or 0) + 1        # v1.1.0: open program pages reload themselves
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


def m58_manifest(since=None):
    """rel -> [size, mtime]; since: only files created/changed after this time (own clock)"""
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
                if since and max(stt.st_mtime, stt.st_ctime) < since - 5:
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


def _m58_zip(items):
    """items [(rel, path)] -> zip bytes with _meta.json {arcname: [rel, mtime]}"""
    bio = _m58_io.BytesIO()
    meta = {}
    with _m58_zip.ZipFile(bio, "w") as z:
        for i, (rel, fp) in enumerate(items):
            try:
                mt = int(os.path.getmtime(fp))
                with open(fp, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            arc = f"f/{i}"
            if rel.lower().endswith(M58_STORED):
                z.writestr(arc, data, compress_type=_m58_zip.ZIP_STORED)
            else:
                z.writestr(arc, data, compress_type=_m58_zip.ZIP_DEFLATED, compresslevel=5)
            meta[arc] = [rel, mt]
        z.writestr("_meta.json", json.dumps(meta, ensure_ascii=False))
    return bio.getvalue()


def _m58_unzip(raw):
    """-> (count, errors)"""
    n, err = 0, []
    with _m58_zip.ZipFile(_m58_io.BytesIO(raw)) as z:
        meta = json.loads(z.read("_meta.json").decode("utf-8"))
        for arc, (rel, mt) in meta.items():
            try:
                if z.getinfo(arc).file_size > M58_DIR_FILE_MAX:
                    raise ValueError("zu groß")
                m58_file_write(rel, z.read(arc), mt)
                n += 1
            except Exception as e:
                err.append(f"{rel}: {e}"[:200])
    return n, err


def _m58_chunks(items):
    """items [(rel, size)] -> [[rel, ...], ...] packages of max M58_CHUNK bytes / M58_CHUNK_N files"""
    out, cur, sz = [], [], 0
    for rel, n in items:
        n = int(n or 0)
        if cur and (sz + n > M58_CHUNK or len(cur) >= M58_CHUNK_N):
            out.append(cur)
            cur, sz = [], 0
        cur.append(rel)
        sz += n
    if cur:
        out.append(cur)
    return out


def _m58_ips():
    fn = globals().get("lan_ips")
    try:
        return fn() if callable(fn) else []
    except Exception:
        return []


def _m58_pairing():
    pr = (globals().get("M88") or {}).get("pair")
    return bool(pr and time.time() < pr.get("ablauf", 0))


def _m58_my_addrs():
    """PC: own addresses in the home network (sent to the device so it can find the PC again)"""
    try:
        m = globals().get("M88") or {}
        port = m.get("port") or m88_cfg().get("port") or 8780
        if m88_cfg().get("modus") != "lan":
            return []
        return [f"http://{ip}:{port}" for ip in _m58_ips()]
    except Exception:
        return []


def _m58_has_new(since, peer):
    """PC: are there changes the device does not have yet (not made by the device itself)?"""
    with DB_LOCK:
        r = CON.execute("SELECT 1 FROM sync_row WHERE lc>? AND dev<>? LIMIT 1", (since, peer)).fetchone()
        if not r:
            r = CON.execute("SELECT 1 FROM sync_tomb WHERE lc>? AND dev<>? LIMIT 1", (since, peer)).fetchone()
    return bool(r)


def _m58_out(h, code, obj):
    """JSON answer, gzip-compressed when the device accepts it"""
    b = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    if len(b) > 2048 and "gzip" in (h.headers.get("Accept-Encoding") or "").lower():
        return h._out(code, _gzip.compress(b, 5), "application/json; charset=utf-8", {"Content-Encoding": "gzip"})
    return h._out(code, b)


def _m58_rjson(h, limit=1 << 20):
    """JSON request body, plain or gzip"""
    b = h._body(limit)
    if (h.headers.get("Content-Encoding") or "").lower() == "gzip" and b:
        dz = _m58_zlib.decompressobj(16 + _m58_zlib.MAX_WBITS)
        b = dz.decompress(b, limit * 8)
        if dz.unconsumed_tail:
            raise ValueError("Anfrage zu groß.")
    if not b:
        return {}
    d = json.loads(b.decode("utf-8"))
    if not isinstance(d, dict):
        raise ValueError("JSON-Objekt erwartet.")
    return d


# ---------------------------------------------------------------------------- server side (PC) - called from m88
def m58_server_route(h, method, p, qs, tok):
    """/sync/... on the interface server. tok = token row (typ 'sync') or None (only /sync/pair, /sync/ping)"""
    if p == "/sync/ping":
        return h._out(200, {"ok": True, "app": "PA Rechnung", "version": APP_VERSION, "dev": m58_me(),
                            "name": m58_cfg().get("name") or _m58_socket.gethostname(), "caps": M58_CAPS,
                            "pairing": _m58_pairing(), "rolle": m58_cfg().get("rolle"), "addrs": _m58_my_addrs()})
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
        return h._out(200, {"ok": True, "token": token, "dev": m58_me(), "name": m58_cfg().get("name") or _m58_socket.gethostname() or "PC",
                            "version": APP_VERSION, "caps": M58_CAPS, "addrs": _m58_my_addrs()})
    if not tok or tok.get("typ") != "sync":
        h._fail()
        return h._out(401, {"ok": False, "error": "Abgleich-Zugang fehlt oder ungültig – Gerät neu koppeln."})
    if p == "/sync/full" and method == "POST":
        d = _m58_rjson(h)
        m58_enable()
        return _m58_out(h, 200, dict(m58_full_export(int(d.get("after") or 0), max(500, min(10000, int(d.get("limit") or 4000)))), ok=True))
    if p == "/sync/wait" and method == "GET":
        # v1.1.0 live: answer as soon as the PC has something new for the device (or after t seconds)
        since, peer = int(qs.get("since") or 0), str(qs.get("dev") or "")[:40]
        end = time.time() + max(1, min(M58_WAIT, int(qs.get("t") or M58_WAIT)))
        while time.time() < end:
            M58_LIVE[peer] = time.time()
            if _m58_has_new(since, peer):
                time.sleep(1.5)                       # collect what belongs together (e.g. invoice + items)
                return _m58_out(h, 200, {"ok": True, "neu": True})
            time.sleep(1.0)
        M58_LIVE[peer] = time.time()
        return _m58_out(h, 200, {"ok": True, "neu": False})
    if p == "/sync/changes" and method == "POST":
        d = _m58_rjson(h, limit=200 << 20)
        peer = str(d.get("dev") or "")[:40]
        m58_enable()
        st = m58_apply(d.get("changes") or [], d.get("name") or peer, conflict_since=int(d.get("ack") or 0))
        rows, upto = m58_changes_since(int(d.get("ack") or 0), peer=peer)
        x("INSERT OR REPLACE INTO sync_peer (dev, name, rolle, my_sent, their_recv, zuletzt, adresse, info) VALUES (?,?,?,?,?,?,?,?)",
          (peer, (d.get("name") or "")[:60], "mobil", upto, int(d.get("upto") or 0), now_iso(), h._ip(), json.dumps(st)))
        M58_LIVE[peer] = time.time()
        return _m58_out(h, 200, {"ok": True, "changes": rows, "upto": upto, "applied": st, "dev": m58_me()})
    if p == "/sync/manifest" and method == "POST":
        d = _m58_rjson(h, limit=100 << 20)
        return _m58_out(h, 200, dict(m58_manifest_compare(d.get("files") or {}), ok=True))
    if p == "/sync/manifest2" and method == "POST":
        # v1.1.0: device sends only its changed files; PC answers with what it needs and what changed here since "since"
        d = _m58_rjson(h, limit=100 << 20)
        now = time.time()
        need = []
        for rel, v in (d.get("files") or {}).items():
            try:
                fp = _m58_safe_rel(rel)
            except ValueError:
                continue
            try:
                lm = os.path.getmtime(fp)
            except OSError:
                lm = None
            if lm is None or float(v[1]) > lm + 2:
                need.append(rel)
        since = d.get("since")
        give = [[rel, sz, mt] for rel, (sz, mt) in m58_manifest(float(since) if since else None).items()]
        return _m58_out(h, 200, {"ok": True, "need": need, "give": give, "now": now})
    if p == "/sync/files/get" and method == "POST":
        d = _m58_rjson(h, limit=20 << 20)
        items = []
        for rel in d.get("rels") or []:
            try:
                fp = _m58_safe_rel(rel)
            except ValueError:
                continue
            if os.path.isfile(fp):
                items.append((rel, fp))
        return h._out(200, _m58_zip(items), "application/zip")
    if p == "/sync/files/put" and method == "POST":
        n = int(h.headers.get("Content-Length") or 0)
        if n > M58_DIR_FILE_MAX + (64 << 20):
            return _m58_out(h, 413, {"ok": False, "error": "Paket zu groß"})
        raw = h.rfile.read(n) if n > 0 else b""
        cnt, err = _m58_unzip(raw)
        return _m58_out(h, 200, {"ok": True, "n": cnt, "fehler": err[:20]})
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


# ---------------------------------------------------------------------------- program update for the mobile app (v1.2.0)
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
        return None                                 # PC older than v3.8.1 - cannot hand out its program
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
def _m58_http(base, path, body=None, raw=None, token="", timeout=60, method=None, ctype="application/json", gz=False):
    data = None
    hd = {"User-Agent": "PA-Rechnung-Abgleich", "Accept-Encoding": "gzip"}
    if token:
        hd["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        hd["Content-Type"] = ctype
        if gz and len(data) > 4096:                   # v1.1.0: only to a PC that understands it (caps "gz")
            data = _gzip.compress(data, 5)
            hd["Content-Encoding"] = "gzip"
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


def _m58_json(base, path, body=None, token="", timeout=120, gz=False):
    st_, b, _h = _m58_http(base, path, body=body, token=token, timeout=timeout, gz=gz)
    return json.loads(b or b"{}")


def _m58_norm(a):
    a = (a or "").strip().rstrip("/")
    if a and not re.match(r"^https?://", a, re.I):
        a = "http://" + a
    return a


def _m58_addr_list(c):
    """last working address first, then the ones the PC reported, then the ones entered by hand"""
    out = []
    for a in [c.get("last_base")] + list(c.get("auto_adr") or []) + list(c.get("adressen") or []):
        a = _m58_norm(a)
        if a and a not in out:
            out.append(a)
    return out


def m58_find_server(c=None, timeout=3):
    """v1.1.0: all addresses are tried at the same time, the first answer of the right PC wins"""
    c = c or m58_cfg()
    adr = _m58_addr_list(c)
    if not adr:
        raise ValueError("PC nicht erreichbar – keine Adresse bekannt. „PC suchen“ drücken oder Adresse eintragen.")
    want = c.get("pc_dev") if c.get("token") else None
    errs = []
    ex = _m58_cf.ThreadPoolExecutor(max_workers=min(8, len(adr)))
    try:
        fs = {ex.submit(_m58_json, a, "/sync/ping", None, "", timeout): a for a in adr}
        for f in _m58_cf.as_completed(fs):
            a = fs[f]
            try:
                j = f.result()
            except Exception as e:
                errs.append(f"{a}: {str(e)[:60]}")
                continue
            if not j.get("ok"):
                continue
            if want and j.get("dev") and j.get("dev") != want:
                errs.append(f"{a}: anderer PC ({j.get('name') or j.get('dev')})")
                continue
            m58_remember_server(a, j)
            return a, j
    finally:
        ex.shutdown(wait=False)
    raise ValueError("PC nicht erreichbar" + (" (" + "; ".join(errs[:4]) + ")" if errs else "."))


def m58_remember_server(base, info):
    """keep the working address and the addresses the PC reports - written only when something changed"""
    M58_RT.update(base=base, caps=list(info.get("caps") or []), erreichbar=True)
    c = m58_cfg()
    ch = False
    if c.get("last_base") != base:
        c["last_base"] = base
        ch = True
    addrs = [_m58_norm(a) for a in (info.get("addrs") or []) if a][:8]
    if addrs and addrs != list(c.get("auto_adr") or []):
        c["auto_adr"] = addrs
        ch = True
    if ch and c.get("token"):
        m58_cfg_save(c)


def m58_discover(timeout=1.5, scan=True):
    """v1.1.0: find PCs with PA Rechnung in the home network.
    1. UDP broadcast (port 8781) - answers within a second
    2. if nobody answers (firewall, iPhone without broadcast): ask /sync/ping on every address of the own /24 network"""
    me = m58_me()
    found = {}
    ips = _m58_ips()
    try:
        s_ = _m58_socket.socket(_m58_socket.AF_INET, _m58_socket.SOCK_DGRAM)
        s_.setsockopt(_m58_socket.SOL_SOCKET, _m58_socket.SO_BROADCAST, 1)
        s_.settimeout(0.3)
        for t in {"255.255.255.255"} | {ip.rsplit(".", 1)[0] + ".255" for ip in ips}:
            try:
                s_.sendto(M58_DISC_MSG, (t, M58_DISC_PORT))
            except OSError:
                pass
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = s_.recvfrom(4096)
            except _m58_socket.timeout:
                continue
            except OSError:
                break
            try:
                j = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if j.get("app") == "PA Rechnung" and j.get("dev") and j.get("dev") != me:
                found[j["dev"]] = dict(j, base=f"http://{addr[0]}:{int(j.get('port') or 8780)}", ip=addr[0])
        s_.close()
    except Exception:
        pass
    if not found and scan and ips:
        ports = {8780}
        for a in _m58_addr_list(m58_cfg()):
            m = re.match(r"^https?://[^/:]+:(\d+)", a)
            if m:
                ports.add(int(m.group(1)))
        hosts = []
        for ip in ips[:2]:
            pre = ip.rsplit(".", 1)[0]
            hosts += [f"http://{pre}.{i}:{pt}" for i in range(1, 255) for pt in sorted(ports) if f"{pre}.{i}" != ip]

        def probe(b):
            try:
                return b, _m58_json(b, "/sync/ping", timeout=0.8)
            except Exception:
                return b, None
        with _m58_cf.ThreadPoolExecutor(max_workers=64) as ex:
            for b, j in ex.map(probe, hosts):
                if j and j.get("ok") and j.get("app") == "PA Rechnung" and j.get("dev") and j.get("dev") != me:
                    found.setdefault(j["dev"], dict(j, base=b, ip=b.split("//", 1)[1].split(":", 1)[0]))
    out = []
    for j in found.values():
        out.append({k: j.get(k) for k in ("dev", "name", "base", "ip", "version", "pairing", "rolle")})
    return sorted(out, key=lambda r: (not r.get("pairing"), r.get("rolle") == "mobil", r.get("name") or ""))


def m58_rediscover():
    """device: the paired PC is not reachable at the known addresses -> look for it in the network"""
    c = m58_cfg()
    want = c.get("pc_dev")
    for r in m58_discover(scan=True):
        if want and r.get("dev") == want:
            try:
                j = _m58_json(r["base"], "/sync/ping", timeout=3)
                m58_remember_server(r["base"], j)
                return r["base"]
            except Exception:
                pass
    return None


def m58_pair(d):
    """mobile device: couple with the PC (code from the PC) and take over its complete state"""
    c = m58_cfg()
    adr = [a.strip() for a in (d.get("adressen") or c.get("adressen") or []) if a and a.strip()]
    sel = _m58_norm(d.get("base") or "")                   # v1.1.0: PC chosen from "PC suchen"
    if not adr and not sel:
        found = [r for r in m58_discover() if r.get("pairing")]
        if len(found) == 1:
            sel = found[0]["base"]
        else:
            raise ValueError("Kein PC zum Koppeln gefunden – am PC „Gerät koppeln“ drücken, dann hier „PC suchen“ "
                             "(oder die Adresse des PCs eintragen).")
    c.update(adressen=adr, last_base=sel or "", auto_adr=[], pc_dev="", token="")
    base, info = m58_find_server(c)
    j = _m58_json(base, "/sync/pair", {"code": d.get("code"), "name": d.get("name") or c.get("name") or "Mobilgerät", "dev": m58_me()})
    if not j.get("ok"):
        raise ValueError(j.get("error") or "Kopplung fehlgeschlagen.")
    c.update(aktiv=True, rolle="mobil", token=j["token"], pc_dev=j.get("dev"), pc_name=j.get("name"), name=d.get("name") or c.get("name") or "",
             last_base=base, auto_adr=[_m58_norm(a) for a in (j.get("addrs") or info.get("addrs") or [])][:8],
             f_my_since=0, f_pc_since=0, f_full=0)
    m58_cfg_save(c)
    M58_RT.update(base=base, caps=list(j.get("caps") or info.get("caps") or []), erreichbar=True, fehler=0, naechster=0.0)
    r = m58_initial_copy(base, j["token"], j.get("dev"))
    return dict(r, ok=True, pc=j.get("name"))


def m58_initial_copy(base, token, pc_dev):
    """replace all data of this device by the PC's state (keeps device settings), then own number ranges"""
    M58_STATE.update(laeuft=True, text="Erstabgleich: Daten werden geholt …")
    try:
        rows, after, clock = [], 0, 0
        gz = "gz" in (M58_RT.get("caps") or [])
        while True:
            j = _m58_json(base, "/sync/full", {"after": after, "limit": 8000}, token=token, timeout=300, gz=gz)
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
        files = m58_sync_files(base, token, voll=True) if m58_cfg().get("dateien", True) else {"hin": 0, "her": 0}
        txt = f"Erstabgleich fertig: {len(rows)} Datensätze, {files['her']} Dateien vom PC."
        x("INSERT INTO sync_log (zeit, peer, gesendet, empfangen, dateien_hin, dateien_her, konflikte, ok, text) VALUES (?,?,?,?,?,?,?,?,?)",
          (now_iso(), "PC", 0, len(rows), files["hin"], files["her"], st["konflikte"], 1, txt))
        M58_STATE.update(letzter={"zeit": now_iso(), "ok": True, "text": txt})
        return {"datensaetze": len(rows), "nummern": nums, "dateien": files, "text": txt}
    finally:
        M58_STATE.update(laeuft=False, text="")


def m58_sync_files(base, token, voll=False):
    """v1.1.0: only changed files, bundled into ZIP packages, 3 packages at the same time"""
    caps = M58_RT.get("caps") or []
    if "zip" not in caps or "fsince" not in caps:
        return _m58_sync_files_v1(base, token)
    c = m58_cfg()
    t0 = time.time()
    voll = voll or not c.get("f_my_since") or t0 - float(c.get("f_full") or 0) > M58_FULL_EVERY
    M58_STATE["text"] = "Dateien werden verglichen …" + (" (komplett)" if voll else "")
    mine = m58_manifest(None if voll else float(c["f_my_since"]))
    j = _m58_json(base, "/sync/manifest2", {"files": mine, "since": None if voll else float(c.get("f_pc_since") or 0)},
                  token=token, timeout=300, gz=True)
    need = [rel for rel in (j.get("need") or []) if rel in mine]
    give = []
    for rel, sz, mt in j.get("give") or []:
        try:
            fp = _m58_safe_rel(rel)
        except ValueError:
            continue
        try:
            lm = os.path.getmtime(fp)
        except OSError:
            lm = None
        if lm is None or float(mt) > lm + 2:
            give.append((rel, sz))
    up = _m58_chunks([(rel, mine[rel][0]) for rel in need])
    down = _m58_chunks(give)
    tot = len(need) + len(give)
    res = {"hin": 0, "her": 0, "fehler": 0}
    errs = []
    lk = threading.Lock()

    def prog():
        M58_STATE["text"] = f"Dateien: {res['hin'] + res['her']} von {tot} …"

    def do_up(ch):
        raw = _m58_zip([(rel, _m58_safe_rel(rel)) for rel in ch])
        _s, b, _h = _m58_http(base, "/sync/files/put", raw=raw, token=token, timeout=900)
        r = json.loads(b or b"{}")
        with lk:
            res["hin"] += int(r.get("n") or 0)
            errs.extend(r.get("fehler") or [])
            prog()

    def do_down(ch):
        _s, b, _h = _m58_http(base, "/sync/files/get", body={"rels": ch}, token=token, timeout=900)
        n, e = _m58_unzip(b)
        with lk:
            res["her"] += n
            errs.extend(e)
            prog()
    if tot:
        prog()
        with _m58_cf.ThreadPoolExecutor(max_workers=M58_WORKERS) as ex:
            fs = [ex.submit(do_up, ch) for ch in up] + [ex.submit(do_down, ch) for ch in down]
            for f in fs:
                try:
                    f.result()
                except Exception as e:
                    errs.append(str(e)[:200])
    res["fehler"] = len(errs)
    M58_RT["f_last"] = time.time()
    if not errs:
        c = m58_cfg()
        c.update(f_my_since=t0, f_pc_since=float(j.get("now") or 0), f_full=t0 if voll else float(c.get("f_full") or 0))
        m58_cfg_save(c)
    else:
        print("m58 Dateien:", "; ".join(errs[:5]))
    return res


def _m58_sync_files_v1(base, token):
    """file comparison with a PC on v3.7.x (one file per request)"""
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


def _m58_pc_peer():
    return q("SELECT * FROM sync_peer WHERE rolle='haupt' ORDER BY zuletzt DESC LIMIT 1", one=True) or {}


def _m58_pending():
    """number of changes made on THIS device that the PC does not have yet"""
    try:
        ms, me = int(_m58_pc_peer().get("my_sent") or 0), m58_me()
        # device-specific settings (PIN, logins, number ranges ...) are recorded but never sent - not counted
        rows = q("SELECT r.tbl, s.k FROM sync_row r LEFT JOIN settings s ON r.tbl='settings' AND s.rowid=r.rid WHERE r.lc>? AND r.dev=?", (ms, me))
        return sum(1 for r in rows if not (r["tbl"] == "settings" and M58_SET_EXCL.match(str(r.get("k") or "")))) + \
            (q("SELECT COUNT(*) n FROM sync_tomb WHERE lc>? AND dev=? AND tbl<>'settings'", (ms, me), one=True) or {}).get("n", 0)
    except Exception:
        return 0


def _m58_wake(grund):
    M58_RT.update(grund=grund, wake_t=time.time())
    M58_WAKE.set()


def m58_sync_now(grund="Knopf", dateien=None):
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
        M58_RT.update(fehler=0, naechster=0.0)
        gz = "gz" in (M58_RT.get("caps") or [])
        pc = _m58_pc_peer()
        my_sent, their_recv = int(pc.get("my_sent") or 0), int(pc.get("their_recv") or 0)
        rounds = 0
        while True:
            rounds += 1
            prev = (my_sent, their_recv)
            M58_STATE["text"] = f"Abgleich läuft … (Runde {rounds})"
            mine, upto_mine = m58_changes_since(my_sent, peer=c.get("pc_dev"))
            j = _m58_json(base, "/sync/changes", {"dev": m58_me(), "name": c.get("name") or "Mobilgerät", "changes": mine,
                                                    "ack": their_recv, "upto": upto_mine}, token=c["token"], timeout=600, gz=gz)
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
        if dateien is None:          # v1.1.0: files when data came/went, on request, at start, otherwise every 10 minutes
            dateien = grund in ("Knopf", "Programmstart") or res["gesendet"] or res["empfangen"] or \
                time.time() - M58_RT.get("f_last", 0) >= M58_FILE_EVERY
        if c.get("dateien", True) and dateien:
            M58_STATE["text"] = "Dateien werden abgeglichen …"
            res["dateien"] = m58_sync_files(base, c["token"])
        neu = None
        if c.get("programm", True) and (grund in ("Knopf", "Programmstart") or time.time() - M58_RT.get("p_last", 0) >= 600):
            M58_RT["p_last"] = time.time()
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
        f_ = M58_RT["fehler"] = int(M58_RT.get("fehler") or 0) + 1
        M58_RT.update(erreichbar=False, live=False, naechster=time.time() + min(300, 15 * 2 ** min(f_ - 1, 5)))
    finally:
        M58_RT["letzt_sync"] = time.time()
        try:
            x("INSERT INTO sync_log (zeit, peer, gesendet, empfangen, dateien_hin, dateien_her, konflikte, ok, text) VALUES (?,?,?,?,?,?,?,?,?)",
              (res["zeit"], c.get("pc_name") or "PC", res["gesendet"], res["empfangen"], res["dateien"]["hin"], res["dateien"]["her"],
               res["konflikte"], 1 if res["ok"] else 0, res["text"]))
        except Exception:
            pass
        M58_STATE.update(laeuft=False, text="", letzter=res)
    # v1.1.0: PC not found at the known addresses -> search the network (IP of the PC may have changed)
    if not res["ok"] and "nicht erreichbar" in res["text"] and M58_RT["fehler"] in (1, 3) or (not res["ok"] and M58_RT["fehler"] % 6 == 0):
        try:
            if m58_rediscover():
                M58_RT["naechster"] = 0.0
                _m58_wake("PC wiedergefunden")
        except Exception:
            traceback.print_exc()
    return dict(res, ok=res["ok"], error=None if res["ok"] else res["text"])


def _m58_loop():
    """device: start, live (after own edits / when the PC reports news), interval, retry with growing pause"""
    time.sleep(15)
    first = True
    last_n, last_change = None, 0.0
    while True:
        woke = M58_WAKE.wait(3)
        M58_WAKE.clear()
        try:
            c = m58_cfg()
            if c.get("aktiv") and first:
                m58_enable()
            if not (c.get("aktiv") and c.get("rolle") == "mobil" and c.get("token")):
                first = False
                continue
            now = time.time()
            with DB_LOCK:
                n = CON.execute("SELECT n FROM sync_clock").fetchone()[0]
            if n != last_n:
                if last_n is not None:
                    last_change = now
                last_n = n
            grund = ""
            if first and c.get("beim_start", True):
                grund = "Programmstart"
            elif woke and M58_RT.get("grund"):
                grund = M58_RT.get("grund")
            elif c.get("live", True) and last_change and now - last_change >= M58_QUIET and last_change > M58_RT.get("letzt_sync", 0):
                if _m58_pending() > 0:
                    grund = "Änderung hier"
                else:
                    last_change = 0.0
            if not grund and int(c.get("auto_min") or 0) > 0 and now - M58_RT.get("letzt_sync", 0) >= int(c["auto_min"]) * 60:
                grund = "Intervall"
            first = False
            M58_RT["grund"] = ""
            if not grund or M58_STATE["laeuft"]:
                continue
            if now < M58_RT.get("naechster", 0) and grund != "PC wiedergefunden":
                continue
            m58_sync_now(grund)
        except Exception:
            traceback.print_exc()


def _m58_push_loop():
    """device, live: a waiting request at the PC answers as soon as there is something new there"""
    time.sleep(25)
    while True:
        try:
            c = m58_cfg()
            if not (c.get("aktiv") and c.get("rolle") == "mobil" and c.get("token") and c.get("live", True)) \
                    or not M58_RT.get("base") or "wait" not in (M58_RT.get("caps") or []) or M58_RT.get("erreichbar") is False:
                M58_RT["live"] = False
                time.sleep(5)
                continue
            if M58_STATE["laeuft"]:
                time.sleep(1)
                continue
            since = int(_m58_pc_peer().get("their_recv") or 0)
            j = _m58_json(M58_RT["base"], f"/sync/wait?since={since}&dev={urllib.parse.quote(m58_me())}&t={M58_WAIT}",
                          token=c["token"], timeout=M58_WAIT + 15)
            M58_RT.update(live=True, push_ok=time.time())
            if j.get("neu") and not M58_STATE["laeuft"]:
                if time.time() - M58_RT.get("wake_t", 0) < 5:
                    time.sleep(5)
                _m58_wake("Änderung am PC")
                time.sleep(2)
        except Exception:
            M58_RT["live"] = False
            time.sleep(15)


def _m58_responder():
    """PC: answers the search of the devices (UDP 8781) while the interface is reachable in the home network"""
    sock, chk, want = None, 0.0, False
    while True:
        try:
            if time.time() - chk > 10:
                chk = time.time()
                try:
                    want = m58_cfg().get("rolle") != "mobil" and m88_running() and m88_cfg().get("modus") == "lan"
                except Exception:
                    want = False
                if want and sock is None:
                    sock = _m58_socket.socket(_m58_socket.AF_INET, _m58_socket.SOCK_DGRAM)
                    sock.bind(("0.0.0.0", M58_DISC_PORT))
                    sock.settimeout(2)
                    M58_RT["suche_aktiv"] = True
                if not want and sock is not None:
                    sock.close()
                    sock = None
                    M58_RT["suche_aktiv"] = False
            if sock is None:
                time.sleep(5)
                continue
            try:
                data, addr = sock.recvfrom(512)
            except _m58_socket.timeout:
                continue
            if data.strip() != M58_DISC_MSG:
                continue
            ans = {"app": "PA Rechnung", "dev": m58_me(), "name": m58_cfg().get("name") or _m58_socket.gethostname(),
                   "port": (globals().get("M88") or {}).get("port") or 8780, "pairing": _m58_pairing(),
                   "version": APP_VERSION, "rolle": m58_cfg().get("rolle")}
            sock.sendto(json.dumps(ans).encode("utf-8"), addr)
        except OSError as e:
            M58_RT["suche_aktiv"] = False
            M58_RT["suche_fehler"] = str(e)[:120]
            try:
                if sock:
                    sock.close()
            except Exception:
                pass
            sock = None
            time.sleep(30)
        except Exception:
            traceback.print_exc()
            time.sleep(10)


HOOK_START.append(_m58_push_loop)
HOOK_START.append(_m58_responder)
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
    pend = _m58_pending() if c.get("rolle") == "mobil" else 0
    now = time.time()
    for p_ in peers:
        p_["live"] = now - M58_LIVE.get(p_.get("dev") or "", 0) < 45
    m88c = {}
    try:
        m88c = m88_cfg()
    except Exception:
        pass
    return {"ok": True, "cfg": {k: v for k, v in c.items() if k != "token"}, "gekoppelt": bool(c.get("token")),
            "me": m58_me(), "peers": peers, "zugaenge": toks, "offen": pend, "state": _m58_state(),
            "log": q("SELECT * FROM sync_log ORDER BY id DESC LIMIT 20"),
            "konflikte": q("SELECT id, zeit, tbl, uid, info FROM sync_konflikt WHERE erledigt=0 ORDER BY id DESC LIMIT 100"),
            "server": {"aktiv": bool(m88c.get("aktiv")), "port": m88c.get("port"), "modus": m88c.get("modus"),
                       "suche": bool(M58_RT.get("suche_aktiv")), "suche_fehler": M58_RT.get("suche_fehler") or ""},
            "rt": _m58_rt(), "plattform": sys.platform, "version": M58_VERSION, "programm": m58_prog_state()}


def _m58_rt():
    n = M58_RT.get("naechster") or 0
    return {"live": bool(M58_RT.get("live")), "erreichbar": M58_RT.get("erreichbar"), "base": M58_RT.get("base") or "",
            "fehler": int(M58_RT.get("fehler") or 0), "naechster_s": max(0, int(n - time.time())) if n else 0}


def m58_status():
    c = m58_cfg()
    return {"ok": True, "state": _m58_state(), "rt": _m58_rt(), "offen": _m58_pending() if c.get("rolle") == "mobil" else 0,
            "live_geraete": [p_["name"] for p_ in q("SELECT dev, name FROM sync_peer WHERE rolle='mobil'")
                             if time.time() - M58_LIVE.get(p_["dev"] or "", 0) < 45]}


def m58_save(d):
    c = m58_cfg()
    if "adressen" in d:
        c["adressen"] = [a.strip() for a in (d.get("adressen") or []) if a and a.strip()][:8]
    for k in ("auto_min", "beim_start", "dateien", "name", "live", "programm"):
        if k in d:
            c[k] = d[k]
    m58_cfg_save(c)
    return m58_view()


def m58_unpair(d):
    c = m58_cfg()
    c.update(token="", aktiv=c.get("rolle") == "haupt", last_base="", auto_adr=[])
    m58_cfg_save(c)
    M58_RT.update(base="", caps=[], live=False, erreichbar=None)
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
HOOK_GET["/api/sync/status"] = lambda h, qs: h._send(200, m58_status())
HOOK_GET["/api/sync/gen"] = lambda h, qs: h._send(200, {"ok": True, "g": int(M58_RT.get("gen") or 0), "laeuft": M58_STATE["laeuft"]})
HOOK_POST["/api/sync/suchen"] = lambda h, d: h._send(200, {"ok": True, "pcs": m58_discover()})
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
        if [len(ch) for ch in _m58_chunks([("a", 10 << 20), ("b", 10 << 20), ("c", 1)])] != [1, 2]:
            err.append("m58: Dateipakete falsch")
    except Exception as e:
        err.append(f"m58 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m58_selftest)
print(f"INIT m58_abgleich v{M58_VERSION}")
