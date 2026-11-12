// ===========================================================================
//  Fritz.swift - Studio Control iOS - AVM Fritz!Box 3272 (TR-064 SOAP)
//  Autor: T. Pfeiffer
//
//  Port des Python-Moduls FritzboxModule (fritzconnection):
//    - Beschreibungen igddesc.xml + tr64desc.xml (Port 49000) lesen
//      -> Dienstname (serviceId-Ende) -> serviceType + controlURL
//    - SOAP-POST exakt wie fritzconnection/core/soaper.py (Envelope, Header
//      "soapaction", "content-type", "charset"), Digest-Auth ueber HTTPClient
//    - Benutzer leer -> "dslf-config"; ab Fritz!OS 7.24 letzter angemeldeter
//      Benutzer aus LANConfigSecurity1/X_AVM-DE_GetUserList (wie _reset_user)
//  Status: Modell, Firmware, WAN-Status, Uptime, externe IP, Link-Raten,
//          WLAN 1/2/3 (2,4 GHz / 5 GHz / Gast), Hosts-Liste
//  Aktionen: WLAN an/aus, Reconnect, Neustart, Portfreigaben (Liste/Anlegen/Loeschen)
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct FritzSettings: Codable {
    var ip: String = "192.168.1.1"
    var user: String = ""
    var password: String = ""
    var pollInterval: Int = 30

    enum CodingKeys: String, CodingKey {
        case ip, user, password, pollInterval
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ip = try c.decodeIfPresent(String.self, forKey: .ip) ?? "192.168.1.1"
        user = try c.decodeIfPresent(String.self, forKey: .user) ?? ""
        password = try c.decodeIfPresent(String.self, forKey: .password) ?? ""
        pollInterval = try c.decodeIfPresent(Int.self, forKey: .pollInterval) ?? 30
    }
}

// ---------------------------------------------------------------------------
// Datentypen
// ---------------------------------------------------------------------------
struct FritzHost: Identifiable, Hashable {
    let id: String
    var name: String
    var ip: String
    var mac: String
    var active: Bool
    var iface: String
    var speed: String
}

struct FritzPortMapping: Identifiable, Hashable {
    let id: Int
    var enabled: Bool
    var proto: String
    var extPort: String
    var intPort: String
    var client: String
    var desc: String
    var remoteHost: String
}

struct FritzWLANState: Hashable {
    var enabled: Bool?
    var ssid: String
}

// ---------------------------------------------------------------------------
// XML-Hilfen
// ---------------------------------------------------------------------------
struct FritzService {
    var serviceType = ""
    var serviceId = ""
    var controlURL = ""
    /// wie fritzconnection: letzter Teil der serviceId nach ':'
    var name: String { serviceId.components(separatedBy: ":").last ?? "" }
}

/// Liest igddesc.xml / tr64desc.xml (Dienste, Modellname, Systemversion).
final class FritzDescParser: NSObject, XMLParserDelegate {
    var services: [(String, FritzService)] = []
    var modelName: String?
    var sysMinor = ""
    var sysPatch = ""
    var sysDisplay = ""
    private var stack: [String] = []
    private var text = ""
    private var cur: FritzService?

    static func parse(_ data: Data) -> FritzDescParser? {
        let p = FritzDescParser()
        let x = XMLParser(data: data)
        x.delegate = p
        guard x.parse() else { return nil }
        return p
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?, attributes attributeDict: [String: String] = [:]) {
        stack.append(elementName)
        text = ""
        if elementName == "service" { cur = FritzService() }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        text += string
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let parent = stack.count >= 2 ? stack[stack.count - 2] : ""
        switch elementName {
        case "serviceType": cur?.serviceType = t
        case "serviceId": cur?.serviceId = t
        case "controlURL": cur?.controlURL = t
        case "service":
            if let s = cur, !s.name.isEmpty { services.append((s.name, s)) }
            cur = nil
        case "modelName":
            if modelName == nil && parent == "device" { modelName = t }
        case "Minor":
            if parent == "systemVersion" { sysMinor = t }
        case "Patch":
            if parent == "systemVersion" { sysPatch = t }
        case "Display":
            if parent == "systemVersion" { sysDisplay = t }
        default:
            break
        }
        if !stack.isEmpty { stack.removeLast() }
        text = ""
    }
}

/// Sammelt alle Blatt-Elemente einer SOAP-Antwort (Name ohne Praefix -> Text).
final class FritzLeafParser: NSObject, XMLParserDelegate {
    var values: [String: String] = [:]
    var lastUser: String?
    private var text = ""
    private var childSeen: [Bool] = []
    private var userIsLast = false

    static func parse(_ data: Data) -> FritzLeafParser {
        let p = FritzLeafParser()
        let x = XMLParser(data: data)
        x.delegate = p
        _ = x.parse()
        return p
    }

    static func local(_ name: String) -> String {
        if let i = name.lastIndex(of: ":") { return String(name[name.index(after: i)...]) }
        return name
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?, attributes attributeDict: [String: String] = [:]) {
        if !childSeen.isEmpty { childSeen[childSeen.count - 1] = true }
        childSeen.append(false)
        text = ""
        if FritzLeafParser.local(elementName) == "Username" {
            userIsLast = (attributeDict["last_user"] == "1")
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        text += string
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?,
                qualifiedName qName: String?) {
        let hadChild = childSeen.popLast() ?? false
        let name = FritzLeafParser.local(elementName)
        if !hadChild {
            values[name] = text
            if name == "Username" && userIsLast && lastUser == nil { lastUser = text }
        }
        text = ""
    }
}

// ---------------------------------------------------------------------------
// TR-064 Client (Port von fritzconnection: FritzConnection + Soaper)
// ---------------------------------------------------------------------------
final class FritzTR064Client {
    static let tcpPort = 49000
    static let defaultUser = "dslf-config"     // fuer Fritz!OS < 7.24
    static let wanServices = ["WANPPPConnection1", "WANIPConnection1"]

    let base: String            // "http://ip:49000"
    let http: HTTPClient
    let password: String
    private(set) var user: String
    private(set) var services: [String: FritzService] = [:]
    private(set) var modelName = ""
    private(set) var firmware = ""
    private(set) var systemVersion = ""
    private(set) var loaded = false
    let timeout: TimeInterval = 6

    init(address: String, user: String, password: String) throws {
        guard let u = makeURL(address, port: FritzTR064Client.tcpPort) else { throw NetError.badAddress(address) }
        base = u.absoluteString
        let usr = user.trimmed.isEmpty ? FritzTR064Client.defaultUser : user.trimmed
        self.user = usr
        self.password = password
        http = HTTPClient()
        if !password.isEmpty {
            http.user = usr
            http.password = password
        }
    }

    /// igddesc.xml + tr64desc.xml laden (wie _load_api_from_router). Fehlende
    /// igddesc ist egal, fehlende tr64desc -> "Zugriff fuer Anwendungen" aus.
    func load() async throws {
        var descs: [FritzDescParser] = []
        for file in ["igddesc.xml", "tr64desc.xml"] {
            guard let url = URL(string: "\(base)/\(file)") else { throw NetError.badAddress(base) }
            do {
                let (d, r) = try await http.request("GET", url, timeout: timeout)
                guard r.statusCode == 200, let p = FritzDescParser.parse(d) else {
                    throw NetError.http(r.statusCode, file)
                }
                descs.append(p)
            } catch {
                if file == "tr64desc.xml" {
                    if error is URLError { throw error }
                    throw NetError.protocolError("Fritz!Box: Zugriff fuer Anwendungen deaktiviert (Heimnetz > Netzwerk > Netzwerkeinstellungen: 'Zugriff fuer Anwendungen zulassen')")
                }
            }
        }
        var svc: [String: FritzService] = [:]
        for p in descs {
            for (name, s) in p.services { svc[name] = s }
        }
        services = svc
        modelName = descs.first?.modelName ?? ""
        for p in descs where !p.sysMinor.isEmpty && !p.sysPatch.isEmpty {
            systemVersion = "\(p.sysMinor).\(p.sysPatch)"
            firmware = p.sysDisplay
            break
        }
        loaded = true
        await resetUser()
    }

    /// Fritz!OS >= 7.24: ohne Benutzername den zuletzt angemeldeten Benutzer nehmen.
    private func resetUser() async {
        guard let v = Double(systemVersion), v >= 7.24, user == FritzTR064Client.defaultUser,
              !password.isEmpty else { return }
        guard let r = try? await call("LANConfigSecurity1", "X_AVM-DE_GetUserList"),
              let listXML = r["NewX_AVM-DE_UserList"] else { return }
        let p = FritzLeafParser.parse(Data(listXML.utf8))
        if let last = p.lastUser, !last.isEmpty {
            user = last
            http.user = last
        }
    }

    static func xmlEscape(_ s: String) -> String {
        var o = ""
        for ch in s {
            switch ch {
            case "&": o += "&amp;"
            case "<": o += "&lt;"
            case ">": o += "&gt;"
            case "\"": o += "&quot;"
            case "'": o += "&#x27;"
            default: o.append(ch)
            }
        }
        return o
    }

    static func normalize(_ name: String) -> String {
        var n = name
        if let last = n.last, last.isNumber { return n.replacingOccurrences(of: ":", with: "") }
        if n.hasSuffix(":") { n.removeLast() }
        return n + "1"
    }

    /// Eine TR-064-Aktion ausfuehren. Rueckgabe: Out-Argumente als Text.
    func call(_ serviceName: String, _ action: String, _ args: [(String, String)] = []) async throws -> [String: String] {
        let name = FritzTR064Client.normalize(serviceName)
        guard let svc = services[name] else { throw NetError.protocolError("Unbekannter Dienst: \(name)") }
        let argXML = args.map { "<\($0.0)>\(FritzTR064Client.xmlEscape($0.1))</\($0.0)>" }.joined()
        let body = "<s:Body><u:\(action) xmlns:u=\"\(svc.serviceType)\">\(argXML)</u:\(action)></s:Body>"
        let envelope = "<?xml version=\"1.0\" encoding=\"utf-8\"?><s:Envelope s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\" xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\">\(body)</s:Envelope>"
        guard let url = URL(string: base + svc.controlURL) else { throw NetError.badAddress(base + svc.controlURL) }
        let headers = ["soapaction": "\(svc.serviceType)#\(action)",
                       "content-type": "text/xml",
                       "charset": "utf-8"]
        let (d, r) = try await http.request("POST", url, headers: headers, body: Data(envelope.utf8), timeout: timeout)
        if r.statusCode != 200 {
            throw FritzTR064Client.soapError(d, status: r.statusCode)
        }
        return FritzLeafParser.parse(d).values
    }

    private static func soapError(_ d: Data, status: Int) -> Error {
        let text = String(decoding: d, as: UTF8.self)
        if text.lowercased().hasPrefix("<html") || text.isEmpty {
            if status == 401 { return NetError.protocolError("Anmeldung abgelehnt (Benutzer/Kennwort?)") }
            var detail = text.replacingOccurrences(of: "<[^>]*>", with: " ", options: .regularExpression)
            detail = detail.replacingOccurrences(of: " +", with: " ", options: .regularExpression).trimmed
            return NetError.http(status, detail.isEmpty ? "Fehler" : String(detail.prefix(160)))
        }
        let v = FritzLeafParser.parse(d).values
        let code = v["errorCode"] ?? ""
        let desc = v["errorDescription"] ?? ""
        if code == "606" { return NetError.protocolError("Aktion nicht erlaubt (606) - Benutzer/Kennwort bzw. Rechte pruefen") }
        if code == "401" { return NetError.protocolError("Aktion unbekannt (401)") }
        if code.isEmpty { return NetError.http(status, "SOAP-Fehler") }
        return NetError.protocolError("TR-064 Fehler \(code): \(desc)")
    }

    /// Erst PPP (DSL, wie 3272), dann IP-Connection; Fehler -> leeres Ergebnis.
    func wanCall(_ action: String, _ args: [(String, String)] = []) async -> [String: String] {
        for s in FritzTR064Client.wanServices {
            if let r = try? await call(s, action, args) { return r }
        }
        return [:]
    }

    /// Wie wanCall, wirft aber den letzten Fehler (fuer SET-Aktionen).
    func wanCallStrict(_ action: String, _ args: [(String, String)] = []) async throws -> [String: String] {
        var last: Error?
        for s in FritzTR064Client.wanServices {
            do {
                return try await call(s, action, args)
            } catch {
                last = error
            }
        }
        throw last ?? NetError.protocolError("keine WAN-Connection gefunden")
    }

    static func bool(_ s: String?) -> Bool {
        guard let s = s?.trimmed.lowercased() else { return false }
        return s == "1" || s == "true"
    }

    static func int(_ s: String?) -> Int {
        guard let s = s?.trimmed else { return 0 }
        return Int(s) ?? Int(Double(s) ?? 0)
    }

    // ---- Abfragen (wie _get_hosts / _get_wan / _get_wlan) ----

    func hosts() async throws -> [FritzHost] {
        var out: [FritzHost] = []
        var n = 0
        do {
            let r = try await call("Hosts1", "GetHostNumberOfEntries")
            n = FritzTR064Client.int(r["NewHostNumberOfEntries"])
        } catch {
            // Netzwerkfehler weiterreichen (Box nicht erreichbar), SOAP-Fehler -> 0
            if error is URLError { throw error }
            n = 0
        }
        if n > 0 {
            for i in 0..<n {
                guard let h = try? await call("Hosts1", "GetGenericHostEntry", [("NewIndex", String(i))]) else { continue }
                let ip = h["NewIPAddress"] ?? ""
                var d = FritzHost(id: "\(i)-\(h["NewMACAddress"] ?? "")",
                                  name: h["NewHostName"] ?? "", ip: ip,
                                  mac: h["NewMACAddress"] ?? "",
                                  active: FritzTR064Client.bool(h["NewActive"]),
                                  iface: h["NewInterfaceType"] ?? "", speed: "")
                if !ip.isEmpty && d.active {
                    if let x = try? await call("Hosts1", "X_AVM-DE_GetSpecificHostEntryByIP", [("NewIPAddress", ip)]) {
                        let it = x["NewX_AVM-DE_InterfaceType"] ?? ""
                        if !it.isEmpty { d.iface = it }
                        let spd = x["NewX_AVM-DE_Speed"] ?? ""
                        if !spd.isEmpty && spd != "0" { d.speed = spd + " Mbit/s" }
                    }
                }
                out.append(d)
            }
        }
        out.sort { a, b in
            if a.active != b.active { return a.active }
            return a.name.lowercased() < b.name.lowercased()
        }
        return out
    }

    struct Wan {
        var conn = ""
        var up = ""
        var ext = ""
        var down = ""
        var upl = ""
    }

    func wan() async -> Wan {
        var w = Wan()
        let s = await wanCall("GetStatusInfo")
        if !s.isEmpty {
            w.conn = s["NewConnectionStatus"] ?? ""
            w.up = FritzTR064Client.fmtUptime(FritzTR064Client.int(s["NewUptime"]))
        }
        let e = await wanCall("GetExternalIPAddress")
        if !e.isEmpty { w.ext = e["NewExternalIPAddress"] ?? "" }
        if let c = try? await call("WANCommonInterfaceConfig1", "GetCommonLinkProperties") {
            let dn = FritzTR064Client.int(c["NewLayer1DownstreamMaxBitRate"])
            let upr = FritzTR064Client.int(c["NewLayer1UpstreamMaxBitRate"])
            w.down = String(format: "%.1f Mbit/s", Double(dn) / 1e6)
            w.upl = String(format: "%.1f Mbit/s", Double(upr) / 1e6)
        }
        return w
    }

    func wlan(_ svc: String) async -> FritzWLANState {
        guard let r = try? await call(svc, "GetInfo") else { return FritzWLANState(enabled: nil, ssid: "") }
        return FritzWLANState(enabled: FritzTR064Client.bool(r["NewEnable"]), ssid: r["NewSSID"] ?? "")
    }

    static func fmtUptime(_ sec: Int) -> String {
        let d = sec / 86400
        var rem = sec % 86400
        let h = rem / 3600
        rem = rem % 3600
        let m = rem / 60
        if d > 0 { return String(format: "%dd %02dh %02dm", d, h, m) }
        return String(format: "%02dh %02dm", h, m)
    }

    // ---- Portfreigaben (TR-064 PortMapping) ----

    func portMappings() async throws -> [FritzPortMapping] {
        let cnt = await wanCall("GetPortMappingNumberOfEntries")
        let n = FritzTR064Client.int(cnt["NewPortMappingNumberOfEntries"])
        var out: [FritzPortMapping] = []
        if n > 0 {
            for i in 0..<n {
                guard let e = try? await wanCallStrict("GetGenericPortMappingEntry", [("NewPortMappingIndex", String(i))]) else { break }
                out.append(FritzPortMapping(id: i,
                                            enabled: FritzTR064Client.bool(e["NewEnabled"]),
                                            proto: e["NewProtocol"] ?? "",
                                            extPort: e["NewExternalPort"] ?? "",
                                            intPort: e["NewInternalPort"] ?? "",
                                            client: e["NewInternalClient"] ?? "",
                                            desc: e["NewPortMappingDescription"] ?? "",
                                            remoteHost: e["NewRemoteHost"] ?? ""))
            }
        }
        return out
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
/// Konstanten ausserhalb der MainActor-Klasse (aus jedem Kontext nutzbar).
enum FritzConst {
    static let wlanServices: [(String, String)] = [("WLANConfiguration1", "2,4 GHz"),
                                                   ("WLANConfiguration2", "5 GHz"),
                                                   ("WLANConfiguration3", "Gast")]

    static func looksLikeIP(_ s: String) -> Bool {
        let parts = s.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4 else { return false }
        for p in parts {
            guard !p.isEmpty, p.count <= 3, let v = Int(p), v >= 0, v <= 255 else { return false }
        }
        return true
    }
}

@MainActor
final class FritzModel: DeviceModel {

    @Published var settings = FritzSettings()
    @Published var modelName = ""
    @Published var firmware = ""
    @Published var wanConn = ""
    @Published var wanExt = ""
    @Published var wanUptime = ""
    @Published var wanDown = ""
    @Published var wanUp = ""
    @Published var wlan: [FritzWLANState] = Array(repeating: FritzWLANState(enabled: nil, ssid: ""), count: 3)
    @Published var hosts: [FritzHost] = []
    @Published var portMappings: [FritzPortMapping] = []
    @Published var portStatus = ""

    private var client: FritzTR064Client?
    private var clientKey = ""

    init() {
        super.init(id: "fritz", title: "Fritz!Box", subtitle: "AVM Fritz!Box 3272 (TR-064)",
                   symbol: "wifi.router", tint: Color(hex: 0xFF453A))
    }

    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override var pollInterval: Double { Double(max(0, settings.pollInterval)) }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(FritzSettings.self, "fritz") { settings = s }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "fritz")
        client = nil
    }

    override func disconnect() {
        // keine dauerhafte Verbindung (HTTP pro Aufruf)
    }

    var activeCount: Int { hosts.filter { $0.active }.count }

    /// Verbindung (Beschreibungen) bei Bedarf neu aufbauen - wie _conn_kw/_connect.
    private func connection() async throws -> FritzTR064Client {
        let key = "\(settings.ip.trimmed)|\(settings.user.trimmed)|\(settings.password)"
        if let c = client, clientKey == key, c.loaded { return c }
        let c = try FritzTR064Client(address: settings.ip, user: settings.user, password: settings.password)
        try await c.load()
        client = c
        clientKey = key
        return c
    }

    override func refresh() async {
        await refreshSafely {
            let c = try await self.connection()
            let h = try await c.hosts()
            let w = await c.wan()
            var states: [FritzWLANState] = []
            for (svc, _) in FritzConst.wlanServices {
                states.append(await c.wlan(svc))
            }
            self.modelName = c.modelName
            self.firmware = c.firmware
            self.hosts = h
            self.wanConn = w.conn
            self.wanExt = w.ext
            self.wanUptime = w.up
            self.wanDown = w.down
            self.wanUp = w.upl
            self.wlan = states
            let conn = w.conn.isEmpty ? "Verbunden" : w.conn
            self.summary = "\(conn) - \(self.activeCount)/\(h.count) Geräte aktiv"
        }
    }

    // ---- Aktionen ----

    func setWLAN(_ index: Int, on: Bool) {
        guard index >= 0 && index < FritzConst.wlanServices.count else { return }
        let svc = FritzConst.wlanServices[index].0
        let label = FritzConst.wlanServices[index].1
        if index < wlan.count { wlan[index].enabled = on }
        perform("WLAN \(label) -> \(on ? "AN" : "AUS")") {
            try await self.doSetWLAN(svc, on: on)
        }
    }

    private func doSetWLAN(_ svc: String, on: Bool) async throws {
        let c = try await connection()
        _ = try await c.call(svc, "SetEnable", [("NewEnable", on ? "1" : "0")])
        Task {
            await pause(1.2)
            await self.refresh()
        }
    }

    func reconnect() {
        perform("Reconnect ausgelöst - warte ...") {
            try await self.doReconnect()
        }
    }

    private func doReconnect() async throws {
        let c = try await connection()
        _ = try await c.wanCallStrict("ForceTermination")
        Task {
            await pause(8)
            await self.refresh()
        }
    }

    func reboot() {
        perform("Neustart ausgelöst - Box ist ca. 2 Min offline") {
            try await self.doReboot()
        }
    }

    private func doReboot() async throws {
        let c = try await connection()
        _ = try await c.call("DeviceConfig1", "Reboot")
    }

    // ---- Portfreigaben ----

    func loadPortMappings() async {
        portStatus = "Lese Freigaben ..."
        do {
            let c = try await connection()
            let list = try await c.portMappings()
            portMappings = list
            portStatus = "\(list.count) Freigabe(n)."
        } catch {
            portStatus = "Fehler: \(DeviceModel.describe(error))"
        }
    }

    func addPortMapping(proto: String, ext: Int, intPort: Int, client cli: String, enabled: Bool, desc: String) async {
        portStatus = "Lege Freigabe an ..."
        let d = desc.trimmed.isEmpty ? "StudioControlApp" : desc.trimmed
        let args: [(String, String)] = [("NewRemoteHost", ""),
                                        ("NewExternalPort", String(ext)),
                                        ("NewProtocol", proto),
                                        ("NewInternalPort", String(intPort)),
                                        ("NewInternalClient", cli),
                                        ("NewEnabled", enabled ? "1" : "0"),
                                        ("NewPortMappingDescription", d),
                                        ("NewLeaseDuration", "0")]
        do {
            let c = try await connection()
            _ = try await c.wanCallStrict("AddPortMapping", args)
            addLog("Portfreigabe \(proto) \(ext) -> \(cli):\(intPort) angelegt")
            Haptics.success()
            await loadPortMappings()
        } catch {
            portStatus = "Anlegen fehlgeschlagen: \(DeviceModel.describe(error))"
            Haptics.error()
        }
    }

    func deletePortMapping(_ e: FritzPortMapping) async {
        let args: [(String, String)] = [("NewRemoteHost", e.remoteHost),
                                        ("NewExternalPort", String(Int(e.extPort) ?? 0)),
                                        ("NewProtocol", e.proto)]
        do {
            let c = try await connection()
            _ = try await c.wanCallStrict("DeletePortMapping", args)
            addLog("Portfreigabe \(e.proto) \(e.extPort) gelöscht")
            Haptics.success()
            await loadPortMappings()
        } catch {
            portStatus = "Löschen fehlgeschlagen: \(DeviceModel.describe(error))"
            Haptics.error()
        }
    }

    /// Geraeteliste als CSV (Ersatz fuer den Excel-Export).
    var hostsCSV: String {
        var lines = ["#;Aktiv;Name;IP-Adresse;MAC-Adresse;Interface;Speed"]
        for (i, d) in hosts.enumerated() {
            lines.append("\(i + 1);\(d.active ? "JA" : "NEIN");\(d.name);\(d.ip);\(d.mac);\(d.iface);\(d.speed)")
        }
        return lines.joined(separator: "\n")
    }

    // ---- Demo (Start mit -demo, ohne Netzwerk) ----
    override func loadDemo() {
        settings.ip = "192.168.1.1"
        settings.user = "studio"
        settings.password = "demo"
        modelName = "FRITZ!Box 3272"
        firmware = "105.06.85"
        wanConn = "Connected"
        wanExt = "84.152.37.118"
        wanUptime = "3d 04h 12m"
        wanDown = "250.0 Mbit/s"
        wanUp = "40.0 Mbit/s"
        wlan = [
            FritzWLANState(enabled: true, ssid: "Studio-WLAN"),
            FritzWLANState(enabled: true, ssid: "Studio-WLAN-5G"),
            FritzWLANState(enabled: false, ssid: "Studio-Gast"),
        ]
        hosts = [
            FritzHost(id: "0-A8:5E:45:66:77:88", name: "Studio-PC", ip: "192.168.1.20",
                      mac: "A8:5E:45:66:77:88", active: true, iface: "Ethernet", speed: "1000 Mbit/s"),
            FritzHost(id: "1-F0:18:98:12:34:56", name: "iPhone-Studio", ip: "192.168.1.31",
                      mac: "F0:18:98:12:34:56", active: true, iface: "802.11", speed: "390 Mbit/s"),
            FritzHost(id: "2-00:10:7F:A1:22:01", name: "TSW-770", ip: "192.168.1.110",
                      mac: "00:10:7F:A1:22:01", active: true, iface: "Ethernet", speed: "1000 Mbit/s"),
            FritzHost(id: "3-00:04:A5:C3:10:22", name: "ClickShare-CX30", ip: "192.168.1.100",
                      mac: "00:04:A5:C3:10:22", active: true, iface: "Ethernet", speed: "1000 Mbit/s"),
            FritzHost(id: "4-64:EB:8C:AA:BB:CC", name: "EPSON-WF7830", ip: "192.168.1.154",
                      mac: "64:EB:8C:AA:BB:CC", active: true, iface: "802.11", speed: "72 Mbit/s"),
            FritzHost(id: "5-DC:A6:32:01:02:03", name: "MacBook-Studio", ip: "192.168.1.35",
                      mac: "DC:A6:32:01:02:03", active: false, iface: "802.11", speed: ""),
        ]
        portMappings = [
            FritzPortMapping(id: 0, enabled: true, proto: "TCP", extPort: "8443", intPort: "443",
                             client: "192.168.1.130", desc: "Q-SYS Remote", remoteHost: ""),
            FritzPortMapping(id: 1, enabled: false, proto: "UDP", extPort: "51820", intPort: "51820",
                             client: "192.168.1.20", desc: "WireGuard", remoteHost: ""),
        ]
        portStatus = "2 Freigabe(n)."
        summary = "Connected - \(activeCount)/\(hosts.count) Geräte aktiv"
    }
}

// ---------------------------------------------------------------------------
// Ansicht
// ---------------------------------------------------------------------------
struct FritzView: View {
    @ObservedObject var model: FritzModel
    @State private var confirmReconnect = false
    @State private var confirmReboot = false

    var body: some View {
        DevicePage(model: model, settings: { FritzSettingsView(model: model) }) {
            Section("Internet") {
                ValueRow(label: "Verbindung", value: dash(model.wanConn), symbol: "globe",
                         valueColor: model.wanConn == "Connected" ? .green : .secondary)
                ValueRow(label: "Externe IP", value: dash(model.wanExt), symbol: "network")
                ValueRow(label: "Uptime", value: dash(model.wanUptime), symbol: "clock")
                ValueRow(label: "Downstream", value: dash(model.wanDown), symbol: "arrow.down.circle")
                ValueRow(label: "Upstream", value: dash(model.wanUp), symbol: "arrow.up.circle")
            }
            Section("Gerät") {
                ValueRow(label: "Modell", value: dash(model.modelName), symbol: "wifi.router")
                ValueRow(label: "Firmware", value: dash(model.firmware), symbol: "cpu")
            }
            Section("WLAN") {
                ForEach(0..<FritzConst.wlanServices.count, id: \.self) { i in
                    FritzWLANRow(label: FritzConst.wlanServices[i].1,
                                 state: i < model.wlan.count ? model.wlan[i] : FritzWLANState(enabled: nil, ssid: ""),
                                 symbol: i == 2 ? "person.2.wave.2" : "wifi") { on in
                        model.setWLAN(i, on: on)
                    }
                }
            }
            Section("Aktionen") {
                TileGrid(columns: 3) {
                    ActionTile(title: "Aktualisieren", symbol: "arrow.clockwise", tint: .blue,
                               disabled: model.busy) {
                        Task { await model.refresh() }
                    }
                    ActionTile(title: "Reconnect (neue IP)", symbol: "arrow.triangle.2.circlepath", tint: .orange,
                               disabled: model.busy) {
                        confirmReconnect = true
                    }
                    ActionTile(title: "Neustart", symbol: "restart.circle", tint: .red,
                               disabled: model.busy) {
                        confirmReboot = true
                    }
                }
                NavigationLink {
                    FritzPortMapView(model: model)
                } label: {
                    Label("Portfreigaben", systemImage: "arrow.left.arrow.right.circle")
                }
            }
            Section {
                if model.hosts.isEmpty {
                    Text("Keine Geräte gelesen").foregroundStyle(.secondary).font(.footnote)
                }
                ForEach(model.hosts) { h in
                    FritzHostRow(host: h)
                }
                if !model.hosts.isEmpty {
                    ShareLink(item: model.hostsCSV) {
                        Label("Liste exportieren (CSV)", systemImage: "square.and.arrow.up")
                    }
                }
            } header: {
                Text("Verbundene Geräte (\(model.activeCount) aktiv / \(model.hosts.count) gesamt)")
            }
        }
        .alert("Internetverbindung neu aufbauen?", isPresented: $confirmReconnect) {
            Button("Reconnect", role: .destructive) { model.reconnect() }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Die Fritz!Box trennt die Internetverbindung und baut sie neu auf. Sie erhält dabei in der Regel eine neue öffentliche IP-Adresse.")
        }
        .alert("Fritz!Box wirklich neu starten?", isPresented: $confirmReboot) {
            Button("Neu starten", role: .destructive) { model.reboot() }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Alle Verbindungen brechen ab, die Box ist ca. 2 Minuten offline.")
        }
    }

    private func dash(_ s: String) -> String { s.isEmpty ? "-" : s }
}

struct FritzWLANRow: View {
    let label: String
    let state: FritzWLANState
    let symbol: String
    let set: (Bool) -> Void

    var body: some View {
        Toggle(isOn: Binding(get: { state.enabled ?? false }, set: { v in Haptics.tap(); set(v) })) {
            VStack(alignment: .leading, spacing: 2) {
                Label(label, systemImage: symbol)
                if state.enabled == nil {
                    Text("nicht verfügbar").font(.caption).foregroundStyle(.secondary)
                } else if !state.ssid.isEmpty {
                    Text(state.ssid).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .tint(.green)
        .disabled(state.enabled == nil)
    }
}

struct FritzHostRow: View {
    let host: FritzHost

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(host.active ? Color.green : Color.gray.opacity(0.5))
                .frame(width: 9, height: 9)
                .padding(.top, 6)
            VStack(alignment: .leading, spacing: 2) {
                Text(host.name.isEmpty ? "(ohne Namen)" : host.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(host.active ? Color.primary : Color.secondary)
                Text(detailLine).font(.caption).foregroundStyle(.secondary)
                Text(host.mac).font(.caption2.monospaced()).foregroundStyle(.secondary)
            }
        }
        .textSelection(.enabled)
    }

    private var detailLine: String {
        var parts: [String] = []
        if !host.ip.isEmpty { parts.append(host.ip) }
        if !host.iface.isEmpty { parts.append(host.iface) }
        if !host.speed.isEmpty { parts.append(host.speed) }
        return parts.isEmpty ? "-" : parts.joined(separator: " · ")
    }
}

// ---------------------------------------------------------------------------
// Portfreigaben
// ---------------------------------------------------------------------------
struct FritzPortMapView: View {
    @ObservedObject var model: FritzModel
    @State private var proto = "TCP"
    @State private var extPort = ""
    @State private var intPort = ""
    @State private var client = ""
    @State private var desc = "StudioControlApp"
    @State private var enabled = true
    @State private var pendingDelete: FritzPortMapping?
    @State private var showDelete = false
    @State private var inputError: String?

    var body: some View {
        List {
            Section {
                if model.portMappings.isEmpty {
                    Text("Keine Freigaben").foregroundStyle(.secondary).font(.footnote)
                }
                ForEach(model.portMappings) { e in
                    FritzPortRow(entry: e)
                        .swipeActions {
                            Button(role: .destructive) {
                                pendingDelete = e
                                showDelete = true
                            } label: {
                                Label("Löschen", systemImage: "trash")
                            }
                        }
                }
            } header: {
                Text("Freigaben")
            } footer: {
                Text(model.portStatus)
            }
            Section("Neue Freigabe") {
                Picker("Protokoll", selection: $proto) {
                    Text("TCP").tag("TCP")
                    Text("UDP").tag("UDP")
                }
                .pickerStyle(.segmented)
                FieldRow(label: "Ext. Port", text: $extPort, placeholder: "z.B. 8080", keyboard: .numberPad)
                FieldRow(label: "Int. Port", text: $intPort, placeholder: "wie extern", keyboard: .numberPad)
                FieldRow(label: "Ziel-IP", text: $client, placeholder: "192.168.1.20", keyboard: .decimalPad)
                FieldRow(label: "Beschreibung", text: $desc, placeholder: "StudioControlApp")
                Toggle("aktiv", isOn: $enabled)
                if let err = inputError {
                    Text(err).font(.footnote).foregroundStyle(.red)
                }
                Button {
                    add()
                } label: {
                    Label("Anlegen", systemImage: "plus.circle.fill")
                }
            }
            Section {
                Text("Freigaben für ANDERE Geräte per TR-064 erfordern in der Fritz!Box die Berechtigung „Änderungen der Sicherheitseinstellungen über UPnP gestatten“ bzw. einen Benutzer mit Rechten „FRITZ!Box Einstellungen“.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Portfreigaben")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    Task { await model.loadPortMappings() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .accessibilityLabel("Neu laden")
            }
        }
        .refreshable { await model.loadPortMappings() }
        .task { await model.loadPortMappings() }
        .alert("Freigabe wirklich löschen?", isPresented: $showDelete, presenting: pendingDelete) { e in
            Button("Löschen", role: .destructive) {
                Task { await model.deletePortMapping(e) }
            }
            Button("Abbrechen", role: .cancel) {}
        } message: { e in
            Text("\(e.proto) \(e.extPort) -> \(e.client):\(e.intPort)")
        }
    }

    private func add() {
        let e = Int(extPort.trimmed) ?? 0
        let i = intPort.trimmed.isEmpty ? e : (Int(intPort.trimmed) ?? 0)
        guard e >= 1 && e <= 65535 && i >= 1 && i <= 65535 else {
            inputError = "Ports 1..65535 eingeben."
            return
        }
        let cli = client.trimmed
        guard FritzConst.looksLikeIP(cli) else {
            inputError = "Gültige Ziel-IP eingeben."
            return
        }
        inputError = nil
        let p = proto
        let en = enabled
        let d = desc
        Task { await model.addPortMapping(proto: p, ext: e, intPort: i, client: cli, enabled: en, desc: d) }
    }
}

struct FritzPortRow: View {
    let entry: FritzPortMapping

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: entry.enabled ? "checkmark.circle.fill" : "xmark.circle")
                .foregroundStyle(entry.enabled ? Color.green : Color.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(entry.proto) \(entry.extPort) → \(entry.client):\(entry.intPort)")
                    .font(.subheadline.weight(.semibold))
                if !entry.desc.isEmpty {
                    Text(entry.desc).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct FritzSettingsView: View {
    @ObservedObject var model: FritzModel
    @State private var s: FritzSettings

    init(model: FritzModel) {
        self.model = model
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "Fritz!Box", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "IP-Adresse", text: $s.ip, placeholder: "192.168.1.1", keyboard: .URL)
                FieldRow(label: "Benutzer", text: $s.user, placeholder: "optional")
                FieldRow(label: "Passwort", text: $s.password, placeholder: "Kennwort", secure: true)
            } header: {
                Text("Verbindung (TR-064, Port 49000)")
            } footer: {
                Text("Benutzer leer = Standard (dslf-config bzw. zuletzt angemeldeter Benutzer ab Fritz!OS 7.24). In der Fritz!Box muss „Zugriff für Anwendungen zulassen“ aktiv sein.")
            }
            Section {
                FieldRow(label: "Aktualisieren (s)", text: intBinding($s.pollInterval), placeholder: "30", keyboard: .numberPad)
            } footer: {
                Text("0 = keine automatische Aktualisierung")
            }
        }
    }
}
