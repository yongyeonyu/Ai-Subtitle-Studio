import json
import tempfile
import unittest
from pathlib import Path

from core.personalization.editor_truth_capture import (
    build_editor_truth_records,
    capture_editor_truth_records,
)
from core.personalization.deferred_editor_learning import (
    DEFERRED_EDITOR_LEARNING_JOB_TYPE,
    enqueue_deferred_editor_learning,
)
from core.personalization.idle_trainer import run_training_queue_once
from core.personalization.lora_storage import initialize_lora_personalization_store, load_training_queue, store_paths


class EditorTruthCaptureTests(unittest.TestCase):
    def test_deferred_editor_learning_runs_from_idle_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            root = Path(tmpdir)
            media_path = root / "clip.mp4"
            subtitle_path = root / "clip.srt"
            project_path = root / "project.assproj"
            media_path.write_bytes(b"video")
            subtitle_path.write_text("", encoding="utf-8")

            segments = [
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 2.5,
                    "text": "안녕하세요, 오늘 갑니다.",
                    "original_text": "안녕하세요 오늘 감니다",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [{"source": "STT1", "text": "안녕 하세요 오늘 감니다", "score": 0.82}],
                }
            ]

            queued = enqueue_deferred_editor_learning(
                segments,
                media_path=str(media_path),
                subtitle_path=str(subtitle_path),
                project_path=str(project_path),
                trigger="manual_save",
                settings={"editor_truth_capture_enabled": True},
                store_dir=tmpdir,
            )
            self.assertTrue(queued["queued"])
            queue = load_training_queue(tmpdir)
            self.assertEqual(queue["items"][0]["job_type"], DEFERRED_EDITOR_LEARNING_JOB_TYPE)

            result = run_training_queue_once(tmpdir, low_resource=True)

            self.assertTrue(result["processed"])
            self.assertEqual(result["outcome"]["status"], "complete")
            paths = store_paths(tmpdir)
            self.assertTrue(paths["truth_table"].read_text(encoding="utf-8").strip())
            self.assertTrue(paths["text_lora_corpus"].read_text(encoding="utf-8").strip())
            updated_queue = load_training_queue(tmpdir)
            self.assertEqual(updated_queue["items"][0]["status"], "complete")

    def test_capture_editor_save_appends_truth_rows_and_dedupes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            media_path = root / "clip.mp4"
            subtitle_path = root / "clip.srt"
            project_path = root / "project.assproj"
            media_path.write_bytes(b"video")
            subtitle_path.write_text("", encoding="utf-8")

            segments = [
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 3.5,
                    "text": "(박수) 안녕하세요!\n오늘 갈게요.",
                    "speaker": "SPEAKER_01",
                    "original_text": "안녕하세요 오늘 갈게요",
                    "original_start": 0.8,
                    "original_end": 3.2,
                    "source_segment_count": 2,
                    "score": 72,
                    "stt_ensemble_needs_llm_review": True,
                    "stt_candidates": [
                        {"source": "STT1", "text": "안녕하세요 오늘 갈게요", "score": 0.78},
                        {"source": "STT2", "text": "안녕하세요 오늘 갈게요.", "score": 0.81},
                    ],
                },
                {"line": 1, "start": 3.5, "end": 4.0, "text": "", "is_gap": True},
                {"line": 2, "start": 4.0, "end": 5.0, "text": "대기 중", "stt_pending": True},
            ]

            result = capture_editor_truth_records(
                segments,
                media_path=str(media_path),
                subtitle_path=str(subtitle_path),
                project_path=str(project_path),
                trigger="manual_save",
                settings={"selected_audio_ai": "deepfilter", "sub_max_cps": 12},
                store_dir=tmpdir,
                refresh_bundle=False,
            )

            self.assertEqual(result["appended_rows"], 1)
            self.assertEqual(result["excluded_parenthetical_rows"], 1)
            paths = store_paths(tmpdir)
            rows = [
                json.loads(line)
                for line in paths["truth_table"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["raw_ground_truth_text"], "(박수) 안녕하세요!\n오늘 갈게요.")
            self.assertEqual(row["speech_training_text"], "안녕하세요! 오늘 갈게요.")
            self.assertEqual(row["excluded_parenthetical_text"], "박수")
            self.assertEqual(row["speaker_or_voice_hint"], "SPEAKER_01")
            self.assertTrue(row["edited_in_editor"])
            self.assertTrue(row["hard_case"])
            self.assertIn("user_text_changed", row["hard_case_reasons"])
            self.assertEqual(row["settings_snapshot"]["sub_max_cps"], 12)
            self.assertEqual(row["stt_candidate_snapshot"]["candidates"][0]["source"], "STT1")
            self.assertEqual(row["source_before_edit"], "안녕하세요 오늘 갈게요")
            self.assertEqual(row["user_edit_metrics"]["schema"], "ai_subtitle_studio.user_edit_metrics.v1")
            self.assertEqual(row["user_edit_metrics"]["severity"], "large")
            self.assertGreater(row["user_edit_metrics"]["text"]["levenshtein_distance"], 0)
            self.assertAlmostEqual(row["user_edit_metrics"]["timing"]["move_distance_sec"], 0.5, places=3)
            self.assertTrue(row["user_edit_metrics"]["split_merge"]["split_added"])
            self.assertTrue(row["user_edit_metrics"]["split_merge"]["merge_likely"])
            self.assertTrue(row["user_edit_metrics"]["style"]["punctuation_changed"])
            self.assertEqual(result["runtime_patterns"]["appended_patterns"], 1)
            self.assertEqual(result["user_edit_metrics"]["event_status"], "recorded")
            self.assertEqual(result["user_edit_metrics"]["event_rows"], 1)

            excluded_rows = [
                json.loads(line)
                for line in paths["excluded_parentheticals"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(excluded_rows[0]["excluded_text"], "박수")
            queue = load_training_queue(tmpdir)
            queued_types = {item["job_type"] for item in queue["items"]}
            self.assertIn("analyze_truth_table", queued_types)
            self.assertIn("build_text_training_plan", queued_types)
            self.assertIn("hard_case_subtitle_policy", queued_types)
            deep_events = [
                json.loads(line)
                for line in paths["deep_policy_events"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(deep_events[0]["event_type"], "user_edit_metrics")
            self.assertTrue(deep_events[0]["hard_case"])

            second = capture_editor_truth_records(
                segments,
                media_path=str(media_path),
                subtitle_path=str(subtitle_path),
                project_path=str(project_path),
                trigger="manual_save",
                store_dir=tmpdir,
                refresh_bundle=False,
            )
            self.assertEqual(second["appended_rows"], 0)
            self.assertEqual(second["excluded_parenthetical_rows"], 0)

    def test_build_editor_truth_records_skips_pending_gap_and_invalid_rows(self):
        built = build_editor_truth_records(
            [
                {"start": 0, "end": 1, "text": "정상 자막"},
                {"start": 1, "end": 2, "text": "무음", "is_gap": True},
                {"start": 2, "end": 3, "text": "대기", "stt_pending": True},
                {"start": 3, "end": 3, "text": "시간 오류"},
                {"start": 4, "end": 5, "text": "a"},
            ],
            min_chars=2,
        )

        self.assertEqual(len(built["truth_rows"]), 1)
        stats = built["stats"]
        self.assertEqual(stats["gap"], 1)
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["invalid_time"], 1)
        self.assertEqual(stats["too_short"], 1)


if __name__ == "__main__":
    unittest.main()
