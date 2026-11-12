// ===========================================================================
//  OtherViews.swift - PA AV Toolbox iOS v1.0.0
//  Autor: T. Pfeiffer
//  Discovery, Terminal, Ping, Info
// ===========================================================================
import SwiftUI
import UIKit

// ===========================================================================
//  Discovery
// ===========================================================================
struct DiscoveryView: View {
    @EnvironmentObject var m: DiscoveryModel
    @State private var pick: HostPick?
    @State private var url: URL?
    @State private var showLog = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    Card {
                        FieldLabel(text: "IP-Bereiche (Komma getrennt)")
                        TextField("192.168.0.1-254, 10.0.0.0/24", text: $m.ranges)
                            .textFieldStyle(.roundedBorder)
                            .keyboardType(.numbersAndPunctuation)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.never)
                        FieldLabel(text: "Ports (leer = Kennports der Klassen)")
                        TextField("z.B. 1710, 23, 4352", text: $m.ports)
                            .textFieldStyle(.roundedBorder)
                            .keyboardType(.numbersAndPunctuation)
                        Stepper("Parallel: \(m.parallel)", value: $m.parallel, in: 8...128, step: 8)
                        FieldLabel(text: "Klassen")
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: 8)], spacing: 8) {
                            ForEach(DISC_CLASSES.map { $0.0 }, id: \.self) { c in
                                let on = m.classes.contains(c)
                                Button {
                                    if on { m.classes.remove(c) } else { m.classes.insert(c) }
                                } label: {
                                    Text(c).font(.footnote.bold())
                                        .frame(maxWidth: .infinity).padding(.vertical, 7)
                                        .background(on ? Color.house : Color(.tertiarySystemFill))
                                        .foregroundColor(on ? Color.white : Color.primary)
                                        .clipShape(Capsule())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        if m.running {
                            Button(role: .destructive) { m.stopScan() } label: {
                                Label("Stop", systemImage: "stop.fill").frame(maxWidth: .infinity)
                            }.buttonStyle(.bordered)
                        } else {
                            Button { hideKeyboard(); url = nil; m.start() } label: {
                                Label("Suchen", systemImage: "magnifyingglass").frame(maxWidth: .infinity)
                            }.buttonStyle(.borderedProminent)
                        }
                        ProgressView(value: m.progress)
                        Text(m.status).font(.footnote).foregroundColor(.secondary)
                    }

                    Card {
                        HStack {
                            Text("Geraete").font(.headline)
                            Spacer()
                            Toggle("nur bestaetigte", isOn: $m.onlyConfirmed)
                                .font(.caption).fixedSize()
                        }
                        if m.visibleRows.isEmpty {
                            Text("Noch keine Geraete").font(.footnote).foregroundColor(.secondary)
                        }
                        ForEach(m.visibleRows) { r in
                            Button { pick = HostPick(ip: r.ip, port: nil) } label: {
                                HStack(alignment: .top, spacing: 10) {
                                    Image(systemName: r.confirmed ? "checkmark.seal.fill" : "questionmark.circle")
                                        .foregroundColor(r.confirmed ? .okGreen : .secondary)
                                        .font(.title3)
                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack {
                                            Text(r.vendor).font(.subheadline.bold())
                                            Spacer()
                                            Text(r.ip).font(.system(.footnote, design: .monospaced))
                                        }
                                        if !r.model.isEmpty {
                                            Text(r.model).font(.caption).foregroundColor(.primary)
                                        }
                                        Text("Ports: " + r.portsText).font(.caption2).foregroundColor(.secondary)
                                    }
                                }
                                .padding(.vertical, 4)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            Divider()
                        }
                    }

                    Card {
                        DisclosureGroup("Protokoll", isExpanded: $showLog) {
                            LogBox(lines: m.log)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Discovery")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if let u = url {
                        ShareLink(item: u) { Image(systemName: "square.and.arrow.up") }
                    } else {
                        Button { url = m.exportCSV() } label: { Image(systemName: "doc.badge.plus") }
                            .disabled(m.visibleRows.isEmpty || m.running)
                    }
                }
            }
            .onChange(of: m.onlyConfirmed) { _ in url = nil }
            .hostActions($pick)
        }
    }
}

// ===========================================================================
//  Terminal
// ===========================================================================
struct TerminalView: View {
    @EnvironmentObject var t: TermModel
    @FocusState private var inputFocus: Bool

    private var groups: [String] {
        var g: [String] = []
        for p in PRESETS where !g.contains(p.group) { g.append(p.group) }
        return g
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 8) {
                // Verbindung
                HStack(spacing: 6) {
                    TextField("IP / Host", text: $t.ip)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numbersAndPunctuation)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    TextField("Port", text: $t.port)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numberPad)
                        .frame(width: 70)
                    Picker("", selection: $t.proto) {
                        Text("TCP").tag("TCP")
                        Text("UDP").tag("UDP")
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 100)
                    .disabled(t.connected)
                }
                HStack {
                    Circle().fill(t.connected ? Color.okGreen : Color.gray).frame(width: 12, height: 12)
                    Text(t.state).font(.caption).lineLimit(1)
                    Spacer()
                    Button(t.connected ? "Trennen" : "Verbinden") { hideKeyboard(); t.toggle() }
                        .buttonStyle(.borderedProminent)
                        .tint(t.connected ? Color.errRed : Color.accentBlue)
                }

                // Ausgabe
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(t.lines) { l in
                                Text(l.text)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(color(l.kind))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .textSelection(.enabled)
                                    .id(l.id)
                            }
                        }
                        .padding(8)
                    }
                    .background(Color.consoleBg)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .onChange(of: t.lines.count) { _ in
                        if let last = t.lines.last { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }

                // Optionen
                HStack {
                    Menu {
                        ForEach(TERMINATORS.map { $0.0 }, id: \.self) { n in
                            Button(n) { t.term = n }
                        }
                    } label: {
                        Label("Ende: \(t.term)", systemImage: "return").font(.caption)
                    }
                    Spacer()
                    Toggle("Hex senden", isOn: $t.hexSend).font(.caption).fixedSize()
                    Toggle("Hex anz.", isOn: $t.hexShow).font(.caption).fixedSize()
                }

                // Eingabe
                HStack {
                    TextField(t.hexSend ? "81 01 04 00 02 FF" : "Befehl  (\\r \\n \\x1b erlaubt)", text: $t.input)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(.body, design: .monospaced))
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .focused($inputFocus)
                        .submitLabel(.send)
                        .onSubmit { t.send() }
                    Button { t.send() } label: { Image(systemName: "paperplane.fill") }
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 8)
            .navigationTitle("Terminal")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Menu {
                        ForEach(groups, id: \.self) { g in
                            Section(g) {
                                ForEach(PRESETS.filter { $0.group == g }) { p in
                                    Button(p.desc) { t.use(p) }
                                }
                            }
                        }
                    } label: {
                        Label("Vorlagen", systemImage: "list.bullet.rectangle")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { t.clear() } label: { Image(systemName: "trash") }
                }
            }
        }
    }

    private func color(_ k: LineKind) -> Color {
        switch k {
        case .tx: return Color(hex: 0x6CB4FF)
        case .rx: return Color(hex: 0x9BE09B)
        case .info: return Color(hex: 0xF5D36B)
        }
    }
}

// ===========================================================================
//  Ping
// ===========================================================================
struct PingView: View {
    @EnvironmentObject var p: PingModel

    var body: some View {
        NavigationStack {
            VStack(spacing: 10) {
                HStack {
                    TextField("IP / Hostname", text: $p.target)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numbersAndPunctuation)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    if p.running {
                        Button("Stop") { p.stopPing() }.buttonStyle(.bordered).tint(.errRed)
                    } else {
                        Button("Start") { hideKeyboard(); p.start() }.buttonStyle(.borderedProminent)
                    }
                }
                HStack(spacing: 8) {
                    stat("Gesendet", "\(p.sent)")
                    stat("Antworten", "\(p.recv)")
                    stat("Verlust", p.lossText + " %")
                }
                Card {
                    FieldLabel(text: "min / avg / max")
                    Text(p.rttText + " ms").font(.system(.title3, design: .monospaced)).bold()
                }
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(p.lines) { l in
                                Text(l.text)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(l.kind == .rx ? Color(hex: 0x9BE09B) : Color(hex: 0xFF8A8A))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .id(l.id)
                            }
                        }
                        .padding(8)
                    }
                    .background(Color.consoleBg)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .onChange(of: p.lines.count) { _ in
                        if let last = p.lines.last { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 8)
            .navigationTitle("Ping")
        }
    }

    private func stat(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.system(.title3, design: .rounded)).bold()
            Text(title).font(.caption2).foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

// ===========================================================================
//  Info
// ===========================================================================
struct InfoView: View {
    @State private var ownIP = "-"

    var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(AppInfo.name).font(.title2.bold()).foregroundColor(.house)
                        Text("Version \(AppInfo.version)  -  basiert auf \(AppInfo.basedOn)")
                            .font(.footnote).foregroundColor(.secondary)
                        Text("Autor: \(AppInfo.author)").font(.footnote)
                    }
                    .padding(.vertical, 4)
                }
                Section("Dieses Geraet") {
                    HStack { Text("Eigene IP"); Spacer(); Text(ownIP).font(.system(.body, design: .monospaced)) }
                    HStack { Text("Ziel-Vorschlag"); Spacer(); Text(Net.defaultTarget()).font(.system(.body, design: .monospaced)) }
                }
                Section {
                    Text("Beim ersten Start fragt iOS nach dem Zugriff auf das lokale Netzwerk - bitte erlauben. Nachtraeglich: Einstellungen > Datenschutz & Sicherheit > Lokales Netzwerk > AV Toolbox.")
                        .font(.footnote)
                    Button("Einstellungen oeffnen") {
                        if let u = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(u) }
                    }
                } header: {
                    Text("Lokales Netzwerk")
                } footer: {
                    Text("Ohne diese Freigabe findet die App keine Geraete im WLAN.")
                }
                Section {
                    row("NetScanner: Port / IP / Deep", true)
                    row("Discovery mit Modellabfrage", true)
                    row("Terminal TCP / UDP / Telnet + Vorlagen", true)
                    row("Dauer-Ping mit Statistik", true)
                    row("CSV-Export (Teilen-Menue)", true)
                    row("MAC-Scan / Hersteller (OUI)", false)
                    row("Programme starten (Werkzeuge)", false)
                    row("Netzwerkkarte umstellen (Adapter)", false)
                } header: {
                    Text("Funktionen")
                } footer: {
                    Text("iOS sperrt fuer Apps den Zugriff auf MAC-Adressen (ARP-Tabelle) und die Netzwerkeinstellungen. Diese Funktionen gibt es nur in der Windows-Toolbox.")
                }
            }
            .navigationTitle("Info")
            .onAppear { ownIP = Net.localIPv4()?.ip ?? "kein WLAN" }
        }
    }

    private func row(_ t: String, _ ok: Bool) -> some View {
        HStack {
            Image(systemName: ok ? "checkmark.circle.fill" : "xmark.circle")
                .foregroundColor(ok ? .okGreen : .secondary)
            Text(t).foregroundColor(ok ? .primary : .secondary)
        }
    }
}
