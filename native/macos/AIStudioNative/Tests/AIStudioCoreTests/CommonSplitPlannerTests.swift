import XCTest
@testable import AIStudioCore

final class CommonSplitPlannerTests: XCTestCase {
    func testLongSegmentSplitsIntoSafeGroups() throws {
        let text = "여기 안에 들어가 있는 것도 똑같고 저기 방향제도 똑같고 이번에는 동일한 차를 그냥 2대를 만드셨네"
        let tokens = text.split(separator: " ").map(String.init)
        let words = tokens.enumerated().map { index, token in
            CommonSplitWord(
                word: token,
                start: (Double(index) * (9.9 / Double(tokens.count)) * 1_000).rounded() / 1_000,
                end: (Double(index + 1) * (9.9 / Double(tokens.count)) * 1_000).rounded() / 1_000
            )
        }
        let segment = CommonSplitSegment(
            start: 0,
            end: 9.9,
            text: text,
            words: words,
            policy: CommonSplitPolicy(
                enabled: true,
                targetChars: 16,
                hardChars: 24,
                hardDuration: 5.5,
                minDuration: 0.2
            )
        )

        let response = CommonSplitPlanner.plan(CommonSplitPlanRequest(segments: [segment]))
        let plan = try XCTUnwrap(response.plans.first)
        XCTAssertEqual(plan.action, "split")
        XCTAssertGreaterThan(plan.groups.count, 1)
        for group in plan.groups {
            let chars = words[group.startIndex..<group.endIndex].reduce(0) { sum, word in
                sum + word.word.filter { !$0.isWhitespace }.count
            }
            let duration = words[group.endIndex - 1].end - words[group.startIndex].start
            XCTAssertLessThanOrEqual(chars, 24)
            XCTAssertLessThanOrEqual(duration, 5.501)
        }
    }

    func testSingleWordLongDurationClamps() throws {
        let segment = CommonSplitSegment(
            start: 2.0,
            end: 12.0,
            text: "테스트",
            words: [CommonSplitWord(word: "테스트", start: 2.0, end: 12.0)],
            policy: CommonSplitPolicy(
                enabled: true,
                targetChars: 16,
                hardChars: 24,
                hardDuration: 5.5,
                minDuration: 0.2
            )
        )

        let plan = try XCTUnwrap(CommonSplitPlanner.planSegments([segment]).first)
        XCTAssertEqual(plan.action, "clamp")
        XCTAssertEqual(plan.newEnd, 7.5)
    }

    func testShortSegmentKeeps() throws {
        let segment = CommonSplitSegment(
            start: 0,
            end: 1,
            text: "안녕하세요",
            words: [CommonSplitWord(word: "안녕하세요", start: 0.1, end: 0.9)],
            policy: CommonSplitPolicy()
        )

        let plan = try XCTUnwrap(CommonSplitPlanner.planSegments([segment]).first)
        XCTAssertEqual(plan.action, "keep")
        XCTAssertTrue(plan.groups.isEmpty)
        XCTAssertNil(plan.newEnd)
    }
}
