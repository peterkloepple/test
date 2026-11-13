// ===========================================================================
//  Update.swift - Studio Control iOS - Update-Pruefung, Signatur-Ablauf, Sicherung
//  Autor: T. Pfeiffer
//
//  UpdateCenter  - liest version.json aus dem GitHub-Release und vergleicht die
//                  Build-Nummer mit der installierten App; liest das Ablaufdatum
//                  der Signatur (embedded.mobileprovision) und erinnert vorher.
//  SettingsBackup - alle Geraete-Einstellungen als eine JSON-Datei sichern/laden.
//  Eine iOS-App kann sich nicht selbst installieren: installiert wird weiter mit
//  Sideloadly (PC) oder mit AltStore/SideStore direkt am iPhone.
// ===========================================================================
import Foundation
import SwiftUI
import UIKit
import UserNotifications

let APP_VERSION: String = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "1.1.0"
let APP_BUILD: Int = Int((Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "0") ?? 0

struct RemoteVersion: Codable, Equatable {
    var version: String = ""
    var build: Int = 0
    var date: String = ""
    var commit: String = ""
    var notes: String = ""
    var ipa: String = ""
    var page: String = ""
    var source: String = ""

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = (try? c.decodeIfPresent(String.self, forKey: .version)) ?? ""
        build = (try? c.decodeIfPresent(Int.self, forKey: .build)) ?? 0
        date = (try? c.decodeIfPresent(String.self, forKey: .date)) ?? ""
        commit = (try? c.decodeIfPresent(String.self, forKey: .commit)) ?? ""
        notes = (try? c.decodeIfPresent(String.self, forKey: .notes)) ?? ""
        ipa = (try? c.decodeIfPresent(String.self, forKey: .ipa)) ?? ""
        page = (try? c.decodeIfPresent(String.self, forKey: .page)) ?? ""
        source = (try? c.decodeIfPresent(String.self, forKey: .source)) ?? ""
    }
}

@MainActor
final class UpdateCenter: ObservableObject {
    static let base = "https://github.com/peterkloepple/test/releases/download/studio-ios-latest/"
    static let versionURL = base + "version.json"
    static let ipaURL = base + "StudioControl_iOS.ipa"
    static let sourceURL = base + "apps.json"
    static let pageURL = "https://github.com/peterkloepple/test/releases/tag/studio-ios-latest"

    @Published var remote: RemoteVersion?
    @Published var checking = false
    @Published var lastCheck: Date?
    @Published var error: String?
    /// Ablauf der Signatur (nil = nicht signiert / Simulator / unbekannt)
    @Published var expiry: Date?
    @Published var reminderOn: Bool = UserDefaults.standard.bool(forKey: "update.reminder")
    @Published var skippedBuild: Int = UserDefaults.standard.integer(forKey: "update.skipped")
    @Published var message: String?

    init() {
        expiry = UpdateCenter.readExpiry()
        if let t = UserDefaults.standard.object(forKey: "update.lastCheck") as? Date { lastCheck = t }
        if let d = UserDefaults.standard.data(forKey: "update.remote"),
           let r = try? JSONDecoder().decode(RemoteVersion.self, from: d) {
            remote = r
        }
        if DeviceModel.demoMode {
            var r = RemoteVersion()
            r.version = APP_VERSION
            r.build = APP_BUILD + 1
            r.date = "2026-11-20 18:30"
            r.notes = "Beispiel: Fehlerkorrekturen Beamer und Mics."
            r.ipa = UpdateCenter.ipaURL
            r.page = UpdateCenter.pageURL
            remote = r
            lastCheck = Date()
            expiry = Date().addingTimeInterval(5 * 86400 + 3600)
        }
    }

    var updateAvailable: Bool {
        guard let r = remote else { return false }
        return r.build > APP_BUILD
    }

    /// Banner auf der Startseite zeigen? (nicht, wenn diese Version uebersprungen wurde)
    var showUpdateBanner: Bool {
        guard let r = remote, updateAvailable else { return false }
        return r.build != skippedBuild
    }

    var daysLeft: Int? {
        guard let e = expiry else { return nil }
        return Int(floor(e.timeIntervalSinceNow / 86400))
    }

    var expiryText: String {
        guard let e = expiry else { return "unbekannt (nicht signiert)" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "EEE dd.MM.yyyy HH:mm"
        let left = e.timeIntervalSinceNow
        if left <= 0 { return "abgelaufen (\(f.string(from: e)))" }
        let d = Int(left / 86400)
        let h = Int(left / 3600) % 24
        return "\(f.string(from: e)) (noch \(d) T \(h) h)"
    }

    /// Signatur laeuft in weniger als 2 Tagen ab?
    var expiresSoon: Bool {
        guard let e = expiry else { return false }
        return e.timeIntervalSinceNow < 2 * 86400
    }

    func skipCurrent() {
        guard let r = remote else { return }
        skippedBuild = r.build
        UserDefaults.standard.set(r.build, forKey: "update.skipped")
    }

    /// Prueft auf eine neue Version. Ohne force hoechstens alle 6 Stunden.
    func check(force: Bool = false) async {
        if DeviceModel.demoMode { return }
        if checking { return }
        if !force, let t = lastCheck, Date().timeIntervalSince(t) < 6 * 3600 { return }
        guard let url = URL(string: UpdateCenter.versionURL) else { return }
        checking = true
        defer { checking = false }
        do {
            var req = URLRequest(url: url, timeoutInterval: 12)
            req.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else { throw NetError.protocolError("keine Antwort") }
            if http.statusCode == 404 {
                throw NetError.protocolError("Noch keine Versionsdatei im Release (version.json)")
            }
            guard (200..<300).contains(http.statusCode) else {
                throw NetError.http(http.statusCode, "GitHub")
            }
            let r = try JSONDecoder().decode(RemoteVersion.self, from: data)
            remote = r
            error = nil
            lastCheck = Date()
            UserDefaults.standard.set(lastCheck, forKey: "update.lastCheck")
            UserDefaults.standard.set(data, forKey: "update.remote")
            if force {
                message = r.build > APP_BUILD
                    ? "Neue Version \(r.version) (Build \(r.build)) verfügbar."
                    : "Die App ist aktuell (Version \(APP_VERSION), Build \(APP_BUILD))."
            }
        } catch {
            self.error = DeviceModel.describe(error)
            if force { message = "Prüfung fehlgeschlagen: \(DeviceModel.describe(error))" }
        }
    }

    // ---- Signatur ----
    static func readExpiry() -> Date? {
        guard let path = Bundle.main.path(forResource: "embedded", ofType: "mobileprovision"),
              let data = FileManager.default.contents(atPath: path) else { return nil }
        guard let a = data.range(of: Data("<?xml".utf8)),
              let b = data.range(of: Data("</plist>".utf8)), a.lowerBound < b.upperBound else { return nil }
        let xml = data.subdata(in: a.lowerBound..<b.upperBound)
        guard let obj = try? PropertyListSerialization.propertyList(from: xml, options: [], format: nil),
              let dict = obj as? [String: Any] else { return nil }
        return dict["ExpirationDate"] as? Date
    }

    // ---- Erinnerung ----
    func setReminder(_ on: Bool) {
        if !on {
            reminderOn = false
            UserDefaults.standard.set(false, forKey: "update.reminder")
            UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["sig.1", "sig.2"])
            return
        }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, _ in
            Task { @MainActor in
                self.reminderOn = granted
                UserDefaults.standard.set(granted, forKey: "update.reminder")
                if granted {
                    self.scheduleReminder()
                } else {
                    self.message = "Mitteilungen sind für Studio nicht erlaubt (iOS-Einstellungen > Mitteilungen > Studio)."
                }
            }
        }
    }

    /// Plant die Erinnerungen 24 h und 3 h vor Ablauf (bei jedem Start neu).
    func scheduleReminder() {
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: ["sig.1", "sig.2"])
        guard reminderOn, let e = expiry else { return }
        let plan: [(String, TimeInterval, String)] = [
            ("sig.1", 24 * 3600, "Die Signatur der App läuft morgen ab. Mit Sideloadly neu installieren - Einstellungen bleiben erhalten."),
            ("sig.2", 3 * 3600, "Die Signatur der App läuft in 3 Stunden ab. Danach startet Studio nicht mehr, bis sie neu installiert ist.")
        ]
        for (id, before, text) in plan {
            let when = e.addingTimeInterval(-before)
            let delay = when.timeIntervalSinceNow
            if delay < 60 { continue }
            let c = UNMutableNotificationContent()
            c.title = "Studio Control"
            c.body = text
            c.sound = .default
            let trig = UNTimeIntervalNotificationTrigger(timeInterval: delay, repeats: false)
            center.add(UNNotificationRequest(identifier: id, content: c, trigger: trig), withCompletionHandler: nil)
        }
    }

    // ---- Oeffnen ----
    func open(_ s: String) {
        guard let u = URL(string: s) else { return }
        UIApplication.shared.open(u, options: [:]) { ok in
            if !ok {
                Task { @MainActor in self.message = "Konnte nicht geöffnet werden - die passende App ist nicht installiert." }
            }
        }
    }

    func openInStore(_ scheme: String) {
        let ipa = (remote?.ipa.isEmpty == false) ? (remote?.ipa ?? UpdateCenter.ipaURL) : UpdateCenter.ipaURL
        let enc = ipa.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ipa
        open("\(scheme)://install?url=\(enc)")
    }

    func addSource(_ scheme: String) {
        let enc = UpdateCenter.sourceURL.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? UpdateCenter.sourceURL
        open("\(scheme)://source?url=\(enc)")
    }
}

// ---------------------------------------------------------------------------
// Sicherung aller Einstellungen
// ---------------------------------------------------------------------------
enum SettingsBackup {
    /// Schreibt alle Einstellungen in eine JSON-Datei im Temp-Ordner und liefert deren URL.
    @MainActor
    static func export(_ devices: [DeviceModel]) -> URL? {
        var items: [String: String] = [:]
        for d in devices {
            d.saveSettings()
            for k in d.storeKeys {
                if let data = SecureStore.load(k) { items[k] = data.base64EncodedString() }
            }
        }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd_HHmm"
        let root: [String: Any] = ["app": "StudioControl", "version": APP_VERSION, "build": APP_BUILD,
                                   "date": f.string(from: Date()), "items": items]
        guard let data = try? JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys]) else { return nil }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("StudioControl_Einstellungen_\(f.string(from: Date())).json")
        do {
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            return nil
        }
    }

    /// Liest eine Sicherung ein. Rueckgabe: Anzahl uebernommener Geraete.
    @MainActor
    static func restore(from url: URL, into devices: [DeviceModel]) throws -> Int {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: url)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              (root["app"] as? String) == "StudioControl",
              let items = root["items"] as? [String: String] else {
            throw NetError.protocolError("Das ist keine Studio-Control-Sicherung")
        }
        let allowed = Set(devices.flatMap { $0.storeKeys })
        var n = 0
        for (k, v) in items where allowed.contains(k) {
            if let d = Data(base64Encoded: v) {
                SecureStore.save(k, d)
                n += 1
            }
        }
        for d in devices { d.loadSettings() }
        return n
    }
}
