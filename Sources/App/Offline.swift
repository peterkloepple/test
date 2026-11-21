// ===========================================================================
//  Offline.swift - PA Schematic iOS - letzter Stand der Planung zum Ansehen ohne PC
//  Autor: T. Pfeiffer
//
//  Vom PC kommen: die Seite selbst, eine Datei mit allen Daten (offline.js) und
//  die Bilder (Plan, Racks, Geraetebilder). Alles liegt in einem Ordner der App.
// ===========================================================================
import Foundation

enum OfflineError: LocalizedError {
    case bad(String)

    var errorDescription: String? {
        switch self {
        case .bad(let t): return t
        }
    }
}

enum Offline {
    static var root: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
    }
    static var dir: URL { root.appendingPathComponent("offline", isDirectory: true) }
    static var index: URL { dir.appendingPathComponent("index.html") }

    static var available: Bool {
        FileManager.default.fileExists(atPath: index.path)
    }

    static func date() -> Date? {
        let a = try? FileManager.default.attributesOfItem(atPath: index.path)
        return a?[.modificationDate] as? Date
    }

    static func dateText(_ d: Date?) -> String {
        guard let d = d else { return "-" }
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "dd.MM.yyyy HH:mm"
        return f.string(from: d)
    }

    private static func get(_ base: String, _ path: String, _ key: String) async throws -> Data {
        guard let u = URL(string: base + path) else { throw OfflineError.bad("Adresse ungültig") }
        var req = URLRequest(url: u, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        req.setValue(key, forHTTPHeaderField: "X-Key")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw OfflineError.bad("Der PC hat \(path) nicht geliefert")
        }
        return data
    }

    /// Holt den Stand vom PC und legt ihn ab. Liefert die Zahl der Dateien.
    static func sync(base: String, key: String) async throws -> Int {
        let fm = FileManager.default
        let page = try await get(base, "/", key)
        guard var html = String(data: page, encoding: .utf8), html.contains("<!--PA_OFFLINE-->") else {
            throw OfflineError.bad("Das Programm am PC ist zu alt für die Ansicht ohne PC")
        }
        html = html.replacingOccurrences(of: "<!--PA_OFFLINE-->", with: "<script src=\"offline.js\"></script>")
        let raw = try await get(base, "/api/bundle", key)
        guard let obj = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
              let js = obj["js"] as? String, let imgs = obj["img"] as? [String: String] else {
            throw OfflineError.bad("Die Daten vom PC sind nicht lesbar")
        }
        let tmp = root.appendingPathComponent("offline_neu", isDirectory: true)
        try? fm.removeItem(at: tmp)
        try fm.createDirectory(at: tmp, withIntermediateDirectories: true)
        var n = 2
        for (name, path) in imgs {
            let safe = name.replacingOccurrences(of: "/", with: "_")
            if let d = try? await get(base, path, key) {
                try d.write(to: tmp.appendingPathComponent(safe))
                n += 1
            }
        }
        try Data(js.utf8).write(to: tmp.appendingPathComponent("offline.js"))
        try Data(html.utf8).write(to: tmp.appendingPathComponent("index.html"))
        try? fm.removeItem(at: dir)
        try fm.moveItem(at: tmp, to: dir)
        return n
    }
}
