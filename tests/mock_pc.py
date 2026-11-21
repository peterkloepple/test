# ===========================================================================
#  mock_pc.py - PA Schematic iOS - Nachbau des Programms am PC fuer den Test im Simulator
#  Autor: T. Pfeiffer
#  Liefert die Seite der Handy-App und feste Beispieldaten (tests/mock), wie sie
#  PA Schematic im WLAN bereitstellt. Aenderungen werden nur bestaetigt.
# ===========================================================================
import http.server, json, os, sys, urllib.parse

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock")
M = json.load(open(os.path.join(D, "data.json"), encoding="utf-8"))


def okey(p):
    if "?" not in p:
        return p
    a, q = p.split("?", 1)
    q = [x for x in q.split("&") if x and not x.startswith(("v=", "k="))]
    return a + ("?" + "&".join(q) if q else "")


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def out(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        key = okey(self.path)
        if path in ("/", "/index.html"):
            self.out(200, open(os.path.join(D, "index.html"), "rb").read(), "text/html; charset=utf-8")
        elif path in ("/icon.png", "/favicon.ico"):
            self.out(200, open(os.path.join(D, "icon.png"), "rb").read(), "image/png")
        elif key in M["img"]:
            self.out(200, open(os.path.join(D, M["img"][key]), "rb").read(), "image/png")
        elif key in M["data"]:
            self.out(200, json.dumps(M["data"][key], ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        else:
            self.out(404, b'{"err": "nicht im Nachbau"}', "application/json; charset=utf-8")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        self.out(200, b'{"ok": true, "msg": "Nachbau: bestaetigt"}', "application/json; charset=utf-8")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
