// ===========================================================================
//  DeviceModel.swift - Studio Control iOS - Basisklasse fuer jedes Geraet
//  Autor: T. Pfeiffer
//
//  Jedes Geraet erbt von DeviceModel und ueberschreibt:
//    refresh()       - Status lesen (wird beim Oeffnen + im Intervall aufgerufen)
//    loadSettings()  - Einstellungen aus SecureStore laden
//    saveSettings()  - Einstellungen speichern
//  Aktionen laufen ueber perform("Text") { ... } - setzt busy, faengt Fehler,
//  schreibt das Protokoll, gibt ein kurzes Haptik-Feedback.
// ===========================================================================
import Foundation
import SwiftUI
import UIKit

enum DeviceState: Equatable {
    case unknown
    case online
    case offline
    case notConfigured
}

@MainActor
class DeviceModel: ObservableObject, Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let symbol: String
    let tint: Color

    @Published var state: DeviceState = .unknown
    /// Kurzer Status fuer die Kachel (z.B. "An - HDMI 1")
    @Published var summary: String = ""
    @Published var busy = false
    @Published var lastError: String?
    @Published var lastUpdate: Date?
    @Published var log: [LogLine] = []

    /// Wie oft die Detailseite automatisch aktualisiert (Sekunden, 0 = nie)
    var pollInterval: Double { 5 }
    /// Ist das Geraet ueberhaupt eingerichtet (IP eingetragen)?
    var isConfigured: Bool { true }

    init(id: String, title: String, subtitle: String, symbol: String, tint: Color) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.symbol = symbol
        self.tint = tint
    }

    // ---- zum Ueberschreiben ----
    func refresh() async {}
    func loadSettings() {}
    func saveSettings() {}
    /// Verbindung schliessen (App geht in den Hintergrund)
    func disconnect() {}
    /// Nimmt das Geraet an den Szenen "Studio an" / "Studio aus" teil?
    var supportsScene: Bool { false }
    /// Szene ausfuehren (z.B. Beamer an, gewaehlte Steckdosen an). Wirft bei Fehler.
    func scene(_ on: Bool) async throws {}

    // ---- Hilfen ----
    func addLog(_ text: String, error: Bool = false) {
        log.insert(LogLine(time: Date(), text: text, isError: error), at: 0)
        if log.count > 200 { log.removeLast(log.count - 200) }
    }

    /// Fuehrt eine Aktion aus: busy-Anzeige, Fehler ins Protokoll, Haptik.
    func perform(_ label: String, haptic: Bool = true, _ op: @escaping () async throws -> Void) {
        Task { await performAsync(label, haptic: haptic, op) }
    }

    func performAsync(_ label: String, haptic: Bool = true, _ op: @escaping () async throws -> Void) async {
        busy = true
        defer { busy = false }
        do {
            try await op()
            lastError = nil
            if !label.isEmpty { addLog(label) }
            if haptic { Haptics.success() }
        } catch {
            let msg = DeviceModel.describe(error)
            lastError = msg
            addLog("\(label.isEmpty ? "Fehler" : label): \(msg)", error: true)
            if haptic { Haptics.error() }
        }
    }

    /// Status lesen mit Fehlerbehandlung (setzt online/offline).
    func refreshSafely(_ op: () async throws -> Void) async {
        guard isConfigured else {
            state = .notConfigured
            summary = "Nicht eingerichtet"
            return
        }
        do {
            try await op()
            state = .online
            lastError = nil
            lastUpdate = Date()
        } catch is CancellationError {
            return
        } catch {
            state = .offline
            let msg = DeviceModel.describe(error)
            if lastError != msg { addLog(msg, error: true) }
            lastError = msg
            summary = "Nicht erreichbar"
        }
    }

    static func describe(_ error: Error) -> String {
        if let e = error as? LocalizedError, let d = e.errorDescription { return d }
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain {
            switch ns.code {
            case NSURLErrorTimedOut: return "Zeitueberschreitung"
            case NSURLErrorCannotConnectToHost: return "Verbindung abgelehnt"
            case NSURLErrorNotConnectedToInternet: return "Kein Netzwerk"
            case NSURLErrorCannotFindHost: return "Adresse unbekannt"
            case NSURLErrorUserCancelledAuthentication: return "Anmeldung abgelehnt (Benutzer/Kennwort?)"
            default: break
            }
        }
        let t = error.localizedDescription
        if t.contains("POSIXErrorCode") || t.contains("Connection refused") { return "Verbindung abgelehnt" }
        return t
    }
}

enum Haptics {
    static func success() { UINotificationFeedbackGenerator().notificationOccurred(.success) }
    static func error() { UINotificationFeedbackGenerator().notificationOccurred(.error) }
    static func tap() { UIImpactFeedbackGenerator(style: .light).impactOccurred() }
}
