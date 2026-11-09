# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m32_handy_upload  v1.0.0
# Wird vom Programmkern in dessen Namensraum geladen (gemeinsame Globals).
# Autor: T. Pfeiffer
#
# "Beleg per Handy": zweiter kleiner HTTP-Server auf 0.0.0.0 (Port einstellbar,
# Standard 8765), der NUR eine mobile Upload-Seite und einen Upload-Endpunkt
# bedient. Zugriff nur mit Zufalls-Token (secrets.token_urlsafe), Token laeuft
# nach 30 Minuten ab, danach stoppt der Server. Uploads landen wie Dateien aus
# dem Eingangsordner in der Beleg-Pruefliste (pending_belege).

import secrets

HANDY_TTL = 30 * 60
HANDY_MAX_FILES = 200
HANDY_EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".pdf", ".tif", ".tiff", ".bmp", ".gif")
HANDY = {"token": "", "ablauf": 0.0, "srv": None, "port": 0, "ip": "", "files": [], "lock": threading.Lock()}


def lan_ips():
    ips = []
    try:
        s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_.settimeout(0.5)
        s_.connect(("10.255.255.255", 1))     # no packet is sent, only selects the outgoing interface
        ips.append(s_.getsockname()[0])
        s_.close()
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            ips.append(ip)
    except Exception:
        pass
    out = []
    for ip in ips:
        if ip and not ip.startswith(("127.", "169.254.", "0.")) and ip not in out:
            out.append(ip)
    return out


def qr_svg(text, size=260):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderSVG
    w = QrCodeWidget(text)
    w.barLevel = "M"
    b = w.getBounds()
    bw, bh = b[2] - b[0], b[3] - b[1]
    d = Drawing(size, size, transform=[size / bw, 0, 0, size / bh, 0, 0])
    d.add(w)
    svg = renderSVG.drawToString(d)
    return svg[svg.find("<svg"):] if "<svg" in svg else svg


def _handy_active():
    return bool(HANDY["srv"]) and bool(HANDY["token"]) and time.time() < HANDY["ablauf"]


def handy_status():
    act = _handy_active()
    return {"aktiv": act, "rest_s": max(0, int(HANDY["ablauf"] - time.time())) if act else 0, "port": HANDY["port"],
            "url": f"http://{HANDY['ip']}:{HANDY['port']}/m/{HANDY['token']}" if act else "",
            "n": len(HANDY["files"]), "files": HANDY["files"][-30:]}


def handy_stop():
    srv = HANDY["srv"]
    HANDY.update(srv=None, token="", ablauf=0.0)
    if srv:
        def _down():
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
        threading.Thread(target=_down, daemon=True).start()
    return {"ok": True}


def _handy_watch(srv):
    while HANDY["srv"] is srv:
        if time.time() >= HANDY["ablauf"]:
            if HANDY["srv"] is srv:
                handy_stop()
            return
        time.sleep(5)


def handy_start(d=None):
    d = d or {}
    s = get_settings()
    port = int(float(s.get("handy_port") or 8765))
    ips = lan_ips()
    ip = d.get("ip") if d.get("ip") in ips else (ips[0] if ips else "")
    if not ip:
        raise ValueError("Keine Netzwerkverbindung gefunden – der PC muss im WLAN/LAN sein.")
    with HANDY["lock"]:
        if not HANDY["srv"]:
            last = None
            for p_ in range(port, port + 6):
                try:
                    srv = ThreadingHTTPServer(("0.0.0.0", p_), HandyHandler)
                    srv.daemon_threads = True
                    break
                except OSError as e:
                    last = e
                    srv = None
            if not srv:
                raise ValueError(f"Port {port} ist belegt ({last}). Bitte in den Einstellungen einen anderen Handy-Port eintragen.")
            # token/expiry must be set before the watcher thread starts (else it stops at once)
            HANDY.update(srv=srv, port=srv.server_address[1], files=[], ablauf=time.time() + HANDY_TTL)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            threading.Thread(target=_handy_watch, args=(srv,), daemon=True).start()
        HANDY.update(token=secrets.token_urlsafe(18), ablauf=time.time() + HANDY_TTL, ip=ip)
    url = f"http://{ip}:{HANDY['port']}/m/{HANDY['token']}"
    return {"ok": True, "url": url, "svg": qr_svg(url), "ips": ips, "ip": ip, "port": HANDY["port"], "rest_s": HANDY_TTL,
            "max_mb": int(float(s.get("handy_max_mb") or 25))}


def handy_store(tmp, name):
    """analyse an uploaded file and put it into the Beleg check list"""
    try:
        for res in prepare_results(analyze_any(tmp, name), tmp, name):
            TMP.pop(res.get("token"), None)
            res.pop("token", None)
            res["hint"] = ("Per Handy hochgeladen. " + (res.get("hint") or "")).strip()
            nm = res.get("filename") or name
            x("INSERT INTO pending_belege (file, name, result, created) VALUES (?,?,?,?)",
              (res["tmp"], nm, json.dumps(res, ensure_ascii=False, default=str), now_iso()))
            x("INSERT INTO eingang_log (datum, file, typ, betrag, partner, status, info) VALUES (?,?,?,?,?,?,?)",
              (now_iso(), f"Handy » {nm}", res.get("typ"), res.get("betrag") or 0, res.get("partner", ""), "prüfen",
               "Passwort nötig" if res.get("needs_password") else f"{int((res.get('confidence') or 0) * 100)} % sicher"))
        return True
    except Exception:
        traceback.print_exc()
        return False


HANDY_PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beleg senden</title>
<style>
:root{--acc:#5b3fd6;--ink:#1d1a26;--bg:#f6f4fb;--ok:#1f9d6b;--bad:#c8323c}
*{box-sizing:border-box}body{margin:0;font:18px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
.w{max-width:560px;margin:0 auto;padding:22px 18px 40px}
h1{font-size:26px;margin:6px 0 4px}p{margin:6px 0 16px;color:#555}
label.big{display:block;background:var(--acc);color:#fff;text-align:center;padding:26px 16px;border-radius:18px;font-size:22px;font-weight:600;margin:14px 0;cursor:pointer}
label.sec{background:#fff;color:var(--acc);border:2px solid var(--acc)}
input[type=file]{display:none}
.it{background:#fff;border-radius:12px;padding:12px 14px;margin:8px 0;display:flex;gap:10px;align-items:center;font-size:16px}
.it b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ok{color:var(--ok)}.bad{color:var(--bad)}
.foot{font-size:14px;color:#777;margin-top:22px}
</style></head><body><div class="w">
<h1>Beleg senden</h1>
<p>Foto von Rechnung oder Quittung machen oder PDF auswählen – es landet direkt in <b>PA Rechnung</b> unter „Belege &amp; Import“ zur Prüfung.</p>
<label class="big">📷 Foto aufnehmen<input id="cam" type="file" accept="image/*,application/pdf" capture="environment" multiple></label>
<label class="big sec">📄 Datei / PDF auswählen<input id="file" type="file" accept="image/*,application/pdf" multiple></label>
<div id="list"></div>
<div class="foot">Max. __MAX__ MB pro Datei. Der Code gilt noch bis __UNTIL__ Uhr.</div>
</div><script>
var TOK="__TOKEN__", MAX=__MAX__*1048576;
function row(n){var d=document.createElement("div");d.className="it";d.innerHTML="<b></b><span>wird gesendet …</span>";d.firstChild.textContent=n;document.getElementById("list").prepend(d);return d.lastChild;}
async function send(files){for(var i=0;i<files.length;i++){var f=files[i];var s=row(f.name||"Foto");
 if(f.size>MAX){s.textContent="zu groß";s.className="bad";continue;}
 try{var r=await fetch("/m/"+TOK+"/up",{method:"POST",headers:{"X-Filename":encodeURIComponent(f.name||"foto.jpg"),"Content-Type":f.type||"application/octet-stream"},body:f});
  var j=await r.json().catch(function(){return {};});
  if(r.ok&&j.ok){s.textContent="✓ angekommen";s.className="ok";}else{s.textContent=j.error||("Fehler "+r.status);s.className="bad";}}
 catch(e){s.textContent="keine Verbindung";s.className="bad";}}}
document.getElementById("cam").onchange=function(e){send(e.target.files);e.target.value="";};
document.getElementById("file").onchange=function(e){send(e.target.files);e.target.value="";};
</script></body></html>"""

HANDY_GONE = """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Code abgelaufen</title></head><body style="font:20px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;padding:30px;background:#f6f4fb;color:#1d1a26">
<h1 style="font-size:26px">Code abgelaufen</h1><p>Dieser QR-Code ist nicht mehr gültig. Bitte am PC in PA Rechnung unter
„Beleg per Handy“ einen neuen Code erzeugen und erneut scannen.</p></body></html>"""


def _handy_magic_ok(path):
    """v2.1.0: the content must really be a photo or a PDF (before, any file renamed via Content-Type image/jpeg landed in the list)"""
    try:
        with open(path, "rb") as f:
            h = f.read(16)
    except Exception:
        return False
    return (h.startswith((b"%PDF", b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"BM", b"II*\x00", b"MM\x00*"))
            or (h[:4] == b"RIFF" and h[8:12] == b"WEBP") or h[4:8] == b"ftyp" or b"%PDF" in h)


class HandyHandler(BaseHTTPRequestHandler):
    server_version = "PARechnungHandy/1.0"
    timeout = 60   # v2.0.6: stalled phone/LAN connections do not hold a thread forever

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

    def _tok_ok(self, tok):
        cur = HANDY["token"]
        return bool(cur) and secrets.compare_digest(tok.encode(), cur.encode()) and time.time() < HANDY["ablauf"]

    def do_GET(self):
        m = re.fullmatch(r"/m/([A-Za-z0-9_\-]{10,64})/?", urlparse(self.path).path)
        if not m:
            return self._out(404, "Nicht gefunden", "text/plain; charset=utf-8")
        if not self._tok_ok(m.group(1)):
            return self._out(403, HANDY_GONE, "text/html; charset=utf-8")
        mx = int(float(get_settings().get("handy_max_mb") or 25))
        until = datetime.datetime.fromtimestamp(HANDY["ablauf"]).strftime("%H:%M")
        html = HANDY_PAGE.replace("__TOKEN__", m.group(1)).replace("__MAX__", str(mx)).replace("__UNTIL__", until)
        return self._out(200, html, "text/html; charset=utf-8")

    def do_POST(self):
        m = re.fullmatch(r"/m/([A-Za-z0-9_\-]{10,64})/up", urlparse(self.path).path)
        if not m:
            return self._out(404, {"ok": False, "error": "Nicht gefunden"})
        if not self._tok_ok(m.group(1)):
            return self._out(403, {"ok": False, "error": "Code abgelaufen – am PC neuen QR-Code erzeugen."})
        if len(HANDY["files"]) >= HANDY_MAX_FILES:
            return self._out(429, {"ok": False, "error": "Zu viele Dateien für diesen Code."})
        mx = int(float(get_settings().get("handy_max_mb") or 25)) * 1048576
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return self._out(400, {"ok": False, "error": "Leere Datei."})
        if n > mx:
            return self._out(413, {"ok": False, "error": f"Datei zu groß (max. {mx // 1048576} MB)."})
        # v2.1.0: strip both path separators (os.path.basename only knows the local one) and control characters
        name = safe_name(re.split(r"[\\/]", unquote(self.headers.get("X-Filename") or ""))[-1].strip()) if self.headers.get("X-Filename") else "foto"
        ext = os.path.splitext(name.lower())[1]
        if ext not in HANDY_EXT:
            ct = (self.headers.get("Content-Type") or "").lower()
            ext = mimetypes.guess_extension(ct.split(";")[0].strip()) or ""
            ext = ".jpg" if ext in (".jpe", ".jfif") else ext
            if ext not in HANDY_EXT:
                return self._out(415, {"ok": False, "error": "Nur Fotos und PDFs."})
            name = os.path.splitext(name)[0] + ext
        if re.fullmatch(r"(image|foto|photo|img|dsc|pxl)?[_\-]?\d*\.\w+", name.lower()):
            name = "Handy_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + name
        tmp = _tmp_for(name)
        left = n
        with open(tmp, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left > 0 or not _handy_magic_ok(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
            if left > 0:
                return self._out(400, {"ok": False, "error": "Übertragung abgebrochen."})
            return self._out(415, {"ok": False, "error": "Nur Fotos und PDFs."})
        entry = {"name": name, "zeit": now_iso()[11:19], "groesse": n, "status": "analysiert …"}
        HANDY["files"].append(entry)

        def _work():
            entry["status"] = "in Prüfliste" if handy_store(tmp, name) else "Fehler"
        threading.Thread(target=_work, daemon=True).start()
        return self._out(200, {"ok": True})


HOOK_POST["/api/handy/start"] = lambda h, d: h._send(200, handy_start(d))
HOOK_POST["/api/handy/stop"] = lambda h, d: h._send(200, handy_stop())
HOOK_GET["/api/handy/status"] = lambda h, qs: h._send(200, handy_status())
