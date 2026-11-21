// ===========================================================================
//  WebScreen.swift - PA Schematic iOS - Oberflaeche vom PC in einem WKWebView
//  Autor: T. Pfeiffer
//
//  Bruecke zur Seite (window.webkit.messageHandlers.pa):
//    scan      Barcode oder QR-Code lesen, Antwort ueber window.paScan(key, text)
//    settings  Fenster "App und Verbindung" oeffnen
//    ready     Seite ist verbunden - Stand fuer unterwegs sichern
//    sync      Stand jetzt sichern und das Ergebnis melden
// ===========================================================================
import SwiftUI
import UIKit
import WebKit
import SafariServices

struct WebScreen: UIViewRepresentable {
    let app: AppState

    func makeCoordinator() -> Coordinator {
        Coordinator(app: app)
    }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.allowsInlineMediaPlayback = true
        cfg.preferences.javaScriptCanOpenWindowsAutomatically = true
        cfg.userContentController.add(context.coordinator, name: "pa")
        cfg.applicationNameForUserAgent = "PASchematicApp/\(APP_VERSION) (Build \(APP_BUILD))"
        let web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = context.coordinator
        web.uiDelegate = context.coordinator
        web.isOpaque = false
        web.backgroundColor = UIColor(red: 0.071, green: 0.075, blue: 0.082, alpha: 1)
        web.scrollView.backgroundColor = web.backgroundColor
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.scrollView.bounces = false
        web.allowsLinkPreview = false
        context.coordinator.web = web
        app.runJS = { [weak web] code in
            web?.evaluateJavaScript(code, completionHandler: nil)
        }
        if app.mode == .offline {
            web.loadFileURL(Offline.index, allowingReadAccessTo: Offline.dir)
        } else if let u = URL(string: app.server) {
            web.load(URLRequest(url: u, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 10))
        }
        return web
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
    }

    static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) {
        uiView.configuration.userContentController.removeScriptMessageHandler(forName: "pa")
    }

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate {
        let app: AppState
        weak var web: WKWebView?

        init(app: AppState) {
            self.app = app
        }

        // ---- Nachrichten der Seite ----
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard let body = message.body as? [String: Any], let cmd = body["cmd"] as? String else { return }
            switch cmd {
            case "scan":
                let key = (body["key"] as? String) ?? ""
                app.scanDone = { [weak self] code in
                    let js = "window.paScan && window.paScan(\(AppState.js(key)), \(AppState.js(code)))"
                    self?.web?.evaluateJavaScript(js, completionHandler: nil)
                }
                app.showScanner = true
            case "settings":
                app.showSettings = true
            case "ready":
                app.failed = nil
                app.sync(tell: false)
            case "sync":
                app.sync(tell: true)
            default:
                break
            }
        }

        // ---- Laden ----
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            if app.mode == .online { app.failed = nil }
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            if app.mode == .online { app.failed = error.localizedDescription }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            if app.mode == .online { app.failed = error.localizedDescription }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Dateien (PDF, Fotos) und Verweise nach aussen gehen in einem eigenen Blatt auf
            if navigationAction.targetFrame == nil, let u = navigationAction.request.url {
                open(u)
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let u = navigationAction.request.url { open(u) }
            return nil
        }

        private func open(_ u: URL) {
            guard let scheme = u.scheme?.lowercased(), scheme == "http" || scheme == "https" else { return }
            let vc = SFSafariViewController(url: u)
            vc.preferredControlTintColor = UIColor(red: 0.039, green: 0.518, blue: 1, alpha: 1)
            top()?.present(vc, animated: true)
        }

        // ---- Meldungen der Seite (alert, confirm, prompt) ----
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
            show(a) { completionHandler() }
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "Abbrechen", style: .cancel) { _ in completionHandler(false) })
            a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
            show(a) { completionHandler(false) }
        }

        func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
            let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
            a.addTextField { $0.text = defaultText }
            a.addAction(UIAlertAction(title: "Abbrechen", style: .cancel) { _ in completionHandler(nil) })
            a.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(a.textFields?.first?.text) })
            show(a) { completionHandler(nil) }
        }

        private func show(_ a: UIAlertController, orElse: () -> Void) {
            if let t = top() {
                t.present(a, animated: true)
            } else {
                orElse()
            }
        }

        private func top() -> UIViewController? {
            let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            var vc = scenes.flatMap { $0.windows }.first(where: { $0.isKeyWindow })?.rootViewController
            while let p = vc?.presentedViewController { vc = p }
            return vc
        }
    }
}
