#if DEBUG
import Foundation
import SwiftUI

private actor CookWithPipUITestScenarioCounter {
    private var recommendationRequests = 0
    private var sourceRequests = 0
    private var previewRequests = 0
    private var confirmationRequests = 0
    private var lastConfirmedLines: [RecipeShoppingAcceptedLine] = []
    private var confirmations: [RecipeShoppingConfirmation] = []

    func nextRecommendation() -> Int { recommendationRequests += 1; return recommendationRequests }
    func nextSource() -> Int { sourceRequests += 1; return sourceRequests }
    func nextPreview() -> Int { previewRequests += 1; return previewRequests }
    func nextConfirmation() -> Int { confirmationRequests += 1; return confirmationRequests }
    func recordConfirmation(_ confirmation: RecipeShoppingConfirmation) {
        confirmations.append(confirmation)
        lastConfirmedLines = confirmation.accepted_lines
    }
    func confirmedLines() -> [RecipeShoppingAcceptedLine] { lastConfirmedLines }
    func recordedConfirmations() -> [RecipeShoppingConfirmation] { confirmations }
}

struct CookWithPipUITestService: CookWithPipService, CookWithPipWorkflowService {
    private let recipes: [HouseholdRecipe]
    private let cookNowResults: [RecipeRecommendation]
    private let almostThereResults: [RecipeRecommendation]
    private let evaluations: [Int: RecipeEvaluation]
    private let scenario: String
    private let counter: CookWithPipUITestScenarioCounter

    static func launchArgument(_ name: String) -> String? {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: name), arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }

    init(scenario override: String? = nil) {
        scenario = override ?? Self.launchArgument("-pip-ui-scenario") ?? "default"
        counter = CookWithPipUITestScenarioCounter()
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
                Self.makeIngredient(id: 912, name: "sampalok", amount: "45.250000", unit: "g",
                                    substitutionOptions: [IngredientRequirement(
                                        displayName: "calamansi", amount: Self.quantity("30.000000"), unit: "g"
                                    )]),
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
        let pinakbet = Self.makeRecipe(
            id: 304,
            title: "Test Recipe: Pinakbet na Ilokano na may mahahabang pangalan ng sangkap",
            region: "Ilocos",
            summary: "A synthetic fixture for long Filipino ingredient names and blocked safety states.",
            prepMinutes: 18,
            cookMinutes: 42,
            ingredients: [
                Self.makeIngredient(id: 915, name: "talong na hiniwa nang pahaba at inalisan ng dulo", amount: "250", unit: "g"),
                Self.makeIngredient(id: 916, name: "bagoong isda na may hindi pa nasusuring label", amount: "30", unit: "g")
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
        let pinakbetEvaluation = Self.makeEvaluation(
            recipe: pinakbet,
            decision: "blocked",
            reasons: ["declared_allergen_conflict"],
            availability: [
                Self.availabilityLine(id: 915, name: "talong", required: true, needed: "250", available: "0", shortfall: "250", unit: "g", status: "missing", batchIDs: []),
                Self.availabilityLine(id: 916, name: "bagoong isda", required: true, needed: "30", available: "30", shortfall: "0", unit: "g", status: "full", batchIDs: [1906])
            ],
            ingredientDecisions: [
                Self.safetyLine(index: 0, id: 915, decision: "eligible"),
                Self.safetyLine(index: 1, id: 916, decision: "blocked", reasons: ["declared_allergen_conflict"])
            ],
            overallAvailability: "missing"
        )

        recipes = [bicolExpress, laing, sinigang, pinakbet]
        evaluations = [
            sinigang.id: sinigangEvaluation,
            laing.id: laingEvaluation,
            bicolExpress.id: bicolExpressEvaluation,
            pinakbet.id: pinakbetEvaluation
        ]
        cookNowResults = [Self.recommendation(recipe: sinigang, evaluation: sinigangEvaluation, missingCount: 0)]
        almostThereResults = [Self.recommendation(recipe: laing, evaluation: laingEvaluation, missingCount: 2)]
    }

    func fetchRecipePage(query: String?, limit: Int, offset: Int,
                         scope: HouseholdScope) async throws -> [HouseholdRecipe] {
        if scenario == "recipes-empty" { return [] }
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
        let requestNumber = await counter.nextRecommendation()
        if scenario == "recipes-offline-once", requestNumber == 1 {
            throw APIError.networkError(URLError(.notConnectedToInternet))
        }
        if scenario == "recipes-loading", requestNumber == 1 {
            try? await Task.sleep(for: .seconds(8))
        }
        let candidates = scenario == "recipes-empty" ? [] : (payload.mode == "cook_now" ? cookNowResults : almostThereResults)
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
        if scenario == "source-error-once", await counter.nextSource() == 1 {
            throw APIError.http(status: 503, detail: .string("synthetic source failure"), retryAfter: nil)
        }
        throw APIError.http(status: 404, detail: nil, retryAfter: nil)
    }

    func fetchMyFoodProfile(scope: HouseholdScope) async throws -> FoodProfileRead {
        FoodProfileRead(
            scope: "member",
            revision: 2,
            preferences: FoodPreferences(preferred_cuisines: ["Filipino", "Bicolano"], servings: Decimal(string: "2.5")!),
            allergy_status: "DECLARED",
            allergies: [FoodAllergy(allergen_code: "milk", severity: "severe", cross_contact_concern: true)]
        )
    }

    func saveMyFoodProfile(_ profile: FoodProfileWrite, scope: HouseholdScope) async throws -> FoodProfileRead {
        FoodProfileRead(scope: "member", revision: (profile.expected_revision ?? 0) + 1,
                        preferences: profile.preferences, allergy_status: profile.allergy_status,
                        allergies: profile.allergies)
    }

    func lookupIngredients(query: String?, limit: Int, scope: HouseholdScope) async throws -> IngredientLookup {
        let values = [
            IngredientCandidate(id: 9201, canonical_name: "coconut milk", filipino_name: "gata", family: "coconut",
                                default_unit: "mL", aliases: [], is_active: true, matched_alias: "gata"),
            IngredientCandidate(id: 9202, canonical_name: "water spinach", filipino_name: "kangkong", family: "leafy greens",
                                default_unit: "g", aliases: [], is_active: true, matched_alias: nil)
        ]
        let matches = values.filter { query == nil || $0.canonical_name.localizedCaseInsensitiveContains(query!) || $0.filipino_name?.localizedCaseInsensitiveContains(query!) == true }
        return IngredientLookup(query: query, ambiguous: matches.count > 1, results: Array(matches.prefix(limit)))
    }

    func fetchProductsForCookWithPip(scope: HouseholdScope) async throws -> [Product] {
        [Self.product]
    }

    func fetchProductForCookWithPip(id: Int, scope: HouseholdScope) async throws -> Product {
        guard id == Self.product.id else { throw APIError.http(status: 404, detail: nil, retryAfter: nil) }
        return Self.product
    }

    func fetchProductMapping(productID: Int, scope: HouseholdScope) async throws -> ProductIngredientMappingRead {
        guard productID == Self.product.id else { throw APIError.http(status: 404, detail: nil, retryAfter: nil) }
        return Self.mapping(version: 1)
    }

    func saveProductMapping(productID: Int, mapping: ProductIngredientMappingWrite,
                            scope: HouseholdScope) async throws -> ProductIngredientMappingRead {
        Self.mapping(version: (mapping.expected_version ?? 0) + 1, write: mapping)
    }

    func fetchProductLabel(productID: Int, scope: HouseholdScope) async throws -> ProductLabelRead {
        if scenario == "product-label-stale" {
            return ProductLabelRead(product_id: productID, mapping_version: 1, revision: 4,
                                    declared_allergens: ["milk"], possible_allergens: [], custom_allergens: [],
                                    composition_known: false, source_reference: "Synthetic package label",
                                    reviewed_by_user_id: 9901, reviewed_at: "2026-11-01T00:00:00Z",
                                    current_for_product: false, revoked: false, revoked_at: nil, revoked_by_user_id: nil)
        }
        throw APIError.http(status: 404, detail: nil, retryAfter: nil)
    }

    func saveProductLabel(productID: Int, label: ProductLabelWrite,
                          scope: HouseholdScope) async throws -> ProductLabelRead {
        ProductLabelRead(product_id: productID, mapping_version: label.expected_mapping_version,
                         revision: (label.expected_revision ?? 0) + 1,
                         declared_allergens: label.declared_allergens,
                         possible_allergens: label.possible_allergens,
                         custom_allergens: label.custom_allergens, composition_known: label.composition_known,
                         source_reference: label.source_reference, reviewed_by_user_id: 9901,
                         reviewed_at: "2026-11-09T00:00:00Z", current_for_product: true,
                         revoked: false, revoked_at: nil, revoked_by_user_id: nil)
    }

    func previewRecipeShopping(_ request: RecipeShoppingPreviewRequest,
                               scope: HouseholdScope) async throws -> RecipeShoppingPreview {
        if scenario == "shopping-offline-once", await counter.nextPreview() == 1 {
            throw APIError.networkError(URLError(.notConnectedToInternet))
        }
        let decision = scenario == "shopping-review-required" ? "review_required"
            : (scenario == "shopping-blocked" ? "blocked" : "eligible")
        let reasons = decision == "review_required" ? ["product_allergen_label_not_reviewed"]
            : (decision == "blocked" ? ["declared_allergen_conflict"] : [])
        let secondLine = RecipeShoppingLine(
            ingredient_id: 914, canonical_name: "gata", display_name: "gata", unit: "mL",
            required_quantity: Self.quantity("200"), pantry_quantity: Self.quantity("50"),
            shortage: Self.quantity("150"), pending_quantity: Self.quantity("100"),
            target_quantity: Self.quantity("150"), additional_quantity: Self.quantity("50"),
            pending_item_ids: [9911, 9912], covered_batch_ids: [9905], status: "ready", review_reasons: [])
        let firstLine = RecipeShoppingLine(
            ingredient_id: 901, canonical_name: "kangkong", display_name: "kangkong", unit: "g",
            required_quantity: Self.quantity("120"), pantry_quantity: Self.quantity("20"),
            shortage: Self.quantity("100"), pending_quantity: Self.quantity("0"),
            target_quantity: Self.quantity("100"), additional_quantity: Self.quantity("100"),
            pending_item_ids: [], covered_batch_ids: [9904], status: "ready", review_reasons: [])
        var requirements = [
            IngredientAvailabilitySnapshot(ingredient_id: 901, canonical_name: "kangkong", display_names: ["kangkong"],
                required: true, required_amount: Self.quantity("120"), available_amount: Self.quantity("20"),
                shortfall: Self.quantity("100"), unit: "g", status: "partial", covered_batch_ids: [9904],
                missing_expiry_batch_ids: [], unknown_reasons: []),
            IngredientAvailabilitySnapshot(ingredient_id: 914, canonical_name: "gata", display_names: ["gata"],
                required: true, required_amount: Self.quantity("200"), available_amount: Self.quantity("50"),
                shortfall: Self.quantity("150"), unit: "mL", status: "partial", covered_batch_ids: [9905],
                missing_expiry_batch_ids: [], unknown_reasons: [])
        ]
        let optionalLine = RecipeShoppingLine(
            ingredient_id: 913, canonical_name: "kangkong", display_name: "kangkong (optional)", unit: "g",
            required_quantity: Self.quantity("120"), pantry_quantity: Self.quantity("120"),
            shortage: Self.quantity("0"), pending_quantity: Self.quantity("0"),
            target_quantity: Self.quantity("0"), additional_quantity: Self.quantity("0"),
            pending_item_ids: [], covered_batch_ids: [9904], status: "ready", review_reasons: [])
        if request.include_optional {
            requirements.append(IngredientAvailabilitySnapshot(
                ingredient_id: 913, canonical_name: "kangkong", display_names: ["kangkong"], required: false,
                required_amount: Self.quantity("120"), available_amount: Self.quantity("120"),
                shortfall: Self.quantity("0"), unit: "g", status: "full", covered_batch_ids: [9904],
                missing_expiry_batch_ids: [], unknown_reasons: []))
        }
        let readySafety = FoodSafetySnapshot(
            decision: decision, reasons: reasons,
            ingredients: [IngredientSafetySnapshot(requirement_index: 0, ingredient_id: 901,
                decision: decision, reasons: reasons)],
            availability: RecipeAvailabilitySnapshot(
                recipe_servings: request.servings, servings: request.servings, overall_status: "partial",
                requirements: requirements
            ), notice: "No known conflict is not a safety guarantee. Check actual labels and preparation."
        )
        return RecipeShoppingPreview(
            preview_id: "synthetic-preview-9905", expires_at: "2026-11-09T00:10:00Z", recipe_id: request.recipe_id,
            recipe_revision: request.expected_recipe_revision, servings: request.servings,
            include_optional: request.include_optional, shopping_revision: 3, inventory_revision: 7,
            included_requirement_indexes: request.include_optional ? [0, 1, 2] : [0, 1], safety: readySafety,
            lines: request.include_optional ? [firstLine, secondLine, optionalLine] : [firstLine, secondLine],
            unlinked_manual_items: [UnlinkedShoppingReview(item_id: 9906, name: "manual market note",
                quantity: Self.quantity("1"), unit: nil, candidate_ingredient_ids: [], reason: "not_linked")]
        )
    }

    func confirmRecipeShopping(_ confirmation: RecipeShoppingConfirmation,
                               scope: HouseholdScope) async throws -> RecipeShoppingConfirmationResult {
        await counter.recordConfirmation(confirmation)
        let attempt = await counter.nextConfirmation()
        if scenario == "shopping-retry" && attempt == 1 {
            throw APIError.networkError(URLError(.timedOut))
        }
        if scenario == "shopping-stale" && attempt == 1 {
            throw APIError.http(status: 409, detail: .string("STALE_PREVIEW"), retryAfter: nil)
        }
        return RecipeShoppingConfirmationResult(
            preview_id: confirmation.preview_id, shopping_revision: confirmation.expected_revision + 1,
            created: confirmation.accepted_lines.map { line in
                let name = line.ingredient_id == 914 ? "gata" : "kangkong"
                let unit = line.ingredient_id == 914 ? "mL" : "g"
                return RecipeShoppingChange(id: 9907 + line.ingredient_id, name: name, quantity: line.target_quantity,
                    unit: unit, is_bought: false, notes: nil, product_id: nil, ingredient_id: line.ingredient_id,
                    origin_recipe_id: 301, origin_recipe_revision: 1, origin_plan_id: nil, origin_plan_revision: nil,
                    created_at: nil, updated_at: nil)
            }, updated: [], unchanged: [], consolidated: confirmation.accepted_lines.filter { $0.consolidate_existing }.map { line in
                ConsolidatedShoppingItems(kept_item_id: 9911,
                    removed_items: [RecipeShoppingChange(id: 9912, name: "gata", quantity: line.target_quantity,
                        unit: "mL", is_bought: false, notes: nil, product_id: nil, ingredient_id: line.ingredient_id,
                        origin_recipe_id: nil, origin_recipe_revision: nil, origin_plan_id: nil,
                        origin_plan_revision: nil, created_at: nil, updated_at: nil)])
            }
        )
    }

    func fetchShoppingListFromServer(scope: HouseholdScope) async throws -> [ShoppingItem] {
        let lines = await counter.confirmedLines()
        return lines.enumerated().map { index, line in
            let name = line.ingredient_id == 914 ? "gata" : "kangkong"
            let unit = line.ingredient_id == 914 ? "mL" : "g"
            let amount = NSDecimalNumber(decimal: line.target_quantity.value).doubleValue
            return ShoppingItem(id: 9907 + index, name: name, product_id: nil, quantity: amount,
                                unit: unit, is_bought: false)
        }
    }

    func recordedConfirmations() async -> [RecipeShoppingConfirmation] {
        await counter.recordedConfirmations()
    }
}

@MainActor
struct CookWithPipUITestHost: View {
    private var scope: HouseholdScope {
        let fixtureID = Int(Self.launchArgument("-pip-ui-fixture-id") ?? "0") ?? 0
        return HouseholdScope(userID: 9901 + fixtureID, householdID: 9902 + fixtureID, serverID: "ui-test-fixtures")
    }
    private let service = CookWithPipUITestService()
    @State private var showingShoppingList = false
    @StateObject private var shoppingViewModel: ShoppingViewModel
    @State private var pendingShoppingStore: CookWithPipUITestPendingShoppingStore

    init() {
        let fixtureID = Int(Self.launchArgument("-pip-ui-fixture-id") ?? "0") ?? 0
        let scope = HouseholdScope(userID: 9901 + fixtureID, householdID: 9902 + fixtureID,
                                   serverID: "ui-test-fixtures")
        _shoppingViewModel = StateObject(wrappedValue: ShoppingViewModel(isPreview: true, scope: scope))
        _pendingShoppingStore = State(initialValue: CookWithPipUITestPendingShoppingStore())
    }

    private static func launchArgument(_ name: String) -> String? {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: name), arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
    }

    var body: some View {
        VStack(spacing: 0) {
            Text("UI TEST FIXTURES")
                .font(.caption.weight(.bold))
                .foregroundStyle(ProvisionTheme.textPrimary)
                .frame(maxWidth: .infinity, minHeight: 30)
                .background(ProvisionTheme.provisionGreenLight)
                .overlay(alignment: .bottom) {
                    Rectangle().fill(ProvisionTheme.border).frame(height: 1)
                }
                .accessibilityIdentifier("ui-test-fixture-banner")

            if showingShoppingList {
                NavigationStack {
                    ShoppingListView(viewModel: shoppingViewModel)
                }
            } else {
                HomeView(
                    viewModel: HomeViewModel(isPreview: true),
                    authVM: PreviewData.makeAuthViewModel(),
                    onNavigateToShopping: { showingShoppingList = true },
                    onShoppingConfirmed: {
                        shoppingViewModel.items = (try? await service.fetchShoppingListFromServer(scope: scope)) ?? []
                    },
                    cookWithPipScope: scope,
                    cookWithPipService: service,
                    cookWithPipWorkflowService: service,
                    cookWithPipPendingStore: pendingShoppingStore
                )
            }
        }
        .preferredColorScheme(Self.launchArgument("-pip-ui-appearance") == "dark" ? .dark : nil)
        .environment(\.dynamicTypeSize,
                     Self.launchArgument("-pip-ui-type") == "accessibility" ? .accessibility3 : .large)
    }
}

private extension CookWithPipUITestService {
    static var product: Product {
        Product(id: 9903, name: "Test Product: Gata", brand: "Synthetic fixture", category: "Canned goods",
                package_size: 400, unit: "mL", updated_at: "2026-11-09T00:00:00Z")
    }

    static func mapping(version: Int, write: ProductIngredientMappingWrite? = nil) -> ProductIngredientMappingRead {
        let mode = write?.mode ?? .direct
        let verified = write?.verified ?? true
        let componentIDs = mode == .composite ? (write?.components.map(\.ingredient_id) ?? []) : []
        return ProductIngredientMappingRead(
            id: 9908, product_id: product.id, version: version, is_current: true, mode: mode,
            ingredient_id: mode == .direct ? (write?.ingredient_id ?? 9201) : nil,
            verification_status: mode == .unknown ? "UNKNOWN" : (verified ? "VERIFIED" : "UNVERIFIED"),
            method: write?.method ?? "synthetic fixture",
            verified_by_user_id: verified ? 9901 : nil,
            verified_at: verified ? "2026-11-09T00:00:00Z" : nil, confidence: nil,
            unknown_composition: write?.unknown_composition ?? false,
            component_ingredient_ids: componentIDs, package_factors: [],
            created_at: "2026-11-09T00:00:00Z", updated_at: "2026-11-09T00:00:00Z"
        )
    }

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
                               required: Bool = true,
                               substitutionOptions: [IngredientRequirement] = []) -> RecipeIngredient {
        RecipeIngredient(
            ingredient_id: id,
            display_name: name,
            amount: Self.quantity(amount),
            unit: unit,
            required: required,
            preparation: nil,
            substitution_options: substitutionOptions
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

private final class CookWithPipUITestPendingShoppingStore: PendingRecipeShoppingStore {
    private let lock = NSLock()
    private var records: [String: PendingRecipeShoppingRecord] = [:]

    func readPendingRecipeShopping(scope: HouseholdScope) -> PendingRecipeShoppingRecord? {
        lock.lock()
        defer { lock.unlock() }
        return records[scope.storageKey]
    }

    func savePendingRecipeShopping(_ record: PendingRecipeShoppingRecord, scope: HouseholdScope) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        records[scope.storageKey] = record
        return true
    }

    func deletePendingRecipeShopping(scope: HouseholdScope) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return records.removeValue(forKey: scope.storageKey) != nil
    }
}
#endif
