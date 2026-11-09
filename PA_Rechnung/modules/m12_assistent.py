# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m12_assistent
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# v1.3.0  Beleg-Assistent (learning + checks + optional local LLM) and bank PDF
# ----------------------------------------------------------------------------
import urllib.request
from collections import Counter

ASSIST_TYPES = ("ausgabe", "gehalt", "eigene_rechnung", "anlage", "einnahme")
STOP = set("der die das und oder für fur von mit auf im in an zu zum zur den dem des ein eine einer eines ist sind bei aus nach "
           "bitte vielen dank ihre ihr sie wir uns unser unsere eur euro gmbh co kg ag nr seite datum the and of to".split())


def tokens(text):
    t = (text or "").lower()
    t = re.sub(r"\d{1,3}(?:\.\d{3})*,\d{2}", " ", t)
    t = re.sub(r"\d+", " ", t)
    words = [w for w in re.findall(r"[a-zäöüß][a-zäöüß\-]{2,}", t) if w not in STOP]
    return words[:1500]


def norm_partner(p):
    p = (p or "").lower()
    p = re.sub(r"\b(gmbh|co|kg|ag|ug|e\.?k|mbh|ohg|gbr|inc|ltd|se)\b\.?", " ", p)
    return re.sub(r"[^a-z0-9äöüß]+", " ", p).strip()[:60]


def learn_sample(typ, kategorie, partner, text, beleg_id=None):
    if typ not in ASSIST_TYPES:
        return
    toks = tokens(text)
    if beleg_id and q("SELECT id FROM beleg_learn WHERE beleg_id=?", (beleg_id,), one=True):
        x("UPDATE beleg_learn SET typ=?, kategorie=?, partner=? WHERE beleg_id=?", (typ, kategorie or "", norm_partner(partner), beleg_id))
        MODEL_CACHE.clear()
        return
    if not toks and not partner:
        return
    x("INSERT INTO beleg_learn (typ, kategorie, partner, tokens, beleg_id, created) VALUES (?,?,?,?,?,?)",
      (typ, kategorie or "", norm_partner(partner), json.dumps(toks[:600]), beleg_id, now_iso()))
    MODEL_CACHE.clear()


MODEL_CACHE = {}


def nb_model():
    if MODEL_CACHE.get("m"):
        return MODEL_CACHE["m"]
    rows = q("SELECT typ, kategorie, partner, tokens FROM beleg_learn")
    m = {"n": len(rows), "typ": {}, "kat": {}, "vocab": set(), "partner": {}}
    for r in rows:
        toks = json.loads(r["tokens"] or "[]")
        for key, cls in (("typ", r["typ"]), ("kat", r["kategorie"] if r["typ"] == "ausgabe" else None)):
            if not cls:
                continue
            e = m[key].setdefault(cls, {"docs": 0, "cnt": Counter(), "total": 0})
            e["docs"] += 1
            e["cnt"].update(toks)
            e["total"] += len(toks)
        m["vocab"].update(toks)
        if r["partner"]:
            pm = m["partner"].setdefault(r["partner"], Counter())
            pm[(r["typ"], r["kategorie"] or "")] += 1
    MODEL_CACHE["m"] = m
    return m


def nb_predict(m, key, toks):
    classes = m[key]
    if not classes:
        return None, 0.0
    V = max(1, len(m["vocab"]))
    ndocs = sum(c["docs"] for c in classes.values())
    scores = {}
    for cls, e in classes.items():
        sc = math.log(e["docs"] / ndocs)
        den = e["total"] + V
        for t in toks:
            sc += math.log((e["cnt"].get(t, 0) + 1) / den)
        scores[cls] = sc
    best = max(scores, key=scores.get)
    mx = scores[best]
    tot = sum(math.exp(v - mx) for v in scores.values())
    return best, round(1.0 / tot, 3)


def llm_classify(text, s):
    url = (s.get("ki_url") or "http://127.0.0.1:11434").rstrip("/")
    model = s.get("ki_model") or ""
    if not model:
        tags = json.loads(urllib.request.urlopen(url + "/api/tags", timeout=4).read().decode())
        names = [t["name"] for t in tags.get("models", [])]
        pref = [n for n in names if re.match(r"(qwen|llama|mistral|gemma|phi)", n)]
        model = (pref or names or [""])[0]
        if not model:
            raise RuntimeError("Kein Modell in Ollama installiert.")
    prompt = (
        "Du bist Buchhaltungs-Assistent für einen Kleinunternehmer (Firma: " + (s.get("firma") or "") + ", Inhaber: " + (s.get("inhaber") or "") + ").\n"
        "Ordne den folgenden Beleg ein. Antworte NUR mit JSON: {\"typ\":..., \"kategorie\":..., \"partner\":..., \"datum\":\"JJJJ-MM-TT\", "
        "\"betrag\":Zahl, \"nr\":..., \"sicherheit\":0-1, \"begruendung\":\"kurz\"}.\n"
        "typ ist genau einer von: ausgabe (Eingangsrechnung/Quittung eines Lieferanten an uns), eigene_rechnung (Ausgangsrechnung, "
        "die WIR (" + (s.get("firma") or "") + ") an einen Kunden gestellt haben), gehalt (Gehalts-/Lohnabrechnung oder Lohnsteuerbescheinigung), "
        "einnahme (Gutschrift/Honorar an uns), anlage (Nachweis/Abrechnung als Anhang zu einer Rechnung).\n"
        "kategorie nur bei ausgabe, eine von: " + ", ".join(EUER_KATEGORIEN) + ".\n\nBELEG:\n" + (text or "")[:3500])
    body = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False,
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(url + "/api/generate", body, {"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=int(s.get("ki_timeout") or 45)).read().decode())
    r = json.loads(out.get("response") or "{}")
    r["_model"] = model
    if r.get("typ") not in ASSIST_TYPES:
        r["typ"] = None
    if r.get("kategorie") not in EUER_KATEGORIEN:
        r["kategorie"] = None
    return r


def beleg_checks(r):
    """plausibility checks -> list of warnings"""
    w = []
    s = get_settings()
    typ = r.get("typ")
    betrag = float(r.get("betrag") or 0)
    dat = d_iso(r.get("datum"))
    t = datetime.date.today()
    if not dat:
        w.append("Kein Datum erkannt.")
    elif dat > t + datetime.timedelta(days=30):
        w.append(f"Datum {de_date(dat.isoformat())} liegt in der Zukunft.")
    elif dat.year < t.year - 1:
        w.append(f"Beleg ist von {dat.year} – gehört in ein älteres Steuerjahr.")
    if re.search(r"kontoauszug|alter kontostand|neuer kontostand", (r.get("text") or "")[:2500].lower()):
        w.append("Das sieht nach einem Kontoauszug aus – bitte unter „Bank-Abgleich“ einlesen statt als Beleg.")
    if typ in ("ausgabe", "einnahme") and not betrag:
        w.append("Kein Betrag erkannt.")
    if typ == "gehalt":
        d = r.get("details") or {}
        if not d.get("brutto"):
            w.append("Gehaltsabrechnung ohne Brutto-Betrag.")
        elif float(d.get("lst") or 0) > float(d.get("brutto") or 0) or float(d.get("netto") or 0) > float(d.get("brutto") or 0):
            w.append("Lohnsteuer oder Netto größer als Brutto – Werte prüfen.")
    flat = re.sub(r"\s", "", (r.get("text") or "").lower())
    own_iban = re.sub(r"\s", "", s.get("iban", "")).lower()
    own_ids = [t.lower() for t in re.findall(r"\bDE\d{9}\b|\b\d{3}/\d{4}/\d{4}\b", " ".join(s.get(k, "") for k in ("fuss1", "fuss2", "fuss3", "fuss4")))]
    if typ in ("ausgabe", "einnahme") and flat and ((own_iban and own_iban in flat) or any(t.replace(" ", "") in flat for t in own_ids)) \
            and not r.get("details", {}).get("einvoice"):
        w.append("Enthält deine eigene IBAN/Steuernummer – ist das deine eigene Ausgangsrechnung?")
    if typ in ("ausgabe", "einnahme"):
        nr = (r.get("nr") or "").strip()
        pn = norm_partner(r.get("partner"))
        # v2.1.0: same number from ANOTHER supplier ("1001" is common) is no duplicate - it blocked the automatic booking
        nr_dup = [b for b in (q("SELECT partner FROM belege WHERE nr=? AND typ=?", (nr, typ)) if nr else [])
                  if not pn or not norm_partner(b["partner"]) or norm_partner(b["partner"])[:8] == pn[:8]]
        if nr_dup:
            w.append(f"Beleg-Nr. {nr} ist schon erfasst – Dublette?")
        elif betrag and dat:
            for b in q("SELECT * FROM belege WHERE typ=? AND abs(betrag-?)<0.01 AND julianday(datum) BETWEEN julianday(?)-3 AND julianday(?)+3 AND (quelle IS NULL OR quelle!='bank')",
                       (typ, betrag, dat.isoformat(), dat.isoformat())):
                if not pn or norm_partner(b["partner"])[:8] == pn[:8]:
                    w.append(f"Gleicher Betrag am {de_date(b['datum'])} schon erfasst ({b['partner']}) – Dublette?")
                    break
    if typ == "eigene_rechnung" and r.get("nr") and q("SELECT id FROM invoices WHERE nr=?", (r["nr"],), one=True):
        w.append(f"Rechnung {r['nr']} ist schon im Archiv.")
    return w


def assist(res):
    """combine rules, learned model, partner memory and optional LLM"""
    s = get_settings()
    text = res.get("text") or ""
    m = nb_model()
    src = [{"name": "Regeln", "typ": res["typ"], "kategorie": res.get("kategorie"), "conf": res.get("confidence", 0.5)}]
    votes = Counter()
    votes[res["typ"]] += float(res.get("confidence") or 0.4)
    kat_votes = Counter()
    if res.get("kategorie"):
        kat_votes[res["kategorie"]] += 0.4 if res["kategorie"] != "Sonstige Betriebsausgaben" else 0.1
    if res.get("details", {}).get("einvoice"):
        votes[res["typ"]] += 2.0
    pn = norm_partner(res.get("partner"))
    if pn and pn in m["partner"]:
        (pt, pk), n = m["partner"][pn].most_common(1)[0]
        tot = sum(m["partner"][pn].values())
        c = round(min(0.95, 0.5 + 0.15 * n) * n / tot, 2)
        src.append({"name": f"Gelernt: {res.get('partner')} ({n}× bestätigt)", "typ": pt, "kategorie": pk or None, "conf": c})
        votes[pt] += c * 1.2
        if pk:
            kat_votes[pk] += c * 2
    if m["n"] >= 6 and text:
        toks = tokens(text)
        bt, bc = nb_predict(m, "typ", toks)
        if bt:
            bk, bkc = nb_predict(m, "kat", toks) if bt == "ausgabe" else (None, 0)
            src.append({"name": f"Gelernt aus {m['n']} Belegen", "typ": bt, "kategorie": bk, "conf": bc})
            votes[bt] += bc * min(1.0, m["n"] / 30)
            if bk:
                kat_votes[bk] += bkc * min(1.0, m["n"] / 30)
    if s.get("ki_enabled") and text and (s.get("ki_immer") or max(votes.values()) < 1.2):
        try:
            l = llm_classify(text, s)
            if l.get("typ"):
                try:
                    c = max(0.0, min(1.0, float(str(l.get("sicherheit") or 0.7).replace(",", "."))))
                except Exception:
                    c = 0.7
                if l.get("datum") and not re.match(r"\d{4}-\d{2}-\d{2}", str(l["datum"])):
                    l["datum"] = iso_from_de(str(l["datum"]))
                elif l.get("datum"):
                    # v2.6.3: the model may answer "2025-13-01" / "2025-02-30" - only real dates are taken
                    d_ = d_iso(str(l["datum"]))
                    l["datum"] = d_.isoformat() if d_ else ""
                src.append({"name": f"Dr. Jey ({l['_model']})", "typ": l["typ"], "kategorie": l.get("kategorie"), "conf": round(c, 2),
                            "begruendung": l.get("begruendung", "")})
                votes[l["typ"]] += c * 1.2
                if l.get("kategorie"):
                    kat_votes[l["kategorie"]] += c
                for k in ("partner", "nr", "datum"):
                    if l.get(k) and not res.get(k):
                        res[k] = str(l[k])[:80]
                if l.get("betrag") and not res.get("betrag"):
                    try:
                        res["betrag"] = abs(float(str(l["betrag"]).replace(",", ".")))
                    except Exception:
                        pass
        except Exception as e:
            src.append({"name": "Dr. Jey", "typ": None, "conf": 0, "fehler": f"nicht erreichbar ({str(e)[:60]})"})
    best, bv = votes.most_common(1)[0]
    total = sum(votes.values()) or 1
    conf = round(min(0.99, bv / total * min(1.0, 0.35 + bv / 3)), 2)
    pre_warn = list(res.get("warnungen") or [])     # from the rules (own e-invoice, foreign currency, payslip check ...)
    if res.get("details", {}).get("einvoice"):
        conf = max(conf, 0.97) if not pre_warn else min(conf, float(res.get("confidence") or 0.6))
    locked_rule = res.get("details", {}).get("einvoice") or (res["typ"] == "eigene_rechnung" and res.get("parsed"))
    if best != res["typ"] and best != "eigene_rechnung" and not locked_rule:
        if best == "gehalt" and not res.get("details", {}).get("brutto"):
            res["details"] = salary_fields(text, year_doc="lohnsteuerbescheinigung" in text.lower())
            res["betrag"] = res["details"].get("brutto", 0.0) or res.get("betrag")
        res["hint"] = f"Assistent: als {best} eingeordnet (Regeln sagten {res['typ']}). " + (res.get("hint") or "")
        res["typ"] = best
    if res["typ"] == "ausgabe" and kat_votes:
        res["kategorie"] = kat_votes.most_common(1)[0][0]
    res["assistent"] = {"typ": res["typ"], "kategorie": res.get("kategorie") if res["typ"] == "ausgabe" else None, "sicherheit": conf,
                        "quellen": src, "gelernt": m["n"]}
    res["confidence"] = conf
    # v2.1.0: keep the warnings of the rules - they were overwritten, so the inbox booked e.g. an own invoice
    # that is already in the program automatically as income (counted twice)
    res["warnungen"] = list(dict.fromkeys(pre_warn + beleg_checks(res)))
    return res

# ---------------- Inbox watcher ----------------


def eingang_dir():
    return (get_settings().get("eingang_dir") or "").strip() or os.path.join(DATA_DIR, "Eingang")


SKIP_IN = re.compile(r"^(~\$|\.|thumbs\.db$|desktop\.ini$)|\.(tmp|crdownload|part|partial|download)$", re.I)
EINGANG_LOCK = threading.Lock()
EINGANG_SEEN = {}    # path -> (size, mtime) of the previous scan


def _eingang_claim(d, fn, fp, force):
    """move a finished file out of the inbox -> temp path or None (still being written / in use)
    v2.1.0: a file still open in the scanner or in an Explorer copy (which keeps the OLD mtime) was copied again
    and again on every scan (shutil.move across drives = copy + delete, delete fails) - one orphan temp copy per scan."""
    st_ = os.stat(fp)
    sig = (st_.st_size, st_.st_mtime)
    if not force:
        if time.time() - st_.st_mtime < 5:
            return None
        if EINGANG_SEEN.get(fp) != sig:      # size/time must be unchanged since the previous scan
            EINGANG_SEEN[fp] = sig
            return None
    EINGANG_SEEN.pop(fp, None)
    claim = os.path.join(d, "." + uuid.uuid4().hex[:8] + "_" + fn)     # dot names are skipped by later scans
    try:
        os.rename(fp, claim)      # same folder: fails on Windows while another program has the file open
    except OSError:
        return None
    tmp = _tmp_for(fn)
    try:
        shutil.move(claim, tmp)
    except Exception:
        if os.path.exists(claim):        # not moved: drop a partial copy, give the file its name back
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
                os.rename(claim, fp)
            except Exception:
                pass
        raise
    return tmp


def eingang_scan(force=False):
    s = get_settings()
    if not s.get("auto_eingang") and not force:
        return 0
    d = eingang_dir()
    os.makedirs(d, exist_ok=True)
    thr = float(s.get("auto_schwelle") or 0.9)
    with EINGANG_LOCK:      # background loop and the "Jetzt pruefen" button never work on the same file
        return _eingang_scan_locked(d, s, thr, force)


def _eingang_scan_locked(d, s, thr, force):
    n = 0
    for fn in os.listdir(d):
        m_ = re.match(r"^\.[0-9a-f]{8}_(.+)$", fn)
        if m_ and os.path.isfile(os.path.join(d, fn)) and not os.path.exists(os.path.join(d, m_.group(1))):
            try:      # claim left over after a crash -> give the file its name back
                os.rename(os.path.join(d, fn), os.path.join(d, m_.group(1)))
            except OSError:
                pass
    names = sorted(os.listdir(d))
    for k_ in [k_ for k_ in EINGANG_SEEN if os.path.dirname(k_) != d or os.path.basename(k_) not in names]:
        EINGANG_SEEN.pop(k_, None)
    for fn in names:
        fp = os.path.join(d, fn)
        if not os.path.isfile(fp) or SKIP_IN.search(fn):
            continue
        try:
            tmp = _eingang_claim(d, fn, fp, force)
            if tmp is None:
                continue
            try:
                results_ = prepare_results(analyze_any(tmp, fn), tmp, fn)
            except Exception:
                # v2.0.6: analysis failed -> file goes to <Eingang>/Nicht lesbar (was deleted at the next start)
                traceback.print_exc()
                try:
                    if os.path.exists(tmp):
                        bad_ = os.path.join(d, "Nicht lesbar")
                        os.makedirs(bad_, exist_ok=True)
                        dst_ = os.path.join(bad_, fn)
                        if os.path.exists(dst_):
                            r_, e_ = os.path.splitext(fn)
                            dst_ = os.path.join(bad_, f"{r_}_{uuid.uuid4().hex[:4]}{e_}")
                        shutil.move(tmp, dst_)
                except Exception:
                    traceback.print_exc()
                continue
            for res in results_:
                nm = res.get("filename") or fn
                if res.get("aus"):
                    nm = f"{res['aus']} » {nm}"
                auto = not res.get("needs_password") and res["confidence"] >= thr and not res.get("warnungen") \
                    and res["typ"] in ("ausgabe", "gehalt", "einnahme")
                if auto:
                    r = save_beleg(dict(res, lernen=False))
                    x("INSERT INTO eingang_log (datum, file, typ, betrag, partner, status, beleg_id, invoice_id, info) VALUES (?,?,?,?,?,?,?,?,?)",
                      (now_iso(), nm, res["typ"], res.get("betrag") or 0, res.get("partner", ""), "gebucht", r.get("id"), r.get("invoice_id"),
                       f"{int(res['confidence'] * 100)} % sicher"))
                else:
                    TMP.pop(res.get("token"), None)
                    res.pop("token", None)
                    x("INSERT INTO pending_belege (file, name, result, created) VALUES (?,?,?,?)",
                      (res["tmp"], res.get("filename") or fn, json.dumps(res, ensure_ascii=False, default=str), now_iso()))
                    info = "Passwort nötig" if res.get("needs_password") else ("; ".join(res.get("warnungen") or []) or f"nur {int(res['confidence'] * 100)} % sicher")
                    x("INSERT INTO eingang_log (datum, file, typ, betrag, partner, status, info) VALUES (?,?,?,?,?,?,?)",
                      (now_iso(), nm, res["typ"], res.get("betrag") or 0, res.get("partner", ""), "Passwort" if res.get("needs_password") else "prüfen", info))
                n += 1
        except Exception:
            traceback.print_exc()
    return n


def eingang_loop():
    try:
        if not q("SELECT id FROM beleg_learn LIMIT 1", one=True):
            retrain_from_files()
    except Exception:
        traceback.print_exc()
    while True:
        try:
            eingang_scan()
        except Exception:
            traceback.print_exc()
        time.sleep(20)


def retrain_from_files():
    n = 0
    for b in q("SELECT * FROM belege WHERE typ IN ('ausgabe','gehalt','einnahme','anlage') AND file!='' AND file IS NOT NULL"):
        if q("SELECT id FROM beleg_learn WHERE beleg_id=?", (b["id"],), one=True):
            continue
        fp = os.path.join(DATA_DIR, b["file"])
        text = pdf_text(fp) if fp.lower().endswith(".pdf") and os.path.exists(fp) else ""
        learn_sample(b["typ"], b["kategorie"], b["partner"], text or (b["partner"] or ""), b["id"])
        n += 1
    MODEL_CACHE.clear()
    return n

# ---------------- Bank statement as PDF ----------------


AMT_RE = re.compile(r"([+-]?\s?\d{1,3}(?:\.\d{3})*,\d{2})\s?(-|\+|S|H|€|EUR)?(?:\s?(S|H|€|EUR))?\s*$")
DATE_START = re.compile(r"^\s*(\d{2}\.\d{2}\.(?:\d{2,4})?)\s+(?:(\d{2}\.\d{2}\.(?:\d{2,4})?)\s+)?(.*)$")


def pdf_text_all(path, pw=None):
    if not pypdf:
        return ""
    r, _u = pdf_open(path, pw)
    try:
        out = []
        for pg in r.pages[:60]:
            try:
                out.append(pg.extract_text(extraction_mode="layout") or "")
            except Exception:
                out.append(pg.extract_text() or "")
        return "\n".join(out)
    except Exception:
        return ""


def parse_bank_pdf(path, text=None):
    text = text if text is not None else pdf_text_all(path)
    if ocr_need(text) and ocr_available():
        try:
            t_ = ocr_file(path)
            text = t_ if len(t_.strip()) > len(text.strip()) else text
        except Exception:
            if not text.strip():
                raise ValueError("Im PDF wurde kein Text gefunden, Texterkennung fehlgeschlagen: " + (OCR_LAST.get("fehler") or "?"))
    if not text.strip():
        raise ValueError("Im PDF wurde kein Text gefunden (Scan ohne Texterkennung).")
    years = re.findall(r"\b(20\d{2})\b", text)
    year = Counter(years).most_common(1)[0][0] if years else str(datetime.date.today().year)
    full = [d_ for d_ in (iso_from_de(x_) for x_ in re.findall(r"\b\d{1,2}\.\d{1,2}\.20\d{2}\b", text)) if d_]
    ref = max(full) if full else None
    lines = text.split("\n")
    skip = re.compile(r"\b(alter kontostand|neuer kontostand|kontostand|saldo|übertrag|uebertrag|summe|seite \d+|blatt \d+|iban|bic|kontoauszug|zeitraum|"
                      r"buchungstag|wert|valuta|vorgang|betrag in|soll\s+haben)\b", re.I)
    skip_tx = re.compile(r"\b(alter|neuer) (kontostand|saldo)\b|\bkontostand (am|vom|per)\b|\b(übertrag|uebertrag)\b|\bsaldovortrag\b|"
                         r"\bdispo|\bkreditrahmen\b|^\s*\d{2}\.\d{2}\.\d{2,4}\s*-\s*\d{2}\.\d{2}\.\d{2,4}", re.I)
    foot = re.compile(r"(c24 bank gmbh|ust\.?-id|seite \d+ von \d+|speicherstraße|frankfurt am main|kontoauszug \d{2}/\d{4})", re.I)
    raw = []
    cur = None
    for ln in lines:
        if not ln.strip():
            continue
        m = DATE_START.match(ln)
        am = AMT_RE.search(ln)
        if m and am and not skip_tx.search(ln):
            dat = m.group(1)
            if len(dat) == 6:
                y_ = int(ref[:4]) if ref else int(year)
                if ref and int(dat[3:5]) > int(ref[5:7]):
                    y_ -= 1
                dat += str(y_)
            iso = iso_from_de(dat)
            if not iso:
                continue
            val = parse_amount(am.group(1).replace(" ", ""))
            suf = " ".join(v for v in (am.group(2), am.group(3)) if v)
            explicit = am.group(1).strip().startswith(("-", "+")) or "-" in (am.group(2) or "") or "S" in suf.split() or "H" in suf.split()
            if "S" in suf.split() or (am.group(2) == "-"):
                val = -abs(val)
            elif "H" in suf.split():
                val = abs(val)
            desc = m.group(3)[:am.start() - m.start(3)] if am.start() > m.start(3) else m.group(3)
            cur = {"datum": iso, "betrag": val, "explicit": explicit, "col": am.start(), "text": [re.sub(r"\s{2,}", " | ", desc.strip())]}
            raw.append(cur)
        elif cur and not skip.search(ln) and not foot.search(ln) and not AMT_RE.search(ln):
            t = re.sub(r"\s{2,}", " ", ln.strip())
            if t and len(cur["text"]) < 6:
                cur["text"].append(t)
        elif am and skip.search(ln):
            cur = None
    if not raw:
        raise ValueError("Keine Buchungszeilen erkannt. Bitte den Auszug als CSV exportieren oder ein anderes PDF versuchen.")
    # amounts without sign: decide by column (two columns = Soll/Haben)
    unsigned = [r for r in raw if not r["explicit"]]
    if unsigned and len(unsigned) == len(raw):
        cols = sorted({r["col"] for r in unsigned})
        if len(cols) > 1 and cols[-1] - cols[0] > 6:
            mid = (cols[0] + cols[-1]) / 2
            for r in unsigned:
                r["betrag"] = -abs(r["betrag"]) if r["col"] < mid else abs(r["betrag"])
    out = []
    seen = {}
    for r in raw:
        first = r["text"][0].split(" | ")
        kind = first[0] if first else ""
        name = ""
        rest = r["text"][1:]
        if len(first) > 1:
            name = first[1]
        elif rest:
            name, rest = rest[0], rest[1:]
        if re.match(r"(lastschrift|überweisung|ueberweisung|gutschrift|dauerauftrag|kartenzahlung|sepa|zahlungseingang|echtzeit)", kind.lower()) and not name and rest:
            name, rest = rest[0], rest[1:]
        if not name:
            name, kind = kind, ""
        mk = re.match(r"(sepa[- ]?[a-zäöü\-]+|lastschrift|überweisung|ueberweisung|gutschrift|kartenzahlung|dauerauftrag|zahlungseingang|"
                      r"echtzeit-?überweisung|bankgebühren|entgelt)\s+(.{3,})$", name, re.I)
        if mk and not kind:
            kind, name = mk.group(1), mk.group(2)
        zweck = " ".join([kind] + rest).strip()
        key = f"{r['datum']}|{r['betrag']:.2f}|{name}|{zweck}"
        seen[key] = seen.get(key, 0) + 1
        out.append({"hash": hashlib.sha1(f"{key}|{seen[key]}".encode("utf-8")).hexdigest(), "datum": r["datum"], "betrag": round(r["betrag"], 2),
                    "name": name[:80], "zweck": zweck[:240], "iban": ""})
    return out


def learn_correction(d):
    """a beleg was edited -> remember the corrected classification"""
    if d.get("typ") not in ASSIST_TYPES:
        return
    bid = int(d["id"])
    if q("SELECT id FROM beleg_learn WHERE beleg_id=?", (bid,), one=True):
        x("UPDATE beleg_learn SET typ=?, kategorie=?, partner=? WHERE beleg_id=?",
          (d["typ"], d.get("kategorie", "") if d["typ"] == "ausgabe" else "", norm_partner(d.get("partner")), bid))
    else:
        b = q("SELECT file FROM belege WHERE id=?", (bid,), one=True)
        fp = os.path.join(DATA_DIR, b["file"]) if b and b["file"] else ""
        text = pdf_text(fp) if fp.lower().endswith(".pdf") and os.path.exists(fp) else ""
        learn_sample(d["typ"], d.get("kategorie", "") if d["typ"] == "ausgabe" else "", d.get("partner"), text, bid)
    MODEL_CACHE.clear()


def assist_status():
    m = nb_model()
    s = get_settings()
    per = {t: (m["typ"].get(t) or {}).get("docs", 0) for t in ASSIST_TYPES}
    return {"gelernt": m["n"], "pro_typ": per, "partner": len(m["partner"]), "ki_enabled": bool(s.get("ki_enabled")),
            "auto_eingang": bool(s.get("auto_eingang")), "eingang_dir": eingang_dir(),
            "pending": q("SELECT COUNT(*) n FROM pending_belege", one=True)["n"],
            "log": q("SELECT * FROM eingang_log ORDER BY id DESC LIMIT 30"),
            "top_partner": [{"partner": k, "typ": v.most_common(1)[0][0][0], "kategorie": v.most_common(1)[0][0][1], "n": sum(v.values())}
                            for k, v in sorted(m["partner"].items(), key=lambda kv: -sum(kv[1].values()))[:15]]}


def pending_list():
    out = []
    for r in q("SELECT * FROM pending_belege ORDER BY id"):
        fp = os.path.join(DATA_DIR, r["file"])
        if not os.path.exists(fp):
            x("DELETE FROM pending_belege WHERE id=?", (r["id"],))
            continue
        res = json.loads(r["result"] or "{}")
        tok = next((k for k, v in list(TMP.items()) if v.get("path") == fp), None)
        if not tok:
            tok = uuid.uuid4().hex
            TMP[tok] = {"path": fp, "name": r["name"]}
        res.update(token=tok, tmp=r["file"], pending_id=r["id"], filename=r["name"], eingang=r["created"])
        out.append(res)
    return out
