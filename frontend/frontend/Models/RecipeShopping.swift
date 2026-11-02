import Foundation

/// Decimal values remain decimal strings when sent to the server.
public struct ExactQuantity: Codable, Sendable, Equatable {
    public let value: Decimal

    public init(_ value: Decimal) { self.value = value }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let text = try? container.decode(String.self),
           let number = Decimal(string: text, locale: Locale(identifier: "en_US_POSIX")) {
            value = number
        } else {
            value = try container.decode(Decimal.self)
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(NSDecimalNumber(decimal: value).stringValue)
    }
}

public struct RecipeShoppingPreviewRequest: Encodable, Sendable {
    public let recipe_id: Int
    public let expected_recipe_revision: Int
    public let servings: ExactQuantity
    public let diner_user_ids: [Int]?
    public let include_optional: Bool

    public init(recipeID: Int, revision: Int, servings: ExactQuantity, dinerUserIDs: [Int]? = nil, includeOptional: Bool = false) {
        recipe_id = recipeID
        expected_recipe_revision = revision
        self.servings = servings
        diner_user_ids = dinerUserIDs
        include_optional = includeOptional
    }
}

public struct IngredientAvailabilitySnapshot: Decodable, Sendable {
    public let ingredient_id: Int?
    public let canonical_name: String?
    public let display_names: [String]
    public let required: Bool
    public let required_amount: ExactQuantity?
    public let available_amount: ExactQuantity?
    public let shortfall: ExactQuantity?
    public let unit: String?
    public let status: String
    public let covered_batch_ids: [Int]
    public let missing_expiry_batch_ids: [Int]
    public let unknown_reasons: [String]
}

public struct RecipeAvailabilitySnapshot: Decodable, Sendable {
    public let recipe_servings: ExactQuantity
    public let servings: ExactQuantity
    public let overall_status: String
    public let requirements: [IngredientAvailabilitySnapshot]
}

public struct IngredientSafetySnapshot: Decodable, Sendable {
    public let requirement_index: Int
    public let ingredient_id: Int?
    public let decision: String
    public let reasons: [String]
}

public struct FoodSafetySnapshot: Decodable, Sendable {
    public let decision: String
    public let reasons: [String]
    public let ingredients: [IngredientSafetySnapshot]
    public let availability: RecipeAvailabilitySnapshot
    public let notice: String
}

public struct RecipeShoppingLine: Decodable, Sendable {
    public let ingredient_id: Int?
    public let canonical_name: String?
    public let display_name: String
    public let unit: String?
    public let required_quantity: ExactQuantity?
    public let pantry_quantity: ExactQuantity?
    public let shortage: ExactQuantity?
    public let pending_quantity: ExactQuantity?
    public let target_quantity: ExactQuantity?
    public let additional_quantity: ExactQuantity?
    public let pending_item_ids: [Int]
    public let covered_batch_ids: [Int]
    public let status: String
    public let review_reasons: [String]
}

public struct UnlinkedShoppingReview: Decodable, Sendable {
    public let item_id: Int
    public let name: String
    public let quantity: ExactQuantity
    public let unit: String?
    public let candidate_ingredient_ids: [Int]
    public let reason: String
}

public struct RecipeShoppingPreview: Decodable, Sendable {
    public let preview_id: String
    /// Preserve the server timestamp, including fractional seconds and timezone.
    public let expires_at: String
    public let recipe_id: Int
    public let recipe_revision: Int
    public let servings: ExactQuantity
    public let include_optional: Bool
    public let shopping_revision: Int
    public let inventory_revision: Int
    public let included_requirement_indexes: [Int]
    public let safety: FoodSafetySnapshot
    public let lines: [RecipeShoppingLine]
    public let unlinked_manual_items: [UnlinkedShoppingReview]
}

public struct RecipeShoppingAcceptedLine: Codable, Sendable {
    public let ingredient_id: Int
    public let target_quantity: ExactQuantity
    public let consolidate_existing: Bool

    public init(ingredientID: Int, target: ExactQuantity, consolidateExisting: Bool = false) {
        ingredient_id = ingredientID
        target_quantity = target
        consolidate_existing = consolidateExisting
    }
}

/// Persist this exact value for retries; edits require a new idempotency key.
public struct RecipeShoppingConfirmation: Codable, Sendable {
    public let preview_id: String
    public let idempotency_key: String
    public let expected_revision: Int
    public let accepted_lines: [RecipeShoppingAcceptedLine]

    public init(previewID: String, idempotencyKey: String, revision: Int, acceptedLines: [RecipeShoppingAcceptedLine]) {
        preview_id = previewID
        idempotency_key = idempotencyKey
        expected_revision = revision
        accepted_lines = acceptedLines
    }
}

public struct RecipeShoppingChange: Decodable, Sendable {
    public let id: Int
    public let name: String
    public let quantity: ExactQuantity
    public let unit: String?
    public let is_bought: Bool
    public let notes: String?
    public let product_id: Int?
    public let ingredient_id: Int?
    public let origin_recipe_id: Int?
    public let origin_recipe_revision: Int?
    public let origin_plan_id: Int?
    public let origin_plan_revision: Int?
    public let created_at: String?
    public let updated_at: String?
}

public struct ConsolidatedShoppingItems: Decodable, Sendable {
    public let kept_item_id: Int
    public let removed_items: [RecipeShoppingChange]
}

public struct RecipeShoppingConfirmationResult: Decodable, Sendable {
    public let preview_id: String
    public let shopping_revision: Int
    public let created: [RecipeShoppingChange]
    public let updated: [RecipeShoppingChange]
    public let unchanged: [RecipeShoppingChange]
    public let consolidated: [ConsolidatedShoppingItems]
}
