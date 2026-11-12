// ===========================================================================
//  Speedtest.swift - Studio Control iOS - Internet-Geschwindigkeit (Cloudflare)
//  Autor: T. Pfeiffer
//
//  Messkern wie SpeedTestEngine in sc.py:
//    - speed.cloudflare.com (naechster Standort per Anycast)
//    - /meta (Standort, Anbieter), Ersatz /cdn-cgi/trace
//    - Leerlauf-Latenz: 21 Anfragen /__down?bytes=0 ueber EINE Verbindung,
//      erste verworfen, Server-Timing (dur=) abgezogen -> Median, Minimum, Jitter
//    - Download /__down?bytes=25000000 und Upload POST /__up (25 MB je Anfrage)
//      ueber N parallele Verbindungen (je Strom eine eigene URLSession, damit
//      HTTP/2 nicht alles in eine Verbindung buendelt)
//    - Anlaufphase (2 s) wird ausgeblendet, Messung danach "duration" Sekunden
//    - Latenz unter Last alle 0,25 s, Spitze + 90%-Wert aus 100-ms-Proben
//  Ookla CLI gibt es auf dem iPhone nicht (keine EXE) -> nur Cloudflare.
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen + Datentypen
// ---------------------------------------------------------------------------
struct SpeedtestSettings: Codable {
    var base: String = "https://speed.cloudflare.com"
    var streams: Int = 8
    var duration: Int = 15

    init() {}

    enum CodingKeys: String, CodingKey {
        case base, streams, duration
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        base = try c.decodeIfPresent(String.self, forKey: .base) ?? "https://speed.cloudflare.com"
        streams = try c.decodeIfPresent(Int.self, forKey: .streams) ?? 8
        duration = try c.decodeIfPresent(Int.self, forKey: .duration) ?? 15
    }
}

struct SpeedtestSample: Hashable {
    let t: Double
    let mbit: Double
}

struct SpeedtestResult: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var time: String = ""
    var engine: String = "Cloudflare"
    var server: String = ""
    var isp: String = ""
    var ip: String = ""
    var ping: Double?
    var pingMin: Double?
    var jitter: Double?
    var down: Double?
    var downPeak: Double?
    var downP90: Double?
    var pingDown: Double?
    var up: Double?
    var upPeak: Double?
    var upP90: Double?
    var pingUp: Double?
    var notes: [String] = []

    init() {}

    enum CodingKeys: String, CodingKey {
        case id, time, engine, server, isp, ip, ping, pingMin, jitter
        case down, downPeak, downP90, pingDown, up, upPeak, upP90, pingUp, notes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        time = try c.decodeIfPresent(String.self, forKey: .time) ?? ""
        engine = try c.decodeIfPresent(String.self, forKey: .engine) ?? "Cloudflare"
        server = try c.decodeIfPresent(String.self, forKey: .server) ?? ""
        isp = try c.decodeIfPresent(String.self, forKey: .isp) ?? ""
        ip = try c.decodeIfPresent(String.self, forKey: .ip) ?? ""
        ping = try c.decodeIfPresent(Double.self, forKey: .ping)
        pingMin = try c.decodeIfPresent(Double.self, forKey: .pingMin)
        jitter = try c.decodeIfPresent(Double.self, forKey: .jitter)
        down = try c.decodeIfPresent(Double.self, forKey: .down)
        downPeak = try c.decodeIfPresent(Double.self, forKey: .downPeak)
        downP90 = try c.decodeIfPresent(Double.self, forKey: .downP90)
        pingDown = try c.decodeIfPresent(Double.self, forKey: .pingDown)
        up = try c.decodeIfPresent(Double.self, forKey: .up)
        upPeak = try c.decodeIfPresent(Double.self, forKey: .upPeak)
        upP90 = try c.decodeIfPresent(Double.self, forKey: .upP90)
        pingUp = try c.decodeIfPresent(Double.self, forKey: .pingUp)
        notes = try c.decodeIfPresent([String].self, forKey: .notes) ?? []
    }

    /// "Ping Last" der Verlaufstabelle = groesster Wert aus Download/Upload
    var pingLoaded: Double? {
        let pl = [pingDown, pingUp].compactMap { $0 }
        return pl.max()
    }
}

/// Formatierung wie st_fmt_rate / f1 in sc.py
enum SpeedtestFmt {
    static func rate(_ mbit: Double?) -> String {
        guard let m = mbit else { return "-" }
        if m >= 1000 { return String(format: "%.2f Gbit/s", m / 1000.0) }
        if m >= 100 { return String(format: "%.0f Mbit/s", m) }
        return String(format: "%.1f Mbit/s", m)
    }

    static func num(_ v: Double?) -> String {
        guard let x = v else { return "-" }
        return x >= 100 ? String(format: "%.0f", x) : String(format: "%.1f", x)
    }

    static func ms(_ v: Double?) -> String {
        guard let x = v else { return "-" }
        return String(format: "%.1f", x)
    }

    static func median(_ a: [Double]) -> Double? {
        if a.isEmpty { return nil }
        let s = a.sorted()
        let n = s.count
        if n % 2 == 1 { return s[n / 2] }
        return (s[n / 2 - 1] + s[n / 2]) / 2.0
    }
}

// ---------------------------------------------------------------------------
// Thread-sichere Hilfen fuer die Messung
// ---------------------------------------------------------------------------
final class SpeedtestCounter {
    private let lock = NSLock()
    private var bytes: Int64 = 0
    private var stopped = false
    private var errs: [String] = []

    func add(_ n: Int64) {
        lock.lock()
        if !stopped { bytes += n }
        lock.unlock()
    }

    var total: Int64 {
        lock.lock()
        defer { lock.unlock() }
        return bytes
    }

    func stop() {
        lock.lock()
        stopped = true
        lock.unlock()
    }

    var isStopped: Bool {
        lock.lock()
        defer { lock.unlock() }
        return stopped
    }

    func addError(_ e: String) {
        lock.lock()
        if !stopped && errs.count < 50 { errs.append(e) }
        lock.unlock()
    }

    var errors: [String] {
        lock.lock()
        defer { lock.unlock() }
        return errs
    }
}

final class SpeedtestValueList {
    private let lock = NSLock()
    private var items: [Double] = []

    func append(_ v: Double) {
        lock.lock()
        items.append(v)
        lock.unlock()
    }

    var all: [Double] {
        lock.lock()
        defer { lock.unlock() }
        return items
    }
}

/// Ein Download- oder Upload-Strom mit eigener URLSession (= eigene Verbindung).
final class SpeedtestStream: NSObject, URLSessionDataDelegate {
    private let url: URL
    private let upload: Bool
    private let payload: Data
    private let headers: [String: String]
    private let counter: SpeedtestCounter
    private let lock = NSLock()
    private var invalidated = false
    private var session: URLSession?

    init(url: URL, upload: Bool, payload: Data, headers: [String: String], counter: SpeedtestCounter) {
        self.url = url
        self.upload = upload
        self.payload = payload
        self.headers = headers
        self.counter = counter
        super.init()
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 10
        cfg.timeoutIntervalForResource = 3600
        cfg.urlCache = nil
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        cfg.httpMaximumConnectionsPerHost = 1
        let q = OperationQueue()
        q.maxConcurrentOperationCount = 1
        session = URLSession(configuration: cfg, delegate: self, delegateQueue: q)
    }

    func start() {
        lock.lock()
        defer { lock.unlock() }
        guard !invalidated, !counter.isStopped, let s = session else { return }
        var req = URLRequest(url: url)
        for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
        if upload {
            req.httpMethod = "POST"
            req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
            s.uploadTask(with: req, from: payload).resume()
        } else {
            req.httpMethod = "GET"
            s.dataTask(with: req).resume()
        }
    }

    func stop() {
        lock.lock()
        invalidated = true
        let s = session
        session = nil
        lock.unlock()
        s?.invalidateAndCancel()
    }

    // Antwortkopf: Download nur bei HTTP 200 weiterlesen
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        if let h = response as? HTTPURLResponse {
            if !upload && h.statusCode != 200 {
                counter.addError("HTTP \(h.statusCode)")
                completionHandler(.cancel)
                return
            }
            if upload && h.statusCode >= 400 {
                counter.addError("HTTP \(h.statusCode)")
            }
        }
        completionHandler(.allow)
    }

    // Download: empfangene Nutzdaten zaehlen
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        if !upload { counter.add(Int64(data.count)) }
    }

    // Upload: gesendete Bytes zaehlen
    func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64,
                    totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        if upload { counter.add(bytesSent) }
    }

    // Anfrage fertig -> naechste Anfrage auf diesem Strom
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if counter.isStopped { return }
        var delay = 0.0
        if let e = error {
            let ns = e as NSError
            if ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled {
                delay = 0.5          // nach HTTP-Fehler abgebrochen
            } else {
                counter.addError(e.localizedDescription)
                delay = 0.3
            }
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + delay) { [weak self] in
            self?.start()
        }
    }
}

// ---------------------------------------------------------------------------
// Messkern
// ---------------------------------------------------------------------------
struct SpeedtestPhaseResult {
    var mbit: Double?
    var peak: Double?
    var p90: Double?
    var loadedMs: Double?
    var errors: [String] = []
}

final class SpeedtestEngine {
    static let defaultBase = "https://speed.cloudflare.com"
    static let downChunk = 25 * 1000 * 1000
    static let upChunk = 25 * 1000 * 1000
    static let bufSize = 256 * 1024

    let baseString: String
    let host: String
    let streams: Int
    let duration: Double
    let warmup: Double = 2.0

    var onSample: ((String, Double, Double) -> Void)?
    var onPhase: ((String) -> Void)?

    private let lock = NSLock()
    private var cancelled = false
    private var activeStreams: [SpeedtestStream] = []
    private var activeCounter: SpeedtestCounter?
    private var sessions: [URLSession] = []

    init(base: String, streams: Int, duration: Double) {
        var b = base.trimmed
        while b.hasSuffix("/") { b.removeLast() }
        if b.isEmpty { b = SpeedtestEngine.defaultBase }
        if !b.contains("://") { b = "https://" + b }
        baseString = b
        host = URL(string: b)?.host ?? "speed.cloudflare.com"
        self.streams = max(1, streams)
        self.duration = max(4.0, duration)
    }

    var isCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }

    func cancel() {
        lock.lock()
        cancelled = true
        let st = activeStreams
        let ctr = activeCounter
        let ss = sessions
        lock.unlock()
        ctr?.stop()
        for s in st { s.stop() }
        for s in ss { s.invalidateAndCancel() }
    }

    // ---- Hilfen ----
    private var headers: [String: String] {
        ["User-Agent": "StudioControlApp-Speedtest/\(APP_VERSION)",
         "Accept": "*/*",
         "Referer": "https://speed.cloudflare.com/"]
    }

    private func url(_ path: String) -> URL? {
        URL(string: baseString + path)
    }

    private func request(_ path: String) throws -> URLRequest {
        guard let u = url(path) else { throw NetError.badAddress(baseString + path) }
        var r = URLRequest(url: u)
        r.httpMethod = "GET"
        for (k, v) in headers { r.setValue(v, forHTTPHeaderField: k) }
        return r
    }

    /// Eigene URLSession (eine gehaltene Verbindung), wird bei cancel() beendet.
    private func makeSession(timeout: Double) -> URLSession {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = timeout
        cfg.timeoutIntervalForResource = 120
        cfg.urlCache = nil
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        cfg.httpMaximumConnectionsPerHost = 1
        let s = URLSession(configuration: cfg)
        lock.lock()
        sessions.append(s)
        lock.unlock()
        return s
    }

    private func dropSession(_ s: URLSession) {
        s.invalidateAndCancel()
        lock.lock()
        sessions.removeAll { $0 === s }
        lock.unlock()
    }

    static func now() -> Double {
        Double(DispatchTime.now().uptimeNanoseconds) / 1_000_000_000.0
    }

    /// Serverzeit aus "Server-Timing: cfRequestDuration;dur=1.23" (ms) - wird abgezogen.
    static func serverMs(_ resp: URLResponse) -> Double {
        guard let h = resp as? HTTPURLResponse,
              let st = h.value(forHTTPHeaderField: "Server-Timing"),
              let r = st.range(of: "dur=") else { return 0 }
        var num = ""
        for ch in st[r.upperBound...] {
            if ch.isASCII && (ch.isNumber || ch == ".") { num.append(ch) } else { break }
        }
        return Double(num) ?? 0
    }

    private static func str(_ v: Any?) -> String {
        if let s = v as? String { return s }
        if let n = v as? NSNumber { return n.stringValue }
        return ""
    }

    // ---- Standort / Server ----
    func meta() async -> [String: String] {
        var info: [String: String] = [:]
        let s = makeSession(timeout: 6)
        defer { dropSession(s) }
        do {
            let (d, r) = try await s.data(for: try request("/meta"))
            if (r as? HTTPURLResponse)?.statusCode == 200,
               let obj = try JSONSerialization.jsonObject(with: d) as? [String: Any] {
                info["ip"] = SpeedtestEngine.str(obj["clientIp"])
                info["isp"] = SpeedtestEngine.str(obj["asOrganization"])
                info["asn"] = SpeedtestEngine.str(obj["asn"])
                info["country"] = SpeedtestEngine.str(obj["country"])
                var city = SpeedtestEngine.str(obj["city"])
                // "colo" kann ein Objekt {"iata":..,"city":..} oder ein Text sein
                if let colo = obj["colo"] as? [String: Any] {
                    info["colo"] = SpeedtestEngine.str(colo["iata"])
                    let cc = SpeedtestEngine.str(colo["city"])
                    if !cc.isEmpty { city = cc }
                } else {
                    info["colo"] = SpeedtestEngine.str(obj["colo"])
                }
                info["city"] = city
            }
        } catch {
            // weiter mit /cdn-cgi/trace
        }
        if (info["colo"] ?? "").isEmpty && !isCancelled {
            do {
                let (d, _) = try await s.data(for: try request("/cdn-cgi/trace"))
                let txt = String(decoding: d, as: UTF8.self)
                var kv: [String: String] = [:]
                for line in txt.components(separatedBy: "\n") {
                    if let eq = line.firstIndex(of: "=") {
                        kv[String(line[line.startIndex..<eq])] = String(line[line.index(after: eq)...]).trimmed
                    }
                }
                info["ip"] = kv["ip"] ?? (info["ip"] ?? "")
                info["colo"] = kv["colo"] ?? ""
                info["country"] = kv["loc"] ?? (info["country"] ?? "")
            } catch {
                // ohne Standort weiter
            }
        }
        return info
    }

    // ---- Latenz im Leerlauf ----
    func latency(_ count: Int = 20) async throws -> [Double] {
        var out: [Double] = []
        let s = makeSession(timeout: 6)
        defer { dropSession(s) }
        for i in 0...count {
            if isCancelled { break }
            let req = try request("/__down?bytes=0")
            let t0 = SpeedtestEngine.now()
            let (_, r) = try await s.data(for: req)
            let rtt = (SpeedtestEngine.now() - t0) * 1000.0 - SpeedtestEngine.serverMs(r)
            if i > 0 { out.append(max(0, rtt)) }       // erste Anfrage = Verbindungsaufbau
            await pause(0.05)
        }
        return out
    }

    // ---- Latenz unter Last ----
    private func probeLoop(_ counter: SpeedtestCounter, _ list: SpeedtestValueList, _ s: URLSession) async {
        var first = true
        while !counter.isStopped {
            do {
                let req = try request("/__down?bytes=0")
                let t0 = SpeedtestEngine.now()
                let (_, r) = try await s.data(for: req)
                let rtt = (SpeedtestEngine.now() - t0) * 1000.0 - SpeedtestEngine.serverMs(r)
                if !first { list.append(max(0, rtt)) }
                first = false
            } catch {
                return
            }
            await pause(0.25)
        }
    }

    /// Nicht komprimierbare Nutzlast: 256 KB Zufall, wiederholt bis 25 MB
    static func makePayload() -> Data {
        var chunk = [UInt8](repeating: 0, count: bufSize)
        var g = SystemRandomNumberGenerator()
        var i = 0
        while i < chunk.count {
            var r = g.next()
            var k = 0
            while k < 8 && i < chunk.count {
                chunk[i] = UInt8(truncatingIfNeeded: r)
                r >>= 8
                i += 1
                k += 1
            }
        }
        var d = Data(capacity: upChunk)
        while d.count < upChunk {
            let n = min(chunk.count, upChunk - d.count)
            d.append(contentsOf: chunk[0..<n])
        }
        return d
    }

    // ---- Durchsatz ----
    func throughput(_ phase: String) async -> SpeedtestPhaseResult {
        let upload = (phase == "up")
        let counter = SpeedtestCounter()
        let payload = upload ? SpeedtestEngine.makePayload() : Data()
        let path = upload ? "/__up" : "/__down?bytes=\(SpeedtestEngine.downChunk)"
        guard let u = url(path) else {
            return SpeedtestPhaseResult(errors: ["Ungueltige Adresse"])
        }
        var workers: [SpeedtestStream] = []
        for _ in 0..<streams {
            workers.append(SpeedtestStream(url: u, upload: upload, payload: payload, headers: headers, counter: counter))
        }
        let probeSession = makeSession(timeout: 6)
        lock.lock()
        activeStreams = workers
        activeCounter = counter
        let wasCancelled = cancelled
        lock.unlock()
        if wasCancelled { counter.stop() }

        let loaded = SpeedtestValueList()
        let tStart = SpeedtestEngine.now()
        for w in workers { w.start() }
        let probe = Task { await self.probeLoop(counter, loaded, probeSession) }

        var samples: [SpeedtestSample] = []
        var lastT = tStart
        var lastB: Int64 = 0
        var baseT: Double?
        var baseB: Int64 = 0
        while !counter.isStopped {
            await pause(0.1)
            if isCancelled { break }
            let now = SpeedtestEngine.now()
            let tot = counter.total
            let dt = now - lastT
            if dt > 0 {
                let mbit = Double(tot - lastB) * 8.0 / dt / 1e6
                samples.append(SpeedtestSample(t: now - tStart, mbit: mbit))
                onSample?(phase, now - tStart, mbit)
            }
            lastT = now
            lastB = tot
            let el = now - tStart
            if baseT == nil && el >= warmup {
                baseT = now                       // Ende der Anlaufphase
                baseB = tot
            }
            if el >= duration + warmup { break }
        }
        let endT = SpeedtestEngine.now()
        let endB = counter.total
        let errors = counter.errors
        counter.stop()
        for w in workers { w.stop() }
        dropSession(probeSession)
        _ = await probe.value
        lock.lock()
        activeStreams = []
        activeCounter = nil
        lock.unlock()

        var res = SpeedtestPhaseResult()
        res.errors = errors
        guard let bt = baseT, endT - bt > 0.5 else { return res }
        let steady = samples.filter { $0.t >= warmup }.map { $0.mbit }
        if steady.count >= 5 {
            let srt = steady.sorted()
            res.p90 = srt[Int(0.9 * Double(srt.count - 1))]
        }
        res.mbit = Double(endB - baseB) * 8.0 / (endT - bt) / 1e6
        res.peak = steady.max()
        res.loadedMs = SpeedtestFmt.median(loaded.all)
        return res
    }

    // ---- Gesamtablauf ----
    func run() async throws -> SpeedtestResult? {
        var res = SpeedtestResult()
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        res.time = f.string(from: Date())
        res.engine = "Cloudflare"

        onPhase?("Server ermitteln ...")
        let m = await meta()
        if isCancelled { return nil }
        let srv = "\(m["colo"] ?? "") \(m["city"] ?? "")".trimmed
        res.server = srv.isEmpty ? host : srv
        res.isp = m["isp"] ?? ""
        res.ip = m["ip"] ?? ""

        onPhase?("Latenz messen ...")
        let lat: [Double]
        do {
            lat = try await latency(20)
        } catch {
            if isCancelled { return nil }
            throw error
        }
        if isCancelled { return nil }
        if lat.isEmpty {
            throw NetError.protocolError("keine Latenzmessung möglich (Server nicht erreichbar?)")
        }
        res.ping = SpeedtestFmt.median(lat)
        res.pingMin = lat.min()
        if lat.count > 1 {
            var sum = 0.0
            for k in 1..<lat.count { sum += abs(lat[k] - lat[k - 1]) }
            res.jitter = sum / Double(lat.count - 1)
        } else {
            res.jitter = 0
        }

        onPhase?("Download (\(streams) Verbindungen) ...")
        let d = await throughput("down")
        if isCancelled { return nil }
        res.down = d.mbit
        res.downPeak = d.peak
        res.downP90 = d.p90
        res.pingDown = d.loadedMs

        onPhase?("Upload (\(streams) Verbindungen) ...")
        let u = await throughput("up")
        if isCancelled { return nil }
        res.up = u.mbit
        res.upPeak = u.peak
        res.upP90 = u.p90
        res.pingUp = u.loadedMs
        res.notes = Array(d.errors.prefix(3)) + Array(u.errors.prefix(3))
        return res
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
@MainActor
final class SpeedtestModel: DeviceModel {
    static let historyKey = "speedtest.history"
    static let historyCols = ["Zeit", "Messung", "Server", "Ping", "Jitter", "Download", "Upload",
                              "Ping Last", "Verlust"]

    @Published var settings = SpeedtestSettings()
    @Published var running = false
    @Published var phaseText = "Bereit"
    @Published var downSamples: [SpeedtestSample] = []
    @Published var upSamples: [SpeedtestSample] = []
    @Published var liveDown: Double?
    @Published var liveUp: Double?
    @Published var current: SpeedtestResult?
    @Published var history: [SpeedtestResult] = []
    @Published var csvURL: URL?

    private var engine: SpeedtestEngine?

    init() {
        super.init(id: "speedtest", title: "Speedtest", subtitle: "Internet-Geschwindigkeit",
                   symbol: "speedometer", tint: Color(hex: 0x32ADE6))
    }

    override var pollInterval: Double { 0 }
    override var isConfigured: Bool { true }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(SpeedtestSettings.self, "speedtest") {
            settings = s
        }
        loadHistory()
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "speedtest")
    }

    override func refresh() async {
        await refreshSafely {
            updateSummary()
        }
    }

    override func disconnect() {
        // App geht in den Hintergrund -> laufende Messung waere ohnehin verfaelscht
        if running { cancel() }
    }

    private func updateSummary() {
        if running {
            summary = phaseText
        } else if let r = current ?? history.first {
            summary = "↓ \(SpeedtestFmt.rate(r.down))  ↑ \(SpeedtestFmt.rate(r.up))"
        } else {
            summary = "Noch keine Messung"
        }
    }

    // ---- Ablauf ----
    func start() {
        guard !running else { return }
        running = true
        downSamples = []
        upSamples = []
        liveDown = nil
        liveUp = nil
        current = nil
        lastError = nil
        phaseText = "Start ..."
        let s = settings
        let eng = SpeedtestEngine(base: s.base,
                                  streams: max(1, min(32, s.streams)),
                                  duration: Double(max(5, min(60, s.duration))))
        eng.onSample = { [weak self] phase, t, mbit in
            Task { @MainActor in
                self?.addSample(phase, t, mbit)
            }
        }
        eng.onPhase = { [weak self] text in
            Task { @MainActor in
                self?.phaseText = text
                self?.updateSummary()
            }
        }
        engine = eng
        addLog("Messung gestartet (\(eng.streams) Verbindungen, \(Int(eng.duration)) s je Richtung)")
        updateSummary()
        Task { [weak self] in
            do {
                let r = try await eng.run()
                self?.finish(r, nil)
            } catch {
                self?.finish(nil, error)
            }
        }
    }

    func cancel() {
        engine?.cancel()
        phaseText = "Abgebrochen"
    }

    private func addSample(_ phase: String, _ t: Double, _ mbit: Double) {
        guard running else { return }
        if phase == "down" {
            downSamples.append(SpeedtestSample(t: t, mbit: mbit))
            liveDown = mbit
        } else {
            upSamples.append(SpeedtestSample(t: t, mbit: mbit))
            liveUp = mbit
        }
    }

    private func finish(_ r: SpeedtestResult?, _ err: Error?) {
        running = false
        engine = nil
        if let e = err {
            let msg = DeviceModel.describe(e)
            phaseText = "Fehler"
            lastError = msg
            addLog("Messung fehlgeschlagen: \(msg)", error: true)
            Haptics.error()
            updateSummary()
            return
        }
        guard let res = r else {
            phaseText = "Abgebrochen"
            addLog("Messung abgebrochen.")
            updateSummary()
            return
        }
        current = res
        history.insert(res, at: 0)
        if history.count > 200 { history.removeLast(history.count - 200) }
        saveHistory()
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        phaseText = "Fertig \(f.string(from: Date()))"
        addLog("Ergebnis: Down \(SpeedtestFmt.rate(res.down)), Up \(SpeedtestFmt.rate(res.up)), Ping \(SpeedtestFmt.ms(res.ping)) ms, Jitter \(SpeedtestFmt.ms(res.jitter)) ms")
        Haptics.success()
        updateSummary()
    }

    // ---- Anzeige ----
    var shown: SpeedtestResult? { current ?? (running ? nil : history.first) }

    var downText: String { running ? SpeedtestFmt.num(liveDown) : SpeedtestFmt.num(shown?.down) }
    var upText: String { running ? SpeedtestFmt.num(liveUp) : SpeedtestFmt.num(shown?.up) }
    var pingText: String { running ? "-" : SpeedtestFmt.ms(shown?.ping) }
    var jitterText: String { running ? "-" : SpeedtestFmt.ms(shown?.jitter) }

    /// Detailzeilen wie detail_var in sc.py
    var detailLines: [String] {
        guard let r = shown else { return ["Noch keine Messung."] }
        var parts: [String] = ["\(r.engine), Server \(r.server.isEmpty ? "-" : r.server)"]
        if !r.isp.isEmpty { parts.append("Anbieter \(r.isp)") }
        if !r.ip.isEmpty { parts.append("Öffentliche IP \(r.ip)") }
        if r.pingDown != nil || r.pingUp != nil {
            let a = r.pingDown.map { String(format: "%.0f", $0) } ?? "-"
            let b = r.pingUp.map { String(format: "%.0f", $0) } ?? "-"
            parts.append("Ping unter Last: Download \(a) ms / Upload \(b) ms")
        }
        if r.downP90 != nil {
            parts.append("90%-Wert: Down \(SpeedtestFmt.rate(r.downP90)) / Up \(SpeedtestFmt.rate(r.upP90))")
            parts.append("Spitze: Down \(SpeedtestFmt.rate(r.downPeak)) / Up \(SpeedtestFmt.rate(r.upPeak))")
        }
        if let pm = r.pingMin { parts.append(String(format: "Ping minimal %.1f ms", pm)) }
        if !r.notes.isEmpty { parts.append("Hinweise: " + r.notes.prefix(3).joined(separator: "; ")) }
        parts.append("Gemessen \(r.time)")
        return parts
    }

    var averageText: String {
        let last = history.prefix(20)
        let downs = last.compactMap { $0.down }
        let ups = last.compactMap { $0.up }
        if downs.isEmpty { return "" }
        let d = downs.reduce(0, +) / Double(downs.count)
        let upTxt = ups.isEmpty ? "-" : SpeedtestFmt.rate(ups.reduce(0, +) / Double(ups.count))
        return "Mittel der letzten \(downs.count): Down \(SpeedtestFmt.rate(d)), Up \(upTxt)"
    }

    // ---- Verlauf ----
    private func loadHistory() {
        if let d = UserDefaults.standard.data(forKey: SpeedtestModel.historyKey),
           let h = try? JSONDecoder().decode([SpeedtestResult].self, from: d) {
            history = Array(h.prefix(200))
        }
        writeCSV()
    }

    private func saveHistory() {
        if let d = try? JSONEncoder().encode(history) {
            UserDefaults.standard.set(d, forKey: SpeedtestModel.historyKey)
        }
        writeCSV()
    }

    func clearHistory() {
        history.removeAll()
        current = nil
        UserDefaults.standard.removeObject(forKey: SpeedtestModel.historyKey)
        writeCSV()
        addLog("Verlauf gelöscht")
        updateSummary()
    }

    func deleteHistory(at offsets: IndexSet) {
        history.remove(atOffsets: offsets)
        saveHistory()
    }

    static func csvRow(_ r: SpeedtestResult) -> [String] {
        func g(_ v: Double?, _ f: String) -> String { v.map { String(format: f, $0) } ?? "" }
        return [r.time, r.engine, r.server, g(r.ping, "%.1f"), g(r.jitter, "%.1f"),
                g(r.down, "%.1f"), g(r.up, "%.1f"), g(r.pingLoaded, "%.0f"), ""]
    }

    /// CSV (Semikolon, UTF-8 mit BOM, aelteste zuerst) in eine temporaere Datei fuer ShareLink
    private func writeCSV() {
        guard !history.isEmpty else {
            csvURL = nil
            return
        }
        var text = SpeedtestModel.historyCols.joined(separator: ";") + "\n"
        for r in history.reversed() {
            text += SpeedtestModel.csvRow(r).map { $0.replacingOccurrences(of: ";", with: ",") }
                .joined(separator: ";") + "\n"
        }
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd"
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("Speedtest_\(f.string(from: Date())).csv")
        var data = Data([0xEF, 0xBB, 0xBF])
        data.append(Data(text.utf8))
        do {
            try data.write(to: url, options: .atomic)
            csvURL = url
        } catch {
            csvURL = nil
            addLog("CSV nicht geschrieben: \(error.localizedDescription)", error: true)
        }
    }
}

// ---------------------------------------------------------------------------
// Live-Kurve (Download blau, Upload lila)
// ---------------------------------------------------------------------------
struct SpeedtestGraph: View {
    let down: [SpeedtestSample]
    let up: [SpeedtestSample]
    let duration: Double

    static let downColor = Color(hex: 0x0A84FF)
    static let upColor = Color(hex: 0xBF5AF2)

    var body: some View {
        Canvas { ctx, size in
            let w = max(200.0, size.width)
            let h = size.height
            let padL: CGFloat = 40
            let padB: CGFloat = 18
            let padT: CGFloat = 16
            let plotH = h - padB - padT

            // Skala ohne Anlaufphase (Upload: Sendepuffer-Scheinspitze abschneiden)
            let pts = down + up
            let steady = pts.filter { $0.t >= 1.0 }.map { $0.mbit }
            let basis = steady.isEmpty ? pts.map { $0.mbit } : steady
            let vmax = max(basis.max() ?? 0, 10.0) * 1.1
            var step = pow(10.0, floor(log10(vmax)))
            let top = ceil(vmax / step) * step
            if top / step < 3 { step = step / 2.0 }

            var i = 0
            while Double(i) * step <= top + 1e-9 {
                let v = Double(i) * step
                let y = h - padB - plotH * CGFloat(v / top)
                var line = Path()
                line.move(to: CGPoint(x: padL, y: y))
                line.addLine(to: CGPoint(x: w - 6, y: y))
                ctx.stroke(line, with: .color(Color.secondary.opacity(0.25)), lineWidth: 0.5)
                ctx.draw(Text(String(format: "%g", v)).font(.system(size: 9)).foregroundColor(.secondary),
                         at: CGPoint(x: padL - 5, y: y), anchor: .trailing)
                i += 1
            }

            let dur = duration + 2.0
            let total = dur * 2.0
            let series: [([SpeedtestSample], Color, Double)] = [
                (down, SpeedtestGraph.downColor, 0.0),
                (up, SpeedtestGraph.upColor, dur),
            ]
            for (seq, col, off) in series {
                if seq.count < 2 { continue }
                var p = Path()
                var firstPt = true
                for smp in seq {
                    let x = padL + (w - 6 - padL) * CGFloat(min(1.0, (smp.t + off) / total))
                    let y = h - padB - plotH * CGFloat(min(smp.mbit, top) / top)
                    if firstPt {
                        p.move(to: CGPoint(x: x, y: y))
                        firstPt = false
                    } else {
                        p.addLine(to: CGPoint(x: x, y: y))
                    }
                }
                ctx.stroke(p, with: .color(col), style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
            }

            ctx.draw(Text("Download").font(.system(size: 10, weight: .bold)).foregroundColor(SpeedtestGraph.downColor),
                     at: CGPoint(x: padL + 4, y: h - 2), anchor: .bottomLeading)
            ctx.draw(Text("Upload").font(.system(size: 10, weight: .bold)).foregroundColor(SpeedtestGraph.upColor),
                     at: CGPoint(x: padL + (w - padL) / 2.0, y: h - 2), anchor: .bottomLeading)
            ctx.draw(Text("Mbit/s").font(.system(size: 9)).foregroundColor(.secondary),
                     at: CGPoint(x: 2, y: 2), anchor: .topLeading)
        }
        .frame(height: 180)
    }
}

/// Grosse Ergebniszahl
struct SpeedtestValueTile: View {
    let title: String
    let value: String
    let unit: String
    let color: Color
    let symbol: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Label(title, systemImage: symbol)
                .font(.caption.weight(.semibold))
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(size: 30, weight: .bold, design: .rounded))
                .foregroundColor(color)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            Text(unit)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color(.tertiarySystemFill)))
    }
}

// ---------------------------------------------------------------------------
// Detailseite
// ---------------------------------------------------------------------------
struct SpeedtestView: View {
    @ObservedObject var model: SpeedtestModel
    @State private var confirmClear = false

    var body: some View {
        DevicePage(model: model, settings: { SpeedtestSettingsView(model: model) }) {
            resultSection
            graphSection
            controlSection
            historySection
        }
    }

    private var resultSection: some View {
        Section {
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                SpeedtestValueTile(title: "Download", value: model.downText, unit: "Mbit/s",
                                   color: SpeedtestGraph.downColor, symbol: "arrow.down.circle.fill")
                SpeedtestValueTile(title: "Upload", value: model.upText, unit: "Mbit/s",
                                   color: SpeedtestGraph.upColor, symbol: "arrow.up.circle.fill")
                SpeedtestValueTile(title: "Ping", value: model.pingText, unit: "ms",
                                   color: Color(hex: 0x30D158), symbol: "timer")
                SpeedtestValueTile(title: "Jitter", value: model.jitterText, unit: "ms",
                                   color: Color(hex: 0xFF9F0A), symbol: "waveform.path.ecg")
            }
            .padding(.vertical, 4)
            VStack(alignment: .leading, spacing: 3) {
                ForEach(model.detailLines, id: \.self) { line in
                    Text(line)
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }
            }
            .textSelection(.enabled)
        } header: {
            Text("Ergebnis")
        }
    }

    private var graphSection: some View {
        Section {
            SpeedtestGraph(down: model.downSamples, up: model.upSamples,
                           duration: Double(max(5, min(60, model.settings.duration))))
                .padding(.vertical, 6)
        } header: {
            Text("Verlauf der Messung")
        }
    }

    private var controlSection: some View {
        Section {
            HStack(spacing: 10) {
                if model.running {
                    ProgressView()
                }
                Text(model.phaseText)
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(model.running ? model.tint : .secondary)
                Spacer()
            }
            if model.running {
                Button(role: .destructive) {
                    Haptics.tap()
                    model.cancel()
                } label: {
                    Label("Abbrechen", systemImage: "xmark.circle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            } else {
                Button {
                    Haptics.tap()
                    model.start()
                } label: {
                    Label("Messung starten", systemImage: "play.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(model.tint)
                .controlSize(.large)
            }
        } header: {
            Text("Messung")
        } footer: {
            Text("Cloudflare-Speedtest mit \(model.settings.streams) parallelen Verbindungen, je Richtung \(model.settings.duration) s nach 2 s Anlaufphase. Für genaue Werte andere Downloads/Streams pausieren und mehrmals messen. Im WLAN begrenzt meist die Funkstrecke.")
        }
    }

    private var historySection: some View {
        Section {
            if !model.averageText.isEmpty {
                Text(model.averageText)
                    .font(.footnote.weight(.semibold))
            }
            if let u = model.csvURL {
                ShareLink(item: u) {
                    Label("CSV exportieren", systemImage: "square.and.arrow.up")
                }
            }
            if !model.history.isEmpty {
                Button(role: .destructive) {
                    confirmClear = true
                } label: {
                    Label("Verlauf leeren", systemImage: "trash")
                }
                .confirmationDialog("Alle gespeicherten Messungen löschen?", isPresented: $confirmClear,
                                    titleVisibility: .visible) {
                    Button("Löschen", role: .destructive) {
                        model.clearHistory()
                    }
                    Button("Abbrechen", role: .cancel) {}
                }
            }
            if model.history.isEmpty {
                Text("Noch keine Messungen gespeichert.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }
            ForEach(model.history) { r in
                SpeedtestHistoryRow(r: r)
            }
            .onDelete { idx in
                model.deleteHistory(at: idx)
            }
        } header: {
            Text("Bisherige Messungen (\(model.history.count))")
        }
    }
}

struct SpeedtestHistoryRow: View {
    let r: SpeedtestResult

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(r.time).font(.caption).foregroundColor(.secondary)
                Spacer()
                Text(r.server).font(.caption).foregroundColor(.secondary).lineLimit(1)
            }
            HStack(spacing: 12) {
                Label(SpeedtestFmt.rate(r.down), systemImage: "arrow.down")
                    .foregroundColor(SpeedtestGraph.downColor)
                Label(SpeedtestFmt.rate(r.up), systemImage: "arrow.up")
                    .foregroundColor(SpeedtestGraph.upColor)
                Spacer()
                Text("\(SpeedtestFmt.ms(r.ping)) ms")
                    .foregroundColor(.secondary)
            }
            .font(.subheadline.weight(.semibold))
            .monospacedDigit()
        }
        .padding(.vertical, 2)
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct SpeedtestSettingsView: View {
    @ObservedObject var model: SpeedtestModel
    @State private var s: SpeedtestSettings

    init(model: SpeedtestModel) {
        _model = ObservedObject(wrappedValue: model)
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "Speedtest", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "Server", text: $s.base, placeholder: "https://speed.cloudflare.com", keyboard: .URL)
            } header: {
                Text("Messserver")
            } footer: {
                Text("speed.cloudflare.com oder ein kompatibler Server (/__down, /__up, /meta).")
            }
            Section {
                Stepper("Verbindungen: \(s.streams)", value: $s.streams, in: 1...32)
                Stepper("Dauer je Richtung: \(s.duration) s", value: $s.duration, in: 5...60)
            } header: {
                Text("Messung")
            } footer: {
                Text("Mehr parallele Verbindungen lasten schnelle Anschlüsse besser aus. Die ersten 2 s (Anlaufphase) zählen nicht.")
            }
            Section {
                Button("Standardwerte") {
                    s = SpeedtestSettings()
                }
            }
        }
    }
}
