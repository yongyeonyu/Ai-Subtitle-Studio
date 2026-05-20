import Foundation

extension TimelineEditing {
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
            } else if gapSec <= loraGapLimit + tolerance,
                      isMicroSegment(current, minDuration: microMinDuration, charFloor: microCharFloor)
                        || isMicroSegment(next, minDuration: microMinDuration, charFloor: microCharFloor) {
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

    static func magnetSegmentFrames(_ segment: TimelineSubtitleMagnetSegment, fps: Double) -> (start: Int, end: Int) {
        let start = segment.timelineStartFrame ?? segment.startFrame ?? frameIndex(segment.start, fps: fps)
        let endRaw = segment.timelineEndFrame ?? segment.endFrame ?? frameIndex(segment.end, fps: fps)
        let end = max(start + 1, endRaw)
        return (start, end)
    }

    static func frameIndex(_ sec: Double, fps: Double) -> Int {
        let normalizedFPS = max(1.0, min(240.0, fps.isFinite ? fps : 30.0))
        let clampedSec = max(0.0, sec.isFinite ? sec : 0.0)
        return Int((clampedSec * normalizedFPS).rounded())
    }

    static func secFromFrame(_ frame: Int, fps: Double) -> Double {
        let normalizedFPS = max(1.0, min(240.0, fps.isFinite ? fps : 30.0))
        return round((Double(max(0, frame)) / normalizedFPS) * 1_000_000) / 1_000_000
    }

    static func boundaryBlocksGap(start: Double, end: Double, boundaries: [Double], tolerance: Double) -> Bool {
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

    static func vadBlocksGap(start: Double, end: Double, vadSegments: [TimelineSubtitleMagnetVADSegment], tolerance: Double) -> Bool {
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

    static func isMicroSegment(_ segment: TimelineSubtitleMagnetSegment, minDuration: Double, charFloor: Int) -> Bool {
        let duration = max(0.0, segment.end - segment.start)
        let compactLength = segment.text.replacingOccurrences(of: "\\s+", with: "", options: .regularExpression).count
        return duration < minDuration || compactLength <= charFloor
    }

    static func normalizeMagnetSegment(_ segment: TimelineSubtitleMagnetSegment, fps: Double) -> TimelineSubtitleMagnetSegment {
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

    static func snapshotRow(_ segment: TimelineSubtitleMagnetSegment, index: Int) -> TimelineSubtitleMagnetSnapshotRow {
        TimelineSubtitleMagnetSnapshotRow(
            index: index,
            line: segment.line ?? index,
            start: round(max(0.0, segment.start) * 1_000_000) / 1_000_000,
            end: round(max(0.0, segment.end) * 1_000_000) / 1_000_000,
            text: segment.text,
            spk: segment.spk ?? segment.speaker ?? ""
        )
    }
}
