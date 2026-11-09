import Foundation

// MARK: - User Model
// Conforms to FastAPI backend app.schemas.auth.UserRead

nonisolated public struct User: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var email: String
    public var display_name: String?
    public var is_active: Bool
    public var created_at: String
    public var default_household_id: Int?
    public var default_household_name: String?
    
    public init(
        id: Int,
        email: String,
        display_name: String? = nil,
        is_active: Bool = true,
        created_at: String = "",
        default_household_id: Int? = nil,
        default_household_name: String? = nil
    ) {
        self.id = id
        self.email = email
        self.display_name = display_name
        self.is_active = is_active
        self.created_at = created_at
        self.default_household_id = default_household_id
        self.default_household_name = default_household_name
    }
    
    public var displayNameOrEmail: String {
        if let name = display_name, !name.trimmingCharacters(in: .whitespaces).isEmpty {
            return name
        }
        return email
    }
}

nonisolated public struct HouseholdMembership: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public let name: String
    public let role: String
    public let is_default: Bool
}

nonisolated public struct HouseholdContext: Codable, Sendable {
    public let id: Int
    public let name: String
    public let role: String
}

/// Stored in Keychain only after the server has verified this exact token and household.
nonisolated public struct VerifiedHouseholdSession: Codable, Sendable {
    public let token: String
    public let user: User
    public let scope: HouseholdScope
    public let households: [HouseholdMembership]

    public func isUsableOffline(token currentToken: String, now: Date = Date()) -> Bool {
        guard token == currentToken, user.id == scope.userID,
              households.contains(where: { $0.id == scope.householdID }) else { return false }
        let parts = token.split(separator: ".")
        guard parts.count == 3 else { return false }
        var payload = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        payload += String(repeating: "=", count: (4 - payload.count % 4) % 4)
        guard let data = Data(base64Encoded: payload),
              let claims = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let expiration = claims["exp"] as? TimeInterval else { return false }
        return expiration.isFinite && now.timeIntervalSince1970 < expiration
    }
}

// MARK: - Authentication DTOs

nonisolated public struct AuthToken: Codable, Sendable {
    public let access_token: String
    public let token_type: String
    
    public init(access_token: String, token_type: String = "bearer") {
        self.access_token = access_token
        self.token_type = token_type
    }
}

nonisolated public struct LoginRequest: Codable, Sendable {
    public let email: String
    public let password: String
    
    public init(email: String, password: String) {
        self.email = email
        self.password = password
    }
}

nonisolated public struct RegisterRequest: Codable, Sendable {
    public let email: String
    public let password: String
    public let display_name: String?
    
    public init(email: String, password: String, display_name: String? = nil) {
        self.email = email
        self.password = password
        self.display_name = display_name
    }
}
