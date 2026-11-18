import Foundation
import SwiftUI
@preconcurrency import Vision
@preconcurrency import VisionKit
import ImageIO
import UIKit
import Combine

// MARK: - Match Confidence

public enum MatchConfidence: String, Sendable, Codable, Hashable {
    case exact = "Exact"
    case high = "High"
    case uncertain = "Uncertain"
    case none = "None"
}

// MARK: - Parsed Receipt Line Item

public struct ReceiptLineItem: Identifiable, Hashable, Sendable {
    public let id: UUID
    public var rawText: String
    public var parsedName: String
    public var unitPrice: Double?
    public var quantity: Double
    public var matchedProduct: Product?
    public var confidence: MatchConfidence

    public var lineTotal: Double? {
        guard let price = unitPrice else { return nil }
        return (quantity * price * 100).rounded() / 100
    }

    public var parsedPrice: Double? {
        get { unitPrice }
        set { unitPrice = newValue }
    }

    public init(
        id: UUID = UUID(),
        rawText: String,
        parsedName: String,
        unitPrice: Double? = nil,
        quantity: Double = 1.0,
        matchedProduct: Product? = nil,
        confidence: MatchConfidence = .none
    ) {
        self.id = id
        self.rawText = rawText
        self.parsedName = parsedName
        self.unitPrice = unitPrice
        self.quantity = quantity
        self.matchedProduct = matchedProduct
        self.confidence = confidence
    }
    
    public init(
        rawText: String,
        parsedName: String,
        parsedPrice: Double?,
        quantity: Double = 1.0,
        matchedProduct: Product? = nil
    ) {
        self.id = UUID()
        self.rawText = rawText
        self.parsedName = parsedName
        self.unitPrice = parsedPrice
        self.quantity = quantity
        self.matchedProduct = matchedProduct
        self.confidence = matchedProduct != nil ? .high : .none
    }
}

// MARK: - Vision OCR Text Recognition Service

public final class ReceiptOCRService: Sendable {
    public static let shared = ReceiptOCRService()
    
    public init() {}
    
    /// Performs text recognition on a UIImage using Vision framework
    public func recognizeText(from image: UIImage) async -> [String] {
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
            request.usesLanguageCorrection = true
            let preferredLanguages = ["en-US", "fil", "tl"]
            let supportedLanguages = (try? request.supportedRecognitionLanguages()) ?? []
            let selectedLanguages = preferredLanguages.filter(supportedLanguages.contains)
            if !selectedLanguages.isEmpty {
                request.recognitionLanguages = selectedLanguages
            } else if let fallbackLanguage = supportedLanguages.first {
                request.recognitionLanguages = [fallbackLanguage]
            }
            
            let handler = VNImageRequestHandler(
                cgImage: cgImage,
                orientation: Self.cgImageOrientation(for: image.imageOrientation),
                options: [:]
            )
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try handler.perform([request])
                } catch {
                    continuation.resume(returning: [])
                }
            }
        }
    }
    
    /// Parses extracted receipt lines into line items with candidate prices
    private static let headerFooterKeywords = [
        "TOTAL", "CASH", "CHANGE", "VAT", "SUBTOTAL", "RECEIPT",
        "THANK YOU", "INVOICE", "TIN#", "OR#", "POS#", "STORE",
        "SUPERMARKET", "MERCHANDISE", "ITEMS SOLD", "CHANGE DUE", "PAYMENT",
        "APPROVAL", "AUTHORIZATION", "TRACE NO", "REFERENCE NO", "TERMINAL",
        "BALANCE DUE", "AMOUNT PAID", "CARD NO", "CASHIER", "CUSTOMER"
    ]

    private static let dateLineRegex = try? NSRegularExpression(
        pattern: #"^\s*(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)?\s*$"#,
        options: .caseInsensitive
    )
    private static let paymentMetadataRegex = try? NSRegularExpression(
        pattern: #"^\s*(?:DATE|TIME|TENDER|CARD|CREDIT|DEBIT|PAYMENT|APPROVAL|AUTH(?:ORIZATION)?|TRACE|REFERENCE|TERMINAL|ACCOUNT|CASHIER|CUSTOMER|BALANCE|AID|MID|TID|TRANS(?:ACTION)?(?:\s+NO\.?)?)\b"#,
        options: .caseInsensitive
    )
    private static let standaloneAmountRegex = try? NSRegularExpression(
        pattern: #"^\s*(?:[P₱]\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*$"#,
        options: .caseInsensitive
    )

    private static func cgImageOrientation(for orientation: UIImage.Orientation) -> CGImagePropertyOrientation {
        switch orientation {
        case .up: .up
        case .down: .down
        case .left: .left
        case .right: .right
        case .upMirrored: .upMirrored
        case .downMirrored: .downMirrored
        case .leftMirrored: .leftMirrored
        case .rightMirrored: .rightMirrored
        @unknown default: .up
        }
    }

    private static let multiplierRegex = try? NSRegularExpression(
        pattern: #"(?:^|\s+)(\d+(?:\.\d+)?)\s*(?:@|[xX]|\*|(?:PCS?|PC)\s*@)\s*[P₱\s]*(\d+\.\d{2})\s*(?:[VBTvbt])?\s*$"#,
        options: .caseInsensitive
    )

    private static let trailingPriceRegex = try? NSRegularExpression(
        pattern: #"[P₱\s]*(\d+\.\d{2})\s*(?:[VBTvbt])?\s*$"#,
        options: .caseInsensitive
    )

    /// Parses a single receipt line into a line item with quantity, unit price, line total, and confidence
    public func parseLine(_ line: String, catalog: [Product]) -> ReceiptLineItem? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 3 else { return nil }

        let upper = trimmed.uppercased()
        if Self.headerFooterKeywords.contains(where: { upper.contains($0) }) {
            return nil
        }
        let fullRange = NSRange(location: 0, length: trimmed.utf16.count)
        if [Self.dateLineRegex, Self.paymentMetadataRegex, Self.standaloneAmountRegex]
            .compactMap({ $0 })
            .contains(where: { $0.firstMatch(in: trimmed, options: [], range: fullRange) != nil }) {
            return nil
        }

        var extractedQty: Double = 1.0
        var extractedPrice: Double? = nil
        var cleanedName = trimmed

        if let regex = Self.multiplierRegex,
           let match = regex.firstMatch(in: trimmed, options: [], range: fullRange),
           let qtyRange = Range(match.range(at: 1), in: trimmed),
           let priceRange = Range(match.range(at: 2), in: trimmed) {
            extractedQty = Double(trimmed[qtyRange]) ?? 1.0
            extractedPrice = Double(trimmed[priceRange])
            if let matchRange = Range(match.range(at: 0), in: trimmed) {
                cleanedName = trimmed.replacingCharacters(in: matchRange, with: "").trimmingCharacters(in: .whitespaces)
            }
        } else if let regex = Self.trailingPriceRegex,
                  let match = regex.firstMatch(in: trimmed, options: [], range: fullRange),
                  let priceRange = Range(match.range(at: 1), in: trimmed) {
            extractedPrice = Double(trimmed[priceRange])
            if let matchRange = Range(match.range(at: 0), in: trimmed) {
                cleanedName = trimmed.replacingCharacters(in: matchRange, with: "").trimmingCharacters(in: .whitespaces)
            }
        }

        cleanedName = cleanedName.trimmingCharacters(in: CharacterSet(charactersIn: " -_@*"))
        guard !cleanedName.isEmpty else { return nil }

        let (matched, confidence) = findBestCatalogMatch(name: cleanedName, catalog: catalog)

        return ReceiptLineItem(
            rawText: line,
            parsedName: matched?.name ?? cleanedName,
            unitPrice: extractedPrice,
            quantity: extractedQty,
            matchedProduct: matched,
            confidence: confidence
        )
    }

    /// Parses extracted receipt lines into line items with candidate prices
    public func parseReceiptLines(_ lines: [String], catalog: [Product]) -> [ReceiptLineItem] {
        var items: [ReceiptLineItem] = []
        for line in lines {
            if let item = parseLine(line, catalog: catalog) {
                items.append(item)
            }
        }
        return items
    }

    public func findBestCatalogMatch(name: String, catalog: [Product]) -> (Product?, MatchConfidence) {
        let needle = name.lowercased().trimmingCharacters(in: .whitespaces)
        let needleTokens = needle.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.count >= 3 }
        let needleTokenSet = Set(needleTokens)

        // 1. Exact match by barcode or case-insensitive exact name
        for product in catalog {
            if let barcode = product.barcode, barcode.lowercased() == needle {
                return (product, .exact)
            }
            if product.name.lowercased() == needle {
                return (product, .exact)
            }
        }

        // 2. High confidence match
        for product in catalog {
            let pName = product.name.lowercased()
            let pTokens = pName.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.count >= 3 }
            let pTokenSet = Set(pTokens)
            let brandTokens = Set(
                (product.brand ?? "")
                    .lowercased()
                    .components(separatedBy: CharacterSet.alphanumerics.inverted)
                    .filter { $0.count >= 3 }
            )
            let productIdentityTokens = pTokenSet.subtracting(brandTokens)
            let needleIdentityTokens = needleTokenSet.subtracting(brandTokens)

            // Match the brand and at least one product-specific token. Brand
            // tokens alone must never select a sibling product from the same brand.
            if !brandTokens.isEmpty,
               brandTokens.isSubset(of: needleTokenSet),
               !needleIdentityTokens.isDisjoint(with: productIdentityTokens) {
                return (product, .high)
            }

            // Overlap of >= 2 tokens (length > 3)
            let significantNeedle = needleIdentityTokens.filter { $0.count > 3 }
            let significantProd = productIdentityTokens.filter { $0.count > 3 }
            let overlap = significantNeedle.intersection(significantProd)
            if overlap.count >= 2 {
                return (product, .high)
            }
        }

        // 3. Uncertain confidence: single token overlap
        for product in catalog {
            let pTokens = product.name.lowercased()
                .components(separatedBy: CharacterSet.alphanumerics.inverted)
                .filter { $0.count >= 3 }
            let pTokenSet = Set(pTokens)
            let brandTokens = Set(
                (product.brand ?? "")
                    .lowercased()
                    .components(separatedBy: CharacterSet.alphanumerics.inverted)
                    .filter { $0.count >= 3 }
            )
            let overlap = needleTokenSet.subtracting(brandTokens)
                .intersection(pTokenSet.subtracting(brandTokens))
            if !overlap.isEmpty {
                return (product, .uncertain)
            }
        }

        return (nil, .none)
    }
}

// MARK: - VisionKit Document Camera Representable

#if canImport(VisionKit)
public struct DocumentCameraScannerView: UIViewControllerRepresentable {
    public let onScannedImages: @MainActor @Sendable ([UIImage]) -> Void
    public let onCancel: @MainActor @Sendable () -> Void
    
    public init(
        onScannedImages: @escaping @MainActor @Sendable ([UIImage]) -> Void,
        onCancel: @escaping @MainActor @Sendable () -> Void
    ) {
        self.onScannedImages = onScannedImages
        self.onCancel = onCancel
    }
    
    public func makeCoordinator() -> Coordinator {
        Coordinator(onScannedImages: onScannedImages, onCancel: onCancel)
    }
    
    public func makeUIViewController(context: Context) -> UIViewController {
        if VNDocumentCameraViewController.isSupported {
            let controller = VNDocumentCameraViewController()
            controller.delegate = context.coordinator
            return controller
        } else {
            // Simulator or unsupported fallback
            let fallbackVC = UIViewController()
            fallbackVC.view.backgroundColor = .systemBackground
            return fallbackVC
        }
    }
    
    public func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
    
    public final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate, @unchecked Sendable {
        private let onScannedImages: @MainActor @Sendable ([UIImage]) -> Void
        private let onCancel: @MainActor @Sendable () -> Void
        
        public init(
            onScannedImages: @escaping @MainActor @Sendable ([UIImage]) -> Void,
            onCancel: @escaping @MainActor @Sendable () -> Void
        ) {
            self.onScannedImages = onScannedImages
            self.onCancel = onCancel
        }
        
        public func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            var images: [UIImage] = []
            for i in 0..<scan.pageCount {
                images.append(scan.imageOfPage(at: i))
            }
            let onScanned = self.onScannedImages
            controller.dismiss(animated: true) {
                Task { @MainActor in
                    onScanned(images)
                }
            }
        }
        
        public func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) {
            let onCancel = self.onCancel
            controller.dismiss(animated: true) {
                Task { @MainActor in
                    onCancel()
                }
            }
        }
        
        public func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) {
            let onCancel = self.onCancel
            controller.dismiss(animated: true) {
                Task { @MainActor in
                    onCancel()
                }
            }
        }
    }
}
#endif
