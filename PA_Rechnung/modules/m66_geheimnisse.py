# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m66_geheimnisse (v2.0.17)
# Gespeicherte Passwoerter (Mail, IMAP, FinTS-PIN, Backup, Kalender, Microsoft-Token, Bank-Schluessel)
# pro PC und Windows-Benutzer verschluesselt:
#  - bisher: ein DPAPI-Block -> nur auf dem PC/Benutzer lesbar, auf dem er gespeichert wurde
#    (Datenordner im OneDrive / auf zweitem PC / nach Windows-Kennwort-Reset -> "laesst sich nicht entschluesseln")
#  - jetzt: "pc:"-Eintrag mit einem DPAPI-Block je PC+Benutzer. Wird das Passwort auf einem weiteren
#    PC eingetragen, kommt dessen Block dazu; die anderen PCs behalten ihren. Wird es auf einem PC
#    GEAENDERT (alter Wert dort lesbar und anders), gelten die Bloecke der anderen PCs als veraltet.
#  - Test-Mail mit eingetipptem Passwort erfolgreich -> Passwort wird automatisch gespeichert.
#  - Bootstrap meldet, ob das Mail-Passwort auf DIESEM PC lesbar ist (smtp_set / smtp_fremd).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M66_VERSION = "1.0.0"

import getpass as _m66_gp
import socket as _m66_sock


def pc_id():
    try:
        u = os.environ.get("USERNAME") or _m66_gp.getuser()
    except Exception:
        u = "?"
    h = os.environ.get("COMPUTERNAME") or _m66_sock.gethostname() or "?"
    return f"{h}\\{u}".lower()


def _m66_one(raw):
    if sys.platform.startswith("win"):
        try:
            return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
        except Exception as e:
            # never store a readable base64 copy on Windows - the caller shows the error instead
            traceback.print_exc()
            raise ValueError(f"Passwort konnte nicht verschlüsselt werden (Windows-DPAPI: {e}) - es wurde nicht gespeichert.")
    return "b64:" + base64.b64encode(raw).decode()   # development / non-Windows only


def _m66_open1(v):
    if v.startswith("dpapi:"):
        return _dpapi(base64.b64decode(v[6:]), False).decode("utf-8")
    if v.startswith("b64:"):
        return base64.b64decode(v[4:]).decode("utf-8")
    return v


def _m66_map(v):
    try:
        m = json.loads(v[3:])
        return m if isinstance(m, dict) and isinstance(m.get("pcs"), dict) else None
    except Exception:
        return None


class SecretOtherPC(ValueError):
    pass


def protect_secret(txt):
    if not txt:
        return ""
    return "pc:" + json.dumps({"pcs": {pc_id(): _m66_one(txt.encode("utf-8"))}}, separators=(",", ":"))


def unprotect_secret(v):
    if not v:
        return ""
    if isinstance(v, str) and v.startswith("pc:"):
        m = _m66_map(v)
        if not m:
            raise SecretOtherPC("Gespeichertes Passwort ist beschaedigt.")
        me = m["pcs"].get(pc_id())
        if me:
            return _m66_open1(me)
        # older entry without this PC: try the others (e.g. b64 from tests, same user under other PC name)
        for blob in m["pcs"].values():
            try:
                return _m66_open1(blob)
            except Exception:
                pass
        raise SecretOtherPC("Passwort wurde auf einem anderen PC gespeichert: " + ", ".join(sorted(m["pcs"])))
    return _m66_open1(v)


def secret_readable(v):
    if not v:
        return False
    try:
        unprotect_secret(v)
        return True
    except Exception:
        return False


@chain_step("set_setting", "m66_geheimnisse")
def _m66_step_set_setting(_next, k, v):
    # merge per-PC blocks: entering the same secret on a second PC keeps the first PC working
    if isinstance(v, str) and v.startswith("pc:"):
        try:
            new = _m66_map(v)
            old = get_settings().get(k)
            if new and isinstance(old, str) and old:
                me = pc_id()
                old_map = _m66_map(old) if old.startswith("pc:") else None
                if old_map is None and old.startswith(("dpapi:", "b64:")):
                    old_map = {"pcs": {"(frueher)": old}}
                if old_map:
                    try:
                        cur_here = unprotect_secret(old)
                    except Exception:
                        cur_here = None
                    new_val = _m66_open1(new["pcs"][me])
                    if cur_here is None or cur_here == new_val:
                        legacy_here = cur_here is not None and not old.startswith("pc:")
                        pcs = {} if legacy_here else {kk: vv for kk, vv in old_map["pcs"].items() if kk != me}
                        pcs[me] = new["pcs"][me]
                        v = "pc:" + json.dumps({"pcs": pcs}, separators=(",", ":"))
        except Exception:
            traceback.print_exc()
    return _next(k, v)


# ---------------- mail: clear message + auto-save after a successful test ----------------

@chain_step("smtp_cfg", "m66_geheimnisse")
def _m66_step_smtp_cfg(_next, over=None):
    c = _next(over)
    if c.get("pass_err"):
        c["pass_err"] = (f"Das Mail-Passwort ist auf diesem PC ({pc_id()}) noch nicht eingetragen – es wurde auf einem anderen PC "
                         "oder unter einem anderen Windows-Benutzer gespeichert (z. B. Datenordner im OneDrive oder nach "
                         "Windows-Kennwort-Reset). Bitte in den Einstellungen → E-Mail einmal neu eintragen und speichern; "
                         "die anderen PCs behalten ihr Passwort.")
    return c


@chain_step("mail_test", "m66_geheimnisse")
def _m66_step_mail_test(_next, d):
    r = _next(d)
    try:
        pw = str((d or {}).get("pass") or "")
        if r.get("ok") and pw and str((d or {}).get("auth") or "pass") != "ms":
            set_setting("smtp_pass", protect_secret(pw))
            for k, sk in (("host", "smtp_host"), ("user", "smtp_user")):
                if (d or {}).get(k):
                    set_setting(sk, str(d[k]).strip())
            r["gespeichert"] = True
        if r.get("ok"):
            set_setting("mail_status", {"zeit": now_iso(), "ok": True, "fehler": ""})
            if r.get("gespeichert"):
                r.setdefault("schritte", []).append("✓ Passwort für diesen PC gespeichert")
    except Exception as e:
        traceback.print_exc()
        if r.get("ok") and isinstance(e, ValueError):
            r.setdefault("schritte", []).append("✗ " + str(e))
    return r


def _m66_boot(d):
    s = get_settings()
    v = s.get("smtp_pass") or ""
    d["smtp_set"] = secret_readable(v)
    d["smtp_fremd"] = bool(v) and not d["smtp_set"]
    d["pc_id"] = pc_id()


HOOK_POST["/api/mail/test"] = lambda h, d: h._send(200, mail_test(d or {}))
HOOK_BOOT.append(_m66_boot)
