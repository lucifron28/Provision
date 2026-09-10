import Foundation
import Security

// MARK: - Native iOS Keychain Store
// Manages secure, hardware-encrypted storage for JWT access tokens
// using Apple's Security framework (SecItemAdd, SecItemCopyMatching, SecItemDelete).

public final class KeychainStore {
    public static let shared = KeychainStore()
    
    private let service = "mseuf.edu.ph.provision.auth"
    private let tokenAccount = "accessToken"
    
    private init() {}
    
    /// Saves the JWT access token securely into the iOS Keychain.
    /// Overwrites existing token if present.
    @discardableResult
    public func saveAccessToken(_ token: String) -> Bool {
        guard let data = token.data(using: .utf8) else { return false }
        
        // Delete any existing token item first to ensure a clean insert
        deleteAccessToken()
        
        // Build Keychain query dictionary
        // kSecAttrAccessibleAfterFirstUnlock ensures token is available whenever the device is unlocked
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]
        
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
}
