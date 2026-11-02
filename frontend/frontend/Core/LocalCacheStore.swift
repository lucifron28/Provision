import Foundation
import CryptoKit

/// The server-verified account and household that own persisted client data.
public struct HouseholdScope: Codable, Hashable, Sendable {
    public let userID: Int
    public let householdID: Int
    public let serverID: String

    public init(userID: Int, householdID: Int, serverID: String = "") {
        self.userID = userID
        self.householdID = householdID
        self.serverID = serverID
    }

    public var storageKey: String {
        let server = SHA256.hash(data: Data(serverID.utf8)).map { String(format: "%02x", $0) }.joined()
        return "server-\(server)-user-\(userID)-household-\(householdID)"
    }
}

public actor LocalCacheStore {
    public static let shared = LocalCacheStore()
    private let fileManager = FileManager.default
    private let rootDirectory: URL

    public init(rootDirectory: URL? = nil) {
        self.rootDirectory = rootDirectory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("ProvisionCache", isDirectory: true)
    }

    private func directory(for scope: HouseholdScope) -> URL {
        rootDirectory.appendingPathComponent(scope.storageKey, isDirectory: true)
    }

    private func write<T: Encodable>(_ value: T, filename: String, scope: HouseholdScope) {
        let directory = directory(for: scope)
        do {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
            try JSONEncoder().encode(value).write(to: directory.appendingPathComponent(filename), options: .atomic)
        } catch { }
    }

    private func read<T: Decodable>(_ type: T.Type, filename: String, scope: HouseholdScope) -> T? {
        guard let data = try? Data(contentsOf: directory(for: scope).appendingPathComponent(filename)) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }

    public func saveProducts(_ values: [Product], scope: HouseholdScope) { write(values, filename: "products.json", scope: scope) }
    public func loadProducts(scope: HouseholdScope) -> [Product]? { read([Product].self, filename: "products.json", scope: scope) }
    public func saveLocations(_ values: [StorageLocation], scope: HouseholdScope) { write(values, filename: "locations.json", scope: scope) }
    public func loadLocations(scope: HouseholdScope) -> [StorageLocation]? { read([StorageLocation].self, filename: "locations.json", scope: scope) }
    private func batchFilename(productID: Int?, activeOnly: Bool) -> String {
        let prefix = productID.map { "product-\($0)-" } ?? ""
        return prefix + (activeOnly ? "active-batches.json" : "batches.json")
    }
    public func saveBatches(_ values: [InventoryBatch], productID: Int?, activeOnly: Bool, scope: HouseholdScope) {
        write(values, filename: batchFilename(productID: productID, activeOnly: activeOnly), scope: scope)
    }
    public func loadBatches(productID: Int?, activeOnly: Bool, scope: HouseholdScope) -> [InventoryBatch]? {
        if let exact = read([InventoryBatch].self, filename: batchFilename(productID: productID, activeOnly: activeOnly), scope: scope) { return exact }
        if activeOnly, let all = read([InventoryBatch].self, filename: batchFilename(productID: productID, activeOnly: false), scope: scope) { return all }
        if productID != nil {
            if activeOnly, let active = read([InventoryBatch].self, filename: batchFilename(productID: nil, activeOnly: true), scope: scope) { return active }
            return read([InventoryBatch].self, filename: batchFilename(productID: nil, activeOnly: false), scope: scope)
        }
        return nil
    }
    public func saveShoppingItems(_ values: [ShoppingItem], scope: HouseholdScope) { write(values, filename: "shopping.json", scope: scope) }
    public func loadShoppingItems(scope: HouseholdScope) -> [ShoppingItem]? { read([ShoppingItem].self, filename: "shopping.json", scope: scope) }

    public func clear(scope: HouseholdScope) {
        try? fileManager.removeItem(at: directory(for: scope))
    }
}
