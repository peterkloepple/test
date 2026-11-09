# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m77_abnahme (v2.0.19)
# Abnahmeprotokoll je Projekt mit Unterschrift auf Handy/Tablet oder am PC:
#  - Datum, Ort, Teilnehmer, abgenommene Leistungen (vorbelegt aus Angebot / Projekt-Eintraegen),
#    Maengelliste mit Frist (nachverfolgbar: erledigt am), Vorbehalte, Ergebnis (erteilt / unter Vorbehalt / verweigert)
#  - Unterschrift Kunde + Auftragnehmer: eigener kleiner Server im LAN (wie m32: Zufalls-Token, Ablauf 30 min,
#    QR-Code am PC), mobile Seite mit Unterschriftsfeld (Canvas, Touch). Alternativ am PC mit Maus/Stift.
#  - PDF mit Unterschriften, Zeitstempeln und SHA-256-Pruefsumme landet im Projekt (Ordner "Abnahme")
#  - Aenderung des Inhalts nach der Unterschrift verwirft die Unterschriften (Pruefsumme)
#  - Schlussrechnung (m40): Hinweis, wenn keine erteilte Abnahme vorliegt; optional sperren
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

import secrets

M77_VERSION = "1.0.0"
M77_TTL = 30 * 60
M77_DIR = "Abnahme"
M77_ERGEBNIS = {"erteilt": "Abnahme erteilt", "vorbehalt": "Abnahme unter Vorbehalt erteilt", "verweigert": "Abnahme verweigert", "": "offen"}
M77_DEF_SET = {"port": 8782, "pruefen": True, "sperren": False, "an_name": ""}
M77 = {"srv": None, "port": 0, "ip": "", "tokens": {}, "lock": threading.Lock()}


def _m77_schema():
    x("CREATE TABLE IF NOT EXISTS m77_prot (id INTEGER PRIMARY KEY, project_id INTEGER, nr TEXT, datum TEXT, ort TEXT, teilnehmer TEXT, "
      "leistungen TEXT, maengel TEXT, vorbehalte TEXT, ergebnis TEXT, notiz TEXT, sig_kunde TEXT, sig_kunde_name TEXT, sig_kunde_zeit TEXT, "
      "sig_an TEXT, sig_an_name TEXT, sig_an_zeit TEXT, sig_hash TEXT, pdf_file TEXT, hash TEXT, created TEXT, updated TEXT)")
    try:
        x("CREATE INDEX IF NOT EXISTS m77_p_proj ON m77_prot(project_id)")
    except Exception:
        pass


HOOK_SCHEMA.append(_m77_schema)


def m77_settings():
    s = get_settings()
    m = dict(M77_DEF_SET, **(s.get("m77") or {}))
    if not m["an_name"]:
        m["an_name"] = s.get("inhaber") or ""
    return m


def _m77_load(pid_or_row):
    r = pid_or_row if isinstance(pid_or_row, dict) else q("SELECT * FROM m77_prot WHERE id=?", (int(pid_or_row),), one=True)
    if not r:
        raise ValueError("Abnahmeprotokoll nicht gefunden.")
    r = dict(r)
    for k in ("leistungen", "maengel", "teilnehmer"):
        try:
            r[k] = json.loads(r[k] or "[]")
        except Exception:
            r[k] = []
    r["ergebnis_de"] = M77_ERGEBNIS.get(r.get("ergebnis") or "", r.get("ergebnis") or "")
    r["signiert_kunde"] = bool(r.get("sig_kunde"))
    r["signiert_an"] = bool(r.get("sig_an"))
    r["status"] = "unterschrieben" if r["signiert_kunde"] and r["signiert_an"] else ("teilweise" if r["signiert_kunde"] or r["signiert_an"] else "entwurf")
    t = today()
    r["maengel_offen"] = sum(1 for m in r["maengel"] if not m.get("erledigt_am"))
    r["maengel_ueber"] = sum(1 for m in r["maengel"] if not m.get("erledigt_am") and m.get("frist") and m["frist"] < t)
    return r


def _m77_content_hash(r):
    """hash over the protocol content - defect completion dates are tracking data and not part of it"""
    c = {"project_id": r["project_id"], "nr": r.get("nr"), "datum": r.get("datum"), "ort": r.get("ort"), "teilnehmer": r.get("teilnehmer"),
         "leistungen": r.get("leistungen"), "maengel": [{"text": m.get("text", ""), "frist": m.get("frist", "")} for m in r.get("maengel") or []],
         "vorbehalte": r.get("vorbehalte"), "ergebnis": r.get("ergebnis")}
    return hashlib.sha256(json.dumps(c, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _m77_full_hash(r):
    h = hashlib.sha256()
    h.update(_m77_content_hash(r).encode())
    for k in ("sig_kunde", "sig_kunde_name", "sig_kunde_zeit", "sig_an", "sig_an_name", "sig_an_zeit"):
        h.update(str(r.get(k) or "").encode("utf-8"))
    return h.hexdigest()


def m77_vorschlag(pid):
    """proposed accepted services: accepted offer items, else project entries (services)"""
    ang = q("SELECT id FROM invoices WHERE project_id=? AND typ IN ('angebot','auftrag') AND status IN ('angenommen','erledigt','offen') "
            "ORDER BY CASE status WHEN 'angenommen' THEN 0 WHEN 'erledigt' THEN 1 ELSE 2 END, typ DESC, datum DESC LIMIT 1", (pid,), one=True)
    out = []
    if ang:
        for it in q("SELECT name, qty, descr FROM items WHERE invoice_id=? ORDER BY pos", (ang["id"],)):
            if (it["name"] or "").strip():
                out.append({"text": it["name"].strip(), "ok": True})
    if not out:
        seen = set()
        for e in q("SELECT name, art FROM project_entries WHERE project_id=? ORDER BY datum, id", (pid,)):
            n = (e["name"] or "").strip()
            if n and n.lower() not in seen and (e["art"] or "") != "Material":
                seen.add(n.lower())
                out.append({"text": n, "ok": True})
    return out[:60]


def m77_list(pid):
    return [_m77_load(r) for r in q("SELECT * FROM m77_prot WHERE project_id=? ORDER BY datum DESC, id DESC", (int(pid),))]


def m77_project(pid):
    pid = int(pid)
    p = get_project(pid)
    if not p:
        raise ValueError("Projekt nicht gefunden.")
    rows = m77_list(pid)
    cust = p.get("customer") or {}
    return {"protokolle": [_m77_strip(r) for r in rows], "freigabe": m77_freigabe(pid), "settings": m77_settings(),
            "vorschlag": {"leistungen": m77_vorschlag(pid), "ort": " ".join(v for v in ((cust.get("strasse") or ""), (cust.get("plz") or ""), (cust.get("ort") or "")) if v).strip(),
                          "teilnehmer": [{"name": (cust.get("name") or cust.get("firma") or ""), "rolle": "Auftraggeber"},
                                         {"name": m77_settings()["an_name"], "rolle": "Auftragnehmer"}]}}


def _m77_strip(r):
    """no big signature images in list answers (only flags + small thumbnails are fine)"""
    r = dict(r)
    r["sig_kunde_img"] = r.pop("sig_kunde", "") or ""
    r["sig_an_img"] = r.pop("sig_an", "") or ""
    return r


def m77_freigabe(pid):
    rows = q("SELECT * FROM m77_prot WHERE project_id=? ORDER BY datum DESC, id DESC", (int(pid),))
    for r in rows:
        r = _m77_load(r)
        if r["ergebnis"] in ("erteilt", "vorbehalt") and r["status"] == "unterschrieben":
            return {"ok": True, "text": f"Abnahme vom {de_date(r['datum'])} ({r['ergebnis_de']})", "id": r["id"], "maengel_offen": r["maengel_offen"]}
    if rows:
        return {"ok": False, "text": "Abnahmeprotokoll vorhanden, aber noch nicht erteilt oder nicht von beiden unterschrieben."}
    return {"ok": False, "text": "Für dieses Projekt liegt noch keine Abnahme vor."}


def _m77_clean_list(lst, keys):
    out = []
    for e in lst or []:
        if not isinstance(e, dict):
            continue
        d = {k: (str(e.get(k) or "")[:500] if k not in ("ok",) else bool(e.get(k, True))) for k in keys}
        if any(str(d.get(k) or "").strip() for k in keys if k not in ("ok",)):
            out.append(d)
    return out[:200]


def m77_save(d):
    pid = int(d["project_id"])
    if not q("SELECT id FROM projects WHERE id=?", (pid,), one=True):
        raise ValueError("Projekt nicht gefunden.")
    erg = d.get("ergebnis") or ""
    if erg not in M77_ERGEBNIS:
        erg = ""
    vals = {"datum": (d.get("datum") or today())[:10], "ort": (d.get("ort") or "")[:300],
            "teilnehmer": _m77_clean_list(d.get("teilnehmer"), ("name", "rolle")),
            "leistungen": _m77_clean_list(d.get("leistungen"), ("text", "ok")),
            "maengel": _m77_clean_list(d.get("maengel"), ("text", "frist", "erledigt_am")),
            "vorbehalte": (d.get("vorbehalte") or "")[:3000], "ergebnis": erg, "notiz": (d.get("notiz") or "")[:2000]}
    info = ""
    if d.get("id"):
        old = _m77_load(int(d["id"]))
        new = dict(old, **vals)
        sig_keep = old.get("sig_hash") and _m77_content_hash(new) == old["sig_hash"]
        x("UPDATE m77_prot SET datum=?, ort=?, teilnehmer=?, leistungen=?, maengel=?, vorbehalte=?, ergebnis=?, notiz=?, updated=? WHERE id=?",
          (vals["datum"], vals["ort"], json.dumps(vals["teilnehmer"], ensure_ascii=False), json.dumps(vals["leistungen"], ensure_ascii=False),
           json.dumps(vals["maengel"], ensure_ascii=False), vals["vorbehalte"], erg, vals["notiz"], now_iso(), old["id"]))
        if (old["signiert_kunde"] or old["signiert_an"]) and not sig_keep:
            x("UPDATE m77_prot SET sig_kunde='', sig_kunde_name='', sig_kunde_zeit='', sig_an='', sig_an_name='', sig_an_zeit='', sig_hash='', hash='' WHERE id=?",
              (old["id"],))
            info = "Inhalt geändert - die Unterschriften wurden verworfen und müssen neu geleistet werden."
        rid = old["id"]
    else:
        pr = q("SELECT nr FROM projects WHERE id=?", (pid,), one=True)
        # highest number so far + 1 (COUNT+1 gave a number twice after a delete -> the PDF of a signed protocol was overwritten)
        n = 1
        for r_ in q("SELECT nr FROM m77_prot WHERE project_id=?", (pid,)):
            m_ = re.search(r"-(\d+)$", r_["nr"] or "")
            if m_:
                n = max(n, int(m_.group(1)) + 1)
        rid = x("INSERT INTO m77_prot (project_id, nr, datum, ort, teilnehmer, leistungen, maengel, vorbehalte, ergebnis, notiz, created, updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, f"AP-{pr['nr']}-{n}", vals["datum"], vals["ort"], json.dumps(vals["teilnehmer"], ensure_ascii=False),
                 json.dumps(vals["leistungen"], ensure_ascii=False), json.dumps(vals["maengel"], ensure_ascii=False), vals["vorbehalte"], erg,
                 vals["notiz"], now_iso(), now_iso()))
    return {"ok": True, "id": rid, "info": info}


def m77_delete(ids):
    for i in ids or []:
        x("DELETE FROM m77_prot WHERE id=?", (int(i),))
    return {"ok": True}


def m77_mangel(d):
    """mark a defect done / open again (does not touch the signatures)"""
    r = _m77_load(int(d["id"]))
    i = int(d["idx"])
    if i < 0 or i >= len(r["maengel"]):
        raise ValueError("Mangel nicht gefunden.")
    r["maengel"][i]["erledigt_am"] = (d.get("erledigt_am") or today())[:10] if d.get("erledigt", True) else ""
    x("UPDATE m77_prot SET maengel=?, updated=? WHERE id=?", (json.dumps(r["maengel"], ensure_ascii=False), now_iso(), r["id"]))
    return {"ok": True}


def _m77_png_ok(png):
    if not isinstance(png, str) or not png.startswith("data:image/png;base64,"):
        raise ValueError("Unterschrift fehlt.")
    raw = base64.b64decode(png.split(",", 1)[1])
    if len(raw) > 2 * 1048576 or not raw.startswith(b"\x89PNG"):
        raise ValueError("Unterschrift ungültig.")
    return png


def m77_sign(pid_, rolle, name, png):
    r = _m77_load(int(pid_))
    if rolle not in ("kunde", "an"):
        raise ValueError("Unbekannte Rolle.")
    png = _m77_png_ok(png)
    name = (name or "").strip()[:120]
    if not name:
        raise ValueError("Bitte den Namen in Druckschrift eintragen.")
    ch = _m77_content_hash(r)
    if r.get("sig_hash") and r["sig_hash"] != ch:
        x("UPDATE m77_prot SET sig_kunde='', sig_kunde_name='', sig_kunde_zeit='', sig_an='', sig_an_name='', sig_an_zeit='' WHERE id=?", (r["id"],))
    zeit = now_iso()
    x(f"UPDATE m77_prot SET sig_{rolle}=?, sig_{rolle}_name=?, sig_{rolle}_zeit=?, sig_hash=?, updated=? WHERE id=?",
      (png, name, zeit, ch, now_iso(), r["id"]))
    r = _m77_load(r["id"])
    res = {"ok": True, "status": r["status"]}
    if r["status"] == "unterschrieben":
        try:
            res["pdf"] = m77_pdf(r["id"], open_=False)
        except Exception as e:
            traceback.print_exc()
            res["warn"] = f"PDF konnte nicht erstellt werden: {e}"
    return res


def m77_unsign(d):
    r = _m77_load(int(d["id"]))
    rolle = d.get("rolle")
    if rolle not in ("kunde", "an"):
        raise ValueError("Unbekannte Rolle.")
    x(f"UPDATE m77_prot SET sig_{rolle}='', sig_{rolle}_name='', sig_{rolle}_zeit='', hash='', updated=? WHERE id=?", (now_iso(), r["id"]))
    return {"ok": True}


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def m77_pdf_bytes(rid):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    r = _m77_load(int(rid))
    p = get_project(r["project_id"])
    s = get_settings()
    ink, gray, acc, soft = colors.HexColor("#1e1a2b"), colors.HexColor("#6c6880"), colors.HexColor("#5b3fd6"), colors.HexColor("#f3f1fb")
    N = ParagraphStyle("n", fontName=FONT_R(), fontSize=9.5, leading=13, textColor=ink)
    NS = ParagraphStyle("ns", fontName=FONT_R(), fontSize=7.5, leading=9.5, textColor=gray)
    C = ParagraphStyle("c", fontName=FONT_R(), fontSize=8.5, leading=11, textColor=ink)
    K = ParagraphStyle("k", fontName=FONT_B(), fontSize=7.5, leading=9, textColor=acc)
    H1 = ParagraphStyle("h1", fontName=FONT_B(), fontSize=18, leading=22, textColor=ink, spaceAfter=2)
    H2 = ParagraphStyle("h2", fontName=FONT_B(), fontSize=11, leading=14, textColor=ink, spaceBefore=10, spaceAfter=4)
    e = lambda t: (str(t if t is not None else "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    tsb = [("FONT", (0, 0), (-1, 0), FONT_B(), 7.5), ("TEXTCOLOR", (0, 0), (-1, 0), gray), ("LINEBELOW", (0, 0), (-1, 0), 0.6, ink),
           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("FONT", (0, 1), (-1, -1), FONT_R(), 8.5)]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Abnahmeprotokoll {r['nr']}", author="T. Pfeiffer", creator=f"{APP_NAME} v{APP_VERSION}")
    cust = p.get("customer") or {}
    el = [Paragraph("ABNAHMEPROTOKOLL", K), Paragraph(e(p["name"]), H1),
          Paragraph(f"Protokoll {e(r['nr'])} · Projekt {e(p['nr'])}", NS), Spacer(1, 8)]
    kv = [["Auftraggeber", Paragraph(e(cust.get("firma") or cust.get("name") or "-") + (("<br/>" + e(" ".join(v for v in (cust.get("strasse"), cust.get("plz"), cust.get("ort")) if v))) if cust else ""), C)],
          ["Auftragnehmer", Paragraph(e(s.get("firma") or "") + "<br/>" + e(m77_settings()["an_name"]), C)],
          ["Datum der Abnahme", de_date(r["datum"])], ["Ort", Paragraph(e(r["ort"] or "-"), C)]]
    t = Table(kv, colWidths=[42 * mm, 132 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (0, -1), FONT_B(), 8.5), ("FONT", (1, 0), (1, -1), FONT_R(), 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e4e1ee")), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    el.append(t)
    if r["teilnehmer"]:
        el += [Paragraph("Teilnehmer", H2)]
        tt = Table([["Name", "Funktion / Firma"]] + [[Paragraph(e(a.get("name")), C), Paragraph(e(a.get("rolle")), C)] for a in r["teilnehmer"]],
                   colWidths=[80 * mm, 94 * mm], repeatRows=1)
        tt.setStyle(TableStyle(tsb))
        el.append(tt)
    el += [Paragraph("Abgenommene Leistungen", H2)]
    if r["leistungen"]:
        lt = Table([["Nr.", "Leistung", "abgenommen"]] + [[str(i + 1), Paragraph(e(a.get("text")), C), "ja" if a.get("ok", True) else "nein"]
                                                          for i, a in enumerate(r["leistungen"])], colWidths=[10 * mm, 140 * mm, 24 * mm], repeatRows=1)
        lt.setStyle(TableStyle(tsb + [("ALIGN", (2, 0), (2, -1), "CENTER")]))
        el.append(lt)
    else:
        el.append(Paragraph("Gesamte vertraglich vereinbarte Leistung.", N))
    el += [Paragraph("Mängel", H2)]
    if r["maengel"]:
        mt = Table([["Nr.", "Mangel", "Frist zur Beseitigung", "erledigt am"]] +
                   [[str(i + 1), Paragraph(e(m.get("text")), C), de_date(m.get("frist") or ""), de_date(m.get("erledigt_am") or "")]
                    for i, m in enumerate(r["maengel"])], colWidths=[10 * mm, 112 * mm, 30 * mm, 22 * mm], repeatRows=1)
        mt.setStyle(TableStyle(tsb))
        el.append(mt)
    else:
        el.append(Paragraph("Es wurden keine Mängel festgestellt.", N))
    if r["vorbehalte"]:
        el += [Paragraph("Vorbehalte / Bemerkungen", H2), Paragraph(e(r["vorbehalte"]).replace("\n", "<br/>"), N)]
    el += [Paragraph("Ergebnis", H2), Paragraph(f"<b>{e(r['ergebnis_de'])}</b>", N)]
    if r["ergebnis"] in ("erteilt", "vorbehalt"):
        el.append(Paragraph("Mit der Abnahme beginnt die Verjährungsfrist für Mängelansprüche. Die aufgeführten Mängel werden innerhalb der "
                            "genannten Fristen beseitigt; die Abnahme gilt insoweit unter Vorbehalt dieser Mängel.", NS))

    def sig_cell(img, name, zeit, rolle):
        parts = []
        if img:
            try:
                raw = base64.b64decode(img.split(",", 1)[1])
                ir = ImageReader(io.BytesIO(raw))
                iw, ih = ir.getSize()
                sc = min(70 * mm / max(iw, 1), 28 * mm / max(ih, 1))
                w, h = iw * sc, ih * sc
                parts.append(RLImage(io.BytesIO(raw), width=w, height=h))
            except Exception:
                parts.append(Paragraph("(Unterschrift nicht lesbar)", NS))
        else:
            parts.append(Spacer(1, 22 * mm))
        parts += [Paragraph("_" * 46, NS), Paragraph(f"<b>{e(rolle)}</b>: {e(name or '')}", C),
                  Paragraph(f"unterschrieben {e(zeit[:16].replace('T', ' ')) if zeit else '-'}", NS)]
        return parts
    sg = Table([[sig_cell(r.get("sig_kunde"), r.get("sig_kunde_name"), r.get("sig_kunde_zeit"), "Auftraggeber"),
                 sig_cell(r.get("sig_an"), r.get("sig_an_name"), r.get("sig_an_zeit"), "Auftragnehmer")]], colWidths=[87 * mm, 87 * mm])
    sg.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    el += [Spacer(1, 12), KeepTogether([Paragraph("Unterschriften", H2), sg])]
    fh = _m77_full_hash(r)
    el += [Spacer(1, 10), Paragraph(f"Prüfsumme (SHA-256) über Inhalt und Unterschriften: {fh}", NS),
           Paragraph(f"Erstellt am {de_date(today())} mit {APP_NAME} · T. Pfeiffer", NS)]

    def onpage(cv, dc):
        cv.setFont(FONT_R(), 7)
        cv.setFillColor(gray)
        cv.drawString(18 * mm, 9 * mm, f"Abnahmeprotokoll {r['nr']} · {p['nr']} · T. Pfeiffer")
        cv.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Seite {dc.page}")
    doc.build(el, onFirstPage=onpage, onLaterPages=onpage)
    return buf.getvalue(), fh


def m77_pdf(rid, open_=True):
    r = _m77_load(int(rid))
    data, fh = m77_pdf_bytes(rid)
    p = q("SELECT * FROM projects WHERE id=?", (r["project_id"],), one=True)
    base = ensure_project_folders(p)
    dd = os.path.join(base, M77_DIR)
    os.makedirs(dd, exist_ok=True)
    fp = os.path.join(dd, safe_name(f"Abnahmeprotokoll_{r['nr']}_{r['datum']}_{r['id']}.pdf"))
    write_file(fp, data)
    rel = os.path.relpath(fp, DATA_DIR)
    if q("SELECT id FROM project_files WHERE path=?", (rel,), one=True):
        x("UPDATE project_files SET size=?, added=? WHERE path=?", (len(data), now_iso(), rel))
    else:
        x("INSERT INTO project_files (project_id, folder, kind, name, path, size, note, added) VALUES (?,?,?,?,?,?,?,?)",
          (r["project_id"], M77_DIR, "Dokument", os.path.basename(fp), rel, len(data), "Abnahmeprotokoll", now_iso()))
    x("UPDATE m77_prot SET pdf_file=?, hash=? WHERE id=?", (rel, fh, r["id"]))
    if open_ and not os.environ.get("PA_RECHNUNG_NO_OPEN"):
        open_path(fp)
    return rel


# ---------------------------------------------------------------------------
# Signature server (LAN, token, like m32)
# ---------------------------------------------------------------------------
def _m77_active_tokens():
    t = time.time()
    return {k: v for k, v in M77["tokens"].items() if v["ablauf"] > t}


def m77_stop(only_idle=None):
    """stop the signature server; only_idle=<server>: stop only if it is still that server and has no active link
    (checked under the lock, so a QR code created at the same moment is not killed)"""
    with M77["lock"]:
        srv = M77["srv"]
        if only_idle is not None and (srv is not only_idle or _m77_active_tokens()):
            return {"ok": True}
        M77.update(srv=None, tokens={})
    if srv:
        def _down():
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
        threading.Thread(target=_down, daemon=True).start()
    return {"ok": True}


def _m77_watch(srv):
    while M77["srv"] is srv:
        if not _m77_active_tokens():
            m77_stop(only_idle=srv)
            if M77["srv"] is not srv:
                return
        time.sleep(5)


class M77Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows: with SO_REUSEADDR a busy port would be bound a second time without error -> exclusive bind there
    allow_reuse_address = not sys.platform.startswith("win")

    def server_bind(self):
        if sys.platform.startswith("win") and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        ThreadingHTTPServer.server_bind(self)


def m77_handy_start(d):
    rid, rolle = int(d["id"]), d.get("rolle") or "kunde"
    if rolle not in ("kunde", "an"):
        raise ValueError("Unbekannte Rolle.")
    _m77_load(rid)
    st = m77_settings()
    port = int(float(st.get("port") or 8782))
    ips = lan_ips()
    ip = d.get("ip") if d.get("ip") in ips else (ips[0] if ips else "")
    if not ip:
        raise ValueError("Keine Netzwerkverbindung gefunden – der PC muss im WLAN/LAN sein.")
    with M77["lock"]:
        if not M77["srv"]:
            srv, last = None, None
            for p_ in range(port, port + 6):
                try:
                    srv = M77Server(("0.0.0.0", p_), M77Handler)
                    break
                except OSError as e:
                    last, srv = e, None
            if not srv:
                raise ValueError(f"Port {port} ist belegt ({last}). Bitte unter Einstellungen > EN 1090 & Abnahme einen anderen Port eintragen.")
            M77.update(srv=srv, port=srv.server_address[1], ip=ip)
            tok = secrets.token_urlsafe(18)
            M77["tokens"][tok] = {"id": rid, "rolle": rolle, "ablauf": time.time() + M77_TTL, "fertig": False}
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            threading.Thread(target=_m77_watch, args=(srv,), daemon=True).start()
        else:
            for k in [k for k, v in M77["tokens"].items() if v["id"] == rid and v["rolle"] == rolle]:
                M77["tokens"].pop(k, None)
            tok = secrets.token_urlsafe(18)
            M77["tokens"][tok] = {"id": rid, "rolle": rolle, "ablauf": time.time() + M77_TTL, "fertig": False}
            M77["ip"] = ip
    url = f"http://{ip}:{M77['port']}/s/{tok}"
    return {"ok": True, "url": url, "svg": qr_svg(url), "ips": ips, "ip": ip, "rest_s": M77_TTL, "token": tok}


def m77_handy_status(tok):
    v = M77["tokens"].get(tok or "")
    if not v:
        return {"ok": True, "aktiv": False, "fertig": False}
    return {"ok": True, "aktiv": v["ablauf"] > time.time(), "fertig": v.get("fertig", False), "rest_s": max(0, int(v["ablauf"] - time.time()))}


M77_PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Abnahme unterschreiben</title>
<style>
*{box-sizing:border-box}body{margin:0;font:16px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f6f4fb;color:#1d1a26}
.w{max-width:760px;margin:0 auto;padding:16px}h1{font-size:21px;margin:4px 0 2px}.s{color:#6c6880;font-size:13px}
.c{background:#fff;border-radius:14px;padding:14px;margin:12px 0;box-shadow:0 1px 4px rgba(0,0,0,.06)}
ul{margin:4px 0 0 18px;padding:0}li{margin:2px 0}
input{width:100%;font:inherit;padding:12px;border:1px solid #d6d1e6;border-radius:10px;margin-top:6px}
canvas{width:100%;height:220px;border:2px dashed #b9b2d3;border-radius:12px;background:#fff;touch-action:none;display:block;margin-top:8px}
.b{display:flex;gap:10px;margin-top:12px}button{flex:1;font:600 17px inherit;padding:14px;border:0;border-radius:12px;background:#ece8f8;color:#1d1a26}
button.p{background:#5b3fd6;color:#fff}.ok{background:#e6f6ee;color:#145c3a;padding:18px;border-radius:12px;font-weight:600;text-align:center}
.err{color:#b3261e;font-size:14px;margin-top:8px}
</style></head><body><div class="w">
<div class="s">Abnahmeprotokoll __NR__ · __ROLLE__</div><h1>__PROJEKT__</h1><div class="s">Datum __DATUM__ · __ORT__</div>
<div class="c"><b>Abgenommene Leistungen</b>__LEIST__</div>
<div class="c"><b>Mängel</b>__MAENGEL__</div>
<div class="c"><b>Ergebnis:</b> __ERGEBNIS__ __VORB__</div>
<div class="c" id="sigc"><b>Unterschrift __ROLLE__</b>
<input id="nm" placeholder="Name in Druckschrift" value="__NAME__" autocomplete="off">
<canvas id="cv"></canvas><div class="s">Mit dem Finger oder Stift im Feld unterschreiben.</div>
<div class="b"><button id="clr" type="button">Löschen</button><button id="ok" class="p" type="button">Unterschreiben</button></div><div class="err" id="er"></div></div>
<div class="s" style="text-align:center">gültig bis __UNTIL__ Uhr</div></div>
<script>
const cv=document.getElementById("cv"),ctx=cv.getContext("2d");let drawn=false,down=false,last=null;
function fit(){const r=cv.getBoundingClientRect(),d=window.devicePixelRatio||1;const img=drawn?cv.toDataURL():null;cv.width=r.width*d;cv.height=r.height*d;ctx.setTransform(d,0,0,d,0,0);ctx.lineWidth=2.6;ctx.lineCap="round";ctx.lineJoin="round";ctx.strokeStyle="#111";if(img){const i=new Image();i.onload=()=>ctx.drawImage(i,0,0,r.width,r.height);i.src=img;}}
fit();addEventListener("resize",fit);
const pos=e=>{const r=cv.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];};
cv.addEventListener("pointerdown",e=>{down=true;last=pos(e);cv.setPointerCapture(e.pointerId);e.preventDefault();});
cv.addEventListener("pointermove",e=>{if(!down)return;const p=pos(e);ctx.beginPath();ctx.moveTo(last[0],last[1]);ctx.lineTo(p[0],p[1]);ctx.stroke();last=p;drawn=true;e.preventDefault();});
["pointerup","pointercancel","pointerleave"].forEach(t=>cv.addEventListener(t,()=>{down=false;}));
document.getElementById("clr").onclick=()=>{ctx.clearRect(0,0,cv.width,cv.height);drawn=false;};
document.getElementById("ok").onclick=async()=>{const er=document.getElementById("er");er.textContent="";
 const nm=document.getElementById("nm").value.trim();if(!nm){er.textContent="Bitte den Namen eintragen.";return;}if(!drawn){er.textContent="Bitte im Feld unterschreiben.";return;}
 const o=document.createElement("canvas");o.width=cv.width;o.height=cv.height;const c2=o.getContext("2d");c2.fillStyle="#fff";c2.fillRect(0,0,o.width,o.height);c2.drawImage(cv,0,0);
 try{const r=await fetch(location.pathname.replace(/\\/$/,"")+"/sig",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:nm,png:o.toDataURL("image/png"),hash:"__HASH__"})});
  const j=await r.json();if(!j.ok){er.textContent=j.error||"Fehler";return;}
  document.getElementById("sigc").innerHTML='<div class="ok">✓ Vielen Dank – die Unterschrift wurde übertragen.</div>';}catch(e){er.textContent="Keine Verbindung zum PC.";}};
</script></body></html>"""


def _m77_h(t):
    return (str(t if t is not None else "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _m77_page(v):
    r = _m77_load(v["id"])
    p = q("SELECT nr, name FROM projects WHERE id=?", (r["project_id"],), one=True) or {"nr": "", "name": ""}
    leist = "<ul>" + "".join(f"<li>{_m77_h(a.get('text'))}{'' if a.get('ok', True) else ' (nicht abgenommen)'}</li>" for a in r["leistungen"]) + "</ul>" \
        if r["leistungen"] else "<div class='s'>Gesamte vereinbarte Leistung</div>"
    maengel = "<ul>" + "".join(f"<li>{_m77_h(m.get('text'))}{(' – Frist ' + _m77_h(de_date(m['frist']))) if m.get('frist') else ''}</li>" for m in r["maengel"]) + "</ul>" \
        if r["maengel"] else "<div class='s'>keine</div>"
    nm = ""
    if v["rolle"] == "an":
        nm = m77_settings()["an_name"]
    else:
        tn = [a for a in r["teilnehmer"] if re.search(r"auftraggeber|kunde|bauherr", (a.get("rolle") or "").lower())]
        nm = tn[0]["name"] if tn else ""
    rep = {"__NR__": r["nr"], "__ROLLE__": "Auftraggeber" if v["rolle"] == "kunde" else "Auftragnehmer", "__PROJEKT__": p["name"],
           "__DATUM__": de_date(r["datum"]), "__ORT__": r["ort"] or "", "__ERGEBNIS__": r["ergebnis_de"], "__NAME__": nm,
           "__VORB__": ("<div class='s' style='margin-top:6px'>" + _m77_h(r["vorbehalte"]).replace("\n", "<br>") + "</div>") if r["vorbehalte"] else "",
           "__UNTIL__": datetime.datetime.fromtimestamp(v["ablauf"]).strftime("%H:%M"), "__HASH__": _m77_content_hash(r)}
    html = M77_PAGE.replace("__LEIST__", leist).replace("__MAENGEL__", maengel)
    for k, val in rep.items():
        html = html.replace(k, val if k in ("__VORB__",) else _m77_h(val))
    return html


class M77Handler(BaseHTTPRequestHandler):
    server_version = "PARechnungAbnahme/1.0"
    timeout = 60

    def log_message(self, fmt, *args):
        pass

    def _out(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _tok(self, tok):
        for k, v in list(M77["tokens"].items()):
            if secrets.compare_digest(k.encode(), tok.encode()) and v["ablauf"] > time.time() and not v.get("fertig"):
                return v
        return None

    def do_GET(self):
        m = re.fullmatch(r"/s/([A-Za-z0-9_\-]{10,64})/?", urlparse(self.path).path)
        if not m:
            return self._out(404, "Nicht gefunden", "text/plain; charset=utf-8")
        v = self._tok(m.group(1))
        if not v:
            return self._out(403, "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                                  "<body style='font:18px sans-serif;padding:24px'><h2>Link abgelaufen</h2>Bitte am PC einen neuen QR-Code erzeugen.</body>",
                             "text/html; charset=utf-8")
        try:
            return self._out(200, _m77_page(v), "text/html; charset=utf-8")
        except Exception as e:
            return self._out(500, f"Fehler: {e}", "text/plain; charset=utf-8")

    def do_POST(self):
        m = re.fullmatch(r"/s/([A-Za-z0-9_\-]{10,64})/sig", urlparse(self.path).path)
        if not m:
            return self._out(404, {"ok": False, "error": "Nicht gefunden"})
        v = self._tok(m.group(1))
        if not v:
            return self._out(403, {"ok": False, "error": "Link abgelaufen – am PC neuen QR-Code erzeugen."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 3 * 1048576:
            return self._out(413, {"ok": False, "error": "Ungültige Daten."})
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(d, dict):
                raise ValueError("Ungültige Daten.")
            # the signer must sign exactly the content shown on the phone - not a version changed on the PC meanwhile
            if d.get("hash") != _m77_content_hash(_m77_load(v["id"])):
                raise ValueError("Das Protokoll wurde inzwischen am PC geändert – bitte die Seite neu laden und erneut prüfen.")
            res = m77_sign(v["id"], v["rolle"], d.get("name"), d.get("png"))
            v["fertig"] = True
            return self._out(200, {"ok": True, "status": res.get("status")})
        except ValueError as e:
            return self._out(200, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._out(500, {"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Schlussrechnung check (m40)
# ---------------------------------------------------------------------------
@chain_step("m40_create_schluss", "m77_abnahme")
def _m77_step_m40_create_schluss(_next, pid, quelle=None):
    st = m77_settings()
    fg = m77_freigabe(pid) if st.get("pruefen") else {"ok": True}
    if not fg["ok"] and st.get("sperren"):
        raise ValueError("Schlussrechnung gesperrt: " + fg["text"] + " Bitte zuerst das Abnahmeprotokoll erstellen und unterschreiben lassen "
                         "(oder unter Einstellungen > EN 1090 & Abnahme die Sperre ausschalten).")
    r = _next(pid, quelle)
    if not fg["ok"] and isinstance(r, dict):
        r.setdefault("warn", []).append("Hinweis: " + fg["text"])
    elif fg.get("maengel_offen") and isinstance(r, dict):
        r.setdefault("warn", []).append(f"Hinweis: {fg['maengel_offen']} Mangel/Mängel aus der Abnahme sind noch offen.")
    return r


def m77_overview():
    rows = q("SELECT a.*, p.nr pnr, p.name pname FROM m77_prot a LEFT JOIN projects p ON p.id=a.project_id ORDER BY a.datum DESC, a.id DESC")
    out, maengel = [], []
    t = today()
    for r in rows:
        pn, pnm = r.pop("pnr"), r.pop("pname")
        r = _m77_strip(_m77_load(r))
        r["sig_kunde_img"] = r["sig_an_img"] = ""
        r["pnr"], r["pname"] = pn, pnm
        out.append(r)
        for i, m in enumerate(r["maengel"]):
            maengel.append({"prot_id": r["id"], "idx": i, "nr": r["nr"], "project_id": r["project_id"], "pnr": pn, "pname": pnm,
                            "text": m.get("text", ""), "frist": m.get("frist", ""), "erledigt_am": m.get("erledigt_am", ""),
                            "ueber": bool(m.get("frist") and not m.get("erledigt_am") and m["frist"] < t)})
    maengel.sort(key=lambda m: (bool(m["erledigt_am"]), m["frist"] or "9999"))
    return {"protokolle": out, "maengel": maengel}


def _m77_settings_save(h, d):
    cur_ = m77_settings()
    if "port" in d:
        cur_["port"] = max(1024, min(65000, int(float(d.get("port") or 8782))))
    for k in ("pruefen", "sperren"):
        if k in d:
            cur_[k] = bool(d[k])
    if "an_name" in d:
        cur_["an_name"] = str(d.get("an_name") or "")[:120]
    set_setting("m77", cur_)
    return h._send(200, {"ok": True, "settings": cur_})


HOOK_GET["/api/m77/project"] = lambda h, qs: h._send(200, m77_project(int(qs["project_id"])))
HOOK_GET["/api/m77/prot"] = lambda h, qs: h._send(200, _m77_load(int(qs["id"])))
HOOK_GET["/api/m77/settings"] = lambda h, qs: h._send(200, {"ok": True, "settings": m77_settings()})
HOOK_GET["/api/m77/overview"] = lambda h, qs: h._send(200, m77_overview())
HOOK_GET["/api/m77/handy/status"] = lambda h, qs: h._send(200, m77_handy_status(qs.get("token")))
HOOK_POST["/api/m77/save"] = lambda h, d: h._send(200, m77_save(d))
HOOK_POST["/api/m77/delete"] = lambda h, d: h._send(200, m77_delete(d.get("ids") or [d.get("id")]))
HOOK_POST["/api/m77/mangel"] = lambda h, d: h._send(200, m77_mangel(d))
HOOK_POST["/api/m77/sign"] = lambda h, d: h._send(200, m77_sign(d["id"], d.get("rolle"), d.get("name"), d.get("png")))
HOOK_POST["/api/m77/unsign"] = lambda h, d: h._send(200, m77_unsign(d))
HOOK_POST["/api/m77/pdf"] = lambda h, d: h._send(200, {"ok": True, "path": m77_pdf(int(d["id"]))})
HOOK_POST["/api/m77/handy/start"] = lambda h, d: h._send(200, m77_handy_start(d))
HOOK_POST["/api/m77/handy/stop"] = lambda h, d: h._send(200, m77_stop())
HOOK_POST["/api/m77/settings"] = _m77_settings_save


def _m77_boot(b):
    try:
        t = today()
        ue = 0
        offen = 0
        for r in q("SELECT maengel FROM m77_prot"):
            for m in json.loads(r["maengel"] or "[]"):
                if not m.get("erledigt_am"):
                    offen += 1
                    if m.get("frist") and m["frist"] < t:
                        ue += 1
        b["m77"] = {"maengel_offen": offen, "maengel_ueber": ue}
    except Exception:
        b["m77"] = {"maengel_offen": 0, "maengel_ueber": 0}


HOOK_BOOT.append(_m77_boot)


def _m77_ex(p):
    ov = m77_overview()
    rows = ov["protokolle"]
    if p.get("project_id"):
        rows = [r for r in rows if r["project_id"] == int(p["project_id"])]
    ids = {int(i) for i in (p.get("ids") or []) if str(i).isdigit()}
    if ids:
        rows = [r for r in rows if r["id"] in ids]
    pids = {r["id"] for r in rows}
    return [_sh("Abnahmen", [("Nr.", "t", 16), ("Datum", "d", 11), ("Projekt", "t", 30), ("Ergebnis", "t", 26), ("Status", "t", 14),
                             ("Mängel offen", "n", 10)],
                [[r["nr"], r["datum"], f"{r['pnr']} {r['pname']}", r["ergebnis_de"], r["status"], r["maengel_offen"]] for r in rows],
                f"Stand {de_date(today())}", total=False),
            _sh("Mängel", [("Protokoll", "t", 16), ("Projekt", "t", 28), ("Mangel", "t", 44), ("Frist", "d", 11), ("erledigt am", "d", 11)],
                [[m["nr"], f"{m['pnr']} {m['pname']}", m["text"], m["frist"], m["erledigt_am"]] for m in ov["maengel"] if m["prot_id"] in pids], "", total=False)]


EXPORTS["m77_abnahme"] = ("Abnahmen", _m77_ex)


def _m77_selftest():
    err = []
    pid = None
    try:
        pid = x("INSERT INTO projects (nr, name, bereich, status, start, folders, created, updated) VALUES (?,?,?,?,?,?,?,?)",
                ("_ST77", "Selbsttest Abnahme", "AV", "aktiv", today(), "[]", now_iso(), now_iso()))
        r = m77_save({"project_id": pid, "datum": today(), "ort": "Saal 1", "ergebnis": "erteilt",
                      "leistungen": [{"text": "Mediensteuerung", "ok": True}], "maengel": [{"text": "Kabelkanal fehlt", "frist": "2000-01-01"}]})
        rid = r["id"]
        if m77_freigabe(pid)["ok"]:
            err.append("m77: Freigabe ohne Unterschrift")
        # 4x2 white PNG
        png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAQAAAACCAIAAADwyuo0AAAAFElEQVR4XmP8//8/AwwwwVkMDAwASAYDAan28UMAAAAASUVORK5CYII="
        m77_sign(rid, "kunde", "Kunde Test", png)
        res = m77_sign(rid, "an", "T. Pfeiffer", png)
        if res.get("status") != "unterschrieben" or not m77_freigabe(pid)["ok"]:
            err.append("m77: Freigabe nach Unterschrift fehlt")
        if not res.get("pdf"):
            err.append("m77: PDF nicht erstellt " + str(res.get("warn") or ""))
        m77_mangel({"id": rid, "idx": 0, "erledigt": True})
        if _m77_load(rid)["status"] != "unterschrieben":
            err.append("m77: Mangel-Erledigung hat Unterschrift verworfen")
        m77_save({"id": rid, "project_id": pid, "datum": today(), "ort": "Saal 2", "ergebnis": "erteilt",
                  "leistungen": [{"text": "Mediensteuerung", "ok": True}], "maengel": [{"text": "Kabelkanal fehlt", "frist": "2000-01-01"}]})
        if _m77_load(rid)["status"] != "entwurf":
            err.append("m77: Inhaltsänderung hat Unterschriften nicht verworfen")
    except Exception as e:
        err.append(f"m77 Ausnahme: {e}")
    finally:
        if pid:
            x("DELETE FROM m77_prot WHERE project_id=?", (pid,))
            x("DELETE FROM project_files WHERE project_id=?", (pid,))
            x("DELETE FROM projects WHERE id=?", (pid,))
    return err


HOOK_SELFTEST.append(_m77_selftest)
