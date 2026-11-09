# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m29_kalender (v2.0.7)
# Kalender: der komplette TimeTree-Kalender wird heruntergeladen und im
# Programm gespeichert (alle Kalender, Labels, Termine inkl. Wiederholungen,
# Notizen, Orte). Anzeige als Monat / Woche / Liste unter "Kalender".
# Abruf ueber die TimeTree-Web-Schnittstelle mit E-Mail + Passwort (wie die
# TimeTree-Webseite; inoffiziell, kann sich seitens TimeTree aendern) -
# alternativ .ics-Datei importieren (z. B. bei Anmeldung ueber Google/Apple).
# Nur lesend: im TimeTree-Kalender wird nichts veraendert.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import urllib.request
import urllib.error
import http.cookies

M29_VERSION = "1.0.0"
TT_API = "https://timetreeapp.com/api/v1"
TT_UA = "web/2.1.0/en"
KAL_LOCK = threading.Lock()
KAL_STATE = {"laeuft": False, "text": ""}
_WD = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def m29_schema():
    x("CREATE TABLE IF NOT EXISTS kal_cal (id TEXT PRIMARY KEY, quelle TEXT, name TEXT, farbe TEXT, aktiv INTEGER DEFAULT 1, "
      "anzahl INTEGER DEFAULT 0, abgerufen TEXT, raw TEXT)")
    x("CREATE TABLE IF NOT EXISTS kal_label (cal_id TEXT, label_id INTEGER, name TEXT, farbe TEXT, PRIMARY KEY (cal_id, label_id))")
    x("CREATE TABLE IF NOT EXISTS kal_event (cal_id TEXT, uuid TEXT, title TEXT, start_ms INTEGER, end_ms INTEGER, all_day INTEGER, "
      "start_tz TEXT, end_tz TEXT, rec TEXT, note TEXT, location TEXT, url TEXT, label_id INTEGER, category INTEGER, typ INTEGER, "
      "parent_id TEXT, recurring_uuid TEXT, updated_ms INTEGER, raw TEXT, PRIMARY KEY (cal_id, uuid))")
    x("CREATE INDEX IF NOT EXISTS ix_kal_event_start ON kal_event(start_ms)")


HOOK_SCHEMA.append(m29_schema)


# ---------------------------------------------------------------------------
# time helpers (no tz database needed: local time of this PC, UTC, or zoneinfo if available)
# ---------------------------------------------------------------------------
def _kal_tz(name):
    if not name or name.upper() in ("UTC", "Z", "GMT", "ETC/UTC"):
        return datetime.timezone.utc
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(name)
    except Exception:
        return None          # unknown -> local time of this PC


_KAL_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


def _kal_local_off():
    """current UTC offset of this PC (fallback for dates Windows' C runtime cannot convert, e.g. before 1970)"""
    try:
        return datetime.datetime.now().astimezone().utcoffset() or datetime.timedelta(0)
    except Exception:
        return datetime.timedelta(0)


def _kal_naive_local(aware):
    """aware datetime -> naive local time; works for dates before 1970 on Windows too"""
    try:
        return datetime.datetime.fromtimestamp(aware.timestamp())
    except (OSError, OverflowError, ValueError):
        return (aware.astimezone(datetime.timezone.utc) + _kal_local_off()).replace(tzinfo=None)


def ms_to_local(ms, tz=None, all_day=False):
    """epoch ms -> naive local datetime (all-day: the calendar date in the event's zone)"""
    aware = _KAL_EPOCH + datetime.timedelta(milliseconds=int(ms or 0))   # no fromtimestamp: negative ms fail on Windows
    if all_day:
        z = _kal_tz(tz)
        if z is not None:
            return aware.astimezone(z).replace(tzinfo=None)
    return _kal_naive_local(aware)


def local_to_ms(dt):
    try:
        return int(time.mktime(dt.timetuple()) * 1000)
    except (OSError, OverflowError, ValueError):
        return int((dt - _kal_local_off() - _KAL_EPOCH.replace(tzinfo=None)) / datetime.timedelta(milliseconds=1))


def _ical_dt(val, params=""):
    """iCal date/datetime -> (naive local datetime, all_day)"""
    v = (val or "").strip()
    if re.search(r"VALUE=DATE(?![-\w])", params or "", re.I) or re.fullmatch(r"\d{8}", v):   # not VALUE=DATE-TIME
        return datetime.datetime.strptime(v[:8], "%Y%m%d"), True
    m = re.fullmatch(r"(\d{8}T\d{4,6})(Z?)", v)
    if not m:
        raise ValueError(f"Unbekanntes Datum: {v}")
    s_ = m.group(1)
    dt = datetime.datetime.strptime(s_ + ("00" if len(s_) == 13 else ""), "%Y%m%dT%H%M%S")
    if m.group(2) == "Z":
        return _kal_naive_local(dt.replace(tzinfo=datetime.timezone.utc)), False
    tzm = re.search(r"TZID=([^;:]+)", params or "")
    if tzm:
        z = _kal_tz(tzm.group(1).strip('"'))
        if z is not None:
            return _kal_naive_local(dt.replace(tzinfo=z)), False
    return dt, False


# ---------------------------------------------------------------------------
# RRULE expansion (DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY, BYMONTH, EXDATE, RDATE)
# ---------------------------------------------------------------------------
def _rr_parse(rule):
    r = {}
    for part in rule.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            r[k.strip().upper()] = v.strip()
    return r


def _nth_weekday(y, m, wd, n):
    """n-th (1..5 or -1..-5) weekday wd (0=Mo) in month, or None"""
    if n > 0:
        d = datetime.date(y, m, 1)
        d += datetime.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
        return d if d.month == m else None
    last = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1))
    d = last - datetime.timedelta(days=(last.weekday() - wd) % 7 + 7 * (-n - 1))
    return d if d.month == m else None


def _month_days(y, m, r, d0):
    """candidate dates of one month for MONTHLY/YEARLY rules"""
    out = []
    last = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)).day
    if r.get("BYDAY"):
        for tok in r["BYDAY"].split(","):
            mm = re.fullmatch(r"([+-]?\d*)([A-Z]{2})", tok.strip().upper())
            if not mm or mm.group(2) not in _WD:
                continue
            wd = _WD.index(mm.group(2))
            if mm.group(1) not in ("", "+", "-"):
                d = _nth_weekday(y, m, wd, int(mm.group(1)))
                if d:
                    out.append(d)
            else:
                d = datetime.date(y, m, 1)
                d += datetime.timedelta(days=(wd - d.weekday()) % 7)
                while d.month == m:
                    out.append(d)
                    d += datetime.timedelta(days=7)
    if r.get("BYMONTHDAY"):
        for tok in r["BYMONTHDAY"].split(","):
            try:
                n = int(tok)
            except ValueError:
                continue
            day = n if n > 0 else last + 1 + n
            if 1 <= day <= last:
                out.append(datetime.date(y, m, day))
    if not r.get("BYDAY") and not r.get("BYMONTHDAY") and d0.day <= last:
        out.append(datetime.date(y, m, d0.day))
    if r.get("BYSETPOS") and out:
        out = sorted(set(out))
        sel = []
        for tok in r["BYSETPOS"].split(","):
            try:
                i = int(tok)
                sel.append(out[i - 1 if i > 0 else i])
            except (ValueError, IndexError):
                pass
        out = sel
    return sorted(set(out))


def rr_expand(start, rule, until_to, exdates=(), all_day=False, limit=20000):
    """occurrence start datetimes (naive local) of a rule, from start up to until_to"""
    r = _rr_parse(rule)
    freq = r.get("FREQ", "").upper()
    iv = max(1, int(r.get("INTERVAL") or 1))
    count = int(r["COUNT"]) if (r.get("COUNT") or "").isdigit() else None
    until = None
    if r.get("UNTIL"):
        try:
            until, _ = _ical_dt(r["UNTIL"])
            if len(r["UNTIL"]) == 8:
                until = until.replace(hour=23, minute=59, second=59)
        except Exception:
            until = None
    end = min(until_to, until) if until else until_to
    ex = {e.replace(second=0, microsecond=0) for e in exdates}
    exd = {e.date() for e in exdates}
    t0 = start.time()
    out, n, steps = [], 0, 0

    def emit(d):
        nonlocal n
        dt = datetime.datetime.combine(d, t0)
        if dt < start:
            return True
        if dt > end:
            return False
        n += 1
        if count is not None and n > count:
            return False
        if not ((all_day and d in exd) or dt.replace(second=0, microsecond=0) in ex):
            out.append(dt)
        return True

    d0 = start.date()
    if freq == "DAILY":
        d = d0
        while steps < limit:
            steps += 1
            if r.get("BYDAY") and _WD[d.weekday()] not in [t[-2:] for t in r["BYDAY"].upper().split(",")]:
                d += datetime.timedelta(days=iv)
                if datetime.datetime.combine(d, t0) > end:
                    break
                continue
            if not emit(d):
                break
            d += datetime.timedelta(days=iv)
    elif freq == "WEEKLY":
        days = [_WD.index(t[-2:]) for t in (r.get("BYDAY") or _WD[d0.weekday()]).upper().split(",") if t[-2:] in _WD] or [d0.weekday()]
        wk = d0 - datetime.timedelta(days=d0.weekday())
        go_on = True
        while go_on and steps < limit:
            steps += 1
            for wd in sorted(days):
                if not emit(wk + datetime.timedelta(days=wd)):
                    go_on = False
                    break
            wk += datetime.timedelta(weeks=iv)
    elif freq in ("MONTHLY", "YEARLY"):
        y, m = d0.year, d0.month
        months = [int(v) for v in (r.get("BYMONTH") or "").split(",") if v.strip().isdigit()] if freq == "YEARLY" else []
        if freq == "YEARLY" and not months:
            months = [d0.month]
        go_on = True
        while go_on and steps < limit:
            steps += 1
            mlist = [(y, m)] if freq == "MONTHLY" else [(y, mm) for mm in sorted(months)]
            for (yy, mm) in mlist:
                rr = r if (freq == "MONTHLY" or r.get("BYDAY") or r.get("BYMONTHDAY")) else dict(r, BYMONTHDAY=str(d0.day))
                for d in _month_days(yy, mm, rr, d0):
                    if not emit(d):
                        go_on = False
                        break
                if not go_on:
                    break
            if freq == "MONTHLY":
                m += iv
                while m > 12:
                    m -= 12
                    y += 1
            else:
                y += iv
            if datetime.datetime(y, m if freq == "MONTHLY" else 1, 1) > end:
                break
    else:
        emit(d0)
    return out


def kal_occurrences(ev, von, bis):
    """all occurrences of a stored event overlapping [von, bis) as (start, end) naive local datetimes"""
    ad = bool(ev["all_day"])
    st = ms_to_local(ev["start_ms"], ev["start_tz"], ad)
    en = ms_to_local(ev["end_ms"] or ev["start_ms"], ev["end_tz"] or ev["start_tz"], ad)
    if ad:
        st = st.replace(hour=0, minute=0, second=0, microsecond=0)
        en = en.replace(hour=0, minute=0, second=0, microsecond=0)
        if en < st:
            en = st
    dur = en - st
    rec = []
    try:
        rec = json.loads(ev["rec"] or "[]") or []
    except Exception:
        rec = []
    rules = [l_.split(":", 1)[1] for l_ in rec if l_.upper().startswith("RRULE")]
    exd, rdates = [], []
    for l_ in rec:
        up = l_.upper()
        if up.startswith("EXDATE") or up.startswith("RDATE"):
            head, _, vals = l_.partition(":")
            for v in vals.split(","):
                try:
                    (exd if up.startswith("EXDATE") else rdates).append(_ical_dt(v.strip(), head)[0])
                except Exception:
                    pass
    starts = []
    if rules:
        for rl in rules:
            starts += rr_expand(st, rl, bis, exd, ad)
        starts += [d for d in rdates if d < bis]
    else:
        starts = [st]
    out = []
    for s_ in sorted(set(starts)):
        e_ = s_ + dur
        e_cmp = e_ if not ad else (e_ + datetime.timedelta(days=1))   # all-day end is inclusive here
        if s_ < bis and e_cmp > von:
            out.append((s_, e_))
    return out


# ---------------------------------------------------------------------------
# TimeTree web API (read only)
# ---------------------------------------------------------------------------
def _tt_req(method, path, body=None, session=None, timeout=25):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(TT_API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json", "X-Timetreea": TT_UA,
                                          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    if session:
        req.add_header("Cookie", f"_session_id={session}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, r.headers, (json.loads(raw.decode("utf-8")) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read() or b""
        try:
            js = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            js = {"text": raw[:300].decode("utf-8", "replace")}
        return e.code, e.headers, js
    except urllib.error.URLError as e:
        raise ValueError(f"TimeTree nicht erreichbar ({getattr(e, 'reason', e)}) - Internetverbindung prüfen.")
    except (socket.timeout, TimeoutError):
        raise ValueError("TimeTree antwortet nicht (Zeitüberschreitung).")


def tt_login(email, pw):
    st_, hd, js = _tt_req("PUT", "/auth/email/signin", {"uid": email, "password": pw, "uuid": uuid.uuid4().hex})
    if st_ != 200:
        code = (js.get("error") or {}).get("code") if isinstance(js.get("error"), dict) else None
        if code == -702 or st_ in (401, 403):
            raise ValueError("TimeTree-Anmeldung abgelehnt - E-Mail oder Passwort falsch. "
                             "(Wer sich in TimeTree über Google/Apple/LINE anmeldet, braucht ein eigenes TimeTree-Passwort "
                             "oder nutzt den .ics-Import.)")
        if code == -495 or st_ == 429:
            raise ValueError("TimeTree: zu viele Anmeldeversuche - bitte später erneut versuchen.")
        raise ValueError(f"TimeTree-Anmeldung fehlgeschlagen (HTTP {st_}).")
    sid = None
    for hv in (hd.get_all("Set-Cookie") or []):
        c = http.cookies.SimpleCookie()
        try:
            c.load(hv)
        except Exception:
            continue
        if "_session_id" in c:
            sid = c["_session_id"].value
    if not sid:
        raise ValueError("TimeTree hat keine Sitzung zurückgegeben - Anmeldung nicht möglich.")
    return sid


def _tt_creds():
    s = get_settings()
    email = (s.get("tt_email") or "").strip()
    try:
        pw = unprotect_secret(s.get("tt_pass") or "")
    except Exception:
        pw = ""
    try:
        sess = unprotect_secret(s.get("tt_session") or "")
    except Exception:
        sess = ""
    return email, pw, sess


def _tt_get(path, sess_box):
    st_, _, js = _tt_req("GET", path, session=sess_box[0])
    if st_ in (401, 403):
        email, pw, _ = _tt_creds()
        if not (email and pw):
            raise ValueError("TimeTree-Sitzung abgelaufen - bitte E-Mail und Passwort eintragen.")
        sess_box[0] = tt_login(email, pw)
        set_setting("tt_session", protect_secret(sess_box[0]))
        st_, _, js = _tt_req("GET", path, session=sess_box[0])
    if st_ != 200:
        raise ValueError(f"TimeTree-Abruf fehlgeschlagen ({path.split('?')[0]}: HTTP {st_}).")
    return js


def _hexcol(v):
    if isinstance(v, int):
        return f"#{v & 0xFFFFFF:06x}"
    v = str(v or "")
    return v if re.fullmatch(r"#[0-9a-fA-F]{6}", v) else (("#" + v) if re.fullmatch(r"[0-9a-fA-F]{6}", v) else "")


def _ev_label(e):
    lid = e.get("label_id")
    if lid is not None:
        return lid
    try:
        rid = e["relationships"]["label"]["data"]["id"]
        return int(str(rid).split(",")[-1])
    except Exception:
        return None


def tt_sync():
    """download the complete TimeTree account: all active calendars, labels and events (replaces the local copy)"""
    if not KAL_LOCK.acquire(blocking=False):
        raise ValueError("Der Kalender wird gerade abgerufen - bitte einen Moment warten.")
    KAL_STATE.update(laeuft=True, text="Anmelden …")
    try:
        email, pw, sess = _tt_creds()
        if not email or not pw:
            raise ValueError("Bitte zuerst E-Mail und Passwort deines TimeTree-Kontos eintragen.")
        if not sess:
            sess = tt_login(email, pw)
            set_setting("tt_session", protect_secret(sess))
        box = [sess]
        KAL_STATE["text"] = "Kalender laden …"
        cals = (_tt_get("/calendars?since=0", box).get("calendars") or [])
        cals = [c for c in cals if not c.get("deactivated_at")]
        res = {"kalender": 0, "termine": 0, "labels": 0}
        keep = set()
        for c in cals:
            cid = "tt:" + str(c.get("id"))
            keep.add(cid)
            name = c.get("name") or c.get("alias_code") or f"Kalender {c.get('id')}"
            KAL_STATE["text"] = f"„{name}“: Labels …"
            labels = []
            try:
                lj = _tt_get(f"/calendar/{c['id']}/labels", box)
                labels = lj.get("calendar_labels") or []
            except ValueError:
                labels = []
            KAL_STATE["text"] = f"„{name}“: Termine …"
            evs, since, guard = [], None, 0
            while guard < 500:
                guard += 1
                js = _tt_get(f"/calendar/{c['id']}/events/sync" + (f"?since={since}" if since is not None else ""), box)
                evs += js.get("events") or []
                KAL_STATE["text"] = f"„{name}“: {len(evs)} Termine …"
                if js.get("chunk") is True and js.get("since") is not None and js.get("since") != since:
                    since = js["since"]
                    continue
                break
            evs = [e for e in evs if not e.get("deactivated_at") and not e.get("deleted_at")]
            rows = []
            for e in evs:
                rows.append((cid, str(e.get("uuid") or e.get("id")), e.get("title") or "", int(e.get("start_at") or 0),
                             int(e.get("end_at") or e.get("start_at") or 0), 1 if e.get("all_day") else 0, e.get("start_timezone") or "",
                             e.get("end_timezone") or "", json.dumps(e.get("recurrences") or [], ensure_ascii=False), e.get("note") or "",
                             e.get("location") or "", e.get("url") or "", _ev_label(e), e.get("category"), e.get("type"),
                             e.get("parent_id"), e.get("recurring_uuid"), int(e.get("updated_at") or 0), json.dumps(e, ensure_ascii=False)))
            with DB_LOCK:
                old = CON.execute("SELECT aktiv, farbe FROM kal_cal WHERE id=?", (cid,)).fetchone()
                CON.execute("DELETE FROM kal_event WHERE cal_id=?", (cid,))
                CON.executemany("INSERT OR REPLACE INTO kal_event (cal_id, uuid, title, start_ms, end_ms, all_day, start_tz, end_tz, rec, note, "
                                "location, url, label_id, category, typ, parent_id, recurring_uuid, updated_ms, raw) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                CON.execute("DELETE FROM kal_label WHERE cal_id=?", (cid,))
                CON.executemany("INSERT OR REPLACE INTO kal_label (cal_id, label_id, name, farbe) VALUES (?,?,?,?)",
                                [(cid, l_.get("id"), l_.get("name") or "", _hexcol(l_.get("color"))) for l_ in labels if l_.get("id") is not None])
                CON.execute("INSERT OR REPLACE INTO kal_cal (id, quelle, name, farbe, aktiv, anzahl, abgerufen, raw) VALUES (?,?,?,?,?,?,?,?)",
                            (cid, "timetree", name, (old[1] if old and old[1] else _hexcol(c.get("color")) or "#30a46c"),
                             old[0] if old else 1, len(rows), now_iso(), json.dumps(c, ensure_ascii=False)))
                CON.commit()
            res["kalender"] += 1
            res["termine"] += len(rows)
            res["labels"] += len(labels)
        # calendars that no longer exist in the account
        with DB_LOCK:
            for (cid,) in CON.execute("SELECT id FROM kal_cal WHERE quelle='timetree'").fetchall():
                if cid not in keep:
                    CON.execute("DELETE FROM kal_event WHERE cal_id=?", (cid,))
                    CON.execute("DELETE FROM kal_label WHERE cal_id=?", (cid,))
                    CON.execute("DELETE FROM kal_cal WHERE id=?", (cid,))
            CON.commit()
        try:
            DB_GEN[0] += 1
        except NameError:
            pass
        set_setting("tt_last", {"zeit": now_iso(), "fehler": "", **res})
        res["ok"] = True
        return res
    except ValueError as e:
        set_setting("tt_last", dict(get_settings().get("tt_last") or {}, fehler=str(e), versuch=now_iso()))
        raise
    finally:
        KAL_STATE.update(laeuft=False, text="")
        KAL_LOCK.release()


# ---------------------------------------------------------------------------
# .ics import / export
# ---------------------------------------------------------------------------
def _ics_unfold(text):
    out = []
    for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if ln[:1] in (" ", "\t") and out:
            out[-1] += ln[1:]
        else:
            out.append(ln)
    return out


def _ics_unesc(v):
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def ics_parse(text):
    cal_name, cal_col, events, cur = "", "", [], None
    for ln in _ics_unfold(text):
        if not ln.strip():
            continue
        head, _, val = ln.partition(":")
        name = head.split(";", 1)[0].upper()
        params = head[len(name):]
        if name == "BEGIN" and val.upper() == "VEVENT":
            cur = {"rec": []}
        elif name == "END" and val.upper() == "VEVENT" and cur is not None:
            if cur.get("start"):
                events.append(cur)
            cur = None
        elif cur is None:
            if name == "X-WR-CALNAME":
                cal_name = _ics_unesc(val)
            elif name in ("X-APPLE-CALENDAR-COLOR", "COLOR"):
                cal_col = val
        else:
            if name == "UID":
                cur["uid"] = val
            elif name == "SUMMARY":
                cur["title"] = _ics_unesc(val)
            elif name == "DESCRIPTION":
                cur["note"] = _ics_unesc(val)
            elif name == "LOCATION":
                cur["location"] = _ics_unesc(val)
            elif name == "URL":
                cur["url"] = val
            elif name == "CATEGORIES":
                cur["cat"] = _ics_unesc(val)
            elif name == "COLOR":
                cur["color"] = val
            elif name == "DTSTART":
                cur["start"], cur["all_day"] = _ical_dt(val, params)
            elif name == "DTEND":
                cur["end"], _ = _ical_dt(val, params)
            elif name in ("RRULE", "EXDATE", "RDATE"):
                cur["rec"].append(f"{head}:{val}")
    return cal_name, cal_col, events


def ics_import(path, filename):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ValueError("Das ist keine Kalenderdatei (.ics).")
    cname, ccol, evs = ics_parse(text)
    cname = cname or os.path.splitext(os.path.basename(filename))[0]
    cid = "ics:" + re.sub(r"\W+", "_", cname.lower()).strip("_")[:60]
    rows = []
    for i, e in enumerate(evs):
        st_ = e["start"]
        ad = bool(e.get("all_day"))
        en = e.get("end") or (st_ + (datetime.timedelta(days=1) if ad else datetime.timedelta(hours=1)))
        if ad:
            # store like TimeTree: midnight UTC of the date, inclusive end date
            sm = int(datetime.datetime(st_.year, st_.month, st_.day, tzinfo=datetime.timezone.utc).timestamp() * 1000)
            ei = en - datetime.timedelta(days=1) if en > st_ else st_
            em = int(datetime.datetime(ei.year, ei.month, ei.day, tzinfo=datetime.timezone.utc).timestamp() * 1000)
            tz = "UTC"
        else:
            sm, em, tz = local_to_ms(st_), local_to_ms(en), ""
        rows.append((cid, e.get("uid") or f"ics-{i}", e.get("title") or "", sm, em, 1 if ad else 0, tz, tz,
                     json.dumps(e.get("rec") or [], ensure_ascii=False), e.get("note") or "", e.get("location") or "", e.get("url") or "",
                     None, 1, 0, None, None, 0, ""))
    with DB_LOCK:
        old = CON.execute("SELECT aktiv, farbe FROM kal_cal WHERE id=?", (cid,)).fetchone()
        CON.execute("DELETE FROM kal_event WHERE cal_id=?", (cid,))
        CON.executemany("INSERT OR REPLACE INTO kal_event (cal_id, uuid, title, start_ms, end_ms, all_day, start_tz, end_tz, rec, note, "
                        "location, url, label_id, category, typ, parent_id, recurring_uuid, updated_ms, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        CON.execute("INSERT OR REPLACE INTO kal_cal (id, quelle, name, farbe, aktiv, anzahl, abgerufen, raw) VALUES (?,?,?,?,?,?,?,?)",
                    (cid, "ics", cname, (old[1] if old and old[1] else _hexcol(ccol) or "#0a84ff"), old[0] if old else 1, len(rows), now_iso(), ""))
        CON.commit()
    try:
        DB_GEN[0] += 1
    except NameError:
        pass
    return {"ok": True, "kalender": cname, "termine": len(rows)}


def _ics_esc(v):
    return str(v or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _ics_fold(line):
    out, b = [], line.encode("utf-8")
    while len(b) > 74:
        cut = 74
        while cut > 0 and (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def ics_export(cal_id=None):
    cals = {r["id"]: r for r in q("SELECT * FROM kal_cal")}
    evs = q("SELECT * FROM kal_event" + (" WHERE cal_id=?" if cal_id else "") + " ORDER BY start_ms", (cal_id,) if cal_id else ())
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//T. Pfeiffer//PA Rechnung {APP_VERSION}//DE", "CALSCALE:GREGORIAN",
         "X-WR-CALNAME:" + _ics_esc(cals[cal_id]["name"] if cal_id and cal_id in cals else "Kalender (alle)")]
    stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for e in evs:
        ad = bool(e["all_day"])
        st_ = ms_to_local(e["start_ms"], e["start_tz"], ad)
        en = ms_to_local(e["end_ms"] or e["start_ms"], e["end_tz"] or e["start_tz"], ad)
        L += ["BEGIN:VEVENT", "UID:" + _ics_esc(e["uuid"]), "DTSTAMP:" + stamp, "SUMMARY:" + _ics_esc(e["title"])]
        if ad:
            L += ["DTSTART;VALUE=DATE:" + st_.strftime("%Y%m%d"), "DTEND;VALUE=DATE:" + (en + datetime.timedelta(days=1)).strftime("%Y%m%d")]
        else:
            # local wall-clock time (floating) - weekly lessons stay at 17:00 across summer/winter time
            L += ["DTSTART:" + st_.strftime("%Y%m%dT%H%M%S"), "DTEND:" + en.strftime("%Y%m%dT%H%M%S")]
        for k, v in (("DESCRIPTION", e["note"]), ("LOCATION", e["location"])):
            if v:
                L.append(f"{k}:{_ics_esc(v)}")
        if e["url"]:
            L.append("URL:" + e["url"])
        lb = q("SELECT name FROM kal_label WHERE cal_id=? AND label_id=?", (e["cal_id"], e["label_id"]), one=True) if e["label_id"] is not None else None
        cats = [cals[e["cal_id"]]["name"]] if e["cal_id"] in cals else []
        if lb and lb["name"]:
            cats.append(lb["name"])
        if cats:
            L.append("CATEGORIES:" + ",".join(_ics_esc(c) for c in cats))
        try:
            L += [r_ for r_ in json.loads(e["rec"] or "[]") if r_]
        except Exception:
            pass
        L.append("END:VEVENT")
    L.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l_) for l_ in L) + "\r\n"


# ---------------------------------------------------------------------------
# queries for the UI
# ---------------------------------------------------------------------------
def kal_events(von, bis, qtext="", alle=False):
    v = datetime.datetime.strptime(von[:10], "%Y-%m-%d")
    b = datetime.datetime.strptime(bis[:10], "%Y-%m-%d")
    cals = {r["id"]: r for r in q("SELECT id, name, farbe, aktiv, quelle FROM kal_cal")}
    labels = {(r["cal_id"], r["label_id"]): r for r in q("SELECT * FROM kal_label")}
    act = [cid for cid, c in cals.items() if c["aktiv"] or alle]
    if not act:
        return []
    vm = local_to_ms(v - datetime.timedelta(days=40))
    rows = q(f"SELECT * FROM kal_event WHERE cal_id IN ({','.join('?' * len(act))}) AND (start_ms < ? AND (rec LIKE '%RRULE%' OR end_ms >= ? OR start_ms >= ?))",
             act + [local_to_ms(b) + 86400000, vm, vm])
    ql = (qtext or "").lower().strip()
    out = []
    for e in rows:
        if ql and ql not in f"{e['title']} {e['note']} {e['location']}".lower():
            continue
        try:
            occ = kal_occurrences(e, v, b)
        except Exception:
            traceback.print_exc()
            continue
        lb = labels.get((e["cal_id"], e["label_id"]))
        col = (lb["farbe"] if lb and lb["farbe"] else "") or cals[e["cal_id"]]["farbe"] or "#0a84ff"
        for s_, en in occ:
            out.append({"uuid": e["uuid"], "cal_id": e["cal_id"], "kal": cals[e["cal_id"]]["name"], "title": e["title"] or "(ohne Titel)",
                        "start": s_.strftime("%Y-%m-%dT%H:%M"), "end": en.strftime("%Y-%m-%dT%H:%M"), "all_day": bool(e["all_day"]),
                        "farbe": col, "label": lb["name"] if lb else "", "ort": e["location"] or "", "notiz": e["note"] or "",
                        "url": e["url"] or "", "wdh": "RRULE" in (e["rec"] or ""), "memo": e["category"] == 2})
    out.sort(key=lambda r: (r["start"][:10], not r["all_day"], r["start"], r["title"]))
    return out


def kal_info():
    s = get_settings()
    email, pw, sess = _tt_creds()
    return {"ok": True, "email": email, "has_pw": bool(pw), "verbunden": bool(sess), "auto": int(s.get("tt_auto") or 0),
            "last": s.get("tt_last") or {}, "laeuft": KAL_STATE["laeuft"], "status": KAL_STATE["text"],
            "kalender": q("SELECT id, quelle, name, farbe, aktiv, anzahl, abgerufen FROM kal_cal ORDER BY quelle DESC, name"),
            "labels": q("SELECT * FROM kal_label ORDER BY cal_id, label_id")}


def kal_settings(d):
    if "email" in d:
        if (d.get("email") or "").strip() != (get_settings().get("tt_email") or ""):
            set_setting("tt_session", "")
        set_setting("tt_email", (d.get("email") or "").strip())
    if d.get("password"):
        set_setting("tt_pass", protect_secret(d["password"]))
        set_setting("tt_session", "")
    if "auto" in d:
        set_setting("tt_auto", max(0, int(d.get("auto") or 0)))
    if d.get("abmelden"):
        set_setting("tt_pass", "")
        set_setting("tt_session", "")
    return kal_info()


def kal_cal_update(d):
    if d.get("loeschen"):
        with DB_LOCK:
            CON.execute("DELETE FROM kal_event WHERE cal_id=?", (d["id"],))
            CON.execute("DELETE FROM kal_label WHERE cal_id=?", (d["id"],))
            CON.execute("DELETE FROM kal_cal WHERE id=?", (d["id"],))
            CON.commit()
        return kal_info()
    if "aktiv" in d:
        x("UPDATE kal_cal SET aktiv=? WHERE id=?", (1 if d["aktiv"] else 0, d["id"]))
    if d.get("farbe") and re.fullmatch(r"#[0-9a-fA-F]{6}", d["farbe"]):
        x("UPDATE kal_cal SET farbe=? WHERE id=?", (d["farbe"], d["id"]))
    return kal_info()


def kal_export(d):
    data = ics_export(d.get("id") or None)
    nm = "Kalender_" + (re.sub(r"\W+", "_", d.get("name") or "alle").strip("_") or "alle") + "_" + time.strftime("%Y-%m-%d") + ".ics"
    out = os.path.join(DATA_DIR, "Export", nm)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_file(out, data, text=True)
    if d.get("open", True) and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(os.path.dirname(out))
    return {"ok": True, "path": out}


def kal_sync_route(h, d):
    try:
        return h._send(200, tt_sync())
    except ValueError as e:
        return h._send(200, {"ok": False, "error": str(e)})


def _kal_upload(h, tmp, name):
    try:
        return h._send(200, ics_import(tmp, name))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _kal_boot(d):
    try:
        t = datetime.date.today().isoformat()
        n = len([e for e in kal_events(t, (datetime.date.today() + datetime.timedelta(days=1)).isoformat()) if not e["memo"]])
        d["kal"] = {"heute": n}
    except Exception:
        d["kal"] = {"heute": 0}


def _kal_loop():
    time.sleep(25)
    while True:
        try:
            s = get_settings()
            auto = int(s.get("tt_auto") or 0)
            email, pw, _ = _tt_creds()
            if auto and email and pw:
                last = (s.get("tt_last") or {}).get("zeit") or ""
                due = True
                if last:
                    try:
                        due = (datetime.datetime.now() - datetime.datetime.fromisoformat(last.replace(" ", "T"))).total_seconds() >= auto * 60
                    except Exception:
                        due = True
                if due and not KAL_STATE["laeuft"]:
                    try:
                        tt_sync()
                    except ValueError:
                        pass
        except Exception:
            traceback.print_exc()
        time.sleep(60)


def _kal_selftest():
    errs = []
    try:
        st_ = datetime.datetime(2026, 1, 5, 17, 0)
        occ = rr_expand(st_, "FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4", datetime.datetime(2026, 12, 31))
        if [o.strftime("%m-%d") for o in occ] != ["01-05", "01-07", "01-12", "01-14"]:
            errs.append("Kalender: Wochen-Wiederholung falsch")
        occ = rr_expand(datetime.datetime(2026, 1, 13, 9, 0), "FREQ=MONTHLY;BYDAY=2TU", datetime.datetime(2026, 4, 30))
        if [o.strftime("%m-%d") for o in occ] != ["01-13", "02-10", "03-10", "04-14"]:
            errs.append("Kalender: Monats-Wiederholung (2. Dienstag) falsch")
        ex = [datetime.datetime(2026, 1, 7, 17, 0)]
        occ = rr_expand(st_, "FREQ=DAILY;UNTIL=20260108", datetime.datetime(2026, 12, 31), ex)
        if [o.day for o in occ] != [5, 6, 8]:
            errs.append("Kalender: EXDATE/UNTIL falsch")
        n, c, ev = ics_parse("BEGIN:VCALENDAR\r\nX-WR-CALNAME:Test\r\nBEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Probe\\, lang\r\n"
                             "DTSTART;VALUE=DATE:20260301\r\nDTEND;VALUE=DATE:20260302\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        if n != "Test" or len(ev) != 1 or ev[0]["title"] != "Probe, lang" or not ev[0]["all_day"]:
            errs.append("Kalender: .ics-Leser falsch")
    except Exception as e:
        errs.append(f"Kalender: {type(e).__name__}: {e}")
    return errs


def kal_url(d):
    u = (d.get("url") or "").strip()
    if not re.match(r"^https?://", u, re.I):
        raise ValueError("Nur Internet-Links (http/https) können geöffnet werden.")
    webbrowser.open(u)
    return {"ok": True}


HOOK_POST["/api/kal/url"] = lambda h, d: h._send(200, kal_url(d))
HOOK_GET["/api/kal/info"] = lambda h, qs: h._send(200, kal_info())
HOOK_GET["/api/kal/events"] = lambda h, qs: h._send(200, {"ok": True, "events": kal_events(qs.get("von") or today(), qs.get("bis") or today(), qs.get("q") or "")})
HOOK_POST["/api/kal/settings"] = lambda h, d: h._send(200, kal_settings(d))
HOOK_POST["/api/kal/sync"] = kal_sync_route
HOOK_POST["/api/kal/cal"] = lambda h, d: h._send(200, kal_cal_update(d))
HOOK_POST["/api/kal/export"] = lambda h, d: h._send(200, kal_export(d))
HOOK_UPLOAD["/api/upload/ics"] = _kal_upload
HOOK_BOOT.append(_kal_boot)
HOOK_START.append(_kal_loop)
HOOK_SELFTEST.append(_kal_selftest)
