import Foundation

extension TimelineEditing {
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

    static func snapDragTime(
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

    static func snapDragSpan(
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

    static func snapSecToFrame(_ sec: Double, fps: Double) -> Double {
        let normalizedFPS = max(1.0, min(240.0, fps.isFinite ? fps : 30.0))
        let clampedSec = max(0.0, sec.isFinite ? sec : 0.0)
        let frame = Int(floor(clampedSec * normalizedFPS + 1e-6))
        return round((Double(frame) / normalizedFPS) * 1_000_000) / 1_000_000
    }

    static func clamp(_ value: Double, lower: Double, upper: Double) -> Double {
        let safeLower = min(lower, upper)
        let safeUpper = max(lower, upper)
        return max(safeLower, min(value, safeUpper))
    }

    static func snapCandidatePriority(_ kind: String) -> Int {
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
}
