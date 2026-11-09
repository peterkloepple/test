# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m62_schriften (v2.0.11)
# Schriftarten fuer alle Dokumente:
#  - Ordner "Schriften" im Datenordner: .ttf / .otf / .ttc hineinlegen (Explorer,
#    Hineinziehen, ZIP oder "Aus Windows uebernehmen")
#  - Familien werden automatisch erkannt (Normal, Fett, Kursiv, Fett kursiv)
#  - Wahl: Standard fuer alle Dokumente, je Projekt (alle Dokumente des Projekts)
#    und je Dokument (Rechnung, Angebot, AB, Storno, Brief) - je nach Lust und Laune
#  - festgeschriebene Rechnungen behalten ihre Schrift (GoBD: Nachdruck identisch)
# Prioritaet: Dokument > Projekt > Standard > Helvetica.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M62_VERSION = "1.0.0"
FONT_DIR = os.path.join(DATA_DIR, "Schriften")
FONT_EXT = (".ttf", ".otf", ".ttc", ".otc")
FONT_LOCK = threading.RLock()
FONT_STATE = {"fam": {}, "probleme": [], "zeit": 0.0, "sig": None}
SYS_FONT_CACHE = {"sig": None, "fam": {}}
FONT_STYLE_DE = {"r": "Normal", "b": "Fett", "i": "Kursiv", "bi": "Fett kursiv"}
FONT_README = ("Schriften fuer Pfeiffer-Audio Rechnung\r\n\r\n"
               "Hier .ttf-, .otf- oder .ttc-Dateien ablegen (auch in Unterordnern). Nach dem Ablegen im Programm unter\r\n"
               "Einstellungen > Dokumente > Schriftarten auf \"Neu einlesen\" klicken.\r\n\r\n"
               "Eine Familie besteht am besten aus vier Dateien: Normal, Fett, Kursiv, Fett kursiv.\r\n"
               "OpenType-Dateien mit PostScript-Konturen (CFF) koennen nicht in PDFs eingebettet werden - bitte die TTF-Variante nehmen.\r\n")


# ---------------- reading font files (own fast parser) ----------------

def _u16(b, o):
    return int.from_bytes(b[o:o + 2], "big")


def _u32(b, o):
    return int.from_bytes(b[o:o + 4], "big")


def _face_info(data, off):
    """table directory at off -> dict with names and flags"""
    n = _u16(data, off + 4)
    tabs = {}
    for i in range(n):
        e = off + 12 + i * 16
        tabs[data[e:e + 4].decode("latin-1")] = (_u32(data, e + 8), _u32(data, e + 12))
    names = {}
    if "name" in tabs:
        o, _ln = tabs["name"]
        cnt, so = _u16(data, o + 2), o + _u16(data, o + 4)
        for i in range(cnt):
            r = o + 6 + i * 12
            pid, eid, lid, nid, ln, no = (_u16(data, r), _u16(data, r + 2), _u16(data, r + 4), _u16(data, r + 6), _u16(data, r + 8), _u16(data, r + 10))
            if nid not in (1, 2, 4, 6, 16, 17):
                continue
            raw = data[so + no:so + no + ln]
            if pid == 3 or pid == 0:
                txt = raw.decode("utf-16-be", "replace")
                prio = 3 if (pid == 3 and lid in (0x0409, 0x0407)) else 2
            elif pid == 1 and eid == 0:
                txt = raw.decode("mac_roman", "replace")
                prio = 1
            else:
                continue
            if txt.strip() and prio > names.get(nid, (0, ""))[0]:
                names[nid] = (prio, txt.strip())
    nm = {k: v[1] for k, v in names.items()}
    bold = italic = False
    fstype, weight = 0, 400
    if "OS/2" in tabs:
        o, _ln = tabs["OS/2"]
        weight = _u16(data, o + 4)
        fstype = _u16(data, o + 8)
        sel = _u16(data, o + 62)
        italic, bold = bool(sel & 1), bool(sel & 32)
    elif "head" in tabs:
        ms = _u16(data, tabs["head"][0] + 44)
        bold, italic = bool(ms & 1), bool(ms & 2)
    sub = (nm.get(2) or "").lower()
    if "bold" in sub or "fett" in sub:
        bold = True
    if "italic" in sub or "oblique" in sub or "kursiv" in sub:
        italic = True
    return {"family": nm.get(1) or nm.get(16) or nm.get(4) or "", "sub": nm.get(2) or "", "full": nm.get(4) or "",
            "ps": nm.get(6) or "", "tfam": nm.get(16) or "", "bold": bold, "italic": italic, "weight": weight,
            "cff": "CFF " in tabs or "CFF2" in tabs, "glyf": "glyf" in tabs, "variabel": "fvar" in tabs,
            "eingeschraenkt": bool(fstype & 0x0002) and not (fstype & 0x000C)}


def font_faces(path):
    """-> list of faces (TTC = several)"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == b"ttcf":
        n = _u32(data, 8)
        out = []
        for i in range(min(n, 64)):
            fi = _face_info(data, _u32(data, 12 + i * 4))
            fi["index"] = i
            out.append(fi)
        return out
    if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
        raise ValueError("keine TrueType-/OpenType-Datei")
    fi = _face_info(data, 0)
    fi["index"] = 0
    return [fi]


def _style_key(fi):
    return ("b" if fi["bold"] else "") + ("i" if fi["italic"] else "") or "r"


def _slug(t):
    return re.sub(r"[^A-Za-z0-9]+", "", t)[:40] or "Font"


def _face_ok(fi):
    if fi["cff"] and not fi["glyf"]:
        return "OpenType mit PostScript-Konturen (CFF) – kann nicht eingebettet werden, bitte die TTF-Variante verwenden"
    if fi["eingeschraenkt"]:
        return "Lizenz der Schrift verbietet das Einbetten in Dokumente"
    return ""


def _collect(paths):
    """files -> {family: {style: (path, index, info)}}, problems"""
    fam, probs = {}, []
    allp = {}
    for p in paths:
        try:
            faces = font_faces(p)
        except Exception as e:
            probs.append({"datei": os.path.basename(p), "grund": f"nicht lesbar ({e})"})
            continue
        for fi in faces:
            why = _face_ok(fi)
            if why:
                probs.append({"datei": os.path.basename(p) + (f" #{fi['index']}" if fi["index"] else ""), "grund": why, "familie": fi["family"]})
                continue
            name = fi["family"] or os.path.splitext(os.path.basename(p))[0]
            allp.setdefault(name, set()).add(p)
            st = _style_key(fi)
            cur = fam.setdefault(name, {}).get(st)
            # several weights with the same RIBBI flags: prefer the one closest to 400/700
            if cur is None or abs(fi["weight"] - (700 if "b" in st else 400)) < abs(cur[2]["weight"] - (700 if "b" in st else 400)):
                fam[name][st] = (p, fi["index"], fi)
    for name in fam:
        fam[name]["_alle"] = sorted(allp.get(name, ()))
    return fam, probs


def _font_files(folder):
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(("_", "."))]
        for fn in files:
            if fn.lower().endswith(FONT_EXT):
                out.append(os.path.join(root, fn))
    return sorted(out)


# ---------------- registering ----------------

def fonts_scan(force=False):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping
    with FONT_LOCK:
        os.makedirs(FONT_DIR, exist_ok=True)
        rd = os.path.join(FONT_DIR, "LIESMICH.txt")
        if not os.path.exists(rd):
            try:
                with open(rd, "w", encoding="utf-8") as f:
                    f.write(FONT_README)
            except OSError:
                pass
        files = _font_files(FONT_DIR)
        sig = [(p, os.path.getsize(p), int(os.path.getmtime(p))) for p in files]
        if not force and sig == FONT_STATE["sig"]:
            return FONT_STATE
        fam, probs = _collect(files)
        builtin = {k for k, v in FONT_FAMILIES.items() if v.get("builtin")}
        new_fams = {}
        info = {}
        for name, styles in sorted(fam.items()):
            alle = styles.pop("_alle", [])
            disp = name if name not in builtin else name + " (Datei)"
            reg = {}
            for st, (p, idx, fi) in styles.items():
                rn = f"PAF_{_slug(disp)}_{st}_{hashlib.md5((p + str(idx)).encode()).hexdigest()[:6]}"
                try:
                    if rn not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont(rn, p, subfontIndex=idx) if idx else TTFont(rn, p))
                    reg[st] = rn
                except Exception as e:
                    msg = str(e)
                    if "postscript" in msg.lower() or "cff" in msg.lower():
                        msg = "PostScript-Konturen (CFF) – bitte TTF-Variante"
                    elif "embed" in msg.lower() or "subset" in msg.lower():
                        msg = "Lizenz verbietet das Einbetten"
                    probs.append({"datei": os.path.basename(p), "grund": msg[:160], "familie": name})
            if not reg:
                continue
            r = reg.get("r") or reg.get("b") or reg.get("i") or reg.get("bi")
            b = reg.get("b") or r
            i = reg.get("i") or r
            bi = reg.get("bi") or reg.get("b") or reg.get("i") or r
            new_fams[disp] = {"r": r, "b": b, "i": i, "bi": bi, "builtin": False}
            try:
                for nm_, bo, it in ((r, 1, 1), (r, 0, 1), (r, 1, 0), (r, 0, 0)):   # normal last: ps2tt(r) must stay 'normal'
                    addMapping(nm_, bo, it, {(0, 0): r, (1, 0): b, (0, 1): i, (1, 1): bi}[(bo, it)])
            except Exception:
                pass
            info[disp] = {"name": disp, "stile": {k: k in reg for k in ("r", "b", "i", "bi")},
                          "dateien": [{"stil": FONT_STYLE_DE[k], "datei": os.path.relpath(v[0], FONT_DIR), "schnitt": v[2]["sub"],
                                       "variabel": v[2]["variabel"]} for k, v in sorted(styles.items()) if k in reg],
                          "alle": [os.path.relpath(x_, FONT_DIR) for x_ in alle]}
        # swap in one step: readers in other threads never see a half-filled table
        FONT_FAMILIES.update(new_fams)
        for k in [k for k, v in list(FONT_FAMILIES.items()) if not v.get("builtin") and k not in new_fams]:
            FONT_FAMILIES.pop(k, None)
        FONT_STATE.update(fam=info, probleme=probs, zeit=time.time(), sig=sig)
        _font_default_apply()
        return FONT_STATE


def _font_default_apply():
    d = str(get_settings().get("doc_font") or "Helvetica")
    FONT_DEFAULT["fam"] = d if d in FONT_FAMILIES else "Helvetica"


def font_ok(name):
    return bool(name) and name in FONT_FAMILIES


# ---------------- which font for which document ----------------

def font_for(font=None, project_id=None):
    if font and font_ok(font):
        return font
    if project_id:
        try:
            r = q("SELECT font FROM projects WHERE id=?", (int(project_id),), one=True)
            if r and font_ok(r["font"]):
                return r["font"]
        except Exception:
            pass
    return FONT_DEFAULT.get("fam") or "Helvetica"


def m62_schema():
    for t in ("invoices", "projects", "briefe"):
        try:
            have = {r["name"] for r in q(f"PRAGMA table_info({t})")}
            if have and "font" not in have:
                x(f"ALTER TABLE {t} ADD COLUMN font TEXT")
                if t == "invoices":
                    # everything issued before 2.0.11 was printed in Helvetica - keep it that way (GoBD)
                    x("UPDATE invoices SET font='Helvetica' WHERE locked=1 AND COALESCE(font,'')=''")
        except Exception:
            traceback.print_exc()
    try:
        fonts_scan(True)
    except Exception:
        traceback.print_exc()


HOOK_SCHEMA.append(m62_schema)

# invoices / offers / storno / reminders
def inv_font(inv):
    inv = inv or {}
    if inv.get("locked") and not font_ok(inv.get("font")):
        return "Helvetica"      # locked without stored font: issued before fonts existed
    return font_for(inv.get("font"), inv.get("project_id"))


@chain_step("render_invoice_pdf", "m62_schriften")
def _m62_step_render_invoice_pdf(_next, inv, s=None, attachments=True):
    fam = inv_font(inv)
    with doc_font(fam):
        return _next(inv, s, attachments)


@chain_step("save_invoice", "m62_schriften")
def _m62_step_save_invoice(_next, d, bump=True):
    res = _next(d, bump)
    if "font" in d:
        f = d.get("font") or None
        if not f or font_ok(f):     # a font that is missing right now keeps the stored choice
            x("UPDATE invoices SET font=? WHERE id=? AND COALESCE(locked,0)=0 AND COALESCE(font,'')!=COALESCE(?,'')", (f, res[0], f))
    return res


@chain_step("lock_invoice", "m62_schriften")
def _m62_step_lock_invoice(_next, iid):
    # GoBD: a locked invoice keeps the font it was issued with (reprint identical)
    try:
        r = q("SELECT font, project_id, locked, typ, status FROM invoices WHERE id=?", (iid,), one=True)
        if r and not r["locked"] and not r["font"] and r["typ"] in ("rechnung", "storno") and r["status"] != "entwurf":
            x("UPDATE invoices SET font=? WHERE id=?", (font_for(None, r["project_id"]), iid))
    except Exception:
        traceback.print_exc()
    return _next(iid)


@chain_step("storno_invoice", "m62_schriften")
def _m62_step_storno_invoice(_next, iid):
    # the cancellation looks like the original invoice; the original keeps its font when it gets locked
    try:
        r0 = q("SELECT font, project_id, locked FROM invoices WHERE id=?", (iid,), one=True)
        if r0 and not r0["locked"] and not r0["font"]:
            x("UPDATE invoices SET font=? WHERE id=?", (font_for(None, r0["project_id"]), iid))
    except Exception:
        traceback.print_exc()
    res = _next(iid)
    try:
        sid = res[0] if isinstance(res, (tuple, list)) else res
        r = q("SELECT font, project_id FROM invoices WHERE id=?", (iid,), one=True)
        if r and sid:
            x("UPDATE invoices SET font=? WHERE id=?", (r["font"] or font_for(None, r["project_id"]), sid))
    except Exception:
        traceback.print_exc()
    return res


@chain_step("convert_doc", "m62_schriften")
def _m62_step_convert_doc(_next, iid, to_typ):
    res = _next(iid, to_typ)
    try:
        r = q("SELECT font FROM invoices WHERE id=?", (iid,), one=True)
        if r and r["font"] and isinstance(res, (tuple, list)):
            x("UPDATE invoices SET font=? WHERE id=? AND COALESCE(font,'')='' AND COALESCE(locked,0)=0", (r["font"], res[0]))
    except Exception:
        traceback.print_exc()
    return res


@chain_step("m50_zugferd_pdf", "m62_schriften")
def _m62_step_m50_zugferd_pdf(_next, inv, opts=None, s=None, base_pdf=None):
    with doc_font(inv_font(inv)):
        return _next(inv, opts, s, base_pdf)


# letters
@chain_step("brief_pdf", "m62_schriften")
def _m62_step_brief_pdf(_next, b, vals, s=None):
    with doc_font(font_for((b or {}).get("font"), (b or {}).get("project_id"))):
        return _next(b, vals, s)


@chain_step("br_save", "m62_schriften")
def _m62_step_br_save(_next, d):
    bid = _next(d)
    if "font" in d:
        f = d.get("font") if font_ok(d.get("font")) else None
        x("UPDATE briefe SET font=? WHERE id=?", (f, bid))
    return bid


@chain_step("br_get", "m62_schriften")
def _m62_step_br_get(_next, bid):
    b = _next(bid)
    try:
        if b is not None and "font" not in b:
            r = q("SELECT font FROM briefe WHERE id=?", (int(bid),), one=True)
            b["font"] = r["font"] if r else None
    except Exception:
        pass
    return b


# project documents: calculation, handover documentation
@chain_step("m41_kalk_pdf", "m62_schriften")
def _m62_step_m41_kalk_pdf(_next, kid):
    pid = None
    try:
        r = q("SELECT project_id FROM m41_kalk WHERE id=?", (int(kid),), one=True)
        pid = r["project_id"] if r else None
    except Exception:
        pass
    with doc_font(font_for(None, pid)):
        return _next(kid)


@chain_step("handover_pdf", "m62_schriften")
def _m62_step_handover_pdf(_next, pid, file_ids, notes=""):
    with doc_font(font_for(None, pid)):
        return _next(pid, file_ids, notes)


# ---------------- system fonts (Windows) ----------------

def _sys_font_dirs():
    out = []
    if sys.platform.startswith("win"):
        out.append(os.path.join(os.environ.get("WINDIR") or "C:\\Windows", "Fonts"))
        la = os.environ.get("LOCALAPPDATA")
        if la:
            out.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    else:
        out += ["/usr/share/fonts", os.path.expanduser("~/.fonts"), "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    return [d for d in out if os.path.isdir(d)]


SYS_LOCK = threading.Lock()


def sys_fonts(qtxt=""):
    with SYS_LOCK:
        files = []
        for d in _sys_font_dirs():
            files += _font_files(d)
        sig = (len(files), sum(int(os.path.getmtime(p)) for p in files[:2000]))
        if SYS_FONT_CACHE["sig"] != sig:
            fam, _p = _collect(files)
            SYS_FONT_CACHE.update(sig=sig, fam={k: {st: v[0] for st, v in sts.items()} for k, sts in fam.items()})
    have = set(FONT_FAMILIES)
    ql = (qtxt or "").strip().lower()
    out = [{"name": k, "stile": {s_: s_ in v for s_ in ("r", "b", "i", "bi")}, "da": k in have}
           for k, v in sorted(SYS_FONT_CACHE["fam"].items(), key=lambda kv: kv[0].lower()) if not ql or ql in k.lower()]
    return {"ok": True, "schriften": out[:600], "anzahl": len(out)}


def sys_font_add(names):
    n = 0
    if not SYS_FONT_CACHE["fam"]:
        sys_fonts()
    with FONT_LOCK:
        for name in names or []:
            for st, p in (SYS_FONT_CACHE["fam"].get(name) or {}).items():
                dst = os.path.join(FONT_DIR, os.path.basename(p))
                if not os.path.exists(dst):
                    shutil.copy2(p, dst)
                    n += 1
    fonts_scan(True)
    return {"ok": True, "kopiert": n, "fonts": fonts_view()}


# ---------------- upload / delete / views ----------------

def _font_upload(h, tmp, name):
    added, skipped = [], []
    try:
        os.makedirs(FONT_DIR, exist_ok=True)
        low = (name or "").lower()
        if low.endswith(".zip"):
            with zipfile.ZipFile(tmp) as z:
                for zi in z.infolist():
                    bn = os.path.basename(zi.filename)
                    if zi.is_dir() or not bn.lower().endswith(FONT_EXT) or bn.startswith("._") or zi.file_size > 60_000_000:
                        continue
                    dst = os.path.join(FONT_DIR, safe_name(bn))
                    if os.path.exists(dst):
                        skipped.append(bn)
                        continue
                    with z.open(zi) as src, open(dst, "wb") as f:
                        shutil.copyfileobj(src, f)
                    added.append(bn)
        elif low.endswith(FONT_EXT):
            font_faces(tmp)   # raises for garbage
            dst = os.path.join(FONT_DIR, safe_name(os.path.basename(name)))
            if os.path.exists(dst):
                skipped.append(name)
            else:
                shutil.copyfile(tmp, dst)
                added.append(name)
        else:
            raise ValueError("Bitte .ttf-, .otf-, .ttc-Dateien oder ein ZIP mit Schriften wählen.")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    fonts_scan(True)
    return h._send(200, {"ok": True, "neu": added, "schon_da": skipped, "fonts": fonts_view()})


def font_delete(name):
    info = FONT_STATE["fam"].get(name)
    if not info:
        raise ValueError("Diese Schrift liegt nicht im Schriften-Ordner.")
    n_lock = q("SELECT COUNT(*) n FROM invoices WHERE font=? AND locked=1", (name,), one=True)["n"]
    if n_lock:
        raise ValueError(f"„{name}“ wird von {n_lock} festgeschriebenen Rechnung(en) verwendet und bleibt deshalb erhalten "
                         "(ein Nachdruck muss genau gleich aussehen).")
    dd = os.path.join(DATA_DIR, TRASH_DIR, time.strftime("%Y-%m-%d"), "Schriften")
    os.makedirs(dd, exist_ok=True)
    n = 0
    for rel in info.get("alle") or [f["datei"] for f in info["dateien"]]:
        src = os.path.join(FONT_DIR, rel)
        if os.path.isfile(src):
            dst = os.path.join(dd, os.path.basename(src))
            if os.path.exists(dst):
                dst = os.path.join(dd, uuid.uuid4().hex[:6] + "_" + os.path.basename(src))
            shutil.move(src, dst)
            n += 1
    fonts_scan(True)
    return {"ok": True, "verschoben": n, "fonts": fonts_view()}


def fonts_view():
    st = FONT_STATE
    fams = [{"name": k, "builtin": True, "stile": {"r": True, "b": True, "i": True, "bi": True}, "dateien": []}
            for k in ("Helvetica", "Times", "Courier")]
    fams += [dict(v, builtin=False) for k, v in sorted(st["fam"].items(), key=lambda kv: kv[0].lower())]
    s = get_settings()
    used = {}
    try:
        for r in q("SELECT font, COUNT(*) n FROM invoices WHERE COALESCE(font,'')!='' GROUP BY font"):
            used[r["font"]] = used.get(r["font"], 0) + r["n"]
    except Exception:
        pass
    for f in fams:
        f["benutzt"] = used.get(f["name"], 0)
    return {"ok": True, "familien": fams, "standard": FONT_DEFAULT.get("fam") or "Helvetica", "gewaehlt": s.get("doc_font") or "Helvetica",
            "probleme": st["probleme"], "ordner": FONT_DIR}


def font_file(name, st):
    info = FONT_STATE["fam"].get(name)
    if not info:
        return None
    m = {f["stil"]: f["datei"] for f in info["dateien"]}
    rel = m.get(FONT_STYLE_DE.get(st, "Normal")) or m.get("Normal") or (info["dateien"][0]["datei"] if info["dateien"] else None)
    if not rel:
        return None
    fp = os.path.realpath(os.path.join(FONT_DIR, rel))
    if os.path.commonpath([os.path.realpath(FONT_DIR), fp]) != os.path.realpath(FONT_DIR) or not os.path.isfile(fp):
        return None
    return fp


def font_probe(name):
    """sample page in this font -> preview token"""
    from reportlab.lib.pagesizes import A4 as _A4
    fam = name if font_ok(name) else "Helvetica"
    buf = io.BytesIO()
    with doc_font(fam):
        c = rl_canvas.Canvas(buf, pagesize=_A4)
        W, H = _A4
        y = H - 70
        c.setFont(FONT_B(), 22)
        c.drawString(56, y, fam)
        y -= 34
        for st, fn in (("Normal", FONT_R()), ("Fett", FONT_B()), ("Kursiv", FONT_I()), ("Fett kursiv", FONT_BI())):
            c.setFont(fn, 13)
            c.drawString(56, y, f"{st}: Rechnung Nr. 2026-042 · Summe 1.234,56 € · ÄÖÜ äöü ß")
            y -= 24
        y -= 10
        c.setFont(FONT_R(), 10)
        for ln in ("Sehr geehrte Damen und Herren,", "für die Inbetriebnahme der Q-SYS-Anlage im großen Saal berechnen wir Ihnen:",
                   "1  Programmierung Q-SYS Core 110f        8,00 h      95,00 €      760,00 €",
                   "2  Schweißarbeiten Traverse (135 MAG)     3,50 h      78,00 €      273,00 €",
                   "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789 @ & % § € « » „ “ – —"):
            c.drawString(56, y, ln)
            y -= 16
        for sz in (8, 9, 10, 11, 12, 14, 18):
            c.setFont(FONT_R(), sz)
            c.drawString(56, y - 6, f"{sz} pt  Pfeiffer-Audio Rechnung")
            y -= sz + 10
        c.showPage()
        c.save()
    pngs = pdf_to_pngs(buf.getvalue())
    tok = uuid.uuid4().hex[:12]
    PREVIEW.clear()
    PREVIEW[tok] = pngs
    return {"ok": True, "token": tok, "pages": len(pngs)}


def _font_file_route(h, qs):
    fp = font_file(qs.get("fam") or "", qs.get("st") or "r")
    if not fp:
        return h._send(404, b"", "text/plain")
    ext = os.path.splitext(fp)[1].lower()
    mt = {".ttf": "font/ttf", ".otf": "font/otf", ".ttc": "font/collection"}.get(ext, "application/octet-stream")
    with open(fp, "rb") as f:
        return h._send(200, f.read(), mt)


def _font_set_default(d):
    f = d.get("font") or "Helvetica"
    if not font_ok(f):
        raise ValueError("Diese Schrift ist nicht vorhanden.")
    set_setting("doc_font", f)
    _font_default_apply()
    return fonts_view()


def _font_set_project(d):
    f = d.get("font") or None
    if f and not font_ok(f):
        raise ValueError("Diese Schrift ist nicht vorhanden.")
    x("UPDATE projects SET font=? WHERE id=?", (f, int(d["project_id"])))
    return {"ok": True}


def _m62_boot(d):
    try:
        fonts_scan()
    except Exception:
        traceback.print_exc()
    d["fonts"] = {"liste": ["Helvetica", "Times", "Courier"] + sorted(FONT_STATE["fam"], key=str.lower),
                  "standard": FONT_DEFAULT.get("fam") or "Helvetica"}


def _m62_selftest():
    err = []
    try:
        with doc_font("Times"):
            if FONT_R() != "Times-Roman" or FONT_B() != "Times-Bold":
                err.append("Schriften: Umschalten auf Times wirkt nicht")
        if font_for("gibt-es-nicht", None) not in FONT_FAMILIES:
            err.append("Schriften: unbekannte Schrift faellt nicht zurueck")
    except Exception as e:
        err.append(f"Schriften: {e}")
    return err


HOOK_GET["/api/fonts"] = lambda h, qs: h._send(200, fonts_view())
HOOK_GET["/api/fonts/file"] = _font_file_route
HOOK_GET["/api/fonts/system"] = lambda h, qs: h._send(200, sys_fonts(qs.get("q") or ""))
HOOK_POST["/api/fonts/rescan"] = lambda h, d: (fonts_scan(True), h._send(200, fonts_view()))[1]
HOOK_POST["/api/fonts/default"] = lambda h, d: h._send(200, _font_set_default(d))
HOOK_POST["/api/fonts/project"] = lambda h, d: h._send(200, _font_set_project(d))
HOOK_POST["/api/fonts/delete"] = lambda h, d: h._send(200, font_delete(d.get("name") or ""))
HOOK_POST["/api/fonts/probe"] = lambda h, d: h._send(200, font_probe(d.get("font") or ""))
HOOK_POST["/api/fonts/system/add"] = lambda h, d: h._send(200, sys_font_add(d.get("namen") or []))
HOOK_POST["/api/fonts/open"] = lambda h, d: (os.makedirs(FONT_DIR, exist_ok=True), open_path(FONT_DIR), h._send(200, {"ok": True}))[2]
HOOK_UPLOAD["/api/upload/font"] = _font_upload
HOOK_BOOT.append(_m62_boot)
HOOK_SELFTEST.append(_m62_selftest)
