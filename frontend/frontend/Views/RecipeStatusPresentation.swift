import SwiftUI

public enum RecipeStatusTone: Sendable {
    case positive
    case warning
    case blocked
    case neutral

    fileprivate var foreground: Color {
        switch self {
        case .positive: ProvisionTheme.provisionGreen
        case .warning: ProvisionTheme.amberWarning
        case .blocked: ProvisionTheme.redAlert
        case .neutral: ProvisionTheme.textSecondary
        }
    }

    fileprivate var background: Color {
        switch self {
        case .positive: ProvisionTheme.provisionGreenLight
        case .warning: ProvisionTheme.amberLight
        case .blocked: ProvisionTheme.redLight
        case .neutral: ProvisionTheme.surfaceSecondary
        }
    }
}

public struct RecipeStatusPresentation: Sendable {
    public let title: String
    public let systemImage: String
    public let tone: RecipeStatusTone
    public let explanation: String

    public static func safety(_ decision: String) -> RecipeStatusPresentation {
        switch decision {
        case "eligible":
            RecipeStatusPresentation(title: "Eligible", systemImage: "checkmark.shield", tone: .positive,
                                     explanation: "No known conflict under the recorded household data.")
        case "blocked":
            RecipeStatusPresentation(title: "Blocked", systemImage: "xmark.shield.fill", tone: .blocked,
                                     explanation: "The server found a confirmed conflict or hard restriction.")
        case "review_required":
            RecipeStatusPresentation(title: "Review required", systemImage: "exclamationmark.shield.fill", tone: .warning,
                                     explanation: "The server needs more label or ingredient information.")
        default:
            RecipeStatusPresentation(title: "Unknown safety status", systemImage: "questionmark.shield", tone: .neutral,
                                     explanation: "The server returned an unrecognized safety result.")
        }
    }

    public static func availability(_ status: String) -> RecipeStatusPresentation {
        switch status {
        case "full":
            RecipeStatusPresentation(title: "Available", systemImage: "checkmark.circle.fill", tone: .positive,
                                     explanation: "Required quantities are covered by counted household stock.")
        case "partial":
            RecipeStatusPresentation(title: "Partial", systemImage: "circle.lefthalf.filled", tone: .warning,
                                     explanation: "Some required quantity is available.")
        case "missing":
            RecipeStatusPresentation(title: "Missing", systemImage: "minus.circle.fill", tone: .warning,
                                     explanation: "The server found a required quantity shortage.")
        case "unknown":
            RecipeStatusPresentation(title: "Unknown", systemImage: "questionmark.circle.fill", tone: .neutral,
                                     explanation: "The server could not compare this quantity reliably.")
        default:
            RecipeStatusPresentation(title: "Unknown", systemImage: "questionmark.circle.fill", tone: .neutral,
                                     explanation: "The server returned an unrecognized availability result.")
        }
    }
}

struct StatusPill: View {
    let presentation: RecipeStatusPresentation

    var body: some View {
        Label(presentation.title, systemImage: presentation.systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(presentation.tone.foreground)
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(presentation.tone.background)
            .clipShape(Capsule())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(presentation.title)
    }
}

enum QuantityText {
    static func string(_ quantity: ExactQuantity) -> String {
        NSDecimalNumber(decimal: quantity.value).stringValue
    }
}

enum ReasonText {
    static func display(_ value: String) -> String {
        value.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
