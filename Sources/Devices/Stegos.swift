// ===========================================================================
//  Stegos.swift - Studio Control iOS - Beyerdynamic Stegos RS (Funkmikrofone)
//  Autor: T. Pfeiffer
//
//  Steuerung ueber die Crestron-CP3-Bridge (TCP, ASCII, Zeilenende CR).
//  Port von sc.py "MODUL 3 - STEGOS" (StgTcpClient, StegosModule).
//  Dauerhafte TCP-Verbindung mit Lese-Schleife, die Rueckmeldungen
//  (CHnVOL, CHnBAT, CHnBLVL, CHnMID, CHnACT, CHnMUTE, CHnSYNC, GMUTE, RF, MVOL)
//  auswertet. Die PC-Pegelmessung (sounddevice/ASIO) ist auf dem iPhone
//  nicht moeglich und daher nicht portiert.
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct StegosPresetEntry: Codable, Hashable {
    var vol: Int
    var mute: Bool
}

struct StegosSettings: Codable {
    var ip: String = StegosProto.defaultIP
    var port: Int = StegosProto.defaultPort
    var names: [String] = ["Mic 1", "Mic 2", "Mic 3", "Mic 4"]
    /// Presets wie in stegos_config.json: Name -> { "1": {vol, mute}, ... }
    var presets: [String: [String: StegosPresetEntry]] = [:]

    init() {}

    enum CodingKeys: String, CodingKey {
        case ip, port, names, presets
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ip = try c.decodeIfPresent(String.self, forKey: .ip) ?? StegosProto.defaultIP
        port = try c.decodeIfPresent(Int.self, forKey: .port) ?? StegosProto.defaultPort
        names = try c.decodeIfPresent([String].self, forKey: .names) ?? ["Mic 1", "Mic 2", "Mic 3", "Mic 4"]
        presets = try c.decodeIfPresent([String: [String: StegosPresetEntry]].self, forKey: .presets) ?? [:]
    }

    func name(_ ch: Int) -> String {
        let i = ch - 1
        if i >= 0 && i < names.count && !names[i].trimmed.isEmpty { return names[i] }
        return "Mic \(ch)"
    }
}

// ---------------------------------------------------------------------------
// Protokoll (STG_PROTO / STG_FB_CH / STG_FB_G)
// ---------------------------------------------------------------------------
enum StegosProto {
    static let defaultIP = "192.168.1.120"
    static let defaultPort = 5001
    static let chCount = 4
    static let volMin = 0
    static let volMax = 100
    static let eol = "\r"

    static func chActive(_ ch: Int, _ st: String) -> String { "CH\(ch)A\(st)" }
    static func chMute(_ ch: Int, _ st: String) -> String { "CH\(ch)M\(st)" }
    static func chVolUp(_ ch: Int) -> String { "CH\(ch)VU" }
    static func chVolDown(_ ch: Int) -> String { "CH\(ch)VD" }
    static func chVolSet(_ ch: Int, _ val: Int) -> String { "CH\(ch)V=\(val)" }
    static func gMute(_ st: String) -> String { "GM\(st)" }
    static let mVolUp = "MVU"
    static let mVolDown = "MVD"
    static func mVolSet(_ val: Int) -> String { "MV=\(val)" }
    static let powerOff = "POFF"
    static func rf(_ band: String) -> String { "RF\(band)" }
    static let pollCh = "?CH"
    static let pollMute = "?MU"
    static let pollVol = "?VL"
    static let pollBat = "?BT"
    static let pollRF = "?RF"
    static let pollAlloc = "?AL"
    static let pollAllKeys: [String] = [pollCh, pollMute, pollVol, pollBat, pollRF, pollAlloc]

    static let battText: [String: String] = ["N": "Kein", "T": "Trickle", "F": "Fast", "E": "Fehler"]
    static let rfText: [String: String] = ["H": "High", "M": "Mid", "L": "Low"]
}

/// Eine ausgewertete Rueckmeldezeile.
enum StegosFeedback {
    case gmute(Bool)
    case rf(String)
    case mvol(Int)
    case vol(Int, Int)
    case bat(Int, String)
    case blvl(Int, Int, String)
    case mid(Int, String)
    case act(Int, Bool)
    case mute(Int, Bool)
    case sync(Int, Bool)

    /// Gleiche Reihenfolge und Muster wie _parse_fb in sc.py (Gross/Klein egal).
    static func parse(_ raw: String) -> StegosFeedback? {
        let up = raw.uppercased()
        func rest(_ prefix: String) -> String? {
            guard up.hasPrefix(prefix) else { return nil }
            return String(raw.dropFirst(prefix.count))
        }
        if let r = rest("GMUTE="), let c = r.first, c == "0" || c == "1" {
            return .gmute(c == "1")
        }
        if let r = rest("RF="), let c = r.uppercased().first, "HML".contains(c) {
            return .rf(String(c))
        }
        if let r = rest("MVOL="), let v = leadingInt(r) {
            return .mvol(v)
        }
        guard up.hasPrefix("CH"), up.count >= 3 else { return nil }
        let chChar = up[up.index(up.startIndex, offsetBy: 2)]
        guard let ch = Int(String(chChar)), ch >= 1, ch <= 4 else { return nil }
        let tailRaw = String(raw.dropFirst(3))
        let tail = tailRaw.uppercased()
        func sub(_ key: String) -> String? {
            guard tail.hasPrefix(key) else { return nil }
            return String(tailRaw.dropFirst(key.count))
        }
        if let r = sub("VOL="), let v = leadingInt(r) { return .vol(ch, v) }
        if let r = sub("BAT="), let c = r.uppercased().first, "NTFE".contains(c) { return .bat(ch, String(c)) }
        if let r = sub("BLVL="), let v = leadingInt(r), v >= 0 {
            let digits = String(r.prefix(while: { $0.isASCII && $0.isNumber }))
            return .blvl(ch, v, digits)
        }
        if let r = sub("MID=") {
            let v = String(r.prefix(while: { !$0.isWhitespace }))
            return .mid(ch, v.trimmed)
        }
        if let r = sub("ACT="), let c = r.first, c == "0" || c == "1" { return .act(ch, c == "1") }
        if let r = sub("MUTE="), let c = r.first, c == "0" || c == "1" { return .mute(ch, c == "1") }
        if let r = sub("SYNC="), let c = r.first, c == "0" || c == "1" { return .sync(ch, c == "1") }
        return nil
    }

    /// "-?\d+" am Anfang
    static func leadingInt(_ s: String) -> Int? {
        var t = Substring(s)
        var neg = false
        if t.first == "-" { neg = true; t = t.dropFirst() }
        let digits = t.prefix(while: { $0.isASCII && $0.isNumber })
        guard !digits.isEmpty, let v = Int(digits) else { return nil }
        return neg ? -v : v
    }
}

/// Zustand eines Kanals aus den Rueckmeldungen.
struct StegosChannelState {
    var vol: Int? = nil          // nil = unbekannt; negativ = "-"
    var mute: Bool? = nil
    var active: Bool? = nil
    var batStat: String? = nil
    var batLvlText: String? = nil
    var batPct: Double? = nil    // 0...100
    var muid: String = "-"
    var sync: String = "-"
    var rf: String = "-"

    var volText: String {
        guard let v = vol else { return "-" }
        return v < 0 ? "-" : String(v)
    }

    var battText: String {
        if batStat == nil && batLvlText == nil { return "-" }
        var t = "?"
        if let s = batStat { t = StegosProto.battText[s] ?? s }
        if let l = batLvlText { t += " (\(l))" }
        return t
    }
}

struct StegosMonitorLine: Identifiable {
    enum Kind { case tx, rx, err, sys }
    let id = UUID()
    let time: Date
    let kind: Kind
    let text: String
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
@MainActor
final class StegosModel: DeviceModel {
    @Published var settings = StegosSettings()
    @Published var channels: [StegosChannelState] = Array(repeating: StegosChannelState(), count: StegosProto.chCount)
    @Published var sliders: [Double] = Array(repeating: 50, count: StegosProto.chCount)
    @Published var masterSlider: Double = 50
    @Published var gmute: Bool? = nil
    @Published var rfBand: String = "-"
    @Published var mvol: Int? = nil
    @Published var connected = false
    @Published var monitor: [StegosMonitorLine] = []

    /// Wird von der Ansicht gesetzt: Seite sichtbar -> Verbindung halten
    var pageVisible = false

    private var conn: TCPConnection?
    private var readerTask: Task<Void, Never>?
    private var connecting = false
    private var editing = Set<Int>()          // 0..3 Kanaele, 4 = Master
    private var lastSent: [Int: Int] = [:]    // wie ch_last_sent / m_last_sent

    init() {
        super.init(id: "stegos", title: "Mics", subtitle: "Beyerdynamic Stegos RS",
                   symbol: "mic.fill", tint: Color(hex: 0xFF375F))
    }

    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty && settings.port > 0 }
    override var pollInterval: Double { 15 }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(StegosSettings.self, "stegos") { settings = s }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "stegos")
        // neue Adresse -> beim naechsten Aktualisieren neu verbinden
        if conn != nil { closeConnection(note: "Getrennt (Einstellungen geaendert)") }
    }

    // ---- Verbindung ----
    func ensureConnected() async throws {
        var waited = 0
        while connecting && waited < 100 {
            await pause(0.05)
            waited += 1
        }
        if let c = conn, !c.isClosed { return }
        if conn != nil { closeConnection(note: nil) }
        connecting = true
        defer { connecting = false }
        guard let p = UInt16(exactly: settings.port), p > 0 else {
            throw NetError.badAddress("\(settings.ip):\(settings.port)")
        }
        let c = try TCPConnection(host: settings.ip, port: p)
        do {
            try await c.connect(timeout: 4)
        } catch {
            c.close()
            mon(.err, "Verbindung fehlgeschlagen: \(DeviceModel.describe(error))")
            throw error
        }
        conn = c
        connected = true
        mon(.sys, "Verbunden mit \(settings.ip.trimmed):\(settings.port)")
        readerTask = Task { [weak self] in
            await self?.readLoop(c)
        }
    }

    private func closeConnection(note: String?) {
        readerTask?.cancel()
        readerTask = nil
        conn?.close()
        conn = nil
        connected = false
        if let n = note { mon(.sys, n) }
    }

    override func disconnect() {
        if conn != nil { closeConnection(note: "Getrennt") }
    }

    func toggleConnection() {
        if connected {
            disconnect()
        } else {
            perform("Verbinden") {
                try await self.ensureConnected()
                try await self.pollAll()
            }
        }
    }

    /// Lese-Schleife: trennt an CR oder LF wie StgTcpClient._read_loop.
    private func readLoop(_ c: TCPConnection) async {
        var buf = Data()
        while !Task.isCancelled {
            let d = await c.readAvailable(wait: 0.25, settle: 0.02)
            if !d.isEmpty {
                buf.append(d)
                while let i = buf.firstIndex(where: { $0 == 0x0D || $0 == 0x0A }) {
                    let lineData = Data(buf[buf.startIndex..<i].filter { $0 < 0x80 })
                    buf.removeSubrange(buf.startIndex...i)
                    let line = String(decoding: lineData, as: UTF8.self).trimmed
                    if !line.isEmpty {
                        mon(.rx, line)
                        handle(line)
                    }
                }
                if buf.count > 65536 { buf.removeAll() }
            } else if c.isClosed {
                break
            }
        }
        if !Task.isCancelled, conn === c {
            conn = nil
            connected = false
            readerTask = nil
            mon(.err, "Verbindung von der Gegenstelle beendet")
            summary = "Getrennt"
        }
    }

    // ---- Senden ----
    func sendLine(_ text: String) async throws {
        if conn == nil || conn?.isClosed == true {
            try await ensureConnected()
        }
        guard let c = conn else {
            mon(.err, "Nicht verbunden - '\(text)' nicht gesendet")
            throw NetError.closed
        }
        do {
            try await c.send(text + StegosProto.eol, encoding: .ascii)
            mon(.tx, text)
        } catch {
            mon(.err, "Sendefehler: \(DeviceModel.describe(error))")
            closeConnection(note: "Getrennt")
            throw error
        }
    }

    func cmd(_ text: String, _ label: String) {
        perform(label) { try await self.sendLine(text) }
    }

    func pollAll() async throws {
        for k in StegosProto.pollAllKeys {
            try await sendLine(k)
        }
    }

    // ---- Aktionen ----
    func setMute(_ ch: Int, _ on: Bool) {
        cmd(StegosProto.chMute(ch, on ? "1" : "0"), "\(settings.name(ch)): \(on ? "stumm" : "offen")")
    }

    func setActive(_ ch: Int, _ on: Bool) {
        cmd(StegosProto.chActive(ch, on ? "1" : "0"), "\(settings.name(ch)): \(on ? "aktiv" : "inaktiv")")
    }

    func sliderEditing(_ idx: Int, _ isEditing: Bool) {
        if isEditing {
            editing.insert(idx)
            return
        }
        editing.remove(idx)
        if idx == 4 {
            let iv = Int(masterSlider.rounded())
            if lastSent[4] != iv {
                lastSent[4] = iv
                cmd(StegosProto.mVolSet(iv), "Master-Lautstaerke \(iv)")
            }
        } else if idx >= 0 && idx < StegosProto.chCount {
            let iv = Int(sliders[idx].rounded())
            if lastSent[idx] != iv {
                lastSent[idx] = iv
                let ch = idx + 1
                cmd(StegosProto.chVolSet(ch, iv), "\(settings.name(ch)): Lautstaerke \(iv)")
            }
        }
    }

    // ---- Presets (client-seitig, wie _preset_save/_preset_recall) ----
    var presetNames: [String] { settings.presets.keys.sorted() }

    func savePreset(_ rawName: String) {
        let name = rawName.trimmed
        guard !name.isEmpty else {
            addLog("Bitte einen Preset-Namen eingeben.", error: true)
            return
        }
        var snap: [String: StegosPresetEntry] = [:]
        for ch in 1...StegosProto.chCount {
            let st = channels[ch - 1]
            var vol = Int(sliders[ch - 1].rounded())
            if let v = st.vol, v >= 0 { vol = v }
            snap[String(ch)] = StegosPresetEntry(vol: vol, mute: st.mute == true)
        }
        settings.presets[name] = snap
        SecureStore.saveCodable(settings, "stegos")
        addLog("Preset '\(name)' gespeichert (\(StegosProto.chCount) Kanaele).")
        Haptics.success()
    }

    func recallPreset(_ name: String) {
        guard let snap = settings.presets[name] else {
            addLog("Preset '\(name)' nicht gefunden.", error: true)
            return
        }
        perform("Preset '\(name)' abgerufen") {
            if self.conn == nil { try await self.ensureConnected() }
            let keys = snap.keys.sorted { (Int($0) ?? 0) < (Int($1) ?? 0) }
            for k in keys {
                guard let ch = Int(k), ch >= 1, ch <= StegosProto.chCount, let e = snap[k] else { continue }
                try await self.sendLine(StegosProto.chVolSet(ch, e.vol))
                self.sliders[ch - 1] = Double(e.vol)
                self.lastSent[ch - 1] = e.vol
                try await self.sendLine(StegosProto.chMute(ch, e.mute ? "1" : "0"))
            }
        }
    }

    func deletePreset(_ name: String) {
        guard settings.presets[name] != nil else { return }
        settings.presets.removeValue(forKey: name)
        SecureStore.saveCodable(settings, "stegos")
        addLog("Preset '\(name)' geloescht.")
    }

    // ---- Rueckmeldungen ----
    private func handle(_ line: String) {
        guard let fb = StegosFeedback.parse(line) else { return }
        switch fb {
        case .gmute(let on):
            gmute = on
        case .rf(let band):
            let t = StegosProto.rfText[band] ?? band
            rfBand = t
            for i in 0..<channels.count { channels[i].rf = t }
        case .mvol(let v):
            mvol = v
            if v >= 0 && !editing.contains(4) { masterSlider = Double(min(StegosProto.volMax, v)) }
        case .vol(let ch, let v):
            channels[ch - 1].vol = v
            if v >= 0 && !editing.contains(ch - 1) { sliders[ch - 1] = Double(min(StegosProto.volMax, v)) }
        case .bat(let ch, let st):
            channels[ch - 1].batStat = st
        case .blvl(let ch, let lv, let txt):
            channels[ch - 1].batLvlText = txt
            // Annahme wie in sc.py: Prozent; Werte 0..5 als Balkenstufen (x20 %)
            let pct = lv <= 5 ? lv * 20 : min(100, lv)
            channels[ch - 1].batPct = Double(pct)
        case .mid(let ch, let mid):
            channels[ch - 1].muid = mid.isEmpty ? "-" : mid
            channels[ch - 1].sync = mid.isEmpty ? "frei" : "belegt"
        case .act(let ch, let on):
            channels[ch - 1].active = on
        case .mute(let ch, let on):
            channels[ch - 1].mute = on
        case .sync(let ch, let on):
            channels[ch - 1].sync = on ? "used" : "sync"
        }
        summary = makeSummary()
        lastUpdate = Date()
    }

    private func makeSummary() -> String {
        if !connected { return "Getrennt" }
        let muted = channels.filter { $0.mute == true }.count
        let active = channels.filter { $0.active == true }.count
        var parts: [String] = []
        if channels.contains(where: { $0.active != nil }) { parts.append("\(active) aktiv") }
        if channels.contains(where: { $0.mute != nil }) { parts.append("\(muted) stumm") }
        if gmute == true { parts.append("Global stumm") }
        if let m = mvol, m >= 0 { parts.append("Master \(m)") }
        return parts.isEmpty ? "Verbunden" : parts.joined(separator: " · ")
    }

    private func mon(_ kind: StegosMonitorLine.Kind, _ text: String) {
        monitor.insert(StegosMonitorLine(time: Date(), kind: kind, text: text), at: 0)
        if monitor.count > 300 { monitor.removeLast(monitor.count - 300) }
    }

    func clearMonitor() { monitor.removeAll() }

    // ---- Status ----
    override func refresh() async {
        await refreshSafely {
            if self.pageVisible || self.conn != nil {
                try await self.ensureConnected()
                try await self.pollAll()
                self.summary = self.makeSummary()
            } else {
                guard let p = UInt16(exactly: self.settings.port) else {
                    throw NetError.badAddress("\(self.settings.ip):\(self.settings.port)")
                }
                let ok = await TCPConnection.probe(host: self.settings.ip.trimmed, port: p)
                if !ok { throw NetError.protocolError("CP3-Bridge nicht erreichbar") }
                self.summary = "Bridge erreichbar"
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Ansicht
// ---------------------------------------------------------------------------
struct StegosView: View {
    @ObservedObject var model: StegosModel
    @State private var showPowerOff = false
    @State private var presetName = ""
    @State private var showMonitor = false

    var body: some View {
        DevicePage(model: model, settings: { StegosSettingsView(model: model) }) {
            Group {
                connectionSection
                ForEach(1...StegosProto.chCount, id: \.self) { ch in
                    StegosChannelSection(model: model, ch: ch)
                }
                masterSection
                rfSection
            }
            Group {
                presetSection
                pollSection
                monitorSection
            }
        }
        .onAppear {
            model.pageVisible = true
            if !model.connected {
                Task { await model.refresh() }
            }
        }
        .onDisappear {
            model.pageVisible = false
            model.disconnect()
        }
        .confirmationDialog("Alle Mikrofone ausschalten?", isPresented: $showPowerOff, titleVisibility: .visible) {
            Button("Mikrofone ausschalten", role: .destructive) {
                model.cmd(StegosProto.powerOff, "Mikrofone ausgeschaltet (POFF)")
            }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    private var connectionSection: some View {
        Section("Verbindung") {
            ValueRow(label: "CP3-Bridge", value: "\(model.settings.ip):\(model.settings.port)", symbol: "network")
            HStack {
                Label(model.connected ? "Verbunden" : "Getrennt",
                      systemImage: model.connected ? "checkmark.circle.fill" : "xmark.circle")
                    .foregroundStyle(model.connected ? Color.green : Color.secondary)
                Spacer()
                Button(model.connected ? "Trennen" : "Verbinden") {
                    model.toggleConnection()
                }
                .buttonStyle(.borderless)
            }
        }
    }

    private var masterSection: some View {
        Section("Master / Global") {
            HStack(spacing: 12) {
                Button {
                    model.cmd(StegosProto.mVolDown, "Master leiser")
                } label: {
                    Image(systemName: "minus.circle.fill").font(.title3)
                }
                .buttonStyle(.borderless)
                Slider(value: $model.masterSlider, in: 0...100, step: 1, onEditingChanged: { editing in
                    model.sliderEditing(4, editing)
                })
                Button {
                    model.cmd(StegosProto.mVolUp, "Master lauter")
                } label: {
                    Image(systemName: "plus.circle.fill").font(.title3)
                }
                .buttonStyle(.borderless)
                Text("\(Int(model.masterSlider))")
                    .font(.body.monospacedDigit())
                    .frame(width: 36, alignment: .trailing)
            }
            HStack {
                Text("Master (Rückmeldung)").font(.footnote).foregroundStyle(.secondary)
                LevelBar(value: Double(max(0, model.mvol ?? 0)) / 100.0, tint: .blue)
                Text(mvolText).font(.footnote.monospacedDigit()).foregroundStyle(.secondary)
            }
            ValueRow(label: "Global Mute", value: gmuteText, symbol: "speaker.slash")
            TileGrid(columns: 2) {
                ActionTile(title: "Global stumm", symbol: "mic.slash.fill", tint: .red, active: model.gmute == true) {
                    model.cmd(StegosProto.gMute("1"), "Global stumm")
                }
                ActionTile(title: "Global offen", symbol: "mic.fill", tint: .green, active: model.gmute == false) {
                    model.cmd(StegosProto.gMute("0"), "Global offen")
                }
                ActionTile(title: "Global umschalten", symbol: "arrow.left.arrow.right", tint: .orange) {
                    model.cmd(StegosProto.gMute("T"), "Global Mute umgeschaltet")
                }
                ActionTile(title: "Mics ausschalten", symbol: "power", tint: .red) {
                    showPowerOff = true
                }
            }
        }
    }

    private var rfSection: some View {
        Section("Funkband") {
            ValueRow(label: "RF-Band", value: model.rfBand, symbol: "antenna.radiowaves.left.and.right")
            TileGrid(columns: 3) {
                ActionTile(title: "High", symbol: "arrow.up", tint: .purple, active: model.rfBand == "High") {
                    model.cmd(StegosProto.rf("H"), "RF-Band High")
                }
                ActionTile(title: "Mid", symbol: "equal", tint: .purple, active: model.rfBand == "Mid") {
                    model.cmd(StegosProto.rf("M"), "RF-Band Mid")
                }
                ActionTile(title: "Low", symbol: "arrow.down", tint: .purple, active: model.rfBand == "Low") {
                    model.cmd(StegosProto.rf("L"), "RF-Band Low")
                }
            }
        }
    }

    private var presetSection: some View {
        Section {
            ForEach(model.presetNames, id: \.self) { name in
                HStack {
                    Label(name, systemImage: "slider.horizontal.3")
                    Spacer()
                    Button("Abrufen") { model.recallPreset(name) }
                        .buttonStyle(.borderless)
                }
                .swipeActions {
                    Button(role: .destructive) {
                        model.deletePreset(name)
                    } label: {
                        Label("Löschen", systemImage: "trash")
                    }
                }
            }
            HStack {
                TextField("Neuer Preset-Name", text: $presetName)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Speichern") {
                    model.savePreset(presetName)
                    presetName = ""
                }
                .buttonStyle(.borderless)
                .disabled(presetName.trimmed.isEmpty)
            }
        } header: {
            Text("Presets")
        } footer: {
            Text("Speichert je Kanal Lautstärke + Mute-Zustand und stellt sie beim Abrufen über die normalen CH..V= / CH..M-Befehle wieder her.")
        }
    }

    private var pollSection: some View {
        Section("Abfrage") {
            TileGrid(columns: 3) {
                ActionTile(title: "Kanal", symbol: "questionmark.circle") { model.cmd(StegosProto.pollCh, "Abfrage Kanal") }
                ActionTile(title: "Mute", symbol: "questionmark.circle") { model.cmd(StegosProto.pollMute, "Abfrage Mute") }
                ActionTile(title: "Vol", symbol: "questionmark.circle") { model.cmd(StegosProto.pollVol, "Abfrage Vol") }
                ActionTile(title: "Batt", symbol: "questionmark.circle") { model.cmd(StegosProto.pollBat, "Abfrage Batt") }
                ActionTile(title: "RF", symbol: "questionmark.circle") { model.cmd(StegosProto.pollRF, "Abfrage RF") }
                ActionTile(title: "Alloc", symbol: "questionmark.circle") { model.cmd(StegosProto.pollAlloc, "Abfrage Alloc") }
            }
            Button {
                model.perform("Alle abgefragt") { try await model.pollAll() }
            } label: {
                Label("Alle abfragen", systemImage: "arrow.clockwise")
            }
        }
    }

    private var monitorSection: some View {
        Section {
            DisclosureGroup(isExpanded: $showMonitor) {
                if model.monitor.isEmpty {
                    Text("Noch keine Daten").font(.footnote).foregroundStyle(.secondary)
                }
                ForEach(model.monitor.prefix(120)) { line in
                    Text(monPrefix(line.kind) + line.text)
                        .font(.caption.monospaced())
                        .foregroundStyle(monColor(line.kind))
                        .textSelection(.enabled)
                }
                Button("Monitor leeren") { model.clearMonitor() }
            } label: {
                Label("ASCII-Monitor", systemImage: "terminal")
            }
        }
    }

    private var gmuteText: String {
        guard let g = model.gmute else { return "-" }
        return g ? "Mute" : "offen"
    }

    private var mvolText: String {
        guard let m = model.mvol else { return "-" }
        return m < 0 ? "-" : String(m)
    }

    private func monPrefix(_ k: StegosMonitorLine.Kind) -> String {
        switch k {
        case .tx: return ">> "
        case .rx: return "<< "
        case .err: return "!! "
        case .sys: return "-- "
        }
    }

    private func monColor(_ k: StegosMonitorLine.Kind) -> Color {
        switch k {
        case .tx: return .green
        case .rx: return .blue
        case .err: return .red
        case .sys: return .secondary
        }
    }
}

/// Karte eines Mikrofonkanals.
struct StegosChannelSection: View {
    @ObservedObject var model: StegosModel
    let ch: Int

    private var st: StegosChannelState { model.channels[ch - 1] }

    var body: some View {
        Section {
            Toggle(isOn: Binding(get: { st.mute == true }, set: { v in Haptics.tap(); model.setMute(ch, v) })) {
                Label("Stumm", systemImage: st.mute == true ? "mic.slash.fill" : "mic.fill")
            }
            .tint(.red)
            Toggle(isOn: Binding(get: { st.active == true }, set: { v in Haptics.tap(); model.setActive(ch, v) })) {
                Label("Aktiv", systemImage: "dot.radiowaves.left.and.right")
            }
            .tint(.green)
            HStack(spacing: 12) {
                Button {
                    model.cmd(StegosProto.chVolDown(ch), "\(model.settings.name(ch)): leiser")
                } label: {
                    Image(systemName: "minus.circle.fill").font(.title3)
                }
                .buttonStyle(.borderless)
                Slider(value: $model.sliders[ch - 1], in: 0...100, step: 1, onEditingChanged: { editing in
                    model.sliderEditing(ch - 1, editing)
                })
                Button {
                    model.cmd(StegosProto.chVolUp(ch), "\(model.settings.name(ch)): lauter")
                } label: {
                    Image(systemName: "plus.circle.fill").font(.title3)
                }
                .buttonStyle(.borderless)
                Text("\(Int(model.sliders[ch - 1]))")
                    .font(.body.monospacedDigit())
                    .frame(width: 36, alignment: .trailing)
            }
            HStack {
                Text("Vol").font(.footnote).foregroundStyle(.secondary).frame(width: 44, alignment: .leading)
                LevelBar(value: Double(max(0, st.vol ?? 0)) / 100.0, tint: .blue)
                Text(st.volText).font(.footnote.monospacedDigit()).foregroundStyle(.secondary)
                    .frame(width: 36, alignment: .trailing)
            }
            HStack {
                Text("Akku").font(.footnote).foregroundStyle(.secondary).frame(width: 44, alignment: .leading)
                LevelBar(value: (st.batPct ?? 0) / 100.0, tint: battColor)
                Text(st.battText).font(.footnote).foregroundStyle(.secondary)
            }
            Text("MU-ID \(st.muid) · Sync \(st.sync) · RF \(st.rf)")
                .font(.caption).foregroundStyle(.secondary)
        } header: {
            HStack {
                Text("\(ch) · \(model.settings.name(ch))")
                Spacer()
                Menu {
                    Button("Aktiv umschalten") { model.cmd(StegosProto.chActive(ch, "T"), "\(model.settings.name(ch)): Aktiv umgeschaltet") }
                    Button("Mute umschalten") { model.cmd(StegosProto.chMute(ch, "T"), "\(model.settings.name(ch)): Mute umgeschaltet") }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
    }

    private var battColor: Color {
        let v = st.batPct ?? 0
        if v > 40 { return .green }
        if v > 20 { return .yellow }
        return .red
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct StegosSettingsView: View {
    @ObservedObject var model: StegosModel
    @State private var s: StegosSettings

    init(model: StegosModel) {
        self.model = model
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "Stegos", onSave: {
            while s.names.count < StegosProto.chCount { s.names.append("Mic \(s.names.count + 1)") }
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "IP-Adresse", text: $s.ip, placeholder: StegosProto.defaultIP, keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($s.port), placeholder: String(StegosProto.defaultPort), keyboard: .numberPad)
            } header: {
                Text("CP3-Bridge (TCP ASCII)")
            } footer: {
                Text("Die CP3 setzt die ASCII-Befehle auf den Stegos RS um. Standard: \(StegosProto.defaultIP):\(StegosProto.defaultPort)")
            }
            Section("Kanalnamen") {
                ForEach(0..<StegosProto.chCount, id: \.self) { i in
                    FieldRow(label: "Kanal \(i + 1)", text: nameBinding(i), placeholder: "Mic \(i + 1)")
                }
            }
        }
    }

    private func nameBinding(_ i: Int) -> Binding<String> {
        Binding(get: {
            i < s.names.count ? s.names[i] : ""
        }, set: { v in
            while s.names.count <= i { s.names.append("Mic \(s.names.count + 1)") }
            s.names[i] = v
        })
    }
}
