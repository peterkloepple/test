# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m20_zusatz_main
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

# ---------------- v1.6.6: Korrektur der Buchhaltung aus dem Jahresabschluss ----------------
KORR_PARTNER = "Korrektur Jahresabschluss"


def korr_list(year):
    out = []
    for b in q("SELECT * FROM belege WHERE partner LIKE ? AND substr(datum,1,4)=? ORDER BY id", (KORR_PARTNER + "%", str(year))):
        try:
            dd = json.loads(b["details"] or "{}")
        except Exception:
            dd = {}
        if not dd.get("korrektur"):
            continue
        out.append({"id": b["id"], "art": "beleg", "feld": dd.get("korrektur"), "typ": b["typ"], "datum": b["datum"], "kategorie": b["kategorie"] or "",
                    "betrag": dd.get("diff", b["betrag"] or 0), "notiz": b["notiz"] or "", "am": (b["created"] or "")[:10]})
    for i, k in enumerate((tax_inputs(year).get("abschluss") or {}).get("korrekturen") or []):
        out.append({"id": i, "art": "eingabe", "feld": k.get("feld"), "typ": "eingabe", "datum": k.get("am", ""), "kategorie": k.get("text", ""),
                    "betrag": k.get("diff", 0), "notiz": k.get("notiz", ""), "am": k.get("am", ""), "alt": k.get("alt"), "neu": k.get("neu")})
    return out


def abschluss_programm(year):
    e = euer(year)
    tc = tax_calc(year)
    g = tc["gehalt"]
    return {"einnahmen": e["einnahmen"], "ausgaben": e["ausgaben"], "gewinn": e["gewinn"],
            "bruttolohn": g["brutto"], "lst_abzug": round(g["lst"], 2), "soli_lohn": g["soli"],
            "wk": round(max(tc["wk_pauschale"], tc["wk_real"]), 2), "wk_real": tc["wk_real"], "wk_pauschale": tc["wk_pauschale"],
            "zve": tc["calc"]["zve"], "est_festgesetzt": tc["calc"]["est"], "soli_festgesetzt": tc["calc"]["soli"]}


def korr_book(d):
    year = int(d["year"])
    feld = d.get("feld")
    diff = round(float(d.get("betrag") or 0), 2)
    if abs(diff) < 0.005:
        raise ValueError("Keine Abweichung - nichts zu korrigieren.")
    datum = d.get("datum") or f"{year}-12-31"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum) or int(datum[:4]) != year:
        raise ValueError(f"Das Buchungsdatum muss im Jahr {year} liegen.")
    notiz = (d.get("notiz") or "").strip()
    partner = f"{KORR_PARTNER} {year}"
    if feld == "gewinn":
        feld = "einnahmen" if d.get("via") != "ausgaben" else "ausgaben"
        if feld == "ausgaben":
            diff = -diff   # more profit = less expenses
    if feld == "einnahmen":
        det = {"korrektur": "einnahmen", "diff": diff}
        bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("einnahme", datum, partner, "KORR", diff, "Korrektur Jahresabschluss", notiz or f"Abgleich mit Steuererklärung {year}", "",
                 json.dumps(det), None, None, now_iso()))
        return {"ok": True, "id": bid, "info": f"Korrekturbuchung Einnahmen {money(diff)} angelegt."}
    if feld == "ausgaben":
        kat = d.get("kategorie") or "Sonstige Betriebsausgaben"
        if kat not in EUER_KATEGORIEN:
            kat = "Sonstige Betriebsausgaben"
        betrag = round(diff / 0.7, 2) if kat.startswith("Bewirtung") else diff
        det = {"korrektur": "ausgaben", "diff": diff}
        bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("ausgabe", datum, partner, "KORR", betrag, kat, notiz or f"Abgleich mit Steuererklärung {year}", "", json.dumps(det), None, None, now_iso()))
        return {"ok": True, "id": bid, "info": f"Korrekturbuchung Ausgaben {money(diff)} ({kat}) angelegt."}
    if feld in ("bruttolohn", "lst_abzug"):
        det = {"zeitraum": "jahr", "korrektur": feld, "diff": diff}
        for k in ("brutto", "lst", "soli", "kist", "rv", "kv", "pv", "av", "netto"):
            det[k] = 0.0
        det["brutto" if feld == "bruttolohn" else "lst"] = diff
        if feld == "bruttolohn":
            det["netto"] = diff
        bid = x("INSERT INTO belege (typ, datum, partner, nr, betrag, kategorie, notiz, file, details, invoice_id, project_id, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("gehalt", datum, partner, "KORR", det["netto"], "", notiz or f"Abgleich mit Bescheid {year}", "", json.dumps(det), None, None, now_iso()))
        return {"ok": True, "id": bid, "info": f"Korrektur {'Bruttolohn' if feld == 'bruttolohn' else 'Lohnsteuer'} {money(diff)} angelegt."}
    if feld == "wk":
        r = q("SELECT data FROM taxyear WHERE year=?", (year,), one=True)
        dd = json.loads(r["data"]) if r else {}
        t = tax_inputs(year)
        alt = float(t.get("wk") or 0)
        neu = round(max(0.0, alt + diff), 2)
        dd["wk"] = neu
        ab = dd.get("abschluss") or {}
        ab.setdefault("korrekturen", []).append({"feld": "wk", "alt": alt, "neu": neu, "diff": diff, "am": today(), "notiz": notiz,
                                                "text": "Werbungskosten tatsächlich"})
        dd["abschluss"] = ab
        x("INSERT OR REPLACE INTO taxyear (year, data) VALUES (?,?)", (year, json.dumps(dd, ensure_ascii=False)))
        return {"ok": True, "info": f"Werbungskosten (tatsächlich) von {money(alt)} auf {money(neu)} gesetzt."}
    raise ValueError("Dieses Feld kann nicht direkt korrigiert werden.")


def korr_undo(d):
    year = int(d["year"])
    if d.get("art") == "eingabe":
        r = q("SELECT data FROM taxyear WHERE year=?", (year,), one=True)
        dd = json.loads(r["data"]) if r else {}
        ab = dd.get("abschluss") or {}
        ks = ab.get("korrekturen") or []
        i = int(d["id"])
        if 0 <= i < len(ks):
            k = ks.pop(i)
            if k.get("feld") == "wk":
                # exact restore: the booking was clamped at 0 (neu = max(0, alt + diff)), so undo the real change neu - alt
                cur_wk = float(dd.get("wk") or 0)
                if k.get("alt") is not None and k.get("neu") is not None:
                    dd["wk"] = round(max(0.0, cur_wk - (float(k["neu"]) - float(k["alt"]))), 2)
                else:
                    dd["wk"] = round(max(0.0, cur_wk - float(k.get("diff") or 0)), 2)
        ab["korrekturen"] = ks
        dd["abschluss"] = ab
        x("INSERT OR REPLACE INTO taxyear (year, data) VALUES (?,?)", (year, json.dumps(dd, ensure_ascii=False)))
        return {"ok": True}
    b = q("SELECT * FROM belege WHERE id=? AND partner LIKE ?", (int(d["id"]), KORR_PARTNER + "%"), one=True)
    if not b:
        raise ValueError("Korrekturbuchung nicht gefunden.")
    x("DELETE FROM belege WHERE id=?", (b["id"],))
    return {"ok": True}


# ---------------- v1.6.4: Assistent - doppelte Belege / Rechnungen nachtraeglich finden ----------------
FHASH = {}


def _file_sha(rel):
    if not rel:
        return ""
    fp = rel if os.path.isabs(rel) else os.path.join(DATA_DIR, rel)
    try:
        st_ = os.stat(fp)
    except OSError:
        return ""
    k = (fp, st_.st_size, int(st_.st_mtime))
    if k not in FHASH:
        h = hashlib.sha256()
        with open(fp, "rb") as fh:
            for ch in iter(lambda: fh.read(1 << 20), b""):
                h.update(ch)
        FHASH[k] = h.hexdigest()
    return FHASH[k]


_NORM_RX1 = re.compile(r"\b(gmbh|co|kg|ag|ug|e\.?k\.?|ohg|gbr|mbh|und|&)\b")
_NORM_RX2 = re.compile(r"[^a-z0-9äöüß]")
_NORM_CACHE = {}


def _norm(t):
    # v2.0.6: precompiled + cached (find_duplicates calls this ~4x per Beleg)
    t = t or ""
    r = _NORM_CACHE.get(t)
    if r is None:
        if len(_NORM_CACHE) > 20000:
            _NORM_CACHE.clear()
        r = _NORM_RX2.sub("", _NORM_RX1.sub(" ", t.lower()))
        _NORM_CACHE[t] = r
    return r


class _UF:
    def __init__(self):
        self.p = {}

    def f(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def u(self, a, b):
        self.p[self.f(a)] = self.f(b)


def find_duplicates():
    ign = set(json.loads(get_settings().get("dup_ignore") or "[]"))
    out = []
    # ---- Belege ----
    bel = {b["id"]: b for b in q("SELECT * FROM belege")}
    uf, why, keys = _UF(), {}, {}
    for b in bel.values():
        uf.f(b["id"])
        cents = int(round((b["betrag"] or 0) * 100))
        cand = []
        hs = _file_sha(b["file"]) if b["file"] else ""
        if hs:
            cand.append(("h:" + hs, "gleiche Datei"))
        if b["typ"] != "anlage":
            nr = _norm(b["nr"])
            if nr and len(nr) >= 3:
                cand.append((f"n:{b['typ']}|{cents}|{nr}", "gleiche Beleg-Nr. und gleicher Betrag"))
            pn = _norm(b["partner"])
            if pn and b["datum"]:
                cand.append((f"p:{b['typ']}|{cents}|{b['datum']}|{pn}", "gleicher Partner, gleiches Datum, gleicher Betrag"))
        for k, w in cand:
            if k in keys:
                uf.u(b["id"], keys[k])
                r_ = uf.f(b["id"])
                why.setdefault(r_, set()).add(w)
            else:
                keys[k] = b["id"]
    cl = {}
    for i in bel:
        cl.setdefault(uf.f(i), []).append(i)
    used_bank = {r["beleg_id"] for r in q("SELECT beleg_id FROM bank_tx WHERE beleg_id IS NOT NULL")} if q("SELECT name FROM sqlite_master WHERE name='bank_tx'") else set()
    used_asset = {r["beleg_id"] for r in q("SELECT beleg_id FROM assets WHERE beleg_id IS NOT NULL")}
    for root, ids in cl.items():
        if len(ids) < 2:
            continue
        ids.sort()
        sig = "b:" + ",".join(map(str, ids))
        if sig in ign:
            continue
        reasons = set()
        for i in ids:
            reasons |= why.get(uf.f(i), set())

        def score(i):
            b = bel[i]
            return (1 if b["invoice_id"] else 0) + (1 if i in used_bank else 0) + (1 if i in used_asset else 0) + (0.5 if b["file"] else 0) + (0.3 if b["project_id"] else 0)
        keep = sorted(ids, key=lambda i: (-score(i), i))[0]
        out.append({"sig": sig, "kind": "beleg", "grund": ", ".join(sorted(reasons)) or "gleiche Daten", "keep": keep,
                    "items": [{"id": i, "typ": BTYP_DE.get(bel[i]["typ"], bel[i]["typ"]), "datum": bel[i]["datum"], "partner": bel[i]["partner"] or "",
                               "nr": bel[i]["nr"] or "", "betrag": bel[i]["betrag"] or 0, "kategorie": bel[i]["kategorie"] or "",
                               "file": os.path.basename(bel[i]["file"] or ""), "verknuepft": score(i) >= 1, "created": bel[i]["created"] or ""} for i in ids]})
    # ---- eigene Rechnungen / Dokumente ----
    inv = {r["id"]: dict(r) for r in q("SELECT * FROM invoices WHERE status<>'storniert'")}
    items = {}
    for it in q("SELECT invoice_id, name, qty, total FROM items ORDER BY invoice_id, pos"):
        items.setdefault(it["invoice_id"], []).append(f"{_norm(it['name'])}:{round(it['qty'] or 0, 2)}:{round(it['total'] or 0, 2)}")
    uf2, keys2 = _UF(), {}
    for r in inv.values():
        uf2.f(r["id"])
        ck = str(r["customer_id"] or "") or _norm(inv_name(r))
        k = f"{r['typ']}|{ck}|{r['datum']}|{int(round((r['summe'] or 0) * 100))}|{'#'.join(items.get(r['id'], []))}"
        if k in keys2:
            uf2.u(r["id"], keys2[k])
        else:
            keys2[k] = r["id"]
    cl2 = {}
    for i in inv:
        cl2.setdefault(uf2.f(i), []).append(i)
    for root, ids in cl2.items():
        if len(ids) < 2:
            continue
        ids.sort()
        sig = "i:" + ",".join(map(str, ids))
        if sig in ign:
            continue

        def sc(i):
            r = inv[i]
            return (3 if r["locked"] else 0) + (2 if r["status"] == "bezahlt" else 0) + (1 if r["status"] != "entwurf" else 0) + (1 if r.get("versendet_am") else 0)
        keep = sorted(ids, key=lambda i: (-sc(i), i))[0]
        out.append({"sig": sig, "kind": "invoice", "grund": "gleicher Kunde, gleiches Datum, gleiche Positionen und gleicher Betrag", "keep": keep,
                    "items": [{"id": i, "typ": TYP_DE.get(inv[i]["typ"], inv[i]["typ"]), "datum": inv[i]["datum"], "partner": inv_name(inv[i]),
                               "nr": inv[i]["nr"] if inv[i]["status"] != "entwurf" else "Entwurf", "betrag": inv[i]["summe"] or 0,
                               "status": inv[i]["status"], "locked": bool(inv[i]["locked"]), "titel": inv[i]["titel"] or ""} for i in ids]})
    out.sort(key=lambda c: (c["kind"] != "invoice", max(x["datum"] or "" for x in c["items"])), reverse=False)
    return {"ok": True, "gruppen": out, "anzahl": sum(len(c["items"]) - 1 for c in out)}


def dup_ignore(sig):
    ign = json.loads(get_settings().get("dup_ignore") or "[]")
    if sig and sig not in ign:
        ign.append(sig)
    set_setting("dup_ignore", json.dumps(ign))
    return {"ok": True}

# ---------------- v1.6.4: Datei-/Ordnerdialoge starten im Windows-Ordner "Downloads" ----------------
WIN = None            # pywebview window (set in main)
PICKED = set()        # paths returned by the native dialog (only these may be read back)


def downloads_dir():
    """Windows known folder 'Downloads' (FOLDERID_Downloads) - follows a relocated folder, not a fixed path"""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            g = GUID(0x374DE290, 0x123F, 0x4565, (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            p_ = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p_)) == 0:
                path = p_.value
                ctypes.windll.ole32.CoTaskMemFree(p_)
                if path and os.path.isdir(path):
                    return path
        except Exception:
            traceback.print_exc()
    for c in (os.path.join(os.path.expanduser("~"), "Downloads"), os.path.expanduser("~")):
        if os.path.isdir(c):
            return c
    return DATA_DIR


IMG_EXT = ["png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"]


def _accept_types(accept):
    ext = []
    for a in (accept or "").split(","):
        a = a.strip().lower()
        if not a:
            continue
        if a == "image/*":
            ext += IMG_EXT
        elif a.startswith("."):
            ext.append(a[1:])
    ext = [e for e in dict.fromkeys(ext) if re.fullmatch(r"\w+", e)]
    out = []
    if ext:
        out.append("Passende Dateien (" + ";".join("*." + e for e in ext) + ")")
    out.append("Alle Dateien (*.*)")
    return tuple(out)


def native_pick(d):
    """open a native dialog starting in Downloads; returns list of paths, [] on cancel, None if no native dialog available"""
    start = downloads_dir()
    folder = bool(d.get("folder"))
    multiple = bool(d.get("multiple", not folder))
    start_in = d.get("start") or ""
    if start_in and os.path.isdir(start_in) and d.get("prefer_current"):
        start = start_in
    if WIN is not None:
        try:
            import webview
            FD = getattr(webview, "FileDialog", None)
            kind = (FD.FOLDER if FD else webview.FOLDER_DIALOG) if folder else (FD.OPEN if FD else webview.OPEN_DIALOG)
            kw = {"directory": start, "allow_multiple": multiple}
            if not folder:
                kw["file_types"] = _accept_types(d.get("accept"))
            try:
                res = WIN.create_file_dialog(kind, **kw)
            except Exception:
                kw.pop("file_types", None)
                res = WIN.create_file_dialog(kind, **kw)
            if not res:
                return []
            return [res] if isinstance(res, str) else list(res)
        except Exception:
            traceback.print_exc()
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if folder:
            r = filedialog.askdirectory(initialdir=start, parent=root)
            res = [r] if r else []
        else:
            ft = [(t.split(" (")[0], t.split("(")[1].rstrip(")").replace(";", " ")) for t in _accept_types(d.get("accept"))]
            if multiple:
                res = list(filedialog.askopenfilenames(initialdir=start, filetypes=ft, parent=root) or [])
            else:
                r = filedialog.askopenfilename(initialdir=start, filetypes=ft, parent=root)
                res = [r] if r else []
        root.destroy()
        return res
    except Exception:
        traceback.print_exc()
        return None


def api_pick(d):
    res = native_pick(d)
    if res is None:
        return {"ok": False, "native": False}
    res = [os.path.normpath(r) for r in res]
    if not d.get("folder"):
        PICKED.update(res)
    return {"ok": True, "native": True, "paths": res,
            "files": [{"path": r, "name": os.path.basename(r), "size": os.path.getsize(r) if os.path.isfile(r) else 0} for r in res]}

def free_port():
    s_ = socket.socket()
    s_.bind(("127.0.0.1", 0))
    pt = s_.getsockname()[1]
    s_.close()
    return pt


def server_start():
    """v3.7.0: database, background jobs and program server - returns the address of the program page.
    Used by main() (PC) and by the iPhone app (which shows the page in its own WebView)."""
    print(f"INIT {APP_NAME} v{APP_VERSION}  data={DATA_DIR}")
    init_db()
    threading.Thread(target=schedule_loop, daemon=True).start()
    threading.Thread(target=eingang_loop, daemon=True).start()
    start_hooks()
    port = int(os.environ.get("PA_RECHNUNG_PORT") or free_port())
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print("UI:", url)
    return url


def main():
    url = server_start()
    if "--server" in sys.argv:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    try:
        import webview
        global WIN
        WIN = webview.create_window(f"{APP_NAME}  v{APP_VERSION}", url, width=1520, height=960, min_size=(1180, 720))
        webview.start()
    except Exception:
        traceback.print_exc()
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
