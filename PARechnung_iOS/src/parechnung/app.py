# -*- coding: utf-8 -*-
# PA Rechnung - iPhone/iPad-App v1.1.0 (Programm v3.7.1)
# v1.1.0: Programm-Updates kommen beim Abgleich vom PC (starter.py) - kein neuer Bau fuer jede Programmversion.
# Startet das komplette Programm (Ordner "programm") auf dem Geraet und zeigt es im eigenen Fenster (WKWebView).
# Daten: "Dateien"-App -> Auf meinem iPhone -> PA Rechnung -> PA Rechnung Daten (Datenbank, Belege, Projekte).
# Oeffnen von PDFs/Exporten: iOS-Teilen-Blatt (Drucken, Mail, In Dateien sichern, Oeffnen in ...).
# Abgleich mit dem PC: im Programm unter "Abgleich".
# Autor: T. Pfeiffer
import builtins
import os
import threading
import traceback

import toga
from toga.style import Pack

from parechnung import starter

APP_IOS_VERSION = "1.1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "programm")


# program versions fetched from the PC (not in "Documents": must not be touched by the file sync or the Files app)
PROG_UPDATES = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "PARechnung", "programm")


class PARechnung(toga.App):
    def startup(self):
        print(f"INIT PA Rechnung iOS-App v{APP_IOS_VERSION}")
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.info = toga.Label("PA Rechnung startet …", style=Pack(margin=30, font_size=17, text_align="center"))
        self.main_window.content = toga.Box(children=[self.info], style=Pack(direction="column", align_items="center", justify_content="center", flex=1))
        self.main_window.show()
        threading.Thread(target=self._start_program, daemon=True).start()

    # ---- program in a background thread (database, modules, server on 127.0.0.1 only)
    def _start_program(self):
        try:
            docs = os.path.join(os.path.expanduser("~"), "Documents", "PA Rechnung Daten")
            os.makedirs(docs, exist_ok=True)
            os.environ["PA_RECHNUNG_DATA"] = docs
            os.environ["PA_RECHNUNG_PLATTFORM"] = "ios"
            builtins.PA_OPEN_HOOK = self._open_file
            url, info = starter.start(PROG, PROG_UPDATES)
            print("INIT Programm:", info)
            self.loop.call_soon_threadsafe(self._show, url)
        except Exception:
            err = traceback.format_exc()
            print(err)
            self.loop.call_soon_threadsafe(self._fail, err)

    def _show(self, url):
        self.web = toga.WebView(url=url, style=Pack(flex=1))
        try:
            self.web.user_agent = (self.web.user_agent or "Mozilla/5.0 (iPhone)") + " PARechnung-iOS/" + APP_IOS_VERSION
        except Exception:
            pass
        self.web.url = url
        self.main_window.content = self.web

    def _fail(self, err):
        self.info.text = "Das Programm konnte nicht starten:\n\n" + err[-1500:]

    # ---- "Oeffnen" from the program (PDF, export, beleg): share sheet with print / mail / files / open in
    def _open_file(self, path):
        if not os.path.exists(path):
            return False
        self.loop.call_soon_threadsafe(self._share, path)
        return True

    def _share(self, path):
        try:
            from rubicon.objc import ObjCClass
            NSURL = ObjCClass("NSURL")
            UIActivityViewController = ObjCClass("UIActivityViewController")
            UIApplication = ObjCClass("UIApplication")
            vc = UIActivityViewController.alloc().initWithActivityItems([NSURL.fileURLWithPath(path)], applicationActivities=None)
            root = UIApplication.sharedApplication.keyWindow.rootViewController
            while root.presentedViewController is not None:
                root = root.presentedViewController
            pop = vc.popoverPresentationController          # iPad: share sheet needs an anchor
            if pop is not None:
                pop.sourceView = root.view
                try:
                    from rubicon.objc.types import CGRect, CGPoint, CGSize
                    b = root.view.bounds
                    pop.sourceRect = CGRect(CGPoint(b.size.width / 2, 60), CGSize(1, 1))
                except Exception:
                    pass
            root.presentViewController(vc, animated=True, completion=None)
        except Exception:
            traceback.print_exc()


def main():
    return PARechnung("PA Rechnung", "de.tpfeiffer.parechnung")
