# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m92_pin_sperre (v2.4.2)
# PIN-Sperre: das Programm laesst sich NUR mit einer sechsstelligen PIN oeffnen.
#  - Erster Start: PIN festlegen (zweimal eingeben). Danach bei JEDEM Start PIN-Abfrage.
#  - Kein anderer Zugang: kein Passwort, keine Hintertuer, kein "PIN vergessen".
#  - Die Sperre sitzt im Server: solange die PIN nicht eingegeben ist, liefert der Hauptserver
#    nur die Sperrseite aus - jede Daten-/Upload-/Export-Anfrage wird mit 401 abgelehnt.
#  - Handy-Upload (m32), Abnahme (m77) und REST-API/PWA (m88) antworten mit 423, bis die
#    PIN nach dem Programmstart einmal am PC eingegeben wurde.
#  - PIN nur als PBKDF2-SHA256-Hash (Salz, 300000 Runden) in der Datenbank, Tabelle m92_pin.
#  - Fehlversuche: ab dem 5. Fehler Wartezeit 30 s, verdoppelt je Fehler, max. 15 min;
#    der Zaehler steht in der Datenbank (Neustart setzt ihn nicht zurueck).
#  - Sitzung: zufaelliges Cookie (HttpOnly, SameSite=Strict), nur im Speicher -> nach jedem
#    Neustart wieder PIN. "Jetzt sperren" / Strg+L / automatische Sperre nach Leerlauf.
# Autor: T. Pfeiffer

import secrets
import hmac

M92_VERSION = "1.1.0"
# v1.1.0 (v2.4.2): LAN servers (handy upload, signature, app/REST) are also locked while the program is
#   locked (Strg+L, idle lock) - unless "m92_lan_offen" is set (e.g. stopwatch on the phone keeps running).
M92_ITER = 300000
M92_FREE_FAILS = 4            # so many wrong PINs without waiting
M92_WAIT_BASE = 30            # seconds after the first counted failure
M92_WAIT_MAX = 900            # 15 minutes
M92_COOKIE = "pa92"
# v1.0.1: the update self test (m22 selftest_core) runs this core in its own namespace
# "pa_selbsttest" with a throw-away data folder - nobody can enter a PIN there. The LAN
# servers must answer normally in that test instance (m88 test calls /v1/...), otherwise
# every update is rejected. The real program never runs under this name.
M92_TESTLAUF = (__name__ == "pa_selbsttest")
M92 = {"tokens": {}, "geoeffnet": M92_TESTLAUF, "lock": threading.Lock()}


# ---------------------------------------------------------------- storage
def _m92_schema():
    x("""CREATE TABLE IF NOT EXISTS m92_pin (
           id INTEGER PRIMARY KEY CHECK (id = 1),
           salt TEXT, hash TEXT, iter INTEGER,
           fails INTEGER DEFAULT 0, gesperrt_bis REAL DEFAULT 0,
           gesetzt TEXT, geaendert TEXT)""")


HOOK_SCHEMA.append(_m92_schema)


def _m92_row():
    try:
        return q("SELECT * FROM m92_pin WHERE id=1", one=True)
    except Exception:
        return None


def m92_has_pin():
    r = _m92_row()
    return bool(r and r.get("hash") and r.get("salt"))


def _m92_hash(pin, salt_hex, it):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), int(it)).hex()


def _m92_check_format(pin):
    pin = str(pin or "")
    if not re.fullmatch(r"\d{6}", pin):
        raise ValueError("Die PIN muss aus genau 6 Ziffern bestehen.")
    if len(set(pin)) == 1:
        raise ValueError("Bitte keine PIN aus lauter gleichen Ziffern.")
    if pin in "0123456789" or pin in "9876543210" or pin in "1234567890":
        raise ValueError("Bitte keine fortlaufende Ziffernfolge als PIN.")
    return pin


def _m92_store(pin):
    salt = secrets.token_hex(16)
    h = _m92_hash(pin, salt, M92_ITER)
    now = now_iso()
    if _m92_row():
        x("UPDATE m92_pin SET salt=?, hash=?, iter=?, fails=0, gesperrt_bis=0, geaendert=? WHERE id=1", (salt, h, M92_ITER, now))
    else:
        x("INSERT INTO m92_pin (id, salt, hash, iter, fails, gesperrt_bis, gesetzt, geaendert) VALUES (1,?,?,?,0,0,?,?)",
          (salt, h, M92_ITER, now, now))


def _m92_wait_left():
    r = _m92_row() or {}
    return max(0, int(round(float(r.get("gesperrt_bis") or 0) - time.time())))


def m92_verify(pin):
    """-> (ok, message, wait_seconds). Counts failures and enforces the waiting time."""
    with M92["lock"]:
        r = _m92_row()
        if not r or not r.get("hash"):
            return False, "Noch keine PIN festgelegt.", 0
        left = int(round(float(r.get("gesperrt_bis") or 0) - time.time()))
        if left > 0:
            return False, f"Zu viele Fehlversuche - bitte {_m92_fmt(left)} warten.", left
        pin = str(pin or "")
        ok = bool(re.fullmatch(r"\d{6}", pin)) and hmac.compare_digest(_m92_hash(pin, r["salt"], r["iter"] or M92_ITER), r["hash"])
        if ok:
            x("UPDATE m92_pin SET fails=0, gesperrt_bis=0 WHERE id=1")
            return True, "", 0
        fails = int(r.get("fails") or 0) + 1
        wait = 0
        if fails > M92_FREE_FAILS:
            wait = min(M92_WAIT_MAX, M92_WAIT_BASE * (2 ** (fails - M92_FREE_FAILS - 1)))
        x("UPDATE m92_pin SET fails=?, gesperrt_bis=? WHERE id=1", (fails, time.time() + wait if wait else 0))
        if wait:
            return False, f"PIN falsch. Nächster Versuch in {_m92_fmt(wait)}.", wait
        rest = M92_FREE_FAILS - fails
        return False, "PIN falsch." + (f" Noch {rest} Versuch{'e' if rest != 1 else ''} ohne Wartezeit." if rest > 0 else
                                       " Ab jetzt Wartezeit nach jedem Fehler."), 0


def _m92_fmt(sec):
    sec = int(sec)
    return f"{sec} s" if sec < 60 else f"{sec // 60} min {sec % 60:02d} s"


# ---------------------------------------------------------------- session
def _m92_cookie(handler):
    ck = handler.headers.get("Cookie") or ""
    m = re.search(r"(?:^|;\s*)" + M92_COOKIE + r"=([A-Za-z0-9_\-]{20,80})", ck)
    return m.group(1) if m else ""


def _m92_idle_sec():
    """server side idle lock (setting m92_autolock in minutes, 0 = off) - backstop for the timer in the UI"""
    try:
        return max(0, int(get_settings().get("m92_autolock") or 0)) * 60
    except Exception:
        return 0


def _m92_purge(idle):
    """drop sessions idle for longer than the autolock time (caller holds M92["lock"])"""
    if idle > 0:
        now = time.time()
        for k in [k for k, t in M92["tokens"].items() if now - t > idle]:
            M92["tokens"].pop(k, None)


def m92_session_ok(handler):
    tok = _m92_cookie(handler)
    if not tok:
        return False
    idle = _m92_idle_sec()
    with M92["lock"]:
        _m92_purge(idle)
        for k in M92["tokens"]:
            if hmac.compare_digest(k.encode(), tok.encode()):
                M92["tokens"][k] = time.time()     # every authorised request counts as activity
                return True
    return False


def _m92_new_session():
    tok = secrets.token_urlsafe(32)
    with M92["lock"]:
        M92["tokens"][tok] = time.time()
        M92["geoeffnet"] = True
    return {"Set-Cookie": f"{M92_COOKIE}={tok}; Path=/; HttpOnly; SameSite=Strict"}


def m92_lock_all():
    with M92["lock"]:
        M92["tokens"].clear()


_M92_CLEAR = {"Set-Cookie": f"{M92_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"}


# ---------------------------------------------------------------- lock page
M92_PAGE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pfeiffer-Audio Rechnung - gesperrt</title>
<style>
:root{--bg:#17151f;--bg2:#211e2c;--ink:#f3f1f8;--mute:#8d87a0;--acc:#6a48e0;--acc2:#8a6cf0;--bad:#e2574f;--ok:#2fb47c;
 --font:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;--disp:"Segoe UI Variable Display","Segoe UI",system-ui,sans-serif}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:radial-gradient(1200px 700px at 50% -10%,#2a2440 0%,var(--bg) 60%);color:var(--ink);font:14px/1.45 var(--font);-webkit-font-smoothing:antialiased;user-select:none}
.wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:24px}
.box{width:360px;max-width:100%;text-align:center}
.logo{width:56px;height:76px;object-fit:contain;background:#fff;border-radius:12px;padding:4px;margin:0 auto 14px;display:block}
h1{font:600 20px/1.2 var(--disp);margin:0 0 4px;letter-spacing:.2px}
.sub{color:var(--mute);font-size:13px;min-height:19px;margin-bottom:22px}
.dots{display:flex;gap:12px;justify-content:center;margin-bottom:10px}
.dot{width:40px;height:50px;border-radius:10px;background:var(--bg2);border:1.5px solid #34304a;display:flex;align-items:center;justify-content:center;transition:border-color .12s,background .12s}
.dot.f{border-color:var(--acc2)}
.dot.f::after{content:"";width:12px;height:12px;border-radius:50%;background:var(--ink)}
.dot.cur{border-color:var(--acc2);box-shadow:0 0 0 3px rgba(138,108,240,.22)}
.msg{min-height:20px;font-size:13px;margin:8px 0 16px;color:var(--bad)}
.msg.ok{color:var(--ok)}
.shake{animation:sh .38s}
@keyframes sh{20%{transform:translateX(-9px)}40%{transform:translateX(8px)}60%{transform:translateX(-6px)}80%{transform:translateX(4px)}}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;max-width:276px;margin:0 auto}
.k{height:58px;border-radius:14px;border:0;background:var(--bg2);color:var(--ink);font:500 22px var(--disp);cursor:pointer;transition:background .1s,transform .06s}
.k:hover{background:#2c283b}.k:active{transform:scale(.96);background:var(--acc)}
.k.s{font-size:13px;color:var(--mute)}
.k:disabled{opacity:.35;cursor:default}
.foot{margin-top:22px;color:var(--mute);font-size:11.5px}
</style></head><body>
<div class="wrap"><div class="box">
 <img class="logo" src="/logo" alt="" onerror="this.style.display='none'">
 <h1 id="t">Pfeiffer-Audio Rechnung</h1>
 <div class="sub" id="sub">PIN eingeben</div>
 <div class="dots" id="dots"></div>
 <div class="msg" id="msg"></div>
 <div class="pad" id="pad"></div>
 <div class="foot">__VER__ &middot; Zugang nur mit PIN</div>
</div></div>
<script>
"use strict";
let pin = "", first = "", mode = "unlock", busy = false, waitT = null;
const $ = id => document.getElementById(id);
function dots(){ $("dots").innerHTML = [0,1,2,3,4,5].map(i => `<div class="dot ${i < pin.length ? "f" : ""} ${i === pin.length ? "cur" : ""}"></div>`).join(""); }
function msg(t, ok){ const m = $("msg"); m.textContent = t || ""; m.className = "msg" + (ok ? " ok" : ""); }
function shake(){ const d = $("dots"); d.classList.remove("shake"); void d.offsetWidth; d.classList.add("shake"); }
function padOn(on){ document.querySelectorAll(".k").forEach(b => b.disabled = !on); }
function pad(){ const keys = ["1","2","3","4","5","6","7","8","9","C","0","<"];
  $("pad").innerHTML = keys.map(k => `<button class="k ${k === "C" || k === "<" ? "s" : ""}" data-k="${k}">${k === "<" ? "&#9003;" : k === "C" ? "L&ouml;schen" : k}</button>`).join("");
  $("pad").onclick = e => { const b = e.target.closest(".k"); if (b) key(b.dataset.k); }; }
function key(k){
  if (busy) return;
  if (k === "C") { pin = ""; } else if (k === "<") { pin = pin.slice(0, -1); }
  else if (/^\d$/.test(k) && pin.length < 6) { pin += k; }
  dots(); if (pin.length === 6) setTimeout(submit, 90);
}
async function post(url, body){
  const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), credentials: "same-origin"});
  return r.json().catch(() => ({ok: false, error: "Fehler " + r.status}));
}
function wait(sec){
  clearInterval(waitT); padOn(false); busy = true;
  const end = Date.now() + sec * 1000;
  const tick = () => { const l = Math.ceil((end - Date.now()) / 1000);
    if (l <= 0) { clearInterval(waitT); busy = false; padOn(true); msg(""); return; }
    msg("Zu viele Fehlversuche - bitte " + (l >= 60 ? Math.floor(l / 60) + " min " + String(l % 60).padStart(2, "0") + " s" : l + " s") + " warten."); };
  tick(); waitT = setInterval(tick, 500);
}
async function submit(){
  if (pin.length !== 6 || busy) return;
  const p = pin;
  if (mode === "setup1") { first = p; pin = ""; mode = "setup2"; $("sub").textContent = "PIN zur Bestätigung wiederholen"; msg(""); dots(); return; }
  busy = true;
  let r;
  try {
    r = mode === "setup2" ? await post("/api/m92/setup", {pin: first, pin2: p}) : await post("/api/m92/unlock", {pin: p});
  } catch (e) { r = {ok: false, error: "Keine Verbindung zum Programm."}; }
  busy = false; pin = ""; dots();
  if (r.ok) { msg("Entsperrt", true); padOn(false); location.replace("/"); return; }
  shake();
  if (mode === "setup2") { mode = "setup1"; first = ""; $("sub").textContent = "Neue 6-stellige PIN festlegen"; }
  msg(r.error || "PIN falsch.");
  if (r.wait) wait(r.wait);
}
document.addEventListener("keydown", e => {
  if (/^\d$/.test(e.key)) { key(e.key); e.preventDefault(); }
  else if (e.key === "Backspace") { key("<"); e.preventDefault(); }
  else if (e.key === "Escape" || e.key === "Delete") { key("C"); e.preventDefault(); }
});
(async () => {
  pad(); dots();
  let s = {};
  try { s = await (await fetch("/api/m92/status", {credentials: "same-origin"})).json(); } catch (e) {}
  if (s.offen) { location.replace("/"); return; }
  if (!s.pin) { mode = "setup1"; $("t").textContent = "PIN festlegen"; $("sub").textContent = "Neue 6-stellige PIN festlegen";
    msg("Ohne diese PIN lässt sich das Programm nicht mehr öffnen - gut merken!", true); }
  if (s.wait) wait(s.wait);
})();
</script></body></html>"""


def _m92_page():
    return M92_PAGE.replace("__VER__", f"v{APP_VERSION}")


# ---------------------------------------------------------------- own routes (/api/m92/*)
def _m92_json(handler):
    try:
        n = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        n = 0
    if n <= 0 or n > 4096:
        return {}
    try:
        d = json.loads(handler.rfile.read(n).decode("utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _m92_get(handler, p):
    if p == "/api/m92/status":
        return handler._send(200, {"ok": True, "pin": m92_has_pin(), "offen": m92_session_ok(handler), "wait": _m92_wait_left(),
                                   "autolock": int(get_settings().get("m92_autolock") or 0)})
    return handler._send(404, {"ok": False, "error": "not found"})


def _m92_post(handler, p):
    d = _m92_json(handler)
    if p == "/api/m92/unlock":
        ok, err, wait = m92_verify(d.get("pin"))
        if not ok:
            time.sleep(0.4)
            return handler._send(200, {"ok": False, "error": err, "wait": wait})
        return handler._send(200, {"ok": True}, extra=_m92_new_session())
    if p == "/api/m92/setup":
        with M92["lock"]:
            if m92_has_pin():
                return handler._send(200, {"ok": False, "error": "Es ist schon eine PIN festgelegt."})
            try:
                pin = _m92_check_format(d.get("pin"))
            except ValueError as e:
                return handler._send(200, {"ok": False, "error": str(e)})
            if str(d.get("pin2") or "") != pin:
                return handler._send(200, {"ok": False, "error": "Die beiden Eingaben stimmen nicht überein - bitte neu festlegen."})
            _m92_store(pin)
        return handler._send(200, {"ok": True}, extra=_m92_new_session())
    # everything below needs an open session
    if not m92_session_ok(handler):
        return handler._send(401, {"ok": False, "error": "Programm gesperrt", "locked": True}, extra={"X-PA-Locked": "1"})
    if p == "/api/m92/lock":
        m92_lock_all()
        return handler._send(200, {"ok": True}, extra=_M92_CLEAR)
    if p == "/api/m92/change":
        ok, err, wait = m92_verify(d.get("alt"))
        if not ok:
            return handler._send(200, {"ok": False, "error": "Bisherige PIN: " + err, "wait": wait})
        try:
            pin = _m92_check_format(d.get("neu"))
        except ValueError as e:
            return handler._send(200, {"ok": False, "error": str(e)})
        if str(d.get("neu2") or "") != pin:
            return handler._send(200, {"ok": False, "error": "Die neue PIN und die Wiederholung stimmen nicht überein."})
        with M92["lock"]:
            _m92_store(pin)
        return handler._send(200, {"ok": True})
    if p == "/api/m92/settings":
        try:
            mins = max(0, min(240, int(d.get("autolock") or 0)))
        except (TypeError, ValueError):
            mins = 0
        set_setting("m92_autolock", mins)
        if "lan_offen" in d:
            set_setting("m92_lan_offen", bool(d.get("lan_offen")))
        return handler._send(200, {"ok": True, "autolock": mins, "lan_offen": bool(get_settings().get("m92_lan_offen"))})
    return handler._send(404, {"ok": False, "error": "not found"})


def _m92_locked(handler):
    return handler._send(401, {"ok": False, "error": "Programm gesperrt - bitte PIN eingeben.", "locked": True}, extra={"X-PA-Locked": "1"})


# ---------------------------------------------------------------- gate for the main server (m19 Handler)
_M92_ORIG_GET = Handler.do_GET
_M92_ORIG_POST = Handler.do_POST


def _m92_do_GET(self):
    if self._bad_host():
        return self._send(403, b"", "text/plain")
    try:
        p = urlparse(self.path).path
        if p.startswith("/api/m92/"):
            return _m92_get(self, p)
        if m92_session_ok(self):
            return _M92_ORIG_GET(self)
        if p in ("/", "/index.html"):
            # the core started and serves pages -> start counts as successful (otherwise the starter
            # would treat an update as broken while the PIN screen waits; normally done by bootstrap)
            try:
                mark_start_ok()
            except Exception:
                pass
            return self._send(200, _m92_page(), "text/html; charset=utf-8", {"X-Frame-Options": "DENY"})
        if p == "/logo":
            return _M92_ORIG_GET(self)     # only the logo for the lock page
        return _m92_locked(self)
    except Exception as e:
        traceback.print_exc()
        return self._send(500, {"error": str(e)})


def _m92_do_POST(self):
    if self._bad_host() or self._foreign():
        return self._send(403, {"ok": False, "error": "forbidden"})
    try:
        p = urlparse(self.path).path
        if p.startswith("/api/m92/"):
            return _m92_post(self, p)
        if m92_session_ok(self):
            return _M92_ORIG_POST(self)
        return _m92_locked(self)
    except Exception as e:
        traceback.print_exc()
        return self._send(500, {"error": str(e)})


Handler.do_GET = _m92_do_GET
Handler.do_POST = _m92_do_POST


# ---------------------------------------------------------------- gate for LAN servers (handy, abnahme, api/pwa)
M92_LAN_TEXT = "Pfeiffer-Audio Rechnung ist gesperrt - bitte zuerst am PC die PIN eingeben."


def m92_lan_ok():
    if M92_TESTLAUF:
        return True
    if not M92["geoeffnet"]:
        return False
    with M92["lock"]:
        _m92_purge(_m92_idle_sec())        # idle PC session = locked, same as Strg+L / UI autolock
        open_ = bool(M92["tokens"])
    if open_:
        return True
    try:
        return bool(get_settings().get("m92_lan_offen"))
    except Exception:
        return False


def _m92_wrap_lan(cls_name):
    cls = globals().get(cls_name)
    if cls is None:
        return
    for meth in ("do_GET", "do_POST"):
        orig = getattr(cls, meth, None)
        if orig is None or getattr(orig, "_m92", False):
            continue

        def make(orig_, meth_):
            def gated(self):
                if not m92_lan_ok():
                    if meth_ == "do_GET":
                        return self._out(423, "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                                              "<body style='font:18px sans-serif;padding:24px'><h2>Gesperrt</h2>" + M92_LAN_TEXT + "</body>",
                                         "text/html; charset=utf-8")
                    return self._out(423, {"ok": False, "error": M92_LAN_TEXT})
                return orig_(self)
            gated._m92 = True
            return gated
        setattr(cls, meth, make(orig, meth))


for _m92_c in ("HandyHandler", "M77Handler", "M88Handler"):
    _m92_wrap_lan(_m92_c)


# ---------------------------------------------------------------- bootstrap / selftest
def _m92_boot(d):
    r = _m92_row() or {}
    d["m92"] = {"version": M92_VERSION, "autolock": int(get_settings().get("m92_autolock") or 0), "lan_offen": bool(get_settings().get("m92_lan_offen")),
                "gesetzt": r.get("gesetzt") or "", "geaendert": r.get("geaendert") or ""}


HOOK_BOOT.append(_m92_boot)


def _m92_selftest():
    err = []
    try:
        salt = secrets.token_hex(16)
        if _m92_hash("482915", salt, 1000) != _m92_hash("482915", salt, 1000) or _m92_hash("482915", salt, 1000) == _m92_hash("482916", salt, 1000):
            err.append("m92: PIN-Hash fehlerhaft")
        for bad in ("12345", "1234567", "abcdef", "111111", "123456", "654321"):
            try:
                _m92_check_format(bad)
                err.append(f"m92: unzulaessige PIN {bad} angenommen")
            except ValueError:
                pass
        with M92["lock"]:
            M92["tokens"]["_st_m92_idle"] = time.time() - 3600
            _m92_purge(0)
            kept = "_st_m92_idle" in M92["tokens"]
            _m92_purge(600)
            gone = "_st_m92_idle" not in M92["tokens"]
            M92["tokens"].pop("_st_m92_idle", None)
        if not (kept and gone):
            err.append("m92: Leerlauf-Sperre im Server fehlerhaft")
        if Handler.do_GET is not _m92_do_GET or Handler.do_POST is not _m92_do_POST:
            err.append("m92: Sperre nicht im Hauptserver eingehaengt")
        for c in ("HandyHandler", "M77Handler", "M88Handler"):
            cls = globals().get(c)
            if cls is not None and not getattr(cls.do_GET, "_m92", False):
                err.append(f"m92: {c} nicht gesperrt")
    except Exception as e:
        err.append(f"m92 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m92_selftest)
