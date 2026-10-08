import Foundation
import SwiftUI
import Combine

public struct ScannedIntakeItem: Identifiable, Hashable, Sendable {
    public let id: UUID
    public var name: String
    public var brand: String?
    public var barcode: String
    public var quantity: Double
    public var unit: String
    public var expirationDate: Date?
    public var status: IntakeStatus
    public var productId: Int?
    public var storageLocationId: Int?
    public var unitPrice: Double?
    public var isConfirmed: Bool
    
    public enum IntakeStatus: String, Sendable {
        case autoLogged = "Auto-logged"
        case recognized = "Recognized"
        case needsReview = "Needs Review"
        case confirmed = "Confirmed"
    }

    public init(
        id: UUID = UUID(),
        name: String,
        brand: String? = nil,
        barcode: String,
        quantity: Double = 1.0,
        unit: String = "pcs",
        expirationDate: Date? = nil,
        status: IntakeStatus = .recognized,
        productId: Int? = nil,
        storageLocationId: Int? = nil,
        unitPrice: Double? = nil,
        isConfirmed: Bool = false
    ) {
        self.id = id
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
        self.isConfirmed = isConfirmed
    }
}

@MainActor
public class ScanViewModel: ObservableObject {
    @Published public var storeName: String
    @Published public var scannedItems: [ScannedIntakeItem] = []
    @Published public var availableLocations: [StorageLocation] = []
    @Published public var isScanning: Bool = true
    @Published public var isCommitting: Bool = false
    @Published public var toastMessage: String? = nil
    @Published public var errorMessage: String? = nil
    @Published public var lastScannedBarcode: String = ""
    @Published public var unresolvedBarcode: String? = nil
    @Published public var showingQuickAddSheet: Bool = false
    @Published public var isResolvingBarcode: Bool = false
    @Published public var isProcessingReceipt: Bool = false
    @Published public var showingReceiptCamera: Bool = false
    public var isPreview: Bool
    public let scannerManager: BarcodeScannerManager
    private let client: APIClient
    private var inFlightResolutions: Set<String> = []
    
    public init(client: APIClient = .shared, isPreview: Bool = false) {
        self.client = client
        self.isPreview = isPreview
        self.storeName = isPreview ? "SM Supermarket Megamall" : ""
        self.scannerManager = BarcodeScannerManager()
        if isPreview {
            scannerManager.isCameraAvailable = false
            setupSampleIntake()
        }

        self.scannerManager.onBarcodeDetected = { [weak self] code in
            self?.onBarcodeScanned(code)
        }
    }

    public func loadLocations() async {
        do {
            let locations = try await client.fetchLocations()
            self.availableLocations = locations
        } catch {
            self.errorMessage = "Failed to load locations: \(error.localizedDescription)"
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
        // Check if barcode is already being resolved
        if inFlightResolutions.contains(barcode) {
            return
        }
        inFlightResolutions.insert(barcode)
        defer {
            inFlightResolutions.remove(barcode)
        }

        isResolvingBarcode = true
        defer {
            isResolvingBarcode = false
        }

        // 1. Check if already scanned in current session -> increment quantity
        if let idx = scannedItems.firstIndex(where: { $0.barcode == barcode }) {
            scannedItems[idx].quantity += 1.0
            self.toastMessage = "Incremented \(scannedItems[idx].name) (\(Int(scannedItems[idx].quantity)))"
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
            let item = ScannedIntakeItem(
                name: prod.name,
                brand: prod.brand,
                barcode: barcode,
                quantity: 1.0,
                unit: prod.unit ?? "pcs",
                expirationDate: nil,
                status: .recognized,
                productId: prod.id,
                storageLocationId: nil,
                isConfirmed: false
            )
            self.scannedItems.insert(item, at: 0)
            self.toastMessage = "Recognized: \(prod.name)"
        } else {
            self.unresolvedBarcode = barcode
            self.showingQuickAddSheet = true
            self.toastMessage = "Unrecognized barcode: \(barcode)"
        }
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

            let item = ScannedIntakeItem(
                name: createdProduct.name,
                brand: createdProduct.brand,
                barcode: barcode,
                quantity: 1.0,
                unit: createdProduct.unit ?? "pcs",
                expirationDate: nil,
                status: .autoLogged,
                productId: createdProduct.id,
                storageLocationId: nil,
                isConfirmed: false
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

    public func processScannedReceipt(images: [UIImage]) async {
        isProcessingReceipt = true
        toastMessage = "Processing receipt OCR..."

        var allLines: [String] = []
        for image in images {
            let lines = await ReceiptOCRService.shared.recognizeText(from: image)
            allLines.append(contentsOf: lines)
        }

        let catalog = isPreview ? PreviewData.products : (try? await client.fetchProducts()) ?? PreviewData.products
        let parsedItems = ReceiptOCRService.shared.parseReceiptLines(allLines, catalog: catalog)

        var addedCount = 0
        for item in parsedItems {
            let intakeItem = ScannedIntakeItem(
                name: item.matchedProduct?.name ?? item.parsedName,
                brand: item.matchedProduct?.brand,
                barcode: item.matchedProduct?.barcode ?? UUID().uuidString.prefix(8).description,
                quantity: item.quantity,
                unit: item.matchedProduct?.unit ?? "pcs",
                expirationDate: nil,
                status: item.matchedProduct != nil ? .recognized : .needsReview,
                productId: item.matchedProduct?.id,
                storageLocationId: nil,
                unitPrice: item.parsedPrice,
                isConfirmed: false
            )
            scannedItems.insert(intakeItem, at: 0)
            addedCount += 1
        }

        toastMessage = "Extracted \(addedCount) items from receipt"
        isProcessingReceipt = false
    }

    public func simulateReceiptScan(receiptName: String = "SM Supermarket Megamall (Receipt #0994)") {
        self.storeName = "SM Supermarket Megamall"
        let sampleLines = [
            "SM SUPERMARKET MEGAMALL",
            "CENTURY TUNA FLAKES OIL 180G    40.50",
            "PUREFOODS CORNED BEEF 150G      92.00",
            "SAN MIGUEL PALE PILSEN 330ML    52.00",
            "GARDENIA CLASSIC WHITE BREAD    82.00",
            "DATU PUTI VINEGAR BOTTLE 1L     48.00",
            "TOTAL AMOUNT                  314.50"
        ]

        let catalog = isPreview ? PreviewData.products : PreviewData.products
        let parsed = ReceiptOCRService.shared.parseReceiptLines(sampleLines, catalog: catalog)

        for item in parsed {
            let intakeItem = ScannedIntakeItem(
                name: item.matchedProduct?.name ?? item.parsedName,
                brand: item.matchedProduct?.brand,
                barcode: item.matchedProduct?.barcode ?? UUID().uuidString.prefix(8).description,
                quantity: item.quantity,
                unit: item.matchedProduct?.unit ?? "pcs",
                expirationDate: nil,
                status: item.matchedProduct != nil ? .recognized : .needsReview,
                productId: item.matchedProduct?.id,
                storageLocationId: nil,
                unitPrice: item.parsedPrice,
                isConfirmed: false
            )
            scannedItems.insert(intakeItem, at: 0)
        }
        toastMessage = "Loaded \(parsed.count) receipt items from \(storeName)"
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
                expirationDate: calendar.date(byAdding: .day, value: 5, to: Date()),
                status: .autoLogged,
                productId: 1,
                storageLocationId: 1,
                isConfirmed: true
            ),
            ScannedIntakeItem(
                name: "Greek Yogurt Tub",
                brand: "Fage",
                barcode: "00789012",
                quantity: 2,
                unit: "pack",
                expirationDate: calendar.date(byAdding: .day, value: 12, to: Date()),
                status: .autoLogged,
                productId: 2,
                storageLocationId: 1,
                isConfirmed: true
            ),
            ScannedIntakeItem(
                name: "Century Tuna Flakes",
                brand: "Century",
                barcode: "4800016644810",
                quantity: 4,
                unit: "cans",
                expirationDate: calendar.date(byAdding: .year, value: 2, to: Date()),
                status: .recognized,
                productId: 3,
                storageLocationId: 2,
                isConfirmed: true
            )
        ]
    }

    @discardableResult
    public func confirmItem(_ item: ScannedIntakeItem) -> Bool {
        guard let idx = scannedItems.firstIndex(where: { $0.id == item.id }) else { return false }
        var target = scannedItems[idx]

        // An item can only be confirmed if it has a productId, is not .needsReview, has storageLocationId, and valid quantity/unit
        guard target.productId != nil && target.status != .needsReview else {
            self.errorMessage = "Cannot confirm: '\(target.name)' is unresolved. Please link or register the product first."
            return false
        }
        guard target.storageLocationId != nil else {
            self.errorMessage = "Cannot confirm: Please select a storage location for '\(target.name)'."
            return false
        }
        guard target.quantity > 0 && !target.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            self.errorMessage = "Cannot confirm: '\(target.name)' must have a valid quantity and unit."
            return false
        }

        target.isConfirmed.toggle()
        if target.isConfirmed {
            target.status = .confirmed
        } else {
            target.status = .recognized
        }
        scannedItems[idx] = target
        return target.isConfirmed
    }

    public func confirmAllValid() {
        for idx in scannedItems.indices {
            let item = scannedItems[idx]
            if item.productId != nil &&
                item.status != .needsReview &&
                item.storageLocationId != nil &&
                item.quantity > 0 &&
                !item.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                scannedItems[idx].isConfirmed = true
                scannedItems[idx].status = .confirmed
            }
        }
    }
    
    public func addItem(barcode: String, name: String, brand: String? = nil, quantity: Double = 1, unit: String = "units", daysUntilExp: Int? = nil) {
        let exp: Date? = daysUntilExp.flatMap { Calendar.current.date(byAdding: .day, value: $0, to: Date()) }
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
        guard !scannedItems.isEmpty else {
            self.errorMessage = "Intake queue is empty. Scan or add items before committing."
            return
        }
        isCommitting = true
        errorMessage = nil

        // Enforce strict validation
        for item in scannedItems {
            guard item.productId != nil && item.status != .needsReview else {
                self.errorMessage = "Cannot commit: '\(item.name)' is unresolved. Please link or register the product first."
                isCommitting = false
                return
            }
            guard item.storageLocationId != nil else {
                self.errorMessage = "Cannot commit: Please select a storage location for '\(item.name)'."
                isCommitting = false
                return
            }
            guard item.quantity > 0 && !item.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                self.errorMessage = "Cannot commit: '\(item.name)' must have a valid quantity and unit."
                isCommitting = false
                return
            }
            guard item.isConfirmed else {
                self.errorMessage = "Cannot commit: Please confirm details for '\(item.name)' before committing."
                isCommitting = false
                return
            }
        }

        if isPreview {
            try? await Task.sleep(nanoseconds: 300_000_000)
            self.toastMessage = "Committed intake of \(scannedItems.count) items (Preview)"
            self.scannedItems.removeAll()
            self.lastScannedBarcode = ""
            isCommitting = false
            return
        }

        do {
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd"

            var itemsToCommit: [SessionItemCreate] = []
            for item in scannedItems {
                guard let pid = item.productId else {
                    self.errorMessage = "Cannot commit: '\(item.name)' is unresolved. Please link or register the product first."
                    isCommitting = false
                    return
                }
                guard let locId = item.storageLocationId else {
                    self.errorMessage = "Cannot commit: Please select a storage location for '\(item.name)'."
                    isCommitting = false
                    return
                }

                let expStr: String? = item.expirationDate.map { dateFormatter.string(from: $0) }
                let sessionItem = SessionItemCreate(
                    product_id: pid,
                    storage_location_id: locId,
                    quantity: item.quantity,
                    expiration_date: expStr,
                    unit_price: item.unitPrice
                )
                itemsToCommit.append(sessionItem)
            }

            // Create the draft grocery session
            let isoFormatter = ISO8601DateFormatter()
            let trimmedStore = storeName.trimmingCharacters(in: .whitespaces)
            let sessionName = trimmedStore.isEmpty ? "Grocery Intake" : trimmedStore
            let sessionCreate = GrocerySessionCreate(
                store_name: sessionName,
                purchase_date: isoFormatter.string(from: Date()),
                total_amount: scannedItems.compactMap { $0.unitPrice }.reduce(0.0, +),
                notes: "Rapid intake session committed via Provision app"
            )
            let session = try await client.createSession(sessionCreate)

            // Commit session to generate batches and ledger events
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
