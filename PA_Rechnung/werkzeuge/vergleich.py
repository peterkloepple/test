# Pfeiffer-Audio Rechnung - Werkzeug: Vorher/Nachher-Vergleich (Golden Master) v1.0.0
# Autor: T. Pfeiffer
# same scenario against a program version -> normalized snapshot (JSON) for before/after comparison
# usage: python3 gm.py <core.py> <out.json> [port]
import sys, os, json, time, subprocess, shutil, tempfile, re, io, sqlite3, urllib.request, http.cookiejar

core, out = sys.argv[1], sys.argv[2]
port = int(sys.argv[3]) if len(sys.argv) > 3 else 8790
data = tempfile.mkdtemp(prefix="gm_")
env = dict(os.environ, PA_RECHNUNG_DATA=data, PA_RECHNUNG_PORT=str(port))
srv = subprocess.Popen([sys.executable, core, "--server"], env=env, stdout=open(os.path.join(data, "_srv.log"), "w"), stderr=subprocess.STDOUT)
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
B = f"http://127.0.0.1:{port}"
LOG = []


def req(method, path, body=None, raw=False):
    r = urllib.request.Request(B + path, method=method, data=None if body is None else json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    try:
        with op.open(r, timeout=120) as f:
            b = f.read()
            return b if raw else json.loads(b or b"{}")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return json.loads(b)
        except Exception:
            return {"_http": e.code, "_body": b[:300].decode("utf-8", "replace")}


def post(p, d):
    r = req("POST", p, d)
    LOG.append([p, _norm(r)])
    return r


def get(p):
    return req("GET", p)


def pdftext(b):
    try:
        import pypdf
        rd = pypdf.PdfReader(io.BytesIO(b))
        return "\n".join((pg.extract_text() or "") for pg in rd.pages)
    except Exception as e:
        return f"PDF-FEHLER {e} {b[:80]!r}"


RND = re.compile(r"\bE-[0-9A-F]{6}\b")
TS = re.compile(r"\b20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\b|\b20\d\d-\d\d-\d\d \d\d:\d\d(:\d\d)?\b")


def _norm(o):
    if isinstance(o, dict):
        return {k: ("<TS>" if k in ("created", "updated", "ts", "zeit", "geaendert", "kurs_datum", "hash", "salt", "gesetzt", "token", "prev") and o[k] else _norm(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_norm(v) for v in o]
    if isinstance(o, str):
        return RND.sub("E-<RND>", TS.sub("<TS>", o.replace(data, "<DATA>")))
    return o


for _ in range(80):
    try:
        urllib.request.urlopen(B + "/", timeout=1)
        break
    except Exception:
        time.sleep(0.25)
post("/api/m92/setup", {"pin": "135790", "pin2": "135790"})
post("/api/m92/unlock", {"pin": "135790"})
post("/api/settings/save", {"firma": "T. Pfeiffer Test", "name": "T. Pfeiffer", "strasse": "Teststr. 1", "plz": "51103", "ort": "Köln",
                            "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank": "Testbank", "email": "t@example.org"})

c1 = post("/api/customer/save", {"firma": "Muster AV GmbH", "strasse": "Hauptstr. 5", "plz": "50667", "ort": "Köln", "email": "a@b.de"})
c2 = post("/api/customer/save", {"firma": "Sample Events Ltd", "strasse": "1 High St", "plz": "SW1", "ort": "London", "land": "GB", "email": "x@y.uk"})
cid1 = c1.get("id")
cid2 = c2.get("id")
IT = [{"qty": 2, "name": "Q-SYS Programmierung", "descr": "Tagessatz", "price": 850, "rabatt": 0, "unit": "Tag"},
      {"qty": 1, "name": "Mikrofon-Kabel", "price": 19.9, "rabatt": 10, "unit": "Stk"},
      {"qty": 3.5, "name": "Anfahrt", "price": 0.42, "rabatt": 0, "unit": "km"}]
ids = {}


def inv(key, **kw):
    d = {"typ": "rechnung", "customer_id": cid1, "datum": "2026-03-10", "liefer": "2026-03-09", "frist": 14, "items": [dict(i) for i in IT],
         "addr": ["Muster AV GmbH", "Hauptstr. 5", "50667 Köln"], "titel": "Rechnung", "toptext": "Vielen Dank für Ihren Auftrag.",
         "foottext": "Zahlbar bis [Zahlungsfrist]. [Skonto]"}
    d.update(kw)
    r = post("/api/invoice/save", d)
    ids[key] = r.get("id")
    return r.get("id")


# KU invoices
a = inv("ku1")
b = inv("ku2", datum="2026-04-02", skonto_pct=2, skonto_tage=7, font=None)
post("/api/invoice/status", {"id": a, "status": "bezahlt", "bezahlt_am": "2026-03-20"})
post("/api/m71/book", {"invoice_id": b, "datum": "2026-04-05", "betrag": 500, "notiz": "Teilzahlung"})
post("/api/invoice/storno", {"id": b})
ang = inv("ang", typ="angebot", datum="2026-04-10", titel="Angebot")
conv = post("/api/invoice/convert", {"id": ang, "to": "rechnung"})
ids["conv"] = conv.get("id")
dr = inv("draft", status="entwurf", datum="2026-04-12")
fin = post("/api/invoice/save", dict(get(f"/api/invoice?id={dr}"), finalize=True))
ids["fin"] = fin.get("id")
# English / foreign currency (rate fixed)
e1 = inv("intl", customer_id=cid2, datum="2026-05-03", addr=["Sample Events Ltd", "1 High St", "London"],
         m82={"sprache": "en", "waehrung": "GBP", "kurs": 0.85, "kurs_datum": "2026-05-03", "kurs_quelle": "fest"})
e2 = inv("intl_eur", customer_id=cid2, datum="2026-05-04", m82={"sprache": "en", "waehrung": "EUR"})
# reminder
post("/api/mahnung/create", {"id": ids["conv"], "stufe": 1})
# switch to standard taxation from 2026-07-01
post("/api/m80/cfg", {"ab": "2026-07-01", "versteuerung": "ist", "zeitraum": "quartal", "satz": 19})
r1 = inv("regel19", datum="2026-07-15")
it7 = [dict(i) for i in IT]
it7[1]["ust_satz"] = 7
r2 = inv("regel7", datum="2026-08-01", items=it7)
post("/api/invoice/status", {"id": r1, "status": "bezahlt", "bezahlt_am": "2026-07-30"})
post("/api/m71/book", {"invoice_id": r2, "datum": "2026-08-10", "betrag": 100})
post("/api/invoice/storno", {"id": r2})
r3 = inv("regel_intl", customer_id=cid2, datum="2026-09-01", m82={"sprache": "en", "waehrung": "EUR"})
post("/api/invoice/export", {"id": r3, "open": False})
# changes on an unlocked document (GoBD log)
cur = get(f"/api/invoice?id={ids['fin']}")
cur["titel"] = "Rechnung geändert"
cur["items"][0]["qty"] = 3
post("/api/invoice/save", cur)

snap = {"log": LOG, "invoices": {}, "pdf": {}, "api": {}, "db": {}}
for k, iid in ids.items():
    if not iid:
        continue
    snap["invoices"][k] = _norm(get(f"/api/invoice?id={iid}"))
    snap["pdf"][k] = _norm(pdftext(req("GET", f"/api/invoice/pdf?id={iid}", raw=True)))
for p in ("/api/stats?year=2026", "/api/tax?year=2026", "/api/stats/detail?year=2026", "/api/m80/ustva?year=2026", "/api/m71/overview",
          "/api/m82/list", "/api/report/year?year=2026"):
    snap["api"][p] = _norm(req("GET", p))
b_ = get("/api/bootstrap")
snap["api"]["bootstrap.invoices"] = _norm(b_.get("invoices"))
srv.terminate()
srv.wait(10)
con = sqlite3.connect(os.path.join(data, "daten.sqlite"))
con.row_factory = sqlite3.Row
for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    if t in ("settings",) or t.startswith("sqlite_"):
        continue
    try:
        rows = [dict(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")]
    except Exception as e:
        rows = [str(e)]
    snap["db"][t] = _norm(rows)
json.dump(snap, open(out, "w"), ensure_ascii=False, indent=1, sort_keys=True, default=str)
if len(sys.argv) > 4:
    shutil.rmtree(sys.argv[4], ignore_errors=True)
    shutil.copytree(data, sys.argv[4])
shutil.rmtree(data, ignore_errors=True)
print("OK", out, len(ids), "Dokumente", sum(len(v) for v in snap["db"].values()), "DB-Zeilen")
