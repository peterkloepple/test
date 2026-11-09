# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m33_fints (v2.3.1)
# Bankabruf per FinTS/HBCI (PIN/TAN, PSD2) mit python-fints.
# - Einstellungen-Reiter "Bankabruf" (UI: ui/m33_bank.js)
# - Abruf laeuft in einem eigenen Arbeits-Thread pro Sitzung (Token). Der
#   Thread haelt den FinTS-Dialog offen und wartet auf Antworten der UI
#   (TAN, Auswahl TAN-Verfahren/-Medium/Konto, "in der App bestaetigt").
#   Zwischen zwei Abrufen wird der Client-Zustand per client.deconstruct()
#   gespeichert (System-ID, BPD/UPD) -> die Bank erkennt das Programm wieder.
# - Neue Umsaetze: Duplikatpruefung, bank_suggest, sichere Zuordnungen werden
#   automatisch gebucht, der Rest wartet in fints_pending auf den Bank-Abgleich.
# fints wird NUR in Funktionen importiert (EXE evtl. noch ohne Bibliothek).
# v2.3.0: Bank aus der Bank-Bibliothek (m93) waehlbar; die von der Bank angebotenen
#   TAN-Verfahren und TAN-Medien werden gespeichert und sind in den Einstellungen
#   als Auswahl verfuegbar.
# Autor: T. Pfeiffer

FINTS_LIB_MSG = "Für den Bankabruf bitte einmal build_exe.bat ausführen (neue Bibliothek fints)."
FINTS_TIMEOUT = 300          # seconds the worker waits for a TAN / choice
FINTS_SESS = {}              # token -> _FtsSess
FINTS_LOCK = threading.Lock()
FINTS_FACTORY = None         # tests: fn(cfg, pin) -> client object (duck typed like FinTS3PinTanClient)
FINTS_SERVER_HINTS = [
    ("Sparkassen (Beispiel Region sn)", "https://banking-sn.s-fints-pt-sn.de/fints30"),
    ("Volks- und Raiffeisenbanken (Atruvia)", "https://fints1.atruvia.de/cgi-bin/hbciservlet"),
    ("Postbank", "https://hbci.postbank.de/banking/hbci.do"),
    ("DKB", "https://banking-dkb.s-fints-pt-dkb.de/fints30"),
    ("ING", "https://fints.ing.de/fints/"),
    ("comdirect", "https://fints.comdirect.de/fints"),
]


class _FtsAbbruch(Exception):
    pass


# ---------------- settings ----------------

def fints_cfg():
    s = get_settings()
    return {
        "blz": str(s.get("fints_blz") or "").replace(" ", ""),
        "user": str(s.get("fints_user") or "").strip(),
        "kunde": str(s.get("fints_kunde") or "").strip(),
        "url": str(s.get("fints_url") or "").strip(),
        "produkt": str(s.get("fints_produkt") or "").strip(),
        "pin_speichern": s.get("fints_pin_speichern", True) is not False,
        "pin_gespeichert": bool(s.get("fints_pin")),
        "konto": str(s.get("fints_konto") or ""),
        "konten": s.get("fints_konten") or [],
        "tan_mech": str(s.get("fints_tan_mech") or ""),
        "tan_medium": str(s.get("fints_tan_medium") or ""),
        "tan_optionen": s.get("fints_tan_optionen") or [],
        "tan_medien": s.get("fints_tan_medien") or [],
        "auto": s.get("fints_auto", True) is not False,
        "tage": int(s.get("fints_tage") or 90),
        "letzter": str(s.get("fints_letzter") or ""),
        "log": s.get("fints_log") or None,
    }


def fints_lib_ok():
    if FINTS_FACTORY:
        return True
    try:
        import fints.client  # noqa: F401
        return True
    except Exception:
        return False


def fints_config_view():
    c = fints_cfg()
    c["lib_ok"] = fints_lib_ok()
    c["server_hints"] = [{"label": a, "url": b} for a, b in FINTS_SERVER_HINTS]
    c["eingerichtet"] = bool(c["blz"] and c["user"] and c["url"] and c["produkt"])
    try:
        m93_sync_own()                                           # v2.3.1: take over the bank of the invoice IBAN
        c.update({k: v for k, v in fints_cfg().items() if k in ("blz", "url")})
        c["bank"] = m93_bank(c["blz"]) if c["blz"] else None     # m93 Bank-Bibliothek
        c["eigene"] = m93_eigene()
        c["eingerichtet"] = bool(c["blz"] and c["user"] and c["url"] and c["produkt"])
    except Exception:
        traceback.print_exc()
        c["bank"] = c.get("bank")
    return c


def fints_config_save(d):
    m = {"blz": "fints_blz", "user": "fints_user", "kunde": "fints_kunde", "url": "fints_url", "produkt": "fints_produkt",
         "konto": "fints_konto", "tan_mech": "fints_tan_mech", "tan_medium": "fints_tan_medium"}
    if d.get("blz") and not re.fullmatch(r"\d{8}", str(d.get("blz") or "").replace(" ", "")):
        raise ValueError("Die Bankleitzahl hat 8 Ziffern.")
    if d.get("url") and not str(d["url"]).strip().lower().startswith("https://"):
        raise ValueError("Die FinTS-Server-Adresse muss mit https:// beginnen.")
    for k, sk in m.items():
        if k in d:
            v = str(d.get(k) or "").strip()
            set_setting(sk, v.replace(" ", "") if k == "blz" else v)
    if "auto" in d:
        set_setting("fints_auto", bool(d["auto"]))
    if "tage" in d:
        set_setting("fints_tage", max(1, min(730, int(float(d.get("tage") or 90)))))
    if "pin_speichern" in d:
        set_setting("fints_pin_speichern", bool(d["pin_speichern"]))
        if not d["pin_speichern"]:
            set_setting("fints_pin", "")
    if d.get("pin_neu") and d.get("pin_speichern", True):
        set_setting("fints_pin", protect_secret(str(d["pin_neu"])))
    if d.get("pin_loeschen"):
        set_setting("fints_pin", "")
    if d.get("reset_bank"):
        # forget TAN choice and stored client state (e.g. after bank change)
        for k in ("fints_state", "fints_tan_mech", "fints_tan_medium", "fints_konten", "fints_konto", "fints_tan_optionen", "fints_tan_medien"):
            set_setting(k, [] if k in ("fints_konten", "fints_tan_optionen", "fints_tan_medien") else "")
    return fints_config_view()


# ---------------- helpers (testable, no fints import) ----------------

def _fx_norm(s):
    return re.sub(r"[^0-9a-zäöüß]", "", (s or "").lower())


def fints_tx_hash(datum, betrag, zweck, gegen, n=1):
    """Own duplicate hash for fetched transactions (prefix fts:)."""
    key = f"{(datum or '')[:10]}|{float(betrag or 0):.2f}|{_fx_norm(zweck)[:140]}|{_fx_norm(gegen)[:60]}|{int(n)}"
    return "fts:" + hashlib.sha1(key.encode("utf-8")).hexdigest()


def _fx_val(v, attr="amount"):
    if v is None:
        return None
    if hasattr(v, attr):
        v = getattr(v, attr)
    return v


def _fx_date(v):
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    s = str(v)
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else (iso_from_de(s) or "")


def fints_tx_dict(t):
    """mt940 / camt Transaction (or plain dict) -> dict like parse_bank_csv rows (without hash)."""
    data = getattr(t, "data", t) or {}
    dat = _fx_date(data.get("entry_date") or data.get("date"))
    amt = _fx_val(data.get("amount"))
    try:
        amt = round(float(amt), 2)
    except Exception:
        amt = 0.0
    name = str(data.get("applicant_name") or data.get("recipient_name") or "").strip()
    zweck = str(data.get("purpose") or "").strip()
    if not zweck:
        zweck = str(data.get("posting_text") or "").strip()
    zweck = re.sub(r"\s+", " ", zweck)
    iban = str(data.get("applicant_iban") or "").replace(" ", "")
    return {"datum": dat, "betrag": amt, "name": name[:120], "zweck": zweck[:400], "iban": iban}


def fints_prepare(raw):
    """Add hash, drop duplicates (own hash, pending, fuzzy against CSV imports). Returns (new, dup_count)."""
    out, cnt = [], {}
    for r in raw:
        if not r.get("datum"):
            continue
        gegen = r.get("iban") or r.get("name") or ""
        k = (r["datum"], f"{r['betrag']:.2f}", _fx_norm(r.get("zweck"))[:140], _fx_norm(gegen)[:60])
        cnt[k] = cnt.get(k, 0) + 1
        out.append(dict(r, hash=fints_tx_hash(r["datum"], r["betrag"], r.get("zweck"), gegen, cnt[k])))
    if not out:
        return [], 0
    known = {x_["hash"] for x_ in q("SELECT hash FROM bank_tx")} | {x_["hash"] for x_ in q("SELECT hash FROM fints_pending")}
    dmin = min(t["datum"] for t in out)
    # rows from CSV/PDF imports have other hashes -> fuzzy compare, each existing row matches once
    others = [dict(x_) for x_ in q("SELECT hash, datum, betrag, name, zweck, iban FROM bank_tx WHERE hash NOT LIKE 'fts:%' "
                                  "AND julianday(datum) >= julianday(?)-4", (dmin,))]
    new, dup = [], 0
    for t in out:
        if t["hash"] in known:
            dup += 1
            continue
        hit = None
        for o in others:
            if abs((o["betrag"] or 0) - t["betrag"]) > 0.005:
                continue
            od, td = d_iso(o["datum"]), d_iso(t["datum"])
            if not od or not td or abs((od - td).days) > 3:
                continue
            oz, tz = _fx_norm(o["zweck"]), _fx_norm(t["zweck"])
            same = (o.get("iban") and t.get("iban") and o["iban"].replace(" ", "").upper() == t["iban"].upper()) \
                or (oz and tz and (oz[:24] == tz[:24] or oz in tz or tz in oz)) \
                or (_fx_norm(o["name"]) and _fx_norm(o["name"]) == _fx_norm(t["name"]))
            if same:
                hit = o
                break
        if hit:
            others.remove(hit)
            dup += 1
            continue
        known.add(t["hash"])
        new.append(t)
    return new, dup


def fints_safe_invoice(t):
    """Exactly one open invoice with exact amount AND (invoice no. or customer name in text) -> invoice row."""
    if (t.get("betrag") or 0) <= 0:
        return None
    hits = [i for i in q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen'") if abs((i["summe"] or 0) - t["betrag"]) < 0.005]
    if len(hits) != 1:
        return None
    inv = hits[0]
    text = (t.get("name", "") + " " + t.get("zweck", "")).lower()
    blob = re.sub(r"[^0-9a-z]", "", text)
    nrn = re.sub(r"[^0-9a-z]", "", (inv["nr"] or "").lower())
    if nrn and len(nrn) >= 4 and nrn in blob:
        return inv
    # v2.0.6: legal forms (GmbH, AG ...) do not count as a name match; the distinctive name parts must all appear
    toks = [w for w in re.split(r"\W+", re.sub(r"\b(gmbh|co|kg|ag|ug|ohg|gbr|mbh|und|e\.?k\.?|gbr|ev|e\.v)\b", " ", inv_name(inv).lower())) if len(w) > 3]
    if toks and all(w in text for w in toks[:2]):
        return inv
    return None


def fints_import(raw, saldo=None, konto="", auto=None, quelle="Bankabruf (FinTS)"):
    """raw: list of dicts (datum, betrag, name, zweck, iban). Returns protocol dict."""
    if auto is None:
        auto = fints_cfg()["auto"]
    new, dup = fints_prepare(raw)
    res = {"abgerufen": len(raw), "doppelt": dup, "neu": len(new), "bezahlt": [], "fixkosten": [], "offen": 0, "saldo": None}
    sug = bank_suggest([dict(t) for t in new]) if new else []
    for t in sug:
        inv = fints_safe_invoice(t) if auto else None
        if inv:
            bank_apply([dict(t, aktion="paid", invoice_id=inv["id"])])
            res["bezahlt"].append({"nr": inv["nr"], "name": inv_name(inv), "betrag": t["betrag"], "datum": t["datum"]})
            continue
        if auto and t.get("fix_vormerk") and t.get("aktion") == "ausgabe":
            bank_apply([t])
            res["fixkosten"].append({"name": t.get("fix_name") or t["name"], "betrag": t["betrag"], "datum": t["datum"]})
            continue
        x("INSERT OR IGNORE INTO fints_pending (hash, datum, betrag, name, zweck, iban, created) VALUES (?,?,?,?,?,?,?)",
          (t["hash"], t["datum"], t["betrag"], t["name"], t["zweck"], t.get("iban", ""), now_iso()))
        res["offen"] += 1
    if saldo and saldo.get("saldo") is not None:
        res["saldo"] = store_saldo({"saldo": float(saldo["saldo"]), "datum": saldo.get("datum") or today()}, quelle)
    return res


def fints_pending_list():
    x("DELETE FROM fints_pending WHERE hash IN (SELECT hash FROM bank_tx)")
    rows = [dict(r) for r in q("SELECT hash, datum, betrag, name, zweck, iban FROM fints_pending ORDER BY datum, id")]
    for r in rows:
        r["name"], r["zweck"], r["iban"] = r["name"] or "", r["zweck"] or "", r["iban"] or ""
    return bank_suggest(rows) if rows else []


# ---------------- session / worker ----------------

class _FtsSess:
    def __init__(self, modus, cfg, pin, tage=None):
        self.token = uuid.uuid4().hex
        self.modus, self.cfg, self.pin, self.tage = modus, cfg, pin, tage
        self.state, self.frage, self.antwort = "running", None, None
        self.logs, self.ergebnis, self.error = [], None, ""
        self.cond = threading.Condition()
        self.t0 = self.touch = time.time()
        self.cancel = False

    def log(self, m):
        with self.cond:
            self.logs.append(time.strftime("%H:%M:%S") + "  " + m)
            self.cond.notify_all()

    def ask(self, frage, timeout=None):
        with self.cond:
            if self.cancel:
                raise _FtsAbbruch("Abgebrochen.")
            self.frage, self.state, self.antwort = frage, "frage", None
            self.cond.notify_all()
            end = time.time() + (timeout or FINTS_TIMEOUT)
            while self.antwort is None:
                rem = end - time.time()
                if rem <= 0:
                    self.frage, self.state = None, "running"
                    raise _FtsAbbruch("Zeitüberschreitung - keine Eingabe innerhalb von %d Minuten." % ((timeout or FINTS_TIMEOUT) // 60))
                self.cond.wait(rem)
            a, self.antwort = self.antwort, None
        if a.get("abbrechen"):
            raise _FtsAbbruch("Abgebrochen.")
        return a

    def answer(self, a):
        with self.cond:
            self.touch = time.time()
            if self.state != "frage":
                if a.get("abbrechen"):
                    self.cancel = True
                    return
                raise ValueError("Der Bankabruf erwartet gerade keine Eingabe.")
            self.antwort, self.frage, self.state = dict(a), None, "running"
            self.cond.notify_all()

    def finish(self, state, error="", ergebnis=None):
        with self.cond:
            self.state, self.error, self.frage = state, error, None
            if ergebnis is not None:
                self.ergebnis = ergebnis
            self.cond.notify_all()

    def wait(self, timeout=25.0):
        end = time.time() + timeout
        with self.cond:
            while self.state == "running":
                rem = end - time.time()
                if rem <= 0:
                    break
                self.cond.wait(min(rem, 1.0))

    def view(self):
        with self.cond:
            return {"ok": True, "token": self.token, "modus": self.modus, "state": self.state, "frage": self.frage,
                    "log": list(self.logs), "ergebnis": self.ergebnis, "error": self.error}


def _fts_is_tan(r):
    return r is not None and type(r).__name__ == "NeedTANResponse"


def _fts_strip_html(s):
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    import html as _html
    return _html.unescape(s).strip()


def fints_challenge(r):
    """NeedTANResponse -> dict for the UI (text, picture as data-uri, chipTAN start code)."""
    d = {"art": "tan", "decoupled": bool(getattr(r, "decoupled", False))}
    txt = getattr(r, "challenge_html", None) or getattr(r, "challenge", None) or ""
    d["text"] = _fts_strip_html(str(txt))
    m = getattr(r, "challenge_matrix", None)
    if m and isinstance(m, (tuple, list)) and len(m) == 2 and m[1]:
        mime = m[0] if isinstance(m[0], str) and m[0].startswith("image/") else "image/png"
        raw = m[1] if isinstance(m[1], (bytes, bytearray)) else str(m[1]).encode("latin-1", "replace")
        d["bild"] = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    hh = getattr(r, "challenge_hhduc", None)
    if hh:
        d["hhduc"] = str(hh)
    d["titel"] = "Freigabe in der Banking-App" if d["decoupled"] else "TAN eingeben"
    return d


def _fts_resolve(s, client, r):
    n = 0
    while _fts_is_tan(r):
        n += 1
        if n > 12:
            raise _FtsAbbruch("Die Bank fragt immer wieder nach einer Freigabe - Abruf beendet.")
        fr = fints_challenge(r)
        s.log("Bank verlangt Freigabe: " + ("bitte in der App bestätigen" if fr["decoupled"] else "TAN eingeben"))
        a = s.ask(fr)
        tan = "" if fr["decoupled"] else str(a.get("tan") or "").strip()
        if not fr["decoupled"] and not tan:
            raise _FtsAbbruch("Keine TAN eingegeben.")
        r = client.send_tan(r, tan)
    return r


def _fts_choose(s, titel, text, opts, saved=""):
    """opts: list of (id, label). Returns id."""
    ids = [o[0] for o in opts]
    if saved and saved in ids:
        return saved
    if len(opts) == 1:
        return opts[0][0]
    if not opts:
        return ""
    a = s.ask({"art": "wahl", "titel": titel, "text": text, "optionen": [{"id": i, "label": l} for i, l in opts]})
    w = str(a.get("wahl") or "")
    if w not in ids:
        raise _FtsAbbruch("Keine gültige Auswahl.")
    return w


def _fts_bootstrap(s, client, cfg):
    try:
        client.fetch_tan_mechanisms()
    except Exception as e:
        n_ = type(e).__name__
        if "PIN" in n_.upper() or "Connection" in n_ or "Auth" in n_:
            raise
        s.log("TAN-Verfahren konnten nicht vorab gelesen werden (%s) - weiter." % type(e).__name__)
    mechs = client.get_tan_mechanisms() or {}
    opts = [(str(k), "%s (%s)" % (getattr(v, "name", "") or k, k)) for k, v in mechs.items() if str(k) != "999"]
    if opts:
        set_setting("fints_tan_optionen", [{"id": i, "label": l} for i, l in opts])   # v2.3.0: selectable in settings
        w = _fts_choose(s, "TAN-Verfahren wählen", "Deine Bank bietet mehrere Freigabe-Verfahren an. Die Auswahl wird gespeichert.", opts, cfg["tan_mech"])
        if w:
            client.set_tan_mechanism(w)
            if w != cfg["tan_mech"]:
                set_setting("fints_tan_mech", w)
            s.log("TAN-Verfahren: " + dict(opts).get(w, w))
    try:
        need_medium = client.is_tan_media_required() and not getattr(client, "selected_tan_medium", None)
    except Exception:
        need_medium = False
    if need_medium:
        res = client.get_tan_media()
        media = list(res[1]) if res and len(res) > 1 and res[1] else []
        mo = [(str(getattr(m, "tan_medium_name", "") or ""), str(getattr(m, "tan_medium_name", "") or "")) for m in media if getattr(m, "tan_medium_name", None)]
        if mo:
            set_setting("fints_tan_medien", [{"id": i, "label": l} for i, l in mo])   # v2.3.0: selectable in settings
            w = _fts_choose(s, "TAN-Medium wählen", "Welches Gerät bzw. welche App soll die TAN liefern? Die Auswahl wird gespeichert.", mo, cfg["tan_medium"])
            client.set_tan_medium(next(m for m in media if str(getattr(m, "tan_medium_name", "")) == w))
            if w != cfg["tan_medium"]:
                set_setting("fints_tan_medium", w)
            s.log("TAN-Medium: " + w)


def _fts_make_client(cfg, pin):
    if FINTS_FACTORY:
        return FINTS_FACTORY(cfg, pin)
    try:
        from fints.client import FinTS3PinTanClient
    except ImportError:
        raise ValueError(FINTS_LIB_MSG)
    state = None
    try:
        st = get_settings().get("fints_state") or ""
        state = base64.b64decode(unprotect_secret(st)) if st else None
    except Exception:
        state = None
    kw = dict(product_id=cfg["produkt"], from_data=state)
    if cfg["kunde"]:
        kw["customer_id"] = cfg["kunde"]
    if cfg["tan_medium"]:
        kw["tan_medium"] = cfg["tan_medium"]
    return FinTS3PinTanClient(cfg["blz"], cfg["user"], pin, cfg["url"], **kw)


def _fts_errtext(e):
    n = type(e).__name__
    msg = str(e) or n
    if isinstance(e, ValueError):
        return msg
    if "PIN" in n.upper():
        set_setting("fints_pin", "")
        return ("Die Bank hat die Anmeldung abgelehnt (PIN oder Benutzerkennung falsch?). Die gespeicherte PIN wurde vorsichtshalber gelöscht. "
                "Achtung: nach mehreren Fehlversuchen sperrt die Bank den Zugang.")
    if "TemporaryAuth" in n or "locked" in msg.lower():
        return "Der Zugang ist bei der Bank vorübergehend gesperrt - bitte im Online-Banking bzw. bei der Bank entsperren."
    if "SCARequired" in n:
        return "Die Bank verlangt eine starke Kundenauthentifizierung, die nicht abgeschlossen wurde. Bitte erneut versuchen."
    if any(k in n for k in ("Connection", "Timeout", "SSL", "HTTP")) or "Max retries" in msg or "Name or service" in msg or "getaddrinfo" in msg:
        return "FinTS-Server nicht erreichbar - Internetverbindung und Server-Adresse prüfen (%s)." % n
    if "9010" in msg or "BPD" in msg:
        return "Die Bank hat die Verbindung abgelehnt - BLZ und FinTS-Server-Adresse prüfen."
    if "9078" in msg or "produkt" in msg.lower() or "product" in msg.lower():
        return "Die Bank akzeptiert die Produkt-Registrierungsnummer nicht - Eintrag prüfen (" + msg[:160] + ")."
    return "Bankabruf fehlgeschlagen: %s (%s)" % (msg[:240], n)


def _fts_account_dict(a):
    return {"iban": getattr(a, "iban", "") or "", "bic": getattr(a, "bic", "") or "", "nr": getattr(a, "accountnumber", "") or "",
            "unterkonto": getattr(a, "subaccount", "") or "", "blz": getattr(a, "blz", "") or ""}


def _fts_range(s):
    cfg = s.cfg
    bis = datetime.date.today()
    if s.tage:
        von = bis - datetime.timedelta(days=int(s.tage))
    elif cfg["letzter"] and d_iso(cfg["letzter"]):
        von = d_iso(cfg["letzter"]) - datetime.timedelta(days=30)     # v2.1.1: 30 days overlap (late card postings), duplicates are filtered
    else:
        von = bis - datetime.timedelta(days=cfg["tage"] or 90)
    return von, bis


def _fts_worker(s):
    cfg = s.cfg
    try:
        s.log("Verbinde mit " + cfg["url"])
        client = _fts_make_client(cfg, s.pin)
        _fts_bootstrap(s, client, cfg)
        res, bal, acc_d = None, None, None
        with client:
            itr = getattr(client, "init_tan_response", None)
            if _fts_is_tan(itr):
                s.log("Die Bank verlangt eine Freigabe für die Anmeldung.")
                _fts_resolve(s, client, itr)
            accs = _fts_resolve(s, client, client.get_sepa_accounts()) or []
            konten = [_fts_account_dict(a) for a in accs]
            set_setting("fints_konten", konten)
            s.log("%d Konto/Konten gefunden." % len(konten))
            if s.modus == "abruf":
                if not konten:
                    raise ValueError("Die Bank meldet keine Konten für diese Zugangsdaten.")
                w = _fts_choose(s, "Konto wählen", "Von welchem Konto sollen die Umsätze geholt werden? Die Auswahl wird gespeichert.",
                                [(k["iban"] or k["nr"], (k["iban"] or k["nr"]) + (" / Unterkonto " + k["unterkonto"] if k["unterkonto"] else "")) for k in konten],
                                cfg["konto"] or re.sub(r"\s", "", str(get_settings().get("iban") or "")).upper())   # v2.3.1: invoice IBAN preselected
                if w != cfg["konto"]:
                    set_setting("fints_konto", w)
                acc = next(a for a, k in zip(accs, konten) if (k["iban"] or k["nr"]) == w)
                acc_d = next(k for k in konten if (k["iban"] or k["nr"]) == w)
                von, bis = _fts_range(s)
                s.log("Umsätze %s bis %s werden abgerufen ..." % (de_date(von.isoformat()), de_date(bis.isoformat())))
                res = _fts_resolve(s, client, client.get_transactions(acc, von, bis)) or []
                try:
                    bal = _fts_resolve(s, client, client.get_balance(acc))
                except _FtsAbbruch:
                    raise
                except Exception as e_:
                    s.log("Kontostand nicht abrufbar (%s)." % type(e_).__name__)
        try:
            set_setting("fints_state", protect_secret(base64.b64encode(client.deconstruct(including_private=True)).decode("ascii")))
        except Exception:
            pass
        if s.modus != "abruf":
            s.finish("fertig", ergebnis={"konten": konten})
            return
        raw = [fints_tx_dict(t) for t in res]
        sal = None
        if bal is not None:
            amt = _fx_val(getattr(bal, "amount", None))
            if amt is not None:
                sal = {"saldo": float(amt), "datum": _fx_date(getattr(bal, "date", None)) or today()}
        s.log("%d Umsätze empfangen." % len(raw))
        erg = fints_import(raw, sal, acc_d["iban"] if acc_d else "")
        erg.update({"zeit": now_iso(), "ok": True, "von": von.isoformat(), "bis": bis.isoformat(), "konto": (acc_d or {}).get("iban", "")})
        set_setting("fints_letzter", bis.isoformat())
        s.log("Neu: %d · doppelt: %d · automatisch bezahlt: %d · Fixkosten: %d · zur Prüfung: %d"
              % (erg["neu"], erg["doppelt"], len(erg["bezahlt"]), len(erg["fixkosten"]), erg["offen"]))
        erg["log"] = list(s.logs)
        set_setting("fints_log", erg)
        s.finish("fertig", ergebnis=erg)
    except _FtsAbbruch as e:
        s.log(str(e))
        s.finish("abgebrochen", str(e))
    except Exception as e:
        if not isinstance(e, ValueError) and not any(k in type(e).__name__ for k in ("PIN", "Connection", "Auth")):
            traceback.print_exc()
        msg = _fts_errtext(e)
        s.log(msg)
        if s.modus == "abruf":
            set_setting("fints_log", {"zeit": now_iso(), "ok": False, "fehler": msg, "log": list(s.logs)})
        s.finish("fehler", msg)
    finally:
        s.pin = None


def fints_start(d):
    cfg = fints_cfg()
    if not fints_lib_ok():
        raise ValueError(FINTS_LIB_MSG)
    miss = [n for k, n in (("blz", "Bankleitzahl"), ("user", "Benutzerkennung"), ("url", "FinTS-Server"), ("produkt", "Produkt-Registrierungsnummer")) if not cfg[k]]
    if miss:
        raise ValueError("Bankabruf noch nicht eingerichtet - in Einstellungen → Bankabruf fehlt: " + ", ".join(miss) + ".")
    pin = str(d.get("pin") or "")
    if not pin and cfg["pin_gespeichert"]:
        try:
            pin = unprotect_secret(get_settings().get("fints_pin") or "")
        except Exception:
            pin = ""
    if not pin:
        return {"ok": True, "state": "pin", "frage": {"art": "pin"}}
    if d.get("pin") and d.get("pin_merken") and cfg["pin_speichern"]:
        set_setting("fints_pin", protect_secret(pin))
    with FINTS_LOCK:
        now = time.time()
        for k, v in list(FINTS_SESS.items()):
            if v.state in ("running", "frage") and now - v.touch < FINTS_TIMEOUT + 60:
                raise ValueError("Ein Bankabruf läuft bereits - bitte erst abschließen oder abbrechen.")
            if now - v.t0 > 1800:
                FINTS_SESS.pop(k, None)
        modus = "konten" if d.get("modus") == "konten" else "abruf"
        tage = int(d["tage"]) if d.get("tage") else None
        s = _FtsSess(modus, cfg, pin, tage)
        FINTS_SESS[s.token] = s
    threading.Thread(target=_fts_worker, args=(s,), daemon=True).start()
    s.wait(float(d.get("_wait") or 25))
    return s.view()


def _fts_get(token):
    s = FINTS_SESS.get(token or "")
    if not s:
        raise ValueError("Diese Bankabruf-Sitzung ist abgelaufen - bitte neu starten.")
    return s


def fints_answer(d):
    s = _fts_get(d.get("token"))
    s.answer({k: d.get(k) for k in ("tan", "wahl", "weiter", "abbrechen")})
    s.wait(float(d.get("_wait") or 25))
    return s.view()


def fints_status(token, wait=0.0):
    s = _fts_get(token)
    if wait:
        s.wait(wait)
    return s.view()


# ---------------- hooks ----------------

def _fts_schema():
    x("CREATE TABLE IF NOT EXISTS fints_pending (id INTEGER PRIMARY KEY, hash TEXT UNIQUE, datum TEXT, betrag REAL, name TEXT, "
      "zweck TEXT, iban TEXT, created TEXT)")


def _fts_boot(d):
    st = d.get("settings")
    if isinstance(st, dict):
        for k in ("fints_pin", "fints_state", "fints_log"):
            st.pop(k, None)
    try:
        c = fints_cfg()
        lg = c["log"] or {}
        d["fints"] = {"eingerichtet": bool(c["blz"] and c["user"] and c["url"] and c["produkt"]), "pin_gespeichert": c["pin_gespeichert"],
                      "letzter": c["letzter"], "pending": q("SELECT COUNT(*) n FROM fints_pending WHERE hash NOT IN (SELECT hash FROM bank_tx)", one=True)["n"],
                      "log_zeit": lg.get("zeit", ""), "log_ok": lg.get("ok", None)}
    except Exception:
        traceback.print_exc()


def _fts_selftest():
    errs = []
    a = fints_tx_hash("2026-01-05", -23.79, "Adobe Abo 123", "DE001", 1)
    if a != fints_tx_hash("2026-01-05", -23.790001, "ADOBE  abo-123", "de 001", 1):
        errs.append("FinTS: Duplikat-Hash nicht normalisiert")
    if a == fints_tx_hash("2026-01-05", -23.79, "Adobe Abo 123", "DE001", 2):
        errs.append("FinTS: Duplikat-Hash ignoriert laufende Nummer")
    t = fints_tx_dict({"date": datetime.date(2026, 2, 3), "amount": 12.5, "applicant_name": "Kunde", "purpose": "RE 2026-001"})
    if t["datum"] != "2026-02-03" or t["betrag"] != 12.5:
        errs.append("FinTS: Umsatz-Umwandlung fehlerhaft")
    if fints_challenge(type("NeedTANResponse", (), {"challenge": "Bitte<br>TAN", "decoupled": True})())["text"] != "Bitte\nTAN":
        errs.append("FinTS: TAN-Text-Aufbereitung fehlerhaft")
    try:
        new, dup = fints_prepare([dict(t), dict(t)])
        if len(new) != 2:
            errs.append("FinTS: gleiche Umsaetze am selben Tag werden faelschlich verworfen")
    except Exception as e:
        errs.append("FinTS: Duplikatpruefung Fehler " + str(e))
    return errs


def _fts_r(fn):
    return lambda h, d: h._send(200, fn(d))


HOOK_SCHEMA.append(_fts_schema)
HOOK_BOOT.append(_fts_boot)
HOOK_SELFTEST.append(_fts_selftest)
HOOK_GET["/api/fints/config"] = lambda h, qs: h._send(200, fints_config_view())
HOOK_GET["/api/fints/status"] = lambda h, qs: h._send(200, fints_status(qs.get("token"), float(qs.get("wait") or 0)))
HOOK_GET["/api/fints/pending"] = lambda h, qs: h._send(200, fints_pending_list())
HOOK_GET["/api/fints/log"] = lambda h, qs: h._send(200, fints_cfg()["log"] or {})
HOOK_POST["/api/fints/config/save"] = lambda h, d: h._send(200, dict(fints_config_save(d), ok=True))
HOOK_POST["/api/fints/start"] = _fts_r(fints_start)
HOOK_POST["/api/fints/answer"] = _fts_r(fints_answer)
HOOK_POST["/api/fints/pending/clear"] = lambda h, d: (x("DELETE FROM fints_pending"), h._send(200, {"ok": True}))[1]


FINTS_REG_URL = "https://www.hbci-zka.de/register/prod_register.htm"


def _fts_openurl(h, d):
    # only the registration page - no arbitrary URLs from the UI
    if not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        try:
            webbrowser.open(FINTS_REG_URL)
        except Exception:
            pass
    return h._send(200, {"ok": True, "url": FINTS_REG_URL})


HOOK_POST["/api/fints/openreg"] = _fts_openurl
