import Foundation

// MARK: - API Client
// Concrete, readable URLSession async/await client communicating with the FastAPI backend

public enum APIError: LocalizedError, Sendable {
    case invalidURL
    case networkError(Error)
    case unauthorized
    case invalidResponse(Int, String?)
    case decodingError(Error)
    case serverMessage(String)
    
    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API URL endpoint."
        case .networkError(let error):
            return "Network connection failed: \(error.localizedDescription)"
        case .unauthorized:
            return "Authentication required or token expired."
        case .invalidResponse(let code, let message):
            return "Server responded with status \(code): \(message ?? "No details")"
        case .decodingError(let error):
            return "Failed to parse server response: \(error.localizedDescription)"
        case .serverMessage(let msg):
            return msg
        }
    }
}

public enum APIEnvironment {
    private static let hostKey = "provision_backend_host"
    private static let fallbackHost = "10.212.56.11"

    /// Configurable local LAN host for physical iPhone testing.
    /// Can be customized at runtime via UserDefaults without requiring code recompilation.
    nonisolated(unsafe) public static var localDeviceHost: String {
        get {
            UserDefaults.standard.string(forKey: hostKey) ?? fallbackHost
        }
        set {
            UserDefaults.standard.set(newValue, forKey: hostKey)
        }
    }
    nonisolated(unsafe) public static var port: Int = 8000
    nonisolated(unsafe) public static var apiVersionPath: String = "api/v1"
    nonisolated public static func validateHost(_ host: String) -> URL? {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        guard let url = URL(string: "http://\(trimmed):\(port)/\(apiVersionPath)"),
              url.host != nil else {
            return nil
        }
        return url
    }

    nonisolated public static var defaultBaseURL: URL {
        #if targetEnvironment(simulator)
        return URL(string: "http://127.0.0.1:\(port)/\(apiVersionPath)")!
        #else
        return URL(string: "http://\(localDeviceHost):\(port)/\(apiVersionPath)")!
        #endif
    }
}

public actor APIClient {
    public static let shared = APIClient()
    
    public var baseURL: URL
    public var accessToken: String? = nil
    public private(set) var isOfflineMode: Bool = false
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    public init(baseURL: URL = APIEnvironment.defaultBaseURL, session: URLSession? = nil) {
        self.baseURL = baseURL
        
        if let session = session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 10.0
            config.timeoutIntervalForResource = 30.0
            self.session = URLSession(configuration: config)
        }
        
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }
    
    public func setBaseURL(_ url: URL) {
        self.baseURL = url
    }
    
    public func setAccessToken(_ token: String?) {
        self.accessToken = token
    }
    
    public func clearCache() async {
        isOfflineMode = false
        await LocalCacheStore.shared.clearAll()
    }

    private func isNetworkFailure(_ error: Error) -> Bool {
        switch error {
        case APIError.networkError:
            return true
        case is URLError:
            return true
        default:
            return false
        }
    }

    // MARK: - Generic Request Helper
    
    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        var req = request
        if let token = accessToken, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw APIError.networkError(error)
        }
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse(-1, "Not an HTTP response")
        }
        
        if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
            throw APIError.unauthorized
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
    
    private func executeVoid(_ request: URLRequest) async throws {
        var req = request
        if let token = accessToken, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw APIError.networkError(error)
        }
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse(-1, "Not an HTTP response")
        }
        
        if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
            throw APIError.unauthorized
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            if let errorObj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = errorObj["detail"] as? String {
                throw APIError.serverMessage(detail)
            }
            let rawString = String(data: data, encoding: .utf8)
            throw APIError.invalidResponse(httpResponse.statusCode, rawString)
        }
    }
    
    // MARK: - Authentication
    
    public func register(request: RegisterRequest) async throws -> User {
        let url = baseURL.appendingPathComponent("auth/register")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try encoder.encode(request)
        return try await execute(req)
    }
    
    public func login(request: LoginRequest) async throws -> AuthToken {
        let url = baseURL.appendingPathComponent("auth/login")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try encoder.encode(request)
        return try await execute(req)
    }
    
    public func fetchCurrentUser() async throws -> User {
        let url = baseURL.appendingPathComponent("auth/me")
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        return try await execute(req)
    }
    
    // MARK: - Products
    
    public func fetchProducts(search: String? = nil, category: String? = nil, skip: Int = 0, limit: Int? = 500) async throws -> [Product] {
        var components = URLComponents(url: baseURL.appendingPathComponent("products/"), resolvingAgainstBaseURL: true)
        var queryItems: [URLQueryItem] = []
        if let search = search, !search.trimmingCharacters(in: .whitespaces).isEmpty {
            queryItems.append(URLQueryItem(name: "search", value: search))
        }
        if let category = category, !category.trimmingCharacters(in: .whitespaces).isEmpty {
            queryItems.append(URLQueryItem(name: "category", value: category))
        }
        if skip > 0 {
            queryItems.append(URLQueryItem(name: "skip", value: String(skip)))
        }
        if let limit = limit {
            queryItems.append(URLQueryItem(name: "limit", value: String(limit)))
        }
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        guard let url = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        do {
            let products: [Product] = try await execute(request)
            isOfflineMode = false
            let isUnfiltered = (search == nil || search!.isEmpty) && (category == nil || category!.isEmpty)
            if isUnfiltered {
                await LocalCacheStore.shared.saveProducts(products)
            }
            return products
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let cached = await LocalCacheStore.shared.loadProducts(), !cached.isEmpty {
                isOfflineMode = true
                var result = cached
                if let cat = category, !cat.isEmpty {
                    result = result.filter { $0.category == cat }
                }
                if let s = search, !s.isEmpty {
                    result = result.filter { $0.name.localizedCaseInsensitiveContains(s) || ($0.brand?.localizedCaseInsensitiveContains(s) == true) }
                }
                return result
            }
            throw error
        }
    }
    
    public func createProduct(_ product: ProductCreate) async throws -> Product {
        let url = baseURL.appendingPathComponent("products/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(product)
        return try await execute(request)
    }
    
    public func fetchProduct(id: Int) async throws -> Product {
        let url = baseURL.appendingPathComponent("products/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request)
    }
    
    public func fetchProduct(barcode: String) async throws -> Product? {
        var components = URLComponents(url: baseURL.appendingPathComponent("products/"), resolvingAgainstBaseURL: true)
        components?.queryItems = [URLQueryItem(name: "barcode", value: barcode)]
        guard let url = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        let products: [Product] = try await execute(request)
        return products.first
    }

    public func updateProduct(id: Int, update: ProductUpdate) async throws -> Product {
        let url = baseURL.appendingPathComponent("products/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(update)
        return try await execute(request)
    }
    
    // MARK: - Storage Locations
    
    public func fetchLocations() async throws -> [StorageLocation] {
        let url = baseURL.appendingPathComponent("locations/")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        do {
            let locations: [StorageLocation] = try await execute(request)
            isOfflineMode = false
            await LocalCacheStore.shared.saveLocations(locations)
            return locations
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let cached = await LocalCacheStore.shared.loadLocations(), !cached.isEmpty {
                isOfflineMode = true
                return cached
            }
            throw error
        }
    }

    // MARK: - Grocery Sessions

    public func createSession(_ session: GrocerySessionCreate) async throws -> GrocerySession {
        let url = baseURL.appendingPathComponent("grocery-sessions/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(session)
        return try await execute(request)
    }

    public func commitSession(id: Int, items: [SessionItemCreate]) async throws -> GrocerySession {
        let url = baseURL.appendingPathComponent("grocery-sessions/\(id)/commit")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = CommitSessionRequest(items: items)
        request.httpBody = try encoder.encode(body)
        return try await execute(request)
    }

    public func fetchSessions() async throws -> [GrocerySession] {
        let url = baseURL.appendingPathComponent("grocery-sessions/")
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
        do {
            let batches: [InventoryBatch] = try await execute(request)
            isOfflineMode = false
            if productId == nil {
                await LocalCacheStore.shared.saveBatches(batches)
            }
            return batches
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let cached = await LocalCacheStore.shared.loadBatches(), !cached.isEmpty {
                isOfflineMode = true
                var filtered = cached
                if let pid = productId {
                    filtered = filtered.filter { $0.product_id == pid }
                }
                if activeOnly {
                    filtered = filtered.filter { $0.remaining_quantity > 0 }
                }
                return filtered
            }
            throw error
        }
    }
    
    public func createBatch(_ batch: InventoryBatchCreate) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("batches/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(batch)
        return try await execute(request)
    }
    
    public func updateBatchMetadata(batchId: Int, updates: [String: Any]) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("batches/\(batchId)")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: updates)
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
        do {
            let items: [ShoppingItem] = try await execute(request)
            isOfflineMode = false
            await LocalCacheStore.shared.saveShoppingItems(items)
            return items
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let cached = await LocalCacheStore.shared.loadShoppingItems(), !cached.isEmpty {
                isOfflineMode = true
                return cached
            }
            throw error
        }
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
        try await executeVoid(request)
    }
    
    public func clearCompletedShoppingItems() async throws {
        let url = baseURL.appendingPathComponent("shopping-list/completed/clear")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        try await executeVoid(request)
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
        let url = baseURL.appendingPathComponent("analytics/valuation")
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
