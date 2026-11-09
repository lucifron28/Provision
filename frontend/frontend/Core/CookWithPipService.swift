import Foundation

public protocol CookWithPipService: Sendable {
    func fetchRecipePage(query: String?, limit: Int, offset: Int,
                         scope: HouseholdScope) async throws -> [HouseholdRecipe]
    func fetchRecipe(id: Int, scope: HouseholdScope) async throws -> HouseholdRecipe
    func evaluateRecipe(id: Int, payload: RecipeEvaluationRequest,
                        scope: HouseholdScope) async throws -> RecipeEvaluation
    func recommendRecipes(_ payload: RecipeRecommendationRequest,
                          scope: HouseholdScope) async throws -> RecipeRecommendations
    func fetchRecipeSourceReference(id: Int, scope: HouseholdScope) async throws -> RecipeSourceReference
}

extension APIClient: CookWithPipService {}
