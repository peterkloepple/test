import SwiftUI
struct FritzSettings: Codable { var ip: String = "" }
@MainActor final class FritzModel: DeviceModel {
    @Published var settings = FritzSettings()
    init() { super.init(id: "fritz", title: "Fritz", subtitle: "Test", symbol: "wifi.router", tint: Color(hex: 0xFF453A)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(FritzSettings.self, "fritz") ?? FritzSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "fritz") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct FritzView: View {
    @ObservedObject var model: FritzModel
    var body: some View {
        DevicePage(model: model, settings: { FritzSettingsView(model: model) }) {
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
struct FritzSettingsView: View {
    @ObservedObject var model: FritzModel
    @State private var s: FritzSettings
    @State private var port = 23
    init(model: FritzModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Fritz", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
