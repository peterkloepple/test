import SwiftUI
struct SpeedportSettings: Codable { var ip: String = "" }
@MainActor final class SpeedportModel: DeviceModel {
    @Published var settings = SpeedportSettings()
    init() { super.init(id: "speedport", title: "Speedport", subtitle: "Test", symbol: "server.rack", tint: Color(hex: 0xE20074)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(SpeedportSettings.self, "speedport") ?? SpeedportSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "speedport") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct SpeedportView: View {
    @ObservedObject var model: SpeedportModel
    var body: some View {
        DevicePage(model: model, settings: { SpeedportSettingsView(model: model) }) {
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
struct SpeedportSettingsView: View {
    @ObservedObject var model: SpeedportModel
    @State private var s: SpeedportSettings
    @State private var port = 23
    init(model: SpeedportModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Speedport", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
