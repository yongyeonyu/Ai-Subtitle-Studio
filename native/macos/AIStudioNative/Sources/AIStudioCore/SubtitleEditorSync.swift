import Foundation

enum SubtitleEditorSyncNative {
    static func prepareLoadResponse(_ request: TimelineEditorLoadRequest) -> TimelineEditorLoadResponse {
        let fps = max(1.0, request.frameRate.isFinite ? request.frameRate : 30.0)
        var preparedSegments: [TimelineEditorLoadPreparedSegment] = []
        preparedSegments.reserveCapacity(request.segments.count)
        var preparedBlocks: [TimelineEditorLoadPreparedBlock] = []
        preparedBlocks.reserveCapacity(request.segments.count * 2)
        var nextBlockIndex = 0

        for item in request.segments {
            let start = TimelineEditing.snapSecToFrame(max(0.0, item.start), fps: fps)
            var end = TimelineEditing.snapSecToFrame(max(start, item.end.isFinite ? item.end : start), fps: fps)
            if end <= start {
                end = TimelineEditing.snapSecToFrame(start + 0.5, fps: fps)
            }

            if item.isGap ?? false {
                preparedSegments.append(
                    TimelineEditorLoadPreparedSegment(
                        sourceIndex: item.sourceIndex,
                        start: start,
                        end: end,
                        text: "",
                        parts: [],
                        isGap: true
                    )
                )
                preparedBlocks.append(
                    TimelineEditorLoadPreparedBlock(
                        blockIndex: nextBlockIndex,
                        sourceIndex: item.sourceIndex,
                        start: start,
                        end: end,
                        text: "",
                        isGap: true
                    )
                )
                nextBlockIndex += 1
                continue
            }

            let cleaned = TimelineEditing.cleanEditorLoadText(item.text)
            let parts = cleaned
                .split(separator: "\n", omittingEmptySubsequences: false)
                .map(String.init)
                .filter { !$0.isEmpty }
            if parts.isEmpty {
                continue
            }

            preparedSegments.append(
                TimelineEditorLoadPreparedSegment(
                    sourceIndex: item.sourceIndex,
                    start: start,
                    end: end,
                    text: parts.joined(separator: "\n"),
                    parts: parts,
                    isGap: false
                )
            )

            var currentBlockText = parts[0]
            for part in parts.dropFirst() {
                if shouldSplitMultilinePartIntoSeparateBlock(item: item, part: part) {
                    preparedBlocks.append(
                        TimelineEditorLoadPreparedBlock(
                            blockIndex: nextBlockIndex,
                            sourceIndex: item.sourceIndex,
                            start: start,
                            end: end,
                            text: currentBlockText,
                            isGap: false
                        )
                    )
                    nextBlockIndex += 1
                    currentBlockText = part
                } else {
                    currentBlockText += "\u{2028}" + part
                }
            }
            preparedBlocks.append(
                TimelineEditorLoadPreparedBlock(
                    blockIndex: nextBlockIndex,
                    sourceIndex: item.sourceIndex,
                    start: start,
                    end: end,
                    text: currentBlockText,
                    isGap: false
                )
            )
            nextBlockIndex += 1
        }

        return TimelineEditorLoadResponse(
            segments: preparedSegments,
            blocks: preparedBlocks
        )
    }

    private static func shouldSplitMultilinePartIntoSeparateBlock(
        item: TimelineEditorLoadInputSegment,
        part: String
    ) -> Bool {
        guard part.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("-") else {
            return false
        }
        let speakers = normalizedSpeakerList(item)
        if Set(speakers).count >= 2 {
            return true
        }
        let speaker = normalizedSpeaker(item.speaker)
        let speaker2 = normalizedSpeaker(item.speaker2)
        return !speaker.isEmpty && !speaker2.isEmpty && speaker != speaker2
    }

    private static func normalizedSpeakerList(_ item: TimelineEditorLoadInputSegment) -> [String] {
        (item.speakerList ?? [])
            .map(normalizedSpeaker)
            .filter { !$0.isEmpty }
    }

    private static func normalizedSpeaker(_ value: String?) -> String {
        String(value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
