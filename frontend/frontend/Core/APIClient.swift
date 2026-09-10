import Foundation

// MARK: - API Client
// Concrete, readable URLSession async/await client communicating with the FastAPI backend

public enum APIError: LocalizedError {
    case invalidURL
    case networkError(Error)
    case invalidResponse(Int, String?)
    case decodingError(Error)
    case serverMessage(String)
    
    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API URL endpoint."
        case .networkError(let error):
            return "Network connection failed: \(error.localizedDescription)"
        case .invalidResponse(let code, let message):
            return "Server responded with status \(code): \(message ?? "No details")"
        case .decodingError(let error):
            return "Failed to parse server response: \(error.localizedDescription)"
        case .serverMessage(let msg):
            return msg
        }
    }
}

public actor APIClient {
    public static let shared = APIClient()
    
    public static func defaultBaseURL() -> URL {
        #if targetEnvironment(simulator)
        return URL(string: "http://127.0.0.1:8000/api/v1")!
        #else
        // Physical iPhone: connect over local Wi-Fi to development Mac
        return URL(string: "http://172.22.67.167:8000/api/v1")!
        #endif
    }
    
    public var baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    
    public init(baseURL: URL = APIClient.defaultBaseURL()) {
        self.baseURL = baseURL
        
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10.0
        config.timeoutIntervalForResource = 30.0
        self.session = URLSession(configuration: config)
        
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }
    
    public func setBaseURL(_ url: URL) {
        self.baseURL = url
    }
    
    // MARK: - Generic Request Helper
    
    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse(-1, "Not an HTTP response")
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            // Attempt to parse FastAPI detail message
            if let errorObj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = errorObj["detail"] as? String {
                throw APIError.serverMessage(detail)
            }
            let rawString = String(data: data, encoding: .utf8)
            throw APIError.invalidResponse(httpResponse.statusCode, rawString)
        }
        
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }
    
    // MARK: - Products
    
    public func fetchProducts(search: String? = nil, category: String? = nil) async throws -> [Product] {
        var components = URLComponents(url: baseURL.appendingPathComponent("products/"), resolvingAgainstBaseURL: true)
        var queryItems: [URLQueryItem] = []
        if let search = search, !search.trimmingCharacters(in: .whitespaces).isEmpty {
            queryItems.append(URLQueryItem(name: "search", value: search))
        }
        if let category = category, !category.trimmingCharacters(in: .whitespaces).isEmpty {
            queryItems.append(URLQueryItem(name: "category", value: category))
        }
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        guard let url = components?.url else { throw APIError.invalidURL }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    public func fetchProduct(id: Int) async throws -> Product {
        let url = baseURL.appendingPathComponent("products/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    // MARK: - Storage Locations
    
    public func fetchLocations() async throws -> [StorageLocation] {
        let url = baseURL.appendingPathComponent("locations/")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    // MARK: - Batches
    
    public func fetchBatches(productId: Int? = nil, activeOnly: Bool = true) async throws -> [InventoryBatch] {
        var components = URLComponents(url: baseURL.appendingPathComponent("batches/"), resolvingAgainstBaseURL: true)
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "active_only", value: activeOnly ? "true" : "false")
        ]
        if let pid = productId {
            queryItems.append(URLQueryItem(name: "product_id", value: "\(pid)"))
        }
        components?.queryItems = queryItems
        guard let url = components?.url else { throw APIError.invalidURL }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    // MARK: - Consume & Discard Operations
    
    public func consumeProduct(productId: Int, quantity: Double, reason: String? = nil, notes: String? = nil) async throws -> ConsumeResponse {
        let url = baseURL.appendingPathComponent("inventory/consume")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ConsumeRequest(product_id: productId, quantity: quantity, reason: reason, notes: notes)
        request.httpBody = try encoder.encode(body)
        return try await execute(request)
    }
    
    public func discardBatch(batchId: Int, reason: String? = nil, notes: String? = nil) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("inventory/batches/\(batchId)/discard")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = DiscardRequest(reason: reason, notes: notes)
        request.httpBody = try encoder.encode(body)
        return try await execute(request)
    }
    
    public func adjustBatch(batchId: Int, newQuantity: Double, reason: String, notes: String? = nil) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("inventory/batches/\(batchId)/adjust")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = AdjustmentRequest(new_remaining_quantity: newQuantity, reason: reason, notes: notes)
        request.httpBody = try encoder.encode(body)
        return try await execute(request)
    }
    
    // MARK: - Shopping List
    
    public func fetchShoppingList() async throws -> [ShoppingItem] {
        let url = baseURL.appendingPathComponent("shopping-list/")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    public func updateShoppingItem(id: Int, update: ShoppingItemUpdate) async throws -> ShoppingItem {
        let url = baseURL.appendingPathComponent("shopping-list/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(update)
        return try await execute(request)
    }
    public func createShoppingItem(_ item: ShoppingItemCreate) async throws -> ShoppingItem {
        let url = baseURL.appendingPathComponent("shopping-list/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(item)
        return try await execute(request)
    }
    
    public func toggleShoppingItem(id: Int) async throws -> ShoppingItem {
        let url = baseURL.appendingPathComponent("shopping-list/\(id)/toggle")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        return try await execute(request)
    }
    
    public func deleteShoppingItem(id: Int) async throws {
        let url = baseURL.appendingPathComponent("shopping-list/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw APIError.invalidResponse(-1, "Failed to delete shopping item")
        }
    }
    
    public func clearCompletedShoppingItems() async throws {
        let url = baseURL.appendingPathComponent("shopping-list/completed/clear")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw APIError.invalidResponse(-1, "Failed to clear completed items")
        }
    }
    
    public func generateShoppingSuggestions(threshold: Double = 1.0) async throws -> [ShoppingItem] {
        let url = baseURL.appendingPathComponent("shopping-list/generate-from-low-stock")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload = ["threshold": threshold]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        return try await execute(request)
    }
    
    // MARK: - Analytics
    
    public func fetchExpiringSoon(days: Int = 7) async throws -> [ExpiringSoonItem] {
        var components = URLComponents(url: baseURL.appendingPathComponent("analytics/expiring-soon"), resolvingAgainstBaseURL: true)
        components?.queryItems = [URLQueryItem(name: "days", value: "\(days)")]
        guard let url = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    public func fetchLowStock(threshold: Double = 2.0) async throws -> [LowStockItem] {
        var components = URLComponents(url: baseURL.appendingPathComponent("analytics/low-stock"), resolvingAgainstBaseURL: true)
        components?.queryItems = [URLQueryItem(name: "threshold", value: "\(threshold)")]
        guard let url = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    public func fetchValuation() async throws -> InventoryValuation {
        let url = baseURL.appendingPathComponent("analytics/inventory-valuation")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    public func fetchSpending() async throws -> SpendingSummary {
        let url = baseURL.appendingPathComponent("analytics/spending")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    public func fetchWaste() async throws -> WasteSummary {
        let url = baseURL.appendingPathComponent("analytics/waste")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
}
