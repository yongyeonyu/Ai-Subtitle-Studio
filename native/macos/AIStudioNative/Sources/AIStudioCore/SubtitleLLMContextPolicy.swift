import Foundation

public enum SubtitleLLMContextPolicy {
    public static func plan(payload: [String: Any]) -> [String: Any] {
        let segments = SubtitleAssemblyValue.dictionaryRows(payload["segments"])
        let vadSegments = SubtitleAssemblyValue.dictionaryRows(payload["vad_segments"])
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let maxCandidates = max(1, min(8, Int(SubtitleAssemblyValue.number(settings["subtitle_llm_context_candidate_limit"], fallback: 5.0))))
        let packs = segments.enumerated().map { index, _ in
            contextPack(index: index, segments: segments, vadSegments: vadSegments, maxCandidates: maxCandidates)
        }
        return [
            "schema": SubtitleAssemblySchemas.llmContextPack,
            "backend": "swift",
            "pack_count": packs.count,
            "packs": packs,
            "rules": [
                "llm_role": "advisory_only",
                "text_owner": "stt1_stt2_candidates",
                "time_owner": "vad_stt_span",
                "neighbor_context_policy": "previous_next_for_disambiguation_not_replacement",
                "failure_action": "rollback_to_stt_locked_text",
            ],
        ]
    }

    public static func gate(payload: [String: Any]) -> [String: Any] {
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let sourceText = cleanText(payload["source_text"])
        let outputText = cleanText(textChunks(payload["chunks"]).joined(separator: " "))
        let contextPack = payload["context_pack"] as? [String: Any] ?? [:]
        let minCurrentSimilarity = clamp(
            SubtitleAssemblyValue.number(settings["subtitle_llm_context_min_current_similarity"], fallback: 0.86),
            min: 0.50,
            max: 1.0
        )
        let neighborMargin = clamp(
            SubtitleAssemblyValue.number(settings["subtitle_llm_context_neighbor_reject_margin"], fallback: 0.06),
            min: 0.0,
            max: 0.30
        )

        if outputText.isEmpty {
            return gateResult(
                accepted: false,
                reason: "empty_output",
                sourceSimilarity: 0.0,
                currentSimilarity: 0.0,
                neighborSimilarity: 0.0,
                currentSource: ""
            )
        }

        let currentCandidates = candidateTexts(contextPack: contextPack, roles: ["current"])
        let neighborCandidates = candidateTexts(contextPack: contextPack, roles: ["previous", "next"])
        let currentSet = currentCandidates.isEmpty ? [sourceText].filter { !$0.isEmpty } : currentCandidates
        let currentBest = bestSimilarity(outputText, currentSet)
        let neighborBest = bestSimilarity(outputText, neighborCandidates)
        let sourceSimilarity = similarity(outputText, sourceText)

        if neighborBest.score >= minCurrentSimilarity && neighborBest.score > currentBest.score + neighborMargin {
            return gateResult(
                accepted: false,
                reason: "neighbor_context_takeover",
                sourceSimilarity: sourceSimilarity,
                currentSimilarity: currentBest.score,
                neighborSimilarity: neighborBest.score,
                currentSource: currentBest.text
            )
        }

        if currentBest.score < minCurrentSimilarity && sourceSimilarity < minCurrentSimilarity {
            return gateResult(
                accepted: false,
                reason: "not_supported_by_current_stt_context",
                sourceSimilarity: sourceSimilarity,
                currentSimilarity: currentBest.score,
                neighborSimilarity: neighborBest.score,
                currentSource: currentBest.text
            )
        }

        return gateResult(
            accepted: true,
            reason: "stt_vad_context_supported",
            sourceSimilarity: sourceSimilarity,
            currentSimilarity: currentBest.score,
            neighborSimilarity: neighborBest.score,
            currentSource: currentBest.text
        )
    }

    private static func contextPack(
        index: Int,
        segments: [[String: Any]],
        vadSegments: [[String: Any]],
        maxCandidates: Int
    ) -> [String: Any] {
        let current = index >= 0 && index < segments.count ? segments[index] : [:]
        let start = SubtitleAssemblyValue.number(current["start"], fallback: 0.0)
        let end = SubtitleAssemblyValue.number(current["end"], fallback: start)
        return [
            "schema": SubtitleAssemblySchemas.llmContextPack,
            "index": index,
            "window": [
                "previous": rowSummary(index: index - 1, role: "previous", row: row(at: index - 1, in: segments), maxCandidates: maxCandidates),
                "current": rowSummary(index: index, role: "current", row: current, maxCandidates: maxCandidates),
                "next": rowSummary(index: index + 1, role: "next", row: row(at: index + 1, in: segments), maxCandidates: maxCandidates),
            ],
            "vad": vadSummary(vadSegments: vadSegments, start: start, end: end),
            "constraints": [
                "llm_role": "advisory_only",
                "current_subtitle_required": true,
                "previous_next_are_context_only": true,
                "forbidden": [
                    "invent_words",
                    "replace_current_with_neighbor",
                    "move_time_outside_vad_stt_span",
                ],
            ],
        ]
    }

    private static func row(at index: Int, in rows: [[String: Any]]) -> [String: Any] {
        guard index >= 0 && index < rows.count else {
            return [:]
        }
        return rows[index]
    }

    private static func rowSummary(index: Int, role: String, row: [String: Any], maxCandidates: Int) -> [String: Any] {
        guard !row.isEmpty else {
            return [
                "index": index,
                "role": role,
                "exists": false,
                "text": "",
                "candidates": [],
            ]
        }
        return [
            "index": index,
            "role": role,
            "exists": true,
            "start": round3(SubtitleAssemblyValue.number(row["start"], fallback: 0.0)),
            "end": round3(SubtitleAssemblyValue.number(row["end"], fallback: 0.0)),
            "text": cleanText(row["text"]),
            "selected_source": selectedSource(row),
            "candidates": candidateRows(row, maxCandidates: maxCandidates),
        ]
    }

    private static func selectedSource(_ row: [String: Any]) -> String {
        for key in ["stt_selected_source", "stt_ensemble_source", "stt_ensemble_llm_selected_source", "source"] {
            let value = SubtitleAssemblyValue.string(row[key])
            if !value.isEmpty {
                return value
            }
        }
        return ""
    }

    private static func candidateRows(_ row: [String: Any], maxCandidates: Int) -> [[String: Any]] {
        var out: [[String: Any]] = []
        var seen = Set<String>()

        func appendCandidate(text rawText: Any?, source rawSource: Any?, rank: Int) {
            let text = cleanText(rawText)
            let key = compact(text)
            guard !key.isEmpty && !seen.contains(key) && out.count < maxCandidates else {
                return
            }
            seen.insert(key)
            out.append(
                [
                    "rank": rank,
                    "source": SubtitleAssemblyValue.string(rawSource),
                    "text": clipped(text, maxChars: 96),
                    "compact_len": compact(text).count,
                ]
            )
        }

        appendCandidate(text: row["text"], source: selectedSource(row).isEmpty ? "CURRENT" : selectedSource(row), rank: 0)
        for (offset, item) in SubtitleAssemblyValue.dictionaryRows(row["stt_candidates"]).enumerated() {
            appendCandidate(
                text: item["text"],
                source: SubtitleAssemblyValue.string(item["source"]).isEmpty ? item["stt_source"] : item["source"],
                rank: offset + 1
            )
        }
        return out
    }

    private static func vadSummary(vadSegments: [[String: Any]], start: Double, end: Double) -> [String: Any] {
        let duration = max(0.001, end - start)
        var hints: [[String: Any]] = []
        var overlap = 0.0
        for row in vadSegments {
            let vadStart = SubtitleAssemblyValue.number(row["start"], fallback: 0.0)
            let vadEnd = SubtitleAssemblyValue.number(row["end"], fallback: vadStart)
            if vadEnd < start - 0.4 || vadStart > end + 0.4 {
                continue
            }
            let clippedStart = max(start, vadStart)
            let clippedEnd = min(end, vadEnd)
            if clippedEnd > clippedStart {
                overlap += clippedEnd - clippedStart
            }
            if hints.count < 8 {
                hints.append(["start": round3(vadStart), "end": round3(vadEnd)])
            }
        }
        return [
            "speech_overlap_ratio": round3(min(1.0, max(0.0, overlap / duration))),
            "hints": hints,
        ]
    }

    private static func candidateTexts(contextPack: [String: Any], roles: Set<String>) -> [String] {
        guard let window = contextPack["window"] as? [String: Any] else {
            return []
        }
        var out: [String] = []
        for role in roles.sorted() {
            guard let row = window[role] as? [String: Any] else {
                continue
            }
            let text = cleanText(row["text"])
            if !text.isEmpty {
                out.append(text)
            }
            for item in SubtitleAssemblyValue.dictionaryRows(row["candidates"]) {
                let candidate = cleanText(item["text"])
                if !candidate.isEmpty {
                    out.append(candidate)
                }
            }
        }
        var seen = Set<String>()
        return out.filter { text in
            let key = compact(text)
            if key.isEmpty || seen.contains(key) {
                return false
            }
            seen.insert(key)
            return true
        }
    }

    private static func textChunks(_ value: Any?) -> [String] {
        if let values = value as? [String] {
            return values.map { cleanText($0) }.filter { !$0.isEmpty }
        }
        if let values = value as? [Any] {
            return values.map { cleanText($0) }.filter { !$0.isEmpty }
        }
        let single = cleanText(value)
        return single.isEmpty ? [] : [single]
    }

    private static func cleanText(_ value: Any?) -> String {
        SubtitleAssemblyValue.string(value)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func compact(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\\s+", with: "", options: .regularExpression)
            .lowercased()
    }

    private static func clipped(_ value: String, maxChars: Int) -> String {
        if value.count <= maxChars {
            return value
        }
        return String(value.prefix(maxChars))
    }

    private static func bestSimilarity(_ output: String, _ candidates: [String]) -> (score: Double, text: String) {
        var bestScore = 0.0
        var bestText = ""
        for candidate in candidates {
            let score = similarity(output, candidate)
            if score > bestScore {
                bestScore = score
                bestText = candidate
            }
        }
        return (bestScore, bestText)
    }

    private static func similarity(_ left: String, _ right: String) -> Double {
        let a = Array(compact(left))
        let b = Array(compact(right))
        if a.isEmpty || b.isEmpty {
            return 0.0
        }
        if a == b {
            return 1.0
        }
        let distance = levenshtein(a, b)
        let denom = max(a.count, b.count)
        return max(0.0, 1.0 - (Double(distance) / Double(max(1, denom))))
    }

    private static func levenshtein(_ left: [Character], _ right: [Character]) -> Int {
        if left.isEmpty {
            return right.count
        }
        if right.isEmpty {
            return left.count
        }
        var previous = Array(0...right.count)
        var current = Array(repeating: 0, count: right.count + 1)
        for i in 1...left.count {
            current[0] = i
            for j in 1...right.count {
                let cost = left[i - 1] == right[j - 1] ? 0 : 1
                current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            }
            previous = current
        }
        return previous[right.count]
    }

    private static func gateResult(
        accepted: Bool,
        reason: String,
        sourceSimilarity: Double,
        currentSimilarity: Double,
        neighborSimilarity: Double,
        currentSource: String
    ) -> [String: Any] {
        [
            "schema": SubtitleAssemblySchemas.llmContextGate,
            "backend": "swift",
            "accepted": accepted,
            "reason": reason,
            "source_similarity": round3(sourceSimilarity),
            "current_context_similarity": round3(currentSimilarity),
            "neighbor_context_similarity": round3(neighborSimilarity),
            "matched_current_text": clipped(currentSource, maxChars: 96),
        ]
    }

    private static func clamp(_ value: Double, min minValue: Double, max maxValue: Double) -> Double {
        Swift.max(minValue, Swift.min(maxValue, value))
    }

    private static func round3(_ value: Double) -> Double {
        (value * 1000.0).rounded() / 1000.0
    }
}
