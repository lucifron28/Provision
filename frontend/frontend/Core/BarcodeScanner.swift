import Combine
import Foundation
import SwiftUI
@preconcurrency import AVFoundation
import UIKit

// MARK: - Camera Permission States

public enum CameraPermission: Sendable {
    case notDetermined
    case authorized
    case denied
}

// MARK: - Barcode Scanner Manager

@MainActor
public final class BarcodeScannerManager: ObservableObject {
    @Published public var permission: CameraPermission = .notDetermined
    @Published public var isCameraAvailable: Bool = true
    @Published public var isScanning: Bool = false
    @Published public var lastDetectedBarcode: String = ""
    
    public let session = AVCaptureSession()
    
    private let sessionQueue = DispatchQueue(label: "mseuf.edu.ph.provision.scanner.session")
    private let metadataQueue = DispatchQueue(label: "mseuf.edu.ph.provision.scanner.metadata")
    private let metadataOutput = AVCaptureMetadataOutput()
    
    private var isConfigured: Bool = false
    private var delegateHolder: AnyObject?
    
    // Throttling / Debouncing parameters
    private var lastScannedCode: String = ""
    private var lastScannedTime: Date = .distantPast
    private let sameBarcodeDebounceInterval: TimeInterval = 1.5
    private let interBarcodeThrottleInterval: TimeInterval = 0.4
    
    public var onBarcodeDetected: (@MainActor @Sendable (String) -> Void)?
    
    public init() {
        checkHardwareAndPermission()
    }
    
    public func checkHardwareAndPermission() {
        #if targetEnvironment(simulator)
        self.isCameraAvailable = false
        self.permission = .authorized
        #else
        if AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) == nil {
            self.isCameraAvailable = false
        } else {
            self.isCameraAvailable = true
        }
        
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            self.permission = .authorized
        case .notDetermined:
            self.permission = .notDetermined
        case .denied, .restricted:
            self.permission = .denied
        @unknown default:
            self.permission = .denied
        }
        #endif
    }
    
    public func requestPermission() async -> Bool {
        #if targetEnvironment(simulator)
        self.permission = .authorized
        return true
        #else
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        if status == .authorized {
            self.permission = .authorized
            return true
        } else if status == .notDetermined {
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            self.permission = granted ? .authorized : .denied
            return granted
        } else {
            self.permission = .denied
            return false
        }
        #endif
    }
    
    public func startScanning() {
        guard isCameraAvailable else { return }
        
        checkHardwareAndPermission()
        guard permission == .authorized else { return }
        
        let session = self.session
        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            self.configureSessionIfNeeded()
            if !session.isRunning {
                session.startRunning()
                Task { @MainActor [weak self] in
                    self?.isScanning = true
                }
            }
        }
    }
    
    public func stopScanning() {
        guard isCameraAvailable else { return }
        let session = self.session
        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            if session.isRunning {
                session.stopRunning()
                Task { @MainActor [weak self] in
                    self?.isScanning = false
                }
            }
        }
    }
    
    private nonisolated func configureSessionIfNeeded() {
        #if !targetEnvironment(simulator)
        Task { @MainActor in
            guard !self.isConfigured else { return }
            
            self.sessionQueue.async { [weak self] in
                guard let self = self else { return }
                guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else {
                    return
                }
                
                do {
                    self.session.beginConfiguration()
                    self.session.sessionPreset = .high
                    
                    let input = try AVCaptureDeviceInput(device: device)
                    if self.session.canAddInput(input) {
                        self.session.addInput(input)
                    }
                    
                    if self.session.canAddOutput(self.metadataOutput) {
                        self.session.addOutput(self.metadataOutput)
                        
                        let delegate = BarcodeMetadataDelegate { [weak self] code in
                            Task { @MainActor [weak self] in
                                self?.handleRawBarcodeDetected(code)
                            }
                        }
                        
                        Task { @MainActor [weak self] in
                            self?.delegateHolder = delegate
                        }
                        
                        self.metadataOutput.setMetadataObjectsDelegate(delegate, queue: self.metadataQueue)
                        
                        // Minimum supported grocery barcode types: EAN-13, EAN-8, UPC-E, Code 128
                        let targetTypes: [AVMetadataObject.ObjectType] = [
                            .ean13,
                            .ean8,
                            .upce,
                            .code128,
                            .code39,
                            .qr
                        ]
                        let available = self.metadataOutput.availableMetadataObjectTypes
                        let supported = targetTypes.filter { available.contains($0) }
                        self.metadataOutput.metadataObjectTypes = supported
                    }
                    
                    self.session.commitConfiguration()
                    
                    Task { @MainActor [weak self] in
                        self?.isConfigured = true
                    }
                } catch {
                    // Camera configuration failed
                }
            }
        }
        #endif
    }
    
    private func handleRawBarcodeDetected(_ code: String) {
        let now = Date()
        
        // Throttling / Debouncing
        if code == lastScannedCode && now.timeIntervalSince(lastScannedTime) < sameBarcodeDebounceInterval {
            return // Same barcode repeated within debounce window
        } else if now.timeIntervalSince(lastScannedTime) < interBarcodeThrottleInterval {
            return // Rapid multi-code throttle
        }
        
        lastScannedCode = code
        lastScannedTime = now
        lastDetectedBarcode = code
        
        // Trigger subtle haptic feedback
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.impactOccurred()
        
        onBarcodeDetected?(code)
    }
}

// MARK: - AVCaptureMetadataOutputObjectsDelegate

private final class BarcodeMetadataDelegate: NSObject, AVCaptureMetadataOutputObjectsDelegate, @unchecked Sendable {
    private let onCodeDetected: @Sendable (String) -> Void
    
    init(onCodeDetected: @escaping @Sendable (String) -> Void) {
        self.onCodeDetected = onCodeDetected
    }
    
    nonisolated func metadataOutput(
        _ output: AVCaptureMetadataOutput,
        didOutput metadataObjects: [AVMetadataObject],
        from connection: AVCaptureConnection
    ) {
        guard let readable = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              let stringValue = readable.stringValue,
              !stringValue.isEmpty else {
            return
        }
        onCodeDetected(stringValue)
    }
}

// MARK: - Camera Preview Representable

public struct CameraPreviewRepresentable: UIViewRepresentable {
    public let session: AVCaptureSession
    
    public init(session: AVCaptureSession) {
        self.session = session
    }
    
    public func makeUIView(context: Context) -> CameraPreviewUIView {
        let view = CameraPreviewUIView()
        view.previewLayer.session = session
        return view
    }
    
    public func updateUIView(_ uiView: CameraPreviewUIView, context: Context) {
        if uiView.previewLayer.session != session {
            uiView.previewLayer.session = session
        }
    }
}

public final class CameraPreviewUIView: UIView {
    public override class var layerClass: AnyClass {
        AVCaptureVideoPreviewLayer.self
    }
    
    public var previewLayer: AVCaptureVideoPreviewLayer {
        layer as! AVCaptureVideoPreviewLayer
    }
    
    public override init(frame: CGRect) {
        super.init(frame: frame)
        previewLayer.videoGravity = .resizeAspectFill
        backgroundColor = .black
    }
    
    required init?(coder: NSCoder) {
        super.init(coder: coder)
        previewLayer.videoGravity = .resizeAspectFill
        backgroundColor = .black
    }
}

// MARK: - Barcode Scanner View (SwiftUI Wrapper)

public struct BarcodeScannerView: View {
    @ObservedObject public var manager: BarcodeScannerManager
    public let onBarcodeDetected: @MainActor @Sendable (String) -> Void
    
    public init(
        manager: BarcodeScannerManager,
        onBarcodeDetected: @escaping @MainActor @Sendable (String) -> Void
    ) {
        self.manager = manager
        self.onBarcodeDetected = onBarcodeDetected
    }
    
    public var body: some View {
        ZStack {
            if !manager.isCameraAvailable {
                // Simulator or devices without camera
                simulatorPlaceholderView
            } else {
                switch manager.permission {
                case .authorized:
                    CameraPreviewRepresentable(session: manager.session)
                        .background(Color.black)
                case .notDetermined:
                    permissionRequestingView
                case .denied:
                    permissionDeniedView
                }
            }
        }
        .onAppear {
            manager.onBarcodeDetected = onBarcodeDetected
            if manager.isCameraAvailable {
                if manager.permission == .notDetermined {
                    Task {
                        _ = await manager.requestPermission()
                        if manager.permission == .authorized {
                            manager.startScanning()
                        }
                    }
                } else if manager.permission == .authorized {
                    manager.startScanning()
                }
            }
        }
        .onDisappear {
            manager.stopScanning()
        }
    }
    
    private var simulatorPlaceholderView: some View {
        ZStack {
            Color(red: 0.10, green: 0.12, blue: 0.11)
            VStack(spacing: 8) {
                Image(systemName: "camera.viewfinder")
                    .font(.system(size: 36))
                    .foregroundStyle(ProvisionTheme.heroCard.opacity(0.8))
                Text("Camera Unavailable in Simulator")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                Text("Barcode capture active on physical iOS devices.")
                    .font(.system(size: 11))
                    .foregroundStyle(Color.white.opacity(0.7))
            }
            .padding()
        }
    }
    
    private var permissionRequestingView: some View {
        ZStack {
            Color(red: 0.10, green: 0.12, blue: 0.11)
            VStack(spacing: 10) {
                ProgressView()
                    .tint(.white)
                Text("Requesting camera access...")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(.white)
            }
        }
    }
    
    private var permissionDeniedView: some View {
        ZStack {
            Color(red: 0.15, green: 0.12, blue: 0.12)
            VStack(spacing: 8) {
                Image(systemName: "video.slash.fill")
                    .font(.system(size: 32))
                    .foregroundStyle(ProvisionTheme.redAlert)
                Text("Camera Access Denied")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(.white)
                Text("Please enable camera permission in Settings to scan barcodes.")
                    .font(.system(size: 11))
                    .foregroundStyle(Color.white.opacity(0.8))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 16)
                
                Button("Open Settings") {
                    if let url = URL(string: UIApplication.openSettingsURLString) {
                        UIApplication.shared.open(url)
                    }
                }
                .font(.system(size: 12, weight: .bold))
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(ProvisionTheme.heroCard)
                .foregroundStyle(ProvisionTheme.background)
                .clipShape(Capsule())
                .padding(.top, 4)
            }
            .padding()
        }
    }
}
