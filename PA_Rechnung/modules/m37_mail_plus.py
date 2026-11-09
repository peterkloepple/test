# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m37_mail_plus (v2.0.9)
# E-Mail-Versand robust gemacht:
#  - Anbieter-Vorlagen (Gmail, GMX, web.de, T-Online, IONOS, Strato, Outlook ...)
#  - Verschluesselung waehlbar (automatisch / SSL / STARTTLS / keine)
#  - eigene Absender-Adresse (wenn der Login keine Mail-Adresse ist)
#  - verstaendliche Fehlermeldungen mit Loesungs-Hinweis je Anbieter
#  - Test-Mail mit Schritt-Protokoll, testet die Werte im Formular (ohne vorher zu speichern)
#  - Microsoft (Outlook.com / Hotmail / Microsoft 365): Anmeldung per OAuth2 (XOAUTH2),
#    weil Microsoft das einfache Passwort fuer SMTP/IMAP abgeschaltet hat
#  - IMAP: gleiches OAuth2 fuer Microsoft, Passwort des Versands als Ersatz
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import ssl
import urllib.request
import urllib.parse
import urllib.error

M37_VERSION = "1.0.0"

MAIL_PROVIDERS = [
    {"id": "gmail", "label": "Gmail / Google Workspace", "domains": ["gmail.com", "googlemail.com"], "smtp": ["smtp.gmail.com", 587, "starttls"],
     "imap": ["imap.gmail.com", 993], "hint": "Gmail braucht ein App-Passwort (16 Zeichen): Google-Konto → Sicherheit → 2-Schritt-Bestätigung an → "
     "„App-Passwörter“ → neues Passwort erzeugen und hier eintragen. Das normale Google-Passwort funktioniert nicht."},
    {"id": "gmx", "label": "GMX", "domains": ["gmx.de", "gmx.net", "gmx.at", "gmx.ch", "gmx.com"], "smtp": ["mail.gmx.net", 587, "starttls"],
     "imap": ["imap.gmx.net", 993], "hint": "Bei GMX muss der Zugriff für Mailprogramme erst freigeschaltet werden: im GMX-Postfach → E-Mail → "
     "Einstellungen → POP3/IMAP Abruf → „Zugriff über POP3 und IMAP erlauben“ anhaken."},
    {"id": "webde", "label": "WEB.DE", "domains": ["web.de"], "smtp": ["smtp.web.de", 587, "starttls"], "imap": ["imap.web.de", 993],
     "hint": "Bei WEB.DE muss der Zugriff für Mailprogramme erst freigeschaltet werden: im Postfach → Einstellungen → POP3/IMAP Abruf → "
     "„Zugriff über POP3 und IMAP erlauben“ anhaken."},
    {"id": "tonline", "label": "T-Online / Telekom", "domains": ["t-online.de", "magenta.de"], "smtp": ["securesmtp.t-online.de", 465, "ssl"],
     "imap": ["secureimap.t-online.de", 993], "hint": "Telekom verlangt ein eigenes E-Mail-Passwort für Mailprogramme (nicht das Login-Passwort): "
     "E-Mail-Center → Einstellungen → Passwörter → E-Mail-Passwort anlegen."},
    {"id": "outlook", "label": "Outlook.com / Hotmail / Live (Microsoft)", "domains": ["outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "live.com", "live.de", "msn.com"],
     "smtp": ["smtp-mail.outlook.com", 587, "starttls"], "imap": ["outlook.office365.com", 993], "auth": "ms",
     "hint": "Microsoft hat das einfache Passwort für Mailprogramme abgeschaltet (Fehler 5.7.139 „basic authentication is disabled“). "
     "Hier „Anmeldung: Microsoft-Konto (OAuth2)“ wählen und einmal bei Microsoft anmelden – Anleitung im Handbuch, Kapitel 13."},
    {"id": "m365", "label": "Microsoft 365 / Exchange Online (Firma)", "domains": [], "smtp": ["smtp.office365.com", 587, "starttls"],
     "imap": ["outlook.office365.com", 993], "auth": "ms",
     "hint": "Microsoft 365: SMTP-AUTH muss für das Postfach im Admin-Center erlaubt sein; Anmeldung per Microsoft-Konto (OAuth2)."},
    {"id": "icloud", "label": "iCloud", "domains": ["icloud.com", "me.com", "mac.com"], "smtp": ["smtp.mail.me.com", 587, "starttls"],
     "imap": ["imap.mail.me.com", 993], "hint": "iCloud braucht ein app-spezifisches Passwort: appleid.apple.com → Anmeldung und Sicherheit → App-spezifische Passwörter."},
    {"id": "yahoo", "label": "Yahoo", "domains": ["yahoo.com", "yahoo.de"], "smtp": ["smtp.mail.yahoo.com", 465, "ssl"], "imap": ["imap.mail.yahoo.com", 993],
     "hint": "Yahoo braucht ein App-Passwort: Kontosicherheit → App-Passwort generieren."},
    {"id": "ionos", "label": "IONOS (1&1) – eigene Domain", "domains": ["online.de", "onlinehome.de"], "smtp": ["smtp.ionos.de", 587, "starttls"],
     "imap": ["imap.ionos.de", 993], "hint": "Benutzer = komplette E-Mail-Adresse, Passwort = Passwort des Postfachs (nicht das IONOS-Kundenlogin)."},
    {"id": "strato", "label": "STRATO – eigene Domain", "domains": [], "smtp": ["smtp.strato.de", 465, "ssl"], "imap": ["imap.strato.de", 993],
     "hint": "Benutzer = komplette E-Mail-Adresse, Passwort = Passwort des Postfachs."},
    {"id": "allinkl", "label": "ALL-INKL – eigene Domain", "domains": [], "smtp": ["", 465, "ssl"], "imap": ["", 993],
     "hint": "Server steht in den KAS-Postfach-Daten (z. B. w0123456.kasserver.com). Benutzer = Postfachname (z. B. m0123456)."},
    {"id": "hetzner", "label": "Hetzner – eigene Domain", "domains": [], "smtp": ["mail.your-server.de", 587, "starttls"], "imap": ["mail.your-server.de", 993],
     "hint": "Benutzer = komplette E-Mail-Adresse."},
    {"id": "mailbox", "label": "mailbox.org", "domains": ["mailbox.org"], "smtp": ["smtp.mailbox.org", 465, "ssl"], "imap": ["imap.mailbox.org", 993], "hint": ""},
    {"id": "posteo", "label": "Posteo", "domains": ["posteo.de", "posteo.net"], "smtp": ["posteo.de", 587, "starttls"], "imap": ["posteo.de", 993], "hint": ""},
    {"id": "freenet", "label": "freenet", "domains": ["freenet.de"], "smtp": ["mx.freenet.de", 587, "starttls"], "imap": ["mx.freenet.de", 993],
     "hint": "Bei freenet muss „E-Mail-Programme“ (POP3/IMAP/SMTP) in den Postfach-Einstellungen aktiviert sein."},
    {"id": "eigen", "label": "anderer Anbieter / eigener Server", "domains": [], "smtp": ["", 587, "auto"], "imap": ["", 993], "hint": ""},
]
MS_SCOPES = "offline_access https://outlook.office.com/SMTP.Send https://outlook.office.com/IMAP.AccessAsUser.All"
MS_LOGIN = "https://login.microsoftonline.com"
MS_FLOW = {}             # running device-code flow
MS_TOKEN = {"access": "", "exp": 0.0}
MS_LOCK = threading.Lock()


def mail_provider(user="", host=""):
    dom = (user or "").rsplit("@", 1)[-1].strip().lower() if "@" in (user or "") else ""
    h = (host or "").strip().lower()
    for p_ in MAIL_PROVIDERS:
        if dom and dom in p_["domains"]:
            return p_
    for p_ in MAIL_PROVIDERS:
        if h and p_["smtp"][0] and (h == p_["smtp"][0] or h == p_["imap"][0]):
            return p_
    if "office365" in h or "outlook" in h:
        return next(p_ for p_ in MAIL_PROVIDERS if p_["id"] == "outlook")
    return None


# ---------------- configuration ----------------

def smtp_cfg(over=None):
    s = get_settings()
    c = {"host": str(s.get("smtp_host") or "").strip(), "port": int(float(s.get("smtp_port") or 0) or 0),
         "user": str(s.get("smtp_user") or "").strip(), "pass": None, "sec": str(s.get("smtp_sec") or "auto"),
         "from_addr": str(s.get("smtp_from_addr") or "").strip(), "from_name": str(s.get("smtp_from") or "").strip(),
         "auth": str(s.get("smtp_auth") or "pass"), "bcc_self": bool(s.get("mail_bcc_self")),
         "verify": not s.get("smtp_noverify")}
    for k, v in (over or {}).items():
        if k in c and v is not None and v != "":
            c[k] = v.strip() if isinstance(v, str) else v
    if over and over.get("pass"):
        c["pass"] = str(over["pass"])
    if c["pass"] is None:
        c["pass_err"] = ""
        try:
            c["pass"] = unprotect_secret(s.get("smtp_pass") or "")
        except Exception:
            c["pass"] = ""
            c["pass_err"] = ("Das gespeicherte Mail-Passwort lässt sich hier nicht entschlüsseln (Datenordner von einem anderen PC "
                             "oder Windows-Benutzer übernommen?). Bitte das Passwort in den Einstellungen → E-Mail neu eintragen.")
    try:
        c["port"] = int(float(c["port"] or 0))
    except Exception:
        c["port"] = 0
    if c["sec"] not in ("auto", "ssl", "starttls", "none"):
        c["sec"] = "auto"
    if not c["port"]:
        c["port"] = 465 if c["sec"] == "ssl" else 587
    c["host"] = re.sub(r"^(smtps?|https?)://", "", c["host"], flags=re.I).strip().strip("/")
    if ":" in c["host"] and c["host"].rsplit(":", 1)[1].isdigit():
        c["host"], pt = c["host"].rsplit(":", 1)
        c["port"] = int(pt)
    return c


def _clean_pw(pw, c):
    pw = (pw or "").strip()
    p_ = mail_provider(c.get("user"), c.get("host"))
    # Google / Yahoo / iCloud app passwords are shown in groups with spaces
    if p_ and p_["id"] in ("gmail", "yahoo", "icloud") and re.fullmatch(r"[a-zA-Z]{4}( [a-zA-Z]{4}){3}", pw):
        pw = pw.replace(" ", "")
    return pw


def _smtp_login_once(srv, user, pw):
    """login with ONE auth method. smtplib.login() tries the next method after a 535 -
    Gmail has already hung up by then and the real answer (wrong password) is lost."""
    srv.ehlo_or_helo_if_needed()
    if not srv.has_extn("auth"):
        raise smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")
    adv = (srv.esmtp_features.get("auth") or "").upper().split()
    srv.user, srv.password = user, pw
    for m in ("PLAIN", "LOGIN", "CRAM-MD5"):
        if m in adv:
            return srv.auth(m, getattr(srv, "auth_" + m.lower().replace("-", "_")))
    return srv.login(user, pw)


# ---------------- error texts ----------------

def mail_error_text(e, c, stage=""):
    p_ = mail_provider(c.get("user"), c.get("host"))
    hint = (" " + p_["hint"]) if p_ and p_.get("hint") else ""
    host, port = c.get("host"), c.get("port")
    t = str(e)
    if isinstance(e, ValueError) and not isinstance(e, ssl.SSLError):
        return t
    if stage == "login" and isinstance(e, (smtplib.SMTPServerDisconnected, socket.timeout, TimeoutError, ConnectionResetError)):
        return ("Der Server hat die Anmeldung abgebrochen – meist stimmen Benutzer oder Passwort nicht (manche Server trennen dann "
                "einfach die Verbindung)." + hint)
    if isinstance(e, smtplib.SMTPAuthenticationError):
        srv = (e.smtp_error.decode("utf-8", "replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error or ""))[:220]
        low = srv.lower()
        if c.get("auth") == "ms":
            return ("Microsoft hat die Anmeldung abgelehnt. Bitte in den Einstellungen → E-Mail neu „Bei Microsoft anmelden“ – der Benutzer muss "
                    "genau die angemeldete Adresse sein; bei Microsoft 365 muss SMTP-AUTH für das Postfach erlaubt sein. Server sagt: " + srv)
        if "5.7.139" in srv or "basic authentication is disabled" in low or "basicauthblocked" in low.replace(" ", ""):
            return ("Microsoft lässt die Anmeldung mit Passwort nicht mehr zu (basic authentication is disabled). In den Einstellungen → E-Mail "
                    "„Anmeldung: Microsoft-Konto (OAuth2)“ wählen und einmal bei Microsoft anmelden. Server sagt: " + srv)
        if "application-specific password" in low or "5.7.9" in srv:
            return "Der Server verlangt ein App-Passwort statt des normalen Passworts." + hint + " Server sagt: " + srv
        if "smtp auth" in low and "disabled" in low:
            return "SMTP-Anmeldung ist für dieses Postfach abgeschaltet (beim Anbieter/Admin freischalten)." + hint + " Server sagt: " + srv
        if "5.7.8" in srv or "badcredentials" in low:
            return (f"Anmeldung abgelehnt – Benutzer „{c.get('user')}“ oder Passwort falsch." + hint
                    + " Benutzer muss die vollständige Adresse sein; das App-Passwort gehört genau zu diesem Konto. Server sagt: " + srv)
        return ("Anmeldung abgelehnt – Benutzer oder Passwort stimmen nicht." + hint + f" Server sagt: {e.smtp_code} {srv}")
    if isinstance(e, smtplib.SMTPSenderRefused):
        return (f"Der Server lehnt die Absender-Adresse „{c.get('from_addr') or c.get('user')}“ ab. Sie muss zum Konto passen – "
                "ggf. unter „Absender-Adresse“ die richtige Adresse eintragen. Server sagt: " + str(e.smtp_error)[:200])
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        bad = ", ".join(e.recipients.keys()) if getattr(e, "recipients", None) else ""
        return f"Empfänger-Adresse abgelehnt: {bad}. Bitte die Adresse prüfen (mehrere Empfänger mit Komma trennen)."
    if isinstance(e, smtplib.SMTPDataError):
        if e.smtp_code == 552 or "size" in str(e.smtp_error).lower():
            return "Die Mail ist dem Server zu groß (Anhang zu groß)."
        return f"Der Server hat die Mail nicht angenommen ({e.smtp_code}): {str(e.smtp_error)[:200]}"
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return f"Der Server {host} kann das nicht: {t}. Verschlüsselung/Port prüfen (465 = SSL, 587 = STARTTLS)."
    if isinstance(e, smtplib.SMTPServerDisconnected):
        return (f"{host}:{port} hat die Verbindung sofort getrennt – meist passen Port und Verschlüsselung nicht zusammen "
                "(Port 465 = SSL, Port 587 = STARTTLS).")
    if isinstance(e, ssl.SSLCertVerificationError):
        return (f"Das Sicherheitszertifikat von {host} ist ungültig oder passt nicht zum Servernamen ({getattr(e, 'verify_message', '') or t}). "
                "Servernamen prüfen – bei eigenem Server mit selbst ausgestelltem Zertifikat „Zertifikat nicht prüfen“ anhaken.")
    if isinstance(e, ssl.SSLError):
        if "WRONG_VERSION_NUMBER" in t or "wrong version number" in t.lower() or "UNKNOWN_PROTOCOL" in t:
            return (f"Verschlüsselung passt nicht zum Port {port}: Bei Port 465 „SSL“, bei Port 587 „STARTTLS“ wählen "
                    "(oder „automatisch“).")
        return f"Verschlüsselte Verbindung zu {host} fehlgeschlagen: {t}"
    if isinstance(e, socket.gaierror):
        return f"Server „{host}“ nicht gefunden – Schreibweise oder Internetverbindung prüfen."
    if isinstance(e, (socket.timeout, TimeoutError)):
        return (f"Keine Antwort von {host}:{port} (Zeitüberschreitung). Port prüfen – manche Netze/Router sperren Port 25 und 465; "
                "dann 587 mit STARTTLS versuchen. Auch eine Firewall/Virenscanner kann blockieren.")
    if isinstance(e, ConnectionRefusedError):
        return f"{host}:{port} lehnt die Verbindung ab – falscher Port oder Server."
    if isinstance(e, ConnectionResetError):
        return f"{host}:{port} hat die Verbindung zurückgesetzt – Port/Verschlüsselung prüfen; ggf. blockiert ein Virenscanner den Mailversand."
    if isinstance(e, OSError) and "DPAPI" in t:
        return "Das gespeicherte Mail-Passwort lässt sich hier nicht entschlüsseln – bitte in den Einstellungen → E-Mail neu eintragen."
    if isinstance(e, smtplib.SMTPException):
        return f"Mailserver meldet: {t[:240]}"
    if isinstance(e, OSError):
        return f"Verbindung zu {host}:{port} fehlgeschlagen: {t[:200]}"
    return f"{type(e).__name__}: {t[:240]}"


# ---------------- Microsoft OAuth2 (device code) ----------------

def _ms_post(path, data, timeout=30):
    s = get_settings()
    tenant = (s.get("ms_tenant") or "common").strip() or "common"
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{MS_LOGIN}/{tenant}/oauth2/v2.0/{path}", data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return {"error": f"http_{e.code}", "error_description": str(e)}


def _ms_client():
    cid = str(get_settings().get("ms_client_id") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", cid):
        raise ValueError("Für die Microsoft-Anmeldung bitte zuerst die Anwendungs-ID (Client-ID) deiner App-Registrierung eintragen "
                         "(Einstellungen → E-Mail → Microsoft-Konto; Anleitung im Handbuch).")
    return cid


def ms_start(d=None):
    if d and d.get("client_id") is not None:
        set_setting("ms_client_id", str(d.get("client_id") or "").strip())
        if d.get("tenant"):
            set_setting("ms_tenant", str(d["tenant"]).strip())
    cid = _ms_client()
    r = _ms_post("devicecode", {"client_id": cid, "scope": MS_SCOPES})
    if r.get("error"):
        raise ValueError("Microsoft lehnt ab: " + (r.get("error_description") or r["error"]).split("\r\n")[0][:300])
    flow = {"device_code": r["device_code"], "user_code": r["user_code"], "url": r.get("verification_uri") or "https://microsoft.com/devicelogin",
            "interval": int(r.get("interval") or 5), "exp": time.time() + int(r.get("expires_in") or 900), "state": "warten", "msg": ""}
    flow["id"] = uuid.uuid4().hex
    MS_FLOW.clear()
    MS_FLOW.update(flow)
    threading.Thread(target=_ms_poll, args=(cid, flow["id"], flow["device_code"]), daemon=True).start()
    try:
        webbrowser.open(flow["url"])
    except Exception:
        pass
    return {"ok": True, "code": flow["user_code"], "url": flow["url"], "text": r.get("message", "")}


def _ms_save_tokens(r):
    if r.get("refresh_token"):
        set_setting("ms_refresh", protect_secret(r["refresh_token"]))
    MS_TOKEN["access"] = r.get("access_token") or ""
    MS_TOKEN["exp"] = time.time() + int(r.get("expires_in") or 3000) - 120
    try:
        idt = r.get("id_token") or ""
        if idt.count(".") == 2:
            pl = idt.split(".")[1]
            info = json.loads(base64.urlsafe_b64decode(pl + "=" * (-len(pl) % 4)).decode("utf-8"))
            set_setting("ms_konto", info.get("preferred_username") or info.get("email") or "")
    except Exception:
        pass


def _ms_poll(cid, fid, dcode):
    mine = lambda: MS_FLOW.get("id") == fid
    while mine() and MS_FLOW.get("state") == "warten" and time.time() < MS_FLOW.get("exp", 0):
        time.sleep(MS_FLOW.get("interval", 5))
        if not mine():
            return
        r = _ms_post("token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": cid, "device_code": dcode})
        if not mine() or MS_FLOW.get("state") != "warten":
            if not r.get("error") and mine():
                _ms_save_tokens(r)
            return
        err = r.get("error")
        if not err:
            _ms_save_tokens(r)
            set_setting("ms_verbunden", now_iso())
            MS_FLOW.update(state="fertig", msg="Mit Microsoft verbunden.")
            return
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            MS_FLOW["interval"] = MS_FLOW.get("interval", 5) + 5
            continue
        MS_FLOW.update(state="fehler", msg={"authorization_declined": "Anmeldung bei Microsoft abgelehnt.",
                                            "expired_token": "Der Code ist abgelaufen – bitte neu starten."}.get(err)
                       or (r.get("error_description") or err).split("\r\n")[0][:300])
        return
    if mine() and MS_FLOW.get("state") == "warten":
        MS_FLOW.update(state="fehler", msg="Der Code ist abgelaufen – bitte neu starten.")


def ms_status():
    s = get_settings()
    return {"ok": True, "flow": {k: MS_FLOW.get(k) for k in ("state", "msg", "user_code", "url")} if MS_FLOW else None,
            "verbunden": bool(s.get("ms_refresh")), "konto": s.get("ms_konto") or "", "seit": s.get("ms_verbunden") or "",
            "client_id": s.get("ms_client_id") or "", "tenant": s.get("ms_tenant") or "common"}


def ms_token():
    with MS_LOCK:
        if MS_TOKEN["access"] and time.time() < MS_TOKEN["exp"]:
            return MS_TOKEN["access"]
        s = get_settings()
        try:
            rt = unprotect_secret(s.get("ms_refresh") or "")
        except Exception:
            rt = ""
        if not rt:
            raise ValueError("Noch nicht bei Microsoft angemeldet – Einstellungen → E-Mail → „Bei Microsoft anmelden“.")
        r = _ms_post("token", {"grant_type": "refresh_token", "client_id": _ms_client(), "refresh_token": rt, "scope": MS_SCOPES})
        if r.get("error"):
            if r["error"] in ("invalid_grant", "interaction_required"):
                set_setting("ms_refresh", "")
                raise ValueError("Die Microsoft-Anmeldung ist abgelaufen oder wurde widerrufen – bitte in den Einstellungen → E-Mail neu anmelden.")
            raise ValueError("Microsoft-Token nicht erneuerbar: " + (r.get("error_description") or r["error"]).split("\r\n")[0][:240])
        _ms_save_tokens(r)
        return MS_TOKEN["access"]


def ms_logout():
    set_setting("ms_refresh", "")
    set_setting("ms_konto", "")
    MS_TOKEN.update(access="", exp=0)
    return {"ok": True}


def _xoauth2(user, token):
    return f"user={user}\x01auth=Bearer {token}\x01\x01"


# ---------------- SMTP ----------------

def smtp_open(c, log=None, timeout=30):
    lg = log if log is not None else []
    if not c["host"]:
        raise ValueError("Bitte den SMTP-Server eintragen (Einstellungen → E-Mail).")
    if not c["user"]:
        raise ValueError("Bitte Benutzer / Absender-Adresse eintragen (Einstellungen → E-Mail).")
    use_ms = c.get("auth") == "ms"
    if not use_ms and not c.get("pass"):
        raise ValueError(c.get("pass_err") or "Bitte das Passwort bzw. App-Passwort eintragen (Einstellungen → E-Mail).")
    try:
        socket.getaddrinfo(c["host"], c["port"])
    except socket.gaierror as e:
        raise ValueError(mail_error_text(e, c))
    lg.append(f"✓ Server {c['host']} gefunden")
    sec = c["sec"]
    if sec == "auto":
        sec = "ssl" if c["port"] == 465 else "starttls"
    ctx = ssl.create_default_context()
    if not c.get("verify", True):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        if sec == "ssl":
            srv = smtplib.SMTP_SSL(c["host"], c["port"], timeout=timeout, context=ctx)
            lg.append(f"✓ verbunden mit Port {c['port']} (SSL)")
        else:
            srv = smtplib.SMTP(c["host"], c["port"], timeout=timeout)
            lg.append(f"✓ verbunden mit Port {c['port']}")
            srv.ehlo()
            if sec == "starttls" or srv.has_extn("starttls"):
                if not srv.has_extn("starttls"):
                    try:
                        srv.quit()
                    except Exception:
                        pass
                    raise ValueError(f"{c['host']}:{c['port']} bietet keine Verschlüsselung (STARTTLS) an. Bei Port 465 „SSL“ wählen – "
                                     "unverschlüsselt (Einstellung „keine“) nur im eigenen Netz verwenden.")
                srv.starttls(context=ctx)
                srv.ehlo()
                lg.append("✓ Verschlüsselung (STARTTLS) aktiv")
            else:
                lg.append("! ohne Verschlüsselung (nur im eigenen Netz sinnvoll)")
    except ssl.SSLError as e:
        raise ValueError(mail_error_text(e, c))
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(mail_error_text(e, c))
    try:
        if use_ms:
            tok = ms_token()
            srv.ehlo_or_helo_if_needed()
            srv.auth("XOAUTH2", lambda ch=None: _xoauth2(c["user"], tok) if ch is None else "", initial_response_ok=True)
            lg.append("✓ angemeldet (Microsoft-Konto, OAuth2)")
        else:
            _smtp_login_once(srv, c["user"], _clean_pw(c["pass"], c))
            lg.append(f"✓ angemeldet als {c['user']}")
    except Exception as e:
        try:
            srv.close()
        except Exception:
            pass
        raise ValueError(mail_error_text(e, c, "login"))
    return srv


def _addr_list(v):
    parts = [a.strip() for a in re.split(r"[;,\n]+", v or "") if a.strip()]
    return ", ".join(parts)


def send_mail(to, cc, subject, body, attachments, over=None, log=None):
    """v2.0.9: same signature as before, clear German errors (ValueError)"""
    from email.utils import formataddr, make_msgid, formatdate
    c = smtp_cfg(over)
    sender = c["from_addr"] or c["user"]
    if "@" not in sender:
        raise ValueError(f"„{sender}“ ist keine E-Mail-Adresse. Bitte unter Einstellungen → E-Mail die Absender-Adresse eintragen.")
    msg = EmailMessage()
    msg["From"] = formataddr((c["from_name"], sender))
    msg["To"] = _addr_list(to)
    if cc:
        msg["Cc"] = _addr_list(cc)
    if c["bcc_self"]:
        msg["Bcc"] = sender
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    msg.set_content(body)
    for fn, data in attachments:
        mt = mimetypes.guess_type(fn)[0] or "application/pdf"
        ma, sb = mt.split("/", 1)
        msg.add_attachment(data, maintype=ma, subtype=sb, filename=fn)
    lg = log if log is not None else []
    srv = smtp_open(c, lg)
    try:
        try:
            refused = srv.send_message(msg)
        except Exception as e:
            raise ValueError(mail_error_text(e, c))
        if refused:
            lg.append("! nicht zugestellt an: " + ", ".join(refused))
            # v2.1.0: refused To/Cc recipients but accepted BCC copy to oneself counted as "sent" before
            from email.utils import getaddresses
            real = {a.lower() for _n, a in getaddresses([msg["To"] or "", msg["Cc"] or ""]) if a}
            bad = {str(a).lower() for a in refused}
            if real and real <= bad:
                raise ValueError(f"Empfänger-Adresse abgelehnt: {', '.join(sorted(refused))}. Die Mail wurde NICHT zugestellt – "
                                 "bitte die Adresse prüfen.")
        lg.append("✓ Mail übergeben an " + msg["To"])
    finally:
        try:
            srv.quit()
        except Exception:
            pass
    set_setting("mail_status", {"zeit": now_iso(), "ok": True, "an": msg["To"]})
    return True


def mail_configured(s=None):
    s = s or get_settings()
    if not (str(s.get("smtp_host") or "").strip() and str(s.get("smtp_user") or "").strip()):
        return False
    return bool(s.get("ms_refresh")) if s.get("smtp_auth") == "ms" else bool(s.get("smtp_pass"))


@chain_step("mail_prepare", "m37_mail_plus")
def _m37_step_mail_prepare(_next, doc_id=None, mahnung_id=None):
    r = _next(doc_id, mahnung_id)
    r["configured"] = mail_configured()
    return r


def mail_send(d):
    """v2.0.9: like m06, but also with Microsoft login (no password stored)"""
    s = get_settings()
    to = (d.get("to") or "").strip()
    if not to or "@" not in to:
        raise ValueError("Bitte eine gültige Empfänger-Adresse angeben.")
    if not mail_configured(s):
        raise ValueError("E-Mail ist noch nicht eingerichtet (Einstellungen → E-Mail).")
    if d.get("mahnung_id"):
        m = q("SELECT * FROM mahnungen WHERE id=?", (d["mahnung_id"],), one=True)
        if not m:
            raise ValueError("Diese Mahnung gibt es nicht mehr.")
        fp = os.path.join(DATA_DIR, m["file"]) if not os.path.isabs(m["file"]) else m["file"]
        att = [(os.path.basename(fp), open(fp, "rb").read())]
        doc_id = m["invoice_id"]
    else:
        doc_id = int(d["doc_id"])
        inv = get_invoice(doc_id)
        path = invoice_pdf_path(inv, s)
        data = render_invoice_pdf(inv, s)
        write_file(path, data)
        att = [(os.path.basename(path), data)]
    try:
        lg = []
        send_mail(to, d.get("cc", ""), d.get("subject", ""), d.get("body", ""), att, log=lg)
        warn = "; ".join(l_[2:] for l_ in lg if l_.startswith("! nicht zugestellt"))
        x("INSERT INTO mail_log (doc_id, mahnung_id, an, betreff, datum, ok, fehler) VALUES (?,?,?,?,?,1,?)",
          (doc_id, d.get("mahnung_id"), to, d.get("subject", ""), now_iso(), warn))
        if not d.get("mahnung_id"):
            x("UPDATE invoices SET versendet_am=? WHERE id=?", (today(), doc_id))
            lock_invoice(doc_id)
        return {"ok": True, "warnung": warn} if warn else {"ok": True}
    except ValueError as e:
        err = f"Versand fehlgeschlagen: {e}"
    except Exception as e:
        err = "Versand fehlgeschlagen: " + mail_error_text(e, smtp_cfg())
    set_setting("mail_status", {"zeit": now_iso(), "ok": False, "fehler": err})
    x("INSERT INTO mail_log (doc_id, mahnung_id, an, betreff, datum, ok, fehler) VALUES (?,?,?,?,?,0,?)",
      (doc_id, d.get("mahnung_id"), to, d.get("subject", ""), now_iso(), err))
    raise ValueError(err)


def mail_test(d):
    over = {k: d.get(k) for k in ("host", "port", "user", "pass", "sec", "from_addr", "from_name", "auth", "verify") if d.get(k) not in (None, "")}
    log = []
    c = smtp_cfg(over)
    to = (d.get("to") or c["from_addr"] or c["user"] or "").strip()
    try:
        send_mail(to, "", "Test - Pfeiffer-Audio Rechnung", "Der E-Mail-Versand funktioniert.\n\nServer: %s:%s\nBenutzer: %s\n" % (c["host"], c["port"], c["user"]),
                  [], over=over, log=log)
        return {"ok": True, "schritte": log, "an": to}
    except Exception as e:
        msg = str(e) if isinstance(e, ValueError) else mail_error_text(e, c)
        log.append("✗ " + msg)
        set_setting("mail_status", {"zeit": now_iso(), "ok": False, "fehler": msg})
        p_ = mail_provider(c["user"], c["host"])
        return {"ok": False, "error": msg, "schritte": log, "anbieter": p_["label"] if p_ else ""}


# ---------------- IMAP: OAuth2 + password fallback ----------------

@chain_step("imap_cfg", "m37_mail_plus")
def _m37_step_imap_cfg(_next, over=None):
    c = _next(over)
    s = get_settings()
    c["auth"] = str((over or {}).get("auth") or s.get("mi_auth") or "pass")
    if c["auth"] == "ms":
        c["pass"] = "(oauth)" if s.get("ms_refresh") else ""
    # same mailbox as for sending -> use that password if none stored for IMAP
    if not c["pass"] and c["auth"] != "ms" and c["user"] and c["user"].lower() == str(s.get("smtp_user") or "").strip().lower():
        try:
            c["pass"] = unprotect_secret(s.get("smtp_pass") or "")
        except Exception:
            pass
    return c


@chain_step("imap_connect", "m37_mail_plus")
def _m37_step_imap_connect(_next, c, timeout=20):
    if c.get("auth") != "ms":
        try:
            return _next(c, timeout)
        except ValueError as e:
            t = str(e)
            p_ = mail_provider(c.get("user"), c.get("host"))
            if "Anmeldung abgelehnt" in t and p_ and p_.get("hint"):
                raise ValueError(t + " Hinweis: " + p_["hint"])
            raise
    if not c["host"] or not c["user"]:
        raise ValueError("Bitte IMAP-Server und Benutzer eintragen.")
    try:
        M = imaplib.IMAP4_SSL(c["host"], c["port"] or 993, timeout=timeout)
    except Exception as e:
        raise ValueError(f"Verbindung zu {c['host']}:{c['port']} fehlgeschlagen: {e}")
    tok = ms_token()
    try:
        M.authenticate("XOAUTH2", lambda _ch: _xoauth2(c["user"], tok).encode())
    except imaplib.IMAP4.error as e:
        try:
            M.logout()
        except Exception:
            pass
        raise ValueError("Microsoft-Anmeldung am Postfach abgelehnt: " + _imap_txt(e) + " – Benutzer muss die angemeldete Adresse sein.")
    return M


@chain_step("imap_status", "m37_mail_plus")
def _m37_step_imap_status(_next, ):
    r = _next()
    s = get_settings()
    if s.get("mi_auth") == "ms":
        r["eingerichtet"] = bool((s.get("mi_host") or "").strip() and (s.get("mi_user") or "").strip() and s.get("ms_refresh"))
        r["passwort"] = bool(s.get("ms_refresh"))
    return r


@chain_step("imap_save", "m37_mail_plus")
def _m37_step_imap_save(_next, d):
    if "auth" in d:
        set_setting("mi_auth", "ms" if d.get("auth") == "ms" else "pass")
    return _next(d)


def _m37_imap_test_route(h, d):
    o = _imap_over(d) or {}
    if d.get("auth"):
        o["auth"] = d["auth"]
    return h._send(200, imap_test(o or None))


# ---------------- routes / boot ----------------

def _m37_boot(d):
    st = d.get("settings") or {}
    for k in ("ms_refresh",):
        st.pop(k, None)
    d["mail_providers"] = MAIL_PROVIDERS
    d["ms_verbunden"] = bool(get_settings().get("ms_refresh"))


def _m37_selftest():
    err = []
    try:
        c = smtp_cfg({"host": " smtp.gmail.com:465 ", "user": "a@gmail.com", "pass": "abcd efgh ijkl mnop"})
        if c["host"] != "smtp.gmail.com" or c["port"] != 465 or _clean_pw(c["pass"], c) != "abcdefghijklmnop":
            err.append("Mail: Konfiguration wird falsch bereinigt")
        if _addr_list("a@x.de; b@y.de") != "a@x.de, b@y.de":
            err.append("Mail: Empfängerliste falsch")
        e = smtplib.SMTPAuthenticationError(535, b"5.7.139 Authentication unsuccessful, basic authentication is disabled.")
        if "OAuth2" not in mail_error_text(e, {"host": "smtp-mail.outlook.com", "user": "x@hotmail.com"}):
            err.append("Mail: Microsoft-Hinweis fehlt")
    except Exception as ex:
        err.append(f"Mail: {ex}")
    return err


HOOK_POST["/api/mail/test"] = lambda h, d: h._send(200, mail_test(d or {}))
HOOK_POST["/api/mail/ms/start"] = lambda h, d: h._send(200, ms_start(d))
HOOK_GET["/api/mail/ms/status"] = lambda h, qs: h._send(200, ms_status())
HOOK_POST["/api/mail/ms/logout"] = lambda h, d: h._send(200, ms_logout())
HOOK_POST["/api/mail/imap/test"] = _m37_imap_test_route
# /api/mail/imap/speichern (m31) calls the global imap_save at request time -> already the wrapper above
HOOK_BOOT.append(_m37_boot)
HOOK_SELFTEST.append(_m37_selftest)
