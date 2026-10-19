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
    @State private var showingExpirationOCRSheet: Bool = false
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
                            Text("None").tag(Int?.none)
                            ForEach(locations) { loc in
                                Text(loc.name).tag(Int?.some(loc.id))
                            }
                        }
                        .tint(ProvisionTheme.provisionGreen)
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
                            Text("Save Changes")
                                .font(.system(size: 16, weight: .bold))
                                .frame(maxWidth: .infinity, minHeight: 48)
                                .foregroundStyle(.white)
                        }
                    }
                    .listRowBackground(isSubmitting ? ProvisionTheme.provisionGreen.opacity(0.4) : ProvisionTheme.provisionGreen)
                    .disabled(isSubmitting)
                }
            }
            .scrollContentBackground(.hidden)
            .background(ProvisionTheme.background.ignoresSafeArea())
            .scrollDismissesKeyboard(.interactively)
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
    
    private func fetchLocations() async {
        if !viewModel.locations.isEmpty {
            self.locations = viewModel.locations
            return
        }
        if viewModel.isPreview { return }
        isLoadingLocations = true
        do {
            locations = try await APIClient.shared.fetchLocations()
        } catch {
            errorMessage = "Could not load storage locations."
        }
        isLoadingLocations = false
    }
    
    private func submit() {
        let trimmedPrice = unitPriceStr.trimmingCharacters(in: .whitespaces)
        var parsedPrice: Double? = nil
        if !trimmedPrice.isEmpty {
            guard let p = Double(trimmedPrice.replacingOccurrences(of: ",", with: ".")), p >= 0 else {
                errorMessage = "Enter a valid price."
                return
            }
            parsedPrice = p
        }
        
        isSubmitting = true
        errorMessage = nil
        
        Task {
            var updates: [String: Any] = [:]
            
            if trackExpiration {
                let formatter = DateFormatter()
                formatter.dateFormat = "yyyy-MM-dd"
                updates["expiration_date"] = formatter.string(from: expirationDate)
            } else {
                updates["expiration_date"] = NSNull()
            }
            
            if let locationId = selectedLocationId {
                updates["storage_location_id"] = locationId
            } else {
                updates["storage_location_id"] = NSNull()
            }
            
            if let price = parsedPrice {
                updates["unit_price"] = price
            } else {
                updates["unit_price"] = NSNull()
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
