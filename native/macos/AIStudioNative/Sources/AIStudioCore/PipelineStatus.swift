import Foundation

public enum PipelineStatusNative {
    static let stageLabels: [String: String] = [
        "cut_boundary": "컷 경계",
        "preprocess": "전처리",
        "audio": "음성",
        "stt1": "STT 1",
        "stt2": "STT 2",
        "vad": "VAD",
        "subtitle_llm": "자막 LLM",
        "roughcut_llm": "러프컷 LLM",
        "lora": "LoRA",
        "deep_learning": "딥러닝",
    ]

    static let stageOrder = [
        "cut_boundary",
        "preprocess",
        "audio",
        "stt1",
        "stt2",
        "vad",
        "subtitle_llm",
        "roughcut_llm",
        "lora",
        "deep_learning",
    ]

    static let htmlBreakTokens = ["<br>", "<br/>", "<br />"]
    static let cutBoundaryTokens = lowercased([
        "[컷 경계]", "컷 경계", "scan-cut", "scan cut", "cut boundary", "cut_boundary", "scene cut", "pyramid60",
    ])
    static let preprocessTokens = lowercased([
        "[전처리]", "오디오 추출", "ffmpeg 오디오", "전처리",
    ])
    static let audioTokens = lowercased([
        "[음성]", "음량", "필터", "deepfilter", "rnnoise", "resemble", "clearvoice", "노이즈", "보컬",
    ])
    static let subtitleLLMTokens = lowercased([
        "[자막 llm]", "llm", "최적화", "교정", "분리",
    ])
    static let vadTokens = lowercased([
        "[vad]", "silero", "ten_vad", "ten vad", "검수", "위치 재계산", "음성 섹터",
    ])
    static let stt2Tokens = lowercased([
        "저점 구간", "stt2 확인", "stt2 결과로 보강",
    ])
    static let loraTokens = lowercased([
        "[lora]", "lora", "개인화", "텍스트 lora", "lo-ra",
    ])
    static let deepLearningTokens = lowercased([
        "[딥러닝]", "deep learning", "deep-learning", "deep subtitle", "deep policy",
    ])
    static let sttTokens = lowercased([
        "[stt", "whisper", "stt", "자막 생성",
    ])
    static let dualSTTStageKeys: Set<String> = ["stt1", "stt2"]
    static let sttSubtitleLLMStageKeys: Set<String> = ["stt1", "subtitle_llm"]
    static let ensembleSTTSubtitleLLMStageKeys: Set<String> = ["stt1", "stt2", "subtitle_llm"]

    public static func summary(payload: [String: Any]) -> [String: Any] {
        let statusText = stringValue(payload["status_text"])
        let sttEnsembleEnabled = boolValue(payload["stt_ensemble_enabled"])
        let reduced = summarize(statusText: statusText, sttEnsembleEnabled: sttEnsembleEnabled)
        return [
            "keys": orderedKeys(reduced.latestKeys),
            "all_keys": orderedKeys(reduced.allKeys),
            "label": reduced.label,
            "active": !reduced.latestKeys.isEmpty,
        ]
    }

    public static func summarize(
        statusText: String,
        sttEnsembleEnabled: Bool = false
    ) -> (latestKeys: Set<String>, allKeys: Set<String>, label: String) {
        if statusText.isEmpty {
            return ([], [], "")
        }
        let (normalized, lines) = normalizedLines(statusText)
        let latestKeys = blobStageKeys(
            normalized: normalized,
            lines: lines,
            sttEnsembleEnabled: sttEnsembleEnabled,
            collectAll: false
        )
        let allKeys = blobStageKeys(
            normalized: normalized,
            lines: lines,
            sttEnsembleEnabled: sttEnsembleEnabled,
            collectAll: true
        )
        return (latestKeys, allKeys, stageLabel(from: latestKeys))
    }

    static func normalizedLines(_ blob: String) -> (String, [String]) {
        let normalized = htmlBreakTokens.reduce(blob) { partial, token in
            partial.replacingOccurrences(of: token, with: "\n")
        }
        let lines = normalized
            .split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return (normalized, lines)
    }

    static func blobStageKeys(
        normalized: String,
        lines: [String],
        sttEnsembleEnabled: Bool,
        collectAll: Bool
    ) -> Set<String> {
        if normalized.isEmpty {
            return []
        }
        if collectAll {
            var keys: Set<String> = []
            for line in lines {
                keys.formUnion(stageKeys(from: line, sttEnsembleEnabled: sttEnsembleEnabled))
            }
            if keys.isEmpty {
                keys.formUnion(stageKeys(from: normalized, sttEnsembleEnabled: sttEnsembleEnabled))
            }
            return keys
        }
        for line in lines.reversed() {
            let keys = stageKeys(from: line, sttEnsembleEnabled: sttEnsembleEnabled)
            if !keys.isEmpty {
                return keys
            }
        }
        return stageKeys(from: normalized, sttEnsembleEnabled: sttEnsembleEnabled)
    }

    static func stageKeys(from blob: String, sttEnsembleEnabled: Bool) -> Set<String> {
        let lowered = blob.lowercased()
        if lowered.isEmpty {
            return []
        }
        if containsAny(lowered, tokens: cutBoundaryTokens) {
            return ["cut_boundary"]
        }
        if containsAny(lowered, tokens: preprocessTokens) {
            return ["preprocess"]
        }
        if containsAny(lowered, tokens: audioTokens) {
            return ["audio"]
        }
        if lowered.contains("[stt+자막 llm]") {
            var keys: Set<String> = ["stt1", "subtitle_llm"]
            if sttEnsembleEnabled {
                keys.insert("stt2")
            }
            return keys
        }
        if containsAny(lowered, tokens: subtitleLLMTokens) {
            return ["subtitle_llm"]
        }
        if containsAny(lowered, tokens: vadTokens) {
            return ["vad"]
        }
        if lowered.contains("stt1 우선") {
            return ["stt1"]
        }
        if containsAny(lowered, tokens: stt2Tokens) {
            return ["stt2"]
        }
        if containsAny(lowered, tokens: loraTokens) {
            return ["lora"]
        }
        if containsAny(lowered, tokens: deepLearningTokens) {
            return ["deep_learning"]
        }
        if containsAny(lowered, tokens: sttTokens) {
            var keys: Set<String> = ["stt1"]
            if sttEnsembleEnabled {
                keys.insert("stt2")
            }
            return keys
        }
        return []
    }

    static func stageLabel(from keys: Set<String>) -> String {
        if keys.isEmpty {
            return ""
        }
        if keys == dualSTTStageKeys {
            return "STT 1/2"
        }
        if keys == sttSubtitleLLMStageKeys || keys == ensembleSTTSubtitleLLMStageKeys {
            return "STT+자막 LLM"
        }
        for key in stageOrder where keys.contains(key) {
            return stageLabels[key] ?? "대기"
        }
        return "대기"
    }

    static func orderedKeys(_ keys: Set<String>) -> [String] {
        stageOrder.filter { keys.contains($0) }
    }

    static func containsAny(_ blob: String, tokens: [String]) -> Bool {
        tokens.contains { blob.contains($0) }
    }

    static func lowercased(_ values: [String]) -> [String] {
        values.map { $0.lowercased() }
    }

    static func stringValue(_ value: Any?) -> String {
        if let text = value as? String {
            return text
        }
        if let value {
            return String(describing: value)
        }
        return ""
    }

    static func boolValue(_ value: Any?) -> Bool {
        switch value {
        case let value as Bool:
            return value
        case let value as NSNumber:
            return value.boolValue
        case let value as String:
            switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "1", "true", "yes", "on":
                return true
            case "0", "false", "no", "off":
                return false
            default:
                return false
            }
        default:
            return false
        }
    }
}
