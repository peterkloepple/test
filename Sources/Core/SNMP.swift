// ===========================================================================
//  SNMP.swift - Studio Control iOS - SNMP v2c (Get, GetNext, Walk, Set) ueber UDP 161
//  Autor: T. Pfeiffer
// ===========================================================================
import Foundation

enum SNMPValue: CustomStringConvertible {
    case int(Int64)
    case string(Data)
    case oid(String)
    case ip(String)
    case counter(UInt64)      // Counter32/Gauge32/TimeTicks/Counter64
    case timeticks(UInt64)
    case null
    case noSuch                // noSuchObject / noSuchInstance / endOfMibView
    case other(UInt8, Data)

    var description: String {
        switch self {
        case .int(let v): return String(v)
        case .string(let d): return SNMPValue.text(d)
        case .oid(let o): return o
        case .ip(let s): return s
        case .counter(let v): return String(v)
        case .timeticks(let v): return String(v)
        case .null: return ""
        case .noSuch: return ""
        case .other(_, let d): return d.hex
        }
    }

    var intValue: Int64? {
        switch self {
        case .int(let v): return v
        case .counter(let v), .timeticks(let v): return Int64(truncatingIfNeeded: v)
        case .string(let d): return Int64(SNMPValue.text(d).trimmed)
        default: return nil
        }
    }

    var data: Data {
        switch self {
        case .string(let d): return d
        case .other(_, let d): return d
        default: return Data(description.utf8)
        }
    }

    static func text(_ d: Data) -> String {
        let printable = d.allSatisfy { ($0 >= 0x20 && $0 < 0x7f) || $0 == 0x0a || $0 == 0x0d || $0 == 0x09 || $0 == 0 }
        if printable {
            return String(decoding: d.filter { $0 != 0 }, as: UTF8.self)
        }
        if let s = String(data: d, encoding: .utf8) { return s }
        return d.latin1
    }
}

enum SNMPSetType {
    case integer(Int64)
    case unsigned(UInt32)     // Gauge32/Unsigned32
    case octets(Data)
}

struct SNMPClient {
    var host: String
    var community: String = "public"
    var port: UInt16 = 161
    var timeout: TimeInterval = 2
    var retries: Int = 1

    // ---- oeffentliche Aufrufe ----
    func get(_ oids: [String]) async throws -> [(String, SNMPValue)] {
        try await exchange(pdu: 0xA0, varbinds: oids.map { ($0, Data([0x05, 0x00])) })
    }

    func get(_ oid: String) async throws -> SNMPValue? {
        let r = try await get([oid])
        return r.first?.1
    }

    func getNext(_ oid: String) async throws -> (String, SNMPValue)? {
        try await exchange(pdu: 0xA1, varbinds: [(oid, Data([0x05, 0x00]))]).first
    }

    /// Alle Werte unterhalb von `base` (max. `maxRows`).
    func walk(_ base: String, maxRows: Int = 512) async throws -> [(String, SNMPValue)] {
        var out: [(String, SNMPValue)] = []
        var cur = base
        let prefix = base + "."
        while out.count < maxRows {
            guard let (oid, val) = try await getNext(cur) else { break }
            if !oid.hasPrefix(prefix) { break }
            if case .noSuch = val { break }
            out.append((oid, val))
            if oid == cur { break }
            cur = oid
        }
        return out
    }

    func set(_ oid: String, _ value: SNMPSetType) async throws -> SNMPValue? {
        let enc: Data
        switch value {
        case .integer(let v): enc = BER.tlv(0x02, BER.intBytes(v))
        case .unsigned(let v): enc = BER.tlv(0x42, BER.uintBytes(UInt64(v)))
        case .octets(let d): enc = BER.tlv(0x04, d)
        }
        return try await exchange(pdu: 0xA3, varbinds: [(oid, enc)]).first?.1
    }

    // ---- intern ----
    private func exchange(pdu: UInt8, varbinds: [(String, Data)]) async throws -> [(String, SNMPValue)] {
        let reqId = Int64(Int32.random(in: 1...0x7fffffff))
        var vbl = Data()
        for (oid, val) in varbinds {
            vbl.append(BER.tlv(0x30, BER.tlv(0x06, try BER.encodeOID(oid)) + val))
        }
        let pduBody = BER.tlv(0x02, BER.intBytes(reqId)) + BER.tlv(0x02, Data([0])) + BER.tlv(0x02, Data([0]))
            + BER.tlv(0x30, vbl)
        let msg = BER.tlv(0x30, BER.tlv(0x02, Data([1])) + BER.tlv(0x04, Data(community.utf8)) + BER.tlv(pdu, pduBody))
        let resp = try await UDPExchange.request(host: host, port: port, payload: msg, timeout: timeout, retries: retries)
        return try parse(resp)
    }

    private func parse(_ d: Data) throws -> [(String, SNMPValue)] {
        var r = BER.Reader(d)
        let (t0, msg) = try r.next()
        guard t0 == 0x30 else { throw NetError.protocolError("SNMP: ungültige Antwort") }
        var m = BER.Reader(msg)
        _ = try m.next()                       // version
        _ = try m.next()                       // community
        let (_, pdu) = try m.next()            // response PDU
        var p = BER.Reader(pdu)
        _ = try p.next()                       // request id
        let (_, es) = try p.next()             // error status
        let errStatus = BER.int(es)
        _ = try p.next()                       // error index
        if errStatus != 0 {
            let names = [1: "tooBig", 2: "noSuchName", 3: "badValue", 4: "readOnly", 5: "genErr", 6: "noAccess",
                         7: "wrongType", 10: "wrongValue", 16: "authorizationError", 17: "notWritable"]
            throw NetError.protocolError("SNMP-Fehler: \(names[Int(errStatus)] ?? String(errStatus))")
        }
        let (_, vbl) = try p.next()
        var vr = BER.Reader(vbl)
        var out: [(String, SNMPValue)] = []
        while !vr.atEnd {
            let (_, vb) = try vr.next()
            var v = BER.Reader(vb)
            let (_, oidB) = try v.next()
            let (vt, vv) = try v.next()
            out.append((BER.decodeOID(oidB), BER.value(vt, vv)))
        }
        return out
    }
}

enum BER {
    static func len(_ n: Int) -> Data {
        if n < 0x80 { return Data([UInt8(n)]) }
        var b: [UInt8] = []
        var v = n
        while v > 0 { b.insert(UInt8(v & 0xff), at: 0); v >>= 8 }
        return Data([0x80 | UInt8(b.count)] + b)
    }

    static func tlv(_ t: UInt8, _ v: Data) -> Data { Data([t]) + len(v.count) + v }

    static func intBytes(_ v: Int64) -> Data {
        var b: [UInt8] = []
        var x = v
        repeat {
            b.insert(UInt8(truncatingIfNeeded: x & 0xff), at: 0)
            x >>= 8
        } while !(x == 0 && b[0] & 0x80 == 0) && !(x == -1 && b[0] & 0x80 != 0)
        return Data(b)
    }

    static func uintBytes(_ v: UInt64) -> Data {
        var b: [UInt8] = []
        var x = v
        repeat { b.insert(UInt8(x & 0xff), at: 0); x >>= 8 } while x > 0
        if b[0] & 0x80 != 0 { b.insert(0, at: 0) }
        return Data(b)
    }

    static func encodeOID(_ s: String) throws -> Data {
        let parts = s.trimmingCharacters(in: CharacterSet(charactersIn: ". ")).split(separator: ".").compactMap { UInt64($0) }
        guard parts.count >= 2 else { throw NetError.protocolError("OID ungültig: \(s)") }
        var out = Data([UInt8(parts[0] * 40 + parts[1])])
        for p in parts.dropFirst(2) {
            var stack: [UInt8] = [UInt8(p & 0x7f)]
            var v = p >> 7
            while v > 0 { stack.insert(UInt8(v & 0x7f) | 0x80, at: 0); v >>= 7 }
            out.append(contentsOf: stack)
        }
        return out
    }

    static func decodeOID(_ d: Data) -> String {
        let b = [UInt8](d)
        guard !b.isEmpty else { return "" }
        var parts = [String(b[0] / 40), String(b[0] % 40)]
        var v: UInt64 = 0
        for x in b.dropFirst() {
            v = (v << 7) | UInt64(x & 0x7f)
            if x & 0x80 == 0 { parts.append(String(v)); v = 0 }
        }
        return parts.joined(separator: ".")
    }

    static func int(_ d: Data) -> Int64 {
        var v: Int64 = 0
        let b = [UInt8](d)
        guard !b.isEmpty else { return 0 }
        if b[0] & 0x80 != 0 { v = -1 }
        for x in b { v = (v << 8) | Int64(x) }
        return v
    }

    static func uint(_ d: Data) -> UInt64 {
        var v: UInt64 = 0
        for x in d { v = (v << 8) | UInt64(x) }
        return v
    }

    static func value(_ t: UInt8, _ d: Data) -> SNMPValue {
        switch t {
        case 0x02: return .int(int(d))
        case 0x04: return .string(d)
        case 0x05: return .null
        case 0x06: return .oid(decodeOID(d))
        case 0x40: return .ip(d.map { String($0) }.joined(separator: "."))
        case 0x41, 0x42, 0x46: return .counter(uint(d))
        case 0x43: return .timeticks(uint(d))
        case 0x80, 0x81, 0x82: return .noSuch
        default: return .other(t, d)
        }
    }

    struct Reader {
        let d: [UInt8]
        var i = 0
        init(_ data: Data) { d = [UInt8](data) }
        var atEnd: Bool { i >= d.count }

        mutating func next() throws -> (UInt8, Data) {
            guard i + 2 <= d.count else { throw NetError.protocolError("BER: Ende") }
            let t = d[i]
            var n = Int(d[i + 1])
            i += 2
            if n & 0x80 != 0 {
                let k = n & 0x7f
                guard k <= 4, i + k <= d.count else { throw NetError.protocolError("BER: Laenge") }
                n = 0
                for _ in 0..<k { n = (n << 8) | Int(d[i]); i += 1 }
            }
            guard i + n <= d.count else { throw NetError.protocolError("BER: abgeschnitten") }
            let v = Data(d[i..<(i + n)])
            i += n
            return (t, v)
        }
    }
}
