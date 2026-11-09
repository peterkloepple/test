# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m08_abos_unterricht
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ---------------- Recurring invoices + maintenance contracts ----------------


def copy_invoice_as_draft(src_id, datum, extra_title_date=None):
    src = get_invoice(src_id)
    if not src:
        return None
    d = {k: src[k] for k in ("customer_id", "project_id", "kdnr", "addr", "zahlart", "frist", "toptext", "foottext")}
    dd = d_iso(datum) or datetime.date.today()
    d.update(typ="rechnung", status="entwurf", datum=dd.isoformat(), liefer=dd.isoformat(), auftrag=dd.isoformat(),
             titel=month_title(src["titel"], dd), source="abo",
             items=[{k: it[k] for k in ("qty", "nr", "name", "descr", "price", "rabatt", "article_id")} for it in src["items"]])
    iid, _ = save_invoice(d, bump=False)
    return iid


_SCHED_LOCK = threading.Lock()


def run_schedules():
    # v2.0.6: one run at a time (start thread + HTTP calls created duplicate drafts)
    with _SCHED_LOCK:
        return _run_schedules()


def _m08_schema():
    # v2.1.0: day of month a recurring invoice / contract belongs to (31st stays 31st after February)
    x("CREATE TABLE IF NOT EXISTS m08_anker (tab TEXT, rid INTEGER, datum TEXT, tag INTEGER, PRIMARY KEY (tab, rid))")


HOOK_SCHEMA.append(_m08_schema)


def next_due(tab, rid, cur, months):
    """v2.1.0: next due date after cur. The day of month is kept across short months (31.01. -> 28.02. -> 31.03.,
    29.02. -> 28.02. -> 29.02. in the next leap year). The anchor only counts while the stored date is unchanged -
    a date set by hand starts a new anchor."""
    tag = cur.day
    try:
        a = q("SELECT datum, tag FROM m08_anker WHERE tab=? AND rid=?", (tab, rid), one=True)
        if a and a["datum"] == cur.isoformat() and a["tag"] and int(a["tag"]) > cur.day:
            tag = int(a["tag"])
    except Exception:
        pass
    first = add_months(datetime.date(cur.year, cur.month, 1), max(1, int(months or 1)))
    last = (add_months(first, 1) - datetime.timedelta(days=1)).day
    nx = datetime.date(first.year, first.month, min(tag, last))
    try:
        x("INSERT OR REPLACE INTO m08_anker (tab, rid, datum, tag) VALUES (?,?,?,?)", (tab, rid, nx.isoformat(), tag))
    except Exception:
        pass
    return nx


def _run_schedules():
    made = []
    t = datetime.date.today()
    for r in q("SELECT * FROM recurring WHERE aktiv=1"):
        nxt = d_iso(r["naechstes"])
        n = 0
        while nxt and nxt <= t and n < 12:
            iid = copy_invoice_as_draft(r["invoice_id"], nxt.isoformat())
            if iid:
                made.append(iid)
            nn = next_due("recurring", r["id"], nxt, r["intervall"])
            x("UPDATE recurring SET letzte=?, naechstes=? WHERE id=?", (nxt.isoformat(), nn.isoformat(), r["id"]))
            nxt = nn
            n += 1
    return made


def vertraege_due():
    t = datetime.date.today()
    out = []
    for v in q("SELECT * FROM vertraege WHERE aktiv=1"):
        nx = d_iso(v["naechste"])
        if nx and nx - datetime.timedelta(days=int(v["vorlauf"] or 14)) <= t:
            v["tage"] = (nx - t).days
            out.append(v)
    return out


def vertrag_done(vid, datum=None):
    v = q("SELECT * FROM vertraege WHERE id=?", (vid,), one=True)
    s = get_settings()
    nx = d_iso(v["naechste"]) or datetime.date.today()
    inv_id = None
    if v["auto_rechnung"]:
        c = q("SELECT * FROM customers WHERE id=?", (v["customer_id"],), one=True) if v["customer_id"] else None
        a = q("SELECT * FROM articles WHERE id=?", (v["article_id"],), one=True) if v["article_id"] else None
        d = {"typ": "rechnung", "status": "entwurf", "customer_id": v["customer_id"], "project_id": v["project_id"],
             "kdnr": c["kdnr"] if c else "", "addr": address_lines(c), "datum": today(), "liefer": datum or today(),
             "auftrag": today(), "titel": f"Rechnung {v['name']}", "toptext": s["default_top"], "foottext": s["default_foot"],
             "zahlart": s.get("zahlart", "Ueberweisung"), "frist": s["frist"], "source": "wartung",
             "items": [{"qty": 1, "nr": a["nr"] if a else "", "name": (a["name"] if a else v["name"]),
                        "descr": ((v["beschreibung"] or "") + f"\nTermin {de_date(datum or today())}").strip(),
                        "price": float(v["preis"] or (a["price"] if a else 0)), "rabatt": 0, "article_id": v["article_id"]}]}
        inv_id, _ = save_invoice(d, bump=False)
    x("UPDATE vertraege SET letzte=?, naechste=? WHERE id=?", (datum or today(), next_due("vertraege", vid, nx, int(v["intervall"] or 12)).isoformat(), vid))
    return {"ok": True, "invoice_id": inv_id}


def schedule_loop():
    while True:
        try:
            auto_backup()
        except Exception:
            traceback.print_exc()
        try:
            run_schedules()
        except Exception:
            traceback.print_exc()
        time.sleep(3600)

# ---------------- Students / lessons ----------------


def lesson_ctx():
    st = {r["id"]: r for r in q("SELECT * FROM students ORDER BY sort, name")}
    ku = {r["id"]: r for r in q("SELECT * FROM kurse ORDER BY sort, name")}
    return st, ku


def lesson_eff(l, st, ku):
    """effective billing data of a lesson (course overrides student)"""
    s_ = st.get(l["student_id"]) or {}
    k = ku.get(l.get("kurs_id")) if l.get("kurs_id") else None
    art = (k["article_id"] if k and k["article_id"] else None) or s_.get("article_id")
    modus = (k["modus"] if k and k["modus"] else None) or s_.get("modus") or "monat"
    dauer = float(l.get("dauer") or (k["dauer"] if k else 0) or s_.get("dauer") or 1)
    payer = (k["customer_id"] if k and k["customer_id"] else None) or s_.get("customer_id")
    return {"article_id": art, "modus": modus, "dauer": dauer, "payer": payer, "kurs": k}


def lesson_month(year, month, customer_id=None):
    ym = f"{int(year):04d}-{int(month):02d}"
    st, ku = lesson_ctx()
    les = q("SELECT * FROM lessons WHERE substr(datum,1,7)=?", (ym,))
    for l in les:
        e = lesson_eff(l, st, ku)
        l["payer"], l["article_id"], l["modus"], l["dauer_eff"] = e["payer"], e["article_id"], e["modus"], e["dauer"]
    if customer_id:
        cid = int(customer_id)
        les = [l for l in les if l["payer"] == cid]
    members = q("SELECT m.*, s.name FROM kurs_members m LEFT JOIN students s ON s.id=m.student_id")
    return {"students": list(st.values()), "lessons": les, "kurse": list(ku.values()), "members": members}


def lesson_payers(year, month):
    data = lesson_month(year, month)
    out = {}
    for l in data["lessons"]:
        if l["invoice_id"] or l["status"] not in (None, "", "stattgefunden") or not l["payer"]:
            continue
        out[l["payer"]] = out.get(l["payer"], 0) + 1
    return out


def lessons_to_invoice(customer_id, year, month, attach=True):
    s = get_settings()
    year, month = int(year), int(month)
    data = lesson_month(year, month, customer_id)
    st, ku = lesson_ctx()
    groups = {}
    used = []
    for l in data["lessons"]:
        if l["status"] not in (None, "", "stattgefunden") or l["invoice_id"]:
            continue
        if l["student_id"] not in st:
            continue
        key = (l["article_id"], l["modus"], l.get("kurs_id") or 0)
        groups.setdefault(key, {}).setdefault(l["student_id"], []).append(l)
        used.append(l["id"])
    if not used:
        raise ValueError("Für diesen Monat und Empfänger sind keine offenen Stunden erfasst.")
    items = []
    for (aid, modus, kid), per in sorted(groups.items(), key=lambda kv: (kv[0][2], kv[0][0] or 0)):
        a = q("SELECT * FROM articles WHERE id=?", (aid,), one=True) if aid else None
        k = ku.get(kid)
        names = sorted(st[sid]["name"] for sid in per)
        if modus == "stunde":
            qty = round(sum(float(l["dauer_eff"]) for ls in per.values() for l in ls), 2)
            lines = [f"{st[sid]['name']}: " + ", ".join(de_date(l['datum'])[:6] for l in sorted(ls, key=lambda l: l['datum']))
                     for sid, ls in sorted(per.items(), key=lambda kv: st[kv[0]]["name"])]
        else:
            qty = len(per)
            lines = names
        if k:
            lines = [f"Kurs {k['name']}"] + lines
        items.append({"qty": qty, "nr": a["nr"] if a else "", "name": a["name"] if a else (k["name"] if k else "Unterricht"),
                      "descr": "\n".join(lines), "price": a["price"] if a else 0, "rabatt": 0, "article_id": aid})
    c = q("SELECT * FROM customers WHERE id=?", (customer_id,), one=True)
    first = datetime.date(year, month, 1)
    last = add_months(first, 1) - datetime.timedelta(days=1)
    draft = {"typ": "rechnung", "customer_id": c["id"] if c else None, "kdnr": c["kdnr"] if c else "", "addr": address_lines(c),
             "datum": today(), "liefer": first.isoformat(), "auftrag": first.isoformat(), "titel": f"Rechnung {MONTHS_DE[month - 1]}",
             "toptext": s["default_top"], "foottext": s["default_foot"], "zahlart": s.get("zahlart", "Ueberweisung"),
             "frist": s["frist"], "items": items, "lesson_ids": used, "attachments": []}
    if attach:
        pdf = lesson_report_pdf(data, st, used, MONTHS_DE[month - 1] + f" {year}", c, ku)
        d_ = os.path.join(BELEG_DIR, "Anlagen", str(year))
        os.makedirs(d_, exist_ok=True)
        fp = os.path.join(d_, f"Stundennachweis_{year}-{month:02d}_{uuid.uuid4().hex[:4]}.pdf")
        write_file(fp, pdf)
        rel = os.path.relpath(fp, DATA_DIR)
        bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created) VALUES ('anlage',?,?,'',0,'',?,?,'{}',?)",
                (last.isoformat(), f"Stundennachweis {MONTHS_DE[month - 1]} {year}", "automatisch erzeugt", rel, now_iso()))
        draft["attachments"] = [{"id": bid, "file": rel, "partner": f"Stundennachweis {MONTHS_DE[month - 1]} {year}", "pending": True}]
    return draft


def lessons_bill_all(year, month):
    made = []
    for payer in lesson_payers(year, month):
        dr = lessons_to_invoice(payer, year, month, attach=True)
        att = dr.pop("attachments", [])
        dr["status"] = "entwurf"
        dr["source"] = "unterricht"
        iid, _ = save_invoice(dr, bump=False)
        for a_ in att:
            x("UPDATE belege SET invoice_id=? WHERE id=?", (iid, a_["id"]))
        for lid in dr["lesson_ids"]:
            x("UPDATE lessons SET invoice_id=? WHERE id=? AND invoice_id IS NULL", (iid, lid))
        made.append(iid)
    return made


def student_for_customer(cid, article_id=None, payer=None):
    ex = q("SELECT id FROM students WHERE person_customer_id=?", (cid,), one=True)
    if ex:
        return ex["id"]
    c = q("SELECT * FROM customers WHERE id=?", (cid,), one=True)
    if not c:
        raise ValueError("Kunde nicht gefunden.")
    return x("INSERT INTO students (name, customer_id, article_id, modus, dauer, aktiv, person_customer_id, notiz, sort) VALUES (?,?,?,?,?,1,?,?,0)",
             ((c["name"] or c["firma"] or c["kdnr"]).strip(), payer or cid, article_id, "monat", 1, cid, ""))


def kurs_toggle_day(kid, datum):
    mem = [m["student_id"] for m in q("SELECT student_id FROM kurs_members WHERE kurs_id=?", (kid,))]
    if not mem:
        raise ValueError("Der Kurs hat noch keine Teilnehmer.")
    have = {l["student_id"]: l for l in q("SELECT * FROM lessons WHERE kurs_id=? AND datum=?", (kid, datum))}
    if all(sid in have for sid in mem):
        n = 0
        for l in have.values():
            if not l["invoice_id"]:
                x("DELETE FROM lessons WHERE id=?", (l["id"],))
                n += 1
        return {"state": None, "n": n}
    for sid in mem:
        if sid not in have:
            x("INSERT INTO lessons (student_id, datum, dauer, status, notiz, kurs_id) VALUES (?,?,?,?,?,?)",
              (sid, datum, None, "stattgefunden", "", kid))
    return {"state": "stattgefunden", "n": len(mem)}


def lesson_report_pdf(data, st, used, label, cust, ku=None):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    ku = ku or {}
    s = get_settings()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Stundennachweis {label}", author=s.get("inhaber", ""))
    ss = font_stylesheet()
    el = [Paragraph(f"<b>Stundennachweis {label}</b>", ss["Title"]),
          Paragraph(f"{s.get('inhaber', '')} · {s.get('firma', '')}" + (f" · für {cust['firma'] or cust['name']}" if cust else ""), ss["Normal"]),
          Spacer(1, 8)]
    rows = [["Kurs / Unterricht", "Schüler/in", "Termine", "Anzahl", "Stunden"]]
    tot_n = tot_h = 0
    per = {}
    for l in data["lessons"]:
        if l["id"] in used:
            per.setdefault((l.get("kurs_id") or 0, l["student_id"]), []).append(l)
    for (kid, sid), ls in sorted(per.items(), key=lambda kv: ((ku.get(kv[0][0]) or {}).get("name", ""), st[kv[0][1]]["name"])):
        h = sum(float(l.get("dauer_eff") or l["dauer"] or 1) for l in ls)
        rows.append([(ku.get(kid) or {}).get("name", "Einzelunterricht")[:28], st[sid]["name"][:30],
                     ", ".join(de_date(l["datum"])[:6] for l in sorted(ls, key=lambda l: l["datum"])), str(len(ls)), num_de(h, 2)])
        tot_n += len(ls)
        tot_h += h
    rows.append(["Summe", "", "", str(tot_n), num_de(tot_h, 2)])
    t = Table(rows, colWidths=[38 * mm, 40 * mm, 62 * mm, 14 * mm, 18 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), FONT_B(), 9), ("FONT", (0, 1), (-1, -1), FONT_R(), 9),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
                           ("FONT", (0, -1), (-1, -1), FONT_B(), 9), ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f4fa")])]))
    el.append(t)
    doc.build(el)
    return buf.getvalue()


def _m08_selftest():
    errs = []
    try:
        got, d = [], datetime.date(2026, 1, 31)
        for _ in range(3):
            d = next_due("_selbsttest", -1, d, 1)
            got.append(d.isoformat())
        if got != ["2026-02-28", "2026-03-31", "2026-04-30"]:
            errs.append(f"Abo-Rechnung: Monatsende driftet ({got})")
        got, d = [], datetime.date(2024, 2, 29)
        for _ in range(4):
            d = next_due("_selbsttest", -2, d, 12)
            got.append(d.isoformat())
        if got[-1] != "2028-02-29":
            errs.append(f"Abo-Rechnung: 29. Februar geht verloren ({got})")
    except Exception as e:
        errs.append(f"Abo-Rechnung: {e}")
    finally:
        try:
            x("DELETE FROM m08_anker WHERE tab='_selbsttest'")
        except Exception:
            pass
    return errs


HOOK_SELFTEST.append(_m08_selftest)


# ---------------------------------------------------------------------------
# v2.1.1: "Rechnung aus Stunden" creates the time sheet attachment right away. If the draft is
# discarded, the attachment stayed forever. Orphans (never linked to a document, older than
# 14 days - drafts may be parked that long) are moved to the recycle bin once at program start.
# ---------------------------------------------------------------------------
def m08_orphan_sheets(days=14):
    lim = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    n = 0
    for b in q("SELECT id, file, created FROM belege WHERE typ='anlage' AND invoice_id IS NULL AND notiz='automatisch erzeugt' "
               "AND partner LIKE 'Stundennachweis %' AND COALESCE(created,'') < ?", (lim,)):
        try:
            if b["file"] and "trash_file" in globals():
                trash_file(b["file"])
            x("DELETE FROM belege WHERE id=? AND invoice_id IS NULL", (b["id"],))
            n += 1
        except Exception:
            traceback.print_exc()
    return n


def _m08_orphan_start():
    time.sleep(90)
    try:
        m08_orphan_sheets()
    except Exception:
        traceback.print_exc()


HOOK_START.append(_m08_orphan_start)


def _m08_orphan_selftest():
    err = []
    try:
        old = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        b1 = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created) VALUES "
               "('anlage','2026-01-31','Stundennachweis Januar 2026','',0,'','automatisch erzeugt','','{}',?)", (old,))
        b2 = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, created) VALUES "
               "('anlage','2026-01-31','Stundennachweis Januar 2026','',0,'','automatisch erzeugt','','{}',?)", (now_iso(),))
        m08_orphan_sheets()
        if q("SELECT id FROM belege WHERE id=?", (b1,), one=True):
            err.append("m08: verwaister Stundennachweis nicht entfernt")
        if not q("SELECT id FROM belege WHERE id=?", (b2,), one=True):
            err.append("m08: frischer Stundennachweis faelschlich entfernt")
        x("DELETE FROM belege WHERE id IN (?,?)", (b1, b2))
    except Exception as e:
        err.append(f"m08 Stundennachweis-Aufraeumen: {e}")
    return err


HOOK_SELFTEST.append(_m08_orphan_selftest)
