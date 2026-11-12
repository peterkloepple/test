// ===========================================================================
//  Net.swift - Studio Control iOS - Netzwerk-Kern (TCP, UDP, HTTP)
//  Autor: T. Pfeiffer
//  TCPConnection: NWConnection mit Empfangspuffer (kein Datenverlust bei Timeout)
//  UDPExchange:   eine Anfrage, eine Antwort (SNMP, Discovery)
//  HTTPClient:    URLSession mit eigenen Cookies, Basic/Digest, selbstsignierte Zertifikate
// ===========================================================================
import Foundation
import Network

enum NetError: LocalizedError {
    case timeout(String)
    case closed
    case badAddress(String)
    case http(Int, String)
    case protocolError(String)

    var errorDescription: String? {
        switch self {
        case .timeout(let what): return "Zeitüberschreitung: \(what)"
        case .closed: return "Verbindung getrennt"
        case .badAddress(let a): return "Ungültige Adresse: \(a)"
        case .http(let code, let text): return "HTTP \(code): \(text)"
        case .protocolError(let t): return t
        }
    }
}

/// Fuehrt einen Block genau einmal aus (Continuations duerfen nur einmal fortgesetzt werden).
final class Once {
    private var done = false
    private let lock = NSLock()
    func run(_ block: () -> Void) {
        lock.lock()
        if done { lock.unlock(); return }
        done = true
        lock.unlock()
        block()
    }
}

// ---------------------------------------------------------------------------
// TCP
// ---------------------------------------------------------------------------
final class TCPConnection {
    let host: String
    let port: UInt16
    private let conn: NWConnection
    private let queue: DispatchQueue
    private var buffer = Data()          // nur auf queue
    private var closedFlag = false       // nur auf queue

    init(host: String, port: UInt16) throws {
        let h = host.trimmingCharacters(in: .whitespaces)
        guard !h.isEmpty, port > 0, let p = NWEndpoint.Port(rawValue: port) else {
            throw NetError.badAddress("\(host):\(port)")
        }
        self.host = h
        self.port = port
        let tcp = NWProtocolTCP.Options()
        tcp.noDelay = true
        tcp.connectionTimeout = 6
        let params = NWParameters(tls: nil, tcp: tcp)
        conn = NWConnection(host: NWEndpoint.Host(h), port: p, using: params)
        queue = DispatchQueue(label: "tcp.\(h).\(port)")
    }

    deinit { conn.cancel() }

    var isClosed: Bool { queue.sync { closedFlag } }

    func connect(timeout: TimeInterval = 5) async throws {
        let once = Once()
        let c = conn
        let q = queue
        let name = "\(host):\(port)"
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            c.stateUpdateHandler = { [weak self] state in
                switch state {
                case .ready:
                    once.run { cont.resume() }
                case .failed(let e):
                    self?.closedFlag = true
                    once.run { cont.resume(throwing: e) }
                case .waiting(let e):
                    // z.B. Verbindung abgelehnt / Netz nicht erreichbar
                    once.run { c.cancel(); cont.resume(throwing: e) }
                case .cancelled:
                    self?.closedFlag = true
                    once.run { cont.resume(throwing: NetError.closed) }
                default:
                    break
                }
            }
            c.start(queue: q)
            q.asyncAfter(deadline: .now() + timeout) {
                once.run { c.cancel(); cont.resume(throwing: NetError.timeout("Verbindung zu \(name)")) }
            }
        }
        queue.async { self.receiveLoop() }
    }

    private func receiveLoop() {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, complete, error in
            guard let self = self else { return }
            if let data = data, !data.isEmpty { self.buffer.append(data) }
            if complete || error != nil {
                self.closedFlag = true
                return
            }
            self.receiveLoop()
        }
    }

    func send(_ data: Data) async throws {
        let c = conn
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            c.send(content: data, completion: .contentProcessed { err in
                if let err = err { cont.resume(throwing: err) } else { cont.resume() }
            })
        }
    }

    func send(_ text: String, encoding: String.Encoding = .ascii) async throws {
        let d = text.data(using: encoding) ?? Data(text.utf8)
        try await send(d)
    }

    /// Alles, was im Puffer liegt, entnehmen.
    func takeAll() -> Data {
        queue.sync {
            let d = buffer
            buffer.removeAll()
            return d
        }
    }

    /// Puffer leeren (z.B. vor einem neuen Befehl).
    func clear() { _ = takeAll() }

    /// Liest bis einschliesslich Trennzeichen (z.B. "\r"). Rueckgabe ohne Trennzeichen.
    func readUntil(_ delim: Data, timeout: TimeInterval = 3) async throws -> Data {
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            let res: (Data?, Bool) = queue.sync {
                if let r = buffer.range(of: delim) {
                    let line = buffer.subdata(in: buffer.startIndex..<r.lowerBound)
                    buffer.removeSubrange(buffer.startIndex..<r.upperBound)
                    return (line, false)
                }
                return (nil, closedFlag)
            }
            if let line = res.0 { return line }
            if res.1 { throw NetError.closed }
            if Date() > deadline { throw NetError.timeout("Antwort von \(host)") }
            try await Task.sleep(nanoseconds: 15_000_000)
        }
    }

    func readLine(timeout: TimeInterval = 3, delimiter: String = "\r") async throws -> String {
        let d = try await readUntil(Data(delimiter.utf8), timeout: timeout)
        return String(decoding: d, as: UTF8.self)
    }

    /// Liest genau n Bytes.
    func read(count n: Int, timeout: TimeInterval = 3) async throws -> Data {
        let deadline = Date().addingTimeInterval(timeout)
        while true {
            let res: (Data?, Bool) = queue.sync {
                if buffer.count >= n {
                    let d = buffer.prefix(n)
                    buffer.removeFirst(n)
                    return (Data(d), false)
                }
                return (nil, closedFlag)
            }
            if let d = res.0 { return d }
            if res.1 { throw NetError.closed }
            if Date() > deadline { throw NetError.timeout("Antwort von \(host)") }
            try await Task.sleep(nanoseconds: 15_000_000)
        }
    }

    /// Wartet bis zu `wait` Sekunden auf Daten und liefert, was gekommen ist (auch leer).
    func readAvailable(wait: TimeInterval = 0.5, settle: TimeInterval = 0.08) async -> Data {
        let deadline = Date().addingTimeInterval(wait)
        var lastCount = 0
        var stableSince = Date()
        while Date() < deadline {
            let n = queue.sync { buffer.count }
            if n != lastCount { lastCount = n; stableSince = Date() }
            if n > 0 && Date().timeIntervalSince(stableSince) >= settle { break }
            try? await Task.sleep(nanoseconds: 15_000_000)
        }
        return takeAll()
    }

    func close() {
        conn.cancel()
        queue.async { self.closedFlag = true }
    }

    /// Prueft nur, ob ein TCP-Port offen ist.
    static func probe(host: String, port: UInt16, timeout: TimeInterval = 2) async -> Bool {
        guard let c = try? TCPConnection(host: host, port: port) else { return false }
        do {
            try await c.connect(timeout: timeout)
            c.close()
            return true
        } catch {
            c.close()
            return false
        }
    }
}

// ---------------------------------------------------------------------------
// UDP
// ---------------------------------------------------------------------------
enum UDPExchange {
    /// Sendet ein Datagramm und wartet auf die erste Antwort.
    static func request(host: String, port: UInt16, payload: Data, timeout: TimeInterval = 2,
                        retries: Int = 1) async throws -> Data {
        var lastErr: Error = NetError.timeout("UDP \(host):\(port)")
        for _ in 0...max(0, retries) {
            do {
                return try await once(host: host, port: port, payload: payload, timeout: timeout)
            } catch {
                lastErr = error
            }
        }
        throw lastErr
    }

    private static func once(host: String, port: UInt16, payload: Data, timeout: TimeInterval) async throws -> Data {
        guard let p = NWEndpoint.Port(rawValue: port), !host.isEmpty else { throw NetError.badAddress("\(host):\(port)") }
        let conn = NWConnection(host: NWEndpoint.Host(host), port: p, using: .udp)
        let q = DispatchQueue(label: "udp.\(host)")
        let once = Once()
        defer { conn.cancel() }
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Data, Error>) in
            conn.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    conn.send(content: payload, completion: .contentProcessed { err in
                        if let err = err { once.run { cont.resume(throwing: err) }; return }
                        conn.receiveMessage { data, _, _, error in
                            if let error = error { once.run { cont.resume(throwing: error) }; return }
                            once.run { cont.resume(returning: data ?? Data()) }
                        }
                    })
                case .failed(let e):
                    once.run { cont.resume(throwing: e) }
                default:
                    break
                }
            }
            conn.start(queue: q)
            q.asyncAfter(deadline: .now() + timeout) {
                once.run { cont.resume(throwing: NetError.timeout("UDP \(host):\(port)")) }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------
final class HTTPClient: NSObject, URLSessionTaskDelegate, URLSessionDataDelegate {
    var user: String?
    var password: String?
    /// Selbstsignierte Zertifikate (ClickShare, Drucker, Router) akzeptieren
    var allowInsecure = true
    /// Weiterleitungen folgen
    var followRedirects = true
    private(set) var authFailures = 0

    lazy var session: URLSession = {
        let cfg = URLSessionConfiguration.ephemeral     // eigene Cookies, nichts auf Platte
        cfg.timeoutIntervalForRequest = 10
        cfg.timeoutIntervalForResource = 60
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        cfg.httpShouldSetCookies = true
        cfg.httpCookieAcceptPolicy = .always
        return URLSession(configuration: cfg, delegate: self, delegateQueue: nil)
    }()

    init(user: String? = nil, password: String? = nil) {
        self.user = user
        self.password = password
    }

    func cookies(for url: URL) -> [HTTPCookie] {
        session.configuration.httpCookieStorage?.cookies(for: url) ?? []
    }

    func setCookie(name: String, value: String, url: URL) {
        let props: [HTTPCookiePropertyKey: Any] = [.name: name, .value: value, .domain: url.host ?? "", .path: "/"]
        if let c = HTTPCookie(properties: props) {
            session.configuration.httpCookieStorage?.setCookie(c)
        }
    }

    @discardableResult
    func request(_ method: String, _ url: URL, headers: [String: String] = [:], body: Data? = nil,
                 timeout: TimeInterval = 8) async throws -> (Data, HTTPURLResponse) {
        var req = URLRequest(url: url, timeoutInterval: timeout)
        req.httpMethod = method
        for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
        req.httpBody = body
        authFailures = 0
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw NetError.protocolError("keine HTTP-Antwort") }
        return (data, http)
    }

    func getText(_ url: URL, headers: [String: String] = [:], timeout: TimeInterval = 8) async throws -> String {
        let (d, r) = try await request("GET", url, headers: headers, timeout: timeout)
        guard (200..<300).contains(r.statusCode) else {
            throw NetError.http(r.statusCode, HTTPURLResponse.localizedString(forStatusCode: r.statusCode))
        }
        return String(decoding: d, as: UTF8.self)
    }

    func getJSON(_ url: URL, headers: [String: String] = [:], timeout: TimeInterval = 8) async throws -> Any {
        var h = headers
        if h["Accept"] == nil { h["Accept"] = "application/json" }
        let (d, r) = try await request("GET", url, headers: h, timeout: timeout)
        guard (200..<300).contains(r.statusCode) else {
            throw NetError.http(r.statusCode, String(decoding: d.prefix(200), as: UTF8.self))
        }
        return try JSONSerialization.jsonObject(with: d, options: [.fragmentsAllowed])
    }

    // Zertifikate + Anmeldung (Basic/Digest/NTLM werden von URLSession erledigt)
    func urlSession(_ session: URLSession, task: URLSessionTask, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        let method = challenge.protectionSpace.authenticationMethod
        if method == NSURLAuthenticationMethodServerTrust {
            if allowInsecure, let trust = challenge.protectionSpace.serverTrust {
                completionHandler(.useCredential, URLCredential(trust: trust))
            } else {
                completionHandler(.performDefaultHandling, nil)
            }
            return
        }
        if method == NSURLAuthenticationMethodHTTPBasic || method == NSURLAuthenticationMethodHTTPDigest
            || method == NSURLAuthenticationMethodNTLM {
            if challenge.previousFailureCount < 1, let u = user, let p = password {
                completionHandler(.useCredential, URLCredential(user: u, password: p, persistence: .forSession))
            } else {
                authFailures += 1
                completionHandler(.rejectProtectionSpace, nil)
            }
            return
        }
        completionHandler(.performDefaultHandling, nil)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(followRedirects ? request : nil)
    }
}

// ---------------------------------------------------------------------------
// Hilfen
// ---------------------------------------------------------------------------
extension Data {
    var hex: String { map { String(format: "%02x", $0) }.joined() }

    init?(hex: String) {
        let s = hex.filter { !$0.isWhitespace }
        guard s.count % 2 == 0 else { return nil }
        var d = Data(capacity: s.count / 2)
        var i = s.startIndex
        while i < s.endIndex {
            let j = s.index(i, offsetBy: 2)
            guard let b = UInt8(s[i..<j], radix: 16) else { return nil }
            d.append(b)
            i = j
        }
        self = d
    }

    var latin1: String { String(data: self, encoding: .isoLatin1) ?? "" }
}

extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
    var latin1Data: Data { data(using: .isoLatin1) ?? Data(utf8) }
}

/// Basis-URL aus Eingabe ("192.168.0.10", "http://x", "x:8080") bauen.
func makeURL(_ hostOrURL: String, scheme: String = "http", port: Int? = nil, path: String = "") -> URL? {
    var h = hostOrURL.trimmed
    if h.isEmpty { return nil }
    var sch = scheme
    if let r = h.range(of: "://") {
        sch = String(h[h.startIndex..<r.lowerBound])
        h = String(h[r.upperBound...])
    }
    while h.hasSuffix("/") { h.removeLast() }
    var s = "\(sch)://\(h)"
    if let p = port, !h.contains(":") { s += ":\(p)" }
    if !path.isEmpty { s += path.hasPrefix("/") ? path : "/" + path }
    return URL(string: s)
}

/// Kurze Pause ohne Fehler bei Abbruch.
func pause(_ seconds: Double) async {
    try? await Task.sleep(nanoseconds: UInt64(max(0, seconds) * 1_000_000_000))
}
