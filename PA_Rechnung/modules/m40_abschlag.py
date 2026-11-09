# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m40_abschlag
# Abschlagsrechnungen und Schlussrechnung je Projekt (Zahlungsplan).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer
#
# Tabelle m40_plan: ein Zahlungsplan je Projekt. raten = JSON-Liste
#   [{"bez": "1. Abschlag bei Auftrag", "modus": "pct"|"betrag", "wert": 30, "invoice_id": 12}, ...]
# Rechnungen werden als normale Entwuerfe (typ rechnung, status entwurf) ueber save_invoice angelegt,
# negative Abzugspositionen funktionieren mit line_total / render_invoice_pdf (qty 1, price < 0).

M40_VORLAGE = [("1. Abschlag bei Auftrag", 30.0), ("2. Abschlag bei Lieferung / Montagebeginn", 40.0),
               ("3. Abschlag / Rest bei Fertigstellung", 30.0)]


def _m40_schema():
    x("CREATE TABLE IF NOT EXISTS m40_plan (id INTEGER PRIMARY KEY, project_id INTEGER UNIQUE, auftragssumme REAL, "
      "angebot_id INTEGER, auftrag_text TEXT, raten TEXT, quelle TEXT, schluss_id INTEGER, notiz TEXT, created TEXT, updated TEXT)")


HOOK_SCHEMA.append(_m40_schema)


def _m40_r2(v):
    return round(float(v or 0) + 1e-9, 2)


def m40_rate_betrag(rate, summe):
    """amount of one installment: percent of order sum or fixed amount"""
    w = float(rate.get("wert") or 0)
    if (rate.get("modus") or "pct") == "pct":
        return _m40_r2(summe * w / 100.0)
    return _m40_r2(w)


def m40_schluss_rest(gesamt, abschlaege):
    """gesamt = total of all services; abschlaege = list of {"betrag", "bezahlt"(bool)}.
    returns dict with paid / unpaid deductions and remaining amount"""
    bez = _m40_r2(sum(float(a["betrag"]) for a in abschlaege if a.get("bezahlt")))
    off = _m40_r2(sum(float(a["betrag"]) for a in abschlaege if not a.get("bezahlt")))
    return {"gesamt": _m40_r2(gesamt), "abzug_bezahlt": bez, "abzug_offen": off,
            "abzug": _m40_r2(bez + off), "rest": _m40_r2(gesamt - bez - off)}


def _m40_load(pid):
    r = q("SELECT * FROM m40_plan WHERE project_id=?", (pid,), one=True)
    if not r:
        return None
    try:
        r["raten"] = json.loads(r["raten"] or "[]")
    except Exception:
        r["raten"] = []
    return r


M40_SRC_ABSCHLAG = "m40_abschlag"
M40_SRC_SCHLUSS = "m40_schluss"


def _m40_inv_state(iid, pid=None, src=None):
    """linked invoice of a plan row. With pid/src the link is only valid if the invoice still belongs to this
    project and was created by m40 - SQLite reuses the id of a deleted invoice (no AUTOINCREMENT), so a deleted
    draft could otherwise point to an unrelated new invoice (which was then deducted in the final invoice)."""
    if not iid:
        return None
    r = q("SELECT id, nr, datum, summe, COALESCE(netto, summe) netto, COALESCE(ust_modus, '') ust_modus, status, typ, storno_von, "
          "locked, bezahlt_am, project_id, COALESCE(source, '') source FROM invoices WHERE id=?", (iid,), one=True)
    if r and pid is not None and (r["project_id"] != pid or r["typ"] != "rechnung" or (src and r["source"] != src)):
        return None
    return r


def _m40_regel(datum=None):
    """v2.1.0: Regelbesteuerung (m80) active for a new document of this date"""
    f = globals().get("m80_regel_on")
    try:
        return bool(f and f(datum or today()))
    except Exception:
        return False


def _m40_abzug_lines(inv, regel):
    """deduction basis of one issued installment invoice: [(net amount, ust_satz or None)].
    v2.1.0: with Regelbesteuerung the installment is deducted with its NET amount per VAT rate - the final
    invoice adds the VAT again (before, the gross amount was deducted as net and VAT was added on top)."""
    if not regel:
        return [(float(inv["summe"] or 0), None)]
    if inv.get("ust_modus") != "regel":
        return [(float(inv["summe"] or 0), 0.0)]     # installment without VAT (Kleinunternehmer): deduct as issued
    by = {}
    for it in q("SELECT total, ust_satz FROM items WHERE invoice_id=? ORDER BY pos", (inv["id"],)):
        sz = float(it["ust_satz"]) if it["ust_satz"] is not None else float((m80_cfg().get("satz") or 19))
        by[sz] = round(by.get(sz, 0.0) + float(it["total"] or 0), 2)
    return [(v, k) for k, v in sorted(by.items(), key=lambda kv: -kv[0]) if abs(v) >= 0.005] or [(float(inv["netto"] or 0), None)]


def _m40_valid(inv):
    """invoice counts as issued (not draft, not cancelled)"""
    return bool(inv) and inv["status"] not in ("entwurf", "storniert") and not inv.get("storno_von")


def m40_overview(pid):
    p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("Projekt nicht gefunden.")
    plan = _m40_load(pid)
    angebote = q("SELECT id, nr, datum, summe, COALESCE(netto, summe) netto, status, titel FROM invoices WHERE project_id=? "
                 "AND typ IN ('angebot','auftrag') ORDER BY datum DESC, id DESC", (pid,))
    out = {"project": {"id": p["id"], "nr": p["nr"], "name": p["name"], "budget": p["budget"] or 0},
           "angebote": angebote, "plan": None, "kpi": None, "regel": _m40_regel(),
           "vorlage": [{"bez": b, "modus": "pct", "wert": w} for b, w in M40_VORLAGE]}
    if not plan:
        return out
    summe = float(plan["auftragssumme"] or 0)
    raten = []
    gestellt = bezahlt = 0.0
    for i, r in enumerate(plan["raten"]):
        inv = _m40_inv_state(r.get("invoice_id"), pid, M40_SRC_ABSCHLAG)
        st = "frei"
        if inv:
            if inv["status"] == "entwurf":
                st = "entwurf"
            elif not _m40_valid(inv):
                st = "storniert"
            else:
                st = "bezahlt" if inv["status"] == "bezahlt" else "offen"
                gestellt += float(inv["netto"] or 0)
                if inv["status"] == "bezahlt":
                    bezahlt += float(inv["netto"] or 0)
        raten.append(dict(r, idx=i, betrag=m40_rate_betrag(r, summe), inv=inv, state=st))
    sinv = _m40_inv_state(plan.get("schluss_id"), pid, M40_SRC_SCHLUSS)
    sst = None
    if sinv:
        if sinv["status"] == "entwurf":
            sst = "entwurf"
        elif not _m40_valid(sinv):
            sst = "storniert"
        else:
            sst = "bezahlt" if sinv["status"] == "bezahlt" else "offen"
            gestellt += float(sinv["netto"] or 0)
            if sinv["status"] == "bezahlt":
                bezahlt += float(sinv["netto"] or 0)
    plan_sum = _m40_r2(sum(r["betrag"] for r in raten))
    out["plan"] = dict(plan, raten=raten, schluss=sinv, schluss_state=sst, plan_summe=plan_sum)
    out["kpi"] = {"auftrag": _m40_r2(summe), "gestellt": _m40_r2(gestellt), "bezahlt": _m40_r2(bezahlt),
                  "offen": _m40_r2(gestellt - bezahlt), "noch_zu_stellen": _m40_r2(max(0.0, summe - gestellt)),
                  "plan_abweichung": _m40_r2(plan_sum - summe)}
    return out


def m40_save_plan(d):
    pid = int(d["project_id"])
    if not q("SELECT id FROM projects WHERE id=?", (pid,), one=True):
        raise ValueError("Projekt nicht gefunden.")
    old = _m40_load(pid)
    old_r = old["raten"] if old else []
    raten = []
    for i, r in enumerate(d.get("raten") or []):
        modus = "betrag" if r.get("modus") == "betrag" else "pct"
        try:
            wert = float(r.get("wert") or 0)
        except Exception:
            raise ValueError(f"Abschlag {i + 1}: Wert ist keine Zahl.")
        if wert < 0:
            raise ValueError(f"Abschlag {i + 1}: negativer Wert ist nicht erlaubt.")
        iid = r.get("invoice_id")
        # keep invoice links from the stored plan (UI may not send them back)
        if not iid and r.get("idx") is not None and int(r["idx"]) < len(old_r):
            iid = old_r[int(r["idx"])].get("invoice_id")
        if iid and not _m40_inv_state(int(iid), pid, M40_SRC_ABSCHLAG):
            iid = None      # link to a deleted (or reused) invoice id is gone
        raten.append({"bez": (r.get("bez") or f"{i + 1}. Abschlag").strip(), "modus": modus, "wert": wert,
                      "invoice_id": int(iid) if iid else None})
    # removed rows that still carry an issued invoice must not vanish silently
    kept = {r["invoice_id"] for r in raten if r["invoice_id"]}
    for r in old_r:
        inv = _m40_inv_state(r.get("invoice_id"), pid, M40_SRC_ABSCHLAG)
        if inv and inv["id"] not in kept and _m40_valid(inv):
            raise ValueError(f"Der Abschlag „{r.get('bez')}“ ist bereits als Rechnung {inv['nr']} gestellt und kann nicht entfernt werden.")
    summe = float(d.get("auftragssumme") or 0)
    if summe < 0:
        raise ValueError("Die Auftragssumme darf nicht negativ sein.")
    vals = (summe, d.get("angebot_id") or None, (d.get("auftrag_text") or "").strip(),
            json.dumps(raten, ensure_ascii=False), d.get("quelle") or "angebot", d.get("notiz") or "", now_iso())
    if old:
        x("UPDATE m40_plan SET auftragssumme=?, angebot_id=?, auftrag_text=?, raten=?, quelle=?, notiz=?, updated=? WHERE project_id=?",
          vals + (pid,))
    else:
        x("INSERT INTO m40_plan (auftragssumme, angebot_id, auftrag_text, raten, quelle, notiz, updated, project_id, created) "
          "VALUES (?,?,?,?,?,?,?,?,?)", vals + (pid, now_iso()))
    return m40_overview(pid)


def _m40_head(pid):
    """customer/address part of a new document for project pid"""
    p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    c = q("SELECT * FROM customers WHERE id=?", (p["customer_id"],), one=True) if p and p["customer_id"] else None
    s = get_settings()
    return p, s, {"customer_id": c["id"] if c else None, "kdnr": c["kdnr"] if c else "", "addr": address_lines(c),
                  "project_id": pid, "datum": today(), "liefer": today(), "auftrag": p["start"] or "",
                  "zahlart": s.get("zahlart", "Ueberweisung"), "frist": s.get("frist") or 7, "status": "entwurf",
                  "foottext": s.get("default_foot", "")}


def _m40_auftrag_label(plan, p):
    if plan.get("auftrag_text"):
        return plan["auftrag_text"]
    if plan.get("angebot_id"):
        a = q("SELECT nr, datum, typ FROM invoices WHERE id=?", (plan["angebot_id"],), one=True)
        if a:
            art = "Auftragsbestätigung" if a["typ"] == "auftrag" else "Angebot"
            return f"{art} {a['nr']} vom {de_date(a['datum'])}"
    return f"Projekt {p['nr']} {p['name']}"


def m40_create_abschlag(pid, idx):
    # v2.6.3: serialized - a double click created two drafts (one of them not linked to the plan)
    with DOC_LOCK:
        return _m40_create_abschlag(pid, idx)


def _m40_create_abschlag(pid, idx):
    plan = _m40_load(pid)
    if not plan:
        raise ValueError("Bitte zuerst den Zahlungsplan speichern.")
    if idx < 0 or idx >= len(plan["raten"]):
        raise ValueError("Abschlag nicht gefunden.")
    r = plan["raten"][idx]
    inv = _m40_inv_state(r.get("invoice_id"), pid, M40_SRC_ABSCHLAG)
    if inv and (inv["status"] == "entwurf" or _m40_valid(inv)):
        raise ValueError(f"Für diesen Abschlag gibt es bereits {'einen Entwurf' if inv['status'] == 'entwurf' else 'die Rechnung ' + inv['nr']}.")
    summe = float(plan["auftragssumme"] or 0)
    if summe <= 0:
        raise ValueError("Bitte eine Auftragssumme eintragen.")
    betrag = m40_rate_betrag(r, summe)
    if betrag <= 0:
        raise ValueError("Der Abschlag ist 0 € - bitte Prozent oder Betrag eintragen.")
    p, s, d = _m40_head(pid)
    n = idx + 1
    lbl = _m40_auftrag_label(plan, p)
    pct = (num_de(float(r["wert"]), 2).rstrip("0").rstrip(",") + " %") if r["modus"] == "pct" else None
    d.update(typ="rechnung", titel=f"{n}. Abschlagsrechnung",
             toptext=f"Gemäß vereinbartem Zahlungsplan stellen wir Ihnen für {p['name']} den {n}. Abschlag in Rechnung.\n"
                     + (s.get("default_top") or ""),
             source=M40_SRC_ABSCHLAG,
             items=[{"qty": 1, "nr": "", "name": f"{r['bez']}",
                     "descr": (f"Abschlag {pct} auf {lbl}" if pct else f"Abschlag (Festbetrag) auf {lbl}")
                              + f"\nAuftragssumme {money(summe)}",
                     "price": betrag, "rabatt": 0}])
    iid, nr = save_invoice(d)
    plan["raten"][idx]["invoice_id"] = iid
    x("UPDATE m40_plan SET raten=?, updated=? WHERE project_id=?", (json.dumps(plan["raten"], ensure_ascii=False), now_iso(), pid))
    return {"ok": True, "id": iid, "nr": nr}


def _m40_base_items(pid, plan, quelle):
    """service items for the final invoice"""
    if quelle == "angebot" and plan.get("angebot_id"):
        it = q("SELECT qty, nr, name, descr, price, rabatt, article_id, ust_satz FROM items WHERE invoice_id=? ORDER BY pos", (plan["angebot_id"],))
        if it:
            # v2.1.0: keep the VAT rate of each offer line (7 % lines were billed with the default rate)
            return [{k: v for k, v in dict(i).items() if not (k == "ust_satz" and v is None)} for i in it]
    if quelle in ("angebot", "entries"):
        ents = q("SELECT * FROM project_entries WHERE project_id=? AND invoice_id IS NULL ORDER BY datum, id", (pid,))
        if ents:
            return [{"qty": e["qty"], "nr": e["nr"] or "", "name": e["name"],
                     "descr": ((de_date(e["datum"]) + " " + (e["descr"] or "")).strip()),
                     "price": e["price"], "rabatt": 0, "entry_id": e["id"]} for e in ents]
    if quelle in ("angebot", "entries", "pauschal"):
        p = q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
        return [{"qty": 1, "nr": "", "name": f"Gesamtleistung {p['name']}", "descr": _m40_auftrag_label(plan, p),
                 "price": float(plan["auftragssumme"] or 0), "rabatt": 0}]
    return []


def m40_build_schluss_items(base_items, abschlaege):
    """base items + one negative item per issued installment (per VAT rate with Regelbesteuerung).
    abschlaege: [{"n", "nr", "datum", "betrag", "bezahlt", "bezahlt_am", optional "lines": [(net, ust_satz)]}]"""
    out = [dict(i) for i in base_items]
    for a in abschlaege:
        dsc = (f"bezahlt am {de_date(a['bezahlt_am'])}" if a.get("bezahlt") and a.get("bezahlt_am")
               else ("bezahlt" if a.get("bezahlt") else "gestellt, Zahlung noch offen"))
        lines = a.get("lines") or [(a["betrag"], None)]
        for net, sz in lines:
            it = {"qty": 1, "nr": "", "name": f"abzgl. {a['n']}. Abschlagsrechnung Nr. {a['nr']} vom {de_date(a['datum'])}",
                  "descr": dsc, "price": -float(net), "rabatt": 0}
            if sz is not None:
                it["ust_satz"] = sz
            out.append(it)
    return out


def m40_create_schluss(pid, quelle=None):
    with DOC_LOCK:
        return _m40_create_schluss(pid, quelle)


def _m40_create_schluss(pid, quelle=None):
    plan = _m40_load(pid)
    if not plan:
        raise ValueError("Bitte zuerst den Zahlungsplan speichern.")
    sinv = _m40_inv_state(plan.get("schluss_id"), pid, M40_SRC_SCHLUSS)
    if sinv and (sinv["status"] == "entwurf" or _m40_valid(sinv)):
        raise ValueError(f"Es gibt bereits eine Schlussrechnung ({'Entwurf' if sinv['status'] == 'entwurf' else sinv['nr']}).")
    quelle = quelle or plan.get("quelle") or "angebot"
    regel = _m40_regel(today())
    abz, warn = [], []
    for i, r in enumerate(plan["raten"]):
        inv = _m40_inv_state(r.get("invoice_id"), pid, M40_SRC_ABSCHLAG)
        if not inv:
            continue
        if inv["status"] == "entwurf":
            warn.append(f"{i + 1}. Abschlag ist noch Entwurf und wird nicht abgezogen.")
            continue
        if not _m40_valid(inv):
            continue
        abz.append({"n": i + 1, "nr": inv["nr"], "datum": inv["datum"], "betrag": float(inv["summe"] or 0),
                    "bezahlt": inv["status"] == "bezahlt", "bezahlt_am": inv.get("bezahlt_am") or "",
                    "lines": _m40_abzug_lines(inv, regel)})
    base = _m40_base_items(pid, plan, quelle)
    if not base:
        raise ValueError("Keine Leistungen gefunden (Angebot, offene Projektleistungen oder Auftragssumme).")
    for it in base:
        it["total"] = line_total(it)
    items = m40_build_schluss_items(base, abz)
    p, s, d = _m40_head(pid)

    def _text(rest):
        calc = f"Gesamtleistung {money(rest['gesamt'])}"
        if rest["abzug_bezahlt"]:
            calc += f" - bereits bezahlte Abschläge {money(rest['abzug_bezahlt'])}"
        if rest["abzug_offen"]:
            calc += f" - gestellte, noch offene Abschläge {money(rest['abzug_offen'])}"
        calc += f" = verbleibender Rechnungsbetrag {money(rest['rest'])}" + (" (brutto)." if regel else ".")
        lines = [f"Schlussrechnung für {p['name']} ({_m40_auftrag_label(plan, p)}): {calc}"]
        if rest["abzug_offen"]:
            lines.append("Die noch offenen Abschlagsrechnungen bitte gesondert begleichen.")
        return "\n".join(lines) + "\n" + (s.get("default_top") or "")
    # provisional text (amounts are final only after saving - Regelbesteuerung adds VAT per rate)
    rest = m40_schluss_rest(sum(it["total"] for it in base), abz)
    d.update(typ="rechnung", titel="Schlussrechnung", source=M40_SRC_SCHLUSS, toptext=_text(rest), items=items)
    iid, nr = save_invoice(d)
    # v2.1.0: the text shows the amounts of the saved document (gross with Regelbesteuerung) - the remaining
    # amount always equals the invoice total, gesamt = remaining amount + deducted installments (as issued)
    saved = q("SELECT summe FROM invoices WHERE id=?", (iid,), one=True)
    if saved:
        r2 = _m40_r2(saved["summe"])
        rest = dict(rest, rest=r2, gesamt=_m40_r2(r2 + rest["abzug"]))
        x("UPDATE invoices SET toptext=? WHERE id=?", (_text(rest), iid))
    x("UPDATE m40_plan SET schluss_id=?, quelle=?, updated=? WHERE project_id=?", (iid, quelle, now_iso(), pid))
    return {"ok": True, "id": iid, "nr": nr, "rest": rest, "warn": warn}


def _m40_get(h, qs):
    return h._send(200, m40_overview(int(qs["project_id"])))


def _m40_post_save(h, d):
    return h._send(200, dict(m40_save_plan(d), ok=True))


def _m40_post_abschlag(h, d):
    return h._send(200, m40_create_abschlag(int(d["project_id"]), int(d["idx"])))


def _m40_post_schluss(h, d):
    return h._send(200, m40_create_schluss(int(d["project_id"]), d.get("quelle")))


def _m40_post_unlink(h, d):
    """remove link of a cancelled/deleted invoice from the plan so the installment can be issued again"""
    pid = int(d["project_id"])
    plan = _m40_load(pid)
    if not plan:
        raise ValueError("Kein Zahlungsplan.")
    idx = d.get("idx")
    if idx is None:
        inv = _m40_inv_state(plan.get("schluss_id"), pid, M40_SRC_SCHLUSS)
        if inv and _m40_valid(inv):
            raise ValueError("Gestellte Rechnungen nicht lösen - bitte zuerst stornieren.")
        x("UPDATE m40_plan SET schluss_id=NULL WHERE project_id=?", (pid,))
    else:
        if not 0 <= int(idx) < len(plan["raten"]):
            raise ValueError("Abschlag nicht gefunden.")
        r = plan["raten"][int(idx)]
        inv = _m40_inv_state(r.get("invoice_id"), pid, M40_SRC_ABSCHLAG)
        if inv and _m40_valid(inv):
            raise ValueError("Gestellte Rechnungen nicht lösen - bitte zuerst stornieren.")
        r["invoice_id"] = None
        x("UPDATE m40_plan SET raten=? WHERE project_id=?", (json.dumps(plan["raten"], ensure_ascii=False), pid))
    return h._send(200, dict(m40_overview(pid), ok=True))


HOOK_GET["/api/m40/plan"] = _m40_get
HOOK_POST["/api/m40/plan/save"] = _m40_post_save
HOOK_POST["/api/m40/abschlag"] = _m40_post_abschlag
HOOK_POST["/api/m40/schluss"] = _m40_post_schluss
HOOK_POST["/api/m40/unlink"] = _m40_post_unlink


def _m40_selftest():
    err = []
    r = m40_schluss_rest(10000.0, [{"betrag": 3000, "bezahlt": True}, {"betrag": 4000, "bezahlt": False}])
    if r["rest"] != 3000.0 or r["abzug_bezahlt"] != 3000.0 or r["abzug_offen"] != 4000.0:
        err.append(f"m40: Schlussrechnung Rest falsch: {r}")
    if m40_rate_betrag({"modus": "pct", "wert": 30}, 12345.67) != 3703.70:
        err.append("m40: Abschlag 30 % falsch berechnet")
    if m40_rate_betrag({"modus": "betrag", "wert": 1500}, 9999) != 1500.0:
        err.append("m40: Abschlag Festbetrag falsch")
    base = [{"qty": 2, "price": 2500, "rabatt": 0, "name": "A"}, {"qty": 10, "price": 500, "rabatt": 0, "name": "B"}]
    its = m40_build_schluss_items(base, [{"n": 1, "nr": "T-1", "datum": "2026-01-01", "betrag": 3000, "bezahlt": True},
                                         {"n": 2, "nr": "T-2", "datum": "2026-02-01", "betrag": 4000, "bezahlt": False}])
    tot = round(sum(line_total(i) for i in its), 2)
    if tot != 3000.0:
        err.append(f"m40: Summe Schlussrechnung mit Abzugspositionen = {tot}, erwartet 3000,00")
    # v2.1.0: Regelbesteuerung - one NET deduction line per VAT rate of the installment
    its = m40_build_schluss_items([], [{"n": 1, "nr": "T-1", "datum": "2026-01-01", "betrag": 1297.0, "bezahlt": False,
                                        "lines": [(1000.0, 19.0), (100.0, 7.0)]}])
    if [(i["price"], i.get("ust_satz")) for i in its] != [(-1000.0, 19.0), (-100.0, 7.0)]:
        err.append(f"m40: Abzug je Steuersatz falsch: {[(i['price'], i.get('ust_satz')) for i in its]}")
    return err


HOOK_SELFTEST.append(_m40_selftest)
