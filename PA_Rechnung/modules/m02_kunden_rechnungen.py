# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m02_kunden_rechnungen
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer

# ----------------------------------------------------------------------------
# Customers / addresses
# ----------------------------------------------------------------------------

def inv_name(r):
    if r.get("customer_id"):
        c = q("SELECT firma, name, kdnr FROM customers WHERE id=?", (r["customer_id"],), one=True)
        if c:
            return c["firma"] or c["name"] or c["kdnr"]
    a = [l for l in json.loads(r.get("addr") or "[]") if not re.match(r"^(herrn?|frau|familie|firma)$", l.strip(), re.I)]
    return a[0] if a else (r.get("kdnr") or "")


def address_lines(c):
    if not c:
        return []
    out = []
    an = (c.get("anrede") or "").strip()
    if c.get("firma"):
        out.append(c["firma"])
        if c.get("name"):
            out.append((an + " " + c["name"]).strip())
    else:
        if an:
            out.append(an)
        if c.get("name"):
            out.append(c["name"])
    if c.get("strasse"):
        out.append(c["strasse"])
    po = " ".join(v for v in (c.get("plz"), c.get("ort")) if v)
    if po:
        out.append(po)
    if c.get("land") and c["land"] not in ("DE", "Deutschland", ""):
        out.append(c["land"])
    return out

# ----------------------------------------------------------------------------
# Invoices
# ----------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# v3.0.0: document chain ("Rechnungs-Kette")
# Later modules no longer replace save_invoice & co. with hidden wrappers. They register a step:
#     @chain_step("save_invoice", "m62_schriften")
#     def _m62_step_save_invoice(_next, d, bump=True): ... res = _next(d, bump) ...
# Steps run in load order of the modules, the last registered step is the outermost (same order as before).
# chain_info() lists all steps (Systempruefung / diagnosis).
# ---------------------------------------------------------------------------
CHAIN_NAMES = ("get_invoice", "save_invoice", "lock_invoice", "storno_invoice", "convert_doc", "fill_placeholders", "render_invoice_pdf")


class _ChainSeg:
    """one chain: base function + steps in registration order; .call = composed function"""
    __slots__ = ("name", "base", "steps", "call", "nr")

    def __init__(self, name, base, nr):
        self.name, self.base, self.steps, self.nr = name, base, [], nr
        self.call = base

    def build(self):
        f = self.base
        for _mod, step in self.steps:
            f = (lambda st, nx: (lambda *a, **k: st(nx, *a, **k)))(step, f)
        self.call = f


CHAINS = {}          # name -> list of segments (normally one; a new one starts when a module replaced the function by hand)


def _chain_entry(seg):
    def entry(*a, **k):
        return seg.call(*a, **k)
    entry.__name__ = seg.name
    entry.__qualname__ = seg.name
    entry._chain = seg
    return entry


def _chain_start(name):
    g = globals()
    segs = CHAINS.setdefault(name, [])
    seg = _ChainSeg(name, g[name], len(segs) + 1)
    segs.append(seg)
    g[name] = _chain_entry(seg)
    return seg


def chain_step(name, module):
    """decorator: register a step around the function <name> of the shared namespace
    (replaces the former "_orig = f; def f(...)" wrappers - same order: last registered = outermost)"""
    g = globals()
    if not callable(g.get(name)):
        raise KeyError(f"unbekannte Funktion {name}")
    cur = getattr(g[name], "_chain", None)
    seg = cur if (cur is not None and cur.name == name) else _chain_start(name)

    def deco(fn):
        seg.steps.append((module, fn))
        seg.build()
        return fn
    return deco


def chain_inner(name, module):
    """the chain below the step of <module> (what "_orig" meant for wrappers that also call the inner level directly).
    The segment is looked up by the module, not via the current global (a cache layer may sit on top of the chain)."""
    memo = {}

    def inner(*a, **k):
        segs = CHAINS.get(name) or []
        seg = next((sg for sg in segs if any(m == module for m, _f in sg.steps)), segs[-1] if segs else None)
        if seg is None:
            return globals()[name](*a, **k)
        key = (id(seg), len(seg.steps))
        f = memo.get(key)
        if f is None:
            idx = next((i for i, (m, _f) in enumerate(seg.steps) if m == module), len(seg.steps))
            f = seg.base
            for _mod, step in seg.steps[:idx]:
                f = (lambda st, nx: (lambda *a2, **k2: st(nx, *a2, **k2)))(step, f)
            memo.clear()
            memo[key] = f
        return f(*a, **k)
    inner.__name__ = f"{name}_unter_{module}"
    return inner


def chain_info():
    out = {}
    for n, segs in CHAINS.items():
        lst = []
        for seg in segs:
            bm = getattr(getattr(seg.base, "__code__", None), "co_filename", "") or ""
            bm = os.path.basename(bm).replace(".py", "") or "Kern"
            lst.append(f"{bm} (Basis)")
            lst += [m for m, _f in seg.steps]
        cur = globals().get(n)
        if getattr(cur, "_chain", None) is not segs[-1]:
            fm = os.path.basename(getattr(getattr(cur, "__code__", None), "co_filename", "") or "").replace(".py", "") or "?"
            lst.append(f"{fm} (ersetzt die Funktion, ruft die Kette selbst auf)")
        out[n] = lst
    return out


def get_invoice(iid):
    inv = q("SELECT * FROM invoices WHERE id=?", (iid,), one=True)
    if not inv:
        return None
    inv["addr"] = json.loads(inv["addr"] or "[]")
    inv["items"] = q("SELECT * FROM items WHERE invoice_id=? ORDER BY pos", (iid,))
    inv["attachments"] = q("SELECT id, partner, file, typ, datum FROM belege WHERE invoice_id=? AND typ='anlage'", (iid,))
    inv["mahnungen"] = q("SELECT * FROM mahnungen WHERE invoice_id=? ORDER BY stufe", (iid,))
    inv["mails"] = q("SELECT * FROM mail_log WHERE doc_id=? ORDER BY id DESC", (iid,))
    inv["ref"] = q("SELECT id, nr, typ FROM invoices WHERE id=?", (inv["ref_id"],), one=True) if inv.get("ref_id") else None
    inv["children"] = q("SELECT id, nr, typ, status FROM invoices WHERE ref_id=?", (iid,))
    return inv


def next_doc_nr(typ, s=None):
    s = s or get_settings()
    key = DOC_TYPES.get(typ, DOC_TYPES["rechnung"])["series"]
    nr = s[key]
    while q("SELECT id FROM invoices WHERE nr=?", (nr,), one=True):
        nr = inc_number(nr)
    return key, nr


# v2.1.0: number allocation, cancellation and conversion are serialized - two parallel requests
# (double click, scheduler thread, phone app) gave the same number (UNIQUE error) or two
# cancellations / two invoices for one document. Own lock, so DB reads are not blocked.
DOC_LOCK = threading.RLock()


def save_invoice(d, bump=True):
    with DOC_LOCK:
        return _save_invoice_locked(d, bump)


def _save_invoice_locked(d, bump=True):
    s = get_settings()
    typ = d.get("typ") or "rechnung"
    iid = d.get("id")
    if iid:
        old = q("SELECT locked, typ, status FROM invoices WHERE id=?", (iid,), one=True)
        if old and old["locked"] and not d.get("_force"):
            raise ValueError("Diese Rechnung ist festgeschrieben (versendet, bezahlt oder als PDF ausgegeben). "
                             "Korrekturen bitte über „Stornieren“ und eine neue Rechnung.")
    items = d.get("items") or []
    for it in items:
        it["total"] = line_total(it)
    summe = round(sum(it["total"] for it in items), 2)
    nr = (d.get("nr") or "").strip()
    status = d.get("status") or "offen"
    if status == "entwurf" and not nr:
        nr = "E-" + uuid.uuid4().hex[:6].upper()
    if nr.startswith("E-") and d.get("finalize"):
        nr = ""
        status = "offen"
    key = None
    if not nr:
        key, nr = next_doc_nr(typ, s)
    dup = q("SELECT id FROM invoices WHERE nr=?", (nr,), one=True)
    if dup and dup["id"] != iid:
        raise ValueError(f"Nummer {nr} ist schon vergeben.")
    vals = (nr, d.get("customer_id"), d.get("project_id"), d.get("kdnr", ""),
            json.dumps(d.get("addr") or [], ensure_ascii=False), d.get("datum") or today(),
            d.get("liefer") or "", d.get("auftrag") or "", d.get("titel", DOC_TYPES.get(typ, {}).get("title", "Rechnung")),
            d.get("toptext", ""), d.get("foottext", ""), d.get("zahlart", "Ueberweisung"),
            int(d.get("frist")) if str(d.get("frist", "")).strip() not in ("", "None") else 7, status, d.get("bezahlt_am") or "",
            summe, d.get("notiz", ""), d.get("source", "app"), typ, d.get("ref_id"), d.get("gueltig_bis") or "")
    if iid:
        x("UPDATE invoices SET nr=?, customer_id=?, project_id=?, kdnr=?, addr=?, datum=?, liefer=?, auftrag=?, titel=?, "
          "toptext=?, foottext=?, zahlart=?, frist=?, status=?, bezahlt_am=?, summe=?, notiz=?, source=?, typ=?, ref_id=?, "
          "gueltig_bis=?, updated=? WHERE id=?", vals + (now_iso(), iid))
        x("DELETE FROM items WHERE invoice_id=?", (iid,))
    else:
        iid = x("INSERT INTO invoices (nr, customer_id, project_id, kdnr, addr, datum, liefer, auftrag, titel, toptext, "
                "foottext, zahlart, frist, status, bezahlt_am, summe, notiz, source, typ, ref_id, gueltig_bis, created, updated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals + (now_iso(), now_iso()))
    if bump and key:
        set_setting(key, inc_number(nr))
    elif bump and not nr.startswith("E-"):
        k2 = DOC_TYPES.get(typ, DOC_TYPES["rechnung"])["series"]
        try:
            if re.sub(r"\D", "", nr) and int(re.sub(r"\D", "", nr)) >= int(re.sub(r"\D", "", s[k2])):
                set_setting(k2, inc_number(nr))
        except Exception:
            pass
    for i, it in enumerate(items):
        x("INSERT INTO items (invoice_id, pos, qty, nr, name, descr, price, rabatt, total, article_id, entry_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          (iid, i + 1, float(it.get("qty") or 0), it.get("nr", ""), it.get("name", ""), it.get("descr", ""),
           float(it.get("price") or 0), float(it.get("rabatt") or 0), it["total"], it.get("article_id"), it.get("entry_id")))
    # v2.6.3: "id NOT IN (NULL)" is never true - with an empty list nothing was released
    keep = [int(it["entry_id"]) for it in items if it.get("entry_id")]
    if keep:
        x(f"UPDATE project_entries SET invoice_id=NULL WHERE invoice_id=? AND id NOT IN ({','.join('?' * len(keep))})", [iid] + keep)
    else:
        x("UPDATE project_entries SET invoice_id=NULL WHERE invoice_id=?", (iid,))
    if d.get("lesson_ids") is not None:
        lk = [int(v) for v in (d.get("lesson_ids") or [])]
        if lk:
            x(f"UPDATE lessons SET invoice_id=NULL WHERE invoice_id=? AND id NOT IN ({','.join('?' * len(lk))})", [iid] + lk)
        else:
            x("UPDATE lessons SET invoice_id=NULL WHERE invoice_id=?", (iid,))
    if typ in ("rechnung", "storno") and status != "entwurf":
        for eid in {it.get("entry_id") for it in items if it.get("entry_id")}:
            x("UPDATE project_entries SET invoice_id=? WHERE id=? AND invoice_id IS NULL", (iid, eid))
        for lid in d.get("lesson_ids") or []:
            x("UPDATE lessons SET invoice_id=? WHERE id=? AND invoice_id IS NULL", (iid, lid))
    elif d.get("lesson_ids") and not (d.get("notiz") or "").strip():   # v2.0.6: never overwrite a user note
        x("UPDATE invoices SET notiz=? WHERE id=?", (json.dumps({"lesson_ids": d["lesson_ids"]}), iid))
    # accepted offer sets project budget
    if typ == "angebot" and d.get("project_id"):
        pr = q("SELECT budget FROM projects WHERE id=?", (d["project_id"],), one=True)
        if pr and not pr["budget"]:
            x("UPDATE projects SET budget=? WHERE id=?", (summe, d["project_id"]))
    return iid, nr


def lock_invoice(iid):
    x("UPDATE invoices SET locked=1 WHERE id=? AND typ IN ('rechnung','storno') AND status!='entwurf'", (iid,))


def storno_invoice(iid):
    with DOC_LOCK:
        return _storno_invoice_locked(iid)


def _storno_invoice_locked(iid):
    inv = get_invoice(iid)
    if not inv or inv["typ"] != "rechnung":
        raise ValueError("Nur Rechnungen können storniert werden.")
    if inv["storno_von"]:
        raise ValueError("Diese Rechnung ist bereits storniert.")
    if inv["status"] == "entwurf":
        raise ValueError("Entwürfe einfach löschen statt stornieren.")
    s = get_settings()
    paid = inv["status"] == "bezahlt"
    items = [{"qty": -float(it["qty"]), "nr": it["nr"], "name": it["name"], "descr": it["descr"], "price": it["price"],
              "rabatt": it["rabatt"]} for it in inv["items"]]
    d = {"typ": "storno", "customer_id": inv["customer_id"], "project_id": inv["project_id"], "kdnr": inv["kdnr"],
         "addr": inv["addr"], "datum": today(), "liefer": inv["liefer"], "auftrag": inv["auftrag"],
         "titel": f"Storno-Rechnung zu {inv['nr']}",
         "toptext": f"Hiermit stornieren wir die Rechnung {inv['nr']} vom {de_date(inv['datum'])} in voller Höhe.",
         "foottext": ("Der bereits gezahlte Betrag wird Ihnen erstattet. " if paid else "Die ursprüngliche Rechnung ist damit gegenstandslos. ") + s["default_foot"],
         "zahlart": "Bar", "frist": 0, "status": "offen" if paid else "storniert", "items": items, "ref_id": iid}
    sid, snr = save_invoice(d)
    lock_invoice(sid)
    x("UPDATE invoices SET storno_von=?, locked=1, status=? WHERE id=?", (sid, "bezahlt" if paid else "storniert", iid))
    x("UPDATE project_entries SET invoice_id=NULL WHERE invoice_id=?", (iid,))
    x("UPDATE lessons SET invoice_id=NULL WHERE invoice_id=?", (iid,))
    return sid, snr


# v2.1.0: allowed conversions - before, "storno" created a cancellation with POSITIVE amounts
# (original not marked) and an invoice could be copied into a second invoice with ref_id
CONVERT_OK = {"angebot": ("auftrag", "rechnung"), "auftrag": ("rechnung",)}


def convert_doc(iid, to_typ):
    with DOC_LOCK:
        return _convert_doc_locked(iid, to_typ)


def _convert_doc_locked(iid, to_typ):
    src = get_invoice(iid)
    if not src:
        raise ValueError("Dokument nicht gefunden.")
    if to_typ not in CONVERT_OK.get(src.get("typ") or "rechnung", ()):
        raise ValueError(f"{DOC_TYPES.get(src.get('typ'), {}).get('title', 'Dieses Dokument')} kann nicht in "
                         f"{DOC_TYPES.get(to_typ, {}).get('title', to_typ)} umgewandelt werden.")
    ex = q("SELECT nr FROM invoices WHERE ref_id=? AND typ=?", (iid, to_typ), one=True)
    if ex:
        raise ValueError(f"Daraus wurde bereits {DOC_TYPES[to_typ]['title']} {ex['nr']} erstellt.")
    s = get_settings()
    d = {k: src[k] for k in ("customer_id", "project_id", "kdnr", "addr", "liefer", "auftrag", "zahlart", "frist")}
    d.update(typ=to_typ, ref_id=iid, datum=today(), status="offen",
             items=[{k: it[k] for k in ("qty", "nr", "name", "descr", "price", "rabatt", "article_id", "entry_id")} for it in src["items"]])
    lbl = DOC_TYPES[to_typ]["title"]
    d["titel"] = re.sub(r"^(Angebot|Auftragsbestätigung|Rechnung)", lbl, src["titel"] or lbl) if src["titel"] else lbl
    if to_typ == "rechnung":
        d["toptext"], d["foottext"] = s["default_top"], s["default_foot"]
        d["auftrag"] = src["datum"]
    else:
        d["toptext"], d["foottext"] = s.get("default_top_" + to_typ, ""), s.get("default_foot_" + to_typ, "")
    nid, nnr = save_invoice(d)
    if src["typ"] == "angebot":
        x("UPDATE invoices SET status='angenommen' WHERE id=?", (iid,))
    elif src["typ"] == "auftrag" and to_typ == "rechnung":
        x("UPDATE invoices SET status='erledigt' WHERE id=?", (iid,))
    return nid, nnr


def fill_placeholders(text, inv, summe):
    frist = int(inv.get("frist")) if str(inv.get("frist", "")).strip() not in ("", "None") else 7
    try:
        dd = datetime.date.fromisoformat(inv.get("datum") or today())
    except Exception:
        dd = datetime.date.today()
    fdate = (dd + datetime.timedelta(days=frist)).strftime("%d.%m.%Y")
    gb = inv.get("gueltig_bis") or ""
    return (text or "").replace("[Frist]", str(frist)).replace("[Zahlungsfrist]", fdate) \
        .replace("[Rechnungsnummer]", inv.get("nr", "")).replace("[Nummer]", inv.get("nr", "")) \
        .replace("[Betrag]", money(summe)).replace("[Gueltig]", de_date(gb)).replace("[Gültig]", de_date(gb)) \
        .replace("[Mahnfrist]", de_date(inv.get("_mahnfrist") or ""))

# ----------------------------------------------------------------------------
# Invoice PDF (layout follows the original template)
# ----------------------------------------------------------------------------
GRAY = colors.HexColor("#777777")
LINE = colors.HexColor("#222222")


def epc_payload(s, amount, ref):
    return "\n".join(["BCD", "002", "1", "SCT", s.get("bic", ""), (s.get("kontoinhaber") or s.get("inhaber", ""))[:70],
                      re.sub(r"\s", "", s.get("iban", "")), f"EUR{amount:.2f}", "", "", ref[:140]])


def fmt_iban(iban):
    i = re.sub(r"\s", "", iban or "")
    return " ".join(i[k:k + 4] for k in range(0, len(i), 4))


def _pdf_wrap(text, font, size, width):
    """simpleSplit + hard break of single words that are wider than the column (v2.1.0: long URLs,
    part numbers or names without spaces ran over the price columns)"""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    out = []
    for ln in simpleSplit(text or "", font, size, width):
        while len(ln) > 1 and stringWidth(ln, font, size) > width + 0.01:
            k = len(ln) - 1
            while k > 1 and stringWidth(ln[:k], font, size) > width:
                k -= 1
            out.append(ln[:k])
            ln = ln[k:]
        out.append(ln)
    return out


def _pdf_fit(text, font, size, maxw, minsize=6.0):
    """font size so that text fits into maxw (v2.1.0: long numbers ran out of the boxes)"""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    w = stringWidth(text or "", font, size)
    if w <= maxw or w <= 0:
        return size
    return max(minsize, size * maxw / w)


def _money_price(v, fmt=None):
    """unit price: 2 decimals, up to 4 if the price has them (0,335 EUR was shown as 0,34 EUR -
    qty x shown price did not match the line total). fmt = money formatter of the caller (m82 swaps
    it for foreign currencies), the extra decimals are put into its 2-decimal output."""
    fmt = fmt or money
    v = float(v or 0)
    r = round(v, 4)
    if abs(r - round(v, 2)) < 1e-9:
        return fmt(v)
    ip = math.floor(abs(r))
    frac = f"{abs(r):.4f}".split(".")[1].rstrip("0")
    m = re.match(r"^(.*\d[.,])00(\D*)$", fmt(float(ip)))
    if not m:
        return fmt(v)
    out = m.group(1) + frac + m.group(2)
    return ("-" + out) if r < 0 and not out.startswith("-") else out


def draw_qr(c, data, x0, top, size, H):
    w = QrCodeWidget(data)
    w.barLevel = "M"
    b = w.getBounds()
    bw, bh = b[2] - b[0], b[3] - b[1]
    dr = Drawing(size, size, transform=[size / bw, 0, 0, size / bh, 0, 0])
    dr.add(w)
    renderPDF.draw(dr, c, x0, H - top - size)


# v3.0.0: render context for the invoice PDF. Default = German / EUR. m82 (international) puts its formatter set
# into RENDER_TL.fmt for the duration of one render call (English texts, foreign currency, no EPC QR code).
RENDER_TL = threading.local()
RENDER_FMT_DE = {"L": lambda s_: s_, "money": lambda *a, **k: money(*a, **k), "num": lambda *a, **k: num_de(*a, **k),
                 "date": lambda *a, **k: de_date(*a, **k), "fill": None, "cur": lambda: "EUR"}


def render_invoice_pdf(inv, s=None, attachments=True):
    # v3.0.0: language / currency / VAT block are native here (before: m80 and m82 rebuilt this function from its source text).
    # The formatter set comes from the render context (m82 sets it for English / foreign currency documents),
    # default = German / EUR - exactly the former behaviour.
    _F = getattr(RENDER_TL, "fmt", None) or RENDER_FMT_DE
    L, _rf_money, _rf_num, _rf_date = _F["L"], _F["money"], _F["num"], _F["date"]
    _rf_fill = _F["fill"] or fill_placeholders
    _rf_cur = _F["cur"]()
    s = s or get_settings()
    buf = io.BytesIO()
    W, H = A4
    c = rl_canvas.Canvas(buf, pagesize=A4)
    typ = inv.get("typ") or "rechnung"
    if str(inv.get("nr") or "").startswith("E-"):
        inv = dict(inv, nr="ENTWURF")
    dt = DOC_TYPES.get(typ, DOC_TYPES["rechnung"])
    nrlabel = inv.get("_nrlabel") or L(dt["nrlabel"])
    c.setTitle(f"{L(inv.get('_doctitle') or dt['title'])} {inv.get('nr', '')}")
    c.setAuthor(s.get("inhaber", ""))
    c.setCreator(f"{APP_NAME} v{APP_VERSION}")
    items = inv.get("items") or []
    for it in items:
        it["total"] = item_total(inv, it)
    summe = round(sum(it["total"] for it in items), 2)
    _m80b = m80_ust_block(inv) if (inv.get("_m80") and "m80_ust_block" in globals()) else None
    if _m80b:
        summe = _m80b["brutto"]

    def T(x0, base, text, size=10, bold=False, align="l", col=colors.black, font=None):
        c.setFillColor(col)
        f = font or (FONT_B() if bold else FONT_R())
        c.setFont(f, size)
        y = H - base
        if align == "r":
            c.drawRightString(x0, y, text)
        elif align == "c":
            c.drawCentredString(x0, y, text)
        else:
            c.drawString(x0, y, text)

    def hline(x1, x2, top, w=0.6, col=LINE):
        c.setStrokeColor(col)
        c.setLineWidth(w)
        c.line(x1, H - top, x2, H - top)

    has_rab = any(float(it.get("rabatt") or 0) for it in items)
    dec_qty = any(abs(float(it.get("qty") or 0) - round(float(it.get("qty") or 0))) > 1e-9 for it in items)
    # v2.1.0: 3 decimals when a quantity has them (0,125 t was printed as 0,13 - qty x price did not match)
    qd = 3 if any(abs(float(it.get("qty") or 0) - round(float(it.get("qty") or 0), 2)) > 1e-9 for it in items) else 2
    if has_rab:
        col = dict(pos=79.5, qty=177.5, nr=190, de=235, dew=128, price=422, rab=472.7, tot=552.9)
    else:
        col = dict(pos=78.5, qty=175.6, nr=188, de=230, dew=180, price=477.9, rab=None, tot=552.9)

    def table_header(top):
        hline(56, 553, top - 16)
        b = top
        T(58 if not has_rab else 59, b, L('Pos.'))
        T(col["qty"], b, L('Anzahl'), align="r")
        T(col["nr"], b, L('Artikel'))
        T(col["de"], b, L('Beschreibung'))
        T(col["price"], b, L('Preis'), align="r")
        if has_rab:
            T(col["rab"], b, L('Rabatt'), align="r")
        T(col["tot"], b, L('Gesamtpreis'), align="r")
        hline(56, 553, top + 6)

    def footer():
        hline(56.7, 552.8, 789.5, 0.6)
        cols = [(56, s.get("fuss1", ""), "l"), (174, s.get("fuss2", ""), "l"),
                (307, s.get("fuss3", ""), "l"), (552.8, s.get("fuss4", ""), "r")]
        for x0, txt, al in cols:
            for k, ln in enumerate((txt or "").split("\n")[:4]):
                T(x0, 803 + 8 * k, ln, size=7, align=al)

    # pre-layout items into lines
    blocks = []
    for i, it in enumerate(items):
        lines = [("b", l) for l in _pdf_wrap(it.get("name") or "", FONT_B(), 10, col["dew"])] or [("b", "")]
        for para in (it.get("descr") or "").split("\n"):
            if para.strip() == "":
                continue
            lines += [("n", l) for l in _pdf_wrap(para, FONT_R(), 10, col["dew"])]
        # article no.: smaller font if needed, very long numbers wrap inside their column (v2.1.0)
        anr, nrw = str(it.get("nr") or ""), col["de"] - col["nr"] - 4
        fs = _pdf_fit(anr, FONT_R(), 10, nrw, 7.0)
        nrl = [(anr, fs)] if c.stringWidth(anr, FONT_R(), fs) <= nrw + 0.01 else [(l, 7.0) for l in _pdf_wrap(anr, FONT_R(), 7.0, nrw)]
        blocks.append((i, it, lines, nrl))

    page = 1
    ITEM_LIMIT = 612
    _pgno = [page]

    def _new_page():
        # continuation page: footer, new page with company + number + page no.; returns the next free y
        footer()
        c.showPage()
        _pgno[0] += 1
        T(557.3, 60, s.get("firma", ""), size=12, bold=True, align="r")
        T(56, 60, f"{nrlabel} {inv.get('_nrvalue') or inv.get('nr', '')}  ·  {L('Seite')} {_pgno[0]}", size=10, col=GRAY)
        return 100

    def first_page_head():
        logo = s.get("logo") or ""
        lp = os.path.join(ASSET_DIR, logo)
        if logo and os.path.exists(lp):
            try:
                img = ImageReader(lp)
                iw, ih = img.getSize()
                bw, bh = 65.5, 99.0
                sc = min(bw / iw, bh / ih)
                dw, dh = iw * sc, ih * sc
                c.drawImage(img, 481.6 + (bw - dw) / 2, H - 20 - dh, dw, dh, mask="auto")
            except Exception:
                pass
        T(557.3, 139.0, s.get("firma", ""), size=12, bold=True, align="r")
        snd = s.get("absender", "")
        T(56, 157.0, snd, size=8)
        sw = c.stringWidth(snd, FONT_R(), 8)
        hline(56, 56 + sw, 158.4, 0.5, colors.black)
        for k, ln in enumerate((inv.get("addr") or [])[:7]):
            T(56, 181.0 + 13 * k, ln, size=11)
        if inv.get("_meta"):
            meta = [(L(_a), _b) for _a, _b in inv["_meta"]] + [(nrlabel, inv.get("_nrvalue") or inv.get("nr", ""))]
        elif typ == "angebot":
            meta = [(L('Datum'), _rf_date(inv.get("datum"))), (L('Gültig bis'), _rf_date(inv.get("gueltig_bis"))), (L('Seite'), "1"),
                    (L('Kunden-Nr.'), inv.get("kdnr", "")), (nrlabel, inv.get("nr", ""))]
        else:
            meta = [(L('Lieferdatum'), _rf_date(inv.get("liefer"))), (L('Auftragsdatum'), _rf_date(inv.get("auftrag"))),
                    (L('Seite'), "1"), (L('Datum'), _rf_date(inv.get("datum"))), (L('Kunden-Nr.'), inv.get("kdnr", "")),
                    (nrlabel, inv.get("nr", ""))]
        meta = [m for m in meta if m[1] or m[0] not in (L('Lieferdatum'), L('Auftragsdatum'), L('Kunden-Nr.'), L('Gültig bis'))]
        bases = [182, 195, 209, 222, 236, 250][-len(meta):]
        for (lbl, val), b in zip(meta, bases):
            last = lbl == nrlabel
            if last:
                c.setFillColor(colors.HexColor(s.get("highlight") or "#fbe3e3"))
                c.rect(487.5, H - 253, 63, 14.5, stroke=0, fill=1)
            T(393, b, lbl, size=11, bold=last)
            val = str(val or "")
            T(489, b, val, size=_pdf_fit(val, FONT_B() if last else FONT_R(), 11, 68), bold=last)
        top = 304
        if inv.get("titel"):
            T(56, top, inv["titel"], size=12, bold=True)
        tt = _rf_fill(inv.get("toptext", ""), inv, summe)
        ty = 329
        for para in tt.split("\n"):
            for ln in _pdf_wrap(para, FONT_R(), 10, 497):
                if ty > 772:         # v2.1.0: very long header text continues on the next page (ran into the footer)
                    ty = _new_page() + 10
                T(56, ty, ln, size=10)
                ty += 12
        return max(363, ty + 22) if _pgno[0] == 1 else ty + 22

    hb = first_page_head()
    if hb + 34 > ITEM_LIMIT:
        hb = _new_page() + 30      # v2.1.0: no room left for the table below the header text
    table_header(hb)
    y = hb + 23
    run = 0.0

    def _carry(run_):
        T(460, 640, L('Übertrag:'), size=10, bold=True, align="r")
        T(552.9, 640, _rf_money(run_), size=10, bold=True, align="r")
        _new_page()
        T(56, 100, L('Übertrag'), size=10, bold=True)
        T(552.9, 100, _rf_money(run_), size=10, bold=True, align="r")
        table_header(130)
        return 153

    for bi, (i, it, lines, nrl) in enumerate(blocks):
        need = 11 * max(len(lines), len(nrl))
        if y + need > ITEM_LIMIT and bi > 0:
            y = _carry(run)
        pg0 = _pgno[0]
        q_ = float(it.get("qty") or 0)
        qs = _rf_num(q_, qd) if dec_qty else (str(int(round(q_))) if abs(q_ - round(q_)) < 1e-9 else _rf_num(q_, qd))
        T(col["pos"], y, str(i + 1), align="r")
        T(col["qty"], y, qs, align="r")
        for k, (nl, nfs) in enumerate(nrl):
            T(col["nr"], y + 11 * k, nl, size=nfs)
        T(col["price"], y, _money_price(it.get("price"), lambda v_: _rf_money(v_)), align="r")
        if has_rab:
            r = float(it.get("rabatt") or 0)
            T(col["rab"], y, (_rf_num(r, 2) + " %") if r else "", align="r")
        T(col["tot"], y, _rf_money(it["total"]), align="r")
        yy = y
        for kind, ln in lines:
            if yy > ITEM_LIMIT:      # v2.0.6: very long description continues on the next page
                yy = _carry(run + it["total"])   # item total already printed on the previous page
            T(col["de"], yy, ln, bold=(kind == "b"))
            yy += 11
        run += it["total"]
        y = (max(yy, y + 11 * len(nrl)) if _pgno[0] == pg0 else yy) + 11

    # totals block
    za = inv.get("zahlart") or "Ueberweisung"
    hline(344, 553, 630.5, 0.6)
    if _m80b:
        _yy = 644.0
        T(376, _yy, L('Nettobetrag:'), size=10)
        T(552.7, _yy, _rf_money(_m80b["netto"]), size=10, align="r")
        for _r in _m80b["saetze"][:4]:
            _yy += 12.5
            T(376, _yy, (L('zzgl. USt ') + _m80_pct(_r["satz"]) + ":") if _r["satz"] else L('USt 0 %:'), size=10)
            T(552.7, _yy, _rf_money(_r["ust"]), size=10, align="r")
        hline(370, 553, _yy + 5, 0.4)
        T(376, _yy + 19, L('Gesamtbetrag:'), size=12, bold=True)
        T(552.7, _yy + 19, _rf_money(summe), size=12, bold=True, align="r")
    else:
        T(376, 646.3, L('Gesamtbetrag:'), size=12, bold=True)
        T(552.7, 646.3, _rf_money(summe), size=12, bold=True, align="r")
    paybox = typ in ("rechnung",) and summe > 0 and inv.get("status") != "storniert"
    if inv.get("_paybox") is not None:
        paybox = inv["_paybox"] and summe > 0
    if not paybox:
        pass
    elif za == "Ueberweisung" and s.get("iban"):
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.rect(55.5, H - 709.7, 277.5, 79.2, stroke=1, fill=0)
        T(68, 648, L('Zahlbetrag'), size=8, col=GRAY)
        T(174, 648, nrlabel, size=8, col=GRAY)
        T(68, 666, _rf_money(summe), size=13)
        pnr = str(inv.get("_nrvalue") or inv.get("nr", "") or "")
        T(174, 666, pnr, size=_pdf_fit(pnr, FONT_R(), 13, 88))
        T(68, 685, L('Unsere Bankverbindung (IBAN)'), size=8, col=GRAY)
        T(68, 703, fmt_iban(s["iban"]), size=13)
        if summe > 0 and _rf_cur == "EUR":
            draw_qr(c, epc_payload(s, summe, f"{L('Rechnung')} {inv.get('_nrvalue') or inv.get('nr', '')}"), 266, 638, 62, H)
    elif za == "PayPal":
        c.setStrokeColor(colors.HexColor("#1f73c9"))
        c.setLineWidth(0.8)
        c.rect(55.5, H - 711, 277.5, 96, stroke=1, fill=0)
        T(68, 640, "PayPal", size=17, col=colors.HexColor("#1f4f9c"), font=FONT_BI())
        T(323, 638, L('Mit einem Klick per PayPal bezahlen'), size=8.5, col=colors.HexColor("#1f73c9"), align="r")
        T(68, 671, L('Zahlbetrag:'), size=8)
        T(113, 671, _rf_money(summe), size=8)
        T(68, 680, L('Empfänger:'), size=8)
        T(113, 680, s.get("inhaber", ""), size=8)
        T(113, 690, s.get("paypal_mail", ""), size=8)
        pm = (s.get("paypal_me") or "").strip().strip("/")
        if pm:
            url = (pm if pm.startswith("http") else "https://paypal.me/" + pm) + f"/{summe:.2f}" + _rf_cur
            draw_qr(c, url, 270, 652, 54, H)
            c.linkURL(url, (55.5, H - 711, 333, H - 615), relative=0)
    ft = _rf_fill(inv.get("foottext", ""), inv, summe)
    fy = 737
    for para in ft.split("\n"):
        for ln in _pdf_wrap(para, FONT_R(), 10, 497):
            if fy > 780:         # v2.1.0: the rest goes onto an extra page (was cut off silently after 4 lines)
                fy = _new_page() + 10
            T(56, fy, ln, size=10)
            fy += 12
    footer()
    c.showPage()
    c.save()
    data = buf.getvalue()
    att = inv.get("attachments") or []
    if attachments and att and pypdf:
        try:
            w = pypdf.PdfWriter()
            for pg in pypdf.PdfReader(io.BytesIO(data)).pages:
                w.add_page(pg)
            for a in att:
                fp = os.path.join(DATA_DIR, a["file"]) if not os.path.isabs(a["file"]) else a["file"]
                if os.path.exists(fp) and fp.lower().endswith(".pdf"):
                    try:     # v2.1.0: one damaged attachment no longer drops all the others
                        for pg in pypdf.PdfReader(fp).pages:
                            w.add_page(pg)
                    except Exception:
                        traceback.print_exc()
            o = io.BytesIO()
            w.write(o)
            data = o.getvalue()
        except Exception:
            traceback.print_exc()
    return data


# v3.0.0: the base renderer without the wrappers of later modules (m82 renders foreign documents with it)
render_invoice_pdf_base = render_invoice_pdf


def pdf_to_pngs(data, scale=1.5, max_pages=8):
    out = []
    if not pdfium:
        return out
    with PDFIUM_LOCK:     # v3.6.1: pdfium is not thread safe
        doc = pdfium.PdfDocument(data)
        try:
            for i in range(min(len(doc), max_pages)):
                img = doc[i].render(scale=scale).to_pil()
                b = io.BytesIO()
                img.save(b, "PNG", optimize=False)
                out.append(b.getvalue())
        finally:
            doc.close()
    return out


def invoice_pdf_path(inv, s):
    y = (inv.get("datum") or today())[:4]
    folder = os.path.join(s.get("pdf_dir") or os.path.join(DATA_DIR, "Rechnungen"), y)
    os.makedirs(folder, exist_ok=True)
    typ = inv.get("typ") or "rechnung"
    pat = (s.get("pdf_pattern") or "rechnung_{nr}.pdf") if typ == "rechnung" else DOC_TYPES[typ]["file"]
    # v2.6.3: keep separators ("2026-001" and "20260-01" gave the same file and overwrote each other)
    fn = pat.replace("{nr}", re.sub(r"[^0-9A-Za-z._-]", "_", inv["nr"] or ""))
    return os.path.join(folder, safe_name(fn))


# v3.0.0: the document functions become chain entries (steps of later modules hook in via chain_step)
for _cn in CHAIN_NAMES:
    _chain_start(_cn)
del _cn
