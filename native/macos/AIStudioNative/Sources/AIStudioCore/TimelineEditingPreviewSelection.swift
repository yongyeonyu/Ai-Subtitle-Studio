import Foundation

extension TimelineEditing {
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

    static func cleanWhisperText(_ text: String) -> String {
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

    static func editorSegmentSource(_ seg: TimelineEditorSegmentRow) -> String {
        let source = seg.sttPreviewSource
            ?? seg.sttSource
            ?? seg.sttSelectedSource
            ?? seg.sttEnsembleLLMSelectedSource
            ?? seg.sttEnsembleSource
            ?? "STT1"
        let normalized = source.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        return normalized.isEmpty ? "STT1" : normalized
    }

    static func editorSegmentSpeaker(_ seg: TimelineEditorSegmentRow) -> String {
        let speaker = seg.speaker ?? seg.spk ?? "00"
        let normalized = speaker.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.isEmpty ? "00" : normalized
    }

    static func normalizedSTTScore(_ seg: TimelineEditorSegmentRow) -> Double {
        let raw = seg.sttScore ?? seg.score ?? 98.0
        let normalized = raw > 1.0 ? raw : raw * 100.0
        return max(0.0, min(100.0, normalized.isFinite ? normalized : 98.0))
    }

    static func sourcePriority(_ source: String) -> Int {
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

    static func segmentsOverlap(
        _ left: TimelineEditorSegmentRow,
        _ right: TimelineEditorSegmentRow,
        pad: Double = 0.001
    ) -> Bool {
        left.start < right.end + pad && left.end > right.start - pad
    }

    static func dropOverlappingPreviewSegments(
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

    static func segmentOverlapsTimeRange(
        _ seg: TimelineEditorSegmentRow,
        start: Double,
        end: Double,
        pad: Double = 0.001
    ) -> Bool {
        seg.start < end - pad && seg.end > start + pad
    }

    static func bestFinalSegmentForSTTCandidate(
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

    static func overlappingSegments(
        segments: [TimelineEditorSegmentRow],
        candidate: TimelineEditorSegmentRow,
        fps: Double
    ) -> [TimelineEditorSegmentRow] {
        let candStart = snapSecToFrame(max(0.0, candidate.start), fps: fps)
        let candEnd = snapSecToFrame(max(candStart, candidate.end), fps: fps)
        return segments.filter { segmentOverlapsTimeRange($0, start: candStart, end: candEnd) }
    }

    static func sttSelectionSlot(
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

    static func sttSlotCandidatesForSource(
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
}
