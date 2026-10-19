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
    @State private var reviewingItem: ScannedIntakeItem? = nil

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
            .sheet(item: $reviewingItem) { item in
                IntakeItemReviewSheet(
                    itemId: item.id,
                    viewModel: viewModel
                )
            }
            .safeAreaInset(edge: .bottom) {
                if !viewModel.scannedItems.isEmpty {
                    commitActionBar
                }
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
            } else if case .paused = viewModel.scannerState,
                      viewModel.activeSuspensions.contains(.userPaused) {
                Button {
                    viewModel.resumeScanning(releasing: .userPaused)
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
                .disabled(viewModel.isIntakeMutationLocked)
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
        if reviewingItem != nil { return .itemReviewSheet }
        return nil
    }

    private var intakeReviewSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            intakeSummaryHeader

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
                emptyIntakeView
            } else {
                LazyVStack(spacing: 8) {
                    ForEach(viewModel.scannedItems) { item in
                        compactIntakeRow(for: item)
                    }
                }
                .disabled(viewModel.isIntakeMutationLocked)
            }
        }
    }

    private var intakeSummaryHeader: some View {
        let totalCount = viewModel.scannedItems.count
        let readyCount = viewModel.readyItemsCount
        let needsReviewCount = viewModel.itemsNeedingReviewCount
        let readyToConfirmCount = viewModel.readyToConfirmCount

        return HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Intake Review")
                    .font(ProvisionTypography.sectionSerif)
                    .foregroundStyle(ProvisionTheme.textPrimary)

                HStack(spacing: 6) {
                    Text("Total: \(totalCount)")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textSecondary)

                    Text("•")
                        .font(.system(size: 10))
                        .foregroundStyle(ProvisionTheme.textTertiary)

                    Text("Ready: \(readyCount)")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.provisionGreen)

                    if needsReviewCount > 0 {
                        Text("•")
                            .font(.system(size: 10))
                            .foregroundStyle(ProvisionTheme.textTertiary)

                        HStack(spacing: 2) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 9))
                            Text("Needs Review: \(needsReviewCount)")
                                .font(.system(size: 12, weight: .bold))
                        }
                        .foregroundStyle(ProvisionTheme.amberWarning)
                    }
                }
            }

            Spacer()

            HStack(spacing: 8) {
                if readyToConfirmCount > 0 {
                    Button {
                        viewModel.confirmAllReady()
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
                    .disabled(viewModel.isIntakeMutationLocked)
                }

                Button {
                    showingAddManualSheet = true
                } label: {
                    Text("+ Manual")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
                .disabled(viewModel.isIntakeMutationLocked)
            }
        }
    }

    private var emptyIntakeView: some View {
        VStack(spacing: 12) {
            Image("pip_grocery")
                .resizable()
                .scaledToFit()
                .frame(width: 80, height: 80)
                .accessibilityHidden(true)

            Text("No items scanned in this session")
                .font(ProvisionTypography.headline)
                .foregroundStyle(ProvisionTheme.textSecondary)

            Text("Scan barcodes or receipts above, or add items manually.")
                .font(ProvisionTypography.footnote)
                .foregroundStyle(ProvisionTheme.textTertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(28)
        .provisionCard()
    }

    private func compactIntakeRow(for item: ScannedIntakeItem) -> some View {
        Button {
            reviewingItem = item
        } label: {
            let state = viewModel.validationState(for: item)
            let hasConflict = item.conflictingReceiptQuantity != nil
            let hasException = (state == .needsReview || state == .needsDetails)

            HStack(alignment: .center, spacing: 10) {
                // Exception warning indicator
                if hasException {
                    Image(systemName: state == .needsReview ? "exclamationmark.triangle.fill" : "exclamationmark.circle.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(state == .needsReview ? ProvisionTheme.redAlert : ProvisionTheme.amberWarning)
                }

                // Main Details Column with adaptive multi-line wrapping
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(item.name)
                            .font(ProvisionTypography.headline)
                            .foregroundStyle(ProvisionTheme.textPrimary)
                            .lineLimit(2)
                            .fixedSize(horizontal: false, vertical: true)

                        if let brand = item.brand, !brand.isEmpty {
                            Text("(\(brand))")
                                .font(ProvisionTypography.caption)
                                .foregroundStyle(ProvisionTheme.textSecondary)
                                .lineLimit(1)
                        }
                    }

                    // Adaptive metadata layout: wraps to 2 lines on small screens/Dynamic Type
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 6) {
                            Text("\(formattedQuantity(item.quantity)) \(item.unit)")
                                .font(ProvisionTypography.subheadline)
                                .foregroundStyle(ProvisionTheme.textSecondary)

                            Text("•")
                                .font(ProvisionTypography.caption)
                                .foregroundStyle(ProvisionTheme.textTertiary)

                            locationBadge(for: item)

                            if hasConflict {
                                Text("•")
                                    .font(ProvisionTypography.caption)
                                    .foregroundStyle(ProvisionTheme.textTertiary)
                                conflictBadge
                            }
                        }

                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(formattedQuantity(item.quantity)) \(item.unit)")
                                .font(ProvisionTypography.subheadline)
                                .foregroundStyle(ProvisionTheme.textSecondary)

                            HStack(spacing: 6) {
                                locationBadge(for: item)
                                if hasConflict {
                                    conflictBadge
                                }
                            }
                        }
                    }
                }

                Spacer(minLength: 6)

                // Status Pill & Chevron
                HStack(spacing: 6) {
                    statusPill(for: item)

                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(ProvisionTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(hasException ? (state == .needsReview ? ProvisionTheme.redAlert.opacity(0.4) : ProvisionTheme.amberWarning.opacity(0.4)) : ProvisionTheme.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(item.name), \(formattedQuantity(item.quantity)) \(item.unit), \(item.storageLocationId != nil ? "location selected" : "no location selected"), status: \(viewModel.validationState(for: item).rawValue)")
        .accessibilityHint("Double tap to inspect and edit item details")
    }

    @ViewBuilder
    private func locationBadge(for item: ScannedIntakeItem) -> some View {
        if let locId = item.storageLocationId,
           let loc = viewModel.availableLocations.first(where: { $0.id == locId }) {
            HStack(spacing: 3) {
                Image(systemName: "archivebox")
                    .font(.system(size: 10))
                Text(loc.name)
                    .font(ProvisionTypography.caption)
            }
            .foregroundStyle(ProvisionTheme.textSecondary)
        } else {
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.circle.fill")
                    .font(.system(size: 10))
                Text("No location")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(ProvisionTheme.amberLight)
            .foregroundStyle(ProvisionTheme.amberWarning)
            .clipShape(Capsule())
        }
    }

    private var conflictBadge: some View {
        Text("Conflict")
            .font(.system(size: 10, weight: .bold))
            .padding(.horizontal, 5)
            .padding(.vertical, 1.5)
            .background(ProvisionTheme.redLight)
            .foregroundStyle(ProvisionTheme.redAlert)
            .clipShape(Capsule())
    }

    @ViewBuilder
    private func statusPill(for item: ScannedIntakeItem) -> some View {
        let state = viewModel.validationState(for: item)
        switch state {
        case .confirmed:
            HStack(spacing: 3) {
                Image(systemName: "checkmark")
                    .font(.system(size: 9, weight: .bold))
                Text("Confirmed")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.provisionGreenLight)
            .foregroundStyle(ProvisionTheme.provisionGreen)
            .clipShape(Capsule())

        case .needsReview:
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 9, weight: .bold))
                Text("Needs Review")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.redLight)
            .foregroundStyle(ProvisionTheme.redAlert)
            .clipShape(Capsule())

        case .needsDetails:
            HStack(spacing: 3) {
                Image(systemName: "exclamationmark.circle")
                    .font(.system(size: 9, weight: .bold))
                Text("Needs Details")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.amberLight)
            .foregroundStyle(ProvisionTheme.amberWarning)
            .clipShape(Capsule())

        case .ready:
            HStack(spacing: 3) {
                Image(systemName: "circle")
                    .font(.system(size: 9, weight: .bold))
                Text("Ready")
                    .font(.system(size: 11, weight: .bold))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(ProvisionTheme.provisionGreenLight.opacity(0.6))
            .foregroundStyle(ProvisionTheme.provisionGreen)
            .clipShape(Capsule())
        }
    }

    private var commitActionBar: some View {
        let totalCount = viewModel.scannedItems.count
        let confirmedCount = viewModel.confirmedItemsCount
        let allConfirmed = totalCount > 0 && confirmedCount == totalCount
        let reviewCount = viewModel.itemsNeedingReviewCount
        let locationCount = viewModel.itemsNeedingLocationCount
        let unconfirmedCount = totalCount - confirmedCount

        var reasons: [String] = []
        if reviewCount > 0 {
            reasons.append("\(reviewCount) item\(reviewCount == 1 ? "" : "s") need review")
        }
        if locationCount > 0 {
            reasons.append("\(locationCount) item\(locationCount == 1 ? "" : "s") need location")
        }
        if reasons.isEmpty && unconfirmedCount > 0 {
            reasons.append("\(unconfirmedCount) item\(unconfirmedCount == 1 ? "" : "s") need confirmation")
        }
        let reasonText = reasons.joined(separator: " • ")

        return VStack(spacing: 8) {
            // Clear status / reasons when disabled
            HStack(spacing: 6) {
                if allConfirmed {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                    Text("Ready to Commit • All \(totalCount) items confirmed")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                } else if viewModel.hasPendingCommitRecovery {
                    Image(systemName: "arrow.clockwise.circle.fill")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.amberWarning)
                    Text("Unresolved previous submission pending")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.amberWarning)
                } else {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.amberWarning)
                    Text(reasonText)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.amberWarning)
                        .lineLimit(1)
                }
                Spacer()
            }

            // Commit Button
            Button {
                Task {
                    await viewModel.commitIntakeSession()
                }
            } label: {
                HStack(spacing: 8) {
                    if viewModel.isCommitting {
                        ProgressView()
                            .tint(.white)
                        Text("Committing Intake...")
                            .font(.system(size: 15, weight: .bold))
                    } else {
                        Image(systemName: viewModel.hasPendingCommitRecovery ? "arrow.clockwise.circle.fill" : allConfirmed ? "checkmark.circle.fill" : "lock.fill")
                        Text(viewModel.hasPendingCommitRecovery ? "Resolve Previous Submission" : allConfirmed ? "Commit \(totalCount) Item(s) to Pantry" : "Commit Intake (\(confirmedCount)/\(totalCount) Confirmed)")
                            .font(.system(size: 15, weight: .bold))
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 13)
                .background((allConfirmed || viewModel.hasPendingCommitRecovery) ? ProvisionTheme.provisionGreen : ProvisionTheme.surfaceSecondary)
                .foregroundStyle((allConfirmed || viewModel.hasPendingCommitRecovery) ? ProvisionTheme.onAccent : ProvisionTheme.textTertiary)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(allConfirmed ? Color.clear : ProvisionTheme.border.opacity(0.6), lineWidth: 1)
                )
            }
            .disabled(viewModel.isCommitting || viewModel.pendingCommitRecoveryError != nil || (!viewModel.hasPendingCommitRecovery && !allConfirmed))

            if viewModel.hasPendingCommitRecovery {
                Button("Check Status / Cancel Previous Draft") {
                    Task {
                        await viewModel.cancelPendingCommitAndUnlock()
                    }
                }
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(ProvisionTheme.redAlert)
                .disabled(viewModel.isCommitting || viewModel.pendingCommitRecoveryError != nil)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 6)
        .background(
            ProvisionTheme.surface
                .shadow(color: Color.black.opacity(0.06), radius: 8, x: 0, y: -4)
        )
        .overlay(alignment: .top) {
            Divider()
        }
    }

    private func formattedQuantity(_ qty: Double) -> String {
        if qty.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(qty))"
        } else {
            return String(format: "%.1f", qty)
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
// MARK: - Focused Intake Item Review Sheet

public struct IntakeItemReviewSheet: View {
    public let itemId: UUID
    @ObservedObject public var viewModel: ScanViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var showingOCRScanner: Bool = false
    @State private var priceText: String = ""
    @State private var catalogSearchQuery: String = ""
    @State private var selectedCatalogProductId: Int? = nil
    @State private var newProductName: String = ""
    @State private var newProductBrand: String = ""
    @State private var newProductCategory: String = "Canned Goods"
    @State private var newProductUnit: String = "pcs"
    @State private var isRegistering: Bool = false
    @State private var showingInlineRegistration: Bool = false

    private var item: ScannedIntakeItem? {
        viewModel.scannedItems.first(where: { $0.id == itemId })
    }

    public init(itemId: UUID, viewModel: ScanViewModel) {
        self.itemId = itemId
        self.viewModel = viewModel
    }

    public var body: some View {
        NavigationStack {
            Group {
                if let targetItem = item {
                    ScrollView {
                        VStack(spacing: 16) {
                            // Header: Name, Brand, Barcode & Status Pill
                            headerCard(for: targetItem)

                            // Conflict Resolution Banner (if conflict exists)
                            if let conflictQty = targetItem.conflictingReceiptQuantity {
                                conflictCard(for: targetItem, conflictQty: conflictQty)
                            }

                            // Unresolved Product Banner / Resolution (if status == .needsReview or productId == nil)
                            if targetItem.productId == nil || targetItem.status == .needsReview {
                                productResolutionCard(for: targetItem)
                            }

                            // Core Properties Card
                            VStack(spacing: 14) {
                                // 1. Quantity Stepper with unit display (minimum 1.0 bounded)
                                quantityRow(for: targetItem)

                                Divider()

                                // 2. Storage Location Picker
                                locationRow(for: targetItem)

                                Divider()

                                // 3. Expiration Date Picker & Scanner Trigger
                                expirationRow(for: targetItem)

                                Divider()

                                // 4. Unit Price Editor
                                priceRow(for: targetItem)
                            }
                            .padding(14)
                            .provisionCard()

                            // Confirmation Section
                            confirmationCard(for: targetItem)

                            // Delete Action
                            Button(role: .destructive) {
                                viewModel.removeItem(id: targetItem.id)
                                dismiss()
                            } label: {
                                HStack(spacing: 6) {
                                    Image(systemName: "trash")
                                    Text("Remove from Intake")
                                }
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.redAlert)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                            }
                            .disabled(viewModel.isIntakeMutationLocked)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 16)
                    }
                    .background(ProvisionTheme.background.ignoresSafeArea())
                } else {
                    VStack(spacing: 12) {
                        Text("Item no longer in intake queue")
                            .font(ProvisionTypography.headline)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                        Button("Done") {
                            dismiss()
                        }
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(ProvisionTheme.background.ignoresSafeArea())
                }
            }
            .navigationTitle("Item Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                }
            }
            .sheet(isPresented: $showingOCRScanner) {
                if let targetItem = item {
                    ExpirationDateScannerSheet(
                        title: "Scan Expiry: \(targetItem.name)",
                        initialDate: targetItem.expirationDate
                    ) { scannedDate in
                        viewModel.updateItemExpirationDate(id: targetItem.id, date: scannedDate)
                        showingOCRScanner = false
                    }
                }
            }
            .onAppear {
                if let target = item {
                    if let p = target.unitPrice {
                        priceText = String(format: "%.2f", p)
                    }
                    newProductName = target.name
                    newProductBrand = target.brand ?? ""
                    newProductUnit = target.unit
                }
            }
        }
    }

    private func headerCard(for targetItem: ScannedIntakeItem) -> some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text(targetItem.name)
                    .font(ProvisionTypography.titleSerif)
                    .foregroundStyle(ProvisionTheme.textPrimary)

                Text("\(targetItem.brand ?? "Pantry") • Barcode: \(targetItem.barcode)")
                    .font(ProvisionTypography.caption)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }

            Spacer()

            if targetItem.isConfirmed {
                Text("Confirmed")
                    .font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(ProvisionTheme.provisionGreenLight)
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .clipShape(Capsule())
            } else if targetItem.productId == nil || targetItem.status == .needsReview || targetItem.conflictingReceiptQuantity != nil {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 10))
                    Text("Needs Review")
                        .font(.system(size: 11, weight: .bold))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(ProvisionTheme.amberLight)
                .foregroundStyle(ProvisionTheme.amberWarning)
                .clipShape(Capsule())
            } else {
                Text("Ready")
                    .font(.system(size: 11, weight: .bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(ProvisionTheme.provisionGreenLight.opacity(0.6))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .clipShape(Capsule())
            }
        }
        .padding(14)
        .provisionCard()
    }

    private func conflictCard(for targetItem: ScannedIntakeItem, conflictQty: Double) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(ProvisionTheme.amberWarning)
                Text("Quantity Conflict Detected")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(ProvisionTheme.amberWarning)
            }

            Text("Scanned barcode count is \(formattedQuantity(targetItem.quantity)), but receipt shows \(formattedQuantity(conflictQty)). Choose correct quantity:")
                .font(.system(size: 12))
                .foregroundStyle(ProvisionTheme.textSecondary)

            HStack(spacing: 10) {
                Button {
                    viewModel.resolveQuantityConflict(id: targetItem.id, keepQuantity: targetItem.quantity)
                } label: {
                    Text("Keep Scanned (\(formattedQuantity(targetItem.quantity)))")
                        .font(.system(size: 12, weight: .semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(ProvisionTheme.surfaceSecondary)
                        .foregroundStyle(ProvisionTheme.textPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
                .buttonStyle(.plain)

                Button {
                    viewModel.resolveQuantityConflict(id: targetItem.id, keepQuantity: conflictQty)
                } label: {
                    Text("Use Receipt (\(formattedQuantity(conflictQty)))")
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
        .padding(12)
        .background(ProvisionTheme.amberLight)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(ProvisionTheme.amberWarning.opacity(0.4), lineWidth: 1)
        )
    }

    private func productResolutionCard(for targetItem: ScannedIntakeItem) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "questionmark.circle.fill")
                    .foregroundStyle(ProvisionTheme.amberWarning)
                Text(targetItem.productId == nil ? "Unresolved Product" : "Needs Review")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(ProvisionTheme.amberWarning)
            }

            Text("This barcode (\(targetItem.barcode)) is not linked to a verified catalog product. Link to an existing catalog product or register details below.")
                .font(.system(size: 12))
                .foregroundStyle(ProvisionTheme.textSecondary)
            if !viewModel.availableCatalog.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Search & Match Existing Catalog Product:")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textPrimary)

                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 12))
                            .foregroundStyle(ProvisionTheme.textTertiary)

                        TextField("Search by name, brand, or barcode...", text: $catalogSearchQuery)
                            .font(.system(size: 13))
                            .foregroundStyle(ProvisionTheme.textPrimary)

                        if !catalogSearchQuery.isEmpty {
                            Button {
                                catalogSearchQuery = ""
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 13))
                                    .foregroundStyle(ProvisionTheme.textTertiary)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(ProvisionTheme.inputBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(ProvisionTheme.border, lineWidth: 1)
                    )

                    let query = catalogSearchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                    let filteredCatalog = viewModel.availableCatalog.filter { prod in
                        guard !query.isEmpty else { return true }
                        let nameMatch = prod.name.lowercased().contains(query)
                        let brandMatch = prod.brand?.lowercased().contains(query) == true
                        let barcodeMatch = prod.barcode?.contains(query) == true
                        let categoryMatch = prod.category?.lowercased().contains(query) == true
                        return nameMatch || brandMatch || barcodeMatch || categoryMatch
                    }

                    if filteredCatalog.isEmpty {
                        Text("No catalog products match '\(catalogSearchQuery)'. Register below.")
                            .font(.system(size: 11))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .padding(.vertical, 4)
                    } else {
                        ScrollView(.vertical, showsIndicators: true) {
                            LazyVStack(spacing: 6) {
                                ForEach(Array(filteredCatalog.prefix(8))) { prod in
                                    Button {
                                        viewModel.resolveItemWithCatalogProduct(itemId: targetItem.id, product: prod)
                                        catalogSearchQuery = ""
                                    } label: {
                                        HStack {
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(prod.name)
                                                    .font(.system(size: 13, weight: .semibold))
                                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                                HStack(spacing: 4) {
                                                    if let brand = prod.brand, !brand.isEmpty {
                                                        Text(brand)
                                                    }
                                                    if let cat = prod.category {
                                                        Text("• \(cat)")
                                                    }
                                                }
                                                .font(.system(size: 11))
                                                .foregroundStyle(ProvisionTheme.textSecondary)
                                            }
                                            Spacer()
                                            HStack(spacing: 4) {
                                                Image(systemName: "link.circle.fill")
                                                Text("Link")
                                                    .font(.system(size: 12, weight: .bold))
                                            }
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 6)
                                            .background(ProvisionTheme.provisionGreenLight)
                                            .foregroundStyle(ProvisionTheme.provisionGreen)
                                            .clipShape(Capsule())
                                        }
                                        .padding(8)
                                        .background(ProvisionTheme.surface)
                                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                        .frame(maxHeight: 180)
                    }
                }
            }

            Divider()

            DisclosureGroup(isExpanded: $showingInlineRegistration) {
                VStack(spacing: 10) {
                    TextField("Product Name (Required)", text: $newProductName)
                        .provisionInputField()
                    TextField("Brand (Optional)", text: $newProductBrand)
                        .provisionInputField()
                    Picker("Category", selection: $newProductCategory) {
                        ForEach(["Canned Goods", "Dairy & Chilled", "Snacks & Bakery", "Beverages", "Grains & Staples", "Fresh Produce", "Condiments & Sauces", "Frozen & Meats"], id: \.self) { cat in
                            Text(cat).tag(cat)
                        }
                    }
                    Picker("Unit", selection: $newProductUnit) {
                        ForEach(ProductUnits.allUnits, id: \.self) { u in
                            Text(u).tag(u)
                        }
                    }

                    Button {
                        isRegistering = true
                        Task {
                            viewModel.resolvingItemId = targetItem.id
                            viewModel.unresolvedBarcode = targetItem.barcode
                            let success = await viewModel.registerProductAndAddToQueue(
                                name: newProductName,
                                brand: newProductBrand.isEmpty ? nil : newProductBrand,
                                category: newProductCategory,
                                unit: newProductUnit,
                                packageSize: nil
                            )
                            if success {
                                newProductName = ""
                                newProductBrand = ""
                                showingInlineRegistration = false
                            }
                            isRegistering = false
                        }
                    } label: {
                        if isRegistering {
                            ProgressView().tint(.white)
                        } else {
                            Text("Register & Link Product")
                                .font(.system(size: 13, weight: .bold))
                                .foregroundStyle(.white)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 10)
                                .background(newProductName.trimmingCharacters(in: .whitespaces).isEmpty ? ProvisionTheme.textTertiary : ProvisionTheme.provisionGreen)
                                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }
                    }
                    .disabled(newProductName.trimmingCharacters(in: .whitespaces).isEmpty || isRegistering)
                }
                .padding(.top, 8)
            } label: {
                HStack {
                    Image(systemName: "plus.circle.fill")
                    Text("Register as New Product")
                        .font(.system(size: 13, weight: .semibold))
                }
                .foregroundStyle(ProvisionTheme.provisionGreen)
            }
        }
        .padding(12)
        .background(ProvisionTheme.amberLight)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(ProvisionTheme.amberWarning.opacity(0.4), lineWidth: 1)
        )
    }

    private func quantityRow(for targetItem: ScannedIntakeItem) -> some View {
        HStack {
            Text("Quantity")
                .font(ProvisionTypography.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
            Spacer()
            HStack(spacing: 12) {
                Text("\(formattedQuantity(targetItem.quantity)) \(targetItem.unit)")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textPrimary)

                Stepper("") {
                    viewModel.incrementQuantity(for: targetItem)
                } onDecrement: {
                    viewModel.decrementQuantity(for: targetItem)
                }
                .labelsHidden()
            }
        }
    }

    private func locationRow(for targetItem: ScannedIntakeItem) -> some View {
        HStack {
            Text("Storage Location")
                .font(ProvisionTypography.subheadline)
                .foregroundStyle(ProvisionTheme.textSecondary)
            Spacer()
            Menu {
                ForEach(viewModel.availableLocations) { loc in
                    Button {
                        viewModel.updateItemLocation(id: targetItem.id, locationId: loc.id)
                    } label: {
                        HStack {
                            Text(loc.name)
                            if targetItem.storageLocationId == loc.id {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "archivebox")
                        .font(.system(size: 12))
                    if let locId = targetItem.storageLocationId,
                       let loc = viewModel.availableLocations.first(where: { $0.id == locId }) {
                        Text(loc.name)
                            .font(.system(size: 13, weight: .semibold))
                    } else {
                        Text("Select Location ⚠️")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(ProvisionTheme.amberWarning)
                    }
                    Image(systemName: "chevron.down")
                        .font(.system(size: 10))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(targetItem.storageLocationId == nil ? ProvisionTheme.amberLight : ProvisionTheme.surfaceSecondary)
                .foregroundStyle(targetItem.storageLocationId == nil ? ProvisionTheme.amberWarning : ProvisionTheme.textPrimary)
                .clipShape(Capsule())
            }
        }
    }

    private func expirationRow(for targetItem: ScannedIntakeItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Expiration Date")
                    .font(ProvisionTypography.subheadline)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                Spacer()
                Button {
                    showingOCRScanner = true
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "camera.viewfinder")
                        Text("Scan OCR")
                    }
                    .font(.system(size: 12, weight: .semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(ProvisionTheme.provisionGreenLight)
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }

            if let exp = targetItem.expirationDate {
                HStack {
                    DatePicker(
                        "Date",
                        selection: Binding(
                            get: { exp },
                            set: { viewModel.updateItemExpirationDate(id: targetItem.id, date: $0) }
                        ),
                        displayedComponents: .date
                    )
                    .labelsHidden()

                    Spacer()

                    Button("Clear") {
                        viewModel.updateItemExpirationDate(id: targetItem.id, date: nil)
                    }
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.redAlert)
                    .buttonStyle(.plain)
                }
            } else {
                HStack {
                    Text("No expiration set")
                        .font(.system(size: 13))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Spacer()
                    Button("+ Set Date") {
                        viewModel.updateItemExpirationDate(id: targetItem.id, date: Calendar.current.date(byAdding: .day, value: 30, to: Date()))
                    }
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func priceRow(for targetItem: ScannedIntakeItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Unit Price (PHP)")
                    .font(ProvisionTypography.subheadline)
                    .foregroundStyle(ProvisionTheme.textSecondary)
                Spacer()
                HStack(spacing: 6) {
                    Text("₱")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    TextField("0.00", text: $priceText)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .frame(width: 80)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(ProvisionTheme.surfaceSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        .onChange(of: priceText) { _, newText in
                            let trimmed = newText.trimmingCharacters(in: .whitespacesAndNewlines)
                            if trimmed.isEmpty {
                                viewModel.updateItemPrice(id: targetItem.id, price: nil)
                            } else if let parsed = Double(trimmed.replacingOccurrences(of: ",", with: ".")), parsed >= 0 {
                                viewModel.updateItemPrice(id: targetItem.id, price: parsed)
                            }
                        }
                }
            }

            if let p = targetItem.unitPrice {
                HStack {
                    Spacer()
                    Text(String(format: "Total: ₱%.2f", p * targetItem.quantity))
                        .font(ProvisionTypography.caption)
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
            }
        }
    }

    private func confirmationCard(for targetItem: ScannedIntakeItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if targetItem.isConfirmed {
                Button {
                    viewModel.unconfirmItem(id: targetItem.id)
                } label: {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                        Text("Confirmed • Tap to Unconfirm")
                            .font(.system(size: 14, weight: .bold))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(ProvisionTheme.provisionGreenLight)
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
            } else {
                Button {
                    viewModel.confirmItem(id: targetItem.id)
                } label: {
                    HStack {
                        Image(systemName: "checkmark.circle")
                        Text("Confirm Details")
                            .font(.system(size: 14, weight: .bold))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(viewModel.isItemEligibleForConfirmation(targetItem) ? ProvisionTheme.provisionGreen : ProvisionTheme.surfaceSecondary)
                    .foregroundStyle(viewModel.isItemEligibleForConfirmation(targetItem) ? ProvisionTheme.onAccent : ProvisionTheme.textTertiary)
                }
                .disabled(viewModel.isIntakeMutationLocked)

                if !viewModel.isItemEligibleForConfirmation(targetItem) {
                    HStack(spacing: 4) {
                        Image(systemName: "info.circle")
                            .font(.system(size: 11))
                        Text(unconfirmedReason(for: targetItem))
                            .font(.system(size: 11))
                    }
                    .foregroundStyle(ProvisionTheme.amberWarning)
                    .padding(.top, 2)
                }
            }

            if let error = viewModel.errorMessage {
                Text(error)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(ProvisionTheme.redAlert)
            }
        }
    }

    private func unconfirmedReason(for item: ScannedIntakeItem) -> String {
        if item.conflictingReceiptQuantity != nil {
            return "Resolve quantity conflict before confirming"
        }
        if item.productId == nil || item.status == .needsReview {
            return "Link or register product before confirming"
        }
        if item.storageLocationId == nil {
            return "Select a storage location before confirming"
        }
        if item.quantity <= 0 || item.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Provide a valid quantity and unit before confirming"
        }
        return "Complete all required details before confirming"
    }

    private func formattedQuantity(_ qty: Double) -> String {
        if qty.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(qty))"
        } else {
            return String(format: "%.1f", qty)
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
