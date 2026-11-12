import SwiftUI
struct ClickShareSettings: Codable { var ip: String = "" }
@MainActor final class ClickShareModel: DeviceModel {
    @Published var settings = ClickShareSettings()
    init() { super.init(id: "clickshare", title: "ClickShare", subtitle: "Test", symbol: "rectangle.on.rectangle", tint: Color(hex: 0x30B0C7)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(ClickShareSettings.self, "clickshare") ?? ClickShareSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "clickshare") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct ClickShareView: View {
    @ObservedObject var model: ClickShareModel
    var body: some View {
        DevicePage(model: model, settings: { ClickShareSettingsView(model: model) }) {
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
struct ClickShareSettingsView: View {
    @ObservedObject var model: ClickShareModel
    @State private var s: ClickShareSettings
    @State private var port = 23
    init(model: ClickShareModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "ClickShare", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
