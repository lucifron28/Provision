import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// MARK: - Provision Theme
// Visual foundation reflecting the warm, modern pantry identity from Figma

public enum ProvisionTheme {
    // MARK: - Adaptive Color Engine
    #if canImport(UIKit)
    private static func adaptive(
        light: (r: CGFloat, g: CGFloat, b: CGFloat),
        dark: (r: CGFloat, g: CGFloat, b: CGFloat)
    ) -> Color {
        Color(uiColor: UIColor { trait in
            if trait.userInterfaceStyle == .dark {
                return UIColor(red: dark.r, green: dark.g, blue: dark.b, alpha: 1.0)
            } else {
                return UIColor(red: light.r, green: light.g, blue: light.b, alpha: 1.0)
            }
        })
    }
    #else
    private static func adaptive(
        light: (r: CGFloat, g: CGFloat, b: CGFloat),
        dark: (r: CGFloat, g: CGFloat, b: CGFloat)
    ) -> Color {
        Color(red: light.r, green: light.g, blue: light.b)
    }
    #endif

    // MARK: - Canvas & Surface Palette (Adaptive)
    // Warm cream in light mode (#FAF7F2), rich warm dark charcoal in dark mode (#161916)
    public static let background = adaptive(light: (0.980, 0.969, 0.949), dark: (0.086, 0.098, 0.086))
    // Pure white in light (#FFFFFF), elevated warm card surface in dark (#212521)
    public static let surface = adaptive(light: (1.000, 1.000, 1.000), dark: (0.129, 0.145, 0.129))
    // Soft beige in light (#F5F0E8), secondary elevated surface in dark (#2C312C)
    public static let surfaceSecondary = adaptive(light: (0.961, 0.941, 0.910), dark: (0.173, 0.192, 0.173))
    // Warm peach hero (#F7EDE0), warm muted bronze hero (#2E2822)
    public static let heroCard = adaptive(light: (0.969, 0.929, 0.871), dark: (0.180, 0.157, 0.133))
    // Crisp input field background
    public static let inputBackground = adaptive(light: (1.000, 1.000, 1.000), dark: (0.161, 0.180, 0.161))

    // MARK: - Brand Forest Green
    // Deep forest green (#336142) in light; brighter vibrant green (#529167) in dark for WCAG AA >= 4.5:1
    public static let provisionGreen = adaptive(light: (0.200, 0.380, 0.259), dark: (0.322, 0.569, 0.404))
    public static let provisionGreenLight = adaptive(light: (0.910, 0.949, 0.922), dark: (0.118, 0.188, 0.137))

    // MARK: - Semantic Status Colors
    // Accessible warning amber with >= 4.5:1 contrast
    public static let amberWarning = adaptive(light: (0.678, 0.361, 0.051), dark: (0.898, 0.541, 0.180))
    public static let amberLight = adaptive(light: (0.988, 0.949, 0.878), dark: (0.216, 0.157, 0.086))

    // Accessible urgency red with >= 4.5:1 contrast
    public static let redAlert = adaptive(light: (0.780, 0.200, 0.200), dark: (0.918, 0.380, 0.380))
    public static let redLight = adaptive(light: (0.980, 0.918, 0.918), dark: (0.227, 0.114, 0.114))

    // MARK: - Text & Foreground Hierarchy
    // Dark charcoal in light mode (#1F2421), clean high-contrast warm white in dark mode (#F2F5F3)
    public static let textPrimary = adaptive(light: (0.122, 0.141, 0.129), dark: (0.949, 0.961, 0.953))
    public static let textSecondary = adaptive(light: (0.380, 0.400, 0.388), dark: (0.655, 0.678, 0.663))
    public static let textTertiary = adaptive(light: (0.459, 0.478, 0.467), dark: (0.522, 0.549, 0.533))
    public static let border = adaptive(light: (0.878, 0.863, 0.831), dark: (0.220, 0.243, 0.220))
}

// MARK: - Provision Semantic Typography (Dynamic Type Ready)

public enum ProvisionTypography {
    public static let heroSerif = Font.system(.title, design: .serif, weight: .bold)
    public static let titleSerif = Font.system(.title2, design: .serif, weight: .bold)
    public static let sectionSerif = Font.system(.title3, design: .serif, weight: .semibold)
    public static let headline = Font.headline
    public static let subheadline = Font.subheadline
    public static let body = Font.body
    public static let callout = Font.callout
    public static let footnote = Font.footnote
    public static let caption = Font.caption
    public static let caption2 = Font.caption2
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

// MARK: - Accessible Touch Targets & Minimum Hit Testing

public struct AccessibleTouchTarget: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
    }
}

public extension View {
    func accessibleTouchTarget() -> some View {
        modifier(AccessibleTouchTarget())
    }
}

// MARK: - Restrained Haptic Feedback

public enum HapticFeedback {
    #if os(iOS)
    @MainActor public static func light() {
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.prepare()
        generator.impactOccurred()
    }

    @MainActor public static func medium() {
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.prepare()
        generator.impactOccurred()
    }

    @MainActor public static func success() {
        let generator = UINotificationFeedbackGenerator()
        generator.prepare()
        generator.notificationOccurred(.success)
    }

    @MainActor public static func warning() {
        let generator = UINotificationFeedbackGenerator()
        generator.prepare()
        generator.notificationOccurred(.warning)
    }
    #else
    @MainActor public static func light() {}
    @MainActor public static func medium() {}
    @MainActor public static func success() {}
    @MainActor public static func warning() {}
    #endif
}

// MARK: - Accessible Input Field Modifier

public struct ProvisionInputFieldStyle: ViewModifier {
    public func body(content: Content) -> some View {
        content
            .foregroundStyle(ProvisionTheme.textPrimary)
            .tint(ProvisionTheme.provisionGreen)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(ProvisionTheme.inputBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(ProvisionTheme.border, lineWidth: 1)
            )
    }
}

public extension View {
    func provisionInputField() -> some View {
        modifier(ProvisionInputFieldStyle())
    }
}
