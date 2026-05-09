import Foundation

public struct SubtitleSegment: Codable, Equatable, Sendable {
    public var start: Double
    public var end: Double
    public var text: String
    public var isGap: Bool

    public init(start: Double, end: Double, text: String, isGap: Bool = false) {
        self.start = start
        self.end = end
        self.text = text
        self.isGap = isGap
    }

    private enum CodingKeys: String, CodingKey {
        case start
        case end
        case text
        case isGap = "is_gap"
    }
}
