import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.personalization.lora_models import (
    ExcludedParentheticalRow,
    LearnedRuleEntry,
    TrainingQueueItem,
    TrialRecord,
    TruthTableRow,
)
from core.personalization.llm_review_exchange import (
    LLM_REVIEW_REQUEST_SCHEMA,
    LLM_REVIEW_RESULT_SCHEMA,
    export_llm_review_request,
    import_llm_review_result,
)
from core.personalization.lora_retention import prune_low_value_personalization_data
from core.personalization.lora_storage import (
    append_excluded_parentheticals,
    append_multimodal_lora_context_rows,
    append_prompt_trials,
    append_setting_trials,
    append_truth_table_rows,
    compact_lora_personalization_store,
    initialize_lora_personalization_store,
    load_best_settings,
    load_dedupe_index,
    load_learned_rules,
    load_training_queue,
    load_unified_lora_data_bundle,
    refresh_lora_personalization_manifest,
    refresh_unified_lora_data_bundle,
    reset_lora_personalization_store,
    restore_lora_personalization_store_from_bundle,
    save_best_settings,
    save_learned_rules,
    save_retention_policy,
    save_training_queue,
    store_paths,
)


class LoraPersonalizationStorageTests(unittest.TestCase):
    def test_initialize_store_creates_phase3_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)

            self.assertTrue(paths["root"].exists())
            self.assertTrue(paths["manifest"].exists())
            self.assertTrue(paths["truth_table"].exists())
            self.assertTrue(paths["training_queue"].exists())
            self.assertTrue(paths["learned_split_rules"].exists())
            self.assertTrue(paths["learned_line_break_rules"].exists())
            self.assertTrue(paths["setting_trials"].exists())
            self.assertTrue(paths["prompt_trials"].exists())
            self.assertTrue(paths["best_settings"].exists())
            self.assertTrue(paths["excluded_parentheticals"].exists())
            self.assertTrue(paths["dedupe_index"].exists())
            self.assertTrue(paths["trained_adapters"].exists())
            self.assertTrue(paths["retention_policy"].exists())
            self.assertTrue(paths["retention_history"].exists())
            self.assertEqual(paths["lora_retrieval_index"].name, "lora_retrieval_index.json")
            self.assertTrue(paths["unified_lora_data"].exists())
            self.assertEqual(paths["unified_lora_data"].name, "lora_data_bundle.zip")
            self.assertTrue(zipfile.is_zipfile(paths["unified_lora_data"]))
            self.assertIn("llm_review_request", paths)
            self.assertIn("llm_review_result", paths)
            self.assertEqual(manifest["counts"]["truth_table_rows"], 0)
            self.assertEqual(manifest["counts"]["queue_items"], 0)
            self.assertEqual(manifest["counts"]["llm_review_request_files"], 0)
            self.assertEqual(manifest["counts"]["llm_review_result_files"], 0)
            self.assertEqual(manifest["counts"]["retention_history_rows"], 0)
            self.assertEqual(manifest["counts"]["lora_retrieval_index_docs"], 0)
            self.assertEqual(manifest["counts"]["unified_lora_data_records"], 0)

    def test_manifest_counts_voice_audio_only_when_wav_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)
            audio_path = paths["voice_lora_clips"] / "me" / "clip.wav"
            paths["voice_lora_training_plan"].write_text(
                json.dumps(
                    {
                        "schema": "ai_subtitle_studio.voice_lora_training_plan.v1",
                        "items": [
                            {
                                "speaker": "me",
                                "audio_ready": True,
                                "audio_path": str(audio_path),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            missing_manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(missing_manifest["counts"]["voice_lora_stored_audio_items"], 0)

            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(b"RIFFfake wav data")
            ready_manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(ready_manifest["counts"]["voice_lora_stored_audio_items"], 1)

    def test_models_and_appenders_dedupe_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            truth_row = TruthTableRow(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                segment_id="seg-1",
                start_sec=1.0,
                end_sec=3.0,
                raw_ground_truth_text="(박수) 안녕하세요!",
                speech_training_text="안녕하세요!",
                excluded_parenthetical_text="박수",
                detected_split_rule="요",
                speaker_or_voice_hint="spk1",
            ).to_record()
            excluded_row = ExcludedParentheticalRow(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                segment_id="seg-1",
                original_text="(박수) 안녕하세요!",
                excluded_text="박수",
                kept_text="안녕하세요!",
            ).to_record()
            setting_trial = TrialRecord(
                trial_type="setting",
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"audio_preset": "clear_voice", "stt_quality_preset": "precise"},
                status="complete",
                score=97.8,
                metrics={"cer": 0.03, "line_break_match": 1.0},
                reason="Best CER and line break match",
            ).to_record()
            prompt_trial = TrialRecord(
                trial_type="prompt",
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"provider": "openai", "model": "gpt-5.5"},
                prompt_template_id="subtitle_qa_v1",
                prompt_text="Keep spoken style and avoid invention.",
                status="complete",
                score=98.2,
                metrics={"punctuation_match": 1.0},
            ).to_record()
            context_row = {
                "schema": "ai_subtitle_studio.multimodal_lora_context.v1",
                "task": "subtitle_generation_context",
                "source": "unit_test",
                "media_id": "media-001",
                "media_profile": {"video": {"fps": 29.97}, "audio": {"sample_rate": 48000}},
                "subtitle_profile": {"reading_speed": {"avg_cps": 7.5}},
                "dedupe_hash": "context-media-001",
            }

            truth_result_first = append_truth_table_rows([truth_row], tmpdir)
            truth_result_second = append_truth_table_rows([truth_row], tmpdir)
            excluded_result = append_excluded_parentheticals([excluded_row, excluded_row], tmpdir)
            setting_result = append_setting_trials([setting_trial, setting_trial], tmpdir)
            prompt_result = append_prompt_trials([prompt_trial, prompt_trial], tmpdir)
            context_result = append_multimodal_lora_context_rows([context_row, context_row], tmpdir)

            self.assertEqual(truth_result_first["appended_rows"], 1)
            self.assertEqual(truth_result_second["appended_rows"], 0)
            self.assertEqual(excluded_result["appended_rows"], 1)
            self.assertEqual(setting_result["appended_rows"], 1)
            self.assertEqual(prompt_result["appended_rows"], 1)
            self.assertEqual(context_result["appended_rows"], 1)

            manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(manifest["counts"]["truth_table_rows"], 1)
            self.assertEqual(manifest["counts"]["excluded_parenthetical_rows"], 1)
            self.assertEqual(manifest["counts"]["setting_trial_rows"], 1)
            self.assertEqual(manifest["counts"]["prompt_trial_rows"], 1)
            self.assertEqual(manifest["counts"]["multimodal_lora_context_rows"], 1)
            self.assertEqual(manifest["counts"]["unified_lora_data_records"], 5)

            bundle = load_unified_lora_data_bundle(store_dir=tmpdir)
            self.assertEqual(bundle["schema"], "ai_subtitle_studio.lora_unified_data_bundle.v1")
            self.assertEqual(bundle["counts"]["unified_training_records"], 5)
            self.assertEqual(len(bundle["sections"]["truth_table"]), 1)
            self.assertEqual(
                {row["kind"] for row in bundle["records"]},
                {"truth_table", "excluded_parentheticals", "setting_trials", "prompt_trials", "multimodal_lora_context"},
            )

            dedupe = load_dedupe_index(tmpdir)
            self.assertEqual(len(dedupe["entries"]["truth_table"]), 1)
            self.assertEqual(len(dedupe["entries"]["excluded_parentheticals"]), 1)

    def test_queue_rules_best_settings_and_compaction_work(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)

            queue_item = TrainingQueueItem(
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                job_type="optimize_settings",
                status="waiting",
                priority=10,
            ).to_record()
            queue_payload = save_training_queue([queue_item], tmpdir)
            self.assertEqual(len(queue_payload["items"]), 1)
            self.assertEqual(len(load_training_queue(tmpdir)["items"]), 1)

            split_rule = LearnedRuleEntry(
                rule_text="그러니까",
                rule_type="split_rule",
                frequency=7,
                confidence=0.92,
                examples=["오늘은 그러니까 여기까지"],
                source_media_refs=["media-001"],
            ).to_record()
            line_break_rule = LearnedRuleEntry(
                rule_text="18|12",
                rule_type="line_break_rule",
                frequency=5,
                confidence=0.88,
                examples=["첫 줄 열여덟 글자 / 둘째 줄 열두 글자"],
                source_media_refs=["media-001"],
            ).to_record()
            save_learned_rules("split", [split_rule], tmpdir)
            save_learned_rules("line_break", [line_break_rule], tmpdir)
            self.assertEqual(len(load_learned_rules("split", tmpdir)["items"]), 1)
            self.assertEqual(len(load_learned_rules("line_break", tmpdir)["items"]), 1)

            best_settings = save_best_settings(
                {
                    "global_recommended_defaults": {"audio_preset": "clear_voice"},
                    "by_media_id": {"media-001": {"audio_preset": "clear_voice", "score": 97.8}},
                },
                tmpdir,
            )
            self.assertEqual(best_settings["global_recommended_defaults"]["audio_preset"], "clear_voice")
            self.assertIn("media-001", load_best_settings(tmpdir)["by_media_id"])

            duplicate_trial = TrialRecord(
                trial_type="setting",
                media_id="media-001",
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                config={"audio_preset": "clear_voice"},
                status="complete",
                score=97.8,
            ).to_record()
            with paths["setting_trials"].open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(duplicate_trial, ensure_ascii=False) + "\n")
                handle.write(json.dumps(duplicate_trial, ensure_ascii=False) + "\n")

            compact_result = compact_lora_personalization_store(tmpdir)
            self.assertEqual(compact_result["removed_counts"]["setting_trials"], 1)

            lines = paths["setting_trials"].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(manifest["counts"]["queue_items"], 1)
            self.assertEqual(manifest["counts"]["learned_split_rules"], 1)
            self.assertEqual(manifest["counts"]["learned_line_break_rules"], 1)

    def test_retention_prunes_lowest_score_trial_and_low_frequency_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            save_retention_policy(
                {
                    "enabled": True,
                    "jsonl": {
                        "setting_trials": {"min_keep": 4, "max_rows": 100, "remove_per_training": 1},
                        "prompt_trials": {"min_keep": 64, "max_rows": 100, "remove_per_training": 0},
                        "truth_table": {"min_keep": 512, "max_rows": 12000, "remove_per_training": 0},
                        "excluded_parentheticals": {"min_keep": 512, "max_rows": 4000, "remove_per_training": 0},
                    },
                    "rules": {
                        "split": {"max_items": 2},
                        "line_break": {"max_items": 256},
                    },
                },
                tmpdir,
            )
            trials = [
                TrialRecord(
                    trial_type="setting",
                    media_id=f"media-{index}",
                    media_path=f"/tmp/{index}.mp4",
                    subtitle_path=f"/tmp/{index}.srt",
                    config={"candidate": index},
                    status="complete",
                    score=score,
                ).to_record()
                for index, score in enumerate([92.0, 25.0, 70.0, 55.0, 88.0], start=1)
            ]
            append_setting_trials(trials, tmpdir)
            split_rules = [
                LearnedRuleEntry(rule_text="강한 규칙", rule_type="split_rule", frequency=20, confidence=0.95).to_record(),
                LearnedRuleEntry(rule_text="약한 규칙", rule_type="split_rule", frequency=1, confidence=0.2).to_record(),
                LearnedRuleEntry(rule_text="중간 규칙", rule_type="split_rule", frequency=5, confidence=0.75).to_record(),
            ]
            save_learned_rules("split", split_rules, tmpdir)

            result = prune_low_value_personalization_data(
                store_dir=tmpdir,
                trigger="training_job:optimize_settings",
                appended_counts={"setting_trials": 1},
            )

            self.assertEqual(result["removed"]["setting_trials"], 1)
            self.assertEqual(result["removed"]["split_rules"], 1)
            paths = store_paths(tmpdir)
            remaining_trials = [
                json.loads(line)
                for line in paths["setting_trials"].read_text(encoding="utf-8").strip().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(remaining_trials), 4)
            self.assertNotIn(25.0, [float(row.get("score", 0.0) or 0.0) for row in remaining_trials])
            remaining_rules = load_learned_rules("split", tmpdir)["items"]
            self.assertEqual(len(remaining_rules), 2)
            self.assertNotIn("약한 규칙", [row.get("rule_text") for row in remaining_rules])
            manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(manifest["counts"]["retention_history_rows"], 1)

    def test_retention_noop_protects_small_datasets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            trial = TrialRecord(
                trial_type="setting",
                media_id="small-media",
                media_path="/tmp/small.mp4",
                subtitle_path="/tmp/small.srt",
                config={"candidate": "small"},
                status="complete",
                score=12.0,
            ).to_record()
            append_setting_trials([trial], tmpdir)

            result = prune_low_value_personalization_data(
                store_dir=tmpdir,
                trigger="training_job:optimize_settings",
                appended_counts={"setting_trials": 1},
            )

            self.assertEqual(result["total_removed"], 0)
            paths = store_paths(tmpdir)
            lines = paths["setting_trials"].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(manifest["counts"]["retention_history_rows"], 0)

    def test_unified_lora_bundle_can_be_forced_and_tracks_record_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)
            append_prompt_trials(
                [
                    TrialRecord(
                        trial_type="prompt",
                        media_id="bundle-media",
                        media_path="/tmp/bundle.mp4",
                        subtitle_path="/tmp/bundle.srt",
                        config={"provider": "inherit"},
                        prompt_template_id="bundle_prompt",
                        prompt_text="Keep the subtitle concise.",
                        status="complete",
                        score=91.0,
                    ).to_record()
                ],
                tmpdir,
            )
            (paths["text_lora_corpus"]).write_text(
                json.dumps(
                    {
                        "task": "text_correction",
                        "source": "unit_test",
                        "input": "안녕 하세요",
                        "output": "안녕하세요",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (paths["text_lora_corpus_manifest"]).write_text(
                json.dumps(
                    {
                        "schema": "ai_subtitle_studio.personalization_corpus_manifest.v1",
                        "updated_at": "2026-05-05T00:00:00",
                        "stats": {"total_items": 1},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = refresh_unified_lora_data_bundle(tmpdir, force=True)
            self.assertTrue(result["exists"])
            self.assertTrue(result["refreshed"])
            self.assertTrue(zipfile.is_zipfile(Path(result["path"])))
            self.assertEqual(result["record_count"], 2)
            payload = load_unified_lora_data_bundle(result["path"])
            self.assertEqual(payload["records"][0]["kind"], "prompt_trials")
            self.assertEqual(payload["sections"]["prompt_trials"][0]["prompt_template_id"], "bundle_prompt")
            self.assertEqual(payload["storage_mode"], "single_file_managed_zip_bundle")
            self.assertEqual(payload["bundle_role"], "primary_user_managed_lora_learning_file")
            self.assertEqual(payload["archive_format"], "zip")
            self.assertEqual(payload["sections"]["text_lora_corpus"][0]["output"], "안녕하세요")
            self.assertEqual(payload["sections"]["text_lora_corpus_manifest"]["stats"]["total_items"], 1)

    def test_single_bundle_can_restore_internal_cache_files(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as restored_dir:
            initialize_lora_personalization_store(source_dir)
            source_paths = store_paths(source_dir)
            append_truth_table_rows(
                [
                    TruthTableRow(
                        media_id="restore-media",
                        media_path="/tmp/restore.mp4",
                        subtitle_path="/tmp/restore.srt",
                        segment_id="restore:1",
                        start_sec=0.0,
                        end_sec=1.5,
                        raw_ground_truth_text="복원 테스트입니다.",
                        speech_training_text="복원 테스트입니다.",
                    ).to_record()
                ],
                source_dir,
            )
            save_training_queue(
                [
                    TrainingQueueItem(
                        media_id="restore-media",
                        media_path="/tmp/restore.mp4",
                        subtitle_path="/tmp/restore.srt",
                        job_type="optimize_prompts",
                    ).to_record()
                ],
                source_dir,
            )
            source_paths["text_lora_dataset"].write_text(
                json.dumps(
                    {
                        "task": "text_correction",
                        "source": "restore_test",
                        "input": "복원 테스트 입니다",
                        "output": "복원 테스트입니다.",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            source_clip = source_paths["voice_lora_clips"] / "speaker-a" / "clip.wav"
            source_clip.parent.mkdir(parents=True, exist_ok=True)
            source_clip.write_bytes(b"RIFFfake voice clip")
            bundle_result = refresh_unified_lora_data_bundle(source_dir, force=True)

            restore_result = restore_lora_personalization_store_from_bundle(bundle_result["path"], restored_dir)
            restored_paths = store_paths(restored_dir)
            restored_clip = restored_paths["voice_lora_clips"] / "speaker-a" / "clip.wav"
            restored_truth_rows = [
                json.loads(line)
                for line in restored_paths["truth_table"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            restored_text_rows = [
                json.loads(line)
                for line in restored_paths["text_lora_dataset"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(restore_result["record_count"], 2)
            self.assertEqual(restore_result["restored_attachment_files"], 1)
            self.assertEqual(restored_truth_rows[0]["media_id"], "restore-media")
            self.assertEqual(restored_text_rows[0]["output"], "복원 테스트입니다.")
            self.assertEqual(restored_clip.read_bytes(), b"RIFFfake voice clip")
            self.assertEqual(load_training_queue(restored_dir)["items"][0]["job_type"], "optimize_prompts")
            self.assertTrue(restored_paths["unified_lora_data"].exists())

    def test_initialize_can_rebuild_cache_from_bundle_only(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as bundle_only_dir:
            initialize_lora_personalization_store(source_dir)
            append_truth_table_rows(
                [
                    TruthTableRow(
                        media_id="bundle-only-media",
                        media_path="/tmp/only.mp4",
                        subtitle_path="/tmp/only.srt",
                        segment_id="only:1",
                        start_sec=0.0,
                        end_sec=1.5,
                        raw_ground_truth_text="파일 하나만 있어도 됩니다.",
                        speech_training_text="파일 하나만 있어도 됩니다.",
                    ).to_record()
                ],
                source_dir,
            )
            source_bundle = Path(refresh_unified_lora_data_bundle(source_dir, force=True)["path"])
            target_bundle = store_paths(bundle_only_dir)["unified_lora_data"]
            target_bundle.parent.mkdir(parents=True, exist_ok=True)
            target_bundle.write_bytes(source_bundle.read_bytes())

            manifest = initialize_lora_personalization_store(bundle_only_dir)

            self.assertEqual(manifest["counts"]["truth_table_rows"], 1)
            restored_truth = store_paths(bundle_only_dir)["truth_table"].read_text(encoding="utf-8")
            self.assertIn("bundle-only-media", restored_truth)

    def test_initialize_can_migrate_legacy_json_bundle_to_zip(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as bundle_only_dir:
            initialize_lora_personalization_store(source_dir)
            append_truth_table_rows(
                [
                    TruthTableRow(
                        media_id="legacy-json-media",
                        media_path="/tmp/legacy.mp4",
                        subtitle_path="/tmp/legacy.srt",
                        segment_id="legacy:1",
                        start_sec=0.0,
                        end_sec=1.5,
                        raw_ground_truth_text="예전 JSON 파일도 불러옵니다.",
                        speech_training_text="예전 JSON 파일도 불러옵니다.",
                    ).to_record()
                ],
                source_dir,
            )
            refresh_unified_lora_data_bundle(source_dir, force=True)
            payload = load_unified_lora_data_bundle(store_dir=source_dir)
            target_paths = store_paths(bundle_only_dir)
            target_paths["root"].mkdir(parents=True, exist_ok=True)
            target_paths["legacy_unified_lora_data"].write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            manifest = initialize_lora_personalization_store(bundle_only_dir)

            self.assertEqual(manifest["counts"]["truth_table_rows"], 1)
            self.assertTrue(zipfile.is_zipfile(target_paths["unified_lora_data"]))
            self.assertFalse(target_paths["legacy_unified_lora_data"].exists())
            restored_truth = target_paths["truth_table"].read_text(encoding="utf-8")
            self.assertIn("legacy-json-media", restored_truth)

    def test_reset_lora_personalization_store_deletes_learning_data_and_reinitializes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)
            append_truth_table_rows(
                [
                    TruthTableRow(
                        media_id="reset-media",
                        media_path="/tmp/reset.mp4",
                        subtitle_path="/tmp/reset.srt",
                        segment_id="reset:1",
                        start_sec=0.0,
                        end_sec=1.5,
                        raw_ground_truth_text="처음부터 다시 학습합니다.",
                        speech_training_text="처음부터 다시 학습합니다.",
                    ).to_record()
                ],
                tmpdir,
            )
            clip_path = paths["voice_lora_clips"] / "speaker" / "clip.wav"
            clip_path.parent.mkdir(parents=True, exist_ok=True)
            clip_path.write_bytes(b"RIFFfake wav data")
            refresh_unified_lora_data_bundle(tmpdir, force=True)

            result = reset_lora_personalization_store(tmpdir)
            reset_paths = store_paths(tmpdir)

            self.assertGreater(result["deleted_files"], 0)
            self.assertFalse(clip_path.exists())
            self.assertTrue(reset_paths["root"].exists())
            self.assertTrue(reset_paths["unified_lora_data"].exists())
            self.assertEqual(result["manifest"]["counts"]["truth_table_rows"], 0)
            self.assertEqual(result["manifest"]["counts"]["unified_lora_data_records"], 0)
            self.assertEqual(reset_paths["truth_table"].read_text(encoding="utf-8"), "")

    def test_llm_review_json_export_and_import_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            truth_row = TruthTableRow(
                media_id="media-llm",
                media_path="/tmp/llm.mp4",
                subtitle_path="/tmp/llm.srt",
                segment_id="seg-1",
                start_sec=1.0,
                end_sec=2.5,
                raw_ground_truth_text="근데 이건 좋아요.",
                speech_training_text="근데 이건 좋아요.",
                detected_split_rule="근데",
            ).to_record()
            append_truth_table_rows([truth_row], tmpdir)

            export_result = export_llm_review_request(store_dir=tmpdir, max_rows_per_section=5)
            paths = store_paths(tmpdir)
            request_payload = json.loads(paths["llm_review_request"].read_text(encoding="utf-8"))

            self.assertEqual(export_result["schema"], LLM_REVIEW_REQUEST_SCHEMA)
            self.assertEqual(request_payload["schema"], LLM_REVIEW_REQUEST_SCHEMA)
            self.assertEqual(request_payload["return_json_template"]["schema"], LLM_REVIEW_RESULT_SCHEMA)
            self.assertIn("ChatGPT", request_payload["workflow"]["supported_reviewers"])
            self.assertEqual(len(request_payload["data"]["truth_table_recent_rows"]), 1)

            result_payload = {
                "schema": LLM_REVIEW_RESULT_SCHEMA,
                "review_id": export_result["review_id"],
                "accepted_split_rules": [
                    {
                        "rule_text": "근데",
                        "confidence": 0.92,
                        "examples": ["근데 이건 좋아요."],
                        "reason": "truth table에서 반복 가능한 접속 표현입니다.",
                    }
                ],
                "accepted_line_break_rules": [
                    {
                        "rule_text": "12|8",
                        "confidence": 0.81,
                        "examples": ["첫 줄 예시\n둘째 줄"],
                    }
                ],
                "prompt_trials": [
                    {
                        "prompt_template_id": "manual_llm_review",
                        "prompt_text": "Keep spoken Korean style while avoiding invented content.",
                        "score": 88.5,
                        "reason": "보수적 검토 프롬프트",
                    }
                ],
                "setting_recommendations": {
                    "global_recommended_defaults": {"audio_preset": "clear_voice"},
                },
                "notes": ["반복 검증 필요"],
            }

            import_result = import_llm_review_result(result_payload, store_dir=tmpdir)
            self.assertEqual(import_result["inserted_split_rules"], 1)
            self.assertEqual(import_result["inserted_line_break_rules"], 1)
            self.assertEqual(import_result["appended_prompt_trials"], 1)
            self.assertTrue(import_result["settings_updated"])
            self.assertTrue(paths["llm_review_result"].exists())

            split_rules = load_learned_rules("split", tmpdir)["items"]
            line_break_rules = load_learned_rules("line_break", tmpdir)["items"]
            self.assertEqual(split_rules[0]["metadata"]["source"], "manual_llm_review")
            self.assertEqual(line_break_rules[0]["metadata"]["source"], "manual_llm_review")
            self.assertEqual(load_best_settings(tmpdir)["global_recommended_defaults"]["audio_preset"], "clear_voice")

            manifest = refresh_lora_personalization_manifest(tmpdir)
            self.assertEqual(manifest["counts"]["prompt_trial_rows"], 1)
            self.assertEqual(manifest["counts"]["llm_review_request_files"], 1)
            self.assertEqual(manifest["counts"]["llm_review_result_files"], 1)


if __name__ == "__main__":
    unittest.main()
