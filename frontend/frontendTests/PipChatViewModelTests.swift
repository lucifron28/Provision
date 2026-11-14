import XCTest
@testable import frontend

private actor PipChatServiceSpy: PipChatService {
    private var consent: PipChatConsent
    private var requests: [PipChatRequest] = []
    private let failsOffline: Bool
    private let response: PipChatResponse

    init(consent: PipChatConsent, failsOffline: Bool = false,
         response: PipChatResponse = PipChatResponse(reply: "Sige, let's cook together.", language: "taglish")) {
        self.consent = consent
        self.failsOffline = failsOffline
        self.response = response
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
        return response
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

    func testContextAndRecentRecipesStayBoundedToTheConversation() async throws {
        let card = PipChatRecipeCard(
            reference: "R1",
            recipe_id: 301,
            title: "Tinolang Manok",
            summary: nil,
            cuisine: "Filipino",
            availability_status: "partial",
            missing_ingredient_count: 1,
            safety_decision: "eligible",
            safety_reasons: []
        )
        let service = PipChatServiceSpy(
            consent: PipChatConsent(
                chatGranted: true,
                allMembersChatGranted: true,
                providerEnabled: true,
                notice: "Test notice"
            ),
            response: PipChatResponse(reply: "Review this stored recipe.", language: "english", recipeCards: [card])
        )
        let context = PipChatContext(kind: .product, id: 88)
        let viewModel = PipChatViewModel(scope: scope, context: context, service: service)

        await viewModel.loadConsent()
        viewModel.draft = "Suggest a meal with this product."
        await viewModel.send()
        viewModel.draft = "What was that recipe?"
        await viewModel.send()

        let requests = await service.recordedRequests()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].context, context)
        XCTAssertEqual(requests[0].recent_recipe_ids, [])
        XCTAssertEqual(requests[1].context, context)
        XCTAssertEqual(requests[1].recent_recipe_ids, [301])
        XCTAssertEqual(viewModel.messages.last?.recipeCards.map(\.recipe_id), [301])
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
