// ===========================================================================
//  ScannerView.swift - PA AV Toolbox iOS v1.0.0
//  Autor: T. Pfeiffer
// ===========================================================================
import SwiftUI
import UIKit

struct ScannerView: View {
    @EnvironmentObject var m: ScannerModel
    @State private var pick: HostPick?
    @State private var showExport = false
    @State private var showLog = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    Card {
                        FieldLabel(text: "Ziel / Subnetz")
                        HStack {
                            TextField("192.168.0  |  192.168.0.0/24  |  IP", text: $m.target)
                                .textFieldStyle(.roundedBorder)
                                .keyboardType(.numbersAndPunctuation)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                            Button { m.useOwnNet() } label: {
                                Image(systemName: "location.circle")
                            }
                            .accessibilityLabel("Eigenes Netz")
                        }
                        Picker("Modus", selection: $m.mode) {
                            ForEach(ScanMode.allCases) { Text($0.title).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        if m.mode == .port {
                            HStack {
                                FieldLabel(text: "Ports")
                                TextField("1", text: $m.p1)
                                    .textFieldStyle(.roundedBorder).keyboardType(.numberPad).frame(width: 80)
                                Text("-")
                                TextField("1024", text: $m.p2)
                                    .textFieldStyle(.roundedBorder).keyboardType(.numberPad).frame(width: 80)
                                Spacer()
                            }
                        }
                        Text(hint).font(.caption2).foregroundColor(.secondary)
                        HStack {
                            if m.running {
                                Button(role: .destructive) { m.stopScan() } label: {
                                    Label("Stop", systemImage: "stop.fill").frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                            } else {
                                Button { hideKeyboard(); m.start() } label: {
                                    Label(m.mode.title + " starten", systemImage: "play.fill").frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                            }
                        }
                        ProgressView(value: m.progress)
                        Text(m.status).font(.footnote).foregroundColor(.secondary)
                    }

                    Card {
                        HStack {
                            Text("Ergebnisse").font(.headline)
                            Spacer()
                            Text("\(m.rows.count)").font(.subheadline).foregroundColor(.secondary)
                        }
                        if m.rows.isEmpty {
                            Text("Noch keine Treffer").font(.footnote).foregroundColor(.secondary)
                        }
                        ForEach(m.rows) { r in
                            Button {
                                let port = r.ports.hasSuffix(" offen") ? String(r.ports.split(separator: " ").first ?? "") : nil
                                pick = HostPick(ip: r.ip, port: port)
                            } label: {
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack {
                                        Text(r.ip).font(.system(.body, design: .monospaced)).bold()
                                        Spacer()
                                        if !r.host.isEmpty {
                                            Text(r.host).font(.caption).foregroundColor(.secondary).lineLimit(1)
                                        }
                                    }
                                    Text(r.ports).font(.caption).foregroundColor(.house).multilineTextAlignment(.leading)
                                }
                                .padding(.vertical, 4)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            Divider()
                        }
                    }

                    Card {
                        DisclosureGroup("Scan-Log", isExpanded: $showLog) {
                            LogBox(lines: m.log)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("NetScanner")
            .toolbar {
                ToolbarItemGroup(placement: .navigationBarTrailing) {
                    Button { m.clear() } label: { Image(systemName: "trash") }
                        .disabled(m.running)
                    Button { showExport = true } label: { Image(systemName: "square.and.arrow.up") }
                        .disabled(m.rows.isEmpty)
                }
            }
            .hostActions($pick)
            .sheet(isPresented: $showExport) { ScanExportSheet() }
        }
    }

    private var hint: String {
        switch m.mode {
        case .port: return "Alle Ports EINER IP, 0,4 s je Port, 100 parallel."
        case .ip: return "Lebend-Test ueber 7 Probe-Ports (offen oder abgelehnt = erreichbar)."
        case .deep: return "49 Dienste je Host inkl. Q-SYS 1710, Crestron 41794, Extron 22023, Name per DNS/NetBIOS."
        }
    }
}

struct ScanExportSheet: View {
    @EnvironmentObject var m: ScannerModel
    @Environment(\.dismiss) private var dismiss
    @State private var colIP = true
    @State private var colPorts = true
    @State private var colHost = true
    @State private var url: URL?

    var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("Spalten fuer den Export"),
                        footer: Text("CSV mit Semikolon, UTF-8 - oeffnet direkt in Excel. Teilen per Mail, Dateien-App, AirDrop.")) {
                    Toggle("IP-Adresse", isOn: $colIP)
                    Toggle("Ports / Status", isOn: $colPorts)
                    Toggle("Hostname", isOn: $colHost)
                }
                Section {
                    Button("Alle") { colIP = true; colPorts = true; colHost = true }
                    Button("Keine") { colIP = false; colPorts = false; colHost = false }
                }
                Section {
                    if let u = url {
                        ShareLink(item: u) {
                            Label("CSV teilen / sichern", systemImage: "square.and.arrow.up")
                        }
                    } else {
                        Button {
                            url = m.exportCSV(ip: colIP, ports: colPorts, host: colHost)
                        } label: {
                            Label("CSV erstellen", systemImage: "doc.badge.plus")
                        }
                        .disabled(!(colIP || colPorts || colHost))
                    }
                }
            }
            .onChange(of: colIP) { _ in url = nil }
            .onChange(of: colPorts) { _ in url = nil }
            .onChange(of: colHost) { _ in url = nil }
            .navigationTitle("Export-Auswahl")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Schliessen") { dismiss() } }
            }
        }
    }
}

func hideKeyboard() {
    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
}
