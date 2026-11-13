// ===========================================================================
//  Touchpanel.swift - Studio Control iOS - Crestron TSW-770 Emulator (CIP)
//  Autor: T. Pfeiffer
//
//  Das iPhone meldet sich als Touchpanel (IP-ID) per CIP an einer Crestron
//  CP3 an (TCP 41794). Port von sc.py "MODUL 8 - TOUCHPANEL"
//  (CIPPanel, RelayToggle, TouchpanelModule).
//  - Registrierung auf Typ 0F, Update Request nach Typ 02 (00 00 00 1F)
//  - End-of-Query -> EOQ-Ack + Heartbeat, Panel ONLINE
//  - Heartbeat alle 15 s nach dem letzten Senden, gehaltene Tasten alle 0,5 s
//  - Digital/Analog/Serial in beide Richtungen, RX-Puffer ueber Segmentgrenzen
//  - Neuverbindung nach Abbruch
//  Die Remote-API (TCP-Server fuer Q-SYS) ist nicht portiert: eine iPhone-App
//  kann im Hintergrund keinen dauerhaften TCP-Server betreiben.
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Konstanten (TP_DEF_* in sc.py)
// ---------------------------------------------------------------------------
enum TouchpanelConst {
    static let defHost = "192.168.1.100"
    static let defPort = 41794
    static let defIPID = "03"
    static let relayCount = 8

    static func hex2(_ v: Int) -> String {
        let h = String(v & 0xFF, radix: 16)
        return h.count < 2 ? "0" + h : h
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct TouchpanelRelay: Codable, Identifiable, Hashable {
    var id = UUID()
    var label: String
    var join: Int
    /// false = Toggle (Puls wie RelayToggle), true = Taster (Press/Release)
    var momentary: Bool = false

    init(label: String, join: Int, momentary: Bool = false) {
        self.label = label
        self.join = join
        self.momentary = momentary
    }

    enum CodingKeys: String, CodingKey {
        case id, label, join, momentary
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        label = try c.decodeIfPresent(String.self, forKey: .label) ?? "Relais"
        join = try c.decodeIfPresent(Int.self, forKey: .join) ?? 1
        momentary = try c.decodeIfPresent(Bool.self, forKey: .momentary) ?? false
    }
}

struct TouchpanelSettings: Codable {
    var host: String = TouchpanelConst.defHost
    var port: Int = TouchpanelConst.defPort
    var ipid: String = TouchpanelConst.defIPID
    var localPreview: Bool = true
    var debug: Bool = true
    var relays: [TouchpanelRelay] = TouchpanelSettings.defaultRelays()
    /// Szenen wie in touchpanel_config.json: Name -> Relaiszustaende
    var scenes: [String: [Bool]] = [:]

    init() {}

    static func defaultRelays() -> [TouchpanelRelay] {
        (1...TouchpanelConst.relayCount).map { TouchpanelRelay(label: "Relais \($0)", join: $0) }
    }

    enum CodingKeys: String, CodingKey {
        case host, port, ipid, localPreview, debug, relays, scenes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        host = try c.decodeIfPresent(String.self, forKey: .host) ?? TouchpanelConst.defHost
        port = try c.decodeIfPresent(Int.self, forKey: .port) ?? TouchpanelConst.defPort
        ipid = try c.decodeIfPresent(String.self, forKey: .ipid) ?? TouchpanelConst.defIPID
        localPreview = try c.decodeIfPresent(Bool.self, forKey: .localPreview) ?? true
        debug = try c.decodeIfPresent(Bool.self, forKey: .debug) ?? true
        relays = try c.decodeIfPresent([TouchpanelRelay].self, forKey: .relays) ?? TouchpanelSettings.defaultRelays()
        scenes = try c.decodeIfPresent([String: [Bool]].self, forKey: .scenes) ?? [:]
    }
}

// ---------------------------------------------------------------------------
// CIP-Client (wie CIPPanel in sc.py)
// ---------------------------------------------------------------------------
@MainActor
final class TouchpanelCIP {
    static let txDigital: [UInt8] = [0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x00]
    static let txDigitalButton: [UInt8] = [0x05, 0x00, 0x06, 0x00, 0x00, 0x03, 0x27]
    static let txAnalog: [UInt8] = [0x05, 0x00, 0x08, 0x00, 0x00, 0x05, 0x14]
    static let txSerial: [UInt8] = [0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x34]
    static let heartbeat = Data([0x0D, 0x00, 0x02, 0x00, 0x00])
    static let updateReq = Data([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x00])
    static let eoqAck = Data([0x05, 0x00, 0x05, 0x00, 0x00, 0x02, 0x03, 0x1D])

    var host = TouchpanelConst.defHost
    var port: UInt16 = UInt16(TouchpanelConst.defPort)
    var ipid: UInt8 = 0x03

    /// (Text, raw) - raw = Detail (Hex/Heartbeat), nur im Debug-Modus zeigen
    var onLog: ((String, Bool) -> Void)?
    var onLink: ((Bool) -> Void)?
    var onDigital: ((Int, Bool) -> Void)?
    var onAnalog: ((Int, Int) -> Void)?
    var onSerial: ((Int, String) -> Void)?

    private(set) var running = false
    private(set) var connected = false
    private var link = false
    private var restart = false
    private var gen = 0
    private var conn: TCPConnection?
    private var loopTask: Task<Void, Never>?
    private var rxbuf: [UInt8] = []
    private var txQueue: [Data] = []
    private var txBusy = false
    private var lastTx = Date()
    private var lastBtn = Date()
    private var buttonsPressed: [Int: Data] = [:]
    // zuletzt gesendete Werte (werden nach dem Online-Gehen erneut gesendet)
    private var outD: [Int: Bool] = [:]
    private var outA: [Int: Int] = [:]
    private var outS: [Int: String] = [:]

    var ipidHex: String { TouchpanelConst.hex2(Int(ipid)) }

    func configure(host: String, port: Int, ipidHex: String) throws {
        guard let p = UInt16(exactly: port), p > 0 else { throw NetError.badAddress("\(host):\(port)") }
        var hx = ipidHex.trimmed
        if hx.lowercased().hasPrefix("0x") { hx = String(hx.dropFirst(2)) }   // wie int("0x03", 16)
        guard let v = Int(hx, radix: 16), v >= 0 else {
            throw NetError.protocolError("Ungültige IP-ID (hex): \(ipidHex)")
        }
        self.host = host.trimmed
        self.port = p
        self.ipid = UInt8(v & 0xFF)
    }

    func start() {
        if running { return }
        running = true
        restart = false
        gen += 1
        rxbuf = []
        let g = gen
        log("CIP start -> Ziel \(host):\(port)  IP-ID 0x\(ipidHex)")
        loopTask = Task { [weak self] in
            await self?.connectionLoop(g)
        }
    }

    func stop() {
        running = false
        connected = false
        loopTask?.cancel()
        loopTask = nil
        conn?.close()
        conn = nil
        setLink(false)
        // nichts Altes nach dem naechsten Verbinden senden (gehaltene Tasten, Queue)
        buttonsPressed.removeAll()
        txQueue.removeAll()
        log("CIP gestoppt")
    }

    // ---- Joins Panel -> Prozessor ----
    func setDigital(_ join: Int, _ value: Bool) { outDigital(join, value, button: false) }

    func setAnalog(_ join: Int, _ value: Int) {
        guard validJoin(join) else { return }
        let v = max(0, min(65535, value))
        outA[join] = v
        let cj = join - 1
        var tx = TouchpanelCIP.txAnalog
        tx.append(UInt8((cj >> 8) & 0xFF))
        tx.append(UInt8(cj & 0xFF))
        tx.append(UInt8((v >> 8) & 0xFF))
        tx.append(UInt8(v & 0xFF))
        sendOut("a", join, String(v), Data(tx))
    }

    func setSerial(_ join: Int, _ value: String) {
        guard validJoin(join) else { return }
        outS[join] = value
        // Umlaute als Latin-1, max. 240 Zeichen (Laengenbyte)
        let enc = value.data(using: .isoLatin1, allowLossyConversion: true) ?? Data(value.utf8)
        let data = [UInt8](enc.prefix(240))
        var tx = TouchpanelCIP.txSerial
        tx[2] = UInt8(8 + data.count)
        tx[6] = UInt8(4 + data.count)
        let cj = join - 1
        tx.append(UInt8((cj >> 8) & 0xFF))
        tx.append(UInt8(cj & 0xFF))
        tx.append(0x03)
        tx.append(contentsOf: data)
        sendOut("s", join, value, Data(tx))
    }

    func press(_ join: Int) {
        lastBtn = Date()
        outDigital(join, true, button: true)
    }

    func release(_ join: Int) { outDigital(join, false, button: true) }

    func pulse(_ join: Int) {
        outDigital(join, true, button: true)
        outDigital(join, false, button: true)
    }

    func updateRequest() {
        if connected {
            enqueue(TouchpanelCIP.updateReq)
            log("Update Request gesendet")
        } else {
            log("Update Request ignoriert - nicht online")
        }
    }

    private func validJoin(_ join: Int) -> Bool {
        if join < 1 || join > 65535 {
            log("Join \(join) ungültig (1...65535)")
            return false
        }
        return true
    }

    private func outDigital(_ join: Int, _ value: Bool, button: Bool) {
        guard validJoin(join) else { return }
        outD[join] = value
        let cj = join - 1
        var tx = button ? TouchpanelCIP.txDigitalButton : TouchpanelCIP.txDigital
        // packed = (cj // 256) + (cj % 256) * 256, Release setzt 0x80 -> [lo, hi|0x80]
        tx.append(UInt8(cj & 0xFF))
        var hi = UInt8((cj >> 8) & 0xFF)
        if !value { hi |= 0x80 }
        tx.append(hi)
        let frame = Data(tx)
        if button {
            // nur online halten - offline verworfene Tasten nicht spaeter wiederholen
            if value && connected && !restart {
                buttonsPressed[join] = frame
            } else {
                buttonsPressed.removeValue(forKey: join)
            }
        }
        sendOut("d", join, value ? "1" : "0", frame)
    }

    private func sendOut(_ base: String, _ join: Int, _ text: String, _ frame: Data) {
        if connected && !restart {
            log("OUT \(base)-Join \(join) = \(text)")
            enqueue(frame)
        } else {
            log("OUT \(base)-Join \(join) = \(text) VERWORFEN (Panel nicht online)")
        }
    }

    // ---- Senden (Reihenfolge bleibt erhalten) ----
    private func enqueue(_ d: Data) {
        txQueue.append(d)
        if txBusy { return }
        txBusy = true
        Task { [weak self] in
            await self?.drain()
        }
    }

    private func drain() async {
        while !txQueue.isEmpty {
            let d = txQueue.removeFirst()
            guard let c = conn, !restart else { continue }   // wie sc.py: ohne Socket verworfen
            do {
                try await c.send(d)
                lastTx = Date()
                log("TX <\(d.hex)>", raw: true)
            } catch {
                if running { log("TX-Fehler: \(DeviceModel.describe(error)) -> Reconnect") }
                if conn === c { restart = true }
            }
        }
        txBusy = false
    }

    // ---- Verbindungsschleife ----
    private func alive(_ g: Int) -> Bool {
        running && g == gen && !Task.isCancelled
    }

    private func connectionLoop(_ g: Int) async {
        var warned = false
        while alive(g) {
            guard let c = try? TCPConnection(host: host, port: port) else {
                if !warned {
                    log("Ungültige Adresse \(host):\(port)")
                    warned = true
                }
                setLink(false)
                await pause(1)
                continue
            }
            do {
                try await c.connect(timeout: 2)
            } catch {
                c.close()
                if !warned {
                    log("Verbinde zu \(host):\(port) - noch kein Erfolg (\(DeviceModel.describe(error)))")
                    warned = true
                }
                setLink(false)
                await pause(1)
                continue
            }
            if !alive(g) {
                c.close()
                break
            }
            warned = false
            rxbuf = []
            restart = false
            txQueue.removeAll()
            conn = c
            lastTx = Date()
            lastBtn = Date()
            log("TCP verbunden mit \(host):\(port) - warte auf CIP-Registrierung (Typ 0F)")
            let t0 = Date()
            var hinted = false
            while alive(g) && !restart {
                let d = await c.readAvailable(wait: 0.1, settle: 0.01)
                if !alive(g) { break }
                if !d.isEmpty {
                    log("RX <\(d.hex)>", raw: true)
                    feed(d)
                } else if c.isClosed {
                    log("Gegenstelle hat geschlossen -> Reconnect")
                    restart = true
                    break
                }
                if !connected && !hinted && Date().timeIntervalSince(t0) >= 4 {
                    hinted = true
                    log("WARNUNG: TCP steht, aber keine CIP-Registrierung. Falscher Port? CIP am Prozessor aus? Programm/IP-ID?")
                }
                if connected && !restart {
                    if Date().timeIntervalSince(lastTx) >= 15 {
                        lastTx = Date()
                        enqueue(TouchpanelCIP.heartbeat)
                    }
                    if Date().timeIntervalSince(lastBtn) >= 0.5 {
                        lastBtn = Date()
                        for j in buttonsPressed.keys.sorted() {
                            if let f = buttonsPressed[j] { enqueue(f) }
                        }
                    }
                }
            }
            if conn === c {
                conn = nil
                connected = false
                setLink(false)
            }
            c.close()
            // nur die eigene Generation: nach Stop/Start nichts der neuen Sitzung loeschen
            if g == gen {
                txQueue.removeAll()
                buttonsPressed.removeAll()
            }
            if alive(g) {
                log("Verbindung verloren - neuer Versuch in 1 s")
                await pause(1)
            }
        }
    }

    // ---- Empfang: Pakete ueber TCP-Segmentgrenzen zusammensetzen ----
    private func feed(_ d: Data) {
        rxbuf.append(contentsOf: d)
        var pos = 0
        let n = rxbuf.count
        while n - pos >= 3 {
            let plen = (Int(rxbuf[pos + 1]) << 8) + Int(rxbuf[pos + 2])
            let pktLen = plen + 3
            if n - pos < pktLen { break }
            let ptype = rxbuf[pos]
            let payload = Array(rxbuf[(pos + 3)..<(pos + 3 + plen)])
            process(ptype, payload)
            pos += pktLen
        }
        if pos > 0 { rxbuf.removeFirst(pos) }
        if rxbuf.count > 65536 { rxbuf = [] }
    }

    private func short(_ ptype: UInt8, _ p: [UInt8]) {
        log("RX-Paket Typ 0x\(TouchpanelConst.hex2(Int(ptype))) nicht auswertbar (zu kurz: \(p.count) Byte)", raw: true)
    }

    private func process(_ ptype: UInt8, _ p: [UInt8]) {
        switch ptype {
        case 0x0D, 0x0E:
            log("RX Heartbeat", raw: true)
        case 0x0F:
            log("RX Typ 0F Registrierungsaufforderung -> sende IP-ID-Registrierung")
            let tx: [UInt8] = [0x01, 0x00, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, ipid, 0x40, 0xFF, 0xFF, 0xF1, 0x01]
            enqueue(Data(tx))
        case 0x02:
            if p == [0x00, 0x00, 0x00, 0x1F] {
                log("RX Typ 02: IP-ID 0x\(ipidHex) REGISTRIERT -> Update Request")
                enqueue(TouchpanelCIP.updateReq)
            } else if p == [0xFF, 0xFF, 0x02] {
                log("RX Typ 02: FEHLER - IP-ID 0x\(ipidHex) existiert NICHT im Programm. Im SIMPL-Programm Panel/XPanel unter dieser IP-ID anlegen, F12, laden.")
            } else {
                log("RX Typ 02: unerwartete Antwort <\(Data(p).hex)>")
            }
        case 0x03:
            log("RX Typ 03: Steuersystem-Trennung -> Reconnect")
            restart = true
        case 0x12:
            guard p.count >= 7 else { short(ptype, p); return }
            let join = ((Int(p[5]) << 8) | Int(p[6])) + 1
            let bytes: [UInt8] = p.count > 8 ? Array(p[8...]) : []
            let value = String(bytes: bytes, encoding: .isoLatin1) ?? ""
            log("RX Serial-Join \(join) = '\(value)'")
            onSerial?(join, value)
        case 0x05:
            guard p.count >= 4 else { short(ptype, p); return }
            let datatype = p[3]
            switch datatype {
            case 0x00:
                guard p.count >= 6 else { short(ptype, p); return }
                let join = (((Int(p[5]) & 0x7F) << 8) | Int(p[4])) + 1
                let state = ((Int(p[5]) & 0x80) >> 7) ^ 0x01
                log("RX Digital-Join \(join) = \(state)")
                onDigital?(join, state == 1)
            case 0x14:
                guard p.count >= 8 else { short(ptype, p); return }
                let join = ((Int(p[4]) << 8) | Int(p[5])) + 1
                let value = (Int(p[6]) << 8) + Int(p[7])
                log("RX Analog-Join \(join) = \(value)")
                onAnalog?(join, value)
            case 0x03:
                guard p.count >= 5 else { short(ptype, p); return }
                let urt = p[4]
                if urt == 0x1C {
                    log("RX End-of-Query -> EOQ-Ack, Panel ONLINE")
                    enqueue(TouchpanelCIP.eoqAck)
                    enqueue(TouchpanelCIP.heartbeat)
                    connected = true
                    setLink(true)
                    for j in outD.keys.sorted() {
                        if let v = outD[j] { setDigital(j, v) }
                    }
                    for j in outA.keys.sorted() {
                        if let v = outA[j] { setAnalog(j, v) }
                    }
                    for j in outS.keys.sorted() {
                        if let v = outS[j] { setSerial(j, v) }
                    }
                } else {
                    log("RX Update-Request Typ 0x\(TouchpanelConst.hex2(Int(urt)))", raw: true)
                }
            case 0x08:
                log("RX Datum/Uhrzeit", raw: true)
            default:
                log("RX Typ 05 unbekannter Datentyp 0x\(TouchpanelConst.hex2(Int(datatype)))", raw: true)
            }
        default:
            log("RX unbekannter Typ 0x\(TouchpanelConst.hex2(Int(ptype))) <\(Data(p).hex)>", raw: true)
        }
    }

    private func setLink(_ state: Bool) {
        if state != link {
            link = state
            onLink?(state)
        }
    }

    private func log(_ text: String, raw: Bool = false) {
        onLog?("[CIP] " + text, raw)
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
struct TouchpanelFeedback: Identifiable {
    var id: String { "\(type)\(join)" }
    let type: String       // "D", "A", "S"
    let join: Int
    var value: String
}

@MainActor
final class TouchpanelModel: DeviceModel {
    @Published var settings = TouchpanelSettings()
    @Published var online = false
    @Published var running = false
    @Published var relayOn: [UUID: Bool] = [:]
    @Published var feedback: [String: TouchpanelFeedback] = [:]
    @Published var analogIn: [Int: Int] = [:]
    @Published var serialIn: [Int: String] = [:]

    /// Wird von der Ansicht gesetzt: Seite sichtbar -> CIP-Verbindung halten
    var pageVisible = false

    private let cip: TouchpanelCIP

    init() {
        cip = TouchpanelCIP()
        super.init(id: "touchpanel", title: "Touchpanel", subtitle: "Crestron TSW-770 (CIP)",
                   symbol: "rectangle.grid.2x2.fill", tint: Color(hex: 0x5E5CE6))
        cip.onLog = { [weak self] text, raw in
            self?.cipLog(text, raw)
        }
        cip.onLink = { [weak self] st in
            self?.linkChanged(st)
        }
        cip.onDigital = { [weak self] j, v in
            self?.digitalIn(j, v)
        }
        cip.onAnalog = { [weak self] j, v in
            self?.analogInput(j, v)
        }
        cip.onSerial = { [weak self] j, v in
            self?.serialInput(j, v)
        }
    }

    override var isConfigured: Bool { !settings.host.trimmed.isEmpty }
    override var pollInterval: Double { 5 }

    /// Schnellaktionen der Kachel: CIP wird bei Bedarf erst verbunden.
    override var quickActions: [QuickAction] {
        [
            // Bewusst KEINE Relais-Schnellaktionen: Relais (Lift, Leinwand ...) nur auf der Seite schalten
            QuickAction(id: "touchpanel.refresh", title: "Aktualisieren", symbol: "arrow.clockwise",
                        run: { [weak self] in
                            guard let me = self else { return }
                            Task { await me.refresh() }
                        }),
        ]
    }

    private func quickAllRelays(_ on: Bool) {
        // Vorschau/Demo: nur Lampen setzen, wie auf der Seite (keine Verbindung noetig)
        if settings.localPreview || DeviceModel.demoMode {
            allRelays(on)
            return
        }
        perform("Alle Relais \(on ? "EIN" : "AUS")") {
            if !self.cip.running { self.startCIP() }
            var n = 0
            while !self.online && self.cip.running && n < 60 {
                await pause(0.1)
                n += 1
            }
            if !self.online {
                if self.cip.running && !self.pageVisible { self.stopCIP() }
                throw NetError.protocolError("CIP nicht registriert (IP-ID \(self.settings.ipid))")
            }
            // Feedback-Joins des Update Request abwarten, dann nur abweichende Relais pulsen
            await pause(0.4)
            self.allRelays(on)
            // Pulse senden lassen; ohne offene Seite die CIP-Sitzung wieder schliessen
            await pause(0.8)
            if self.cip.running && !self.pageVisible { self.stopCIP() }
        }
    }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(TouchpanelSettings.self, "touchpanel") { settings = s }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "touchpanel")
        // neue Parameter -> CIP neu starten (refresh startet wieder, solange die Seite offen ist)
        if cip.running { stopCIP() }
    }

    // ---- CIP steuern ----
    func startCIP() {
        if cip.running { return }
        do {
            try cip.configure(host: settings.host, port: settings.port, ipidHex: settings.ipid)
        } catch {
            lastError = DeviceModel.describe(error)
            addLog("Ungültige CIP-Parameter: \(DeviceModel.describe(error))", error: true)
            return
        }
        cip.start()
        running = true
        summary = "Verbinde ... (IP-ID \(settings.ipid))"
    }

    func stopCIP() {
        cip.stop()
        running = false
        online = false
        summary = "Getrennt"
    }

    func toggleCIP() {
        if cip.running {
            stopCIP()
        } else {
            startCIP()
        }
    }

    override func disconnect() {
        if cip.running { stopCIP() }
    }

    // ---- Relais / Tasten ----
    func isOn(_ r: TouchpanelRelay) -> Bool { relayOn[r.id] == true }

    /// Toggle: Press-Join pulsen (Prozessor toggelt das Relais)
    func relayClick(_ r: TouchpanelRelay) {
        addLog("\(r.label) angetippt -> Pulse Join \(r.join)")
        cip.pulse(r.join)
        if settings.localPreview {
            relayOn[r.id] = !isOn(r)
        }
    }

    func buttonPress(_ r: TouchpanelRelay) {
        cip.press(r.join)
    }

    func buttonRelease(_ r: TouchpanelRelay) {
        cip.release(r.join)
    }

    /// Alle EIN/AUS: in der Vorschau Lampen setzen, sonst nur abweichende Relais pulsen.
    func allRelays(_ on: Bool) {
        let toggles = settings.relays.filter { !$0.momentary }
        if settings.localPreview {
            for r in toggles { relayOn[r.id] = on }
        } else {
            var n = 0
            for r in toggles where isOn(r) != on {
                cip.pulse(r.join)
                n += 1
            }
            addLog("Alle \(on ? "EIN" : "AUS"): \(n) Relais geschaltet")
        }
    }

    // ---- Szenen (Relais-Kombinationen) ----
    var sceneNames: [String] { settings.scenes.keys.sorted() }

    func saveScene(_ rawName: String) {
        let name = rawName.trimmed
        guard !name.isEmpty else {
            addLog("Bitte einen Szenen-Namen eingeben.", error: true)
            return
        }
        let st = settings.relays.map { isOn($0) }
        settings.scenes[name] = st
        SecureStore.saveCodable(settings, "touchpanel")
        addLog("Szene '\(name)' gespeichert: " + st.map { $0 ? "1" : "0" }.joined(separator: " "))
        Haptics.success()
    }

    func recallScene(_ name: String) {
        guard let want = settings.scenes[name] else {
            addLog("Szene '\(name)' nicht gefunden.", error: true)
            return
        }
        var changed = 0
        for (i, r) in settings.relays.enumerated() {
            if i >= want.count { break }
            if isOn(r) != want[i] {
                changed += 1
                if settings.localPreview {
                    relayOn[r.id] = want[i]
                } else {
                    cip.pulse(r.join)
                }
            }
        }
        addLog("Szene '\(name)' abgerufen - \(changed) Relais umgeschaltet.")
        Haptics.success()
    }

    func deleteScene(_ name: String) {
        guard settings.scenes[name] != nil else { return }
        settings.scenes.removeValue(forKey: name)
        SecureStore.saveCodable(settings, "touchpanel")
        addLog("Szene '\(name)' geloescht.")
    }

    // ---- Test-Joins ----
    func testDigital(_ op: String, _ join: Int) {
        switch op {
        case "H": cip.press(join)
        case "R": cip.release(join)
        case "P": cip.pulse(join)
        case "D1": cip.setDigital(join, true)
        case "D0": cip.setDigital(join, false)
        default: break
        }
    }

    func testAnalog(_ join: Int, _ value: Int) { cip.setAnalog(join, value) }
    func testSerial(_ join: Int, _ text: String) { cip.setSerial(join, text) }
    func updateRequest() { cip.updateRequest() }
    func clearFeedback() { feedback.removeAll() }

    var feedbackList: [TouchpanelFeedback] {
        feedback.values.sorted { a, b in
            if a.type != b.type { return a.type < b.type }
            return a.join < b.join
        }
    }

    // ---- Rueckmeldungen ----
    private func cipLog(_ text: String, _ raw: Bool) {
        if raw && !settings.debug { return }
        let err = text.contains("FEHLER") || text.contains("WARNUNG") || text.contains("Fehler")
        addLog(text, error: err)
    }

    private func linkChanged(_ st: Bool) {
        online = st
        if st {
            state = .online
            lastError = nil
            lastUpdate = Date()
            summary = "Online - IP-ID \(settings.ipid)"
            addLog("CIP: online (registriert)")
        } else {
            // wie _update_cip_led(False): alle Lampen aus
            relayOn.removeAll()
            if cip.running {
                summary = "Offline - verbinde neu ..."
            }
        }
    }

    private func digitalIn(_ j: Int, _ v: Bool) {
        feedback["D\(j)"] = TouchpanelFeedback(type: "D", join: j, value: v ? "1" : "0")
        for r in settings.relays where r.join == j {
            relayOn[r.id] = v
        }
        lastUpdate = Date()
    }

    private func analogInput(_ j: Int, _ v: Int) {
        feedback["A\(j)"] = TouchpanelFeedback(type: "A", join: j, value: String(v))
        analogIn[j] = v
        lastUpdate = Date()
    }

    private func serialInput(_ j: Int, _ v: String) {
        feedback["S\(j)"] = TouchpanelFeedback(type: "S", join: j, value: v)
        serialIn[j] = v
        lastUpdate = Date()
    }

    // ---- Status ----
    override func refresh() async {
        if DeviceModel.demoMode { await refreshSafely {}; return }
        if pageVisible {
            if !cip.running { startCIP() }
            var n = 0
            while !online && cip.running && n < 40 {
                await pause(0.1)
                n += 1
            }
            await refreshSafely {
                if !self.cip.running {
                    throw NetError.protocolError(self.lastError ?? "CIP gestoppt")
                }
                if !self.online {
                    throw NetError.protocolError("CIP nicht registriert (IP-ID \(self.settings.ipid))")
                }
                self.summary = "Online - IP-ID \(self.settings.ipid)"
            }
        } else {
            await refreshSafely {
                guard let p = UInt16(exactly: self.settings.port) else {
                    throw NetError.badAddress("\(self.settings.host):\(self.settings.port)")
                }
                if self.online {
                    self.summary = "Online - IP-ID \(self.settings.ipid)"
                    return
                }
                let ok = await TCPConnection.probe(host: self.settings.host.trimmed, port: p)
                if !ok { throw NetError.protocolError("CIP-Port nicht erreichbar") }
                self.summary = "Prozessor erreichbar"
            }
        }
    }

    // ---- Demo (Start mit -demo, ohne Netzwerk) ----
    override func loadDemo() {
        settings.host = "192.168.1.110"
        settings.port = 41794
        settings.ipid = "03"
        settings.localPreview = true
        settings.relays = [
            TouchpanelRelay(label: "Licht Decke", join: 1),
            TouchpanelRelay(label: "Licht Tisch", join: 2),
            TouchpanelRelay(label: "Beamer-Lift", join: 3),
            TouchpanelRelay(label: "Leinwand", join: 4),
            TouchpanelRelay(label: "Verstaerker", join: 5),
            TouchpanelRelay(label: "Monitore", join: 6),
            TouchpanelRelay(label: "Rotlicht", join: 7),
            TouchpanelRelay(label: "Gong", join: 8, momentary: true),
        ]
        settings.scenes = [
            "Aufnahme": [true, true, false, false, true, true, true, false],
            "Praesentation": [false, true, true, true, true, false, false, false],
        ]
        let onStates = [true, true, false, false, true, true, false, false]
        var ro: [UUID: Bool] = [:]
        for (i, r) in settings.relays.enumerated() where i < onStates.count {
            ro[r.id] = onStates[i]
        }
        relayOn = ro
        running = true
        online = true
        var fb: [String: TouchpanelFeedback] = [:]
        for (i, r) in settings.relays.enumerated() where i < onStates.count {
            fb["D\(r.join)"] = TouchpanelFeedback(type: "D", join: r.join, value: onStates[i] ? "1" : "0")
        }
        fb["A1"] = TouchpanelFeedback(type: "A", join: 1, value: "32768")
        fb["S1"] = TouchpanelFeedback(type: "S", join: 1, value: "Studio bereit")
        feedback = fb
        analogIn = [1: 32768]
        serialIn = [1: "Studio bereit"]
        summary = "Online - IP-ID 03"
    }
}

// ---------------------------------------------------------------------------
// Ansicht
// ---------------------------------------------------------------------------
struct TouchpanelView: View {
    @ObservedObject var model: TouchpanelModel
    @State private var sceneName = ""
    @State private var dJoin = 1
    @State private var aJoin = 1
    @State private var aValue: Double = 32768
    @State private var sJoin = 1
    @State private var sText = "Hallo Crestron"

    var body: some View {
        DevicePage(model: model, settings: { TouchpanelSettingsView(model: model) }) {
            Group {
                connectionSection
                relaySection
                sceneSection
            }
            Group {
                digitalSection
                analogSection
                serialSection
                feedbackSection
            }
        }
        .onAppear {
            model.pageVisible = true
            if !model.running {
                Task { await model.refresh() }
            }
        }
        .onDisappear {
            model.pageVisible = false
            model.disconnect()
        }
    }

    private var connectionSection: some View {
        Section {
            ValueRow(label: "Prozessor", value: "\(model.settings.host):\(model.settings.port)", symbol: "cpu")
            ValueRow(label: "IP-ID", value: "0x\(model.settings.ipid)", symbol: "number")
            HStack {
                Label(model.online ? "ONLINE (registriert)" : (model.running ? "OFFLINE - verbinde ..." : "Getrennt"),
                      systemImage: model.online ? "checkmark.circle.fill" : "xmark.circle")
                    .foregroundStyle(model.online ? Color.green : Color.secondary)
                Spacer()
                Button(model.running ? "Trennen" : "Verbinden") {
                    model.toggleCIP()
                }
                .buttonStyle(.borderless)
            }
            Button {
                model.updateRequest()
            } label: {
                Label("Update Request (Resync)", systemImage: "arrow.triangle.2.circlepath")
            }
        } header: {
            Text("CIP-Verbindung")
        }
    }

    private var relaySection: some View {
        Section {
            TileGrid(columns: 2) {
                ForEach(model.settings.relays) { r in
                    if r.momentary {
                        TouchpanelHoldTile(title: tileTitle(r), on: model.isOn(r),
                                           press: { model.buttonPress(r) },
                                           release: { model.buttonRelease(r) })
                    } else {
                        ActionTile(title: tileTitle(r), symbol: model.isOn(r) ? "power.circle.fill" : "power.circle",
                                   tint: Color(hex: 0x5E5CE6), active: model.isOn(r)) {
                            model.relayClick(r)
                        }
                    }
                }
            }
            HStack {
                Button("Alle EIN") { model.allRelays(true) }
                    .buttonStyle(.borderless)
                Spacer()
                Button("Alle AUS") { model.allRelays(false) }
                    .buttonStyle(.borderless)
            }
            Toggle(isOn: Binding(get: { model.settings.localPreview }, set: { v in
                model.settings.localPreview = v
                SecureStore.saveCodable(model.settings, "touchpanel")
            })) {
                Label("Lokale Vorschau (ohne CP3)", systemImage: "eye")
            }
        } header: {
            Text("Relais-Panel")
        } footer: {
            Text("Toggle sendet einen Digital-Puls auf den Join (Panel -> CP3), die Lampe folgt dem Feedback-Join (CP3 -> Panel). Taster senden Press/Release.")
        }
    }

    private var sceneSection: some View {
        Section {
            ForEach(model.sceneNames, id: \.self) { name in
                HStack {
                    Label(name, systemImage: "square.stack.3d.up")
                    Spacer()
                    Button("Abrufen") { model.recallScene(name) }
                        .buttonStyle(.borderless)
                }
                .swipeActions {
                    Button(role: .destructive) {
                        model.deleteScene(name)
                    } label: {
                        Label("Löschen", systemImage: "trash")
                    }
                }
            }
            HStack {
                TextField("Neuer Szenen-Name", text: $sceneName)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Speichern") {
                    model.saveScene(sceneName)
                    sceneName = ""
                }
                .buttonStyle(.borderless)
                .disabled(sceneName.trimmed.isEmpty)
            }
        } header: {
            Text("Szenen")
        } footer: {
            Text("Speichert den aktuellen Relais-Zustand. Beim Abrufen werden nur abweichende Relais gepulst.")
        }
    }

    private var digitalSection: some View {
        Section("Digital-Join senden") {
            Stepper(value: $dJoin, in: 1...65535) {
                ValueRow(label: "Join", value: "\(dJoin)")
            }
            HStack(spacing: 10) {
                TouchpanelHoldTile(title: "Halten", on: false,
                                   press: { model.testDigital("H", dJoin) },
                                   release: { model.testDigital("R", dJoin) })
                ActionTile(title: "Puls", symbol: "hand.tap") { model.testDigital("P", dJoin) }
            }
            HStack(spacing: 10) {
                ActionTile(title: "Press", symbol: "arrow.down.circle") { model.testDigital("H", dJoin) }
                ActionTile(title: "Release", symbol: "arrow.up.circle") { model.testDigital("R", dJoin) }
            }
            HStack(spacing: 10) {
                ActionTile(title: "High", symbol: "1.circle") { model.testDigital("D1", dJoin) }
                ActionTile(title: "Low", symbol: "0.circle") { model.testDigital("D0", dJoin) }
            }
        }
    }

    private var analogSection: some View {
        Section("Analog-Join senden") {
            Stepper(value: $aJoin, in: 1...65535) {
                ValueRow(label: "Join", value: "\(aJoin)")
            }
            VStack(alignment: .leading) {
                HStack {
                    Text("Wert")
                    Spacer()
                    Text("\(Int(aValue))").font(.body.monospacedDigit()).foregroundStyle(.secondary)
                }
                Slider(value: $aValue, in: 0...65535, step: 1, onEditingChanged: { editing in
                    if !editing { model.testAnalog(aJoin, Int(aValue)) }
                })
            }
            if let fb = model.analogIn[aJoin] {
                ValueRow(label: "Feedback A\(aJoin)", value: "\(fb)")
            }
            Button {
                model.testAnalog(aJoin, Int(aValue))
            } label: {
                Label("Analog setzen", systemImage: "slider.horizontal.below.rectangle")
            }
        }
    }

    private var serialSection: some View {
        Section("Serial-Join senden") {
            Stepper(value: $sJoin, in: 1...65535) {
                ValueRow(label: "Join", value: "\(sJoin)")
            }
            TextField("Text", text: $sText)
                .autocorrectionDisabled()
            if let fb = model.serialIn[sJoin] {
                ValueRow(label: "Feedback S\(sJoin)", value: fb)
            }
            Button {
                model.testSerial(sJoin, sText)
            } label: {
                Label("Serial setzen", systemImage: "text.cursor")
            }
        }
    }

    private var feedbackSection: some View {
        Section {
            if model.feedback.isEmpty {
                Text("Noch keine Rückmeldungen").font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(model.feedbackList) { f in
                HStack {
                    Text("\(f.type)\(f.join)").font(.body.monospaced())
                    Spacer()
                    Text(f.value).foregroundStyle(f.type == "D" && f.value == "1" ? Color.green : Color.secondary)
                        .textSelection(.enabled)
                }
            }
            if !model.feedback.isEmpty {
                Button("Monitor leeren") { model.clearFeedback() }
            }
        } header: {
            Text("Feedback vom Prozessor")
        }
    }

    private func tileTitle(_ r: TouchpanelRelay) -> String {
        "\(r.label)\nD\(r.join) · \(model.isOn(r) ? "EIN" : "AUS")"
    }
}

/// Taster: Press beim Beruehren, Release beim Loslassen.
struct TouchpanelHoldTile: View {
    let title: String
    let on: Bool
    let press: () -> Void
    let release: () -> Void
    @State private var held = false

    var body: some View {
        let lit = held || on
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: "hand.point.up.left.fill")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(lit ? Color.white : Color(hex: 0x5E5CE6))
            Text(title)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(lit ? Color.white : Color.primary)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, minHeight: 74, alignment: .leading)
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(lit ? AnyShapeStyle(Color(hex: 0x5E5CE6).gradient) : AnyShapeStyle(Color(.tertiarySystemFill)))
        )
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    if !held {
                        held = true
                        Haptics.tap()
                        press()
                    }
                }
                .onEnded { _ in
                    if held {
                        held = false
                        release()
                    }
                }
        )
        .onDisappear {
            // abgebrochene Geste: Taste nicht haengen lassen
            if held {
                held = false
                release()
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct TouchpanelSettingsView: View {
    @ObservedObject var model: TouchpanelModel
    @State private var s: TouchpanelSettings

    init(model: TouchpanelModel) {
        self.model = model
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "Touchpanel", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "Prozessor-IP", text: $s.host, placeholder: TouchpanelConst.defHost, keyboard: .numbersAndPunctuation)
                FieldRow(label: "CIP-Port", text: intBinding($s.port), placeholder: String(TouchpanelConst.defPort), keyboard: .numberPad)
                FieldRow(label: "IP-ID (hex)", text: $s.ipid, placeholder: TouchpanelConst.defIPID)
            } header: {
                Text("CIP - Anbindung an CP3")
            } footer: {
                Text("Im Crestron-Programm TSW-770/XPanel unter dieser IP-ID anlegen, F12, laden.")
            }
            Section("Optionen") {
                Toggle("Lokale Vorschau (ohne CP3)", isOn: $s.localPreview)
                Toggle("Debug-Detail (Hex/Heartbeat)", isOn: $s.debug)
            }
            Section {
                ForEach($s.relays) { $r in
                    VStack(alignment: .leading, spacing: 6) {
                        TextField("Bezeichnung", text: $r.label)
                        HStack {
                            Text("Join").foregroundStyle(.secondary)
                            TextField("1", text: intBinding($r.join))
                                .keyboardType(.numberPad)
                                .frame(width: 70)
                            Spacer()
                            Toggle("Taster", isOn: $r.momentary)
                                .fixedSize()
                        }
                    }
                }
                .onDelete { idx in
                    s.relays.remove(atOffsets: idx)
                }
                Button {
                    let next = (s.relays.map { $0.join }.max() ?? 0) + 1
                    s.relays.append(TouchpanelRelay(label: "Relais \(next)", join: next))
                } label: {
                    Label("Taste hinzufügen", systemImage: "plus.circle")
                }
                Button("Standard (8 Relais, Join 1-8)") {
                    s.relays = TouchpanelSettings.defaultRelays()
                }
            } header: {
                Text("Relais / Tasten")
            } footer: {
                Text("Toggle: Puls auf den Join, Lampe folgt dem Feedback-Join. Taster: Press beim Drücken, Release beim Loslassen.")
            }
        }
    }
}
