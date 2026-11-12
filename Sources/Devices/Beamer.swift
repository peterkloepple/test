import SwiftUI
struct BeamerSettings: Codable { var ip: String = "" }
@MainActor final class BeamerModel: DeviceModel {
    @Published var settings = BeamerSettings()
    init() { super.init(id: "beamer", title: "Beamer", subtitle: "Test", symbol: "videoprojector", tint: Color(hex: 0xFF9F0A)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(BeamerSettings.self, "beamer") ?? BeamerSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "beamer") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct BeamerView: View {
    @ObservedObject var model: BeamerModel
    var body: some View {
        DevicePage(model: model, settings: { BeamerSettingsView(model: model) }) {
            Section("Test") {
                TileGrid {
                    ActionTile(title: "An", symbol: "power", tint: .green, active: true) { model.perform("an") { } }
                    ActionTile(title: "Aus", symbol: "power", tint: .red) { }
                }
                ValueRow(label: "IP", value: model.settings.ip)
                LevelBar(value: 0.5)
                PowerToggleRow(title: "Power", isOn: true) { _ in }
            }
        }
    }
}
struct BeamerSettingsView: View {
    @ObservedObject var model: BeamerModel
    @State private var s: BeamerSettings
    @State private var port = 23
    init(model: BeamerModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Beamer", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
