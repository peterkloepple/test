# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m38_psd2_bank (v2.0.9)
# Bankabruf fuer Banken ohne FinTS/HBCI - z. B. C24 Bank - ueber die
# PSD2-Schnittstelle der Bank. Vermittelt wird ueber den Kontoinformations-
# dienst Enable Banking (eigene App-Registrierung, eigene Konten).
# Ablauf: App-ID + privater Schluessel (.pem) eintragen -> Bank waehlen ->
# im Browser bei der Bank freigeben (bis zu 180 Tage) -> Umsaetze abrufen.
# Die Umsaetze laufen durch dieselbe Pruefung wie beim FinTS-Abruf
# (Dubletten, sichere Zuordnungen, Bank-Abgleich).
# Die JWT-Signatur (RS256) ist hier in reinem Python umgesetzt - keine
# zusaetzliche Bibliothek noetig.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import urllib.request
import urllib.parse
import urllib.error
import http.server

M38_VERSION = "1.0.0"
EB_API = "https://api.enablebanking.com"
EB_CB_PORT = 47823
EB_DEFAULT_REDIRECT = f"http://localhost:{EB_CB_PORT}/callback"
EB_DEFAULT_BANK = "C24 Bank"
EB_CALLBACK = {"code": "", "state": "", "error": ""}
EB_FACTORY = None          # tests: fn(method, path, body, params) -> dict
EB_LOCK = threading.Lock()
EB_CB_SRV = {"srv": None, "srv6": None, "timer": None, "path": "/callback"}
EB_FETCH_LOCK = threading.Lock()


# ---------------- RS256 in pure python ----------------

def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _der(buf, i):
    tag = buf[i]
    ln = buf[i + 1]
    i += 2
    if ln & 0x80:
        nb = ln & 0x7F
        ln = int.from_bytes(buf[i:i + nb], "big")
        i += nb
    return tag, buf[i:i + ln], i + ln


def _der_seq_ints(body):
    out, i = [], 0
    while i < len(body):
        tag, val, i = _der(body, i)
        out.append((tag, val))
    return out


def rsa_key_from_pem(pem):
    """PKCS#1 or PKCS#8 RSA private key (PEM text) -> (n, d)"""
    txt = pem.decode("utf-8", "replace") if isinstance(pem, bytes) else str(pem)
    m = re.search(r"-----BEGIN ((?:RSA )?PRIVATE KEY)-----(.*?)-----END \1-----", txt, re.S)
    if not m:
        if "ENCRYPTED PRIVATE KEY" in txt:
            raise ValueError("Der Schlüssel ist mit einem Kennwort verschlüsselt – bitte unverschlüsselt exportieren.")
        raise ValueError("Keine PEM-Datei mit privatem RSA-Schlüssel (-----BEGIN PRIVATE KEY-----).")
    raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)))
    tag, body, _ = _der(raw, 0)
    items = _der_seq_ints(body)
    if m.group(1) == "PRIVATE KEY":
        # PKCS#8: version, algorithm, OCTET STRING(PKCS#1)
        oct_ = next(v for t, v in items if t == 0x04)
        tag, body, _ = _der(oct_, 0)
        items = _der_seq_ints(body)
    ints = [int.from_bytes(v, "big") for t, v in items if t == 0x02]
    if len(ints) < 4:
        raise ValueError("RSA-Schlüssel nicht lesbar.")
    n, d = ints[1], ints[3]
    if n.bit_length() < 1024:
        raise ValueError("RSA-Schlüssel zu kurz.")
    return n, d


_SHA256_DI = bytes.fromhex("3031300d060960864801650304020105000420")


def rs256_sign(msg, key):
    n, d = key
    k = (n.bit_length() + 7) // 8
    t = _SHA256_DI + hashlib.sha256(msg).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def eb_jwt(app_id, key, ttl=3600):
    now = int(time.time())
    h = _b64u(json.dumps({"typ": "JWT", "alg": "RS256", "kid": app_id}, separators=(",", ":")).encode())
    p = _b64u(json.dumps({"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + ttl}, separators=(",", ":")).encode())
    sig = rs256_sign(f"{h}.{p}".encode("ascii"), key)
    return f"{h}.{p}.{_b64u(sig)}"


# ---------------- configuration ----------------

def eb_cfg():
    s = get_settings()
    key = None
    try:
        pem = unprotect_secret(s.get("eb_key") or "")
        key = rsa_key_from_pem(pem) if pem else None
    except Exception:
        key = None
    return {"app_id": str(s.get("eb_app_id") or "").strip(), "key": key, "key_gesetzt": bool(s.get("eb_key")),
            "bank": str(s.get("eb_bank") or EB_DEFAULT_BANK), "land": str(s.get("eb_land") or "DE"),
            "redirect": str(s.get("eb_redirect") or EB_DEFAULT_REDIRECT).strip(), "session": str(s.get("eb_session") or ""),
            "konten": s.get("eb_konten") or [], "konto": str(s.get("eb_konto") or ""), "gueltig_bis": str(s.get("eb_gueltig_bis") or ""),
            "letzter": "", "tage": int(float(s.get("eb_tage") or 90)), "auto": s.get("eb_auto", True) not in (False, 0, "0"),
            "auto_abruf": bool(s.get("eb_auto_abruf")), "log": s.get("eb_log") or {}}


def eb_config_view():
    c = eb_cfg()
    c["letzter"] = _eb_letzter(c["konto"])
    c.pop("key", None)
    c["eingerichtet"] = bool(c["app_id"] and c["key_gesetzt"])
    c["verbunden"] = bool(c["session"]) and (not c["gueltig_bis"] or c["gueltig_bis"][:10] >= today())
    c["key_ok"] = eb_cfg()["key"] is not None
    c["default_redirect"] = EB_DEFAULT_REDIRECT
    return c


def eb_config_save(d):
    m = {"app_id": "eb_app_id", "bank": "eb_bank", "land": "eb_land", "redirect": "eb_redirect", "konto": "eb_konto", "tage": "eb_tage",
         "auto": "eb_auto", "auto_abruf": "eb_auto_abruf"}
    for k, sk in m.items():
        if k in d:
            v = d[k]
            if isinstance(v, str):
                v = v.strip()
            if k == "app_id" and v and not re.fullmatch(r"[0-9a-fA-F-]{36}", v):
                raise ValueError("Die Application-ID von Enable Banking hat die Form xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.")
            set_setting(sk, v)
    if d.get("key_pem"):
        rsa_key_from_pem(d["key_pem"])
        set_setting("eb_key", protect_secret(d["key_pem"] if isinstance(d["key_pem"], str) else d["key_pem"].decode("utf-8")))
    if d.get("key_loeschen"):
        set_setting("eb_key", "")
    return eb_config_view()


# ---------------- http ----------------

def eb_req(method, path, body=None, params=None, timeout=60):
    if EB_FACTORY:
        return EB_FACTORY(method, path, body, params)
    c = eb_cfg()
    if not c["app_id"] or not c["key"]:
        raise ValueError("Bitte zuerst Application-ID und privaten Schlüssel (.pem) von Enable Banking eintragen.")
    url = EB_API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + eb_jwt(c["app_id"], c["key"]), "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            j = {}
        msg = j.get("message") or j.get("error") or j.get("detail") or str(e)
        if isinstance(msg, (dict, list)):
            msg = json.dumps(msg, ensure_ascii=False)
        if e.code == 401:
            raise ValueError("Enable Banking lehnt die Anmeldung ab (401) – Application-ID und Schlüssel prüfen. " + str(msg)[:200])
        if e.code in (403, 422) and "session" in path:
            raise ValueError("Die Bank-Freigabe ist abgelaufen oder ungültig – bitte neu mit der Bank verbinden. " + str(msg)[:200])
        raise ValueError(f"Enable Banking meldet Fehler {e.code}: {str(msg)[:300]}")
    except urllib.error.URLError as e:
        raise ValueError(f"Keine Verbindung zu Enable Banking ({e.reason}). Internetverbindung prüfen.")


def eb_banks(qtxt=""):
    c = eb_cfg()
    r = eb_req("GET", "/aspsps", params={"country": c["land"] or "DE"})
    lst = [{"name": a.get("name"), "land": a.get("country"), "psu": a.get("psu_types") or [], "max_tage": a.get("maximum_consent_validity")}
           for a in (r.get("aspsps") or [])]
    ql = (qtxt or "").lower()
    if ql:
        lst = [a for a in lst if ql in (a["name"] or "").lower()]
    return {"ok": True, "banken": lst[:3000]}   # v2.3.0: full list for the bank selection


# ---------------- authorisation ----------------

class _EbCb(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.rstrip("/") != (EB_CB_SRV.get("path") or "/callback").rstrip("/"):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(u.query)
        EB_CALLBACK.update(code=(qs.get("code") or [""])[0], state=(qs.get("state") or [""])[0],
                           error=(qs.get("error_description") or qs.get("error") or [""])[0])
        if EB_CALLBACK["code"] and EB_CALLBACK["state"] != str(get_settings().get("eb_state") or "-"):
            EB_CALLBACK.update(code="", error="Die Freigabe gehört nicht zu dieser Anfrage – bitte neu verbinden.")
        ok = bool(EB_CALLBACK["code"])
        html = ("<html><head><meta charset='utf-8'><title>Pfeiffer-Audio Rechnung</title></head><body style='font-family:Segoe UI,Arial;padding:40px'>"
                + ("<h2>✓ Bank freigegeben</h2><p>Du kannst dieses Fenster schließen – das Programm übernimmt die Verbindung.</p>" if ok else
                   "<h2>Freigabe nicht erfolgt</h2><p>" + _eb_html_escape(EB_CALLBACK["error"] or "Kein Code erhalten.") + "</p>")
                + "</body></html>").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)
        if ok:
            threading.Thread(target=_eb_cb_finish, daemon=True).start()


def _eb_html_escape(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _eb_cb_finish():
    try:
        eb_session_from_code(EB_CALLBACK["code"], EB_CALLBACK["state"])
    except Exception as e:
        EB_CALLBACK["error"] = str(e)
    _eb_cb_stop()


def _eb_cb_stop(sync=False):
    tm = EB_CB_SRV.get("timer")
    EB_CB_SRV["timer"] = None
    if tm:
        try:
            tm.cancel()
        except Exception:
            pass
    srv = EB_CB_SRV.get("srv")
    srv6 = EB_CB_SRV.get("srv6")
    EB_CB_SRV["srv"] = None
    EB_CB_SRV["srv6"] = None
    if not srv and not srv6:
        return

    def _down():
        for s_ in (srv, srv6):
            if not s_:
                continue
            try:
                s_.shutdown()
            except Exception:
                pass
            try:
                s_.server_close()
            except Exception:
                pass
    if sync:
        _down()            # never from inside the handler thread (would deadlock)
    else:
        threading.Thread(target=_down, daemon=True).start()


def _eb_cb_start(redirect):
    u = urllib.parse.urlparse(redirect)
    if u.scheme != "http" or (u.hostname or "") not in ("localhost", "127.0.0.1"):
        return False
    _eb_cb_stop(sync=True)
    try:
        srv = http.server.HTTPServer(("127.0.0.1", u.port or 80), _EbCb)
    except OSError:
        return False
    EB_CB_SRV["srv"] = srv
    EB_CB_SRV["path"] = u.path or "/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if (u.hostname or "") == "localhost":
        # v2.1.1: some browsers resolve "localhost" to ::1 first - listen there too (if IPv6 is available)
        try:
            class _Srv6(http.server.HTTPServer):
                address_family = socket.AF_INET6
            srv6 = _Srv6(("::1", u.port or 80), _EbCb)
            EB_CB_SRV["srv6"] = srv6
            threading.Thread(target=srv6.serve_forever, daemon=True).start()
        except Exception:
            EB_CB_SRV["srv6"] = None
    tm = threading.Timer(900, _eb_cb_stop)
    tm.daemon = True
    EB_CB_SRV["timer"] = tm
    tm.start()
    return True


def eb_connect(d=None):
    d = d or {}
    if d:
        eb_config_save({k: v for k, v in d.items() if k in ("bank", "land", "redirect", "app_id")})
    c = eb_cfg()
    if not c["bank"]:
        raise ValueError("Bitte die Bank wählen.")
    tage = int(d.get("tage_freigabe") or 180)
    valid = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=max(1, min(tage, 180)))).replace(microsecond=0)
    state = uuid.uuid4().hex
    set_setting("eb_state", state)
    EB_CALLBACK.update(code="", state="", error="")
    body = {"access": {"valid_until": valid.isoformat().replace("+00:00", "Z")}, "aspsp": {"name": c["bank"], "country": c["land"] or "DE"},
            "state": state, "redirect_url": c["redirect"], "psu_type": "personal"}
    try:
        r = eb_req("POST", "/auth", body)
    except ValueError as e:
        if "maximum" in str(e).lower() or "valid_until" in str(e).lower():
            body["access"]["valid_until"] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=89)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            r = eb_req("POST", "/auth", body)
        else:
            raise
    url = r.get("url")
    if not url:
        raise ValueError("Enable Banking hat keine Anmeldeseite geliefert.")
    lauscht = _eb_cb_start(c["redirect"])
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return {"ok": True, "url": url, "lauscht": lauscht, "redirect": c["redirect"]}


def eb_session_from_code(code, state=""):
    code = (code or "").strip()
    if "code=" in code:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(code).query or code.split("?", 1)[-1])
        state = state or (qs.get("state") or [""])[0]
        code = (qs.get("code") or [""])[0]
    if not code:
        raise ValueError("Kein Freigabe-Code gefunden. Bitte die komplette Adresse aus der Browser-Adresszeile einfügen.")
    exp = str(get_settings().get("eb_state") or "")
    if exp and state != exp:
        raise ValueError("Die Freigabe gehört nicht zu dieser Anfrage (state passt nicht) – bitte neu verbinden.")
    with EB_LOCK:
        r = eb_req("POST", "/sessions", {"code": code})
        konten = []
        for a in r.get("accounts") or []:
            aid = a.get("account_id") or {}
            konten.append({"uid": a.get("uid") or "", "iban": (aid.get("iban") if isinstance(aid, dict) else "") or "",
                           "name": a.get("name") or a.get("product") or "", "waehrung": a.get("currency") or "EUR"})
        set_setting("eb_session", r.get("session_id") or "")
        set_setting("eb_konten", konten)
        acc = r.get("access") or {}
        set_setting("eb_gueltig_bis", str(acc.get("valid_until") or "")[:10])
        cur = str(get_settings().get("eb_konto") or "")
        if konten and cur not in [k["uid"] for k in konten]:
            # v2.3.1: prefer the account whose IBAN is the one printed on the invoices (Firma & Bank)
            own_iban = re.sub(r"\s", "", str(get_settings().get("iban") or "")).upper()
            own = next((k for k in konten if re.sub(r"\s", "", k.get("iban") or "").upper() == own_iban and own_iban), None)
            set_setting("eb_konto", (own or konten[0])["uid"])
        set_setting("eb_verbunden", now_iso())
    EB_CALLBACK.update(code="", error="")
    return {"ok": True, "konten": konten, "gueltig_bis": str(acc.get("valid_until") or "")[:10]}


def eb_disconnect():
    sid = eb_cfg()["session"]
    if sid:
        try:
            eb_req("DELETE", f"/sessions/{sid}")
        except Exception:
            pass
    for k in ("eb_session", "eb_gueltig_bis"):
        set_setting(k, "")
    set_setting("eb_konten", [])
    return {"ok": True}


def eb_status():
    v = eb_config_view()
    v["callback"] = {"wartet": bool(EB_CB_SRV.get("srv")), "fehler": EB_CALLBACK.get("error") or ""}
    return v


# ---------------- transactions ----------------

def _eb_amt(t):
    ta = t.get("transaction_amount") or {}
    try:
        v = abs(float(str(ta.get("amount") or 0).replace(",", ".")))
    except Exception:
        v = 0.0
    if (t.get("credit_debit_indicator") or "").upper() == "DBIT":
        v = -v
    elif str(ta.get("amount") or "").startswith("-"):
        v = -v
    return round(v, 2)


def eb_tx_dict(t):
    deb = (t.get("credit_debit_indicator") or "").upper() == "DBIT"
    party = (t.get("creditor") if deb else t.get("debtor")) or {}
    acc = (t.get("creditor_account") if deb else t.get("debtor_account")) or {}
    rem = t.get("remittance_information") or []
    zweck = " ".join(str(x_) for x_ in rem) if isinstance(rem, list) else str(rem)
    if not zweck.strip():
        zweck = str(t.get("note") or (t.get("bank_transaction_code") or {}).get("description") or "")
    return {"datum": str(t.get("booking_date") or t.get("value_date") or t.get("transaction_date") or "")[:10], "betrag": _eb_amt(t),
            "name": str(party.get("name") or "")[:120], "zweck": re.sub(r"\s+", " ", zweck).strip()[:400],
            "iban": str(acc.get("iban") or "").replace(" ", "")}


def eb_fetch(tage=None):
    if not EB_FETCH_LOCK.acquire(timeout=5):
        raise ValueError("Ein Bankabruf läuft gerade schon – bitte kurz warten.")
    try:
        return _eb_fetch(tage)
    finally:
        EB_FETCH_LOCK.release()


def _eb_fetch(tage=None):
    c = eb_cfg()
    if not c["session"]:
        raise ValueError(f"Noch nicht mit der Bank verbunden – Einstellungen → Bankabruf → „{c['bank'] or 'Bank'} verbinden“.")
    if c["gueltig_bis"] and c["gueltig_bis"][:10] < today():
        raise ValueError("Die Freigabe der Bank ist abgelaufen – bitte in den Einstellungen → Bankabruf neu verbinden.")
    konto = next((k for k in c["konten"] if k["uid"] == c["konto"]), (c["konten"] or [None])[0])
    if not konto:
        raise ValueError("Die Bank hat kein Konto freigegeben – bitte neu verbinden und ein Konto auswählen.")
    bis = datetime.date.today()
    if tage:
        von = bis - datetime.timedelta(days=int(tage))
    elif _eb_letzter(konto["uid"]):
        von = d_iso(_eb_letzter(konto["uid"])) - datetime.timedelta(days=30)   # v2.1.1: late postings
    else:
        von = bis - datetime.timedelta(days=c["tage"])
    log = [f"Konto {konto['iban'] or konto['uid']} – Umsätze {de_date(von.isoformat())} bis {de_date(bis.isoformat())}"]
    raw, ck, n_pend = [], None, 0
    for _i in range(60):
        params = {"date_from": von.isoformat(), "date_to": bis.isoformat()}
        if ck:
            params["continuation_key"] = ck
        r = eb_req("GET", f"/accounts/{konto['uid']}/transactions", params=params)
        for t in r.get("transactions") or []:
            if (t.get("status") or "BOOK").upper() not in ("BOOK", "BOOKED"):
                n_pend += 1
                continue
            raw.append(eb_tx_dict(t))
        ck = r.get("continuation_key")
        if not ck:
            break
    log.append(f"{len(raw)} gebuchte Umsätze empfangen" + (f", {n_pend} vorgemerkte übersprungen" if n_pend else ""))
    sal = None
    try:
        b = eb_req("GET", f"/accounts/{konto['uid']}/balances")
        bl = b.get("balances") or []
        pick = next((x_ for x_ in bl if x_.get("balance_type") in ("CLBD", "closingBooked")), None) or \
            next((x_ for x_ in bl if x_.get("balance_type") in ("ITBD", "XPCD", "ITAV", "interimBooked", "expected")), None) or (bl[0] if bl else None)
        if pick:
            sal = {"saldo": float((pick.get("balance_amount") or {}).get("amount") or 0),
                   "datum": str(pick.get("reference_date") or today())[:10]}
            log.append(f"Kontostand {money(sal['saldo'])}")
    except Exception as e_:
        log.append(f"Kontostand nicht abrufbar ({e_})")
    erg = fints_import(raw, sal, konto["iban"], auto=c["auto"], quelle=f"Bankabruf ({c['bank']}, PSD2)")
    erg.update({"zeit": now_iso(), "ok": True, "von": von.isoformat(), "bis": bis.isoformat(), "konto": konto["iban"], "bank": c["bank"]})
    log.append("Neu: %d · doppelt: %d · automatisch bezahlt: %d · Fixkosten: %d · zur Prüfung: %d"
               % (erg["neu"], erg["doppelt"], len(erg["bezahlt"]), len(erg["fixkosten"]), erg["offen"]))
    erg["log"] = log
    lz = get_settings().get("eb_letzter")
    lz = dict(lz) if isinstance(lz, dict) else {}
    lz[konto["uid"]] = bis.isoformat()
    set_setting("eb_letzter", lz)
    set_setting("eb_log", erg)
    return erg


def _eb_letzter(uid):
    lz = get_settings().get("eb_letzter")
    v = (lz or {}).get(uid) if isinstance(lz, dict) else ""
    return v if v and d_iso(v) else ""


def _eb_fetch_route(h, d):
    try:
        return h._send(200, dict(eb_fetch(d.get("tage")), ok=True))
    except ValueError as e:
        set_setting("eb_log", {"zeit": now_iso(), "ok": False, "fehler": str(e), "log": []})
        raise


def _eb_loop():
    time.sleep(90)
    while True:
        try:
            c = eb_cfg()
            lg = c["log"] or {}
            fehler_neu = lg.get("ok") is False and (lg.get("zeit") or "") > (datetime.datetime.now() - datetime.timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
            if c["auto_abruf"] and c["session"] and _eb_letzter(c["konto"]) != today() and not fehler_neu \
                    and (not c["gueltig_bis"] or c["gueltig_bis"] >= today()):
                eb_fetch()
        except Exception as e:
            set_setting("eb_log", {"zeit": now_iso(), "ok": False, "fehler": str(e), "log": []})
        time.sleep(3600)


def _eb_upload_key(h, tmp, name):
    try:
        pem = open(tmp, "rb").read(20000).decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    rsa_key_from_pem(pem)
    set_setting("eb_key", protect_secret(pem))
    m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", name or "")
    if m and not get_settings().get("eb_app_id"):
        set_setting("eb_app_id", m.group(1))
    return h._send(200, dict(eb_config_view(), ok=True))


def _eb_boot(d):
    st = d.get("settings") or {}
    for k in ("eb_key", "eb_state", "eb_session"):
        st.pop(k, None)
    v = eb_config_view()
    d["psd2"] = {"eingerichtet": v["eingerichtet"], "verbunden": v["verbunden"], "bank": v["bank"], "gueltig_bis": v["gueltig_bis"]}


def _eb_selftest():
    err = []
    try:
        n = (1 << 2047) + 12345
        d_ = 0x10001
        s1 = rs256_sign(b"test", (n, d_))
        if len(s1) != (n.bit_length() + 7) // 8:
            err.append("PSD2: Signaturlänge falsch")
        t = eb_tx_dict({"transaction_amount": {"amount": "12.50", "currency": "EUR"}, "credit_debit_indicator": "DBIT",
                        "booking_date": "2026-10-01", "creditor": {"name": "Shop"}, "remittance_information": ["Rg 1", "Kd 2"]})
        if t["betrag"] != -12.5 or t["name"] != "Shop" or t["zweck"] != "Rg 1 Kd 2":
            err.append("PSD2: Umsatz falsch gelesen")
    except Exception as e:
        err.append(f"PSD2: {e}")
    return err


HOOK_GET["/api/eb/config"] = lambda h, qs: h._send(200, eb_status())
HOOK_GET["/api/eb/banks"] = lambda h, qs: h._send(200, eb_banks(qs.get("q") or ""))
HOOK_POST["/api/eb/config/save"] = lambda h, d: h._send(200, dict(eb_config_save(d), ok=True))
HOOK_POST["/api/eb/connect"] = lambda h, d: h._send(200, eb_connect(d))
HOOK_POST["/api/eb/code"] = lambda h, d: h._send(200, eb_session_from_code(d.get("code") or d.get("url") or "", d.get("state") or ""))
HOOK_POST["/api/eb/trennen"] = lambda h, d: h._send(200, eb_disconnect())
HOOK_POST["/api/eb/abruf"] = _eb_fetch_route
HOOK_POST["/api/eb/openurl"] = lambda h, d: (webbrowser.open("https://enablebanking.com/cp/applications"), h._send(200, {"ok": True}))[1]
HOOK_UPLOAD["/api/upload/ebkey"] = _eb_upload_key
HOOK_BOOT.append(_eb_boot)
HOOK_START.append(_eb_loop)
HOOK_SELFTEST.append(_eb_selftest)
