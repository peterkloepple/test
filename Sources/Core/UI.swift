// ===========================================================================
//  UI.swift - Studio Control iOS - gemeinsame Bausteine fuer alle Geraeteseiten
//  Autor: T. Pfeiffer
//
//  DevicePage      - Rahmen jeder Geraeteseite (Statuskarte, Inhalt, Protokoll,
//                    Einstellungen-Knopf, Ziehen zum Aktualisieren, Auto-Aktualisierung)
//  ActionTile      - grosse Kachel-Taste (wie Kontrollzentrum)
//  ValueRow        - Zeile "Name ... Wert"
//  LevelBar        - Pegel-/Fuellstandsbalken
//  SettingsSheet   - Einstellungen als Formular mit Sichern/Abbrechen
// ===========================================================================
import SwiftUI

// ---------------------------------------------------------------------------
// Geraeteseite
// ---------------------------------------------------------------------------
struct DevicePage<Content: View, Settings: View>: View {
    @ObservedObject var model: DeviceModel
    let settings: () -> Settings
    let content: () -> Content
    @State private var showSettings = false
    @State private var showLog = false
    @Environment(\.scenePhase) private var phase

    init(model: DeviceModel, @ViewBuilder settings: @escaping () -> Settings, @ViewBuilder content: @escaping () -> Content) {
        self.model = model
        self.settings = settings
        self.content = content
    }

    var body: some View {
        List {
            Section {
                StatusCard(model: model)
            }
            .listRowInsets(EdgeInsets(top: 10, leading: 14, bottom: 10, trailing: 14))
            if model.state == .notConfigured {
                Section {
                    Button {
                        showSettings = true
                    } label: {
                        Label("Jetzt einrichten (IP-Adresse eintragen)", systemImage: "gearshape")
                    }
                }
            }
            content()
            Section {
                DisclosureGroup(isExpanded: $showLog) {
                    if model.log.isEmpty {
                        Text("Noch keine Einträge").foregroundStyle(.secondary).font(.footnote)
                    }
                    ForEach(model.log.prefix(60)) { line in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(line.time, style: .time).font(.caption2).foregroundStyle(.secondary)
                            Text(line.text).font(.footnote).foregroundStyle(line.isError ? Color.red : Color.primary)
                                .textSelection(.enabled)
                        }
                    }
                } label: {
                    Label("Protokoll", systemImage: "list.bullet.rectangle")
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(model.title)
        .navigationBarTitleDisplayMode(.large)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                HStack(spacing: 14) {
                    if model.busy { ProgressView() }
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("Einstellungen")
                }
            }
        }
        .refreshable { await model.refresh() }
        .onAppear {
            if DeviceModel.launchArg("-settings") == model.id { showSettings = true }
            if DeviceModel.launchArg("-log") == model.id { showLog = true }
            if DeviceModel.demoMode, let n = Int(DeviceModel.launchArg("-scrollPage") ?? "") {
                DemoScroll.scroll(page: n)
            }
        }
        .task(id: phase) {
            guard phase == .active else { return }
            await model.refresh()
            let iv = model.pollInterval
            guard iv > 0 else { return }
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(iv * 1_000_000_000))
                if Task.isCancelled { break }
                if !model.busy { await model.refresh() }
            }
        }
        .sheet(isPresented: $showSettings, onDismiss: {
            Task { await model.refresh() }
        }) {
            settings()
        }
    }
}

// ---------------------------------------------------------------------------
// Statuskarte oben auf jeder Seite
// ---------------------------------------------------------------------------
struct StatusCard: View {
    @ObservedObject var model: DeviceModel

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            DeviceIcon(symbol: model.symbol, tint: model.tint, size: 54)
            VStack(alignment: .leading, spacing: 4) {
                Text(model.subtitle).font(.subheadline).foregroundStyle(.secondary)
                HStack(spacing: 6) {
                    StateDot(state: model.state)
                    Text(stateText).font(.headline)
                }
                if !model.summary.isEmpty {
                    Text(model.summary).font(.subheadline).foregroundStyle(.primary).lineLimit(2)
                }
                if let err = model.lastError, model.state != .notConfigured {
                    Text(err).font(.caption).foregroundStyle(.red).lineLimit(3)
                } else if let t = model.lastUpdate {
                    Text("Stand \(t.formatted(date: .omitted, time: .standard))").font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
        }
    }

    var stateText: String {
        switch model.state {
        case .online: return "Verbunden"
        case .offline: return "Nicht erreichbar"
        case .unknown: return "Wird geprüft ..."
        case .notConfigured: return "Nicht eingerichtet"
        }
    }
}

struct StateDot: View {
    let state: DeviceState
    var body: some View {
        Circle().fill(color).frame(width: 9, height: 9)
    }
    var color: Color {
        switch state {
        case .online: return .green
        case .offline: return .red
        case .unknown: return .orange
        case .notConfigured: return .gray
        }
    }
}

struct DeviceIcon: View {
    let symbol: String
    let tint: Color
    var size: CGFloat = 44

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.27, style: .continuous)
                .fill(LinearGradient(colors: [tint.opacity(0.95), tint.opacity(0.7)], startPoint: .top, endPoint: .bottom))
            Image(systemName: symbol)
                .font(.system(size: size * 0.46, weight: .semibold))
                .foregroundStyle(.white)
        }
        .frame(width: size, height: size)
    }
}

// ---------------------------------------------------------------------------
// Grosse Kachel-Taste
// ---------------------------------------------------------------------------
struct ActionTile: View {
    let title: String
    let symbol: String
    var tint: Color = .accentColor
    var active: Bool = false
    var disabled: Bool = false
    let action: () -> Void

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                Image(systemName: symbol)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(active ? .white : tint)
                Text(title)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(active ? .white : .primary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                    .minimumScaleFactor(0.8)
            }
            .frame(maxWidth: .infinity, minHeight: 74, alignment: .leading)
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(active ? AnyShapeStyle(tint.gradient) : AnyShapeStyle(Color(.tertiarySystemFill)))
            )
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.45 : 1)
    }
}

/// Raster aus Kacheln als eigene Listenzeile.
struct TileGrid<Content: View>: View {
    var columns: Int = 2
    @ViewBuilder let content: () -> Content

    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: columns), spacing: 10) {
            content()
        }
        .padding(.vertical, 4)
    }
}

// ---------------------------------------------------------------------------
// Zeilen
// ---------------------------------------------------------------------------
struct ValueRow: View {
    let label: String
    let value: String
    var symbol: String? = nil
    var valueColor: Color = .secondary

    var body: some View {
        HStack {
            if let s = symbol {
                Label(label, systemImage: s)
            } else {
                Text(label)
            }
            Spacer()
            Text(value).foregroundStyle(valueColor).multilineTextAlignment(.trailing).textSelection(.enabled)
        }
    }
}

struct LevelBar: View {
    /// 0...1
    let value: Double
    var tint: Color = .green
    var height: CGFloat = 8

    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Color(.tertiarySystemFill))
                Capsule().fill(tint.gradient)
                    .frame(width: max(0, min(1, value)) * g.size.width)
            }
        }
        .frame(height: height)
        .animation(.easeOut(duration: 0.2), value: value)
    }
}

/// Ein-/Aus-Schalter mit Text und Symbol, der eine async-Aktion ausloest.
struct PowerToggleRow: View {
    let title: String
    var symbol: String = "power"
    let isOn: Bool
    var tint: Color = .green
    let set: (Bool) -> Void

    var body: some View {
        Toggle(isOn: Binding(get: { isOn }, set: { v in Haptics.tap(); set(v) })) {
            Label(title, systemImage: symbol)
        }
        .tint(tint)
    }
}

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------
struct SettingsSheet<Content: View>: View {
    let title: String
    let onSave: () -> Void
    @ViewBuilder let content: () -> Content
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                content()
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Sichern") {
                        onSave()
                        Haptics.success()
                        dismiss()
                    }
                    .bold()
                }
            }
        }
    }
}

struct FieldRow: View {
    let label: String
    @Binding var text: String
    var placeholder: String = ""
    var keyboard: UIKeyboardType = .default
    var secure: Bool = false

    var body: some View {
        HStack {
            Text(label)
            Spacer(minLength: 12)
            Group {
                if secure {
                    SecureField(placeholder, text: $text)
                } else {
                    TextField(placeholder, text: $text)
                        .keyboardType(keyboard)
                }
            }
            .multilineTextAlignment(.trailing)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .foregroundStyle(.secondary)
        }
    }
}

/// Zahl als Text-Binding fuer FieldRow
func intBinding(_ b: Binding<Int>) -> Binding<String> {
    Binding(get: { String(b.wrappedValue) }, set: { b.wrappedValue = Int($0.trimmed) ?? b.wrappedValue })
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xff) / 255, green: Double((hex >> 8) & 0xff) / 255,
                  blue: Double(hex & 0xff) / 255)
    }
}


// ---------------------------------------------------------------------------
// Nur Demo/Handbuch: oberste Liste um n Bildschirmhoehen scrollen
// ---------------------------------------------------------------------------
enum DemoScroll {
    static func scroll(page: Int) {
        guard page > 0 else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            let wins = UIApplication.shared.connectedScenes.compactMap { ($0 as? UIWindowScene)?.keyWindow }
            guard let win = wins.first, var top = win.rootViewController else { return }
            while let p = top.presentedViewController { top = p }
            guard let sv = find(top.view) else { return }
            let ins = sv.adjustedContentInset
            let visible = sv.bounds.height - ins.top - ins.bottom
            let maxY = max(-ins.top, sv.contentSize.height - sv.bounds.height + ins.bottom)
            let y = min(CGFloat(page) * visible * 0.88 - ins.top, maxY)
            sv.setContentOffset(CGPoint(x: 0, y: y), animated: false)
        }
    }

    private static func find(_ v: UIView) -> UIScrollView? {
        if let s = v as? UIScrollView, !(s is UITextView), s.contentSize.height > s.bounds.height + 20 {
            return s
        }
        for c in v.subviews {
            if let r = find(c) { return r }
        }
        return nil
    }
}
