# Version: 03.07.04
# Phase: PHASE2
import unittest

from core.pipeline_status import generation_stage_keys, generation_stage_label, process_mode_label


class PipelineStatusTests(unittest.TestCase):
    def test_preprocess_status_wins_over_audio_and_vad_words(self):
        status = "⏳ [전처리] FFMPEG 오디오 추출 및 기본 필터 적용 중"
        self.assertEqual(generation_stage_keys(status), {"preprocess"})
        self.assertEqual(generation_stage_label(status), "전처리")

    def test_pipeline_stage_parser_matches_sidebar_keys(self):
        self.assertEqual(generation_stage_keys("⏳ [음성] RNNoise 빠른 노이즈 제거 중"), {"audio"})
        self.assertEqual(generation_stage_keys("⏳ [VAD] TEN VAD 음성 섹터 스캔 중"), {"vad"})
        self.assertEqual(generation_stage_keys("⏳ [STT] STT1/STT2 병렬 인식 중", stt_ensemble_enabled=True), {"stt1", "stt2"})
        self.assertEqual(generation_stage_keys("⏳ [자막 LLM] 교정/분리 중"), {"subtitle_llm"})

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
