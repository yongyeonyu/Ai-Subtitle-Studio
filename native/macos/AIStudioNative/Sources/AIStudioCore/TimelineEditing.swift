import CryptoKit
import Foundation

public struct TimelineTimingDragCandidate: Codable, Equatable, Sendable {
    public var time: Double
    public var kind: String?
    public var threshold: Double?

    public init(time: Double, kind: String? = nil, threshold: Double? = nil) {
        self.time = time
        self.kind = kind
        self.threshold = threshold
    }
}

public struct TimelineTimingDragRequest: Codable, Equatable, Sendable {
    public var edge: String
    public var delta: Double
    public var originalStart: Double
    public var originalEnd: Double
    public var minValue: Double
    public var maxValue: Double
    public var frameRate: Double
    public var snapThreshold: Double
    public var candidates: [TimelineTimingDragCandidate]

    public init(
        edge: String,
        delta: Double,
        originalStart: Double,
        originalEnd: Double,
        minValue: Double,
        maxValue: Double,
        frameRate: Double,
        snapThreshold: Double,
        candidates: [TimelineTimingDragCandidate] = []
    ) {
        self.edge = edge
        self.delta = delta
        self.originalStart = originalStart
        self.originalEnd = originalEnd
        self.minValue = minValue
        self.maxValue = maxValue
        self.frameRate = frameRate
        self.snapThreshold = snapThreshold
        self.candidates = candidates
    }
}

public struct TimelineTimingDragResponse: Codable, Equatable, Sendable {
    public var edge: String
    public var start: Double?
    public var end: Double?
    public var guideTime: Double?
    public var snappedTime: Double?
    public var snappedKind: String?

    public init(
        edge: String,
        start: Double? = nil,
        end: Double? = nil,
        guideTime: Double? = nil,
        snappedTime: Double? = nil,
        snappedKind: String? = nil
    ) {
        self.edge = edge
        self.start = start
        self.end = end
        self.guideTime = guideTime
        self.snappedTime = snappedTime
        self.snappedKind = snappedKind
    }
}

public struct TimelineSubtitleMergePreviewRequest: Codable, Equatable, Sendable {
    public var edge: String
    public var currentStart: Double
    public var currentEnd: Double
    public var previousStart: Double?
    public var previousEnd: Double?
    public var nextStart: Double?
    public var nextEnd: Double?
    public var frameRate: Double

    public init(
        edge: String,
        currentStart: Double,
        currentEnd: Double,
        previousStart: Double? = nil,
        previousEnd: Double? = nil,
        nextStart: Double? = nil,
        nextEnd: Double? = nil,
        frameRate: Double
    ) {
        self.edge = edge
        self.currentStart = currentStart
        self.currentEnd = currentEnd
        self.previousStart = previousStart
        self.previousEnd = previousEnd
        self.nextStart = nextStart
        self.nextEnd = nextEnd
        self.frameRate = frameRate
    }
}

public struct TimelineSubtitleMergePreviewResponse: Codable, Equatable, Sendable {
    public var target: String?

    public init(target: String? = nil) {
        self.target = target
    }
}

public struct TimelineSubtitleMagnetSegment: Codable, Equatable, Sendable {
    public var line: Int?
    public var start: Double
    public var end: Double
    public var text: String
    public var spk: String?
    public var speaker: String?
    public var isGap: Bool?
    public var startFrame: Int?
    public var endFrame: Int?
    public var timelineStartFrame: Int?
    public var timelineEndFrame: Int?

    public init(
        line: Int? = nil,
        start: Double,
        end: Double,
        text: String = "",
        spk: String? = nil,
        speaker: String? = nil,
        isGap: Bool? = nil,
        startFrame: Int? = nil,
        endFrame: Int? = nil,
        timelineStartFrame: Int? = nil,
        timelineEndFrame: Int? = nil
    ) {
        self.line = line
        self.start = start
        self.end = end
        self.text = text
        self.spk = spk
        self.speaker = speaker
        self.isGap = isGap
        self.startFrame = startFrame
        self.endFrame = endFrame
        self.timelineStartFrame = timelineStartFrame
        self.timelineEndFrame = timelineEndFrame
    }
}

public struct TimelineSubtitleMagnetVADSegment: Codable, Equatable, Sendable {
    public var start: Double
    public var end: Double

    public init(start: Double, end: Double) {
        self.start = start
        self.end = end
    }
}

public struct TimelineSubtitleMagnetSnapshotRow: Codable, Equatable, Sendable {
    public var index: Int
    public var line: Int
    public var start: Double
    public var end: Double
    public var text: String
    public var spk: String

    public init(index: Int, line: Int, start: Double, end: Double, text: String, spk: String) {
        self.index = index
        self.line = line
        self.start = start
        self.end = end
        self.text = text
        self.spk = spk
    }
}

public struct TimelineSubtitleMagnetReport: Codable, Equatable, Sendable {
    public var thresholdSec: Double
    public var closedPairs: Int
    public var mergedPairs: Int
    public var blocked: [String: Int]
    public var modes: [String: Int]

    public init(
        thresholdSec: Double,
        closedPairs: Int,
        mergedPairs: Int,
        blocked: [String: Int],
        modes: [String: Int]
    ) {
        self.thresholdSec = thresholdSec
        self.closedPairs = closedPairs
        self.mergedPairs = mergedPairs
        self.blocked = blocked
        self.modes = modes
    }
}

public struct TimelineSubtitleMagnetRequest: Codable, Equatable, Sendable {
    public var segments: [TimelineSubtitleMagnetSegment]
    public var thresholdSec: Double
    public var boundaryTimes: [Double]
    public var provisionalBoundaries: [Double]
    public var vadSegments: [TimelineSubtitleMagnetVADSegment]
    public var speakerStrict: Bool
    public var frameRate: Double
    public var policy: [String: Double]
    public var strategy: String

    public init(
        segments: [TimelineSubtitleMagnetSegment],
        thresholdSec: Double,
        boundaryTimes: [Double] = [],
        provisionalBoundaries: [Double] = [],
        vadSegments: [TimelineSubtitleMagnetVADSegment] = [],
        speakerStrict: Bool = true,
        frameRate: Double,
        policy: [String: Double] = [:],
        strategy: String = "extend_current"
    ) {
        self.segments = segments
        self.thresholdSec = thresholdSec
        self.boundaryTimes = boundaryTimes
        self.provisionalBoundaries = provisionalBoundaries
        self.vadSegments = vadSegments
        self.speakerStrict = speakerStrict
        self.frameRate = frameRate
        self.policy = policy
        self.strategy = strategy
    }
}

public struct TimelineSubtitleMagnetResponse: Codable, Equatable, Sendable {
    public var segments: [TimelineSubtitleMagnetSegment]
    public var report: TimelineSubtitleMagnetReport
    public var snapshotBefore: [TimelineSubtitleMagnetSnapshotRow]
    public var snapshotAfter: [TimelineSubtitleMagnetSnapshotRow]
    public var fingerprintBefore: String?
    public var fingerprintAfter: String?

    public init(
        segments: [TimelineSubtitleMagnetSegment],
        report: TimelineSubtitleMagnetReport,
        snapshotBefore: [TimelineSubtitleMagnetSnapshotRow] = [],
        snapshotAfter: [TimelineSubtitleMagnetSnapshotRow] = [],
        fingerprintBefore: String? = nil,
        fingerprintAfter: String? = nil
    ) {
        self.segments = segments
        self.report = report
        self.snapshotBefore = snapshotBefore
        self.snapshotAfter = snapshotAfter
        self.fingerprintBefore = fingerprintBefore
        self.fingerprintAfter = fingerprintAfter
    }
}

public struct TimelineUndoSnapshotBlock: Codable, Equatable, Sendable {
    public var text: String
    public var speakerID: String
    public var start: Double
    public var end: Double?
    public var isGap: Bool
}

public struct TimelineUndoSnapshotSegment: Codable, Equatable, Sendable {
    public var line: Int
    public var start: Double
    public var end: Double
    public var text: String
    public var speakerID: String
    public var isGap: Bool
}

public struct TimelineUndoSnapshotRequest: Codable, Equatable, Sendable {
    public var blocks: [TimelineUndoSnapshotBlock]
    public var segments: [TimelineUndoSnapshotSegment]
    public var cursorLine: Int
    public var activeClipIndex: Int
    public var projectBoundaryTimes: [Double]
}

public struct TimelineUndoSnapshotResponse: Codable, Equatable, Sendable {
    public var fingerprint: String
    public var blockCount: Int
    public var segmentCount: Int
    public var cursorLine: Int
    public var activeClipIndex: Int
    public var projectBoundaryTimes: [Double]
}

public struct TimelineEditorSegmentRow: Codable, Equatable, Sendable {
    public var line: Int?
    public var start: Double
    public var end: Double
    public var text: String
    public var speaker: String?
    public var spk: String?
    public var isGap: Bool?
    public var sttPreviewSource: String?
    public var sttSource: String?
    public var sttSelectedSource: String?
    public var sttEnsembleSource: String?
    public var sttEnsembleLLMSelectedSource: String?
    public var score: Double?
    public var sttScore: Double?
    public var clipIndex: Int?
    public var clipFile: String?
    public var startFrame: Int?
    public var endFrame: Int?
    public var timelineStartFrame: Int?
    public var timelineEndFrame: Int?
}

public struct TimelineLiveSubtitlePreviewRequest: Codable, Equatable, Sendable {
    public var previewSegments: [TimelineEditorSegmentRow]
    public var confirmedSegments: [TimelineEditorSegmentRow]
    public var frameRate: Double
}

public struct TimelineLiveSubtitlePreviewResponse: Codable, Equatable, Sendable {
    public var drafts: [TimelineEditorSegmentRow]
}

public struct TimelineSTTSlotPart: Codable, Equatable, Sendable {
    public var source: String
    public var start: Double
    public var end: Double
    public var text: String
}

public struct TimelineSTTReplacementMeta: Codable, Equatable, Sendable {
    public var start: Double
    public var end: Double
    public var text: String
    public var line: Int?
}

public struct TimelineSTTSelectionCandidate: Codable, Equatable, Sendable {
    public var start: Double
    public var end: Double
    public var text: String
    public var source: String
    public var speaker: String
    public var score: Double
    public var sttScore: Double
    public var clipIndex: Int?
    public var clipFile: String?
    public var placementMode: String
    public var targetLine: Int?
    public var targetStart: Double?
    public var targetEnd: Double?
    public var originalCandidateStart: Double
    public var originalCandidateEnd: Double
    public var replacedSegmentCount: Int
    public var slotCandidateParts: [TimelineSTTSlotPart]
    public var slotSplitIndex: Int?
    public var slotSplitTotal: Int?
}

public struct TimelineSTTCandidateSelectionRequest: Codable, Equatable, Sendable {
    public var currentSegments: [TimelineEditorSegmentRow]
    public var livePreviewSegments: [TimelineEditorSegmentRow]
    public var candidate: TimelineEditorSegmentRow
    public var frameRate: Double
}

public struct TimelineSTTCandidateSelectionResponse: Codable, Equatable, Sendable {
    public var usedSlot: Bool
    public var slotStart: Double?
    public var slotEnd: Double?
    public var replacedSegments: [TimelineSTTReplacementMeta]
    public var selectedCandidates: [TimelineSTTSelectionCandidate]
    public var filteredPreviewSegments: [TimelineEditorSegmentRow]
    public var anchorSec: Double
    public var selectedStart: Double
    public var selectedEnd: Double
}

public struct TimelineSRTMetadataMatchSegment: Codable, Equatable, Sendable {
    public var start: Double
    public var end: Double
    public var text: String
}

public struct TimelineSRTMetadataMatchRequest: Codable, Equatable, Sendable {
    public var srtSegments: [TimelineSRTMetadataMatchSegment]
    public var projectSegments: [TimelineSRTMetadataMatchSegment]
}

public struct TimelineSRTMetadataMatchResponse: Codable, Equatable, Sendable {
    public var matches: [Int]
}

public struct TimelineEditorLoadInputSegment: Codable, Equatable, Sendable {
    public var sourceIndex: Int
    public var start: Double
    public var end: Double
    public var text: String
    public var isGap: Bool?
}

public struct TimelineEditorLoadPreparedSegment: Codable, Equatable, Sendable {
    public var sourceIndex: Int
    public var start: Double
    public var end: Double
    public var text: String
    public var parts: [String]
    public var isGap: Bool
}

public struct TimelineEditorLoadRequest: Codable, Equatable, Sendable {
    public var segments: [TimelineEditorLoadInputSegment]
    public var frameRate: Double
}

public struct TimelineEditorLoadResponse: Codable, Equatable, Sendable {
    public var segments: [TimelineEditorLoadPreparedSegment]
}

public struct TimelineDragSnapBaseSegment: Codable, Equatable, Sendable {
    public var line: Int?
    public var start: Double
    public var end: Double
    public var isGap: Bool?
    public var sttPending: Bool?
    public var liveSTTPreview: Bool?
    public var liveSubtitlePreview: Bool?
}

public struct TimelineDragSnapBaseCandidate: Codable, Equatable, Sendable {
    public var time: Double
    public var kind: String
    public var sourceLine: Int?
}

public struct TimelineDragSnapBaseRequest: Codable, Equatable, Sendable {
    public var segments: [TimelineDragSnapBaseSegment]
    public var gapSegments: [TimelineRange]
    public var vadSegments: [TimelineRange]
    public var voiceActivitySegments: [TimelineRange]
    public var boundaryTimes: [Double]
    public var scanBoundaryTimes: [Double]
    public var userGuides: [Double]
    public var roughcutRanges: [TimelineRange]
    public var totalDuration: Double
    public var frameRate: Double
    public var includeGapControls: Bool
}

public struct TimelineDragSnapBaseResponse: Codable, Equatable, Sendable {
    public var candidates: [TimelineDragSnapBaseCandidate]
}

public struct TimelineSegmentTimingEditRow: Codable, Equatable, Sendable {
    public var line: Int
    public var start: Double
    public var end: Double
    public var isGap: Bool
}

public struct TimelineSegmentTimingEditPlanRequest: Codable, Equatable, Sendable {
    public var segments: [TimelineSegmentTimingEditRow]
    public var line: Int
    public var newStart: Double
    public var newEnd: Double
    public var edge: String
    public var frameRate: Double
}

public struct TimelineSegmentTimingEditPlanResponse: Codable, Equatable, Sendable {
    public var segments: [TimelineSegmentTimingEditRow]
    public var deletedLines: [Int]
}

public enum TimelineEditing {
    public static func apply(_ request: TimelineTimingDragRequest) -> TimelineTimingDragResponse {
        switch request.edge {
        case "square_right":
            let minEnd = snapSecToFrame(request.minValue, fps: request.frameRate)
            let maxEnd = snapSecToFrame(max(request.minValue, request.maxValue), fps: request.frameRate)
            let nextEnd = clamp(
                snapSecToFrame(request.originalEnd + request.delta, fps: request.frameRate),
                lower: minEnd,
                upper: maxEnd
            )
            let snapped = snapDragTime(
                nextEnd,
                candidates: request.candidates,
                defaultThreshold: request.snapThreshold,
                minValue: minEnd,
                maxValue: maxEnd,
                fps: request.frameRate
            )
            return TimelineTimingDragResponse(
                edge: request.edge,
                end: snapped.value,
                guideTime: snapped.value,
                snappedTime: snapped.candidateTime,
                snappedKind: snapped.candidate?.kind
            )
        case "square_left":
            let minStart = snapSecToFrame(request.minValue, fps: request.frameRate)
            let maxStart = snapSecToFrame(max(request.minValue, request.maxValue), fps: request.frameRate)
            let nextStart = clamp(
                snapSecToFrame(request.originalStart + request.delta, fps: request.frameRate),
                lower: minStart,
                upper: maxStart
            )
            let snapped = snapDragTime(
                nextStart,
                candidates: request.candidates,
                defaultThreshold: request.snapThreshold,
                minValue: minStart,
                maxValue: maxStart,
                fps: request.frameRate
            )
            return TimelineTimingDragResponse(
                edge: request.edge,
                start: snapped.value,
                guideTime: snapped.value,
                snappedTime: snapped.candidateTime,
                snappedKind: snapped.candidate?.kind
            )
        case "center":
            let duration = max(0.0, snapSecToFrame(request.originalEnd - request.originalStart, fps: request.frameRate))
            let minStart = snapSecToFrame(request.minValue, fps: request.frameRate)
            let maxStart = snapSecToFrame(max(request.minValue, request.maxValue - duration), fps: request.frameRate)
            let nextStart = clamp(
                snapSecToFrame(request.originalStart + request.delta, fps: request.frameRate),
                lower: minStart,
                upper: maxStart
            )
            let snapped = snapDragSpan(
                nextStart,
                duration: duration,
                candidates: request.candidates,
                defaultThreshold: request.snapThreshold,
                minStart: minStart,
                maxEnd: request.maxValue,
                fps: request.frameRate
            )
            return TimelineTimingDragResponse(
                edge: request.edge,
                start: snapped.start,
                end: snapSecToFrame(snapped.start + duration, fps: request.frameRate),
                guideTime: snapped.guideTime,
                snappedTime: snapped.candidateTime,
                snappedKind: snapped.candidate?.kind
            )
        case "diamond":
            let minBoundary = snapSecToFrame(request.minValue, fps: request.frameRate)
            let maxBoundary = snapSecToFrame(max(request.minValue, request.maxValue), fps: request.frameRate)
            let nextBoundary = clamp(
                snapSecToFrame(request.originalEnd + request.delta, fps: request.frameRate),
                lower: minBoundary,
                upper: maxBoundary
            )
            let snapped = snapDragTime(
                nextBoundary,
                candidates: request.candidates,
                defaultThreshold: request.snapThreshold,
                minValue: minBoundary,
                maxValue: maxBoundary,
                fps: request.frameRate
            )
            return TimelineTimingDragResponse(
                edge: request.edge,
                start: snapped.value,
                end: snapped.value,
                guideTime: snapped.value,
                snappedTime: snapped.candidateTime,
                snappedKind: snapped.candidate?.kind
            )
        default:
            return TimelineTimingDragResponse(edge: request.edge)
        }
    }

    public static func mergePreview(_ request: TimelineSubtitleMergePreviewRequest) -> TimelineSubtitleMergePreviewResponse {
        let tolerance = max(0.001, 1.1 / max(1.0, request.frameRate))
        let currentStart = snapSecToFrame(request.currentStart, fps: request.frameRate)
        let currentEnd = snapSecToFrame(request.currentEnd, fps: request.frameRate)

        switch request.edge {
        case "square_left":
            guard
                let previousStart = request.previousStart,
                let previousEnd = request.previousEnd
            else {
                return TimelineSubtitleMergePreviewResponse()
            }
            let snappedPreviousStart = snapSecToFrame(previousStart, fps: request.frameRate)
            let snappedPreviousEnd = snapSecToFrame(previousEnd, fps: request.frameRate)
            if abs(currentStart - snappedPreviousStart) <= tolerance && currentEnd > snappedPreviousEnd + (tolerance * 0.5) {
                return TimelineSubtitleMergePreviewResponse(target: "previous")
            }
        case "square_right":
            guard
                let nextStart = request.nextStart,
                let nextEnd = request.nextEnd
            else {
                return TimelineSubtitleMergePreviewResponse()
            }
            let snappedNextStart = snapSecToFrame(nextStart, fps: request.frameRate)
            let snappedNextEnd = snapSecToFrame(nextEnd, fps: request.frameRate)
            if abs(currentEnd - snappedNextEnd) <= tolerance && currentStart < snappedNextStart - (tolerance * 0.5) {
                return TimelineSubtitleMergePreviewResponse(target: "next")
            }
        default:
            break
        }
        return TimelineSubtitleMergePreviewResponse()
    }

    public static func subtitleMagnet(_ request: TimelineSubtitleMagnetRequest) -> TimelineSubtitleMagnetResponse {
        let fps = max(1.0, min(240.0, request.frameRate.isFinite ? request.frameRate : 30.0))
        var rows = request.segments.filter { !($0.isGap ?? false) }.sorted {
            if $0.start == $1.start {
                return $0.end < $1.end
            }
            return $0.start < $1.start
        }
        guard rows.count >= 2 else {
            return TimelineSubtitleMagnetResponse(
                segments: rows,
                report: TimelineSubtitleMagnetReport(
                    thresholdSec: round(request.thresholdSec * 1_000) / 1_000,
                    closedPairs: 0,
                    mergedPairs: 0,
                    blocked: [:],
                    modes: [:]
                )
            )
        }

        let tolerance = max(0.001, 1.0 / fps)
        let deepGapLimit = min(request.thresholdSec, request.policy["deep_bridge_gap_sec"] ?? request.thresholdSec)
        let loraGapLimit = min(request.thresholdSec, request.policy["lora_micro_merge_gap_sec"] ?? request.thresholdSec)
        let microMinDuration = max(0.05, request.policy["lora_micro_merge_min_duration"] ?? 0.8)
        let splitThreshold = max(8.0, request.policy["split_length_threshold"] ?? 20.0)
        let microCharFloor = max(2, Int(round(splitThreshold * 0.45)))

        var blocked: [String: Int] = [:]
        var modes: [String: Int] = [:]
        var closedPairs = 0
        var affected = Set<Int>()
        let original = rows

        for index in 0..<(rows.count - 1) {
            var current = rows[index]
            let next = rows[index + 1]
            let currentFrames = magnetSegmentFrames(current, fps: fps)
            let nextFrames = magnetSegmentFrames(next, fps: fps)
            let gapFrames = nextFrames.start - currentFrames.end
            let gapSec = Double(gapFrames) / fps
            if gapFrames <= 0 {
                continue
            }
            if gapSec > request.thresholdSec + tolerance {
                blocked["threshold", default: 0] += 1
                continue
            }
            if request.speakerStrict {
                let currentSpeaker = (current.spk ?? current.speaker ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let nextSpeaker = (next.spk ?? next.speaker ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                if currentSpeaker != nextSpeaker {
                    blocked["speaker", default: 0] += 1
                    continue
                }
            }
            if boundaryBlocksGap(
                start: current.end,
                end: next.start,
                boundaries: request.boundaryTimes,
                tolerance: tolerance
            ) {
                blocked["confirmed_cut", default: 0] += 1
                continue
            }
            if boundaryBlocksGap(
                start: current.end,
                end: next.start,
                boundaries: request.provisionalBoundaries,
                tolerance: tolerance
            ) {
                blocked["provisional_cut", default: 0] += 1
                continue
            }
            if vadBlocksGap(
                start: current.end,
                end: next.start,
                vadSegments: request.vadSegments,
                tolerance: tolerance
            ) {
                blocked["voice_boundary", default: 0] += 1
                continue
            }

            let mode: String
            if gapSec <= deepGapLimit + tolerance {
                mode = "deep_bridge"
            } else if gapSec <= loraGapLimit + tolerance, isMicroSegment(current, minDuration: microMinDuration, charFloor: microCharFloor) || isMicroSegment(next, minDuration: microMinDuration, charFloor: microCharFloor) {
                mode = "lora_micro"
            } else {
                blocked["threshold", default: 0] += 1
                continue
            }

            let boundaryFrame = nextFrames.start
            current.end = secFromFrame(boundaryFrame, fps: fps)
            current.endFrame = boundaryFrame
            current.timelineEndFrame = boundaryFrame
            rows[index] = normalizeMagnetSegment(current, fps: fps)
            affected.insert(index)
            affected.insert(index + 1)
            closedPairs += 1
            modes[mode, default: 0] += 1
        }

        for idx in rows.indices {
            rows[idx].line = idx
        }
        let orderedIndices = affected.sorted()
        let snapshotBefore = orderedIndices.map { snapshotRow(original[$0], index: $0) }
        let snapshotAfter = orderedIndices.map { snapshotRow(rows[$0], index: $0) }

        return TimelineSubtitleMagnetResponse(
            segments: rows,
            report: TimelineSubtitleMagnetReport(
                thresholdSec: round(request.thresholdSec * 1_000) / 1_000,
                closedPairs: closedPairs,
                mergedPairs: closedPairs,
                blocked: blocked,
                modes: modes
            ),
            snapshotBefore: snapshotBefore,
            snapshotAfter: snapshotAfter,
            fingerprintBefore: fingerprint(for: snapshotBefore),
            fingerprintAfter: fingerprint(for: snapshotAfter)
        )
    }

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

    public static func liveSubtitlePreview(_ request: TimelineLiveSubtitlePreviewRequest) -> TimelineLiveSubtitlePreviewResponse {
        let fps = max(1.0, request.frameRate.isFinite ? request.frameRate : 30.0)
        let confirmedSegments = request.confirmedSegments.filter { !($0.isGap ?? false) }
        let filteredPreview = dropOverlappingPreviewSegments(
            request.previewSegments,
            finalSegments: confirmedSegments,
            sameSourceOnly: false
        )
        if filteredPreview.isEmpty {
            return TimelineLiveSubtitlePreviewResponse(drafts: [])
        }

        var drafts: [TimelineEditorSegmentRow] = []
        let ordered = filteredPreview.sorted {
            let startCompare = ($0.start, sourcePriority(editorSegmentSource($0)), $0.end)
            let rightCompare = ($1.start, sourcePriority(editorSegmentSource($1)), $1.end)
            return startCompare < rightCompare
        }

        for seg in ordered {
            let text = cleanWhisperText(seg.text)
            if text.isEmpty {
                continue
            }
            let start = snapSecToFrame(max(0.0, seg.start), fps: fps)
            let end = snapSecToFrame(max(start + 0.05, seg.end.isFinite ? seg.end : (start + 0.5)), fps: fps)
            let source = editorSegmentSource(seg)
            let score = normalizedSTTScore(seg)
            var draft = seg
            draft.start = start
            draft.end = end
            draft.text = text
            draft.line = -1000 - drafts.count
            draft.sttEnsembleSource = source
            draft.score = score
            draft.sttScore = score
            draft.isGap = false

            var replaceIndex: Int?
            var shouldSkip = false
            for (idx, existing) in drafts.enumerated() {
                if !segmentsOverlap(draft, existing, pad: 0.05) {
                    continue
                }
                if sourcePriority(source) < sourcePriority(editorSegmentSource(existing)) {
                    replaceIndex = idx
                } else {
                    shouldSkip = true
                }
                break
            }
            if let replaceIndex {
                drafts[replaceIndex] = draft
            } else if !shouldSkip {
                drafts.append(draft)
            }
        }

        let sortedDrafts = drafts.sorted { ($0.start, $0.end) < ($1.start, $1.end) }
        let finalized = sortedDrafts.enumerated().map { index, row -> TimelineEditorSegmentRow in
            var draft = row
            draft.line = -1000 - index
            return draft
        }
        return TimelineLiveSubtitlePreviewResponse(drafts: finalized)
    }

    public static func sttCandidateSelection(_ request: TimelineSTTCandidateSelectionRequest) -> TimelineSTTCandidateSelectionResponse {
        let fps = max(1.0, request.frameRate.isFinite ? request.frameRate : 30.0)
        let current = request.currentSegments.filter { !($0.isGap ?? false) }
        let candidateText = cleanWhisperText(request.candidate.text)
        let candidateSource = editorSegmentSource(request.candidate)
        let candidateScore = normalizedSTTScore(request.candidate)
        let safeStart = max(0.0, request.candidate.start)
        let safeEnd = max(safeStart, request.candidate.end)

        let slot = sttSelectionSlot(segments: current, candidate: request.candidate, fps: fps)
        let replacedSegments = slot?.segments ?? overlappingSegments(segments: current, candidate: request.candidate, fps: fps)

        var filteredPreviewSegments = request.livePreviewSegments
        let selectedStart: Double
        let selectedEnd: Double
        let anchorSec: Double
        let selectedCandidates: [TimelineSTTSelectionCandidate]

        if let slot {
            let slotParts = sttSlotCandidatesForSource(
                livePreviewSegments: request.livePreviewSegments,
                candidate: request.candidate,
                slotStart: slot.start,
                slotEnd: slot.end
            )
            let replacementCount = replacedSegments.count
            let baseSlotParts = slotParts.prefix(24).map {
                TimelineSTTSlotPart(
                    source: editorSegmentSource($0),
                    start: $0.start,
                    end: $0.end,
                    text: cleanWhisperText($0.text)
                )
            }
            if slotParts.count > 1 {
                selectedCandidates = slotParts.enumerated().compactMap { partIndex, part in
                    let partStart = snapSecToFrame(max(slot.start, part.start), fps: fps)
                    let partEnd = snapSecToFrame(max(partStart + 0.05, min(slot.end, part.end)), fps: fps)
                    guard partEnd > partStart else {
                        return nil
                    }
                    return TimelineSTTSelectionCandidate(
                        start: partStart,
                        end: partEnd,
                        text: cleanWhisperText(part.text),
                        source: editorSegmentSource(part),
                        speaker: editorSegmentSpeaker(part),
                        score: normalizedSTTScore(part),
                        sttScore: normalizedSTTScore(part),
                        clipIndex: part.clipIndex,
                        clipFile: part.clipFile,
                        placementMode: "manual_final_slot_replace",
                        targetLine: nil,
                        targetStart: nil,
                        targetEnd: nil,
                        originalCandidateStart: part.start,
                        originalCandidateEnd: part.end,
                        replacedSegmentCount: replacementCount,
                        slotCandidateParts: baseSlotParts,
                        slotSplitIndex: partIndex,
                        slotSplitTotal: slotParts.count
                    )
                }
            } else {
                let mergedText = slotParts.map { cleanWhisperText($0.text) }.filter { !$0.isEmpty }.joined(separator: " ")
                selectedCandidates = [
                    TimelineSTTSelectionCandidate(
                        start: snapSecToFrame(slot.start, fps: fps),
                        end: snapSecToFrame(max(slot.start + 0.05, slot.end), fps: fps),
                        text: mergedText.isEmpty ? candidateText : mergedText,
                        source: candidateSource,
                        speaker: editorSegmentSpeaker(request.candidate),
                        score: candidateScore,
                        sttScore: candidateScore,
                        clipIndex: request.candidate.clipIndex,
                        clipFile: request.candidate.clipFile,
                        placementMode: "manual_final_slot_replace",
                        targetLine: nil,
                        targetStart: nil,
                        targetEnd: nil,
                        originalCandidateStart: safeStart,
                        originalCandidateEnd: safeEnd,
                        replacedSegmentCount: replacementCount,
                        slotCandidateParts: baseSlotParts,
                        slotSplitIndex: nil,
                        slotSplitTotal: nil
                    )
                ]
            }
            selectedStart = selectedCandidates.map(\.start).min() ?? snapSecToFrame(slot.start, fps: fps)
            selectedEnd = selectedCandidates.map(\.end).max() ?? snapSecToFrame(slot.end, fps: fps)
            anchorSec = selectedStart
        } else {
            selectedCandidates = [
                TimelineSTTSelectionCandidate(
                    start: snapSecToFrame(safeStart, fps: fps),
                    end: snapSecToFrame(max(safeStart + 0.05, safeEnd), fps: fps),
                    text: candidateText,
                    source: candidateSource,
                    speaker: editorSegmentSpeaker(request.candidate),
                    score: candidateScore,
                    sttScore: candidateScore,
                    clipIndex: request.candidate.clipIndex,
                    clipFile: request.candidate.clipFile,
                    placementMode: "manual_exact_candidate_timing",
                    targetLine: nil,
                    targetStart: nil,
                    targetEnd: nil,
                    originalCandidateStart: safeStart,
                    originalCandidateEnd: safeEnd,
                    replacedSegmentCount: replacedSegments.count,
                    slotCandidateParts: [],
                    slotSplitIndex: nil,
                    slotSplitTotal: nil
                )
            ]
            selectedStart = selectedCandidates[0].start
            selectedEnd = selectedCandidates[0].end
            anchorSec = selectedStart
        }

        let hasAlternativeOverlap = request.livePreviewSegments.contains { seg in
            seg.start < selectedEnd + 0.05 &&
            seg.end > selectedStart - 0.05 &&
            editorSegmentSource(seg) != candidateSource
        }
        if hasAlternativeOverlap {
            filteredPreviewSegments = request.livePreviewSegments.filter { seg in
                let overlaps = seg.start < selectedEnd + 0.05 && seg.end > selectedStart - 0.05
                return !(overlaps && editorSegmentSource(seg) == candidateSource)
            }
        }

        return TimelineSTTCandidateSelectionResponse(
            usedSlot: slot != nil,
            slotStart: slot?.start,
            slotEnd: slot?.end,
            replacedSegments: replacedSegments.map {
                TimelineSTTReplacementMeta(
                    start: round(max(0.0, $0.start) * 1_000_000) / 1_000_000,
                    end: round(max(0.0, $0.end) * 1_000_000) / 1_000_000,
                    text: $0.text,
                    line: $0.line
                )
            },
            selectedCandidates: selectedCandidates,
            filteredPreviewSegments: filteredPreviewSegments,
            anchorSec: anchorSec,
            selectedStart: selectedStart,
            selectedEnd: selectedEnd
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

    public static func dragSnapBase(_ request: TimelineDragSnapBaseRequest) -> TimelineDragSnapBaseResponse {
        let fps = max(1.0, request.frameRate.isFinite ? request.frameRate : 30.0)
        let total = max(0.0, request.totalDuration.isFinite ? request.totalDuration : 0.0)
        var deduped: [Double: TimelineDragSnapBaseCandidate] = [:]

        func insertCandidate(_ sec: Double, kind: String, sourceLine: Int? = nil) {
            guard sec.isFinite else { return }
            let snapped = snapSecToFrame(sec, fps: fps)
            guard snapped >= 0.0 else { return }
            if total > 0.0, snapped > total {
                return
            }
            let candidate = TimelineDragSnapBaseCandidate(time: snapped, kind: kind, sourceLine: sourceLine)
            if let existing = deduped[snapped] {
                if snapCandidatePriority(kind) > snapCandidatePriority(existing.kind) {
                    deduped[snapped] = candidate
                }
            } else {
                deduped[snapped] = candidate
            }
        }

        for seg in request.segments {
            if seg.isGap ?? false {
                continue
            }
            if seg.sttPending ?? false || seg.liveSTTPreview ?? false || seg.liveSubtitlePreview ?? false {
                continue
            }
            insertCandidate(seg.start, kind: "subtitle", sourceLine: seg.line)
            insertCandidate(seg.end, kind: "subtitle", sourceLine: seg.line)
        }

        if request.includeGapControls {
            for gap in request.gapSegments {
                insertCandidate(gap.start, kind: "gap")
                insertCandidate(gap.end, kind: "gap")
            }
        }

        for vad in request.vadSegments {
            insertCandidate(vad.start, kind: "vad")
            insertCandidate(vad.end, kind: "vad")
        }
        for item in request.voiceActivitySegments {
            insertCandidate(item.start, kind: "voice_activity")
            insertCandidate(item.end, kind: "voice_activity")
        }
        for sec in request.boundaryTimes {
            insertCandidate(sec, kind: "cut_official")
        }
        for sec in request.scanBoundaryTimes {
            insertCandidate(sec, kind: "cut_temporary")
        }
        for sec in request.userGuides {
            insertCandidate(sec, kind: "user_guide")
        }
        for marker in request.roughcutRanges {
            insertCandidate(marker.start, kind: "roughcut")
            insertCandidate(marker.end, kind: "roughcut")
        }
        insertCandidate(0.0, kind: "timeline")
        insertCandidate(total, kind: "timeline")

        let candidates = deduped.values.sorted {
            if $0.time == $1.time {
                return snapCandidatePriority($0.kind) > snapCandidatePriority($1.kind)
            }
            return $0.time < $1.time
        }
        return TimelineDragSnapBaseResponse(candidates: candidates)
    }

    public static func segmentTimingEditPlan(_ request: TimelineSegmentTimingEditPlanRequest) -> TimelineSegmentTimingEditPlanResponse {
        let fps = max(1.0, request.frameRate.isFinite ? request.frameRate : 30.0)
        let minSpan = max(0.02, min(0.1, 1.0 / max(1.0, fps)))
        let eps = 0.001

        var rows = request.segments.map { row in
            let start = snapSecToFrame(max(0.0, row.start), fps: fps)
            var end = snapSecToFrame(max(start, row.end.isFinite ? row.end : start), fps: fps)
            if end <= start {
                end = snapSecToFrame(start + minSpan, fps: fps)
            }
            return TimelineSegmentTimingEditRow(
                line: row.line,
                start: start,
                end: end,
                isGap: row.isGap
            )
        }

        guard let anchorIndex = rows.firstIndex(where: { $0.line == request.line }) else {
            return TimelineSegmentTimingEditPlanResponse(segments: rows, deletedLines: [])
        }

        let oldStart = rows[anchorIndex].start
        let oldEnd = rows[anchorIndex].end
        let newStart = snapSecToFrame(max(0.0, request.newStart), fps: fps)
        var newEnd = snapSecToFrame(max(newStart, request.newEnd.isFinite ? request.newEnd : newStart), fps: fps)
        if newEnd <= newStart {
            newEnd = snapSecToFrame(newStart + minSpan, fps: fps)
        }

        rows[anchorIndex].start = newStart
        rows[anchorIndex].end = newEnd

        let trimPreviousSubtitles = (request.edge == "square_left" || request.edge == "center") && newStart < oldStart - eps
        let trimNextSubtitles = (request.edge == "square_right" || request.edge == "center") && newEnd > oldEnd + eps
        var deletedLines = Set<Int>()

        var prevIndex = anchorIndex - 1
        while prevIndex >= 0 {
            let prev = rows[prevIndex]
            if deletedLines.contains(prev.line) {
                prevIndex -= 1
                continue
            }
            if prev.isGap {
                if request.edge == "gap" {
                    break
                }
                if prev.end <= newStart + eps {
                    break
                }
                if newStart <= prev.start + 0.05 {
                    deletedLines.insert(prev.line)
                    prevIndex -= 1
                    continue
                }
                rows[prevIndex].end = snapSecToFrame(newStart, fps: fps)
                break
            }
            if !trimPreviousSubtitles || prev.end <= newStart + eps {
                break
            }
            if newStart <= prev.start + minSpan {
                deletedLines.insert(prev.line)
                prevIndex -= 1
                continue
            }
            rows[prevIndex].end = snapSecToFrame(newStart, fps: fps)
            break
        }

        var nextIndex = anchorIndex + 1
        while nextIndex < rows.count {
            let next = rows[nextIndex]
            if deletedLines.contains(next.line) {
                nextIndex += 1
                continue
            }
            if next.isGap {
                if request.edge == "gap" {
                    break
                }
                if next.start >= newEnd - eps {
                    break
                }
                if newEnd >= next.end - 0.05 {
                    deletedLines.insert(next.line)
                    nextIndex += 1
                    continue
                }
                rows[nextIndex].start = snapSecToFrame(newEnd, fps: fps)
                break
            }
            if !trimNextSubtitles || next.start >= newEnd - eps {
                break
            }
            if newEnd >= next.end - minSpan {
                deletedLines.insert(next.line)
                nextIndex += 1
                continue
            }
            rows[nextIndex].start = snapSecToFrame(newEnd, fps: fps)
            break
        }

        return TimelineSegmentTimingEditPlanResponse(
            segments: rows.filter { !deletedLines.contains($0.line) },
            deletedLines: deletedLines.sorted()
        )
    }

    private static func cleanWhisperText(_ text: String) -> String {
        let pattern = #"<\|[^|>\n\r]{1,80}\|>"#
        let regex = try? NSRegularExpression(pattern: pattern, options: [])
        let source = text.replacingOccurrences(of: "\u{2028}", with: "\n")
        let fullRange = NSRange(source.startIndex..<source.endIndex, in: source)
        let cleaned = regex?.stringByReplacingMatches(in: source, options: [], range: fullRange, withTemplate: " ") ?? source
        let collapsedSpaces = cleaned.replacingOccurrences(of: #"[ \t]+"#, with: " ", options: .regularExpression)
        let collapsedAroundNewline = collapsedSpaces.replacingOccurrences(of: #" *\n *"#, with: "\n", options: .regularExpression)
        let collapsedNewlines = collapsedAroundNewline.replacingOccurrences(of: #"\n{3,}"#, with: "\n\n", options: .regularExpression)
        return collapsedNewlines.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func cleanEditorLoadText(_ text: String) -> String {
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

    private static func regexReplace(_ source: String, pattern: String, replacement: String) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: []) else {
            return source
        }
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        return regex.stringByReplacingMatches(in: source, options: [], range: range, withTemplate: replacement)
    }

    private static func normalizedSegmentText(_ text: String) -> String {
        regexReplace(text.trimmingCharacters(in: .whitespacesAndNewlines), pattern: #"\s+"#, replacement: " ")
    }

    private static func metadataMatchScore(
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

    private static func editorSegmentSource(_ seg: TimelineEditorSegmentRow) -> String {
        let source = seg.sttPreviewSource
            ?? seg.sttSource
            ?? seg.sttSelectedSource
            ?? seg.sttEnsembleLLMSelectedSource
            ?? seg.sttEnsembleSource
            ?? "STT1"
        let normalized = source.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        return normalized.isEmpty ? "STT1" : normalized
    }

    private static func editorSegmentSpeaker(_ seg: TimelineEditorSegmentRow) -> String {
        let speaker = seg.speaker ?? seg.spk ?? "00"
        let normalized = speaker.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? "00" : normalized
    }

    private static func normalizedSTTScore(_ seg: TimelineEditorSegmentRow) -> Double {
        let raw = seg.sttScore ?? seg.score ?? 98.0
        let normalized = raw > 1.0 ? raw : raw * 100.0
        return max(0.0, min(100.0, normalized.isFinite ? normalized : 98.0))
    }

    private static func sourcePriority(_ source: String) -> Int {
        switch source {
        case "STT1":
            return 0
        case "STT", "":
            return 1
        case "STT2":
            return 2
        default:
            return 3
        }
    }

    private static func segmentsOverlap(
        _ left: TimelineEditorSegmentRow,
        _ right: TimelineEditorSegmentRow,
        pad: Double = 0.001
    ) -> Bool {
        left.start < right.end + pad && left.end > right.start - pad
    }

    private static func dropOverlappingPreviewSegments(
        _ previewSegments: [TimelineEditorSegmentRow],
        finalSegments: [TimelineEditorSegmentRow],
        sameSourceOnly: Bool
    ) -> [TimelineEditorSegmentRow] {
        if previewSegments.isEmpty || finalSegments.isEmpty {
            return previewSegments
        }
        let ranges = finalSegments.compactMap { seg -> (Double, Double, String)? in
            let source = editorSegmentSource(seg)
            return (seg.start, seg.end, source)
        }
        if ranges.isEmpty {
            return previewSegments
        }
        return previewSegments.filter { seg in
            let source = editorSegmentSource(seg)
            let overlaps = ranges.contains { range in
                let sourceMatches = !sameSourceOnly || range.2.isEmpty || source.isEmpty || range.2 == source
                return sourceMatches && seg.start < range.1 + 0.05 && seg.end > range.0 - 0.05
            }
            return !overlaps
        }
    }

    private static func segmentOverlapsTimeRange(
        _ seg: TimelineEditorSegmentRow,
        start: Double,
        end: Double,
        pad: Double = 0.001
    ) -> Bool {
        seg.start < end - pad && seg.end > start + pad
    }

    private static func bestFinalSegmentForSTTCandidate(
        segments: [TimelineEditorSegmentRow],
        candidate: TimelineEditorSegmentRow,
        fps: Double
    ) -> TimelineEditorSegmentRow? {
        let candStart = candidate.start
        let candEnd = candidate.end
        if candEnd <= candStart {
            return nil
        }
        let candDuration = max(0.001, candEnd - candStart)
        let candCenter = (candStart + candEnd) / 2.0
        let edgeTolerance = max(0.18, min(0.45, 6.0 / max(1.0, fps)))
        var bestSegment: TimelineEditorSegmentRow?
        var bestScore = 0.0

        for seg in segments where !(seg.isGap ?? false) && seg.end > seg.start {
            let segDuration = max(0.001, seg.end - seg.start)
            let overlap = max(0.0, min(seg.end, candEnd) - max(seg.start, candStart))
            let centerBonus = (seg.start - edgeTolerance <= candCenter && candCenter <= seg.end + edgeTolerance) ? 1.0 : 0.0
            var edgeBonus = 0.0
            if abs(candStart - seg.start) <= edgeTolerance {
                edgeBonus += 0.5
            }
            if abs(candEnd - seg.end) <= edgeTolerance {
                edgeBonus += 0.5
            }
            if overlap <= 0.0 && centerBonus <= 0.0 {
                continue
            }
            let score = (overlap / candDuration) * 0.55
                + (overlap / segDuration) * 0.30
                + centerBonus * 0.10
                + edgeBonus * 0.05
            if score > bestScore {
                bestScore = score
                bestSegment = seg
            }
        }

        return bestScore >= 0.35 ? bestSegment : nil
    }

    private static func overlappingSegments(
        segments: [TimelineEditorSegmentRow],
        candidate: TimelineEditorSegmentRow,
        fps: Double
    ) -> [TimelineEditorSegmentRow] {
        let candStart = snapSecToFrame(max(0.0, candidate.start), fps: fps)
        let candEnd = snapSecToFrame(max(candStart, candidate.end), fps: fps)
        return segments.filter { segmentOverlapsTimeRange($0, start: candStart, end: candEnd) }
    }

    private static func sttSelectionSlot(
        segments: [TimelineEditorSegmentRow],
        candidate: TimelineEditorSegmentRow,
        fps: Double
    ) -> (start: Double, end: Double, segments: [TimelineEditorSegmentRow])? {
        let target = bestFinalSegmentForSTTCandidate(segments: segments, candidate: candidate, fps: fps)
        let candStart = snapSecToFrame(max(0.0, candidate.start), fps: fps)
        let candEnd = snapSecToFrame(max(candStart, candidate.end), fps: fps)
        if candEnd <= candStart {
            return nil
        }
        let edgeTolerance = max(0.12, min(0.35, 4.0 / max(1.0, fps)))
        var selected: [TimelineEditorSegmentRow] = []
        for seg in segments where !(seg.isGap ?? false) && seg.end > seg.start {
            let start = snapSecToFrame(seg.start, fps: fps)
            let end = snapSecToFrame(seg.end, fps: fps)
            let overlap = max(0.0, min(end, candEnd) - max(start, candStart))
            if overlap <= 0.0 {
                continue
            }
            let sameTarget = target != nil
                && (seg.line ?? -999999) == (target?.line ?? -888888)
                && abs(seg.start - (target?.start ?? 0.0)) < 0.05
            let meaningful = overlap >= min(max(0.001, end - start), max(0.001, candEnd - candStart)) * 0.35
            if sameTarget || overlap >= edgeTolerance || meaningful {
                selected.append(seg)
            }
        }
        if let target,
           !selected.contains(where: { abs($0.start - target.start) < 0.05 && abs($0.end - target.end) < 0.05 }) {
            selected.append(target)
        }
        if selected.isEmpty {
            return nil
        }
        selected.sort { ($0.start, $0.end) < ($1.start, $1.end) }
        let slotStart = snapSecToFrame(selected.map(\.start).min() ?? candStart, fps: fps)
        let slotEnd = snapSecToFrame(selected.map(\.end).max() ?? candEnd, fps: fps)
        if slotEnd <= slotStart {
            return nil
        }
        return (slotStart, slotEnd, selected)
    }

    private static func sttSlotCandidatesForSource(
        livePreviewSegments: [TimelineEditorSegmentRow],
        candidate: TimelineEditorSegmentRow,
        slotStart: Double,
        slotEnd: Double
    ) -> [TimelineEditorSegmentRow] {
        let source = editorSegmentSource(candidate)
        var rows = livePreviewSegments.filter {
            editorSegmentSource($0) == source && $0.start < slotEnd + 0.05 && $0.end > slotStart - 0.05
        }
        if rows.isEmpty {
            rows = [candidate]
        }
        var seen = Set<String>()
        var deduped: [TimelineEditorSegmentRow] = []
        for row in rows.sorted(by: { ($0.start, $0.end) < ($1.start, $1.end) }) {
            var updated = row
            updated.text = cleanWhisperText(updated.text)
            if updated.text.isEmpty {
                continue
            }
            let key = "\(round(updated.start * 1_000) / 1_000)|\(round(updated.end * 1_000) / 1_000)|\(updated.text)"
            if seen.contains(key) {
                continue
            }
            seen.insert(key)
            deduped.append(updated)
        }
        return deduped
    }

    private static func snapDragTime(
        _ value: Double,
        candidates: [TimelineTimingDragCandidate],
        defaultThreshold: Double,
        minValue: Double,
        maxValue: Double,
        fps: Double
    ) -> (value: Double, candidateTime: Double?, candidate: TimelineTimingDragCandidate?) {
        let snappedValue = snapSecToFrame(value, fps: fps)
        let lower = snapSecToFrame(minValue, fps: fps)
        let upper = snapSecToFrame(max(minValue, maxValue), fps: fps)
        var bestCandidate: TimelineTimingDragCandidate?
        var bestCandidateTime: Double?
        var bestDistance = Double.infinity

        for candidate in candidates {
            let candidateTime = snapSecToFrame(candidate.time, fps: fps)
            guard candidateTime >= lower, candidateTime <= upper else {
                continue
            }
            let distance = abs(candidateTime - snappedValue)
            let threshold = max(0.0, candidate.threshold ?? defaultThreshold)
            if distance <= threshold, distance < bestDistance {
                bestCandidate = candidate
                bestCandidateTime = candidateTime
                bestDistance = distance
            }
        }

        if let bestCandidate, let bestCandidateTime {
            return (bestCandidateTime, bestCandidateTime, bestCandidate)
        }
        return (clamp(snappedValue, lower: lower, upper: upper), nil, nil)
    }

    private static func snapDragSpan(
        _ start: Double,
        duration: Double,
        candidates: [TimelineTimingDragCandidate],
        defaultThreshold: Double,
        minStart: Double,
        maxEnd: Double,
        fps: Double
    ) -> (start: Double, guideTime: Double, candidateTime: Double?, candidate: TimelineTimingDragCandidate?) {
        let snappedDuration = max(0.0, snapSecToFrame(duration, fps: fps))
        let lower = snapSecToFrame(minStart, fps: fps)
        let upper = snapSecToFrame(max(minStart, maxEnd - snappedDuration), fps: fps)
        let clampedStart = clamp(snapSecToFrame(start, fps: fps), lower: lower, upper: upper)
        let anchors = [
            ("start", clampedStart),
            ("end", snapSecToFrame(clampedStart + snappedDuration, fps: fps)),
        ]

        var bestCandidate: TimelineTimingDragCandidate?
        var bestCandidateTime: Double?
        var bestStart = clampedStart
        var bestGuideTime = clampedStart
        var bestDistance = Double.infinity

        for (anchorName, anchorTime) in anchors {
            for candidate in candidates {
                let candidateTime = snapSecToFrame(candidate.time, fps: fps)
                let nextStart = anchorName == "start"
                    ? candidateTime
                    : snapSecToFrame(candidateTime - snappedDuration, fps: fps)
                guard nextStart >= lower, nextStart <= upper else {
                    continue
                }
                let distance = abs(candidateTime - anchorTime)
                let threshold = max(0.0, candidate.threshold ?? defaultThreshold)
                if distance <= threshold, distance < bestDistance {
                    bestCandidate = candidate
                    bestCandidateTime = candidateTime
                    bestStart = nextStart
                    bestGuideTime = candidateTime
                    bestDistance = distance
                }
            }
        }

        if let bestCandidate, let bestCandidateTime {
            return (snapSecToFrame(bestStart, fps: fps), snapSecToFrame(bestGuideTime, fps: fps), bestCandidateTime, bestCandidate)
        }
        return (clampedStart, clampedStart, nil, nil)
    }

    private static func snapSecToFrame(_ sec: Double, fps: Double) -> Double {
        let normalizedFPS = max(1.0, min(240.0, fps.isFinite ? fps : 30.0))
        let clampedSec = max(0.0, sec.isFinite ? sec : 0.0)
        let frame = Int(floor(clampedSec * normalizedFPS + 1e-6))
        return round((Double(frame) / normalizedFPS) * 1_000_000) / 1_000_000
    }

    private static func clamp(_ value: Double, lower: Double, upper: Double) -> Double {
        let safeLower = min(lower, upper)
        let safeUpper = max(lower, upper)
        return max(safeLower, min(value, safeUpper))
    }

    private static func magnetSegmentFrames(_ segment: TimelineSubtitleMagnetSegment, fps: Double) -> (start: Int, end: Int) {
        let start = segment.timelineStartFrame ?? segment.startFrame ?? frameIndex(segment.start, fps: fps)
        let endRaw = segment.timelineEndFrame ?? segment.endFrame ?? frameIndex(segment.end, fps: fps)
        let end = max(start + 1, endRaw)
        return (start, end)
    }

    private static func frameIndex(_ sec: Double, fps: Double) -> Int {
        let normalizedFPS = max(1.0, min(240.0, fps.isFinite ? fps : 30.0))
        let clampedSec = max(0.0, sec.isFinite ? sec : 0.0)
        return Int((clampedSec * normalizedFPS).rounded())
    }

    private static func secFromFrame(_ frame: Int, fps: Double) -> Double {
        let normalizedFPS = max(1.0, min(240.0, fps.isFinite ? fps : 30.0))
        return round((Double(max(0, frame)) / normalizedFPS) * 1_000_000) / 1_000_000
    }

    private static func boundaryBlocksGap(start: Double, end: Double, boundaries: [Double], tolerance: Double) -> Bool {
        let low = min(start, end) - max(0.0, tolerance)
        let high = max(start, end) + max(0.0, tolerance)
        for value in boundaries {
            let point = max(0.0, value)
            if point >= low && point <= high {
                return true
            }
        }
        return false
    }

    private static func vadBlocksGap(start: Double, end: Double, vadSegments: [TimelineSubtitleMagnetVADSegment], tolerance: Double) -> Bool {
        let innerLow = min(start, end) + max(0.0, tolerance)
        let innerHigh = max(start, end) - max(0.0, tolerance)
        if innerHigh <= innerLow {
            return false
        }
        for item in vadSegments {
            let segStart = max(0.0, item.start)
            let segEnd = max(segStart, item.end)
            if segEnd <= innerLow || segStart >= innerHigh {
                continue
            }
            return true
        }
        return false
    }

    private static func isMicroSegment(_ segment: TimelineSubtitleMagnetSegment, minDuration: Double, charFloor: Int) -> Bool {
        let duration = max(0.0, segment.end - segment.start)
        let compactLength = segment.text.replacingOccurrences(of: "\\s+", with: "", options: .regularExpression).count
        return duration < minDuration || compactLength <= charFloor
    }

    private static func normalizeMagnetSegment(_ segment: TimelineSubtitleMagnetSegment, fps: Double) -> TimelineSubtitleMagnetSegment {
        var updated = segment
        let frames = magnetSegmentFrames(updated, fps: fps)
        updated.start = secFromFrame(frames.start, fps: fps)
        updated.end = secFromFrame(frames.end, fps: fps)
        updated.startFrame = frames.start
        updated.endFrame = frames.end
        updated.timelineStartFrame = frames.start
        updated.timelineEndFrame = frames.end
        return updated
    }

    private static func snapshotRow(_ segment: TimelineSubtitleMagnetSegment, index: Int) -> TimelineSubtitleMagnetSnapshotRow {
        TimelineSubtitleMagnetSnapshotRow(
            index: index,
            line: segment.line ?? index,
            start: round(max(0.0, segment.start) * 1_000_000) / 1_000_000,
            end: round(max(0.0, segment.end) * 1_000_000) / 1_000_000,
            text: segment.text,
            spk: segment.spk ?? segment.speaker ?? ""
        )
    }

    private static func snapCandidatePriority(_ kind: String) -> Int {
        switch kind {
        case "user_guide":
            return 13
        case "cut_official":
            return 12
        case "cut_temporary":
            return 11
        case "subtitle":
            return 10
        case "stt1", "stt2":
            return 9
        case "voice_activity", "gap":
            return 8
        case "vad":
            return 7
        case "roughcut":
            return 6
        case "timeline":
            return 5
        default:
            return 0
        }
    }

    private static func fingerprint<T: Encodable>(for value: T) -> String? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        guard let data = try? encoder.encode(value) else {
            return nil
        }
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private static func fingerprintDictionary(_ value: [String: AnyEncodable]) -> String? {
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
