import Combine
import Foundation

@MainActor
public final class CookWithPipPreferencesViewModel: ObservableObject {
    @Published public private(set) var profile: FoodProfileRead?
    @Published public var preferences = FoodPreferences()
    @Published public var allergyStatus = "NOT_PROVIDED"
    @Published public var allergies: [FoodAllergy] = []
    @Published public private(set) var isLoading = false
    @Published public private(set) var isSaving = false
    @Published public private(set) var hasLoaded = false
    @Published public private(set) var errorMessage: String?
    @Published public private(set) var successMessage: String?

    private let scope: HouseholdScope
    private let service: any CookWithPipWorkflowService

    public init(scope: HouseholdScope, service: any CookWithPipWorkflowService = APIClient.shared) {
        self.scope = scope
        self.service = service
    }

    public var canSave: Bool {
        return switch allergyStatus {
        case "DECLARED": !allergies.isEmpty
        case "NOT_PROVIDED", "NONE_DECLARED": allergies.isEmpty
        default: false
        }
    }

    public func load() async {
        isLoading = true
        errorMessage = nil
        do {
            let value = try await service.fetchMyFoodProfile(scope: scope)
            profile = value
            preferences = value.preferences
            allergyStatus = value.allergy_status
            allergies = value.allergies
            successMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        hasLoaded = true
        isLoading = false
    }

    public func save() async {
        guard canSave else {
            errorMessage = "Choose an allergy declaration that matches the listed allergies."
            return
        }
        isSaving = true
        errorMessage = nil
        successMessage = nil
        do {
            let saved = try await service.saveMyFoodProfile(
                FoodProfileWrite(revision: profile?.revision, preferences: preferences,
                                 allergyStatus: allergyStatus, allergies: allergies),
                scope: scope
            )
            profile = saved
            preferences = saved.preferences
            allergyStatus = saved.allergy_status
            allergies = saved.allergies
            successMessage = "Your cooking preferences were saved."
        } catch {
            errorMessage = error.localizedDescription
        }
        isSaving = false
    }
}
