# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m57_apps  v1.0.0 (ab Programm v3.6.4)
# Apps: andere Web-Apps per Link im Programm erfassen (z. B. MediaFlow, TimeTree, Online-Banking, Lieferanten-Portal,
# Q-SYS Reflect, Crestron XiO) und mit einem Klick oeffnen - in einem eigenen Programmfenster oder im Standard-Browser.
# Auf Wunsch mit eigenem Eintrag in der Seitenleiste (Bereich "Apps").
# Datenschutz: das Programm ruft die Links NIE selbst ab (kein Vorschaubild, kein Favicon) - die Seite wird erst
# geladen, wenn du die App oeffnest, und bekommt dabei keine Programmdaten (kein Referer, keine Cookies des Programms).
# Gespeichert in den Einstellungen (apps) - damit auch im Backup.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M57_VERSION = "1.0.0"
M57_MODES = ("fenster", "browser")


def _apps():
    v = get_settings().get("apps")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = []
    return [a for a in (v or []) if isinstance(a, dict) and a.get("id")]


def _apps_save(lst):
    set_setting("apps", lst)


def _app_url(u):
    u = (u or "").strip()
    if u and not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = "https://" + u                      # "app.mediaflow.de" -> https://app.mediaflow.de
    if not re.match(r"^https?://[^\s/]+\.[^\s/]+|^https?://(localhost|\d{1,3}(\.\d{1,3}){3})(:\d+)?(/|$)", u, re.I):
        raise ValueError("Bitte einen Weblink eintragen (https://…).")
    if len(u) > 2000:
        raise ValueError("Link zu lang.")
    return u


def apps_view():
    return {"ok": True, "apps": _apps()}


def apps_save(d):
    lst = _apps()
    aid = str(d.get("id") or "")
    if aid:
        a = next((x_ for x_ in lst if x_["id"] == aid), None)
        if not a:
            raise ValueError("App nicht gefunden.")
    else:
        a = {"id": uuid.uuid4().hex[:10], "angelegt": now_iso()}
        lst.append(a)
    name = (d.get("name") or "").strip()[:60]
    if not name:
        raise ValueError("Bitte einen Namen eintragen.")
    a["name"] = name
    a["url"] = _app_url(d.get("url"))
    a["symbol"] = (d.get("symbol") or "").strip()[:2] or name[:1].upper()
    a["farbe"] = d.get("farbe") if re.fullmatch(r"#[0-9a-fA-F]{6}", d.get("farbe") or "") else (a.get("farbe") or "#6a48e0")
    a["oeffnen"] = d.get("oeffnen") if d.get("oeffnen") in M57_MODES else "fenster"
    a["seitenleiste"] = bool(d.get("seitenleiste", True))
    a["notiz"] = (d.get("notiz") or "").strip()[:300]
    a["kategorie"] = (d.get("kategorie") or "").strip()[:40]
    _apps_save(lst)
    return apps_view()


def apps_delete(d):
    aid = str(d.get("id") or "")
    _apps_save([x_ for x_ in _apps() if x_["id"] != aid])
    return apps_view()


def apps_sort(d):
    order = [str(i) for i in (d.get("ids") or [])]
    lst = _apps()
    lst.sort(key=lambda a: order.index(a["id"]) if a["id"] in order else 10 ** 6)
    _apps_save(lst)
    return apps_view()


def _app_window(title, url):
    """own program window (pywebview) - separate from the program page, like a small browser for this app"""
    w = globals().get("WIN")
    if w is None:
        return False
    try:
        import webview
        webview.create_window(title, url, width=1320, height=880, min_size=(640, 480))
        return True
    except Exception:
        traceback.print_exc()
        return False


def apps_open(d):
    lst = _apps()
    a = next((x_ for x_ in lst if x_["id"] == str(d.get("id") or "")), None)
    if not a:
        raise ValueError("App nicht gefunden.")
    url = _app_url(a.get("url"))
    mode = d.get("wie") if d.get("wie") in M57_MODES else a.get("oeffnen", "fenster")
    wo = "browser"
    if mode == "fenster" and _app_window(a.get("name") or "App", url):
        wo = "fenster"
    else:
        webbrowser.open(url)
    a["zuletzt"] = now_iso()
    a["anzahl"] = int(a.get("anzahl") or 0) + 1
    _apps_save(lst)
    return {"ok": True, "wo": wo, "name": a.get("name")}


def _apps_boot(d):
    try:
        d["apps"] = [{k: a.get(k) for k in ("id", "name", "symbol", "farbe", "seitenleiste", "kategorie")} for a in _apps()]
    except Exception:
        d["apps"] = []


HOOK_GET["/api/apps"] = lambda h, qs: h._send(200, apps_view())
HOOK_POST["/api/apps/speichern"] = lambda h, d: h._send(200, apps_save(d))
HOOK_POST["/api/apps/loeschen"] = lambda h, d: h._send(200, apps_delete(d))
HOOK_POST["/api/apps/sortieren"] = lambda h, d: h._send(200, apps_sort(d))
HOOK_POST["/api/apps/oeffnen"] = lambda h, d: h._send(200, apps_open(d))
HOOK_BOOT.append(_apps_boot)


def m57_selftest():
    err = []
    try:
        if _app_url("app.mediaflow.de/start") != "https://app.mediaflow.de/start":
            err.append("m57: Link ohne https:// nicht ergaenzt")
        for bad in ("javascript:alert(1)", "file:///C:/Windows", "ftp://x.de", "keinlink"):
            try:
                _app_url(bad)
                err.append(f"m57: unzulaessiger Link angenommen ({bad})")
            except ValueError:
                pass
        if _app_url("http://192.168.1.20:8080/") != "http://192.168.1.20:8080/":
            err.append("m57: Geraet im Heimnetz (IP) abgewiesen")
    except Exception as e:
        err.append(f"m57 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m57_selftest)
print(f"INIT m57_apps v{M57_VERSION}")
