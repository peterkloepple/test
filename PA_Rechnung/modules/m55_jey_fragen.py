# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m55_jey_fragen
# "Frag Dr. Jey": Fragen in Alltagssprache zu Umsatz, Ausgaben, Steuer, Kontostand ...
# Sicherer Ansatz: KEIN SQL von der KI. Absicht wird per Regeln (optional lokale KI -> JSON) erkannt,
# die Zahlen kommen ausschliesslich aus vorhandenen Programmfunktionen.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M55_INTENTS = {
    "umsatz": "Umsatz eines Jahres oder Monats",
    "umsatz_kunde": "Umsatz mit einem bestimmten Kunden",
    "ausgaben": "Ausgaben gesamt, einer Kategorie oder bei einem Lieferanten",
    "offene": "offene / überfällige Rechnungen",
    "top_kunden": "größte Kunden nach Umsatz",
    "vergleich": "Vergleich zweier Jahre",
    "gewinn": "Gewinn (EÜR) eines Jahres",
    "steuer": "Steuer, Nachzahlung, Rücklage",
    "fixkosten": "laufende Fixkosten pro Monat",
    "kontostand": "aktueller Kontostand",
    "liquiditaet": "Liquiditätsvorschau / reicht das Geld",
    "ku": "Kleinunternehmergrenzen",
    "hilfe": "Beispiele / was kann ich fragen",
}
M55_BEISPIELE = ["Wie viel Umsatz hatte ich 2025?", "Was habe ich dieses Jahr mit Kunde Müller umgesetzt?",
                 "Wie hoch waren meine Softwarekosten letztes Jahr?", "Welche Rechnungen sind noch offen?",
                 "Wer sind meine größten Kunden?", "Vergleich 2025 mit 2026", "Wie viel Gewinn habe ich gemacht?",
                 "Muss ich Steuern nachzahlen?", "Wie hoch sind meine Fixkosten?", "Wie ist mein Kontostand?",
                 "Reicht das Geld die nächsten Monate?", "Bin ich noch Kleinunternehmer?"]
M55_KAT = [
    (("software", "lizenz", "lizenzen", "programme"), "Software / Lizenzen"),
    (("telefon", "internet", "handy", "mobilfunk", "telekommunikation"), "Telekommunikation / Internet"),
    (("hotel", "übernachtung", "uebernachtung"), "Übernachtung / Reisenebenkosten"),
    (("fahrt", "fahrten", "tanken", "tank", "benzin", "diesel", "reise", "bahn", "zug", "parken"), "Fahrtkosten / Reise"),
    (("kleinmaterial", "werkzeug", "verbrauch"), "Arbeitsmittel (Kleinmaterial)"),
    (("material", "waren", "ware", "stahl", "rohstoff"), "Waren / Material"),
    (("fremdleistung", "fremdleistungen", "subunternehmer"), "Fremdleistungen"),
    (("equipment", "gwg", "gerät", "geräte", "geraete", "technik"), "Arbeitsmittel / Equipment (GWG)"),
    (("leasing", "mietgerät", "grover"), "Miete / Leasing Geräte"),
    (("miete", "raumkosten", "werkstattmiete", "büromiete"), "Raumkosten / Miete"),
    (("werbung", "marketing", "anzeigen", "flyer"), "Werbung / Marketing"),
    (("fortbildung", "seminar", "schulung", "fachliteratur", "bücher", "buch", "kurs"), "Fortbildung / Fachliteratur"),
    (("steuerberater", "steuerberatung", "anwalt", "rechtsberatung", "buchführung"), "Rechts- und Steuerberatung"),
    (("büro", "buero", "porto", "briefmarken", "papier"), "Bürobedarf / Porto"),
    (("versicherung", "versicherungen", "beiträge", "beitraege", "gema", "ihk", "kammer"), "Versicherungen / Beiträge"),
    (("bankgebühr", "bankgebühren", "kontoführung", "kontofuehrung", "bank"), "Bankgebühren"),
    (("bewirtung", "restaurant", "essen", "geschäftsessen"), "Bewirtung (70%)"),
    (("abschreibung", "afa"), "Abschreibung (AfA)"),
]
M55_STOP = {"gmbh", "und", "der", "die", "das", "audio", "firma", "herr", "frau", "kunde", "kunden", "mbh", "co", "kg", "ug",
            "e.v.", "ev", "von", "mit", "the", "service", "services", "gbr", "ohg", "ag", "team", "studio", "media"}


def _m55_low(t):
    return " " + re.sub(r"\s+", " ", (t or "").lower().replace("ß", "ss").replace("?", " ").replace("!", " ").replace(",", " ")) + " "


def m55_years(ql, now_y):
    ys = [int(y) for y in re.findall(r"\b(20\d\d)\b", ql)]
    if re.search(r"vorletzt", ql):
        ys.append(now_y - 2)
    if re.search(r"letzte[snm]? jahr|vorjahr|im letzten jahr|letztes jahr", ql):
        ys.append(now_y - 1)
    if re.search(r"dieses jahr|diesem jahr|dies jahr|heuer|aktuellen jahr|laufenden jahr|bisher|in diesem jahr", ql):
        ys.append(now_y)
    out = []
    for y in ys:
        if y not in out:
            out.append(y)
    return out


def m55_month(ql, ref):
    names = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"]
    alt = {"maerz": 3, "marz": 3, "jan ": 1, "feb ": 2, "aug ": 8, "sept": 9, "okt ": 10, "nov ": 11, "dez ": 12}
    for i, n in enumerate(names):
        if re.search(r"\b" + n + r"\b", ql):
            return i + 1
    for k, v in alt.items():
        if " " + k in ql:
            return v
    if "letzten monat" in ql or "vormonat" in ql:
        return add_months(datetime.date(ref.year, ref.month, 1), -1).month
    if "diesen monat" in ql or "diesem monat" in ql or "aktuellen monat" in ql:
        return ref.month
    return None


def m55_customer(ql, hint=None):
    """best customer whose name/number appears in the question (or matches the KI hint)"""
    best, bs = None, 0
    text = _m55_low(hint) if hint else ql
    for c in q("SELECT id, kdnr, firma, name FROM customers"):
        if c["kdnr"] and re.search(r"\b" + re.escape(c["kdnr"].lower()) + r"\b", text):
            return c
        sc = 0
        for field in (c["firma"], c["name"]):
            for tok in re.findall(r"[a-zäöüß0-9&\-]{3,}", (field or "").lower().replace("ß", "ss")):
                if tok in M55_STOP or len(tok) < 4:
                    continue
                if re.search(r"\b" + re.escape(tok[:max(4, len(tok) - 2)]), text):
                    sc += len(tok)
        if sc > bs:
            best, bs = c, sc
    return best if bs >= 4 else None


def m55_kategorie(ql, hint=None):
    text = _m55_low(hint) if hint else ql
    if hint:
        for k in EUER_KATEGORIEN:
            if k.lower() == hint.lower():
                return k
    for keys, kat in M55_KAT:
        for k in keys:
            if re.search(r"\b" + re.escape(k), text):
                return kat
    return None


def m55_partner(ql):
    m = re.search(r"\b(?:bei|von|an)\s+([a-zäöü0-9&.\- ]{3,30}?)(?:\s+(?:im|in|20\d\d|letzt|dies|ausgegeben|bezahlt|gezahlt)|\s*$)", ql.strip())
    if not m:
        return None
    p = m.group(1).strip()
    if p in M55_STOP or len(p) < 3:
        return None
    if q("SELECT id FROM belege WHERE typ='ausgabe' AND lower(partner) LIKE ? LIMIT 1", ("%" + p + "%",), one=True):
        return p
    return None


def m55_rules(question):
    t = datetime.date.today()
    ql = _m55_low(question)
    ys = m55_years(ql, t.year)
    p = {"jahr": ys[0] if ys else None, "jahr2": ys[1] if len(ys) > 1 else None, "monat": m55_month(ql, t)}
    if not ys and ("letzten monat" in ql or "vormonat" in ql) and t.month == 1:
        p["jahr"] = t.year - 1   # v2.0.6: "letzten Monat" im Januar = Dezember des Vorjahres
    has = lambda *ws: any(re.search(w, ql) for w in ws)
    cust = m55_customer(ql)
    kat = m55_kategorie(ql)
    cand = []
    if has(r"\bhilfe\b", r"was kannst", r"beispiel", r"wie funktioniert"):
        cand.append(("hilfe", 3))
    if has(r"kontostand", r"\bsaldo\b", r"guthaben", r"auf dem konto", r"wie viel geld hab"):
        cand.append(("kontostand", 3))
    if has(r"liquidit", r"reicht (das|mein) geld", r"engpass", r"nächsten (wochen|monate)", r"naechsten (wochen|monate)", r"geld knapp", r"vorschau"):
        cand.append(("liquiditaet", 3))
    if has(r"\boffen", r"unbezahlt", r"ausstehend", r"überfällig", r"ueberfaellig", r"noch nicht bezahlt", r"schuldet", r"wer muss (mir )?noch"):
        cand.append(("offene", 3))
    if has(r"kleinunternehmer", r"§ ?19", r"umsatzgrenze", r"\bgrenze\b", r"25[.]?000", r"100[.]?000"):
        cand.append(("ku", 3))
    if has(r"steuer", r"nachzahl", r"rücklage", r"ruecklage", r"finanzamt", r"vorauszahlung"):
        cand.append(("steuer", 2 if kat else 3))
    if has(r"fixkosten", r"laufende kosten", r"monatliche kosten", r"feste kosten", r"regelmässige (kosten|ausgaben)", r"regelmaessige"):
        cand.append(("fixkosten", 3))
    if has(r"gewinn", r"überschuss", r"ueberschuss", r"\beür\b", r"\beuer\b", r"was bleibt"):
        cand.append(("gewinn", 3))
    if has(r"(grösst|groesst|grösste|beste|wichtigste|top)\w* kunden", r"\btop\s?\d*\b", r"meisten umsatz", r"umsatzstärkst"):
        cand.append(("top_kunden", 3))
    if (len(ys) >= 2 and has(r"vergleich", r"\bvs\b", r"gegenüber", r"gegenueber", r"im vergleich", r"mehr als", r"weniger als", r"\bmit\b")) or \
            has(r"vergleich.*jahr", r"jahresvergleich"):
        cand.append(("vergleich", 3 if len(ys) >= 2 else 2))
    if has(r"ausgabe", r"kosten", r"ausgegeben", r"aufwand", r"bezahlt für", r"gezahlt für", r"\bbezahlt\b", r"\bgezahlt\b"):
        cand.append(("ausgaben", 3 if (kat or m55_partner(ql)) else 2))
    if cust and has(r"umsatz", r"umgesetzt", r"verdient", r"rechnung", r"bezahlt", r"wie viel", r"wieviel", r"eingenommen"):
        cand.append(("umsatz_kunde", 4))
    if has(r"umsatz", r"umgesetzt", r"einnahmen", r"erlöse", r"erloese", r"eingenommen", r"verdient", r"verkauft"):
        cand.append(("umsatz", 2))
    if not cust and not p.get("monat") and any(c[0] == "umsatz" for c in cand):
        mk = re.search(r"\b(?:mit|für|fuer|von)\s+(?:(?:dem\s+)?(?:kunden?|firma|herrn?|frau)\s+)?([a-zäöü][\w&.\-]{2,})", ql)
        if mk and mk.group(1) not in M55_STOP | {"dem", "den", "der", "allen", "meinen", "meiner", "mir", "uns", "jahr", "monat",
                                                  "rechnungen", "diesem", "dieses", "letztem", "letztes", "kunden",
                                                  "januar", "februar", "märz", "maerz", "marz", "april", "mai", "juni", "juli", "august",
                                                  "september", "oktober", "november", "dezember", "quartal"} \
                and not re.fullmatch(r"20\d\d", mk.group(1)):
            cand.append(("umsatz_kunde", 4))
            p["kunde_id"] = None
            p["kunde_text"] = mk.group(1)
    if not cand:
        return {"intent": None, "score": 0, "params": p}
    order = list(M55_INTENTS)
    intent, score = sorted(cand, key=lambda c: (-c[1], order.index(c[0])))[0]
    if cust:
        p["kunde_id"] = cust["id"]
    if intent == "ausgaben":
        p["kategorie"] = kat
        p["partner"] = m55_partner(ql) if not kat else None
    if intent == "top_kunden":
        m = re.search(r"\btop\s?(\d{1,2})\b|\b(\d{1,2}) (grösst|groesst|best|wichtigst)", ql)
        p["n"] = int(next(g for g in m.groups() if g and g.isdigit())) if m else 5
    return {"intent": intent, "score": score, "params": p}

# ---------------------------------------------------------------------------
# local KI (Ollama) - only for intent JSON and for phrasing, never for numbers
# ---------------------------------------------------------------------------


def _m55_model(s):
    url = (s.get("ki_url") or "http://127.0.0.1:11434").rstrip("/")
    model = s.get("ki_model") or ""
    if not model:
        tags = json.loads(urllib.request.urlopen(url + "/api/tags", timeout=4).read().decode())
        names = [t_["name"] for t_ in tags.get("models", [])]
        pref = [n for n in names if re.match(r"(qwen|llama|mistral|gemma|phi)", n)]
        model = (pref or names or [""])[0]
    if not model:
        raise RuntimeError("Kein Modell in Ollama installiert.")
    return url, model


def m55_llm(prompt, s, as_json=False):
    url, model = _m55_model(s)
    body = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if as_json:
        body["format"] = "json"
    req = urllib.request.Request(url + "/api/generate", json.dumps(body).encode(), {"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=min(int(s.get("ki_timeout") or 45), 40)).read().decode())
    return (out.get("response") or "").strip(), model


def m55_ki_intent(question, s):
    kunden = ", ".join((c["firma"] or c["name"] or "")[:30] for c in q("SELECT firma, name FROM customers LIMIT 80"))
    prompt = ("Du übersetzt Fragen eines Kleinunternehmers an sein Buchhaltungsprogramm in eine Absicht. Heute ist "
              f"{de_date(today())}. Antworte NUR mit JSON: {{\"intent\":..., \"kunde\":Text oder null, \"jahr\":Zahl oder null, "
              "\"jahr2\":Zahl oder null, \"monat\":1-12 oder null, \"kategorie\":Text oder null, \"partner\":Text oder null}.\n"
              "intent ist genau einer von: " + "; ".join(f"{k} = {v}" for k, v in M55_INTENTS.items()) + "; unklar = passt zu nichts.\n"
              "kategorie nur bei ausgaben, eine von: " + ", ".join(EUER_KATEGORIEN) + ".\n"
              "Bekannte Kunden: " + kunden + "\nBerechne KEINE Zahlen.\n\nFRAGE: " + question[:400])
    txt, model = m55_llm(prompt, s, True)
    r = json.loads(txt or "{}")
    it = r.get("intent")
    if it not in M55_INTENTS:
        return None
    t = datetime.date.today()
    p = {"jahr": None, "jahr2": None, "monat": None}
    for k in ("jahr", "jahr2"):
        try:
            v = int(r.get(k) or 0)
            p[k] = v if 2000 <= v <= t.year + 1 else None
        except Exception:
            pass
    try:
        mo = int(r.get("monat") or 0)
        p["monat"] = mo if 1 <= mo <= 12 else None
    except Exception:
        pass
    if r.get("kunde"):
        c = m55_customer(_m55_low(question), str(r["kunde"]))
        p["kunde_id"] = c["id"] if c else None
        if not c and it == "umsatz_kunde":
            p["kunde_text"] = str(r["kunde"])[:40]
    if it == "ausgaben":
        p["kategorie"] = m55_kategorie(_m55_low(question), str(r.get("kategorie") or "")) if r.get("kategorie") else m55_kategorie(_m55_low(question))
        p["partner"] = str(r.get("partner"))[:40] if r.get("partner") and not p["kategorie"] else None
    if it == "top_kunden":
        p["n"] = 5
    return {"intent": it, "score": 2, "params": p, "model": model}


def _m55_nums(t):
    return {re.sub(r"[.,]", "", n).lstrip("0") for n in re.findall(r"\d[\d.,]*\d|\d", t or "")}


def m55_ki_phrase(question, res, s):
    facts = "\n".join(f"- {z['label']}: {z['wert']}" for z in res["zahlen"]) + "\n" + \
            "\n".join(f"- {l['label']}: {l['wert']}" for l in res.get("liste", [])[:6])
    prompt = ("Du bist Dr. Jey, der freundliche Assistent im Buchhaltungsprogramm. Beantworte die Frage in höchstens zwei kurzen "
              "deutschen Sätzen in der Du-Form. Verwende AUSSCHLIESSLICH die folgenden Fakten und schreibe Zahlen exakt so wie angegeben. "
              "Erfinde keine weiteren Zahlen, Daten oder Vergleiche.\n\nFRAGE: " + question[:300] + "\n\nFAKTEN:\n" + facts +
              "\nBisherige Antwort (sachlich): " + res["antwort"])
    txt, model = m55_llm(prompt, s, False)
    txt = re.sub(r"\s+", " ", txt).strip().strip('"')
    allowed = _m55_nums(facts + " " + res["antwort"] + " " + question)
    bad = [n for n in _m55_nums(txt) if n and n not in allowed]
    if not txt or bad or len(txt) > 600:
        return None
    return txt

# ---------------------------------------------------------------------------
# Answers (numbers only from existing functions)
# ---------------------------------------------------------------------------


def _z(label, v, kind="eur"):
    return {"label": label, "wert": money(v) if kind == "eur" else (num_de(v, 1) + " %" if kind == "pct" else str(v)), "raw": v}


def m55_answer(intent, p):
    t = datetime.date.today()
    y = p.get("jahr") or t.year
    R = {"intent": intent, "params": p, "zahlen": [], "liste": [], "links": [], "antwort": ""}
    if intent == "hilfe" or not intent:
        R["antwort"] = "Ich beantworte Fragen zu deinen Zahlen - zum Beispiel:"
        R["beispiele"] = M55_BEISPIELE
        return R
    if intent == "umsatz":
        st = stats(y)
        if p.get("monat"):
            m = st["months"][p["monat"] - 1]
            R["zahlen"] = [_z(f"Umsatz {MONTHS_LONG[p['monat'] - 1]} {y}", m["umsatz"]), _z("Rechnungen", m["anzahl"], "n"),
                           _z("Zahlungseingang im Monat", m["zufluss"])]
            R["antwort"] = f"Im {MONTHS_LONG[p['monat'] - 1]} {y} hattest du {money(m['umsatz'])} Umsatz aus {m['anzahl']} Rechnung(en)."
        else:
            e = euer(y)
            R["zahlen"] = [_z(f"Umsatz {y} (Rechnungsdatum)", st["total"]), _z("Rechnungen", st["anzahl"], "n"),
                           _z(f"Zahlungseingang {y}", e["einnahmen"]), _z("davon noch offen", e["offen"])]
            R["antwort"] = f"Dein Umsatz {y} beträgt {money(st['total'])} aus {st['anzahl']} Rechnung(en); eingegangen sind {money(e['einnahmen'])}."
        R["links"] = [{"label": f"Statistik {y}", "view": "stat", "year": y}]
        return R
    if intent == "umsatz_kunde":
        if not p.get("kunde_id"):
            R["rueckfrage"] = True
            R["antwort"] = "Welchen Kunden meinst du? Nenne bitte Firmenname, Name oder Kundennummer." + \
                           (f" („{p['kunde_text']}“ habe ich nicht gefunden.)" if p.get("kunde_text") else "")
            R["beispiele"] = [f"Umsatz mit {(c['firma'] or c['name'])} {t.year}" for c in q("SELECT firma, name FROM customers LIMIT 3")]
            return R
        c = q("SELECT * FROM customers WHERE id=?", (p["kunde_id"],), one=True)
        nm = c["firma"] or c["name"] or c["kdnr"]
        args = [c["id"]]
        cond = f"customer_id=? AND {COUNT_SQL}"
        if p.get("jahr"):
            cond += " AND substr(datum,1,4)=?"
            args.append(str(y))
        r = q(f"SELECT COALESCE(SUM(summe),0) s, COUNT(*) n FROM invoices WHERE {cond}", args, one=True)
        o = {"s": round(sum(m53_offen(r_) for r_ in q(f"SELECT * FROM invoices WHERE {cond} AND status='offen' AND typ='rechnung'", args)), 2)}
        er = q(f"SELECT COALESCE(SUM(summe),0) s, COUNT(*) n FROM invoices WHERE {cond} AND status='offen' AND typ='storno'", args, one=True)
        nre = q(f"SELECT COUNT(*) n FROM invoices WHERE {cond} AND typ='rechnung'", args, one=True)["n"]
        zr = f" {y}" if p.get("jahr") else " (gesamt)"
        R["zahlen"] = [_z(f"Umsatz mit {nm}{zr}", r["s"]), _z("Rechnungen", nre, "n"), _z("davon offen", o["s"]),
                       _z("offene Erstattung", abs(er["s"]))]
        R["antwort"] = f"Mit {nm} hast du{zr.replace(' (gesamt)', ' insgesamt')} {money(r['s'])} Umsatz aus {nre} Rechnung(en) gemacht" + \
                       (f", davon sind {money(o['s'])} noch offen" if o["s"] > 0.005 else "") + \
                       (f"; eine Erstattung von {money(abs(er['s']))} (Storno) ist noch nicht ausgezahlt" if er["s"] < -0.005 else "") + "."
        for i in q(f"SELECT id, nr, datum, summe, status FROM invoices WHERE {cond} ORDER BY datum DESC LIMIT 6", args):
            R["liste"].append({"label": f"{i['nr']} · {de_date(i['datum'])} · {i['status']}", "wert": money(i["summe"]), "inv": i["id"]})
        R["links"] = [{"label": f"Kunde {nm} öffnen", "view": "users", "arg": c["id"]}]
        return R
    if intent == "ausgaben":
        e = euer(y)
        if p.get("kategorie"):
            v = e["kategorien"].get(p["kategorie"], 0.0)
            n = sum(1 for b in e["ausgaben_list"] if (b["kategorie"] or "") == p["kategorie"])
            R["zahlen"] = [_z(f"{p['kategorie']} {y}", v), _z("Belege", n, "n"), _z(f"Ausgaben gesamt {y}", e["ausgaben"]),
                           _z("Anteil", round(100 * v / e["ausgaben"], 1) if e["ausgaben"] else 0, "pct")]
            R["antwort"] = f"Für {p['kategorie']} hast du {y} {money(v)} ausgegeben ({n} Beleg(e))."
            top = {}
            for b in e["ausgaben_list"]:
                if (b["kategorie"] or "") == p["kategorie"]:
                    top[b["partner"] or "?"] = top.get(b["partner"] or "?", 0) + b["betrag"]
            R["liste"] = [{"label": k, "wert": money(v_)} for k, v_ in sorted(top.items(), key=lambda kv: -kv[1])[:6]]
        elif p.get("partner"):
            r = q("SELECT COALESCE(SUM(betrag),0) s, COUNT(*) n FROM belege WHERE typ='ausgabe' AND lower(partner) LIKE ? AND substr(datum,1,4)=?",
                  ("%" + p["partner"].lower() + "%", str(y)), one=True)
            R["zahlen"] = [_z(f"Ausgaben bei „{p['partner']}“ {y}", r["s"]), _z("Belege", r["n"], "n")]
            R["antwort"] = f"Bei „{p['partner']}“ hast du {y} {money(r['s'])} ausgegeben ({r['n']} Beleg(e))."
        else:
            R["zahlen"] = [_z(f"Ausgaben {y}", e["ausgaben"]), _z("Kategorien", len(e["kategorien"]), "n")]
            R["antwort"] = f"Deine Betriebsausgaben {y} liegen bei {money(e['ausgaben'])}."
            R["liste"] = [{"label": k, "wert": money(v_)} for k, v_ in sorted(e["kategorien"].items(), key=lambda kv: -kv[1])[:6]]
        R["links"] = [{"label": f"Jahresabrechnung {y}", "view": "tax", "year": y}, {"label": "Belege", "view": "beleg"}]
        return R
    if intent == "offene":
        rows = q("SELECT * FROM invoices WHERE typ='rechnung' AND status='offen' ORDER BY datum")
        rest = {r["id"]: round(m53_offen(r), 2) for r in rows}     # partial payments (m71) deducted
        ov = overdue_list()
        s_all = round(sum(rest.values()), 2)
        s_ov = round(sum(rest.get(r["id"], r["summe"]) for r in ov), 2)
        R["zahlen"] = [_z("Offene Rechnungen", len(rows), "n"), _z("Offener Betrag", s_all),
                       _z("davon überfällig", s_ov), _z("überfällige Rechnungen", len(ov), "n")]
        R["antwort"] = (f"Es sind {len(rows)} Rechnung(en) über {money(s_all)} offen" +
                        (f", davon {len(ov)} überfällig ({money(s_ov)})." if ov else ", nichts davon ist überfällig.")) \
            if rows else "Alle Rechnungen sind bezahlt - es ist nichts offen."
        erst = q("SELECT * FROM invoices WHERE typ='storno' AND status='offen' ORDER BY datum")
        if erst:
            se = abs(sum(r["summe"] for r in erst))
            R["zahlen"].append(_z("offene Erstattungen", se))
            R["antwort"] += f" Außerdem sind {len(erst)} Erstattung(en) aus Stornos über {money(se)} noch nicht ausgezahlt."
        R["liste"] = [{"label": f"{r['nr']} · {inv_name(r)} · {de_date(r['datum'])}", "wert": money(rest[r["id"]]), "inv": r["id"]} for r in rows[:8]]
        R["links"] = [{"label": "Rechnungen", "view": "inv"}]
        return R
    if intent == "top_kunden":
        st = stats(y)
        n = int(p.get("n") or 5)
        top = st["kunden"][:n]
        R["zahlen"] = [_z(f"Umsatz {y}", st["total"]), _z("Kunden mit Umsatz", len(st["kunden"]), "n")]
        R["liste"] = [{"label": f"{i + 1}. {k['name']} ({k['anzahl']} Rg.)", "wert": f"{money(k['summe'])} · {num_de(k['anteil'], 1)} %",
                       "kunde": k["customer_id"]} for i, k in enumerate(top)]
        R["antwort"] = (f"Dein größter Kunde {y} ist {top[0]['name']} mit {money(top[0]['summe'])} ({num_de(top[0]['anteil'], 1)} % vom Umsatz)."
                        if top else f"Für {y} gibt es noch keine Rechnungen.")
        R["links"] = [{"label": f"Statistik {y}", "view": "stat", "year": y}]
        return R
    if intent == "vergleich":
        y1 = p.get("jahr") or t.year - 1
        y2 = p.get("jahr2") or (t.year if y1 != t.year else t.year - 1)
        y1, y2 = min(y1, y2), max(y1, y2)
        a, b = stats(y1), stats(y2)
        ea, eb = euer(y1), euer(y2)
        R["zahlen"] = [_z(f"Umsatz {y1}", a["total"]), _z(f"Umsatz {y2}", b["total"]),
                       _z(f"Gewinn {y1}", ea["gewinn"]), _z(f"Gewinn {y2}", eb["gewinn"]),
                       _z(f"Ausgaben {y1}", ea["ausgaben"]), _z(f"Ausgaben {y2}", eb["ausgaben"])]
        d = round(b["total"] - a["total"], 2)
        pct = (round(100 * d / a["total"], 1) if a["total"] else None)
        if pct is not None:
            R["zahlen"].append(_z("Veränderung Umsatz", pct, "pct"))
        R["antwort"] = f"Umsatz {y2}: {money(b['total'])} gegenüber {money(a['total'])} in {y1}" + \
                       (f" ({'+' if d >= 0 else ''}{num_de(pct, 1)} %)." if pct is not None else ".") + \
                       (f" Hinweis: {y2} läuft noch." if y2 == t.year else "")
        R["links"] = [{"label": "Statistik", "view": "stat", "year": y2}]
        return R
    if intent == "gewinn":
        e = euer(y)
        R["zahlen"] = [_z(f"Gewinn {y} (EÜR)", e["gewinn"]), _z("Betriebseinnahmen", e["einnahmen"]), _z("Betriebsausgaben", e["ausgaben"]),
                       _z("offene Rechnungen (nicht enthalten)", e["offen"])]
        R["antwort"] = f"Dein Gewinn {y} nach EÜR liegt bei {money(e['gewinn'])} (Einnahmen {money(e['einnahmen'])}, Ausgaben {money(e['ausgaben'])})."
        R["links"] = [{"label": f"Jahresabrechnung {y}", "view": "tax", "year": y}]
        return R
    if intent == "steuer":
        tc = tax_calc(y)
        rl = m54_ruecklage(y)
        hoch = y == t.year and rl["basis"] != "Jahreswert"
        R["zahlen"] = [_z(f"ESt gesamt {y}" + (" (hochgerechnet)" if hoch else ""), rl["steuer_gesamt_jahr"]),
                       _z("Lohnsteuer/Soli/KiSt aus Gehalt" + (" (hochgerechnet)" if hoch else ""), rl["lohnsteuer_jahr"]),
                       _z("Vorauszahlungen im Jahr", rl["vorauszahlung_jahr"]),
                       _z("erwartete " + ("Nachzahlung" if rl["nachzahlung_erwartet"] >= 0 else "Erstattung"), abs(rl["nachzahlung_erwartet"])),
                       _z("Steuer auf die Selbstständigkeit", rl["anteil_jahr"]), _z("Rücklage pro Monat", rl["monat"]),
                       _z("Stand bisher ohne Hochrechnung: " + ("Nachzahlung" if tc["differenz"] >= 0 else "Erstattung"), abs(tc["differenz"]))]
        nz = rl["nachzahlung_erwartet"]
        R["antwort"] = ((f"Hochgerechnet auf das ganze Jahr {y} " if hoch else f"Für {y} ") +
                        (f"erwarte ich eine Nachzahlung von etwa {money(nz)}" if nz >= 0 else f"erwarte ich eine Erstattung von etwa {money(-nz)}") +
                        f". Auf die Selbstständigkeit entfallen rund {money(rl['anteil_jahr'])} - lege dafür etwa {money(rl['monat'])} pro Monat zurück.")
        R["liste"] = [{"label": h_["text"], "wert": ""} for h_ in rl["hinweise"]]
        R["links"] = [{"label": f"Steuer {y}", "view": "tax", "year": y}]
        return R
    if intent == "fixkosten":
        fk = m53_fixkosten_table()
        src = "Fixkosten-Tabelle"
        if not fk:
            fk = m53_fixkosten_schaetzung(t)
            src = "geschätzt aus wiederkehrenden Belegen der letzten 12 Monate"
        mon = round(sum(f["betrag"] / (f["months"] or 1) if f["months"] else f["betrag"] * 52 / 12 for f in fk), 2)
        R["zahlen"] = [_z("Fixkosten pro Monat (umgerechnet)", mon), _z("Posten", len(fk), "n"), _z("pro Jahr", round(mon * 12, 2))]
        R["liste"] = [{"label": f"{f['name']} ({'monatlich' if f['months'] == 1 else 'wöchentlich' if f['months'] == 0 else 'alle ' + str(f['months']) + ' Monate'})",
                       "wert": money(f["betrag"])} for f in sorted(fk, key=lambda f: -f["betrag"])[:8]]
        R["antwort"] = (f"Deine laufenden Fixkosten liegen bei etwa {money(mon)} pro Monat ({src})." if fk else
                        "Ich habe keine wiederkehrenden Ausgaben gefunden (keine Fixkosten-Tabelle, zu wenige gleichartige Belege).")
        R["links"] = [{"label": "Liquidität", "view": "liq"}]
        return R
    if intent == "kontostand":
        k = kontostand_info()
        if not k:
            R["antwort"] = "Es ist noch kein Kontostand erfasst. Lies einen Kontoauszug im Bank-Abgleich ein oder trage den Stand im Dashboard ein."
            R["links"] = [{"label": "Bank-Abgleich", "view": "bank"}]
            return R
        R["zahlen"] = [_z(f"Kontostand {de_date(k['datum'])}", k["saldo"])]
        if k.get("nachher_n"):
            R["zahlen"].append(_z(f"geschätzt inkl. {k['nachher_n']} späterer Umsätze", k["geschaetzt"]))
        R["antwort"] = f"Dein letzter erfasster Kontostand ({de_date(k['datum'])}) beträgt {money(k['saldo'])}" + \
                       (f", geschätzt aktuell {money(k['geschaetzt'])}." if k.get("nachher_n") else ".")
        R["links"] = [{"label": "Bank-Abgleich", "view": "bank"}, {"label": "Liquidität", "view": "liq"}]
        return R
    if intent == "liquiditaet":
        f = liq_forecast()
        R["zahlen"] = [_z("Startwert", f["start"]), _z(f"tiefster Stand ({de_date(f['min']['datum'])})", f["min"]["saldo"]),
                       _z(f"Stand in {len(f['series']) - 1} Tagen", f["ende"]), _z("Mindestreserve", f["min_reserve"])]
        R["antwort"] = (f"In den nächsten {len(f['series']) - 1} Tagen sinkt der Kontostand voraussichtlich bis auf {money(f['min']['saldo'])} "
                        f"am {de_date(f['min']['datum'])} und liegt am Ende bei {money(f['ende'])}.")
        R["liste"] = [{"label": w, "wert": ""} for w in f["warnungen"]]
        R["links"] = [{"label": "Liquiditätsvorschau", "view": "liq"}]
        return R
    if intent == "ku":
        kp = ku_prognose(y)
        R["zahlen"] = [_z(f"Umsatz {y} bisher", kp["bisher"]), _z("Hochrechnung", kp["prognose"]), _z(f"Umsatz {y - 1}", kp["vorjahr"]),
                       _z("Abstand zur 100.000-Grenze", kp["rest_bis_grenze"])]
        ok_ = not any(w["stufe"] == "kritisch" for w in kp["warnungen"])
        R["antwort"] = ("Nach den erfassten Zahlen ist die Kleinunternehmerregelung weiterhin möglich." if ok_ else
                        "Achtung: Eine Kleinunternehmergrenze ist überschritten.") + " Im Zweifel bitte mit dem Steuerberater klären."
        R["liste"] = [{"label": w["text"], "wert": ""} for w in kp["warnungen"]]
        R["links"] = [{"label": "Übersicht", "view": "dash"}]
        return R
    R["antwort"] = "Dazu habe ich keine Auswertung."
    return R


def jey_ask(question, use_ki=None):
    question = (question or "").strip()
    if not question:
        raise ValueError("Bitte eine Frage eingeben.")
    s = get_settings()
    ki_on = bool(s.get("ki_enabled")) if use_ki is None else bool(use_ki) and bool(s.get("ki_enabled"))
    rr = m55_rules(question)
    quelle, model, ki_err = "Regeln", "", ""
    det = rr
    if ki_on and rr["score"] < 3:
        try:
            k = m55_ki_intent(question, s)
            if k:
                det, quelle, model = k, "lokale KI (Absicht)", k.get("model", "")
        except Exception as e:
            ki_err = f"Lokale KI nicht erreichbar ({e}) - regelbasiert beantwortet."
    if not det["intent"]:
        return {"ok": True, "intent": None, "rueckfrage": True, "quelle": quelle,
                "antwort": "Das habe ich nicht sicher verstanden. Ich rechne nur mit deinen echten Daten - frag zum Beispiel so:",
                "beispiele": M55_BEISPIELE[:8], "zahlen": [], "liste": [], "links": [], "hinweis": ki_err}
    res = m55_answer(det["intent"], det["params"])
    res.update(ok=True, quelle=quelle, hinweis=ki_err, frage=question)
    if ki_on and res["zahlen"] and not res.get("rueckfrage"):
        try:
            txt = m55_ki_phrase(question, res, s)
            if txt:
                res["antwort_sachlich"] = res["antwort"]
                res["antwort"] = txt
                res["quelle"] = quelle + " + KI-Formulierung (Zahlen geprüft)"
        except Exception:
            pass
    if model:
        res["model"] = model
    return res


def m55_route_ask(h, d):
    return h._send(200, jey_ask(d.get("frage") or d.get("q") or "", d.get("ki")))


def m55_route_info(h, qs):
    s = get_settings()
    return h._send(200, {"beispiele": M55_BEISPIELE, "ki": bool(s.get("ki_enabled")), "intents": M55_INTENTS})


HOOK_POST["/api/m55/frage"] = m55_route_ask
HOOK_GET["/api/m55/info"] = m55_route_info


def m55_selftest():
    err = []
    tests = [("Wie viel Umsatz hatte ich 2025?", "umsatz", {"jahr": 2025}),
             ("Welche Rechnungen sind noch offen?", "offene", {}),
             ("Wie hoch waren meine Softwarekosten letztes Jahr?", "ausgaben", {"kategorie": "Software / Lizenzen",
                                                                               "jahr": datetime.date.today().year - 1}),
             ("Wer sind meine größten Kunden?", "top_kunden", {}),
             ("Vergleich 2025 mit 2026", "vergleich", {"jahr": 2025, "jahr2": 2026})]
    try:
        for qtext, want, params in tests:
            r = m55_rules(qtext)
            if r["intent"] != want:
                err.append(f"m55: „{qtext}“ -> {r['intent']} statt {want}")
                continue
            for k, v in params.items():
                if r["params"].get(k) != v:
                    err.append(f"m55: „{qtext}“ Parameter {k}={r['params'].get(k)} statt {v}")
            a = m55_answer(r["intent"], r["params"])
            if not a.get("antwort"):
                err.append(f"m55: keine Antwort für „{qtext}“")
        if m55_rules("Wie wird das Wetter morgen")["intent"] is not None:
            err.append("m55: unsinnige Frage wurde einer Absicht zugeordnet")
        c = q("SELECT id, firma, name FROM customers WHERE COALESCE(firma,'')!='' LIMIT 1", one=True)
        if c:
            r = m55_rules(f"Wie viel Umsatz mit {c['firma']}?")
            if r["intent"] != "umsatz_kunde" or r["params"].get("kunde_id") != c["id"]:
                err.append(f"m55: Kunde {c['firma']} nicht erkannt ({r['intent']}, {r['params'].get('kunde_id')})")
    except Exception as e:
        err.append(f"m55 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m55_selftest)
