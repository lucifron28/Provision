import Foundation

// MARK: - Shopping List Models
// Conforms to FastAPI app.schemas.shopping

public struct ShoppingItem: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var name: String
    public var product_id: Int?
    public var quantity: Double
    public var unit: String?
    public var is_bought: Bool
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
}

public struct ShoppingItemCreate: Codable, Sendable {
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

public struct ShoppingItemUpdate: Codable, Sendable {
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
