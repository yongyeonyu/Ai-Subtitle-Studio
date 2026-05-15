# Version: 03.07.04
# Phase: PHASE2
import unittest

from core.pipeline_status import (
    generation_stage_keys,
    generation_stage_keys_all,
    generation_stage_label,
    generation_stage_summary,
    is_generation_stage_status,
    process_mode_label,
)


class PipelineStatusTests(unittest.TestCase):
    def test_preprocess_status_wins_over_audio_and_vad_words(self):
        status = "⏳ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중"
        self.assertEqual(generation_stage_keys(status), {"preprocess"})
        self.assertEqual(generation_stage_label(status), "전처리")

    def test_pipeline_stage_parser_matches_sidebar_keys(self):
        self.assertEqual(generation_stage_keys("⏳ [음성] RNNoise 음성 보존 노이즈 제거 중"), {"audio"})
        self.assertEqual(generation_stage_keys("⏳ [VAD] TEN VAD 음성 섹터 스캔 중"), {"vad"})
        self.assertEqual(generation_stage_keys("⏳ [STT] STT1/STT2 병렬 인식 중", stt_ensemble_enabled=True), {"stt1", "stt2"})
        self.assertEqual(generation_stage_keys("⏳ [자막 LLM] 교정/분리 중"), {"subtitle_llm"})

    def test_pipeline_stage_parser_can_collect_parallel_live_steps(self):
        status = "\n".join(
            [
                "  ▶ [STT1] 진행 상황: 00분 22초 / 02분 59초 (13%)",
                "[STT2] Loading weights: 100%",
                "[LLM-보정차단] 원문 무결성 검사",
            ]
        )
        self.assertEqual(
            generation_stage_keys_all(status, stt_ensemble_enabled=True),
            {"stt1", "stt2", "subtitle_llm"},
        )

    def test_pipeline_stage_parser_cached_results_are_not_shared_mutably(self):
        status = "⏳ [STT] STT1/STT2 병렬 인식 중"
        first = generation_stage_keys(status, stt_ensemble_enabled=True)
        first.add("mutated")
        second = generation_stage_keys(status, stt_ensemble_enabled=True)
        self.assertEqual(second, {"stt1", "stt2"})

        first_all = generation_stage_keys_all(status, stt_ensemble_enabled=True)
        first_all.clear()
        second_all = generation_stage_keys_all(status, stt_ensemble_enabled=True)
        self.assertEqual(second_all, {"stt1", "stt2"})

    def test_pipeline_stage_label_uses_cached_blob_reduction_without_losing_latest_stage(self):
        status = "\n".join(
            [
                "⏳ [전처리] FFMPEG 오디오 추출 중",
                "⏳ [음성] RNNoise 음성 보존 노이즈 제거 중",
            ]
        )
        self.assertEqual(generation_stage_keys(status), {"audio"})
        self.assertEqual(generation_stage_label(status), "음성")
        self.assertTrue(is_generation_stage_status(status))

    def test_generation_stage_summary_returns_independent_latest_and_all_views(self):
        status = "\n".join(
            [
                "⏳ [STT] STT1/STT2 병렬 인식 중",
                "⏳ [자막 LLM] 교정/분리 중",
            ]
        )
        summary = generation_stage_summary(status, stt_ensemble_enabled=True)
        summary["keys"].add("mutated")
        summary["all_keys"].clear()

        second = generation_stage_summary(status, stt_ensemble_enabled=True)
        self.assertEqual(second["keys"], {"subtitle_llm"})
        self.assertEqual(second["all_keys"], {"stt1", "stt2", "subtitle_llm"})
        self.assertEqual(second["label"], "자막 LLM")
        self.assertTrue(second["active"])

    def test_process_mode_label_uses_processing_state_before_screen_mode(self):
        self.assertEqual(
            process_mode_label(
                screen_mode="editor",
                process_mode="MODE_AI_ALL",
                state="ST_PROC",
                status_text="⏳ [전처리] FFMPEG 오디오 추출 중",
                processing=True,
            ),
            "자막 생성",
        )
        self.assertEqual(
            process_mode_label(screen_mode="editor", process_mode="MODE_AI_ALL", state="ST_EDITING", processing=False),
            "에디터",
        )


if __name__ == "__main__":
    unittest.main()
