import XCTest
@testable import AIStudioCore

final class SubtitleQualityScorerTests: XCTestCase {
    func testGoodSegmentScoresGreen() throws {
        let request = try decodeRequest(
            """
            {
              "segments": [
                {
                  "start": 0.0,
                  "end": 1.2,
                  "text": "안녕하세요",
                  "words": [{"word": "안녕하세요", "start": 0.1, "end": 1.0, "confidence": 0.91}],
                  "asr_metadata": {
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.1,
                    "no_speech_prob": 0.02,
                    "word_confidence": 0.91,
                    "words": [{"word": "안녕하세요", "start": 0.1, "end": 1.0, "confidence": 0.91}],
                    "vad_alignment": {"vad_overlap_ratio": 1.0},
                    "hallucination_risk": {"risk": 0.0, "flags": []}
                  }
                }
              ],
              "settings": {"sub_max_cps": 12}
            }
            """
        )

        let response = SubtitleQualityScorer.score(request)
        XCTAssertEqual(response.metrics.count, 1)
        XCTAssertEqual(response.metrics[0].confidenceLabel, "green")
        XCTAssertGreaterThanOrEqual(response.metrics[0].confidenceScore ?? 0, 85)
        XCTAssertEqual(response.metrics[0].hallucinationPenalty, 0)
    }

    func testMissingMetadataStaysGray() throws {
        let request = try decodeRequest(
            """
            {
              "segments": [
                {"start": 0.0, "end": 0.2, "text": "긴문장입니다"}
              ],
              "settings": {"sub_min_duration": 0.3, "sub_max_cps": 12}
            }
            """
        )

        let response = SubtitleQualityScorer.score(request)
        let metric = try XCTUnwrap(response.metrics.first)
        XCTAssertEqual(metric.confidenceLabel, "gray")
        XCTAssertTrue(metric.flags.contains("metadata_missing"))
        XCTAssertTrue(metric.flags.contains("word_timestamps_missing"))
    }

    func testUncertainLLMRewriteIsYellow() throws {
        let request = try decodeRequest(
            """
            {
              "segments": [
                {
                  "start": 0.0,
                  "end": 1.3,
                  "text": "안경쓰신 분들은 그냥 시뮬레이터를 하시는 게 낫습니다",
                  "words": [{"word": "안경쓰신", "start": 0.0, "end": 0.4}],
                  "asr_metadata": {
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.05,
                    "word_confidence": 0.91,
                    "hallucination_risk": {"risk": 0.0, "flags": []}
                  },
                  "_llm_rewrite_policy": {
                    "changed": true,
                    "confidence": "medium",
                    "needs_review": true,
                    "reason": "uncertain_lexical_rewrite",
                    "similarity": 0.88,
                    "score_penalty": 18.0
                  }
                }
              ],
              "settings": {"subtitle_quality_enabled": true, "sub_max_cps": 12}
            }
            """
        )

        let response = SubtitleQualityScorer.score(request)
        let metric = try XCTUnwrap(response.metrics.first)
        XCTAssertEqual(metric.confidenceLabel, "yellow")
        XCTAssertTrue(metric.flags.contains("llm_uncertain_rewrite"))
    }

    private func decodeRequest(_ json: String) throws -> QualityScoreRequest {
        try JSONDecoder().decode(QualityScoreRequest.self, from: Data(json.utf8))
    }
}
