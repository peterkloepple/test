# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m11_bootstrap
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# HTTP API
# ----------------------------------------------------------------------------
PREVIEW = {}


def bootstrap():
    s = get_settings()
    mark_start_ok()
    return {
        "upd": {"source": CORE_SOURCE, "launcher": LAUNCHER_VER, "hinweis": _rj(os.path.join(APP_DIR, "hinweis.json"))},
        "version": APP_VERSION, "data_dir": DATA_DIR, "pending": q("SELECT COUNT(*) n FROM pending_belege", one=True)["n"], "konto": kontostand_info(), "pw_count": len(get_settings().get("beleg_pw") or []), "settings": {k: v for k, v in s.items() if k not in ("smtp_pass", "beleg_pw", "tt_pass", "tt_session")},
        "customers": q("SELECT * FROM customers ORDER BY COALESCE(NULLIF(firma,''), name)"),
        "articles": q("SELECT * FROM articles ORDER BY cat, sort, nr"),
        "texts": q("SELECT * FROM texts ORDER BY kind, sort, id"),
        "invoices": q("SELECT id, nr, customer_id, project_id, kdnr, addr, datum, titel, zahlart, frist, status, bezahlt_am, summe, source, "
                      "typ, ref_id, storno_von, locked, mahnstufe, versendet_am, gueltig_bis FROM invoices ORDER BY datum DESC, nr DESC"),
        "belege": q("SELECT id, typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id FROM belege ORDER BY datum DESC"),
        "projects": q("SELECT p.*, (SELECT COUNT(*) FROM project_files f WHERE f.project_id=p.id) nfiles, "
                      "(SELECT COALESCE(SUM(summe),0) FROM invoices i WHERE i.project_id=p.id AND i.typ IN ('rechnung','storno') AND i.status NOT IN ('storniert','entwurf')) umsatz, "
                      "(SELECT COUNT(*) FROM project_entries e WHERE e.project_id=p.id AND e.invoice_id IS NULL) offen_pos "
                      "FROM projects p ORDER BY p.status, p.start DESC"),
        "templates": q("SELECT * FROM templates ORDER BY id"),
        "kategorien": EUER_KATEGORIEN,
        "pdfium": bool(pdfium), "pypdf": bool(pypdf),
        "overdue": overdue_list(),
        "mahnungen": q("SELECT m.*, i.nr FROM mahnungen m LEFT JOIN invoices i ON i.id=m.invoice_id ORDER BY m.id DESC LIMIT 200"),
        "recurring": q("SELECT r.*, i.nr src_nr, i.addr src_addr, i.summe src_summe FROM recurring r LEFT JOIN invoices i ON i.id=r.invoice_id ORDER BY r.naechstes"),
        "vertraege": q("SELECT * FROM vertraege ORDER BY aktiv DESC, naechste"),
        "vertraege_due": vertraege_due(),
        "students": q("SELECT * FROM students ORDER BY aktiv DESC, sort, name"),
        "kurse": q("SELECT * FROM kurse ORDER BY aktiv DESC, sort, name"),
        "kurs_members": q("SELECT * FROM kurs_members"),
        "assets": q("SELECT * FROM assets ORDER BY kaufdatum DESC"),
        "zertifikate": q("SELECT * FROM zertifikate ORDER BY aktiv DESC, gueltig_bis"),
        "cert_warn": cert_warnings(),
        "cert_types": CERT_TYPES, "afa_presets": AFA_PRESETS,
        "ocr": ocr_available(), "frozen": bool(getattr(sys, "frozen", False)),
        "exe": sys.executable if getattr(sys, "frozen", False) else "",
        "smtp_set": bool(s.get("smtp_pass")),
    }


# ---------------- v1.1.0 routes ----------------
EXT_UPLOADS = ("/api/upload/bank", "/api/upload/bom", "/api/upload/zert", "/api/upload/update", "/api/upload/steuer", "/api/upload/paket")


def _crud(table, cols, d, num=()):
    vals = tuple((float(d.get(c) or 0) if c in num else d.get(c)) for c in cols)
    if d.get("id"):
        x(f"UPDATE {table} SET {', '.join(c + '=?' for c in cols)} WHERE id=?", vals + (d["id"],))
        return d["id"]
    return x(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
