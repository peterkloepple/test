// ===========================================================================
//  Tapo.swift - Studio Control iOS - TP-Link Tapo Steckdosen (P100/P110/P115 ...)
//  Autor: T. Pfeiffer
//  Lokales KLAP-Protokoll (HTTP Port 80): handshake1/handshake2, Auth-Hash v1 (MD5)
//  mit Rueckfall auf v2 (SHA1/SHA256), AES-CBC + SHA256-Signatur, Cookie TP_SESSIONID.
//  Netzsuche: Unicast-Sweep des eigenen /24 (TCP 80 offen -> KLAP-handshake1 -> get_device_info).
//  UDP-Broadcast-Suche (Port 20002/20004) ist auf iOS ohne Sonder-Entitlement nicht moeglich.
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct TapoPlug: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var name: String = ""
    var ip: String = ""
    var inScene: Bool = false

    enum CodingKeys: String, CodingKey {
        case id, name, ip, inScene
    }

    init(id: UUID = UUID(), name: String = "", ip: String = "", inScene: Bool = false) {
        self.id = id
        self.name = name
        self.ip = ip
        self.inScene = inScene
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(UUID.self, forKey: .id)) ?? UUID()
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? ""
        ip = (try? c.decodeIfPresent(String.self, forKey: .ip)) ?? ""
        inScene = (try? c.decodeIfPresent(Bool.self, forKey: .inScene)) ?? false
    }
}

struct TapoSettings: Codable {
    var email: String = ""
    var password: String = ""
    var plugs: [TapoPlug] = []
    var pollInterval: Int = 10

    enum CodingKeys: String, CodingKey {
        case email, password, plugs, pollInterval
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        email = (try? c.decodeIfPresent(String.self, forKey: .email)) ?? ""
        password = (try? c.decodeIfPresent(String.self, forKey: .password)) ?? ""
        plugs = (try? c.decodeIfPresent([TapoPlug].self, forKey: .plugs)) ?? []
        pollInterval = (try? c.decodeIfPresent(Int.self, forKey: .pollInterval)) ?? 10
    }
}

// ---------------------------------------------------------------------------
// KLAP-Protokoll (1:1 aus sc.py KlapClient)
// ---------------------------------------------------------------------------
enum TapoKlapError: LocalizedError {
    case auth(String)
    case failed(String)

    var isAuth: Bool {
        if case .auth = self { return true }
        return false
    }

    var errorDescription: String? {
        switch self {
        case .auth(let t): return t
        case .failed(let t): return t
        }
    }
}

enum TapoKlap {
    // JSON exakt wie Python json.dumps (mit Leerzeichen nach ':' und ',')
    static let jsonGetInfo = "{\"method\": \"get_device_info\"}"
    static let jsonGetEnergy = "{\"method\": \"get_energy_usage\"}"
    static func jsonSetOn(_ on: Bool) -> String {
        "{\"method\": \"set_device_info\", \"params\": {\"device_on\": \(on ? "true" : "false")}}"
    }

    /// auth_hash_v1 = md5(md5(user) + md5(pw))
    static func authV1(_ user: String, _ pw: String) -> Data {
        var d = Crypto.md5(Data(user.utf8))
        d.append(Crypto.md5(Data(pw.utf8)))
        return Crypto.md5(d)
    }

    /// auth_hash_v2 = sha256(sha1(user) + sha1(pw))
    static func authV2(_ user: String, _ pw: String) -> Data {
        var d = Crypto.sha1(Data(user.utf8))
        d.append(Crypto.sha1(Data(pw.utf8)))
        return Crypto.sha256(d)
    }

    /// _pack_i32: (n mod 2^32) als 4 Byte Big-Endian
    static func packI32(_ n: Int64) -> Data {
        let v = UInt32(truncatingIfNeeded: n)
        return Data([UInt8((v >> 24) & 0xff), UInt8((v >> 16) & 0xff), UInt8((v >> 8) & 0xff), UInt8(v & 0xff)])
    }

    /// _unpkcs7: tolerant (nur entfernen, wenn Padding gueltig)
    static func unpad(_ data: Data) -> Data {
        let b = [UInt8](data)
        guard let last = b.last else { return data }
        let p = Int(last)
        if p >= 1 && p <= 16 && b.count >= p {
            var ok = true
            for i in (b.count - p)..<b.count where b[i] != last { ok = false }
            if ok { return Data(b[0..<(b.count - p)]) }
        }
        return data
    }

    static func cat(_ parts: Data...) -> Data {
        var d = Data()
        for p in parts { d.append(p) }
        return d
    }
}

/// Ein KLAP-Client pro Steckdose (Sitzung wird wiederverwendet, bei Fehler neu aufgebaut).
@MainActor
final class TapoKlapClient {
    let ip: String
    let timeout: TimeInterval
    private var http = HTTPClient()
    private var key = Data()
    private var iv12 = Data()
    private var sig28 = Data()
    private var seq: Int64 = 0
    private(set) var ready = false
    private var locked = false

    init(ip: String, timeout: TimeInterval = 6) {
        self.ip = ip
        self.timeout = timeout
    }

    func reset() {
        ready = false
    }

    private func baseURL() -> URL? { URL(string: "http://\(ip)/") }

    private func post(_ path: String, _ body: Data) async throws -> (Int, Data, HTTPURLResponse) {
        guard let url = URL(string: "http://\(ip)\(path)") else { throw NetError.badAddress(ip) }
        let (d, r) = try await http.request("POST", url, headers: ["Content-Type": "application/octet-stream"],
                                            body: body, timeout: timeout)
        return (r.statusCode, d, r)
    }

    /// TP_SESSIONID aus Set-Cookie sicher in den Cookie-Speicher uebernehmen.
    private func adoptSessionCookie(_ resp: HTTPURLResponse) {
        guard let base = baseURL() else { return }
        if http.cookies(for: base).contains(where: { $0.name == "TP_SESSIONID" }) { return }
        guard let raw = resp.value(forHTTPHeaderField: "Set-Cookie") else { return }
        for part in raw.components(separatedBy: CharacterSet(charactersIn: ";,")) {
            let t = part.trimmed
            if t.hasPrefix("TP_SESSIONID=") {
                let v = String(t.dropFirst("TP_SESSIONID=".count))
                http.setCookie(name: "TP_SESSIONID", value: v, url: base)
                return
            }
        }
    }

    func handshake(user: String, pw: String) async throws {
        ready = false
        http = HTTPClient()          // neue Sitzung (wie requests.Session() in Python)
        let ls = Crypto.random(16)
        let ah1 = TapoKlap.authV1(user, pw)
        let ah2 = TapoKlap.authV2(user, pw)

        let (st, body, resp) = try await post("/app/handshake1", ls)
        guard st == 200, body.count >= 48 else {
            throw TapoKlapError.failed("Handshake1 fehlgeschlagen (Status \(st), \(body.count)B)")
        }
        adoptSessionCookie(resp)
        let b = [UInt8](body)
        let rs = Data(b[0..<16])
        let serverHash = Data(b[16..<48])

        let ah: Data
        let isV1: Bool
        if Crypto.sha256(TapoKlap.cat(ls, ah1)) == serverHash {
            ah = ah1
            isV1 = true
        } else if Crypto.sha256(TapoKlap.cat(ls, rs, ah2)) == serverHash {
            ah = ah2
            isV1 = false
        } else {
            throw TapoKlapError.auth("Auth fehlgeschlagen - E-Mail/Passwort pruefen (Server-Hash passt weder zu v1 noch v2)")
        }

        let hs2 = isV1 ? Crypto.sha256(TapoKlap.cat(rs, ah)) : Crypto.sha256(TapoKlap.cat(rs, ls, ah))
        let (st2, _, _) = try await post("/app/handshake2", hs2)
        guard st2 == 200 else { throw TapoKlapError.failed("Handshake2 fehlgeschlagen (Status \(st2))") }

        derive(ls: ls, rs: rs, ah: ah)
        ready = true
    }

    private func derive(ls: Data, rs: Data, ah: Data) {
        key = Data(Crypto.sha256(TapoKlap.cat(Data("lsk".utf8), ls, rs, ah)).prefix(16))
        let fiv = [UInt8](Crypto.sha256(TapoKlap.cat(Data("iv".utf8), ls, rs, ah)))
        iv12 = Data(fiv[0..<12])
        let u = (UInt32(fiv[28]) << 24) | (UInt32(fiv[29]) << 16) | (UInt32(fiv[30]) << 8) | UInt32(fiv[31])
        seq = Int64(Int32(bitPattern: u))
        sig28 = Data(Crypto.sha256(TapoKlap.cat(Data("ldk".utf8), ls, rs, ah)).prefix(28))
    }

    private func acquire() async {
        while locked { await pause(0.02) }
        locked = true
    }

    private func release() { locked = false }

    /// Verschluesselte Anfrage; liefert das JSON-Objekt der Antwort.
    func request(user: String, pw: String, json: String) async throws -> [String: Any] {
        await acquire()
        defer { release() }
        if !ready { try await handshake(user: user, pw: pw) }
        seq += 1
        let s = seq
        let iv = TapoKlap.cat(iv12, TapoKlap.packI32(s))
        let ct = try Crypto.aesCBC(encrypt: true, key: key, iv: iv, data: Data(json.utf8))
        let sig = Crypto.sha256(TapoKlap.cat(sig28, TapoKlap.packI32(s), ct))
        let (st, body, _) = try await post("/app/request?seq=\(s)", TapoKlap.cat(sig, ct))
        guard st == 200 else {
            ready = false
            throw TapoKlapError.failed("Request fehlgeschlagen (Status \(st))")
        }
        guard body.count > 32 else { throw TapoKlapError.failed("Antwort leer/nicht entschluesselbar") }
        let enc = Data([UInt8](body)[32...])
        guard let raw = try? Crypto.aesCBCNoPad(encrypt: false, key: key, iv: iv, data: enc) else {
            throw TapoKlapError.failed("Antwort leer/nicht entschluesselbar")
        }
        let plain = TapoKlap.unpad(raw)
        guard !plain.isEmpty,
              let obj = try? JSONSerialization.jsonObject(with: plain, options: []),
              let dict = obj as? [String: Any] else {
            throw TapoKlapError.failed("Antwort leer/nicht entschluesselbar")
        }
        return dict
    }
}

// ---------------------------------------------------------------------------
// Hilfen
// ---------------------------------------------------------------------------
func tapoNum(_ v: Any?) -> Double? {
    if let n = v as? NSNumber { return n.doubleValue }
    if let s = v as? String { return Double(s) }
    return nil
}

func tapoInt(_ v: Any?) -> Int? {
    if let n = v as? NSNumber { return n.intValue }
    if let s = v as? String { return Int(s) }
    return nil
}

func tapoErrorCode(_ resp: [String: Any]) -> Int {
    tapoInt(resp["error_code"]) ?? 0
}

/// _chk aus Python: error_code != 0 -> Fehler
func tapoCheck(_ resp: [String: Any]) throws {
    let ec = tapoErrorCode(resp)
    if ec != 0 { throw TapoKlapError.failed("Geraet meldet error_code=\(ec)") }
}

func tapoCleanIP(_ s: String) -> String {
    s.trimmingCharacters(in: CharacterSet(charactersIn: "#/ \t\r\n"))
}

func tapoLooksLikeIP(_ s: String) -> Bool {
    let parts = s.split(separator: ".", omittingEmptySubsequences: false)
    guard parts.count == 4 else { return false }
    for p in parts {
        guard !p.isEmpty, p.allSatisfy({ $0.isASCII && $0.isNumber }), let v = Int(p), v >= 0, v <= 255 else { return false }
    }
    return true
}

func tapoIPKey(_ ip: String) -> Int {
    var k = 0
    for p in ip.split(separator: ".") { k = k * 256 + (Int(p) ?? 0) }
    return k
}

private let tapoTypeLabels: [String: String] = [
    "SMART.TAPOPLUG": "Steckdose",
    "SMART.TAPOBULB": "Lampe",
    "SMART.TAPOSWITCH": "Schalter",
    "SMART.TAPOHUB": "Hub",
    "SMART.TAPOSENSOR": "Sensor",
    "SMART.IPCAMERA": "Kamera",
    "SMART.TAPODOORBELL": "Tuerklingel",
    "SMART.TAPOROBOVAC": "Staubsauger",
    "SMART.TAPOCHIME": "Gong",
    "SMART.KASAPLUG": "Kasa-Steckdose",
    "SMART.KASASWITCH": "Kasa-Schalter",
    "SMART.KASAHUB": "Kasa-Hub",
    "IOT.SMARTPLUGSWITCH": "Steckdose (IOT)",
    "IOT.SMARTBULB": "Lampe (IOT)",
    "IOT.IPCAMERA": "Kamera (IOT)"
]

func tapoTypeLabel(_ dtype: String, _ model: String) -> String {
    let lab = tapoTypeLabels[dtype.uppercased()]
    if let l = lab, !model.isEmpty { return "\(l) \(model)" }
    if let l = lab { return l }
    if !model.isEmpty { return model }
    return dtype.isEmpty ? "Tapo-Geraet" : dtype
}

/// Eigene IPv4 des iPhones (WLAN en0 bevorzugt) ueber getifaddrs.
func tapoLocalIPv4() -> String? {
    var addrs: UnsafeMutablePointer<ifaddrs>? = nil
    guard getifaddrs(&addrs) == 0, let first = addrs else { return nil }
    defer { freeifaddrs(addrs) }
    var fallback: String? = nil
    var ptr: UnsafeMutablePointer<ifaddrs>? = first
    while let p = ptr {
        let ifa = p.pointee
        ptr = ifa.ifa_next
        guard let sa = ifa.ifa_addr else { continue }
        if sa.pointee.sa_family != UInt8(AF_INET) { continue }
        if (Int32(ifa.ifa_flags) & IFF_UP) == 0 { continue }
        let name = String(cString: ifa.ifa_name)
        var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
        let rc = getnameinfo(sa, socklen_t(sa.pointee.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST)
        if rc != 0 { continue }
        let ip = String(cString: host)
        if ip.hasPrefix("127.") || ip.hasPrefix("169.254.") { continue }
        if name == "en0" { return ip }
        if fallback == nil && name.hasPrefix("en") { fallback = ip }
    }
    return fallback
}

// ---------------------------------------------------------------------------
// Laufzeit-Status einer Steckdose
// ---------------------------------------------------------------------------
struct TapoPlugStatus {
    var reachable = false
    var isOn = false
    var error: String?
    var model = ""
    var type = ""
    var fw = ""
    var hw = ""
    var mac = ""
    var nickname = ""
    var rssi: Int?
    var signal: Int?
    var onTime: Int?
    /// nil = unbekannt, false = kein Energiemesser (error_code bei get_energy_usage)
    var hasEnergy: Bool?
    var powerW: Double?
    var todayKWh: Double?
    var monthKWh: Double?
}

struct TapoScanHit: Identifiable, Hashable {
    var id: String { ip }
    let ip: String
    let label: String

    /// Name fuer die Uebernahme (wie adopt_ip in Python)
    var adoptName: String {
        if label == "(Typ ungeprueft)" || label == "anderes Konto" || label.isEmpty {
            return "Geraet " + (ip.split(separator: ".").last.map { String($0) } ?? ip)
        }
        return label
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
@MainActor
final class TapoModel: DeviceModel {
    @Published var settings = TapoSettings()
    @Published var status: [UUID: TapoPlugStatus] = [:]
    @Published var pending: Set<UUID> = []

    @Published var scanRunning = false
    @Published var scanDone = 0
    @Published var scanTotal = 0
    @Published var scanFound: [TapoScanHit] = []
    @Published var scanInfo = ""
    private var scanStop = false
    private var scanQueue: [String] = []
    private var scanIndex = 0

    private var clients: [String: TapoKlapClient] = [:]

    init() {
        super.init(id: "tapo", title: "Steckdosen", subtitle: "TP-Link Tapo (KLAP)",
                   symbol: "powerplug.fill", tint: Color(hex: 0x30D158))
    }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(TapoSettings.self, "tapo") { settings = s }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "tapo")
        clients.removeAll()
    }

    override var isConfigured: Bool {
        !settings.email.trimmed.isEmpty && !settings.password.isEmpty
            && settings.plugs.contains(where: { !tapoCleanIP($0.ip).isEmpty })
    }

    override var pollInterval: Double { Double(max(3, settings.pollInterval)) }

    override var supportsScene: Bool { settings.plugs.contains(where: { $0.inScene }) }

    override func disconnect() {
        clients.removeAll()
    }

    // ---- Netzwerk ----
    private func client(_ ip: String) -> TapoKlapClient {
        if let c = clients[ip] { return c }
        let c = TapoKlapClient(ip: ip)
        clients[ip] = c
        return c
    }

    /// Anfrage an eine Steckdose; bei abgelaufener Sitzung einmal neu verbinden.
    private func call(_ rawIP: String, _ json: String) async throws -> [String: Any] {
        let ip = tapoCleanIP(rawIP)
        guard tapoLooksLikeIP(ip) else {
            throw TapoKlapError.failed("\(ip): keine IP-Adresse (z.B. 192.168.0.237 eintragen)")
        }
        let user = settings.email.trimmed
        let pw = settings.password
        guard !user.isEmpty, !pw.isEmpty else { throw TapoKlapError.auth("Bitte E-Mail und Passwort eintragen") }
        let c = client(ip)
        let wasReady = c.ready
        do {
            return try await c.request(user: user, pw: pw, json: json)
        } catch let e as TapoKlapError where e.isAuth {
            throw e
        } catch {
            if !wasReady { throw error }
            c.reset()
            return try await c.request(user: user, pw: pw, json: json)
        }
    }

    private func poll(_ p: TapoPlug, prev: TapoPlugStatus) async -> TapoPlugStatus {
        var st = prev
        do {
            let info = try await call(p.ip, TapoKlap.jsonGetInfo)
            try tapoCheck(info)
            let res = info["result"] as? [String: Any] ?? [:]
            st.reachable = true
            st.error = nil
            st.isOn = (res["device_on"] as? Bool) == true
            st.model = (res["model"] as? String) ?? st.model
            st.type = (res["type"] as? String) ?? st.type
            st.fw = (res["fw_ver"] as? String) ?? st.fw
            st.hw = (res["hw_ver"] as? String) ?? st.hw
            st.mac = (res["mac"] as? String) ?? st.mac
            if let nick = res["nickname"] as? String {
                if let d = Data(base64Encoded: nick), let t = String(data: d, encoding: .utf8) {
                    st.nickname = t
                } else {
                    st.nickname = nick
                }
            }
            st.rssi = tapoInt(res["rssi"])
            st.signal = tapoInt(res["signal_level"])
            st.onTime = tapoInt(res["on_time"])
        } catch {
            st.reachable = false
            st.error = DeviceModel.describe(error)
            return st
        }
        if st.hasEnergy != false {
            if let e = try? await call(p.ip, TapoKlap.jsonGetEnergy) {
                if tapoErrorCode(e) != 0 {
                    st.hasEnergy = false
                    st.powerW = nil
                    st.todayKWh = nil
                    st.monthKWh = nil
                } else {
                    let r = e["result"] as? [String: Any] ?? [:]
                    st.hasEnergy = true
                    st.powerW = tapoNum(r["current_power"]).map { $0 / 1000.0 }
                    st.todayKWh = tapoNum(r["today_energy"]).map { $0 / 1000.0 }
                    st.monthKWh = tapoNum(r["month_energy"]).map { $0 / 1000.0 }
                }
            }
        }
        return st
    }

    override func refresh() async {
        await refreshSafely {
            let plugs = self.settings.plugs.filter { !tapoCleanIP($0.ip).isEmpty }
            if plugs.isEmpty { throw NetError.protocolError("Keine Steckdose eingetragen") }
            var tasks: [(UUID, Task<TapoPlugStatus, Never>)] = []
            for p in plugs {
                let prev = self.status[p.id] ?? TapoPlugStatus()
                let t = Task { await self.poll(p, prev: prev) }
                tasks.append((p.id, t))
            }
            var online = 0
            var firstErr: String?
            for (id, t) in tasks {
                let st = await t.value
                if self.pending.contains(id), let old = self.status[id] {
                    var merged = st
                    merged.isOn = old.isOn
                    self.status[id] = merged
                } else {
                    self.status[id] = st
                }
                if st.reachable { online += 1 } else if firstErr == nil { firstErr = st.error }
            }
            let ids = Set(self.settings.plugs.map { $0.id })
            self.status = self.status.filter { ids.contains($0.key) }
            if online == 0 { throw NetError.protocolError(firstErr ?? "Keine Steckdose erreichbar") }
            self.summary = self.makeSummary()
        }
    }

    func makeSummary() -> String {
        let plugs = settings.plugs.filter { !tapoCleanIP($0.ip).isEmpty }
        var onCount = 0
        var watts = 0.0
        var haveWatts = false
        for p in plugs {
            guard let st = status[p.id], st.reachable else { continue }
            if st.isOn { onCount += 1 }
            if let w = st.powerW { watts += w; haveWatts = true }
        }
        var s = "\(onCount) von \(plugs.count) an"
        if haveWatts { s += " - \(Int(watts.rounded())) W" }
        return s
    }

    var totalPowerW: Double? {
        var sum = 0.0
        var have = false
        for p in settings.plugs {
            if let st = status[p.id], st.reachable, let w = st.powerW { sum += w; have = true }
        }
        return have ? sum : nil
    }

    var totalTodayKWh: Double? {
        var sum = 0.0
        var have = false
        for p in settings.plugs {
            if let st = status[p.id], let v = st.todayKWh { sum += v; have = true }
        }
        return have ? sum : nil
    }

    var totalMonthKWh: Double? {
        var sum = 0.0
        var have = false
        for p in settings.plugs {
            if let st = status[p.id], let v = st.monthKWh { sum += v; have = true }
        }
        return have ? sum : nil
    }

    // ---- Aktionen ----
    private func switchPlug(_ p: TapoPlug, _ on: Bool) async throws {
        let resp = try await call(p.ip, TapoKlap.jsonSetOn(on))
        try tapoCheck(resp)
        var st = status[p.id] ?? TapoPlugStatus()
        st.isOn = on
        st.reachable = true
        st.error = nil
        status[p.id] = st
        summary = makeSummary()
    }

    func setPlug(_ p: TapoPlug, _ on: Bool) {
        let name = p.name.trimmed.isEmpty ? tapoCleanIP(p.ip) : p.name
        pending.insert(p.id)
        perform("\(name): \(on ? "Ein" : "Aus")") {
            defer { self.pending.remove(p.id) }
            try await self.switchPlug(p, on)
            await pause(0.8)
            await self.refresh()
        }
    }

    func setAll(_ on: Bool) {
        let plugs = settings.plugs.filter { !tapoCleanIP($0.ip).isEmpty }
        perform(on ? "Alle Steckdosen ein" : "Alle Steckdosen aus") {
            var errors: [String] = []
            for p in plugs {
                do { try await self.switchPlug(p, on) } catch {
                    errors.append("\(p.name): \(DeviceModel.describe(error))")
                }
            }
            await self.refresh()
            if !errors.isEmpty { throw NetError.protocolError(errors.joined(separator: "; ")) }
        }
    }

    override func scene(_ on: Bool) async throws {
        let plugs = settings.plugs.filter { $0.inScene && !tapoCleanIP($0.ip).isEmpty }
        var errors: [String] = []
        for p in plugs {
            do { try await switchPlug(p, on) } catch {
                errors.append("\(p.name): \(DeviceModel.describe(error))")
            }
        }
        addLog("Szene \(on ? "an" : "aus"): \(plugs.count - errors.count) von \(plugs.count) geschaltet", error: !errors.isEmpty)
        if !errors.isEmpty { throw NetError.protocolError(errors.joined(separator: "; ")) }
    }

    // ---- Netzsuche (Unicast-Sweep wie scan_network/classify_device) ----
    func startScan(user: String, pw: String) {
        if scanRunning {
            scanStop = true
            scanInfo = "Suche wird abgebrochen ..."
            return
        }
        guard let own = tapoLocalIPv4() else {
            scanInfo = "Kein WLAN gefunden - iPhone mit dem Netz der Steckdosen verbinden."
            return
        }
        let parts = own.split(separator: ".")
        guard parts.count == 4 else { scanInfo = "Ungueltige eigene Adresse \(own)"; return }
        let base = parts[0..<3].joined(separator: ".") + "."
        scanQueue = (1...254).map { base + String($0) }
        scanIndex = 0
        scanDone = 0
        scanTotal = scanQueue.count
        scanFound = []
        scanStop = false
        scanRunning = true
        scanInfo = "Suche in \(base)0/24 ..."
        addLog("Scan startet in \(base)0/24")
        let u = user.trimmed
        Task { await self.runScan(user: u, pw: pw) }
    }

    private func runScan(user: String, pw: String) async {
        var workers: [Task<Void, Never>] = []
        for _ in 0..<24 {
            workers.append(Task { await self.scanWorker(user: user, pw: pw) })
        }
        for w in workers { await w.value }
        if scanStop {
            scanInfo = "Abgebrochen - gefunden: \(scanFound.count)"
            addLog("Scan abgebrochen. Bisher gefunden: \(scanFound.count)")
        } else {
            scanInfo = "Fertig - gefunden: \(scanFound.count)"
            addLog("Scan fertig. Gefundene Geraete: \(scanFound.count)")
        }
        scanRunning = false
        scanStop = false
    }

    private func scanWorker(user: String, pw: String) async {
        while !scanStop && scanIndex < scanQueue.count {
            let ip = scanQueue[scanIndex]
            scanIndex += 1
            let hit = await scanProbe(ip, user: user, pw: pw)
            scanDone += 1
            if let h = hit, !scanFound.contains(where: { $0.ip == h.ip }) {
                scanFound.append(h)
                scanFound.sort { tapoIPKey($0.ip) < tapoIPKey($1.ip) }
                addLog("GEFUNDEN (Sweep): \(h.label) auf \(h.ip)")
            }
        }
    }

    private func scanProbe(_ ip: String, user: String, pw: String) async -> TapoScanHit? {
        guard await TCPConnection.probe(host: ip, port: 80, timeout: 0.6) else { return nil }
        guard await isTapo(ip) else { return nil }
        if user.isEmpty || pw.isEmpty { return TapoScanHit(ip: ip, label: "(Typ ungeprueft)") }
        let c = TapoKlapClient(ip: ip, timeout: 3)
        do {
            let info = try await c.request(user: user, pw: pw, json: TapoKlap.jsonGetInfo)
            let res = info["result"] as? [String: Any] ?? [:]
            let dtype = ((res["type"] as? String) ?? "").uppercased()
            let model = (res["model"] as? String) ?? ""
            return TapoScanHit(ip: ip, label: tapoTypeLabel(dtype, model))
        } catch let e as TapoKlapError where e.isAuth {
            return TapoScanHit(ip: ip, label: "anderes Konto")
        } catch {
            return nil
        }
    }

    /// _is_tapo: handshake1 mit 16 Zufallsbytes -> Status 200 und >= 48 Byte
    private func isTapo(_ ip: String) async -> Bool {
        guard let url = URL(string: "http://\(ip)/app/handshake1") else { return false }
        let h = HTTPClient()
        do {
            let (d, r) = try await h.request("POST", url, headers: ["Content-Type": "application/octet-stream"],
                                             body: Crypto.random(16), timeout: 1.2)
            return r.statusCode == 200 && d.count >= 48
        } catch {
            return false
        }
    }

    // ---- Demo (Start mit -demo, ohne Netzwerk) ----
    override func loadDemo() {
        let p1 = TapoPlug(name: "Licht Studio", ip: "192.168.1.61", inScene: true)
        let p2 = TapoPlug(name: "Monitore", ip: "192.168.1.62", inScene: true)
        let p3 = TapoPlug(name: "Verstaerker", ip: "192.168.1.63", inScene: true)
        let p4 = TapoPlug(name: "Kaffeemaschine", ip: "192.168.1.64", inScene: false)
        var s = TapoSettings()
        s.email = "studio@example.com"
        s.password = "demo"
        s.plugs = [p1, p2, p3, p4]
        s.pollInterval = 10
        settings = s

        func mk(_ on: Bool, _ nick: String, _ mac: String, _ rssi: Int, _ sig: Int, _ onTime: Int,
                _ w: Double, _ today: Double, _ month: Double) -> TapoPlugStatus {
            var st = TapoPlugStatus()
            st.reachable = true
            st.isOn = on
            st.error = nil
            st.model = "P110"
            st.type = "SMART.TAPOPLUG"
            st.fw = "1.3.1 Build 240621 Rel.162048"
            st.hw = "1.0"
            st.mac = mac
            st.nickname = nick
            st.rssi = rssi
            st.signal = sig
            st.onTime = on ? onTime : 0
            st.hasEnergy = true
            st.powerW = w
            st.todayKWh = today
            st.monthKWh = month
            return st
        }
        status = [
            p1.id: mk(true, "Licht Studio", "3C-52-A1-10-20-01", -48, 3, 9_840, 42.6, 0.31, 6.84),
            p2.id: mk(true, "Monitore", "3C-52-A1-10-20-02", -55, 3, 9_790, 68.2, 0.52, 11.37),
            p3.id: mk(true, "Verstaerker", "3C-52-A1-10-20-03", -61, 2, 9_720, 23.9, 0.19, 4.12),
            p4.id: mk(false, "Kaffeemaschine", "3C-52-A1-10-20-04", -67, 2, 0, 0.0, 0.08, 2.95),
        ]
        pending = []
        summary = makeSummary()
    }
}

// ---------------------------------------------------------------------------
// Ansicht
// ---------------------------------------------------------------------------
struct TapoView: View {
    @ObservedObject var model: TapoModel

    var body: some View {
        DevicePage(model: model, settings: { TapoSettingsView(model: model) }) {
            if !model.settings.plugs.isEmpty {
                Section("Alle Steckdosen") {
                    TileGrid {
                        ActionTile(title: "Alle an", symbol: "power", tint: Color(hex: 0x30D158)) { model.setAll(true) }
                        ActionTile(title: "Alle aus", symbol: "poweroff", tint: .red) { model.setAll(false) }
                    }
                }
            }
            if model.totalPowerW != nil || model.totalTodayKWh != nil {
                Section("Verbrauch gesamt") {
                    ValueRow(label: "Leistung jetzt", value: tapoFmtW(model.totalPowerW), symbol: "bolt.fill")
                    ValueRow(label: "Heute", value: tapoFmtKWh(model.totalTodayKWh), symbol: "sun.max")
                    ValueRow(label: "Dieser Monat", value: tapoFmtKWh(model.totalMonthKWh), symbol: "calendar")
                }
            }
            if model.settings.plugs.isEmpty {
                Section("Steckdosen") {
                    Text("Noch keine Steckdosen eingetragen. In den Einstellungen hinzufügen oder „Netz durchsuchen“.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            ForEach(model.settings.plugs) { p in
                TapoPlugSection(model: model, plug: p, st: model.status[p.id])
            }
        }
    }
}

func tapoFmtW(_ v: Double?) -> String {
    guard let v = v else { return "-" }
    return String(format: "%.1f W", v)
}

func tapoFmtKWh(_ v: Double?) -> String {
    guard let v = v else { return "-" }
    return String(format: "%.2f kWh", v)
}

func tapoFmtDuration(_ sec: Int?) -> String {
    guard let s = sec else { return "-" }
    let d = s / 86400
    let h = (s % 86400) / 3600
    let m = (s % 3600) / 60
    if d > 0 { return "\(d) d \(h) h" }
    if h > 0 { return "\(h) h \(m) min" }
    return "\(m) min"
}

struct TapoPlugSection: View {
    @ObservedObject var model: TapoModel
    let plug: TapoPlug
    let st: TapoPlugStatus?

    var title: String {
        plug.name.trimmed.isEmpty ? tapoCleanIP(plug.ip) : plug.name
    }

    var stateText: String {
        guard let s = st else { return "Wird geprüft ..." }
        if !s.reachable { return "Nicht erreichbar" }
        return s.isOn ? "Ein" : "Aus"
    }

    var body: some View {
        Section {
            HStack {
                PowerToggleRow(title: title, symbol: "powerplug", isOn: st?.isOn ?? false,
                               tint: Color(hex: 0x30D158)) { v in model.setPlug(plug, v) }
                    .disabled(model.pending.contains(plug.id))
                if model.pending.contains(plug.id) { ProgressView().padding(.leading, 4) }
            }
            ValueRow(label: "Status", value: stateText,
                     valueColor: (st?.reachable ?? false) ? ((st?.isOn ?? false) ? Color.green : Color.secondary) : Color.red)
            if let s = st, s.hasEnergy == true {
                ValueRow(label: "Leistung", value: tapoFmtW(s.powerW), symbol: "bolt.fill")
                ValueRow(label: "Heute", value: tapoFmtKWh(s.todayKWh))
                ValueRow(label: "Monat", value: tapoFmtKWh(s.monthKWh))
            }
            DisclosureGroup("Geräteinfo") {
                ValueRow(label: "IP-Adresse", value: tapoCleanIP(plug.ip))
                ValueRow(label: "Modell", value: (st?.model ?? "").isEmpty ? "-" : (st?.model ?? "-"))
                ValueRow(label: "Name in der App", value: (st?.nickname ?? "").isEmpty ? "-" : (st?.nickname ?? "-"))
                ValueRow(label: "Firmware", value: (st?.fw ?? "").isEmpty ? "-" : (st?.fw ?? "-"))
                ValueRow(label: "Hardware", value: (st?.hw ?? "").isEmpty ? "-" : (st?.hw ?? "-"))
                ValueRow(label: "MAC", value: (st?.mac ?? "").isEmpty ? "-" : (st?.mac ?? "-"))
                ValueRow(label: "WLAN", value: tapoSignalText(st))
                ValueRow(label: "Eingeschaltet seit", value: (st?.isOn ?? false) ? tapoFmtDuration(st?.onTime) : "-")
                ValueRow(label: "In Szene", value: plug.inScene ? "Ja" : "Nein")
            }
        } footer: {
            if let e = st?.error, !(st?.reachable ?? false) {
                Text(e).foregroundStyle(.red)
            }
        }
    }
}

func tapoSignalText(_ st: TapoPlugStatus?) -> String {
    guard let s = st else { return "-" }
    var parts: [String] = []
    if let r = s.rssi { parts.append("\(r) dBm") }
    if let l = s.signal { parts.append("Stufe \(l)") }
    return parts.isEmpty ? "-" : parts.joined(separator: " - ")
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct TapoSettingsView: View {
    @ObservedObject var model: TapoModel
    @State var s: TapoSettings

    init(model: TapoModel) {
        _model = ObservedObject(wrappedValue: model)
        _s = State(initialValue: model.settings)
    }

    private func isKnown(_ ip: String) -> Bool {
        s.plugs.contains(where: { tapoCleanIP($0.ip) == ip })
    }

    private func adopt(_ h: TapoScanHit) {
        if isKnown(h.ip) { return }
        s.plugs.append(TapoPlug(name: h.adoptName, ip: h.ip, inScene: false))
    }

    var body: some View {
        SettingsSheet(title: "Tapo-Steckdosen", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "E-Mail", text: $s.email, placeholder: "name@beispiel.de", keyboard: .emailAddress)
                FieldRow(label: "Passwort", text: $s.password, placeholder: "Tapo-Passwort", secure: true)
            } header: {
                Text("Tapo-Konto")
            } footer: {
                Text("Die Zugangsdaten des Tapo-App-Kontos. Sie werden im Schlüsselbund gespeichert.")
            }
            Section {
                ForEach($s.plugs) { $p in
                    VStack(alignment: .leading, spacing: 6) {
                        TextField("Name", text: $p.name)
                            .font(.body.weight(.semibold))
                        TextField("IP-Adresse (z.B. 192.168.0.237)", text: $p.ip)
                            .keyboardType(.numbersAndPunctuation)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .foregroundStyle(.secondary)
                        Toggle("In Szene „Studio an/aus“", isOn: $p.inScene)
                            .font(.subheadline)
                    }
                    .padding(.vertical, 2)
                }
                .onDelete { idx in s.plugs.remove(atOffsets: idx) }
                .onMove { from, to in s.plugs.move(fromOffsets: from, toOffset: to) }
                Button {
                    s.plugs.append(TapoPlug(name: "Steckdose \(s.plugs.count + 1)"))
                } label: {
                    Label("Steckdose hinzufügen", systemImage: "plus.circle.fill")
                }
            } header: {
                Text("Steckdosen")
            } footer: {
                Text("Zum Entfernen nach links wischen.")
            }
            Section {
                Button {
                    model.startScan(user: s.email, pw: s.password)
                } label: {
                    Label(model.scanRunning ? "Suche abbrechen" : "Netz durchsuchen",
                          systemImage: model.scanRunning ? "stop.circle" : "magnifyingglass")
                }
                if model.scanRunning {
                    VStack(alignment: .leading, spacing: 4) {
                        ProgressView(value: Double(model.scanDone), total: Double(max(1, model.scanTotal)))
                        Text("KLAP-Sweep \(model.scanDone)/\(model.scanTotal)")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if !model.scanInfo.isEmpty {
                    Text(model.scanInfo).font(.footnote).foregroundStyle(.secondary)
                }
                ForEach(model.scanFound) { h in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(h.ip).font(.body.monospacedDigit())
                            Text(h.label).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if isKnown(h.ip) {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        } else {
                            Button("Übernehmen") { adopt(h) }
                                .buttonStyle(.borderless)
                        }
                    }
                }
                if model.scanFound.contains(where: { !isKnown($0.ip) }) {
                    Button {
                        for h in model.scanFound { adopt(h) }
                    } label: {
                        Label("Alle übernehmen", systemImage: "square.and.arrow.down")
                    }
                }
            } header: {
                Text("Netz durchsuchen")
            } footer: {
                Text("Prüft alle Adressen im eigenen WLAN-Netz (/24) auf Port 80 und den Tapo-Handshake. Mit Zugangsdaten wird zusätzlich der Gerätetyp gelesen.")
            }
            Section("Aktualisierung") {
                Stepper("Abfrage alle \(s.pollInterval) s", value: $s.pollInterval, in: 3...120)
            }
        }
    }
}
