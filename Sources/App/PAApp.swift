// ===========================================================================
//  PAApp.swift - PA Schematic iOS v1.0.0
//  Autor: T. Pfeiffer
//
//  Die App ist eine Huelle: Ihre Oberflaeche laedt sie vom Programm PA Schematic
//  am PC (immer derselbe Stand wie das Programm). Dazu kommt, was nur eine echte
//  App kann: Barcodes scannen, den letzten Stand ohne PC zeigen, Update pruefen.
// ===========================================================================
import SwiftUI
import UIKit

let APP_VERSION: String = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "1.0.0"
let APP_BUILD: Int = Int((Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "0") ?? 0

enum Look {
    static let bg = Color(red: 0.071, green: 0.075, blue: 0.082)
    static let panel = Color(red: 0.102, green: 0.106, blue: 0.118)
    static let raised = Color(red: 0.145, green: 0.153, blue: 0.169)
    static let line = Color(red: 0.204, green: 0.212, blue: 0.231)
    static let muted = Color(red: 0.557, green: 0.569, blue: 0.596)
    static let accent = Color(red: 0.039, green: 0.518, blue: 1.0)
}

enum Mode {
    case connect, online, offline
}

@MainActor
final class AppState: ObservableObject {
    @Published var server: String = UserDefaults.standard.string(forKey: "server") ?? ""
    @Published var mode: Mode = .connect
    @Published var failed: String? = nil
    @Published var showScanner = false
    @Published var showSettings = false
    @Published var reloadToken = 0
    @Published var offlineDate: Date? = Offline.date()
    @Published var syncing = false
    @Published var note: String? = nil
    var scanDone: ((String) -> Void)? = nil
    var runJS: ((String) -> Void)? = nil

    init() {
        mode = server.isEmpty ? .connect : .online
        // Startargument "-offline 1": gleich den gesicherten Stand zeigen (fuer Tests)
        if UserDefaults.standard.bool(forKey: "offline") && Offline.available { mode = .offline }
    }

    /// Adresse des PCs mit Schluessel, z. B. http://192.168.178.23:8765/?k=abc
    func setServer(_ text: String) -> Bool {
        let s = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let u = URL(string: s), let scheme = u.scheme?.lowercased(), scheme == "http" || scheme == "https",
              u.host != nil, AppState.key(of: s) != nil else { return false }
        server = s
        UserDefaults.standard.set(s, forKey: "server")
        failed = nil
        mode = .online
        reloadToken += 1
        return true
    }

    func disconnect() {
        server = ""
        UserDefaults.standard.removeObject(forKey: "server")
        failed = nil
        mode = .connect
    }

    func retry() {
        failed = nil
        mode = .online
        reloadToken += 1
    }

    func goOffline() {
        guard Offline.available else { return }
        failed = nil
        mode = .offline
        reloadToken += 1
    }

    static func key(of s: String) -> String? {
        guard let c = URLComponents(string: s) else { return nil }
        let k = c.queryItems?.first(where: { $0.name == "k" })?.value ?? ""
        return k.isEmpty ? nil : k
    }

    var key: String { AppState.key(of: server) ?? "" }

    /// http://host:port ohne Pfad
    var base: String {
        guard let c = URLComponents(string: server), let h = c.host else { return "" }
        let p = c.port.map { ":\($0)" } ?? ""
        return "\(c.scheme ?? "http")://\(h)\(p)"
    }

    /// Stand fuer unterwegs sichern; tell = Ergebnis in der Oberflaeche melden
    func sync(tell: Bool) {
        if syncing || mode != .online || base.isEmpty { return }
        syncing = true
        let b = base, k = key
        Task {
            var text = ""
            var bad = false
            do {
                let n = try await Offline.sync(base: b, key: k)
                text = "Stand gesichert (\(n) Dateien) - ohne PC unter App und Verbindung zu öffnen"
            } catch {
                text = "Sichern nicht gelungen: \(error.localizedDescription)"
                bad = true
            }
            self.syncing = false
            self.offlineDate = Offline.date()
            if tell {
                self.runJS?("window.paToast && window.paToast(\(AppState.js(text)), \(bad ? "true" : "false"))")
            }
        }
    }

    /// Text als JavaScript-Zeichenkette
    static func js(_ s: String) -> String {
        if let d = try? JSONSerialization.data(withJSONObject: [s]), let t = String(data: d, encoding: .utf8) {
            return String(t.dropFirst().dropLast())
        }
        return "\"\""
    }
}

@main
struct PASchematicApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}

struct RootView: View {
    @StateObject private var app = AppState()
    @StateObject private var upd = UpdateCenter()
    @Environment(\.scenePhase) private var phase

    var body: some View {
        ZStack {
            Look.bg.ignoresSafeArea()
            if app.mode == .connect {
                ConnectView()
            } else {
                WebScreen(app: app)
                    .id(app.reloadToken)
                    .ignoresSafeArea()
                if app.mode == .online, let f = app.failed {
                    FailView(text: f)
                }
            }
        }
        .environmentObject(app)
        .environmentObject(upd)
        .fullScreenCover(isPresented: $app.showScanner) {
            ScannerScreen { code in
                app.showScanner = false
                let done = app.scanDone
                app.scanDone = nil
                if let code = code { done?(code) }
            }
        }
        .sheet(isPresented: $app.showSettings) {
            SettingsView()
                .environmentObject(app)
                .environmentObject(upd)
        }
        .preferredColorScheme(.dark)
        .task {
            await upd.check(pc: app.base, key: app.key, force: false)
        }
        .onChange(of: phase) { p in
            if p == .background { app.sync(tell: false) }
        }
    }
}

// ---------------------------------------------------------------------------
// Verbinden: QR-Code am PC scannen oder Adresse eintragen
// ---------------------------------------------------------------------------
struct ConnectView: View {
    @EnvironmentObject var app: AppState
    @State private var text = ""
    @State private var wrong = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Spacer().frame(height: 30)
                Text("PA Schematic")
                    .font(.system(size: 34, weight: .bold))
                Text("Am PC in PA Schematic das Menü Handy > Handy-App verbinden öffnen. Das iPhone muss im selben WLAN sein wie der PC.")
                    .foregroundColor(Look.muted)
                Button {
                    app.scanDone = { code in
                        if !app.setServer(code) { wrong = true }
                    }
                    app.showScanner = true
                } label: {
                    Text("QR-Code am PC scannen")
                        .font(.system(size: 17, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 15)
                        .background(Look.accent)
                        .foregroundColor(.white)
                        .cornerRadius(13)
                }
                Text("Oder die Adresse aus dem Fenster am PC eintragen")
                    .font(.system(size: 14))
                    .foregroundColor(Look.muted)
                    .padding(.top, 8)
                TextField("http://192.168.178.23:8765/?k=...", text: $text)
                    .keyboardType(.URL)
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                    .padding(12)
                    .background(Look.panel)
                    .cornerRadius(11)
                    .overlay(RoundedRectangle(cornerRadius: 11).stroke(Look.line, lineWidth: 1))
                Button {
                    if !app.setServer(text) { wrong = true }
                } label: {
                    Text("Verbinden")
                        .font(.system(size: 17, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                        .background(Look.raised)
                        .foregroundColor(.white)
                        .cornerRadius(13)
                }
                if wrong {
                    Text("Das ist keine Adresse von PA Schematic. Sie beginnt mit http:// und endet mit ?k= und dem Schlüssel.")
                        .font(.system(size: 14))
                        .foregroundColor(.orange)
                }
                if Offline.available {
                    Button {
                        app.goOffline()
                    } label: {
                        VStack(spacing: 3) {
                            Text("Letzten Stand ohne PC ansehen")
                                .font(.system(size: 17, weight: .semibold))
                            Text("gesichert am \(Offline.dateText(app.offlineDate))")
                                .font(.system(size: 13))
                                .foregroundColor(Look.muted)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(Look.panel)
                        .foregroundColor(.white)
                        .cornerRadius(13)
                        .overlay(RoundedRectangle(cornerRadius: 13).stroke(Look.line, lineWidth: 1))
                    }
                    .padding(.top, 10)
                }
                Button("App und Update") { app.showSettings = true }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 14)
                Text("Version \(APP_VERSION) (Build \(APP_BUILD))")
                    .font(.system(size: 12))
                    .foregroundColor(Look.muted)
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal, 22)
            .padding(.bottom, 30)
        }
    }
}

// ---------------------------------------------------------------------------
// PC nicht erreichbar
// ---------------------------------------------------------------------------
struct FailView: View {
    @EnvironmentObject var app: AppState
    let text: String

    var body: some View {
        ZStack {
            Look.bg.ignoresSafeArea()
            VStack(spacing: 14) {
                Text("Der PC ist nicht erreichbar")
                    .font(.system(size: 22, weight: .bold))
                Text("Läuft PA Schematic am PC, ist der Zugang für das Handy offen und ist das iPhone im selben WLAN?")
                    .multilineTextAlignment(.center)
                    .foregroundColor(Look.muted)
                Text(text)
                    .font(.system(size: 13))
                    .multilineTextAlignment(.center)
                    .foregroundColor(Look.muted)
                big("Noch einmal versuchen", Look.accent) { app.retry() }
                if Offline.available {
                    big("Letzten Stand ohne PC ansehen", Look.raised) { app.goOffline() }
                    Text("gesichert am \(Offline.dateText(app.offlineDate))")
                        .font(.system(size: 13))
                        .foregroundColor(Look.muted)
                }
                big("Neu verbinden (QR-Code)", Look.raised) { app.disconnect() }
            }
            .padding(.horizontal, 26)
        }
    }

    private func big(_ title: String, _ color: Color, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 13)
                .background(color)
                .foregroundColor(.white)
                .cornerRadius(13)
        }
    }
}

// ---------------------------------------------------------------------------
// App, Verbindung und Update
// ---------------------------------------------------------------------------
struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var upd: UpdateCenter
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Verbindung")) {
                    if app.server.isEmpty {
                        Text("Nicht verbunden").foregroundColor(Look.muted)
                    } else {
                        Text(app.base).font(.system(size: 15, design: .monospaced))
                        Text(app.mode == .offline ? "Ansicht ohne PC" : (app.failed == nil ? "Verbunden" : "PC nicht erreichbar"))
                            .foregroundColor(Look.muted)
                        if app.mode == .offline {
                            Button("Wieder mit dem PC verbinden") { dismiss(); app.retry() }
                        }
                        Button("Neu verbinden (QR-Code scannen)") { dismiss(); app.disconnect() }
                    }
                }
                Section(header: Text("Stand für unterwegs"),
                        footer: Text("Die App sichert den Stand der Planung von selbst, wenn sie verbunden ist. Ohne PC lässt er sich ansehen, aber nicht ändern.")) {
                    Text(app.offlineDate == nil ? "Noch nichts gesichert" : "Gesichert am \(Offline.dateText(app.offlineDate))")
                    if app.mode == .online && app.failed == nil {
                        Button(app.syncing ? "Sichert ..." : "Jetzt sichern") { app.sync(tell: false) }
                            .disabled(app.syncing)
                    }
                    if Offline.available && app.mode != .offline {
                        Button("Stand ohne PC ansehen") { dismiss(); app.goOffline() }
                    }
                }
                Section(header: Text("App"),
                        footer: Text("Die Oberfläche kommt vom PC und hat immer den Stand des Programms. Die App selbst wird nur selten erneuert: am iPhone mit SideStore oder AltStore, am PC mit Sideloadly.")) {
                    Text("Version \(APP_VERSION) (Build \(APP_BUILD))")
                    if let r = upd.remote {
                        if upd.updateAvailable {
                            Text("Neu: Version \(r.version) (Build \(r.build)) vom \(r.date)")
                                .foregroundColor(.orange)
                            if !r.notes.isEmpty {
                                Text(r.notes).font(.system(size: 14)).foregroundColor(Look.muted)
                            }
                            Button("Mit SideStore installieren") { upd.openInStore("sidestore") }
                            Button("Mit AltStore installieren") { upd.openInStore("altstore") }
                            Button("Download-Seite öffnen") { upd.open(r.page.isEmpty ? UpdateCenter.pageURL : r.page) }
                        } else {
                            Text("Die App ist aktuell.").foregroundColor(Look.muted)
                        }
                    }
                    Button(upd.checking ? "Prüft ..." : "Nach Update suchen") {
                        Task { await upd.check(pc: app.base, key: app.key, force: true) }
                    }
                    .disabled(upd.checking)
                    if let m = upd.message {
                        Text(m).font(.system(size: 14)).foregroundColor(Look.muted)
                    }
                    Text("Signatur gültig bis: \(upd.expiryText)")
                        .font(.system(size: 14))
                        .foregroundColor(upd.expiresSoon ? .orange : Look.muted)
                }
            }
            .navigationTitle("App und Verbindung")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Fertig") { dismiss() }
                }
            }
        }
        .preferredColorScheme(.dark)
    }
}
