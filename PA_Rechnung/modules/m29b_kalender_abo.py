# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m29b_kalender_abo  v1.0.0 (ab Programm v3.6.2)
# Kalender-Abos: beliebig viele Internet-Kalender per Link (ICS/iCal, auch webcal://) abonnieren, z. B.
# MediaFlow-Laufzeiten, Google-/Outlook-/iCloud-Freigaben, Schulferien. Jeder Link wird als eigener Kalender
# im Programm gespeichert (Tabellen von m29: kal_cal / kal_event, Quelle "abo") und erscheint unter "Kalender",
# in der Uebersicht und ueberall, wo m29-Termine genutzt werden. Nur lesend - am Ursprung wird nichts veraendert.
# Abruf: automatisch je Abo (Intervall), per Knopf, beim Speichern. Bei einem Fehler bleiben die letzten Termine.
# Gespeichert in den Einstellungen (kal_abos) - damit auch im Backup.
# Datenschutz: zum Kalender-Server geht nur ein einfacher GET auf den Link - neutraler User-Agent, keine Cookies,
# kein Referer, keine Programmdaten. Die Handy-App liest die Termine ueber m88 (/v1/kalender).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import urllib.request
import urllib.error

M29B_VERSION = "1.0.0"
M29B_LOCK = threading.Lock()
M29B_RUN = set()                 # ids being fetched right now
M29B_MAX = 25 * 1024 * 1024      # 25 MB per feed
# privacy: the calendar server gets nothing from the program - neutral User-Agent, no cookies, no Referer,
# no login data, nothing in the URL besides the link itself; redirects only to http(s); one GET per fetch
M29B_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Calendar/1.0"


class _M29bRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not re.match(r"^https?://", newurl or "", re.I):
            raise ValueError("Weiterleitung auf eine ungültige Adresse abgelehnt.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


M29B_OPENER = urllib.request.build_opener(_M29bRedirect)   # no cookie handler -> no cookies sent or kept
M29B_OPENER.addheaders = []                                  # drop urllib's own "Python-urllib/x" User-Agent


def _abo_list():
    v = get_settings().get("kal_abos")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = []
    return [a for a in (v or []) if isinstance(a, dict) and a.get("id")]


def _abo_save_all(lst):
    set_setting("kal_abos", lst)


def _abo_url(u):
    u = (u or "").strip()
    if u.lower().startswith("webcal://"):
        u = "https://" + u[9:]
    if not re.match(r"^https?://[^\s/]+\.[^\s/]+", u, re.I):
        raise ValueError("Bitte einen Internet-Link eintragen (https://… oder webcal://…).")
    return u


def _abo_cid(aid):
    return "abo:" + aid


def _abo_store(text, aid, name, farbe=""):
    """ICS text -> calendar 'abo:<id>' (replaces its events). Returns (calendar name, number of events)."""
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ValueError("Unter dem Link liegt kein Kalender (keine ICS-Daten).")
    cname, ccol, evs = ics_parse(text)
    # cancelled events (STATUS:CANCELLED) are not shown
    cancelled = set()
    for blk in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S | re.I):
        if re.search(r"^STATUS:CANCELLED", blk, re.M | re.I):
            m = re.search(r"^UID:(.+)$", blk, re.M)
            if m:
                cancelled.add(m.group(1).strip())
    cid = _abo_cid(aid)
    name = (name or "").strip() or cname or "Kalender-Abo"
    rows = []
    for i, e in enumerate(evs):
        if e.get("uid") and e["uid"] in cancelled:
            continue
        st_ = e["start"]
        ad = bool(e.get("all_day"))
        en = e.get("end") or (st_ + (datetime.timedelta(days=1) if ad else datetime.timedelta(hours=1)))
        if ad:
            sm = int(datetime.datetime(st_.year, st_.month, st_.day, tzinfo=datetime.timezone.utc).timestamp() * 1000)
            ei = en - datetime.timedelta(days=1) if en > st_ else st_
            em = int(datetime.datetime(ei.year, ei.month, ei.day, tzinfo=datetime.timezone.utc).timestamp() * 1000)
            tz = "UTC"
        else:
            sm, em, tz = local_to_ms(st_), local_to_ms(en), ""
        rows.append((cid, e.get("uid") or f"abo-{i}", e.get("title") or "", sm, em, 1 if ad else 0, tz, tz,
                     json.dumps(e.get("rec") or [], ensure_ascii=False), e.get("note") or "", e.get("location") or "", e.get("url") or "",
                     None, 1, 0, None, None, 0, ""))
    with DB_LOCK:
        old = CON.execute("SELECT aktiv, farbe FROM kal_cal WHERE id=?", (cid,)).fetchone()
        CON.execute("DELETE FROM kal_event WHERE cal_id=?", (cid,))
        CON.executemany("INSERT OR REPLACE INTO kal_event (cal_id, uuid, title, start_ms, end_ms, all_day, start_tz, end_tz, rec, note, "
                        "location, url, label_id, category, typ, parent_id, recurring_uuid, updated_ms, raw) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        col = farbe if re.fullmatch(r"#[0-9a-fA-F]{6}", farbe or "") else ((old[1] if old and old[1] else "") or _hexcol(ccol) or "#ff9f0a")
        CON.execute("INSERT OR REPLACE INTO kal_cal (id, quelle, name, farbe, aktiv, anzahl, abgerufen, raw) VALUES (?,?,?,?,?,?,?,?)",
                    (cid, "abo", name, col, old[0] if old else 1, len(rows), now_iso(), ""))
        CON.commit()
    try:
        DB_GEN[0] += 1
    except NameError:
        pass
    return name, len(rows)


def _abo_download(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": M29B_UA, "Accept": "text/calendar, text/plain, */*"})
    try:
        with M29B_OPENER.open(req, timeout=40) as r:
            raw = r.read(M29B_MAX + 1)
    except urllib.error.HTTPError as e:
        raise ValueError({401: "Zugriff verweigert (401) – Link abgelaufen oder privat?", 403: "Zugriff verweigert (403) – Link abgelaufen oder privat?",
                          404: "Link nicht gefunden (404) – wurde das Abo beim Anbieter gelöscht?"}.get(e.code, f"Server meldet Fehler {e.code}."))
    except urllib.error.URLError as e:
        raise ValueError(f"Keine Verbindung zum Kalender-Server ({getattr(e, 'reason', e)}).")
    except Exception as e:
        raise ValueError(f"Abruf fehlgeschlagen: {e}")
    if len(raw) > M29B_MAX:
        raise ValueError("Kalender zu groß (über 25 MB).")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def abo_fetch(aid):
    """fetch one subscription now; result is written into the subscription (letzter)"""
    with M29B_LOCK:
        if aid in M29B_RUN:
            return {"ok": True, "laeuft": True}
        M29B_RUN.add(aid)
    try:
        lst = _abo_list()
        a = next((x_ for x_ in lst if x_["id"] == aid), None)
        if not a:
            raise ValueError("Abo nicht gefunden.")
        res = {"zeit": now_iso(), "ok": False, "text": "", "termine": 0}
        try:
            text = _abo_download(_abo_url(a.get("url")))
            name, n = _abo_store(text, aid, a.get("name"), a.get("farbe") or "")
            res.update(ok=True, termine=n, text=f"{n} Termine")
            if not a.get("name"):
                a["name"] = name
        except ValueError as e:
            res["text"] = str(e)[:300]
        except Exception as e:
            traceback.print_exc()
            res["text"] = f"Fehler: {str(e)[:250]}"
        lst = _abo_list()                      # re-read: may have changed meanwhile
        for x_ in lst:
            if x_["id"] == aid:
                x_["letzter"] = res
                if a.get("name") and not x_.get("name"):
                    x_["name"] = a["name"]
        _abo_save_all(lst)
        if not res["ok"]:
            return {"ok": False, "error": res["text"], "abo": aid}
        return {"ok": True, "termine": res["termine"], "name": a.get("name"), "abo": aid}
    finally:
        with M29B_LOCK:
            M29B_RUN.discard(aid)


def abo_view():
    lst = _abo_list()
    cals = {r["id"]: r for r in q("SELECT id, name, farbe, aktiv, anzahl, abgerufen FROM kal_cal WHERE quelle='abo'")}
    out = []
    for a in lst:
        c = cals.get(_abo_cid(a["id"])) or {}
        out.append({"id": a["id"], "name": a.get("name") or c.get("name") or "", "url": a.get("url") or "", "aktiv": a.get("aktiv", True),
                    "intervall": int(a.get("intervall") or 60), "farbe": c.get("farbe") or a.get("farbe") or "#ff9f0a",
                    "anzeigen": bool(c.get("aktiv", 1)), "termine": c.get("anzahl") or 0, "letzter": a.get("letzter") or {},
                    "laeuft": a["id"] in M29B_RUN})
    return {"ok": True, "abos": out}


def abo_save(d):
    lst = _abo_list()
    url = _abo_url(d.get("url"))
    aid = str(d.get("id") or "")
    if aid:
        a = next((x_ for x_ in lst if x_["id"] == aid), None)
        if not a:
            raise ValueError("Abo nicht gefunden.")
    else:
        if any(_abo_url(x_.get("url")) == url for x_ in lst if x_.get("url")):
            raise ValueError("Dieser Link ist schon abonniert.")
        aid = uuid.uuid4().hex[:10]
        a = {"id": aid, "angelegt": now_iso()}
        lst.append(a)
    a["url"] = url
    a["name"] = (d.get("name") or "").strip()[:80]
    a["aktiv"] = bool(d.get("aktiv", True))
    a["intervall"] = max(15, min(1440, int(d.get("intervall") or 60)))
    if re.fullmatch(r"#[0-9a-fA-F]{6}", d.get("farbe") or ""):
        a["farbe"] = d["farbe"]
        x("UPDATE kal_cal SET farbe=? WHERE id=?", (d["farbe"], _abo_cid(aid)))
    if a["name"]:
        x("UPDATE kal_cal SET name=? WHERE id=?", (a["name"], _abo_cid(aid)))
    _abo_save_all(lst)
    r = abo_fetch(aid) if d.get("abrufen", True) else {"ok": True}
    v = abo_view()
    v["abruf"] = r
    return v


def abo_delete(d):
    aid = str(d.get("id") or "")
    lst = [x_ for x_ in _abo_list() if x_["id"] != aid]
    _abo_save_all(lst)
    with DB_LOCK:
        CON.execute("DELETE FROM kal_event WHERE cal_id=?", (_abo_cid(aid),))
        CON.execute("DELETE FROM kal_cal WHERE id=?", (_abo_cid(aid),))
        CON.commit()
    try:
        DB_GEN[0] += 1
    except NameError:
        pass
    return abo_view()


def abo_fetch_all(only_due=False):
    n, errs = 0, []
    for a in _abo_list():
        if not a.get("aktiv", True):
            continue
        if only_due:
            last = (a.get("letzter") or {}).get("zeit") or ""
            if last:
                try:
                    age = (datetime.datetime.now() - datetime.datetime.fromisoformat(last.replace(" ", "T")[:19])).total_seconds()
                    if age < int(a.get("intervall") or 60) * 60:
                        continue
                except Exception:
                    pass
        r = abo_fetch(a["id"])
        n += 1
        if not r.get("ok") and r.get("error"):
            errs.append(f"{a.get('name') or a.get('url')}: {r['error']}")
    return {"ok": True, "abgerufen": n, "fehler": errs}


# v1.0.0: the MediaFlow "Laufzeiten" feed (requested 08.11.2026) is entered once on first start;
# removing it in the dialog is final (flag kal_abo_seed_1 stays set).
M29B_SEED = [("kal_abo_seed_1", "MediaFlow Laufzeiten",
              "https://api.mediaflow.mertens.ag/functions/v1/calendar-feed/78611b82-18ae-4065-aaf8-019cecdcc357.ics")]


def _abo_seed():
    s = get_settings()
    lst = _abo_list()
    changed = False
    for flag, name, url in M29B_SEED:
        if s.get(flag):
            continue
        if not any((x_.get("url") or "") == url for x_ in lst):
            lst.append({"id": uuid.uuid4().hex[:10], "name": name, "url": url, "aktiv": True, "intervall": 60,
                        "farbe": "#ff9f0a", "angelegt": now_iso()})
            changed = True
        set_setting(flag, True)
    if changed:
        _abo_save_all(lst)


def _abo_loop():
    try:
        _abo_seed()
    except Exception:
        traceback.print_exc()
    time.sleep(40)
    while True:
        try:
            abo_fetch_all(only_due=True)
        except Exception:
            traceback.print_exc()
        time.sleep(60)


HOOK_GET["/api/kalabo/liste"] = lambda h, qs: h._send(200, abo_view())
HOOK_POST["/api/kalabo/speichern"] = lambda h, d: h._send(200, abo_save(d))
HOOK_POST["/api/kalabo/loeschen"] = lambda h, d: h._send(200, abo_delete(d))
HOOK_POST["/api/kalabo/abrufen"] = lambda h, d: h._send(200, abo_fetch(str(d["id"])) if d.get("id") else abo_fetch_all())
HOOK_START.append(_abo_loop)


def m29b_selftest():
    err = []
    aid = "_selftest_"
    try:
        if _abo_url("webcal://example.org/a.ics") != "https://example.org/a.ics":
            err.append("m29b: webcal-Link nicht umgesetzt")
        txt = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-WR-CALNAME:Laufzeiten\r\n"
               "BEGIN:VEVENT\r\nUID:t1@x\r\nDTSTART:20261026T060000Z\r\nDTEND:20261026T070000Z\r\nSUMMARY:MT 02 · Vorbereitung\r\n"
               "LOCATION:Johannstr. 1\\, 40476 Düsseldorf\r\nDESCRIPTION:Zeile 1\\nZeile\r\n  2\r\nEND:VEVENT\r\n"
               "BEGIN:VEVENT\r\nUID:t2@x\r\nSTATUS:CANCELLED\r\nDTSTART:20261027T060000Z\r\nSUMMARY:abgesagt\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        name, n = _abo_store(txt, aid, "")
        if name != "Laufzeiten" or n != 1:
            err.append(f"m29b: Speichern falsch ({name}, {n})")
        ev = q("SELECT * FROM kal_event WHERE cal_id=?", (_abo_cid(aid),), one=True) or {}
        if ev.get("location") != "Johannstr. 1, 40476 Düsseldorf" or "Zeile 1\nZeile 2" not in (ev.get("note") or ""):
            err.append("m29b: Ort/Beschreibung falsch gelesen")
        loc = ms_to_local(ev.get("start_ms") or 0)
        want = _kal_naive_local(datetime.datetime(2026, 10, 26, 6, 0, tzinfo=datetime.timezone.utc))
        if loc != want:
            err.append(f"m29b: UTC-Zeit falsch umgerechnet ({loc} statt {want})")
        try:
            _abo_store("<html>Fehler</html>", aid, "")
            err.append("m29b: HTML statt Kalender nicht erkannt")
        except ValueError:
            pass
    except Exception as e:
        err.append(f"m29b Ausnahme: {e}")
    finally:
        with DB_LOCK:
            CON.execute("DELETE FROM kal_event WHERE cal_id=?", (_abo_cid(aid),))
            CON.execute("DELETE FROM kal_cal WHERE id=?", (_abo_cid(aid),))
            CON.commit()
    return err


HOOK_SELFTEST.append(m29b_selftest)
print(f"INIT m29b_kalender_abo v{M29B_VERSION}")
