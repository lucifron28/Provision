import Foundation

// MARK: - Local Offline Cache Store
// Provides persistent disk caching for pantry products, batches, locations, and shopping items
// ensuring immediate responsive UI and seamless offline fallback.

public final class LocalCacheStore: @unchecked Sendable {
    public static let shared = LocalCacheStore()
    
    private let fileManager = FileManager.default
    private let cacheQueue = DispatchQueue(label: "mseuf.edu.ph.provision.cache", qos: .utility)
    
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
        loadFromDisk()
    }
    
    // MARK: - Products
    
    public func saveProducts(_ products: [Product]) {
        cacheQueue.async {
            self.cachedProducts = products
            self.writeToDisk(products, filename: "products.json")
        }
    }
    
    public func loadProducts() -> [Product]? {
        if let memory = cachedProducts, !memory.isEmpty {
            return memory
        }
        return readFromDisk([Product].self, filename: "products.json")
    }
    
    // MARK: - Storage Locations
    
    public func saveLocations(_ locations: [StorageLocation]) {
        cacheQueue.async {
            self.cachedLocations = locations
            self.writeToDisk(locations, filename: "locations.json")
        }
    }
    
    public func loadLocations() -> [StorageLocation]? {
        if let memory = cachedLocations, !memory.isEmpty {
            return memory
        }
        return readFromDisk([StorageLocation].self, filename: "locations.json")
    }
    
    // MARK: - Inventory Batches
    
    public func saveBatches(_ batches: [InventoryBatch]) {
        cacheQueue.async {
            self.cachedBatches = batches
            self.writeToDisk(batches, filename: "batches.json")
        }
    }
    
    public func loadBatches() -> [InventoryBatch]? {
        if let memory = cachedBatches, !memory.isEmpty {
            return memory
        }
        return readFromDisk([InventoryBatch].self, filename: "batches.json")
    }
    
    // MARK: - Shopping Items
    
    public func saveShoppingItems(_ items: [ShoppingItem]) {
        cacheQueue.async {
            self.cachedShoppingItems = items
            self.writeToDisk(items, filename: "shopping.json")
        }
    }
    
    public func loadShoppingItems() -> [ShoppingItem]? {
        if let memory = cachedShoppingItems, !memory.isEmpty {
            return memory
        }
        return readFromDisk([ShoppingItem].self, filename: "shopping.json")
    }
    
    // MARK: - Persistence Helpers
    
    private func loadFromDisk() {
        cachedProducts = readFromDisk([Product].self, filename: "products.json")
        cachedLocations = readFromDisk([StorageLocation].self, filename: "locations.json")
        cachedBatches = readFromDisk([InventoryBatch].self, filename: "batches.json")
        cachedShoppingItems = readFromDisk([ShoppingItem].self, filename: "shopping.json")
    }
    
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
