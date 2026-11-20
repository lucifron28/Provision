import Foundation
import XCTest
@testable import frontend

nonisolated private enum CookServiceBehavior: Sendable, Equatable {
    case fixture
    case empty
    case paged
    case offline
    case serverError
    case sourceFailsOnce
}

private actor CookWithPipServiceSpy: CookWithPipService {
    private let fixture: CookWithPipUITestService
    private let behavior: CookServiceBehavior
    private var recommendationRequests: [(RecipeRecommendationRequest, HouseholdScope)] = []
    private var recipePageRequests: [(String?, Int?, Int, Int, HouseholdScope)] = []
    private var evaluationRequests: [(Int, RecipeEvaluationRequest, HouseholdScope)] = []
    private var sourceReferenceRequests = 0

    init(behavior: CookServiceBehavior = .fixture, fixtureScenario: String = "default") {
        self.behavior = behavior
        fixture = CookWithPipUITestService(scenario: fixtureScenario)
    }

    func fetchRecipePage(query: String?, inventoryBatchID: Int?, limit: Int, offset: Int,
                         scope: HouseholdScope) async throws -> [HouseholdRecipe] {
        recipePageRequests.append((query, inventoryBatchID, limit, offset, scope))
        if behavior == .offline {
            try await Task.sleep(for: .milliseconds(40))
            throw URLError(.notConnectedToInternet)
        }
        if behavior == .serverError {
            throw APIError.http(status: 503, detail: nil, retryAfter: nil)
        }
        if behavior == .empty { return [] }
        if behavior == .paged, offset == 0 {
            let first = try await fixture.fetchRecipePage(query: nil, inventoryBatchID: nil,
                                                          limit: 1, offset: 0, scope: scope)
            return Array(repeating: first[0], count: limit)
        }
        if behavior == .paged { return [] }
        return try await fixture.fetchRecipePage(query: query, inventoryBatchID: inventoryBatchID,
                                                 limit: limit, offset: offset, scope: scope)
    }

    func fetchRecipe(id: Int, scope: HouseholdScope) async throws -> HouseholdRecipe {
        try await fixture.fetchRecipe(id: id, scope: scope)
    }

    func evaluateRecipe(id: Int, payload: RecipeEvaluationRequest,
                        scope: HouseholdScope) async throws -> RecipeEvaluation {
        evaluationRequests.append((id, payload, scope))
        return try await fixture.evaluateRecipe(id: id, payload: payload, scope: scope)
    }

    func recommendRecipes(_ payload: RecipeRecommendationRequest,
                          scope: HouseholdScope) async throws -> RecipeRecommendations {
        recommendationRequests.append((payload, scope))
        if behavior == .offline {
            try await Task.sleep(for: .milliseconds(40))
            throw URLError(.notConnectedToInternet)
        }
        if behavior == .serverError {
            throw APIError.http(status: 503, detail: nil, retryAfter: nil)
        }
        let response = try await fixture.recommendRecipes(payload, scope: scope)
        if behavior == .empty {
            return RecipeRecommendations(items: [], candidates_evaluated: 0, has_more_candidates: false,
                                         excluded_blocked: 0, excluded_review_required: 0,
                                         excluded_unknown_quantities: 0, provider_enabled: false)
        }
        if behavior == .paged && payload.candidate_offset == 0 {
            return RecipeRecommendations(items: response.items, candidates_evaluated: response.candidates_evaluated,
                                         has_more_candidates: true, excluded_blocked: response.excluded_blocked,
                                         excluded_review_required: response.excluded_review_required,
                                         excluded_unknown_quantities: response.excluded_unknown_quantities,
                                         provider_enabled: false)
        }
        return response
    }

    func fetchRecipeSourceReference(id: Int, scope: HouseholdScope) async throws -> RecipeSourceReference {
        sourceReferenceRequests += 1
        if behavior == .sourceFailsOnce && sourceReferenceRequests == 1 {
            throw APIError.http(status: 503, detail: nil, retryAfter: nil)
        }
        return try await fixture.fetchRecipeSourceReference(id: id, scope: scope)
    }

    func recordedRecommendationRequests() -> [(RecipeRecommendationRequest, HouseholdScope)] {
        recommendationRequests
    }

    func recordedRecipePageRequests() -> [(String?, Int?, Int, Int, HouseholdScope)] {
        recipePageRequests
    }

    func recordedEvaluationRequests() -> [(Int, RecipeEvaluationRequest, HouseholdScope)] {
        evaluationRequests
    }
}

@MainActor
final class CookWithPipViewModelTests: XCTestCase {
    private let scope = HouseholdScope(userID: 15, householdID: 29, serverID: "https://provision.test/api/v1")

    func testRecommendationModesUseSelectedHousehold() async throws {
        let service = CookWithPipServiceSpy()
        let viewModel = CookWithPipViewModel(scope: scope, service: service)

        await viewModel.load(reset: true)
        XCTAssertEqual(viewModel.recommendations.first?.recipe.title, "Sinigang na Baboy")
        await viewModel.select(.almostThere)
        XCTAssertEqual(viewModel.recommendations.first?.recipe.title, "Chicken Adobo")

        let requests = await service.recordedRecommendationRequests()
        XCTAssertEqual(requests.map { $0.0.mode }, ["cook_now", "almost_there"])
        XCTAssertTrue(requests.allSatisfy { $0.1 == scope })
        XCTAssertTrue(requests.allSatisfy { $0.0.candidate_limit == 100 })
    }

    func testReviewCandidatesRemainVisibleAlongsideEmptyCookNowResults() async throws {
        let service = CookWithPipServiceSpy(fixtureScenario: "recipes-needs-review")
        let viewModel = CookWithPipViewModel(scope: scope, service: service)

        await viewModel.load(reset: true)

        XCTAssertTrue(viewModel.recommendations.isEmpty)
        XCTAssertEqual(viewModel.needsReviewCandidates.map(\.title), ["Ginisang Kangkong"])
        XCTAssertTrue(viewModel.hasExcludedCandidates)
    }

    func testMyRecipesSearchAndPagination() async throws {
        let service = CookWithPipServiceSpy(behavior: .paged)
        let viewModel = CookWithPipViewModel(scope: scope, service: service)
        await viewModel.select(.myRecipes)
        XCTAssertEqual(viewModel.recipes.count, 20)
        XCTAssertTrue(viewModel.hasMore)

        await viewModel.loadMore()
        XCTAssertEqual(viewModel.recipes.count, 20)
        XCTAssertFalse(viewModel.hasMore)

        viewModel.searchQuery = "  Chicken Adobo  "
        await viewModel.load(reset: true)
        let pages = await service.recordedRecipePageRequests()
        XCTAssertEqual(pages.map { $0.0 }, [nil, nil, "Chicken Adobo"])
        XCTAssertEqual(pages.map { $0.3 }, [0, 20, 0])
        XCTAssertTrue(pages.allSatisfy { $0.4 == scope })
    }

    func testExpiringBatchStartsMyRecipesWithTheBatchFilter() async throws {
        let service = CookWithPipServiceSpy()
        let viewModel = CookWithPipViewModel(scope: scope, service: service, initialMode: .myRecipes,
                                             inventoryBatchID: 912, ingredientFilterLabel: "Kangkong")

        await viewModel.load(reset: true)

        XCTAssertEqual(viewModel.mode, .myRecipes)
        XCTAssertEqual(viewModel.ingredientFilterLabel, "Kangkong")
        let requests = await service.recordedRecipePageRequests()
        XCTAssertEqual(requests.first?.1, 912)
    }

    func testRecommendationPaginationUsesBackendCandidateWindow() async throws {
        let service = CookWithPipServiceSpy(behavior: .paged)
        let viewModel = CookWithPipViewModel(scope: scope, service: service)

        await viewModel.load(reset: true)
        XCTAssertTrue(viewModel.hasMore)
        await viewModel.loadMore()

        let requests = await service.recordedRecommendationRequests()
        XCTAssertEqual(requests.map { $0.0.candidate_offset }, [0, 100])
        XCTAssertTrue(requests.allSatisfy { $0.0.candidate_limit == 100 && $0.1 == scope })
        XCTAssertFalse(viewModel.hasMore)
    }

    func testEmptyAndOfflineStatesAreExplicit() async throws {
        let emptyService = CookWithPipServiceSpy(behavior: .empty)
        let emptyViewModel = CookWithPipViewModel(scope: scope, service: emptyService)
        await emptyViewModel.load(reset: true)
        XCTAssertTrue(emptyViewModel.hasLoadedOnce)
        XCTAssertTrue(emptyViewModel.recommendations.isEmpty)
        XCTAssertNil(emptyViewModel.errorMessage)

        let offlineService = CookWithPipServiceSpy(behavior: .offline)
        let offlineViewModel = CookWithPipViewModel(scope: scope, service: offlineService)
        let loadingTask = Task { await offlineViewModel.load(reset: true) }
        try await Task.sleep(for: .milliseconds(5))
        XCTAssertTrue(offlineViewModel.isLoading)
        await loadingTask.value
        XCTAssertTrue(offlineViewModel.hasLoadedOnce)
        XCTAssertTrue(offlineViewModel.isOffline)
        XCTAssertNotNil(offlineViewModel.errorMessage)

        let serverErrorService = CookWithPipServiceSpy(behavior: .serverError)
        let serverErrorViewModel = CookWithPipViewModel(scope: scope, service: serverErrorService)
        await serverErrorViewModel.load(reset: true)
        XCTAssertFalse(serverErrorViewModel.isOffline)
        XCTAssertTrue(serverErrorViewModel.errorMessage?.contains("temporarily unavailable") == true)
    }

    func testDetailUsesCurrentServerEvaluationAndExactServings() async throws {
        let service = CookWithPipServiceSpy()
        let viewModel = RecipeDetailViewModel(recipeID: 303, scope: scope, service: service)

        await viewModel.load()

        XCTAssertEqual(viewModel.recipe?.revision, 1)
        XCTAssertEqual(viewModel.evaluation?.result.decision, "review_required")
        XCTAssertEqual(viewModel.evaluation?.result.availability.overall_status, "unknown")
        XCTAssertNil(viewModel.errorMessage)

        let requests = await service.recordedEvaluationRequests()
        let request = try XCTUnwrap(requests.first)
        XCTAssertEqual(request.0, 303)
        XCTAssertEqual(request.2, scope)
        XCTAssertEqual(request.1.expected_recipe_revision, 1)
        XCTAssertEqual(request.1.servings, ExactQuantity(Decimal(string: "4.000000")!))
        XCTAssertTrue(request.1.include_optional)
        XCTAssertNil(request.1.diner_user_ids)
    }

    func testSourceLookupFailureKeepsEvaluationAndRetryRecovers() async throws {
        let service = CookWithPipServiceSpy(behavior: .sourceFailsOnce)
        let viewModel = RecipeDetailViewModel(recipeID: 303, scope: scope, service: service)

        await viewModel.load()

        XCTAssertNotNil(viewModel.recipe)
        XCTAssertNotNil(viewModel.evaluation)
        XCTAssertTrue(viewModel.sourceReferenceErrorMessage?.contains("temporarily unavailable") == true)
        XCTAssertFalse(viewModel.isSourceOffline)

        await viewModel.retrySourceReference()

        XCTAssertNil(viewModel.sourceReferenceErrorMessage)
        XCTAssertNil(viewModel.sourceReference)
        XCTAssertFalse(viewModel.isLoadingSourceReference)
    }

    func testSafetyAndAvailabilityLabelsPreserveDistinctStates() throws {
        XCTAssertEqual(RecipeStatusPresentation.safety("eligible").title, "Eligible")
        XCTAssertEqual(RecipeStatusPresentation.safety("blocked").title, "Blocked")
        XCTAssertEqual(RecipeStatusPresentation.safety("review_required").title, "Review required")
        XCTAssertEqual(RecipeStatusPresentation.availability("partial").title, "Partial")
        XCTAssertEqual(RecipeStatusPresentation.availability("missing").title, "Missing")
        XCTAssertEqual(RecipeStatusPresentation.availability("unknown").title, "Unknown")
    }
    func testFoodPreferencesDecodeBackendDecimalStringsAndJSONNumbers() throws {
        let backendStringJSON = #"{"preferred_cuisines":["Filipino"],"preferred_regions":[],"dislikes":[],"diet_patterns":[],"ingredient_exclusions":[],"heat_tolerance":"no_preference","equipment":["stovetop"],"max_cook_minutes":45,"meal_budget_php":"250.75","preferred_language":"en","servings":"2.5000"}"#
        let stringPreferences = try JSONDecoder().decode(
            FoodPreferences.self,
            from: Data(backendStringJSON.utf8)
        )
        XCTAssertEqual(stringPreferences.servings, Decimal(string: "2.5000"))
        XCTAssertEqual(stringPreferences.meal_budget_php, Decimal(string: "250.75"))

        let backendNumberJSON = #"{"preferred_cuisines":["Filipino"],"preferred_regions":[],"dislikes":[],"diet_patterns":[],"ingredient_exclusions":[],"heat_tolerance":"no_preference","equipment":[],"max_cook_minutes":null,"meal_budget_php":null,"preferred_language":"en","servings":3.25}"#
        let numberPreferences = try JSONDecoder().decode(
            FoodPreferences.self,
            from: Data(backendNumberJSON.utf8)
        )
        XCTAssertEqual(numberPreferences.servings, Decimal(string: "3.25"))
        XCTAssertNil(numberPreferences.meal_budget_php)
    }

}

private final class CookWithPipRequestProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var lastRequest: URLRequest?

    static func reset() {
        lock.lock()
        lastRequest = nil
        lock.unlock()
    }

    static func capturedRequest() -> URLRequest? {
        lock.lock()
        defer { lock.unlock() }
        return lastRequest
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        Self.lastRequest = request
        Self.lock.unlock()
        let response = HTTPURLResponse(url: request.url!, statusCode: 200,
                                        httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("[]".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

extension CookWithPipViewModelTests {
    func testRecipePageClientRejectsWrongHouseholdAndSendsVerifiedScope() async throws {
        CookWithPipRequestProtocol.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CookWithPipRequestProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://provision.test/api/v1")!,
                               session: URLSession(configuration: configuration))
        await client.setAccessToken("synthetic-token")
        await client.setHouseholdScope(scope)
        let wrongScope = HouseholdScope(userID: scope.userID, householdID: scope.householdID + 1,
                                        serverID: scope.serverID)

        do {
            _ = try await client.fetchRecipePage(query: nil, limit: 20, offset: 0, scope: wrongScope)
            XCTFail("Expected the client to reject an unselected household")
        } catch APIError.sessionChanged {
            // A caller cannot select another household by passing a different scope.
        }
        XCTAssertNil(CookWithPipRequestProtocol.capturedRequest())

        _ = try await client.fetchRecipePage(query: "Chicken Adobo & rice", inventoryBatchID: 912,
                                             limit: 20, offset: 40, scope: scope)
        let request = try XCTUnwrap(CookWithPipRequestProtocol.capturedRequest())
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Household-ID"), String(scope.householdID))
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer synthetic-token")
        let queryItems = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
        XCTAssertEqual(queryItems.first(where: { $0.name == "limit" })?.value, "20")
        XCTAssertEqual(queryItems.first(where: { $0.name == "offset" })?.value, "40")
        XCTAssertEqual(queryItems.first(where: { $0.name == "query" })?.value, "Chicken Adobo & rice")
        XCTAssertEqual(queryItems.first(where: { $0.name == "inventory_batch_id" })?.value, "912")
    }
}
