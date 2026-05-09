import XCTest
@testable import AIStudioCore

final class TimelineColumnsTests: XCTestCase {
    func testBuildWaveformColumnsMatchesMinimapRules() {
        let columns = TimelineColumns.buildWaveformColumns(
            waveform: [0.0, 0.5, 1.0, 0.25],
            width: 4,
            totalDuration: 4.0,
            vadSegments: [TimelineRange(start: 1.0, end: 2.0)]
        )

        XCTAssertEqual(columns.heights, [1, 7, 14, 3])
        XCTAssertEqual(columns.speech, [false, true, true, false])
    }

    func testEmptyWaveformReturnsEmptyColumns() {
        let columns = TimelineColumns.buildWaveformColumns(
            waveform: [],
            width: 100,
            totalDuration: 10.0
        )

        XCTAssertTrue(columns.heights.isEmpty)
        XCTAssertTrue(columns.speech.isEmpty)
    }

    func testSegmentLayoutCullsAndClipsVisibleRows() {
        let response = TimelineLayout.segmentLayouts(TimelineSegmentLayoutRequest(
            segments: [
                TimelineSegmentLayoutInput(id: "hidden", line: 1, start: 0.0, end: 0.5),
                TimelineSegmentLayoutInput(id: "visible", line: 2, start: 1.5, end: 2.5, lane: 1),
                TimelineSegmentLayoutInput(id: "tail", line: 3, start: 9.8, end: 10.4)
            ],
            viewStart: 1.0,
            viewEnd: 3.0,
            width: 200,
            top: 10,
            rowHeight: 20,
            laneGap: 4,
            minWidth: 3,
            padSec: 0.0,
            playheadSec: 2.0
        ))

        XCTAssertEqual(response.visibleCount, 1)
        XCTAssertEqual(response.layouts.first?.id, "visible")
        XCTAssertEqual(response.layouts.first?.x, 50)
        XCTAssertEqual(response.layouts.first?.width, 100)
        XCTAssertEqual(response.layouts.first?.y, 34)
        XCTAssertEqual(response.layouts.first?.isActive, true)
    }

    func testPlayheadDirtyRectUsesOldAndNewPixelsOnly() {
        let rect = TimelineLayout.playheadDirtyRect(TimelinePlayheadDirtyRequest(
            oldSec: 1.0,
            newSec: 2.0,
            viewStart: 0.0,
            viewEnd: 4.0,
            width: 400,
            height: 36,
            extraPx: 8
        ))

        XCTAssertEqual(rect.x, 200)
        XCTAssertEqual(rect.left, 92)
        XCTAssertEqual(rect.width, 117)
        XCTAssertEqual(rect.height, 36)
    }
}
