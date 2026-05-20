import CryptoKit
import Foundation

extension TimelineEditing {
    public static func undoSnapshot(_ request: TimelineUndoSnapshotRequest) -> TimelineUndoSnapshotResponse {
        let normalizedBlocks = request.blocks.map {
            TimelineUndoSnapshotBlock(
                text: $0.text,
                speakerID: $0.speakerID,
                start: round(max(0.0, $0.start) * 1_000_000) / 1_000_000,
                end: $0.end.map { round(max(0.0, $0) * 1_000_000) / 1_000_000 },
                isGap: $0.isGap
            )
        }
        let normalizedSegments = request.segments.map {
            TimelineUndoSnapshotSegment(
                line: $0.line,
                start: round(max(0.0, $0.start) * 1_000_000) / 1_000_000,
                end: round(max(0.0, $0.end) * 1_000_000) / 1_000_000,
                text: $0.text,
                speakerID: $0.speakerID,
                isGap: $0.isGap
            )
        }
        let snapshot: [String: AnyEncodable] = [
            "blocks": AnyEncodable(normalizedBlocks),
            "segments": AnyEncodable(normalizedSegments),
            "cursorLine": AnyEncodable(request.cursorLine),
            "activeClipIndex": AnyEncodable(request.activeClipIndex),
            "projectBoundaryTimes": AnyEncodable(request.projectBoundaryTimes.map { round(max(0.0, $0) * 1_000_000) / 1_000_000 }),
        ]
        let fingerprintValue = fingerprintDictionary(snapshot) ?? ""
        return TimelineUndoSnapshotResponse(
            fingerprint: fingerprintValue,
            blockCount: normalizedBlocks.count,
            segmentCount: normalizedSegments.count,
            cursorLine: request.cursorLine,
            activeClipIndex: request.activeClipIndex,
            projectBoundaryTimes: request.projectBoundaryTimes
        )
    }

    public static func srtMetadataMatches(_ request: TimelineSRTMetadataMatchRequest) -> TimelineSRTMetadataMatchResponse {
        let project = request.projectSegments
        if request.srtSegments.isEmpty || project.isEmpty {
            return TimelineSRTMetadataMatchResponse(matches: request.srtSegments.map { _ in -1 })
        }

        let projectCount = project.count
        let textIndex = Dictionary(grouping: project.enumerated(), by: { normalizedSegmentText($0.element.text) })
        var used = Set<Int>()
        var matches: [Int] = []

        for (srtIndex, srtSeg) in request.srtSegments.enumerated() {
            var candidateIndices = Set<Int>()

            for offset in -14...14 {
                let candidate = srtIndex + offset
                if candidate >= 0 && candidate < projectCount {
                    candidateIndices.insert(candidate)
                }
            }
            if srtIndex < projectCount {
                candidateIndices.insert(srtIndex)
            }

            let normalizedText = normalizedSegmentText(srtSeg.text)
            if let textMatches = textIndex[normalizedText] {
                for item in textMatches.prefix(24) {
                    candidateIndices.insert(item.offset)
                }
            }

            var bestIndex = -1
            var bestScore = Int.min
            for projectIndex in candidateIndices.sorted() {
                if used.contains(projectIndex) {
                    continue
                }
                let score = metadataMatchScore(
                    srtSegment: srtSeg,
                    projectSegment: project[projectIndex],
                    srtIndex: srtIndex,
                    projectIndex: projectIndex
                )
                if score > bestScore {
                    bestScore = score
                    bestIndex = projectIndex
                }
            }

            if bestScore < 30, projectCount == request.srtSegments.count, srtIndex < projectCount, !used.contains(srtIndex) {
                bestIndex = srtIndex
            } else if bestIndex < 0, srtIndex < projectCount, !used.contains(srtIndex) {
                bestIndex = srtIndex
            }

            if bestIndex >= 0 {
                used.insert(bestIndex)
            }
            matches.append(bestIndex)
        }

        return TimelineSRTMetadataMatchResponse(matches: matches)
    }

    public static func prepareEditorSegmentsForLoad(_ request: TimelineEditorLoadRequest) -> TimelineEditorLoadResponse {
        let fps = max(1.0, request.frameRate.isFinite ? request.frameRate : 30.0)
        var prepared: [TimelineEditorLoadPreparedSegment] = []
        prepared.reserveCapacity(request.segments.count)

        for item in request.segments {
            let start = snapSecToFrame(max(0.0, item.start), fps: fps)
            var end = snapSecToFrame(max(start, item.end.isFinite ? item.end : start), fps: fps)
            if end <= start {
                end = snapSecToFrame(start + 0.5, fps: fps)
            }

            if item.isGap ?? false {
                prepared.append(
                    TimelineEditorLoadPreparedSegment(
                        sourceIndex: item.sourceIndex,
                        start: start,
                        end: end,
                        text: "",
                        parts: [],
                        isGap: true
                    )
                )
                continue
            }

            let cleaned = cleanEditorLoadText(item.text)
            let parts = cleaned
                .split(separator: "\n", omittingEmptySubsequences: false)
                .map(String.init)
                .filter { !$0.isEmpty }
            if parts.isEmpty {
                continue
            }
            prepared.append(
                TimelineEditorLoadPreparedSegment(
                    sourceIndex: item.sourceIndex,
                    start: start,
                    end: end,
                    text: parts.joined(separator: "\n"),
                    parts: parts,
                    isGap: false
                )
            )
        }

        return TimelineEditorLoadResponse(segments: prepared)
    }

    static func cleanEditorLoadText(_ text: String) -> String {
        var cleaned = text.replacingOccurrences(of: "\u{2028}", with: "\n")
        cleaned = regexReplace(cleaned, pattern: #"<\|[^|>\n\r]{1,80}\|>"#, replacement: " ")
        cleaned = regexReplace(cleaned, pattern: #"[［\[{(<【（《]\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*[\]})>】）》]"#, replacement: " ")
        cleaned = regexReplace(cleaned, pattern: #"(?<!\S)\d{1,3}[:\.]\d{2}[:\.]\d{2,3}(?!\S)"#, replacement: " ")
        cleaned = regexReplace(cleaned, pattern: #"\d{1,3}[:\.]\d{2}[:\.]\d{2,3}\s*$"#, replacement: " ")
        cleaned = regexReplace(cleaned, pattern: #"^\s*\d{1,3}[:\.]\d{2}(?:[:\.]\d+)?\s+"#, replacement: "")
        cleaned = regexReplace(cleaned, pattern: #"<[^>]+>"#, replacement: "")
        let parts = cleaned
            .replacingOccurrences(of: "\r", with: "")
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { raw in
                regexReplace(String(raw).trimmingCharacters(in: .whitespacesAndNewlines), pattern: #"[ \t\f\v]+"#, replacement: " ")
            }
            .filter { !$0.isEmpty }
        return parts.joined(separator: "\n")
    }

    static func regexReplace(_ source: String, pattern: String, replacement: String) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: []) else {
            return source
        }
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        return regex.stringByReplacingMatches(in: source, options: [], range: range, withTemplate: replacement)
    }

    static func normalizedSegmentText(_ text: String) -> String {
        regexReplace(text.trimmingCharacters(in: .whitespacesAndNewlines), pattern: #"\s+"#, replacement: " ")
    }

    static func metadataMatchScore(
        srtSegment: TimelineSRTMetadataMatchSegment,
        projectSegment: TimelineSRTMetadataMatchSegment,
        srtIndex: Int,
        projectIndex: Int
    ) -> Int {
        let startDelta = abs(srtSegment.start - projectSegment.start)
        let endDelta = abs(srtSegment.end - projectSegment.end)
        let srtText = normalizedSegmentText(srtSegment.text)
        let projectText = normalizedSegmentText(projectSegment.text)
        var score = 0
        if startDelta <= 0.05 && endDelta <= 0.05 {
            score += 50
        } else if startDelta <= 0.25 && endDelta <= 0.25 {
            score += 34
        } else if startDelta <= 0.6 && endDelta <= 0.6 {
            score += 16
        }
        if !srtText.isEmpty && !projectText.isEmpty {
            if srtText == projectText {
                score += 44
            } else if srtText.contains(projectText) || projectText.contains(srtText) {
                score += 22
            }
        }
        if srtIndex == projectIndex {
            score += 12
        }
        return score
    }

    static func fingerprint<T: Encodable>(for value: T) -> String? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        guard let data = try? encoder.encode(value) else {
            return nil
        }
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    static func fingerprintDictionary(_ value: [String: AnyEncodable]) -> String? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        guard let data = try? encoder.encode(value) else {
            return nil
        }
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}

public struct AnyEncodable: Encodable {
    private let encodeImpl: (Encoder) throws -> Void

    public init<T: Encodable>(_ value: T) {
        self.encodeImpl = value.encode(to:)
    }

    public func encode(to encoder: Encoder) throws {
        try encodeImpl(encoder)
    }
}
