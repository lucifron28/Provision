import Foundation
import SwiftUI
import Combine

public enum AuthState: Equatable {
    case checkingSession
    case sessionUnavailable
    case signedOut
    case signedIn(User)
}

@MainActor
public class AuthViewModel: ObservableObject {
    @Published public var authState: AuthState = .checkingSession
    @Published public var currentUser: User? = nil
    @Published public var isLoading: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public private(set) var households: [HouseholdMembership] = []
    @Published public private(set) var selectedScope: HouseholdScope? = nil
    
    private let client: APIClient
    private let keychain: KeychainStore
    public var isPreview: Bool
    
    public init(client: APIClient = .shared, keychain: KeychainStore = .shared, isPreview: Bool = false) {
        self.client = client
        self.keychain = keychain
        self.isPreview = isPreview
    }

    private func establishSession(_ user: User) async throws {
        let memberships = try await client.fetchHouseholds()
        guard let membership = memberships.first(where: { $0.id == user.default_household_id })
                ?? memberships.first(where: { $0.is_default }) else {
            throw APIError.invalidResponse(403, "No authorized household membership")
        }
        let scope = try await client.selectHousehold(membership.id, userID: user.id)
        households = memberships
        selectedScope = scope
        currentUser = user
        errorMessage = nil
        persistVerifiedSession()
        authState = .signedIn(user)
    }

    private func persistVerifiedSession() {
        guard let token = keychain.readAccessToken(), let user = currentUser, let scope = selectedScope else { return }
        _ = keychain.saveVerifiedSession(VerifiedHouseholdSession(token: token, user: user, scope: scope, households: households))
    }

    public func selectHousehold(_ household: HouseholdMembership) async {
        guard let user = currentUser, selectedScope?.householdID != household.id else { return }
        let previousScope = selectedScope
        errorMessage = nil
        authState = .checkingSession
        NotificationService.shared.clearHouseholdAlerts()
        await client.setHouseholdScope(nil)
        do {
            selectedScope = try await client.selectHousehold(household.id, userID: user.id)
            persistVerifiedSession()
        } catch {
            errorMessage = error.localizedDescription
            if case APIError.unauthorized = error {
                keychain.deleteAccessToken()
                keychain.deleteVerifiedSession()
                await client.setAccessToken(nil)
                currentUser = nil
                selectedScope = nil
                households = []
                authState = .signedOut
                return
            }
            await client.setHouseholdScope(previousScope)
        }
        authState = .signedIn(user)
    }
    
    /// Restores session on app launch by verifying Keychain token against /auth/me.
    public func checkExistingSession() async {
        if isPreview { return }
        NotificationService.shared.clearHouseholdAlerts()
        guard let token = keychain.readAccessToken(), !token.isEmpty else {
            self.currentUser = nil
            self.authState = .signedOut
            return
        }
        
        await client.setAccessToken(token)
        
        do {
            let user = try await client.fetchCurrentUser()
            try await establishSession(user)
        } catch {
            self.currentUser = nil
            self.selectedScope = nil
            self.households = []
            if case APIError.unauthorized = error {
                keychain.deleteAccessToken()
                keychain.deleteVerifiedSession()
                await client.setAccessToken(nil)
                await client.clearCache()
                self.authState = .signedOut
            } else if case APIError.networkError = error,
                      let verified = keychain.readVerifiedSession(), verified.isUsableOffline(token: token),
                      verified.scope.serverID == (await client.currentServerID()) {
                await client.setHouseholdScope(verified.scope)
                self.currentUser = verified.user
                self.households = verified.households
                self.selectedScope = verified.scope
                self.errorMessage = nil
                self.authState = .signedIn(verified.user)
            } else {
                self.errorMessage = error.localizedDescription
                self.authState = .sessionUnavailable
            }
        }
    }
    
    /// Authenticates user credentials via POST /auth/login and stores JWT in Keychain.
    public func login(email: String, password: String) async -> Bool {
        isLoading = true
        errorMessage = nil
        
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        
        do {
            let tokenResponse = try await client.login(request: LoginRequest(email: trimmedEmail, password: password))
            guard keychain.saveAccessToken(tokenResponse.access_token) else {
                throw APIError.serverMessage("Could not securely save your session.")
            }
            await client.setAccessToken(tokenResponse.access_token)
            
            let user = try await client.fetchCurrentUser()
            try await establishSession(user)
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
        if isPreview {
            self.currentUser = nil
            self.authState = .signedOut
            return
        }
        NotificationService.shared.clearHouseholdAlerts()
        keychain.deleteAccessToken()
        keychain.deleteVerifiedSession()
        await client.setAccessToken(nil)
        await client.clearCache()
        self.currentUser = nil
        self.selectedScope = nil
        self.households = []
        self.authState = .signedOut
    }
}
