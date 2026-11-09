# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m87_ansichten (v2.0.19)
# Gespeicherte Ansichten (Filter, Suche, Sortierung, Feld-Filter) fuer die Listen
# Rechnungen/Angebote, Kunden, Projekte, Belege, Bausteine und Lager.
# Gespeichert in den Einstellungen (m87_ansichten) - damit im Datenordner und im Backup.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M87_VERSION = "1.0.0"
M87_VIEWS = ("inv", "users", "proj", "beleg", "blocks", "m42lager")
# v2.1.0: read-modify-write of the settings list one at a time (two windows saving at once lost one view)
M87_LOCK = threading.RLock()


def m87_list():
    v = get_settings().get("m87_ansichten") or []
    return v if isinstance(v, list) else []


def m87_save(d):
    with M87_LOCK:
        return _m87_save(d)


def _m87_save(d):
    name = (d.get("name") or "").strip()[:60]
    if not name:
        raise ValueError("Bitte einen Namen für die Ansicht angeben.")
    if d.get("view") not in M87_VIEWS:
        raise ValueError("Diese Seite kann keine Ansichten speichern.")
    st = d.get("state") if isinstance(d.get("state"), dict) else {}
    if len(json.dumps(st)) > 20000:
        raise ValueError("Ansicht zu groß.")
    allv = m87_list()
    vid = str(d.get("id") or "")
    cur_ = next((a for a in allv if a.get("id") == vid), None) if vid else None
    if cur_:
        cur_.update({"name": name, "state": st if d.get("state") is not None else cur_.get("state"), "dash": bool(d.get("dash", cur_.get("dash")))})
    else:
        vid = uuid.uuid4().hex[:10]
        allv.append({"id": vid, "name": name, "view": d["view"], "state": st, "dash": bool(d.get("dash")), "created": now_iso()})
    set_setting("m87_ansichten", allv)
    return {"ok": True, "id": vid, "ansichten": allv}


def m87_delete(vid):
    with M87_LOCK:
        return _m87_delete(vid)


def _m87_delete(vid):
    allv = [a for a in m87_list() if a.get("id") != str(vid)]
    set_setting("m87_ansichten", allv)
    return {"ok": True, "ansichten": allv}


def m87_sort(ids):
    with M87_LOCK:
        return _m87_sort(ids)


def _m87_sort(ids):
    allv = m87_list()
    pos = {str(i): k for k, i in enumerate(ids or [])}
    allv.sort(key=lambda a: pos.get(a.get("id"), 10 ** 6))
    set_setting("m87_ansichten", allv)
    return {"ok": True, "ansichten": allv}


def _m87_boot(d):
    d["m87"] = m87_list()


HOOK_BOOT.append(_m87_boot)
HOOK_GET["/api/m87/list"] = lambda h, qs: h._send(200, {"ansichten": m87_list()})
HOOK_POST["/api/m87/save"] = lambda h, d: h._send(200, m87_save(d))
HOOK_POST["/api/m87/delete"] = lambda h, d: h._send(200, m87_delete(d.get("id")))
HOOK_POST["/api/m87/sort"] = lambda h, d: h._send(200, m87_sort(d.get("ids")))


def _m87_selftest():
    err = []
    try:
        before = get_settings().get("m87_ansichten")
        r = m87_save({"name": "_ST offen", "view": "inv", "state": {"invF": {"status": "offen"}}})
        if not any(a["id"] == r["id"] and a["state"]["invF"]["status"] == "offen" for a in m87_list()):
            err.append("m87: Ansicht nicht gespeichert")
        m87_delete(r["id"])
        if any(a["id"] == r["id"] for a in m87_list()):
            err.append("m87: Ansicht nicht geloescht")
        set_setting("m87_ansichten", before or [])
    except Exception as e:
        err.append(f"m87 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m87_selftest)
