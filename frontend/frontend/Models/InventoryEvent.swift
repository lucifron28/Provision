import Foundation

// MARK: - Consume Schemas

nonisolated public struct ConsumeRequest: Codable, Sendable, Equatable {
    public var product_id: Int
    public var quantity: Double
    public var reason: String?
    public var notes: String?
    public var idempotency_key: String
    
    public init(product_id: Int, quantity: Double, reason: String? = "Household consumption", notes: String? = nil,
                idempotency_key: String = UUID().uuidString) {
        self.product_id = product_id
        self.quantity = quantity
        self.reason = reason
        self.notes = notes
        self.idempotency_key = idempotency_key
    }
}

nonisolated public struct BatchDeduction: Codable, Identifiable, Hashable, Sendable {
    public var batch_id: Int
    public var quantity_deducted: Double
    public var remaining_in_batch: Double
    public var expiration_date: String?
    
    public var id: Int { batch_id }
}

nonisolated public struct ConsumeResponse: Codable, Sendable {
    public var product_id: Int
    public var requested_quantity: Double
    public var total_consumed: Double
    public var batches_deducted: [BatchDeduction]
    public var new_total_stock: Double
}

// MARK: - Discard Schema

nonisolated public struct DiscardRequest: Codable, Sendable, Equatable {
    public var reason: String?
    public var notes: String?
    public var quantity: Double?
    public var expected_updated_at: String?
    public var idempotency_key: String
    
    public init(reason: String? = "Spoiled / Expired", notes: String? = nil, quantity: Double? = nil,
                expected_updated_at: String? = nil, idempotency_key: String = UUID().uuidString) {
        self.reason = reason
        self.notes = notes
        self.quantity = quantity
        self.expected_updated_at = expected_updated_at
        self.idempotency_key = idempotency_key
    }
}

// MARK: - Adjustment Schema

nonisolated public struct AdjustmentRequest: Codable, Sendable, Equatable {
    public var new_remaining_quantity: Double
    public var reason: String
    public var notes: String?
    public var expected_updated_at: String?
    public var idempotency_key: String
    
    public init(new_remaining_quantity: Double, reason: String, notes: String? = nil,
                expected_updated_at: String? = nil, idempotency_key: String = UUID().uuidString) {
        self.new_remaining_quantity = new_remaining_quantity
        self.reason = reason
        self.notes = notes
        self.expected_updated_at = expected_updated_at
        self.idempotency_key = idempotency_key
    }
}

nonisolated public enum PendingInventoryAction: Codable, Equatable, Sendable {
    case consume(ConsumeRequest)
    case discard(batchID: Int, request: DiscardRequest)
    case adjust(batchID: Int, request: AdjustmentRequest)
}

nonisolated public struct PendingInventoryActionRecord: Codable, Equatable, Sendable {
    public let scopeStorageKey: String
    public let action: PendingInventoryAction

    public init(scopeStorageKey: String, action: PendingInventoryAction) {
        self.scopeStorageKey = scopeStorageKey
        self.action = action
    }
}

nonisolated public enum PendingInventoryActionReadResult: Equatable, Sendable {
    case missing
    case record(PendingInventoryActionRecord)
    case corrupt
    case unavailable
}
