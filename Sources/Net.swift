// ===========================================================================
//  Net.swift - PA AV Toolbox iOS v1.0.0
//  Autor: T. Pfeiffer
//  Low-Level-Netzwerk: TCP-Probe, TCP-Austausch, Reverse-DNS, NetBIOS,
//  eigene IP, Adressbereiche, ICMP-Ping. Alles blockierend -> nur aus
//  Hintergrund-Threads aufrufen.
// ===========================================================================
import Foundation
import Darwin

enum ProbeResult {
    case open, refused, timeout
}

/// Thread-sicheres Stop-Flag
final class StopFlag {
    private let lock = NSLock()
    private var value = false
    var isSet: Bool {
        lock.lock(); defer { lock.unlock() }
        return value
    }
    func set() { lock.lock(); value = true; lock.unlock() }
    func reset() { lock.lock(); value = false; lock.unlock() }
}

/// Thread-sicherer Zaehler
final class Counter {
    private let lock = NSLock()
    private var value = 0
    func inc() -> Int {
        lock.lock(); defer { lock.unlock() }
        value += 1
        return value
    }
}

/// Parallele Abarbeitung mit fester Thread-Zahl (blockierende Sockets)
enum Par {
    static func run<T>(_ items: [T], max: Int, stop: StopFlag, _ work: @escaping (T) -> Void) {
        let q = OperationQueue()
        q.maxConcurrentOperationCount = max
        q.qualityOfService = .userInitiated
        for it in items {
            q.addOperation {
                if stop.isSet { return }
                work(it)
            }
        }
        q.waitUntilAllOperationsAreFinished()
    }
}

enum Net {

    // ------------------------------------------------------------------ IP
    static func ipToUInt(_ s: String) -> UInt32? {
        let p = s.split(separator: ".", omittingEmptySubsequences: false)
        guard p.count == 4 else { return nil }
        var v: UInt32 = 0
        for x in p {
            guard let n = UInt32(x), n < 256 else { return nil }
            v = (v << 8) | n
        }
        return v
    }

    static func uintToIP(_ v: UInt32) -> String {
        return "\((v >> 24) & 255).\((v >> 16) & 255).\((v >> 8) & 255).\(v & 255)"
    }

    static func ipKey(_ ip: String) -> UInt32 {
        return ipToUInt(ip) ?? 0
    }

    static func isIPv4(_ s: String) -> Bool {
        return ipToUInt(s) != nil
    }

    static func makeAddr(_ ip: String, _ port: UInt16) -> sockaddr_in? {
        var a = sockaddr_in()
        a.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        a.sin_family = sa_family_t(AF_INET)
        a.sin_port = port.bigEndian
        guard inet_pton(AF_INET, ip, &a.sin_addr) == 1 else { return nil }
        return a
    }

    static func ipString(_ sa: UnsafeMutablePointer<sockaddr>) -> String {
        var a = sa.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { $0.pointee.sin_addr }
        var buf = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
        _ = inet_ntop(AF_INET, &a, &buf, socklen_t(INET_ADDRSTRLEN))
        return String(cString: buf)
    }

    /// Eigene IPv4 (WLAN en0 bevorzugt) mit Netzmaske
    static func localIPv4() -> (ip: String, mask: String)? {
        var ifap: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifap) == 0, let first = ifap else { return nil }
        defer { freeifaddrs(ifap) }
        var best: (String, String)?
        var p: UnsafeMutablePointer<ifaddrs>? = first
        while let cur = p {
            let ifa = cur.pointee
            if let sa = ifa.ifa_addr, sa.pointee.sa_family == sa_family_t(AF_INET) {
                let name = String(cString: ifa.ifa_name)
                let ip = ipString(sa)
                var mask = "255.255.255.0"
                if let m = ifa.ifa_netmask { mask = ipString(m) }
                if name == "en0" { return (ip, mask) }
                if best == nil && name.hasPrefix("en") && !ip.hasPrefix("169.254") {
                    best = (ip, mask)
                }
            }
            p = ifa.ifa_next
        }
        if let b = best { return (b.0, b.1) }
        return nil
    }

    /// Vorschlag fuer das Ziel-Feld aus eigener IP: "192.168.0" oder "10.1.0.0/22"
    static func defaultTarget() -> String {
        guard let l = localIPv4(), let ip = ipToUInt(l.ip), let m = ipToUInt(l.mask) else {
            return "192.168.0"
        }
        let prefix = m.nonzeroBitCount
        if prefix == 24 {
            let p = l.ip.split(separator: ".")
            return "\(p[0]).\(p[1]).\(p[2])"
        }
        let p = max(16, prefix)
        let mask: UInt32 = p >= 32 ? 0xFFFF_FFFF : ~UInt32(0) << UInt32(32 - p)
        return "\(uintToIP(ip & mask))/\(p)"
    }

    /// Bereichs-Parser: a.b.c.d | a.b.c.d-e | a.b.c | a.b.c.d/nn | mehrere mit Komma
    static func hostsFrom(_ target: String, cap: Int = 4096) -> [String] {
        var out: [String] = []
        var seen = Set<String>()
        func add(_ ip: String) {
            if out.count < cap && seen.insert(ip).inserted { out.append(ip) }
        }
        for raw in target.split(separator: ",") {
            let c = raw.trimmingCharacters(in: .whitespaces)
            if c.isEmpty { continue }
            if c.contains("/") {
                let sp = c.split(separator: "/")
                guard sp.count == 2, let base = ipToUInt(String(sp[0])),
                      let pfx = Int(sp[1]), pfx >= 16, pfx <= 32 else { continue }
                let mask: UInt32 = pfx >= 32 ? 0xFFFF_FFFF : ~UInt32(0) << UInt32(32 - pfx)
                let net = base & mask
                let size = UInt32(1) << UInt32(32 - pfx)
                if size <= 2 {
                    for i in 0..<size { add(uintToIP(net + i)) }
                } else {
                    var i: UInt32 = 1
                    while i < size - 1 && out.count < cap {
                        add(uintToIP(net + i))
                        i += 1
                    }
                }
                continue
            }
            let parts = c.split(separator: ".", omittingEmptySubsequences: false).map(String.init)
            if parts.count == 4 && parts[3].contains("-") {
                let rr = parts[3].split(separator: "-")
                let base = parts[0...2].joined(separator: ".")
                guard rr.count == 2, let lo = Int(rr[0]), let hi = Int(rr[1]),
                      lo >= 0, hi <= 255, lo <= hi, ipToUInt(base + ".0") != nil else { continue }
                for i in lo...hi { add("\(base).\(i)") }
                continue
            }
            if parts.count == 4 {
                if isIPv4(c) { add(c) }
                continue
            }
            if parts.count == 3 && ipToUInt(c + ".0") != nil {
                for i in 1...254 { add("\(c).\(i)") }
            }
        }
        return out
    }

    // ----------------------------------------------------------------- TCP
    /// Nicht-blockierender Connect mit Timeout. Liefert fd (>=0) bei .open,
    /// der Aufrufer muss ihn schliessen.
    static func connectFD(_ ip: String, _ port: Int, timeout: Double) -> (Int32, ProbeResult) {
        guard port > 0, port < 65536, var addr = makeAddr(ip, UInt16(port)) else { return (-1, .timeout) }
        let fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        if fd < 0 { return (-1, .timeout) }
        var one: Int32 = 1
        _ = setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, socklen_t(MemoryLayout<Int32>.size))
        let flags = fcntl(fd, F_GETFL, 0)
        _ = fcntl(fd, F_SETFL, flags | O_NONBLOCK)
        let rc = withUnsafePointer(to: &addr) { ptr -> Int32 in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sp in
                Darwin.connect(fd, sp, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        if rc == 0 { return (fd, .open) }
        let err = errno
        if err == ECONNREFUSED { Darwin.close(fd); return (-1, .refused) }
        if err != EINPROGRESS { Darwin.close(fd); return (-1, .timeout) }
        var pfd = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
        let pr = poll(&pfd, 1, Int32(timeout * 1000))
        if pr <= 0 { Darwin.close(fd); return (-1, .timeout) }
        var soErr: Int32 = 0
        var len = socklen_t(MemoryLayout<Int32>.size)
        _ = getsockopt(fd, SOL_SOCKET, SO_ERROR, &soErr, &len)
        if soErr == 0 { return (fd, .open) }
        Darwin.close(fd)
        return (-1, soErr == ECONNREFUSED ? .refused : .timeout)
    }

    static func tcpProbe(_ ip: String, _ port: Int, timeout: Double) -> ProbeResult {
        let (fd, r) = connectFD(ip, port, timeout: timeout)
        if fd >= 0 { Darwin.close(fd) }
        return r
    }

    static func writeAll(_ fd: Int32, _ d: Data) -> Bool {
        let total = d.count
        if total == 0 { return true }
        return d.withUnsafeBytes { (raw: UnsafeRawBufferPointer) -> Bool in
            guard let base = raw.baseAddress else { return true }
            var sent = 0
            while sent < total {
                let n = Darwin.send(fd, base + sent, total - sent, 0)
                if n > 0 { sent += n; continue }
                if n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
                    var p = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
                    if poll(&p, 1, 2000) <= 0 { return false }
                    continue
                }
                return false
            }
            return true
        }
    }

    /// Liest bis eine Pause > timeout, limit erreicht oder Gegenstelle schliesst
    static func readAvailable(_ fd: Int32, timeout: Double, limit: Int, single: Bool = false) -> Data {
        var out = Data()
        var buf = [UInt8](repeating: 0, count: 2048)
        while out.count < limit {
            var p = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
            let pr = poll(&p, 1, Int32(timeout * 1000))
            if pr <= 0 { break }
            let n = Darwin.recv(fd, &buf, buf.count, 0)
            if n <= 0 { break }
            out.append(contentsOf: buf[0..<n])
            if single { break }
        }
        return out
    }

    /// Verbinden, optional Banner lesen, senden, Antwort lesen
    static func exchange(_ ip: String, _ port: Int, send: Data?, connectTimeout: Double = 0.8,
                         readTimeout: Double = 1.2, limit: Int = 4096, readBannerFirst: Bool = false) -> Data? {
        let (fd, r) = connectFD(ip, port, timeout: connectTimeout)
        guard r == .open, fd >= 0 else { return nil }
        defer { Darwin.close(fd) }
        var out = Data()
        if readBannerFirst {
            out.append(readAvailable(fd, timeout: readTimeout, limit: 256, single: true))
        }
        if let s = send, !s.isEmpty {
            _ = writeAll(fd, s)
        }
        out.append(readAvailable(fd, timeout: readTimeout, limit: limit))
        return out
    }

    // ----------------------------------------------------------- Namen
    /// Fuehrt work aus, gibt nach seconds den Standardwert zurueck
    static func withTimeout<T>(_ seconds: Double, fallback: T, _ work: @escaping () -> T) -> T {
        let sem = DispatchSemaphore(value: 0)
        let lock = NSLock()
        var result = fallback
        DispatchQueue.global(qos: .utility).async {
            let r = work()
            lock.lock(); result = r; lock.unlock()
            sem.signal()
        }
        if sem.wait(timeout: .now() + seconds) == .timedOut { return fallback }
        lock.lock(); defer { lock.unlock() }
        return result
    }

    static func reverseDNS(_ ip: String) -> String {
        return withTimeout(2.0, fallback: "") {
            guard var a = makeAddr(ip, 0) else { return "" }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            let rc = withUnsafePointer(to: &a) { ptr -> Int32 in
                ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sp in
                    getnameinfo(sp, socklen_t(MemoryLayout<sockaddr_in>.size),
                                &host, socklen_t(host.count), nil, 0, NI_NAMEREQD)
                }
            }
            if rc != 0 { return "" }
            let name = String(cString: host)
            return name == ip ? "" : name
        }
    }

    /// NetBIOS-Name ueber NBSTAT-Abfrage (UDP 137), Eintrag <00> UNIQUE
    static func netbiosName(_ ip: String, timeout: Double = 1.0) -> String {
        guard var addr = makeAddr(ip, 137) else { return "" }
        let fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        if fd < 0 { return "" }
        defer { Darwin.close(fd) }
        var q: [UInt8] = [0x13, 0x37, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x20]
        q.append(contentsOf: [0x43, 0x4B])                              // '*'
        q.append(contentsOf: [UInt8](repeating: 0x41, count: 30))       // 15 x NUL
        q.append(contentsOf: [0x00, 0x00, 0x21, 0x00, 0x01])            // NBSTAT, IN
        let sent = withUnsafePointer(to: &addr) { ptr -> Int in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sp in
                sendto(fd, q, q.count, 0, sp, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        if sent < 0 { return "" }
        var p = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
        if poll(&p, 1, Int32(timeout * 1000)) <= 0 { return "" }
        var buf = [UInt8](repeating: 0, count: 1024)
        let n = Darwin.recv(fd, &buf, buf.count, 0)
        if n < 57 { return "" }
        let cnt = Int(buf[56])
        var off = 57
        for _ in 0..<cnt {
            if off + 18 > n { break }
            let suffix = buf[off + 15]
            let flags = (UInt16(buf[off + 16]) << 8) | UInt16(buf[off + 17])
            if suffix == 0x00 && (flags & 0x8000) == 0 {
                let s = String(decoding: buf[off..<(off + 15)], as: UTF8.self)
                    .trimmingCharacters(in: .whitespaces)
                if !s.isEmpty { return s }
            }
            off += 18
        }
        return ""
    }

    static func resolveIPv4(_ host: String) -> String? {
        let h = host.trimmingCharacters(in: .whitespaces)
        if isIPv4(h) { return h }
        var hints = addrinfo()
        hints.ai_family = AF_INET
        hints.ai_socktype = SOCK_STREAM
        var res: UnsafeMutablePointer<addrinfo>?
        guard getaddrinfo(h, nil, &hints, &res) == 0, let r = res else { return nil }
        defer { freeaddrinfo(res) }
        guard let sa = r.pointee.ai_addr else { return nil }
        return ipString(sa)
    }
}

// ===========================================================================
//  ICMP-Ping ohne Root (SOCK_DGRAM / IPPROTO_ICMP, unter iOS erlaubt)
// ===========================================================================
final class Pinger {
    private let ip: String
    private var fd: Int32 = -1
    private var seq: UInt16 = 0
    private let ident = UInt16.random(in: 1...0xFFFE)

    init?(ip: String) {
        self.ip = ip
        fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)
        if fd < 0 { return nil }
    }

    deinit {
        if fd >= 0 { Darwin.close(fd) }
    }

    static func checksum(_ b: [UInt8]) -> UInt16 {
        var sum: UInt32 = 0
        var i = 0
        while i + 1 < b.count {
            sum += (UInt32(b[i]) << 8) | UInt32(b[i + 1])
            i += 2
        }
        if i < b.count { sum += UInt32(b[i]) << 8 }
        while (sum >> 16) != 0 { sum = (sum & 0xFFFF) + (sum >> 16) }
        return ~UInt16(sum & 0xFFFF)
    }

    /// Antwortzeit in ms oder nil bei Zeitueberschreitung
    func ping(timeout: Double = 1.0) -> Double? {
        guard var addr = Net.makeAddr(ip, 0) else { return nil }
        seq &+= 1
        var pkt = [UInt8](repeating: 0, count: 40)
        pkt[0] = 8
        pkt[4] = UInt8(ident >> 8); pkt[5] = UInt8(ident & 0xFF)
        pkt[6] = UInt8(seq >> 8); pkt[7] = UInt8(seq & 0xFF)
        for i in 8..<pkt.count { pkt[i] = UInt8(i & 0xFF) }
        let ck = Pinger.checksum(pkt)
        pkt[2] = UInt8(ck >> 8); pkt[3] = UInt8(ck & 0xFF)
        let t0 = Date()
        let sent = withUnsafePointer(to: &addr) { ptr -> Int in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sp in
                sendto(fd, pkt, pkt.count, 0, sp, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        if sent < 0 { return nil }
        var buf = [UInt8](repeating: 0, count: 1500)
        while true {
            let left = timeout - Date().timeIntervalSince(t0)
            if left <= 0 { return nil }
            var p = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
            if poll(&p, 1, Int32(left * 1000)) <= 0 { return nil }
            let n = Darwin.recv(fd, &buf, buf.count, 0)
            if n <= 0 { return nil }
            var off = 0
            if (buf[0] >> 4) == 4 { off = Int(buf[0] & 0x0F) * 4 }    // IP-Header vorhanden
            if n >= off + 8 && buf[off] == 0 {
                let rseq = (UInt16(buf[off + 6]) << 8) | UInt16(buf[off + 7])
                if rseq == seq {
                    return Date().timeIntervalSince(t0) * 1000.0
                }
            }
        }
    }
}

// ===========================================================================
//  Kleine Helfer
// ===========================================================================
enum Txt {
    static func firstMatch(_ pattern: String, in s: String, group: Int = 1,
                           options: NSRegularExpression.Options = []) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern, options: options) else { return nil }
        let ns = s as NSString
        guard let m = re.firstMatch(in: s, range: NSRange(location: 0, length: ns.length)),
              m.numberOfRanges > group else { return nil }
        let r = m.range(at: group)
        if r.location == NSNotFound { return nil }
        return ns.substring(with: r)
    }

    static func hex(_ d: Data) -> String {
        return d.map { String(format: "%02X", $0) }.joined(separator: " ")
    }

    static func printable(_ d: Data) -> String {
        var s = ""
        for x in d {
            if x == 10 { s += "\n" }
            else if x == 13 { continue }
            else if x >= 32 && x < 127 { s.append(Character(UnicodeScalar(x))) }
            else { s += String(format: "<%02X>", x) }
        }
        return s
    }

    /// "81 01 04 00 02 FF" / "0x81,0x01" / "81:01" -> Bytes
    static func parseHex(_ s: String) -> Data? {
        var t = s.replacingOccurrences(of: "0x", with: " ")
        t = t.replacingOccurrences(of: "\\x", with: " ")
        for c in [",", ";", ":", "-"] { t = t.replacingOccurrences(of: c, with: " ") }
        var out = Data()
        for part in t.split(separator: " ") where !part.isEmpty {
            guard let v = UInt8(part, radix: 16) else { return nil }
            out.append(v)
        }
        return out
    }

    /// Escape-Folgen: \r \n \t \0 \\ \xHH (wie Windows-Toolbox)
    static func unescape(_ s: String) -> Data {
        var out = Data()
        let chars = Array(s.unicodeScalars)
        var i = 0
        while i < chars.count {
            let c = chars[i]
            if c == "\\" && i + 1 < chars.count {
                let n = chars[i + 1]
                switch n {
                case "r": out.append(13); i += 2; continue
                case "n": out.append(10); i += 2; continue
                case "t": out.append(9); i += 2; continue
                case "0": out.append(0); i += 2; continue
                case "\\": out.append(92); i += 2; continue
                case "x":
                    if i + 3 < chars.count {
                        let h = String(Character(chars[i + 2])) + String(Character(chars[i + 3]))
                        if let v = UInt8(h, radix: 16) { out.append(v); i += 4; continue }
                    }
                default: break
                }
            }
            if c.value < 256 { out.append(UInt8(c.value)) }
            i += 1
        }
        return out
    }

    static func now() -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f.string(from: Date())
    }

    static func stamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd_HHmm"
        return f.string(from: Date())
    }

    static func csvField(_ s: String) -> String {
        if s.contains(";") || s.contains("\"") || s.contains("\n") {
            return "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\""
        }
        return s
    }

    /// CSV (Semikolon, UTF-8 mit BOM) in eine temporaere Datei schreiben
    static func writeCSV(name: String, title: String, headers: [String], rows: [[String]]) -> URL? {
        var s = "\u{FEFF}"
        s += csvField(title) + "\r\n"
        s += "Eintraege gesamt: \(rows.count)\r\n\r\n"
        s += headers.map(csvField).joined(separator: ";") + "\r\n"
        for r in rows { s += r.map(csvField).joined(separator: ";") + "\r\n" }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name)
        do {
            try s.write(to: url, atomically: true, encoding: .utf8)
            return url
        } catch {
            return nil
        }
    }
}
