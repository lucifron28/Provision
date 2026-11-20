import Combine
import Foundation

public enum CookWithPipMode: String, CaseIterable, Identifiable, Sendable {
    case cookNow
    case almostThere
    case myRecipes

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .cookNow: "Cook Now"
        case .almostThere: "Almost There"
        case .myRecipes: "My Recipes"
        }
    }

    fileprivate var recommendationMode: String? {
        switch self {
        case .cookNow: "cook_now"
        case .almostThere: "almost_there"
        case .myRecipes: nil
        }
    }
}

@MainActor
public final class CookWithPipViewModel: ObservableObject {
    @Published public var mode: CookWithPipMode
    @Published public var searchQuery = ""
    @Published public private(set) var recommendations: [RecipeRecommendation] = []
    @Published public private(set) var recipes: [HouseholdRecipe] = []
    @Published public private(set) var isLoading = false
    @Published public private(set) var isLoadingMore = false
    @Published public private(set) var hasLoadedOnce = false
    @Published public private(set) var hasMore = false
    @Published public private(set) var isOffline = false
    @Published public private(set) var errorMessage: String?
    @Published public private(set) var excludedBlocked = 0
    @Published public private(set) var excludedReviewRequired = 0
    @Published public private(set) var excludedUnknownQuantities = 0
    @Published public private(set) var excludedCandidates: [ExcludedRecipeCandidate] = []

    public let scope: HouseholdScope
    public let service: any CookWithPipService
    public let inventoryBatchID: Int?
    public let ingredientFilterLabel: String?

    private let pageSize = 20
    private let candidatePageSize = 100
    private var recipeOffset = 0
    private var candidateOffset = 0
    private var activeRequestID = UUID()

    public init(scope: HouseholdScope, service: any CookWithPipService = APIClient.shared,
                initialMode: CookWithPipMode = .cookNow, inventoryBatchID: Int? = nil,
                ingredientFilterLabel: String? = nil) {
        self.scope = scope
        self.service = service
        self.mode = initialMode
        self.inventoryBatchID = inventoryBatchID
        self.ingredientFilterLabel = ingredientFilterLabel
    }

    public func select(_ mode: CookWithPipMode) async {
        guard self.mode != mode else { return }
        self.mode = mode
        await load(reset: true)
    }

    public func load(reset: Bool = false, preserveResults: Bool = false) async {
        let requestID = UUID()
        activeRequestID = requestID
        let requestedMode = mode
        let query = normalizedQuery

        if reset {
            recipeOffset = 0
            candidateOffset = 0
            hasMore = false
            errorMessage = nil
            isOffline = false
            if !preserveResults {
                recipes = []
                recommendations = []
                excludedBlocked = 0
                excludedReviewRequired = 0
                excludedUnknownQuantities = 0
                excludedCandidates = []
                hasLoadedOnce = false
            }
        }

        isLoading = !hasLoadedOnce || (reset && !preserveResults)
        isLoadingMore = !reset
        errorMessage = nil
        isOffline = false

        do {
            if requestedMode == .myRecipes {
                let page = try await service.fetchRecipePage(
                    query: query.isEmpty ? nil : query,
                    inventoryBatchID: inventoryBatchID,
                    limit: pageSize,
                    offset: recipeOffset,
                    scope: scope
                )
                guard activeRequestID == requestID else { return }
                if reset { recipes = page } else { recipes.append(contentsOf: page) }
                recipeOffset += page.count
                hasMore = page.count == pageSize
            } else if let recommendationMode = requestedMode.recommendationMode {
                let page = try await service.recommendRecipes(
                    RecipeRecommendationRequest(
                        mode: recommendationMode,
                        query: query.isEmpty ? nil : query,
                        limit: pageSize,
                        candidateLimit: candidatePageSize,
                        candidateOffset: candidateOffset
                    ),
                    scope: scope
                )
                guard activeRequestID == requestID else { return }
                if reset {
                    recommendations = page.items
                    excludedBlocked = page.excluded_blocked
                    excludedReviewRequired = page.excluded_review_required
                    excludedUnknownQuantities = page.excluded_unknown_quantities
                    excludedCandidates = page.excluded_candidates
                } else {
                    recommendations.append(contentsOf: page.items)
                    excludedBlocked += page.excluded_blocked
                    excludedReviewRequired += page.excluded_review_required
                    excludedUnknownQuantities += page.excluded_unknown_quantities
                    let existingIDs = Set(excludedCandidates.map(\.id))
                    excludedCandidates.append(contentsOf: page.excluded_candidates.filter { !existingIDs.contains($0.id) })
                }
                candidateOffset += candidatePageSize
                hasMore = page.has_more_candidates
            }
            guard activeRequestID == requestID else { return }
            hasLoadedOnce = true
        } catch {
            guard activeRequestID == requestID else { return }
            errorMessage = error.localizedDescription
            isOffline = Self.isNetworkError(error)
            hasLoadedOnce = true
        }

        guard activeRequestID == requestID else { return }
        isLoading = false
        isLoadingMore = false
    }

    public func refresh() async {
        await load(reset: true, preserveResults: true)
    }

    public func loadMore() async {
        guard hasMore, !isLoading, !isLoadingMore else { return }
        await load()
    }

    public var normalizedQuery: String {
        String(searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).prefix(180))
    }

    public var currentRecommendations: [RecipeRecommendation] {
        mode == .myRecipes ? [] : recommendations
    }

    public var currentRecipes: [HouseholdRecipe] {
        mode == .myRecipes ? recipes : []
    }

    public var hasExcludedCandidates: Bool {
        excludedBlocked > 0 || excludedReviewRequired > 0 || excludedUnknownQuantities > 0 || !excludedCandidates.isEmpty
    }

    public var needsReviewCandidates: [ExcludedRecipeCandidate] {
        excludedCandidates.filter { $0.status == "review_required" || $0.status == "unknown_quantities" }
    }

    public var blockedCandidates: [ExcludedRecipeCandidate] {
        excludedCandidates.filter { $0.status == "blocked" }
    }

    static func isNetworkError(_ error: Error) -> Bool {
        if case APIError.networkError = error { return true }
        return error is URLError
    }
}
