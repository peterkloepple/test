// ===========================================================================
//  Beamer.swift - Studio Control iOS - Sharp XG-PH50X (RS-232C ueber TCP)
//  Autor: T. Pfeiffer
//
//  Protokoll (wie SharpClient in sc.py):
//    - TCP zum Seriell-Server (Standard 192.168.1.50:10002)
//    - Login: auf "login" warten -> Benutzer+CRLF, auf "pass" warten -> Kennwort+CRLF,
//      nach 6 s ohne Prompt: Benutzer und Kennwort blind senden (0,5 s Abstand)
//    - Befehl: 4 Zeichen CMD (links, mit Leerzeichen aufgefuellt) + 4 Zeichen
//      Parameter (rechtsbuendig) + CR, Antwort eine Zeile ("OK", "ERR" oder Wert)
//    - Abfrage mit Parameter "????"; Statusabfrage POWR/ICHK alle 3 s
//    - gleicher Befehl+Parameter innerhalb 0,3 s wird verworfen (Entprellung)
//  Die Verbindung bleibt offen; Befehle laufen nacheinander (Actor + Warteschlange),
//  bei getrennter Verbindung wird einmal neu verbunden und der Befehl wiederholt.
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct BeamerSettings: Codable {
    var ip: String = "192.168.1.50"
    var port: Int = 10002
    var user: String = "admin"
    var password: String = "admin"
    var inScene: Bool = true

    init() {}

    enum CodingKeys: String, CodingKey {
        case ip, port, user, password, inScene
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ip = try c.decodeIfPresent(String.self, forKey: .ip) ?? "192.168.1.50"
        port = try c.decodeIfPresent(Int.self, forKey: .port) ?? 10002
        user = try c.decodeIfPresent(String.self, forKey: .user) ?? "admin"
        password = try c.decodeIfPresent(String.self, forKey: .password) ?? "admin"
        inScene = try c.decodeIfPresent(Bool.self, forKey: .inScene) ?? true
    }
}

// ---------------------------------------------------------------------------
// Protokoll-Client (Actor = ein Befehl nach dem anderen)
// ---------------------------------------------------------------------------
actor SharpBeamerClient {
    static let loginTimeout: Double = 6
    static let debounce: Double = 0.3

    private var conn: TCPConnection?
    private var connKey = ""
    private var rx: [UInt8] = []
    private var lastCmdTime: [String: Date] = [:]
    private var freshLogin = false
    private(set) var loginMethod = ""

    // einfache asynchrone Sperre (Actor-Methoden sind wiedereintrittsfaehig)
    private var locked = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    private func acquire() async {
        if !locked {
            locked = true
            return
        }
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            waiters.append(c)
        }
    }

    private func release() {
        if waiters.isEmpty {
            locked = false
        } else {
            let w = waiters.removeFirst()
            w.resume()
        }
    }

    // ---- Befehlsaufbau (build_cmd / P aus sc.py) ----
    static func buildCmd(_ cmd: String, _ param: String) -> String {
        var c = cmd
        while c.count < 4 { c += " " }
        c = String(c.prefix(4))
        var p = param
        while p.count < 4 { p = " " + p }
        p = String(p.prefix(4))
        return c + p + "\r"
    }

    static func param(_ v: Int, _ lo: Int, _ hi: Int) -> String {
        let x = max(lo, min(hi, v))
        return String(format: "%4d", x)
    }

    var isConnected: Bool {
        guard let c = conn else { return false }
        return !c.isClosed
    }

    /// true genau einmal nach jeder neuen Anmeldung
    func consumeFreshLogin() -> Bool {
        let f = freshLogin
        freshLogin = false
        return f
    }

    func close() {
        conn?.close()
        conn = nil
        connKey = ""
        rx.removeAll()
    }

    // ---- Verbindung + Login ----
    private func ensureConnected(_ s: BeamerSettings) async throws -> TCPConnection {
        let host = s.ip.trimmed
        let key = "\(host):\(s.port):\(s.user):\(s.password)"
        if let c = conn, !c.isClosed, key == connKey {
            return c
        }
        conn?.close()
        conn = nil
        guard let port = UInt16(exactly: s.port), port > 0 else {
            throw NetError.badAddress("\(host):\(s.port)")
        }
        let c = try TCPConnection(host: host, port: port)
        try await c.connect(timeout: 5)
        do {
            try await login(c, s)
        } catch {
            c.close()
            throw error
        }
        conn = c
        connKey = key
        rx.removeAll()
        freshLogin = true
        return c
    }

    private func login(_ c: TCPConnection, _ s: BeamerSettings) async throws {
        let deadline = Date().addingTimeInterval(SharpBeamerClient.loginTimeout)
        var waitPass = false
        var acc = ""
        while Date() < deadline {
            let d = await c.readAvailable(wait: 0.3, settle: 0.05)
            if !d.isEmpty {
                acc += d.latin1.lowercased()
            } else if c.isClosed {
                throw NetError.closed
            }
            if !waitPass && acc.contains("login") {
                try await c.send(s.user + "\r\n", encoding: .utf8)
                waitPass = true
                acc = ""
            } else if waitPass && acc.contains("pass") {
                try await c.send(s.password + "\r\n", encoding: .utf8)
                loginMethod = "Prompt-Login"
                _ = await c.readAvailable(wait: 0.4, settle: 0.1)
                return
            }
        }
        // Login-Timeout - Zugangsdaten blind senden (wie _blind_login)
        try await c.send(s.user + "\r\n", encoding: .utf8)
        await pause(0.5)
        try await c.send(s.password + "\r\n", encoding: .utf8)
        loginMethod = "Blind-Login"
        _ = await c.readAvailable(wait: 0.4, settle: 0.1)
    }

    // ---- Antwortzeile lesen (CR oder LF beendet die Zeile, Leerzeilen ueberspringen) ----
    private func readLine(_ c: TCPConnection, timeout: Double) async throws -> String {
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            while let idx = rx.firstIndex(where: { $0 == 0x0D || $0 == 0x0A }) {
                let lineBytes = Array(rx[0..<idx])
                rx.removeSubrange(0...idx)
                let line = String(decoding: lineBytes, as: UTF8.self).trimmed
                if !line.isEmpty { return line }
            }
            if Date() >= deadline {
                throw NetError.timeout("Antwort vom Beamer")
            }
            let d = await c.readAvailable(wait: 0.25, settle: 0.02)
            if d.isEmpty {
                if c.isClosed { throw NetError.closed }
            } else {
                rx.append(contentsOf: d)
            }
        }
    }

    /// Sendet CMD+Param und liefert die Antwortzeile. nil = durch Entprellung verworfen.
    func command(_ cmd: String, _ param: String, settings s: BeamerSettings,
                 timeout: Double = 2.5) async throws -> String? {
        let key = cmd + param
        let now = Date()
        if let t = lastCmdTime[key], now.timeIntervalSince(t) < SharpBeamerClient.debounce {
            return nil
        }
        lastCmdTime[key] = now
        await acquire()
        defer { release() }
        var attempt = 0
        while true {
            let hadConn = (conn != nil)
            do {
                let c = try await ensureConnected(s)
                c.clear()
                rx.removeAll()
                try await c.send(SharpBeamerClient.buildCmd(cmd, param), encoding: .ascii)
                return try await readLine(c, timeout: timeout)
            } catch {
                let stillOpen = conn.map { !$0.isClosed } ?? false
                if let ne = error as? NetError, case .timeout = ne, stillOpen {
                    // Verbindung steht, nur keine Antwort -> nicht neu verbinden
                    throw error
                }
                conn?.close()
                conn = nil
                if attempt == 0 && hadConn {
                    attempt += 1
                    continue        // alte Verbindung war tot -> einmal neu verbinden
                }
                throw error
            }
        }
    }

    /// Roh-Text senden (Terminal), liefert alles, was innerhalb ~1,5 s zurueckkommt.
    func sendRaw(_ text: String, addCR: Bool, settings s: BeamerSettings) async throws -> String {
        await acquire()
        defer { release() }
        let c = try await ensureConnected(s)
        c.clear()
        rx.removeAll()
        try await c.send(text + (addCR ? "\r" : ""), encoding: .ascii)
        let d = await c.readAvailable(wait: 1.5, settle: 0.15)
        return d.latin1.trimmed
    }
}

// ---------------------------------------------------------------------------
// Auswahl-Optionen (Beschriftung + Parameter)
// ---------------------------------------------------------------------------
struct BeamerOpt: Hashable {
    let label: String
    let param: String
}

struct BeamerMenuSpec: Hashable {
    let title: String
    let cmd: String
    let options: [BeamerOpt]
}

struct BeamerKnob: Hashable {
    let label: String
    let cmd: String
    let lo: Int
    let hi: Int
}

enum BeamerTables {
    // SH_IN_CMD: Bildwerte je Eingang (RGB1, RGB2, DVI, Video1, Video2)
    static let inCmd: [String: [String]] = [
        "contrast": ["RAPI", "RBPI", "RCPI", "VAPI", "VBPI"],
        "bright": ["RABR", "RBBR", "RCBR", "VABR", "VBBR"],
        "color": ["RACO", "RBCO", "RCCO", "VACO", "VBCO"],
        "tint": ["RATI", "RBTI", "RCTI", "VATI", "VBTI"],
        "red": ["RARD", "RBRD", "RCRD", "VARD", "VBRD"],
        "green": ["RAGN", "RBGN", "RCGN", "VAGN", "VBGN"],
        "blue": ["RABE", "RBBE", "RCBE", "VABE", "VBBE"],
        "sharp": ["RASH", "RBSH", "RCSH", "VASH", "VBSH"],
        "bright_boost": ["RAWE", "RBWE", "RCWE", "VAWE", "VBWE"],
    ]
    static let inPfx = ["RA", "RB", "RC", "VA", "VB"]
    static let inNames = ["RGB 1", "RGB 2", "DVI", "Video 1", "Video 2"]
    static let ichkMap: [String: String] = ["1": "RGB 1", "2": "RGB 2", "3": "DVI", "4": "Video 1", "5": "Video 2"]

    static let picKeys: [(String, String, Int, Int)] = [
        ("contrast", "Kontrast", -30, 30), ("bright", "Helligkeit", -30, 30),
        ("color", "Farbe", -30, 30), ("tint", "Farbton", -30, 30),
        ("red", "Rot", -30, 30), ("green", "Grün", -30, 30),
        ("blue", "Blau", -30, 30), ("sharp", "Schärfe", -30, 30),
        ("bright_boost", "Bright-Boost", 0, 10),
    ]

    static func picKnobs(_ idx: Int) -> [BeamerKnob] {
        let i = max(0, min(4, idx - 1))
        var out: [BeamerKnob] = []
        for k in picKeys {
            if let cmds = inCmd[k.0] {
                out.append(BeamerKnob(label: k.1, cmd: cmds[i], lo: k.2, hi: k.3))
            }
        }
        return out
    }

    static let audioKnobs = [
        BeamerKnob(label: "Lautstärke", cmd: "VOLA", lo: 0, hi: 60),
        BeamerKnob(label: "Balance", cmd: "AABL", lo: -30, hi: 30),
        BeamerKnob(label: "Höhen", cmd: "AATE", lo: -30, hi: 30),
        BeamerKnob(label: "Bass", cmd: "AABA", lo: -30, hi: 30),
    ]
    static let lensKnobs = [
        BeamerKnob(label: "Zoom", cmd: "LNZO", lo: -255, hi: 255),
        BeamerKnob(label: "Fokus", cmd: "LNFO", lo: -255, hi: 255),
        BeamerKnob(label: "Shift V", cmd: "LNUD", lo: -800, hi: 800),
        BeamerKnob(label: "Shift H", cmd: "LNLR", lo: -800, hi: 800),
        BeamerKnob(label: "Digital-Shift", cmd: "LNDS", lo: -96, hi: 96),
    ]
    static let keystoneKnobs = [
        BeamerKnob(label: "Keystone V", cmd: "KEYV", lo: -60, hi: 60),
        BeamerKnob(label: "Keystone H", cmd: "KEYH", lo: -60, hi: 60),
    ]
    static let syncKnobs = [
        BeamerKnob(label: "H-Position", cmd: "IAHP", lo: -150, hi: 150),
        BeamerKnob(label: "V-Position", cmd: "IAVP", lo: -60, hi: 60),
        BeamerKnob(label: "Clock", cmd: "INCL", lo: -150, hi: 150),
        BeamerKnob(label: "Phase", cmd: "INPH", lo: -60, hi: 60),
        BeamerKnob(label: "Image Resize", cmd: "IMRS", lo: -30, hi: 30),
    ]
    static let cmsKnobs = [
        BeamerKnob(label: "Helligkeit", cmd: "CMSL", lo: -30, hi: 30),
        BeamerKnob(label: "Sättigung", cmd: "CMSC", lo: -30, hi: 30),
        BeamerKnob(label: "Farbton", cmd: "CMSH", lo: -30, hi: 30),
    ]

    static func o(_ pairs: [(String, String)]) -> [BeamerOpt] {
        pairs.map { BeamerOpt(label: $0.0, param: $0.1) }
    }

    static let osd = o([("Normal", "   0"), ("Level A", "   1"), ("Level B", "   2")])
    static let pip = o([("Aus", "   0"), ("Unten rechts", "   1"), ("Unten links", "   2"),
                        ("Oben rechts", "   3"), ("Oben links", "   4")])
    static let speaker = o([("An", "   1"), ("Aus", "   0")])
    static let audioOut = o([("Fix", "   0"), ("Variabel", "   1")])
    static let background = o([("Logo", "   1"), ("Custom", "   2"), ("Blau", "   3"), ("Kein", "   4")])
    static let startup = o([("Logo", "   1"), ("Custom", "   2"), ("Kein", "   3")])
    static let autoSync = o([("Aus", "   0"), ("Normal", "   1"), ("Schnell", "   2")])
    static let memory = o((1...7).map { ("Speicher \($0)", "   \($0)") })
    static let picMode = o([("Standard", "   0"), ("Präsentation", "   1"), ("Kino", "   2"), ("Custom", "   3")])
    static let colorTemp = o([("4500K", " 045"), ("5500K", " 055"), ("6500K", " 065"), ("7500K", " 075"),
                              ("8500K", " 085"), ("9300K", " 093"), ("10500K", " 105")])
    static let progressive = o([("2D", "   0"), ("3D", "   1"), ("Film", "   2")])
    static let dnr = o([("Aus", "   0"), ("1", "   1"), ("2", "   2"), ("3", "   3")])
    static let cmsRGB = o([("Standard", "  00"), ("sRGB", "  01"), ("Custom 1", "  11"),
                           ("Custom 2", "  12"), ("Custom 3", "  13")])
    static let cmsVideo = o([("Standard", "  00"), ("Custom 1", "  11"), ("Custom 2", "  12"), ("Custom 3", "  13")])
    static let cmsRows: [BeamerMenuSpec] = [
        BeamerMenuSpec(title: "Eingang 1 (RGB 1)", cmd: "CSRA", options: cmsRGB),
        BeamerMenuSpec(title: "Eingang 2 (RGB 2)", cmd: "CSRB", options: cmsRGB),
        BeamerMenuSpec(title: "Eingang 3 (DVI)", cmd: "CSRC", options: cmsRGB),
        BeamerMenuSpec(title: "Eingang 4 (Video 1)", cmd: "CSVA", options: cmsVideo),
        BeamerMenuSpec(title: "Eingang 5 (Video 2)", cmd: "CSVB", options: cmsVideo),
    ]
    static let cmsTarget = o([("Rot", "   1"), ("Gelb", "   2"), ("Grün", "   3"),
                              ("Cyan", "   4"), ("Blau", "   5"), ("Magenta", "   6")])
    static let lampMode = o([("Beide", "   0"), ("Lampe 1", "   1"), ("Lampe 2", "   2"), ("Equal", "   3")])
    static let eco = o([("Standard", "   0"), ("Eco", "   1")])
    static let onOff = o([("Aus", "   0"), ("An", "   1")])
    static let stack = o([("Normal", "   0"), ("Master", "   1"), ("Slave", "   2")])
    static let keylock = o([("Normal", "   0"), ("Level A", "   1"), ("Level B", "   2")])
    static let videoSystem = o([("Auto", "   0"), ("PAL", "   1"), ("SECAM", "   2"), ("NTSC 4.43", "   3"),
                                ("NTSC 3.58", "   4"), ("PAL-M", "   5"), ("PAL-N", "   6")])
    static let language = o([("English", "   1"), ("Deutsch", "   2"), ("Español", "   3"), ("Nederlands", "   4"),
                             ("Français", "   5"), ("Italiano", "   6"), ("Svenska", "   7"), ("Português", "   9")])

    /// Resize-Befehl + Optionen je Eingang (wie _pp_rebuild)
    static func resize(_ idx: Int) -> (String, [BeamerOpt]) {
        let i = max(0, min(4, idx - 1))
        var cmd = inPfx[i] + "SR"
        if idx == 4 { cmd = "RASV" }
        if idx == 5 { cmd = "RBSV" }
        var items = [("Normal", "   0"), ("Stretch", "   1"), ("Dot-by-Dot", "   2"), ("Smart", "   3")]
        if idx >= 1 && idx <= 3 { items.append(("Full", "   4")) }
        return (cmd, o(items))
    }

    /// Signaltyp-Befehl + Optionen je Eingang (nil = keiner)
    static func signal(_ idx: Int) -> (String, [BeamerOpt])? {
        if idx == 1 || idx == 2 {
            return (idx == 1 ? "IASI" : "IBSI", o([("Auto", "   0"), ("RGB", "   1"), ("Component", "   2")]))
        }
        if idx == 3 {
            return ("ICSI", o([("DPC RGB", "   3"), ("DPC Comp", "   4"), ("DVid RGB", "   5"), ("DVid Comp", "   6")]))
        }
        return nil
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
@MainActor
final class BeamerModel: DeviceModel {
    @Published var settings = BeamerSettings()
    @Published var power: Bool?
    @Published var input = "-"
    @Published var info: [String: String] = [:]
    @Published var values: [String: Int] = [:]
    @Published var ppInput = 1
    @Published var lastResponse = ""
    @Published var connected = false
    @Published var terminal: [String] = []

    private let client = SharpBeamerClient()

    init() {
        super.init(id: "beamer", title: "Beamer", subtitle: "Sharp XG-PH50X",
                   symbol: "videoprojector", tint: Color(hex: 0xFF9F0A))
    }

    override var pollInterval: Double { 3 }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override var supportsScene: Bool { settings.inScene }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(BeamerSettings.self, "beamer") {
            settings = s
        }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "beamer")
        let c = client
        Task { await c.close() }
        connected = false
    }

    override func disconnect() {
        let c = client
        Task { await c.close() }
        connected = false
    }

    // ---- Status ----
    override func refresh() async {
        await refreshSafely {
            let s = settings
            if let p = try await client.command("POWR", "????", settings: s) {
                handle("POWR", "????", p)
            }
            if let i = try await client.command("ICHK", "????", settings: s) {
                handle("ICHK", "????", i)
            }
            if await client.consumeFreshLogin() {
                let m = await client.loginMethod
                addLog("Angemeldet [\(m)] - \(s.ip.trimmed):\(s.port)")
                await queryAll()
            }
            updateSummary()
        }
        connected = await client.isConnected
    }

    private func updateSummary() {
        guard let p = power else {
            summary = connected ? "Verbunden" : ""
            return
        }
        summary = p ? "An - \(input)" : "Aus (Standby)"
    }

    static func inputName(_ raw: String) -> String {
        let s = raw.trimmed
        let digits = String(s.filter { $0.isASCII && $0.isNumber })
        if let n = BeamerTables.ichkMap[digits] { return n }
        if let n = BeamerTables.ichkMap[s] { return n }
        return s.isEmpty ? "-" : s
    }

    /// Antwort auswerten (wie _parse_line)
    private func handle(_ cmd: String, _ param: String, _ t: String) {
        lastResponse = "\(cmd) \(param.trimmed) -> \(t)"
        if t == "OK" || t == "ERR" { return }
        let digits = String(t.filter { ($0.isASCII && $0.isNumber) || $0 == "." })
        let p = param.trimmed
        switch cmd {
        case "POWR":
            power = digits.hasPrefix("1")
        case "ICHK":
            input = BeamerModel.inputName(t)
        case "TLTT":
            info["lamp\(p)_h"] = digits + " h"
        case "TLTL":
            info["lamp\(p)_l"] = digits + " %"
        case "TFRQ":
            info["freq\(p)"] = digits + (p == "1" ? " kHz" : " Hz")
        case "TNAM":
            info["model"] = t
        case "SNRD":
            info["serial"] = t
        case "PJN0":
            info["name"] = t
        case "TLPS":
            info["lps\(p)"] = t
        case "TLPN":
            info["lpn"] = t
        case "TPOW":
            info["tpow"] = t
        default:
            if param == "????" {
                let num = t.replacingOccurrences(of: "%", with: "")
                    .replacingOccurrences(of: "+", with: "").trimmed
                if let d = Double(num) {
                    values[cmd] = Int(d.rounded())
                }
            }
        }
    }

    /// Alles abfragen (wie _query_all): Status, Info, Lampen, Frequenzen, Reglerwerte
    func queryAll() async {
        let s = settings
        var list: [(String, String)] = [("POWR", "????"), ("ICHK", "????"), ("TNAM", "????"), ("SNRD", "????"),
                                        ("TLTT", "1"), ("TLTT", "2"), ("TLTL", "1"), ("TLTL", "2"),
                                        ("TFRQ", "1"), ("TFRQ", "2")]
        var knobs: [BeamerKnob] = BeamerTables.audioKnobs
        knobs += BeamerTables.picKnobs(ppInput)
        knobs += BeamerTables.lensKnobs
        knobs += BeamerTables.keystoneKnobs
        knobs += BeamerTables.syncKnobs
        knobs += BeamerTables.cmsKnobs
        for k in knobs { list.append((k.cmd, "????")) }
        await queryList(list, settings: s)
    }

    private func queryList(_ list: [(String, String)], settings s: BeamerSettings) async {
        var fails = 0
        for (c, p) in list {
            do {
                if let r = try await client.command(c, p, settings: s, timeout: 1.5) {
                    handle(c, p, r)
                }
                fails = 0
            } catch {
                fails += 1
                if fails >= 3 {
                    addLog("Abfrage abgebrochen: \(DeviceModel.describe(error))", error: true)
                    break
                }
            }
        }
    }

    // ---- Aktionen ----
    func send(_ cmd: String, _ param: String, _ label: String, timeout: Double = 2.5) {
        let s = settings
        let c = client
        perform(label) { [weak self] in
            guard let self = self else { return }
            if let r = try await c.command(cmd, param, settings: s, timeout: timeout) {
                self.handle(cmd, param, r)
                if r == "ERR" {
                    throw NetError.protocolError("Beamer meldet ERR (\(cmd))")
                }
            }
        }
    }

    func setPower(_ on: Bool) {
        let s = settings
        let c = client
        perform(on ? "Beamer einschalten" : "Beamer ausschalten") { [weak self] in
            guard let self = self else { return }
            if let r = try await c.command("POWR", on ? "   1" : "   0", settings: s, timeout: 6) {
                self.handle("POWR", "x", r)
                if r == "ERR" { throw NetError.protocolError("Beamer meldet ERR (POWR)") }
                self.power = on
                self.updateSummary()
            }
        }
    }

    func selectInput(_ idx: Int) {
        let cmd = idx <= 3 ? "IRGB" : "IVED"
        let p = idx <= 3 ? "   \(idx)" : "   \(idx - 3)"
        let name = BeamerTables.inNames[max(0, min(4, idx - 1))]
        let s = settings
        let c = client
        perform("Eingang \(name)") { [weak self] in
            guard let self = self else { return }
            if let r = try await c.command(cmd, p, settings: s) {
                self.handle(cmd, p, r)
                if r == "ERR" { throw NetError.protocolError("Beamer meldet ERR (\(cmd))") }
            }
            await pause(0.4)
            if let i = try await c.command("ICHK", "????", settings: s) {
                self.handle("ICHK", "????", i)
            }
            self.updateSummary()
        }
    }

    func knobValue(_ k: BeamerKnob) -> Int {
        max(k.lo, min(k.hi, values[k.cmd] ?? 0))
    }

    func setKnobLocal(_ k: BeamerKnob, _ v: Int) {
        values[k.cmd] = max(k.lo, min(k.hi, v))
    }

    func sendKnob(_ k: BeamerKnob) {
        let v = knobValue(k)
        send(k.cmd, SharpBeamerClient.param(v, k.lo, k.hi), "\(k.label) \(v)")
    }

    func stepKnob(_ k: BeamerKnob, _ delta: Int) {
        setKnobLocal(k, knobValue(k) + delta)
        sendKnob(k)
    }

    func readKnobs(_ knobs: [BeamerKnob]) {
        let s = settings
        perform("Werte gelesen", haptic: false) { [weak self] in
            guard let self = self else { return }
            await self.queryList(knobs.map { ($0.cmd, "????") }, settings: s)
        }
    }

    func readAll() {
        perform("Alles abgefragt", haptic: false) { [weak self] in
            guard let self = self else { return }
            await self.queryAll()
            self.updateSummary()
        }
    }

    func query(_ cmd: String, _ param: String, _ label: String) {
        send(cmd, param, label)
    }

    func sendRaw(_ text: String, addCR: Bool) {
        guard !text.isEmpty else { return }
        let s = settings
        let c = client
        perform("", haptic: false) { [weak self] in
            guard let self = self else { return }
            self.appendTerminal(">> " + text + (addCR ? " <CR>" : ""))
            let r = try await c.sendRaw(text, addCR: addCR, settings: s)
            let lines = r.components(separatedBy: CharacterSet(charactersIn: "\r\n")).filter { !$0.trimmed.isEmpty }
            if lines.isEmpty {
                self.appendTerminal("<< (keine Antwort)")
            } else {
                for l in lines { self.appendTerminal("<< " + l.trimmed) }
            }
        }
    }

    func appendTerminal(_ line: String) {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        terminal.insert(f.string(from: Date()) + " " + line, at: 0)
        if terminal.count > 300 { terminal.removeLast(terminal.count - 300) }
    }

    // ---- Szene ----
    override func scene(_ on: Bool) async throws {
        let r = try await client.command("POWR", on ? "   1" : "   0", settings: settings, timeout: 6)
        if r == "ERR" { throw NetError.protocolError("Beamer meldet ERR (POWR)") }
        if r != nil {
            power = on
            updateSummary()
        }
    }
}

// ---------------------------------------------------------------------------
// Bausteine
// ---------------------------------------------------------------------------
struct BeamerKnobRow: View {
    @ObservedObject var model: BeamerModel
    let knob: BeamerKnob
    var step: Int = 2

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(knob.label)
                Spacer()
                Text("\(model.knobValue(knob))")
                    .monospacedDigit()
                    .foregroundColor(.secondary)
            }
            HStack(spacing: 12) {
                Button {
                    Haptics.tap()
                    model.stepKnob(knob, -step)
                } label: {
                    Image(systemName: "minus.circle.fill").font(.title3)
                }
                .buttonStyle(.borderless)
                Slider(value: Binding(get: { Double(model.knobValue(knob)) },
                                      set: { model.setKnobLocal(knob, Int($0.rounded())) }),
                       in: Double(knob.lo)...Double(knob.hi), step: 1,
                       onEditingChanged: { editing in
                           if !editing { model.sendKnob(knob) }
                       })
                Button {
                    Haptics.tap()
                    model.stepKnob(knob, step)
                } label: {
                    Image(systemName: "plus.circle.fill").font(.title3)
                }
                .buttonStyle(.borderless)
            }
        }
        .padding(.vertical, 2)
    }
}

struct BeamerMenuRow: View {
    @ObservedObject var model: BeamerModel
    let title: String
    let symbol: String
    let cmd: String
    let options: [BeamerOpt]

    var body: some View {
        Menu {
            ForEach(options, id: \.self) { o in
                Button(o.label) {
                    Haptics.tap()
                    model.send(cmd, o.param, "\(title): \(o.label)")
                }
            }
        } label: {
            HStack {
                Label(title, systemImage: symbol)
                    .foregroundColor(.primary)
                Spacer()
                Image(systemName: "chevron.up.chevron.down")
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Detailseite
// ---------------------------------------------------------------------------
struct BeamerView: View {
    @ObservedObject var model: BeamerModel
    @State private var showLens = false
    @State private var showSync = false
    @State private var showCMS = false
    @State private var showSystem = false
    @State private var showTerminal = false
    @State private var rawText = ""

    var body: some View {
        DevicePage(model: model, settings: { BeamerSettingsView(model: model) }) {
            Group {
                powerSection
                inputSection
                imageSection
                audioSection
            }
            Group {
                pictureSection
                lensSection
                syncSection
                cmsSection
            }
            Group {
                systemSection
                infoSection
                terminalSection
            }
        }
    }

    // ---- Power / Status ----
    private var powerSection: some View {
        Section("Power") {
            PowerToggleRow(title: "Projektor", symbol: "power", isOn: model.power ?? false, tint: .green) { on in
                model.setPower(on)
            }
            ValueRow(label: "Status", value: powerText, symbol: "info.circle")
            ValueRow(label: "Eingang", value: model.input, symbol: "rectangle.on.rectangle")
            ValueRow(label: "Verbindung", value: model.connected ? "Angemeldet" : "Getrennt",
                     symbol: "network", valueColor: model.connected ? .green : .secondary)
        }
    }

    private var powerText: String {
        guard let p = model.power else { return "?" }
        return p ? "AN" : "AUS"
    }

    // ---- Eingang ----
    private var inputSection: some View {
        Section("Eingang") {
            TileGrid(columns: 3) {
                ForEach(1...5, id: \.self) { i in
                    ActionTile(title: BeamerTables.inNames[i - 1],
                               symbol: i <= 3 ? "display" : "film",
                               tint: model.tint,
                               active: model.input == BeamerTables.inNames[i - 1]) {
                        model.selectInput(i)
                    }
                }
                ActionTile(title: "Abfragen", symbol: "arrow.clockwise", tint: model.tint) {
                    Task { await model.refresh() }
                }
            }
        }
    }

    // ---- Bild allgemein ----
    private var imageSection: some View {
        Section("Bild") {
            TileGrid(columns: 2) {
                ActionTile(title: "Freeze an", symbol: "pause.rectangle", tint: .blue) {
                    model.send("FREZ", "   1", "Freeze an")
                }
                ActionTile(title: "Freeze aus", symbol: "play.rectangle", tint: .blue) {
                    model.send("FREZ", "   0", "Freeze aus")
                }
                ActionTile(title: "Bild schwarz", symbol: "eye.slash", tint: .indigo) {
                    model.send("IMBK", "   1", "Black an")
                }
                ActionTile(title: "Bild zeigen", symbol: "eye", tint: .indigo) {
                    model.send("IMBK", "   0", "Black aus")
                }
            }
            BeamerMenuRow(model: model, title: "OSD-Anzeige", symbol: "textformat", cmd: "IMDI", options: BeamerTables.osd)
            BeamerMenuRow(model: model, title: "PIP", symbol: "pip", cmd: "PINP", options: BeamerTables.pip)
            BeamerMenuRow(model: model, title: "Hintergrund", symbol: "photo", cmd: "IMBG", options: BeamerTables.background)
            BeamerMenuRow(model: model, title: "Startlogo", symbol: "sparkles", cmd: "IMSI", options: BeamerTables.startup)
        }
    }

    // ---- Audio ----
    private var audioSection: some View {
        Section("Audio") {
            ForEach(BeamerTables.audioKnobs, id: \.self) { k in
                BeamerKnobRow(model: model, knob: k)
            }
            TileGrid(columns: 2) {
                ActionTile(title: "Ton aus", symbol: "speaker.slash.fill", tint: .red) {
                    model.send("MUTE", "   1", "Mute an")
                }
                ActionTile(title: "Ton an", symbol: "speaker.wave.2.fill", tint: .green) {
                    model.send("MUTE", "   0", "Mute aus")
                }
            }
            BeamerMenuRow(model: model, title: "Lautsprecher", symbol: "hifispeaker", cmd: "ASPK", options: BeamerTables.speaker)
            BeamerMenuRow(model: model, title: "Audio-Ausgang", symbol: "cable.connector", cmd: "AOUT", options: BeamerTables.audioOut)
            Button {
                model.send("AARE", "   1", "Audio Reset")
            } label: {
                Label("Audio zurücksetzen", systemImage: "arrow.counterclockwise")
            }
            Button {
                model.readKnobs(BeamerTables.audioKnobs)
            } label: {
                Label("Werte lesen", systemImage: "arrow.down.circle")
            }
        }
    }

    // ---- Bildparameter je Eingang ----
    private var pictureSection: some View {
        let idx = model.ppInput
        let pfx = BeamerTables.inPfx[max(0, min(4, idx - 1))]
        let rs = BeamerTables.resize(idx)
        let sig = BeamerTables.signal(idx)
        return Section {
            Picker("Eingang", selection: $model.ppInput) {
                Text("RGB1").tag(1)
                Text("RGB2").tag(2)
                Text("DVI").tag(3)
                Text("Vid1").tag(4)
                Text("Vid2").tag(5)
            }
            .pickerStyle(.segmented)
            .onChange(of: model.ppInput) { v in
                model.readKnobs(BeamerTables.picKnobs(v))
            }
            ForEach(BeamerTables.picKnobs(idx), id: \.self) { k in
                BeamerKnobRow(model: model, knob: k)
            }
            BeamerMenuRow(model: model, title: "Bildmodus", symbol: "photo.on.rectangle", cmd: pfx + "PS", options: BeamerTables.picMode)
            BeamerMenuRow(model: model, title: "Farbtemperatur", symbol: "thermometer", cmd: pfx + "CT", options: BeamerTables.colorTemp)
            if idx != 3 {
                BeamerMenuRow(model: model, title: "Progressive", symbol: "film.stack", cmd: pfx + "IP", options: BeamerTables.progressive)
            }
            BeamerMenuRow(model: model, title: "Rauschreduzierung", symbol: "waveform.path", cmd: pfx + "NR", options: BeamerTables.dnr)
            BeamerMenuRow(model: model, title: "Resize", symbol: "aspectratio", cmd: rs.0, options: rs.1)
            if let sg = sig {
                BeamerMenuRow(model: model, title: "Signaltyp", symbol: "cable.connector.horizontal", cmd: sg.0, options: sg.1)
            }
            Button {
                model.send(pfx + "RE", "   1", "Bildwerte zurückgesetzt")
            } label: {
                Label("Bildwerte zurücksetzen", systemImage: "arrow.counterclockwise")
            }
            Button {
                model.readKnobs(BeamerTables.picKnobs(idx))
            } label: {
                Label("Werte lesen", systemImage: "arrow.down.circle")
            }
        } header: {
            Text("Bildparameter")
        }
    }

    // ---- Optik / Geometrie ----
    private var lensSection: some View {
        Section {
            DisclosureGroup(isExpanded: $showLens) {
                ForEach(BeamerTables.lensKnobs, id: \.self) { k in
                    BeamerKnobRow(model: model, knob: k)
                }
                Button {
                    model.send("LNRS", "   1", "Lens Reset")
                } label: {
                    Label("Objektiv zurücksetzen", systemImage: "arrow.counterclockwise")
                }
                ForEach(BeamerTables.keystoneKnobs, id: \.self) { k in
                    BeamerKnobRow(model: model, knob: k)
                }
                Button {
                    model.readKnobs(BeamerTables.lensKnobs + BeamerTables.keystoneKnobs)
                } label: {
                    Label("Werte lesen", systemImage: "arrow.down.circle")
                }
            } label: {
                Label("Optik & Keystone", systemImage: "camera.aperture")
            }
        }
    }

    // ---- Fine Sync / Speicher ----
    private var syncSection: some View {
        Section {
            DisclosureGroup(isExpanded: $showSync) {
                ForEach(BeamerTables.syncKnobs, id: \.self) { k in
                    BeamerKnobRow(model: model, knob: k)
                }
                BeamerMenuRow(model: model, title: "Auto-Sync", symbol: "arrow.triangle.2.circlepath", cmd: "AADJ", options: BeamerTables.autoSync)
                Button {
                    model.send("ADJS", "   1", "Auto-Sync gestartet")
                } label: {
                    Label("Auto-Sync starten", systemImage: "play.circle")
                }
                Button {
                    model.send("IARE", "   1", "Fine-Sync Reset")
                } label: {
                    Label("Fine-Sync zurücksetzen", systemImage: "arrow.counterclockwise")
                }
                BeamerMenuRow(model: model, title: "Einstellung speichern", symbol: "square.and.arrow.down", cmd: "MEMS", options: BeamerTables.memory)
                BeamerMenuRow(model: model, title: "Einstellung laden", symbol: "square.and.arrow.up", cmd: "MEML", options: BeamerTables.memory)
            } label: {
                Label("Fine Sync & Speicher", systemImage: "slider.horizontal.3")
            }
        }
    }

    // ---- C.M.S. ----
    private var cmsSection: some View {
        Section {
            DisclosureGroup(isExpanded: $showCMS) {
                ForEach(BeamerTables.cmsRows, id: \.self) { row in
                    BeamerMenuRow(model: model, title: row.title, symbol: "paintpalette", cmd: row.cmd, options: row.options)
                }
                BeamerMenuRow(model: model, title: "Zielfarbe", symbol: "scope", cmd: "CMTG", options: BeamerTables.cmsTarget)
                ForEach(BeamerTables.cmsKnobs, id: \.self) { k in
                    BeamerKnobRow(model: model, knob: k)
                }
                Button {
                    model.send("CMRE", "   0", "CMS Reset Farbe")
                } label: {
                    Label("Farbe zurücksetzen", systemImage: "arrow.counterclockwise")
                }
                Button {
                    model.send("CMRE", "   1", "CMS Reset alle")
                } label: {
                    Label("Alle zurücksetzen", systemImage: "arrow.counterclockwise.circle")
                }
            } label: {
                Label("Farbmanagement (C.M.S.)", systemImage: "paintpalette")
            }
        }
    }

    // ---- Lampe / System / Video / Sprache ----
    private var systemSection: some View {
        Section {
            DisclosureGroup(isExpanded: $showSystem) {
                Group {
                    BeamerMenuRow(model: model, title: "Lampenmodus", symbol: "lightbulb", cmd: "LPMD", options: BeamerTables.lampMode)
                    BeamerMenuRow(model: model, title: "Eco-Modus", symbol: "leaf", cmd: "THMD", options: BeamerTables.eco)
                    BeamerMenuRow(model: model, title: "Auto-Power-Off", symbol: "powersleep", cmd: "APOW", options: BeamerTables.onOff)
                    BeamerMenuRow(model: model, title: "Spiegeln (Reverse)", symbol: "arrow.left.and.right.righttriangle.left.righttriangle.right", cmd: "IMRE", options: BeamerTables.onOff)
                    BeamerMenuRow(model: model, title: "Kopfüber (Invert)", symbol: "arrow.up.and.down.righttriangle.up.righttriangle.down", cmd: "IMIN", options: BeamerTables.onOff)
                }
                Group {
                    BeamerMenuRow(model: model, title: "Stack", symbol: "square.stack", cmd: "STAK", options: BeamerTables.stack)
                    BeamerMenuRow(model: model, title: "Tastensperre", symbol: "lock", cmd: "KEYL", options: BeamerTables.keylock)
                    BeamerMenuRow(model: model, title: "Monitor-Ausgang", symbol: "display.2", cmd: "MOUT", options: BeamerTables.onOff)
                    BeamerMenuRow(model: model, title: "Video-System", symbol: "tv", cmd: "MESY", options: BeamerTables.videoSystem)
                    BeamerMenuRow(model: model, title: "OSD-Sprache", symbol: "globe", cmd: "MELA", options: BeamerTables.language)
                }
            } label: {
                Label("Lampe, System & Sprache", systemImage: "gearshape.2")
            }
        }
    }

    // ---- Geraeteinfo ----
    private var infoSection: some View {
        Section("Geräteinfo") {
            Group {
                ValueRow(label: "Modell", value: model.info["model"] ?? "-")
                ValueRow(label: "Seriennr.", value: model.info["serial"] ?? "-")
                ValueRow(label: "Projektorname", value: model.info["name"] ?? "-")
                ValueRow(label: "Lampe 1 Stunden", value: model.info["lamp1_h"] ?? "-")
                ValueRow(label: "Lampe 2 Stunden", value: model.info["lamp2_h"] ?? "-")
            }
            Group {
                ValueRow(label: "Lampe 1 Leben", value: model.info["lamp1_l"] ?? "-")
                ValueRow(label: "Lampe 2 Leben", value: model.info["lamp2_l"] ?? "-")
                ValueRow(label: "H-Frequenz", value: model.info["freq1"] ?? "-")
                ValueRow(label: "V-Frequenz", value: model.info["freq2"] ?? "-")
            }
            Group {
                ValueRow(label: "Lampe 1 Status", value: model.info["lps1"] ?? "-")
                ValueRow(label: "Lampe 2 Status", value: model.info["lps2"] ?? "-")
                ValueRow(label: "Aktive Lampe", value: model.info["lpn"] ?? "-")
                ValueRow(label: "Lampen-Power", value: model.info["tpow"] ?? "-")
            }
            Menu {
                Button("Lampe 1 Status") { model.query("TLPS", "   1", "Lampe 1 Status") }
                Button("Lampe 2 Status") { model.query("TLPS", "   2", "Lampe 2 Status") }
                Button("Aktive Lampe") { model.query("TLPN", "????", "Aktive Lampe") }
                Button("Lampen-Power") { model.query("TPOW", "????", "Lampen-Power") }
                Button("Projektorname") { model.query("PJN0", "   1", "Projektorname") }
            } label: {
                Label("Einzeln abfragen", systemImage: "questionmark.circle")
            }
            Button {
                model.readAll()
            } label: {
                Label("Alles abfragen", systemImage: "arrow.clockwise.circle")
            }
            if !model.lastResponse.isEmpty {
                ValueRow(label: "Letzte Antwort", value: model.lastResponse)
                    .font(.footnote)
            }
        }
    }

    // ---- Terminal ----
    private var terminalSection: some View {
        Section {
            DisclosureGroup(isExpanded: $showTerminal) {
                TextField("z.B. POWR????", text: $rawText)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .font(.system(.body, design: .monospaced))
                HStack {
                    Button("Senden + CR") {
                        model.sendRaw(rawText, addCR: true)
                    }
                    .buttonStyle(.borderless)
                    Spacer()
                    Button("Ohne CR") {
                        model.sendRaw(rawText, addCR: false)
                    }
                    .buttonStyle(.borderless)
                    Spacer()
                    Button("Leeren") {
                        model.terminal.removeAll()
                    }
                    .buttonStyle(.borderless)
                }
                Text("4 Zeichen Befehl + 4 Zeichen Parameter, z.B. POWR   1 oder ICHK????")
                    .font(.caption)
                    .foregroundColor(.secondary)
                ForEach(Array(model.terminal.prefix(80).enumerated()), id: \.offset) { item in
                    Text(item.element)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                }
            } label: {
                Label("Terminal", systemImage: "terminal")
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct BeamerSettingsView: View {
    @ObservedObject var model: BeamerModel
    @State private var s: BeamerSettings

    init(model: BeamerModel) {
        _model = ObservedObject(wrappedValue: model)
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "Beamer", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "IP-Adresse", text: $s.ip, placeholder: "192.168.1.50", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($s.port), placeholder: "10002", keyboard: .numberPad)
            } header: {
                Text("Verbindung (RS-232C über TCP)")
            }
            Section {
                FieldRow(label: "Benutzer", text: $s.user, placeholder: "admin")
                FieldRow(label: "Kennwort", text: $s.password, placeholder: "admin", secure: true)
            } header: {
                Text("Anmeldung")
            } footer: {
                Text("Erscheint kein Login-Prompt, werden Benutzer und Kennwort nach 6 s blind gesendet.")
            }
            Section {
                Toggle("Bei Szenen schalten", isOn: $s.inScene)
            } footer: {
                Text("\"Studio an\" schaltet den Beamer ein, \"Studio aus\" schaltet ihn aus.")
            }
        }
    }
}
