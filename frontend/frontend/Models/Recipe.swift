import Foundation

public struct IngredientRequirement: Codable, Sendable {
    public let ingredient_id: Int?
    public let display_name: String?
    public let amount: ExactQuantity
    public let unit: String
    public let required: Bool

    public init(ingredientID: Int? = nil, displayName: String? = nil, amount: ExactQuantity, unit: String, required: Bool = true) {
        ingredient_id = ingredientID
        display_name = displayName
        self.amount = amount
        self.unit = unit
        self.required = required
    }
}

public struct RecipeIngredient: Decodable, Sendable {
    public let ingredient_id: Int?
    public let display_name: String
    public let amount: ExactQuantity
    public let unit: String
    public let required: Bool
    public let preparation: String?
    public let substitution_options: [IngredientRequirement]
}

public struct HouseholdRecipe: Decodable, Identifiable, Sendable {
    public let id: Int
    public let revision: Int
    public let is_active: Bool
    public let provenance: String
    public let title: String
    public let summary: String?
    public let cuisine: String
    public let content_permission: String
    public let adapted_from_recipe_id: Int?
    public let adapted_from_recipe_revision: Int?
    public let ph_regions: [String]
    public let course_categories: [String]
    public let dish_types: [String]
    public let difficulty: String
    public let prep_minutes: Int
    public let cook_minutes: Int
    public let servings: ExactQuantity
    public let equipment: [String]
    public let spice_level: String
    public let instructions: [String]
    public let ingredients: [RecipeIngredient]
}

public struct RecipeSubstitution: Encodable, Sendable {
    public let requirement_index: Int
    public let replacement: IngredientRequirement
    public init(requirementIndex: Int, replacement: IngredientRequirement) {
        requirement_index = requirementIndex
        self.replacement = replacement
    }
}

public struct RecipeEvaluationRequest: Encodable, Sendable {
    public let expected_recipe_revision: Int
    public let servings: ExactQuantity
    public let include_optional: Bool
    public let diner_user_ids: [Int]?
    public let substitutions: [RecipeSubstitution]

    public init(revision: Int, servings: ExactQuantity, includeOptional: Bool = true,
                dinerUserIDs: [Int]? = nil, substitutions: [RecipeSubstitution] = []) {
        expected_recipe_revision = revision
        self.servings = servings
        include_optional = includeOptional
        diner_user_ids = dinerUserIDs
        self.substitutions = substitutions
    }
}

public struct RecipeEvaluation: Decodable, Sendable {
    public let recipe_id: Int
    public let recipe_revision: Int
    public let included_requirement_indexes: [Int]
    public let result: FoodSafetySnapshot
}

public struct RecipeRecommendationRequest: Encodable, Sendable {
    public let servings: ExactQuantity?
    public let diner_user_ids: [Int]?
    public let mode: String
    public let query: String?
    public let max_missing_ingredients: Int
    public let limit: Int
    public let candidate_offset: Int

    public init(servings: ExactQuantity? = nil, dinerUserIDs: [Int]? = nil, mode: String = "all",
                query: String? = nil, maxMissingIngredients: Int = 3, limit: Int = 20, candidateOffset: Int = 0) {
        self.servings = servings
        diner_user_ids = dinerUserIDs
        self.mode = mode
        self.query = query
        max_missing_ingredients = maxMissingIngredients
        self.limit = limit
        candidate_offset = candidateOffset
    }
}

public struct RecipeSourceReference: Decodable, Sendable {
    public let recipe_id: Int
    public let revision: Int
    public let is_active: Bool
    public let canonical_url: String
    public let author: String?
    public let publisher_name: String
    public let source_label: String
    public let currently_allowed: Bool
    public let copied_publisher_content: Bool
    public let live_fetch_enabled: Bool
    public let linked_at: String
}

public struct RecipeRecommendation: Decodable, Sendable {
    public let recipe: HouseholdRecipe
    public let evaluation: FoodSafetySnapshot
    public let coverage: ExactQuantity
    public let missing_ingredient_count: Int
    public let near_expiry_batch_count: Int
    public let preference_match: Bool
    public let source_reference: RecipeSourceReference?
}

public struct RecipeRecommendations: Decodable, Sendable {
    public let items: [RecipeRecommendation]
    public let candidates_evaluated: Int
    public let has_more_candidates: Bool
    public let excluded_blocked: Int
    public let excluded_review_required: Int
    public let excluded_unknown_quantities: Int
    public let provider_enabled: Bool
}
