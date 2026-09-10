import SwiftUI

// MARK: - Provision Theme
// Visual foundation reflecting the warm, modern pantry identity from Figma

public enum ProvisionTheme {
    // Brand & Neutral Palette
    public static let background = Color(red: 0.98, green: 0.97, blue: 0.95) // Warm neutral #FAF7F2
    public static let surface = Color.white
    public static let surfaceSecondary = Color(red: 0.96, green: 0.94, blue: 0.91) // Soft beige #F5F0E8
    public static let heroCard = Color(red: 0.97, green: 0.93, blue: 0.87) // Warm peach #F7EDE0
    
    public static let provisionGreen = Color(red: 0.20, green: 0.38, blue: 0.26) // Deep forest green #336142
    public static let provisionGreenLight = Color(red: 0.91, green: 0.95, blue: 0.92) // Soft green tag
    
    public static let amberWarning = Color(red: 0.88, green: 0.55, blue: 0.15) // Warning amber #E08C26
    public static let amberLight = Color(red: 0.99, green: 0.95, blue: 0.88)
    
    public static let redAlert = Color(red: 0.82, green: 0.24, blue: 0.24) // Urgency red #D13D3D
    public static let redLight = Color(red: 0.98, green: 0.92, blue: 0.92)
    
    public static let textPrimary = Color(red: 0.12, green: 0.14, blue: 0.13)
    public static let textSecondary = Color(red: 0.45, green: 0.47, blue: 0.46)
    public static let textTertiary = Color(red: 0.65, green: 0.67, blue: 0.66)
    public static let border = Color(red: 0.90, green: 0.88, blue: 0.84)
}

// MARK: - View Modifiers

public struct ProvisionCardStyle: ViewModifier {
    var backgroundColor: Color = ProvisionTheme.surface
    var cornerRadius: CGFloat = 16
    var borderColor: Color = ProvisionTheme.border.opacity(0.6)
    
    public func body(content: Content) -> some View {
        content
            .background(backgroundColor)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(borderColor, lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.03), radius: 6, x: 0, y: 2)
    }
}

public extension View {
    func provisionCard(
        backgroundColor: Color = ProvisionTheme.surface,
        cornerRadius: CGFloat = 16,
        borderColor: Color = ProvisionTheme.border.opacity(0.6)
    ) -> some View {
        modifier(ProvisionCardStyle(backgroundColor: backgroundColor, cornerRadius: cornerRadius, borderColor: borderColor))
    }
}
