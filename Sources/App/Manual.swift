// ===========================================================================
//  Manual.swift - Studio Control iOS - Handbuch in der App
//  Autor: T. Pfeiffer
//  v1.2.1 - Die Handbuecher (PDF) liegen in der App und lassen sich unter
//           Info & Update ohne Internet oeffnen, durchblaettern und teilen.
// ===========================================================================
import SwiftUI
import PDFKit

struct ManualEntry: Identifiable, Hashable {
    let id: String          // Dateiname ohne .pdf (liegt im App-Paket)
    let title: String
    let subtitle: String
    let symbol: String

    var url: URL? { Bundle.main.url(forResource: id, withExtension: "pdf") }
}

let manualEntries: [ManualEntry] = [
    ManualEntry(id: "Handbuch_Steckdosen", title: "Handbuch Steckdosen",
                subtitle: "Stand v1.2.0 - Tapo, zwei Konten, Diagnose", symbol: "powerplug"),
    ManualEntry(id: "Handbuch_Gesamt", title: "Handbuch gesamt",
                subtitle: "Stand v1.1.1 - alle Seiten der App", symbol: "book")
]

struct PDFKitView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displayDirection = .vertical
        v.backgroundColor = UIColor.black
        v.document = PDFDocument(url: url)
        return v
    }

    func updateUIView(_ uiView: PDFView, context: Context) {
        if uiView.document?.documentURL != url {
            uiView.document = PDFDocument(url: url)
        }
    }
}

struct ManualView: View {
    let entry: ManualEntry

    var body: some View {
        Group {
            if let u = entry.url {
                PDFKitView(url: u)
                    .ignoresSafeArea(edges: .bottom)
                    .toolbar {
                        ToolbarItem(placement: .primaryAction) {
                            ShareLink(item: u) {
                                Image(systemName: "square.and.arrow.up")
                            }
                        }
                    }
            } else {
                Text("Das Handbuch fehlt in dieser App-Version.")
                    .foregroundStyle(.secondary)
                    .padding()
            }
        }
        .navigationTitle(entry.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Abschnitt "Handbuch" fuer die Seite Info & Update
struct ManualSection: View {
    var body: some View {
        Section {
            ForEach(manualEntries) { e in
                NavigationLink {
                    ManualView(entry: e)
                } label: {
                    HStack(spacing: 12) {
                        Image(systemName: e.symbol)
                            .foregroundStyle(Color(hex: 0x0A84FF))
                            .frame(width: 26)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(e.title)
                            Text(e.subtitle).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        } header: {
            Text("Handbuch")
        } footer: {
            Text("Liegt in der App, kein Internet nötig. Über das Teilen-Symbol in Dateien sichern oder drucken.")
        }
    }
}
