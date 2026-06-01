import Foundation

public enum AppleSpeechSupportNative {
    public static func probe(payload: [String: Any]) -> [String: Any] {
        let locale = String(describing: payload["locale"] ?? "ko-KR")
        #if os(macOS)
        let transcriberClass: AnyClass? = NSClassFromString("Speech.SpeechTranscriber") ?? NSClassFromString("SpeechTranscriber")
        let detectorClass: AnyClass? = NSClassFromString("Speech.SpeechDetector") ?? NSClassFromString("SpeechDetector")
        let available = transcriberClass != nil
        let detectorAvailable = detectorClass != nil
        let reason = available ? "runtime_class_available" : "speech_framework_missing_or_unsupported"
        return [
            "available": available,
            "detector_available": detectorAvailable,
            "locale": locale,
            "reason": reason,
        ]
        #else
        return [
            "available": false,
            "detector_available": false,
            "locale": locale,
            "reason": "platform_unsupported",
        ]
        #endif
    }
}
