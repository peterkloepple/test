// ===========================================================================
//  DiscoveryModel.swift - PA AV Toolbox iOS v1.0.0
//  Autor: T. Pfeiffer
//  AV-Discovery (aus Toolbox 1.3.0): Phase 1 Kennports, Phase 2 Modell-/
//  Markenabfrage (QRC, PJLink, Shure, HTTP, Banner). Ohne MAC (iOS).
// ===========================================================================
import Foundation

let PORT_VENDOR: [Int: String] = [
    1710: "Q-SYS", 41794: "Crestron", 22023: "Extron",
    2202: "Shure", 4352: "Display", 7142: "NEC", 1515: "Samsung", 9761: "LG",
]
let DISC_CLASSES: [(String, [Int])] = [
    ("Q-SYS", [1710]),
    ("Crestron", [41794, 22, 23]),
    ("Extron", [22023, 23, 80]),
    ("Mikrofone", [2202, 80]),
    ("Displays", [4352, 7142, 1515, 9761, 80]),
]
let BRANDS: [(String, String)] = [
    ("sennheiser", "Sennheiser"), ("audio-technica", "Audio-Technica"),
    ("televic", "Televic"), ("plixus", "Televic"), ("confidea", "Televic"),
    ("beyerdynamic", "beyerdynamic"), ("shure", "Shure"),
    ("biamp", "Biamp"), ("tesira", "Biamp"), ("clearone", "ClearOne"),
    ("dicentis", "Bosch"),
    ("samsung", "Samsung"), ("panasonic", "Panasonic"), ("sony", "Sony"),
    ("barco", "Barco"), ("christie", "Christie"), ("epson", "Epson"),
    ("viewsonic", "ViewSonic"), ("optoma", "Optoma"),
    ("crestron", "Crestron"), ("extron", "Extron"),
    ("q-sys", "Q-SYS"), ("qsc", "QSC"),
]
let DISC_CONNECT_TIMEOUT = 0.8
let DISC_IDENTIFY_TIMEOUT = 1.2

struct DiscRow: Identifiable, Hashable {
    let id = UUID()
    var ip: String
    var ports: [Int]
    var vendor: String
    var model: String
    var confirmed: Bool
    var portsText: String { ports.sorted().map(String.init).joined(separator: ", ") }
}

final class DiscoveryModel: ObservableObject {
    @Published var ranges: String {
        didSet { UserDefaults.standard.set(ranges, forKey: "disc_range") }
    }
    @Published var ports: String {
        didSet { UserDefaults.standard.set(ports, forKey: "disc_ports") }
    }
    @Published var parallel: Int {
        didSet { UserDefaults.standard.set(parallel, forKey: "disc_par") }
    }
    @Published var classes: Set<String> = Set(DISC_CLASSES.map { $0.0 })
    @Published var onlyConfirmed = false
    @Published var rows: [DiscRow] = []
    @Published var log: [String] = []
    @Published var status = "Bereit"
    @Published var progress: Double = 0
    @Published var running = false

    private let stop = StopFlag()
    private let engineQ = DispatchQueue(label: "pa.discovery.engine", qos: .userInitiated)

    init() {
        let d = UserDefaults.standard
        var def = Net.defaultTarget()
        if !def.contains("/") { def += ".1-254" }
        ranges = d.string(forKey: "disc_range") ?? def
        ports = d.string(forKey: "disc_ports") ?? ""
        let p = d.integer(forKey: "disc_par")
        parallel = p > 0 ? p : 48
    }

    var visibleRows: [DiscRow] {
        onlyConfirmed ? rows.filter { $0.confirmed } : rows
    }

    private func ui(_ block: @escaping () -> Void) { DispatchQueue.main.async(execute: block) }
    private func addLog(_ m: String) {
        let line = "[\(Txt.now())] " + m
        ui { self.log.append(line) }
    }

    func portList() -> [Int] {
        var out: [Int] = []
        var seen = Set<Int>()
        for tok in ports.split(whereSeparator: { $0 == "," || $0 == " " || $0 == ";" }) {
            if let p = Int(tok), p > 0, p < 65536, seen.insert(p).inserted { out.append(p) }
        }
        if out.isEmpty {
            for (name, ps) in DISC_CLASSES where classes.contains(name) || classes.isEmpty {
                for p in ps {
                    if seen.insert(p).inserted { out.append(p) }
                }
            }
        }
        return out.sorted()
    }

    func stopScan() { stop.set(); status = "Stoppe..." }

    func start() {
        if running { return }
        rows = []; log = []; progress = 0
        stop.reset()
        running = true
        status = "Suche laeuft ..."
        let hosts = Net.hostsFrom(ranges)
        let ps = portList()
        let workers = max(1, min(128, parallel))
        engineQ.async {
            self.scan(hosts: hosts, ports: ps, workers: workers)
            self.ui { self.running = false }
        }
    }

    // ------------------------------------------------------- Ablauf
    private func scan(hosts: [String], ports: [Int], workers: Int) {
        if hosts.isEmpty || ports.isEmpty {
            addLog("Keine Hosts oder Ports - Eingaben pruefen")
            ui { self.status = "Bereit" }
            return
        }
        var tasks: [(String, Int)] = []
        for h in hosts { for p in ports { tasks.append((h, p)) } }
        let total = tasks.count
        addLog("Phase 1: \(hosts.count) Hosts x \(ports.count) Ports = \(total) Pruefungen")
        let lock = NSLock()
        var found: [String: DiscRow] = [:]
        let done = Counter()
        Par.run(tasks, max: workers, stop: stop) { t in
            let ok = Net.tcpProbe(t.0, t.1, timeout: DISC_CONNECT_TIMEOUT) == .open
            let d = done.inc()
            if d % 25 == 0 || d == total {
                lock.lock(); let n = found.count; lock.unlock()
                self.ui {
                    self.progress = Double(d) / Double(total)
                    self.status = "\(d) / \(total) geprueft - \(n) Geraete"
                }
            }
            if ok {
                lock.lock()
                var r = found[t.0] ?? DiscRow(ip: t.0, ports: [], vendor: "", model: "", confirmed: false)
                if !r.ports.contains(t.1) { r.ports.append(t.1) }
                if let v = PORT_VENDOR[t.1] {
                    if r.vendor.isEmpty { r.vendor = v }
                    r.confirmed = true
                }
                found[t.0] = r
                lock.unlock()
            }
        }
        if !stop.isSet {
            addLog("Phase 2: Modell-/Marken-Abfrage fuer \(found.count) Geraete")
            ui { self.status = "Modellabfrage ..." }
            Par.run(Array(found.keys), max: min(workers, 24), stop: stop) { ip in
                lock.lock(); guard var r = found[ip] else { lock.unlock(); return }; lock.unlock()
                self.identify(&r)
                lock.lock(); found[ip] = r; lock.unlock()
            }
        }
        var list = Array(found.values)
        for i in list.indices where list[i].vendor.isEmpty {
            list[i].vendor = classifyFromPorts(list[i].ports) ?? "?"
        }
        list.sort { Net.ipKey($0.ip) < Net.ipKey($1.ip) }
        let conf = list.filter { $0.confirmed }.count
        addLog(stop.isSet ? "Abgebrochen" : "Fertig: \(conf) bestaetigt, \(list.count) gesamt")
        ui {
            self.rows = list
            self.progress = 1
            self.status = "Fertig: \(conf) bestaetigt, \(list.count) gesamt"
        }
    }

    private func classifyFromPorts(_ ports: [Int]) -> String? {
        for p in [1710, 41794, 22023, 2202, 4352, 7142, 1515, 9761] where ports.contains(p) {
            return PORT_VENDOR[p]
        }
        return nil
    }

    private func identify(_ r: inout DiscRow) {
        let ps = Set(r.ports)
        var vendor = "", model = ""
        if ps.contains(1710) { (vendor, model) = identQRC(r.ip) }
        else if ps.contains(4352) { (vendor, model) = identPJLink(r.ip) }
        else if ps.contains(2202) { (vendor, model) = identShure(r.ip) }
        else if ps.contains(22023) { (vendor, model) = identBanner(r.ip, 22023) }
        else if ps.contains(80) { (vendor, model) = identHTTP(r.ip) }
        else if ps.contains(23) { (vendor, model) = identBanner(r.ip, 23) }
        if !vendor.isEmpty { r.vendor = vendor; r.confirmed = true }
        if !model.isEmpty { r.model = model.trimmingCharacters(in: .whitespaces) }
        if !r.confirmed && ps.contains(80) {
            let (v2, m2) = identHTTP(r.ip)
            if !v2.isEmpty { r.vendor = v2; r.confirmed = true }
            if !m2.isEmpty && r.model.isEmpty { r.model = m2 }
        }
    }

    // ------------------------------------------------ Identify-Routinen
    private func str(_ d: Data?) -> String {
        guard let d = d else { return "" }
        return String(decoding: d, as: UTF8.self)
    }

    private func brand(_ text: String) -> String {
        let low = text.lowercased()
        for (tok, name) in BRANDS where low.contains(tok) { return name }
        return ""
    }

    private func identQRC(_ ip: String) -> (String, String) {
        var q = Data("{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"StatusGet\",\"params\":0}".utf8)
        q.append(0)
        let raw = str(Net.exchange(ip, 1710, send: q, connectTimeout: DISC_CONNECT_TIMEOUT, readTimeout: DISC_IDENTIFY_TIMEOUT))
        let m = Txt.firstMatch("\"[Pp]latform\"\\s*:\\s*\"([^\"]+)\"", in: raw)
            ?? Txt.firstMatch("\"DesignName\"\\s*:\\s*\"([^\"]+)\"", in: raw)
        return ("Q-SYS", m ?? "")
    }

    private func identPJLink(_ ip: String) -> (String, String) {
        let q = Data("%1INF1 ?\r%1INF2 ?\r%1NAME ?\r".utf8)
        let raw = str(Net.exchange(ip, 4352, send: q, connectTimeout: DISC_CONNECT_TIMEOUT,
                                   readTimeout: DISC_IDENTIFY_TIMEOUT, readBannerFirst: true))
        if raw.isEmpty { return ("Display", "PJLink-Display") }
        let mfr = (Txt.firstMatch("%1INF1=([^\r\n]*)", in: raw) ?? "").trimmingCharacters(in: .whitespaces)
        let mdl = (Txt.firstMatch("%1INF2=([^\r\n]*)", in: raw) ?? "").trimmingCharacters(in: .whitespaces)
        let name = (Txt.firstMatch("%1NAME=([^\r\n]*)", in: raw) ?? "").trimmingCharacters(in: .whitespaces)
        let vendor = mfr.isEmpty || mfr.hasPrefix("ERR") ? "Display" : String(mfr.prefix(16))
        var parts: [String] = []
        if !mdl.isEmpty && !mdl.hasPrefix("ERR") { parts.append(mdl) }
        if !name.isEmpty && !name.hasPrefix("ERR") { parts.append("(\(name))") }
        return (vendor, parts.isEmpty ? "PJLink-Display" : parts.joined(separator: " "))
    }

    private func identShure(_ ip: String) -> (String, String) {
        let raw = str(Net.exchange(ip, 2202, send: Data("< GET MODEL_NAME >".utf8),
                                   connectTimeout: DISC_CONNECT_TIMEOUT, readTimeout: DISC_IDENTIFY_TIMEOUT))
        let m = Txt.firstMatch("MODEL_NAME\\s+\\{?([\\w\\-\\._ ]+)\\}?", in: raw)
        return ("Shure", (m ?? "").trimmingCharacters(in: .whitespaces))
    }

    private func identHTTP(_ ip: String, port: Int = 80) -> (String, String) {
        let q = Data("GET / HTTP/1.0\r\nHost: device\r\nConnection: close\r\n\r\n".utf8)
        let raw = str(Net.exchange(ip, port, send: q, connectTimeout: DISC_CONNECT_TIMEOUT,
                                   readTimeout: DISC_IDENTIFY_TIMEOUT))
        if raw.isEmpty { return ("", "") }
        let vendor = brand(raw)
        var model = ""
        if let t = Txt.firstMatch("<title>(.*?)</title>", in: raw, options: [.caseInsensitive, .dotMatchesLineSeparators]) {
            let c = t.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
            if c.count >= 2 && c.count <= 60 { model = c }
        }
        return (vendor, model)
    }

    private func identBanner(_ ip: String, _ port: Int) -> (String, String) {
        let send: Data? = (port == 23 || port == 41794) ? Data("ver\r\n".utf8) : nil
        let raw = str(Net.exchange(ip, port, send: send, connectTimeout: DISC_CONNECT_TIMEOUT,
                                   readTimeout: DISC_IDENTIFY_TIMEOUT, readBannerFirst: true))
        return (brand(raw), "")
    }

    // ---------------------------------------------------------- Export
    func exportCSV() -> URL? {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        let data = visibleRows.map { [$0.ip, $0.vendor, $0.model, $0.portsText, $0.confirmed ? "ja" : "nein"] }
        return Txt.writeCSV(name: "Discovery_\(Txt.stamp()).csv",
                            title: "AV-Discovery - \(ranges) - \(f.string(from: Date())) - Autor: T. Pfeiffer",
                            headers: ["IP-Adresse", "Hersteller", "Modell", "Offene Ports", "Bestaetigt"],
                            rows: data)
    }
}
