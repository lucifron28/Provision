import Foundation
import UserNotifications
import Combine

// MARK: - Background Expiration Alert Notification Service

public final class NotificationService: @unchecked Sendable {
    public static let shared = NotificationService()
    
    private let center = UNUserNotificationCenter.current()
    private let alertsEnabledKey = "provision_expiration_alerts_enabled"
    
    public var isAlertsEnabled: Bool {
        get {
            UserDefaults.standard.object(forKey: alertsEnabledKey) as? Bool ?? true
        }
        set {
            UserDefaults.standard.set(newValue, forKey: alertsEnabledKey)
            if !newValue {
                cancelAllExpirationAlerts()
            }
        }
    }
    
    public init() {}
    
    /// Requests notification authorization from user
    public func requestAuthorization() async -> Bool {
        do {
            let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
            return granted
        } catch {
            return false
        }
    }
    
    /// Checks current authorization status
    public func checkAuthorizationStatus() async -> UNAuthorizationStatus {
        let settings = await center.notificationSettings()
        return settings.authorizationStatus
    }
    
    /// Synchronizes expiration alert notifications based on currently expiring items
    public func syncExpirationAlerts(expiringSoon: [ExpiringSoonItem]) async {
        guard isAlertsEnabled else {
            cancelAllExpirationAlerts()
            return
        }
        
        // Filter items expiring within 2 days
        let urgentItems = expiringSoon.filter { $0.days_until_expiration <= 2 }
        guard !urgentItems.isEmpty else {
            cancelAllExpirationAlerts()
            return
        }
        
        let status = await checkAuthorizationStatus()
        guard status == .authorized || status == .provisional else {
            return
        }
        
        // Cancel existing and schedule a fresh morning notification
        cancelAllExpirationAlerts()
        
        let content = UNMutableNotificationContent()
        content.title = "Pantry Expiration Alert"
        if urgentItems.count == 1, let first = urgentItems.first {
            content.body = "⚠️ \(first.product_name) expires in \(first.days_until_expiration) days! Use it before it spoils."
        } else {
            let names = urgentItems.prefix(2).map { $0.product_name }.joined(separator: ", ")
            content.body = "⚠️ \(urgentItems.count) items expiring soon (\(names)). Check your pantry today!"
        }
        content.sound = .default
        content.badge = NSNumber(value: urgentItems.count)
        
        // Schedule daily at 8:00 AM
        var dateComponents = DateComponents()
        dateComponents.hour = 8
        dateComponents.minute = 0
        
        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: true)
        let request = UNNotificationRequest(
            identifier: "provision_daily_expiration_alert",
            content: content,
            trigger: trigger
        )
        
        try? await center.add(request)
    }
    
    /// Cancels scheduled expiration alerts
    public func cancelAllExpirationAlerts() {
        center.removePendingNotificationRequests(withIdentifiers: ["provision_daily_expiration_alert"])
    }
}
