import Foundation

public enum NativePolicyEngine {
    public static func llmCandidates(payload: [String: Any]) -> [String: Any] {
        let text = cleanLine(payload["text"])
        let threshold = max(2, intValue(payload["threshold"], default: 10))
        let rules = payload["rules"] as? [String: Any] ?? [:]
        let settings = payload["settings"] as? [String: Any] ?? [:]
        if !boolValue(settings["llm_candidate_policy_enabled"], default: true) || text.isEmpty {
            return ["candidates": []]
        }
        let maxCandidates = max(1, min(6, intValue(settings["llm_candidate_policy_max_candidates"], default: 4)))
        let targetLineCount = intValue(settings["subtitle_target_line_count"], default: 0)
        let patterns = loraLineBreakPatterns(settings: settings, limit: max(0, min(6, intValue(settings["linebreak_lora_policy_max_patterns"], default: 3))))

        var raw: [(String, String, [String], String)] = [("A", "원문 유지", [text], "source")]
        for (index, pattern) in patterns.enumerated() {
            raw.append(("L\(index + 1)", "LoRA ground truth 줄바꿈(\(pattern))", patternChunks(text: text, pattern: pattern), "lora_ground_truth_line_break"))
        }
        raw.append(("B", "기존 줄바꿈 유지", existingLineChunks(payload["text"]), "existing_linebreak"))
        raw.append(("C", "규칙 기반 안전 분할", greedyRuleChunks(text: text, threshold: threshold, rules: rules), "rule_greedy"))
        if targetLineCount >= 2 {
            raw.append(("D", "LoRA 줄 수 맞춤", balancedChunksForCount(text: text, targetCount: targetLineCount), "lora_line_count"))
        }
        raw.append(("E", "균형 길이 분할", balancedChunks(text: text, threshold: threshold), "balanced"))

        var out: [[String: Any]] = []
        var seen = Set<String>()
        for (candidateID, label, chunks, strategy) in raw {
            let cleaned = cleanChunks(chunks)
            if cleaned.isEmpty {
                continue
            }
            let signature = chunksSignature(cleaned)
            if signature.isEmpty || seen.contains(signature) {
                continue
            }
            seen.insert(signature)
            out.append([
                "id": candidateID,
                "label": label,
                "strategy": strategy,
                "chunks": cleaned,
                "chunk_count": cleaned.count,
                "compact_len": compactLength(cleaned.joined()),
                "lora_primary": strategy == "lora_ground_truth_line_break",
            ])
            if out.count >= maxCandidates {
                break
            }
        }
        return ["candidates": out]
    }

    public static func llmCandidatesBatch(payload: [String: Any]) -> [String: Any] {
        let items = payload["items"] as? [[String: Any]] ?? []
        let results = items.map { item -> [String: Any] in
            let response = llmCandidates(payload: item)
            return [
                "id": item["id"] ?? "",
                "candidates": response["candidates"] ?? [],
            ]
        }
        return ["results": results]
    }

    public static func deepRerank(payload: [String: Any]) -> [String: Any] {
        let original = cleanLine(payload["original_text"])
        let candidateLists = (payload["candidate_lists"] as? [[Any]] ?? []).map { row in
            cleanChunks(row.map { stringValue($0) })
        }
        let settings = payload["settings"] as? [String: Any] ?? [:]
        let profile = payload["profile"] as? [String: Any] ?? [:]
        if !boolValue(settings["deep_subtitle_policy_enabled"], default: true)
            || !boolValue(settings["deep_subtitle_reranker_enabled"], default: true) {
            return ["chunks": candidateLists.first ?? [], "metadata": [:]]
        }
        let patternOnly = boolValue(settings["deep_policy_pattern_only_enabled"], default: false)
        let patternSettings = profilePatternSettings(profile)
        var scored: [(Double, Int, [String])] = []
        var seen = Set<String>()
        for (index, chunks) in candidateLists.enumerated() {
            let key = chunks.map { compact($0) }.joined(separator: "\n")
            if chunks.isEmpty || seen.contains(key) {
                continue
            }
            seen.insert(key)
            let score: Double
            if patternOnly && !patternSettings.isEmpty {
                let joined = cleanLine(chunks.joined(separator: " "))
                let targetLen = clampInt(patternSettings["split_length_threshold"] ?? settings["split_length_threshold"], low: 6, high: 40, defaultValue: 16)
                let lineTarget = intValue(patternSettings["subtitle_target_line_count"] ?? settings["subtitle_target_line_count"], default: 0)
                let lengthScore = 1.0 - min(1.0, abs(Double(compactLength(joined) - targetLen)) / max(6.0, Double(targetLen)))
                let lineScore = lineTarget <= 0 ? 0.65 : max(0.0, 1.0 - abs(Double(chunks.count - lineTarget)) / max(1.0, Double(lineTarget)))
                score = max(0.0, min(1.0, lengthScore * 0.74 + lineScore * 0.26))
            } else {
                score = candidateTextScore(original: original, chunks: chunks, settings: settings, profile: profile)
            }
            scored.append((score, index, chunks))
        }
        if scored.isEmpty {
            return ["chunks": [], "metadata": [:]]
        }
        scored.sort {
            if abs($0.0 - $1.0) > 0.0000001 {
                return $0.0 > $1.0
            }
            return $0.1 < $1.1
        }
        let best = scored[0]
        let baseScore = scored.first(where: { $0.1 == 0 })?.0 ?? best.0
        let margin = best.0 - baseScore
        let minMargin = clampDouble(settings["deep_subtitle_reranker_min_margin"], low: 0.0, high: 0.4, defaultValue: 0.03)
        let chosen = (best.1 == 0 || margin >= minMargin) ? best.2 : (candidateLists.first ?? [])
        let chosenIndex = chunksSignature(chosen) == chunksSignature(best.2) ? best.1 : 0
        return [
            "chunks": chosen,
            "metadata": [
                "schema": "ai_subtitle_studio.deep_subtitle_policy.v1",
                "model": "feature_mlp_fallback_v1:swift",
                "task": "subtitle_rerank",
                "chosen_index": chosenIndex,
                "best_score": rounded(best.0, places: 4),
                "base_score": rounded(baseScore, places: 4),
                "margin": rounded(margin, places: 4),
                "profile_score": rounded(profileTopScore(profile), places: 4),
                "candidate_count": scored.count,
            ],
        ]
    }

    public static func deepRerankBatch(payload: [String: Any]) -> [String: Any] {
        let items = payload["items"] as? [[String: Any]] ?? []
        let results = items.map { item -> [String: Any] in
            let response = deepRerank(payload: item)
            return [
                "id": item["id"] ?? "",
                "chunks": response["chunks"] ?? [],
                "metadata": response["metadata"] ?? [:],
            ]
        }
        return ["results": results]
    }

    public static func loraScore(payload: [String: Any]) -> [String: Any] {
        let index = payload["index"] as? [String: Any] ?? [:]
        let docs = index["docs"] as? [[String: Any]] ?? []
        let queryVector = stringDoubleDict(payload["query_vector"])
        let queryTerms = stringDoubleDict(payload["query_terms"])
        if docs.isEmpty || (queryVector.isEmpty && queryTerms.isEmpty) {
            return ["items": []]
        }
        let inverted = index["inverted_index"] as? [String: [[Any]]] ?? [:]
        let bm25 = index["bm25"] as? [String: Any] ?? [:]
        let postings = bm25["term_postings"] as? [String: [[Any]]] ?? [:]
        let idf = stringDoubleDict(bm25["idf"])
        let docLengths = (bm25["doc_lengths"] as? [Any] ?? []).map { doubleValue($0, default: 0.0) }
        let avgDocLen = max(1.0, doubleValue(bm25["avg_doc_len"], default: 1.0))

        var vectorScores = Array(repeating: 0.0, count: docs.count)
        for (bucket, queryWeight) in queryVector {
            for row in inverted[bucket] ?? [] {
                if row.count < 2 {
                    continue
                }
                let docIndex = intValue(row[0], default: -1)
                if docIndex >= 0 && docIndex < vectorScores.count {
                    vectorScores[docIndex] += queryWeight * doubleValue(row[1], default: 0.0)
                }
            }
        }

        var bm25Scores = Array(repeating: 0.0, count: docs.count)
        let k1 = 1.35
        let b = 0.72
        for (termHash, queryTF) in queryTerms {
            let termIDF = idf[termHash] ?? 0.0
            if termIDF <= 0.0 {
                continue
            }
            let queryWeight = 1.0 + log(max(1.0, queryTF))
            for row in postings[termHash] ?? [] {
                if row.count < 2 {
                    continue
                }
                let docIndex = intValue(row[0], default: -1)
                if docIndex < 0 || docIndex >= bm25Scores.count {
                    continue
                }
                let tf = doubleValue(row[1], default: 0.0)
                if tf <= 0.0 {
                    continue
                }
                let docLen = docIndex < docLengths.count ? docLengths[docIndex] : avgDocLen
                let denom = tf + k1 * (1.0 - b + b * docLen / avgDocLen)
                bm25Scores[docIndex] += termIDF * ((tf * (k1 + 1.0)) / max(0.0001, denom)) * queryWeight
            }
        }

        let kinds = Set((payload["kinds"] as? [Any] ?? []).map { stringValue($0) }.filter { !$0.isEmpty })
        let qualityBuckets = Set((payload["quality_buckets"] as? [Any] ?? []).map { stringValue($0) }.filter { !$0.isEmpty })
        let query = stringValue(payload["query"])
        let mediaPath = stringValue(payload["media_path"])
        let mediaID = stringValue(payload["media_id"])
        let queryPathKeys = Set((payload["media_lookup_keys"] as? [Any] ?? []).map { stringValue($0) })
        let queryLeaf = compact(pathLeafTerms(mediaPath))
        let queryFacets = facetMap(payload["query_facets"] as? [String: Any] ?? [:])

        var touched = Set<Int>()
        for index in vectorScores.indices where vectorScores[index] != 0.0 {
            touched.insert(index)
        }
        for index in bm25Scores.indices where bm25Scores[index] != 0.0 {
            touched.insert(index)
        }

        let touchedList = Array(touched)
        let inputs = touchedList.compactMap { docIndex -> NativeLoraDocInput? in
            if docIndex < 0 || docIndex >= docs.count {
                return nil
            }
            return nativeLoraDocInput(index: docIndex, doc: docs[docIndex])
        }
        let vectors = vectorScores
        let bm25s = bm25Scores
        let scoreBox = LockedArray<NativeLoraScore>()
        DispatchQueue.concurrentPerform(iterations: inputs.count) { pos in
            let doc = inputs[pos]
            let docIndex = doc.index
            if !kinds.isEmpty && !kinds.contains(doc.kind) {
                return
            }
            if !qualityBuckets.isEmpty && !qualityBuckets.contains(doc.qualityBucket) {
                return
            }
            let overlap = tokenOverlapScore(query, doc.textPreview)
            let vectorScore = vectors[docIndex]
            let bm25Raw = bm25s[docIndex]
            let vectorPoints = vectorScore * 44.0
            let bm25Points = min(24.0, log1p(max(0.0, bm25Raw)) * 9.0)
            let overlapPoints = overlap * 8.0
            let qualityPoints = doc.quality * 8.0
            let kindPoints = kindBoost(doc.kind)
            let mediaPoints = mediaMatchBoost(
                doc: doc,
                mediaPath: mediaPath,
                mediaID: mediaID,
                queryPathKeys: queryPathKeys,
                queryLeaf: queryLeaf
            )
            let facet = facetMatchPoints(doc: doc, queryFacets: queryFacets)
            let recency = doc.recency
            let finalScore = min(100.0, vectorPoints + bm25Points + overlapPoints + qualityPoints + kindPoints + mediaPoints + facet.points + recency)
            scoreBox.append(
                NativeLoraScore(
                    docIndex: docIndex,
                    vectorScore: rounded(vectorScore, places: 6),
                    bm25Score: rounded(bm25Raw, places: 6),
                    overlapScore: rounded(overlap, places: 6),
                    retrievalScore: rounded(finalScore, places: 4),
                    quality: doc.quality,
                    scoreBreakdown: [
                        "vector": rounded(vectorPoints, places: 4),
                        "bm25": rounded(bm25Points, places: 4),
                        "overlap": rounded(overlapPoints, places: 4),
                        "quality": rounded(qualityPoints, places: 4),
                        "kind": rounded(kindPoints, places: 4),
                        "media": rounded(mediaPoints, places: 4),
                        "facet": rounded(facet.points, places: 4),
                        "recency": rounded(recency, places: 4),
                        "final": rounded(finalScore, places: 4),
                    ],
                    facetMatches: facet.matches
                )
            )
        }
        let scored = scoreBox.snapshot().sorted {
            if abs($0.retrievalScore - $1.retrievalScore) > 0.0000001 {
                return $0.retrievalScore > $1.retrievalScore
            }
            return $0.quality > $1.quality
        }
        let ranked = scored.map { score -> [String: Any] in
            var doc = docs[score.docIndex]
            doc["vector_score"] = score.vectorScore
            doc["bm25_score"] = score.bm25Score
            doc["overlap_score"] = score.overlapScore
            doc["retrieval_score"] = score.retrievalScore
            doc["score_model"] = "hybrid_hash_vector_bm25_context_facet_quality_bucket_v3"
            doc["score_breakdown"] = score.scoreBreakdown
            if !score.facetMatches.isEmpty {
                doc["facet_matches"] = score.facetMatches
            }
            return doc
        }
        return ["items": ranked]
    }
}

private struct NativeLoraDocInput: Sendable {
    let index: Int
    let kind: String
    let qualityBucket: String
    let quality: Double
    let textPreview: String
    let mediaID: String
    let mediaPath: String
    let mediaLookupKeys: Set<String>
    let facets: [String: [String]]
    let recency: Double
}

private struct NativeLoraScore: Sendable {
    let docIndex: Int
    let vectorScore: Double
    let bm25Score: Double
    let overlapScore: Double
    let retrievalScore: Double
    let quality: Double
    let scoreBreakdown: [String: Double]
    let facetMatches: [String: [String]]
}

private final class LockedArray<Element: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [Element] = []

    func append(_ value: Element) {
        lock.lock()
        values.append(value)
        lock.unlock()
    }

    func snapshot() -> [Element] {
        lock.lock()
        let out = values
        lock.unlock()
        return out
    }
}

private func nativeLoraDocInput(index: Int, doc: [String: Any]) -> NativeLoraDocInput {
    NativeLoraDocInput(
        index: index,
        kind: stringValue(doc["kind"]),
        qualityBucket: stringValue(doc["quality_bucket"]),
        quality: max(0.0, min(1.0, doubleValue(doc["quality"], default: 0.0))),
        textPreview: stringValue(doc["text_preview"]),
        mediaID: stringValue(doc["media_id"]),
        mediaPath: stringValue(doc["media_path"]),
        mediaLookupKeys: Set((doc["media_lookup_keys"] as? [Any] ?? []).map { stringValue($0) }),
        facets: facetMap(doc["facets"] as? [String: Any] ?? [:]),
        recency: recencyPoints(doc)
    )
}

private func stringValue(_ value: Any?) -> String {
    if value == nil || value is NSNull {
        return ""
    }
    return String(describing: value!)
}

private func intValue(_ value: Any?, default fallback: Int) -> Int {
    if let int = value as? Int {
        return int
    }
    if let double = value as? Double {
        return Int(double.rounded())
    }
    if let string = value as? String, let double = Double(string) {
        return Int(double.rounded())
    }
    return fallback
}

private func doubleValue(_ value: Any?, default fallback: Double) -> Double {
    if let double = value as? Double {
        return double
    }
    if let int = value as? Int {
        return Double(int)
    }
    if let string = value as? String, let double = Double(string) {
        return double
    }
    return fallback
}

private func boolValue(_ value: Any?, default fallback: Bool) -> Bool {
    if let bool = value as? Bool {
        return bool
    }
    if let string = value as? String {
        return !["0", "false", "off", "no", "끔", "아니오"].contains(string.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }
    if value == nil || value is NSNull {
        return fallback
    }
    return boolValue(default: fallback, value: value)
}

private func boolValue(default fallback: Bool, value: Any?) -> Bool {
    if let number = value as? NSNumber {
        return number.boolValue
    }
    return fallback
}

private func cleanLine(_ value: Any?) -> String {
    stringValue(value)
        .components(separatedBy: .whitespacesAndNewlines)
        .filter { !$0.isEmpty }
        .joined(separator: " ")
}

private func compact(_ text: String) -> String {
    text.components(separatedBy: .whitespacesAndNewlines).joined().lowercased()
}

private func compactLength(_ text: String) -> Int {
    compact(text).count
}

private func tokens(_ text: String) -> [String] {
    guard let regex = NativePolicyCaches.tokenRegex else {
        return []
    }
    let lowered = text.lowercased()
    let range = NSRange(lowered.startIndex..<lowered.endIndex, in: lowered)
    return regex.matches(in: lowered, range: range).compactMap { match in
        guard let range = Range(match.range, in: lowered) else { return nil }
        return String(lowered[range])
    }
}

private func tokenizeWords(_ text: String) -> [String] {
    let split = cleanLine(text).split { $0.isWhitespace }.map(String.init)
    return split.isEmpty && !cleanLine(text).isEmpty ? [cleanLine(text)] : split
}

private func cleanChunks(_ chunks: [String]) -> [String] {
    chunks.map(cleanLine).filter { !$0.isEmpty }
}

private func chunksSignature(_ chunks: [String]) -> String {
    cleanChunks(chunks).map { compact($0) }.joined(separator: "\u{1F}")
}

private func existingLineChunks(_ value: Any?) -> [String] {
    stringValue(value).components(separatedBy: .newlines).map(cleanLine).filter { !$0.isEmpty }
}

private func isNaturalBreak(_ word: String, _ nextWord: String, rules: [String: Any]) -> Bool {
    let wordClean = word.replacingOccurrences(of: #"[^\w가-힣]"#, with: "", options: .regularExpression)
    let nextClean = nextWord.replacingOccurrences(of: #"[^\w가-힣]"#, with: "", options: .regularExpression)
    if word.trimmingCharacters(in: .whitespacesAndNewlines).hasSuffix(",")
        || word.hasSuffix("!")
        || word.hasSuffix("?")
        || word.hasSuffix("~") {
        return true
    }
    for rule in rules["end_words"] as? [Any] ?? [] {
        let text = stringValue(rule)
        if !text.isEmpty && wordClean.hasSuffix(text) {
            return true
        }
    }
    for rule in rules["start_words"] as? [Any] ?? [] {
        let text = stringValue(rule)
        if !text.isEmpty && nextClean.hasPrefix(text) {
            return true
        }
    }
    return false
}

private func greedyRuleChunks(text: String, threshold: Int, rules: [String: Any]) -> [String] {
    let sourceTokens = tokenizeWords(text)
    if sourceTokens.count <= 1 {
        return text.isEmpty ? [] : [text]
    }
    let threshold = max(2, threshold)
    let hardLimit = max(threshold + 2, Int(ceil(Double(threshold) * 1.45)))
    var chunks: [String] = []
    var buffer: [String] = []
    for (index, token) in sourceTokens.enumerated() {
        buffer.append(token)
        let isLast = index == sourceTokens.count - 1
        let clen = compactLength(buffer.joined(separator: " "))
        var flush = isLast
        if !isLast {
            let next = sourceTokens[index + 1]
            flush = (clen >= threshold && isNaturalBreak(token, next, rules: rules)) || clen >= hardLimit
        }
        if flush {
            let chunk = cleanLine(buffer.joined(separator: " "))
            if !chunk.isEmpty {
                chunks.append(chunk)
            }
            buffer.removeAll()
        }
    }
    return chunks.isEmpty && !text.isEmpty ? [text] : chunks
}

private func balancedChunks(text: String, threshold: Int) -> [String] {
    let sourceTokens = tokenizeWords(text)
    if sourceTokens.count <= 1 {
        return text.isEmpty ? [] : [text]
    }
    let charCount = max(1, compactLength(text))
    let targetChunks = max(1, min(6, Int(ceil(Double(charCount) / Double(max(2, threshold))))))
    if targetChunks <= 1 {
        return [text]
    }
    let targetChars = max(1, Int(ceil(Double(charCount) / Double(targetChunks))))
    var chunks: [String] = []
    var buffer: [String] = []
    for token in sourceTokens {
        if !buffer.isEmpty && compactLength((buffer + [token]).joined(separator: " ")) > targetChars && chunks.count < targetChunks - 1 {
            chunks.append(cleanLine(buffer.joined(separator: " ")))
            buffer = [token]
        } else {
            buffer.append(token)
        }
    }
    if !buffer.isEmpty {
        chunks.append(cleanLine(buffer.joined(separator: " ")))
    }
    return chunks.isEmpty ? [text] : chunks
}

private func balancedChunksForCount(text: String, targetCount: Int) -> [String] {
    let sourceTokens = tokenizeWords(text)
    let target = max(1, min(4, targetCount))
    if target <= 1 || sourceTokens.count <= 1 {
        return text.isEmpty ? [] : [text]
    }
    let finalTarget = min(target, sourceTokens.count)
    let targetChars = max(1, Int(ceil(Double(max(1, compactLength(text))) / Double(finalTarget))))
    var chunks: [String] = []
    var buffer: [String] = []
    for token in sourceTokens {
        if !buffer.isEmpty && chunks.count < finalTarget - 1 && compactLength((buffer + [token]).joined(separator: " ")) > targetChars {
            chunks.append(cleanLine(buffer.joined(separator: " ")))
            buffer = [token]
        } else {
            buffer.append(token)
        }
    }
    if !buffer.isEmpty {
        chunks.append(cleanLine(buffer.joined(separator: " ")))
    }
    return chunks.isEmpty ? [text] : chunks
}

private func patternChunks(text: String, pattern: String) -> [String] {
    let targets = pattern
        .split { "|,/ ".contains($0) }
        .compactMap { Int($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
        .filter { $0 > 0 }
    if targets.count <= 1 {
        return []
    }
    let sourceTokens = tokenizeWords(text)
    if sourceTokens.count <= 1 {
        return text.isEmpty ? [] : [text]
    }
    var chunks: [String] = []
    var buffer: [String] = []
    var targetIndex = 0
    for token in sourceTokens {
        if !buffer.isEmpty
            && targetIndex < targets.count - 1
            && compactLength((buffer + [token]).joined(separator: " ")) > targets[targetIndex] {
            chunks.append(cleanLine(buffer.joined(separator: " ")))
            buffer = [token]
            targetIndex += 1
        } else {
            buffer.append(token)
        }
    }
    if !buffer.isEmpty {
        chunks.append(cleanLine(buffer.joined(separator: " ")))
    }
    return chunks.count >= 2 ? chunks : []
}

private func loraLineBreakPatterns(settings: [String: Any], limit: Int) -> [String] {
    if !boolValue(settings["linebreak_lora_policy_enabled"], default: true) {
        return []
    }
    var patterns: [String] = []
    var seen = Set<String>()
    func add(_ value: Any?) {
        let text = stringValue(value).trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty || !text.contains("|") {
            return
        }
        let key = text.lowercased()
        if seen.contains(key) {
            return
        }
        seen.insert(key)
        patterns.append(text)
    }
    add(settings["lora_line_break_pattern"])
    let profile = settings["_lora_generation_profile"] as? [String: Any] ?? [:]
    for item in profile["examples"] as? [[String: Any]] ?? [] {
        add(item["line_break_pattern"])
        if let style = item["style_profile"] as? [String: Any],
           let lineBreak = style["line_break"] as? [String: Any] {
            add(lineBreak["pattern"])
        }
    }
    for item in profile["learned_rules"] as? [[String: Any]] ?? [] {
        if stringValue(item["kind"]) == "learned_line_break_rules" {
            add(item["rule_text"])
        }
    }
    return Array(patterns.prefix(max(0, limit)))
}

private func rounded(_ value: Double, places: Int) -> Double {
    let scale = pow(10.0, Double(places))
    return (value * scale).rounded() / scale
}

private func clampDouble(_ value: Any?, low: Double, high: Double, defaultValue: Double) -> Double {
    max(low, min(high, doubleValue(value, default: defaultValue)))
}

private func clampInt(_ value: Any?, low: Int, high: Int, defaultValue: Int) -> Int {
    max(low, min(high, intValue(value, default: defaultValue)))
}

private func stringDoubleDict(_ value: Any?) -> [String: Double] {
    var out: [String: Double] = [:]
    for (key, item) in value as? [String: Any] ?? [:] {
        out[key] = doubleValue(item, default: 0.0)
    }
    return out
}

private func compactSimilarity(_ left: String, _ right: String) -> Double {
    let a = Array(compact(left))
    let b = Array(compact(right))
    if a.isEmpty || b.isEmpty {
        return 0.0
    }
    let distance = levenshtein(a, b)
    return max(0.0, min(1.0, 1.0 - Double(distance) / Double(max(a.count, b.count))))
}

private func levenshtein<T: Equatable>(_ left: [T], _ right: [T]) -> Int {
    if left.isEmpty {
        return right.count
    }
    if right.isEmpty {
        return left.count
    }
    var previous = Array(0...right.count)
    for (leftIndex, leftItem) in left.enumerated() {
        var current = [leftIndex + 1]
        for (rightIndex, rightItem) in right.enumerated() {
            let insertCost = current[rightIndex] + 1
            let deleteCost = previous[rightIndex + 1] + 1
            let replaceCost = previous[rightIndex] + (leftItem == rightItem ? 0 : 1)
            current.append(min(insertCost, deleteCost, replaceCost))
        }
        previous = current
    }
    return previous.last ?? max(left.count, right.count)
}

private func tokenOverlapScore(_ left: String, _ right: String) -> Double {
    let l = Set(tokens(left))
    let r = Set(tokens(right))
    if l.isEmpty || r.isEmpty {
        return 0.0
    }
    return Double(l.intersection(r).count) / Double(max(1, l.union(r).count))
}

private func textSimilarity(_ left: String, _ right: String) -> Double {
    let charRatio = compactSimilarity(left, right)
    let tokenRatio = tokenOverlapScore(left, right)
    return max(0.0, min(1.0, charRatio * 0.72 + tokenRatio * 0.28))
}

private func profileExamples(_ profile: [String: Any]) -> [String] {
    var out: [String] = []
    for item in profile["examples"] as? [[String: Any]] ?? [] {
        for key in ["output", "text", "input"] {
            let text = cleanLine(item[key])
            if !text.isEmpty {
                out.append(text)
                break
            }
        }
    }
    return out
}

private func profileTopScore(_ profile: [String: Any]) -> Double {
    max(0.0, min(100.0, doubleValue(profile["top_score"], default: 0.0))) / 100.0
}

private func profilePatternSettings(_ profile: [String: Any]) -> [String: Any] {
    if let settings = profile["pattern_settings"] as? [String: Any], !settings.isEmpty {
        return settings
    }
    if let pattern = profile["pattern_match"] as? [String: Any],
       let settings = pattern["settings"] as? [String: Any] {
        return settings
    }
    return [:]
}

private func profileExclusions(_ profile: [String: Any]) -> [String] {
    (profile["exclusions"] as? [[String: Any]] ?? []).map { cleanLine($0["text"]) }.filter { !$0.isEmpty }
}

private func excludedPenalty(text: String, profile: [String: Any]) -> Double {
    let compactText = compact(text)
    if compactText.isEmpty {
        return 0.0
    }
    var penalty = 0.0
    for excluded in profileExclusions(profile) {
        let ex = compact(excluded)
        if !ex.isEmpty && compactText.contains(ex) {
            penalty = max(penalty, 0.42)
        }
    }
    return penalty
}

private func profileStyleScore(text: String, settings: [String: Any], profile: [String: Any]) -> Double {
    let pattern = profilePatternSettings(profile)
    if !pattern.isEmpty {
        let targetLen = clampInt(pattern["split_length_threshold"] ?? settings["split_length_threshold"], low: 6, high: 40, defaultValue: 16)
        if compactLength(text) <= 0 {
            return 0.0
        }
        return max(0.0, min(1.0, 1.0 - min(1.0, abs(Double(compactLength(text) - targetLen)) / max(6.0, Double(targetLen)))))
    }
    let examples = profileExamples(profile)
    let exampleScore = examples.isEmpty ? 0.35 : examples.map { textSimilarity(text, $0) }.max() ?? 0.35
    let targetLen = clampInt(settings["split_length_threshold"], low: 6, high: 40, defaultValue: 16)
    let lengthScore = compactLength(text) <= 0 ? 0.0 : 1.0 - min(1.0, abs(Double(compactLength(text) - targetLen)) / max(6.0, Double(targetLen)))
    return max(0.0, min(1.0, exampleScore * 0.65 + lengthScore * 0.35 - excludedPenalty(text: text, profile: profile)))
}

private func candidateTextScore(original: String, chunks: [String], settings: [String: Any], profile: [String: Any]) -> Double {
    let text = cleanLine(chunks.map(cleanLine).filter { !$0.isEmpty }.joined(separator: " "))
    if text.isEmpty {
        return 0.0
    }
    let integrity = textSimilarity(original, text)
    let style = profileStyleScore(text: text, settings: settings, profile: profile)
    let maxChars = clampInt(settings["split_length_threshold"], low: 6, high: 40, defaultValue: 16)
    let chunkLengths = chunks.map { compactLength($0) }.filter { $0 > 0 }
    let splitScore: Double
    if chunkLengths.isEmpty {
        splitScore = 0.0
    } else {
        let overflow = max(0, (chunkLengths.max() ?? 0) - Int(Double(maxChars) * 1.45))
        let underflow = chunkLengths.filter { $0 <= 1 }.count
        splitScore = max(0.0, 1.0 - Double(overflow) / max(1.0, Double(maxChars)) - Double(underflow) * 0.2)
    }
    let targetLines = intValue(settings["subtitle_target_line_count"], default: 0)
    let lineScore = targetLines > 0 ? max(0.0, 1.0 - abs(Double(chunks.count - targetLines)) / max(1.0, Double(targetLines))) : 0.65
    return max(0.0, min(1.0, integrity * 0.43 + style * 0.34 + splitScore * 0.13 + lineScore * 0.10))
}

private func kindBoost(_ kind: String) -> Double {
    [
        "truth_table": 7.0,
        "text_lora_corpus": 8.0,
        "text_lora_dataset": 5.0,
        "multimodal_lora_context": 6.0,
        "setting_trials": 5.0,
        "prompt_trials": 4.0,
        "audio_preset_lora": 5.0,
        "deep_policy_events": 4.5,
        "voice_lora_bridge": 3.0,
        "stt1_whisper_adapter_dataset": 5.0,
        "excluded_parentheticals": 6.0,
        "learned_split_rules": 4.0,
        "learned_line_break_rules": 4.0,
        "best_settings": 3.0,
    ][kind] ?? 1.0
}

private func pathLeafTerms(_ path: String) -> String {
    let leaf = (path as NSString).lastPathComponent
    let stem = (leaf as NSString).deletingPathExtension
    return "\(leaf) \(stem)"
        .replacingOccurrences(of: #"[\s._\-/]+"#, with: " ", options: .regularExpression)
}

private func mediaMatchBoost(doc: NativeLoraDocInput, mediaPath: String, mediaID: String, queryPathKeys: Set<String>, queryLeaf: String) -> Double {
    var boost = 0.0
    if !mediaID.isEmpty && doc.mediaID == mediaID {
        boost += 18.0
    }
    if !mediaPath.isEmpty {
        if !queryPathKeys.isEmpty && !doc.mediaLookupKeys.isEmpty && !queryPathKeys.intersection(doc.mediaLookupKeys).isEmpty {
            boost += 22.0
        }
        let docLeaf = compact(pathLeafTerms(doc.mediaPath))
        if !queryLeaf.isEmpty && !docLeaf.isEmpty && (queryLeaf.contains(docLeaf) || docLeaf.contains(queryLeaf)) {
            boost += 8.0
        }
    }
    return boost
}

private func facetLabel(_ value: Any?) -> String {
    let text = stringValue(value).trimmingCharacters(in: .whitespacesAndNewlines)
    return ["", "-", "none", "null", "unknown"].contains(text.lowercased()) ? "" : text
}

private func facetList(_ value: Any?) -> [String] {
    let raw = value as? [Any] ?? [value as Any]
    var out: [String] = []
    var seen = Set<String>()
    for item in raw {
        let text = facetLabel(item)
        let key = text.lowercased()
        if text.isEmpty || seen.contains(key) {
            continue
        }
        seen.insert(key)
        out.append(text)
        if out.count >= 12 {
            break
        }
    }
    return out
}

private func facetMap(_ raw: [String: Any]) -> [String: [String]] {
    var out: [String: [String]] = [:]
    for key in ["scene", "topic", "mic_type", "noise_level"] {
        let value = facetLabel(raw[key])
        if !value.isEmpty {
            out[key] = [value]
        }
    }
    for key in ["noise_sources", "training_focus", "topic_terms"] {
        let values = facetList(raw[key])
        if !values.isEmpty {
            out[key] = values
        }
    }
    return out
}

private func facetMatchPoints(doc: NativeLoraDocInput, queryFacets: [String: [String]]) -> (points: Double, matches: [String: [String]]) {
    if queryFacets.isEmpty {
        return (0.0, [:])
    }
    var points = 0.0
    var matches: [String: [String]] = [:]
    for (key, weight) in ["scene": 4.0, "topic": 5.0, "mic_type": 2.0, "noise_level": 2.0] {
        let query = queryFacets[key]?.first ?? ""
        let docValue = doc.facets[key]?.first ?? ""
        if !query.isEmpty && !docValue.isEmpty && query == docValue {
            points += weight
            matches[key] = [query]
        }
    }
    let listWeights: [String: (Double, Double)] = [
        "noise_sources": (1.1, 3.3),
        "training_focus": (0.65, 2.6),
        "topic_terms": (0.35, 2.1),
    ]
    for (key, rule) in listWeights {
        let queryValues = Dictionary(uniqueKeysWithValues: (queryFacets[key] ?? []).map { ($0.lowercased(), $0) })
        let docValues = Dictionary(uniqueKeysWithValues: (doc.facets[key] ?? []).map { ($0.lowercased(), $0) })
        let overlap = Set(queryValues.keys).intersection(Set(docValues.keys)).sorted()
        if !overlap.isEmpty {
            points += min(rule.1, Double(overlap.count) * rule.0)
            matches[key] = overlap.prefix(6).compactMap { queryValues[$0] }
        }
    }
    return (min(14.0, points), matches)
}

private func recencyPoints(_ doc: [String: Any]) -> Double {
    let text = stringValue(doc["created_at"])
    if text.isEmpty {
        return 0.0
    }
    let date = NativePolicyCaches.parseDate(text)
    guard let date else {
        return 0.0
    }
    let ageDays = max(0.0, Date().timeIntervalSince(date) / 86_400.0)
    return rounded(max(0.0, min(2.5, 2.5 * exp(-ageDays / 180.0))), places: 4)
}

private enum NativePolicyCaches {
    static let tokenRegex = try? NSRegularExpression(pattern: #"[0-9A-Za-z_]+|[가-힣]+"#)
    private static let dateParsers = NativePolicyDateParsers()

    static func parseDate(_ text: String) -> Date? {
        dateParsers.parse(text)
    }
}

private final class NativePolicyDateParsers: @unchecked Sendable {
    private static let dateLock = NSLock()
    private let isoFormatter = ISO8601DateFormatter()
    private let pythonFormatters: [DateFormatter] = {
        ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd'T'HH:mm:ss"].map { format in
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            formatter.dateFormat = format
            return formatter
        }
    }()

    func parse(_ text: String) -> Date? {
        Self.dateLock.lock()
        defer { Self.dateLock.unlock() }
        if let date = isoFormatter.date(from: text) {
            return date
        }
        for formatter in pythonFormatters {
            if let date = formatter.date(from: text) {
                return date
            }
        }
        return nil
    }
}
