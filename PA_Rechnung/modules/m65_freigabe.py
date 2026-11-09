# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m65_freigabe (v2.0.14)
# Rechnungen frei korrigieren und loeschen - auch festgeschriebene - statt
# stornieren zu muessen. Einstellung "inv_frei" (Standard: an).
#  - "Bearbeiten" hebt die Festschreibung einer Rechnung auf (Editor wird wieder frei)
#  - Loeschen geht fuer jede Rechnung (einzeln und als Sammelaktion)
#  - Storno geloescht -> Originalrechnung wird wieder "offen"
#  - Original geloescht -> zugehoerige Storno-Rechnung wird mitgeloescht
#  - die PDF-Datei wandert in den Papierkorb im Datenordner
#  - war es die zuletzt vergebene Nummer, wird der Nummernkreis zurueckgesetzt
# Jede Aufhebung und Loeschung steht weiterhin im GoBD-Protokoll (m51).
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M65_VERSION = "1.0.0"


def inv_frei():
    return get_settings().get("inv_frei", True) not in (False, 0, "0", "false")


def _m65_log(iid, aktion, alt, neu):
    try:
        r = q("SELECT nr, typ FROM invoices WHERE id=?", (iid,), one=True)
        m51_log("Rechnung", iid, aktion, "", alt, neu, f"{(r or {}).get('typ') or ''} {(r or {}).get('nr') or ''}".strip())
    except Exception:
        pass


def inv_unlock(iid):
    if not inv_frei():
        raise ValueError("Festgeschriebene Rechnungen sind geschützt (Einstellungen › Dokumente › „Rechnungen frei korrigieren und löschen“).")
    r = q("SELECT id, locked FROM invoices WHERE id=?", (int(iid),), one=True)
    if not r:
        raise ValueError("Rechnung nicht gefunden.")
    if r["locked"]:
        _m65_log(r["id"], "Festschreibung aufgehoben", "festgeschrieben", "bearbeitbar")
        x("UPDATE invoices SET locked=0, updated=? WHERE id=?", (now_iso(), r["id"]))
    return {"ok": True}


def _trash_pdf(inv):
    try:
        s = get_settings()
        fp = invoice_pdf_path(inv, s)
        if fp and os.path.isfile(fp):
            dd = os.path.join(DATA_DIR, TRASH_DIR, time.strftime("%Y-%m-%d"), "Rechnungen")
            os.makedirs(dd, exist_ok=True)
            dst = os.path.join(dd, os.path.basename(fp))
            if os.path.exists(dst):
                dst = os.path.join(dd, uuid.uuid4().hex[:6] + "_" + os.path.basename(fp))
            shutil.move(fp, dst)
    except Exception:
        traceback.print_exc()


def _nr_back(inv):
    """deleted the last issued number -> number range goes back (no gap)"""
    try:
        nr = str(inv.get("nr") or "")
        if not nr or nr.startswith("E-"):
            return
        key = DOC_TYPES.get(inv.get("typ") or "rechnung", DOC_TYPES["rechnung"])["series"]
        s = get_settings()
        if s.get(key) and inc_number(nr) == s[key] and not q("SELECT id FROM invoices WHERE nr=?", (nr,), one=True):
            set_setting(key, nr)
    except Exception:
        traceback.print_exc()


def _m65_try(sql, args=()):
    # table / column may not exist (module not loaded, older data folder)
    try:
        x(sql, args)
    except Exception as e:
        if "no such" not in str(e).lower():
            traceback.print_exc()


def inv_delete_links(iid):
    """remove every link to a deleted invoice id - SQLite reuses the highest id (and _nr_back the number),
    so the next document would otherwise inherit bank bookings, offer status, billed services ..."""
    iid = int(iid)
    # bank bookings: back to "Zu pruefen" (fints_pending) when no Beleg hangs on them, otherwise just unlink
    try:
        for bt in q("SELECT * FROM bank_tx WHERE invoice_id=?", (iid,)):
            moved = False
            if bt.get("beleg_id") in (None, ""):
                try:
                    x("INSERT OR IGNORE INTO fints_pending (hash, datum, betrag, name, zweck, iban, created) VALUES (?,?,?,?,?,?,?)",
                      (bt["hash"], bt["datum"], bt["betrag"], bt["name"] or "", bt["zweck"] or "", bt["iban"] or "", now_iso()))
                    x("DELETE FROM bank_tx WHERE id=?", (bt["id"],))
                    moved = True
                except Exception:
                    traceback.print_exc()
            if not moved:
                x("UPDATE bank_tx SET invoice_id=NULL, status='ignore' WHERE id=?", (bt["id"],))
    except Exception:
        traceback.print_exc()
    for sql in ("DELETE FROM m71_zahlung WHERE invoice_id=?",
                "DELETE FROM m73_angebot WHERE invoice_id=?",
                "DELETE FROM m82_doc WHERE invoice_id=?",
                "DELETE FROM mahnungen WHERE invoice_id=?",
                "UPDATE m74_service SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE m75_pruefung SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE m41_aufmass SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE m41_kalk SET angebot_id=NULL WHERE angebot_id=?",
                "UPDATE m40_plan SET angebot_id=NULL WHERE angebot_id=?",
                "UPDATE m40_plan SET schluss_id=NULL WHERE schluss_id=?",
                "UPDATE m81_buchung SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE eingang_log SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE mail_log SET doc_id=NULL WHERE doc_id=?",
                "UPDATE recurring SET aktiv=0, invoice_id=NULL WHERE invoice_id=?",
                "UPDATE project_entries SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE lessons SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE belege SET invoice_id=NULL WHERE invoice_id=?",
                "UPDATE invoices SET ref_id=NULL WHERE ref_id=?"):
        _m65_try(sql, (iid,))
    # instalment plans (m40) keep the invoice id inside the JSON list "raten"
    try:
        for p in q("SELECT id, raten FROM m40_plan WHERE raten LIKE '%invoice_id%'"):
            try:
                raten = json.loads(p["raten"] or "[]")
            except Exception:
                continue
            if not isinstance(raten, list):
                continue
            hit = False
            for r in raten:
                if isinstance(r, dict) and str(r.get("invoice_id") or "") == str(iid):
                    r["invoice_id"] = None
                    hit = True
            if hit:
                x("UPDATE m40_plan SET raten=? WHERE id=?", (json.dumps(raten, ensure_ascii=False), p["id"]))
    except Exception as e:
        if "no such" not in str(e).lower():
            traceback.print_exc()


def inv_delete(iid, _seen=None):
    iid = int(iid)
    _seen = _seen or set()
    if iid in _seen:
        return 0
    _seen.add(iid)
    inv = q("SELECT * FROM invoices WHERE id=?", (iid,), one=True)
    if not inv:
        return 0
    if inv["locked"] and not inv_frei():
        raise ValueError("Festgeschriebene Rechnungen können nicht gelöscht werden – bitte stornieren "
                         "(oder in den Einstellungen „Rechnungen frei korrigieren und löschen“ einschalten).")
    n = 0
    # a cancellation that belongs to this invoice goes with it
    if inv.get("storno_von"):
        n += inv_delete(inv["storno_von"], _seen)
    # deleting a cancellation re-opens the original invoice
    for o in q("SELECT id, bezahlt_am FROM invoices WHERE storno_von=?", (iid,)):
        if o["id"] not in _seen:
            x("UPDATE invoices SET storno_von=NULL, status=?, updated=? WHERE id=?", ("bezahlt" if o["bezahlt_am"] else "offen", now_iso(), o["id"]))
    full = get_invoice(iid) or inv
    if inv["locked"]:
        _m65_log(iid, "Festschreibung aufgehoben", "festgeschrieben", "zum Löschen")
        x("UPDATE invoices SET locked=0 WHERE id=?", (iid,))
    x("DELETE FROM items WHERE invoice_id=?", (iid,))
    inv_delete_links(iid)
    x("DELETE FROM invoices WHERE id=?", (iid,))
    _trash_pdf(full)
    _nr_back(full)
    return n + 1


def _m65_delete_route(h, d):
    n = inv_delete(d["id"])
    return h._send(200, {"ok": True, "geloescht": n})


@chain_step("bulk_action", "m65_freigabe")
def _m65_step_bulk_action(_next, d):
    if d.get("kind") == "invoice" and d.get("action") == "delete" and inv_frei():
        ok_, err = 0, []
        for i in d.get("ids") or []:
            try:
                ok_ += inv_delete(i)
            except Exception as e:
                err.append(str(e))
        return {"ok": True, "done": ok_, "skipped": len(err), "errors": err[:5]}
    return _next(d)


def _m65_boot(d):
    d["inv_frei"] = inv_frei()


HOOK_POST["/api/invoice/delete"] = _m65_delete_route
HOOK_POST["/api/invoice/unlock"] = lambda h, d: h._send(200, inv_unlock(d["id"]))
HOOK_BOOT.append(_m65_boot)
