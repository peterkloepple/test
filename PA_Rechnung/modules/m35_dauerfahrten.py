# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m35_dauerfahrten (v2.0.9)
# Dauerfahrten: wiederkehrende Fahrten (z. B. jeden Di + Do zum Kunden,
# jeden 1. Montag im Monat, alle 2 Wochen ...). Aus jeder Vorlage entstehen
# die einzelnen Fahrten bis heute - automatisch oder als Vorschlag zum
# Bestaetigen. Feiertage (Bundesland waehlbar) koennen ausgelassen werden.
# Geloeschte oder uebersprungene Termine werden nie neu erzeugt.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import calendar

M35_VERSION = "1.0.0"
FS_MAX_BACK = 400          # days a new series may reach back
FS_LAENDER = {"BW": "Baden-Württemberg", "BY": "Bayern", "BE": "Berlin", "BB": "Brandenburg", "HB": "Bremen", "HH": "Hamburg",
              "HE": "Hessen", "MV": "Mecklenburg-Vorpommern", "NI": "Niedersachsen", "NW": "Nordrhein-Westfalen",
              "RP": "Rheinland-Pfalz", "SL": "Saarland", "SN": "Sachsen", "ST": "Sachsen-Anhalt", "SH": "Schleswig-Holstein", "TH": "Thüringen"}
FS_RHYTHMEN = ("woche", "monat", "monat_wt")
FS_LOCK = threading.Lock()


def m35_schema():
    x("CREATE TABLE IF NOT EXISTS fahrt_serien (id INTEGER PRIMARY KEY, name TEXT, ziel TEXT, zweck TEXT, km REAL, art TEXT, "
      "project_id INTEGER, customer_id INTEGER, rhythmus TEXT, wochentage TEXT, alle_n INTEGER DEFAULT 1, monatstag INTEGER, "
      "nth INTEGER, start TEXT, ende TEXT, modus TEXT DEFAULT 'auto', feiertage INTEGER DEFAULT 1, aktiv INTEGER DEFAULT 1, "
      "notiz TEXT, created TEXT)")
    x("CREATE TABLE IF NOT EXISTS fahrt_serien_done (serie_id INTEGER, datum TEXT, status TEXT, fahrt_id INTEGER, "
      "PRIMARY KEY (serie_id, datum))")
    have = {r["name"] for r in q("PRAGMA table_info(fahrten)")}
    if "serie_id" not in have:
        x("ALTER TABLE fahrten ADD COLUMN serie_id INTEGER")
    # v2.0.9: dates before gen_ab are never generated (editing a series must not refill the past)
    if "gen_ab" not in {r["name"] for r in q("PRAGMA table_info(fahrt_serien)")}:
        x("ALTER TABLE fahrt_serien ADD COLUMN gen_ab TEXT")


HOOK_SCHEMA.append(m35_schema)


# ---------------- holidays ----------------

def _ostern(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mon = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return datetime.date(y, mon, day)


_FT_CACHE = {}


def feiertage(year, land="NW"):
    """-> {date: name} for one German state"""
    key = (year, land)
    if key in _FT_CACHE:
        return _FT_CACHE[key]
    D = datetime.date
    td = datetime.timedelta
    e = _ostern(year)
    f = {D(year, 1, 1): "Neujahr", e - td(2): "Karfreitag", e + td(1): "Ostermontag", D(year, 5, 1): "Tag der Arbeit",
         e + td(39): "Christi Himmelfahrt", e + td(50): "Pfingstmontag", D(year, 10, 3): "Tag der Deutschen Einheit",
         D(year, 12, 25): "1. Weihnachtstag", D(year, 12, 26): "2. Weihnachtstag"}
    if land in ("BW", "BY", "ST"):
        f[D(year, 1, 6)] = "Heilige Drei Könige"
    if land == "BE" or (land == "MV" and year >= 2023):
        f[D(year, 3, 8)] = "Frauentag"
    if land in ("BW", "BY", "HE", "NW", "RP", "SL"):
        f[e + td(60)] = "Fronleichnam"
    if land == "SL":
        f[D(year, 8, 15)] = "Mariä Himmelfahrt"
    if land == "TH" and year >= 2019:
        f[D(year, 9, 20)] = "Weltkindertag"
    if land in ("BB", "MV", "SN", "ST", "TH") or (land in ("HB", "HH", "NI", "SH") and year >= 2018):
        f[D(year, 10, 31)] = "Reformationstag"
    if land in ("BW", "BY", "NW", "RP", "SL"):
        f[D(year, 11, 1)] = "Allerheiligen"
    if land == "SN":
        d = D(year, 11, 22)
        while d.weekday() != 2:
            d -= td(1)
        f[d] = "Buß- und Bettag"
    _FT_CACHE[key] = f
    return f


def ist_feiertag(d, land=None):
    land = land or (get_settings().get("fs_land") or "NW")
    return feiertage(d.year, land).get(d)


# ---------------- rhythm ----------------

def _wd_list(s):
    out = []
    for p_ in re.split(r"[,; ]+", str(s or "")):
        if p_.strip().isdigit() and 1 <= int(p_) <= 7:
            out.append(int(p_))
    return sorted(set(out))


def _last_dom(y, m):
    return calendar.monthrange(y, m)[1]


def _fs_nth_weekday(y, m, wd, nth):
    """wd 1=Mo..7=So, nth 1..5 or -1 = last -> date or None"""
    if nth == -1:
        d = datetime.date(y, m, _last_dom(y, m))
        while d.isoweekday() != wd:
            d -= datetime.timedelta(days=1)
        return d
    d = datetime.date(y, m, 1)
    while d.isoweekday() != wd:
        d += datetime.timedelta(days=1)
    d += datetime.timedelta(days=7 * (nth - 1))
    return d if d.month == m else None


def serie_termine(s, von, bis, land=None):
    """all dates of series s in [von, bis] (date objects), holidays removed if wanted"""
    st = d_iso(s.get("start"))
    if not st:
        return []
    en = d_iso(s.get("ende"))
    a = max(von, st)
    b = min(bis, en) if en else bis
    if a > b:
        return []
    n = max(1, int(s.get("alle_n") or 1))
    rh = s.get("rhythmus") or "woche"
    out = []
    if rh == "woche":
        wds = _wd_list(s.get("wochentage")) or [st.isoweekday()]
        week0 = st - datetime.timedelta(days=st.isoweekday() - 1)
        d = a
        while d <= b:
            if d.isoweekday() in wds and ((d - week0).days // 7) % n == 0:
                out.append(d)
            d += datetime.timedelta(days=1)
    elif rh in ("monat", "monat_wt"):
        y, m = a.year, a.month
        m0 = st.year * 12 + st.month - 1
        while (y, m) <= (b.year, b.month):
            if ((y * 12 + m - 1) - m0) % n == 0:
                if rh == "monat":
                    tag = int(s.get("monatstag") or st.day)
                    d = datetime.date(y, m, min(max(1, tag), _last_dom(y, m)))
                else:
                    wds = _wd_list(s.get("wochentage")) or [st.isoweekday()]
                    d = _fs_nth_weekday(y, m, wds[0], int(s.get("nth") or 1))
                if d and a <= d <= b:
                    out.append(d)
            m += 1
            if m > 12:
                y, m = y + 1, 1
    if s.get("feiertage", 1) in (1, True, "1", "true"):
        land = land or (get_settings().get("fs_land") or "NW")
        out = [d for d in out if not ist_feiertag(d, land)]
    return out


def rhythmus_text(s):
    WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    n = max(1, int(s.get("alle_n") or 1))
    rh = s.get("rhythmus") or "woche"
    wds = _wd_list(s.get("wochentage"))
    if rh == "woche":
        t = ", ".join(WD[w - 1] for w in wds) or "wöchentlich"
        return ("jede Woche " if n == 1 else f"alle {n} Wochen ") + t
    if rh == "monat":
        tag = int(s.get("monatstag") or 0) or ((d_iso(s.get("start")) or datetime.date.today()).day)
        return ("monatlich" if n == 1 else f"alle {n} Monate") + f" am {tag}."
    nth = int(s.get("nth") or 1)
    nt = "letzten" if nth == -1 else f"{nth}."
    return ("jeden " if n == 1 else f"alle {n} Monate am ") + f"{nt} {WD[(wds or [1])[0] - 1]} im Monat"


# ---------------- generation ----------------

def _done_dates(sid):
    return {r["datum"] for r in q("SELECT datum FROM fahrt_serien_done WHERE serie_id=?", (sid,))}


def _fs_from(s):
    lim = datetime.date.today() - datetime.timedelta(days=FS_MAX_BACK)
    st = d_iso(s.get("start")) or datetime.date.today()
    ga = d_iso(s.get("gen_ab"))
    return max(st, lim, ga) if ga else max(st, lim)


def fs_offen(sid=None, bis=None):
    """dates that are due but not yet created / skipped -> list of dicts"""
    bis = bis or datetime.date.today()
    rows = q("SELECT * FROM fahrt_serien WHERE aktiv=1" + (" AND id=?" if sid else ""), (sid,) if sid else ())
    land = get_settings().get("fs_land") or "NW"
    out = []
    for s in rows:
        done = _done_dates(s["id"])
        for d in serie_termine(s, _fs_from(s), bis, land):
            iso = d.isoformat()
            if iso not in done:
                out.append({"serie_id": s["id"], "datum": iso, "name": s["name"], "ziel": s["ziel"], "zweck": s["zweck"],
                            "km": s["km"], "art": s["art"], "modus": s["modus"] or "auto"})
    return sorted(out, key=lambda r: (r["datum"], r["serie_id"]))


def _fs_create(s, iso):
    fid = x("INSERT INTO fahrten (datum, ziel, zweck, km, art, project_id, customer_id, notiz, serie_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (iso, s["ziel"] or "", s["zweck"] or "", float(s["km"] or 0), s["art"] or "dienst", s["project_id"], s["customer_id"],
             ("Dauerfahrt: " + (s["name"] or "")).strip(), s["id"]))
    x("INSERT OR REPLACE INTO fahrt_serien_done (serie_id, datum, status, fahrt_id) VALUES (?,?,?,?)", (s["id"], iso, "angelegt", fid))
    return fid


def fs_run(only_auto=True):
    """create all due trips of 'auto' series -> number created"""
    if not FS_LOCK.acquire(timeout=30):
        return 0
    try:
        n = 0
        ser = {s["id"]: s for s in q("SELECT * FROM fahrt_serien WHERE aktiv=1")}
        for o in fs_offen():
            s = ser.get(o["serie_id"])
            if not s or (only_auto and (s["modus"] or "auto") != "auto"):
                continue
            _fs_create(s, o["datum"])
            n += 1
        if n:
            set_setting("fs_letzter", {"zeit": now_iso(), "angelegt": n})
        return n
    finally:
        FS_LOCK.release()


def fs_apply(items):
    """items: [{serie_id, datum, use}] -> use=True create, False skip forever"""
    with FS_LOCK:
        return _fs_apply(items)


def _fs_apply(items):
    n_ok = n_skip = 0
    ser = {s["id"]: s for s in q("SELECT * FROM fahrt_serien")}
    for it in items or []:
        s = ser.get(int(it.get("serie_id") or 0))
        iso = str(it.get("datum") or "")[:10]
        if not s or not d_iso(iso):
            continue
        if q("SELECT 1 FROM fahrt_serien_done WHERE serie_id=? AND datum=?", (s["id"], iso), one=True):
            continue
        if it.get("use", True):
            _fs_create(s, iso)
            n_ok += 1
        else:
            x("INSERT OR REPLACE INTO fahrt_serien_done (serie_id, datum, status, fahrt_id) VALUES (?,?,?,NULL)", (s["id"], iso, "uebersprungen"))
            n_skip += 1
    return {"ok": True, "angelegt": n_ok, "uebersprungen": n_skip}


def fs_save(d):
    rh = d.get("rhythmus") or "woche"
    if rh not in FS_RHYTHMEN:
        raise ValueError("Unbekannter Rhythmus.")
    if not d_iso(d.get("start")):
        raise ValueError("Bitte ein Startdatum angeben.")
    if d.get("ende") and d_iso(d.get("ende")) and d_iso(d["ende"]) < d_iso(d["start"]):
        raise ValueError("Das Enddatum liegt vor dem Startdatum.")
    km = float(parse_amount(str(d.get("km"))) if isinstance(d.get("km"), str) else (d.get("km") or 0))
    if km <= 0:
        raise ValueError("Bitte die km angeben.")
    wds = ",".join(str(w) for w in _wd_list(d.get("wochentage")))
    if rh == "woche" and not wds:
        raise ValueError("Bitte mindestens einen Wochentag wählen.")
    if rh == "monat_wt" and not wds:
        raise ValueError("Bitte den Wochentag wählen.")
    vals = {"name": (d.get("name") or d.get("ziel") or "Dauerfahrt").strip()[:80], "ziel": (d.get("ziel") or "").strip(),
            "zweck": (d.get("zweck") or "").strip(), "km": km, "art": "pendel" if d.get("art") == "pendel" else "dienst",
            "project_id": int(d["project_id"]) if d.get("project_id") else None,
            "customer_id": int(d["customer_id"]) if d.get("customer_id") else None, "rhythmus": rh, "wochentage": wds,
            "alle_n": max(1, int(float(d.get("alle_n") or 1))), "monatstag": int(float(d.get("monatstag") or 0)) or None,
            "nth": int(float(d.get("nth") or 1)), "start": str(d["start"])[:10], "ende": (str(d.get("ende") or "")[:10] or None),
            "modus": "vorschlag" if d.get("modus") == "vorschlag" else "auto", "feiertage": 1 if d.get("feiertage", True) else 0,
            "aktiv": 1 if d.get("aktiv", True) else 0, "notiz": d.get("notiz") or ""}
    today_ = datetime.date.today().isoformat()
    if d.get("id"):
        sid = int(d["id"])
        alt = q("SELECT * FROM fahrt_serien WHERE id=?", (sid,), one=True)
        if not alt:
            raise ValueError("Diese Dauerfahrt gibt es nicht mehr.")
        # editing never refills the past: only dates from today on (or later than before)
        vals["gen_ab"] = max(alt["gen_ab"] or alt["start"] or today_, today_)
        cols = list(vals)
        x(f"UPDATE fahrt_serien SET {', '.join(c + '=?' for c in cols)} WHERE id=?", tuple(vals[c] for c in cols) + (sid,))
    else:
        vals["created"] = now_iso()
        vals["gen_ab"] = vals["start"]
        cols = list(vals)
        sid = x(f"INSERT INTO fahrt_serien ({', '.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(vals[c] for c in cols))
        # "als Dauerfahrt": the source trip becomes the first trip of the series (no duplicate on that day)
        src = q("SELECT * FROM fahrten WHERE id=?", (int(d["quelle_fahrt_id"]),), one=True) if d.get("quelle_fahrt_id") else None
        if src and not src["serie_id"]:
            x("UPDATE fahrten SET serie_id=? WHERE id=?", (sid, src["id"]))
            x("INSERT OR REPLACE INTO fahrt_serien_done (serie_id, datum, status, fahrt_id) VALUES (?,?,?,?)", (sid, src["datum"], "angelegt", src["id"]))
    n = fs_run()
    return {"ok": True, "id": sid, "angelegt": n}


def fs_delete(sid, fahrten_mit=False):
    sid = int(sid)
    n = 0
    if fahrten_mit:
        n = q("SELECT COUNT(*) n FROM fahrten WHERE serie_id=?", (sid,), one=True)["n"]
        x("DELETE FROM fahrten WHERE serie_id=?", (sid,))
    else:
        x("UPDATE fahrten SET serie_id=NULL WHERE serie_id=?", (sid,))
    x("DELETE FROM fahrt_serien_done WHERE serie_id=?", (sid,))
    x("DELETE FROM fahrt_serien WHERE id=?", (sid,))
    return {"ok": True, "geloescht_fahrten": n}


def fs_list():
    out = []
    today_ = datetime.date.today()
    land = get_settings().get("fs_land") or "NW"
    for s in q("SELECT * FROM fahrt_serien ORDER BY aktiv DESC, name"):
        s = dict(s)
        s["rhythmus_text"] = rhythmus_text(s)
        s["anzahl"] = q("SELECT COUNT(*) n FROM fahrten WHERE serie_id=?", (s["id"],), one=True)["n"]
        nx = serie_termine(s, today_ + datetime.timedelta(days=1), today_ + datetime.timedelta(days=400), land)[:1] if s["aktiv"] else []
        s["naechste"] = nx[0].isoformat() if nx else ""
        out.append(s)
    return {"ok": True, "serien": out, "vorschlaege": [o for o in fs_offen() if o["modus"] == "vorschlag"],
            "land": land, "laender": FS_LAENDER, "letzter": get_settings().get("fs_letzter") or {}}


def fs_preview(d, n=8):
    s = dict(d)
    s["wochentage"] = ",".join(str(w) for w in _wd_list(d.get("wochentage")))
    try:
        st = d_iso(s.get("start")) or datetime.date.today()
        ds = serie_termine(s, st, st + datetime.timedelta(days=800))[:n]
    except Exception:
        ds = []
    return {"ok": True, "termine": [x_.isoformat() for x_ in ds], "text": rhythmus_text(s)}


def _fs_loop():
    time.sleep(20)
    last = ""
    while True:
        try:
            t = datetime.date.today().isoformat()
            if t != last:
                fs_run()
                last = t
        except Exception:
            traceback.print_exc()
        time.sleep(600)


def _fs_boot(d):
    try:
        d["fs_vorschlaege"] = len([o for o in fs_offen() if o["modus"] == "vorschlag"])
    except Exception:
        d["fs_vorschlaege"] = 0


def _fs_selftest():
    err = []
    try:
        if _ostern(2026) != datetime.date(2026, 4, 5) or _ostern(2027) != datetime.date(2027, 3, 28):
            err.append("Dauerfahrten: Osterdatum falsch")
        s = {"start": "2026-01-01", "rhythmus": "woche", "wochentage": "2,4", "alle_n": 1, "feiertage": 1}
        ds = serie_termine(s, datetime.date(2026, 4, 1), datetime.date(2026, 4, 10), "NW")
        if [x_.isoformat() for x_ in ds] != ["2026-04-02", "2026-04-07", "2026-04-09"]:
            err.append("Dauerfahrten: Wochenrhythmus falsch " + str(ds))
        s2 = {"start": "2026-01-01", "rhythmus": "monat_wt", "wochentage": "1", "nth": -1, "alle_n": 1, "feiertage": 0}
        if [x_.isoformat() for x_ in serie_termine(s2, datetime.date(2026, 5, 1), datetime.date(2026, 6, 30))] != ["2026-05-25", "2026-06-29"]:
            err.append("Dauerfahrten: letzter Montag falsch")
    except Exception as e:
        err.append(f"Dauerfahrten: {e}")
    return err


HOOK_GET["/api/fserie/list"] = lambda h, qs: h._send(200, fs_list())
HOOK_POST["/api/fserie/save"] = lambda h, d: h._send(200, fs_save(d))
HOOK_POST["/api/fserie/delete"] = lambda h, d: h._send(200, fs_delete(d.get("id"), bool(d.get("fahrten_mit"))))
HOOK_POST["/api/fserie/apply"] = lambda h, d: h._send(200, fs_apply(d.get("items") or []))
HOOK_POST["/api/fserie/run"] = lambda h, d: h._send(200, {"ok": True, "angelegt": fs_run()})
HOOK_POST["/api/fserie/preview"] = lambda h, d: h._send(200, fs_preview(d))
def fs_set_land(land):
    land = land if land in FS_LAENDER else "NW"
    if land != (get_settings().get("fs_land") or "NW"):
        t = datetime.date.today().isoformat()
        x("UPDATE fahrt_serien SET gen_ab=? WHERE COALESCE(gen_ab, start, '') < ?", (t, t))
        set_setting("fs_land", land)
    return {"ok": True}


HOOK_POST["/api/fserie/land"] = lambda h, d: h._send(200, fs_set_land(d.get("land")))
HOOK_BOOT.append(_fs_boot)
HOOK_START.append(_fs_loop)
HOOK_SELFTEST.append(_fs_selftest)


# deleting a single generated trip marks its date as skipped (never re-created)

def _fs_fahrt_delete(h, d):
    ids = [int(d["id"])] if d.get("id") else []
    for fid in ids:
        r = q("SELECT serie_id, datum FROM fahrten WHERE id=?", (fid,), one=True)
        if r and r["serie_id"]:
            x("UPDATE fahrt_serien_done SET status='geloescht', fahrt_id=NULL WHERE serie_id=? AND datum=?", (r["serie_id"], r["datum"]))
        x("DELETE FROM fahrten WHERE id=?", (fid,))
    return h._send(200, {"ok": True})


HOOK_POST["/api/fahrt/delete"] = _fs_fahrt_delete
