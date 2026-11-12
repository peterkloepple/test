// ===========================================================================
//  ScannerModel.swift - PA AV Toolbox iOS v1.0.0
//  Autor: T. Pfeiffer
//  NetScanner (aus Toolbox 1.3.0): Port-Scan / IP-Scan / Deep-Scan.
//  MAC-Scan und Herstellerspalte entfallen: iOS gibt Apps keinen Zugriff
//  auf die ARP-Tabelle.
// ===========================================================================
import Foundation

let NS_IP_PROBE_PORTS = [80, 443, 22, 7000, 3389, 445, 8080]
let NS_DEEP_PROBE_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445,
    502, 515, 554, 587, 631, 993, 995, 1080, 1194, 1433, 1521,
    1710, 1723, 1883, 2202, 3000, 3306, 3389, 5000, 5060, 5222,
    5353, 5432, 5900, 6024, 7000, 8000, 8008, 8080, 8443, 8888,
    9000, 9100, 22023, 41794, 49152,
]
let NS_SERVICE: [Int: String] = [
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 135: "RPC", 139: "NetBIOS", 143: "IMAP",
    443: "HTTPS", 445: "SMB", 502: "Modbus", 554: "RTSP", 631: "IPP",
    1433: "MSSQL", 1710: "QSYS-QRC", 2202: "Shure", 3306: "MySQL",
    3389: "RDP", 5060: "SIP", 5432: "Postgres", 5900: "VNC",
    6024: "Yealink", 7000: "QSYS", 8080: "HTTP-Alt", 8443: "HTTPS-Alt",
    9100: "Printer", 22023: "Extron", 41794: "Crestron-CIP",
]
let NS_CONNECT_TIMEOUT = 0.4
let NS_PORTSCAN_WORKERS = 100
let NS_HOSTSCAN_WORKERS = 64

func nsSvc(_ p: Int) -> String {
    return NS_SERVICE[p] ?? String(p)
}

enum ScanMode: String, CaseIterable, Identifiable {
    case port = "Port"
    case ip = "IP"
    case deep = "Deep"
    var id: String { rawValue }
    var title: String {
        switch self {
        case .port: return "Port-Scan"
        case .ip: return "IP-Scan"
        case .deep: return "Deep-Scan"
        }
    }
}

struct ScanRow: Identifiable, Hashable {
    let id = UUID()
    var ip: String
    var ports: String
    var host: String
}

final class ScannerModel: ObservableObject {
    @Published var target: String {
        didSet { UserDefaults.standard.set(target, forKey: "ns_target") }
    }
    @Published var p1: String {
        didSet { UserDefaults.standard.set(p1, forKey: "ns_p1") }
    }
    @Published var p2: String {
        didSet { UserDefaults.standard.set(p2, forKey: "ns_p2") }
    }
    @Published var mode: ScanMode = .ip
    @Published var rows: [ScanRow] = []
    @Published var log: [String] = []
    @Published var status = "Bereit"
    @Published var progress: Double = 0
    @Published var running = false
    @Published var lastTarget = ""

    private let stop = StopFlag()
    private let engineQ = DispatchQueue(label: "pa.netscanner.engine", qos: .userInitiated)

    init() {
        let d = UserDefaults.standard
        target = d.string(forKey: "ns_target") ?? Net.defaultTarget()
        p1 = d.string(forKey: "ns_p1") ?? "1"
        p2 = d.string(forKey: "ns_p2") ?? "1024"
    }

    // ------------------------------------------------ UI-Rueckmeldungen
    private func ui(_ block: @escaping () -> Void) {
        DispatchQueue.main.async(execute: block)
    }
    private func addLog(_ m: String) {
        let line = "[\(Txt.now())] " + m
        ui { self.log.append(line); if self.log.count > 400 { self.log.removeFirst(100) } }
    }
    private func setStatus(_ s: String) { ui { self.status = s } }
    private func setProgress(_ d: Int, _ t: Int) {
        ui { self.progress = t > 0 ? Double(d) / Double(t) : 0; self.status = "\(d) / \(t) geprueft" }
    }
    private func addRow(_ r: ScanRow) { ui { self.rows.append(r) } }
    private func finish() {
        ui {
            self.running = false
            if self.status.hasSuffix("geprueft") || self.status == "Stoppe..." { self.status = "Bereit" }
        }
    }

    func useOwnNet() {
        target = Net.defaultTarget()
    }

    func clear() {
        rows = []
        log = []
        progress = 0
        status = "Bereit"
    }

    func stopScan() {
        stop.set()
        status = "Stoppe..."
    }

    func start() {
        if running { return }
        clear()
        stop.reset()
        running = true
        status = "Scan laeuft ..."
        let t = target.trimmingCharacters(in: .whitespaces)
        lastTarget = t
        let m = mode
        var a = Int(p1) ?? 1
        var b = Int(p2) ?? 1024
        if a > b { swap(&a, &b) }
        a = max(1, a); b = min(65535, b)
        engineQ.async {
            switch m {
            case .port: self.runPortscan(t, a, b)
            case .ip: self.runIPscan(t)
            case .deep: self.runDeepscan(t)
            }
            self.finish()
        }
    }

    // ------------------------------------------------------- Port-Scan
    private func runPortscan(_ ip: String, _ p1: Int, _ p2: Int) {
        guard Net.isIPv4(ip) else {
            addLog("Bitte EINE Ziel-IP angeben (z.B. 192.168.0.10)")
            return
        }
        let ports = Array(p1...p2)
        let total = ports.count
        addLog("PORT-SCAN \(ip)  Ports \(p1)-\(p2)")
        let done = Counter()
        let found = Counter()
        Par.run(ports, max: NS_PORTSCAN_WORKERS, stop: stop) { port in
            let r = Net.tcpProbe(ip, port, timeout: NS_CONNECT_TIMEOUT)
            let d = done.inc()
            if d % 50 == 0 || d == total { self.setProgress(d, total) }
            if r == .open {
                _ = found.inc()
                self.addRow(ScanRow(ip: ip, ports: "\(port) offen", host: nsSvc(port)))
                self.addLog("OFFEN -> \(port) (\(nsSvc(port)))")
            }
        }
        // nach Portnummer sortieren
        ui {
            self.rows.sort { (Int($0.ports.split(separator: " ").first ?? "0") ?? 0) <
                             (Int($1.ports.split(separator: " ").first ?? "0") ?? 0) }
            let n = self.rows.count
            self.status = "Port-Scan fertig - \(n) offen"
        }
        if stop.isSet { addLog("Abgebrochen") }
        addLog("FERTIG")
    }

    // --------------------------------------------------------- IP-Scan
    private func hostAlive(_ ip: String) -> Bool {
        var alive = false
        for p in NS_IP_PROBE_PORTS {
            if stop.isSet { return false }
            let r = Net.tcpProbe(ip, p, timeout: NS_CONNECT_TIMEOUT)
            if r == .open { return true }
            if r == .refused { alive = true }
        }
        return alive
    }

    private func runIPscan(_ target: String) {
        let hosts = Net.hostsFrom(target)
        if hosts.isEmpty {
            addLog("Ungueltiges Subnetz (z.B. 192.168.0 oder 192.168.0.0/24)")
            return
        }
        let total = hosts.count
        addLog("IP-SCAN \(target)  (\(total) Hosts)")
        let done = Counter()
        let lock = NSLock()
        var alive: [String] = []
        Par.run(hosts, max: NS_HOSTSCAN_WORKERS, stop: stop) { ip in
            let ok = self.hostAlive(ip)
            let d = done.inc()
            if d % 5 == 0 || d == total { self.setProgress(d, total) }
            if ok {
                lock.lock(); alive.append(ip); lock.unlock()
                self.addLog("HOST UP -> \(ip)")
            }
        }
        if stop.isSet { addLog("Abgebrochen"); return }
        setStatus("Loese Hostnamen auf...")
        let sorted = alive.sorted { Net.ipKey($0) < Net.ipKey($1) }
        var names: [String: String] = [:]
        Par.run(sorted, max: 16, stop: stop) { ip in
            let n = Net.reverseDNS(ip)
            lock.lock(); names[ip] = n; lock.unlock()
        }
        for ip in sorted {
            addRow(ScanRow(ip: ip, ports: "erreichbar", host: names[ip] ?? ""))
        }
        setStatus("IP-Scan fertig - \(sorted.count) Hosts")
        addLog("FERTIG - \(sorted.count) Hosts erreichbar")
    }

    // ------------------------------------------------------- Deep-Scan
    private func runDeepscan(_ target: String) {
        let hosts = Net.hostsFrom(target)
        if hosts.isEmpty {
            addLog("Ungueltiges Subnetz (z.B. 192.168.0 oder 192.168.0.0/24)")
            return
        }
        let total = hosts.count
        addLog("DEEP-SCAN \(target)  (\(total) Hosts, \(NS_DEEP_PROBE_PORTS.count) Ports)")
        let done = Counter()
        let lock = NSLock()
        var results: [(String, [Int])] = []
        Par.run(hosts, max: NS_HOSTSCAN_WORKERS, stop: stop) { ip in
            var open: [Int] = []
            for p in NS_DEEP_PROBE_PORTS {
                if self.stop.isSet { break }
                if Net.tcpProbe(ip, p, timeout: NS_CONNECT_TIMEOUT) == .open { open.append(p) }
            }
            let d = done.inc()
            if d % 3 == 0 || d == total { self.setProgress(d, total) }
            if !open.isEmpty {
                lock.lock(); results.append((ip, open)); lock.unlock()
            }
        }
        if stop.isSet { addLog("Abgebrochen"); return }
        setStatus("Loese Hostnamen auf...")
        let sorted = results.sorted { Net.ipKey($0.0) < Net.ipKey($1.0) }
        var names: [String: String] = [:]
        Par.run(sorted.map { $0.0 }, max: 16, stop: stop) { ip in
            var n = Net.reverseDNS(ip)
            if n.isEmpty { n = Net.netbiosName(ip) }
            lock.lock(); names[ip] = n; lock.unlock()
        }
        for (ip, open) in sorted {
            let ps = open.map { "\($0)/\(nsSvc($0))" }.joined(separator: ", ")
            let n = names[ip] ?? ""
            addRow(ScanRow(ip: ip, ports: ps, host: n.isEmpty ? "?" : n))
            addLog("DEEP UP -> \(ip)  \(n.isEmpty ? "?" : n)")
        }
        setStatus("Deep-Scan fertig - \(sorted.count) Hosts")
        addLog("FERTIG - \(sorted.count) Hosts")
    }

    // ---------------------------------------------------------- Export
    func exportCSV(ip: Bool, ports: Bool, host: Bool) -> URL? {
        var heads: [String] = []
        if ip { heads.append("IP-Adresse") }
        if ports { heads.append("Ports / Status") }
        if host { heads.append("Hostname") }
        let data: [[String]] = rows.map { r in
            var a: [String] = []
            if ip { a.append(r.ip) }
            if ports { a.append(r.ports) }
            if host { a.append(r.host) }
            return a
        }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm"
        let tn = lastTarget.replacingOccurrences(of: "/", with: "-").replacingOccurrences(of: ".", with: "_")
        return Txt.writeCSV(name: "Scan_\(tn.isEmpty ? "Scan" : tn)_\(Txt.stamp()).csv",
                            title: "NetScanner - Ziel: \(lastTarget) - \(f.string(from: Date())) - Autor: T. Pfeiffer",
                            headers: heads, rows: data)
    }
}
