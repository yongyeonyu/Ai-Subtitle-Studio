import XCTest
@testable import AIStudioCore

final class SubtitleCoreTests: XCTestCase {
    func testSubtitleCoreCommonSplitPlanWrapsPlannerResponse() throws {
        let payload: [String: Any] = [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "common_split_plan",
            "payload": [
                "segments": [
                    [
                        "start": 0.0,
                        "end": 8.0,
                        "text": "여기 안에 들어가 있는 것도 똑같고 저기 방향제도 똑같고 이번에는 동일한 차를 그냥 2대를 만드셨네",
                        "words": [
                            ["word": "여기", "start": 0.0, "end": 0.7],
                            ["word": "안에", "start": 0.7, "end": 1.4],
                            ["word": "들어가", "start": 1.4, "end": 2.1],
                            ["word": "있는", "start": 2.1, "end": 2.8],
                            ["word": "것도", "start": 2.8, "end": 3.5],
                            ["word": "똑같고", "start": 3.5, "end": 4.2],
                            ["word": "저기", "start": 4.2, "end": 4.9],
                            ["word": "방향제도", "start": 4.9, "end": 5.6],
                            ["word": "똑같고", "start": 5.6, "end": 6.3],
                            ["word": "이번에는", "start": 6.3, "end": 7.0],
                            ["word": "동일한", "start": 7.0, "end": 7.5],
                            ["word": "차를", "start": 7.5, "end": 8.0],
                        ],
                        "policy": [
                            "enabled": true,
                            "target_chars": 16,
                            "hard_chars": 24,
                            "hard_duration": 5.5,
                            "min_duration": 0.2,
                        ],
                    ],
                ],
            ],
        ]

        let response = SubtitleCoreNative.plan(payload: payload)
        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "common_split_plan")
        let result = try XCTUnwrap(response["result"] as? [String: Any])
        let plans = try XCTUnwrap(result["plans"] as? [[String: Any]])
        XCTAssertEqual(plans.count, 1)
        XCTAssertEqual(plans.first?["action"] as? String, "split")
    }

    func testSubtitleCoreRejectsUnknownOperation() {
        let response = SubtitleCoreNative.plan(payload: [
            "schema": SubtitleCoreNative.requestSchema,
            "operation": "unknown_operation",
            "payload": [:],
        ])

        XCTAssertEqual(response["schema"] as? String, SubtitleCoreNative.responseSchema)
        XCTAssertEqual(response["operation"] as? String, "unknown_operation")
        XCTAssertNotNil(response["error"] as? String)
    }
}
