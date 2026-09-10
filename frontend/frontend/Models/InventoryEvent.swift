import Foundation

// MARK: - Consume Schemas

public struct ConsumeRequest: Codable, Sendable {
    public var product_id: Int
    public var quantity: Double
    public var reason: String?
    public var notes: String?
    
    public init(product_id: Int, quantity: Double, reason: String? = "Household consumption", notes: String? = nil) {
        self.product_id = product_id
        self.quantity = quantity
        self.reason = reason
        self.notes = notes
    }
}

public struct BatchDeduction: Codable, Identifiable, Hashable, Sendable {
    public var batch_id: Int
    public var quantity_deducted: Double
    public var remaining_in_batch: Double
    public var expiration_date: String?
    
    public var id: Int { batch_id }
}

public struct ConsumeResponse: Codable, Sendable {
    public var product_id: Int
    public var requested_quantity: Double
    public var total_consumed: Double
    public var batches_deducted: [BatchDeduction]
    public var new_total_stock: Double
}

// MARK: - Discard Schema

public struct DiscardRequest: Codable, Sendable {
    public var reason: String?
    public var notes: String?
    
    public init(reason: String? = "Spoiled / Expired", notes: String? = nil) {
        self.reason = reason
        self.notes = notes
    }
}

// MARK: - Adjustment Schema

public struct AdjustmentRequest: Codable, Sendable {
    public var new_remaining_quantity: Double
    public var reason: String
    public var notes: String?
    
    public init(new_remaining_quantity: Double, reason: String, notes: String? = nil) {
        self.new_remaining_quantity = new_remaining_quantity
        self.reason = reason
        self.notes = notes
    }
}
