import Foundation

public struct CommonSplitPlanRequest: Decodable, Sendable {
    public var segments: [CommonSplitSegment]

    public init(segments: [CommonSplitSegment]) {
        self.segments = segments
    }

    private enum CodingKeys: String, CodingKey {
        case segments
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        segments = (try? container.decode([CommonSplitSegment].self, forKey: .segments)) ?? []
    }
}

public struct CommonSplitPlanResponse: Codable, Equatable, Sendable {
    public var plans: [CommonSplitPlan]

    public init(plans: [CommonSplitPlan]) {
        self.plans = plans
    }
}

public struct CommonSplitSegment: Decodable, Sendable {
    public var start: Double
    public var end: Double
    public var text: String
    public var words: [CommonSplitWord]
    public var policy: CommonSplitPolicy

    private enum CodingKeys: String, CodingKey {
        case start
        case end
        case text
        case words
        case policy
    }

    public init(
        start: Double,
        end: Double,
        text: String,
        words: [CommonSplitWord],
        policy: CommonSplitPolicy
    ) {
        self.start = start
        self.end = end
        self.text = text
        self.words = words
        self.policy = policy
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        start = Self.decodeDouble(container, .start) ?? 0.0
        end = Self.decodeDouble(container, .end) ?? start
        text = (try? container.decode(String.self, forKey: .text)) ?? ""
        words = (try? container.decode([CommonSplitWord].self, forKey: .words)) ?? []
        policy = (try? container.decode(CommonSplitPolicy.self, forKey: .policy)) ?? CommonSplitPolicy()
    }

    static func decodeDouble<K: CodingKey>(_ container: KeyedDecodingContainer<K>, _ key: K) -> Double? {
        if let value = try? container.decode(Double.self, forKey: key) {
            return value
        }
        if let value = try? container.decode(Int.self, forKey: key) {
            return Double(value)
        }
        if let value = try? container.decode(String.self, forKey: key) {
            return Double(value)
        }
        return nil
    }
}

public struct CommonSplitWord: Decodable, Equatable, Sendable {
    public var word: String
    public var start: Double
    public var end: Double

    private enum CodingKeys: String, CodingKey {
        case word
        case text
        case start
        case end
    }

    public init(word: String, start: Double, end: Double) {
        self.word = word
        self.start = start
        self.end = end
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        word = (try? container.decode(String.self, forKey: .word))
            ?? (try? container.decode(String.self, forKey: .text))
            ?? ""
        start = CommonSplitSegment.decodeDouble(container, .start) ?? 0.0
        end = CommonSplitSegment.decodeDouble(container, .end) ?? start
    }
}

public struct CommonSplitPolicy: Codable, Equatable, Sendable {
    public var enabled: Bool
    public var targetChars: Int
    public var hardChars: Int
    public var hardDuration: Double
    public var minDuration: Double

    private enum CodingKeys: String, CodingKey {
        case enabled
        case targetChars = "target_chars"
        case hardChars = "hard_chars"
        case hardDuration = "hard_duration"
        case minDuration = "min_duration"
    }

    public init(
        enabled: Bool = true,
        targetChars: Int = 16,
        hardChars: Int = 24,
        hardDuration: Double = 5.5,
        minDuration: Double = 0.2
    ) {
        self.enabled = enabled
        self.targetChars = targetChars
        self.hardChars = hardChars
        self.hardDuration = hardDuration
        self.minDuration = minDuration
    }
}

public struct CommonSplitGroup: Codable, Equatable, Sendable {
    public var startIndex: Int
    public var endIndex: Int

    private enum CodingKeys: String, CodingKey {
        case startIndex = "start_index"
        case endIndex = "end_index"
    }

    public init(startIndex: Int, endIndex: Int) {
        self.startIndex = startIndex
        self.endIndex = endIndex
    }
}

public struct CommonSplitPlan: Codable, Equatable, Sendable {
    public var action: String
    public var groups: [CommonSplitGroup]
    public var newEnd: Double?

    private enum CodingKeys: String, CodingKey {
        case action
        case groups
        case newEnd = "new_end"
    }

    public init(action: String, groups: [CommonSplitGroup] = [], newEnd: Double? = nil) {
        self.action = action
        self.groups = groups
        self.newEnd = newEnd
    }
}

public enum CommonSplitPlanner {
    public static func plan(_ request: CommonSplitPlanRequest) -> CommonSplitPlanResponse {
        CommonSplitPlanResponse(plans: request.segments.map(planSegment))
    }

    public static func planSegments(_ segments: [CommonSplitSegment]) -> [CommonSplitPlan] {
        plan(CommonSplitPlanRequest(segments: segments)).plans
    }

    private static func planSegment(_ segment: CommonSplitSegment) -> CommonSplitPlan {
        let policy = segment.policy
        guard policy.enabled else {
            return CommonSplitPlan(action: "keep")
        }
        let text = segment.text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            return CommonSplitPlan(action: "keep")
        }
        let duration = max(0.0, segment.end - segment.start)
        let chars = compactLength(text)
        if chars <= policy.targetChars && duration <= policy.hardDuration + 0.001 {
            return CommonSplitPlan(action: "keep")
        }

        let words = segment.words.filter { !$0.word.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        if words.count >= 2 {
            let groups = splitWordRanges(words, policy: policy)
            if groups.count > 1 {
                return CommonSplitPlan(action: "split", groups: groups)
            }
        }

        if duration > policy.hardDuration + 0.001 {
            let newEnd = round3(max(segment.start + policy.minDuration, segment.start + policy.hardDuration))
            return CommonSplitPlan(action: "clamp", newEnd: newEnd)
        }
        return CommonSplitPlan(action: "keep")
    }

    private static func splitWordRanges(_ words: [CommonSplitWord], policy: CommonSplitPolicy) -> [CommonSplitGroup] {
        guard words.count >= 2 else {
            return [CommonSplitGroup(startIndex: 0, endIndex: words.count)]
        }
        let totalChars = wordChars(words, start: 0, end: words.count)
        let totalDuration = wordDuration(words, start: 0, end: words.count)
        let targetChars = max(1, policy.targetChars)
        let hardDuration = max(0.05, policy.hardDuration)
        var targetCount = max(
            1,
            Int((Double(totalChars + targetChars - 1) / Double(targetChars)).rounded(.down)),
            Int(((totalDuration + hardDuration - 0.001) / hardDuration).rounded(.down))
        )
        targetCount = min(words.count, targetCount)
        var groups = [CommonSplitGroup(startIndex: 0, endIndex: words.count)]

        func groupScore(_ group: CommonSplitGroup) -> Double {
            max(
                Double(wordChars(words, start: group.startIndex, end: group.endIndex)) / max(1.0, Double(policy.targetChars)),
                wordDuration(words, start: group.startIndex, end: group.endIndex) / max(0.05, policy.hardDuration)
            )
        }

        while groups.count < targetCount {
            let candidates = groups.enumerated()
                .filter { $0.element.endIndex - $0.element.startIndex >= 2 }
                .map { (groupScore($0.element), $0.offset) }
            guard let candidate = candidates.max(by: { $0.0 < $1.0 }) else {
                break
            }
            let group = groups[candidate.1]
            guard let split = bestSplitIndex(words, start: group.startIndex, end: group.endIndex) else {
                break
            }
            groups.replaceSubrange(
                candidate.1...candidate.1,
                with: [
                    CommonSplitGroup(startIndex: group.startIndex, endIndex: split),
                    CommonSplitGroup(startIndex: split, endIndex: group.endIndex),
                ]
            )
        }

        var changed = true
        while changed {
            changed = false
            for (idx, group) in groups.enumerated() {
                if group.endIndex - group.startIndex < 2 {
                    continue
                }
                if wordChars(words, start: group.startIndex, end: group.endIndex) <= policy.hardChars
                    && wordDuration(words, start: group.startIndex, end: group.endIndex) <= policy.hardDuration + 0.001 {
                    continue
                }
                guard let split = bestSplitIndex(words, start: group.startIndex, end: group.endIndex) else {
                    continue
                }
                groups.replaceSubrange(
                    idx...idx,
                    with: [
                        CommonSplitGroup(startIndex: group.startIndex, endIndex: split),
                        CommonSplitGroup(startIndex: split, endIndex: group.endIndex),
                    ]
                )
                changed = true
                break
            }
        }

        return groups.filter { $0.endIndex > $0.startIndex }
    }

    private static func bestSplitIndex(_ words: [CommonSplitWord], start: Int, end: Int) -> Int? {
        guard end - start >= 2 else {
            return nil
        }
        let totalChars = max(1, wordChars(words, start: start, end: end))
        let totalDuration = max(0.05, wordDuration(words, start: start, end: end))
        var bestScore: Double?
        var bestIndex: Int?
        for idx in (start + 1)..<end {
            let leftChars = wordChars(words, start: start, end: idx)
            let rightChars = wordChars(words, start: idx, end: end)
            let leftDuration = wordDuration(words, start: start, end: idx)
            let rightDuration = wordDuration(words, start: idx, end: end)
            let charBalance = Double(abs(leftChars - rightChars)) / Double(totalChars)
            let durationBalance = abs(leftDuration - rightDuration) / totalDuration
            let edgePenalty = (idx - start == 1 || end - idx == 1) ? 0.22 : 0.0
            let naturalBonus = isCommonSplitBreak(words[idx - 1], words[idx]) ? -0.18 : 0.0
            let gap = words[idx].start - words[idx - 1].end
            let gapBonus = gap >= 0.28 ? -0.12 : 0.0
            let score = charBalance + durationBalance * 0.45 + edgePenalty + naturalBonus + gapBonus
            if bestScore == nil || score < (bestScore ?? score) {
                bestScore = score
                bestIndex = idx
            }
        }
        return bestIndex
    }

    private static func compactLength(_ value: String) -> Int {
        value.filter { !$0.isWhitespace }.count
    }

    private static func wordChars(_ words: [CommonSplitWord], start: Int, end: Int) -> Int {
        guard start < end else { return 0 }
        return words[start..<end].reduce(0) { $0 + compactLength($1.word) }
    }

    private static func wordDuration(_ words: [CommonSplitWord], start: Int, end: Int) -> Double {
        guard start < end, start >= 0, end <= words.count else { return 0.0 }
        return max(0.0, words[end - 1].end - words[start].start)
    }

    private static func isCommonSplitBreak(_ left: CommonSplitWord, _ right: CommonSplitWord?) -> Bool {
        let text = left.word.trimmingCharacters(in: .whitespacesAndNewlines)
        let nextText = right?.word.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if [".", ",", "!", "?", "~", "…", "。", "，"].contains(where: { text.hasSuffix($0) }) {
            return true
        }
        let clean = text.filter { $0.isLetter || $0.isNumber || ("가"..."힣").contains($0) }
        let nextClean = nextText.filter { $0.isLetter || $0.isNumber || ("가"..."힣").contains($0) }
        let endTokens = [
            "거든요", "거든", "는데요", "는데", "네요", "습니다", "합니다", "했는데",
            "했고", "하고", "해서", "니까", "라고", "같아요", "같고", "예요",
            "이에요", "요", "죠", "다", "고",
        ]
        let startTokens = [
            "그리고", "그래서", "근데", "그런데", "이번에는", "일단", "여기",
            "저기", "그러면", "자", "아", "오",
        ]
        return endTokens.contains(where: { clean.hasSuffix($0) })
            || startTokens.contains(where: { nextClean.hasPrefix($0) })
    }

    private static func round3(_ value: Double) -> Double {
        (value * 1_000.0).rounded() / 1_000.0
    }
}
