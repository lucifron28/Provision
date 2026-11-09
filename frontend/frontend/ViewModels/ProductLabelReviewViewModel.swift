import Combine
import Foundation

@MainActor
public final class ProductLabelReviewViewModel: ObservableObject {
    @Published public private(set) var product: Product?
    @Published public private(set) var mapping: ProductIngredientMappingRead?
    @Published public private(set) var label: ProductLabelRead?
    @Published public private(set) var searchResults: [IngredientCandidate] = []
    @Published public var searchText = ""
    @Published public var mappingMode: IngredientMappingMode = .unknown
    @Published public var selectedIngredientIDs: Set<Int> = []
    @Published public var mappingVerified = false
    @Published public var mappingCompositionKnown = false
    @Published public var declaredAllergens: Set<String> = []
    @Published public var possibleAllergens: Set<String> = []
    @Published public var customAllergenText = ""
    @Published public var labelCompositionKnown = false
    @Published public var sourceReference = ""
    @Published public private(set) var isLoading = false
    @Published public private(set) var isSearching = false
    @Published public private(set) var isSaving = false
    @Published public private(set) var hasLoaded = false
    @Published public private(set) var errorMessage: String?
    @Published public private(set) var statusMessage: String?

    private let productID: Int
    private let scope: HouseholdScope
    private let service: any CookWithPipWorkflowService

    public init(productID: Int, scope: HouseholdScope, service: any CookWithPipWorkflowService = APIClient.shared) {
        self.productID = productID
        self.scope = scope
        self.service = service
    }

    public var canReviewLabel: Bool {
        guard product?.updated_at != nil,
              let mapping,
              mapping.verification_status == "VERIFIED",
              !mapping.unknown_composition,
              mapping.mode != .unknown,
              !sourceReference.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        return true
    }

    public var canSaveMapping: Bool { isValidMappingSelection }

    public func load() async {
        isLoading = true
        errorMessage = nil
        statusMessage = nil
        do {
            let currentProduct = try await service.fetchProductForCookWithPip(id: productID, scope: scope)
            product = currentProduct
            do {
                mapping = try await service.fetchProductMapping(productID: productID, scope: scope)
                mappingMode = mapping?.mode ?? .unknown
                mappingVerified = mapping?.verification_status == "VERIFIED"
                mappingCompositionKnown = mapping?.unknown_composition == false
                if let mapping {
                    if mapping.mode == .direct, let ingredientID = mapping.ingredient_id {
                        selectedIngredientIDs = [ingredientID]
                    } else {
                        selectedIngredientIDs = Set(mapping.component_ingredient_ids)
                    }
                }
            } catch {
                if isNotFound(error) {
                    mapping = nil
                    mappingMode = .unknown
                    mappingVerified = false
                    mappingCompositionKnown = false
                    selectedIngredientIDs = []
                } else { throw error }
            }
            do {
                label = try await service.fetchProductLabel(productID: productID, scope: scope)
                if let label {
                    declaredAllergens = Set(label.declared_allergens)
                    possibleAllergens = Set(label.possible_allergens)
                    customAllergenText = label.custom_allergens.joined(separator: ", ")
                    labelCompositionKnown = label.composition_known
                    sourceReference = label.source_reference
                }
            } catch {
                if isNotFound(error) { label = nil }
                else { throw error }
            }
        } catch {
            errorMessage = friendlyMessage(error)
        }
        hasLoaded = true
        isLoading = false
    }

    public func searchIngredients() async {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else {
            searchResults = []
            return
        }
        isSearching = true
        errorMessage = nil
        do {
            searchResults = try await service.lookupIngredients(query: query, limit: 30, scope: scope).results
        } catch {
            errorMessage = friendlyMessage(error)
        }
        isSearching = false
    }

    @discardableResult
    public func saveMapping() async -> Bool {
        guard isValidMappingSelection else {
            errorMessage = mappingMode == .direct
                ? "Choose exactly one matching ingredient for a direct mapping."
                : "Choose at least two matching ingredients for a composite mapping."
            return false
        }
        isSaving = true
        errorMessage = nil
        statusMessage = nil
        let ids = selectedIngredientIDs.sorted()
        do {
            mapping = try await service.saveProductMapping(
                productID: productID,
                mapping: ProductIngredientMappingWrite(
                    version: mapping?.version,
                    mode: mappingMode,
                    ingredientID: mappingMode == .direct ? ids.first : nil,
                    componentIDs: mappingMode == .composite ? ids : [],
                    verified: mappingVerified && mappingCompositionKnown,
                    compositionKnown: mappingCompositionKnown
                ),
                scope: scope
            )
            statusMessage = "Ingredient mapping saved. Review the package against this mapping before recording allergens."
            do {
                label = try await service.fetchProductLabel(productID: productID, scope: scope)
            } catch {
                if isNotFound(error) { label = nil }
                else { errorMessage = friendlyMessage(error) }
            }
            isSaving = false
            return true
        } catch {
            errorMessage = friendlyMessage(error)
        }
        isSaving = false
        return false
    }

    @discardableResult
    public func saveLabel() async -> Bool {
        guard canReviewLabel, let mapping, let product, let updatedAt = product.updated_at else {
            errorMessage = "A current product and verified complete ingredient mapping are required before recording a label review."
            return false
        }
        let custom = splitList(customAllergenText)
        guard custom.allSatisfy({ $0.count <= 180 }), declaredAllergens.isDisjoint(with: possibleAllergens) else {
            errorMessage = "Each custom allergen must be 180 characters or fewer, and cannot be both declared and possible."
            return false
        }
        let source = sourceReference.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !source.isEmpty else {
            errorMessage = "Enter where you read this information, such as the package label."
            return false
        }
        isSaving = true
        errorMessage = nil
        statusMessage = nil
        do {
            label = try await service.saveProductLabel(
                productID: productID,
                label: ProductLabelWrite(
                    revision: label?.revision,
                    mappingVersion: mapping.version,
                    productUpdatedAt: updatedAt,
                    declaredAllergens: declaredAllergens.sorted(),
                    possibleAllergens: possibleAllergens.sorted(),
                    customAllergens: custom,
                    compositionKnown: labelCompositionKnown,
                    sourceReference: source
                ),
                scope: scope
            )
            statusMessage = "Package label review recorded. It is not a safety certification."
            isSaving = false
            return true
        } catch {
            errorMessage = friendlyMessage(error)
        }
        isSaving = false
        return false
    }

    public func setAllergen(_ code: FoodAllergenCode, disposition: String) {
        declaredAllergens.remove(code.rawValue)
        possibleAllergens.remove(code.rawValue)
        if disposition == "declared" { declaredAllergens.insert(code.rawValue) }
        if disposition == "possible" { possibleAllergens.insert(code.rawValue) }
    }

    private var isValidMappingSelection: Bool {
        return switch mappingMode {
        case .direct: selectedIngredientIDs.count == 1
        case .composite: selectedIngredientIDs.count >= 2
        case .unknown: selectedIngredientIDs.isEmpty && !mappingVerified && !mappingCompositionKnown
        }
    }

    private func isNotFound(_ error: Error) -> Bool {
        guard let apiError = error as? APIError, case .http(status: 404, _, _) = apiError else { return false }
        return true
    }

    private func friendlyMessage(_ error: Error) -> String {
        guard let apiError = error as? APIError else { return error.localizedDescription }
        return switch apiError.serverErrorCode {
        case "PRODUCT_CHANGED": "Product details changed on the server. Reload before reviewing this label."
        case "MAPPING_VERSION_CONFLICT": "The ingredient mapping changed. Reload it and review the product again."
        case "PRODUCT_LABEL_REVISION_CONFLICT": "The label review changed. Reload it before editing."
        default: error.localizedDescription
        }
    }

    private func splitList(_ text: String) -> [String] {
        var seen = Set<String>()
        return text.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && seen.insert($0.lowercased()).inserted }
    }
}

@MainActor
public final class ProductLabelListViewModel: ObservableObject {
    @Published public private(set) var products: [Product] = []
    @Published public private(set) var isLoading = false
    @Published public private(set) var errorMessage: String?

    private let scope: HouseholdScope
    private let service: any CookWithPipWorkflowService

    public init(scope: HouseholdScope, service: any CookWithPipWorkflowService = APIClient.shared) {
        self.scope = scope
        self.service = service
    }

    public func load() async {
        isLoading = true
        errorMessage = nil
        do {
            products = try await service.fetchProductsForCookWithPip(scope: scope)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
