import Foundation

// MARK: - Analytics Models
// Conforms to FastAPI app.schemas.analytics

public struct InventoryValuation: Codable, Sendable {
    public var total_value: Double
    public var total_active_batches: Int
    public var total_active_products: Int
    
    enum CodingKeys: String, CodingKey {
        case total_value
        case total_active_batches
        case total_active_products
    }
    
    public init(total_value: Double = 0, total_active_batches: Int = 0, total_active_products: Int = 0) {
        self.total_value = total_value
        self.total_active_batches = total_active_batches
        self.total_active_products = total_active_products
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let val = try? container.decode(Double.self, forKey: .total_value) {
            total_value = val
        } else if let str = try? container.decode(String.self, forKey: .total_value) {
            total_value = Double(str) ?? 0
        } else {
            total_value = 0
        }
        total_active_batches = try container.decode(Int.self, forKey: .total_active_batches)
        total_active_products = try container.decode(Int.self, forKey: .total_active_products)
    }
}

public struct SpendingSummary: Codable, Sendable {
    public var total_spent: Double
    public var sessions_count: Int
    
    enum CodingKeys: String, CodingKey {
        case total_spent
        case sessions_count
    }
    
    public init(total_spent: Double = 0, sessions_count: Int = 0) {
        self.total_spent = total_spent
        self.sessions_count = sessions_count
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let val = try? container.decode(Double.self, forKey: .total_spent) {
            total_spent = val
        } else if let str = try? container.decode(String.self, forKey: .total_spent) {
            total_spent = Double(str) ?? 0
        } else {
            total_spent = 0
        }
        sessions_count = try container.decode(Int.self, forKey: .sessions_count)
    }
}

public struct WasteSummary: Codable, Sendable {
    public var total_waste_events: Int
    public var total_quantity_wasted: Double
    public var total_financial_loss: Double
    
    enum CodingKeys: String, CodingKey {
        case total_waste_events
        case total_quantity_wasted
        case total_financial_loss
    }
    
    public init(total_waste_events: Int = 0, total_quantity_wasted: Double = 0, total_financial_loss: Double = 0) {
        self.total_waste_events = total_waste_events
        self.total_quantity_wasted = total_quantity_wasted
        self.total_financial_loss = total_financial_loss
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        total_waste_events = try container.decode(Int.self, forKey: .total_waste_events)
        total_quantity_wasted = try container.decode(Double.self, forKey: .total_quantity_wasted)
        if let val = try? container.decode(Double.self, forKey: .total_financial_loss) {
            total_financial_loss = val
        } else if let str = try? container.decode(String.self, forKey: .total_financial_loss) {
            total_financial_loss = Double(str) ?? 0
        } else {
            total_financial_loss = 0
        }
    }
}

public struct ExpiringSoonItem: Codable, Identifiable, Hashable, Sendable {
    public var batch_id: Int
    public var product_id: Int
    public var product_name: String
    public var brand: String?
    public var remaining_quantity: Double
    public var unit: String?
    public var expiration_date: String
    public var days_until_expiration: Int
    public var storage_location: String?
    
    public var id: Int { batch_id }
    
    public var displayQuantity: String {
        if remaining_quantity.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(remaining_quantity))\(unit ?? "")"
        } else {
            return String(format: "%.1f%@", remaining_quantity, unit ?? "")
        }
    }
    
    public var urgencyBadgeText: String {
        if days_until_expiration < 0 {
            return "EXPIRED (\(abs(days_until_expiration))d)"
        } else if days_until_expiration == 0 {
            return "EXPIRES TODAY"
        } else if days_until_expiration == 1 {
            return "EXPIRES TOMORROW"
        } else {
            return "EXPIRES IN \(days_until_expiration)D"
        }
    }
}

public struct LowStockItem: Codable, Identifiable, Hashable, Sendable {
    public var product_id: Int
    public var product_name: String
    public var brand: String?
    public var current_stock: Double
    public var unit: String?
    
    public var id: Int { product_id }
    
    public var displayStock: String {
        if current_stock <= 0 {
            return "Out of stock"
        } else if current_stock.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(current_stock)) \(unit ?? "left")"
        } else {
            return String(format: "%.1f %@", current_stock, unit ?? "left")
        }
    }
}
