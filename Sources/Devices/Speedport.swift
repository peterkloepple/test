// ===========================================================================
//  Speedport.swift - Studio Control iOS - Telekom Speedport Smart 4 Typ B
//  Autor: T. Pfeiffer
//
//  Port des Python-Moduls SpeedportModule (speedport-api 0.6.0):
//    - alle JSON-Daten (data/*.json) sind AES-CCM verschluesselt, hex-codiert,
//      Tag 16 Byte am Ende, Nonce = erste 8 Byte des Schluessels
//    - Schluessel ohne Anmeldung: DEFAULT_KEY; nach Login: die Challenge
//    - Login: POST data/Login.json "getChallenge=1" (+httoken) -> challenge,
//      dann "showpw=0&password=" + sha256(challenge:passwort) (Default-Key)
//    - POST-Aktionen: httoken von der Referer-Seite, Body "k=v&..." verschluesselt
//  Status: Modell/Firmware, Internet, externe IP (nach Login), Uptime,
//          DSL-Raten, WLAN/Gast-WLAN, Geraeteliste, Verbindungs-Historie
//  Aktionen: WLAN an/aus, Gast-WLAN an/aus, Reconnect, Neustart (mit Rueckfrage)
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct SpeedportSettings: Codable {
    var ip: String = "192.168.0.1"
    var password: String = ""
    var pollInterval: Int = 30

    enum CodingKeys: String, CodingKey {
        case ip, password, pollInterval
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ip = try c.decodeIfPresent(String.self, forKey: .ip) ?? "192.168.0.1"
        password = try c.decodeIfPresent(String.self, forKey: .password) ?? ""
        pollInterval = try c.decodeIfPresent(Int.self, forKey: .pollInterval) ?? 30
    }
}

// ---------------------------------------------------------------------------
// Datentypen
// ---------------------------------------------------------------------------
struct SpeedportDevice: Identifiable, Hashable {
    let id: String
    var name: String
    var ip: String
    var mac: String
    var typ: String
    var active: Bool
}

struct SpeedportHistEntry: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var date: Date = Date()
    var t: String = ""
    var online: String = "-"
    var down: String = "-"
    var up: String = "-"
    var ext: String = "-"
    var uptime: String = ""
    var ev: String = ""
}

// ---------------------------------------------------------------------------
// AES-CCM (RFC 3610) Verschluesselung - Gegenstueck zu Crypto.aesCCMDecrypt
// ---------------------------------------------------------------------------
enum SpeedportCCM {
    /// Verschluesselt `plain` ohne AAD; Rueckgabe = Chiffrat + Tag.
    static func encrypt(key: Data, nonce: Data, plain: Data, tagLen: Int = 16) throws -> Data {
        let L = 15 - nonce.count
        func ctrBlock(_ i: Int) -> Data {
            var b = Data([UInt8(L - 1)])
            b.append(nonce)
            var tail = [UInt8](repeating: 0, count: L)
            var v = i
            var k = L - 1
            while k >= 0 { tail[k] = UInt8(v & 0xff); v >>= 8; k -= 1 }
            b.append(contentsOf: tail)
            return b
        }
        // CBC-MAC ueber B0 + Klartext (aufgefuellt)
        let flags: UInt8 = UInt8(((tagLen - 2) / 2) << 3) | UInt8(L - 1)
        var b0 = Data([flags])
        b0.append(nonce)
        var ln = [UInt8](repeating: 0, count: L)
        var v = plain.count
        var k = L - 1
        while k >= 0 { ln[k] = UInt8(v & 0xff); v >>= 8; k -= 1 }
        b0.append(contentsOf: ln)
        var macInput = b0
        var p = plain
        while p.count % 16 != 0 { p.append(0) }
        macInput.append(p)
        let macAll = try Crypto.aesCBCNoPad(encrypt: true, key: key, iv: Data(count: 16), data: macInput)
        let mac = [UInt8](macAll.suffix(16))
        let s0Data = try Crypto.aesECB(key: key, block: ctrBlock(0))
        let s0 = [UInt8](s0Data)
        var out = try Crypto.aesCTR(key: key, counter: ctrBlock(1), data: plain)
        for i in 0..<tagLen { out.append(mac[i] ^ s0[i]) }
        return out
    }
}

// ---------------------------------------------------------------------------
// Client (Port von speedport/connection.py + api.py)
// ---------------------------------------------------------------------------
final class SpeedportClient {
    static let defaultKey = "cdc0cac1280b516e674f0057e4929bca84447cca8425007e33a88a5cf598a190"

    let base: String                // "http://ip"
    let http = HTTPClient()
    private(set) var loginKey = ""
    var isLoggedIn: Bool { !loginKey.isEmpty }

    init(host: String) throws {
        guard let u = makeURL(host) else { throw NetError.badAddress(host) }
        base = u.absoluteString
    }

    // ---- Verschluesselung (decode / encode) ----

    static func keyData(_ key: String) throws -> Data {
        let k = key.isEmpty ? defaultKey : key
        guard let d = Data(hex: k), d.count == 16 || d.count == 24 || d.count == 32 else {
            throw NetError.protocolError("Speedport: ungültiger Schlüssel")
        }
        return d
    }

    static func decode(_ text: String, key: String) throws -> Any {
        let kd = try keyData(key)
        guard let ct = Data(hex: text.trimmed) else {
            throw NetError.protocolError("Speedport: falscher Entschlüsselungs-Schlüssel")
        }
        let plain = try Crypto.aesCCMDecrypt(key: kd, nonce: Data(kd.prefix(8)), ciphertextAndTag: ct,
                                             aad: Data(), tagLen: 16)
        if let obj = try? JSONSerialization.jsonObject(with: plain, options: [.fragmentsAllowed]) {
            if let arr = obj as? [Any] { return simplify(arr) }
            return obj
        }
        return String(decoding: plain, as: UTF8.self)
    }

    static func encode(_ text: String, key: String) throws -> String {
        let kd = try keyData(key)
        return try SpeedportCCM.encrypt(key: kd, nonce: Data(kd.prefix(8)), plain: Data(text.utf8), tagLen: 16).hex
    }

    /// varid/varvalue-Liste in ein flaches Woerterbuch umbauen (simplify_response).
    static func simplify(_ arr: [Any]) -> [String: Any] {
        var result: [String: Any] = [:]
        for it in arr {
            guard let item = it as? [String: Any] else { continue }
            let varid = str(item["varid"])
            if varid.isEmpty { continue }
            if let list = item["varvalue"] as? [Any] {
                var li: [String: Any] = [:]
                for sub in list {
                    if let sd = sub as? [String: Any] {
                        let sid = str(sd["varid"])
                        if !sid.isEmpty { li[sid] = sd["varvalue"] ?? "" }
                    }
                }
                var existing = result[varid] as? [[String: Any]] ?? []
                existing.append(li)
                result[varid] = existing
            } else {
                result[varid] = item["varvalue"] ?? ""
            }
        }
        return result
    }

    static func str(_ v: Any?) -> String {
        guard let v = v else { return "" }
        if v is NSNull { return "" }
        if let s = v as? String { return s }
        if let n = v as? NSNumber { return n.stringValue }
        return String(describing: v)
    }

    // ---- HTTP ----

    private func url(_ s: String) throws -> URL {
        guard let u = URL(string: s) else { throw NetError.badAddress(s) }
        return u
    }

    /// httoken aus der Referer-Seite lesen ("httoken = 123456").
    private func httoken(_ pageURL: String) async throws -> String {
        let (d, _) = try await http.request("GET", try url(pageURL), timeout: 8)
        let text = String(decoding: d, as: UTF8.self)
        guard let re = try? NSRegularExpression(pattern: "httoken = (\\d+)") else { return "" }
        let ns = text as NSString
        if let m = re.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)), m.numberOfRanges > 1 {
            return ns.substring(with: m.range(at: 1))
        }
        return ""
    }

    func get(_ path: String, auth: Bool = false, referer: String = "", timeout: TimeInterval = 8) async throws -> Any {
        var u = "\(base)/\(path)"
        var ref = ""
        if !referer.isEmpty {
            ref = "\(base)/\(referer)"
            let tok = try await httoken(ref)
            if !tok.isEmpty { u += "?_tn=\(tok)" }
        }
        var headers: [String: String] = [:]
        if !ref.isEmpty { headers["Referer"] = ref }
        let (d, _) = try await http.request("GET", try url(u), headers: headers, timeout: timeout)
        return try SpeedportClient.decode(String(decoding: d, as: UTF8.self), key: auth ? loginKey : SpeedportClient.defaultKey)
    }

    func post(_ path: String, _ data: [(String, String)], referer: String, timeout: TimeInterval = 15) async throws -> Any {
        let ref = "\(base)/\(referer)"
        var items = data
        let tok = try await httoken(ref)
        if !tok.isEmpty { items.append(("httoken", tok)) }
        let body = items.map { "\($0.0)=\($0.1)" }.joined(separator: "&")
        let enc = try SpeedportClient.encode(body, key: loginKey)
        let headers = ["Referer": ref, "Content-Type": "text/plain; charset=utf-8"]
        let (d, _) = try await http.request("POST", try url("\(base)/\(path)"), headers: headers,
                                            body: Data(enc.utf8), timeout: timeout)
        return try SpeedportClient.decode(String(decoding: d, as: UTF8.self), key: loginKey)
    }

    /// Anmeldung wie Connection.login (Challenge wird zum Sitzungsschluessel).
    func login(_ password: String, retry: Int = 1) async throws {
        loginKey = ""
        let ch = try await post("data/Login.json", [("getChallenge", "1")], referer: "/", timeout: 8)
        guard let cd = ch as? [String: Any] else { throw NetError.protocolError("Speedport: keine Challenge") }
        let challenge = SpeedportClient.str(cd["challenge"])
        guard !challenge.isEmpty else { throw NetError.protocolError("Speedport: keine Challenge") }
        loginKey = challenge
        let hash = Crypto.sha256(Data("\(challenge):\(password)".utf8)).hex
        let enc = try SpeedportClient.encode("showpw=0&password=" + hash, key: SpeedportClient.defaultKey)
        let (d, _) = try await http.request("POST", try url("\(base)/data/Login.json"),
                                            headers: ["Content-Type": "text/plain; charset=utf-8"],
                                            body: Data(enc.utf8), timeout: 8)
        let res = try SpeedportClient.decode(String(decoding: d, as: UTF8.self), key: SpeedportClient.defaultKey)
        let r = res as? [String: Any] ?? [:]
        let locked = Int(SpeedportClient.str(r["login_locked"])) ?? 0
        if locked > 0 && locked < 60 {
            // Python wartet und versucht es erneut (innerhalb des 8-s-Limits)
            if retry > 0 && locked + 1 <= 7 {
                await pause(Double(locked + 1))
                try await login(password, retry: retry - 1)
                return
            }
            loginKey = ""
            throw NetError.protocolError("Login gesperrt - bitte \(locked) s warten")
        }
        if SpeedportClient.str(r["login"]) != "success" {
            loginKey = ""
            throw NetError.protocolError("Login fehlgeschlagen (Gerätepasswort?)")
        }
    }

    // ---- API ----

    func status() async throws -> [String: Any] {
        let r = try await get("data/Status.json")
        return r as? [String: Any] ?? [:]
    }

    func ipData() async throws -> [String: Any] {
        let r = try await get("data/IPData.json", auth: true, referer: "html/content/internet/con_ipdata.html", timeout: 6)
        return r as? [String: Any] ?? [:]
    }

    /// DeviceList.json -> addm*-Listen. sorted=true wie die Property sp.devices
    /// (Sortierung nach letztem IPv4-Oktett, wirft bei fehlender IP).
    func devices(auth: Bool, sorted: Bool) async throws -> [[String: Any]] {
        let r = try await get("data/DeviceList.json", auth: auth, timeout: 10)
        guard let d = r as? [String: Any] else { return [] }
        var out: [[String: Any]] = []
        for key in ["addmlandevice", "addmwlan5device", "addmwlandevice", "addmdevice"] {
            if let l = d[key] as? [[String: Any]] { out += l }
        }
        if sorted {
            var keyed: [(Int, [String: Any])] = []
            for dev in out {
                let ip = SpeedportClient.str(dev["mdevice_ipv4"])
                guard let last = ip.split(separator: ".").last, let n = Int(last) else {
                    throw NetError.protocolError("Speedport: Gerät ohne IPv4")
                }
                keyed.append((n, dev))
            }
            keyed.sort { $0.0 < $1.0 }
            out = keyed.map { $0.1 }
        }
        return out
    }

    func setWifi(_ on: Bool, guest: Bool) async throws {
        let v = on ? "1" : "0"
        if guest {
            _ = try await post("data/WLANBasic.json", [("wlan_guest_active", v)],
                               referer: "html/content/network/wlan_guest.html")
        } else {
            _ = try await post("data/Modules.json", [("use_wlan", v)],
                               referer: "html/content/network/wlan_basic.html")
        }
    }

    func reconnect() async throws {
        _ = try await post("data/Connect.json", [("req_connect", "reconnect")],
                           referer: "html/content/internet/con_ipdata.html")
    }

    func reboot() async throws {
        _ = try await post("data/Reboot.json", [("reboot_device", "true")],
                           referer: "html/content/config/restart.html")
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
enum SpeedportAction: String {
    case wifiOn, wifiOff, guestOn, guestOff, reconnect, reboot

    var label: String {
        switch self {
        case .wifiOn: return "WLAN an"
        case .wifiOff: return "WLAN aus"
        case .guestOn: return "Gast-WLAN an"
        case .guestOff: return "Gast-WLAN aus"
        case .reconnect: return "Reconnect"
        case .reboot: return "Neustart"
        }
    }
}

@MainActor
final class SpeedportModel: DeviceModel {
    static let histMax = 1000

    @Published var settings = SpeedportSettings()
    @Published var modelInfo = ""
    @Published var online = ""
    @Published var publicIP = ""
    @Published var uptime = ""
    @Published var down = ""
    @Published var up = ""
    @Published var wlanOn: Bool?
    @Published var guestOn: Bool?
    @Published var wlanSSID = ""
    @Published var guestSSID = ""
    @Published var devices: [SpeedportDevice] = []
    @Published var history: [SpeedportHistEntry] = []

    init() {
        super.init(id: "speedport", title: "Speedport", subtitle: "Telekom Speedport Smart 4 Typ B",
                   symbol: "server.rack", tint: Color(hex: 0xE20074))
    }

    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override var pollInterval: Double { Double(max(0, settings.pollInterval)) }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(SpeedportSettings.self, "speedport") { settings = s }
        if let h = SecureStore.loadCodable([SpeedportHistEntry].self, "speedport.history") { history = h }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "speedport")
    }

    var activeCount: Int { devices.filter { $0.active }.count }

    // ---- Hilfen (wie _fmt_rate / _dev_type / _dev_active) ----

    nonisolated static func fmtRate(_ v: String) -> String {
        guard let n = Int(v.trimmed) else { return v.isEmpty ? "-" : v }
        if n <= 0 { return "-" }
        if n >= 1000 { return String(format: "%.0f Mbit/s", Double(n) / 1000.0) }
        return "\(n) kbit/s"
    }

    nonisolated static func devType(_ d: [String: Any]) -> String {
        let t = SpeedportClient.str(d["mdevice_type"] ?? d["type"]).lowercased()
        let m = ["lan": "LAN", "wlan": "WLAN 2,4 GHz", "wlan5": "WLAN 5 GHz",
                 "0": "LAN", "1": "WLAN 2,4 GHz", "2": "WLAN 5 GHz"]
        if let n = Int(t) { return m[String(n % 3)] ?? t }
        return m[t] ?? t
    }

    nonisolated static func devActive(_ d: [String: Any]) -> Bool {
        let v = SpeedportClient.str(d["mdevice_connected"] ?? d["connected"]).trimmed.lowercased()
        return ["1", "true", "online", "connected", "ja", "yes"].contains(v)
    }

    nonisolated static func first(_ d: [String: Any], _ names: [String]) -> String {
        for n in names {
            for k in [n, "mdevice_" + n] {
                let v = SpeedportClient.str(d[k])
                if !v.isEmpty { return v }
            }
        }
        return ""
    }

    // ---- Abfrage (wie _fetch) ----

    override func refresh() async {
        await refreshSafely {
            do {
                try await self.poll()
            } catch {
                if !(error is CancellationError) {
                    self.histAdd(status: nil, err: DeviceModel.describe(error))
                }
                throw error
            }
        }
    }

    private func poll() async throws {
        let c = try SpeedportClient(host: settings.ip)
        let pw = settings.password
        // 1) Status (ohne Anmeldung)
        var status: [String: Any] = [:]
        var statusErr: Error?
        do {
            status = try await c.status()
        } catch {
            statusErr = error
        }
        // 2) Geraeteliste ohne Login (Default-Key)
        var raw: [[String: Any]] = (try? await c.devices(auth: false, sorted: true)) ?? []
        if raw.isEmpty { raw = (try? await c.devices(auth: false, sorted: false)) ?? [] }
        if statusErr != nil && raw.isEmpty, let e = statusErr { throw e }
        // 3) leer -> einmal anmelden, mit Login-Key holen + externe IP
        var ip: [String: Any] = [:]
        if raw.isEmpty && !pw.isEmpty {
            do {
                try await c.login(pw)
                raw = (try? await c.devices(auth: false, sorted: true)) ?? []
                if raw.isEmpty { raw = (try? await c.devices(auth: true, sorted: false)) ?? [] }
                ip = (try? await c.ipData()) ?? [:]
            } catch {
                addLog("Login: \(DeviceModel.describe(error))", error: true)
            }
        }
        // 4) Werte einsammeln (sp.get: erst Status, dann IP-Daten)
        func g(_ k: String) -> String {
            let s = SpeedportClient.str(status[k])
            if !s.isEmpty || status[k] != nil { return s }
            return SpeedportClient.str(ip[k])
        }
        let name = g("device_name").isEmpty ? g("hardware_version") : g("device_name")
        let fw = g("firmware_version")
        let st: [String: String] = [
            "onlinestatus": g("onlinestatus"),
            "public_ip": g("public_ip_v4"),
            "uptime": g("inet_uptime"),
            "dsl_down": g("dsl_downstream"),
            "dsl_up": g("dsl_upstream"),
            "inet_down": g("inet_download"),
            "inet_up": g("inet_upload")
        ]
        // Geraete normalisieren und sortieren (aktiv zuerst, dann Name)
        var norm: [SpeedportDevice] = []
        for (i, d) in raw.enumerated() {
            let mac = SpeedportModel.first(d, ["mac", "macaddress", "physaddress"])
            norm.append(SpeedportDevice(id: "\(i)-\(mac)",
                                        name: SpeedportModel.first(d, ["name", "hostname", "devicename"]),
                                        ip: SpeedportModel.first(d, ["ipv4", "ip", "ipaddress"]),
                                        mac: mac,
                                        typ: SpeedportModel.devType(d),
                                        active: SpeedportModel.devActive(d)))
        }
        norm.sort { a, b in
            if a.active != b.active { return a.active }
            return a.name.lowercased() < b.name.lowercased()
        }
        devices = norm
        modelInfo = (name + "  " + fw).trimmed
        online = st["onlinestatus"] ?? ""
        publicIP = st["public_ip"] ?? ""
        let upt = st["uptime"] ?? ""
        uptime = upt.replacingOccurrences(of: "T", with: " ")
        down = SpeedportModel.fmtRate(SpeedportModel.pick(st["dsl_down"], st["inet_down"]))
        up = SpeedportModel.fmtRate(SpeedportModel.pick(st["dsl_up"], st["inet_up"]))
        let uw = g("use_wlan")
        wlanOn = uw.isEmpty ? nil : (Int(uw) ?? 0) != 0
        let gw = g("wlan_guest_active")
        guestOn = gw.isEmpty ? nil : (Int(gw) ?? 0) != 0
        wlanSSID = g("wlan_ssid")
        guestSSID = g("wlan_guest_ssid")
        let on = online.isEmpty ? "Verbunden" : online
        summary = "\(on) - \(activeCount)/\(norm.count) verbunden"
        histAdd(status: st, err: nil)
    }

    /// Python: status.get("dsl_down") or status.get("inet_down")
    nonisolated static func pick(_ a: String?, _ b: String?) -> String {
        if let a = a, !a.isEmpty { return a }
        return b ?? ""
    }

    // ---- Aktionen (wie on_action) ----

    func run(_ action: SpeedportAction) {
        perform("Aktion '\(action.label)' ausgeführt") {
            try await self.doRun(action)
        }
    }

    private func doRun(_ action: SpeedportAction) async throws {
        let pw = settings.password
        guard !pw.isEmpty else { throw NetError.protocolError("Gerätepasswort fehlt (Einstellungen)") }
        let c = try SpeedportClient(host: settings.ip)
        _ = try? await c.status()
        do {
            try await c.login(pw)
        } catch {
            throw NetError.protocolError("Login fehlgeschlagen - Aktion braucht Anmeldung (\(DeviceModel.describe(error)))")
        }
        switch action {
        case .wifiOn: try await c.setWifi(true, guest: false)
        case .wifiOff: try await c.setWifi(false, guest: false)
        case .guestOn: try await c.setWifi(true, guest: true)
        case .guestOff: try await c.setWifi(false, guest: true)
        case .reconnect: try await c.reconnect()
        case .reboot: try await c.reboot()
        }
        if action != .reboot {
            Task {
                await pause(1.5)
                await self.refresh()
            }
        }
    }

    // ---- Verbindungs-Historie (Ereignisse + 15-min-Stuetzpunkte) ----

    private static let tsFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return f
    }()

    private func histAdd(status: [String: String]?, err: String?) {
        let now = Date()
        let last = history.last
        var e = SpeedportHistEntry()
        e.date = now
        e.t = SpeedportModel.tsFormatter.string(from: now)
        if let err = err {
            e.ev = "Poll-Fehler: \(err)"
        } else if let s = status {
            let on = s["onlinestatus"] ?? ""
            e.online = on.isEmpty ? "-" : on
            e.down = SpeedportModel.fmtRate(SpeedportModel.pick(s["dsl_down"], s["inet_down"]))
            e.up = SpeedportModel.fmtRate(SpeedportModel.pick(s["dsl_up"], s["inet_up"]))
            let ext = s["public_ip"] ?? ""
            e.ext = ext.isEmpty ? "-" : ext
            e.uptime = s["uptime"] ?? ""
            var evs: [String] = []
            if let l = last {
                if !["-", ""].contains(l.ext) && e.ext != l.ext { evs.append("Externe IP gewechselt (\(l.ext))") }
                if !l.uptime.isEmpty && !e.uptime.isEmpty && e.uptime != l.uptime { evs.append("Neu verbunden (Reconnect)") }
                if e.online != l.online { evs.append("Status: \(l.online) -> \(e.online)") }
                if (l.down != e.down || l.up != e.up) && l.down != "-" { evs.append("Sync-Rate geändert") }
            } else {
                evs.append("Start Aufzeichnung")
            }
            e.ev = evs.joined(separator: ", ")
        }
        var keep = !e.ev.isEmpty || last == nil
        if !keep, let l = last {
            keep = now.timeIntervalSince(l.date) >= 900
        }
        guard keep else { return }
        history.append(e)
        if history.count > SpeedportModel.histMax {
            history.removeFirst(history.count - SpeedportModel.histMax)
        }
        SecureStore.saveCodable(history, "speedport.history")
    }

    func clearHistory() {
        history = []
        SecureStore.saveCodable(history, "speedport.history")
    }

    var devicesCSV: String {
        var lines = ["#;Verbunden;Name;IP-Adresse;MAC-Adresse;Typ"]
        for (i, d) in devices.enumerated() {
            lines.append("\(i + 1);\(d.active ? "JA" : "NEIN");\(d.name);\(d.ip);\(d.mac);\(d.typ)")
        }
        return lines.joined(separator: "\n")
    }

    var historyCSV: String {
        var lines = ["Zeit;Internet;Downstream;Upstream;Externe IP;Verbunden seit;Ereignis"]
        for e in history {
            lines.append("\(e.t);\(e.online);\(e.down);\(e.up);\(e.ext);\(e.uptime);\(e.ev)")
        }
        return lines.joined(separator: "\n")
    }

    // ---- Demo (Start mit -demo, ohne Netzwerk) ----
    override func loadDemo() {
        settings.ip = "192.168.1.2"
        settings.password = "demo"
        modelInfo = "Speedport Smart 4 Typ B  010139.4.8.001.0"
        online = "online"
        publicIP = "84.152.37.118"
        uptime = "2026-11-09 06:14:22"
        down = "250 Mbit/s"
        up = "40 Mbit/s"
        wlanOn = true
        guestOn = false
        wlanSSID = "SP-Studio"
        guestSSID = "SP-Gast"
        devices = [
            SpeedportDevice(id: "0-3C:A6:2F:11:22:33", name: "fritz.box", ip: "192.168.1.1",
                            mac: "3C:A6:2F:11:22:33", typ: "LAN", active: true),
            SpeedportDevice(id: "1-A8:5E:45:66:77:88", name: "Studio-PC", ip: "192.168.1.20",
                            mac: "A8:5E:45:66:77:88", typ: "LAN", active: true),
            SpeedportDevice(id: "2-F0:18:98:12:34:56", name: "iPhone-Studio", ip: "192.168.1.31",
                            mac: "F0:18:98:12:34:56", typ: "WLAN 5 GHz", active: true),
            SpeedportDevice(id: "3-64:EB:8C:AA:BB:CC", name: "EPSON-WF7830", ip: "192.168.1.154",
                            mac: "64:EB:8C:AA:BB:CC", typ: "WLAN 2,4 GHz", active: true),
            SpeedportDevice(id: "4-DC:A6:32:01:02:03", name: "MacBook-Studio", ip: "192.168.1.35",
                            mac: "DC:A6:32:01:02:03", typ: "WLAN 5 GHz", active: false),
        ]
        func h(_ t: String, _ ev: String) -> SpeedportHistEntry {
            var e = SpeedportHistEntry()
            e.t = t
            e.online = "online"
            e.down = "250 Mbit/s"
            e.up = "40 Mbit/s"
            e.ext = "84.152.37.118"
            e.uptime = "2026-11-09T06:14:22"
            e.ev = ev
            return e
        }
        history = [
            h("2026-11-12 08:00:03", "Start Aufzeichnung"),
            h("2026-11-12 08:15:04", ""),
            h("2026-11-12 08:30:04", ""),
        ]
        summary = "online - \(activeCount)/\(devices.count) verbunden"
    }
}

// ---------------------------------------------------------------------------
// Ansicht
// ---------------------------------------------------------------------------
struct SpeedportView: View {
    @ObservedObject var model: SpeedportModel
    @State private var confirmReboot = false
    @State private var confirmClear = false
    @State private var showHistory = false

    var body: some View {
        DevicePage(model: model, settings: { SpeedportSettingsView(model: model) }) {
            Section("Status / Internet") {
                ValueRow(label: "Internet", value: dash(model.online), symbol: "globe",
                         valueColor: model.online.lowercased() == "online" ? .green : .secondary)
                ValueRow(label: "Externe IP", value: dash(model.publicIP), symbol: "network")
                ValueRow(label: "Verbunden seit", value: dash(model.uptime), symbol: "clock")
                ValueRow(label: "Downstream", value: dash(model.down), symbol: "arrow.down.circle")
                ValueRow(label: "Upstream", value: dash(model.up), symbol: "arrow.up.circle")
                ValueRow(label: "Modell/Firmware", value: dash(model.modelInfo), symbol: "server.rack")
            }
            Section {
                SpeedportWLANRow(title: "WLAN", ssid: model.wlanSSID, state: model.wlanOn, symbol: "wifi")
                SpeedportWLANRow(title: "Gast-WLAN", ssid: model.guestSSID, state: model.guestOn, symbol: "person.2.wave.2")
                TileGrid(columns: 2) {
                    ActionTile(title: "WLAN an", symbol: "wifi", tint: .green,
                               active: model.wlanOn == true, disabled: model.busy) { model.run(.wifiOn) }
                    ActionTile(title: "WLAN aus", symbol: "wifi.slash", tint: .gray,
                               active: model.wlanOn == false, disabled: model.busy) { model.run(.wifiOff) }
                    ActionTile(title: "Gast-WLAN an", symbol: "person.2.wave.2", tint: .green,
                               active: model.guestOn == true, disabled: model.busy) { model.run(.guestOn) }
                    ActionTile(title: "Gast-WLAN aus", symbol: "person.2.slash", tint: .gray,
                               active: model.guestOn == false, disabled: model.busy) { model.run(.guestOff) }
                }
            } header: {
                Text("WLAN")
            } footer: {
                Text("Schalten braucht das Gerätepasswort (Anmeldung am Speedport).")
            }
            Section("Aktionen") {
                TileGrid(columns: 3) {
                    ActionTile(title: "Aktualisieren", symbol: "arrow.clockwise", tint: .blue,
                               disabled: model.busy) {
                        Task { await model.refresh() }
                    }
                    ActionTile(title: "Reconnect", symbol: "arrow.triangle.2.circlepath", tint: .orange,
                               disabled: model.busy) {
                        model.run(.reconnect)
                    }
                    ActionTile(title: "Neustart", symbol: "restart.circle", tint: .red,
                               disabled: model.busy) {
                        confirmReboot = true
                    }
                }
            }
            Section {
                if model.devices.isEmpty {
                    Text("Keine Geräte gelesen").foregroundStyle(.secondary).font(.footnote)
                }
                ForEach(model.devices) { d in
                    SpeedportDeviceRow(device: d)
                }
                if !model.devices.isEmpty {
                    ShareLink(item: model.devicesCSV) {
                        Label("Liste exportieren (CSV)", systemImage: "square.and.arrow.up")
                    }
                }
            } header: {
                Text("Verbundene Geräte (\(model.activeCount) verbunden / \(model.devices.count) gesamt)")
            }
            Section {
                DisclosureGroup(isExpanded: $showHistory) {
                    if model.history.isEmpty {
                        Text("Noch keine Einträge").foregroundStyle(.secondary).font(.footnote)
                    }
                    ForEach(Array(model.history.suffix(100).reversed())) { e in
                        SpeedportHistRow(entry: e)
                    }
                    if !model.history.isEmpty {
                        ShareLink(item: model.historyCSV) {
                            Label("Historie exportieren (CSV)", systemImage: "square.and.arrow.up")
                        }
                        Button(role: .destructive) {
                            confirmClear = true
                        } label: {
                            Label("Historie leeren", systemImage: "trash")
                        }
                    }
                } label: {
                    Label("Verbindungs-Historie (\(model.history.count))", systemImage: "clock.arrow.circlepath")
                }
            } footer: {
                Text("Ereignisse (neue IP, Reconnect, Statuswechsel, Fehler) und alle 15 Minuten ein Stützpunkt.")
            }
        }
        .alert("Speedport wirklich neu starten?", isPresented: $confirmReboot) {
            Button("Neu starten", role: .destructive) { model.run(.reboot) }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Alle Verbindungen brechen ab.")
        }
        .alert("Verbindungs-Historie wirklich löschen?", isPresented: $confirmClear) {
            Button("Löschen", role: .destructive) { model.clearHistory() }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    private func dash(_ s: String) -> String { s.isEmpty ? "-" : s }
}

struct SpeedportWLANRow: View {
    let title: String
    let ssid: String
    let state: Bool?
    let symbol: String

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Label(title, systemImage: symbol)
                if !ssid.isEmpty {
                    Text(ssid).font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
            Text(stateText).foregroundStyle(state == true ? Color.green : Color.secondary)
        }
    }

    private var stateText: String {
        guard let s = state else { return "-" }
        return s ? "An" : "Aus"
    }
}

struct SpeedportDeviceRow: View {
    let device: SpeedportDevice

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(device.active ? Color.green : Color.gray.opacity(0.5))
                .frame(width: 9, height: 9)
                .padding(.top, 6)
            VStack(alignment: .leading, spacing: 2) {
                Text(device.name.isEmpty ? "(ohne Namen)" : device.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(device.active ? Color.primary : Color.secondary)
                Text(detailLine).font(.caption).foregroundStyle(.secondary)
                Text(device.mac).font(.caption2.monospaced()).foregroundStyle(.secondary)
            }
        }
        .textSelection(.enabled)
    }

    private var detailLine: String {
        var parts: [String] = []
        if !device.ip.isEmpty { parts.append(device.ip) }
        if !device.typ.isEmpty { parts.append(device.typ) }
        return parts.isEmpty ? "-" : parts.joined(separator: " · ")
    }
}

struct SpeedportHistRow: View {
    let entry: SpeedportHistEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(entry.t).font(.caption.monospaced())
                Spacer()
                Text(entry.online).font(.caption).foregroundStyle(entry.online.lowercased() == "online" ? Color.green : Color.secondary)
            }
            Text("\(entry.down) / \(entry.up) - \(entry.ext)").font(.caption2).foregroundStyle(.secondary)
            if !entry.ev.isEmpty {
                Text(entry.ev).font(.caption).foregroundStyle(entry.ev.hasPrefix("Poll-Fehler") ? Color.red : Color.primary)
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct SpeedportSettingsView: View {
    @ObservedObject var model: SpeedportModel
    @State private var s: SpeedportSettings

    init(model: SpeedportModel) {
        self.model = model
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "Speedport", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "IP-Adresse", text: $s.ip, placeholder: "192.168.0.1", keyboard: .URL)
                FieldRow(label: "Gerätepasswort", text: $s.password, placeholder: "Kennwort", secure: true)
            } header: {
                Text("Verbindung")
            } footer: {
                Text("Status und Geräteliste gehen ohne Anmeldung. Externe IP und alle Schaltaktionen brauchen das Gerätepasswort (Rückseite des Speedport).")
            }
            Section {
                FieldRow(label: "Aktualisieren (s)", text: intBinding($s.pollInterval), placeholder: "30", keyboard: .numberPad)
            } footer: {
                Text("0 = keine automatische Aktualisierung")
            }
        }
    }
}
