import Foundation
import SwiftUI
@preconcurrency import Vision
import UIKit
import Combine

// MARK: - Expiration Date OCR Parser Service

public final class ExpirationDateOCRService: Sendable {
    public static let shared = ExpirationDateOCRService()
    
    public init() {}
    
    /// Month mapping dictionary for textual month names
    private static let monthMap: [String: Int] = [
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
    ]
    
    /// Parses an array of recognized OCR text strings into the most likely expiration date
    public func parseExpirationDate(from lines: [String]) -> (date: Date, rawString: String)? {
        for line in lines {
            let upper = line.uppercased().trimmingCharacters(in: .whitespacesAndNewlines)
            if let result = extractDate(from: upper) {
                return (result, line)
            }
        }
        return nil
    }
    
    /// Extracts a date from a single line of text
    public func extractDate(from rawText: String) -> Date? {
        let text = rawText.uppercased()
        
        // Pattern 1: DD MMM YYYY or DD-MMM-YYYY (e.g. 24 SEP 2026, 15-OCT-2026, 05 NOV 26)
        let ddMmmYyyyPattern = #"\b(\d{1,2})[-/\s]+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[-/\s]+(\d{2,4})\b"#
        if let regex = try? NSRegularExpression(pattern: ddMmmYyyyPattern),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let dayRange = Range(match.range(at: 1), in: text),
               let monthRange = Range(match.range(at: 2), in: text),
               let yearRange = Range(match.range(at: 3), in: text) {
                let day = Int(text[dayRange]) ?? 1
                let monthStr = String(text[monthRange].prefix(3))
                let month = Self.monthMap[monthStr] ?? 1
                var year = Int(text[yearRange]) ?? 2026
                if year < 100 { year += 2000 }
                return makeDate(year: year, month: month, day: day)
            }
        }
        
        // Pattern 2: MMM DD, YYYY or MMM DD YYYY (e.g. SEP 24 2026, OCT 15, 2026)
        let mmmDdYyyyPattern = #"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[-/\s]+(\d{1,2})[,-\s]+(\d{2,4})\b"#
        if let regex = try? NSRegularExpression(pattern: mmmDdYyyyPattern),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let monthRange = Range(match.range(at: 1), in: text),
               let dayRange = Range(match.range(at: 2), in: text),
               let yearRange = Range(match.range(at: 3), in: text) {
                let monthStr = String(text[monthRange].prefix(3))
                let month = Self.monthMap[monthStr] ?? 1
                let day = Int(text[dayRange]) ?? 1
                var year = Int(text[yearRange]) ?? 2026
                if year < 100 { year += 2000 }
                return makeDate(year: year, month: month, day: day)
            }
        }
        
        // Pattern 3: ISO YYYY-MM-DD or YYYY/MM/DD (e.g. 2026-10-15)
        let isoPattern = #"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b"#
        if let regex = try? NSRegularExpression(pattern: isoPattern),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let yRange = Range(match.range(at: 1), in: text),
               let mRange = Range(match.range(at: 2), in: text),
               let dRange = Range(match.range(at: 3), in: text) {
                let year = Int(text[yRange]) ?? 2026
                let month = Int(text[mRange]) ?? 1
                let day = Int(text[dRange]) ?? 1
                return makeDate(year: year, month: month, day: day)
            }
        }
        
        // Pattern 4: MM/DD/YYYY or MM/DD/YY (e.g. 10/15/2026, 05/20/26)
        let numericPattern = #"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b"#
        if let regex = try? NSRegularExpression(pattern: numericPattern),
           let match = regex.firstMatch(in: text, options: [], range: NSRange(location: 0, length: text.utf16.count)) {
            if let mRange = Range(match.range(at: 1), in: text),
               let dRange = Range(match.range(at: 2), in: text),
               let yRange = Range(match.range(at: 3), in: text) {
                let month = Int(text[mRange]) ?? 1
                let day = Int(text[dRange]) ?? 1
                var year = Int(text[yRange]) ?? 2026
                if year < 100 { year += 2000 }
                if month >= 1 && month <= 12 && day >= 1 && day <= 31 {
                    return makeDate(year: year, month: month, day: day)
                }
            }
        }
        
        return nil
    }
    
    /// Recognizes text from image and extracts expiration date
    public func scanExpirationDate(from image: UIImage) async -> (date: Date, rawString: String)? {
        guard let cgImage = image.cgImage else { return nil }
        
        return await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { request, error in
                guard error == nil,
                      let observations = request.results as? [VNRecognizedTextObservation] else {
                    continuation.resume(returning: nil)
                    return
                }
                
                let lines: [String] = observations.compactMap { observation in
                    observation.topCandidates(1).first?.string
                }
                let parsed = self.parseExpirationDate(from: lines)
                continuation.resume(returning: parsed)
            }
            
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = false
            
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try handler.perform([request])
                } catch {
                    continuation.resume(returning: nil)
                }
            }
        }
    }
    
    private func makeDate(year: Int, month: Int, day: Int) -> Date? {
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        components.hour = 12
        return Calendar.current.date(from: components)
    }
}

// MARK: - Expiration Date Scanner Sheet View

public struct ExpirationDateScannerSheet: View {
    @Environment(\.dismiss) private var dismiss
    public let title: String
    public let onDateSelected: (Date) -> Void
    
    @State private var sampleInputText: String = "EXP: 24 SEP 2026"
    @State private var parsedDate: Date? = nil
    @State private var detectedText: String? = nil
    @State private var isAnalyzing: Bool = false
    
    public init(
        title: String = "Scan Expiration Date",
        onDateSelected: @escaping (Date) -> Void
    ) {
        self.title = title
        self.onDateSelected = onDateSelected
    }
    
    public var body: some View {
        NavigationStack {
            Form {
                Section("Package Camera OCR") {
                    VStack(alignment: .leading, spacing: 12) {
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
                        
                        if let date = parsedDate {
                            HStack {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(ProvisionTheme.provisionGreen)
                                Text("Recognized:")
                                    .font(.system(size: 13, weight: .semibold))
                                Text(date, format: .dateTime.month().day().year())
                                    .font(.system(size: 15, weight: .bold, design: .monospaced))
                                    .foregroundStyle(ProvisionTheme.provisionGreen)
                            }
                            .padding(10)
                            .background(ProvisionTheme.provisionGreenLight)
                            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        }
                    }
                    .padding(.vertical, 4)
                }
                
                Section("Sample Package Presets (Testing & Simulator)") {
                    presetButton("EXP: 24 SEP 2026 (Century Tuna)") {
                        applyPreset("24 SEP 2026")
                    }
                    presetButton("BEST BEFORE 15 OCT 2026 (Magnolia Milk)") {
                        applyPreset("15 OCT 2026")
                    }
                    presetButton("EXP: 2026-12-31 (Datu Puti Vinegar)") {
                        applyPreset("2026-12-31")
                    }
                    presetButton("USE BY: 05/18/2027 (Purefoods Corned Beef)") {
                        applyPreset("05/18/2027")
                    }
                    presetButton("EXP: 2 DAYS FROM NOW (Urgent Bread)") {
                        let d = Calendar.current.date(byAdding: .day, value: 2, to: Date()) ?? Date()
                        parsedDate = d
                        detectedText = "2 DAYS FROM NOW"
                    }
                }
                
                Section("Custom Package Stamp Text") {
                    TextField("e.g. EXP 28 NOV 2026", text: $sampleInputText)
                    
                    Button("Parse Stamp") {
                        if let extracted = ExpirationDateOCRService.shared.extractDate(from: sampleInputText) {
                            parsedDate = extracted
                            detectedText = sampleInputText
                        }
                    }
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(ProvisionTheme.heroCard)
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Apply Date") {
                        if let date = parsedDate {
                            onDateSelected(date)
                            dismiss()
                        }
                    }
                    .font(.system(size: 14, weight: .bold))
                    .disabled(parsedDate == nil)
                }
            }
            .onAppear {
                if let extracted = ExpirationDateOCRService.shared.extractDate(from: sampleInputText) {
                    parsedDate = extracted
                }
            }
        }
    }
    
    private func presetButton(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Image(systemName: "text.viewfinder")
                    .font(.system(size: 12))
                    .foregroundStyle(ProvisionTheme.heroCard)
                Text(label)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(ProvisionTheme.textPrimary)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 10))
                    .foregroundStyle(ProvisionTheme.textTertiary)
            }
        }
    }
    
    private func applyPreset(_ text: String) {
        sampleInputText = text
        if let extracted = ExpirationDateOCRService.shared.extractDate(from: text) {
            parsedDate = extracted
            detectedText = text
        }
    }
}
