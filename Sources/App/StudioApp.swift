// ===========================================================================
//  StudioApp.swift - Studio Control iOS - Einstieg, Startseite, Szenen
//  Autor: T. Pfeiffer
// ===========================================================================
import SwiftUI
import UniformTypeIdentifiers

@main
struct StudioControlApp: App {
    @StateObject private var hub = DeviceHub()
    @StateObject private var updates = UpdateCenter()
    @Environment(\.scenePhase) private var phase

    init() {
        print("INIT Studio Control iOS v\(APP_VERSION) (Build \(APP_BUILD))")
    }

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(hub)
                .environmentObject(updates)
                .preferredColorScheme(.dark)
                .tint(Color(hex: 0x0A84FF))
        }
        .onChange(of: phase) { p in
            if p == .background { hub.disconnectAll() }
            if p == .active {
                updates.expiry = DeviceModel.demoMode ? updates.expiry : UpdateCenter.readExpiry()
                updates.scheduleReminder()
                Task { await updates.check() }
            }
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
    /// Reihenfolge und ausgeblendete Kacheln der Startseite
    @Published var order: [String] {
        didSet { UserDefaults.standard.set(order, forKey: "home.order") }
    }
    @Published var hidden: [String] {
        didSet { UserDefaults.standard.set(hidden, forKey: "home.hidden") }
    }

    var all: [DeviceModel] {
        [beamer, tapo, stegos, clickshare, touchpanel, printer, switchDev, fritz, speedport, speedtest]
    }

    /// Alle Geraete in der vom Nutzer gewaehlten Reihenfolge
    var ordered: [DeviceModel] {
        let a = all
        var out: [DeviceModel] = []
        for id in order {
            if let d = a.first(where: { $0.id == id }), !out.contains(where: { $0.id == id }) { out.append(d) }
        }
        for d in a where !out.contains(where: { $0.id == d.id }) { out.append(d) }
        return out
    }

    /// Kacheln der Startseite (ohne ausgeblendete)
    var visible: [DeviceModel] {
        ordered.filter { !hidden.contains($0.id) }
    }

    func setHidden(_ id: String, _ hide: Bool) {
        var h = hidden.filter { $0 != id }
        if hide { h.append(id) }
        hidden = h
    }

    init() {
        order = UserDefaults.standard.stringArray(forKey: "home.order") ?? []
        hidden = DeviceModel.demoMode ? [] : (UserDefaults.standard.stringArray(forKey: "home.hidden") ?? [])
        for d in all { d.loadSettings() }
        if DeviceModel.demoMode {
            for d in all { d.loadDemo(); d.state = .online; d.lastUpdate = Date() }
        }
    }

    func refreshAll() async {
        await withTaskGroup(of: Void.self) { g in
            for d in visible where d.isConfigured {
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
            sceneMessage = ok.isEmpty ? "Kein Gerät für Szenen eingerichtet (je Gerät in den Einstellungen)." :
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
    @EnvironmentObject var updates: UpdateCenter
    @State private var showAbout = false
    @State private var showArrange = false
    @State private var path: [String] = []

    private let cols = [GridItem(.adaptive(minimum: 158), spacing: 12)]

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    sceneBar
                    if updates.showUpdateBanner || updates.expiresSoon {
                        HomeBanner(showAbout: $showAbout)
                    }
                    Text("Geräte").font(.title3.bold()).padding(.horizontal, 4)
                    LazyVGrid(columns: cols, spacing: 12) {
                        ForEach(hub.visible, id: \.id) { d in
                            NavigationLink(value: d.id) {
                                DeviceTile(model: d)
                            }
                            .buttonStyle(.plain)
                            .contextMenu {
                                ForEach(d.quickActions) { qa in
                                    Button {
                                        Haptics.tap()
                                        qa.run()
                                    } label: {
                                        Label(qa.title, systemImage: qa.symbol)
                                    }
                                }
                                Divider()
                                Button {
                                    Task { await d.refresh() }
                                } label: {
                                    Label("Status aktualisieren", systemImage: "arrow.clockwise")
                                }
                                Button {
                                    hub.setHidden(d.id, true)
                                } label: {
                                    Label("Kachel ausblenden", systemImage: "eye.slash")
                                }
                            }
                        }
                    }
                    if !hub.hidden.isEmpty {
                        Button {
                            showArrange = true
                        } label: {
                            Label("\(hub.hidden.count) ausgeblendet - Startseite anpassen", systemImage: "eye.slash")
                                .font(.footnote)
                        }
                        .padding(.horizontal, 4)
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
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        showArrange = true
                    } label: {
                        Image(systemName: "square.grid.2x2")
                    }
                    .accessibilityLabel("Startseite anpassen")
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showAbout = true
                    } label: {
                        Image(systemName: updates.updateAvailable ? "arrow.down.circle.fill" : "info.circle")
                    }
                    .accessibilityLabel("Info und Update")
                }
            }
            .refreshable { await hub.refreshAll() }
            .task {
                if let p = DeviceModel.launchArg("-page"), path.isEmpty { path = [p] }
                if DeviceModel.launchArg("-about") != nil { showAbout = true }
                if DeviceModel.launchArg("-arrange") != nil { showArrange = true }
                await hub.refreshAll()
            }
            .sheet(isPresented: $showAbout) { AboutView() }
            .sheet(isPresented: $showArrange) { ArrangeView() }
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

// ---------------------------------------------------------------------------
// Hinweis-Banner: Update verfuegbar / Signatur laeuft ab
// ---------------------------------------------------------------------------
struct HomeBanner: View {
    @EnvironmentObject var updates: UpdateCenter
    @Binding var showAbout: Bool

    var body: some View {
        VStack(spacing: 10) {
            if updates.showUpdateBanner, let r = updates.remote {
                bannerRow(symbol: "arrow.down.circle.fill", tint: Color(hex: 0x0A84FF),
                          title: "Update verfügbar: Version \(r.version) (Build \(r.build))",
                          text: r.notes.isEmpty ? "Tippen für Details und Installation." : r.notes)
            }
            if updates.expiresSoon {
                bannerRow(symbol: "exclamationmark.triangle.fill", tint: .orange,
                          title: "Signatur läuft bald ab",
                          text: "Gültig bis \(updates.expiryText). Mit Sideloadly neu installieren - Einstellungen bleiben erhalten.")
            }
        }
    }

    private func bannerRow(symbol: String, tint: Color, title: String, text: String) -> some View {
        Button {
            showAbout = true
        } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: symbol).font(.title2).foregroundStyle(tint)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                    Text(text).font(.footnote).foregroundStyle(.secondary).lineLimit(3)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.footnote).foregroundStyle(.tertiary)
            }
            .padding(14)
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Color(.secondarySystemGroupedBackground)))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(tint.opacity(0.6), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// ---------------------------------------------------------------------------
// Startseite anpassen: Reihenfolge und Sichtbarkeit der Kacheln
// ---------------------------------------------------------------------------
struct ArrangeView: View {
    @EnvironmentObject var hub: DeviceHub
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(hub.ordered, id: \.id) { d in
                        HStack(spacing: 12) {
                            DeviceIcon(symbol: d.symbol, tint: d.tint, size: 30)
                            Text(d.title)
                            Spacer()
                            Toggle("", isOn: Binding(get: { !hub.hidden.contains(d.id) },
                                                     set: { hub.setHidden(d.id, !$0) }))
                                .labelsHidden()
                        }
                    }
                    .onMove { from, to in
                        var ids = hub.ordered.map { $0.id }
                        ids.move(fromOffsets: from, toOffset: to)
                        hub.order = ids
                    }
                } footer: {
                    Text("Am Griff rechts ziehen = Reihenfolge ändern. Schalter aus = Kachel ausblenden (Gerät wird dann auch nicht mehr abgefragt; Szenen schalten es weiterhin).")
                }
                Section {
                    Button("Standard wiederherstellen") {
                        hub.order = []
                        hub.hidden = []
                    }
                }
            }
            .environment(\.editMode, .constant(.active))
            .navigationTitle("Startseite anpassen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Info, Update, Signatur, Sicherung
// ---------------------------------------------------------------------------
struct AboutView: View {
    @EnvironmentObject var hub: DeviceHub
    @EnvironmentObject var updates: UpdateCenter
    @Environment(\.dismiss) private var dismiss
    @State private var backupURL: URL?
    @State private var showImport = false
    @State private var askRestore: URL?
    @State private var note: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 14) {
                        DeviceIcon(symbol: "slider.horizontal.3", tint: Color(hex: 0x0A84FF), size: 60)
                        VStack(alignment: .leading) {
                            Text("Studio Control").font(.title2.bold())
                            Text("Version \(APP_VERSION) (Build \(APP_BUILD))").foregroundStyle(.secondary)
                            Text("T. Pfeiffer").foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 6)
                }
                updateSection
                signatureSection
                backupSection
                Section("Hinweise") {
                    Text("Das iPhone muss im selben Netzwerk (WLAN) wie die Geräte sein. Beim ersten Start fragt iOS nach dem Zugriff auf das lokale Netzwerk - bitte erlauben (sonst: Einstellungen > Datenschutz > Lokales Netzwerk > Studio).")
                    Text("Einstellungen (IP-Adressen, Kennwörter) liegen verschlüsselt im iOS-Schlüsselbund und bleiben bei Updates erhalten.")
                    Text("Szenen: In den Einstellungen von Beamer, Steckdosen und ClickShare festlegen, was 'Studio an' und 'Studio aus' schalten.")
                    Text("Kachel lange drücken = Schnellaktionen (z.B. Beamer ein/aus) ohne die Seite zu öffnen.")
                }
            }
            .navigationTitle("Info & Update")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                if DeviceModel.demoMode, let n = Int(DeviceModel.launchArg("-scrollPage") ?? "") {
                    DemoScroll.scroll(page: n)
                }
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Fertig") { dismiss() } }
            }
            .fileImporter(isPresented: $showImport, allowedContentTypes: [.json]) { result in
                if case .success(let url) = result { askRestore = url }
            }
            .alert("Sicherung einspielen?", isPresented: Binding(get: { askRestore != nil }, set: { if !$0 { askRestore = nil } })) {
                Button("Einspielen", role: .destructive) {
                    if let u = askRestore { restore(u) }
                }
                Button("Abbrechen", role: .cancel) {}
            } message: {
                Text("Die Einstellungen aller Geräte in der Datei ersetzen die jetzigen.")
            }
            .alert("Studio Control", isPresented: Binding(get: { note != nil || updates.message != nil },
                                                          set: { if !$0 { note = nil; updates.message = nil } })) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(note ?? updates.message ?? "")
            }
        }
    }

    private var updateSection: some View {
        Section {
            if let r = updates.remote, updates.updateAvailable {
                VStack(alignment: .leading, spacing: 4) {
                    Label("Version \(r.version) (Build \(r.build)) verfügbar", systemImage: "arrow.down.circle.fill")
                        .font(.headline).foregroundStyle(Color(hex: 0x0A84FF))
                    if !r.date.isEmpty { Text("Gebaut \(r.date)").font(.caption).foregroundStyle(.secondary) }
                    if !r.notes.isEmpty { Text(r.notes).font(.footnote) }
                }
                .padding(.vertical, 2)
                Button {
                    updates.openInStore("sidestore")
                } label: {
                    Label("Mit SideStore installieren", systemImage: "square.and.arrow.down")
                }
                Button {
                    updates.openInStore("altstore")
                } label: {
                    Label("Mit AltStore installieren", systemImage: "square.and.arrow.down")
                }
                Button {
                    updates.open(UpdateCenter.pageURL)
                } label: {
                    Label("Download-Seite öffnen (für Sideloadly am PC)", systemImage: "safari")
                }
                if updates.showUpdateBanner {
                    Button("Diese Version überspringen") { updates.skipCurrent() }
                }
            } else {
                ValueRow(label: "Stand", value: updates.remote == nil ? "noch nicht geprüft" : "aktuell", symbol: "checkmark.circle")
            }
            Button {
                Task { await updates.check(force: true) }
            } label: {
                HStack {
                    Label("Nach Update suchen", systemImage: "arrow.triangle.2.circlepath")
                    Spacer()
                    if updates.checking { ProgressView() }
                }
            }
            .disabled(updates.checking)
            if let t = updates.lastCheck {
                ValueRow(label: "Zuletzt geprüft", value: t.formatted(date: .abbreviated, time: .shortened))
            }
            if let e = updates.error {
                Text(e).font(.caption).foregroundStyle(.red)
            }
            DisclosureGroup("Updates direkt am iPhone (ohne PC)") {
                Text("Mit AltStore oder SideStore lässt sich die App am iPhone selbst aktualisieren. Einmal die Quelle hinzufügen - danach meldet der Store neue Versionen und installiert sie per Fingertipp.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button("Quelle zu SideStore hinzufügen") { updates.addSource("sidestore") }
                Button("Quelle zu AltStore hinzufügen") { updates.addSource("altstore") }
                Button("Quellen-Adresse kopieren") {
                    UIPasteboard.general.string = UpdateCenter.sourceURL
                    Haptics.success()
                }
            }
        } header: {
            Text("Update")
        } footer: {
            Text("Die App prüft beim Öffnen (höchstens alle 6 Stunden), ob bei GitHub eine neuere Version liegt. Installiert wird mit Sideloadly am PC oder mit AltStore/SideStore am iPhone - selbst installieren darf sich eine iOS-App nicht.")
        }
    }

    private var signatureSection: some View {
        Section {
            ValueRow(label: "Gültig bis", value: updates.expiryText, symbol: "signature",
                     valueColor: updates.expiresSoon ? .orange : .secondary)
            Toggle(isOn: Binding(get: { updates.reminderOn }, set: { updates.setReminder($0) })) {
                Label("Vor Ablauf erinnern", systemImage: "bell")
            }
        } header: {
            Text("Signatur")
        } footer: {
            Text("Mit kostenloser Apple-ID gilt die Signatur 7 Tage. Die Erinnerung kommt 24 und 3 Stunden vorher als Mitteilung. Neu installieren mit derselben oder einer neueren .ipa - Einstellungen bleiben erhalten.")
        }
    }

    private var backupSection: some View {
        Section {
            if let u = backupURL {
                ShareLink(item: u) {
                    Label("Sicherung teilen / in Dateien sichern", systemImage: "square.and.arrow.up")
                }
            } else {
                Button {
                    backupURL = SettingsBackup.export(hub.all)
                    if backupURL == nil { note = "Sicherung konnte nicht erstellt werden." }
                } label: {
                    Label("Sicherung erstellen", systemImage: "externaldrive.badge.plus")
                }
            }
            Button {
                showImport = true
            } label: {
                Label("Sicherung einspielen ...", systemImage: "externaldrive.badge.timemachine")
            }
        } header: {
            Text("Einstellungen sichern")
        } footer: {
            Text("Eine Datei mit den Einstellungen aller Geräte (IP-Adressen, Namen, Relais, Kennwörter). Achtung: Kennwörter stehen lesbar in der Datei - nur an sicherem Ort ablegen.")
        }
    }

    private func restore(_ url: URL) {
        do {
            let n = try SettingsBackup.restore(from: url, into: hub.all)
            note = "\(n) Einstellungssätze übernommen."
            Haptics.success()
            Task { await hub.refreshAll() }
        } catch {
            note = "Einspielen fehlgeschlagen: \(DeviceModel.describe(error))"
            Haptics.error()
        }
    }
}
