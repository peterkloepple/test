// ===========================================================================
//  TerminalPingModel.swift - PA AV Toolbox iOS v1.0.0
//  Autor: T. Pfeiffer
//  Terminal: TCP / UDP mit Telnet-Aushandlung (IAC -> WONT/DONT), Vorlagen.
//  Ping: ICMP-Dauerping mit Statistik.
// ===========================================================================
import Foundation
import Darwin

let TERMINATORS: [(String, [UInt8])] = [
    ("CR", [13]), ("LF", [10]), ("CRLF", [13, 10]), ("NUL", [0]), ("keiner", []),
]

struct Preset: Identifiable {
    let id = UUID()
    let group: String
    let desc: String
    let cmd: String      // in Escape-Schreibweise (\r, \x1b) bzw. Hex
    let port: String
    let proto: String
    let term: String
    let hex: Bool
}

let PRESETS: [Preset] = [
    Preset(group: "Extron SIS", desc: "Firmware abfragen", cmd: "Q", port: "23", proto: "TCP", term: "keiner", hex: false),
    Preset(group: "Extron SIS", desc: "Info / Modell", cmd: "I", port: "23", proto: "TCP", term: "keiner", hex: false),
    Preset(group: "Extron SIS", desc: "Teilenummer", cmd: "N", port: "23", proto: "TCP", term: "keiner", hex: false),
    Preset(group: "Extron SIS", desc: "Geraetename", cmd: "\\x1bCN\\r", port: "23", proto: "TCP", term: "keiner", hex: false),
    Preset(group: "Extron SIS", desc: "Verbose Mode 3", cmd: "\\x1b3CV\\r", port: "23", proto: "TCP", term: "keiner", hex: false),
    Preset(group: "Extron SIS", desc: "IP-Adresse", cmd: "\\x1bCI\\r", port: "23", proto: "TCP", term: "keiner", hex: false),
    Preset(group: "Q-SYS QRC", desc: "NoOp (Verbindungstest)", cmd: "{\"jsonrpc\":\"2.0\",\"method\":\"NoOp\",\"params\":{}}", port: "1710", proto: "TCP", term: "NUL", hex: false),
    Preset(group: "Q-SYS QRC", desc: "StatusGet", cmd: "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"StatusGet\",\"params\":0}", port: "1710", proto: "TCP", term: "NUL", hex: false),
    Preset(group: "Q-SYS QRC", desc: "Component.GetComponents", cmd: "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"Component.GetComponents\",\"params\":{}}", port: "1710", proto: "TCP", term: "NUL", hex: false),
    Preset(group: "Q-SYS QRC", desc: "Control.Get (Named Control)", cmd: "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"Control.Get\",\"params\":[\"MeinControl\"]}", port: "1710", proto: "TCP", term: "NUL", hex: false),
    Preset(group: "Q-SYS QRC", desc: "Logon", cmd: "{\"jsonrpc\":\"2.0\",\"method\":\"Logon\",\"params\":{\"User\":\"user\",\"Password\":\"pin\"}}", port: "1710", proto: "TCP", term: "NUL", hex: false),
    Preset(group: "Crestron Konsole", desc: "Version", cmd: "ver", port: "23", proto: "TCP", term: "CR", hex: false),
    Preset(group: "Crestron Konsole", desc: "Info", cmd: "info", port: "23", proto: "TCP", term: "CR", hex: false),
    Preset(group: "Crestron Konsole", desc: "IP-Konfiguration", cmd: "ipconfig", port: "23", proto: "TCP", term: "CR", hex: false),
    Preset(group: "Crestron Konsole", desc: "Programm-Status", cmd: "progcomments", port: "23", proto: "TCP", term: "CR", hex: false),
    Preset(group: "Crestron Konsole", desc: "IP-Tabelle", cmd: "iptable", port: "23", proto: "TCP", term: "CR", hex: false),
    Preset(group: "Crestron Konsole", desc: "Fehlerlog", cmd: "err", port: "23", proto: "TCP", term: "CR", hex: false),
    Preset(group: "PJLink", desc: "Power abfragen", cmd: "%1POWR ?", port: "4352", proto: "TCP", term: "CR", hex: false),
    Preset(group: "PJLink", desc: "Power EIN", cmd: "%1POWR 1", port: "4352", proto: "TCP", term: "CR", hex: false),
    Preset(group: "PJLink", desc: "Power AUS", cmd: "%1POWR 0", port: "4352", proto: "TCP", term: "CR", hex: false),
    Preset(group: "PJLink", desc: "Eingang abfragen", cmd: "%1INPT ?", port: "4352", proto: "TCP", term: "CR", hex: false),
    Preset(group: "PJLink", desc: "Name abfragen", cmd: "%1NAME ?", port: "4352", proto: "TCP", term: "CR", hex: false),
    Preset(group: "VISCA over IP", desc: "Power EIN (Sony)", cmd: "01 00 00 06 00 00 00 01 81 01 04 00 02 FF", port: "52381", proto: "UDP", term: "keiner", hex: true),
    Preset(group: "VISCA over IP", desc: "Power AUS (Sony)", cmd: "01 00 00 06 00 00 00 01 81 01 04 00 03 FF", port: "52381", proto: "UDP", term: "keiner", hex: true),
    Preset(group: "VISCA over IP", desc: "Preset 1 abrufen", cmd: "01 00 00 07 00 00 00 01 81 01 04 3F 02 00 FF", port: "52381", proto: "UDP", term: "keiner", hex: true),
    Preset(group: "VISCA (TCP roh)", desc: "Power EIN", cmd: "81 01 04 00 02 FF", port: "5678", proto: "TCP", term: "keiner", hex: true),
]

enum LineKind { case tx, rx, info }

struct TermLine: Identifiable {
    let id = UUID()
    let kind: LineKind
    let text: String
}

// ===========================================================================
//  Terminal
// ===========================================================================
final class TermModel: ObservableObject {
    @Published var ip: String { didSet { UserDefaults.standard.set(ip, forKey: "term_ip") } }
    @Published var port: String { didSet { UserDefaults.standard.set(port, forKey: "term_port") } }
    @Published var proto: String { didSet { UserDefaults.standard.set(proto, forKey: "term_proto") } }
    @Published var term: String { didSet { UserDefaults.standard.set(term, forKey: "term_term") } }
    @Published var hexSend: Bool { didSet { UserDefaults.standard.set(hexSend, forKey: "term_hex") } }
    @Published var hexShow = false
    @Published var input = ""
    @Published var lines: [TermLine] = []
    @Published var connected = false
    @Published var state = "Getrennt"

    private let lock = NSLock()
    private var fd: Int32 = -1
    private var alive = false
    private var udpAddr = sockaddr_in()
    private let ioQ = DispatchQueue(label: "pa.terminal.io")

    init() {
        let d = UserDefaults.standard
        ip = d.string(forKey: "term_ip") ?? "192.168.1.10"
        port = d.string(forKey: "term_port") ?? "23"
        proto = d.string(forKey: "term_proto") ?? "TCP"
        term = d.string(forKey: "term_term") ?? "CR"
        hexSend = d.bool(forKey: "term_hex")
    }

    private func ui(_ b: @escaping () -> Void) { DispatchQueue.main.async(execute: b) }

    private func add(_ k: LineKind, _ t: String) {
        ui {
            self.lines.append(TermLine(kind: k, text: t))
            if self.lines.count > 1500 { self.lines.removeFirst(300) }
        }
    }

    private func setState(_ up: Bool, _ msg: String) {
        ui { self.connected = up; self.state = msg }
        add(.info, "--- \(msg) ---")
    }

    private var isAlive: Bool {
        lock.lock(); defer { lock.unlock() }
        return alive
    }

    func toggle() {
        if connected { disconnect() } else { connect() }
    }

    func connect() {
        let host = ip.trimmingCharacters(in: .whitespaces)
        guard let p = Int(port.trimmingCharacters(in: .whitespaces)), p > 0, p < 65536 else {
            add(.info, "--- Port pruefen ---"); return
        }
        let pr = proto
        state = "Verbinde ..."
        ioQ.async {
            guard let addrIP = Net.resolveIPv4(host) else {
                self.setState(false, "Adresse nicht aufloesbar: \(host)"); return
            }
            if pr == "UDP" {
                let s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
                guard s >= 0, let a = Net.makeAddr(addrIP, UInt16(p)) else {
                    self.setState(false, "Verbindung fehlgeschlagen"); return
                }
                self.lock.lock(); self.fd = s; self.udpAddr = a; self.alive = true; self.lock.unlock()
            } else {
                let (s, r) = Net.connectFD(addrIP, p, timeout: 4.0)
                if s < 0 {
                    self.setState(false, r == .refused ? "Verbindung abgelehnt (Port zu)" : "Verbindung fehlgeschlagen (Zeitueberschreitung)")
                    return
                }
                self.lock.lock(); self.fd = s; self.alive = true; self.lock.unlock()
            }
            self.setState(true, "\(pr) \(host):\(p) verbunden")
            let t = Thread { self.rxLoop(udp: pr == "UDP") }
            t.start()
        }
    }

    func disconnect() {
        lock.lock()
        let was = alive
        alive = false
        let s = fd
        fd = -1
        lock.unlock()
        if s >= 0 { Darwin.close(s) }
        if was { setState(false, "Getrennt") }
    }

    private func telnetFilter(_ data: [UInt8], fd: Int32) -> [UInt8] {
        var out: [UInt8] = []
        var i = 0
        while i < data.count {
            let b = data[i]
            if b == 255 && i + 1 < data.count {
                let cmd = data[i + 1]
                if (cmd == 251 || cmd == 252 || cmd == 253 || cmd == 254) && i + 2 < data.count {
                    let opt = data[i + 2]
                    let reply: UInt8 = (cmd == 251 || cmd == 252) ? 254 : 252
                    _ = Net.writeAll(fd, Data([255, reply, opt]))
                    i += 3
                    continue
                }
                if cmd == 255 { out.append(255); i += 2; continue }
                i += 2
                continue
            }
            out.append(b)
            i += 1
        }
        return out
    }

    private func rxLoop(udp: Bool) {
        var buf = [UInt8](repeating: 0, count: 8192)
        while isAlive {
            lock.lock(); let s = fd; lock.unlock()
            if s < 0 { break }
            var p = pollfd(fd: s, events: Int16(POLLIN), revents: 0)
            let pr = poll(&p, 1, 500)
            if pr == 0 { continue }
            if pr < 0 { break }
            let n = Darwin.recv(s, &buf, buf.count, 0)
            if n <= 0 {
                if !udp && isAlive {
                    lock.lock(); alive = false; fd = -1; lock.unlock()
                    Darwin.close(s)
                    setState(false, n == 0 ? "Gegenstelle hat getrennt" : "Verbindung verloren")
                }
                if udp { continue }
                break
            }
            var bytes = Array(buf[0..<n])
            if !udp { bytes = telnetFilter(bytes, fd: s) }
            if bytes.isEmpty { continue }
            let d = Data(bytes)
            let showHex = DispatchQueue.main.sync { self.hexShow }
            add(.rx, showHex ? Txt.hex(d) : Txt.printable(d))
        }
    }

    func send() {
        let text = input
        guard connected else { add(.info, "--- nicht verbunden ---"); return }
        var payload: Data
        if hexSend {
            guard let h = Txt.parseHex(text) else {
                add(.info, "--- Ungueltige Hex-Eingabe (Beispiel: 81 01 04 00 02 FF) ---"); return
            }
            payload = h
        } else {
            payload = Txt.unescape(text)
        }
        let termBytes = TERMINATORS.first(where: { $0.0 == term })?.1 ?? []
        payload.append(contentsOf: termBytes)
        let shown = hexSend ? Txt.hex(payload) : Txt.printable(payload)
        let udp = proto == "UDP"
        ioQ.async {
            self.lock.lock(); let s = self.fd; var a = self.udpAddr; self.lock.unlock()
            if s < 0 { return }
            var ok = false
            if udp {
                let n = payload.withUnsafeBytes { raw -> Int in
                    withUnsafePointer(to: &a) { ptr -> Int in
                        ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sp in
                            sendto(s, raw.baseAddress, raw.count, 0, sp, socklen_t(MemoryLayout<sockaddr_in>.size))
                        }
                    }
                }
                ok = n >= 0
            } else {
                ok = Net.writeAll(s, payload)
            }
            if ok { self.add(.tx, "> " + shown) } else { self.add(.info, "--- Senden fehlgeschlagen ---") }
        }
    }

    func use(_ p: Preset) {
        input = p.cmd
        hexSend = p.hex
        term = p.term
        if !connected { port = p.port; proto = p.proto }
    }

    func clear() { lines = [] }
}

// ===========================================================================
//  Ping
// ===========================================================================
final class PingModel: ObservableObject {
    @Published var target: String { didSet { UserDefaults.standard.set(target, forKey: "ping_ip") } }
    @Published var lines: [TermLine] = []
    @Published var running = false
    @Published var sent = 0
    @Published var recv = 0
    @Published var minMs: Double = 0
    @Published var avgMs: Double = 0
    @Published var maxMs: Double = 0

    private let stop = StopFlag()

    init() {
        target = UserDefaults.standard.string(forKey: "ping_ip") ?? "192.168.1.1"
    }

    var lossText: String {
        sent == 0 ? "0" : String(format: "%.0f", 100.0 * Double(sent - recv) / Double(sent))
    }

    var rttText: String {
        recv == 0 ? "- / - / -" : String(format: "%.1f / %.1f / %.1f", minMs, avgMs, maxMs)
    }

    func start() {
        if running { return }
        let t = target.trimmingCharacters(in: .whitespaces)
        if t.isEmpty { return }
        lines = []; sent = 0; recv = 0; minMs = 0; avgMs = 0; maxMs = 0
        stop.reset()
        running = true
        let th = Thread { self.loop(t) }
        th.start()
    }

    func stopPing() { stop.set() }

    private func loop(_ host: String) {
        guard let ip = Net.resolveIPv4(host) else {
            DispatchQueue.main.async {
                self.lines.append(TermLine(kind: .info, text: "Adresse nicht aufloesbar: \(host)"))
                self.running = false
            }
            return
        }
        guard let pinger = Pinger(ip: ip) else {
            DispatchQueue.main.async {
                self.lines.append(TermLine(kind: .info, text: "ICMP-Socket nicht verfuegbar"))
                self.running = false
            }
            return
        }
        var times: [Double] = []
        var s = 0, r = 0
        while !stop.isSet {
            let t0 = Date()
            s += 1
            let rtt = pinger.ping(timeout: 1.0)
            var line: TermLine
            if let ms = rtt {
                r += 1
                times.append(ms)
                line = TermLine(kind: .rx, text: "\(Txt.now())  Antwort von \(ip)  " + String(format: "%.1f ms", ms))
            } else {
                line = TermLine(kind: .info, text: "\(Txt.now())  Zeitueberschreitung \(ip)")
            }
            let sc = s, rc = r
            let mn = times.min() ?? 0, mx = times.max() ?? 0
            let av = times.isEmpty ? 0 : times.reduce(0, +) / Double(times.count)
            DispatchQueue.main.async {
                self.lines.append(line)
                if self.lines.count > 1000 { self.lines.removeFirst(200) }
                self.sent = sc; self.recv = rc
                self.minMs = mn; self.maxMs = mx; self.avgMs = av
            }
            let wait = 1.0 - Date().timeIntervalSince(t0)
            if wait > 0 { Thread.sleep(forTimeInterval: wait) }
        }
        DispatchQueue.main.async { self.running = false }
    }
}
