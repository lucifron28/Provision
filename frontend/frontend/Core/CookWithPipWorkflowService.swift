import Foundation

public protocol CookWithPipWorkflowService: Sendable {
    func fetchMyFoodProfile(scope: HouseholdScope) async throws -> FoodProfileRead
    func saveMyFoodProfile(_ profile: FoodProfileWrite, scope: HouseholdScope) async throws -> FoodProfileRead
    func lookupIngredients(query: String?, limit: Int, scope: HouseholdScope) async throws -> IngredientLookup
    func fetchProductsForCookWithPip(scope: HouseholdScope) async throws -> [Product]
    func fetchProductForCookWithPip(id: Int, scope: HouseholdScope) async throws -> Product
    func fetchProductMapping(productID: Int, scope: HouseholdScope) async throws -> ProductIngredientMappingRead
    func saveProductMapping(productID: Int, mapping: ProductIngredientMappingWrite,
                            scope: HouseholdScope) async throws -> ProductIngredientMappingRead
    func fetchProductLabel(productID: Int, scope: HouseholdScope) async throws -> ProductLabelRead
    func saveProductLabel(productID: Int, label: ProductLabelWrite,
                          scope: HouseholdScope) async throws -> ProductLabelRead
    func previewRecipeShopping(_ request: RecipeShoppingPreviewRequest,
                               scope: HouseholdScope) async throws -> RecipeShoppingPreview
    func confirmRecipeShopping(_ confirmation: RecipeShoppingConfirmation,
                               scope: HouseholdScope) async throws -> RecipeShoppingConfirmationResult
    func fetchShoppingListFromServer(scope: HouseholdScope) async throws -> [ShoppingItem]
}

extension APIClient: CookWithPipWorkflowService {}
