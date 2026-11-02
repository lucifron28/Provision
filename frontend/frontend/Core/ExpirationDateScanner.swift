import Foundation
import SwiftUI
@preconcurrency import Vision
import UIKit
import Combine
import AVFoundation

// MARK: - Expiration Date OCR Parser Service

public final class ExpirationDateOCRService: Sendable {
    public static let shared = ExpirationDateOCRService()

    public init() {}

    /// Month mapping dictionary for textual month names (English and Tagalog / Filipino)
    public static let monthMap: [String: Int] = [
        // English
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DEC": 12,
        // Tagalog / Filipino
        "ENE": 1, "PEB": 2, "ABR": 4, "HUN": 6, "HUL": 7, "AGO": 8,
        "SET": 9, "OKT": 10, "NOB": 11, "DIS": 12
    ]

    /// Determines whether a given year is a leap year
    public static func isLeapYear(_ year: Int) -> Bool {
        return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0)
    }

    /// Returns the maximum days in a given month and year (accounting for leap years)
    public static func daysInMonth(month: Int, year: Int) -> Int? {
        guard (1...12).contains(month) else { return nil }
        switch month {
        case 1, 3, 5, 7, 8, 10, 12:
            return 31
        case 4, 6, 9, 11:
            return 30
        case 2:
            return isLeapYear(year) ? 29 : 28
        default:
            return nil
        }
    }

    /// Validates whether a day, month, and year form a real calendar date
    public static func isValidDate(year: Int, month: Int, day: Int) -> Bool {
        guard (1...12).contains(month) else { return false }
        guard let maxDays = daysInMonth(month: month, year: year) else { return false }
        return (1...maxDays).contains(day)
    }

    private func makeDate(year: Int, month: Int, day: Int) -> Date? {
        var adjustedYear = year
        if adjustedYear < 100 {
            adjustedYear += 2000
        }
        guard Self.isValidDate(year: adjustedYear, month: month, day: day) else {
            return nil
        }
        var components = DateComponents()
        components.year = adjustedYear
        components.month = month
        components.day = day
        components.hour = 12
        return Calendar.current.date(from: components)
    }

    private static let monthTokens = "SEPT|SET|OKT|NOB|DIS|ENE|PEB|ABR|HUN|HUL|AGO|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"
    private static let prefixPattern = #"(?:(?:\b(?:EXP(?:IRY|IRATION)?(?:\s+DATE)?|BBD|BB|BEST\s+BEFORE|USE\s+BY|CONSUME\s+BEFORE|PETSA(?:\s+NG\s+PAGKAPASO)?)\b\s*[:.-]?\s*)|(?:\b(?:EXP|BBD|BB)))"#

    /// Extracts a date and ambiguity flag from a single line of text
    public func extractExpirationDate(from rawText: String) -> (date: Date, isAmbiguous: Bool)? {
        let text = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }

        // Pattern 1: Delimited DD MMM YYYY (e.g. 24 SEP 2026, 24-SEP-2026, 24.SEP.2026, 24 ENE 2026)
        let ddMmmPattern = #"\b(\d{1,2})[-/. \t]+("# + Self.monthTokens + #")[A-Z]*[-/. \t]+(\d{2,4})\b"#
        if let regex = try? NSRegularExpression(pattern: ddMmmPattern, options: .caseInsensitive),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let dayRange = Range(match.range(at: 1), in: text),
               let monthRange = Range(match.range(at: 2), in: text),
               let yearRange = Range(match.range(at: 3), in: text) {
                let day = Int(text[dayRange]) ?? 1
                let rawMonthStr = String(text[monthRange]).uppercased()
                let prefix4 = String(rawMonthStr.prefix(4))
                let prefix3 = String(rawMonthStr.prefix(3))
                let key = Self.monthMap[prefix4] != nil ? prefix4 : prefix3
                if let month = Self.monthMap[key],
                   let rawYear = Int(text[yearRange]),
                   let date = makeDate(year: rawYear, month: month, day: day) {
                    return (date, false)
                }
            }
        }

        // Pattern 2: Delimited MMM DD, YYYY (e.g. SEP 24 2026, OCT 15, 2026, ENE 24 2026)
        let mmmDdPattern = #"\b("# + Self.monthTokens + #")[A-Z]*[-/. \t]+(\d{1,2})[,-/. \t]+(\d{2,4})\b"#
        if let regex = try? NSRegularExpression(pattern: mmmDdPattern, options: .caseInsensitive),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let monthRange = Range(match.range(at: 1), in: text),
               let dayRange = Range(match.range(at: 2), in: text),
               let yearRange = Range(match.range(at: 3), in: text) {
                let rawMonthStr = String(text[monthRange]).uppercased()
                let prefix4 = String(rawMonthStr.prefix(4))
                let prefix3 = String(rawMonthStr.prefix(3))
                let key = Self.monthMap[prefix4] != nil ? prefix4 : prefix3
                let day = Int(text[dayRange]) ?? 1
                if let month = Self.monthMap[key],
                   let rawYear = Int(text[yearRange]),
                   let date = makeDate(year: rawYear, month: month, day: day) {
                    return (date, false)
                }
            }
        }

        // Pattern 3: Compact stamps without delimiters (e.g. 24SEP26, 15OCT2026, EXP24SEP26, BBD 15OCT26, 29PEB28)
        let compactPattern = #"(?:"# + Self.prefixPattern + #")?(\d{1,2})("# + Self.monthTokens + #")(\d{2}|\d{4})\b"#
        if let regex = try? NSRegularExpression(pattern: compactPattern, options: .caseInsensitive),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let dayRange = Range(match.range(at: 1), in: text),
               let monthRange = Range(match.range(at: 2), in: text),
               let yearRange = Range(match.range(at: 3), in: text) {
                let day = Int(text[dayRange]) ?? 1
                let rawMonthStr = String(text[monthRange]).uppercased()
                let prefix4 = String(rawMonthStr.prefix(4))
                let prefix3 = String(rawMonthStr.prefix(3))
                let key = Self.monthMap[prefix4] != nil ? prefix4 : prefix3
                if let month = Self.monthMap[key],
                   let rawYear = Int(text[yearRange]),
                   let date = makeDate(year: rawYear, month: month, day: day) {
                    return (date, false)
                }
            }
        }

        // Pattern 4: ISO 8601 (YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD)
        let isoPattern = #"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b"#
        if let regex = try? NSRegularExpression(pattern: isoPattern, options: .caseInsensitive),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let yRange = Range(match.range(at: 1), in: text),
               let mRange = Range(match.range(at: 2), in: text),
               let dRange = Range(match.range(at: 3), in: text) {
                let year = Int(text[yRange]) ?? 2026
                let month = Int(text[mRange]) ?? 1
                let day = Int(text[dRange]) ?? 1
                if let date = makeDate(year: year, month: month, day: day) {
                    return (date, false)
                }
            }
        }

        // Pattern 5: Numeric dates (DD.MM.YYYY, MM/DD/YYYY, etc.)
        let numericPattern = #"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b"#
        if let regex = try? NSRegularExpression(pattern: numericPattern, options: .caseInsensitive),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let p1Range = Range(match.range(at: 1), in: text),
               let p2Range = Range(match.range(at: 2), in: text),
               let yRange = Range(match.range(at: 3), in: text) {
                let p1 = Int(text[p1Range]) ?? 1
                let p2 = Int(text[p2Range]) ?? 1
                let rawYear = Int(text[yRange]) ?? 2026

                // Case A: Both numbers <= 12 -> Ambiguous between MM/DD and DD/MM
                if (1...12).contains(p1) && (1...12).contains(p2) {
                    if let date = makeDate(year: rawYear, month: p1, day: p2) {
                        return (date, true)
                    }
                }
                // Case B: First number > 12 -> Unambiguously DD.MM.YYYY
                else if p1 > 12 && (1...12).contains(p2) {
                    if let date = makeDate(year: rawYear, month: p2, day: p1) {
                        return (date, false)
                    }
                }
                // Case C: Second number > 12 -> Unambiguously MM/DD/YYYY
                else if (1...12).contains(p1) && p2 > 12 {
                    if let date = makeDate(year: rawYear, month: p1, day: p2) {
                        return (date, false)
                    }
                }
            }
        }

        return nil
    }

    /// Backwards-compatible extractDate returning solely Date?
    public func extractDate(from rawText: String) -> Date? {
        return extractExpirationDate(from: rawText)?.date
    }

    /// Parses an array of recognized OCR text strings into the most likely expiration date
    public func parseExpirationDate(from lines: [String]) -> (date: Date, rawString: String, isAmbiguous: Bool)? {
        for line in lines {
            if let result = extractExpirationDate(from: line) {
                return (result.date, line, result.isAmbiguous)
            }
        }

        if lines.count > 1 {
            for i in 0..<(lines.count - 1) {
                let combined = "\(lines[i]) \(lines[i + 1])"
                if let result = extractExpirationDate(from: combined) {
                    return (result.date, combined, result.isAmbiguous)
                }
            }
        }

        return nil
    }

    /// Recognizes text lines from an image using Vision OCR
    public func recognizeTextLines(from image: UIImage) async -> [String] {
        guard let cgImage = image.cgImage else { return [] }

        return await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { request, error in
                guard error == nil,
                      let observations = request.results as? [VNRecognizedTextObservation] else {
                    continuation.resume(returning: [])
                    return
                }

                let lines: [String] = observations.compactMap { observation in
                    observation.topCandidates(1).first?.string
                }
                continuation.resume(returning: lines)
            }

            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = false

            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try handler.perform([request])
                } catch {
                    continuation.resume(returning: [])
                }
            }
        }
    }

    /// Recognizes text from image and extracts expiration date
    public func scanExpirationDate(from image: UIImage) async -> (date: Date, rawString: String, isAmbiguous: Bool)? {
        let lines = await recognizeTextLines(from: image)
        return parseExpirationDate(from: lines)
    }
}

// MARK: - Package Stamp Image Picker (UIKit Bridge)

public struct PackageStampImagePicker: UIViewControllerRepresentable {
    public let sourceType: UIImagePickerController.SourceType
    public let onImageCaptured: @MainActor @Sendable (UIImage) -> Void
    public let onCancel: @MainActor @Sendable () -> Void

    public init(
        sourceType: UIImagePickerController.SourceType = .camera,
        onImageCaptured: @escaping @MainActor @Sendable (UIImage) -> Void,
        onCancel: @escaping @MainActor @Sendable () -> Void
    ) {
        self.sourceType = sourceType
        self.onImageCaptured = onImageCaptured
        self.onCancel = onCancel
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator(onImageCaptured: onImageCaptured, onCancel: onCancel)
    }

    public func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        if UIImagePickerController.isSourceTypeAvailable(sourceType) {
            picker.sourceType = sourceType
        } else {
            picker.sourceType = .photoLibrary
        }
        picker.delegate = context.coordinator
        return picker
    }

    public func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    public final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate, @unchecked Sendable {
        private let onImageCaptured: @MainActor @Sendable (UIImage) -> Void
        private let onCancel: @MainActor @Sendable () -> Void

        public init(
            onImageCaptured: @escaping @MainActor @Sendable (UIImage) -> Void,
            onCancel: @escaping @MainActor @Sendable () -> Void
        ) {
            self.onImageCaptured = onImageCaptured
            self.onCancel = onCancel
        }

        public func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey : Any]) {
            let capturedImage = (info[.editedImage] as? UIImage) ?? (info[.originalImage] as? UIImage)
            let onCaptured = self.onImageCaptured
            picker.dismiss(animated: true) {
                if let image = capturedImage {
                    Task { @MainActor in
                        onCaptured(image)
                    }
                }
            }
        }

        public func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            let onCancel = self.onCancel
            picker.dismiss(animated: true) {
                Task { @MainActor in
                    onCancel()
                }
            }
        }
    }
}

// MARK: - Expiration Date Source State

public enum ExpirationDateSource: Equatable, Sendable {
    case none
    case previouslySaved(Date)
    case ocrRecognized(Date, rawText: String, isAmbiguous: Bool)
    case manualSelected(Date)

    public var description: String {
        switch self {
        case .none:
            return "None (Unknown)"
        case .previouslySaved:
            return "Previously Saved on Package"
        case .ocrRecognized:
            return "OCR Proposed Stamp"
        case .manualSelected:
            return "Manually Selected"
        }
    }
}

// MARK: - Expiration Date Scanner Sheet View

public struct ExpirationDateScannerSheet: View {
    @Environment(\.dismiss) private var dismiss
    public let title: String
    public let initialDate: Date?
    public let onDateSelected: (Date?) -> Void

    @State private var selectedDate: Date
    @State private var hasExplicitDate: Bool
    @State private var dateSource: ExpirationDateSource
    @State private var parsedDate: Date? = nil
    @State private var detectedText: String? = nil
    @State private var isAmbiguous: Bool = false
    @State private var isAnalyzing: Bool = false
    @State private var capturedImage: UIImage? = nil

    @State private var showingImagePicker: Bool = false
    @State private var pickerSourceType: UIImagePickerController.SourceType = .camera
    @State private var permissionDenied: Bool = false
    @State private var manualInputText: String = ""

    public init(
        title: String = "Scan Expiration Date",
        initialDate: Date? = nil,
        onDateSelected: @escaping (Date?) -> Void
    ) {
        self.title = title
        self.initialDate = initialDate
        self.onDateSelected = onDateSelected
        let hasInitial = initialDate != nil
        _hasExplicitDate = State(initialValue: hasInitial)
        _dateSource = State(initialValue: hasInitial ? .previouslySaved(initialDate!) : .none)
        _selectedDate = State(initialValue: initialDate ?? Date())
        _parsedDate = State(initialValue: initialDate)
    }

    public init(
        title: String = "Scan Expiration Date",
        initialDate: Date? = nil,
        onDateSelected: @escaping (Date) -> Void
    ) {
        self.title = title
        self.initialDate = initialDate
        self.onDateSelected = { date in
            if let date {
                onDateSelected(date)
            }
        }
        let hasInitial = initialDate != nil
        _hasExplicitDate = State(initialValue: hasInitial)
        _dateSource = State(initialValue: hasInitial ? .previouslySaved(initialDate!) : .none)
        _selectedDate = State(initialValue: initialDate ?? Date())
        _parsedDate = State(initialValue: initialDate)
    }

    private var isCameraAvailable: Bool {
        UIImagePickerController.isSourceTypeAvailable(.camera)
    }

    public var body: some View {
        NavigationStack {
            Form {
                // Section 1: Camera OCR Capture Card
                Section("Package Camera OCR") {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .fill(ProvisionTheme.heroCard.opacity(0.15))
                                    .frame(width: 48, height: 48)
                                Image(systemName: "camera.viewfinder")
                                    .font(.system(size: 24))
                                    .foregroundStyle(ProvisionTheme.heroCard)
                            }

                            VStack(alignment: .leading, spacing: 2) {
                                Text("Optical Character Recognition")
                                    .font(.system(size: 15, weight: .bold))
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                                Text("Point camera at printed EXP or Best By stamp")
                                    .font(.system(size: 12))
                                    .foregroundStyle(ProvisionTheme.textSecondary)
                            }
                        }

                        if isAnalyzing {
                            HStack(spacing: 10) {
                                ProgressView()
                                Text("Analyzing package stamp with Vision OCR...")
                                    .font(.system(size: 13))
                                    .foregroundStyle(ProvisionTheme.textSecondary)
                            }
                            .padding(.vertical, 4)
                        }

                        HStack(spacing: 10) {
                            Button {
                                checkCameraPermissionAndOpen()
                            } label: {
                                HStack {
                                    Image(systemName: isCameraAvailable ? "camera.fill" : "photo.on.rectangle")
                                    Text(capturedImage == nil ? (isCameraAvailable ? "Capture Package Stamp" : "Choose Photo") : "Retake Photo")
                                        .font(.system(size: 14, weight: .semibold))
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 10)
                                .background(ProvisionTheme.provisionGreenLight)
                                .foregroundStyle(ProvisionTheme.provisionGreen)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                            }
                            .buttonStyle(.borderless)

                            if isCameraAvailable {
                                Button {
                                    pickerSourceType = .photoLibrary
                                    showingImagePicker = true
                                } label: {
                                    Image(systemName: "photo")
                                        .font(.system(size: 16))
                                        .padding(.vertical, 10)
                                        .padding(.horizontal, 14)
                                        .background(ProvisionTheme.surfaceSecondary)
                                        .foregroundStyle(ProvisionTheme.textPrimary)
                                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                                }
                                .buttonStyle(.borderless)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }

                // Section 2: Camera Permission Warning (if denied)
                if permissionDenied {
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 8) {
                                Image(systemName: "camera.badge.ellipsis")
                                    .font(.system(size: 20))
                                    .foregroundStyle(ProvisionTheme.amberWarning)
                                Text("Camera Access Denied")
                                    .font(.system(size: 14, weight: .bold))
                                    .foregroundStyle(ProvisionTheme.textPrimary)
                            }
                            Text("Camera permission is required to capture photos directly. You can pick an image from your photo library or enter the expiration date manually below.")
                                .font(.system(size: 12))
                                .foregroundStyle(ProvisionTheme.textSecondary)

                            HStack(spacing: 14) {
                                Button("Choose from Photos") {
                                    pickerSourceType = .photoLibrary
                                    showingImagePicker = true
                                }
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.provisionGreen)

                                if let settingsUrl = URL(string: UIApplication.openSettingsURLString) {
                                    Button("Open Settings") {
                                        UIApplication.shared.open(settingsUrl)
                                    }
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundStyle(ProvisionTheme.heroCard)
                                }
                            }
                            .padding(.top, 2)
                        }
                        .padding(.vertical, 4)
                    }
                }

                // Section 3: OCR Results & Proposed Date
                if detectedText != nil || parsedDate != nil {
                    Section("OCR Recognition Result") {
                        VStack(alignment: .leading, spacing: 10) {
                            if let text = detectedText {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Detected Stamp Text:")
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                    Text(text)
                                        .font(.system(size: 13, weight: .medium, design: .monospaced))
                                        .foregroundStyle(ProvisionTheme.textPrimary)
                                        .padding(8)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .background(ProvisionTheme.surfaceSecondary)
                                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                                }
                            }

                            if let proposed = parsedDate {
                                HStack {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(ProvisionTheme.provisionGreen)
                                    Text("Proposed Date:")
                                        .font(.system(size: 13, weight: .semibold))
                                        .foregroundStyle(ProvisionTheme.textPrimary)
                                    Spacer()
                                    Text(proposed, format: .dateTime.month().day().year())
                                        .font(.system(size: 14, weight: .bold, design: .monospaced))
                                        .foregroundStyle(ProvisionTheme.provisionGreen)
                                }
                                .padding(10)
                                .background(ProvisionTheme.provisionGreenLight)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                            } else {
                                HStack(spacing: 8) {
                                    Image(systemName: "exclamationmark.circle")
                                        .foregroundStyle(ProvisionTheme.amberWarning)
                                    Text(hasExplicitDate ? "No date recognized in photo. Your current selection is preserved below." : "No recognized date stamp. Please set date manually below.")
                                        .font(.system(size: 12, weight: .medium))
                                        .foregroundStyle(ProvisionTheme.textSecondary)
                                }
                                .padding(8)
                                .background(ProvisionTheme.amberLight)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                            }

                            if isAmbiguous {
                                HStack(alignment: .top, spacing: 8) {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .foregroundStyle(ProvisionTheme.amberWarning)
                                        .font(.system(size: 14))
                                    Text("Format is ambiguous (numeric MM/DD vs DD/MM). Please confirm the proposed date below.")
                                        .font(.system(size: 12, weight: .medium))
                                        .foregroundStyle(ProvisionTheme.amberWarning)
                                }
                                .padding(8)
                                .background(ProvisionTheme.amberLight.opacity(0.6))
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }

                // Section 4: Date Confirmation / Fine-tuning
                Section("Expiration Date Confirmation") {
                    if hasExplicitDate {
                        DatePicker(
                            "Expiration Date",
                            selection: $selectedDate,
                            displayedComponents: .date
                        )
                        .font(.system(size: 15, weight: .medium))
                        .onChange(of: selectedDate) { _, newDate in
                            dateSource = .manualSelected(newDate)
                            hasExplicitDate = true
                        }

                        HStack {
                            Text("Source: \(dateSource.description)")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                            Spacer()
                            Button("Clear Date") {
                                hasExplicitDate = false
                                dateSource = .none
                                parsedDate = nil
                                detectedText = nil
                                isAmbiguous = false
                            }
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.redAlert)
                        }
                    } else {
                        HStack {
                            Image(systemName: "questionmark.circle")
                                .foregroundStyle(ProvisionTheme.textTertiary)
                            Text("No date selected (Unknown)")
                                .font(.system(size: 14))
                                .foregroundStyle(ProvisionTheme.textSecondary)
                            Spacer()
                            Button("+ Set Date") {
                                hasExplicitDate = true
                                selectedDate = Date()
                            }
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(ProvisionTheme.provisionGreen)
                        }
                        .padding(.vertical, 4)
                    }
                }

                // Section 5: Manual Stamp Text Input
                Section("Enter Stamp Text Manually") {
                    HStack {
                        TextField("e.g. 24SEP26 or EXP 24/09/2026", text: $manualInputText)
                            .textInputAutocapitalization(.characters)
                            .disableAutocorrection(true)

                        Button("Parse") {
                            parseManualText()
                        }
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(ProvisionTheme.heroCard)
                        .disabled(manualInputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }

                // Section 6: Action Buttons
                Section {
                    Button(role: .destructive) {
                        onDateSelected(nil)
                        dismiss()
                    } label: {
                        HStack {
                            Spacer()
                            Image(systemName: "xmark.circle")
                            Text("Leave Unknown (No Expiration)")
                                .font(.system(size: 14, weight: .medium))
                            Spacer()
                        }
                    }
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(hasExplicitDate ? "Apply Date" : "Confirm Unknown") {
                        onDateSelected(hasExplicitDate ? selectedDate : nil)
                        dismiss()
                    }
                    .font(.system(size: 15, weight: .bold))
                }
            }
            .sheet(isPresented: $showingImagePicker) {
                PackageStampImagePicker(sourceType: pickerSourceType) { image in
                    handleCapturedImage(image)
                } onCancel: {
                }
            }
        }
    }

    private func checkCameraPermissionAndOpen() {
        guard isCameraAvailable else {
            pickerSourceType = .photoLibrary
            showingImagePicker = true
            return
        }

        let status = AVCaptureDevice.authorizationStatus(for: .video)
        switch status {
        case .authorized:
            pickerSourceType = .camera
            showingImagePicker = true
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { granted in
                Task { @MainActor in
                    if granted {
                        pickerSourceType = .camera
                        showingImagePicker = true
                    } else {
                        permissionDenied = true
                    }
                }
            }
        case .denied, .restricted:
            permissionDenied = true
        @unknown default:
            permissionDenied = true
        }
    }

    private func handleCapturedImage(_ image: UIImage) {
        capturedImage = image
        isAnalyzing = true
        detectedText = nil

        Task {
            let lines = await ExpirationDateOCRService.shared.recognizeTextLines(from: image)
            let parsed = ExpirationDateOCRService.shared.parseExpirationDate(from: lines)
            await MainActor.run {
                self.isAnalyzing = false
                if let parsed = parsed {
                    self.parsedDate = parsed.date
                    self.selectedDate = parsed.date
                    self.detectedText = parsed.rawString
                    self.isAmbiguous = parsed.isAmbiguous
                    self.hasExplicitDate = true
                    self.dateSource = .ocrRecognized(parsed.date, rawText: parsed.rawString, isAmbiguous: parsed.isAmbiguous)
                } else {
                    self.parsedDate = nil
                    self.isAmbiguous = false
                    if !lines.isEmpty {
                        self.detectedText = "OCR found text but no valid date stamp:\n" + lines.prefix(3).joined(separator: "\n")
                    } else {
                        self.detectedText = "No readable text detected in photo"
                    }
                    // Priority 5: Preserve existing date if present; do not misrepresent as newly recognized
                    switch self.dateSource {
                    case .previouslySaved(let saved):
                        self.selectedDate = saved
                        self.hasExplicitDate = true
                    case .manualSelected(let manual):
                        self.selectedDate = manual
                        self.hasExplicitDate = true
                    default:
                        if let initial = self.initialDate {
                            self.selectedDate = initial
                            self.hasExplicitDate = true
                            self.dateSource = .previouslySaved(initial)
                        } else {
                            self.hasExplicitDate = false
                            self.dateSource = .none
                        }
                    }
                }
            }
        }
    }

    private func parseManualText() {
        let trimmed = manualInputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        if let result = ExpirationDateOCRService.shared.extractExpirationDate(from: trimmed) {
            selectedDate = result.date
            parsedDate = result.date
            detectedText = trimmed
            isAmbiguous = result.isAmbiguous
            hasExplicitDate = true
            dateSource = .manualSelected(result.date)
        } else {
            detectedText = "Could not parse date stamp from '\(trimmed)'"
            parsedDate = nil
            isAmbiguous = false
        }
    }
}
