import SwiftUI

public struct ScanView: View {
    @ObservedObject var viewModel: ScanViewModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var scanMode: Int = 0 // 0: Rapid Barcode, 1: Receipt Review
    @State private var showingAddManualSheet: Bool = false
    @State private var manualName: String = ""
    @State private var manualBarcode: String = ""
    @State private var manualBrand: String = ""
    
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
                    
                    // Detected Barcode Display
                    if scanMode == 0 {
                        detectedBarcodeCard
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
                if scanMode == 0 {
                    viewModel.startScanning()
                }
            }
            .onDisappear {
                viewModel.stopScanning()
            }
            .onChange(of: scanMode) { _, newMode in
                if newMode == 0 {
                    viewModel.startScanning()
                } else {
                    viewModel.stopScanning()
                }
            }
            .onChange(of: scenePhase) { _, newPhase in
                if newPhase == .active && scanMode == 0 {
                    viewModel.startScanning()
                } else {
                    viewModel.stopScanning()
                }
            }
            .sheet(isPresented: $showingAddManualSheet) {
                manualEntrySheet
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
        }
    }
    
    // MARK: - Subviews
    
    private var viewfinderCard: some View {
        ZStack {
            if scanMode == 0 {
                // Real camera scanner in Rapid Barcode mode
                BarcodeScannerView(manager: viewModel.scannerManager) { detectedBarcode in
                    viewModel.onBarcodeScanned(detectedBarcode)
                }
                .frame(height: 200)
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            } else {
                // Receipt Review (existing prototype mode)
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(Color(red: 0.10, green: 0.12, blue: 0.11))
                    .frame(height: 200)

                VStack(spacing: 12) {
                    Image(systemName: "doc.text.viewfinder")
                        .font(.system(size: 44))
                        .foregroundStyle(ProvisionTheme.heroCard)

                    Text("Align receipt edges in frame")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Color.white.opacity(0.8))
                }
            }
            
            // Corner Reticles Overlay
            VStack {
                HStack {
                    cornerBracket(top: true, left: true)
                    Spacer()
                    cornerBracket(top: true, left: false)
                }
                Spacer()
                HStack {
                    cornerBracket(top: false, left: true)
                    Spacer()
                    cornerBracket(top: false, left: false)
                }
            }
            .padding(28)
            .frame(height: 200)
            .allowsHitTesting(false)
        }
    }
    
    private func cornerBracket(top: Bool, left: Bool) -> some View {
        Path { path in
            let length: CGFloat = 20
            let startX: CGFloat = left ? 0 : length
            let startY: CGFloat = top ? length : 0
            let cornerX: CGFloat = left ? 0 : length
            let cornerY: CGFloat = top ? 0 : length
            let endX: CGFloat = left ? length : 0
            let endY: CGFloat = top ? 0 : length
            
            path.move(to: CGPoint(x: startX, y: startY))
            path.addLine(to: CGPoint(x: cornerX, y: cornerY))
            path.addLine(to: CGPoint(x: endX, y: endY))
        }
        .stroke(ProvisionTheme.heroCard, lineWidth: 3)
        .frame(width: 20, height: 20)
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
            viewModel.onBarcodeScanned(barcode)
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
                Text("Detected Barcode")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .textCase(.uppercase)
                    .tracking(0.8)

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

    private var intakeReviewSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Intake Review (Simulation)")
                        .font(.system(size: 18, weight: .bold, design: .serif))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    Text("\(viewModel.scannedItems.count) items ready to simulate intake")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                
                Spacer()
                
                Button {
                    showingAddManualSheet = true
                } label: {
                    Text("+ Manual")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.provisionGreen)
                }
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
                VStack(spacing: 10) {
                    ForEach($viewModel.scannedItems) { $item in
                        intakeItemRow(item: $item)
                    }
                }
                
                // Commit Button
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
                            Image(systemName: "checkmark.circle.fill")
                            Text("Simulate Intake (Midterm Prototype)")
                                .font(.system(size: 16, weight: .bold))
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(ProvisionTheme.provisionGreen)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
                .disabled(viewModel.isCommitting)
                .padding(.top, 8)
            }
        }
    }
    
    private func intakeItemRow(item: Binding<ScannedIntakeItem>) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.wrappedValue.name)
                        .font(.system(size: 15, weight: .bold, design: .serif))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                    
                    Text("\(item.wrappedValue.brand ?? "Pantry") • Barcode: \(item.wrappedValue.barcode)")
                        .font(.system(size: 11))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                
                Spacer()
                
                Text(item.wrappedValue.status.rawValue)
                    .font(.system(size: 10, weight: .bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(ProvisionTheme.provisionGreenLight)
                    .foregroundStyle(ProvisionTheme.provisionGreen)
                    .clipShape(Capsule())
            }
            
            Divider()
            
            HStack {
                // Quantity Stepper
                HStack(spacing: 12) {
                    Text("Qty: \(Int(item.wrappedValue.quantity))")
                        .font(.system(size: 13, weight: .semibold))
                    
                    Stepper("", value: item.quantity, in: 1...99, step: 1)
                        .labelsHidden()
                }
                
                Spacer()
                
                // Expiry display
                HStack(spacing: 4) {
                    Image(systemName: "calendar")
                        .font(.system(size: 11))
                    Text(item.wrappedValue.expirationDate, format: .dateTime.month().day().year())
                        .font(.system(size: 12, weight: .medium))
                }
                .foregroundStyle(ProvisionTheme.textSecondary)
            }
        }
        .padding(14)
        .provisionCard()
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
}

#Preview("Intake Scanner") {
    ScanView(viewModel: PreviewData.makeScanViewModel())
}
