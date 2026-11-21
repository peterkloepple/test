// ===========================================================================
//  Update.swift - PA Schematic iOS - Update-Pruefung und Ablauf der Signatur
//  Autor: T. Pfeiffer
//
//  Die neue Version steht bei GitHub (version.json im Release). Hat das iPhone
//  kein Internet, fragt die App den PC: PA Schematic legt die neueste App dort
//  bereit. Installiert wird am iPhone mit SideStore oder AltStore, am PC mit
//  Sideloadly - eine iOS-App kann sich nicht selbst installieren.
// ===========================================================================
import Foundation
import SwiftUI
import UIKit

struct RemoteVersion: Codable, Equatable {
    var version: String = ""
    var build: Int = 0
    var date: String = ""
    var notes: String = ""
    var ipa: String = ""
    var page: String = ""
    var ipa_pc: String = ""

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        version = (try? c.decodeIfPresent(String.self, forKey: .version)) ?? ""
        build = (try? c.decodeIfPresent(Int.self, forKey: .build)) ?? 0
        date = (try? c.decodeIfPresent(String.self, forKey: .date)) ?? ""
        notes = (try? c.decodeIfPresent(String.self, forKey: .notes)) ?? ""
        ipa = (try? c.decodeIfPresent(String.self, forKey: .ipa)) ?? ""
        page = (try? c.decodeIfPresent(String.self, forKey: .page)) ?? ""
        ipa_pc = (try? c.decodeIfPresent(String.self, forKey: .ipa_pc)) ?? ""
    }
}

@MainActor
final class UpdateCenter: ObservableObject {
    static let base = "https://github.com/peterkloepple/test/releases/download/paschematic-ios-latest/"
    static let versionURL = base + "version.json"
    static let ipaURL = base + "PASchematic_iOS.ipa"
    static let pageURL = "https://github.com/peterkloepple/test/releases/tag/paschematic-ios-latest"

    @Published var remote: RemoteVersion?
    @Published var checking = false
    @Published var message: String?
    @Published var expiry: Date?
    private var lastCheck: Date?
    private var fromPC = false

    init() {
        expiry = UpdateCenter.readExpiry()
    }

    var updateAvailable: Bool {
        guard let r = remote else { return false }
        return r.build > APP_BUILD
    }

    var expiryText: String {
        guard let e = expiry else { return "unbekannt" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "EEE dd.MM.yyyy HH:mm"
        let left = e.timeIntervalSinceNow
        if left <= 0 { return "abgelaufen (\(f.string(from: e)))" }
        return "\(f.string(from: e)) (noch \(Int(left / 86400)) T \(Int(left / 3600) % 24) h)"
    }

    var expiresSoon: Bool {
        guard let e = expiry else { return false }
        return e.timeIntervalSinceNow < 2 * 86400
    }

    private func fetch(_ url: String, key: String?) async -> RemoteVersion? {
        guard let u = URL(string: url) else { return nil }
        var req = URLRequest(url: u, cachePolicy: .reloadIgnoringLocalAndRemoteCacheData, timeoutInterval: 10)
        if let k = key { req.setValue(k, forHTTPHeaderField: "X-Key") }
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { return nil }
        return try? JSONDecoder().decode(RemoteVersion.self, from: data)
    }

    /// Erst GitHub fragen, sonst den PC. Ohne force hoechstens alle 6 Stunden.
    func check(pc: String, key: String, force: Bool) async {
        if checking { return }
        if !force, let t = lastCheck, Date().timeIntervalSince(t) < 6 * 3600 { return }
        checking = true
        defer { checking = false }
        var r = await fetch(UpdateCenter.versionURL, key: nil)
        fromPC = false
        if r == nil, !pc.isEmpty {
            r = await fetch(pc + "/app/version.json", key: key)
            fromPC = r != nil
        }
        guard let got = r else {
            if force { message = "Prüfung nicht gelungen: weder GitHub noch der PC haben geantwortet." }
            return
        }
        remote = got
        lastCheck = Date()
        if force {
            message = got.build > APP_BUILD
                ? "Neue Version \(got.version) (Build \(got.build)) gefunden\(fromPC ? " - sie liegt am PC bereit" : "")."
                : "Die App ist aktuell."
        }
    }

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

    func open(_ s: String) {
        guard let u = URL(string: s) else { return }
        UIApplication.shared.open(u, options: [:]) { ok in
            if !ok {
                Task { @MainActor in self.message = "Konnte nicht geöffnet werden - die passende App ist nicht installiert." }
            }
        }
    }

    /// Uebergibt die neue .ipa an SideStore oder AltStore; ohne Internet die Kopie vom PC
    func openInStore(_ scheme: String) {
        var ipa = UpdateCenter.ipaURL
        if let r = remote {
            if fromPC, !r.ipa_pc.isEmpty {
                ipa = r.ipa_pc
            } else if !r.ipa.isEmpty {
                ipa = r.ipa
            }
        }
        let enc = ipa.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ipa
        open("\(scheme)://install?url=\(enc)")
    }
}
