// ===========================================================================
//  Crypto.swift - Studio Control iOS - Hash/AES/Zufall
//  Autor: T. Pfeiffer
// ===========================================================================
import Foundation
import CryptoKit
import CommonCrypto

enum Crypto {
    static func sha256(_ d: Data) -> Data { Data(SHA256.hash(data: d)) }
    static func sha1(_ d: Data) -> Data { Data(Insecure.SHA1.hash(data: d)) }
    static func md5(_ d: Data) -> Data { Data(Insecure.MD5.hash(data: d)) }
    static func md5Hex(_ s: String) -> String { md5(Data(s.utf8)).hex }

    static func random(_ n: Int) -> Data {
        var d = Data(count: n)
        let rc = d.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, n, $0.baseAddress!) }
        if rc != errSecSuccess {
            for i in 0..<n { d[i] = UInt8.random(in: 0...255) }
        }
        return d
    }

    /// AES-CBC mit PKCS7-Padding (128/192/256 Bit Schluessel).
    static func aesCBC(encrypt: Bool, key: Data, iv: Data, data: Data) throws -> Data {
        try cc(op: encrypt ? CCOperation(kCCEncrypt) : CCOperation(kCCDecrypt),
               options: CCOptions(kCCOptionPKCS7Padding), key: key, iv: iv, data: data)
    }

    /// AES-CBC ohne Padding (Laenge muss Vielfaches von 16 sein).
    static func aesCBCNoPad(encrypt: Bool, key: Data, iv: Data, data: Data) throws -> Data {
        try cc(op: encrypt ? CCOperation(kCCEncrypt) : CCOperation(kCCDecrypt),
               options: 0, key: key, iv: iv, data: data)
    }

    /// Einzelner AES-Block (ECB) - Baustein fuer CTR/CCM.
    static func aesECB(key: Data, block: Data) throws -> Data {
        try cc(op: CCOperation(kCCEncrypt), options: CCOptions(kCCOptionECBMode), key: key, iv: nil, data: block)
    }

    /// AES-CTR (Zaehler = 16 Byte Startblock, Big-Endian hochgezaehlt).
    static func aesCTR(key: Data, counter: Data, data: Data) throws -> Data {
        var ctr = [UInt8](counter)
        var out = Data(capacity: data.count)
        var i = 0
        let bytes = [UInt8](data)
        while i < bytes.count {
            let ks = [UInt8](try aesECB(key: key, block: Data(ctr)))
            let n = min(16, bytes.count - i)
            for k in 0..<n { out.append(bytes[i + k] ^ ks[k]) }
            i += n
            var j = 15
            while j >= 0 {
                ctr[j] = ctr[j] &+ 1
                if ctr[j] != 0 { break }
                j -= 1
            }
        }
        return out
    }

    /// AES-CCM entschluesseln (RFC 3610), Tag-Laenge `tagLen`, Nonce 7..13 Byte.
    /// Liefert Klartext; wirft bei falschem Tag.
    static func aesCCMDecrypt(key: Data, nonce: Data, ciphertextAndTag: Data, aad: Data = Data(), tagLen: Int = 16) throws -> Data {
        guard ciphertextAndTag.count >= tagLen else { throw NetError.protocolError("CCM: zu kurz") }
        let ct = ciphertextAndTag.prefix(ciphertextAndTag.count - tagLen)
        let tag = ciphertextAndTag.suffix(tagLen)
        let L = 15 - nonce.count
        // A0 / Ai
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
        let s0 = try aesECB(key: key, block: ctrBlock(0))
        let plain = try aesCTR(key: key, counter: ctrBlock(1), data: Data(ct))
        // CBC-MAC
        var flags: UInt8 = UInt8(((tagLen - 2) / 2) << 3) | UInt8(L - 1)
        if !aad.isEmpty { flags |= 0x40 }
        var b0 = Data([flags])
        b0.append(nonce)
        var ln = [UInt8](repeating: 0, count: L)
        var v = plain.count
        var k = L - 1
        while k >= 0 { ln[k] = UInt8(v & 0xff); v >>= 8; k -= 1 }
        b0.append(contentsOf: ln)
        var macInput = b0
        if !aad.isEmpty {
            var a = Data()
            if aad.count < 0xFF00 {
                a.append(UInt8((aad.count >> 8) & 0xff)); a.append(UInt8(aad.count & 0xff))
            } else {
                a.append(contentsOf: [0xff, 0xfe])
                let c = UInt32(aad.count)
                a.append(contentsOf: [UInt8(c >> 24), UInt8((c >> 16) & 0xff), UInt8((c >> 8) & 0xff), UInt8(c & 0xff)])
            }
            a.append(aad)
            while a.count % 16 != 0 { a.append(0) }
            macInput.append(a)
        }
        var p = plain
        while p.count % 16 != 0 { p.append(0) }
        macInput.append(p)
        let mac = try aesCBCNoPad(encrypt: true, key: key, iv: Data(count: 16), data: macInput).suffix(16)
        var t = Data()
        let s0b = [UInt8](s0)
        let macb = [UInt8](mac)
        for i in 0..<tagLen { t.append(macb[i] ^ s0b[i]) }
        guard t == Data(tag) else { throw NetError.protocolError("CCM: Pruefsumme falsch (Schluessel?)") }
        return plain
    }

    private static func cc(op: CCOperation, options: CCOptions, key: Data, iv: Data?, data: Data) throws -> Data {
        var out = Data(count: data.count + kCCBlockSizeAES128)
        var moved = 0
        let outCap = out.count
        let status: CCCryptorStatus = out.withUnsafeMutableBytes { outPtr in
            data.withUnsafeBytes { inPtr in
                key.withUnsafeBytes { keyPtr in
                    if let iv = iv {
                        return iv.withUnsafeBytes { ivPtr in
                            CCCrypt(op, CCAlgorithm(kCCAlgorithmAES), options,
                                    keyPtr.baseAddress, key.count, ivPtr.baseAddress,
                                    inPtr.baseAddress, data.count, outPtr.baseAddress, outCap, &moved)
                        }
                    } else {
                        return CCCrypt(op, CCAlgorithm(kCCAlgorithmAES), options,
                                       keyPtr.baseAddress, key.count, nil,
                                       inPtr.baseAddress, data.count, outPtr.baseAddress, outCap, &moved)
                    }
                }
            }
        }
        guard status == kCCSuccess else { throw NetError.protocolError("AES-Fehler \(status)") }
        out.count = moved
        return out
    }
}
