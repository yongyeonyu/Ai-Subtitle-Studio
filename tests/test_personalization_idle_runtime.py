import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from core.personalization.idle_trainer import (
    PersonalizationIdleTrainer,
    enqueue_default_training_jobs,
    enqueue_full_training_jobs,
    format_training_queue_status_summary,
    recover_interrupted_training_jobs,
    run_training_queue_once,
)
from core.audio.whisper_transformers import is_transformers_whisper_model
from core.personalization.lora_models import TruthTableRow
from core.personalization.lora_storage import (
    append_truth_table_rows,
    initialize_lora_personalization_store,
    load_best_settings,
    load_training_queue,
    save_training_queue,
    store_paths,
)
from core.personalization.lora_trial_scoring import record_setting_trial_result
from core.personalization.runtime_personalization import personalization_settings_override_for_media


class _DummyOwner(QObject):
    def __init__(self):
        super().__init__()
        self.backend = None
        self._auto_processing_active = False
        self._current_work_mode = "editor"
        self.stack = None

    def _is_editor_actively_editing(self):
        return False


class _DummyStack:
    def __init__(self, index: int):
        self._index = index

    def currentIndex(self):
        return self._index


class PersonalizationIdleRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _perfect_trial_metrics(score: float = 96.0) -> dict:
        return {
            "final_score": score,
            "character_error_rate": 0.02,
            "eojeol_error_rate": 0.03,
            "timing_overlap_score": 0.98,
            "line_break_match_score": 1.0,
            "punctuation_match_score": 1.0,
            "parenthetical_exclusion_correctness": 1.0,
            "segment_split_merge_f1": 1.0,
        }

    def test_idle_trainer_queue_controls_pause_resume_and_clear(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            payload = enqueue_default_training_jobs(
                [{"media_id": "media-001", "media_path": "/tmp/clip_a.mp4", "subtitle_path": "/tmp/clip_a.srt"}],
                store_dir=tmpdir,
            )
            self.assertEqual(len(list(payload.get("items") or [])), 6)

            owner = _DummyOwner()
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            try:
                self.assertEqual(trainer.queue_summary().get("waiting"), 6)

                trainer.pause_pending_jobs()
                self.assertEqual(trainer.queue_summary().get("paused"), 6)

                trainer.resume_pending_jobs()
                self.assertEqual(trainer.queue_summary().get("waiting"), 6)

                trainer.clear_pending_jobs(keep_completed=False)
                self.assertEqual(load_training_queue(tmpdir).get("items"), [])
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_training_queue_status_summary_uses_user_visible_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            save_training_queue(
                [
                    {"job_id": "done", "status": "complete"},
                    {"job_id": "running", "status": "in_progress"},
                    {"job_id": "waiting-a", "status": "waiting"},
                    {"job_id": "waiting-b", "status": "waiting"},
                ],
                tmpdir,
            )

            summary = format_training_queue_status_summary(load_training_queue(tmpdir))

            self.assertEqual(summary, "완료 1개 · 실행중 1개 · 대기 2개")
            self.assertEqual(format_training_queue_status_summary({"items": []}), "대기 작업 없음")

    def test_idle_trainer_defaults_to_slow_low_resource_schedule(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)

            owner = _DummyOwner()
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            try:
                self.assertGreaterEqual(trainer.idle_window_ms, 300_000)
                self.assertGreaterEqual(trainer.cooldown_ms, 300_000)
                self.assertGreaterEqual(trainer._poll_timer.interval(), 30_000)
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_enqueue_full_training_jobs_requeues_completed_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            append_truth_table_rows(
                [
                    TruthTableRow(
                        media_id="media-001",
                        media_path="/Users/test/Movies/clip_a.mp4",
                        subtitle_path="/Users/test/Movies/clip_a.srt",
                        segment_id="clip_a:1",
                        start_sec=0.0,
                        end_sec=2.0,
                        raw_ground_truth_text="전체 학습 테스트입니다.",
                        speech_training_text="전체 학습 테스트입니다.",
                    ).to_record(),
                    TruthTableRow(
                        media_id="media-002",
                        media_path="/Users/test/Movies/clip_b.mp4",
                        subtitle_path="/Users/test/Movies/clip_b.srt",
                        segment_id="clip_b:1",
                        start_sec=0.0,
                        end_sec=2.0,
                        raw_ground_truth_text="두 번째 영상입니다.",
                        speech_training_text="두 번째 영상입니다.",
                    ).to_record(),
                ],
                tmpdir,
            )

            first_payload = enqueue_full_training_jobs(store_dir=tmpdir)
            first_items = list(first_payload.get("items") or [])
            self.assertEqual(len(first_items), 8)
            self.assertIn("build_retrieval_index", {str(item.get("job_type") or "") for item in first_items})
            self.assertIn("build_subtitle_pattern_index", {str(item.get("job_type") or "") for item in first_items})
            self.assertNotIn("build_voice_profiles", {str(item.get("job_type") or "") for item in first_items})
            self.assertNotIn("build_stt1_whisper_adapter", {str(item.get("job_type") or "") for item in first_items})

            first_items[0]["status"] = "complete"
            first_items[0]["progress"] = 1.0
            first_items[0]["payload"] = {"checkpoint": {"stage": "completed"}}
            save_training_queue(first_items, tmpdir)

            second_payload = enqueue_full_training_jobs(store_dir=tmpdir)
            restored_item = list(second_payload.get("items") or [])[0]
            self.assertEqual(restored_item["status"], "waiting")
            self.assertEqual(restored_item["progress"], 0.0)
            self.assertEqual(restored_item["last_error"], "manual_full_training_requeued")
            self.assertTrue((restored_item.get("payload") or {}).get("manual_full_training"))

    def test_training_queue_logs_detailed_learning_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)
            logs: list[str] = []

            with patch(
                "core.personalization.idle_trainer.get_logger",
                return_value=SimpleNamespace(log=logs.append),
            ):
                result = run_training_queue_once(tmpdir, low_resource=False)

            self.assertTrue(result["processed"])
            joined = "\n".join(logs)
            self.assertIn("[LoRA 학습] 시작: 수동 · 1/4 · truth 분석", joined)
            self.assertIn("truth table 규칙 분석 중", joined)
            self.assertIn("검색 인덱스 갱신", joined)

    def test_low_resource_training_downgrades_full_audio_extraction_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            save_training_queue(
                [
                    {
                        "job_id": "voice-full",
                        "job_type": "build_voice_profiles",
                        "media_id": "global",
                        "media_path": "",
                        "subtitle_path": "",
                        "status": "waiting",
                        "priority": 1,
                        "progress": 0.0,
                        "attempts": 0,
                        "payload": {"manual_full_training": True, "extract_audio": True},
                    }
                ],
                tmpdir,
            )

            with (
                patch(
                    "core.personalization.idle_trainer.save_voice_lora_profile_manifest",
                    return_value={"speaker_profiles": 1},
                ),
                patch(
                    "core.personalization.idle_trainer.save_voice_lora_training_plan",
                    return_value={
                        "usable_voice_rows": 7,
                        "stored_audio_items": 0,
                        "extraction_errors": 0,
                        "extraction_skipped": 0,
                    },
                ) as voice_plan,
            ):
                result = run_training_queue_once(tmpdir, low_resource=True)

            self.assertTrue(result["processed"])
            self.assertEqual(voice_plan.call_args.kwargs["extract_audio"], False)
            item = load_training_queue(tmpdir)["items"][0]
            self.assertEqual(item["status"], "complete")
            payload = dict(item.get("payload") or {})
            self.assertTrue(payload.get("resumed_as_low_resource_idle"))
            self.assertTrue(payload.get("audio_extraction_deferred"))
            self.assertEqual(payload["checkpoint"]["reason"], "audio_extraction_deferred")

    def test_low_resource_training_skips_retention_prune(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)

            with patch("core.personalization.idle_trainer.prune_low_value_personalization_data") as prune:
                result = run_training_queue_once(tmpdir, low_resource=True)

            self.assertTrue(result["processed"])
            prune.assert_not_called()

    def test_low_resource_training_defers_retrieval_index_and_zip_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            save_training_queue(
                [
                    {
                        "job_id": "index-low-power",
                        "job_type": "build_retrieval_index",
                        "media_id": "global",
                        "media_path": "",
                        "subtitle_path": "",
                        "status": "waiting",
                        "priority": 1,
                        "progress": 0.0,
                        "attempts": 0,
                        "payload": {"force": True},
                    }
                ],
                tmpdir,
            )

            with (
                patch("core.personalization.idle_trainer.build_lora_retrieval_index") as build_index,
                patch("core.personalization.idle_trainer.refresh_unified_lora_data_bundle") as refresh_bundle,
                patch("core.personalization.lora_store_bundle.refresh_unified_lora_data_bundle") as manifest_bundle,
            ):
                result = run_training_queue_once(tmpdir, low_resource=True)

            self.assertTrue(result["processed"])
            build_index.assert_not_called()
            refresh_bundle.assert_not_called()
            manifest_bundle.assert_not_called()
            item = load_training_queue(tmpdir)["items"][0]
            self.assertEqual(item["status"], "skipped")
            self.assertEqual(item["last_error"], "low_resource_index_refresh_deferred")

    def test_low_resource_completed_job_does_not_refresh_retrieval_index_in_app_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)

            with patch("core.personalization.idle_trainer.build_lora_retrieval_index") as build_index:
                result = run_training_queue_once(tmpdir, low_resource=True)

            self.assertTrue(result["processed"])
            build_index.assert_not_called()
            outcome = dict(result.get("outcome") or {})
            self.assertEqual((outcome.get("retrieval_index") or {}).get("reason"), "low_resource_index_refresh_deferred")

    def test_run_training_queue_once_writes_store_local_training_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            append_truth_table_rows(
                [
                    TruthTableRow(
                        media_id="media-001",
                        media_path="/Users/test/Movies/clip_a.mp4",
                        subtitle_path="/Users/test/Movies/clip_a.srt",
                        segment_id="clip_a:1",
                        start_sec=0.0,
                        end_sec=2.1,
                        raw_ground_truth_text="안녕하세요.",
                        speech_training_text="안녕하세요.",
                        line_break_pattern="6",
                        punctuation_pattern=".",
                        detected_split_rule="",
                    ).to_record()
                ],
                tmpdir,
            )
            payload = enqueue_default_training_jobs(
                [{"media_id": "media-001", "media_path": "/Users/test/Movies/clip_a.mp4", "subtitle_path": "/Users/test/Movies/clip_a.srt"}],
                store_dir=tmpdir,
            )
            self.assertEqual(len(list(payload.get("items") or [])), 6)

            paths = store_paths(tmpdir)
            paths["text_lora_corpus"].write_text(
                json.dumps(
                    {
                        "task": "text_correction",
                        "input": "안녕하세요",
                        "output": "안녕하세요.",
                        "source": "ground_truth",
                        "meta": {"speaker": "00"},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            paths["voice_lora_bridge"].write_text(
                json.dumps(
                    {
                        "speaker": "00",
                        "duration_frames": 180,
                        "clip_path": str(paths["root"] / "clip_a.mp4"),
                        "project_path": "/Users/test/Projects/clip_a.json",
                        "text": "안녕하세요.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            paths["multimodal_lora_context"].write_text(
                json.dumps(
                    {
                        "schema": "ai_subtitle_studio.multimodal_lora_context.v1",
                        "task": "subtitle_generation_context",
                        "source": "unit_test",
                        "media_id": "media-001",
                        "media_profile": {
                            "has_audio": True,
                            "has_video": True,
                            "audio": {"sample_rate": 48000, "channels": 2},
                            "video": {"fps": 29.97},
                        },
                        "subtitle_profile": {
                            "excluded_parenthetical_ratio": 0.3,
                            "reading_speed": {"avg_cps": 12.5, "max_cps": 17.0},
                        },
                        "candidate_context": {"candidate_count": 2, "candidate_disagreement_ratio": 0.22},
                        "context_classification": {
                            "scene_environment": {"label": "car"},
                            "topic": {"primary": "vehicle_review"},
                            "microphone_environment": {
                                "mic_type": "builtin_or_far",
                                "noise_level": "high",
                                "noise_sources": ["engine", "traffic"],
                            },
                            "training_focus": ["handle_low_rumble", "protect_brand_model_names"],
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (paths["root"] / "clip_a.mp4").write_bytes(b"fake media")

            processed = []
            def fake_run(command, **_kwargs):
                Path(command[-1]).write_bytes(b"RIFFfake wav data")
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with patch("core.personalization.text_lora_runner.subprocess.run", side_effect=fake_run):
                for _ in range(6):
                    result = run_training_queue_once(tmpdir)
                    processed.append(result)

            self.assertTrue(all(item.get("processed") for item in processed))
            self.assertEqual(
                {str(item.get("outcome", {}).get("status", "")) for item in processed},
                {"complete"},
            )
            self.assertEqual(run_training_queue_once(tmpdir)["reason"], "no_pending_job")

            queue_items = list(load_training_queue(tmpdir).get("items") or [])
            self.assertTrue(queue_items)
            self.assertTrue(all(str(item.get("status") or "") == "complete" for item in queue_items))
            self.assertEqual(queue_items[0]["payload"]["checkpoint"]["stage"], "completed")
            self.assertIn("checkpoint_history", queue_items[0]["payload"])
            self.assertTrue(paths["text_lora_training_plan"].exists())
            self.assertTrue(paths["subtitle_pattern_index"].exists())
            self.assertGreater(json.loads(paths["subtitle_pattern_index"].read_text(encoding="utf-8"))["pattern_count"], 0)
            self.assertTrue(paths["learned_split_rules"].exists())
            self.assertGreater(len(paths["setting_trials"].read_text(encoding="utf-8").strip().splitlines()), 0)
            self.assertGreater(len(paths["prompt_trials"].read_text(encoding="utf-8").strip().splitlines()), 0)
            setting_trials = [
                json.loads(line)
                for line in paths["setting_trials"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            prompt_trials = [
                json.loads(line)
                for line in paths["prompt_trials"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(any((row.get("metrics") or {}).get("multimodal_context_rows") == 1 for row in setting_trials))
            self.assertTrue(any((row.get("metrics") or {}).get("scene_environment") == "car" for row in setting_trials))
            self.assertTrue(any((row.get("metrics") or {}).get("topic") == "vehicle_review" for row in setting_trials))
            self.assertTrue(any(row.get("prompt_template_id") == "subtitle_qa_multimodal_context_v1" for row in prompt_trials))

            best_settings = load_best_settings(tmpdir)
            self.assertIn("media-001", dict(best_settings.get("by_media_id") or {}))
            self.assertEqual(best_settings.get("global_recommended_defaults"), {})

    def test_runtime_override_uses_ready_stt1_adapter_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)
            model_dir = paths["trained_adapters"] / "personal_stt1_whisper_adapter" / "merged_transformers"
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "config.json").write_text("{}", encoding="utf-8")
            (model_dir / "preprocessor_config.json").write_text("{}", encoding="utf-8")
            paths["stt1_whisper_adapter_runtime_manifest"].write_text(
                json.dumps(
                    {
                        "schema": "ai_subtitle_studio.stt1_whisper_adapter_runtime_manifest.v1",
                        "runtime_ready": True,
                        "dataset_stats": {"usable_training_rows": 32},
                        "activation_policy": {
                            "minimum_truth_rows": 24,
                            "minimum_retrieval_score": 28.0,
                            "allow_global_fallback": True,
                        },
                        "runtime_candidates": {
                            "mac": {
                                "backend": "transformers-whisper",
                                "selected_whisper_model": str(model_dir),
                                "ready": True,
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("core.personalization.runtime_personalization.config.IS_MAC", True), patch(
                "core.personalization.runtime_personalization.load_settings",
                return_value={"stt_quality_preset": "precise"},
            ):
                override = personalization_settings_override_for_media("/Users/test/Movies/fresh_clip.mp4", store_dir=tmpdir)

            self.assertEqual(override["selected_whisper_model"], str(model_dir))
            self.assertTrue(is_transformers_whisper_model(str(model_dir)))

    def test_fast_quality_excludes_learned_lora_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            media_path = "/Users/test/Movies/fast_clip.mp4"
            record_setting_trial_result(
                media_id="fast-001",
                media_path=media_path,
                subtitle_path="/Users/test/Movies/fast_clip.srt",
                config={
                    "selected_audio_ai": "clearvoice",
                    "selected_model": "gpt-5.5",
                    "stt_ensemble_enabled": True,
                    "sub_max_cps": 15,
                },
                metrics=self._perfect_trial_metrics(),
                reason="fast should stay stt1 only without lora",
                store_dir=tmpdir,
            )

            with patch(
                "core.personalization.runtime_personalization.load_settings",
                return_value={"stt_quality_preset": "fast"},
            ):
                override = personalization_settings_override_for_media(media_path, store_dir=tmpdir)

            self.assertEqual(override, {"stt_ensemble_enabled": False})

    def test_balanced_quality_uses_only_stt1_minimal_lora_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            media_path = "/Users/test/Movies/balanced_clip.mp4"
            record_setting_trial_result(
                media_id="balanced-001",
                media_path=media_path,
                subtitle_path="/Users/test/Movies/balanced_clip.srt",
                config={
                    "selected_audio_ai": "clearvoice",
                    "selected_whisper_model": "large-v3",
                    "selected_model": "gpt-5.5",
                    "stt_quality_preset": "precise",
                    "subtitle_quality_auto_correct_enabled": True,
                    "stt_ensemble_enabled": True,
                    "sub_max_cps": 15,
                    "sub_gap_break_sec": 1.0,
                },
                metrics=self._perfect_trial_metrics(),
                reason="balanced should keep only lightweight stt1 lora keys",
                store_dir=tmpdir,
            )

            with patch(
                "core.personalization.runtime_personalization.load_settings",
                return_value={"stt_quality_preset": "balanced"},
            ):
                override = personalization_settings_override_for_media(media_path, store_dir=tmpdir)

            self.assertEqual(override["selected_audio_ai"], "clearvoice")
            self.assertEqual(override["selected_whisper_model"], "large-v3")
            self.assertEqual(override["sub_max_cps"], 15)
            self.assertEqual(override["sub_gap_break_sec"], 1.0)
            self.assertEqual(override["stt_ensemble_enabled"], False)
            self.assertNotIn("selected_model", override)
            self.assertNotIn("stt_quality_preset", override)
            self.assertNotIn("subtitle_quality_auto_correct_enabled", override)

    def test_voice_profile_job_fails_when_audio_sources_are_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)
            paths["voice_lora_bridge"].write_text(
                json.dumps(
                    {
                        "speaker": "00",
                        "duration_frames": 180,
                        "clip_path": str(paths["root"] / "missing.mp4"),
                        "project_path": "/Users/test/Projects/clip_a.json",
                        "text": "안녕하세요.",
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "duration_sec": 2.0,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            save_training_queue(
                [
                    {
                        "job_id": "voice-job",
                        "job_type": "build_voice_profiles",
                        "media_id": "global",
                        "status": "waiting",
                        "priority": 1,
                        "payload": {"extract_audio": True},
                    }
                ],
                tmpdir,
            )

            result = run_training_queue_once(tmpdir)

            self.assertTrue(result["processed"])
            self.assertEqual(result["outcome"]["status"], "failed")
            self.assertIn("voice_audio_extraction_incomplete", result["outcome"]["result"]["reason"])
            queue_item = load_training_queue(tmpdir)["items"][0]
            self.assertEqual(queue_item["status"], "failed")
            self.assertIn("stored 0/1", queue_item["last_error"])

    def test_voice_profile_queue_job_defers_audio_extraction_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)
            paths["voice_lora_bridge"].write_text(
                json.dumps(
                    {
                        "speaker": "00",
                        "duration_frames": 180,
                        "clip_path": str(paths["root"] / "missing.mp4"),
                        "project_path": "/Users/test/Projects/clip_a.json",
                        "text": "안녕하세요.",
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "duration_sec": 2.0,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            save_training_queue(
                [
                    {
                        "job_id": "voice-job",
                        "job_type": "build_voice_profiles",
                        "media_id": "global",
                        "status": "waiting",
                        "priority": 1,
                    }
                ],
                tmpdir,
            )

            result = run_training_queue_once(tmpdir)

            self.assertTrue(result["processed"])
            self.assertEqual(result["outcome"]["status"], "complete")
            self.assertEqual(result["outcome"]["result"]["reason"], "audio_extraction_deferred")
            queue_item = load_training_queue(tmpdir)["items"][0]
            self.assertEqual(queue_item["status"], "complete")
            self.assertEqual(queue_item["last_error"], "")

    def test_idle_trainer_poll_starts_background_job_when_idle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)

            owner = _DummyOwner()
            owner.stack = _DummyStack(0)
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            trainer.idle_window_ms = 0
            trainer.last_user_activity_ms = 0
            try:
                trainer._poll()
                worker = trainer._worker_thread
                self.assertIsNotNone(worker)
                worker.join(timeout=2.0)
                self.assertFalse(worker.is_alive())

                queue_items = list(load_training_queue(tmpdir).get("items") or [])
                self.assertEqual(str(queue_items[0].get("status") or ""), "complete")
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_background_training_logs_auto_learning_status_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)

            owner = _DummyOwner()
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            logs: list[str] = []
            try:
                with patch(
                    "core.personalization.idle_trainer.get_logger",
                    return_value=SimpleNamespace(log=logs.append),
                ):
                    result = trainer.start_background_run()
                    self.assertTrue(result["started"])
                    worker = trainer._worker_thread
                    self.assertIsNotNone(worker)
                    worker.join(timeout=2.0)
                    self.assertFalse(worker.is_alive())

                joined = "\n".join(logs)
                self.assertIn("자동 학습 상태: 대기 4개 (백그라운드 시작)", joined)
                self.assertIn("자동 학습 상태: 완료 1개 · 대기 3개 (백그라운드 완료)", joined)
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_idle_trainer_runs_only_on_home_idle_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)

            owner = _DummyOwner()
            owner._current_work_mode = "editor"
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            trainer.idle_window_ms = 0
            trainer.last_user_activity_ms = 0
            try:
                trainer._poll()
                self.assertIsNone(trainer._worker_thread)

                owner.stack = _DummyStack(0)
                trainer._poll()
                worker = trainer._worker_thread
                self.assertIsNotNone(worker)
                worker.join(timeout=2.0)
                self.assertFalse(worker.is_alive())
                self.assertEqual(load_training_queue(tmpdir)["items"][0]["status"], "complete")
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_foreground_activity_suspends_idle_training_until_home_is_idle_again(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)

            owner = _DummyOwner()
            owner.stack = _DummyStack(0)
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            trainer.idle_window_ms = 0
            trainer.cooldown_ms = 0
            trainer.last_user_activity_ms = 0
            try:
                result = trainer.suspend_for_foreground_activity(reason="file_open", hold_ms=60_000)
                self.assertTrue(result["suspended"])

                trainer._poll()
                self.assertIsNone(trainer._worker_thread)

                trainer._suspended_until_ms = 0
                trainer.last_user_activity_ms = 0
                trainer._poll()
                worker = trainer._worker_thread
                self.assertIsNotNone(worker)
                worker.join(timeout=2.0)
                self.assertFalse(worker.is_alive())
                self.assertEqual(load_training_queue(tmpdir)["items"][0]["status"], "complete")
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_paused_jobs_are_not_processed_until_resumed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)

            owner = _DummyOwner()
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            try:
                trainer.pause_pending_jobs()
                result = run_training_queue_once(tmpdir)
                self.assertFalse(result["processed"])
                self.assertEqual(result["reason"], "no_pending_job")

                trainer.resume_pending_jobs()
                resumed = run_training_queue_once(tmpdir)
                self.assertTrue(resumed["processed"])
                self.assertEqual(str(resumed.get("outcome", {}).get("status", "")), "complete")
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_reenqueue_preserves_completed_checkpoint_for_resume(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            enqueue_default_training_jobs([], store_dir=tmpdir)
            first = run_training_queue_once(tmpdir)
            self.assertTrue(first["processed"])
            completed_item = load_training_queue(tmpdir)["items"][0]
            self.assertEqual(completed_item["status"], "complete")
            self.assertEqual(completed_item["payload"]["checkpoint"]["stage"], "completed")

            enqueue_default_training_jobs([], store_dir=tmpdir)

            restored_item = load_training_queue(tmpdir)["items"][0]
            self.assertEqual(restored_item["status"], "complete")
            self.assertEqual(restored_item["payload"]["checkpoint"]["stage"], "completed")

    def test_interrupted_in_progress_jobs_are_recovered_as_waiting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            save_training_queue(
                [
                    {
                        "job_id": "stale-job",
                        "job_type": "optimize_prompts",
                        "media_id": "media-001",
                        "media_path": "/tmp/clip.mp4",
                        "subtitle_path": "/tmp/clip.srt",
                        "status": "in_progress",
                        "priority": 1,
                        "progress": 0.1,
                        "attempts": 1,
                        "last_error": "",
                        "created_at": "2026-05-05T10:00:00",
                        "updated_at": "2026-05-05T10:00:00",
                    }
                ],
                tmpdir,
            )

            result = recover_interrupted_training_jobs(tmpdir, reason="unit_test")

            self.assertEqual(result["recovered"], 1)
            queue_item = load_training_queue(tmpdir)["items"][0]
            self.assertEqual(queue_item["status"], "waiting")
            self.assertEqual(queue_item["progress"], 0.0)
            self.assertEqual(queue_item["attempts"], 1)
            self.assertIn("interrupted_unit_test", queue_item["last_error"])
            self.assertEqual(queue_item["payload"]["checkpoint"]["stage"], "recovered_after_interruption")
            self.assertTrue(queue_item["payload"]["checkpoint"]["resumable"])

    def test_shutdown_recovers_active_job_for_resume(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            save_training_queue(
                [
                    {
                        "job_id": "shutdown-job",
                        "job_type": "optimize_settings",
                        "media_id": "media-001",
                        "media_path": "/tmp/clip.mp4",
                        "subtitle_path": "/tmp/clip.srt",
                        "status": "in_progress",
                        "priority": 1,
                        "progress": 0.45,
                        "attempts": 1,
                        "last_error": "midpoint",
                        "payload": {"checkpoint": {"stage": "candidate_eval"}},
                    }
                ],
                tmpdir,
            )

            owner = _DummyOwner()
            trainer = PersonalizationIdleTrainer(owner, store_dir=tmpdir)
            trainer._poll_timer.stop()
            try:
                result = trainer.shutdown(timeout_sec=0.1)
                self.assertFalse(result["busy"])
                queue_item = load_training_queue(tmpdir)["items"][0]
                self.assertEqual(queue_item["status"], "waiting")
                self.assertEqual(queue_item["payload"]["checkpoint"]["stage"], "recovered_after_interruption")
            finally:
                trainer._poll_timer.stop()
                trainer.deleteLater()

    def test_runtime_override_matches_windows_nas_and_icloud_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            metrics = {
                "final_score": 96.0,
                "character_error_rate": 0.02,
                "eojeol_error_rate": 0.03,
                "timing_overlap_score": 0.98,
                "line_break_match_score": 1.0,
                "punctuation_match_score": 1.0,
                "parenthetical_exclusion_correctness": 1.0,
                "segment_split_merge_f1": 1.0,
            }

            record_setting_trial_result(
                media_id="windows-001",
                media_path=r"C:\Users\User\Videos\Clip One.MP4",
                subtitle_path=r"C:\Users\User\Videos\Clip One.srt",
                config={"selected_audio_ai": "clearvoice"},
                metrics=metrics,
                reason="windows",
                store_dir=tmpdir,
            )
            record_setting_trial_result(
                media_id="nas-001",
                media_path="smb://NAS/share/Season01/clip_a.mov",
                subtitle_path="smb://NAS/share/Season01/clip_a.srt",
                config={"selected_model": "gpt-5.5"},
                metrics={**metrics, "final_score": 97.0},
                reason="nas",
                store_dir=tmpdir,
            )
            record_setting_trial_result(
                media_id="icloud-001",
                media_path="/Users/user/Library/Mobile Documents/com~apple~CloudDocs/Jobs/clip_b.mp4",
                subtitle_path="/Users/user/Library/Mobile Documents/com~apple~CloudDocs/Jobs/clip_b.srt",
                config={"sub_max_cps": 14},
                metrics={**metrics, "final_score": 98.0},
                reason="icloud",
                store_dir=tmpdir,
            )

            windows_override = personalization_settings_override_for_media(
                "c:/users/user/videos/clip one.mp4",
                store_dir=tmpdir,
                base_settings={"stt_quality_preset": "precise"},
            )
            nas_override = personalization_settings_override_for_media(
                "smb://nas/share/Season01/clip_a.mov",
                store_dir=tmpdir,
                base_settings={"stt_quality_preset": "precise"},
            )
            icloud_override = personalization_settings_override_for_media(
                "/Users/user/Library/Mobile Documents/com~apple~CloudDocs/Jobs/clip_b.mp4",
                store_dir=tmpdir,
                base_settings={"stt_quality_preset": "precise"},
            )

            self.assertEqual(windows_override["selected_audio_ai"], "clearvoice")
            self.assertEqual(nas_override["selected_model"], "gpt-5.5")
            self.assertEqual(icloud_override["sub_max_cps"], 14)


if __name__ == "__main__":
    unittest.main()
