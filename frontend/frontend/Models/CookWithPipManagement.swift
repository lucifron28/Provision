import Foundation

nonisolated public enum FoodAllergenCode: String, Codable, CaseIterable, Identifiable, Sendable {
    case milk, egg, fish, crustaceanShellfish = "crustacean_shellfish"
    case treeNuts = "tree_nuts", peanuts, wheat, soy, sesame

    public var id: String { rawValue }
    public var title: String {
        return switch self {
        case .crustaceanShellfish: "Crustacean shellfish"
        case .treeNuts: "Tree nuts"
        default: rawValue.capitalized
        }
    }
}

nonisolated public struct FoodPreferences: Codable, Equatable, Sendable {
    public var preferred_cuisines: [String]
    public var preferred_regions: [String]
    public var dislikes: [String]
    public var diet_patterns: [String]
    public var ingredient_exclusions: [Int]
    public var heat_tolerance: String
    public var equipment: [String]
    public var max_cook_minutes: Int?
    public var meal_budget_php: Decimal?
    public var preferred_language: String
    public var servings: Decimal

    public init(preferred_cuisines: [String] = ["Filipino"], preferred_regions: [String] = [],
                dislikes: [String] = [], diet_patterns: [String] = [], ingredient_exclusions: [Int] = [],
                heat_tolerance: String = "no_preference", equipment: [String] = [],
                max_cook_minutes: Int? = nil, meal_budget_php: Decimal? = nil,
                preferred_language: String = "en", servings: Decimal = 2) {
        self.preferred_cuisines = preferred_cuisines
        self.preferred_regions = preferred_regions
        self.dislikes = dislikes
        self.diet_patterns = diet_patterns
        self.ingredient_exclusions = ingredient_exclusions
        self.heat_tolerance = heat_tolerance
        self.equipment = equipment
        self.max_cook_minutes = max_cook_minutes
        self.meal_budget_php = meal_budget_php
        self.preferred_language = preferred_language
        self.servings = servings
    }
}

nonisolated public struct FoodAllergy: Codable, Equatable, Sendable {
    public var allergen_code: String?
    public var custom_text: String?
    public var severity: String?
    public var cross_contact_concern: Bool
    public var notes: String?

    public init(allergen_code: String? = nil, custom_text: String? = nil, severity: String? = nil,
                cross_contact_concern: Bool = false, notes: String? = nil) {
        self.allergen_code = allergen_code
        self.custom_text = custom_text
        self.severity = severity
        self.cross_contact_concern = cross_contact_concern
        self.notes = notes
    }
}

nonisolated public struct FoodProfileRead: Decodable, Equatable, Sendable {
    public let scope: String
    public let revision: Int?
    public var preferences: FoodPreferences
    public var allergy_status: String
    public var allergies: [FoodAllergy]

    public init(scope: String, revision: Int? = nil, preferences: FoodPreferences = FoodPreferences(),
                allergy_status: String = "NOT_PROVIDED", allergies: [FoodAllergy] = []) {
        self.scope = scope
        self.revision = revision
        self.preferences = preferences
        self.allergy_status = allergy_status
        self.allergies = allergies
    }
}

nonisolated public struct FoodProfileWrite: Encodable, Sendable {
    public let expected_revision: Int?
    public let preferences: FoodPreferences
    public let allergy_status: String
    public let allergies: [FoodAllergy]

    public init(revision: Int?, preferences: FoodPreferences, allergyStatus: String, allergies: [FoodAllergy]) {
        expected_revision = revision
        self.preferences = preferences
        allergy_status = allergyStatus
        self.allergies = allergies
    }
}

nonisolated public struct IngredientAlias: Decodable, Sendable {
    public let alias: String
    public let language: String
    public let region: String?
}

nonisolated public struct IngredientCandidate: Decodable, Identifiable, Sendable {
    public let id: Int
    public let canonical_name: String
    public let filipino_name: String?
    public let family: String?
    public let default_unit: String?
    public let aliases: [IngredientAlias]
    public let is_active: Bool
    public let matched_alias: String?
}

nonisolated public struct IngredientLookup: Decodable, Sendable {
    public let query: String?
    public let ambiguous: Bool
    public let results: [IngredientCandidate]
}

nonisolated public enum IngredientMappingMode: String, Codable, Sendable {
    case direct = "DIRECT"
    case composite = "COMPOSITE"
    case unknown = "UNKNOWN"
}

nonisolated public struct ProductIngredientMappingRead: Decodable, Sendable {
    public let id: Int
    public let product_id: Int
    public let version: Int
    public let is_current: Bool
    public let mode: IngredientMappingMode
    public let ingredient_id: Int?
    public let verification_status: String
    public let method: String
    public let verified_by_user_id: Int?
    public let verified_at: String?
    public let confidence: Decimal?
    public let unknown_composition: Bool
    public let component_ingredient_ids: [Int]
    public let package_factors: [ProductPackageFactorRead]
    public let created_at: String
    public let updated_at: String
}

nonisolated public struct ProductPackageFactorRead: Decodable, Sendable {
    public let ingredient_id: Int
    public let inventory_unit: String
    public let ingredient_amount: Decimal
    public let ingredient_unit: String
    public let source_reference: String
    public let verified_by_user_id: Int?
    public let verified_at: String
}

nonisolated public struct IngredientMappingComponent: Codable, Sendable {
    public let ingredient_id: Int
    public init(ingredientID: Int) { ingredient_id = ingredientID }
}

nonisolated public struct ProductPackageFactorWrite: Encodable, Sendable {
    public let ingredient_id: Int
    public let inventory_unit: String
    public let ingredient_amount: ExactQuantity
    public let ingredient_unit: String
    public let source_reference: String

    public init(ingredientID: Int, inventoryUnit: String, ingredientAmount: ExactQuantity,
                ingredientUnit: String, sourceReference: String) {
        ingredient_id = ingredientID
        inventory_unit = inventoryUnit
        ingredient_amount = ingredientAmount
        ingredient_unit = ingredientUnit
        source_reference = sourceReference
    }
}

nonisolated public struct ProductIngredientMappingWrite: Encodable, Sendable {
    public let expected_version: Int?
    public let mode: IngredientMappingMode
    public let ingredient_id: Int?
    public let components: [IngredientMappingComponent]
    public let verified: Bool
    public let method: String
    public let confidence: Decimal?
    public let unknown_composition: Bool
    public let package_factors: [ProductPackageFactorWrite]

    public init(version: Int?, mode: IngredientMappingMode, ingredientID: Int?, componentIDs: [Int],
                verified: Bool, compositionKnown: Bool) {
        expected_version = version
        self.mode = mode
        ingredient_id = ingredientID
        components = componentIDs.map { IngredientMappingComponent(ingredientID: $0) }
        self.verified = verified
        method = "user_package_label_review"
        confidence = nil
        unknown_composition = !compositionKnown
        package_factors = []
    }
}

nonisolated public struct ProductLabelRead: Decodable, Sendable {
    public let product_id: Int
    public let mapping_version: Int
    public let revision: Int
    public let declared_allergens: [String]
    public let possible_allergens: [String]
    public let custom_allergens: [String]
    public let composition_known: Bool
    public let source_reference: String
    public let reviewed_by_user_id: Int?
    public let reviewed_at: String
    public let current_for_product: Bool
    public let revoked: Bool
    public let revoked_at: String?
    public let revoked_by_user_id: Int?
}

nonisolated public struct ProductLabelWrite: Encodable, Sendable {
    public let expected_revision: Int?
    public let expected_mapping_version: Int
    public let expected_product_updated_at: String
    public let reviewed: Bool
    public let declared_allergens: [String]
    public let possible_allergens: [String]
    public let custom_allergens: [String]
    public let composition_known: Bool
    public let source_reference: String

    public init(revision: Int?, mappingVersion: Int, productUpdatedAt: String,
                declaredAllergens: [String], possibleAllergens: [String], customAllergens: [String],
                compositionKnown: Bool, sourceReference: String) {
        expected_revision = revision
        expected_mapping_version = mappingVersion
        expected_product_updated_at = productUpdatedAt
        reviewed = true
        self.declared_allergens = declaredAllergens
        self.possible_allergens = possibleAllergens
        self.custom_allergens = customAllergens
        self.composition_known = compositionKnown
        self.source_reference = sourceReference
    }
}
