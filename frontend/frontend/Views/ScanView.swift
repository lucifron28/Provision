import VisionKit
import SwiftUI

public struct ScanView: View {
    @ObservedObject var viewModel: ScanViewModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var scanMode: Int = 0 // 0: Rapid Barcode, 1: Receipt Review
    @State private var showingAddManualSheet: Bool = false
    @State private var manualName: String = ""
    @State private var manualBarcode: String = ""
    @State private var manualBrand: String = ""
    @State private var quickAddName: String = ""
    @State private var quickAddBrand: String = ""
    @State private var quickAddCategory: String = "Canned Goods"
    @State private var quickAddUnit: String = "pcs"
    @State private var isRegisteringProduct: Bool = false
    @State private var editingItemForOCR: ScannedIntakeItem? = nil
    @State private var manualDatePickerItem: ScannedIntakeItem? = nil
    @State private var editingPriceItem: ScannedIntakeItem? = nil
    @State private var editingPriceText: String = ""
    @State private var selectedCatalogProductId: Int? = nil

    public init(viewModel: ScanViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Mode Picker
                    Picker("Mode", selection: $scanMode) {
                        Text("Rapid Barcode").tag(0)
                        Text("Receipt Intake").tag(1)
                    }
                    .pickerStyle(.segmented)

                    // Viewfinder Box
                    viewfinderCard

                    // Detected Barcode Display & Single-Scan Controls
                    if scanMode == 0 {
                        detectedBarcodeCard
                        rearmControlsCard
                    }
                    // Quick Simulation Bar (Available in simulator or preview testing)
                    if !viewModel.scannerManager.isCameraAvailable || viewModel.isPreview {
                        simulationBarcodeButtons
                    }
                    // Scanned Intake Items Review
                    intakeReviewSection
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
            .background(ProvisionTheme.background.ignoresSafeArea())
            .navigationTitle("Intake Scanner")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                if scanMode == 1 {
                    viewModel.suspendScanning(for: .receiptMode)
                } else {
                    viewModel.resumeScanning(releasing: .receiptMode)
                }
                if scenePhase == .active {
                    viewModel.resumeScanning(releasing: .background)
                } else {
                    viewModel.suspendScanning(for: .background)
                }
                viewModel.resumeScanning(releasing: .navigatedAway)
            }
            .onDisappear {
                viewModel.suspendScanning(for: .navigatedAway)
            }
            .onChange(of: scanMode) { _, newMode in
                if newMode == 1 {
                    viewModel.suspendScanning(for: .receiptMode)
                } else {
                    viewModel.resumeScanning(releasing: .receiptMode)
                }
            }
            .onChange(of: scenePhase) { _, newPhase in
                if newPhase == .active {
                    viewModel.resumeScanning(releasing: .background)
                } else {
                    viewModel.suspendScanning(for: .background)
                }
            }
            .onChange(of: activeModalSuspension) { oldReason, newReason in
                if let old = oldReason {
                    viewModel.resumeScanning(releasing: old)
                }
                if let new = newReason {
                    viewModel.suspendScanning(for: new)
                }
            }
            .sheet(isPresented: $showingAddManualSheet) {
                manualEntrySheet
            }
            .sheet(isPresented: $viewModel.showingQuickAddSheet) {
                quickAddProductSheet
                    .onDisappear {
                        viewModel.clearResolutionState()
                    }
            }
            .sheet(isPresented: $viewModel.showingReceiptCamera) {
                #if canImport(VisionKit)
                DocumentCameraScannerView(
                    onScannedImages: { images in
                        viewModel.showingReceiptCamera = false
                        Task {
                            await viewModel.processScannedReceipt(images: images)
                        }
                    },
                    onCancel: {
                        viewModel.showingReceiptCamera = false
                    }
                )
                #else
                EmptyView()
                #endif
            }
            .sheet(item: $editingItemForOCR) { targetItem in
                ExpirationDateScannerSheet(
                    title: "Scan Expiry: \(targetItem.name)",
                    initialDate: targetItem.expirationDate
                ) { (scannedDate: Date?) in
                    viewModel.updateItemExpirationDate(id: targetItem.id, date: scannedDate)
                    editingItemForOCR = nil
                }
            }
            .sheet(item: $manualDatePickerItem) { targetItem in
                NavigationStack {
                    DatePickerSheet(initialDate: targetItem.expirationDate ?? Date()) { selectedDate in
                        viewModel.updateItemExpirationDate(id: targetItem.id, date: selectedDate)
                        manualDatePickerItem = nil
                    } onCancel: {
                        manualDatePickerItem = nil
                    }
                }
                .presentationDetents([.medium])
            }
            .alert("Edit Unit Price", isPresented: isEditingPriceBinding) {
                TextField("Price in PHP (e.g. 45.00)", text: $editingPriceText)
                    .keyboardType(.decimalPad)
                Button("Cancel", role: .cancel) { editingPriceItem = nil }
                Button("Save") {
                    if let target = editingPriceItem {
                        let trimmed = editingPriceText.trimmingCharacters(in: .whitespacesAndNewlines)
                        if trimmed.isEmpty {
                            viewModel.updateItemPrice(id: target.id, price: nil)
                        } else if let parsed = Double(trimmed.replacingOccurrences(of: ",", with: ".")), parsed >= 0 {
                            viewModel.updateItemPrice(id: target.id, price: parsed)
                        } else {
                            viewModel.errorMessage = "Invalid price '\(trimmed)'. Please enter a valid number (e.g. 45.00)."
                        }
                    }
                    editingPriceItem = nil
                }
            } message: {
                if let target = editingPriceItem {
                    Text("Enter the unit price for '\(target.name)'")
                }
            }
            .overlay(alignment: .bottom) {
                if let msg = viewModel.toastMessage {
                    Text(msg)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(ProvisionTheme.provisionGreen)
                        .clipShape(Capsule())
                        .shadow(color: .black.opacity(0.12), radius: 6, y: 3)
                        .padding(.bottom, 16)
                }
            }
            .task {
                await viewModel.loadLocations()
            }
        }
    }

    // MARK: - Subviews

    private var viewfinderCard: some View {
        ZStack {
            if scanMode == 0 {
                // Real camera scanner in Rapid Barcode mode
                BarcodeScannerView(manager: viewModel.scannerManager)
                .frame(height: 200)
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            } else {
                // Receipt Review Mode
                ZStack {
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(Color(red: 0.10, green: 0.12, blue: 0.11))
                        .frame(height: 200)

                    VStack(spacing: 12) {
                        Image(systemName: "doc.text.viewfinder")
                            .font(.system(size: 36))
                            .foregroundStyle(ProvisionTheme.heroCard)

                        Text("Supermarket Receipt Scanner")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(.white)

                        HStack(spacing: 8) {
                            #if canImport(VisionKit)
                            if VNDocumentCameraViewController.isSupported {
                                Button {
                                    viewModel.showingReceiptCamera = true
                                } label: {
                                    HStack(spacing: 5) {
                                        Image(systemName: "camera.fill")
                                        Text("Scan")
                                    }
                                    .font(.system(size: 12, weight: .bold))
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 7)
                                    .background(ProvisionTheme.heroCard)
                                    .foregroundStyle(ProvisionTheme.background)
                                    .clipShape(Capsule())
                                }
                            }
                            #endif
                            if !viewModel.lastCapturedReceiptLines.isEmpty {
                                Button {
                                    Task {
                                        await viewModel.retryReceiptMatching()
                                    }
                                } label: {
                                    HStack(spacing: 5) {
                                        Image(systemName: "arrow.clockwise")
                                        Text("Retry Matching")
                                    }
                                    .font(.system(size: 11, weight: .semibold))
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 7)
                                    .background(ProvisionTheme.provisionGreenLight)
                                    .foregroundStyle(ProvisionTheme.provisionGreen)
                                    .clipShape(Capsule())
                                }
                            }
                            #if DEBUG
                            if viewModel.isPreview {
                                Button {
                                    viewModel.simulateReceiptScan()
                                } label: {
                                    HStack(spacing: 5) {
                                        Image(systemName: "doc.badge.plus")
                                        Text("Sample Receipt (#0994)")
                                    }
                                    .font(.system(size: 11, weight: .semibold))
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 7)
                                    .background(ProvisionTheme.surface)
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .clipShape(Capsule())
                                    .overlay(Capsule().stroke(ProvisionTheme.border, lineWidth: 1))
                                }
                            }
                            #endif
                        }
                    }
                }
            }
            // Scanner State Banner Overlay (ONLY displayed when in Barcode mode!)
            if scanMode == 0 {
                VStack {
                    HStack(spacing: 6) {
                        switch viewModel.scannerState {
                        case .ready:
                            Circle()
                                .fill(Color.green)
                                .frame(width: 8, height: 8)
                            Text("Ready to Scan")
                        case .processing:
                            ProgressView()
                                .scaleEffect(0.6)
                                .tint(.white)
                            Text("Looking up barcode...")
                        case .detected(_, let name):
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(Color.green)
                            Text("Scanned: \(name)")
                        case .needsReview:
                            Image(systemName: "exclamationmark.circle.fill")
                                .foregroundStyle(ProvisionTheme.amberWarning)
                            Text("Action Required")
                        case .error:
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(ProvisionTheme.redAlert)
                            Text("Lookup Error")
                        case .paused(let reason):
                            Image(systemName: "pause.circle.fill")
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text("Paused: \(reason)")
                        }
                    }
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.black.opacity(0.65))
                    .clipShape(Capsule())
                    .padding(.top, 12)

                    Spacer()
                }
                .allowsHitTesting(false)
            }
        }
    }

    private var simulationBarcodeButtons: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("QUICK SCAN SIMULATION")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(ProvisionTheme.textTertiary)
                .tracking(0.6)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    simButton(title: "Whole Milk", brand: "Dairy", barcode: "00123456", days: 7)
                    simButton(title: "Century Tuna", brand: "Century", barcode: "4800016644810", days: 730)
                    simButton(title: "Greek Yogurt", brand: "Fage", barcode: "00789012", days: 14)
                    simButton(title: "Jasmine Rice", brand: "Royal", barcode: "00345678", days: 365)
                }
            }
        }
    }

    private func simButton(title: String, brand: String, barcode: String, days: Int) -> some View {
        Button {
            viewModel.onBarcodeScanned(barcode, generation: viewModel.currentScanGeneration)
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "barcode.viewfinder")
                    .font(.system(size: 12))
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(ProvisionTheme.surface)
            .foregroundStyle(ProvisionTheme.textPrimary)
            .clipShape(Capsule())
            .overlay(Capsule().stroke(ProvisionTheme.border, lineWidth: 1))
        }
    }

    private var detectedBarcodeCard: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(viewModel.lastScannedBarcode.isEmpty ? ProvisionTheme.surfaceSecondary : ProvisionTheme.provisionGreenLight)
                    .frame(width: 40, height: 40)
                Image(systemName: "barcode.viewfinder")
                    .font(.system(size: 20))
                    .foregroundStyle(viewModel.lastScannedBarcode.isEmpty ? ProvisionTheme.textTertiary : ProvisionTheme.provisionGreen)
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text("Detected Barcode")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .textCase(.uppercase)
                        .tracking(0.8)
                    if viewModel.isResolvingBarcode {
                        ProgressView()
                            .scaleEffect(0.7)
                    }
                }

                if viewModel.lastScannedBarcode.isEmpty {
                    Text("Waiting for barcode...")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                } else {
                    Text(viewModel.lastScannedBarcode)
                        .font(.system(size: 17, weight: .bold, design: .monospaced))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
            }

            Spacer()

            if !viewModel.lastScannedBarcode.isEmpty {
                Button {
                    UIPasteboard.general.string = viewModel.lastScannedBarcode
                    viewModel.toastMessage = "Copied to clipboard"
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.system(size: 13))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .padding(8)
                        .background(ProvisionTheme.surfaceSecondary)
                        .clipShape(Circle())
                }
            }
        }
        .padding(14)
        .provisionCard(borderColor: viewModel.lastScannedBarcode.isEmpty ? ProvisionTheme.border : ProvisionTheme.provisionGreen.opacity(0.5))
    }

    @ViewBuilder
    private var rearmControlsCard: some View {
        HStack(spacing: 10) {
            if viewModel.canRearm {
                Button {
                    viewModel.rearmScanner()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "barcode.viewfinder")
                        Text("Scan Next Barcode")
                            .font(.system(size: 14, weight: .bold))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(ProvisionTheme.provisionGreen)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
            } else if case .processing = viewModel.scannerState {
                HStack(spacing: 8) {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Looking up product in catalog...")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(ProvisionTheme.surfaceSecondary)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }

            if case .error = viewModel.scannerState {
                Button {
                    viewModel.retryBarcodeLookup()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.clockwise")
                        Text("Retry Lookup")
                            .font(.system(size: 13, weight: .semibold))
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(ProvisionTheme.redLight)
                    .foregroundStyle(ProvisionTheme.redAlert)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
            } else if case .paused = viewModel.scannerState, !viewModel.isSuspended {
                Button {
                    viewModel.rearmScanner()
                } label: {
                    Text("Resume")
                        .font(.system(size: 13, weight: .semibold))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(ProvisionTheme.surfaceSecondary)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var isEditingPriceBinding: Binding<Bool> {
        Binding(
            get: { editingPriceItem != nil },
            set: { if !$0 { editingPriceItem = nil } }
        )
    }

    private var activeModalSuspension: SuspensionReason? {
        if showingAddManualSheet { return .manualEntrySheet }
        if viewModel.showingQuickAddSheet { return .quickAddSheet }
        if viewModel.showingReceiptCamera { return .receiptCamera }
        if editingItemForOCR != nil { return .expirationSheet }
        if manualDatePickerItem != nil { return .priceEditing }
        if editingPriceItem != nil { return .priceEditing }
        return nil
    }
    private var intakeReviewSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Intake Review")
                        .font(.system(size: 18, weight: .bold, design: .serif))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text("\(viewModel.scannedItems.count) items in current intake session")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }

                Spacer()

                HStack(spacing: 8) {
                    // "Confirm All" button if there are items ready to confirm
                    let hasConfirmableItems = viewModel.scannedItems.contains { item in
                        !item.isConfirmed &&
                        item.productId != nil &&
                        item.status != .needsReview &&
                        item.storageLocationId != nil &&
                        item.quantity > 0 &&
                        !item.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    }
                    if hasConfirmableItems {
                        Button {
                            viewModel.confirmAllValid()
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark.circle.fill")
                                Text("Confirm All")
                            }
                            .font(.system(size: 12, weight: .bold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(ProvisionTheme.provisionGreenLight)
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                            .clipShape(Capsule())
                        }
                    }

                    Button {
                        showingAddManualSheet = true
                    } label: {
                        Text("+ Manual")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                }
                .disabled(viewModel.isIntakeMutationLocked)
            }

            // Validation error banner if viewModel.errorMessage != nil
            if let errorMsg = viewModel.errorMessage {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .font(.system(size: 16))

                    Text(errorMsg)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(ProvisionTheme.redAlert)

                    Spacer()

                    Button {
                        viewModel.errorMessage = nil
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(ProvisionTheme.redAlert.opacity(0.8))
                    }
                    .buttonStyle(.plain)
                }
                .padding(12)
                .background(ProvisionTheme.redLight)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(ProvisionTheme.redAlert.opacity(0.3), lineWidth: 1)
                )
            }

            if viewModel.isProcessingReceipt {
                HStack(spacing: 12) {
                    ProgressView()
                        .tint(ProvisionTheme.provisionGreen)
                    Text("Processing receipt with Vision OCR...")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Spacer()
                }
                .padding(14)
                .provisionCard()
            }

            if viewModel.scannedItems.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "barcode")
                        .font(.system(size: 36))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text("No items scanned in this session")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                .frame(maxWidth: .infinity)
                .padding(32)
                .provisionCard()
            } else {
                let totalCount = viewModel.scannedItems.count
                let confirmedCount = viewModel.scannedItems.filter { $0.isConfirmed }.count
                let allConfirmed = totalCount > 0 && confirmedCount == totalCount

                // Requirement 7: Commit readiness banner
                HStack(spacing: 8) {
                    Image(systemName: allConfirmed ? "checkmark.circle.fill" : "info.circle.fill")
                        .font(.system(size: 13))
                    Text(allConfirmed ? "Ready to Commit • All \(totalCount) item(s) confirmed" : "\(confirmedCount) of \(totalCount) item(s) confirmed • Review & confirm all items to commit")
                        .font(.system(size: 12, weight: .semibold))
                    Spacer()
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(allConfirmed ? ProvisionTheme.provisionGreenLight : ProvisionTheme.amberLight)
                .foregroundStyle(allConfirmed ? ProvisionTheme.provisionGreen : ProvisionTheme.amberWarning)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                VStack(spacing: 10) {
                    ForEach($viewModel.scannedItems) { $item in
                        intakeItemRow(item: $item)
                    }
                }
                .disabled(viewModel.isIntakeMutationLocked)

                // Commit Button with anti-duplicate and disabled state
                Button {
                    Task {
                        await viewModel.commitIntakeSession()
                    }
                } label: {
                    HStack {
                        if viewModel.isCommitting {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Image(systemName: viewModel.hasPendingCommitRecovery ? "arrow.clockwise.circle.fill" : allConfirmed ? "checkmark.circle.fill" : "lock.fill")
                            Text(viewModel.hasPendingCommitRecovery ? "Resolve Previous Submission" : allConfirmed ? "Commit \(totalCount) Item(s) to Pantry" : "Commit Intake (\(confirmedCount)/\(totalCount) Confirmed)")
                                .font(.system(size: 16, weight: .bold))
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background((allConfirmed || viewModel.hasPendingCommitRecovery) ? ProvisionTheme.provisionGreen : ProvisionTheme.textTertiary)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
                .disabled(viewModel.isCommitting || viewModel.pendingCommitRecoveryError != nil || (!viewModel.hasPendingCommitRecovery && !allConfirmed))
                .padding(.top, 8)

                if viewModel.hasPendingCommitRecovery {
                    Button("Check Status / Cancel Previous Draft") {
                        Task {
                            await viewModel.cancelPendingCommitAndUnlock()
                        }
                    }
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.redAlert)
                    .disabled(viewModel.isCommitting || viewModel.pendingCommitRecoveryError != nil)
                    .padding(.top, 4)
                }
            }
        }
    }

    private func intakeItemRow(item: Binding<ScannedIntakeItem>) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header: Name, Brand, Barcode + Status Badge
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(item.wrappedValue.name)
                        .font(.system(size: 15, weight: .bold, design: .serif))
                        .foregroundStyle(ProvisionTheme.textPrimary)

                    Text("\(item.wrappedValue.brand ?? "Pantry") • Barcode: \(item.wrappedValue.barcode)")
                        .font(.system(size: 11))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }

                Spacer()

                HStack(spacing: 8) {
                    // Status Badge
                    statusBadge(for: item.wrappedValue)

                    // Explicit Delete Action
                    Button(role: .destructive) {
                        viewModel.removeItem(id: item.wrappedValue.id)
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 13))
                            .foregroundStyle(ProvisionTheme.redAlert)
                            .padding(6)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Remove \(item.wrappedValue.name) from intake")
                }
            }

            // Priority 4: Explicit Quantity Conflict Resolution Banner
            if let conflictQty = item.wrappedValue.conflictingReceiptQuantity {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(ProvisionTheme.amberWarning)
                            .font(.system(size: 13))
                        Text("Quantity Conflict Detected")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(ProvisionTheme.amberWarning)
                    }

                    Text("Barcode count is \(Int(item.wrappedValue.quantity)), but receipt shows \(Int(conflictQty)). Choose which quantity is correct:")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.textSecondary)

                    HStack(spacing: 8) {
                        Button {
                            viewModel.resolveQuantityConflict(id: item.wrappedValue.id, keepQuantity: item.wrappedValue.quantity)
                        } label: {
                            Text("Keep Scanned (\(Int(item.wrappedValue.quantity)))")
                                .font(.system(size: 12, weight: .semibold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(ProvisionTheme.surfaceSecondary)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        }
                        .buttonStyle(.plain)

                        Button {
                            viewModel.resolveQuantityConflict(id: item.wrappedValue.id, keepQuantity: conflictQty)
                        } label: {
                            Text("Use Receipt (\(Int(conflictQty)))")
                                .font(.system(size: 12, weight: .semibold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(ProvisionTheme.provisionGreenLight)
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(10)
                .background(ProvisionTheme.amberLight)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            // If productId == nil: prominent button/tag to trigger quick add
            if item.wrappedValue.productId == nil || item.wrappedValue.status == .needsReview {
                Button {
                    viewModel.resolvingItemId = item.wrappedValue.id
                    viewModel.unresolvedBarcode = item.wrappedValue.barcode
                    quickAddName = item.wrappedValue.name
                    quickAddBrand = item.wrappedValue.brand ?? ""
                    selectedCatalogProductId = nil
                    viewModel.showingQuickAddSheet = true
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "questionmark.circle.fill")
                            .font(.system(size: 12))
                        Text(item.wrappedValue.productId == nil ? "Unresolved Product • Tap to Match or Register" : "Uncertain Match • Tap to Review Product")
                            .font(.system(size: 12, weight: .bold))
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.system(size: 10, weight: .bold))
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(ProvisionTheme.amberLight)
                    .foregroundStyle(ProvisionTheme.amberWarning)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(ProvisionTheme.amberWarning.opacity(0.4), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }

            Divider()

            // Price & Line Total Row
            HStack(spacing: 8) {
                if let price = item.wrappedValue.unitPrice {
                    HStack(spacing: 4) {
                        Image(systemName: "tag.fill")
                            .font(.system(size: 10))
                        Text(String(format: "₱%.2f ea", price))
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundStyle(ProvisionTheme.provisionGreen)

                    Text("•")
                        .foregroundStyle(ProvisionTheme.textTertiary)

                    Text(String(format: "Total: ₱%.2f", price * item.wrappedValue.quantity))
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                } else {
                    Text("No price recorded")
                        .font(.system(size: 11))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                }

                Spacer()

                Button {
                    editingPriceItem = item.wrappedValue
                    editingPriceText = item.wrappedValue.unitPrice.map { String(format: "%.2f", $0) } ?? ""
                } label: {
                    Text(item.wrappedValue.unitPrice == nil ? "+ Set Price" : "Edit Price")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
                .buttonStyle(.plain)
            }

            // Controls Row: Quantity, Location Selector, Expiration Date
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    // Quantity Stepper
                    HStack(spacing: 8) {
                        Text("Qty: \(Int(item.wrappedValue.quantity)) \(item.wrappedValue.unit)")
                            .font(.system(size: 13, weight: .semibold))

                        Stepper("", onIncrement: {
                            viewModel.incrementQuantity(for: item.wrappedValue)
                        }, onDecrement: {
                            viewModel.decrementQuantity(for: item.wrappedValue)
                        })
                        .labelsHidden()
                    }
                    Spacer()

                    // Confirm/Unconfirm action button
                    Button {
                        if item.wrappedValue.isConfirmed {
                            item.wrappedValue.isConfirmed = false
                            item.wrappedValue.status = .recognized
                        } else {
                            if item.wrappedValue.storageLocationId == nil {
                                viewModel.errorMessage = "Please select a storage location for '\(item.wrappedValue.name)'"
                            } else if item.wrappedValue.productId == nil || item.wrappedValue.status == .needsReview {
                                viewModel.errorMessage = "Cannot confirm: '\(item.wrappedValue.name)' is unresolved. Please register the product first."
                            } else {
                                item.wrappedValue.isConfirmed = true
                                item.wrappedValue.status = .confirmed
                                viewModel.errorMessage = nil
                            }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: item.wrappedValue.isConfirmed ? "checkmark.circle.fill" : "circle")
                            Text(item.wrappedValue.isConfirmed ? "Confirmed" : "Confirm Details")
                        }
                        .font(.system(size: 12, weight: .bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(item.wrappedValue.isConfirmed ? ProvisionTheme.provisionGreen : ProvisionTheme.surfaceSecondary)
                        .foregroundStyle(item.wrappedValue.isConfirmed ? .white : ProvisionTheme.textPrimary)
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }

                HStack(alignment: .center, spacing: 12) {
                    // Storage Location Selector
                    Menu {
                        ForEach(viewModel.availableLocations) { loc in
                            Button {
                                viewModel.updateItemLocation(id: item.wrappedValue.id, locationId: loc.id)
                            } label: {
                                HStack {
                                    Text(loc.name)
                                    if item.wrappedValue.storageLocationId == loc.id {
                                        Image(systemName: "checkmark")
                                    }
                                }
                            }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "archivebox")
                                .font(.system(size: 11))
                            if let locId = item.wrappedValue.storageLocationId,
                               let loc = viewModel.availableLocations.first(where: { $0.id == locId }) {
                                Text(loc.name)
                                    .font(.system(size: 12, weight: .medium))
                            } else {
                                Text("Select Location ⚠️")
                                    .font(.system(size: 12, weight: .bold))
                                    .foregroundStyle(ProvisionTheme.amberWarning)
                            }
                            Image(systemName: "chevron.down")
                                .font(.system(size: 9))
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(item.wrappedValue.storageLocationId == nil ? ProvisionTheme.amberLight : ProvisionTheme.surfaceSecondary)
                        .foregroundStyle(item.wrappedValue.storageLocationId == nil ? ProvisionTheme.amberWarning : ProvisionTheme.textPrimary)
                        .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    // Expiration Date Section
                    if let expDate = item.wrappedValue.expirationDate {
                        HStack(spacing: 4) {
                            Button {
                                editingItemForOCR = item.wrappedValue
                            } label: {
                                HStack(spacing: 4) {
                                    Image(systemName: "calendar")
                                        .font(.system(size: 11))
                                    Text(expDate, format: .dateTime.month().day().year())
                                        .font(.system(size: 12, weight: .medium))
                                }
                                .padding(.horizontal, 8)
                                .padding(.vertical, 5)
                                .background(ProvisionTheme.surfaceSecondary)
                                .foregroundStyle(ProvisionTheme.textPrimary)
                                .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)

                            Button {
                                editingItemForOCR = item.wrappedValue
                            } label: {
                                Image(systemName: "camera.viewfinder")
                                    .font(.system(size: 11))
                                    .padding(6)
                                    .background(ProvisionTheme.surfaceSecondary)
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .clipShape(Circle())
                            }
                            .buttonStyle(.plain)

                            Button {
                                viewModel.updateItemExpirationDate(id: item.wrappedValue.id, date: nil)
                            } label: {
                                Text("Clear")
                                    .font(.system(size: 11, weight: .semibold))
                                    .foregroundStyle(ProvisionTheme.redAlert)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 4)
                            }
                            .buttonStyle(.plain)
                        }
                    } else {
                        HStack(spacing: 4) {
                            Text("No Expiration (Optional)")
                                .font(.system(size: 11))
                                .foregroundStyle(ProvisionTheme.textSecondary)

                            Button {
                                manualDatePickerItem = item.wrappedValue
                            } label: {
                                Text("Pick")
                                    .font(.system(size: 11, weight: .semibold))
                                    .foregroundStyle(ProvisionTheme.provisionGreen)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 4)
                                    .background(ProvisionTheme.provisionGreenLight)
                                    .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)

                            Button {
                                editingItemForOCR = item.wrappedValue
                            } label: {
                                HStack(spacing: 2) {
                                    Image(systemName: "camera.viewfinder")
                                        .font(.system(size: 10))
                                    Text("OCR")
                                        .font(.system(size: 11, weight: .semibold))
                                }
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 4)
                                .background(ProvisionTheme.provisionGreenLight)
                                .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .padding(14)
        .provisionCard()
    }

    @ViewBuilder
    private func statusBadge(for item: ScannedIntakeItem) -> some View {
        if item.isConfirmed {
            Text("Confirmed")
                .font(.system(size: 10, weight: .bold))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(ProvisionTheme.provisionGreenLight)
                .foregroundStyle(ProvisionTheme.provisionGreen)
                .clipShape(Capsule())
        } else if item.productId == nil || item.status == .needsReview {
            Text("Needs Review")
                .font(.system(size: 10, weight: .bold))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(ProvisionTheme.amberLight)
                .foregroundStyle(ProvisionTheme.amberWarning)
                .clipShape(Capsule())
        } else {
            Text("Recognized")
                .font(.system(size: 10, weight: .bold))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.blue.opacity(0.12))
                .foregroundStyle(Color.blue)
                .clipShape(Capsule())
        }
    }

    private var manualEntrySheet: some View {
        NavigationStack {
            Form {
                Section("Product Information") {
                    TextField("Product Name", text: $manualName)
                    TextField("Brand (Optional)", text: $manualBrand)
                    TextField("Barcode / SKU", text: $manualBarcode)
                }
            }
            .navigationTitle("Manual Intake Entry")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showingAddManualSheet = false }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        if !manualName.isEmpty {
                            viewModel.addItem(
                                barcode: manualBarcode.isEmpty ? UUID().uuidString.prefix(8).description : manualBarcode,
                                name: manualName,
                                brand: manualBrand.isEmpty ? nil : manualBrand
                            )
                            manualName = ""
                            manualBrand = ""
                            manualBarcode = ""
                            showingAddManualSheet = false
                        }
                    }
                    .disabled(manualName.isEmpty)
                }
            }
        }
    }

    private var quickAddProductSheet: some View {
        NavigationStack {
            Form {
                if !viewModel.availableCatalog.isEmpty {
                    Section("Match to Existing Catalog Product") {
                        Picker("Select Catalog Product", selection: $selectedCatalogProductId) {
                            Text("Choose from catalog...").tag(nil as Int?)
                            ForEach(viewModel.availableCatalog) { prod in
                                Text("\(prod.name) (\(prod.brand ?? "Pantry"))").tag(prod.id as Int?)
                            }
                        }

                        if let selId = selectedCatalogProductId,
                           let foundProd = viewModel.availableCatalog.first(where: { $0.id == selId }) {
                            Button {
                                viewModel.resolveProductWithCatalog(product: foundProd)
                                selectedCatalogProductId = nil
                            } label: {
                                HStack {
                                    Image(systemName: "link.circle.fill")
                                    Text("Link as \(foundProd.name)")
                                        .bold()
                                }
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                            }
                        }
                    }
                }

                Section("Or Register as New Product") {
                    HStack {
                        Text("Barcode")
                        Spacer()
                        Text(viewModel.unresolvedBarcode ?? "")
                            .font(.system(size: 14, weight: .bold, design: .monospaced))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    TextField("Product Name (Required)", text: $quickAddName)
                    TextField("Brand (Optional)", text: $quickAddBrand)

                    Picker("Category", selection: $quickAddCategory) {
                        ForEach(["Canned Goods", "Dairy & Chilled", "Snacks & Bakery", "Beverages", "Grains & Staples", "Fresh Produce", "Condiments & Sauces", "Frozen & Meats"], id: \.self) { cat in
                            Text(cat).tag(cat)
                        }
                    }

                    Picker("Unit", selection: $quickAddUnit) {
                        ForEach(ProductUnits.allUnits, id: \.self) { u in
                            Text(u).tag(u)
                        }
                    }
                }
            }
            .navigationTitle("Resolve Product Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        viewModel.clearResolutionState()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        isRegisteringProduct = true
                        Task {
                            let success = await viewModel.registerProductAndAddToQueue(
                                name: quickAddName,
                                brand: quickAddBrand.isEmpty ? nil : quickAddBrand,
                                category: quickAddCategory,
                                unit: quickAddUnit,
                                packageSize: nil
                            )
                            if success {
                                quickAddName = ""
                                quickAddBrand = ""
                            }
                            isRegisteringProduct = false
                        }
                    } label: {
                        if isRegisteringProduct {
                            ProgressView()
                        } else {
                            Text("Save & Add")
                                .bold()
                        }
                    }
                    .disabled(quickAddName.trimmingCharacters(in: .whitespaces).isEmpty || isRegisteringProduct)
                }
            }
        }
    }
}

private struct DatePickerSheet: View {
    @State private var selectedDate: Date
    let onSave: (Date) -> Void
    let onCancel: () -> Void

    init(initialDate: Date, onSave: @escaping (Date) -> Void, onCancel: @escaping () -> Void) {
        _selectedDate = State(initialValue: initialDate)
        self.onSave = onSave
        self.onCancel = onCancel
    }

    var body: some View {
        VStack(spacing: 20) {
            DatePicker(
                "Expiration Date",
                selection: $selectedDate,
                displayedComponents: [.date]
            )
            .datePickerStyle(.graphical)
            .padding()
        }
        .navigationTitle("Pick Expiration Date")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel", action: onCancel)
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("Set Date") {
                    onSave(selectedDate)
                }
                .bold()
            }
        }
    }
}

#Preview("Intake Scanner") {
    ScanView(viewModel: PreviewData.makeScanViewModel())
}
