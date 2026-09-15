import SwiftUI

public struct AddInventoryView: View {
    @ObservedObject var viewModel: InventoryViewModel
    @Environment(\.dismiss) private var dismiss
    
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
    @State private var newProductPackageSizeStr: String = ""
    
    // Batch Details
    @State private var quantity: Double = 1.0
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
        if let id = initialProductId {
            _mode = State(initialValue: .existing)
            _selectedProductId = State(initialValue: id)
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
                    } else {
                        TextField("Product Name (Required)", text: $newProductName)
                        TextField("Unit (e.g. pcs, cans, kg)", text: $newProductUnit)
                        TextField("Brand (Optional)", text: $newProductBrand)
                        TextField("Category (Optional)", text: $newProductCategory)
                        TextField("Barcode (Optional)", text: $newProductBarcode)
                        TextField("Package Size (Optional)", text: $newProductPackageSizeStr)
                            .keyboardType(.decimalPad)
                    }
                }
                
                Section("Stock Information") {
                    Stepper("Quantity: \(formatQuantity(quantity))", value: $quantity, in: 0.1...1000, step: 1.0)
                    
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
                            Text("Add to Inventory")
                                .font(.system(size: 16, weight: .bold))
                                .frame(maxWidth: .infinity)
                                .foregroundStyle(.white)
                        }
                    }
                    .listRowBackground(ProvisionTheme.provisionGreen)
                    .disabled(isSubmitting || !isFormValid)
                }
            }
            .navigationTitle("Add Inventory")
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
        if mode == .existing {
            return selectedProductId != nil && quantity > 0
        } else {
            return !newProductName.trimmingCharacters(in: .whitespaces).isEmpty && quantity > 0
        }
    }
    
    private func fetchLocations() async {
        isLoadingLocations = true
        do {
            locations = try await APIClient.shared.fetchLocations()
            if let first = locations.first {
                selectedLocationId = first.id
            }
        } catch {
            print("Failed to fetch locations: \(error)")
        }
        isLoadingLocations = false
    }
    
    private func submit() {
        guard isFormValid else { return }
        isSubmitting = true
        errorMessage = nil
        
        Task {
            var newProduct: ProductCreate? = nil
            if mode == .new {
                let pSize = Double(newProductPackageSizeStr.replacingOccurrences(of: ",", with: "."))
                newProduct = ProductCreate(
                    name: newProductName.trimmingCharacters(in: .whitespaces),
                    brand: newProductBrand.isEmpty ? nil : newProductBrand,
                    barcode: newProductBarcode.isEmpty ? nil : newProductBarcode,
                    category: newProductCategory.isEmpty ? nil : newProductCategory,
                    package_size: pSize,
                    unit: newProductUnit.isEmpty ? nil : newProductUnit,
                    source: "manual"
                )
            }
            
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            
            let isoFormatter = ISO8601DateFormatter()
            isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            
            let expStr = trackExpiration ? formatter.string(from: expirationDate) : nil
            let purStr = isoFormatter.string(from: purchaseDate)
            
            let price = Double(unitPriceStr.replacingOccurrences(of: ",", with: "."))
            
            let batchCreate = InventoryBatchCreate(
                product_id: mode == .existing ? (selectedProductId ?? 0) : 0, // 0 is placeholder if new
                storage_location_id: selectedLocationId,
                purchased_at: purStr,
                expiration_date: expStr,
                original_quantity: quantity,
                unit_price: price
            )
            
            let success = await viewModel.createManualInventory(
                product: newProduct,
                productId: mode == .existing ? selectedProductId : nil,
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
    
    private func formatQuantity(_ qty: Double) -> String {
        if qty.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(qty))"
        } else {
            return String(format: "%.1f", qty)
        }
    }
}
