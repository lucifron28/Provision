import Foundation

// MARK: - Storage Location Model

public struct StorageLocation: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var name: String
    public var location_type: String?
    
    public init(id: Int, name: String, location_type: String? = nil) {
        self.id = id
        self.name = name
        self.location_type = location_type
    }
}

// MARK: - Inventory Batch Model
// Conforms to FastAPI app.schemas.batch.InventoryBatchWithDetails

public struct InventoryBatch: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var product_id: Int
    public var storage_location_id: Int?
    public var grocery_session_id: Int?
    public var purchased_at: String?
    public var expiration_date: String?
    public var original_quantity: Double
    public var remaining_quantity: Double
    public var unit_price: Double?
    public var created_at: String?
    public var updated_at: String?
    
    public var product: Product?
    public var storage_location: StorageLocation?
    
    enum CodingKeys: String, CodingKey {
        case id
        case product_id
        case storage_location_id
        case grocery_session_id
        case purchased_at
        case expiration_date
        case original_quantity
        case remaining_quantity
        case unit_price
        case created_at
        case updated_at
        case product
        case storage_location
    }
    
    public init(
        id: Int,
        product_id: Int,
        storage_location_id: Int? = nil,
        grocery_session_id: Int? = nil,
        purchased_at: String? = nil,
        expiration_date: String? = nil,
        original_quantity: Double,
        remaining_quantity: Double,
        unit_price: Double? = nil,
        created_at: String? = nil,
        updated_at: String? = nil,
        product: Product? = nil,
        storage_location: StorageLocation? = nil
    ) {
        self.id = id
        self.product_id = product_id
        self.storage_location_id = storage_location_id
        self.grocery_session_id = grocery_session_id
        self.purchased_at = purchased_at
        self.expiration_date = expiration_date
        self.original_quantity = original_quantity
        self.remaining_quantity = remaining_quantity
        self.unit_price = unit_price
        self.created_at = created_at
        self.updated_at = updated_at
        self.product = product
        self.storage_location = storage_location
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        product_id = try container.decode(Int.self, forKey: .product_id)
        storage_location_id = try container.decodeIfPresent(Int.self, forKey: .storage_location_id)
        grocery_session_id = try container.decodeIfPresent(Int.self, forKey: .grocery_session_id)
        purchased_at = try container.decodeIfPresent(String.self, forKey: .purchased_at)
        expiration_date = try container.decodeIfPresent(String.self, forKey: .expiration_date)
        original_quantity = try container.decode(Double.self, forKey: .original_quantity)
        remaining_quantity = try container.decode(Double.self, forKey: .remaining_quantity)
        
        // Handle Decimal decoded as string or number
        if let priceDouble = try? container.decodeIfPresent(Double.self, forKey: .unit_price) {
            unit_price = priceDouble
        } else if let priceString = try? container.decodeIfPresent(String.self, forKey: .unit_price) {
            unit_price = Double(priceString)
        } else {
            unit_price = nil
        }
        
        created_at = try container.decodeIfPresent(String.self, forKey: .created_at)
        updated_at = try container.decodeIfPresent(String.self, forKey: .updated_at)
        product = try container.decodeIfPresent(Product.self, forKey: .product)
        storage_location = try container.decodeIfPresent(StorageLocation.self, forKey: .storage_location)
    }
    
    // MARK: - Expiration & Display Helpers
    
    public var parsedExpirationDate: Date? {
        guard let expiration_date = expiration_date else { return nil }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter.date(from: expiration_date)
    }
    
    public var daysUntilExpiration: Int? {
        guard let expDate = parsedExpirationDate else { return nil }
        let calendar = Calendar.current
        let startOfToday = calendar.startOfDay(for: Date())
        let startOfExp = calendar.startOfDay(for: expDate)
        let components = calendar.dateComponents([.day], from: startOfToday, to: startOfExp)
        return components.day
    }
    
    public var isExpired: Bool {
        guard let days = daysUntilExpiration else { return false }
        return days < 0
    }
    
    public var formattedExpiration: String {
        guard let expDate = parsedExpirationDate else { return "No Expiry Date" }
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .none
        return formatter.string(from: expDate)
    }
    public var displayExpiration: String {
        formattedExpiration
    }
    
    
    public var expirationBadgeText: String {
        guard let days = daysUntilExpiration else { return "No Expiry" }
        if days < 0 {
            return "EXPIRED (\(abs(days))d ago)"
        } else if days == 0 {
            return "EXPIRES TODAY"
        } else if days == 1 {
            return "EXPIRES TOMORROW"
        } else if days <= 7 {
            return "EXPIRES IN \(days)D"
        } else {
            return formattedExpiration
        }
    }
    
    public var displayQuantity: String {
        if remaining_quantity.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(remaining_quantity))"
        } else {
            return String(format: "%.1f", remaining_quantity)
        }
    }
}
