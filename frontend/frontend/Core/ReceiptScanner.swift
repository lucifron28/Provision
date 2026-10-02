import Foundation
import SwiftUI
@preconcurrency import Vision
@preconcurrency import VisionKit
import UIKit
import Combine

// MARK: - Parsed Receipt Line Item

public struct ReceiptLineItem: Identifiable, Hashable, Sendable {
    public let id = UUID()
    public var rawText: String
    public var parsedName: String
    public var parsedPrice: Double?
    public var quantity: Double
    public var matchedProduct: Product?
    
    public init(
        rawText: String,
        parsedName: String,
        parsedPrice: Double? = nil,
        quantity: Double = 1.0,
        matchedProduct: Product? = nil
    ) {
        self.rawText = rawText
        self.parsedName = parsedName
        self.parsedPrice = parsedPrice
        self.quantity = quantity
        self.matchedProduct = matchedProduct
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
            request.recognitionLanguages = ["en-US", "fil"]
            
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
    
    /// Parses extracted receipt lines into line items with candidate prices
    public func parseReceiptLines(_ lines: [String], catalog: [Product]) -> [ReceiptLineItem] {
        var items: [ReceiptLineItem] = []
        
        // Regex to match typical supermarket price trailing patterns: e.g. "45.50", "P120.00", "₱82.00", "99.00"
        let priceRegex = try? NSRegularExpression(pattern: #"(?:[P₱\s]*)(\d+(?:\.\d{2}))\s*$"#, options: .caseInsensitive)
        
        for rawLine in lines {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard line.count >= 3 else { continue }
            
            // Skip typical receipt header/footer lines
            let upper = line.uppercased()
            if upper.contains("TOTAL") || upper.contains("CASH") || upper.contains("CHANGE") ||
               upper.contains("VAT") || upper.contains("SUBTOTAL") || upper.contains("RECEIPT") ||
               upper.contains("THANK YOU") || upper.contains("INVOICE") || upper.contains("TIN#") {
                continue
            }
            
            var extractedPrice: Double? = nil
            var cleanedName = line
            
            if let regex = priceRegex {
                let range = NSRange(location: 0, length: line.utf16.count)
                if let match = regex.firstMatch(in: line, options: [], range: range),
                   let priceRange = Range(match.range(at: 1), in: line) {
                    let priceString = String(line[priceRange])
                    extractedPrice = Double(priceString)
                    
                    if let fullMatchRange = Range(match.range(at: 0), in: line) {
                        cleanedName = line.replacingCharacters(in: fullMatchRange, with: "").trimmingCharacters(in: .whitespaces)
                    }
                }
            }
            
            guard !cleanedName.isEmpty else { continue }
            
            // Fuzzy match cleaned name against local catalog
            let matched = findBestCatalogMatch(name: cleanedName, catalog: catalog)
            
            let item = ReceiptLineItem(
                rawText: rawLine,
                parsedName: matched?.name ?? cleanedName,
                parsedPrice: extractedPrice ?? matched?.package_size,
                quantity: 1.0,
                matchedProduct: matched
            )
            items.append(item)
        }
        
        return items
    }
    
    private func findBestCatalogMatch(name: String, catalog: [Product]) -> Product? {
        let needle = name.lowercased()
        
        // 1. Direct contains check
        for product in catalog {
            let pName = product.name.lowercased()
            if needle.contains(pName) || pName.contains(needle) {
                return product
            }
            if let brand = product.brand?.lowercased(), !brand.isEmpty, needle.contains(brand) {
                let tokens = needle.components(separatedBy: " ").filter { $0.count > 2 }
                if tokens.contains(where: { pName.contains($0) }) {
                    return product
                }
            }
        }
        
        // 2. Token overlap check
        let needleTokens = Set(needle.components(separatedBy: .alphanumerics.inverted).filter { $0.count >= 4 })
        for product in catalog {
            let prodTokens = Set(product.name.lowercased().components(separatedBy: .alphanumerics.inverted).filter { $0.count >= 4 })
            if !needleTokens.isDisjoint(with: prodTokens) {
                return product
            }
        }
        
        return nil
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
