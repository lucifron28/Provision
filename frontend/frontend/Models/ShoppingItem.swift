import Foundation

// MARK: - Shopping List Models
// Conforms to FastAPI app.schemas.shopping

nonisolated public struct ShoppingItem: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var name: String
    public var product_id: Int?
    public var quantity: Double
    public var unit: String?
    public var is_bought: Bool
    public var reconciliation_status: String?
    public var notes: String?
    public var created_at: String?
    public var updated_at: String?
    public var product: Product?
    
    public init(
        id: Int,
        name: String,
        product_id: Int? = nil,
        quantity: Double = 1.0,
        unit: String? = nil,
        is_bought: Bool = false,
        reconciliation_status: String? = nil,
        notes: String? = nil,
        created_at: String? = nil,
        updated_at: String? = nil,
        product: Product? = nil
    ) {
        self.id = id
        self.name = name
        self.product_id = product_id
        self.quantity = quantity
        self.unit = unit
        self.is_bought = is_bought
        self.reconciliation_status = reconciliation_status
        self.notes = notes
        self.created_at = created_at
        self.updated_at = updated_at
        self.product = product
    }
    
    public var displayQuantity: String {
        if quantity.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(quantity))"
        } else {
            return String(format: "%.1f", quantity)
        }
    }

    public var reconciliationStatus: String { reconciliation_status ?? "pending" }
}

nonisolated public struct PurchasedItemResolutionRequest: Codable, Sendable, Equatable {
    public let shopping_item_id: Int
    public let expected_updated_at: String
    public let action: String
    public let product_id: Int?
    public let new_product: ProductCreate?
    public let quantity: ExactQuantity?
    public let inventory_unit: String?
    public let storage_location_id: Int?
    public let expiration_date: String?
    public let unit_price: ExactQuantity?

    public init(shoppingItemID: Int, expectedUpdatedAt: String, action: String,
                productID: Int? = nil, newProduct: ProductCreate? = nil,
                quantity: ExactQuantity? = nil, inventoryUnit: String? = nil,
                storageLocationID: Int? = nil, expirationDate: String? = nil,
                unitPrice: ExactQuantity? = nil) {
        shopping_item_id = shoppingItemID
        expected_updated_at = expectedUpdatedAt
        self.action = action
        product_id = productID
        new_product = newProduct
        self.quantity = quantity
        inventory_unit = inventoryUnit
        storage_location_id = storageLocationID
        expiration_date = expirationDate
        unit_price = unitPrice
    }
}

nonisolated public struct ReconcilePurchasedItemsRequest: Codable, Sendable, Equatable {
    public let idempotency_key: String
    public let items: [PurchasedItemResolutionRequest]

    public init(idempotencyKey: String = UUID().uuidString, items: [PurchasedItemResolutionRequest]) {
        idempotency_key = idempotencyKey
        self.items = items
    }
}

nonisolated public struct ReconciledPurchasedItem: Decodable, Sendable, Equatable {
    public let shopping_item_id: Int
    public let reconciliation_status: String
    public let product_id: Int?
    public let product_name: String?
    public let batch_id: Int?
    public let quantity: ExactQuantity?
    public let inventory_unit: String?
}

nonisolated public struct ReconcilePurchasedItemsResponse: Decodable, Sendable {
    public let items: [ReconciledPurchasedItem]
    public let replayed: Bool
}

nonisolated public struct PendingPurchasedGroceriesRecord: Codable, Sendable, Equatable {
    public let scopeStorageKey: String
    public let request: ReconcilePurchasedItemsRequest

    public init(scopeStorageKey: String, request: ReconcilePurchasedItemsRequest) {
        self.scopeStorageKey = scopeStorageKey
        self.request = request
    }
}

nonisolated public enum PendingPurchasedGroceriesReadResult: Equatable, Sendable {
    case missing
    case record(PendingPurchasedGroceriesRecord)
    case corrupt
    case unavailable
}

nonisolated public struct ShoppingItemCreate: Codable, Sendable {
    public var name: String?
    public var product_id: Int?
    public var quantity: Double
    public var unit: String?
    public var notes: String?
    
    public init(name: String? = nil, product_id: Int? = nil, quantity: Double = 1.0, unit: String? = nil, notes: String? = nil) {
        self.name = name
        self.product_id = product_id
        self.quantity = quantity
        self.unit = unit
        self.notes = notes
    }
}

nonisolated public struct ShoppingItemUpdate: Codable, Sendable {
    public var name: String?
    public var product_id: Int?
    public var quantity: Double?
    public var unit: String?
    public var is_bought: Bool?
    public var notes: String?
    
    public init(name: String? = nil, product_id: Int? = nil, quantity: Double? = nil, unit: String? = nil, is_bought: Bool? = nil, notes: String? = nil) {
        self.name = name
        self.product_id = product_id
        self.quantity = quantity
        self.unit = unit
        self.is_bought = is_bought
        self.notes = notes
    }
}
