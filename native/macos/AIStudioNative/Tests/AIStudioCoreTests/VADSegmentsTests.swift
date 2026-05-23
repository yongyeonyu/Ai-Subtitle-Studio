import XCTest
@testable import AIStudioCore

final class VADSegmentsTests: XCTestCase {
    func testFlagsToSegmentsMatchesPythonPolicyShape() throws {
        let response = VADSegmentsNative.flagsToSegments(payload: [
            "flags": [0, 1, 1, 0, 0, 1, 1, 1, 0],
            "hop_sec": 0.1,
            "min_speech_sec": 0.15,
            "min_silence_sec": 0.0,
            "speech_pad_sec": 0.05,
            "source": "ten_vad",
            "for_post_stt_align": true,
        ])

        let rows = try XCTUnwrap(response["segments"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 2)
        XCTAssertEqual(rows[0]["start"] as? Double ?? -1, 0.05, accuracy: 0.001)
        XCTAssertEqual(rows[0]["end"] as? Double ?? -1, 0.35, accuracy: 0.001)
        XCTAssertEqual(rows[0]["source"] as? String, "ten_vad")
        XCTAssertEqual(rows[0]["post_stt_align"] as? Bool, true)
        XCTAssertEqual(rows[0]["vad_word_filter"] as? Bool, false)
        XCTAssertEqual(rows[1]["start"] as? Double ?? -1, 0.45, accuracy: 0.001)
        XCTAssertEqual(rows[1]["end"] as? Double ?? -1, 0.85, accuracy: 0.001)
    }

    func testFlagsMergeCloseSpeechRuns() throws {
        let response = VADSegmentsNative.flagsToSegments(payload: [
            "flags": [1, 1, 0, 1, 1],
            "hop_sec": 0.1,
            "min_speech_sec": 0.1,
            "min_silence_sec": 0.11,
            "speech_pad_sec": 0.0,
            "source": "ten_vad",
        ])

        let rows = try XCTUnwrap(response["segments"] as? [[String: Any]])
        XCTAssertEqual(rows.count, 1)
        XCTAssertEqual(rows[0]["start"] as? Double ?? -1, 0.0, accuracy: 0.001)
        XCTAssertEqual(rows[0]["end"] as? Double ?? -1, 0.5, accuracy: 0.001)
    }
}
