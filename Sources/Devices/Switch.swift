// ===========================================================================
//  Switch.swift - Studio Control iOS - Cisco managed Switch (SNMP v2c)
//  Autor: T. Pfeiffer
//
//  Port aus sc.py (SwitchModule, portiert aus Q-SYS Plugin Cisco_SG350_Port_Overview):
//    Poll:   ifAdminStatus, ifOperStatus, ifSpeed, ifAlias, pethPsePortAdminEnable,
//            ARP (ipNetToMedia), FDB (dot1dTpFdbPort), dot1dBasePortIfIndex,
//            dot1qPvid, sysName
//    SET:    ifAdminStatus (Integer), PoE AdminEnable (Integer), dot1qPvid (Unsigned32)
//    LLDP:   lldpRemSysName / lldpRemPortId / lldpRemPortDesc
//  Zusaetzlich (Standard-MIB-II / IF-MIB, nicht im Python): sysDescr, sysUpTime,
//  sysLocation, sysContact, Port-Zaehler (ifHC*Octets, Errors), ifAlias SET.
// ===========================================================================
import Foundation
import SwiftUI

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct SwitchSettings: Codable {
    var model: String = "SG350-28P"
    var ip: String = "192.168.1.254"
    var community: String = "public"
    var pollInterval: Int = 30
    var portCount: Int = 28
    var poePorts: Int = 24
    var management: Bool = false
    var writeCommunity: String = "private"

    enum CodingKeys: String, CodingKey {
        case model, ip, community, pollInterval, portCount, poePorts, management, writeCommunity
    }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        model = try c.decodeIfPresent(String.self, forKey: .model) ?? "SG350-28P"
        ip = try c.decodeIfPresent(String.self, forKey: .ip) ?? "192.168.1.254"
        community = try c.decodeIfPresent(String.self, forKey: .community) ?? "public"
        pollInterval = try c.decodeIfPresent(Int.self, forKey: .pollInterval) ?? 30
        portCount = try c.decodeIfPresent(Int.self, forKey: .portCount) ?? 28
        poePorts = try c.decodeIfPresent(Int.self, forKey: .poePorts) ?? 24
        management = try c.decodeIfPresent(Bool.self, forKey: .management) ?? false
        writeCommunity = try c.decodeIfPresent(String.self, forKey: .writeCommunity) ?? "private"
    }
}

// ---------------------------------------------------------------------------
// Modell-Katalog (Ports gesamt = ifIndex 1..N, PoE-Ports) - wie SW_MODEL_LIST
// ---------------------------------------------------------------------------
enum SwitchCatalog {
    static let custom = "Custom (manuell)"

    static let list: [(name: String, ports: Int, poe: Int)] = [
        ("Custom (manuell)", 0, 0),
        ("SG250-08", 8, 0), ("SG250-08HP", 8, 8), ("SG250-10P", 10, 8),
        ("SG250-18", 18, 0), ("SG250-26", 26, 0), ("SG250-26P", 26, 24),
        ("SG250-26HP", 26, 24), ("SG250-50", 50, 0), ("SG250-50P", 50, 48),
        ("SG250-50HP", 50, 48),
        ("SG350-10", 10, 0), ("SG350-10P", 10, 8), ("SG350-10MP", 10, 8),
        ("SG350-28", 28, 0), ("SG350-28P", 28, 24), ("SG350-28MP", 28, 24),
        ("SG350-52", 52, 0), ("SG350-52P", 52, 48), ("SG350-52MP", 52, 48),
        ("SG350X-24", 28, 0), ("SG350X-24P", 28, 24), ("SG350X-24MP", 28, 24),
        ("SG350X-48", 52, 0), ("SG350X-48P", 52, 48), ("SG350X-48MP", 52, 48),
        ("SG550X-24", 28, 0), ("SG550X-24P", 28, 24), ("SG550X-24MP", 28, 24),
        ("SG550X-48", 52, 0), ("SG550X-48P", 52, 48), ("SG550X-48MP", 52, 48),
        ("CBS250-8T", 8, 0), ("CBS250-8PP-D", 8, 8), ("CBS250-8P-E-2G", 10, 8),
        ("CBS250-8FP-E-2G", 10, 8), ("CBS250-16T-2G", 18, 0), ("CBS250-16P-2G", 18, 16),
        ("CBS250-24T-4G", 28, 0), ("CBS250-24P-4G", 28, 24), ("CBS250-24FP-4G", 28, 24),
        ("CBS250-24T-4X", 28, 0), ("CBS250-24P-4X", 28, 24), ("CBS250-24FP-4X", 28, 24),
        ("CBS250-48T-4G", 52, 0), ("CBS250-48P-4G", 52, 48), ("CBS250-48PP-4G", 52, 48),
        ("CBS250-48T-4X", 52, 0), ("CBS250-48P-4X", 52, 48),
        ("CBS350-8T-E-2G", 10, 0), ("CBS350-8P-E-2G", 10, 8), ("CBS350-8FP-E-2G", 10, 8),
        ("CBS350-8P-2G", 10, 8), ("CBS350-8MP-2X", 10, 8), ("CBS350-16T-2G", 18, 0),
        ("CBS350-16P-2G", 18, 16), ("CBS350-16FP-2G", 18, 16), ("CBS350-24T-4G", 28, 0),
        ("CBS350-24P-4G", 28, 24), ("CBS350-24FP-4G", 28, 24), ("CBS350-24S-4G", 28, 0),
        ("CBS350-24T-4X", 28, 0), ("CBS350-24P-4X", 28, 24), ("CBS350-24FP-4X", 28, 24),
        ("CBS350-48T-4G", 52, 0), ("CBS350-48P-4G", 52, 48), ("CBS350-48FP-4G", 52, 48),
        ("CBS350-48T-4X", 52, 0), ("CBS350-48P-4X", 52, 48), ("CBS350-48FP-4X", 52, 48),
        ("SF350-08", 8, 0), ("SF352-08", 10, 0), ("SF352-08P", 10, 8),
        ("SF352-08MP", 10, 8), ("SF350-24", 28, 0), ("SF350-24P", 28, 24),
        ("SF350-24MP", 28, 24), ("SF350-48", 52, 0), ("SF350-48P", 52, 48),
        ("SF350-48MP", 52, 48),
        ("SF550X-24", 28, 0), ("SF550X-24P", 28, 24), ("SF550X-24MP", 28, 24),
        ("SF550X-48", 52, 0), ("SF550X-48P", 52, 48), ("SF550X-48MP", 52, 48),
    ]

    static var names: [String] { list.map { $0.name } }

    /// (Ports, PoE) des Modells; (0, 0) = Custom / unbekannt
    static func lookup(_ name: String) -> (ports: Int, poe: Int) {
        for m in list where m.name == name { return (m.ports, m.poe) }
        return (0, 0)
    }

    /// wie sw_speed_str()
    static func speedText(_ bps: Int64) -> String {
        if bps >= 1_000_000_000 { return "1 Gbit" }
        if bps >= 100_000_000 { return "100 Mbit" }
        if bps >= 10_000_000 { return "10 Mbit" }
        return ""
    }

    static func two(_ v: UInt64) -> String { v < 10 ? "0\(v)" : "\(v)" }

    /// TimeTicks (1/100 s) lesbar
    static func uptimeText(_ ticks: UInt64) -> String {
        let s = ticks / 100
        let d = s / 86400
        let h = (s % 86400) / 3600
        let m = (s % 3600) / 60
        let sec = s % 60
        let hms = "\(two(h)):\(two(m)):\(two(sec))"
        return d > 0 ? "\(d) Tage \(hms)" : hms
    }

    static func rateText(_ bps: Double) -> String {
        if bps >= 1_000_000_000 { return String(format: "%.2f Gbit/s", bps / 1_000_000_000) }
        if bps >= 1_000_000 { return String(format: "%.1f Mbit/s", bps / 1_000_000) }
        if bps >= 1_000 { return String(format: "%.1f kbit/s", bps / 1_000) }
        return String(format: "%.0f bit/s", bps)
    }

    static func poeDetectText(_ v: Int) -> String {
        switch v {
        case 1: return "Deaktiviert"
        case 2: return "Suche Verbraucher"
        case 3: return "Liefert Strom"
        case 4: return "Fehler"
        case 5: return "Test"
        case 6: return "Anderer Fehler"
        default: return "\(v)"
        }
    }
}

// ---------------------------------------------------------------------------
// Daten
// ---------------------------------------------------------------------------
struct SwitchPort: Equatable {
    var admin: Int = 2
    var oper: Int = 2
    var speed: Int64 = 0
    var poe: Int = 2
    var ip: String = ""
    var mac: String = ""
    var desc: String = ""
    var vlan: Int? = nil

    var adminText: String { admin == 1 ? "UP" : "DOWN" }
    var linkText: String { admin != 1 ? "DISABLED" : (oper == 1 ? "UP" : "DOWN") }
    var speedText: String { oper == 1 ? SwitchCatalog.speedText(speed) : "" }

    func poeText(port: Int, poePorts: Int) -> String {
        port > poePorts ? "n/a" : (poe == 1 ? "EIN" : "AUS")
    }

    /// Farbe wie Front-LED: gruen = Link 1G, orange = Link < 1G, grau = gesperrt, leer = kein Link
    var color: Color {
        if admin != 1 { return Color(.systemGray3) }
        if oper == 1 { return speed >= 1_000_000_000 ? Color.green : Color.orange }
        return Color(.tertiarySystemFill)
    }

    var textColor: Color {
        if admin == 1 && oper == 1 { return .white }
        return .secondary
    }
}

struct SwitchSystemInfo {
    var name: String = ""
    var descr: String = ""
    var uptime: UInt64? = nil
    var location: String = ""
    var contact: String = ""
}

struct SwitchLLDPNeighbor: Identifiable {
    var id: String { "\(localPort).\(remIndex)" }
    var localPort: Int
    var remIndex: String
    var sysName: String = ""
    var portId: String = ""
    var portDesc: String = ""
}

struct SwitchPortCounters {
    var time: Date = Date()
    var name: String = ""
    var descr: String = ""
    var highSpeed: UInt64? = nil
    var inOctets: UInt64? = nil
    var outOctets: UInt64? = nil
    var inErrors: UInt64? = nil
    var outErrors: UInt64? = nil
    var inDiscards: UInt64? = nil
    var outDiscards: UInt64? = nil
    var poeDetect: Int? = nil
    var inRate: Double? = nil
    var outRate: Double? = nil
}

struct SwitchPollResult {
    var ports: [Int: SwitchPort]
    var bpOfIf: [Int: Int]
    var system: SwitchSystemInfo
}

// ---------------------------------------------------------------------------
// SNMP-Client (nur Netzwerk)
// ---------------------------------------------------------------------------
struct SwitchSNMPClient {
    let host: String
    let community: String
    let writeCommunity: String

    // OIDs wie SW_OID
    static let ifAdminStatus = "1.3.6.1.2.1.2.2.1.7"
    static let ifOperStatus = "1.3.6.1.2.1.2.2.1.8"
    static let ifSpeed = "1.3.6.1.2.1.2.2.1.5"
    static let ifAlias = "1.3.6.1.2.1.31.1.1.1.18"
    static let poeAdminEnable = "1.3.6.1.2.1.105.1.1.1.3"
    static let poeDetectStatus = "1.3.6.1.2.1.105.1.1.1.6"
    static let sysName = "1.3.6.1.2.1.1.5.0"
    static let arp = "1.3.6.1.2.1.4.22.1.2"
    static let fdb = "1.3.6.1.2.1.17.4.3.1.2"
    static let bpif = "1.3.6.1.2.1.17.1.4.1.2"
    static let pvid = "1.3.6.1.2.1.17.7.1.4.5.1.1"
    static let lldpRemPortId = "1.0.8802.1.1.2.1.4.1.1.7"
    static let lldpRemPortDesc = "1.0.8802.1.1.2.1.4.1.1.8"
    static let lldpRemSysName = "1.0.8802.1.1.2.1.4.1.1.9"
    // Standard MIB-II / IF-MIB (Zusatz)
    static let sysDescr = "1.3.6.1.2.1.1.1.0"
    static let sysUpTime = "1.3.6.1.2.1.1.3.0"
    static let sysContact = "1.3.6.1.2.1.1.4.0"
    static let sysLocation = "1.3.6.1.2.1.1.6.0"
    static let ifDescr = "1.3.6.1.2.1.2.2.1.2"
    static let ifInDiscards = "1.3.6.1.2.1.2.2.1.13"
    static let ifInErrors = "1.3.6.1.2.1.2.2.1.14"
    static let ifOutDiscards = "1.3.6.1.2.1.2.2.1.19"
    static let ifOutErrors = "1.3.6.1.2.1.2.2.1.20"
    static let ifName = "1.3.6.1.2.1.31.1.1.1.1"
    static let ifHCInOctets = "1.3.6.1.2.1.31.1.1.1.6"
    static let ifHCOutOctets = "1.3.6.1.2.1.31.1.1.1.10"
    static let ifHighSpeed = "1.3.6.1.2.1.31.1.1.1.15"

    // Python: timeout=3, retries=0
    private var reader: SNMPClient { SNMPClient(host: host, community: community, port: 161, timeout: 3, retries: 0) }
    private var writer: SNMPClient { SNMPClient(host: host, community: writeCommunity, port: 161, timeout: 3, retries: 0) }

    // ---- Hilfen ----
    static func tail(_ oid: String, _ base: String) -> String {
        String(oid.dropFirst(base.count + 1))
    }

    static func lastInt(_ oid: String) -> Int? {
        guard let last = oid.split(separator: ".").last else { return nil }
        return Int(last)
    }

    static func intOf(_ v: SNMPValue) -> Int? {
        guard let i = v.intValue else { return nil }
        return Int(truncatingIfNeeded: i)
    }

    static func u64(_ v: SNMPValue?) -> UInt64? {
        guard let v = v else { return nil }
        switch v {
        case .counter(let x): return x
        case .timeticks(let x): return x
        case .int(let x): return x >= 0 ? UInt64(x) : nil
        default: return nil
        }
    }

    static func text(_ v: SNMPValue?) -> String {
        guard let v = v else { return "" }
        switch v {
        case .noSuch, .null: return ""
        default: return v.description
        }
    }

    static func macText(_ d: Data) -> String {
        d.prefix(6).map { String(format: "%02X", $0) }.joined(separator: ":")
    }

    /// Walk einer Spalte wie sw_snmp_walk: Fehler -> bisher gelesene Zeilen (oder leer)
    func walkColumn(_ base: String, maxRows: Int = 2048) async -> [(String, SNMPValue)] {
        let c = reader
        var out: [(String, SNMPValue)] = []
        var cur = base
        let prefix = base + "."
        while out.count < maxRows {
            if Task.isCancelled { break }
            guard let r = try? await c.getNext(cur) else { break }
            let oid = r.0
            let val = r.1
            if !oid.hasPrefix(prefix) { break }
            if case .noSuch = val { break }
            out.append((oid, val))
            if oid == cur { break }
            cur = oid
        }
        return out
    }

    // ---- Poll (wie SwitchModule.do_poll) ----
    func poll(portCount: Int, poePorts: Int) async throws -> SwitchPollResult {
        // System zuerst: wirft bei Zeitueberschreitung -> Geraet nicht erreichbar
        let sysVals = try await reader.get([SwitchSNMPClient.sysDescr, SwitchSNMPClient.sysUpTime,
                                            SwitchSNMPClient.sysContact, SwitchSNMPClient.sysName,
                                            SwitchSNMPClient.sysLocation])
        var sys = SwitchSystemInfo()
        for (oid, v) in sysVals {
            switch oid {
            case SwitchSNMPClient.sysDescr: sys.descr = SwitchSNMPClient.text(v)
            case SwitchSNMPClient.sysUpTime: sys.uptime = SwitchSNMPClient.u64(v)
            case SwitchSNMPClient.sysContact: sys.contact = SwitchSNMPClient.text(v)
            case SwitchSNMPClient.sysName: sys.name = SwitchSNMPClient.text(v)
            case SwitchSNMPClient.sysLocation: sys.location = SwitchSNMPClient.text(v)
            default: break
            }
        }

        var data: [Int: SwitchPort] = [:]
        if portCount >= 1 {
            for i in 1...portCount { data[i] = SwitchPort() }
        }

        func inRange(_ p: Int) -> Bool { p >= 1 && p <= portCount }

        var b = SwitchSNMPClient.ifAdminStatus
        for (oid, v) in await walkColumn(b) {
            if let p = Int(SwitchSNMPClient.tail(oid, b)), inRange(p), let x = SwitchSNMPClient.intOf(v) {
                data[p]?.admin = x
            }
        }
        b = SwitchSNMPClient.ifOperStatus
        for (oid, v) in await walkColumn(b) {
            if let p = Int(SwitchSNMPClient.tail(oid, b)), inRange(p), let x = SwitchSNMPClient.intOf(v) {
                data[p]?.oper = x
            }
        }
        b = SwitchSNMPClient.ifSpeed
        for (oid, v) in await walkColumn(b) {
            if let p = Int(SwitchSNMPClient.tail(oid, b)), inRange(p), let x = v.intValue {
                data[p]?.speed = x
            }
        }
        b = SwitchSNMPClient.ifAlias
        for (oid, v) in await walkColumn(b) {
            if let p = Int(SwitchSNMPClient.tail(oid, b)), inRange(p) {
                data[p]?.desc = SwitchSNMPClient.text(v)
            }
        }
        // PoE: tail = grp.port
        b = SwitchSNMPClient.poeAdminEnable
        for (oid, v) in await walkColumn(b) {
            if let p = SwitchSNMPClient.lastInt(oid), p >= 1, p <= poePorts, p <= portCount,
               let x = SwitchSNMPClient.intOf(v) {
                data[p]?.poe = x
            }
        }
        // ARP: mac -> ip
        var arp: [String: String] = [:]
        b = SwitchSNMPClient.arp
        for (oid, v) in await walkColumn(b) {
            let parts = SwitchSNMPClient.tail(oid, b).split(separator: ".").map { String($0) }
            let raw = v.data
            if parts.count >= 5 && raw.count >= 6 {
                let ipaddr = parts.suffix(4).joined(separator: ".")
                arp[SwitchSNMPClient.macText(raw)] = ipaddr
            }
        }
        // FDB: mac -> bridgeport
        var fdb: [String: Int] = [:]
        b = SwitchSNMPClient.fdb
        for (oid, v) in await walkColumn(b) {
            let parts = SwitchSNMPClient.tail(oid, b).split(separator: ".")
            if parts.count >= 6 {
                let bytes = parts.suffix(6).compactMap { Int($0) }
                if bytes.count == 6, let bp = SwitchSNMPClient.intOf(v) {
                    let mac = bytes.map { String(format: "%02X", $0 & 0xff) }.joined(separator: ":")
                    fdb[mac] = bp
                }
            }
        }
        // bridgeport -> ifIndex
        var bpif: [Int: Int] = [:]
        b = SwitchSNMPClient.bpif
        for (oid, v) in await walkColumn(b) {
            if let bp = SwitchSNMPClient.lastInt(oid), let ifidx = SwitchSNMPClient.intOf(v) {
                bpif[bp] = ifidx
            }
        }
        var bpOfIf: [Int: Int] = [:]
        for (bp, ifidx) in bpif { bpOfIf[ifidx] = bp }
        // VLAN (PVID): Index = dot1dBasePort
        b = SwitchSNMPClient.pvid
        for (oid, v) in await walkColumn(b) {
            if let bp = SwitchSNMPClient.lastInt(oid), let vid = SwitchSNMPClient.intOf(v) {
                let ifidx = bpif[bp] ?? bp
                if inRange(ifidx) { data[ifidx]?.vlan = vid }
            }
        }
        // MACs je Port
        var macsByPort: [Int: [String]] = [:]
        for (mac, bp) in fdb {
            if let ifidx = bpif[bp], inRange(ifidx) {
                macsByPort[ifidx, default: []].append(mac)
            }
        }
        for (ifidx, macs) in macsByPort {
            data[ifidx]?.mac = macs.sorted().joined(separator: ", ")
        }
        // IP-Zuordnung (MAC am Port -> IP aus ARP)
        for (mac, bp) in fdb.sorted(by: { $0.key < $1.key }) {
            if let ifidx = bpif[bp], let ipaddr = arp[mac], inRange(ifidx) {
                let cur = data[ifidx]?.ip ?? ""
                data[ifidx]?.ip = cur.isEmpty ? ipaddr : cur + " / " + ipaddr
            }
        }
        return SwitchPollResult(ports: data, bpOfIf: bpOfIf, system: sys)
    }

    // ---- Port-Zaehler (Detailansicht) ----
    func counters(port p: Int) async throws -> SwitchPortCounters {
        let s = "." + String(p)
        let oids = [SwitchSNMPClient.ifName + s, SwitchSNMPClient.ifDescr + s, SwitchSNMPClient.ifHighSpeed + s,
                    SwitchSNMPClient.ifHCInOctets + s, SwitchSNMPClient.ifHCOutOctets + s,
                    SwitchSNMPClient.ifInErrors + s, SwitchSNMPClient.ifOutErrors + s,
                    SwitchSNMPClient.ifInDiscards + s, SwitchSNMPClient.ifOutDiscards + s,
                    SwitchSNMPClient.poeDetectStatus + ".1" + s]
        let vals = try await reader.get(oids)
        var map: [String: SNMPValue] = [:]
        for (o, v) in vals { map[o] = v }
        var c = SwitchPortCounters()
        c.time = Date()
        c.name = SwitchSNMPClient.text(map[oids[0]])
        c.descr = SwitchSNMPClient.text(map[oids[1]])
        c.highSpeed = SwitchSNMPClient.u64(map[oids[2]])
        c.inOctets = SwitchSNMPClient.u64(map[oids[3]])
        c.outOctets = SwitchSNMPClient.u64(map[oids[4]])
        c.inErrors = SwitchSNMPClient.u64(map[oids[5]])
        c.outErrors = SwitchSNMPClient.u64(map[oids[6]])
        c.inDiscards = SwitchSNMPClient.u64(map[oids[7]])
        c.outDiscards = SwitchSNMPClient.u64(map[oids[8]])
        if let pv = map[oids[9]], let x = SwitchSNMPClient.intOf(pv) { c.poeDetect = x }
        return c
    }

    // ---- LLDP (wie show_lldp) ----
    func lldp() async -> [SwitchLLDPNeighbor] {
        var rows: [String: SwitchLLDPNeighbor] = [:]
        let cols: [(String, Int)] = [(SwitchSNMPClient.lldpRemSysName, 0),
                                     (SwitchSNMPClient.lldpRemPortId, 1),
                                     (SwitchSNMPClient.lldpRemPortDesc, 2)]
        for (base, field) in cols {
            for (oid, v) in await walkColumn(base) {
                let parts = SwitchSNMPClient.tail(oid, base).split(separator: ".").map { String($0) }
                if parts.count < 3 { continue }
                guard let lport = Int(parts[parts.count - 2]) else { continue }
                let idx = parts[parts.count - 1]
                var val = SwitchSNMPClient.text(v)
                // MAC-artige Port-IDs lesbar machen
                if case .string(let raw) = v, raw.count == 6 {
                    let printable = raw.allSatisfy { $0 >= 0x20 && $0 < 0x7f }
                    if !printable { val = SwitchSNMPClient.macText(raw) }
                }
                let key = "\(lport).\(idx)"
                var n = rows[key] ?? SwitchLLDPNeighbor(localPort: lport, remIndex: idx)
                switch field {
                case 0: n.sysName = val
                case 1: n.portId = val
                default: n.portDesc = val
                }
                rows[key] = n
            }
        }
        return rows.values.sorted { a, b in
            a.localPort != b.localPort ? a.localPort < b.localPort : a.remIndex < b.remIndex
        }
    }

    // ---- SET ----
    func setAdmin(port p: Int, up: Bool) async throws {
        _ = try await writer.set(SwitchSNMPClient.ifAdminStatus + "." + String(p), .integer(up ? 1 : 2))
    }

    func setPoE(port p: Int, on: Bool) async throws {
        _ = try await writer.set(SwitchSNMPClient.poeAdminEnable + ".1." + String(p), .integer(on ? 1 : 2))
    }

    func setPVID(bridgePort bp: Int, vlan: Int) async throws {
        _ = try await writer.set(SwitchSNMPClient.pvid + "." + String(bp), .unsigned(UInt32(vlan)))
    }

    func setAlias(port p: Int, text: String) async throws {
        _ = try await writer.set(SwitchSNMPClient.ifAlias + "." + String(p), .octets(Data(text.utf8)))
    }
}

// ---------------------------------------------------------------------------
// Modell
// ---------------------------------------------------------------------------
@MainActor
final class SwitchModel: DeviceModel {
    @Published var settings = SwitchSettings()
    @Published var ports: [Int: SwitchPort] = [:]
    @Published var system = SwitchSystemInfo()
    @Published var lldp: [SwitchLLDPNeighbor] = []
    @Published var lldpLoaded = false
    @Published var counters: [Int: SwitchPortCounters] = [:]
    @Published var counterError: String?
    @Published var exportURL: URL?
    private var bpOfIf: [Int: Int] = [:]
    private var polling = false

    init() {
        super.init(id: "switch", title: "Switch", subtitle: "Cisco managed (SNMP)",
                   symbol: "network", tint: Color(hex: 0x64D2FF))
    }

    override var pollInterval: Double { Double(max(0, settings.pollInterval)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }

    override func loadSettings() {
        if let s = SecureStore.loadCodable(SwitchSettings.self, "switch") { settings = s }
    }

    override func saveSettings() {
        SecureStore.saveCodable(settings, "switch")
        ports = [:]
        counters = [:]
    }

    var portCount: Int {
        let m = SwitchCatalog.lookup(settings.model)
        if m.ports > 0 { return m.ports }
        return max(1, settings.portCount)
    }

    var poePorts: Int {
        let m = SwitchCatalog.lookup(settings.model)
        if m.ports > 0 { return m.poe }
        return max(0, settings.poePorts)
    }

    var client: SwitchSNMPClient {
        let c = settings.community.trimmed
        let w = settings.writeCommunity.trimmed
        return SwitchSNMPClient(host: settings.ip.trimmed, community: c.isEmpty ? "public" : c,
                                writeCommunity: w.isEmpty ? "private" : w)
    }

    func port(_ p: Int) -> SwitchPort { ports[p] ?? SwitchPort() }

    var countUp: Int { ports.values.filter { $0.oper == 1 }.count }
    var countPoE: Int { ports.values.filter { $0.poe == 1 }.count }
    var countDisabled: Int { ports.values.filter { $0.admin != 1 }.count }

    override func refresh() async {
        if polling { return }
        polling = true
        defer { polling = false }
        await refreshSafely {
            let res = try await self.client.poll(portCount: self.portCount, poePorts: self.poePorts)
            self.ports = res.ports
            self.bpOfIf = res.bpOfIf
            self.system = res.system
            let name = res.system.name.isEmpty ? "" : res.system.name + " - "
            var s = "\(name)\(self.countUp) aktiv"
            if self.poePorts > 0 { s += ", \(self.countPoE) PoE" }
            if self.countDisabled > 0 { s += ", \(self.countDisabled) gesperrt" }
            self.summary = s
        }
    }

    private func requireManagement() -> Bool {
        if settings.management { return true }
        addLog("Management (SNMP SET) ist in den Einstellungen ausgeschaltet", error: true)
        return false
    }

    private func refreshAfterWrite() async {
        await pause(1)       // Python: after(1000, do_poll)
        await refresh()
    }

    // ---- Schreiben (immer nach Bestaetigung in der Oberflaeche) ----
    func setAdmin(_ p: Int, up: Bool) {
        guard requireManagement() else { return }
        let c = client
        perform("Port \(p) Admin -> \(up ? "UP" : "DOWN")") {
            try await c.setAdmin(port: p, up: up)
            await self.refreshAfterWrite()
        }
    }

    func setPoE(_ p: Int, on: Bool) {
        guard requireManagement(), p <= poePorts else { return }
        let c = client
        perform("Port \(p) PoE -> \(on ? "EIN" : "AUS")") {
            try await c.setPoE(port: p, on: on)
            await self.refreshAfterWrite()
        }
    }

    func setPVID(_ p: Int, vlan: Int) {
        guard requireManagement(), vlan >= 1, vlan <= 4094 else { return }
        let c = client
        let bp = bpOfIf[p] ?? p
        perform("Port \(p) PVID -> \(vlan)") {
            try await c.setPVID(bridgePort: bp, vlan: vlan)
            await self.refreshAfterWrite()
        }
    }

    func setAlias(_ p: Int, text: String) {
        guard requireManagement() else { return }
        let c = client
        perform("Port \(p) Beschreibung -> \"\(text)\"") {
            try await c.setAlias(port: p, text: text)
            await self.refreshAfterWrite()
        }
    }

    // ---- Zaehler + Rate ----
    func loadCounters(_ p: Int) async {
        guard isConfigured else { return }
        do {
            var c = try await client.counters(port: p)
            if let old = counters[p] {
                let dt = c.time.timeIntervalSince(old.time)
                if dt > 0.5 {
                    if let a = old.inOctets, let b = c.inOctets, b >= a { c.inRate = Double(b - a) * 8 / dt }
                    if let a = old.outOctets, let b = c.outOctets, b >= a { c.outRate = Double(b - a) * 8 / dt }
                }
            }
            counters[p] = c
            counterError = nil
        } catch is CancellationError {
            return
        } catch {
            counterError = DeviceModel.describe(error)
        }
    }

    // ---- LLDP ----
    func loadLLDP() {
        let c = client
        perform("LLDP-Nachbarn gelesen", haptic: false) {
            let rows = await c.lldp()
            self.lldp = rows
            self.lldpLoaded = true
        }
    }

    func neighbors(of p: Int) -> [SwitchLLDPNeighbor] { lldp.filter { $0.localPort == p } }

    // ---- CSV-Export (wie _export_csv: Semikolon, UTF-8 mit BOM) ----
    private static func csvField(_ s: String) -> String {
        if s.contains(";") || s.contains("\"") || s.contains("\n") || s.contains("\r") {
            return "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\""
        }
        return s
    }

    func makeCSV() {
        let model = settings.model
        let ip = settings.ip.trimmed
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.dateFormat = "yyyy-MM-dd HH:mm:ss"
        let stand = df.string(from: Date())
        df.dateFormat = "yyyyMMdd_HHmmss"
        let ts = df.string(from: Date())

        var lines: [[String]] = []
        lines.append(["Cisco Switch Port-Uebersicht"])
        lines.append(["Modell", model, "IP", ip.isEmpty ? "-" : ip, "Stand", stand])
        lines.append([])
        lines.append(["Port", "Admin", "Link", "Speed", "PoE", "IP-Adresse", "MAC-Adressen", "Beschreibung"])
        let n = portCount
        for i in 1...max(1, n) {
            let d = port(i)
            lines.append([String(i), d.adminText, d.linkText, d.speedText, d.poeText(port: i, poePorts: poePorts),
                          d.ip, d.mac, d.desc])
        }
        let text = lines.map { row in row.map { SwitchModel.csvField($0) }.joined(separator: ";") }
            .joined(separator: "\r\n") + "\r\n"
        let safeIP = (ip.isEmpty ? "switch" : ip).replacingOccurrences(of: ".", with: "-")
            .replacingOccurrences(of: ":", with: "-")
        let safeModel = model.replacingOccurrences(of: " ", with: "").replacingOccurrences(of: "(", with: "")
            .replacingOccurrences(of: ")", with: "")
        let fname = "Switch_Portuebersicht_\(safeModel)_\(safeIP)_\(ts).csv"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(fname)
        var data = Data([0xEF, 0xBB, 0xBF])
        data.append(Data(text.utf8))
        do {
            try data.write(to: url, options: .atomic)
            exportURL = url
            addLog("CSV erstellt: \(fname)")
        } catch {
            addLog("CSV-Export fehlgeschlagen: \(DeviceModel.describe(error))", error: true)
        }
    }

    // ---- Demo (Start mit -demo, ohne Netzwerk) ----
    override func loadDemo() {
        settings.model = "SG350-10P"
        settings.ip = "192.168.1.254"
        settings.portCount = 10
        settings.poePorts = 8
        settings.management = true
        // (Port, admin, oper, speed, PoE, IP, MAC, Beschreibung)
        let rows: [(Int, Int, Int, Int64, Int, String, String, String)] = [
            (1, 1, 1, 1_000_000_000, 1, "192.168.1.110", "00:10:7F:A1:22:01", "Touchpanel TSW-770"),
            (2, 1, 1, 1_000_000_000, 1, "192.168.1.100", "00:04:A5:C3:10:22", "ClickShare CX-30"),
            (3, 1, 1, 1_000_000_000, 1, "192.168.1.130", "00:60:74:5E:31:07", "Q-SYS Core 110f"),
            (4, 1, 1, 1_000_000_000, 1, "192.168.1.141", "00:1D:C1:0B:44:12", "PTZ-Kamera"),
            (5, 1, 1, 100_000_000, 2, "192.168.1.50", "00:22:FA:93:0E:5C", "Beamer XG-PH50X"),
            (6, 1, 2, 0, 2, "", "", "Reserve"),
            (7, 1, 2, 0, 2, "", "", ""),
            (8, 2, 2, 0, 2, "", "", "gesperrt"),
            (9, 1, 1, 1_000_000_000, 2, "192.168.1.1", "3C:A6:2F:11:22:33", "Uplink Fritz!Box"),
            (10, 1, 1, 1_000_000_000, 2, "192.168.1.20", "A8:5E:45:66:77:88", "Studio-PC"),
        ]
        var pm: [Int: SwitchPort] = [:]
        var cm: [Int: SwitchPortCounters] = [:]
        for r in rows {
            var p = SwitchPort()
            p.admin = r.1
            p.oper = r.2
            p.speed = r.3
            p.poe = r.4
            p.ip = r.5
            p.mac = r.6
            p.desc = r.7
            p.vlan = 1
            pm[r.0] = p
            if r.2 == 1 {
                var c = SwitchPortCounters()
                c.name = "gi\(r.0)"
                c.descr = "GigabitEthernet\(r.0)"
                c.highSpeed = UInt64(r.3 / 1_000_000)
                c.inOctets = UInt64(r.0) * 1_234_567_890
                c.outOctets = UInt64(r.0) * 987_654_321
                c.inErrors = 0
                c.outErrors = 0
                c.inDiscards = 0
                c.outDiscards = 0
                c.poeDetect = r.4 == 1 ? 3 : 2
                c.inRate = Double(r.0) * 1_250_000
                c.outRate = Double(r.0) * 640_000
                cm[r.0] = c
            }
        }
        ports = pm
        counters = cm
        counterError = nil
        var sys = SwitchSystemInfo()
        sys.name = "switch-studio"
        sys.descr = "SG350-10P 10-Port Gigabit PoE Managed Switch"
        sys.uptime = 123_456_700
        sys.location = "Studio, Rack 1"
        sys.contact = "Studio-Technik"
        system = sys
        lldp = [
            SwitchLLDPNeighbor(localPort: 3, remIndex: "1", sysName: "Core110f-Studio", portId: "LAN A", portDesc: "Q-SYS LAN A"),
            SwitchLLDPNeighbor(localPort: 9, remIndex: "2", sysName: "fritz.box", portId: "LAN 1", portDesc: "LAN 1"),
        ]
        lldpLoaded = true
        summary = "switch-studio - \(countUp) aktiv, \(countPoE) PoE, \(countDisabled) gesperrt"
    }
}

// ---------------------------------------------------------------------------
// Oberflaeche
// ---------------------------------------------------------------------------
struct SwitchPortSel: Identifiable {
    let id: Int
}

/// Bestaetigungsdialog fuer jeden SET
struct SwitchPendingWrite {
    let title: String
    let message: String
    let confirm: String
    let run: @MainActor () -> Void
}

@MainActor
struct SwitchView: View {
    @ObservedObject var model: SwitchModel
    @State private var selected: SwitchPortSel?
    @State private var showList = false

    init(model: SwitchModel) {
        _model = ObservedObject(wrappedValue: model)
    }

    var body: some View {
        DevicePage(model: model, settings: { SwitchSettingsView(model: model) }) {
            Section {
                SwitchPortGrid(ports: model.ports, portCount: model.portCount, poePorts: model.poePorts) { p in
                    selected = SwitchPortSel(id: p)
                }
                .padding(.vertical, 6)
                HStack(spacing: 0) {
                    statView("Aktiv", model.countUp, .green)
                    statView("PoE aktiv", model.countPoE, .yellow)
                    statView("Gesperrt", model.countDisabled, .gray)
                }
            } header: {
                Text("Ports (\(model.settings.model))")
            } footer: {
                Text("Grün = Link 1 Gbit, Orange = Link 10/100, Grau = gesperrt, leer = kein Link, Blitz = PoE ein. Port antippen für Details.")
            }
            systemSection
            Section {
                DisclosureGroup(isExpanded: $showList) {
                    ForEach(Array(1...max(1, model.portCount)), id: \.self) { p in
                        portRow(p)
                    }
                } label: {
                    Label("Portliste", systemImage: "list.bullet")
                }
            }
            lldpSection
            exportSection
        }
        .sheet(item: $selected) { sel in
            SwitchPortDetailView(model: model, port: sel.id)
        }
    }

    private func statView(_ title: String, _ value: Int, _ tint: Color) -> some View {
        VStack(spacing: 2) {
            Text("\(value)").font(.title2.weight(.semibold)).foregroundStyle(tint)
            Text(title).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private var systemSection: some View {
        Section("System") {
            ValueRow(label: "Name", value: model.system.name.isEmpty ? "–" : model.system.name, symbol: "tag")
            ValueRow(label: "Modell", value: model.settings.model, symbol: "network")
            ValueRow(label: "Laufzeit", value: model.system.uptime.map { SwitchCatalog.uptimeText($0) } ?? "–",
                     symbol: "clock")
            if !model.system.location.isEmpty {
                ValueRow(label: "Standort", value: model.system.location, symbol: "mappin.and.ellipse")
            }
            if !model.system.contact.isEmpty {
                ValueRow(label: "Kontakt", value: model.system.contact, symbol: "person")
            }
            if !model.system.descr.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Label("Systembeschreibung", systemImage: "info.circle")
                    Text(model.system.descr).font(.footnote).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
        }
    }

    private func portRow(_ p: Int) -> some View {
        let d = model.port(p)
        return Button {
            selected = SwitchPortSel(id: p)
        } label: {
            HStack(spacing: 10) {
                RoundedRectangle(cornerRadius: 3, style: .continuous).fill(d.color).frame(width: 14, height: 14)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Port \(p)").foregroundStyle(.primary)
                    if !d.desc.isEmpty {
                        Text(d.desc).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(d.linkText).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    if !d.ip.isEmpty {
                        Text(d.ip).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }
        }
    }

    private var lldpSection: some View {
        Section {
            Button {
                model.loadLLDP()
            } label: {
                Label(model.lldpLoaded ? "LLDP-Nachbarn neu lesen" : "LLDP-Nachbarn lesen",
                      systemImage: "point.3.connected.trianglepath.dotted")
            }
            .disabled(model.busy)
            if model.lldpLoaded && model.lldp.isEmpty {
                Text("Keine Nachbarn gefunden (LLDP muss am Switch aktiv sein).")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(model.lldp) { n in
                VStack(alignment: .leading, spacing: 2) {
                    Text("Port \(n.localPort) → \(n.sysName.isEmpty ? "?" : n.sysName)").font(.subheadline)
                    Text([n.portId, n.portDesc].filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        } header: {
            Text("LLDP-Nachbarn")
        }
    }

    private var exportSection: some View {
        Section {
            Button {
                model.makeCSV()
            } label: {
                Label("CSV-Tabelle erstellen", systemImage: "tablecells")
            }
            if let url = model.exportURL {
                ShareLink(item: url) {
                    Label("CSV teilen / in Dateien sichern", systemImage: "square.and.arrow.up")
                }
            }
        } header: {
            Text("Export")
        } footer: {
            Text("Port-Übersicht als CSV (Semikolon, öffnet direkt in Excel).")
        }
    }
}

/// Port-Raster wie die Frontblende: oben ungerade, unten gerade Ports
@MainActor
struct SwitchPortGrid: View {
    let ports: [Int: SwitchPort]
    let portCount: Int
    let poePorts: Int
    let onTap: (Int) -> Void

    struct Slot: Identifiable {
        let id: Int
        let port: Int?
    }

    private var columnsCount: Int { max(1, min(12, (portCount + 1) / 2)) }

    private var slots: [Slot] {
        var out: [Slot] = []
        let cols = columnsCount
        var start = 1
        var idx = 0
        while start <= portCount {
            for row in 0..<2 {
                for c in 0..<cols {
                    let p = start + c * 2 + row
                    out.append(Slot(id: idx, port: p <= portCount ? p : nil))
                    idx += 1
                }
            }
            start += cols * 2
        }
        return out
    }

    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: columnsCount), spacing: 4) {
            ForEach(slots) { s in
                if let p = s.port {
                    cell(p)
                } else {
                    Color.clear.aspectRatio(1, contentMode: .fit)
                }
            }
        }
    }

    private func cell(_ p: Int) -> some View {
        let d = ports[p] ?? SwitchPort()
        let poeOn = p <= poePorts && d.poe == 1
        return Button {
            Haptics.tap()
            onTap(p)
        } label: {
            ZStack(alignment: .topTrailing) {
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(d.color)
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .stroke(Color.primary.opacity(0.12), lineWidth: 0.5)
                Text("\(p)")
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(d.textColor)
                    .minimumScaleFactor(0.6)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                if poeOn {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 7, weight: .bold))
                        .foregroundStyle(Color.yellow)
                        .padding(2)
                }
            }
            .aspectRatio(1, contentMode: .fit)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Port \(p), \(d.linkText)")
    }
}

/// Detailblatt eines Ports (Status, Zaehler, LLDP, Verwaltung)
@MainActor
struct SwitchPortDetailView: View {
    @ObservedObject var model: SwitchModel
    let port: Int
    @Environment(\.dismiss) private var dismiss
    @State private var aliasText = ""
    @State private var pvidText = ""
    @State private var inputError: String?
    @State private var pending: SwitchPendingWrite?
    @State private var showConfirm = false

    init(model: SwitchModel, port: Int) {
        _model = ObservedObject(wrappedValue: model)
        self.port = port
    }

    private var d: SwitchPort { model.port(port) }
    private var isPoE: Bool { port <= model.poePorts }
    private var mgmt: Bool { model.settings.management }

    var body: some View {
        NavigationStack {
            List {
                statusSection
                countersSection
                if !model.neighbors(of: port).isEmpty {
                    Section("LLDP-Nachbar") {
                        ForEach(model.neighbors(of: port)) { n in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(n.sysName.isEmpty ? "?" : n.sysName).font(.subheadline)
                                Text([n.portId, n.portDesc].filter { !$0.isEmpty }.joined(separator: " · "))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                managementSection
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Port \(port)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarLeading) {
                    if model.busy { ProgressView() }
                }
            }
            .alert(Text(pending?.title ?? ""), isPresented: $showConfirm, presenting: pending) { p in
                Button(p.confirm, role: .destructive) { p.run() }
                Button("Abbrechen", role: .cancel) {}
            } message: { p in
                Text(p.message)
            }
            .onAppear {
                aliasText = d.desc
                pvidText = d.vlan.map { String($0) } ?? ""
            }
            .task {
                while !Task.isCancelled {
                    await model.loadCounters(port)
                    await pause(3)
                }
            }
        }
    }

    private var statusSection: some View {
        Section("Status") {
            ValueRow(label: "Admin", value: d.adminText, symbol: "power",
                     valueColor: d.admin == 1 ? .green : .secondary)
            ValueRow(label: "Link", value: d.linkText, symbol: "cable.connector",
                     valueColor: d.linkText == "UP" ? .green : (d.linkText == "DOWN" ? .red : .secondary))
            ValueRow(label: "Speed", value: d.speedText.isEmpty ? "–" : d.speedText, symbol: "speedometer")
            ValueRow(label: "PoE", value: d.poeText(port: port, poePorts: model.poePorts), symbol: "bolt")
            ValueRow(label: "VLAN (PVID)", value: d.vlan.map { String($0) } ?? "–", symbol: "square.stack.3d.up")
            ValueRow(label: "Beschreibung", value: d.desc.isEmpty ? "–" : d.desc, symbol: "text.alignleft")
            ValueRow(label: "IP-Adresse", value: d.ip.isEmpty ? "–" : d.ip, symbol: "number")
            if !d.mac.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Label("MAC-Adressen", systemImage: "barcode")
                    Text(d.mac.replacingOccurrences(of: ", ", with: "\n"))
                        .font(.footnote.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
        }
    }

    private var countersSection: some View {
        Section {
            if let c = model.counters[port] {
                if !c.name.isEmpty || !c.descr.isEmpty {
                    ValueRow(label: "Interface", value: c.name.isEmpty ? c.descr : c.name)
                }
                if let hs = c.highSpeed, d.oper == 1 {
                    ValueRow(label: "Geschwindigkeit", value: "\(hs) Mbit/s")
                }
                ValueRow(label: "Empfangen", value: bytes(c.inOctets))
                ValueRow(label: "Gesendet", value: bytes(c.outOctets))
                ValueRow(label: "Rate ein / aus",
                         value: "\(c.inRate.map { SwitchCatalog.rateText($0) } ?? "…") / \(c.outRate.map { SwitchCatalog.rateText($0) } ?? "…")")
                ValueRow(label: "Fehler ein / aus", value: "\(num(c.inErrors)) / \(num(c.outErrors))",
                         valueColor: ((c.inErrors ?? 0) + (c.outErrors ?? 0)) > 0 ? .orange : .secondary)
                ValueRow(label: "Verworfen ein / aus", value: "\(num(c.inDiscards)) / \(num(c.outDiscards))")
                if isPoE, let pd = c.poeDetect {
                    ValueRow(label: "PoE-Erkennung", value: SwitchCatalog.poeDetectText(pd))
                }
            } else if let e = model.counterError {
                Text(e).font(.footnote).foregroundStyle(.red)
            } else {
                HStack {
                    ProgressView()
                    Text("Zähler werden gelesen …").foregroundStyle(.secondary)
                }
            }
        } header: {
            Text("Verkehr")
        } footer: {
            Text("Wird alle 3 Sekunden aktualisiert.")
        }
    }

    private var managementSection: some View {
        Section {
            Toggle(isOn: Binding(get: { d.admin == 1 }, set: { v in askAdmin(v) })) {
                Label("Port aktiv", systemImage: "power")
            }
            .disabled(!mgmt || model.busy)
            if isPoE {
                Toggle(isOn: Binding(get: { d.poe == 1 }, set: { v in askPoE(v) })) {
                    Label("PoE", systemImage: "bolt.fill")
                }
                .tint(.yellow)
                .disabled(!mgmt || model.busy)
            }
            HStack {
                TextField("Beschreibung", text: $aliasText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Setzen") { askAlias() }
                    .buttonStyle(.borderless)
                    .disabled(!mgmt || model.busy)
            }
            HStack {
                TextField("VLAN-ID (PVID)", text: $pvidText)
                    .keyboardType(.numberPad)
                Button("Setzen") { askPVID() }
                    .buttonStyle(.borderless)
                    .disabled(!mgmt || model.busy)
            }
            if let e = inputError {
                Text(e).font(.footnote).foregroundStyle(.red)
            }
        } header: {
            Text("Verwaltung")
        } footer: {
            if mgmt {
                Text("Jede Änderung wird per SNMP SET (Write Community) gesendet und vorher bestätigt.")
            } else {
                Text("Schreibzugriff ist aus. In den Einstellungen \"Management (SNMP SET)\" einschalten.")
            }
        }
    }

    private func bytes(_ v: UInt64?) -> String {
        guard let v = v else { return "–" }
        return ByteCountFormatter.string(fromByteCount: Int64(truncatingIfNeeded: v), countStyle: .binary)
    }

    private func num(_ v: UInt64?) -> String {
        guard let v = v else { return "–" }
        return String(v)
    }

    // ---- Bestaetigungen ----
    private func ask(_ w: SwitchPendingWrite) {
        inputError = nil
        pending = w
        showConfirm = true
    }

    private func askAdmin(_ up: Bool) {
        let m = model
        let p = port
        ask(SwitchPendingWrite(
            title: up ? "Port \(p) aktivieren?" : "Port \(p) deaktivieren?",
            message: up ? "Setzt ifAdminStatus auf UP." :
                "Setzt ifAdminStatus auf DOWN. Angeschlossene Geräte verlieren die Verbindung. "
                + "Ist es der Weg zu diesem iPhone, ist der Switch danach nicht mehr erreichbar.",
            confirm: up ? "Aktivieren" : "Deaktivieren",
            run: { m.setAdmin(p, up: up) }))
    }

    private func askPoE(_ on: Bool) {
        let m = model
        let p = port
        ask(SwitchPendingWrite(
            title: on ? "PoE an Port \(p) einschalten?" : "PoE an Port \(p) ausschalten?",
            message: on ? "Der Port liefert danach wieder Strom." :
                "Per PoE versorgte Geräte (Kamera, Access Point, Telefon …) an diesem Port gehen aus.",
            confirm: on ? "Einschalten" : "Ausschalten",
            run: { m.setPoE(p, on: on) }))
    }

    private func askAlias() {
        let m = model
        let p = port
        let t = aliasText.trimmed
        if t.utf8.count > 64 {
            inputError = "Beschreibung max. 64 Zeichen."
            return
        }
        ask(SwitchPendingWrite(
            title: "Beschreibung von Port \(p) setzen?",
            message: t.isEmpty ? "Die Beschreibung wird gelöscht." : "Neue Beschreibung: \"\(t)\"",
            confirm: "Setzen",
            run: { m.setAlias(p, text: t) }))
    }

    private func askPVID() {
        let m = model
        let p = port
        guard let vid = Int(pvidText.trimmed), vid >= 1, vid <= 4094 else {
            inputError = "VLAN-ID 1..4094 eingeben."
            return
        }
        ask(SwitchPendingWrite(
            title: "Port \(p) auf VLAN \(vid) (PVID) setzen?",
            message: "Achtung: Der Port muss im Ziel-VLAN als Member (untagged) angelegt sein, sonst lehnt der Switch ab.",
            confirm: "Setzen",
            run: { m.setPVID(p, vlan: vid) }))
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
@MainActor
struct SwitchSettingsView: View {
    @ObservedObject var model: SwitchModel
    @State private var s: SwitchSettings

    init(model: SwitchModel) {
        _model = ObservedObject(wrappedValue: model)
        _s = State(initialValue: model.settings)
    }

    private var catalog: (ports: Int, poe: Int) { SwitchCatalog.lookup(s.model) }

    var body: some View {
        SettingsSheet(title: "Switch", onSave: {
            model.settings = s
            model.saveSettings()
        }) {
            Section {
                FieldRow(label: "IP-Adresse", text: $s.ip, placeholder: "192.168.1.254", keyboard: .numbersAndPunctuation)
                FieldRow(label: "SNMP Community", text: $s.community, placeholder: "public")
                FieldRow(label: "Poll-Intervall (s)", text: intBinding($s.pollInterval), placeholder: "30",
                         keyboard: .numberPad)
            } header: {
                Text("Verbindung (SNMP v2c, UDP 161)")
            } footer: {
                Text("Poll-Intervall 0 = nur manuell aktualisieren.")
            }
            Section {
                Picker("Modell", selection: $s.model) {
                    ForEach(SwitchCatalog.names, id: \.self) { n in
                        Text(n).tag(n)
                    }
                }
                .pickerStyle(.navigationLink)
                if catalog.ports > 0 {
                    ValueRow(label: "Ports", value: "\(catalog.ports)")
                    ValueRow(label: "PoE-Ports", value: "\(catalog.poe)")
                } else {
                    FieldRow(label: "Port Count", text: intBinding($s.portCount), placeholder: "28", keyboard: .numberPad)
                    FieldRow(label: "PoE Ports", text: intBinding($s.poePorts), placeholder: "24", keyboard: .numberPad)
                }
            } header: {
                Text("Modell")
            }
            Section {
                Toggle("Management (SNMP SET)", isOn: $s.management)
                if s.management {
                    FieldRow(label: "Write Community", text: $s.writeCommunity, placeholder: "private", secure: true)
                }
            } header: {
                Text("Verwaltung")
            } footer: {
                Text("Erlaubt Port an/aus, PoE an/aus, Beschreibung und VLAN (PVID). Jede Änderung wird vorher bestätigt.")
            }
        }
    }
}
