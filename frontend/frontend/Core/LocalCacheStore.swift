import Foundation

// MARK: - Local Offline Cache Store
// Provides persistent disk caching for pantry products, batches, locations, and shopping items
// ensuring immediate responsive UI and seamless offline fallback.

public actor LocalCacheStore {
    public static let shared = LocalCacheStore()
    
    private let fileManager = FileManager.default
    
    private var cacheDirectory: URL {
        let urls = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)
        let dir = urls[0].appendingPathComponent("ProvisionCache", isDirectory: true)
        if !fileManager.fileExists(atPath: dir.path) {
            try? fileManager.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        return dir
    }
    
    // In-memory hot cache
    private var cachedProducts: [Product]?
    private var cachedLocations: [StorageLocation]?
    private var cachedBatches: [InventoryBatch]?
    private var cachedShoppingItems: [ShoppingItem]?
    
    public init() {
        self.cachedProducts = nil
        self.cachedLocations = nil
        self.cachedBatches = nil
        self.cachedShoppingItems = nil
    }
    
    // MARK: - Products
    
    public func saveProducts(_ products: [Product]) {
        self.cachedProducts = products
        self.writeToDisk(products, filename: "products.json")
    }

    public func mergeProducts(_ products: [Product]) {
        var current = loadProducts() ?? []
        let newIds = Set(products.map { $0.id })
        current.removeAll { newIds.contains($0.id) }
        current.append(contentsOf: products)
        saveProducts(current)
    }
    
    public func loadProducts() -> [Product]? {
        if let memory = cachedProducts, !memory.isEmpty {
            return memory
        }
        let disk = readFromDisk([Product].self, filename: "products.json")
        if let disk = disk {
            cachedProducts = disk
        }
        return disk
    }
    
    // MARK: - Storage Locations
    
    public func saveLocations(_ locations: [StorageLocation]) {
        self.cachedLocations = locations
        self.writeToDisk(locations, filename: "locations.json")
    }
    
    public func loadLocations() -> [StorageLocation]? {
        if let memory = cachedLocations, !memory.isEmpty {
            return memory
        }
        let disk = readFromDisk([StorageLocation].self, filename: "locations.json")
        if let disk = disk {
            cachedLocations = disk
        }
        return disk
    }
    
    // MARK: - Inventory Batches
    
    public func saveBatches(_ batches: [InventoryBatch]) {
        self.cachedBatches = batches
        self.writeToDisk(batches, filename: "batches.json")
    }

    public func mergeBatches(_ batches: [InventoryBatch], forProductId productId: Int? = nil) {
        var current = loadBatches() ?? []
        if let productId = productId {
            current.removeAll { $0.product_id == productId }
            current.append(contentsOf: batches)
        } else {
            let newIds = Set(batches.map { $0.id })
            current.removeAll { newIds.contains($0.id) }
            current.append(contentsOf: batches)
        }
        saveBatches(current)
    }
    
    public func loadBatches() -> [InventoryBatch]? {
        if let memory = cachedBatches, !memory.isEmpty {
            return memory
        }
        let disk = readFromDisk([InventoryBatch].self, filename: "batches.json")
        if let disk = disk {
            cachedBatches = disk
        }
        return disk
    }
    
    // MARK: - Shopping Items
    
    public func saveShoppingItems(_ items: [ShoppingItem]) {
        self.cachedShoppingItems = items
        self.writeToDisk(items, filename: "shopping.json")
    }
    
    public func loadShoppingItems() -> [ShoppingItem]? {
        if let memory = cachedShoppingItems, !memory.isEmpty {
            return memory
        }
        let disk = readFromDisk([ShoppingItem].self, filename: "shopping.json")
        if let disk = disk {
            cachedShoppingItems = disk
        }
        return disk
    }

    // MARK: - Cache Clearing

    public func clearAll() {
        cachedProducts = nil
        cachedLocations = nil
        cachedBatches = nil
        cachedShoppingItems = nil

        let filenames = ["products.json", "locations.json", "batches.json", "shopping.json"]
        for filename in filenames {
            let fileURL = cacheDirectory.appendingPathComponent(filename)
            if fileManager.fileExists(atPath: fileURL.path) {
                try? fileManager.removeItem(at: fileURL)
            }
        }
    }
    
    // MARK: - Persistence Helpers
    
    
    private func writeToDisk<T: Encodable>(_ object: T, filename: String) {
        let fileURL = cacheDirectory.appendingPathComponent(filename)
        do {
            let data = try JSONEncoder().encode(object)
            try data.write(to: fileURL, options: .atomic)
        } catch {}
    }
    
    private func readFromDisk<T: Decodable>(_ type: T.Type, filename: String) -> T? {
        let fileURL = cacheDirectory.appendingPathComponent(filename)
        guard fileManager.fileExists(atPath: fileURL.path) else { return nil }
        do {
            let data = try Data(contentsOf: fileURL)
            return try JSONDecoder().decode(type, from: data)
        } catch {
            return nil
        }
    }
}
