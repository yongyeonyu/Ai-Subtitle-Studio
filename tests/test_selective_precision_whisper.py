import os
import tempfile
import unittest

from core.subtitle_quality.selective_precision_whisper import (
    precision_whisper_deterministic_judge,
    run_selective_precision_whisper,
    select_precision_whisper_targets,
)


class SelectivePrecisionWhisperTests(unittest.TestCase):
    def test_selects_only_uncertain_segments_against_precision_lattice(self):
        segments = [
            {"line": 0, "start": 1.0, "end": 1.7, "text": "안녕하세요", "words": [{"start": 1.05, "end": 1.65, "word": "안녕하세요"}]},
            {"line": 1, "start": 3.0, "end": 3.6, "text": "다시 확인", "quality": {"flags": ("outside_vad_speech",)}},
        ]
        lattice = [{"start": 1.0, "end": 1.75}, {"start": 2.85, "end": 3.75}]

        targets = select_precision_whisper_targets(segments, lattice, settings={})

        self.assertEqual([item["segment_index"] for item in targets], [1])
        self.assertLess(targets[0]["recheck_start"], 3.0)
        self.assertGreater(targets[0]["recheck_end"], 3.6)

    def test_missing_word_timing_alone_does_not_select_vad_aligned_segment(self):
        segments = [{"line": 0, "start": 1.0, "end": 1.7, "text": "정상 자막"}]
        lattice = [{"start": 0.98, "end": 1.72}]

        targets = select_precision_whisper_targets(segments, lattice, settings={})

        self.assertEqual(targets, [])

    def test_deterministic_judge_accepts_similar_candidate_inside_vad(self):
        segment = {"start": 1.0, "end": 1.8, "text": "안녕하세요", "stt_candidates": [{"text": "안녕하세요"}]}
        candidate = {"start": 0.98, "end": 1.82, "text": "안녕하세요"}
        lattice = [{"start": 0.95, "end": 1.85}]

        decision = precision_whisper_deterministic_judge(segment, candidate, lattice, settings={})

        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["reason"], "deterministic_precision_whisper_judge")

    def test_deterministic_judge_rejects_candidate_too_far_from_existing_or_stt(self):
        segment = {"start": 1.0, "end": 1.8, "text": "안녕하세요"}
        candidate = {"start": 0.98, "end": 1.82, "text": "전혀 다른 문장입니다"}
        lattice = [{"start": 0.95, "end": 1.85}]

        decision = precision_whisper_deterministic_judge(segment, candidate, lattice, settings={})

        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["reason"], "text_too_far_from_existing_or_stt")

    def test_run_selective_precision_whisper_applies_only_judged_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_audio = os.path.join(tmp, "source.wav")
            with open(source_audio, "wb") as f:
                f.write(b"not real wav but extractor is mocked")

            segments = [
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 1.5,
                    "text": "안 녕",
                    "quality": {"flags": ("outside_vad_speech",)},
                },
                {
                    "line": 1,
                    "start": 3.0,
                    "end": 3.5,
                    "text": "유지",
                    "quality": {"flags": ("outside_vad_speech",)},
                },
            ]
            lattice = [{"start": 0.95, "end": 1.55}, {"start": 2.95, "end": 3.55}]

            def extractor(source, start, end, out_path):
                with open(out_path, "wb") as f:
                    f.write(b"clip")
                return out_path

            calls = []

            def transcriber(clip_path, target, settings):
                calls.append(target["segment_index"])
                if target["segment_index"] == 0:
                    return {"text": "안녕", "engine": "test", "model": "precision"}
                return {"text": "완전히 다른 내용", "engine": "test", "model": "precision"}

            result = run_selective_precision_whisper(
                segments,
                audio_path=source_audio,
                lattice_segments=lattice,
                settings={},
                transcriber=transcriber,
                clip_extractor=extractor,
            )

        out = list(result.segments)
        self.assertEqual(calls, [0, 1])
        self.assertEqual(out[0]["text"], "안녕")
        self.assertEqual(out[1]["text"], "유지")
        self.assertEqual(result.report["accepted_count"], 1)
        self.assertEqual(result.report["rejected_count"], 1)
        self.assertEqual(out[0]["asr_metadata"]["precision_whisper"]["model"], "precision")


if __name__ == "__main__":
    unittest.main()
