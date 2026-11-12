import SwiftUI
struct PrinterSettings: Codable { var ip: String = "" }
@MainActor final class PrinterModel: DeviceModel {
    @Published var settings = PrinterSettings()
    init() { super.init(id: "printer", title: "Printer", subtitle: "Test", symbol: "printer.fill", tint: Color(hex: 0x8E8E93)) }
    override var isConfigured: Bool { !settings.ip.trimmed.isEmpty }
    override func loadSettings() { settings = SecureStore.loadCodable(PrinterSettings.self, "printer") ?? PrinterSettings() }
    override func saveSettings() { SecureStore.saveCodable(settings, "printer") }
    override func refresh() async {
        await refreshSafely {
            let up = await TCPConnection.probe(host: settings.ip, port: 80)
            if !up { throw NetError.closed }
            summary = "ok"
        }
    }
}
struct PrinterView: View {
    @ObservedObject var model: PrinterModel
    var body: some View {
        DevicePage(model: model, settings: { PrinterSettingsView(model: model) }) {
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
struct PrinterSettingsView: View {
    @ObservedObject var model: PrinterModel
    @State private var s: PrinterSettings
    @State private var port = 23
    init(model: PrinterModel) { self.model = model; _s = State(initialValue: model.settings) }
    var body: some View {
        SettingsSheet(title: "Printer", onSave: { model.settings = s; model.saveSettings() }) {
            Section("Verbindung") {
                FieldRow(label: "IP", text: $s.ip, placeholder: "192.168.0.10", keyboard: .numbersAndPunctuation)
                FieldRow(label: "Port", text: intBinding($port))
            }
        }
    }
}
