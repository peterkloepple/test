# -*- coding: utf-8 -*-
# =============================================================================
#  Pfeiffer-Audio Rechnung - Update-Datei erzeugen  v3.7.0
#  Baut aus dem Projektordner eine .paupdate-Datei (ZIP mit update.json,
#  Programmkern, modules/, ui/, ui.html, assets und build/ mit Starter +
#  requirements fuer den automatischen EXE-Bau (m70)), die im Programm unter
#  Einstellungen > Daten > Programm-Update eingespielt wird.
#  Aufruf: python make_update.py [version] [changelog.txt]
#  Autor: T. Pfeiffer
# =============================================================================
import os, sys, re, ast, json, time, zipfile, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT = "PA-Rechnung-Update"
MIN_LAUNCHER = "1.6.0"


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def find_core(ver=None):
    best, bv = None, (0,)
    for fn in os.listdir(HERE):
        m = re.match(r"PA_Rechnung_v([\d.]+)\.py$", fn)
        if not m:
            continue
        if ver and m.group(1) == ver:
            return os.path.join(HERE, fn), m.group(1)
        if vtuple(m.group(1)) > bv:
            best, bv = (os.path.join(HERE, fn), m.group(1)), vtuple(m.group(1))
    if ver:
        raise SystemExit(f"PA_Rechnung_v{ver}.py nicht gefunden.")
    if not best:
        raise SystemExit("Keine Programmdatei PA_Rechnung_vX.Y.Z.py gefunden.")
    return best


def imports_of(src):
    """required = imported at module level outside try; optional = everything else."""
    tree = ast.parse(src)
    req, opt = set(), set()

    def add(node, bucket):
        if isinstance(node, ast.Import):
            for a in node.names:
                bucket.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            bucket.add(node.module)

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            add(node, req)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            add(node, opt)
    return sorted(req), sorted(opt - req)


def hard_imports(src):
    """all imports that are NOT inside a try block (they must exist, otherwise the module does not load)"""
    tree = ast.parse(src)
    out = set()

    def walk(node, in_try):
        for ch in ast.iter_child_nodes(node):
            t = in_try or isinstance(ch, ast.Try)
            if isinstance(ch, ast.Import) and not in_try:
                out.update(a.name for a in ch.names)
            elif isinstance(ch, ast.ImportFrom) and ch.module and ch.level == 0 and not in_try:
                out.add(ch.module)
            walk(ch, t)
    walk(tree, False)
    return out


def bundle_names():
    """modules the starter packs into the EXE (function _bundle in PA_Rechnung_Start.py)"""
    t = ast.parse(open(os.path.join(HERE, "PA_Rechnung_Start.py"), encoding="utf-8").read())
    names = set()
    for f in t.body:
        if isinstance(f, ast.FunctionDef) and f.name == "_bundle":
            for n in ast.walk(f):
                if isinstance(n, ast.Import):
                    names.update(a.name for a in n.names)
    return names


def check_bundle(sources):
    """v2.5.0: stop if a module imports something the EXE does not contain (v2.5.0 'wave' -> program did not start)"""
    have = bundle_names()
    roots = {n.split(".")[0] for n in have}
    missing = {}
    for name, src in sources:
        for imp in hard_imports(src):
            if imp in have or imp.split(".")[0] in roots:
                continue
            missing.setdefault(imp, []).append(name)
    if missing:
        raise SystemExit("FEHLER: Diese Bausteine sind nicht in der EXE (PA_Rechnung_Start.py, _bundle) - bitte dort eintragen:\n" +
                         "\n".join(f"  {k}  <- {', '.join(sorted(set(v)))}" for k, v in sorted(missing.items())))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ver = sys.argv[1] if len(sys.argv) > 1 and re.fullmatch(r"[\d.]+", sys.argv[1]) else None
    cl_file = next((a for a in sys.argv[1:] if a.lower().endswith(".txt")), None)
    core, ver = find_core(ver)
    src = open(core, encoding="utf-8").read()
    m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', src, re.M)
    if not m or m.group(1) != ver:
        raise SystemExit(f"APP_VERSION in {os.path.basename(core)} passt nicht zum Dateinamen ({m.group(1) if m else '?'}).")
    compile(src, core, "exec")
    mods = []
    REPLACED = {
        "m84_kalender_plus.py": "m84_kalender.py", "m84b_timetree_schreiben.py": "m84_kalender.py", "m84c_kurstermine.py": "m84_kalender.py",
        "m44_steuerbescheid.py": "m44_steuerjahr.py", "m45_jahr.py": "m44_steuerjahr.py", "m46_angleich.py": "m44_steuerjahr.py",
        "m98_gmail_login.py": "m98_mail.py", "m99_mail_privat.py": "m98_mail.py", "m99b_rechnungsabsender.py": "m98_mail.py",
        "m99c_outlook.py": "m98_mail.py", "m30_mail_import.py": "m30_mail_eingang.py", "m31_imap.py": "m30_mail_eingang.py",
        "m44_bescheid.js": "m44_steuerjahr.js", "m45_jahr.js": "m44_steuerjahr.js", "m46_angleich.js": "m44_steuerjahr.js",
        "m98_gmail.js": "m98_mail.js", "m99_privat.js": "m98_mail.js", "m99c_outlook.js": "m98_mail.js",
    }
    for sub, pat in (("modules", r"m\d\d\w*\.py$"), ("ui", r"\w+\.js$")):
        dd = os.path.join(HERE, sub)
        if os.path.isdir(dd):
            for fn in sorted(os.listdir(dd)):
                if re.match(pat, fn):
                    # files merged into a newer module (v3.1.0) never go into an update package
                    if fn in REPLACED and os.path.isfile(os.path.join(dd, REPLACED[fn])):
                        print("  uebersprungen (ersetzt durch " + REPLACED[fn] + "): " + fn)
                        continue
                    b = open(os.path.join(dd, fn), "rb").read()
                    if fn.endswith(".py"):
                        compile(b.decode("utf-8"), fn, "exec")
                    mods.append((sub + "/" + fn, b))
    ui = open(os.path.join(HERE, "ui.html"), encoding="utf-8").read()
    kern = os.path.join(HERE, "ui", "kern_01_basis.js")
    mu = re.search(r'const UI_VERSION = "([^"]+)"', open(kern, encoding="utf-8").read() if os.path.isfile(kern) else ui)
    if mu and mu.group(1) != ver:
        print(f"WARNUNG: UI_VERSION in ui.html ist {mu.group(1)}, Programm ist {ver}.")
    req, opt = imports_of(src)
    for pth, b in mods:
        if pth.endswith(".py"):
            r2, o2 = imports_of(b.decode("utf-8"))
            req = sorted(set(req) | set(r2))
            opt = sorted((set(opt) | set(o2)) - set(req))
    check_bundle([(os.path.basename(core), src)] + [(p_, b_.decode("utf-8")) for p_, b_ in mods if p_.endswith(".py")])
    files = [("PA_Rechnung.py", src.encode("utf-8")), ("ui.html", ui.encode("utf-8"))] + mods
    ad = os.path.join(HERE, "assets")
    if os.path.isdir(ad):
        for fn in sorted(os.listdir(ad)):
            fp = os.path.join(ad, fn)
            if os.path.isfile(fp):
                files.append(("assets/" + fn, open(fp, "rb").read()))
    # v2.1.1: Starter + requirements fuer den automatischen EXE-Bau auf dem PC (m70)
    for fn in ("PA_Rechnung_Start.py", "requirements.txt", "requirements_ocr.txt"):
        fp = os.path.join(HERE, fn)
        if os.path.isfile(fp):
            b = open(fp, "rb").read()
            if fn.endswith(".py"):
                compile(b.decode("utf-8"), fn, "exec")
            files.append(("build/" + fn, b))
        elif fn != "requirements_ocr.txt":
            raise SystemExit(f"{fn} fehlt im Projektordner (wird fuer den EXE-Bau gebraucht).")
    changelog = open(cl_file, encoding="utf-8").read().strip() if cl_file else ""
    if not changelog and os.path.exists(os.path.join(HERE, "changelog.txt")):
        txt = open(os.path.join(HERE, "changelog.txt"), encoding="utf-8").read()
        sec = re.search(r"^v?" + re.escape(ver) + r"\b.*?$(.*?)(?=^v?\d+\.\d+|\Z)", txt, re.M | re.S)
        changelog = (sec.group(1) if sec else "").strip()
    man = {"format": FORMAT, "app": "Pfeiffer-Audio Rechnung", "version": ver, "main": "PA_Rechnung.py",
           "date": time.strftime("%Y-%m-%d %H:%M"), "author": "T. Pfeiffer", "min_launcher": MIN_LAUNCHER,
           "requires": req, "optional": opt, "changelog": changelog,
           "files": [{"path": p, "sha256": sha(b), "size": len(b)} for p, b in files]}
    out_dir = os.path.join(HERE, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"PA_Rechnung_v{ver}.paupdate")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("update.json", json.dumps(man, ensure_ascii=False, indent=1))
        for p, b in files:
            z.writestr("files/" + p, b)
    print(f"INIT make_update v3.7.0")
    print(f"Update-Datei: {out}  ({round(os.path.getsize(out) / 1024)} KB, {len(files)} Dateien)")
    print("Benötigte Bibliotheken:", ", ".join(m_ for m_ in req if "." not in m_ or m_.split(".")[0] in ("reportlab",)))
    return out


if __name__ == "__main__":
    main()
