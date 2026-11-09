# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m22_selbsttest (v2.0.0)
# Selbsttest: laedt einen Programmkern (den laufenden oder ein neues Update)
# in einen FRISCHEN Namensraum mit leerer Test-Datenbank (Beispieldaten aus
# assets/seed.json), rechnet die Kernfunktionen durch und prueft die Summen.
# Beim Einspielen einer .paupdate wird das Update nur aktiv, wenn der
# Selbsttest besteht - sonst bleibt die bisherige Version.
# Autor: T. Pfeiffer

_SELFTEST_LOCK = threading.Lock()


def _base_checks(g):
    """runs inside the fresh namespace g; returns list of error strings"""
    errs = []
    # v2.4.7: a module that cannot load (missing library) must not slip through an update
    for mf in g.get("MODULES_FAILED") or []:
        errs.append(f"Modul {mf['modul']} lässt sich nicht laden – Baustein „{mf['fehlt']}“ fehlt in diesem Programm (EXE neu bauen).")
    q_, euer_, stats_ = g["q"], g["euer"], g["stats"]
    ys = sorted({int(r["y"]) for r in q_("SELECT DISTINCT substr(datum,1,4) y FROM invoices WHERE datum<>''") if r["y"] and r["y"].isdigit()})
    if not ys:
        errs.append("Keine Beispielrechnungen in der Testdatenbank (seed.json).")
        return errs
    for y in ys[-2:]:
        try:
            st = stats_(y)
            direct = round(sum(r["summe"] or 0 for r in q_(f"SELECT summe FROM invoices WHERE substr(datum,1,4)=? AND {g['COUNT_SQL']}", (str(y),))), 2)
            if abs(st["total"] - direct) > 0.01:
                errs.append(f"Statistik {y}: Umsatz {st['total']} statt {direct}")
            if abs(sum(m["umsatz"] for m in st["months"]) - st["total"]) > 0.05:
                errs.append(f"Statistik {y}: Monatssumme passt nicht zum Jahresumsatz")
            if abs(sum(k["summe"] for k in st["kunden"]) - st["total"]) > 0.05:
                errs.append(f"Statistik {y}: Kundensumme passt nicht zum Jahresumsatz")
            e = euer_(y)
            if abs(e["gewinn"] - (e["einnahmen"] - e["ausgaben"])) > 0.01:
                errs.append(f"EUER {y}: Gewinn != Einnahmen - Ausgaben")
            if abs(e["einnahmen"] - e["einnahmen_rechnungen"] - e["einnahmen_sonstige"]) > 0.01:
                errs.append(f"EUER {y}: Einnahmen-Teilsummen passen nicht")
            if abs(sum(e["kategorien"].values()) - e["ausgaben"]) > 0.01:
                errs.append(f"EUER {y}: Ausgaben-Kategorien passen nicht zur Summe")
            t = g["tax_calc"](y)
            if t["calc"]["gesamt"] < 0:
                errs.append(f"Steuer {y}: negative Steuer")
            sd = g["stats_detail"](y)
            s_re = round(sum(r["summe"] for r in sd["rechnungen"] if r["zaehlt"]), 2)
            if abs(s_re - st["total"]) > 0.05:
                errs.append(f"Statistik-Rechnungen {y}: {s_re} statt {st['total']}")
            s_ein = round(sum(r["summe"] for r in sd["einnahmen"]), 2)
            if abs(s_ein - e["einnahmen"]) > 0.05:
                errs.append(f"Statistik-Einnahmen {y}: {s_ein} statt {e['einnahmen']}")
        except Exception as ex:
            errs.append(f"Rechenfehler {y}: {type(ex).__name__}: {ex}")
    try:
        inv = q_("SELECT id FROM invoices WHERE typ='rechnung' ORDER BY id DESC LIMIT 1", one=True)
        if inv:
            pdf = g["render_invoice_pdf"](g["get_invoice"](inv["id"]))
            if not (isinstance(pdf, (bytes, bytearray)) and pdf[:4] == b"%PDF"):
                errs.append("Rechnungs-PDF wird nicht erzeugt")
    except Exception as ex:
        errs.append(f"Rechnungs-PDF: {type(ex).__name__}: {ex}")
    try:
        sheets = g["ex_stats"]({"year": ys[-1]})
        xl = g["export_xlsx"](sheets, "Selbsttest")
        if not xl or xl[:2] != b"PK":
            errs.append("Excel-Export liefert keine Datei")
    except Exception as ex:
        errs.append(f"Excel-Export: {type(ex).__name__}: {ex}")
    try:
        b = g["bootstrap"]()
        if b.get("version") != g["APP_VERSION"]:
            errs.append("Bootstrap meldet falsche Version")
    except Exception as ex:
        errs.append(f"Bootstrap: {type(ex).__name__}: {ex}")
    return errs


def selftest_core(core_path):
    """exec a program core in a fresh namespace with a throw-away data folder"""
    import tempfile
    t0 = time.time()
    res = {"ok": False, "fehler": [], "module": [], "tests": 0, "core": core_path}
    with _SELFTEST_LOCK:
        tmp = tempfile.mkdtemp(prefix="pa_selbsttest_")
        keep = {k: os.environ.get(k) for k in ("PA_RECHNUNG_DATA", "PA_RECHNUNG_NO_OPEN", "PA_RECHNUNG_RES")}
        os.environ["PA_RECHNUNG_DATA"] = tmp
        os.environ["PA_RECHNUNG_NO_OPEN"] = "1"
        os.environ["PA_RECHNUNG_RES"] = os.path.dirname(os.path.abspath(core_path))
        g = {"__name__": "pa_selbsttest", "__file__": os.path.abspath(core_path), "__builtins__": __builtins__}
        try:
            with open(core_path, encoding="utf-8") as f:
                code = compile(f.read(), core_path, "exec")
            exec(code, g)
            res["module"] = list(g.get("MODULES_LOADED") or [])
            g["init_db"]()
            errs = _base_checks(g)
            res["tests"] = 1
            for fn in g.get("HOOK_SELFTEST") or []:
                res["tests"] += 1
                try:
                    e = fn() or []
                    errs += [f"{getattr(fn, '__name__', 'test')}: {x_}" for x_ in e]
                except Exception as ex:
                    errs.append(f"{getattr(fn, '__name__', 'test')}: {type(ex).__name__}: {ex}")
            res["fehler"] = errs
            res["ok"] = not errs
        except SyntaxError as ex:
            res["fehler"] = [f"Programmfehler (Syntax) in {os.path.basename(ex.filename or '')} Zeile {ex.lineno}: {ex.msg}"]
        except Exception as ex:
            tb = traceback.extract_tb(ex.__traceback__)
            where = f" ({os.path.basename(tb[-1].filename)} Zeile {tb[-1].lineno})" if tb else ""
            res["fehler"] = [f"Programm startet nicht: {type(ex).__name__}: {ex}{where}"]
        finally:
            try:
                con = g.get("CON")
                if con is not None:
                    con.close()
            except Exception:
                pass
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(tmp, ignore_errors=True)
    res["dauer_s"] = round(time.time() - t0, 1)
    return res


def run_selftest(print_=False):
    r = selftest_core(os.path.abspath(__file__))
    if print_:
        print("Selbsttest", "OK" if r["ok"] else "FEHLER", f"({r['tests']} Testgruppen, {len(r['module'])} Module, {r['dauer_s']} s)")
        for e in r["fehler"]:
            print("  -", e)
    return r


# install_paupdate: activate only if the new version passes the self test
@chain_step("install_paupdate", "m22_selbsttest")
def _m22_step_install_paupdate(_next, path, allow_same=False):
    ap = os.path.join(APP_DIR, "aktiv.json")
    before = _rj(ap, {}) or {}
    # old versions are cleaned up only after the new one passed the self test
    r = _next(path, allow_same, prune=False)
    ver = r.get("version")
    act = _rj(ap, {}) or {}
    core = os.path.join(APP_DIR, "versionen", ver, act.get("main") or "PA_Rechnung.py")
    st = selftest_core(core)
    r["selbsttest"] = st
    if not st["ok"]:
        bad = set(act.get("defekt") or []) | {ver}
        before["defekt"] = sorted(bad | set(before.get("defekt") or []))
        _wj(ap, before)
        # the failed version is removed again (it must neither push out a working version nor stay selectable)
        if ver and VER_RE.fullmatch(str(ver)) and str(ver) != (before.get("version") or ""):
            shutil.rmtree(os.path.join(APP_DIR, "versionen", ver), ignore_errors=True)
        raise ValueError(f"Update v{ver} hat den Selbsttest NICHT bestanden und wurde nicht aktiviert - "
                         f"deine bisherige Version bleibt. Gefunden: " + " | ".join(st["fehler"][:4]))
    prune_versions(ver, r.get("vorher") or "builtin")
    return r


HOOK_POST["/api/selbsttest"] = lambda h, d: h._send(200, run_selftest())
