import SwiftUI

public struct EditProductView: View {
    @ObservedObject var viewModel: InventoryViewModel
    let product: Product
    @Environment(\.dismiss) private var dismiss
    
    @State private var name: String
    @State private var unit: String
    @State private var brand: String
    @State private var category: String
    @State private var barcode: String
    
    @State private var isSubmitting: Bool = false
    @State private var errorMessage: String?
    
    public init(viewModel: InventoryViewModel, product: Product) {
        self.viewModel = viewModel
        self.product = product
        
        _name = State(initialValue: product.name)
        
        // Match existing unit if valid, otherwise pick a sensible default
        let initialUnit: String
        if let u = product.unit, ProductUnits.allUnits.contains(u) {
            initialUnit = u
        } else if let u = product.unit, u.lowercased().contains("kg") {
            initialUnit = "kg"
        } else if let u = product.unit, u.lowercased().contains("l") {
            initialUnit = "L"
        } else if let u = product.unit, u.lowercased().contains("g") {
            initialUnit = "g"
        } else {
            initialUnit = "pcs"
        }
        _unit = State(initialValue: initialUnit)
        
        _brand = State(initialValue: product.brand ?? "")
        _category = State(initialValue: product.category ?? "")
        _barcode = State(initialValue: product.barcode ?? "")
    }
    
    public var body: some View {
        NavigationStack {
            Form {
                if let err = errorMessage {
                    Section {
                        Text(err).foregroundColor(ProvisionTheme.redAlert)
                    }
                }
                
                Section("Product Details") {
                    TextField("Product Name (Required)", text: $name)
                    
                    Picker("Unit", selection: $unit) {
                        ForEach(ProductUnits.allUnits, id: \.self) { u in
                            Text(u).tag(u)
                        }
                    }
                    
                    TextField("Brand (Optional)", text: $brand)
                    TextField("Category (Optional)", text: $category)
                    TextField("Barcode (Optional)", text: $barcode)
                }
                
                Section {
                    Button {
                        submit()
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("Save Changes")
                                .font(.system(size: 16, weight: .bold))
                                .frame(maxWidth: .infinity)
                                .foregroundStyle(.white)
                        }
                    }
                    .listRowBackground(ProvisionTheme.provisionGreen)
                    .disabled(isSubmitting || name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .navigationTitle("Edit Product")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
    
    private func submit() {
        let trimmedName = name.trimmingCharacters(in: .whitespaces)
        guard !trimmedName.isEmpty else {
            errorMessage = "Product name is required."
            return
        }
        guard ProductUnits.allUnits.contains(unit) else {
            errorMessage = "Please select a valid unit."
            return
        }
        
        isSubmitting = true
        errorMessage = nil
        
        let trimmedBrand = brand.trimmingCharacters(in: .whitespaces)
        let trimmedCategory = category.trimmingCharacters(in: .whitespaces)
        let trimmedBarcode = barcode.trimmingCharacters(in: .whitespaces)
        
        let update = ProductUpdate(
            name: trimmedName,
            brand: trimmedBrand.isEmpty ? nil : trimmedBrand,
            barcode: trimmedBarcode.isEmpty ? nil : trimmedBarcode,
            category: trimmedCategory.isEmpty ? nil : trimmedCategory,
            unit: unit
        )
        
        Task {
            let success = await viewModel.updateProductMetadata(productId: product.id, update: update)
            if success {
                dismiss()
            } else {
                errorMessage = viewModel.errorMessage
            }
            isSubmitting = false
        }
    }
}
