import SwiftUI
struct StegosSettings: Codable { var ip: String = "" }
@MainActor final class StegosModel: DeviceModel {
    @Published var settings = StegosSettings()
    init() { super.init(id: "stegos", title: "Stegos", subtitle: "Test", symbol: "mic.fill", tint: Color(hex: 0xFF375F)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(StegosSettings.self, "stegos") ?? StegosSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "stegos") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct StegosView: View {
    @ObservedObject var model: StegosModel
    var body: some View {
        DevicePage(model: model, settings: { StegosSettingsView(model: model) }) {
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
struct StegosSettingsView: View {
    @ObservedObject var model: StegosModel
    @State private var s: StegosSettings
    @State private var port = 23
    init(model: StegosModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Stegos", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
