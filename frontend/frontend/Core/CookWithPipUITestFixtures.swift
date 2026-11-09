#if DEBUG
import Foundation
import SwiftUI

struct CookWithPipUITestService: CookWithPipService {
    private let recipes: [HouseholdRecipe]
    private let cookNowResults: [RecipeRecommendation]
    private let almostThereResults: [RecipeRecommendation]
    private let evaluations: [Int: RecipeEvaluation]

    init() {
        let unknown = IngredientAvailabilitySnapshot(
            ingredient_id: 901,
            canonical_name: nil,
            display_names: ["kangkong"],
            required: true,
            required_amount: nil,
            available_amount: nil,
            shortfall: nil,
            unit: "g",
            status: "unknown",
            covered_batch_ids: [],
            missing_expiry_batch_ids: [],
            unknown_reasons: ["ingredient_mapping_unknown"]
        )
        let missingPork = IngredientAvailabilitySnapshot(
            ingredient_id: 902,
            canonical_name: "pork",
            display_names: ["baboy"],
            required: true,
            required_amount: Self.quantity("0.750000"),
            available_amount: Self.quantity("0.250000"),
            shortfall: Self.quantity("0.500000"),
            unit: "kg",
            status: "partial",
            covered_batch_ids: [1902],
            missing_expiry_batch_ids: [],
            unknown_reasons: []
        )
        let missingGabi = IngredientAvailabilitySnapshot(
            ingredient_id: 903,
            canonical_name: "taro leaves",
            display_names: ["dahon ng gabi"],
            required: true,
            required_amount: Self.quantity("300"),
            available_amount: Self.quantity("0"),
            shortfall: Self.quantity("300"),
            unit: "g",
            status: "missing",
            covered_batch_ids: [],
            missing_expiry_batch_ids: [],
            unknown_reasons: []
        )

        let sinigang = Self.makeRecipe(
            id: 301,
            title: "Test Recipe: Sinigang na Baboy",
            region: "Tagalog",
            summary: "A synthetic UI fixture with exact ingredient amounts.",
            prepMinutes: 15,
            cookMinutes: 40,
            ingredients: [
                Self.makeIngredient(id: 911, name: "baboy", amount: "0.500000", unit: "kg"),
                Self.makeIngredient(id: 912, name: "sampalok", amount: "45.250000", unit: "g"),
                Self.makeIngredient(id: 913, name: "kangkong", amount: "120", unit: "g", required: false)
            ]
        )
        let laing = Self.makeRecipe(
            id: 302,
            title: "Test Recipe: Laing",
            region: "Bicolano",
            summary: "A synthetic fixture with two server-reported missing items.",
            prepMinutes: 10,
            cookMinutes: 35,
            ingredients: [
                Self.makeIngredient(id: 902, name: "baboy", amount: "0.750000", unit: "kg"),
                Self.makeIngredient(id: 903, name: "dahon ng gabi", amount: "300", unit: "g")
            ]
        )
        let bicolExpress = Self.makeRecipe(
            id: 303,
            title: "Test Recipe: Bicol Express",
            region: "Bicolano",
            summary: "A synthetic fixture with unknown ingredient and label data.",
            prepMinutes: 12,
            cookMinutes: 38,
            ingredients: [
                Self.makeIngredient(id: nil, name: "kangkong", amount: "100.000000", unit: "g"),
                Self.makeIngredient(id: 914, name: "gata", amount: "200.000000", unit: "ml")
            ]
        )

        let sinigangEvaluation = Self.makeEvaluation(
            recipe: sinigang,
            decision: "eligible",
            availability: [
                Self.availabilityLine(id: 911, name: "baboy", required: true, needed: "0.500000", available: "0.500000", shortfall: "0", unit: "kg", status: "full", batchIDs: [1901]),
                Self.availabilityLine(id: 912, name: "sampalok", required: true, needed: "45.250000", available: "60.000000", shortfall: "0", unit: "g", status: "full", batchIDs: [1903]),
                Self.availabilityLine(id: 913, name: "kangkong", required: false, needed: "120", available: "120", shortfall: "0", unit: "g", status: "full", batchIDs: [1904])
            ],
            ingredientDecisions: [
                Self.safetyLine(index: 0, id: 911, decision: "eligible"),
                Self.safetyLine(index: 1, id: 912, decision: "eligible"),
                Self.safetyLine(index: 2, id: 913, decision: "eligible")
            ]
        )
        let laingEvaluation = Self.makeEvaluation(
            recipe: laing,
            decision: "eligible",
            availability: [missingPork, missingGabi],
            ingredientDecisions: [
                Self.safetyLine(index: 0, id: 902, decision: "eligible"),
                Self.safetyLine(index: 1, id: 903, decision: "eligible")
            ],
            overallAvailability: "partial"
        )
        let bicolExpressEvaluation = Self.makeEvaluation(
            recipe: bicolExpress,
            decision: "review_required",
            reasons: ["product_allergen_label_not_reviewed"],
            availability: [unknown, Self.availabilityLine(id: 914, name: "gata", required: true, needed: "200.000000", available: "200.000000", shortfall: "0", unit: "ml", status: "full", batchIDs: [1905])],
            ingredientDecisions: [
                Self.safetyLine(index: 0, id: nil, decision: "review_required", reasons: ["ingredient_mapping_unknown"]),
                Self.safetyLine(index: 1, id: 914, decision: "review_required", reasons: ["product_allergen_label_not_reviewed"])
            ],
            overallAvailability: "unknown"
        )

        recipes = [bicolExpress, laing, sinigang]
        evaluations = [
            sinigang.id: sinigangEvaluation,
            laing.id: laingEvaluation,
            bicolExpress.id: bicolExpressEvaluation
        ]
        cookNowResults = [Self.recommendation(recipe: sinigang, evaluation: sinigangEvaluation, missingCount: 0)]
        almostThereResults = [Self.recommendation(recipe: laing, evaluation: laingEvaluation, missingCount: 2)]
    }

    func fetchRecipePage(query: String?, limit: Int, offset: Int,
                         scope: HouseholdScope) async throws -> [HouseholdRecipe] {
        let matching = recipes.filter { recipe in
            guard let query, !query.isEmpty else { return true }
            return recipe.title.localizedCaseInsensitiveContains(query)
        }
        return Array(matching.dropFirst(offset).prefix(limit))
    }

    func fetchRecipe(id: Int, scope: HouseholdScope) async throws -> HouseholdRecipe {
        guard let recipe = recipes.first(where: { $0.id == id }) else {
            throw APIError.http(status: 404, detail: nil, retryAfter: nil)
        }
        return recipe
    }

    func evaluateRecipe(id: Int, payload: RecipeEvaluationRequest,
                        scope: HouseholdScope) async throws -> RecipeEvaluation {
        guard let evaluation = evaluations[id] else {
            throw APIError.http(status: 404, detail: nil, retryAfter: nil)
        }
        return evaluation
    }

    func recommendRecipes(_ payload: RecipeRecommendationRequest,
                          scope: HouseholdScope) async throws -> RecipeRecommendations {
        let candidates = payload.mode == "cook_now" ? cookNowResults : almostThereResults
        let matching = candidates.filter { recommendation in
            guard let query = payload.query, !query.isEmpty else { return true }
            return recommendation.recipe.title.localizedCaseInsensitiveContains(query)
        }
        let page = Array(matching.dropFirst(payload.candidate_offset).prefix(payload.limit))
        return RecipeRecommendations(
            items: page,
            candidates_evaluated: page.count,
            has_more_candidates: payload.candidate_offset + page.count < matching.count,
            excluded_blocked: 0,
            excluded_review_required: 0,
            excluded_unknown_quantities: 0,
            provider_enabled: false
        )
    }

    func fetchRecipeSourceReference(id: Int, scope: HouseholdScope) async throws -> RecipeSourceReference {
        throw APIError.http(status: 404, detail: nil, retryAfter: nil)
    }
}

@MainActor
struct CookWithPipUITestHost: View {
    private let scope = HouseholdScope(userID: 9901, householdID: 9902, serverID: "ui-test-fixtures")
    private let service = CookWithPipUITestService()

    var body: some View {
        HomeView(
            viewModel: HomeViewModel(isPreview: true),
            authVM: PreviewData.makeAuthViewModel(),
            cookWithPipScope: scope,
            cookWithPipService: service
        )
        .safeAreaInset(edge: .top, spacing: 0) {
            Text("UI TEST FIXTURES")
                .font(.caption.weight(.bold))
                .foregroundStyle(ProvisionTheme.onAccent)
                .frame(maxWidth: .infinity, minHeight: 26)
                .background(ProvisionTheme.provisionGreen)
                .accessibilityIdentifier("ui-test-fixture-banner")
        }
    }
}

private extension CookWithPipUITestService {
    static func makeRecipe(id: Int, title: String, region: String, summary: String,
                            prepMinutes: Int, cookMinutes: Int,
                            ingredients: [RecipeIngredient]) -> HouseholdRecipe {
        HouseholdRecipe(
            id: id,
            revision: 1,
            is_active: true,
            provenance: "USER_ENTERED",
            title: title,
            summary: summary,
            cuisine: "Filipino",
            content_permission: "OWNED_OR_PERMISSION_GRANTED",
            adapted_from_recipe_id: nil,
            adapted_from_recipe_revision: nil,
            ph_regions: [region],
            course_categories: ["dinner"],
            dish_types: ["ulam"],
            difficulty: "beginner",
            prep_minutes: prepMinutes,
            cook_minutes: cookMinutes,
            servings: Self.quantity("4.000000"),
            equipment: ["stovetop"],
            spice_level: "medium",
            instructions: ["Prepare the measured ingredients.", "Cook until ready and check the package labels."],
            ingredients: ingredients
        )
    }

    static func makeIngredient(id: Int?, name: String, amount: String, unit: String,
                                required: Bool = true) -> RecipeIngredient {
        RecipeIngredient(
            ingredient_id: id,
            display_name: name,
            amount: Self.quantity(amount),
            unit: unit,
            required: required,
            preparation: nil,
            substitution_options: []
        )
    }

    static func availabilityLine(id: Int, name: String, required: Bool, needed: String,
                                   available: String, shortfall: String, unit: String,
                                   status: String, batchIDs: [Int]) -> IngredientAvailabilitySnapshot {
        IngredientAvailabilitySnapshot(
            ingredient_id: id,
            canonical_name: name,
            display_names: [name],
            required: required,
            required_amount: Self.quantity(needed),
            available_amount: Self.quantity(available),
            shortfall: Self.quantity(shortfall),
            unit: unit,
            status: status,
            covered_batch_ids: batchIDs,
            missing_expiry_batch_ids: [],
            unknown_reasons: []
        )
    }

    static func safetyLine(index: Int, id: Int?, decision: String,
                            reasons: [String] = []) -> IngredientSafetySnapshot {
        IngredientSafetySnapshot(requirement_index: index, ingredient_id: id, decision: decision, reasons: reasons)
    }

    static func makeEvaluation(recipe: HouseholdRecipe, decision: String,
                                reasons: [String] = [], availability: [IngredientAvailabilitySnapshot],
                                ingredientDecisions: [IngredientSafetySnapshot],
                                overallAvailability: String = "full") -> RecipeEvaluation {
        RecipeEvaluation(
            recipe_id: recipe.id,
            recipe_revision: recipe.revision,
            included_requirement_indexes: Array(recipe.ingredients.indices),
            result: FoodSafetySnapshot(
                decision: decision,
                reasons: reasons,
                ingredients: ingredientDecisions,
                availability: RecipeAvailabilitySnapshot(
                    recipe_servings: recipe.servings,
                    servings: recipe.servings,
                    overall_status: overallAvailability,
                    requirements: availability
                ),
                notice: "No known conflict is not a safety guarantee. Check actual labels and preparation."
            )
        )
    }

    static func recommendation(recipe: HouseholdRecipe, evaluation: RecipeEvaluation,
                                missingCount: Int) -> RecipeRecommendation {
        RecipeRecommendation(
            recipe: recipe,
            evaluation: evaluation.result,
            coverage: Self.quantity(missingCount == 0 ? "1" : "0.5"),
            missing_ingredient_count: missingCount,
            near_expiry_batch_count: 0,
            preference_match: true,
            source_reference: nil
        )
    }

    static func quantity(_ value: String) -> ExactQuantity {
        ExactQuantity(Decimal(string: value, locale: Locale(identifier: "en_US_POSIX"))!)
    }
}
#endif
