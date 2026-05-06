import json
import tempfile
import unittest
from pathlib import Path

from core.audio.stt_lattice import (
    STT_LATTICE_ARTIFACT_SCHEMA,
    build_stt_lattice_artifact,
    collect_stt_lattice_candidates,
    persist_stt_lattice_artifact,
    select_stt_lattice_text,
)
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_manager import save_project


class STTLatticeTests(unittest.TestCase):
    def test_lattice_replaces_only_confident_weak_word(self):
        segment = {
            "start": 0.0,
            "end": 1.8,
            "text": "망고 보여 봐",
            "stt_candidates": [
                {
                    "source": "STT1",
                    "text": "망고 보여 봐",
                    "score": 0.52,
                    "words": [
                        {"word": "망고", "start": 0.0, "end": 0.5, "confidence": 0.21},
                        {"word": "보여", "start": 0.55, "end": 1.0, "confidence": 0.82},
                        {"word": "봐", "start": 1.05, "end": 1.35, "confidence": 0.87},
                    ],
                },
                {
                    "source": "STT2",
                    "text": "방금 보여 봐",
                    "score": 0.91,
                    "words": [
                        {"word": "방금", "start": 0.02, "end": 0.52, "confidence": 0.93},
                        {"word": "보여", "start": 0.56, "end": 1.02, "confidence": 0.8},
                        {"word": "봐", "start": 1.06, "end": 1.34, "confidence": 0.79},
                    ],
                },
            ],
        }

        selected, meta = select_stt_lattice_text(
            segment,
            {
                "stt_lattice_min_confidence": 0.4,
                "stt_lattice_replace_margin": 0.08,
            },
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["text"], "방금 보여 봐")
        self.assertEqual(meta["replacements"], 1)
        self.assertEqual(selected["words"][0]["stt_word_source"], "STT2")

    def test_lattice_keeps_protected_number(self):
        segment = {
            "start": 0.0,
            "end": 1.2,
            "text": "3번 카메라",
            "stt_candidates": [
                {
                    "source": "STT1",
                    "text": "3번 카메라",
                    "score": 0.55,
                    "words": [
                        {"word": "3번", "start": 0.0, "end": 0.45, "confidence": 0.2},
                        {"word": "카메라", "start": 0.5, "end": 1.1, "confidence": 0.8},
                    ],
                },
                {
                    "source": "STT2",
                    "text": "이번 카메라",
                    "score": 0.95,
                    "words": [
                        {"word": "이번", "start": 0.0, "end": 0.45, "confidence": 0.96},
                        {"word": "카메라", "start": 0.5, "end": 1.1, "confidence": 0.85},
                    ],
                },
            ],
        }

        selected, meta = select_stt_lattice_text(segment, {"stt_lattice_min_confidence": 0.4})

        self.assertIsNone(selected)
        self.assertEqual(meta["reason"], "no_confident_replacement")

    def test_lattice_collects_retry_vad_rescue_and_manual_candidates(self):
        segment = {
            "start": 1.0,
            "end": 2.0,
            "text": "원본 후보",
            "words": [{"word": "원본", "start": 1.0, "end": 1.4, "confidence": 0.7}],
            "stt_candidates": [{"source": "STT1", "text": "원본 후보"}],
            "vad_candidates": [{"source": "VAD", "text": "브이 후보"}],
            "stt_retry_candidates": [{"source": "STT1_RETRY", "text": "재시도 후보"}],
            "stt_recheck_candidates": [{"source": "STT2_RECHECK", "text": "재확인 후보"}],
            "stt_rescue_candidates": [{"source": "RESCUE", "text": "복구 후보"}],
            "manual_rerecognition_candidates": [{"source": "MANUAL", "text": "수동 후보"}],
        }

        candidates = collect_stt_lattice_candidates(segment)
        roles = {row["candidate_role"] for row in candidates}

        self.assertIn("selected_current", roles)
        self.assertIn("vad_variant", roles)
        self.assertIn("retry", roles)
        self.assertIn("low_score_recheck", roles)
        self.assertIn("rescue", roles)
        self.assertIn("manual_re_recognition", roles)

    def test_lattice_selector_uses_recheck_candidates(self):
        segment = {
            "start": 0.0,
            "end": 1.2,
            "text": "망고 보여",
            "words": [
                {"word": "망고", "start": 0.0, "end": 0.5, "confidence": 0.2},
                {"word": "보여", "start": 0.55, "end": 1.1, "confidence": 0.8},
            ],
            "stt_recheck_candidates": [
                {
                    "source": "STT2_RECHECK",
                    "text": "방금 보여",
                    "score": 0.96,
                    "words": [
                        {"word": "방금", "start": 0.0, "end": 0.5, "confidence": 0.96},
                        {"word": "보여", "start": 0.55, "end": 1.1, "confidence": 0.84},
                    ],
                }
            ],
        }

        selected, meta = select_stt_lattice_text(
            segment,
            {
                "stt_lattice_min_confidence": 0.4,
                "stt_lattice_replace_margin": 0.08,
            },
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["text"], "방금 보여")
        self.assertEqual(meta["candidate_roles"]["low_score_recheck"], 1)

    def test_lattice_artifact_records_all_candidate_roles(self):
        segment = {
            "id": "seg_a",
            "start": 0.0,
            "end": 1.0,
            "text": "기본",
            "stt_candidates": [{"source": "STT1", "text": "기본"}],
            "vad_candidates": [{"source": "VAD", "text": "비디"}],
            "manual_stt_candidates": [{"source": "MANUAL", "text": "수동"}],
            "_stt_lattice_policy": {"accepted": True, "confidence": 0.8},
        }

        artifact = build_stt_lattice_artifact([segment], {"stt_lattice_artifact_candidate_limit": 16})

        self.assertEqual(artifact["schema"], STT_LATTICE_ARTIFACT_SCHEMA)
        self.assertEqual(artifact["summary"]["accepted_count"], 1)
        self.assertEqual(artifact["summary"]["role_counts"]["vad_variant"], 1)
        self.assertEqual(artifact["summary"]["role_counts"]["manual_re_recognition"], 1)
        self.assertEqual(artifact["segments"][0]["candidate_count"], 4)

    def test_project_metadata_and_artifact_preserve_lattice_after_save(self):
        segment = {
            "id": "seg_lattice",
            "start": 0.0,
            "end": 1.5,
            "text": "저장 후보",
            "stt_recheck_candidates": [{"source": "STT2_RECHECK", "text": "재확인 후보"}],
            "manual_rerecognition_candidates": [{"source": "MANUAL", "text": "수동 후보"}],
            "_stt_lattice_policy": {"enabled": True, "accepted": False, "reason": "checked"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "sample.json"
            project = {
                "app": "AI Subtitle Studio",
                "version": "test",
                "phase": "test",
                "timeline": {"timebase": {"primary_fps": 30.0}, "tracks": [{"clips": []}]},
                "media": [],
                "editor_state": build_editor_state(mode="single", media_files=[], segments=[], primary_fps=30.0),
                "workspace": {},
                "user_settings": {
                    "accuracy_graph_persist_enabled": False,
                    "stt_lattice_persist_enabled": True,
                },
            }
            project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

            save_project(
                str(project_path),
                segments=[segment],
                user_settings={
                    "accuracy_graph_persist_enabled": False,
                    "stt_lattice_persist_enabled": True,
                },
            )
            saved = json.loads(project_path.read_text(encoding="utf-8"))
            reloaded_segments = project_segments_to_editor(saved)
            artifact_path = Path(saved["analysis"]["stt_lattice_artifact_path"])
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(reloaded_segments[0]["stt_recheck_candidates"][0]["text"], "재확인 후보")
        self.assertEqual(reloaded_segments[0]["manual_rerecognition_candidates"][0]["text"], "수동 후보")
        self.assertEqual(saved["analysis"]["stt_lattice_schema"], STT_LATTICE_ARTIFACT_SCHEMA)
        self.assertTrue(artifact_path.name.endswith(".stt_lattice.json"))
        self.assertEqual(artifact["segments"][0]["candidate_role_counts"]["manual_re_recognition"], 1)

    def test_lattice_artifact_can_persist_to_cache_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = persist_stt_lattice_artifact(
                [{"start": 0.0, "end": 0.4, "text": "캐시"}],
                {"stt_lattice_persist_enabled": True},
                cache_dir=tmp,
            )
            path = Path(result["path"])
            self.assertTrue(path.exists())

        self.assertEqual(result["schema"], STT_LATTICE_ARTIFACT_SCHEMA)
        self.assertTrue(path.name.endswith(".stt_lattice.json"))


if __name__ == "__main__":
    unittest.main()
