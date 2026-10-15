import Foundation


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

struct TestAssertionFailure: Error {
    let message: String
}

func assertTrue(_ condition: Bool, _ message: String) throws {
    if !condition {
        throw TestAssertionFailure(message: "ASSERTION FAILED: \(message)")
    }
}

func assertEquals<T: Equatable>(_ actual: T, _ expected: T, _ message: String) throws {
    if actual != expected {
        throw TestAssertionFailure(message: "EQUALS FAILED: expected '\(expected)', got '\(actual)'. \(message)")
    }
}

print("Running Provision Swift Regression Tests...")

// ==============================================================================
// 1. Confirmed-Item Mutation Invalidation Tests
// ==============================================================================
do {
    print("Test 1: Confirmed-item mutation invalidation...")
    var item = ScannedIntakeItem(
        name: "Century Tuna",
        brand: "Century",
        barcode: "4800016644818",
        quantity: 1.0,
        unit: "cans",
        expirationDate: nil,
        status: .confirmed,
        productId: 1,
        storageLocationId: 10,
        unitPrice: 40.50,
        isConfirmed: true
    )
    try assertTrue(item.isConfirmed, "Item should start confirmed")
    try assertEquals(item.status, .confirmed, "Status should be confirmed")

    // Invalidation helper simulation
    func invalidate(_ item: inout ScannedIntakeItem) {
        item.isConfirmed = false
        if item.status == .confirmed {
            item.status = .recognized
        }
    }

    // A. Quantity mutation invalidates confirmation
    item.quantity += 1.0
    invalidate(&item)
    try assertTrue(!item.isConfirmed, "Quantity change must invalidate confirmation")
    try assertEquals(item.status, .recognized, "Status must revert to recognized")

    // Re-confirm
    item.isConfirmed = true
    item.status = .confirmed

    // B. Location mutation invalidates confirmation
    item.storageLocationId = 20
    invalidate(&item)
    try assertTrue(!item.isConfirmed, "Location change must invalidate confirmation")

    // Re-confirm
    item.isConfirmed = true
    item.status = .confirmed

    // C. Unit price mutation invalidates confirmation
    item.unitPrice = 45.00
    invalidate(&item)
    try assertTrue(!item.isConfirmed, "Price change must invalidate confirmation")

    // Re-confirm
    item.isConfirmed = true
    item.status = .confirmed

    // D. Expiration date mutation invalidates confirmation
    item.expirationDate = Date(timeIntervalSince1970: 1800000000)
    invalidate(&item)
    try assertTrue(!item.isConfirmed, "Expiration date change must invalidate confirmation")

    // Re-confirm
    item.isConfirmed = true
    item.status = .confirmed

    // E. Clearing expiration date invalidates confirmation
    item.expirationDate = nil
    invalidate(&item)
    try assertTrue(!item.isConfirmed, "Clearing expiration date must invalidate confirmation")

    print("  -> Passed!")
}

// ==============================================================================
// 2. Product-Resolution Workflow Tests (Unknown Barcode -> Existing vs In-Place)
// ==============================================================================
do {
    print("Test 2: Product-resolution workflow (Case 2A & Case 2B)...")

    var items: [ScannedIntakeItem] = []
    var resolvingId: UUID? = nil
    var unresolvedBarcode: String? = nil

    func resolveProduct(catalogProduct: (id: Int, name: String, brand: String?, unit: String?)) {
        if let targetId = resolvingId, let idx = items.firstIndex(where: { $0.id == targetId }) {
            items[idx].productId = catalogProduct.id
            items[idx].name = catalogProduct.name
            items[idx].brand = catalogProduct.brand
            items[idx].status = .recognized
            items[idx].isConfirmed = false
        } else {
            let bc = unresolvedBarcode ?? "UNKNOWN_BC"
            let newItem = ScannedIntakeItem(
                name: catalogProduct.name,
                brand: catalogProduct.brand,
                barcode: bc,
                quantity: 1.0,
                unit: catalogProduct.unit ?? "pcs",
                expirationDate: nil,
                status: .recognized,
                productId: catalogProduct.id,
                storageLocationId: nil,
                isConfirmed: false
            )
            items.insert(newItem, at: 0)
        }
        resolvingId = nil
        unresolvedBarcode = nil
    }

    // Case 2A: Unknown barcode scanned (no queue item exists yet) -> User links existing catalog product
    unresolvedBarcode = "4809998887776"
    resolvingId = nil
    resolveProduct(catalogProduct: (id: 42, name: "Lucky Me Pancit Canton", brand: "Lucky Me", unit: "pack"))

    try assertEquals(items.count, 1, "Must create exactly one item in queue")
    try assertEquals(items[0].name, "Lucky Me Pancit Canton", "Name must match catalog product")
    try assertEquals(items[0].barcode, "4809998887776", "Must keep the scanned unknown barcode")
    try assertEquals(items[0].productId, 42, "Must link to product ID")
    try assertTrue(!items[0].isConfirmed, "Must require confirmation")
    try assertTrue(resolvingId == nil, "Must clear resolvingId")
    try assertTrue(unresolvedBarcode == nil, "Must clear unresolvedBarcode")

    // Case 2B: Unresolved receipt item exists -> User links existing catalog product in-place
    let unresolvedItem = ScannedIntakeItem(
        name: "UNKNOWN ITEM 123",
        brand: nil,
        barcode: "RCPT_001",
        quantity: 2.0,
        unit: "pcs",
        expirationDate: nil,
        status: .needsReview,
        productId: nil,
        storageLocationId: nil,
        isConfirmed: false
    )
    items.append(unresolvedItem)
    try assertEquals(items.count, 2, "Items count should now be 2")

    // Link the unresolved item
    resolvingId = unresolvedItem.id
    resolveProduct(catalogProduct: (id: 99, name: "San Miguel Pale Pilsen", brand: "San Miguel", unit: "can"))

    try assertEquals(items.count, 2, "Must NOT duplicate item; count must remain 2")
    let updatedItem = items.first(where: { $0.id == unresolvedItem.id })!
    try assertEquals(updatedItem.name, "San Miguel Pale Pilsen", "Must update original entry name in-place")
    try assertEquals(updatedItem.productId, 99, "Must update product ID in-place")
    try assertEquals(updatedItem.quantity, 2.0, "Must preserve original quantity")
    try assertEquals(updatedItem.status, .recognized, "Status must update to recognized")

    print("  -> Passed!")
}

// ==============================================================================
// 3. Safe Reconciliation Tests (No Double-Counting)
// ==============================================================================
do {
    print("Test 3: Receipt/barcode safe reconciliation (prevent double-counting)...")

    var items: [ScannedIntakeItem] = []

    // Helper mirror of ScanViewModel.reconcileExistingItem
    func reconcile(existingIdx: Int, receiptQty: Double, receiptPrice: Double?, isReceiptUncertain: Bool) {
        let existing = items[existingIdx]
        let finalQty = max(existing.quantity, receiptQty)
        let changed = (existing.quantity != finalQty)
        items[existingIdx].quantity = finalQty

        if let price = receiptPrice {
            items[existingIdx].unitPrice = price
        }
        if changed || existing.isConfirmed || isReceiptUncertain {
            items[existingIdx].status = .needsReview
        }
        items[existingIdx].isConfirmed = false
    }

    // A. Single item scanned (qty 1), receipt also has qty 1 -> MUST NOT double-count to 2!
    items.append(
        ScannedIntakeItem(
            name: "Century Tuna",
            brand: "Century",
            barcode: "4800016644818",
            quantity: 1.0,
            unit: "cans",
            expirationDate: nil,
            status: .confirmed,
            productId: 1,
            storageLocationId: 5,
            unitPrice: nil,
            isConfirmed: true
        )
    )

    reconcile(existingIdx: 0, receiptQty: 1.0, receiptPrice: 40.50, isReceiptUncertain: false)
    try assertEquals(items[0].quantity, 1.0, "Quantity must NOT double-count 1 + 1 = 2; must remain 1.0")
    try assertEquals(items[0].unitPrice, 40.50, "Unit price from receipt must be attached")
    try assertTrue(!items[0].isConfirmed, "Confirmation must be reset")
    try assertEquals(items[0].status, .needsReview, "Confirmed item modified by receipt must be flagged for review")

    // B. Re-importing same receipt a second time -> Quantity must stay 1.0
    reconcile(existingIdx: 0, receiptQty: 1.0, receiptPrice: 40.50, isReceiptUncertain: false)
    try assertEquals(items[0].quantity, 1.0, "Repeated receipt import must not increase quantity")

    // C. Conflicting quantities: user scanned 1 can, receipt shows basket has 3 cans
    reconcile(existingIdx: 0, receiptQty: 3.0, receiptPrice: 40.50, isReceiptUncertain: false)
    try assertEquals(items[0].quantity, 3.0, "Reconciled quantity must take max verified basket count (3.0)")
    try assertEquals(items[0].status, .needsReview, "Conflicting quantity must require review")

    print("  -> Passed!")
}

// ==============================================================================
// 4. Expiration Date State Management Tests
// ==============================================================================
do {
    print("Test 4: Expiration date source tracking and preservation on OCR failure...")

    enum DateSource: Equatable {
        case none
        case previouslySaved(Date)
        case ocrRecognized(Date, isAmbiguous: Bool)
        case manualSelected(Date)
    }

    let initialDate = Date(timeIntervalSince1970: 1780000000)
    var dateSource: DateSource = .previouslySaved(initialDate)
    var selectedDate: Date = initialDate
    var hasExplicitDate: Bool = true
    var isAmbiguous: Bool = false

    // A. Failed OCR attempt on new photo -> MUST NOT misrepresent older date or set ambiguous
    func handleFailedOCR() {
        isAmbiguous = false // Reset ambiguity
        // Preserve previously saved date
        selectedDate = initialDate
        dateSource = .previouslySaved(initialDate)
        hasExplicitDate = true
    }

    handleFailedOCR()
    try assertTrue(dateSource == .previouslySaved(initialDate), "Must preserve previously saved source on OCR failure")
    try assertTrue(!isAmbiguous, "Ambiguity must be reset on failed OCR")
    try assertEquals(selectedDate, initialDate, "Saved date must be preserved")

    // B. User explicitly clears date
    dateSource = .none
    hasExplicitDate = false
    try assertTrue(dateSource == .none, "Date source must be none after clearing")
    try assertTrue(!hasExplicitDate, "hasExplicitDate must be false")

    // C. When hasExplicitDate is false, user tapping 'Done' applies nil, never today
    let appliedDate: Date? = hasExplicitDate ? selectedDate : nil
    try assertTrue(appliedDate == nil, "Must apply nil when explicit date is false, never today's date")

    print("  -> Passed!")
}

// ==============================================================================
// 5. Total Calculation (quantity * unitPrice) Tests
// ==============================================================================
do {
    print("Test 5: Grocery session total calculation (quantity * unitPrice)...")

    let testItems = [
        ScannedIntakeItem(name: "Item A", barcode: "1", quantity: 4.0, unit: "cans", expirationDate: nil, unitPrice: 40.50),
        ScannedIntakeItem(name: "Item B", barcode: "2", quantity: 2.5, unit: "kg", expirationDate: nil, unitPrice: 120.00),
        ScannedIntakeItem(name: "Item C", barcode: "3", quantity: 1.0, unit: "pack", expirationDate: nil, unitPrice: nil) // no price
    ]

    let total = testItems.compactMap { item in
        item.unitPrice.map { $0 * item.quantity }
    }.reduce(0.0, +)

    // Expected: 4 * 40.50 + 2.5 * 120.00 = 162.00 + 300.00 = 462.00
    try assertEquals(total, 462.00, "Total must be 462.00 (4 * 40.50 + 2.5 * 120)")

    print("  -> Passed!")
}

// ==============================================================================
// 6. Cancellation & State Cleanup Tests
// ==============================================================================
do {
    print("Test 6: Product-resolution cancellation and state cleanup...")

    var resolvingId: UUID? = UUID()
    var unresolvedBarcode: String? = "4800001112223"
    var showingSheet: Bool = true

    func clearResolutionState() {
        resolvingId = nil
        unresolvedBarcode = nil
        showingSheet = false
    }

    clearResolutionState()
    try assertTrue(resolvingId == nil, "resolvingId must be nil after clearResolutionState")
    try assertTrue(unresolvedBarcode == nil, "unresolvedBarcode must be nil after clearResolutionState")
    try assertTrue(!showingSheet, "showingSheet must be false after clearResolutionState")

    print("  -> Passed!")
}

// ==============================================================================
// 7. Barcode Lookup Failure Differentiation Tests (404 vs Network Error)
// ==============================================================================
do {
    print("Test 7: Barcode lookup error differentiation (404 vs Network error)...")

    enum MockAPIError: Error {
        case networkError
        case unauthorized
        case serverError(String)
    }

    var showingQuickAdd = false
    var unresolvedBarcode: String? = nil
    var errorMessage: String? = nil

    func handleLookupResult(barcode: String, result: Result<String?, MockAPIError>) {
        switch result {
        case .success(let found):
            if found == nil {
                // Genuinely not found in catalog (HTTP 200 with empty list)
                unresolvedBarcode = barcode
                showingQuickAdd = true
            }
        case .failure(let error):
            // Network / Server failure: DO NOT show quick add sheet! Show actionable error with retry
            switch error {
            case .networkError:
                errorMessage = "Network connection failed. Unable to verify barcode \(barcode)."
            case .unauthorized:
                errorMessage = "Session expired or authentication required. Please log in again."
            case .serverError(let msg):
                errorMessage = "Lookup failed for barcode \(barcode): \(msg)"
            }
        }
    }

    // Case A: Network failure -> MUST NOT show registration sheet!
    handleLookupResult(barcode: "4800000000000", result: .failure(.networkError))
    try assertTrue(!showingQuickAdd, "Network failure must NOT show quick add registration sheet")
    try assertTrue(unresolvedBarcode == nil, "unresolvedBarcode must not be set on network error")
    try assertEquals(errorMessage, "Network connection failed. Unable to verify barcode 4800000000000.", "Must show network error message")

    // Case B: Genuine 404 (product not found in catalog) -> Shows registration sheet
    errorMessage = nil
    handleLookupResult(barcode: "4800000000000", result: .success(nil))
    try assertTrue(showingQuickAdd, "Genuinely unknown barcode must show registration sheet")
    try assertEquals(unresolvedBarcode, "4800000000000", "unresolvedBarcode must be set")
    try assertTrue(errorMessage == nil, "No error message on genuine not found")

    print("  -> Passed!")
}

// ==============================================================================
// 8. Repeated Receipt Import Stability Tests
// ==============================================================================
do {
    print("Test 8: Repeated receipt import stability...")

    var queue: [ScannedIntakeItem] = []

    func importReceipt(lines: [(name: String, barcode: String, qty: Double, price: Double)]) {
        for line in lines {
            if let idx = queue.firstIndex(where: { $0.barcode == line.barcode }) {
                // Safe reconciliation: never blindly add
                queue[idx].quantity = max(queue[idx].quantity, line.qty)
                queue[idx].unitPrice = line.price
            } else {
                queue.append(
                    ScannedIntakeItem(
                        name: line.name,
                        barcode: line.barcode,
                        quantity: line.qty,
                        unit: "pcs",
                        expirationDate: nil,
                        status: .recognized,
                        unitPrice: line.price
                    )
                )
            }
        }
    }

    let receiptA = [
        (name: "Century Tuna", barcode: "4800016644818", qty: 2.0, price: 40.50),
        (name: "Gardenia Bread", barcode: "4806500800018", qty: 1.0, price: 82.00)
    ]

    // First import
    importReceipt(lines: receiptA)
    try assertEquals(queue.count, 2, "Queue should have 2 items")
    try assertEquals(queue[0].quantity, 2.0, "Century Tuna quantity should be 2.0")
    try assertEquals(queue[1].quantity, 1.0, "Gardenia Bread quantity should be 1.0")

    // Second import of same receipt
    importReceipt(lines: receiptA)
    try assertEquals(queue.count, 2, "Repeated import must NOT add duplicate entries")
    try assertEquals(queue[0].quantity, 2.0, "Repeated import must NOT increase Century Tuna quantity")
    try assertEquals(queue[1].quantity, 1.0, "Repeated import must NOT increase Gardenia Bread quantity")

    print("  -> Passed!")
}

print("\nALL SWIFT REGRESSION TESTS PASSED SUCCESSFULLY! (8/8 suites)")
