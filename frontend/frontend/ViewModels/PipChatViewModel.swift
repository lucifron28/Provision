import Combine
import Foundation

nonisolated enum PipChatMessageRole: String, Sendable {
    case user
    case assistant
}

nonisolated public struct PipChatDisplayMessage: Identifiable, Sendable {
    public let id = UUID()
    let role: PipChatMessageRole
    let text: String
    let facts: [PipChatFact]
    let actions: [PipChatAction]
    let recipeCards: [PipChatRecipeCard]
    let safetyNotice: String?
    let includeInProviderHistory: Bool

    init(role: PipChatMessageRole, text: String, facts: [PipChatFact] = [],
         actions: [PipChatAction] = [], recipeCards: [PipChatRecipeCard] = [],
         safetyNotice: String? = nil,
         includeInProviderHistory: Bool = true) {
        self.role = role
        self.text = text
        self.facts = facts
        self.actions = actions
        self.recipeCards = recipeCards
        self.safetyNotice = safetyNotice
        self.includeInProviderHistory = includeInProviderHistory
    }
}

@MainActor
public final class PipChatViewModel: ObservableObject {
    @Published public private(set) var consent: PipChatConsent?
    @Published public private(set) var messages: [PipChatDisplayMessage] = []
    @Published public var draft = ""
    @Published public private(set) var isLoadingConsent = false
    @Published public private(set) var isSending = false
    @Published public private(set) var isUpdatingConsent = false
    @Published public private(set) var hasLoadedConsent = false
    @Published public private(set) var isOffline = false
    @Published public private(set) var errorMessage: String?

    private let scope: HouseholdScope
    private let context: PipChatContext?
    private let service: any PipChatService
    private var recentRecipeIDs: [Int] = []

    public init(scope: HouseholdScope, context: PipChatContext? = nil,
                service: any PipChatService) {
        self.scope = scope
        self.context = context
        self.service = service
    }

    public var isChatReady: Bool {
        consent?.all_active_members_chat_granted == true && consent?.provider_enabled == true
    }

    public var canSend: Bool {
        isChatReady && !isSending && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func loadConsent() async {
        guard !isLoadingConsent else { return }
        isLoadingConsent = true
        defer {
            isLoadingConsent = false
            hasLoadedConsent = true
        }
        do {
            consent = try await service.fetchPipChatConsent(scope: scope)
            isOffline = false
            errorMessage = nil
        } catch {
            isOffline = Self.isNetworkError(error)
            errorMessage = error.localizedDescription
        }
    }

    public func setConsent(_ purpose: PipChatConsentPurpose, granted: Bool) async {
        guard !isUpdatingConsent else { return }
        isUpdatingConsent = true
        defer { isUpdatingConsent = false }
        do {
            consent = try await service.updatePipChatConsent(
                PipChatConsentUpdate(purpose: purpose, granted: granted),
                scope: scope
            )
            isOffline = false
            errorMessage = nil
            if !granted { clearConversation() }
        } catch {
            isOffline = Self.isNetworkError(error)
            errorMessage = error.localizedDescription
        }
    }

    public func revokeAllConsent() async {
        guard !isUpdatingConsent else { return }
        isUpdatingConsent = true
        defer { isUpdatingConsent = false }
        do {
            consent = try await service.revokePipChatConsent(scope: scope)
            clearConversation()
            isOffline = false
            errorMessage = nil
        } catch {
            isOffline = Self.isNetworkError(error)
            errorMessage = error.localizedDescription
        }
    }

    public func send() async {
        let message = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard isChatReady, !isSending, !message.isEmpty, message.count <= 1200 else { return }
        var recentMessages = Array(messages.filter { $0.includeInProviderHistory }.suffix(8))
        while recentMessages.reduce(message.count, { $0 + $1.text.count }) > 4000,
              recentMessages.count >= 2 {
            recentMessages.removeFirst(2)
        }
        let history = recentMessages.map {
            PipChatHistoryTurn(role: $0.role.rawValue, content: $0.text)
        }
        isSending = true
        errorMessage = nil
        defer { isSending = false }
        do {
            let response = try await service.sendPipChat(
                PipChatRequest(
                    message: message,
                    history: history,
                    context: context,
                    recentRecipeIDs: recentRecipeIDs.filter { id in
                        context?.kind != .recipe || context?.id != id
                    }
                ),
                scope: scope
            )
            let responseRecipeIDs = response.recipe_cards.map(\.recipe_id)
                + response.actions.map(\.recipe_id)
            var nextRecipeIDs: [Int] = []
            for id in responseRecipeIDs + recentRecipeIDs where !nextRecipeIDs.contains(id) {
                nextRecipeIDs.append(id)
                if nextRecipeIDs.count == 3 { break }
            }
            recentRecipeIDs = nextRecipeIDs
            messages.append(PipChatDisplayMessage(
                role: .user,
                text: message,
                includeInProviderHistory: !response.local_guidance
            ))
            messages.append(PipChatDisplayMessage(
                role: .assistant,
                text: response.reply,
                facts: response.facts,
                actions: response.actions,
                recipeCards: response.recipe_cards,
                safetyNotice: response.safety_notice,
                includeInProviderHistory: !response.local_guidance
            ))
            draft = ""
            isOffline = false
        } catch {
            isOffline = Self.isNetworkError(error)
            errorMessage = error.localizedDescription
        }
    }

    public func clearConversation() {
        messages.removeAll()
        recentRecipeIDs.removeAll()
        draft = ""
    }

    private static func isNetworkError(_ error: Error) -> Bool {
        if let apiError = error as? APIError,
           case .networkError(let underlying) = apiError {
            return isNetworkError(underlying)
        }
        guard let urlError = error as? URLError else { return false }
        return [
            .notConnectedToInternet, .timedOut, .cannotFindHost, .cannotConnectToHost,
            .networkConnectionLost, .dnsLookupFailed
        ].contains(urlError.code)
    }
}
