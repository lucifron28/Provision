import Foundation

// MARK: - User Model
// Conforms to FastAPI backend app.schemas.auth.UserRead

public struct User: Codable, Identifiable, Hashable, Sendable {
    public let id: Int
    public var email: String
    public var display_name: String?
    public var is_active: Bool
    public var created_at: String
    
    public init(
        id: Int,
        email: String,
        display_name: String? = nil,
        is_active: Bool = true,
        created_at: String = ""
    ) {
        self.id = id
        self.email = email
        self.display_name = display_name
        self.is_active = is_active
        self.created_at = created_at
    }
    
    public var displayNameOrEmail: String {
        if let name = display_name, !name.trimmingCharacters(in: .whitespaces).isEmpty {
            return name
        }
        return email
    }
}

// MARK: - Authentication DTOs

public struct AuthToken: Codable, Sendable {
    public let access_token: String
    public let token_type: String
    
    public init(access_token: String, token_type: String = "bearer") {
        self.access_token = access_token
        self.token_type = token_type
    }
}

public struct LoginRequest: Codable, Sendable {
    public let email: String
    public let password: String
    
    public init(email: String, password: String) {
        self.email = email
        self.password = password
    }
}

public struct RegisterRequest: Codable, Sendable {
    public let email: String
    public let password: String
    public let display_name: String?
    
    public init(email: String, password: String, display_name: String? = nil) {
        self.email = email
        self.password = password
        self.display_name = display_name
    }
}
