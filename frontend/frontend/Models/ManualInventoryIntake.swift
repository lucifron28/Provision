import Foundation

nonisolated public struct ManualInventoryIntakeRequest: Codable, Equatable, Sendable {
    public let idempotency_key: String
    public let product_id: Int?
    public let new_product: ProductCreate?
    public let storage_location_id: Int?
    public let purchased_at: String?
    public let expiration_date: String?
    public let quantity: Double
    public let unit_price: Double?

    public init(idempotencyKey: String = UUID().uuidString,
                productID: Int? = nil,
                newProduct: ProductCreate? = nil,
                storageLocationID: Int? = nil,
                purchasedAt: String? = nil,
                expirationDate: String? = nil,
                quantity: Double,
                unitPrice: Double? = nil) {
        idempotency_key = idempotencyKey
        product_id = productID
        new_product = newProduct
        storage_location_id = storageLocationID
        purchased_at = purchasedAt
        expiration_date = expirationDate
        self.quantity = quantity
        unit_price = unitPrice
    }
}

nonisolated public struct ManualInventoryIntakeResponse: Decodable, Sendable {
    public let product_id: Int
    public let product_name: String
    public let unit: String?
    public let batch_id: Int
    public let quantity: Double
    public let expiration_date: String?
    public let storage_location_id: Int?
    public let replayed: Bool
}

nonisolated public struct PendingManualInventoryIntakeRecord: Codable, Equatable, Sendable {
    public let scopeStorageKey: String
    public let request: ManualInventoryIntakeRequest

    public init(scopeStorageKey: String, request: ManualInventoryIntakeRequest) {
        self.scopeStorageKey = scopeStorageKey
        self.request = request
    }
}

nonisolated public enum PendingManualInventoryIntakeReadResult: Equatable, Sendable {
    case missing
    case record(PendingManualInventoryIntakeRecord)
    case corrupt
    case unavailable
}
