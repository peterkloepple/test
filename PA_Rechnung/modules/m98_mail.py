# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m98_mail  v3.1.0
# Mail-Konten - ab v3.1.0 in EINER Datei zusammengefasst aus:
#   m98_gmail_login         Gmail mit 2-Faktor-Anmeldung (App-Passwort per Browser-Login)
#   m99_mail_privat         privates Postfach (getrennt, nicht ausgewertet)
#   m99b_rechnungsabsender  Rechnungsuebernahme nur fuer freigegebene Absender
#   m99c_outlook            Versand/Abruf ueber Microsoft Outlook
# Reihenfolge der Teile = bisherige Lade-Reihenfolge (Verhalten unveraendert).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer


# ============================================================================
# Teil aus m98_gmail_login.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m98_gmail_login (v2.5.0)
# v2.5.0: Die Adresse steht im Google-Fenster schon drin (Anmelde-Link mit Adresse + automatisches Ausfuellen).
# Gmail mit 2-Faktor-Anmeldung: Login im Browser - wie beim Bank-Login (m94).
# Problem: Mit eingeschalteter 2-Schritt-Bestaetigung nimmt Gmail fuer IMAP/SMTP weder das
# normale Google-Passwort noch einen Code - nur ein App-Passwort (16 Buchstaben).
# Ablauf jetzt:
#  1. Knopf "Mit Google anmelden" -> das Programm oeffnet die Google-Seite "App-Passwoerter"
#     in einem eigenen Browserfenster (Edge/Chrome, frisches Profil, nichts bleibt gespeichert).
#  2. DU meldest dich dort ganz normal an: Passwort + 2. Faktor (Handy bestaetigen / Code).
#     Das Programm sieht weder Google-Passwort noch Code.
#  3. Auf der Seite traegt das Programm den Namen "PA Rechnung" ein und klickt "Erstellen".
#  4. Google zeigt das neue App-Passwort - das Programm liest es ab, prueft es sofort am
#     Gmail-Postfach (IMAP), speichert es verschluesselt fuer Abruf UND Versand und schliesst das Fenster.
#  5. Danach werden die Mails abgerufen und gespeichert (Datenordner\E-Mails + Liste "E-Mails"),
#     ab dann automatisch alle 15 Minuten.
# Notweg: Laesst Google die Anmeldung im Fenster nicht zu, kann ein App-Passwort, das du im
# eigenen Browser erzeugt hast, im selben Dialog eingefuegt werden - gleiche Pruefung/Speicherung.
# v2.4.4: Ziele - das gleiche Login richtet auch das private Postfach (m99) ein; jedes Ziel hat eigene
# Adressen-, Speicher- und Abruf-Funktion (M98_ZIELE). Geschaeft und Privat bleiben getrennt.
# Autor: T. Pfeiffer

M98_VERSION = "1.2.0"
M98_URL = os.environ.get("PA_GM_URL") or "https://myaccount.google.com/apppasswords"   # env only for tests
M98_APPNAME = "PA Rechnung"
M98_MAX_VERSUCHE = 8            # IMAP login attempts per session (Google blocks after many failures)
M98 = {"sess": None, "lock": threading.Lock()}
M98_GMAIL_IMAP = ("imap.gmail.com", 993)
M98_GMAIL_SMTP = ("smtp.gmail.com", 587, "starttls")

M98_JS_SCAN = r"""(() => {
  const o = {c: [], m: [], u: location.href, na: false};
  const t = document.body ? document.body.innerText : "";
  o.t = /apppasswords/.test(location.href) ? t.slice(0, 20000) : "";
  if (/apppasswords/.test(location.href)) {
    document.querySelectorAll("span,div,strong,b,code,p,pre,h1,h2,h3,input").forEach(e => {
      const v = ((e.tagName === "INPUT" ? e.value : e.textContent) || "").replace(/\s/g, "");
      if (/^[a-z]{16}$/.test(v)) o.c.push(v);
    });
  }
  let al = ""; document.querySelectorAll("[aria-label],[data-email]").forEach(e => { al += " " + (e.getAttribute("aria-label") || "") + " " + (e.getAttribute("data-email") || ""); });
  const em = (t + al).match(/[A-Za-z0-9._%+-]+@(gmail|googlemail)\.com/g); if (em) o.m = [...new Set(em)].slice(0, 6);
  o.na = /nicht verfügbar|is not available for your account|not available for your account/i.test(t);
  return o;
})()"""

# v2.5.0: Google sign-in page - your address is entered automatically and "Weiter" is clicked (once)
M98_JS_ADRESSE = r"""(() => {
  const inp = document.querySelector("input#identifierId, input[type=email][name=identifier], input[type=email][autocomplete=username], input[type=email]");
  if (!inp || inp.offsetParent === null) return "kein feld";
  if (!inp.value) {
    inp.focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(inp, "%ADR%");
    inp.dispatchEvent(new Event("input", {bubbles: true}));
    inp.dispatchEvent(new Event("change", {bubbles: true}));
  }
  const next = document.querySelector("#identifierNext button") || document.querySelector("#identifierNext") ||
    [...document.querySelectorAll("button,[role=button]")].find(b => b.offsetParent !== null && /^(weiter|next)$/i.test((b.innerText || "").trim()));
  if (next) setTimeout(() => next.click(), 400);
  return "ok";
})()"""


def gm_login_url(adresse):
    """Google sign-in that already carries your address and then goes on to the app password page"""
    if os.environ.get("PA_GM_URL"):
        return M98_URL                                     # tests
    from urllib.parse import quote
    cont = quote(M98_URL, safe="")
    if not adresse:
        return M98_URL
    return (f"https://accounts.google.com/ServiceLogin?service=accountsettings&Email={quote(adresse, safe='')}"
            f"&login_hint={quote(adresse, safe='')}&continue={cont}&followup={cont}")


M98_JS_FILL = r"""(() => {
  if (!/myaccount\.google\.com\/.*apppasswords/.test(location.href)) return "seite";
  const vis = e => e && e.offsetParent !== null && !e.disabled;
  const inp = [...document.querySelectorAll("input[type=text],input:not([type])")].find(vis);
  if (!inp) return "kein feld";
  if (!inp.value) {
    inp.focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(inp, "%NAME%");
    inp.dispatchEvent(new Event("input", {bubbles: true}));
    inp.dispatchEvent(new Event("change", {bubbles: true}));
  }
  const btn = [...document.querySelectorAll("button,[role=button]")].find(b => vis(b) && /^(erstellen|create)$/i.test((b.innerText || "").trim()));
  if (!btn) return "kein knopf";
  setTimeout(() => btn.click(), 600);
  return "ok";
})()""".replace("%NAME%", M98_APPNAME)


# ============================================================ pure helpers (testable)
def gm_is_gmail(addr):
    a = str(addr or "").strip().lower()
    return a.endswith("@gmail.com") or a.endswith("@googlemail.com")


def gm_candidates(texts, elems=()):
    """app password candidates from page text ("abcd efgh ijkl mnop") and single elements (16 letters)"""
    out = []
    for e in elems or ():
        e = re.sub(r"\s", "", str(e or ""))
        if re.fullmatch(r"[a-z]{16}", e) and e not in out:
            out.append(e)
    for t in texts or ():
        for m in re.finditer(r"(?<![A-Za-zÀ-ſ])([a-z]{4})[  ]([a-z]{4})[  ]([a-z]{4})[  ]([a-z]{4})(?![A-Za-zÀ-ſ])", str(t or "")):
            v = "".join(m.groups())
            if v not in out:
                out.append(v)
    return out


def gm_addresses(page_mails=()):
    """gmail addresses to try: settings first, then the ones shown on the Google page"""
    s = get_settings()
    out = []
    for a in (s.get("mi_user"), s.get("smtp_user"), s.get("smtp_from_addr"), s.get("m98_adresse"), *(page_mails or ())):   # v2.5.0: m98_adresse = einmal abgefragt
        a = str(a or "").strip().lower()
        if a and "@" not in a and "gmail" in str(s.get("mi_host") or s.get("smtp_host") or ""):
            a += "@gmail.com"
        if gm_is_gmail(a) and a not in out:
            out.append(a)
    return out


def gm_check(user, pw, timeout=20):
    """True = Gmail accepts this app password (IMAP login), False = rejected; network errors raise ValueError"""
    pw = re.sub(r"\s", "", str(pw or ""))
    try:
        M = imaplib.IMAP4_SSL(M98_GMAIL_IMAP[0], M98_GMAIL_IMAP[1], timeout=timeout)
    except Exception as e:
        raise ValueError(f"Keine Verbindung zu Gmail ({M98_GMAIL_IMAP[0]}): {e}")
    try:
        M.login(user, pw)
        return True
    except imaplib.IMAP4.error:
        return False
    finally:
        try:
            M.logout()
        except Exception:
            pass


def gm_save(user, pw):
    """store the working app password for fetching AND sending, switch on automatic fetching"""
    s = get_settings()
    pw = re.sub(r"\s", "", str(pw or ""))
    set_setting("mi_host", M98_GMAIL_IMAP[0])
    set_setting("mi_port", M98_GMAIL_IMAP[1])
    set_setting("mi_ssl", True)
    set_setting("mi_user", user)
    set_setting("mi_auth", "pass")
    set_setting("mi_pass", protect_secret(pw))
    first = not s.get("m98_eingerichtet")
    if first:
        set_setting("mi_unseen", False)          # save ALL mails (last 60 days at first, then every new one), not only unread
        if not s.get("mi_after"):
            set_setting("mi_after", "nichts")    # Gmail stays untouched
    if int(float(s.get("mi_interval") or 0)) <= 0:
        set_setting("mi_interval", 15)
    smtp_user = str(s.get("smtp_user") or "").strip().lower()
    versand = False
    if not smtp_user or smtp_user == user:
        set_setting("smtp_host", M98_GMAIL_SMTP[0])
        set_setting("smtp_port", M98_GMAIL_SMTP[1])
        set_setting("smtp_sec", M98_GMAIL_SMTP[2])
        set_setting("smtp_user", user)
        set_setting("smtp_auth", "pass")
        set_setting("smtp_pass", protect_secret(pw))
        if not str(s.get("smtp_from_addr") or "").strip():
            set_setting("smtp_from_addr", user)
        versand = True
    set_setting("m98_eingerichtet", {"zeit": now_iso(), "adresse": user, "versand": versand})
    return versand


# ============================================================ browser session (built on the bank login m94)
M98_ZIELE = {}      # ziel -> {"adressen": fn(page_mails), "save": fn(user, pw) -> versand, "fetch": fn() -> dict, "name": str}


def _gm_ziel(z):
    z = str(z or "geschaeft")
    if z not in M98_ZIELE:
        raise ValueError("Unbekanntes Postfach.")
    return M98_ZIELE[z]


class _GmSess(_WbSess):
    def __init__(self, ziel="geschaeft"):
        self.ziel = ziel
        try:
            adr = (_gm_ziel(ziel)["adressen"](()) or [""])[0]
        except Exception:
            adr = ""
        self.vorgabe = adr
        hin = ("Im Google-Fenster anmelden: " + (f"Adresse {adr} ist schon eingetragen – " if adr else "E-Mail, ")
               + "Passwort und dann die 2-Schritt-Bestätigung (Handy bestätigen oder Code eingeben).")
        super().__init__({"url": gm_login_url(adr), "profil_behalten": False, "iban": "", "bank": "Google", "hinweis": hin})
        self.adr_gefuellt = set()
        self.phase = "start"           # start | login | erzeugen | pruefen | abruf | fertig
        self.tried = set()
        self.versuche = 0
        self.adresse = ""
        self.mails = []
        self.filled = {}
        self.abruf = None
        self.versand = False
        self.hinweis2 = ""

    def _update(self):                 # no bank data recognition
        pass

    def start(self):
        super().start()
        if self.lines and "Bank" in self.lines[-1]:
            self.lines[-1] = time.strftime("%H:%M:%S ") + "Warte auf deine Anmeldung bei Google …"
        self.phase = "login"

    def _scan(self):
        texts, elems, mails, url, na = [], [], [], "", False
        for sid in list(self.sessions):
            try:
                r = self.call("Runtime.evaluate", {"expression": M98_JS_SCAN, "returnByValue": True}, session=sid, timeout=5)
                v = (r.get("result") or {}).get("value") or {}
            except Exception:
                continue
            if v.get("t"):
                texts.append(v["t"])
            elems += v.get("c") or []
            mails += v.get("m") or []
            na = na or bool(v.get("na"))
            if self.vorgabe and "accounts.google." in (v.get("u") or "") and sid not in self.adr_gefuellt:
                try:
                    rr = self.call("Runtime.evaluate", {"expression": M98_JS_ADRESSE.replace("%ADR%", self.vorgabe.replace('"', "")),
                                                        "returnByValue": True}, session=sid, timeout=5)
                    if ((rr.get("result") or {}).get("value")) == "ok":
                        self.adr_gefuellt.add(sid)
                        self.log(f"Adresse {self.vorgabe} eingetragen – jetzt Passwort und Bestätigung.")
                except Exception:
                    pass
            if "apppasswords" in (v.get("u") or ""):
                url = v["u"]
                if self.filled.get(sid, 0) < 1 and time.time() - self.filled.get(sid + "_t", 0) > 4:
                    try:
                        rr = self.call("Runtime.evaluate", {"expression": M98_JS_FILL, "returnByValue": True}, session=sid, timeout=5)
                        if ((rr.get("result") or {}).get("value")) == "ok":
                            self.filled[sid] = self.filled.get(sid, 0) + 1
                            self.log(f"Name „{M98_APPNAME}“ eingetragen und „Erstellen“ geklickt.")
                        self.filled[sid + "_t"] = time.time()
                    except Exception:
                        pass
        return texts, elems, mails, url, na

    def _watch(self):
        while self.state == "browser":
            if self.proc.poll() is not None:
                if self.state == "browser":
                    self.state = "abgebrochen"
                    self.error = "Google-Fenster wurde geschlossen."
                    self.log(self.error)
                break
            if time.time() - self.t0 > M94_MAX_SEK:
                self.log("Zeit abgelaufen (20 Minuten) – Fenster wird geschlossen.")
                self.state, self.error = "abgebrochen", "Zeit abgelaufen."
                self.close()
                break
            try:
                texts, elems, mails, url, na = self._scan()
                for m in mails:
                    if m not in self.mails:
                        self.mails.append(m)
                if url and self.phase == "login":
                    self.phase = "erzeugen"
                    self.log("Angemeldet – Seite „App-Passwörter“ offen.")
                if na and url and not self.hinweis2:
                    self.hinweis2 = ("Google bietet für dieses Konto keine App-Passwörter an. Ursache: 2-Schritt-Bestätigung aus, "
                                     "nur Passkey/Sicherheitsschlüssel oder „Erweiterter Schutz“. Abhilfe: 2-Schritt-Bestätigung mit Handy/Authenticator einschalten.")
                    self.log(self.hinweis2)
                for pw in gm_candidates(texts, elems):
                    if self.state != "browser" or self._try(pw):
                        break
            except Exception:
                traceback.print_exc()
            time.sleep(1.2)

    def _try(self, pw):
        zf = _gm_ziel(self.ziel)
        users = zf["adressen"](self.mails)
        if not users:
            if self.mails and zf.get("falsch") and self.hinweis2 != zf["falsch"]:
                self.hinweis2 = zf["falsch"]
                self.log(self.hinweis2)
            return False                    # address not known yet - wait until Google shows it
        if self.versuche >= M98_MAX_VERSUCHE:
            msg = ("Zu viele Versuche am Gmail-Postfach – damit Google die Adresse nicht sperrt, prüft das Programm nicht weiter. "
                   "Bitte das Fenster schließen und unten „App-Passwort selbst einfügen“ nutzen oder später neu anmelden.")
            if self.hinweis2 != msg:
                self.hinweis2 = msg
                self.log(msg)
            return False
        for u in users:
            if (u, pw) in self.tried or self.versuche >= M98_MAX_VERSUCHE:
                continue
            self.tried.add((u, pw))
            self.versuche += 1
            self.phase = "pruefen"
            msg = f"App-Passwort erkannt – prüfe am Postfach {u} …"
            if not (self.lines and self.lines[-1].endswith(msg)) and not (len(self.lines) > 1 and self.lines[-2].endswith(msg)):
                self.log(msg)
            try:
                ok = gm_check(u, pw)
            except ValueError as e:
                if not (self.lines and self.lines[-1].endswith(str(e))):
                    self.log(str(e))
                self.tried.discard((u, pw))
                self.versuche -= 1
                self.phase = "erzeugen"
                return False
            if ok:
                try:
                    self._done(u, pw)
                except ValueError as e:
                    self.hinweis2 = str(e)
                    self.log(str(e))
                    self.phase = "erzeugen"
                    return False
                return True
            self.log("Gmail lehnt dieses Passwort für " + u + " ab.")
        self.phase = "erzeugen"
        return False

    def _done(self, user, pw):
        with self.lock:                        # v2.4.8: watch thread and "einfügen" may finish at the same moment
            if getattr(self, "_fertig", False):
                return
            self._fertig = True
        try:
            self.versand = _gm_ziel(self.ziel)["save"](user, pw)
        except Exception:
            self._fertig = False
            raise
        self.adresse = user
        self.log("Passwort gespeichert (verschlüsselt) – für Abruf" + (" und Versand." if self.versand else "."))
        self.phase = "abruf"
        self.state = "fertig"
        self.close()
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        self.log("Rufe E-Mails ab …")
        try:
            r = _gm_ziel(self.ziel)["fetch"]()
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        self.abruf = r
        self.log("Abruf: " + (r.get("text") or r.get("error") or "fertig"))
        self.phase = "fertig"

    def view(self):
        return {"ok": True, "token": self.token, "state": self.state, "phase": self.phase, "error": self.error,
                "log": self.lines[-12:], "hinweis": self.cfg["hinweis"], "vorgabe": self.vorgabe, "hinweis2": self.hinweis2, "adresse": self.adresse,
                "versand": self.versand, "abruf": self.abruf, "ziel": self.ziel, "sekunden": int(time.time() - self.t0)}


def gm_start(d=None):
    ziel = str((d or {}).get("ziel") or "geschaeft")
    _gm_ziel(ziel)
    with M98["lock"]:
        s = M98["sess"]
        if s and isinstance(s, _GmSess) and (s.alive() or s.phase == "abruf" or s.state == "start"):   # v2.4.8: also while starting
            if s.ziel != ziel:
                raise ValueError("Es ist schon ein Google-Fenster offen (anderes Postfach) – bitte erst dort fertig machen oder schließen.")
            return s.view()
        s = _GmSess(ziel)
        M98["sess"] = s
    try:
        s.start()
    except Exception as e:
        s.state, s.error = "fehler", str(e).replace("Bank-Fenster", "Google-Fenster")
        s.log("Fehler: " + s.error)
        s.close()
    return s.view()


def _gm_get(token):
    s = M98["sess"]
    if not s or (token and token != s.token):
        raise ValueError("Kein Google-Fenster offen.")
    return s


def gm_status(token):
    return _gm_get(token).view()


def gm_abbrechen(token):
    s = M98["sess"]
    if s and (not token or token == s.token) and s.state == "browser":
        s.state, s.error = "abgebrochen", "Abgebrochen."
        s.close()
    return {"ok": True}


def gm_passwort(d):
    """paste fallback: app password created in the own browser"""
    pw = re.sub(r"\s", "", str(d.get("pass") or ""))
    if not re.fullmatch(r"[A-Za-z]{16}", pw):
        raise ValueError("Ein Gmail-App-Passwort hat genau 16 Buchstaben (Leerzeichen egal).")
    pw = pw.lower()
    ziel = str(d.get("ziel") or "geschaeft")
    zf = _gm_ziel(ziel)
    s = M98["sess"]
    if s and getattr(s, "ziel", "geschaeft") != ziel:
        s = None
    users = []
    u0 = str(d.get("user") or "").strip().lower()
    if u0:
        if "@" not in u0:
            u0 += "@gmail.com"
        users.append(u0)
    users += [u for u in zf["adressen"](getattr(s, "mails", []) if s else []) if u not in users]
    if not users:
        raise ValueError("Bitte deine Gmail-Adresse eintragen.")
    for u in users[:3]:
        if gm_check(u, pw):
            if s and isinstance(s, _GmSess) and s.state == "browser":
                s._done(u, pw)
                return s.view()
            versand = zf["save"](u, pw)
            r = zf["fetch"]()
            return {"ok": True, "state": "fertig", "phase": "fertig", "adresse": u, "versand": versand, "abruf": r, "log": []}
    raise ValueError("Gmail lehnt dieses App-Passwort ab (geprüft: " + ", ".join(users[:3]) + "). Neues App-Passwort erzeugen und genau so einfügen.")


def gm_info():
    s = get_settings()
    e = s.get("m98_eingerichtet") or {}
    return {"eingerichtet": bool(e), "adresse": e.get("adresse") or "", "zeit": e.get("zeit") or "",
            "browser": bool(wb_find_browser()), "adressen": gm_addresses(), "version": M98_VERSION}


M98_ZIELE["geschaeft"] = {"name": "Geschäftspostfach", "adressen": gm_addresses, "save": gm_save, "fetch": lambda: imap_fetch()}


# ============================================================ routes / hooks
HOOK_GET["/api/gm/info"] = lambda h, qs: h._send(200, gm_info())
HOOK_GET["/api/gm/status"] = lambda h, qs: _wb_r(lambda d: gm_status(qs.get("token") or ""))(h, {})
HOOK_POST["/api/gm/start"] = _wb_r(gm_start)
HOOK_POST["/api/gm/abbrechen"] = _wb_r(lambda d: gm_abbrechen(d.get("token") or ""))
HOOK_POST["/api/gm/passwort"] = _wb_r(gm_passwort)


def gm_adresse_merken(d):
    """v2.5.0: business Gmail address asked once in the UI (when nothing is set yet) - remembered for every later login"""
    a = str((d or {}).get("adresse") or "").strip().lower()
    if a and "@" not in a:
        a += "@gmail.com"
    if not gm_is_gmail(a):
        raise ValueError("Bitte eine Gmail-Adresse eintragen (…@gmail.com).")
    set_setting("m98_adresse", a)
    return {"ok": True, "adresse": a, "adressen": gm_addresses()}


HOOK_POST["/api/gm/adresse"] = _wb_r(gm_adresse_merken)


def _gm_boot(d):
    try:
        d["gm"] = gm_info()
    except Exception:
        d["gm"] = {}
    st = d.get("settings") or {}
    st.pop("m98_eingerichtet", None)


HOOK_BOOT.append(_gm_boot)


def _gm_selftest():
    err = []
    try:
        if gm_candidates(["Ihr App-Passwort für Ihr Gerät\nabcd efgh ijkl mnop\nSo verwenden Sie es"]) != ["abcdefghijklmnop"]:
            err.append("m98: App-Passwort im Seitentext nicht erkannt")
        if gm_candidates([], ["a b c d e f g h i j k l m n o p"]) != ["abcdefghijklmnop"]:
            err.append("m98: App-Passwort in Einzelzeichen nicht erkannt")
        if gm_candidates(["Anmelden Konto Gerät Name"]):
            err.append("m98: falscher Treffer im Seitentext")
        if not gm_is_gmail("x@googlemail.com") or gm_is_gmail("x@web.de"):
            err.append("m98: Gmail-Erkennung fehlerhaft")
        if not issubclass(_GmSess, _WbSess):
            err.append("m98: Browser-Sitzung fehlt")
    except Exception as e:
        err.append(f"m98 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_gm_selftest)


# ============================================================================
# Teil aus m99_mail_privat.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m99_mail_privat (v2.4.8)
# Zweites, PRIVATES E-Mail-Postfach - nur separat verwalten, NICHT auswerten.
#  - Eigene Zugangsdaten (Einstellungen > Privates Postfach), Gmail auch per Google-Login (m98, Ziel "privat").
#  - Abruf per IMAP (nur lesend, BODY.PEEK - im Postfach aendert sich nichts), automatisch alle X Minuten.
#  - Gespeichert wird getrennt vom Geschaeft: Tabelle mail_privat + Ordner "<Datenordner>\E-Mails privat".
#  - KEINE Rechnungserkennung, keine Beleg-Pruefliste, kein Absender-Gedaechtnis, keine KI, nicht im
#    GoBD-Protokoll, nicht in Steuerakte/DATEV/Statistik. Das Geschaeftspostfach (mi_*) bleibt unberuehrt.
#  - Einlesen auch per Datei: .eml, .msg, .mbox und Outlook-Datendatei .pst (ueber m99c).
#  - Seite "Privat-Mails": Liste mit Suche, Lesen (HTML ohne Nachladen externer Bilder = keine
#    Lesebestaetigungs-Pixel), Anhaenge oeffnen, markieren, lokal loeschen.
#  - Nur auf Knopfdruck: einzelne Mail "Ans Geschaeft uebergeben" (z. B. eine Rechnung, die privat ankam) -
#    erst dann laeuft sie durch die normale Pruefung im Geschaeftspostfach.
# Autor: T. Pfeiffer

M99_VERSION = "1.0.0"
M99_DIRNAME = "E-Mails privat"
M99_LOCK = threading.Lock()
M99_DB_LOCK = threading.RLock()
M99_MAX_PER_RUN = 300
M99_TEST = (__name__ == "pa_selbsttest")


def m99_schema():
    x("""CREATE TABLE IF NOT EXISTS mail_privat (id INTEGER PRIMARY KEY, msgid TEXT, hash TEXT, konto TEXT, imap_ordner TEXT,
         absender TEXT, absender_addr TEXT, empfaenger TEXT, betreff TEXT, datum TEXT, text TEXT, anhaenge TEXT,
         ordner TEXT, gelesen INTEGER DEFAULT 0, markiert INTEGER DEFAULT 0, uebergeben INTEGER DEFAULT 0, created TEXT)""")
    x("CREATE INDEX IF NOT EXISTS ix_mail_privat_msgid ON mail_privat (msgid)")
    x("CREATE INDEX IF NOT EXISTS ix_mail_privat_hash ON mail_privat (hash)")
    x("CREATE INDEX IF NOT EXISTS ix_mail_privat_datum ON mail_privat (datum)")


HOOK_SCHEMA.append(m99_schema)
try:
    M89_SKIP.add("mail_privat")      # private mailbox: no undo journal / "Verlauf"
except NameError:
    pass


def mp_dir():
    d = os.path.join(DATA_DIR, M99_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


# ============================================================ settings
def mp_cfg(over=None):
    s = get_settings()
    c = {"host": str(s.get("mp_host") or "").strip(), "port": int(float(s.get("mp_port") or 0) or 0),
         "ssl": s.get("mp_ssl", True) not in (False, 0, "0", "false"), "user": str(s.get("mp_user") or "").strip(),
         "pass": "", "folder": str(s.get("mp_folder") or "INBOX").strip() or "INBOX",
         "interval": int(float(s.get("mp_interval") or 0)), "tage": int(float(s.get("mp_tage") or 60) or 60)}
    try:
        c["pass"] = unprotect_secret(s.get("mp_pass") or "")
    except Exception:
        c["pass"] = ""
    for k, v in (over or {}).items():
        if k == "pass" and not v:
            continue
        if k in c and v is not None and v != "":
            c[k] = v.strip() if isinstance(v, str) else v
    c["port"] = int(float(c.get("port") or 0) or 0)
    c["ssl"] = c["ssl"] not in (False, 0, "0", "false")
    if c["user"] and "@" not in c["user"] and "gmail" in c["host"].lower():
        c["user"] += "@gmail.com"
    if not c["host"] and "@" in c["user"]:
        try:
            p_ = mail_provider(c["user"], "")
            if p_ and p_.get("imap") and p_["imap"][0]:
                c["host"], c["port"] = p_["imap"][0], c["port"] or int(p_["imap"][1] or 993)
        except Exception:
            pass
    if not c["port"]:
        c["port"] = 993 if c["ssl"] else 143
    if gm_is_gmail(c["user"]) or "gmail" in c["host"].lower():
        c["pass"] = re.sub(r"\s", "", c["pass"])
    return c


def mp_view():
    s = get_settings()
    c = mp_cfg()
    st = s.get("mp_status") or {}
    try:
        n = q("SELECT COUNT(*) n, SUM(CASE WHEN gelesen=0 THEN 1 ELSE 0 END) u FROM mail_privat", one=True) or {}
    except Exception:
        n = {}
    return {"ok": True, "host": c["host"], "port": c["port"], "ssl": c["ssl"], "user": c["user"], "folder": c["folder"],
            "interval": c["interval"], "tage": c["tage"], "passwort": bool(s.get("mp_pass")),
            "eingerichtet": bool(c["host"] and c["user"] and s.get("mp_pass")), "gmail": gm_is_gmail(c["user"]),
            "letzter": st, "laeuft": M99_LOCK.locked(), "anzahl": int(n.get("n") or 0), "ungelesen": int(n.get("u") or 0),
            "ordner_pfad": M99_DIRNAME, "browser": bool(wb_find_browser())}


def mp_save(d):
    keys = {"host": "mp_host", "port": "mp_port", "ssl": "mp_ssl", "user": "mp_user", "folder": "mp_folder",
            "interval": "mp_interval", "tage": "mp_tage"}
    u = str(d.get("user") or "").strip().lower()
    if u and _mp_is_business(u):
        raise ValueError("Das ist die Adresse deines Geschäftspostfachs – hier bitte das private Konto eintragen.")
    for k, sk in keys.items():
        if k in d:
            v = d[k]
            if k in ("port", "interval", "tage"):
                try:
                    v = int(float(v or 0))
                except Exception:
                    v = 0
            set_setting(sk, v.strip() if isinstance(v, str) else v)
    if d.get("pass"):
        set_setting("mp_pass", protect_secret(str(d["pass"])))
    return mp_view()


def mp_trennen(d):
    """remove the account (credentials); mails only on request"""
    for k in ("mp_pass", "mp_user", "mp_host", "mp_state", "mp_status", "m99_gmail"):
        set_setting(k, "" if k not in ("mp_state",) else {})
    n = 0
    if d.get("mails_loeschen"):
        ids = [r["id"] for r in q("SELECT id FROM mail_privat")]
        n = mp_delete(ids)["n"]
    return dict(mp_view(), geloescht=n)


def _mp_is_business(addr):
    s = get_settings()
    a = str(addr or "").strip().lower()
    return bool(a) and a in {str(s.get(k) or "").strip().lower() for k in ("mi_user", "smtp_user", "smtp_from_addr")}


# ============================================================ IMAP (own, read-only - no business password fallbacks)
def mp_connect(c, timeout=25):
    if not c["host"] or not c["user"]:
        raise ValueError("Bitte Server und Benutzer des privaten Postfachs eintragen.")
    if not c["pass"]:
        raise ValueError("Bitte das Passwort des privaten Postfachs eintragen" + (" (Gmail: „Mit Google anmelden“)." if gm_is_gmail(c["user"]) else "."))
    try:
        M = imaplib.IMAP4_SSL(c["host"], c["port"], timeout=timeout) if c["ssl"] else imaplib.IMAP4(c["host"], c["port"], timeout=timeout)
        if not c["ssl"]:
            M.starttls()
    except socket.gaierror:
        raise ValueError(f"Server „{c['host']}“ nicht gefunden.")
    except Exception as e:
        raise ValueError(f"Verbindung zu {c['host']}:{c['port']} fehlgeschlagen: {e}")
    try:
        M.login(c["user"], c["pass"])
    except imaplib.IMAP4.error as e:
        try:
            M.logout()
        except Exception:
            pass
        hint = " Gmail: unter „Privates Postfach“ auf „Mit Google anmelden“ klicken." if gm_is_gmail(c["user"]) else " Benutzer/Passwort prüfen (manche Anbieter brauchen ein App-Passwort oder IMAP-Freischaltung)."
        raise ValueError("Anmeldung am privaten Postfach abgelehnt." + hint + f" Server sagt: {_imap_txt(e)}")
    return M


def mp_test(over=None):
    c = mp_cfg(over)
    M = mp_connect(c)
    try:
        n = _imap_select(M, c["folder"], readonly=True)
        return {"ok": True, "info": f"Verbunden: {n} Mail(s) im Ordner „{c['folder']}“."}
    finally:
        try:
            M.logout()
        except Exception:
            pass


def mp_find_dup(msgid, h):
    if msgid:
        r = q("SELECT id FROM mail_privat WHERE msgid=? LIMIT 1", (msgid,), one=True)
        if r:
            return r
    return q("SELECT id FROM mail_privat WHERE hash=? LIMIT 1", (h,), one=True)


def mp_import_raw(raw, konto="", imap_ordner="", ext=".eml"):
    """store one private mail (.eml or Outlook .msg) - no classification, no business tables"""
    h = hashlib.sha1(raw).hexdigest()
    if ext == ".msg":
        tmp = os.path.join(DATA_DIR, "_tmp_" + uuid.uuid4().hex + ".msg")
        try:
            write_file(tmp, raw)
            p = mail_parse_msg(tmp)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
    else:
        p = mail_parse_eml(raw)
    with M99_DB_LOCK:
        if mp_find_dup(p.get("msgid"), h):
            return {"status": "doppelt"}
        datum = p.get("datum") or now_iso()
        stamp = re.sub(r"[^0-9]", "", datum)[:14]
        sub = re.sub(r"[^\w\-]+", "_", (p.get("betreff") or "ohne_Betreff"))[:40].strip("_") or "Mail"
        folder = os.path.join(mp_dir(), datum[:7], f"{stamp[:8]}_{stamp[8:14]}_{sub}_{h[:6]}")
        os.makedirs(folder, exist_ok=True)
        mname = "mail.msg" if ext == ".msg" else "mail.eml"
        write_file(os.path.join(folder, mname), raw)
        used, atts = {mname}, []
        for a in p["atts"][:60]:
            if a.get("inline") and (a.get("ctype") or "").startswith("image/") and len(a["data"]) < 60000:
                continue                         # small inline images (logos, signatures) stay only inside mail.eml
            nm = safe_name(a["name"]) or "anhang.bin"
            base, e_ = os.path.splitext(nm)
            k = 2
            while nm.lower() in used:
                nm = f"{base}_{k}{e_}"
                k += 1
            used.add(nm.lower())
            write_file(os.path.join(folder, nm), a["data"])
            atts.append({"name": a["name"], "size": len(a["data"]), "ctype": a.get("ctype") or "",
                         "file": os.path.relpath(os.path.join(folder, nm), DATA_DIR)})
        mid = x("INSERT INTO mail_privat (msgid, hash, konto, imap_ordner, absender, absender_addr, empfaenger, betreff, datum, text, anhaenge, "
                "ordner, gelesen, markiert, uebergeben, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,?)",
                (p.get("msgid") or "", h, konto[:200], imap_ordner[:200], (p.get("absender") or "")[:200], (p.get("absender_addr") or "")[:200],
                 (p.get("empfaenger") or "")[:300], (p.get("betreff") or "")[:500], datum, (p.get("text") or "")[:60000],
                 json.dumps(atts, ensure_ascii=False), os.path.relpath(folder, DATA_DIR), now_iso()))
    return {"status": "neu", "id": mid}


def mp_import_file(path, filename):
    """.eml / .msg / .mbox file dropped on the page Privat-Mails"""
    ext = os.path.splitext(filename.lower())[1]
    out = {"ok": True, "neu": 0, "doppelt": 0, "fehler": 0, "datei": filename}
    if ext in (".mbox", ".mbx") or (ext not in (".eml", ".msg") and open(path, "rb").read(5) == b"From "):
        mb = mailbox.mbox(path, create=False)
        try:
            for k, msg in enumerate(mb):
                if k >= 20000:
                    break
                try:
                    r = mp_import_raw(msg.as_bytes(), "Datei", filename)
                except Exception:
                    traceback.print_exc()
                    r = {"status": "fehler"}
                out[r["status"]] += 1
        finally:
            mb.close()
    elif ext in (".eml", ".msg"):
        try:
            r = mp_import_raw(open(path, "rb").read(), "Datei", filename, ext)
        except Exception:
            traceback.print_exc()
            r = {"status": "fehler"}
        out[r["status"]] += 1
    else:
        raise ValueError(f"„{filename}“ ist keine E-Mail-Datei (.eml, .msg, .mbox – Outlook-Datendatei .pst über denselben Knopf).")
    return out


def _mp_up(h, tmp, name):
    try:
        return h._send(200, mp_import_file(tmp, name))
    except ValueError as e:
        return h._send(200, {"ok": False, "error": str(e)})
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


HOOK_UPLOAD["/api/upload/mp"] = _mp_up


def mp_fetch(over=None):
    if not M99_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Abruf läuft bereits."}
    st = {"zeit": now_iso(), "ok": False, "neu": 0, "doppelt": 0, "fehler": 0, "text": ""}
    try:
        c = mp_cfg(over)
        M = mp_connect(c)
        try:
            _imap_select(M, c["folder"], readonly=True)           # read-only: nothing changes in the mailbox
            typ, data = M.response("UIDVALIDITY")
            uidv = (data[0].decode() if data and data[0] else "") if isinstance(data, list) else ""
            state = get_settings().get("mp_state") or {}
            if not isinstance(state, dict):
                state = {}
            key = f"{c['user']}@{c['host']}/{c['folder']}"
            prev = state.get(key) or {}
            last = int(prev.get("uid") or 0) if prev.get("uidvalidity") == uidv else 0
            if last:
                crit = ["UID", f"{last + 1}:*"]
            else:
                mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                d_ = datetime.date.today() - datetime.timedelta(days=max(1, c["tage"]))
                crit = ["SINCE", f"{d_.day:02d}-{mon[d_.month - 1]}-{d_.year}"]
            typ, data = M.uid("SEARCH", None, *crit)
            if typ != "OK":
                raise ValueError("Suche im Postfach fehlgeschlagen.")
            uids = sorted({int(u) for u in (data[0] or b"").split() if u.isdigit() and int(u) > last})
            more = len(uids) > M99_MAX_PER_RUN
            uids = uids[:M99_MAX_PER_RUN]
            # v2.4.8: mails that failed last time are tried again (max. 3 times)
            retry = {int(k): int(v) for k, v in ((prev.get("retry") or {}) if prev.get("uidvalidity") == uidv else {}).items()}
            uids = sorted(set(uids) | {u_ for u_, n_ in retry.items() if n_ < 3 and u_ <= last})
            max_uid = last
            for u in uids:
                ok_ = False
                try:
                    typ, msg = M.uid("FETCH", str(u), "(BODY.PEEK[])")
                    raw = next((bytes(pt[1]) for pt in msg or [] if isinstance(pt, tuple) and len(pt) >= 2 and isinstance(pt[1], (bytes, bytearray))), None)
                    if raw is not None:
                        r = mp_import_raw(raw, c["user"], c["folder"])
                        st[r["status"]] += 1
                        ok_ = True
                except Exception:
                    traceback.print_exc()
                if ok_:
                    retry.pop(u, None)
                else:
                    st["fehler"] += 1
                    retry[u] = retry.get(u, 0) + 1
                max_uid = max(max_uid, u)
            state[key] = {"uidvalidity": uidv, "uid": max_uid, "retry": {str(k): v for k, v in retry.items() if v < 3}}
            set_setting("mp_state", state)
            st["ok"] = True
            st["text"] = f"{st['neu']} neu, {st['doppelt']} schon vorhanden" + (f", {st['fehler']} Fehler" if st["fehler"] else "") + \
                (" – weitere beim nächsten Abruf" if more else "")
        finally:
            try:
                M.logout()
            except Exception:
                pass
    except ValueError as e:
        st["text"] = str(e)
    except Exception as e:
        traceback.print_exc()
        st["text"] = f"Fehler beim Abruf: {e}"
    finally:
        set_setting("mp_status", st)
        M99_LOCK.release()
    return dict(st, error=None if st["ok"] else st["text"])


def mp_loop():
    time.sleep(25)
    while True:
        try:
            s = get_settings()
            iv = int(float(s.get("mp_interval") or 0))
            if iv > 0 and s.get("mp_pass") and s.get("mp_user"):
                last = (s.get("mp_status") or {}).get("zeit") or ""
                due = True
                if last:
                    try:
                        due = (datetime.datetime.now() - datetime.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() >= iv * 60
                    except Exception:
                        due = True
                if due:
                    mp_fetch()
        except Exception:
            traceback.print_exc()
        time.sleep(30)


if not M99_TEST:
    HOOK_START.append(mp_loop)


# ============================================================ list / read / actions
def mp_list(qs):
    f = str(qs.get("f") or "alle")
    such = str(qs.get("q") or "").strip()
    off = max(0, int(qs.get("off") or 0))
    lim = min(500, max(20, int(qs.get("n") or 200)))
    w, a = [], []
    if f == "ungelesen":
        w.append("gelesen=0")
    elif f == "markiert":
        w.append("markiert=1")
    elif f == "anhang":
        w.append("anhaenge<>'[]'")
    for t in such.split()[:6]:
        w.append("(betreff LIKE ? OR absender LIKE ? OR absender_addr LIKE ? OR text LIKE ?)")
        a += [f"%{t}%"] * 4
    where = (" WHERE " + " AND ".join(w)) if w else ""
    rows = q(f"SELECT id, absender, absender_addr, betreff, datum, gelesen, markiert, uebergeben, anhaenge, substr(text,1,160) vorschau "
             f"FROM mail_privat{where} ORDER BY datum DESC, id DESC LIMIT ? OFFSET ?", tuple(a) + (lim, off))
    for r in rows:
        at = json.loads(r.pop("anhaenge") or "[]")
        r["anh"] = len(at)
        r["vorschau"] = re.sub(r"\s+", " ", r["vorschau"] or "").strip()
    tot = q(f"SELECT COUNT(*) n FROM mail_privat{where}", tuple(a), one=True)["n"]
    return {"ok": True, "items": rows, "gesamt": tot, "off": off, "n": lim, "konto": mp_view()}


def _mp_row(mid):
    r = q("SELECT * FROM mail_privat WHERE id=?", (int(mid or 0),), one=True)
    if not r:
        raise ValueError("E-Mail nicht gefunden.")
    return r


def _mp_html(path):
    """HTML part of the stored mail; cid: images become data: URIs (shown), external content stays blocked by CSP in the viewer"""
    try:
        raw = open(path, "rb").read()
    except Exception:
        return ""
    try:
        m = email.message_from_bytes(_mail_fix_headers(raw), policy=email.policy.default)
        b = m.get_body(preferencelist=("html",))
        if b is None:
            return ""
        html = b.get_content()
        cids = {}
        for part in m.walk():
            cid = (part.get("Content-ID") or "").strip("<> ")
            if cid and (part.get_content_type() or "").startswith("image/"):
                data = part.get_payload(decode=True) or b""
                if len(data) < 3000000:
                    cids[cid] = f"data:{part.get_content_type()};base64,{base64.b64encode(data).decode()}"
        if cids:
            html = re.sub(r"cid:([^\"'\s>)]+)", lambda mm: cids.get(mm.group(1), mm.group(0)), html)
        # v2.4.8: no automatic navigation out of the viewer (would tell the sender that the mail was read)
        html = re.sub(r"<meta[^>]+http-equiv\s*=\s*[\"']?refresh[^>]*>", "", html, flags=re.I)
        html = re.sub(r"<(base|link|iframe|frame|object|embed|form)\b[^>]*>", "", html, flags=re.I)
        return html[:3000000]
    except Exception:
        return ""


def mp_get(mid):
    r = _mp_row(mid)
    r["anhaenge"] = json.loads(r["anhaenge"] or "[]")
    r["html"] = _mp_html(os.path.join(DATA_DIR, r["ordner"] or "", "mail.eml")) if r.get("ordner") else ""   # .msg: text view
    r["text"] = (r["text"] or "")[:60000]
    r.pop("hash", None)
    if not r["gelesen"]:
        x("UPDATE mail_privat SET gelesen=1 WHERE id=?", (r["id"],))
    return r


def _mp_ids(d):
    ids = d.get("ids") if isinstance(d.get("ids"), list) else [d.get("id")]
    return [int(i) for i in ids if str(i or "").isdigit()]


def mp_mark(d):
    ids = _mp_ids(d)
    for k in ("gelesen", "markiert"):
        if k in d and ids:
            x(f"UPDATE mail_privat SET {k}=? WHERE id IN ({','.join('?' * len(ids))})", (1 if d[k] else 0, *ids))
    return {"ok": True, "n": len(ids)}


def mp_delete(ids):
    n = 0
    with M99_DB_LOCK:
        for i in ids:
            r = q("SELECT ordner FROM mail_privat WHERE id=?", (int(i),), one=True)
            if not r:
                continue
            if r.get("ordner"):
                p = os.path.normpath(os.path.join(DATA_DIR, r["ordner"]))
                if p.startswith(os.path.normpath(mp_dir()) + os.sep):
                    shutil.rmtree(p, ignore_errors=True)
                    try:
                        os.rmdir(os.path.dirname(p))      # empty month folder
                    except OSError:
                        pass
            x("DELETE FROM mail_privat WHERE id=?", (int(i),))
            n += 1
    return {"ok": True, "n": n}


def mp_uebergeben(d):
    """only on request: hand one private mail over to the business inbox (normal invoice check there)"""
    r = _mp_row(d.get("id"))
    base = os.path.join(DATA_DIR, r["ordner"] or "")
    path, ext = next(((os.path.join(base, n), e) for n, e in (("mail.eml", ".eml"), ("mail.msg", ".msg")) if os.path.isfile(os.path.join(base, n))), ("", ""))
    if not path:
        raise ValueError("Die Mail-Datei fehlt im Datenordner.")
    res = mail_import_raw(open(path, "rb").read(), ext, "Privat (übergeben)", r.get("konto") or "")
    x("UPDATE mail_privat SET uebergeben=1 WHERE id=?", (r["id"],))
    return {"ok": True, "status": res.get("status"), "id": res.get("id"), "urteil": res.get("urteil")}


# ============================================================ attachments: never start programs from mails
M99_GEFAEHRLICH = (".exe", ".com", ".bat", ".cmd", ".scr", ".pif", ".msi", ".msp", ".js", ".jse", ".vbs", ".vbe", ".wsf", ".wsh",
                   ".hta", ".ps1", ".psm1", ".lnk", ".cpl", ".reg", ".jar", ".dll", ".url", ".iso", ".img", ".vhd", ".vhdx",
                   ".appx", ".msix", ".application", ".gadget", ".docm", ".xlsm", ".pptm", ".scf", ".inf")
@chain_step("open_plain", "m98_mail")
def _m99_step_open_plain(_next, path, *a, **k):
    p = os.path.normcase(os.path.abspath(str(path or "")))
    roots = [os.path.normcase(os.path.abspath(os.path.join(DATA_DIR, d_))) for d_ in (M99_DIRNAME, MAIL_DIRNAME)]
    if any(p.startswith(r_ + os.sep) for r_ in roots) and p.endswith(M99_GEFAEHRLICH):
        raise ValueError("Aus Sicherheitsgründen öffnet das Programm Programme/Skripte aus E-Mails nicht direkt "
                         f"({os.path.splitext(p)[1]}). Über „Ordner öffnen“ kannst du die Datei selbst prüfen.")
    return _next(path, *a, **k)


# ============================================================ Gmail login (m98) for the private mailbox
def mp_gm_adressen(page_mails=()):
    out = []
    for a in (get_settings().get("mp_user"), *(page_mails or ())):
        a = str(a or "").strip().lower()
        if gm_is_gmail(a) and not _mp_is_business(a) and a not in out:
            out.append(a)
    return out


def mp_gm_save(user, pw):
    if _mp_is_business(user):
        raise ValueError("Das ist dein Geschäftskonto – im Google-Fenster bitte mit dem privaten Konto anmelden.")
    set_setting("mp_host", M98_GMAIL_IMAP[0])
    set_setting("mp_port", M98_GMAIL_IMAP[1])
    set_setting("mp_ssl", True)
    set_setting("mp_user", user)
    set_setting("mp_pass", protect_secret(re.sub(r"\s", "", pw)))
    if int(float(get_settings().get("mp_interval") or 0)) <= 0:
        set_setting("mp_interval", 15)
    set_setting("m99_gmail", {"zeit": now_iso(), "adresse": user})
    return False                     # private mailbox: never used for sending business mail


M98_ZIELE["privat"] = {"name": "Privates Postfach", "adressen": mp_gm_adressen, "save": mp_gm_save, "fetch": lambda: mp_fetch(),
                       "falsch": "Im Google-Fenster ist dein Geschäftskonto angemeldet. Oben rechts auf das Profilbild → Abmelden "
                                 "und mit dem privaten Gmail-Konto anmelden."}


# ============================================================ routes / hooks
HOOK_GET["/api/mp/info"] = lambda h, qs: h._send(200, mp_view())
HOOK_GET["/api/mp/list"] = lambda h, qs: _wb_r(lambda d: mp_list(qs))(h, {})
HOOK_GET["/api/mp/get"] = lambda h, qs: _wb_r(lambda d: mp_get(qs.get("id")))(h, {})
HOOK_POST["/api/mp/speichern"] = _wb_r(mp_save)
HOOK_POST["/api/mp/test"] = _wb_r(lambda d: mp_test({k: d.get(k) for k in ("host", "port", "ssl", "user", "pass", "folder") if k in d}))
HOOK_POST["/api/mp/abrufen"] = _wb_r(lambda d: mp_fetch())
HOOK_POST["/api/mp/markieren"] = _wb_r(mp_mark)
HOOK_POST["/api/mp/loeschen"] = _wb_r(lambda d: mp_delete(_mp_ids(d)))
HOOK_POST["/api/mp/uebergeben"] = _wb_r(mp_uebergeben)
HOOK_POST["/api/mp/trennen"] = _wb_r(mp_trennen)


def _mp_boot(d):
    st = d.get("settings") or {}
    for k in ("mp_pass", "mp_state", "mp_status", "m99_gmail"):
        st.pop(k, None)
    try:
        v = mp_view()
        d["mp"] = {"eingerichtet": v["eingerichtet"], "adresse": v["user"], "ungelesen": v["ungelesen"], "anzahl": v["anzahl"]}
    except Exception:
        d["mp"] = {}


HOOK_BOOT.append(_mp_boot)


def _mp_selftest():
    err = []
    try:
        raw = (b"From: Oma <oma@example.org>\r\nTo: privat@example.org\r\nSubject: Rechnung? Nein, Kuchenrezept\r\n"
               b"Message-ID: <m99test@example.org>\r\nDate: Fri, 30 Oct 2026 10:00:00 +0100\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nHallo!\r\n")
        n0 = q("SELECT COUNT(*) n FROM mail_inbox", one=True)["n"]
        r = mp_import_raw(raw, "privat@example.org", "INBOX")
        if r.get("status") != "neu":
            err.append("m99: private Mail nicht gespeichert")
        if mp_import_raw(raw).get("status") != "doppelt":
            err.append("m99: doppelte private Mail nicht erkannt")
        if q("SELECT COUNT(*) n FROM mail_inbox", one=True)["n"] != n0:
            err.append("m99: private Mail ist im Geschäftspostfach gelandet")
        lst = mp_list({"q": "Kuchenrezept"})
        if not lst["items"]:
            err.append("m99: Suche findet private Mail nicht")
        mp_delete([r["id"]])
        if "privat" not in M98_ZIELE:
            err.append("m99: Google-Login für das private Postfach fehlt")
    except Exception as e:
        err.append(f"m99 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_mp_selftest)


# ============================================================================
# Teil aus m99b_rechnungsabsender.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m99b_rechnungsabsender (v2.4.4)
# Rechnungsuebernahme aus E-Mails nur noch fuer freigegebene Absender.
#  - Standard-Liste: Apple, eBay, Vodafone (in jeder Form: Vodafone, Vodafone Kabel/Kabel Deutschland,
#    Unitymedia), Telekom (Telekom, T-Mobile), Anthropic, Deutsche Bahn (bahn.de, deutschebahn.com). PayPal ist ausdruecklich gesperrt - auch wenn es um einen
#    eBay-Kauf geht.
#  - Erkannt wird am Absender-DOMAIN (nicht am Anzeigenamen - den kann jeder faelschen).
#  - Alle anderen Mails werden gespeichert, aber NICHT ausgewertet: Urteil "Keine Rechnung", keine KI-Abfrage.
#  - Auch von freigegebenen Absendern zaehlt nur, was eine Rechnung enthaelt: Rechnung als Anhang,
#    E-Rechnung (XML), Rechnung im Mailtext (Apple-Belege) oder Rechnung im Kundenportal (Vodafone/Telekom
#    verschicken oft nur den Hinweis + Link). Bestellbestaetigungen, Versandinfos, Werbung, Mahnungen,
#    Gutschriften -> "Keine Rechnung".
#  - Liste anpassbar: Einstellungen > E-Mail-Abruf > Karte "Rechnungs-Absender".
#    Zeilenformat:  Name: muster, muster      Muster = Domain mit Endung (apple.com - Subdomains wie email.apple.com
#                                             gehoeren dazu), alter Kurzname (apple = apple.de/.com/... nur mit
#                                             ueblicher Endung) oder mit * im Namen vor der Endung (*vodafone*)
#                   !Name: muster             = gesperrt (geht vor, * und Kurzname passen dort bei jeder Endung)
#  - v2.6.3: frei gilt nur noch fuer die echte Domain inkl. Endung - apple.top, bahn.cn, telekom-xyz.ru sind fremd.
#  - "Als Beleg uebernehmen" per Hand geht weiterhin bei jeder Mail.
# Autor: T. Pfeiffer

M99B_VERSION = "1.3.0"
M99B_STANDARD = ("Apple: apple.com, itunes.com, icloud.com\n"
                 "eBay: ebay.de, ebay.com\n"
                 "Vodafone: vodafone.de, vodafone.com, vodafone-kabel.de, vodafonekabel.de, kabeldeutschland.de, kabel-deutschland.de, unitymedia.de\n"
                 "Telekom: telekom.de, telekom.com, t-mobile.de, t-mobile.com\n"
                 "Anthropic: anthropic.com\n"
                 "Deutsche Bahn: bahn.de, bahn.com, deutschebahn.com\n"
                 "!PayPal: *paypal*\n"
                 "!Apotheken: *apotheke*, docmorris, *medpex*, mycare, *apo-*")
M99B_SUBJ = re.compile(r"rechnung|invoice|receipt|quittung|\bbeleg\b|zahlungsbest(ä|ae)tigung", re.I)
M99B_NEIN = re.compile(r"mahnung|erinnerung|reminder|gutschrift|erstattung|refund|storno|newsletter|angebot", re.I)
M99B_DB = re.compile(r"buchungsbest(ä|ae)tigung|fahrkarte|ticket|bahncard", re.I)
# v2.4.5: mails with an amount that are no invoice (order/payment confirmations) get their own judgement
MAIL_URTEILE["zahlung"] = "Zahlung/Bestellung mit Betrag (keine Rechnung)"
M99B_BETRAG = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2})\s?(?:€|eur\b)|(?:€|eur)\s?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+[.,]\d{2})", re.I)
M99B_KAUF = re.compile(r"bestell|kauf|gekauft|zahlung|bezahlt|order|beleg|quittung|ticket|buchung|abbuchung|lastschrift|einzug|payment|purchase|receipt", re.I)
# v2.4.5: advertising / newsletters of invoice senders (e.g. news@insideapple.apple.com with prices) are no invoices
M99B_WERB_LOCAL = re.compile(r"^(news|newsletter|marketing|promo|promotion|angebot|angebote|deals|offers|mailing|werbung|aktion|aktionen|no-?reply-?news)", re.I)
M99B_WERB_DOM = {"news", "newsletter", "insideapple", "marketing", "promo", "mailing", "angebote", "deals", "offers", "mail-news", "e-news"}


def m99b_werbung(p):
    """True = newsletter/advertising (list header, bulk mail, typical marketing sender)"""
    addr = str(p.get("absender_addr") or "").lower()
    local, _, dom = addr.partition("@")
    if p.get("list_unsub") or str(p.get("precedence") or "").lower() in ("bulk", "list", "junk"):
        return True
    if M99B_WERB_LOCAL.search(local):
        return True
    return any(l in M99B_WERB_DOM for l in dom.split("."))


M99B_ENTHAELT = ("rechnung_anhang", "rechnung_text", "erechnung", "rechnung_link")


M99B_MUSTER_RX = r"\*?[a-z0-9-]+\*?(?:\.[a-z0-9-]+)*"
# endings a short name (apple) or a *pattern* without ending may have in an allow line - phishing domains use others
M99B_TLD_OK = {"de", "com", "net", "org", "eu", "at", "ch", "nl", "be", "fr", "it", "es", "ie", "lu", "co.uk", "com.au"}


def _m99b_reg(domain):
    """registrable domain (mail.apple.com -> apple.com, shop.co.uk -> shop.co.uk) -> (name, ending)"""
    parts = [x for x in str(domain or "").lower().strip(".").split(".") if x]
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gv", "ac") and len(parts[-1]) == 2:
        return parts[-3], ".".join(parts[-2:])
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return (parts[0] if parts else ""), ""


def m99b_parse(text):
    """'Name: a, *b*' lines -> [{"name", "sperre", "muster": [...]}]"""
    out = []
    for ln in str(text or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ":" not in ln:
            continue
        name, rest = ln.split(":", 1)
        name = name.strip()
        sperre = name.startswith("!")
        name = name.lstrip("!").strip()
        mu = [m.strip().lower() for m in re.split(r"[,;\s]+", rest) if m.strip()]
        mu = [m for m in mu if re.fullmatch(M99B_MUSTER_RX, m)]
        if name and mu:
            out.append({"name": name, "sperre": sperre, "muster": mu})
    return out


def m99b_liste():
    s = get_settings()
    t = s.get("m99b_liste")
    return m99b_parse(t if isinstance(t, str) and t.strip() else M99B_STANDARD)


def _m99b_glob(label, m):
    """* only inside ONE domain label (never across a dot)"""
    rx = "".join("[a-z0-9-]*" if ch == "*" else re.escape(ch) for ch in m)
    return re.fullmatch(rx, label) is not None


def _m99b_hit(domain, muster, sperre=False):
    """allow line (sperre=False):
         apple.com      = this registrable domain and its subdomains (email.apple.com), NOT apple.com.evil.de
         *vodafone*.de  = * inside the name before the ending
         apple / *x*    = short name: only with a usual ending (M99B_TLD_OK) - apple.top / bahn.cn stay foreign
       block line (sperre=True): short name / *x* match the name with ANY ending (blocking may be broad)"""
    dom = str(domain or "").lower().strip(".")
    if not dom:
        return False
    name, tld = _m99b_reg(dom)
    labels = [l for l in dom.split(".") if l]
    for m in muster:
        if "." in m:
            mn, _, mt = m.partition(".")
            if "*" in mn:
                if mt == tld and _m99b_glob(name, mn):
                    return True
            elif dom == m or dom.endswith("." + m):
                return True
            continue
        if sperre:
            if ("*" in m and any(_m99b_glob(l, m) for l in labels)) or ("*" not in m and m == name):
                return True
        elif tld in M99B_TLD_OK and (_m99b_glob(name, m) if "*" in m else m == name):
            return True
    return False


def m99b_absender(addr, liste=None):
    """-> (status, name): status 'frei' / 'gesperrt' / 'fremd'"""
    addr = str(addr or "").strip().lower()
    dom = addr.rsplit("@", 1)[-1] if "@" in addr else ""
    if not dom:
        return "fremd", ""
    liste = m99b_liste() if liste is None else liste
    for r in liste:
        if r["sperre"] and _m99b_hit(dom, r["muster"], sperre=True):
            return "gesperrt", r["name"]
    for r in liste:
        if not r["sperre"] and _m99b_hit(dom, r["muster"]):
            return "frei", r["name"]
    return "fremd", ""


def m99b_betrag(p):
    """first EUR amount in subject/text -> float or 0 (cheap, no attachment analysis)"""
    t = (str(p.get("betreff") or "") + "\n" + str(p.get("text") or "")[:20000])
    m = M99B_BETRAG.search(t)
    if not m:
        return 0.0
    v = (m.group(1) or m.group(2) or "").strip()
    try:
        if "," in v:
            v = v.replace(".", "").replace(",", ".")
        return round(float(v), 2)
    except Exception:
        return 0.0


def _m99b_zahlung(p, r, frei):
    """amount but no invoice -> 'zahlung' (visible, one click to declare it an invoice); never for advertising"""
    b = m99b_betrag(p)
    if b <= 0:
        return False
    if m99b_werbung(p) and not M99B_KAUF.search(str(p.get("betreff") or "")):
        return False
    r["urteil"], r["sicherheit"], r["betrag"] = "zahlung", 0.7, r.get("betrag") or b
    r["begruendung"].append(f"Betrag {b:.2f} € gefunden, aber keine Rechnung (z. B. Bestell-/Zahlungsbestätigung)"
                            + ("" if frei else " – Absender nicht auf der Rechnungs-Liste") + ". Ist es doch eine: „Ist eine Rechnung“ klicken.")
    return True


@chain_step("mail_classify_full", "m98_mail")
def _m99b_step_mail_classify_full(_next, p, atts_info, llm_budget=None):
    st, name = m99b_absender(p.get("absender_addr"))
    if st == "fremd":
        r = {"urteil": "keine", "sicherheit": 0.99, "begruendung": [], "betrag": None}
        if not _m99b_zahlung(p, r, False):
            r["begruendung"].append(f"Absender {p.get('absender_addr') or '?'} steht nicht auf der Liste der Rechnungs-Absender – nur gespeichert, nicht ausgewertet.")
        return r
    if st != "frei":
        why = (f"Absender {p.get('absender_addr') or '?'} ist gesperrt ({name}) – wird nicht als Rechnung ausgewertet." if st == "gesperrt" else
               f"Absender {p.get('absender_addr') or '?'} steht nicht auf der Liste der Rechnungs-Absender – nur gespeichert, nicht ausgewertet.")
        return {"urteil": "keine", "sicherheit": 0.99, "begruendung": [why], "betrag": None}
    r = _next(p, atts_info, llm_budget)
    r["begruendung"] = [f"Rechnungs-Absender: {name}"] + list(r.get("begruendung") or [])
    subj = str(p.get("betreff") or "")
    inv_att = any(a.get("art") in ("rechnung", "erechnung") for a in atts_info or [])
    if not inv_att and not (M99B_SUBJ.search(subj) and not M99B_NEIN.search(subj)):
        if m99b_werbung(p):
            r["urteil"], r["sicherheit"], r["betrag"] = "keine", 0.95, None
            r["begruendung"].append("Werbung/Newsletter (Werbe-Absender oder Abmelde-Link) – Preise darin sind keine Rechnung.")
            return r
        if r.get("urteil") == "rechnung_text" and float(r.get("sicherheit") or 0) < 0.6:
            r["begruendung"].append("Zu wenige Rechnungsmerkmale im Mailtext und kein Rechnungs-Betreff.")
            r["urteil"] = "auftrag"          # -> below: amount = 'zahlung', otherwise 'keine'
    if r.get("urteil") not in M99B_ENTHAELT:
        # known invoice sender: the subject decides (Apple "Deine Rechnung von Apple", Anthropic "Your receipt",
        # Deutsche Bahn "Buchungsbestaetigung" with the ticket/invoice PDF) - order/shipping/marketing mails stay out
        subj = str(p.get("betreff") or "")
        pdf = any(str(a.get("name") or "").lower().endswith((".pdf", ".xml")) and a.get("art") not in ("logo", "leer") for a in atts_info or [])
        if M99B_SUBJ.search(subj) and not M99B_NEIN.search(subj):
            r["urteil"], r["sicherheit"] = ("rechnung_anhang" if pdf else "rechnung_text"), 0.88
            r["begruendung"].append("Rechnungs-Absender und Betreff nennt Rechnung/Beleg.")
        elif M99B_DB.search(subj) and pdf and name == "Deutsche Bahn":
            r["urteil"], r["sicherheit"] = "rechnung_anhang", 0.85
            r["begruendung"].append("Deutsche Bahn: Buchungsbestätigung mit Fahrkarte/Rechnung als PDF.")
    if r.get("urteil") not in M99B_ENTHAELT:
        was = MAIL_URTEILE.get(r.get("urteil"), r.get("urteil"))
        if r.get("urteil") in ("mahnung", "gutschrift") or not _m99b_zahlung(p, r, True):
            r["begruendung"].append(f"Enthält keine Rechnung ({was}) – wird nicht übernommen.")
            r["urteil"], r["sicherheit"] = "keine", max(0.9, float(r.get("sicherheit") or 0))
    return r


# ---- manual: "Ist eine Rechnung" (declared by you - never overwritten by a re-evaluation)
def _m99b_manuell():
    v = get_settings().get("m99b_manuell")
    return set(int(i) for i in v) if isinstance(v, list) else set()


def _m99b_label(addr):
    dom = str(addr or "").lower().rsplit("@", 1)[-1]
    parts = [x for x in dom.split(".") if x]
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gv", "ac") and len(parts[-1]) == 2:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")


def m99b_liste_add(addr, name=""):
    """sender -> own line in the list (unless already allowed); -> (added, label, reason)"""
    st, nm = m99b_absender(addr)
    if st == "frei":
        return False, nm, "steht schon auf der Liste"
    if st == "gesperrt":
        return False, nm, f"ist gesperrt ({nm})"
    lab = _m99b_label(addr)
    nm_, tld_ = _m99b_reg(str(addr).lower().rsplit("@", 1)[-1])
    dom_ = f"{nm_}.{tld_}" if nm_ and tld_ else ""
    if not lab or not dom_ or not re.fullmatch(M99B_MUSTER_RX, dom_):
        return False, "", "Domain nicht erkannt"
    if (str(addr).lower().rsplit("@", 1)[-1]) in MAIL_FREEMAIL:
        return False, lab, "Freemail-Adresse (gmail, web.de …) – würde alle Absender dort freigeben"
    t = m99b_view()["text"].rstrip() + f"\n{(name or lab).strip()[:40].replace(':', ' ')}: {dom_}"     # full domain incl. ending
    set_setting("m99b_liste", t)
    return True, lab, ""


def _m99b_reanalyse(r):
    """attachments stored with 'nicht ausgewertet' -> analyse them now (needed before 'Als Beleg uebernehmen');
    returns the new attachment list (also written to the row)"""
    atts = json.loads(r["anhaenge"] or "[]")
    if not any("nicht ausgewertet" in str(a.get("hinweis") or "") for a in atts):
        return atts
    other = any(os.path.splitext(str(a.get("name") or "").lower())[1] in ATT_DOC_EXT for a in atts)
    new = []
    for a in atts:
        fp = os.path.join(DATA_DIR, a["file"]) if a.get("file") else ""
        if "nicht ausgewertet" in str(a.get("hinweis") or "") and fp and os.path.isfile(fp):
            try:
                i = _m99b_orig_att_info(a.get("name") or os.path.basename(fp), open(fp, "rb").read(), False, other)
                i["file"] = a["file"]
                ext_ = os.path.splitext(fp.lower())[1]
                if i.get("art") in ("logo", "leer", "sonstig") and (ext_ in ATT_IMG_EXT or ext_ in ATT_DOC_EXT):
                    # file exists and you declared the mail an invoice -> make it selectable for "Als Beleg uebernehmen"
                    i["art"] = "bild" if ext_ in ATT_IMG_EXT else "dokument"
                a = i
            except Exception:
                traceback.print_exc()
        new.append(a)
    x("UPDATE mail_inbox SET anhaenge=? WHERE id=?", (json.dumps(new, ensure_ascii=False, default=str), r["id"]))
    return new


def mail_ist_rechnung(d):
    ids = [int(i) for i in (d.get("ids") or ([d["id"]] if d.get("id") else []))]
    man = _m99b_manuell()
    n, added, notes = 0, [], []
    for mid in ids:
        r = q("SELECT * FROM mail_inbox WHERE id=?", (mid,), one=True)
        if not r or r["status"] == "geloescht":
            continue
        atts = _m99b_reanalyse(r)
        has_doc = any(a.get("file") and a.get("art") in ("rechnung", "erechnung", "dokument", "bild", "sonstig") and
                      str(a.get("name") or "").lower().endswith((".pdf", ".xml", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic")) for a in atts)
        urteil = "rechnung_anhang" if has_doc else "rechnung_text"
        beg = json.loads(r["begruendung"] or "[]")
        beg.append("Von dir als Rechnung markiert.")
        betrag = r["betrag"] or m99b_betrag({"betreff": r["betreff"], "text": r["text"]}) or None
        x("UPDATE mail_inbox SET urteil=?, sicherheit=1.0, begruendung=?, betrag=?, status=CASE WHEN status='keine' THEN 'neu' ELSE status END, updated=? WHERE id=?",
          (urteil, json.dumps(beg, ensure_ascii=False), betrag, now_iso(), mid))
        mail_learn_sender(r["absender_addr"], True)
        man.add(mid)
        n += 1
        if d.get("liste"):
            ok, lab, why = m99b_liste_add(r["absender_addr"], r["absender"])
            if ok:
                added.append(lab)
            elif why and why != "steht schon auf der Liste":
                notes.append(f"{r['absender_addr']}: {why}")
    set_setting("m99b_manuell", sorted(man)[-20000:])
    return {"ok": True, "n": n, "liste": sorted(set(added)), "hinweise": notes[:5]}


@chain_step("mail_reclassify", "m98_mail")
def _m99b_step_mail_reclassify(_next, ids=None):
    """manual decisions stay; attachments of senders that are now on the list get analysed; chunks of 400 (SQLite limit)"""
    man = _m99b_manuell()
    if ids is None:
        ids = [r["id"] for r in q("SELECT id FROM mail_inbox WHERE status='neu'")]
    ids = [int(i) for i in ids if int(i) not in man]
    n = 0
    for k in range(0, len(ids), 400):
        part = ids[k:k + 400]
        for r in q(f"SELECT id, absender_addr, anhaenge FROM mail_inbox WHERE id IN ({','.join('?' * len(part))}) AND anhaenge LIKE '%nicht ausgewertet%'", part):
            if m99b_absender(r["absender_addr"])[0] == "frei":
                _m99b_reanalyse(r)
        n += _next(part) or 0
    return n


@chain_step("mail_mark_none", "m98_mail")
def _m99b_step_mail_mark_none(_next, ids):
    man = _m99b_manuell()
    if man & {int(i) for i in ids}:
        set_setting("m99b_manuell", sorted(man - {int(i) for i in ids}))
    return _next(ids)


HOOK_POST["/api/mail/ist_rechnung"] = _wb_r(mail_ist_rechnung)
HOOK_POST["/api/mail/keine"] = lambda h, d: h._send(200, mail_mark_none(_mail_ids(d)))


# ---- speed: attachments of mails from senders NOT on the list are not analysed (big Outlook files)
M99B_TL = threading.local()
_m99b_orig_att_info = chain_inner("mail_att_info", "m98_mail")   # v3.0.0: the level below this module (was: the function before the wrapper)
def _m99b_mark(p):
    try:
        M99B_TL.frei = m99b_absender((p or {}).get("absender_addr"))[0] == "frei"
    except Exception:
        M99B_TL.frei = True
    return p


@chain_step("mail_parse_eml", "m98_mail")
def _m99b_step_mail_parse_eml(_next, raw):
    return _m99b_mark(_next(raw))


@chain_step("mail_parse_msg", "m98_mail")
def _m99b_step_mail_parse_msg(_next, path):
    return _m99b_mark(_next(path))


@chain_step("mail_att_info", "m98_mail")
def _m99b_step_mail_att_info(_next, name, data, inline=False, other_docs=False):
    if getattr(M99B_TL, "frei", True) is False:
        ext = os.path.splitext((name or "").lower())[1]
        art = "leer" if not data else ("logo" if ext in ATT_IMG_EXT and (inline or len(data) < 30000) else "sonstig")
        return {"name": name, "size": len(data or b""), "ext": ext, "art": art, "score": 0.0,
                "hinweis": "nicht ausgewertet (Absender nicht auf der Rechnungs-Liste)"}
    return _next(name, data, inline, other_docs)


def m99b_neu_bewerten():
    """re-evaluate all business mails that are still open (once after the update, and after changing the list)"""
    try:
        n = mail_reclassify(None)
        return {"ok": True, "n": n}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


def _m99b_start():
    time.sleep(8)
    s = get_settings()
    if s.get("m99b_bewertet") != M99B_VERSION:
        r = m99b_neu_bewerten()
        if r.get("ok"):
            set_setting("m99b_bewertet", M99B_VERSION)
            print(f"INIT m99b: {r['n']} offene Mail(s) mit der Rechnungs-Absenderliste neu bewertet")


if __name__ != "pa_selbsttest":
    HOOK_START.append(_m99b_start)


def m99b_view():
    s = get_settings()
    t = s.get("m99b_liste")
    return {"ok": True, "text": t if isinstance(t, str) and t.strip() else M99B_STANDARD, "standard": M99B_STANDARD,
            "liste": m99b_liste(), "eigene": bool(isinstance(t, str) and t.strip())}


def m99b_save(d):
    t = str(d.get("text") or "").strip()
    if d.get("standard") or t == M99B_STANDARD:
        t = ""
    elif not any(not r["sperre"] for r in m99b_parse(t)):
        raise ValueError("Die Liste enthält keinen freigegebenen Absender (Format: „Name: muster, muster“).")
    set_setting("m99b_liste", t)
    n_open = q("SELECT COUNT(*) n FROM mail_inbox WHERE status='neu'", one=True)["n"]
    if n_open > 300:                     # big inbox (e.g. after a .pst import): re-evaluate in the background
        threading.Thread(target=m99b_neu_bewerten, daemon=True).start()
        return dict(m99b_view(), neu_bewertet=0, hintergrund=n_open)
    r = m99b_neu_bewerten()
    return dict(m99b_view(), neu_bewertet=r.get("n", 0))


HOOK_GET["/api/m99b/liste"] = lambda h, qs: h._send(200, m99b_view())
HOOK_POST["/api/m99b/liste"] = _wb_r(m99b_save)


def _m99b_selftest():
    err = []
    try:
        L = m99b_parse(M99B_STANDARD)
        cases = {"no_reply@email.apple.com": "frei", "ebay@ebay.de": "frei", "rechnung@vodafone.de": "frei", "info@kabeldeutschland.de": "frei",
                 "noreply@rechnung.vodafone-kabel.de": "frei", "rechnungonline@telekom.de": "frei", "service@paypal.de": "gesperrt",
                 "invoice+statements@mail.anthropic.com": "frei", "buchungsbestaetigung@bahn.de": "frei", "noreply@deutschebahn.com": "frei",
                 "x@apple-id-sicherheit.info": "fremd", "billing@apple.irgendwas.de": "fremd", "news@insideapple.apple.com": "frei", "shop@amazon.de": "fremd", "kunde@gmail.com": "fremd",
                 # v2.6.3: phishing look-alikes (other ending / name only contains the brand)
                 "billing@apple.top": "fremd", "x@bahn.cn": "fremd", "rechnung@telekom-kundenservice.ru": "fremd",
                 "re@myvodafone-billing.xyz": "fremd", "x@apple.com.evil.de": "fremd", "a@ebay.de": "frei", "b@email.t-mobile.de": "frei",
                 "service@paypal.com": "gesperrt", "x@paypal-rechnung.top": "gesperrt"}
        for a, want in cases.items():
            got = m99b_absender(a, L)[0]
            if got != want:
                err.append(f"m99b: {a} -> {got}, erwartet {want}")
        r = mail_classify_full({"absender_addr": "service@paypal.de", "betreff": "Ihre Rechnung", "text": "Rechnung 12,00 EUR", "links": [], "atts": []}, [])
        if r["urteil"] != "keine":
            err.append("m99b: PayPal-Mail wird ausgewertet")
        r = mail_classify_full({"absender_addr": "no_reply@email.apple.com", "betreff": "Deine Rechnung von Apple", "text": "Gesamt 9,99 €", "links": [], "atts": []}, [])
        if r["urteil"] != "rechnung_text":
            err.append("m99b: Apple-Rechnung nicht erkannt")
        r = mail_classify_full({"absender_addr": "ebay@ebay.de", "betreff": "Bestellung bestätigt: Kabel", "text": "Danke", "links": [], "atts": []}, [])
        if r["urteil"] != "keine":
            err.append("m99b: eBay-Bestellbestätigung als Rechnung gewertet")
        r = mail_classify_full({"absender_addr": "ebay@ebay.de", "betreff": "Bestellung bestätigt: Kabel", "text": "Gesamt: 12,99 EUR", "links": [], "atts": []}, [])
        if r["urteil"] != "zahlung":
            err.append("m99b: Bestellung mit Betrag nicht als Zahlung erkannt")
        r = mail_classify_full({"absender_addr": "service@shop-apotheke.com", "betreff": "Ihre Rechnung", "text": "Gesamt 19,90 €", "links": [], "atts": []}, [])
        if r["urteil"] != "keine":
            err.append("m99b: Apotheke wird ausgewertet")
        r = mail_classify_full({"absender_addr": "news@insideapple.apple.com", "betreff": "Die Apple Watch Series 12 ist da.",
                                "text": "Ab 79,12 € im Monat. Jetzt kaufen.", "links": [], "atts": [], "list_unsub": True}, [])
        if r["urteil"] != "keine":
            err.append("m99b: Apple-Werbung als " + r["urteil"] + " gewertet")
        if _m99b_label("a@mail.anthropic.com") != "anthropic" or _m99b_label("x@shop.co.uk") != "shop":
            err.append("m99b: Domain-Kürzel falsch")
        # own lists of older versions (short names / *wildcards*) keep working, but not for foreign endings
        old = m99b_parse("Apple: apple\nVodafone: *vodafone*\nShop: *muster*.de")
        for a, want in {"a@email.apple.com": "frei", "a@apple.top": "fremd", "a@rechnung.vodafone-kabel.de": "frei",
                        "a@vodafone-billing.xyz": "fremd", "a@mein-muster.de": "frei", "a@mein-muster.de.evil.ru": "fremd"}.items():
            if m99b_absender(a, old)[0] != want:
                err.append(f"m99b (alte Liste): {a} -> {m99b_absender(a, old)[0]}, erwartet {want}")
    except Exception as e:
        err.append(f"m99b Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m99b_selftest)


# ============================================================================
# Teil aus m99c_outlook.py
# ============================================================================
# Pfeiffer-Audio Rechnung - Modul m99c_outlook (v2.4.4)
# Schnittstelle zu Microsoft Outlook (Desktop-Programm, "klassisches" Outlook aus Microsoft 365 / Office 2016-2024).
#  1. Versand ueber Outlook: Rechnungen, Angebote, Mahnungen, Regel-Mails gehen statt per SMTP ueber dein
#     Outlook raus - mit dem Outlook-Konto deiner Wahl, landen in "Gesendete Elemente", Outlook-Signatur bleibt
#     dein Ding. Auf Wunsch wird die Mail erst im Outlook-Fenster angezeigt und du klickst selbst auf Senden.
#  2. Abruf aus Outlook: Mails aus dem Posteingang (oder einem Unterordner) eines Outlook-Kontos werden ins
#     Programm geholt (als .msg) und laufen durch die normale Rechnungspruefung - mit der Rechnungs-Absenderliste
#     (m99b). In Outlook aendert sich nichts.
#  3. Outlook-Datendateien (.pst UND .ost) einlesen: auf der Seite E-Mails (Geschaeft, wird geprueft) oder
#     Privat-Mails (nur gespeichert) hineinziehen oder per Knopf waehlen. v2.4.5: Datei und Ordner werden
#     gemerkt und bei JEDEM Programmstart aktualisiert (nur neue Mails). .ost = Konto im Outlook dieses PCs,
#     wird ueber dieses Konto gelesen; .pst wird kurz eingehaengt. Ausgelassen: Geloeschte Elemente, Junk,
#     Postausgang, Entwuerfe. Neue .pst-Dateien in einem gemerkten Ordner kommen beim Start automatisch dazu.
# Technik: Outlook-COM-Schnittstelle ueber Windows PowerShell (in Windows enthalten) - keine neue Bibliothek.
# Hinweis: Das NEUE Outlook (olk.exe, "Neues Outlook"-Schalter) hat keine Schnittstelle fuer Programme - dann
# im Outlook oben rechts "Neues Outlook" ausschalten oder weiter den normalen Mailversand (SMTP/IMAP) nutzen.
# Autor: T. Pfeiffer

M99C_VERSION = "1.1.0"
M99C_LOCK = threading.Lock()
M99C_MAX = 200
M99C_TEST = (__name__ == "pa_selbsttest")

M99C_PS_HEAD = r"""
$ErrorActionPreference = "Stop"
$inp = Get-Content -Raw -Encoding UTF8 -LiteralPath $args[0] | ConvertFrom-Json
$out = @{ ok = $false }
function Save-Out { [IO.File]::WriteAllText($args[0], ($out | ConvertTo-Json -Depth 6 -Compress), (New-Object Text.UTF8Encoding($false))) }
function Get-OL {
  try { return New-Object -ComObject Outlook.Application }
  catch { throw "OUTLOOK_FEHLT: " + $_.Exception.Message }
}
function Find-Account($ol, $smtp) {
  if (-not $smtp) { return $null }
  foreach ($a in $ol.Session.Accounts) { if ($a.SmtpAddress -ieq $smtp -or $a.DisplayName -ieq $smtp) { return $a } }
  return $null
}
function Get-Inbox($ol, $smtp, $path) {
  $ns = $ol.GetNamespace("MAPI")
  $acc = Find-Account $ol $smtp
  if ($acc) { $f = $acc.DeliveryStore.GetDefaultFolder(6) } else { $f = $ns.GetDefaultFolder(6) }
  if ($path) { foreach ($p in ($path -split "[/\\]")) { if ($p) { $f = $f.Folders.Item($p) } } }
  return $f
}
"""

M99C_PS = {
    "info": r"""
try {
  $ol = Get-OL
  $out.version = [string]$ol.Version
  $acc = @()
  foreach ($a in $ol.Session.Accounts) {
    $fold = @()
    try {
      $ib = $a.DeliveryStore.GetDefaultFolder(6)
      foreach ($s in $ib.Folders) { $fold += [string]$s.Name; foreach ($s2 in $s.Folders) { $fold += ([string]$s.Name + "/" + [string]$s2.Name) } }
      $ibn = [string]$ib.Name
    } catch { $ibn = "" }
    $acc += @{ name = [string]$a.DisplayName; smtp = [string]$a.SmtpAddress; posteingang = $ibn; ordner = $fold }
  }
  $out.konten = $acc
  $out.ok = $true
} catch { $out.error = $_.Exception.Message }
Save-Out $args[1]
""",
    "senden": r"""
try {
  $ol = Get-OL
  $m = $ol.CreateItem(0)
  $m.To = [string]$inp.to
  if ($inp.cc) { $m.CC = [string]$inp.cc }
  $m.Subject = [string]$inp.subject
  $m.Body = [string]$inp.body
  foreach ($f in $inp.files) { [void]$m.Attachments.Add([string]$f) }
  $acc = Find-Account $ol $inp.konto
  if ($inp.konto -and -not $acc) { throw "KONTO_FEHLT: " + $inp.konto }
  if ($acc) {
    try { [void][System.__ComObject].InvokeMember("SendUsingAccount", [System.Reflection.BindingFlags]::SetProperty, $null, $m, @($acc)) }
    catch { $m.SendUsingAccount = $acc }
  }
  if ($inp.anzeigen) { $m.Display($false); $out.angezeigt = $true } else { $m.Send(); $out.gesendet = $true }
  $out.ok = $true
} catch { $out.error = $_.Exception.Message }
Save-Out $args[1]
""",
    "abrufen": r"""
try {
  $ol = Get-OL
  $f = Get-Inbox $ol $inp.konto $inp.ordner
  $out.ordner = [string]$f.FolderPath
  $seit = [datetime]::ParseExact([string]$inp.seit, "yyyy-MM-dd HH:mm:ss", [Globalization.CultureInfo]::InvariantCulture)
  $known = @{}
  foreach ($e in $inp.bekannt) { $known[[string]$e] = 1 }
  $items = $f.Items
  $items.Sort("[ReceivedTime]", $true)
  $res = @(); $n = 0; $mehr = $false
  $i = $items.GetFirst()
  $skipped = 0
  while ($i -ne $null) {
    $stop = $false
    try {
      if ($i.Class -eq 43) {
        if ($i.ReceivedTime -lt $seit) { $stop = $true }
        else {
          $id = [string]$i.EntryID
          if (-not $known.ContainsKey($id)) {
            if ($n -ge [int]$inp.max) { $mehr = $true; $stop = $true }
            else {
              $p = Join-Path $inp.dir ("m" + $n + ".msg")
              $i.SaveAs($p, 3)
              $res += @{ file = $p; id = $id; zeit = $i.ReceivedTime.ToString("yyyy-MM-dd HH:mm:ss") }
              $n++
            }
          }
        }
      }
    } catch { $skipped++ }
    if ($stop) { break }
    $i = $items.GetNext()
  }
  $out.uebersprungen = $skipped
  $out.mails = $res
  $out.mehr = $mehr
  $out.ok = $true
} catch { $out.error = $_.Exception.Message }
Save-Out $args[1]
""",
    "stores": r"""
try {
  $ol = Get-OL
  $ns = $ol.GetNamespace("MAPI")
  $st = @()
  foreach ($s in $ns.Stores) { $fp = ""; try { $fp = [string]$s.FilePath } catch {}; $st += @{ name = [string]$s.DisplayName; pfad = $fp } }
  $out.stores = $st
  $out.ok = $true
} catch { $out.error = $_.Exception.Message }
Save-Out $args[1]
""",
    "sync": r"""
$ns = $null; $store = $null; $added = $false
try {
  $ol = Get-OL
  $ns = $ol.GetNamespace("MAPI")
  $pfad = [string]$inp.pfad
  $name = [IO.Path]::GetFileName($pfad)
  $max = [int]$inp.max
  if ($max -le 0) { $max = [int]::MaxValue }
  foreach ($s in $ns.Stores) { $fp = ""; try { $fp = [string]$s.FilePath } catch {}; if ($fp -and $fp -ieq $pfad) { $store = $s } }
  # by file name only for .ost (path of the account file may differ) - a .pst with the same name elsewhere is another file
  if (-not $store -and $pfad -match '\.ost$') { foreach ($s in $ns.Stores) { $fp = ""; try { $fp = [string]$s.FilePath } catch {}; if ($fp -and ([IO.Path]::GetFileName($fp) -ieq $name)) { $store = $s } } }
  if (-not $store) {
    if ($pfad -match '\.ost$') { throw "OST_FREMD: " + $name }
    $before = @{}
    foreach ($s in $ns.Stores) { $before[[string]$s.StoreID] = 1 }
    try { $ns.AddStore($pfad) } catch { throw "PST_FEHLER: " + $_.Exception.Message }
    foreach ($s in $ns.Stores) { if (-not $before.ContainsKey([string]$s.StoreID)) { $store = $s } }
    if (-not $store) { throw "PST_FEHLER: Datei wurde von Outlook nicht eingehaengt." }
    $added = $true
    # marker: if this run is killed, the next start detaches the store again ("abhaengen")
    if ($inp.marker) { try { [IO.File]::WriteAllText([string]$inp.marker, $pfad, (New-Object Text.UTF8Encoding($false))) } catch {} }
  }
  $out.name = [string]$store.DisplayName
  try { $out.pfad = [string]$store.FilePath } catch { $out.pfad = $pfad }
  $seit = [datetime]::ParseExact([string]$inp.seit, "yyyy-MM-dd HH:mm:ss", [Globalization.CultureInfo]::InvariantCulture)
  $known = @{}
  foreach ($e in $inp.bekannt) { $known[[string]$e] = 1 }
  $skip = @{}
  foreach ($t in 3, 4, 16, 23) { try { $skip[[string]$store.GetDefaultFolder($t).EntryID] = 1 } catch {} }
  $list = New-Object System.Collections.ArrayList
  $script:n = 0
  $script:voll = $false
  function Walk($f, $path) {
    if ($script:voll) { return }
    if ($skip.ContainsKey([string]$f.EntryID)) { return }
    if ($f.DefaultItemType -eq 0) {
      $items = $f.Items
      try { $items.Sort("[ReceivedTime]", $true) } catch {}
      $it = $items.GetFirst()
      while ($it -ne $null) {
        $stop = $false
        try {
          if ($it.Class -eq 43) {
            if ($it.ReceivedTime -lt $seit) { $stop = $true }
            else {
              $id = [string]$it.EntryID
              if (-not $known.ContainsKey($id)) {
                if ($script:n -ge $max) { $script:voll = $true; $stop = $true }
                else {
                  $p = Join-Path $inp.dir ("m{0:D6}.msg" -f $script:n)
                  $it.SaveAs($p, 3)
                  [void]$list.Add(@{ file = $p; id = $id; ordner = $path; zeit = $it.ReceivedTime.ToString("yyyy-MM-dd HH:mm:ss") })
                  $script:n++
                }
              }
            }
          }
        } catch {}
        if ($stop) { break }
        $it = $items.GetNext()
      }
    }
    foreach ($sub in $f.Folders) { if ($script:voll) { break }; Walk $sub ($path + "/" + [string]$sub.Name) }
  }
  foreach ($sub in $store.GetRootFolder().Folders) { if ($script:voll) { break }; Walk $sub ([string]$sub.Name) }
  $out.mails = $list
  $out.anzahl = $script:n
  $out.mehr = $script:voll
  $out.ok = $true
} catch { $out.error = $_.Exception.Message }
finally {
  # detach a file attached by this run - also after an error
  if ($added -and $store) {
    try { $ns.RemoveStore($store.GetRootFolder()); if ($inp.marker) { Remove-Item -LiteralPath ([string]$inp.marker) -ErrorAction SilentlyContinue } } catch {}
  }
}
Save-Out $args[1]
""",
    "abhaengen": r"""
try {
  $ol = Get-OL
  $ns = $ol.GetNamespace("MAPI")
  $n = 0
  foreach ($p in @($inp.pfade)) {
    foreach ($s in @($ns.Stores)) { $fp = ""; try { $fp = [string]$s.FilePath } catch {}; if ($fp -and $fp -ieq [string]$p) { try { $ns.RemoveStore($s.GetRootFolder()); $n++ } catch {} } }
  }
  $out.entfernt = $n
  $out.ok = $true
} catch { $out.error = $_.Exception.Message }
Save-Out $args[1]
""",
}


def mo_ps(name, data, timeout=180):
    """run one Outlook PowerShell action -> dict (raises ValueError with a German message)"""
    exe = os.environ.get("PA_MO_PS")          # tests only: replacement for powershell.exe
    if not exe:
        if not sys.platform.startswith("win"):
            raise ValueError("Die Outlook-Schnittstelle gibt es nur unter Windows.")
        exe = shutil.which("powershell.exe") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    tmp = tempfile.mkdtemp(prefix="pa_outlook_")
    try:
        sp, ip, op = os.path.join(tmp, f"{name}.ps1"), os.path.join(tmp, "in.json"), os.path.join(tmp, "out.json")
        with open(sp, "w", encoding="utf-8-sig") as f:
            f.write(M99C_PS_HEAD + M99C_PS[name])
        d = dict(data or {})
        d.setdefault("dir", tmp)
        with open(ip, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        args = [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", sp, ip, op]
        kw = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "timeout": timeout}
        if sys.platform.startswith("win"):
            kw["creationflags"] = 0x08000000
        try:
            pr = subprocess.run(args, **kw)
        except subprocess.TimeoutExpired:
            raise ValueError("Outlook antwortet nicht (Zeitüberschreitung). Hängt in Outlook ein Dialog oder eine Sicherheitsabfrage?")
        except OSError as e:
            raise ValueError(f"Windows PowerShell lässt sich nicht starten: {e}")
        if not os.path.isfile(op):
            err = (pr.stderr or b"").decode("utf-8", "replace").strip()[:300]
            raise ValueError("Outlook-Schnittstelle ohne Antwort" + (f": {err}" if err else "."))
        r = json.loads(open(op, encoding="utf-8-sig").read() or "{}")
        if not r.get("ok"):
            raise ValueError(mo_fehlertext(r.get("error") or "unbekannter Fehler"))
        r["_tmp"] = tmp
        return r
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def mo_fehlertext(e):
    e = str(e or "")
    if "OUTLOOK_FEHLT" in e or "80040154" in e:
        return ("Klassisches Outlook nicht gefunden. Das „Neue Outlook“ und Outlook im Browser haben keine Schnittstelle für Programme – "
                "in Outlook oben rechts den Schalter „Neues Outlook“ ausschalten (bzw. Outlook aus Microsoft 365/Office installieren).")
    if "OST_FREMD" in e:
        return ("Diese .ost-Datei gehört zu keinem Konto im Outlook auf diesem PC (z. B. von einem anderen PC oder einem gelöschten Konto). "
                "Eine .ost lässt sich nur über das Outlook lesen, zu dem sie gehört – dort das Konto einrichten oder eine .pst exportieren.")
    if "PST_FEHLER" in e:
        return ("Outlook konnte die Datendatei nicht öffnen – ist sie beschädigt, mit Passwort geschützt oder eine .ost-Datei? "
                "Outlook meldet: " + e.split(":", 1)[-1].strip()[:200])
    if "KONTO_FEHLT" in e:
        return f"Das Outlook-Konto „{e.split(':', 1)[-1].strip()}“ gibt es in Outlook nicht (mehr) – unter Einstellungen → Outlook ein Konto wählen."
    if "80080005" in e:
        return "Outlook läuft mit anderen Rechten (z. B. „Als Administrator“) als dieses Programm – Outlook normal starten."
    if "ObjectNotFound" in e or "konnte nicht gefunden" in e.lower() or "not be found" in e.lower():
        return "Den gewählten Outlook-Ordner gibt es nicht – unter Einstellungen → Outlook neu wählen."
    return "Outlook meldet: " + e[:300]


def mo_cfg():
    s = get_settings()
    return {"versand": bool(s.get("mo_versand")), "anzeigen": bool(s.get("mo_anzeigen")), "konto": str(s.get("mo_konto") or ""),
            "abruf": bool(s.get("mo_abruf")), "konto_abruf": str(s.get("mo_konto_abruf") or ""), "ordner": str(s.get("mo_ordner") or ""),
            "interval": int(float(s.get("mo_interval") or 0)), "tage": int(float(s.get("mo_tage") or 60) or 60),
            "status": s.get("mo_status") or {}, "versand_status": s.get("mo_versand_status") or {}}


def mo_info():
    r = mo_ps("info", {}, timeout=90)
    shutil.rmtree(r.pop("_tmp", ""), ignore_errors=True)
    return {"ok": True, "version": r.get("version") or "", "konten": r.get("konten") or []}


def mo_view():
    return dict(mo_cfg(), ok=True, windows=sys.platform.startswith("win") or bool(os.environ.get("PA_MO_PS")))


def mo_save(d):
    for k, sk in (("versand", "mo_versand"), ("anzeigen", "mo_anzeigen"), ("abruf", "mo_abruf")):
        if k in d:
            set_setting(sk, bool(d[k]))
    old = mo_cfg()
    for k, sk in (("konto", "mo_konto"), ("konto_abruf", "mo_konto_abruf"), ("ordner", "mo_ordner")):
        if k in d:
            set_setting(sk, str(d[k] or "").strip())
    for k, sk in (("interval", "mo_interval"), ("tage", "mo_tage")):
        if k in d:
            try:
                set_setting(sk, max(0, int(float(d[k] or 0))))
            except Exception:
                pass
    new = mo_cfg()
    if (old["konto_abruf"], old["ordner"]) != (new["konto_abruf"], new["ordner"]):
        set_setting("mo_state", {})          # other folder -> start again from "last X days"
    return mo_view()


# ============================================================ 1. sending through Outlook
def mo_send(to, cc, subject, body, attachments, anzeigen=None, konto=None, log=None):
    c = mo_cfg()
    tmp = tempfile.mkdtemp(prefix="pa_outlook_att_")
    try:
        files = []
        for fn, data in attachments or []:
            p = os.path.join(tmp, safe_name(fn) or "anhang.pdf")
            write_file(p, data)
            files.append(p)
        semi = lambda v: "; ".join(a.strip() for a in re.split(r"[;,]", str(v or "")) if a.strip())
        r = mo_ps("senden", {"to": semi(to), "cc": semi(cc), "subject": subject or "", "body": body or "", "files": files,
                             "konto": c["konto"] if konto is None else konto, "anzeigen": c["anzeigen"] if anzeigen is None else bool(anzeigen)})
        shutil.rmtree(r.pop("_tmp", ""), ignore_errors=True)
        if log is not None:
            log.append("✓ " + ("Im Outlook-Fenster geöffnet – dort auf Senden klicken" if r.get("angezeigt") else "Über Outlook gesendet") + f" an {semi(to)}")
        set_setting("mo_versand_status", {"zeit": now_iso(), "ok": True, "an": semi(to), "angezeigt": bool(r.get("angezeigt"))})
        set_setting("mail_status", {"zeit": now_iso(), "ok": True, "an": semi(to), "weg": "Outlook"})
        return True
    finally:
        # Outlook copies the attachments when they are added; give a displayed mail a moment, then clean up
        _t = threading.Timer(120, lambda: shutil.rmtree(tmp, ignore_errors=True))
        _t.daemon = True
        _t.start()


_m99c_send_mail = chain_inner("send_mail", "m98_mail")   # v3.0.0: the level below this module (was: the function before the wrapper)
@chain_step("send_mail", "m98_mail")
def _m99c_step_send_mail(_next, to, cc, subject, body, attachments, over=None, log=None):
    if over is None and get_settings().get("mo_versand"):
        return mo_send(to, cc, subject, body, attachments, log=log)
    return _next(to, cc, subject, body, attachments, over=over, log=log)


@chain_step("mail_configured", "m98_mail")
def _m99c_step_mail_configured(_next, s=None):
    s = s or get_settings()
    return True if s.get("mo_versand") else _next(s)


def mo_test(d):
    c = mo_cfg()
    to = str(d.get("to") or c["konto"] or get_settings().get("smtp_user") or "").strip()
    if "@" not in to:
        raise ValueError("Bitte eine Empfänger-Adresse für die Test-Mail angeben.")
    lg = []
    mo_send(to, "", "Test - Pfeiffer-Audio Rechnung (Outlook)", "Der Versand über Outlook funktioniert.\n", [],
            anzeigen=bool(d.get("anzeigen", c["anzeigen"])), konto=d.get("konto", c["konto"]), log=lg)
    return {"ok": True, "schritte": lg, "an": to}


# ============================================================ 2. fetching from Outlook
def mo_fetch():
    if not M99C_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Outlook-Abruf läuft bereits."}
    st = {"zeit": now_iso(), "ok": False, "neu": 0, "doppelt": 0, "fehler": 0, "text": ""}
    tmp = ""
    try:
        c = mo_cfg()
        state = get_settings().get("mo_state") or {}
        if not isinstance(state, dict):
            state = {}
        seit = state.get("seit") or (datetime.datetime.now() - datetime.timedelta(days=max(1, c["tage"]))).strftime("%Y-%m-%d %H:%M:%S")
        ids = list(state.get("ids") or [])
        fehl = {k: v for k, v in (state.get("fehl") or {}).items() if isinstance(v, list) and len(v) == 2}   # id -> [zeit, tries]
        known = ids[-3000:] + [k for k, v in fehl.items() if v[1] >= 3]
        r = mo_ps("abrufen", {"konto": c["konto_abruf"], "ordner": c["ordner"], "seit": seit, "bekannt": known, "max": M99C_MAX}, timeout=600)
        tmp = r.pop("_tmp", "")
        newest = ""
        mails = r.get("mails") or []
        if isinstance(mails, dict):
            mails = [mails]
        for m in mails:
            ok_ = False
            try:
                raw = open(m["file"], "rb").read()
                res = mail_import_raw(raw, ".msg", "Outlook", r.get("ordner") or "Outlook")
                st[res["status"]] = st.get(res["status"], 0) + 1
                ok_ = res["status"] != "fehler"
            except Exception:
                traceback.print_exc()
                st["fehler"] += 1
            if ok_:
                ids.append(m["id"])
                fehl.pop(m["id"], None)
            else:
                fehl[m["id"]] = [m.get("zeit") or "", (fehl.get(m["id"]) or ["", 0])[1] + 1]
            newest = max(newest, m.get("zeit") or "")
        st["fehler"] += int(r.get("uebersprungen") or 0)
        if not r.get("mehr") and newest:
            # move the window forward (2 days overlap - the EntryID list prevents duplicates), but not past failed mails
            nd = (datetime.datetime.strptime(newest, "%Y-%m-%d %H:%M:%S") - datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
            pend = [v[0] for v in fehl.values() if v[1] < 3 and v[0]]
            seit = max(seit, min([nd] + pend))
        set_setting("mo_state", {"seit": seit, "ids": ids[-3000:], "fehl": {k: v for k, v in fehl.items() if v[1] < 3 or v[0] >= seit}})
        st["ok"] = True
        st["text"] = f"{st['neu']} neu, {st['doppelt']} schon vorhanden" + (f", {st['fehler']} Fehler" if st["fehler"] else "") + \
            (" – weitere beim nächsten Abruf" if r.get("mehr") else "") + (f" ({r.get('ordner')})" if r.get("ordner") else "")
    except ValueError as e:
        st["text"] = str(e)
    except Exception as e:
        traceback.print_exc()
        st["text"] = f"Fehler beim Outlook-Abruf: {e}"
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        set_setting("mo_status", st)
        M99C_LOCK.release()
    return dict(st, error=None if st["ok"] else st["text"])


def mo_loop():
    time.sleep(40)
    while True:
        try:
            c = mo_cfg()
            if c["abruf"] and c["interval"] > 0:
                last = (c["status"] or {}).get("zeit") or ""
                due = True
                if last:
                    try:
                        due = (datetime.datetime.now() - datetime.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() >= c["interval"] * 60
                    except Exception:
                        due = True
                if due:
                    mo_fetch()
        except Exception:
            traceback.print_exc()
        time.sleep(30)


if not M99C_TEST:
    HOOK_START.append(mo_loop)


# ============================================================ 3. Outlook data files (.pst / .ost) - remembered, updated at every start
# A source = one data file on this PC: {"id", "pfad", "ziel", "name", "seit", "ids", "status"}.
#  - .ost belongs to an account in this Outlook - read through that account (store found by file path/name).
#  - .pst is attached for reading and detached again (if it is not open in Outlook anyway).
#  - first run: ALL mails; later runs: only mails received since the last run (2 days overlap, EntryIDs prevent doubles).
#  - The folder of every source is remembered too; new .pst files that appear there are picked up at the next start.
#  - v2.6.3: export/import in chunks of M99C_CHUNK mails; after each chunk the progress is saved (EntryIDs in table
#    m99c_seen), so a killed run / program end continues there instead of starting again with ALL mails.
#    A .pst attached by a run that was killed is detached at the next run (marker file in _outlook_angehaengt).
M99C_JOBS = {}
M99C_SYNC = threading.Lock()
M99C_ALT = "1900-01-01 00:00:00"
M99C_CHUNK = 2000
M99C_MAX_RUNDEN = 500
M99C_MARK = "_outlook_angehaengt"


def _mo_schema():
    x("CREATE TABLE IF NOT EXISTS m99c_seen (quelle TEXT, eid TEXT, zeit TEXT, PRIMARY KEY (quelle, eid))")


HOOK_SCHEMA.append(_mo_schema)
try:
    M89_SKIP.add("m99c_seen")        # progress list, never part of an undo step
except NameError:
    pass


def mo_abhaengen_reste():
    """data files attached by a run that was killed (marker left behind) are detached from Outlook again"""
    d = os.path.join(DATA_DIR, M99C_MARK)
    if not os.path.isdir(d):
        return 0
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".txt")]
    pfade = []
    for f in files:
        try:
            p_ = open(f, encoding="utf-8-sig").read().strip()
            if p_:
                pfade.append(p_)
        except Exception:
            pass
    if pfade:
        try:
            r = mo_ps("abhaengen", {"pfade": pfade}, timeout=120)
            shutil.rmtree(r.pop("_tmp", ""), ignore_errors=True)
        except ValueError:
            traceback.print_exc()
            return 0                         # markers stay for the next try
    for f in files:
        _mo_rm(f)
    return len(pfade)


def _mo_rm(p):
    try:
        if p:
            os.remove(p)
    except Exception:
        pass


def _mo_key(p):
    return os.path.normcase(os.path.normpath(str(p or "")))


def mo_quellen():
    q_ = get_settings().get("mo_quellen")
    return q_ if isinstance(q_, list) else []


def mo_ordner():
    o = get_settings().get("mo_ordner_quellen")
    return o if isinstance(o, list) else []


def _mo_q_save(lst):
    set_setting("mo_quellen", lst)


def mo_quelle_add(pfad, ziel, ordner_merken=True):
    if ziel not in ("geschaeft", "privat"):
        raise ValueError("Unbekanntes Ziel.")
    pfad = os.path.abspath(pfad)
    ext = os.path.splitext(pfad.lower())[1]
    if ext not in (".pst", ".ost"):
        raise ValueError(f"„{os.path.basename(pfad)}“ ist keine Outlook-Datendatei (.pst/.ost).")
    lst = mo_quellen()
    src = next((x for x in lst if _mo_key(x.get("pfad")) == _mo_key(pfad)), None)
    if src:
        if src.get("ziel") != ziel:
            src["ziel"] = ziel
            src["seit"], src["ids_zeit"], src["fehl"] = M99C_ALT, [], {}     # other target -> read everything again into the new place
    else:
        src = {"id": uuid.uuid4().hex[:10], "pfad": pfad, "ziel": ziel, "name": os.path.basename(pfad), "seit": M99C_ALT, "ids_zeit": [],
               "status": {}, "angelegt": now_iso()}
        lst.append(src)
    _mo_q_save(lst)
    if ordner_merken:
        od = os.path.dirname(pfad)
        ol = mo_ordner()
        if not any(_mo_key(o.get("ordner")) == _mo_key(od) for o in ol):
            ol.append({"ordner": od, "ziel": ziel})
            set_setting("mo_ordner_quellen", ol)
    return src


def _mo_suchorte():
    home = os.path.expanduser("~")
    la = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    docs = os.path.join(home, "Documents")
    try:
        docs = downloads_dir().replace("Downloads", "Documents") if not os.path.isdir(docs) else docs
    except Exception:
        pass
    out = [os.path.join(la, "Microsoft", "Outlook"), os.path.join(docs, "Outlook-Dateien"), os.path.join(docs, "Outlook Files"), docs,
           os.path.join(home, "Desktop"), os.path.join(home, "Downloads")] + [o.get("ordner") for o in mo_ordner()]
    seen, res = set(), []
    for d in out:
        k = _mo_key(d)
        if d and k not in seen and os.path.isdir(d):
            seen.add(k)
            res.append(d)
    return res


def mo_finden(name, groesse=None):
    """dropped file (only its name is known) -> full path: Outlook's own list of data files first, then the usual folders"""
    name = os.path.basename(str(name or ""))
    if not name:
        return ""
    try:
        r = mo_ps("stores", {}, timeout=90)
        shutil.rmtree(r.pop("_tmp", ""), ignore_errors=True)
        for st in r.get("stores") or []:
            fp = str(st.get("pfad") or "")
            if fp and os.path.basename(fp).lower() == name.lower():
                return fp
    except ValueError:
        pass
    hits = []
    for d in _mo_suchorte():
        for root, dirs, files in os.walk(d):
            if root[len(d):].count(os.sep) >= 2:
                dirs[:] = []
            for f in files:
                if f.lower() == name.lower():
                    hits.append(os.path.join(root, f))
    if groesse and len(hits) > 1:
        hits.sort(key=lambda h: abs(os.path.getsize(h) - int(groesse)) if os.path.exists(h) else 1 << 62)
    return hits[0] if hits else ""


def _mo_job(titel, n):
    tok = uuid.uuid4().hex[:12]
    job = {"token": tok, "datei": titel, "state": "laeuft", "phase": "export", "exportiert": 0, "gesamt": 0, "fertig": 0,
           "neu": 0, "doppelt": 0, "fehler": 0, "text": "", "start": time.time(), "quellen": n, "nr": 0, "aktuell": "", "ergebnisse": []}
    M99C_JOBS[tok] = job
    return job


def mo_sync_start(ids=None, grund="Knopf"):
    """update remembered sources (all, or the given ids) in the background -> job"""
    srcs = [x for x in mo_quellen() if not ids or x.get("id") in ids]
    if not srcs:
        raise ValueError("Keine gemerkten Outlook-Dateien.")
    job = _mo_job(", ".join(x["name"] for x in srcs)[:200], len(srcs))
    job["grund"] = grund
    threading.Thread(target=_mo_sync_run, args=(job, [x["id"] for x in srcs]), daemon=True).start()
    return dict(job, ok=True)


def _mo_src_save(src):
    """write the state of one remembered source back (target changed meanwhile: keep its reset)"""
    lst = mo_quellen()
    for x in lst:
        if x.get("id") == src.get("id"):
            if x.get("ziel") != src.get("ziel"):
                x["status"] = src.get("status")
            else:
                x.update({k: src.get(k) for k in ("ids_zeit", "fehl", "seit", "status", "outlook_name")})
    _mo_q_save(lst)


def _mo_sync_one(job, src, save=None):
    """one data file -> export new mails through Outlook (in chunks) -> import. Updates src (seit, ids_zeit, status) in place;
    save(src) is called after every chunk (progress kept when the program ends in the middle)."""
    work = os.path.join(DATA_DIR, "_outlook_import", job["token"] + "_" + str(src.get("id") or "x"))
    mdir = os.path.join(work, "msg")
    os.makedirs(mdir, exist_ok=True)
    done = threading.Event()
    base = [job["exportiert"]]

    def count():
        while not done.wait(1.5):
            try:
                job["exportiert"] = base[0] + len(os.listdir(mdir))
            except Exception:
                pass
    threading.Thread(target=count, daemon=True).start()
    res = {"name": src["name"], "neu": 0, "doppelt": 0, "fehler": 0, "ok": False, "text": ""}
    sk = str(src.get("id") or "x") if save else ""          # progress table only for remembered sources
    known = [x for x in (src.get("ids_zeit") or []) if isinstance(x, list) and len(x) == 2]
    if sk:
        have = {x[0] for x in known}
        known += [[r_["eid"], r_["zeit"] or ""] for r_ in q("SELECT eid, zeit FROM m99c_seen WHERE quelle=?", (sk,)) if r_["eid"] not in have]
    fehl = {k: v for k, v in (src.get("fehl") or {}).items() if isinstance(v, list) and len(v) == 2}   # id -> [zeit, tries]
    mark_dir = os.path.join(DATA_DIR, M99C_MARK)
    os.makedirs(mark_dir, exist_ok=True)
    try:
        budget = [10]
        quelle = f"Outlook-Datei {src['name']}"[:200]
        runde = 0
        while True:
            runde += 1
            job["phase"] = "export"
            r = mo_ps("sync", {"pfad": src["pfad"], "seit": src.get("seit") or M99C_ALT,
                               "bekannt": [x[0] for x in known] + [k for k, v in fehl.items() if v[1] >= 3], "dir": mdir,
                               "max": M99C_CHUNK, "marker": os.path.join(mark_dir, f"{job['token']}_{sk or 'tmp'}.txt")},
                      timeout=4 * 3600)
            shutil.rmtree(r.pop("_tmp", "") or "", ignore_errors=True)
            mails = r.get("mails") or []
            if isinstance(mails, dict):
                mails = [mails]
            job["phase"] = "import"
            job["exportiert"] = base[0] + len(mails)
            job["gesamt"] += len(mails)
            neu_ids = []
            for m in mails:
                try:
                    raw = open(m["file"], "rb").read()
                    if src["ziel"] == "privat":
                        rr = mp_import_raw(raw, quelle, m.get("ordner") or "", ".msg")
                    else:
                        rr = mail_import_raw(raw, ".msg", quelle, m.get("ordner") or "", budget)
                    st_ = rr.get("status") or "fehler"
                except Exception:
                    traceback.print_exc()
                    st_ = "fehler"
                res[st_] = res.get(st_, 0) + 1
                job[st_] = job.get(st_, 0) + 1
                if st_ != "fehler":
                    e_ = [str(m.get("id") or ""), str(m.get("zeit") or "")]
                    known.append(e_)
                    neu_ids.append(e_)
                    fehl.pop(e_[0], None)
                else:
                    k_ = str(m.get("id") or "")
                    fehl[k_] = [str(m.get("zeit") or ""), (fehl.get(k_) or ["", 0])[1] + 1]
                job["fertig"] += 1
                _mo_rm(m.get("file"))
            base[0] = job["exportiert"]
            if r.get("name"):
                src["outlook_name"] = r["name"]
            if not r.get("mehr") or runde >= M99C_MAX_RUNDEN:
                break
            # chunk finished, more to come: keep the progress (window stays, EntryIDs in m99c_seen)
            if sk:
                for k in range(0, len(neu_ids), 300):     # 300 rows x 3 values stay below the SQLite variable limit
                    part = neu_ids[k:k + 300]
                    x("INSERT OR IGNORE INTO m99c_seen (quelle, eid, zeit) VALUES " + ",".join("(?,?,?)" for _ in part),
                      tuple(v for e_ in part for v in (sk, e_[0], e_[1])))
                src["fehl"] = fehl
                src["status"] = {"zeit": now_iso(), "ok": True, "text": f"läuft: {res['neu']} neu, {res['doppelt']} schon vorhanden"}
                save(src)
        # from now on only mails of the last 2 days are looked at again (EntryIDs of those days prevent doubles)
        cut = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        # failed mails (max. 3 tries) keep the window open so they are exported again next time
        pend = [v[0] for v in fehl.values() if v[1] < 3 and v[0]]
        seit_neu = min([cut] + pend)
        src["ids_zeit"] = [x for x in known if x[1] >= seit_neu][-20000:]
        src["fehl"] = {k: v for k, v in fehl.items() if v[1] < 3 or v[0] >= seit_neu}
        src["seit"] = seit_neu
        if sk:
            x("DELETE FROM m99c_seen WHERE quelle=?", (sk,))
        res["ok"] = True
        res["text"] = f"{res['neu']} neu, {res['doppelt']} schon vorhanden" + (f", {res['fehler']} Fehler" if res["fehler"] else "")
    except ValueError as e:
        res["text"] = str(e)
    except Exception as e:
        traceback.print_exc()
        res["text"] = f"Fehler: {e}"
    finally:
        done.set()
        shutil.rmtree(work, ignore_errors=True)
    src["status"] = {"zeit": now_iso(), "ok": res["ok"], "text": res["text"]}
    return res


def _mo_sync_run(job, ids, temp_src=None):
    job["phase"] = "wartet"                  # one Outlook run at a time - later ones wait in line
    with M99C_SYNC:
        job["start"] = time.time()
        try:
            try:
                mo_abhaengen_reste()
            except Exception:
                traceback.print_exc()
            todo = [temp_src] if temp_src else ids
            for nr, sid in enumerate(todo, 1):
                src = temp_src if temp_src else next((x for x in mo_quellen() if x.get("id") == sid), None)
                if not src:
                    continue
                job.update({"nr": nr, "aktuell": src["name"]})
                if src["pfad"].lower().endswith(".pst") and not os.path.isfile(src["pfad"]):
                    res = {"name": src["name"], "ok": False, "text": "Datei nicht mehr da: " + src["pfad"]}
                    src["status"] = {"zeit": now_iso(), "ok": False, "text": res["text"]}
                else:
                    res = _mo_sync_one(job, src, None if temp_src else _mo_src_save)
                if not temp_src:
                    _mo_src_save(src)
                job["ergebnisse"].append(res)
            bad = [r_ for r_ in job["ergebnisse"] if not r_.get("ok")]
            job["state"] = "fehler" if bad and len(bad) == len(job["ergebnisse"]) else "fertig"
            job["text"] = f"{job['neu']} neu, {job['doppelt']} schon vorhanden" + (f", {job['fehler']} Fehler" if job["fehler"] else "") + \
                ("; " + "; ".join(f"{r_['name']}: {r_['text']}" for r_ in bad) if bad else "")
            if job["state"] == "fehler" and len(bad) == 1:
                job["text"] = bad[0]["text"]
        except Exception as e:
            traceback.print_exc()
            job["state"], job["text"] = "fehler", f"Fehler: {e}"
        finally:
            job["sekunden"] = int(time.time() - job["start"])
            if temp_src:
                _mo_rm(temp_src.get("pfad"))
                shutil.rmtree(os.path.dirname(temp_src.get("pfad") or ""), ignore_errors=True)
            else:
                set_setting("mo_sync_status", {"zeit": now_iso(), "ok": job["state"] == "fertig", "text": job["text"], "grund": job.get("grund", "")})


def mo_datei(d):
    """a .pst/.ost was chosen or dropped: remember it (and its folder) and read it now"""
    ziel = str(d.get("ziel") or "")
    pfad = os.path.normpath(str(d.get("pfad") or "")) if d.get("pfad") else ""
    if pfad:
        if pfad not in globals().get("PICKED", set()):
            raise ValueError("Bitte die Outlook-Datei über den Knopf „Outlook-Datei“ auswählen.")
    else:
        name = os.path.basename(str(d.get("name") or ""))
        if not name.lower().endswith((".pst", ".ost")):
            raise ValueError(f"„{name}“ ist keine Outlook-Datendatei (.pst/.ost).")
        pfad = mo_finden(name, d.get("groesse"))
        if not pfad:
            return {"ok": False, "nicht_gefunden": True, "ost": name.lower().endswith(".ost"),
                    "error": (f"„{name}“ wurde weder in Outlook noch in den üblichen Ordnern gefunden. Bitte über den Knopf „Outlook-Datei“ auswählen – "
                              "dann merkt sich das Programm den Ort." if name.lower().endswith(".ost") else "")}
    src = mo_quelle_add(pfad, ziel)
    job = mo_sync_start([src["id"]], "Datei eingefügt")
    return dict(job, quelle=src["pfad"], ordner=os.path.dirname(src["pfad"]))


def mo_pst_upload_start(tmp, name, ziel):
    """fallback: .pst dropped whose location is unknown -> read the uploaded copy once (not remembered)"""
    if not name.lower().endswith(".pst"):
        _mo_rm(tmp)
        raise ValueError(f"„{name}“ ist keine .pst-Datei.")
    if ziel not in ("geschaeft", "privat"):
        _mo_rm(tmp)
        raise ValueError("Unbekanntes Ziel.")
    d = os.path.join(DATA_DIR, "_outlook_import", "upload_" + uuid.uuid4().hex[:8])
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "datei.pst")
    shutil.move(tmp, p)
    job = _mo_job(name, 1)
    job["grund"] = "einmalig"
    src = {"id": "tmp", "pfad": p, "ziel": ziel, "name": name, "seit": M99C_ALT, "ids_zeit": []}
    threading.Thread(target=_mo_sync_run, args=(job, [], src), daemon=True).start()
    return dict(job, ok=True)


def mo_job_status(tok):
    j = M99C_JOBS.get(str(tok or ""))
    if not j:
        raise ValueError("Kein Einlese-Auftrag gefunden.")
    return dict(j, ok=True, sekunden=int(time.time() - j["start"]) if j["state"] == "laeuft" else j.get("sekunden", 0))


def mo_quellen_view():
    s = get_settings()
    lst = []
    for x in mo_quellen():
        lst.append({"id": x["id"], "pfad": x["pfad"], "name": x["name"], "ziel": x["ziel"], "status": x.get("status") or {},
                    "da": os.path.isfile(x["pfad"]), "erstmal": (x.get("seit") or M99C_ALT) == M99C_ALT})
    run = next((dict(j, sekunden=int(time.time() - j["start"])) for j in M99C_JOBS.values() if j["state"] == "laeuft"), None)
    return {"ok": True, "quellen": lst, "ordner": mo_ordner(), "beim_start": s.get("mo_start_sync", True) is not False,
            "letzter": s.get("mo_sync_status") or {}, "laeuft": run}


def mo_quellen_save(d):
    if "beim_start" in d:
        set_setting("mo_start_sync", bool(d["beim_start"]))
    lst = mo_quellen()
    if d.get("entfernen"):
        lst = [x for x in lst if x.get("id") != d["entfernen"]]
        _mo_q_save(lst)
    if d.get("ziel_id") and d.get("ziel") in ("geschaeft", "privat"):
        for x in lst:
            if x.get("id") == d["ziel_id"] and x.get("ziel") != d["ziel"]:
                x["ziel"], x["seit"], x["ids_zeit"], x["fehl"] = d["ziel"], M99C_ALT, [], {}
        _mo_q_save(lst)
    if d.get("ordner_entfernen"):
        set_setting("mo_ordner_quellen", [o for o in mo_ordner() if _mo_key(o.get("ordner")) != _mo_key(d["ordner_entfernen"])])
    return mo_quellen_view()


def mo_beim_start():
    """program start: new .pst files in remembered folders are added, then every remembered file is updated"""
    shutil.rmtree(os.path.join(DATA_DIR, "_outlook_import"), ignore_errors=True)     # leftovers of an interrupted run
    time.sleep(45)
    try:
        with M99C_SYNC:
            mo_abhaengen_reste()          # .pst still attached by a run that was killed (also uploads)
    except Exception:
        traceback.print_exc()
    if get_settings().get("mo_start_sync", True) is False:
        return
    try:
        known = {_mo_key(x["pfad"]) for x in mo_quellen()}
        for o in mo_ordner():
            od = o.get("ordner") or ""
            if not os.path.isdir(od):
                continue
            for f in sorted(os.listdir(od)):
                fp = os.path.join(od, f)
                if f.lower().endswith(".pst") and os.path.isfile(fp) and _mo_key(fp) not in known:
                    mo_quelle_add(fp, o.get("ziel") or "geschaeft", ordner_merken=False)
                    known.add(_mo_key(fp))
                    print("INIT m99c: neue Outlook-Datei im gemerkten Ordner:", fp)
        if mo_quellen():
            print("INIT m99c: aktualisiere", len(mo_quellen()), "gemerkte Outlook-Datei(en)")
            mo_sync_start(None, "Programmstart")
    except Exception:
        traceback.print_exc()


if not M99C_TEST:
    HOOK_START.append(mo_beim_start)


def _mo_up(ziel):
    def h(handler, tmp, name):
        try:
            return handler._send(200, mo_pst_upload_start(tmp, name, ziel))
        except ValueError as e:
            return handler._send(200, {"ok": False, "error": str(e)})
    return h


HOOK_POST["/api/mo/datei"] = _wb_r(mo_datei)
HOOK_POST["/api/mo/quellen"] = _wb_r(mo_quellen_save)
HOOK_POST["/api/mo/quellen/sync"] = _wb_r(lambda d: mo_sync_start(d.get("ids") or None, "Knopf"))
HOOK_GET["/api/mo/quellen"] = lambda h, qs: h._send(200, mo_quellen_view())
HOOK_UPLOAD["/api/upload/pst_geschaeft"] = _mo_up("geschaeft")
HOOK_UPLOAD["/api/upload/pst_privat"] = _mo_up("privat")
HOOK_GET["/api/mo/pst/status"] = lambda h, qs: _wb_r(lambda d: mo_job_status(qs.get("token")))(h, {})


# ============================================================ routes / hooks
HOOK_GET["/api/mo/config"] = lambda h, qs: h._send(200, mo_view())
HOOK_GET["/api/mo/info"] = lambda h, qs: _wb_r(lambda d: mo_info())(h, {})
HOOK_POST["/api/mo/speichern"] = _wb_r(mo_save)
HOOK_POST["/api/mo/test"] = _wb_r(mo_test)
HOOK_POST["/api/mo/abrufen"] = _wb_r(lambda d: mo_fetch())


def _mo_boot(d):
    st = d.get("settings") or {}
    st.pop("mo_state", None)
    c = mo_cfg()
    d["mo"] = {"versand": c["versand"], "abruf": c["abruf"], "konto": c["konto"]}


HOOK_BOOT.append(_mo_boot)


def _mo_selftest():
    err = []
    try:
        if "OUTLOOK_FEHLT" in mo_fehlertext("OUTLOOK_FEHLT: x") or "Neues Outlook" not in mo_fehlertext("OUTLOOK_FEHLT: x"):
            err.append("m99c: Fehlertext Outlook fehlt")
        for k in ("info", "senden", "abrufen", "stores", "sync"):
            if "Save-Out" not in M99C_PS[k]:
                err.append(f"m99c: Skript {k} unvollständig")
        if send_mail.__name__ != "send_mail" or _m99c_send_mail is send_mail:
            err.append("m99c: Versand-Umleitung fehlt")
    except Exception as e:
        err.append(f"m99c Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_mo_selftest)
