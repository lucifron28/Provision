import Combine
import Foundation

@MainActor
public final class RecipeDetailViewModel: ObservableObject {
    @Published public private(set) var recipe: HouseholdRecipe?
    @Published public private(set) var evaluation: RecipeEvaluation?
    @Published public private(set) var sourceReference: RecipeSourceReference?
    @Published public private(set) var sourceReferenceErrorMessage: String?
    @Published public private(set) var isSourceOffline = false
    @Published public private(set) var isLoadingSourceReference = false
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
        sourceReference = nil
        sourceReferenceErrorMessage = nil
        isSourceOffline = false

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
            await loadSourceReference(requestID: requestID)
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

    public func retrySourceReference() async {
        await loadSourceReference(requestID: activeRequestID)
    }

    private func loadSourceReference(requestID: UUID) async {
        isLoadingSourceReference = true
        sourceReferenceErrorMessage = nil
        isSourceOffline = false
        defer {
            if activeRequestID == requestID {
                isLoadingSourceReference = false
            }
        }

        do {
            let source = try await service.fetchRecipeSourceReference(id: recipeID, scope: scope)
            guard activeRequestID == requestID else { return }
            sourceReference = source
        } catch {
            guard activeRequestID == requestID else { return }
            if let apiError = error as? APIError,
               case .http(status: 404, _, _) = apiError {
                sourceReference = nil
                return
            }
            sourceReference = nil
            sourceReferenceErrorMessage = error.localizedDescription
            isSourceOffline = CookWithPipViewModel.isNetworkError(error)
        }
    }
}
