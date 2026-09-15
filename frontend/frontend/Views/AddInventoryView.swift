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
    
    // Product Details (New)
    @State private var newProductName: String = ""
    @State private var newProductUnit: String = "pcs"
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
    
    @State private var locations: [StorageLocation] = []
    @State private var isLoadingLocations: Bool = false
    @State private var isSubmitting: Bool = false
    @State private var errorMessage: String?
    
    public init(viewModel: InventoryViewModel, initialProductId: Int? = nil) {
        self.viewModel = viewModel
        self.isRestockMode = initialProductId != nil
        if let id = initialProductId {
            _mode = State(initialValue: .existing)
            _selectedProductId = State(initialValue: id)
        }
    }
    
    private var currentUnit: String {
        if isRestockMode || mode == .existing {
            if let pid = selectedProductId, let prod = viewModel.products.first(where: { $0.id == pid }) {
                return prod.displayUnit
            }
            return "pcs"
        } else {
            return newProductUnit
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
                    Section("Product Source") {
                        Picker("Mode", selection: $mode) {
                            Text("Select Existing").tag(Mode.existing)
                            Text("Create New").tag(Mode.new)
                        }
                        .pickerStyle(.segmented)
                        
                        if mode == .existing {
                            Picker("Product", selection: $selectedProductId) {
                                Text("Select a Product").tag(Int?.none)
                                ForEach(viewModel.products) { p in
                                    Text("\(p.name) \(p.brand != nil ? "(\(p.brand!))" : "")").tag(Int?.some(p.id))
                                }
                            }
                            
                            if selectedProductId != nil {
                                HStack {
                                    Text("Unit")
                                    Spacer()
                                    Text(currentUnit)
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                }
                            }
                        } else {
                            TextField("Product Name (Required)", text: $newProductName)
                            
                            Picker("Unit", selection: $newProductUnit) {
                                ForEach(ProductUnits.allUnits, id: \.self) { u in
                                    Text(u).tag(u)
                                }
                            }
                            
                            TextField("Brand (Optional)", text: $newProductBrand)
                            TextField("Category (Optional)", text: $newProductCategory)
                            TextField("Barcode (Optional)", text: $newProductBarcode)
                        }
                    }
                }
                
                Section("Stock Information") {
                    HStack {
                        Text("Amount")
                        Spacer()
                        TextField(ProductUnits.isMeasured(currentUnit) ? "e.g. 1.5" : "e.g. 1", text: $amountText)
                            .keyboardType(ProductUnits.isMeasured(currentUnit) ? .decimalPad : .numberPad)
                            .multilineTextAlignment(.trailing)
                        Text(currentUnit)
                            .foregroundStyle(ProvisionTheme.textSecondary)
                    }
                    
                    Toggle("Track Expiration", isOn: $trackExpiration)
                    if trackExpiration {
                        DatePicker("Expiration Date", selection: $expirationDate, displayedComponents: .date)
                    }
                    
                    if isLoadingLocations {
                        ProgressView("Loading locations...")
                    } else if !locations.isEmpty {
                        Picker("Storage Location", selection: $selectedLocationId) {
                            Text("None").tag(Int?.none)
                            ForEach(locations) { loc in
                                Text(loc.name).tag(Int?.some(loc.id))
                            }
                        }
                    }
                    
                    HStack {
                        Text("Unit Price (₱)")
                        Spacer()
                        TextField("Optional", text: $unitPriceStr)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                    }
                    
                    DatePicker("Purchase Date", selection: $purchaseDate, displayedComponents: .date)
                }
                
                Section {
                    Button {
                        submit()
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text(isRestockMode ? "Add Stock" : "Add to Inventory")
                                .font(.system(size: 16, weight: .bold))
                                .frame(maxWidth: .infinity)
                                .foregroundStyle(.white)
                        }
                    }
                    .listRowBackground(ProvisionTheme.provisionGreen)
                    .disabled(isSubmitting || !isFormValid)
                }
            }
            .navigationTitle(isRestockMode ? "Add Stock" : "Add Inventory")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .task {
                await fetchLocations()
            }
        }
    }
    
    private var isFormValid: Bool {
        let parsedQty = Double(amountText.replacingOccurrences(of: ",", with: "."))
        guard let qty = parsedQty, qty > 0 else { return false }
        
        if isRestockMode || mode == .existing {
            return selectedProductId != nil
        } else {
            return !newProductName.trimmingCharacters(in: .whitespaces).isEmpty && !newProductUnit.trimmingCharacters(in: .whitespaces).isEmpty
        }
    }
    
    private func fetchLocations() async {
        isLoadingLocations = true
        do {
            locations = try await APIClient.shared.fetchLocations()
            if let first = locations.first, selectedLocationId == nil {
                selectedLocationId = first.id
            }
        } catch {
            errorMessage = "Could not load storage locations."
        }
        isLoadingLocations = false
    }
    
    private func submit() {
        errorMessage = nil
        let parsedQty = Double(amountText.replacingOccurrences(of: ",", with: "."))
        guard let qty = parsedQty, qty > 0 else {
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
            guard let p = Double(trimmedPrice.replacingOccurrences(of: ",", with: ".")), p >= 0 else {
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
