import XCTest
@testable import AIStudioCore

final class PipelineStatusTests: XCTestCase {
    func testPreprocessStatusWinsOverAudioAndVadWords() {
        let summary = PipelineStatusNative.summarize(
            statusText: "⏳ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중"
        )
        XCTAssertEqual(summary.latestKeys, ["preprocess"])
        XCTAssertEqual(summary.label, "전처리")
    }

    func testParallelLiveStepsCollectAllRelevantStageKeys() {
        let status = [
            "  ▶ [STT1] 진행 상황: 00분 22초 / 02분 59초 (13%)",
            "[STT2] Loading weights: 100%",
            "[LLM-보정차단] 원문 무결성 검사",
        ].joined(separator: "\n")
        let summary = PipelineStatusNative.summarize(
            statusText: status,
            sttEnsembleEnabled: true
        )
        XCTAssertEqual(summary.allKeys, ["stt1", "stt2", "subtitle_llm"])
    }

    func testStageLabelTracksLatestRecognizedLine() {
        let status = [
            "⏳ [전처리] FFMPEG 오디오 추출 중",
            "⏳ [음성] RNNoise 음성 보존 노이즈 제거 중",
        ].joined(separator: "\n")
        let summary = PipelineStatusNative.summarize(statusText: status)
        XCTAssertEqual(summary.latestKeys, ["audio"])
        XCTAssertEqual(summary.label, "음성")
    }

    func testSTTLabelRespectsEnsembleFlag() {
        let status = "⏳ [STT] STT1/STT2 병렬 인식 중"
        XCTAssertEqual(
            PipelineStatusNative.summarize(statusText: status, sttEnsembleEnabled: false).label,
            "STT 1"
        )
        XCTAssertEqual(
            PipelineStatusNative.summarize(statusText: status, sttEnsembleEnabled: true).label,
            "STT 1/2"
        )
    }
}
