import Foundation
import SwiftUI
import Combine

public struct ScannedIntakeItem: Identifiable, Hashable {
    public let id = UUID()
    public var name: String
    public var brand: String?
    public var barcode: String
    public var quantity: Double
    public var unit: String
    public var expirationDate: Date
    public var status: IntakeStatus
    
    public enum IntakeStatus: String {
        case autoLogged = "Auto-logged"
        case recognized = "Recognized"
        case needsReview = "Needs Review"
    }
}

@MainActor
public class ScanViewModel: ObservableObject {
    @Published public var storeName: String = "Trader Joe's"
    @Published public var scannedItems: [ScannedIntakeItem] = []
    @Published public var isScanning: Bool = true
    @Published public var isCommitting: Bool = false
    @Published public var toastMessage: String? = nil
    @Published public var errorMessage: String? = nil
    @Published public var lastScannedBarcode: String = ""
    
    private let client: APIClient
    
    public init(client: APIClient = .shared) {
        self.client = client
        setupSampleIntake()
    }
    
    private func setupSampleIntake() {
        let calendar = Calendar.current
        self.scannedItems = [
            ScannedIntakeItem(
                name: "Organic Whole Milk",
                brand: "Trader Joe's",
                barcode: "00123456",
                quantity: 1,
                unit: "1L",
                expirationDate: calendar.date(byAdding: .day, value: 5, to: Date()) ?? Date(),
                status: .autoLogged
            ),
            ScannedIntakeItem(
                name: "Greek Yogurt Tub",
                brand: "Fage",
                barcode: "00789012",
                quantity: 2,
                unit: "pack",
                expirationDate: calendar.date(byAdding: .day, value: 12, to: Date()) ?? Date(),
                status: .autoLogged
            ),
            ScannedIntakeItem(
                name: "Century Tuna Flakes",
                brand: "Century",
                barcode: "4800016644810",
                quantity: 4,
                unit: "cans",
                expirationDate: calendar.date(byAdding: .year, value: 2, to: Date()) ?? Date(),
                status: .recognized
            )
        ]
    }
    
    public func addItem(barcode: String, name: String, brand: String? = nil, quantity: Double = 1, unit: String = "units", daysUntilExp: Int = 14) {
        let exp = Calendar.current.date(byAdding: .day, value: daysUntilExp, to: Date()) ?? Date()
        let item = ScannedIntakeItem(
            name: name,
            brand: brand,
            barcode: barcode,
            quantity: quantity,
            unit: unit,
            expirationDate: exp,
            status: .recognized
        )
        scannedItems.insert(item, at: 0)
        lastScannedBarcode = barcode
        toastMessage = "Scanned \(name)"
    }
    
    public func removeItem(at offsets: IndexSet) {
        scannedItems.remove(atOffsets: offsets)
    }
    
    public func commitIntakeSession() async {
        isCommitting = true
        errorMessage = nil
        
        // Simulating intake batch registration via API
        do {
            try await Task.sleep(nanoseconds: 500_000_000)
            self.toastMessage = "Successfully intake committed \(scannedItems.count) items into inventory"
            self.scannedItems.removeAll()
        } catch {
            self.errorMessage = "Failed to commit session: \(error.localizedDescription)"
        }
        
        isCommitting = false
    }
}
