import XCTest
@testable import AIStudioCore

final class SubtitleEditorSyncTests: XCTestCase {
    func testPrepareEditorSegmentsForLoadKeepsSingleSpeakerHyphenLinesInsideOneBlock() {
        let response = TimelineEditing.prepareEditorSegmentsForLoad(
            TimelineEditorLoadRequest(
                segments: [
                    TimelineEditorLoadInputSegment(
                        sourceIndex: 0,
                        start: 1.0,
                        end: 3.0,
                        text: "- 안녕하세요\n- 반갑습니다",
                        isGap: false,
                        speaker: "00",
                        speaker2: nil,
                        speakerList: ["00"]
                    )
                ],
                frameRate: 30.0
            )
        )

        XCTAssertEqual(response.segments.count, 1)
        XCTAssertEqual(response.segments[0].text, "- 안녕하세요\n- 반갑습니다")
        XCTAssertEqual(response.blocks.map(\.text), ["- 안녕하세요\u{2028}- 반갑습니다"])
    }

    func testPrepareEditorSegmentsForLoadSplitsTrueMultiSpeakerHyphenLinesIntoSeparateBlocks() {
        let response = TimelineEditing.prepareEditorSegmentsForLoad(
            TimelineEditorLoadRequest(
                segments: [
                    TimelineEditorLoadInputSegment(
                        sourceIndex: 0,
                        start: 1.0,
                        end: 3.0,
                        text: "- 안녕하세요\n- 반갑습니다",
                        isGap: false,
                        speaker: "00",
                        speaker2: "01",
                        speakerList: ["00", "01"]
                    )
                ],
                frameRate: 30.0
            )
        )

        XCTAssertEqual(response.segments.count, 1)
        XCTAssertEqual(response.segments[0].parts, ["- 안녕하세요", "- 반갑습니다"])
        XCTAssertEqual(response.blocks.map(\.text), ["- 안녕하세요", "- 반갑습니다"])
    }
}
