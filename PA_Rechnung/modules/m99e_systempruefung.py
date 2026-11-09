# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m99e_systempruefung  v1.0.0 (ab Programm v3.0.0)
# Seite "Systempruefung": prueft am eigenen PC alles, was sich hier nicht vorab testen laesst, und schreibt einen
# PDF-Bericht: Programm/Module, Selbsttest (auf Wegwerf-Daten), Datenbank (Integritaet, Version, Sicherungen),
# Rechnungs-Kette, Texterkennung, Scanner (WIA-Geraete), TimeTree, Mail, Bank, Speicherplatz.
# Der Rundgang durch alle Seiten laeuft in der Oberflaeche (ui/m99e_systempruefung.js) und kommt mit in den Bericht.
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

M99E_VERSION = "1.1.1"
M99E_LAST = {"ergebnis": None}

# v1.1.0 (v3.2.0): time of every server request since program start (path without query) -> "Tempo" in the check
M99E_TEMPO = {}
M99E_TEMPO_LOCK = threading.Lock()


def _m99e_record(h):
    """time from the parsed request line (set in parse_request) - waiting for the client is not counted"""
    t0 = getattr(h, "_m99e_t0", None)
    if t0 is None:
        return
    dt = time.perf_counter() - t0
    pth = (getattr(h, "path", "") or "").split("?")[0]
    if pth.startswith("/api/") and not pth.startswith(("/api/sp/", "/api/m92/")):
        key = re.sub(r"/\d+(?=/|$)", "/<id>", pth)[:80]
        with M99E_TEMPO_LOCK:
            e = M99E_TEMPO.setdefault(key, [0, 0.0, 0.0])
            e[0] += 1
            e[1] += dt
            e[2] = max(e[2], dt)
            if len(M99E_TEMPO) > 400:
                for k_ in sorted(M99E_TEMPO, key=lambda k_: M99E_TEMPO[k_][0])[:100]:
                    M99E_TEMPO.pop(k_, None)


def _m99e_timed(orig):
    def handle_one_request(self):
        self._m99e_t0 = None
        try:
            return orig(self)
        finally:
            _m99e_record(self)
    handle_one_request._m99e = True
    return handle_one_request


def _m99e_parse(orig):
    def parse_request(self):
        r = orig(self)
        self._m99e_t0 = time.perf_counter()
        return r
    parse_request._m99e = True
    return parse_request


if not getattr(Handler.handle_one_request, "_m99e", False):
    Handler.handle_one_request = _m99e_timed(Handler.handle_one_request)
    Handler.parse_request = _m99e_parse(Handler.parse_request)


def m99e_tempo(n=12):
    with M99E_TEMPO_LOCK:
        rows = [(k, v[0], v[1] / max(1, v[0]), v[2]) for k, v in M99E_TEMPO.items()]
    rows.sort(key=lambda r: -r[2])
    return [{"pfad": k, "anzahl": c, "schnitt_ms": round(a * 1000), "max_ms": round(m * 1000)} for k, c, a, m in rows[:n]]

M99E_PS_WIA = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
  $dm = New-Object -ComObject WIA.DeviceManager
  $n = 0
  foreach ($d in $dm.DeviceInfos) {
    if ($d.Type -eq 1) { $n++; Write-Output ('GERAET ' + $d.Properties.Item('Name').Value) }
  }
  Write-Output ('ANZAHL ' + $n)
} catch { Write-Output ('FEHLER ' + $_.Exception.Message) }
"""


def _sp(gruppe, name, status, text=""):
    return {"gruppe": gruppe, "name": name, "status": status, "text": str(text or "")[:600]}


def _m99e_age_days(path):
    try:
        return (time.time() - os.path.getmtime(path)) / 86400
    except OSError:
        return None


def m99e_scanner():
    if not sys.platform.startswith("win"):
        return _sp("Scanner", "Windows-Scan (WIA)", "info", "Nur unter Windows prüfbar.")
    try:
        flags = 0x08000000
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", M99E_PS_WIA],
                           capture_output=True, timeout=40, creationflags=flags)
        out = (r.stdout or b"").decode("utf-8", "replace")
        if "FEHLER" in out:
            return _sp("Scanner", "Windows-Scan (WIA)", "fehler", out.split("FEHLER", 1)[1].strip()[:300])
        names = [l[7:].strip() for l in out.splitlines() if l.startswith("GERAET ")]
        if not names:
            return _sp("Scanner", "Windows-Scan (WIA)", "warn", "Kein Scanner gefunden – eingeschaltet und in Windows eingerichtet?")
        return _sp("Scanner", "Windows-Scan (WIA)", "ok", ", ".join(names))
    except Exception as e:
        return _sp("Scanner", "Windows-Scan (WIA)", "fehler", str(e))


def m99e_run(teile=None):
    t0 = time.time()
    res = []
    s = get_settings()
    teile = set(teile or ["programm", "selbsttest", "datenbank", "kette", "ocr", "scanner", "timetree", "mail", "bank", "sicherung", "tempo"])
    if "programm" in teile:
        res.append(_sp("Programm", "Version", "ok", f"v{APP_VERSION} · Python {sys.version.split()[0]} · {'EXE' if getattr(sys, 'frozen', False) else 'Python-Datei'}"))
        res.append(_sp("Programm", "Module", "fehler" if MODULES_FAILED else "ok",
                       f"{len(MODULES_LOADED)} geladen" + (" · nicht geladen: " + ", ".join(str(m) for m in MODULES_FAILED) if MODULES_FAILED else "")))
        try:
            ui_modules_js()
        except Exception:
            pass
        alt = list(globals().get("MODULES_SKIPPED") or []) + list(globals().get("UI_SKIPPED") or [])
        if alt:
            res.append(_sp("Programm", "Alte Dateien im Programmordner", "warn",
                           f"{len(alt)} alte Dateien aus der Zeit vor v3.1 liegen noch im Programm ({', '.join(alt)}). Sie werden übersprungen. "
                           "Aufräumen: ZIP immer in einen LEEREN Ordner entpacken und die EXE daraus neu bauen – oder die Dateien in den Ordnern modules und ui löschen."))
        try:
            du = shutil.disk_usage(DATA_DIR)
            frei = du.free / 1073741824
            res.append(_sp("Programm", "Speicherplatz Datenordner", "warn" if frei < 2 else "ok", f"{frei:.1f} GB frei · {DATA_DIR}"))
        except Exception as e:
            res.append(_sp("Programm", "Speicherplatz Datenordner", "fehler", e))
    if "selbsttest" in teile:
        try:
            r = run_selftest()
            res.append(_sp("Selbsttest", "Alle Module (Wegwerf-Daten)", "ok" if r["ok"] else "fehler",
                           f"{r['tests']} Testgruppen, {r['dauer_s']} s" + ("" if r["ok"] else " · " + " | ".join(r["fehler"][:12]))))
        except Exception as e:
            res.append(_sp("Selbsttest", "Alle Module", "fehler", e))
    if "datenbank" in teile:
        try:
            with DB_LOCK:
                ic_ = CON.execute("PRAGMA quick_check").fetchone()[0]
            res.append(_sp("Datenbank", "Integrität", "ok" if ic_ == "ok" else "fehler", ic_))
        except Exception as e:
            res.append(_sp("Datenbank", "Integrität", "fehler", e))
        try:
            v = db_version_info()
            st = v["state"]
            txt = f"Programmstand {v['programm']} · Migration {v['migration']} · {v['tabellen']} Tabellen · {v['groesse_mb']} MB"
            res.append(_sp("Datenbank", "Version", "fehler" if st["fehler"] else ("warn" if st["neuere_db"] else "ok"),
                           txt + (" · " + " | ".join(st["fehler"]) if st["fehler"] else "") +
                           (" · Datenbank stammt von einer neueren Programmversion" if st["neuere_db"] else "")))
            vu = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("vor_update_"))
            res.append(_sp("Datenbank", "Sicherung vor Update", "ok" if vu else "info", vu[-1] if vu else "noch keine (entsteht beim nächsten Versionswechsel)"))
        except Exception as e:
            res.append(_sp("Datenbank", "Version", "fehler", e))
        try:
            n = {t: q(f"SELECT COUNT(*) AS n FROM {t}", one=True)["n"] for t in ("invoices", "belege", "customers", "projects")}
            res.append(_sp("Datenbank", "Inhalt", "info", f"{n['invoices']} Dokumente · {n['belege']} Belege · {n['customers']} Kunden · {n['projects']} Projekte"))
        except Exception as e:
            res.append(_sp("Datenbank", "Inhalt", "fehler", e))
    if "kette" in teile:
        try:
            ci = chain_info()
            for k in ("save_invoice", "render_invoice_pdf", "storno_invoice", "x", "get_settings", "set_setting", "kal_events"):
                if k in ci:
                    res.append(_sp("Rechnungs-Kette", k, "info", " → ".join(ci[k])))
            res.append(_sp("Rechnungs-Kette", "Ketten gesamt", "ok", f"{len(ci)} Funktionen mit zusammen {sum(len(v) for v in ci.values())} Stufen"))
        except Exception as e:
            res.append(_sp("Rechnungs-Kette", "Ketten", "fehler", e))
    if "ocr" in teile:
        try:
            r = ocr_test()
            res.append(_sp("Texterkennung", "Windows-OCR", "ok" if r.get("ok") else ("info" if not r.get("windows") else "fehler"),
                           (f"Weg: {r.get('weg')}" if r.get("ok") else r.get("fehler") or "") + ("" if r.get("winrt") else " · Python-Paket winrt fehlt (PowerShell-Weg)")))
        except Exception as e:
            res.append(_sp("Texterkennung", "Windows-OCR", "fehler", e))
    if "scanner" in teile:
        res.append(m99e_scanner())
    if "timetree" in teile:
        try:
            if not (s.get("tt_email") or "").strip():
                res.append(_sp("TimeTree", "Zugang", "info", "Nicht eingerichtet."))
            else:
                cals = q("SELECT COUNT(*) AS n, MAX(abgerufen) AS a FROM kal_cal WHERE quelle='timetree'", one=True) if q(
                    "SELECT 1 FROM sqlite_master WHERE name='kal_cal'", one=True) else {"n": 0, "a": ""}
                res.append(_sp("TimeTree", "Kalender", "ok" if cals["n"] else "warn",
                               f"{cals['n']} Kalender · zuletzt abgerufen {cals['a'] or 'nie'}"))
                if q("SELECT 1 FROM sqlite_master WHERE name='m84_termin'", one=True):
                    bad = q("SELECT tt_status, COUNT(*) AS n FROM m84_termin WHERE tt_status IN ('fehler','pruefen','wartet') GROUP BY tt_status")
                    ok_ = q("SELECT COUNT(*) AS n FROM m84_termin WHERE tt_status='ok'", one=True)["n"]
                    txt = f"{ok_} Termine in TimeTree" + ("".join(f" · {r['n']}× {r['tt_status']}" for r in bad))
                    diag = (s.get("m48_diag") or [])[-1:] or [{}]
                    if bad and diag[0]:
                        txt += f" · letzter Aufruf: {diag[0].get('aufruf', '')} HTTP {diag[0].get('http', '')}"
                    res.append(_sp("TimeTree", "Termine übertragen", "warn" if bad else "ok", txt))
        except Exception as e:
            res.append(_sp("TimeTree", "Prüfung", "fehler", e))
    if "mail" in teile:
        smtp = bool((s.get("smtp_host") or s.get("smtp_user") or "").strip())
        res.append(_sp("Mail", "Versand (SMTP / Outlook)", "ok" if smtp or s.get("m99c_aktiv") else "info",
                       "eingerichtet" if smtp else ("Outlook" if s.get("m99c_aktiv") else "nicht eingerichtet")))
        try:
            last = q("SELECT MAX(datum) AS d, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS f FROM mail_log", one=True)
            res.append(_sp("Mail", "Letzter Versand", "warn" if (last["f"] or 0) else "info", f"{last['d'] or 'nie'}" + (f" · {last['f']} fehlgeschlagen" if last["f"] else "")))
        except Exception:
            pass
    if "bank" in teile:
        try:
            r = q("SELECT MAX(datum) AS d, COUNT(*) AS n FROM bank_tx", one=True)
            alt = None
            if r["d"]:
                alt = (datetime.date.today() - datetime.date.fromisoformat(r["d"][:10])).days
            res.append(_sp("Bank", "Umsätze", "warn" if alt is not None and alt > 30 else "info",
                           f"{r['n']} Umsätze · neuester vom {de_date(r['d']) if r['d'] else '–'}" + (f" ({alt} Tage alt)" if alt is not None else "")))
        except Exception as e:
            res.append(_sp("Bank", "Umsätze", "fehler", e))
    if "tempo" in teile:
        tp = m99e_tempo(8)
        if tp:
            slow = [r_ for r_ in tp if r_["schnitt_ms"] > 1500]
            res.append(_sp("Tempo", "Langsamste Server-Abfragen", "warn" if slow else "ok",
                           " · ".join(f"{r_['pfad']} {r_['schnitt_ms']} ms (max {r_['max_ms']}, {r_['anzahl']}×)" for r_ in tp[:6])))
        else:
            res.append(_sp("Tempo", "Langsamste Server-Abfragen", "info", "Noch keine Messwerte (erst nach etwas Benutzung)."))
    if "sicherung" in teile:
        try:
            fs = sorted((os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")), key=os.path.getmtime)
            if not fs:
                res.append(_sp("Sicherung", "Letzte Sicherung", "warn", "Noch keine Sicherung vorhanden."))
            else:
                a = _m99e_age_days(fs[-1]) or 0
                res.append(_sp("Sicherung", "Letzte Sicherung", "warn" if a > 7 else "ok", f"{os.path.basename(fs[-1])} · vor {a:.1f} Tagen"))
        except Exception as e:
            res.append(_sp("Sicherung", "Letzte Sicherung", "fehler", e))
    out = {"ok": True, "zeit": now_iso(), "dauer_s": round(time.time() - t0, 1), "punkte": res,
           "fehler": sum(1 for r in res if r["status"] == "fehler"), "warn": sum(1 for r in res if r["status"] == "warn")}
    M99E_LAST["ergebnis"] = out
    return out


def m99e_pdf(d):
    """report PDF from the result (+ UI tour) -> Downloads folder"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rc
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    r = d.get("ergebnis") or M99E_LAST["ergebnis"] or m99e_run()
    rund = d.get("rundgang") or []
    fn_r, fn_b = FONT_R(), FONT_B()
    st = {"h1": ParagraphStyle("h1", fontName=fn_b, fontSize=16, leading=20, textColor=rc.HexColor("#3C4860")),
          "n": ParagraphStyle("n", fontName=fn_r, fontSize=8.5, leading=11),
          "b": ParagraphStyle("b", fontName=fn_b, fontSize=8.5, leading=11)}
    col = {"ok": rc.HexColor("#2e9e5b"), "warn": rc.HexColor("#d98a00"), "fehler": rc.HexColor("#c0392b"), "info": rc.HexColor("#6b7280")}
    lbl = {"ok": "OK", "warn": "Hinweis", "fehler": "FEHLER", "info": "Info"}
    E = lambda t_: str(t_).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    story = [Paragraph("Systemprüfung – Pfeiffer-Audio Rechnung", st["h1"]), Spacer(1, 4),
             Paragraph(f"v{APP_VERSION} · {de_date(today())} · {r['fehler']} Fehler · {r['warn']} Hinweise · Dauer {r['dauer_s']} s", st["n"]), Spacer(1, 8)]
    rows = [[Paragraph("Bereich", st["b"]), Paragraph("Prüfung", st["b"]), Paragraph("Ergebnis", st["b"]), Paragraph("Details", st["b"])]]
    styles = [("GRID", (0, 0), (-1, -1), 0.3, rc.HexColor("#d0d5dd")), ("BACKGROUND", (0, 0), (-1, 0), rc.HexColor("#E8ECF3")),
              ("VALIGN", (0, 0), (-1, -1), "TOP")]
    allp = list(r["punkte"])
    if rund:
        fe = [x_ for x_ in rund if x_.get("fehler")]
        allp.append(_sp("Rundgang", "Alle Seiten der Oberfläche", "fehler" if fe else "ok",
                        f"{len(rund)} Seiten" + ("" if not fe else " · " + " | ".join(f"{x_['seite']}: {x_['fehler']}" for x_ in fe[:20]))))
        ms = sorted((x_ for x_ in rund if x_.get("ms")), key=lambda x_: -x_["ms"])[:6]
        if ms:
            allp.append(_sp("Tempo", "Langsamste Seiten", "warn" if ms[0]["ms"] > 3000 else "ok",
                            " · ".join(f"{x_['seite']} {x_['ms']} ms" for x_ in ms)))
    for i, p_ in enumerate(allp, 1):
        rows.append([Paragraph(E(p_["gruppe"]), st["n"]), Paragraph(E(p_["name"]), st["n"]),
                     Paragraph(f'<font color="{col[p_["status"]].hexval().replace("0x", "#")}"><b>{lbl[p_["status"]]}</b></font>', st["n"]),
                     Paragraph(E(p_["text"]), st["n"])])
    tb = Table(rows, colWidths=[28 * mm, 40 * mm, 18 * mm, 94 * mm], repeatRows=1)
    tb.setStyle(TableStyle(styles))
    story.append(tb)
    story += [Spacer(1, 10), Paragraph("Bei Fehlern diesen Bericht an T. Pfeiffer schicken. Der Bericht enthält keine Passwörter.", st["n"])]
    out_dir = downloads_dir() if "downloads_dir" in globals() else DATA_DIR
    os.makedirs(out_dir, exist_ok=True)
    fp = os.path.join(out_dir, f"Systempruefung_v{APP_VERSION}_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M')}.pdf")
    doc = SimpleDocTemplate(fp, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
                            title="Systemprüfung", author="T. Pfeiffer")
    doc.build(story)
    if d.get("open", True):
        try:
            open_path(fp)
        except Exception:
            pass
    return {"ok": True, "path": fp}


HOOK_POST["/api/sp/run"] = lambda h, d: h._send(200, m99e_run(d.get("teile")))
HOOK_POST["/api/sp/pdf"] = lambda h, d: h._send(200, m99e_pdf(d))


def m99e_selftest():
    err = []
    try:
        r = m99e_run(["programm", "datenbank", "kette", "bank", "sicherung", "mail", "timetree"])
        if not r["punkte"] or any(p_["status"] == "fehler" and p_["gruppe"] == "Rechnungs-Kette" for p_ in r["punkte"]):
            err.append("m99e: Systemprüfung liefert nichts / Kette fehlerhaft")
        fp = m99e_pdf({"ergebnis": r, "rundgang": [{"seite": "dash", "fehler": ""}], "open": False})["path"]
        if not os.path.isfile(fp) or os.path.getsize(fp) < 1000:
            err.append("m99e: Bericht-PDF fehlt")
        else:
            os.remove(fp)
    except Exception as e:
        err.append(f"m99e Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(m99e_selftest)
print(f"INIT m99e_systempruefung v{M99E_VERSION}")
