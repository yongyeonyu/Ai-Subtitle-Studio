import Foundation

public enum StartupDiagnosticsNative {
    public static func build(payload: [String: Any]) -> [String: Any] {
        let mediaPath = stringValue(payload["media_path"])
        let mediaName = stringValue(payload["media_name"], default: URL(fileURLWithPath: mediaPath).lastPathComponent)
        let media = dictValue(payload["media"])
        let audio = dictValue(payload["audio"])
        let settings = dictValue(payload["settings"])
        let cutBoundaries = arrayValue(payload["cut_boundaries"])
        let provisionalBoundaries = arrayValue(payload["provisional_cut_boundaries"])
        let expectedTimeSec = doubleValue(payload["expected_time_sec"])
        let speakerCountHint = payload["speaker_count_hint"]

        let durationSec = doubleValue(media["duration_sec"], default: doubleValue(media["duration"]))
        let fps = doubleValue(media["fps"])
        let audioQuality = audioQualityProfile(audio)
        let cutDensity = cutDensityProfile(
            cutBoundaries: cutBoundaries,
            provisionalBoundaries: provisionalBoundaries,
            durationSec: durationSec
        )
        let speakers = speakerHint(settings: settings, hint: speakerCountHint)
        let recommendation = recommendPipeline(
            durationSec: durationSec,
            fps: fps,
            audioQuality: audioQuality,
            cutDensity: cutDensity,
            speakerCount: intValue(speakers["count"], default: 1)
        )
        let expected = max(0.0, expectedTimeSec)

        return [
            "schema": "ai_subtitle_studio.startup_diagnostic.v1",
            "created_at": createdAtString(),
            "media_path": mediaPath,
            "media_name": mediaName,
            "media": [
                "duration_sec": roundTo(durationSec, digits: 3),
                "duration_label": durationLabel(durationSec),
                "fps": roundTo(fps, digits: 3),
                "width": intValue(media["width"]),
                "height": intValue(media["height"]),
                "info_txt": stringValue(media["info_txt"]),
            ],
            "audio": merge(audio, with: ["quality": audioQuality]),
            "speakers": speakers,
            "cut_density": cutDensity,
            "estimated_processing_sec": expected > 0.0 ? roundTo(expected, digits: 3) : 0.0,
            "estimated_processing_label": processingLabel(expected),
            "estimated_processing_source": expected > 0.0 ? "history" : "unknown",
            "recommended_pipeline": recommendation,
        ]
    }

    public static func attachExpected(payload: [String: Any]) -> [String: Any] {
        var diagnostic = dictValue(payload["diagnostic"])
        let expected = max(0.0, doubleValue(payload["expected_time_sec"]))
        let source = stringValue(payload["source"], default: "history")
        diagnostic["estimated_processing_sec"] = expected > 0.0 ? roundTo(expected, digits: 3) : 0.0
        diagnostic["estimated_processing_label"] = processingLabel(expected)
        diagnostic["estimated_processing_source"] = expected > 0.0 ? source : "unknown"
        return diagnostic
    }

    public static func formatLog(payload: [String: Any]) -> [String: Any] {
        let diagnostic = dictValue(payload["diagnostic"])
        let media = dictValue(diagnostic["media"])
        let audio = dictValue(diagnostic["audio"])
        let quality = dictValue(audio["quality"])
        let cutDensity = dictValue(diagnostic["cut_density"])
        let recommendation = dictValue(diagnostic["recommended_pipeline"])
        let reasons = arrayValue(recommendation["reasons"])
        let reasonText = reasons
            .prefix(4)
            .map { reasonLabel(stringValue($0)) }
            .filter { !$0.isEmpty }
            .joined(separator: ", ")
        let joinedReasons = reasonText.isEmpty ? "기본 안정값" : reasonText

        let sampleRate = intValue(audio["sample_rate"])
        let channels = intValue(audio["channels"])
        let sampleLabel = sampleRate > 0 ? String(format: "%.1fkHz", Double(sampleRate) / 1000.0) : "샘플레이트 미상"
        let channelLabel = channels > 0 ? "\(channels)ch" : "채널 미상"

        let perMinuteLabel = String(format: "%.2f", doubleValue(cutDensity["per_minute"]))
        let lines = [
            "  🩺 [시작 진단] \(stringValue(diagnostic["media_name"])) · \(stringValue(media["duration_label"], default: "-")) · \(String(format: "%.2f", doubleValue(media["fps"])))fps · \(intValue(media["width"]))x\(intValue(media["height"]))",
            "  🩺 [시작 진단] 오디오 \(stringValue(quality["summary"], default: "미상")) · 노이즈 추정 \(stringValue(quality["noise_label"], default: "미상")) · \(sampleLabel) · \(channelLabel)",
            "  🩺 [시작 진단] 컷 밀도 \(stringValue(cutDensity["label"], default: "미상")) · 정식 \(intValue(cutDensity["verified_count"]))개 · 임시 \(intValue(cutDensity["provisional_count"]))개 · \(perMinuteLabel)/분",
            "  🩺 [시작 진단] 추천 \(stringValue(recommendation["label"], default: "균형 모드")) · 예상 \(stringValue(diagnostic["estimated_processing_label"], default: "예상불가")) · 근거: \(joinedReasons)",
        ]
        return ["lines": lines]
    }

    private static func createdAtString() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return formatter.string(from: Date())
    }

    private static func durationLabel(_ seconds: Double) -> String {
        guard seconds > 0 else { return "-" }
        let total = Int(seconds.rounded())
        let minutes = total / 60
        let sec = total % 60
        let hours = minutes / 60
        let remMinutes = minutes % 60
        if hours > 0 {
            return String(format: "%02d:%02d:%02d", hours, remMinutes, sec)
        }
        return String(format: "%02d:%02d", remMinutes, sec)
    }

    private static func processingLabel(_ seconds: Double) -> String {
        guard seconds > 0 else { return "예상불가" }
        let total = Int(seconds.rounded())
        let minutes = total / 60
        let sec = total % 60
        let hours = minutes / 60
        let remMinutes = minutes % 60
        if hours > 0 {
            return "\(hours)시간 \(remMinutes)분 \(sec)초"
        }
        if remMinutes > 0 {
            return "\(remMinutes)분 \(sec)초"
        }
        return "\(sec)초"
    }

    private static func boundaryTime(_ item: Any) -> Double {
        if let dict = item as? [String: Any] {
            for key in ["timeline_sec", "time", "start", "sec"] {
                if dict[key] != nil {
                    return doubleValue(dict[key])
                }
            }
            return 0.0
        }
        return doubleValue(item)
    }

    private static func audioQualityProfile(_ audioInfo: [String: Any]) -> [String: Any] {
        if !boolValue(audioInfo["has_audio"]) {
            return [
                "score": 0,
                "label": "red",
                "summary": "오디오 없음",
                "noise_estimate": "high",
                "noise_label": "높음",
                "source": "metadata_heuristic",
                "reasons": ["audio_missing"],
            ]
        }

        var score = 100
        var reasons: [String] = []
        let sampleRate = intValue(audioInfo["sample_rate"])
        let bitRate = intValue(audioInfo["bit_rate"])
        let channels = intValue(audioInfo["channels"])

        if sampleRate > 0 && sampleRate < 16_000 {
            score -= 35
            reasons.append("low_sample_rate")
        } else if sampleRate > 0 && sampleRate < 32_000 {
            score -= 15
            reasons.append("medium_sample_rate")
        } else if sampleRate <= 0 {
            score -= 20
            reasons.append("unknown_sample_rate")
        }

        if bitRate > 0 && bitRate < 48_000 {
            score -= 30
            reasons.append("low_bit_rate")
        } else if bitRate > 0 && bitRate < 96_000 {
            score -= 12
            reasons.append("medium_bit_rate")
        } else if bitRate <= 0 {
            score -= 8
            reasons.append("unknown_bit_rate")
        }

        if channels <= 0 {
            score -= 8
            reasons.append("unknown_channels")
        }

        score = max(0, min(100, score))
        let label: String
        let summary: String
        let noise: String
        let noiseLabel: String
        if score >= 75 {
            label = "green"
            summary = "양호"
            noise = "low"
            noiseLabel = "낮음"
        } else if score >= 45 {
            label = "yellow"
            summary = "주의"
            noise = "medium"
            noiseLabel = "중간"
        } else {
            label = "red"
            summary = "복구 필요"
            noise = "high"
            noiseLabel = "높음"
        }

        return [
            "score": score,
            "label": label,
            "summary": summary,
            "noise_estimate": noise,
            "noise_label": noiseLabel,
            "source": "metadata_heuristic",
            "reasons": reasons,
        ]
    }

    private static func cutDensityProfile(
        cutBoundaries: [Any],
        provisionalBoundaries: [Any],
        durationSec: Double
    ) -> [String: Any] {
        let cuts = cutBoundaries.map(boundaryTime).filter { $0 > 0.0 }
        let provisional = provisionalBoundaries.map(boundaryTime).filter { $0 > 0.0 }
        let minutes = max(durationSec / 60.0, 0.0)
        let perMinute = minutes > 0.0 ? Double(cuts.count) / minutes : 0.0
        let level: String
        let label: String
        if perMinute >= 4.0 {
            level = "high"
            label = "높음"
        } else if perMinute >= 1.0 {
            level = "medium"
            label = "중간"
        } else {
            level = "low"
            label = "낮음"
        }
        return [
            "verified_count": cuts.count,
            "provisional_count": provisional.count,
            "per_minute": roundTo(perMinute, digits: 3),
            "level": level,
            "label": label,
        ]
    }

    private static func speakerHint(settings: [String: Any], hint: Any?) -> [String: Any] {
        if let hint, !(hint is NSNull) {
            return [
                "count": max(1, intValue(hint, default: 1)),
                "source": "runtime",
            ]
        }
        return [
            "count": max(1, intValue(settings["max_speakers"], default: 1)),
            "source": "settings",
        ]
    }

    private static func recommendPipeline(
        durationSec: Double,
        fps: Double,
        audioQuality: [String: Any],
        cutDensity: [String: Any],
        speakerCount: Int
    ) -> [String: Any] {
        if durationSec <= 0.0 {
            return [
                "mode": "recovery",
                "label": "복구 모드",
                "score": 100,
                "reasons": ["duration_unknown"],
            ]
        }
        if intValue(audioQuality["score"]) < 35 {
            return [
                "mode": "recovery",
                "label": "복구 모드",
                "score": 95,
                "reasons": ["audio_quality_low"],
            ]
        }

        var score = 0
        var reasons: [String] = []
        if durationSec >= 20.0 * 60.0 {
            score += 2
            reasons.append("long_video")
        } else if durationSec <= 5.0 * 60.0 {
            score -= 1
            reasons.append("short_video")
        }
        if fps >= 50.0 {
            score += 1
            reasons.append("high_fps")
        }
        let cutLevel = stringValue(cutDensity["level"])
        if cutLevel == "high" {
            score += 2
            reasons.append("dense_cuts")
        } else if cutLevel == "low" && durationSec <= 8.0 * 60.0 {
            score -= 1
            reasons.append("simple_cut_structure")
        }
        if speakerCount >= 2 {
            score += 1
            reasons.append("multi_speaker")
        }
        if intValue(audioQuality["score"]) < 70 {
            score += 1
            reasons.append("audio_attention_needed")
        }

        let mode: String
        let label: String
        if score <= -2 {
            mode = "fast"
            label = "빠른 모드"
        } else if score <= 1 {
            mode = "balanced"
            label = "균형 모드"
        } else {
            mode = "precise"
            label = "정밀 모드"
        }
        return [
            "mode": mode,
            "label": label,
            "score": score,
            "reasons": reasons,
        ]
    }

    private static func reasonLabel(_ reason: String) -> String {
        switch reason {
        case "duration_unknown":
            return "길이 확인 필요"
        case "audio_quality_low":
            return "오디오 품질 낮음"
        case "long_video":
            return "긴 영상"
        case "short_video":
            return "짧은 영상"
        case "high_fps":
            return "고FPS"
        case "dense_cuts":
            return "컷 많음"
        case "simple_cut_structure":
            return "단순 컷"
        case "multi_speaker":
            return "복수 화자"
        case "audio_attention_needed":
            return "오디오 주의"
        default:
            return reason
        }
    }

    private static func roundTo(_ value: Double, digits: Int) -> Double {
        guard digits >= 0 else { return value }
        let scale = pow(10.0, Double(digits))
        return (value * scale).rounded() / scale
    }

    private static func merge(_ base: [String: Any], with extra: [String: Any]) -> [String: Any] {
        var out = base
        for (key, value) in extra {
            out[key] = value
        }
        return out
    }

    private static func dictValue(_ value: Any?) -> [String: Any] {
        value as? [String: Any] ?? [:]
    }

    private static func arrayValue(_ value: Any?) -> [Any] {
        value as? [Any] ?? []
    }

    private static func stringValue(_ value: Any?, default defaultValue: String = "") -> String {
        guard let value else { return defaultValue }
        let text = String(describing: value)
        return text.isEmpty ? defaultValue : text
    }

    private static func boolValue(_ value: Any?) -> Bool {
        switch value {
        case let value as Bool:
            return value
        case let value as NSNumber:
            return value.boolValue
        case let value as String:
            return ["1", "true", "yes", "on", "사용", "켜짐"].contains(value.lowercased())
        default:
            return false
        }
    }

    private static func doubleValue(_ value: Any?, default defaultValue: Double = 0.0) -> Double {
        switch value {
        case let value as Double:
            return value.isFinite ? value : defaultValue
        case let value as NSNumber:
            let parsed = value.doubleValue
            return parsed.isFinite ? parsed : defaultValue
        case let value as String:
            let parsed = Double(value) ?? defaultValue
            return parsed.isFinite ? parsed : defaultValue
        default:
            return defaultValue
        }
    }

    private static func intValue(_ value: Any?, default defaultValue: Int = 0) -> Int {
        switch value {
        case let value as Int:
            return value
        case let value as NSNumber:
            return value.intValue
        case let value as String:
            return Int(Double(value) ?? Double(defaultValue))
        default:
            return defaultValue
        }
    }
}
