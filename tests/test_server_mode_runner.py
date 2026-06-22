from __future__ import annotations

import argparse
import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from unittest.mock import patch

from tools import server_mode_runner


class ServerModeRunnerTests(unittest.TestCase):
    def test_artifact_applied_word_precision_clip_rows_copies_reject_reason_from_raw_rows(self):
        rows = server_mode_runner._artifact_applied_word_precision_clip_rows(
            [
                {
                    "primary_text": "11.4",
                    "start": 25.06,
                    "end": 27.6,
                }
            ],
            [],
            [
                {
                    "text": "11.4",
                    "start": 25.06,
                    "end": 27.6,
                    "precision_reject_reason": "candidate_similarity_below_threshold",
                    "precision_reject_detail": {
                        "similarity": 0.2,
                        "min_similarity": 0.8,
                    },
                }
            ],
            [
                {
                    "text": "11.4",
                    "start": 25.06,
                    "end": 27.6,
                }
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["likely_applied"])
        self.assertEqual(rows[0]["matched_output_text"], "11.4")
        self.assertEqual(rows[0]["precision_reject_reason"], "candidate_similarity_below_threshold")
        self.assertEqual(
            rows[0]["precision_reject_detail"],
            {
                "similarity": 0.2,
                "min_similarity": 0.8,
            },
        )

    def test_artifact_gap_owner_groups_assigns_reference_gaps_to_source_spans(self):
        groups = server_mode_runner._artifact_gap_owner_groups(
            [
                {
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "action": "split",
                    "split_count": 2,
                    "text": "앞 구간",
                },
                {
                    "source_start": 4.0,
                    "source_end": 6.0,
                    "action": "post_gap_duration_clamp",
                    "split_count": None,
                    "text": "뒤 구간",
                },
            ],
            [
                {
                    "start": 0.5,
                    "end": 1.5,
                    "duration_sec": 1.0,
                    "text": "앞 gap",
                    "best_overlap_ratio": 0.0,
                },
                {
                    "start": 4.2,
                    "end": 5.6,
                    "duration_sec": 1.4,
                    "text": "뒤 gap",
                    "best_overlap_ratio": 0.1,
                },
                {
                    "start": 7.0,
                    "end": 8.0,
                    "duration_sec": 1.0,
                    "text": "무관 gap",
                    "best_overlap_ratio": 0.0,
                },
            ],
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["sample_texts"], ["뒤 구간"])
        self.assertEqual(groups[0]["reference_gap_rows"][0]["text"], "뒤 gap")
        self.assertEqual(groups[1]["sample_texts"], ["앞 구간"])
        self.assertEqual(groups[1]["reference_gap_rows"][0]["text"], "앞 gap")

    def test_artifact_span_owner_flow_merges_split_restore_trim_and_gap_views(self):
        flow = server_mode_runner._artifact_span_owner_flow(
            [
                {
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "action": "split",
                    "split_count": 2,
                    "split_index": 0,
                    "text": "앞 구간",
                }
            ],
            [
                {
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "split_count": 2,
                    "observed_split_indexes": [0],
                    "missing_split_indexes": [1],
                }
            ],
            [
                {
                    "raw_text": "앞 구간",
                    "split_count": 2,
                    "restored_split_indexes": [0, 1],
                    "restored_count": 2,
                    "has_digit_word_text": True,
                    "singleton_word_text_count": 0,
                    "phrase_word_text_count": 2,
                }
            ],
            [
                {
                    "decision": "keep",
                    "split_count": 2,
                    "split_index": 0,
                    "text": "앞 구간",
                },
                {
                    "decision": "drop",
                    "split_count": 2,
                    "split_index": 1,
                    "text": "앞 구간",
                },
            ],
            [
                {
                    "source_start": 0.0,
                    "source_end": 3.0,
                    "reference_gap_count": 1,
                    "reference_gap_total_duration_sec": 1.0,
                    "reference_gap_rows": [{"text": "앞 gap"}],
                }
            ],
            [
                {
                    "stage": "pre_cleanup_review",
                    "rows": [
                        {
                            "source_start": 0.0,
                            "source_end": 3.0,
                            "start": 0.0,
                            "end": 1.5,
                            "duration_sec": 1.5,
                            "text": "앞 구간",
                            "split_index": 0,
                            "split_count": 2,
                            "raw_text": "앞 구간 원문",
                            "word_text": "앞 구간",
                            "raw_lock_reason": "subtitle_llm_disabled",
                        }
                    ],
                }
            ],
        )

        self.assertEqual(len(flow), 1)
        self.assertEqual(flow[0]["missing_split_indexes"], [1])
        self.assertTrue(flow[0]["raw_restore_group"]["present"])
        self.assertEqual(flow[0]["raw_restore_group"]["class"], "all_phrase")
        self.assertEqual(flow[0]["trim_recent_overlap"]["drop_split_indexes"], [1])
        self.assertEqual(flow[0]["reference_gap_rows"][0]["text"], "앞 gap")
        self.assertEqual(flow[0]["pre_cleanup_rows"][0]["text"], "앞 구간")

    def test_raw_restore_group_classification_counts(self):
        counts = server_mode_runner._raw_restore_group_classification_counts(
            [
                {
                    "raw_text": "a",
                    "singleton_word_text_count": 2,
                    "phrase_word_text_count": 0,
                    "has_digit_word_text": True,
                },
                {
                    "raw_text": "b",
                    "singleton_word_text_count": 1,
                    "phrase_word_text_count": 2,
                    "has_digit_word_text": False,
                },
                {
                    "raw_text": "c",
                    "singleton_word_text_count": 0,
                    "phrase_word_text_count": 3,
                    "has_digit_word_text": True,
                },
            ]
        )

        self.assertEqual(
            counts,
            {
                "all_singleton": 1,
                "mixed": 1,
                "all_phrase": 1,
                "has_digit_word_text": 2,
            },
        )

    def test_server_env_forces_no_ui_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            env = server_mode_runner._server_env()

        self.assertEqual(env["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(env["AI_SUBTITLE_SERVER_MODE"], "1")
        self.assertEqual(env["AI_SUBTITLE_SERVER_NO_UI"], "1")

    def test_benchmark_command_preserves_variant_and_ranking_args(self):
        args = argparse.Namespace(
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
            variants=["apple_case1_high_selective_timing_priority", "apple_case2_high_selective"],
        )

        command = server_mode_runner._benchmark_command(args)

        self.assertIn("--ranking-policy", command)
        self.assertIn("timing_priority_speed_weighted", command)
        self.assertIn("--variants", command)
        self.assertIn("apple_case1_high_selective_timing_priority", command)
        self.assertIn("apple_case2_high_selective", command)

    def test_run_benchmark_prints_json_envelope(self):
        args = argparse.Namespace(
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
            variants=["apple_case1_high_selective_timing_priority"],
        )
        stdout = StringIO()
        with patch("tools.server_mode_runner.subprocess.run") as run_mock, patch(
            "sys.stdout", stdout
        ):
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = '{"json":"/tmp/result.json"}'
            run_mock.return_value.stderr = ""
            code = server_mode_runner._run_benchmark(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertIn("command", payload)
        self.assertEqual(payload["stdout"], '{"json":"/tmp/result.json"}')

    def test_benchmark_preset_maps_to_triplet_variants(self):
        args = argparse.Namespace(
            preset="apple_compare_triplet",
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
        )

        mapped = server_mode_runner._preset_namespace(args)

        self.assertEqual(
            mapped.variants,
            [
                "stt_original_selective_no_llm",
                "apple_case1_high_selective_timing_priority",
                "apple_case2_high_selective",
            ],
        )

    def test_benchmark_preset_maps_case2_timing_variant(self):
        args = argparse.Namespace(
            preset="apple_case2_timing",
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
        )

        mapped = server_mode_runner._preset_namespace(args)

        self.assertEqual(mapped.variants, ["apple_case2_high_selective_timing_priority"])

    def test_run_benchmark_preset_prints_compact_payload(self):
        args = argparse.Namespace(
            preset="apple_case2_timing",
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
        )
        stdout = StringIO()
        with patch("tools.server_mode_runner._run_preset_once_payload", return_value={"ok": True, "winner": {"name": "case2"}}), patch(
            "sys.stdout", stdout
        ):
            code = server_mode_runner._run_benchmark_preset(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["winner"]["name"], "case2")

    def test_artifact_summary_payload_extracts_compact_rows(self):
        with TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "benchmark_results.json"
            raw_dir = Path(tmpdir) / "apple_case1_high_selective_timing_priority"
            reference_srt = Path(tmpdir) / "reference.srt"
            raw_dir.mkdir(parents=True, exist_ok=True)
            reference_srt.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:00,000 --> 00:00:01,200",
                        "메타데이터만 없는 후보",
                        "",
                        "2",
                        "00:00:02,000 --> 00:00:03,200",
                        "17.8",
                        "",
                        "3",
                        "00:00:03,500 --> 00:00:04,200",
                        "누락된 참조 줄",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "raw_segments.json").write_text(
                json.dumps(
                    [
                        {
                            "start": 0.0,
                            "end": 1.6,
                            "text": "메타데이터만 없는 후보",
                            "stt_score": 22,
                            "stt_score_flags": [
                                "no_speech_prob_missing",
                                "avg_logprob_missing",
                                "word_confidence_missing",
                            ],
                            "quality": {"vad_alignment_score": 100.0},
                        },
                        {
                            "start": 2.0,
                            "end": 3.2,
                            "text": "17.8",
                            "stt_score": 22,
                            "stt_word_precision_applied": True,
                            "stt_score_flags": [
                                "no_speech_prob_missing",
                                "avg_logprob_missing",
                                "word_confidence_missing",
                            ],
                            "asr_metadata": {
                                "selective_word_timestamps": {
                                    "range_start": 2.0,
                                    "range_end": 3.2,
                                    "source": "STT1",
                                }
                            },
                            "quality": {"vad_alignment_score": 100.0},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "output_segments.json").write_text(
                json.dumps(
                    [
                        {
                            "start": 0.0,
                            "end": 1.6,
                            "text": "메타데이터만 없는 후보",
                            "stt_word_precision_applied": True,
                            "asr_metadata": {
                                "selective_word_timestamps": {
                                    "range_start": 0.0,
                                    "range_end": 2.0,
                                    "source": "STT1",
                                }
                            },
                            "_final_stt_anchor_guard_policy": {
                                "task": "final_stt_anchor_guard",
                                "action": "restore_stt_anchor",
                                "source": "STT1",
                            },
                            "_final_transcript_integrity_policy": {
                                "task": "final_transcript_integrity_guard",
                                "accepted": True,
                                "reason": "ok",
                                "source_segments": 2,
                                "final_segments": 2,
                                "source_compact_len": 20,
                                "candidate_compact_len": 20,
                                "similarity": 0.99,
                                "length_delta_ratio": 0.0,
                            },
                            "_common_split_guard_policy": {
                                "action": "split",
                                "split_count": 2,
                                "split_index": 0,
                                "source_start": 0.0,
                                "source_end": 3.2,
                            },
                        },
                        {
                            "start": 2.0,
                            "end": 3.2,
                            "text": "17.8",
                            "stt_word_precision_applied": True,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "stage_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "stage": "deep_split",
                            "stage_label": "분할/묶음 정리",
                            "segment_count": 4,
                            "sample_texts": ["메타데이터만 없는 후보", "17.8"],
                            "first_start": 0.0,
                            "last_end": 3.2,
                            "rows": [
                                {
                                    "start": 0.0,
                                    "end": 1.6,
                                    "duration_sec": 1.6,
                                    "text": "메타데이터만 없는 후보",
                                    "split_index": 0,
                                    "split_count": 2,
                                    "source_start": 0.0,
                                    "source_end": 3.2,
                                    "selected_source": "STT1",
                                    "has_common_split_policy": True,
                                    "raw_lock_reason": "",
                                    "restored_after_postprocess": False,
                                    "raw_text": "",
                                    "word_text": "메타데이터만 없는 후보",
                                }
                            ],
                        },
                        {
                            "stage": "final_integrity_guard",
                            "stage_label": "최종 자막/STT 원문 무결성 확인",
                            "segment_count": 2,
                            "sample_texts": ["메타데이터만 없는 후보", "17.8"],
                            "first_start": 0.0,
                            "last_end": 3.2,
                            "rows": [
                                {
                                    "start": 0.0,
                                    "end": 1.6,
                                    "duration_sec": 1.6,
                                    "text": "메타데이터만 없는 후보",
                                    "split_index": 0,
                                    "split_count": 2,
                                    "source_start": 0.0,
                                    "source_end": 3.2,
                                    "selected_source": "STT1",
                                    "has_common_split_policy": True,
                                    "raw_lock_reason": "",
                                    "restored_after_postprocess": False,
                                    "raw_text": "",
                                    "word_text": "메타데이터만 없는 후보",
                                }
                            ],
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "stage_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "stage": "deep_split",
                            "stage_label": "분할/묶음 정리",
                            "segment_count": 4,
                            "since_first_ms": 4.0,
                            "since_previous_ms": None,
                        },
                        {
                            "stage": "final_integrity_guard",
                            "stage_label": "최종 자막/STT 원문 무결성 확인",
                            "segment_count": 2,
                            "since_first_ms": 11.5,
                            "since_previous_ms": 7.5,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "major_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "phase": "primary_transcribe",
                            "elapsed_ms": 1200.0,
                            "since_start_ms": 1200.0,
                            "row_count": 4,
                        },
                        {
                            "phase": "final_postprocess",
                            "elapsed_ms": 25.5,
                            "since_start_ms": 1225.5,
                            "row_count": 2,
                        },
                        {
                            "phase": "release_runtime_models",
                            "elapsed_ms": 10.0,
                            "since_start_ms": 1235.5,
                            "row_count": 0,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "selective_ensemble_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "phase": "primary_collect",
                            "elapsed_ms": 1180.0,
                            "row_count": 2,
                            "model": "apple_speech:ko-KR",
                            "collect_runtime_info_found": True,
                            "collect_runtime_info": {
                                "model": "apple_speech:ko-KR",
                                "cache_key": "ko|apple_speech:ko-KR",
                                "reuse_enabled": False,
                                "worker_source": "transient_child_worker",
                                "transient_worker": True,
                                "native_memory_snapshot_force_refresh": True,
                                "preexisting_child_processor_count": 0,
                                "preexisting_cached_worker_count": 0,
                                "preexisting_busy_worker_count": 0,
                                "preexisting_alive_owner_runtime_count": 0,
                                "preexisting_alive_child_runtime_count": 0,
                                "preexisting_alive_cached_worker_count": 0,
                                "preexisting_alive_runtime_total_count": 0,
                                "pressure_stage": "critical",
                                "allow_collect_worker_reuse": False,
                                "resource_snapshot": {
                                    "available_memory_ratio": 0.1433,
                                    "compressed_memory_ratio": 0.4059,
                                    "process_rss_bytes": 116457472,
                                    "memory_pressure_stage": "critical",
                                },
                                "duration_first_submission_enabled": True,
                                "submission_order_indices": [2, 0, 1],
                                "submitted_chunk_paths": ["/tmp/a.wav", "/tmp/b.wav", "/tmp/c.wav"],
                                "submitted_chunk_durations_sec": [3.0, 2.0, 1.0],
                                "submitted_chunk_offsets_sec": [20.0, 0.0, 10.0],
                                "completed_chunk_paths": ["/tmp/b.wav", "/tmp/c.wav", "/tmp/a.wav"],
                                "completed_chunk_elapsed_ms": [5000.0, 7000.0, 9000.0],
                                "emitted_chunk_paths": ["/tmp/b.wav", "/tmp/c.wav", "/tmp/a.wav"],
                                "emitted_chunk_elapsed_ms": [5200.0, 7200.0, 9200.0],
                            },
                        },
                        {
                            "phase": "secondary_low_score_recheck",
                            "elapsed_ms": 22.5,
                            "row_count": 2,
                            "model": "whisperkit-persistent:large-v3",
                            "recheck_plan_source_counts": {
                                "low_score": 2,
                                "missing_voice": 0,
                                "route_hint": 1,
                                "merged": 3,
                            },
                            "raw_range_count": 4,
                            "range_count": 3,
                            "prepared_clip_count": 3,
                            "collected_segment_count": 2,
                            "applied_range_count": 1,
                            "skipped_range_count": 2,
                            "applied_segment_count": 1,
                            "retained_primary_segment_count": 2,
                            "collect_runtime_info_found": True,
                            "collect_runtime_info": {
                                "model": "whisperkit-persistent:large-v3",
                                "cache_key": "ko|whisperkit-persistent:large-v3",
                                "reuse_enabled": False,
                                "worker_source": "transient_child_worker",
                                "transient_worker": True,
                                "native_memory_snapshot_force_refresh": False,
                                "preexisting_child_processor_count": 0,
                                "preexisting_cached_worker_count": 0,
                                "preexisting_busy_worker_count": 0,
                                "preexisting_alive_owner_runtime_count": 0,
                                "preexisting_alive_child_runtime_count": 0,
                                "preexisting_alive_cached_worker_count": 0,
                                "preexisting_alive_runtime_total_count": 0,
                                "pressure_stage": "critical",
                                "allow_collect_worker_reuse": False,
                                "resource_snapshot": {
                                    "available_memory_ratio": 0.1433,
                                    "compressed_memory_ratio": 0.4059,
                                    "process_rss_bytes": 116457472,
                                    "memory_pressure_stage": "critical",
                                },
                                "duration_first_submission_enabled": True,
                                "submission_order_indices": [0, 1],
                                "submitted_chunk_paths": ["/tmp/r1.wav", "/tmp/r2.wav"],
                                "submitted_chunk_durations_sec": [2.0, 1.5],
                                "submitted_chunk_offsets_sec": [15.0, 22.0],
                                "completed_chunk_paths": ["/tmp/r1.wav", "/tmp/r2.wav"],
                                "completed_chunk_elapsed_ms": [2100.0, 3100.0],
                                "emitted_chunk_paths": ["/tmp/r1.wav", "/tmp/r2.wav"],
                                "emitted_chunk_elapsed_ms": [2300.0, 3300.0],
                            },
                        },
                        {
                            "phase": "word_precision_recheck",
                            "elapsed_ms": 11.0,
                            "row_count": 2,
                            "model": "apple_speech:ko-KR",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "word_precision_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "phase": "range_select",
                            "elapsed_ms": 1.5,
                            "segment_count": 4,
                            "range_count": 2,
                        },
                        {
                            "phase": "prepare_clips",
                            "elapsed_ms": 6.0,
                            "range_count": 2,
                            "prepared_clip_count": 2,
                            "prepared_total_clip_duration_sec": 3.5,
                            "prepared_max_clip_duration_sec": 2.0,
                            "prepared_clip_rows": [
                                {
                                    "path": "/tmp/clip_a.wav",
                                    "start": 0.0,
                                    "end": 2.0,
                                    "duration_sec": 2.0,
                                    "primary_text": "메타데이터만 없는 후보",
                                    "secondary_text": "",
                                    "best_original_score": 61.0,
                                },
                                {
                                    "path": "/tmp/clip_b.wav",
                                    "start": 3.0,
                                    "end": 4.5,
                                    "duration_sec": 1.5,
                                    "primary_text": "17.8",
                                    "secondary_text": "",
                                    "best_original_score": 59.0,
                                },
                            ],
                        },
                        {
                            "phase": "collect_segments",
                            "elapsed_ms": 11.0,
                            "collected_segment_count": 2,
                            "collect_clip_rows": [
                                {
                                    "path": "/tmp/clip_a.wav",
                                    "start": 0.0,
                                    "end": 2.0,
                                    "duration_sec": 2.0,
                                    "source_chunk_path": "/tmp/chunk_a.wav",
                                    "source_chunk_start": 0.0,
                                    "source_chunk_duration_sec": 5.0,
                                    "local_start": 0.0,
                                    "local_end": 2.0,
                                    "padding_sec": 0.2,
                                    "primary_text": "메타데이터만 없는 후보",
                                    "merged_clip_count": 1,
                                    "collected_segment_count": 1,
                                    "collected_text_segment_count": 1,
                                    "collected_total_duration_sec": 1.6,
                                    "collected_sample_texts": ["메타데이터만 없는 후보"],
                                },
                                {
                                    "path": "/tmp/clip_b.wav",
                                    "start": 3.0,
                                    "end": 4.5,
                                    "duration_sec": 1.5,
                                    "source_chunk_path": "/tmp/chunk_b.wav",
                                    "source_chunk_start": 3.0,
                                    "source_chunk_duration_sec": 4.0,
                                    "local_start": 0.0,
                                    "local_end": 1.5,
                                    "padding_sec": 0.2,
                                    "primary_text": "17.8",
                                    "merged_clip_count": 1,
                                    "collected_segment_count": 1,
                                    "collected_text_segment_count": 1,
                                    "collected_total_duration_sec": 1.2,
                                    "collected_sample_texts": ["17.8"],
                                },
                            ],
                            "prepared_clip_rows": [
                                {
                                    "path": "/tmp/clip_a.wav",
                                    "start": 0.0,
                                    "end": 2.0,
                                    "duration_sec": 2.0,
                                    "source_chunk_path": "/tmp/chunk_a.wav",
                                    "source_chunk_start": 0.0,
                                    "source_chunk_duration_sec": 5.0,
                                    "local_start": 0.0,
                                    "local_end": 2.0,
                                    "padding_sec": 0.2,
                                    "primary_text": "메타데이터만 없는 후보",
                                    "secondary_text": "",
                                    "best_original_score": 61.0,
                                    "collected_segment_count": 1,
                                    "collected_text_segment_count": 1,
                                    "collected_total_duration_sec": 1.6,
                                    "collected_sample_texts": ["메타데이터만 없는 후보"],
                                },
                                {
                                    "path": "/tmp/clip_b.wav",
                                    "start": 3.0,
                                    "end": 4.5,
                                    "duration_sec": 1.5,
                                    "source_chunk_path": "/tmp/chunk_b.wav",
                                    "source_chunk_start": 3.0,
                                    "source_chunk_duration_sec": 4.0,
                                    "local_start": 0.0,
                                    "local_end": 1.5,
                                    "padding_sec": 0.2,
                                    "primary_text": "17.8",
                                    "secondary_text": "",
                                    "best_original_score": 59.0,
                                    "collected_segment_count": 1,
                                    "collected_text_segment_count": 1,
                                    "collected_total_duration_sec": 1.2,
                                    "collected_sample_texts": ["17.8"],
                                },
                            ],
                            "collect_runtime_info": {
                                "model": "apple_speech:ko-KR",
                                "cache_key": "ko|apple_speech:ko-KR",
                                "reuse_enabled": True,
                                "worker_source": "cached_child_worker_reused",
                                "transient_worker": False,
                                "pressure_stage": "warning",
                                "allow_collect_worker_reuse": True,
                                "preexisting_child_processor_count": 2,
                                "preexisting_cached_worker_count": 1,
                                "preexisting_busy_worker_count": 0,
                                "preexisting_alive_owner_runtime_count": 1,
                                "preexisting_alive_child_runtime_count": 1,
                                "preexisting_alive_cached_worker_count": 1,
                                "preexisting_alive_runtime_total_count": 2,
                                "resource_snapshot": {
                                    "available_memory_ratio": 0.18,
                                    "compressed_memory_ratio": 0.18,
                                    "process_rss_bytes": 123456789,
                                    "memory_pressure_stage": "warning",
                                },
                                "duration_first_submission_enabled": True,
                                "submission_order_indices": [1, 0],
                                "submitted_chunk_paths": ["/tmp/clip_b.wav", "/tmp/clip_a.wav"],
                                "submitted_chunk_durations_sec": [1.5, 2.0],
                                "submitted_chunk_offsets_sec": [3.0, 0.0],
                                "completed_chunk_paths": ["/tmp/clip_b.wav", "/tmp/clip_a.wav"],
                                "completed_chunk_elapsed_ms": [8.4, 11.0],
                            },
                        },
                        {
                            "phase": "annotate_segments",
                            "elapsed_ms": 4.0,
                            "collected_segment_count": 2,
                        },
                        {
                            "phase": "apply_precision",
                            "elapsed_ms": 3.0,
                            "range_count": 2,
                            "collected_segment_count": 2,
                            "applied_count": 2,
                            "result_segment_count": 2,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "final_cleanup_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "stage": "llm_final",
                            "step": "input",
                            "segment_count": 4,
                            "changed": 0,
                            "sample_texts": ["메타데이터만 없는 후보", "17.8"],
                            "rows": [
                                {
                                    "start": 0.0,
                                    "end": 1.6,
                                    "duration_sec": 1.6,
                                    "text": "메타데이터만 없는 후보",
                                    "split_index": 0,
                                    "split_count": 2,
                                    "source_start": 0.0,
                                    "source_end": 3.2,
                                    "selected_source": "STT1",
                                    "cleanup_action": "",
                                }
                            ],
                        },
                        {
                            "stage": "llm_final",
                            "step": "merge_likely_oversplit_rows",
                            "segment_count": 2,
                            "changed": 2,
                            "sample_texts": ["메타데이터만 없는 후보", "17.8"],
                            "rows": [
                                {
                                    "start": 0.0,
                                    "end": 3.2,
                                    "duration_sec": 3.2,
                                    "text": "메타데이터만 없는 후보 17.8",
                                    "split_index": None,
                                    "split_count": None,
                                    "source_start": None,
                                    "source_end": None,
                                    "selected_source": "",
                                    "cleanup_action": "merge",
                                }
                            ],
                        },
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "no_llm_raw_restore_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "step": "anchor_restore",
                            "decision": "skip",
                            "reason": "preserve_common_split_row",
                            "start": 0.0,
                            "end": 1.6,
                            "duration_sec": 1.6,
                            "text": "메타데이터만 없는 후보",
                            "split_index": 0,
                            "split_count": 2,
                            "has_common_split_policy": True,
                            "raw_lock_reason": "",
                            "restored_after_postprocess": False,
                            "raw_text": "메타데이터만 없는 후보",
                            "word_text": "메타데이터만 없는 후보",
                            "selected_source": "STT1",
                            "anchor_text": "메타데이터만 없는 후보 전체",
                            "similarity": 0.71,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (raw_dir / "trim_recent_overlap_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "stage": "llm_final",
                            "decision": "trim",
                            "reason": "recent_overlap_removed",
                            "start": 2.0,
                            "end": 3.2,
                            "duration_sec": 1.2,
                            "text": "17.8 메타데이터만 없는 후보",
                            "trimmed_text": "17.8",
                            "previous_text": "메타데이터만 없는 후보",
                            "prefix_overlap": 0,
                            "suffix_overlap": 1,
                            "split_index": 1,
                            "split_count": 2,
                            "has_common_split_policy": True,
                            "token_count": 2,
                            "previous_token_count": 1,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            json_path.write_text(
                json.dumps(
                    {
                        "reference_srt": str(reference_srt),
                        "start_sec": 0.0,
                        "end_sec": 4.0,
                        "ranked_results": [
                            {
                                "name": "apple_case1_high_selective_timing_priority",
                                "elapsed_sec": 12.473,
                                "quality": {
                                    "quality_score": 86.731,
                                    "timing_priority_quality_score": 86.742,
                                    "timing_mae_sec": 0.4304,
                                },
                                "settings": {
                                    "selected_whisper_model": "apple_speech:ko-KR",
                                    "selected_whisper_model_secondary": "whisperkit-persistent:large-v3",
                                    "stt_low_score_recheck_threshold": 78,
                                    "stt_word_timestamps_precision_enabled": True,
                                    "stt_word_timestamps_precision_threshold": 72.0,
                                    "stt_word_timestamps_precision_max_segments": 4,
                                    "stt_word_timestamps_precision_max_audio_sec": 30.0,
                                    "stt_whisper_primary_metadata_only_low_score_recheck_requires_secondary_signal": True,
                                    "stt_whisper_primary_metadata_only_low_score_recheck_skip_max_duration_sec": 2.2,
                                    "stt_whisper_primary_metadata_only_low_score_recheck_skip_min_vad_score": 95.0,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 0,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                                "error": "",
                            },
                            {
                                "name": "stt_original_selective_no_llm",
                                "elapsed_sec": 88.586,
                                "quality": {
                                    "quality_score": 70.928,
                                    "timing_priority_quality_score": 72.057,
                                    "timing_mae_sec": 0.686,
                                },
                                "rank": 2,
                                "error": "",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = server_mode_runner._artifact_summary_payload(json_path)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["row_count"], 2)
        self.assertEqual(payload["winner"]["name"], "apple_case1_high_selective_timing_priority")
        self.assertEqual(payload["rows"][1]["timing_mae_sec"], 0.686)
        self.assertEqual(payload["winner"]["selected_whisper_model"], "apple_speech:ko-KR")
        self.assertEqual(payload["winner"]["word_precision_count"], 0)
        self.assertEqual(payload["winner"]["low_score_diagnostics"]["total_low_score_rows"], 2)
        self.assertEqual(payload["winner"]["low_score_diagnostics"]["short_stable_metadata_only_rows"], 1)
        self.assertEqual(payload["winner"]["low_score_diagnostics"]["surviving_primary_low_score_rows"], 2)
        self.assertEqual(payload["winner"]["low_score_diagnostics"]["skipped_metadata_only_primary_low_score_rows"], 0)
        self.assertEqual(payload["winner"]["low_score_diagnostics"]["surviving_digit_rows"], 1)
        self.assertEqual(payload["winner"]["low_score_diagnostics"]["surviving_low_vad_rows"], 0)
        self.assertEqual(
            payload["winner"]["artifact_primary_recheck_plan_counts"],
            {
                "low_score": 2,
                "missing_voice": 0,
                "route_hint": 0,
                "merged": 2,
                "ranges": 2,
            },
        )
        self.assertEqual(
            payload["winner"]["artifact_primary_recheck_plan_rows"]["low_score"][0]["primary_text"],
            "메타데이터만 없는 후보",
        )
        self.assertEqual(
            payload["winner"]["artifact_primary_recheck_plan_rows"]["low_score"][1]["primary_text"],
            "17.8",
        )
        self.assertEqual(
            payload["winner"]["artifact_primary_recheck_plan_rows"]["ranges"][1]["primary_has_digits"],
            True,
        )
        self.assertAlmostEqual(
            payload["winner"]["artifact_primary_recheck_plan_rows"]["ranges"][0]["duration_sec"],
            1.6,
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_rows"][0]["primary_text"],
            "메타데이터만 없는 후보",
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_rows"][1]["primary_text"],
            "17.8",
        )
        self.assertEqual(
            payload["winner"]["artifact_applied_word_precision_rows"][0]["text"],
            "메타데이터만 없는 후보",
        )
        self.assertEqual(
            payload["winner"]["artifact_applied_word_precision_rows"][0]["precision_range_start"],
            0.0,
        )
        self.assertEqual(
            payload["winner"]["artifact_applied_word_precision_rows"][0]["precision_source"],
            "STT1",
        )
        self.assertFalse(
            payload["winner"]["artifact_applied_word_precision_rows"][0]["precision_range_derived"],
        )
        self.assertEqual(
            payload["winner"]["artifact_applied_word_precision_rows"][1]["text"],
            "17.8",
        )
        self.assertEqual(
            payload["winner"]["artifact_applied_word_precision_rows"][1]["precision_range_start"],
            2.0,
        )
        self.assertEqual(
            payload["winner"]["artifact_applied_word_precision_rows"][1]["precision_source"],
            "STT1",
        )
        self.assertTrue(
            payload["winner"]["artifact_applied_word_precision_rows"][1]["precision_range_derived"],
        )
        self.assertEqual(
            payload["winner"]["artifact_applied_word_precision_rows"][1]["precision_match_text"],
            "17.8",
        )
        self.assertEqual(payload["winner"]["artifact_raw_rows"][0]["text"], "메타데이터만 없는 후보")
        self.assertEqual(payload["winner"]["artifact_output_rows"][1]["text"], "17.8")
        self.assertEqual(payload["winner"]["artifact_common_split_rows"][0]["text"], "메타데이터만 없는 후보")
        self.assertEqual(payload["winner"]["artifact_common_split_rows"][0]["split_count"], 2)
        self.assertEqual(payload["winner"]["artifact_common_split_rows"][0]["source_duration_sec"], 3.2)
        self.assertEqual(payload["winner"]["artifact_missing_common_split_groups"][0]["observed_split_indexes"], [0])
        self.assertEqual(payload["winner"]["artifact_missing_common_split_groups"][0]["missing_split_indexes"], [1])
        self.assertEqual(payload["winner"]["artifact_stage_trace"][0]["stage"], "deep_split")
        self.assertEqual(payload["winner"]["artifact_stage_trace"][0]["segment_count"], 4)
        self.assertEqual(payload["winner"]["artifact_stage_trace"][0]["rows"][0]["split_count"], 2)
        self.assertTrue(payload["winner"]["artifact_stage_trace"][0]["rows"][0]["has_common_split_policy"])
        self.assertEqual(payload["winner"]["artifact_stage_trace"][0]["rows"][0]["selected_source"], "STT1")
        self.assertEqual(payload["winner"]["artifact_stage_trace"][1]["stage"], "final_integrity_guard")
        self.assertEqual(payload["winner"]["artifact_stage_runtime_trace"][0]["stage"], "deep_split")
        self.assertEqual(payload["winner"]["artifact_stage_runtime_trace"][1]["since_previous_ms"], 7.5)
        self.assertEqual(payload["winner"]["artifact_major_runtime_trace"][0]["phase"], "primary_transcribe")
        self.assertEqual(payload["winner"]["artifact_major_runtime_trace"][1]["elapsed_ms"], 25.5)
        self.assertEqual(payload["winner"]["artifact_selective_ensemble_runtime_trace"][0]["phase"], "primary_collect")
        self.assertTrue(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][0]["collect_runtime_info_found"]
        )
        self.assertEqual(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][0]["collect_runtime_info"]["worker_source"],
            "transient_child_worker",
        )
        self.assertTrue(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][0]["collect_runtime_info"]["native_memory_snapshot_force_refresh"]
        )
        self.assertEqual(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][0]["collect_runtime_info"]["submission_order_indices"],
            [2, 0, 1],
        )
        self.assertEqual(payload["winner"]["artifact_selective_ensemble_runtime_trace"][1]["elapsed_ms"], 22.5)
        self.assertEqual(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][1]["recheck_plan_source_counts"]["route_hint"],
            1,
        )
        self.assertEqual(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][1]["raw_range_count"],
            4,
        )
        self.assertEqual(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][1]["applied_range_count"],
            1,
        )
        self.assertEqual(
            payload["winner"]["artifact_selective_ensemble_runtime_trace"][1]["collect_runtime_info"]["submitted_chunk_paths"],
            ["/tmp/r1.wav", "/tmp/r2.wav"],
        )
        self.assertEqual(payload["winner"]["artifact_word_precision_runtime_trace"][0]["phase"], "range_select")
        self.assertEqual(payload["winner"]["artifact_word_precision_runtime_trace"][2]["elapsed_ms"], 11.0)
        self.assertEqual(
            payload["winner"]["artifact_word_precision_runtime_trace"][2]["collect_runtime_info"]["worker_source"],
            "cached_child_worker_reused",
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_runtime_trace"][2]["collect_runtime_info"]["preexisting_alive_runtime_total_count"],
            2,
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_runtime_trace"][2]["collect_runtime_info"]["resource_snapshot"],
            {
                "available_memory_ratio": 0.18,
                "compressed_memory_ratio": 0.18,
                "process_rss_bytes": 123456789,
                "memory_pressure_stage": "warning",
            },
        )
        self.assertTrue(
            payload["winner"]["artifact_word_precision_runtime_trace"][2]["collect_runtime_info"]["duration_first_submission_enabled"]
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_runtime_trace"][2]["collect_runtime_info"]["submission_order_indices"],
            [1, 0],
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_runtime_trace"][2]["prepared_clip_rows"][0]["collected_segment_count"],
            1,
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_runtime_trace"][2]["collect_clip_rows"][0]["merged_clip_count"],
            1,
        )
        self.assertEqual(payload["winner"]["artifact_word_precision_runtime_trace"][4]["applied_count"], 2)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][0]["duration_sec"], 2.0)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][1]["primary_text"], "17.8")
        self.assertTrue(payload["winner"]["artifact_word_precision_clip_rows"][0]["likely_applied"])
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][0]["collected_segment_count"], 1)
        self.assertEqual(
            payload["winner"]["artifact_word_precision_clip_rows"][0]["collected_sample_texts"],
            ["메타데이터만 없는 후보"],
        )
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][0]["source_chunk_path"], "/tmp/chunk_a.wav")
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][0]["padding_sec"], 0.2)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][0]["submission_index"], 1)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][1]["submission_index"], 0)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][0]["completion_order_index"], 1)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][0]["completed_chunk_elapsed_ms"], 11.0)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][1]["completion_order_index"], 0)
        self.assertEqual(payload["winner"]["artifact_word_precision_clip_rows"][1]["completed_chunk_elapsed_ms"], 8.4)
        self.assertEqual(
            payload["winner"]["artifact_word_precision_clip_rows"][0]["matched_applied_text"],
            "메타데이터만 없는 후보",
        )
        self.assertEqual(payload["winner"]["artifact_word_precision_chunk_groups"][0]["source_chunk_path"], "/tmp/chunk_b.wav")
        self.assertEqual(payload["winner"]["artifact_word_precision_chunk_groups"][0]["non_applied_clip_count"], 1)
        self.assertEqual(payload["winner"]["artifact_word_precision_chunk_groups"][1]["source_chunk_path"], "/tmp/chunk_a.wav")
        self.assertEqual(payload["winner"]["artifact_word_precision_overlap_groups"][0]["source_chunk_path"], "/tmp/chunk_b.wav")
        self.assertEqual(payload["winner"]["artifact_word_precision_overlap_groups"][0]["cluster_span_sec"], 1.5)
        self.assertEqual(payload["winner"]["artifact_word_precision_overlap_groups"][0]["collected_total_duration_sec"], 1.2)
        self.assertEqual(payload["winner"]["artifact_word_precision_overlap_groups"][0]["non_applied_collected_total_duration_sec"], 1.2)
        self.assertEqual(
            payload["winner"]["artifact_word_precision_overlap_groups"][0]["clip_roles"][0]["role"],
            "non_applied",
        )
        self.assertTrue(
            payload["winner"]["artifact_word_precision_overlap_groups"][0]["clip_roles"][0]["pure_numeric"]
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_overlap_groups"][0]["clip_roles"][0]["collected_duration_ratio"],
            0.8,
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_overlap_groups"][0]["clip_roles"][0]["submission_index"],
            0,
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_overlap_groups"][0]["clip_roles"][0]["completed_chunk_elapsed_ms"],
            8.4,
        )
        self.assertEqual(
            payload["winner"]["artifact_word_precision_overlap_groups"][0]["max_non_applied_completed_chunk_elapsed_ms"],
            8.4,
        )
        self.assertEqual(payload["winner"]["artifact_word_precision_overlap_groups"][1]["clip_count"], 1)
        self.assertEqual(payload["winner"]["artifact_word_precision_low_yield_clip_rows"], [])
        self.assertEqual(payload["winner"]["artifact_word_precision_collect_clip_rows"][0]["source_chunk_path"], "/tmp/chunk_a.wav")
        self.assertEqual(payload["winner"]["artifact_final_cleanup_trace"][0]["step"], "input")
        self.assertEqual(payload["winner"]["artifact_final_cleanup_trace"][1]["step"], "merge_likely_oversplit_rows")
        self.assertEqual(payload["winner"]["artifact_final_cleanup_trace"][1]["changed"], 2)
        self.assertEqual(payload["winner"]["artifact_final_cleanup_trace"][0]["rows"][0]["split_count"], 2)
        self.assertEqual(payload["winner"]["artifact_final_cleanup_trace"][1]["rows"][0]["cleanup_action"], "merge")
        self.assertEqual(payload["winner"]["artifact_no_llm_raw_restore_trace"][0]["reason"], "preserve_common_split_row")
        self.assertTrue(payload["winner"]["artifact_no_llm_raw_restore_trace"][0]["has_common_split_policy"])
        self.assertEqual(payload["winner"]["artifact_no_llm_raw_restore_trace"][0]["anchor_text"], "메타데이터만 없는 후보 전체")
        self.assertEqual(payload["winner"]["artifact_raw_restore_restore_groups"], [])
        self.assertEqual(payload["winner"]["artifact_trim_recent_overlap_trace"][0]["decision"], "trim")
        self.assertEqual(payload["winner"]["artifact_trim_recent_overlap_trace"][0]["reason"], "recent_overlap_removed")
        self.assertEqual(payload["winner"]["artifact_trim_recent_overlap_trace"][0]["trimmed_text"], "17.8")
        self.assertEqual(payload["winner"]["artifact_trim_recent_overlap_trace"][0]["suffix_overlap"], 1)
        self.assertEqual(payload["winner"]["artifact_reference_rows"][0]["text"], "메타데이터만 없는 후보")
        self.assertEqual(payload["winner"]["artifact_reference_rows"][1]["text"], "17.8")
        self.assertEqual(payload["winner"]["artifact_reference_gap_rows"][0]["text"], "누락된 참조 줄")
        self.assertEqual(payload["winner"]["artifact_reference_gap_rows"][0]["best_overlap_sec"], 0.0)
        self.assertEqual(payload["winner"]["artifact_gap_owner_groups"], [])
        self.assertEqual(payload["winner"]["artifact_span_owner_flow"][0]["missing_split_indexes"], [1])
        self.assertFalse(payload["winner"]["artifact_span_owner_flow"][0]["raw_restore_group"]["present"])
        self.assertEqual(payload["winner"]["artifact_span_owner_flow"][0]["trim_recent_overlap"]["trim_split_indexes"], [])
        self.assertEqual(payload["winner"]["artifact_span_owner_flow"][0]["pre_cleanup_rows"][0]["text"], "메타데이터만 없는 후보")
        self.assertEqual(payload["winner"]["artifact_output_gap_rows"], [])
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["precision_candidate_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["precision_applied_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["recheck_range_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["common_split_output_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["gap_owner_group_count"], 0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["span_owner_flow_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["raw_restore_restore_group_count"], 0)
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["raw_restore_restore_group_class_counts"],
            {
                "all_singleton": 0,
                "mixed": 0,
                "all_phrase": 0,
                "has_digit_word_text": 0,
            },
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["stt_anchor_guard_row_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["stt_anchor_guard_trim_row_count"], 0)
        self.assertTrue(payload["winner"]["runtime_stage_budget"]["final_transcript_integrity_accepted"])
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["trim_recent_overlap_decisions"]["trim"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["stage_segment_counts"]["deep_split"], 4)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["stage_runtime_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["stage_runtime_total_ms"], 11.5)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["stage_runtime_ms_by_stage"]["final_integrity_guard"], 7.5)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_stage_name"], "final_integrity_guard")
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_stage_ms"], 7.5)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["major_runtime_count"], 3)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["major_runtime_total_ms"], 1235.5)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["major_runtime_ms_by_phase"]["primary_transcribe"], 1200.0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_major_phase_name"], "primary_transcribe")
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_major_phase_ms"], 1200.0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["major_wallclock_gap_ms"], 11237.5)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["selective_runtime_count"], 3)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["selective_runtime_total_ms"], 1213.5)
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["selective_runtime_ms_by_phase"]["secondary_low_score_recheck"],
            22.5,
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["primary_collect_pressure_stage"], "critical")
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["primary_collect_worker_source"],
            "transient_child_worker",
        )
        self.assertFalse(payload["winner"]["runtime_stage_budget"]["primary_collect_reuse_enabled"])
        self.assertTrue(
            payload["winner"]["runtime_stage_budget"]["primary_collect_duration_first_submission_enabled"]
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["primary_collect_submitted_chunk_count"], 3)
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["primary_collect_pressure_stage_source"],
            "native_top_level_pressure_stage",
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["primary_collect_pressure_stage_trigger_reason"],
            "critical_compressed_memory_ratio",
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_low_score_source_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_route_hint_source_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_raw_range_count"], 4)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_range_count"], 3)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_prepared_clip_count"], 3)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_collected_segment_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_applied_range_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_skipped_range_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_applied_segment_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["secondary_recheck_collect_pressure_stage"], "critical")
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["secondary_recheck_collect_worker_source"],
            "transient_child_worker",
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_selective_phase_name"], "primary_collect")
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_selective_phase_ms"], 1180.0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_runtime_count"], 5)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_runtime_total_ms"], 25.5)
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_runtime_ms_by_phase"]["collect_segments"],
            11.0,
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_clip_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_overlap_group_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_non_applied_overlap_group_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_max_overlap_group_span_sec"], 2.0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_overlap_group_collected_duration_sec"], 2.8)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_non_applied_overlap_group_collected_duration_sec"], 1.2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_max_overlap_group_collected_duration_sec"], 1.6)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_max_completed_chunk_elapsed_ms"], 11.0)
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_max_non_applied_completed_chunk_elapsed_ms"],
            8.4,
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_low_yield_clip_count"], 0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_low_yield_clip_collected_duration_sec"], 0.0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_max_low_yield_clip_waste_score"], 0.0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_collected_segment_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_non_applied_collected_segment_count"], 1)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_source_chunk_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_collect_clip_count"], 2)
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_available_memory_ratio"],
            0.18,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_compressed_memory_ratio"],
            0.18,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_process_rss_bytes"],
            123456789,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_preexisting_alive_runtime_total_count"],
            2,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_pressure_stage_source"],
            "native_top_level_pressure_stage",
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_pressure_stage_trigger_reason"],
            "warning_available_memory_ratio",
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_available_memory_critical_ratio_threshold"],
            0.12,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_available_memory_critical_headroom"],
            0.06,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_compressed_memory_critical_ratio_threshold"],
            0.22,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_compressed_memory_critical_headroom"],
            0.04,
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_pressure_reasons"],
            ["warning_available_memory_ratio"],
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_pressure_reason_stage"],
            "warning",
        )
        self.assertFalse(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_pressure_stage_reason_mismatch"]
        )
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_pressure_stage_reason_mismatch_kind"],
            "",
        )
        self.assertTrue(
            payload["winner"]["runtime_stage_budget"]["word_precision_collect_duration_first_submission_enabled"]
        )
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_collect_submitted_chunk_count"], 2)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_total_clip_duration_sec"], 3.5)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["word_precision_max_clip_duration_sec"], 2.0)
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_word_precision_phase_name"], "collect_segments")
        self.assertEqual(payload["winner"]["runtime_stage_budget"]["slowest_word_precision_phase_ms"], 11.0)
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["final_cleanup_step_changes"]["merge_likely_oversplit_rows"],
            2,
        )
        self.assertEqual(payload["winner"]["artifact_stt_anchor_guard_rows"][0]["guard_action"], "restore_stt_anchor")
        self.assertTrue(payload["winner"]["artifact_final_transcript_integrity_policy"]["accepted"])
        self.assertEqual(
            payload["winner"]["runtime_stage_budget"]["runtime_policy_snapshot"]["stt_word_timestamps_precision_threshold"],
            72.0,
        )

    def test_extract_trailing_json_object_skips_log_prefix(self):
        payload = server_mode_runner._extract_trailing_json_object(
            "2026-06-02 log line\\nmore log\\n{\"json\":\"/tmp/result.json\",\"ok\":true}\n"
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["json"], "/tmp/result.json")

    def test_extract_recheck_source_counts_reads_latest_log_line(self):
        payload = server_mode_runner._extract_recheck_source_counts(
            "x\\n  🧭 [Fast-STT2] 후보 source low_score=4 missing_voice=1 route_hint=2 merged=6\\n"
        )

        self.assertEqual(
            payload,
            {"low_score": 4, "missing_voice": 1, "route_hint": 2, "merged": 6},
        )

    def test_compare_artifacts_reports_compact_deltas(self):
        with TemporaryDirectory() as tmpdir:
            baseline = Path(tmpdir) / "baseline.json"
            candidate = Path(tmpdir) / "candidate.json"
            baseline.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "baseline",
                                "elapsed_sec": 88.586,
                                "quality": {
                                    "quality_score": 70.928,
                                    "timing_priority_quality_score": 72.057,
                                    "timing_mae_sec": 0.686,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 6,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            candidate.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case1",
                                "elapsed_sec": 17.165,
                                "quality": {
                                    "quality_score": 86.731,
                                    "timing_priority_quality_score": 86.742,
                                    "timing_mae_sec": 0.4304,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 0,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            args = argparse.Namespace(baseline_json=str(baseline), candidate_json=str(candidate))
            stdout = StringIO()
            with patch("sys.stdout", stdout):
                code = server_mode_runner._run_compare_artifacts(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertAlmostEqual(payload["deltas"]["elapsed_sec_delta"], -71.421)
        self.assertAlmostEqual(payload["deltas"]["quality_score_delta"], 15.803)
        self.assertAlmostEqual(payload["deltas"]["timing_mae_sec_delta"], -0.2556)
        self.assertAlmostEqual(payload["deltas"]["word_precision_count_delta"], -6.0)

    def test_compare_current_vs_accepted_reports_runtime_budget_deltas(self):
        with TemporaryDirectory() as tmpdir:
            accepted = Path(tmpdir) / "accepted.json"
            current = Path(tmpdir) / "current.json"
            accepted_dir = Path(tmpdir) / "case2"
            current_dir = Path(tmpdir) / "case2_experiment"
            accepted_dir.mkdir(parents=True, exist_ok=True)
            current_dir.mkdir(parents=True, exist_ok=True)
            accepted.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case2",
                                "elapsed_sec": 15.503,
                                "quality": {
                                    "quality_score": 85.164,
                                    "timing_priority_quality_score": 85.498,
                                    "timing_mae_sec": 0.4076,
                                },
                                "settings": {
                                    "stt_word_timestamps_precision_threshold": 70.0,
                                    "stt_word_timestamps_precision_max_segments": 32,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 3,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (accepted_dir / "stage_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {"stage": "deep_split", "stage_label": "분할", "segment_count": 15, "since_first_ms": 5.0, "since_previous_ms": None},
                        {"stage": "final_integrity_guard", "stage_label": "무결성", "segment_count": 13, "since_first_ms": 20.0, "since_previous_ms": 15.0},
                    ]
                ),
                encoding="utf-8",
            )
            (accepted_dir / "major_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {"phase": "primary_transcribe", "elapsed_ms": 1200.0, "since_start_ms": 1200.0, "row_count": 15},
                        {"phase": "final_postprocess", "elapsed_ms": 10.0, "since_start_ms": 1210.0, "row_count": 13},
                        {"phase": "release_runtime_models", "elapsed_ms": 5.0, "since_start_ms": 1215.0, "row_count": 0},
                    ]
                ),
                encoding="utf-8",
            )
            (accepted_dir / "selective_ensemble_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "phase": "primary_collect",
                            "elapsed_ms": 1180.0,
                            "row_count": 15,
                            "model": "whisperkit-persistent:large-v3",
                            "collect_runtime_info_found": True,
                            "collect_runtime_info": {
                                "reuse_enabled": False,
                                "worker_source": "owner_runtime_direct",
                                "pressure_stage": "critical",
                                "preexisting_alive_runtime_total_count": 0,
                                "duration_first_submission_enabled": False,
                                "stt_benchmark_plan": {
                                    "requested_model": "mlx-community/whisper-large-v3",
                                    "active_backend": "whisperkit_persistent",
                                    "active_model": "whisperkit-persistent:large-v3",
                                    "active_reason": "autotuned_backend",
                                    "challengers": [
                                        {
                                            "backend": "apple_speech",
                                            "model": "apple_speech:ko-KR",
                                            "reason": "apple_speech_high_challenger_benchmark_only",
                                        }
                                    ],
                                    "vad_challenger": {
                                        "provider": "silero",
                                        "reason": "benchmark_probe",
                                    },
                                },
                                "submitted_chunk_paths": ["/tmp/full.wav"],
                                "submitted_chunk_durations_sec": [30.0],
                                "submitted_chunk_offsets_sec": [0.0],
                                "completed_chunk_paths": ["/tmp/full.wav"],
                                "completed_chunk_elapsed_ms": [8240.608],
                                "emitted_chunk_paths": ["/tmp/full.wav"],
                                "emitted_chunk_elapsed_ms": [8245.781],
                                "resource_snapshot": {
                                    "available_memory_ratio": 0.14,
                                    "compressed_memory_ratio": 0.41,
                                    "process_rss_bytes": 123456000,
                                    "memory_pressure_stage": "critical",
                                },
                            },
                        },
                        {"phase": "secondary_low_score_recheck", "elapsed_ms": 20.0, "row_count": 15, "model": "apple_speech:ko-KR"},
                        {"phase": "word_precision_recheck", "elapsed_ms": 15.0, "row_count": 13, "model": "whisperkit-persistent:large-v3"},
                    ]
                ),
                encoding="utf-8",
            )
            (accepted_dir / "word_precision_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {"phase": "range_select", "elapsed_ms": 2.0, "segment_count": 15, "range_count": 3},
                        {
                            "phase": "prepare_clips",
                            "elapsed_ms": 5.0,
                            "range_count": 3,
                            "prepared_clip_count": 3,
                            "prepared_total_clip_duration_sec": 6.5,
                            "prepared_max_clip_duration_sec": 3.0,
                            "prepared_clip_rows": [
                                {"path": "/tmp/a.wav", "start": 0.0, "end": 3.0, "duration_sec": 3.0, "primary_text": "A", "secondary_text": "", "best_original_score": 61.0, "collected_total_duration_sec": 3.2},
                                {"path": "/tmp/b.wav", "start": 4.0, "end": 6.0, "duration_sec": 2.0, "primary_text": "B", "secondary_text": "", "best_original_score": 59.0, "collected_total_duration_sec": 2.1},
                                {"path": "/tmp/c.wav", "start": 7.0, "end": 8.5, "duration_sec": 1.5, "primary_text": "C", "secondary_text": "", "best_original_score": 58.0, "collected_total_duration_sec": 1.2},
                            ],
                        },
                        {
                            "phase": "collect_segments",
                            "elapsed_ms": 6.0,
                            "collected_segment_count": 3,
                            "collect_owner_bound": True,
                            "collect_owner_type": "VideoProcessor",
                            "collect_runtime_info_found": True,
                            "collect_runtime_info": {
                                "reuse_enabled": True,
                                "worker_source": "cached_child_worker_reused",
                                "pressure_stage": "warning",
                                "allow_collect_worker_reuse": True,
                                "transient_worker": False,
                                "resource_snapshot": {
                                    "available_memory_ratio": 0.18,
                                    "compressed_memory_ratio": 0.18,
                                    "process_rss_bytes": 123456789,
                                    "memory_pressure_stage": "warning",
                                },
                                "duration_first_submission_enabled": True,
                                "submission_order_indices": [0, 2, 1],
                                "submitted_chunk_paths": ["/tmp/a.wav", "/tmp/c.wav", "/tmp/b.wav"],
                                "submitted_chunk_durations_sec": [3.0, 1.5, 2.0],
                                "submitted_chunk_offsets_sec": [0.0, 7.0, 4.0],
                            },
                        },
                        {"phase": "annotate_segments", "elapsed_ms": 2.0, "collected_segment_count": 3},
                        {"phase": "apply_precision", "elapsed_ms": 1.0, "range_count": 3, "collected_segment_count": 3, "applied_count": 2, "result_segment_count": 13},
                    ]
                ),
                encoding="utf-8",
            )
            current.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case2_experiment",
                                "elapsed_sec": 18.0,
                                "quality": {
                                    "quality_score": 85.0,
                                    "timing_priority_quality_score": 85.2,
                                    "timing_mae_sec": 0.41,
                                },
                                "settings": {
                                    "stt_word_timestamps_precision_threshold": 72.0,
                                    "stt_word_timestamps_precision_max_segments": 28,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 2,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (current_dir / "stage_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {"stage": "deep_split", "stage_label": "분할", "segment_count": 15, "since_first_ms": 6.0, "since_previous_ms": None},
                        {"stage": "final_integrity_guard", "stage_label": "무결성", "segment_count": 13, "since_first_ms": 29.5, "since_previous_ms": 23.5},
                    ]
                ),
                encoding="utf-8",
            )
            (current_dir / "major_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {"phase": "primary_transcribe", "elapsed_ms": 1230.0, "since_start_ms": 1230.0, "row_count": 15},
                        {"phase": "final_postprocess", "elapsed_ms": 12.5, "since_start_ms": 1242.5, "row_count": 13},
                        {"phase": "release_runtime_models", "elapsed_ms": 8.5, "since_start_ms": 1251.0, "row_count": 0},
                    ]
                ),
                encoding="utf-8",
            )
            (current_dir / "selective_ensemble_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {
                            "phase": "primary_collect",
                            "elapsed_ms": 1205.0,
                            "row_count": 15,
                            "model": "whisperkit-persistent:large-v3",
                            "collect_runtime_info_found": True,
                            "collect_runtime_info": {
                                "reuse_enabled": False,
                                "worker_source": "owner_runtime_direct",
                                "pressure_stage": "critical",
                                "preexisting_alive_runtime_total_count": 0,
                                "duration_first_submission_enabled": False,
                                "stt_benchmark_plan": {
                                    "requested_model": "mlx-community/whisper-large-v3",
                                    "active_backend": "whisperkit_persistent",
                                    "active_model": "whisperkit-persistent:large-v3",
                                    "active_reason": "autotuned_backend",
                                    "challengers": [
                                        {
                                            "backend": "apple_speech",
                                            "model": "apple_speech:ko-KR",
                                            "reason": "apple_speech_high_challenger_benchmark_only",
                                        }
                                    ],
                                    "vad_challenger": {
                                        "provider": "silero",
                                        "reason": "benchmark_probe",
                                    },
                                },
                                "submitted_chunk_paths": ["/tmp/full.wav"],
                                "submitted_chunk_durations_sec": [30.0],
                                "submitted_chunk_offsets_sec": [0.0],
                                "completed_chunk_paths": ["/tmp/full.wav"],
                                "completed_chunk_elapsed_ms": [9405.25],
                                "emitted_chunk_paths": ["/tmp/full.wav"],
                                "emitted_chunk_elapsed_ms": [9410.5],
                                "resource_snapshot": {
                                    "available_memory_ratio": 0.14,
                                    "compressed_memory_ratio": 0.41,
                                    "process_rss_bytes": 123456000,
                                    "memory_pressure_stage": "critical",
                                },
                            },
                        },
                        {"phase": "secondary_low_score_recheck", "elapsed_ms": 28.5, "row_count": 15, "model": "apple_speech:ko-KR"},
                        {"phase": "word_precision_recheck", "elapsed_ms": 14.0, "row_count": 13, "model": "whisperkit-persistent:large-v3"},
                    ]
                ),
                encoding="utf-8",
            )
            (current_dir / "word_precision_runtime_trace.json").write_text(
                json.dumps(
                    [
                        {"phase": "range_select", "elapsed_ms": 1.5, "segment_count": 15, "range_count": 2},
                        {
                            "phase": "prepare_clips",
                            "elapsed_ms": 6.0,
                            "range_count": 2,
                            "prepared_clip_count": 2,
                            "prepared_total_clip_duration_sec": 4.0,
                            "prepared_max_clip_duration_sec": 2.5,
                            "prepared_clip_rows": [
                                {"path": "/tmp/a.wav", "start": 0.0, "end": 2.5, "duration_sec": 2.5, "primary_text": "A", "secondary_text": "", "best_original_score": 60.0, "collected_total_duration_sec": 2.5},
                                {"path": "/tmp/b.wav", "start": 3.0, "end": 4.5, "duration_sec": 1.5, "primary_text": "B", "secondary_text": "", "best_original_score": 57.0, "collected_total_duration_sec": 1.0},
                            ],
                        },
                        {
                            "phase": "collect_segments",
                            "elapsed_ms": 9.0,
                            "collected_segment_count": 2,
                            "collect_owner_bound": True,
                            "collect_owner_type": "VideoProcessor",
                            "collect_runtime_info_found": True,
                            "collect_runtime_info": {
                                "reuse_enabled": False,
                                "worker_source": "transient_child_worker",
                                "pressure_stage": "critical",
                                "allow_collect_worker_reuse": False,
                                "transient_worker": True,
                                "resource_snapshot": {
                                    "available_memory_ratio": 0.0812,
                                    "compressed_memory_ratio": 0.3634,
                                    "process_rss_bytes": 234567890,
                                    "memory_pressure_stage": "critical",
                                },
                                "duration_first_submission_enabled": True,
                                "submission_order_indices": [1, 0],
                                "submitted_chunk_paths": ["/tmp/b.wav", "/tmp/a.wav"],
                                "submitted_chunk_durations_sec": [1.5, 2.5],
                                "submitted_chunk_offsets_sec": [3.0, 0.0],
                            },
                        },
                        {"phase": "annotate_segments", "elapsed_ms": 3.0, "collected_segment_count": 2},
                        {"phase": "apply_precision", "elapsed_ms": 0.5, "range_count": 2, "collected_segment_count": 2, "applied_count": 2, "result_segment_count": 13},
                    ]
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            args = argparse.Namespace(
                current_json=str(current),
                accepted_target="case2",
                accepted_json="",
                accepted_label="",
                baseline_json=str(Path(tmpdir) / "unused-baseline.json"),
                case1_json=str(Path(tmpdir) / "unused-case1.json"),
                case2_json=str(accepted),
            )
            with patch("sys.stdout", stdout):
                code = server_mode_runner._run_compare_current_vs_accepted(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["accepted_target"], "case2")
        self.assertAlmostEqual(payload["comparison"]["deltas"]["elapsed_sec_delta"], 2.497)
        self.assertEqual(payload["comparison"]["deltas"]["word_precision_count_delta"], -1.0)
        self.assertEqual(payload["runtime_budget_delta"]["precision_candidate_count_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["precision_applied_count_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["missing_common_split_group_count_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["gap_owner_group_count_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["reference_gap_row_count_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["output_gap_row_count_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["stage_runtime_total_ms_delta"], 9.5)
        self.assertEqual(payload["runtime_budget_delta"]["major_runtime_total_ms_delta"], 36.0)
        self.assertEqual(payload["runtime_budget_delta"]["selective_runtime_total_ms_delta"], 32.5)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_runtime_total_ms_delta"], 4.0)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_submitted_chunk_count"], 1)
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_submitted_chunk_count"], 1)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_submitted_total_duration_sec"], 30.0)
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_submitted_total_duration_sec"], 30.0)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_submitted_total_duration_sec_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_max_completed_chunk_elapsed_ms"], 8240.608)
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_max_completed_chunk_elapsed_ms"], 9405.25)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_max_completed_chunk_elapsed_ms_delta"], 1164.642)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_max_emitted_chunk_elapsed_ms"], 8245.781)
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_max_emitted_chunk_elapsed_ms"], 9410.5)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_max_emitted_chunk_elapsed_ms_delta"], 1164.719)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_pressure_stage"], "critical")
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_pressure_stage"], "critical")
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_worker_source"], "owner_runtime_direct")
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_worker_source"], "owner_runtime_direct")
        self.assertFalse(payload["runtime_budget_delta"]["primary_collect_reuse_enabled"])
        self.assertFalse(payload["runtime_budget_delta"]["current_primary_collect_reuse_enabled"])
        self.assertEqual(
            payload["runtime_budget_delta"]["primary_collect_pressure_stage_source"],
            "native_top_level_pressure_stage",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_primary_collect_pressure_stage_source"],
            "native_top_level_pressure_stage",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["primary_collect_pressure_stage_trigger_reason"],
            "critical_compressed_memory_ratio",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_primary_collect_pressure_stage_trigger_reason"],
            "critical_compressed_memory_ratio",
        )
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_active_backend"], "whisperkit_persistent")
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_active_backend"], "whisperkit_persistent")
        self.assertEqual(
            payload["runtime_budget_delta"]["primary_collect_active_model"],
            "whisperkit-persistent:large-v3",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_primary_collect_active_model"],
            "whisperkit-persistent:large-v3",
        )
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_active_reason"], "autotuned_backend")
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_active_reason"], "autotuned_backend")
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_challenger_count"], 1)
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_challenger_count"], 1)
        self.assertEqual(payload["runtime_budget_delta"]["primary_collect_vad_challenger_provider"], "silero")
        self.assertEqual(payload["runtime_budget_delta"]["current_primary_collect_vad_challenger_provider"], "silero")
        self.assertTrue(payload["runtime_budget_delta"]["primary_collect_shape_static"])
        self.assertTrue(payload["runtime_budget_delta"]["primary_collect_route_plan_static"])
        self.assertTrue(payload["runtime_budget_delta"]["primary_collect_state_static"])
        self.assertFalse(payload["runtime_budget_delta"]["primary_collect_completion_latency_dominates"])
        self.assertTrue(payload["primary_collect_shape_static"])
        self.assertTrue(payload["primary_collect_route_plan_static"])
        self.assertTrue(payload["primary_collect_state_static"])
        self.assertFalse(payload["primary_collect_completion_latency_dominates"])
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_clip_count_delta"], -1.0)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_applied_clip_count_delta"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_non_applied_clip_count_delta"], -1.0)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_total_clip_duration_sec_delta"], -2.5)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_non_applied_clip_duration_sec_delta"], -2.5)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_max_clip_duration_sec_delta"], -0.5)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_overlap_group_count_delta"], -1.0)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_non_applied_overlap_group_count_delta"], -1.0)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_max_overlap_group_span_sec_delta"], -0.5)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_overlap_group_collected_duration_sec_delta"], -3.0)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_non_applied_overlap_group_collected_duration_sec_delta"], -3.0)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_max_overlap_group_collected_duration_sec_delta"], -0.7)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_pressure_stage"], "warning")
        self.assertEqual(payload["runtime_budget_delta"]["current_word_precision_collect_pressure_stage"], "critical")
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_worker_source"], "cached_child_worker_reused")
        self.assertEqual(payload["runtime_budget_delta"]["current_word_precision_collect_worker_source"], "transient_child_worker")
        self.assertTrue(payload["runtime_budget_delta"]["word_precision_collect_reuse_enabled"])
        self.assertFalse(payload["runtime_budget_delta"]["current_word_precision_collect_reuse_enabled"])
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_available_memory_ratio"], 0.18)
        self.assertEqual(payload["runtime_budget_delta"]["current_word_precision_collect_available_memory_ratio"], 0.0812)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_available_memory_ratio_delta"], -0.0988)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_compressed_memory_ratio"], 0.18)
        self.assertEqual(payload["runtime_budget_delta"]["current_word_precision_collect_compressed_memory_ratio"], 0.3634)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_compressed_memory_ratio_delta"], 0.1834)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_process_rss_bytes"], 123456789)
        self.assertEqual(payload["runtime_budget_delta"]["current_word_precision_collect_process_rss_bytes"], 234567890)
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_process_rss_bytes_delta"], 111111101.0)
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_pressure_stage_source"],
            "native_top_level_pressure_stage",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_word_precision_collect_pressure_stage_source"],
            "native_top_level_pressure_stage",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_pressure_stage_trigger_reason"],
            "warning_available_memory_ratio",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_word_precision_collect_pressure_stage_trigger_reason"],
            "critical_compressed_memory_ratio",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_available_memory_critical_ratio_threshold"],
            0.12,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_word_precision_collect_available_memory_critical_ratio_threshold"],
            0.12,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_available_memory_critical_headroom"],
            0.06,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_word_precision_collect_available_memory_critical_headroom"],
            -0.0388,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_available_memory_critical_headroom_delta"],
            -0.0988,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_compressed_memory_critical_ratio_threshold"],
            0.22,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_word_precision_collect_compressed_memory_critical_ratio_threshold"],
            0.22,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_compressed_memory_critical_headroom"],
            0.04,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_word_precision_collect_compressed_memory_critical_headroom"],
            -0.1434,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_compressed_memory_critical_headroom_delta"],
            -0.1834,
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_pressure_reasons"],
            ["warning_available_memory_ratio"],
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["current_word_precision_collect_pressure_reasons"],
            [
                "critical_available_memory_ratio",
                "critical_compressed_memory_ratio",
            ],
        )
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_pressure_reason_stage"], "warning")
        self.assertEqual(payload["runtime_budget_delta"]["current_word_precision_collect_pressure_reason_stage"], "critical")
        self.assertFalse(payload["runtime_budget_delta"]["word_precision_collect_pressure_stage_reason_mismatch"])
        self.assertFalse(payload["runtime_budget_delta"]["current_word_precision_collect_pressure_stage_reason_mismatch"])
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_collect_pressure_stage_reason_mismatch_kind"], "")
        self.assertEqual(payload["runtime_budget_delta"]["current_word_precision_collect_pressure_stage_reason_mismatch_kind"], "")
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_pressure_reason_added"],
            ["critical_available_memory_ratio", "critical_compressed_memory_ratio"],
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_collect_pressure_reason_removed"],
            ["warning_available_memory_ratio"],
        )
        self.assertEqual(payload["runtime_budget_delta"]["word_precision_submission_index_changed_count"], 2)
        self.assertTrue(payload["runtime_budget_delta"]["word_precision_submission_order_proven"])
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_submission_delta_rows"][0]["primary_text"],
            "B",
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_submission_delta_rows"][0]["submission_index_delta"],
            -2.0,
        )
        self.assertEqual(payload["runtime_budget_delta"]["major_wallclock_gap_ms_delta"], 2461.0)
        self.assertEqual(
            payload["runtime_budget_delta"]["major_runtime_phase_ms_deltas"],
            {
                "final_postprocess": 2.5,
                "primary_transcribe": 30.0,
                "release_runtime_models": 3.5,
            },
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["selective_runtime_phase_ms_deltas"],
            {
                "primary_collect": 25.0,
                "secondary_low_score_recheck": 8.5,
                "word_precision_recheck": -1.0,
            },
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["word_precision_runtime_phase_ms_deltas"],
            {
                "apply_precision": -0.5,
                "annotate_segments": 1.0,
                "collect_segments": 3.0,
                "prepare_clips": 1.0,
                "range_select": -0.5,
            },
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["raw_restore_restore_group_class_count_deltas"],
            {
                "all_phrase": 0.0,
                "all_singleton": 0.0,
                "has_digit_word_text": 0.0,
                "mixed": 0.0,
            },
        )
        self.assertEqual(payload["runtime_budget_delta"]["trim_recent_overlap_decision_deltas"]["drop"], 0.0)
        self.assertEqual(payload["runtime_budget_delta"]["stage_segment_count_deltas"], {})
        self.assertIn("major_runtime_transcribe", payload["runtime_budget_delta"]["hot_owner_hints"])
        self.assertIn("major_runtime_recheck", payload["runtime_budget_delta"]["hot_owner_hints"])
        self.assertIn("precision_overlap_groups", payload["runtime_budget_delta"]["hot_owner_hints"])
        self.assertIn("precision_collect_order", payload["runtime_budget_delta"]["hot_owner_hints"])
        self.assertIn("native_pressure_stage_source", payload["runtime_budget_delta"]["hot_owner_hints"])
        self.assertIn("critical_pressure_collect_policy", payload["runtime_budget_delta"]["hot_owner_hints"])
        self.assertEqual(payload["hot_owner_hints"], payload["runtime_budget_delta"]["hot_owner_hints"])
        self.assertEqual(payload["runtime_budget_delta"]["final_cleanup_step_change_deltas"], {})
        self.assertEqual(
            payload["runtime_budget_delta"]["runtime_policy_snapshot_changed_keys"],
            [
                "stt_word_timestamps_precision_max_segments",
                "stt_word_timestamps_precision_threshold",
            ],
        )
        self.assertEqual(
            payload["runtime_budget_delta"]["hot_owner_hints"],
            [
                "precision_overlap_groups",
                "major_runtime_transcribe",
                "major_runtime_postprocess",
                "major_runtime_release",
                "major_runtime_recheck",
                "major_runtime_precision",
                "precision_collect_order",
                "available_memory_snapshot_volatility",
                "native_pressure_stage_source",
                "critical_pressure_snapshot_thresholds",
                "critical_pressure_collect_policy",
            ],
        )
        by_file = {item["file"]: item["reasons"] for item in payload["owner_file_shortlist"]}
        self.assertEqual(
            by_file["core/audio/stt_recheck_service.py"],
            ["precision_overlap_groups", "major_runtime_recheck", "precision_collect_order"],
        )
        self.assertEqual(
            by_file["core/audio/media_processor_transcribe_recheck.py"],
            [
                "precision_overlap_groups",
                "major_runtime_recheck",
                "major_runtime_precision",
                "precision_collect_order",
            ],
        )
        self.assertEqual(
            by_file["core/audio/transcribe_policy_helpers.py"],
            ["precision_overlap_groups", "major_runtime_precision"],
        )
        self.assertEqual(
            by_file["core/audio/audio_runtime_services.py"],
            [
                "available_memory_snapshot_volatility",
                "native_pressure_stage_source",
                "critical_pressure_snapshot_thresholds",
                "critical_pressure_collect_policy",
            ],
        )

    def test_hot_owner_hints_demote_native_pressure_when_collect_pressure_state_is_static(self):
        hints = server_mode_runner._hot_owner_hints_from_runtime_budget_delta(
            {
                "major_runtime_phase_ms_deltas": {
                    "primary_transcribe": 1356.015,
                    "final_postprocess": -5.195,
                    "release_runtime_models": -0.45,
                },
                "selective_runtime_phase_ms_deltas": {
                    "primary_collect": 820.577,
                    "secondary_low_score_recheck": 558.278,
                    "word_precision_recheck": -33.065,
                },
                "word_precision_runtime_phase_ms_deltas": {
                    "collect_segments": -66.688,
                    "prepare_clips": 33.626,
                    "annotate_segments": -0.171,
                    "apply_precision": 0.22,
                    "range_select": -0.052,
                },
                "precision_candidate_count_delta": -6.0,
                "recheck_range_count_delta": -11.0,
                "word_precision_collect_pressure_stage": "critical",
                "current_word_precision_collect_pressure_stage": "critical",
                "word_precision_collect_pressure_stage_source": "native_top_level_pressure_stage",
                "current_word_precision_collect_pressure_stage_source": "native_top_level_pressure_stage",
                "word_precision_collect_pressure_stage_trigger_reason": "critical_compressed_memory_ratio",
                "current_word_precision_collect_pressure_stage_trigger_reason": "critical_compressed_memory_ratio",
                "word_precision_collect_worker_source": "transient_child_worker",
                "current_word_precision_collect_worker_source": "transient_child_worker",
                "word_precision_collect_reuse_enabled": False,
                "current_word_precision_collect_reuse_enabled": False,
                "word_precision_collect_pressure_reasons": ["critical_compressed_memory_ratio"],
                "current_word_precision_collect_pressure_reasons": ["critical_compressed_memory_ratio"],
                "word_precision_collect_preexisting_alive_runtime_total_count": 0,
                "current_word_precision_collect_preexisting_alive_runtime_total_count": 0,
            }
        )
        self.assertIn("major_runtime_transcribe", hints)
        self.assertIn("major_runtime_recheck", hints)
        self.assertIn("major_runtime_precision", hints)
        self.assertNotIn("native_pressure_stage_source", hints)
        self.assertNotIn("critical_pressure_collect_policy", hints)

    def test_hot_owner_hints_from_runtime_budget_delta_flags_primary_collect_completion_latency(self):
        hints = server_mode_runner._hot_owner_hints_from_runtime_budget_delta(
            {
                "selective_runtime_phase_ms_deltas": {
                    "primary_collect": 114372.525,
                },
                "primary_collect_submitted_chunk_count": 1,
                "current_primary_collect_submitted_chunk_count": 1,
                "primary_collect_submitted_total_duration_sec_delta": 0.0,
                "primary_collect_max_completed_chunk_elapsed_ms_delta": 114276.086,
                "word_precision_runtime_total_ms_delta": 1194.269,
                "primary_collect_shape_static": True,
                "primary_collect_state_static": True,
                "primary_collect_completion_latency_dominates": True,
            }
        )

        self.assertEqual(hints[0], "primary_collect_completion_latency")
        self.assertIn("major_runtime_transcribe", hints)

    def test_hot_owner_hints_from_runtime_budget_delta_flags_pressure_stage_reason_mismatch(self):
        hints = server_mode_runner._hot_owner_hints_from_runtime_budget_delta(
            {
                "current_word_precision_collect_pressure_stage_reason_mismatch": True,
                "word_precision_collect_pressure_reasons": ["warning_available_memory_ratio"],
                "current_word_precision_collect_pressure_reasons": ["critical_compressed_memory_ratio"],
                "word_precision_collect_pressure_stage": "warning",
                "current_word_precision_collect_pressure_stage": "warning",
                "word_precision_collect_worker_source": "cached_child_worker_reused",
                "current_word_precision_collect_worker_source": "cached_child_worker_reused",
                "word_precision_collect_reuse_enabled": True,
                "current_word_precision_collect_reuse_enabled": True,
            }
        )

        self.assertEqual(
            hints[:2],
            ["pressure_stage_reason_mismatch", "critical_pressure_snapshot_thresholds"],
        )

    def test_hot_owner_hints_from_runtime_budget_delta_flags_available_memory_snapshot_volatility(self):
        hints = server_mode_runner._hot_owner_hints_from_runtime_budget_delta(
            {
                "current_word_precision_collect_pressure_stage_reason_mismatch": True,
                "word_precision_collect_pressure_reasons": ["critical_compressed_memory_ratio"],
                "current_word_precision_collect_pressure_reasons": [
                    "critical_available_memory_ratio",
                    "critical_compressed_memory_ratio",
                ],
                "word_precision_collect_pressure_stage": "warning",
                "current_word_precision_collect_pressure_stage": "warning",
                "word_precision_collect_worker_source": "cached_child_worker_reused",
                "current_word_precision_collect_worker_source": "cached_child_worker_reused",
                "word_precision_collect_reuse_enabled": True,
                "current_word_precision_collect_reuse_enabled": True,
            }
        )

        self.assertEqual(
            hints[:3],
            [
                "available_memory_snapshot_volatility",
                "pressure_stage_reason_mismatch",
                "critical_pressure_snapshot_thresholds",
            ],
        )

    def test_compare_current_vs_accepted_supports_custom_accepted_json_override(self):
        with TemporaryDirectory() as tmpdir:
            accepted = Path(tmpdir) / "diagnostic_case1.json"
            current = Path(tmpdir) / "current.json"
            accepted.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case1_diagnostic",
                                "elapsed_sec": 1.626,
                                "quality": {
                                    "quality_score": 64.861,
                                    "timing_priority_quality_score": 67.113,
                                    "timing_mae_sec": 0.6137,
                                },
                                "settings": {
                                    "stt_low_score_recheck_threshold": 78,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 0,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            current.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case1_experiment",
                                "elapsed_sec": 1.441,
                                "quality": {
                                    "quality_score": 58.544,
                                    "timing_priority_quality_score": 60.744,
                                    "timing_mae_sec": 0.7285,
                                },
                                "settings": {
                                    "stt_low_score_recheck_threshold": 78,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 0,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            args = argparse.Namespace(
                current_json=str(current),
                accepted_target="",
                accepted_json=str(accepted),
                accepted_label="case1_diagnostic",
                baseline_json=str(Path(tmpdir) / "unused-baseline.json"),
                case1_json=str(Path(tmpdir) / "unused-case1.json"),
                case2_json=str(Path(tmpdir) / "unused-case2.json"),
            )
            with patch("sys.stdout", stdout):
                code = server_mode_runner._run_compare_current_vs_accepted(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["accepted_target"], "case1_diagnostic")
        self.assertEqual(payload["accepted"]["json"], str(accepted))
        self.assertAlmostEqual(payload["comparison"]["deltas"]["elapsed_sec_delta"], -0.185)
        self.assertAlmostEqual(payload["comparison"]["deltas"]["quality_score_delta"], -6.317)

    def test_owner_file_shortlist_from_hints_maps_case1_case2_owners(self):
        hints = [
            "common_split",
            "missing_common_split_groups",
            "gap_owner_groups",
            "raw_restore_restore_groups",
            "output_gap_rows",
        ]

        shortlist = server_mode_runner._owner_file_shortlist_from_hints(hints)
        by_file = {item["file"]: item["reasons"] for item in shortlist}

        self.assertEqual(
            by_file["tools/benchmark_subtitle_pipeline_variants.py"],
            ["common_split", "missing_common_split_groups", "gap_owner_groups"],
        )
        self.assertEqual(
            by_file["core/engine/subtitle_engine.py"],
            ["common_split", "missing_common_split_groups", "gap_owner_groups"],
        )
        self.assertEqual(
            by_file["core/engine/subtitle_stt_candidate_selection.py"],
            ["raw_restore_restore_groups"],
        )
        self.assertEqual(
            by_file["core/engine/subtitle_final_integrity.py"],
            ["missing_common_split_groups", "gap_owner_groups", "output_gap_rows"],
        )

    def test_accepted_standings_reports_current_winner_and_pairwise_deltas(self):
        with TemporaryDirectory() as tmpdir:
            baseline = Path(tmpdir) / "baseline.json"
            case1 = Path(tmpdir) / "case1.json"
            case2 = Path(tmpdir) / "case2.json"
            baseline.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "baseline",
                                "elapsed_sec": 85.934,
                                "quality": {
                                    "quality_score": 74.506,
                                    "timing_priority_quality_score": 75.084,
                                    "timing_mae_sec": 0.6768,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 6,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            case1.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case1",
                                "elapsed_sec": 9.923,
                                "quality": {
                                    "quality_score": 64.399,
                                    "timing_priority_quality_score": 66.278,
                                    "timing_mae_sec": 0.7567,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 0,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            case2.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case2",
                                "elapsed_sec": 16.073,
                                "quality": {
                                    "quality_score": 85.164,
                                    "timing_priority_quality_score": 85.498,
                                    "timing_mae_sec": 0.4076,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 3,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                baseline_json=str(baseline),
                case1_json=str(case1),
                case2_json=str(case2),
            )
            stdout = StringIO()
            with patch("sys.stdout", stdout):
                code = server_mode_runner._run_accepted_standings(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["standings"]["overall_quality_timing_winner"], "case2")
        self.assertEqual(payload["standings"]["speed_winner"], "case1")
        self.assertAlmostEqual(
            payload["comparisons"]["case1_vs_baseline"]["deltas"]["elapsed_sec_delta"],
            -76.011,
        )
        self.assertAlmostEqual(
            payload["comparisons"]["case2_vs_case1"]["deltas"]["timing_priority_quality_score_delta"],
            19.22,
        )

    def test_next_owner_plan_payload_prioritizes_case2_precision_overlap_clusters(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 3,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 17.94,
                            "cluster_span_sec": 2.26,
                            "sample_texts": ["계속 17.8인데"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.16,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.68,
                                    "end": 17.94,
                                    "duration_sec": 2.26,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.0,
                                    "submission_index": 7,
                                    "submitted_chunk_duration_sec": 2.26,
                                    "submitted_chunk_offset_sec": 15.68,
                                    "completion_order_index": 7,
                                    "completed_chunk_elapsed_ms": 5783.881,
                                    "emission_order_index": 4,
                                    "emitted_chunk_elapsed_ms": 5784.015,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.16,
                                    "collected_duration_ratio": 0.513,
                                }
                            ],
                        },
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                        },
                        {
                            "cluster_start": 7.44,
                            "cluster_end": 14.8,
                            "cluster_span_sec": 7.36,
                            "sample_texts": ["유지가 되고 있고요", "17.8", "변화가 없네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 1.08,
                        },
                    ],
                    "artifact_primary_recheck_plan_rows": {
                        "merged": [
                            {"start": 22.26, "end": 25.26, "duration_sec": 3.0, "primary_text": "17.8에서 연비가 안 바뀌는데"}
                        ]
                    },
                }
            },
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"], "case2")
        self.assertEqual(
            payload["next_owner_hints"],
            ["collect_path_non_skip_owner", "precision_overlap_groups", "major_runtime_precision"],
        )
        self.assertEqual(
            payload["recommended_experiments"][0]["sample_texts"][0],
            "계속 17.8인데",
        )
        by_file = {item["file"]: item["reasons"] for item in payload["owner_file_shortlist"]}
        self.assertEqual(
            by_file["core/audio/stt_recheck_service.py"],
            ["collect_path_non_skip_owner", "precision_overlap_groups"],
        )
        self.assertEqual(
            by_file["core/audio/media_processor_transcribe_recheck.py"],
            ["collect_path_non_skip_owner", "precision_overlap_groups", "major_runtime_precision"],
        )
        self.assertEqual(payload["preconditions"], [])

    def test_next_owner_plan_payload_flags_case2_artifact_without_collected_duration_instrumentation(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 3,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 7.44,
                            "cluster_end": 14.8,
                            "cluster_span_sec": 7.36,
                            "sample_texts": ["유지가 되고 있고요", "17.8", "변화가 없네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 0.0,
                        },
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 0.0,
                        },
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertEqual(payload["preconditions"][0]["id"], "refresh_case2_collect_instrumentation")
        self.assertIn("benchmark_subtitle_pipeline_variants.py", payload["preconditions"][0]["command"])

    def test_next_owner_plan_payload_prioritizes_case2_overlap_clusters_when_collected_burden_exists(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 3,
                        "precision_candidate_count": 6,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                        "word_precision_collect_pressure_stage": "critical",
                        "word_precision_collect_pressure_stage_source": "native_top_level_pressure_stage",
                        "word_precision_collect_pressure_stage_trigger_reason": "critical_native_pressure_stage",
                        "word_precision_collect_worker_source": "transient_child_worker",
                        "word_precision_collect_owner_type": "VideoProcessor",
                        "word_precision_collect_reuse_enabled": False,
                        "word_precision_collect_allow_worker_reuse": False,
                        "word_precision_collect_pressure_reasons": [
                            "critical_compressed_memory_ratio",
                        ],
                        "word_precision_collect_available_memory_ratio": 0.1509,
                        "word_precision_collect_compressed_memory_ratio": 0.3627,
                        "word_precision_collect_process_rss_bytes": 113852416,
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 17.94,
                            "cluster_span_sec": 2.26,
                            "sample_texts": ["계속 17.8인데"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.16,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.68,
                                    "end": 17.94,
                                    "duration_sec": 2.26,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.0,
                                    "submission_index": 7,
                                    "submitted_chunk_duration_sec": 2.26,
                                    "submitted_chunk_offset_sec": 15.68,
                                    "completion_order_index": 7,
                                    "completed_chunk_elapsed_ms": 5783.881,
                                    "emission_order_index": 4,
                                    "emitted_chunk_elapsed_ms": 5784.015,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.16,
                                    "collected_duration_ratio": 0.513,
                                }
                            ],
                        },
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {
                                    "primary_text": "11.4",
                                    "likely_applied": False,
                                    "pure_numeric": True,
                                    "has_digits": True,
                                    "collected_total_duration_sec": 1.8,
                                },
                                {
                                    "primary_text": "17.8에서 연비가 안 바뀌는데",
                                    "likely_applied": False,
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "collected_total_duration_sec": 1.86,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {
                        "merged": [
                            {"start": 15.88, "end": 17.74, "duration_sec": 1.86, "primary_text": "계속 17.8인데"}
                        ]
                    },
                }
            },
        )

        self.assertEqual(
            payload["next_owner_hints"],
            ["collect_path_non_skip_owner", "collect_path_non_padding_owner", "precision_overlap_groups", "major_runtime_precision"],
        )
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precision_cluster_1")
        self.assertEqual(payload["recommended_experiments"][0]["cluster_start"], 15.68)
        self.assertEqual(payload["recommended_experiments"][0]["non_applied_collected_total_duration_sec"], 1.16)
        self.assertEqual(payload["recommended_experiments"][1]["id"], "case2_precision_cluster_2")
        self.assertEqual(payload["recommended_experiments"][1]["cluster_start"], 22.06)
        self.assertEqual(
            payload["recommended_experiments"][1]["top_non_applied_clip_roles"][0]["primary_text"],
            "11.4",
        )
        self.assertTrue(payload["recommended_experiments"][1]["top_non_applied_clip_roles"][0]["pure_numeric"])
        self.assertEqual(
            payload["recommended_experiments"][1]["recommended_subclips"][0]["id"],
            "case2_precision_cluster_2_subclip_1",
        )
        self.assertEqual(
            payload["recommended_experiments"][1]["recommended_subclips"][0]["experiment_type"],
            "duplicate_pure_numeric_subclip",
        )
        self.assertIn(
            "duplicate_pure_numeric_local_padding_tightening",
            payload["recommended_experiments"][1]["recommended_subclips"][0]["known_rejected_experiment_families"],
        )
        self.assertIn(
            "phrase_linked_pure_numeric_collect_prioritization",
            payload["recommended_experiments"][1]["recommended_subclips"][0]["known_rejected_experiment_families"],
        )
        self.assertNotIn(
            "phrase_linked_pure_numeric_collect_prioritization",
            payload["recommended_experiments"][1]["recommended_subclips"][0].get("revalidation_candidate_experiment_families") or [],
        )
        self.assertEqual(
            payload["recommended_experiments"][1]["recommended_subclips"][0]["preferred_next_experiment_family"],
            "collect_path_non_skip_owner",
        )
        self.assertEqual(
            payload["recommended_experiments"][1]["recommended_subclips"][1]["experiment_type"],
            "digit_phrase_subclip",
        )
        self.assertIn(
            "metadata_only_long_digit_phrase_skip",
            payload["recommended_experiments"][1]["recommended_subclips"][1]["known_rejected_experiment_families"],
        )
        self.assertIn(
            "long_metadata_only_digit_phrase_collect_defer",
            payload["recommended_experiments"][1]["recommended_subclips"][1]["known_rejected_experiment_families"],
        )
        self.assertIn(
            "overlapping_phrase_neighbor_pure_numeric_skip",
            payload["recommended_experiments"][1]["known_rejected_experiment_families"],
        )
        self.assertIn(
            "critical_pressure_collect_policy",
            payload["known_rejected_experiment_families"],
        )
        by_file = {item["file"]: item["reasons"] for item in payload["owner_file_shortlist"]}
        self.assertEqual(
            by_file["core/audio/media_processor_transcribe_recheck.py"],
            ["collect_path_non_skip_owner", "collect_path_non_padding_owner", "precision_overlap_groups", "major_runtime_precision"],
        )
        self.assertNotIn("core/audio/audio_runtime_services.py", by_file)
        self.assertNotIn("core/performance.py", by_file)
        self.assertNotIn("core/native_macos_memory.py", by_file)

    def test_next_owner_plan_payload_surfaces_precollect_worker_residency_before_native_pressure_source(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 1,
                        "precision_candidate_count": 4,
                        "precision_applied_count": 1,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                        "word_precision_collect_pressure_stage": "critical",
                        "word_precision_collect_pressure_stage_source": "native_top_level_pressure_stage",
                        "word_precision_collect_pressure_stage_trigger_reason": "critical_native_pressure_stage",
                        "word_precision_collect_worker_source": "transient_child_worker",
                        "word_precision_collect_owner_type": "VideoProcessor",
                        "word_precision_collect_reuse_enabled": False,
                        "word_precision_collect_allow_worker_reuse": False,
                        "word_precision_collect_preexisting_alive_runtime_total_count": 3,
                        "word_precision_collect_preexisting_alive_owner_runtime_count": 1,
                        "word_precision_collect_preexisting_alive_child_runtime_count": 2,
                        "word_precision_collect_preexisting_alive_cached_worker_count": 1,
                        "word_precision_collect_preexisting_child_processor_count": 2,
                        "word_precision_collect_preexisting_cached_worker_count": 1,
                        "word_precision_collect_pressure_reasons": [
                            "critical_compressed_memory_ratio",
                        ],
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [],
                        }
                    ],
                }
            },
        )

        self.assertEqual(payload["next_owner_hints"][0], "precollect_worker_residency")
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precollect_worker_residency")
        self.assertEqual(payload["recommended_experiments"][0]["preexisting_alive_runtime_total_count"], 3)
        self.assertEqual(payload["recommended_experiments"][1]["id"], "case2_precision_cluster_1")

    def test_next_owner_plan_payload_prioritizes_primary_collect_path_when_primary_collect_dominates(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 2,
                        "precision_candidate_count": 6,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                        "word_precision_collect_pressure_stage": "critical",
                        "word_precision_collect_pressure_stage_source": "native_top_level_pressure_stage",
                        "word_precision_collect_pressure_stage_trigger_reason": "critical_compressed_memory_ratio",
                        "word_precision_collect_worker_source": "transient_child_worker",
                        "word_precision_collect_owner_type": "VideoProcessor",
                        "word_precision_collect_reuse_enabled": False,
                        "word_precision_collect_allow_worker_reuse": False,
                        "word_precision_collect_pressure_reasons": [
                            "critical_compressed_memory_ratio",
                        ],
                        "primary_collect_pressure_stage": "critical",
                        "primary_collect_worker_source": "transient_child_worker",
                        "primary_collect_reuse_enabled": False,
                        "primary_collect_duration_first_submission_enabled": False,
                        "primary_collect_submitted_chunk_count": 1,
                        "primary_collect_submitted_total_duration_sec": 30.0,
                        "primary_collect_preexisting_alive_runtime_total_count": 0,
                        "primary_collect_pressure_stage_source": "native_top_level_pressure_stage",
                        "primary_collect_pressure_stage_trigger_reason": "critical_compressed_memory_ratio",
                        "primary_collect_max_completed_chunk_elapsed_ms": 122516.694,
                        "primary_collect_max_emitted_chunk_elapsed_ms": 122521.472,
                        "primary_collect_active_backend": "whisperkit_persistent",
                        "primary_collect_active_model": "whisperkit-persistent:large-v3",
                        "primary_collect_active_reason": "autotuned_backend",
                        "primary_collect_challenger_count": 1,
                        "primary_collect_vad_challenger_provider": "silero",
                        "secondary_recheck_range_count": 2,
                        "secondary_recheck_applied_range_count": 2,
                        "selective_runtime_ms_by_phase": {
                            "primary_collect": 95627.75,
                            "secondary_low_score_recheck": 2603.99,
                            "word_precision_recheck": 21903.683,
                        },
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {
                                    "primary_text": "11.4",
                                    "likely_applied": False,
                                    "pure_numeric": True,
                                    "has_digits": True,
                                    "collected_total_duration_sec": 1.8,
                                },
                                {
                                    "primary_text": "17.8에서 연비가 안 바뀌는데",
                                    "likely_applied": False,
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "collected_total_duration_sec": 1.86,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertEqual(
            payload["next_owner_hints"][:3],
            ["primary_collect_path", "primary_collect_completion_latency", "major_runtime_transcribe"],
        )
        self.assertIn("secondary_recheck_path", payload["next_owner_hints"])
        self.assertNotIn("native_pressure_stage_source", payload["next_owner_hints"])
        self.assertNotIn("critical_pressure_snapshot_thresholds", payload["next_owner_hints"])
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_primary_collect_path")
        self.assertEqual(payload["recommended_experiments"][0]["focus"], "primary_collect_path")
        self.assertEqual(payload["recommended_experiments"][0]["primary_collect_submitted_chunk_count"], 1)
        self.assertEqual(payload["recommended_experiments"][0]["primary_collect_submitted_total_duration_sec"], 30.0)
        self.assertEqual(payload["recommended_experiments"][0]["primary_collect_max_completed_chunk_elapsed_ms"], 122516.694)
        self.assertEqual(payload["recommended_experiments"][0]["primary_collect_active_backend"], "whisperkit_persistent")
        self.assertEqual(
            payload["recommended_experiments"][0]["primary_collect_active_model"],
            "whisperkit-persistent:large-v3",
        )
        self.assertIn(
            "case2_exact_mlx_primary_route_override",
            payload["recommended_experiments"][0]["known_rejected_experiment_families"],
        )
        by_file = {item["file"]: item["reasons"] for item in payload["owner_file_shortlist"]}
        self.assertEqual(
            by_file["core/audio/media_processor_transcribe.py"],
            ["primary_collect_path", "primary_collect_completion_latency"],
        )
        self.assertEqual(
            by_file["core/audio/media_processor_transcribe_run.py"],
            ["primary_collect_path", "primary_collect_completion_latency", "major_runtime_transcribe"],
        )
        self.assertEqual(
            by_file["core/audio/stt_recheck_service.py"],
            ["secondary_recheck_path", "major_runtime_recheck", "collect_path_non_skip_owner", "precision_overlap_groups"],
        )

    def test_next_owner_plan_payload_prioritizes_pressure_stage_reason_mismatch(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 1,
                        "precision_candidate_count": 4,
                        "precision_applied_count": 2,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                        "word_precision_collect_pressure_stage": "warning",
                        "word_precision_collect_worker_source": "cached_child_worker_reused",
                        "word_precision_collect_owner_type": "VideoProcessor",
                        "word_precision_collect_reuse_enabled": True,
                        "word_precision_collect_allow_worker_reuse": True,
                        "word_precision_collect_pressure_reasons": [
                            "critical_compressed_memory_ratio",
                        ],
                        "word_precision_collect_pressure_reason_stage": "critical",
                        "word_precision_collect_pressure_stage_reason_mismatch": True,
                        "word_precision_collect_pressure_stage_reason_mismatch_kind": "native_warning_raw_critical",
                        "word_precision_collect_available_memory_ratio": 0.1255,
                        "word_precision_collect_available_memory_critical_ratio_threshold": 0.12,
                        "word_precision_collect_available_memory_critical_headroom": 0.0055,
                        "word_precision_collect_compressed_memory_ratio": 0.3685,
                        "word_precision_collect_compressed_memory_critical_ratio_threshold": 0.3,
                        "word_precision_collect_compressed_memory_critical_headroom": -0.0685,
                        "word_precision_collect_process_rss_bytes": 113852416,
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {
                                    "primary_text": "11.4",
                                    "likely_applied": False,
                                    "pure_numeric": True,
                                    "has_digits": True,
                                    "collected_total_duration_sec": 1.8,
                                },
                                {
                                    "primary_text": "17.8에서 연비가 안 바뀌는데",
                                    "likely_applied": False,
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "collected_total_duration_sec": 1.86,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertEqual(payload["next_owner_hints"][0], "pressure_stage_reason_mismatch")
        self.assertIn("precision_overlap_groups", payload["next_owner_hints"])
        self.assertEqual(
            payload["recommended_experiments"][0]["id"],
            "case2_collect_pressure_stage_reason_mismatch",
        )
        self.assertEqual(
            payload["recommended_experiments"][0]["collect_pressure_reason_mismatch_kind"],
            "native_warning_raw_critical",
        )
        self.assertEqual(payload["recommended_experiments"][0]["collect_available_memory_critical_headroom"], 0.0055)
        self.assertEqual(payload["recommended_experiments"][0]["collect_compressed_memory_critical_headroom"], -0.0685)
        by_file = {item["file"]: item["reasons"] for item in payload["owner_file_shortlist"]}
        self.assertEqual(
            by_file["core/audio/audio_runtime_services.py"],
            ["pressure_stage_reason_mismatch"],
        )

    def test_next_owner_plan_payload_prioritizes_available_memory_snapshot_volatility(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 1,
                        "precision_candidate_count": 4,
                        "precision_applied_count": 2,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                        "word_precision_collect_pressure_stage": "warning",
                        "word_precision_collect_worker_source": "cached_child_worker_reused",
                        "word_precision_collect_owner_type": "VideoProcessor",
                        "word_precision_collect_reuse_enabled": True,
                        "word_precision_collect_allow_worker_reuse": True,
                        "word_precision_collect_pressure_reasons": [
                            "critical_available_memory_ratio",
                            "critical_compressed_memory_ratio",
                        ],
                        "word_precision_collect_pressure_reason_stage": "critical",
                        "word_precision_collect_pressure_stage_reason_mismatch": True,
                        "word_precision_collect_pressure_stage_reason_mismatch_kind": "native_warning_raw_critical",
                        "word_precision_collect_available_memory_ratio": 0.1072,
                        "word_precision_collect_available_memory_critical_ratio_threshold": 0.12,
                        "word_precision_collect_available_memory_critical_headroom": -0.0128,
                        "word_precision_collect_compressed_memory_ratio": 0.3665,
                        "word_precision_collect_compressed_memory_critical_ratio_threshold": 0.3,
                        "word_precision_collect_compressed_memory_critical_headroom": -0.0665,
                        "word_precision_collect_process_rss_bytes": 88735744,
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {"primary_text": "11.4", "likely_applied": False, "pure_numeric": True, "has_digits": True, "collected_total_duration_sec": 1.8},
                                {"primary_text": "17.8에서 연비가 안 바뀌는데", "likely_applied": False, "pure_numeric": False, "has_digits": True, "collected_total_duration_sec": 1.86},
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertEqual(payload["next_owner_hints"][0], "available_memory_snapshot_volatility")
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_collect_available_memory_snapshot")
        self.assertEqual(payload["recommended_experiments"][0]["focus"], "available_memory_snapshot_volatility")
        self.assertEqual(payload["recommended_experiments"][0]["collect_available_memory_critical_headroom"], -0.0128)
        self.assertEqual(payload["recommended_experiments"][0]["collect_compressed_memory_critical_headroom"], -0.0665)
        by_file = {item["file"]: item["reasons"] for item in payload["owner_file_shortlist"]}
        self.assertEqual(
            by_file["core/audio/audio_runtime_services.py"],
            ["available_memory_snapshot_volatility", "pressure_stage_reason_mismatch"],
        )

    def test_next_owner_plan_payload_infers_case2_from_artifact_winner_name(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "artifact",
            {
                "winner": {
                    "name": "apple_case2_high_selective_timing_priority",
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 3,
                        "precision_candidate_count": 6,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                        "word_precision_collect_pressure_stage": "critical",
                        "word_precision_collect_pressure_stage_source": "native_top_level_pressure_stage",
                        "word_precision_collect_pressure_stage_trigger_reason": "critical_native_pressure_stage",
                        "word_precision_collect_worker_source": "transient_child_worker",
                        "word_precision_collect_owner_type": "VideoProcessor",
                        "word_precision_collect_reuse_enabled": False,
                        "word_precision_collect_allow_worker_reuse": False,
                        "word_precision_collect_pressure_reasons": [
                            "critical_compressed_memory_ratio",
                        ],
                        "word_precision_collect_available_memory_ratio": 0.1509,
                        "word_precision_collect_compressed_memory_ratio": 0.3627,
                        "word_precision_collect_process_rss_bytes": 113852416,
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 17.94,
                            "cluster_span_sec": 2.26,
                            "sample_texts": ["계속 17.8인데"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.16,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.68,
                                    "end": 17.94,
                                    "duration_sec": 2.26,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.0,
                                    "submission_index": 7,
                                    "submitted_chunk_duration_sec": 2.26,
                                    "submitted_chunk_offset_sec": 15.68,
                                    "completion_order_index": 7,
                                    "completed_chunk_elapsed_ms": 5783.881,
                                    "emission_order_index": 4,
                                    "emitted_chunk_elapsed_ms": 5784.015,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.16,
                                    "collected_duration_ratio": 0.513,
                                }
                            ],
                        },
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {
                                    "primary_text": "11.4",
                                    "start": 25.06,
                                    "end": 27.6,
                                    "duration_sec": 2.54,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": True,
                                    "has_digits": True,
                                    "matched_applied_text": "11.4에서 또 안 바뀌네",
                                    "best_applied_overlap_ratio": 0.063,
                                    "collected_total_duration_sec": 1.8,
                                    "collected_duration_ratio": 0.709,
                                },
                                {
                                    "primary_text": "17.8에서 연비가 안 바뀌는데",
                                    "start": 22.06,
                                    "end": 25.46,
                                    "duration_sec": 3.4,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.0,
                                    "collected_total_duration_sec": 1.86,
                                    "collected_duration_ratio": 0.547,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {
                        "merged": [
                            {"start": 15.88, "end": 17.74, "duration_sec": 1.86, "primary_text": "계속 17.8인데"}
                        ]
                    },
                }
            },
        )

        self.assertEqual(
            payload["next_owner_hints"],
            ["collect_path_non_skip_owner", "collect_path_non_padding_owner", "precision_overlap_groups", "major_runtime_precision"],
        )
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precision_cluster_1")
        self.assertEqual(payload["recommended_experiments"][1]["id"], "case2_precision_cluster_2")
        self.assertIn(
            "short_digit_phrase_collect_prioritization",
            payload["recommended_experiments"][0]["known_rejected_experiment_families"],
        )
        self.assertIn(
            "short_digit_phrase_collect_prioritization",
            payload["recommended_experiments"][0]["recommended_subclips"][0]["known_rejected_experiment_families"],
        )
        self.assertNotIn(
            "phrase_linked_pure_numeric_collect_prioritization",
            payload["recommended_experiments"][1]["recommended_subclips"][0].get("revalidation_candidate_experiment_families") or [],
        )
        self.assertEqual(payload["recommended_experiments"][1]["id"], "case2_precision_cluster_2")
        self.assertIn(
            "metadata_only_long_digit_phrase_local_padding_tightening",
            payload["recommended_experiments"][1]["known_rejected_experiment_families"],
        )
        self.assertIn(
            "phrase_linked_pure_numeric_collect_prioritization",
            payload["recommended_experiments"][1]["recommended_subclips"][0]["known_rejected_experiment_families"],
        )
        self.assertIn(
            "critical_pressure_collect_policy",
            payload["known_rejected_experiment_families"],
        )

    def test_next_owner_plan_payload_adds_low_yield_nondigit_collect_card(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 3,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 17.94,
                            "cluster_span_sec": 2.26,
                            "sample_texts": ["계속 17.8인데"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.16,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.68,
                                    "end": 17.94,
                                    "duration_sec": 2.26,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.0,
                                    "submission_index": 7,
                                    "submitted_chunk_duration_sec": 2.26,
                                    "submitted_chunk_offset_sec": 15.68,
                                    "completion_order_index": 7,
                                    "completed_chunk_elapsed_ms": 5783.881,
                                    "emission_order_index": 4,
                                    "emitted_chunk_elapsed_ms": 5784.015,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.16,
                                    "collected_duration_ratio": 0.513,
                                }
                            ],
                        },
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {
                                    "primary_text": "11.4",
                                    "start": 25.06,
                                    "end": 27.6,
                                    "duration_sec": 2.54,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": True,
                                    "has_digits": True,
                                    "matched_applied_text": "11.4에서 또 안 바뀌네",
                                    "best_applied_overlap_ratio": 0.063,
                                    "submission_index": 6,
                                    "submitted_chunk_duration_sec": 2.54,
                                    "submitted_chunk_offset_sec": 25.06,
                                    "completion_order_index": 5,
                                    "completed_chunk_elapsed_ms": 5030.028,
                                    "emission_order_index": 6,
                                    "emitted_chunk_elapsed_ms": 5784.243,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.8,
                                    "collected_duration_ratio": 0.709,
                                },
                                {
                                    "primary_text": "17.8에서 연비가 안 바뀌는데",
                                    "start": 22.06,
                                    "end": 25.46,
                                    "duration_sec": 3.4,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.0,
                                    "submission_index": 2,
                                    "submitted_chunk_duration_sec": 3.4,
                                    "submitted_chunk_offset_sec": 22.06,
                                    "completion_order_index": 2,
                                    "completed_chunk_elapsed_ms": 3532.688,
                                    "emission_order_index": 5,
                                    "emitted_chunk_elapsed_ms": 5784.16,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.86,
                                    "collected_duration_ratio": 0.547,
                                },
                            ],
                        },
                        {
                            "cluster_start": 7.44,
                            "cluster_end": 14.8,
                            "cluster_span_sec": 7.36,
                            "sample_texts": ["유지가 되고 있고요", "17.8", "변화가 없네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 1.08,
                            "clip_roles": [
                                {
                                    "primary_text": "변화가 없네",
                                    "start": 11.6,
                                    "end": 14.6,
                                    "duration_sec": 3.0,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": False,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.158,
                                    "submission_index": 1,
                                    "submitted_chunk_duration_sec": 3.0,
                                    "submitted_chunk_offset_sec": 11.6,
                                    "completion_order_index": 1,
                                    "completed_chunk_elapsed_ms": 2806.974,
                                    "emission_order_index": 3,
                                    "emitted_chunk_elapsed_ms": 5738.871,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 0.52,
                                    "collected_duration_ratio": 0.173,
                                    "collect_waste_score": 0.438,
                                },
                                {
                                    "primary_text": "유지가 되고 있고요",
                                    "start": 7.64,
                                    "end": 10.42,
                                    "duration_sec": 2.78,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": False,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.333,
                                    "submission_index": 3,
                                    "submitted_chunk_duration_sec": 2.78,
                                    "submitted_chunk_offset_sec": 7.64,
                                    "completion_order_index": 3,
                                    "completed_chunk_elapsed_ms": 4213.849,
                                    "emission_order_index": 1,
                                    "emitted_chunk_elapsed_ms": 5738.719,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 0.56,
                                    "collected_duration_ratio": 0.201,
                                    "collect_waste_score": 0.374,
                                },
                            ],
                        },
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precision_cluster_1")
        self.assertEqual(payload["recommended_experiments"][0]["cluster_start"], 15.68)
        self.assertEqual(payload["recommended_experiments"][1]["id"], "case2_precision_cluster_2")
        self.assertEqual(payload["recommended_experiments"][1]["cluster_start"], 22.06)
        self.assertEqual(payload["recommended_experiments"][2]["id"], "case2_low_yield_collect_clips")
        self.assertEqual(payload["recommended_experiments"][2]["selection_rule"], "non_digit_non_applied_low_overlap")
        self.assertEqual(payload["recommended_experiments"][2]["clip_roles"][0]["primary_text"], "변화가 없네")
        self.assertEqual(
            payload["recommended_experiments"][2]["recommended_subclips"][0]["experiment_type"],
            "low_yield_nondigit_subclip",
        )
        self.assertIn(
            "low_vad_nondigit_precision_skip",
            payload["recommended_experiments"][2]["recommended_subclips"][0]["known_rejected_experiment_families"],
        )
        self.assertEqual(
            payload["recommended_experiments"][2]["recommended_subclips"][0]["preferred_next_experiment_family"],
            "collect_path_non_skip_owner",
        )

    def test_next_owner_plan_payload_prioritizes_precision_edge_shift_gate_when_reject_reason_is_dominant(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 1,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {
                                    "primary_text": "미검증 숫자 구간 A",
                                    "start": 25.06,
                                    "end": 27.6,
                                    "duration_sec": 2.54,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": True,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "matched_output_text": "미검증 숫자 구간 A",
                                    "best_applied_overlap_ratio": 0.063,
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {"edge_shift": 0.52, "max_timing_shift": 0.28},
                                    "submission_index": 6,
                                    "submitted_chunk_duration_sec": 2.54,
                                    "submitted_chunk_offset_sec": 25.06,
                                    "completion_order_index": 6,
                                    "completed_chunk_elapsed_ms": 12416.801,
                                    "emission_order_index": 6,
                                    "emitted_chunk_elapsed_ms": 13337.747,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.8,
                                    "collected_duration_ratio": 0.709,
                                },
                                {
                                    "primary_text": "미검증 숫자 구간 B",
                                    "start": 22.06,
                                    "end": 25.46,
                                    "duration_sec": 3.4,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "matched_output_text": "미검증 숫자 구간 B",
                                    "best_applied_overlap_ratio": 0.0,
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {"edge_shift": 0.62, "max_timing_shift": 0.28},
                                    "submission_index": 2,
                                    "submitted_chunk_duration_sec": 3.4,
                                    "submitted_chunk_offset_sec": 22.06,
                                    "completion_order_index": 2,
                                    "completed_chunk_elapsed_ms": 8581.905,
                                    "emission_order_index": 5,
                                    "emitted_chunk_elapsed_ms": 13337.632,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.86,
                                    "collected_duration_ratio": 0.547,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertEqual(
            payload["next_owner_hints"],
            ["precision_apply_gate_edge_shift", "precision_overlap_groups", "major_runtime_precision"],
        )
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precision_edge_shift_gate")
        self.assertEqual(payload["recommended_experiments"][0]["dominant_reject_reason"], "candidate_edge_shift_exceeded")
        self.assertEqual(payload["recommended_experiments"][0]["dominant_reject_count"], 2)
        self.assertEqual(
            payload["recommended_experiments"][0]["recommended_subclips"][0]["precision_reject_reason"],
            "candidate_edge_shift_exceeded",
        )
        self.assertEqual(
            payload["recommended_experiments"][0]["recommended_subclips"][0]["preferred_next_experiment_family"],
            "precision_apply_gate_non_skip_owner",
        )

    def test_next_owner_plan_payload_deprioritizes_exhausted_precision_edge_shift_gate(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 2,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 3,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 17.94,
                            "cluster_span_sec": 2.26,
                            "sample_texts": ["계속 17.8인데"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.86,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.88,
                                    "end": 17.74,
                                    "duration_sec": 1.86,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "matched_output_text": "계속 17.8인데",
                                    "best_applied_overlap_ratio": 0.0,
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {"edge_shift": 0.64, "max_timing_shift": 0.28},
                                    "submission_index": 2,
                                    "submitted_chunk_duration_sec": 1.86,
                                    "submitted_chunk_offset_sec": 15.88,
                                    "completion_order_index": 2,
                                    "completed_chunk_elapsed_ms": 5600.083,
                                    "emission_order_index": 2,
                                    "emitted_chunk_elapsed_ms": 5600.083,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.86,
                                    "collected_duration_ratio": 1.0,
                                }
                            ],
                        },
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 3.66,
                            "clip_roles": [
                                {
                                    "primary_text": "11.4",
                                    "start": 25.06,
                                    "end": 27.6,
                                    "duration_sec": 2.54,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": True,
                                    "has_digits": True,
                                    "matched_applied_text": "11.4에서 또 안 바뀌네",
                                    "matched_output_text": "11.4",
                                    "best_applied_overlap_ratio": 0.063,
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {"edge_shift": 0.52, "max_timing_shift": 0.28},
                                    "submission_index": 6,
                                    "submitted_chunk_duration_sec": 2.54,
                                    "submitted_chunk_offset_sec": 25.06,
                                    "completion_order_index": 5,
                                    "completed_chunk_elapsed_ms": 5483.84,
                                    "emission_order_index": 6,
                                    "emitted_chunk_elapsed_ms": 5600.601,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.8,
                                    "collected_duration_ratio": 0.709,
                                },
                                {
                                    "primary_text": "17.8에서 연비가 안 바뀌는데",
                                    "start": 22.06,
                                    "end": 25.46,
                                    "duration_sec": 3.4,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "matched_output_text": "17.8에서 연비가 안 바뀌는데",
                                    "best_applied_overlap_ratio": 0.0,
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {"edge_shift": 0.62, "max_timing_shift": 0.28},
                                    "submission_index": 1,
                                    "submitted_chunk_duration_sec": 3.4,
                                    "submitted_chunk_offset_sec": 22.06,
                                    "completion_order_index": 2,
                                    "completed_chunk_elapsed_ms": 3423.73,
                                    "emission_order_index": 5,
                                    "emitted_chunk_elapsed_ms": 5600.461,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.86,
                                    "collected_duration_ratio": 0.547,
                                },
                            ],
                        },
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertEqual(
            payload["next_owner_hints"],
            [
                "collect_path_non_skip_owner",
                "collect_path_non_padding_owner",
                "precision_overlap_groups",
                "major_runtime_precision",
            ],
        )
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precision_cluster_1")
        self.assertNotIn(
            "case2_precision_edge_shift_gate",
            [item["id"] for item in payload["recommended_experiments"]],
        )

    def test_next_owner_plan_payload_deprioritizes_cruise_prefix_edge_shift_gate_when_output_text_is_already_recovered(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 2,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 2,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 3.52,
                            "cluster_end": 5.76,
                            "cluster_span_sec": 2.24,
                            "sample_texts": ["80으로 크루즈 컨트롤 걸었고요"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.42,
                            "clip_roles": [
                                {
                                    "primary_text": "80으로 크루즈 컨트롤 걸었고요",
                                    "start": 3.52,
                                    "end": 5.76,
                                    "duration_sec": 2.24,
                                    "likely_applied": False,
                                    "matched_output_text": "80km/h로 크루즈 컨트롤 걸었고요",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 0.56,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "80으로 크루즈 컨트롤",
                                    },
                                    "completed_chunk_elapsed_ms": 5425.99,
                                    "submitted_chunk_duration_sec": 2.24,
                                    "submitted_chunk_offset_sec": 3.52,
                                    "collected_total_duration_sec": 1.42,
                                }
                            ],
                        },
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 17.94,
                            "cluster_span_sec": 2.26,
                            "sample_texts": ["계속 17.8인데"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.86,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.88,
                                    "end": 17.74,
                                    "duration_sec": 1.86,
                                    "likely_applied": False,
                                    "matched_output_text": "계속 17.8인데",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 0.6,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "계속 17 .8인데",
                                    },
                                    "completed_chunk_elapsed_ms": 5414.53,
                                    "submitted_chunk_duration_sec": 1.86,
                                    "submitted_chunk_offset_sec": 15.88,
                                    "collected_total_duration_sec": 1.2,
                                }
                            ],
                        },
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        ids = [item["id"] for item in payload["recommended_experiments"]]
        self.assertIn("case2_precision_candidate_text_artifact", ids)
        self.assertIn("case2_low_yield_collect_clips", ids)
        self.assertNotIn(
            "case2_precision_edge_shift_gate",
            ids,
        )

    def test_case2_precision_candidate_truncation_metrics_detects_short_prefix_candidates(self):
        metrics = server_mode_runner._case2_precision_candidate_truncation_metrics(
            {
                "primary_text": "유지가 되고 있고요",
                "matched_output_text": "유지가 되고 있고요",
                "precision_reject_reason": "candidate_edge_shift_exceeded",
                "precision_reject_detail": {
                    "edge_shift": 1.8,
                    "max_timing_shift": 0.28,
                    "candidate_text": "유지가",
                },
            }
        )

        self.assertEqual(metrics["candidate_text"], "유지가")
        self.assertLess(metrics["candidate_ratio"], 0.7)
        self.assertEqual(metrics["is_prefix"], "1")
        self.assertEqual(metrics["output_matches_primary"], "1")

    def test_case2_precision_candidate_text_artifact_metrics_detects_spacing_artifact(self):
        metrics = server_mode_runner._case2_precision_candidate_text_artifact_metrics(
            {
                "primary_text": "계속 17.8인데",
                "matched_output_text": "계속 17.8인데",
                "precision_reject_reason": "candidate_edge_shift_exceeded",
                "precision_reject_detail": {
                    "edge_shift": 0.6,
                    "max_timing_shift": 0.28,
                    "candidate_text": "계속 17 .8인데",
                },
            }
        )

        self.assertEqual(metrics["candidate_text"], "계속 17 .8인데")
        self.assertEqual(metrics["artifact_kind"], "spacing_normalization")
        self.assertEqual(metrics["output_matches_primary"], "1")

    def test_next_owner_plan_payload_surfaces_precision_candidate_text_artifact_owner(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 2,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 2,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 14.32,
                            "sample_texts": ["계속 17.8인데", "17.8에서 연비가 안 바뀌는데", "11.4"],
                            "non_applied_clip_count": 3,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 4.86,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.88,
                                    "end": 17.74,
                                    "duration_sec": 1.86,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "matched_output_text": "계속 17.8인데",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 0.6,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "계속 17 .8인데",
                                    },
                                    "submission_index": 4,
                                    "submitted_chunk_duration_sec": 1.86,
                                    "submitted_chunk_offset_sec": 15.88,
                                    "completion_order_index": 4,
                                    "completed_chunk_elapsed_ms": 5425.99,
                                    "emission_order_index": 4,
                                    "emitted_chunk_elapsed_ms": 5427.779,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.2,
                                    "collected_duration_ratio": 0.645,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertIn("precision_candidate_text_artifact", payload["next_owner_hints"])
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precision_candidate_text_artifact")
        self.assertEqual(
            payload["recommended_experiments"][0]["recommended_subclips"][0]["candidate_text"],
            "계속 17 .8인데",
        )
        self.assertEqual(
            payload["recommended_experiments"][0]["recommended_subclips"][0]["preferred_next_experiment_family"],
            "candidate_text_artifact_owner",
        )

    def test_next_owner_plan_payload_skips_hard_rejected_numeric_spacing_artifact_owner(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 2,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 2,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 4.8,
                            "clip_roles": [
                                {
                                    "primary_text": "11.4",
                                    "start": 25.06,
                                    "end": 27.6,
                                    "duration_sec": 2.54,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "matched_output_text": "11.4",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 0.52,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "11 .4",
                                    },
                                    "submission_index": 5,
                                    "submitted_chunk_duration_sec": 2.54,
                                    "submitted_chunk_offset_sec": 25.06,
                                    "completion_order_index": 4,
                                    "completed_chunk_elapsed_ms": 4656.024,
                                    "emission_order_index": 6,
                                    "emitted_chunk_elapsed_ms": 5427.573,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.8,
                                    "collected_duration_ratio": 0.709,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertNotIn("precision_candidate_text_artifact", payload["next_owner_hints"])
        self.assertNotEqual(payload["recommended_experiments"][0]["id"], "case2_precision_candidate_text_artifact")

    def test_next_owner_plan_payload_surfaces_precision_candidate_truncation_owner(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 2,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 2,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 7.44,
                            "cluster_end": 14.8,
                            "cluster_span_sec": 7.36,
                            "sample_texts": ["유지가 되고 있고요", "17.8", "변화가 없네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 1.08,
                            "clip_roles": [
                                {
                                    "primary_text": "테스트 자막 행",
                                    "start": 11.4,
                                    "end": 14.8,
                                    "duration_sec": 3.4,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "matched_output_text": "테스트 자막 행",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 2.120001,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "테스트",
                                    },
                                    "submission_index": 1,
                                    "submitted_chunk_duration_sec": 3.4,
                                    "submitted_chunk_offset_sec": 11.4,
                                    "completion_order_index": 1,
                                    "completed_chunk_elapsed_ms": 2611.985,
                                    "emission_order_index": 3,
                                    "emitted_chunk_elapsed_ms": 5426.969,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 0.52,
                                    "collected_duration_ratio": 0.153,
                                },
                                {
                                    "primary_text": "다른 테스트 자막",
                                    "start": 7.44,
                                    "end": 10.82,
                                    "duration_sec": 3.38,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "matched_output_text": "다른 테스트 자막",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 1.8,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "다른",
                                    },
                                    "submission_index": 3,
                                    "submitted_chunk_duration_sec": 3.38,
                                    "submitted_chunk_offset_sec": 7.44,
                                    "completion_order_index": 3,
                                    "completed_chunk_elapsed_ms": 3929.96,
                                    "emission_order_index": 1,
                                    "emitted_chunk_elapsed_ms": 5426.604,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 0.56,
                                    "collected_duration_ratio": 0.166,
                                },
                            ],
                        }
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertIn("precision_candidate_truncation", payload["next_owner_hints"])
        self.assertEqual(payload["recommended_experiments"][0]["id"], "case2_precision_candidate_truncation")
        self.assertEqual(
            payload["recommended_experiments"][0]["recommended_subclips"][0]["candidate_text"],
            "다른",
        )
        self.assertEqual(
            payload["recommended_experiments"][0]["recommended_subclips"][0]["preferred_next_experiment_family"],
            "collect_path_candidate_truncation_owner",
        )

    def test_next_owner_plan_payload_skips_stale_precision_candidate_truncation_owner(self):
        payload = server_mode_runner._next_owner_plan_payload(
            "case2",
            {
                "winner": {
                    "runtime_stage_budget": {
                        "word_precision_non_applied_overlap_group_count": 2,
                        "precision_candidate_count": 8,
                        "precision_applied_count": 2,
                        "slowest_major_phase_name": "ensemble_transcribe",
                        "slowest_word_precision_phase_name": "collect_segments",
                    },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 7.44,
                            "cluster_end": 14.8,
                            "cluster_span_sec": 7.36,
                            "sample_texts": ["유지가 되고 있고요", "17.8", "변화가 없네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 1.08,
                            "clip_roles": [
                                {
                                    "primary_text": "변화가 없네",
                                    "start": 11.4,
                                    "end": 14.8,
                                    "duration_sec": 3.4,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "matched_output_text": "변화가 없네",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 2.120001,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "변화가",
                                    },
                                    "submission_index": 1,
                                    "submitted_chunk_duration_sec": 3.4,
                                    "submitted_chunk_offset_sec": 11.4,
                                    "completion_order_index": 1,
                                    "completed_chunk_elapsed_ms": 2611.985,
                                    "emission_order_index": 3,
                                    "emitted_chunk_elapsed_ms": 5426.969,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 0.52,
                                    "collected_duration_ratio": 0.153,
                                },
                                {
                                    "primary_text": "유지가 되고 있고요",
                                    "start": 7.44,
                                    "end": 10.82,
                                    "duration_sec": 3.38,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "matched_output_text": "유지가 되고 있고요",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 1.8,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": "유지가",
                                    },
                                    "submission_index": 3,
                                    "submitted_chunk_duration_sec": 3.38,
                                    "submitted_chunk_offset_sec": 7.44,
                                    "completion_order_index": 3,
                                    "completed_chunk_elapsed_ms": 3929.96,
                                    "emission_order_index": 1,
                                    "emitted_chunk_elapsed_ms": 5426.604,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 0.56,
                                    "collected_duration_ratio": 0.166,
                                },
                            ],
                        },
                        {
                            "cluster_start": 22.06,
                            "cluster_end": 30.0,
                            "cluster_span_sec": 7.94,
                            "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4", "11.4에서 또 안 바뀌네"],
                            "non_applied_clip_count": 2,
                            "applied_clip_count": 1,
                            "non_applied_collected_total_duration_sec": 4.8,
                            "clip_roles": [
                                {
                                    "primary_text": "17.8에서 연비가 안 바뀌는데",
                                    "start": 22.06,
                                    "end": 25.06,
                                    "duration_sec": 3.0,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "matched_output_text": "17.8에서 연비가 안 바뀌는데",
                                    "precision_reject_reason": "candidate_edge_shift_exceeded",
                                    "precision_reject_detail": {
                                        "edge_shift": 0.62,
                                        "max_timing_shift": 0.28,
                                        "candidate_text": ".8에서 연비가",
                                    },
                                    "submission_index": 2,
                                    "submitted_chunk_duration_sec": 3.0,
                                    "submitted_chunk_offset_sec": 22.06,
                                    "completion_order_index": 2,
                                    "completed_chunk_elapsed_ms": 3532.688,
                                    "emission_order_index": 2,
                                    "emitted_chunk_elapsed_ms": 5426.7,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.86,
                                    "collected_duration_ratio": 0.62,
                                },
                            ],
                        },
                    ],
                    "artifact_primary_recheck_plan_rows": {"merged": []},
                }
            },
        )

        self.assertNotIn("precision_candidate_truncation", payload["next_owner_hints"])
        self.assertNotEqual(payload["recommended_experiments"][0]["id"], "case2_precision_candidate_truncation")

    def test_case2_short_digit_collect_prioritization_is_now_hard_rejected(self):
        hints = server_mode_runner._case2_subclip_rejection_hints("계속 17.8인데")

        self.assertIn(
            "selective_secondary_overlap_precision_skip",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "short_digit_phrase_collect_prioritization",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "numeric_core_digit_phrase_edge_shift_salvage",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "edge_safe_alternate_digit_candidate",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "digit_edge_clip",
            hints["known_rejected_experiment_families"],
        )
        self.assertNotIn(
            "short_digit_phrase_collect_prioritization",
            hints.get("revalidation_candidate_experiment_families") or [],
        )
        joined_notes = " ".join(hints["avoid_notes"]).lower()
        self.assertIn("did not change live submission order", joined_notes)
        self.assertIn("numeric-core digit-phrase edge-shift salvage", joined_notes)
        self.assertIn("edge-safe alternate digit candidate fallback", joined_notes)
        self.assertIn("digit edge clipping kept the same precision-applied count", joined_notes)

    def test_case2_cruise_prefix_owner_new_split_and_padding_families_are_hard_rejected(self):
        hints = server_mode_runner._case2_subclip_rejection_hints("80으로 크루즈 컨트롤 걸었고요")

        self.assertIn(
            "precision_apply_gate_prefix_tail_split",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "longer_digit_phrase_collect_padding_restore",
            hints["known_rejected_experiment_families"],
        )
        self.assertEqual(
            hints["preferred_next_experiment_family"],
            "precision_apply_gate_non_split_owner",
        )
        joined_notes = " ".join(hints["avoid_notes"]).lower()
        self.assertIn("segment churn", joined_notes)
        self.assertIn("collect padding", joined_notes)

    def test_case2_cruise_prefix_owner_is_now_exhausted_when_output_text_already_recovers_row(self):
        exhausted = server_mode_runner._case2_precision_edge_shift_subclip_exhausted(
            {
                "primary_text": "80으로 크루즈 컨트롤 걸었고요",
                "matched_output_text": "80km/h로 크루즈 컨트롤 걸었고요",
                "precision_reject_detail": {"candidate_text": "80으로 크루즈 컨트롤"},
            }
        )

        self.assertTrue(exhausted)

    def test_case2_phrase_linked_pure_numeric_collect_prioritization_is_now_hard_rejected(self):
        hints = server_mode_runner._case2_subclip_rejection_hints("11.4")

        self.assertIn(
            "phrase_linked_pure_numeric_collect_prioritization",
            hints["known_rejected_experiment_families"],
        )
        self.assertNotIn(
            "phrase_linked_pure_numeric_collect_prioritization",
            hints.get("revalidation_candidate_experiment_families") or [],
        )
        self.assertIn(
            "did not move live submission order",
            " ".join(hints["avoid_notes"]).lower(),
        )
        self.assertIn(
            "numeric_spacing_artifact_edge_shift_relaxation",
            hints["known_rejected_experiment_families"],
        )

    def test_case2_long_digit_phrase_collect_defer_is_now_hard_rejected_after_causal_negative_result(self):
        hints = server_mode_runner._case2_subclip_rejection_hints("17.8에서 연비가 안 바뀌는데")

        self.assertIn(
            "selective_secondary_overlap_precision_skip",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "long_metadata_only_digit_phrase_collect_defer",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "long_digit_leading_leftpad",
            hints["known_rejected_experiment_families"],
        )
        self.assertNotIn(
            "long_metadata_only_digit_phrase_collect_defer",
            hints.get("revalidation_candidate_experiment_families") or [],
        )
        self.assertIn(
            "moved live submission order",
            " ".join(hints["avoid_notes"]).lower(),
        )
        self.assertIn(
            "left prepad",
            " ".join(hints["avoid_notes"]).lower(),
        )

    def test_case2_low_yield_nondigit_clip_hints_avoid_broad_skip_family(self):
        hints = server_mode_runner._case2_subclip_rejection_hints("유지가 되고 있고요")

        self.assertIn(
            "low_vad_nondigit_precision_skip",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "low_vad_nondigit_collect_defer",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "low_vad_phrase_full_speech_filter",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "low_vad_nondigit_collect_tail_padding_restore",
            hints["known_rejected_experiment_families"],
        )
        self.assertEqual(
            hints["preferred_next_experiment_family"],
            "collect_path_non_skip_owner",
        )

    def test_case2_global_rejection_hints_include_collect_policy_family(self):
        hints = server_mode_runner._case2_global_rejection_hints()

        self.assertIn(
            "critical_pressure_collect_policy",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "native_pressure_stage_source",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "critical_pressure_snapshot_thresholds",
            hints["known_rejected_experiment_families"],
        )
        self.assertIn(
            "collect-path owners",
            " ".join(hints["avoid_notes"]).lower(),
        )

    def test_run_next_owner_plan_supports_accepted_target(self):
        with TemporaryDirectory() as tmpdir:
            case2 = Path(tmpdir) / "case2.json"
            winner_dir = Path(tmpdir) / "apple_case2_high_selective_timing_priority"
            winner_dir.mkdir(parents=True, exist_ok=True)
            case2.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "apple_case2_high_selective_timing_priority",
                                "elapsed_sec": 14.77,
                                "quality": {
                                    "quality_score": 85.164,
                                    "timing_priority_quality_score": 85.498,
                                    "timing_mae_sec": 0.4076,
                                },
                                "native_stt_segments_summary": {
                                    "word_precision_count": 3,
                                    "stt2_selected_count": 0,
                                    "recheck_applied_count": 0,
                                    "stt2_coverage_ratio": 0.0,
                                },
                                "settings": {},
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (winner_dir / "raw_segments.json").write_text("[]", encoding="utf-8")
            (winner_dir / "output_segments.json").write_text("[]", encoding="utf-8")
            (winner_dir / "word_precision_runtime_trace.json").write_text("[]", encoding="utf-8")
            stdout = StringIO()
            args = argparse.Namespace(
                artifact_json="",
                accepted_target="case2",
                baseline_json=str(case2),
                case1_json=str(case2),
                case2_json=str(case2),
            )
            with patch("sys.stdout", stdout), patch(
                "tools.server_mode_runner._artifact_summary_payload",
                return_value={
                    "winner": {
                        "runtime_stage_budget": {
                            "word_precision_non_applied_overlap_group_count": 1,
                            "precision_candidate_count": 6,
                            "precision_applied_count": 3,
                            "slowest_major_phase_name": "ensemble_transcribe",
                            "slowest_word_precision_phase_name": "collect_segments",
                        },
                    "artifact_word_precision_overlap_groups": [
                        {
                            "cluster_start": 15.68,
                            "cluster_end": 17.94,
                            "cluster_span_sec": 2.26,
                            "sample_texts": ["계속 17.8인데"],
                            "non_applied_clip_count": 1,
                            "applied_clip_count": 0,
                            "non_applied_collected_total_duration_sec": 1.16,
                            "clip_roles": [
                                {
                                    "primary_text": "계속 17.8인데",
                                    "start": 15.68,
                                    "end": 17.94,
                                    "duration_sec": 2.26,
                                    "likely_applied": False,
                                    "role": "non_applied",
                                    "pure_numeric": False,
                                    "has_digits": True,
                                    "matched_applied_text": "",
                                    "best_applied_overlap_ratio": 0.0,
                                    "submission_index": 7,
                                    "submitted_chunk_duration_sec": 2.26,
                                    "submitted_chunk_offset_sec": 15.68,
                                    "completion_order_index": 7,
                                    "completed_chunk_elapsed_ms": 5783.881,
                                    "emission_order_index": 4,
                                    "emitted_chunk_elapsed_ms": 5784.015,
                                    "duration_first_submission_enabled": True,
                                    "collected_total_duration_sec": 1.16,
                                    "collected_duration_ratio": 0.513,
                                }
                            ],
                        },
                        {
                            "cluster_start": 22.06,
                                "cluster_end": 30.0,
                                "cluster_span_sec": 7.94,
                                "sample_texts": ["17.8에서 연비가 안 바뀌는데", "11.4"],
                                "non_applied_clip_count": 2,
                                "applied_clip_count": 1,
                                "non_applied_collected_total_duration_sec": 3.66,
                            }
                        ],
                        "artifact_primary_recheck_plan_rows": {"merged": []},
                    }
                },
            ):
                code = server_mode_runner._run_next_owner_plan(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["target"], "case2")
        self.assertEqual(payload["artifact_json"], str(case2))
        self.assertEqual(
            payload["recommended_experiments"][0]["focus"],
            "word_precision_collect_path",
        )
        self.assertEqual(payload["preconditions"], [])

    def test_run_preset_once_payload_attaches_recheck_source_counts_from_stdout(self):
        with TemporaryDirectory() as tmpdir:
            artifact = Path(tmpdir) / "artifact.json"
            artifact.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case2",
                                "elapsed_sec": 16.717,
                                "quality": {
                                    "quality_score": 85.164,
                                    "timing_priority_quality_score": 85.498,
                                    "timing_mae_sec": 0.4076,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            proc = mock.Mock()
            proc.returncode = 0
            proc.stdout = (
                "  🧭 [선택 STT2 재검사] 후보 source low_score=4 missing_voice=1 route_hint=1 merged=6\\n"
                + json.dumps({"json": str(artifact)})
            )
            proc.stderr = ""
            with patch("tools.server_mode_runner.subprocess.run", return_value=proc):
                payload = server_mode_runner._run_preset_once_payload(
                    preset_name="apple_case2_timing",
                    media="/tmp/in.mp4",
                    reference_srt="/tmp/ref.srt",
                    start_sec=0.0,
                    duration_sec=30.0,
                    suite="variants",
                    stt_profile="current",
                    ranking_policy="timing_priority_speed_weighted",
                    llm_model="",
                    cached_raw_segments="",
                    keep_artifacts=False,
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["winner"]["recheck_source_counts"]["merged"], 6)

    def test_matrix_preset_runs_sequential_presets_and_emits_comparisons(self):
        args = argparse.Namespace(
            presets=["baseline_same_slice", "apple_case1_timing", "apple_case2_timing"],
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
        )
        with TemporaryDirectory() as tmpdir:
            baseline = Path(tmpdir) / "baseline.json"
            case1 = Path(tmpdir) / "case1.json"
            case2 = Path(tmpdir) / "case2.json"
            baseline.write_text(
                json.dumps(
                    {"ranked_results": [{"name": "baseline", "elapsed_sec": 88.586, "quality": {"quality_score": 70.928, "timing_priority_quality_score": 72.057, "timing_mae_sec": 0.686}, "rank": 1}]}
                ),
                encoding="utf-8",
            )
            case1.write_text(
                json.dumps(
                    {"ranked_results": [{"name": "case1", "elapsed_sec": 13.18, "quality": {"quality_score": 64.399, "timing_priority_quality_score": 66.278, "timing_mae_sec": 0.7567}, "rank": 1}]}
                ),
                encoding="utf-8",
            )
            case2.write_text(
                json.dumps(
                    {"ranked_results": [{"name": "case2", "elapsed_sec": 17.794, "quality": {"quality_score": 85.164, "timing_priority_quality_score": 85.498, "timing_mae_sec": 0.4076}, "rank": 1}]}
                ),
                encoding="utf-8",
            )

            returns = []
            for path in (baseline, case1, case2):
                proc = mock.Mock()
                proc.returncode = 0
                proc.stdout = json.dumps({"json": str(path)})
                proc.stderr = ""
                returns.append(proc)

            stdout = StringIO()
            with patch("tools.server_mode_runner.subprocess.run", side_effect=returns), patch("sys.stdout", stdout):
                code = server_mode_runner._run_matrix_preset(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["baseline_preset"], "baseline_same_slice")
        self.assertEqual(len(payload["runs"]), 3)
        self.assertEqual(len(payload["comparisons_vs_first"]), 2)
        self.assertEqual(payload["winner_by_timing_priority_quality"]["preset"], "apple_case2_timing")
        self.assertEqual(payload["winner_by_speed"]["preset"], "apple_case1_timing")
        case2_delta = payload["comparisons_vs_first"][1]["deltas"]
        self.assertAlmostEqual(case2_delta["quality_score_delta"], 14.236)
        self.assertAlmostEqual(case2_delta["timing_mae_sec_delta"], -0.2784)

    def test_matrix_repeat_aggregates_per_preset_and_reports_mean_winners(self):
        args = argparse.Namespace(
            presets=["baseline_same_slice", "apple_case1_timing", "apple_case2_timing"],
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
            repeat=2,
        )
        with TemporaryDirectory() as tmpdir:
            baseline1 = Path(tmpdir) / "baseline1.json"
            baseline2 = Path(tmpdir) / "baseline2.json"
            case11 = Path(tmpdir) / "case11.json"
            case12 = Path(tmpdir) / "case12.json"
            case21 = Path(tmpdir) / "case21.json"
            case22 = Path(tmpdir) / "case22.json"
            fixtures = [
                (baseline1, 88.0, 74.0, 75.0, 0.68, "baseline"),
                (baseline2, 84.0, 75.0, 76.0, 0.66, "baseline"),
                (case11, 13.0, 64.0, 66.0, 0.75, "case1"),
                (case12, 12.0, 65.0, 67.0, 0.74, "case1"),
                (case21, 18.0, 85.0, 85.4, 0.41, "case2"),
                (case22, 17.0, 85.2, 85.5, 0.40, "case2"),
            ]
            for path, elapsed, quality, timing, mae, name in fixtures:
                path.write_text(
                    json.dumps(
                        {
                            "ranked_results": [
                                {
                                    "name": name,
                                    "elapsed_sec": elapsed,
                                    "quality": {
                                        "quality_score": quality,
                                        "timing_priority_quality_score": timing,
                                        "timing_mae_sec": mae,
                                    },
                                    "rank": 1,
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
            returns = []
            for path, *_ in fixtures:
                proc = mock.Mock()
                proc.returncode = 0
                proc.stdout = json.dumps({"json": str(path)})
                proc.stderr = ""
                returns.append(proc)

            stdout = StringIO()
            with patch("tools.server_mode_runner.subprocess.run", side_effect=returns), patch("sys.stdout", stdout):
                code = server_mode_runner._run_matrix_repeat(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["repeat"], 2)
        self.assertEqual(len(payload["per_preset"]), 3)
        self.assertEqual(payload["winner_by_mean_timing_priority_quality"]["preset"], "apple_case2_timing")
        self.assertEqual(payload["winner_by_mean_speed"]["preset"], "apple_case1_timing")
        case2_delta = payload["comparisons_vs_first_mean"][1]["deltas"]
        self.assertAlmostEqual(case2_delta["quality_score_mean_delta"], 10.6)
        self.assertAlmostEqual(case2_delta["timing_mae_sec_mean_delta"], -0.265)

    def test_repeat_preset_aggregates_multiple_successful_runs(self):
        args = argparse.Namespace(
            preset="apple_case1_timing",
            media="/tmp/in.mp4",
            reference_srt="/tmp/ref.srt",
            start_sec=0.0,
            duration_sec=30.0,
            suite="variants",
            stt_profile="current",
            ranking_policy="timing_priority_speed_weighted",
            llm_model="",
            cached_raw_segments="",
            keep_artifacts=False,
            repeat=2,
        )
        with TemporaryDirectory() as tmpdir:
            artifact1 = Path(tmpdir) / "a1.json"
            artifact2 = Path(tmpdir) / "a2.json"
            artifact1.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case1",
                                "elapsed_sec": 17.165,
                                "quality": {
                                    "quality_score": 86.731,
                                    "timing_priority_quality_score": 86.742,
                                    "timing_mae_sec": 0.4304,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            artifact2.write_text(
                json.dumps(
                    {
                        "ranked_results": [
                            {
                                "name": "case1",
                                "elapsed_sec": 11.595,
                                "quality": {
                                    "quality_score": 86.731,
                                    "timing_priority_quality_score": 86.742,
                                    "timing_mae_sec": 0.4304,
                                },
                                "rank": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            stdout = StringIO()
            with patch("tools.server_mode_runner.subprocess.run") as run_mock, patch("sys.stdout", stdout):
                run_mock.side_effect = [
                    mock.Mock(returncode=0, stdout=json.dumps({"json": str(artifact1)}), stderr=""),
                    mock.Mock(returncode=0, stdout=json.dumps({"json": str(artifact2)}), stderr=""),
                ]
                code = server_mode_runner._run_repeat_preset(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["completed_runs"], 2)
        self.assertAlmostEqual(payload["aggregate"]["elapsed_sec"]["mean"], 14.38)
        self.assertAlmostEqual(payload["aggregate"]["elapsed_sec"]["spread"], 5.57)


if __name__ == "__main__":
    unittest.main()
