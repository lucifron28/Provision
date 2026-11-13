import XCTest
@testable import frontend

private actor PipChatServiceSpy: PipChatService {
    private var consent: PipChatConsent
    private var requests: [PipChatRequest] = []
    private let failsOffline: Bool

    init(consent: PipChatConsent, failsOffline: Bool = false) {
        self.consent = consent
        self.failsOffline = failsOffline
    }

    func fetchPipChatConsent(scope: HouseholdScope) async throws -> PipChatConsent {
        consent
    }

    func updatePipChatConsent(_ update: PipChatConsentUpdate,
                              scope: HouseholdScope) async throws -> PipChatConsent {
        let chat = update.purpose == PipChatConsentPurpose.chat.rawValue
            ? update.granted : consent.chat_granted
        let allergy = update.purpose == PipChatConsentPurpose.allergySharing.rawValue
            ? update.granted : consent.allergy_sharing_granted
        consent = PipChatConsent(
            chatGranted: chat,
            allMembersChatGranted: chat,
            allergySharingGranted: chat && allergy,
            allMembersAllergySharingGranted: chat && allergy,
            providerEnabled: true,
            notice: "Test notice"
        )
        return consent
    }

    func revokePipChatConsent(scope: HouseholdScope) async throws -> PipChatConsent {
        consent = PipChatConsent(chatGranted: false, allMembersChatGranted: false, providerEnabled: true)
        return consent
    }

    func sendPipChat(_ request: PipChatRequest,
                     scope: HouseholdScope) async throws -> PipChatResponse {
        if failsOffline { throw URLError(.notConnectedToInternet) }
        requests.append(request)
        if request.message.localizedCaseInsensitiveContains("allergy") {
            return PipChatResponse(
                reply: "I can't use allergy details without separate permission.",
                language: "english",
                model: "local-guidance",
                localGuidance: true
            )
        }
        return PipChatResponse(reply: "Sige, let's cook together.", language: "taglish")
    }

    func recordedRequests() -> [PipChatRequest] { requests }
}

@MainActor
final class PipChatViewModelTests: XCTestCase {
    private let scope = HouseholdScope(userID: 11, householdID: 22, serverID: "pip-chat-test")

    func testConversationUsesBoundedHistoryAndClearsAfterRevocation() async throws {
        let service = PipChatServiceSpy(consent: PipChatConsent(
            chatGranted: true,
            allMembersChatGranted: true,
            providerEnabled: true,
            notice: "Test notice"
        ))
        let viewModel = PipChatViewModel(scope: scope, service: service)

        await viewModel.loadConsent()
        XCTAssertTrue(viewModel.isChatReady)
        viewModel.draft = "Anong lulutuin natin?"
        await viewModel.send()
        XCTAssertEqual(viewModel.messages.count, 2)
        XCTAssertEqual(viewModel.messages.last?.text, "Sige, let's cook together.")

        viewModel.draft = "May iba ka pang idea?"
        await viewModel.send()
        let requests = await service.recordedRequests()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[1].history.map(\.role), ["user", "assistant"])
        XCTAssertEqual(requests[1].history.first?.content, "Anong lulutuin natin?")

        viewModel.draft = "I have a peanut allergy."
        await viewModel.send()
        viewModel.draft = "What else could I make?"
        await viewModel.send()
        let requestsAfterLocalGuidance = await service.recordedRequests()
        XCTAssertEqual(requestsAfterLocalGuidance.count, 4)
        XCTAssertFalse(requestsAfterLocalGuidance[3].history.contains { $0.content.contains("allergy") })

        await viewModel.setConsent(.allergySharing, granted: false)
        XCTAssertTrue(viewModel.messages.isEmpty)
        XCTAssertTrue(viewModel.draft.isEmpty)
    }

    func testSendIsBlockedUntilEveryActiveHouseholdMemberConsents() async {
        let service = PipChatServiceSpy(consent: PipChatConsent(
            chatGranted: true,
            allMembersChatGranted: false,
            providerEnabled: true,
            notice: "Test notice"
        ))
        let viewModel = PipChatViewModel(scope: scope, service: service)
        await viewModel.loadConsent()
        viewModel.draft = "Hello Pip"

        XCTAssertFalse(viewModel.isChatReady)
        await viewModel.send()
        XCTAssertTrue(viewModel.messages.isEmpty)
        let requests = await service.recordedRequests()
        XCTAssertTrue(requests.isEmpty)
    }

    func testOfflineSendKeepsDraftAndShowsOfflineState() async {
        let service = PipChatServiceSpy(consent: PipChatConsent(
            chatGranted: true,
            allMembersChatGranted: true,
            providerEnabled: true,
            notice: "Test notice"
        ), failsOffline: true)
        let viewModel = PipChatViewModel(scope: scope, service: service)
        await viewModel.loadConsent()
        viewModel.draft = "Let's cook something."

        await viewModel.send()

        XCTAssertTrue(viewModel.isOffline)
        XCTAssertEqual(viewModel.draft, "Let's cook something.")
        XCTAssertTrue(viewModel.messages.isEmpty)
        XCTAssertNotNil(viewModel.errorMessage)
    }
}
