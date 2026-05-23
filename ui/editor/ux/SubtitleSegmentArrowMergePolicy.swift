import Foundation

public enum SubtitleSegmentArrowMergeAction: String, Sendable {
    case merge
    case deleteCoveredText
}

public struct SubtitleSegmentArrowMergeInput: Sendable {
    public let draggedID: Int
    public let coveredID: Int
    public let draggedText: String
    public let coveredText: String
    public let draggedStart: Double
    public let draggedEnd: Double
    public let coveredStart: Double
    public let coveredEnd: Double

    public init(
        draggedID: Int,
        coveredID: Int,
        draggedText: String,
        coveredText: String,
        draggedStart: Double,
        draggedEnd: Double,
        coveredStart: Double,
        coveredEnd: Double
    ) {
        self.draggedID = draggedID
        self.coveredID = coveredID
        self.draggedText = draggedText
        self.coveredText = coveredText
        self.draggedStart = draggedStart
        self.draggedEnd = draggedEnd
        self.coveredStart = coveredStart
        self.coveredEnd = coveredEnd
    }
}

public struct SubtitleSegmentArrowMergePlan: Equatable, Sendable {
    public let keepID: Int
    public let removeID: Int
    public let start: Double
    public let end: Double
    public let text: String
}

public enum SubtitleSegmentArrowMergePolicy {
    // 변경 금지: 화살표 메뉴의 "지우기"는 덮인 세그먼트의 글자만 제거하고,
    // 끌어온 세그먼트는 덮인 세그먼트의 시간 끝까지 확장한다.
    // "합치기"는 같은 시간 범위를 쓰되 텍스트를 시간순으로 결합한다.
    public static func plan(
        action: SubtitleSegmentArrowMergeAction,
        input: SubtitleSegmentArrowMergeInput
    ) -> SubtitleSegmentArrowMergePlan {
        let start = min(input.draggedStart, input.coveredStart)
        let end = max(input.draggedEnd, input.coveredEnd)
        let text: String

        switch action {
        case .deleteCoveredText:
            text = input.draggedText
        case .merge:
            if input.draggedStart <= input.coveredStart {
                text = joined(input.draggedText, input.coveredText)
            } else {
                text = joined(input.coveredText, input.draggedText)
            }
        }

        return SubtitleSegmentArrowMergePlan(
            keepID: input.draggedID,
            removeID: input.coveredID,
            start: start,
            end: end,
            text: text
        )
    }

    private static func joined(_ first: String, _ second: String) -> String {
        let left = first.trimmingCharacters(in: .whitespacesAndNewlines)
        let right = second.trimmingCharacters(in: .whitespacesAndNewlines)
        if left.isEmpty { return right }
        if right.isEmpty { return left }
        return left + " " + right
    }
}
