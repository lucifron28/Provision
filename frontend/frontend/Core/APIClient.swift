import Foundation

public enum APIErrorDetail: Decodable, Sendable, Equatable {
    case string(String), number(Double), bool(Bool), object([String: APIErrorDetail]), array([APIErrorDetail]), null

    public init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let object = try? value.decode([String: APIErrorDetail].self) { self = .object(object) }
        else if let array = try? value.decode([APIErrorDetail].self) { self = .array(array) }
        else if let text = try? value.decode(String.self) { self = .string(text) }
        else if let flag = try? value.decode(Bool.self) { self = .bool(flag) }
        else { self = .number(try value.decode(Double.self)) }
    }
}

private struct APIErrorEnvelope: Decodable {
    let detail: APIErrorDetail?
}

// MARK: - API Client
// Concrete, readable URLSession async/await client communicating with the FastAPI backend

public enum APIError: LocalizedError, Sendable {
    case invalidURL
    case sessionChanged
    case networkError(Error)
    case unauthorized
    case http(status: Int, detail: APIErrorDetail?, retryAfter: String?)
    case invalidResponse(Int, String?)
    case decodingError(Error)
    case serverMessage(String)
    
    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API URL endpoint."
        case .sessionChanged:
            return "The account or household changed. Please try again."
        case .networkError(let error):
            return "Network connection failed: \(error.localizedDescription)"
        case .unauthorized:
            return "Authentication required or token expired."
        case .http(let status, _, let retryAfter):
            switch status {
            case 403: return "You do not have access to this household or action."
            case 409: return "The data changed. Refresh and review it before retrying."
            case 422: return "Some information needs correction before retrying."
            case 429: return "Too many requests. Try again later\(retryAfter.map { " (retry after \($0))" } ?? "")."
            case 502, 503, 504: return "The service is temporarily unavailable. Please try again."
            default: return "The server returned an error (\(status))."
            }
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
    private var householdScope: HouseholdScope?
    private var sessionGeneration: UInt64 = 0
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    public init(baseURL: URL = APIEnvironment.defaultBaseURL, session: URLSession? = nil, initialScope: HouseholdScope? = nil) {
        self.baseURL = baseURL
        self.householdScope = initialScope
        
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
        self.encoder.outputFormatting = [.sortedKeys]
    }
    
    public func setBaseURL(_ url: URL) {
        if self.baseURL != url {
            sessionGeneration &+= 1
            householdScope = nil
            accessToken = nil
        }
        self.baseURL = url
    }

    public func currentServerID() -> String { baseURL.absoluteString }
    
    public func setAccessToken(_ token: String?) {
        if self.accessToken != token {
            sessionGeneration &+= 1
            householdScope = nil
        }
        self.accessToken = token
    }

    public func setHouseholdScope(_ scope: HouseholdScope?) {
        if householdScope != scope { sessionGeneration &+= 1 }
        householdScope = scope
        isOfflineMode = false
    }
    
    public func clearCache() async {
        isOfflineMode = false
        if let scope = householdScope { await LocalCacheStore.shared.clear(scope: scope) }
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

    private func fetchAllPages<T: Decodable & Identifiable>(
        _ original: URLComponents, start: Int = 0, pageSize: Int = 100, generation: UInt64,
        expectedScope: HouseholdScope? = nil, offsetName: String = "skip"
    ) async throws -> [T] where T.ID == Int {
        var offset = start
        var items: [T] = []
        var seen = Set<Int>()
        while true {
            guard generation == sessionGeneration else { throw APIError.sessionChanged }
            var components = original
            var query = (components.queryItems ?? []).filter { $0.name != "skip" && $0.name != "offset" && $0.name != "limit" }
            query.append(URLQueryItem(name: offsetName, value: String(offset)))
            query.append(URLQueryItem(name: "limit", value: String(pageSize)))
            components.queryItems = query
            guard let url = components.url else { throw APIError.invalidURL }
            let page: [T] = try await execute(URLRequest(url: url), expectedScope: expectedScope)
            guard page.count <= pageSize, page.allSatisfy({ seen.insert($0.id).inserted }) else {
                throw APIError.invalidResponse(502, "Inconsistent paginated response")
            }
            items.append(contentsOf: page)
            if page.count < pageSize { return items }
            guard offset <= Int.max - pageSize else { throw APIError.invalidResponse(502, "Pagination overflow") }
            offset += pageSize
        }
    }

    // MARK: - Generic Request Helper
    
    private func execute<T: Decodable>(_ request: URLRequest, expectedScope: HouseholdScope? = nil) async throws -> T {
        if let expectedScope, expectedScope != householdScope { throw APIError.sessionChanged }
        var req = request
        let generation = sessionGeneration
        if let scope = householdScope, req.value(forHTTPHeaderField: "X-Household-ID") == nil {
            req.setValue(String(scope.householdID), forHTTPHeaderField: "X-Household-ID")
        }
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
        
        guard generation == sessionGeneration else { throw APIError.sessionChanged }
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse(-1, "Not an HTTP response")
        }
        
        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            // Attempt to parse FastAPI detail message
            let detail = (try? decoder.decode(APIErrorEnvelope.self, from: data))?.detail
            throw APIError.http(status: httpResponse.statusCode, detail: detail,
                                retryAfter: httpResponse.value(forHTTPHeaderField: "Retry-After"))
        }
        
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }
    
    private func executeVoid(_ request: URLRequest, expectedScope: HouseholdScope? = nil) async throws {
        if let expectedScope, expectedScope != householdScope { throw APIError.sessionChanged }
        var req = request
        let generation = sessionGeneration
        if let scope = householdScope, req.value(forHTTPHeaderField: "X-Household-ID") == nil {
            req.setValue(String(scope.householdID), forHTTPHeaderField: "X-Household-ID")
        }
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
        
        guard generation == sessionGeneration else { throw APIError.sessionChanged }
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse(-1, "Not an HTTP response")
        }
        
        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let detail = (try? decoder.decode(APIErrorEnvelope.self, from: data))?.detail
            throw APIError.http(status: httpResponse.statusCode, detail: detail,
                                retryAfter: httpResponse.value(forHTTPHeaderField: "Retry-After"))
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

    public func fetchHouseholds() async throws -> [HouseholdMembership] {
        let url = baseURL.appendingPathComponent("households/")
        return try await execute(URLRequest(url: url))
    }

    /// Only switch after the server confirms membership for the requested household.
    public func selectHousehold(_ householdID: Int, userID: Int) async throws -> HouseholdScope {
        let url = baseURL.appendingPathComponent("households/current")
        var request = URLRequest(url: url)
        request.setValue(String(householdID), forHTTPHeaderField: "X-Household-ID")
        let household: HouseholdContext = try await execute(request)
        guard household.id == householdID else { throw APIError.invalidResponse(502, "Household mismatch") }
        let scope = HouseholdScope(userID: userID, householdID: householdID, serverID: baseURL.absoluteString)
        setHouseholdScope(scope)
        return scope
    }
    
    // MARK: - Products
    
    public func fetchProducts(search: String? = nil, category: String? = nil, skip: Int = 0, limit: Int? = 500, expectedScope: HouseholdScope? = nil) async throws -> [Product] {
        guard skip >= 0, limit == nil || limit! > 0 else { throw APIError.invalidURL }
        if let expectedScope, expectedScope != householdScope { throw APIError.sessionChanged }
        let scope = householdScope
        let generation = sessionGeneration
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
        do {
            guard let components else { throw APIError.invalidURL }
            let products: [Product] = try await fetchAllPages(components, start: skip, pageSize: max(1, min(limit ?? 100, 100)), generation: generation, expectedScope: expectedScope)
            isOfflineMode = false
            let isUnfiltered = (search == nil || search!.isEmpty) && (category == nil || category!.isEmpty)
            if isUnfiltered && skip == 0 {
                if let scope { await LocalCacheStore.shared.saveProducts(products, scope: scope) }
            }
            guard generation == sessionGeneration else { throw APIError.sessionChanged }
            return products
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let scope, scope == householdScope, let cached = await LocalCacheStore.shared.loadProducts(scope: scope) {
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                isOfflineMode = true
                var result = cached
                if let cat = category, !cat.isEmpty {
                    result = result.filter { $0.category == cat }
                }
                if let s = search, !s.isEmpty {
                    result = result.filter { $0.name.localizedCaseInsensitiveContains(s) || ($0.brand?.localizedCaseInsensitiveContains(s) == true) }
                }
                if skip > 0 { result = Array(result.dropFirst(skip)) }
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                return result
            }
            throw error
        }
    }
    
    public func createProduct(_ product: ProductCreate, expectedScope: HouseholdScope? = nil) async throws -> Product {
        let url = baseURL.appendingPathComponent("products/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(product)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func fetchProduct(id: Int, expectedScope: HouseholdScope? = nil) async throws -> Product {
        let url = baseURL.appendingPathComponent("products/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func fetchProduct(barcode: String, expectedScope: HouseholdScope? = nil) async throws -> Product? {
        var components = URLComponents(url: baseURL.appendingPathComponent("products/"), resolvingAgainstBaseURL: true)
        components?.queryItems = [URLQueryItem(name: "barcode", value: barcode)]
        guard let url = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        let products: [Product] = try await execute(request, expectedScope: expectedScope)
        return products.first
    }

    public func updateProduct(id: Int, update: ProductUpdate, expectedScope: HouseholdScope? = nil) async throws -> Product {
        let url = baseURL.appendingPathComponent("products/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(update)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    // MARK: - Storage Locations
    
    public func fetchLocations(expectedScope: HouseholdScope? = nil) async throws -> [StorageLocation] {
        if let expectedScope, expectedScope != householdScope { throw APIError.sessionChanged }
        let scope = householdScope
        let generation = sessionGeneration
        guard let components = URLComponents(url: baseURL.appendingPathComponent("locations/"), resolvingAgainstBaseURL: true) else { throw APIError.invalidURL }
        do {
            let locations: [StorageLocation] = try await fetchAllPages(components, generation: generation, expectedScope: expectedScope)
            isOfflineMode = false
            if let scope { await LocalCacheStore.shared.saveLocations(locations, scope: scope) }
            guard generation == sessionGeneration else { throw APIError.sessionChanged }
            return locations
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let scope, scope == householdScope, let cached = await LocalCacheStore.shared.loadLocations(scope: scope) {
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                isOfflineMode = true
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                return cached
            }
            throw error
        }
    }

    // MARK: - Grocery Sessions

    public func createSession(_ session: GrocerySessionCreate, expectedScope: HouseholdScope) async throws -> GrocerySession {
        let url = baseURL.appendingPathComponent("grocery-sessions/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(session)
        return try await execute(request, expectedScope: expectedScope)
    }

    public func commitSession(id: Int, items: [SessionItemCreate], expectedScope: HouseholdScope) async throws -> GrocerySession {
        let url = baseURL.appendingPathComponent("grocery-sessions/\(id)/commit")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = CommitSessionRequest(items: items)
        request.httpBody = try encoder.encode(body)
        return try await execute(request, expectedScope: expectedScope)
    }

    public func fetchSession(id: Int, expectedScope: HouseholdScope) async throws -> GrocerySession {
        let url = baseURL.appendingPathComponent("grocery-sessions/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }

    public func cancelSession(id: Int, expectedScope: HouseholdScope) async throws -> GrocerySession {
        let url = baseURL.appendingPathComponent("grocery-sessions/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        return try await execute(request, expectedScope: expectedScope)
    }

    public func fetchSessions(expectedScope: HouseholdScope? = nil) async throws -> [GrocerySession] {
        let url = baseURL.appendingPathComponent("grocery-sessions/")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }

    public func fetchRecipes(query: String? = nil, scope: HouseholdScope) async throws -> [HouseholdRecipe] {
        guard scope == householdScope else { throw APIError.sessionChanged }
        var components = URLComponents(url: baseURL.appendingPathComponent("recipes/"), resolvingAgainstBaseURL: true)
        if let query, !query.isEmpty { components?.queryItems = [URLQueryItem(name: "query", value: query)] }
        guard let components else { throw APIError.invalidURL }
        return try await fetchAllPages(components, generation: sessionGeneration, expectedScope: scope, offsetName: "offset")
    }

    public func fetchRecipe(id: Int, scope: HouseholdScope) async throws -> HouseholdRecipe {
        let url = baseURL.appendingPathComponent("recipes/\(id)")
        return try await execute(URLRequest(url: url), expectedScope: scope)
    }

    public func evaluateRecipe(id: Int, payload: RecipeEvaluationRequest, scope: HouseholdScope) async throws -> RecipeEvaluation {
        let url = baseURL.appendingPathComponent("recipes/\(id)/evaluate")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(payload)
        return try await execute(request, expectedScope: scope)
    }

    public func recommendRecipes(_ payload: RecipeRecommendationRequest, scope: HouseholdScope) async throws -> RecipeRecommendations {
        let url = baseURL.appendingPathComponent("recipes/recommendations")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(payload)
        return try await execute(request, expectedScope: scope)
    }

    public func previewRecipeShopping(_ payload: RecipeShoppingPreviewRequest, scope: HouseholdScope) async throws -> RecipeShoppingPreview {
        let url = baseURL.appendingPathComponent("recipe-shopping/preview")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(payload)
        return try await execute(request, expectedScope: scope)
    }

    public func confirmRecipeShopping(_ payload: RecipeShoppingConfirmation, scope: HouseholdScope) async throws -> RecipeShoppingConfirmationResult {
        let url = baseURL.appendingPathComponent("recipe-shopping/confirm")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(payload)
        return try await execute(request, expectedScope: scope)
    }

    // MARK: - Batches
    
    public func fetchBatches(productId: Int? = nil, activeOnly: Bool = true, expectedScope: HouseholdScope? = nil) async throws -> [InventoryBatch] {
        if let expectedScope, expectedScope != householdScope { throw APIError.sessionChanged }
        let scope = householdScope
        let generation = sessionGeneration
        var components = URLComponents(url: baseURL.appendingPathComponent("batches/"), resolvingAgainstBaseURL: true)
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "active_only", value: activeOnly ? "true" : "false")
        ]
        if let pid = productId {
            queryItems.append(URLQueryItem(name: "product_id", value: "\(pid)"))
        }
        components?.queryItems = queryItems
        do {
            guard let components else { throw APIError.invalidURL }
            let batches: [InventoryBatch] = try await fetchAllPages(components, generation: generation, expectedScope: expectedScope)
            isOfflineMode = false
            if let scope { await LocalCacheStore.shared.saveBatches(batches, productID: productId, activeOnly: activeOnly, scope: scope) }
            guard generation == sessionGeneration else { throw APIError.sessionChanged }
            return batches
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let scope, scope == householdScope, let cached = await LocalCacheStore.shared.loadBatches(productID: productId, activeOnly: activeOnly, scope: scope) {
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                isOfflineMode = true
                var filtered = cached
                if let pid = productId {
                    filtered = filtered.filter { $0.product_id == pid }
                }
                if activeOnly {
                    filtered = filtered.filter { $0.remaining_quantity > 0 }
                }
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                return filtered
            }
            throw error
        }
    }
    
    public func createBatch(_ batch: InventoryBatchCreate, expectedScope: HouseholdScope? = nil) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("batches/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(batch)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func updateBatchMetadata(batchId: Int, updates: [String: Any], expectedScope: HouseholdScope? = nil) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("batches/\(batchId)")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: updates)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    // MARK: - Consume & Discard Operations
    
    public func consumeProduct(productId: Int, quantity: Double, reason: String? = nil, notes: String? = nil, expectedScope: HouseholdScope? = nil) async throws -> ConsumeResponse {
        let url = baseURL.appendingPathComponent("inventory/consume")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ConsumeRequest(product_id: productId, quantity: quantity, reason: reason, notes: notes)
        request.httpBody = try encoder.encode(body)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func discardBatch(batchId: Int, reason: String? = nil, notes: String? = nil, expectedScope: HouseholdScope? = nil) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("inventory/batches/\(batchId)/discard")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = DiscardRequest(reason: reason, notes: notes)
        request.httpBody = try encoder.encode(body)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func adjustBatch(batchId: Int, newQuantity: Double, reason: String, notes: String? = nil, expectedScope: HouseholdScope? = nil) async throws -> InventoryBatch {
        let url = baseURL.appendingPathComponent("inventory/batches/\(batchId)/adjust")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = AdjustmentRequest(new_remaining_quantity: newQuantity, reason: reason, notes: notes)
        request.httpBody = try encoder.encode(body)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    // MARK: - Shopping List
    
    public func fetchShoppingList(expectedScope: HouseholdScope? = nil) async throws -> [ShoppingItem] {
        if let expectedScope, expectedScope != householdScope { throw APIError.sessionChanged }
        let scope = householdScope
        let generation = sessionGeneration
        guard let components = URLComponents(url: baseURL.appendingPathComponent("shopping-list/"), resolvingAgainstBaseURL: true) else { throw APIError.invalidURL }
        do {
            let items: [ShoppingItem] = try await fetchAllPages(components, generation: generation, expectedScope: expectedScope)
            isOfflineMode = false
            if let scope { await LocalCacheStore.shared.saveShoppingItems(items, scope: scope) }
            guard generation == sessionGeneration else { throw APIError.sessionChanged }
            return items
        } catch {
            guard isNetworkFailure(error) else {
                throw error
            }
            if let scope, scope == householdScope, let cached = await LocalCacheStore.shared.loadShoppingItems(scope: scope) {
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                isOfflineMode = true
                guard generation == sessionGeneration else { throw APIError.sessionChanged }
                return cached
            }
            throw error
        }
    }
    
    public func updateShoppingItem(id: Int, update: ShoppingItemUpdate, expectedScope: HouseholdScope? = nil) async throws -> ShoppingItem {
        let url = baseURL.appendingPathComponent("shopping-list/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(update)
        return try await execute(request, expectedScope: expectedScope)
    }
    public func createShoppingItem(_ item: ShoppingItemCreate, expectedScope: HouseholdScope? = nil) async throws -> ShoppingItem {
        let url = baseURL.appendingPathComponent("shopping-list/")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(item)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func toggleShoppingItem(id: Int, expectedScope: HouseholdScope? = nil) async throws -> ShoppingItem {
        let url = baseURL.appendingPathComponent("shopping-list/\(id)/toggle")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func deleteShoppingItem(id: Int, expectedScope: HouseholdScope? = nil) async throws {
        let url = baseURL.appendingPathComponent("shopping-list/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        try await executeVoid(request, expectedScope: expectedScope)
    }
    
    public func clearCompletedShoppingItems(expectedScope: HouseholdScope? = nil) async throws {
        let url = baseURL.appendingPathComponent("shopping-list/completed/clear")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        try await executeVoid(request, expectedScope: expectedScope)
    }
    
    public func generateShoppingSuggestions(threshold: Double = 1.0, expectedScope: HouseholdScope? = nil) async throws -> [ShoppingItem] {
        let url = baseURL.appendingPathComponent("shopping-list/generate-from-low-stock")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload = ["threshold": threshold]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        return try await execute(request, expectedScope: expectedScope)
    }
    
    // MARK: - Analytics
    
    public func fetchExpiringSoon(days: Int = 7, expectedScope: HouseholdScope? = nil) async throws -> [ExpiringSoonItem] {
        var components = URLComponents(url: baseURL.appendingPathComponent("analytics/expiring-soon"), resolvingAgainstBaseURL: true)
        components?.queryItems = [URLQueryItem(name: "days", value: "\(days)")]
        guard let url = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func fetchLowStock(threshold: Double = 2.0, expectedScope: HouseholdScope? = nil) async throws -> [LowStockItem] {
        var components = URLComponents(url: baseURL.appendingPathComponent("analytics/low-stock"), resolvingAgainstBaseURL: true)
        components?.queryItems = [URLQueryItem(name: "threshold", value: "\(threshold)")]
        guard let url = components?.url else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func fetchValuation(expectedScope: HouseholdScope? = nil) async throws -> InventoryValuation {
        let url = baseURL.appendingPathComponent("analytics/valuation")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func fetchSpending(expectedScope: HouseholdScope? = nil) async throws -> SpendingSummary {
        let url = baseURL.appendingPathComponent("analytics/spending")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }
    
    public func fetchWaste(expectedScope: HouseholdScope? = nil) async throws -> WasteSummary {
        let url = baseURL.appendingPathComponent("analytics/waste")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await execute(request, expectedScope: expectedScope)
    }
}
