# -*- coding: utf-8 -*-
# Pfeiffer-Audio Rechnung - Modul m91_server_exklusiv (v2.1.0)
# Exklusiver Port fuer alle HTTP-Server des Programms unter Windows.
# ThreadingHTTPServer setzt allow_reuse_address (SO_REUSEADDR). Unter Windows bedeutet das:
# ein ZWEITES Programm darf denselben Port zusaetzlich belegen, ohne Fehlermeldung - Anfragen
# landen dann zufaellig bei einem der beiden. Dieses Modul ersetzt den globalen Namen
# ThreadingHTTPServer durch eine Unterklasse, die unter Windows SO_EXCLUSIVEADDRUSE setzt und
# SO_REUSEADDR weglaesst. Wer den Namen zur Laufzeit benutzt, profitiert automatisch:
#   m20 main() (Hauptserver), m32 Handy-Upload (Port-Suche greift jetzt wirklich).
# m77/m88 haben schon eigene Klassen; sie rufen ThreadingHTTPServer.server_bind(self) ueber den
# globalen Namen auf - deshalb nutzt server_bind hier KEIN super(), sondern die Basisklasse direkt.
# Das Setzen von SO_EXCLUSIVEADDRUSE steht nur noch hier (m88 hat keine eigene Kopie mehr).
# Unter Linux/macOS bleibt alles unveraendert.
# Autor: T. Pfeiffer

M91_VERSION = "1.0.0"
M91_WIN = sys.platform.startswith("win")
_M91_BASE = ThreadingHTTPServer


class M91Server(_M91_BASE):
    daemon_threads = True
    allow_reuse_address = not M91_WIN

    def server_bind(self):
        if M91_WIN and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        # explicit base call (works for instances of M77Server/M88Server too)
        _M91_BASE.server_bind(self)


ThreadingHTTPServer = M91Server


def _m91_selftest():
    err = []
    try:
        if ThreadingHTTPServer is not M91Server or not issubclass(M91Server, _M91_BASE):
            err.append("m91: Serverklasse nicht ersetzt")
        srv = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        port = srv.server_address[1]
        try:
            if M91_WIN:
                try:
                    s2 = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
                    s2.server_close()
                    err.append("m91: Port liess sich unter Windows doppelt belegen")
                except OSError:
                    pass
        finally:
            srv.server_close()
    except Exception as e:
        err.append(f"m91 Ausnahme: {e}")
    return err


HOOK_SELFTEST.append(_m91_selftest)
