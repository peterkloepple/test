# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m94_webbank (v2.4.0)
# Bank-Login im Browser ("wie Outbank"): fuer Banken ohne FinTS, z. B. C24 Bank.
#  - Das Programm oeffnet das normale Online-Banking der Bank in einem eigenen
#    Browserfenster (Microsoft Edge oder Google Chrome, eigenes Profil im Datenordner).
#  - DU meldest dich dort ganz normal an (C24: QR-Code mit der C24-App scannen bzw.
#    in der App freigeben). Das Programm sieht weder Passwort noch PIN.
#  - Waehrend du eingeloggt bist, liest das Programm ueber die Chrome-DevTools-
#    Schnittstelle (nur lokal, 127.0.0.1) die Daten mit, die die Bank-Seite selbst
#    laedt (JSON), und erkennt daraus Kontostand und Umsaetze. Notfalls wird der
#    sichtbare Seitentext ausgewertet.
#  - "Uebernehmen": Umsaetze laufen durch dieselbe Pruefung wie beim FinTS-Abruf
#    (Doppelte, sichere Zuordnungen, Rest in den Bank-Abgleich), der Kontostand wird
#    gespeichert, das Fenster schliesst sich.
#  - Rohdaten des letzten Abrufs liegen unter <Datenordner>/Bankzugang/rohdaten
#    (zur Fehlersuche, falls die Bank ihre Seite umbaut).
# Ohne Fremdbibliothek: WebSocket- und DevTools-Client sind hier selbst geschrieben.
# Autor: T. Pfeiffer

import secrets
import queue as queue_mod
import tempfile

M94_VERSION = "1.0.0"
M94_KNOWN = {   # BLZ -> (name, online banking url)
    "50024024": ("C24 Bank", "https://banking.c24.de"),
}
M94_LOGIN_HINT = {
    "50024024": "Im Bank-Fenster anmelden: den angezeigten QR-Code mit der C24-App scannen bzw. die Anmeldung in der C24-App freigeben.",
}
M94_MAX_SEK = 20 * 60        # a browser session lives at most 20 minutes
M94 = {"sess": None, "lock": threading.Lock()}


# ============================================================ settings
def wb_dir(*p):
    d = os.path.join(DATA_DIR, "Bankzugang", *p)
    os.makedirs(d, exist_ok=True)
    return d


def wb_cfg():
    s = get_settings()
    own = None
    try:
        own = m93_bank(s.get("iban") or "")
    except Exception:
        pass
    blz = str(s.get("wb_blz") or (own or {}).get("blz") or "")
    known = M94_KNOWN.get(blz)
    url = str(s.get("wb_url") or (known[1] if known else "")).strip()
    bank = str(s.get("wb_bank") or (known[0] if known else (own or {}).get("name") or "")).strip()
    return {"blz": blz, "bank": bank, "url": url, "auto": s.get("wb_auto", True) is not False,
            "profil_behalten": s.get("wb_profil", True) is not False, "log": s.get("wb_log") or {},
            "hinweis": M94_LOGIN_HINT.get(blz, "Im Fenster ganz normal beim Online-Banking anmelden und die Freigabe bestätigen."),
            "iban": re.sub(r"\s", "", str(s.get("iban") or "")).upper()}


def wb_config_view():
    c = wb_cfg()
    exe = wb_find_browser()
    c.update({"browser": exe or "", "browser_name": _wb_browser_name(exe), "eingerichtet": bool(c["url"]),
              "profil_da": os.path.isdir(os.path.join(DATA_DIR, "Bankzugang", "browser")),
              "bekannt": [{"blz": k, "bank": v[0], "url": v[1]} for k, v in M94_KNOWN.items()]})
    return c


def wb_config_save(d):
    if "url" in d:
        u = str(d.get("url") or "").strip()
        if u and not re.match(r"^https://[\w.-]+", u, re.I) and not re.match(r"^http://(127\.0\.0\.1|localhost)", u, re.I):
            raise ValueError("Die Adresse des Online-Bankings muss mit https:// beginnen.")
        set_setting("wb_url", u)
    for k, sk in (("bank", "wb_bank"), ("blz", "wb_blz")):
        if k in d:
            set_setting(sk, str(d.get(k) or "").strip())
    if "auto" in d:
        set_setting("wb_auto", bool(d["auto"]))
    if "profil_behalten" in d:
        set_setting("wb_profil", bool(d["profil_behalten"]))
    return wb_config_view()


def wb_profil_loeschen():
    s = M94["sess"]
    if s and s.alive():
        raise ValueError("Bitte zuerst das Bank-Fenster schließen.")
    p = os.path.join(DATA_DIR, "Bankzugang", "browser")
    shutil.rmtree(p, ignore_errors=True)
    return {"ok": True}


# ============================================================ browser
def wb_find_browser():
    env = os.environ.get("PA_WB_BROWSER")
    if env and os.path.isfile(env):
        return env
    cands = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
        try:
            import winreg
            for exe in ("msedge.exe", "chrome.exe"):
                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + exe) as k:
                            cands.append(winreg.QueryValue(k, None))
                    except OSError:
                        pass
        except Exception:
            pass
    else:
        for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome"):
            p = shutil.which(n)
            if p:
                cands.append(p)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return ""


def _wb_browser_name(exe):
    e = os.path.basename(exe or "").lower()
    return "Microsoft Edge" if "edge" in e else "Google Chrome" if "chrome" in e else "Chromium" if "chrom" in e else ("Browser" if e else "")


# ============================================================ minimal websocket client (RFC 6455)
class _WbWs:
    def __init__(self, url, timeout=10):
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (("?" + u.query) if u.query else "")
        req = (f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            ch = self.sock.recv(1)
            if not ch:
                raise ConnectionError("WebSocket: Verbindung beendet")
            head += ch
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("WebSocket: " + head.split(b"\r\n", 1)[0].decode("latin-1", "replace"))
        self.sock.settimeout(None)
        self.wlock = threading.Lock()

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            ch = self.sock.recv(n - len(buf))
            if not ch:
                raise ConnectionError("WebSocket geschlossen")
            buf += ch
        return buf

    def send(self, text, opcode=1):
        data = text.encode("utf-8") if isinstance(text, str) else text
        n = len(data)
        hdr = bytes([0x80 | opcode])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mk = os.urandom(4)
        masked = bytes(b ^ mk[i % 4] for i, b in enumerate(data))
        with self.wlock:
            self.sock.sendall(hdr + mk + masked)

    def recv(self):
        parts, op0 = [], None
        while True:
            b1, b2 = self._read(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mk = self._read(4) if b2 & 0x80 else None
            data = self._read(n) if n else b""
            if mk:
                data = bytes(b ^ mk[i % 4] for i, b in enumerate(data))
            if op == 8:
                raise ConnectionError("WebSocket geschlossen")
            if op == 9:
                self.send(data, opcode=10)
                continue
            if op == 10:
                continue
            if op in (1, 2):
                op0, parts = op, [data]
            elif op == 0:
                parts.append(data)
            if fin and op0 is not None:
                return b"".join(parts).decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ============================================================ devtools session
class _WbSess:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = secrets.token_urlsafe(12)
        self.state = "start"          # start | browser | fertig | fehler | abgebrochen
        self.error = ""
        self.lines = []
        self.t0 = time.time()
        self.proc = None
        self.ws = None
        self.mid = 0
        self.waiting = {}             # id -> [event, result]
        self.reqs = {}                # (session, requestId) -> url
        self.jsons = []               # (url, obj)
        self.sessions = set()
        self.lock = threading.Lock()
        self.jobs = queue_mod.Queue()
        self.erkannt = {}
        self.ergebnis = None
        host = (urlparse(cfg["url"]).hostname or "").lower()
        parts = host.split(".")
        self.domain = host if re.fullmatch(r"[\d.]+|localhost", host) else ".".join(parts[-2:])

    def log(self, m):
        self.lines.append(time.strftime("%H:%M:%S ") + m)
        self.lines = self.lines[-80:]

    def alive(self):
        return self.state == "browser" and self.proc is not None and self.proc.poll() is None

    # ---- raw protocol
    def call(self, method, params=None, session=None, timeout=15):
        with self.lock:
            self.mid += 1
            i = self.mid
            ev = threading.Event()
            self.waiting[i] = [ev, None]
        msg = {"id": i, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        if not ev.wait(timeout):
            self.waiting.pop(i, None)
            raise TimeoutError(method)
        r = self.waiting.pop(i, [None, {}])[1] or {}
        if "error" in r:
            raise RuntimeError(f"{method}: {r['error'].get('message')}")
        return r.get("result") or {}

    def _reader(self):
        try:
            while True:
                m = json.loads(self.ws.recv())
                if "id" in m:
                    w = self.waiting.get(m["id"])
                    if w:
                        w[1] = m
                        w[0].set()
                    continue
                self.jobs.put(m)
        except Exception as e:
            if self.state == "browser":
                self.log("Verbindung zum Browser beendet (%s)." % type(e).__name__)
        finally:
            self.jobs.put(None)

    def _worker(self):
        while True:
            m = self.jobs.get()
            if m is None:
                break
            try:
                self._event(m)
            except Exception:
                traceback.print_exc()

    def _event(self, m):
        meth, p, sid = m.get("method"), m.get("params") or {}, m.get("sessionId")
        if meth == "Target.attachedToTarget":
            ti = p.get("targetInfo") or {}
            ns = p.get("sessionId")
            if ti.get("type") in ("page", "iframe"):
                self.sessions.add(ns)
                for meth2, prm in (("Network.enable", {"maxResourceBufferSize": 20000000, "maxTotalBufferSize": 100000000}),
                                   ("Page.enable", {}), ("Runtime.runIfWaitingForDebugger", {})):
                    try:
                        self.call(meth2, prm, session=ns)
                    except Exception:
                        pass
            else:
                try:
                    self.call("Runtime.runIfWaitingForDebugger", {}, session=ns)
                except Exception:
                    pass
        elif meth == "Target.detachedFromTarget":
            self.sessions.discard(p.get("sessionId"))
        elif meth == "Network.responseReceived":
            r = p.get("response") or {}
            url, mime = r.get("url") or "", (r.get("mimeType") or "").lower()
            host = (urlparse(url).hostname or "").lower()
            if (host == self.domain or host.endswith("." + self.domain)) and ("json" in mime or p.get("type") in ("XHR", "Fetch")):
                self.reqs[(sid, p.get("requestId"))] = url
        elif meth == "Network.loadingFinished":
            url = self.reqs.pop((sid, p.get("requestId")), None)
            if url:
                try:
                    b = self.call("Network.getResponseBody", {"requestId": p.get("requestId")}, session=sid, timeout=10)
                    body = b.get("body") or ""
                    if b.get("base64Encoded"):
                        body = base64.b64decode(body).decode("utf-8", "replace")
                    obj = json.loads(body)
                    self.jsons.append((url, obj))
                    self.jsons = self.jsons[-600:]
                    self._update()
                except (ValueError, RuntimeError, TimeoutError):
                    pass
        elif meth == "Page.frameNavigated" and not (p.get("frame") or {}).get("parentId"):
            u = (p.get("frame") or {}).get("url") or ""
            if u.startswith("http"):
                self.log("Seite: " + re.sub(r"[?#].*", "", u)[:90])

    def _update(self):
        try:
            self.erkannt = wb_extract(self.jsons, self.cfg["iban"])
        except Exception:
            traceback.print_exc()

    # ---- lifecycle
    def start(self):
        exe = wb_find_browser()
        if not exe:
            raise ValueError("Kein Microsoft Edge oder Google Chrome gefunden – einer davon wird für das Bank-Fenster gebraucht.")
        prof = wb_dir("browser") if self.cfg["profil_behalten"] else tempfile.mkdtemp(prefix="pa_bank_")
        self.profile_tmp = None if self.cfg["profil_behalten"] else prof
        s_ = socket.socket()
        s_.bind(("127.0.0.1", 0))
        port = s_.getsockname()[1]
        s_.close()
        args = [exe, f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1", f"--user-data-dir={prof}",
                "--no-first-run", "--no-default-browser-check", "--disable-features=Translate,msEdgeTranslate",
                "--window-size=1180,900", f"--app={self.cfg['url']}"]
        if not sys.platform.startswith("win") and os.environ.get("PA_WB_HEADLESS"):
            args.insert(1, "--headless=new")
        args[1:1] = [a_ for a_ in (os.environ.get("PA_WB_ARGS") or "").split() if a_]   # extra switches (tests / special setups)
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform.startswith("win"):
            kw["creationflags"] = 0x08000000      # CREATE_NO_WINDOW (console only)
        self.proc = subprocess.Popen(args, **kw)
        self.log(f"{_wb_browser_name(exe)} gestartet: {self.cfg['url']}")
        ver = None
        for _ in range(100):
            if self.proc.poll() is not None:
                raise ValueError("Der Browser hat sich sofort wieder beendet. Ist das Bank-Fenster schon offen? Sonst Programm neu starten.")
            try:
                import urllib.request
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                    ver = json.loads(r.read().decode())
                break
            except Exception:
                time.sleep(0.15)
        if not ver:
            raise ValueError("Keine Verbindung zum Browser (DevTools).")
        self.ws = _WbWs(ver["webSocketDebuggerUrl"])
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()
        self.state = "browser"
        self.call("Target.setDiscoverTargets", {"discover": True})
        self.call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})
        # page created before auto-attach: attach explicitly
        try:
            for t in self.call("Target.getTargets").get("targetInfos") or []:
                if t.get("type") == "page" and not t.get("attached"):
                    self.call("Target.attachToTarget", {"targetId": t["targetId"], "flatten": True})
        except Exception:
            pass
        self.log("Warte auf deine Anmeldung im Bank-Fenster …")
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        while self.state == "browser":
            if self.proc.poll() is not None:
                if self.state == "browser":
                    self.state = "abgebrochen" if not self.ergebnis else self.state
                    self.error = "Bank-Fenster wurde geschlossen."
                    self.log(self.error)
                break
            if time.time() - self.t0 > M94_MAX_SEK:
                self.log("Zeit abgelaufen (20 Minuten) – Fenster wird geschlossen.")
                self.state = "abgebrochen"
                self.error = "Zeit abgelaufen."
                self.close()
                break
            time.sleep(1)

    def page_texts(self):
        out = []
        for sid in list(self.sessions):
            try:
                r = self.call("Runtime.evaluate", {"expression": "document.body ? document.body.innerText : ''", "returnByValue": True},
                              session=sid, timeout=5)
                t = ((r.get("result") or {}).get("value") or "")
                if t:
                    out.append(t)
            except Exception:
                pass
        return out

    def close(self):
        try:
            if self.ws:
                self.call("Browser.close", timeout=3)
        except Exception:
            pass
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.wait(5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        if getattr(self, "profile_tmp", None):
            shutil.rmtree(self.profile_tmp, ignore_errors=True)

    def view(self):
        e = self.erkannt or {}
        tx = e.get("tx") or []
        return {"ok": True, "token": self.token, "state": self.state, "error": self.error, "log": self.lines[-12:],
                "pakete": len(self.jsons), "bank": self.cfg["bank"], "hinweis": self.cfg["hinweis"],
                "erkannt": {"saldo": e.get("saldo"), "konto": e.get("konto") or "", "umsaetze": len(tx),
                            "von": min((t["datum"] for t in tx), default=""), "bis": max((t["datum"] for t in tx), default=""),
                            "quelle": e.get("quelle") or ""},
                "ergebnis": self.ergebnis, "sekunden": int(time.time() - self.t0)}


# ============================================================ data recognition (pure functions, testable)
_WB_AMT = re.compile(r"(amount|betrag|value|sum|volume|summe)", re.I)
_WB_DATE = re.compile(r"(bookingdate|booking_date|valuedate|value_date|valuta|buchungsdatum|bookedat|booked_at|date|datum|executedat|createdat|created_at|timestamp|time)", re.I)
_WB_TEXT = re.compile(r"(purpose|remittance|reference|verwendung|description|subject|memo|information|title|text|bookingtext|details)", re.I)
_WB_NAME = re.compile(r"(counterparty|counter_party|creditor|debtor|partner|recipient|sender|merchant|payee|payer|empfaenger|auftraggeber|name)", re.I)
_WB_DIR = re.compile(r"^(creditdebit\w*|credit_debit\w*|direction|indicator|type|kind|transactiontype|transaction_type|bookingtype|booking_type|umsatzart)$", re.I)
_WB_BAL = re.compile(r"(balance|saldo|kontostand)", re.I)
_WB_IBAN = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b")
_WB_NEG = re.compile(r"^(debit|dbit|dbt|d|outgoing|out|outbound|ausgang|belastung|lastschrift|withdrawal|payment_out|sent|expense|charge|card_payment)$", re.I)


def wb_num(v, key=""):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f / 100 if re.search(r"cent|minor", key, re.I) else f
    if isinstance(v, str):
        s = v.strip().replace("−", "-").replace("€", "").replace("EUR", "").replace("\xa0", "").replace(" ", "")
        if not re.fullmatch(r"[+-]?\d[\d.,]*", s):
            return None
        if re.search(r",\d{1,2}$", s):
            s = s.replace(".", "").replace(",", ".")
        elif re.search(r"\.\d{1,2}$", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", "").replace(".", "")
        try:
            f = float(s)
        except ValueError:
            return None
        return f / 100 if re.search(r"cent|minor", key, re.I) else f
    if isinstance(v, dict):
        for k2, v2 in v.items():
            if re.fullmatch(r"(value|amount|betrag|sum|centamount|amountincents|valueincents|cents|minorunits|units)", k2, re.I):
                n = wb_num(v2, k2)
                if n is not None:
                    if re.search(r"negative|sign", json.dumps(v)[:200], re.I) and v.get("negative") is True:
                        n = -abs(n)
                    return n
    return None


def wb_date(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        t = float(v)
        if t > 1e11:
            t /= 1000
        if 9e8 < t < 4e9:
            return datetime.datetime.fromtimestamp(t).date().isoformat()
        return ""
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    if isinstance(v, dict):
        for k2, v2 in v.items():
            if _WB_DATE.search(k2) or k2.lower() in ("value", "iso"):
                d = wb_date(v2)
                if d:
                    return d
    return ""


def _wb_str(v, depth=0):
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list) and depth < 2:
        return " ".join(x_ for x_ in (_wb_str(i, depth + 1) for i in v) if x_)
    if isinstance(v, dict) and depth < 2:
        for k2 in ("name", "displayName", "fullName", "value", "text", "unstructured", "line"):
            if isinstance(v.get(k2), str):
                return v[k2].strip()
    return ""


def _wb_tx(d):
    """dict -> transaction dict or None"""
    if not isinstance(d, dict) or len(d) < 2:
        return None
    amt, amt_key, dat, zweck, name, iban, neg = None, "", "", "", "", "", False
    ranked_dates = []
    for k, v in d.items():
        kl = k.lower()
        if amt is None and _WB_AMT.search(kl) and not _WB_BAL.search(kl) and not _WB_DATE.search(kl) and not re.search(r"fee|limit|max|min|count|total", kl):
            n = wb_num(v, k)
            if n is not None:
                amt, amt_key = n, k
        if _WB_DATE.search(kl) and not re.search(r"update|modified|expir|valid", kl):
            dd = wb_date(v)
            if dd:
                pr = 0 if re.search(r"booking|buchung|booked", kl) else 1 if re.search(r"value|valuta", kl) else 2
                ranked_dates.append((pr, dd))
        if _WB_TEXT.search(kl) and not zweck:
            zweck = _wb_str(v)
        if _WB_NAME.search(kl) and not name and not re.search(r"bank|account_?name|file|user", kl):
            if isinstance(v, dict):
                name = _wb_str(v)
                for k3, v3 in v.items():
                    if "iban" in k3.lower() and isinstance(v3, str):
                        iban = v3.replace(" ", "").upper()
            else:
                name = _wb_str(v)
        if "iban" in kl and isinstance(v, str) and not iban and re.search(r"counter|partner|creditor|debtor|other|remote|recipient|sender", kl):
            iban = v.replace(" ", "").upper()
        if _WB_DIR.search(kl) and isinstance(v, str) and _WB_NEG.match(v.strip()):
            neg = True
        if re.fullmatch(r"(isincoming|incoming|iscredit|credit)", kl) and v is False:
            neg = True
        if re.fullmatch(r"(isoutgoing|outgoing|isdebit|debit)", kl) and v is True:
            neg = True
    if ranked_dates:
        dat = sorted(ranked_dates)[0][1]
    if amt is None or not dat or not (zweck or name):
        return None
    if neg and amt > 0:
        amt = -amt
    return {"datum": dat, "betrag": round(amt, 2), "name": name[:120], "zweck": re.sub(r"\s+", " ", zweck)[:400], "iban": iban,
            "_id": str(d.get("id") or d.get("transactionId") or d.get("uuid") or d.get("transaction_id") or "")}


def _wb_walk(o, fn, depth=0, ctx=None):
    if depth > 14:
        return
    if isinstance(o, dict):
        fn(o, ctx)
        for v in o.values():
            _wb_walk(v, fn, depth + 1, o)
    elif isinstance(o, list):
        for v in o[:5000]:
            _wb_walk(v, fn, depth + 1, ctx)


def _wb_bal_val(v, key="", depth=0):
    """balance value: number/string/amount dict, or nested {booked:{amount}, available:{...}} (booked/current first)"""
    n = wb_num(v, key)
    if n is not None or not isinstance(v, (dict, list)) or depth > 3:
        return n
    items = v.items() if isinstance(v, dict) else [(key, x_) for x_ in v]
    rank = lambda k: 0 if re.search(r"booked|current|actual|closing|balance|saldo|amount|value", str(k), re.I) and not re.search(r"available|verf", str(k), re.I) \
        else 2 if re.search(r"available|verf|limit|credit", str(k), re.I) else 1
    for k2, v2 in sorted(items, key=lambda kv: rank(kv[0])):
        if isinstance(v2, (dict, list, str, int, float)) and not isinstance(v2, bool):
            if isinstance(v2, str) and not re.search(r"\d", v2):
                continue
            if re.search(r"date|time|currency|type|id$", str(k2), re.I):
                continue
            n = _wb_bal_val(v2, str(k2), depth + 1)
            if n is not None:
                return n
    return None


def wb_extract(jsons, own_iban=""):
    """jsons: list of (url, obj) -> {saldo:{saldo,datum}|None, konto, tx:[...], quelle}"""
    txs, seen, bals, ibans = [], set(), [], []

    def visit(d, parent):
        t = _wb_tx(d)
        if t:
            k = t["_id"] or (t["datum"], t["betrag"], t["name"], t["zweck"])
            if k not in seen:
                seen.add(k)
                txs.append(t)
            return
        for k, v in d.items():
            kl = k.lower()
            if isinstance(v, str) and "iban" in kl:
                ibans.append(v.replace(" ", "").upper())
            if _WB_BAL.search(kl) and not re.search(r"limit|overdraft|dispo|credit_?line|pocket|goal|savings", kl):
                n = _wb_bal_val(v, k)
                if n is not None:
                    pr = 0 if re.search(r"booked|current|actual|account_?balance|^balance$|^saldo$|kontostand", kl) else \
                        2 if re.search(r"available|verfueg|verfüg", kl) else 1
                    own = own_iban and own_iban in json.dumps(d)[:4000].replace(" ", "").upper()
                    bals.append((0 if own else 1, pr, n, wb_date(d.get("date") or d.get("balanceDate") or d.get("referenceDate") or "") or today()))

    for url, obj in jsons:
        _wb_walk(obj, visit)
    saldo = None
    if bals:
        b = sorted(bals, key=lambda x_: (x_[0], x_[1]))[0]
        saldo = {"saldo": round(b[2], 2), "datum": b[3]}
    konto = own_iban if own_iban and own_iban in ibans else (ibans[0] if ibans else "")
    for t in txs:
        t.pop("_id", None)
    txs.sort(key=lambda t: t["datum"])
    return {"saldo": saldo, "konto": konto, "tx": txs, "quelle": "json" if (txs or saldo) else ""}


_WB_MON = {m: i + 1 for i, m in enumerate(["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"])}
_WB_AMT_TXT = re.compile(r"([+\-−]?\s?\d{1,3}(?:\.\d{3})*,\d{2})\s?€")


def wb_extract_text(texts):
    """Fallback: visible page text -> saldo + simple transaction list (date headers + amount lines)."""
    saldo, txs = None, []
    for t in texts:
        m = re.search(r"(Kontostand|Saldo|Verfügbar|Guthaben)[^\d−+\-]{0,60}([+\-−]?\s?\d{1,3}(?:\.\d{3})*,\d{2})\s?€", t, re.I)
        if m and saldo is None:
            saldo = {"saldo": wb_num(m.group(2)), "datum": today()}
        cur, prev = "", ""
        tdy = datetime.date.today()
        for line in [l.strip() for l in t.splitlines() if l.strip()]:
            low = line.lower()
            d = ""
            if low in ("heute", "today"):
                d = tdy.isoformat()
            elif low in ("gestern", "yesterday"):
                d = (tdy - datetime.timedelta(days=1)).isoformat()
            else:
                m2 = re.match(r"^(?:\w+,\s*)?(\d{1,2})\.\s*([a-zäöü]+)\s*(\d{4})?$", low)
                if m2 and m2.group(2) in _WB_MON:
                    y = int(m2.group(3) or tdy.year)
                    d = f"{y}-{_WB_MON[m2.group(2)]:02d}-{int(m2.group(1)):02d}"
                else:
                    d = wb_date(line) if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", line) else ""
            if d:
                cur = d
                continue
            m3 = _WB_AMT_TXT.fullmatch(line)
            if m3 and cur and prev and not re.search(r"kontostand|saldo|verfügbar|guthaben", prev, re.I):
                txs.append({"datum": cur, "betrag": wb_num(m3.group(1)), "name": prev[:120], "zweck": "", "iban": ""})
                prev = ""
                continue
            prev = line
    return {"saldo": saldo, "konto": "", "tx": txs, "quelle": "seitentext" if (txs or saldo) else ""}


# ============================================================ actions
def wb_start(d=None):
    with M94["lock"]:
        s = M94["sess"]
        # v2.6.3: also while the browser is still starting (double click opened a second, orphaned browser)
        if s and (s.alive() or (s.state == "start" and time.time() - s.t0 < 120)):
            return s.view()
        cfg = wb_cfg()
        if not cfg["url"]:
            raise ValueError("Für deine Bank ist noch keine Online-Banking-Adresse eingetragen (Einstellungen → Bankabruf).")
        s = _WbSess(cfg)
        M94["sess"] = s
    try:
        s.start()
    except Exception as e:
        s.state, s.error = "fehler", str(e)
        s.log("Fehler: " + str(e))
        s.close()
    return s.view()


def _wb_get(token):
    s = M94["sess"]
    if not s or (token and token != s.token):
        raise ValueError("Kein Bank-Fenster offen.")
    return s


def wb_status(token):
    return _wb_get(token).view()


_WB_SECRET_KEY = re.compile(r"token|auth|session|cookie|secret|passw|bearer|jwt|csrf|xsrf|credential|signature|nonce|apikey|api_key"
                            r"|^pin$|^tan$|otp$|^code$|^key$", re.I)


def wb_scrub(o, depth=0):
    """raw data for the debug file without login data: values of auth/token/session/cookie... keys are replaced"""
    if depth > 30:
        return None
    if isinstance(o, dict):
        return {k: ("***" if _WB_SECRET_KEY.search(str(k)) and o[k] not in (None, "", [], {}) else wb_scrub(o[k], depth + 1)) for k in o}
    if isinstance(o, list):
        return [wb_scrub(v, depth + 1) for v in o]
    if isinstance(o, str) and re.fullmatch(r"(?i)bearer\s+\S+|eyJ[\w-]+\.[\w-]+\.[\w-]+", o.strip()):
        return "***"                      # bearer header / JWT as a plain value
    return o


def _wb_url_plain(u):
    return re.sub(r"[?#].*", "", str(u or ""))      # query strings may carry tokens


def _wb_save_raw(s, texts):
    try:
        d = wb_dir("rohdaten")
        fn = os.path.join(d, time.strftime("%Y-%m-%d_%H%M%S_") + re.sub(r"\W+", "_", s.cfg["bank"] or "bank") + ".json")
        with open(fn, "w", encoding="utf-8") as f:
            json.dump({"bank": s.cfg["bank"], "url": _wb_url_plain(s.cfg["url"]), "zeit": now_iso(),
                       "json": [{"url": _wb_url_plain(u), "daten": wb_scrub(o)} for u, o in s.jsons],
                       "seitentext": texts}, f, ensure_ascii=False, indent=1, default=str)
        files = sorted(os.listdir(d))
        for old in files[:-5]:
            try:
                os.remove(os.path.join(d, old))
            except OSError:
                pass
        return fn
    except Exception:
        traceback.print_exc()
        return ""


def wb_uebernehmen(token):
    s = _wb_get(token)
    if s.state != "browser":
        raise ValueError("Das Bank-Fenster ist nicht mehr offen.")
    texts = s.page_texts()
    e = wb_extract(s.jsons, s.cfg["iban"])
    quelle_txt = "Bank-Login (" + (s.cfg["bank"] or "Bank") + ")"
    auto = s.cfg["auto"]
    if not e["tx"] and not e["saldo"]:
        e = wb_extract_text(texts)
        auto = False                  # text recognition: never book automatically
    raw_file = _wb_save_raw(s, texts)
    if not e["tx"] and not e["saldo"]:
        s.log("Noch nichts erkannt.")
        return dict(s.view(), ok=False, error="Noch keine Umsätze oder Kontostand erkannt. Bist du eingeloggt? Öffne im Bank-Fenster die Umsätze "
                                              "(ggf. nach unten scrollen) und klick dann noch einmal auf „Übernehmen“.")
    res = fints_import(e["tx"], e["saldo"], e["konto"], auto=auto, quelle=quelle_txt)
    res.update({"ok": True, "zeit": now_iso(), "von": min((t["datum"] for t in e["tx"]), default=""),
                "bis": max((t["datum"] for t in e["tx"]), default=""), "konto": e["konto"], "erkennung": e["quelle"], "rohdaten": raw_file,
                "bank": s.cfg["bank"]})
    set_setting("wb_log", res)
    s.ergebnis = res
    s.state = "fertig"
    s.log(f"{res['abgerufen']} Umsätze übernommen, {res['neu']} neu." + (f" Kontostand {res['saldo']['saldo'] if isinstance(res.get('saldo'), dict) else ''}" if res.get("saldo") else ""))
    threading.Thread(target=s.close, daemon=True).start()
    return s.view()


def wb_abbrechen(token):
    s = _wb_get(token)
    if s.state == "browser":
        s.state, s.error = "abgebrochen", "Abgebrochen."
    threading.Thread(target=s.close, daemon=True).start()
    return s.view()


# ============================================================ routes / hooks
def _wb_r(fn):
    def h(handler, d):
        try:
            return handler._send(200, fn(d))
        except ValueError as e:
            return handler._send(200, {"ok": False, "error": str(e)})
    return h


HOOK_GET["/api/wb/config"] = lambda h, qs: h._send(200, wb_config_view())
HOOK_GET["/api/wb/status"] = lambda h, qs: _wb_r(lambda d: wb_status(qs.get("token") or ""))(h, {})
HOOK_POST["/api/wb/config/save"] = _wb_r(wb_config_save)
HOOK_POST["/api/wb/start"] = _wb_r(wb_start)
HOOK_POST["/api/wb/uebernehmen"] = _wb_r(lambda d: wb_uebernehmen(d.get("token") or ""))
HOOK_POST["/api/wb/abbrechen"] = _wb_r(lambda d: wb_abbrechen(d.get("token") or ""))
HOOK_POST["/api/wb/profil_loeschen"] = _wb_r(lambda d: wb_profil_loeschen())


def _wb_boot(d):
    c = wb_cfg()
    lg = c["log"] or {}
    d["wb"] = {"eingerichtet": bool(c["url"]), "bank": c["bank"], "url": c["url"], "letzter": lg.get("zeit", ""), "version": M94_VERSION}


HOOK_BOOT.append(_wb_boot)


def _wb_selftest():
    err = []
    try:
        sample = [("https://banking.c24.de/api/x", {"accounts": [{"iban": "DE00500240240000000000", "balance": {"value": "1.234,56", "currency": "EUR"}}],
                   "transactions": [{"id": "a1", "bookingDate": "2026-10-20", "amount": {"value": -49.9, "currency": "EUR"},
                                     "counterparty": {"name": "Telekom", "iban": "DE11111111111111111111"}, "purpose": "Rechnung 10/2026"},
                                    {"id": "a2", "bookingDate": "2026-10-21", "amount": "250,00", "creditDebitIndicator": "CREDIT",
                                     "counterpartyName": "Muster GmbH", "remittanceInformation": "RE-2026-0042"},
                                    {"id": "a3", "valueDate": 1761264000000, "amountInCents": 1999, "direction": "OUTGOING",
                                     "merchant": {"name": "Amazon"}, "description": "Bestellung"}]})]
        e = wb_extract(sample, "DE00500240240000000000")
        if not e["saldo"] or abs(e["saldo"]["saldo"] - 1234.56) > 0.001:
            err.append(f"m94: Kontostand nicht erkannt ({e['saldo']})")
        b = {t["name"]: t["betrag"] for t in e["tx"]}
        if b.get("Telekom") != -49.9 or b.get("Muster GmbH") != 250.0 or b.get("Amazon") != -19.99:
            err.append(f"m94: Umsätze falsch erkannt ({b})")
        tt = wb_extract_text(["Kontostand\n1.234,56 €\n27. Oktober 2026\nREWE\n-12,34 €\nGestern\nGehalt\n2.000,00 €"])
        if not tt["saldo"] or len(tt["tx"]) != 2:
            err.append("m94: Seitentext-Erkennung fehlerhaft")
        sc = wb_scrub({"accessToken": "abc", "data": [{"sessionId": "x", "amount": 5, "auth": {"pin": "1"}}], "h": "Bearer xyz.abc"})
        if json.dumps(sc).count("***") != 4 or sc["data"][0]["amount"] != 5:
            err.append(f"m94: Rohdaten nicht bereinigt ({sc})")
        if wb_num("−1.234,50 €") != -1234.5 or wb_num("12.5") != 12.5 or wb_num(1999, "amountInCents") != 19.99:
            err.append("m94: Zahlenerkennung fehlerhaft")
    except Exception as ex:
        err.append(f"m94 Ausnahme: {type(ex).__name__}: {ex}")
    return err


HOOK_SELFTEST.append(_wb_selftest)
