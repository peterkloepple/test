// ===========================================================================
//  StudioApp.swift - Studio Control iOS - Einstieg, Startseite, Szenen
//  Autor: T. Pfeiffer
// ===========================================================================
import SwiftUI

let APP_VERSION = "1.0.0"

@main
struct StudioControlApp: App {
    @StateObject private var hub = DeviceHub()
    @Environment(\.scenePhase) private var phase

    init() {
        print("INIT Studio Control iOS v\(APP_VERSION)")
    }

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(hub)
                .preferredColorScheme(.dark)
                .tint(Color(hex: 0x0A84FF))
        }
        .onChange(of: phase) { p in
            if p == .background { hub.disconnectAll() }
        }
    }
}

// ---------------------------------------------------------------------------
// Alle Geraete
// ---------------------------------------------------------------------------
@MainActor
final class DeviceHub: ObservableObject {
    let beamer = BeamerModel()
    let tapo = TapoModel()
    let stegos = StegosModel()
    let clickshare = ClickShareModel()
    let switchDev = SwitchModel()
    let fritz = FritzModel()
    let speedport = SpeedportModel()
    let printer = PrinterModel()
    let touchpanel = TouchpanelModel()
    let speedtest = SpeedtestModel()

    @Published var sceneBusy = false
    @Published var sceneMessage: String?

    var all: [DeviceModel] {
        [beamer, tapo, stegos, clickshare, touchpanel, printer, switchDev, fritz, speedport, speedtest]
    }

    init() {
        for d in all { d.loadSettings() }
    }

    func refreshAll() async {
        await withTaskGroup(of: Void.self) { g in
            for d in all where d.isConfigured {
                g.addTask { await d.refresh() }
            }
        }
    }

    func disconnectAll() {
        for d in all { d.disconnect() }
    }

    func runScene(_ on: Bool) async {
        sceneBusy = true
        defer { sceneBusy = false }
        var ok: [String] = []
        var bad: [String] = []
        for d in all where d.supportsScene && d.isConfigured {
            do {
                try await d.scene(on)
                ok.append(d.title)
                d.addLog(on ? "Szene Studio an" : "Szene Studio aus")
            } catch {
                bad.append("\(d.title): \(DeviceModel.describe(error))")
            }
        }
        if bad.isEmpty {
            sceneMessage = ok.isEmpty ? "Kein Geraet fuer Szenen eingerichtet (je Geraet in den Einstellungen)." :
                "\(on ? "Studio an" : "Studio aus"): \(ok.joined(separator: ", "))"
            Haptics.success()
        } else {
            sceneMessage = "Teilweise fehlgeschlagen:\n" + bad.joined(separator: "\n")
            Haptics.error()
        }
        await refreshAll()
    }

    @ViewBuilder
    func detail(for d: DeviceModel) -> some View {
        if let m = d as? BeamerModel { BeamerView(model: m) }
        else if let m = d as? TapoModel { TapoView(model: m) }
        else if let m = d as? StegosModel { StegosView(model: m) }
        else if let m = d as? ClickShareModel { ClickShareView(model: m) }
        else if let m = d as? SwitchModel { SwitchView(model: m) }
        else if let m = d as? FritzModel { FritzView(model: m) }
        else if let m = d as? SpeedportModel { SpeedportView(model: m) }
        else if let m = d as? PrinterModel { PrinterView(model: m) }
        else if let m = d as? TouchpanelModel { TouchpanelView(model: m) }
        else if let m = d as? SpeedtestModel { SpeedtestView(model: m) }
        else { Text(d.title) }
    }
}

// ---------------------------------------------------------------------------
// Startseite
// ---------------------------------------------------------------------------
struct HomeView: View {
    @EnvironmentObject var hub: DeviceHub
    @State private var showAbout = false

    private let cols = [GridItem(.adaptive(minimum: 158), spacing: 12)]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    sceneBar
                    Text("Geraete").font(.title3.bold()).padding(.horizontal, 4)
                    LazyVGrid(columns: cols, spacing: 12) {
                        ForEach(hub.all, id: \.id) { d in
                            NavigationLink(value: d.id) {
                                DeviceTile(model: d)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 30)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Studio")
            .navigationDestination(for: String.self) { id in
                if let d = hub.all.first(where: { $0.id == id }) {
                    hub.detail(for: d)
                }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showAbout = true
                    } label: {
                        Image(systemName: "info.circle")
                    }
                }
            }
            .refreshable { await hub.refreshAll() }
            .task { await hub.refreshAll() }
            .sheet(isPresented: $showAbout) { AboutView() }
            .alert("Szene", isPresented: Binding(get: { hub.sceneMessage != nil }, set: { if !$0 { hub.sceneMessage = nil } })) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(hub.sceneMessage ?? "")
            }
        }
    }

    private var sceneBar: some View {
        HStack(spacing: 12) {
            SceneButton(title: "Studio an", symbol: "sun.max.fill", tint: .orange, busy: hub.sceneBusy) {
                Task { await hub.runScene(true) }
            }
            SceneButton(title: "Studio aus", symbol: "moon.fill", tint: .indigo, busy: hub.sceneBusy) {
                Task { await hub.runScene(false) }
            }
        }
        .padding(.top, 6)
    }
}

struct SceneButton: View {
    let title: String
    let symbol: String
    let tint: Color
    let busy: Bool
    let action: () -> Void

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            HStack(spacing: 10) {
                Image(systemName: symbol).font(.title3.weight(.semibold))
                Text(title).font(.headline)
                Spacer(minLength: 0)
                if busy { ProgressView().tint(.white) }
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: 56)
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(tint.gradient))
        }
        .buttonStyle(.plain)
        .disabled(busy)
    }
}

struct DeviceTile: View {
    @ObservedObject var model: DeviceModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                DeviceIcon(symbol: model.symbol, tint: model.tint, size: 40)
                Spacer()
                if model.busy {
                    ProgressView().scaleEffect(0.8)
                } else {
                    StateDot(state: model.state)
                }
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(model.title).font(.headline).foregroundStyle(.primary).lineLimit(1)
                Text(tileText).font(.footnote).foregroundStyle(.secondary).lineLimit(2)
                    .frame(maxWidth: .infinity, minHeight: 34, alignment: .topLeading)
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(Color(.secondarySystemGroupedBackground)))
        .contentShape(Rectangle())
    }

    var tileText: String {
        switch model.state {
        case .notConfigured: return "Tippen zum Einrichten"
        case .unknown where model.summary.isEmpty: return model.subtitle
        default: return model.summary.isEmpty ? model.subtitle : model.summary
        }
    }
}

struct AboutView: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 14) {
                        DeviceIcon(symbol: "slider.horizontal.3", tint: Color(hex: 0x0A84FF), size: 60)
                        VStack(alignment: .leading) {
                            Text("Studio Control").font(.title2.bold())
                            Text("Version \(APP_VERSION)").foregroundStyle(.secondary)
                            Text("T. Pfeiffer").foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 6)
                }
                Section("Hinweise") {
                    Text("Das iPhone muss im selben Netzwerk (WLAN) wie die Geraete sein. Beim ersten Start fragt iOS nach dem Zugriff auf das lokale Netzwerk - bitte erlauben (sonst: Einstellungen > Datenschutz > Lokales Netzwerk > Studio Control).")
                    Text("Einstellungen (IP-Adressen, Kennwoerter) liegen verschluesselt im iOS-Schluesselbund und bleiben bei Updates erhalten.")
                    Text("Szenen: In den Einstellungen von Beamer, Steckdosen und ClickShare festlegen, was 'Studio an' und 'Studio aus' schalten.")
                }
            }
            .navigationTitle("Info")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } }
            }
        }
    }
}
