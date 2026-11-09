# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m95_mail_fix (v2.4.0)
# E-Mail-Abruf (IMAP) mit Gmail: "[AUTHENTICATIONFAILED] Invalid credentials" obwohl der Versand geht.
# Ursachen im Programm bis v2.3.1:
#  1. "Verbindung testen" im Reiter E-Mail-Abruf hat ein neu eingetipptes Passwort zwar getestet,
#     aber NICHT gespeichert - der Hintergrund-Abruf nahm weiter das alte (falsche) Passwort.
#  2. War einmal ein IMAP-Passwort gespeichert (z. B. das normale Google-Passwort oder ein altes
#     App-Passwort), wurde das funktionierende Passwort vom E-Mail-Versand nie probiert.
# Jetzt:
#  - Gmail: Leerzeichen im App-Passwort werden entfernt, Benutzer ohne "@" wird zu ...@gmail.com.
#  - Anmeldung probiert der Reihe nach: eingetipptes Passwort -> gespeichertes Abruf-Passwort ->
#    Passwort vom E-Mail-Versand (gleiche Adresse). Das erste, das klappt, wird fuer den Abruf
#    gespeichert; ein eingetipptes Gmail-App-Passwort zusaetzlich fuer den Versand (gleiche Adresse).
#  - Klappt keins: klare Meldung, welche Passwoerter geprueft wurden, und was zu tun ist.
# Autor: T. Pfeiffer

M95_VERSION = "1.0.0"
M95_TL = threading.local()       # last connect of this thread (for the test result text)
def _m95_is_gmail(user, host):
    u, h = (user or "").lower(), (host or "").lower()
    return "gmail" in h or "googlemail" in h or u.endswith("@gmail.com") or u.endswith("@googlemail.com")


def _m95_norm_pw(pw, gmail):
    pw = str(pw or "")
    if gmail:
        pw = re.sub(r"\s", "", pw)          # app passwords are shown in 4 blocks - spaces are only formatting
    return pw


def _m95_same_addr(a, b):
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def _m95_norm_cfg(c):
    if c.get("auth") != "ms" and _m95_is_gmail(c.get("user"), c.get("host")):
        if c.get("user") and "@" not in c["user"]:
            c["user"] = c["user"].strip() + "@gmail.com"
        if not c.get("host"):
            c["host"] = "imap.gmail.com"
        c["pass"] = _m95_norm_pw(c.get("pass"), True)
    return c


def _m95_target(c):
    return (str(c.get("host") or "").strip().lower(), str(c.get("user") or "").strip().lower())


@chain_step("imap_cfg", "m95_mail_fix")
def _m95_step_imap_cfg(_next, over=None):
    c = _m95_norm_cfg(_next(over))
    c["_typed"] = bool(over and over.get("pass"))
    # v2.6.3: stored passwords (IMAP and sending) only go to the stored server + user - "Verbindung testen" with a
    # newly typed host/user but no typed password sent them to that other server
    c["_same"] = True
    if over and not c["_typed"] and c.get("auth") != "ms":
        try:
            base = _m95_norm_cfg(_next(None))
            c["_same"] = _m95_target(base) == _m95_target(c)
        except Exception:
            c["_same"] = False
        if not c["_same"]:
            c["pass"] = ""
    return c


def _m95_secret(key):
    try:
        return unprotect_secret(get_settings().get(key) or "")
    except Exception:
        return ""


@chain_step("imap_connect", "m95_mail_fix")
def _m95_step_imap_connect(_next, c, timeout=20):
    M95_TL.c = c
    if c.get("auth") == "ms":
        return _next(c, timeout)
    s = get_settings()
    gmail = _m95_is_gmail(c.get("user"), c.get("host"))
    stored = _m95_norm_pw(_m95_secret("mi_pass"), gmail)
    same_box = _m95_same_addr(c.get("user"), str(s.get("smtp_user") or ""))
    cands, seen = [], set()

    def add(pw, label):
        pw = _m95_norm_pw(pw, gmail)
        if pw and pw not in seen:
            seen.add(pw)
            cands.append((pw, label))

    add(c.get("pass"), "eingegebenes Passwort" if c.get("_typed") else "gespeichertes Abruf-Passwort")
    if not c.get("_typed") and c.get("_same", True):
        add(stored, "gespeichertes Abruf-Passwort")
        if same_box:
            add(_m95_secret("smtp_pass"), "Passwort vom E-Mail-Versand")
    if not cands:
        raise ValueError("Bitte das Passwort eintragen" + (" (bei Gmail: App-Passwort, 16 Zeichen)." if gmail else "."))
    tried = []
    for pw, label in cands:
        try:
            M = _next(dict(c, **{"pass": pw}), timeout)
        except ValueError as e:
            if "Anmeldung abgelehnt" in str(e):
                tried.append(label)
                continue
            raise
        # success: remember the password that works
        try:
            if pw != stored:
                set_setting("mi_pass", protect_secret(pw))
                c["_gespeichert"] = True
            if c.get("_typed") and gmail and same_box and pw != _m95_norm_pw(_m95_secret("smtp_pass"), True):
                set_setting("smtp_pass", protect_secret(pw))       # one Gmail app password for fetching AND sending
                c["_auch_versand"] = True
        except Exception:
            traceback.print_exc()
        return M
    if gmail:
        raise ValueError("Gmail lehnt die Anmeldung ab (geprüft: " + ", ".join(tried) + "). "
                         "Häufigste Ursache: Das App-Passwort gilt nicht mehr – Google löscht alle App-Passwörter, sobald das Google-Passwort geändert wird. "
                         "So geht's: myaccount.google.com/apppasswords öffnen → neues App-Passwort erzeugen (z. B. „PA Rechnung“) → "
                         "hier ins Passwortfeld kopieren (Leerzeichen egal) → „Verbindung testen“. Es wird dann für Abruf UND Versand gespeichert. "
                         f"Benutzer muss die volle Adresse sein (jetzt: {c.get('user')}).")
    raise ValueError("Anmeldung abgelehnt (geprüft: " + ", ".join(tried) + ") – Benutzer/Passwort prüfen (bei Outlook/GMX/Web.de ggf. App-Passwort oder IMAP im Webmail freischalten).")


@chain_step("imap_test", "m95_mail_fix")
def _m95_step_imap_test(_next, over=None):
    M95_TL.c = None
    r = _next(over)
    c = getattr(M95_TL, "c", None) or {}
    if r.get("ok") and c.get("_gespeichert"):
        r["info"] = (r.get("info") or "") + " Passwort für den Abruf gespeichert" + (" – und für den Versand." if c.get("_auch_versand") else ".")
        r["gespeichert"] = True
    return r


def _m95_selftest():
    err = []
    try:
        if imap_cfg({"host": "imap.fremder-server.example", "user": "x@fremder-server.example"}).get("pass"):
            err.append("m95: gespeichertes Passwort fuer fremden Server verwendet")
        if _m95_norm_pw("abcd efgh ijkl mnop", True) != "abcdefghijklmnop":
            err.append("m95: Leerzeichen im App-Passwort nicht entfernt")
        if not _m95_is_gmail("x@googlemail.com", "") or _m95_is_gmail("x@web.de", "imap.web.de"):
            err.append("m95: Gmail-Erkennung fehlerhaft")
    except Exception as e:
        err.append(f"m95 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m95_selftest)
