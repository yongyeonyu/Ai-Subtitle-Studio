import json
import tempfile
import unittest
from pathlib import Path

from core.personalization.text_lora_dataset import (
    build_text_lora_dataset,
    accumulate_personalization_dataset,
    export_text_lora_dataset,
    load_project_segment_pairs,
)
from core.personalization.text_lora_runner import (
    build_text_lora_training_plan,
    build_voice_lora_profile_manifest,
)


class TextLoraDatasetTests(unittest.TestCase):
    def test_build_dataset_absorbs_corrections_and_memories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            corrections = root / "dataset_correction.json"
            correction_memory = root / "correction_memory.json"
            wrong_answer_memory = root / "wrong_answer_memory.json"

            corrections.write_text(
                json.dumps({"bmw 드라이빙센터": "BMW 드라이빙센터"}, ensure_ascii=False),
                encoding="utf-8",
            )
            correction_memory.write_text(
                json.dumps(
                    {
                        "schema": "ai_subtitle_studio.correction_memory.v1",
                        "items": [
                            {
                                "original": "소설가유모씨",
                                "corrected": "u_mo_c",
                                "type": "proper_noun",
                                "confidence": 0.95,
                                "count": 3,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            wrong_answer_memory.write_text(
                json.dumps(
                    {
                        "schema": "ai_subtitle_studio.wrong_answer_memory.v1",
                        "items": [{"phrase": "구독과 좋아요", "count": 2}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = build_text_lora_dataset(
                corrections_path=corrections,
                correction_memory_path=correction_memory,
                wrong_answer_memory_path=wrong_answer_memory,
                project_paths=[],
            )

            self.assertEqual(payload["stats"]["legacy_corrections"], 1)
            self.assertEqual(payload["stats"]["correction_memory"], 1)
            self.assertEqual(payload["stats"]["wrong_answer_memory"], 1)
            self.assertEqual(payload["stats"]["total_items"], 3)
            self.assertEqual(payload["items"][0]["task"], "text_correction")
            self.assertIn("weight", payload["items"][0]["meta"])

    def test_export_dataset_writes_jsonl_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            corrections = root / "dataset_correction.json"
            corrections.write_text(
                json.dumps({"엑사원": "EXAONE"}, ensure_ascii=False),
                encoding="utf-8",
            )
            dataset_path = root / "out.jsonl"
            manifest_path = root / "manifest.json"

            result = export_text_lora_dataset(
                dataset_path=dataset_path,
                manifest_path=manifest_path,
                corrections_path=corrections,
                correction_memory_path=root / "missing_correction_memory.json",
                wrong_answer_memory_path=root / "missing_wrong_answer_memory.json",
                project_paths=[],
            )

            self.assertTrue(dataset_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertEqual(result["stats"]["total_items"], 1)
            lines = dataset_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["input"], "엑사원")
            self.assertEqual(row["output"], "EXAONE")

    def test_project_segment_pairs_absorb_selected_stt_candidate_to_final_text(self):
        payload = {
            "project_name": "테스트 프로젝트",
            "editor_state": {
                "subtitles": {
                    "segments": [
                        {
                            "start": 1.0,
                            "end": 2.0,
                            "text": "BMW 드라이빙센터예요",
                            "stt_selected_source": "STT2",
                            "stt_candidates": [
                                {"source": "STT1", "text": "bmw 드라이빙 센터에요"},
                                {"source": "STT2", "text": "bmw 드라이빙센터에요"},
                            ],
                        }
                    ]
                }
            },
        }

        result = load_project_segment_pairs(project_payloads=[payload])
        self.assertEqual(result["files_scanned"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["input"], "bmw 드라이빙센터에요")
        self.assertEqual(result["items"][0]["output"], "BMW 드라이빙센터예요")
        self.assertEqual(result["items"][0]["meta"]["selected_source"], "STT2")
        self.assertGreater(result["items"][0]["meta"]["delta_ratio"], 0.08)

    def test_build_dataset_includes_current_editor_segments(self):
        payload = build_text_lora_dataset(
            current_segments=[
                {
                    "start": 3.0,
                    "end": 4.0,
                    "text": "EXAONE 모델입니다",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [
                        {"source": "STT1", "text": "엑사원 모델입니다"},
                        {"source": "STT2", "text": "엑사온 모델입니다"},
                    ],
                }
            ],
            current_project_path="/tmp/current_project.json",
            project_paths=[],
        )

        self.assertEqual(payload["stats"]["project_segment_pairs"], 1)
        project_rows = [item for item in payload["items"] if item["source"] == "current_editor_segment_pair"]
        self.assertEqual(len(project_rows), 1)
        self.assertEqual(project_rows[0]["input"], "엑사원 모델입니다")
        self.assertEqual(project_rows[0]["output"], "EXAONE 모델입니다")
        self.assertIn("quality_profile", payload)

    def test_build_dataset_filters_low_signal_project_pairs(self):
        payload = build_text_lora_dataset(
            current_segments=[
                {
                    "start": 1.0,
                    "end": 1.4,
                    "text": "안녕",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [{"source": "STT1", "text": "안뇽"}],
                },
                {
                    "start": 2.0,
                    "end": 3.0,
                    "text": "테스트입니다.",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [{"source": "STT1", "text": "테스트입니다"}],
                },
            ],
            current_project_path="/tmp/current_project.json",
            project_paths=[],
        )

        self.assertEqual(payload["stats"]["project_segment_pairs"], 0)
        self.assertGreaterEqual(payload["stats"]["project_pairs_filtered_short_input"], 1)
        self.assertGreaterEqual(payload["stats"]["project_pairs_filtered_low_delta"], 1)

    def test_accumulate_personalization_dataset_appends_once_and_builds_voice_bridge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from core.personalization import text_lora_dataset as mod
            from core.personalization import text_lora_runner as runner_mod

            root = Path(tmpdir)
            mod.TEXT_LORA_DATASET_DIR = root
            mod.TEXT_LORA_CORPUS_PATH = root / "text_lora_corpus.jsonl"
            mod.TEXT_LORA_CORPUS_MANIFEST_PATH = root / "text_lora_corpus_manifest.json"
            mod.VOICE_LORA_BRIDGE_PATH = root / "voice_lora_bridge.jsonl"
            runner_mod.TEXT_LORA_DATASET_DIR = root
            runner_mod.TEXT_LORA_CORPUS_PATH = root / "text_lora_corpus.jsonl"
            runner_mod.TEXT_LORA_CORPUS_MANIFEST_PATH = root / "text_lora_corpus_manifest.json"
            runner_mod.VOICE_LORA_BRIDGE_PATH = root / "voice_lora_bridge.jsonl"
            runner_mod.TEXT_LORA_TRAINING_PLAN_PATH = root / "text_lora_training_plan.json"
            runner_mod.VOICE_LORA_PROFILE_MANIFEST_PATH = root / "voice_lora_profile_manifest.json"

            segments = [
                {
                    "start": 3.0,
                    "end": 4.0,
                    "start_frame": 90,
                    "end_frame": 120,
                    "timeline_frame_rate": 30.0,
                    "text": "EXAONE 모델입니다",
                    "speaker": "01",
                    "_clip_file": "/tmp/a.mp4",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [
                        {"source": "STT1", "text": "엑사원 모델입니다"},
                    ],
                }
            ]
            first = accumulate_personalization_dataset(
                current_segments=segments,
                current_project_path="/tmp/current_project.json",
                trigger="unit_test",
            )
            second = accumulate_personalization_dataset(
                current_segments=segments,
                current_project_path="/tmp/current_project.json",
                trigger="unit_test_repeat",
            )

            self.assertEqual(first["appended_rows"], 1)
            self.assertEqual(first["voice_bridge_rows"], 1)
            self.assertEqual(second["appended_rows"], 0)
            self.assertEqual(second["voice_bridge_rows"], 0)

            corpus_lines = (root / "text_lora_corpus.jsonl").read_text(encoding="utf-8").strip().splitlines()
            bridge_lines = (root / "voice_lora_bridge.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(corpus_lines), 1)
            self.assertEqual(len(bridge_lines), 1)
            bridge_row = json.loads(bridge_lines[0])
            self.assertEqual(bridge_row["start_frame"], 90)
            self.assertEqual(bridge_row["end_frame"], 120)
            self.assertEqual(bridge_row["speaker"], "01")
            self.assertTrue((root / "text_lora_corpus_manifest.json").exists())

            plan = build_text_lora_training_plan(corpus_path=root / "text_lora_corpus.jsonl")
            self.assertEqual(plan["stats"]["usable_text_rows"], 1)
            self.assertIn("backend", plan)

            voice_manifest = build_voice_lora_profile_manifest(bridge_path=root / "voice_lora_bridge.jsonl")
            self.assertEqual(len(voice_manifest["speaker_profiles"]), 1)
            self.assertEqual(voice_manifest["speaker_profiles"][0]["speaker"], "01")


if __name__ == "__main__":
    unittest.main()
