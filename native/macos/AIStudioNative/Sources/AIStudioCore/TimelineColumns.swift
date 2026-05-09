import Foundation

public struct TimelineRange: Codable, Equatable, Sendable {
    public var start: Double
    public var end: Double

    public init(start: Double, end: Double) {
        self.start = start
        self.end = end
    }
}

public struct TimelineWaveformColumns: Codable, Equatable, Sendable {
    public var heights: [Int]
    public var speech: [Bool]

    public init(heights: [Int], speech: [Bool]) {
        self.heights = heights
        self.speech = speech
    }
}

public struct TimelineSegmentLayoutInput: Codable, Equatable, Sendable {
    public var id: String?
    public var line: Int?
    public var start: Double
    public var end: Double
    public var lane: Int?
    public var isGap: Bool
    public var isPending: Bool

    public init(
        id: String? = nil,
        line: Int? = nil,
        start: Double,
        end: Double,
        lane: Int? = nil,
        isGap: Bool = false,
        isPending: Bool = false
    ) {
        self.id = id
        self.line = line
        self.start = start
        self.end = end
        self.lane = lane
        self.isGap = isGap
        self.isPending = isPending
    }
}

public struct TimelineSegmentLayoutRequest: Codable, Equatable, Sendable {
    public var segments: [TimelineSegmentLayoutInput]
    public var viewStart: Double
    public var viewEnd: Double
    public var width: Int
    public var top: Int
    public var rowHeight: Int
    public var laneGap: Int
    public var minWidth: Int
    public var padSec: Double
    public var playheadSec: Double?

    public init(
        segments: [TimelineSegmentLayoutInput],
        viewStart: Double,
        viewEnd: Double,
        width: Int,
        top: Int = 0,
        rowHeight: Int = 22,
        laneGap: Int = 2,
        minWidth: Int = 2,
        padSec: Double = 0.0,
        playheadSec: Double? = nil
    ) {
        self.segments = segments
        self.viewStart = viewStart
        self.viewEnd = viewEnd
        self.width = width
        self.top = top
        self.rowHeight = rowHeight
        self.laneGap = laneGap
        self.minWidth = minWidth
        self.padSec = padSec
        self.playheadSec = playheadSec
    }
}

public struct TimelineSegmentLayout: Codable, Equatable, Sendable {
    public var index: Int
    public var id: String?
    public var line: Int?
    public var x: Int
    public var width: Int
    public var clippedX: Int
    public var clippedWidth: Int
    public var y: Int
    public var height: Int
    public var lane: Int
    public var isActive: Bool
    public var isGap: Bool
    public var isPending: Bool

    public init(
        index: Int,
        id: String?,
        line: Int?,
        x: Int,
        width: Int,
        clippedX: Int,
        clippedWidth: Int,
        y: Int,
        height: Int,
        lane: Int,
        isActive: Bool,
        isGap: Bool,
        isPending: Bool
    ) {
        self.index = index
        self.id = id
        self.line = line
        self.x = x
        self.width = width
        self.clippedX = clippedX
        self.clippedWidth = clippedWidth
        self.y = y
        self.height = height
        self.lane = lane
        self.isActive = isActive
        self.isGap = isGap
        self.isPending = isPending
    }
}

public struct TimelineSegmentLayoutResponse: Codable, Equatable, Sendable {
    public var layouts: [TimelineSegmentLayout]
    public var visibleCount: Int

    public init(layouts: [TimelineSegmentLayout]) {
        self.layouts = layouts
        self.visibleCount = layouts.count
    }
}

public struct TimelinePlayheadDirtyRequest: Codable, Equatable, Sendable {
    public var oldSec: Double?
    public var newSec: Double
    public var viewStart: Double
    public var viewEnd: Double
    public var width: Int
    public var height: Int
    public var extraPx: Int

    public init(
        oldSec: Double?,
        newSec: Double,
        viewStart: Double,
        viewEnd: Double,
        width: Int,
        height: Int,
        extraPx: Int = 12
    ) {
        self.oldSec = oldSec
        self.newSec = newSec
        self.viewStart = viewStart
        self.viewEnd = viewEnd
        self.width = width
        self.height = height
        self.extraPx = extraPx
    }
}

public struct TimelinePlayheadDirtyRect: Codable, Equatable, Sendable {
    public var x: Int
    public var left: Int
    public var top: Int
    public var width: Int
    public var height: Int

    public init(x: Int, left: Int, top: Int, width: Int, height: Int) {
        self.x = x
        self.left = left
        self.top = top
        self.width = width
        self.height = height
    }
}

public enum TimelineColumns {
    public static func buildWaveformColumns(
        waveform: [Float],
        width: Int,
        totalDuration: Double,
        vadSegments: [TimelineRange] = [],
        maxHeight: Int = 14
    ) -> TimelineWaveformColumns {
        guard width > 0, !waveform.isEmpty else {
            return TimelineWaveformColumns(heights: [], speech: [])
        }

        let wfLen = waveform.count
        let speechRanges = buildSpeechRanges(
            vadSegments,
            waveformLength: wfLen,
            totalDuration: totalDuration
        )

        var heights: [Int] = []
        var speech: [Bool] = []
        heights.reserveCapacity(width)
        speech.reserveCapacity(width)

        var rangeIndex = 0
        let denominator = max(1, width)
        for x in 0..<width {
            let idx = min(wfLen - 1, Int((Double(x) / Double(denominator)) * Double(wfLen)))
            while rangeIndex < speechRanges.count && idx >= speechRanges[rangeIndex].1 {
                rangeIndex += 1
            }
            let inSpeech = rangeIndex < speechRanges.count
                && speechRanges[rangeIndex].0 <= idx
                && idx < speechRanges[rangeIndex].1
            let amp = waveform[idx].isFinite ? max(0, Float(abs(waveform[idx]))) : 0
            heights.append(max(1, Int(amp * Float(maxHeight))))
            speech.append(inSpeech)
        }

        return TimelineWaveformColumns(heights: heights, speech: speech)
    }

    private static func buildSpeechRanges(
        _ vadSegments: [TimelineRange],
        waveformLength: Int,
        totalDuration: Double
    ) -> [(Int, Int)] {
        guard waveformLength > 0, !vadSegments.isEmpty else { return [] }
        let scale = totalDuration > 0 ? Double(waveformLength) / totalDuration : 100.0
        var ranges: [(Int, Int)] = []
        ranges.reserveCapacity(vadSegments.count)
        for segment in vadSegments {
            let start = max(0, Int(segment.start * scale))
            let end = min(waveformLength, Int(segment.end * scale) + 1)
            if end > start {
                ranges.append((start, end))
            }
        }
        ranges.sort { left, right in
            if left.0 == right.0 {
                return left.1 < right.1
            }
            return left.0 < right.0
        }
        return ranges
    }
}

public enum TimelineLayout {
    public static func segmentLayouts(_ request: TimelineSegmentLayoutRequest) -> TimelineSegmentLayoutResponse {
        let canvasWidth = max(0, request.width)
        guard canvasWidth > 0 else {
            return TimelineSegmentLayoutResponse(layouts: [])
        }

        let viewStart = min(request.viewStart, request.viewEnd)
        let viewEnd = max(request.viewStart, request.viewEnd)
        let span = max(0.001, viewEnd - viewStart)
        let pixelsPerSecond = Double(canvasWidth) / span
        let pad = max(0.0, request.padSec)
        let visibleStart = max(0.0, viewStart - pad)
        let visibleEnd = viewEnd + pad
        let rowHeight = max(1, request.rowHeight)
        let laneGap = max(0, request.laneGap)
        let minWidth = max(1, request.minWidth)

        var layouts: [TimelineSegmentLayout] = []
        layouts.reserveCapacity(min(request.segments.count, 512))

        for (index, segment) in request.segments.enumerated() {
            let start = min(segment.start, segment.end)
            let end = max(segment.start, segment.end)
            guard end >= visibleStart && start <= visibleEnd else {
                continue
            }

            let x = Int(floor((start - viewStart) * pixelsPerSecond))
            let rawWidth = Int(ceil(max(0.0, end - start) * pixelsPerSecond))
            let segmentWidth = max(minWidth, rawWidth)
            let clippedLeft = max(0, x)
            let clippedRight = min(canvasWidth, max(x + segmentWidth, x + minWidth))
            let clippedWidth = max(1, clippedRight - clippedLeft)
            let lane = max(0, segment.lane ?? 0)
            let y = request.top + lane * (rowHeight + laneGap)
            let active = request.playheadSec.map { sec in
                sec >= start && sec <= end
            } ?? false

            layouts.append(TimelineSegmentLayout(
                index: index,
                id: segment.id,
                line: segment.line,
                x: x,
                width: segmentWidth,
                clippedX: clippedLeft,
                clippedWidth: clippedWidth,
                y: y,
                height: rowHeight,
                lane: lane,
                isActive: active,
                isGap: segment.isGap,
                isPending: segment.isPending
            ))
        }

        return TimelineSegmentLayoutResponse(layouts: layouts)
    }

    public static func playheadDirtyRect(_ request: TimelinePlayheadDirtyRequest) -> TimelinePlayheadDirtyRect {
        let canvasWidth = max(1, request.width)
        let canvasHeight = max(1, request.height)
        let viewStart = min(request.viewStart, request.viewEnd)
        let viewEnd = max(request.viewStart, request.viewEnd)
        let span = max(0.001, viewEnd - viewStart)
        let pixelsPerSecond = Double(canvasWidth) / span
        let newX = clampPixel(Int(round((request.newSec - viewStart) * pixelsPerSecond)), width: canvasWidth)
        let oldX = request.oldSec.map {
            clampPixel(Int(round(($0 - viewStart) * pixelsPerSecond)), width: canvasWidth)
        } ?? newX
        let extra = max(1, request.extraPx)
        let left = max(0, min(oldX, newX) - extra)
        let right = min(canvasWidth, max(oldX, newX) + extra + 1)
        return TimelinePlayheadDirtyRect(
            x: newX,
            left: left,
            top: 0,
            width: max(1, right - left),
            height: canvasHeight
        )
    }

    private static func clampPixel(_ value: Int, width: Int) -> Int {
        min(max(0, value), max(0, width - 1))
    }
}
