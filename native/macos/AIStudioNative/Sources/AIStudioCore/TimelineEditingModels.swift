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
    public var speaker: String?
    public var speaker2: String?
    public var speakerList: [String]?
}

public struct TimelineEditorLoadPreparedSegment: Codable, Equatable, Sendable {
    public var sourceIndex: Int
    public var start: Double
    public var end: Double
    public var text: String
    public var parts: [String]
    public var isGap: Bool
}

public struct TimelineEditorLoadPreparedBlock: Codable, Equatable, Sendable {
    public var blockIndex: Int
    public var sourceIndex: Int
    public var start: Double
    public var end: Double
    public var text: String
    public var isGap: Bool
}

public struct TimelineEditorLoadRequest: Codable, Equatable, Sendable {
    public var segments: [TimelineEditorLoadInputSegment]
    public var frameRate: Double
}

public struct TimelineEditorLoadResponse: Codable, Equatable, Sendable {
    public var segments: [TimelineEditorLoadPreparedSegment]
    public var blocks: [TimelineEditorLoadPreparedBlock]
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
