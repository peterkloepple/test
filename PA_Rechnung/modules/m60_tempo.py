# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m60_tempo (v2.0.6)
# Geschwindigkeit: Datenbank im WAL-Modus (schnelles Speichern, kein
# Journal-Datei-Anlegen/Loeschen pro Speichervorgang - unter Windows mit
# Virenscanner der groesste Bremsklotz), Indizes auf alle Verknuepfungs-
# spalten, regelmaessiger Checkpoint im Leerlauf (die Hauptdatei
# daten.sqlite ist damit fuer Cloud-Sync/Kopie immer aktuell).
# Liegt der Datenordner auf einem Netzlaufwerk, bleibt der klassische
# Journal-Modus (WAL funktioniert dort nicht zuverlaessig).
# Autor: T. Pfeiffer

M60_VERSION = "1.0.0"
M60_STATE = {"mode": "", "indexes": 0, "checkpoint": "", "net": False}

M60_INDEXES = [
    ("items", "invoice_id"), ("items", "entry_id"),
    ("invoices", "customer_id"), ("invoices", "project_id"), ("invoices", "nr"), ("invoices", "datum"),
    ("invoices", "ref_id"), ("invoices", "storno_von"), ("invoices", "status"),
    ("belege", "invoice_id"), ("belege", "project_id"), ("belege", "datum"), ("belege", "typ"),
    ("project_files", "project_id"), ("project_entries", "project_id"), ("project_entries", "invoice_id"),
    ("mahnungen", "invoice_id"), ("mail_log", "doc_id"), ("recurring", "invoice_id"),
    ("bank_tx", "hash"), ("bank_tx", "invoice_id"), ("bank_tx", "beleg_id"), ("bank_tx", "datum"),
    ("lessons", "student_id"), ("lessons", "invoice_id"), ("lessons", "kurs_id"),
    ("kurs_members", "kurs_id"), ("kurs_members", "student_id"),
    ("assets", "beleg_id"), ("fahrten", "datum"), ("beleg_learn", "beleg_id"),
    ("eingang_log", "beleg_id"), ("vorlagen", "hash"), ("briefe", "customer_id"), ("briefe", "project_id"),
    ("fixkosten_vormerk", "fix_id"), ("fixkosten_vormerk", "beleg_id"), ("fixkosten_vormerk", "bank_tx_id"),
    ("m40_plan", "project_id"), ("m41_aufmass", "project_id"), ("m41_kalk", "project_id"),
    ("m42_buchung", "project_id"), ("fints_pending", "hash"), ("mail_inbox", "datum"),
    ("customers", "kdnr"),
]


def _m60_is_network(path):
    p = os.path.abspath(path)
    if p.startswith("\\\\") or p.startswith("//"):
        return True
    if sys.platform.startswith("win"):
        try:
            import ctypes
            root = os.path.splitdrive(p)[0] + "\\"
            return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 4   # DRIVE_REMOTE
        except Exception:
            return False
    return False


def m60_schema():
    net = _m60_is_network(DATA_DIR)
    M60_STATE["net"] = net
    with DB_LOCK:
        try:
            CON.commit()
            mode = CON.execute("PRAGMA journal_mode=" + ("DELETE" if net else "WAL")).fetchone()[0]
            M60_STATE["mode"] = str(mode).upper()
            CON.execute("PRAGMA synchronous=" + ("NORMAL" if M60_STATE["mode"] == "WAL" else "FULL"))
            CON.execute("PRAGMA temp_store=MEMORY")
            CON.execute("PRAGMA cache_size=-32000")   # 32 MB page cache
        except Exception:
            traceback.print_exc()
        tables = {r[0] for r in CON.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        n = 0
        for t, c in M60_INDEXES:
            if t not in tables:
                continue
            try:
                cols = {r[1] for r in CON.execute(f"PRAGMA table_info({t})")}
                if c not in cols:
                    continue
                CON.execute(f"CREATE INDEX IF NOT EXISTS ix60_{t}_{c} ON {t}({c})")
                n += 1
            except Exception:
                traceback.print_exc()
        CON.commit()
        try:
            CON.execute("PRAGMA optimize")
        except Exception:
            pass
    M60_STATE["indexes"] = n


HOOK_SCHEMA.append(m60_schema)


def m60_checkpoint(mode="TRUNCATE"):
    if M60_STATE.get("mode") != "WAL" or CON is None:
        return None
    try:
        wal = DB_PATH + "-wal"
        if os.path.exists(wal) and os.path.getsize(wal) == 0:
            return None
        with DB_LOCK:
            r = CON.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        M60_STATE["checkpoint"] = now_iso()
        return r
    except Exception:
        return None


def m60_loop():
    # keep daten.sqlite up to date (Cloud-Sync, Kopie im Explorer) - every 30 s, cheap when idle
    while True:
        time.sleep(30)
        m60_checkpoint()
        try:
            _m60_fhash_save()
        except Exception:
            pass


HOOK_START.append(m60_loop)

try:
    import atexit as _m60_atexit
    _m60_atexit.register(m60_checkpoint)
except Exception:
    pass


# ---------------------------------------------------------------------------
# v2.0.6: write counter (for short-lived caches) + write freeze during a data-folder move
# ---------------------------------------------------------------------------
DB_GEN = [0]
_m60_gen_lock = threading.Lock()


def _m60_bump():
    # under a lock: "+= 1" from two writer threads could lose a step and bring back a counter value
    # that already has a (now stale) cache entry
    with _m60_gen_lock:
        DB_GEN[0] += 1


@chain_step("x", "m60_tempo")
def _m60_step_x(_next, sql, args=()):
    if DD_FROZEN[0]:
        raise ValueError("Der Datenordner wurde gerade umgezogen - das Programm startet neu. Bitte die Eingabe danach wiederholen.")
    _m60_bump()
    try:
        return _next(sql, args)
    finally:
        _m60_bump()   # again after the write: a reader in between must not keep the old result


def _m60_cached(fn, ttl=3.0):
    """cache results of heavy read functions for a few seconds as long as nothing was written
    (one Jahresbericht/Export calls euer()/tax_calc() up to 40x for the same year)"""
    cache = {}
    lock = threading.Lock()

    def wrapper(*a):
        k = (a, DB_GEN[0], today())
        with lock:
            hit = cache.get(k)
            if hit and time.time() - hit[0] < ttl:
                return pickle.loads(hit[1])
        r = fn(*a)
        with lock:
            if len(cache) > 32:
                cache.clear()
            try:
                cache[k] = (time.time(), pickle.dumps(r, protocol=pickle.HIGHEST_PROTOCOL))
            except Exception:
                pass
        return r
    wrapper.__name__ = getattr(fn, "__name__", "cached")
    wrapper._m60_orig = fn
    return wrapper


import pickle
euer = _m60_cached(euer)
tax_calc = _m60_cached(tax_calc)
euer_totals = _m60_cached(euer_totals, ttl=60.0)
find_duplicates = _m60_cached(find_duplicates, ttl=300.0)   # Belege view calls /api/dups on every render

# file hashes of Belege survive a restart (the first duplicate check read EVERY beleg file completely)
M60_FHASH_FILE = os.path.join(DATA_DIR, "Assets", "_dateihash_cache.json")
M60_FHASH_SAVED = [0]


def _m60_fhash_load():
    try:
        with open(M60_FHASH_FILE, encoding="utf-8") as f:
            for k, v in (json.load(f) or {}).items():
                fp, sz, mt = k.rsplit("|", 2)
                FHASH[(fp, int(sz), int(mt))] = v
        M60_FHASH_SAVED[0] = len(FHASH)
    except Exception:
        pass


def _m60_fhash_save():
    if len(FHASH) == M60_FHASH_SAVED[0]:
        return
    try:
        data = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in list(FHASH.items())[-50000:]}
        tmp = M60_FHASH_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, M60_FHASH_FILE)
        M60_FHASH_SAVED[0] = len(FHASH)
    except Exception:
        pass


_m60_fhash_load()
