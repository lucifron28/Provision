import Foundation

nonisolated public enum PipChatConsentPurpose: String, Codable, Sendable {
    case chat = "pip_chat_v1"
    case allergySharing = "pip_chat_allergies_v1"

    public var policyVersion: String {
        switch self {
        case .chat: "2026-11-14-pip-chat-v2"
        case .allergySharing: "2026-11-13-pip-chat-allergy-v1"
        }
    }
}

nonisolated public struct PipChatContext: Codable, Hashable, Sendable {
    public enum Kind: String, Codable, Hashable, Sendable {
        case recipe
        case product
    }

    public let kind: Kind
    public let id: Int

    public init(kind: Kind, id: Int) {
        self.kind = kind
        self.id = id
    }
}

nonisolated public struct PipChatConsent: Decodable, Sendable, Equatable {
    public let chat_granted: Bool
    public let all_active_members_chat_granted: Bool
    public let allergy_sharing_granted: Bool
    public let all_active_members_allergy_sharing_granted: Bool
    public let provider_enabled: Bool
    public let chat_policy_version: String
    public let allergy_policy_version: String
    public let notice: String

    public init(chatGranted: Bool, allMembersChatGranted: Bool,
                allergySharingGranted: Bool = false, allMembersAllergySharingGranted: Bool = false,
                providerEnabled: Bool = true,
                chatPolicyVersion: String = "2026-11-14-pip-chat-v2",
                allergyPolicyVersion: String = "2026-11-13-pip-chat-allergy-v1",
                notice: String = "") {
        chat_granted = chatGranted
        all_active_members_chat_granted = allMembersChatGranted
        allergy_sharing_granted = allergySharingGranted
        all_active_members_allergy_sharing_granted = allMembersAllergySharingGranted
        provider_enabled = providerEnabled
        chat_policy_version = chatPolicyVersion
        allergy_policy_version = allergyPolicyVersion
        self.notice = notice
    }
}

nonisolated public struct PipChatConsentUpdate: Encodable, Sendable {
    public let purpose: String
    public let policy_version: String
    public let granted: Bool

    public init(purpose: PipChatConsentPurpose, granted: Bool) {
        self.purpose = purpose.rawValue
        self.policy_version = purpose.policyVersion
        self.granted = granted
    }
}

nonisolated public struct PipChatHistoryTurn: Codable, Sendable, Equatable {
    public let role: String
    public let content: String

    public init(role: String, content: String) {
        self.role = role
        self.content = content
    }
}

nonisolated public struct PipChatRequest: Encodable, Sendable {
    public let message: String
    public let history: [PipChatHistoryTurn]
    public let context: PipChatContext?
    public let recent_recipe_ids: [Int]

    public init(message: String, history: [PipChatHistoryTurn],
                context: PipChatContext? = nil, recentRecipeIDs: [Int] = []) {
        self.message = message
        self.history = history
        self.context = context
        recent_recipe_ids = recentRecipeIDs
    }
}

nonisolated public struct PipChatFact: Decodable, Sendable, Equatable, Identifiable {
    public let reference: String
    public let kind: String
    public let label: String
    public let detail: String
    public var id: String { reference }
}

nonisolated public struct PipChatAction: Decodable, Sendable, Equatable, Identifiable {
    public let kind: String
    public let reference: String
    public let recipe_id: Int
    public let title: String
    public var id: String { reference }

    public init(kind: String, reference: String, recipeID: Int, title: String) {
        self.kind = kind
        self.reference = reference
        recipe_id = recipeID
        self.title = title
    }
}

nonisolated public struct PipChatRecipeCard: Decodable, Sendable, Equatable, Identifiable {
    public let reference: String
    public let recipe_id: Int
    public let title: String
    public let summary: String?
    public let cuisine: String
    public let availability_status: String
    public let missing_ingredient_count: Int
    public let safety_decision: String
    public let safety_reasons: [String]
    public var id: String { reference }
}

nonisolated public struct PipChatResponse: Decodable, Sendable, Equatable {
    public let reply: String
    public let language: String
    public let facts: [PipChatFact]
    public let actions: [PipChatAction]
    public let recipe_cards: [PipChatRecipeCard]
    public let model: String
    public let local_guidance: Bool
    public let safety_notice: String

    public init(reply: String, language: String, facts: [PipChatFact] = [],
                actions: [PipChatAction] = [], recipeCards: [PipChatRecipeCard] = [],
                model: String = "fixture",
                localGuidance: Bool = false,
                safetyNotice: String = "Chat suggestions are not safety checks.") {
        self.reply = reply
        self.language = language
        self.facts = facts
        self.actions = actions
        recipe_cards = recipeCards
        self.model = model
        local_guidance = localGuidance
        safety_notice = safetyNotice
    }
}
