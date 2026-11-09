# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m01_grundlagen
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# Optional libraries
# ----------------------------------------------------------------------------
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import simpleSplit, ImageReader
from reportlab.lib import colors
# reportlab loads its barcode modules dynamically - import them explicitly
# so PyInstaller bundles them (fix v1.0.1: No module named ...code128)
import importlib as _il
for _m in ("code128", "code39", "code93", "common", "usps", "usps4s", "eanbc", "ecc200datamatrix",
           "fourstate", "lto", "qr", "qrencoder", "widgets", "dmtx"):
    try:
        _il.import_module("reportlab.graphics.barcode." + _m)
    except Exception:
        pass
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

try:
    import pypdf
except Exception:
    pypdf = None
try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None
# v3.6.1: pdfium is NOT thread safe - two pages rendered at the same time (thumbnails, page view, OCR, print)
# crashed the whole program (segfault). Every use of pdfium runs under this lock.
PDFIUM_LOCK = threading.RLock()

DB_LOCK = threading.RLock()

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    # v2.4.2: no personal data in the program code any more - own values live only in the data folder
    # (m97 copies the old built-in values into the settings once, see m97_sicherheit.py)
    "firma": "",
    "inhaber": "",
    "absender": "",
    "logo": "logo.jpg",
    "bank": "",
    "iban": "",
    "bic": "",
    "kontoinhaber": "",
    "paypal_mail": "",
    "paypal_me": "",
    "fuss1": "",
    "fuss2": "",
    "fuss3": "",
    "fuss4": "",
    "next_nr": "2026-001",
    "next_kdnr": "KD-1001",
    "next_projnr": "P2026-001",
    "frist": 7,
    "zahlart": "Ueberweisung",
    "pdf_dir": os.path.join(DATA_DIR, "Rechnungen"),
    "pdf_pattern": "rechnung_{nr}.pdf",
    "highlight": "#fbe3e3",
    "default_top": "Vielen Dank für Ihren Auftrag! Bitte zahlen Sie den Betrag binnen [Frist] Tagen ab Rechnungsdatum.",
    "default_foot": "Kein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
    "kleinunternehmer": True,
    "theme": "light",
    "next_angnr": "A2026-001",
    "next_abnr": "AB2026-001",
    "angebot_gueltig": 30,
    "default_top_angebot": "Vielen Dank für Ihre Anfrage. Gerne bieten wir Ihnen folgende Leistungen an:",
    "default_foot_angebot": "Dieses Angebot ist gültig bis [Gueltig]. Kein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
    "default_top_auftrag": "Vielen Dank für Ihren Auftrag. Hiermit bestätigen wir folgende Leistungen:",
    "default_foot_auftrag": "Kein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
    "mahn_gebuehr": [0.0, 5.0, 10.0, 15.0],
    "mahn_frist": 7,
    "mahn_text": [
        "sicher ist es Ihrer Aufmerksamkeit entgangen: Für die folgende Rechnung konnten wir noch keinen Zahlungseingang feststellen. Bitte überweisen Sie den offenen Betrag bis zum [Mahnfrist].",
        "leider konnten wir trotz unserer Zahlungserinnerung noch keinen Zahlungseingang feststellen. Bitte überweisen Sie den offenen Betrag zuzüglich Mahngebühr bis zum [Mahnfrist].",
        "trotz Erinnerung und erster Mahnung ist die folgende Rechnung weiterhin offen. Bitte begleichen Sie den Gesamtbetrag umgehend, spätestens bis zum [Mahnfrist].",
        "dies ist unsere letzte Mahnung. Sollte der Gesamtbetrag nicht bis zum [Mahnfrist] eingehen, werden wir ohne weitere Ankündigung rechtliche Schritte einleiten."],
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_pass": "",
    "smtp_from": "",
    "mail_bcc_self": True,
    "mail_subject": "[Dokument] [Nummer] - [Firma]",
    "mail_body": "Guten Tag,\n\nanbei erhalten Sie [Dokument] [Nummer] über [Betrag].\n\nMit freundlichen Grüßen\n[Inhaber]\n[Firma]",
    "stundensatz": 60.0,
    "timer": None,
    "km_dienst": 0.30,
    "backup_target": "",
    "materialpreise": {"S235": 1.60, "S355": 1.90, "Edelstahl 1.4301": 5.50, "Aluminium": 6.00},
    "aufschlag": 20.0,
    "ki_enabled": False,
    "ki_url": "http://127.0.0.1:11434",
    "ki_model": "",
    "ki_immer": False,
    "ki_timeout": 45,
    "auto_eingang": False,
    "eingang_dir": "",
    "auto_schwelle": 0.9,
    "beleg_pw": [],
    "std_pw": "",
}

PROJECT_TEMPLATES = [
    {"name": "AV-Projekt", "bereich": "AV", "folders": [
        "01 Angebot & Planung", "02 Blockschaltbilder", "03 Zeichnungen & Pläne",
        "04 Programmierung/Q-SYS", "04 Programmierung/Crestron", "04 Programmierung/Extron",
        "05 Doku & Handbücher", "06 Fotos", "07 Rechnungen & Belege"]},
    {"name": "Metallbau / Schlosserei", "bereich": "Metallbau", "folders": [
        "01 Angebot & Aufmaß", "02 Zeichnungen/Inventor", "02 Zeichnungen/DXF & DWG",
        "03 Stücklisten & Material", "04 Schweißdokumentation/WPS & WPQR",
        "04 Schweißdokumentation/Prüfberichte", "05 Fotos", "06 Rechnungen & Belege"]},
    {"name": "Schweißen", "bereich": "Schweißen", "folders": [
        "01 Auftrag", "02 Zeichnungen", "03 WPS & WPQR", "04 Werkstoffzeugnisse",
        "05 Prüfberichte (VT, PT, MT)", "06 Fotos", "07 Rechnungen & Belege"]},
    {"name": "Audio / Studio", "bereich": "Audio", "folders": [
        "01 Auftrag", "02 Session-Dateien", "03 Mixdowns & Master", "04 Fotos", "05 Rechnungen & Belege"]},
    {"name": "Unterricht / DJ", "bereich": "Unterricht", "folders": [
        "01 Teilnehmer", "02 Material", "03 Abrechnungen"]},
    {"name": "Leer", "bereich": "Sonstiges", "folders": ["01 Allgemein"]},
]

# file kind detection -> (kind, preferred folder keywords)
KIND_RULES = [
    ("Schweißdokument", ("wps", "wpqr", "schweiss", "schweiß", "pqr", "prüfbericht", "pruefbericht", "zeugnis", "3.1"), None),
    ("Blockschaltbild", ("block", "schaltbild", "signalfluss", "signal", "schematic", "riser", "verkabelung"), (".vsd", ".vsdx", ".drawio")),
    ("CAD-Zeichnung", (), (".dwg", ".dxf", ".ipt", ".iam", ".idw", ".ipn", ".step", ".stp", ".igs", ".iges", ".sat", ".stl", ".dwf", ".dft", ".sldprt", ".sldasm")),
    ("Q-SYS / AV-Programm", (), (".qsys", ".qsc", ".lua", ".smw", ".usp", ".ush", ".umc", ".vtz", ".lpz", ".cpz", ".gcpj", ".gcp", ".exe")),
    ("Foto", (), (".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".bmp", ".tif", ".tiff")),
    ("Stückliste", ("stückliste", "stueckliste", "bom", "material", "teileliste"), (".xlsx", ".xls", ".csv")),
    ("Zeichnung", ("zeichnung", "plan", "grundriss", "ansicht", "schnitt", "drawing"), (".pdf", ".svg")),
    ("Dokument", (), (".pdf", ".docx", ".doc", ".txt", ".odt", ".xlsx", ".pptx", ".md")),
    ("Audio", (), (".wav", ".aif", ".aiff", ".mp3", ".flac", ".als", ".npr", ".ptx", ".cpr")),
]
KIND_FOLDER_HINTS = {
    "Schweißdokument": ("schweiß", "wps", "prüf"),
    "Blockschaltbild": ("block",),
    "CAD-Zeichnung": ("inventor", "dxf", "zeichnung"),
    "Q-SYS / AV-Programm": ("q-sys", "programm", "crestron"),
    "Foto": ("foto",),
    "Stückliste": ("stück", "material"),
    "Zeichnung": ("zeichnung", "plän", "plan"),
    "Dokument": ("doku", "auftrag", "angebot", "allgemein"),
    "Audio": ("session", "mix", "master"),
}

EUER_KATEGORIEN = [
    "Waren / Material", "Fremdleistungen", "Arbeitsmittel / Equipment (GWG)", "Arbeitsmittel (Kleinmaterial)",
    "Software / Lizenzen", "Telekommunikation / Internet", "Fahrtkosten / Reise", "Übernachtung / Reisenebenkosten",
    "Raumkosten / Miete", "Miete / Leasing Geräte", "Werbung / Marketing", "Fortbildung / Fachliteratur", "Rechts- und Steuerberatung",
    "Bürobedarf / Porto", "Versicherungen / Beiträge", "Bankgebühren", "Bewirtung (70%)",
    "Abschreibung (AfA)", "Sonstige Betriebsausgaben",
]
# Anlage EUER 2025: (Zeile, Kennzahl, Bezeichnung)
EUER_FORM = {
    "_einnahmen_ku": (12, 111, "Betriebseinnahmen als umsatzsteuerlicher Kleinunternehmer"),
    "Waren / Material": (27, 100, "Waren, Rohstoffe und Hilfsstoffe"),
    "Fremdleistungen": (29, 110, "Bezogene Fremdleistungen"),
    "Abschreibung (AfA)": (33, 130, "AfA auf bewegliche Wirtschaftsgüter"),
    "Arbeitsmittel / Equipment (GWG)": (36, 132, "Aufwendungen für geringwertige Wirtschaftsgüter"),
    "Raumkosten / Miete": (39, 150, "Miete/Pacht für Geschäftsräume"),
    "Telekommunikation / Internet": (43, 280, "Aufwendungen für Telekommunikation"),
    "Übernachtung / Reisenebenkosten": (44, 221, "Übernachtungs- und Reisenebenkosten"),
    "Fortbildung / Fachliteratur": (45, 281, "Fortbildungskosten"),
    "Rechts- und Steuerberatung": (46, 194, "Rechts- und Steuerberatung, Buchführung"),
    "Versicherungen / Beiträge": (49, 223, "Beiträge, Gebühren, Abgaben und Versicherungen"),
    "Software / Lizenzen": (50, 228, "Laufende EDV-Kosten"),
    "Arbeitsmittel (Kleinmaterial)": (51, 229, "Arbeitsmittel"),
    "Werbung / Marketing": (54, 224, "Werbekosten"),
    "Bürobedarf / Porto": (60, 183, "Übrige unbeschränkt abziehbare Betriebsausgaben"),
    "Bankgebühren": (60, 183, "Übrige unbeschränkt abziehbare Betriebsausgaben"),
    "Miete / Leasing Geräte": (60, 183, "Übrige unbeschränkt abziehbare Betriebsausgaben"),
    "Sonstige Betriebsausgaben": (60, 183, "Übrige unbeschränkt abziehbare Betriebsausgaben"),
    "Bewirtung (70%)": (63, 165, "Bewirtungsaufwendungen (abziehbarer Teil)"),
    "_homeoffice": (66, 163, "Tagespauschale (Homeoffice)"),
    "Fahrtkosten / Reise": (70, 146, "Sonstige tatsächliche Fahrtkosten / Fahrten mit Privat-Pkw"),
    "_fahrten": (70, 146, "Sonstige tatsächliche Fahrtkosten / Fahrten mit Privat-Pkw"),
    "Fahrten Privat-Pkw (km-Pauschale)": (70, 146, "Sonstige tatsächliche Fahrtkosten / Fahrten mit Privat-Pkw"),
    "Homeoffice-Tagespauschale": (66, 163, "Tagespauschale (Homeoffice)"),
    "_summe": (75, 199, "Summe Betriebsausgaben"),
}
DOC_TYPES = {
    "rechnung": {"title": "Rechnung", "nrlabel": "Rechnung Nr.", "series": "next_nr", "file": "rechnung_{nr}.pdf"},
    "storno": {"title": "Storno-Rechnung", "nrlabel": "Rechnung Nr.", "series": "next_nr", "file": "storno_{nr}.pdf"},
    "angebot": {"title": "Angebot", "nrlabel": "Angebot Nr.", "series": "next_angnr", "file": "angebot_{nr}.pdf"},
    "auftrag": {"title": "Auftragsbestätigung", "nrlabel": "Auftrag Nr.", "series": "next_abnr", "file": "auftrag_{nr}.pdf"},
}
COUNT_SQL = "typ IN ('rechnung','storno') AND status NOT IN ('storniert','entwurf')"

VENDOR_CATEGORY = [
    (("grover",), "Miete / Leasing Geräte"),
    (("vodafone", "telekom deutschland"), "Telekommunikation / Internet"),
    (("thomann", "music store", "justmusic", "session music", "musikhaus", "kirstein"), "Arbeitsmittel / Equipment (GWG)"),
    (("telekom", "vodafone", "o2 ", "1&1", "congstar", "netcologne", "unitymedia"), "Telekommunikation / Internet"),
    (("adobe", "steinberg", "ableton", "avid", "native instruments", "waves", "izotope", "plugin", "microsoft", "autodesk", "q-sys", "qsc", "crestron", "lizenz", "abo"), "Software / Lizenzen"),
    (("deutsche bahn", "db fernverkehr", "aral", "shell", "esso", "total", "jet ", "tankstelle", "kvb", "vrs", "flixbus", "parken", "parkhaus"), "Fahrtkosten / Reise"),
    (("google ads", "meta platforms", "facebook", "flyeralarm", "vistaprint", "werbung"), "Werbung / Marketing"),
    (("udemy", "sae", "seminar", "schulung", "fortbildung", "buch", "thalia"), "Fortbildung / Fachliteratur"),
    (("dhl", "deutsche post", "hermes", "porto", "büro", "staples"), "Bürobedarf / Porto"),
    (("würth", "wuerth", "hornbach", "obi", "bauhaus", "hagebau", "stahl", "schweiss", "schweiß", "linde", "air liquide", "messer", "esab", "fronius", "lorch", "kemppi", "metall"), "Waren / Material"),
    (("amazon",), "Arbeitsmittel / Equipment (GWG)"),
    (("versicherung", "haftpflicht", "gema", "berufsgenossenschaft", "ihk", "hwk", "handwerkskammer"), "Versicherungen / Beiträge"),
    (("restaurant", "bewirtung", "gaststätte", "cafe"), "Bewirtung (70%)"),
]

# Income tax tables (par. 32a EStG): gfb, z2end, a2, z3end, a3, c3, c4, c5, soli_fg
TARIF = {
    2023: (10908, 15999, 979.18, 62809, 192.59, 966.53, 9972.98, 18307.73, 17543),   # v2.6.3 (was computed with 2024 values)
    2024: (11784, 17005, 954.80, 66760, 181.19, 991.21, 10636.31, 18971.06, 18130),
    2025: (12096, 17443, 932.30, 68480, 176.64, 1015.13, 10911.92, 19246.67, 19950),
    2026: (12348, 17799, 914.51, 69878, 173.10, 1034.87, 11135.63, 19470.38, 20350),
}

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.date.today().isoformat()


def de_date(iso):
    if not iso:
        return ""
    try:
        y, m, d = iso[:10].split("-")
        return f"{d}.{m}.{y}"
    except Exception:
        return iso


def iso_from_de(s):
    m = re.match(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})", s or "")
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, mo, d).isoformat()
    except Exception:
        return ""


def money(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s + " EUR"


def num_de(v, dec=2):
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def parse_amount(s):
    if isinstance(s, (int, float)) and not isinstance(s, bool):    # v2.6.3: None / numbers no longer crash
        return float(s)
    s = str(s or "").strip().replace("€", "").replace("EUR", "").strip()
    neg = s.startswith("-") or s.endswith("-")
    s = s.strip("-").strip()
    if re.match(r"^\d{1,3}(\.\d{3})*,\d{1,2}$", s) or re.match(r"^\d+,\d{1,2}$", s):
        v = float(s.replace(".", "").replace(",", "."))
    elif re.match(r"^\d{1,3}(,\d{3})*\.\d{1,2}$", s) or re.match(r"^\d+\.\d{1,2}$", s):
        v = float(s.replace(",", ""))
    else:
        v = float(s.replace(".", "").replace(",", ".")) if s else 0.0
    return -v if neg else v


def inc_number(s):
    m = re.match(r"^(.*?)(\d+)(\D*)$", s or "")
    if not m:
        return (s or "") + "1"
    pre, n, post = m.groups()
    return f"{pre}{str(int(n) + 1).zfill(len(n))}{post}"


_WIN_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s or "").strip().rstrip(".").strip()
    root, ext = os.path.splitext(s)
    if not ext and root.startswith(".") and "." not in root[1:]:   # v2.1.0: ".pdf" keeps its extension -> "datei.pdf"
        root, ext = "", root
    root = root.strip().strip(".")
    ext = ext[:12]
    if root.lower() in _WIN_RESERVED:                               # v2.1.0: CON.pdf, NUL.txt ... cannot be created on Windows
        root = "_" + root
    return (root[:120 - len(ext)] or "datei") + ext


PATH_MAX_WIN = 240     # v2.6.3: stay below MAX_PATH (260) - Windows without LongPathsEnabled cannot create longer paths


def fit_path(folder, name, limit=PATH_MAX_WIN):
    """folder + name, the file name (not the extension) shortened so that the full path stays below limit"""
    p = os.path.join(folder, name)
    over = len(os.path.abspath(p)) - limit
    if over <= 0:
        return p
    root, ext = os.path.splitext(name)
    root = root[:max(8, len(root) - over)].rstrip(" .") or "datei"
    return os.path.join(folder, root + ext)


def _frist(v, default=7):
    """v2.0.6: payment term - 0 (sofort) stays 0, only empty -> default"""
    try:
        return int(v) if str(v).strip() not in ("", "None") else default
    except Exception:
        return default


def item_total(inv, it):
    """v2.0.6: a locked (issued) document is always reproduced with its stored line totals"""
    if inv and inv.get("locked") and it.get("total") not in (None, ""):
        try:
            return round(float(it["total"]), 2)
        except Exception:
            pass
    return line_total(it)


def line_total(it):
    q = float(it.get("qty") or 0)
    p = float(it.get("price") or 0)
    r = float(it.get("rabatt") or 0)
    v = q * p * (1 - r / 100.0)
    # v2.0.6: kaufmaennisch runden, auch negativ (Storno = exakt -Original)
    return math.copysign(round(abs(v) + 1e-9, 2), v) if v else 0.0


def write_file(path, data, text=False):
    try:
        if text:
            open(path, "w", encoding="utf-8-sig").write(data)
        else:
            open(path, "wb").write(data)
    except PermissionError:
        raise ValueError(f"Die Datei {os.path.basename(path)} ist noch geöffnet (z. B. im PDF-Viewer oder Excel) - bitte schließen und erneut versuchen.")


def open_path(p):
    # v3.7.0: the iPhone app sets builtins.PA_OPEN_HOOK (share sheet / "Oeffnen in") - no desktop program to start there
    hk = getattr(__import__("builtins"), "PA_OPEN_HOOK", None)
    if hk:
        try:
            return bool(hk(str(p)))
        except Exception:
            traceback.print_exc()
            return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # noqa
        else:
            # v2.6.3: argument list instead of a shell string (quotes / $() in a path were executed)
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY, kdnr TEXT UNIQUE, anrede TEXT, firma TEXT, name TEXT,
  strasse TEXT, plz TEXT, ort TEXT, land TEXT, tel TEXT, mobil TEXT, mail TEXT,
  web TEXT, notiz TEXT, gruppe TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY, nr TEXT, name TEXT, descr TEXT, price REAL, unit TEXT,
  cat TEXT, active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS texts (id INTEGER PRIMARY KEY, kind TEXT, text TEXT, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY, nr TEXT UNIQUE, customer_id INTEGER, project_id INTEGER,
  kdnr TEXT, addr TEXT, datum TEXT, liefer TEXT, auftrag TEXT, titel TEXT,
  toptext TEXT, foottext TEXT, zahlart TEXT, frist INTEGER, status TEXT,
  bezahlt_am TEXT, summe REAL, notiz TEXT, source TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, invoice_id INTEGER, pos INTEGER, qty REAL, nr TEXT,
  name TEXT, descr TEXT, price REAL, rabatt REAL, total REAL, article_id INTEGER);
CREATE TABLE IF NOT EXISTS belege (
  id INTEGER PRIMARY KEY, typ TEXT, datum TEXT, partner TEXT, nr TEXT, betrag REAL,
  kategorie TEXT, notiz TEXT, file TEXT, details TEXT, invoice_id INTEGER,
  project_id INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY, nr TEXT, name TEXT, customer_id INTEGER, bereich TEXT,
  status TEXT, start TEXT, ende TEXT, descr TEXT, folders TEXT, dir TEXT,
  budget REAL, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS project_files (
  id INTEGER PRIMARY KEY, project_id INTEGER, folder TEXT, kind TEXT, name TEXT,
  path TEXT, size INTEGER, note TEXT, added TEXT);
CREATE TABLE IF NOT EXISTS project_entries (
  id INTEGER PRIMARY KEY, project_id INTEGER, datum TEXT, art TEXT, nr TEXT,
  name TEXT, descr TEXT, qty REAL, unit TEXT, price REAL, invoice_id INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS templates (id INTEGER PRIMARY KEY, name TEXT, bereich TEXT, folders TEXT);
CREATE TABLE IF NOT EXISTS taxyear (year INTEGER PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS mahnungen (id INTEGER PRIMARY KEY, invoice_id INTEGER, stufe INTEGER, datum TEXT,
  frist_bis TEXT, gebuehr REAL, betrag REAL, file TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS mail_log (id INTEGER PRIMARY KEY, doc_id INTEGER, mahnung_id INTEGER, an TEXT,
  betreff TEXT, datum TEXT, ok INTEGER, fehler TEXT);
CREATE TABLE IF NOT EXISTS bank_tx (id INTEGER PRIMARY KEY, hash TEXT UNIQUE, datum TEXT, betrag REAL, name TEXT,
  zweck TEXT, iban TEXT, invoice_id INTEGER, beleg_id INTEGER, status TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS recurring (id INTEGER PRIMARY KEY, name TEXT, invoice_id INTEGER, intervall INTEGER,
  naechstes TEXT, aktiv INTEGER DEFAULT 1, letzte TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS vertraege (id INTEGER PRIMARY KEY, name TEXT, customer_id INTEGER, project_id INTEGER,
  intervall INTEGER, naechste TEXT, preis REAL, article_id INTEGER, beschreibung TEXT, auto_rechnung INTEGER DEFAULT 1,
  vorlauf INTEGER DEFAULT 14, aktiv INTEGER DEFAULT 1, notiz TEXT, letzte TEXT);
CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, customer_id INTEGER, article_id INTEGER,
  modus TEXT DEFAULT 'monat', dauer REAL DEFAULT 1, rhythmus TEXT, aktiv INTEGER DEFAULT 1, notiz TEXT, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS kurse (id INTEGER PRIMARY KEY, name TEXT, article_id INTEGER, customer_id INTEGER,
  modus TEXT DEFAULT 'monat', dauer REAL DEFAULT 1, rhythmus TEXT, aktiv INTEGER DEFAULT 1, notiz TEXT, start TEXT, ende TEXT,
  farbe TEXT, sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS kurs_members (id INTEGER PRIMARY KEY, kurs_id INTEGER, student_id INTEGER, seit TEXT,
  UNIQUE(kurs_id, student_id));
CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY, student_id INTEGER, datum TEXT, dauer REAL, status TEXT,
  notiz TEXT, invoice_id INTEGER);
CREATE TABLE IF NOT EXISTS assets (id INTEGER PRIMARY KEY, bezeichnung TEXT, kategorie TEXT, kaufdatum TEXT, betrag REAL,
  nd_jahre REAL, methode TEXT, beleg_id INTEGER, seriennr TEXT, standort TEXT, notiz TEXT, abgang TEXT, project_id INTEGER);
CREATE TABLE IF NOT EXISTS fahrten (id INTEGER PRIMARY KEY, datum TEXT, ziel TEXT, zweck TEXT, km REAL, art TEXT,
  project_id INTEGER, customer_id INTEGER, notiz TEXT);
CREATE TABLE IF NOT EXISTS steuerakte (id INTEGER PRIMARY KEY, year INTEGER, art TEXT, titel TEXT, datum TEXT, file TEXT,
  notiz TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS kontostand (id INTEGER PRIMARY KEY, datum TEXT UNIQUE, saldo REAL, quelle TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS beleg_learn (id INTEGER PRIMARY KEY, typ TEXT, kategorie TEXT, partner TEXT, tokens TEXT,
  beleg_id INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS pending_belege (id INTEGER PRIMARY KEY, file TEXT, name TEXT, result TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS eingang_log (id INTEGER PRIMARY KEY, datum TEXT, file TEXT, typ TEXT, betrag REAL, partner TEXT,
  status TEXT, beleg_id INTEGER, invoice_id INTEGER, info TEXT);
CREATE TABLE IF NOT EXISTS zertifikate (id INTEGER PRIMARY KEY, typ TEXT, bezeichnung TEXT, person TEXT, nummer TEXT,
  norm TEXT, ausgestellt TEXT, gueltig_bis TEXT, bestaetigt_am TEXT, bestaetigung_monate INTEGER, file TEXT, notiz TEXT,
  aktiv INTEGER DEFAULT 1);
"""

MIGRATIONS = {
    "invoices": [("typ", "TEXT DEFAULT 'rechnung'"), ("ref_id", "INTEGER"), ("storno_von", "INTEGER"),
                 ("locked", "INTEGER DEFAULT 0"), ("mahnstufe", "INTEGER DEFAULT 0"), ("versendet_am", "TEXT"),
                 ("gueltig_bis", "TEXT")],
    "items": [("entry_id", "INTEGER")],
    "belege": [("quelle", "TEXT")],
    "students": [("person_customer_id", "INTEGER")],
    "lessons": [("kurs_id", "INTEGER")],
}


def migrate():
    for table, cols in MIGRATIONS.items():
        have = {r["name"] for r in q(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                x(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                if table == "invoices" and name == "locked":
                    x("UPDATE invoices SET locked=1 WHERE status='bezahlt'")
    x("UPDATE invoices SET typ='rechnung' WHERE typ IS NULL OR typ=''")



def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


CON = None


def q(sql, args=(), one=False):
    with DB_LOCK:
        cur = CON.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    with DB_LOCK:
        cur = CON.execute(sql, args)
        CON.commit()
        return cur.lastrowid


def get_settings():
    s = dict(DEFAULT_SETTINGS)
    for r in q("SELECT k, v FROM settings"):
        try:
            s[r["k"]] = json.loads(r["v"])
        except Exception:
            s[r["k"]] = r["v"]
    return s


def set_setting(k, v):
    x("INSERT OR REPLACE INTO settings (k, v) VALUES (?, ?)", (k, json.dumps(v, ensure_ascii=False)))


def init_db():
    global CON
    first = not os.path.exists(DB_PATH)
    CON = db()
    with DB_LOCK:
        CON.executescript(SCHEMA)
        CON.commit()
    migrate()
    logo_dst = os.path.join(ASSET_DIR, "logo.jpg")
    if not os.path.exists(logo_dst) and os.path.exists(res_path("assets", "logo.jpg")):
        shutil.copy(res_path("assets", "logo.jpg"), logo_dst)
    for t in q("SELECT id, folders FROM templates"):
        if "(VT/PT/MT)" in (t["folders"] or ""):
            x("UPDATE templates SET folders=? WHERE id=?", (t["folders"].replace("(VT/PT/MT)", "(VT, PT, MT)"), t["id"]))
    if not q("SELECT id FROM templates LIMIT 1"):
        for t in PROJECT_TEMPLATES:
            x("INSERT INTO templates (name, bereich, folders) VALUES (?,?,?)",
              (t["name"], t["bereich"], json.dumps(t["folders"], ensure_ascii=False)))
    keep = {os.path.basename(r["file"] or "") for r in q("SELECT file FROM pending_belege")}
    for f in os.listdir(DATA_DIR):
        if f.startswith("_tmp_") and f not in keep:
            try:
                os.remove(os.path.join(DATA_DIR, f))
            except Exception:
                pass
    if first:
        seed()


def seed():
    p = res_path("assets", "seed.json")
    if not os.path.exists(p):
        return
    d = json.load(open(p, encoding="utf-8"))
    for i, a in enumerate(d.get("articles", [])):
        x("INSERT INTO articles (nr, name, descr, price, unit, cat, active, sort) VALUES (?,?,?,?,?,?,1,?)",
          (a["nr"], a["name"], a["desc"], a["price"], "Std" if "std" in a["name"].lower() else "Stk", a.get("cat", ""), i))
    for c in d.get("customers", []):
        x("INSERT OR IGNORE INTO customers (kdnr, anrede, firma, name, strasse, plz, ort, land, tel, mobil, mail, web, notiz, gruppe, created) "
          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (c["kdnr"], c.get("anrede", ""), c["firma"], c["name"], c["strasse"], c["plz"], c["ort"], "DE",
           c["tel"], c["mobil"], c["mail"], c["web"], "", "Kunden", now_iso()))
    tops = [
        "Vielen Dank für Ihren Auftrag! Bitte zahlen Sie den Betrag binnen [Frist] Tagen ab Rechnungsdatum.",
        "Vielen Dank für Ihren Auftrag! Zahlungsziel binnen [Frist] Tagen ab Rechnungsdatum.",
        "Vielen Dank für Ihre Bestellung! Zahlungsziel binnen [Frist] Tagen ab Rechnungsdatum.",
        "Gemäß Ihrem Auftrag berechnen wir Ihnen die folgenden Positionen.",
        "Bitte überweisen Sie den Betrag bis zum [Zahlungsfrist] auf unser Konto.",
    ]
    foots = [
        "Kein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
        "Betrag dankend erhalten.\nKein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
        "Bitte überweisen Sie den Betrag bis zum [Zahlungsfrist] auf unser Konto.\nKein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
    ]
    for i, t in enumerate(tops):
        x("INSERT INTO texts (kind, text, sort) VALUES ('top', ?, ?)", (t, i))
    for i, t in enumerate(foots):
        x("INSERT INTO texts (kind, text, sort) VALUES ('foot', ?, ?)", (t, i))
    for inv in d.get("invoices", []):
        c = q("SELECT * FROM customers WHERE kdnr=?", (inv["kdnr"],), one=True)
        frist = 14 if "14 Tagen" in inv["toptext"] else 7
        top = inv["toptext"].replace(f"binnen {frist} Tagen", "binnen [Frist] Tagen")
        data = {
            "nr": inv["nr"], "customer_id": c["id"] if c else None, "kdnr": inv["kdnr"],
            "addr": address_lines(c) if c else [], "datum": iso_from_de(inv["datum"]),
            "liefer": iso_from_de(inv["liefer"]), "auftrag": iso_from_de(inv["auftrag"]),
            "titel": inv["titel"], "toptext": top,
            "foottext": "Kein Ausweis der Mehrwertsteuer, da Kleinunternehmer nach §19 (1) UStG",
            "zahlart": inv["zahlart"], "frist": frist, "status": "bezahlt",
            "bezahlt_am": iso_from_de(inv["datum"]), "source": "import",
            "items": [{"qty": it["qty"], "nr": it["nr"], "name": it["name"], "descr": it["desc"],
                       "price": it["price"], "rabatt": it["rabatt"]} for it in inv["items"]],
        }
        save_invoice(data, bump=False)
