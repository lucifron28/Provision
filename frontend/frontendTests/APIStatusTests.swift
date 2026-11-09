import XCTest
@testable import frontend

private final class HTTPStatusProtocol: URLProtocol {
    nonisolated(unsafe) static var statusCode = 401

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        if Self.statusCode == 0 {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.statusCode,
                                       httpVersion: nil, headerFields: ["Content-Type": "application/json", "Retry-After": "30"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"detail":{"code":"HOUSEHOLD_ACCESS_DENIED"}}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private final class MemoryCredentialStore: CredentialStore {
    private var token: String?
    private var session: VerifiedHouseholdSession?
    func saveAccessToken(_ value: String) -> Bool { token = value; return true }
    func readAccessToken() -> String? { token }
    func deleteAccessToken() -> Bool { token = nil; return true }
    func saveVerifiedSession(_ value: VerifiedHouseholdSession) -> Bool { session = value; return true }
    func readVerifiedSession() -> VerifiedHouseholdSession? { session }
    func deleteVerifiedSession() { session = nil }
}

final class APIStatusTests: XCTestCase {
    func testUserDecodesDefaultHousehold() throws {
        let data = Data(#"{"id":7,"email":"a@example.org","display_name":null,"is_active":true,"created_at":"2026-11-02T00:00:00Z","default_household_id":42,"default_household_name":"Family"}"#.utf8)
        let user = try JSONDecoder().decode(User.self, from: data)
        XCTAssertEqual(user.id, 7)
        XCTAssertEqual(user.default_household_id, 42)
        XCTAssertEqual(user.default_household_name, "Family")
    }

    func testUnauthorizedAndForbiddenRemainDistinct() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HTTPStatusProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
                               session: URLSession(configuration: configuration))
        HTTPStatusProtocol.statusCode = 401
        do {
            _ = try await client.fetchCurrentUser()
            XCTFail("Expected 401")
        } catch APIError.unauthorized {
            // Authentication is invalid.
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
        HTTPStatusProtocol.statusCode = 403
        do {
            _ = try await client.fetchCurrentUser()
            XCTFail("Expected 403")
        } catch APIError.http(let status, let detail, _) {
            XCTAssertEqual(status, 403)
            XCTAssertEqual(detail, APIErrorDetail.object(["code": .string("HOUSEHOLD_ACCESS_DENIED")]))
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testStructuredErrorsKeepStatusAndRetryHeader() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HTTPStatusProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
                               session: URLSession(configuration: configuration))
        for expected in [409, 422, 429, 502, 503, 504] {
            HTTPStatusProtocol.statusCode = expected
            do {
                _ = try await client.fetchCurrentUser()
                XCTFail("Expected HTTP error \(expected)")
            } catch APIError.http(let status, let detail, let retryAfter) {
                XCTAssertEqual(status, expected)
                XCTAssertEqual(detail, APIErrorDetail.object(["code": .string("HOUSEHOLD_ACCESS_DENIED")]))
                XCTAssertEqual(retryAfter, "30")
            } catch {
                XCTFail("Unexpected error: \(error)")
            }
        }
    }
}

private final class PaginationProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let url = request.url!
        let parts = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        let offset = Int(parts.queryItems?.first(where: { $0.name == "skip" })?.value ?? "0") ?? 0
        let size = Int(parts.queryItems?.first(where: { $0.name == "limit" })?.value ?? "100") ?? 100
        let status = request.value(forHTTPHeaderField: "X-Household-ID") == "7" ? 200 : 403
        let end = min(135, offset + size)
        let ids = offset < end ? Array(offset..<end) : []
        let rows: [[String: Any]] = ids.map { id in
            if url.path.contains("batches") {
                return ["id": id + 1, "product_id": id + 1, "original_quantity": 1, "remaining_quantity": 1]
            }
            if url.path.contains("shopping-list") {
                return ["id": id + 1, "name": "Item \(id)", "quantity": 1, "is_bought": false]
            }
            return ["id": id + 1, "name": "Product \(id)"]
        }
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: try! JSONSerialization.data(withJSONObject: rows))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

extension APIStatusTests {
    @MainActor
    func testNetworkFailurePreservesCredentialsButUnauthorizedClearsThem() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HTTPStatusProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
                               session: URLSession(configuration: configuration))
        let keychain = MemoryCredentialStore()
        XCTAssertTrue(keychain.saveAccessToken("saved-token"))
        let viewModel = AuthViewModel(client: client, keychain: keychain)
        HTTPStatusProtocol.statusCode = 0
        await viewModel.checkExistingSession()
        XCTAssertEqual(keychain.readAccessToken(), "saved-token")
        XCTAssertEqual(viewModel.authState, .sessionUnavailable)
        HTTPStatusProtocol.statusCode = 403
        await viewModel.checkExistingSession()
        XCTAssertEqual(keychain.readAccessToken(), "saved-token")
        XCTAssertEqual(viewModel.authState, .sessionUnavailable)
        HTTPStatusProtocol.statusCode = 401
        await viewModel.checkExistingSession()
        XCTAssertNil(keychain.readAccessToken())
        XCTAssertEqual(viewModel.authState, .signedOut)
    }

    func testCollectionsFetchBeyondOneHundredAndSendHousehold() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PaginationProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
            session: URLSession(configuration: configuration),
            initialScope: HouseholdScope(userID: 3, householdID: 7))
        let products = try await client.fetchProducts()
        let locations = try await client.fetchLocations()
        let batches = try await client.fetchBatches()
        let shopping = try await client.fetchShoppingList()
        XCTAssertEqual(products.count, 135)
        XCTAssertEqual(locations.count, 135)
        XCTAssertEqual(batches.count, 135)
        XCTAssertEqual(shopping.count, 135)
    }

    func testScopedCachesDoNotCrossAccountsOrHouseholds() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let cache = LocalCacheStore(rootDirectory: root)
        let first = HouseholdScope(userID: 1, householdID: 9)
        let otherHousehold = HouseholdScope(userID: 1, householdID: 10)
        let otherUser = HouseholdScope(userID: 2, householdID: 9)
        let otherServer = HouseholdScope(userID: 1, householdID: 9, serverID: "https://other.example.org/api/v1")
        await cache.saveProducts([Product(id: 1, name: "Private")], scope: first)
        let restored = await cache.loadProducts(scope: first)
        let foreignHousehold = await cache.loadProducts(scope: otherHousehold)
        let foreignUser = await cache.loadProducts(scope: otherUser)
        let foreignServer = await cache.loadProducts(scope: otherServer)
        XCTAssertEqual(restored?.first?.name, "Private")
        XCTAssertNil(foreignHousehold)
        XCTAssertNil(foreignUser)
        XCTAssertNil(foreignServer)
    }

    @MainActor
    func testUnownedLegacyIntakeIsLockedWithoutReplaying() throws {
        let suite = "provision.scope-test.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let original = Data("legacy private intake".utf8)
        defaults.set(original, forKey: pendingIntakeCommitStorageKey)
        let vm = ScanViewModel(isPreview: false, pendingCommitDefaults: defaults,
            scope: HouseholdScope(userID: 1, householdID: 9))
        XCTAssertTrue(vm.hasPendingCommitRecovery)
        XCTAssertTrue(vm.scannedItems.isEmpty)
        XCTAssertEqual(defaults.data(forKey: pendingIntakeCommitStorageKey), original)
    }
}

extension APIStatusTests {
    func testExactQuantityAndConfirmationRoundTrip() throws {
        let quantity = ExactQuantity(Decimal(string: "0.123456")!)
        let payload = RecipeShoppingConfirmation(previewID: "preview-token", idempotencyKey: "retry-key-123",
            revision: 4, acceptedLines: [RecipeShoppingAcceptedLine(ingredientID: 3, target: quantity)])
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let first = try encoder.encode(payload)
        let restored = try JSONDecoder().decode(RecipeShoppingConfirmation.self, from: first)
        XCTAssertEqual(try encoder.encode(restored), first)
        XCTAssertEqual(restored.accepted_lines[0].target_quantity, quantity)
        XCTAssertTrue(String(decoding: first, as: UTF8.self).contains("0.123456"))
        XCTAssertEqual(restored.idempotency_key, "retry-key-123")
    }

    func testOfflineSessionRequiresSameUnexpiredVerifiedTokenAndHousehold() throws {
        func token(expires: Int) -> String {
            let data = Data("{\"exp\":\(expires)}".utf8)
            let payload = data.base64EncodedString().replacingOccurrences(of: "+", with: "-")
                .replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
            return "header.\(payload).signature"
        }
        let current = token(expires: 2_000_000_000)
        let user = User(id: 1, email: "person@example.org")
        let household = HouseholdMembership(id: 9, name: "Family", role: "OWNER", is_default: true)
        let verified = VerifiedHouseholdSession(token: current, user: user,
            scope: HouseholdScope(userID: 1, householdID: 9), households: [household])
        XCTAssertTrue(verified.isUsableOffline(token: current, now: Date(timeIntervalSince1970: 1_900_000_000)))
        XCTAssertFalse(verified.isUsableOffline(token: "different", now: Date(timeIntervalSince1970: 1_900_000_000)))
        XCTAssertFalse(verified.isUsableOffline(token: current, now: Date(timeIntervalSince1970: 2_000_000_001)))
        let wrongHousehold = VerifiedHouseholdSession(token: current, user: user,
            scope: HouseholdScope(userID: 1, householdID: 10), households: [household])
        XCTAssertFalse(wrongHousehold.isUsableOffline(token: current, now: Date(timeIntervalSince1970: 1_900_000_000)))
    }

    @MainActor
    func testPendingIntakeRestoresOnlyForItsOwner() throws {
        let suite = "provision.pending-scope.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let scope = HouseholdScope(userID: 1, householdID: 9)
        let pending = PendingIntakeCommit(sessionID: 12, fingerprint: "saved", storeName: "Market",
            intakeItems: [], requestItems: [])
        defaults.set(try JSONEncoder().encode(pending), forKey: scopedPendingIntakeCommitStorageKey(for: scope))
        let owner = ScanViewModel(isPreview: false, pendingCommitDefaults: defaults, scope: scope)
        let other = ScanViewModel(isPreview: false, pendingCommitDefaults: defaults,
            scope: HouseholdScope(userID: 2, householdID: 9))
        XCTAssertEqual(owner.pendingDraftSessionId, 12)
        XCTAssertTrue(owner.hasPendingCommitRecovery)
        XCTAssertNil(other.pendingDraftSessionId)
        XCTAssertFalse(other.hasPendingCommitRecovery)
    }

    func testOldHouseholdCannotReplayIntakeAfterSwitch() async throws {
        let old = HouseholdScope(userID: 1, householdID: 9)
        let current = HouseholdScope(userID: 1, householdID: 10)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HTTPStatusProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
            session: URLSession(configuration: configuration), initialScope: current)
        do {
            _ = try await client.createSession(GrocerySessionCreate(store_name: "Market", idempotency_key: "original-key"), expectedScope: old)
            XCTFail("A previous household's request must not be sent")
        } catch APIError.sessionChanged {
            // The request was rejected before transport.
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}

private final class HouseholdSwitchProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let household = request.value(forHTTPHeaderField: "X-Household-ID")
        let allowed = household == "10"
        let status = allowed ? 200 : 403
        let json = request.url!.path.hasSuffix("/households/current")
            ? #"{"id":10,"name":"Other household","role":"MEMBER"}"# : "[]"
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

extension APIStatusTests {
    func testHouseholdSwitchRequiresAuthorizationAndRejectsOldScope() async throws {
        let old = HouseholdScope(userID: 1, householdID: 9)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HouseholdSwitchProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
            session: URLSession(configuration: configuration), initialScope: old)
        let selected = try await client.selectHousehold(10, userID: 1)
        XCTAssertEqual(selected.householdID, 10)
        do {
            _ = try await client.fetchShoppingList(expectedScope: old)
            XCTFail("Old household tasks must not fetch using the new context")
        } catch APIError.sessionChanged {
        }
        do {
            _ = try await client.selectHousehold(11, userID: 1)
            XCTFail("An unauthorized household must not become active")
        } catch APIError.http(let status, _, _) {
            XCTAssertEqual(status, 403)
        }
        let items = try await client.fetchShoppingList(expectedScope: selected)
        XCTAssertTrue(items.isEmpty)
    }
}

private final class RetryProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var requests: [Data] = []
    static func reset() { lock.lock(); requests = []; lock.unlock() }
    static func captured() -> [Data] { lock.lock(); defer { lock.unlock() }; return requests }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    private func bodyData() -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = buffer.withUnsafeMutableBufferPointer { pointer in
                stream.read(pointer.baseAddress!, maxLength: pointer.count)
            }
            guard count > 0 else { break }
            data.append(contentsOf: buffer[..<count])
        }
        return data
    }
    override func startLoading() {
        let body = bodyData()
        Self.lock.lock()
        Self.requests.append(body)
        let count = Self.requests.count
        Self.lock.unlock()
        if count == 1 {
            client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
            return
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        let responseBody = #"{"preview_id":"preview-token","shopping_revision":5,"created":[],"updated":[],"unchanged":[],"consolidated":[]}"#
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(responseBody.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

extension APIStatusTests {
    func testShoppingRetryKeepsExactPayloadAndIdempotencyKey() async throws {
        RetryProtocol.reset()
        let scope = HouseholdScope(userID: 1, householdID: 9)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RetryProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
            session: URLSession(configuration: configuration), initialScope: scope)
        let payload = RecipeShoppingConfirmation(previewID: "preview-token", idempotencyKey: "same-retry-key",
            revision: 4, acceptedLines: [RecipeShoppingAcceptedLine(ingredientID: 3, target: ExactQuantity(Decimal(string: "0.123456")!))])
        do {
            _ = try await client.confirmRecipeShopping(payload, scope: scope)
            XCTFail("The first response must be lost")
        } catch APIError.networkError { }
        let result = try await client.confirmRecipeShopping(payload, scope: scope)
        XCTAssertEqual(result.shopping_revision, 5)
        let requests = RetryProtocol.captured()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0], requests[1])
        XCTAssertTrue(String(decoding: requests[0], as: UTF8.self).contains("same-retry-key"))
    }
}

extension APIStatusTests {
    func testRecipeShoppingPreviewDecodesSafetyAmountsAndTimestamp() throws {
        let json = #"""
        {"preview_id":"preview","expires_at":"2026-11-02T12:34:56.123456Z",
         "recipe_id":1,"recipe_revision":3,"servings":"2.0000","include_optional":false,
         "shopping_revision":7,"inventory_revision":9,"included_requirement_indexes":[0],
         "safety":{"decision":"eligible","reasons":[],"ingredients":[],"notice":"Check labels",
                   "availability":{"recipe_servings":"4","servings":"2","overall_status":"partial","requirements":[]}},
         "lines":[{"ingredient_id":4,"canonical_name":"rice","display_name":"bigas","unit":"g",
                   "required_quantity":"2.000001","pantry_quantity":"1.000000","shortage":"1.000001",
                   "pending_quantity":"0","target_quantity":"1.000001","additional_quantity":"1.000001",
                   "pending_item_ids":[],"covered_batch_ids":[2],"status":"ready","review_reasons":[]}],
         "unlinked_manual_items":[]}
        """#
        let preview = try JSONDecoder().decode(RecipeShoppingPreview.self, from: Data(json.utf8))
        XCTAssertEqual(preview.expires_at, "2026-11-02T12:34:56.123456Z")
        XCTAssertEqual(preview.recipe_revision, 3)
        XCTAssertEqual(preview.shopping_revision, 7)
        XCTAssertEqual(preview.safety.decision, "eligible")
        XCTAssertEqual(preview.lines[0].shortage, ExactQuantity(Decimal(string: "1.000001")!))
    }
}

extension APIStatusTests {
    func testRecipeDecodeAndEvaluationRequestPreserveDecimalsAndRevision() throws {
        let json = #"""
        {"id":12,"revision":4,"is_active":true,"provenance":"USER_ENTERED",
         "title":"Sinigang","summary":null,"cuisine":"Filipino",
         "content_permission":"OWNED_OR_PERMISSION_GRANTED","adapted_from_recipe_id":null,
         "adapted_from_recipe_revision":null,"ph_regions":["region_unknown"],
         "course_categories":["dinner"],"dish_types":["soup"],"difficulty":"beginner",
         "prep_minutes":10,"cook_minutes":30,"servings":"4.0000","equipment":[],
         "spice_level":"mild","instructions":["Cook"],"ingredients":[
           {"ingredient_id":2,"display_name":"baboy","amount":"0.123456","unit":"kg",
            "required":true,"preparation":null,"substitution_options":[]}]}
        """#
        let recipe = try JSONDecoder().decode(HouseholdRecipe.self, from: Data(json.utf8))
        XCTAssertEqual(recipe.revision, 4)
        XCTAssertEqual(recipe.ingredients[0].amount, ExactQuantity(Decimal(string: "0.123456")!))
        let evaluation = RecipeEvaluationRequest(revision: recipe.revision, servings: ExactQuantity(Decimal(string: "2.5")!))
        let encoded = String(decoding: try JSONEncoder().encode(evaluation), as: UTF8.self)
        XCTAssertTrue(encoded.contains("2.5"))
        XCTAssertTrue(encoded.contains("expected_recipe_revision"))
    }
}

extension APIStatusTests {
    func testRecipeRecommendationsDecodeServerQuantitiesAndSafetyState() throws {
        let json = #"""
        {
          "items": [{
            "recipe": {
              "id": 21, "revision": 3, "is_active": true, "provenance": "USER_ENTERED",
              "title": "Sinigang", "summary": null, "cuisine": "Filipino",
              "content_permission": "OWNED_OR_PERMISSION_GRANTED",
              "adapted_from_recipe_id": null, "adapted_from_recipe_revision": null,
              "ph_regions": ["Tagalog"], "course_categories": ["dinner"], "dish_types": ["soup"],
              "difficulty": "beginner", "prep_minutes": 10, "cook_minutes": 35,
              "servings": "4", "equipment": [], "spice_level": "mild",
              "instructions": ["Cook the measured ingredients."],
              "ingredients": [{"ingredient_id": 7, "display_name": "baboy", "amount": "0.123456",
                "unit": "kg", "required": true, "preparation": null, "substitution_options": []}]
            },
            "evaluation": {
              "decision": "eligible", "reasons": [],
              "ingredients": [{"requirement_index": 0, "ingredient_id": 7, "decision": "eligible", "reasons": []}],
              "availability": {"recipe_servings": "4", "servings": "4", "overall_status": "full",
                "requirements": [{"ingredient_id": 7, "canonical_name": "pork", "display_names": ["baboy"],
                  "required": true, "required_amount": "0.123456", "available_amount": "0.123456",
                  "shortfall": "0", "unit": "kg", "status": "full", "covered_batch_ids": [2],
                  "missing_expiry_batch_ids": [], "unknown_reasons": []}]},
              "notice": "Check actual labels and preparation."
            },
            "coverage": 1.0, "missing_ingredient_count": 0, "near_expiry_batch_count": 0,
            "preference_match": true, "source_reference": null
          }],
          "candidates_evaluated": 1, "has_more_candidates": false, "excluded_blocked": 0,
          "excluded_review_required": 0, "excluded_unknown_quantities": 0, "provider_enabled": false
        }
        """#
        let response = try JSONDecoder().decode(RecipeRecommendations.self, from: Data(json.utf8))
        XCTAssertEqual(response.items.first?.recipe.ingredients.first?.amount,
                       ExactQuantity(Decimal(string: "0.123456")!))
        XCTAssertEqual(response.items.first?.evaluation.availability.requirements.first?.available_amount,
                       ExactQuantity(Decimal(string: "0.123456")!))
        XCTAssertEqual(response.items.first?.evaluation.decision, "eligible")
        XCTAssertFalse(response.provider_enabled)
    }
}

extension APIStatusTests {
    @MainActor
    func testOwnedPendingIntakeCanBeRecoveredWhileLegacyDataRemainsQuarantined() throws {
        let suite = "provision.pending-legacy.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let scope = HouseholdScope(userID: 1, householdID: 9)
        let legacy = Data("unowned".utf8)
        defaults.set(legacy, forKey: pendingIntakeCommitStorageKey)
        let owned = PendingIntakeCommit(sessionID: 12, fingerprint: "owned", storeName: "Market",
            intakeItems: [], requestItems: [])
        defaults.set(try JSONEncoder().encode(owned), forKey: scopedPendingIntakeCommitStorageKey(for: scope))
        let vm = ScanViewModel(isPreview: false, pendingCommitDefaults: defaults, scope: scope)
        XCTAssertEqual(vm.pendingDraftSessionId, 12)
        XCTAssertNil(vm.pendingCommitRecoveryError)
        XCTAssertEqual(defaults.data(forKey: pendingIntakeCommitStorageKey), legacy)
    }
}

extension APIStatusTests {
    @MainActor
    func testOfflineRestoresOnlyPreviouslyVerifiedHousehold() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HTTPStatusProtocol.self]
        let baseURL = URL(string: "https://example.org/api/v1")!
        let client = APIClient(baseURL: baseURL, session: URLSession(configuration: configuration))
        let keychain = MemoryCredentialStore()
        let expiration = Int(Date().timeIntervalSince1970) + 3600
        let payload = Data("{\"exp\":\(expiration)}".utf8).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
        let token = "header.\(payload).signature"
        let user = User(id: 1, email: "person@example.org")
        let household = HouseholdMembership(id: 9, name: "Family", role: "OWNER", is_default: true)
        let scope = HouseholdScope(userID: 1, householdID: 9, serverID: baseURL.absoluteString)
        XCTAssertTrue(keychain.saveAccessToken(token))
        XCTAssertTrue(keychain.saveVerifiedSession(VerifiedHouseholdSession(token: token, user: user,
            scope: scope, households: [household])))
        HTTPStatusProtocol.statusCode = 0
        let viewModel = AuthViewModel(client: client, keychain: keychain)
        await viewModel.checkExistingSession()
        XCTAssertEqual(viewModel.authState, .signedIn(user))
        XCTAssertEqual(viewModel.selectedScope, scope)
        XCTAssertEqual(keychain.readAccessToken(), token)
    }
}

private final class DelayedAuthenticationProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var pending: DelayedAuthenticationProtocol?
    nonisolated(unsafe) private static var started: XCTestExpectation?
    static func prepare(_ expectation: XCTestExpectation) {
        lock.lock(); pending = nil; started = expectation; lock.unlock()
    }
    static func complete() {
        lock.lock(); let request = pending; pending = nil; lock.unlock()
        guard let request else { return }
        let response = HTTPURLResponse(url: request.request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        let body = #"{"id":1,"email":"person@example.org","is_active":true,"created_at":"2026-01-01T00:00:00Z","default_household_id":9,"default_household_name":"Family"}"#
        request.client?.urlProtocol(request, didReceive: response, cacheStoragePolicy: .notAllowed)
        request.client?.urlProtocol(request, didLoad: Data(body.utf8))
        request.client?.urlProtocolDidFinishLoading(request)
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.lock()
        Self.pending = self
        let expectation = Self.started
        Self.lock.unlock()
        expectation?.fulfill()
    }
    override func stopLoading() {}
}

extension APIStatusTests {
    @MainActor
    func testDelayedSessionCheckCannotRestoreAfterLogout() async throws {
        let started = expectation(description: "session request started")
        DelayedAuthenticationProtocol.prepare(started)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DelayedAuthenticationProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.org/api/v1")!,
                               session: URLSession(configuration: configuration))
        let keychain = MemoryCredentialStore()
        XCTAssertTrue(keychain.saveAccessToken("saved-token"))
        let viewModel = AuthViewModel(client: client, keychain: keychain)
        let check = Task { await viewModel.checkExistingSession() }
        await fulfillment(of: [started], timeout: 5)
        await viewModel.logout()
        DelayedAuthenticationProtocol.complete()
        await check.value
        XCTAssertEqual(viewModel.authState, .signedOut)
        XCTAssertNil(viewModel.currentUser)
        XCTAssertNil(viewModel.selectedScope)
        XCTAssertNil(keychain.readAccessToken())
    }
}
