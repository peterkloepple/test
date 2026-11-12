// ===========================================================================
//  Store.swift - Studio Control iOS - Einstellungen sicher speichern (Schluesselbund)
//  Autor: T. Pfeiffer
//  Jedes Geraet speichert seine Einstellungen (IP, Port, Kennwort ...) als JSON
//  im iOS-Schluesselbund - bleibt bei App-Updates erhalten, Kennwoerter verschluesselt.
// ===========================================================================
import Foundation
import Security

enum SecureStore {
    private static let service = "de.tpfeiffer.studiocontrol"

    static func save(_ key: String, _ data: Data) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service,
                                kSecAttrAccount as String: key]
        SecItemDelete(q as CFDictionary)
        var add = q
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        let st = SecItemAdd(add as CFDictionary, nil)
        if st != errSecSuccess {
            // Ersatz: UserDefaults (z.B. wenn der Schluesselbund bei unsignierten Testbuilds fehlt)
            UserDefaults.standard.set(data, forKey: "store." + key)
        } else {
            UserDefaults.standard.removeObject(forKey: "store." + key)
        }
    }

    static func load(_ key: String) -> Data? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrService as String: service,
                                kSecAttrAccount as String: key,
                                kSecReturnData as String: true,
                                kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        if SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data {
            return d
        }
        return UserDefaults.standard.data(forKey: "store." + key)
    }

    static func loadCodable<T: Codable>(_ type: T.Type, _ key: String) -> T? {
        guard let d = load(key) else { return nil }
        return try? JSONDecoder().decode(T.self, from: d)
    }

    static func saveCodable<T: Codable>(_ value: T, _ key: String) {
        if let d = try? JSONEncoder().encode(value) { save(key, d) }
    }
}

/// Kleine Protokollzeile fuer die Geraete-Seiten.
struct LogLine: Identifiable, Hashable {
    let id = UUID()
    let time: Date
    let text: String
    let isError: Bool
}
