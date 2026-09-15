import SwiftUI

public struct ProductDetailView: View {
    @ObservedObject var viewModel: InventoryViewModel
    let product: Product
    @Environment(\.dismiss) private var dismiss
    
    @State private var showingConsumeSheet: Bool = false
    @State private var showingAdjustSheet: Bool = false
    @State private var showingDiscardAlert: Bool = false
    
    @State private var showingAddStockSheet: Bool = false
    @State private var showingEditProductSheet: Bool = false
    @State private var editingBatch: InventoryBatch? = nil
    
    @State private var consumeAmountText: String = "1"
    @State private var consumeReason: String = "Household consumption"
    @State private var consumeErrorMessage: String? = nil
    
    @State private var adjustBatchId: Int = 0
    @State private var adjustAmountText: String = "1"
    @State private var adjustReason: String = "Physical inventory count"
    @State private var adjustErrorMessage: String? = nil
    
    @State private var selectedBatchForDiscard: InventoryBatch? = nil
    
    public init(viewModel: InventoryViewModel, product: Product) {
        self.viewModel = viewModel
        self.product = product
    }
    
    private var currentProduct: Product {
        viewModel.selectedProduct ?? product
    }
    
    private var isUnitValid: Bool {
        ProductUnits.isValid(currentProduct.unit)
    }
    
    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Top Product Summary Card
                productSummaryHeader
                
                // Warning on Invalid Legacy Unit
                if !isUnitValid {
                    invalidUnitWarningCard
                }
                
                // Big Action Buttons (Consume, Discard, Adjust)
                actionButtonsRow
                
                // Batch Data (FEFO list)
                batchDataSection
            }
            .padding(16)
        }
        .background(ProvisionTheme.background.ignoresSafeArea())
        .navigationTitle(currentProduct.barcode != nil ? "SKU: \(currentProduct.barcode!)" : "Product Detail")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.selectProduct(product)
        }
        .sheet(isPresented: $showingConsumeSheet) {
            consumeSheet
        }
        .sheet(isPresented: $showingAddStockSheet) {
            AddInventoryView(viewModel: viewModel, initialProductId: currentProduct.id)
        }
        .sheet(isPresented: $showingEditProductSheet) {
            EditProductView(viewModel: viewModel, product: currentProduct)
        }
        .sheet(item: $editingBatch) { batch in
            EditBatchView(viewModel: viewModel, batch: batch)
        }
        .sheet(isPresented: $showingAdjustSheet) {
            adjustSheet
        }
        .alert("Discard Batch?", isPresented: $showingDiscardAlert) {
            Button("Cancel", role: .cancel) {}
            Button("Discard", role: .destructive) {
                if let batch = selectedBatchForDiscard {
                    Task {
                        _ = await viewModel.discardBatch(batchId: batch.id)
                    }
                }
            }
        } message: {
            if let batch = selectedBatchForDiscard {
                Text("Are you sure you want to discard \(formatQuantity(batch.remaining_quantity)) \(currentProduct.displayUnit) expiring \(batch.displayExpiration)? This will log a waste event.")
            } else {
                Text("Are you sure you want to discard this batch?")
            }
        }
    }
    
    // MARK: - Subviews
    
    private var invalidUnitWarningCard: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 18))
                .foregroundStyle(ProvisionTheme.amberWarning)
            
            VStack(alignment: .leading, spacing: 2) {
                Text("Invalid stock unit: \"\(currentProduct.displayUnit)\"")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                Text("Edit product to correct it before adding stock or consuming.")
                    .font(.system(size: 11))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            
            Spacer()
            
            Button("Edit") {
                showingEditProductSheet = true
            }
            .font(.system(size: 12, weight: .bold))
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(ProvisionTheme.amberWarning)
            .foregroundStyle(.white)
            .clipShape(Capsule())
        }
        .padding(14)
        .provisionCard(borderColor: ProvisionTheme.amberWarning.opacity(0.6))
    }
    
    private var productSummaryHeader: some View {
        HStack(alignment: .top, spacing: 16) {
            // Product Icon Box
            ZStack {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(ProvisionTheme.surfaceSecondary)
                    .frame(width: 80, height: 80)
                Image(systemName: "shippingbox.fill")
                    .font(.system(size: 36))
                    .foregroundStyle(ProvisionTheme.provisionGreen)
            }
            
            VStack(alignment: .leading, spacing: 6) {
                Text(currentProduct.name)
                    .font(.system(size: 22, weight: .bold, design: .serif))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                
                Text(currentProduct.subtitle)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                
                HStack(spacing: 4) {
                    Text("TOTAL STOCK:")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                        .tracking(0.6)
                    
                    Text("\(currentProduct.displayStock) \(currentProduct.displayUnit.uppercased())")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(currentProduct.isOutOfStock ? ProvisionTheme.redAlert : ProvisionTheme.provisionGreen)
                }
                .padding(.top, 4)
                
                HStack(spacing: 8) {
                    Button {
                        showingAddStockSheet = true
                    } label: {
                        Text("+ ADD STOCK")
                            .font(.system(size: 11, weight: .bold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(isUnitValid ? ProvisionTheme.provisionGreen : ProvisionTheme.textTertiary)
                            .foregroundStyle(.white)
                            .clipShape(Capsule())
                    }
                    .disabled(!isUnitValid)
                    
                    Menu {
                        Button {
                            showingEditProductSheet = true
                        } label: {
                            Label("Edit Product", systemImage: "pencil")
                        }
                    } label: {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 13, weight: .bold))
                            .padding(6)
                            .background(ProvisionTheme.surfaceSecondary)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                            .clipShape(Circle())
                    }
                }
                .padding(.top, 4)
            }
            
            Spacer()
        }
        .padding(16)
        .provisionCard()
    }
    
    private var actionButtonsRow: some View {
        HStack(spacing: 10) {
            // Consume Button
            Button {
                consumeAmountText = "1"
                consumeErrorMessage = nil
                showingConsumeSheet = true
            } label: {
                VStack(spacing: 6) {
                    Image(systemName: "minus.circle.fill")
                        .font(.system(size: 18))
                    Text("CONSUME")
                        .font(.system(size: 12, weight: .bold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(currentProduct.isOutOfStock || !isUnitValid ? ProvisionTheme.surfaceSecondary : ProvisionTheme.provisionGreenLight)
                .foregroundStyle(currentProduct.isOutOfStock || !isUnitValid ? ProvisionTheme.textTertiary : ProvisionTheme.provisionGreen)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .disabled(currentProduct.isOutOfStock || !isUnitValid)
            
            // Discard Button
            Button {
                if let earliest = viewModel.productBatches.first {
                    selectedBatchForDiscard = earliest
                    showingDiscardAlert = true
                }
            } label: {
                VStack(spacing: 6) {
                    Image(systemName: "trash.fill")
                        .font(.system(size: 18))
                    Text("DISCARD")
                        .font(.system(size: 12, weight: .bold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(ProvisionTheme.surface)
                .foregroundStyle(ProvisionTheme.redAlert)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
            }
            .disabled(viewModel.productBatches.isEmpty)
            
            // Adjust Button
            Button {
                if let earliest = viewModel.productBatches.first {
                    adjustBatchId = earliest.id
                    adjustAmountText = formatQuantity(earliest.remaining_quantity)
                    adjustErrorMessage = nil
                    showingAdjustSheet = true
                }
            } label: {
                VStack(spacing: 6) {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 18))
                    Text("ADJUST")
                        .font(.system(size: 12, weight: .bold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(ProvisionTheme.surface)
                .foregroundStyle(ProvisionTheme.textPrimary)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(ProvisionTheme.border, lineWidth: 1))
            }
            .disabled(viewModel.productBatches.isEmpty)
        }
    }
    
    private var batchDataSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("BATCH DATA (FEFO)")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textSecondary)
                    .tracking(0.8)
                Spacer()
                Text("\(viewModel.productBatches.count) active batches")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(ProvisionTheme.textTertiary)
            }
            
            if viewModel.isDetailLoading {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding()
            } else if viewModel.productBatches.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "tray")
                        .font(.system(size: 32))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text("No active batches in stock")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
                .frame(maxWidth: .infinity)
                .padding(32)
                .provisionCard()
            } else {
                // First Batch is "Use First"
                if let firstBatch = viewModel.productBatches.first {
                    useFirstBatchCard(batch: firstBatch)
                }
                
                // Rest of batches
                if viewModel.productBatches.count > 1 {
                    Text("REST OF STOCK")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                        .tracking(0.6)
                        .padding(.top, 6)
                    
                    VStack(spacing: 8) {
                        ForEach(viewModel.productBatches.dropFirst()) { batch in
                            batchRow(batch: batch)
                        }
                    }
                }
            }
        }
    }
    
    private func useFirstBatchCard(batch: InventoryBatch) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 11))
                    Text("USE FIRST")
                        .font(.system(size: 11, weight: .heavy))
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(ProvisionTheme.amberLight)
                .foregroundStyle(ProvisionTheme.amberWarning)
                .clipShape(Capsule())
                
                Spacer()
                
                Text("\(formatQuantity(batch.remaining_quantity)) \(currentProduct.displayUnit)")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                
                Menu {
                    Button {
                        editingBatch = batch
                    } label: {
                        Label("Edit Batch", systemImage: "pencil")
                    }
                    
                    Button {
                        adjustBatchId = batch.id
                        adjustAmountText = formatQuantity(batch.remaining_quantity)
                        adjustErrorMessage = nil
                        showingAdjustSheet = true
                    } label: {
                        Label("Adjust Quantity", systemImage: "slider.horizontal.3")
                    }
                    
                    Button(role: .destructive) {
                        selectedBatchForDiscard = batch
                        showingDiscardAlert = true
                    } label: {
                        Label("Discard Batch", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 14))
                        .padding(4)
                        .foregroundStyle(ProvisionTheme.textSecondary)
                }
            }
            
            Divider()
            
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("EXPIRATION")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text(batch.displayExpiration.uppercased())
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(batch.isExpired ? ProvisionTheme.redAlert : ProvisionTheme.textPrimary)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 2) {
                    Text("LOCATION")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text(batch.storage_location?.name.uppercased() ?? "PANTRY")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
            }
        }
        .padding(16)
        .provisionCard(borderColor: ProvisionTheme.amberWarning.opacity(0.5))
    }
    
    private func batchRow(batch: InventoryBatch) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Image(systemName: "calendar")
                        .font(.system(size: 12))
                        .foregroundStyle(ProvisionTheme.textTertiary)
                    Text(batch.displayExpiration)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(ProvisionTheme.textPrimary)
                }
                
                Text(batch.storage_location?.name ?? "General Storage")
                    .font(.system(size: 12))
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
            
            Spacer()
            
            Text("\(formatQuantity(batch.remaining_quantity)) \(currentProduct.displayUnit)")
                .font(.system(size: 15, weight: .bold))
                .foregroundStyle(ProvisionTheme.textPrimary)
            
            Menu {
                Button(role: .destructive) {
                    selectedBatchForDiscard = batch
                    showingDiscardAlert = true
                } label: {
                    Label("Discard Batch", systemImage: "trash")
                }
                
                Button {
                    editingBatch = batch
                } label: {
                    Label("Edit Batch", systemImage: "pencil")
                }
                
                Button {
                    adjustBatchId = batch.id
                    adjustAmountText = formatQuantity(batch.remaining_quantity)
                    adjustErrorMessage = nil
                    showingAdjustSheet = true
                } label: {
                    Label("Adjust Quantity", systemImage: "slider.horizontal.3")
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 14))
                    .padding(8)
                    .foregroundStyle(ProvisionTheme.textSecondary)
            }
        }
        .padding(14)
        .provisionCard()
    }
    
    // MARK: - Sheets
    
    private var consumeSheet: some View {
        NavigationStack {
            VStack(spacing: 24) {
                VStack(spacing: 8) {
                    Text("Consume \(currentProduct.name)")
                        .font(.system(size: 20, weight: .bold, design: .serif))
                    Text("Units will automatically be deducted First Expired First Out (FEFO)")
                        .font(.system(size: 13))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.top, 16)
                
                if let err = consumeErrorMessage {
                    Text(err)
                        .font(.system(size: 13))
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }
                
                VStack(spacing: 12) {
                    HStack {
                        Text("Amount")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                        Spacer()
                        TextField("0", text: $consumeAmountText)
                            .keyboardType(ProductUnits.isMeasured(currentProduct.unit) ? .decimalPad : .numberPad)
                            .font(.system(size: 36, weight: .bold, design: .serif))
                            .multilineTextAlignment(.trailing)
                        Text(currentProduct.displayUnit)
                            .font(.system(size: 20, weight: .bold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                    }
                    
                    if ProductUnits.isValid(currentProduct.unit) && ProductUnits.isCount(currentProduct.unit) {
                        Stepper("", onIncrement: {
                            let cur = Int(Double(consumeAmountText.replacingOccurrences(of: ",", with: ".")) ?? 0)
                            let maxVal = Int(currentProduct.total_remaining_quantity ?? 1000)
                            if cur < maxVal {
                                consumeAmountText = "\(cur + 1)"
                            }
                        }, onDecrement: {
                            let cur = Int(Double(consumeAmountText.replacingOccurrences(of: ",", with: ".")) ?? 1)
                            if cur > 1 {
                                consumeAmountText = "\(cur - 1)"
                            }
                        })
                        .labelsHidden()
                    }
                }
                .padding(20)
                .frame(maxWidth: .infinity)
                .provisionCard()
                
                VStack(alignment: .leading, spacing: 8) {
                    Text("Reason")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.textSecondary)
                    
                    TextField("Reason", text: $consumeReason)
                        .textFieldStyle(.roundedBorder)
                }
                
                Spacer()
                
                Button {
                    consumeErrorMessage = nil
                    let parsed = Double(consumeAmountText.replacingOccurrences(of: ",", with: "."))
                    guard let amount = parsed, amount > 0 else {
                        consumeErrorMessage = "Please enter a valid amount."
                        return
                    }
                    let maxAvailable = currentProduct.total_remaining_quantity ?? 0
                    guard amount <= maxAvailable else {
                        consumeErrorMessage = "Cannot consume more than available stock (\(formatQuantity(maxAvailable)) \(currentProduct.displayUnit))."
                        return
                    }
                    if ProductUnits.isValid(currentProduct.unit) && ProductUnits.isCount(currentProduct.unit) && floor(amount) != amount {
                        consumeErrorMessage = "Enter a whole number for this unit."
                        return
                    }
                    
                    Task {
                        let success = await viewModel.consumeProduct(
                            productId: currentProduct.id,
                            quantity: amount,
                            reason: consumeReason
                        )
                        if success {
                            showingConsumeSheet = false
                        } else {
                            consumeErrorMessage = viewModel.errorMessage
                        }
                    }
                } label: {
                    Text("Confirm Consumption")
                        .font(.system(size: 16, weight: .bold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(ProvisionTheme.provisionGreen)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(20)
            .background(ProvisionTheme.background.ignoresSafeArea())
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showingConsumeSheet = false }
                }
            }
        }
        .presentationDetents([.medium])
    }
    
    private var adjustSheet: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text("Adjust Batch Stock")
                    .font(.system(size: 20, weight: .bold, design: .serif))
                    .padding(.top, 16)
                
                if let err = adjustErrorMessage {
                    Text(err)
                        .font(.system(size: 13))
                        .foregroundStyle(ProvisionTheme.redAlert)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }
                
                VStack(spacing: 12) {
                    HStack {
                        Text("Amount")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.textSecondary)
                        Spacer()
                        TextField("0", text: $adjustAmountText)
                            .keyboardType(ProductUnits.isMeasured(currentProduct.unit) ? .decimalPad : .numberPad)
                            .font(.system(size: 36, weight: .bold, design: .serif))
                            .multilineTextAlignment(.trailing)
                        Text(currentProduct.displayUnit)
                            .font(.system(size: 20, weight: .bold))
                            .foregroundStyle(ProvisionTheme.textPrimary)
                    }
                    
                    if ProductUnits.isValid(currentProduct.unit) && ProductUnits.isCount(currentProduct.unit) {
                        Stepper("", onIncrement: {
                            let cur = Int(Double(adjustAmountText.replacingOccurrences(of: ",", with: ".")) ?? 0)
                            adjustAmountText = "\(cur + 1)"
                        }, onDecrement: {
                            let cur = Int(Double(adjustAmountText.replacingOccurrences(of: ",", with: ".")) ?? 1)
                            if cur > 0 {
                                adjustAmountText = "\(cur - 1)"
                            }
                        })
                        .labelsHidden()
                    }
                }
                .padding()
                .frame(maxWidth: .infinity)
                .provisionCard()
                
                TextField("Adjustment Reason", text: $adjustReason)
                    .textFieldStyle(.roundedBorder)
                
                Spacer()
                
                Button {
                    adjustErrorMessage = nil
                    let parsed = Double(adjustAmountText.replacingOccurrences(of: ",", with: "."))
                    guard let newAmount = parsed, newAmount >= 0 else {
                        adjustErrorMessage = "Please enter a valid amount."
                        return
                    }
                    if ProductUnits.isValid(currentProduct.unit) && ProductUnits.isCount(currentProduct.unit) && floor(newAmount) != newAmount {
                        adjustErrorMessage = "Enter a whole number for this unit."
                        return
                    }
                    
                    Task {
                        let success = await viewModel.adjustBatch(
                            batchId: adjustBatchId,
                            newQuantity: newAmount,
                            reason: adjustReason
                        )
                        if success {
                            showingAdjustSheet = false
                        } else {
                            adjustErrorMessage = viewModel.errorMessage
                        }
                    }
                } label: {
                    Text("Save Adjustment")
                        .font(.system(size: 16, weight: .bold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(ProvisionTheme.provisionGreen)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(20)
            .background(ProvisionTheme.background.ignoresSafeArea())
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showingAdjustSheet = false }
                }
            }
        }
        .presentationDetents([.medium])
    }
    
    private func formatQuantity(_ qty: Double) -> String {
        ProductUnits.formatAmount(qty)
    }
}
