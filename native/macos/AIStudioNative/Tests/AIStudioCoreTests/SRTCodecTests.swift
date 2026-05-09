import XCTest
@testable import AIStudioCore

final class SRTCodecTests: XCTestCase {
    func testParseMultilineSRTAndPreserveTimestamps() {
        let input = """
        1
        00:00:01,250 --> 00:00:03,500
        첫 줄
        둘째 줄

        2
        00:00:04.000 --> 00:00:05.125
        다음 자막
        """

        let segments = SRTCodec.parse(input)

        XCTAssertEqual(segments.count, 2)
        XCTAssertEqual(segments[0].start, 1.25, accuracy: 0.0001)
        XCTAssertEqual(segments[0].end, 3.5, accuracy: 0.0001)
        XCTAssertEqual(segments[0].text, "첫 줄\n둘째 줄")
        XCTAssertEqual(segments[1].start, 4.0, accuracy: 0.0001)
        XCTAssertEqual(segments[1].end, 5.125, accuracy: 0.0001)
    }

    func testFormatSRTClampsInvalidEndTime() {
        let segments = [
            SubtitleSegment(start: 2.0, end: 1.0, text: "짧은 자막")
        ]

        let output = SRTCodec.format(segments)

        XCTAssertTrue(output.contains("00:00:02,000 --> 00:00:02,100"))
        XCTAssertTrue(output.contains("짧은 자막"))
    }
}
