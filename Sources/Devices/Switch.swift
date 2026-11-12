import SwiftUI
struct SwitchSettings: Codable { var ip: String = "" }
@MainActor final class SwitchModel: DeviceModel {
    @Published var settings = SwitchSettings()
    init() { super.init(id: "switch", title: "Switch", subtitle: "Test", symbol: "network", tint: Color(hex: 0x64D2FF)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(SwitchSettings.self, "switch") ?? SwitchSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "switch") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct SwitchView: View {
    @ObservedObject var model: SwitchModel
    var body: some View {
        DevicePage(model: model, settings: { SwitchSettingsView(model: model) }) {
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
struct SwitchSettingsView: View {
    @ObservedObject var model: SwitchModel
    @State private var s: SwitchSettings
    @State private var port = 23
    init(model: SwitchModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Switch", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
