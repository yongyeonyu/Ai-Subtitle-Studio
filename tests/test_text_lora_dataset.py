import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.personalization.text_lora_dataset import (
    build_text_lora_dataset,
    accumulate_personalization_dataset,
    export_text_lora_dataset,
    load_project_segment_pairs,
)
from core.personalization.lora_storage import load_training_queue
from core.personalization.text_lora_runner import (
    build_text_lora_training_plan,
    build_voice_lora_profile_manifest,
    build_voice_lora_training_plan,
    save_voice_lora_training_plan,
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
                            "quality": {"confidence_score": 96, "confidence_label": "green"},
                            "audio_profile": {"environment": "indoor", "noise_level": "low"},
                            "stt_selected_source": "STT2",
                            "stt_candidates": [
                                {"source": "STT1", "text": "bmw 드라이빙 센터에요", "confidence": 0.71},
                                {"source": "STT2", "text": "bmw 드라이빙센터에요", "confidence": 0.94},
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
        self.assertEqual(result["items"][0]["meta"]["candidate_context"]["candidate_count"], 2)
        self.assertEqual(result["items"][0]["meta"]["generation_context"]["quality"]["confidence_score"], 96)
        self.assertGreater(result["items"][0]["meta"]["delta_ratio"], 0.08)
        self.assertEqual(len(result["context_items"]), 1)
        self.assertEqual(result["context_items"][0]["candidate_context"]["selected_source"], "STT2")

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
        self.assertEqual(payload["stats"]["multimodal_context_items"], 1)
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

    def test_project_segment_learning_excludes_editorial_brackets(self):
        payload = build_text_lora_dataset(
            current_segments=[
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "BMW 드라이빙센터예요 [화면 설명] {편집 메모}",
                    "speaker": "me",
                    "_clip_file": "/tmp/source.mp4",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [
                        {"source": "STT1", "text": "bmw 드라이빙 센터에요 (자동차 설명)"},
                    ],
                },
                {
                    "start": 3.0,
                    "end": 4.0,
                    "text": "(웃음) [효과음] {자료화면}",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [{"source": "STT1", "text": "(웃음)"}],
                },
            ],
            current_project_path="/tmp/current_project.json",
            project_paths=[],
        )

        self.assertEqual(payload["stats"]["project_segment_pairs"], 1)
        self.assertEqual(payload["stats"]["project_pairs_filtered_editorial_only"], 1)
        row = [item for item in payload["items"] if item["source"] == "current_editor_segment_pair"][0]
        self.assertEqual(row["input"], "bmw 드라이빙 센터에요")
        self.assertEqual(row["output"], "BMW 드라이빙센터예요")
        self.assertNotIn("화면 설명", row["output"])
        self.assertNotIn("자동차 설명", row["input"])
        self.assertEqual(len(payload["voice_items"]), 0)
        self.assertEqual(payload["context_items"][0]["pattern_features"]["line_count"], 1)

    def test_project_segment_context_classifies_scene_microphone_and_topic(self):
        payload = build_text_lora_dataset(
            current_segments=[
                {
                    "start": 10.0,
                    "end": 13.0,
                    "text": "BMW X5 차량 리뷰에서 고속도로 주행 소음을 확인합니다",
                    "speaker": "me",
                    "_clip_file": "/tmp/BMW_X5_drive_review.mp4",
                    "audio_profile": {
                        "environment": "car",
                        "mic_present": False,
                        "noise_level": "high",
                        "low_rumble": True,
                    },
                    "stt_selected_source": "STT1",
                    "stt_candidates": [
                        {"source": "STT1", "text": "bmw x5 차량 리뷰에서 고속도로 주행 소음을 확인합니다"},
                        {"source": "STT2", "text": "bmw x5 차량 리브에서 고속도로 소음을 확인합니다"},
                    ],
                }
            ],
            current_project_path="/tmp/vehicle_project.json",
            project_paths=[],
        )

        context = payload["context_items"][0]["context_classification"]
        self.assertEqual(context["scene_environment"]["label"], "car")
        self.assertEqual(context["topic"]["primary"], "vehicle_review")
        self.assertEqual(context["microphone_environment"]["mic_type"], "builtin_or_far")
        self.assertEqual(context["microphone_environment"]["noise_level"], "high")
        self.assertIn("handle_low_rumble", context["training_focus"])

    def test_accumulate_personalization_dataset_appends_once_without_voice_bridge_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from core.personalization import text_lora_dataset as mod
            from core.personalization import text_lora_runner as runner_mod

            root = Path(tmpdir)
            cache = root / ".cache"
            mod.TEXT_LORA_DATASET_DIR = cache
            mod.TEXT_LORA_CORPUS_PATH = cache / "text_lora_corpus.jsonl"
            mod.TEXT_LORA_CORPUS_MANIFEST_PATH = cache / "text_lora_corpus_manifest.json"
            mod.VOICE_LORA_BRIDGE_PATH = cache / "voice_lora_bridge.jsonl"
            mod.MULTIMODAL_LORA_CONTEXT_PATH = cache / "multimodal_lora_context.jsonl"
            runner_mod.TEXT_LORA_DATASET_DIR = cache
            runner_mod.TEXT_LORA_CORPUS_PATH = cache / "text_lora_corpus.jsonl"
            runner_mod.TEXT_LORA_CORPUS_MANIFEST_PATH = cache / "text_lora_corpus_manifest.json"
            runner_mod.VOICE_LORA_BRIDGE_PATH = cache / "voice_lora_bridge.jsonl"
            runner_mod.TEXT_LORA_TRAINING_PLAN_PATH = cache / "text_lora_training_plan.json"
            runner_mod.VOICE_LORA_PROFILE_MANIFEST_PATH = cache / "voice_lora_profile_manifest.json"

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
            self.assertEqual(first["voice_bridge_rows"], 0)
            self.assertEqual(first["multimodal_context_rows"], 1)
            self.assertTrue((first["auto_maintenance"] or {}).get("queued"))
            self.assertEqual(second["appended_rows"], 0)
            self.assertEqual(second["voice_bridge_rows"], 0)
            self.assertEqual(second["multimodal_context_rows"], 0)
            self.assertFalse((second["auto_maintenance"] or {}).get("queued"))

            corpus_lines = (cache / "text_lora_corpus.jsonl").read_text(encoding="utf-8").strip().splitlines()
            context_lines = (cache / "multimodal_lora_context.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(corpus_lines), 1)
            self.assertEqual(len(context_lines), 1)
            context_row = json.loads(context_lines[0])
            self.assertEqual(context_row["task"], "editor_segment_generation_context")
            self.assertEqual(context_row["candidate_context"]["selected_source"], "STT1")
            self.assertEqual(context_row["speaker"], "")
            self.assertEqual(context_row["pattern_features"]["duration_sec"], 1.0)
            self.assertTrue((cache / "text_lora_corpus_manifest.json").exists())
            queued_types = {str(item.get("job_type") or "") for item in list(load_training_queue(root).get("items") or [])}
            self.assertEqual(queued_types, {"analyze_truth_table", "build_text_training_plan"})

            plan = build_text_lora_training_plan(corpus_path=cache / "text_lora_corpus.jsonl")
            self.assertEqual(plan["stats"]["usable_text_rows"], 1)
            self.assertIn("backend", plan)

    def test_voice_bridge_can_be_enabled_for_legacy_voice_exports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cache = root / ".cache"
            cache.mkdir(parents=True, exist_ok=True)
            bridge_path = cache / "voice_lora_bridge.jsonl"
            payload = build_text_lora_dataset(
                current_segments=[
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
                        "stt_candidates": [{"source": "STT1", "text": "엑사원 모델입니다"}],
                    }
                ],
                current_project_path="/tmp/current_project.json",
                project_paths=[],
                voice_lora_bridge_enabled=True,
            )

            self.assertEqual(len(payload["voice_items"]), 1)
            self.assertEqual(payload["voice_items"][0]["speaker"], "01")
            self.assertEqual(payload["voice_items"][0]["text"], "EXAONE 모델입니다")
            bridge_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in payload["voice_items"]) + "\n",
                encoding="utf-8",
            )
            voice_manifest = build_voice_lora_profile_manifest(bridge_path=cache / "voice_lora_bridge.jsonl")
            self.assertEqual(len(voice_manifest["speaker_profiles"]), 1)
            self.assertEqual(voice_manifest["speaker_profiles"][0]["speaker"], "01")

            voice_plan = build_voice_lora_training_plan(
                bridge_path=cache / "voice_lora_bridge.jsonl",
                output_dir=root / "trained_adapters" / "personal_voice_lora",
            )
            self.assertEqual(voice_plan["stats"]["usable_voice_items"], 1)
            self.assertEqual(voice_plan["items"][0]["speaker"], "01")
            self.assertEqual(voice_plan["items"][0]["start_sec"], 3.0)
            self.assertEqual(voice_plan["items"][0]["duration_sec"], 1.0)
            self.assertIn("-ss", voice_plan["items"][0]["extraction_command"])

            saved = save_voice_lora_training_plan(
                bridge_path=cache / "voice_lora_bridge.jsonl",
                output_dir=root / "trained_adapters" / "personal_voice_lora",
                plan_path=cache / "voice_lora_training_plan.json",
                dataset_manifest_path=cache / "voice_lora_dataset_manifest.json",
            )
            self.assertEqual(saved["usable_voice_rows"], 1)
            self.assertTrue((cache / "voice_lora_training_plan.json").exists())
            self.assertTrue((cache / "voice_lora_dataset_manifest.json").exists())

    def test_voice_lora_training_plan_extracts_and_marks_saved_audio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.mp4"
            source.write_bytes(b"fake media")
            bridge = root / "voice_lora_bridge.jsonl"
            bridge.write_text(
                json.dumps(
                    {
                        "text": "안녕하세요 테스트 음성입니다",
                        "clip_path": str(source),
                        "speaker": "me",
                        "start_sec": 1.0,
                        "end_sec": 2.5,
                        "duration_sec": 1.5,
                        "fps": 30.0,
                        "start_frame": 30,
                        "end_frame": 75,
                        "project_path": str(root / "project.json"),
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            plan_path = root / "voice_lora_training_plan.json"
            manifest_path = root / "voice_lora_dataset_manifest.json"

            def fake_run(command, **_kwargs):
                Path(command[-1]).write_bytes(b"RIFFfake wav data")
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with (
                patch("core.personalization.text_lora_runner.runtime_parallel_worker_plan", return_value=(2, {"reserve_cores": 1})) as worker_plan,
                patch("core.personalization.text_lora_runner.subprocess.run", side_effect=fake_run),
            ):
                result = save_voice_lora_training_plan(
                    bridge_path=bridge,
                    output_dir=root / "trained_adapters" / "personal_voice_lora",
                    plan_path=plan_path,
                    dataset_manifest_path=manifest_path,
                    extract_audio=True,
                    resource_settings={"runtime_manual_lora_full_speed": True},
                )

            worker_plan.assert_called_once()
            self.assertEqual(result["usable_voice_rows"], 1)
            self.assertEqual(result["extracted_clips"], 1)
            self.assertEqual(result["stored_audio_items"], 1)
            self.assertEqual(result["extraction_errors"], 0)
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            item = plan["items"][0]
            self.assertTrue(item["audio_ready"])
            self.assertTrue(Path(item["audio_path"]).exists())
            self.assertEqual(plan["stats"]["stored_audio_items"], 1)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["stats"]["stored_audio_items"], 1)
            self.assertEqual(manifest["extraction"]["extracted"], 1)

    def test_voice_lora_training_plan_reports_missing_source_without_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bridge = root / "voice_lora_bridge.jsonl"
            bridge.write_text(
                json.dumps(
                    {
                        "text": "원본 파일이 없는 음성입니다",
                        "clip_path": str(root / "missing.mp4"),
                        "speaker": "me",
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "duration_sec": 2.0,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("core.personalization.text_lora_runner.subprocess.run") as mocked_run:
                result = save_voice_lora_training_plan(
                    bridge_path=bridge,
                    output_dir=root / "trained_adapters" / "personal_voice_lora",
                    plan_path=root / "voice_lora_training_plan.json",
                    dataset_manifest_path=root / "voice_lora_dataset_manifest.json",
                    extract_audio=True,
                )

            mocked_run.assert_not_called()
            self.assertEqual(result["usable_voice_rows"], 1)
            self.assertEqual(result["stored_audio_items"], 0)
            self.assertEqual(result["extraction_skipped"], 1)
            plan = json.loads((root / "voice_lora_training_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["items"][0]["audio_status"], "missing_source_media")

    def test_voice_lora_training_plan_records_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.mp4"
            source.write_bytes(b"fake media")
            bridge = root / "voice_lora_bridge.jsonl"
            bridge.write_text(
                json.dumps(
                    {
                        "text": "실패 테스트 음성입니다",
                        "clip_path": str(source),
                        "speaker": "me",
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "duration_sec": 2.0,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_run(_command, **_kwargs):
                return type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "decode failed"})()

            with patch("core.personalization.text_lora_runner.subprocess.run", side_effect=fake_run):
                result = save_voice_lora_training_plan(
                    bridge_path=bridge,
                    output_dir=root / "trained_adapters" / "personal_voice_lora",
                    plan_path=root / "voice_lora_training_plan.json",
                    dataset_manifest_path=root / "voice_lora_dataset_manifest.json",
                    extract_audio=True,
                )

            self.assertEqual(result["stored_audio_items"], 0)
            self.assertEqual(result["extraction_errors"], 1)
            plan = json.loads((root / "voice_lora_training_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["items"][0]["audio_status"], "failed")
            self.assertFalse(Path(plan["items"][0]["audio_path"]).exists())


if __name__ == "__main__":
    unittest.main()
