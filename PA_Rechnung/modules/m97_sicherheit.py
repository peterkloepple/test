# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m97_sicherheit (v2.4.2)
# 1. Keine persoenlichen Daten mehr im Programmcode:
#    Bis v2.4.1 standen Firma, Anschrift, Bankverbindung, Fusszeilen, Mail-Absender und das
#    Standard-Passwort fuer Belege als eingebaute Standardwerte im Code. Ab v2.4.2 sind die
#    Standardwerte leer. Beim ersten Start uebernimmt dieses Modul einmalig die alten Werte
#    in die Einstellungen des Datenordners - aber NUR fuer Felder, die dort noch nie
#    gespeichert wurden. Gelesen werden die alten Werte aus den alten Programmdateien
#    (Programm\versionen\<Version>\modules bzw. die in der EXE eingebaute Version).
#    Fuer dich aendert sich also nichts; neue Datenordner starten leer.
# 2. Standard-Passwort fuer verschluesselte Belege (std_pw) nicht mehr im Klartext:
#    Es wird mit einem Schluessel aus deiner PIN verschluesselt (PBKDF2-SHA256 + Fernet/AES).
#    Der Schluessel entsteht nur im Arbeitsspeicher, wenn du die PIN eingibst - funktioniert
#    damit auf jedem PC mit demselben Datenordner. PIN aendern verschluesselt neu.
# Autor: T. Pfeiffer

import ast
import glob

M97_VERSION = "1.0.0"
M97_KEYS = ("firma", "inhaber", "absender", "bank", "iban", "bic", "kontoinhaber", "paypal_mail",
            "fuss1", "fuss2", "fuss3", "fuss4", "next_nr", "next_kdnr", "smtp_user", "smtp_from", "std_pw")
M97_PIN_SECRETS = ("std_pw",)
M97_ITER = 200000
M97 = {"key": None, "cache": {}, "lock": threading.RLock()}
M97_TEST = (__name__ == "pa_selbsttest")


# ------------------------------------------------------------ 1. old built-in values -> settings
def _m97_vt(v):
    try:
        return tuple(int(x) for x in re.findall(r"\d+", v)[:3])
    except Exception:
        return (0,)


def _m97_old_defaults():
    """Read DEFAULT_SETTINGS literals of older program versions (newest first)."""
    files = []
    app_dir = globals().get("APP_DIR") or os.path.join(DATA_DIR, "Programm")
    for f in glob.glob(os.path.join(app_dir, "versionen", "*", "modules", "m01_grundlagen.py")):
        files.append((_m97_vt(os.path.basename(os.path.dirname(os.path.dirname(f)))), f))
    for base in {os.environ.get("PA_RECHNUNG_RES_FALLBACK") or "", RES_DIR, os.path.dirname(os.path.abspath(__file__))}:
        f = os.path.join(base, "modules", "m01_grundlagen.py") if base else ""
        if f and os.path.isfile(f):
            files.append(((0,), f))
    files.sort(reverse=True)
    found = {}
    for _, f in files:
        try:
            tree = ast.parse(open(f, encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DEFAULT_SETTINGS" for t in node.targets) and isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and k.value in M97_KEYS and isinstance(v, ast.Constant) and isinstance(v.value, str):
                        if v.value.strip() and k.value not in found:
                            found[k.value] = v.value
    return found


def m97_migrate_defaults():
    if M97_TEST:
        return {"ok": True, "test": True}
    try:
        if q("SELECT v FROM settings WHERE k='m97_alt_uebernommen'", one=True):
            return {"ok": True, "schon": True}
        have = {r["k"] for r in q("SELECT k FROM settings")}
        missing = [k for k in M97_KEYS if k not in have and not (k == "std_pw" and "std_pw_enc" in have)]
        old = _m97_old_defaults() if missing else {}
        taken = []
        for k in missing:
            if k in old:
                set_setting(k, old[k])
                taken.append(k)
        set_setting("m97_alt_uebernommen", {"zeit": now_iso(), "uebernommen": taken, "fehlend": [k for k in missing if k not in old]})
        if taken:
            print("INIT m97: eingebaute Werte uebernommen:", ", ".join(taken))
        return {"ok": True, "uebernommen": taken}
    except Exception:
        traceback.print_exc()
        return {"ok": False}


HOOK_SCHEMA.append(m97_migrate_defaults)


# ------------------------------------------------------------ 2. PIN-protected secrets
def _m97_fernet(key):
    from cryptography.fernet import Fernet
    return Fernet(key)


def _m97_salt():
    r = q("SELECT v FROM settings WHERE k='m97_salt'", one=True)
    if r:
        try:
            return bytes.fromhex(json.loads(r["v"]))
        except Exception:
            pass
    salt = os.urandom(16)
    x("INSERT OR REPLACE INTO settings (k, v) VALUES (?, ?)", ("m97_salt", json.dumps(salt.hex())))
    return salt


def _m97_derive(pin):
    raw = hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"), _m97_salt(), M97_ITER, 32)
    return base64.urlsafe_b64encode(raw)


def _m97_raw(k):
    r = q("SELECT v FROM settings WHERE k=?", (k,), one=True)
    if not r:
        return None
    try:
        return json.loads(r["v"])
    except Exception:
        return r["v"]


def _m97_decrypt(tok, key=None):
    key = key or M97["key"]
    if not key or not tok:
        return ""
    ck = (key, tok)
    if ck in M97["cache"]:
        return M97["cache"][ck]
    try:
        v = _m97_fernet(key).decrypt(tok.encode()).decode("utf-8")
    except Exception:
        v = ""
    M97["cache"][ck] = v
    return v


def _m97_store_secret(k, value, key=None):
    key = key or M97["key"]
    if not key:
        return False
    tok = _m97_fernet(key).encrypt(str(value or "").encode("utf-8")).decode()
    x("INSERT OR REPLACE INTO settings (k, v) VALUES (?, ?)", (k + "_enc", json.dumps(tok)))
    x("DELETE FROM settings WHERE k=?", (k,))
    return True


def _m97_open(pin, old_key=None):
    """PIN accepted -> key in memory; plaintext secrets get encrypted; on PIN change re-encrypt."""
    try:
        new_key = _m97_derive(pin)
    except Exception:
        traceback.print_exc()
        return
    with M97["lock"]:
        for k in M97_PIN_SECRETS:
            plain = _m97_raw(k)
            enc = _m97_raw(k + "_enc")
            val = None
            if enc and old_key:
                val = _m97_decrypt(enc, old_key)
            elif enc and not plain:
                val = None                    # already encrypted with this PIN
            if plain not in (None, ""):
                val = str(plain)
            if val is not None:
                try:
                    _m97_store_secret(k, val, new_key)
                except Exception:
                    traceback.print_exc()
        M97["key"] = new_key
        M97["cache"].clear()


@chain_step("m92_verify", "m97_sicherheit")
def _m97_step_m92_verify(_next, pin):
    r = _next(pin)
    if r and r[0]:
        _m97_open(str(pin))
    return r


@chain_step("_m92_store", "m97_sicherheit")
def _m97_step_m92_store(_next, pin):
    old_key = M97["key"]
    _next(pin)
    _m97_open(str(pin), old_key=old_key)


@chain_step("get_settings", "m97_sicherheit")
def _m97_step_get_settings(_next, ):
    s = _next()
    for k in M97_PIN_SECRETS:
        enc = s.pop(k + "_enc", None)
        if enc:
            s[k] = _m97_decrypt(enc)
    s.pop("m97_salt", None)
    return s


@chain_step("set_setting", "m97_sicherheit")
def _m97_step_set_setting(_next, k, v):
    if k in M97_PIN_SECRETS and M97["key"]:
        try:
            if _m97_store_secret(k, v):
                M97["cache"].clear()
                return
        except Exception:
            traceback.print_exc()
    return _next(k, v)


def _m97_selftest():
    err = []
    try:
        for k in M97_KEYS:
            v = DEFAULT_SETTINGS.get(k)
            if k not in ("next_nr", "next_kdnr") and v not in ("", None):
                err.append(f"m97: Standardwert {k} ist nicht leer")
        key = base64.urlsafe_b64encode(hashlib.pbkdf2_hmac("sha256", b"482915", b"0123456789abcdef", 1000, 32))
        tok = _m97_fernet(key).encrypt(b"geheim").decode()
        if _m97_decrypt(tok, key) != "geheim":
            err.append("m97: Ver-/Entschluesselung fehlerhaft")
    except ImportError:
        err.append("m97: Bibliothek cryptography fehlt")
    except Exception as e:
        err.append(f"m97 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m97_selftest)
