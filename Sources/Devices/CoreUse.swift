import Foundation
// Nur fuer den Kern-Test: alle Kern-APIs einmal benutzen
func coreSmoke() async throws {
    let c = try TCPConnection(host: "127.0.0.1", port: 23)
    try await c.connect(timeout: 1)
    try await c.send("PING\r")
    _ = try await c.readLine(timeout: 1)
    _ = try await c.read(count: 4)
    _ = await c.readAvailable()
    _ = try await UDPExchange.request(host: "127.0.0.1", port: 161, payload: Data([1]))
    let h = HTTPClient(user: "a", password: "b")
    _ = try await h.getJSON(URL(string: "http://127.0.0.1")!)
    _ = try Crypto.aesCBC(encrypt: true, key: Data(count: 16), iv: Data(count: 16), data: Data([1, 2]))
    _ = try Crypto.aesCCMDecrypt(key: Data(count: 16), nonce: Data(count: 12), ciphertextAndTag: Data(count: 20))
    let s = SNMPClient(host: "127.0.0.1")
    _ = try await s.walk("1.3.6.1.2.1.2.2.1.2")
    _ = try await s.set("1.3.6.1.2.1.2.2.1.7.1", .integer(1))
    _ = makeURL("x", port: 80, path: "/a")
    _ = Data(hex: "00ff")?.hex
}
