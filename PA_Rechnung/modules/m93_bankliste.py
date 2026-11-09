# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m93_bankliste (v2.3.1)
# Bank-Bibliothek fuer Bankabruf und Zugang zur Bank: alle deutschen Bankleitzahlen
# (Name, BIC, Ort) plus bekannte FinTS-PIN/TAN-Server-Adressen - die Bank wird aus
# der Liste GEWAEHLT statt BLZ und Adresse abzutippen.
# Daten: assets/banken_de.json
#   - Bankleitzahlen/BIC/Name: Deutsche Bundesbank (ueber Paket bankdata-germany)
#   - FinTS-Adressen: fints-institute-db (CC0); Atruvia (Volks-/Raiffeisenbanken) und
#     ING auf die heutigen Adressen umgestellt; fehlende Adressen bei Genossenschafts-
#     banken (BIC GENODE...) als "vermutet" Atruvia eingetragen.
# Routen:
#   GET /api/bl/suche?q=...&n=40   -> Treffer (Name, Ort, BLZ, BIC, Teil-IBAN)
#   GET /api/bl/blz?blz=...        -> eine Bank (auch aus IBAN "DE.." ableitbar)
#   GET /api/bl/eigene             -> Bank zur IBAN aus Firma & Bank
#   GET /api/bl/info               -> Stand / Quelle / Anzahl
# v1.1.0 (v2.3.1): die Bank der Rechnungs-IBAN (Einstellungen -> Firma & Bank) wird
#   automatisch fuer den Bankabruf uebernommen: mit FinTS -> BLZ + Server-Adresse
#   vorausgefuellt; ohne FinTS (z. B. C24 Bank) -> PSD2-Bank vorbelegt. Folgt der IBAN,
#   solange der Nutzer die Bank nicht selbst geaendert hat (Merker m93_auto_blz).
# Autor: T. Pfeiffer

M93_VERSION = "1.1.0"
M93 = {"data": None, "lock": threading.Lock()}

# login hints per banking group (shown under "Benutzerkennung")
M93_LOGIN_HINT = {
    "sparkasse": "Sparkasse: Anmeldename oder Legitimations-ID aus dem Online-Banking.",
    "vr": "Volks-/Raiffeisenbank: VR-NetKey oder selbst vergebener Alias.",
    "": "Dieselbe Kennung wie beim Online-Banking-Login der Bank.",
}


def _m93_group(name, url):
    u = (url or "").lower()
    n = (name or "").lower()
    if "s-fints-pt" in u or "sparkasse" in n or "landesbank" in n:
        return "sparkasse"
    if "atruvia" in u or "fiducia" in u or "gad.de" in u:
        return "vr"
    return ""


def m93_load():
    with M93["lock"]:
        if M93["data"] is not None:
            return M93["data"]
        p = res_path("assets", "banken_de.json")
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            traceback.print_exc()
            raw = {"banken": [], "urls": [], "stand": "", "quelle": ""}
        urls = raw.get("urls") or []
        banken = []
        for r in raw.get("banken") or []:
            blz, name, bic, ort, ui, q = (list(r) + ["", "", "", "", -1, 0])[:6]
            url = urls[ui] if isinstance(ui, int) and 0 <= ui < len(urls) else ""
            b = {"blz": str(blz), "name": str(name or "").strip(), "bic": str(bic or "").strip(), "ort": str(ort or "").strip(),
                 "url": url, "url_quelle": {1: "liste", 2: "vermutet"}.get(int(q or 0), "")}
            b["gruppe"] = _m93_group(b["name"], url)
            b["_s"] = (b["name"] + " " + b["ort"] + " " + b["blz"] + " " + b["bic"]).lower()
            banken.append(b)
        by_blz = {}
        for b in banken:
            by_blz.setdefault(b["blz"], b)
        M93["data"] = {"banken": banken, "blz": by_blz, "stand": raw.get("stand") or "", "quelle": raw.get("quelle") or ""}
        return M93["data"]


def _m93_pub(b):
    if not b:
        return None
    d = {k: v for k, v in b.items() if not k.startswith("_")}
    d["login_hinweis"] = M93_LOGIN_HINT.get(b.get("gruppe") or "", M93_LOGIN_HINT[""])
    return d


def m93_blz_from(text):
    """BLZ from a BLZ ('500 240 24') or a German IBAN ('DE72 5002 4024 ...')."""
    t = re.sub(r"\s", "", str(text or "")).upper()
    if re.fullmatch(r"DE\d{20}", t):
        return t[4:12]
    if re.fullmatch(r"\d{8}", t):
        return t
    return ""


def m93_bank(blz_or_iban):
    blz = m93_blz_from(blz_or_iban)
    return _m93_pub(m93_load()["blz"].get(blz)) if blz else None


def m93_suche(qtxt, n=40):
    d = m93_load()
    qtxt = str(qtxt or "").strip().lower()
    n = max(1, min(200, int(n or 40)))
    if not qtxt:
        return []
    blz = m93_blz_from(qtxt)
    if blz:
        b = d["blz"].get(blz)
        return [_m93_pub(b)] if b else []
    digits = re.sub(r"\s", "", qtxt)
    words = [w for w in re.split(r"\s+", qtxt) if w]
    hits = []
    for b in d["banken"]:
        if digits.isdigit():
            if b["blz"].startswith(digits):
                hits.append((0, b))
            continue
        if all(w in b["_s"] for w in words):
            nm = b["name"].lower()
            rank = 0 if nm.startswith(qtxt) else 1 if any(nm.startswith(w) for w in words) else 2
            rank += 0 if b["url"] else 3          # banks with a known FinTS address first
            hits.append((rank, b))
    hits.sort(key=lambda x: (x[0], x[1]["name"], x[1]["ort"]))
    seen, out = set(), []
    for _, b in hits:
        k = (b["name"], b["ort"], b["bic"], b["url"])
        if k in seen:                      # many identical branch lines -> one entry
            continue
        seen.add(k)
        out.append(_m93_pub(b))
        if len(out) >= n:
            break
    return out


def m93_eigene():
    s = get_settings()
    iban = str(s.get("iban") or "")
    b = m93_bank(iban)
    weg = "fints" if b and b.get("url") else "psd2" if b else ""
    return {"ok": bool(b), "iban": iban, "iban_fmt": " ".join(re.findall(".{1,4}", re.sub(r"\s", "", iban).upper())),
            "bank": b, "weg": weg, "auto": bool(b) and str(s.get("fints_blz") or "") == str(s.get("m93_auto_blz") or "") == b["blz"]}


def m93_sync_own():
    """Fill the bank access from the invoice IBAN - only fields the user has not set himself."""
    s = get_settings()
    b = m93_bank(s.get("iban") or "")
    if not b:
        return False
    cur = str(s.get("fints_blz") or "")
    auto = str(s.get("m93_auto_blz") or "")
    if cur and cur != auto:
        return False                    # bank chosen by hand -> leave it
    changed = False
    if cur != b["blz"]:
        set_setting("fints_blz", b["blz"])
        changed = True
        if cur:                         # invoice bank changed -> forget the old bank's TAN choice / accounts
            for k in ("fints_state", "fints_tan_mech", "fints_tan_medium", "fints_konto"):
                set_setting(k, "")
            for k in ("fints_konten", "fints_tan_optionen", "fints_tan_medien"):
                set_setting(k, [])
    old_url = str(s.get("fints_url") or "")
    auto_url = str(s.get("m93_auto_url") or "")
    if (not old_url or old_url == auto_url) and old_url != b["url"]:
        set_setting("fints_url", b["url"])
        set_setting("m93_auto_url", b["url"])
        changed = True
    if not b["url"] and not s.get("eb_bank"):
        set_setting("eb_bank", b["name"])          # no FinTS -> PSD2 with this bank
        changed = True
    if auto != b["blz"]:
        set_setting("m93_auto_blz", b["blz"])
    return changed


def _m93_start():
    try:
        m93_sync_own()
    except Exception:
        traceback.print_exc()


HOOK_START.append(_m93_start)


def m93_info():
    d = m93_load()
    return {"ok": True, "version": M93_VERSION, "anzahl": len(d["banken"]), "mit_fints": sum(1 for b in d["banken"] if b["url"]),
            "stand": d["stand"], "quelle": d["quelle"]}


HOOK_GET["/api/bl/suche"] = lambda h, qs: h._send(200, m93_suche(qs.get("q"), qs.get("n") or 40))
HOOK_GET["/api/bl/blz"] = lambda h, qs: h._send(200, {"ok": True, "bank": m93_bank(qs.get("blz"))})
HOOK_GET["/api/bl/eigene"] = lambda h, qs: h._send(200, m93_eigene())
HOOK_GET["/api/bl/info"] = lambda h, qs: h._send(200, m93_info())


def _m93_selftest():
    err = []
    try:
        d = m93_load()
        if len(d["banken"]) < 1000:
            err.append(f"m93: Bankliste zu klein ({len(d['banken'])})")
        if m93_blz_from("DE00 5002 4024 0000 0000 00") != "50024024":
            err.append("m93: BLZ aus IBAN falsch")
        r = m93_suche("Sparkasse KölnBonn")
        if not r or "Sparkasse" not in r[0]["name"]:
            err.append("m93: Suche Sparkasse liefert nichts")
        if m93_bank("DE00 5002 4024 0000 0000 00")["name"] != "C24 Bank":
            err.append("m93: IBAN der Rechnung nicht als C24 Bank erkannt")
        b = m93_bank("37050198")
        if not b or not b["url"].startswith("https://"):
            err.append("m93: BLZ 37050198 ohne FinTS-Adresse")
    except Exception as e:
        err.append(f"m93 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m93_selftest)
