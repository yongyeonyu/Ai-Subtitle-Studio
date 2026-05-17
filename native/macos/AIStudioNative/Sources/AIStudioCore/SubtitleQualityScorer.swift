import Foundation

public struct QualityScoreRequest: Decodable, Sendable {
    public var segments: [QualityScoreSegment]
    public var settings: QualityScoreSettings

    public init(segments: [QualityScoreSegment], settings: QualityScoreSettings = QualityScoreSettings()) {
        self.segments = segments
        self.settings = settings
    }

    private enum CodingKeys: String, CodingKey {
        case segments
        case settings
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        segments = (try? container.decode([QualityScoreSegment].self, forKey: .segments)) ?? []
        settings = (try? container.decode(QualityScoreSettings.self, forKey: .settings)) ?? QualityScoreSettings()
    }
}

public struct QualityScoreSettings: Decodable, Sendable {
    private var doubles: [String: Double]

    public init(_ doubles: [String: Double] = [:]) {
        self.doubles = doubles
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicCodingKey.self)
        var out: [String: Double] = [:]
        for key in container.allKeys {
            if let value = try? container.decode(Double.self, forKey: key) {
                out[key.stringValue] = value
            } else if let value = try? container.decode(Int.self, forKey: key) {
                out[key.stringValue] = Double(value)
            } else if let value = try? container.decode(String.self, forKey: key),
                      let number = Double(value) {
                out[key.stringValue] = number
            }
        }
        doubles = out
    }

    public func double(_ key: String, default fallback: Double) -> Double {
        doubles[key] ?? fallback
    }
}

public struct QualityScoreResponse: Codable, Equatable, Sendable {
    public var metrics: [SubtitleQualityMetric]

    public init(metrics: [SubtitleQualityMetric]) {
        self.metrics = metrics
    }
}

public struct SubtitleQualityMetric: Codable, Equatable, Sendable {
    public var confidenceScore: Double?
    public var confidenceLabel: String
    public var confidenceReason: String
    public var flags: [String]
    public var asrMetadataScore: Double?
    public var vadAlignmentScore: Double?
    public var wordTimestampScore: Double?
    public var timingScore: Double?
    public var repetitionScore: Double?
    public var contextScore: Double?
    public var correctionMemoryScore: Double?
    public var hallucinationPenalty: Double?

    private enum CodingKeys: String, CodingKey {
        case confidenceScore = "confidence_score"
        case confidenceLabel = "confidence_label"
        case confidenceReason = "confidence_reason"
        case flags
        case asrMetadataScore = "asr_metadata_score"
        case vadAlignmentScore = "vad_alignment_score"
        case wordTimestampScore = "word_timestamp_score"
        case timingScore = "timing_score"
        case repetitionScore = "repetition_score"
        case contextScore = "context_score"
        case correctionMemoryScore = "correction_memory_score"
        case hallucinationPenalty = "hallucination_penalty"
    }
}

public struct QualityScoreSegment: Decodable, Sendable {
    public var start: Double?
    public var end: Double?
    public var text: String
    public var words: [QualityWord]
    public var asrMetadata: QualityASRMetadata
    public var quality: QualityInput
    public var llmRewritePolicy: LLMRewritePolicy

    private enum CodingKeys: String, CodingKey {
        case start
        case end
        case text
        case words
        case asrMetadata = "asr_metadata"
        case quality
        case llmRewritePolicy = "_llm_rewrite_policy"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        start = Self.decodeDouble(container, .start)
        end = Self.decodeDouble(container, .end)
        text = (try? container.decode(String.self, forKey: .text)) ?? ""
        words = (try? container.decode([QualityWord].self, forKey: .words)) ?? []
        asrMetadata = (try? container.decode(QualityASRMetadata.self, forKey: .asrMetadata)) ?? QualityASRMetadata()
        quality = (try? container.decode(QualityInput.self, forKey: .quality)) ?? QualityInput()
        llmRewritePolicy = (try? container.decode(LLMRewritePolicy.self, forKey: .llmRewritePolicy)) ?? LLMRewritePolicy()
    }

    static func decodeDouble<K: CodingKey>(_ container: KeyedDecodingContainer<K>, _ key: K) -> Double? {
        if let value = try? container.decode(Double.self, forKey: key) {
            return value
        }
        if let value = try? container.decode(Int.self, forKey: key) {
            return Double(value)
        }
        if let value = try? container.decode(String.self, forKey: key) {
            return Double(value)
        }
        return nil
    }
}

public struct QualityWord: Decodable, Sendable {
    public var word: String
    public var start: Double?
    public var end: Double?

    private enum CodingKeys: String, CodingKey {
        case word
        case text
        case start
        case end
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        word = (try? container.decode(String.self, forKey: .word))
            ?? (try? container.decode(String.self, forKey: .text))
            ?? ""
        start = QualityScoreSegment.decodeDouble(container, .start)
        end = QualityScoreSegment.decodeDouble(container, .end)
    }
}

public struct QualityASRMetadata: Decodable, Sendable {
    public var avgLogprob: Double?
    public var compressionRatio: Double?
    public var noSpeechProb: Double?
    public var wordConfidence: Double?
    public var languageProbability: Double?
    public var words: [QualityWord]
    public var vadAlignment: VADAlignment
    public var hallucinationRisk: HallucinationRisk

    private enum CodingKeys: String, CodingKey {
        case avgLogprob = "avg_logprob"
        case compressionRatio = "compression_ratio"
        case noSpeechProb = "no_speech_prob"
        case wordConfidence = "word_confidence"
        case languageProbability = "language_probability"
        case words
        case vadAlignment = "vad_alignment"
        case hallucinationRisk = "hallucination_risk"
    }

    public init() {
        words = []
        vadAlignment = VADAlignment()
        hallucinationRisk = HallucinationRisk()
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        avgLogprob = QualityScoreSegment.decodeDouble(container, .avgLogprob)
        compressionRatio = QualityScoreSegment.decodeDouble(container, .compressionRatio)
        noSpeechProb = QualityScoreSegment.decodeDouble(container, .noSpeechProb)
        wordConfidence = QualityScoreSegment.decodeDouble(container, .wordConfidence)
        languageProbability = QualityScoreSegment.decodeDouble(container, .languageProbability)
        words = (try? container.decode([QualityWord].self, forKey: .words)) ?? []
        vadAlignment = (try? container.decode(VADAlignment.self, forKey: .vadAlignment)) ?? VADAlignment()
        hallucinationRisk = (try? container.decode(HallucinationRisk.self, forKey: .hallucinationRisk)) ?? HallucinationRisk()
    }
}

public struct VADAlignment: Decodable, Sendable {
    public var overlapRatio: Double?

    private enum CodingKeys: String, CodingKey {
        case overlapRatio = "vad_overlap_ratio"
    }

    public init(overlapRatio: Double? = nil) {
        self.overlapRatio = overlapRatio
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        overlapRatio = QualityScoreSegment.decodeDouble(container, .overlapRatio)
    }
}

public struct HallucinationRisk: Decodable, Sendable {
    public var risk: Double?
    public var flags: [String]

    private enum CodingKeys: String, CodingKey {
        case risk
        case flags
    }

    public init(risk: Double? = nil, flags: [String] = []) {
        self.risk = risk
        self.flags = flags
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        risk = QualityScoreSegment.decodeDouble(container, .risk)
        flags = (try? container.decode([String].self, forKey: .flags)) ?? []
    }
}

public struct QualityInput: Decodable, Sendable {
    public var flags: [String]
    public var vadAlignmentScore: Double?

    private enum CodingKeys: String, CodingKey {
        case flags
        case vadAlignmentScore = "vad_alignment_score"
    }

    public init(flags: [String] = [], vadAlignmentScore: Double? = nil) {
        self.flags = flags
        self.vadAlignmentScore = vadAlignmentScore
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        flags = (try? container.decode([String].self, forKey: .flags)) ?? []
        vadAlignmentScore = QualityScoreSegment.decodeDouble(container, .vadAlignmentScore)
    }
}

public struct LLMRewritePolicy: Decodable, Sendable {
    public var changed: Bool
    public var confidence: String
    public var scorePenalty: Double?

    private enum CodingKeys: String, CodingKey {
        case changed
        case confidence
        case scorePenalty = "score_penalty"
    }

    public init(changed: Bool = false, confidence: String = "", scorePenalty: Double? = nil) {
        self.changed = changed
        self.confidence = confidence
        self.scorePenalty = scorePenalty
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        changed = (try? container.decode(Bool.self, forKey: .changed)) ?? false
        confidence = ((try? container.decode(String.self, forKey: .confidence)) ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        scorePenalty = QualityScoreSegment.decodeDouble(container, .scorePenalty)
    }
}

private struct DynamicCodingKey: CodingKey {
    var stringValue: String
    var intValue: Int?

    init?(stringValue: String) {
        self.stringValue = stringValue
    }

    init?(intValue: Int) {
        self.stringValue = String(intValue)
        self.intValue = intValue
    }
}

public enum SubtitleQualityScorer {
    public static func score(_ request: QualityScoreRequest) -> QualityScoreResponse {
        var previousTexts: [String] = []
        let metrics = request.segments.map { segment in
            let metric = scoreSegment(segment, settings: request.settings, previousTexts: previousTexts)
            previousTexts.append(segment.text)
            return metric
        }
        return QualityScoreResponse(metrics: metrics)
    }

    public static func scoreSegments(_ segments: [QualityScoreSegment], settings: QualityScoreSettings = QualityScoreSettings()) -> [SubtitleQualityMetric] {
        score(QualityScoreRequest(segments: segments, settings: settings)).metrics
    }

    private static func scoreSegment(
        _ segment: QualityScoreSegment,
        settings: QualityScoreSettings,
        previousTexts: [String]
    ) -> SubtitleQualityMetric {
        var flags = segment.quality.flags

        let asrScore = asrMetadataScore(segment, metadata: segment.asrMetadata, flags: &flags)
        let vad = vadScore(segment, flags: &flags)
        let wordScore = wordTimestampScore(segment, flags: &flags)
        let timing = timingScore(segment, flags: &flags, settings: settings)
        let repetition = repetitionScore(segment, previousTexts: previousTexts, flags: &flags)
        let context = contextScore(segment, flags: &flags)
        let memory = memoryScore(segment, flags: &flags)

        let hallucinationPenalty = clipScore((segment.asrMetadata.hallucinationRisk.risk ?? 0.0) * 100.0)
        for flag in segment.asrMetadata.hallucinationRisk.flags {
            addFlag(&flags, flag)
        }

        let weights = scoreWeights(settings)
        let components: [(String, Double?)] = [
            ("asr_metadata_score", asrScore),
            ("vad_alignment_score", vad),
            ("word_timestamp_score", wordScore),
            ("timing_score", timing),
            ("repetition_score", repetition),
            ("context_score", context),
            ("correction_memory_score", memory),
        ]
        let available = components.compactMap { key, value -> (String, Double)? in
            guard let value else { return nil }
            return (key, value)
        }

        var score: Double?
        if available.isEmpty {
            score = nil
        } else {
            let weightSum = available.reduce(0.0) { $0 + max(0.0, weights[$1.0] ?? 0.0) }
            let raw = available.reduce(0.0) { $0 + $1.1 * max(0.0, weights[$1.0] ?? 0.0) } / max(weightSum, 0.001)
            score = clipScore(raw - hallucinationPenalty * max(0.0, weights["hallucination_penalty"] ?? 0.0))
        }

        let rewriteConfidence = applyLLMRewritePenalty(segment, score: &score, flags: &flags)
        var label = labelForScore(score)
        if score == nil || shouldForceGrayForMissingEvidence(segment, flags: flags, wordScore: wordScore, timingScore: timing, contextScore: context) {
            label = "gray"
        } else if rewriteConfidence == "medium" {
            score = clipScore(min(score ?? 72.0, 72.0))
            label = "yellow"
        } else if rewriteConfidence == "low" {
            score = clipScore(min(score ?? 58.0, 58.0))
            label = "red"
        }

        let reasons = flags.isEmpty ? ["ok"] : Array(flags.prefix(4))
        return SubtitleQualityMetric(
            confidenceScore: score,
            confidenceLabel: label,
            confidenceReason: reasons.joined(separator: ", "),
            flags: flags,
            asrMetadataScore: asrScore,
            vadAlignmentScore: vad,
            wordTimestampScore: wordScore,
            timingScore: timing,
            repetitionScore: repetition,
            contextScore: context,
            correctionMemoryScore: memory,
            hallucinationPenalty: hallucinationPenalty
        )
    }

    private static func asrMetadataScore(_ segment: QualityScoreSegment, metadata: QualityASRMetadata, flags: inout [String]) -> Double {
        let missing = metadata.noSpeechProb == nil
            && metadata.avgLogprob == nil
            && metadata.compressionRatio == nil
            && metadata.wordConfidence == nil
            && metadata.languageProbability == nil
            && metadata.words.isEmpty
        if missing {
            addFlag(&flags, "metadata_missing")
            let compact = compactText(segment.text)
            if !compact.isEmpty && duration(segment) >= 0.35 && compact.count <= 18 && looksStructurallyValidText(segment.text) {
                return 52.0
            }
            return 30.0
        }

        var score = 78.0
        if let noSpeech = metadata.noSpeechProb {
            score -= max(0.0, noSpeech - 0.2) * 55.0
            if noSpeech >= 0.6 {
                addFlag(&flags, "high_no_speech_prob")
            }
        } else {
            addFlag(&flags, "no_speech_prob_missing")
        }

        if let avgLogprob = metadata.avgLogprob {
            score += max(-22.0, min(12.0, (avgLogprob + 0.8) * 18.0))
            if avgLogprob <= -1.0 {
                addFlag(&flags, "low_avg_logprob")
            }
        } else {
            addFlag(&flags, "avg_logprob_missing")
        }

        if let compression = metadata.compressionRatio, compression > 2.4 {
            score -= min(24.0, (compression - 2.4) * 18.0)
            addFlag(&flags, "high_compression_ratio")
        }

        if let wordConfidence = metadata.wordConfidence {
            score += (wordConfidence - 0.5) * 24.0
            if wordConfidence < 0.45 {
                addFlag(&flags, "low_word_confidence")
            }
        }

        if let languageProbability = metadata.languageProbability, languageProbability < 0.45 {
            score -= 12.0
            addFlag(&flags, "low_language_probability")
        }
        return clipScore(score)
    }

    private static func vadScore(_ segment: QualityScoreSegment, flags: inout [String]) -> Double? {
        if let score = segment.quality.vadAlignmentScore {
            if score < 20 {
                addFlag(&flags, "outside_vad_speech")
            }
            return clipScore(score)
        }
        guard let ratio = segment.asrMetadata.vadAlignment.overlapRatio else {
            return nil
        }
        let score = ratio * 100.0
        if score < 20 {
            addFlag(&flags, "outside_vad_speech")
        }
        return clipScore(score)
    }

    private static func wordTimestampScore(_ segment: QualityScoreSegment, flags: inout [String]) -> Double {
        let words = segment.words.isEmpty ? segment.asrMetadata.words : segment.words
        if words.isEmpty {
            addFlag(&flags, "word_timestamps_missing")
            let compact = compactText(segment.text)
            if !compact.isEmpty && duration(segment) >= 0.35 && compact.count <= 18 && looksStructurallyValidText(segment.text) {
                return 60.0
            }
            return 35.0
        }

        var valid = 0
        var monotonic = 0
        var previousEnd: Double?
        for word in words {
            guard let start = word.start, let end = word.end, end > start else {
                continue
            }
            valid += 1
            if previousEnd == nil || start >= (previousEnd ?? 0.0) - 0.03 {
                monotonic += 1
            }
            previousEnd = end
        }
        let validRatio = Double(valid) / Double(max(1, words.count))
        let monotonicRatio = Double(monotonic) / Double(max(1, valid))
        let score = validRatio * 60.0 + monotonicRatio * 40.0
        if validRatio < 0.8 {
            addFlag(&flags, "word_timestamp_invalid")
        }
        if monotonicRatio < 0.9 {
            addFlag(&flags, "word_timestamp_overlap")
        }
        return clipScore(score)
    }

    private static func timingScore(_ segment: QualityScoreSegment, flags: inout [String], settings: QualityScoreSettings) -> Double {
        let duration = duration(segment)
        let textLength = compactText(segment.text).count
        if duration <= 0.0 {
            addFlag(&flags, "invalid_timing")
            return 0.0
        }

        let minDuration = settings.double("sub_min_duration", default: 0.2)
        let maxDuration = settings.double("sub_max_duration", default: 6.0)
        let maxCPS = settings.double("sub_max_cps", default: 12.0)
        let cps = Double(textLength) / max(duration, 0.01)
        var score = 100.0
        if duration < minDuration {
            score -= min(50.0, (minDuration - duration) * 120.0)
            addFlag(&flags, "too_short_duration")
        }
        if duration > maxDuration {
            score -= min(45.0, (duration - maxDuration) * 8.0)
            addFlag(&flags, "too_long_duration")
        }
        if cps > maxCPS {
            score -= min(55.0, (cps - maxCPS) * 5.0)
            addFlag(&flags, "high_cps")
        }
        if textLength == 0 {
            score = 0.0
            addFlag(&flags, "empty_text")
        }
        return clipScore(score)
    }

    private static func repetitionScore(_ segment: QualityScoreSegment, previousTexts: [String], flags: inout [String]) -> Double {
        let text = compactText(segment.text)
        if text.count < 5 {
            return 92.0
        }
        for previous in previousTexts.suffix(40).reversed() {
            let prev = compactText(previous)
            if prev.count < 5 {
                continue
            }
            if text.contains(prev) || prev.contains(text) {
                addFlag(&flags, "repeated_phrase_risk")
                return 35.0
            }
            let matchSize = longestCommonSubstringLength(prev, text)
            if matchSize >= 8 && Double(matchSize) / Double(max(1, text.count)) >= 0.7 {
                addFlag(&flags, "repeated_phrase_risk")
                return 45.0
            }
        }
        return 100.0
    }

    private static func contextScore(_ segment: QualityScoreSegment, flags: inout [String]) -> Double {
        let text = segment.text.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            addFlag(&flags, "empty_text")
            return 0.0
        }
        var score = 92.0
        if containsTimecode(text) {
            score -= 50.0
            addFlag(&flags, "timecode_in_text")
        }
        if !containsLanguageCharacter(text) {
            if looksValidNonLanguageToken(text) {
                score -= 6.0
            } else {
                score -= 45.0
                addFlag(&flags, "text_has_no_language_chars")
            }
        }
        if text.count <= 1 {
            score -= 8.0
            addFlag(&flags, "very_short_text")
        }
        return clipScore(score)
    }

    private static func memoryScore(_ segment: QualityScoreSegment, flags: inout [String]) -> Double {
        if segment.quality.flags.contains("wrong_answer_memory_hit") {
            addFlag(&flags, "wrong_answer_memory_hit")
            return 35.0
        }
        return 75.0
    }

    private static func applyLLMRewritePenalty(_ segment: QualityScoreSegment, score: inout Double?, flags: inout [String]) -> String? {
        guard segment.llmRewritePolicy.changed else {
            return nil
        }
        let confidence = segment.llmRewritePolicy.confidence.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if confidence == "high" {
            addFlag(&flags, "llm_confident_rewrite")
            return nil
        }
        addFlag(&flags, "llm_uncertain_rewrite")
        let penalty = segment.llmRewritePolicy.scorePenalty ?? 18.0
        score = clipScore((score ?? 72.0) - penalty)
        return confidence.isEmpty ? "low" : confidence
    }

    private static func scoreWeights(_ settings: QualityScoreSettings) -> [String: Double] {
        [
            "asr_metadata_score": settings.double("score_weight_asr_metadata", default: 0.25),
            "vad_alignment_score": settings.double("score_weight_vad_alignment", default: 0.20),
            "word_timestamp_score": settings.double("score_weight_word_timestamp", default: 0.15),
            "timing_score": settings.double("score_weight_timing", default: 0.10),
            "repetition_score": settings.double("score_weight_repetition", default: 0.10),
            "context_score": settings.double("score_weight_context", default: 0.10),
            "correction_memory_score": settings.double("score_weight_memory", default: 0.05),
            "hallucination_penalty": settings.double("score_weight_hallucination_penalty", default: 0.30),
        ]
    }

    private static func duration(_ segment: QualityScoreSegment) -> Double {
        let start = segment.start ?? 0.0
        let end = segment.end ?? start
        return max(0.0, end - start)
    }

    private static func compactText(_ text: String) -> String {
        String(text.filter { !$0.isWhitespace })
    }

    private static func labelForScore(_ score: Double?) -> String {
        guard let score else { return "gray" }
        if score >= 85 {
            return "green"
        }
        if score >= 65 {
            return "yellow"
        }
        if score >= 35 {
            return "red"
        }
        return "gray"
    }

    private static func clipScore(_ value: Double) -> Double {
        let clipped = max(0.0, min(100.0, value))
        return (clipped * 1_000_000.0).rounded() / 1_000_000.0
    }

    private static func addFlag(_ flags: inout [String], _ flag: String) {
        guard !flag.isEmpty, !flags.contains(flag) else {
            return
        }
        flags.append(flag)
    }

    private static func containsTimecode(_ text: String) -> Bool {
        let pattern = #"(\d{1,2}:\d{2}(:\d{2})?([,.]\d{1,3})?)"#
        return text.range(of: pattern, options: .regularExpression) != nil
    }

    private static func containsLanguageCharacter(_ text: String) -> Bool {
        for scalar in text.unicodeScalars {
            if ("a"..."z").contains(Character(scalar)) || ("A"..."Z").contains(Character(scalar)) {
                return true
            }
            if scalar.value >= 0xAC00 && scalar.value <= 0xD7A3 {
                return true
            }
        }
        return false
    }

    private static func looksValidNonLanguageToken(_ text: String) -> Bool {
        let compact = compactText(text)
        guard !compact.isEmpty else { return false }
        if compact.range(of: #"^\d{2,6}$"#, options: .regularExpression) != nil {
            return true
        }
        let hasDigit = compact.unicodeScalars.contains { CharacterSet.decimalDigits.contains($0) }
        guard hasDigit else { return false }
        return compact.range(of: #"^[0-9A-Za-z][0-9A-Za-z%+./#:_-]*$"#, options: .regularExpression) != nil
    }

    private static func looksStructurallyValidText(_ text: String) -> Bool {
        containsLanguageCharacter(text) || looksValidNonLanguageToken(text)
    }

    private static func shouldForceGrayForMissingEvidence(
        _ segment: QualityScoreSegment,
        flags: [String],
        wordScore: Double,
        timingScore: Double,
        contextScore: Double
    ) -> Bool {
        guard flags.contains("metadata_missing"), wordScore <= 35.0 else {
            return false
        }
        guard looksStructurallyValidText(segment.text) else {
            return true
        }
        if timingScore < 55.0 || contextScore < 65.0 {
            return true
        }
        let blocking: Set<String> = [
            "invalid_timing",
            "too_short_duration",
            "high_cps",
            "timecode_in_text",
            "high_no_speech_prob",
            "non_speech_hallucination_risk",
            "known_hallucination_phrase",
        ]
        return !blocking.isDisjoint(with: Set(flags))
    }

    private static func longestCommonSubstringLength(_ left: String, _ right: String) -> Int {
        let a = Array(left)
        let b = Array(right)
        guard !a.isEmpty, !b.isEmpty else { return 0 }
        var previous = Array(repeating: 0, count: b.count + 1)
        var best = 0
        for i in 1...a.count {
            var current = Array(repeating: 0, count: b.count + 1)
            for j in 1...b.count where a[i - 1] == b[j - 1] {
                let value = previous[j - 1] + 1
                current[j] = value
                if value > best {
                    best = value
                }
            }
            previous = current
        }
        return best
    }
}
