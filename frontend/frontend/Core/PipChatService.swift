import Foundation

public protocol PipChatService: Sendable {
    func fetchPipChatConsent(scope: HouseholdScope) async throws -> PipChatConsent
    func updatePipChatConsent(_ update: PipChatConsentUpdate,
                              scope: HouseholdScope) async throws -> PipChatConsent
    func revokePipChatConsent(scope: HouseholdScope) async throws -> PipChatConsent
    func sendPipChat(_ request: PipChatRequest,
                     scope: HouseholdScope) async throws -> PipChatResponse
}

extension APIClient: PipChatService {}
