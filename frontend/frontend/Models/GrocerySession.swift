import Foundation

// MARK: - Grocery Session Models
// Conforms to FastAPI app.schemas.session

public struct GrocerySession: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var store_name: String
    public var purchase_date: String
    public var total_amount: Double?
    public var status: String
    public var notes: String?
    public var created_at: String?
    public var updated_at: String?
    public var batches: [InventoryBatch]?
    
    public init(
        id: Int,
        store_name: String,
        purchase_date: String,
        total_amount: Double? = nil,
        status: String = "COMPLETED",
        notes: String? = nil,
        created_at: String? = nil,
        updated_at: String? = nil,
        batches: [InventoryBatch]? = nil
    ) {
        self.id = id
        self.store_name = store_name
        self.purchase_date = purchase_date
        self.total_amount = total_amount
        self.status = status
        self.notes = notes
        self.created_at = created_at
        self.updated_at = updated_at
        self.batches = batches
    }
}

public struct GrocerySessionCreate: Codable, Sendable {
    public var store_name: String
    public var purchase_date: String?
    public var total_amount: Double?
    public var notes: String?
    
    public init(
        store_name: String,
        purchase_date: String? = nil,
        total_amount: Double? = nil,
        notes: String? = nil
    ) {
        self.store_name = store_name
        self.purchase_date = purchase_date
        self.total_amount = total_amount
        self.notes = notes
    }
}

public struct SessionItemCreate: Codable, Sendable {
    public var product_id: Int
    public var storage_location_id: Int?
    public var quantity: Double
    public var expiration_date: String?
    public var unit_price: Double?
    
    public init(
        product_id: Int,
        storage_location_id: Int? = nil,
        quantity: Double,
        expiration_date: String? = nil,
        unit_price: Double? = nil
    ) {
        self.product_id = product_id
        self.storage_location_id = storage_location_id
        self.quantity = quantity
        self.expiration_date = expiration_date
        self.unit_price = unit_price
    }
}

public struct CommitSessionRequest: Codable, Sendable {
    public var items: [SessionItemCreate]
    
    public init(items: [SessionItemCreate]) {
        self.items = items
    }
}
