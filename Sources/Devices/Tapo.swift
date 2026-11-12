import SwiftUI
struct TapoSettings: Codable { var ip: String = "" }
@MainActor final class TapoModel: DeviceModel {
    @Published var settings = TapoSettings()
    init() { super.init(id: "tapo", title: "Tapo", subtitle: "Test", symbol: "powerplug", tint: Color(hex: 0x30D158)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(TapoSettings.self, "tapo") ?? TapoSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "tapo") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct TapoView: View {
    @ObservedObject var model: TapoModel
    var body: some View {
        DevicePage(model: model, settings: { TapoSettingsView(model: model) }) {
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
struct TapoSettingsView: View {
    @ObservedObject var model: TapoModel
    @State private var s: TapoSettings
    @State private var port = 23
    init(model: TapoModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Tapo", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
