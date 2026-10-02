import Foundation
import SwiftUI
import Combine

public struct ScannedIntakeItem: Identifiable, Hashable {
    public let id = UUID()
    public var name: String
    public var brand: String?
    public var barcode: String
    public var quantity: Double
    public var unit: String
    public var expirationDate: Date
    public var status: IntakeStatus
    public var productId: Int?
    public var storageLocationId: Int?
    public var unitPrice: Double?
    
    public enum IntakeStatus: String {
        case autoLogged = "Auto-logged"
        case recognized = "Recognized"
        case needsReview = "Needs Review"
    }

    public init(
        name: String,
        brand: String? = nil,
        barcode: String,
        quantity: Double = 1.0,
        unit: String = "pcs",
        expirationDate: Date,
        status: IntakeStatus = .recognized,
        productId: Int? = nil,
        storageLocationId: Int? = nil,
        unitPrice: Double? = nil
    ) {
        self.name = name
        self.brand = brand
        self.barcode = barcode
        self.quantity = quantity
        self.unit = unit
        self.expirationDate = expirationDate
        self.status = status
        self.productId = productId
        self.storageLocationId = storageLocationId
        self.unitPrice = unitPrice
    }
}

@MainActor
public class ScanViewModel: ObservableObject {
    @Published public var storeName: String = "Trader Joe's"
    @Published public var scannedItems: [ScannedIntakeItem] = []
    @Published public var isScanning: Bool = true
    @Published public var isCommitting: Bool = false
    @Published public var toastMessage: String? = nil
    @Published public var errorMessage: String? = nil
    @Published public var lastScannedBarcode: String = ""
    @Published public var unresolvedBarcode: String? = nil
    @Published public var showingQuickAddSheet: Bool = false
    @Published public var isResolvingBarcode: Bool = false
    public var isPreview: Bool
    public let scannerManager: BarcodeScannerManager
    private let client: APIClient
    
    public init(client: APIClient = .shared, isPreview: Bool = false) {
        self.client = client
        self.isPreview = isPreview
        self.scannerManager = BarcodeScannerManager()
        if isPreview {
            scannerManager.isCameraAvailable = false
        }
        setupSampleIntake()

        self.scannerManager.onBarcodeDetected = { [weak self] code in
            self?.onBarcodeScanned(code)
        }
    }

    public func startScanning() {
        guard !isPreview else { return }
        scannerManager.startScanning()
    }

    public func stopScanning() {
        scannerManager.stopScanning()
    }
    public func onBarcodeScanned(_ barcode: String) {
        let trimmed = barcode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        self.lastScannedBarcode = trimmed

        Task {
            await resolveScannedBarcode(trimmed)
        }
    }

    public func resolveScannedBarcode(_ barcode: String) async {
        isResolvingBarcode = true

        // 1. Check if already scanned in current session -> increment quantity
        if let idx = scannedItems.firstIndex(where: { $0.barcode == barcode }) {
            scannedItems[idx].quantity += 1.0
            self.toastMessage = "Incremented \(scannedItems[idx].name) (\(Int(scannedItems[idx].quantity)))"
            isResolvingBarcode = false
            return
        }

        // 2. Query catalog via API or PreviewData
        var resolvedProduct: Product? = nil
        if isPreview {
            resolvedProduct = PreviewData.products.first(where: { $0.barcode == barcode })
        } else {
            do {
                resolvedProduct = try await client.fetchProduct(barcode: barcode)
            } catch {
                // Network error or not found
            }
        }

        if let prod = resolvedProduct {
            let defaultExpDays: Int
            switch prod.category {
            case "Dairy & Chilled": defaultExpDays = 7
            case "Fresh Produce": defaultExpDays = 5
            case "Frozen & Meats": defaultExpDays = 90
            default: defaultExpDays = 180
            }
            let exp = Calendar.current.date(byAdding: .day, value: defaultExpDays, to: Date()) ?? Date()

            let item = ScannedIntakeItem(
                name: prod.name,
                brand: prod.brand,
                barcode: barcode,
                quantity: 1.0,
                unit: prod.unit ?? "pcs",
                expirationDate: exp,
                status: .recognized,
                productId: prod.id
            )
            self.scannedItems.insert(item, at: 0)
            self.toastMessage = "Recognized: \(prod.name)"
        } else {
            self.unresolvedBarcode = barcode
            self.showingQuickAddSheet = true
            self.toastMessage = "Unrecognized barcode: \(barcode)"
        }

        isResolvingBarcode = false
    }

    public func registerProductAndAddToQueue(
        name: String,
        brand: String?,
        category: String?,
        unit: String,
        packageSize: Double?
    ) async -> Bool {
        guard let barcode = unresolvedBarcode else { return false }
        let create = ProductCreate(
            name: name,
            brand: brand?.isEmpty == true ? nil : brand,
            barcode: barcode,
            category: category?.isEmpty == true ? nil : category,
            package_size: packageSize,
            unit: unit
        )

        do {
            let createdProduct: Product
            if isPreview {
                createdProduct = Product(
                    id: Int.random(in: 1000...9999),
                    name: name,
                    brand: brand,
                    barcode: barcode,
                    category: category,
                    package_size: packageSize,
                    unit: unit
                )
            } else {
                createdProduct = try await client.createProduct(create)
            }

            let exp = Calendar.current.date(byAdding: .day, value: 30, to: Date()) ?? Date()
            let item = ScannedIntakeItem(
                name: createdProduct.name,
                brand: createdProduct.brand,
                barcode: barcode,
                quantity: 1.0,
                unit: createdProduct.unit ?? "pcs",
                expirationDate: exp,
                status: .autoLogged,
                productId: createdProduct.id
            )
            self.scannedItems.insert(item, at: 0)
            self.toastMessage = "Added \(createdProduct.name) to intake queue"
            self.unresolvedBarcode = nil
            self.showingQuickAddSheet = false
            return true
        } catch {
            self.errorMessage = "Failed to register product: \(error.localizedDescription)"
            return false
        }
    }

    public func incrementQuantity(for item: ScannedIntakeItem) {
        if let idx = scannedItems.firstIndex(where: { $0.id == item.id }) {
            scannedItems[idx].quantity += 1.0
        }
    }

    public func decrementQuantity(for item: ScannedIntakeItem) {
        if let idx = scannedItems.firstIndex(where: { $0.id == item.id }) {
            if scannedItems[idx].quantity > 1.0 {
                scannedItems[idx].quantity -= 1.0
            } else {
                scannedItems.remove(at: idx)
            }
        }
    }
    private func setupSampleIntake() {
        let calendar = Calendar.current
        self.scannedItems = [
            ScannedIntakeItem(
                name: "Organic Whole Milk",
                brand: "Trader Joe's",
                barcode: "00123456",
                quantity: 1,
                unit: "1L",
                expirationDate: calendar.date(byAdding: .day, value: 5, to: Date()) ?? Date(),
                status: .autoLogged
            ),
            ScannedIntakeItem(
                name: "Greek Yogurt Tub",
                brand: "Fage",
                barcode: "00789012",
                quantity: 2,
                unit: "pack",
                expirationDate: calendar.date(byAdding: .day, value: 12, to: Date()) ?? Date(),
                status: .autoLogged
            ),
            ScannedIntakeItem(
                name: "Century Tuna Flakes",
                brand: "Century",
                barcode: "4800016644810",
                quantity: 4,
                unit: "cans",
                expirationDate: calendar.date(byAdding: .year, value: 2, to: Date()) ?? Date(),
                status: .recognized
            )
        ]
    }
    
    public func addItem(barcode: String, name: String, brand: String? = nil, quantity: Double = 1, unit: String = "units", daysUntilExp: Int = 14) {
        let exp = Calendar.current.date(byAdding: .day, value: daysUntilExp, to: Date()) ?? Date()
        let item = ScannedIntakeItem(
            name: name,
            brand: brand,
            barcode: barcode,
            quantity: quantity,
            unit: unit,
            expirationDate: exp,
            status: .recognized
        )
        scannedItems.insert(item, at: 0)
        lastScannedBarcode = barcode
        toastMessage = "Scanned \(name)"
    }
    
    public func removeItem(at offsets: IndexSet) {
        scannedItems.remove(atOffsets: offsets)
    }
    
    public func commitIntakeSession() async {
        guard !scannedItems.isEmpty else { return }
        isCommitting = true
        errorMessage = nil
        
        if isPreview {
            try? await Task.sleep(nanoseconds: 300_000_000)
            self.toastMessage = "Committed intake of \(scannedItems.count) items (Preview)"
            self.scannedItems.removeAll()
            self.lastScannedBarcode = ""
            isCommitting = false
            return
        }

        do {
            // 1. Fetch available locations to get a fallback location
            let locations = try await client.fetchLocations()
            let defaultLocationId = locations.first?.id

            // 2. Resolve any scanned item missing a productId
            var itemsToCommit: [SessionItemCreate] = []
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd"

            for item in scannedItems {
                var targetProductId = item.productId

                if targetProductId == nil {
                    if let found = try? await client.fetchProduct(barcode: item.barcode) {
                        targetProductId = found.id
                    } else {
                        let create = ProductCreate(
                            name: item.name,
                            brand: item.brand,
                            barcode: item.barcode,
                            category: "Pantry",
                            unit: item.unit
                        )
                        if let created = try? await client.createProduct(create) {
                            targetProductId = created.id
                        }
                    }
                }

                guard let pid = targetProductId else { continue }

                let expStr = dateFormatter.string(from: item.expirationDate)
                let sessionItem = SessionItemCreate(
                    product_id: pid,
                    storage_location_id: item.storageLocationId ?? defaultLocationId,
                    quantity: item.quantity,
                    expiration_date: expStr,
                    unit_price: item.unitPrice
                )
                itemsToCommit.append(sessionItem)
            }

            guard !itemsToCommit.isEmpty else {
                self.errorMessage = "No valid products to commit."
                isCommitting = false
                return
            }

            // 3. Create the draft grocery session
            let isoFormatter = ISO8601DateFormatter()
            let sessionName = storeName.trimmingCharacters(in: .whitespaces).isEmpty ? "Grocery Intake" : storeName
            let sessionCreate = GrocerySessionCreate(
                store_name: sessionName,
                purchase_date: isoFormatter.string(from: Date()),
                total_amount: scannedItems.compactMap { $0.unitPrice }.reduce(0.0, +),
                notes: "Rapid intake session committed via Provision app"
            )
            let session = try await client.createSession(sessionCreate)

            // 4. Commit session to generate batches and ledger events
            _ = try await client.commitSession(id: session.id, items: itemsToCommit)

            self.toastMessage = "Committed \(itemsToCommit.count) items to household inventory!"
            self.scannedItems.removeAll()
            self.lastScannedBarcode = ""
        } catch {
            self.errorMessage = "Failed to commit intake session: \(error.localizedDescription)"
        }

        isCommitting = false
    }
}
