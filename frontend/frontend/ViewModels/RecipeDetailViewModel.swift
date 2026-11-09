import Combine
import Foundation

@MainActor
public final class RecipeDetailViewModel: ObservableObject {
    @Published public private(set) var recipe: HouseholdRecipe?
    @Published public private(set) var evaluation: RecipeEvaluation?
    @Published public private(set) var sourceReference: RecipeSourceReference?
    @Published public private(set) var isLoading = false
    @Published public private(set) var hasLoadedOnce = false
    @Published public private(set) var isOffline = false
    @Published public private(set) var errorMessage: String?

    private let recipeID: Int
    private let scope: HouseholdScope
    private let service: any CookWithPipService
    private var activeRequestID = UUID()

    public init(recipeID: Int, scope: HouseholdScope, service: any CookWithPipService = APIClient.shared) {
        self.recipeID = recipeID
        self.scope = scope
        self.service = service
    }

    public func load() async {
        let requestID = UUID()
        activeRequestID = requestID
        isLoading = true
        errorMessage = nil
        isOffline = false

        do {
            let recipe = try await service.fetchRecipe(id: recipeID, scope: scope)
            guard activeRequestID == requestID else { return }
            let evaluation = try await service.evaluateRecipe(
                id: recipeID,
                payload: RecipeEvaluationRequest(revision: recipe.revision, servings: recipe.servings),
                scope: scope
            )
            guard activeRequestID == requestID else { return }
            self.recipe = recipe
            self.evaluation = evaluation
            if let source = try? await service.fetchRecipeSourceReference(id: recipeID, scope: scope) {
                guard activeRequestID == requestID else { return }
                sourceReference = source
            } else {
                sourceReference = nil
            }
            hasLoadedOnce = true
        } catch {
            guard activeRequestID == requestID else { return }
            errorMessage = error.localizedDescription
            isOffline = CookWithPipViewModel.isNetworkError(error)
            hasLoadedOnce = true
        }

        guard activeRequestID == requestID else { return }
        isLoading = false
    }
}
