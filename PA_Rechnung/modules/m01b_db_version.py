# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m01b_db_version  v1.0.0 (ab Programm v3.0.0)
# Datenbank-Versionierung:
# - Tabelle db_version: mit welcher Programmversion die Datenbank zuletzt geoeffnet wurde, Migrationsstand,
#   Fingerabdruck des Aufbaus (Tabellen + Spalten).
# - Vor dem ersten Start einer NEUEN Programmversion wird automatisch eine Sicherung der Datenbank angelegt
#   (Backup\vor_update_<alt>_nach_<neu>_<zeit>.sqlite), erst danach duerfen Module Tabellen/Spalten anlegen.
# - Nummerierte Migrationen (db_migration): laufen genau einmal, in Reihenfolge, jede in einer Transaktion,
#   Ergebnis in db_migration_log. Schlaegt eine fehl, startet das Programm trotzdem und meldet es.
# - Aenderungen am Aufbau (neue Tabellen/Spalten durch Module) werden protokolliert.
# - Neuere Datenbank als Programm (z. B. nach Zurueckspielen einer alten Version): Hinweis beim Start.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

DBV_VERSION = "1.0.1"
DBV_MIGRATIONS = []          # (nr, name, fn)
DBV_STATE = {"backup": "", "neu_programm": False, "alt": "", "fehler": [], "neuere_db": False, "aenderungen": []}
DBV_KEEP_BACKUPS = 8


def db_migration(nr, name):
    """decorator: numbered data migration, runs once"""
    def deco(fn):
        if any(m[0] == nr for m in DBV_MIGRATIONS):
            raise ValueError(f"Migration {nr} doppelt")
        DBV_MIGRATIONS.append((nr, name, fn))
        DBV_MIGRATIONS.sort(key=lambda m: m[0])
        return fn
    return deco


def _dbv_raw():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _dbv_schema(con):
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        out[t] = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
    return out


def _dbv_read(con):
    try:
        r = con.execute("SELECT * FROM db_version WHERE id=1").fetchone()
        return dict(r) if r else None
    except sqlite3.Error:
        return None


def _vkey(v):
    try:
        return tuple(int(p_) for p_ in str(v).split(".")[:3])
    except Exception:
        return (0, 0, 0)


def db_pre_update():
    """before any table is touched: safety copy when this program version opens the database for the first time"""
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        return
    try:
        con = _dbv_raw()
        try:
            row = _dbv_read(con)
            alt = (row or {}).get("programm") or "vor 3.0.0"
            DBV_STATE["alt"] = alt
            if row and row.get("programm") == APP_VERSION:
                return
            DBV_STATE["neu_programm"] = True
            if row and _vkey(row.get("programm")) > _vkey(APP_VERSION):
                DBV_STATE["neuere_db"] = True
            os.makedirs(BACKUP_DIR, exist_ok=True)
            fn = os.path.join(BACKUP_DIR, "vor_update_{}_nach_{}_{}.sqlite".format(
                re.sub(r"[^0-9A-Za-z.]+", "_", (row or {}).get("programm") or "2.x"), APP_VERSION, datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
            bk = sqlite3.connect(fn)
            try:
                con.backup(bk)
            finally:
                bk.close()
            DBV_STATE["backup"] = fn
            _dbv_prune()
        finally:
            con.close()
    except Exception as e:
        traceback.print_exc()
        DBV_STATE["fehler"].append(f"Sicherung vor dem Update fehlgeschlagen: {e}")


def _dbv_prune():
    try:
        # oldest first by time (the name starts with the old version - 3.5 -> 3.1 -> 3.5 would sort wrong by name)
        fs = sorted((f for f in os.listdir(BACKUP_DIR) if f.startswith("vor_update_") and f.endswith(".sqlite")),
                    key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)))
        for f in fs[:-DBV_KEEP_BACKUPS]:
            os.remove(os.path.join(BACKUP_DIR, f))
    except Exception:
        traceback.print_exc()


def db_after_schema():
    """after all modules created their tables: numbered migrations + version / fingerprint"""
    try:
        with DB_LOCK:
            CON.execute("CREATE TABLE IF NOT EXISTS db_version (id INTEGER PRIMARY KEY CHECK (id=1), programm TEXT, migration INTEGER, "
                        "schema_hash TEXT, schema_json TEXT, geaendert TEXT)")
            CON.execute("CREATE TABLE IF NOT EXISTS db_migration_log (id INTEGER PRIMARY KEY, nr INTEGER, name TEXT, programm TEXT, "
                        "zeit TEXT, ok INTEGER, fehler TEXT)")
            CON.commit()
        row = q("SELECT * FROM db_version WHERE id=1", one=True)
        done = {r["nr"] for r in q("SELECT nr FROM db_migration_log WHERE ok=1")}
        for nr, name, fn in DBV_MIGRATIONS:
            if nr in done:
                continue
            err = ""
            with DB_LOCK:
                try:
                    CON.execute("SAVEPOINT dbv_mig")
                    fn()
                    CON.execute("RELEASE dbv_mig")
                    CON.commit()
                except Exception as e:
                    err = str(e)[:300]
                    traceback.print_exc()
                    try:
                        CON.execute("ROLLBACK TO dbv_mig")
                        CON.execute("RELEASE dbv_mig")
                    except Exception:
                        pass
            x("INSERT INTO db_migration_log (nr, name, programm, zeit, ok, fehler) VALUES (?,?,?,?,?,?)",
              (nr, name, APP_VERSION, now_iso(), 0 if err else 1, err))
            if err:
                DBV_STATE["fehler"].append(f"Migration {nr} ({name}): {err}")
        with DB_LOCK:
            sch = _dbv_schema(CON)
        js = json.dumps(sch, sort_keys=True)
        h_ = hashlib.sha1(js.encode()).hexdigest()[:16]
        if row and row.get("schema_json") and row.get("schema_hash") != h_:
            try:
                old = json.loads(row["schema_json"])
                ch = [f"neue Tabelle {t}" for t in sch if t not in old]
                ch += [f"{t}: neue Spalte {c_}" for t in sch if t in old for c_ in sch[t] if c_ not in old[t]]
                DBV_STATE["aenderungen"] = ch[:200]
            except Exception:
                pass
        mig = max([m[0] for m in DBV_MIGRATIONS] + [0])
        cur_mig = (row or {}).get("migration") or 0
        if (not row or row.get("programm") != APP_VERSION or row.get("schema_hash") != h_) and not DBV_STATE["neuere_db"]:
            x("INSERT OR REPLACE INTO db_version (id, programm, migration, schema_hash, schema_json, geaendert) VALUES (1,?,?,?,?,?)",
              (APP_VERSION, max(mig, cur_mig), h_, js, now_iso()))
    except Exception as e:
        traceback.print_exc()
        DBV_STATE["fehler"].append(f"Datenbank-Versionierung: {e}")


def db_version_info():
    row = q("SELECT programm, migration, schema_hash, geaendert FROM db_version WHERE id=1", one=True) or {}
    tabs = q("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'", one=True)["n"]
    log = q("SELECT nr, name, programm, zeit, ok, fehler FROM db_migration_log ORDER BY id DESC LIMIT 30")
    return {"programm": row.get("programm"), "migration": row.get("migration"), "fingerabdruck": row.get("schema_hash"),
            "geaendert": row.get("geaendert"), "tabellen": tabs, "log": log, "state": DBV_STATE,
            "groesse_mb": round(os.path.getsize(DB_PATH) / 1048576, 2) if os.path.exists(DB_PATH) else 0}


# ---------------------------------------------------------------------------
# numbered migrations (each runs once). New ones get the next number - never change an existing one.
# ---------------------------------------------------------------------------
@db_migration(1, "Grundstand v3.0.0 (Versionierung eingeführt)")
def _dbv_m1():
    CON.execute("UPDATE invoices SET typ='rechnung' WHERE typ IS NULL OR typ=''")


HOOK_BOOT.append(lambda d: d.update(dbv={"backup": os.path.basename(DBV_STATE["backup"]) if DBV_STATE["backup"] else "",
                                          "alt": DBV_STATE["alt"], "neu": DBV_STATE["neu_programm"],
                                          "fehler": DBV_STATE["fehler"], "neuere_db": DBV_STATE["neuere_db"]}))


def m01b_selftest():
    err = []
    try:
        row = q("SELECT * FROM db_version WHERE id=1", one=True)
        if not row or row["programm"] != APP_VERSION or not row["schema_hash"]:
            err.append("m01b: db_version nicht geschrieben")
        if not q("SELECT 1 FROM db_migration_log WHERE nr=1 AND ok=1", one=True):
            err.append("m01b: Migration 1 nicht gelaufen")
    except Exception as e:
        err.append(f"m01b Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m01b_selftest)
print(f"INIT m01b_db_version v{DBV_VERSION}")
