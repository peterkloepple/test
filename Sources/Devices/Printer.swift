// ===========================================================================
//  Printer.swift - Studio Control iOS - Epson WorkForce WF-7830
//  Autor: T. Pfeiffer
//
//  Port von sc.py (EpsonWF7830Control / PrinterModule):
//    - Status ueber IPP Get-Printer-Attributes (eigener Mini-IPP-Kodierer)
//      und SNMP (Printer-MIB, Host-Resources-MIB, EPSON-CTRL "st" -> @BDC ST2)
//    - Tintenstaende (IPP marker-*, sonst SNMP prtMarkerSupplies-Walk)
//    - Wartung: Duesentest, Reinigung, Power-Reinigung, Statusblatt, Leerblatt
//      als Epson-Remote-Mode-Bytefolgen (IPP Print-Job octet-stream / LPR / RAW)
//      mit UNSICHER-Regel (kein zweiter Sendeweg, wenn der erste evtl. ankam)
//    - Druckauftraege: Get-Jobs, Cancel-Job, Cancel-Jobs (-> Purge-Jobs),
//      Pause/Resume/Identify-Printer
//    - Web Config im Browser oeffnen
// ===========================================================================
import Foundation
import SwiftUI
import UIKit

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct PrinterSettings: Codable {
    var ip: String = "192.168.1.154"
    var community: String = "public"
    var ippBasePath: String = "/ipp/print"
    var ippTLS: Bool = false
    var webScheme: String = "http"
    var adminPassword: String = ""
    var timeout: Int = 3
    var inkWarnPct: Int = 15
    var maintTransport: String = "ipp"

    enum CodingKeys: String, CodingKey {
        case ip, community, ippBasePath, ippTLS, webScheme, adminPassword, timeout, inkWarnPct, maintTransport
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let v = try c.decodeIfPresent(String.self, forKey: .ip) { ip = v }
        if let v = try c.decodeIfPresent(String.self, forKey: .community) { community = v }
        if let v = try c.decodeIfPresent(String.self, forKey: .ippBasePath) { ippBasePath = v }
        if let v = try c.decodeIfPresent(Bool.self, forKey: .ippTLS) { ippTLS = v }
        if let v = try c.decodeIfPresent(String.self, forKey: .webScheme) { webScheme = v }
        if let v = try c.decodeIfPresent(String.self, forKey: .adminPassword) { adminPassword = v }
        if let v = try c.decodeIfPresent(Int.self, forKey: .timeout) { timeout = v }
        if let v = try c.decodeIfPresent(Int.self, forKey: .inkWarnPct) { inkWarnPct = v }
        if let v = try c.decodeIfPresent(String.self, forKey: .maintTransport) { maintTransport = v }
    }
}

// ---------------------------------------------------------------------------
// Datentypen
// ---------------------------------------------------------------------------
enum PrinterIPPValue {
    case int(Int)
    case bool(Bool)
    case text(String)

    var text: String {
        switch self {
        case .int(let v): return String(v)
        case .bool(let b): return b ? "true" : "false"
        case .text(let s): return s
        }
    }

    var intValue: Int? {
        switch self {
        case .int(let v): return v
        case .text(let s): return Int(s.trimmed)
        case .bool(let b): return b ? 1 : 0
        }
    }
}

typealias PrinterIPPAttrs = [String: [PrinterIPPValue]]

struct PrinterIPPGroup {
    let tag: UInt8
    var attrs: PrinterIPPAttrs
}

struct PrinterIPPResult {
    var ok: Bool
    var status: Int?
    var msg: String
    var groups: [PrinterIPPGroup] = []
    var via: String? = nil
    var netError: Error? = nil

    var jobs: [PrinterIPPAttrs] { groups.filter { $0.tag == 0x02 }.map { $0.attrs } }
    var printerAttrs: PrinterIPPAttrs? { groups.first(where: { $0.tag == 0x04 })?.attrs }
}

struct PrinterIPPQuery {
    var attrs: PrinterIPPAttrs?
    var via: String
    var error: String
}

struct PrinterST2 {
    var values: [String: String] = [:]
    var code: Int?
}

struct PrinterInfo {
    var name = ""
    var model = ""
    var serial = ""
    var firmware = ""
    var state = ""
    var uptime = ""
    var pages = ""
    var location = ""
    var sysName = ""
    var sysDescr = ""
    var reasons: [String] = []
}

struct PrinterInk: Identifiable {
    let id: Int
    let name: String
    let pct: Int?
    let color: UInt32
    let low: Bool
}

struct PrinterJob: Identifiable {
    let id: Int
    let jobId: Int?
    let name: String
    let state: String
    let user: String
    let kOctets: String
}

struct PrinterPortState: Identifiable {
    var id: Int { port }
    let port: Int
    let label: String
    let open: Bool
}

struct PrinterInkRaw {
    let name: String
    let pct: Int?
}

// ---------------------------------------------------------------------------
// Protokoll-Konstanten und Hilfen (1:1 aus sc.py)
// ---------------------------------------------------------------------------
enum PrinterProto {
    static let defaultIP = "192.168.1.154"

    static let oid: [String: String] = [
        "sysDescr": "1.3.6.1.2.1.1.1.0",
        "sysName": "1.3.6.1.2.1.1.5.0",
        "sysUpTime": "1.3.6.1.2.1.1.3.0",
        "prtName": "1.3.6.1.2.1.43.5.1.1.16.1",
        "prtSerial": "1.3.6.1.2.1.43.5.1.1.17.1",
        "hrPrinterStatus": "1.3.6.1.2.1.25.3.5.1.1.1",
        "hrPrinterError": "1.3.6.1.2.1.25.3.5.1.2.1",
        "lifeCount": "1.3.6.1.2.1.43.10.2.1.4.1.1",
    ]
    static let oidNames = ["sysDescr", "sysName", "sysUpTime", "prtName", "prtSerial",
                           "hrPrinterStatus", "hrPrinterError", "lifeCount"]
    static let supDesc = "1.3.6.1.2.1.43.11.1.1.6.1"
    static let supMax = "1.3.6.1.2.1.43.11.1.1.8.1"
    static let supLvl = "1.3.6.1.2.1.43.11.1.1.9.1"

    static let scanPorts: [(Int, String)] = [
        (80, "HTTP / Web Config"),
        (443, "HTTPS / Web Config"),
        (515, "LPR"),
        (631, "IPP / IPPS"),
        (9100, "RAW / ESC-P-R"),
        (3289, "ENPC (Epson)"),
    ]

    // Reihenfolge wie EP_COLOR_MAP (dict-Reihenfolge in Python)
    static let colorMap: [(String, UInt32)] = [
        ("black", 0x222222), ("schwarz", 0x222222), ("bk", 0x222222), ("k", 0x222222),
        ("cyan", 0x12B6D6), ("c", 0x12B6D6),
        ("magenta", 0xD6329B), ("m", 0xD6329B),
        ("yellow", 0xFFD60A), ("y", 0xFFD60A), ("gelb", 0xFFD60A),
        ("light", 0x9AA6B2), ("gray", 0x9AA6B2), ("grey", 0x9AA6B2),
    ]
    static let defaultColor: UInt32 = 0x6B7685

    static let transports = ["auto", "ipp", "lpr", "raw"]
    static func transportName(_ k: String) -> String {
        switch k {
        case "auto": return "Automatisch (LPR › IPP › RAW)"
        case "lpr": return "LPR Port 515"
        case "raw": return "RAW Port 9100"
        default: return "IPP Port 631"
        }
    }

    // ---- Epson Remote-Modus (Bytefolgen wie epson_print_conf) ----
    static let exitPacket: Data = {
        var d = Data([0x00, 0x00, 0x00, 0x1b, 0x01])
        d.append(Data("@EJL 1284.4\n@EJL     \n".utf8))
        return d
    }()
    static let initSeq = Data([0x1b, 0x40])
    static let remoteOn: Data = {
        var d = Data([0x1b, 0x40, 0x1b, 0x40])
        d.append(contentsOf: [0x1b, 0x28, 0x52, 0x08, 0x00, 0x00])
        d.append(Data("REMOTE1".utf8))
        return d
    }()
    static let remoteOff = Data([0x1b, 0x00, 0x00, 0x00])

    /// Remote-Kommando: 2 Zeichen + Laenge (LE16) + Parameter
    static func rcmd(_ cmd: String, _ args: [UInt8] = []) -> Data {
        var d = Data(cmd.utf8)
        d.append(UInt8(args.count & 0xff))
        d.append(UInt8((args.count >> 8) & 0xff))
        d.append(contentsOf: args)
        return d
    }

    static var jobEnd: Data { rcmd("JE", [0x00]) }

    static func rcmdTime() -> Data {
        let c = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .second], from: Date())
        let y = c.year ?? 2026
        let args: [UInt8] = [0x00, UInt8((y >> 8) & 0xff), UInt8(y & 0xff),
                             UInt8((c.month ?? 1) & 0xff), UInt8((c.day ?? 1) & 0xff),
                             UInt8((c.hour ?? 0) & 0xff), UInt8((c.minute ?? 0) & 0xff),
                             UInt8((c.second ?? 0) & 0xff)]
        return rcmd("TI", args)
    }

    static func seqNozzle(variant: Int = 0) -> Data {
        var d = exitPacket
        d.append(remoteOn)
        d.append(rcmd("NC", variant == 0 ? [0x00, 0x00] : [0x00, 0x10]))
        d.append(remoteOff)
        d.append(jobEnd)
        return d
    }

    static func seqClean(group: UInt8 = 0, power: Bool = false) -> Data {
        let g: UInt8 = power ? (group | 0x10) : group
        var d = exitPacket
        d.append(remoteOn)
        d.append(rcmdTime())
        d.append(rcmd("CH", [0x00, g]))
        d.append(remoteOff)
        d.append(remoteOn)
        d.append(jobEnd)
        d.append(remoteOff)
        return d
    }

    static func seqVersionInfo() -> Data {
        var d = exitPacket
        d.append(remoteOn)
        d.append(rcmd("VI", [0x00, 0x00]))
        d.append(remoteOff)
        d.append(jobEnd)
        return d
    }

    static var paperFeed: Data {
        var d = initSeq
        d.append(0x0c)
        return d
    }

    // ---- EPSON-CTRL ueber SNMP ----
    static let ctrlOIDBase = "1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1"
    static func ctrlOID(cmd: String, payload: [UInt8]) -> String {
        let bytes = [UInt8](rcmd(cmd, payload))
        return ctrlOIDBase + "." + bytes.map { String($0) }.joined(separator: ".")
    }

    static let stStatus: [UInt8: String] = [
        0x00: "Fehler", 0x01: "Selbstdruck", 0x02: "beschäftigt",
        0x03: "wartet", 0x04: "bereit", 0x05: "pausiert", 0x07: "Reinigung läuft",
        0x08: "nicht initialisiert", 0x0A: "fährt herunter",
        0x0F: "Düsentest läuft", 0x11: "Tinte wird geladen",
    ]
    static let stError: [UInt8: String] = [
        0x00: "schwerer Fehler", 0x01: "andere Schnittstelle aktiv",
        0x02: "Abdeckung offen", 0x04: "Papierstau", 0x05: "Tinte leer",
        0x06: "Papier leer", 0x0C: "Papierformat/-typ/-weg falsch",
        0x10: "Resttintenkissen voll (Service)", 0x12: "Doppeleinzug",
        0x1A: "Patronenabdeckung offen", 0x22: "Wartungsbox fehlt",
        0x25: "hintere Abdeckung offen", 0x2B: "Fachabdeckung offen",
        0x36: "Wartungsbox-Abdeckung offen", 0x37: "Scanner/Frontabdeckung offen",
        0x41: "Wartung erforderlich", 0x47: "Drucken gesperrt",
        0x4A: "Wartungsbox fast voll",
    ]
    static let stWarn: [UInt8: String] = [
        0x10: "Tinte niedrig (Schwarz/Gelb)", 0x11: "Tinte niedrig (Magenta)",
        0x12: "Tinte niedrig (Gelb/Cyan)", 0x13: "Tinte niedrig (Cyan)",
        0x44: "Schwarzdruck-Modus", 0x51: "Reinigung gesperrt (Cyan)",
        0x52: "Reinigung gesperrt (Magenta)", 0x53: "Reinigung gesperrt (Gelb)",
        0x54: "Reinigung gesperrt (Schwarz)",
    ]
    static let stInk: [UInt8: String] = [0x00: "Schwarz", 0x01: "Cyan", 0x02: "Magenta", 0x03: "Gelb"]

    /// Anzeige-Reihenfolge der ST2-Felder: (Schluessel, Beschriftung)
    static let st2Keys: [(String, String)] = [
        ("Status", "Status"), ("Fehler", "Fehler"), ("Warnungen", "Warnungen"), ("Tinte", "Tinte"),
        ("Wartungsbox", "Wartungsbox"), ("Papierstau", "Papierstau"), ("Blattzaehler", "Blattzähler"),
        ("Reinigungszeit", "Reinigungszeit"), ("Schnittstelle", "Schnittstelle"), ("Seriennummer", "Seriennummer"),
    ]

    static func code(_ x: UInt8) -> String { String(format: "Code 0x%02X", Int(x)) }

    static func leInt(_ b: [UInt8], signed: Bool) -> Int64 {
        let n = min(b.count, 8)
        if n == 0 { return 0 }
        var v: UInt64 = 0
        for i in 0..<n { v |= UInt64(b[i]) << UInt64(8 * i) }
        if signed && n < 8 && (b[n - 1] & 0x80) != 0 {
            v |= ~UInt64(0) << UInt64(8 * n)
        }
        return Int64(bitPattern: v)
    }

    /// Dekodiert die @BDC-ST2-Statusantwort (ep_parse_st2)
    static func parseST2(_ data: Data) throws -> PrinterST2 {
        guard let r = data.range(of: Data("BDC ST2\r\n".utf8)) else {
            throw NetError.protocolError("keine BDC-ST2-Antwort")
        }
        let all = [UInt8](data[r.upperBound...])
        var ln = 0
        if all.count >= 1 { ln = Int(all[0]) }
        if all.count >= 2 { ln |= Int(all[1]) << 8 }
        let buf = Array(all.dropFirst(2).prefix(ln))
        var out = PrinterST2()
        var pos = 0
        while buf.count - pos >= 2 {
            let ft = buf[pos]
            let l = Int(buf[pos + 1])
            let start = pos + 2
            let end = min(start + l, buf.count)
            let it = Array(buf[start..<end])
            pos = start + l
            if it.count != l { break }
            switch ft {
            case 0x01 where l > 0:
                out.values["Status"] = stStatus[it[0]] ?? code(it[0])
                out.code = Int(it[0])
            case 0x02 where l > 0:
                out.values["Fehler"] = stError[it[0]] ?? code(it[0])
            case 0x04:
                out.values["Warnungen"] = it.map { stWarn[$0] ?? code($0) }.joined(separator: ", ")
            case 0x0C where l > 0:
                out.values["Reinigungszeit"] = "\(leInt(it, signed: true)) s"
            case 0x0F where l > 0:
                let step = it[0] == 0 ? 3 : Int(it[0])
                var inks: [String] = []
                if l - 2 > 1 {
                    for o in stride(from: 1, to: l - 2, by: step) {
                        let name = stInk[it[o + 1]] ?? "Farbe \(it[o + 1])"
                        inks.append("\(name) \(it[o + 2])%")
                    }
                }
                out.values["Tinte"] = inks.joined(separator: ", ")
            case 0x35 where l > 0:
                let m: [UInt8: String] = [0: "kein Stau", 1: "Stau am Ausgang", 2: "Stau im Einzug",
                                          0x80: "kein Papier im Einzug"]
                out.values["Papierstau"] = m[it[0]] ?? code(it[0])
            case 0x36 where l == 20:
                let names = ["normal", "Seiten", "Farbe", "s/w", "leer"]
                var parts: [String] = []
                for k in 0..<5 {
                    let v = leInt(Array(it[(k * 4)..<(k * 4 + 4)]), signed: true)
                    if v >= 0 { parts.append("\(names[k]) \(v)") }
                }
                out.values["Blattzaehler"] = parts.isEmpty ? "-" : parts.joined(separator: ", ")
            case 0x37 where l >= 2:
                let nb = (it[0] == 1 || it[0] == 2) ? Int(it[0]) : 1
                var boxes: [String] = []
                for i in stride(from: 1, to: l, by: nb) {
                    switch it[i] {
                    case 0: boxes.append("nicht voll")
                    case 1: boxes.append("fast voll")
                    case 2: boxes.append("VOLL")
                    default: boxes.append("Code \(it[i])")
                    }
                }
                out.values["Wartungsbox"] = boxes.joined(separator: ", ")
            case 0x3D where l > 0:
                out.values["Schnittstelle"] = it[0] == 0 ? "bereit für Daten" : "nimmt keine Daten an"
            case 0x1F, 0x40:
                if it.allSatisfy({ $0 < 0x80 }) {
                    let s = String(decoding: it, as: UTF8.self)
                    out.values["Seriennummer"] = s.trimmingCharacters(in: CharacterSet(charactersIn: "\u{0} "))
                }
            default:
                break
            }
        }
        return out
    }

    // ---- IPP ----
    static let ippOps: [String: UInt16] = [
        "Get-Jobs": 0x000A, "Cancel-Job": 0x0008, "Pause-Printer": 0x0010,
        "Resume-Printer": 0x0011, "Purge-Jobs": 0x0012, "Cancel-Jobs": 0x0038,
        "Identify-Printer": 0x003C, "Print-Job": 0x0002, "Get-Printer-Attributes": 0x000B,
    ]
    static let ippStatus: [Int: String] = [
        0x0000: "OK", 0x0001: "OK (Attribute ignoriert)", 0x0400: "Bad Request",
        0x0401: "verboten", 0x0402: "nicht authentifiziert", 0x0403: "nicht autorisiert",
        0x0404: "nicht möglich", 0x0406: "nicht gefunden", 0x0501: "nicht unterstützt",
        0x0503: "Service nicht verfügbar", 0x0507: "Drucker busy",
    ]
    static let jobState: [Int: String] = [3: "wartet", 4: "angehalten", 5: "druckt", 6: "gestoppt",
                                          7: "abgebrochen", 8: "abgebrochen (Fehler)", 9: "fertig"]

    /// Attribute, die Get-Printer-Attributes anfragt (wie pyipp: Info, State, Marker)
    static let printerAttrNames = [
        "printer-name", "printer-make-and-model", "printer-info", "printer-device-id",
        "printer-firmware-string-version", "printer-up-time", "printer-location",
        "printer-state", "printer-state-message", "printer-state-reasons",
        "marker-names", "marker-colors", "marker-levels", "marker-high-levels", "marker-types",
        "printer-uuid",
    ]

    /// Identify-Printer: identify-actions = sound, display (Bytes wie sc.py)
    static let identifyExtra = Data(hex: "4400106964656e746966792d616374696f6e730005736f756e644400000007646973706c6179") ?? Data()

    static func be16(_ n: Int) -> Data { Data([UInt8((n >> 8) & 0xff), UInt8(n & 0xff)]) }

    static func be32(_ n: Int) -> Data {
        let u = UInt32(bitPattern: Int32(truncatingIfNeeded: n))
        return Data([UInt8((u >> 24) & 0xff), UInt8((u >> 16) & 0xff), UInt8((u >> 8) & 0xff), UInt8(u & 0xff)])
    }

    static func ippAttr(_ tag: UInt8, _ name: String, _ value: Data) -> Data {
        let nb = Data(name.utf8)
        var d = Data([tag])
        d.append(be16(nb.count))
        d.append(nb)
        d.append(be16(value.count))
        d.append(value)
        return d
    }

    static func ippAttr(_ tag: UInt8, _ name: String, _ value: String) -> Data {
        ippAttr(tag, name, Data(value.utf8))
    }

    /// _ipp_parse: -> (Statuscode, Gruppen)
    static func ippParse(_ data: Data) throws -> (Int, [PrinterIPPGroup]) {
        let b = [UInt8](data)
        guard b.count >= 8 else { throw NetError.protocolError("IPP-Antwort zu kurz") }
        let status = (Int(b[2]) << 8) | Int(b[3])
        var i = 8
        var groups: [PrinterIPPGroup] = []
        var last: String? = nil
        while i < b.count {
            let tag = b[i]
            i += 1
            if tag < 0x10 {
                if tag == 0x03 { break }
                groups.append(PrinterIPPGroup(tag: tag, attrs: [:]))
                continue
            }
            guard i + 2 <= b.count else { throw NetError.protocolError("IPP: abgeschnitten") }
            let nl = (Int(b[i]) << 8) | Int(b[i + 1])
            i += 2
            guard i + nl <= b.count else { throw NetError.protocolError("IPP: abgeschnitten") }
            let name = String(decoding: b[i..<(i + nl)], as: UTF8.self)
            i += nl
            guard i + 2 <= b.count else { throw NetError.protocolError("IPP: abgeschnitten") }
            let vl = (Int(b[i]) << 8) | Int(b[i + 1])
            i += 2
            guard i + vl <= b.count else { throw NetError.protocolError("IPP: abgeschnitten") }
            let raw = Array(b[i..<(i + vl)])
            i += vl
            let val: PrinterIPPValue
            if (tag == 0x21 || tag == 0x23) && vl == 4 {
                var u: UInt32 = 0
                for x in raw { u = (u << 8) | UInt32(x) }
                val = .int(Int(Int32(bitPattern: u)))
            } else if tag == 0x22 && vl == 1 {
                val = .bool(raw[0] != 0)
            } else {
                val = .text(String(decoding: raw, as: UTF8.self))
            }
            if groups.isEmpty { groups.append(PrinterIPPGroup(tag: 0, attrs: [:])) }
            let gi = groups.count - 1
            if !name.isEmpty {
                last = name
                groups[gi].attrs[name] = [val]
            } else if let l = last {
                groups[gi].attrs[l, default: []].append(val)
            }
        }
        return (status, groups)
    }

    static func text(_ a: PrinterIPPAttrs, _ k: String) -> String {
        (a[k]?.first?.text ?? "").trimmed
    }

    /// printer-device-id "MFG:EPSON;MDL:WF-7830 Series;CMD:...;SN:..." -> Woerterbuch
    static func deviceID(_ s: String) -> [String: String] {
        var out: [String: String] = [:]
        for part in s.split(separator: ";") {
            let kv = part.split(separator: ":", maxSplits: 1).map { String($0).trimmed }
            if kv.count == 2 { out[kv[0].uppercased()] = kv[1] }
        }
        return out
    }

    // ---- sonstige Hilfen ----
    /// ep_host: IP/Hostname aus Eingabe ("https://1.2.3.4/PRES" -> "1.2.3.4")
    static func host(_ text: String) -> String {
        var t = text.trimmed
        if let r = t.range(of: "://") { t = String(t[r.upperBound...]) }
        if let s = t.firstIndex(of: "/") { t = String(t[t.startIndex..<s]) }
        if let q = t.firstIndex(of: "?") { t = String(t[t.startIndex..<q]) }
        t = t.trimmed
        if t.filter({ $0 == ":" }).count == 1, let c = t.firstIndex(of: ":") {
            t = String(t[t.startIndex..<c])
        }
        return t
    }

    /// ep_scheme
    static func scheme(_ v: String) -> String {
        let s = v.trimmed.lowercased()
        let head = s.split(separator: ":", maxSplits: 1).first.map { String($0) } ?? s
        return head.trimmingCharacters(in: CharacterSet(charactersIn: "/ ")) == "https" ? "https" : "http"
    }

    /// ep_color_for - Ein-/Zweibuchstaben-Schluessel nur als ganzes Wort
    static func colorFor(_ name: String) -> UInt32 {
        let s = name.trimmed.lowercased()
        if s.isEmpty { return defaultColor }
        if s.hasPrefix("#") {
            let h = String(s.dropFirst())
            if h.count == 6, let v = UInt32(h, radix: 16) { return v }
            if h.count == 3, let v = UInt32(h, radix: 16) {
                let r = (v >> 8) & 0xf
                let g = (v >> 4) & 0xf
                let b = v & 0xf
                return (r * 17) << 16 | (g * 17) << 8 | (b * 17)
            }
        }
        let words = Set(s.split(whereSeparator: { !$0.isLetter }).map { String($0) })
        for (k, v) in colorMap {
            if k.count <= 2 {
                if words.contains(k) { return v }
            } else if s.contains(k) {
                return v
            }
        }
        return defaultColor
    }

    static func fmtUptime(_ seconds: Int) -> String {
        let d = seconds / 86400
        let h = (seconds % 86400) / 3600
        let m = (seconds % 3600) / 60
        if d > 0 { return "\(d)d \(h)h \(m)m" }
        if h > 0 { return "\(h)h \(m)m" }
        return "\(m)m"
    }

    /// _ep_snmp_status_text
    static func snmpStatusText(status: Int64?, errByte: UInt8?) -> String {
        var parts: [String] = []
        if let st = status {
            let m: [Int64: String] = [1: "other", 2: "unbekannt", 3: "bereit", 4: "druckt", 5: "aufwärmen"]
            parts.append(m[st] ?? "Status \(st)")
        }
        if let b = errByte, b != 0 {
            let flags: [(UInt8, String)] = [(0x40, "kein Papier"), (0x80, "wenig Papier"),
                                            (0x10, "keine Tinte"), (0x20, "wenig Tinte"),
                                            (0x08, "Klappe offen"), (0x04, "Papierstau"),
                                            (0x02, "offline"), (0x01, "Service nötig")]
            for (bit, txt) in flags where b & bit != 0 { parts.append(txt) }
        }
        return parts.joined(separator: "  ")
    }

    static func ippStateText(_ v: Int?) -> String {
        guard let v = v else { return "" }
        switch v {
        case 3: return "Bereit"
        case 4: return "Druckt"
        case 5: return "Gestoppt"
        default: return "Status \(v)"
        }
    }

    static func isRefused(_ e: Error) -> Bool {
        if e is NetError { return true }
        let ns = e as NSError
        if ns.domain == NSURLErrorDomain {
            let codes: [Int] = [NSURLErrorCannotConnectToHost, NSURLErrorCannotFindHost, NSURLErrorDNSLookupFailed,
                                NSURLErrorNotConnectedToInternet, NSURLErrorSecureConnectionFailed,
                                NSURLErrorServerCertificateUntrusted, NSURLErrorServerCertificateHasBadDate,
                                NSURLErrorServerCertificateNotYetValid, NSURLErrorServerCertificateHasUnknownRoot,
                                NSURLErrorClientCertificateRejected, NSURLErrorClientCertificateRequired,
                                NSURLErrorAppTransportSecurityRequiresSecureConnection,
                                NSURLErrorBadURL, NSURLErrorUnsupportedURL]
            if codes.contains(ns.code) { return true }
        }
        let t = e.localizedDescription.lowercased()
        for k in ["refused", "verweigert", "abgelehnt", "no route", "unreachable", "ssl", "certificate",
                  "zertifikat", "handshake"] where t.contains(k) {
            return true
        }
        return false
    }
}

// ---------------------------------------------------------------------------
// Protokoll-Client (nur Netzwerk)
// ---------------------------------------------------------------------------
final class PrinterClient {
    let ip: String
    let community: String
    let basePath: String
    let tls: Bool
    let timeout: Double
    private let http: HTTPClient
    private let lock = NSLock()
    private var okCombo: (String, Bool)?       // ep_ipp_op_auto
    private var queryCombo: (String, Bool)?    // ep_ipp_query

    init(settings: PrinterSettings) {
        let h = PrinterProto.host(settings.ip)
        ip = h.isEmpty ? PrinterProto.defaultIP : h
        community = settings.community.trimmed.isEmpty ? "public" : settings.community.trimmed
        let p = settings.ippBasePath.trimmed
        basePath = p.isEmpty ? "/ipp/print" : (p.hasPrefix("/") ? p : "/" + p)
        tls = settings.ippTLS
        timeout = Double(max(1, settings.timeout))
        let pw = settings.adminPassword
        // Mit Admin-Passwort immer als "admin" (Digest/Basic nur auf 401)
        http = HTTPClient(user: pw.isEmpty ? nil : "admin", password: pw.isEmpty ? nil : pw)
        http.allowInsecure = true
    }

    private var snmp: SNMPClient { SNMPClient(host: ip, community: community, timeout: timeout) }

    private func getCombo(_ query: Bool) -> (String, Bool)? {
        lock.lock(); defer { lock.unlock() }
        return query ? queryCombo : okCombo
    }

    private func setCombo(_ c: (String, Bool), query: Bool) {
        lock.lock(); defer { lock.unlock() }
        if query { queryCombo = c } else { okCombo = c }
    }

    private func viaText(_ path: String, _ t: Bool) -> String {
        "\(t ? "ipps" : "ipp")://\(ip):631\(path)"
    }

    // ---- IPP: eine Operation (ep_ipp_op) ----
    func ippOp(_ opName: String, path: String, tls useTLS: Bool, jobId: Int? = nil, extra: Data = Data(),
               document: Data? = nil, timeout tmo: Double = 6) async -> PrinterIPPResult {
        guard let op = PrinterProto.ippOps[opName] else {
            return PrinterIPPResult(ok: false, status: nil, msg: "unbekannte IPP-Operation \(opName)")
        }
        let uri = viaText(path, useTLS)
        var body = Data([2, 0, UInt8((op >> 8) & 0xff), UInt8(op & 0xff)])
        let rid = Int(Date().timeIntervalSince1970) & 0x7FFFFFFF
        body.append(PrinterProto.be32(rid))
        body.append(0x01)
        body.append(PrinterProto.ippAttr(0x47, "attributes-charset", "utf-8"))
        body.append(PrinterProto.ippAttr(0x48, "attributes-natural-language", "de"))
        body.append(PrinterProto.ippAttr(0x45, "printer-uri", uri))
        body.append(PrinterProto.ippAttr(0x42, "requesting-user-name", "StudioControlApp"))
        if let j = jobId {
            body.append(PrinterProto.ippAttr(0x21, "job-id", PrinterProto.be32(j)))
        }
        if opName == "Get-Jobs" {
            body.append(PrinterProto.ippAttr(0x44, "which-jobs", "not-completed"))
            let names = ["job-id", "job-name", "job-state", "job-originating-user-name",
                         "job-k-octets", "time-at-creation"]
            for (n, a) in names.enumerated() {
                body.append(PrinterProto.ippAttr(0x44, n == 0 ? "requested-attributes" : "", a))
            }
        }
        if opName == "Get-Printer-Attributes" {
            for (n, a) in PrinterProto.printerAttrNames.enumerated() {
                body.append(PrinterProto.ippAttr(0x44, n == 0 ? "requested-attributes" : "", a))
            }
        }
        if opName == "Print-Job" {
            body.append(PrinterProto.ippAttr(0x42, "job-name", "StudioControlApp"))
            body.append(PrinterProto.ippAttr(0x49, "document-format", "application/octet-stream"))
        }
        body.append(extra)
        body.append(0x03)
        if let d = document { body.append(d) }

        guard let url = URL(string: "\(useTLS ? "https" : "http")://\(ip):631\(path)") else {
            let e = NetError.badAddress(ip)
            return PrinterIPPResult(ok: false, status: nil, msg: "Netzfehler: \(e.localizedDescription)", netError: e)
        }
        do {
            let (data, resp) = try await http.request("POST", url, headers: ["Content-Type": "application/ipp"],
                                                      body: body, timeout: tmo)
            if resp.statusCode == 401 {
                return PrinterIPPResult(ok: false, status: nil,
                                        msg: "HTTP 401 - Anmeldung nötig (Admin-Kennwort in den Einstellungen)")
            }
            if resp.statusCode != 200 {
                return PrinterIPPResult(ok: false, status: nil, msg: "HTTP \(resp.statusCode)")
            }
            do {
                let (st, groups) = try PrinterProto.ippParse(data)
                var txt = PrinterProto.ippStatus[st] ?? String(format: "0x%04X", st)
                if let ops = groups.first(where: { $0.tag == 0x01 }) {
                    let sm = PrinterProto.text(ops.attrs, "status-message")
                    if !sm.isEmpty { txt += " - \(sm)" }
                }
                return PrinterIPPResult(ok: st < 0x0100, status: st, msg: txt, groups: groups)
            } catch {
                return PrinterIPPResult(ok: false, status: nil, msg: "Antwort unlesbar: \(error.localizedDescription)")
            }
        } catch {
            return PrinterIPPResult(ok: false, status: nil, msg: "Netzfehler: \(error.localizedDescription)",
                                    netError: error)
        }
    }

    // ---- IPP mit Pfad/TLS-Automatik (ep_ipp_op_auto) ----
    func ippAuto(_ opName: String, jobId: Int? = nil, extra: Data = Data(), document: Data? = nil,
                 timeout tmo: Double = 6) async -> PrinterIPPResult {
        var combos: [(String, Bool)] = []
        if let c = getCombo(false) { combos.append(c) }
        for p in [basePath, "/ipp/print", "/ipp", "/"] {
            for t in [tls, !tls] where !combos.contains(where: { $0.0 == p && $0.1 == t }) {
                combos.append((p, t))
            }
        }
        var res = PrinterIPPResult(ok: false, status: nil, msg: "IPP nicht erreichbar")
        var netErr = 0
        for (p, t) in combos {
            res = await ippOp(opName, path: p, tls: t, jobId: jobId, extra: extra, document: document, timeout: tmo)
            if let e = res.netError {
                if opName == "Print-Job" && !PrinterProto.isRefused(e) {
                    // Job evtl. schon angenommen -> NICHT mit anderem Pfad/TLS wiederholen
                    res.msg = "UNSICHER: " + res.msg
                    return res
                }
                netErr += 1
                if netErr >= 2 { return res }      // HTTP und HTTPS nicht erreichbar
                continue
            }
            if res.status != nil {
                setCombo((p, t), query: false)
                res.via = viaText(p, t)
                return res
            }
            if res.msg.contains("Anmeldung") { return res }
        }
        return res
    }

    // ---- Get-Printer-Attributes (ersetzt pyipp in ep_ipp_query) ----
    func queryPrinter() async -> PrinterIPPQuery {
        var paths = [basePath]
        for p in ["/ipp/print", "/", "/ipp/", "/ipp/printer"] where !paths.contains(p) { paths.append(p) }
        var combos: [(String, Bool)] = []
        if let q = getCombo(true) { combos.append(q) }
        for t in [tls, !tls] {
            for p in paths where !combos.contains(where: { $0.0 == p && $0.1 == t }) {
                combos.append((p, t))
            }
        }
        var deadTLS = Set<Bool>()
        var lastErr = "IPP nicht erreichbar"
        for (p, t) in combos {
            if deadTLS.contains(t) { continue }
            let r = await ippOp("Get-Printer-Attributes", path: p, tls: t, timeout: max(6, timeout + 3))
            if r.netError != nil {
                // Verbindung zu diesem Schema geht nicht -> andere Pfade gleichen Schemas sparen
                deadTLS.insert(t)
                lastErr = r.msg
                continue
            }
            if r.ok, let a = r.printerAttrs {
                setCombo((p, t), query: true)
                return PrinterIPPQuery(attrs: a, via: viaText(p, t), error: "")
            }
            lastErr = r.msg
            if r.msg.contains("Anmeldung") { break }
        }
        return PrinterIPPQuery(attrs: nil, via: "", error: lastErr)
    }

    // ---- SNMP ----
    func snmpBasics() async -> Result<[String: SNMPValue], Error> {
        let names = PrinterProto.oidNames
        let oids = names.map { PrinterProto.oid[$0] ?? "" }
        do {
            let r = try await snmp.get(oids)
            var out: [String: SNMPValue] = [:]
            for (i, n) in names.enumerated() where i < r.count {
                let v = r[i].1
                switch v {
                case .noSuch, .null: continue
                default:
                    if v.description.trimmed.isEmpty { continue }
                    out[n] = v
                }
            }
            return .success(out)
        } catch {
            return .failure(error)
        }
    }

    /// EPSON-CTRL "st" (ep_get_status)
    func status() async -> Result<PrinterST2, Error> {
        do {
            guard let v = try await snmp.get(PrinterProto.ctrlOID(cmd: "st", payload: [1])) else {
                throw NetError.protocolError("keine SNMP-Antwort")
            }
            return .success(try PrinterProto.parseST2(v.data))
        } catch {
            return .failure(error)
        }
    }

    /// ep_snmp_ink: prtMarkerSupplies Beschreibung/Max/Stand
    func snmpInk() async -> [PrinterInkRaw] {
        let s = snmp
        let desc = (try? await s.walk(PrinterProto.supDesc, maxRows: 64)) ?? []
        let lvl = (try? await s.walk(PrinterProto.supLvl, maxRows: 64)) ?? []
        let mx = (try? await s.walk(PrinterProto.supMax, maxRows: 64)) ?? []
        var out: [PrinterInkRaw] = []
        let n = max(desc.count, lvl.count)
        for i in 0..<n {
            let name = i < desc.count ? desc[i].1.description.trimmed : "Supply \(i + 1)"
            let cur = i < lvl.count ? Int(lvl[i].1.intValue ?? -1) : -1
            let mxi = i < mx.count ? Int(mx[i].1.intValue ?? 100) : 100
            var pct: Int? = nil
            if cur >= 0 && mxi > 0 {
                pct = max(0, min(100, Int((Double(cur) * 100.0 / Double(mxi)).rounded())))
            }
            out.append(PrinterInkRaw(name: name, pct: pct))
        }
        return out
    }

    // ---- Ports ----
    func scanPorts() async -> [PrinterPortState] {
        let host = ip
        let t = timeout
        let open: [Int: Bool] = await withTaskGroup(of: (Int, Bool).self, returning: [Int: Bool].self) { g in
            for (p, _) in PrinterProto.scanPorts {
                g.addTask {
                    let ok = await TCPConnection.probe(host: host, port: UInt16(p), timeout: t)
                    return (p, ok)
                }
            }
            var m: [Int: Bool] = [:]
            for await (p, ok) in g { m[p] = ok }
            return m
        }
        return PrinterProto.scanPorts.map { PrinterPortState(port: $0.0, label: $0.1, open: open[$0.0] ?? false) }
    }

    // ---- Wartungs-Sendewege ----
    func rawSend(_ data: Data, port: UInt16 = 9100) async -> (Bool, String) {
        do {
            let c = try TCPConnection(host: ip, port: port)
            try await c.connect(timeout: 5)
            try await c.send(data)
            c.close()
            return (true, "\(data.count) Bytes an \(ip):\(port) gesendet.")
        } catch {
            return (false, "Fehler: \(error.localizedDescription)")
        }
    }

    /// Minimaler LPR-Client (RFC 1179) wie ep_lpr_send
    func lprSend(_ data: Data, queue: String = "PASSTHRU", label: String = "StudioControlApp") async -> (Bool, String) {
        let host = "iPhone"
        let job = Int(Date().timeIntervalSince1970) % 1000
        let num = String(format: "%03d", job)
        let cfn = "cfA" + num + host
        let dfn = "dfA" + num + host
        let ctrl = Data("H\(host)\nPstudio\nJ\(label)\nN\(label)\nl\(dfn)\nU\(dfn)\n".utf8)
        var dataStage = false
        var conn: TCPConnection? = nil
        do {
            let c = try TCPConnection(host: ip, port: 515)
            conn = c
            try await c.connect(timeout: 10)
            func cmd(_ b: Data) async throws {
                try await c.send(b)
                let r = try await c.read(count: 1, timeout: 10)
                if r != Data([0x00]) {
                    throw NetError.protocolError("LPR abgelehnt (Antwort \(r.hex))")
                }
            }
            var q = Data([0x02])
            q.append(Data(queue.utf8))
            q.append(0x0a)
            try await cmd(q)
            try await cmd(Data("\u{02}\(ctrl.count) \(cfn)\n".utf8))
            var cd = ctrl
            cd.append(0x00)
            try await cmd(cd)
            try await cmd(Data("\u{03}\(data.count) \(dfn)\n".utf8))
            dataStage = true
            var dd = data
            dd.append(0x00)
            try await cmd(dd)
            c.close()
            return (true, "LPR-Job (\(data.count) Bytes) an \(ip):515 angenommen.")
        } catch {
            conn?.close()
            if dataStage {
                // Daten evtl. schon beim Drucker -> kein zweiter Sendeweg
                return (false, "UNSICHER: LPR-Daten gesendet, Bestätigung fehlt (\(error.localizedDescription))")
            }
            return (false, "LPR-Fehler an \(ip):515: \(error.localizedDescription)")
        }
    }

    /// ep_ipp_print_raw: rohe Epson-Daten als IPP Print-Job (application/octet-stream)
    func ippPrintRaw(_ data: Data) async -> (Bool, String) {
        let res = await ippAuto("Print-Job", document: data, timeout: 15)
        var jid = ""
        if let j = res.jobs.first, let id = j["job-id"]?.first?.intValue { jid = " als Job \(id)" }
        if res.ok {
            let via = res.via.map { "  [\($0)]" } ?? ""
            return (true, "IPP-Job angenommen\(jid) (\(data.count) Bytes)\(via)")
        }
        return (false, "IPP Print-Job: \(res.msg)")
    }

    /// ep_maint_send: lpr | raw | ipp | auto (LPR -> IPP -> RAW)
    func maintSend(_ data: Data, transport: String) async -> (Bool, String) {
        switch transport {
        case "raw": return await rawSend(data)
        case "lpr": return await lprSend(data)
        case "ipp": return await ippPrintRaw(data)
        default: break
        }
        var msgs: [String] = []
        for name in ["LPR 515", "IPP 631", "RAW 9100"] {
            let r: (Bool, String)
            if name == "LPR 515" {
                r = await lprSend(data)
            } else if name == "IPP 631" {
                r = await ippPrintRaw(data)
            } else {
                r = await rawSend(data)
            }
            if r.0 {
                let before = msgs.isEmpty ? "" : "  (vorher: \(msgs.joined(separator: " | ")))"
                return (true, "\(name): \(r.1)\(before)")
            }
            msgs.append("\(name): \(r.1)")
            if r.1.contains("UNSICHER") {
                // Befehl ist vermutlich angekommen - nicht doppelt ausfuehren
                return (false, msgs.joined(separator: " | ") + "  -> kein weiterer Sendeweg (Doppel-Ausführung vermeiden)")
            }
        }
        return (false, msgs.joined(separator: " | "))
    }
}

// ---------------------------------------------------------------------------
// Wartungsbefehle / Bestaetigungen
// ---------------------------------------------------------------------------
enum PrinterMaint: String {
    case nozzle, clean, power, vi, feed

    var label: String {
        switch self {
        case .nozzle: return "Düsentest"
        case .clean: return "Druckkopfreinigung"
        case .power: return "POWER-Reinigung"
        case .vi: return "Statusblatt"
        case .feed: return "Papierführung reinigen"
        }
    }

    var data: Data {
        switch self {
        case .nozzle: return PrinterProto.seqNozzle()
        case .clean: return PrinterProto.seqClean(group: 0, power: false)
        case .power: return PrinterProto.seqClean(group: 0, power: true)
        case .vi: return PrinterProto.seqVersionInfo()
        case .feed: return PrinterProto.paperFeed
        }
    }

    var isCleaning: Bool { self == .clean || self == .power }
}

enum PrinterConfirm {
    case maint(PrinterMaint)
    case cancelJob(Int)
    case cancelAll
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
@MainActor
final class PrinterModel: DeviceModel {
    @Published var settings = PrinterSettings()
    @Published var info = PrinterInfo()
    @Published var inks: [PrinterInk] = []
    @Published var inkSource = ""
    @Published var st2 = PrinterST2()
    @Published var st2Error: String?
    @Published var jobs: [PrinterJob] = []
    @Published var jobStatus = ""
    @Published var maintStatus = ""
    @Published var ports: [PrinterPortState] = []
    @Published var ippVia = ""

    private var client: PrinterClient?
    private var watchToken = 0
    private var lastClean = Date.distantPast
    private var cleanCount = 0
    private var lastInkWarn: [String]? = nil
    private var lastIPPError: String? = nil
    private var lastSNMPError: String? = nil

    init() {
        super.init(id: "printer", title: "Drucker", subtitle: "Epson WorkForce WF-7830",
                   symbol: "printer.fill", tint: Color(hex: 0x8E8E93))
    }

    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override var pollInterval: Double { 10 }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(PrinterSettings.self, "printer") { settings = s }
        client = nil
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "printer")
        client = nil
    }

    var host: String {
        let h = PrinterProto.host(settings.ip)
        return h.isEmpty ? PrinterProto.defaultIP : h
    }

    var webConfigURL: URL? {
        URL(string: "\(PrinterProto.scheme(settings.webScheme))://\(host)/")
    }

    private func currentClient() -> PrinterClient {
        if let c = client { return c }
        let c = PrinterClient(settings: settings)
        client = c
        return c
    }

    // ---- Status ----
    override func refresh() async {
        let c = currentClient()
        await refreshSafely {
            async let q = c.queryPrinter()
            async let s = c.snmpBasics()
            async let st = c.status()
            let ipp = await q
            let snmp = await s
            let stat = await st

            var inf = PrinterInfo()
            var raw: [(String, Int?, String)] = []      // Name, Prozent, Farbschluessel
            var source = ""

            if let a = ipp.attrs {
                let dev = PrinterProto.deviceID(PrinterProto.text(a, "printer-device-id"))
                inf.name = PrinterProto.text(a, "printer-name")
                let mm = PrinterProto.text(a, "printer-make-and-model")
                inf.model = !mm.isEmpty ? mm : (dev["MDL"] ?? dev["MODEL"] ?? dev["MFG"] ?? dev["MANUFACTURER"] ?? "")
                inf.serial = dev["SN"] ?? dev["SERN"] ?? dev["SERIALNUMBER"] ?? ""
                inf.firmware = PrinterProto.text(a, "printer-firmware-string-version")
                inf.location = PrinterProto.text(a, "printer-location")
                let stText = PrinterProto.ippStateText(a["printer-state"]?.first?.intValue)
                let stMsg = PrinterProto.text(a, "printer-state-message")
                inf.state = (stText + "  " + stMsg).trimmed
                if let up = a["printer-up-time"]?.first?.intValue, up > 0 {
                    inf.uptime = PrinterProto.fmtUptime(up)
                }
                inf.reasons = (a["printer-state-reasons"] ?? []).map { $0.text }.filter { !$0.isEmpty && $0 != "none" }
                let names = a["marker-names"] ?? []
                let colors = a["marker-colors"] ?? []
                let levels = a["marker-levels"] ?? []
                for i in 0..<names.count {
                    let lv = i < levels.count ? (levels[i].intValue ?? -1) : -1
                    let pct: Int? = lv >= 0 ? min(100, lv) : nil
                    let col = i < colors.count ? colors[i].text : ""
                    let nm = names[i].text
                    raw.append((nm, pct, col.isEmpty || col == "none" ? nm : col))
                }
                if !raw.isEmpty { source = "IPP" }
                self.ippVia = ipp.via
                self.lastIPPError = nil
            } else {
                self.ippVia = ""
                if self.lastIPPError != ipp.error { self.addLog("IPP: \(ipp.error)", error: true) }
                self.lastIPPError = ipp.error
            }

            var snmpOK = false
            switch snmp {
            case .success(let g):
                snmpOK = true
                func sv(_ k: String) -> String { g[k]?.description.trimmed ?? "" }
                inf.pages = sv("lifeCount")
                inf.sysName = sv("sysName")
                inf.sysDescr = sv("sysDescr")
                if inf.serial.isEmpty { inf.serial = sv("prtSerial") }
                if inf.name.isEmpty {
                    inf.name = [sv("prtName"), sv("sysName"), sv("sysDescr")].first(where: { !$0.isEmpty }) ?? ""
                }
                if inf.model.isEmpty {
                    inf.model = [sv("prtName"), sv("sysDescr")].first(where: { !$0.isEmpty }) ?? ""
                }
                if inf.state.isEmpty {
                    let eb: UInt8? = g["hrPrinterError"]?.data.first
                    inf.state = PrinterProto.snmpStatusText(status: g["hrPrinterStatus"]?.intValue, errByte: eb)
                }
                if inf.uptime.isEmpty, let tt = g["sysUpTime"]?.intValue, tt > 0 {
                    inf.uptime = PrinterProto.fmtUptime(Int(tt / 100))
                }
            case .failure(let e):
                let m = e.localizedDescription
                if ipp.attrs != nil && self.lastSNMPError != m { self.addLog("SNMP: \(m)", error: true) }
                self.lastSNMPError = m
            }
            if snmpOK { self.lastSNMPError = nil }

            if ipp.attrs == nil && !snmpOK {
                throw NetError.protocolError("Weder IPP noch SNMP erreichbar (\(ipp.error))")
            }

            if raw.isEmpty && snmpOK {
                let sink = await c.snmpInk()
                raw = sink.map { ($0.name, $0.pct, $0.name) }
                if !raw.isEmpty { source = "SNMP" }
            }

            switch stat {
            case .success(let d):
                self.st2 = d
                self.st2Error = nil
            case .failure(let e):
                self.st2Error = "nicht lesbar: \(e.localizedDescription)"
            }

            self.info = inf
            self.inkSource = source
            self.applyInks(raw)
            self.summary = self.makeSummary()

            if ipp.attrs != nil {
                let jr = await c.ippAuto("Get-Jobs")
                self.applyJobs(jr, quiet: true)
            }
        }
    }

    private func applyInks(_ raw: [(String, Int?, String)]) {
        let warn = max(0, min(100, settings.inkWarnPct))
        var out: [PrinterInk] = []
        var lowNames: [String] = []
        for (i, r) in raw.enumerated() {
            let name = r.0.isEmpty ? "Supply" : r.0
            let low = r.1 != nil && (r.1 ?? 0) <= warn
            if low { lowNames.append("\(name) (\(r.1 ?? 0)%)") }
            out.append(PrinterInk(id: i, name: name, pct: r.1, color: PrinterProto.colorFor(r.2), low: low))
        }
        inks = out
        if !lowNames.isEmpty {
            let key = lowNames.sorted()
            if lastInkWarn != key {
                lastInkWarn = key
                addLog("WARNUNG: Tinte niedrig (<= \(warn)%): \(lowNames.joined(separator: ", "))", error: true)
            }
        } else {
            lastInkWarn = nil
        }
    }

    private func makeSummary() -> String {
        var parts: [String] = []
        if let s = st2.values["Status"] {
            parts.append(s.prefix(1).uppercased() + s.dropFirst())
        } else if !info.state.isEmpty {
            parts.append(info.state)
        }
        if let f = st2.values["Fehler"] { parts.append(f) }
        let pcts = inks.compactMap { $0.pct }
        if let mn = pcts.min() { parts.append("Tinte min. \(mn) %") }
        return parts.isEmpty ? "Verbunden" : parts.joined(separator: " · ")
    }

    func readStatus() {
        let c = currentClient()
        Task {
            self.busy = true
            let r = await c.status()
            self.busy = false
            switch r {
            case .success(let d):
                self.st2 = d
                self.st2Error = nil
                self.summary = self.makeSummary()
            case .failure(let e):
                self.st2Error = "nicht lesbar: \(e.localizedDescription)"
                self.addLog("SNMP-Status (EPSON-CTRL st): \(e.localizedDescription)", error: true)
            }
        }
    }

    // ---- Wartung ----
    func confirmText(_ k: PrinterMaint) -> String {
        if k == .feed {
            return "Ein leeres Blatt durchziehen (Papierführung reinigen)?\nVorher Normalpapier einlegen."
        }
        var t = "\(k.label) am Drucker \(host) auslösen?"
        if k.isCleaning {
            t += "\n\nDie Reinigung verbraucht Tinte. Erst einen Düsentest machen und nur reinigen, wenn Linien fehlen."
            if k == .power {
                t += "\n\nPOWER-Reinigung verbraucht SEHR viel Tinte und füllt die Wartungsbox. Nur wenn normale Reinigung nicht hilft."
            }
            if Date().timeIntervalSince(lastClean) < 600 && cleanCount >= 2 {
                t += "\n\nACHTUNG: Bereits \(cleanCount) Reinigungen in den letzten 10 min. Epson empfiehlt danach ca. 6 h Pause."
            }
        }
        return t
    }

    func runMaint(_ k: PrinterMaint) {
        if k.isCleaning {
            if Date().timeIntervalSince(lastClean) > 600 { cleanCount = 0 }
            cleanCount += 1
            lastClean = Date()
        }
        let data = k.data
        let tr = settings.maintTransport
        let label = k.label
        let c = currentClient()
        maintStatus = "\(label) wird gesendet …"
        Task {
            self.busy = true
            let r = await c.maintSend(data, transport: tr)
            self.busy = false
            if k == .feed {
                self.addLog((r.0 ? "OK  Leerblatt - " : "FEHLER  ") + r.1, error: !r.0)
                self.maintStatus = (r.0 ? "Leerblatt gesendet: " : "FEHLER: ") + r.1
                if r.0 { Haptics.success() } else { Haptics.error() }
                return
            }
            self.addLog((r.0 ? "OK  " : "FEHLER  ") + "\(label): \(r.1)", error: !r.0)
            if r.0 {
                Haptics.success()
                self.maintStatus = "\(label) gesendet - beobachte Druckerstatus …"
                self.startWatch(label)
            } else {
                Haptics.error()
                self.maintStatus = "\(label) FEHLGESCHLAGEN: \(r.1)"
            }
        }
    }

    /// Nach einem Wartungsbefehl 30 s lang alle 3 s den Status lesen
    private func startWatch(_ label: String) {
        watchToken += 1
        let token = watchToken
        let c = currentClient()
        Task {
            await pause(1.5)
            var seen = Set<String>()
            var reacted = false
            for n in 0...10 {
                if token != self.watchToken { return }
                let r = await c.status()
                if token != self.watchToken { return }
                switch r {
                case .success(let d):
                    self.st2 = d
                    self.st2Error = nil
                    if let s = d.values["Status"], !seen.contains(s) {
                        seen.insert(s)
                        self.addLog("\(label) - Druckerstatus: \(s)")
                    }
                    if let code = d.code, [0x01, 0x02, 0x07, 0x0F].contains(code) {
                        self.maintStatus = "\(label): Drucker reagiert (\(d.values["Status"] ?? ""))"
                        reacted = true
                    }
                case .failure(let e):
                    self.st2Error = "nicht lesbar: \(e.localizedDescription)"
                }
                if n < 10 { await pause(3) }
            }
            if !reacted && token == self.watchToken {
                self.maintStatus = "\(label): Job angenommen, aber keine Statusänderung gesehen - Sendeweg wechseln?"
            }
        }
    }

    // ---- Druckauftraege / Steuerung (IPP) ----
    private func applyJobs(_ r: PrinterIPPResult, quiet: Bool = false) {
        if r.ok {
            var list: [PrinterJob] = []
            for (i, j) in r.jobs.enumerated() {
                let jid = j["job-id"]?.first?.intValue
                let stv = j["job-state"]?.first?.intValue
                let stText = stv.map { PrinterProto.jobState[$0] ?? String($0) } ?? ""
                list.append(PrinterJob(id: jid ?? -(i + 1), jobId: jid,
                                       name: PrinterProto.text(j, "job-name"),
                                       state: stText,
                                       user: PrinterProto.text(j, "job-originating-user-name"),
                                       kOctets: PrinterProto.text(j, "job-k-octets")))
            }
            jobs = list
            jobStatus = list.count == 1 ? "1 offener Auftrag" : "\(list.count) offene Aufträge"
        } else if !quiet {
            var msg = r.msg
            if let v = r.via { msg += "  [\(v)]" }
            jobStatus = "Get-Jobs: \(msg)"
            addLog("FEHLER  IPP Get-Jobs: \(msg)", error: true)
        }
    }

    func loadJobs() {
        let c = currentClient()
        jobStatus = "Get-Jobs …"
        Task {
            self.busy = true
            let r = await c.ippAuto("Get-Jobs")
            self.busy = false
            self.applyJobs(r)
        }
    }

    func ippAction(_ op: String, jobId: Int? = nil, extra: Data = Data(), reloadJobs: Bool = false) {
        let c = currentClient()
        jobStatus = "\(op) …"
        Task {
            self.busy = true
            var r = await c.ippAuto(op, jobId: jobId, extra: extra)
            if op == "Cancel-Jobs" && r.status == 0x0501 {
                r = await c.ippAuto("Purge-Jobs")
            }
            self.busy = false
            var msg = r.msg
            if let v = r.via { msg += "  [\(v)]" }
            self.jobStatus = "\(op): \(msg)"
            self.addLog((r.ok ? "OK  " : "FEHLER  ") + "IPP \(op): \(msg)", error: !r.ok)
            if r.ok { Haptics.success() } else { Haptics.error() }
            if reloadJobs {
                await pause(0.8)
                let j = await c.ippAuto("Get-Jobs")
                self.applyJobs(j)
            }
        }
    }

    func checkPorts() {
        let c = currentClient()
        Task {
            self.busy = true
            let p = await c.scanPorts()
            self.busy = false
            self.ports = p
            self.addLog("Port-Scan: " + p.map { "\($0.port) \($0.open ? "offen" : "zu")" }.joined(separator: ", "))
        }
    }

    func openWebConfig() {
        guard let url = webConfigURL else { return }
        UIApplication.shared.open(url, options: [:], completionHandler: nil)
        addLog("Web Config geöffnet: \(url.absoluteString)")
    }

    func copyAdminPassword() {
        UIPasteboard.general.string = settings.adminPassword
        Haptics.success()
        addLog("Admin-Kennwort in die Zwischenablage kopiert")
    }

    override func disconnect() {
        watchToken += 1
    }
}

// ---------------------------------------------------------------------------
// Ansicht
// ---------------------------------------------------------------------------
struct PrinterView: View {
    @ObservedObject var model: PrinterModel
    @State private var confirm: PrinterConfirm?

    var body: some View {
        DevicePage(model: model, settings: { PrinterSettingsView(model: model) }) {
            deviceSection
            inkSection
            statusSection
            maintSection
            jobsSection
            controlSection
            reachSection
            webSection
        }
        .alert(confirmTitle,
               isPresented: Binding(get: { confirm != nil }, set: { if !$0 { confirm = nil } }),
               presenting: confirm) { c in
            Button(confirmButton(c), role: confirmDestructive(c) ? ButtonRole.destructive : nil) {
                execute(c)
            }
            Button("Abbrechen", role: .cancel) {}
        } message: { c in
            Text(confirmMessage(c))
        }
    }

    // ---- Bestaetigung ----
    private var confirmTitle: String {
        guard let c = confirm else { return "" }
        switch c {
        case .maint(let k): return k.label
        case .cancelJob: return "Auftrag abbrechen"
        case .cancelAll: return "Alle abbrechen"
        }
    }

    private func confirmButton(_ c: PrinterConfirm) -> String {
        switch c {
        case .maint(let k): return k == .feed ? "Leerblatt drucken" : "Auslösen"
        case .cancelJob: return "Auftrag abbrechen"
        case .cancelAll: return "Alle abbrechen"
        }
    }

    private func confirmDestructive(_ c: PrinterConfirm) -> Bool {
        switch c {
        case .maint(let k): return k.isCleaning
        case .cancelJob, .cancelAll: return true
        }
    }

    private func confirmMessage(_ c: PrinterConfirm) -> String {
        switch c {
        case .maint(let k): return model.confirmText(k)
        case .cancelJob(let id): return "Auftrag \(id) abbrechen?"
        case .cancelAll: return "ALLE offenen Druckaufträge am Drucker abbrechen?"
        }
    }

    private func execute(_ c: PrinterConfirm) {
        switch c {
        case .maint(let k): model.runMaint(k)
        case .cancelJob(let id): model.ippAction("Cancel-Job", jobId: id, reloadJobs: true)
        case .cancelAll: model.ippAction("Cancel-Jobs", reloadJobs: true)
        }
    }

    private func dash(_ s: String) -> String { s.isEmpty ? "–" : s }

    // ---- Abschnitte ----
    private var deviceSection: some View {
        Section("Gerät") {
            Group {
                ValueRow(label: "Name", value: dash(model.info.name))
                ValueRow(label: "Modell", value: dash(model.info.model))
                ValueRow(label: "Seriennummer", value: dash(model.info.serial.isEmpty ? (model.st2.values["Seriennummer"] ?? "") : model.info.serial))
                ValueRow(label: "Firmware", value: model.info.firmware.isEmpty ? "n/a (in Web Config)" : model.info.firmware)
                ValueRow(label: "Status", value: dash(model.info.state))
            }
            Group {
                ValueRow(label: "Laufzeit", value: dash(model.info.uptime))
                ValueRow(label: "Seitenzähler", value: dash(model.info.pages))
                ValueRow(label: "Hostname", value: dash(model.info.sysName))
                if !model.info.sysDescr.isEmpty {
                    ValueRow(label: "Beschreibung", value: model.info.sysDescr)
                }
                if !model.ippVia.isEmpty {
                    ValueRow(label: "IPP", value: model.ippVia)
                }
            }
        }
    }

    private var inkSection: some View {
        Section {
            if model.inks.isEmpty {
                Text("Keine Tintendaten (IPP/SNMP).").foregroundStyle(.secondary)
            } else {
                ForEach(model.inks) { ink in
                    PrinterInkRow(ink: ink)
                }
            }
        } header: {
            Text("Tinte")
        } footer: {
            Text(model.inkSource.isEmpty
                 ? "Quelle: IPP (bevorzugt) bzw. SNMP Printer-MIB."
                 : "Quelle: \(model.inkSource). Rot = unter \(model.settings.inkWarnPct) %.")
        }
    }

    private var statusSection: some View {
        Section {
            ForEach(Array(PrinterProto.st2Keys.indices), id: \.self) { i in
                ValueRow(label: PrinterProto.st2Keys[i].1, value: model.st2.values[PrinterProto.st2Keys[i].0] ?? "–",
                         valueColor: PrinterProto.st2Keys[i].0 == "Fehler" ? Color.red : Color.secondary)
            }
            if let e = model.st2Error {
                Text(e).font(.footnote).foregroundStyle(.red)
            }
            if !model.info.reasons.isEmpty {
                ValueRow(label: "IPP-Meldungen", value: model.info.reasons.joined(separator: ", "))
            }
            Button {
                model.readStatus()
            } label: {
                Label("Status lesen", systemImage: "arrow.clockwise")
            }
        } header: {
            Text("Druckerstatus (SNMP)")
        }
    }

    private var maintSection: some View {
        Section {
            TileGrid {
                ActionTile(title: "Düsentest drucken", symbol: "circle.grid.3x3.fill", tint: .blue, disabled: model.busy) {
                    confirm = .maint(.nozzle)
                }
                ActionTile(title: "Druckkopfreinigung", symbol: "drop.fill", tint: .teal, disabled: model.busy) {
                    confirm = .maint(.clean)
                }
                ActionTile(title: "Power-Reinigung", symbol: "bolt.fill", tint: .orange, disabled: model.busy) {
                    confirm = .maint(.power)
                }
                ActionTile(title: "Statusblatt drucken", symbol: "doc.text", tint: .indigo, disabled: model.busy) {
                    confirm = .maint(.vi)
                }
                ActionTile(title: "Papierführung reinigen", symbol: "doc", tint: .gray, disabled: model.busy) {
                    confirm = .maint(.feed)
                }
            }
            Picker("Sendeweg", selection: Binding(get: { model.settings.maintTransport },
                                                  set: { model.settings.maintTransport = $0; model.saveSettings() })) {
                ForEach(PrinterProto.transports, id: \.self) { k in
                    Text(PrinterProto.transportName(k)).tag(k)
                }
            }
            if !model.maintStatus.isEmpty {
                Text(model.maintStatus).font(.footnote.weight(.semibold)).foregroundStyle(.blue)
            }
        } header: {
            Text("Wartung")
        } footer: {
            Text("A4-Normalpapier einlegen - Düsentest und Statusblatt werden gedruckt. Nach jedem Befehl wird 30 s lang der Druckerstatus gelesen. Kommt keine Bestätigung, wird nie über einen zweiten Weg erneut gesendet (keine Doppel-Reinigung).")
        }
    }

    private var jobsSection: some View {
        Section {
            if model.jobs.isEmpty {
                Text("Keine offenen Aufträge").foregroundStyle(.secondary)
            }
            ForEach(model.jobs) { job in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(job.name.isEmpty ? "Auftrag" : job.name).lineLimit(1)
                        Text(jobLine(job)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let jid = job.jobId {
                        Button {
                            confirm = .cancelJob(jid)
                        } label: {
                            Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Auftrag abbrechen")
                    }
                }
            }
            Button {
                model.loadJobs()
            } label: {
                Label("Aufträge laden", systemImage: "list.bullet")
            }
            Button(role: .destructive) {
                confirm = .cancelAll
            } label: {
                Label("Alle abbrechen", systemImage: "xmark.octagon")
            }
            if !model.jobStatus.isEmpty {
                Text(model.jobStatus).font(.footnote).foregroundStyle(.secondary)
            }
        } header: {
            Text("Druckaufträge (IPP)")
        }
    }

    private func jobLine(_ j: PrinterJob) -> String {
        var p: [String] = []
        if let id = j.jobId { p.append("ID \(id)") }
        if !j.state.isEmpty { p.append(j.state) }
        if !j.user.isEmpty { p.append(j.user) }
        if !j.kOctets.isEmpty { p.append("\(j.kOctets) kB") }
        return p.joined(separator: " · ")
    }

    private var controlSection: some View {
        Section {
            TileGrid(columns: 3) {
                ActionTile(title: "Pausieren", symbol: "pause.fill", tint: .orange, disabled: model.busy) {
                    model.ippAction("Pause-Printer")
                }
                ActionTile(title: "Fortsetzen", symbol: "play.fill", tint: .green, disabled: model.busy) {
                    model.ippAction("Resume-Printer")
                }
                ActionTile(title: "Identifizieren", symbol: "speaker.wave.2.fill", tint: .blue, disabled: model.busy) {
                    model.ippAction("Identify-Printer", extra: PrinterProto.identifyExtra)
                }
            }
        } header: {
            Text("Druckersteuerung")
        } footer: {
            Text("Pause/Fortsetzen/Abbrechen kann das Admin-Kennwort erfordern. „nicht unterstützt“ = von der Drucker-Firmware nicht per IPP freigegeben.")
        }
    }

    private var reachSection: some View {
        Section {
            ForEach(model.ports) { p in
                HStack(spacing: 10) {
                    Circle().fill(p.open ? Color.green : Color.gray.opacity(0.5)).frame(width: 9, height: 9)
                    Text("\(p.port)").font(.body.monospacedDigit().weight(.semibold)).frame(width: 52, alignment: .leading)
                    Text(p.label).foregroundStyle(.secondary).lineLimit(1)
                    Spacer()
                    Text(p.open ? "offen" : "zu").foregroundStyle(p.open ? Color.green : Color.secondary)
                }
            }
            Button {
                model.checkPorts()
            } label: {
                Label("Ports prüfen", systemImage: "network")
            }
        } header: {
            Text("Erreichbarkeit")
        }
    }

    private var webSection: some View {
        Section {
            Button {
                model.openWebConfig()
            } label: {
                Label("Web Config öffnen", systemImage: "safari")
            }
            if !model.settings.adminPassword.isEmpty {
                Button {
                    model.copyAdminPassword()
                } label: {
                    Label("Admin-Kennwort kopieren", systemImage: "doc.on.doc")
                }
            }
        } header: {
            Text("Web Config")
        } footer: {
            Text("Öffnet \(model.webConfigURL?.absoluteString ?? "-") in Safari. Firmware-Update, Protokolle und Papiereinstellungen dort bzw. am Bedienfeld.")
        }
    }
}

struct PrinterInkRow: View {
    let ink: PrinterInk

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(ink.name).font(.subheadline.weight(.semibold)).lineLimit(1)
                Spacer()
                Text(ink.pct.map { "\($0) %" } ?? "n/a")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(ink.low ? Color.red : Color.secondary)
            }
            LevelBar(value: Double(ink.pct ?? 0) / 100.0, tint: ink.low ? Color.red : Color(hex: ink.color), height: 10)
        }
        .padding(.vertical, 2)
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct PrinterSettingsView: View {
    @ObservedObject var model: PrinterModel
    @State private var s: PrinterSettings

    init(model: PrinterModel) {
        _model = ObservedObject(wrappedValue: model)
        _s = State(initialValue: model.settings)
    }

    var body: some View {
        SettingsSheet(title: "Drucker", onSave: save) {
            Section {
                FieldRow(label: "IP-Adresse", text: $s.ip, placeholder: PrinterProto.defaultIP, keyboard: .numbersAndPunctuation)
                FieldRow(label: "SNMP-Community", text: $s.community, placeholder: "public")
                FieldRow(label: "Timeout (s)", text: intBinding($s.timeout), placeholder: "3", keyboard: .numberPad)
            } header: {
                Text("Verbindung")
            }
            Section {
                FieldRow(label: "IPP-Pfad", text: $s.ippBasePath, placeholder: "/ipp/print")
                Toggle("IPPS (TLS)", isOn: $s.ippTLS)
                FieldRow(label: "Admin-Kennwort", text: $s.adminPassword, placeholder: "optional", secure: true)
            } header: {
                Text("IPP")
            } footer: {
                Text("Das Admin-Kennwort wird für IPP (Benutzer „admin“, Digest/Basic) verwendet. Pfad und TLS werden bei Bedarf automatisch durchprobiert.")
            }
            Section {
                Picker("Protokoll", selection: $s.webScheme) {
                    Text("http").tag("http")
                    Text("https").tag("https")
                }
            } header: {
                Text("Web Config")
            }
            Section {
                Picker("Sendeweg", selection: $s.maintTransport) {
                    ForEach(PrinterProto.transports, id: \.self) { k in
                        Text(PrinterProto.transportName(k)).tag(k)
                    }
                }
                FieldRow(label: "Tinten-Warnung (%)", text: intBinding($s.inkWarnPct), placeholder: "15", keyboard: .numberPad)
            } header: {
                Text("Wartung & Tinte")
            }
        }
    }

    private func save() {
        var n = s
        let h = PrinterProto.host(n.ip)
        n.ip = h.isEmpty ? PrinterProto.defaultIP : h
        n.community = n.community.trimmed.isEmpty ? "public" : n.community.trimmed
        n.ippBasePath = n.ippBasePath.trimmed.isEmpty ? "/ipp/print" : n.ippBasePath.trimmed
        n.webScheme = PrinterProto.scheme(n.webScheme)
        n.timeout = max(1, n.timeout)
        n.inkWarnPct = max(0, min(100, n.inkWarnPct))
        if !PrinterProto.transports.contains(n.maintTransport) { n.maintTransport = "ipp" }
        model.settings = n
        model.saveSettings()
    }
}
