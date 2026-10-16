import Combine
import Foundation
import SwiftUI
@preconcurrency import AVFoundation
import UIKit

// MARK: - Scanner Diagnostics Logger

public enum DiagnosticLogger {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var lastLogTimes: [String: Date] = [:]

    nonisolated public static func log(_ message: String) {
        #if DEBUG
        print("🔍 [BarcodeScanner] \(message)")
        #endif
    }

    nonisolated public static func logAccepted(barcode: String) {
        #if DEBUG
        print("✅ [BarcodeScanner:ACCEPTED] Barcode: \(barcode)")
        #endif
    }

    nonisolated public static func logRejected(barcode: String, reason: String) {
        #if DEBUG
        lock.lock()
        defer { lock.unlock() }
        let key = "\(barcode):\(reason)"
        let now = Date()
        if let last = lastLogTimes[key], now.timeIntervalSince(last) < 2.0 {
            return
        }
        lastLogTimes[key] = now
        print("⛔️ [BarcodeScanner:REJECTED] Barcode: \(barcode) — Reason: \(reason)")
        #endif
    }
}

// MARK: - Thread-Safe Scanner Acceptance Gate

public final class ScannerAcceptanceGate: @unchecked Sendable {
    private let mutex = NSLock()
    nonisolated(unsafe) private var isLocked: Bool = false
    nonisolated(unsafe) private var currentGeneration: Int = 1
    nonisolated public init() {}

    nonisolated public func lock() {
        mutex.lock()
        defer { mutex.unlock() }
        isLocked = true
    }

    nonisolated public func unlock(generation: Int) {
        mutex.lock()
        defer { mutex.unlock() }
        isLocked = false
        currentGeneration = generation
    }

    nonisolated public func tryAccept(barcode: String, generation: Int) -> Bool {
        mutex.lock()
        defer { mutex.unlock() }
        guard generation == currentGeneration else {
            DiagnosticLogger.logRejected(barcode: barcode, reason: "Stale generation (got \(generation), current \(currentGeneration))")
            return false
        }
        guard !isLocked else {
            DiagnosticLogger.logRejected(barcode: barcode, reason: "Acceptance locked")
            return false
        }
        isLocked = true
        DiagnosticLogger.logAccepted(barcode: barcode)
        return true
    }

    nonisolated public var isArmed: Bool {
        mutex.lock()
        defer { mutex.unlock() }
        return !isLocked
    }

    nonisolated public var generation: Int {
        mutex.lock()
        defer { mutex.unlock() }
        return currentGeneration
    }
}

// MARK: - Scanner State Machine

public enum ScannerState: Equatable, Sendable {
    case ready
    case processing(String)
    case detected(barcode: String, productName: String)
    case needsReview(barcode: String, reason: String)
    case error(barcode: String, message: String)
    case paused(reason: String)

    public var isArmed: Bool {
        if case .ready = self { return true }
        return false
    }

    public var statusTitle: String {
        switch self {
        case .ready:
            return "Ready to Scan"
        case .processing:
            return "Looking up product..."
        case .detected(_, let name):
            return "Scanned: \(name)"
        case .needsReview:
            return "Action Required"
        case .error:
            return "Lookup Failed"
        case .paused(let reason):
            return "Paused (\(reason))"
        }
    }
}

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
    @Published public var isArmed: Bool = true
    @Published public var setupError: String? = nil
    
    nonisolated(unsafe) public let session = AVCaptureSession()
    public var captureMetadataOutput: AVCaptureMetadataOutput { metadataOutput }

    public let acceptanceGate = ScannerAcceptanceGate()

    private let sessionQueue = DispatchQueue(label: "mseuf.edu.ph.provision.scanner.session")
    private let metadataQueue = DispatchQueue(label: "mseuf.edu.ph.provision.scanner.metadata")
    private let metadataOutput = AVCaptureMetadataOutput()

    nonisolated(unsafe) private var isSessionConfiguredOnQueue: Bool = false
    private var delegateHolder: AnyObject?
    private var notificationTokens: [NSObjectProtocol] = []

    public var onBarcodeDetected: (@MainActor @Sendable (String, Int) -> Void)?
    public var onSessionInterrupted: (@MainActor @Sendable () -> Void)?
    public var onSessionInterruptionEnded: (@MainActor @Sendable () -> Void)?
    public var onPermissionGranted: (@MainActor @Sendable () -> Void)?
    public init() {
        checkHardwareAndPermission()
        setupInterruptionObservers()
    }

    deinit {
        for token in notificationTokens {
            NotificationCenter.default.removeObserver(token)
        }
    }

    private func setupInterruptionObservers() {
        let center = NotificationCenter.default
        let t1 = center.addObserver(
            forName: AVCaptureSession.wasInterruptedNotification,
            object: session,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                DiagnosticLogger.log("AVCaptureSession was interrupted")
                self.lockAcceptance()
                self.isScanning = false
                self.onSessionInterrupted?()
            }
        }
        let t2 = center.addObserver(
            forName: AVCaptureSession.interruptionEndedNotification,
            object: session,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                DiagnosticLogger.log("AVCaptureSession interruption ended")
                self.onSessionInterruptionEnded?()
            }
        }
        notificationTokens.append(contentsOf: [t1, t2])
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
        self.onPermissionGranted?()
        return true
        #else
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        if status == .authorized {
            self.permission = .authorized
            self.onPermissionGranted?()
            return true
        } else if status == .notDetermined {
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            self.permission = granted ? .authorized : .denied
            if granted {
                DiagnosticLogger.log("Camera access granted by user")
                self.onPermissionGranted?()
            }
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

        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            if !self.isSessionConfiguredOnQueue {
                let success = self.configureSessionSynchronouslyOnQueue()
                guard success else { return }
            }

            if !self.session.isRunning {
                DiagnosticLogger.log("Starting AVCaptureSession")
                self.session.startRunning()
                let running = self.session.isRunning
                Task { @MainActor [weak self] in
                    self?.isScanning = running
                }
            }
        }
    }

    public func stopScanning() {
        guard isCameraAvailable else { return }
        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            if self.session.isRunning {
                DiagnosticLogger.log("Stopping AVCaptureSession")
                self.session.stopRunning()
            }
            Task { @MainActor [weak self] in
                self?.isScanning = false
            }
        }
    }

    public func rearm(generation: Int = 1) {
        acceptanceGate.unlock(generation: generation)
        DiagnosticLogger.log("BarcodeScannerManager rearmed (generation=\(generation))")
        self.isArmed = true
    }

    public func lockAcceptance() {
        acceptanceGate.lock()
        DiagnosticLogger.log("BarcodeScannerManager acceptance locked")
        self.isArmed = false
    }

    private nonisolated func configureSessionSynchronouslyOnQueue() -> Bool {
        #if targetEnvironment(simulator)
        return true
        #else
        guard !isSessionConfiguredOnQueue else { return true }
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else {
            Task { @MainActor [weak self] in
                self?.setupError = "Rear camera not available on this device."
            }
            return false
        }

        do {
            DiagnosticLogger.log("Configuring AVCaptureSession on sessionQueue...")
            session.beginConfiguration()
            session.sessionPreset = .high

            let input = try AVCaptureDeviceInput(device: device)
            if session.canAddInput(input) {
                session.addInput(input)
            } else {
                session.commitConfiguration()
                Task { @MainActor [weak self] in
                    self?.setupError = "Cannot attach camera input to session."
                }
                return false
            }

            if session.canAddOutput(metadataOutput) {
                session.addOutput(metadataOutput)

                let delegate = BarcodeMetadataDelegate(gate: acceptanceGate) { [weak self] rawCode, gen in
                    Task { @MainActor [weak self] in
                        self?.isArmed = false
                        self?.lastDetectedBarcode = rawCode
                        self?.onBarcodeDetected?(rawCode, gen)
                    }
                }
                self.delegateHolder = delegate
                metadataOutput.setMetadataObjectsDelegate(delegate, queue: metadataQueue)

                let targetTypes: [AVMetadataObject.ObjectType] = [
                    .ean13,
                    .ean8,
                    .upce,
                    .code128,
                    .code39
                ]
                let available = metadataOutput.availableMetadataObjectTypes
                let supported = targetTypes.filter { available.contains($0) }
                metadataOutput.metadataObjectTypes = supported
                DiagnosticLogger.log("Configured metadataObjectTypes: \(supported.map { $0.rawValue })")
            }

            session.commitConfiguration()
            self.isSessionConfiguredOnQueue = true
            return true
        } catch {
            session.commitConfiguration()
            Task { @MainActor [weak self] in
                self?.setupError = "Camera setup failed: \(error.localizedDescription)"
            }
            return false
        }
        #endif
    }
}

// MARK: - AVCaptureMetadataOutputObjectsDelegate

private final class BarcodeMetadataDelegate: NSObject, AVCaptureMetadataOutputObjectsDelegate, @unchecked Sendable {
    private let gate: ScannerAcceptanceGate
    private let onCodeAccepted: @Sendable (String, Int) -> Void

    init(gate: ScannerAcceptanceGate, onCodeAccepted: @escaping @Sendable (String, Int) -> Void) {
        self.gate = gate
        self.onCodeAccepted = onCodeAccepted
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
        let gen = gate.generation
        if gate.tryAccept(barcode: stringValue, generation: gen) {
            onCodeAccepted(stringValue, gen)
        }
    }
}

// MARK: - Camera Preview Representable

public struct CameraPreviewRepresentable: UIViewRepresentable {
    public let session: AVCaptureSession
    public let metadataOutput: AVCaptureMetadataOutput?
    public let visualTargetRect: CGRect
    
    public init(
        session: AVCaptureSession,
        metadataOutput: AVCaptureMetadataOutput? = nil,
        visualTargetRect: CGRect = .zero
    ) {
        self.session = session
        self.metadataOutput = metadataOutput
        self.visualTargetRect = visualTargetRect
    }
    
    public func makeUIView(context: Context) -> CameraPreviewUIView {
        let view = CameraPreviewUIView()
        view.previewLayer.session = session
        view.metadataOutput = metadataOutput
        view.targetVisualRect = visualTargetRect
        return view
    }
    
    public func updateUIView(_ uiView: CameraPreviewUIView, context: Context) {
        if uiView.previewLayer.session != session {
            uiView.previewLayer.session = session
        }
        uiView.metadataOutput = metadataOutput
        uiView.targetVisualRect = visualTargetRect
    }
}

public final class CameraPreviewUIView: UIView {
    public override class var layerClass: AnyClass {
        AVCaptureVideoPreviewLayer.self
    }
    
    public var previewLayer: AVCaptureVideoPreviewLayer {
        layer as! AVCaptureVideoPreviewLayer
    }
    
    public var targetVisualRect: CGRect = .zero {
        didSet {
            updateRectOfInterest()
        }
    }
    
    public weak var metadataOutput: AVCaptureMetadataOutput? {
        didSet {
            updateRectOfInterest()
        }
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

    public override func layoutSubviews() {
        super.layoutSubviews()
        updateRectOfInterest()
    }
    
    public func updateRectOfInterest() {
        guard let output = metadataOutput,
              previewLayer.bounds.width > 0,
              previewLayer.bounds.height > 0,
              targetVisualRect.width > 0,
              targetVisualRect.height > 0 else {
            return
        }
        
        let converted = previewLayer.metadataOutputRectConverted(fromLayerRect: targetVisualRect)
        if converted.origin.x >= 0 && converted.origin.y >= 0 &&
           converted.width > 0 && converted.height > 0 &&
           (converted.origin.x + converted.width) <= 1.05 &&
           (converted.origin.y + converted.height) <= 1.05 {
            output.rectOfInterest = converted
            DiagnosticLogger.log("Updated metadataOutput.rectOfInterest to \(converted) from visualRect: \(targetVisualRect)")
        }
    }
}

// MARK: - Barcode Scanner View (SwiftUI Wrapper)

public struct BarcodeScannerView: View {
    @ObservedObject public var manager: BarcodeScannerManager
    public let onBarcodeDetected: (@MainActor @Sendable (String, Int) -> Void)?
    
    public init(
        manager: BarcodeScannerManager,
        onBarcodeDetected: (@MainActor @Sendable (String, Int) -> Void)? = nil
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
                    GeometryReader { geo in
                        let visualWidth: CGFloat = min(260, geo.size.width - 40)
                        let visualHeight: CGFloat = min(140, geo.size.height - 20)
                        let targetRect = CGRect(
                            x: max(0, (geo.size.width - visualWidth) / 2),
                            y: max(0, (geo.size.height - visualHeight) / 2),
                            width: visualWidth,
                            height: visualHeight
                        )
                        ZStack {
                            CameraPreviewRepresentable(
                                session: manager.session,
                                metadataOutput: manager.captureMetadataOutput,
                                visualTargetRect: targetRect
                            )
                            .background(Color.black)

                            VisualReticleGuide(rect: targetRect)
                                .allowsHitTesting(false)
                        }
                    }
                case .notDetermined:
                    permissionRequestingView
                case .denied:
                    permissionDeniedView
                }
            }
            
            if let err = manager.setupError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 24))
                        .foregroundStyle(ProvisionTheme.redAlert)
                    Text("Camera Setup Error")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(.white)
                    Text(err)
                        .font(.system(size: 11))
                        .foregroundStyle(Color.white.opacity(0.8))
                        .multilineTextAlignment(.center)
                }
                .padding()
                .background(Color.black.opacity(0.85))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
        .onAppear {
            // Only override manager callback if caller supplied an explicit custom handler
            if let customCallback = onBarcodeDetected {
                manager.onBarcodeDetected = customCallback
            }
            if manager.isCameraAvailable && manager.permission == .notDetermined {
                Task {
                    _ = await manager.requestPermission()
                }
            }
        }
    }

    public struct VisualReticleGuide: View {
        public let rect: CGRect
        public let bracketLength: CGFloat = 20
        public let bracketWidth: CGFloat = 3
        public let color: Color = ProvisionTheme.heroCard

        public init(rect: CGRect) {
            self.rect = rect
        }

        public var body: some View {
            Canvas { context, _ in
                // Top Left
                var tl = Path()
                tl.move(to: CGPoint(x: rect.minX, y: rect.minY + bracketLength))
                tl.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
                tl.addLine(to: CGPoint(x: rect.minX + bracketLength, y: rect.minY))
                context.stroke(tl, with: .color(color), lineWidth: bracketWidth)

                // Top Right
                var tr = Path()
                tr.move(to: CGPoint(x: rect.maxX - bracketLength, y: rect.minY))
                tr.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
                tr.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + bracketLength))
                context.stroke(tr, with: .color(color), lineWidth: bracketWidth)

                // Bottom Left
                var bl = Path()
                bl.move(to: CGPoint(x: rect.minX, y: rect.maxY - bracketLength))
                bl.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
                bl.addLine(to: CGPoint(x: rect.minX + bracketLength, y: rect.maxY))
                context.stroke(bl, with: .color(color), lineWidth: bracketWidth)

                // Bottom Right
                var br = Path()
                br.move(to: CGPoint(x: rect.maxX - bracketLength, y: rect.maxY))
                br.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
                br.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - bracketLength))
                context.stroke(br, with: .color(color), lineWidth: bracketWidth)
            }
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
