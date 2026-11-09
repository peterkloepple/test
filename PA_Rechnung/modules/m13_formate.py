# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m13_formate
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# v1.4.0  Belegimport fuer alle Formate, Passwortschutz, Kontostand
# ----------------------------------------------------------------------------
import zlib
import email
import email.policy
from html.parser import HTMLParser


class PasswordNeeded(Exception):
    def __init__(self, wrong=False, kind=""):
        super().__init__("password")
        self.wrong = wrong
        self.kind = kind


CONTAINER_EXT = (".zip", ".eml", ".msg")
ZIP_MEMBER_MAX = 50 * 1024 * 1024      # v2.6.3: unpacked size per zip member / ODF part
ZIP_TOTAL_MAX = 200 * 1024 * 1024      # v2.6.3: unpacked size of all members of one zip
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp")
FORMAT_NAMES = {".pdf": "PDF", ".xlsx": "Excel", ".xlsm": "Excel", ".xls": "Excel (alt)", ".docx": "Word", ".doc": "Word (alt)",
                ".pptx": "PowerPoint", ".odt": "OpenOffice Text", ".ods": "OpenOffice Tabelle", ".odp": "OpenOffice Präsentation",
                ".csv": "CSV", ".txt": "Text", ".rtf": "RTF", ".html": "HTML", ".htm": "HTML", ".xml": "XML", ".json": "JSON",
                ".eml": "E-Mail", ".msg": "Outlook-Mail", ".zip": "ZIP-Archiv"}
FILE_PW = {}   # abs path -> password (session only, for previews)


def saved_passwords():
    out = []
    for v in get_settings().get("beleg_pw") or []:
        try:
            out.append(unprotect_secret(v))
        except Exception:
            pass
    return [p for p in out if p]


def remember_password(pw):
    if not pw or pw in saved_passwords():
        return
    lst = list(get_settings().get("beleg_pw") or [])
    lst.append(protect_secret(pw))
    set_setting("beleg_pw", lst[-30:])


def _candidates(pw):
    c = []
    if pw is not None:
        c.append(pw)
    else:
        std = (get_settings().get("std_pw") or "").strip()
        c += [""] + ([std] if std else []) + saved_passwords()
    out = []
    for p_ in c:
        if p_ not in out:
            out.append(p_)
    return out


# ---------------- PDF ----------------
def pdf_open(path, pw=None):
    r = pypdf.PdfReader(path)
    if not r.is_encrypted:
        return r, None
    for c in _candidates(pw):
        try:
            if r.decrypt(c):
                return r, c
        except Exception:
            continue
    raise PasswordNeeded(wrong=pw is not None, kind="PDF")


def pdf_text_pw(path, pw=None, pages=8):
    r, used = pdf_open(path, pw)
    parts = []
    for pg in r.pages[:pages]:
        try:
            parts.append(pg.extract_text(extraction_mode="layout") or "")
        except Exception:
            try:
                parts.append(pg.extract_text() or "")
            except Exception:
                pass
    return "\n".join(parts), used


# ---------------- MS Office (encrypted CFB container) ----------------
def office_bytes(path, pw=None):
    """returns (bytes, used_password); decrypts MS-Office encryption if needed"""
    data = open(path, "rb").read()
    if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return data, None
    try:
        import msoffcrypto
    except Exception:
        msoffcrypto = None
    if msoffcrypto is None:
        return data, None
    try:
        of = msoffcrypto.OfficeFile(io.BytesIO(data))
        enc = of.is_encrypted()
    except Exception:
        return data, None
    if not enc:
        return data, None
    cands = _candidates(pw) + ([] if pw is not None else ["VelvetSweatshop"])
    for c in cands:
        if c == "" and pw is None:
            continue
        try:
            of = msoffcrypto.OfficeFile(io.BytesIO(data))
            of.load_key(password=c)
            out = io.BytesIO()
            of.decrypt(out)
            return out.getvalue(), c
        except Exception:
            continue
    raise PasswordNeeded(wrong=pw is not None, kind="Office")


def _xml_text(xml, para_tags, cell_tags=(), text_tag=None):
    """generic: one line per paragraph/row, tab between cells"""
    try:
        root = ET.fromstring(xml)
    except Exception:
        return re.sub(r"<[^>]+>", " ", xml.decode("utf-8", "ignore"))
    lines = []

    def local(t):
        return t.rsplit("}", 1)[-1]

    def walk(el, buf):
        tg = local(el.tag)
        if tg in ("tab",):
            buf.append("\t")
        if el.text and (text_tag is None or tg == text_tag):
            buf.append(el.text)
        for ch in el:
            if local(ch.tag) in para_tags:
                b = []
                walk(ch, b)
                lines.append("".join(b))
            elif local(ch.tag) in cell_tags:
                b = []
                walk(ch, b)
                buf.append("".join(b).strip() + "\t")
            else:
                walk(ch, buf)
            if ch.tail and text_tag is None:
                buf.append(ch.tail)
    top = []
    walk(root, top)
    if "".join(top).strip():
        lines.append("".join(top))
    return "\n".join(l.rstrip("\t ") for l in lines if l.strip())


def docx_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    parts = []
    for n in ["word/document.xml"] + sorted(n for n in z.namelist() if re.match(r"word/(header|footer)\d*\.xml", n)):
        if n in z.namelist():
            parts.append(_xml_text(z.read(n), ("p", "tr"), ("tc",), "t"))
    return "\n".join(parts)


def pptx_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.findall(r"\d+", n)[0]))
    return "\n".join(_xml_text(z.read(n), ("p",), (), "t") for n in slides)


def xlsx_text(data):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:6]:
        if len(wb.worksheets) > 1 and out:
            out.append("")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > 400:
                break
            cells = _row_str(row)
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                out.append("\t".join(cells))
    wb.close()
    return "\n".join(out)


MONEY_ROW = re.compile(r"betrag|summe|preis|total|gesamt|netto|brutto|mwst|ust|eur|€|zahlbetrag|endbetrag|saldo", re.I)


def _row_str(row):
    money = any(isinstance(v, str) and MONEY_ROW.search(v) for v in row)
    return [num_de(v) if money and isinstance(v, int) and not isinstance(v, bool) else _cell_str(v) for v in row]


def _cell_str(v):
    if v is None:
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, float):
        return num_de(v)
    return str(v).strip()


def xls_text(data):
    import xlrd
    wb = xlrd.open_workbook(file_contents=data)
    out = []
    for sh in wb.sheets()[:6]:
        if out:
            out.append("")
        for r in range(min(sh.nrows, 400)):
            cells = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        cells.append(xlrd.xldate_as_datetime(cell.value, wb.datemode).strftime("%d.%m.%Y"))
                        continue
                    except Exception:
                        pass
                cells.append(_cell_str(cell.value) if cell.ctype != xlrd.XL_CELL_EMPTY else "")
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                out.append("\t".join(cells))
    return "\n".join(out)


def doc_text(data):
    """Word 97-2003 binary: read the piece table"""
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(data))
    wd = ole.openstream("WordDocument").read()
    flags = struct.unpack_from("<H", wd, 0x0A)[0]
    if flags & 0x0100:
        raise PasswordNeeded(kind="Word")
    tbl_name = "1Table" if flags & 0x0200 else "0Table"
    tbl = ole.openstream(tbl_name).read()
    fc_clx, lcb_clx = struct.unpack_from("<II", wd, 0x01A2)
    clx = tbl[fc_clx:fc_clx + lcb_clx]
    i = 0
    while i < len(clx) and clx[i] == 1:
        i += 3 + struct.unpack_from("<H", clx, i + 1)[0]
    if i >= len(clx) or clx[i] != 2:
        raise ValueError("Word-Struktur nicht lesbar")
    lcb = struct.unpack_from("<I", clx, i + 1)[0]
    plc = clx[i + 5:i + 5 + lcb]
    n = (lcb - 4) // 12
    cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
    out = []
    for k in range(n):
        pcd = plc[(n + 1) * 4 + k * 8:(n + 1) * 4 + k * 8 + 8]
        fc = struct.unpack_from("<I", pcd, 2)[0]
        cnt = cps[k + 1] - cps[k]
        if fc & 0x40000000:
            off = (fc & 0x3FFFFFFF) // 2
            out.append(wd[off:off + cnt].decode("cp1252", "replace"))
        else:
            out.append(wd[fc:fc + cnt * 2].decode("utf-16le", "replace"))
    t = "".join(out)
    t = t.replace("\r", "\n").replace("\x07", "\t").replace("\x0b", "\n").replace("\x0c", "\n")
    t = re.sub(r"\x13[^\x14\x15]*\x14?", "", t).replace("\x15", "")
    return re.sub(r"[\x00-\x08\x0e-\x1f]", "", t)


# ---------------- OpenDocument (incl. ODF 1.2 AES encryption) ----------------
def odf_text(path, pw=None):
    z = zipfile.ZipFile(path)
    if z.getinfo("content.xml").file_size > ZIP_MEMBER_MAX:
        raise ValueError("content.xml zu groß")
    raw = z.read("content.xml")
    used = None
    man = z.read("META-INF/manifest.xml") if "META-INF/manifest.xml" in z.namelist() else b""
    if b"encryption-data" in man and raw[:5] != b"<?xml":
        ok = False
        for c in _candidates(pw):
            if c == "":
                continue
            try:
                raw2 = odf_decrypt(man, "content.xml", raw, c)
                ET.fromstring(raw2)
                raw, used, ok = raw2, c, True
                break
            except Exception:
                continue
        if not ok:
            raise PasswordNeeded(wrong=pw is not None, kind="OpenDocument")
    if path.lower().endswith((".ods", ".ots")):
        return ods_text(raw), used
    return _xml_text(raw, ("p", "h", "table-row"), ("table-cell",)), used


def ods_text(raw):
    O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
    T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
    root = ET.fromstring(raw)
    out = []
    for tb in root.iter(T + "table"):
        if out:
            out.append("")
        for row in list(tb.iter(T + "table-row"))[:400]:
            cells = []
            for c in row:
                if c.tag not in (T + "table-cell", T + "covered-table-cell"):
                    continue
                vt = c.get(O + "value-type")
                if vt in ("float", "currency", "percentage") and c.get(O + "value"):
                    v = num_de(float(c.get(O + "value")))
                elif vt == "date" and c.get(O + "date-value"):
                    v = de_date(c.get(O + "date-value")[:10])
                else:
                    v = " ".join("".join(pp.itertext()) for pp in c).strip()
                rep = min(int(c.get(T + "number-columns-repeated") or 1), 20)
                cells += [v] * (rep if v else min(rep, 1))
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                out.append("\t".join(cells))
    return "\n".join(out)


def odf_decrypt(manifest, name, data, pw):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    root = ET.fromstring(manifest)
    ns = {"m": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"}
    M = "{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}"
    for fe in root.findall("m:file-entry", ns):
        if fe.get(M + "full-path") != name:
            continue
        ed = fe.find("m:encryption-data", ns)
        alg = ed.find("m:algorithm", ns)
        kd = ed.find("m:key-derivation", ns)
        sk = ed.find("m:start-key-generation", ns)
        iv = base64.b64decode(alg.get(M + "initialisation-vector"))
        salt = base64.b64decode(kd.get(M + "salt"))
        it = int(kd.get(M + "iteration-count"))
        ks = int(kd.get(M + "key-size") or 16)
        skname = (sk.get(M + "start-key-generation-name") if sk is not None else "SHA1") or "SHA1"
        start = hashlib.sha256(pw.encode("utf-8")).digest() if "256" in skname else hashlib.sha1(pw.encode("utf-8")).digest()
        key = PBKDF2HMAC(algorithm=hashes.SHA1(), length=ks, salt=salt, iterations=it).derive(start)
        aname = alg.get(M + "algorithm-name") or ""
        if "aes256-cbc" not in aname:
            raise ValueError("Verschlüsselung (Blowfish) wird nicht unterstützt")
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        plain = dec.update(data) + dec.finalize()
        plain = plain[:-plain[-1]] if 0 < plain[-1] <= 16 else plain
        return zlib.decompress(plain, -15)
    raise ValueError("kein Eintrag")


# ---------------- simple formats ----------------
class _HT(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, a):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("br", "p", "tr", "div", "li", "h1", "h2", "h3", "table"):
            self.out.append("\n")
        if tag in ("td", "th"):
            self.out.append("\t")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def html_text(t):
    p = _HT()
    p.feed(t)
    return re.sub(r"[ \xa0]+", " ", "".join(p.out))


def rtf_text(t):
    t = re.sub(r"\\par[d]?\b", "\n", t)
    t = re.sub(r"\\tab\b", "\t", t)
    # v2.6.3: \uN first, together with its fallback character (\'fc, ? or one plain char, see \ucN) -
    # the fallback was decoded as well (umlaut came out twice: "Mueueller")
    fb = "" if re.search(r"\\uc0\b", t) else r"(?:\\'[0-9a-fA-F]{2}|\?|[^\\{}\s])?"
    t = re.sub(r"\\u(-?\d+) ?" + fb, lambda m: chr(int(m.group(1)) % 65536), t)
    t = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"), t)
    t = re.sub(r"\{\\\*[^{}]*\}", "", t)
    t = re.sub(r"\\[a-z]+-?\d* ?", "", t)
    return t.replace("{", "").replace("}", "")


def extract_text_any(path, filename, pw=None):
    """-> (text, used_password, format_name). Raises PasswordNeeded."""
    ext = os.path.splitext(filename.lower())[1]
    fmt = FORMAT_NAMES.get(ext, ext.lstrip(".").upper() or "Datei")
    if ext == ".pdf":
        t, used = pdf_text_pw(path, pw)
        return t, used, fmt
    if ext in (".docx", ".docm", ".dotx", ".xlsx", ".xlsm", ".xltx", ".pptx", ".doc", ".xls", ".ppt"):
        data, used = office_bytes(path, pw)
        if data[:2] == b"PK":
            if ext.startswith(".doc") or ext == ".dotx":
                return docx_text(data), used, fmt
            if ext.startswith(".xl"):
                return xlsx_text(data), used, fmt
            return pptx_text(data), used, fmt
        if ext == ".xls":
            return xls_text(data), used, fmt
        if ext == ".doc":
            return doc_text(data), used, fmt
        return "", used, fmt
    if ext in (".odt", ".ods", ".odp", ".ott"):
        t, used = odf_text(path, pw)
        return t, used, fmt
    raw = open(path, "rb").read(4_000_000)
    if ext in (".html", ".htm"):
        return html_text(_decode(raw)), None, fmt
    if ext == ".rtf":
        return rtf_text(_decode(raw)), None, fmt
    if ext == ".xml":
        return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", _decode(raw))), None, fmt
    if ext in (".csv", ".txt", ".tsv", ".json", ".md", ".log", ".ini") or not ext:
        return _decode(raw), None, fmt
    if ext in IMAGE_EXT:
        return "", None, "Bild"
    # unknown: try as text if it looks like text
    if raw and sum(1 for b in raw[:2000] if b < 9 or 13 < b < 32) < 20:
        return _decode(raw), None, fmt
    return "", None, fmt


# ---------------- containers: zip, eml, msg ----------------
def _tmp_for(name):
    return os.path.join(DATA_DIR, "_tmp_" + uuid.uuid4().hex + os.path.splitext(name)[1].lower())


def unpack_container(path, filename, pw=None):
    """-> (list of (name, bytes), mail_text, used_pw)"""
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".zip":
        try:
            import pyzipper
            Z = pyzipper.AESZipFile
        except Exception:
            Z = zipfile.ZipFile
        with Z(path) as z:
            infos = [i for i in z.infolist() if not i.is_dir() and not os.path.basename(i.filename).startswith((".", "__MACOSX"))
                     and "__MACOSX" not in i.filename][:60]
            # v2.6.3: zip bomb guard - every member is read into memory; skip huge members, cap the total
            infos = [i for i in infos if i.file_size <= ZIP_MEMBER_MAX]
            tot_, keep_ = 0, []
            for i in infos:
                tot_ += i.file_size
                if tot_ > ZIP_TOTAL_MAX:
                    break
                keep_.append(i)
            infos = keep_
            enc = any(i.flag_bits & 0x1 for i in infos)
            used = None
            if enc:
                ok = False
                for c in _candidates(pw):
                    if c == "":
                        continue
                    try:
                        z.setpassword(c.encode("utf-8"))
                        z.read(next(i for i in infos if i.flag_bits & 0x1).filename)
                        used, ok = c, True
                        break
                    except Exception:
                        continue
                if not ok:
                    raise PasswordNeeded(wrong=pw is not None, kind="ZIP")
            out = []
            for i in infos:
                nm = i.filename
                try:
                    nm = nm.encode("cp437").decode("utf-8") if not (i.flag_bits & 0x800) else nm
                except Exception:
                    pass
                try:
                    out.append((os.path.basename(nm), z.read(i.filename)))
                except RuntimeError:
                    raise PasswordNeeded(wrong=pw is not None, kind="ZIP")
            return out, "", used
    if ext == ".eml":
        m = email.message_from_bytes(open(path, "rb").read(), policy=email.policy.default)
        head = f"Von: {m.get('from', '')}\nAn: {m.get('to', '')}\nDatum: {m.get('date', '')}\nBetreff: {m.get('subject', '')}\n\n"
        body = ""
        try:
            b = m.get_body(preferencelist=("plain", "html"))
            if b is not None:
                body = b.get_content()
                if b.get_content_type() == "text/html":
                    body = html_text(body)
        except Exception:
            pass
        atts = []
        for part in m.iter_attachments():
            fn = part.get_filename()
            if not fn:
                continue
            if part.get("Content-ID") and part.get_content_maintype() == "image":
                continue
            if (part.get_content_disposition() or "") == "inline" and part.get_content_maintype() == "image":
                continue
            try:
                atts.append((fn, part.get_payload(decode=True) or b""))
            except Exception:
                continue
        return atts, body + "\n\n" + head, None
    if ext == ".msg":
        import olefile
        ole = olefile.OleFileIO(path)

        def prop(st, code):
            for suf, enc in (("001F", "utf-16le"), ("001E", "cp1252")):
                n = st + ["__substg1.0_" + code + suf]
                if ole.exists("/".join(n)):
                    return ole.openstream(n).read().decode(enc, "replace").rstrip("\x00")
            return ""
        head = f"Von: {prop([], '0C1A')} <{prop([], '0C1F')}>\nBetreff: {prop([], '0037')}\n\n"
        body = prop([], "1000")
        if not body and ole.exists("__substg1.0_10130102"):
            body = html_text(_decode(ole.openstream("__substg1.0_10130102").read()))
        atts = []
        for e in ole.listdir(streams=False, storages=True):
            if len(e) == 1 and e[0].startswith("__attach_version1.0_"):
                nm = prop(e, "3707") or prop(e, "3704") or "anhang"
                dp = e + ["__substg1.0_37010102"]
                if ole.exists("/".join(dp)):
                    atts.append((nm, ole.openstream(dp).read()))
        ole.close()
        return atts, body + "\n\n" + head, None
    return [], "", None


BELEG_LIKE = re.compile(r"\.(pdf|xml|xlsx|xlsm|xls|docx|doc|odt|ods|csv|txt|rtf|html?|jpe?g|png|tiff?|bmp|zip|eml|msg|pptx)$", re.I)


def locked_result(path, filename, e, container=False):
    return {"needs_password": True, "wrong": bool(e.wrong), "format": FORMAT_NAMES.get(os.path.splitext(filename.lower())[1]) or e.kind,
            "filename": filename, "typ": "ausgabe", "confidence": 0, "datum": "", "partner": "", "nr": "", "betrag": 0.0,
            "kategorie": "Sonstige Betriebsausgaben", "details": {}, "text": "", "container": container,
            "hint": ("Passwort falsch – bitte nochmal." if e.wrong else "Die Datei ist mit einem Passwort geschützt.")}


def analyze_any(path, filename, pw=None, depth=0):
    """returns a list of analysis results (containers expand to several)"""
    ext = os.path.splitext(filename.lower())[1]
    if ext in CONTAINER_EXT and depth < 3:
        try:
            atts, mailtext, _used = unpack_container(path, filename, pw)
        except PasswordNeeded as e:
            return [locked_result(path, filename, e, True)]
        except Exception:
            atts, mailtext = [], ""
            traceback.print_exc()
        IMG = re.compile(r"\.(png|jpe?g|gif|bmp|tiff?)$", re.I)
        kids = [(n, b) for n, b in atts if BELEG_LIKE.search(n) and len(b) > 0]
        if ext != ".zip" and any(not IMG.search(n) for n, b in kids):
            kids = [(n, b) for n, b in kids if not IMG.search(n)]   # mail: documents present -> images are logos
        kids = [(n, b) for n, b in kids if not (IMG.search(n) and len(b) < 30000)]
        seen_h = set()
        uniq = []
        for n, b in kids:
            h_ = hashlib.sha1(b).hexdigest()
            if h_ not in seen_h:
                seen_h.add(h_)
                uniq.append((n, b))
        kids = uniq
        if kids:
            out = []
            for n, b in kids[:40]:
                tp = _tmp_for(n)
                write_file(tp, b)
                for r in analyze_any(tp, n, None, depth + 1):
                    r["aus"] = filename
                    r.setdefault("_path", tp)
                    out.append(r)
            try:
                os.remove(path)
            except Exception:
                pass
            return out
        if mailtext:
            res = analyze_text(path, filename, mailtext, "E-Mail")
            return [res]
    try:
        res = analyze_pdf(path, filename, pw)
    except PasswordNeeded as e:
        return [locked_result(path, filename, e)]
    return [res]


def analyze_text(path, filename, text, fmt):
    """run the rule engine on already extracted text (analyze_pdf with pre_text, no file is read)"""
    res = analyze_pdf(path, filename, None, pre_text=text, pre_fmt=fmt)
    return res


def prepare_results(results, path, name):
    """assist + token registration (upload and inbox)"""
    out = []
    for res in results:
        p_ = res.pop("_path", None) or path
        if not res.get("needs_password"):
            try:
                res = assist(res)
            except Exception:
                traceback.print_exc()
        tok = uuid.uuid4().hex
        TMP[tok] = {"path": p_, "name": res.get("filename") or name, "pw": res.pop("_pw", None)}
        if TMP[tok]["pw"]:
            FILE_PW[os.path.abspath(p_)] = TMP[tok]["pw"]
        res["token"] = tok
        res["tmp"] = os.path.relpath(p_, DATA_DIR)
        out.append(res)
    return out


def unlock_beleg(d):
    t = TMP.get(d.get("token"))
    if not t or not os.path.exists(t["path"]):
        return {"ok": False, "error": "Datei nicht mehr vorhanden – bitte neu einfügen."}
    pw = d.get("password") or ""
    res = analyze_any(t["path"], t["name"], pw)
    if len(res) == 1 and res[0].get("needs_password"):
        r = dict(res[0], token=d["token"], tmp=os.path.relpath(t["path"], DATA_DIR))
        if d.get("pending_id"):
            r["pending_id"] = d["pending_id"]
        return {"ok": True, "items": [r]}
    TMP.pop(d["token"], None)
    THUMB_CACHE.pop(os.path.relpath(t["path"], DATA_DIR), None)
    if d.get("merken"):
        remember_password(pw)
    for r in res:
        if not r.get("_path"):
            r["_pw"] = pw
    items = prepare_results(res, t["path"], t["name"])
    if d.get("pending_id"):
        x("DELETE FROM pending_belege WHERE id=?", (int(d["pending_id"]),))
        for it in items:
            keep = {k: v for k, v in it.items() if k not in ("token", "pending_id")}
            it["pending_id"] = x("INSERT INTO pending_belege (file, name, result, created) VALUES (?,?,?,?)",
                                 (it["tmp"], it.get("filename") or t["name"], json.dumps(keep, ensure_ascii=False, default=str), now_iso()))
    return {"ok": True, "items": items}


def text_preview_png(text, fmt, locked=False):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (300, 400), "white")
    dr = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("arial.ttf", 11)
        fb = ImageFont.truetype("arialbd.ttf", 22)
    except Exception:
        try:
            f = ImageFont.truetype("DejaVuSans.ttf", 10)
            fb = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        except Exception:
            f = fb = ImageFont.load_default()
    col = {"Excel": "#1d6f42", "Excel (alt)": "#1d6f42", "Word": "#2b579a", "Word (alt)": "#2b579a", "E-Mail": "#6b4fd8",
           "Outlook-Mail": "#0072c6", "OpenOffice Text": "#3a7fc4", "OpenOffice Tabelle": "#43a047", "ZIP-Archiv": "#8a6d3b"}.get(fmt, "#6c6880")
    dr.rectangle([0, 0, 300, 44], fill=col)
    dr.text((12, 10), fmt[:22], fill="white", font=fb)
    if locked:
        dr.rectangle([110, 150, 190, 230], outline="#b08a2e", width=6)
        dr.arc([122, 100, 178, 170], 180, 360, fill="#b08a2e", width=8)
        dr.text((150, 250), "Passwortgeschützt", fill="#7a6020", font=fb, anchor="mt")
    else:
        y = 54
        for ln in (text or "").split("\n"):
            ln = ln.replace("\t", "  ").strip()
            if not ln:
                continue
            dr.text((10, y), ln[:52], fill="#333", font=f)
            y += 14
            if y > 390:
                break
    b = io.BytesIO()
    im.save(b, "JPEG", quality=85)
    return b.getvalue()


# ---------------- Kontostand ----------------
SALDO_RE = re.compile(r"(neuer kontostand|neuer saldo|kontostand am|endsaldo|schlusssaldo|saldo neu|kontostand|saldo)[^\n\d]{0,60}?"
                      r"(\d{1,2}\.\d{1,2}\.\d{2,4})?[^\n\d+-]{0,160}([+-]?\s?\d{1,3}(?:\.\d{3})*,\d{2})\s?(-|\+|S\b|H\b)?", re.I)


def saldo_from_text(text):
    best = None
    last = None
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:uhr)?", " ", text or "", flags=re.I)
    for m in SALDO_RE.finditer(text):
        if re.search(r"alter|vortrag|übertrag", text[max(0, m.start() - 10):m.start()].lower()):
            continue
        v = parse_amount(m.group(3).replace(" ", ""))
        if m.group(4) == "-" or m.group(4) == "S":
            v = -abs(v)
        dat = iso_from_de(m.group(2) or "")
        cand = {"saldo": round(v, 2), "datum": dat}
        if "neu" in m.group(1).lower() or "end" in m.group(1).lower() or "schluss" in m.group(1).lower():
            best = cand          # last "neuer Kontostand" wins (multi-page)
        else:
            last = cand
    res = best or last
    if res and not res.get("datum"):
        mz = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})", text)
        if mz:
            res["datum"] = iso_from_de(mz.group(2))
    return res


def saldo_from_csv(data):
    text = _decode(data)
    delim = ";" if text.count(";") >= text.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    head_best = None
    for r in rows[:15]:
        j = " ".join(r).lower()
        first = (r[0] if r else "").strip()
        if re.match(r"\d{1,2}\.\d{1,2}\.\d{2,4}$", first) or re.search(r"alter|vortrag|übertrag", j):
            continue
        if re.search(r"kontostand|saldo", j) and not re.search(r"buchung|datum.*betrag", j):
            am = re.findall(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+\.\d{2}\b", re.sub(r"\d{1,2}\.\d{1,2}\.\d{2,4}", " ", " ".join(r)))
            if am:
                ds = re.findall(r"\d{1,2}\.\d{1,2}\.\d{2,4}", " ".join(r))
                head_best = {"saldo": parse_amount(am[-1]), "datum": iso_from_de(ds[-1]) if ds else ""}
    if head_best:
        return head_best
    hi = None
    for i, r in enumerate(rows[:40]):
        low = [c.strip().lower() for c in r]
        if any(re.search(r"saldo|kontostand", c) for c in low) and any(re.search(r"datum|buchung", c) for c in low):
            hi = i
            break
    if hi is None:
        return None
    head = [c.strip().lower() for c in rows[hi]]
    cs = next(i for i, h in enumerate(head) if re.search(r"saldo|kontostand", h))
    cd = next((i for i, h in enumerate(head) if re.search(r"buchung|datum", h)), 0)
    best = None
    for r in rows[hi + 1:]:
        if len(r) <= max(cs, cd) or not r[cs].strip():
            continue
        d = _iso_any(r[cd])
        try:
            v = parse_amount(r[cs])
        except Exception:
            continue
        if d and (best is None or d >= best["datum"]):
            best = {"saldo": v, "datum": d}
    return best


def store_saldo(sal, quelle, txs=None):
    if not sal:
        return None
    dat = sal.get("datum") or (max(t["datum"] for t in txs) if txs else today())
    x("INSERT OR REPLACE INTO kontostand (datum, saldo, quelle, created) VALUES (?,?,?,?)", (dat, float(sal["saldo"]), quelle, now_iso()))
    return {"datum": dat, "saldo": float(sal["saldo"])}


def kontostand_info():
    rows = q("SELECT * FROM kontostand ORDER BY datum DESC, id DESC LIMIT 24")
    if not rows:
        return None
    cur = rows[0]
    after = q("SELECT COALESCE(SUM(betrag),0) s, COUNT(*) n FROM bank_tx WHERE datum>?", (cur["datum"],), one=True)
    return {"saldo": cur["saldo"], "datum": cur["datum"], "quelle": cur["quelle"], "verlauf": list(reversed(rows)),
            "nachher": round(after["s"], 2), "nachher_n": after["n"], "geschaetzt": round(cur["saldo"] + after["s"], 2)}


def bank_table_bytes(path, pw=None):
    """Excel bank export -> csv bytes for parse_bank_csv"""
    data, _ = office_bytes(path, pw)
    if path.lower().endswith(".xls"):
        import xlrd
        wb = xlrd.open_workbook(file_contents=data)
        sh = wb.sheet_by_index(0)
        rows = []
        for r in range(sh.nrows):
            row = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate_as_datetime(cell.value, wb.datemode).strftime("%d.%m.%Y"))
                else:
                    row.append(_cell_str(cell.value) if cell.ctype else "")
            rows.append(row)
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        rows = [[_cell_str(v) for v in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
        wb.close()
    b = io.StringIO()
    w = csv.writer(b, delimiter=";")
    for r in rows:
        w.writerow(r)
    return b.getvalue().encode("utf-8")
