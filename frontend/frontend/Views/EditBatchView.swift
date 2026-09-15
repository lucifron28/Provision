import SwiftUI

public struct EditBatchView: View {
    @ObservedObject var viewModel: InventoryViewModel
    let batch: InventoryBatch
    @Environment(\.dismiss) private var dismiss
    
    @State private var trackExpiration: Bool
    @State private var expirationDate: Date
    @State private var selectedLocationId: Int?
    @State private var unitPriceStr: String
    
    @State private var locations: [StorageLocation] = []
    @State private var isLoadingLocations: Bool = false
    @State private var isSubmitting: Bool = false
    @State private var errorMessage: String?
    
    public init(viewModel: InventoryViewModel, batch: InventoryBatch) {
        self.viewModel = viewModel
        self.batch = batch
        
        // Initialize state from batch
        if let expStr = batch.expiration_date, let date = Self.parseDate(expStr) {
            _trackExpiration = State(initialValue: true)
            _expirationDate = State(initialValue: date)
        } else {
            _trackExpiration = State(initialValue: false)
            _expirationDate = State(initialValue: Date())
        }
        
        _selectedLocationId = State(initialValue: batch.storage_location_id)
        
        if let price = batch.unit_price {
            _unitPriceStr = State(initialValue: String(format: "%.2f", price))
        } else {
            _unitPriceStr = State(initialValue: "")
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
                
                Section("Metadata") {
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
                    .disabled(isSubmitting)
                }
            }
            .navigationTitle("Edit Batch")
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
    
    private func fetchLocations() async {
        isLoadingLocations = true
        do {
            locations = try await APIClient.shared.fetchLocations()
        } catch {
            print("Failed to fetch locations: \(error)")
        }
        isLoadingLocations = false
    }
    
    private func submit() {
        isSubmitting = true
        errorMessage = nil
        
        Task {
            var updates: [String: Any?] = [:]
            
            if trackExpiration {
                let formatter = DateFormatter()
                formatter.dateFormat = "yyyy-MM-dd"
                updates["expiration_date"] = formatter.string(from: expirationDate)
            } else {
                updates["expiration_date"] = nil // This will map to NSNull in APIClient
            }
            
            updates["storage_location_id"] = selectedLocationId
            
            if unitPriceStr.trimmingCharacters(in: .whitespaces).isEmpty {
                updates["unit_price"] = nil
            } else if let price = Double(unitPriceStr.replacingOccurrences(of: ",", with: ".")) {
                updates["unit_price"] = price
            }
            
            let success = await viewModel.updateBatchMetadata(batchId: batch.id, updates: updates)
            if success {
                dismiss()
            } else {
                errorMessage = viewModel.errorMessage
            }
            isSubmitting = false
        }
    }
    
    private static func parseDate(_ str: String) -> Date? {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: str)
    }
}
