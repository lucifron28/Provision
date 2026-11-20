import Foundation
import XCTest
@testable import frontend

private final class PipChatRequestProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var lastRequest: URLRequest?
    nonisolated(unsafe) private static var lastRequestBody: Data?

    static func reset() {
        lock.lock()
        lastRequest = nil
        lastRequestBody = nil
        lock.unlock()
    }

    static func capturedRequest() -> URLRequest? {
        lock.lock()
        defer { lock.unlock() }
        return lastRequest
    }

    static func capturedRequestBody() -> Data? {
        lock.lock()
        defer { lock.unlock() }
        return lastRequestBody
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let body = Self.bodyData(for: request)
        Self.lock.lock()
        Self.lastRequest = request
        Self.lastRequestBody = body
        Self.lock.unlock()

        let responseBody = #"{"reply":"Try a household recipe.","language":"english","facts":[],"actions":[],"recipe_cards":[],"model":"fake","usage":{"prompt_tokens":3,"completion_tokens":4,"total_tokens":7},"local_guidance":false,"safety_notice":"Verify safety in Cook with Pip."}"#
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(responseBody.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    private static func bodyData(for request: URLRequest) -> Data? {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return nil }

        stream.open()
        defer { stream.close() }

        let capacity = 1024
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: capacity)
        defer { buffer.deallocate() }

        var data = Data()
        while true {
            let count = stream.read(buffer, maxLength: capacity)
            if count < 0 { return nil }
            if count == 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }

    override func stopLoading() {}
}

@MainActor
final class PipChatAPIClientTests: XCTestCase {
    func testChatRequestUsesSelectedHouseholdAndTypedPayload() async throws {
        PipChatRequestProtocol.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PipChatRequestProtocol.self]
        let client = APIClient(
            baseURL: URL(string: "https://provision.test/api/v1")!,
            session: URLSession(configuration: configuration)
        )
        let scope = HouseholdScope(userID: 11, householdID: 22, serverID: "test-server")
        await client.setAccessToken("synthetic-token")
        await client.setHouseholdScope(scope)

        let wrongScope = HouseholdScope(userID: 11, householdID: 23, serverID: "test-server")
        do {
            _ = try await client.sendPipChat(
                PipChatRequest(message: "Hello", history: []),
                scope: wrongScope
            )
            XCTFail("The API client must reject a request for a different selected household")
        } catch APIError.sessionChanged {
            // Expected: household scope is checked before a network request.
        }
        XCTAssertNil(PipChatRequestProtocol.capturedRequest())

        let history = [PipChatHistoryTurn(role: "user", content: "Anong lulutuin?")]
        let response = try await client.sendPipChat(
            PipChatRequest(
                message: "Let's make dinner",
                history: history,
                context: PipChatContext(kind: .recipe, id: 305),
                recentRecipeIDs: [303]
            ),
            scope: scope
        )
        XCTAssertEqual(response.reply, "Try a household recipe.")
        XCTAssertFalse(response.local_guidance)

        let request = try XCTUnwrap(PipChatRequestProtocol.capturedRequest())
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertEqual(request.url?.path, "/api/v1/pip/chat")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer synthetic-token")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Household-ID"), "22")
        let body = try XCTUnwrap(PipChatRequestProtocol.capturedRequestBody())
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(payload["message"] as? String, "Let's make dinner")
        let encodedHistory = try XCTUnwrap(payload["history"] as? [[String: String]])
        XCTAssertEqual(encodedHistory, [["role": "user", "content": "Anong lulutuin?"]])
        let context = try XCTUnwrap(payload["context"] as? [String: Any])
        XCTAssertEqual(context["kind"] as? String, "recipe")
        XCTAssertEqual(context["id"] as? Int, 305)
        XCTAssertEqual(payload["recent_recipe_ids"] as? [Int], [303])
    }
}
