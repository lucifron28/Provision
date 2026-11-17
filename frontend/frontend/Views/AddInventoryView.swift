import SwiftUI

public struct AddInventoryView: View {
    @ObservedObject var viewModel: InventoryViewModel
    @Environment(\.dismiss) private var dismiss
    
    let isRestockMode: Bool
    
    // Mode
    enum Mode { case existing, new }
    @State private var mode: Mode = .existing
    
    // Product Selection (Existing)
    @State private var selectedProductId: Int?
    @State private var recentlyUsedProductIDs: [Int] = []
    @State private var showingProductDetails = false
    @State private var showingOptionalDetails = false
    
    // Product Details (New)
    @State private var newProductName: String = ""
    @State private var newProductUnit: String = ""
    @State private var newProductBrand: String = ""
    @State private var newProductCategory: String = ""
    @State private var newProductBarcode: String = ""
    
    // Batch Details
    @State private var amountText: String = "1"
    @State private var trackExpiration: Bool = false
    @State private var expirationDate: Date = Date()
    @State private var purchaseDate: Date = Date()
    @State private var unitPriceStr: String = ""
    @State private var selectedLocationId: Int?
    @State private var showingExpirationOCRSheet: Bool = false
    @State private var locations: [StorageLocation] = []
    @State private var isLoadingLocations: Bool = false
    @State private var isSubmitting: Bool = false
    @State private var errorMessage: String?
    
    public init(viewModel: InventoryViewModel, initialProductId: Int? = nil,
                startWithNewProduct: Bool = false) {
        self.viewModel = viewModel
        self.isRestockMode = initialProductId != nil
        if let id = initialProductId {
            _mode = State(initialValue: .existing)
            _selectedProductId = State(initialValue: id)
        } else if startWithNewProduct {
            _mode = State(initialValue: .new)
        }
    }
    
    private var currentUnit: String {
        if isRestockMode || mode == .existing {
            if let pid = selectedProductId, let prod = viewModel.products.first(where: { $0.id == pid }) {
                return prod.displayUnit
            }
            return "pcs"
        } else {
            return newProductUnit.isEmpty ? "unit" : newProductUnit
        }
    }
    
    public var body: some View {
        NavigationStack {
            Form {
                if let err = errorMessage {
                    Section {
                        Text(err).foregroundColor(ProvisionTheme.redAlert)
                    }
                }
                if let pending = viewModel.pendingManualIntakeRecord {
                    pendingRecoverySection(pending)
                } else if viewModel.pendingManualIntakeState == .corrupt {
                    Section("Saved inventory request") {
                        Text("A saved request could not be read. No new inventory request can be sent from this device until it is recovered.")
                            .foregroundStyle(ProvisionTheme.amberWarning)
                    }
                } else if viewModel.pendingManualIntakeState == .unavailable {
                    Section("Saved inventory request") {
                        Text("This device could not check its saved request. No new inventory request was sent.")
                            .foregroundStyle(ProvisionTheme.amberWarning)
                    }
                } else {
                if isRestockMode {
                    Section("Product") {
                        if let prod = viewModel.products.first(where: { $0.id == selectedProductId }) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(prod.name)
                                    .font(.system(size: 17, weight: .bold, design: .serif))
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                if let brand = prod.brand, !brand.isEmpty {
                                    Text(brand)
                                        .font(.system(size: 13))
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                }
                            }
                            .padding(.vertical, 2)
                        } else {
                            Text("Selected Product")
                                .font(.system(size: 15, weight: .medium))
                        }
                        
                        HStack {
                            Text("Unit")
                            Spacer()
                            Text(currentUnit)
                                .foregroundStyle(ProvisionTheme.textSecondary)
                        }
                    }
                } else {
                    Section {
                        Picker("Mode", selection: $mode) {
                            Label("Catalog Item", systemImage: "books.vertical.fill").tag(Mode.existing)
                            Label("New Item", systemImage: "plus.square.fill").tag(Mode.new)
                        }
                        .pickerStyle(.segmented)
                        .padding(.vertical, 4)
                        .accessibilityIdentifier("inventory-add-mode-picker")
                        
                        if mode == .existing {
                            if viewModel.products.isEmpty {
                                HStack(spacing: 8) {
                                    Image(systemName: "info.circle.fill")
                                        .foregroundStyle(ProvisionTheme.amberWarning)
                                    Text("No registered catalog products found. Select 'New Item' above to register a product.")
                                        .font(.system(size: 13))
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                }
                                .padding(.vertical, 4)
                            } else {
                                SearchableProductSelector(
                                    products: viewModel.products,
                                    selectedProductId: $selectedProductId,
                                    placeholder: "Search catalog by name, brand, or barcode...",
                                    recentlyUsedProductIDs: recentlyUsedProductIDs
                                )
                                
                                if let selectedId = selectedProductId, let p = viewModel.products.first(where: { $0.id == selectedId }) {
                                    HStack {
                                        Text("Unit")
                                            .foregroundStyle(ProvisionTheme.textSecondary)
                                        Spacer()
                                        Text(currentUnit)
                                            .fontWeight(.semibold)
                                            .foregroundStyle(ProvisionTheme.provisionGreen)
                                    }
                                    
                                    if let cat = p.category, !cat.isEmpty {
                                        HStack {
                                            Text("Category")
                                                .foregroundStyle(ProvisionTheme.textSecondary)
                                            Spacer()
                                            Text(cat)
                                                .foregroundStyle(ProvisionTheme.textPrimary)
                                        }
                                    }
                                }
                            }
                        } else {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Product Name *")
                                    .font(.system(size: 11, weight: .bold))
                                    .foregroundStyle(ProvisionTheme.textSecondary)
                                TextField("e.g. Jasmine Rice", text: $newProductName)
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                    .tint(ProvisionTheme.provisionGreen)
                                    .accessibilityIdentifier("inventory-add-product-name")
                            }
                            .padding(.vertical, 2)
                            
                            Picker("Unit", selection: $newProductUnit) {
                                Text("Choose unit").tag("")
                                ForEach(ProductUnits.allUnits, id: \.self) { u in
                                    Text(u).tag(u)
                                }
                            }
                            .pickerStyle(.menu)
                            .tint(ProvisionTheme.provisionGreen)
                            .accessibilityIdentifier("inventory-add-unit-picker")
                            
                            DisclosureGroup("Product details (optional)", isExpanded: $showingProductDetails) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Brand")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                    TextField("e.g. Royal Umbrella", text: $newProductBrand)
                                        .foregroundStyle(ProvisionTheme.textPrimary)
                                        .tint(ProvisionTheme.provisionGreen)
                                }
                                .padding(.vertical, 2)

                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Category")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                    TextField("e.g. Grains & Rice", text: $newProductCategory)
                                        .foregroundStyle(ProvisionTheme.textPrimary)
                                        .tint(ProvisionTheme.provisionGreen)
                                }
                                .padding(.vertical, 2)

                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Barcode")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                    TextField("Enter barcode", text: $newProductBarcode)
                                        .keyboardType(.numberPad)
                                        .foregroundStyle(ProvisionTheme.textPrimary)
                                        .tint(ProvisionTheme.provisionGreen)
                                }
                                .padding(.vertical, 2)
                            }
                            .accessibilityIdentifier("inventory-add-product-details")
                        }
                    } header: {
                        Text(mode == .existing ? "Catalog Selection" : "New Product Specification")
                    }
                }
                
                Section("Quantity") {
                    HStack {
                        Text("Amount")
                            .foregroundStyle(ProvisionTheme.textPrimary)
                        Spacer()
                        TextField(ProductUnits.isMeasured(currentUnit) ? "e.g. 1.5" : "e.g. 1", text: $amountText)
                            .keyboardType(ProductUnits.isMeasured(currentUnit) ? .decimalPad : .numberPad)
                            .multilineTextAlignment(.trailing)
                            .foregroundStyle(ProvisionTheme.textPrimary)
                            .tint(ProvisionTheme.provisionGreen)
                            .accessibilityIdentifier("inventory-add-quantity")
                        Text(currentUnit)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                }

                Section {
                    DisclosureGroup("Optional details", isExpanded: $showingOptionalDetails) {
                    Toggle("Track Expiration", isOn: $trackExpiration)
                        .tint(ProvisionTheme.provisionGreen)
                    
                    if trackExpiration {
                        HStack {
                            DatePicker("Expiration Date", selection: $expirationDate, displayedComponents: .date)
                                .tint(ProvisionTheme.provisionGreen)
                            
                            Button {
                                showingExpirationOCRSheet = true
                            } label: {
                                HStack(spacing: 4) {
                                    Image(systemName: "camera.viewfinder")
                                        .font(.system(size: 14, weight: .semibold))
                                    Text("Scan")
                                        .font(.system(size: 12, weight: .bold))
                                }
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 6)
                                .background(ProvisionTheme.provisionGreenLight)
                                .clipShape(Capsule())
                            }
                            .buttonStyle(.borderless)
                            .accessibleTouchTarget()
                        }
                    }
                    
                    if isLoadingLocations {
                        ProgressView("Loading locations...")
                    } else if !locations.isEmpty {
                        Picker("Storage Location", selection: $selectedLocationId) {
                            Text("No location").tag(Int?.none)
                            ForEach(locations) { loc in
                                Text(loc.name).tag(Int?.some(loc.id))
                            }
                        }
                        .tint(ProvisionTheme.provisionGreen)
                    } else {
                        Text("Storage location is optional. You can add one later.")
                            .font(.footnote)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    
                    HStack {
                        Text("Unit Price (₱)")
                            .foregroundStyle(ProvisionTheme.textPrimary)
                        Spacer()
                        TextField("Optional", text: $unitPriceStr)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .foregroundStyle(ProvisionTheme.textPrimary)
                            .tint(ProvisionTheme.provisionGreen)
                    }
                    
                    DatePicker("Purchase Date", selection: $purchaseDate, displayedComponents: .date)
                        .tint(ProvisionTheme.provisionGreen)
                    }
                    .accessibilityIdentifier("inventory-add-optional-details")
                }
                
                Section {
                    Button {
                        submit()
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .tint(.white)
                                .frame(maxWidth: .infinity, minHeight: 48)
                        } else {
                            Text(isRestockMode ? "Add Stock" : "Add to Inventory")
                                .font(.system(size: 16, weight: .bold))
                                .frame(maxWidth: .infinity, minHeight: 48)
                                .foregroundStyle(ProvisionTheme.onAccent)
                        }
                    }
                    .listRowBackground(isFormValid && !isSubmitting ? ProvisionTheme.provisionGreen : ProvisionTheme.provisionGreen.opacity(0.4))
                    .disabled(isSubmitting || !isFormValid)
                    .accessibilityIdentifier("inventory-add-submit")
                }
                }
            }
            .scrollContentBackground(.hidden)
            .background(ProvisionTheme.background.ignoresSafeArea())
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle(isRestockMode ? "Add Stock" : "Add Inventory")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .task {
                viewModel.loadPendingManualInventoryIntake()
                if let scope = viewModel.scope {
                    recentlyUsedProductIDs = await LocalCacheStore.shared.loadRecentlyUsedProductIDs(scope: scope)
                }
                await fetchLocations()
            }
            .sheet(isPresented: $showingExpirationOCRSheet) {
                ExpirationDateScannerSheet(
                    title: "Scan Package Date",
                    initialDate: trackExpiration ? expirationDate : nil
                ) { (scannedDate: Date?) in
                    if let scannedDate {
                        expirationDate = scannedDate
                        trackExpiration = true
                    } else {
                        trackExpiration = false
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func pendingRecoverySection(_ record: PendingManualInventoryIntakeRecord) -> some View {
        Section("Saved inventory request") {
            let product = viewModel.products.first(where: { $0.id == record.request.product_id })
            let name = record.request.new_product?.name ?? product?.name ?? "Existing product"
            let unit = record.request.new_product?.unit ?? product?.displayUnit ?? "units"
            Text("\(name) · \(ProductUnits.formatAmount(record.request.quantity)) \(unit)")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(ProvisionTheme.textPrimary)
            Text("The server may already have added this item. Retry the saved request unchanged to confirm the result safely.")
                .font(.footnote)
                .foregroundStyle(ProvisionTheme.textSecondary)
            Button {
                Task {
                    isSubmitting = true
                    let succeeded = await viewModel.retryPendingManualInventoryIntake()
                    errorMessage = viewModel.errorMessage
                    isSubmitting = false
                    if succeeded { dismiss() }
                }
            } label: {
                Text("Retry saved request")
                    .font(.system(size: 16, weight: .bold))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(ProvisionTheme.onAccent)
            }
            .listRowBackground(ProvisionTheme.provisionGreen)
            .disabled(isSubmitting)
            .accessibilityIdentifier("inventory-retry-saved-intake")
        }
    }
    
    private var isFormValid: Bool {
        let parsedQty = Double(amountText.replacingOccurrences(of: ",", with: "."))
        guard let qty = parsedQty, qty > 0, qty <= 99_999_999.99,
              decimalPlaces(amountText) <= 2 else { return false }
        
        if isRestockMode || mode == .existing {
            return selectedProductId != nil
        } else {
            return !newProductName.trimmingCharacters(in: .whitespaces).isEmpty
                && !newProductUnit.trimmingCharacters(in: .whitespaces).isEmpty
        }
    }
    
    private func fetchLocations() async {
        if !viewModel.locations.isEmpty {
            self.locations = viewModel.locations
            return
        }
        if viewModel.isPreview { return }
        isLoadingLocations = true
        do {
            locations = try await APIClient.shared.fetchLocations(expectedScope: viewModel.scope)
        } catch {
            errorMessage = "Could not load storage locations."
        }
        isLoadingLocations = false
    }

    private func decimalPlaces(_ value: String) -> Int {
        let normalized = value.replacingOccurrences(of: ",", with: ".")
        guard let separator = normalized.firstIndex(of: ".") else { return 0 }
        return normalized[normalized.index(after: separator)...].count
    }

    private func submit() {
        guard !isSubmitting else { return }
        errorMessage = nil
        let parsedQty = Double(amountText.replacingOccurrences(of: ",", with: "."))
        guard let qty = parsedQty, qty > 0, qty <= 99_999_999.99,
              decimalPlaces(amountText) <= 2 else {
            errorMessage = "Please enter a valid amount greater than zero."
            return
        }
        
        if ProductUnits.isCount(currentUnit) && floor(qty) != qty {
            errorMessage = "Enter a whole number for this unit."
            return
        }
        
        let trimmedPrice = unitPriceStr.trimmingCharacters(in: .whitespaces)
        var price: Double? = nil
        if !trimmedPrice.isEmpty {
            guard let p = Double(trimmedPrice.replacingOccurrences(of: ",", with: ".")),
                  p >= 0, p <= 99_999_999.99, decimalPlaces(trimmedPrice) <= 2 else {
                errorMessage = "Enter a valid price."
                return
            }
            price = p
        }
        
        guard isFormValid else { return }
        isSubmitting = true
        
        Task {
            var newProduct: ProductCreate? = nil
            if !isRestockMode && mode == .new {
                newProduct = ProductCreate(
                    name: newProductName.trimmingCharacters(in: .whitespaces),
                    brand: newProductBrand.isEmpty ? nil : newProductBrand,
                    barcode: newProductBarcode.isEmpty ? nil : newProductBarcode,
                    category: newProductCategory.isEmpty ? nil : newProductCategory,
                    package_size: nil,
                    unit: newProductUnit
                )
            }
            
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            
            let isoFormatter = ISO8601DateFormatter()
            isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            
            let expStr = trackExpiration ? formatter.string(from: expirationDate) : nil
            let purStr = isoFormatter.string(from: purchaseDate)
            
            let batchCreate = InventoryBatchCreate(
                product_id: (isRestockMode || mode == .existing) ? (selectedProductId ?? 0) : 0,
                storage_location_id: selectedLocationId,
                purchased_at: purStr,
                expiration_date: expStr,
                original_quantity: qty,
                unit_price: price
            )
            
            let success = await viewModel.createManualInventory(
                product: newProduct,
                productId: (isRestockMode || mode == .existing) ? selectedProductId : nil,
                batch: batchCreate
            )
            
            if success {
                dismiss()
            } else {
                errorMessage = viewModel.errorMessage
            }
            
            isSubmitting = false
        }
    }
}
