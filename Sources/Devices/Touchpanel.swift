import SwiftUI
struct TouchpanelSettings: Codable { var ip: String = "" }
@MainActor final class TouchpanelModel: DeviceModel {
    @Published var settings = TouchpanelSettings()
    init() { super.init(id: "touchpanel", title: "Touchpanel", subtitle: "Test", symbol: "rectangle.grid.2x2.fill", tint: Color(hex: 0x5E5CE6)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(TouchpanelSettings.self, "touchpanel") ?? TouchpanelSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "touchpanel") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct TouchpanelView: View {
    @ObservedObject var model: TouchpanelModel
    var body: some View {
        DevicePage(model: model, settings: { TouchpanelSettingsView(model: model) }) {
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
struct TouchpanelSettingsView: View {
    @ObservedObject var model: TouchpanelModel
    @State private var s: TouchpanelSettings
    @State private var port = 23
    init(model: TouchpanelModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Touchpanel", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
