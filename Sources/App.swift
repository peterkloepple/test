// ===========================================================================
//  App.swift - PA AV Toolbox iOS v1.0.0
//  Autor: T. Pfeiffer
//  iPhone-Version der Pfeiffer-Audio AV Toolbox (Windows 1.3.0).
//  Reiter: NetScanner, Discovery, Terminal, Ping, Info
// ===========================================================================
import SwiftUI
import UIKit

enum AppInfo {
    static let name = "PA AV Toolbox"
    static let version = "1.0.0"
    static let basedOn = "Windows-Toolbox 1.3.0"
    static let author = "T. Pfeiffer"
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255.0,
                  green: Double((hex >> 8) & 0xFF) / 255.0,
                  blue: Double(hex & 0xFF) / 255.0)
    }
    static let house = Color(hex: 0x3C4860)
    static let accentBlue = Color(hex: 0x0A84FF)
    static let okGreen = Color(hex: 0x30D158)
    static let warnOrange = Color(hex: 0xFF9F0A)
    static let errRed = Color(hex: 0xFF453A)
    static let consoleBg = Color(hex: 0x10151C)
    static let consoleFg = Color(hex: 0xD7DEEA)
}

enum AppTab: Hashable {
    case scanner, discovery, terminal, ping, info
}

/// Gemeinsamer Zustand: alle Modelle + Reiterwahl (fuer Uebergaben)
final class AppState: ObservableObject {
    @Published var tab: AppTab = .scanner
    let scanner = ScannerModel()
    let discovery = DiscoveryModel()
    let term = TermModel()
    let ping = PingModel()

    func toTerminal(ip: String, port: String? = nil) {
        term.ip = ip
        if let p = port, !term.connected { term.port = p }
        tab = .terminal
    }

    func toPing(ip: String) {
        ping.target = ip
        tab = .ping
    }

    /// Loest die iOS-Abfrage "Lokales Netzwerk" frueh aus
    func warmUpLocalNetwork() {
        DispatchQueue.global(qos: .utility).async {
            guard let l = Net.localIPv4() else { return }
            let parts = l.ip.split(separator: ".")
            guard parts.count == 4 else { return }
            let gw = "\(parts[0]).\(parts[1]).\(parts[2]).1"
            _ = Net.tcpProbe(gw, 80, timeout: 0.5)
        }
    }
}

@main
struct PAAVToolboxApp: App {
    @StateObject private var app = AppState()

    init() {
        print("\(AppInfo.name) iOS v\(AppInfo.version) INIT - Autor: \(AppInfo.author)")
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .environmentObject(app.scanner)
                .environmentObject(app.discovery)
                .environmentObject(app.term)
                .environmentObject(app.ping)
                .tint(Color.accentBlue)
                .onAppear { app.warmUpLocalNetwork() }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        TabView(selection: $app.tab) {
            ScannerView()
                .tabItem { Label("NetScanner", systemImage: "dot.radiowaves.left.and.right") }
                .tag(AppTab.scanner)
            DiscoveryView()
                .tabItem { Label("Discovery", systemImage: "magnifyingglass") }
                .tag(AppTab.discovery)
            TerminalView()
                .tabItem { Label("Terminal", systemImage: "terminal") }
                .tag(AppTab.terminal)
            PingView()
                .tabItem { Label("Ping", systemImage: "waveform.path.ecg") }
                .tag(AppTab.ping)
            InfoView()
                .tabItem { Label("Info", systemImage: "info.circle") }
                .tag(AppTab.info)
        }
    }
}

// ===========================================================================
//  Gemeinsame Bausteine
// ===========================================================================
struct Card<Content: View>: View {
    let content: Content
    init(@ViewBuilder _ content: () -> Content) { self.content = content() }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) { content }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

struct FieldLabel: View {
    let text: String
    var body: some View {
        Text(text).font(.caption).foregroundColor(.secondary)
    }
}

struct LogBox: View {
    let lines: [String]
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(lines.enumerated()), id: \.offset) { i, l in
                        Text(l)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(.consoleFg)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .id(i)
                    }
                }
                .padding(8)
            }
            .frame(height: 130)
            .background(Color.consoleBg)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .onChange(of: lines.count) { n in
                if n > 0 { proxy.scrollTo(n - 1, anchor: .bottom) }
            }
        }
    }
}

/// Ausgewaehlter Treffer (IP + optional Port aus dem Port-Scan)
struct HostPick: Identifiable, Equatable {
    var id: String { ip + ":" + (port ?? "") }
    let ip: String
    let port: String?
}

/// Aktionen fuer einen Treffer (Scanner / Discovery)
struct HostActions: ViewModifier {
    @EnvironmentObject var app: AppState
    @Environment(\.openURL) private var openURL
    @Binding var pick: HostPick?

    func body(content: Content) -> some View {
        content.confirmationDialog(pick?.ip ?? "",
                                   isPresented: Binding(get: { pick != nil },
                                                        set: { if !$0 { pick = nil } }),
                                   titleVisibility: .visible,
                                   presenting: pick) { p in
            Button("Im Terminal oeffnen") { app.toTerminal(ip: p.ip, port: p.port) }
            Button("Ping starten") { app.toPing(ip: p.ip); app.ping.start() }
            Button("Web-Oberflaeche (http)") {
                if let u = URL(string: "http://\(p.ip)") { openURL(u) }
            }
            Button("IP kopieren") { UIPasteboard.general.string = p.ip }
            Button("Abbrechen", role: .cancel) {}
        }
    }
}

extension View {
    func hostActions(_ pick: Binding<HostPick?>) -> some View {
        modifier(HostActions(pick: pick))
    }
}
