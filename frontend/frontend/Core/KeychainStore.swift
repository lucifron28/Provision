import Foundation
import Security

// MARK: - Native iOS Keychain Store
// Manages secure, hardware-encrypted storage for JWT access tokens
// using Apple's Security framework (SecItemAdd, SecItemCopyMatching, SecItemDelete).

public protocol CredentialStore {
    @discardableResult func saveAccessToken(_ token: String) -> Bool
    func readAccessToken() -> String?
    @discardableResult func deleteAccessToken() -> Bool
    @discardableResult func saveVerifiedSession(_ session: VerifiedHouseholdSession) -> Bool
    func readVerifiedSession() -> VerifiedHouseholdSession?
    func deleteVerifiedSession()
}

public final class KeychainStore: CredentialStore {
    public static let shared = KeychainStore()
    
    private let service = "mseuf.edu.ph.provision.auth"
    private let tokenAccount = "accessToken"
    private let verifiedSessionAccount = "verifiedHouseholdSession"
    
    private init() {}
    
    /// Saves the JWT access token securely into the iOS Keychain.
    /// Overwrites existing token if present.
    @discardableResult
    public func saveAccessToken(_ token: String) -> Bool {
        guard let data = token.data(using: .utf8) else { return false }
        
        // Build Keychain query dictionary
        // kSecAttrAccessibleAfterFirstUnlock ensures token is available whenever the device is unlocked
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]
        
        let identity: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: tokenAccount]
        let updateStatus = SecItemUpdate(identity as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if updateStatus == errSecSuccess { return true }
        guard updateStatus == errSecItemNotFound else { return false }
        let status = SecItemAdd(query as CFDictionary, nil)
        return status == errSecSuccess
    }
    
    /// Reads the stored JWT access token from the iOS Keychain.
    /// Returns nil if no token is saved or an error occurs.
    public func readAccessToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var dataTypeRef: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &dataTypeRef)
        
        guard status == errSecSuccess, let data = dataTypeRef as? Data else {
            return nil
        }
        
        return String(data: data, encoding: .utf8)
    }
    
    /// Deletes the JWT access token from the iOS Keychain upon logout.
    @discardableResult
    public func deleteAccessToken() -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount
        ]
        
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }

    public func saveVerifiedSession(_ session: VerifiedHouseholdSession) -> Bool {
        guard let data = try? JSONEncoder().encode(session) else { return false }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: verifiedSessionAccount]
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecSuccess { return true }
        guard status == errSecItemNotFound else { return false }
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        return SecItemAdd(item as CFDictionary, nil) == errSecSuccess
    }

    public func readVerifiedSession() -> VerifiedHouseholdSession? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: verifiedSessionAccount,
            kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(VerifiedHouseholdSession.self, from: data)
    }

    public func deleteVerifiedSession() {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: verifiedSessionAccount]
        SecItemDelete(query as CFDictionary)
    }
}
