// ===========================================================================
//  Scanner.swift - PA Schematic iOS - QR-Codes und Barcodes mit der Kamera lesen
//  Autor: T. Pfeiffer
// ===========================================================================
import SwiftUI
import UIKit
import AVFoundation

final class ScanController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onCode: ((String) -> Void)?
    private let session = AVCaptureSession()
    private var preview: AVCaptureVideoPreviewLayer?
    private var device: AVCaptureDevice?
    private var done = false
    private(set) var ready = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        guard let dev = AVCaptureDevice.default(for: .video),
              let input = try? AVCaptureDeviceInput(device: dev),
              session.canAddInput(input) else { return }
        device = dev
        session.addInput(input)
        let out = AVCaptureMetadataOutput()
        guard session.canAddOutput(out) else { return }
        session.addOutput(out)
        out.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)
        let want: [AVMetadataObject.ObjectType] = [.qr, .code128, .code39, .code93, .ean13, .ean8, .upce, .dataMatrix,
                                                   .pdf417, .itf14, .interleaved2of5, .aztec]
        out.metadataObjectTypes = want.filter { out.availableMetadataObjectTypes.contains($0) }
        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        layer.frame = view.bounds
        view.layer.addSublayer(layer)
        preview = layer
        ready = true
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        preview?.frame = view.bounds
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        let s = session
        DispatchQueue.global(qos: .userInitiated).async {
            if !s.isRunning { s.startRunning() }
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        let s = session
        DispatchQueue.global(qos: .userInitiated).async {
            if s.isRunning { s.stopRunning() }
        }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        if done { return }
        guard let obj = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              let text = obj.stringValue, !text.isEmpty else { return }
        done = true
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        onCode?(text)
    }

    func torch(_ on: Bool) {
        guard let d = device, d.hasTorch else { return }
        do {
            try d.lockForConfiguration()
            d.torchMode = on ? .on : .off
            d.unlockForConfiguration()
        } catch {
        }
    }
}

struct ScanCamera: UIViewControllerRepresentable {
    let onCode: (String) -> Void
    @Binding var light: Bool

    func makeUIViewController(context: Context) -> ScanController {
        let c = ScanController()
        c.onCode = onCode
        return c
    }

    func updateUIViewController(_ uiViewController: ScanController, context: Context) {
        uiViewController.torch(light)
    }
}

/// Ganzer Bildschirm: Kamera, Rahmen, Licht, Abbrechen. onDone(nil) = abgebrochen.
struct ScannerScreen: View {
    let onDone: (String?) -> Void
    @State private var light = false
    @State private var allowed = AVCaptureDevice.authorizationStatus(for: .video) != .denied

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if allowed {
                ScanCamera(onCode: { onDone($0) }, light: $light)
                    .ignoresSafeArea()
                RoundedRectangle(cornerRadius: 18)
                    .stroke(Color.white.opacity(0.9), lineWidth: 3)
                    .frame(width: 270, height: 190)
            } else {
                Text("Die Kamera ist für PA Schematic nicht erlaubt. Einstellungen > PA Schematic > Kamera einschalten.")
                    .multilineTextAlignment(.center)
                    .foregroundColor(.white)
                    .padding(30)
            }
            VStack {
                Text("Code in den Rahmen halten")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 9)
                    .background(Color.black.opacity(0.55))
                    .cornerRadius(12)
                    .padding(.top, 24)
                Spacer()
                HStack(spacing: 14) {
                    Button(light ? "Licht aus" : "Licht an") { light.toggle() }
                        .font(.system(size: 17, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.white.opacity(0.18))
                        .foregroundColor(.white)
                        .cornerRadius(13)
                    Button("Abbrechen") { onDone(nil) }
                        .font(.system(size: 17, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.white.opacity(0.18))
                        .foregroundColor(.white)
                        .cornerRadius(13)
                }
                .padding(.horizontal, 22)
                .padding(.bottom, 26)
            }
        }
        .onAppear {
            if AVCaptureDevice.authorizationStatus(for: .video) == .notDetermined {
                AVCaptureDevice.requestAccess(for: .video) { ok in
                    DispatchQueue.main.async { allowed = ok }
                }
            }
        }
    }
}
