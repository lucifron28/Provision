import CryptoKit

import Foundation
import SwiftUI
import Combine

public struct ScannedIntakeItem: Identifiable, Hashable, Codable, Sendable {
    public let id: UUID
    public var name: String
    public var brand: String?
    public var barcode: String
    public var quantity: Double
    public var unit: String
    public var expirationDate: Date?
    public var status: IntakeStatus
    public var productId: Int?
    public var storageLocationId: Int?
    public var unitPrice: Double?
    public var isConfirmed: Bool
    public var conflictingReceiptQuantity: Double? = nil

    public enum IntakeStatus: String, Codable, Sendable {
        case autoLogged = "Auto-logged"
        case recognized = "Recognized"
        case needsReview = "Needs Review"
        case confirmed = "Confirmed"
    }

    public init(
        id: UUID = UUID(),
        name: String,
        brand: String? = nil,
        barcode: String,
        quantity: Double = 1.0,
        unit: String = "pcs",
        expirationDate: Date? = nil,
        status: IntakeStatus = .recognized,
        productId: Int? = nil,
        storageLocationId: Int? = nil,
        unitPrice: Double? = nil,
        isConfirmed: Bool = false,
        conflictingReceiptQuantity: Double? = nil
    ) {
        self.id = id
        self.name = name
        self.brand = brand
        self.barcode = barcode
        self.quantity = quantity
        self.unit = unit
        self.expirationDate = expirationDate
        self.status = status
        self.productId = productId
        self.storageLocationId = storageLocationId
        self.unitPrice = unitPrice
        self.isConfirmed = isConfirmed
        self.conflictingReceiptQuantity = conflictingReceiptQuantity
    }
}

// MARK: - Coordinated Suspension Ownership

public enum SuspensionReason: String, CaseIterable, Hashable, Sendable {
    case receiptMode = "Receipt mode active"
    case receiptCamera = "Receipt camera sheet open"
    case receiptOCR = "Processing receipt OCR"
    case quickAddSheet = "Product resolution sheet open"
    case manualEntrySheet = "Manual entry sheet open"
    case itemReviewSheet = "Intake item review sheet open"
    case expirationSheet = "Expiration date scanner open"
    case priceEditing = "Price editing active"
    case background = "App in background or inactive"
    case navigatedAway = "Navigated away from Scan tab"
    case committing = "Committing grocery intake"
    case cameraInterrupted = "Camera capture interrupted"
    case userPaused = "User explicitly paused"
    case pendingCommitRecovery = "Recovering a previous intake commit"
}

private struct PendingIntakeCommit: Codable {
    let sessionID: Int?
    let fingerprint: String
    let storeName: String
    let intakeItems: [ScannedIntakeItem]
    let requestItems: [SessionItemCreate]
    let creationRequest: GrocerySessionCreate?

    func attaching(sessionID: Int) -> PendingIntakeCommit {
        PendingIntakeCommit(
            sessionID: sessionID,
            fingerprint: fingerprint,
            storeName: storeName,
            intakeItems: intakeItems,
            requestItems: requestItems,
            creationRequest: creationRequest
        )
    }
}

private struct IntakeFingerprintPayload: Codable {
    let storeName: String
    let items: [ScannedIntakeItem]
}

private let pendingIntakeCommitStorageKey = "provision.pending-intake-commit.v1"

@MainActor
public class ScanViewModel: ObservableObject {
    @Published public var storeName: String
    @Published public var scannedItems: [ScannedIntakeItem] = []
    @Published public var availableLocations: [StorageLocation] = []
    @Published public var isScanning: Bool = true
    @Published public var scannerState: ScannerState = .ready
    @Published public var isCommitting: Bool = false
    @Published public var toastMessage: String? = nil
    @Published public var errorMessage: String? = nil
    @Published public var lastScannedBarcode: String = ""
    @Published public var unresolvedBarcode: String? = nil
    @Published public var resolvingItemId: UUID? = nil
    @Published public var availableCatalog: [Product] = []
    @Published public var showingQuickAddSheet: Bool = false
    @Published public var isResolvingBarcode: Bool = false
    @Published public var isProcessingReceipt: Bool = false
    @Published public var showingReceiptCamera: Bool = false
    @Published public private(set) var currentScanGeneration: Int = 1
    @Published public private(set) var activeSuspensions: Set<SuspensionReason> = []
    @Published public private(set) var lastCapturedReceiptLines: [String] = []

    public var isSuspended: Bool { !activeSuspensions.isEmpty }
    public var currentSuspensionReason: String? { activeSuspensions.first?.rawValue }
    public var suspensionReason: String? { currentSuspensionReason }
    public var hasPendingCommitRecovery: Bool { pendingIntakeCommit != nil || pendingCommitRecoveryError != nil }
    public var isIntakeMutationLocked: Bool { isCommitting || hasPendingCommitRecovery }

    @Published public private(set) var pendingDraftSessionId: Int? = nil
    @Published public private(set) var pendingCommitRecoveryError: String? = nil
    private var pendingIntakeCommit: PendingIntakeCommit? = nil
    private let pendingCommitDefaults: UserDefaults
    private var postCommitDeferredItems: [ScannedIntakeItem] = []
    public var isPreview: Bool
    public let scannerManager: BarcodeScannerManager
    private let client: APIClient
    private var inFlightResolutions: Set<String> = []
    private var toastDismissTask: Task<Void, Never>? = nil

    public func showToast(_ message: String) {
        self.toastMessage = message
        toastDismissTask?.cancel()
        toastDismissTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 3_500_000_000)
            if !Task.isCancelled && self.toastMessage == message {
                self.toastMessage = nil
            }
        }
    }
    public init(
        client: APIClient = .shared,
        isPreview: Bool = false,
        pendingCommitDefaults: UserDefaults = .standard
    ) {
        self.client = client
        self.isPreview = isPreview
        self.pendingCommitDefaults = pendingCommitDefaults
        self.storeName = isPreview ? "SM Supermarket Megamall" : ""
        self.scannerManager = BarcodeScannerManager()
        if !isPreview {
            self.activeSuspensions.insert(.navigatedAway)
            if let data = pendingCommitDefaults.data(forKey: pendingIntakeCommitStorageKey) {
                do {
                    let pending = try JSONDecoder().decode(PendingIntakeCommit.self, from: data)
                    self.pendingIntakeCommit = pending
                    self.pendingDraftSessionId = pending.sessionID
                    self.storeName = pending.storeName
                    self.scannedItems = pending.intakeItems
                    self.activeSuspensions.insert(.pendingCommitRecovery)
                    self.errorMessage = "A previous intake submission needs reconciliation. Retry before editing or starting another intake."
                } catch {
                    self.pendingCommitRecoveryError = "Saved intake recovery data could not be read. No new intake was submitted; preserve this app data and contact support before retrying."
                    self.activeSuspensions.insert(.pendingCommitRecovery)
                    self.errorMessage = self.pendingCommitRecoveryError
                }
            }
        }
        if isPreview {
            scannerManager.isCameraAvailable = false
            setupSampleIntake()
        }

        self.scannerManager.onBarcodeDetected = { [weak self] code, gen in
            self?.onBarcodeScanned(code, generation: gen)
        }
        self.scannerManager.onSessionInterrupted = { [weak self] in
            self?.suspendScanning(for: .cameraInterrupted)
        }
        self.scannerManager.onSessionInterruptionEnded = { [weak self] in
            self?.resumeScanning(releasing: .cameraInterrupted)
        }
        self.scannerManager.onPermissionGranted = { [weak self] in
            guard let self = self else { return }
            DiagnosticLogger.log("Camera permission granted: starting capture if active")
            self.startScanningIfAvailable()
        }
    }

    public func loadLocations() async {
        do {
            let locations = try await client.fetchLocations()
            self.availableLocations = locations
        } catch {
            self.errorMessage = "Failed to load locations: \(error.localizedDescription)"
        }
        await loadCatalog()
    }

    public func loadCatalog() async {
        if isPreview {
            self.availableCatalog = PreviewData.products
            return
        }
        do {
            self.availableCatalog = try await client.fetchProducts(limit: 500)
        } catch {
            // Keep existing or empty
        }
    }

    public var canRearm: Bool {
        guard !isIntakeMutationLocked else { return false }
        guard !isResolvingBarcode else { return false }
        guard !isProcessingReceipt else { return false }
        guard !showingQuickAddSheet else { return false }
        guard !isSuspended else { return false }
        switch scannerState {
        case .ready:
            return false // Already armed and waiting
        case .processing:
            return false // Lookup in flight
        case .detected, .needsReview, .error, .paused:
            return true
        }
    }

    @discardableResult
    public func rearmScanner() -> Bool {
        guard canRearm else {
            #if DEBUG
            DiagnosticLogger.log("rearmScanner() ignored: canRearm is false (state=\(scannerState), isCommitting=\(isCommitting), isResolving=\(isResolvingBarcode), isSuspended=\(isSuspended))")
            #endif
            return false
        }
        currentScanGeneration += 1
        self.scannerState = .ready
        self.lastScannedBarcode = ""
        self.scannerManager.rearm(generation: currentScanGeneration)
        #if DEBUG
        DiagnosticLogger.log("Scanner rearmed to .ready (generation=\(currentScanGeneration))")
        #endif
        return true
    }

    public func suspendScanning(for reason: SuspensionReason) {
        activeSuspensions.insert(reason)
        scannerManager.lockAcceptance()
        scannerManager.stopScanning()
        #if DEBUG
        DiagnosticLogger.log("Scanning suspended for [\(reason.rawValue)]. Active suspensions count: \(activeSuspensions.count) (state=\(scannerState))")
        #endif
    }

    public func resumeScanning(releasing reason: SuspensionReason) {
        if activeSuspensions.remove(reason) != nil {
            #if DEBUG
            DiagnosticLogger.log("Released suspension [\(reason.rawValue)]. Remaining suspensions count: \(activeSuspensions.count)")
            #endif

            if reason == .userPaused, case .paused = scannerState {
                currentScanGeneration += 1
                scannerState = .ready
            }
        }
        startScanningIfAvailable()
    }

    public func startScanningIfAvailable() {
        guard activeSuspensions.isEmpty,
              !isCommitting,
              !isProcessingReceipt,
              !showingReceiptCamera,
              !hasPendingCommitRecovery,
              !isPreview else {
            return
        }

        scannerManager.startScanning()
        if case .ready = scannerState {
            scannerManager.rearm(generation: currentScanGeneration)
        } else {
            scannerManager.lockAcceptance()
        }
    }

    public func pauseScanning(reason: String = "User paused") {
        suspendScanning(for: .userPaused)
        self.scannerState = .paused(reason: reason)
        #if DEBUG
        DiagnosticLogger.log("Scanner paused by user: \(reason)")
        #endif
    }

    public func retryBarcodeLookup() {
        guard case .error(let barcode, _) = scannerState else { return }
        guard !isResolvingBarcode && !isIntakeMutationLocked else { return }
        self.errorMessage = nil
        self.scannerState = .processing(barcode)
        let gen = currentScanGeneration
        Task {
            await resolveScannedBarcode(barcode, generation: gen)
        }
    }

    public func simulateBarcodeDetection(_ barcode: String, generation: Int? = nil) {
        onBarcodeScanned(barcode, generation: generation ?? currentScanGeneration)
    }

    public func startScanning() {
        startScanningIfAvailable()
    }

    public func stopScanning() {
        suspendScanning(for: .userPaused)
    }

    public func onBarcodeScanned(_ barcode: String, generation: Int) {
        let trimmed = barcode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        guard !isSuspended else {
            #if DEBUG
            DiagnosticLogger.logRejected(barcode: trimmed, reason: "Scanning is suspended (\(currentSuspensionReason ?? "overlay active"))")
            #endif
            return
        }
        guard !isIntakeMutationLocked else {
            #if DEBUG
            DiagnosticLogger.logRejected(barcode: trimmed, reason: "An intake submission is being reconciled")
            #endif
            return
        }

        // Phase 1 Requirement: Controlled single-scan acceptance state machine
        guard scannerState.isArmed else {
            #if DEBUG
            DiagnosticLogger.logRejected(barcode: trimmed, reason: "ScannerState is \(scannerState) (not armed/ready)")
            #endif
            return
        }

        guard generation == currentScanGeneration else {
            #if DEBUG
            DiagnosticLogger.logRejected(barcode: trimmed, reason: "Stale generation (got \(generation), expected \(currentScanGeneration))")
            #endif
            return
        }

        self.lastScannedBarcode = trimmed
        self.scannerState = .processing(trimmed)
        self.scannerManager.lockAcceptance()
        HapticFeedback.medium()

        Task {
            await resolveScannedBarcode(trimmed, generation: generation)
        }
    }

    public func resolveScannedBarcode(_ barcode: String, generation: Int) async {
        guard !isIntakeMutationLocked else { return }
        guard generation == self.currentScanGeneration else {
            #if DEBUG
            DiagnosticLogger.log("Discarding resolution for \(barcode): generation changed (active=\(self.currentScanGeneration), request=\(generation))")
            #endif
            return
        }
        // Check if barcode is already being resolved
        if inFlightResolutions.contains(barcode) {
            return
        }
        inFlightResolutions.insert(barcode)
        defer {
            inFlightResolutions.remove(barcode)
        }

        isResolvingBarcode = true
        defer {
            isResolvingBarcode = false
        }

        // 1. Check if already scanned in current session -> increment quantity
        if let idx = scannedItems.firstIndex(where: { $0.barcode == barcode }) {
            scannedItems[idx].quantity += 1.0
            invalidateConfirmation(at: idx)
            self.scannerState = .detected(barcode: barcode, productName: scannedItems[idx].name)
            showToast("Incremented \(scannedItems[idx].name) (\(Int(scannedItems[idx].quantity)))")
            return
        }

        // 2. Query catalog via API or PreviewData
        var resolvedProduct: Product? = nil
        var lookupErrorText: String? = nil

        if isPreview {
            resolvedProduct = PreviewData.products.first(where: { $0.barcode == barcode })
        } else {
            do {
                resolvedProduct = try await client.fetchProduct(barcode: barcode)
            } catch {
                if case APIError.unauthorized = error {
                    lookupErrorText = "Session expired or authentication required. Please log in again."
                } else if case APIError.networkError = error {
                    lookupErrorText = "Network connection failed. Unable to verify barcode \(barcode)."
                } else if error is URLError {
                    lookupErrorText = "Network connection failed. Unable to verify barcode \(barcode)."
                } else {
                    lookupErrorText = "Lookup failed for barcode \(barcode): \(error.localizedDescription)"
                }
            }
        }

        guard generation == self.currentScanGeneration else { return }

        // Defect 4 Fix: Prevent delayed lookups from modifying queue during an active commit
        if isCommitting || activeSuspensions.contains(.committing) || hasPendingCommitRecovery {
            #if DEBUG
            DiagnosticLogger.log("Lookup returned for \(barcode) while commit in progress: deferring to post-commit queue")
            #endif
            if lookupErrorText == nil {
                let deferred = ScannedIntakeItem(
                    name: resolvedProduct?.name ?? "Unrecognized product",
                    brand: resolvedProduct?.brand,
                    barcode: barcode,
                    quantity: 1.0,
                    unit: resolvedProduct?.unit ?? "pcs",
                    expirationDate: nil,
                    status: resolvedProduct == nil ? .needsReview : .recognized,
                    productId: resolvedProduct?.id,
                    storageLocationId: nil,
                    isConfirmed: false
                )
                postCommitDeferredItems.append(deferred)
            }
            return
        }

        // Priority 3: Do not treat network/auth errors as unknown products
        if let err = lookupErrorText {
            self.errorMessage = err
            self.scannerState = .error(barcode: barcode, message: err)
            return
        }

        if let prod = resolvedProduct {
            let item = ScannedIntakeItem(
                name: prod.name,
                brand: prod.brand,
                barcode: barcode,
                quantity: 1.0,
                unit: prod.unit ?? "pcs",
                expirationDate: nil,
                status: .recognized,
                productId: prod.id,
                storageLocationId: nil,
                isConfirmed: false
            )
            self.scannedItems.insert(item, at: 0)
            self.scannerState = .detected(barcode: barcode, productName: prod.name)
            showToast("Recognized: \(prod.name)")
        } else {
            // Genuinely not found in catalog (HTTP 200 with empty list)
            self.resolvingItemId = nil
            self.unresolvedBarcode = barcode
            self.showingQuickAddSheet = true
            self.scannerState = .needsReview(barcode: barcode, reason: "Unrecognized barcode")
            showToast("Unrecognized barcode: \(barcode)")
        }
    }

    public func registerProductAndAddToQueue(
        name: String,
        brand: String?,
        category: String?,
        unit: String,
        packageSize: Double?
    ) async -> Bool {
        guard !isIntakeMutationLocked else { return false }
        guard let barcode = unresolvedBarcode else { return false }
        let create = ProductCreate(
            name: name,
            brand: brand?.isEmpty == true ? nil : brand,
            barcode: barcode,
            category: category?.isEmpty == true ? nil : category,
            package_size: packageSize,
            unit: unit
        )

        do {
            let createdProduct: Product
            if isPreview {
                createdProduct = Product(
                    id: Int.random(in: 1000...9999),
                    name: name,
                    brand: brand,
                    barcode: barcode,
                    category: category,
                    package_size: packageSize,
                    unit: unit
                )
            } else {
                createdProduct = try await client.createProduct(create)
            }

            // Requirement 3: Update original intake entry instead of creating duplicate unresolved entries
            if let targetId = resolvingItemId, let idx = scannedItems.firstIndex(where: { $0.id == targetId }) {
                scannedItems[idx].productId = createdProduct.id
                scannedItems[idx].name = createdProduct.name
                scannedItems[idx].brand = createdProduct.brand
                scannedItems[idx].barcode = barcode
                scannedItems[idx].unit = createdProduct.unit ?? scannedItems[idx].unit
                scannedItems[idx].status = .recognized
                invalidateConfirmation(at: idx)
                showToast("Resolved as \(createdProduct.name)")
            } else {
                let item = ScannedIntakeItem(
                    name: createdProduct.name,
                    brand: createdProduct.brand,
                    barcode: barcode,
                    quantity: 1.0,
                    unit: createdProduct.unit ?? "pcs",
                    expirationDate: nil,
                    status: .autoLogged,
                    productId: createdProduct.id,
                    storageLocationId: nil,
                    isConfirmed: false
                )
                self.scannedItems.insert(item, at: 0)
                showToast("Added \(createdProduct.name) to intake queue")
            }
            clearResolutionState()
            return true
        } catch {
            self.errorMessage = "Failed to register product: \(error.localizedDescription)"
            // Preserve unresolved item and user-entered details on failure
            return false
        }
    }

    public func clearResolutionState() {
        resolvingItemId = nil
        unresolvedBarcode = nil
        showingQuickAddSheet = false
    }

    // Requirement 5: Invalidate confirmation when important item details are modified
    public func invalidateConfirmation(at index: Int) {
        guard !isIntakeMutationLocked else { return }
        guard index >= 0 && index < scannedItems.count else { return }
        scannedItems[index].isConfirmed = false
        if scannedItems[index].status == .confirmed {
            scannedItems[index].status = .recognized
        }
    }

    public func incrementQuantity(for item: ScannedIntakeItem) {
        guard !isIntakeMutationLocked else { return }
        if let idx = scannedItems.firstIndex(where: { $0.id == item.id }) {
            scannedItems[idx].quantity += 1.0
            invalidateConfirmation(at: idx)
        }
    }

    public func decrementQuantity(for item: ScannedIntakeItem) {
        guard !isIntakeMutationLocked else { return }
        if let idx = scannedItems.firstIndex(where: { $0.id == item.id }) {
            if scannedItems[idx].quantity > 1.0 {
                scannedItems[idx].quantity -= 1.0
                invalidateConfirmation(at: idx)
            }
            // Bounded stepper: stops at minimum quantity 1.0. Does NOT delete item!
        }
    }

    public func removeItem(id: UUID) {
        guard !isIntakeMutationLocked else { return }
        if let idx = scannedItems.firstIndex(where: { $0.id == id }) {
            let name = scannedItems[idx].name
            scannedItems.remove(at: idx)
            showToast("Removed \(name) from intake")
        }
    }
    // Case 2A: Unknown barcode -> existing product resolution (handles both existing & nil resolvingItemId)
    public func resolveProductWithCatalog(product: Product) {
        guard !isIntakeMutationLocked else { return }
        if let targetId = resolvingItemId, let idx = scannedItems.firstIndex(where: { $0.id == targetId }) {
            scannedItems[idx].productId = product.id
            scannedItems[idx].name = product.name
            scannedItems[idx].brand = product.brand
            if let bc = product.barcode, !bc.isEmpty {
                scannedItems[idx].barcode = bc
            } else if let b = unresolvedBarcode, !b.isEmpty {
                scannedItems[idx].barcode = b
            }
            if let u = product.unit {
                scannedItems[idx].unit = u
            }
            scannedItems[idx].status = .recognized
            invalidateConfirmation(at: idx)
            showToast("Linked as \(product.name)")
        } else {
            let bc = (unresolvedBarcode?.isEmpty == false ? unresolvedBarcode : product.barcode) ?? UUID().uuidString.prefix(8).description
            let item = ScannedIntakeItem(
                name: product.name,
                brand: product.brand,
                barcode: bc,
                quantity: 1.0,
                unit: product.unit ?? "pcs",
                expirationDate: nil,
                status: .recognized,
                productId: product.id,
                storageLocationId: nil,
                isConfirmed: false
            )
            scannedItems.insert(item, at: 0)
            showToast("Added \(product.name) to intake queue")
        }
        clearResolutionState()
    }

    public func resolveItemWithCatalogProduct(itemId: UUID, product: Product) {
        guard !isIntakeMutationLocked else { return }
        resolvingItemId = itemId
        resolveProductWithCatalog(product: product)
    }

    public func updateItemQuantity(id: UUID, quantity: Double) {
        guard !isIntakeMutationLocked else { return }
        guard let idx = scannedItems.firstIndex(where: { $0.id == id }) else { return }
        scannedItems[idx].quantity = max(1.0, quantity)
        invalidateConfirmation(at: idx)
    }

    public func updateItemLocation(id: UUID, locationId: Int?) {
        guard !isIntakeMutationLocked else { return }
        guard let idx = scannedItems.firstIndex(where: { $0.id == id }) else { return }
        scannedItems[idx].storageLocationId = locationId
        invalidateConfirmation(at: idx)
    }

    public func updateItemExpirationDate(id: UUID, date: Date?) {
        guard !isIntakeMutationLocked else { return }
        guard let idx = scannedItems.firstIndex(where: { $0.id == id }) else { return }
        scannedItems[idx].expirationDate = date
        invalidateConfirmation(at: idx)
    }
    public func processScannedReceipt(images: [UIImage]) async {
        guard !isIntakeMutationLocked && !isProcessingReceipt else { return }
        guard !images.isEmpty else {
            self.errorMessage = "No receipt images were provided."
            return
        }
        isProcessingReceipt = true
        suspendScanning(for: .receiptOCR)
        toastMessage = "Processing receipt OCR..."
        defer {
            isProcessingReceipt = false
            resumeScanning(releasing: .receiptOCR)
        }

        var allLines: [String] = []
        for image in images {
            let lines = await ReceiptOCRService.shared.recognizeText(from: image)
            allLines.append(contentsOf: lines)
        }
        await processReceiptLines(allLines)
    }

    func processReceiptLines(_ lines: [String]) async {
        guard !isIntakeMutationLocked else { return }
        lastCapturedReceiptLines = lines
        guard !lines.isEmpty else {
            errorMessage = "No text could be recognized from receipt image. Please ensure the receipt is well-lit and legible."
            return
        }
        await matchReceiptLines(lines)
    }

    public func retryReceiptMatching() async {
        guard !isIntakeMutationLocked && !isProcessingReceipt else { return }
        guard !lastCapturedReceiptLines.isEmpty else {
            self.errorMessage = "No captured receipt lines available to retry."
            return
        }
        isProcessingReceipt = true
        suspendScanning(for: .receiptOCR)
        toastMessage = "Retrying receipt product matching..."
        defer {
            isProcessingReceipt = false
            resumeScanning(releasing: .receiptOCR)
        }
        await matchReceiptLines(lastCapturedReceiptLines)
    }

    private func matchReceiptLines(_ lines: [String]) async {
        let catalog: [Product]
        if isPreview {
            catalog = PreviewData.products
        } else {
            do {
                catalog = try await client.fetchProducts(limit: 500)
            } catch {
                self.errorMessage = "Failed to load product catalog for receipt matching: \(error.localizedDescription). Tap 'Retry Matching' to retry without recapturing."
                return
            }
        }
        let parsedItems = ReceiptOCRService.shared.parseReceiptLines(lines, catalog: catalog)
        integrateReceiptItems(parsedItems)
    }

    public func simulateReceiptScan(receiptName: String = "SM Supermarket Megamall (Receipt #0994)") {
        guard !isIntakeMutationLocked else { return }
        self.storeName = "SM Supermarket Megamall"
        let sampleLines = [
            "SM SUPERMARKET MEGAMALL",
            "CENTURY TUNA FLAKES OIL 180G    2 @ 40.50 V",
            "PUREFOODS CORNED BEEF 150G      92.00",
            "SAN MIGUEL PALE PILSEN 330ML    52.00",
            "GARDENIA CLASSIC WHITE BREAD    82.00",
            "DATU PUTI VINEGAR BOTTLE 1L     48.00",
            "TOTAL AMOUNT                  314.50"
        ]

        let catalog = isPreview ? PreviewData.products : []
        let parsed = ReceiptOCRService.shared.parseReceiptLines(sampleLines, catalog: catalog)
        integrateReceiptItems(parsed)
    }

    private func reconcileExistingItem(at idx: Int, with receiptItem: ReceiptLineItem) {
        let existing = scannedItems[idx]

        // Priority 4: Safe reconciliation - avoid double-counting or blind max()
        if existing.quantity == receiptItem.quantity {
            // Quantities agree: attach receipt unit price if available
            if let price = receiptItem.unitPrice {
                scannedItems[idx].unitPrice = price
            }
            if receiptItem.confidence == .uncertain {
                scannedItems[idx].status = .needsReview
            }
        } else {
            // Explicit conflict: scanned barcode count != receipt line count
            // Flag conflict explicitly so the user can choose the intended final quantity
            scannedItems[idx].conflictingReceiptQuantity = receiptItem.quantity
            if let price = receiptItem.unitPrice {
                scannedItems[idx].unitPrice = price
            }
            scannedItems[idx].status = .needsReview
        }

        // Always invalidate confirmation when receipt reconciliation modifies an item
        invalidateConfirmation(at: idx)
    }

    public func resolveQuantityConflict(id: UUID, keepQuantity: Double) {
        guard !isIntakeMutationLocked else { return }
        guard let idx = scannedItems.firstIndex(where: { $0.id == id }) else { return }
        scannedItems[idx].quantity = max(1.0, keepQuantity)
        scannedItems[idx].conflictingReceiptQuantity = nil
        if scannedItems[idx].productId != nil {
            scannedItems[idx].status = .recognized
        }
        invalidateConfirmation(at: idx)
        showToast("Set quantity to \(Int(keepQuantity)) \(scannedItems[idx].unit)")
    }

    private func deterministicReceiptBarcode(name: String) -> String {
        let normalized = name.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
            .joined(separator: "-")
        let key = normalized.isEmpty ? "unmatched-item" : normalized
        let hashSuffix = String(abs(name.utf8.reduce(0) { ($0 &* 31) &+ Int($1) }))
        return "RCPT-" + key.prefix(20) + "-" + hashSuffix.prefix(6)
    }

    private func integrateReceiptItems(_ parsedItems: [ReceiptLineItem]) {
        guard !isIntakeMutationLocked else { return }
        var mergedCount = 0
        var newCount = 0

        for item in parsedItems {
            let isRecognized = (item.confidence == .exact || item.confidence == .high) && item.matchedProduct != nil
            let status: ScannedIntakeItem.IntakeStatus = isRecognized ? .recognized : .needsReview
            // Medium: Generate deterministic identifier for unmatched items to prevent duplicates on re-import
            let candidateBarcode = item.matchedProduct?.barcode ?? deterministicReceiptBarcode(name: item.parsedName)

            // Identify existing items using reliable product identifiers
            if let pid = item.matchedProduct?.id, let idx = scannedItems.firstIndex(where: { $0.productId == pid }) {
                reconcileExistingItem(at: idx, with: item)
                mergedCount += 1
            } else if let idx = scannedItems.firstIndex(where: { $0.barcode == candidateBarcode }) {
                reconcileExistingItem(at: idx, with: item)
                mergedCount += 1
            } else {
                let intakeItem = ScannedIntakeItem(
                    name: item.matchedProduct?.name ?? item.parsedName,
                    brand: item.matchedProduct?.brand,
                    barcode: candidateBarcode,
                    quantity: item.quantity,
                    unit: item.matchedProduct?.unit ?? "pcs",
                    expirationDate: nil,
                    status: status,
                    productId: item.matchedProduct?.id,
                    storageLocationId: nil,
                    unitPrice: item.unitPrice,
                    isConfirmed: false
                )
                scannedItems.insert(intakeItem, at: 0)
                newCount += 1
            }
        }

        if mergedCount > 0 && newCount > 0 {
            showToast("Added \(newCount) items, merged \(mergedCount) with existing intake")
        } else if mergedCount > 0 {
            showToast("Merged \(mergedCount) items with existing intake")
        } else {
            showToast("Extracted \(newCount) items from receipt")
        }
    }
    public func updateItemPrice(id: UUID, price: Double?) {
        guard !isIntakeMutationLocked else { return }
        guard let idx = scannedItems.firstIndex(where: { $0.id == id }) else { return }
        scannedItems[idx].unitPrice = price
        invalidateConfirmation(at: idx)
    }

    public func updateItemProduct(id: UUID, product: Product) {
        guard !isIntakeMutationLocked else { return }
        resolveItemWithCatalogProduct(itemId: id, product: product)
    }
    private func setupSampleIntake() {
        let calendar = Calendar.current
        self.scannedItems = [
            ScannedIntakeItem(
                name: "Organic Whole Milk",
                brand: "Trader Joe's",
                barcode: "00123456",
                quantity: 1,
                unit: "1L",
                expirationDate: calendar.date(byAdding: .day, value: 5, to: Date()),
                status: .autoLogged,
                productId: 1,
                storageLocationId: 1,
                isConfirmed: true
            ),
            ScannedIntakeItem(
                name: "Greek Yogurt Tub",
                brand: "Fage",
                barcode: "00789012",
                quantity: 2,
                unit: "pack",
                expirationDate: calendar.date(byAdding: .day, value: 12, to: Date()),
                status: .autoLogged,
                productId: 2,
                storageLocationId: 1,
                isConfirmed: true
            ),
            ScannedIntakeItem(
                name: "Century Tuna Flakes",
                brand: "Century",
                barcode: "4800016644810",
                quantity: 4,
                unit: "cans",
                expirationDate: calendar.date(byAdding: .year, value: 2, to: Date()),
                status: .recognized,
                productId: 3,
                storageLocationId: 2,
                isConfirmed: true
            )
        ]
    }

    // MARK: - Centralized Confirmation Logic

    /// Validates whether an intake item satisfies all confirmation requirements.
    public func isItemEligibleForConfirmation(_ item: ScannedIntakeItem) -> Bool {
        item.productId != nil &&
        item.status != .needsReview &&
        item.storageLocationId != nil &&
        item.quantity > 0 &&
        !item.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        item.conflictingReceiptQuantity == nil
    }

    /// Confirms a specific intake item after validating all requirements.
    @discardableResult
    public func confirmItem(id: UUID) -> Bool {
        guard !isIntakeMutationLocked else { return false }
        guard let idx = scannedItems.firstIndex(where: { $0.id == id }) else { return false }
        let target = scannedItems[idx]

        // An item can only be confirmed if it has no conflict, has a productId, is not .needsReview, has storageLocationId, and valid quantity/unit
        guard target.conflictingReceiptQuantity == nil else {
            self.errorMessage = "Cannot confirm: '\(target.name)' has an unresolved quantity conflict. Please choose the correct quantity first."
            return false
        }
        guard target.productId != nil && target.status != .needsReview else {
            self.errorMessage = "Cannot confirm: '\(target.name)' is unresolved. Please link or register the product first."
            return false
        }
        guard target.storageLocationId != nil else {
            self.errorMessage = "Cannot confirm: Please select a storage location for '\(target.name)'."
            return false
        }
        guard target.quantity > 0 && !target.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            self.errorMessage = "Cannot confirm: '\(target.name)' must have a valid quantity and unit."
            return false
        }

        scannedItems[idx].isConfirmed = true
        scannedItems[idx].status = .confirmed
        self.errorMessage = nil
        return true
    }

    /// Unconfirms a specific intake item, returning it to recognized state.
    public func unconfirmItem(id: UUID) {
        guard !isIntakeMutationLocked else { return }
        guard let idx = scannedItems.firstIndex(where: { $0.id == id }) else { return }
        invalidateConfirmation(at: idx)
    }

    /// Confirms all eligible ready items that satisfy validation rules.
    public func confirmAllReady() {
        guard !isIntakeMutationLocked else { return }
        for idx in scannedItems.indices {
            let item = scannedItems[idx]
            if isItemEligibleForConfirmation(item) {
                scannedItems[idx].isConfirmed = true
                scannedItems[idx].status = .confirmed
            }
        }
    }

    /// Compatibility overload for confirmItem(id:)
    @discardableResult
    public func confirmItem(_ item: ScannedIntakeItem) -> Bool {
        confirmItem(id: item.id)
    }

    /// Compatibility alias for confirmAllReady()
    public func confirmAllValid() {
        confirmAllReady()
    }

    /// Count of items needing review (unresolved product or quantity conflict)
    public var itemsNeedingReviewCount: Int {
        scannedItems.filter { $0.productId == nil || $0.status == .needsReview || $0.conflictingReceiptQuantity != nil }.count
    }

    /// Count of items missing a storage location
    public var itemsNeedingLocationCount: Int {
        scannedItems.filter { $0.storageLocationId == nil }.count
    }

    /// Count of confirmed items
    public var confirmedItemsCount: Int {
        scannedItems.filter { $0.isConfirmed }.count
    }

    /// Count of items that satisfy validation rules (whether confirmed or ready to confirm)
    public var readyItemsCount: Int {
        scannedItems.filter { isItemEligibleForConfirmation($0) }.count
    }

    /// Count of items that satisfy validation rules and are waiting to be confirmed
    public var readyToConfirmCount: Int {
        scannedItems.filter { isItemEligibleForConfirmation($0) && !$0.isConfirmed }.count
    }

    public func addItem(barcode: String, name: String, brand: String? = nil, quantity: Double = 1, unit: String = "units", daysUntilExp: Int? = nil) {
        guard !isIntakeMutationLocked else { return }
        let exp: Date? = daysUntilExp.flatMap { Calendar.current.date(byAdding: .day, value: $0, to: Date()) }
        let item = ScannedIntakeItem(
            name: name,
            brand: brand,
            barcode: barcode,
            quantity: quantity,
            unit: unit,
            expirationDate: exp,
            status: .recognized
        )
        scannedItems.insert(item, at: 0)
        lastScannedBarcode = barcode
        toastMessage = "Scanned \(name)"
    }

    public func removeItem(at offsets: IndexSet) {
        guard !isIntakeMutationLocked else { return }
        scannedItems.remove(atOffsets: offsets)
    }

    public func commitIntakeSession() async {
        guard !isCommitting else { return }
        guard pendingCommitRecoveryError == nil else {
            errorMessage = pendingCommitRecoveryError
            return
        }
        guard pendingDraftSessionId == nil || pendingIntakeCommit != nil else {
            errorMessage = "A previous intake submission cannot be identified safely. No new submission was sent."
            return
        }
        guard !scannedItems.isEmpty else {
            errorMessage = "Intake queue is empty. Scan or add items before committing."
            return
        }

        let itemsSnapshot = scannedItems
        for item in itemsSnapshot {
            guard item.conflictingReceiptQuantity == nil else {
                errorMessage = "Cannot commit: '\(item.name)' has an unresolved quantity conflict. Please resolve it before committing."
                return
            }
            guard item.productId != nil && item.status != .needsReview else {
                errorMessage = "Cannot commit: '\(item.name)' is unresolved. Please link or register the product first."
                return
            }
            guard item.storageLocationId != nil else {
                errorMessage = "Cannot commit: Please select a storage location for '\(item.name)'."
                return
            }
            guard item.quantity > 0 && !item.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                errorMessage = "Cannot commit: '\(item.name)' must have a valid quantity and unit."
                return
            }
            guard item.isConfirmed else {
                errorMessage = "Cannot commit: Please confirm details for '\(item.name)' before committing."
                return
            }
        }

        isCommitting = true
        errorMessage = nil
        suspendScanning(for: .committing)
        defer {
            isCommitting = false
            resumeScanning(releasing: .committing)
        }

        if isPreview {
            try? await Task.sleep(nanoseconds: 300_000_000)
            toastMessage = "Committed intake of \(itemsSnapshot.count) items (Preview)"
            clearCommittedIntake(committedCount: itemsSnapshot.count)
            return
        }

        do {
            if let pending = pendingIntakeCommit {
                let currentFingerprint = try intakeFingerprint(items: itemsSnapshot, storeName: storeName)
                guard currentFingerprint == pending.fingerprint else {
                    scannedItems = pending.intakeItems
                    storeName = pending.storeName
                    errorMessage = "The saved intake changed after a previous submission. The original snapshot was restored; reconcile it before editing."
                    return
                }
                try await reconcilePendingCommit(pending)
                return
            }

            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd"
            let requestItems = try itemsSnapshot.map { item -> SessionItemCreate in
                guard let productID = item.productId, let locationID = item.storageLocationId else {
                    throw IntakeCommitError.invalidItem
                }
                return SessionItemCreate(
                    product_id: productID,
                    storage_location_id: locationID,
                    quantity: item.quantity,
                    expiration_date: item.expirationDate.map { dateFormatter.string(from: $0) },
                    unit_price: item.unitPrice
                )
            }
            let sessionName = storeName.trimmingCharacters(in: .whitespacesAndNewlines)
            let normalizedStoreName = sessionName.isEmpty ? "Grocery Intake" : sessionName
            let fingerprint = try intakeFingerprint(items: itemsSnapshot, storeName: normalizedStoreName)
            let computedTotal = itemsSnapshot.compactMap { item in
                item.unitPrice.map { $0 * item.quantity }
            }.reduce(0.0, +)
            let isoFormatter = ISO8601DateFormatter()
            let creationRequest = GrocerySessionCreate(
                store_name: normalizedStoreName,
                purchase_date: isoFormatter.string(from: Date()),
                total_amount: computedTotal > 0 ? computedTotal : nil,
                notes: "Rapid intake session committed via Provision app",
                idempotency_key: UUID().uuidString
            )
            let pending = PendingIntakeCommit(
                sessionID: nil,
                fingerprint: fingerprint,
                storeName: normalizedStoreName,
                intakeItems: itemsSnapshot,
                requestItems: requestItems,
                creationRequest: creationRequest
            )
            try persistPendingCommit(pending)
            try await reconcilePendingCommit(pending)
        } catch {
            errorMessage = "Failed to commit intake session: \(error.localizedDescription). The saved submission, if present, remains available for safe reconciliation."
            HapticFeedback.warning()
            if pendingIntakeCommit == nil && !postCommitDeferredItems.isEmpty {
                scannedItems.insert(contentsOf: postCommitDeferredItems, at: 0)
                postCommitDeferredItems.removeAll()
            }
        }
    }

    public func cancelPendingCommitAndUnlock() async {
        guard !isCommitting, let unresolvedPending = pendingIntakeCommit else { return }
        isCommitting = true
        errorMessage = nil
        suspendScanning(for: .committing)
        defer {
            isCommitting = false
            resumeScanning(releasing: .committing)
        }

        do {
            let (pending, _) = try await resolvePendingSession(unresolvedPending)
            guard let sessionID = pending.sessionID else {
                throw IntakeCommitError.unidentifiedSession
            }
            let session = try await client.fetchSession(id: sessionID)
            switch session.status.uppercased() {
            case "COMPLETED":
                clearCommittedIntake(committedCount: pending.requestItems.count)
                errorMessage = "The previous intake was already committed. Its result has been reconciled."
            case "DRAFT":
                let cancelled = try await client.cancelSession(id: sessionID)
                guard cancelled.status.uppercased() == "CANCELLED" else {
                    errorMessage = "The previous draft was not confirmed cancelled. The intake remains locked for reconciliation."
                    return
                }
                clearCancelledPendingCommit()
            case "CANCELLED":
                clearCancelledPendingCommit()
            default:
                errorMessage = "Previous intake session #\(sessionID) has status '\(session.status)'. It cannot be safely unlocked."
            }
        } catch {
            errorMessage = "Could not safely cancel or reconcile the previous intake: \(error.localizedDescription). No replacement submission was sent."
        }
    }

    private func reconcilePendingCommit(_ unresolvedPending: PendingIntakeCommit) async throws {
        let (pending, createdSession) = try await resolvePendingSession(unresolvedPending)
        guard let sessionID = pending.sessionID else {
            throw IntakeCommitError.unidentifiedSession
        }
        let sessionStatus: String
        if let createdSession {
            sessionStatus = createdSession.status
        } else {
            sessionStatus = try await client.fetchSession(id: sessionID).status
        }
        switch sessionStatus.uppercased() {
        case "COMPLETED":
            clearCommittedIntake(committedCount: pending.requestItems.count)
        case "DRAFT":
            await submitPendingCommit(pending)
        case "CANCELLED":
            clearCancelledPendingCommit()
        default:
            errorMessage = "Previous intake session #\(sessionID) has status '\(sessionStatus)'. No new session was created."
        }
    }

    private func resolvePendingSession(
        _ pending: PendingIntakeCommit
    ) async throws -> (pending: PendingIntakeCommit, createdSession: GrocerySession?) {
        guard pending.sessionID == nil else { return (pending, nil) }
        guard let creationRequest = pending.creationRequest,
              creationRequest.idempotency_key != nil else {
            throw IntakeCommitError.unidentifiedSession
        }
        let createdSession = try await client.createSession(creationRequest)
        let identifiedPending = pending.attaching(sessionID: createdSession.id)
        try persistPendingCommit(identifiedPending)
        return (identifiedPending, createdSession)
    }

    private func submitPendingCommit(_ pending: PendingIntakeCommit) async {
        guard let sessionID = pending.sessionID else {
            errorMessage = IntakeCommitError.unidentifiedSession.localizedDescription
            return
        }
        do {
            let committed = try await client.commitSession(id: sessionID, items: pending.requestItems)
            guard committed.status.uppercased() == "COMPLETED" else {
                errorMessage = "Session #\(sessionID) returned status '\(committed.status)'. Its saved submission remains locked for reconciliation."
                return
            }
            clearCommittedIntake(committedCount: pending.requestItems.count)
            HapticFeedback.success()
        } catch {
            errorMessage = "Could not confirm intake session #\(sessionID): \(error.localizedDescription). Retry reconciliation before editing or creating another session."
            HapticFeedback.warning()
        }
    }

    private func intakeFingerprint(items: [ScannedIntakeItem], storeName: String) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let payload = IntakeFingerprintPayload(storeName: storeName, items: items)
        let digest = SHA256.hash(data: try encoder.encode(payload))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private func persistPendingCommit(_ pending: PendingIntakeCommit) throws {
        let data = try JSONEncoder().encode(pending)
        pendingCommitDefaults.set(data, forKey: pendingIntakeCommitStorageKey)
        pendingIntakeCommit = pending
        pendingDraftSessionId = pending.sessionID
        storeName = pending.storeName
        activeSuspensions.insert(.pendingCommitRecovery)
        scannerManager.lockAcceptance()
        scannerManager.stopScanning()
    }

    private func clearPendingCommitState() {
        if pendingIntakeCommit != nil {
            pendingCommitDefaults.removeObject(forKey: pendingIntakeCommitStorageKey)
        }
        pendingIntakeCommit = nil
        pendingDraftSessionId = nil
        pendingCommitRecoveryError = nil
        activeSuspensions.remove(.pendingCommitRecovery)
    }

    private func clearCancelledPendingCommit() {
        clearPendingCommitState()
        if !postCommitDeferredItems.isEmpty {
            scannedItems.insert(contentsOf: postCommitDeferredItems, at: 0)
            postCommitDeferredItems.removeAll()
        }
        errorMessage = nil
        showToast("Previous draft cancelled; no inventory was committed. Review and retry when ready.")
    }

    private func clearCommittedIntake(committedCount: Int) {
        clearPendingCommitState()
        toastMessage = "Committed \(committedCount) items to household inventory!"
        scannedItems = postCommitDeferredItems
        postCommitDeferredItems.removeAll()
        lastScannedBarcode = ""
        if let first = scannedItems.first {
            scannerState = .detected(barcode: first.barcode, productName: first.name)
        }
    }
}

private enum IntakeCommitError: LocalizedError {
    case invalidItem
    case unidentifiedSession

    var errorDescription: String? {
        switch self {
        case .invalidItem:
            return "An intake item has no product or storage location."
        case .unidentifiedSession:
            return "Saved session creation cannot be replayed safely because its idempotency key is unavailable."
        }
    }
}
