import Foundation

// MARK: - Product Model
// Conforms to FastAPI app.schemas.product.ProductWithStock

public struct Product: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var name: String
    public var brand: String?
    public var barcode: String?
    public var category: String?
    public var package_size: Double?
    public var unit: String?
    public var image_url: String?
    public var source: String?
    public var created_at: String?
    public var updated_at: String?
    
    // Aggregated stock metrics attached by backend
    public var total_remaining_quantity: Double?
    public var active_batches_count: Int?
    
    public init(
        id: Int,
        name: String,
        brand: String? = nil,
        barcode: String? = nil,
        category: String? = nil,
        package_size: Double? = nil,
        unit: String? = nil,
        image_url: String? = nil,
        source: String? = nil,
        created_at: String? = nil,
        updated_at: String? = nil,
        total_remaining_quantity: Double? = 0,
        active_batches_count: Int? = 0
    ) {
        self.id = id
        self.name = name
        self.brand = brand
        self.barcode = barcode
        self.category = category
        self.package_size = package_size
        self.unit = unit
        self.image_url = image_url
        self.source = source
        self.created_at = created_at
        self.updated_at = updated_at
        self.total_remaining_quantity = total_remaining_quantity
        self.active_batches_count = active_batches_count
    }
    
    // MARK: - Display Helpers
    
    public var displayStock: String {
        ProductUnits.formatAmount(total_remaining_quantity ?? 0)
    }
    
    public var displayUnit: String {
        let u = unit?.trimmingCharacters(in: .whitespaces) ?? ""
        return u.isEmpty ? "units" : u
    }
    
    public var subtitle: String {
        var parts: [String] = []
        if let brand = brand, !brand.isEmpty {
            parts.append(brand)
        }
        if let size = package_size, size > 0 {
            let sizeStr = size.truncatingRemainder(dividingBy: 1) == 0 ? "\(Int(size))" : String(format: "%.1f", size)
            if let u = unit, !u.isEmpty {
                parts.append("\(sizeStr) \(u)")
            } else {
                parts.append(sizeStr)
            }
        }
        return parts.isEmpty ? (category ?? "General") : parts.joined(separator: " • ")
    }
    
    public var isOutOfStock: Bool {
        (total_remaining_quantity ?? 0) <= 0
    }
    
    public var isLowStock: Bool {
        let stock = total_remaining_quantity ?? 0
        return stock > 0 && stock <= 2
    }
}

// MARK: - Product Units Helper

public enum ProductUnits {
    public static let measuredUnits: [String] = ["kg", "g", "L", "mL"]
    public static let countUnits: [String] = ["pcs", "cans", "bottles", "packs", "boxes", "bags"]
    public static let allUnits: [String] = ["pcs", "kg", "g", "L", "mL", "cans", "bottles", "packs", "boxes", "bags"]
    
    public static func isMeasured(_ unit: String?) -> Bool {
        guard let unit = unit?.trimmingCharacters(in: .whitespaces) else { return false }
        return measuredUnits.contains(unit)
    }
    
    public static func isCount(_ unit: String?) -> Bool {
        guard let unit = unit?.trimmingCharacters(in: .whitespaces) else { return true }
        return countUnits.contains(unit) || !measuredUnits.contains(unit)
    }
    
    public static func formatAmount(_ qty: Double) -> String {
        if qty.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(qty))"
        }
        let str = String(format: "%.2f", qty)
        if str.hasSuffix("0") {
            return String(format: "%.1f", qty)
        }
        return str
    }
}

public struct ProductCreate: Codable, Sendable {
    public var name: String
    public var brand: String?
    public var barcode: String?
    public var category: String?
    public var package_size: Double?
    public var unit: String?
    public var image_url: String?
    
    public init(name: String, brand: String? = nil, barcode: String? = nil, category: String? = nil, package_size: Double? = nil, unit: String? = nil, image_url: String? = nil) {
        self.name = name
        self.brand = brand
        self.barcode = barcode
        self.category = category
        self.package_size = package_size
        self.unit = unit
        self.image_url = image_url
    }
}
