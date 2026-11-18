// ===========================================================================
//  HandbookView.swift - PA AV Toolbox iOS v1.0.1
//  Autor: T. Pfeiffer
//  Zeigt das mitgelieferte Handbuch (PDF im App-Paket) mit PDFKit an:
//  Blaettern, Zoomen, Inhaltsverzeichnis-Links, Teilen/Sichern.
// ===========================================================================
import SwiftUI
import PDFKit

enum Handbook {
    static let resource = "PA_AV_Toolbox_iOS_Handbuch"
    static var url: URL? {
        return Bundle.main.url(forResource: resource, withExtension: "pdf")
    }
}

struct PDFKitView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displayDirection = .vertical
        v.backgroundColor = UIColor.systemGroupedBackground
        v.document = PDFDocument(url: url)
        return v
    }

    func updateUIView(_ uiView: PDFView, context: Context) {}
}

struct HandbookView: View {
    var body: some View {
        Group {
            if let u = Handbook.url {
                PDFKitView(url: u)
                    .ignoresSafeArea(edges: .bottom)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "book.closed").font(.largeTitle).foregroundColor(.secondary)
                    Text("Handbuch nicht im App-Paket gefunden").foregroundColor(.secondary)
                }
            }
        }
        .navigationTitle("Handbuch")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                if let u = Handbook.url {
                    ShareLink(item: u) { Image(systemName: "square.and.arrow.up") }
                }
            }
        }
    }
}
