import Foundation
import SwiftUI
import Combine

public enum AuthState: Equatable {
    case checkingSession
    case signedOut
    case signedIn(User)
}

@MainActor
public class AuthViewModel: ObservableObject {
    @Published public var authState: AuthState = .checkingSession
    @Published public var currentUser: User? = nil
    @Published public var isLoading: Bool = false
    @Published public var errorMessage: String? = nil
    
    private let client: APIClient
    private let keychain: KeychainStore
    
    public init(client: APIClient = .shared, keychain: KeychainStore = .shared) {
        self.client = client
        self.keychain = keychain
    }
    
    /// Restores session on app launch by verifying Keychain token against /auth/me.
    public func checkExistingSession() async {
        guard let token = keychain.readAccessToken(), !token.isEmpty else {
            self.currentUser = nil
            self.authState = .signedOut
            return
        }
        
        await client.setAccessToken(token)
        
        do {
            let user = try await client.fetchCurrentUser()
            self.currentUser = user
            self.authState = .signedIn(user)
        } catch {
            // Invalid or expired token: clear Keychain and return to Login
            keychain.deleteAccessToken()
            await client.setAccessToken(nil)
            self.currentUser = nil
            self.authState = .signedOut
        }
    }
    
    /// Authenticates user credentials via POST /auth/login and stores JWT in Keychain.
    public func login(email: String, password: String) async -> Bool {
        isLoading = true
        errorMessage = nil
        
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        
        do {
            let tokenResponse = try await client.login(request: LoginRequest(email: trimmedEmail, password: password))
            keychain.saveAccessToken(tokenResponse.access_token)
            await client.setAccessToken(tokenResponse.access_token)
            
            let user = try await client.fetchCurrentUser()
            self.currentUser = user
            self.authState = .signedIn(user)
            self.isLoading = false
            return true
        } catch {
            self.errorMessage = error.localizedDescription
            self.isLoading = false
            return false
        }
    }
    
    /// Registers a new user via POST /auth/register and automatically signs in.
    public func register(email: String, password: String, displayName: String?) async -> Bool {
        isLoading = true
        errorMessage = nil
        
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedName = displayName?.trimmingCharacters(in: .whitespacesAndNewlines)
        
        do {
            _ = try await client.register(
                request: RegisterRequest(
                    email: trimmedEmail,
                    password: password,
                    display_name: trimmedName?.isEmpty == true ? nil : trimmedName
                )
            )
            // Seamless auto-login on successful registration
            return await login(email: trimmedEmail, password: password)
        } catch {
            self.errorMessage = error.localizedDescription
            self.isLoading = false
            return false
        }
    }
    
    /// Clears the Keychain token, clears in-memory APIClient token, and returns app to signedOut.
    public func logout() async {
        keychain.deleteAccessToken()
        await client.setAccessToken(nil)
        self.currentUser = nil
        self.authState = .signedOut
    }
}
