// ===========================================================================
//  ClickShare.swift - Studio Control iOS - Barco ClickShare CX-Serie
//  Autor: T. Pfeiffer
//
//  REST API v2:  https://<ip>:4003/v2/<pfad>  (Basic Auth, selbstsigniertes Zertifikat)
//  Port aus sc.py (cs_request / ClickShareModule, aus Q-SYS Plugin ClickShare CX v1.2):
//    GET   configuration/system/device-identity, configuration/system/status,
//          configuration/video-outputs, configuration/input-cards (nur CX-50),
//          configuration/buttons, configuration/peripherals, configuration/video,
//          configuration/audio, configuration/personalization
//    PATCH configuration/video {cecEnabled}, configuration/audio {enabled},
//          configuration/personalization {showNetworkInfo | showWallpaper |
//          theaterMode.enabled | screensaver.timeout}
//    POST  operations/reboot, operations/standby
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct ClickShareSettings: Codable {
    var ip: String = "192.168.1.100"
    var user: String = "admin"
    var password: String = ""
    var buttons: Int = 1
    var pollInterval: Int = 20
    /// Nimmt an der Szene teil ("Studio aus" = Standby)
    var inScene: Bool = false

    enum CodingKeys: String, CodingKey {
        case ip, user, password, buttons, pollInterval, inScene
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ip = try c.decodeIfPresent(String.self, forKey: .ip) ?? "192.168.1.100"
        user = try c.decodeIfPresent(String.self, forKey: .user) ?? "admin"
        password = try c.decodeIfPresent(String.self, forKey: .password) ?? ""
        buttons = try c.decodeIfPresent(Int.self, forKey: .buttons) ?? 1
        pollInterval = try c.decodeIfPresent(Int.self, forKey: .pollInterval) ?? 20
        inScene = try c.decodeIfPresent(Bool.self, forKey: .inScene) ?? false
    }
}

// ---------------------------------------------------------------------------
// Daten
// ---------------------------------------------------------------------------
struct ClickSharePeripheral {
    var name: String
    var inUse: Bool

    var text: String { "\(name.isEmpty ? "?" : name) (\(inUse ? "aktiv" : "bereit"))" }
}

struct ClickShareButton {
    var connected: Bool
    var status: String
    var serial: String
    var mac: String
    var firmware: String
}

struct ClickShareStatus {
    var model: String = ""           // productName
    var modelName: String = ""
    var serial: String = ""
    var article: String = ""
    var hardware: String = ""
    var sharing: Bool? = nil
    var voutConnected: Bool? = nil
    var voutResolution: String = ""
    var vinSupported: Bool = false   // nur CX-50
    var vinSignal: Bool? = nil
    var vinSource: String = ""
    var buttons: [ClickShareButton?] = []
    var camera: ClickSharePeripheral? = nil
    var microphone: ClickSharePeripheral? = nil
    var speaker: ClickSharePeripheral? = nil
    var touch: ClickSharePeripheral? = nil
    var cec: Bool? = nil
    var audio: Bool? = nil
    var netInfo: Bool? = nil
    var wallpaper: Bool? = nil
    var cinema: Bool? = nil
    var saver: String? = nil
}

/// Steuer-Schalter wie in Python (key, Pfad, JSON-Schluessel)
enum ClickShareToggle: String, CaseIterable, Identifiable {
    case cec, audio, net, wall, cinema

    var id: String { rawValue }

    var title: String {
        switch self {
        case .cec: return "CEC"
        case .audio: return "Audio"
        case .net: return "Netzwerk-Info anzeigen"
        case .wall: return "Wallpaper anzeigen"
        case .cinema: return "Cinema-/Theater-Modus"
        }
    }

    var symbol: String {
        switch self {
        case .cec: return "tv"
        case .audio: return "speaker.wave.2.fill"
        case .net: return "network"
        case .wall: return "photo"
        case .cinema: return "film"
        }
    }

    var path: String {
        switch self {
        case .cec: return "configuration/video"
        case .audio: return "configuration/audio"
        case .net, .wall, .cinema: return "configuration/personalization"
        }
    }

    var jsonKey: String {
        switch self {
        case .cec: return "cecEnabled"
        case .audio: return "enabled"
        case .net: return "showNetworkInfo"
        case .wall: return "showWallpaper"
        case .cinema: return "theaterMode"
        }
    }

    func body(_ on: Bool) -> [String: Any] {
        if self == .cinema { return ["theaterMode": ["enabled": on]] }
        return [jsonKey: on]
    }
}

// ---------------------------------------------------------------------------
// JSON-Hilfen (Python-Wahrheitswerte nachbilden)
// ---------------------------------------------------------------------------
enum ClickShareJSON {
    static func truthy(_ v: Any?) -> Bool {
        guard let v = v else { return false }
        if v is NSNull { return false }
        if let s = v as? String { return !s.isEmpty }
        if let n = v as? NSNumber { return n.boolValue }
        if let a = v as? [Any] { return !a.isEmpty }
        if let d = v as? [String: Any] { return !d.isEmpty }
        return true
    }

    static func str(_ v: Any?) -> String {
        guard let v = v else { return "" }
        if v is NSNull { return "" }
        if let s = v as? String { return s }
        if let n = v as? NSNumber { return n.stringValue }
        return "\(v)"
    }

    /// body[0] bei Liste, sonst body bei dict, sonst leer
    static func first(_ j: Any?) -> [String: Any] {
        if let a = j as? [Any] {
            return (a.first as? [String: Any]) ?? [:]
        }
        return (j as? [String: Any]) ?? [:]
    }

    static func dicts(_ v: Any?) -> [[String: Any]] {
        guard let a = v as? [Any] else { return [] }
        return a.compactMap { $0 as? [String: Any] }
    }
}

// ---------------------------------------------------------------------------
// REST-Client (nur Netzwerk)
// ---------------------------------------------------------------------------
struct ClickShareResponse {
    let code: Int
    let json: Any?
}

final class ClickShareAPI {
    private let http = HTTPClient()

    /// wie cs_request(): https://<ip>:4003/v2/<path>, Basic Auth, verify=False
    func request(ip: String, user: String, password: String, method: String, path: String,
                 body: Data? = nil, timeout: TimeInterval = 8) async throws -> ClickShareResponse {
        let host = ip.trimmed
        guard !host.isEmpty, let url = URL(string: "https://\(host):4003/v2/\(path)") else {
            throw NetError.badAddress(host)
        }
        http.user = user
        http.password = password
        http.allowInsecure = true
        // requests sendet Basic Auth sofort mit (nicht erst nach 401)
        let token = Data("\(user):\(password)".utf8).base64EncodedString()
        let headers = ["Content-Type": "application/json",
                       "accept": "*/*",
                       "Authorization": "Basic \(token)"]
        let (d, r) = try await http.request(method, url, headers: headers, body: body, timeout: timeout)
        let json = try? JSONSerialization.jsonObject(with: d, options: [.fragmentsAllowed])
        return ClickShareResponse(code: r.statusCode, json: json)
    }

    // ---- Poll (wie ClickShareModule.do_poll) ----
    func poll(ip: String, user: String, password: String) async throws -> ClickShareStatus {
        func get(_ path: String) async -> ClickShareResponse? {
            try? await request(ip: ip, user: user, password: password, method: "GET", path: path)
        }
        var st = ClickShareStatus()

        // device-identity: entscheidet ueber erreichbar / Anmeldung
        let idr = try await request(ip: ip, user: user, password: password, method: "GET",
                                    path: "configuration/system/device-identity")
        if idr.code == 401 {
            throw NetError.protocolError("Zugangsdaten ungültig (401)")
        }
        guard idr.code == 200, let ident = idr.json as? [String: Any] else {
            throw NetError.http(idr.code, "keine gültige Antwort von device-identity")
        }
        st.model = ClickShareJSON.str(ident["productName"])
        st.modelName = ClickShareJSON.str(ident["modelName"])
        st.serial = ClickShareJSON.str(ident["serialNumber"])
        st.article = ClickShareJSON.str(ident["articleNumber"])
        st.hardware = ClickShareJSON.str(ident["hardwareVersion"])

        // system/status -> sharing
        if let r = await get("configuration/system/status"), r.code == 200, let b = r.json as? [String: Any] {
            st.sharing = ClickShareJSON.truthy(b["sharing"])
        }
        // video-outputs
        if let r = await get("configuration/video-outputs") {
            let vo = ClickShareJSON.first(r.json)
            st.voutConnected = ClickShareJSON.truthy(vo["connected"])
            st.voutResolution = ClickShareJSON.str(vo["preferredResolution"])
        }
        // input-cards (nur CX-50)
        if st.model == "CX-50" {
            st.vinSupported = true
            if let r = await get("configuration/input-cards") {
                let vi = ClickShareJSON.first(r.json)
                st.vinSignal = ClickShareJSON.truthy(vi["hasSignal"])
                st.vinSource = ClickShareJSON.str(vi["sourceName"])
            }
        }
        // buttons
        if let r = await get("configuration/buttons"), let list = r.json as? [Any] {
            st.buttons = list.map { item -> ClickShareButton? in
                guard let b = item as? [String: Any] else { return nil }
                return ClickShareButton(connected: ClickShareJSON.truthy(b["connected"]),
                                        status: ClickShareJSON.str(b["status"]),
                                        serial: ClickShareJSON.str(b["serialNumber"]),
                                        mac: ClickShareJSON.str(b["macAddress"]),
                                        firmware: ClickShareJSON.str(b["firmwareVersion"]))
            }
        }
        // peripherals
        if let r = await get("configuration/peripherals") {
            ClickShareAPI.applyPeripherals(ClickShareJSON.dicts(r.json), to: &st)
        }
        // Steuer-Zustaende
        if let r = await get("configuration/video"), let b = r.json as? [String: Any] {
            st.cec = ClickShareJSON.truthy(b["cecEnabled"])
        }
        if let r = await get("configuration/audio"), let b = r.json as? [String: Any] {
            st.audio = ClickShareJSON.truthy(b["enabled"])
        }
        if let r = await get("configuration/personalization"), let b = r.json as? [String: Any] {
            st.netInfo = ClickShareJSON.truthy(b["showNetworkInfo"])
            st.wallpaper = ClickShareJSON.truthy(b["showWallpaper"])
            if let tm = b["theaterMode"] as? [String: Any] {
                st.cinema = ClickShareJSON.truthy(tm["enabled"])
            } else {
                st.cinema = false
            }
            if let ss = b["screensaver"] as? [String: Any] {
                st.saver = ClickShareJSON.str(ss["timeout"])
            }
        }
        return st
    }

    /// wie _apply_periph(): erstes eingestecktes Geraet je Typ mit "capable"
    static func applyPeripherals(_ list: [[String: Any]], to st: inout ClickShareStatus) {
        var cam: ClickSharePeripheral? = nil
        var mic: ClickSharePeripheral? = nil
        var spk: ClickSharePeripheral? = nil
        var touch: ClickSharePeripheral? = nil
        for p in list {
            if !ClickShareJSON.truthy(p["pluggedIn"]) { continue }
            let name = ClickShareJSON.str(p["name"])
            if cam == nil {
                let cams = ClickShareJSON.dicts(p["cameras"])
                if let c = cams.first(where: { ClickShareJSON.truthy($0["capable"]) }) {
                    cam = ClickSharePeripheral(name: name, inUse: ClickShareJSON.truthy(c["inUse"]))
                }
            }
            if mic == nil {
                let mics = ClickShareJSON.dicts(p["microphones"])
                let spks = ClickShareJSON.dicts(p["speakers"])
                if !mics.isEmpty && !spks.isEmpty {
                    let m = mics.first(where: { ClickShareJSON.truthy($0["capable"]) })
                    let s = spks.first(where: { ClickShareJSON.truthy($0["capable"]) })
                    if let m = m, let s = s {
                        mic = ClickSharePeripheral(name: name, inUse: ClickShareJSON.truthy(m["inUse"]))
                        spk = ClickSharePeripheral(name: name, inUse: ClickShareJSON.truthy(s["inUse"]))
                    }
                }
            }
            if touch == nil {
                let ts = ClickShareJSON.dicts(p["touchscreens"])
                if let t = ts.first(where: { ClickShareJSON.truthy($0["capable"]) }) {
                    touch = ClickSharePeripheral(name: name, inUse: ClickShareJSON.truthy(t["inUse"]))
                }
            }
        }
        st.camera = cam
        st.microphone = mic
        st.speaker = spk
        st.touch = touch
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
@MainActor
final class ClickShareModel: DeviceModel {
    static let saverTimeouts = ["Infinite", "1", "5", "10", "15", "30", "45", "60"]

    @Published var settings = ClickShareSettings()
    @Published var status = ClickShareStatus()
    private let api = ClickShareAPI()
    private var polling = false

    init() {
        super.init(id: "clickshare", title: "ClickShare", subtitle: "Barco ClickShare CX (REST API v2)",
                   symbol: "rectangle.on.rectangle", tint: Color(hex: 0x30B0C7))
    }

    override var pollInterval: Double { Double(max(0, settings.pollInterval)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override var supportsScene: Bool { settings.inScene }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(ClickShareSettings.self, "clickshare") { settings = s }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "clickshare")
    }

    var buttonRows: Int { max(1, settings.buttons) }

    private func call(_ method: String, _ path: String, body: Data? = nil) async throws -> ClickShareResponse {
        try await api.request(ip: settings.ip, user: settings.user.trimmed, password: settings.password,
                              method: method, path: path, body: body)
    }

    override func refresh() async {
        if polling { return }
        polling = true
        defer { polling = false }
        await refreshSafely {
            let st = try await self.api.poll(ip: self.settings.ip, user: self.settings.user.trimmed,
                                             password: self.settings.password)
            self.status = st
            var parts: [String] = []
            if !st.model.isEmpty { parts.append(st.model) }
            if let sh = st.sharing { parts.append(sh ? "Teilt gerade" : "Bereit") }
            self.summary = parts.isEmpty ? "Verbunden" : parts.joined(separator: " · ")
        }
    }

    // ---- Aktionen ----
    func reboot() {
        perform("Neustart gesendet") {
            do {
                let r = try await self.call("POST", "operations/reboot", body: Data())
                if r.code != 200 { throw NetError.http(r.code, "Reboot") }
            } catch let e as NetError {
                throw e
            } catch {
                // Python: Netzfehler (Code 0) gilt als OK - das Geraet trennt beim Neustart
            }
        }
    }

    /// POST operations/standby (wie Python). 404 = Firmware kennt den Endpunkt nicht.
    private func standbyRequest() async throws {
        let r = try await call("POST", "operations/standby", body: Data())
        switch r.code {
        case 200, 202, 204:
            return
        case 404:
            throw NetError.protocolError("Standby nicht unterstützt (404) – Firmware prüfen")
        default:
            throw NetError.http(r.code, "Standby")
        }
    }

    func standby() {
        perform("Standby gesendet") {
            try await self.standbyRequest()
        }
    }

    func toggleState(_ t: ClickShareToggle) -> Bool? {
        switch t {
        case .cec: return status.cec
        case .audio: return status.audio
        case .net: return status.netInfo
        case .wall: return status.wallpaper
        case .cinema: return status.cinema
        }
    }

    private func setLocal(_ t: ClickShareToggle, _ on: Bool) {
        switch t {
        case .cec: status.cec = on
        case .audio: status.audio = on
        case .net: status.netInfo = on
        case .wall: status.wallpaper = on
        case .cinema: status.cinema = on
        }
    }

    func setToggle(_ t: ClickShareToggle, _ on: Bool) {
        setLocal(t, on)
        perform("\(t.title) \(on ? "ein" : "aus")") {
            do {
                let data = try JSONSerialization.data(withJSONObject: t.body(on))
                let r = try await self.call("PATCH", t.path, body: data)
                if r.code != 200 { throw NetError.http(r.code, t.title) }
            } catch {
                await pause(0.3)
                await self.refresh()
                throw error
            }
        }
    }

    func setSaver(_ value: String) {
        status.saver = value
        perform("Screensaver-Timeout \(value)") {
            let data = try JSONSerialization.data(withJSONObject: ["screensaver": ["timeout": value]])
            let r = try await self.call("PATCH", "configuration/personalization", body: data)
            if r.code != 200 { throw NetError.http(r.code, "Screensaver") }
        }
    }

    // ---- Szene: nur "Studio aus" = Standby (die API hat keinen Wake-Endpunkt) ----
    override func scene(_ on: Bool) async throws {
        if on { return }
        try await standbyRequest()
    }

    // ---- Demo (Start mit -demo, ohne Netzwerk) ----
    override func loadDemo() {
        settings.ip = "192.168.1.100"
        settings.user = "admin"
        settings.buttons = 2
        var st = ClickShareStatus()
        st.model = "ClickShare CX-30"
        st.modelName = "C-30"
        st.serial = "1863012345"
        st.article = "R9861523EU"
        st.hardware = "1.0"
        st.sharing = true
        st.voutConnected = true
        st.voutResolution = "1920x1080 @ 60 Hz"
        st.vinSupported = false
        st.buttons = [
            ClickShareButton(connected: true, status: "Teilt gerade", serial: "1872011111",
                             mac: "00:04:A5:12:34:01", firmware: "02.18.01.0010"),
            ClickShareButton(connected: true, status: "Bereit", serial: "1872011112",
                             mac: "00:04:A5:12:34:02", firmware: "02.18.01.0010"),
        ]
        st.camera = ClickSharePeripheral(name: "Logitech MeetUp", inUse: true)
        st.microphone = ClickSharePeripheral(name: "Logitech MeetUp", inUse: true)
        st.speaker = ClickSharePeripheral(name: "Logitech MeetUp", inUse: false)
        st.touch = nil
        st.cec = true
        st.audio = true
        st.netInfo = false
        st.wallpaper = true
        st.cinema = false
        st.saver = "10"
        status = st
        summary = "ClickShare CX-30 · Teilt gerade"
    }
}

// ---------------------------------------------------------------------------
// Oberflaeche
// ---------------------------------------------------------------------------
@MainActor
struct ClickShareView: View {
    @ObservedObject var model: ClickShareModel
    @State private var confirmReboot = false

    init(model: ClickShareModel) {
        _model = ObservedObject(wrappedValue: model)
    }

    private var st: ClickShareStatus { model.status }

    private func yesNo(_ b: Bool?) -> String {
        guard let b = b else { return "–" }
        return b ? "Ja" : "Nein"
    }

    private func dash(_ s: String) -> String { s.isEmpty ? "–" : s }

    private func periph(_ p: ClickSharePeripheral?) -> String { p?.text ?? "nicht verbunden" }

    var body: some View {
        DevicePage(model: model, settings: { ClickShareSettingsView(model: model) }) {
            Section {
                TileGrid {
                    ActionTile(title: "Standby", symbol: "moon.zzz.fill", tint: Color(hex: 0x30B0C7),
                               disabled: model.busy) {
                        model.standby()
                    }
                    ActionTile(title: "Neustart", symbol: "arrow.clockwise", tint: .orange,
                               disabled: model.busy) {
                        confirmReboot = true
                    }
                }
            } header: {
                Text("Steuerung")
            }
            sharingSection
            systemSection
            videoSection
            peripheralSection
            buttonsSection
            controlSection
        }
        .alert("Neustart", isPresented: $confirmReboot) {
            Button("Neu starten", role: .destructive) { model.reboot() }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("ClickShare \(model.settings.ip.trimmed) wirklich neu starten? Laufende Präsentationen brechen ab.")
        }
    }

    private var sharingSection: some View {
        Section {
            HStack(spacing: 12) {
                Image(systemName: st.sharing == true ? "rectangle.on.rectangle.angled" : "rectangle.on.rectangle")
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(st.sharing == true ? Color.green : Color.secondary)
                    .frame(width: 36)
                VStack(alignment: .leading, spacing: 2) {
                    Text(st.sharing == true ? "Es wird geteilt" : (st.sharing == false ? "Kein Sharing aktiv" : "Sharing unbekannt"))
                        .font(.headline)
                    Text(model.state == .online ? "Online" : "Offline")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(.vertical, 4)
        }
    }

    private var systemSection: some View {
        Section("System") {
            ValueRow(label: "Modell", value: dash(st.model), symbol: "rectangle.on.rectangle")
            ValueRow(label: "Modellname", value: dash(st.modelName), symbol: "tag")
            ValueRow(label: "Seriennummer", value: dash(st.serial), symbol: "number")
            ValueRow(label: "Artikelnummer", value: dash(st.article), symbol: "barcode")
            ValueRow(label: "Hardware-Version", value: dash(st.hardware), symbol: "cpu")
        }
    }

    private var videoSection: some View {
        Section("Video") {
            ValueRow(label: "Ausgang verbunden", value: yesNo(st.voutConnected), symbol: "display",
                     valueColor: st.voutConnected == true ? .green : .secondary)
            ValueRow(label: "Bevorzugte Auflösung", value: dash(st.voutResolution), symbol: "aspectratio")
            if st.vinSupported {
                ValueRow(label: "Eingang Signal", value: yesNo(st.vinSignal), symbol: "cable.connector",
                         valueColor: st.vinSignal == true ? .green : .secondary)
                ValueRow(label: "Quelle", value: dash(st.vinSource), symbol: "arrow.right.square")
            } else {
                ValueRow(label: "Eingang", value: "nicht unterstützt", symbol: "cable.connector")
            }
        }
    }

    private var peripheralSection: some View {
        Section("Peripherie") {
            ValueRow(label: "Kamera", value: periph(st.camera), symbol: "video.fill")
            ValueRow(label: "Mikrofon", value: periph(st.microphone), symbol: "mic.fill")
            ValueRow(label: "Lautsprecher", value: periph(st.speaker), symbol: "speaker.wave.2.fill")
            ValueRow(label: "Touchscreen", value: periph(st.touch), symbol: "hand.tap.fill")
        }
    }

    private var buttonsSection: some View {
        Section {
            ForEach(0..<model.buttonRows, id: \.self) { i in
                buttonRow(i)
            }
        } header: {
            Text("Base Units / Buttons")
        } footer: {
            Text("Anzahl der angezeigten Buttons in den Einstellungen (Paired Buttons).")
        }
    }

    private func buttonRow(_ i: Int) -> some View {
        let b: ClickShareButton? = i < st.buttons.count ? st.buttons[i] : nil
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Circle().fill(b?.connected == true ? Color.green : Color.gray.opacity(0.5))
                    .frame(width: 9, height: 9)
                Text("Button \(i + 1)").font(.headline)
                Spacer()
                Text(b == nil ? "Kein Button" : (b?.connected == true ? "Verbunden" : "Nicht verbunden"))
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            if let b = b {
                if !b.status.isEmpty {
                    Text("Status: \(b.status)").font(.caption).foregroundStyle(.secondary)
                }
                Text("SN \(dash(b.serial)) · MAC \(dash(b.mac))")
                    .font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
                Text("Firmware \(dash(b.firmware))").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    private var saverOptions: [String] {
        var opts = ClickShareModel.saverTimeouts
        if let cur = st.saver, !cur.isEmpty, !opts.contains(cur) { opts.append(cur) }
        return opts
    }

    private func saverLabel(_ v: String) -> String {
        v == "Infinite" ? "Nie (Infinite)" : "\(v) min"
    }

    private var controlSection: some View {
        Section {
            ForEach(ClickShareToggle.allCases) { t in
                Toggle(isOn: Binding(get: { model.toggleState(t) ?? false },
                                     set: { v in model.setToggle(t, v) })) {
                    Label(t.title, systemImage: t.symbol)
                }
                .disabled(model.toggleState(t) == nil || model.busy)
            }
            Picker(selection: Binding(get: { st.saver ?? "" }, set: { v in model.setSaver(v) })) {
                if st.saver == nil {
                    Text("–").tag("")
                }
                ForEach(saverOptions, id: \.self) { v in
                    Text(saverLabel(v)).tag(v)
                }
            } label: {
                Label("Screensaver-Timeout", systemImage: "moon.stars")
            }
            .disabled(st.saver == nil || model.busy)
        } header: {
            Text("Einstellungen am Gerät")
        }
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
@MainActor
struct ClickShareSettingsView: View {
    @ObservedObject var model: ClickShareModel
    @State private var s: ClickShareSettings

    init(model: ClickShareModel) {
        _model = ObservedObject(wrappedValue: model)
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "ClickShare", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "IP-Adresse", text: $s.ip, placeholder: "192.168.1.100", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Benutzer", text: $s.user, placeholder: "admin")
                FieldRow(label: "Passwort", text: $s.password, placeholder: "", secure: true)
            } header: {
                Text("Verbindung (HTTPS, Port 4003)")
            } footer: {
                Text("REST API v2 der CX-Serie. Das selbstsignierte Zertifikat wird akzeptiert.")
            }
            Section {
                FieldRow(label: "Paired Buttons", text: intBinding($s.buttons), placeholder: "1", keyboard: .numberPad)
                FieldRow(label: "Poll-Intervall (s)", text: intBinding($s.pollInterval), placeholder: "20",
                         keyboard: .numberPad)
            } header: {
                Text("Anzeige")
            } footer: {
                Text("Poll-Intervall 0 = nur manuell aktualisieren.")
            }
            Section {
                Toggle("An Szenen teilnehmen", isOn: $s.inScene)
            } header: {
                Text("Szenen")
            } footer: {
                Text("\"Studio aus\" schickt die ClickShare in Standby. \"Studio an\" macht nichts – die API hat keinen Aufwach-Befehl, die Einheit wacht beim Teilen oder per Button auf.")
            }
        }
    }
}
