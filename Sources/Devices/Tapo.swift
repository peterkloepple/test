// ===========================================================================
//  Tapo.swift - Studio Control iOS - TP-Link Tapo Steckdosen (P100/P110/P115 ...)
//  Autor: T. Pfeiffer
//  v1.2.0 - Stand wie Studio Control App (Windows) v1.13.0:
//    - eine KLAP-Sitzung je Steckdose bleibt bestehen (kein Anmelden je Tippen)
//    - zwei Tapo-Konten + Kontowahl je Dose (Auto / Konto 1 / Konto 2)
//    - Zugangsdaten werden OHNE zusaetzliche Anmeldeversuche geprueft: aus der
//      einen Handshake1-Antwort wird lokal verglichen, welche Daten passen
//      (Konto 1, Konto 2, Schreibvarianten, Werkszugaenge)
//    - Sperrpause 45 s nach falschen Zugangsdaten / HTTP 403
//    - klare Ursachen: 403 = Drittanbieter-Kompatibilitaet, andere Zugangsdaten,
//      schlafender Webserver (wird per UDP 20002 geweckt), offline
//    - Diagnose je Dose und fuer alle (Modell, Verschluesselung, Konto-Kennung)
//    - kein Systemproxy fuer Zugriffe ins eigene Netz
//  Lokales KLAP-Protokoll (HTTP Port 80): handshake1/handshake2, Auth-Hash v1 (MD5)
//  und v2 (SHA1/SHA256), AES-CBC + SHA256-Signatur, Cookie TP_SESSIONID.
//  Netzsuche: Unicast-Sweep des eigenen /24 (TCP 80 offen -> KLAP-handshake1).
//  UDP-Broadcast-Suche ist auf iOS ohne Sonder-Entitlement nicht moeglich;
//  die gezielte UDP-Abfrage einer einzelnen Dose (Port 20002) geht.
// ===========================================================================
import Foundation
import SwiftUI
import Security

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct TapoPlug: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var name: String = ""
    var ip: String = ""
    var inScene: Bool = false
    /// "auto", "1" oder "2" (welches Tapo-Konto fuer diese Dose gilt)
    var konto: String = "auto"

    enum CodingKeys: String, CodingKey {
        case id, name, ip, inScene, konto
    }

    init(id: UUID = UUID(), name: String = "", ip: String = "", inScene: Bool = false, konto: String = "auto") {
        self.id = id
        self.name = name
        self.ip = ip
        self.inScene = inScene
        self.konto = konto
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? c.decodeIfPresent(UUID.self, forKey: .id)) ?? UUID()
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? ""
        ip = (try? c.decodeIfPresent(String.self, forKey: .ip)) ?? ""
        inScene = (try? c.decodeIfPresent(Bool.self, forKey: .inScene)) ?? false
        konto = (try? c.decodeIfPresent(String.self, forKey: .konto)) ?? "auto"
    }
}

struct TapoSettings: Codable {
    var email: String = ""
    var password: String = ""
    var email2: String = ""
    var password2: String = ""
    var plugs: [TapoPlug] = []
    var pollInterval: Int = 15

    enum CodingKeys: String, CodingKey {
        case email, password, email2, password2, plugs, pollInterval
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        email = (try? c.decodeIfPresent(String.self, forKey: .email)) ?? ""
        password = (try? c.decodeIfPresent(String.self, forKey: .password)) ?? ""
        email2 = (try? c.decodeIfPresent(String.self, forKey: .email2)) ?? ""
        password2 = (try? c.decodeIfPresent(String.self, forKey: .password2)) ?? ""
        plugs = (try? c.decodeIfPresent([TapoPlug].self, forKey: .plugs)) ?? []
        pollInterval = (try? c.decodeIfPresent(Int.self, forKey: .pollInterval)) ?? 15
    }
}

// ---------------------------------------------------------------------------
// Fehler (wie TapoError in der Windows-App)
// ---------------------------------------------------------------------------
enum TapoKind {
    case net, sleep, forbidden, auth, proto, session, dev
}

struct TapoError: LocalizedError {
    let text: String
    let kind: TapoKind

    init(_ text: String, _ kind: TapoKind = .proto) {
        self.text = text
        self.kind = kind
    }

    var errorDescription: String? { text }
}

func tapoIsCancel(_ error: Error) -> Bool {
    if error is CancellationError { return true }
    let ns = error as NSError
    return ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled
}

@MainActor
func tapoNetText(_ error: Error) -> String {
    let ns = error as NSError
    if ns.domain == NSURLErrorDomain {
        switch ns.code {
        case NSURLErrorTimedOut:
            return "keine Antwort (Dose aus, falsche IP oder anderes Netz)"
        case NSURLErrorCannotConnectToHost:
            return "Port 80 geschlossen (Dose schläft oder kein Tapo-Gerät)"
        case NSURLErrorNotConnectedToInternet, NSURLErrorNetworkConnectionLost, NSURLErrorCannotFindHost:
            return "Netz nicht erreichbar"
        default:
            break
        }
    }
    return DeviceModel.describe(error)
}

/// Kurztext + Hinweis fuer die Anzeige (wie _explain)
func tapoExplain(_ e: TapoError) -> (String, String) {
    switch e.kind {
    case .auth:
        return ("Zugang falsch", "Zugangsdaten passen nicht - „Diagnose“ tippen, Erklärung im Protokoll.")
    case .forbidden:
        return ("gesperrt (403)", "Drittanbieter-Kompatibilität in der Tapo-App einschalten - Erklärung im Protokoll.")
    case .net, .sleep:
        return ("offline", e.text)
    default:
        return ("Fehler", e.text)
    }
}

let tapoAuthLongText: String = "Diese Dose hat andere Zugangsdaten gespeichert als eingetragen. Prüfen: E-Mail und Passwort Zeichen für Zeichen wie in der Tapo-App; gehört die Dose zu einem anderen Konto, dieses als Konto 2 eintragen. Hilft das nicht: Dose in der Tapo-App entfernen, zurücksetzen (Knopf 5 s) und neu hinzufügen."

// ---------------------------------------------------------------------------
// Zugangsdaten-Kandidaten (wie tapo_candidates)
// ---------------------------------------------------------------------------
struct TapoCred {
    let label: String
    let user: String
    let pw: String
}

let tapoDefaultCreds: [TapoCred] = [
    TapoCred(label: "Tapo-Werkszugang", user: "test@tp-link.net", pw: "test"),
    TapoCred(label: "Kasa-Werkszugang", user: "kasa@tp-link.net", pw: "kasaSetup"),
    TapoCred(label: "leere Zugangsdaten", user: "", pw: "")
]

/// Sperrpause nach Zugangsdaten-Fehler (Sekunden)
let tapoAuthPause: TimeInterval = 45

func tapoCandidates(email: String, password: String, email2: String, password2: String, which: String) -> [TapoCred] {
    var out: [TapoCred] = []
    func add(_ name: String, _ u: String, _ p: String) {
        if u.isEmpty && p.isEmpty { return }
        out.append(TapoCred(label: name, user: u, pw: p))
        let us = u.trimmed
        let ps = p.trimmed
        if us != u || ps != p {
            out.append(TapoCred(label: name + " (ohne Leerzeichen)", user: us, pw: ps))
        }
        if us.lowercased() != us {
            out.append(TapoCred(label: name + " (E-Mail klein)", user: us.lowercased(), pw: ps))
        }
    }
    if which == "auto" || which == "1" { add("Konto 1", email, password) }
    if which == "auto" || which == "2" { add("Konto 2", email2, password2) }
    out.append(contentsOf: tapoDefaultCreds)
    return out
}

// ---------------------------------------------------------------------------
// KLAP-Bausteine
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Adresse
// ---------------------------------------------------------------------------
/// wie addr_clean: Schema, Pfad, Leerzeichen und '#' weg
func tapoCleanIP(_ s: String) -> String {
    var t = s.trimmed
    if let r = t.range(of: "://") { t = String(t[r.upperBound...]) }
    if let slash = t.firstIndex(of: "/") { t = String(t[..<slash]) }
    return t.trimmingCharacters(in: CharacterSet(charactersIn: "# \t\r\n"))
}

/// wie tapo_hostport: "192.168.0.5:8080" -> ("192.168.0.5", 8080), sonst Port 80
func tapoHostPort(_ ip: String) -> (String, Int) {
    let t = tapoCleanIP(ip)
    let parts = t.split(separator: ":", omittingEmptySubsequences: false)
    if parts.count == 2 {
        let h = String(parts[0])
        if let p = Int(parts[1]), p > 0, p < 65536 { return (h, p) }
        return (h, 80)
    }
    return (t, 80)
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

// ---------------------------------------------------------------------------
// Einzel-Abfrage per UDP 20002 (weckt auch den Webserver der Dose)
// ---------------------------------------------------------------------------
struct TapoDisco {
    var ip = ""
    var type = ""
    var model = ""
    var mac = ""
    var owner = ""
    var enc = ""
    var factory = false
    var tpap = false
}

let tapoLegacyQuery = Data([0x02, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
                            0x00, 0x00, 0x00, 0x00, 0x46, 0x3c, 0xb5, 0xd3])

func tapoCRC32(_ data: Data) -> UInt32 {
    var crc: UInt32 = 0xFFFFFFFF
    for byte in data {
        crc ^= UInt32(byte)
        for _ in 0..<8 {
            let mask: UInt32 = (crc & 1) == 1 ? 0xEDB88320 : 0
            crc = (crc >> 1) ^ mask
        }
    }
    return crc ^ 0xFFFFFFFF
}

private var tapoRSAPemCache: String?

/// Oeffentlicher RSA-1024-Schluessel als PEM (SubjectPublicKeyInfo), wie ihn die Tapo-App mitschickt.
func tapoRSAPem() -> String? {
    if let p = tapoRSAPemCache { return p }
    let attrs: [String: Any] = [
        kSecAttrKeyType as String: kSecAttrKeyTypeRSA,
        kSecAttrKeySizeInBits as String: 1024
    ]
    var err: Unmanaged<CFError>?
    guard let priv = SecKeyCreateRandomKey(attrs as CFDictionary, &err) else { return nil }
    guard let pub = SecKeyCopyPublicKey(priv) else { return nil }
    guard let cf = SecKeyCopyExternalRepresentation(pub, &err) else { return nil }
    let pkcs1 = cf as Data
    if pkcs1.count != 140 { return nil }
    // SubjectPublicKeyInfo-Kopf fuer RSA 1024 + PKCS#1-Schluessel
    var der = Data([0x30, 0x81, 0x9F, 0x30, 0x0D, 0x06, 0x09, 0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01,
                    0x05, 0x00, 0x03, 0x81, 0x8D, 0x00])
    der.append(pkcs1)
    let b64 = der.base64EncodedString(options: [.lineLength64Characters, .endLineWithLineFeed])
    let pem = "-----BEGIN PUBLIC KEY-----\n" + b64 + "\n-----END PUBLIC KEY-----\n"
    tapoRSAPemCache = pem
    return pem
}

/// Discovery-Paket wie die Tapo-App (mit RSA-Schluessel); ohne Schluessel das alte 16-Byte-Paket.
func tapoDiscoQuery() -> Data {
    guard let pem = tapoRSAPem() else { return tapoLegacyQuery }
    let obj: [String: Any] = ["params": ["rsa_key": pem]]
    guard let payload = try? JSONSerialization.data(withJSONObject: obj, options: [.withoutEscapingSlashes]) else {
        return tapoLegacyQuery
    }
    let n = payload.count
    var bytes: [UInt8] = [2, 0, 0, 1, UInt8((n >> 8) & 0xff), UInt8(n & 0xff), 17, 0]
    bytes.append(contentsOf: [UInt8](Crypto.random(4)))
    bytes.append(contentsOf: [0x5A, 0x6B, 0x7C, 0x8D])
    bytes.append(contentsOf: [UInt8](payload))
    let crc = tapoCRC32(Data(bytes))
    bytes[12] = UInt8((crc >> 24) & 0xff)
    bytes[13] = UInt8((crc >> 16) & 0xff)
    bytes[14] = UInt8((crc >> 8) & 0xff)
    bytes[15] = UInt8(crc & 0xff)
    return Data(bytes)
}

func tapoParseDiscovery(_ data: Data, _ src: String) -> TapoDisco? {
    guard data.count > 16 else { return nil }
    let payload = Data([UInt8](data)[16...])
    guard let obj = try? JSONSerialization.jsonObject(with: payload, options: []),
          let top = obj as? [String: Any] else { return nil }
    let res = (top["result"] as? [String: Any]) ?? top
    let dtype = (res["device_type"] as? String) ?? ""
    var model = (res["device_model"] as? String) ?? ""
    if model.isEmpty { model = (res["model"] as? String) ?? "" }
    if let paren = model.firstIndex(of: "(") { model = String(model[..<paren]) }
    model = model.trimmed
    if dtype.isEmpty && model.isEmpty { return nil }
    let sch = (res["mgt_encrypt_schm"] as? [String: Any]) ?? [:]
    var enc = (sch["encrypt_type"] as? String) ?? ""
    var tpap = false
    if let v = res["tpap"] {
        if let b = v as? Bool { tpap = b } else if !(v is NSNull) { tpap = true }
    }
    if tpap && enc.isEmpty { enc = "TPAP" }
    var d = TapoDisco()
    d.ip = (res["ip"] as? String) ?? src
    if d.ip.isEmpty { d.ip = src }
    d.type = dtype
    d.model = model
    d.mac = (res["mac"] as? String) ?? ""
    d.owner = (res["owner"] as? String) ?? ""
    d.enc = enc
    d.factory = (res["factory_default"] as? Bool) == true
    d.tpap = tpap
    return d
}

/// Einzelne Dose per UDP 20002 fragen (erst mit RSA-Schluessel, dann altes Paket).
func tapoDiscoverOne(_ host: String, timeout: TimeInterval = 1.5) async -> TapoDisco? {
    let queries: [Data] = [tapoDiscoQuery(), tapoLegacyQuery]
    let each = max(0.6, timeout / 2.0)
    for q in queries {
        if let d = try? await UDPExchange.request(host: host, port: 20002, payload: q, timeout: each, retries: 0),
           let info = tapoParseDiscovery(d, host) {
            return info
        }
    }
    return nil
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
    return dtype.isEmpty ? "Tapo-Gerät" : dtype
}

// ---------------------------------------------------------------------------
// Eine Steckdose: haelt die KLAP-Sitzung und meldet sich bei Bedarf neu an
// (KlapSession + TapoPlug aus der Windows-App in einer Klasse)
// ---------------------------------------------------------------------------
@MainActor
final class TapoLink {
    let ip: String
    let host: String
    let port: Int
    let timeout: TimeInterval
    private var http = HTTPClient()
    private var key = Data()
    private var iv12 = Data()
    private var sig28 = Data()
    private var seq: Int64 = 0
    private(set) var ready = false
    private(set) var expires = Date.distantPast
    private(set) var matched = ""
    private(set) var variant = ""
    var authBlockUntil = Date.distantPast
    var authError: TapoError?
    var disco: TapoDisco?
    var lastLog = ""
    var lastErr = ""
    private var locked = false

    init(ip: String, timeout: TimeInterval = 5) {
        self.ip = ip
        let hp = tapoHostPort(ip)
        self.host = hp.0
        self.port = hp.1
        self.timeout = timeout
        http.noProxy = true
    }

    /// Sitzung verwerfen (z.B. Zugangsdaten geaendert) - naechster Zugriff meldet neu an.
    func reset() {
        ready = false
        authBlockUntil = Date.distantPast
        authError = nil
    }

    /// URLSession freigeben (haelt sonst ihren Delegate fest -> Leck).
    func close() {
        ready = false
        http.session.finishTasksAndInvalidate()
        http = HTTPClient()
        http.noProxy = true
    }

    private func freshHTTP() {
        http.session.finishTasksAndInvalidate()
        http = HTTPClient()
        http.noProxy = true          // nie ueber einen Proxy ins eigene Netz
    }

    private func urlString(_ path: String) -> String {
        let portPart: String = port == 80 ? "" : ":" + String(port)
        return "http://" + host + portPart + path
    }

    private func post(_ path: String, _ body: Data) async throws -> (Int, Data, HTTPURLResponse) {
        guard let url = URL(string: urlString(path)) else {
            throw TapoError("ungültige Adresse \(ip)", .net)
        }
        do {
            let (d, r) = try await http.request("POST", url,
                                                headers: ["Content-Type": "application/octet-stream", "Accept": "*/*"],
                                                body: body, timeout: timeout)
            return (r.statusCode, d, r)
        } catch {
            if tapoIsCancel(error) { throw error }
            throw TapoError(tapoNetText(error), .net)
        }
    }

    /// TP_SESSIONID aus Set-Cookie sicher in den Cookie-Speicher uebernehmen.
    private func adoptSessionCookie(_ resp: HTTPURLResponse) {
        guard let base = URL(string: urlString("/")) else { return }
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

    /// TIMEOUT=<s> aus Set-Cookie (Standard 86400)
    private func cookieTimeout(_ resp: HTTPURLResponse) -> Int {
        guard let raw = resp.value(forHTTPHeaderField: "Set-Cookie"),
              let r = raw.range(of: "TIMEOUT=") else { return 86400 }
        var digits = ""
        for ch in raw[r.upperBound...] {
            if ch.isASCII && ch.isNumber { digits.append(ch) } else { break }
        }
        return Int(digits) ?? 86400
    }

    /// Es wird nur EINMAL angemeldet: welche Zugangsdaten passen, ergibt der lokale Vergleich.
    private func handshake(_ cands: [TapoCred]) async throws -> String {
        ready = false
        freshHTTP()
        let ls = Crypto.random(16)
        let (st, body, resp) = try await post("/app/handshake1", ls)
        if st == 403 {
            let m403: String = "Dose verweigert die lokale Anmeldung (HTTP 403). In der Tapo-App unter Ich > Drittanbieter-Dienste die „Drittanbieter-Kompatibilität“ einschalten, 1 Minute warten, dann erneut versuchen."
            throw TapoError(m403, .forbidden)
        }
        if st == 404 {
            throw TapoError("Dose kennt die KLAP-Anmeldung nicht (HTTP 404) - sehr alte Firmware oder kein Tapo-Gerät.", .proto)
        }
        guard st == 200, body.count >= 48 else {
            throw TapoError("Handshake1: unerwartete Antwort (HTTP \(st), \(body.count) Byte)", .proto)
        }
        adoptSessionCookie(resp)
        let b = [UInt8](body)
        let rs = Data(b[0..<16])
        let serverHash = Data(b[16..<48])

        var hitLabel = ""
        var hitHash = Data()
        var hitVer = 0
        var seen = Set<String>()
        for c in cands {
            let k = c.user + "\u{0}" + c.pw
            if seen.contains(k) { continue }
            seen.insert(k)
            let a1 = TapoKlap.authV1(c.user, c.pw)
            if Crypto.sha256(TapoKlap.cat(ls, a1)) == serverHash {
                hitLabel = c.label
                hitHash = a1
                hitVer = 1
                break
            }
            let a2 = TapoKlap.authV2(c.user, c.pw)
            if Crypto.sha256(TapoKlap.cat(ls, rs, a2)) == serverHash {
                hitLabel = c.label
                hitHash = a2
                hitVer = 2
                break
            }
        }
        if hitVer == 0 {
            let names = cands.map { $0.label }.joined(separator: ", ")
            throw TapoError("Zugangsdaten passen nicht zu dieser Dose (geprüft: \(names)).", .auth)
        }
        let hs2 = hitVer == 1 ? Crypto.sha256(TapoKlap.cat(rs, hitHash)) : Crypto.sha256(TapoKlap.cat(rs, ls, hitHash))
        let (st2, _, _) = try await post("/app/handshake2", hs2)
        if st2 == 403 {
            throw TapoError("Handshake2 abgewiesen (HTTP 403) - Drittanbieter-Kompatibilität in der Tapo-App prüfen.", .forbidden)
        }
        if st2 != 200 { throw TapoError("Handshake2: HTTP \(st2)", .proto) }

        key = Data(Crypto.sha256(TapoKlap.cat(Data("lsk".utf8), ls, rs, hitHash)).prefix(16))
        let fiv = [UInt8](Crypto.sha256(TapoKlap.cat(Data("iv".utf8), ls, rs, hitHash)))
        iv12 = Data(fiv[0..<12])
        let u = (UInt32(fiv[28]) << 24) | (UInt32(fiv[29]) << 16) | (UInt32(fiv[30]) << 8) | UInt32(fiv[31])
        seq = Int64(Int32(bitPattern: u))
        sig28 = Data(Crypto.sha256(TapoKlap.cat(Data("ldk".utf8), ls, rs, hitHash)).prefix(28))
        let life = max(60, cookieTimeout(resp) - 120)
        expires = Date().addingTimeInterval(TimeInterval(life))
        matched = hitLabel
        variant = "v\(hitVer)"
        ready = true
        return hitLabel
    }

    /// Verschluesselte Anfrage; liefert "result" der Antwort.
    private func request(_ json: String, _ what: String) async throws -> [String: Any] {
        if !ready || Date() > expires {
            ready = false
            throw TapoError("Sitzung abgelaufen", .session)
        }
        seq += 1
        let s = seq
        let iv = TapoKlap.cat(iv12, TapoKlap.packI32(s))
        guard let ct = try? Crypto.aesCBC(encrypt: true, key: key, iv: iv, data: Data(json.utf8)) else {
            ready = false
            throw TapoError("Verschlüsselung fehlgeschlagen", .session)
        }
        let sig = Crypto.sha256(TapoKlap.cat(sig28, TapoKlap.packI32(s), ct))
        let (st, body, _) = try await post("/app/request?seq=\(s)", TapoKlap.cat(sig, ct))
        if st != 200 {
            ready = false
            throw TapoError("Sitzung beendet (HTTP \(st))", .session)
        }
        if body.count <= 32 {
            ready = false
            throw TapoError("leere Antwort", .session)
        }
        let enc = Data([UInt8](body)[32...])
        guard let raw = try? Crypto.aesCBCNoPad(encrypt: false, key: key, iv: iv, data: enc) else {
            ready = false
            throw TapoError("Antwort nicht lesbar (Sitzung neu)", .session)
        }
        let plain = TapoKlap.unpad(raw)
        guard !plain.isEmpty,
              let obj = try? JSONSerialization.jsonObject(with: plain, options: []),
              let dict = obj as? [String: Any] else {
            ready = false
            throw TapoError("Antwort nicht lesbar (Sitzung neu)", .session)
        }
        let ec = tapoInt(dict["error_code"]) ?? 0
        if ec == -1012 || ec == -1501 || ec == 9999 || ec == 1002 {
            ready = false
            throw TapoError("Sitzung von der Dose beendet (Code \(ec))", .session)
        }
        if ec != 0 { throw TapoError("Dose meldet Fehler \(ec) bei \(what)", .dev) }
        return (dict["result"] as? [String: Any]) ?? [:]
    }

    private func connect(_ cands: [TapoCred], force: Bool) async throws -> String {
        if ready && Date() < expires && !force { return matched }
        if Date() < authBlockUntil && !force, let e = authError { throw e }
        let p16 = UInt16(clamping: port)
        if !(await TCPConnection.probe(host: host, port: p16, timeout: 1.0)) {
            // Webserver der Dose schlaeft (Firmware 1.4.x) -> per UDP wecken
            if let d = await tapoDiscoverOne(host) { disco = d }
            await pause(0.8)
            if !(await TCPConnection.probe(host: host, port: p16, timeout: 2.0)) {
                if let d = disco {
                    let extra = d.enc.isEmpty ? "" : " - sie meldet Verschlüsselung \(d.enc)"
                    throw TapoError("Dose antwortet auf die Suche (UDP), aber Port \(port) bleibt zu\(extra).", .sleep)
                }
                throw TapoError("keine Antwort (Dose aus, falsche IP oder anderes Netz)", .net)
            }
        }
        do {
            let lab = try await handshake(cands)
            authError = nil
            return lab
        } catch let e as TapoError {
            if e.kind == .auth || e.kind == .forbidden {
                authBlockUntil = Date().addingTimeInterval(tapoAuthPause)
                authError = e
            }
            throw e
        }
    }

    private func acquire() async {
        while locked { await pause(0.02) }
        locked = true
    }

    private func release() { locked = false }

    /// Anmelden (bzw. bestehende Sitzung nutzen); liefert die Bezeichnung der passenden Zugangsdaten.
    func login(_ cands: [TapoCred], force: Bool) async throws -> String {
        await acquire()
        defer { release() }
        return try await connect(cands, force: force)
    }

    /// Anfrage; bei abgelaufener Sitzung einmal neu anmelden.
    func call(_ cands: [TapoCred], _ json: String, _ what: String) async throws -> [String: Any] {
        await acquire()
        defer { release() }
        _ = try await connect(cands, force: false)
        do {
            return try await request(json, what)
        } catch let e as TapoError {
            if e.kind != .session { throw e }
        }
        _ = try await connect(cands, force: true)
        return try await request(json, what)
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

func tapoDecodeName(_ v: Any?) -> String {
    guard let s = v as? String else { return "" }
    if let d = Data(base64Encoded: s), let t = String(data: d, encoding: .utf8) { return t }
    return s
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
    /// Kurztext bei Fehler: "offline", "Zugang falsch", "gesperrt (403)", "Fehler", "keine IP"
    var short = ""
    /// Mit welchen Zugangsdaten angemeldet (Konto 1, Konto 2, Werkszugang ...)
    var access = ""
    var overheated = false
    var model = ""
    var type = ""
    var fw = ""
    var hw = ""
    var mac = ""
    var nickname = ""
    var rssi: Int?
    var signal: Int?
    var onTime: Int?
    /// nil = unbekannt, false = kein Energiemesser (Fehlercode bei get_energy_usage)
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
        if label == "(Typ ungeprüft)" || label == "anderes Konto" || label == "gesperrt (403)" || label.isEmpty {
            return "Dose " + (ip.split(separator: ".").last.map { String($0) } ?? ip)
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
    @Published var diag: [UUID: [String]] = [:]
    @Published var diagRunning: Set<UUID> = []

    @Published var scanRunning = false
    @Published var scanDone = 0
    @Published var scanTotal = 0
    @Published var scanFound: [TapoScanHit] = []
    @Published var scanInfo = ""
    private var scanStop = false
    private var scanQueue: [String] = []
    private var scanIndex = 0

    private var links: [String: TapoLink] = [:]

    init() {
        super.init(id: "tapo", title: "Steckdosen", subtitle: "TP-Link Tapo (KLAP)",
                   symbol: "powerplug.fill", tint: Color(hex: 0x30D158))
    }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(TapoSettings.self, "tapo") { settings = s }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "tapo")
        // Zugangsdaten/IP koennen sich geaendert haben: Sitzungen und Sperrpausen verwerfen
        for c in links.values { c.close() }
        links.removeAll()
        for k in Array(status.keys) { status[k]?.hasEnergy = nil }
    }

    override var quickActions: [QuickAction] {
        [
            QuickAction(id: "tapo.allOn", title: "Alle an", symbol: "power",
                        run: { [weak self] in self?.setAll(true) }),
            QuickAction(id: "tapo.allOff", title: "Alle aus", symbol: "poweroff",
                        run: { [weak self] in self?.setAll(false) }),
            QuickAction(id: "tapo.refresh", title: "Aktualisieren", symbol: "arrow.clockwise",
                        run: { [weak self] in Task { await self?.refresh() } })
        ]
    }

    /// Eingerichtet, sobald eine Dose eingetragen ist (Werkszugaenge brauchen kein Konto).
    override var isConfigured: Bool {
        settings.plugs.contains(where: { !tapoCleanIP($0.ip).isEmpty })
    }

    override var pollInterval: Double { Double(max(3, settings.pollInterval)) }

    override var supportsScene: Bool { settings.plugs.contains(where: { $0.inScene }) }

    override func disconnect() {
        for c in links.values { c.close() }
        links.removeAll()
    }

    // ---- Netzwerk ----
    private func link(_ ip: String) -> TapoLink {
        if let c = links[ip] { return c }
        let c = TapoLink(ip: ip)
        links[ip] = c
        return c
    }

    private func cands(for p: TapoPlug) -> [TapoCred] {
        tapoCandidates(email: settings.email, password: settings.password,
                       email2: settings.email2, password2: settings.password2, which: p.konto)
    }

    private func plugName(_ p: TapoPlug) -> String {
        p.name.trimmed.isEmpty ? tapoCleanIP(p.ip) : p.name
    }

    /// Anfrage an eine Steckdose (Sitzung bleibt bestehen).
    private func call(_ p: TapoPlug, _ json: String, _ what: String) async throws -> [String: Any] {
        let ip = tapoCleanIP(p.ip)
        guard tapoLooksLikeIP(tapoHostPort(ip).0) else {
            throw TapoError("\(ip): keine IP-Adresse (z.B. 192.168.0.130 eintragen)", .proto)
        }
        return try await link(ip).call(cands(for: p), json, what)
    }

    private func poll(_ p: TapoPlug, prev: TapoPlugStatus) async -> TapoPlugStatus {
        var st = prev
        let ip = tapoCleanIP(p.ip)
        guard tapoLooksLikeIP(tapoHostPort(ip).0) else {
            st.reachable = false
            st.short = "keine IP"
            st.error = "Bitte in den Einstellungen die IP-Adresse eintragen (z.B. 192.168.0.130)."
            return st
        }
        let lk = link(ip)
        do {
            let res = try await call(p, TapoKlap.jsonGetInfo, "get_device_info")
            st.reachable = true
            st.error = nil
            st.short = ""
            st.isOn = (res["device_on"] as? Bool) == true
            st.overheated = (res["overheated"] as? Bool) == true
            st.model = (res["model"] as? String) ?? st.model
            st.type = (res["type"] as? String) ?? st.type
            st.fw = (res["fw_ver"] as? String) ?? st.fw
            st.hw = (res["hw_ver"] as? String) ?? st.hw
            st.mac = (res["mac"] as? String) ?? st.mac
            if res["nickname"] != nil { st.nickname = tapoDecodeName(res["nickname"]) }
            st.rssi = tapoInt(res["rssi"])
            st.signal = tapoInt(res["signal_level"])
            st.onTime = tapoInt(res["on_time"])
            st.access = lk.matched
            let sig = "\(st.isOn)|\(lk.matched)"
            if lk.lastLog != sig {
                let nm = st.nickname.isEmpty ? "Dose" : st.nickname
                addLog("\(ip): \(nm), \(st.isOn ? "EIN" : "AUS") (\(lk.matched))")
                lk.lastLog = sig
            }
            lk.lastErr = ""
        } catch let e as TapoError {
            let ex = tapoExplain(e)
            st.reachable = false
            st.short = ex.0
            st.error = ex.1
            if lk.lastErr != e.text {
                if e.kind == .auth { addLog("   -> " + tapoAuthLongText, error: true) }
                addLog("\(ip): \(ex.0) - \(e.text)", error: true)
                lk.lastErr = e.text
            }
            lk.lastLog = ""
            return st
        } catch {
            if tapoIsCancel(error) { return prev }
            st.reachable = false
            st.short = "Fehler"
            st.error = DeviceModel.describe(error)
            return st
        }
        if st.hasEnergy != false {
            do {
                let r = try await call(p, TapoKlap.jsonGetEnergy, "get_energy_usage")
                st.hasEnergy = true
                st.powerW = tapoNum(r["current_power"]).map { $0 / 1000.0 }
                st.todayKWh = tapoNum(r["today_energy"]).map { $0 / 1000.0 }
                st.monthKWh = tapoNum(r["month_energy"]).map { $0 / 1000.0 }
            } catch let e as TapoError {
                if e.kind == .dev {
                    // einmal erkannter Energiemesser bleibt (voruebergehender Fehlercode)
                    if st.hasEnergy != true { st.hasEnergy = false }
                    st.powerW = nil
                    st.todayKWh = nil
                    st.monthKWh = nil
                }
            } catch {
                // Abbruch o.ae.: Werte behalten
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
                if st.reachable { online += 1 } else if firstErr == nil {
                    firstErr = st.short.isEmpty ? st.error : "\(st.short): \(st.error ?? "")"
                }
            }
            let ids = Set(self.settings.plugs.map { $0.id })
            self.status = self.status.filter { ids.contains($0.key) }
            self.fillNames()
            if online == 0 { throw NetError.protocolError(firstErr ?? "Keine Steckdose erreichbar") }
            self.summary = self.makeSummary()
        }
    }

    /// Leere Namen mit dem Namen aus der Tapo-App fuellen (wie die Windows-App).
    private func fillNames() {
        var changed = false
        for i in settings.plugs.indices {
            if settings.plugs[i].name.trimmed.isEmpty, let st = status[settings.plugs[i].id], !st.nickname.isEmpty {
                settings.plugs[i].name = st.nickname
                changed = true
            }
        }
        if changed { SecureStore.saveCodable(settings, "tapo") }
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
        _ = try await call(p, TapoKlap.jsonSetOn(on), "set_device_info")
        var st = status[p.id] ?? TapoPlugStatus()
        st.isOn = on
        st.reachable = true
        st.error = nil
        st.short = ""
        status[p.id] = st
        summary = makeSummary()
    }

    func setPlug(_ p: TapoPlug, _ on: Bool) {
        let name = plugName(p)
        pending.insert(p.id)
        perform("\(name): geschaltet -> \(on ? "EIN" : "AUS")") {
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
                    errors.append("\(self.plugName(p)): \(DeviceModel.describe(error))")
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
                errors.append("\(plugName(p)): \(DeviceModel.describe(error))")
            }
        }
        addLog("Szene \(on ? "an" : "aus"): \(plugs.count - errors.count) von \(plugs.count) geschaltet", error: !errors.isEmpty)
        if !errors.isEmpty { throw NetError.protocolError(errors.joined(separator: "; ")) }
    }

    // ---- Diagnose (wie diagnose / diagnose_all) ----
    func diagnose(_ p: TapoPlug) {
        Task { _ = await self.runDiagnose(p) }
    }

    func diagnoseAll() {
        let plugs = settings.plugs.filter { !tapoCleanIP($0.ip).isEmpty }
        if plugs.isEmpty { return }
        Task {
            var owners: [String: [String]] = [:]
            for p in plugs {
                let r = await self.runDiagnose(p)
                if let d = r.1, !d.owner.isEmpty {
                    owners[d.owner, default: []].append(r.0)
                }
            }
            if owners.count > 1 {
                let groups = owners.values.map { $0.joined(separator: ", ") }.joined(separator: " | ")
                self.addLog("HINWEIS: Die Dosen gehören zu \(owners.count) verschiedenen Tapo-Konten: \(groups)", error: true)
            } else if owners.count == 1 {
                self.addLog("Alle antwortenden Dosen gehören zum selben Tapo-Konto.")
            }
        }
    }

    private func runDiagnose(_ p: TapoPlug) async -> (String, TapoDisco?) {
        let ip = tapoCleanIP(p.ip)
        if ip.isEmpty { return (ip, nil) }
        if diagRunning.contains(p.id) { return (ip, nil) }
        diagRunning.insert(p.id)
        defer { diagRunning.remove(p.id) }
        var lines: [String] = ["Diagnose \(plugName(p)) (\(ip))"]
        let hp = tapoHostPort(ip)
        let d = await tapoDiscoverOne(hp.0, timeout: 2.0)
        if let d = d {
            let owner: String = d.owner.isEmpty ? "-" : (String(d.owner.prefix(8)) + "...")
            let typ: String = tapoTypeLabel(d.type, d.model)
            let encText: String = d.enc.isEmpty ? "?" : d.enc
            let fact: String = d.factory ? "ja" : "nein"
            let l1a: String = "1 Suche (UDP 20002): \(typ), Verschlüsselung \(encText), "
            let l1b: String = "Werkszustand \(fact), Konto-Kennung \(owner)"
            lines.append(l1a + l1b)
            if d.enc.uppercased() == "TPAP" || d.tpap {
                lines.append("  -> Dose meldet das neue TPAP-Verfahren: in der Tapo-App „Drittanbieter-Kompatibilität“ einschalten, dann spricht sie wieder KLAP.")
            }
        } else {
            lines.append("1 Suche (UDP 20002): keine Antwort (Firewall/WLAN-Isolation oder Dose aus)")
        }
        let open = await TCPConnection.probe(host: hp.0, port: UInt16(clamping: hp.1), timeout: 1.5)
        lines.append("2 Port \(hp.1): \(open ? "offen" : "zu / keine Antwort")")
        if tapoLooksLikeIP(hp.0) {
            let lk = link(ip)
            lk.authBlockUntil = Date.distantPast
            let cs = cands(for: p)
            do {
                let lab = try await lk.login(cs, force: true)
                lines.append("3 Anmeldung: OK mit \(lab) (KLAP \(lk.variant))")
                let res = try await lk.call(cs, TapoKlap.jsonGetInfo, "get_device_info")
                let model = (res["model"] as? String) ?? "?"
                let hw = (res["hw_ver"] as? String) ?? "?"
                let fw = (res["fw_ver"] as? String) ?? "?"
                let on = (res["device_on"] as? Bool) == true
                var rssi: String = "?"
                if let r = tapoInt(res["rssi"]) { rssi = String(r) }
                let nick: String = tapoDecodeName(res["nickname"])
                let onText: String = on ? "EIN" : "AUS"
                let l4a: String = "4 Gerät: \(model) „\(nick)“, HW \(hw), FW \(fw), "
                let l4b: String = "\(onText), WLAN \(rssi) dBm"
                lines.append(l4a + l4b)
            } catch let e as TapoError {
                lines.append("3 Anmeldung: \(tapoExplain(e).0) - \(e.text)")
                if e.kind == .auth { lines.append("  -> " + tapoAuthLongText) }
            } catch {
                lines.append("3 Anmeldung: Fehler - \(DeviceModel.describe(error))")
            }
        } else {
            lines.append("3 Anmeldung: übersprungen - keine gültige IP-Adresse")
        }
        diag[p.id] = lines
        // Protokoll zeigt das Neueste oben: Block umgekehrt eintragen, damit er von oben nach unten lesbar ist
        for ln in lines.reversed() { addLog(ln) }
        return (ip, d)
    }

    // ---- Netzsuche (Unicast-Sweep wie scan_network) ----
    func startScan(_ cands: [TapoCred]) {
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
        guard parts.count == 4 else { scanInfo = "Ungültige eigene Adresse \(own)"; return }
        let base = parts[0..<3].joined(separator: ".") + "."
        scanQueue = (1...254).map { base + String($0) }
        scanIndex = 0
        scanDone = 0
        scanTotal = scanQueue.count
        scanFound = []
        scanStop = false
        scanRunning = true
        scanInfo = "Suche in \(base)0/24 ..."
        addLog("Suche in \(base)0/24 ...")
        Task { await self.runScan(cands) }
    }

    private func runScan(_ cands: [TapoCred]) async {
        var workers: [Task<Void, Never>] = []
        for _ in 0..<24 {
            workers.append(Task { await self.scanWorker(cands) })
        }
        for w in workers { await w.value }
        if scanStop {
            scanInfo = "Abgebrochen - gefunden: \(scanFound.count)"
            addLog("Suche abgebrochen. Gefunden: \(scanFound.count)")
        } else {
            scanInfo = "Fertig - gefunden: \(scanFound.count)"
            addLog("Suche fertig. Gefunden: \(scanFound.count)")
        }
        scanRunning = false
        scanStop = false
    }

    private func scanWorker(_ cands: [TapoCred]) async {
        while !scanStop && scanIndex < scanQueue.count {
            let ip = scanQueue[scanIndex]
            scanIndex += 1
            let hit = await scanProbe(ip, cands)
            scanDone += 1
            if let h = hit, !scanFound.contains(where: { $0.ip == h.ip }) {
                scanFound.append(h)
                scanFound.sort { tapoIPKey($0.ip) < tapoIPKey($1.ip) }
                addLog("gefunden (Port 80): \(h.label) auf \(h.ip)")
            }
        }
    }

    private func scanProbe(_ ip: String, _ cands: [TapoCred]) async -> TapoScanHit? {
        guard await TCPConnection.probe(host: ip, port: 80, timeout: 0.6) else { return nil }
        guard await isTapo(ip) else { return nil }
        let c = TapoLink(ip: ip, timeout: 3)
        defer { c.close() }
        do {
            let res = try await c.call(cands, TapoKlap.jsonGetInfo, "get_device_info")
            let dtype = ((res["type"] as? String) ?? "").uppercased()
            let model = (res["model"] as? String) ?? ""
            return TapoScanHit(ip: ip, label: tapoTypeLabel(dtype, model))
        } catch let e as TapoError {
            if e.kind == .auth { return TapoScanHit(ip: ip, label: "anderes Konto") }
            if e.kind == .forbidden { return TapoScanHit(ip: ip, label: "gesperrt (403)") }
            return TapoScanHit(ip: ip, label: "(Typ ungeprüft)")
        } catch {
            return nil
        }
    }

    /// Tapo-Geraet: handshake1 mit 16 Zufallsbytes -> 403 oder (200 und >= 48 Byte)
    private func isTapo(_ ip: String) async -> Bool {
        guard let url = URL(string: "http://\(ip)/app/handshake1") else { return false }
        let h = HTTPClient()
        h.noProxy = true
        defer { h.session.finishTasksAndInvalidate() }
        do {
            let (d, r) = try await h.request("POST", url, headers: ["Content-Type": "application/octet-stream"],
                                             body: Crypto.random(16), timeout: 1.5)
            return r.statusCode == 403 || (r.statusCode == 200 && d.count >= 48)
        } catch {
            return false
        }
    }

    // ---- Demo (Start mit -demo, ohne Netzwerk) ----
    override func loadDemo() {
        let p1 = TapoPlug(name: "Licht Studio", ip: "192.168.1.61", inScene: true)
        let p2 = TapoPlug(name: "Monitore", ip: "192.168.1.62", inScene: true)
        let p3 = TapoPlug(name: "Verstaerker", ip: "192.168.1.63", inScene: true, konto: "1")
        let p4 = TapoPlug(name: "Kaffeemaschine", ip: "192.168.1.64", inScene: false, konto: "2")
        var s = TapoSettings()
        s.email = "studio@example.com"
        s.password = "demo"
        s.email2 = "privat@example.com"
        s.password2 = "demo"
        s.plugs = [p1, p2, p3, p4]
        s.pollInterval = 15
        settings = s

        func mk(_ on: Bool, _ nick: String, _ mac: String, _ rssi: Int, _ sig: Int, _ onTime: Int,
                _ w: Double, _ today: Double, _ month: Double, _ access: String) -> TapoPlugStatus {
            var st = TapoPlugStatus()
            st.reachable = true
            st.isOn = on
            st.error = nil
            st.access = access
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
            p1.id: mk(true, "Licht Studio", "3C-52-A1-10-20-01", -48, 3, 9_840, 42.6, 0.31, 6.84, "Konto 1"),
            p2.id: mk(true, "Monitore", "3C-52-A1-10-20-02", -55, 3, 9_790, 68.2, 0.52, 11.37, "Konto 1"),
            p3.id: mk(true, "Verstaerker", "3C-52-A1-10-20-03", -61, 2, 9_720, 23.9, 0.19, 4.12, "Konto 1"),
            p4.id: mk(false, "Kaffeemaschine", "3C-52-A1-10-20-04", -67, 2, 0, 0.0, 0.08, 2.95, "Konto 2"),
        ]
        diag = [p1.id: [
            "Diagnose Licht Studio (192.168.1.61)",
            "1 Suche (UDP 20002): Steckdose P110, Verschlüsselung KLAP, Werkszustand nein, Konto-Kennung 3F9A21C4...",
            "2 Port 80: offen",
            "3 Anmeldung: OK mit Konto 1 (KLAP v2)",
            "4 Gerät: P110 „Licht Studio“, HW 1.0, FW 1.3.1 Build 240621 Rel.162048, EIN, WLAN -48 dBm"
        ]]
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
                        ActionTile(title: "Alle abfragen", symbol: "arrow.clockwise", tint: .blue) {
                            Task { await model.refresh() }
                        }
                        ActionTile(title: "Diagnose alle", symbol: "stethoscope", tint: .orange) { model.diagnoseAll() }
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

func tapoKontoText(_ k: String) -> String {
    if k == "1" { return "Konto 1" }
    if k == "2" { return "Konto 2" }
    return "Auto"
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
        if !s.reachable { return s.short.isEmpty ? "Nicht erreichbar" : s.short }
        if s.overheated { return s.isOn ? "Ein - ÜBERHITZT" : "Aus - ÜBERHITZT" }
        return s.isOn ? "Ein" : "Aus"
    }

    var stateColor: Color {
        guard let s = st else { return Color.secondary }
        if !s.reachable { return s.short == "offline" ? Color.secondary : Color.red }
        if s.overheated { return Color.red }
        return s.isOn ? Color.green : Color.secondary
    }

    var accessText: String {
        let a = st?.access ?? ""
        return a.isEmpty ? "-" : a
    }

    var body: some View {
        Section {
            HStack {
                PowerToggleRow(title: title, symbol: "powerplug", isOn: st?.isOn ?? false,
                               tint: Color(hex: 0x30D158)) { v in model.setPlug(plug, v) }
                    .disabled(model.pending.contains(plug.id))
                if model.pending.contains(plug.id) { ProgressView().padding(.leading, 4) }
            }
            ValueRow(label: "Status", value: stateText, valueColor: stateColor)
            if let s = st, s.hasEnergy == true {
                ValueRow(label: "Leistung", value: tapoFmtW(s.powerW), symbol: "bolt.fill")
                ValueRow(label: "Heute", value: tapoFmtKWh(s.todayKWh))
                ValueRow(label: "Monat", value: tapoFmtKWh(s.monthKWh))
            }
            DisclosureGroup("Geräteinfo") {
                Group {
                    ValueRow(label: "IP-Adresse", value: tapoCleanIP(plug.ip))
                    ValueRow(label: "Modell", value: (st?.model ?? "").isEmpty ? "-" : (st?.model ?? "-"))
                    ValueRow(label: "Name in der App", value: (st?.nickname ?? "").isEmpty ? "-" : (st?.nickname ?? "-"))
                    ValueRow(label: "Firmware", value: (st?.fw ?? "").isEmpty ? "-" : (st?.fw ?? "-"))
                    ValueRow(label: "Hardware", value: (st?.hw ?? "").isEmpty ? "-" : (st?.hw ?? "-"))
                    ValueRow(label: "MAC", value: (st?.mac ?? "").isEmpty ? "-" : (st?.mac ?? "-"))
                }
                Group {
                    ValueRow(label: "WLAN", value: tapoSignalText(st))
                    ValueRow(label: "Eingeschaltet seit", value: (st?.isOn ?? false) ? tapoFmtDuration(st?.onTime) : "-")
                    ValueRow(label: "Kontowahl", value: tapoKontoText(plug.konto))
                    ValueRow(label: "Angemeldet mit", value: accessText)
                    ValueRow(label: "In Szene", value: plug.inScene ? "Ja" : "Nein")
                }
            }
            HStack {
                Button {
                    model.diagnose(plug)
                } label: {
                    Label("Diagnose", systemImage: "stethoscope")
                }
                .disabled(model.diagRunning.contains(plug.id))
                if model.diagRunning.contains(plug.id) { ProgressView().padding(.leading, 4) }
            }
            if let lines = model.diag[plug.id] {
                DisclosureGroup("Diagnose-Ergebnis") {
                    ForEach(Array(lines.enumerated()), id: \.offset) { item in
                        Text(item.element)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                }
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

    private func scanCands() -> [TapoCred] {
        tapoCandidates(email: s.email, password: s.password, email2: s.email2, password2: s.password2, which: "auto")
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
                Text("Tapo-Konto 1")
            } footer: {
                Text("Genau wie in der Tapo-App, Groß-/Kleinschreibung beachten. Gespeichert im Schlüsselbund.")
            }
            Section {
                FieldRow(label: "E-Mail", text: $s.email2, placeholder: "optional", keyboard: .emailAddress)
                FieldRow(label: "Passwort", text: $s.password2, placeholder: "optional", secure: true)
            } header: {
                Text("Tapo-Konto 2 (optional)")
            } footer: {
                Text("Für Dosen, die zu einem anderen Tapo-Konto gehören. Mit Kontowahl „Auto“ findet die App selbst heraus, welches Konto passt - ohne zusätzliche Anmeldeversuche.")
            }
            Section {
                ForEach($s.plugs) { $p in
                    VStack(alignment: .leading, spacing: 6) {
                        TextField("Name (leer = Name aus der Tapo-App)", text: $p.name)
                            .font(.body.weight(.semibold))
                        TextField("IP-Adresse (z.B. 192.168.0.130)", text: $p.ip)
                            .keyboardType(.numbersAndPunctuation)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .foregroundStyle(.secondary)
                        Picker("Konto", selection: $p.konto) {
                            Text("Auto").tag("auto")
                            Text("Konto 1").tag("1")
                            Text("Konto 2").tag("2")
                        }
                        .pickerStyle(.segmented)
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
                    model.startScan(scanCands())
                } label: {
                    Label(model.scanRunning ? "Suche abbrechen" : "Netz durchsuchen",
                          systemImage: model.scanRunning ? "stop.circle" : "magnifyingglass")
                }
                if model.scanRunning {
                    VStack(alignment: .leading, spacing: 4) {
                        ProgressView(value: Double(model.scanDone), total: Double(max(1, model.scanTotal)))
                        Text("Port-80-Suche \(model.scanDone)/\(model.scanTotal)")
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
                Text("Prüft alle Adressen im eigenen WLAN-Netz (/24) auf Port 80 und den Tapo-Handshake. Der Gerätetyp wird mit Konto 1, Konto 2 oder einem Werkszugang gelesen.")
            }
            Section("Aktualisierung") {
                Stepper("Abfrage alle \(s.pollInterval) s", value: $s.pollInterval, in: 3...120)
            }
        }
    }
}
