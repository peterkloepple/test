import SwiftUI
struct SpeedtestSettings: Codable { var ip: String = "" }
@MainActor final class SpeedtestModel: DeviceModel {
    @Published var settings = SpeedtestSettings()
    init() { super.init(id: "speedtest", title: "Speedtest", subtitle: "Test", symbol: "speedometer", tint: Color(hex: 0x32ADE6)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(SpeedtestSettings.self, "speedtest") ?? SpeedtestSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "speedtest") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct SpeedtestView: View {
    @ObservedObject var model: SpeedtestModel
    var body: some View {
        DevicePage(model: model, settings: { SpeedtestSettingsView(model: model) }) {
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
struct SpeedtestSettingsView: View {
    @ObservedObject var model: SpeedtestModel
    @State private var s: SpeedtestSettings
    @State private var port = 23
    init(model: SpeedtestModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Speedtest", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
